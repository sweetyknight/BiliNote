from abc import ABC
import os

from app.decorators.timeit import timeit
from app.models.transcriber_model import TranscriptResult, TranscriptSegment
from app.services.provider import ProviderService
from app.transcriber.base import Transcriber
from app.utils.logger import get_logger
from openai import OpenAI
import ffmpeg
import tempfile
from dotenv import load_dotenv

load_dotenv()

logger = get_logger(__name__)

MAX_SIZE_MB = 18
MAX_SIZE_BYTES = MAX_SIZE_MB * 1024 * 1024

def compress_audio(input_path: str, target_bitrate='64k') -> str:
    """压缩音频文件以满足 Groq API 大小限制"""
    logger.info(f"开始压缩音频文件: {input_path}, 目标比特率: {target_bitrate}")
    output_fd, output_path = tempfile.mkstemp(suffix=".mp3")
    os.close(output_fd)
    try:
        ffmpeg.input(input_path).output(output_path, audio_bitrate=target_bitrate).run(quiet=True, overwrite_output=True)
        compressed_size = os.path.getsize(output_path)
        logger.info(f"音频压缩完成: {output_path}, 压缩后大小: {compressed_size / (1024*1024):.2f} MB")
        return output_path
    except Exception as e:
        logger.error(f"音频压缩失败: {e}", exc_info=True)
        raise

class GroqTranscriber(Transcriber, ABC):

    def __init__(self):
        logger.info("初始化 GroqTranscriber")

    @timeit
    def transcript(self, file_path: str) -> TranscriptResult:
        logger.info(f"开始 Groq 转写: {file_path}")

        # 检查文件大小
        file_size = os.path.getsize(file_path)
        logger.info(f"音频文件大小: {file_size / (1024*1024):.2f} MB")

        if file_size > MAX_SIZE_BYTES:
            logger.warning(f"文件超过 {MAX_SIZE_MB}MB 限制 (当前 {file_size / (1024*1024):.2f}MB)，开始压缩...")
            file_path = compress_audio(file_path)
            logger.info(f"使用压缩后的文件: {file_path}")

        # 获取 Groq 供应商配置
        logger.info("获取 Groq 供应商配置")
        provider = ProviderService.get_provider_by_id('groq')

        if not provider:
            logger.error("Groq 供应商未配置")
            raise Exception("Groq 供应商未配置,请配置以后使用。")

        logger.info(f"Groq API base_url: {provider.get('base_url')}")

        client = OpenAI(
            api_key=provider.get('api_key'),
            base_url=provider.get('base_url')
        )

        model_name = os.getenv('GROQ_TRANSCRIBER_MODEL')
        logger.info(f"使用 Groq 模型: {model_name}")

        try:
            with open(file_path, "rb") as file:
                logger.info("向 Groq API 发送转写请求...")
                transcription = client.audio.transcriptions.create(
                    file=(file_path, file.read()),
                    model=model_name,
                    response_format="verbose_json",
                )
                logger.info(f"Groq API 响应成功，检测到语言: {transcription.language}")
                logger.debug(f"转写文本预览: {transcription.text[:200]}..." if len(transcription.text) > 200 else f"转写文本: {transcription.text}")
        except Exception as e:
            logger.error(f"Groq API 请求失败: {e}", exc_info=True)
            raise

        segments = []
        full_text = ""
        segment_count = 0

        for seg in transcription.segments:
            text = seg.text.strip()
            full_text += text + " "
            segments.append(TranscriptSegment(
                start=seg.start,
                end=seg.end,
                text=text
            ))
            segment_count += 1

        logger.info(f"Groq 转写完成: 共 {segment_count} 个片段, 总文本长度 {len(full_text)} 字符")

        result = TranscriptResult(
            language=transcription.language,
            full_text=full_text.strip(),
            segments=segments,
            raw=transcription.to_dict()
        )
        return result
