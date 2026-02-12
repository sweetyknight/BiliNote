from app.db.engine import get_db
from app.db.models.models import Model


def get_model_by_provider_and_name(provider_id: int, model_name: str):
    db = next(get_db())
    try:
        model = db.query(Model).filter_by(provider_id=provider_id, model_name=model_name).first()
        if model:
            return {
                "id": model.id,
                "provider_id": model.provider_id,
                "model_name": model.model_name,
                "model_type": model.model_type,
                "created_at": model.created_at,
            }
        return None
    finally:
        db.close()


def insert_model(provider_id: int, model_name: str, model_type: str = 'llm'):
    db = next(get_db())
    try:
        model = Model(provider_id=provider_id, model_name=model_name, model_type=model_type)
        db.add(model)
        db.commit()
        db.refresh(model)
        return {
            "id": model.id,
            "provider_id": model.provider_id,
            "model_name": model.model_name,
            "model_type": model.model_type,
            "created_at": model.created_at,
        }
    finally:
        db.close()


def get_models_by_provider(provider_id: int, model_type: str = None):
    """
    获取供应商下的模型列表
    
    Args:
        provider_id: 供应商ID
        model_type: 模型类型过滤，'llm' 或 'transcriber'，None 表示返回所有类型
    """
    db = next(get_db())
    try:
        query = db.query(Model).filter_by(provider_id=provider_id)
        if model_type:
            query = query.filter_by(model_type=model_type)
        models = query.all()
        return [{"id": m.id, "model_name": m.model_name, "model_type": m.model_type} for m in models]
    finally:
        db.close()


def delete_model(model_id: int):
    db = next(get_db())
    try:
        model = db.query(Model).filter_by(id=model_id).first()
        if model:
            db.delete(model)
            db.commit()
    finally:
        db.close()


def get_all_models(model_type: str = None):
    """
    获取所有模型列表
    
    Args:
        model_type: 模型类型过滤，'llm' 或 'transcriber'，None 表示返回所有类型
    """
    db = next(get_db())
    try:
        query = db.query(Model)
        if model_type:
            query = query.filter_by(model_type=model_type)
        models = query.all()
        return [
            {"id": m.id, "provider_id": m.provider_id, "model_name": m.model_name, "model_type": m.model_type}
            for m in models
        ]
    finally:
        db.close()


def update_model_name(model_id: int, new_model_name: str):
    """更新模型名称"""
    db = next(get_db())
    try:
        model = db.query(Model).filter_by(id=model_id).first()
        if model:
            model.model_name = new_model_name
            db.commit()
            return {"id": model.id, "provider_id": model.provider_id, "model_name": model.model_name}
        return None
    finally:
        db.close()


def delete_models_by_provider(provider_id: str):
    """删除供应商下的所有模型"""
    db = next(get_db())
    try:
        models = db.query(Model).filter_by(provider_id=provider_id).all()
        for model in models:
            db.delete(model)
        db.commit()
        return len(models)
    finally:
        db.close()