import asyncio
import logging
from typing import Optional, Callable

from prompt_toolkit import Application
from prompt_toolkit.layout import Layout, HSplit, VSplit, Window, ConditionalContainer
from prompt_toolkit.widgets import Label, TextArea, Button
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.filters import has_focus
from prompt_toolkit.cursor_shapes import CursorShape

from ..ZYPAgent import ZYPAgent, ModelConfig
from ..storage import SessionStorage, ConfigStorage
from .handlers import SessionHandler, ModelHandler
from .styles import ZYP_STYLE, COLORS


class ZYPTuiApp:
    def __init__(self):
        self.agent: Optional[ZYPAgent] = None
        self.session_storage: Optional[SessionStorage] = None
        self.config_storage: Optional[ConfigStorage] = None
        self.session_handler: Optional[SessionHandler] = None
        self.model_handler: Optional[ModelHandler] = None

        self._app: Optional[Application] = None
        self._running = False
        self._streaming = False

        self._sidebar_width = 25
        self._input_height = 5

        # 聊天显示区域 - 使用 Window + FormattedTextControl 以获得更好的控制
        self._chat_control = FormattedTextControl(
            text=self._get_welcome_text(),
            focusable=False,
        )
        from prompt_toolkit.layout.margins import ScrollbarMargin
        self._chat_window = Window(
            content=self._chat_control,
            wrap_lines=True,
            right_margins=[ScrollbarMargin()],
            style=f"bg:{COLORS['main_bg']} fg:{COLORS['main_fg']}",
        )

        # 状态标签
        self._status_label = Label(
            text="就绪",
            style=f"italic fg:{COLORS['warning']}"
        )

        # 输入区域 - 关键修复：添加 focusable 和 focus_on_click
        self._input_area = TextArea(
            multiline=True,
            height=3,
            style=f"bg:{COLORS['input_bg']} fg:{COLORS['main_fg']}",
            focusable=True,
            focus_on_click=True,
        )

        # 发送按钮 - 使用自定义样式移除箭头
        self._submit_btn = self._create_flat_button("发送", self._on_input_submit, width=8)

        # 中断按钮
        self._interrupt_btn = self._create_flat_button("中断", self._on_interrupt, width=8)

        # 新建会话按钮
        self._new_session_btn = self._create_flat_button("新建会话", self._on_new_session, width=12)

        # 模型选择按钮
        self._model_buttons = {}
        for model in ["deepseek", "ollama", "openai"]:
            btn = self._create_flat_button(
                f"{model}",
                lambda m=model: self._on_model_select(m),
                width=10,
            )
            self._model_buttons[model] = btn

        # 侧边栏控件
        self._sidebar_control = FormattedTextControl(
            text=self._get_sidebar_text(),
            focusable=False,
        )
        self._sidebar_window = Window(
            content=self._sidebar_control,
            width=Dimension.exact(self._sidebar_width),
            style=f"bg:{COLORS['sidebar_bg']} fg:{COLORS['sidebar_fg']}",
        )

        # 快捷键绑定
        self._kb = self._create_key_bindings()

    def _create_flat_button(self, text: str, handler: Callable, width: int = 8):
        """创建扁平样式按钮，不显示箭头"""
        from prompt_toolkit.layout.controls import FormattedTextControl
        from prompt_toolkit.mouse_events import MouseEventType
        
        def get_text():
            return f"{text:^{width}}"
        
        control = FormattedTextControl(
            text=get_text,
            style=f"bg:{COLORS['primary']} fg:#000000",
            focusable=True,
        )
        
        def handle_mouse(event):
            if event.event_type == MouseEventType.MOUSE_UP:
                handler()
        
        control.mouse_handler = handle_mouse
        
        window = Window(
            content=control,
            height=Dimension.exact(1),
            width=Dimension.exact(width),
            style=f"bg:{COLORS['primary']} fg:#000000",
        )
        
        # 保存引用以便更新样式
        window._button_text = text
        window._button_handler = handler
        return window

    def _get_welcome_text(self) -> str:
        return """欢迎使用 ZYP Agent
==================

请选择或创建新会话开始聊天。

快捷键:
  Ctrl+Enter : 发送消息
  Ctrl+C    : 中断生成
  Ctrl+N    : 新建会话
  Esc       : 退出

支持的模型: deepseek, ollama, openai
"""

    def _create_key_bindings(self) -> KeyBindings:
        kb = KeyBindings()

        # 关键修复：添加 Ctrl+Enter 发送消息
        @kb.add("c-m", eager=True)  # Ctrl+Enter (c-m 是 Enter 的键码)
        def handle_submit(event):
            self._on_input_submit()

        @kb.add("c-j", eager=True)  # Ctrl+J 也作为发送备选
        def handle_submit_alt(event):
            self._on_input_submit()

        @kb.add("escape", eager=True)
        @kb.add("c-c", eager=True)
        def handle_interrupt(event):
            if self._streaming:
                self._on_interrupt()
            else:
                self._running = False
                if self._app:
                    self._app.exit()

        @kb.add("c-n", eager=True)
        def handle_new_session(event):
            self._on_new_session()

        return kb

    async def initialize(self):
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s | %(levelname)-8s | %(message)s',
            datefmt='%H:%M:%S'
        )

        self.session_storage = SessionStorage("./data/sessions")
        self.config_storage = ConfigStorage("./data/config.json")

        self.session_handler = SessionHandler(self.session_storage)
        await self.session_handler.initialize()

        self.model_handler = ModelHandler()
        model_config = self.config_storage.get_model_config()

        self.agent = ZYPAgent()
        await self.agent.initialize()

        self._update_chat_display()
        self._update_sidebar()

        session = self.session_handler.get_active_session()
        if session:
            self._load_session_messages(session)

        self._status_label.text = "就绪"

    def _get_layout(self) -> Layout:
        # 顶部标题栏
        header = Window(
            content=FormattedTextControl(text=" ZYP Agent v1.0 "),
            height=Dimension.exact(1),
            style=f"bold fg:{COLORS['primary']} bg:{COLORS['sidebar_bg']}",
        )

        # 侧边栏 - 包含会话列表和模型选择
        sidebar_content = HSplit([
            Window(
                content=FormattedTextControl(text=" ZYP Agent "),
                height=Dimension.exact(1),
                style=f"bold fg:{COLORS['primary']}",
            ),
            Window(
                content=FormattedTextControl(text="─" * 23),
                height=Dimension.exact(1),
                style=f"fg:{COLORS['sidebar_bg']}",
            ),
            Window(
                content=FormattedTextControl(text=" 会话列表 "),
                height=Dimension.exact(1),
                style=f"bold fg:{COLORS['sidebar_fg']}",
            ),
            self._sidebar_window,
            Window(height=Dimension.exact(1)),  #  spacer
            self._new_session_btn,
            Window(
                content=FormattedTextControl(text="─" * 23),
                height=Dimension.exact(1),
                style=f"fg:{COLORS['sidebar_bg']}",
            ),
            Window(
                content=FormattedTextControl(text=" 模型 "),
                height=Dimension.exact(1),
                style=f"bold fg:{COLORS['sidebar_fg']}",
            ),
            VSplit([
                self._model_buttons["deepseek"],
                self._model_buttons["ollama"],
                self._model_buttons["openai"],
            ]),
        ], width=Dimension.exact(self._sidebar_width))

        # 主聊天区域
        chat_area = HSplit([
            self._chat_window,
        ])

        # 主体布局：侧边栏 + 聊天区域
        body = VSplit([
            sidebar_content,
            Window(width=Dimension.exact(1), char="│", style=f"fg:{COLORS['sidebar_bg']}"),
            chat_area,
        ])

        # 输入区域
        input_row = VSplit([
            self._input_area,
            Window(width=Dimension.exact(1)),  # spacer
            HSplit([
                self._submit_btn,
                self._interrupt_btn,
                self._status_label,
            ], width=Dimension.exact(14)),
        ], height=Dimension.exact(self._input_height))

        # 根布局
        root = HSplit([
            header,
            body,
            Window(height=Dimension.exact(1), char="─", style=f"fg:{COLORS['sidebar_bg']}"),
            input_row,
        ])

        return Layout(root, focused_element=self._input_area)  # 关键修复：设置初始焦点

    def _get_sidebar_text(self) -> str:
        lines = []
        
        session = self.session_handler.get_active_session() if self.session_handler else None
        if session:
            lines.append(f">> {session.name}")
        else:
            lines.append("  无活动会话")
        
        return "\n".join(lines)

    def _update_sidebar(self):
        self._sidebar_control.text = self._get_sidebar_text()

    def run(self):
        self._app = Application(
            layout=self._get_layout(),
            style=ZYP_STYLE,
            key_bindings=self._kb,
            full_screen=True,
            mouse_support=True,
            cursor=CursorShape.BLOCK,
        )
        self._running = True
        self._app.run()

    def _update_chat_display(self):
        if not self.session_handler:
            return
            
        session = self.session_handler.get_active_session()
        if session and session.messages:
            lines = []
            for msg in session.messages:
                role = msg.role
                content = msg.content
                if role == "user":
                    lines.append(f"[{COLORS['user']}]用户[/]: {content}")
                elif role == "assistant":
                    lines.append(f"[{COLORS['assistant']}]助手[/]: {content}")
                elif role == "tool":
                    lines.append(f"[{COLORS['tool']}]工具[/]: {content}")
            self._chat_control.text = "\n\n".join(lines)
        else:
            self._chat_control.text = self._get_welcome_text()

    def _load_session_messages(self, session):
        lines = []
        for msg in session.messages:
            role = msg.role
            content = msg.content
            if role == "user":
                lines.append(f"[{COLORS['user']}]用户[/]: {content}")
            elif role == "assistant":
                lines.append(f"[{COLORS['assistant']}]助手[/]: {content}")
            elif role == "tool":
                lines.append(f"[{COLORS['tool']}]工具[/]: {content}")
        
        if lines:
            self._chat_control.text = "\n\n".join(lines)
        else:
            self._chat_control.text = self._get_welcome_text()

    def _on_input_submit(self):
        text = self._input_area.text.strip()
        if not text:
            return

        if not self._streaming:
            self._input_area.text = ""
            asyncio.create_task(self._handle_message(text))

    async def _handle_message(self, text: str):
        if not self.session_handler:
            return
            
        session_id = self.session_handler.get_active_session_id()
        if not session_id:
            session_id = self.session_handler.create_session()
            self._update_sidebar()

        self.session_handler.add_message(session_id, "user", text)
        
        current_text = self._chat_control.text
        if current_text == self._get_welcome_text():
            self._chat_control.text = f"[{COLORS['user']}]用户[/]: {text}"
        else:
            self._chat_control.text = current_text + f"\n\n[{COLORS['user']}]用户[/]: {text}"

        self._streaming = True
        self._status_label.text = "生成中..."

        self._chat_control.text += f"\n\n[{COLORS['assistant']}]助手[/]: "

        try:
            full_response = ""

            async def stream_callback(delta: str):
                nonlocal full_response
                full_response += delta
                self._chat_control.text += delta

            await self.agent.chat(text, session_id, stream_callback)

            self.session_handler.add_message(session_id, "assistant", full_response)

        except Exception as e:
            logging.error(f"Chat error: {e}")
            self._chat_control.text += f"\n\n[{COLORS['error']}]错误[/]: {str(e)}"

        finally:
            self._streaming = False
            self._status_label.text = "就绪"

    def _on_interrupt(self):
        if self._streaming and self.agent:
            self.agent.stop_streaming()
            self._streaming = False
            self._status_label.text = "已中断"

    def _on_new_session(self):
        if not self._streaming and self.session_handler:
            session_id = self.session_handler.create_session()
            self._chat_control.text = self._get_welcome_text()
            self._update_sidebar()
            self._status_label.text = "新会话已创建"

    def _on_model_select(self, model_type: str):
        if not self._streaming and self.model_handler:
            self.model_handler.set_current_model(model_type)
            for m, btn in self._model_buttons.items():
                # 更新按钮文本 - 使用 * 标记当前选中的模型
                new_text = f"*{m}*" if m == model_type else f"{m}"
                btn._button_text = new_text
                # 强制刷新显示
                btn.content.text = lambda t=new_text, w=btn.width: f"{t:^{w}}"
            self._status_label.text = f"已选择模型: {model_type}"
