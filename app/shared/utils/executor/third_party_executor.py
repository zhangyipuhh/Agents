# -*- coding:utf-8 -*-
"""
第三方命令执行器（2026-08-03 新增）。

职责：
    - 接收明文请求体 + 端点名
    - 加密请求体（RSA-OAEP + AES-256-GCM）→ 调用 HTTPS 接口
    - 解析明文 JSON 响应 → 返回
    - 所有异常统一封装为 ``ThirdPartyExecutorError``

调用关系：
    SSHTools.execute_command
        └─→ third_party_executor.dispatch(endpoint_name, payload, timeout)
                ├─→ endpoints.ThirdPartyEndpointRegistry.get(name)
                ├─→ crypto.rsa_aes.encrypt_body(...)
                └─→ httpx.AsyncClient.post(url, json=encrypted, timeout=...)

Date: 2026-08-03
Author: AI Assistant
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import httpx

from app.shared.utils.crypto.rsa_aes import (
    RSAEncryptError,
    encrypt_body,
)
from app.shared.utils.executor.endpoints import ThirdPartyEndpointRegistry
from app.shared.utils.executor.errors import (
    ERR_CRYPTO_ENCRYPT,
    ERR_HTTP,
    ERR_INVALID_RESPONSE,
    ERR_TIMEOUT,
    ThirdPartyExecutorError,
)


logger = logging.getLogger(__name__)


def _build_request_body(
    *,
    command: str,
    wrapped_command: str,
    business_name: str,
    timeout: int,
    server_type: Optional[str],
    ssh_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """构造明文请求体。

    Args:
        command: 用户原始命令
        wrapped_command: 平台派生后命令（Linux/bash 或 Windows/powershell 包装）
        business_name: 业务名
        timeout: 超时（秒）
        server_type: 平台类型（linux / windows）
        ssh_config: 可选 SSH 连接配置（含 ip / port / username / password），
            用于第三方接口按"ip+username 均非空 → 走 SSH 远程执行"分流。
            不传或为空 dict 时，第三方走"本机执行"路径。

    Returns:
        Dict[str, Any]: 明文请求体（按第三方接口契约 v1）

    Notes:
        字段集严格遵循第三方契约 ``execute接口说明.md``：
        - 必填: command / wrapped_command / issued_at
        - 可选 SSH: ip / port / username / password（缺省时第三方本机执行）
        - 元数据: business_name / timeout / platform / request_id
    """
    import uuid
    from datetime import datetime, timezone

    body: Dict[str, Any] = {
        "command": command,
        "wrapped_command": wrapped_command,
        "business_name": business_name,
        "timeout": int(timeout),
        "platform": (server_type or "linux").lower(),
        "request_id": str(uuid.uuid4()),
        "issued_at": datetime.now(timezone.utc).isoformat(),
    }
    # 注入 SSH 连接信息（按第三方契约：ip+username 均非空 → SSH 远程执行）
    if ssh_config:
        ip = ssh_config.get("ip")
        port = ssh_config.get("port")
        username = ssh_config.get("username")
        password = ssh_config.get("password")
        if ip and username:
            body["ip"] = str(ip)
            body["port"] = int(port) if port else 22
            body["username"] = str(username)
            # password 在 SSH 模式下必填；缺失时透传空串，由第三方判 400
            body["password"] = password if password is not None else ""
    return body


async def dispatch(
    *,
    endpoint_name: str,
    command: str,
    wrapped_command: str,
    business_name: str,
    timeout: int,
    server_type: Optional[str],
    ssh_config: Optional[Dict[str, Any]] = None,
    client: Optional[httpx.AsyncClient] = None,
) -> Dict[str, Any]:
    """向指定第三方端点发起加密命令执行请求并返回明文响应。

    Args:
        endpoint_name: 端点名
        command: 用户原始命令
        wrapped_command: 平台派生后命令
        business_name: 业务名
        timeout: 单条命令执行超时（秒），传给第三方
        server_type: 平台类型
        ssh_config: 可选 SSH 连接配置（含 ip / port / username / password），
            来源一般是 DevOpsServerService.get_connection_config 的返回值。
        client: 可选 httpx 客户端（测试注入使用）；None 时新建

    Returns:
        Dict[str, Any]: 第三方明文响应（``success`` / ``output`` / ``error?`` /
            ``exit_code``）

    Raises:
        ThirdPartyExecutorError: 端点配置缺失 / 加密失败 / HTTP 失败 / 超时 /
            响应非法时抛出
    """
    registry = ThirdPartyEndpointRegistry.get_instance()
    endpoint = registry.get(endpoint_name)

    plaintext = _build_request_body(
        command=command,
        wrapped_command=wrapped_command,
        business_name=business_name,
        timeout=timeout,
        server_type=server_type,
        ssh_config=ssh_config,
    )

    # 1. 加密请求体
    try:
        encrypted_payload = encrypt_body(
            plaintext, endpoint.public_key_pem
        )
    except RSAEncryptError as exc:
        logger.warning(
            "[third_party_executor] encrypt failed (endpoint=%s): %s",
            endpoint_name,
            type(exc).__name__,
        )
        raise ThirdPartyExecutorError(
            error_code=ERR_CRYPTO_ENCRYPT,
            reason=f"RSA+AES 加密失败: {exc}",
            user_message="加密请求体失败",
        ) from exc

    # 2. HTTPS 调用
    own_client = client is None
    http_client = client or httpx.AsyncClient(timeout=endpoint.timeout_seconds)
    try:
        try:
            response = await http_client.post(
                endpoint.url,
                json=encrypted_payload,
                headers={"Content-Type": "application/json"},
            )
        except httpx.TimeoutException as exc:
            logger.warning(
                "[third_party_executor] timeout (endpoint=%s): %s",
                endpoint_name,
                type(exc).__name__,
            )
            raise ThirdPartyExecutorError(
                error_code=ERR_TIMEOUT,
                reason=f"第三方调用超时: {exc}",
                user_message="第三方执行超时",
            ) from exc
        except httpx.HTTPError as exc:
            logger.warning(
                "[third_party_executor] http error (endpoint=%s): %s",
                endpoint_name,
                type(exc).__name__,
            )
            raise ThirdPartyExecutorError(
                error_code=ERR_HTTP,
                reason=f"第三方 HTTP 错误: {exc}",
                user_message="第三方调用失败",
            ) from exc

        # 3. 响应体解析（无论 HTTP 状态码都尝试解析，第三方契约：
        #    400/500 时 body 也是 {success:false, error:...} 结构）
        try:
            body = response.json()
        except Exception:  # noqa: BLE001
            body = None

        if not isinstance(body, dict):
            body = None

        # 4. HTTP 状态码校验
        if response.status_code >= 400:
            # 尝试从 body 提取 error 字段（第三方契约保证结构存在）
            err_detail = ""
            if isinstance(body, dict):
                err_raw = body.get("error") or body.get("detail")
                if err_raw:
                    err_detail = str(err_raw)
            reason = f"第三方返回 HTTP {response.status_code} (endpoint={endpoint_name})"
            if err_detail:
                reason += f" | error={err_detail}"
            # 不在 user_message 中回显 err_detail（避免泄漏第三方内部细节）
            raise ThirdPartyExecutorError(
                error_code=ERR_HTTP,
                reason=reason,
                user_message=f"第三方返回错误 ({response.status_code})",
            )

        if body is None:
            raise ThirdPartyExecutorError(
                error_code=ERR_INVALID_RESPONSE,
                reason="第三方响应非 JSON",
                user_message="第三方响应格式错误",
            )

        if not isinstance(body, dict):
            raise ThirdPartyExecutorError(
                error_code=ERR_INVALID_RESPONSE,
                reason="第三方响应不是 dict",
                user_message="第三方响应格式错误",
            )

        return body
    finally:
        if own_client and http_client is not None:
            try:
                await http_client.aclose()
            except Exception:  # noqa: BLE001 - close 失败不影响业务
                pass


def normalize_response(response: Dict[str, Any]) -> Dict[str, Any]:
    """把第三方响应归一化为既有 ``payload`` 结构。

    既有本地路径 ``payload`` 结构（见 SSHTools.execute_command）::

        {
            "success": bool,
            "output": str,
            "exit_code": int,
            # 可选：
            "error": str,
        }

    Args:
        response: 第三方原始响应

    Returns:
        Dict[str, Any]: 标准化后的 payload

    Raises:
        ThirdPartyExecutorError: 响应缺少必填字段或类型非法
    """
    if "success" not in response:
        raise ThirdPartyExecutorError(
            error_code=ERR_INVALID_RESPONSE,
            reason="第三方响应缺少 success 字段",
            user_message="第三方响应格式错误",
        )
    success = bool(response.get("success"))
    try:
        exit_code = int(response.get("exit_code") or 0)
    except (TypeError, ValueError) as exc:
        raise ThirdPartyExecutorError(
            error_code=ERR_INVALID_RESPONSE,
            reason=f"exit_code 非法: {exc}",
            user_message="第三方响应格式错误",
        ) from exc
    output = response.get("output")
    if output is not None and not isinstance(output, str):
        output = str(output)
    err = response.get("error")
    payload: Dict[str, Any] = {
        "success": success,
        "output": output or "",
        "exit_code": exit_code,
    }
    if err:
        payload["error"] = str(err)
    return payload