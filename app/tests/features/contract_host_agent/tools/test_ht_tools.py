# -*- coding:utf-8 -*-
"""
HtTools 测试模块

覆盖：
- validate_prerequisites 工具可导入
- validate_prerequisites 要件齐全路径自动向 store 写入 approval/ready/{sid}=True
- validate_prerequisites 非成功路径（no_documents/no_requirements/invalid_format）不写 store
- validate_prerequisites 成功路径同步 HtAgentState.is_check=True
- check_approval 函数已删除（不可导入）
- HtAgentConfig.get_tools() 不再含 check_approval

Date: 2026-08-20
"""
import json
from unittest.mock import patch


# ============================================================
# 辅助：构造最简 runtime mock + 跟踪 store 调用 + 真实 ToolMessage/Command
# ============================================================


class _FakeStoreValue:
    """模拟 langgraph store get 返回对象的 value 容器"""

    def __init__(self, value):
        self.value = value


class _FakeStore:
    """模拟 langgraph BaseStore 子集：put/get 调用追踪与回放。

    - put(namespace, key, value): 记录调用并保存到内部 _data
    - get(namespace, key): 返回 _FakeStoreValue(value) 或 None
    """

    def __init__(self):
        self.puts = []  # [(namespace_tuple, key, value), ...]
        self._data = {}

    def put(self, namespace, key, value):
        self.puts.append((namespace, key, value))
        self._data[(namespace, key)] = value

    def get(self, namespace, key):
        if (namespace, key) not in self._data:
            return None
        return _FakeStoreValue(self._data[(namespace, key)])


class _RealToolMessage:
    """绕过 conftest 全局 Mock 的轻量 ToolMessage，仅供本测试读 content。"""

    def __init__(self, content="", tool_call_id=None, **kwargs):
        self.content = content
        self.tool_call_id = tool_call_id


class _FakeRuntime:
    """满足 HtTools 调用的最简 ToolRuntime 占位（属性非 dict）。"""

    def __init__(self, store, session_id="sess_test", tool_call_id="call_test", store_id="store_test"):
        self.store = store
        self.tool_call_id = tool_call_id
        self.context = {
            "store_id": store_id,
            "session_id": session_id,
        }


def _last_message(cmd):
    """从 Command 返回中提取最后一条 ToolMessage 的 JSON content 字典。"""
    messages = cmd.update.get("messages") or []
    return json.loads(messages[-1].content)


def _invoke_validate_with_fakes(store, session_id="sess_test"):
    """调用 validate_prerequisites 真实函数本体（绕过 @tool StructuredTool 包装）。

    说明：conftest 全局 mock 了 langchain.tools.tool 为 identity 装饰器，
    所以 validate_prerequisites 在测试环境下就是普通函数；同时 mock 了
    langchain_core.messages.ToolMessage，本测试用 _RealToolMessage 替换。
    """
    from app.features.contract_host_agent.tools import HtTools

    runtime = _FakeRuntime(store, session_id=session_id)
    with patch.object(HtTools, "ToolMessage", _RealToolMessage):
        cmd = HtTools.validate_prerequisites.func(runtime) if hasattr(HtTools.validate_prerequisites, "func") else HtTools.validate_prerequisites(runtime)
    return cmd


# ============================================================
# P0: 导入/存在性
# ============================================================


def test_validate_prerequisites_importable():
    """P0: validate_prerequisites 工具可导入。"""
    from app.features.contract_host_agent.tools.HtTools import validate_prerequisites

    assert validate_prerequisites is not None


def test_check_approval_removed():
    """P0: check_approval 工具已删除，导入应抛出 ImportError。

    背景：2026-08-20 将 check_approval 的副作用合并入 validate_prerequisites，
    原 @tool 函数必须彻底移除，避免 LLM/历史会话仍可调用造成行为分叉。
    """
    import pytest

    with pytest.raises(ImportError):
        from app.features.contract_host_agent.tools.HtTools import check_approval  # noqa: F401


# ============================================================
# P1: 成功路径 - 自动写入审批就绪信号
# ============================================================


def test_validate_prerequisites_success_writes_approval_ready_signal():
    """
    P1: 要件齐全（status=success）路径自动向 store 写入 approval/ready/{sid}=True。

    合并后契约：validate_prerequisites 不再依赖 LLM 单独调一次 check_approval，
    要件齐全即视为审批就绪，写入 store 信号并同步 state。
    """
    store = _FakeStore()
    # 预先植入"供地合同"+"成交确认书"两类要件，模拟上游已上传
    store.put((("store_test"),), "approval/prereq/sess_001", {
        "sess_001": {
            "供地合同": [{"id": "1"}],
            "成交确认书": [{"id": "2"}],
        }
    })
    store.puts.clear()  # 只关注本调用的副作用

    cmd = _invoke_validate_with_fakes(store, session_id="sess_001")
    payload = _last_message(cmd)

    # 返回体契约
    assert payload["status"] == "success"
    assert payload["approval_ready"] is True
    assert payload["approval_signal_written"] is True
    assert "供地合同" in payload["uploaded_requirements"]

    # store 副作用契约：namespace=(store_id,), key=approval/ready/{sid}, value=True
    matched = [
        (ns, key, val) for (ns, key, val) in store.puts
        if key == "approval/ready/sess_001"
    ]
    assert len(matched) == 1, f"预期写一次 approval/ready 信号，实际: {store.puts}"
    ns, key, val = matched[0]
    assert ns == ("store_test",)
    assert val is True


def test_validate_prerequisites_success_updates_state_is_check():
    """
    P1: 要件齐全路径同步 HtAgentState.is_check=True。

    背景：HtAgentState.is_check 字段原本由 check_approval 写入；合并后必须由
    validate_prerequisites 接力，否则审批 Agent 永远不会收到"启动"信号。
    """
    store = _FakeStore()
    store.put((("store_test"),), "approval/prereq/sess_002", {
        "sess_002": {
            "供地合同": [{"id": "1"}],
            "会议纪要": [{"id": "2"}],
        }
    })

    cmd = _invoke_validate_with_fakes(store, session_id="sess_002")
    assert cmd.update.get("is_check") is True, "成功路径必须写 is_check=True"


# ============================================================
# P1: 失败路径 - 不写 store
# ============================================================


def test_validate_prerequisites_no_documents_does_not_write_signal():
    """
    P1: 无任何已上传文档时（status=no_documents）不写 store ready 信号。

    语义与原 check_approval(ischeck=False) 对齐：要件为空时审批未就绪。
    """
    store = _FakeStore()
    cmd = _invoke_validate_with_fakes(store, session_id="sess_empty")
    payload = _last_message(cmd)

    assert payload["status"] == "no_documents"
    assert all("approval/ready" not in key for (_, key, _) in store.puts)


def test_validate_prerequisites_no_requirements_does_not_write_signal():
    """
    P1: 所有要件均为空时（status=no_requirements）不写 store ready 信号。
    """
    store = _FakeStore()
    store.put((("store_test"),), "approval/prereq/sess_no_req", {
        "sess_no_req": {
            "供地合同": [],
            "成交确认书": [],
        }
    })
    store.puts.clear()

    cmd = _invoke_validate_with_fakes(store, session_id="sess_no_req")
    payload = _last_message(cmd)

    assert payload["status"] == "no_requirements"
    assert all("approval/ready" not in key for (_, key, _) in store.puts)


def test_validate_prerequisites_invalid_format_does_not_write_signal():
    """
    P1: store 返回非 dict 结构（status=invalid_format）时不写 store ready 信号。
    """
    store = _FakeStore()
    # 模拟上游写入非字典结构（如序列化异常后写入字符串）
    store.put((("store_test"),), "approval/prereq/sess_bad", "not_a_dict")
    store.puts.clear()

    cmd = _invoke_validate_with_fakes(store, session_id="sess_bad")
    payload = _last_message(cmd)

    assert payload["status"] == "invalid_format"
    assert all("approval/ready" not in key for (_, key, _) in store.puts)


# ============================================================
# P1: 工具注册
# ============================================================


def test_ht_agent_config_tools_no_longer_exposes_check_approval():
    """
    P1: HtAgentConfig.get_tools() 返回的工具列表不再含 check_approval。

    合并后必须从 Agent 工具注册表中移除，避免 LLM 看到已不存在的工具。
    """
    from app.features.contract_host_agent.config.HtAgentConfig import HtAgentConfig

    cfg = HtAgentConfig()
    tools, _ = cfg.get_tools()

    def _name(t):
        return getattr(t, "name", None) or getattr(t, "__name__", str(t))

    names = {_name(t) for t in (tools or [])}
    assert "check_approval" not in names, "check_approval 必须从 HtAgentConfig 工具列表移除"
    assert "validate_prerequisites" in names
    assert "warn_issue" in names
    assert "get_approval_result" in names