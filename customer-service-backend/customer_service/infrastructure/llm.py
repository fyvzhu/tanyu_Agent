"""
LLM 基础设施 - LangChain ChatModel
"""
from langchain_openai import ChatOpenAI
from langchain_core.language_models import BaseChatModel

from customer_service.config.config import settings

_llm_instance: BaseChatModel | None = None


def get_llm() -> BaseChatModel:
    """获取 LLM 实例（单例）"""
    global _llm_instance
    if _llm_instance is None:
        _llm_instance = ChatOpenAI(
            model=settings.llm_model,
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            temperature=0  # 尽最大努力保证稳定性
        )
    return _llm_instance


# 向后兼容的全局变量
llm: BaseChatModel = get_llm()


if __name__ == '__main__':
    print(llm.invoke("你还好吗？我最近不太开心，给给我提供一些开心的情绪价值").content)
