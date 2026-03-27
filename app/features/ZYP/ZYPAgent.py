import asyncio
from typing import Callable, Optional, Any, AsyncIterator
from dataclasses import dataclass

from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore

from app.core.agent.agent import get_agent
from app.core.llmcalls.model_factory import ModelFactory

from .config import (
    ZYPConfig,
    ZYPState,
    ZYPContext,
    ZYPExecuteConfig,
    ZYPConfigurableConfig,
    DEFAULT_PROMPT,
)


@dataclass
class ModelConfig:
    model_type: str
    model_name: str
    api_key: str
    base_url: str
    temperature: float


class ZYPAgent:
    def __init__(self, config: Optional[ZYPConfig] = None):
        self._agent = None
        self._checkpointer = MemorySaver()
        self._store = InMemoryStore()
        self._streaming = False
        self._config = config or self._create_default_config()

    def _create_default_config(self) -> ZYPConfig:
        return ZYPConfig(
            model_type="deepseek",
            model_name="deepseek-chat",
            api_key="",
            base_url="https://api.deepseek.com",
            temperature=0.0,
            max_tokens=20000,
            max_tokens_before_summary=16000,
            max_summary_tokens=4000,
            system_prompt=DEFAULT_PROMPT,
            checkpointer=self._checkpointer,
            store=self._store,
        )

    async def initialize(self):
        if self._agent is None:
            self._agent = await get_agent(self._config)

    async def reinitialize(self, model_config: ModelConfig):
        self._config.model_type = model_config.model_type
        self._config.model_name = model_config.model_name
        self._config.api_key = model_config.api_key
        self._config.base_url = model_config.base_url
        self._config.temperature = model_config.temperature

        self._checkpointer = MemorySaver()
        self._store = InMemoryStore()
        self._config.checkpointer = self._checkpointer
        self._config.store = self._store

        self._agent = await get_agent(self._config)

    async def chat(
        self,
        message: str,
        session_id: str,
        stream_callback: Callable[[str], None],
    ) -> str:
        if self._agent is None:
            await self.initialize()

        store_id = "default"

        config = ZYPExecuteConfig(
            configurable=ZYPConfigurableConfig(thread_id=session_id)
        )

        state = ZYPState(
            messages=[message],
            error_limit=5,
            limit=25,
            file_chunk_read_progress=1,
            image_paths_id=[],
            IS_MULTIMODAL=False,
        )

        context = ZYPContext(
            session_id=session_id,
            namespace={},
            store_id=store_id,
            image_ids=[],
        )

        full_response = ""

        try:
            async for chunk in self._agent.astream(
                config=config,
                input_state=state,
                context=context,
                stream_mode="messages",
            ):
                if self._streaming is False:
                    continue

                if chunk and len(chunk) > 0:
                    msg = chunk[-1] if isinstance(chunk, list) else chunk
                    if hasattr(msg, "content") and msg.content:
                        delta = msg.content[len(full_response):]
                        if delta:
                            full_response += delta
                            await stream_callback(delta)

        except Exception as e:
            raise ZYPError(f"Chat failed: {str(e)}") from e

        return full_response

    def stop_streaming(self):
        self._streaming = False

    async def astream(
        self,
        message: str,
        session_id: str,
    ) -> AsyncIterator[str]:
        if self._agent is None:
            await self.initialize()

        store_id = "default"

        config = ZYPExecuteConfig(
            configurable=ZYPConfigurableConfig(thread_id=session_id)
        )

        state = ZYPState(
            messages=[message],
            error_limit=5,
            limit=25,
            file_chunk_read_progress=1,
            image_paths_id=[],
            IS_MULTIMODAL=False,
        )

        context = ZYPContext(
            session_id=session_id,
            namespace={},
            store_id=store_id,
            image_ids=[],
        )

        self._streaming = True
        full_response = ""

        async for chunk in self._agent.astream(
            config=config,
            input_state=state,
            context=context,
            stream_mode="messages",
        ):
            if not self._streaming:
                break

            if chunk and len(chunk) > 0:
                msg = chunk[-1] if isinstance(chunk, list) else chunk
                if hasattr(msg, "content") and msg.content:
                    delta = msg.content[len(full_response):]
                    if delta:
                        full_response += delta
                        yield delta


class ZYPError(Exception):
    pass


class NetworkError(ZYPError):
    pass


class AuthError(ZYPError):
    pass


class TimeoutError(ZYPError):
    pass


class StorageError(ZYPError):
    pass
