from typing import Dict, List, Optional, TYPE_CHECKING
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from app.core.agent import ToolRuntime


class BaseSchema(BaseModel):
    pass


class FileRegistry(BaseSchema):
    files: Dict[str, str] = Field(default_factory=dict, description="file_id → file_path")


class ImageRegistry(BaseSchema):
    images: Dict[str, str] = Field(default_factory=dict, description="image_id → base64_data")


class DocumentChunk(BaseSchema):
    index: int = Field(..., description="块索引")
    name: str = Field(..., description="块名称/类型")
    content: str = Field(..., description="块内容")


class ClauseChunk(BaseSchema):
    index: int = Field(..., description="块索引")
    name: str = Field(..., description="条款名称")
    content: str = Field(..., description="条款内容")


class QAItem(BaseSchema):
    question: str = Field(..., description="问题内容")
    answer: str = Field(..., description="答案内容")


class ExtractionItem(BaseSchema):
    index: str = Field(..., description="索引标识，如'基础信息'、'第一条'等")
    content: List[QAItem] = Field(default_factory=list, description="问答列表")


class ExtractionReference(BaseSchema):
    host_session_id: str = Field(..., description="会话ID")
    documents: Dict[str, List[ExtractionItem]] = Field(
        default_factory=dict,
        description="文档类型 → 提取项列表"
    )


class ApprovalPrerequisites(BaseSchema):
    host_session_id: str = Field(..., description="会话ID")
    requirements: Dict[str, List[ExtractionItem]] = Field(
        default_factory=dict,
        description="要件类型 → 要件列表"
    )


class ApprovalResult(BaseSchema):
    host_session_id: str = Field(..., description="会话ID")
    status: str = Field(..., description="approved/rejected")
    result: str = Field(..., description="审批结论")
    timestamp: str = Field(..., description="时间戳")
    details: Optional[Dict] = Field(default=None, description="详情")


def get_data_session_id(runtime: "ToolRuntime") -> str:
    host_session_id = runtime.context.get('host_session_id')
    if host_session_id:
        return host_session_id
    return runtime.context.get('session_id', 'default')
