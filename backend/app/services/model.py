

from app.db.model_dao import insert_model, get_all_models, get_model_by_provider_and_name, delete_model
from app.db.provider_dao import get_enabled_providers
from app.enmus.exception import ProviderErrorEnum
from app.exceptions.provider import ProviderError
from app.gpt.gpt_factory import GPTFactory
from app.gpt.provider.openai_compatible_provider import OpenAICompatibleProvider
from app.models.model_config import ModelConfig
from app.services.provider import ProviderService
from app.services.constant import is_transcriber_model
from app.utils.logger import get_logger

logger=get_logger(__name__)
class ModelService:

    @staticmethod
    def _build_model_config(provider: dict) -> ModelConfig:
        return ModelConfig(
            api_key=provider["api_key"],
            base_url=provider["base_url"],
            provider=provider["name"],
            model_name='',
            name=provider["name"],
            provider_type=provider.get("provider_type", "openai"),
        )

    @staticmethod
    def get_model_list(provider_id: int, verbose: bool = False):
        provider = ProviderService.get_provider_by_id(provider_id)
        if not provider:
            return []

        try:
            config = ModelService._build_model_config(provider)
            gpt = GPTFactory().from_config(config)
            models = gpt.list_models()
            if verbose:
                print(f"[{provider['name']}] 模型列表: {models}")
            return models
        except Exception as e:
            print(f"[{provider['name']}] 获取模型失败: {e}")
            return []

    @staticmethod
    def get_all_models(verbose: bool = False, model_type: str = 'llm'):
        """
        获取所有模型列表
        
        Args:
            verbose: 是否输出详细日志
            model_type: 模型类型过滤，'llm' 或 'transcriber'，默认只返回 LLM 模型
        """
        try:
            raw_models = get_all_models(model_type=model_type)
            if verbose:
                print(f"所有模型列表: {raw_models}")
            return ModelService._format_models(raw_models)
        except Exception as e:
            print(f"获取所有模型失败: {e}")
            return []
    @staticmethod
    def get_all_models_safe(verbose: bool = False, model_type: str = 'llm'):
        """
        获取所有模型列表（安全版本）
        
        Args:
            verbose: 是否输出详细日志
            model_type: 模型类型过滤，'llm' 或 'transcriber'，默认只返回 LLM 模型
        """
        try:
            raw_models = get_all_models(model_type=model_type)
            if verbose:
                print(f"所有模型列表: {raw_models}")
            return ModelService._format_models(raw_models)
        except Exception as e:
            print(f"获取所有模型失败: {e}")
            return []
    @staticmethod
    def _format_models(raw_models: list) -> list:
        """
        格式化模型列表
        """
        formatted = []
        for model in raw_models:
            formatted.append({
                "id": model.get("id"),
                "provider_id": model.get("provider_id"),
                "model_name": model.get("model_name"),
                "created_at": model.get("created_at", None),  # 如果有created_at字段
            })
        return formatted
    @staticmethod
    def get_enabled_models_by_provider( provider_id: str|int,):
        from app.db.model_dao import get_models_by_provider

        all_models = get_models_by_provider(provider_id)
        enabled_models = all_models
        return enabled_models
    @staticmethod
    def get_all_models_by_id(provider_id: str, verbose: bool = False):
        try:
            provider = ProviderService.get_provider_by_id(provider_id)

            models = ModelService.get_model_list(provider["id"], verbose=verbose)
            logger.debug(f"[{provider['name']}] 模型列表类型: {type(models)}")

            # 处理不同的返回类型
            if isinstance(models, list):
                # 如果返回空列表，直接返回
                if not models:
                    logger.warning(f"[{provider['name']}] 模型列表为空")
                    return {"models": []}
                serializable_models = models
            elif hasattr(models, 'data'):
                # 如果有 data 属性（ModelList 或 SyncPage 对象）
                try:
                    # 尝试将 SyncPage 对象转换为列表
                    model_list = list(models.data) if hasattr(models.data, '__iter__') else models.data
                    # 尝试使用 model_dump() 方法（Pydantic v2）
                    serializable_models = [
                        m.model_dump() if hasattr(m, 'model_dump') 
                        else (dict(m) if hasattr(m, '__dict__') else {
                            "id": getattr(m, 'id', str(m)),
                            "object": getattr(m, 'object', 'model'),
                            "created": getattr(m, 'created', 0),
                            "owned_by": getattr(m, 'owned_by', ''),
                        })
                        for m in model_list
                    ]
                except Exception as e:
                    logger.warning(f"[{provider['name']}] 使用 model_dump() 失败，尝试直接转换: {e}")
                    # 如果 model_dump() 失败，尝试直接转换为字典
                    try:
                        model_list = list(models.data) if hasattr(models.data, '__iter__') else models.data
                        serializable_models = [
                            dict(m) if hasattr(m, '__dict__') else {
                                "id": getattr(m, 'id', str(m)),
                                "object": getattr(m, 'object', 'model'),
                                "created": getattr(m, 'created', 0),
                                "owned_by": getattr(m, 'owned_by', ''),
                            }
                            for m in model_list
                        ]
                    except Exception as e2:
                        logger.error(f"[{provider['name']}] 转换模型对象失败: {e2}")
                        # 最后尝试：直接使用对象属性
                        model_list = list(models.data) if hasattr(models.data, '__iter__') else models.data
                        serializable_models = [
                            {
                                "id": getattr(m, 'id', str(m)),
                                "object": getattr(m, 'object', 'model'),
                                "created": getattr(m, 'created', 0),
                                "owned_by": getattr(m, 'owned_by', ''),
                            }
                            for m in model_list
                        ]
            elif hasattr(models, '__iter__') and not isinstance(models, (str, bytes)):
                # 如果可以直接迭代（如 SyncPage 对象）
                try:
                    # 尝试将可迭代对象转换为列表
                    model_list = list(models)
                    serializable_models = [
                        m.model_dump() if hasattr(m, 'model_dump') 
                        else (dict(m) if hasattr(m, '__dict__') else {
                            "id": getattr(m, 'id', str(m)),
                            "object": getattr(m, 'object', 'model'),
                            "created": getattr(m, 'created', 0),
                            "owned_by": getattr(m, 'owned_by', ''),
                        })
                        for m in model_list
                    ]
                except Exception as e:
                    logger.warning(f"[{provider['name']}] 迭代转换失败，尝试其他方法: {e}")
                    try:
                        model_list = list(models)
                        serializable_models = [
                            dict(m) if hasattr(m, '__dict__') else {
                                "id": getattr(m, 'id', str(m)),
                                "object": getattr(m, 'object', 'model'),
                                "created": getattr(m, 'created', 0),
                                "owned_by": getattr(m, 'owned_by', ''),
                            }
                            for m in model_list
                        ]
                    except Exception as e2:
                        logger.error(f"[{provider['name']}] 迭代转换模型对象失败: {e2}")
                        serializable_models = []
            else:
                logger.error(f"[{provider['name']}] 未知的模型列表格式: {type(models)}")
                return {"models": []}

            # 过滤掉转写模型（如 whisper），只保留 LLM 模型
            original_count = len(serializable_models)
            serializable_models = [
                m for m in serializable_models 
                if not is_transcriber_model(m.get('id', '') if isinstance(m, dict) else getattr(m, 'id', ''))
            ]
            filtered_count = original_count - len(serializable_models)
            if filtered_count > 0:
                logger.info(f"[{provider['name']}] 已过滤 {filtered_count} 个转写模型")

            model_list = {
                "models": serializable_models
            }

            logger.info(f"[{provider['name']}] 获取模型成功，共 {len(serializable_models)} 个 LLM 模型")
            return model_list
        except Exception as e:
            logger.error(f"[{provider_id}] 获取模型失败: {e}", exc_info=True)
            return {"models": []}
    @staticmethod
    def connect_test(id: str) -> bool:

        provider = ProviderService.get_provider_by_id(id)

        if provider:
            if not provider.get('api_key'):
                raise ProviderError(code=ProviderErrorEnum.NOT_FOUND.code, message=ProviderErrorEnum.NOT_FOUND.message)

            provider_type = provider.get('provider_type', 'openai')

            if provider_type == 'anthropic':
                # 使用 Anthropic 原生 API 测试
                from app.gpt.provider.anthropic_provider import AnthropicProvider
                result = AnthropicProvider.test_connection(
                    api_key=provider.get('api_key'),
                    base_url=provider.get('base_url')
                )
            else:
                # 使用 OpenAI 兼容 API 测试
                result = OpenAICompatibleProvider.test_connection(
                    api_key=provider.get('api_key'),
                    base_url=provider.get('base_url')
                )

            if result:
                return True
            else:
                raise ProviderError(code=ProviderErrorEnum.WRONG_PARAMETER.code,message=ProviderErrorEnum.WRONG_PARAMETER.message)

        raise ProviderError(code=ProviderErrorEnum.NOT_FOUND.code, message=ProviderErrorEnum.NOT_FOUND.message)



    @staticmethod
    def delete_model_by_id( model_id: int) -> bool:
        try:
            delete_model(model_id)
            return True
        except Exception as e:
            print(f"[{model_id}] <UNK>: {e}")
            return False
    @staticmethod
    def add_new_model(provider_id: int, model_name: str) -> bool:
        try:
            # 先查供应商是否存在
            provider = ProviderService.get_provider_by_id(provider_id)
            if not provider:
                print(f"供应商ID {provider_id} 不存在，无法添加模型")
                return False

            # 查询是否已存在同名模型
            existing = get_model_by_provider_and_name(provider_id, model_name)
            if existing:
                print(f"模型 {model_name} 已存在于供应商ID {provider_id} 下，跳过插入")
                return False

            # 自动识别模型类型
            model_type = 'transcriber' if is_transcriber_model(model_name) else 'llm'
            logger.info(f"添加模型 {model_name}，识别为类型: {model_type}")

            # 插入模型
            insert_model(provider_id=provider_id, model_name=model_name, model_type=model_type)
            print(f"模型 {model_name} (类型: {model_type}) 已成功添加到供应商ID {provider_id}")
            return True
        except Exception as e:
            print(f"添加模型失败: {e}")
            return False

if __name__ == '__main__':
    # 单个 Provider 测试
    print(ModelService.get_model_list(1, verbose=True))

    # 所有 Provider 模型测试
    # print(ModelService.get_all_models(verbose=True))
