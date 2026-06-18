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

================================================================================
新增子智能体工具的标准流程（务必全部完成）
================================================================================
1. 实现工具函数
   在 app/core/tools/ 下新增或修改工具文件（如 FooTools.py），
   工具函数使用 @tool 装饰器且工具名与下方 SUBAGENT_TOOL_NAMES 注册一致

2. 注册到本注册表
   在下方 SUBAGENT_TOOL_NAMES 集合中添加工具名（小写）

3. 同步前端常量
   修改 web/Agent/src/utils/sseParser.js：
   - SUBAGENT_META 中添加 { icon, label } 显示元信息
   - SUBAGENT_TOOLS 集合自动包含（Object.keys）

4. 同步后端删除逻辑（如有特殊清理需求）
   如新工具需在删除会话时清理额外资源，在
   app/shared/utils/memory/checkpoint_history.py 的
   collect_subagent_thread_ids_for_cleanup 中补充清理分支

5. 添加测试
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