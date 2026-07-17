# -*- coding:utf-8 -*-
"""
feishu 测试目录本地 conftest

在测试模块导入前 mock lark_oapi SDK，使测试无需真实安装 lark-oapi 包即可运行。

mock 范围：
    - lark_oapi.Client.builder() 链式调用（app_id / app_secret / log_level / build）
    - lark_oapi.LogLevel 枚举（DEBUG / INFO / WARNING / ERROR，使用真实整数值以支持 _resolve_log_level 测试）
    - lark_oapi.api.im.v1.CreateMessageRequest / CreateMessageRequestBody builder 链

注意：生产环境中 lark_oapi 是真实依赖（见 app/requirements.txt），
此处 mock 仅用于沙箱/CI 环境无该包时的单元测试运行。
"""
import sys
import types
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# 构造 lark_oapi mock
# ---------------------------------------------------------------------------
_lark = types.ModuleType("lark_oapi")
_lark.__path__ = []  # 标记为 package 以支持子模块导入


class _LogLevel:
    """模拟 lark.LogLevel 枚举（使用真实整数值，供 _resolve_log_level 测试比较）。"""
    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40


_lark.LogLevel = _LogLevel


class _ClientBuilder:
    """模拟 lark.Client.builder() 链式构造器。"""

    def __init__(self):
        self._app_id = None
        self._app_secret = None
        self._log_level = None

    def app_id(self, app_id):
        self._app_id = app_id
        return self

    def app_secret(self, app_secret):
        self._app_secret = app_secret
        return self

    def log_level(self, level):
        self._log_level = level
        return self

    def build(self):
        """构造一个 mock client 实例（每次 build 返回新实例，以支持单例缓存测试）。

        2026-07-16 修复：模拟 lark.Client 真实存储结构 —— 凭证放在 _config.app_id /
        _config.app_secret（不在 _app_id/_app_secret 顶层属性）。同时保留旧属性名
        以兼容历史测试。
        """
        client = MagicMock(name="lark.Client")
        client._app_id = self._app_id
        client._app_secret = self._app_secret
        client._log_level = self._log_level
        # 新代码通过 _config.app_id / _config.app_secret 拿凭证；模拟真实结构
        mock_config = MagicMock(name="_config")
        mock_config.app_id = self._app_id
        mock_config.app_secret = self._app_secret
        client._config = mock_config
        return client


class _Client:
    """模拟 lark.Client 类。"""

    @staticmethod
    def builder():
        return _ClientBuilder()


_lark.Client = _Client


# ---------------------------------------------------------------------------
# 构造 lark_oapi.api.im.v1 子模块
# ---------------------------------------------------------------------------
_lark_api = types.ModuleType("lark_oapi.api")
_lark_api.__path__ = []

_lark_api_im = types.ModuleType("lark_oapi.api.im")
_lark_api_im.__path__ = []

_lark_api_im_v1 = types.ModuleType("lark_oapi.api.im.v1")


class _MessageRequestBuilder:
    """模拟 CreateMessageRequest.builder() 链。"""

    def receive_id_type(self, x):
        return self

    def request_body(self, x):
        return self

    def build(self):
        return MagicMock(name="CreateMessageRequest")


class _MessageRequestBodyBuilder:
    """模拟 CreateMessageRequestBody.builder() 链。"""

    def receive_id(self, x):
        return self

    def msg_type(self, x):
        return self

    def content(self, x):
        return self

    def uuid(self, x):
        return self

    def build(self):
        return MagicMock(name="CreateMessageRequestBody")


class _CreateMessageRequest:
    """模拟 lark_oapi.api.im.v1.CreateMessageRequest。"""

    @staticmethod
    def builder():
        return _MessageRequestBuilder()


class _CreateMessageRequestBody:
    """模拟 lark_oapi.api.im.v1.CreateMessageRequestBody。"""

    @staticmethod
    def builder():
        return _MessageRequestBodyBuilder()


_lark_api_im_v1.CreateMessageRequest = _CreateMessageRequest
_lark_api_im_v1.CreateMessageRequestBody = _CreateMessageRequestBody


class _P2ImMessageReceiveV1:
    """模拟 lark_oapi.api.im.v1.P2ImMessageReceiveV1（仅作类型提示用）。"""

    pass


_lark_api_im_v1.P2ImMessageReceiveV1 = _P2ImMessageReceiveV1


# ---------------------------------------------------------------------------
# 构造 GetMessageResourceRequest builder + message_resource 资源（供
# FeishuWebSocketService 下载文件）
# ---------------------------------------------------------------------------
class _GetMessageResourceRequestBuilder:
    """模拟 lark_oapi.api.im.v1.GetMessageResourceRequest.builder() 链。

    真实 SDK 的用法：
        req = GetMessageResourceRequest.builder() \\
            .message_id(message_id) \\      # path 参数
            .file_key(file_key) \\          # path 参数
            .type("file") \\                # query 参数（"file" 或 "image"）
            .build()
        resp = client.im.v1.message_resource.get(req)
        # resp.file 是 IO-like 对象，.read() 返回 bytes
    """

    instances: list = []  # 记录所有实例，便于测试断言

    def __init__(self):
        self._message_id = None
        self._file_key = None
        self._type = None

    def message_id(self, mid: str):
        self._message_id = mid
        return self

    def file_key(self, key: str):
        self._file_key = key
        return self

    def type(self, t: str):
        self._type = t
        return self

    def build(self):
        req = MagicMock(name="GetMessageResourceRequest")
        req._message_id = self._message_id
        req._file_key = self._file_key
        req._type = self._type
        _GetMessageResourceRequestBuilder.instances.append(
            (self._message_id, self._file_key, self._type)
        )
        return req


class _GetMessageResourceRequest:
    """模拟 lark_oapi.api.im.v1.GetMessageResourceRequest。"""

    instances: list = []

    @staticmethod
    def builder():
        return _GetMessageResourceRequestBuilder()


# 让 GetMessageResourceRequest.instances 与 builder.instances 等价（兼容两种访问）
_GetMessageResourceRequest.instances = _GetMessageResourceRequestBuilder.instances
_lark_api_im_v1.GetMessageResourceRequest = _GetMessageResourceRequest


# 在 im.v1.message_resource 命名空间下挂 get() 方法。
# 真实 SDK 的结构： client.im.v1.message_resource.get(request)
# （2026-07-17 修正：之前误用 client.im.v1.message.get_message_resource() 路径
# 会撞到 Message 资源类的边界，运行期抛 AttributeError。）
class _MessageResourceNamespace:
    """模拟 lark.im.v1.message_resource 命名空间，仅暴露 ``get()``。

    测试中通过 ``lark_client.im.v1.message_resource.get = MagicMock(...)``
    直接覆盖 ``get``；不进 conftest 自动塞值（避免与生产 SDK 行为不一致）。
    """

    def __init__(self) -> None:
        self.get = None  # 测试阶段通过 setattr 注入


_message_resource_ns = _MessageResourceNamespace()
# 暴露为 ``lark_client.im.v1.message_resource`` 引用同一对象
# 但实际上每个真实 client 是不同实例，这一层仅供类型标注/import 探测，
# 真正的 mock 在测试里覆盖 ``client.im.v1.message_resource.get``。


_lark_api.im = _lark_api_im
_lark_api_im.v1 = _lark_api_im_v1
_lark.api = _lark_api


# ---------------------------------------------------------------------------
# 构造 lark_oapi.api.bot.v1 子模块（供 FeishuWebSocketService 获取机器人 open_id）
# ---------------------------------------------------------------------------
_lark_api_bot = types.ModuleType("lark_oapi.api.bot")
_lark_api_bot.__path__ = []
_lark_api_bot_v1 = types.ModuleType("lark_oapi.api.bot.v1")


class _GetBotRequestBuilder:
    """模拟 GetBotRequest.builder()。"""

    def build(self):
        return MagicMock(name="GetBotRequest")


class _GetBotRequest:
    """模拟 lark_oapi.api.bot.v1.GetBotRequest。"""

    @staticmethod
    def builder():
        return _GetBotRequestBuilder()


_lark_api_bot_v1.GetBotRequest = _GetBotRequest
_lark_api_bot.v1 = _lark_api_bot_v1
_lark_api.bot = _lark_api_bot


# ---------------------------------------------------------------------------
# 构造 lark_oapi.ws 与 lark.EventDispatcherHandler（供 FeishuWebSocketService）
# ---------------------------------------------------------------------------
class _WsClient:
    """模拟 lark.ws.Client（仅记录实例化参数，不真正连接）。"""

    instances: list = []  # 记录所有实例，便于测试断言

    def __init__(self, app_id, app_secret, event_handler=None, log_level=None):
        self._app_id = app_id
        self._app_secret = app_secret
        self._event_handler = event_handler
        self._log_level = log_level
        _WsClient.instances.append(self)

    def start(self):
        """模拟 SDK start()：在测试中默认不阻塞，立即返回。"""
        return None


class _EventDispatcherHandlerBuilder:
    """模拟 lark.EventDispatcherHandler.builder() 链。"""

    def __init__(self, encryption_key: str = "", verification_token: str = ""):
        self._handlers: list = []
        self._encryption_key = encryption_key
        self._verification_token = verification_token

    def register_p2_im_message_receive_v1(self, handler):
        self._handlers.append(("p2_im_message_receive_v1", handler))
        return self

    def register_p2_card_action_trigger(self, handler):
        self._handlers.append(("p2_card_action_trigger", handler))
        return self

    def build(self):
        return MagicMock(name="EventDispatcherHandler", handlers=self._handlers)


class _EventDispatcherHandler:
    """模拟 lark.EventDispatcherHandler。"""

    @staticmethod
    def builder(encryption_key: str = "", verification_token: str = ""):
        return _EventDispatcherHandlerBuilder(encryption_key, verification_token)


class _WsModule:
    """类形式占位（已被裸 ModuleType 取代），保留以避免历史引用误删。"""

    Client = _WsClient


# 单一 ``_ws_module`` 实例，必须同时挂到 ``_lark.ws`` 与 ``sys.modules``，
# 并在内部暴露 ``.client`` 子模块供 ``import lark_oapi.ws.client`` 走通。
_ws_module = types.ModuleType("lark_oapi.ws")
_ws_module.__path__ = []  # 标记为 package，使 ``lark_oapi.ws.client`` 可被导入
_ws_module.Client = _WsClient
_lark.ws = _ws_module
_lark.EventDispatcherHandler = _EventDispatcherHandler

# 为 _run_ws_blocking 提供的 ``import lark_oapi.ws.client`` 路径做兜底：
# 真实 SDK 路径 ``lark_oapi.ws.client``；本模块只需含 ``loop`` 属性供 monkey patch。
_ws_client_mod = types.ModuleType("lark_oapi.ws.client")
_ws_client_mod.loop = None
_ws_module.client = _ws_client_mod
sys.modules["lark_oapi.ws.client"] = _ws_client_mod


# 注册到 sys.modules
sys.modules["lark_oapi"] = _lark
sys.modules["lark_oapi.api"] = _lark_api
sys.modules["lark_oapi.api.im"] = _lark_api_im
sys.modules["lark_oapi.api.im.v1"] = _lark_api_im_v1
sys.modules["lark_oapi.api.bot"] = _lark_api_bot
sys.modules["lark_oapi.api.bot.v1"] = _lark_api_bot_v1
sys.modules["lark_oapi.ws"] = _ws_module
