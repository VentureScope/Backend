import os
from typing import Optional, List, Any, AsyncIterator
from pydantic import PrivateAttr

from langchain_core.language_models.llms import LLM
from langchain_core.callbacks import AsyncCallbackManagerForLLMRun
from langchain_core.outputs import GenerationChunk

from openai import OpenAI, AsyncOpenAI
from app.core.config import settings

class HostedLLM(LLM):
    """Custom LangChain LLM wrapping the VentureScope hosted endpoint."""
    
    token: Optional[str] = None
    model: str = settings.CHAT_MODEL_NAME
    temperature: float = settings.CHAT_TEMPERATURE
    max_tokens: int = settings.CHAT_MAX_TOKENS
    endpoint: str = None
    
    _client: Any = PrivateAttr()
    _async_client: Any = PrivateAttr()

    def __init__(self, token: Optional[str] = None, **kwargs):
        super().__init__(**kwargs)
        self.token = token or os.environ.get("HOSTED_LLM_TOKEN")
        if not self.token:
            raise ValueError("Missing HOSTED_LLM_TOKEN environment variable.")
        self.endpoint = os.environ.get("END_POINT")
        if not self.endpoint:
            raise ValueError("END_POINT environment variable is not set.")
            
        # Initialize both sync and async clients for flexibility
        self._client = OpenAI(
            base_url=self.endpoint,
            api_key=self.token,
        )
        self._async_client = AsyncOpenAI(
            base_url=self.endpoint,
            api_key=self.token,
        )

    @property
    def _llm_type(self) -> str:
        return "hosted_llm"

    def _call(
        self, 
        prompt: str, 
        stop: Optional[List[str]] = None
    ) -> str:
        messages = [
            {"role": "user", "content": prompt},
        ]
        response = self._client.chat.completions.create(
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            model=self.model,
            stop=stop,
        )
        return response.choices[0].message.content

    async def _astream(
        self,
        prompt: str,
        stop: Optional[List[str]] = None,
        run_manager: Optional[AsyncCallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> AsyncIterator[GenerationChunk]:
        """Async streaming implementation for real-time WebSocket output."""
        messages = [
            {"role": "user", "content": prompt},
        ]
        stream = await self._async_client.chat.completions.create(
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            model=self.model,
            stop=stop,
            stream=True
        )
        
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta.content or ""
            if delta:
                gen_chunk = GenerationChunk(text=delta)
                # Yield to LangChain LCEL pipeline
                yield gen_chunk
                if run_manager:
                    await run_manager.on_llm_new_token(gen_chunk.text)
