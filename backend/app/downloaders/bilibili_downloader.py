import json
import logging
import os
import tempfile
from abc import ABC
from typing import Union, Optional

import yt_dlp

from app.downloaders.base import Downloader, DownloadQuality, QUALITY_MAP
from app.models.notes_model import AudioDownloadResult
from app.services.cookie_manager import CookieConfigManager
from app.utils.path_helper import get_data_dir
from app.utils.url_parser import extract_video_id

logger = logging.getLogger(__name__)
cookie_manager = CookieConfigManager()


class BilibiliDownloader(Downloader, ABC):
    def __init__(self):
        super().__init__()
        self._cookie_file = None

    def _get_cookie_config(self) -> dict:
        """获取Bilibili cookies配置，返回 ydl_opts 中应该添加的选项"""
        cookie_str = cookie_manager.get("bilibili")

        if not cookie_str:
            logger.warning("未配置Bilibili cookies，部分视频可能无法下载")
            return {}

        # 支持 "browser:chrome" 格式，从浏览器获取cookies
        if cookie_str.strip().startswith("browser:"):
            browser_name = cookie_str.split(":", 1)[1].strip()
            logger.info(f"使用浏览器cookies: {browser_name}")
            return {'cookiesfrombrowser': (browser_name,)}

        try:
            # 尝试解析为JSON数组格式（浏览器扩展导出格式）
            cookies = json.loads(cookie_str)
            if isinstance(cookies, list):
                return self._convert_json_cookies_to_file(cookies)
        except (json.JSONDecodeError, TypeError):
            pass

        # Netscape格式（以#开头或包含制表符分隔的内容）
        if cookie_str.strip().startswith('#') or '\t' in cookie_str:
            return self._write_cookie_file(cookie_str)

        logger.warning("Bilibili cookies格式无法识别，跳过cookie配置")
        return {}

    def _convert_json_cookies_to_file(self, cookies: list) -> dict:
        """将JSON数组格式的cookies转换为Netscape格式cookie文件"""
        lines = ["# Netscape HTTP Cookie File"]
        for cookie in cookies:
            if not isinstance(cookie, dict):
                continue
            domain = cookie.get("domain", "")
            flag = "TRUE" if domain.startswith(".") else "FALSE"
            path = cookie.get("path", "/")
            secure = "TRUE" if cookie.get("secure", False) else "FALSE"
            expiry = str(int(cookie.get("expirationDate", 0)))
            name = cookie.get("name", "")
            value = cookie.get("value", "")
            if name:
                lines.append(f"{domain}\t{flag}\t{path}\t{secure}\t{expiry}\t{name}\t{value}")

        if len(lines) <= 1:
            return {}

        return self._write_cookie_file("\n".join(lines))

    def _write_cookie_file(self, content: str) -> dict:
        """将cookie内容写入临时文件并返回yt_dlp配置"""
        try:
            cookie_file = tempfile.NamedTemporaryFile(
                mode='w', suffix='.txt', delete=False, encoding='utf-8'
            )
            cookie_file.write(content)
            cookie_file.close()
            self._cookie_file = cookie_file.name
            logger.info(f"Bilibili cookies文件已创建: {self._cookie_file}")
            return {'cookiefile': self._cookie_file}
        except Exception as e:
            logger.error(f"创建Bilibili cookies文件失败: {e}")
            return {}

    def _cleanup_cookie_file(self):
        """清理临时cookies文件"""
        if self._cookie_file and os.path.exists(self._cookie_file):
            try:
                os.unlink(self._cookie_file)
            except Exception:
                pass
            self._cookie_file = None

    def download(
        self,
        video_url: str,
        output_dir: Union[str, None] = None,
        quality: DownloadQuality = "fast",
        need_video:Optional[bool]=False
    ) -> AudioDownloadResult:
        if output_dir is None:
            output_dir = get_data_dir()
        if not output_dir:
            output_dir=self.cache_data
        os.makedirs(output_dir, exist_ok=True)

        output_path = os.path.join(output_dir, "%(id)s.%(ext)s")

        ydl_opts = {
            'format': 'bestaudio[ext=m4a]/bestaudio/best',
            'outtmpl': output_path,
            'postprocessors': [
                {
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '64',
                }
            ],
            'noplaylist': True,
            'quiet': False,
        }

        # 添加cookies支持
        cookie_opts = self._get_cookie_config()
        ydl_opts.update(cookie_opts)

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=True)
                video_id = info.get("id")
                title = info.get("title")
                duration = info.get("duration", 0)
                cover_url = info.get("thumbnail")
                audio_path = os.path.join(output_dir, f"{video_id}.mp3")

            return AudioDownloadResult(
                file_path=audio_path,
                title=title,
                duration=duration,
                cover_url=cover_url,
                platform="bilibili",
                video_id=video_id,
                raw_info=info,
                video_path=None,
                video_url=video_url
            )
        finally:
            self._cleanup_cookie_file()

    def download_video(
        self,
        video_url: str,
        output_dir: Union[str, None] = None,
    ) -> str:
        """
        下载视频，返回视频文件路径
        """

        if output_dir is None:
            output_dir = get_data_dir()
        os.makedirs(output_dir, exist_ok=True)
        print("video_url",video_url)
        video_id=extract_video_id(video_url, "bilibili")
        video_path = os.path.join(output_dir, f"{video_id}.mp4")
        if os.path.exists(video_path):
            return video_path

        # 检查是否已经存在


        output_path = os.path.join(output_dir, "%(id)s.%(ext)s")

        ydl_opts = {
            'format': 'bv*[ext=mp4]/bestvideo+bestaudio/best',
            'outtmpl': output_path,
            'noplaylist': True,
            'quiet': False,
            'merge_output_format': 'mp4',  # 确保合并成 mp4
        }

        # 添加cookies支持
        cookie_opts = self._get_cookie_config()
        ydl_opts.update(cookie_opts)

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=True)
                video_id = info.get("id")
                video_path = os.path.join(output_dir, f"{video_id}.mp4")

            if not os.path.exists(video_path):
                raise FileNotFoundError(f"视频文件未找到: {video_path}")

            return video_path
        finally:
            self._cleanup_cookie_file()

    def delete_video(self, video_path: str) -> str:
        """
        删除视频文件
        """
        if os.path.exists(video_path):
            os.remove(video_path)
            return f"视频文件已删除: {video_path}"
        else:
            return f"视频文件未找到: {video_path}"