import base64
import os
import re
import subprocess
import ffmpeg
from PIL import Image, ImageDraw, ImageFont
from typing import Optional, Tuple, List

from app.utils.logger import get_logger
from app.utils.path_helper import get_app_dir

logger = get_logger(__name__)


# 图片密度配置
# - economy: 节省模式，适合生活/娱乐类视频，节省 API 成本
# - standard: 标准模式，平衡覆盖率和成本
# - high: 高密度模式，适合教程/学术类视频，确保不遗漏细节
IMAGE_DENSITY_CONFIGS = {
    "economy": {
        "multiplier": 0.7,
        "description": "节省模式 - 适合生活/娱乐类视频"
    },
    "standard": {
        "multiplier": 1.0,
        "description": "标准模式 - 平衡覆盖率和成本"
    },
    "high": {
        "multiplier": 1.5,
        "description": "高密度模式 - 适合教程/学术类视频"
    },
    "ultra": {
        "multiplier": 2.0,
        "description": "超高密度模式 - 适合代码演示/操作教程"
    }
}


def get_optimal_video_params(duration: float, density: str = "standard") -> dict:
    """
    根据视频时长和密度配置返回最优采样参数
    
    :param duration: 视频时长（秒）
    :param density: 图片密度级别 ("economy" | "standard" | "high" | "ultra")
    :return: 包含 frame_interval, grid_size, max_images 的字典
    """
    # 获取密度倍数
    density_config = IMAGE_DENSITY_CONFIGS.get(density, IMAGE_DENSITY_CONFIGS["standard"])
    multiplier = density_config["multiplier"]
    
    # 基础配置（标准模式）
    if duration <= 300:  # 5分钟以内
        base_config = {
            "frame_interval": 3,
            "grid_size": (3, 3),
            "max_images": 10
        }
    elif duration <= 900:  # 15分钟以内
        base_config = {
            "frame_interval": 4,
            "grid_size": (3, 3),
            "max_images": 14
        }
    elif duration <= 1800:  # 30分钟以内
        base_config = {
            "frame_interval": 5,
            "grid_size": (4, 4),
            "max_images": 18
        }
    elif duration <= 3600:  # 1小时以内
        base_config = {
            "frame_interval": 6,
            "grid_size": (4, 4),
            "max_images": 24
        }
    elif duration <= 7200:  # 2小时以内
        base_config = {
            "frame_interval": 8,
            "grid_size": (4, 4),
            "max_images": 32
        }
    else:  # 超长视频 (>2小时)
        # 动态计算：确保覆盖率 >= 85%
        grid_frames = 16  # 4x4 网格
        target_coverage = 0.85
        max_images = 40
        frame_interval = int(duration * target_coverage / (max_images * grid_frames))
        frame_interval = max(8, min(frame_interval, 20))
        base_config = {
            "frame_interval": frame_interval,
            "grid_size": (4, 4),
            "max_images": max_images
        }
    
    # 根据密度倍数调整
    adjusted_max_images = int(base_config["max_images"] * multiplier)
    # 调整帧间隔（密度越高，间隔越小）
    adjusted_interval = max(2, int(base_config["frame_interval"] / multiplier))
    
    result = {
        "frame_interval": adjusted_interval,
        "grid_size": base_config["grid_size"],
        "max_images": adjusted_max_images
    }
    
    logger.info(f"[VideoParams] 时长={duration:.0f}s, 密度={density}, 配置={result}")
    return result


def get_density_for_style(style: str) -> str:
    """
    根据笔记风格自动选择图片密度
    
    :param style: 笔记风格
    :return: 图片密度级别
    
    密度说明：
    - ultra: 代码演示、操作教程（需要捕捉每个操作细节）
    - high: 教程、学术、详细笔记（默认，平衡准确性和成本）
    - standard: 商业、会议纪要（中等密度）
    - economy: 生活娱乐类（低密度节省成本）
    """
    # 需要超高密度的风格（代码演示、操作教程）
    ultra_density_styles = {'tutorial'}
    # 需要高密度的风格（学术、详细、任务导向）
    high_density_styles = {'detailed', 'academic', 'task_oriented'}
    # 标准密度（商业、会议）
    standard_density_styles = {'business', 'meeting_minutes'}
    # 可以用低密度的风格（生活、娱乐）
    low_density_styles = {'life_journal', 'xiaohongshu', 'minimal'}
    
    if style in ultra_density_styles:
        return "ultra"
    elif style in high_density_styles:
        return "high"
    elif style in standard_density_styles:
        return "standard"
    elif style in low_density_styles:
        return "economy"
    else:
        return "high"  # 默认使用高密度，提高准确性
class VideoReader:
    def __init__(self,
                 video_path: str,
                 grid_size=(3, 3),
                 frame_interval=2,
                 unit_width=960,
                 unit_height=540,
                 save_quality=90,
                 font_path="fonts/arial.ttf",
                 frame_dir=None,
                 grid_dir=None,
                 smart_sampling: bool = True,
                 change_threshold: float = 0.15,  # 场景变化检测阈值，值越小越敏感（保留更多帧）
                 auto_params: bool = True,
                 density: str = "high",  # 默认高密度模式，提高准确性
                 style: str = None):
        """
        初始化 VideoReader
        :param video_path: 视频文件路径
        :param grid_size: 网格尺寸，如 (3, 3)，设为 (0,0) 表示自动
        :param frame_interval: 帧提取间隔（秒），设为 0 表示自动
        :param unit_width: 单帧宽度
        :param unit_height: 单帧高度
        :param save_quality: 保存质量
        :param font_path: 字体路径
        :param frame_dir: 帧保存目录
        :param grid_dir: 网格图保存目录
        :param smart_sampling: 是否启用智能采样（跳过相似帧）
        :param change_threshold: 场景变化阈值 (0-1)，值越小越敏感
        :param auto_params: 是否根据视频时长自动调整参数
        :param density: 图片密度级别 ("economy" | "standard" | "high" | "ultra")
        :param style: 笔记风格，用于自动选择密度（如果 density 未指定）
        """
        self.video_path = video_path
        self.smart_sampling = smart_sampling
        self.change_threshold = change_threshold
        self.auto_params = auto_params
        
        # 如果提供了 style，根据风格自动调整密度（覆盖默认值）
        if style:
            style_density = get_density_for_style(style)
            logger.info(f"📊 根据笔记风格 '{style}' 自动选择密度: {style_density}")
            density = style_density
        
        self.density = density
        
        # 获取视频时长并自动调整参数
        self.duration = self._get_video_duration()
        
        # 判断是否需要自动调整：
        # - grid_size 为 (0, 0) 或 frame_interval 为 0 表示用户选择"自动"
        # - auto_params=True 且有视频时长时启用自动优化
        is_auto_grid = grid_size == (0, 0) or grid_size[0] == 0 or grid_size[1] == 0
        is_auto_interval = frame_interval == 0
        
        if auto_params and self.duration and (is_auto_grid or is_auto_interval):
            optimal = get_optimal_video_params(self.duration, density)
            # 如果用户选择自动（值为0），使用最优参数；否则使用用户设置的值
            self.grid_size = optimal["grid_size"] if is_auto_grid else grid_size
            self.frame_interval = optimal["frame_interval"] if is_auto_interval else frame_interval
            self.max_images = optimal["max_images"]
            logger.info(f"📊 自动参数优化: 视频时长={self.duration:.0f}s, 密度={density}, interval={self.frame_interval}s, grid={self.grid_size}, max_images={self.max_images}")
        elif auto_params and self.duration:
            # 用户手动设置了所有参数
            optimal = get_optimal_video_params(self.duration, density)
            self.grid_size = grid_size
            self.frame_interval = frame_interval
            self.max_images = optimal["max_images"]
            logger.info(f"📊 手动参数设置: 视频时长={self.duration:.0f}s, 密度={density}, interval={self.frame_interval}s, grid={self.grid_size}, max_images={self.max_images}")
        else:
            self.grid_size = grid_size if not is_auto_grid else (3, 3)  # 无法自动时使用默认值
            self.frame_interval = frame_interval if not is_auto_interval else 4
            self.max_images = 10
        
        self.unit_width = unit_width
        self.unit_height = unit_height
        self.save_quality = save_quality
        self.frame_dir = frame_dir or get_app_dir("output_frames")
        self.grid_dir = grid_dir or get_app_dir("grid_output")
        logger.info(f"视频路径：{video_path}, frame_dir={self.frame_dir}, grid_dir={self.grid_dir}")
        self.font_path = font_path
    
    def _get_video_duration(self) -> Optional[float]:
        """获取视频时长"""
        try:
            probe = ffmpeg.probe(self.video_path)
            return float(probe["format"]["duration"])
        except Exception as e:
            logger.warning(f"获取视频时长失败: {e}")
            return None

    def format_time(self, seconds: float) -> str:
        mm = int(seconds // 60)
        ss = int(seconds % 60)
        return f"{mm:02d}_{ss:02d}"

    def extract_time_from_filename(self, filename: str) -> float:
        match = re.search(r"frame_(\d{2})_(\d{2})\.jpg", filename)
        if match:
            mm, ss = map(int, match.groups())
            return mm * 60 + ss
        return float('inf')

    def _compute_frame_histogram(self, frame_path: str) -> Optional[List[float]]:
        """
        计算帧的颜色直方图用于相似度比较
        :param frame_path: 帧图片路径
        :return: 归一化的直方图列表
        """
        try:
            with Image.open(frame_path) as img:
                # 缩小图片加速计算
                img_small = img.resize((64, 64), Image.Resampling.LANCZOS).convert("RGB")
                # 计算简单的颜色直方图
                histogram = img_small.histogram()
                # 归一化
                total = sum(histogram)
                if total > 0:
                    histogram = [h / total for h in histogram]
                return histogram
        except Exception as e:
            logger.warning(f"计算直方图失败 ({frame_path}): {e}")
            return None

    def _histogram_similarity(self, hist1: List[float], hist2: List[float]) -> float:
        """
        计算两个直方图的相似度 (余弦相似度)
        :return: 相似度 0-1，1表示完全相同
        """
        if not hist1 or not hist2 or len(hist1) != len(hist2):
            return 0.0
        
        dot_product = sum(a * b for a, b in zip(hist1, hist2))
        norm1 = sum(a * a for a in hist1) ** 0.5
        norm2 = sum(b * b for b in hist2) ** 0.5
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return dot_product / (norm1 * norm2)

    def extract_frames(self, max_frames=1000) -> list[str]:
        """
        提取视频帧，支持智能采样模式
        
        智能采样策略（优化版）：
        1. 保证最小帧数：至少能组成 1 个网格 + 备用帧
        2. 定期强制保留关键帧：保证时间均匀覆盖
        3. 保留首尾帧：不管相似度如何
        4. 动态阈值：如果跳过太多，自动放宽阈值
        5. 最大跳过限制：连续跳过帧数有上限
        """
        try:
            os.makedirs(self.frame_dir, exist_ok=True)
            duration = self.duration or float(ffmpeg.probe(self.video_path)["format"]["duration"])
            timestamps = [i for i in range(0, int(duration), self.frame_interval)][:max_frames]
            
            # 计算最小需要保留的帧数（至少能组成 1.5 个网格，留有余量）
            grid_size_total = self.grid_size[0] * self.grid_size[1]
            min_required_frames = max(grid_size_total + (grid_size_total // 2), int(len(timestamps) * 0.15))
            
            # 强制保留帧的间隔：确保时间均匀覆盖
            # 按最小帧数计算，每隔多少帧至少保留一帧
            force_keep_interval = max(1, len(timestamps) // min_required_frames) if len(timestamps) > 0 else 1
            
            # 最大连续跳过帧数限制（防止长时间没有帧）
            max_consecutive_skip = max(3, force_keep_interval - 1)
            
            logger.info(f"📊 智能采样参数: min_frames={min_required_frames}, force_interval={force_keep_interval}, max_skip={max_consecutive_skip}")
            
            image_paths = []
            prev_histogram = None
            skipped_count = 0
            consecutive_skipped = 0
            
            for idx, ts in enumerate(timestamps):
                time_label = self.format_time(ts)
                output_path = os.path.join(self.frame_dir, f"frame_{time_label}.jpg")
                cmd = ["ffmpeg", "-ss", str(ts), "-i", self.video_path, "-frames:v", "1", "-q:v", "2", "-y", output_path,
                       "-hide_banner", "-loglevel", "error"]
                subprocess.run(cmd, check=True)
                
                # 判断是否需要强制保留
                is_first_frame = (idx == 0)
                is_last_frame = (idx == len(timestamps) - 1)
                is_force_keep_point = (idx % force_keep_interval == 0)
                reached_max_skip = (consecutive_skipped >= max_consecutive_skip)
                
                force_keep = is_first_frame or is_last_frame or is_force_keep_point or reached_max_skip
                
                # 智能采样：跳过与前一帧相似的帧（但受强制保留规则约束）
                should_keep = force_keep  # 默认：强制保留的帧一定保留
                
                if self.smart_sampling and prev_histogram is not None and not force_keep:
                    current_histogram = self._compute_frame_histogram(output_path)
                    if current_histogram:
                        similarity = self._histogram_similarity(prev_histogram, current_histogram)
                        # 动态阈值：根据已保留帧数动态调整
                        # 如果保留的帧太少，放宽阈值
                        current_keep_ratio = len(image_paths) / max(1, idx)
                        target_keep_ratio = min_required_frames / max(1, len(timestamps))
                        
                        if current_keep_ratio < target_keep_ratio * 0.8:
                            # 保留率太低，使用更宽松的阈值
                            effective_threshold = self.change_threshold * 0.5
                        else:
                            effective_threshold = self.change_threshold
                        
                        if similarity > (1 - effective_threshold):
                            # 帧太相似，删除并跳过
                            os.remove(output_path)
                            skipped_count += 1
                            consecutive_skipped += 1
                            continue
                        # 保留此帧，更新直方图
                        prev_histogram = current_histogram
                        should_keep = True
                    else:
                        # 无法计算直方图，默认保留
                        should_keep = True
                else:
                    # 第一帧或强制保留帧，更新直方图基准
                    prev_histogram = self._compute_frame_histogram(output_path)
                    should_keep = True
                
                image_paths.append(output_path)
                consecutive_skipped = 0  # 重置连续跳过计数
            
            if self.smart_sampling:
                keep_ratio = len(image_paths) / len(timestamps) * 100 if timestamps else 0
                logger.info(f"🧠 智能采样完成: 原始帧数={len(timestamps)}, 保留={len(image_paths)} ({keep_ratio:.1f}%), 跳过={skipped_count}")
            
            # 如果保留的帧数仍然不足，记录警告
            if len(image_paths) < grid_size_total:
                logger.warning(f"⚠️ 保留帧数 ({len(image_paths)}) 少于网格所需 ({grid_size_total})，建议检查视频或调整参数")
            
            return image_paths
        except Exception as e:
            logger.error(f"分割帧发生错误：{str(e)}")
            raise ValueError("视频处理失败")

    def group_images(self) -> list[list[str]]:
        image_files = [os.path.join(self.frame_dir, f) for f in os.listdir(self.frame_dir) if
                       f.startswith("frame_") and f.endswith(".jpg")]
        image_files.sort(key=lambda f: self.extract_time_from_filename(os.path.basename(f)))
        group_size = self.grid_size[0] * self.grid_size[1]
        return [image_files[i:i + group_size] for i in range(0, len(image_files), group_size)]

    def concat_images(self, image_paths: list[str], name: str, allow_partial: bool = True) -> str:
        """
        将多张图片拼接成网格图
        
        :param image_paths: 图片路径列表
        :param name: 输出文件名（不含扩展名）
        :param allow_partial: 是否允许不完整网格（用灰色填充空位）
        :return: 网格图保存路径
        """
        os.makedirs(self.grid_dir, exist_ok=True)
        font = ImageFont.truetype(self.font_path, 48) if os.path.exists(self.font_path) else ImageFont.load_default()
        images = []

        for path in image_paths:
            img = Image.open(path).convert("RGB").resize((self.unit_width, self.unit_height), Image.Resampling.LANCZOS)
            timestamp = re.search(r"frame_(\d{2})_(\d{2})\.jpg", os.path.basename(path))
            time_text = f"{timestamp.group(1)}:{timestamp.group(2)}" if timestamp else ""
            draw = ImageDraw.Draw(img)
            draw.text((10, 10), time_text, fill="yellow", font=font, stroke_width=1, stroke_fill="black")
            images.append(img)

        cols, rows = self.grid_size
        # 使用浅灰色背景（区分空位和图片内容）
        grid_img = Image.new("RGB", (self.unit_width * cols, self.unit_height * rows), (240, 240, 240))

        for i, img in enumerate(images):
            x = (i % cols) * self.unit_width
            y = (i // cols) * self.unit_height
            grid_img.paste(img, (x, y))

        save_path = os.path.join(self.grid_dir, f"{name}.jpg")
        grid_img.save(save_path, quality=self.save_quality)
        return save_path

    def encode_images_to_base64(self, image_paths: list[str], max_images: Optional[int] = None, max_width: int = 1440, quality: int = 60) -> list[str]:
        """
        将图片编码为 Base64，同时压缩以减小 payload 大小
        :param image_paths: 图片路径列表
        :param max_images: 最多编码的图片数量，None 则使用自动计算的值
        :param max_width: 最大宽度（默认 1440，会按比例缩放）
        :param quality: JPEG 压缩质量（默认 60，范围 1-100）
        :return: Base64 编码的图片列表
        """
        import io
        
        # 使用自动参数或传入的值
        max_images = max_images or self.max_images
        
        # 限制图片数量，避免 API 请求过大
        if len(image_paths) > max_images:
            logger.warning(f"⚠️ 图片数量 ({len(image_paths)}) 超过限制 ({max_images})，将均匀采样")
            # 均匀采样
            step = len(image_paths) / max_images
            image_paths = [image_paths[int(i * step)] for i in range(max_images)]
            logger.info(f"✅ 采样后图片数量: {len(image_paths)}")

        base64_images = []
        total_size = 0
        for idx, path in enumerate(image_paths, 1):
            try:
                # 打开并压缩图片
                with Image.open(path) as img:
                    # 按比例缩放
                    if img.width > max_width:
                        ratio = max_width / img.width
                        new_size = (max_width, int(img.height * ratio))
                        img = img.resize(new_size, Image.Resampling.LANCZOS)
                    
                    # 转换为 JPEG 并压缩
                    buffer = io.BytesIO()
                    img.convert("RGB").save(buffer, format="JPEG", quality=quality, optimize=True)
                    img_bytes = buffer.getvalue()
                    total_size += len(img_bytes)
                    
                    encoded_string = base64.b64encode(img_bytes).decode("utf-8")
                    base64_images.append(f"data:image/jpeg;base64,{encoded_string}")
                    logger.debug(f"✅ 编码图片 {idx}/{len(image_paths)}: {os.path.basename(path)}, 大小: {len(img_bytes)/1024:.1f}KB")
            except Exception as e:
                logger.error(f"❌ 编码图片失败 ({path}): {e}")
                continue

        logger.info(f"✅ 图片编码完成，共 {len(base64_images)} 张，总大小: {total_size/1024/1024:.2f}MB")
        return base64_images

    def run(self) -> list[str]:
        """
        执行视频帧提取、智能筛选、网格拼图、Base64编码的完整流程
        :return: Base64 编码的图片 URL 列表
        """
        logger.info("🎬 开始视频理解处理...")
        logger.info(f"📋 配置: smart_sampling={self.smart_sampling}, change_threshold={self.change_threshold}, auto_params={self.auto_params}")
        
        try:
            # 确保目录存在
            os.makedirs(self.frame_dir, exist_ok=True)
            os.makedirs(self.grid_dir, exist_ok=True)
            
            # 清空帧文件夹
            for file in os.listdir(self.frame_dir):
                if file.startswith("frame_"):
                    os.remove(os.path.join(self.frame_dir, file))
            
            # 清空网格文件夹
            for file in os.listdir(self.grid_dir):
                if file.startswith("grid_"):
                    os.remove(os.path.join(self.grid_dir, file))
            
            # 提取帧（包含智能采样）
            logger.info("🖼️ 开始提取视频帧...")
            self.extract_frames()
            
            # 拼接网格图
            logger.info("🔲 开始拼接网格图...")
            image_paths = []
            groups = self.group_images()
            grid_size_total = self.grid_size[0] * self.grid_size[1]
            
            # 计算最小可接受的帧数（至少需要半个网格的内容才有意义）
            min_acceptable = max(grid_size_total // 2, 3)
            
            for idx, group in enumerate(groups, start=1):
                if len(group) < min_acceptable:
                    logger.warning(f"⚠️ 跳过第 {idx} 组，图片太少 ({len(group)} 张，最少需要 {min_acceptable} 张)")
                    continue
                if len(group) < grid_size_total:
                    logger.info(f"📦 第 {idx} 组图片不足 {grid_size_total} 张 (实际 {len(group)} 张)，将用空位填充")
                out_path = self.concat_images(group, f"grid_{idx}", allow_partial=True)
                image_paths.append(out_path)

            logger.info(f"📤 开始编码图像，网格图数量: {len(image_paths)}")
            urls = self.encode_images_to_base64(image_paths)
            logger.info(f"✅ 视频理解处理完成，返回 {len(urls)} 张图片")
            return urls
        except Exception as e:
            logger.error(f"❌ 视频处理失败: {str(e)}")
            raise ValueError("视频处理失败")


