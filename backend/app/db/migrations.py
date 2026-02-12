"""
数据库迁移脚本
用于添加新字段到已存在的表
"""
import sqlite3
from app.utils.logger import get_logger
from app.db.engine import BACKEND_DIR
from app.services.constant import is_transcriber_model

logger = get_logger(__name__)

# 使用与 engine.py 相同的数据库路径
DB_PATH = BACKEND_DIR / "bili_note.db"


def migrate_add_provider_type():
    """
    为 providers 表添加 provider_type 字段
    """
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()

        # 检查列是否已存在
        cursor.execute("PRAGMA table_info(providers)")
        columns = [column[1] for column in cursor.fetchall()]

        if 'provider_type' not in columns:
            logger.info("添加 provider_type 列到 providers 表")
            cursor.execute("ALTER TABLE providers ADD COLUMN provider_type TEXT DEFAULT 'openai'")
            conn.commit()
            logger.info("provider_type 列添加成功")
        else:
            logger.info("provider_type 列已存在，跳过迁移")

        conn.close()
        return True
    except Exception as e:
        logger.error(f"迁移失败: {e}")
        return False


def migrate_add_model_type():
    """
    为 models 表添加 model_type 字段，并根据模型名称自动设置类型
    """
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()

        # 检查列是否已存在
        cursor.execute("PRAGMA table_info(models)")
        columns = [column[1] for column in cursor.fetchall()]

        if 'model_type' not in columns:
            logger.info("添加 model_type 列到 models 表")
            cursor.execute("ALTER TABLE models ADD COLUMN model_type TEXT DEFAULT 'llm'")
            conn.commit()
            logger.info("model_type 列添加成功")
            
            # 更新现有模型的类型
            _update_existing_model_types(cursor, conn)
        else:
            logger.info("model_type 列已存在，跳过迁移")

        conn.close()
        return True
    except Exception as e:
        logger.error(f"迁移 model_type 失败: {e}")
        return False


def _update_existing_model_types(cursor, conn):
    """
    根据模型名称更新现有模型的类型
    """
    try:
        # 获取所有模型
        cursor.execute("SELECT id, model_name FROM models")
        models = cursor.fetchall()
        
        updated_count = 0
        for model_id, model_name in models:
            model_type = 'transcriber' if is_transcriber_model(model_name) else 'llm'
            cursor.execute(
                "UPDATE models SET model_type = ? WHERE id = ?",
                (model_type, model_id)
            )
            if model_type == 'transcriber':
                logger.info(f"模型 {model_name} (ID: {model_id}) 被标记为转写模型")
                updated_count += 1
        
        conn.commit()
        logger.info(f"现有模型类型更新完成，共标记 {updated_count} 个转写模型")
    except Exception as e:
        logger.error(f"更新现有模型类型失败: {e}")


def run_migrations():
    """
    运行所有迁移
    """
    logger.info("开始数据库迁移")
    migrate_add_provider_type()
    migrate_add_model_type()
    logger.info("数据库迁移完成")
