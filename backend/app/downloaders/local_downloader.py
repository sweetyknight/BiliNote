import os
import subprocess
import json
from abc import ABC
from typing import Optional

from app.downloaders.base import Downloader
from app.enmus.note_enums import DownloadQuality
from app.models.audio_model import AudioDownloadResult

from app.utils.video_helper import save_cover_to_static


class LocalDownloader(Downloader, ABC):
    def __init__(self):
        super().__init__()

    def has_audio_stream(self, input_path: str) -> bool:
        """
        检查视频文件是否包含音频流
        :param input_path: 输入文件路径
        :return: True 如果有音频流，False 否则
        """
        try:
            command = [
                'ffprobe',
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_streams',
                '-select_streams', 'a',  # 只选择音频流
                input_path
            ]
            result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            output = json.loads(result.stdout.decode('utf-8'))
            streams = output.get('streams', [])
            return len(streams) > 0
        except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
            print(f"[ffprobe 警告] 检查音频流失败: {e}")
            # 如果 ffprobe 失败，假设有音频流，让 ffmpeg 去处理
            return True


    def extract_cover(self, input_path: str, output_dir: Optional[str] = None) -> str:
        """
        从本地视频文件中提取一张封面图（默认取第一帧）
        :param input_path: 输入视频路径
        :param output_dir: 输出目录，默认和视频同目录
        :return: 提取出的封面图片路径
        """
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"输入文件不存在: {input_path}")

        if output_dir is None:
            output_dir = os.path.dirname(input_path)

        base_name = os.path.splitext(os.path.basename(input_path))[0]
        output_path = os.path.join(output_dir, f"{base_name}_cover.jpg")

        try:
            command = [
                'ffmpeg',
                '-i', input_path,
                '-ss', '00:00:01',  # 跳到视频第1秒，防止黑屏
                '-vframes', '1',  # 只截取一帧
                '-q:v', '2',  # 输出质量高一点（qscale，2是很高）
                '-y',  # 覆盖
                output_path
            ]
            subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)

            if not os.path.exists(output_path):
                raise RuntimeError(f"封面图片生成失败: {output_path}")

            return output_path
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"提取封面失败: {output_path}") from e

    def convert_to_mp3(self, input_path: str, output_path: str = None) -> str:
        """
        将本地视频文件转为 MP3 音频文件
        :param input_path: 输入文件路径（如 .mp4）
        :param output_path: 输出文件路径（可选，默认同目录同名 .mp3）
        :return: 生成的 mp3 文件路径
        """
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"输入文件不存在: {input_path}")

        # 检查视频文件是否包含音频流
        if not self.has_audio_stream(input_path):
            raise RuntimeError(
                f"视频文件不包含音频流，无法提取音频: {input_path}\n"
                "请确保上传的视频文件包含音频轨道。"
            )

        if output_path is None:
            base, _ = os.path.splitext(input_path)
            output_path = base + ".mp3"
        try:
            # 调用 ffmpeg 转换
            command = [
                'ffmpeg',
                '-i', input_path,
                '-vn',  # 不要视频流
                '-acodec', 'libmp3lame',  # 使用mp3编码
                '-y',  # 覆盖输出文件
                output_path
            ]

            result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)

            if not os.path.exists(output_path):
                raise RuntimeError(f"mp3 文件生成失败: {output_path}")

            return output_path
        except subprocess.CalledProcessError as e:
            # 捕获并打印 ffmpeg 的详细错误信息
            stderr_output = e.stderr.decode('utf-8', errors='replace') if e.stderr else "无错误输出"
            print(f"[ffmpeg 错误] 退出码: {e.returncode}")
            print(f"[ffmpeg 错误] 输入文件: {input_path}")
            print(f"[ffmpeg 错误] 输出文件: {output_path}")
            print(f"[ffmpeg 错误] 详细信息:\n{stderr_output}")
            
            # 检查是否是因为没有音频流导致的错误
            if "does not contain any stream" in stderr_output:
                raise RuntimeError(
                    f"视频文件不包含音频流，无法提取音频: {input_path}\n"
                    "请确保上传的视频文件包含音频轨道。"
                ) from e
            
            raise RuntimeError(f"mp3 文件生成失败: {output_path}\nffmpeg 错误: {stderr_output[:500]}") from e
    def download_video(self, video_url: str, output_dir: str = None) -> str:
        """
        处理本地文件路径，返回视频文件路径
        """
        from app.utils.path_helper import normalize_path
        
        # #region agent log
        import json as _json_debug
        _log_path = r"d:\BiliNote\.cursor\debug.log"
        with open(_log_path, "a", encoding="utf-8") as _f: _f.write(_json_debug.dumps({"hypothesisId":"A,E","location":"local_downloader.py:download_video:entry","message":"download_video entry","data":{"video_url":video_url,"output_dir":output_dir},"timestamp":__import__("time").time()*1000,"sessionId":"debug-session","runId":"post-fix"})+"\n")
        # #endregion
        
        # 规范化路径（处理 Docker 路径和 /uploads 路径）
        original_url = video_url
        video_url = normalize_path(video_url)
        
        # #region agent log
        if original_url != video_url:
            with open(_log_path, "a", encoding="utf-8") as _f: _f.write(_json_debug.dumps({"hypothesisId":"DOCKER_PATH_FIX","location":"local_downloader.py:download_video:path_normalized","message":"Path normalized","data":{"original":original_url,"normalized":video_url},"timestamp":__import__("time").time()*1000,"sessionId":"debug-session","runId":"post-fix"})+"\n")
        # #endregion

        # #region agent log
        _file_exists = os.path.exists(video_url)
        _parent_dir = os.path.dirname(video_url)
        _parent_exists = os.path.exists(_parent_dir) if _parent_dir else False
        _parent_contents = os.listdir(_parent_dir) if _parent_exists else []
        with open(_log_path, "a", encoding="utf-8") as _f: _f.write(_json_debug.dumps({"hypothesisId":"C,D","location":"local_downloader.py:download_video:before_check","message":"file existence check","data":{"video_url":video_url,"file_exists":_file_exists,"parent_dir":_parent_dir,"parent_exists":_parent_exists,"parent_contents":_parent_contents[:20]},"timestamp":__import__("time").time()*1000,"sessionId":"debug-session","runId":"post-fix"})+"\n")
        # #endregion
        if not os.path.exists(video_url):
            raise FileNotFoundError(f"文件不存在: {video_url}")
        return video_url
    def download(
            self,
            video_url: str,
            output_dir: str = None,
            quality: DownloadQuality = "fast",
            need_video: Optional[bool] = False
    ) -> AudioDownloadResult:
        """
        处理本地文件路径，返回音频元信息
        """
        from app.utils.path_helper import normalize_path
        
        # 规范化路径（处理 Docker 路径和 /uploads 路径）
        video_url = normalize_path(video_url)

        if not os.path.exists(video_url):
            raise FileNotFoundError(f"本地文件不存在: {video_url}")

        file_name = os.path.basename(video_url)
        title, _ = os.path.splitext(file_name)
        print(title, file_name,video_url)
        file_path=self.convert_to_mp3(video_url)
        cover_path = self.extract_cover(video_url)
        cover_url = save_cover_to_static(cover_path)

        print('file——path',file_path)
        return AudioDownloadResult(
            file_path=file_path,
            title=title,
            duration=0,  # 可选：后续加上读取时长
            cover_url=cover_url,  # 暂无封面
            platform="local",
            video_id=title,
            raw_info={
                'path':  file_path
            },
            video_path=None,
            video_url=video_url  # 保存原始路径
        )
