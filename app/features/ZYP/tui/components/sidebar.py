from typing import Callable, Optional
from datetime import datetime

from prompt_toolkit.layout import Container, Window, HSplit, VSplit, VerticalAlign
from prompt_toolkit.widgets import Label, Button, Box
from prompt_toolkit.layout.controls import FormattedTextControl

from ..styles import COLORS


class SidebarButton(Button):
    def __init__(self, text: str, handler: Callable = None, **kwargs):
        super().__init__(text, handler, **kwargs)


class SessionItem:
    def __init__(self, session_id: str, name: str, is_active: bool = False):
        self.session_id = session_id
        self.name = name
        self.is_active = is_active

    def render(self) -> str:
        prefix = ">> " if self.is_active else "   "
        return f"{prefix}{self.name}"


class SessionList:
    def __init__(self):
        self.items: list[SessionItem] = []
        self.selected_index = 0

    def add(self, session_id: str, name: str, is_active: bool = False):
        item = SessionItem(session_id, name, is_active)
        self.items.append(item)
        if is_active:
            self.selected_index = len(self.items) - 1

    def select(self, index: int):
        if 0 <= index < len(self.items):
            self.selected_index = index
            for i, item in enumerate(self.items):
                item.is_active = i == index

    def get_selected(self) -> Optional[SessionItem]:
        if 0 <= self.selected_index < len(self.items):
            return self.items[self.selected_index]
        return None

    def render(self) -> list[str]:
        return [item.render() for item in self.items]


class Sidebar:
    def __init__(
        self,
        width: int = 25,
        on_session_select: Callable[[str], None] = None,
        on_new_session: Callable = None,
        on_model_change: Callable[[str], None] = None,
    ):
        self.width = width
        self.on_session_select = on_session_select
        self.on_new_session = on_new_session
        self.on_model_change = on_model_change

        self.session_list = SessionList()
        self.current_model = "deepseek"
        self.models = ["deepseek", "ollama", "openai"]

        self._header = Label(text=" ZYP Agent ", style=f"bold fg:{COLORS['primary']}")
        self._divider = Label(text="─" * (self.width - 1), style=f"fg:{COLORS['sidebar_bg']}")

        self._session_header = Label(
            text=" 会话列表 ",
            style=f"bold fg:{COLORS['sidebar_fg']}"
        )

        self._new_session_btn = SidebarButton(
            "[+] 新建会话",
            handler=lambda: on_new_session() if on_new_session else None,
        )

        self._model_label = Label(
            text=" 模型 ",
            style=f"bold fg:{COLORS['sidebar_fg']}"
        )
        self._model_buttons = []
        for model in self.models:
            btn = SidebarButton(
                f"  {model}",
                handler=lambda m=model: on_model_change(m) if on_model_change else None,
            )
            self._model_buttons.append((model, btn))

        # 会话列表显示区域
        self._session_display = Label(
            text="无会话",
            style=f"fg:{COLORS['sidebar_fg']}"
        )

    def add_session(self, session_id: str, name: str):
        is_active = len(self.session_list.items) == 0
        self.session_list.add(session_id, name, is_active)
        self._update_session_display()

    def select_session(self, index: int):
        self.session_list.select(index)
        self._update_session_display()

    def _update_session_display(self):
        session_lines = self.session_list.render()
        self._session_display.text = "\n".join(session_lines) if session_lines else "无会话"

    def get_selected_session(self) -> Optional[str]:
        item = self.session_list.get_selected()
        return item.session_id if item else None

    def clear_sessions(self):
        self.session_list = SessionList()
        self._session_display.text = "无会话"

    def set_model(self, model_type: str):
        self.current_model = model_type

    def get_container(self) -> Container:
        """返回包含所有侧边栏元素的容器"""
        # 模型按钮容器
        model_buttons_container = VSplit([
            btn for _, btn in self._model_buttons
        ])

        # 构建完整的侧边栏布局
        content = HSplit([
            self._header,
            self._divider,
            self._session_header,
            self._session_display,
            Window(height=1),  # spacer
            self._new_session_btn,
            self._divider,
            self._model_label,
            model_buttons_container,
        ], width=self.width)

        return content
