#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
AgentContext 模块

定义对话上下文的类型结构，用于在 Agent 会话中传递和管理上下文信息。
该模块提供上下文类的类型定义，支持多用户会话隔离和上下文共享。

Date: 2026-03-13
Author: 张镒谱
"""

from typing_extensions import TypedDict
from typing import Optional


class AgentContext(TypedDict):
    """
    上下文类

    继承自 TypedDict，用于定义对话上下文的结构。
    上下文类的字段会被添加到状态类中，用于在会话中传递和管理上下文信息。
    该模块提供上下文类的类型定义，支持多用户会话隔离和上下文共享。

    Attributes:
        session_id: 会话 ID，用于区分不同用户的对话，相同 session_id 的对话共享记忆
        host_session_id: 主机会话 ID，用于多智能体协作时数据隔离

    Example:
        >>> context = AgentContext(session_id="user_123")
        >>> # 在 Agent 状态中使用上下文

    说明:
        2026-07-01 删除原 project_id 字段（Optional[int] = None）。
        业务场景需要的上下文键（如 project_id）由调用方通过 context_overrides
        显式注入到 context_class(**kwargs)；AgentContext 是 TypedDict，
        运行时仍允许任意额外键，工具可通过 runtime.context.get("project_id") 读取。
    """

    session_id: str = "default"
    """会话 ID，用于区分不同用户的对话，相同 session_id 的对话共享记忆，默认 "default" """
    namespace: dict = {}
    store_id: str = "default"
    """存储 ID，用于区分不同用户的存储空间，相同 store_id 的存储空间共享记忆，默认 "default" """
    image_ids: list[str] = []
    """图片ID列表，用于多模态模型处理图片"""
    host_session_id: Optional[str] = None
    """主机会话 ID，用于多智能体协作时数据隔离，默认 None"""
    process_data: dict = {}
    """过程数据字典，用于存储业务逻辑中的临时过程值，默认空字典"""
    dynamic_context_suffix: str = ""
    """动态上下文后缀（附件 <attachments> / 服务器 <servers> 节点），
    由 chat 路由经 context_overrides 注入，agent._llm_call 追加到系统提示词末尾，默认空字符串"""
    referenced_servers: list = []
    """2026-07-26 新增：用户通过 `#` 触发的引用项（结构化数据，name/business_name + server_type）。
    与 dynamic_context_suffix 中的 <servers> XML 节点同源；工具可经
    runtime.context.get("referenced_servers") 读取该列表做参数补全，避免解析 XML。
    由 chat 路由经 context_overrides.referenced_servers 注入，frontend 数据源已是
    用户权限范围内的 server 列表，无需后端再校验归属。默认空列表。"""
    # 2026-07-29 新增：审计日志身份字段
    log_user_id: Optional[int] = None
    """审计日志用户 ID（Optional[int]）。
    业务语义：写入 audit_logs.user_id 的真值来源，**禁止信任客户端**。
    - 请求路径（agent_router）由 request.state.user_id（auth_middleware 注入）强制覆盖；
    - 调度路径（task_scheduler_service）由 schedule.created_by_user_id 强制覆盖；
    - 工具如需发起新审计事件，应优先读取 ``runtime.context.get("log_user_id")``，
      避免与 request.state 解耦的间接上下文。
    默认 None 表示身份未被注入（lifespan 异常 / 测试桩 / 离线脚本场景）。"""
    log_username: Optional[str] = None
    """审计日志用户名（Optional[str]）。
    业务语义：与 ``log_user_id`` 配对使用，来源同样不可信客户端。
    流程：request.state.username / schedule owner.username 强制覆盖；
    工具侧推荐 ``runtime.context.get("log_username")`` 取值。
    默认 None。"""
    # 2026-07-30 新增：审计日志 IP 字段
    log_ip: Optional[str] = None
    """审计日志客户端 IP（Optional[str]）。
    业务语义：写入 ``audit_logs.ip_address`` 的真值来源，**禁止信任客户端**。
    - 请求路径（agent_router）由 ``request.client.host`` 强制覆盖；
    - 调度路径（task_scheduler_service）保持 None（定时任务无远程客户端）；
    - 工具如需发起新审计事件，应优先读取 ``runtime.context.get("log_ip")``，
      避免与 request.state 解耦的间接上下文。
    默认 None 表示身份未被注入（lifespan 异常 / 离线脚本 / 测试桩场景）。"""
    # 2026-08-03 新增：第三方执行器开关与端点名（与 SSHTools.execute_command 配合）
    use_third_party_executor: bool = False
    """是否走第三方命令执行器（2026-08-03 新增，SSHTools.execute_command 专用）。

    业务语义：
    - ``True`` → ``SSHTools.execute_command`` 跳过本地 Paramiko，改为
      通过 HTTPS 调用 ``runtime.context["third_party_endpoint_name"]`` 指向的
      第三方端点（请求体经 RSA-OAEP + AES-256-GCM 加密）。
    - ``False``（默认）→ 走本地 Paramiko SSH，行为完全向后兼容。

    注意：
    - 仅 ``SSHTools.execute_command`` 读取本字段；``execute_batch_commands`` /
      ``get_system_logs`` 不受影响（按用户当前需求保持不变）。
    - 加密契约详见 ``app/shared/utils/crypto/rsa_aes.py`` 与
      ``app/shared/utils/executor/third_party_executor.py``。
    - 业务方可在 ``AgentContext.context_overrides`` 中通过
      ``{"use_third_party_executor": True}`` 注入。
    """
    third_party_endpoint_name: Optional[str] = None
    """第三方执行器端点名（2026-08-03 新增，SSHTools.execute_command 专用）。

    业务语义：
    - 非空时直接使用；为空 / 缺失时回退到
      ``settings.third_party_executor.default_endpoint``（默认 ``"primary"``）。
    - 端点配置从 ``.env`` 的 ``THIRD_PARTY_EXECUTOR_ENDPOINTS`` JSON 加载，
      由 ``app/shared/utils/executor/endpoints.ThirdPartyEndpointRegistry`` 管理。
    - 仅在 ``use_third_party_executor=True`` 时生效。
    """
