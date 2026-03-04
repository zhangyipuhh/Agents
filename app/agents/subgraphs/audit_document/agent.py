#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
智能体模块

本模块实现了合同审批智能体，包含三个节点（start, llm, end），
用于根据用户上传的文件类型调用对应的解析工具，并将解析结果存入长期记忆。

Date: 2026/3/4
Author: 张镒谱
"""
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, START, END
from langgraph.store.base import BaseStore
from app.agents.subgraphs.audit_document.states import AuditDocumentState
from app.agents.subgraphs.audit_document.tools import AuditDocumentTools
from app.agents.llmcalls.ollama import create_model
from app.utils.memory.document_memory_store import DocumentMemoryStore
from typing import Dict, Any, List


class AuditDocumentAgent:
    """
    合同审批智能体类
    """
    
    def __init__(self):
        """
        初始化智能体
        """
        self.tools = AuditDocumentTools()
        self.document_store = DocumentMemoryStore()
        self.model = create_model(
            model_name="qwen3-vl:30b",
            api_key=None,
            temperature=0.1,
            base_url="http://192.168.1.107:11434"
        )
        self.graph = self._build_graph()
    
    def _build_graph(self) -> StateGraph:
        """
        构建智能体工作流图
        
        Returns:
            StateGraph: 智能体工作流图
        """
        # 创建状态图
        builder = StateGraph(AuditDocumentState)
        
        # 添加节点
        builder.add_node("start", self.start_node)
        builder.add_node("llm", self.llm_node)
        builder.add_node("end", self.end_node)
        
        # 添加边
        builder.add_edge(START, "start")
        builder.add_edge("start", "llm")
        builder.add_edge("llm", "end")
        
        # 编译图
        return builder.compile()
    
    def start_node(self, state: AuditDocumentState, config: RunnableConfig) -> Dict[str, Any]:
        """
        开始节点
        
        Args:
            state: 当前状态
            config: 运行配置
            
        Returns:
            新状态
        """
        # 初始化状态
        return {
            "session_id": state.session_id,
            "file_paths": state.file_paths,
            "image_paths": state.image_paths or [],
            "contract_data": state.contract_data or [],
            "transaction_data": state.transaction_data or [],
            "meeting_data": state.meeting_data or [],
            "file_id": state.file_id
        }
    
    def llm_node(self, state: AuditDocumentState, config: RunnableConfig) -> Dict[str, Any]:
        """
        LLM节点
        
        Args:
            state: 当前状态
            config: 运行配置
            
        Returns:
            新状态
        """
        # 获取提示词（智能体的第一参数）
        prompt = state.messages[-1].content if state.messages else ""
        
        # 根据提示词识别文件类型
        file_type = self._identify_file_type(prompt)
        
        # 解析文件
        parsed_results = []
        
        for i, file_path in enumerate(state.file_paths):
            file_id = state.file_id or f"file_{i}"
            
            if file_type == "contract":
                # 解析合同
                result = self.tools.parse_contract(file_path)
                state.contract_data.append(result)
                
                # 存储到长期记忆
                self.document_store.save_document(
                    session_id=state.session_id,
                    file_id=file_id,
                    file_type="contract",
                    content=result,
                    file_name=file_path.split("/")[-1]
                )
            
            elif file_type == "transaction":
                # 解析成交确认书
                result = self.tools.parse_transaction(file_path, state.session_id)
                state.transaction_data.append(result)
                state.image_paths.extend(result.get("image_paths", []))
                
                # 存储到长期记忆
                self.document_store.save_document(
                    session_id=state.session_id,
                    file_id=file_id,
                    file_type="transaction",
                    content=result,
                    file_name=file_path.split("/")[-1]
                )
            
            elif file_type == "meeting":
                # 解析会议纪要
                result = self.tools.parse_meeting_minutes(file_path)
                state.meeting_data.append(result)
                
                # 存储到长期记忆
                self.document_store.save_document(
                    session_id=state.session_id,
                    file_id=file_id,
                    file_type="meeting",
                    content=result,
                    file_name=file_path.split("/")[-1]
                )
            
            parsed_results.append(result)
        
        return {
            "messages": state.messages,
            "session_id": state.session_id,
            "file_paths": state.file_paths,
            "image_paths": state.image_paths,
            "contract_data": state.contract_data,
            "transaction_data": state.transaction_data,
            "meeting_data": state.meeting_data,
            "file_id": state.file_id
        }
    
    def end_node(self, state: AuditDocumentState, config: RunnableConfig) -> Dict[str, Any]:
        """
        结束节点
        
        Args:
            state: 当前状态
            config: 运行配置
            
        Returns:
            最终状态
        """
        # 返回最终状态
        return {
            "messages": state.messages,
            "session_id": state.session_id,
            "file_paths": state.file_paths,
            "image_paths": state.image_paths,
            "contract_data": state.contract_data,
            "transaction_data": state.transaction_data,
            "meeting_data": state.meeting_data,
            "file_id": state.file_id
        }
    
    def _identify_file_type(self, prompt: str) -> str:
        """
        根据提示词识别文件类型
        
        Args:
            prompt: 用户提示词
            
        Returns:
            文件类型（contract, transaction, meeting）
        """
        prompt_lower = prompt.lower()
        
        if "合同" in prompt_lower:
            return "contract"
        elif "成交确认书" in prompt_lower:
            return "transaction"
        elif "会议纪要" in prompt_lower:
            return "meeting"
        else:
            # 默认返回合同类型
            return "contract"
    
    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        运行智能体
        
        Args:
            state: 初始状态
            
        Returns:
            运行结果
        """
        return self.graph.invoke(state)
