#!/usr/bin/python
# -*- coding:utf-8 -*-
# Date: 2026-03-27
# Author: 张镒谱

import json
import uuid
from pathlib import Path
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional

from ..ZYPAgent import ModelConfig


@dataclass
class Message:
    """
    聊天消息数据类，存储单条消息的完整信息
    """
    id: str
    role: str
    content: str
    tool_calls: Optional[list] = None
    created_at: str = ""

    def __post_init__(self):
        """
        初始化后自动设置创建时间戳，确保每条消息都有时间记录
        """
        if not self.created_at:
            self.created_at = datetime.now().isoformat()

    def to_dict(self) -> dict:
        """
        将Message实例转换为字典，用于JSON序列化存储
        """
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Message":
        """
        从字典数据创建Message实例，支持反序列化操作
        """
        return cls(**data)


@dataclass
class Session:
    """
    聊天会话数据类，存储会话的元数据及消息列表
    """
    id: str
    name: str
    created_at: str
    updated_at: str
    messages: list[Message]
    model_config: dict

    def __post_init__(self):
        """
        初始化后自动处理时间戳和空值，确保数据完整性
        """
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if not self.updated_at:
            self.updated_at = self.created_at
        if self.messages is None:
            self.messages = []
        if self.model_config is None:
            self.model_config = {}

    def to_dict(self) -> dict:
        """
        将Session实例转换为字典，消息列表中的每条消息也序列化为字典
        """
        return {
            "id": self.id,
            "name": self.name,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "messages": [msg.to_dict() if isinstance(msg, Message) else msg for msg in self.messages],
            "model_config": self.model_config,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Session":
        """
        从字典数据创建Session实例，反序列化时将字典转换为Message对象
        """
        messages = [Message.from_dict(m) if isinstance(m, dict) else m for m in data.get("messages", [])]
        return cls(
            id=data["id"],
            name=data["name"],
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            messages=messages,
            model_config=data.get("model_config", {}),
        )


@dataclass
class SessionIndex:
    """
    会话索引数据类，用于管理会话列表和当前活跃会话
    """
    sessions: list[dict]
    active_session_id: Optional[str] = None

    def to_dict(self) -> dict:
        """
        将SessionIndex转换为字典格式，用于索引文件的序列化
        """
        return {
            "sessions": self.sessions,
            "active_session_id": self.active_session_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SessionIndex":
        """
        从字典创建SessionIndex实例
        """
        return cls(
            sessions=data.get("sessions", []),
            active_session_id=data.get("active_session_id"),
        )


class SessionStorage:
    """
    会话存储类，负责会话数据的持久化管理
    采用分离存储策略：会话索引存储在单一文件，各会话数据独立存储
    """
    def __init__(self, storage_path: str = "./data/sessions"):
        self.storage_path = Path(storage_path)
        self.index_path = self.storage_path / "sessions.json"
        self._ensure_storage_dir()

    def _ensure_storage_dir(self):
        """
        确保存储目录存在，不存在则创建，支持嵌套目录创建
        """
        self.storage_path.mkdir(parents=True, exist_ok=True)

    def _load_index(self) -> SessionIndex:
        """
        加载会话索引文件，若文件不存在或解析错误则返回空索引
        """
        if not self.index_path.exists():
            return SessionIndex(sessions=[], active_session_id=None)
        try:
            with open(self.index_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return SessionIndex.from_dict(data)
        except (json.JSONDecodeError, KeyError):
            return SessionIndex(sessions=[], active_session_id=None)

    def _save_index(self, index: SessionIndex):
        """
        保存会话索引到JSON文件，使用格式化输出提高可读性
        """
        with open(self.index_path, "w", encoding="utf-8") as f:
            json.dump(index.to_dict(), f, ensure_ascii=False, indent=2)

    def _get_session_path(self, session_id: str) -> Path:
        """
        根据会话ID生成对应的存储文件路径
        """
        return self.storage_path / f"session_{session_id}.json"

    def create_session(self, name: Optional[str] = None, model_config: Optional[dict] = None) -> Session:
        """
        创建新会话，生成唯一UUID作为会话ID
        若未提供名称则使用当前时间作为默认名称，默认使用DeepSeek模型配置
        创建完成后自动将该会话设为活跃会话
        """
        session_id = str(uuid.uuid4())
        session_name = name or f"会话 {datetime.now().strftime('%Y-%m-%d %H:%M')}"

        session = Session(
            id=session_id,
            name=session_name,
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
            messages=[],
            model_config=model_config or {
                "model_type": "deepseek",
                "model_name": "deepseek-chat",
                "api_key": "",
                "base_url": "https://api.deepseek.com",
                "temperature": 0.0,
            },
        )

        self._save_session(session)

        index = self._load_index()
        index.sessions.append({
            "id": session_id,
            "name": session_name,
            "created_at": session.created_at,
        })
        index.active_session_id = session_id
        self._save_index(index)

        return session

    def _save_session(self, session: Session):
        """
        将单个会话数据保存到独立JSON文件中
        """
        session_path = self._get_session_path(session.id)
        with open(session_path, "w", encoding="utf-8") as f:
            json.dump(session.to_dict(), f, ensure_ascii=False, indent=2)

    def get_session(self, session_id: str) -> Optional[Session]:
        """
        根据会话ID获取会话数据，若文件不存在或解析错误则返回None
        """
        session_path = self._get_session_path(session_id)
        if not session_path.exists():
            return None
        try:
            with open(session_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return Session.from_dict(data)
        except (json.JSONDecodeError, KeyError):
            return None

    def update_session(self, session: Session):
        """
        更新会话数据，会自动更新时间戳并同步更新索引中的会话信息
        """
        session.updated_at = datetime.now().isoformat()
        self._save_session(session)

        index = self._load_index()
        for s in index.sessions:
            if s["id"] == session.id:
                s["name"] = session.name
                s["updated_at"] = session.updated_at
                break
        self._save_index(index)

    def delete_session(self, session_id: str):
        """
        删除指定会话，若删除的是活跃会话则自动切换到第一个可用会话
        遍历索引列表找到目标会话并移除，确保索引与实际文件保持一致
        """
        session_path = self._get_session_path(session_id)
        if session_path.exists():
            session_path.unlink()

        index = self._load_index()
        index.sessions = [s for s in index.sessions if s["id"] != session_id]
        if index.active_session_id == session_id:
            index.active_session_id = index.sessions[0]["id"] if index.sessions else None
        self._save_index(index)

    def list_sessions(self) -> list[dict]:
        """
        获取所有会话的摘要信息列表
        """
        index = self._load_index()
        return index.sessions

    def get_active_session_id(self) -> Optional[str]:
        """
        获取当前活跃会话的ID
        """
        index = self._load_index()
        return index.active_session_id

    def set_active_session(self, session_id: str):
        """
        设置指定会话为活跃会话
        """
        index = self._load_index()
        index.active_session_id = session_id
        self._save_index(index)
