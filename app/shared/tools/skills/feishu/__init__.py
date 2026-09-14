#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
shared/tools/skills/feishu 入口

承载 FeishuClient（公共 client 工厂）与 FeishuMessageTools（消息发送工具）；
通过 module_path 发现被工具注册中心加载。

子模块清单：
    - FeishuClient / FeishuEndpointResolver / FeishuMessageTools：旧路径
    - FeishuDocxClient / FeishuSheetsClient / FeishuBitableClient /
      FeishuDriveClient / FeishuWikiClient：HTTP 客户端层（不直接暴露给 LLM）
    - FeishuDocxTools / FeishuSheetsTools / FeishuBitableTools /
      FeishuWikiTools：@tool 工具集
      （docx 7 + sheets 3 + bitable 3 + wiki 6 = 19 件；含 create_wiki_node_from_markdown 一键入口）
    - FeishuWebSocketManager / FeishuWebSocketService / MarkdownToCardConverter /
      InterruptToCardConverter：消息通道与卡片渲染
"""
