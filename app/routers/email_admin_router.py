#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
邮件系统 Admin Router 模块。

提供 /api/admin/email 下的 SMTP 配置、策略管理与邮件发送接口。
所有接口均要求 admin 权限，服务实例由 app/core/server.py lifespan
初始化到 app.state.email_config_service。

端点清单：
- GET  /api/admin/email/server-config            获取当前 SMTP 配置（密码不外泄）
- PUT  /api/admin/email/server-config            保存 SMTP 配置（密码留空表示不修改）
- POST /api/admin/email/server-config/test       测试 SMTP 连接（不发送邮件）
- GET  /api/admin/email/emailable-users          列出已注册且邮箱非空用户
- GET  /api/admin/email/policies                 策略列表
- POST /api/admin/email/policies                 新建策略
- PUT  /api/admin/email/policies/{policy_id}     更新策略
- DELETE /api/admin/email/policies/{policy_id}   删除策略
- POST /api/admin/email/test                     发送测试邮件（multipart/form-data）
- POST /api/admin/email/send-by-policy/{policy_id}  按策略发送邮件
"""
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from pydantic import BaseModel, Field

from app.shared.utils.auth.Safety import require_admin
from app.shared.utils.email.email_config_service import (
    EmailConfigError,
    EmailConfigNotFoundError,
    EmailConfigService,
    EmailConfigValidationError,
)
from app.shared.utils.email.email_models import EmailServerConfig
from app.shared.utils.email.email_service import EmailSendError, EmailService


logger = logging.getLogger(__name__)


router = APIRouter(
    prefix="/api/admin/email",
    tags=["Email Admin"],
    dependencies=[Depends(require_admin)],
)


# =============================================================================
# Request Models
# =============================================================================

class UpdateServerConfigRequest(BaseModel):
    """更新 SMTP 配置请求体。

    Attributes:
        host: SMTP 主机名。
        port: SMTP 端口。
        use_ssl: 是否使用 SMTP_SSL。
        username: 登录账号。
        password: 密码或授权码；空字符串表示不修改原密码。
        sender_name: 发件人显示名。
        enabled: 是否启用。
        force_plain: 2026-07-18 新增；跳过 STARTTLS，仅 use_ssl=False 时生效。
        verify_ssl: 2026-07-18 新增；是否校验 SMTP 服务器 TLS 证书。
    """

    host: str = Field(..., min_length=1, max_length=200)
    port: int = Field(..., ge=1, le=65535)
    use_ssl: bool = Field(default=True)
    username: str = Field(..., min_length=1, max_length=200)
    password: str = Field(default="", description="空字符串表示不修改原密码")
    sender_name: str = Field(default="", max_length=200)
    enabled: bool = Field(default=True)
    force_plain: bool = Field(default=False, description="跳过 STARTTLS（25 端口明文 SMTP）")
    verify_ssl: bool = Field(default=True, description="是否校验 TLS 证书")


class TestConnectionRequest(BaseModel):
    """测试 SMTP 连接请求体。

    Attributes:
        host: SMTP 主机名。
        port: SMTP 端口。
        use_ssl: 是否使用 SMTP_SSL。
        username: 登录账号。
        password: 密码或授权码。
        force_plain: 2026-07-18 新增；跳过 STARTTLS。
        verify_ssl: 2026-07-18 新增；是否校验 TLS 证书。
    """

    host: str = Field(..., min_length=1, max_length=200)
    port: int = Field(..., ge=1, le=65535)
    use_ssl: bool = Field(default=True)
    username: str = Field(..., min_length=1, max_length=200)
    password: str = Field(default="")
    force_plain: bool = Field(default=False)
    verify_ssl: bool = Field(default=True)


class CreatePolicyRequest(BaseModel):
    """新建邮件策略请求体。

    Attributes:
        name: 策略名称。
        description: 策略描述。
        recipient_user_ids: 收件人用户 ID 列表。
        subject_template: 主题模板，含 ``{{var}}`` 占位符；空字符串表示
            使用策略名作为主题。
        body_template: 正文模板，含 ``{{var}}`` 占位符；空字符串表示直接使用
            脚本返回值作为正文。
    """

    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    recipient_user_ids: List[int] = Field(..., min_length=1)
    subject_template: str = Field(default="", max_length=500)
    body_template: str = Field(default="")


class UpdatePolicyRequest(BaseModel):
    """更新邮件策略请求体（未传字段保持原值）。

    Attributes:
        name: 策略名称。
        description: 策略描述。
        recipient_user_ids: 收件人用户 ID 列表。
        subject_template: 主题模板；None 表示不修改。
        body_template: 正文模板；None 表示不修改。
    """

    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    recipient_user_ids: Optional[List[int]] = Field(None, min_length=1)
    subject_template: Optional[str] = Field(None, max_length=500)
    body_template: Optional[str] = Field(None)


class SendByPolicyRequest(BaseModel):
    """按策略发送邮件请求体。

    Attributes:
        subject: 邮件主题。
        body: 邮件正文。
        attachment_paths: 附件绝对路径列表（服务器本地路径，脚本场景使用）。
    """

    subject: str = Field(..., min_length=1)
    body: str = Field(...)
    attachment_paths: Optional[List[str]] = Field(default=None)


# =============================================================================
# Helpers
# =============================================================================

def _get_config_service(request: Request) -> EmailConfigService:
    """从 app.state 获取 EmailConfigService。

    参数:
        request: FastAPI Request 对象。

    返回:
        EmailConfigService: 实例。

    异常:
        HTTPException: 服务未初始化时抛出 500。
    """
    service = getattr(request.app.state, "email_config_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="EmailConfigService not initialized",
        )
    return service


def _request_user_id(request: Request) -> int:
    """从 request.state 获取当前用户 ID。

    参数:
        request: FastAPI Request 对象。

    返回:
        int: 用户 ID，缺失时返回 0。
    """
    return int(getattr(request.state, "user_id", 0) or 0)


def _handle_config_error(exc: Exception) -> None:
    """将配置服务异常转换为 HTTPException。

    参数:
        exc: service 层异常。

    异常:
        HTTPException: 根据异常类型抛出对应 HTTP 错误。
    """
    if isinstance(exc, EmailConfigNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, EmailConfigValidationError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if isinstance(exc, EmailConfigError):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    raise exc


# =============================================================================
# SMTP Server Config Endpoints
# =============================================================================

@router.get("/server-config", response_model=Optional[Dict[str, Any]])
async def get_server_config(request: Request) -> Optional[Dict[str, Any]]:
    """获取当前启用的 SMTP 配置（密码字段返回空字符串，不外泄）。

    参数:
        request: FastAPI Request 对象。

    返回:
        Optional[Dict[str, Any]]: 配置字典；不存在返回 None。
    """
    service = _get_config_service(request)
    return await service.get_server_config_public()


@router.put("/server-config", response_model=Dict[str, Any])
async def update_server_config(
    request: Request,
    body: UpdateServerConfigRequest,
) -> Dict[str, Any]:
    """保存 SMTP 配置（密码为空字符串表示不修改原密码）。

    参数:
        request: FastAPI Request 对象。
        body: 更新请求体。

    返回:
        Dict[str, Any]: 含 id / updated_at 字段。
    """
    service = _get_config_service(request)
    config = EmailServerConfig(
        host=body.host,
        port=body.port,
        use_ssl=body.use_ssl,
        username=body.username,
        password=body.password,
        sender_name=body.sender_name,
        enabled=body.enabled,
        # 2026-07-18 新增：企业邮箱兼容字段
        force_plain=body.force_plain,
        verify_ssl=body.verify_ssl,
    )
    try:
        return await service.upsert_server_config(
            config,
            keep_existing_password=(not body.password),
        )
    except Exception as exc:
        _handle_config_error(exc)
        raise


@router.post("/server-config/test", response_model=Dict[str, Any])
async def test_server_config(
    request: Request,
    body: TestConnectionRequest,
) -> Dict[str, Any]:
    """测试 SMTP 连接（不发送邮件）。

    若 body.password 为空，则尝试从数据库读取已保存的密码。

    参数:
        request: FastAPI Request 对象。
        body: 测试请求体。

    返回:
        Dict[str, Any]: 含 success / message 字段。
    """
    service = _get_config_service(request)
    password = body.password
    if not password:
        # 从数据库读已保存的密码
        existing = await service.get_active_server_config()
        if existing and existing.username == body.username:
            password = existing.password

    config = EmailServerConfig(
        host=body.host,
        port=body.port,
        use_ssl=body.use_ssl,
        username=body.username,
        password=password,
        sender_name="",
        enabled=True,
        # 2026-07-18 新增：企业邮箱兼容字段
        force_plain=body.force_plain,
        verify_ssl=body.verify_ssl,
    )
    return await service.test_connection(config)


# =============================================================================
# Emailable Users Endpoint
# =============================================================================

@router.get("/emailable-users", response_model=List[Dict[str, Any]])
async def list_emailable_users(request: Request) -> List[Dict[str, Any]]:
    """列出已注册且邮箱非空的用户（供前端挑选收件人）。

    参数:
        request: FastAPI Request 对象。

    返回:
        List[Dict[str, Any]]: 用户列表，每项含 id / username / real_name / email。
    """
    service = _get_config_service(request)
    return await service.list_emailable_users()


# =============================================================================
# Policy CRUD Endpoints
# =============================================================================

@router.get("/policies", response_model=List[Dict[str, Any]])
async def list_policies(request: Request) -> List[Dict[str, Any]]:
    """列出所有邮件发送策略。

    参数:
        request: FastAPI Request 对象。

    返回:
        List[Dict[str, Any]]: 策略列表。
    """
    service = _get_config_service(request)
    return await service.list_policies()


@router.post(
    "/policies",
    status_code=status.HTTP_201_CREATED,
    response_model=Dict[str, Any],
)
async def create_policy(
    request: Request,
    body: CreatePolicyRequest,
) -> Dict[str, Any]:
    """新建邮件发送策略。

    参数:
        request: FastAPI Request 对象。
        body: 新建请求体。

    返回:
        Dict[str, Any]: 新建策略详情。
    """
    service = _get_config_service(request)
    try:
        return await service.create_policy(
            name=body.name,
            description=body.description,
            recipient_user_ids=body.recipient_user_ids,
            created_by_user_id=_request_user_id(request),
            subject_template=body.subject_template,
            body_template=body.body_template,
        )
    except Exception as exc:
        _handle_config_error(exc)
        raise


@router.put("/policies/{policy_id}", response_model=Dict[str, Any])
async def update_policy(
    request: Request,
    policy_id: int,
    body: UpdatePolicyRequest,
) -> Dict[str, Any]:
    """更新策略字段（未传字段保持原值）。

    参数:
        request: FastAPI Request 对象。
        policy_id: 策略 ID。
        body: 更新请求体。

    返回:
        Dict[str, Any]: 更新后的策略详情。
    """
    service = _get_config_service(request)
    try:
        return await service.update_policy(
            policy_id=policy_id,
            name=body.name,
            description=body.description,
            recipient_user_ids=body.recipient_user_ids,
            subject_template=body.subject_template,
            body_template=body.body_template,
        )
    except Exception as exc:
        _handle_config_error(exc)
        raise


@router.delete("/policies/{policy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_policy(request: Request, policy_id: int) -> None:
    """删除策略（关联表通过 ON DELETE CASCADE 自动清理）。

    参数:
        request: FastAPI Request 对象。
        policy_id: 策略 ID。

    返回:
        None。
    """
    service = _get_config_service(request)
    try:
        await service.delete_policy(policy_id)
    except Exception as exc:
        _handle_config_error(exc)
        raise


# =============================================================================
# Email Sending Endpoints
# =============================================================================

@router.post("/test", response_model=Dict[str, Any])
async def send_test_email(
    request: Request,
    to: str = Form(..., description="收件人邮箱（多个用逗号分隔）"),
    cc: str = Form("", description="抄送邮箱（多个用逗号分隔）"),
    subject: str = Form(..., description="邮件主题"),
    body: str = Form(..., description="邮件正文"),
    files: List[UploadFile] = File(default=[], description="附件列表"),
) -> Dict[str, Any]:
    """发送测试邮件（multipart/form-data，支持附件上传）。

    参数:
        request: FastAPI Request 对象。
        to: 收件人邮箱字符串（逗号分隔）。
        cc: 抄送邮箱字符串（逗号分隔）。
        subject: 邮件主题。
        body: 邮件正文。
        files: 附件上传列表。

    返回:
        Dict[str, Any]: 发送结果，含 success / message_id / sent_to。

    异常:
        HTTPException: SMTP 配置未初始化或发送失败时抛出。
    """
    config_service = _get_config_service(request)
    config = await config_service.get_active_server_config()
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="尚未配置 SMTP 服务器，请先在「服务器配置」Tab 保存配置",
        )

    to_list = [item.strip() for item in to.split(",") if item.strip()]
    cc_list = [item.strip() for item in cc.split(",") if item.strip()] if cc else []
    if not to_list:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="收件人不能为空",
        )

    # 读取上传附件为字节流
    attachment_streams: List[tuple] = []
    for upload_file in files:
        if not upload_file.filename:
            continue
        data = await upload_file.read()
        attachment_streams.append((upload_file.filename, data))

    email_service = EmailService(config)
    try:
        return await email_service.send_email(
            to=to_list,
            subject=subject,
            body=body,
            cc=cc_list or None,
            attachment_streams=attachment_streams or None,
        )
    except EmailSendError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc


@router.post(
    "/send-by-policy/{policy_id}",
    response_model=Dict[str, Any],
)
async def send_by_policy(
    request: Request,
    policy_id: int,
    body: SendByPolicyRequest,
) -> Dict[str, Any]:
    """按策略发送邮件。

    从策略中读取收件人列表，使用当前启用的 SMTP 配置发送邮件。

    参数:
        request: FastAPI Request 对象。
        policy_id: 策略 ID。
        body: 发送请求体（含主题/正文/附件路径）。

    返回:
        Dict[str, Any]: 发送结果。

    异常:
        HTTPException: 策略不存在 / 配置未初始化 / 发送失败时抛出。
    """
    config_service = _get_config_service(request)
    config = await config_service.get_active_server_config()
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="尚未配置 SMTP 服务器",
        )

    try:
        policy = await config_service.get_policy(policy_id)
    except EmailConfigNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc

    recipients = policy.get("recipients", [])
    to_list = [r["email"] for r in recipients if r.get("email")]
    if not to_list:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="策略中没有有效的收件人邮箱",
        )

    email_service = EmailService(config)
    try:
        return await email_service.send_email(
            to=to_list,
            subject=body.subject,
            body=body.body,
            attachment_paths=body.attachment_paths,
        )
    except EmailSendError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
