# -*- coding:utf-8 -*-
"""
Pytest 全局配置与 Mock 基础设施模块

提供所有测试共享的 fixtures 和外部依赖 Mock。
核心原则：通过 autouse fixture 在测试会话开始前集中 Mock 所有外部依赖，
确保测试纯内存运行、无需 PostgreSQL、无需真实 LLM、无需真实文件系统。

Date: 2026-06-08
"""

import sys
from pathlib import Path
from unittest.mock import Mock

# 将项目根目录加入 Python 路径，确保 mcpClient 等本地包可导入
_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import types

# 提前 mock 模块级导入的外部依赖，避免测试收集阶段因缺失包而失败
sys.modules["asyncpg"] = Mock()
sys.modules["mcpClient"] = Mock()
sys.modules["mcpClient.shared"] = Mock()
sys.modules["mcpClient.shared.config_loader"] = Mock()
sys.modules["mcpClient.core"] = Mock()
sys.modules["mcpClient.core.unified_mcp_client"] = Mock()

# 2026-06-23 新增：mock filesystem_encoding_fix 模块，使 apply_fix 成为 no-op。
# app.main 模块加载时会调用 apply_fix()，其内部访问 EncodingSafeFileSearchMiddleware._python_search
# 等属性在纯 Mock 环境下不存在，导致 AttributeError。将 apply_fix 替换为 no-op 可让
# app/tests/ 根目录下的测试也能通过 app fixture 导入 app.main。
_fs_fix = types.ModuleType("app.shared.tools.middleware.filesystem_encoding_fix")
_fs_fix.apply_fix = lambda: None
sys.modules["app.shared.tools.middleware.filesystem_encoding_fix"] = _fs_fix

# mock langchain 及其子模块（使用 ModuleType 以支持 from xxx import yyy）
for _lc_mod in [
    "langchain", "langchain.tools", "langchain.messages", "langchain.chat_models", "langchain_core", "langchain_core.messages",
    "langchain_core.runnables", "langchain_core.documents", "langchain_text_splitters", "langchain_community",
    "langchain_community.document_loaders", "langchain_openai", "langchain_anthropic", "langchain_deepseek", "langchain_ollama",
    "langchain_google_genai", "langchain_mcp_adapters", "langmem", "langmem.short_term", "trustcall", "deepagents",
]:
    sys.modules[_lc_mod] = types.ModuleType(_lc_mod)

# 为 langchain 子模块添加常用属性
# tool 装饰器需要保留被装饰的原始函数，否则测试无法调用 .func
# 注意：必须兼容 @tool 与 @tool(...) 两种写法

def _tool_identity(*args, **kwargs):
    """identity 装饰器：@tool 与 @tool(...) 均返回原函数。"""
    if len(args) == 1 and callable(args[0]) and not kwargs:
        return args[0]

    def _decorator(func):
        return func

    return _decorator


sys.modules["langchain.tools"].tool = _tool_identity

# 2026-06-15 新增：mock langchain.agents 子模块（FilesystemReadTools.explore 依赖）
# FilesystemReadTools.py 顶层 import：
#   from langchain.agents import create_agent
#   from langchain.agents.middleware import ContextEditingMiddleware, TodoListMiddleware
#   from langchain.agents.middleware.context_editing import ClearToolUsesEdit
_agents_mod = types.ModuleType("langchain.agents")
_agents_mod.create_agent = Mock()
sys.modules["langchain.agents"] = _agents_mod

_agents_mw_mod = types.ModuleType("langchain.agents.middleware")
_agents_mw_mod.__path__ = []  # 让它表现为 package 以支持子模块
_agents_mw_mod.ContextEditingMiddleware = Mock()
_agents_mw_mod.TodoListMiddleware = Mock()
sys.modules["langchain.agents.middleware"] = _agents_mw_mod

_agents_mw_ce_mod = types.ModuleType("langchain.agents.middleware.context_editing")
_agents_mw_ce_mod.ClearToolUsesEdit = Mock()
sys.modules["langchain.agents.middleware.context_editing"] = _agents_mw_ce_mod

# 2026-06-15 新增：encoding_safe_file_search 依赖
#   from langchain.agents.middleware.types import AgentMiddleware
_agents_mw_types = types.ModuleType("langchain.agents.middleware.types")
_agents_mw_types.AgentMiddleware = Mock()
sys.modules["langchain.agents.middleware.types"] = _agents_mw_types


class _ToolRuntime(Mock):
    """支持泛型下标的 ToolRuntime Mock"""
    def __class_getitem__(cls, item):
        return cls


sys.modules["langchain.tools"].ToolRuntime = _ToolRuntime
sys.modules["langchain_core.documents"].Document = Mock()
sys.modules["langchain_community.document_loaders"].TextLoader = Mock()
sys.modules["langchain_community.document_loaders"].CSVLoader = Mock()
sys.modules["langchain_community.document_loaders"].JSONLoader = Mock()
sys.modules["langchain_community.document_loaders"].UnstructuredMarkdownLoader = Mock()
sys.modules["langchain_community.document_loaders"].PyPDFLoader = Mock()
sys.modules["langchain.messages"].ToolMessage = Mock()
sys.modules["langchain.messages"].HumanMessage = Mock()
sys.modules["langchain.chat_models"].init_chat_model = Mock()
sys.modules["langchain_core.messages"].ToolMessage = Mock()
sys.modules["langchain_core.messages"].AIMessage = Mock()
sys.modules["langchain_core.messages"].HumanMessage = Mock()
sys.modules["langchain_core.messages"].SystemMessage = Mock()
sys.modules["langchain_core.messages"].BaseMessage = Mock()
sys.modules["langchain_core.messages"].AnyMessage = Mock()
sys.modules["langchain_core.messages.utils"] = types.ModuleType("langchain_core.messages.utils")
sys.modules["langchain_core.messages.utils"].trim_messages = Mock()
sys.modules["langchain_core.messages.utils"].count_tokens_approximately = Mock()
sys.modules["langchain_core.runnables"].RunnableConfig = Mock()


class _Runnable:
    """模拟 langchain Runnable 基类，供 isinstance 检查使用。"""


class _RunnableLambda(_Runnable):
    """模拟 langchain RunnableLambda，保存可调用对象并支持 invoke。"""

    def __init__(self, func):
        self.func = func

    def invoke(self, _input, config=None):
        return self.func(_input)


sys.modules["langchain_core.runnables"].Runnable = _Runnable
sys.modules["langchain_core.runnables"].RunnableLambda = _RunnableLambda
sys.modules["langchain_core.tools"] = types.ModuleType("langchain_core.tools")


class _BaseTool:
    """模拟 langchain BaseTool，支持类继承"""
    pass


sys.modules["langchain_core.tools"].BaseTool = _BaseTool
sys.modules["langchain_core.tools"].StructuredTool = _BaseTool
# 2026-06-15 新增：encoding_safe_file_search 依赖
sys.modules["langchain_core.tools"].tool = _tool_identity

class _RecursiveCharacterTextSplitter:
    """模拟 RecursiveCharacterTextSplitter，提供基础 split_text 功能"""
    def __init__(self, chunk_size: int = 4000, chunk_overlap: int = 50, **kwargs):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def split_text(self, text: str) -> list:
        if not text:
            return [""]
        chunks = []
        start = 0
        while start < len(text):
            end = min(start + self.chunk_size, len(text))
            chunks.append(text[start:end])
            start += max(1, self.chunk_size - self.chunk_overlap)
            if end == len(text):
                break
        return chunks if chunks else [""]


sys.modules["langchain_text_splitters"].RecursiveCharacterTextSplitter = _RecursiveCharacterTextSplitter

# mock 其他常用缺失模块
# aiofiles 需要保留真实文件能力，因此提供一个支持异步上下文管理器的轻量 mock
class _AiofilesOpenContext:
    """模拟 aiofiles.open 返回的异步文件上下文。

    将真实文件对象包装为 async read/write，以满足业务代码中 await f.write() 的调用。
    """
    def __init__(self, path, *args, **kwargs):
        self._path = path
        self._args = args
        self._kwargs = kwargs
        self._f = None

    async def __aenter__(self):
        self._f = open(self._path, *self._args, **self._kwargs)
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self._f:
            self._f.close()

    async def read(self):
        return self._f.read()

    async def write(self, data):
        return self._f.write(data)


class _AiofilesMock:
    """模拟 aiofiles 模块，open 返回真实文件操作的异步上下文。"""
    def open(self, path, *args, **kwargs):
        return _AiofilesOpenContext(path, *args, **kwargs)


sys.modules["aiofiles"] = _AiofilesMock()
sys.modules["aiofiles.os"] = Mock()
sys.modules["sse_starlette"] = Mock()
sys.modules["sse_starlette.sse"] = Mock()
sys.modules["markitdown"] = Mock()
sys.modules["magika"] = Mock()
sys.modules["unstructured"] = Mock()
sys.modules["unstructured.partition"] = Mock()
sys.modules["unstructured.partition.auto"] = Mock()
sys.modules["spacy"] = Mock()
sys.modules["cv2"] = Mock()
sys.modules["pypdf"] = Mock()
sys.modules["pymupdf"] = Mock()
sys.modules["fitz"] = Mock()
# docx 及其子模块必须使用 ModuleType 并设置 __path__ 以支持子模块导入
_docx = types.ModuleType("docx")
_docx.__path__ = []
sys.modules["docx"] = _docx
sys.modules["docx"].Document = Mock()

sys.modules["docx.shared"] = types.ModuleType("docx.shared")
sys.modules["docx.shared"].Pt = Mock()
sys.modules["docx.shared"].Cm = Mock()
sys.modules["docx.shared"].RGBColor = Mock()
sys.modules["docx.shared"].Inches = Mock()

_docx_enum = types.ModuleType("docx.enum")
_docx_enum.__path__ = []
sys.modules["docx.enum"] = _docx_enum
sys.modules["docx.enum.text"] = types.ModuleType("docx.enum.text")
sys.modules["docx.enum.text"].WD_ALIGN_PARAGRAPH = Mock()
sys.modules["docx.enum.section"] = types.ModuleType("docx.enum.section")
sys.modules["docx.enum.section"].WD_SECTION_START = Mock()

_docx_oxml = types.ModuleType("docx.oxml")
_docx_oxml.__path__ = []
sys.modules["docx.oxml"] = _docx_oxml
sys.modules["docx.oxml.ns"] = types.ModuleType("docx.oxml.ns")
sys.modules["docx.oxml.ns"].qn = Mock()
sys.modules["docx.oxml"].OxmlElement = Mock()

_docx_text = types.ModuleType("docx.text")
_docx_text.__path__ = []
sys.modules["docx.text"] = _docx_text
sys.modules["docx.text.run"] = types.ModuleType("docx.text.run")
sys.modules["docx.text.run"].Run = Mock()
sys.modules["PIL"] = Mock()
sys.modules["PIL.Image"] = Mock()
sys.modules["PIL.ImageDraw"] = Mock()
sys.modules["PIL.ImageFont"] = Mock()
sys.modules["numpy"] = Mock()

# deepagents 需要作为包支持子模块
sys.modules["deepagents"] = types.ModuleType("deepagents")
sys.modules["deepagents.backends"] = types.ModuleType("deepagents.backends")
sys.modules["deepagents.backends.sandbox"] = types.ModuleType("deepagents.backends.sandbox")
sys.modules["deepagents.backends.protocol"] = types.ModuleType("deepagents.backends.protocol")
sys.modules["deepagents.backends.filesystem"] = types.ModuleType("deepagents.backends.filesystem")
sys.modules["deepagents.middleware"] = types.ModuleType("deepagents.middleware")
sys.modules["deepagents.middleware.filesystem"] = types.ModuleType("deepagents.middleware.filesystem")

# mock deepagents 核心类
class _ExecuteResponse:
    def __init__(self, output="", exit_code=0, truncated=False):
        self.output = output
        self.exit_code = exit_code
        self.truncated = truncated

class _BaseSandbox:
    pass

sys.modules["deepagents.backends.sandbox"].BaseSandbox = _BaseSandbox
sys.modules["deepagents.backends.protocol"].ExecuteResponse = _ExecuteResponse

class _FileUploadResponse:
    def __init__(self, path="", error=None):
        self.path = path
        self.error = error

class _FileDownloadResponse:
    def __init__(self, path="", content=None, error=None):
        self.path = path
        self.content = content
        self.error = error

class _FileData(dict):
    """模拟 deepagents FileData。"""
    pass


class _ReadResult:
    """模拟 deepagents ReadResult。"""
    def __init__(self, file_data=None, error=None):
        self.file_data = file_data
        self.error = error


class _WriteResult:
    """模拟 deepagents WriteResult。"""
    def __init__(self, path="", error=None):
        self.path = path
        self.error = error


sys.modules["deepagents.backends.protocol"].FileUploadResponse = _FileUploadResponse
sys.modules["deepagents.backends.protocol"].FileDownloadResponse = _FileDownloadResponse
sys.modules["deepagents.backends.protocol"].FileData = _FileData
sys.modules["deepagents.backends.protocol"].ReadResult = _ReadResult
sys.modules["deepagents.backends.protocol"].WriteResult = _WriteResult

class _FilesystemMiddleware:
    def __init__(self, backend=None, **kwargs):
        self.backend = backend

sys.modules["deepagents.middleware.filesystem"].FilesystemMiddleware = _FilesystemMiddleware

# mock create_deep_agent
sys.modules["deepagents"].create_deep_agent = Mock(return_value=Mock())

class _FilesystemBackend:
    """模拟 deepagents FilesystemBackend"""
    def __init__(self, *args, **kwargs):  # 2026-06-15 接受任意构造参数（explore 工具传 root_dir/virtual_mode）
        pass
    @staticmethod
    def _ripgrep_search(*args, **kwargs):
        return []
    # 2026-06-23 新增：filesystem_encoding_fix 模块加载时访问 FilesystemBackend.read，
    # 必须提供该属性否则 app.main 导入失败（AttributeError）
    @staticmethod
    def read(*args, **kwargs):
        return None


sys.modules["deepagents.backends.filesystem"].FilesystemBackend = _FilesystemBackend

# 2026-06-18 新增：模拟 LocalShellBackend，供 DockerSandboxMiddleware fallback 测试使用
class _LocalShellBackend:
    """模拟 deepagents LocalShellBackend"""
    def __init__(self, *args, **kwargs):
        pass

_mock_deepagents_backends_local_shell = types.ModuleType("deepagents.backends.local_shell")
_mock_deepagents_backends_local_shell.LocalShellBackend = _LocalShellBackend
sys.modules["deepagents.backends.local_shell"] = _mock_deepagents_backends_local_shell
sys.modules["deepagents"].LocalShellBackend = _LocalShellBackend

# 2026-06-15 新增：把 FilesystemMiddleware / FilesystemBackend 也注册到 deepagents 顶层
# （FilesystemReadTools.explore 依赖这两个 from ... import 形式）
sys.modules["deepagents"].FilesystemMiddleware = _FilesystemMiddleware
sys.modules["deepagents.backends"].FilesystemBackend = _FilesystemBackend

# mock docker 模块（测试无需真实 Docker）
_mock_docker = types.ModuleType("docker")
_mock_docker.__path__ = []
_mock_docker.from_env = Mock()
_mock_docker.DockerClient = Mock()  # 2026-06-12 新增：socket 模式用 DockerClient(base_url=...)

class _DockerErrors:
    class DockerException(Exception):
        pass
    class NotFound(Exception):
        pass
    class APIError(Exception):
        pass

_mock_docker.errors = _DockerErrors()
sys.modules["docker"] = _mock_docker
sys.modules["docker.errors"] = types.ModuleType("docker.errors")
sys.modules["docker.errors"].DockerException = _DockerErrors.DockerException
sys.modules["docker.errors"].NotFound = _DockerErrors.NotFound
sys.modules["docker.errors"].APIError = _DockerErrors.APIError

# mock langgraph 及其子模块（使用 ModuleType 以支持 from xxx import yyy）
for _lg_mod in [
    "langgraph", "langgraph.checkpoint", "langgraph.checkpoint.base",
    "langgraph.checkpoint.memory", "langgraph.checkpoint.postgres",
    "langgraph.checkpoint.postgres.aio", "langgraph.store", "langgraph.store.base",
    "langgraph.store.memory", "langgraph.config", "langgraph.types", "langgraph.graph",
    "langgraph.graph.message", "langgraph.prebuilt", "langgraph.runtime",
]:
    sys.modules[_lg_mod] = types.ModuleType(_lg_mod)

# 为 langgraph 子模块添加需要的属性
class _Command:
    """模拟 langgraph Command 类型"""
    def __init__(self, update=None, goto=None, resume=None):
        self.update = update or {}
        self.goto = goto
        self.resume = resume


sys.modules["langgraph.types"].Command = _Command
sys.modules["langgraph.types"].interrupt = Mock()
sys.modules["langgraph.types"].RetryPolicy = Mock()
sys.modules["langgraph.types"].Overwrite = Mock()
sys.modules["langgraph.prebuilt"].ToolNode = Mock()
class _Runtime(Mock):
    """支持泛型下标的 Runtime Mock"""
    def __class_getitem__(cls, item):
        return cls


sys.modules["langgraph.runtime"].Runtime = _Runtime
sys.modules["langmem.short_term"].SummarizationNode = Mock()
sys.modules["langmem.short_term"].RunningSummary = Mock()
sys.modules["langchain_deepseek"].ChatDeepSeek = Mock()
sys.modules["langchain_openai"].ChatOpenAI = Mock()
sys.modules["langchain_anthropic"].ChatAnthropic = Mock()
sys.modules["langchain_ollama"].ChatOllama = Mock()
sys.modules["langchain_google_genai"].ChatGoogleGenerativeAI = Mock()
sys.modules["langgraph.graph"].MessagesState = Mock()
sys.modules["langgraph.graph"].StateGraph = Mock()
sys.modules["langgraph.graph"].START = Mock()
sys.modules["langgraph.graph"].END = Mock()
sys.modules["langgraph.graph.message"].add_messages = Mock()
sys.modules["langgraph.config"].get_stream_writer = Mock()
sys.modules["langgraph.checkpoint.base"].BaseCheckpointSaver = Mock()
sys.modules["langgraph.checkpoint.memory"].MemorySaver = Mock()
sys.modules["langgraph.checkpoint.postgres.aio"].AsyncPostgresSaver = Mock()
sys.modules["langgraph.store.base"].BaseStore = Mock()
sys.modules["langgraph.store.memory"].InMemoryStore = Mock()

_mock_psycopg_pool = types.ModuleType("psycopg_pool")
_mock_psycopg_pool.AsyncConnectionPool = Mock()
sys.modules["psycopg_pool"] = _mock_psycopg_pool
sys.modules["psycopg"] = types.ModuleType("psycopg")
_mock_psycopg_rows = types.ModuleType("psycopg.rows")
_mock_psycopg_rows.dict_row = Mock()
sys.modules["psycopg.rows"] = _mock_psycopg_rows

import asyncio
import os
from datetime import datetime, timedelta
from typing import Generator
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


# =============================================================================
# 全局环境变量预设
# =============================================================================


@pytest.fixture(scope="session", autouse=True)
def _setup_env() -> None:
    """
    预设测试环境变量

    强制使用 memory 模式，避免连接真实数据库。
    """
    os.environ["AUTH_STORAGE_MODE"] = "memory"
    os.environ["DATABASE_URL"] = "postgresql://postgres:postgres@localhost:5432/feature_agent"


@pytest.fixture(scope="session", autouse=True)
def _patch_typing_for_mocks() -> Generator[None, None, None]:
    """
    Patch typing._type_check，允许 Mock 对象通过类型注解检查。

    测试中对 langchain/langgraph 等外部依赖使用 Mock/ModuleType 替换，
    当 Agent 模块的注解包含 Union[AgentState, LGCommand] 等依赖 Mock 的类型时，
    Python 的 typing 机制会将其识别为非法前向引用而抛出 SyntaxError。
    本 fixture 在会话开始前统一打补丁，使 Mock 对象跳过原始类型检查。
    """
    import typing
    _orig_type_check = typing._type_check

    def _patched_type_check(arg, msg, is_argument=True, module=None, *, allow_special_forms=False):
        if hasattr(arg, "_mock_name"):
            return arg
        return _orig_type_check(arg, msg, is_argument, module, allow_special_forms=allow_special_forms)

    typing._type_check = _patched_type_check
    yield
    typing._type_check = _orig_type_check


# =============================================================================
# 外部依赖 Mock（autouse=True，所有测试自动生效）
# =============================================================================


@pytest.fixture(scope="session", autouse=True)
def _mock_asyncpg() -> Generator[None, None, None]:
    """
    Mock asyncpg 连接池

    阻止任何真实 PostgreSQL 连接请求。
    """
    mock_pool = Mock()
    mock_conn = Mock()
    mock_conn.execute = AsyncMock(return_value="INSERT 0 1")
    mock_conn.fetch = AsyncMock(return_value=[])
    mock_conn.fetchrow = AsyncMock(return_value=None)
    mock_pool.acquire = Mock()
    mock_pool.acquire.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.acquire.__aexit__ = AsyncMock(return_value=False)
    mock_pool.close = AsyncMock()

    with patch("asyncpg.create_pool", AsyncMock(return_value=mock_pool)):
        yield


@pytest.fixture(scope="session", autouse=True)
def _mock_database_pool() -> Generator[None, None, None]:
    """
    Mock DatabasePool 初始化与关闭
    """
    with patch("app.core.database.DatabasePool.initialize", AsyncMock()) as mock_init, \
         patch("app.core.database.DatabasePool.close", AsyncMock()) as mock_close, \
         patch("app.core.database.DatabasePool.register_schemas", AsyncMock()) as mock_reg:
        yield


@pytest.fixture(scope="session", autouse=True)
def _mock_session_db() -> Generator[None, None, None]:
    """
    Mock SessionDB 初始化
    """
    with patch("app.shared.utils.auth.session_db.SessionDB.initialize", AsyncMock()):
        yield


@pytest.fixture(scope="session", autouse=True)
def _mock_user_db() -> Generator[None, None, None]:
    """
    Mock UserDB.ensure_admin_exists 避免 lifespan 中创建管理员
    """
    with patch("app.shared.utils.auth.user_db.UserDB.ensure_admin_exists", AsyncMock()):
        yield


@pytest.fixture(scope="session", autouse=True)
def _mock_checkpointer() -> Generator[None, None, None]:
    """
    Mock LangGraph Checkpointer 初始化
    """
    mock_cp = Mock()
    with patch(
        "app.shared.utils.memory.checkpoint.get_async_checkpointer",
        AsyncMock(return_value=mock_cp),
    ):
        yield


@pytest.fixture(scope="session", autouse=True)
def _mock_mcp_registry() -> Generator[None, None, None]:
    """
    Mock MCPToolsRegistry 初始化与关闭
    """
    mock_registry = Mock()
    mock_registry.initialize = AsyncMock()
    mock_registry.shutdown = AsyncMock()
    mock_registry.list_servers = Mock(return_value=[])
    mock_registry.get_tools = Mock(return_value=[])

    with patch(
        "app.core.tools.mcp_registry.MCPToolsRegistry.get_instance",
        Mock(return_value=mock_registry),
    ):
        yield


@pytest.fixture(scope="session", autouse=True)
def _mock_captcha() -> Generator[None, None, None]:
    """
    Mock 验证码生成，固定返回测试用验证码
    """
    with patch(
        "app.shared.utils.auth.captcha.CaptchaManager.generate",
        Mock(return_value=("test_captcha_key", "data:image/png;base64,mock")),
    ):
        yield


# =============================================================================
# FastAPI 应用与客户端 Fixtures
# =============================================================================


@pytest.fixture(scope="session")
def app() -> Generator:
    """
    创建配置完成的 FastAPI 应用实例

    lifespan 已被外部 autouse mock 处理，无需真实数据库即可启动。
    """
    import sys
    _lg_types = sys.modules.get("langgraph.types")
    if "app.core.agent.agent" in sys.modules:
        del sys.modules["app.core.agent.agent"]
    # 强制重新设置 langgraph.types，确保不会被覆盖
    sys.modules["langgraph.types"] = _lg_types
    import importlib
    _agent_mod = importlib.import_module("app.core.agent.agent")
    from app.core.server import create_app
    from app.main import register_routers

    _app = create_app()
    register_routers(target_app=_app)
    yield _app


@pytest.fixture(scope="function")
def client(app) -> Generator[TestClient, None, None]:
    """
    提供 FastAPI TestClient

    每个测试函数独立实例，保证状态隔离。
    """
    with TestClient(app) as c:
        yield c


# =============================================================================
# 认证辅助 Fixtures
# =============================================================================


@pytest.fixture(scope="session")
def jwt_auth():
    """
    提供 JWTAuth 实例

    Returns:
        JWTAuth: 使用与生产相同 secret 的认证实例
    """
    from app.shared.utils.auth.Safety import JWTAuth

    return JWTAuth()


@pytest.fixture(scope="function")
def admin_token(jwt_auth) -> str:
    """
    生成 admin 角色的有效 access_token

    Returns:
        str: Bearer token 字符串
    """
    import jwt

    payload = {
        "username": "admin",
        "type": "access",
        "exp": datetime.utcnow() + timedelta(minutes=30),
        "iat": datetime.utcnow(),
    }
    token = jwt.encode(payload, jwt_auth.secret_key, algorithm=jwt_auth.algorithm)
    return f"Bearer {token}"


@pytest.fixture(scope="function")
def user_token(jwt_auth) -> str:
    """
    生成普通 user 角色的有效 access_token

    Returns:
        str: Bearer token 字符串
    """
    import jwt

    payload = {
        "username": "testuser",
        "type": "access",
        "exp": datetime.utcnow() + timedelta(minutes=30),
        "iat": datetime.utcnow(),
    }
    token = jwt.encode(payload, jwt_auth.secret_key, algorithm=jwt_auth.algorithm)
    return f"Bearer {token}"


@pytest.fixture(scope="function")
def admin_headers(admin_token) -> dict:
    """
    admin 认证请求头

    Returns:
        dict: 包含 Authorization 的请求头字典
    """
    return {"Authorization": admin_token}


@pytest.fixture(scope="function")
def user_headers(user_token) -> dict:
    """
    普通用户认证请求头

    Returns:
        dict: 包含 Authorization 的请求头字典
    """
    return {"Authorization": user_token}
