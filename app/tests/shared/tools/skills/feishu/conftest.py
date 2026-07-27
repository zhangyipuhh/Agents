# -*- coding:utf-8 -*-
"""
feishu 测试目录本地 conftest

在测试模块导入前 mock lark_oapi SDK，使测试无需真实安装 lark-oapi 包即可运行。

mock 范围：
    - lark_oapi.Client.builder() 链式调用（app_id / app_secret / log_level / build）
    - lark_oapi.LogLevel 枚举（DEBUG / INFO / WARNING / ERROR，使用真实整数值以支持 _resolve_log_level 测试）
    - lark_oapi.api.im.v1.CreateMessageRequest / CreateMessageRequestBody builder 链
    - lark_oapi.core.enum.HttpMethod / AccessTokenType（仅提供 GET / TENANT 真实使用项）
    - lark_oapi.core.model.BaseRequest / RequestOption（builder 链式构造 + 类级实例追踪，便于断言 http_method / uri / token_types）

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
# 构造 lark_oapi.core 及其子模块（enum / model），对等真实 lark-oapi 1.7.1
# ---------------------------------------------------------------------------
# 真实 lark-oapi 1.7.1 在 core/model.py 提供 BaseRequest 与 RequestOption；
# core/enum.py 提供 HttpMethod、AccessTokenType 等枚举。
# FeishuWebSocketService._fetch_bot_open_id 应改走 BaseRequest 原始 HTTP 路径：
#     from lark_oapi.core.enum import HttpMethod, AccessTokenType
#     from lark_oapi.core.model import BaseRequest, RequestOption
#     req = (BaseRequest.builder()
#            .http_method(HttpMethod.GET)
#            .uri("/open-apis/bot/v3/info")
#            .token_types([AccessTokenType.TENANT])
#            .build())
#     resp = client.request(req, RequestOption.builder().build())
#
# 这里挂载的 mock 必须真实可被 import 且行为接近真实 SDK，使测试断言
# ``http_method`` / ``uri`` / ``token_types`` 时拿到的字段名与生产一致。

# --- lark_oapi.core.enum ---------------------------------------------------
_lark_core_enum = types.ModuleType("lark_oapi.core.enum")

# 真实 lark-oapi 1.7.1 中 HttpMethod / AccessTokenType 是整型枚举；本 mock 仅
# 提供真实使用到的 token（GET、TENANT、USER、APP 等），其余值未在本测试触发
# 路径中用到，不预先给出具体数值，避免错误假设 SDK 真实值。
class _HttpMethod:
    """模拟 lark_oapi.core.enum.HttpMethod（仅暴露本测试用到的 GET）。"""

    GET = "GET"


class _AccessTokenType:
    """模拟 lark_oapi.core.enum.AccessTokenType（仅暴露本测试用到的 TENANT）。"""

    TENANT = "tenant"


_lark_core_enum.HttpMethod = _HttpMethod
_lark_core_enum.AccessTokenType = _AccessTokenType

# --- lark_oapi.core.model ---------------------------------------------------
# 真实 lark-oapi 1.7.1 暴露 ``BaseRequest.builder().http_method(...).uri(...).token_types(...).build()``
# 链式构造器；测试断言构造后 ``request.http_method / uri / token_types`` 字段名与
# 生产代码一致。本 mock 严格按 builder 链实现，避免与生产代码契约错位。
_lark_core_model = types.ModuleType("lark_oapi.core.model")


class _RequestOptionBuilder:
    """模拟 RequestOption.builder() 链（透传配置即可）。"""

    def __init__(self):
        self._opts: dict = {}

    def type(self, t):
        self._opts["type"] = t
        return self

    def build(self):
        """构造 RequestOption 实例（透传所有 builder 配置）。"""
        return _RequestOption(**self._opts)


class _RequestOption:
    """模拟 lark_oapi.core.model.RequestOption。

    真实 SDK 契约：``RequestOption.builder().build()`` 返回一个
    ``RequestOption`` 实例（用于带外传入 lark Client 的 request 调用）。
    本 mock 暴露静态 ``builder()`` 让 ``RequestOption.builder().build()`` 可运行。
    """

    def __init__(self, **kwargs):
        self._kwargs = kwargs

    @staticmethod
    def builder():
        """返回 builder，以便 ``RequestOption.builder().build()`` 链式构造。"""
        return _RequestOptionBuilder()


class _BaseRequestBuilder:
    """模拟 BaseRequest.builder() 链式构造器。

    真实 lark-oapi 1.7.1 原生 HTTP 路径的 SDK 写法：
        req = BaseRequest.builder() \\
            .http_method(HttpMethod.GET) \\
            .uri("/open-apis/bot/v3/info") \\
            .token_types([AccessTokenType.TENANT]) \\
            .build()
        resp = client.request(req, RequestOption.builder().build())

    本 mock 严格实现该 builder 链：每个 setter 返回 ``self`` 便于链式调用，
    ``build()`` 构造一个 ``BaseRequest`` 实例并记录到 ``_BaseRequest.instances``。
    """

    def __init__(self):
        self._http_method = None
        self._uri = None
        self._token_types = None

    def http_method(self, value):
        self._http_method = value
        return self

    def uri(self, value):
        self._uri = value
        return self

    def token_types(self, value):
        self._token_types = value
        return self

    def build(self):
        """构造 BaseRequest 实例，复制 builder 字段并记录到类级 instances。"""
        req = _BaseRequest(
            http_method=self._http_method,
            uri=self._uri,
            token_types=self._token_types,
        )
        return req


class _BaseRequest:
    """模拟 lark_oapi.core.model.BaseRequest（builder 构造，字段可断言）。

    字段：
        http_method: HTTP 方法（HttpMethod 枚举值）
        uri: 资源路径（str）
        token_types: token 类型列表（list[AccessTokenType]）

    Attributes:
        instances: 类级列表，记录所有 ``build()`` 完成的实例（用于测试断言）。
    """

    instances: list = []

    def __init__(self, *, http_method, uri, token_types):
        self.http_method = http_method
        self.uri = uri
        self.token_types = token_types
        _BaseRequest.instances.append(self)

    @staticmethod
    def builder():
        """返回 ``_BaseRequestBuilder`` 以支持 ``BaseRequest.builder().http_method(...)...build()`` 链。"""
        return _BaseRequestBuilder()


_lark_core_model.BaseRequest = _BaseRequest
_lark_core_model.RequestOption = _RequestOption


# --- lark_oapi.core 包级导入 -----------------------------------------------------
_lark_core = types.ModuleType("lark_oapi.core")
_lark_core.__path__ = []  # 标记为 package，使 ``lark_oapi.core.enum`` / ``.model`` 可被导入
_lark_core.enum = _lark_core_enum
_lark_core.model = _lark_core_model
_lark.core = _lark_core


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


# ---------------------------------------------------------------------------
# 构造 lark_oapi.api.cardkit.v1 子模块（供 FeishuCardConsumer 创建/更新 CardKit 卡片）
# ---------------------------------------------------------------------------
# 真实 SDK 用法：
#     from lark_oapi.api.cardkit.v1 import (
#         Card, CreateCardRequest, CreateCardRequestBody,
#         UpdateCardRequest, UpdateCardRequestBody,
#     )
#     req = CreateCardRequest.builder().request_body(
#         CreateCardRequestBody.builder().type("card_json").data(json_str).build()
#     ).build()
#     resp = client.cardkit.v1.card.create(req)        # → resp.data.card_id
#     patch_req = UpdateCardRequest.builder().card_id(...).request_body(
#         UpdateCardRequestBody.builder()
#         .card(Card.builder().type("card_json").data(json_str).build())
#         .sequence(1).build()
#     ).build()
#     resp = client.cardkit.v1.card.update(patch_req)
_lark_api_cardkit = types.ModuleType("lark_oapi.api.cardkit")
_lark_api_cardkit.__path__ = []
_lark_api_cardkit_v1 = types.ModuleType("lark_oapi.api.cardkit.v1")


class _CardBuilder:
    """模拟 Card.builder() 链。"""

    def __init__(self):
        self._type = None
        self._data = None

    def type(self, t):
        self._type = t
        return self

    def data(self, d):
        self._data = d
        return self

    def build(self):
        card = MagicMock(name="Card")
        card._type = self._type
        card._data = self._data
        return card


class _Card:
    """模拟 lark_oapi.api.cardkit.v1.Card。"""

    @staticmethod
    def builder():
        return _CardBuilder()


class _CreateCardRequestBodyBuilder:
    """模拟 CreateCardRequestBody.builder() 链。"""

    def __init__(self):
        self._type = None
        self._data = None

    def type(self, t):
        self._type = t
        return self

    def data(self, d):
        self._data = d
        return self

    def build(self):
        body = MagicMock(name="CreateCardRequestBody")
        body._type = self._type
        body._data = self._data
        return body


class _CreateCardRequestBody:
    @staticmethod
    def builder():
        return _CreateCardRequestBodyBuilder()


class _CreateCardRequestBuilder:
    """模拟 CreateCardRequest.builder() 链。"""

    def __init__(self):
        self._request_body = None

    def request_body(self, body):
        self._request_body = body
        return self

    def build(self):
        req = MagicMock(name="CreateCardRequest")
        req._request_body = self._request_body
        return req


class _CreateCardRequest:
    @staticmethod
    def builder():
        return _CreateCardRequestBuilder()


class _UpdateCardRequestBodyBuilder:
    """模拟 UpdateCardRequestBody.builder() 链。"""

    def __init__(self):
        self._card = None
        self._sequence = None

    def card(self, c):
        self._card = c
        return self

    def sequence(self, s):
        self._sequence = s
        return self

    def build(self):
        body = MagicMock(name="UpdateCardRequestBody")
        body._card = self._card
        body._sequence = self._sequence
        return body


class _UpdateCardRequestBody:
    @staticmethod
    def builder():
        return _UpdateCardRequestBodyBuilder()


class _UpdateCardRequestBuilder:
    """模拟 UpdateCardRequest.builder() 链。"""

    def __init__(self):
        self._card_id = None
        self._request_body = None

    def card_id(self, cid):
        self._card_id = cid
        return self

    def request_body(self, body):
        self._request_body = body
        return self

    def build(self):
        req = MagicMock(name="UpdateCardRequest")
        req._card_id = self._card_id
        req._request_body = self._request_body
        return req


class _UpdateCardRequest:
    @staticmethod
    def builder():
        return _UpdateCardRequestBuilder()


# ---------------------------------------------------------------------------
# 新增：UpdateCardElementRequest / UpdateCardElementRequestBody builder
# 供 FeishuCardConsumer._patch_cardkit_text 元素级更新使用
# ---------------------------------------------------------------------------
class _UpdateCardElementRequestBodyBuilder:
    """模拟 UpdateCardElementRequestBody.builder() 链。"""

    def __init__(self):
        self._uuid = None
        self._sequence = None
        self._element = None

    def uuid(self, u):
        self._uuid = u
        return self

    def sequence(self, s):
        self._sequence = s
        return self

    def element(self, e):
        self._element = e
        return self

    def build(self):
        body = MagicMock(name="UpdateCardElementRequestBody")
        body._uuid = self._uuid
        body._sequence = self._sequence
        body._element = self._element
        return body


class _UpdateCardElementRequestBody:
    @staticmethod
    def builder():
        return _UpdateCardElementRequestBodyBuilder()


class _UpdateCardElementRequestBuilder:
    """模拟 UpdateCardElementRequest.builder() 链。"""

    def __init__(self):
        self._card_id = None
        self._element_id = None
        self._request_body = None

    def card_id(self, cid):
        self._card_id = cid
        return self

    def element_id(self, eid):
        self._element_id = eid
        return self

    def request_body(self, body):
        self._request_body = body
        return self

    def build(self):
        req = MagicMock(name="UpdateCardElementRequest")
        req._card_id = self._card_id
        req._element_id = self._element_id
        req._request_body = self._request_body
        return req


class _UpdateCardElementRequest:
    @staticmethod
    def builder():
        return _UpdateCardElementRequestBuilder()


# ---------------------------------------------------------------------------
# 新增：SettingsCardRequest / SettingsCardRequestBody builder
# 供 FeishuCardConsumer._close_streaming_mode 使用
# ---------------------------------------------------------------------------
class _SettingsCardRequestBodyBuilder:
    """模拟 SettingsCardRequestBody.builder() 链。"""

    def __init__(self):
        self._uuid = None
        self._sequence = None
        self._settings = None

    def uuid(self, u):
        self._uuid = u
        return self

    def sequence(self, s):
        self._sequence = s
        return self

    def settings(self, s):
        self._settings = s
        return self

    def build(self):
        body = MagicMock(name="SettingsCardRequestBody")
        body._uuid = self._uuid
        body._sequence = self._sequence
        body._settings = self._settings
        return body


class _SettingsCardRequestBody:
    @staticmethod
    def builder():
        return _SettingsCardRequestBodyBuilder()


class _SettingsCardRequestBuilder:
    """模拟 SettingsCardRequest.builder() 链。"""

    def __init__(self):
        self._card_id = None
        self._request_body = None

    def card_id(self, cid):
        self._card_id = cid
        return self

    def request_body(self, body):
        self._request_body = body
        return self

    def build(self):
        req = MagicMock(name="SettingsCardRequest")
        req._card_id = self._card_id
        req._request_body = self._request_body
        return req


class _SettingsCardRequest:
    @staticmethod
    def builder():
        return _SettingsCardRequestBuilder()


_lark_api_cardkit_v1.Card = _Card
_lark_api_cardkit_v1.CreateCardRequest = _CreateCardRequest
_lark_api_cardkit_v1.CreateCardRequestBody = _CreateCardRequestBody
_lark_api_cardkit_v1.UpdateCardRequest = _UpdateCardRequest
_lark_api_cardkit_v1.UpdateCardRequestBody = _UpdateCardRequestBody
_lark_api_cardkit_v1.UpdateCardElementRequest = _UpdateCardElementRequest
_lark_api_cardkit_v1.UpdateCardElementRequestBody = _UpdateCardElementRequestBody
_lark_api_cardkit_v1.SettingsCardRequest = _SettingsCardRequest
_lark_api_cardkit_v1.SettingsCardRequestBody = _SettingsCardRequestBody


# 在 _ClientBuilder.build() 返回的 mock client 上挂 cardkit.v1.card 命名空间。
# 由于 client 是 MagicMock，本身就支持任意属性链访问，但为了让
# `client.cardkit.v1.card.create(...)` 与 `client.cardkit.v1.card.update(...)`
# 的返回值可被测试断言，这里提供一个共享的 CardKitNamespace。
class _CardKitCardNamespace:
    """模拟 client.cardkit.v1.card 命名空间，暴露 create / update / settings。

    测试中通过 ``client.cardkit.v1.card.create = MagicMock(...)``
    直接覆盖；本类仅作为默认占位（返回 success=False）。
    """

    def __init__(self):
        # 默认 create / update / settings 返回 success=False 的 MagicMock，
        # 测试用例通过 setattr 注入成功响应或 Mock
        self.create = MagicMock(name="cardkit.create", return_value=MagicMock(success=lambda: False))
        self.update = MagicMock(name="cardkit.update", return_value=MagicMock(success=lambda: False))
        self.settings = MagicMock(name="cardkit.settings", return_value=MagicMock(success=lambda: False))


class _CardKitCardElementNamespace:
    """模拟 client.cardkit.v1.card_element 命名空间，暴露 update。

    元素级更新使用 ``client.cardkit.v1.card_element.update(...)``。
    """

    def __init__(self):
        self.update = MagicMock(
            name="cardkit.card_element.update",
            return_value=MagicMock(success=lambda: False),
        )


class _CardKitV1Namespace:
    """模拟 client.cardkit.v1 命名空间。"""

    def __init__(self):
        self.card = _CardKitCardNamespace()
        self.card_element = _CardKitCardElementNamespace()


class _CardKitNamespace:
    """模拟 client.cardkit 命名空间。"""

    def __init__(self):
        self.v1 = _CardKitV1Namespace()


# 把 cardkit 命名空间挂到所有现有 client 实例（兼容 _ClientBuilder.build
# 返回的 MagicMock；MagicMock 本身支持任意属性链，但显式挂载可让测试断言
# ``client.cardkit.v1.card.create.call_count`` 时拿到同一对象）。
# 这里通过给 _ClientBuilder.build 注入 cardkit 字段实现。
_orig_client_build = _ClientBuilder.build


def _patched_client_build(self):
    client = _orig_client_build(self)
    client.cardkit = _CardKitNamespace()
    return client


_ClientBuilder.build = _patched_client_build


_lark_api_cardkit.v1 = _lark_api_cardkit_v1
_lark_api.cardkit = _lark_api_cardkit


# 注册到 sys.modules
sys.modules["lark_oapi"] = _lark
sys.modules["lark_oapi.api"] = _lark_api
sys.modules["lark_oapi.api.im"] = _lark_api_im
sys.modules["lark_oapi.api.im.v1"] = _lark_api_im_v1
sys.modules["lark_oapi.api.cardkit"] = _lark_api_cardkit
sys.modules["lark_oapi.api.cardkit.v1"] = _lark_api_cardkit_v1
sys.modules["lark_oapi.ws"] = _ws_module
sys.modules["lark_oapi.core"] = _lark_core
sys.modules["lark_oapi.core.enum"] = _lark_core_enum
sys.modules["lark_oapi.core.model"] = _lark_core_model
