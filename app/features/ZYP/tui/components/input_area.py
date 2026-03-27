from typing import Callable, Optional

from prompt_toolkit.widgets import TextArea, Button, Label
from prompt_toolkit.layout import Container, HSplit, VSplit, Window
from prompt_toolkit.key_binding import KeyBindings

from ..styles import COLORS


class InputArea:
    def __init__(
        self,
        on_submit: Callable[[str], None] = None,
        on_interrupt: Callable = None,
        height: int = 5,
    ):
        self.on_submit = on_submit
        self.on_interrupt = on_interrupt
        self.height = height
        self._text = ""

        self._input = TextArea(
            multiline=True,
            height=height - 1,
            accept_handler=self._handle_submit,
            get_line_prefix=self._get_prefix,
            style=f"bg:{COLORS['input_bg']} fg:{COLORS['main_fg']}",
        )

        self._submit_btn = Button(
            text="发送",
            handler=self._handle_submit,
            width=8,
        )

        self._interrupt_btn = Button(
            text="中断",
            handler=self._handle_interrupt,
            width=8,
        )

        self._status_label = Label(
            text="Ctrl+Enter 发送 | Ctrl+C 中断",
            style=f"italic fg:{COLORS['warning']}",
        )

        self._kb = self._create_key_bindings()

    def _create_key_bindings(self) -> KeyBindings:
        kb = KeyBindings()

        @kb.add("c-c", eager=True)
        def handle_interrupt(event):
            if self.on_interrupt:
                self.on_interrupt()

        return kb

    def _handle_submit(self):
        text = self._input.text.strip()
        if text and self.on_submit:
            self.on_submit(text)
            self._input.text = ""

    def _get_prefix(self, line_number: int, other_state: dict) -> str:
        return ""

    def set_enabled(self, enabled: bool):
        self._input.read_only = not enabled
        self._submit_btn.window.style = (
            f"bg:{COLORS['primary']} fg:#000000"
            if enabled
            else f"bg:#666666 fg:#999999"
        )

    def set_status(self, status: str):
        self._status_label.text = status

    def get_container(self) -> Container:
        button_row = HSplit([
            self._submit_btn,
            self._interrupt_btn,
            self._status_label,
        ], align="horizontal")

        return VSplit([
            self._input,
            button_row,
        ], height=self.height)

    def focus(self):
        return self._input
