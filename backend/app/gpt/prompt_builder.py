"""
Prompt 构建器
负责根据用户选项组装完整的 prompt
"""
from app.gpt.prompt import (
    BASE_PROMPT, 
    SYSTEM_PROMPT,
    SYSTEM_PROMPT_MULTIMODAL,
    STYLE_MAP, 
    FORMAT_MAP,
    VISUAL_TEXT_EXTRACTION,
    VISUAL_TEXT_CODE,
    VISUAL_TEXT_ACADEMIC,
    VISUAL_TEXT_LIGHT,
)
from app.utils.logger import get_logger

logger = get_logger(__name__)

# 格式选项定义
note_formats = [
    {'label': '目录', 'value': 'toc'},
    {'label': '原片跳转', 'value': 'link'},
    {'label': '原片截图', 'value': 'screenshot'},
    {'label': 'AI总结', 'value': 'summary'}
]

# 风格选项定义
note_styles = [
    {'label': '精简', 'value': 'minimal'},
    {'label': '详细', 'value': 'detailed'},
    {'label': '学术', 'value': 'academic'},
    {"label": '教程', "value": 'tutorial'},
    {'label': '小红书', 'value': 'xiaohongshu'},
    {'label': '生活向', 'value': 'life_journal'},
    {'label': '任务导向', 'value': 'task_oriented'},
    {'label': '商业风格', 'value': 'business'},
    {'label': '会议纪要', 'value': 'meeting_minutes'}
]


# 图片 detail 配置
# - "auto": GPT 自动选择，适合需要识别文字/代码的场景（765-1105 tokens/张）
# - "low": 固定低分辨率，适合只需理解大致内容的场景（85 tokens/张）
# - "high": 强制高分辨率，适合需要精细分析的场景

# 需要高分辨率识别细节的风格（教程、学术、详细笔记等）
HIGH_DETAIL_STYLES = {'tutorial', 'detailed', 'academic', 'task_oriented'}

# 只需理解大致内容的风格（生活向、小红书、精简等）
LOW_DETAIL_STYLES = {'life_journal', 'xiaohongshu', 'minimal'}

# 中等需求的风格（商业、会议纪要等），使用 auto
AUTO_DETAIL_STYLES = {'business', 'meeting_minutes'}


def get_image_detail_for_style(style: str, has_screenshot_format: bool = False) -> str:
    """
    根据笔记风格和格式选项，决定图片的 detail 参数
    
    :param style: 笔记风格（如 'tutorial', 'life_journal' 等）
    :param has_screenshot_format: 是否启用了截图功能（需要精确时间点识别）
    :return: "auto" | "low" | "high"
    
    策略说明：
    - 教程/学术/详细风格 → auto（需要识别代码、公式、图表）
    - 生活向/小红书/精简风格 → low（只需理解场景，节省成本）
    - 启用截图功能 → 至少 auto（需要准确识别时间戳）
    """
    # 如果启用了截图功能，需要能识别时间戳，至少用 auto
    if has_screenshot_format:
        if style in LOW_DETAIL_STYLES:
            logger.info(f"[ImageDetail] 风格 '{style}' 原本使用 low，但因启用截图功能，升级为 auto")
            return "auto"
    
    if style in HIGH_DETAIL_STYLES:
        logger.info(f"[ImageDetail] 风格 '{style}' 需要识别细节，使用 auto")
        return "auto"
    elif style in LOW_DETAIL_STYLES:
        logger.info(f"[ImageDetail] 风格 '{style}' 只需大致理解，使用 low 节省成本")
        return "low"
    else:
        # 默认使用 auto
        logger.info(f"[ImageDetail] 风格 '{style}' 使用默认 auto")
        return "auto"


def get_system_prompt(has_images: bool = False) -> str:
    """
    获取系统角色 prompt
    
    :param has_images: 是否包含图片输入（多模态模式）
    :return: 系统 prompt
    """
    if has_images:
        logger.info("[PromptBuilder] 多模态模式：使用增强视觉理解的系统提示词")
        return SYSTEM_PROMPT_MULTIMODAL
    return SYSTEM_PROMPT


# 视觉文字提取级别映射
# 高级提取：代码/教程类
CODE_VISUAL_STYLES = {'tutorial'}
# 学术提取：学术/详细/商业
ACADEMIC_VISUAL_STYLES = {'academic', 'detailed', 'business', 'task_oriented', 'meeting_minutes'}
# 轻量提取：生活向/小红书
LIGHT_VISUAL_STYLES = {'life_journal', 'xiaohongshu', 'minimal'}


def get_visual_extraction_prompt(style: str) -> str:
    """
    根据笔记风格返回对应的视觉文字提取提示词
    
    :param style: 笔记风格
    :return: 视觉提取相关的 prompt 片段
    """
    if style in CODE_VISUAL_STYLES:
        logger.info(f"[PromptBuilder] 风格 '{style}' 使用代码增强视觉提取")
        return VISUAL_TEXT_EXTRACTION + VISUAL_TEXT_CODE
    elif style in ACADEMIC_VISUAL_STYLES:
        logger.info(f"[PromptBuilder] 风格 '{style}' 使用学术增强视觉提取")
        return VISUAL_TEXT_EXTRACTION + VISUAL_TEXT_ACADEMIC
    elif style in LIGHT_VISUAL_STYLES:
        logger.info(f"[PromptBuilder] 风格 '{style}' 使用轻量视觉提取")
        return VISUAL_TEXT_LIGHT
    else:
        # 默认使用通用视觉提取
        logger.info(f"[PromptBuilder] 风格 '{style}' 使用通用视觉提取")
        return VISUAL_TEXT_EXTRACTION


def generate_base_prompt(
    title: str, 
    segment_text: str, 
    tags: list, 
    _format: list = None, 
    style: str = None, 
    extras: str = None,
    has_images: bool = False
) -> str:
    """
    生成完整的用户 prompt
    
    :param title: 视频标题
    :param segment_text: 格式化的转录文本
    :param tags: 视频标签
    :param _format: 格式选项列表，如 ['toc', 'link', 'screenshot', 'summary']
    :param style: 笔记风格
    :param extras: 用户额外的自定义要求
    :param has_images: 是否包含视频帧图片（启用视觉文字提取）
    :return: 完整的 prompt 字符串
    """
    logger.debug(f"[PromptBuilder] 生成 prompt: title={title}, format={_format}, style={style}, has_images={has_images}")
    logger.debug(f"[PromptBuilder] segment_text 长度: {len(segment_text) if segment_text else 0} 字符")

    # 处理标签格式
    tags_str = ', '.join(tags) if tags else '无'
    
    # 生成基础 prompt
    prompt = BASE_PROMPT.format(
        video_title=title or '未知标题',
        segment_text=segment_text,
        tags=tags_str
    )

    # 如果有图片，添加视觉文字提取提示
    if has_images:
        logger.info(f"[PromptBuilder] 检测到图片输入，启用视觉文字提取增强")
        visual_prompt = get_visual_extraction_prompt(style or 'detailed')
        prompt += visual_prompt

    # 添加风格要求
    if style and style in STYLE_MAP:
        logger.debug(f"[PromptBuilder] 添加风格: {style}")
        prompt += STYLE_MAP[style]
    else:
        # 默认使用详细风格
        logger.debug(f"[PromptBuilder] 使用默认风格: detailed")
        prompt += STYLE_MAP.get('detailed', '')

    # 添加格式选项
    if _format:
        logger.debug(f"[PromptBuilder] 添加格式选项: {_format}")
        for fmt in _format:
            if fmt in FORMAT_MAP:
                prompt += FORMAT_MAP[fmt]

    # 添加用户额外要求
    if extras:
        logger.debug(f"[PromptBuilder] 添加额外要求")
        prompt += f"\n### 📌 用户特殊要求\n{extras}\n"

    # 添加最终提醒（根据是否有图片调整）
    if has_images:
        prompt += '''
---

## 🎯 开始生成

你已收到视频的转录内容和关键帧截图。请：
1. **结合音频转录和视觉内容**进行综合分析
2. **提取画面中的文字信息**并融入笔记
3. 直接输出高质量的 Markdown 笔记内容
'''
    else:
        prompt += '''
---

## 🎯 开始生成

现在，请根据以上要求，直接输出高质量的 Markdown 笔记内容。
'''

    logger.info(f"[PromptBuilder] Prompt 生成完成，总长度: {len(prompt)} 字符")
    return prompt


def estimate_tokens(text: str) -> int:
    """
    估算文本的 token 数量（粗略估计）
    中文约 1.5-2 个字符一个 token，英文约 4 个字符一个 token
    """
    # 简单估算：假设平均 2 个字符一个 token
    return len(text) // 2


def should_use_chunking(segment_text: str, max_tokens: int = 6000) -> bool:
    """
    判断是否需要分段处理
    
    :param segment_text: 转录文本
    :param max_tokens: 单次处理的最大 token 数
    :return: 是否需要分段
    """
    estimated = estimate_tokens(segment_text)
    logger.debug(f"[PromptBuilder] 估算 token 数: {estimated}, 阈值: {max_tokens}")
    return estimated > max_tokens
