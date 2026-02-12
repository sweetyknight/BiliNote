import json
import logging
import os
import re
from dataclasses import asdict
from pathlib import Path
from typing import List, Optional, Tuple, Union, Any

from fastapi import HTTPException
from pydantic import HttpUrl
from dotenv import load_dotenv

from app.downloaders.base import Downloader
from app.downloaders.bilibili_downloader import BilibiliDownloader
from app.downloaders.douyin_downloader import DouyinDownloader
from app.downloaders.local_downloader import LocalDownloader
from app.downloaders.youtube_downloader import YoutubeDownloader
from app.db.video_task_dao import delete_task_by_video, insert_video_task
from app.enmus.exception import NoteErrorEnum, ProviderErrorEnum
from app.enmus.task_status_enums import TaskStatus
from app.enmus.note_enums import DownloadQuality
from app.exceptions.note import NoteError
from app.exceptions.provider import ProviderError
from app.gpt.base import GPT
from app.gpt.gpt_factory import GPTFactory
from app.models.audio_model import AudioDownloadResult
from app.models.gpt_model import GPTSource
from app.models.model_config import ModelConfig
from app.models.notes_model import AudioDownloadResult, NoteResult
from app.models.transcriber_model import TranscriptResult, TranscriptSegment
from app.services.constant import SUPPORT_PLATFORM_MAP
from app.services.provider import ProviderService
from app.transcriber.base import Transcriber
from app.transcriber.transcriber_provider import get_transcriber, _transcribers
from app.utils.note_helper import replace_content_markers
from app.utils.status_code import StatusCode
from app.utils.video_helper import generate_screenshot
from app.utils.video_reader import VideoReader

# ------------------ 环境变量与全局配置 ------------------

# 从 .env 文件中加载环境变量
load_dotenv()

# 后端 API 地址与端口（若有需要可以在代码其他部分使用 BACKEND_BASE_URL）
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost")
BACKEND_PORT = os.getenv("BACKEND_PORT", "8483")
BACKEND_BASE_URL = f"{API_BASE_URL}:{BACKEND_PORT}"

# 输出目录（用于缓存音频、转写、Markdown 文件，以及存储截图）
NOTE_OUTPUT_DIR = Path(os.getenv("NOTE_OUTPUT_DIR", "note_results"))
NOTE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
IMAGE_OUTPUT_DIR = os.getenv("OUT_DIR", "./static/screenshots")
# 图片基础 URL（用于生成 Markdown 中的图片链接，需前端静态目录对应）
IMAGE_BASE_URL = os.getenv("IMAGE_BASE_URL", "/static/screenshots")

# 日志配置
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class NoteGenerator:
    """
    NoteGenerator 用于执行视频/音频下载、转写、GPT 生成笔记、插入截图/链接、
    以及将任务信息写入状态文件与数据库等功能。
    """

    def __init__(self):
        self.model_size: str = "base"
        self.device: Optional[str] = None
        self.transcriber_type: str = os.getenv("TRANSCRIBER_TYPE", "fast-whisper")
        self.transcriber: Transcriber = self._init_transcriber()
        self.video_path: Optional[Path] = None
        self.video_img_urls=[]
        logger.info("NoteGenerator 初始化完成")


    # ---------------- 公有方法 ----------------

    def generate(
        self,
        video_url: Union[str, HttpUrl],
        platform: str,
        quality: DownloadQuality = DownloadQuality.medium,
        task_id: Optional[str] = None,
        model_name: Optional[str] = None,
        provider_id: Optional[str] = None,
        link: bool = False,
        screenshot: bool = False,
        _format: Optional[List[str]] = None,
        style: Optional[str] = None,
        extras: Optional[str] = None,
        output_path: Optional[str] = None,
        video_understanding: bool = False,
        video_interval: int = 0,
        grid_size: Optional[List[int]] = None,
    ) -> NoteResult | None:
        """
        主流程：按步骤依次下载、转写、GPT 总结、截图/链接处理、存库、返回 NoteResult。

        :param video_url: 视频或音频链接
        :param platform: 平台名称，对应 SUPPORT_PLATFORM_MAP 中的键
        :param quality: 下载音频的质量枚举
        :param task_id: 用于标识本次任务的唯一 ID，亦用于状态文件和缓存文件命名
        :param model_name: GPT 模型名称
        :param provider_id: 模型供应商 ID
        :param link: 是否在笔记中插入视频片段链接
        :param screenshot: 是否在笔记中替换 Screenshot 标记为图片
        :param _format: 包含 'link' 或 'screenshot' 等字符串的列表，决定后续处理
        :param style: GPT 生成笔记的风格
        :param extras: 额外参数，传递给 GPT
        :param output_path: 下载输出目录（可选）
        :param video_understanding: 是否需要视频拼图理解（生成缩略图）
        :param video_interval: 视频帧截取间隔（秒），仅在 video_understanding 为 True 时生效
        :param grid_size: 生成缩略图时的网格大小，如 [3, 3]
        :return: NoteResult 对象，包含 markdown 文本、转写结果和音频元信息
        """
        if grid_size is None:
            grid_size = []

        try:
            logger.info(f"========== 开始生成笔记 (task_id={task_id}) ==========")
            logger.info(f"[参数] video_url={video_url}")
            logger.info(f"[参数] platform={platform}, quality={quality}")
            logger.info(f"[参数] model_name={model_name}, provider_id={provider_id}")
            logger.info(f"[参数] link={link}, screenshot={screenshot}, format={_format}")
            logger.info(f"[参数] video_understanding={video_understanding}, video_interval={video_interval}, grid_size={grid_size}")
            
            # 检测 video_url 是否为本地路径（用于重新生成场景）
            # 如果是本地路径，自动切换到 local 平台处理
            video_url_str = str(video_url)
            is_local_path = (
                # Windows 路径: D:\xxx 或 D:/xxx
                (len(video_url_str) > 2 and video_url_str[1] == ':' and video_url_str[2] in ['\\', '/']) or
                # Unix 路径: /xxx (但不是 // 或 http://)
                (video_url_str.startswith('/') and not video_url_str.startswith('//'))
            )
            if is_local_path and platform != 'local':
                logger.info(f"[自动切换] 检测到本地路径，自动切换到 local 平台处理: {video_url_str}")
                platform = 'local'
            
            self._update_status(task_id, TaskStatus.PARSING, message="正在解析视频链接...", details={
                "video_url": str(video_url),
                "platform": platform,
                "model": model_name,
            })

            # 获取下载器与 GPT 实例
            logger.info("[步骤1] 初始化下载器和 GPT 实例")
            downloader = self._get_downloader(platform)
            gpt = self._get_gpt(model_name, provider_id)

            # 缓存文件路径
            audio_cache_file = NOTE_OUTPUT_DIR / f"{task_id}_audio.json"
            transcript_cache_file = NOTE_OUTPUT_DIR / f"{task_id}_transcript.json"
            markdown_cache_file = NOTE_OUTPUT_DIR / f"{task_id}_markdown.md"
            logger.debug(f"缓存文件路径: audio={audio_cache_file}, transcript={transcript_cache_file}, markdown={markdown_cache_file}")
            # 1. 下载音频/视频
            logger.info("[步骤2] 开始下载媒体文件")
            audio_meta = self._download_media(
                downloader=downloader,
                video_url=video_url,
                quality=quality,
                audio_cache_file=audio_cache_file,
                status_phase=TaskStatus.DOWNLOADING,
                platform=platform,
                output_path=output_path,
                screenshot=screenshot,
                video_understanding=video_understanding,
                video_interval=video_interval,
                grid_size=grid_size,
            )
            logger.info(f"[步骤2] 媒体下载完成: {audio_meta.file_path}")

            # 2. 转写文字
            logger.info("[步骤3] 开始转写音频")
            transcript = self._transcribe_audio(
                audio_file=audio_meta.file_path,
                transcript_cache_file=transcript_cache_file,
                status_phase=TaskStatus.TRANSCRIBING,
            )
            logger.info(f"[步骤3] 转写完成: 语言={transcript.language}, 片段数={len(transcript.segments)}")

            # 3. GPT 总结
            logger.info("[步骤4] 开始 GPT 总结")
            markdown = self._summarize_text(
                audio_meta=audio_meta,
                transcript=transcript,
                gpt=gpt,
                markdown_cache_file=markdown_cache_file,
                link=link,
                screenshot=screenshot,
                formats=_format or [],
                style=style,
                extras=extras,
                video_img_urls=self.video_img_urls,
            )
            logger.info(f"[步骤4] GPT 总结完成, markdown 长度: {len(markdown)} 字符")

            # 4. 截图 & 链接替换
            if _format:
                logger.info(f"[步骤5] 开始后处理 (format={_format})")
                markdown = self._post_process_markdown(
                    markdown=markdown,
                    video_path=self.video_path,
                    formats=_format,
                    audio_meta=audio_meta,
                    platform=platform,
                )
                logger.info("[步骤5] 后处理完成")

            # 5. 保存记录到数据库
            logger.info("[步骤6] 保存记录到数据库")
            self._update_status(task_id, TaskStatus.SAVING)
            self._save_metadata(video_id=audio_meta.video_id, platform=platform, task_id=task_id)

            # 6. 完成
            self._update_status(task_id, TaskStatus.SUCCESS)
            logger.info(f"========== 笔记生成成功 (task_id={task_id}) ==========")
            return NoteResult(markdown=markdown, transcript=transcript, audio_meta=audio_meta)

        except Exception as exc:
            logger.error(f"生成笔记流程异常 (task_id={task_id})：{exc}", exc_info=True)
            # 仅在内层 _handle_exception 尚未写入 FAILED 状态时才更新，避免覆盖详细错误信息
            status_file = NOTE_OUTPUT_DIR / f"{task_id}.status.json"
            already_failed = False
            if status_file.exists():
                try:
                    current = json.loads(status_file.read_text(encoding="utf-8"))
                    already_failed = current.get("status") == TaskStatus.FAILED.value
                except Exception:
                    pass
            if not already_failed:
                self._update_status(task_id, TaskStatus.FAILED, message=str(exc))
            return None

    @staticmethod
    def delete_note(video_id: str, platform: str) -> int:
        """
        删除数据库中对应 video_id 与 platform 的任务记录

        :param video_id: 视频 ID
        :param platform: 平台标识
        :return: 删除的记录数
        """
        logger.info(f"删除笔记记录 (video_id={video_id}, platform={platform})")
        return delete_task_by_video(video_id, platform)

    # ---------------- 私有方法 ----------------

    def _init_transcriber(self) -> Transcriber:
        """
        根据环境变量 TRANSCRIBER_TYPE 动态获取并实例化转写器
        """
        if self.transcriber_type not in _transcribers:
            logger.error(f"未找到支持的转写器：{self.transcriber_type}")
            raise Exception(f"不支持的转写器：{self.transcriber_type}")

        logger.info(f"使用转写器：{self.transcriber_type}")
        return get_transcriber(transcriber_type=self.transcriber_type)

    def _get_gpt(self, model_name: Optional[str], provider_id: Optional[str]) -> GPT:
        """
        根据 provider_id 获取对应的 GPT 实例
        :param model_name: GPT 模型名称
        :param provider_id: 供应商 ID
        :return: GPT 实例
        """
        from app.db.model_dao import get_models_by_provider

        provider = ProviderService.get_provider_by_id(provider_id)
        if not provider:
            logger.error(f"[get_gpt] 未找到模型供应商: provider_id={provider_id}")
            raise ProviderError(code=ProviderErrorEnum.NOT_FOUND,message=ProviderErrorEnum.NOT_FOUND.message)

        # 校正模型名称：前端可能传入不含分组前缀的模型名（如重试旧任务时），
        # 需要与数据库中的实际模型名匹配，确保 API 代理路由正确
        actual_model_name = model_name
        if model_name and provider_id:
            db_models = get_models_by_provider(provider_id, model_type='llm')
            # 精确匹配
            exact_match = any(m['model_name'] == model_name for m in db_models)
            if not exact_match:
                # 尝试模糊匹配：DB 中可能存储了带前缀的名称（如 [千岛]GPT-5.2）
                for m in db_models:
                    db_name = m['model_name']
                    # 检查 DB 模型名是否以 ] 结尾的前缀 + 前端传入的模型名
                    if db_name.endswith(model_name) and db_name != model_name:
                        logger.warning(
                            f"[get_gpt] 模型名称校正: '{model_name}' -> '{db_name}' "
                            f"(前端传入的名称缺少分组前缀，已自动补全)"
                        )
                        actual_model_name = db_name
                        break

        logger.info(f"[get_gpt] 创建 GPT 实例: provider={provider['name']}, model_name={actual_model_name}, base_url={provider['base_url']}")
        config = ModelConfig(
            api_key=provider["api_key"],
            base_url=provider["base_url"],
            model_name=actual_model_name,
            provider=provider["type"],
            name=provider["name"],
            provider_type=provider.get("provider_type"),  # 支持 anthropic 原生 API
        )
        return GPTFactory().from_config(config)

    def _get_downloader(self, platform: str) -> Downloader:
        """
        根据平台名称获取对应的下载器实例

        :param platform: 平台标识，需在 SUPPORT_PLATFORM_MAP 中
        :return: 对应的 Downloader 子类实例
        """
        downloader_cls = SUPPORT_PLATFORM_MAP.get(platform)
        logger.debug(f"实例化下载器 -  {platform}")
        instance = None
        if not downloader_cls:
            logger.error(f"不支持的平台：{platform}")
            raise NoteError(code=NoteErrorEnum.PLATFORM_NOT_SUPPORTED.code,
                            message=NoteErrorEnum.PLATFORM_NOT_SUPPORTED.message)
        try:
            instance = downloader_cls
        except Exception as e:
            logger.error(f"实例化下载器失败：{e}")


        logger.info(f"使用下载器：{downloader_cls.__class__}")
        return instance

    def _update_status(
        self, 
        task_id: Optional[str], 
        status: Union[str, TaskStatus], 
        message: Optional[str] = None,
        details: Optional[dict] = None
    ):
        """
        创建或更新 {task_id}.status.json，记录当前任务状态

        :param task_id: 任务唯一 ID
        :param status: TaskStatus 枚举或自定义状态字符串
        :param message: 可选消息，用于记录失败原因等
        :param details: 可选详细信息，如文件大小、进度等
        """
        if not task_id:
            return

        NOTE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        status_file = NOTE_OUTPUT_DIR / f"{task_id}.status.json"
        logger.debug(f"写入状态文件: {status_file}, 状态: {status}")
        import datetime
        now = datetime.datetime.now()
        data = {
            "status": status.value if isinstance(status, TaskStatus) else status,
            "updated_at": now.strftime("%Y-%m-%d %H:%M:%S")
        }
        if message:
            data["message"] = message
        if details:
            data["details"] = details

        try:
            # First create a temporary file
            temp_file = status_file.with_suffix('.tmp')

            # Write to temporary file
            with temp_file.open('w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            # Atomic rename operation
            temp_file.replace(status_file)

            logger.debug(f"状态文件写入成功: {status_file}")
        except Exception as e:
            logger.error(f"写入状态文件失败 (task_id={task_id})：{e}")
            # Try to write error to file directly as fallback
            try:
                with status_file.open('w', encoding='utf-8') as f:
                    f.write(f"Error writing status: {str(e)}")
            except:
                logger.error(f"写入错误  {e}")

    def _handle_exception(self, task_id, exc, step=None):
        logger.error(f"任务异常 (task_id={task_id}, step={step})", exc_info=True)
        error_message = getattr(exc, 'detail', str(exc))
        if isinstance(error_message, dict):
            try:
                error_message = json.dumps(error_message, ensure_ascii=False)
            except:
                error_message = str(error_message)
        details = {}
        if step:
            details["failed_step"] = step
        # 提取 HTTP 状态码（如 OpenAI API 错误）
        status_code = getattr(exc, 'status_code', None)
        if status_code:
            details["error_code"] = status_code
        # 解析 API 代理错误，提取有用的诊断信息
        error_str = str(exc)
        if 'model_not_found' in error_str or '无可用渠道' in error_str:
            details["error_type"] = "model_not_found"
            details["hint"] = "模型在 API 代理上不可用。请检查：1) 模型名称是否包含分组前缀（如 [千岛]GPT-5.2）；2) 该分组下是否配置了此模型的渠道；3) 尝试在 API 代理管理面板确认模型可用性。"
        self._update_status(task_id, TaskStatus.FAILED, message=error_message, details=details or None)

    def _download_media(
        self,
        downloader: Downloader,
        video_url: Union[str, HttpUrl],
        quality: DownloadQuality,
        audio_cache_file: Path,
        status_phase: TaskStatus,
        platform: str,
        output_path: Optional[str],
        screenshot: bool,
        video_understanding: bool,
        video_interval: int,
        grid_size: List[int],
    ) -> AudioDownloadResult | None:
        """
        1. 检查音频缓存；若不存在，则根据需要下载音频或视频（若需截图/可视化）。
        2. 如果需要视频，则先下载视频并生成缩略图集，再下载音频。
        3. 返回 AudioDownloadResult

        :param downloader: Downloader 实例
        :param video_url: 视频/音频链接
        :param quality: 音频下载质量
        :param audio_cache_file: 本地缓存 JSON 文件路径
        :param status_phase: 对应的状态枚举，如 TaskStatus.DOWNLOADING
        :param platform: 平台标识
        :param output_path: 下载输出目录（可为 None）
        :param screenshot: 是否需要在笔记中插入截图
        :param video_understanding: 是否需要生成缩略图
        :param video_interval: 视频截帧间隔
        :param grid_size: 缩略图网格尺寸
        :return: AudioDownloadResult 对象
        """
        task_id = audio_cache_file.stem.split("_")[0]
        self._update_status(task_id, status_phase, message="正在下载媒体文件...", details={
            "video_url": str(video_url),
            "quality": quality.value if hasattr(quality, 'value') else str(quality),
            "need_video": screenshot or video_understanding,
        })



        # 判断是否需要下载视频
        need_video = screenshot or video_understanding
        if need_video:
            try:
                logger.info("开始下载视频")
                self._update_status(task_id, status_phase, message="正在下载视频文件...", details={
                    "sub_step": "下载视频",
                })
                video_path_str = downloader.download_video(video_url)
                self.video_path = Path(video_path_str)
                video_size = self.video_path.stat().st_size if self.video_path.exists() else 0
                logger.info(f"视频下载完成：{self.video_path}")
                self._update_status(task_id, status_phase, message="视频下载完成", details={
                    "sub_step": "视频下载完成",
                    "video_file": str(self.video_path.name),
                    "video_size": f"{video_size / (1024*1024):.2f} MB",
                })

                # 若指定了 grid_size，则生成缩略图
                if grid_size:
                    logger.info(f"开始生成视频缩略图: grid_size={grid_size}, interval={video_interval}s")
                    try:
                        self.video_img_urls=VideoReader(
                            video_path=str(self.video_path),
                            grid_size=tuple(grid_size),
                            frame_interval=video_interval,
                            unit_width=1280,
                            unit_height=720,
                            save_quality=90,
                        ).run()
                        logger.info(f"✅ 缩略图生成成功，共 {len(self.video_img_urls)} 张")
                    except Exception as e:
                        logger.error(f"❌ 缩略图生成失败: {e}", exc_info=True)
                        # 缩略图生成失败不应该阻止整个流程
                        self.video_img_urls = []
                        logger.warning("⚠️ 将继续处理，但不包含视频理解功能")
                else:
                    logger.info("未指定 grid_size，跳过缩略图生成")
            except Exception as exc:
                logger.error(f"视频下载失败：{exc}", exc_info=True)

                self._handle_exception(task_id, exc, step="DOWNLOADING")
                raise
        # 已有缓存，尝试加载
        if audio_cache_file.exists():
            logger.info(f"检测到音频缓存 ({audio_cache_file})，直接读取")
            try:
                data = json.loads(audio_cache_file.read_text(encoding="utf-8"))
                # 规范化缓存中的路径（处理 Docker 路径映射）
                from app.utils.path_helper import normalize_path
                if 'file_path' in data and data['file_path']:
                    data['file_path'] = normalize_path(data['file_path'])
                if 'video_path' in data and data['video_path']:
                    data['video_path'] = normalize_path(data['video_path'])
                if 'video_url' in data and data['video_url']:
                    data['video_url'] = normalize_path(data['video_url'])
                return AudioDownloadResult(**data)
            except Exception as e:
                logger.warning(f"读取音频缓存失败，将重新下载：{e}")
        # 下载音频
        try:
            logger.info("开始下载音频")
            self._update_status(task_id, status_phase, message="正在下载音频文件...", details={
                "sub_step": "下载音频",
            })
            audio = downloader.download(
                video_url=video_url,
                quality=quality,
                output_dir=output_path,
                need_video=need_video,
            )
            # 缓存 audio 元信息到本地 JSON
            audio_cache_file.write_text(json.dumps(asdict(audio), ensure_ascii=False, indent=2), encoding="utf-8")
            # 获取音频文件大小
            audio_size = Path(audio.file_path).stat().st_size if Path(audio.file_path).exists() else 0
            logger.info(f"音频下载并缓存成功 ({audio_cache_file})")
            self._update_status(task_id, status_phase, message="音频下载完成", details={
                "sub_step": "音频下载完成",
                "audio_file": Path(audio.file_path).name,
                "audio_size": f"{audio_size / (1024*1024):.2f} MB",
                "title": audio.title,
                "duration": f"{audio.duration // 60}分{audio.duration % 60}秒" if audio.duration else "未知",
            })
            return audio
        except Exception as exc:
            logger.error(f"音频下载失败：{exc}")
            self._handle_exception(task_id, exc, step="DOWNLOADING")
            raise


    def _transcribe_audio(
        self,
        audio_file: str,
        transcript_cache_file: Path,
        status_phase: TaskStatus,
    ) -> TranscriptResult | None:
        """
        1. 检查转写缓存；若存在则尝试加载，否则调用转写器生成并缓存。
        2. 返回 TranscriptResult 对象

        :param audio_file: 音频文件本地路径
        :param transcript_cache_file: 转写结果缓存路径
        :param status_phase: 对应的状态枚举，如 TaskStatus.TRANSCRIBING
        :return: TranscriptResult 对象
        """
        task_id = transcript_cache_file.stem.split("_")[0]
        
        # 规范化路径（处理 Docker 路径映射）
        from app.utils.path_helper import normalize_path
        audio_file = normalize_path(audio_file)
        
        logger.info(f"[转写] 开始处理音频文件: {audio_file}")
        logger.info(f"[转写] 使用转写器类型: {self.transcriber_type}")
        logger.info(f"[转写] 缓存文件路径: {transcript_cache_file}")

        # 检查音频文件是否存在
        if not Path(audio_file).exists():
            logger.error(f"[转写] 音频文件不存在: {audio_file}")
            raise FileNotFoundError(f"音频文件不存在: {audio_file}")

        # 获取音频文件信息
        audio_file_size = Path(audio_file).stat().st_size
        logger.info(f"[转写] 音频文件大小: {audio_file_size / (1024*1024):.2f} MB")
        
        self._update_status(task_id, status_phase, message="正在转写音频内容...", details={
            "audio_file": Path(audio_file).name,
            "audio_size": f"{audio_file_size / (1024*1024):.2f} MB",
            "transcriber": self.transcriber_type,
        })

        # 已有缓存，尝试加载
        if transcript_cache_file.exists():
            logger.info(f"[转写] 检测到转写缓存 ({transcript_cache_file})，尝试读取")
            try:
                data = json.loads(transcript_cache_file.read_text(encoding="utf-8"))
                segments = [TranscriptSegment(**seg) for seg in data.get("segments", [])]
                logger.info(f"[转写] 从缓存加载成功: 语言={data['language']}, 片段数={len(segments)}")
                return TranscriptResult(language=data["language"], full_text=data["full_text"], segments=segments)
            except Exception as e:
                logger.warning(f"[转写] 加载转写缓存失败，将重新转写：{e}")

        # 调用转写器
        try:
            logger.info(f"[转写] 开始调用转写器 ({self.transcriber_type}) 进行音频转写...")
            self._update_status(task_id, status_phase, message="正在调用转写服务...", details={
                "transcriber": self.transcriber_type,
                "sub_step": "转写中",
            })

            transcript = self.transcriber.transcript(file_path=audio_file)

            logger.info(f"[转写] 转写完成: 语言={transcript.language}, 片段数={len(transcript.segments)}, 文本长度={len(transcript.full_text)}")

            transcript_cache_file.write_text(json.dumps(asdict(transcript), ensure_ascii=False, indent=2), encoding="utf-8")

            logger.info(f"[转写] 结果已缓存到: {transcript_cache_file}")
            self._update_status(task_id, status_phase, message="转写完成", details={
                "language": transcript.language,
                "segments_count": len(transcript.segments),
                "text_length": f"{len(transcript.full_text)} 字符",
                "sub_step": "转写完成",
            })
            return transcript
        except Exception as exc:
            logger.error(f"[转写] 音频转写失败：{exc}", exc_info=True)
            self._handle_exception(task_id, exc, step="TRANSCRIBING")
            raise

    def _summarize_text(
        self,
        audio_meta: AudioDownloadResult,
        transcript: TranscriptResult,
        gpt: GPT,
        markdown_cache_file: Path,
        link: bool,
        screenshot: bool,
        formats: List[str],
        style: Optional[str],
        extras: Optional[str],
            video_img_urls: List[str],
    ) -> str | None:
        """
        调用 GPT 对转写结果进行总结，生成 Markdown 文本并缓存。

        :param audio_meta: AudioDownloadResult 元信息
        :param transcript: TranscriptResult 转写结果
        :param gpt: GPT 实例
        :param markdown_cache_file: Markdown 缓存路径
        :param link: 是否在笔记中插入链接
        :param screenshot: 是否在笔记中生成截图占位
        :param formats: 包含 'link' 或 'screenshot' 的列表
        :param style: GPT 输出风格
        :param extras: GPT 额外参数
        :return: 生成的 Markdown 字符串
        """
        task_id = markdown_cache_file.stem.split("_")[0]
        logger.info(f"[GPT总结] 开始处理: task_id={task_id}")
        logger.info(f"[GPT总结] 参数: link={link}, screenshot={screenshot}, formats={formats}")
        logger.info(f"[GPT总结] 视频图片数量: {len(video_img_urls)}")

        self._update_status(task_id, TaskStatus.SUMMARIZING, message="正在用 AI 生成笔记...", details={
            "title": audio_meta.title,
            "segments_count": len(transcript.segments),
            "text_length": f"{len(transcript.full_text)} 字符",
            "style": style or "默认",
            "has_images": len(video_img_urls) > 0,
        })

        logger.info("[GPT总结] 构建 GPTSource 对象...")
        source = GPTSource(
            title=audio_meta.title,
            segment=transcript.segments,
            tags=audio_meta.raw_info.get("tags", []),
            screenshot=screenshot,
            video_img_urls=video_img_urls,
            link=link,
            _format=formats,
            style=style,
            extras=extras,
        )
        logger.info(f"[GPT总结] GPTSource 构建完成: title={source.title}, segments={len(source.segment)}, images={len(source.video_img_urls)}")

        # 获取实际发送给 API 的模型名称（可能包含分组前缀）
        actual_model_name = getattr(gpt, 'model', None) or (gpt.config.model_name if hasattr(gpt, 'config') else "未知")
        logger.info(f"[GPT总结] 实际使用的模型名称: {actual_model_name}")

        try:
            logger.info("[GPT总结] 调用 gpt.summarize()...")
            self._update_status(task_id, TaskStatus.SUMMARIZING, message="AI 正在分析内容并生成笔记...", details={
                "sub_step": "调用 AI 模型",
                "model": actual_model_name,
            })

            markdown = gpt.summarize(source)

            logger.info(f"[GPT总结] GPT 调用成功，返回内容长度: {len(markdown)} 字符")

            logger.info(f"[GPT总结] 保存 markdown 到缓存文件: {markdown_cache_file}")
            markdown_cache_file.write_text(markdown, encoding="utf-8")
            logger.info(f"[GPT总结] GPT 总结并缓存成功")
            self._update_status(task_id, TaskStatus.SUMMARIZING, message="笔记生成完成", details={
                "sub_step": "生成完成",
                "markdown_length": f"{len(markdown)} 字符",
            })
            return markdown
        except Exception as exc:
            logger.error(f"[GPT总结] GPT 总结失败：{exc}", exc_info=True)
            self._handle_exception(task_id, exc, step="SUMMARIZING")
            raise

    def _post_process_markdown(
        self,
        markdown: str,
        video_path: Optional[Path],
        formats: List[str],
        audio_meta: AudioDownloadResult,
        platform: str,
    ) -> str:
        """
        对生成的 Markdown 做后期处理：插入截图和/或插入链接。

        :param markdown: 原始 Markdown 字符串
        :param video_path: 本地视频路径（可为 None）
        :param formats: 包含 'link' 或 'screenshot' 的列表
        :param audio_meta: AudioDownloadResult 元信息，用于链接替换
        :param platform: 平台标识，用于链接替换
        :return: 处理后的 Markdown 字符串
        """
        if "screenshot" in formats and video_path:
            try:
                markdown = self._insert_screenshots(markdown, video_path)
            except Exception as exc:
                logger.warning("截图插入失败，跳过该步骤")

        if "link" in formats:
            try:
                markdown = replace_content_markers(markdown, video_id=audio_meta.video_id, platform=platform)
            except Exception as e:
                logger.warning(f"链接插入失败，跳过该步骤：{e}")

        return markdown

    def _insert_screenshots(self, markdown: str, video_path: Path) -> str | None | Any:
        """
        扫描 Markdown 文本中所有 Screenshot 标记，并替换为实际生成的截图链接。

        :param markdown: 含有 *Screenshot-mm:ss 或 Screenshot-[mm:ss] 标记的 Markdown 文本
        :param video_path: 本地视频文件路径
        :return: 替换后的 Markdown 字符串
        """
        matches: List[Tuple[str, int]] = self._extract_screenshot_timestamps(markdown)
        for idx, (marker, ts) in enumerate(matches):
            try:
                img_path = generate_screenshot(str(video_path), str(IMAGE_OUTPUT_DIR), ts, idx)
                filename = Path(img_path).name
                # 构建前端可访问的 URL，例如 /static/screenshots/{filename}
                img_url = f"{IMAGE_BASE_URL.rstrip('/')}/{filename}"
                markdown = markdown.replace(marker, f"![]({img_url})", 1)
            except Exception as exc:
                logger.error(f"生成截图失败 (timestamp={ts})：{exc}")
                # self._handle_exception(task_id, exc)
                return None
        return markdown

    @staticmethod
    def _extract_screenshot_timestamps(markdown: str) -> List[Tuple[str, int]]:
        """
        从 Markdown 文本中提取所有 '*Screenshot-mm:ss' 或 'Screenshot-[mm:ss]' 标记，
        返回 [(原始标记文本, 时间戳秒数), ...] 列表。

        :param markdown: 原始 Markdown 文本
        :return: 标记与对应时间戳秒数的列表
        """
        pattern = r"(?:\*Screenshot-(\d{2}):(\d{2})|Screenshot-\[(\d{2}):(\d{2})\])"
        results: List[Tuple[str, int]] = []
        for match in re.finditer(pattern, markdown):
            mm = match.group(1) or match.group(3)
            ss = match.group(2) or match.group(4)
            total_seconds = int(mm) * 60 + int(ss)
            results.append((match.group(0), total_seconds))
        return results

    def _save_metadata(self, video_id: str, platform: str, task_id: str) -> None:
        """
        将生成的笔记任务记录插入数据库

        :param video_id: 视频 ID
        :param platform: 平台标识
        :param task_id: 任务 ID
        """
        try:
            insert_video_task(video_id=video_id, platform=platform, task_id=task_id)
            logger.info(f"已保存任务记录到数据库 (video_id={video_id}, platform={platform}, task_id={task_id})")
        except Exception as e:
            logger.error(f"保存任务记录失败：{e}")