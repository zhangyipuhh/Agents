from typing import Optional

from prompt_toolkit.widgets import Label, Box
from prompt_toolkit.layout import Window
from prompt_toolkit.formatted_text import FormattedText

from ..styles import COLORS


class MessageBubble:
    def __init__(self, role: str, content: str):
        self.role = role
        self.content = content
        self.tool_calls = None

    def render(self) -> str:
        color_map = {
            "user": COLORS["user"],
            "assistant": COLORS["assistant"],
            "tool": COLORS["tool"],
        }
        color = color_map.get(self.role, COLORS["main_fg"])
        return f"[{color}]{self.role}[/]: {self.content}"


class Divider:
    def __init__(self, char: str = "─", color: Optional[str] = None):
        self.char = char
        self.color = color or COLORS["sidebar_bg"]

    def render(self, width: int) -> str:
        return self.char * width


class StatusBar:
    def __init__(self, text: str = ""):
        self.text = text

    def set_text(self, text: str):
        self.text = text

    def render(self) -> str:
        return self.text
