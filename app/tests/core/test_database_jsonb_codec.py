# -*- coding:utf-8 -*-
"""
测试 DatabasePool 初始化时注册的 JSONB / JSON codec

验证 asyncpg 连接池创建时挂载了 init 回调，使 JSONB / JSON 列
自动反序列化为 Python 对象（list / dict），避免业务层拿到 JSON 字符串
导致 Pydantic 校验失败。

对应生产代码：app/core/database.py::DatabasePool.initialize 与
DatabasePool._init_connection（2026-07-01 新增）。

测试策略：根 conftest 的 _mock_database_pool（autouse session fixture）
会 patch DatabasePool.initialize 为 AsyncMock，导致直接调用
asyncio.run(DatabasePool.initialize()) 拿到的是 mock 值。本文件
改为：
  1. 直接调用 DatabasePool._init_connection 验证 codec 注册逻辑
  2. 静态分析 database.py 源文件验证 initialize 挂载了 init 回调
"""
import asyncio
import inspect
from pathlib import Path

import pytest

from app.core.database import DatabasePool


def test_init_connection_registers_jsonb_and_json():
    """
    _init_connection 回调应对每个新连接注册 jsonb 与 json 两种 codec。

    Returns:
        None

    Raises:
        AssertionError: 未注册 jsonb / json 中任一 codec 时抛出。
    """

    class _FakeConn:
        def __init__(self):
            self.calls = []

        async def set_type_codec(self, typename, encoder, decoder, schema, format=None):
            self.calls.append({
                "typename": typename,
                "encoder": encoder,
                "decoder": decoder,
                "schema": schema,
                "format": format,
            })

    async def _run():
        fake = _FakeConn()
        await DatabasePool._init_connection(fake)
        names = [c["typename"] for c in fake.calls]
        assert "jsonb" in names
        assert "json" in names

        for c in fake.calls:
            assert c["schema"] == "pg_catalog"
            assert callable(c["encoder"])
            assert callable(c["decoder"])
            # 2026-07-15:必须显式 format='text',asyncpg 默认 binary 无法被 json.loads 解码
            assert c["format"] == "text", (
                f"codec {c['typename']} 必须显式 format='text' 以便 json.loads 解码"
            )

    asyncio.run(_run())


def test_initialize_source_passes_init_callback():
    """
    静态分析 database.py 源文件，验证 initialize 源码中调用
    asyncpg.create_pool 时传入了 init=cls._init_connection。

    Returns:
        None

    Raises:
        AssertionError: initialize 源码未挂 init 回调时抛出。
    """
    src_path = Path(DatabasePool.__module__.replace(".", "/") + ".py")
    src_file = Path(__file__).resolve().parents[2] / "core" / "database.py"
    text = src_file.read_text(encoding="utf-8")

    assert "def _init_connection" in text, "必须定义 _init_connection 方法"
    assert "set_type_codec" in text, "_init_connection 必须调用 set_type_codec"
    assert "'jsonb'" in text, "必须注册 jsonb codec"
    assert "'json'" in text, "必须注册 json codec"
    assert "json.dumps" in text and "json.loads" in text, "codec 必须用 json.dumps/loads 编解码"

    init_block_start = text.find("async def initialize")
    assert init_block_start >= 0, "必须存在 initialize 方法"
    init_block = text[init_block_start:]
    assert "init=cls._init_connection" in init_block, (
        "initialize() 必须向 asyncpg.create_pool 传入 init=cls._init_connection"
    )