from typing import Union
from openai import OpenAI
from app.utils.logger import get_logger

logger = get_logger(__name__)


class OpenAICompatibleProvider:
    def __init__(self, api_key: str, base_url: str, model: Union[str, None] = None):
        logger.info(f"[OpenAICompatibleProvider] init: base_url={base_url}")
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        logger.info("[OpenAICompatibleProvider] OpenAI client created")

    @property
    def get_client(self):
        return self.client

    @staticmethod
    def test_connection(api_key: str, base_url: str) -> bool:
        logger.info(f"[OpenAICompatibleProvider] test connection: base_url={base_url}")
        try:
            client = OpenAI(api_key=api_key, base_url=base_url)
            client.models.list()
            logger.info("[OpenAICompatibleProvider] connection test successful")
            return True
        except Exception as e:
            logger.error(f"[OpenAICompatibleProvider] connection test failed: {e}")
            return False
