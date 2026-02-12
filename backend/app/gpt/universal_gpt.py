"""
通用 GPT 实现
使用 OpenAI 兼容 API 进行视频笔记生成
支持所有 OpenAI 兼容的 API 服务（如 OpenAI、DeepSeek、Qwen 等）
"""
import time
from typing import List, Optional
from datetime import timedelta

from app.gpt.base import GPT
from app.gpt.prompt_builder import (
    generate_base_prompt, 
    get_image_detail_for_style, 
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
MAX_RETRIES = 5  # API 调用最大重试次数
RETRY_DELAY = 3  # 重试基础间隔（秒）


class UniversalGPT(GPT):
    """
    通用 GPT 实现类
    使用 OpenAI 兼容 API 调用各种大语言模型
    """

    def __init__(self, client, model: str, temperature: float = 0.7):
        """
        初始化 UniversalGPT
        :param client: OpenAI 兼容的客户端
        :param model: 模型名称，如 gpt-4o, deepseek-chat 等
        :param temperature: 温度参数，默认 0.7（平衡稳定性和表达多样性）
        """
        logger.info(f"[UniversalGPT] 初始化: model={model}, temperature={temperature}")
        self.client = client
        self.model = model
        self.temperature = temperature
        self.screenshot = False
        self.link = False
        logger.debug(f"[UniversalGPT] 客户端类型: {type(client).__name__}")

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
        将转录片段分割成多个块，每个块不超过指定的 token 数
        
        :param segments: 完整的转录片段列表
        :param max_tokens: 每个块的最大 token 数
        :return: 分割后的片段块列表
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
        
        logger.info(f"[UniversalGPT] 将 {len(segments)} 个片段分割成 {len(chunks)} 个块")
        return chunks

    def create_messages(self, segments: List[TranscriptSegment], **kwargs) -> list:
        """
        创建 OpenAI 格式的消息，包含 system prompt
        :param segments: 转写片段列表
        :param kwargs: 其他参数
        :return: 消息列表
        """
        logger.debug(f"[UniversalGPT] 构建消息: segments数量={len(segments)}, title={kwargs.get('title')}")

        video_img_urls = kwargs.get('video_img_urls', [])
        has_images = bool(video_img_urls)
        
        # 获取 system prompt（根据是否有图片使用不同版本）
        system_prompt = get_system_prompt(has_images=has_images)
        
        content_text = generate_base_prompt(
            title=kwargs.get('title'),
            segment_text=self._build_segment_text(segments),
            tags=kwargs.get('tags'),
            _format=kwargs.get('_format'),
            style=kwargs.get('style'),
            extras=kwargs.get('extras'),
            has_images=has_images,  # 传递图片标志以启用视觉文字提取
        )

        logger.debug(f"[UniversalGPT] 生成的 prompt 长度: {len(content_text)} 字符")
        if has_images:
            logger.info(f"[UniversalGPT] 🔤 已启用视觉文字提取增强模式")

        # 组装 content 数组，支持 text + image_url 混合
        content = [{"type": "text", "text": content_text}]

        if video_img_urls:
            # 根据笔记风格动态选择图片分辨率
            style = kwargs.get('style', '')
            formats = kwargs.get('_format', []) or []
            has_screenshot = 'screenshot' in formats
            
            image_detail = get_image_detail_for_style(style, has_screenshot)
            logger.info(f"[UniversalGPT] 添加 {len(video_img_urls)} 张图片，detail={image_detail} (style={style}, screenshot={has_screenshot})")
            
            for url in video_img_urls:
                content.append({
                    "type": "image_url",
                    "image_url": {
                        "url": url,
                        "detail": image_detail
                    }
                })

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": content}
        ]
        logger.debug(f"[UniversalGPT] 消息构建完成: system_prompt 长度={len(system_prompt)}, content块数量={len(content)}")
        return messages

    def _create_chunk_messages(
        self, 
        chunk_index: int, 
        total_chunks: int,
        segments: List[TranscriptSegment], 
        **kwargs
    ) -> list:
        """
        创建分块处理的消息
        
        :param chunk_index: 当前块索引
        :param total_chunks: 总块数
        :param segments: 当前块的转录片段
        :param kwargs: 其他参数
        :return: 消息列表
        """
        system_prompt = get_system_prompt()
        
        # 构建分块处理的特殊提示
        chunk_instruction = f"""
## 分段处理说明

这是视频的第 {chunk_index + 1}/{total_chunks} 部分内容。请对这部分内容进行总结：
- 提取这部分的关键信息和要点
- 保持内容的完整性和准确性
- 输出格式要便于后续合并
"""
        
        segment_text = self._build_segment_text(segments)
        
        content_text = f"""## 视频信息
- **标题**：{kwargs.get('title', '未知标题')}
- **当前部分**：第 {chunk_index + 1}/{total_chunks} 部分

{chunk_instruction}

### 转录内容
<transcript>
{segment_text}
</transcript>

请对以上内容进行结构化总结，使用 Markdown 格式输出。
"""
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": content_text}
        ]
        return messages

    def _create_merge_messages(
        self, 
        chunk_summaries: List[str], 
        title: str,
        **kwargs
    ) -> list:
        """
        创建合并分块结果的消息
        
        :param chunk_summaries: 各分块的总结结果
        :param title: 视频标题
        :param kwargs: 其他参数（style, _format, video_img_urls 等）
        :return: 消息列表
        """
        video_img_urls = kwargs.get('video_img_urls', [])
        has_images = bool(video_img_urls)
        
        system_prompt = get_system_prompt(has_images=has_images)
        
        # 将各部分总结合并
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
        
        # 组装 content 数组，支持 text + image_url 混合
        content = [{"type": "text", "text": content_text}]
        
        if video_img_urls:
            # 根据笔记风格动态选择图片分辨率
            style = kwargs.get('style', '')
            formats = kwargs.get('_format', []) or []
            has_screenshot = 'screenshot' in formats
            
            image_detail = get_image_detail_for_style(style, has_screenshot)
            logger.info(f"[UniversalGPT] 合并阶段添加 {len(video_img_urls)} 张图片，detail={image_detail}")
            
            for url in video_img_urls:
                content.append({
                    "type": "image_url",
                    "image_url": {
                        "url": url,
                        "detail": image_detail
                    }
                })
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": content}
        ]
        return messages

    def _call_api_with_retry(self, messages: list, max_retries: int = MAX_RETRIES) -> str:
        """
        带重试机制的 API 调用，对 503 等服务端错误使用指数退避策略

        :param messages: 消息列表
        :param max_retries: 最大重试次数
        :return: API 返回的内容
        """
        import random
        last_error = None

        for attempt in range(max_retries):
            try:
                logger.info(f"[UniversalGPT] API 调用尝试 {attempt + 1}/{max_retries}")
                start_time = time.time()

                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=self.temperature
                )

                elapsed_time = time.time() - start_time
                content = response.choices[0].message.content.strip()

                logger.info(f"[UniversalGPT] API 调用成功! 耗时: {elapsed_time:.2f}s")

                if hasattr(response, 'usage') and response.usage:
                    logger.info(f"[UniversalGPT] Token 使用: prompt={response.usage.prompt_tokens}, completion={response.usage.completion_tokens}, total={response.usage.total_tokens}")

                return content

            except Exception as e:
                last_error = e
                logger.warning(f"[UniversalGPT] API 调用失败 (尝试 {attempt + 1}/{max_retries}): {e}")

                # 检查是否为不可重试的永久性错误（如模型不存在、认证失败等）
                error_msg = str(e).lower()
                status_code = getattr(e, 'status_code', 0)
                is_permanent_error = (
                    'model_not_found' in error_msg or
                    'invalid_api_key' in error_msg or
                    status_code in (401, 403, 404)
                )
                if is_permanent_error:
                    logger.error(f"[UniversalGPT] 检测到永久性错误，不再重试: {e}")
                    raise e

                if attempt < max_retries - 1:
                    # 对 503/502/429 等服务端错误使用指数退避 + 随机抖动
                    if status_code in (502, 503, 429):
                        wait_time = min(RETRY_DELAY * (2 ** attempt) + random.uniform(0, 2), 30)
                        logger.info(f"[UniversalGPT] 服务端错误({status_code})，{wait_time:.1f}秒后重试...")
                    else:
                        wait_time = RETRY_DELAY * (attempt + 1)
                        logger.info(f"[UniversalGPT] {wait_time}秒后重试...")
                    time.sleep(wait_time)

        logger.error(f"[UniversalGPT] API 调用失败，已达最大重试次数({max_retries})")
        raise last_error

    def list_models(self):
        """
        获取可用模型列表
        :return: 模型列表
        """
        logger.info("[UniversalGPT] 获取模型列表")
        try:
            models = self.client.models.list()
            logger.info(f"[UniversalGPT] 成功获取模型列表")
            return models
        except Exception as e:
            logger.error(f"[UniversalGPT] 获取模型列表失败: {e}", exc_info=True)
            raise

    def summarize(self, source: GPTSource) -> str:
        """
        使用 OpenAI 兼容 API 生成视频笔记摘要
        支持分段处理长视频
        
        :param source: GPT 输入源
        :return: 生成的笔记内容
        """
        logger.info(f"[UniversalGPT] ========== 开始 API 调用 ==========")
        logger.info(f"[UniversalGPT] 模型: {self.model}")
        logger.info(f"[UniversalGPT] 标题: {source.title}")
        logger.info(f"[UniversalGPT] 转写片段数: {len(source.segment)}")
        logger.info(f"[UniversalGPT] 图片数量: {len(source.video_img_urls) if source.video_img_urls else 0}")
        logger.info(f"[UniversalGPT] 格式选项: {source._format}, 风格: {source.style}")

        self.screenshot = source.screenshot
        self.link = source.link
        source.segment = self.ensure_segments_type(source.segment)

        # 构建完整的转录文本用于判断是否需要分段
        full_segment_text = self._build_segment_text(source.segment)
        
        # 判断是否需要分段处理
        if should_use_chunking(full_segment_text, MAX_SEGMENT_TOKENS):
            logger.info("[UniversalGPT] 内容较长，启用分段处理策略")
            return self._summarize_with_chunking(source)
        else:
            logger.info("[UniversalGPT] 内容适中，使用单次处理")
            return self._summarize_single(source)

    def _summarize_single(self, source: GPTSource) -> str:
        """
        单次调用生成笔记（适用于较短内容）
        """
        logger.info("[UniversalGPT] 构建请求消息...")
        messages = self.create_messages(
            source.segment,
            title=source.title,
            tags=source.tags,
            video_img_urls=source.video_img_urls,
            _format=source._format,
            style=source.style,
            extras=source.extras
        )

        content = self._call_api_with_retry(messages)
        logger.info(f"[UniversalGPT] ========== API 调用完成 ==========")
        return content

    def _summarize_with_chunking(self, source: GPTSource) -> str:
        """
        分段处理长内容：先分段总结，再合并
        """
        # 分割片段
        chunks = self._split_segments_into_chunks(source.segment)
        logger.info(f"[UniversalGPT] 开始分段处理，共 {len(chunks)} 个块")
        
        # 逐块处理
        chunk_summaries = []
        for i, chunk in enumerate(chunks):
            logger.info(f"[UniversalGPT] 处理第 {i + 1}/{len(chunks)} 块...")
            
            messages = self._create_chunk_messages(
                chunk_index=i,
                total_chunks=len(chunks),
                segments=chunk,
                title=source.title,
                tags=source.tags,
            )
            
            summary = self._call_api_with_retry(messages)
            chunk_summaries.append(summary)
            logger.info(f"[UniversalGPT] 第 {i + 1} 块处理完成，摘要长度: {len(summary)}")
        
        # 合并所有块的摘要（包含图片以便模型参考视觉内容）
        logger.info("[UniversalGPT] 开始合并分块结果...")
        if source.video_img_urls:
            logger.info(f"[UniversalGPT] 合并阶段将使用 {len(source.video_img_urls)} 张图片")
        
        merge_messages = self._create_merge_messages(
            chunk_summaries=chunk_summaries,
            title=source.title,
            style=source.style,
            _format=source._format,
            extras=source.extras,
            video_img_urls=source.video_img_urls,  # 传入图片供合并阶段参考
        )
        
        final_content = self._call_api_with_retry(merge_messages)
        logger.info(f"[UniversalGPT] ========== 分段处理完成 ==========")
        return final_content
