#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
键值对长期记忆存储模块

本模块提供了基于 LangGraph InMemoryStore 的键值对长期记忆存储功能。
用于在智能体工作流中存储和更新任意键值对数据，支持值的追加操作。

Date: 2026-03-20
Author: AI Assistant
"""
from typing import Any, Optional, List, Union
from langgraph.store.memory import InMemoryStore


class KeyValueMemoryStore:
    """基于 LangGraph Store 的键值对长期记忆存储类，支持值的追加操作"""

    def __init__(self, store: Optional[InMemoryStore] = None):
        """
        初始化键值对存储实例

        Args:
            store: 可选的 InMemoryStore 实例，如果不提供则创建新实例
        """
        self.store = store if store is not None else InMemoryStore()

    def set(
        self,
        namespace: str,
        key: str,
        value: Any
    ) -> bool:
        """
        设置某个命名空间下某个 key 的值

        Args:
            namespace: 命名空间，用于区分不同类型的数据
            key: 键名
            value: 要设置的值

        Returns:
            bool: 设置是否成功
        """
        try:
            self.store.put(namespace, key, {"value": value})
            return True
        except Exception:
            return False

    def get(
        self,
        namespace: str,
        key: str
    ) -> Optional[Any]:
        """
        获取某个命名空间下某个 key 的值

        Args:
            namespace: 命名空间
            key: 键名

        Returns:
            key 对应的值，如果不存在则返回 None
        """
        try:
            data = self.store.get(namespace, key)
            if data:
                return data.get("value")
            return None
        except Exception:
            return None

    def append(
        self,
        namespace: str,
        key: str,
        value: Any
    ) -> bool:
        """
        追加值到某个命名空间下某个 key

        如果 key 不存在，则创建一个新的列表包含该值。
        如果 key 存在且值为列表，则追加到列表末尾。
        如果 key 存在且值不为列表，则将原值和新值组成列表。

        Args:
            namespace: 命名空间
            key: 键名
            value: 要追加的值

        Returns:
            bool: 追加是否成功
        """
        try:
            current_value = self.get(namespace, key)

            if current_value is None:
                new_value = [value]
            elif isinstance(current_value, list):
                new_value = current_value + [value]
            else:
                new_value = [current_value, value]

            return self.set(namespace, key, new_value)
        except Exception:
            return False

    def extend(
        self,
        namespace: str,
        key: str,
        values: List[Any]
    ) -> bool:
        """
        批量追加多个值到某个命名空间下某个 key

        Args:
            namespace: 命名空间
            key: 键名
            values: 要追加的值列表

        Returns:
            bool: 追加是否成功
        """
        try:
            current_value = self.get(namespace, key)

            if current_value is None:
                new_value = values
            elif isinstance(current_value, list):
                new_value = current_value + values
            else:
                new_value = [current_value] + values

            return self.set(namespace, key, new_value)
        except Exception:
            return False

    def delete(
        self,
        namespace: str,
        key: str
    ) -> bool:
        """
        删除某个命名空间下某个 key

        Args:
            namespace: 命名空间
            key: 键名

        Returns:
            bool: 删除是否成功
        """
        try:
            self.store.delete(namespace, key)
            return True
        except Exception:
            return False

    def exists(
        self,
        namespace: str,
        key: str
    ) -> bool:
        """
        检查某个命名空间下某个 key 是否存在

        Args:
            namespace: 命名空间
            key: 键名

        Returns:
            bool: key 是否存在
        """
        try:
            data = self.store.get(namespace, key)
            return data is not None
        except Exception:
            return False

    def update(
        self,
        namespace: str,
        key: str,
        value: Any,
        merge: bool = False
    ) -> bool:
        """
        更新某个命名空间下某个 key 的值

        Args:
            namespace: 命名空间
            key: 键名
            value: 新的值
            merge: 是否合并（仅当原值和新值都是字典时有效）

        Returns:
            bool: 更新是否成功
        """
        try:
            if merge:
                current_value = self.get(namespace, key)
                if isinstance(current_value, dict) and isinstance(value, dict):
                    merged_value = {**current_value, **value}
                    return self.set(namespace, key, merged_value)
            return self.set(namespace, key, value)
        except Exception:
            return False


key_value_memory_store = KeyValueMemoryStore()


if __name__ == "__main__":
    print(key_value_memory_store.get("store_id", "file_id"))
