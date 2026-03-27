from typing import Callable, Optional

from prompt_toolkit.widgets import Label, TextArea
from prompt_toolkit.layout import Window, Container, HSplit
from prompt_toolkit.formatted_text import fragment_to_text

from ..styles import COLORS
from .common import MessageBubble, Divider


class ChatArea:
    def __init__(self):
        self._messages: list[dict] = []
        self._display = ""
        self._container = None

    def add_user_message(self, content: str):
        self._messages.append({"role": "user", "content": content})
        self._update_display()

    def add_assistant_message(self, content: str):
        self._messages.append({"role": "assistant", "content": content})
        self._update_display()

    def add_tool_message(self, content: str):
        self._messages.append({"role": "tool", "content": content})
        self._update_display()

    def append_to_last_message(self, delta: str):
        if self._messages:
            self._messages[-1]["content"] += delta
            self._update_display()

    def set_streaming(self, streaming: bool):
        if streaming and self._messages:
            self._messages[-1]["streaming"] = True
            self._update_display()

    def _update_display(self):
        lines = []
        for msg in self._messages:
            role = msg["role"]
            content = msg["content"]
            streaming = msg.get("streaming", False)

            if role == "user":
                lines.append(f"[{COLORS['user']}]用户[/]: {content}")
            elif role == "assistant":
                prefix = "..." if streaming else ""
                lines.append(f"[{COLORS['assistant']}]助手[/]: {prefix}{content}")
            elif role == "tool":
                lines.append(f"[{COLORS['tool']}]工具[/]: {content}")

        self._display = "\n\n".join(lines)

    def clear(self):
        self._messages = []
        self._display = ""

    def get_display(self) -> str:
        return self._display

    def get_messages(self) -> list[dict]:
        return self._messages.copy()

    def get_container(self) -> Window:
        return Window(
            content=TextArea(
                text=self._display,
                multiline=True,
                scrollbar=True,
                read_only=True,
                style=f"bg:{COLORS['main_bg']} fg:{COLORS['main_fg']}",
            )
        )
