#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
query_transformer — 搜索查询转换器。

将自然语言查询拆解为关键词，过滤停用词，生成 glob + grep 模糊搜索模式。
支持中文分词（jieba）和英文分词，输出结构化搜索指令供子智能体执行。
"""

import re

import jieba

_SEPARATORS = re.compile(r'[，,、\s。；;：:！!？?]+')

_STOP_WORDS = {
    # 中文虚词 / 搜索动词
    "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一",
    "上", "也", "很", "到", "说", "要", "去", "你", "会", "着", "被", "把",
    "没有", "看", "好", "自己", "这", "他", "她", "它", "们", "那", "些",
    "什么", "怎么", "如何", "哪里", "那个", "这个", "还是", "可以", "一个",
    "里面", "包含", "包括", "含", "查找", "搜索", "找到", "列出", "帮我",
    "有没有", "能否", "请", "帮我", "文件", "内容", "字样", "关于", "大概",
    "的话", "意思", "比如", "例如", "需要", "想要", "可能", "应该", "帮忙",
    "一下", "看看",
    # 英文虚词
    "the", "a", "an", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will",
    "would", "could", "should", "may", "might", "can", "shall",
    "to", "of", "in", "for", "on", "with", "at", "by", "from",
    "and", "or", "but", "not", "this", "that", "it", "as", "if",
    "then", "than", "so", "just", "also", "very", "too", "only",
    "some", "any", "all", "each", "every", "both", "few", "more",
    "most", "other", "such", "no", "nor", "same", "own", "into",
    "up", "out", "about", "over", "under", "again", "further",
    "once", "here", "there", "when", "where", "why", "how", "get",
}


def tokenize(query: str) -> list[str]:
    """分词并过滤停用词，返回有效关键词列表。"""
    words = list(jieba.cut(query, cut_all=False))
    keywords = []
    for w in words:
        w = w.strip()
        if len(w) >= 2 and w.lower() not in _STOP_WORDS:
            keywords.append(w)
    if not keywords:
        keywords = [query]
    # 去重保持顺序
    seen = set()
    unique = []
    for kw in keywords:
        if kw not in seen:
            seen.add(kw)
            unique.append(kw)
    return unique


def build_search_patterns(keywords: list[str]) -> tuple[str, str]:
    """生成 glob 和 grep 搜索模式。"""
    glob_pattern = " + ".join([f"**/*{kw}*" for kw in keywords])
    grep_pattern = "|".join(keywords)
    return glob_pattern, grep_pattern


def transform_query(query: str) -> str:
    """主入口：自然语言查询 → 结构化搜索指令。"""
    keywords = tokenize(query)
    glob_pattern, grep_pattern = build_search_patterns(keywords)
    return (
        f"用户搜索意图：{query}\n"
        f"拆解关键词：{', '.join(keywords)}\n"
        f"搜索步骤：\n"
        f"1. glob_search 搜索文件名，模式：{glob_pattern}\n"
        f"2. grep_search 搜索文件内容，模式：{grep_pattern}\n"
        f"如果未找到结果，请为每个关键词生成1-2个常用同义词，"
        f"用新关键词重新搜索一次。\n"
        f"直接返回文件路径列表。"
    )
