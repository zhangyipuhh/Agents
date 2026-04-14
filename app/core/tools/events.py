from typing import TypedDict, Literal, Any
from datetime import datetime


class ToolEvent(TypedDict):
    type: Literal["tool_start", "tool_stop", "tool_progress", "tool_error"]
    tool: str
    tool_call_id: str
    timestamp: float
    data: dict[str, Any]


def create_tool_event(
    event_type: Literal["tool_start", "tool_stop", "tool_progress", "tool_error"],
    tool: str,
    tool_call_id: str,
    data: dict[str, Any] | None = None,
) -> ToolEvent:
    return ToolEvent(
        type=event_type,
        tool=tool,
        tool_call_id=tool_call_id,
        timestamp=datetime.now().timestamp(),
        data=data or {},
    )


def example_tool_start():
    return create_tool_event(
        event_type="tool_start",
        tool="open_file",
        tool_call_id="call_abc123",
        data={
            "args": {"file_path": "/path/to/document.pdf"},
            "description": "开始加载文档",
        },
    )


def example_tool_progress():
    return create_tool_event(
        event_type="tool_progress",
        tool="read_cached_chunk",
        tool_call_id="call_def456",
        data={
            "current": 3,
            "total": 10,
            "percentage": 30,
            "message": "正在读取第 3/10 块",
        },
    )


def example_tool_stop():
    return create_tool_event(
        event_type="tool_stop",
        tool="open_file",
        tool_call_id="call_abc123",
        data={
            "status": "success",
            "result": {"cache_id": "uuid-xxx", "total_chunks": 10},
            "duration_ms": 1250,
        },
    )


def example_tool_error():
    return create_tool_event(
        event_type="tool_error",
        tool="open_file",
        tool_call_id="call_ghi789",
        data={
            "error_type": "FileNotFoundError",
            "error_message": "文件不存在: /path/to/missing.pdf",
            "args": {"file_path": "/path/to/missing.pdf"},
        },
    )


if __name__ == "__main__":
    import json

    print("=== tool_start 示例 ===")
    print(json.dumps(example_tool_start(), indent=2, ensure_ascii=False))

    print("\n=== tool_progress 示例 ===")
    print(json.dumps(example_tool_progress(), indent=2, ensure_ascii=False))

    print("\n=== tool_stop 示例 ===")
    print(json.dumps(example_tool_stop(), indent=2, ensure_ascii=False))

    print("\n=== tool_error 示例 ===")
    print(json.dumps(example_tool_error(), indent=2, ensure_ascii=False))
