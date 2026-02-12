"""
Anthropic 原生 API Provider
支持 Claude 模型的原生 API 调用
"""
import requests
import anthropic

from app.utils.logger import get_logger

logger = get_logger(__name__)


class AnthropicProvider:
    """
    Anthropic API 提供者
    用于连接 Anthropic 原生 API（Claude 系列模型）
    """

    def __init__(self, api_key: str, base_url: str = None):
        """
        初始化 Anthropic Provider
        :param api_key: Anthropic API Key
        :param base_url: 可选的自定义 base_url（用于代理服务）
        """
        logger.info(f"[AnthropicProvider] 初始化: base_url={base_url or 'https://api.anthropic.com (默认)'}")
        logger.debug(f"[AnthropicProvider] API Key: {api_key[:8]}...{api_key[-4:] if len(api_key) > 12 else '***'}")

        if base_url:
            # 移除末尾的 /v1（如果有的话），因为 anthropic SDK 会自动添加
            base_url = base_url.rstrip('/')
            if base_url.endswith('/v1'):
                base_url = base_url[:-3]
            logger.debug(f"[AnthropicProvider] 处理后的 base_url: {base_url}")
            self.client = anthropic.Anthropic(api_key=api_key, base_url=base_url)
        else:
            self.client = anthropic.Anthropic(api_key=api_key)

        logger.info(f"[AnthropicProvider] Anthropic 客户端创建成功")

    @property
    def get_client(self):
        """获取 Anthropic 客户端实例"""
        return self.client

    @staticmethod
    def test_connection(api_key: str, base_url: str = None) -> bool:
        """
        测试 Anthropic API 连接
        对于第三方代理服务，使用 requests 直接调用以避免 SDK 被阻止
        :param api_key: API Key
        :param base_url: 可选的自定义 base_url
        :return: 连接是否成功
        """
        logger.info(f"[AnthropicProvider] 开始连通性测试: base_url={base_url or 'https://api.anthropic.com (默认)'}")

        try:
            # 构建 API URL
            if base_url:
                base_url = base_url.rstrip('/')
                if not base_url.endswith('/v1'):
                    base_url = base_url + '/v1'
            else:
                base_url = "https://api.anthropic.com/v1"

            url = f"{base_url}/messages"
            logger.debug(f"[AnthropicProvider] 测试 URL: {url}")

            # 构建请求
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "anthropic-version": "2023-06-01"
            }

            payload = {
                "model": "claude-3-5-haiku-20241022",
                "max_tokens": 10,
                "messages": [{"role": "user", "content": "Hi"}]
            }

            # 发送测试请求
            logger.info(f"[AnthropicProvider] 发送测试请求...")
            response = requests.post(url, headers=headers, json=payload, timeout=30)

            if response.status_code == 200:
                logger.info("[AnthropicProvider] 连通性测试成功")
                return True
            else:
                logger.error(f"[AnthropicProvider] 连通性测试失败，状态码: {response.status_code}, 响应: {response.text[:200]}")
                return False

        except Exception as e:
            logger.error(f"[AnthropicProvider] 连通性测试失败：{e}", exc_info=True)
            return False
