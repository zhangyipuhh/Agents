# -*- coding:utf-8 -*-
"""
巡检字段规则解析与阈值评估模块（parser）单元测试。

覆盖计划中的 12 类场景 + 边界包含关系：

1.  dataclass 不可变性（frozen）
2.  normalize_inspection_fields 基本合法输入（high/low/ignore）
3.  normalize_inspection_fields: None -> []
4.  normalize_inspection_fields: 非 list 抛 ValueError 且消息含 key（顶层 key）
5.  normalize_inspection_fields: unit 缺省默认为 ""，非 str 抛 ValueError
6.  normalize_inspection_fields: direction 非法值抛 ValueError
7.  normalize_inspection_fields: key 重复抛 ValueError 且消息含 key
8.  normalize_inspection_fields: high/low 必须有有限数字 warn/crit（bool/字符串/NaN/Infinity 拒绝）
9.  normalize_inspection_fields: high 要 warn<=crit，low 要 warn>=crit（边界包含关系）
10. normalize_inspection_fields: ignore 的 warn/crit 必须缺省或 None
11. parse_inspection_output: json / kv / csv / raw 各类正常解析
12. parse_inspection_output: 空/非法输出抛 InspectionParseError（raw 允许空）
13. evaluate_inspection_fields: 全部规则 / 全 ignore -> unassessed
14. evaluate_inspection_fields: 含 high/low 但 raw -> crit（错误说明）
15. evaluate_inspection_fields: 字段缺失 / 非数值（bool 也不算）-> 对应 crit
16. evaluate_inspection_fields: high 使用 >=crit/ >=warn，low 使用 <=crit/ <=warn，critical 优先
17. evaluate_inspection_fields: 保留原始 value
18. evaluate_inspection_fields: disks 数组展开（顶层缺字段时按数组重复评估）

测试风格遵循 `app/tests/shared/utils/` 既有约定：纯内存，无外部依赖。
"""
from __future__ import annotations

import math
from dataclasses import FrozenInstanceError

import pytest

from app.shared.utils.inspection.parser import (
    InspectionEvaluation,
    InspectionFieldResult,
    InspectionFieldRule,
    InspectionParseError,
    evaluate_inspection_fields,
    normalize_inspection_fields,
    parse_inspection_output,
)


# ---------------------------------------------------------------------------
# 1. dataclass 不可变性
# ---------------------------------------------------------------------------


def test_inspection_field_rule_is_frozen_dataclass():
    """InspectionFieldRule 必须是 frozen dataclass。"""
    rule = InspectionFieldRule(
        key="cpu",
        name_zh="CPU 使用率",
        unit="%",
        direction="high",
        warn=80.0,
        crit=95.0,
    )
    with pytest.raises(FrozenInstanceError):
        rule.key = "memory"  # type: ignore[misc]


def test_inspection_field_result_is_frozen_dataclass():
    """InspectionFieldResult 必须是 frozen dataclass。"""
    result = InspectionFieldResult(
        key="cpu",
        name_zh="CPU 使用率",
        unit="%",
        value=88.0,
        status="warn",
        message="",
        warn=80.0,
        crit=95.0,
    )
    with pytest.raises(FrozenInstanceError):
        result.status = "pass"  # type: ignore[misc]


def test_inspection_evaluation_is_frozen_dataclass():
    """InspectionEvaluation 必须是 frozen dataclass，且 error_message 默认为空字符串。"""
    evaluation = InspectionEvaluation(
        parsed_values={"cpu": 88.0},
        fields=(),
        status="warn",
    )
    assert evaluation.error_message == ""
    with pytest.raises(FrozenInstanceError):
        evaluation.status = "pass"  # type: ignore[misc]


def test_inspection_parse_error_inherits_value_error():
    """InspectionParseError 必须继承自 ValueError。"""
    assert issubclass(InspectionParseError, ValueError)
    err = InspectionParseError("boom")
    assert isinstance(err, ValueError)
    assert str(err) == "boom"


# ---------------------------------------------------------------------------
# 2-10. normalize_inspection_fields
# ---------------------------------------------------------------------------


def test_normalize_none_returns_empty_list():
    """None 输入 -> 空列表。"""
    assert normalize_inspection_fields(None) == []


def test_normalize_accepts_valid_high_low_ignore_rules():
    """合法 high/low/ignore 规则全部正常解析；unit 缺省默认为空字符串。"""
    raw = [
        {"key": "cpu", "name_zh": "CPU", "direction": "high", "warn": 80, "crit": 95},
        {"key": "mem_free", "name_zh": "剩余内存", "unit": "MB", "direction": "low", "warn": 1024, "crit": 256},
        {"key": "host", "name_zh": "主机名", "direction": "ignore"},
    ]
    rules = normalize_inspection_fields(raw)
    assert len(rules) == 3

    cpu = rules[0]
    assert isinstance(cpu, InspectionFieldRule)
    assert cpu.key == "cpu"
    assert cpu.name_zh == "CPU"
    assert cpu.unit == ""  # unit 缺省 -> ""
    assert cpu.direction == "high"
    assert cpu.warn == 80.0
    assert cpu.crit == 95.0

    mem = rules[1]
    assert mem.unit == "MB"
    assert mem.direction == "low"
    assert mem.warn == 1024.0
    assert mem.crit == 256.0

    host = rules[2]
    assert host.direction == "ignore"
    assert host.warn is None
    assert host.crit is None


def test_normalize_non_list_raises_value_error():
    """非 list 输入 -> ValueError。"""
    with pytest.raises(ValueError):
        normalize_inspection_fields({"key": "cpu"})  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        normalize_inspection_fields("not a list")  # type: ignore[arg-type]


def test_normalize_non_dict_item_raises_value_error_with_key_context():
    """列表中非 dict 项 -> ValueError，消息包含该项 key（若有）。"""
    raw = [{"key": "cpu", "name_zh": "CPU"}, ["bad"]]
    with pytest.raises(ValueError) as excinfo:
        normalize_inspection_fields(raw)
    # 至少应提到 "cpu" 上下文（来自前面合法的项），或提到索引/位置
    msg = str(excinfo.value)
    assert "cpu" in msg or "1" in msg


def test_normalize_empty_key_or_name_zh_raises_value_error():
    """key 或 name_zh 为空字符串 -> ValueError，消息含 key。"""
    with pytest.raises(ValueError) as excinfo:
        normalize_inspection_fields([{"key": "", "name_zh": "CPU"}])
    assert "key" in str(excinfo.value)

    with pytest.raises(ValueError) as excinfo:
        normalize_inspection_fields([{"key": "cpu", "name_zh": "  "}])
    # name_zh 必须非空
    assert "name_zh" in str(excinfo.value) or "cpu" in str(excinfo.value)


def test_normalize_unit_must_be_str():
    """unit 非字符串 -> ValueError；unit 缺省必须默认为空字符串。"""
    raw = [{"key": "cpu", "name_zh": "CPU", "unit": 123, "direction": "high", "warn": 1, "crit": 2}]
    with pytest.raises(ValueError):
        normalize_inspection_fields(raw)

    # unit 缺省默认为 ""
    rules = normalize_inspection_fields([{"key": "x", "name_zh": "X", "direction": "ignore"}])
    assert rules[0].unit == ""


def test_normalize_direction_must_be_high_low_ignore():
    """direction 非法值 -> ValueError。"""
    raw = [{"key": "cpu", "name_zh": "CPU", "direction": "up", "warn": 1, "crit": 2}]
    with pytest.raises(ValueError) as excinfo:
        normalize_inspection_fields(raw)
    assert "up" in str(excinfo.value) or "direction" in str(excinfo.value)


def test_normalize_duplicate_key_raises_value_error_with_key():
    """key 重复 -> ValueError，消息含重复 key。"""
    raw = [
        {"key": "cpu", "name_zh": "CPU", "direction": "high", "warn": 1, "crit": 2},
        {"key": "cpu", "name_zh": "CPU2", "direction": "low", "warn": 3, "crit": 4},
    ]
    with pytest.raises(ValueError) as excinfo:
        normalize_inspection_fields(raw)
    assert "cpu" in str(excinfo.value)


def test_normalize_high_low_must_have_finite_numeric_warn_crit():
    """high/low 必须有有限数字 warn/crit；bool / 字符串 / NaN / Infinity 全部拒绝。"""
    # bool 拒绝（即使在 Python 中 bool 是 int 子类）
    with pytest.raises(ValueError):
        normalize_inspection_fields([
            {"key": "cpu", "name_zh": "CPU", "direction": "high", "warn": True, "crit": 90},
        ])
    # 字符串拒绝
    with pytest.raises(ValueError):
        normalize_inspection_fields([
            {"key": "cpu", "name_zh": "CPU", "direction": "high", "warn": "80", "crit": 90},
        ])
    # NaN 拒绝
    with pytest.raises(ValueError):
        normalize_inspection_fields([
            {"key": "cpu", "name_zh": "CPU", "direction": "high", "warn": math.nan, "crit": 90},
        ])
    # Infinity 拒绝
    with pytest.raises(ValueError):
        normalize_inspection_fields([
            {"key": "cpu", "name_zh": "CPU", "direction": "high", "warn": 80, "crit": math.inf},
        ])


def test_normalize_high_requires_warn_le_crit_boundary_inclusive():
    """high: warn <= crit（边界包含：warn == crit 合法；warn > crit 抛 ValueError）。"""
    # warn == crit 合法
    rules = normalize_inspection_fields([
        {"key": "cpu", "name_zh": "CPU", "direction": "high", "warn": 90, "crit": 90},
    ])
    assert rules[0].warn == 90.0 and rules[0].crit == 90.0

    # warn > crit 非法
    with pytest.raises(ValueError) as excinfo:
        normalize_inspection_fields([
            {"key": "cpu", "name_zh": "CPU", "direction": "high", "warn": 95, "crit": 80},
        ])
    assert "cpu" in str(excinfo.value)


def test_normalize_low_requires_warn_ge_crit_boundary_inclusive():
    """low: warn >= crit（边界包含：warn == crit 合法；warn < crit 抛 ValueError）。"""
    # warn == crit 合法
    rules = normalize_inspection_fields([
        {"key": "disk_free", "name_zh": "剩余磁盘", "direction": "low", "warn": 10, "crit": 10},
    ])
    assert rules[0].warn == 10.0 and rules[0].crit == 10.0

    # warn < crit 非法
    with pytest.raises(ValueError) as excinfo:
        normalize_inspection_fields([
            {"key": "disk_free", "name_zh": "剩余磁盘", "direction": "low", "warn": 5, "crit": 10},
        ])
    assert "disk_free" in str(excinfo.value)


def test_normalize_ignore_must_not_have_warn_crit():
    """ignore 规则的 warn/crit 必须缺省或 None；非 None 抛 ValueError。"""
    # 缺省合法
    rules = normalize_inspection_fields([
        {"key": "host", "name_zh": "主机名", "direction": "ignore"},
    ])
    assert rules[0].warn is None and rules[0].crit is None

    # 显式 None 合法
    rules = normalize_inspection_fields([
        {"key": "host", "name_zh": "主机名", "direction": "ignore", "warn": None, "crit": None},
    ])
    assert rules[0].warn is None and rules[0].crit is None

    # 提供数字非法
    with pytest.raises(ValueError) as excinfo:
        normalize_inspection_fields([
            {"key": "host", "name_zh": "主机名", "direction": "ignore", "warn": 1, "crit": 2},
        ])
    assert "host" in str(excinfo.value)


# ---------------------------------------------------------------------------
# 11-12. parse_inspection_output
# ---------------------------------------------------------------------------


def test_parse_json_takes_last_non_empty_line():
    """json 解析器：取最后一行非空文本，使用 json.loads。"""
    stdout = '\nnoise line\n{"cpu": 88, "mem": 1024}\n'
    assert parse_inspection_output("json", stdout) == {"cpu": 88, "mem": 1024}

    # 多行 JSON：取最后一个非空行
    stdout = 'noise\n{"a": 1}\n{"a": 2}\n'
    assert parse_inspection_output("json", stdout) == {"a": 2}


def test_parse_json_preserves_top_level_array():
    """json 解析器应接受并保留顶层数组。"""
    parsed = parse_inspection_output("json", 'noise\n[{"cpu": 88}, 95]\n')

    assert parsed == [{"cpu": 88}, 95]


@pytest.mark.parametrize("scalar", ['"text"', "88", "null", "true", "false"])
def test_parse_json_rejects_top_level_scalar(scalar):
    """json 解析器应拒绝字符串、数字、null 和布尔标量。"""
    with pytest.raises(InspectionParseError):
        parse_inspection_output("json", scalar)


def test_parse_kv_splits_by_first_equals():
    """kv 解析器：每个非空行按第一个 '=' 分割为 key/value。"""
    stdout = "cpu=88\nmem_free=1024\nhostname=web01\n"
    assert parse_inspection_output("kv", stdout) == {
        "cpu": "88",
        "mem_free": "1024",
        "hostname": "web01",
    }

    # value 中含 '=' 时只切第一个
    stdout = "msg=hello=world\n"
    assert parse_inspection_output("kv", stdout) == {"msg": "hello=world"}


def test_parse_csv_first_row_header_second_row_data():
    """csv 解析器：第一行表头 + 第一条数据行，使用标准库 csv。"""
    stdout = "cpu,mem_free\n88,1024\n"
    assert parse_inspection_output("csv", stdout) == {"cpu": "88", "mem_free": "1024"}

    # 表头重复时只取第一行数据
    stdout = "cpu\n88\n99\n"
    assert parse_inspection_output("csv", stdout) == {"cpu": "88"}


def test_parse_raw_returns_stdout_as_is():
    """raw 解析器：原样返回 stdout。"""
    assert parse_inspection_output("raw", "anything goes\nreally\n") == "anything goes\nreally\n"
    # raw 允许空字符串
    assert parse_inspection_output("raw", "") == ""
    assert parse_inspection_output("raw", None) is None  # type: ignore[arg-type]


@pytest.mark.parametrize("parser", ["json", "kv", "csv"])
def test_parse_empty_or_invalid_output_raises_inspection_parse_error(parser):
    """json/kv/csv 的空或非法输出 -> InspectionParseError（继承 ValueError）。"""
    with pytest.raises(InspectionParseError):
        parse_inspection_output(parser, "")
    with pytest.raises(InspectionParseError):
        parse_inspection_output(parser, "   \n   \n")

    if parser == "json":
        with pytest.raises(InspectionParseError):
            parse_inspection_output("json", "not json at all\n")
    if parser == "csv":
        # 仅表头无数据行 -> 应视为非法（没有可解析数据）
        with pytest.raises(InspectionParseError):
            parse_inspection_output("csv", "key,value\n")
    if parser == "kv":
        # 仅空白行 -> 应视为非法
        with pytest.raises(InspectionParseError):
            parse_inspection_output("kv", "   \n   \n")


def test_parse_unknown_parser_type_raises_inspection_parse_error():
    """未知 parser 类型 -> InspectionParseError。"""
    with pytest.raises(InspectionParseError):
        parse_inspection_output("xml", "<cpu>88</cpu>")


# ---------------------------------------------------------------------------
# 13-17. evaluate_inspection_fields
# ---------------------------------------------------------------------------


def _rules_high_low():
    return normalize_inspection_fields([
        {"key": "cpu", "name_zh": "CPU", "direction": "high", "warn": 80, "crit": 95},
        {"key": "mem_free", "name_zh": "剩余内存", "unit": "MB", "direction": "low", "warn": 1024, "crit": 256},
    ])


def test_evaluate_no_rules_returns_unassessed():
    """无规则 -> unassessed，error_message 为空。"""
    evaluation = evaluate_inspection_fields({"cpu": 88.0}, [], parser="json")
    assert evaluation.status == "unassessed"
    assert evaluation.error_message == ""
    assert evaluation.fields == ()


def test_evaluate_all_ignore_rules_returns_unassessed():
    """全部 ignore 规则 -> unassessed；各字段仍出现在 fields 中（status=unassessed）。"""
    rules = normalize_inspection_fields([
        {"key": "host", "name_zh": "主机名", "direction": "ignore"},
    ])
    evaluation = evaluate_inspection_fields({"host": "web01"}, rules, parser="json")
    assert evaluation.status == "unassessed"
    assert evaluation.error_message == ""
    assert len(evaluation.fields) == 1
    assert evaluation.fields[0].status == "unassessed"
    assert evaluation.fields[0].value == "web01"


def test_evaluate_raw_with_structured_rules_returns_crit_with_error_message():
    """含 high/low 规则时传 raw 解析器 -> crit，error_message 解释原因。"""
    rules = _rules_high_low()
    evaluation = evaluate_inspection_fields("cpu=88\nmem_free=1024\n", rules, parser="raw")
    assert evaluation.status == "crit"
    assert evaluation.error_message  # 非空
    assert "raw" in evaluation.error_message or "结构化" in evaluation.error_message


def test_evaluate_missing_field_marks_crit_with_preserved_value():
    """声明字段缺失 -> 对应字段 crit，value 保留（None）。"""
    rules = _rules_high_low()
    # 仅有 cpu，没有 mem_free
    evaluation = evaluate_inspection_fields({"cpu": 88.0}, rules, parser="json")
    assert evaluation.status == "crit"

    by_key = {f.key: f for f in evaluation.fields}
    assert by_key["cpu"].status == "warn"
    assert by_key["cpu"].value == 88.0

    mem = by_key["mem_free"]
    assert mem.status == "crit"
    assert mem.value is None
    assert mem.message  # 非空错误说明


def test_evaluate_non_numeric_value_including_bool_marks_crit():
    """非数值（包括 bool）-> 对应字段 crit。"""
    rules = _rules_high_low()
    evaluation = evaluate_inspection_fields(
        {"cpu": True, "mem_free": "1024"}, rules, parser="json"
    )
    assert evaluation.status == "crit"
    by_key = {f.key: f for f in evaluation.fields}
    assert by_key["cpu"].status == "crit"
    assert by_key["cpu"].value is True  # bool 也算"非数值"
    # JSON 字符串不属于 KV / CSV 数值字符串转换范围
    assert by_key["mem_free"].status == "crit"


@pytest.mark.parametrize(
    ("parser", "stdout_template"),
    [
        ("kv", "cpu={value}\n"),
        ("csv", "cpu\n{value}\n"),
    ],
)
@pytest.mark.parametrize(
    ("value", "expected_status"),
    [
        (" 79 ", "pass"),
        ("8.8e1", "warn"),
        ("95", "crit"),
    ],
)
def test_evaluate_kv_csv_finite_numeric_strings_by_threshold(
    parser, stdout_template, value, expected_status
):
    """KV/CSV 的完整有限数字字符串应按阈值评估为 pass/warn/crit。"""
    rules = normalize_inspection_fields([
        {"key": "cpu", "name_zh": "CPU", "direction": "high", "warn": 80, "crit": 95},
    ])
    parsed = parse_inspection_output(parser, stdout_template.format(value=value))

    evaluation = evaluate_inspection_fields(parsed, rules, parser=parser)

    assert evaluation.status == expected_status
    assert evaluation.fields[0].status == expected_status
    assert evaluation.fields[0].value == parsed["cpu"]


@pytest.mark.parametrize("parser", ["kv", "csv"])
@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity", "", "12x", "true"])
def test_evaluate_kv_csv_rejects_non_finite_or_invalid_numeric_strings(parser, value):
    """KV/CSV 的空串、非有限值和非数字字符串应评估为 crit。"""
    rules = normalize_inspection_fields([
        {"key": "cpu", "name_zh": "CPU", "direction": "high", "warn": 80, "crit": 95},
    ])
    if parser == "kv":
        parsed = {"cpu": value}
    else:
        parsed = parse_inspection_output("csv", f"cpu\n{value}\n") if value else {"cpu": ""}

    evaluation = evaluate_inspection_fields(parsed, rules, parser=parser)

    assert evaluation.status == "crit"
    assert evaluation.fields[0].status == "crit"
    assert evaluation.fields[0].value == value


def test_evaluate_json_array_marks_declared_field_missing_and_preserves_array():
    """JSON 顶层数组有声明字段时应 crit，且 parsed_values 保留原数组。"""
    rules = normalize_inspection_fields([
        {"key": "cpu", "name_zh": "CPU", "direction": "high", "warn": 80, "crit": 95},
    ])
    parsed = parse_inspection_output("json", '[{"cpu": 88}]')

    evaluation = evaluate_inspection_fields(parsed, rules, parser="json")

    assert evaluation.status == "crit"
    assert evaluation.fields[0].status == "crit"
    assert evaluation.fields[0].value is None
    assert evaluation.parsed_values is parsed
    assert evaluation.parsed_values == [{"cpu": 88}]


def test_evaluate_non_mapping_input_preserves_original_value():
    """直接评估非 Mapping 输入时应按字段缺失处理但不替换 parsed_values。"""
    rules = normalize_inspection_fields([
        {"key": "cpu", "name_zh": "CPU", "direction": "high", "warn": 80, "crit": 95},
    ])
    parsed = ("not", "a", "mapping")

    evaluation = evaluate_inspection_fields(parsed, rules, parser="json")

    assert evaluation.status == "crit"
    assert evaluation.fields[0].status == "crit"
    assert evaluation.parsed_values is parsed


def test_evaluate_high_uses_ge_warn_and_ge_crit_critical_priority():
    """high 方向：>=warn=warn, >=crit=crit；total 状态：crit 优先于 warn 优先于 pass。"""
    rules = _rules_high_low()
    parsed = {"cpu": 92.0, "mem_free": 4096.0}  # cpu=warn, mem=pass
    evaluation = evaluate_inspection_fields(parsed, rules, parser="json")
    by_key = {f.key: f for f in evaluation.fields}
    assert by_key["cpu"].status == "warn"  # 80 <= 92 < 95
    assert by_key["mem_free"].status == "pass"  # 4096 > 1024
    assert evaluation.status == "warn"

    # 边界：刚好 == warn -> warn
    parsed = {"cpu": 80.0, "mem_free": 4096.0}
    evaluation = evaluate_inspection_fields(parsed, rules, parser="json")
    by_key = {f.key: f for f in evaluation.fields}
    assert by_key["cpu"].status == "warn"
    assert evaluation.status == "warn"

    # 边界：刚好 == crit -> crit
    parsed = {"cpu": 95.0, "mem_free": 4096.0}
    evaluation = evaluate_inspection_fields(parsed, rules, parser="json")
    by_key = {f.key: f for f in evaluation.fields}
    assert by_key["cpu"].status == "crit"
    assert evaluation.status == "crit"  # crit 优先


def test_evaluate_low_uses_le_warn_and_le_crit():
    """low 方向：<=warn=warn, <=crit=crit；边界包含。"""
    rules = _rules_high_low()
    # mem_free=2048 (warn 阈值 1024, crit 256): 2048 > 1024 -> pass
    evaluation = evaluate_inspection_fields({"cpu": 10.0, "mem_free": 2048.0}, rules, parser="json")
    by_key = {f.key: f for f in evaluation.fields}
    assert by_key["mem_free"].status == "pass"
    assert evaluation.status == "pass"

    # 边界：刚好 == warn -> warn
    evaluation = evaluate_inspection_fields({"cpu": 10.0, "mem_free": 1024.0}, rules, parser="json")
    by_key = {f.key: f for f in evaluation.fields}
    assert by_key["mem_free"].status == "warn"
    assert evaluation.status == "warn"

    # 边界：刚好 == crit -> crit
    evaluation = evaluate_inspection_fields({"cpu": 10.0, "mem_free": 256.0}, rules, parser="json")
    by_key = {f.key: f for f in evaluation.fields}
    assert by_key["mem_free"].status == "crit"
    assert evaluation.status == "crit"


def test_evaluate_critical_priority_overall_status():
    """总状态：crit > warn > pass；任意字段 crit 整体 crit。"""
    rules = _rules_high_low()
    # cpu=crit (96), mem_free=pass (4096)
    evaluation = evaluate_inspection_fields({"cpu": 96.0, "mem_free": 4096.0}, rules, parser="json")
    assert evaluation.status == "crit"

    # cpu=pass (10), mem_free=crit (200)
    evaluation = evaluate_inspection_fields({"cpu": 10.0, "mem_free": 200.0}, rules, parser="json")
    assert evaluation.status == "crit"

    # 全部 pass
    evaluation = evaluate_inspection_fields({"cpu": 10.0, "mem_free": 4096.0}, rules, parser="json")
    assert evaluation.status == "pass"


def test_evaluate_preserves_original_value_and_metadata():
    """结果保留原始 value、name_zh、unit、warn、crit 元数据。"""
    rules = _rules_high_low()
    parsed = {"cpu": 88.5, "mem_free": 2048.0}
    evaluation = evaluate_inspection_fields(parsed, rules, parser="json")
    by_key = {f.key: f for f in evaluation.fields}
    cpu = by_key["cpu"]
    assert cpu.value == 88.5  # 原值未改动
    assert cpu.name_zh == "CPU"
    assert cpu.unit == ""
    assert cpu.warn == 80.0
    assert cpu.crit == 95.0

    mem = by_key["mem_free"]
    assert mem.value == 2048.0
    assert mem.name_zh == "剩余内存"
    assert mem.unit == "MB"
    assert mem.warn == 1024.0
    assert mem.crit == 256.0


def test_evaluate_string_keys_only_in_parsed_match_rule_keys():
    """parsed_values 的 key 包含未声明字段时被忽略；声明字段缺失 -> crit。"""
    rules = _rules_high_low()
    parsed = {"cpu": 50.0, "extra_field": "ignored"}
    evaluation = evaluate_inspection_fields(parsed, rules, parser="json")
    by_key = {f.key: f for f in evaluation.fields}
    # 只产出声明字段
    assert set(by_key.keys()) == {"cpu", "mem_free"}
    # 缺失 mem_free
    assert by_key["mem_free"].status == "crit"
    assert evaluation.status == "crit"  # 因为 mem_free 缺失


def test_evaluate_mixed_ignore_and_structured_rules_returns_structured_status():
    """ignore 与 high/low 混合：总状态由结构化规则决定，ignore 字段 status=unassessed。"""
    rules = normalize_inspection_fields([
        {"key": "host", "name_zh": "主机名", "direction": "ignore"},
        {"key": "cpu", "name_zh": "CPU", "direction": "high", "warn": 80, "crit": 95},
    ])
    parsed = {"host": "web01", "cpu": 50.0}
    evaluation = evaluate_inspection_fields(parsed, rules, parser="json")
    assert evaluation.status == "pass"
    by_key = {f.key: f for f in evaluation.fields}
    assert by_key["host"].status == "unassessed"
    assert by_key["cpu"].status == "pass"


# ---------------------------------------------------------------------------
# 18. disks 数组展开（顶层缺字段时按数组重复评估同一条规则）
# ---------------------------------------------------------------------------


def test_evaluate_inspection_fields_disks_array_expands_rule():
    """disks 数组存在且顶层缺 disk_used_pct 时, 对每个元素重复评估同一条规则。

    断言:
        - field_results 顺序与 disks 数组顺序一致, 长度等于 disks 元素数。
        - 每条结果 value 为对应元素的 disk_used_pct 原值。
        - 每条结果 message 携带该元素的 mount 上下文。
        - status 与单条 high 阈值规则一致 (pass / crit)。
    """
    rules = normalize_inspection_fields([
        {
            "key": "disk_used_pct",
            "name_zh": "磁盘使用率",
            "unit": "%",
            "direction": "high",
            "warn": 80,
            "crit": 90,
        }
    ])
    parsed_values = {
        "disks": [
            {"mount": "/", "disk_used_pct": 42},
            {"mount": "/data", "disk_used_pct": 92},
        ],
        "mem_used_pct": 38,
    }

    evaluation = evaluate_inspection_fields(parsed_values, rules, parser="json")

    assert evaluation.status == "crit"
    assert len(evaluation.fields) == 2
    by_index = list(evaluation.fields)
    assert by_index[0].key == "disk_used_pct"
    assert by_index[0].value == 42
    assert by_index[0].status == "pass"
    assert by_index[0].message == "磁盘 /"
    assert by_index[1].key == "disk_used_pct"
    assert by_index[1].value == 92
    assert by_index[1].status == "crit"
    assert by_index[1].message == "磁盘 /data"
    # parsed_values 保留原值, 不被替换为 {} 或被改写。
    assert evaluation.parsed_values is parsed_values


def test_evaluate_inspection_fields_disks_array_empty_marks_crit():
    """disks 数组为空时, 字段以单条 crit 占位, message 含「disks 数组为空」。

    断言:
        - field_results 长度为 1, status == "crit"。
        - message 包含「disks 数组为空」字样, 便于排查脚本侧输出缺失。
        - 整体 status 也是 crit。
    """
    rules = normalize_inspection_fields([
        {
            "key": "disk_used_pct",
            "name_zh": "磁盘使用率",
            "unit": "%",
            "direction": "high",
            "warn": 80,
            "crit": 90,
        }
    ])
    parsed_values = {"disks": []}

    evaluation = evaluate_inspection_fields(parsed_values, rules, parser="json")

    assert evaluation.status == "crit"
    assert len(evaluation.fields) == 1
    field_result = evaluation.fields[0]
    assert field_result.key == "disk_used_pct"
    assert field_result.status == "crit"
    assert field_result.value is None
    assert "disks 数组为空" in field_result.message


def test_evaluate_inspection_fields_disks_array_partial_missing_or_bad_values():
    """disks 数组里某个元素值非法时, 单元素判 crit, 其它元素按规则正常评估。

    覆盖三种局部异常:
        - mount 缺失 -> message 不带磁盘前缀, 但仍可评估。
        - disk_used_pct 是非数字字符串 (JSON) -> 该元素 crit。
        - 元素是非 Mapping (脚本误输出) -> 跳过, 不污染整体结果。
    """
    rules = normalize_inspection_fields([
        {
            "key": "disk_used_pct",
            "name_zh": "磁盘使用率",
            "unit": "%",
            "direction": "high",
            "warn": 80,
            "crit": 90,
        }
    ])
    parsed_values = {
        "disks": [
            {"disk_used_pct": 40},  # 无 mount, pass
            {"mount": "/data", "disk_used_pct": "bad"},  # 非数值, crit
            "not-a-mapping",  # 跳过
            {"mount": "/var", "disk_used_pct": 95},  # crit
        ]
    }

    evaluation = evaluate_inspection_fields(parsed_values, rules, parser="json")

    # 整体由最坏状态决定 -> crit。
    assert evaluation.status == "crit"
    # 跳过非 Mapping 元素, 实际产出 3 条结果。
    assert len(evaluation.fields) == 3
    statuses = [f.status for f in evaluation.fields]
    assert statuses == ["pass", "crit", "crit"]
    # 第一条无 mount, message 为空。
    assert evaluation.fields[0].message == ""
    # 第二条带 mount 但值非数值, message 仍带 mount, value 保留原字符串。
    assert evaluation.fields[1].message == "磁盘 /data"
    assert evaluation.fields[1].value == "bad"
    # 第三条 mount=/var, value=95 -> crit (>= 90)。
    assert evaluation.fields[2].message == "磁盘 /var"
    assert evaluation.fields[2].value == 95


def test_evaluate_inspection_fields_no_disks_key_still_crit():
    """顶层既无 disk_used_pct 也无 disks 数组时, 字段按「缺失」判 crit, 行为不变。"""
    rules = normalize_inspection_fields([
        {
            "key": "disk_used_pct",
            "name_zh": "磁盘使用率",
            "unit": "%",
            "direction": "high",
            "warn": 80,
            "crit": 90,
        }
    ])
    parsed_values = {"mem_used_pct": 40}

    evaluation = evaluate_inspection_fields(parsed_values, rules, parser="json")

    assert evaluation.status == "crit"
    assert len(evaluation.fields) == 1
    field_result = evaluation.fields[0]
    assert field_result.key == "disk_used_pct"
    assert field_result.status == "crit"
    assert field_result.value is None
    # 没有 disks 数组时, 走原「字段在解析结果中缺失」路径。
    assert "disks 数组为空" not in field_result.message
    assert "在解析结果中缺失" in field_result.message


def test_parse_disks_array_regression_bug_user_reported():
    """回归测试: 用户报告的真实坏输出 (缺逗号 + cpu_idle_pct 带 %id 后缀)。

    断言: JSON 解析失败抛 ``InspectionParseError``, 消息含原始出错行片段,
    便于运维侧排查脚本输出格式问题。这是契约的"反面"用例, 防止将来
    评估器对坏 JSON 静默放行。
    """
    broken_stdout = (
        '{"disks":[{"mount":"/","disk_used_pct":28}'
        '{"mount":"/boot/efi","disk_used_pct":1}'
        '{"mount":"/oradb","disk_used_pct":6}'
        '{"mount":"/oragrid","disk_used_pct":48}],'
        '"mem_used_pct":80,"cpu_idle_pct":92.5%id,"load_1m":2.77}'
    )
    with pytest.raises(InspectionParseError) as exc_info:
        parse_inspection_output("json", broken_stdout)
    # 错误消息应包含原始行片段, 便于定位。
    assert "not valid JSON" in str(exc_info.value)


def test_evaluate_disks_array_matches_user_real_linux_output():
    """真实 Linux 输出 (修复后): 4 盘 disks 数组 + mem_used_pct=80 (warn) 触发告警。

    锁定修复后的契约:
        - 4 个 disk_used_pct 字段结果, message 带对应 mount;
        - mem_used_pct=80 (== warn 阈值) → 该字段 warn (边界包含);
        - cpu_idle_pct=92.5 (>= warn=20) → 该字段 pass (low 方向);
        - load_1m=2.77 (< warn=4.0) → 该字段 pass;
        - 整体 status 由最坏状态决定 (mem_used_pct 唯一 warn) → warn。
    """
    rules = normalize_inspection_fields([
        {"key": "disk_used_pct", "name_zh": "磁盘使用率", "unit": "%",
         "direction": "high", "warn": 80, "crit": 90},
        {"key": "mem_used_pct", "name_zh": "内存使用率", "unit": "%",
         "direction": "high", "warn": 80, "crit": 90},
        {"key": "cpu_idle_pct", "name_zh": "CPU 空闲率", "unit": "%",
         "direction": "low", "warn": 20, "crit": 10},
        {"key": "load_1m", "name_zh": "1 分钟平均负载", "unit": "",
         "direction": "high", "warn": 4.0, "crit": 8.0},
    ])
    parsed_values = parse_inspection_output("json", (
        '{"disks":[{"mount":"/","disk_used_pct":28},'
        '{"mount":"/boot/efi","disk_used_pct":1},'
        '{"mount":"/oradb","disk_used_pct":6},'
        '{"mount":"/oragrid","disk_used_pct":48}],'
        '"mem_used_pct":80,"cpu_idle_pct":92.5,"load_1m":2.77}'
    ))

    evaluation = evaluate_inspection_fields(parsed_values, rules, parser="json")

    assert evaluation.status == "warn"
    # 4 盘 → 4 条 disk_used_pct, 按 mount 顺序。
    disk_results = [f for f in evaluation.fields if f.key == "disk_used_pct"]
    assert len(disk_results) == 4
    assert [r.message for r in disk_results] == [
        "磁盘 /", "磁盘 /boot/efi", "磁盘 /oradb", "磁盘 /oragrid",
    ]
    assert [r.value for r in disk_results] == [28, 1, 6, 48]
    # 其它顶层字段正常评估。
    by_key = {f.key: f for f in evaluation.fields if f.key != "disk_used_pct"}
    assert by_key["mem_used_pct"].status == "warn"   # 80 == warn 边界包含
    assert by_key["cpu_idle_pct"].status == "pass"   # 92.5 >= 20
    assert by_key["load_1m"].status == "pass"        # 2.77 < 4.0


def test_parse_windows_powershell_disks_array_with_escaped_backslashes():
    """Windows PowerShell 输出: mount 含 ``\\`` 转义, 解析后应保留为 ``\\``。

    锁定修复后的契约 (避免双引号字符串转义陷阱):
        - PowerShell 手工拼接 JSON 时 ``C:\\`` 应被序列化为 ``C:\\\\``;
        - Python ``json.loads`` 反序列化后 mount 仍是 ``C:\\``;
        - disks 数组展开为 2 条 disk_used_pct, message 含 ``磁盘 C:\\``;
        - uptime_hours 是 ignore → unassessed, 其它字段 pass。
    """
    stdout = (
        '{"disks":['
        '{"mount":"C:\\\\","disk_used_pct":45.5},'
        '{"mount":"D:\\\\","disk_used_pct":22.0}],'
        '"mem_used_pct":45.3,"cpu_used_pct":12,"uptime_hours":142.5}'
    )
    parsed = parse_inspection_output("json", stdout)

    assert parsed["disks"][0]["mount"] == "C:\\"
    assert parsed["disks"][1]["mount"] == "D:\\"

    rules = normalize_inspection_fields([
        {"key": "disk_used_pct", "name_zh": "磁盘使用率", "unit": "%",
         "direction": "high", "warn": 80, "crit": 90},
        {"key": "mem_used_pct", "name_zh": "内存使用率", "unit": "%",
         "direction": "high", "warn": 80, "crit": 90},
        {"key": "cpu_used_pct", "name_zh": "CPU 使用率", "unit": "%",
         "direction": "high", "warn": 80, "crit": 95},
        {"key": "uptime_hours", "name_zh": "系统运行时间", "unit": "小时",
         "direction": "ignore", "warn": None, "crit": None},
    ])
    evaluation = evaluate_inspection_fields(parsed, rules, parser="json")

    assert evaluation.status == "pass"
    disk_results = [f for f in evaluation.fields if f.key == "disk_used_pct"]
    assert len(disk_results) == 2
    assert disk_results[0].message == "磁盘 C:\\"
    assert disk_results[1].message == "磁盘 D:\\"
    # ignore 字段 → unassessed, 保留 value。
    by_key = {f.key: f for f in evaluation.fields if f.key != "disk_used_pct"}
    assert by_key["uptime_hours"].status == "unassessed"
    assert by_key["uptime_hours"].value == 142.5