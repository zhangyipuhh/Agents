# -*- coding:utf-8 -*-
"""
test_feishu_drive_client - FeishuDriveClient 单元测试
"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from app.shared.tools.skills.feishu.FeishuDriveClient import (
    FeishuDriveClient,
    _file_to_dict,
)


def _make_lark_client():
    import lark_oapi as lark
    return lark.Client.builder().app_id("a").app_secret("s").build()


# =============================================================================
# list_files
# =============================================================================


def test_drive_list_files_with_folder_token():
    """folder_token 显式传入 → SDK 收到对应字段。"""
    client = _make_lark_client()
    drive = FeishuDriveClient(client)
    mock_response = MagicMock()
    mock_response.success.return_value = True
    file1 = {"token": "f1", "name": "report.docx", "type": "docx", "url": "..."}
    file2 = {"token": "f2", "name": "data.xlsx", "type": "sheet", "url": "..."}
    mock_response.data.files = [file1, file2]
    client.drive.v1.file.list.return_value = mock_response

    resp = asyncio.run(drive.list_files(folder_token="fld_root"))
    assert resp["success"] is True
    assert len(resp["files"]) == 2
    assert resp["files"][0]["name"] == "report.docx"

    req = client.drive.v1.file.list.call_args[0][0]
    assert req._folder_token == "fld_root"


def test_drive_list_files_root_folder_no_token():
    """folder_token=None → SDK 收到 None（不影响调用）。"""
    client = _make_lark_client()
    drive = FeishuDriveClient(client)
    mock_response = MagicMock()
    mock_response.success.return_value = True
    mock_response.data.files = []
    client.drive.v1.file.list.return_value = mock_response

    resp = asyncio.run(drive.list_files(folder_token=None))
    assert resp["success"] is True
    assert resp["files"] == []


def test_drive_list_files_resolve_folder_token_none_returns_root():
    """反向用例：folder_token=None 不抛错，视为列根目录。"""
    client = _make_lark_client()
    drive = FeishuDriveClient(client)
    mock_response = MagicMock()
    mock_response.success.return_value = True
    mock_response.data.files = [{"token": "f_root_1", "name": "root.docx"}]
    client.drive.v1.file.list.return_value = mock_response

    resp = asyncio.run(drive.list_files())
    assert resp["success"] is True
    # SDK 调用透传：builder() 阶段没设置 folder_token → req._folder_token 应为 None
    req = client.drive.v1.file.list.call_args[0][0]
    assert req._folder_token is None


def test_drive_list_files_api_failure_returns_error():
    client = _make_lark_client()
    drive = FeishuDriveClient(client)
    mock_response = MagicMock()
    mock_response.success.return_value = False
    mock_response.code = 403
    mock_response.msg = "no access"
    client.drive.v1.file.list.return_value = mock_response

    resp = asyncio.run(drive.list_files())
    assert resp["success"] is False
    assert resp["code"] == 403


def test_drive_list_files_exception_caught():
    client = _make_lark_client()
    drive = FeishuDriveClient(client)
    client.drive.v1.file.list.side_effect = RuntimeError("dns error")

    resp = asyncio.run(drive.list_files())
    assert resp["success"] is False
    assert "dns error" in resp["error"]


# =============================================================================
# _file_to_dict
# =============================================================================


def test_file_to_dict_passthrough_when_dict():
    """输入已是 dict → 原样返回。"""
    d = {"token": "f1", "name": "x"}
    assert _file_to_dict(d) == d


def test_file_to_dict_converts_object_to_dict():
    """输入是对象（MagicMock）→ 通过 getattr 取已知字段。"""
    obj = MagicMock()
    obj.token = "f_001"
    obj.name = "report.docx"
    obj.type = "docx"
    obj.url = "https://..."
    obj.parent_token = "fld_1"
    obj.created_time = 1234567890
    obj.modified_time = 1234567900
    obj.owner_id = "ou_owner"

    out = _file_to_dict(obj)
    assert out["token"] == "f_001"
    assert out["name"] == "report.docx"
    assert out["type"] == "docx"
    assert out["parent_token"] == "fld_1"
    assert out["created_time"] == 1234567890