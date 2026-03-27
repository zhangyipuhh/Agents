from typing import Callable, Optional
from datetime import datetime

from ...storage import SessionStorage, Message
from ...ZYPAgent import ModelConfig


class SessionHandler:
    def __init__(self, storage: SessionStorage):
        self.storage = storage
        self._sessions = {}
        self._active_session_id = None
        self._on_session_change: Optional[Callable] = None

    async def initialize(self):
        self._sessions = {}
        session_list = self.storage.list_sessions()
        for session_info in session_list:
            session = self.storage.get_session(session_info["id"])
            if session:
                self._sessions[session.id] = session

        self._active_session_id = self.storage.get_active_session_id()

        if not self._active_session_id and self._sessions:
            self._active_session_id = next(iter(self._sessions))

    def set_on_session_change(self, callback: Callable):
        self._on_session_change = callback

    def create_session(self, name: Optional[str] = None, model_config: Optional[dict] = None) -> str:
        session = self.storage.create_session(name, model_config)
        self._sessions[session.id] = session
        self._active_session_id = session.id
        self.storage.set_active_session(session.id)

        if self._on_session_change:
            self._on_session_change(session.id)

        return session.id

    def get_session(self, session_id: str):
        return self._sessions.get(session_id)

    def get_active_session(self):
        if self._active_session_id:
            return self._sessions.get(self._active_session_id)
        return None

    def get_active_session_id(self) -> Optional[str]:
        return self._active_session_id

    def set_active_session(self, session_id: str):
        if session_id in self._sessions:
            self._active_session_id = session_id
            self.storage.set_active_session(session_id)

            if self._on_session_change:
                self._on_session_change(session_id)

    def delete_session(self, session_id: str):
        if session_id in self._sessions:
            del self._sessions[session_id]
            self.storage.delete_session(session_id)

            if self._active_session_id == session_id:
                self._active_session_id = next(iter(self._sessions)) if self._sessions else None
                if self._active_session_id:
                    self.storage.set_active_session(self._active_session_id)

                if self._on_session_change:
                    self._on_session_change(self._active_session_id)

    def list_sessions(self) -> list[dict]:
        result = []
        for session_id, session in self._sessions.items():
            result.append({
                "id": session.id,
                "name": session.name,
                "created_at": session.created_at,
                "updated_at": session.updated_at,
            })
        return sorted(result, key=lambda x: x["updated_at"], reverse=True)

    def add_message(self, session_id: str, role: str, content: str) -> bool:
        session = self._sessions.get(session_id)
        if not session:
            return False

        message = Message(id=str(datetime.now().timestamp()), role=role, content=content)
        session.messages.append(message)
        session.updated_at = datetime.now().isoformat()
        self.storage.update_session(session)
        return True

    def rename_session(self, session_id: str, new_name: str) -> bool:
        session = self._sessions.get(session_id)
        if not session:
            return False

        session.name = new_name
        self.storage.rename_session(session_id, new_name)
        return True

    def update_model_config(self, session_id: str, model_config: dict):
        session = self._sessions.get(session_id)
        if session:
            session.model_config = model_config
            self.storage.update_session(session)
