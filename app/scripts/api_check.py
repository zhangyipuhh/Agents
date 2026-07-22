# -*- coding:utf-8 -*-
"""
API 接口健康检查标准化模块。

``api_list`` 是脚本系统的**系统级标准参数**：凡在 ``params_schema`` 中声明
``api_list``（``x-control=api-multiselect`` / ``x-source=api-configs`` /
``x-value-field=id``）的脚本，都可通过本模块获得**完全一致**的检查结果结构，
供生成运行摘要、报告附件或邮件正文使用，无需各自手写循环与断言逻辑。

契约要点：
    * ``script_args["api_list"]`` 元素为 API 节点 id 的字符串形式（如 ``"12"``）。
    * 检查执行复用 ``ApiConfigService.send_request(node_id)``：httpx 代理发送、
      按接口配置中的 Mock（expectations）断言校验、自动落库 ``api_check_runs``。
    * 单个接口失败（节点缺失 / 网络异常）**不中断**整体检查，失败信息记录到
      对应 ``ApiCheckItem``。
    * ``api_list`` 为空时返回空 ``ApiCheckReport``，不要求服务可用。

使用示例::

    from app.scripts.api_check import run_api_checks

    report = await run_api_checks(context)
    if report.items:
        summary = summary + " | " + report.summary_line()
        markdown_table = report.to_markdown()
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.scripts.base import ScriptContext, ScriptExecutionError
from app.shared.utils.api_config_service import ApiConfigNotFoundError


@dataclass(frozen=True)
class ApiCheckItem:
    """单个 API 接口的健康检查结果。

    Attributes:
        node_id: API 节点 id（``api_config_nodes.id``）。
        name: 接口节点名称；节点已删除时为空字符串。
        path: 父文件夹路径（如 ``"业务系统/子系统"``）；根节点下为空字符串。
        check_passed: Mock 断言结果；``None`` 表示未执行（节点缺失或被删除），
            ``True`` / ``False`` 表示断言通过 / 未通过。
        http_status: 实际 HTTP 状态码；网络异常或未执行时为 ``None``。
        duration_ms: 请求耗时毫秒；未执行时为 ``None``。
        error_message: 错误描述（节点缺失 / 网络异常等）；正常时为空字符串。
        run_id: ``api_check_runs.id``，调用历史可追溯；未执行时为 ``None``。
        assertion_results: 断言明细列表（来自 ``send_request``），每项含
            ``type`` / ``passed`` / ``detail`` 等字段。
    """

    node_id: int
    name: str = ""
    path: str = ""
    check_passed: Optional[bool] = None
    http_status: Optional[int] = None
    duration_ms: Optional[int] = None
    error_message: str = ""
    run_id: Optional[int] = None
    assertion_results: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ApiCheckReport:
    """``api_list`` 健康检查的统一结果结构。

    Attributes:
        items: 每个接口的检查结果，顺序与 ``api_list`` 一致。
    """

    items: List[ApiCheckItem] = field(default_factory=list)

    @property
    def total(self) -> int:
        """返回:
            int: 检查的接口总数（含未执行项）。
        """
        return len(self.items)

    @property
    def passed(self) -> int:
        """返回:
            int: 断言通过（``check_passed is True``）的接口数。
        """
        return sum(1 for item in self.items if item.check_passed is True)

    @property
    def failed(self) -> int:
        """返回:
            int: 断言未通过或执行出错（``check_passed is False``）的接口数。
        """
        return sum(1 for item in self.items if item.check_passed is False)

    @property
    def skipped(self) -> int:
        """返回:
            int: 未执行（节点缺失，``check_passed is None``）的接口数。
        """
        return sum(1 for item in self.items if item.check_passed is None)

    def summary_line(self) -> str:
        """生成单行人类可读摘要，供 ``agent_task_runs.output_text`` 追加。

        格式示例::

            api_check=2/3 passed, 1 skipped | id=12 OK 200/45ms; id=15 FAIL 404/30ms; id=9 MISSING

        返回:
            str: 摘要文本；``items`` 为空时返回空字符串。
        """
        if not self.items:
            return ""
        executed = self.total - self.skipped
        parts = [f"api_check={self.passed}/{executed} passed"]
        if self.skipped:
            parts.append(f", {self.skipped} skipped")
        details = []
        for item in self.items:
            if item.check_passed is None:
                details.append(f"id={item.node_id} MISSING")
            elif item.check_passed:
                details.append(
                    f"id={item.node_id} OK {item.http_status}/{item.duration_ms}ms"
                )
            else:
                status_text = (
                    str(item.http_status) if item.http_status is not None else "ERR"
                )
                duration_text = (
                    f"{item.duration_ms}ms" if item.duration_ms is not None else "-"
                )
                details.append(f"id={item.node_id} FAIL {status_text}/{duration_text}")
        return "".join(parts) + " | " + "; ".join(details)

    def to_markdown(self) -> str:
        """生成 Markdown 表格，供报告附件 / 邮件正文列举被检查接口及状态。

        返回:
            str: Markdown 表格文本；``items`` 为空时返回空字符串。
        """
        if not self.items:
            return ""
        lines = [
            "| 接口 | 路径 | 状态码 | 耗时(ms) | 结果 | 错误 |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for item in self.items:
            name = item.name or f"id={item.node_id}"
            status = "" if item.http_status is None else str(item.http_status)
            duration = "" if item.duration_ms is None else str(item.duration_ms)
            if item.check_passed is None:
                result_text = "未执行"
            elif item.check_passed:
                result_text = "通过"
            else:
                result_text = "未通过"
            error = item.error_message.replace("|", "\\|") if item.error_message else ""
            lines.append(
                f"| {name} | {item.path} | {status} | {duration} | {result_text} | {error} |"
            )
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        """序列化为 JSON 可存储结构，供脚本落库或作为返回值的一部分。

        返回:
            Dict[str, Any]: 含 ``items`` / ``total`` / ``passed`` / ``failed`` /
            ``skipped`` 的字典。
        """
        return {
            "items": [
                {
                    "node_id": item.node_id,
                    "name": item.name,
                    "path": item.path,
                    "check_passed": item.check_passed,
                    "http_status": item.http_status,
                    "duration_ms": item.duration_ms,
                    "error_message": item.error_message,
                    "run_id": item.run_id,
                    "assertion_results": item.assertion_results,
                }
                for item in self.items
            ],
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
        }


def resolve_api_list(script_args: Dict[str, Any]) -> List[int]:
    """解析并校验 ``api_list`` 脚本参数，所有脚本共用的统一入口。

    缺失键或值为 ``None`` 时按空列表处理；元素为 API 节点 id 的字符串形式，
    转换为 ``int`` 返回。脚本侧不去重，前端已按 schema 的 ``uniqueItems``
    约束保证唯一性。

    参数:
        script_args: 脚本运行参数字典（``context.script_args``）。

    返回:
        List[int]: 通过校验的 API 节点 id 列表（缺失或空数组时返回 ``[]``）。

    异常:
        ScriptExecutionError: ``api_list`` 不是列表、元素不是非空字符串、或
        元素不能转换为整数 id 时抛出，错误消息包含字段名 ``api_list``。
    """
    raw_value = (script_args or {}).get("api_list", [])
    if raw_value is None:
        raw_value = []

    if not isinstance(raw_value, list):
        raise ScriptExecutionError(
            "api_list 必须为字符串数组（API 节点 id 列表），"
            f"实际收到类型: {type(raw_value).__name__}"
        )

    validated: List[int] = []
    for index, item in enumerate(raw_value):
        if not isinstance(item, str):
            raise ScriptExecutionError(
                f"api_list[{index}] 必须为非空字符串形式的 API 节点 id，"
                f"实际收到类型: {type(item).__name__}"
            )
        if not item:
            raise ScriptExecutionError(
                f"api_list[{index}] 不能为空字符串，API 节点 id 必须非空"
            )
        try:
            node_id = int(item)
        except ValueError:
            raise ScriptExecutionError(
                f"api_list[{index}] 必须为整数形式的 API 节点 id，实际收到: {item!r}"
            ) from None
        validated.append(node_id)

    return validated


def _build_node_lookup(nodes: List[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
    """把 ``get_tree()`` 平铺节点列表规整为 ``id → {name, path, node_type}`` 映射。

    父路径沿 ``parent_id`` 链向上拼接（仅含文件夹名），根节点下路径为空串；
    防御环状数据：单条链最多遍历 ``len(nodes)`` 次。

    参数:
        nodes: ``ApiConfigService.get_tree()`` 返回的节点平铺列表。

    返回:
        Dict[int, Dict[str, Any]]: 键为节点 id，值含 ``name`` / ``path`` /
        ``node_type`` 字段；id 非法的节点行被跳过。
    """
    by_id: Dict[int, Dict[str, Any]] = {}
    for node in nodes or []:
        try:
            node_id = int(node.get("id"))
        except (TypeError, ValueError):
            continue
        by_id[node_id] = node

    lookup: Dict[int, Dict[str, Any]] = {}
    for node_id, node in by_id.items():
        segments: List[str] = []
        cursor = node.get("parent_id")
        hops = 0
        while cursor is not None and hops <= len(by_id):
            parent = by_id.get(cursor)
            if parent is None:
                break
            segments.append(str(parent.get("name") or ""))
            cursor = parent.get("parent_id")
            hops += 1
        segments.reverse()
        lookup[node_id] = {
            "name": str(node.get("name") or ""),
            "path": "/".join(s for s in segments if s),
            "node_type": str(node.get("node_type") or ""),
        }
    return lookup


async def run_api_checks(
    context: ScriptContext,
    api_list: Optional[List[int]] = None,
) -> ApiCheckReport:
    """对 ``api_list`` 中的接口逐个执行健康检查并返回统一结果结构。

    每个接口通过 ``context.api_config_service.send_request(node_id)`` 执行：
    httpx 代理发送请求、按接口配置中的 Mock（expectations）断言校验、结果
    自动落库 ``api_check_runs``。单个接口失败不中断整体循环。

    参数:
        context: 脚本运行上下文，需携带 ``api_config_service`` 与 ``script_args``。
        api_list: 可选的 API 节点 id 列表；为 ``None`` 时通过
            ``resolve_api_list(context.script_args)`` 统一解析。

    返回:
        ApiCheckReport: 统一检查结果；``api_list`` 为空时 ``items`` 为空列表。

    异常:
        ScriptExecutionError: ``api_list`` 非空但 ``context.api_config_service``
        为 ``None``（DB 未就绪或服务未注入）时抛出；``api_list`` 参数非法时
        由 ``resolve_api_list`` 抛出。
    """
    ids = api_list if api_list is not None else resolve_api_list(context.script_args)
    if not ids:
        return ApiCheckReport(items=[])

    service = getattr(context, "api_config_service", None)
    if service is None:
        raise ScriptExecutionError(
            "api_config_service 不可用，无法执行 api_list 健康检查"
            "（数据库未就绪或调度器未注入该服务）"
        )

    nodes = await service.get_tree()
    lookup = _build_node_lookup(nodes)

    items: List[ApiCheckItem] = []
    for node_id in ids:
        info = lookup.get(node_id)
        if info is None or info["node_type"] != "api":
            items.append(
                ApiCheckItem(
                    node_id=node_id,
                    check_passed=None,
                    error_message="接口节点不存在或已被删除",
                )
            )
            continue

        try:
            result = await service.send_request(node_id)
        except ApiConfigNotFoundError as exc:
            items.append(
                ApiCheckItem(
                    node_id=node_id,
                    name=info["name"],
                    path=info["path"],
                    check_passed=None,
                    error_message=str(exc) or "接口配置不存在",
                )
            )
            continue
        except Exception as exc:  # noqa: BLE001 - 单接口失败不中断整体检查
            items.append(
                ApiCheckItem(
                    node_id=node_id,
                    name=info["name"],
                    path=info["path"],
                    check_passed=False,
                    error_message=f"{type(exc).__name__}: {exc}",
                )
            )
            continue

        items.append(
            ApiCheckItem(
                node_id=node_id,
                name=info["name"],
                path=info["path"],
                check_passed=bool(result.get("check_passed")),
                http_status=result.get("http_status"),
                duration_ms=result.get("duration_ms"),
                error_message=str(result.get("error_message") or ""),
                run_id=result.get("run_id"),
                assertion_results=list(result.get("assertion_results") or []),
            )
        )

    return ApiCheckReport(items=items)
