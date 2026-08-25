#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
安全认证模块

本模块提供JWT令牌的生成和验证功能。
主要功能包括：
- 生成JWT令牌
- 验证JWT令牌
- 认证中间件
- 白名单管理
- Session 认证中间件

Date: 2026/2/6
Author: 张镒谱
"""
import jwt
import logging
from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse
from app.shared.utils.Session.SessionCache import session_cache

logger = logging.getLogger(__name__)


class JWTAuth:
    """
    JWT认证工具类
    
    提供JWT令牌的生成、验证和中间件功能。
    后续将密钥写入环境变量 ，暂时明文
    """

    def __init__(
        self,
        secret_key: str = "zlnWZlEydbodC0D8oJ_9Pdw3C73rHU23k8PEJfaJlso",
        algorithm: str = "HS256",
        bootstrap_username: Optional[str] = None,
        bootstrap_password: Optional[str] = None,
    ):
        """
        初始化JWT认证工具

        Args:
            secret_key (str): JWT密钥，用于签名和验证令牌
            algorithm (str): JWT算法，默认为HS256
            bootstrap_username: lifespan 阶段注入的默认管理员用户名（memory 模式凭据）。
                2026-08-09 起取代原硬编码 ``"admin"``。
            bootstrap_password: lifespan 阶段注入的默认管理员口令（memory 模式凭据）。
                2026-08-09 起取代原硬编码 ``"123456"``；缺失时 ``verify_credentials`` 在
                memory 模式下抛 ``RuntimeError``（fail-loud，禁止回退）。
        """
        self.secret_key = secret_key
        self.algorithm = algorithm
        self.whitelist: List[str] = []

        # 2026-08-09 新增（等保三级 Task 2）：bootstrap 凭据由 lifespan 注入。
        # 缺省值 None 表示"未配置"，verify_credentials 在 memory 模式 fail-loud。
        self.bootstrap_username = bootstrap_username
        self.bootstrap_password = bootstrap_password
    
    def add_to_whitelist(self, path: str):
        """
        添加路径到白名单
        
        白名单中的路径不需要JWT认证。
        
        Args:
            path (str): 要添加到白名单的路径
        """
        if path not in self.whitelist:
            self.whitelist.append(path)
    
    def is_whitelisted(self, path: str) -> bool:
        """
        检查路径是否在白名单中
        
        Args:
            path (str): 要检查的路径
            
        Returns:
            bool: 如果路径在白名单中返回True，否则返回False
        """
        return path in self.whitelist
    
    async def verify_credentials(self, username: str, password: str) -> bool:
        """验证用户凭据。

        设计（等保三级 Task 2，2026-08-09 改造）：

        - **postgres 模式**：始终走 ``UserDB.verify_credentials``，凭据真相源在 DB；
          bootstrap 注入值不会被使用。
        - **memory 模式**：使用 lifespan 注入的 ``bootstrap_username`` /
          ``bootstrap_password``。两个参数都必填，缺失任一 → ``RuntimeError``
          （fail-loud），禁止回退到任何硬编码默认值。

        Args:
            username: 用户名。
            password: 明文密码。

        Returns:
            bool: 验证成功返回 True，否则返回 False。

        Raises:
            RuntimeError: memory 模式且 bootstrap_username / bootstrap_password
                任一未注入时。
        """
        from app.core.database import DatabasePool

        if DatabasePool.is_enabled():
            from app.shared.utils.auth.user_db import UserDB
            return await UserDB.verify_credentials(username, password)

        # memory 模式：凭据来自 lifespan 注入，缺失必须 fail-loud
        if self.bootstrap_username is None or self.bootstrap_password is None:
            raise RuntimeError(
                "JWTAuth bootstrap credentials not configured; "
                "set AUTH_DEFAULT_ADMIN_USERNAME/AUTH_DEFAULT_ADMIN_PASSWORD"
            )
        return username == self.bootstrap_username and password == self.bootstrap_password
    
    async def generate_token(
        self,
        username: str,
        user_id: Optional[int] = None,
        auth_methods: Optional[List[str]] = None,
    ) -> str:
        """生成 Access Token；payload 显式携带 ``user_id`` 与可选 ``amr`` 字段。

        2026-08-11 等保三级 §1.7 强化：payload 必须包含 ``user_id``，便于
        ``authenticate`` 与审计日志在不依赖额外数据库查询的前提下识别用户唯一标识。

        Args:
            username: 用户名（subject 字段）。
            user_id: 用户唯一 ID（数字主键）。``None`` 时不写入 ``user_id`` 字段（保留
                旧 token 行为，便于过渡期兼容；新调用方必须显式传入）。
            auth_methods: 认证方法标记（``["pwd","totp"]`` / ``["pwd","recovery_code"]``），
                None/空 list 时不写入 ``amr`` 字段（保持旧行为）。

        Returns:
            str: JWT 字符串。

        Raises:
            TypeError: auth_methods 不是 list 时。
            HTTPException: 生成失败时（500）。
        """
        try:
            payload = {
                "username": username,
                "type": "access",
                "exp": datetime.utcnow() + timedelta(minutes=30),
                "iat": datetime.utcnow(),
            }
            if user_id is not None:
                payload["user_id"] = int(user_id)
            if auth_methods:
                if not isinstance(auth_methods, list):
                    raise TypeError(
                        f"auth_methods must be list[str], got {type(auth_methods).__name__}"
                    )
                payload["amr"] = [str(x) for x in auth_methods if x]
            token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
            return token
        except TypeError:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"生成令牌失败: {str(e)}"
            )

    async def generate_refresh_token(
        self,
        username: str,
        user_id: Optional[int] = None,
        expires_delta: Optional[timedelta] = None,
        auth_methods: Optional[List[str]] = None,
    ) -> str:
        """生成 Refresh Token；payload 显式携带 ``user_id`` 与可选 ``amr`` 字段。

        2026-08-11 等保三级 §1.7 强化：``/refresh`` 路径必须能直接从 payload 读取
        ``user_id`` 而无需按 username 再次查询数据库。

        Args:
            username: 用户名。
            user_id: 用户唯一 ID（数字主键）。``None`` 时不写入 ``user_id`` 字段（保留
                旧 token 行为，便于过渡期兼容；新调用方必须显式传入）。
            expires_delta: 可选 TTL（默认 24h）。
            auth_methods: 认证方法标记；与 ``generate_token`` 行为一致。

        Returns:
            str: JWT 字符串。

        Raises:
            TypeError: auth_methods 不是 list 时。
            HTTPException: 生成失败时（500）。
        """
        try:
            payload = {
                "username": username,
                "type": "refresh",
                "exp": datetime.utcnow() + (expires_delta or timedelta(hours=24)),
                "iat": datetime.utcnow(),
            }
            if user_id is not None:
                payload["user_id"] = int(user_id)
            if auth_methods:
                if not isinstance(auth_methods, list):
                    raise TypeError(
                        f"auth_methods must be list[str], got {type(auth_methods).__name__}"
                    )
                payload["amr"] = [str(x) for x in auth_methods if x]
            token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
            return token
        except TypeError:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"生成刷新令牌失败: {str(e)}"
            )

    async def verify_refresh_token(self, token: str) -> dict:
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            if payload.get("type") != "refresh":
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="无效的令牌类型"
                )
            return payload
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh Token 已过期，请重新登录"
            )
        except jwt.InvalidTokenError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="无效的令牌"
            )
    
    async def verify_token(self, token: str) -> dict:
        """
        验证 Access Token；强制 payload.type == "access"。

        2026-08-25 修复：原先仅校验签名与过期，type 字段交由下游
        ``authenticate`` / ``/validate`` 反向拒绝 ``type=="refresh"``，
        存在 type 为 None / 空 / 未知值时静默放行的隐患——本方法与
        ``verify_refresh_token`` 对称：明确 type=access 才放行，
        缺失 / 非 access / refresh 一律 401（fail-secure）。

        Args:
            token (str): 待校验的 JWT 字符串。

        Returns:
            dict: 解码后的 payload（含 type=access）。

        Raises:
            HTTPException 401: 令牌过期、签名无效或 type 字段非 access。
            HTTPException 500: 其他未知异常。
        """
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            # 对称 verify_refresh_token 的 type=refresh 强制校验；
            # 缺失 type / 非 access 一律拒绝（fail-secure）。
            if payload.get("type") != "access":
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="无效的令牌类型",
                )
            return payload
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="令牌已过期"
            )
        except HTTPException:
            # 类型校验抛出的 HTTPException 透传，避免被下方 except Exception 包装为 500
            raise
        except jwt.InvalidTokenError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="无效的令牌"
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"验证令牌失败: {str(e)}"
            )
    
    def extract_access_token(self, request: Request) -> str:
        """
        从请求中提取 Access Token 字符串（不验签）。

        提取顺序与策略：

        1. **Authorization Header (Bearer)** —— 优先；第三方 / 程序化客户端走此路径。
        2. **HttpOnly Cookie 兜底** —— 浏览器主应用场景，Access Token 存 Cookie
           （JS 不可见），只能随请求自动发送。

        若请求携带 ``Authorization`` 头但不是 ``Bearer`` 格式（如 ``Basic``），
        一律拒绝并抛 401，**不静默回退到 Cookie**——防止 Basic 凭据被误识别为有效会话。

        这是 ``authenticate()`` 与 ``/validate`` 等其他需要 Access Token 的入口
        的共享 helper，行为一致即可避免 Cookie 鉴权出现「Basic + Cookie 同时带」
        时静默放行的差异。

        Args:
            request (Request): FastAPI 请求对象。

        Returns:
            str: 提取到的 Access Token 字符串（非空）。

        Raises:
            HTTPException 401: 无 Authorization 头且无 Cookie、或 Authorization 非 Bearer 格式。
        """
        auth_header = request.headers.get("Authorization")

        if auth_header:
            if not auth_header.startswith("Bearer "):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="无效的认证格式",
                )
            return auth_header.split(" ", 1)[1]

        from app.core.config.settings import settings as _settings
        token = request.cookies.get(_settings.auth_cookie.access_token_name)
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="缺少认证信息",
            )
        return token

    async def authenticate(self, request: Request) -> Optional[dict]:
        """
        认证请求

        令牌提取顺序：Authorization Header (Bearer) 优先 → HttpOnly Cookie 兜底。
        浏览器主应用场景下 Access Token 存 HttpOnly Cookie，JS 不可见，
        只能随请求自动发送；第三方/程序化客户端可通过 Authorization Header 传入。

        提取成功后会将认证来源写入 ``request.state.auth_via``（``'bearer'`` / ``'cookie'``），
        供下游中间件（如 CSRF 二次校验）按来源差异化处理。

        从请求中提取并验证JWT令牌，同时查询用户角色信息。

        Args:
            request (Request): FastAPI请求对象

        Returns:
            Optional[dict]: 认证成功返回payload，失败返回None

        Raises:
            HTTPException: 当认证失败时抛出
        """
        token = self.extract_access_token(request)
        auth_via = "bearer" if request.headers.get("Authorization") else "cookie"

        payload = await self.verify_token(token)
        request.state.auth_via = auth_via

        # 2026-08-25 二次防线：verify_token 已强制 type=access；
        # 此处仅作未来回退的安全网。正常情况下不会触发（HTTPException 在 verify_token 内部抛出）。
        if payload.get("type") != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="无效的令牌类型",
            )

        # 将用户信息存储到 request.state，方便后续使用
        username = payload.get("username")
        # 2026-08-11 等保三级 §1.7：优先从 payload 取 user_id（避免每次请求额外查 DB）。
        # 兼容历史 token：旧 token 无 user_id 时回退到按 username 查 DB。
        user_id_from_payload = payload.get("user_id")
        request.state.username = username
        request.state.payload = payload

        # 查询用户角色与最终 user_id（user_id 必须以 DB 为准，避免 token 伪造的极端情况）
        from app.shared.utils.auth.user_db import UserDB
        user = await UserDB.get_user_by_username(username)
        if user:
            request.state.role = user.get('role', 'user')
            # 若 payload 中已有 user_id，保留它（性能更高），但与 DB 不一致时以 DB 为准
            final_user_id = user.get('id')
            request.state.user_id = final_user_id if final_user_id is not None else user_id_from_payload
            # 2026-07-24：allowed_agents 数据源从 users.allowed_agents (JSONB 旧字段)
            # 切换到 user_agent_acl (新表，由「智能体访问」Tab 维护)。
            # admin 不受 ACL 限制，返 [] 让上游 agent_router 走 admin bypass；
            # 普通用户从 agent_permission_service 缓存读 ACL；
            # service 不可用时（lifespan 初始化失败 / db=None）返 [] 走 fail-secure，
            # 不再 fallback 到旧 JSONB 字段（避免历史授权残留导致越权）。
            from app.shared.utils.auth.agent_permission_service import (
                AgentPermissionService,
            )
            role = request.state.role
            if role == 'admin':
                request.state.allowed_agents = []
            else:
                svc = getattr(request.app.state, "agent_permission_service", None)
                if svc is not None:
                    request.state.allowed_agents = sorted(
                        svc.get_user_agent_grants_sync(user.get('id'))
                    )
                else:
                    request.state.allowed_agents = []
        else:
            request.state.role = 'user'
            request.state.user_id = user_id_from_payload
            request.state.allowed_agents = []

        return payload


async def require_admin(request: Request):
    """
    校验当前请求用户是否为 admin 角色

    该函数作为 FastAPI 依赖使用，检查 request.state.role 是否为 'admin'。
    必须在 auth_middleware 之后使用，因为 auth_middleware 负责将 role 写入 request.state。

    Args:
        request: FastAPI 请求对象

    Returns:
        bool: 校验通过返回 True

    Raises:
        HTTPException: 非 admin 用户时返回 403 Forbidden
    """
    role = getattr(request.state, 'role', 'user')
    if role != 'admin':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理员权限"
        )
    return True


async def require_menu_acl(request: Request, menu_id: str):
    """
    要求当前用户的 visible_menus 包含 ``menu_id``（admin role 直接 bypass）。

    该函数作为 FastAPI 依赖使用。机制：

    - role='admin'：直接通过（admin 绕过 ACL）
    - 普通用户：从 ``request.app.state.menu_permission_service`` 调
      ``get_visible_menu_ids(user_id=uid, is_admin=False)``，检查返回值含 ``menu_id``
    - service 不可用（lifespan 未初始化）：raise 503
    - user_id 缺失：raise 401（auth_middleware 应先写入，未写入属配置错误）

    用法（工厂）::

        @router.get('/foo', dependencies=[Depends(require_admin_or_menu_acl('xxx'))])

    Args:
        request: FastAPI Request 对象（依赖注入）
        menu_id: 用户菜单注册表里的 menu_id（一级或二级均可）

    Returns:
        None: 校验通过

    Raises:
        HTTPException 401: 用户身份未识别
        HTTPException 403: 普通用户 ACL 未授权 menu_id
        HTTPException 503: menu_permission_service 不可用（lifespan 未启动）

    Date: 2026-07-23 (ACL 双重门改造)
    """
    role = getattr(request.state, 'role', 'user')
    if role == 'admin':
        return

    user_id = getattr(request.state, 'user_id', None)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户身份未识别",
        )

    svc = getattr(request.app.state, 'menu_permission_service', None)
    if svc is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="menu_permission_service 未初始化（lifespan 未启动）",
        )

    visible = await svc.get_visible_menu_ids(user_id=user_id, is_admin=False)
    if menu_id not in visible:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"权限不足，需要菜单 {menu_id} 授权",
        )


def require_admin_or_menu_acl(menu_id: str):
    """
    组合 FastAPI 依赖：admin 角色直接放行；其他用户要求 ACL 含 ``menu_id``。

    这是双重门：原 ``require_admin`` 行为不变（admin 不写 ACL 也能调），同时
    普通用户 ACL 授权后也能调。

    用于后端 API 端点（如 task-schedules、email server-config）实现：
    - admin：原硬守卫不修改，全功能可用
    - 普通用户：ACL 授权 → 该菜单的 API 端点可访问
    - 普通用户未授权：被 ``require_menu_acl`` 拦截 → 403

    用法::

        from app.shared.utils.auth.Safety import require_admin_or_menu_acl

        @router.get('/foo', dependencies=[Depends(require_admin_or_menu_acl('foo'))])
        async def foo(): ...

    Args:
        menu_id: 菜单 id（与 MENU_CATALOG 注册表 / user_menu_acl.menu_id 对齐）

    Returns:
        FastAPI Depends 工厂函数
    """
    async def _dep(request: Request):
        await require_menu_acl(request, menu_id)

    return _dep


async def auth_middleware(request: Request, call_next):
    path = request.url.path
    print(f"[诊断-auth_middleware] 进入, path={path}")
    
    # 检查路径是否在白名单中
    if jwt_auth.is_whitelisted(path):
        print(f"[诊断-auth_middleware] 路径在白名单中, 跳过验证")
        return await call_next(request)
    
    # 非 API 路径（Vite HMR、静态资源等）跳过 JWT 验证
    if not path.startswith("/api/"):
        print(f"[诊断-auth_middleware] path={path} 非 API 路径, 跳过验证")
        return await call_next(request)
    
    try:
        # 验证JWT令牌
        print(f"[诊断-auth_middleware] 开始验证JWT令牌")
        await jwt_auth.authenticate(request)
        print(f"[诊断-auth_middleware] JWT验证成功, username={getattr(request.state, 'username', None)}")
    except Exception as e:
        import traceback
        print(f"[诊断-auth_middleware] path={path}, 认证异常: {e}")
        print(f"[诊断-auth_middleware] 堆栈: {traceback.format_exc()}")
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": str(e)}
        )

    # CSRF 纵深防御：Cookie 鉴权的写请求必须携带 X-Requested-With 自定义头。
    # 跨站表单/简单请求无法附加自定义头（受 CORS 非简单请求预检限制），
    # 因此恶意站点无法伪造带 Cookie 的写请求；SameSite=Strict 为主防线，
    # 此为二次防线。Bearer 鉴权天然免疫 CSRF（攻击者无法读取 Header），豁免。
    if (
        getattr(request.state, "auth_via", None) == "cookie"
        and request.method not in ("GET", "HEAD", "OPTIONS")
        and request.headers.get("X-Requested-With") != "XMLHttpRequest"
    ):
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": "缺少 CSRF 防护请求头"},
        )

    # 认证通过后，让路由自身的异常正常向上抛出，避免被包装为 401
    return await call_next(request)


async def session_auth_middleware(request: Request, call_next):
    path = request.url.path

    # 白名单路径（无需 Access Token）也无需 Session 验证
    if jwt_auth.is_whitelisted(path):
        return await call_next(request)

    # 检查是否在 Session 白名单路径中（这些路径不需要 Session 验证）
    for prefix in SESSION_WHITELIST_PREFIXES:
        if path.startswith(prefix):
            return await call_next(request)

    # 检查是否需要 Session 验证
    needs_session = False

    # 按前缀匹配
    for prefix in SESSION_REQUIRED_PREFIXES:
        if path.startswith(prefix):
            needs_session = True
            break

    # 匹配 /api/session/{session_id}/ 模式（需要 session 验证的路径）
    if not needs_session and path.startswith("/api/session/"):
        # 排除白名单中的 /api/session/create, /api/session/list, /api/session/delete
        # 格式: /api/session/{session_id}/detail, /api/session/{session_id}/messages 等
        path_segments = path.split("/")
        # path_segments = ['', 'api', 'session', '{session_id}', 'action', ...]
        if len(path_segments) >= 5 and path_segments[4]:
            needs_session = True

    if not needs_session:
        # 不需要 Session 验证的路径直接放行
        # username 由 auth_middleware（外层中间件）设置，此处无需重复检查
        return await call_next(request)

    # 需要 Session 验证时才检查用户认证信息
    username = getattr(request.state, "username", None)
    if not username:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": "缺少用户认证信息"}
        )

    # 需要 Session 验证：检查 X-Session-ID
    session_id = request.headers.get("X-Session-ID")
    if not session_id:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": "缺少 X-Session-ID 请求头"}
        )

    # 验证 session_id 是否属于该用户
    is_valid = await session_cache.verify_session(session_id, username)

    if not is_valid:
        # 2026-08-17 新增：运维控制台智能检测窗口的合成 session_id
        # (ops-detect:{server_id}:{ts}) 由 OpsDetectChatWindow 实时生成，
        # 不进入 sessions 表。verify 失败时若 session_id 以 ops-detect: 开头
        # 且路径在 /api/agent/ 前缀下，自动建行并归属当前用户后放行：
        #   - 等保隔离不破：行归属请求用户，他人猜中 ID 也因 username 不匹配仍 401；
        #   - 不污染主侧边栏：SessionDB.get_user_sessions 过滤该前缀；
        #   - 仅作用于 /api/agent/：避免文件路由自动建行产生孤儿会话。
        if (
            path.startswith("/api/agent/")
            and session_id.startswith("ops-detect:")
            and username
        ):
            user_id = getattr(request.state, "user_id", None) or 0
            try:
                await session_cache.add_session(
                    session_id, username, user_id, project_id=None
                )
                logger.info(
                    f"[session_auth_middleware] 自动供给 ops-detect 会话: "
                    f"session_id={session_id}, username={username}"
                )
            except Exception as e:
                logger.warning(
                    f"[session_auth_middleware] 自动供给 ops-detect 失败: {e}"
                )
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={"detail": "无权访问该会话"}
                )
        else:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "无权访问该会话"}
            )

    request.state.session_id = session_id

    # 2026-06-30 新增：注入会话关联的项目 ID，供上传路由/工具层做项目目录路由
    #   * session_cache.get_session 返回的 dict 已包含 project_id 字段（可能为 None）
    try:
        session_data = await session_cache.get_session(session_id)
        request.state.project_id = session_data.get('project_id') if session_data else None
    except Exception as e:
        logger.warning(f"[session_auth_middleware] 注入 project_id 失败: {e}")
        request.state.project_id = None

    return await call_next(request)


# 不需要 Session 验证的路径前缀（仅需 Access Token）
SESSION_WHITELIST_PREFIXES = [
    "/api/auth",
    "/api/users",
    "/api/session/create",
    "/api/session/list",
    "/api/session/delete",
    "/api/session/admin",
    # 2026-07-XX 新增：/api/agent/list 不依赖 session 隔离，仅读 allowed_agents（来自 JWT），
    # 与 /api/session/list、/api/project/list 语义一致。前端按需建 session 后首次进入页面
    # localStorage.session_id 为空，不发 X-Session-ID 也能访问。
    # 注意：/api/agent/chat 仍命中 SESSION_REQUIRED_PREFIXES（/api/agent/）保留校验。
    "/api/agent/list",
    # 2026-07-17 新增：/api/core/upload-config 是前端 onMounted 拉取的只读配置
    # （返回 max_file_size_mb / parser_enabled），无任何写副作用，与 /api/agent/list
    # 语义一致。不放行整个 /api/core 前缀（避免误伤 /api/core/uploadfile、
    # /api/core/merge-chunks 等真正需要 session 隔离的写接口）。
    "/api/core/upload-config",
]

# 需要 Session 验证的路径前缀
SESSION_REQUIRED_PREFIXES = [
    "/api/files/",
    "/api/agent/",
    "/api/core",
    "/api/map",
    "/api/contract",
]

# 创建全局JWT认证实例
jwt_auth = JWTAuth()
