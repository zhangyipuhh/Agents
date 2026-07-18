# -*- coding:utf-8 -*-
"""
邮件核心发送服务模块。

``EmailService`` 仅依赖 ``EmailServerConfig``，与 FastAPI / app.state 完全解耦，
可在以下场景直接复用：

1. FastAPI Router 调用：从 ``app.state.email_config_service`` 拿到配置后构造实例。
2. 脚本直接调用：
   ``asyncio.run(EmailService(config).send_email(to=[...], subject=..., body=...))``

实现细节：
- 使用 Python 标准库 ``smtplib`` + ``email.message.EmailMessage``，无需额外依赖。
- ``smtplib`` 是同步库，所有 SMTP 调用通过 ``asyncio.to_thread`` 包装为异步，
  避免阻塞事件循环。
- 附件支持两种来源：
  - ``attachment_paths``：本地文件绝对路径列表（脚本场景）。
  - ``attachment_streams``：(文件名, 字节流) 元组列表（FastAPI UploadFile 场景）。
"""
import asyncio
import logging
import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from typing import Any, Dict, List, Optional, Tuple

from app.shared.utils.email.email_models import EmailServerConfig


logger = logging.getLogger(__name__)


class EmailSendError(Exception):
    """邮件发送失败时抛出。"""


class EmailService:
    """邮件发送服务。

    参数:
        config: ``EmailServerConfig`` 实例，提供 SMTP 连接信息与发件人配置。
    """

    def __init__(self, config: EmailServerConfig) -> None:
        """初始化邮件发送服务。

        参数:
            config: SMTP 服务器配置实例。

        异常:
            ValueError: config 为 None 时抛出。
        """
        if config is None:
            raise ValueError("EmailServerConfig 不能为空")
        self._config = config

    @classmethod
    async def from_db(
        cls,
        db: Any,
        credential_key: str,
    ) -> "EmailService":
        """从数据库加载启用的 SMTP 配置并构造实例。

        参数:
            db: asyncpg 连接池；需支持 ``fetchrow`` 异步方法。
            credential_key: Fernet 密钥（base64 字符串），用于解密密码字段。

        返回:
            EmailService: 实例。

        异常:
            EmailSendError: 数据库无启用配置或解密失败时抛出。
        """
        from app.shared.utils.email.email_config_service import EmailConfigService

        config_service = EmailConfigService(db=db, credential_key=credential_key)
        config = await config_service.get_active_server_config()
        if config is None:
            raise EmailSendError("数据库中未找到启用的 SMTP 配置")
        return cls(config)

    async def send_email(
        self,
        to: List[str],
        subject: str,
        body: str,
        cc: Optional[List[str]] = None,
        attachment_paths: Optional[List[str]] = None,
        attachment_streams: Optional[List[Tuple[str, bytes]]] = None,
    ) -> Dict[str, Any]:
        """发送邮件，返回发送结果。

        参数:
            to: 收件人邮箱地址列表。
            subject: 邮件主题。
            body: 邮件正文（纯文本）。
            cc: 抄送邮箱地址列表；None 或空列表表示无抄送。
            attachment_paths: 附件本地绝对路径列表；None 或空列表表示无路径附件。
            attachment_streams: (文件名, 字节流) 元组列表；None 或空列表表示无流附件。

        返回:
            Dict[str, Any]: 含 ``success`` / ``message_id`` / ``sent_to`` 三个字段。

        异常:
            EmailSendError: SMTP 连接 / 登录 / 发送失败时抛出。
            FileNotFoundError: ``attachment_paths`` 中的路径不存在时抛出。
        """
        if not to:
            raise EmailSendError("收件人列表不能为空")

        msg = self._build_message(
            to=to, subject=subject, body=body, cc=cc,
            attachment_paths=attachment_paths,
            attachment_streams=attachment_streams,
        )

        try:
            await asyncio.to_thread(self._smtp_send, msg, to, cc or [])
        except Exception as exc:
            logger.error("[email_service] 发送失败: %s", exc, exc_info=True)
            raise EmailSendError(f"邮件发送失败: {exc}") from exc

        return {
            "success": True,
            "message_id": msg["Message-ID"],
            "sent_to": to,
        }

    def _build_message(
        self,
        to: List[str],
        subject: str,
        body: str,
        cc: Optional[List[str]],
        attachment_paths: Optional[List[str]],
        attachment_streams: Optional[List[Tuple[str, bytes]]],
    ) -> EmailMessage:
        """构造 ``EmailMessage`` 对象。

        参数:
            to: 收件人列表。
            subject: 主题。
            body: 正文。
            cc: 抄送列表；None 视为空。
            attachment_paths: 附件路径列表；None 视为空。
            attachment_streams: 附件流列表；None 视为空。

        返回:
            EmailMessage: 已填充所有字段的邮件对象。

        异常:
            FileNotFoundError: 附件路径不存在时抛出。
        """
        cfg = self._config
        msg = EmailMessage()
        msg["From"] = formataddr((cfg.sender_name or cfg.username, cfg.username))
        msg["To"] = ", ".join(to)
        if cc:
            msg["Cc"] = ", ".join(cc)
        msg["Subject"] = subject
        # 2026-07-18 新增：补齐 RFC 5322 必备头，规避反垃圾误判
        # - Date：缺 Date 头会被多家邮件服务器（QQ / 网易 / 企业 Exchange）
        #   判为伪造邮件直接拒收或进垃圾箱
        # - MIME-Version：包含附件/HTML 时必须 1.0，否则部分服务器拒收
        msg["Date"] = formatdate(localtime=True)
        msg["MIME-Version"] = "1.0"
        # Message-ID 域必须与 From 域一致（反垃圾关键校验点）。
        # cfg.host 是 SMTP 主机（smtp.qq.com / mail.geostar.com.cn），
        # cfg.username 的 @ 后面才是真实的发件人域（qq.com / foxmail.com /
        # geostar.com.cn）。注意：cfg.username 可能已经是邮箱全地址，
        # 需要先剥掉 @ 之前的本地部分。
        from_addr_domain = cfg.username.rsplit("@", 1)[-1] if "@" in cfg.username else cfg.host
        msg["Message-ID"] = make_msgid(domain=from_addr_domain)
        msg.set_content(body)

        # 附件：本地文件路径
        for path in (attachment_paths or []):
            if not os.path.isfile(path):
                raise FileNotFoundError(f"附件不存在: {path}")
            with open(path, "rb") as fp:
                data = fp.read()
            filename = os.path.basename(path)
            maintype, _, subtype = self._guess_type(filename)
            msg.add_attachment(
                data, maintype=maintype, subtype=subtype, filename=filename
            )

        # 附件：字节流（FastAPI UploadFile 场景）
        for filename, data in (attachment_streams or []):
            maintype, _, subtype = self._guess_type(filename)
            msg.add_attachment(
                data, maintype=maintype, subtype=subtype, filename=filename
            )

        return msg

    @staticmethod
    def _guess_type(filename: str) -> Tuple[str, str, str]:
        """根据文件名扩展名猜测 MIME 类型。

        参数:
            filename: 文件名（含扩展名）。

        返回:
            Tuple[str, str, str]: (maintype, "/", subtype)，例如 ``("application", "/", "pdf")``。
            无法识别时返回 ``("application", "/", "octet-stream")``。
        """
        import mimetypes
        guessed, _ = mimetypes.guess_type(filename)
        if guessed and "/" in guessed:
            maintype, subtype = guessed.split("/", 1)
            return maintype, "/", subtype
        return "application", "/", "octet-stream"

    def _smtp_send(
        self,
        msg: EmailMessage,
        to: List[str],
        cc: List[str],
    ) -> None:
        """同步执行 SMTP 连接 + 登录 + 发送 + 关闭。

        参数:
            msg: 已构造好的 ``EmailMessage``。
            to: 收件人列表。
            cc: 抄送列表。

        异常:
            smtplib.SMTPException: 任意 SMTP 操作失败时抛出。

        注意:
            显式传入 ``local_hostname=cfg.host`` 以规避 Windows 中文主机名
            场景下 ``socket.getfqdn()`` 返回非 ASCII 字符串导致 ``EHLO``
            命令在 ``smtplib`` 内部以 ``ascii`` 编码失败的问题。

        2026-07-18 新增：复用 ``EmailConfigService._build_ssl_context``
        兼容企业邮箱老 TLS 协议；``cfg.force_plain=True`` 时跳过 STARTTLS
        支持 25 端口明文 SMTP。
        """
        cfg = self._config
        recipients = list(to) + list(cc)
        # 延迟导入避免循环依赖（email_config_service 反向依赖 email_models）
        from app.shared.utils.email.email_config_service import EmailConfigService

        context = EmailConfigService._build_ssl_context(cfg)
        if cfg.use_ssl:
            with smtplib.SMTP_SSL(
                cfg.host, cfg.port,
                context=context, timeout=30,
                local_hostname=cfg.host,
            ) as smtp:
                smtp.login(cfg.username, cfg.password)
                refused = smtp.send_message(msg, to_addrs=recipients)
                # 2026-07-18 新增：send_message 在收件人/RCPT TO 被拒时
                # 会把失败项存到 refused 字典而不抛异常，导致 UI 显示
                # 成功但实际邮件未送达。这里做显式校验。
                if refused:
                    raise EmailSendError(
                        f"SMTP 服务器拒收部分收件人: {refused}"
                    )
        else:
            with smtplib.SMTP(
                cfg.host, cfg.port,
                timeout=30,
                local_hostname=cfg.host,
            ) as smtp:
                # 2026-07-18 新增：force_plain=True 时跳过 STARTTLS
                if not cfg.force_plain:
                    smtp.starttls(context=context)
                smtp.login(cfg.username, cfg.password)
                refused = smtp.send_message(msg, to_addrs=recipients)
                # 同上：send_message 的静默拒收校验
                if refused:
                    raise EmailSendError(
                        f"SMTP 服务器拒收部分收件人: {refused}"
                    )
