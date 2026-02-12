from app.db.models.models import Model
from app.db.models.providers import Provider
from app.db.models.video_tasks import VideoTask
from app.db.engine import get_engine, Base
from app.utils.logger import get_logger

logger = get_logger(__name__)


def init_db():
    engine = get_engine()

    Base.metadata.create_all(bind=engine)

    # 运行数据库迁移
    try:
        from app.db.migrations import run_migrations
        run_migrations()
    except Exception as e:
        logger.error(f"数据库迁移失败: {e}", exc_info=True)