#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
项目元数据两级缓存模块

提供基于 PostgreSQL 的项目存储和两级缓存（内存 + 数据库）。
当 AUTH_STORAGE_MODE=postgres 时启用数据库模式。

表结构（projects）：
    id          SERIAL PRIMARY KEY
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE
    name        VARCHAR(200) NOT NULL
    uuid        VARCHAR(64)  UNIQUE NOT NULL    -- 项目独立唯一标识
    created_at  TIMESTAMP    DEFAULT NOW()
    updated_at  TIMESTAMP    DEFAULT NOW()

表结构通过 @register_schema 装饰器自动注册，启动时统一初始化。

Date: 2026-06-30
Author: AI Assistant
"""
import threading
import uuid as uuid_module
from datetime import datetime
from typing import Optional, Dict, List

from app.core.database import DatabasePool, register_schema


@register_schema
async def init_project_schema():
    """项目表结构初始化

    创建 projects 表（如果不存在），含 user_id 外键约束与 uuid 唯一约束。
    同步给所有 projects 相关字段添加防御性补齐语句。
    """
    await DatabasePool.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id          SERIAL PRIMARY KEY,
            user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name        VARCHAR(200) NOT NULL,
            uuid        VARCHAR(64)  UNIQUE NOT NULL,
            created_at  TIMESTAMP    DEFAULT NOW(),
            updated_at  TIMESTAMP    DEFAULT NOW()
        )
    """)
    await DatabasePool.execute("""
        CREATE INDEX IF NOT EXISTS idx_projects_user_id ON projects(user_id)
    """)
    await DatabasePool.execute("""
        ALTER TABLE projects ADD COLUMN IF NOT EXISTS relative_path VARCHAR(500)
    """)


class ProjectDB:
    """项目元数据两级缓存管理器

    参照 SessionDB 的双写模式：
    - 写入：双向写（内存 + 数据库）
    - 读取：先内存，miss 时查数据库并回填
    - 启动时：从数据库加载所有项目到内存
    """

    _memory_cache: Dict[int, dict] = {}
    _lock = threading.Lock()
    _initialized: bool = False

    @classmethod
    def is_enabled(cls) -> bool:
        """检查是否启用数据库模式

        Returns:
            bool: AUTH_STORAGE_MODE=postgres 时返回 True
        """
        return DatabasePool.is_enabled()

    @classmethod
    async def initialize(cls) -> None:
        """启动时从数据库加载所有项目到内存

        仅 DB 模式生效；Memory 模式下保持 _initialized=False（不缓存）。
        """
        if not cls.is_enabled() or cls._initialized:
            return
        rows = await DatabasePool.fetch(
            "SELECT id, user_id, name, uuid, relative_path, created_at, updated_at FROM projects"
        )
        with cls._lock:
            for row in rows:
                cls._memory_cache[row['id']] = {
                    'id': row['id'],
                    'user_id': row['user_id'],
                    'name': row['name'],
                    'uuid': row['uuid'],
                    'relative_path': row['relative_path'],
                    'created_at': row['created_at'],
                    'updated_at': row['updated_at'],
                }
        await cls._backfill_missing_relative_paths()
        cls._initialized = True

    @classmethod
    async def create_project(
        cls,
        user_id: int,
        name: str,
        uuid: Optional[str] = None,
        relative_path: Optional[str] = None,
    ) -> Optional[dict]:
        """创建项目（双向写入）

        Args:
            user_id: 创建者用户 ID。
            name: 项目名称（用户输入）。
            uuid: 项目唯一标识；为空时按 UUID v4 自动生成，不再强制等于 session_id。
            relative_path: 项目对应现有文件夹的相对路径；为空时按当前日期自动生成。

        Returns:
            Optional[dict]: 创建成功的项目信息（含 id）；DB 未启用时返回 None。

        Raises:
            ValueError: 缺少必填参数。
        """
        if not user_id or not name:
            raise ValueError("user_id / name 均不可为空")
        # 2026-07-06 修正：项目是独立实体，uuid 不再强制等于 session_id
        project_uuid = uuid or str(uuid_module.uuid4())
        now = datetime.now()
        relative_path = relative_path or f"data/project/{now.year}/{now.month:02d}/{now.day:02d}/{project_uuid}"
        new_id: Optional[int] = None

        # 写入数据库
        if cls.is_enabled():
            row = await DatabasePool.fetchrow(
                """
                INSERT INTO projects (user_id, name, uuid, relative_path, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (uuid) DO NOTHING
                RETURNING id
                """,
                user_id, name, project_uuid, relative_path, now, now,
            )
            if row:
                new_id = row['id']
            else:
                # uuid 已存在，幂等返回已有记录
                existing = await DatabasePool.fetchrow(
                    "SELECT id, user_id, name, uuid, relative_path, created_at, updated_at FROM projects WHERE uuid = $1",
                    project_uuid,
                )
                if existing:
                    return dict(existing)
                # ON CONFLICT DO NOTHING + RETURNING 在某些情况下也允许，这里兜底
                return None
        else:
            # Memory 模式：用 _memory_cache 最大 id + 1
            with cls._lock:
                new_id = (max(cls._memory_cache.keys()) + 1) if cls._memory_cache else 1

        project_data = {
            'id': new_id,
            'user_id': user_id,
            'name': name,
            'uuid': project_uuid,
            'relative_path': relative_path,
            'created_at': now,
            'updated_at': now,
        }

        # 写入内存
        with cls._lock:
            cls._memory_cache[new_id] = project_data

        return project_data

    @classmethod
    async def _backfill_missing_relative_paths(cls) -> None:
        """补齐缺失的 relative_path

        遍历内存缓存，对 relative_path 为空或 None 的记录按 created_at 生成默认路径，
        并在 DB 模式下同步更新数据库。

        Returns:
            None
        """
        need_update: List[tuple] = []

        with cls._lock:
            for project_id, proj in cls._memory_cache.items():
                if not proj.get('relative_path'):
                    created_at = proj.get('created_at') or datetime.now()
                    if isinstance(created_at, str):
                        try:
                            created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                        except ValueError:
                            created_at = datetime.now()
                    backfill_path = f"data/project/{created_at.year}/{created_at.month:02d}/{created_at.day:02d}/{proj['uuid']}"
                    proj['relative_path'] = backfill_path
                    need_update.append((backfill_path, project_id))

        if cls.is_enabled() and need_update:
            for backfill_path, project_id in need_update:
                await DatabasePool.execute(
                    "UPDATE projects SET relative_path = $1 WHERE id = $2",
                    backfill_path, project_id,
                )

    @classmethod
    async def list_user_projects(cls, user_id: int) -> List[dict]:
        """获取用户的所有项目（按 created_at DESC）

        Args:
            user_id: 用户 ID。

        Returns:
            List[dict]: 项目列表，每项含 id、user_id、name、uuid、relative_path、created_at、updated_at。
        """
        if cls.is_enabled():
            rows = await DatabasePool.fetch(
                """
                SELECT id, user_id, name, uuid, relative_path, created_at, updated_at
                FROM projects
                WHERE user_id = $1
                ORDER BY created_at DESC
                """,
                user_id,
            )
            return [dict(row) for row in rows]

        # Memory 模式：从内存过滤
        with cls._lock:
            projects = [
                {**proj, 'created_at': proj.get('created_at')}
                for proj in cls._memory_cache.values()
                if proj.get('user_id') == user_id
            ]
        projects.sort(key=lambda x: x.get('created_at') or datetime.min, reverse=True)
        return projects

    @classmethod
    async def get_project_by_id(
        cls,
        project_id: int,
        user_id: Optional[int] = None,
    ) -> Optional[dict]:
        """按 ID 查项目（可选校验归属）

        Args:
            project_id: 项目主键 ID。
            user_id: 可选，传入时校验项目归属，不匹配返回 None。

        Returns:
            Optional[dict]: 项目信息，未找到或不归属时返回 None。
        """
        if cls.is_enabled():
            row = await DatabasePool.fetchrow(
                """
                SELECT id, user_id, name, uuid, relative_path, created_at, updated_at
                FROM projects
                WHERE id = $1
                """,
                project_id,
            )
            if not row:
                return None
            project_data = dict(row)
        else:
            with cls._lock:
                project_data = cls._memory_cache.get(project_id)
            if not project_data:
                return None
            project_data = dict(project_data)

        if user_id is not None and project_data.get('user_id') != user_id:
            return None
        return project_data

    @classmethod
    async def get_project_by_uuid(cls, uuid: str) -> Optional[dict]:
        """按 uuid 查项目

        Args:
            uuid: 项目 uuid（独立唯一标识）。

        Returns:
            Optional[dict]: 项目信息，未找到返回 None。
        """
        if not uuid:
            return None
        if cls.is_enabled():
            row = await DatabasePool.fetchrow(
                """
                SELECT id, user_id, name, uuid, relative_path, created_at, updated_at
                FROM projects
                WHERE uuid = $1
                """,
                uuid,
            )
            return dict(row) if row else None

        with cls._lock:
            for proj in cls._memory_cache.values():
                if proj.get('uuid') == uuid:
                    return dict(proj)
        return None

    @classmethod
    async def delete_project(cls, project_id: int, user_id: Optional[int] = None) -> bool:
        """删除项目元数据（双向删除：数据库 + 内存缓存）

        Args:
            project_id: 项目主键 ID。
            user_id: 可选，传入时校验项目归属，不匹配则不删除。

        Returns:
            bool: 删除成功返回 True，未找到或无权限返回 False。
        """
        # 先校验归属
        project = await cls.get_project_by_id(project_id, user_id=user_id)
        if not project:
            return False

        # 删除数据库记录
        if cls.is_enabled():
            await DatabasePool.execute(
                "DELETE FROM projects WHERE id = $1",
                project_id,
            )

        # 同步删除内存缓存
        with cls._lock:
            cls._memory_cache.pop(project_id, None)

        return True

    @classmethod
    async def rename_project(
        cls,
        project_id: int,
        new_name: str,
        user_id: Optional[int] = None,
    ) -> Optional[dict]:
        """重命名项目（双向更新：数据库 + 内存缓存）

        Args:
            project_id: 项目主键 ID。
            new_name: 新的项目名称。
            user_id: 可选，传入时校验项目归属，不匹配返回 None。

        Returns:
            Optional[dict]: 更新后的项目信息；参数非法、未找到或无权限返回 None。
        """
        name = (new_name or "").strip()
        if not name or len(name) > 50:
            return None

        # 校验归属
        project = await cls.get_project_by_id(project_id, user_id=user_id)
        if not project:
            return None

        now = datetime.now()

        # 更新数据库
        if cls.is_enabled():
            row = await DatabasePool.fetchrow(
                """
                UPDATE projects
                SET name = $1, updated_at = $2
                WHERE id = $3
                RETURNING id, user_id, name, uuid, relative_path, created_at, updated_at
                """,
                name,
                now,
                project_id,
            )
            updated = dict(row) if row else None
        else:
            updated = dict(project)
            updated['name'] = name
            updated['updated_at'] = now

        # 同步更新内存缓存
        if updated:
            with cls._lock:
                if project_id in cls._memory_cache:
                    cls._memory_cache[project_id]['name'] = name
                    cls._memory_cache[project_id]['updated_at'] = now

        return updated
