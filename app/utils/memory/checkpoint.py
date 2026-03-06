#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
LangGraph Checkpoint 全局单例模块

本模块提供了全局单例的 checkpointer，确保在 FastAPI 应用中
多个 Agent 实例共享同一份短期记忆（thread-level persistence）。

支持两种模式：
- 内存模式（MemorySaver）：开发/测试环境，重启后数据丢失
- 持久化模式（SqliteSaver）：生产环境，数据持久化到文件

Date: 2026-03-05
Author: AI Assistant
"""
from typing import Optional
from langgraph.checkpoint.base import BaseCheckpointSaver

# 全局单例 checkpointer
_global_checkpointer: Optional[BaseCheckpointSaver] = None


def get_global_checkpointer(db_path: str = ":memory:") -> BaseCheckpointSaver:
    """获取全局单例 checkpointer
    
    使用单例模式确保在 FastAPI 应用中，所有 Agent 实例共享同一份记忆。
    这样可以实现：
    - 同一 thread_id 的对话在不同请求间保持连续性
    - 多个 Agent 实例共享同一份 checkpoint 数据
    - 支持内存模式和持久化模式切换
    
    Args:
        db_path: SQLite 数据库路径
            - ":memory:" : 内存数据库（重启后丢失，适合开发测试）
            - "./checkpoints.db" : 持久化到文件（适合生产环境）
    
    Returns:
        BaseCheckpointSaver: 全局单例 checkpointer 实例
    
    Example:
        ```python
        # 在 Agent 中使用
        from app.utils.checkpoint import get_global_checkpointer
        
        checkpointer = get_global_checkpointer("./checkpoints.db")
        graph = builder.compile(checkpointer=checkpointer)
        ```
    """
    global _global_checkpointer
    
    if _global_checkpointer is None:
        # 根据 db_path 选择合适的 checkpointer
        if db_path == ":memory:":
            # 内存模式（开发/测试）
            from langgraph.checkpoint.memory import MemorySaver
            _global_checkpointer = MemorySaver()
            print("[Checkpoint] 使用内存模式（MemorySaver）")
        else:
            # 持久化模式（生产环境）
            from langgraph.checkpoint.sqlite import SqliteSaver
            _global_checkpointer = SqliteSaver.from_conn_string(db_path)
            print(f"[Checkpoint] 使用持久化模式（SqliteSaver）: {db_path}")
    
    return _global_checkpointer


def reset_global_checkpointer():
    """重置全局单例 checkpointer
    
    用于测试或需要重新初始化 checkpointer 的场景。
    """
    global _global_checkpointer
    _global_checkpointer = None
    print("[Checkpoint] 全局 checkpointer 已重置")