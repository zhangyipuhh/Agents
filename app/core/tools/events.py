from typing import TypedDict, Literal, Any
from datetime import datetime


class ToolEvent(TypedDict):
    """
    Subagent 工具事件 TypedDict

    字段说明：
        type: 事件类型
        tool: 工具名（如 "sandbox" / "explore"）
        tool_call_id: 父 LLM 调本工具时的 tool_call_id，同时也是子 agent 的 thread_id
        timestamp: 事件时间戳（秒，浮点）
        data: 事件数据，常见字段如下：

            data 字段约定（2026-06-13 扩展，向后兼容）：
                - args: dict，工具入参（tool_start / tool_error）
                - workspace / root_path: str，工作目录（tool_start）
                - description: str，人可读描述（tool_start）
                - child_stream: dict，子 agent 的 updates 流（tool_progress，向后兼容保留）
                - message: str，进度文本（tool_progress）
                - status: str，"success" / "failure"（tool_stop / tool_error）
                - result / final_summary / sandbox_*: 业务字段（按工具不同）
                - duration_ms: int，工具执行耗时（tool_stop / tool_error）
                - error_type / error_message: 错误信息（tool_error）

                # ===== 新增字段（subagent 前端折叠卡片 / 抽屉展示用） =====
                - thread_id: str，== tool_call_id，便于前端按 id 维护 subagent 列表
                - parent_prompt: str，父 agent 传给子 agent 的 prompt（tool_start）
                - child_messages: list[dict]，子 agent 当前累积的全部 messages，结构化
                    每项格式：
                    {
                        "type": "HumanMessage" | "AIMessage" | "ToolMessage" | "Unknown",
                        "role": "user" | "ai" | "tool" | "unknown",
                        "content": str | list[dict],
                        "tool_calls": [{"name", "args", "id"}],   # 仅 AIMessage
                        "tool_call_id": "str",                     # 仅 ToolMessage
                        "name": "str"                              # 仅 ToolMessage
                    }
                - final_messages: list[dict]，tool_stop 时的最终消息快照（同 child_messages 结构）
    """
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
