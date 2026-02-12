import os
import sys
from pathlib import Path

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))


def normalize_path(path: str) -> str:
    """
    规范化路径，处理以下情况：
    1. Docker 容器路径 /app/data/... -> PROJECT_ROOT/data/...
    2. /uploads/... -> PROJECT_ROOT/uploads/...
    3. Windows 绝对路径（在 Docker 容器内运行时）-> 容器内路径
    
    :param path: 原始路径（可能是 Docker 路径、Windows 路径或本地路径）
    :return: 规范化后的路径
    """
    if not path:
        return path
    
    # 检测是否是 Windows 风格的绝对路径 (如 D:\BiliNote\backend\data\...)
    # 当在 Docker 容器（Linux）内运行时，需要转换 Windows 路径
    is_windows_path = len(path) > 2 and path[1] == ':' and (path[2] == '\\' or path[2] == '/')
    
    if is_windows_path:
        # 在 Docker 容器内运行，需要将 Windows 路径转换为容器内路径
        # 统一使用正斜杠
        normalized = path.replace('\\', '/')
        
        # 尝试提取 backend/data/ 后面的相对路径
        # 支持多种可能的路径格式
        markers = ['backend/data/', 'BiliNote/backend/data/']
        for marker in markers:
            idx = normalized.lower().find(marker.lower())
            if idx != -1:
                # 找到标记，提取相对路径
                relative_path = normalized[idx + len(marker):]
                # 转换为容器内路径 /app/data/...
                container_path = os.path.join('/app/data', relative_path)
                # 检查容器内路径是否存在
                if os.path.exists(container_path):
                    return container_path
                # 同时检查 PROJECT_ROOT/data/... 是否存在（本地开发模式）
                local_path = os.path.join(PROJECT_ROOT, 'data', relative_path)
                if os.path.exists(local_path):
                    return local_path
                # 如果都不存在，根据当前环境返回
                # 检测是否在 Docker 容器内（/app 目录存在）
                if os.path.exists('/app'):
                    return container_path
                return local_path
        
        # 没有找到 backend/data/ 标记，尝试其他处理
        # 检查是否是 backend 目录下的其他文件
        backend_marker = 'backend/'
        idx = normalized.lower().find(backend_marker.lower())
        if idx != -1:
            relative_path = normalized[idx + len(backend_marker):]
            container_path = os.path.join('/app', relative_path)
            if os.path.exists(container_path):
                return container_path
            local_path = os.path.join(PROJECT_ROOT, relative_path)
            if os.path.exists(local_path):
                return local_path
            if os.path.exists('/app'):
                return container_path
            return local_path
    
    # 处理 Docker 容器路径 /app/data/...
    if path.startswith('/app/data/'):
        relative_path = path[len('/app/data/'):]
        path = os.path.join(PROJECT_ROOT, 'data', relative_path)
        path = os.path.normpath(path)
    # 处理 /uploads/... 路径
    elif path.startswith('/uploads'):
        path = os.path.join(os.getcwd(), path.lstrip('/'))
        path = os.path.normpath(path)
    
    return path


def get_data_dir():
    if getattr(sys, 'frozen', False):

        base_dir = os.path.dirname(sys.executable)
    else:

        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../data"))

    data_path = os.path.join(base_dir, "data")
    os.makedirs(data_path, exist_ok=True)
    return data_path


def get_model_dir(subdir: str = "whisper") -> str:
    # 判断是否为打包状态（PyInstaller）
    if getattr(sys, 'frozen', False):
        # exe 执行，放在 APPDATA 或 ~/.cache 下
        base_dir = os.path.join(os.getenv("APPDATA") or str(Path.home()), "BiliNote", "models")
    else:
        # 开发时，相对项目根目录
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../models"))

    path = os.path.join(base_dir, subdir)
    os.makedirs(path, exist_ok=True)
    return path


def get_app_dir(subdir: str = "") -> str:
    """
    返回一个稳定的可写目录：
    - 开发时：使用项目 data 目录
    - 打包后：使用 exe 所在目录
    """
    if getattr(sys, 'frozen', False):
        # 打包后运行：使用 main.exe 所在目录
        base_dir = os.path.dirname(sys.executable)
    else:
        # 开发模式：使用项目的 /data 目录
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../data"))

    full_path = os.path.join(base_dir, subdir)
    os.makedirs(full_path, exist_ok=True)
    return full_path