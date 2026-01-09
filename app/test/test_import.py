#!usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test script to verify MainAgent import
"""

try:
    from app.agents import MainAgent
    print("✅ Successfully imported MainAgent from app.agents")
    
    # Try to instantiate the agent
    agent = MainAgent()
    print("✅ Successfully instantiated MainAgent")
    
    print("All tests passed!")
except ImportError as e:
    print(f"❌ ImportError: {e}")
except Exception as e:
    print(f"❌ Exception: {e}")