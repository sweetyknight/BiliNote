import os
import json
import tempfile
from abc import ABC
from typing import Union, Optional

import yt_dlp

from app.downloaders.base import Downloader, DownloadQuality
from app.models.notes_model import AudioDownloadResult
from app.services.cookie_manager import CookieConfigManager
from app.utils.path_helper import get_data_dir
from app.utils.url_parser import extract_video_id

# #region agent log
_DEBUG_LOG_PATH = r"d:\BiliNote\.cursor\debug.log"
def _debug_log(location, message, data, hypothesis_id):
    import json
    with open(_DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps({"location": location, "message": message, "data": data, "hypothesisId": hypothesis_id, "timestamp": __import__("time").time(), "sessionId": "debug-session"}, ensure_ascii=False) + "\n")
# #endregion

cookie_manager = CookieConfigManager()


class YoutubeDownloader(Downloader, ABC):
    def __init__(self):
        super().__init__()
        self._cookie_file = None
    
    def _get_cookie_config(self) -> dict:
        """获取YouTube cookies配置，返回 ydl_opts 中应该添加的选项"""
        cookie_str = cookie_manager.get("youtube")
        
        # 如果配置为特殊值 "browser:chrome" 或 "browser:edge"，则从浏览器获取
        if cookie_str and cookie_str.startswith("browser:"):
            browser_name = cookie_str.split(":", 1)[1].strip()
            # #region agent log
            _debug_log("youtube_downloader.py:_get_cookie_config", f"使用浏览器cookies: {browser_name}", {"browser": browser_name}, "COOKIE")
            # #endregion
            return {'cookiesfrombrowser': (browser_name,)}
        
        if not cookie_str:
            # 没有配置cookies，返回空配置（不尝试从浏览器获取，因为可能会失败）
            # #region agent log
            _debug_log("youtube_downloader.py:_get_cookie_config", "未配置YouTube cookies", {}, "COOKIE")
            # #endregion
            return {}
        
        # 创建临时cookies文件（Netscape格式）
        try:
            # 如果cookie已经是Netscape格式（以#开头或包含制表符分隔的内容），直接使用
            if cookie_str.strip().startswith('#') or '\t' in cookie_str:
                # 修复：有些cookie可能所有条目都在一行，需要按域名分割成多行
                # Netscape格式要求每个cookie条目占一行
                import re
                # 检测是否需要分割（如果没有换行符但有多个域名条目）
                if '\n' not in cookie_str.strip() or cookie_str.count('\n') < 3:
                    # 按照 .domain.com 或 domain.com 开头的模式分割
                    # 匹配 ".youtube.com\t" 或 "youtube.com\t" 这样的模式
                    fixed_cookie = re.sub(r'\s+(\.?[a-zA-Z0-9][-a-zA-Z0-9]*\.(?:com|net|org|io|co)\t)', r'\n\1', cookie_str)
                    # #region agent log
                    line_count = fixed_cookie.count('\n') + 1
                    _debug_log("youtube_downloader.py:_get_cookie_config", "修复cookie格式，添加换行符", {"original_lines": cookie_str.count('\n') + 1, "fixed_lines": line_count}, "COOKIE_FIX")
                    # #endregion
                    cookie_str = fixed_cookie
                
                cookie_file = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8')
                cookie_file.write(cookie_str)
                cookie_file.close()
                self._cookie_file = cookie_file.name
                # #region agent log
                _debug_log("youtube_downloader.py:_get_cookie_config", "使用Netscape格式cookies文件", {"cookie_file": self._cookie_file, "cookie_lines": cookie_str.count('\n') + 1}, "COOKIE")
                # #endregion
                return {'cookiefile': self._cookie_file}
            else:
                # 简单的key=value格式，无法使用
                # #region agent log
                _debug_log("youtube_downloader.py:_get_cookie_config", "cookies格式不是Netscape格式，跳过", {"cookie_preview": cookie_str[:50] if len(cookie_str) > 50 else cookie_str}, "COOKIE")
                # #endregion
                return {}
        except Exception as e:
            # #region agent log
            _debug_log("youtube_downloader.py:_get_cookie_config:error", "创建cookies文件失败", {"error": str(e)}, "COOKIE")
            # #endregion
            return {}
    
    def _cleanup_cookie_file(self):
        """清理临时cookies文件"""
        if self._cookie_file and os.path.exists(self._cookie_file):
            try:
                os.unlink(self._cookie_file)
            except:
                pass
            self._cookie_file = None

    def download(
        self,
        video_url: str,
        output_dir: Union[str, None] = None,
        quality: DownloadQuality = "fast",
        need_video:Optional[bool]=False
    ) -> AudioDownloadResult:
        # #region agent log
        _debug_log("youtube_downloader.py:download:entry", "download() called", {"video_url": video_url, "quality": str(quality), "need_video": need_video}, "A")
        # #endregion
        if output_dir is None:
            output_dir = get_data_dir()
        if not output_dir:
            output_dir=self.cache_data
        os.makedirs(output_dir, exist_ok=True)

        output_path = os.path.join(output_dir, "%(id)s.%(ext)s")

        ydl_opts = {
            # 先尝试 m4a，然后任意最佳音频，最后任意最佳格式
            'format': 'bestaudio[ext=m4a]/bestaudio/best',
            'outtmpl': output_path,
            'noplaylist': True,
            'quiet': False,
            # 启用远程组件来解决 YouTube n 参数签名 (推荐方式)
            'remote_components': ['ejs:github'],
            'js_runtimes': {'node': {}},
        }
        
        # 添加cookies支持
        cookie_opts = self._get_cookie_config()
        ydl_opts.update(cookie_opts)
        
        # #region agent log
        _debug_log("youtube_downloader.py:download:before_extract", "ydl_opts for download()", {"format": ydl_opts['format'], "output_dir": output_dir, "cookie_opts": str(cookie_opts)}, "F1")
        # #endregion

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # #region agent log
                _debug_log("youtube_downloader.py:download:extracting", "开始提取视频信息", {"video_url": video_url}, "F1")
                # #endregion
                info = ydl.extract_info(video_url, download=True)
                video_id = info.get("id")
                title = info.get("title")
                duration = info.get("duration", 0)
                cover_url = info.get("thumbnail")
                ext = info.get("ext", "m4a")  # 兜底用 m4a
                audio_path = os.path.join(output_dir, f"{video_id}.{ext}")
                # #region agent log
                _debug_log("youtube_downloader.py:download:success", "download() completed", {"video_id": video_id, "ext": ext, "audio_path": audio_path, "title": title}, "F1")
                # #endregion
        except Exception as e:
            # #region agent log
            import traceback
            _debug_log("youtube_downloader.py:download:ERROR", "YouTube下载失败", {"error": str(e), "error_type": type(e).__name__, "traceback": traceback.format_exc()}, "F1,F2,F3")
            # #endregion
            raise
        print('os.path.join(output_dir, f"{video_id}.{ext}")',os.path.join(output_dir, f"{video_id}.{ext}"))

        return AudioDownloadResult(
            file_path=audio_path,
            title=title,
            duration=duration,
            cover_url=cover_url,
            platform="youtube",
            video_id=video_id,
            raw_info={'tags':info.get('tags')}, #全部返回会报错
            video_path=None,  # ❗音频下载不包含视频路径
            video_url=video_url  # 保存原始视频链接
        )

    def download_video(
        self,
        video_url: str,
        output_dir: Union[str, None] = None,
    ) -> str:
        """
        下载视频，返回视频文件路径
        """
        # #region agent log
        _debug_log("youtube_downloader.py:download_video:entry", "download_video() called", {"video_url": video_url}, "B")
        # #endregion
        if output_dir is None:
            output_dir = get_data_dir()
        video_id = extract_video_id(video_url, "youtube")
        video_path = os.path.join(output_dir, f"{video_id}.mp4")
        if os.path.exists(video_path):
            # #region agent log
            _debug_log("youtube_downloader.py:download_video:cache_hit", "Video already exists", {"video_path": video_path}, "B")
            # #endregion
            return video_path
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, "%(id)s.%(ext)s")

        ydl_opts = {
            # 先尝试 mp4+m4a，然后尝试任意最佳视频+音频，最后任意最佳格式
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best',
            'outtmpl': output_path,
            'noplaylist': True,
            'quiet': False,
            'merge_output_format': 'mp4',  # 确保合并成 mp4
            # 启用远程组件来解决 YouTube n 参数签名 (推荐方式)
            'remote_components': ['ejs:github'],
            'js_runtimes': {'node': {}},
        }
        
        # 添加cookies支持
        cookie_opts = self._get_cookie_config()
        ydl_opts.update(cookie_opts)
        
        # #region agent log
        _debug_log(
            "youtube_downloader.py:download_video:before_extract",
            "ydl_opts for download_video()",
            {
                "format": ydl_opts["format"],
                "cookie_opts_keys": list(cookie_opts.keys()),
                "cookiefile_exists": os.path.exists(cookie_opts.get("cookiefile", "")) if "cookiefile" in cookie_opts else False,
                "js_runtimes": ydl_opts.get("js_runtimes", {}),
            },
            "B"
        )
        # #endregion

        # #region agent log
        try:
            check_opts = {
                'quiet': True,
                'js_runtimes': {'node': {}},
            }
            check_opts.update(cookie_opts)
            # #region agent log
            import shutil
            _debug_log(
                "youtube_downloader.py:download_video:env_check",
                "Environment check",
                {"ffmpeg_path": shutil.which("ffmpeg"), "cookie_opts_keys": list(cookie_opts.keys())},
                "H"
            )
            # #endregion
            with yt_dlp.YoutubeDL(check_opts) as ydl_check:
                formats_info = ydl_check.extract_info(video_url, download=False)
                available_formats = [
                    {
                        "format_id": f.get("format_id"),
                        "ext": f.get("ext"),
                        "acodec": f.get("acodec"),
                        "vcodec": f.get("vcodec"),
                        "protocol": f.get("protocol"),
                    }
                    for f in formats_info.get("formats", [])
                ]
                _debug_log("youtube_downloader.py:download_video:available_formats", "Available formats for video", {"video_id": formats_info.get("id"), "formats_count": len(available_formats), "formats": available_formats}, "C")
        except Exception as e:
            _debug_log("youtube_downloader.py:download_video:format_check_error", "Error checking formats", {"error": str(e)}, "E")
        # #endregion

        # #region agent log
        _debug_log(
            "youtube_downloader.py:download_video:attempt1",
            "First download attempt with cookies",
            {"has_cookies": bool(cookie_opts)},
            "RETRY"
        )
        # #endregion
        
        download_success = False
        last_error = None
        
        # 尝试下载，如果失败且有 cookies，则重试不使用 cookies
        for attempt, use_cookies in enumerate([(True, cookie_opts), (False, {})], 1):
            should_use_cookies, current_cookie_opts = use_cookies
            
            # 如果没有配置 cookies，跳过第一次尝试后的重试
            if attempt == 2 and not cookie_opts:
                break
                
            try:
                current_ydl_opts = ydl_opts.copy()
                if should_use_cookies:
                    current_ydl_opts.update(current_cookie_opts)
                else:
                    # 移除 cookies 相关配置
                    current_ydl_opts.pop('cookiefile', None)
                    current_ydl_opts.pop('cookiesfrombrowser', None)
                
                # #region agent log
                _debug_log(
                    f"youtube_downloader.py:download_video:attempt{attempt}",
                    f"Download attempt {attempt}",
                    {"use_cookies": should_use_cookies, "has_cookiefile": 'cookiefile' in current_ydl_opts},
                    "RETRY"
                )
                # #endregion
                
                with yt_dlp.YoutubeDL(current_ydl_opts) as ydl:
                    info = ydl.extract_info(video_url, download=True)
                    video_id = info.get("id")
                    video_path = os.path.join(output_dir, f"{video_id}.mp4")
                    
                    # 检查是否成功下载了视频文件（而不是只有音频）
                    actual_ext = info.get("ext", "")
                    requested = info.get("requested_formats") or []
                    has_video = any(f.get("vcodec") and f.get("vcodec") != "none" for f in requested) if requested else (info.get("vcodec") and info.get("vcodec") != "none")
                    
                    # #region agent log
                    requested_slim = [
                        {
                            "format_id": f.get("format_id"),
                            "ext": f.get("ext"),
                            "protocol": f.get("protocol"),
                            "vcodec": f.get("vcodec"),
                        }
                        for f in requested
                    ]
                    _debug_log(
                        "youtube_downloader.py:download_video:download_result",
                        "Download result check",
                        {
                            "video_id": video_id,
                            "video_path": video_path,
                            "actual_ext": actual_ext,
                            "has_video": has_video,
                            "mp4_exists": os.path.exists(video_path),
                            "format_id": info.get("format_id"),
                            "protocol": info.get("protocol"),
                            "requested_formats": requested_slim,
                            "attempt": attempt,
                        },
                        "B"
                    )
                    # #endregion
                    
                    # 如果没有下载到视频（只有音频），且这是第一次尝试且有 cookies，则重试
                    if not os.path.exists(video_path) and attempt == 1 and cookie_opts:
                        # #region agent log
                        _debug_log(
                            "youtube_downloader.py:download_video:no_video_retry",
                            "Video file not found, retrying without cookies",
                            {"video_path": video_path, "actual_ext": actual_ext, "has_video": has_video},
                            "RETRY"
                        )
                        # #endregion
                        # 删除可能下载的音频文件
                        audio_path = os.path.join(output_dir, f"{video_id}.{actual_ext}")
                        if os.path.exists(audio_path) and actual_ext != "mp4":
                            try:
                                os.remove(audio_path)
                            except:
                                pass
                        continue  # 重试不使用 cookies
                    
                    download_success = True
                    break
                    
            except Exception as e:
                last_error = e
                error_msg = str(e).lower()
                # #region agent log
                _debug_log(
                    f"youtube_downloader.py:download_video:attempt{attempt}_error",
                    f"Download attempt {attempt} failed",
                    {"error": str(e), "error_type": type(e).__name__, "will_retry": attempt == 1 and bool(cookie_opts)},
                    "RETRY"
                )
                # #endregion
                
                # 如果是 cookies 相关错误，尝试不使用 cookies 重试
                if attempt == 1 and cookie_opts and (
                    'cookies are no longer valid' in error_msg or
                    'sign in to confirm' in error_msg or
                    'bot' in error_msg
                ):
                    # #region agent log
                    _debug_log(
                        "youtube_downloader.py:download_video:retry_without_cookies",
                        "Retrying without cookies due to cookie-related error",
                        {"original_error": str(e)},
                        "RETRY"
                    )
                    # #endregion
                    continue
                else:
                    # 非 cookies 相关错误或已重试，直接抛出
                    raise
        
        if not download_success and last_error:
            raise last_error

        if not os.path.exists(video_path):
            raise FileNotFoundError(f"视频文件未找到: {video_path}")

        return video_path
