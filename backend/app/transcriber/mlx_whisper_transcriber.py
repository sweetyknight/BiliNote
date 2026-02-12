import mlx_whisper
from pathlib import Path
import os
import platform
from huggingface_hub import snapshot_download

from app.decorators.timeit import timeit
from app.models.transcriber_model import TranscriptSegment, TranscriptResult
from app.transcriber.base import Transcriber
from app.utils.logger import get_logger
from app.utils.path_helper import get_model_dir
from events import transcription_finished

logger = get_logger(__name__)

class MLXWhisperTranscriber(Transcriber):
    def __init__(
            self,
            model_size: str = "base"
    ):
        # 检查平台
        if platform.system() != "Darwin":
            raise RuntimeError("MLX Whisper 仅支持 Apple 平台")
            
        # 检查环境变量
        if os.environ.get("TRANSCRIBER_TYPE") != "mlx-whisper":
            raise RuntimeError("必须设置环境变量 TRANSCRIBER_TYPE=mlx-whisper 才能使用 MLX Whisper")
            
        self.model_size = model_size
        self.model_name = f"mlx-community/whisper-{model_size}"
        self.model_path = None
        
        # 设置模型路径
        model_dir = get_model_dir("mlx-whisper")
        self.model_path = os.path.join(model_dir, self.model_name)
        # 检查并下载模型
        if not Path(self.model_path).exists():
            logger.info(f"模型 {self.model_name} 不存在，开始下载...")
            snapshot_download(
                self.model_name,
                local_dir=self.model_path,
                local_dir_use_symlinks=False,
            )
            logger.info("模型下载完成")
        
        logger.info(f"初始化 MLX Whisper 转录器，模型：{self.model_name}")

    @timeit
    def transcript(self, file_path: str) -> TranscriptResult:
        logger.info(f"[MLX Whisper] 开始转写音频文件: {file_path}")
        try:
            # 检查文件是否存在
            if not Path(file_path).exists():
                logger.error(f"[MLX Whisper] 音频文件不存在: {file_path}")
                raise FileNotFoundError(f"音频文件不存在: {file_path}")

            file_size = Path(file_path).stat().st_size
            logger.info(f"[MLX Whisper] 音频文件大小: {file_size / (1024*1024):.2f} MB")

            # 使用 MLX Whisper 进行转录
            logger.info(f"[MLX Whisper] 调用 MLX Whisper 模型: {self.model_name}")
            result = mlx_whisper.transcribe(
                file_path,
                path_or_hf_repo=f"{self.model_name}"
            )
            logger.info(f"[MLX Whisper] 转写完成，检测到语言: {result.get('language', 'unknown')}")

            # 转换为标准格式
            segments = []
            full_text = ""

            for segment in result["segments"]:
                text = segment["text"].strip()
                full_text += text + " "
                segments.append(TranscriptSegment(
                    start=segment["start"],
                    end=segment["end"],
                    text=text
                ))

            logger.info(f"[MLX Whisper] 转写结果: 共 {len(segments)} 个片段, 总文本长度 {len(full_text)} 字符")

            transcript_result = TranscriptResult(
                language=result.get("language", "unknown"),
                full_text=full_text.strip(),
                segments=segments,
                raw=result
            )

            return transcript_result

        except Exception as e:
            logger.error(f"[MLX Whisper] 转写失败：{e}", exc_info=True)
            raise e

    def on_finish(self, video_path: str, result: TranscriptResult) -> None:
        logger.info("MLX Whisper 转写完成")
        transcription_finished.send({
            "file_path": video_path,
        }) 