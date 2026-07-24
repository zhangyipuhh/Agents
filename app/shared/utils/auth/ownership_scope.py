# -*- coding:utf-8 -*-
"""
通用配置归属隔离（OwnershipScope）模块。

设计目的
========
项目内有多种"配置类"数据（邮件发送策略、API 配置等），其中部分需要按
创建者用户做隔离：admin 可见全部；普通用户仅可见自己创建的。本模块提供
一种与具体业务解耦的 ``OwnershipScope`` 描述对象，供任意 service / router
复用，避免每个业务表各自实现一套权限过滤。

适用场景
========
凡配置表包含 ``created_by_user_id INTEGER NOT NULL REFERENCES users(id)``
字段、并希望按创建者做可见性隔离的业务，都应使用本模块，例如：

- ``email_policies``：邮件发送策略（admin 见全部，普通用户只见自己创建的）
- 未来：``api_config_nodes`` / ``api_configs``（API 接口配置）

可见性规则
==========
- ``system=True``：内部调用（如定时任务运行时通过 ``notify_policy_id`` 取
  策略），跳过所有过滤可见全部。
- ``is_admin=True`` 且 ``system=False``：admin 角色可见全部（不应用
  ``WHERE created_by_user_id``）。
- 普通用户：仅可见 ``created_by_user_id == self.user_id`` 的记录。

越权访问语义
============
未通过 ``can_access(owner_id)`` 的访问在 service 层返回 ``None``，路由层
映射为 HTTP 404（与 ``ProjectDB.get_project_by_id(..., user_id=...)`` 的
先例一致，不泄露记录是否存在）。

约定字段命名
============
历史表（``email_policies``）已使用 ``created_by_user_id``，新表（如未来
``api_configs``）也建议沿用同一字段名，避免命名分叉导致 service 层
``scope.sql_filter('created_by_user_id', ...)`` 调用不一致。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True)
class OwnershipScope:
    """数据归属隔离的调用上下文。

    Attributes:
        user_id: 当前用户 ID；``system=True`` 时可为 ``None``（系统内部）。
        is_admin: 当前用户是否为 admin 角色。admin 可见全部。
        system: 系统内部调用（定时任务等），不受用户隔离限制。

    说明:
        不可变对象（``frozen=True``），便于跨调用链透传且避免副作用。
    """

    user_id: Optional[int]
    is_admin: bool
    system: bool = False

    # ------------------------------------------------------------------
    # 工厂方法
    # ------------------------------------------------------------------

    @classmethod
    def from_request(cls, request) -> "OwnershipScope":
        """从 FastAPI Request 中提取当前用户的归属上下文。

        由 ``auth_middleware`` 在请求通过 JWT 校验后将 ``user_id`` / ``role``
        写入 ``request.state``，本方法读取这些字段构造 scope。

        参数:
            request: FastAPI Request 对象。

        返回:
            OwnershipScope: 当前请求对应的 scope。

        异常:
            无；``request.state`` 缺失字段时降级为 ``user_id=None`` 且
            ``is_admin=False``（默认按普通用户处理）。
        """
        user_id = getattr(request.state, "user_id", None)
        role = getattr(request.state, "role", "user")
        return cls(
            user_id=int(user_id) if user_id else None,
            is_admin=(role == "admin"),
        )

    @classmethod
    def for_user(cls, user_id: int, is_admin: bool = False) -> "OwnershipScope":
        """为已知 user_id 构造普通用户 scope（脚本调用等场景）。

        参数:
            user_id: 用户 ID。
            is_admin: 是否 admin。默认 ``False``。

        返回:
            OwnershipScope: 对应用户的 scope。
        """
        return cls(user_id=user_id, is_admin=is_admin)

    @classmethod
    def system_scope(cls) -> "OwnershipScope":
        """构造系统内部调用 scope（绕过归属隔离）。

        用于定时任务运行时按 ``notify_policy_id`` 取策略、admin 视图全量
        审计等需要绕过用户隔离的场景。

        返回:
            OwnershipScope: system=True 的 scope。
        """
        return cls(user_id=None, is_admin=False, system=True)

    # ------------------------------------------------------------------
    # 判定方法
    # ------------------------------------------------------------------

    def can_access(self, owner_id: Optional[int]) -> bool:
        """判断当前 scope 是否可访问由 ``owner_id`` 创建的记录。

        判定规则（顺序短路）：
        1. ``system=True``：永真。
        2. ``is_admin=True``：永真（admin 可见全部）。
        3. ``owner_id == self.user_id`` 且 ``user_id`` 非 ``None``：真。
        4. 其他：假。

        参数:
            owner_id: 记录创建者用户 ID；可能为 ``None``（旧数据 / 系统种子）。

        返回:
            bool: 是否允许访问。
        """
        if self.system:
            return True
        if self.is_admin:
            return True
        if owner_id is None or self.user_id is None:
            return False
        return int(owner_id) == int(self.user_id)

    # ------------------------------------------------------------------
    # SQL 过滤辅助
    # ------------------------------------------------------------------

    def sql_filter(
        self,
        column: str = "created_by_user_id",
        param_index: Optional[int] = None,
    ) -> Tuple[str, list]:
        """生成附加到 ``SELECT`` / ``DELETE`` 的归属过滤条件。

        用于在 service 层把 scope 直接翻译为 SQL 子句，避免每个 service
        各自手工拼接 ``WHERE created_by_user_id = $N``。

        参数:
            column: 归属列名，默认 ``created_by_user_id``。
            param_index: 占位符索引（如 ``$N``）；``None`` 时生成 ``$N``
                形式占位符（N=1），调用方需自行确认不与现有占位符冲突。
                推荐做法：在调用方先确定现有占位符最大索引 N，将本方法
                返回的 SQL 片段中的 ``$N`` 替换为 ``$(N+1)``。

        返回:
            Tuple[str, list]: ``(WHERE 片段, 绑定参数列表)``。

            - ``system=True`` 或 ``is_admin=True``：返回 ``("TRUE", [])``，
              直接拼到 ``WHERE`` 子句后对结果无影响。
            - 普通用户：返回 ``(f"{column} = $N", [user_id])``，调用方需
              把 ``$N`` 替换为不冲突的下标。
        """
        if self.system or self.is_admin:
            return "TRUE", []
        if self.user_id is None:
            # 普通用户但 user_id 缺失（理论上不会发生，auth_middleware 已
            # 写入；此处兜底返回空集而不是放行所有数据）。
            return "FALSE", []
        placeholder = f"${param_index}" if param_index is not None else "$N"
        return f"{column} = {placeholder}", [self.user_id]