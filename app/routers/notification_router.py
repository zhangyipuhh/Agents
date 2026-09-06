# -*- coding:utf-8 -*-
"""
通知渠道通用 Router（2026-09-03 落地）。

设计原则（详见 ``memory/misc.md`` 「通知渠道通用表设计原则」）：

- 所有通知渠道（飞书 / 未来钉钉 / 企微 / Slack）走同一 router
- ``channel_type`` 通过 query / body 参数传入，handler 内按 channel_type 分发
- ``prefix="/api/notification"`` —— **不加** ``/admin/`` 段（用户硬约束）
- ACL 全部用 ``messaging.feishu.<sub>``（本期 UI 只暴露飞书；未来加钉钉改
  ``messaging.dingtalk.<sub>`` 即可，本 router 零改动）

端点清单（11 个）：

- GET    /api/notification/channels
- POST   /api/notification/channels
- GET    /api/notification/channels/{channel_id}
- PUT    /api/notification/channels/{channel_id}
- DELETE /api/notification/channels/{channel_id}
- POST   /api/notification/channels/{channel_id}/test-connection
- GET    /api/notification/channels/{channel_id}/targets
- POST   /api/notification/channels/{channel_id}/targets
- PUT    /api/notification/targets/{target_id}
- DELETE /api/notification/targets/{target_id}
- GET    /api/notification/agents
- POST   /api/notification/send-test
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from app.shared.utils.auth.ownership_scope import OwnershipScope
from app.shared.utils.auth.Safety import require_admin_or_menu_acl
from app.shared.utils.notification import (
    NotificationConfigError,
    NotificationConfigNotFoundError,
    NotificationConfigService,
    NotificationConfigValidationError,
)


logger = __import__("logging").getLogger(__name__)


router = APIRouter(
    prefix="/api/notification",
    tags=["Notification"],
)


# =============================================================================
# Helpers
# =============================================================================


def _get_service(request: Request) -> NotificationConfigService:
    """从 ``app.state`` 读取 ``notification_config_service`` 实例。

    异常:
        HTTPException: 服务未初始化时返回 500。
    """
    service = getattr(request.app.state, "notification_config_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="NotificationConfigService not initialized",
        )
    return service


def _request_user_id(request: Request) -> int:
    """从 ``request.state`` 取当前用户 ID，缺失返回 0。"""
    return int(getattr(request.state, "user_id", 0) or 0)


def _handle_service_error(exc: Exception) -> None:
    """把 service 异常映射为 HTTPException。

    异常:
        HTTPException: 视异常类型映射 404 / 400 / 500。
    """
    if isinstance(exc, NotificationConfigNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, NotificationConfigValidationError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if isinstance(exc, NotificationConfigError):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    raise exc


# =============================================================================
# Request Models
# =============================================================================


class CreateChannelRequest(BaseModel):
    """新建 / 更新渠道请求体。

    Attributes:
        channel_type: 渠道类型（白名单 'feishu'）。
        name: 渠道名（按 channel_type 唯一）。
        display_name: 显示名。
        config: 渠道配置 dict（含明文 app_id / app_secret / default_receive_id /
            default_receive_id_type / log_level / agent_name / receiver_username）；
            router 负责 Fernet 加密后写入 DB。
        enabled: 是否启用。
        is_default: 是否默认渠道。
    """

    channel_type: str = Field(default="feishu")
    name: str = Field(..., min_length=1, max_length=100)
    display_name: str = Field(default="", max_length=200)
    config: Dict[str, Any] = Field(default_factory=dict)
    enabled: bool = Field(default=True)
    is_default: bool = Field(default=False)


class UpdateChannelRequest(BaseModel):
    """更新渠道请求体（未传字段保持原值）。

    Attributes:
        display_name: 显示名；None 表示不修改。
        config: 渠道配置 dict；必填字段可省略（service 自动从原行补齐加密字段）。
        enabled: 是否启用；None 表示不修改。
        is_default: 是否默认渠道；None 表示不修改。
        keep_existing_secret: True 时保留原 config 中加密字段（前端「密钥留空表示
            不修改」场景）；默认 True。
    """

    display_name: Optional[str] = Field(default=None, max_length=200)
    config: Optional[Dict[str, Any]] = Field(default=None)
    enabled: Optional[bool] = Field(default=None)
    is_default: Optional[bool] = Field(default=None)
    keep_existing_secret: bool = Field(default=True)


class CreateTargetRequest(BaseModel):
    """新建 / 更新目标请求体。

    Attributes:
        target_type: 目标类型（白名单 'feishu.chat' / 'feishu.user'）。
        name: 目标名。
        config: 目标配置 dict（含 chat_id / chat_type）。
        agent_name: 绑定的智能体名。
        subject_template: 主题模板。
        body_template: 正文模板。
        enabled: 是否启用。
    """

    target_type: str = Field(default="feishu.chat")
    name: str = Field(..., min_length=1, max_length=200)
    config: Dict[str, Any] = Field(default_factory=dict)
    agent_name: str = Field(..., min_length=1, max_length=100)
    subject_template: str = Field(default="", max_length=500)
    body_template: str = Field(default="")
    enabled: bool = Field(default=True)


class UpdateTargetRequest(BaseModel):
    """更新目标请求体。"""

    target_type: Optional[str] = Field(default=None)
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    config: Optional[Dict[str, Any]] = Field(default=None)
    agent_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    subject_template: Optional[str] = Field(default=None, max_length=500)
    body_template: Optional[str] = Field(default=None)
    enabled: Optional[bool] = Field(default=None)


class SendTestRequest(BaseModel):
    """发送测试消息请求体。

    Attributes:
        target_id: 目标 ID。
        channel_type: 渠道类型（冗余校验，与目标所属 channel_type 必须一致）。
        content: 消息正文（Markdown 自动检测 → 卡片）。
    """

    target_id: int = Field(..., ge=1)
    channel_type: str = Field(default="feishu")
    content: str = Field(default="")


# =============================================================================
# Feishu config helper（明文 → 密文）
# =============================================================================


def _encrypt_feishu_config(
    service: NotificationConfigService,
    config: Dict[str, Any],
) -> Dict[str, Any]:
    """把前端传入的飞书 config（含明文 app_id / app_secret）转为可入库的密文 dict。

    - ``app_id`` (明文) → ``config.app_id_encrypted`` (密文)
    - ``app_secret`` (明文) → ``config.app_secret_encrypted`` (密文)
    - ``agent_name`` / ``receiver_username`` / ``default_receive_id`` /
      ``default_receive_id_type`` / ``log_level`` 直传（明文入库）
    - 其他键保留
    """
    out = dict(config)
    # 明文 → 密文
    plain_app_id = out.pop("app_id", None)
    plain_app_secret = out.pop("app_secret", None)
    if plain_app_id:
        out["app_id_encrypted"] = service.encrypt_field(str(plain_app_id))
    elif out.get("app_id_encrypted"):
        # 已是密文，保留
        pass
    if plain_app_secret:
        out["app_secret_encrypted"] = service.encrypt_field(str(plain_app_secret))
    elif out.get("app_secret_encrypted"):
        pass
    return out


# =============================================================================
# Channel Endpoints
# =============================================================================


@router.get("/channels", response_model=List[Dict[str, Any]],
            dependencies=[Depends(require_admin_or_menu_acl('messaging.feishu.apps'))])
async def list_channels(
    request: Request,
    channel_type: Optional[str] = Query(default=None, description="过滤 channel_type"),
) -> List[Dict[str, Any]]:
    """列出渠道（密码脱敏）。

    参数:
        request: FastAPI Request 对象。
        channel_type: 过滤 channel_type（None 返回全部）。

    返回:
        List[Dict[str, Any]]: 渠道列表。
    """
    service = _get_service(request)
    return await service.list_channels(channel_type=channel_type)


@router.post("/channels", response_model=Dict[str, Any],
             status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_admin_or_menu_acl('messaging.feishu.apps'))])
async def create_channel(
    request: Request,
    body: CreateChannelRequest,
) -> Dict[str, Any]:
    """新建渠道。

    参数:
        request: FastAPI Request 对象。
        body: 新建请求体（config 含明文 app_id / app_secret，router 加密）。

    返回:
        Dict[str, Any]: 含 ``id`` / ``updated_at`` / ``created`` 字段。
    """
    service = _get_service(request)
    config_db = _encrypt_feishu_config(service, body.config) if body.channel_type == "feishu" else dict(body.config)
    try:
        return await service.upsert_channel(
            channel_type=body.channel_type,
            name=body.name,
            display_name=body.display_name,
            config=config_db,
            enabled=body.enabled,
            is_default=body.is_default,
            created_by_user_id=_request_user_id(request) or None,
            keep_existing_secret=False,
        )
    except Exception as exc:
        _handle_service_error(exc)
        raise


@router.get("/channels/{channel_id}", response_model=Dict[str, Any],
            dependencies=[Depends(require_admin_or_menu_acl('messaging.feishu.apps'))])
async def get_channel(request: Request, channel_id: int) -> Dict[str, Any]:
    """读取渠道详情（密码脱敏）。"""
    service = _get_service(request)
    ch = await service.get_channel(channel_id)
    if ch is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"channel_id={channel_id} 不存在",
        )
    return ch


@router.put("/channels/{channel_id}", response_model=Dict[str, Any],
            dependencies=[Depends(require_admin_or_menu_acl('messaging.feishu.apps'))])
async def update_channel(
    request: Request,
    channel_id: int,
    body: UpdateChannelRequest,
) -> Dict[str, Any]:
    """更新渠道（部分字段更新）。

    设计：先读原行，merge 字段，再调 ``upsert_channel``。``keep_existing_secret=True``
    保证前端「密钥留空不修改」场景。
    """
    service = _get_service(request)
    existing_internal = await service._get_channel_internal(channel_id)  # noqa: SLF001（service 已提供，private 标记但本模块同包）
    if existing_internal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"channel_id={channel_id} 不存在",
        )

    # merge config（前端可只传部分键；keep_existing_secret=True 时保留原加密字段）
    if body.config is not None:
        merged_config = dict(existing_internal["config"])
        # 应用前端新传入的字段
        for k, v in body.config.items():
            if k in ("app_id", "app_secret") and not v:
                # 留空 → 跳过（保留原加密字段）
                continue
            merged_config[k] = v
        # 加密明文
        merged_config = _encrypt_feishu_config(service, merged_config) if existing_internal["channel_type"] == "feishu" else merged_config
        # keep_existing_secret 语义：如果前端没传明文 app_id/app_secret，且 merged_config 没有 app_id_encrypted 字段，则回填
        if body.keep_existing_secret:
            for k in ("app_id_encrypted", "app_secret_encrypted"):
                if k not in merged_config or not merged_config[k]:
                    if k in existing_internal["config"]:
                        merged_config[k] = existing_internal["config"][k]
        final_config = merged_config
    else:
        final_config = existing_internal["config"]

    try:
        return await service.upsert_channel(
            channel_type=existing_internal["channel_type"],
            name=existing_internal["name"],
            display_name=body.display_name if body.display_name is not None else existing_internal["display_name"],
            config=final_config,
            enabled=body.enabled if body.enabled is not None else existing_internal["enabled"],
            is_default=body.is_default if body.is_default is not None else existing_internal["is_default"],
            created_by_user_id=existing_internal.get("created_by_user_id"),
            keep_existing_secret=True,
        )
    except Exception as exc:
        _handle_service_error(exc)
        raise


@router.delete("/channels/{channel_id}", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[Depends(require_admin_or_menu_acl('messaging.feishu.apps'))])
async def delete_channel(request: Request, channel_id: int) -> None:
    """删除渠道（级联清理 targets）。"""
    service = _get_service(request)
    deleted = await service.delete_channel(channel_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"channel_id={channel_id} 不存在",
        )


@router.post("/channels/{channel_id}/test-connection", response_model=Dict[str, Any],
             dependencies=[Depends(require_admin_or_menu_acl('messaging.feishu.apps'))])
async def test_channel_connection(request: Request, channel_id: int) -> Dict[str, Any]:
    """测试渠道凭证（不发消息）。"""
    service = _get_service(request)
    return await service.test_channel_connection(channel_id)


# =============================================================================
# Target Endpoints
# =============================================================================


@router.get("/channels/{channel_id}/targets", response_model=List[Dict[str, Any]],
            dependencies=[Depends(require_admin_or_menu_acl('messaging.feishu.policies'))])
async def list_targets(
    request: Request,
    channel_id: int,
) -> List[Dict[str, Any]]:
    """列出某渠道下所有目标。"""
    service = _get_service(request)
    scope = OwnershipScope.from_request(request)
    return await service.list_targets(channel_id=channel_id, scope=scope)


@router.post("/channels/{channel_id}/targets", response_model=Dict[str, Any],
             status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_admin_or_menu_acl('messaging.feishu.policies'))])
async def create_target(
    request: Request,
    channel_id: int,
    body: CreateTargetRequest,
) -> Dict[str, Any]:
    """新建目标（绑群 + 绑智能体）。"""
    service = _get_service(request)
    try:
        return await service.upsert_target(
            channel_id=channel_id,
            target_type=body.target_type,
            name=body.name,
            config=body.config,
            agent_name=body.agent_name,
            subject_template=body.subject_template,
            body_template=body.body_template,
            enabled=body.enabled,
            created_by_user_id=_request_user_id(request) or None,
        )
    except Exception as exc:
        _handle_service_error(exc)
        raise


@router.put("/targets/{target_id}", response_model=Dict[str, Any],
            dependencies=[Depends(require_admin_or_menu_acl('messaging.feishu.policies'))])
async def update_target(
    request: Request,
    target_id: int,
    body: UpdateTargetRequest,
) -> Dict[str, Any]:
    """更新目标（部分字段）。"""
    service = _get_service(request)
    existing = await service.get_target(target_id)
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"target_id={target_id} 不存在",
        )
    try:
        return await service.upsert_target(
            channel_id=existing["channel_id"],
            target_type=body.target_type or existing["target_type"],
            name=body.name or existing["name"],
            config=body.config if body.config is not None else existing["config"],
            agent_name=body.agent_name or existing["agent_name"],
            subject_template=body.subject_template if body.subject_template is not None else existing["subject_template"],
            body_template=body.body_template if body.body_template is not None else existing["body_template"],
            enabled=body.enabled if body.enabled is not None else existing["enabled"],
            created_by_user_id=existing.get("created_by_user_id"),
            target_id=target_id,
        )
    except Exception as exc:
        _handle_service_error(exc)
        raise


@router.delete("/targets/{target_id}", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[Depends(require_admin_or_menu_acl('messaging.feishu.policies'))])
async def delete_target(request: Request, target_id: int) -> None:
    """删除目标。"""
    service = _get_service(request)
    deleted = await service.delete_target(target_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"target_id={target_id} 不存在",
        )


# =============================================================================
# Agents + Send Test
# =============================================================================


@router.get("/agents", response_model=List[Dict[str, Any]],
            dependencies=[Depends(require_admin_or_menu_acl('messaging.feishu.policies'))])
async def list_agents(request: Request) -> List[Dict[str, Any]]:
    """列出 enabled=True 智能体（target agent_name 下拉用）。"""
    service = _get_service(request)
    return await service.list_enabled_agents()


@router.post("/send-test", response_model=Dict[str, Any],
             dependencies=[Depends(require_admin_or_menu_acl('messaging.feishu.test'))])
async def send_test(request: Request, body: SendTestRequest) -> Dict[str, Any]:
    """发送测试消息。

    飞书路径：从 target 取 chat_id / chat_type，从 channel config 取凭证（Fernet
    解密），构造临时 ``lark.Client``，调 ``client.im.v1.message.create`` 发到群。
    """
    service = _get_service(request)
    return await service.send_test_message(
        target_id=body.target_id,
        channel_type=body.channel_type,
        content=body.content,
    )
