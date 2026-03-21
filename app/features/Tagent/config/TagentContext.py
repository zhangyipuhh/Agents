from app.core.agent.AgentContext import AgentContext as BaseAgentContext


class TAgentContext(BaseAgentContext):
    """
    上下文类，需要传入一个 TypedDict 类型，定义对话上下文结构，不可变
    上下文类是一个 TypedDict 类型，用于定义对话上下文的结构。
    上下文类的字段会被添加到状态类中，用于在会话中传递上下文信息。
    """
 