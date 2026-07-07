# -*- coding:utf-8 -*-
"""
Project 路径管理器测试（2026-07-01 重构）

测试 app/shared/utils/files/project_path_manager.py 的：
  * get_project_upload_dir
  * get_project_tmp_upload_dir
"""

from pathlib import Path

import pytest

from app.core.config import paths
from app.shared.utils.files import project_path_manager as ppm


class TestProjectPathManager:
    """项目路径管理器测试。"""

    @pytest.fixture(autouse=True)
    def _patch_project_root(self, tmp_path, monkeypatch):
        """将项目根目录指向临时路径，避免污染真实数据目录。"""
        monkeypatch.setattr(paths, "_PROJECT_ROOT", str(tmp_path))

    def test_get_project_upload_dir(self, tmp_path):
        """按 relative_path 解析原文件目录。"""
        relative_path = "data/project/2026/07/01/uuid"
        upload_dir = ppm.get_project_upload_dir(relative_path, create=False)
        assert upload_dir == tmp_path / relative_path

    def test_get_project_upload_dir_creates(self, tmp_path):
        """create=True 时创建日期化目录。"""
        relative_path = "data/project/2026/07/01/uuid"
        upload_dir = ppm.get_project_upload_dir(relative_path, create=True)
        assert upload_dir == tmp_path / relative_path
        assert upload_dir.exists()
        assert upload_dir.is_dir()

    def test_get_project_tmp_upload_dir(self, tmp_path):
        """按 relative_path 解析 tmp 目录。"""
        relative_path = "data/project/2026/07/01/uuid"
        tmp_dir = ppm.get_project_tmp_upload_dir(relative_path, create=False)
        assert tmp_dir == tmp_path / "data/tmp/project/2026/07/01/uuid"

    def test_get_project_tmp_upload_dir_creates(self, tmp_path):
        """create=True 时创建日期化 tmp 目录。"""
        relative_path = "data/project/2026/07/01/uuid"
        tmp_dir = ppm.get_project_tmp_upload_dir(relative_path, create=True)
        assert tmp_dir == tmp_path / "data/tmp/project/2026/07/01/uuid"
        assert tmp_dir.exists()
        assert tmp_dir.is_dir()
