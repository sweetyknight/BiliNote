from app.downloaders.bilibili_downloader import BilibiliDownloader
from app.downloaders.douyin_downloader import DouyinDownloader
from app.downloaders.kuaishou_downloader import KuaiShouDownloader
from app.downloaders.local_downloader import LocalDownloader
from app.downloaders.youtube_downloader import YoutubeDownloader

SUPPORT_PLATFORM_MAP = {
    'youtube':YoutubeDownloader(),
    'bilibili':BilibiliDownloader(),
    'tiktok':DouyinDownloader(),
    'kuaishou':KuaiShouDownloader(),
    'douyin':DouyinDownloader(),
    'local':LocalDownloader()
}

# 语音转写模型关键字列表 - 这些模型不应出现在笔记生成的模型选择中
TRANSCRIBER_MODEL_KEYWORDS = [
    'whisper',           # Groq/OpenAI whisper 系列
    'distil-whisper',    # Distil-Whisper 系列
]

def is_transcriber_model(model_name: str) -> bool:
    """
    判断模型是否为语音转写模型
    
    Args:
        model_name: 模型名称
        
    Returns:
        True 如果是转写模型，False 如果是 LLM 模型
    """
    model_name_lower = model_name.lower()
    return any(keyword in model_name_lower for keyword in TRANSCRIBER_MODEL_KEYWORDS)