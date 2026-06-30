# -*- coding:utf-8 -*-
"""
Project 路径管理器测试（2026-06-30 新增）

测试 app/shared/utils/files/project_path_manager.py 的：
  * get_project_upload_dir
  * get_project_tmp_upload_dir
"""

from pathlib import Path

import pytest

from app.shared.utils.files import project_path_manager as ppm


class TestProjectPathManager:
    """项目路径管理器测试。"""

    def test_get_project_upload_dir_default_uuid(self, tmp_path, monkeypatch):
        """空 uuid 应回退到 'default'。"""
        monkeypatch.setattr(ppm, "_get_project_root", lambda: tmp_path)
        upload_dir = ppm.get_project_upload_dir("", create=False)
        assert upload_dir == tmp_path / "data/project/default"

    def test_get_project_upload_dir_creates(self, tmp_path, monkeypatch):
        """create=True 时应创建目录。"""
        monkeypatch.setattr(ppm, "_get_project_root", lambda: tmp_path)
        upload_dir = ppm.get_project_upload_dir("session-1111", create=True)
        assert upload_dir == tmp_path / "data/project/session-1111"
        assert upload_dir.exists()
        assert upload_dir.is_dir()

    def test_get_project_upload_dir_no_create(self, tmp_path, monkeypatch):
        """create=False 时不创建。"""
        monkeypatch.setattr(ppm, "_get_project_root", lambda: tmp_path)
        upload_dir = ppm.get_project_upload_dir("session-2222", create=False)
        assert upload_dir == tmp_path / "data/project/session-2222"
        assert not upload_dir.exists()

    def test_get_project_tmp_upload_dir(self, tmp_path, monkeypatch):
        """tmp 目录应在 data/tmp/project/ 下。"""
        monkeypatch.setattr(ppm, "_get_project_root", lambda: tmp_path)
        tmp_dir = ppm.get_project_tmp_upload_dir("session-1111", create=True)
        assert tmp_dir == tmp_path / "data/tmp/project/session-1111"
        assert tmp_dir.exists()

    def test_get_project_tmp_upload_dir_default_uuid(self, tmp_path, monkeypatch):
        """空 uuid 的 tmp 目录回退到 'default'。"""
        monkeypatch.setattr(ppm, "_get_project_root", lambda: tmp_path)
        tmp_dir = ppm.get_project_tmp_upload_dir("", create=False)
        assert tmp_dir == tmp_path / "data/tmp/project/default"
