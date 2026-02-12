"""
GPT 工厂类
根据配置创建对应的 GPT 实例
"""
from app.gpt.base import GPT
from app.gpt.provider.openai_compatible_provider import OpenAICompatibleProvider
from app.gpt.provider.anthropic_provider import AnthropicProvider
from app.gpt.universal_gpt import UniversalGPT
from app.gpt.anthropic_gpt import AnthropicGPT
from app.models.model_config import ModelConfig
from app.utils.logger import get_logger

logger = get_logger(__name__)


class GPTFactory:
    @staticmethod
    def from_config(config: ModelConfig) -> GPT:
        """
        根据配置创建对应的 GPT 实例
        支持 OpenAI 兼容 API 和 Anthropic 原生 API
        """
        logger.info(f"[GPTFactory] ========== 创建 GPT 实例 ==========")
        logger.info(f"[GPTFactory] 模型名称: {config.model_name}")
        logger.info(f"[GPTFactory] 供应商名称: {getattr(config, 'name', 'unknown')}")
        logger.info(f"[GPTFactory] Base URL: {config.base_url}")

        provider_type = getattr(config, 'provider_type', None)
        logger.info(f"[GPTFactory] Provider 类型: {provider_type or 'openai-compatible (默认)'}")

        # 检查是否是 Anthropic 类型
        if provider_type == 'anthropic':
            logger.info(f"[GPTFactory] 使用 Anthropic 原生 API")
            try:
                client = AnthropicProvider(
                    api_key=config.api_key,
                    base_url=config.base_url
                ).get_client
                logger.info(f"[GPTFactory] Anthropic 客户端创建成功")
                return AnthropicGPT(client=client, model=config.model_name)
            except Exception as e:
                logger.error(f"[GPTFactory] 创建 Anthropic 客户端失败: {e}", exc_info=True)
                raise

        # 默认使用 OpenAI 兼容 API
        logger.info(f"[GPTFactory] 使用 OpenAI 兼容 API")
        try:
            client = OpenAICompatibleProvider(
                api_key=config.api_key,
                base_url=config.base_url
            ).get_client
            logger.info(f"[GPTFactory] OpenAI 兼容客户端创建成功")
            return UniversalGPT(client=client, model=config.model_name)
        except Exception as e:
            logger.error(f"[GPTFactory] 创建 OpenAI 兼容客户端失败: {e}", exc_info=True)
            raise
