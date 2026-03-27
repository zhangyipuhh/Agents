from dataclasses import dataclass, field
from typing import TypedDict, Optional, Any, TYPE_CHECKING

from app.core.agent.AgentConfig import AgentConfig as BaseAgentConfig

if TYPE_CHECKING:
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.store.memory import InMemoryStore


class ZYPConfigurableConfig(TypedDict):
    thread_id: str


class ZYPExecuteConfig(TypedDict):
    configurable: ZYPConfigurableConfig


class ZYPState(TypedDict):
    messages: list[str]
    error_limit: int
    limit: int
    file_chunk_read_progress: int
    image_paths_id: list[str]
    IS_MULTIMODAL: bool


class ZYPContext(TypedDict):
    session_id: str
    namespace: dict
    store_id: str
    image_ids: list[str]


@dataclass(kw_only=True)
class ZYPConfig(BaseAgentConfig):
    model_type: str = "deepseek"
    model_name: str = "deepseek-chat"
    api_key: str = ""
    base_url: str = ""
    temperature: float = 0.0
    max_tokens: int = 20000
    max_tokens_before_summary: int = 16000
    max_summary_tokens: int = 4000
    system_prompt: str = ""
    checkpointer: Optional["MemorySaver"] = None
    store: Optional["InMemoryStore"] = None
    state_class: type = field(default=None)
    context_class: type = field(default=None)

    def get_model_config(self) -> dict:
        return {
            "model_type": self.model_type,
            "model_name": self.model_name,
            "api_key": self.api_key,
            "base_url": self.base_url,
            "temperature": self.temperature,
        }

    def get_tools(self) -> tuple[list, Any]:
        return super().get_tools()
