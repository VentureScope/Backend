import os
from typing import Optional, List, Any, AsyncIterator
from pydantic import PrivateAttr

from langchain_openai import ChatOpenAI
from langchain_core.callbacks import AsyncCallbackManagerForLLMRun
from langchain_core.outputs import GenerationChunk

from openai import OpenAI, AsyncOpenAI
from app.core.config import settings

class HostedLLM(ChatOpenAI):
    """Custom LangChain LLM wrapping the VentureScope hosted endpoint."""
    
    token: Optional[str] = None
    endpoint: Optional[str] = None

    def __init__(self, token: Optional[str] = None, **kwargs):
        token = token or os.environ.get("HOSTED_LLM_TOKEN")
        if not token:
            raise ValueError("Missing HOSTED_LLM_TOKEN environment variable.")
        endpoint = os.environ.get("END_POINT")
        if not endpoint:
            raise ValueError("END_POINT environment variable is not set.")
            
        kwargs["api_key"] = token
        kwargs["base_url"] = endpoint
        kwargs["model"] = kwargs.get("model", settings.CHAT_MODEL_NAME)
        kwargs["temperature"] = kwargs.get("temperature", settings.CHAT_TEMPERATURE)
        kwargs["max_tokens"] = kwargs.get("max_tokens", settings.CHAT_MAX_TOKENS)
        
        super().__init__(**kwargs)

    @property
    def _llm_type(self) -> str:
        return "hosted_llm"

