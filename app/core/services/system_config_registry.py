# -*- coding:utf-8 -*-
"""SystemConfigRegistry 系统配置组注册表

职责:
- 维护 group_key → GroupMeta 映射
- 支持两种来源: settings_cls(BaseSettings 子类) / field_specs(顶层散字段)
- 由 Settings 子类在模块导入时自我注册(避免 service 反向 import features)

异常:
- ValueError: 注册参数互斥或重复注册
- KeyError: 查询不存在的 group_key
"""
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Type

from pydantic_settings import BaseSettings


@dataclass
class FieldSpec:
    """顶层散字段元数据(用于 agent_chat_max_concurrency / task_scheduler_* 等无独立 Settings 子类的字段)

    Attributes:
        name: 字段名(在 settings 顶层属性名)
        field_type: 字段类型(int / str / bool / list 等)
        default: 默认值
        getter: 从 settings 实例读值的 lambda
        setter: 把值写回 settings 实例的 lambda
        description: 字段说明(可选,用于前端 placeholder/tooltip)
    """
    name: str
    field_type: Type
    default: Any
    getter: Callable[[Any], Any]
    setter: Callable[[Any, Any], None]
    description: str = ""


@dataclass
class GroupMeta:
    """配置组元数据

    Attributes:
        group_key: 组 key(如 'llm' / 'cors')
        tab: 所属孙 Tab('llm' / 'file-parser' / 'security' / 'network' / 'sandbox-task' / 'misc')
        label: 显示名(前端 section 标题)
        settings_cls: BaseSettings 子类(与 field_specs 互斥)
        field_specs: 顶层散字段列表(与 settings_cls 互斥)
        sensitive_fields: 敏感字段名列表(Fernet 加密存储)
        description: 组说明(可选)
    """
    group_key: str
    tab: str
    label: str
    settings_cls: Optional[Type[BaseSettings]] = None
    field_specs: Optional[List[FieldSpec]] = None
    sensitive_fields: List[str] = field(default_factory=list)
    description: str = ""


class SystemConfigRegistry:
    """系统配置组注册表(类方法单例)

    使用:
        SystemConfigRegistry.register(group_key='llm', tab='llm', label='主模型', settings_cls=LLMSettings, ...)
        meta = SystemConfigRegistry.get('llm')
    """

    _groups: Dict[str, GroupMeta] = {}

    @classmethod
    def register(
        cls,
        group_key: str,
        tab: str,
        label: str,
        settings_cls: Optional[Type[BaseSettings]] = None,
        field_specs: Optional[List[FieldSpec]] = None,
        sensitive_fields: Optional[List[str]] = None,
        description: str = "",
    ) -> None:
        """注册一个配置组

        Args:
            group_key: 组 key,全局唯一
            tab: 所属孙 Tab
            label: 显示名
            settings_cls: BaseSettings 子类(与 field_specs 互斥,二选一必填)
            field_specs: 顶层散字段列表(与 settings_cls 互斥)
            sensitive_fields: 敏感字段名列表
            description: 组说明

        Raises:
            ValueError: 参数互斥 / 重复注册
        """
        if settings_cls is None and field_specs is None:
            raise ValueError("register 必须提供 settings_cls 或 field_specs 之一")
        if settings_cls is not None and field_specs is not None:
            raise ValueError("settings_cls 与 field_specs 互斥,只能提供其一")
        if group_key in cls._groups:
            raise ValueError(f"重复注册 group_key: {group_key}")
        cls._groups[group_key] = GroupMeta(
            group_key=group_key,
            tab=tab,
            label=label,
            settings_cls=settings_cls,
            field_specs=field_specs,
            sensitive_fields=list(sensitive_fields or []),
            description=description,
        )

    @classmethod
    def get(cls, group_key: str) -> GroupMeta:
        """查询组元数据

        Raises:
            KeyError: group_key 不存在
        """
        if group_key not in cls._groups:
            raise KeyError(f"group_key 未注册: {group_key}")
        return cls._groups[group_key]

    @classmethod
    def has(cls, group_key: str) -> bool:
        return group_key in cls._groups

    @classmethod
    def all(cls) -> Dict[str, GroupMeta]:
        """返回全部注册组的浅拷贝(防外部污染)"""
        return dict(cls._groups)

    @classmethod
    def list_by_tab(cls, tab: str) -> List[GroupMeta]:
        """按孙 Tab 过滤返回组列表"""
        return [m for m in cls._groups.values() if m.tab == tab]

    @classmethod
    def clear(cls) -> None:
        """清空注册表(仅测试用)"""
        cls._groups.clear()
