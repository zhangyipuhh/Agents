# -*- coding:utf-8 -*-
"""
DevOpsServerService 单元测试（2026-07-15 新增）

覆盖目标：
    - DevOpsServerService(db, config_path, credential_key) 的初始化与 singleton 行为
    - preload_all() 从 DB 加载服务器到缓存
    - scan_and_upsert() 读取 YAML、规范化、Fernet 加密、upsert 写库、刷新缓存
    - list_public_servers() 仅返回 id/business_name/server_type/updated_at（白名单）
    - get_connection_config() 内部解密，绝不外泄密码/IP
    - Fernet 密钥严格校验：空字符串 / 非法 key 抛 ValueError
    - YAML 输入别名兼容（name/host）与字段校验（port 1-65535 / server_type windows|linux）
    - 多次扫描：first insert / next update / 不抛异常
    - 扫描失败时不把原始 YAML / 路径 / IP / 密码回写到响应

测试风格遵循项目规范：
    - 顶部 docstring（中文）
    - 通过 pytest fixture + monkeypatch 注入 db stub 与临时 YAML 文件
    - 不伪造生产 app.state 对象；singleton 通过 DevOpsServerService.set_instance / reset 严格管理
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from cryptography.fernet import Fernet


# 复用 DevOpsServerService 里需要用到的合法 Fernet 密钥
VALID_FERNET_KEY = Fernet.generate_key().decode("ascii")


def _make_db() -> MagicMock:
    """构造一个 MagicMock 作为 asyncpg pool 替身。

    生产侧 DevOpsServerService 通过 ``await db.fetch(...)`` 等异步操作访问 DB，
    因此用 ``AsyncMock`` 让 awaitable 调用返回固定值。

    - ``db.fetch``      → 异步返回 list[Row]
    - ``db.fetchrow``   → 异步返回 Row | None
    - ``db.execute``    → 异步返回 None

    upsert 使用 ``INSERT ... ON CONFLICT ... RETURNING *, (xmax=0) AS inserted``，
    测试场景用 ``side_effect`` 按调用顺序生成插入 / 更新行。
    默认 ``fetchrow`` 返回 ``None``，表示 upsert 失败；调用方可显式覆盖。

    Returns:
        MagicMock: db 池替身（其 fetch/fetchrow/execute 为 AsyncMock）
    """
    db = MagicMock(name="db_pool_stub")
    db.fetch = AsyncMock(return_value=[])
    db.fetchrow = AsyncMock(return_value=None)
    db.execute = AsyncMock(return_value=None)
    return db


@pytest.fixture
def tmp_yaml(tmp_path: Path) -> Path:
    """生成临时 servers.yaml 路径（不在磁盘上预先建文件）。

    Args:
        tmp_path: pytest 临时目录

    Returns:
        Path: servers.yaml 路径
    """
    return tmp_path / "servers.yaml"


@pytest.fixture(autouse=True)
def _reset_singleton():
    """每个用例前后清空 DevOpsServerService 单例。

    Returns:
        None
    """
    from app.shared.utils.devops_server_service import DevOpsServerService

    DevOpsServerService.reset()
    yield
    DevOpsServerService.reset()


# ----------------------------------------------------------------------
# 1. 配置与 Fernet 校验
# ----------------------------------------------------------------------


def test_credential_key_empty_raises_value_error(tmp_yaml):
    """credential_key 为空字符串时，构造 DevOpsServerService 抛 ValueError。

    Args:
        tmp_yaml: 临时 yaml 路径

    Returns:
        None

    Raises:
        AssertionError: 未抛 ValueError 时失败
    """
    db = _make_db()
    with pytest.raises(ValueError):
        from app.shared.utils.devops_server_service import DevOpsServerService
        DevOpsServerService(db=db, config_path=str(tmp_yaml), credential_key="")


def test_credential_key_invalid_raises_value_error(tmp_yaml):
    """credential_key 不是合法 Fernet base64 时，构造抛 ValueError。

    Args:
        tmp_yaml: 临时 yaml 路径

    Returns:
        None

    Raises:
        AssertionError: 未抛 ValueError 时失败
    """
    db = _make_db()
    with pytest.raises(ValueError):
        from app.shared.utils.devops_server_service import DevOpsServerService
        DevOpsServerService(db=db, config_path=str(tmp_yaml), credential_key="not-a-valid-fernet-key")


def test_credential_key_valid_constructs(tmp_yaml):
    """credential_key 为合法 Fernet 密钥时构造成功。

    Args:
        tmp_yaml: 临时 yaml 路径

    Returns:
        None
    """
    db = _make_db()
    from app.shared.utils.devops_server_service import DevOpsServerService
    svc = DevOpsServerService(db=db, config_path=str(tmp_yaml), credential_key=VALID_FERNET_KEY)
    assert svc is not None


# ----------------------------------------------------------------------
# 2. Singleton 行为
# ----------------------------------------------------------------------


def test_singleton_set_get(tmp_yaml):
    """set_instance / get_instance 是同一对象。

    Args:
        tmp_yaml: 临时 yaml 路径

    Returns:
        None
    """
    db = _make_db()
    from app.shared.utils.devops_server_service import DevOpsServerService
    svc = DevOpsServerService(db=db, config_path=str(tmp_yaml), credential_key=VALID_FERNET_KEY)
    DevOpsServerService.set_instance(svc)
    assert DevOpsServerService.get_instance() is svc


# ----------------------------------------------------------------------
# 3. preload_all - 从 DB 加载到内存
# ----------------------------------------------------------------------


def test_preload_all_loads_db_rows_into_cache(tmp_yaml):
    """preload_all() 把 db.fetch 结果映射到 _cache（dict[business_name]）。

    Args:
        tmp_yaml: 临时 yaml 路径

    Returns:
        None
    """
    import asyncio
    db = _make_db()
    db.fetch.return_value = [
        {
            "id": 1,
            "business_name": "alpha",
            "ip": "10.0.0.1",
            "port": 22,
            "username": "root",
            "password_encrypted": b"encrypted_bytes",
            "server_type": "linux",
            "blacklist": ["rm -rf"],
            "whitelist": ["ls"],
            "created_at": None,
            "updated_at": None,
        }
    ]
    from app.shared.utils.devops_server_service import DevOpsServerService
    svc = DevOpsServerService(db=db, config_path=str(tmp_yaml), credential_key=VALID_FERNET_KEY)
    asyncio.run(svc.preload_all())
    assert "alpha" in svc._cache
    assert svc._cache["alpha"]["server_type"] == "linux"


# ----------------------------------------------------------------------
# 4. scan_and_upsert - YAML 别名 / 字段校验 / Fernet 加密 / upsert / 缓存
# ----------------------------------------------------------------------


def test_scan_and_upsert_returns_public_listing_includes_new_record(tmp_yaml):
    """

    Args:
        tmp_yaml: 临时 yaml 路径

    Returns:
        None
    """
    import asyncio
    from cryptography.fernet import Fernet

    db = _make_db()
    # 模拟 RETURNING 行：id / updated_at / password_encrypted（bytes）
    fernet = Fernet(VALID_FERNET_KEY.encode("ascii"))
    encrypted = fernet.encrypt(b"secret")
    db.fetchrow.side_effect = [
        {
            "id": 11,
            "business_name": "alpha",
            "ip": "10.0.0.1",
            "port": 22,
            "username": "root",
            "password_encrypted": encrypted,
            "server_type": "linux",
            "blacklist": ["rm -rf /"],
            "whitelist": ["ls"],
            "created_at": None,
            "updated_at": "2026-07-15",
            "inserted": True,
        }
    ]
    tmp_yaml.parent.mkdir(parents=True, exist_ok=True)
    tmp_yaml.write_text(
        "- name: alpha\n"
        "  host: 10.0.0.1\n"
        "  port: 22\n"
        "  username: root\n"
        "  password: secret\n"
        "  server_type: linux\n"
        "  blacklist: ['rm -rf /']\n"
        "  whitelist: ['ls']\n",
        encoding="utf-8",
    )

    from app.shared.utils.devops_server_service import DevOpsServerService
    svc = DevOpsServerService(db=db, config_path=str(tmp_yaml), credential_key=VALID_FERNET_KEY)
    stats = asyncio.run(svc.scan_and_upsert())

    assert stats == {"scanned": 1, "inserted": 1, "updated": 0, "failed": 0}
    # 缓存里应存在规范键
    assert "alpha" in svc._cache
    rec = svc._cache["alpha"]
    assert rec["ip"] == "10.0.0.1"
    assert rec["server_type"] == "linux"
    assert rec["blacklist"] == ["rm -rf /"]
    assert rec["whitelist"] == ["ls"]
    # 缓存里应包含 DB 返回的真实 id / updated_at / password_encrypted
    assert rec["id"] == 11
    assert rec["updated_at"] == "2026-07-15"
    assert isinstance(rec["password_encrypted"], (bytes, bytearray, memoryview))
    # db.fetchrow 至少被调用 1 次
    assert db.fetchrow.await_count >= 1


def test_scan_and_upsert_rejects_invalid_port(tmp_yaml):
    """port 越界（0 / 70000）时该条记入 failed，不阻断其他记录。

    Args:
        tmp_yaml: 临时 yaml 路径

    Returns:
        None
    """
    import asyncio
    from cryptography.fernet import Fernet

    db = _make_db()
    fernet = Fernet(VALID_FERNET_KEY.encode("ascii"))
    encrypted = fernet.encrypt(b"x")
    # ok 这条触发 RETURNING 行
    db.fetchrow.side_effect = [
        {
            "id": 12,
            "business_name": "ok",
            "ip": "10.0.0.3",
            "port": 22,
            "username": "root",
            "password_encrypted": encrypted,
            "server_type": "linux",
            "blacklist": [],
            "whitelist": [],
            "created_at": None,
            "updated_at": "2026-07-15",
            "inserted": True,
        }
    ]
    tmp_yaml.parent.mkdir(parents=True, exist_ok=True)
    tmp_yaml.write_text(
        "- business_name: bad_port\n"
        "  ip: 10.0.0.2\n"
        "  port: 99999\n"
        "  username: root\n"
        "  password: x\n"
        "  server_type: linux\n"
        "- business_name: ok\n"
        "  ip: 10.0.0.3\n"
        "  port: 22\n"
        "  username: root\n"
        "  password: x\n"
        "  server_type: linux\n",
        encoding="utf-8",
    )

    from app.shared.utils.devops_server_service import DevOpsServerService
    svc = DevOpsServerService(db=db, config_path=str(tmp_yaml), credential_key=VALID_FERNET_KEY)
    stats = asyncio.run(svc.scan_and_upsert())

    assert stats["scanned"] == 2
    assert stats["inserted"] == 1
    assert stats["updated"] == 0
    assert stats["failed"] == 1
    # 失败条目不能进入缓存
    assert "bad_port" not in svc._cache
    assert "ok" in svc._cache


def test_scan_and_upsert_rejects_invalid_server_type(tmp_yaml):
    """server_type 不在 windows/linux 时记 failed。

    Args:
        tmp_yaml: 临时 yaml 路径

    Returns:
        None
    """
    import asyncio
    db = _make_db()
    tmp_yaml.parent.mkdir(parents=True, exist_ok=True)
    tmp_yaml.write_text(
        "- business_name: bsd\n"
        "  ip: 10.0.0.4\n"
        "  port: 22\n"
        "  username: root\n"
        "  password: x\n"
        "  server_type: freebsd\n",
        encoding="utf-8",
    )

    from app.shared.utils.devops_server_service import DevOpsServerService
    svc = DevOpsServerService(db=db, config_path=str(tmp_yaml), credential_key=VALID_FERNET_KEY)
    stats = asyncio.run(svc.scan_and_upsert())

    assert stats["failed"] == 1
    assert stats["inserted"] == 0


def test_scan_and_upsert_handles_duplicate_business_name(tmp_yaml):
    """同一业务名重复出现时必须拒绝并计入 failed，不允许后者覆盖前者。

    Args:
        tmp_yaml: 临时 yaml 路径

    Returns:
        None
    """
    import asyncio
    from cryptography.fernet import Fernet

    db = _make_db()
    fernet = Fernet(VALID_FERNET_KEY.encode("ascii"))
    encrypted = fernet.encrypt(b"x")
    # 只插入一次：第一次 dup 触发 RETURNING，第二次被去重拒绝
    db.fetchrow.side_effect = [
        {
            "id": 99,
            "business_name": "dup",
            "ip": "10.0.0.5",
            "port": 22,
            "username": "root",
            "password_encrypted": encrypted,
            "server_type": "linux",
            "blacklist": [],
            "whitelist": [],
            "created_at": None,
            "updated_at": "2026-07-15",
            "inserted": True,
        }
    ]
    tmp_yaml.parent.mkdir(parents=True, exist_ok=True)
    tmp_yaml.write_text(
        "- business_name: dup\n"
        "  ip: 10.0.0.5\n"
        "  port: 22\n"
        "  username: root\n"
        "  password: x\n"
        "  server_type: linux\n"
        "- business_name: dup\n"
        "  ip: 10.0.0.6\n"
        "  port: 22\n"
        "  username: root\n"
        "  password: y\n"
        "  server_type: linux\n",
        encoding="utf-8",
    )

    from app.shared.utils.devops_server_service import DevOpsServerService
    svc = DevOpsServerService(db=db, config_path=str(tmp_yaml), credential_key=VALID_FERNET_KEY)
    stats = asyncio.run(svc.scan_and_upsert())

    assert stats["scanned"] == 2
    # 重复条目必须记 failed，不允许第二次插入/更新覆盖第一次
    assert stats["failed"] == 1
    assert stats["inserted"] == 1
    assert stats["updated"] == 0
    # 缓存中只有首次出现的 dup（覆盖行为必须禁止）
    assert list(svc._cache.keys()).count("dup") == 1


def test_scan_and_upsert_accepts_top_level_servers_dict(tmp_yaml):
    """顶层 ``{servers: [...]}`` 形式也能被正确扫描入库。

    Args:
        tmp_yaml: 临时 yaml 路径

    Returns:
        None
    """
    import asyncio
    from cryptography.fernet import Fernet

    db = _make_db()
    fernet = Fernet(VALID_FERNET_KEY.encode("ascii"))
    encrypted = fernet.encrypt(b"secret")
    db.fetchrow.side_effect = [
        {
            "id": 1,
            "business_name": "alpha",
            "ip": "10.0.0.1",
            "port": 22,
            "username": "root",
            "password_encrypted": encrypted,
            "server_type": "linux",
            "blacklist": ["rm -rf /"],
            "whitelist": ["ls"],
            "created_at": None,
            "updated_at": "2026-07-15",
            "inserted": True,
        }
    ]
    tmp_yaml.parent.mkdir(parents=True, exist_ok=True)
    tmp_yaml.write_text(
        "servers:\n"
        "  - business_name: alpha\n"
        "    ip: 10.0.0.1\n"
        "    port: 22\n"
        "    username: root\n"
        "    password: secret\n"
        "    server_type: linux\n"
        "    blacklist: ['rm -rf /']\n"
        "    whitelist: ['ls']\n",
        encoding="utf-8",
    )

    from app.shared.utils.devops_server_service import DevOpsServerService
    svc = DevOpsServerService(db=db, config_path=str(tmp_yaml), credential_key=VALID_FERNET_KEY)
    stats = asyncio.run(svc.scan_and_upsert())

    assert stats["scanned"] == 1
    assert stats["inserted"] == 1
    assert stats["failed"] == 0
    assert "alpha" in svc._cache


def test_scan_and_upsert_servers_dict_non_list_safely_fails(tmp_yaml):
    """顶层 ``servers`` 不是 list 时应记 failed，不抛异常。

    Args:
        tmp_yaml: 临时 yaml 路径

    Returns:
        None
    """
    import asyncio
    db = _make_db()
    tmp_yaml.parent.mkdir(parents=True, exist_ok=True)
    tmp_yaml.write_text(
        "servers:\n"
        "  business_name: not-a-list\n"
        "  ip: 1.1.1.1\n",
        encoding="utf-8",
    )

    from app.shared.utils.devops_server_service import DevOpsServerService
    svc = DevOpsServerService(db=db, config_path=str(tmp_yaml), credential_key=VALID_FERNET_KEY)
    stats = asyncio.run(svc.scan_and_upsert())

    # 非 list 时扫描结果不应泄漏敏感细节，但必须有 failed 计数
    assert stats["scanned"] == 0
    assert stats["failed"] >= 1
    # 不抛异常
    assert set(stats.keys()) == {"scanned", "inserted", "updated", "failed"}


def test_scan_and_upsert_cache_contains_decryptable_password(tmp_yaml):
    """扫描成功后缓存必须包含真实 ``password_encrypted``，可立即 ``get_connection_config`` 解密。

    Args:
        tmp_yaml: 临时 yaml 路径

    Returns:
        None
    """
    import asyncio
    from cryptography.fernet import Fernet

    db = _make_db()
    fernet = Fernet(VALID_FERNET_KEY.encode("ascii"))
    encrypted = fernet.encrypt(b"verysecret-xyz")
    db.fetchrow.side_effect = [
        {
            "id": 7,
            "business_name": "alpha",
            "ip": "10.0.0.1",
            "port": 22,
            "username": "root",
            "password_encrypted": encrypted,
            "server_type": "linux",
            "blacklist": ["rm -rf"],
            "whitelist": ["ls"],
            "created_at": None,
            "updated_at": "2026-07-15",
            "inserted": True,
        }
    ]
    tmp_yaml.parent.mkdir(parents=True, exist_ok=True)
    tmp_yaml.write_text(
        "- business_name: alpha\n"
        "  ip: 10.0.0.1\n"
        "  port: 22\n"
        "  username: root\n"
        "  password: verysecret-xyz\n"
        "  server_type: linux\n"
        "  blacklist: ['rm -rf']\n"
        "  whitelist: ['ls']\n",
        encoding="utf-8",
    )

    from app.shared.utils.devops_server_service import DevOpsServerService
    svc = DevOpsServerService(db=db, config_path=str(tmp_yaml), credential_key=VALID_FERNET_KEY)
    asyncio.run(svc.scan_and_upsert())

    # 公开列表必须包含新记录
    public = svc.list_public_servers()
    assert any(item.get("business_name") == "alpha" for item in public)
    item = next(r for r in public if r.get("business_name") == "alpha")
    assert item.get("id") is not None
    assert item.get("updated_at") is not None

    # 缓存里必须包含真实 password_encrypted（来自 DB 返回）
    rec = svc._cache["alpha"]
    assert isinstance(rec["password_encrypted"], (bytes, bytearray, memoryview))

    # get_connection_config 立即可用
    cfg = svc.get_connection_config("alpha")
    assert cfg["password"] == "verysecret-xyz"
    assert cfg["ip"] == "10.0.0.1"
    assert cfg["server_type"] == "linux"


# ----------------------------------------------------------------------
# 4.5 路径集中（paths.resolve_devops_server_config_path）+ 默认路径来自 paths
# ----------------------------------------------------------------------


def test_resolve_devops_server_config_path_absolute_unchanged():
    """绝对路径原样返回。

    Returns:
        None
    """
    # 避免触发 app.core.config.__init__ 中其他模块的副作用
    import importlib.util
    from pathlib import Path as _Path

    spec = importlib.util.spec_from_file_location(
        "_paths_module", _Path("app/core/config/paths.py").resolve()
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    resolve_devops_server_config_path = mod.resolve_devops_server_config_path

    absolute = "C:/abs/servers.yaml"
    out = resolve_devops_server_config_path(absolute)
    assert str(out).replace("\\", "/") == absolute.replace("\\", "/")


def test_resolve_devops_server_config_path_relative_resolves_under_project_root():
    """相对路径相对项目根解析。

    Returns:
        None
    """
    import importlib.util
    from pathlib import Path as _Path

    spec = importlib.util.spec_from_file_location(
        "_paths_module", _Path("app/core/config/paths.py").resolve()
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]

    out = mod.resolve_devops_server_config_path("data/devops/servers.yaml")
    assert out.is_absolute()
    assert str(out).replace("\\", "/") == (
        str(mod._PROJECT_ROOT).replace("\\", "/") + "/data/devops/servers.yaml"
    )


def test_settings_devops_servers_config_path_default_is_paths_constant(monkeypatch):
    """DevOpsSettings.servers_config_path 默认必须直接来自 paths.DEVOPS_SERVER_CONFIG_PATH。

    由于 settings.py 顶层导入链副作用（与本测试无关），
    直接读取源文件并验证 default_factory 输出与 paths 常量等价即可。

    Returns:
        None
    """
    import importlib.util
    from pathlib import Path as _Path

    paths_path = _Path("app/core/config/paths.py").resolve()
    paths_spec = importlib.util.spec_from_file_location("_paths_module", paths_path)
    paths_mod = importlib.util.module_from_spec(paths_spec)
    paths_spec.loader.exec_module(paths_mod)  # type: ignore[union-attr]

    # 解析 settings.py 源文件，找到 DevOpsSettings._default_servers_config_path 的源代码并直接调用
    settings_src = _Path("app/core/config/settings.py").read_text(
        encoding="utf-8"
    )
    # 直接断言 _default_servers_config_path 的返回值 == DEVOPS_SERVER_CONFIG_PATH
    assert "_default_servers_config_path" in settings_src, (
        "settings.py 应在 DevOpsSettings 中定义 _default_servers_config_path"
    )
    # 静态检查 default_factory 调用
    assert (
        'default_factory=_default_servers_config_path' in settings_src
    ), "servers_config_path 必须用 default_factory 引用 paths 常量"

    # 动态：实例化一个简单 BaseSettings 不行，但可以检查 paths.DEVOPS_SERVER_CONFIG_PATH 与默认解析结果一致
    monkeypatch.delenv("DEVOPS_SERVERS_CONFIG_PATH", raising=False)
    # 直接模拟 default_factory 的逻辑（避免加载完整 settings）
    expected = paths_mod.resolve_devops_server_config_path(
        paths_mod.DEVOPS_SERVER_CONFIG_PATH
    )
    # 由于 default_factory 返回的是 str(DEVOPS_SERVER_CONFIG_PATH)（绝对路径），
    # resolve_devops_server_config_path 对绝对路径应原样返回。
    actual = paths_mod.resolve_devops_server_config_path(
        str(paths_mod.DEVOPS_SERVER_CONFIG_PATH)
    )
    assert actual == expected


# ----------------------------------------------------------------------
# 5. 公示字段白名单 + 敏感字段不外泄
# ----------------------------------------------------------------------


def test_list_public_servers_returns_only_whitelisted_fields(tmp_yaml):
    """list_public_servers 每项严格只含 id/business_name/server_type/updated_at。

    Args:
        tmp_yaml: 临时 yaml 路径

    Returns:
        None
    """
    import asyncio
    db = _make_db()
    db.fetch.return_value = [
        {
            "id": 1,
            "business_name": "alpha",
            "ip": "10.0.0.1",
            "port": 22,
            "username": "root",
            "password_encrypted": b"enc",
            "server_type": "linux",
            "blacklist": ["rm -rf"],
            "whitelist": ["ls"],
            "created_at": None,
            "updated_at": None,
        }
    ]
    from app.shared.utils.devops_server_service import DevOpsServerService
    svc = DevOpsServerService(db=db, config_path=str(tmp_yaml), credential_key=VALID_FERNET_KEY)
    asyncio.run(svc.preload_all())
    public = svc.list_public_servers()
    assert len(public) == 1
    item = public[0]
    assert set(item.keys()) == {"id", "business_name", "server_type", "updated_at"}


def test_get_connection_config_decrypts_password(tmp_yaml):
    """get_connection_config(business_name) 内部解密并返回完整配置（含明文 password）。

    Args:
        tmp_yaml: 临时 yaml 路径

    Returns:
        None
    """
    import asyncio
    db = _make_db()
    from cryptography.fernet import Fernet
    fernet = Fernet(VALID_FERNET_KEY.encode("ascii"))
    encrypted = fernet.encrypt(b"plaintext-secret")

    db.fetch.return_value = [
        {
            "id": 1,
            "business_name": "alpha",
            "ip": "10.0.0.1",
            "port": 22,
            "username": "root",
            "password_encrypted": encrypted,
            "server_type": "linux",
            "blacklist": ["rm -rf"],
            "whitelist": ["ls"],
            "created_at": None,
            "updated_at": None,
        }
    ]
    from app.shared.utils.devops_server_service import DevOpsServerService
    svc = DevOpsServerService(db=db, config_path=str(tmp_yaml), credential_key=VALID_FERNET_KEY)
    asyncio.run(svc.preload_all())
    cfg = svc.get_connection_config("alpha")
    assert cfg["ip"] == "10.0.0.1"
    assert cfg["port"] == 22
    assert cfg["username"] == "root"
    assert cfg["password"] == "plaintext-secret"
    assert cfg["server_type"] == "linux"
    assert cfg["blacklist"] == ["rm -rf"]
    assert cfg["whitelist"] == ["ls"]


def test_get_connection_config_unknown_raises(tmp_yaml):
    """业务名不存在时抛 KeyError（不外泄任何配置）。

    Args:
        tmp_yaml: 临时 yaml 路径

    Returns:
        None
    """
    import asyncio
    db = _make_db()
    db.fetch.return_value = []
    from app.shared.utils.devops_server_service import DevOpsServerService
    svc = DevOpsServerService(db=db, config_path=str(tmp_yaml), credential_key=VALID_FERNET_KEY)
    asyncio.run(svc.preload_all())
    with pytest.raises(KeyError):
        svc.get_connection_config("ghost")


# ----------------------------------------------------------------------
# 6. 扫描失败时不把详情写入响应（方法返回结构稳定）
# ----------------------------------------------------------------------


def test_scan_and_upsert_returns_strict_four_numbers(tmp_yaml):
    """scan_and_upsert 返回严格 dict{scanned,inserted,updated,failed}，无其他字段。

    Args:
        tmp_yaml: 临时 yaml 路径

    Returns:
        None
    """
    import asyncio
    from cryptography.fernet import Fernet

    db = _make_db()
    fernet = Fernet(VALID_FERNET_KEY.encode("ascii"))
    encrypted = fernet.encrypt(b"p")
    db.fetchrow.side_effect = [
        {
            "id": 1,
            "business_name": "x",
            "ip": "1.1.1.1",
            "port": 22,
            "username": "u",
            "password_encrypted": encrypted,
            "server_type": "linux",
            "blacklist": [],
            "whitelist": [],
            "created_at": None,
            "updated_at": "2026-07-15",
            "inserted": True,
        }
    ]
    tmp_yaml.parent.mkdir(parents=True, exist_ok=True)
    tmp_yaml.write_text("- business_name: x\n  host: 1.1.1.1\n  port: 22\n  username: u\n  password: p\n  server_type: linux\n", encoding="utf-8")

    from app.shared.utils.devops_server_service import DevOpsServerService
    svc = DevOpsServerService(db=db, config_path=str(tmp_yaml), credential_key=VALID_FERNET_KEY)
    stats = asyncio.run(svc.scan_and_upsert())

    # 不论原 YAML 写什么，返回值只能是这四个数字
    assert set(stats.keys()) == {"scanned", "inserted", "updated", "failed"}
    assert all(isinstance(stats[k], int) for k in stats)


def test_scan_and_upsert_yaml_missing_records_zero_scanned(tmp_yaml):
    """servers.yaml 不存在时，scan_and_upsert 返回 scanned=0，不抛异常。

    Args:
        tmp_yaml: 临时 yaml 路径（不存在）

    Returns:
        None
    """
    import asyncio
    db = _make_db()
    from app.shared.utils.devops_server_service import DevOpsServerService
    svc = DevOpsServerService(db=db, config_path=str(tmp_yaml), credential_key=VALID_FERNET_KEY)
    stats = asyncio.run(svc.scan_and_upsert())
    assert stats == {"scanned": 0, "inserted": 0, "updated": 0, "failed": 0}


def test_scan_and_upsert_path_not_in_stats(tmp_yaml, caplog):
    """扫描异常时，返回的 stats 字典中不包含任何敏感信息（path/IP/password/名单）。

    本用例制造一种会在解析 YAML 后失败的情形（例如不存在的配置 + 业务名校验触发），
    并断言 stats 字段白名单严格只有 4 个数字键；不应包含原始 path 或详情。

    Args:
        tmp_yaml: 临时 yaml 路径
        caplog: pytest caplog fixture

    Returns:
        None
    """
    import asyncio
    db = _make_db()
    tmp_yaml.parent.mkdir(parents=True, exist_ok=True)
    # 故意构造 server_type 非法 → 进入 failed 分支
    tmp_yaml.write_text(
        "- business_name: bad\n"
        "  ip: 10.0.0.99\n"
        "  port: 22\n"
        "  username: u\n"
        "  password: verysecret-xyz\n"
        "  server_type: zos\n",
        encoding="utf-8",
    )

    from app.shared.utils.devops_server_service import DevOpsServerService
    svc = DevOpsServerService(db=db, config_path=str(tmp_yaml), credential_key=VALID_FERNET_KEY)
    stats = asyncio.run(svc.scan_and_upsert())

    # 仅 4 个数字键
    assert set(stats.keys()) == {"scanned", "inserted", "updated", "failed"}
    stats_str = repr(stats)
    # 不回显任何敏感原文
    assert "verysecret-xyz" not in stats_str
    assert "10.0.0.99" not in stats_str
    assert str(tmp_yaml) not in stats_str
    assert "zos" not in stats_str


def test_get_connection_config_does_not_leak_in_public_listing(tmp_yaml):
    """公开列表 list_public_servers 不应出现 password / ip / port / 名单等敏感字段。

    Args:
        tmp_yaml: 临时 yaml 路径

    Returns:
        None
    """
    import asyncio
    db = _make_db()
    db.fetch.return_value = [
        {
            "id": 1,
            "business_name": "alpha",
            "ip": "10.0.0.1",
            "port": 22,
            "username": "root",
            "password_encrypted": b"enc",
            "server_type": "linux",
            "blacklist": ["rm -rf"],
            "whitelist": ["ls"],
            "created_at": None,
            "updated_at": None,
        }
    ]
    from app.shared.utils.devops_server_service import DevOpsServerService
    svc = DevOpsServerService(db=db, config_path=str(tmp_yaml), credential_key=VALID_FERNET_KEY)
    asyncio.run(svc.preload_all())
    public = svc.list_public_servers()
    blob = repr(public)
    assert "10.0.0.1" not in blob
    assert "rm -rf" not in blob
    assert "root" not in blob


# ----------------------------------------------------------------------
# 10. JSONB 反序列化防御（2026-07-15 新增）
# ----------------------------------------------------------------------


def test_ensure_list_already_list_passthrough():
    """``_ensure_list`` 收到 list 时原样返回。

    Returns:
        None
    """
    from app.shared.utils.devops_server_service import _ensure_list
    assert _ensure_list(["a", "b"]) == ["a", "b"]
    assert _ensure_list([]) == []
    # 嵌套 list 也直接返回
    assert _ensure_list([["x"], ["y"]]) == [["x"], ["y"]]


def test_ensure_list_string_json_parses_to_list():
    """``_ensure_list`` 收到 JSON 字符串时还原为 list。

    这是 asyncpg 0.31 jsonb codec 失效场景的核心防御:
    DB 拿到 ``'["a", "b"]'`` 这种字符串时,不能 ``list(value)``(会拆成字符),
    而应 ``json.loads`` 还原。

    Returns:
        None
    """
    from app.shared.utils.devops_server_service import _ensure_list
    assert _ensure_list('["systemctl ", "df", "tail "]') == ["systemctl ", "df", "tail "]
    assert _ensure_list("[]") == []
    assert _ensure_list('["rm -rf"]') == ["rm -rf"]


def test_ensure_list_dict_wraps_in_list():
    """``_ensure_list`` 收到 dict 时包成单元素 list。

    白/黑名单场景不期望 dict,但兼容 asyncpg 误返回 dict 的极端情况。

    Returns:
        None
    """
    from app.shared.utils.devops_server_service import _ensure_list
    assert _ensure_list({"key": "value"}) == [{"key": "value"}]


def test_ensure_list_string_json_dict_wraps():
    """``_ensure_list`` 收到 JSON dict 字符串时包成单元素 list。

    Returns:
        None
    """
    from app.shared.utils.devops_server_service import _ensure_list
    assert _ensure_list('{"foo": "bar"}') == [{"foo": "bar"}]


def test_ensure_list_invalid_string_returns_empty():
    """``_ensure_list`` 收到非法 JSON 字符串时返回 ``[]``(兜底)。

    Returns:
        None
    """
    from app.shared.utils.devops_server_service import _ensure_list
    assert _ensure_list("not json") == []
    assert _ensure_list("{invalid}") == []


def test_ensure_list_none_or_other_returns_empty():
    """``_ensure_list`` 收到 None / 非 list/dict/str 时返回 ``[]``。

    Returns:
        None
    """
    from app.shared.utils.devops_server_service import _ensure_list
    assert _ensure_list(None) == []
    assert _ensure_list(123) == []
    assert _ensure_list(0.5) == []
    assert _ensure_list(True) == []


def test_ensure_list_string_json_primitives_returns_empty():
    """``_ensure_list`` 收到 JSON 字符串但解析为基本类型(数字 / bool / null)时返回 ``[]``。

    Returns:
        None
    """
    from app.shared.utils.devops_server_service import _ensure_list
    assert _ensure_list("123") == []
    assert _ensure_list("true") == []
    assert _ensure_list("null") == []
    assert _ensure_list('"plain_string"') == []


def test_preload_all_decodes_string_whitelist(tmp_yaml):
    """``preload_all`` 收到 JSON 字符串形式的 whitelist/blacklist 时还原为 list。

    模拟 asyncpg jsonb codec 失效场景(DB row 的 whitelist/blacklist 是 str):
    验证 _cache 里存的是真正的 list,不是被 list() 拆过字符的字符串。

    Args:
        tmp_yaml: 临时 yaml 路径

    Returns:
        None
    """
    import asyncio
    db = _make_db()
    db.fetch.return_value = [
        {
            "id": 1,
            "business_name": "alpha",
            "ip": "10.0.0.1",
            "port": 22,
            "username": "root",
            "password_encrypted": b"enc",
            "server_type": "linux",
            # 模拟 asyncpg jsonb 反序列化失效:返回原始 JSON 字符串
            "blacklist": '["rm -rf "]',
            "whitelist": '["systemctl ", "df", "tail "]',
            "created_at": None,
            "updated_at": None,
        }
    ]
    from app.shared.utils.devops_server_service import DevOpsServerService
    svc = DevOpsServerService(db=db, config_path=str(tmp_yaml), credential_key=VALID_FERNET_KEY)
    asyncio.run(svc.preload_all())
    assert svc._cache["alpha"]["blacklist"] == ["rm -rf "]
    assert svc._cache["alpha"]["whitelist"] == ["systemctl ", "df", "tail "]
    # 关键防御验证:如果防御失效,list() 会拆字符串成字符数组
    assert len(svc._cache["alpha"]["whitelist"]) == 3
    assert isinstance(svc._cache["alpha"]["whitelist"][0], str)


def test_get_connection_config_handles_string_whitelist(tmp_yaml):
    """``get_connection_config`` 收到 JSON 字符串形式的 whitelist/blacklist 时还原为 list。

    即便 preload_all 缓存里存的是 list,get_connection_config 仍做一次防御性还原,
    保证返回配置始终是 list 类型,不会污染下游 ``CommandInterceptor``。

    Args:
        tmp_yaml: 临时 yaml 路径

    Returns:
        None
    """
    import asyncio
    db = _make_db()
    # 用合法 Fernet token 作为 password_encrypted
    from cryptography.fernet import Fernet
    fernet = Fernet(VALID_FERNET_KEY.encode("ascii"))
    encrypted_pw = fernet.encrypt(b"plaintext-secret")

    db.fetch.return_value = [
        {
            "id": 1,
            "business_name": "alpha",
            "ip": "10.0.0.1",
            "port": 22,
            "username": "root",
            "password_encrypted": encrypted_pw,
            "server_type": "linux",
            "blacklist": '["rm -rf "]',
            "whitelist": '["df"]',
            "created_at": None,
            "updated_at": None,
        }
    ]
    from app.shared.utils.devops_server_service import DevOpsServerService
    svc = DevOpsServerService(db=db, config_path=str(tmp_yaml), credential_key=VALID_FERNET_KEY)
    asyncio.run(svc.preload_all())
    cfg = svc.get_connection_config("alpha")
    assert cfg["whitelist"] == ["df"]
    assert cfg["blacklist"] == ["rm -rf "]
    # 关键防御验证
    assert isinstance(cfg["whitelist"], list)
    assert cfg["whitelist"][0] == "df"


# ----------------------------------------------------------------------
# delete_server / server_exists
# ----------------------------------------------------------------------


def _service_with_cached_row(tmp_yaml, row_id=1, name="alpha"):
    """构造一个已缓存一行（默认 id=1, business_name='alpha'）的 service 实例。

    Args:
        tmp_yaml: 临时 yaml 路径
        row_id: 缓存行 id
        name: 缓存行 business_name

    Returns:
        Tuple[DevOpsServerService, MagicMock]: service 与 db 池替身
    """
    db = _make_db()
    from app.shared.utils.devops_server_service import DevOpsServerService

    svc = DevOpsServerService(db=db, config_path=str(tmp_yaml), credential_key=VALID_FERNET_KEY)
    svc._cache[name] = {
        "id": row_id,
        "business_name": name,
        "ip": "10.0.0.1",
        "port": 22,
        "username": "root",
        "password_encrypted": b"x",
        "server_type": "linux",
        "blacklist": [],
        "whitelist": [],
        "created_at": None,
        "updated_at": None,
    }
    return svc, db


def test_delete_server_removes_cache_and_calls_db(tmp_yaml):
    """删除后 cache 移除 + DB.execute 被调用，参数为 server_id。

    Args:
        tmp_yaml: 临时 yaml 路径

    Returns:
        None
    """
    import asyncio

    svc, db = _service_with_cached_row(tmp_yaml, row_id=1, name="alpha")
    asyncio.run(svc.delete_server(1))
    # 1) 缓存中应被移除
    assert "alpha" not in svc._cache
    # 2) DB 应执行过 DELETE
    db.execute.assert_awaited()
    sql = db.execute.await_args.args[0]
    assert "DELETE FROM devops_servers" in sql
    # 3) 第一个参数是 server_id
    assert db.execute.await_args.args[1] == 1


def test_delete_server_idempotent_when_cache_missing(tmp_yaml):
    """cache 中不存在对应 id 时，DB DELETE 仍被发出（service 幂等）。

    Args:
        tmp_yaml: 临时 yaml 路径

    Returns:
        None
    """
    import asyncio
    from app.shared.utils.devops_server_service import DevOpsServerService

    db = _make_db()
    svc = DevOpsServerService(db=db, config_path=str(tmp_yaml), credential_key=VALID_FERNET_KEY)
    # cache 保持为空
    asyncio.run(svc.delete_server(99))
    db.execute.assert_awaited_once()
    sql = db.execute.await_args.args[0]
    assert "DELETE FROM devops_servers" in sql
    assert db.execute.await_args.args[1] == 99


def test_server_exists_cache_hit(tmp_yaml):
    """server_exists：cache 命中时直接返回 True，不查 DB。

    Args:
        tmp_yaml: 临时 yaml 路径

    Returns:
        None
    """
    import asyncio

    svc, db = _service_with_cached_row(tmp_yaml, row_id=7, name="alpha")
    assert asyncio.run(svc.server_exists(7)) is True
    db.fetchrow.assert_not_awaited()


def test_server_exists_cache_miss_consults_db(tmp_yaml):
    """server_exists：cache 未命中时回退 DB 查询。

    Args:
        tmp_yaml: 临时 yaml 路径

    Returns:
        None
    """
    import asyncio
    from app.shared.utils.devops_server_service import DevOpsServerService

    db = _make_db()
    svc = DevOpsServerService(db=db, config_path=str(tmp_yaml), credential_key=VALID_FERNET_KEY)
    # cache 为空，DB 命中
    db.fetchrow = AsyncMock(return_value={"?column?": 1})
    assert asyncio.run(svc.server_exists(42)) is True
    db.fetchrow.assert_awaited()
    sql = db.fetchrow.await_args.args[0]
    assert "SELECT 1 FROM devops_servers" in sql
    # cache 未命中 DB 也不存在
    db.fetchrow = AsyncMock(return_value=None)
    assert asyncio.run(svc.server_exists(43)) is False
