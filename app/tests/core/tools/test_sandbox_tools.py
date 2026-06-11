# -*- coding:utf-8 -*-
"""
测试 app.core.tools.SandboxTools 沙箱工具模块

验证模块导入、sandbox 工具存在性及基本功能。

Date: 2026-06-12
"""

import json
from unittest.mock import MagicMock, patch, Mock

import pytest


# =============================================================================
# 模块导入与存在性测试 (P0)
# =============================================================================


def test_sandbox_tools_importable():
    """
    测试 SandboxTools 模块可正常导入且不抛出异常。

    Returns:
        None

    Raises:
        ImportError: 模块导入失败时抛出
    """
    import app.core.tools.SandboxTools as sandbox_tools
    assert sandbox_tools is not None


def test_sandbox_tool_exists():
    """
    测试 sandbox 工具函数在模块中存在。

    Returns:
        None

    Raises:
        AssertionError: 函数不存在时抛出
    """
    from app.core.tools.SandboxTools import sandbox
    assert callable(sandbox)


def test_sandbox_system_prompt_exists():
    """
    测试 SANDBOX_SYSTEM_PROMPT 在模块中存在。

    Returns:
        None

    Raises:
        AssertionError: 常量不存在时抛出
    """
    from app.core.tools.SandboxTools import SANDBOX_SYSTEM_PROMPT
    assert isinstance(SANDBOX_SYSTEM_PROMPT, str)
    assert len(SANDBOX_SYSTEM_PROMPT) > 0
    assert '沙箱' in SANDBOX_SYSTEM_PROMPT or 'sandbox' in SANDBOX_SYSTEM_PROMPT.lower()


# =============================================================================
# 成功路径测试 (P1)
# =============================================================================


@pytest.fixture
def mock_runtime():
    """
    创建 Mock runtime 对象用于测试。

    Returns:
        MagicMock: 模拟的 ToolRuntime 对象
    """
    runtime = MagicMock()
    runtime.tool_call_id = 'call_test_123'
    runtime.context = {'session_id': 'test-session-456'}
    return runtime


@patch('app.core.tools.SandboxTools.ModelFactory.create_model')
@patch('app.core.tools.SandboxTools.create_deep_agent')
@patch('app.core.tools.SandboxTools.DockerSandboxMiddleware')
@patch('app.core.tools.SandboxTools.get_stream_writer')
def test_sandbox_success_path(
    mock_get_writer,
    mock_middleware_class,
    mock_create_agent,
    mock_create_model,
    mock_runtime,
):
    """
    测试 sandbox 工具正常执行流程。

    Mock create_deep_agent 和 DockerSandboxMiddleware，验证正常流程。

    Args:
        mock_get_writer: Mock 的 get_stream_writer
        mock_middleware_class: Mock 的 DockerSandboxMiddleware 类
        mock_create_agent: Mock 的 create_deep_agent
        mock_create_model: Mock 的 ModelFactory.create_model
        mock_runtime: Mock 的 ToolRuntime 对象

    Returns:
        None
    """
    from app.core.tools.SandboxTools import sandbox

    # 设置 Mock
    mock_writer = MagicMock()
    mock_get_writer.return_value = mock_writer

    mock_middleware = MagicMock()
    mock_middleware_class.return_value = mock_middleware

    mock_model = MagicMock()
    mock_create_model.return_value = mock_model

    # 模拟子智能体流式输出
    mock_agent = MagicMock()
    mock_agent.stream.return_value = [
        ('updates', {'node': 'agent'}),
        ('values', {'structured_response': {'answer': '测试执行成功'}}),
    ]
    mock_create_agent.return_value = mock_agent

    # 执行测试
    result = sandbox('执行测试任务', runtime=mock_runtime)

    # 验证结果
    assert result is not None
    assert hasattr(result, 'update')
    assert 'messages' in result.update

    # 验证中间件被创建
    mock_middleware_class.assert_called_once()
    call_kwargs = mock_middleware_class.call_args.kwargs
    assert call_kwargs['session_id'] == 'test-session-456'

    # 验证子智能体被创建
    mock_create_agent.assert_called_once()

    # 验证资源被清理
    mock_middleware.cleanup.assert_called_once()


# =============================================================================
# 错误处理测试 (P1)
# =============================================================================


@patch('app.core.tools.SandboxTools.ModelFactory.create_model')
@patch('app.core.tools.SandboxTools.DockerSandboxMiddleware')
@patch('app.core.tools.SandboxTools.get_stream_writer')
def test_sandbox_docker_error(
    mock_get_writer,
    mock_middleware_class,
    mock_create_model,
    mock_runtime,
):
    """
    测试 Docker 不可用时返回 error Command。

    Args:
        mock_get_writer: Mock 的 get_stream_writer
        mock_middleware_class: Mock 的 DockerSandboxMiddleware 类
        mock_create_model: Mock 的 ModelFactory.create_model
        mock_runtime: Mock 的 ToolRuntime 对象

    Returns:
        None
    """
    from app.core.tools.SandboxTools import sandbox

    # 设置 Mock
    mock_writer = MagicMock()
    mock_get_writer.return_value = mock_writer

    # 模拟 Docker 初始化失败
    mock_middleware_class.side_effect = RuntimeError('Docker daemon 未运行')

    mock_model = MagicMock()
    mock_create_model.return_value = mock_model

    # 执行测试
    result = sandbox('执行测试任务', runtime=mock_runtime)

    # 验证返回错误 Command
    assert result is not None
    assert hasattr(result, 'update')
    assert 'messages' in result.update


@patch('app.core.tools.SandboxTools.ModelFactory.create_model')
@patch('app.core.tools.SandboxTools.create_deep_agent')
@patch('app.core.tools.SandboxTools.DockerSandboxMiddleware')
@patch('app.core.tools.SandboxTools.get_stream_writer')
def test_sandbox_cleanup_on_error(
    mock_get_writer,
    mock_middleware_class,
    mock_create_agent,
    mock_create_model,
    mock_runtime,
):
    """
    测试异常时 backend.cleanup() 被调用。

    Args:
        mock_get_writer: Mock 的 get_stream_writer
        mock_middleware_class: Mock 的 DockerSandboxMiddleware 类
        mock_create_agent: Mock 的 create_deep_agent
        mock_create_model: Mock 的 ModelFactory.create_model
        mock_runtime: Mock 的 ToolRuntime 对象

    Returns:
        None
    """
    from app.core.tools.SandboxTools import sandbox

    # 设置 Mock
    mock_writer = MagicMock()
    mock_get_writer.return_value = mock_writer

    mock_middleware = MagicMock()
    mock_middleware_class.return_value = mock_middleware

    mock_model = MagicMock()
    mock_create_model.return_value = mock_model

    # 模拟子智能体执行时抛出异常
    mock_agent = MagicMock()
    mock_agent.stream.side_effect = Exception('子智能体执行异常')
    mock_create_agent.return_value = mock_agent

    # 执行测试 - 注意：由于异常发生在 stream 中，cleanup 应该在异常处理中被调用
    # 但由于当前实现在异常处理中也会调用 cleanup，我们需要验证这一点
    try:
        result = sandbox('执行测试任务', runtime=mock_runtime)
    except Exception:
        pass  # 忽略异常，我们只关心 cleanup 是否被调用

    # 验证资源被清理（即使发生异常）
    # 注意：当前实现在异常时也会调用 cleanup
    mock_middleware.cleanup.assert_called_once()


# =============================================================================
# _extract_last_ai_text 辅助函数测试
# =============================================================================


class MockAIMessage:
    """模拟 AIMessage 用于测试"""
    def __init__(self, content):
        self.content = content

    def __class_getitem__(cls, item):
        return cls


class MockHumanMessage:
    """模拟 HumanMessage 用于测试"""
    def __init__(self, content):
        self.content = content

    def __class_getitem__(cls, item):
        return cls


def test_extract_last_ai_text_with_string_content():
    """
    测试 _extract_last_ai_text 从字符串内容消息中提取文本。

    Returns:
        None
    """
    from app.core.tools.SandboxTools import _extract_last_ai_text

    messages = [
        MockHumanMessage('用户消息'),
        MockAIMessage('AI 回复内容'),
    ]

    result = _extract_last_ai_text(messages)
    assert result == 'AI 回复内容'


def test_extract_last_ai_text_with_list_content():
    """
    测试 _extract_last_ai_text 从列表内容消息中提取文本。

    Returns:
        None
    """
    from app.core.tools.SandboxTools import _extract_last_ai_text

    messages = [
        MockAIMessage([{'type': 'text', 'text': '文本块内容'}]),
    ]

    result = _extract_last_ai_text(messages)
    assert result == '文本块内容'


def test_extract_last_ai_text_empty_messages():
    """
    测试 _extract_last_ai_text 对空消息列表返回空字符串。

    Returns:
        None
    """
    from app.core.tools.SandboxTools import _extract_last_ai_text

    result = _extract_last_ai_text([])
    assert result == ''


def test_extract_last_ai_text_no_ai_message():
    """
    测试 _extract_last_ai_text 当没有 AI 消息时返回空字符串。

    Returns:
        None
    """
    from app.core.tools.SandboxTools import _extract_last_ai_text

    messages = [MockHumanMessage('用户消息')]

    result = _extract_last_ai_text(messages)
    assert result == ''
