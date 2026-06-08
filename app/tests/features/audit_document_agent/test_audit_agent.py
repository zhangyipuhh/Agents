# -*- coding:utf-8 -*-
"""
审计文档 Agent (AuditDocumentAgent) 冒烟测试模块

验证 AuditDocumentAgent 的核心模块可正常导入以及工具模块可正常导入。

Date: 2026-06-08
"""


def test_agent_module_importable():
    """测试 Agent 主模块可正常导入"""
    from app.features.audit_document_agent import agent
    assert agent is not None


def test_tools_importable():
    """测试工具模块可正常导入"""
    from app.features.audit_document_agent import tools
    assert tools is not None
