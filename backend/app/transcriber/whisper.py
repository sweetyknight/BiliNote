import faulthandler
faulthandler.enable()  # 捕获 C 级别崩溃（如 segfault），输出到 stderr

from faster_whisper import WhisperModel

from app.decorators.timeit import timeit
from app.models.transcriber_model import TranscriptSegment, TranscriptResult
from app.transcriber.base import Transcriber
from app.utils.env_checker import is_cuda_available, is_torch_installed
from app.utils.logger import get_logger
from app.utils.path_helper import get_model_dir

from events import transcription_finished
from pathlib import Path
import os
import subprocess
from tqdm import tqdm
from modelscope import snapshot_download

# 尝试导入批量推理模块（faster-whisper 0.10+）
try:
    from faster_whisper import BatchedInferencePipeline
    BATCHED_AVAILABLE = True
except ImportError:
    BATCHED_AVAILABLE = False

# ============== 转写安全限制配置 ==============
# 可通过环境变量覆盖
MAX_FILE_SIZE_MB = int(os.environ.get("WHISPER_MAX_FILE_SIZE_MB", 2048))  # 最大文件大小 2GB
MAX_DURATION_HOURS = float(os.environ.get("WHISPER_MAX_DURATION_HOURS", 4))  # 最大时长 4 小时
MIN_FREE_MEMORY_GB = float(os.environ.get("WHISPER_MIN_FREE_MEMORY_GB", 2))  # 最小剩余内存 2GB


'''
 Size of the model to use (tiny, tiny.en, base, base.en, small, small.en, distil-small.en, medium, medium.en, distil-medium.en, large-v1, large-v2, large-v3, large, distil-large-v2, distil-large-v3, large-v3-turbo, or turbo
'''
logger=get_logger(__name__)


def get_audio_duration(file_path: str) -> float:
    """
    使用 ffprobe 获取音频/视频文件时长（秒）
    
    :param file_path: 文件路径
    :return: 时长（秒），获取失败返回 -1
    """
    try:
        result = subprocess.run(
            [
                'ffprobe', '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                file_path
            ],
            capture_output=True, text=True, timeout=30
        )
        return float(result.stdout.strip())
    except Exception as e:
        logger.warning(f"获取音频时长失败: {e}")
        return -1


def get_gpu_memory_info() -> dict:
    """
    使用 nvidia-smi 获取实际 GPU 显存信息。

    不使用 torch.cuda.* API，因为：
    1. PyTorch 只能报告自己管理的显存，无法感知 CTranslate2 的显存占用
    2. 在不支持当前 GPU 架构的 PyTorch 版本中，torch.cuda.* 调用可能导致进程崩溃

    :return: {"total_mb": 总显存, "free_mb": 可用显存, "used_mb": 已用显存, "available": bool}
    """
    try:
        result = subprocess.run(
            ['nvidia-smi', '--query-gpu=memory.total,memory.free,memory.used',
             '--format=csv,noheader,nounits'],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0 and result.stdout.strip():
            # 取第一块 GPU 的信息
            line = result.stdout.strip().split('\n')[0]
            parts = [float(x.strip()) for x in line.split(',')]
            total, free, used = parts[0], parts[1], parts[2]
            return {
                "total_mb": total,
                "free_mb": free,
                "used_mb": used,
                "available": True
            }
    except FileNotFoundError:
        logger.debug("nvidia-smi 未找到，跳过 GPU 显存检查")
    except Exception as e:
        logger.debug(f"获取 GPU 显存信息失败: {e}")
    return {"total_mb": 0, "free_mb": 0, "used_mb": 0, "available": False}


def get_system_memory_info() -> dict:
    """
    获取系统内存信息
    
    :return: {"total_gb": 总内存, "free_gb": 可用内存, "percent": 使用百分比}
    """
    try:
        import psutil
        mem = psutil.virtual_memory()
        return {
            "total_gb": mem.total / (1024**3),
            "free_gb": mem.available / (1024**3),
            "percent": mem.percent
        }
    except ImportError:
        logger.debug("psutil 未安装，跳过内存检查")
        return {"total_gb": 0, "free_gb": 999, "percent": 0}  # 默认不限制
    except Exception as e:
        logger.warning(f"获取系统内存信息失败: {e}")
        return {"total_gb": 0, "free_gb": 999, "percent": 0}


def auto_adjust_batch_size(gpu_info: dict, model_size: str) -> int:
    """
    根据 GPU 显存自动调整 batch_size
    
    :param gpu_info: GPU 显存信息
    :param model_size: 模型大小
    :return: 推荐的 batch_size
    """
    if not gpu_info.get("available"):
        return 1  # CPU 模式不使用批量推理
    
    free_mb = gpu_info.get("free_mb", 0)
    
    # 不同模型的显存需求估算（每个 batch 的额外显存 MB）
    model_memory_per_batch = {
        "tiny": 50,
        "base": 80,
        "small": 120,
        "medium": 200,
        "large-v1": 350,
        "large-v2": 350,
        "large-v3": 400,
        "large-v3-turbo": 300,
    }
    
    mem_per_batch = model_memory_per_batch.get(model_size, 200)
    # 保留 2GB 显存余量
    available_for_batch = max(0, free_mb - 2048)
    recommended_batch = max(1, int(available_for_batch / mem_per_batch))

    # 限制最大 batch_size
    recommended_batch = min(recommended_batch, 32)

    logger.info(f"🎯 自动调整 batch_size: 可用显存={free_mb:.0f}MB, 模型={model_size}, 推荐batch_size={recommended_batch}")
    return recommended_batch

MODEL_MAP={
    "tiny": "pengzhendong/faster-whisper-tiny",
    'base':'pengzhendong/faster-whisper-base',
    'small':'pengzhendong/faster-whisper-small',
    'medium':'pengzhendong/faster-whisper-medium',
    'large-v1':'pengzhendong/faster-whisper-large-v1',
    'large-v2':'pengzhendong/faster-whisper-large-v2',
    'large-v3':'pengzhendong/faster-whisper-large-v3',
    'large-v3-turbo':'pengzhendong/faster-whisper-large-v3-turbo',
}

class WhisperTranscriber(Transcriber):
    # TODO:修改为可配置
    def __init__(
            self,
            model_size: str = "base",
            device: str = 'cpu',
            compute_type: str = None,
            cpu_threads: int = 4,
            use_batched: bool = True,  # 是否使用批量推理
            batch_size: int = 0,       # 批量大小，0 = 自动根据显存调整
            auto_batch_size: bool = True,  # 是否自动调整 batch_size
    ):
        logger.info(f"初始化 WhisperTranscriber: model_size={model_size}, device={device}, compute_type={compute_type}")
        self.model_size = model_size

        if device == 'cpu' or device is None:
            self.device = 'cpu'
            logger.info("使用 CPU 进行计算")
        else:
            self.device = "cuda" if self.is_cuda() else "cpu"
            if device == 'cuda' and self.device == 'cpu':
                logger.warning('请求使用 CUDA 但不可用，回退到 CPU 进行计算')

        self.compute_type = compute_type or ("float16" if self.device == "cuda" else "int8")
        logger.info(f"计算类型: {self.compute_type}")

        if use_batched and not BATCHED_AVAILABLE:
            logger.warning("批量推理不可用，请升级 faster-whisper >= 0.10.0")

        model_dir = get_model_dir("whisper")
        model_path = os.path.join(model_dir, f"whisper-{model_size}")
        logger.debug(f"模型目录: {model_dir}, 模型路径: {model_path}")
        if not Path(model_path).exists():
            logger.info(f"模型 whisper-{model_size} 不存在，开始下载...")
            repo_id = MODEL_MAP[model_size]
            model_path = snapshot_download(
                repo_id,

                local_dir=model_path,
            )
            logger.info("模型下载完成")

        logger.info(f"加载 Whisper 模型: {model_path}")
        self.model = WhisperModel(
            model_size_or_path=model_path,
            device=self.device,
            compute_type=self.compute_type,
            download_root=model_dir,
            cpu_threads=cpu_threads,
            num_workers=2 if self.device == "cuda" else 1,  # 多线程加载数据
        )

        # ====== 批量推理配置 ======
        # 重要：batch_size 必须在模型加载之后计算，因为模型会占用 GPU 显存
        # 之前的代码在模型加载前计算 batch_size，导致高估可用显存，引发 OOM 崩溃
        self.use_batched = use_batched and BATCHED_AVAILABLE and self.device == "cuda"

        # 支持通过环境变量手动指定 batch_size（用于调试或特殊配置）
        env_batch_size = os.environ.get("WHISPER_BATCH_SIZE")
        if env_batch_size:
            self.batch_size = int(env_batch_size)
            logger.info(f"使用环境变量指定的 batch_size: {self.batch_size}")
        elif auto_batch_size and self.device == "cuda":
            # 在模型加载后获取 GPU 显存信息（使用 nvidia-smi，获取真实的可用显存）
            gpu_info = get_gpu_memory_info()
            self.batch_size = auto_adjust_batch_size(gpu_info, model_size)
        else:
            self.batch_size = batch_size if batch_size > 0 else 16  # 默认值

        # 创建批量推理管道
        self.batched_model = None
        if self.use_batched:
            try:
                self.batched_model = BatchedInferencePipeline(model=self.model)
                logger.info(f"✅ 批量推理管道创建成功, batch_size={self.batch_size}")
            except Exception as e:
                logger.warning(f"创建批量推理管道失败: {e}, 将使用标准推理")
                self.use_batched = False

        logger.info(f"WhisperTranscriber 初始化完成: device={self.device}, compute_type={self.compute_type}, batched={self.use_batched}, batch_size={self.batch_size}")
    @staticmethod
    def is_torch_installed() -> bool:
        try:
            import torch
            return True
        except ImportError:
            return False

    @staticmethod
    def is_cuda() -> bool:
        try:
            if is_cuda_available():
                logger.info("CUDA 可用，使用 GPU 加速")
                return True
            elif is_torch_installed():
                logger.info("已安装 torch，但 CUDA 不可用，使用 CPU")
                return False
            else:
                logger.warning("未安装 torch，请先安装")
                return False

        except ImportError:
            logger.warning("检测 CUDA 时发生 ImportError")
            return False

    def _check_safety_limits(self, file_path: str) -> dict:
        """
        检查文件是否超出安全限制
        
        :param file_path: 文件路径
        :return: {"ok": bool, "warnings": list, "errors": list, "duration": float, "file_size_mb": float}
        """
        result = {"ok": True, "warnings": [], "errors": [], "duration": -1, "file_size_mb": 0}
        
        # 1. 检查文件大小
        file_size_mb = Path(file_path).stat().st_size / (1024 * 1024)
        result["file_size_mb"] = file_size_mb
        
        if file_size_mb > MAX_FILE_SIZE_MB:
            result["ok"] = False
            result["errors"].append(
                f"文件过大: {file_size_mb:.1f}MB，超出限制 {MAX_FILE_SIZE_MB}MB。"
                f"请压缩文件或设置环境变量 WHISPER_MAX_FILE_SIZE_MB 调整限制。"
            )
        elif file_size_mb > MAX_FILE_SIZE_MB * 0.8:
            result["warnings"].append(f"文件较大 ({file_size_mb:.1f}MB)，转写可能需要较长时间")
        
        # 2. 检查音频时长
        duration = get_audio_duration(file_path)
        result["duration"] = duration
        
        if duration > 0:
            duration_hours = duration / 3600
            max_duration_seconds = MAX_DURATION_HOURS * 3600
            
            if duration > max_duration_seconds:
                result["ok"] = False
                result["errors"].append(
                    f"音频过长: {duration_hours:.1f}小时，超出限制 {MAX_DURATION_HOURS}小时。"
                    f"请裁剪音频或设置环境变量 WHISPER_MAX_DURATION_HOURS 调整限制。"
                )
            elif duration_hours > MAX_DURATION_HOURS * 0.8:
                result["warnings"].append(f"音频较长 ({duration_hours:.1f}小时)，转写可能需要较长时间")
        
        # 3. 检查系统内存
        mem_info = get_system_memory_info()
        if mem_info["free_gb"] < MIN_FREE_MEMORY_GB:
            result["warnings"].append(
                f"系统内存不足: 可用 {mem_info['free_gb']:.1f}GB，"
                f"建议至少 {MIN_FREE_MEMORY_GB}GB。转写可能导致系统卡顿。"
            )
        
        # 4. 检查 GPU 显存（如果使用 CUDA）
        if self.device == "cuda":
            gpu_info = get_gpu_memory_info()
            if gpu_info["available"] and gpu_info["free_mb"] < 1024:
                result["warnings"].append(
                    f"GPU 显存不足: 可用 {gpu_info['free_mb']:.0f}MB，"
                    "可能导致 OOM 错误，建议关闭其他 GPU 程序。"
                )
        
        return result

    @timeit
    def transcript(self, file_path: str) -> TranscriptResult:
        logger.info(f"开始转写音频文件: {file_path}")
        try:
            # 检查文件是否存在
            if not Path(file_path).exists():
                logger.error(f"音频文件不存在: {file_path}")
                raise FileNotFoundError(f"音频文件不存在: {file_path}")

            # ====== 安全限制检查 ======
            safety_check = self._check_safety_limits(file_path)
            
            # 输出警告
            for warning in safety_check["warnings"]:
                logger.warning(f"⚠️ {warning}")
            
            # 如果有错误，拒绝转写
            if not safety_check["ok"]:
                for error in safety_check["errors"]:
                    logger.error(f"❌ {error}")
                raise ValueError(
                    "转写安全检查失败:\n" + "\n".join(safety_check["errors"])
                )
            
            file_size_mb = safety_check["file_size_mb"]
            duration = safety_check["duration"]
            
            logger.info(f"📊 文件信息: 大小={file_size_mb:.2f}MB, 时长={duration/60:.1f}分钟" if duration > 0 else f"📊 文件大小: {file_size_mb:.2f}MB")
            logger.info(f"调用 Whisper 模型进行转写 (device={self.device}, compute_type={self.compute_type}, batched={self.use_batched}, batch_size={self.batch_size})")
            
            import time as _time
            _transcribe_start = _time.time()
            
            # 转写优化参数
            transcribe_options = {
                "beam_size": 5,                      # 保持默认值，确保转写精度
                "vad_filter": True,                  # 启用VAD过滤静音，显著提速
                "vad_parameters": {
                    "min_silence_duration_ms": 500,  # 静音段最小时长
                    "speech_pad_ms": 200,            # 语音边界填充
                },
                "word_timestamps": False,            # 不需要词级时间戳
                "condition_on_previous_text": True,  # 保持上下文连贯性
            }
            
            # 根据是否使用批量推理选择不同的调用方式
            if self.use_batched and self.batched_model is not None:
                logger.info(f"🚀 使用批量推理模式, batch_size={self.batch_size}")
                segments_generator, info = self.batched_model.transcribe(
                    file_path,
                    batch_size=self.batch_size,
                    **transcribe_options
                )
            else:
                logger.info("使用标准推理模式")
                segments_generator, info = self.model.transcribe(
                    file_path,
                    **transcribe_options
                )
            
            # 关键修复：faster-whisper 返回惰性生成器，实际转写在迭代时才发生
            # 将生成器转换为列表，强制立即完成所有转写
            logger.info(f"检测到语言: {info.language}, 语言概率: {info.language_probability:.2f}")
            logger.info("开始收集转写结果（这可能需要几分钟，取决于音频长度）...")
            
            segments_raw = list(segments_generator)  # 强制完成所有转写
            
            _transcribe_end = _time.time()
            
            logger.info(f"转写完成，共 {len(segments_raw)} 个片段，耗时 {_transcribe_end - _transcribe_start:.2f} 秒")

            segments = []
            full_text = ""
            segment_count = 0

            for seg in segments_raw:
                text = seg.text.strip()
                full_text += text + " "
                segments.append(TranscriptSegment(
                    start=seg.start,
                    end=seg.end,
                    text=text
                ))
                segment_count += 1

            logger.info(f"转写结果: 共 {segment_count} 个片段, 总文本长度 {len(full_text)} 字符")

            result = TranscriptResult(
                language=info.language,
                full_text=full_text.strip(),
                segments=segments,
                raw=info
            )

            logger.info(f"Whisper 转写成功完成: {file_path}")
            return result
        except Exception as e:
            logger.error(f"转写失败：{e}", exc_info=True)
            raise


    def on_finish(self,video_path:str,result: TranscriptResult)->None:
        logger.info(f"Whisper 转写完成回调: {video_path}")
        transcription_finished.send({
            "file_path": video_path,
        })

