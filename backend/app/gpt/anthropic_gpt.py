"""
Anthropic GPT 实现
使用 Anthropic 原生 API 进行视频笔记生成
"""
import time
import requests
from typing import List
from datetime import timedelta
from pydantic import BaseModel

from app.gpt.base import GPT
from app.gpt.prompt_builder import (
    generate_base_prompt, 
    get_system_prompt,
    estimate_tokens,
    should_use_chunking,
)
from app.models.gpt_model import GPTSource
from app.models.transcriber_model import TranscriptSegment
from app.utils.logger import get_logger

logger = get_logger(__name__)

# 分段处理的配置常量
MAX_SEGMENT_TOKENS = 32000  # 单次处理的最大 token 数（现代模型支持 128K-200K 上下文）
MAX_RETRIES = 3  # API 调用最大重试次数
RETRY_DELAY = 2  # 重试间隔（秒）


class AnthropicModel(BaseModel):
    """Anthropic 模型信息"""
    id: str
    object: str = "model"
    created: int = 0
    owned_by: str = "anthropic"


class AnthropicModelList(BaseModel):
    """Anthropic 模型列表"""
    object: str = "list"
    data: List[AnthropicModel]


class AnthropicGPT(GPT):
    """
    Anthropic GPT 实现类
    支持 Claude 系列模型的 API 调用
    """

    def __init__(self, client, model: str, temperature: float = 0.7):
        """
        初始化 Anthropic GPT
        :param client: anthropic.Anthropic 客户端
        :param model: 模型名称，如 claude-3-5-sonnet-20241022
        :param temperature: 温度参数，默认 0.7（平衡稳定性和表达多样性）
        """
        logger.info(f"[AnthropicGPT] 初始化: model={model}, temperature={temperature}")
        self.client = client
        self.model = model
        self.temperature = temperature
        self.screenshot = False
        self.link = False
        logger.debug(f"[AnthropicGPT] 客户端类型: {type(client).__name__}")

    def _format_time(self, seconds: float) -> str:
        """格式化时间为 MM:SS 格式"""
        return str(timedelta(seconds=int(seconds)))[2:]

    def _build_segment_text(self, segments: List[TranscriptSegment]) -> str:
        """构建转写片段文本"""
        return "\n".join(
            f"{self._format_time(seg.start)} - {seg.text.strip()}"
            for seg in segments
        )

    def ensure_segments_type(self, segments) -> List[TranscriptSegment]:
        """确保片段类型为 TranscriptSegment"""
        return [TranscriptSegment(**seg) if isinstance(seg, dict) else seg for seg in segments]

    def _split_segments_into_chunks(
        self, 
        segments: List[TranscriptSegment], 
        max_tokens: int = MAX_SEGMENT_TOKENS
    ) -> List[List[TranscriptSegment]]:
        """
        将转录片段分割成多个块
        """
        chunks = []
        current_chunk = []
        current_tokens = 0
        
        for seg in segments:
            seg_text = f"{self._format_time(seg.start)} - {seg.text.strip()}"
            seg_tokens = estimate_tokens(seg_text)
            
            if current_tokens + seg_tokens > max_tokens and current_chunk:
                chunks.append(current_chunk)
                current_chunk = []
                current_tokens = 0
            
            current_chunk.append(seg)
            current_tokens += seg_tokens
        
        if current_chunk:
            chunks.append(current_chunk)
        
        logger.info(f"[AnthropicGPT] 将 {len(segments)} 个片段分割成 {len(chunks)} 个块")
        return chunks

    def _get_api_config(self):
        """获取 API 配置"""
        base_url = getattr(self.client, 'base_url', None)
        api_key = getattr(self.client, 'api_key', None)
        return base_url, api_key

    def _build_api_url(self, base_url: str, endpoint: str) -> str:
        """构建 API URL"""
        base_url_str = str(base_url).rstrip('/')
        if not base_url_str.endswith('/v1'):
            base_url_str = base_url_str + '/v1'
        return f"{base_url_str}/{endpoint}"

    def _build_image_content(self, url: str) -> dict:
        """构建图片内容块"""
        if url.startswith('data:'):
            # Base64 格式
            media_type = url.split(';')[0].split(':')[1]
            data = url.split(',')[1]
            return {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": data
                }
            }
        else:
            # URL 格式
            return {
                "type": "image",
                "source": {
                    "type": "url",
                    "url": url
                }
            }

    def create_messages(self, segments: List[TranscriptSegment], **kwargs) -> list:
        """
        创建 Anthropic 格式的消息
        Anthropic 的图片格式与 OpenAI 不同
        """
        logger.debug(f"[AnthropicGPT] 构建消息: segments数量={len(segments)}, title={kwargs.get('title')}")

        video_img_urls = kwargs.get('video_img_urls', [])
        has_images = bool(video_img_urls)

        content_text = generate_base_prompt(
            title=kwargs.get('title'),
            segment_text=self._build_segment_text(segments),
            tags=kwargs.get('tags'),
            _format=kwargs.get('_format'),
            style=kwargs.get('style'),
            extras=kwargs.get('extras'),
            has_images=has_images,  # 传递图片标志以启用视觉文字提取
        )

        logger.debug(f"[AnthropicGPT] 生成的 prompt 长度: {len(content_text)} 字符")
        if has_images:
            logger.info(f"[AnthropicGPT] 🔤 已启用视觉文字提取增强模式")

        # 构建消息内容
        content = [{"type": "text", "text": content_text}]

        if video_img_urls:
            logger.info(f"[AnthropicGPT] 添加 {len(video_img_urls)} 张图片到消息中")
            for url in video_img_urls:
                content.append(self._build_image_content(url))

        messages = [{"role": "user", "content": content}]
        logger.debug(f"[AnthropicGPT] 消息构建完成: content块数量={len(content)}")
        return messages

    def _create_chunk_messages(
        self, 
        chunk_index: int, 
        total_chunks: int,
        segments: List[TranscriptSegment], 
        **kwargs
    ) -> list:
        """创建分块处理的消息"""
        segment_text = self._build_segment_text(segments)
        
        content_text = f"""## 视频信息
- **标题**：{kwargs.get('title', '未知标题')}
- **当前部分**：第 {chunk_index + 1}/{total_chunks} 部分

## 分段处理说明
这是视频的第 {chunk_index + 1}/{total_chunks} 部分内容。请对这部分内容进行总结：
- 提取这部分的关键信息和要点
- 保持内容的完整性和准确性
- 输出格式要便于后续合并

### 转录内容
<transcript>
{segment_text}
</transcript>

请对以上内容进行结构化总结，使用 Markdown 格式输出。
"""
        
        messages = [{"role": "user", "content": [{"type": "text", "text": content_text}]}]
        return messages

    def _create_merge_messages(
        self, 
        chunk_summaries: List[str], 
        title: str,
        **kwargs
    ) -> list:
        """创建合并分块结果的消息"""
        video_img_urls = kwargs.get('video_img_urls', [])
        has_images = bool(video_img_urls)
        
        summaries_text = ""
        for i, summary in enumerate(chunk_summaries):
            summaries_text += f"\n\n### 第 {i + 1} 部分\n{summary}"
        
        style_instruction = ""
        if kwargs.get('style'):
            from app.gpt.prompt import STYLE_MAP
            style_instruction = STYLE_MAP.get(kwargs['style'], '')
        
        format_instruction = ""
        if kwargs.get('_format'):
            from app.gpt.prompt import FORMAT_MAP
            for fmt in kwargs['_format']:
                if fmt in FORMAT_MAP:
                    format_instruction += FORMAT_MAP[fmt]
        
        # 如果有图片，添加图片参考提示
        image_instruction = ""
        if has_images:
            image_instruction = """
### 视频画面参考
以下提供了视频的关键帧截图，请结合这些画面内容来优化和完善笔记：
- 识别画面中的重要文字、图表、代码等信息
- 补充文字转录中可能遗漏的视觉信息
- 确保笔记内容与视频画面一致
"""
        
        content_text = f"""## 任务：合并笔记

请将以下分部分的视频笔记整合成一份完整、连贯的笔记。
{image_instruction}

### 视频标题
{title}

### 各部分内容
{summaries_text}

---

### 合并要求
1. **去重**：合并重复或相似的内容
2. **整合**：将相关内容组织到合适的章节中
3. **优化结构**：确保整体逻辑清晰，章节分明
4. **统一风格**：保持全文风格一致

{style_instruction}

{format_instruction}

### 输出格式
- 直接输出最终的 Markdown 笔记
- 不要使用代码块包裹
- 确保格式规范、美观易读

---

现在，请生成合并后的完整笔记：
"""
        
        # 组装 content 数组，支持 text + image 混合
        content = [{"type": "text", "text": content_text}]
        
        if video_img_urls:
            logger.info(f"[AnthropicGPT] 合并阶段添加 {len(video_img_urls)} 张图片")
            for url in video_img_urls:
                # Anthropic 使用 base64 格式
                if url.startswith("data:image"):
                    # 解析 data URL
                    media_type = url.split(";")[0].split(":")[1]
                    base64_data = url.split(",")[1]
                    content.append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": base64_data
                        }
                    })
        
        messages = [{"role": "user", "content": content}]
        return messages

    def _call_api_with_retry(
        self, 
        messages: list, 
        system_prompt: str = None,
        max_retries: int = MAX_RETRIES
    ) -> str:
        """
        带重试机制的 API 调用
        """
        base_url, api_key = self._get_api_config()
        
        if not base_url or not api_key:
            raise ValueError("API 配置缺失")
        
        api_url = self._build_api_url(base_url, "messages")
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01"
        }
        
        payload = {
            "model": self.model,
            "max_tokens": 8192,
            "temperature": self.temperature,
            "messages": messages
        }
        
        # 添加 system prompt
        if system_prompt:
            payload["system"] = system_prompt
        
        last_error = None
        
        for attempt in range(max_retries):
            try:
                logger.info(f"[AnthropicGPT] API 调用尝试 {attempt + 1}/{max_retries}")
                start_time = time.time()
                
                response = requests.post(api_url, headers=headers, json=payload, timeout=300)
                elapsed_time = time.time() - start_time
                
                if response.status_code == 200:
                    if not response.text or not response.text.strip():
                        raise ValueError("API 返回空响应")
                    
                    data = response.json()
                    content = data.get("content", [{}])[0].get("text", "")
                    
                    logger.info(f"[AnthropicGPT] API 调用成功! 耗时: {elapsed_time:.2f}s")
                    
                    if "usage" in data:
                        usage = data["usage"]
                        logger.info(f"[AnthropicGPT] Token 使用: input={usage.get('input_tokens', 'N/A')}, output={usage.get('output_tokens', 'N/A')}")
                    
                    return content.strip()
                else:
                    raise ValueError(f"API 调用失败，状态码: {response.status_code}, 响应: {response.text[:500]}")
                    
            except Exception as e:
                last_error = e
                logger.warning(f"[AnthropicGPT] API 调用失败 (尝试 {attempt + 1}/{max_retries}): {e}")
                
                if attempt < max_retries - 1:
                    wait_time = RETRY_DELAY * (attempt + 1)
                    logger.info(f"[AnthropicGPT] {wait_time}秒后重试...")
                    time.sleep(wait_time)
        
        logger.error(f"[AnthropicGPT] API 调用失败，已达最大重试次数")
        raise last_error

    def list_models(self) -> AnthropicModelList:
        """
        从 API 获取可用的 Anthropic 模型列表
        对于第三方代理服务，调用 OpenAI 兼容的 /v1/models 接口
        """
        try:
            base_url, api_key = self._get_api_config()

            if not base_url or not api_key:
                logger.warning("[AnthropicGPT] 无法获取 API 配置，返回空模型列表")
                return AnthropicModelList(data=[])

            models_url = self._build_api_url(base_url, "models")
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }

            logger.info(f"[AnthropicGPT] 正在从 {models_url} 获取模型列表")
            response = requests.get(models_url, headers=headers, timeout=30)

            if response.status_code == 200:
                data = response.json()
                if "data" in data:
                    # 过滤出 Claude 模型
                    claude_models = [
                        AnthropicModel(id=m.get("id"))
                        for m in data["data"]
                        if "claude" in m.get("id", "").lower()
                    ]
                    logger.info(f"[AnthropicGPT] 成功获取 {len(claude_models)} 个 Claude 模型")
                    return AnthropicModelList(data=claude_models)
                else:
                    logger.warning(f"[AnthropicGPT] API 返回格式异常: {data}")
                    return AnthropicModelList(data=[])
            else:
                logger.error(f"[AnthropicGPT] 获取模型列表失败，状态码: {response.status_code}")
                return AnthropicModelList(data=[])

        except Exception as e:
            logger.error(f"[AnthropicGPT] 获取模型列表异常: {e}")
            return AnthropicModelList(data=[])

    def summarize(self, source: GPTSource) -> str:
        """
        使用 Anthropic API 生成视频笔记摘要
        支持分段处理长视频
        """
        logger.info(f"[AnthropicGPT] ========== 开始 API 调用 ==========")
        logger.info(f"[AnthropicGPT] 模型: {self.model}")
        logger.info(f"[AnthropicGPT] 标题: {source.title}")
        logger.info(f"[AnthropicGPT] 转写片段数: {len(source.segment)}")
        logger.info(f"[AnthropicGPT] 图片数量: {len(source.video_img_urls) if source.video_img_urls else 0}")
        logger.info(f"[AnthropicGPT] 格式选项: {source._format}, 风格: {source.style}")

        self.screenshot = source.screenshot
        self.link = source.link
        source.segment = self.ensure_segments_type(source.segment)

        # 构建完整的转录文本用于判断是否需要分段
        full_segment_text = self._build_segment_text(source.segment)
        
        # 判断是否需要分段处理
        if should_use_chunking(full_segment_text, MAX_SEGMENT_TOKENS):
            logger.info("[AnthropicGPT] 内容较长，启用分段处理策略")
            return self._summarize_with_chunking(source)
        else:
            logger.info("[AnthropicGPT] 内容适中，使用单次处理")
            return self._summarize_single(source)

    def _summarize_single(self, source: GPTSource) -> str:
        """单次调用生成笔记"""
        logger.info("[AnthropicGPT] 构建请求消息...")
        
        has_images = bool(source.video_img_urls)
        
        messages = self.create_messages(
            source.segment,
            title=source.title,
            tags=source.tags,
            video_img_urls=source.video_img_urls,
            _format=source._format,
            style=source.style,
            extras=source.extras
        )

        # 根据是否有图片使用不同的系统提示词
        system_prompt = get_system_prompt(has_images=has_images)
        content = self._call_api_with_retry(messages, system_prompt=system_prompt)
        logger.info(f"[AnthropicGPT] ========== API 调用完成 ==========")
        return content

    def _summarize_with_chunking(self, source: GPTSource) -> str:
        """分段处理长内容"""
        chunks = self._split_segments_into_chunks(source.segment)
        logger.info(f"[AnthropicGPT] 开始分段处理，共 {len(chunks)} 个块")
        
        system_prompt = get_system_prompt()
        chunk_summaries = []
        
        for i, chunk in enumerate(chunks):
            logger.info(f"[AnthropicGPT] 处理第 {i + 1}/{len(chunks)} 块...")
            
            messages = self._create_chunk_messages(
                chunk_index=i,
                total_chunks=len(chunks),
                segments=chunk,
                title=source.title,
                tags=source.tags,
            )
            
            summary = self._call_api_with_retry(messages, system_prompt=system_prompt)
            chunk_summaries.append(summary)
            logger.info(f"[AnthropicGPT] 第 {i + 1} 块处理完成")
        
        # 合并（包含图片以便模型参考视觉内容）
        logger.info("[AnthropicGPT] 开始合并分块结果...")
        if source.video_img_urls:
            logger.info(f"[AnthropicGPT] 合并阶段将使用 {len(source.video_img_urls)} 张图片")
        
        # 合并阶段使用包含图片的系统提示
        has_images = bool(source.video_img_urls)
        merge_system_prompt = get_system_prompt(has_images=has_images)
        
        merge_messages = self._create_merge_messages(
            chunk_summaries=chunk_summaries,
            title=source.title,
            style=source.style,
            _format=source._format,
            extras=source.extras,
            video_img_urls=source.video_img_urls,  # 传入图片供合并阶段参考
        )
        
        final_content = self._call_api_with_retry(merge_messages, system_prompt=merge_system_prompt)
        logger.info(f"[AnthropicGPT] ========== 分段处理完成 ==========")
        return final_content
