# -*- coding:utf-8 -*-
"""邮件模板渲染器模块。

提供 ``EmailTemplateRenderer``，将脚本执行结果按 ``{{var}}`` 模板渲染为
邮件主题与正文。占位符语法：

    * ``{{var}}`` —— 变量名仅接受 ``[A-Za-z0-9_]+``；
    * ``{{timestamp|FORMAT}}`` —— 特殊变量，支持通过管道符指定时间格式，
      例如 ``{{timestamp|%Y%m%d%H%M}}`` 渲染为 ``202607201109``；
      省略格式时默认使用 ``%Y-%m-%d %H:%M:%S``；
    * 变量值来自调用方传入的 ``context`` 字典；
    * 仅 ``SUPPORTED_VARS`` 白名单中的键会被渲染，其他键被忽略（防注入）；
    * 未匹配的 ``{{var}}`` 保留原样，避免静默丢失。

设计原则：
    * 不引入 Jinja2 / mako 等第三方模板引擎；
    * 仅做字符串替换，避免任意 Python 表达式执行；
    * 渲染失败的 ``{{var}}`` 保留原样，方便前端调试模板。
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Optional


_PLACEHOLDER_RE = re.compile(
    r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*(?:\|\s*([^}]*)?)?\s*\}\}"
)
_DEFAULT_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"


class EmailTemplateRenderer:
    """邮件模板渲染器（占位符 ``{{var}}``，白名单变量）。

    特殊说明：
        * ``timestamp`` 不依赖 ``context``，在渲染时动态取当前时间；
        * 支持 ``{{timestamp|FORMAT}}`` 内联格式，例如 ``{{timestamp|%Y%m%d%H%M}}``。

    Attributes:
        SUPPORTED_VARS: 可被渲染的变量白名单。**只读**，外部不应修改。
    """

    SUPPORTED_VARS = frozenset(
        {
            "schedule_name",
            "schedule_id",
            "run_id",
            "started_at",
            "finished_at",
            "trigger_type",
            "script_name",
            "script_output",
            "attachment_paths",
            "timestamp",
        }
    )

    @classmethod
    def render(cls, template: str, context: Dict[str, Any]) -> str:
        """按 ``{{var}}`` 渲染模板字符串。

        仅 ``SUPPORTED_VARS`` 中的键会被替换；未匹配的占位符保留原样。
        ``timestamp`` 为特殊变量，不读取 ``context``，在渲染时动态生成当前时间。

        参数:
            template: 含 ``{{var}}`` 占位符的模板字符串；空字符串返回空字符串。
            context: 变量映射；非白名单键会被忽略。

        返回:
            str: 渲染后的字符串。
        """
        if not template:
            return ""
        # 仅白名单变量进入渲染视野
        safe_ctx = {
            key: cls._stringify(value)
            for key, value in (context or {}).items()
            if key in cls.SUPPORTED_VARS
        }

        def _replace(match: "re.Match[str]") -> str:
            name = match.group(1)
            fmt = (match.group(2) or "").strip()
            if name == "timestamp":
                return cls._render_timestamp(fmt)
            if name in safe_ctx:
                return safe_ctx[name]
            # 未匹配或不在白名单：保留原样
            return match.group(0)

        return _PLACEHOLDER_RE.sub(_replace, template)

    @classmethod
    def _render_timestamp(cls, fmt: str) -> str:
        """渲染 ``timestamp`` 变量。

        参数:
            fmt: strftime 格式字符串；为空时使用默认格式
                ``%Y-%m-%d %H:%M:%S``。

        返回:
            str: 当前时间按指定格式渲染后的字符串。

        异常处理:
            格式非法时保留原占位符文本，返回 ``{{timestamp|fmt}}`` 形式，
            避免发送失败并方便前端排查。
        """
        fmt = fmt or _DEFAULT_TIMESTAMP_FORMAT
        try:
            return datetime.now().strftime(fmt)
        except (ValueError, KeyError):
            return f"{{{{timestamp|{fmt}}}}}"

    @staticmethod
    def _stringify(value: Any) -> str:
        """把任意值规范化为字符串。

        约定：
            * ``None`` → 空串；
            * ``datetime`` → ``YYYY-MM-DD HH:MM:SS`` 形式；
            * ``list`` / ``tuple`` → 逗号拼接；
            * 其他 → ``str(value)``。

        参数:
            value: 任意值。

        返回:
            str: 字符串化结果。
        """
        if value is None:
            return ""
        if isinstance(value, datetime):
            return value.strftime("%Y-%m-%d %H:%M:%S")
        if isinstance(value, (list, tuple)):
            return ", ".join(str(item) for item in value)
        return str(value)


def build_render_context(
    schedule: Dict[str, Any],
    run_id: int,
    script_output: str,
    attachments: Optional[List[str]],
    started_at: datetime,
    finished_at: datetime,
    trigger_type: str,
    script_name: Optional[str],
) -> Dict[str, Any]:
    """构造模板渲染上下文，统一管理可用变量。

    参数:
        schedule: 定时任务记录 dict（含 id / name 等）。
        run_id: 执行记录 ID。
        script_output: 脚本返回的正文（已 ``normalize_script_result``）。
        attachments: 附件绝对路径列表（可能为 ``None``）。
        started_at: 本次执行开始时间。
        finished_at: 本次执行结束时间。
        trigger_type: 触发方式 ``scheduled`` 或 ``manual``。
        script_name: 脚本名（agent 任务时为 ``None``）。

    返回:
        Dict[str, Any]: ``EmailTemplateRenderer.render`` 可直接消费的 context。
    """
    return {
        "schedule_name": schedule.get("name") or "",
        "schedule_id": schedule.get("id"),
        "run_id": run_id,
        "started_at": started_at,
        "finished_at": finished_at,
        "trigger_type": trigger_type,
        "script_name": script_name or "",
        "script_output": script_output or "",
        "attachment_paths": attachments or [],
    }
