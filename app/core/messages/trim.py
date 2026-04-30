from typing import List, Optional, Callable, Any
from langchain_core.messages import ToolMessage, BaseMessage
from langchain_core.messages.utils import trim_messages


def trim_old_tool_messages(
    messages: List[BaseMessage],
    keep_last_n: int = 2
) -> List[BaseMessage]:
    """
    只保留最近 N 条 ToolMessage，删除更早的
    
    参考 LangChain ContextEditingMiddleware 的 ClearToolUsesEdit 逻辑，
    但不依赖中间件机制，直接在消息列表层面操作。
    
    Args:
        messages: 消息列表
        keep_last_n: 保留最近几条工具消息，默认 2
        
    Returns:
        过滤后的消息列表
    """
    # 收集所有工具消息
    tool_messages = []
    for msg in messages:
        if isinstance(msg, ToolMessage):
            tool_messages.append(msg)
    
    # 确定要保留的工具消息（最近 N 条）
    keep_tools_count = min(keep_last_n, len(tool_messages))
    keep_tool_ids = set(id(tm) for tm in tool_messages[-keep_tools_count:]) if keep_tools_count > 0 else set()
    
    # 按原始顺序构建结果
    result = []
    for msg in messages:
        if isinstance(msg, ToolMessage):
            # 使用 id() 比较，避免对象身份问题
            if id(msg) in keep_tool_ids:
                result.append(msg)
        else:
            result.append(msg)
    
    return result


def trim_messages_with_tool_limit(
    messages: List[BaseMessage],
    keep_last_n: int = 2,
    max_tokens: Optional[int] = None,
    token_counter: Optional[Callable] = None,
    strategy: str = "last",
    start_on: str = "human",
) -> List[BaseMessage]:
    """
    先过滤工具消息，再按 token 限制裁剪
    
    组合使用工具消息过滤 + token 级别 trim，
    模拟 LangChain 中间件的编辑逻辑。
    
    Args:
        messages: 消息列表
        keep_last_n: 保留最近几条工具消息
        max_tokens: 最大 token 数（可选）
        token_counter: token 计算函数（可选）
        strategy: trim 策略，默认 "last"
        start_on: 开始保留的消息角色，默认 "human"
        
    Returns:
        处理后的消息列表
    """
    messages = trim_old_tool_messages(messages, keep_last_n=keep_last_n)
    
    if max_tokens and token_counter:
        messages = trim_messages(
            messages,
            strategy=strategy,
            token_counter=token_counter,
            max_tokens=max_tokens,
            start_on=start_on,
        )
    
    return messages
