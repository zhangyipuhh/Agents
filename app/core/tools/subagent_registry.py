# -*- coding:utf-8 -*-
"""
子智能体工具集中注册表（2026-06-16 新增）

================================================================================
用途
================================================================================
集中维护"当前系统已注册的子智能体工具名集合"，供所有需要按 tool 名称判断
"是否是子智能体"的后端代码引用，避免分散硬编码导致漏改。

当前注册的子智能体工具：
    - sandbox  ：app/core/tools/SandboxTools.py        （沙箱执行）
    - explore  ：app/core/tools/FilesystemReadTools.py  （文件探索）

================================================================================
与前端的关系
================================================================================
前端 web/Agent/src/utils/sseParser.js 中独立维护同名集合 SUBAGENT_TOOLS，
二者必须保持同步。修改本文件后必须同步检查并修改前端常量。

本文件同时维护 SUBAGENT_META（子智能体展示元信息：icon + label），
作为前后端统一的唯一事实来源。前端不再硬编码 icon/label，而是通过
SSE tool_start 事件或历史消息接口中的 `meta` 字段动态获取。

================================================================================
新增子智能体工具的标准流程（务必全部完成）
================================================================================
1. 实现工具函数
   在 app/core/tools/ 下新增或修改工具文件（如 FooTools.py），
   工具函数使用 @tool 装饰器且工具名与下方 SUBAGENT_TOOL_NAMES 注册一致

2. 注册到本注册表
   在下方 SUBAGENT_TOOL_NAMES 集合中添加工具名（小写）

3. 补充展示元信息（唯一事实来源）
   在下方 SUBAGENT_META 字典中添加该工具的 { icon, label } 显示元信息。
   前端会通过事件/历史项中的 `meta` 字段自动获取，无需再修改前端代码。

4. 同步前端常量
   修改 web/Agent/src/utils/sseParser.js：
   - SUBAGENT_TOOLS 集合中添加工具名（用于判断哪些 tool 渲染为 SubAgentCard）
   - 注意：icon/label 不再在前端硬编码

5. 同步后端删除逻辑（如有特殊清理需求）
   如新工具需在删除会话时清理额外资源，在
   app/shared/utils/memory/checkpoint_history.py 的
   collect_subagent_thread_ids_for_cleanup 中补充清理分支

6. 添加测试
   在 app/tests/core/tools/test_subagent_registry.py 验证字典包含新工具
   在 app/tests/shared/utils/memory/test_checkpoint_history_subagent.py
   添加新工具的反查合并行为测试

================================================================================
设计动机（2026-06-16 修复 bug 引入）
================================================================================
2026-06-16 用户反馈 generate_report 等普通工具的 tool_call 被后端
merge_main_and_subagent_messages 错误地包装成 type:"subagent" 元素，
前端误渲染为 SubAgentCard。修复方案决定：
- 后端在源头按 tool 过滤（仅注册表内的工具才走 subagent 反查通道）
- 前端不修改（用户决策），新数据正确即可，旧脏数据后续自然淘汰

为避免后续新增子智能体工具时再次漏改散落各处的硬编码列表，
将工具名集合集中到本文件作为单一事实来源（single source of truth）。

Date: 2026-06-16
"""
from typing import FrozenSet


# 当前已注册的子智能体工具名（frozen 防止运行期误改）
# 重要：修改此集合时务必阅读本文件顶部"新增子智能体工具的标准流程"
SUBAGENT_TOOL_NAMES: FrozenSet[str] = frozenset({"sandbox", "explore", "query_knowledge"})

# 子智能体展示元信息（前后端统一事实来源）
# 前端通过 SSE tool_start 事件或历史消息中的 `meta` 字段获取，避免硬编码
SUBAGENT_META: dict[str, dict[str, str]] = {
    "sandbox": {"icon": "📦", "label": "沙箱执行"},
    "explore": {"icon": "🔍", "label": "文件探索"},
    "query_knowledge": {"icon": "📚", "label": "知识库检索"},
}


def is_subagent_tool(tool_name: str) -> bool:
    """
    判断给定工具名是否为已注册的子智能体工具

    用途：
        - app/shared/utils/memory/checkpoint_history.py 在 merge_main_and_subagent_messages
          与 collect_subagent_thread_ids_for_cleanup 中调用，
          仅对子智能体工具的 tool_call 反查子 thread 历史 / 收集清理 thread_id

    Args:
        tool_name (str): 工具名（不区分大小写，统一小写比较）

    Returns:
        bool: True 表示是子智能体工具
    """
    if not tool_name or not isinstance(tool_name, str):
        return False
    return tool_name.lower() in SUBAGENT_TOOL_NAMES


def get_subagent_meta(tool_name: str) -> dict[str, str]:
    """
    获取指定子智能体工具的展示元信息（icon + label）

    用途：
        - 后端在构造 tool_start 事件或历史 subagent 元素时注入 `meta` 字段
        - 前端通过 SSE / 历史接口获取后渲染 SubAgentCard

    Args:
        tool_name (str): 工具名（不区分大小写）

    Returns:
        dict[str, str]: {"icon": str, "label": str}；未知工具时返回兜底
            {"icon": "🤖", "label": tool_name or "子智能体"}
    """
    if not tool_name or not isinstance(tool_name, str):
        return {"icon": "🤖", "label": "子智能体"}
    key = tool_name.lower()
    if key in SUBAGENT_META:
        return dict(SUBAGENT_META[key])
    return {"icon": "🤖", "label": tool_name}
