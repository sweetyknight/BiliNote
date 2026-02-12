import time
import functools
from app.utils.logger import get_logger

logger = get_logger(__name__)

def timeit(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        func_name = func.__name__
        module_name = func.__module__
        logger.info(f"[计时] 开始执行 {module_name}.{func_name}")
        start = time.perf_counter()
        try:
            result = func(*args, **kwargs)
            end = time.perf_counter()
            duration = end - start
            logger.info(f"[计时] {module_name}.{func_name} 执行完成，耗时 {duration:.4f} 秒")
            return result
        except Exception as e:
            end = time.perf_counter()
            duration = end - start
            logger.error(f"[计时] {module_name}.{func_name} 执行失败，耗时 {duration:.4f} 秒，错误: {e}")
            raise
    return wrapper
