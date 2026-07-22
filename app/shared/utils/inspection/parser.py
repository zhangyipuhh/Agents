# -*- coding:utf-8 -*-
"""
巡检字段规则解析与阈值评估模块（纯解析与评估层）。

本模块只负责:
    1. 把运维在 YAML / 表单中声明的巡检字段规则 (dict) 规范化为强类型
       ``InspectionFieldRule``;
    2. 把 ``inspection_parser`` 对应格式的 SSH 输出解析为 ``parsed_values``
       (JSON 对象 / 数组、KV / CSV 字典或 raw 字符串, 由解析器决定);
    3. 根据阈值规则对 ``parsed_values`` 做阈值评估, 输出每个字段的
       ``InspectionFieldResult`` 与聚合的 ``InspectionEvaluation``。

注意:
    - 本模块**不**连接 SSH、不读写数据库、不写日志、不做副作用;
      它只对入参做纯函数式处理, 便于上层 (DevOps 工具 / 服务) 自由组装。
    - 本模块**不**修改 ``DevOpsServerService`` / ``server_ops`` / router /
      YAML / SQL, 仅消费 ``inspection_parser`` 字符串 + ``inspection_script``
      输出的 stdout。

阈值评估方向语义:
    - ``high``: 值越大越坏; ``value >= crit`` => crit, ``value >= warn`` => warn, 否则 pass。
    - ``low``:  值越小越坏; ``value <= crit`` => crit, ``value <= warn`` => warn, 否则 pass。
    - ``ignore``: 不评估, 字段结果 status = ``unassessed``。
    - 边界包含: ``warn == crit`` 合法; ``value == warn/crit`` 命中对应等级。
    - 总状态优先级: crit > warn > pass > unassessed (unassessed 不下拉其他字段)。
"""
from __future__ import annotations

import csv
import io
import json
import math
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Optional, Sequence, Tuple


# ---------------------------------------------------------------------------
# 异常
# ---------------------------------------------------------------------------


class InspectionParseError(ValueError):
    """
    巡检输出解析异常。

    继承 :class:`ValueError`, 用于 :func:`parse_inspection_output` 在遇到
    未知解析器、空输入或非法输入时抛出。

    Args:
        message: 人类可读的错误说明, 应尽量包含原始文本片段以便排查。

    Returns:
        None

    Raises:
        无 (本类本身可被随意构造, 仅作为异常载体)。
    """


# ---------------------------------------------------------------------------
# 数据类
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class InspectionFieldRule:
    """
    单条巡检字段规则 (规范化后)。

    Attributes:
        key: 字段英文键, 唯一且非空 (运维侧约定)。
        name_zh: 字段中文名, 非空。
        unit: 单位字符串, 缺省 / 缺失默认为 ``""``。
        direction: 评估方向, ``"high"`` / ``"low"`` / ``"ignore"`` 之一。
        warn: 警告阈值; ``ignore`` 时为 ``None``; ``high`` 时 ``warn <= crit``,
            ``low`` 时 ``warn >= crit``。
        crit: 严重阈值; ``ignore`` 时为 ``None``。
    """

    key: str
    name_zh: str
    unit: str
    direction: str
    warn: Optional[float]
    crit: Optional[float]


@dataclass(frozen=True)
class InspectionFieldResult:
    """
    单字段阈值评估结果。

    Attributes:
        key: 字段英文键, 与规则一致。
        name_zh: 字段中文名。
        unit: 单位字符串。
        value: 原始解析值; 字段缺失时为 ``None``, 非数值时保留原值
            (例如 ``True`` / ``"1024"``) 以便前端展示。
        status: 字段状态, 取值 ``"pass"`` / ``"warn"`` / ``"crit"`` /
            ``"unassessed"``。
        message: 人类可读的字段级说明 (例如缺失原因 / 非数值原因)。
        warn: 警告阈值, ``ignore`` 字段为 ``None``。
        crit: 严重阈值, ``ignore`` 字段为 ``None``。
    """

    key: str
    name_zh: str
    unit: str
    value: Any
    status: str
    message: str
    warn: Optional[float]
    crit: Optional[float]


@dataclass(frozen=True)
class InspectionEvaluation:
    """
    巡检整体评估结果。

    Attributes:
        parsed_values: 解析得到的原始值字典 (由 ``parse_inspection_output``
            产生, ``raw`` 解析器下为字符串)。
        fields: 各字段评估结果, 顺序与规则声明顺序一致。
        status: 总体状态, 取值 ``"pass"`` / ``"warn"`` / ``"crit"`` /
            ``"unassessed"``; 当 ``error_message`` 非空时固定为 ``"crit"``。
        error_message: 评估阶段的错误说明; 默认为空字符串。
            例如 ``"raw 解析器不支持结构化阈值评估"``。
    """

    parsed_values: Any
    fields: Tuple[InspectionFieldResult, ...]
    status: str
    error_message: str = field(default="")


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------


_VALID_DIRECTIONS = ("high", "low", "ignore")


def _format_key_context(idx: int, item: Any) -> str:
    """生成错误消息中可定位到具体 rule 的 ``key`` 上下文。

    Args:
        idx: 规则在列表中的索引。
        item: 规则原始对象。

    Returns:
        形如 ``"<key=cpu>"`` 或 ``"<index=1>"`` 的字符串, 永远不会抛异常。
    """
    if isinstance(item, Mapping):
        key = item.get("key")
        if isinstance(key, str) and key:
            return f"<key={key}>"
    return f"<index={idx}>"


def _validate_threshold_number(value: Any) -> Optional[float]:
    """
    严格校验规则阈值并转换为有限浮点数。

    Args:
        value: 规则中声明的 ``warn`` 或 ``crit`` 原始值。

    Returns:
        ``int`` / ``float`` 类型且有限时返回浮点数；``bool``、字符串、
        ``None``、``NaN``、``Infinity`` 或其它类型返回 ``None``。

    Raises:
        无。
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    return None


def _coerce_parsed_number(value: Any, *, allow_string: bool) -> Optional[float]:
    """
    将巡检解析值转换为可用于阈值评估的有限浮点数。

    Args:
        value: JSON / KV / CSV 解析得到的字段原值。
        allow_string: 是否允许完整数字字符串；仅 KV / CSV 评估传 ``True``。

    Returns:
        有限数字返回浮点数；允许字符串时，前后空白数字和科学计数法也可转换；
        空串、``bool``、非完整数字、``NaN`` / ``Infinity`` 返回 ``None``。

    Raises:
        无；字符串转换失败会返回 ``None``。
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    if allow_string and isinstance(value, str) and value.strip():
        try:
            number = float(value)
        except ValueError:
            return None
        return number if math.isfinite(number) else None
    return None


# ---------------------------------------------------------------------------
# 规则规范化
# ---------------------------------------------------------------------------


def normalize_inspection_fields(
    raw: Optional[Sequence[Any]],
) -> list[InspectionFieldRule]:
    """
    将运维侧声明的字段规则 (dict 列表) 规范化为
    :class:`InspectionFieldRule` 实例。

    Args:
        raw: 原始规则列表, 可为 ``None``。

    Returns:
        规范化后的 :class:`InspectionFieldRule` 列表, 顺序与入参一致。

    Raises:
        ValueError: 任一字段不合法时抛出, 错误消息尽量包含 ``key`` 或
            ``index`` 上下文, 便于定位。

    校验规则:
        - ``raw`` 必须为 ``None`` 或可迭代的 ``list`` (其它类型抛 ``ValueError``)。
        - 元素必须为 ``dict``。
        - ``key`` / ``name_zh`` 必须为非空字符串。
        - ``unit`` 必须为 ``str``, 缺省默认为 ``""``。
        - ``direction`` 仅接受 ``"high"`` / ``"low"`` / ``"ignore"``。
        - ``key`` 在同一列表内必须唯一。
        - ``high`` / ``low`` 的 ``warn`` / ``crit`` 必须为有限数字
          (拒绝 ``bool`` / 字符串 / ``NaN`` / ``Infinity``); ``high`` 要求
          ``warn <= crit``, ``low`` 要求 ``warn >= crit`` (边界包含)。
        - ``ignore`` 的 ``warn`` / ``crit`` 必须缺省或显式 ``None``。
    """
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError(
            f"inspection_fields must be a list, got {type(raw).__name__}"
        )

    rules: list[InspectionFieldRule] = []
    seen_keys: set[str] = set()

    for idx, item in enumerate(raw):
        ctx = _format_key_context(idx, item)

        if not isinstance(item, dict):
            raise ValueError(
                f"inspection_fields[{idx}] must be a dict, got {type(item).__name__} {ctx}"
            )

        # key
        key = item.get("key")
        if not isinstance(key, str) or not key.strip():
            raise ValueError(
                f"inspection_fields[{idx}].key must be a non-empty string {ctx}"
            )
        if key in seen_keys:
            raise ValueError(
                f"inspection_fields[{idx}] duplicate key={key!r}"
            )
        seen_keys.add(key)

        # name_zh
        name_zh = item.get("name_zh")
        if not isinstance(name_zh, str) or not name_zh.strip():
            raise ValueError(
                f"inspection_fields[{idx}].name_zh must be a non-empty string {ctx}"
            )

        # unit (缺省默认 "")
        unit = item.get("unit", "")
        if not isinstance(unit, str):
            raise ValueError(
                f"inspection_fields[{idx}].unit must be a string {ctx}"
            )

        # direction
        direction = item.get("direction")
        if direction not in _VALID_DIRECTIONS:
            raise ValueError(
                f"inspection_fields[{idx}].direction must be one of "
                f"{_VALID_DIRECTIONS}, got {direction!r} {ctx}"
            )

        # warn / crit
        warn_raw = item.get("warn")
        crit_raw = item.get("crit")

        if direction == "ignore":
            if warn_raw is not None or crit_raw is not None:
                raise ValueError(
                    f"inspection_fields[{idx}] ignore rule must not specify warn/crit {ctx}"
                )
            rules.append(
                InspectionFieldRule(
                    key=key,
                    name_zh=name_zh,
                    unit=unit,
                    direction="ignore",
                    warn=None,
                    crit=None,
                )
            )
            continue

        # high / low 都需要有限数字
        warn = _validate_threshold_number(warn_raw)
        if warn is None:
            raise ValueError(
                f"inspection_fields[{idx}].warn must be a finite number, got {warn_raw!r} {ctx}"
            )
        crit = _validate_threshold_number(crit_raw)
        if crit is None:
            raise ValueError(
                f"inspection_fields[{idx}].crit must be a finite number, got {crit_raw!r} {ctx}"
            )

        if direction == "high":
            if not (warn <= crit):
                raise ValueError(
                    f"inspection_fields[{idx}] high rule requires warn <= crit, "
                    f"got warn={warn}, crit={crit} {ctx}"
                )
        else:  # low
            if not (warn >= crit):
                raise ValueError(
                    f"inspection_fields[{idx}] low rule requires warn >= crit, "
                    f"got warn={warn}, crit={crit} {ctx}"
                )

        rules.append(
            InspectionFieldRule(
                key=key,
                name_zh=name_zh,
                unit=unit,
                direction=direction,
                warn=warn,
                crit=crit,
            )
        )

    return rules


# ---------------------------------------------------------------------------
# 输出解析
# ---------------------------------------------------------------------------


def _parse_json(stdout: str) -> Any:
    """
    JSON 解析器: 取最后一行非空文本，解析为对象或数组。

    Args:
        stdout: 原始 stdout。

    Returns:
        解析后的 JSON 对象或数组。

    Raises:
        InspectionParseError: 输入为空、解析失败或顶层结果为 JSON 标量。
    """
    lines = [line for line in stdout.splitlines() if line.strip()]
    if not lines:
        raise InspectionParseError("inspection json output is empty")
    last_line = lines[-1]
    try:
        obj = json.loads(last_line)
    except json.JSONDecodeError as exc:
        raise InspectionParseError(
            f"inspection json output is not valid JSON: {exc.msg} (line={last_line!r})"
        ) from exc
    if not isinstance(obj, (dict, list)):
        raise InspectionParseError(
            "inspection json output must decode to an object or array, "
            f"got {type(obj).__name__}"
        )
    return obj


def _parse_kv(stdout: str) -> Mapping[str, str]:
    """
    KV 解析器: 每个非空行按第一个 ``=`` 切分为 ``key=value``。

    Args:
        stdout: 原始 stdout。

    Returns:
        字段字典 (value 始终为 ``str``)。

    Raises:
        InspectionParseError: 输入无任何有效键值对。
    """
    result: dict[str, str] = {}
    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if "=" not in line:
            raise InspectionParseError(
                f"inspection kv line missing '=': {line!r}"
            )
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            raise InspectionParseError(
                f"inspection kv line has empty key: {line!r}"
            )
        result[key] = value
    if not result:
        raise InspectionParseError("inspection kv output is empty")
    return result


def _parse_csv(stdout: str) -> Mapping[str, str]:
    """
    CSV 解析器: 第一行表头 + 第一条数据行, 使用标准库 :mod:`csv`。

    Args:
        stdout: 原始 stdout。

    Returns:
        字段字典 (value 始终为 ``str``)。

    Raises:
        InspectionParseError: 无表头、无数据行或解析失败。
    """
    reader = csv.reader(io.StringIO(stdout))
    try:
        header = next(reader)
    except StopIteration:
        raise InspectionParseError("inspection csv output has no header row")
    if not header:
        raise InspectionParseError("inspection csv output header is empty")
    try:
        first_row = next(reader)
    except StopIteration:
        raise InspectionParseError("inspection csv output has no data row")
    if len(first_row) < len(header):
        first_row = list(first_row) + [""] * (len(header) - len(first_row))
    result = {h: v for h, v in zip(header, first_row) if h}
    if not result:
        raise InspectionParseError("inspection csv output has no usable key")
    return result


def parse_inspection_output(
    parser: str,
    stdout: Optional[str],
) -> Any:
    """
    按 ``parser`` 类型解析 SSH / 巡检脚本输出的 stdout。

    Args:
        parser: 解析器类型, 取值 ``"json"`` / ``"kv"`` / ``"csv"`` /
            ``"raw"`` (大小写不敏感)。
        stdout: 原始 stdout; ``raw`` 解析器下可为空或 ``None``, 其它解析器
            下空 / 全空白输入会抛 :class:`InspectionParseError`。

    Returns:
        - ``"json"`` → :class:`dict` 或 :class:`list`
        - ``"kv"`` → :class:`dict` (value 为 ``str``)
        - ``"csv"`` → :class:`dict` (value 为 ``str``)
        - ``"raw"`` → 原样返回 ``stdout`` (``None`` 透传)

    Raises:
        InspectionParseError: 解析失败时抛出 (继承 ``ValueError``)。
    """
    if parser is None:
        raise InspectionParseError("inspection parser type is required")

    p = parser.strip().lower()

    if p == "raw":
        return stdout

    if stdout is None or not stdout.strip():
        raise InspectionParseError(
            f"inspection {p} output is empty"
        )

    if p == "json":
        return _parse_json(stdout)
    if p == "kv":
        return _parse_kv(stdout)
    if p == "csv":
        return _parse_csv(stdout)

    raise InspectionParseError(f"unknown inspection parser type: {parser!r}")


# ---------------------------------------------------------------------------
# 阈值评估
# ---------------------------------------------------------------------------


_STATUS_PRIORITY = {"pass": 0, "unassessed": 1, "warn": 2, "crit": 3}

# 巡检脚本输出 JSON 顶层声明「按数组展开」的特殊键名。
# 适用场景：脚本把每个磁盘 / 接口 / 分区输出一条结构化记录,顶层用
# ``{"disks":[{...},{...}]}`` 形式承载;评估器对声明的字段(如
# ``disk_used_pct``)在顶层缺失时,会读取该数组并对每个元素重复评估同一条规则。
_DISKS_ARRAY_KEY = "disks"


def _promote(current: str, candidate: str) -> str:
    """按 ``pass < unassessed < warn < crit`` 优先级取更高严重度。"""
    if _STATUS_PRIORITY[candidate] > _STATUS_PRIORITY[current]:
        return candidate
    return current


def _evaluate_high(value_num: float, warn: float, crit: float) -> str:
    """high 方向: ``>= crit`` => crit, ``>= warn`` => warn, 否则 pass。"""
    if value_num >= crit:
        return "crit"
    if value_num >= warn:
        return "warn"
    return "pass"


def _evaluate_low(value_num: float, warn: float, crit: float) -> str:
    """low 方向: ``<= crit`` => crit, ``<= warn`` => warn, 否则 pass。"""
    if value_num <= crit:
        return "crit"
    if value_num <= warn:
        return "warn"
    return "pass"


def _classify_single_value(
    rule: "InspectionFieldRule",
    raw_value: Any,
    *,
    allow_string: bool,
) -> str:
    """按规则方向与阈值, 把单个 ``raw_value`` 归一化为 ``pass`` / ``warn`` / ``crit``。

    Args:
        rule: 已规范化的字段规则, ``direction`` 必为 ``"high"`` 或 ``"low"``,
            ``warn`` / ``crit`` 已保证非 None。
        raw_value: 来自 ``parsed_values`` 或 ``disks`` 数组元素的原始值。
        allow_string: 是否允许完整有限数字字符串(同 :func:`_coerce_parsed_number`)。

    Returns:
        str: ``"pass"`` / ``"warn"`` / ``"crit"`` 之一, 非数值固定 ``"crit"``。
    """
    value_num = _coerce_parsed_number(raw_value, allow_string=allow_string)
    if value_num is None:
        return "crit"
    assert rule.warn is not None and rule.crit is not None
    if rule.direction == "high":
        return _evaluate_high(value_num, rule.warn, rule.crit)
    return _evaluate_low(value_num, rule.warn, rule.crit)


def _expand_disks_array(
    rule: "InspectionFieldRule",
    disks: List[Any],
    *,
    allow_string: bool,
) -> Tuple[Tuple["InspectionFieldResult", ...], str]:
    """把单条 ``high`` / ``low`` 规则应用到 ``disks`` 数组的每个元素。

    Args:
        rule: 已规范化的字段规则; 调用方须保证 ``direction in ("high","low")``。
        disks: 来自 ``parsed_values[_DISKS_ARRAY_KEY]`` 的数组。
        allow_string: 是否允许字符串形式的有限数字(同 :func:`_coerce_parsed_number`)。

    Returns:
        Tuple[Tuple[InspectionFieldResult, ...], str]: ``(字段结果元组, 最高状态)``。
        数组为空时返回 ``((), "crit")``, 供调用方决定是否要降级为单条
        ``crit`` 占位。
    """
    results: List[InspectionFieldResult] = []
    worst = "pass"
    for entry in disks:
        if not isinstance(entry, Mapping):
            # 非 Mapping 元素 (例如脚本误输出字符串 / 数字) 跳过,
            # 不污染整体结果; 不计入 worst。
            continue
        if rule.key not in entry:
            # 单个元素缺少目标字段, 也跳过(局部噪音);
            # 调用方负责处理「整列都没值」的最坏情况。
            continue
        raw_value = entry[rule.key]
        status = _classify_single_value(rule, raw_value, allow_string=allow_string)
        mount = entry.get("mount")
        message = ""
        if isinstance(mount, str) and mount:
            message = f"磁盘 {mount}"
        results.append(
            InspectionFieldResult(
                key=rule.key,
                name_zh=rule.name_zh,
                unit=rule.unit,
                value=raw_value,
                status=status,
                message=message,
                warn=rule.warn,
                crit=rule.crit,
            )
        )
        worst = _promote(worst, status)
    return tuple(results), worst


def evaluate_inspection_fields(
    parsed_values: Any,
    rules: Iterable[InspectionFieldRule],
    parser: str,
) -> InspectionEvaluation:
    """
    根据阈值规则对 ``parsed_values`` 做评估, 产出每个字段的结果与总状态。

    Args:
        parsed_values: 解析后的值；JSON 可为对象或数组，KV / CSV 为字段字典，
            ``raw`` 解析器下为原始字符串。
        rules: 已规范化的 :class:`InspectionFieldRule` 可迭代对象。
        parser: 解析器类型 (``"json"`` / ``"kv"`` / ``"csv"`` / ``"raw"``);
            用于判断是否能进行结构化评估。

    Returns:
        :class:`InspectionEvaluation` 实例。

    行为约定:
        - 无规则 → 总状态 ``"unassessed"``, ``error_message=""``。
        - 全部 ``ignore`` 规则 → 总状态 ``"unassessed"``, 各字段
          ``status="unassessed"`` (原始 ``value`` 仍保留)。
        - 含 ``high`` / ``low`` 规则但 ``parser == "raw"`` →
          总状态 ``"crit"``, ``error_message`` 解释 raw 解析器不支持
          结构化阈值评估。
        - 声明字段缺失 / 非数值 (``bool`` 也不算) → 该字段 ``status="crit"``,
          ``value`` 保留 (缺失为 ``None``, 非数值保留原值)。KV / CSV 的完整
          有限数字字符串可转换后参与评估；JSON 字符串仍视为非数值。
        - high: ``value >= crit`` => crit, ``value >= warn`` => warn,
          否则 pass。
        - low: ``value <= crit`` => crit, ``value <= warn`` => warn,
          否则 pass。
        - 总状态优先级: crit > warn > pass; ``unassessed`` 不下拉其它字段
          的严重度。
        - **disks 数组展开**：当声明的 ``high`` / ``low`` 字段在顶层缺失,
          但存在 ``disks`` 数组(``parsed_values["disks"]`` 是 ``list``)
          时, 对每个元素重复运行该规则; ``field_results`` 顺序与数组顺序
          一致, ``message`` 携带 ``"磁盘 <mount>"`` 上下文; 数组元素非
          ``Mapping`` 或缺字段的元素跳过(不污染整体结果); 数组为空或
          所有元素都缺字段 → 该字段 ``crit`` + message 含
          ``"disks 数组为空"``。仅作用于 ``disk_used_pct`` 类顶层缺失
          场景, 不影响其它字段的原有路径。
    """
    rules_list = list(rules)
    normalized_parser = (parser or "").strip().lower()

    # 1) 无规则 -> unassessed
    if not rules_list:
        return InspectionEvaluation(
            parsed_values=parsed_values,
            fields=(),
            status="unassessed",
            error_message="",
        )

    # 2) 全部 ignore -> unassessed, 但仍保留各字段原始值
    has_structured = any(r.direction in ("high", "low") for r in rules_list)

    if not has_structured:
        fields: list[InspectionFieldResult] = []
        for r in rules_list:
            raw_value = parsed_values.get(r.key) if isinstance(parsed_values, Mapping) else None
            fields.append(
                InspectionFieldResult(
                    key=r.key,
                    name_zh=r.name_zh,
                    unit=r.unit,
                    value=raw_value,
                    status="unassessed",
                    message="",
                    warn=r.warn,
                    crit=r.crit,
                )
            )
        return InspectionEvaluation(
            parsed_values=parsed_values,
            fields=tuple(fields),
            status="unassessed",
            error_message="",
        )

    # 3) raw 解析器无法做结构化阈值评估
    if normalized_parser == "raw":
        # 仍尽量输出字段列表 (status=unassessed) 以便前端展示字段元数据,
        # 但总状态为 crit 并写明错误。
        fields = []
        for r in rules_list:
            fields.append(
                InspectionFieldResult(
                    key=r.key,
                    name_zh=r.name_zh,
                    unit=r.unit,
                    value=None,
                    status="unassessed",
                    message="raw 解析器不支持结构化阈值评估",
                    warn=r.warn,
                    crit=r.crit,
                )
            )
        return InspectionEvaluation(
            parsed_values=parsed_values,
            fields=tuple(fields),
            status="crit",
            error_message="raw 解析器不支持结构化阈值评估, 请改用 json / kv / csv 解析器",
        )

    # 4) 结构化评估：独立映射用于字段查询，保留 parsed_values 原值
    structured_values: Mapping[str, Any]
    if isinstance(parsed_values, Mapping):
        structured_values = parsed_values
    else:
        structured_values = {}

    overall = "pass"
    fields = []
    for r in rules_list:
        if r.direction == "ignore":
            raw_value = structured_values.get(r.key)
            fields.append(
                InspectionFieldResult(
                    key=r.key,
                    name_zh=r.name_zh,
                    unit=r.unit,
                    value=raw_value,
                    status="unassessed",
                    message="",
                    warn=r.warn,
                    crit=r.crit,
                )
            )
            continue

        if r.key not in structured_values:
            # 顶层字段缺失时, 检查是否存在 ``disks`` 数组, 若有则按数组
            # 展开评估; 没有再按「字段缺失」返回 crit。
            disks_value = structured_values.get(_DISKS_ARRAY_KEY)
            if isinstance(disks_value, list):
                expanded, worst_status = _expand_disks_array(
                    r,
                    disks_value,
                    allow_string=normalized_parser in ("kv", "csv"),
                )
                if expanded:
                    fields.extend(expanded)
                    overall = _promote(overall, worst_status)
                    continue
                # 数组为空或所有元素均缺字段 -> 降级为单条 crit 占位,
                # 与「字段在解析结果中缺失」语义对齐。
                fields.append(
                    InspectionFieldResult(
                        key=r.key,
                        name_zh=r.name_zh,
                        unit=r.unit,
                        value=None,
                        status="crit",
                        message=(
                            f"字段 {r.key} 在解析结果中缺失(disks 数组"
                            f"为空或所有元素均不含 {r.key})"
                        ),
                        warn=r.warn,
                        crit=r.crit,
                    )
                )
                overall = _promote(overall, "crit")
                continue

            fields.append(
                InspectionFieldResult(
                    key=r.key,
                    name_zh=r.name_zh,
                    unit=r.unit,
                    value=None,
                    status="crit",
                    message=f"字段 {r.key} 在解析结果中缺失",
                    warn=r.warn,
                    crit=r.crit,
                )
            )
            overall = _promote(overall, "crit")
            continue

        raw_value = structured_values[r.key]
        value_num = _coerce_parsed_number(
            raw_value,
            allow_string=normalized_parser in ("kv", "csv"),
        )
        if value_num is None:
            # bool / 空串 / 非数字 / NaN / Infinity 等均视为非数值 -> crit
            fields.append(
                InspectionFieldResult(
                    key=r.key,
                    name_zh=r.name_zh,
                    unit=r.unit,
                    value=raw_value,
                    status="crit",
                    message=(
                        f"字段 {r.key} 值不是有限数字 (类型={type(raw_value).__name__})"
                    ),
                    warn=r.warn,
                    crit=r.crit,
                )
            )
            overall = _promote(overall, "crit")
            continue

        assert r.warn is not None and r.crit is not None  # 类型缩窄, normalize 已保证
        if r.direction == "high":
            status = _evaluate_high(value_num, r.warn, r.crit)
        else:  # low
            status = _evaluate_low(value_num, r.warn, r.crit)

        fields.append(
            InspectionFieldResult(
                key=r.key,
                name_zh=r.name_zh,
                unit=r.unit,
                value=raw_value,
                status=status,
                message="",
                warn=r.warn,
                crit=r.crit,
            )
        )
        overall = _promote(overall, status)

    return InspectionEvaluation(
        parsed_values=parsed_values,
        fields=tuple(fields),
        status=overall,
        error_message="",
    )