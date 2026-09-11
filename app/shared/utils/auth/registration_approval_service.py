# -*- coding:utf-8 -*-
"""注册审批业务服务(2026-08-30 新增,等保三级 §7.1.3 访问控制 a/e)

职责:
1. approve_user / reject_user:调用 UserDB.update_user_status + 写审计 + 通知用户邮件
2. notify_admin_new_registration:注册提交时通知 admin(邮件 + 飞书可选)

设计原则:
- 通知失败 fail-soft(仅 logger.warning,不抛异常、不污染业务响应)
- 审计 emit 同样 fail-soft
- reject_user 缺 reason 抛 ValueError(路由层映射 400)
- 非 pending_approval 返回 None(路由层映射 409 Conflict)
"""
import asyncio
import logging
from typing import Optional

from app.core.config.settings import settings
from app.shared.utils.auth.user_db import UserDB

logger = logging.getLogger(__name__)


def _send_approval_email(to: str, subject: str, body: str) -> None:
    """发送审批结果通知邮件给用户(fail-soft)。"""
    try:
        from app.shared.utils.email.email_service import EmailService
        from app.core.database import DatabasePool

        async def _do_send():
            db = DatabasePool._pool if DatabasePool.is_enabled() else None
            svc = await EmailService.from_db(db=db)
            return await svc.send_email(to=[to], subject=subject, body=body)

        asyncio.run(_do_send())
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "[registration_approval_service] 邮件发送失败 to=%s subject=%s err=%s",
            to, subject, type(exc).__name__,
        )


def _send_admin_email(to_list: list, subject: str, body: str) -> None:
    """发送通知邮件给 admin(fail-soft)。"""
    try:
        from app.shared.utils.email.email_service import EmailService
        from app.core.database import DatabasePool

        async def _do_send():
            db = DatabasePool._pool if DatabasePool.is_enabled() else None
            svc = await EmailService.from_db(db=db)
            return await svc.send_email(to=to_list, subject=subject, body=body)

        asyncio.run(_do_send())
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "[registration_approval_service] admin 邮件发送失败 to=%s err=%s",
            to_list, type(exc).__name__,
        )


def _get_notification_service():
    """从 ``app.state.notification_config_service`` 取服务实例（延迟 import）。

    Returns:
        Optional[NotificationConfigService]: 未初始化时返回 None。
    """
    try:
        from app.main import app as _fastapi_app

        return getattr(_fastapi_app.state, "notification_config_service", None)
    except Exception:  # noqa: BLE001
        return None


def _build_admin_lark_client(channel: dict):
    """用 channel 明文凭证构造临时 lark.Client（系统级通知用，不走全局单例）。

    Args:
        channel: ``resolve_default_channel("feishu")`` 返回的 channel dict，
            ``config`` 中含 ``app_id_encrypted`` / ``app_secret_encrypted`` /
            ``log_level``（密文）。

    Returns:
        lark.Client: 新实例。
    """
    import lark_oapi as lark

    svc = _get_notification_service()
    cfg = channel["config"]
    app_id = svc.decrypt_field(cfg.get("app_id_encrypted") or "")
    app_secret = svc.decrypt_field(cfg.get("app_secret_encrypted") or "")
    log_level_str = cfg.get("log_level", "INFO") or "INFO"
    log_level_map = {
        "DEBUG": lark.LogLevel.DEBUG,
        "INFO": lark.LogLevel.INFO,
        "WARNING": lark.LogLevel.WARNING,
        "ERROR": lark.LogLevel.ERROR,
    }
    return (
        lark.Client.builder()
        .app_id(app_id)
        .app_secret(app_secret)
        .log_level(log_level_map.get(log_level_str.upper(), lark.LogLevel.INFO))
        .build()
    )


def _send_feishu_to_admin(content: str) -> None:
    """通过飞书发送通知给 admin（fail-soft，仅在 feishu_notify_enabled=True 时调用）。

    数据源（2026-09-11 切换）：
        - 不再读 ``settings.feishu.feishu_default_receive_id``（.env 已废弃）
        - 走 DB ``resolve_default_channel("feishu")`` 取全局默认渠道
        - 该渠道下第一个 ``enabled=TRUE`` 的 target 作为接收方
        - 用渠道明文凭证构造临时 ``lark.Client``（不走全局单例）
    """
    try:
        svc = _get_notification_service()
        if svc is None:
            logger.warning(
                "[registration_approval_service] notification_config_service 未初始化,跳过"
            )
            return

        import asyncio

        async def _resolve():
            ch = await svc.resolve_default_channel("feishu")
            if ch is None:
                return None, None
            targets = await svc.list_targets(channel_id=ch["id"])
            enabled = [t for t in targets if t.get("enabled")]
            return ch, (enabled[0] if enabled else None)

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                fut = asyncio.run_coroutine_threadsafe(_resolve(), loop)
                ch, target = fut.result(timeout=5.0)
            else:
                ch, target = loop.run_until_complete(_resolve())
        except RuntimeError:
            # 测试环境 / 同步上下文无 loop:用 asyncio.run 一次性执行
            try:
                ch, target = asyncio.run(_resolve())
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "[registration_approval_service] 异步解析失败 err=%s",
                    type(exc).__name__,
                )
                return

        if ch is None:
            logger.warning("[registration_approval_service] 无默认飞书渠道,跳过")
            return
        if target is None:
            logger.warning(
                "[registration_approval_service] 默认渠道 %s 无 enabled target,跳过",
                ch.get("name"),
            )
            return

        tg_cfg = target.get("config") or {}
        chat_id = tg_cfg.get("chat_id")
        chat_type = tg_cfg.get("chat_type", "chat_id") or "chat_id"
        if not chat_id:
            logger.warning(
                "[registration_approval_service] target %s chat_id 为空,跳过",
                target.get("id"),
            )
            return

        client = _build_admin_lark_client(ch)

        from lark_oapi.api.im.v1 import (
            CreateMessageRequest,
            CreateMessageRequestBody,
        )
        body = (
            CreateMessageRequestBody.builder()
            .receive_id(chat_id)
            .msg_type("text")
            .content('{"text": "' + content.replace('"', '\\"').replace('\n', '\\n') + '"}')
            .uuid(str(__import__("uuid").uuid4()))
            .build()
        )
        request = (
            CreateMessageRequest.builder()
            .receive_id_type(chat_type)
            .request_body(body)
            .build()
        )
        client.im.v1.message.create(request)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "[registration_approval_service] 飞书发送失败 err=%s", type(exc).__name__
        )


def _emit_audit(
    *,
    action: str,
    user_id: int,
    username: str,
    operator_user_id: int,
    operator_username: str,
    ip_address: Optional[str] = None,
    reason: Optional[str] = None,
) -> None:
    """统一审计日志(fail-soft)。"""
    try:
        from app.shared.utils.log_service import (
            LogEvent, LogLevel, LogResult, LogType, get_log_service,
        )
        svc = get_log_service()
        if svc is None:
            return

        metadata = {}
        if reason:
            metadata["reason"] = reason

        event = LogEvent(
            action=action,
            log_type=LogType.USER,
            result=LogResult.SUCCESS,
            level=LogLevel.INFO if action == "register_approved" else LogLevel.WARNING,
            source="registration_approval_service",
            user_id=user_id,
            username=username,
            target_type="user",
            target_id=str(user_id),
            target_name=username,
            metadata=metadata,
            message=f"{action} target_user={username} operator={operator_username}",
        )
        svc.emit(event)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "[registration_approval_service] 审计 emit 失败 action=%s err=%s",
            action, type(exc).__name__,
        )


class RegistrationApprovalService:
    """注册审批业务服务(staticmethods,无内部状态)。"""

    @staticmethod
    async def approve_user(
        user_id: int,
        operator_user_id: int,
        operator_username: str,
    ) -> bool:
        """审批通过:将 user.status 改为 active。

        Args:
            user_id: 目标用户 ID
            operator_user_id: 操作人用户 ID
            operator_username: 操作人用户名

        Returns:
            bool: 成功返回 True;用户不存在或非 pending_approval 状态返回 False

        Raises:
            ValueError: user_id 不存在
        """
        user = await UserDB.get_user_by_id(user_id)
        if user is None:
            raise ValueError(f"用户不存在 user_id={user_id}")

        success = await UserDB.update_user_status(
            user_id=user_id,
            status="active",
            reason=None,
            operator_user_id=operator_user_id,
        )
        if not success:
            return False

        email = user.get("email", "")
        if email:
            try:
                _send_approval_email(
                    email,
                    "[账号审批通过] 您已可以登录系统",
                    (
                        f"您好 {user.get('real_name', '')}:\n\n"
                        f"您的注册申请已通过审批,现在可以使用用户名 "
                        f"{user.get('username', '')} 登录系统。\n\n"
                        f"—— 系统管理员"
                    ),
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "[registration_approval_service] approve_user 邮件调用异常 user_id=%s err=%s",
                    user_id, type(exc).__name__,
                )

        _emit_audit(
            action="register_approved",
            user_id=user_id,
            username=user.get("username", ""),
            operator_user_id=operator_user_id,
            operator_username=operator_username,
        )
        return True

    @staticmethod
    async def reject_user(
        user_id: int,
        reason: str,
        operator_user_id: int,
        operator_username: str,
    ) -> Optional[bool]:
        """审批拒绝:将 user.status 改为 rejected,写 reason。

        Args:
            user_id: 目标用户 ID
            reason: 拒绝原因(≥1 字符)
            operator_user_id: 操作人用户 ID
            operator_username: 操作人用户名

        Returns:
            Optional[bool]:
                - True: 拒绝成功
                - None: 用户当前不是 pending_approval(路由层映射 409)
                - 抛 ValueError: 用户不存在 / reason 为空
        """
        if not reason or not reason.strip():
            raise ValueError("拒绝时 reason 必填且不可为空")

        user = await UserDB.get_user_by_id(user_id)
        if user is None:
            raise ValueError(f"用户不存在 user_id={user_id}")

        success = await UserDB.update_user_status(
            user_id=user_id,
            status="rejected",
            reason=reason,
            operator_user_id=operator_user_id,
        )
        if not success:
            return None

        email = user.get("email", "")
        if email:
            try:
                _send_approval_email(
                    email,
                    "[账号审批未通过] 请联系管理员",
                    (
                        f"您好 {user.get('real_name', '')}:\n\n"
                        f"您的注册申请未通过审批。\n"
                        f"原因: {reason}\n\n"
                        f"如有疑问,请联系系统管理员。\n\n"
                        f"—— 系统管理员"
                    ),
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "[registration_approval_service] reject_user 邮件调用异常 user_id=%s err=%s",
                    user_id, type(exc).__name__,
                )

        _emit_audit(
            action="register_rejected",
            user_id=user_id,
            username=user.get("username", ""),
            operator_user_id=operator_user_id,
            operator_username=operator_username,
            reason=reason,
        )
        return True


async def notify_admin_new_registration(
    username: str,
    real_name: str,
    email: str,
    register_ip: str,
) -> None:
    """注册提交时通知 admin(邮件 + 飞书可选开关)。"""
    from datetime import datetime
    cfg = settings.registration_security
    if not cfg.admin_notification_emails and not cfg.feishu_notify_enabled:
        return

    body = (
        f"新用户注册待审批:\n"
        f"  用户名: {username}\n"
        f"  真实姓名: {real_name}\n"
        f"  邮箱: {email}\n"
        f"  来源 IP: {register_ip}\n"
        f"  提交时间: {datetime.utcnow().isoformat()}Z\n\n"
        f"请登录系统 → 用户管理 → 待审批 进行处理。\n"
    )

    if cfg.admin_notification_emails:
        _send_admin_email(
            to_list=list(cfg.admin_notification_emails),
            subject=f"[新用户注册待审批] {username}",
            body=body,
        )
    if cfg.feishu_notify_enabled:
        _send_feishu_to_admin(content=body)
