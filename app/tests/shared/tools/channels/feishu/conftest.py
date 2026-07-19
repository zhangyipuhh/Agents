# -*- coding:utf-8 -*-
"""
channels/feishu 测试目录本地 conftest

通过 ``importlib.util`` 显式加载 ``app/tests/shared/tools/skills/feishu/conftest.py``，
复用其中已经构造完整的 ``lark_oapi`` mock（含 ``cardkit.v1`` 子模块）。

设计理由：
    - ``FeishuCardConsumer`` 同时依赖 ``lark_oapi.api.im.v1``（发送关联消息 / 降级文本）
      与 ``lark_oapi.api.cardkit.v1``（CardKit create/update），mock 必须完整覆盖
    - 避免在两个目录维护两份重复的 mock 代码（skills/feishu + channels/feishu），
      当 mock 需要扩展时只需改一处
    - pytest 的 conftest.py 不应被显式 import 的约定针对的是 fixture 注入逻辑，
      此处仅复用模块级 ``sys.modules`` mock 设置，不涉及 fixture 命名空间污染

Date: 2026-07-19
Author: AI Assistant
"""
import importlib.util
from pathlib import Path

# 定位 skills/feishu/conftest.py 的绝对路径
_skills_conftest_path = (
    Path(__file__).resolve().parent.parent.parent
    / "skills"
    / "feishu"
    / "conftest.py"
)

_spec = importlib.util.spec_from_file_location(
    "_skills_feishu_conftest_for_channels", _skills_conftest_path
)
_skills_conftest = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_skills_conftest)
