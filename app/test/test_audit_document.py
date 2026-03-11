#!usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test script to verify audit_document imports
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from app.utils.memory.document_memory_store import document_memory_store
    print("✅ Successfully imported document_memory_store")
except ImportError as e:
    print(f"❌ ImportError document_memory_store: {e}")
    sys.exit(1)

try:
    from app.agents.subgraphs.audit_document.tools import get_audit_tools
    print("✅ Successfully imported get_audit_tools")
except ImportError as e:
    print(f"❌ ImportError get_audit_tools: {e}")
    sys.exit(1)

try:
    from app.agents.subgraphs.audit_document.agent import AuditDocumentAgent
    print("✅ Successfully imported AuditDocumentAgent")
except ImportError as e:
    print(f"❌ ImportError AuditDocumentAgent: {e}")
    sys.exit(1)

try:
    from app.routers.contract_router import router
    print("✅ Successfully imported contract_router")
except ImportError as e:
    print(f"❌ ImportError contract_router: {e}")
    sys.exit(1)

print("All tests passed!")
