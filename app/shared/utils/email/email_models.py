# -*- coding:utf-8 -*-
"""
邮件系统数据模型模块。

定义 SMTP 服务器配置、邮件发送策略以及发送请求的 Pydantic 模型。
所有模型均为纯数据容器，不依赖 FastAPI / Request，可在脚本与 Web 服务之间复用。

模型清单：
- ``EmailServerConfig``：SMTP 服务器配置（含明文密码，仅内存中流转）
- ``EmailPolicy``：邮件发送策略（策略名 + 描述 + 收件人用户 ID 列表）
- ``SendEmailRequest``：发送邮件请求体（脚本与 HTTP 共用）
"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class EmailServerConfig(BaseModel):
    """SMTP 服务器配置。

    Attributes:
        host: SMTP 服务器主机名，例如 ``smtp.qq.com``。
        port: SMTP 服务器端口；SSL 直连通常为 465，STARTTLS 通常为 587。
        use_ssl: 是否使用 SMTP_SSL 直连（True 走 465，False 走 STARTTLS）。
        username: 登录账号（通常为发件邮箱地址）。
        password: 登录密码或授权码（明文，仅内存中流转；持久化时由
            ``EmailConfigService`` 使用 Fernet 加密）。
        sender_name: 发件人显示名称；空字符串表示使用 username 作为显示名。
        enabled: 是否启用；同一时刻只允许一条配置启用（DB 唯一索引约束）。
        force_plain: 跳过 STARTTLS，仅在 ``use_ssl=False`` 时生效；
            企业邮箱 25 端口明文 SMTP 场景使用。默认 False。
        verify_ssl: 是否校验 SMTP 服务器 TLS 证书；企业自签证书时可设为 False。默认 True。
    """

    host: str = Field(..., min_length=1, max_length=200, description="SMTP 主机")
    port: int = Field(default=465, ge=1, le=65535, description="SMTP 端口")
    use_ssl: bool = Field(default=True, description="True=SMTP_SSL(465)，False=STARTTLS(587)")
    username: str = Field(..., min_length=1, max_length=200, description="登录账号")
    password: str = Field(default="", description="密码或授权码（明文，仅内存）")
    sender_name: str = Field(default="", max_length=200, description="发件人显示名")
    enabled: bool = Field(default=True, description="是否启用")
    # 2026-07-18 新增：企业邮箱兼容字段（方案 Z）
    force_plain: bool = Field(
        default=False,
        description="跳过 STARTTLS，仅在 use_ssl=False 时生效；支持 25 端口明文 SMTP",
    )
    verify_ssl: bool = Field(
        default=True,
        description="是否校验 SMTP 服务器 TLS 证书；自签证书可设为 False",
    )


class EmailPolicy(BaseModel):
    """邮件发送策略（含收件人集合与可选模板）。

    Attributes:
        id: 策略 ID；新建时为 None。
        name: 策略名称（必填）。
        description: 策略描述；空字符串表示无描述。
        recipient_user_ids: 收件人用户 ID 列表（指向 ``users.id``）；
            用户必须已注册且 ``email`` 字段非空。
        subject_template: 邮件主题模板，含 ``{{var}}`` 占位符；空字符串表示
            使用策略名作为主题。支持 ``{{timestamp|FORMAT}}`` 在渲染时动态插入
            当前时间，例如 ``{{timestamp|%Y%m%d%H%M}}``。
        body_template: 邮件正文模板，含 ``{{var}}`` 占位符；空字符串表示直接使用
            脚本返回值作为正文。可用变量由 ``EmailTemplateRenderer.SUPPORTED_VARS``
            定义，并支持 ``{{timestamp|FORMAT}}`` 内联时间格式。
        created_by_user_id: 创建者用户 ID（策略归属字段）；用于按创建者做
            可见性隔离（admin 见全部，普通用户仅见自己创建）。新建时为 None。
        created_at: 创建时间；新建时为 None。
        updated_at: 更新时间；新建时为 None。
    """

    id: Optional[int] = Field(default=None, description="策略 ID")
    name: str = Field(..., min_length=1, max_length=200, description="策略名称")
    description: str = Field(default="", max_length=2000, description="策略描述")
    recipient_user_ids: List[int] = Field(
        default_factory=list, description="收件人用户 ID 列表"
    )
    subject_template: str = Field(
        default="",
        max_length=500,
        description="主题模板（{{var}} 占位符，留空使用策略名）",
    )
    body_template: str = Field(
        default="",
        description="正文模板（{{var}} 占位符，留空使用脚本返回 body）",
    )
    created_by_user_id: Optional[int] = Field(
        default=None, description="创建者用户 ID（归属字段，用于按用户隔离）"
    )
    created_at: Optional[datetime] = Field(default=None, description="创建时间")
    updated_at: Optional[datetime] = Field(default=None, description="更新时间")


class SendEmailRequest(BaseModel):
    """发送邮件请求体（脚本与 HTTP 共用）。

    Attributes:
        to: 收件人邮箱地址列表。
        cc: 抄送邮箱地址列表；None 表示无抄送。
        subject: 邮件主题。
        body: 邮件正文（纯文本）。
        attachment_paths: 附件绝对路径列表（脚本场景使用本地文件路径）。
    """

    to: List[str] = Field(..., min_length=1, description="收件人邮箱列表")
    cc: Optional[List[str]] = Field(default=None, description="抄送邮箱列表")
    subject: str = Field(..., min_length=1, description="邮件主题")
    body: str = Field(..., description="邮件正文")
    attachment_paths: Optional[List[str]] = Field(
        default=None, description="附件绝对路径列表"
    )
