"""
GPT 抽象基类
定义所有 GPT 实现类必须实现的接口
"""
from abc import ABC, abstractmethod
from typing import List, Any

from app.models.gpt_model import GPTSource


class GPT(ABC):
    """
    GPT 抽象基类
    所有 GPT 实现（UniversalGPT、AnthropicGPT 等）都必须继承此类
    """

    @abstractmethod
    def summarize(self, source: GPTSource) -> str:
        """
        生成视频笔记摘要
        :param source: GPT 输入源，包含视频标题、转写片段、图片等信息
        :return: 生成的笔记内容（Markdown 格式）
        """
        pass

    @abstractmethod
    def create_messages(self, segments: List[Any], **kwargs) -> list:
        """
        创建 API 请求消息
        :param segments: 转写片段列表
        :param kwargs: 其他参数（title, tags, video_img_urls 等）
        :return: 消息列表
        """
        pass

    @abstractmethod
    def list_models(self) -> Any:
        """
        获取可用模型列表
        :return: 模型列表
        """
        pass
