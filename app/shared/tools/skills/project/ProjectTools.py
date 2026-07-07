# -*- coding:utf-8 -*-
"""
ProjectTools - project 智能体工具模块。

本模块为 project 智能体提供 8 个 @tool 工具函数，覆盖项目文档工作流的
统一澄清、事实查询、大纲生成、正文填充、工作流编排、日志管理、变更记录
与 Word 导出能力。

工具清单：
1. intent_clarification - 统一澄清协议，向用户发起结构化问题
2. project_doc_query - 项目事实查询
3. project_doc_outline - 按文档类型生成章节大纲
4. project_doc_write - 按项目资料填充文档正文
5. project_doc_workflow - 端到端工作流编排检查清单
6. manage_project_log - 管理 .project/project_log.md
7. append_change_log - 追加变更记录
8. generate_project_docx - 将 Markdown 转为 docx

Date: 2026-07-02
Author: AI Assistant
"""

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse, unquote

from langchain.tools import tool, ToolRuntime
from langchain_core.messages import ToolMessage
from langgraph.config import get_stream_writer
from langgraph.types import Command
from pydantic import BaseModel, Field, field_validator

from app.core.tools.events import create_tool_event
from app.shared.tools.registry import register_tool

logger = logging.getLogger(__name__)

# =============================================================================
# 可选依赖：若模块不存在则降级为 None，并通过日志告警，避免整模块无法导入
# =============================================================================

try:
    from app.core.tools.FilesystemReadTools import explore
except Exception as _e:
    logger.warning(f"FilesystemReadTools.explore 不可用: {_e}")
    explore = None

try:
    from app.core.tools.SkillTools import load_skill, read_skill_file
except Exception as _e:
    logger.warning(f"SkillTools 不可用: {_e}")
    load_skill = None
    read_skill_file = None

try:
    from app.core.config.paths import resolve_project_dir
except Exception as _e:
    logger.warning(f"resolve_project_dir 不可用: {_e}")
    resolve_project_dir = None

try:
    from app.shared.utils.report.word.generator import WordReportGenerator
    from app.shared.utils.report.word.config import (
        CoverConfig,
        FooterConfig,
        ReportConfig,
        SectionConfig,
        TocConfig,
        TocEntry,
    )
except Exception as _e:
    logger.warning(f"WordReportGenerator 不可用: {_e}")
    WordReportGenerator = None
    ReportConfig = None
    SectionConfig = None
    CoverConfig = None
    TocConfig = None
    TocEntry = None
    FooterConfig = None


# =============================================================================
# 常量与映射
# =============================================================================

# 文档类型 -> project-doc-outline references 模板文件名
_OUTLINE_TEMPLATE_MAP = {
    "pre-sales proposal": "outline_pre_sales_proposal.md",
    "售前方案": "outline_pre_sales_proposal.md",
    "requirements specification": "outline_requirements_specification.md",
    "需求规格说明书": "outline_requirements_specification.md",
    "high-level design specification": "outline_high_level_design_specification.md",
    "概要设计说明书": "outline_high_level_design_specification.md",
    "detailed design specification": "outline_detailed_design_specification.md",
    "详细设计说明书": "outline_detailed_design_specification.md",
    "implementation plan": "outline_implementation_plan.md",
    "实施计划": "outline_implementation_plan.md",
    "实施方案": "outline_implementation_plan.md",
    "test plan": "outline_test_plan.md",
    "测试计划": "outline_test_plan.md",
    "测试方案": "outline_test_plan.md",
    "test report": "outline_test_report.md",
    "测试报告": "outline_test_report.md",
    "acceptance report": "outline_acceptance_report.md",
    "验收报告": "outline_acceptance_report.md",
    "implementation & deployment plan": "outline_implementation_deployment_plan.md",
    "实施部署方案": "outline_implementation_deployment_plan.md",
    "training plan": "outline_training_plan.md",
    "培训计划": "outline_training_plan.md",
    "other process documents": "outline_other_process_documents.md",
    "其他过程文档": "outline_other_process_documents.md",
}

# project-doc-write 需要加载的 reference 文件名
_WRITE_REFERENCE_FILES = [
    "software_engineering_doc_section_filling_spec.md",
    "no_fabrication_redline_checklist.md",
    "decision_advisory_generation_rule.md",
    "document_content_purification_rule.md",
    "data_integrity_query_template.md",
]


# =============================================================================
# 内部辅助函数
# =============================================================================

def _safe_get_stream_writer():
    """安全获取流式 writer；非流式环境返回 None，避免抛异常。"""
    try:
        return get_stream_writer()
    except Exception:
        return None


def _tool_call_id(runtime: ToolRuntime) -> str:
    """安全获取工具调用 ID。"""
    try:
        return runtime.tool_call_id
    except Exception:
        return "unknown-tool-call-id"


def _extract_command_text(cmd: Optional[Command]) -> str:
    """从 Command 对象中提取第一条 ToolMessage 的文本内容。"""
    if cmd is None:
        return ""
    update = getattr(cmd, "update", None) or {}
    messages = update.get("messages", [])
    for msg in messages:
        if isinstance(msg, ToolMessage):
            return msg.content or ""
    return json.dumps(update, ensure_ascii=False, default=str)


def _write_event(writer, event: Dict[str, Any]) -> None:
    """向前端发送流式事件，writer 为空时静默跳过。"""
    if writer is not None:
        try:
            writer(event)
        except Exception:
            pass


def _send_tool_start(
    writer,
    tool_name: str,
    tool_call_id: str,
    args: Dict[str, Any],
    description: str,
) -> Dict[str, Any]:
    """发送 tool_start 事件并返回事件字典。"""
    event = create_tool_event(
        event_type="tool_start",
        tool=tool_name,
        tool_call_id=tool_call_id,
        data={"args": args, "description": description},
    )
    _write_event(writer, dict(event))
    return dict(event)


def _send_tool_progress(
    writer,
    tool_name: str,
    tool_call_id: str,
    current: int,
    total: int,
    message: str,
) -> Dict[str, Any]:
    """发送 tool_progress 事件并返回事件字典。"""
    percentage = int(current / total * 100) if total else 0
    event = create_tool_event(
        event_type="tool_progress",
        tool=tool_name,
        tool_call_id=tool_call_id,
        data={
            "current": current,
            "total": total,
            "percentage": percentage,
            "message": message,
        },
    )
    _write_event(writer, dict(event))
    return dict(event)


def _send_tool_stop(
    writer,
    tool_name: str,
    tool_call_id: str,
    result: Dict[str, Any],
    duration_ms: int,
) -> Dict[str, Any]:
    """发送 tool_stop 事件并返回事件字典。"""
    event = create_tool_event(
        event_type="tool_stop",
        tool=tool_name,
        tool_call_id=tool_call_id,
        data={"status": "success", "result": result, "duration_ms": duration_ms},
    )
    _write_event(writer, dict(event))
    return dict(event)


def _error_command(tool_call_id: str, message: str) -> Command:
    """构造带错误 ToolMessage 的 Command。"""
    return Command(
        update={
            "messages": [
                ToolMessage(
                    content=json.dumps(
                        {"status": "error", "message": message},
                        ensure_ascii=False,
                    ),
                    tool_call_id=tool_call_id,
                )
            ]
        }
    )


def _get_skill_base_dir(skill_content: str) -> Optional[Path]:
    """从 load_skill 返回内容中解析 skill 基础目录。"""
    match = re.search(
        r"Base directory for this skill:\s*(.+?)(?:\n|$)", skill_content
    )
    if not match:
        return None
    uri = match.group(1).strip()
    parsed = urlparse(uri)
    path = unquote(parsed.path)
    if os.name == "nt" and path.startswith("/") and len(path) > 2 and path[2] == ":":
        path = path[1:]
    return Path(path) if path else None


def _resolve_project_root(project_id: str) -> Path:
    """解析项目根目录。优先使用 resolve_project_dir，否则基于当前工作目录拼接。"""
    relative = f"data/project/{project_id}"
    if resolve_project_dir is not None:
        try:
            return resolve_project_dir(relative)
        except Exception:
            pass
    return Path.cwd() / relative


def _select_framework_tag(question: str, doc_type: str) -> str:
    """根据问题关键词选择三层框架标签。"""
    text = f"{question} {doc_type}".lower()
    if any(k in text for k in ["评审", "review", "交付", "deliverable", "里程碑", "milestone", "时间", "when"]):
        return "【Framework: PMP · Framework Layer (Schedule Management) + PRINCE2 · Implementation Layer (Management Stage Boundaries)】"
    if any(k in text for k in ["范围", "scope", "变更", "change"]):
        return "【Framework: PRINCE2 · Implementation Layer (Change Theme) + PMP · Framework Layer (Scope/Integration)】"
    if any(k in text for k in ["质量", "quality", "测试", "test", "缺陷", "bug"]):
        return "【Framework: Systems Analyst · Practice Layer (Test & Maintenance) + PMP · Framework Layer (Quality) + PRINCE2 · Implementation Layer (Quality Theme)】"
    if any(k in text for k in ["风险", "risk"]):
        return "【Framework: PMP · Framework Layer (Risk Management) + PRINCE2 · Implementation Layer (Risk Theme)】"
    if any(k in text for k in ["资源", "resource", "成本", "cost", "预算", "budget"]):
        return "【Framework: PMP · Framework Layer (Resource/Cost) + PRINCE2 · Implementation Layer (Business Case Theme)】"
    if any(k in text for k in ["需求", "requirement"]):
        return "【Framework: Systems Analyst · Practice Layer (Requirements Analysis) + PMP · Framework Layer (Scope)】"
    if any(k in text for k in ["架构", "architecture", "设计", "design"]):
        return "【Framework: Systems Analyst · Practice Layer (System Design) + PMP · Framework Layer (Scope/Schedule)】"
    if any(k in text for k in ["实施", "部署", "implementation", "deployment", "运维", "ops"]):
        return "【Framework: Systems Analyst · Practice Layer (Implementation O&M) + PMP · Framework Layer (Executing) + PRINCE2 · Implementation Layer (Delivery Theme)】"
    if any(k in text for k in ["验收", "closing", "close", "收尾"]):
        return "【Framework: PMP · Framework Layer (Closing Process Group) + PRINCE2 · Implementation Layer (Continued Business Validation)】"
    return "【Framework: PMP · Framework Layer / PRINCE2 · Implementation Layer / Systems Analyst · Practice Layer】"


# =============================================================================
# Pydantic 输入模型
# =============================================================================

class QuestionOption(BaseModel):
    """澄清问题的选项。"""

    label: str = Field(
        ..., min_length=1, max_length=50, description="选项显示文本"
    )
    description: str = Field(
        ..., min_length=1, max_length=200, description="选项说明"
    )


class Question(BaseModel):
    """单个澄清问题。"""

    question: str = Field(..., min_length=1, max_length=500, description="问题文本")
    header: str = Field(..., min_length=1, max_length=30, description="短标签")
    options: List[QuestionOption] = Field(
        default_factory=list,
        max_length=5,
        description="选项列表；为空表示纯文本题",
    )
    multiple: bool = Field(
        default=False, description="是否允许多选，默认单选"
    )
    text_only: bool = Field(
        default=False, description="显式标记为纯文本题"
    )

    @field_validator("options")
    @classmethod
    def _validate_options(cls, v: List[QuestionOption]) -> List[QuestionOption]:
        if v and len(v) < 2:
            raise ValueError("options 非空时必须至少 2 个")
        return v


class IntentClarificationInput(BaseModel):
    """intent_clarification 工具入参。"""

    questions: List[Question] = Field(
        ..., min_length=1, max_length=4, description="结构化问题列表（1-4 个）"
    )


class ProjectDocQueryInput(BaseModel):
    """project_doc_query 工具入参。"""

    question: str = Field(..., min_length=1, max_length=2000, description="用户问题")
    doc_type: str = Field(
        default="", max_length=100, description="相关文档类型（可选）"
    )


class ProjectDocOutlineInput(BaseModel):
    """project_doc_outline 工具入参。"""

    doc_type: str = Field(
        ..., min_length=1, max_length=100, description="目标文档类型"
    )
    creation_mode: str = Field(
        default="E1", max_length=10, description="创作模式：E1/E2/E3/E4"
    )


class ProjectDocWriteInput(BaseModel):
    """project_doc_write 工具入参。"""

    outline: str = Field(..., min_length=1, description="已确认的大纲 Markdown")
    doc_type: str = Field(..., min_length=1, max_length=100, description="文档类型")
    creation_mode: str = Field(
        default="E1", max_length=10, description="创作模式：E1/E2/E3/E4"
    )


class ProjectDocWorkflowInput(BaseModel):
    """project_doc_workflow 工具入参。"""

    request: str = Field(..., min_length=1, max_length=2000, description="用户原始请求")


class ManageProjectLogInput(BaseModel):
    """manage_project_log 工具入参。"""

    project_id: str = Field(..., min_length=1, max_length=200, description="项目标识")
    operation: str = Field(
        ..., min_length=1, max_length=20, description="操作类型：append/read"
    )
    content: str = Field(
        default="", max_length=2000, description="append 时的记录内容"
    )


class AppendChangeLogInput(BaseModel):
    """append_change_log 工具入参。"""

    project_id: str = Field(..., min_length=1, max_length=200, description="项目标识")
    record: str = Field(..., min_length=1, max_length=2000, description="变更记录摘要")


class GenerateProjectDocxInput(BaseModel):
    """generate_project_docx 工具入参。"""

    project_id: str = Field(..., min_length=1, max_length=200, description="项目标识")
    markdown_content: str = Field(..., min_length=1, description="Markdown 格式正文")
    title: str = Field(..., min_length=1, max_length=300, description="文档标题")


# =============================================================================
# 工具函数
# =============================================================================

@tool(args_schema=IntentClarificationInput)
def intent_clarification(
    questions: List[Question],
    runtime: ToolRuntime,
) -> Command:
    """
    【统一澄清协议】向用户发起 1-4 个结构化问题，等待用户回答。

    调用时机：
    - 项目文档工作流开始前需要确认需求、范围、文档类型、创作模式等
    - 项目资料缺失需要向用户补充信息
    - 任何需要暂停执行并等待人类输入的节点

    Args:
        questions: 结构化问题列表（1-4 个），每个问题含 question/header/options/multiple/text_only
        runtime: 工具运行时上下文，提供 tool_call_id 与 state

    Returns:
        Command: 包含 pending_question 状态与 ToolMessage 的命令对象
            - pending_question: 待回答问题信息
            - messages: ToolMessage，记录问题已发起

    Raises:
        本工具不向上抛出异常；所有错误通过 ToolMessage 返回
    """
    tool_name = "intent_clarification"
    tool_call_id = _tool_call_id(runtime)
    start_time = datetime.now()
    writer = _safe_get_stream_writer()

    _send_tool_start(
        writer,
        tool_name,
        tool_call_id,
        {"questions_count": len(questions)},
        f"开始统一澄清，共 {len(questions)} 个问题",
    )

    pending_question = {
        "status": "pending",
        "questions": [q.model_dump() for q in questions],
        "tool_call_id": tool_call_id,
    }

    summary = {
        "status": "pending",
        "tool": tool_name,
        "questions_count": len(questions),
        "message": f"已发起 {len(questions)} 个问题等待用户回答",
    }

    end_time = datetime.now()
    duration_ms = int((end_time - start_time).total_seconds() * 1000)
    _send_tool_stop(
        writer,
        tool_name,
        tool_call_id,
        {"status": "pending", "questions_count": len(questions)},
        duration_ms,
    )

    return Command(
        update={
            "pending_question": pending_question,
            "messages": [
                ToolMessage(
                    content=json.dumps(summary, ensure_ascii=False),
                    tool_call_id=tool_call_id,
                )
            ],
        }
    )


@tool(args_schema=ProjectDocQueryInput, description="项目事实查询：回答项目里有什么、何时交付、谁负责、评审怎么安排等问题")
async def project_doc_query(
    question: str,
    doc_type: str = "",
    runtime: ToolRuntime = None,
) -> Command:
    """
    【项目事实查询】基于当前项目文件夹中的资料回答用户的事实性问题。

    调用时机：
    - 用户问“项目里有什么/什么时候交付/谁负责/评审怎么安排”
    - 用户需要 PMO 级别的事实确认
    - 项目文档查询场景

    Args:
        question: 用户问题
        doc_type: 相关文档类型（可选，用于辅助框架选择）
        runtime: 工具运行时上下文，需提供 project_id 与 tool_call_id

    Returns:
        Command: 包含带 Framework 标签的答案与证据来源的 ToolMessage

    Raises:
        本工具不向上抛出异常；错误通过 ToolMessage 返回
    """
    tool_name = "project_doc_query"
    tool_call_id = _tool_call_id(runtime)
    start_time = datetime.now()
    writer = _safe_get_stream_writer()

    _send_tool_start(
        writer,
        tool_name,
        tool_call_id,
        {"question": question, "doc_type": doc_type},
        f"开始项目事实查询: {question}",
    )

    if explore is None:
        return _error_command(tool_call_id, "explore 工具不可用，无法读取项目资料")

    prompt = (
        f"请基于当前项目文件夹中的所有资料，回答以下问题：\n\n"
        f"问题：{question}\n"
        f"相关文档类型：{doc_type or '未指定'}\n\n"
        f"要求：\n"
        f"1. 搜索策划表、合同、需求、计划、周报等项目文件；\n"
        f"2. 只返回项目中真实存在的数据，严禁虚构人名、日期、数字；\n"
        f"3. 列出你读取的文件路径及关键证据摘录；\n"
        f"4. 如果没有找到相关资料，明确说明“未找到对应项目资料”。"
    )

    _send_tool_progress(
        writer,
        tool_name,
        tool_call_id,
        1,
        2,
        "正在调用 explore 读取项目资料",
    )

    explore_cmd = await explore(prompt=prompt, runtime=runtime)
    evidence = _extract_command_text(explore_cmd)

    _send_tool_progress(
        writer,
        tool_name,
        tool_call_id,
        2,
        2,
        "已获取项目资料，正在生成答案",
    )

    framework_tag = _select_framework_tag(question, doc_type)
    answer = f"{framework_tag}\n\n基于项目资料查询结果：\n\n{evidence}"

    result_data = {
        "status": "success",
        "framework_tag": framework_tag,
        "evidence": evidence,
        "answer": answer,
    }

    end_time = datetime.now()
    duration_ms = int((end_time - start_time).total_seconds() * 1000)
    _send_tool_stop(
        writer,
        tool_name,
        tool_call_id,
        result_data,
        duration_ms,
    )

    return Command(
        update={
            "messages": [
                ToolMessage(
                    content=json.dumps(
                        {
                            "status": "success",
                            "tool": tool_name,
                            "answer": answer,
                            "duration_ms": duration_ms,
                        },
                        ensure_ascii=False,
                    ),
                    tool_call_id=tool_call_id,
                )
            ]
        }
    )


@tool(args_schema=ProjectDocOutlineInput, description="按文档类型生成章节大纲（无正文），支持从项目现有 docx 提取格式模板参考")
async def project_doc_outline(
    doc_type: str,
    creation_mode: str = "E1",
    runtime: ToolRuntime = None,
) -> Command:
    """
    【生成章节大纲】根据目标文档类型返回标准章节大纲（无正文）。

    调用时机：
    - 用户需要“先看大纲”再写正文
    - 需要按软件工程规范生成文档结构
    - 已从 hub 确认文档类型与创作模式

    Args:
        doc_type: 目标文档类型，如“实施方案”“测试计划”“需求规格说明书”等
        creation_mode: 创作模式，E1=基于现有资料 / E2=全新独立生成 / E3=增量更新 / E4=仿写其他项目
        runtime: 工具运行时上下文

    Returns:
        Command: 包含章节大纲 Markdown 与格式模板参考的 ToolMessage

    Raises:
        本工具不向上抛出异常；错误通过 ToolMessage 返回
    """
    tool_name = "project_doc_outline"
    tool_call_id = _tool_call_id(runtime)
    start_time = datetime.now()
    writer = _safe_get_stream_writer()

    _send_tool_start(
        writer,
        tool_name,
        tool_call_id,
        {"doc_type": doc_type, "creation_mode": creation_mode},
        f"开始生成 {doc_type} 章节大纲",
    )

    if load_skill is None or read_skill_file is None:
        return _error_command(tool_call_id, "SkillTools 不可用，无法加载大纲模板")

    key = doc_type.strip().lower()
    template_file = _OUTLINE_TEMPLATE_MAP.get(key)
    if template_file is None:
        return _error_command(
            tool_call_id, f"不支持的文档类型: {doc_type}"
        )

    _send_tool_progress(
        writer, tool_name, tool_call_id, 1, 3, "加载 project-doc-outline skill"
    )

    skill_cmd = load_skill("project-doc-outline", runtime=runtime)
    skill_content = _extract_command_text(skill_cmd)
    base_dir = _get_skill_base_dir(skill_content)

    reference_content = ""
    if base_dir is not None:
        ref_path = base_dir / "references" / template_file
        ref_cmd = read_skill_file(str(ref_path), runtime=runtime)
        reference_content = _extract_command_text(ref_cmd)

    _send_tool_progress(
        writer, tool_name, tool_call_id, 2, 3, "读取项目现有 docx 格式模板"
    )

    format_template = ""
    if explore is not None:
        prompt = (
            f"请在当前项目文件夹中查找与“{doc_type}”相关的 docx 文件，"
            f"提取其章节结构（只列标题层级，不要正文），作为格式模板参考返回。"
            f"如果没有找到相关 docx，说明“未找到格式模板”。"
        )
        explore_cmd = await explore(prompt=prompt, runtime=runtime)
        format_template = _extract_command_text(explore_cmd)

    _send_tool_progress(
        writer, tool_name, tool_call_id, 3, 3, "组装章节大纲"
    )

    outline_md = (
        f"# {doc_type} 章节大纲\n\n"
        f"> 创作模式：{creation_mode}\n\n"
        f"## 参考模板（{template_file}）\n\n"
        f"{reference_content}\n\n"
        f"## 项目格式模板参考\n\n"
        f"{format_template or '未找到项目内相关 docx 格式模板'}\n"
    )

    result_data = {
        "status": "success",
        "doc_type": doc_type,
        "creation_mode": creation_mode,
        "template_file": template_file,
        "outline": outline_md,
    }

    end_time = datetime.now()
    duration_ms = int((end_time - start_time).total_seconds() * 1000)
    _send_tool_stop(writer, tool_name, tool_call_id, result_data, duration_ms)

    return Command(
        update={
            "messages": [
                ToolMessage(
                    content=json.dumps(
                        {
                            "status": "success",
                            "tool": tool_name,
                            "doc_type": doc_type,
                            "creation_mode": creation_mode,
                            "outline": outline_md,
                            "duration_ms": duration_ms,
                        },
                        ensure_ascii=False,
                    ),
                    tool_call_id=tool_call_id,
                )
            ]
        }
    )


@tool(args_schema=ProjectDocWriteInput, description="在已确认的大纲上，按项目资料填充文档正文")
async def project_doc_write(
    outline: str,
    doc_type: str,
    creation_mode: str = "E1",
    runtime: ToolRuntime = None,
) -> Command:
    """
    【文档正文填充】基于已确认大纲与项目资料，返回可进一步渲染的文档正文上下文。

    调用时机：
    - 用户已确认大纲并要求“按资料写正文”
    - 需要基于项目资料填充各章节
    - 已明确创作模式（E1/E2/E3/E4）

    Args:
        outline: 已确认的大纲 Markdown
        doc_type: 文档类型
        creation_mode: 创作模式，默认 E1
        runtime: 工具运行时上下文

    Returns:
        Command: 包含大纲、项目资料与写作参考的 ToolMessage，供模型继续生成正文

    Raises:
        本工具不向上抛出异常；错误通过 ToolMessage 返回
    """
    tool_name = "project_doc_write"
    tool_call_id = _tool_call_id(runtime)
    start_time = datetime.now()
    writer = _safe_get_stream_writer()

    _send_tool_start(
        writer,
        tool_name,
        tool_call_id,
        {"doc_type": doc_type, "creation_mode": creation_mode},
        f"开始为 {doc_type} 填充正文",
    )

    if load_skill is None or read_skill_file is None:
        return _error_command(
            tool_call_id, "SkillTools 不可用，无法加载写作参考"
        )

    _send_tool_progress(
        writer, tool_name, tool_call_id, 1, 3, "加载 project-doc-write skill 参考"
    )

    skill_cmd = load_skill("project-doc-write", runtime=runtime)
    skill_content = _extract_command_text(skill_cmd)
    base_dir = _get_skill_base_dir(skill_content)

    references: List[str] = []
    if base_dir is not None:
        for ref_file in _WRITE_REFERENCE_FILES:
            ref_cmd = read_skill_file(
                str(base_dir / "references" / ref_file), runtime=runtime
            )
            references.append(_extract_command_text(ref_cmd))

    _send_tool_progress(
        writer, tool_name, tool_call_id, 2, 3, "读取项目资料"
    )

    project_materials = ""
    if explore is not None:
        prompt = (
            f"请基于当前项目文件夹中的资料，提取与“{doc_type}”相关的内容，"
            f"用于填充以下大纲。返回读取的文件路径、关键段落与数据，严禁虚构。\n\n"
            f"大纲：\n{outline}\n"
        )
        explore_cmd = await explore(prompt=prompt, runtime=runtime)
        project_materials = _extract_command_text(explore_cmd)

    _send_tool_progress(
        writer, tool_name, tool_call_id, 3, 3, "组装文档正文上下文"
    )

    body_md = (
        f"# {doc_type}\n\n"
        f"> 创作模式：{creation_mode}\n\n"
        f"## 一、已确认大纲\n\n"
        f"{outline}\n\n"
        f"## 二、项目资料\n\n"
        f"{project_materials or '未找到项目资料'}\n\n"
        f"## 三、写作规范参考\n\n"
        + "\n\n".join(references)
    )

    result_data = {
        "status": "success",
        "doc_type": doc_type,
        "creation_mode": creation_mode,
        "body": body_md,
    }

    end_time = datetime.now()
    duration_ms = int((end_time - start_time).total_seconds() * 1000)
    _send_tool_stop(writer, tool_name, tool_call_id, result_data, duration_ms)

    return Command(
        update={
            "messages": [
                ToolMessage(
                    content=json.dumps(
                        {
                            "status": "success",
                            "tool": tool_name,
                            "doc_type": doc_type,
                            "creation_mode": creation_mode,
                            "body": body_md,
                            "duration_ms": duration_ms,
                        },
                        ensure_ascii=False,
                    ),
                    tool_call_id=tool_call_id,
                )
            ]
        }
    )


@tool(args_schema=ProjectDocWorkflowInput, description="端到端项目文档工作流编排，返回可执行检查清单")
def project_doc_workflow(
    request: str,
    runtime: ToolRuntime = None,
) -> Command:
    """
    【端到端工作流编排】将用户请求转换为按顺序执行的工具调用检查清单。

    调用时机：
    - 用户希望“从 0 生成完整项目文档”
    - 用户希望“基于现有材料写一份文档”
    - 需要 hub → query → outline → write 的完整流水线

    Args:
        request: 用户原始请求
        runtime: 工具运行时上下文

    Returns:
        Command: 包含详细执行计划/检查清单 JSON 的 ToolMessage，提示模型按顺序调用其他工具

    Raises:
        本工具不向上抛出异常；错误通过 ToolMessage 返回
    """
    tool_name = "project_doc_workflow"
    tool_call_id = _tool_call_id(runtime)
    start_time = datetime.now()
    writer = _safe_get_stream_writer()

    _send_tool_start(
        writer,
        tool_name,
        tool_call_id,
        {"request": request},
        "开始编排端到端项目文档工作流",
    )

    checklist = {
        "request": request,
        "steps": [
            {
                "step": 1,
                "tool": "intent_clarification",
                "purpose": "澄清意图维度：E.intent_detail（创作模式 E1/E2/E3/E4）、A.intent（doc_type/project_id/action_intent）、C.environment/D.document_attr",
                "output": "pending_question",
                "next_when": "用户完成回答后",
            },
            {
                "step": 2,
                "tool": "project_doc_query",
                "purpose": "加载策划表、合同、需求、计划等项目资料，提取里程碑、评审计划、责任人",
                "output": "带 Framework 标签的答案与证据来源",
                "next_when": "资料加载完成",
            },
            {
                "step": 3,
                "tool": "intent_clarification",
                "purpose": "如资料缺失，按 B.data / D.document_attr 维度继续向用户澄清",
                "output": "补充澄清记录",
                "next_when": "缺失信息补齐",
            },
            {
                "step": 4,
                "tool": "project_doc_outline",
                "purpose": "按 doc_type + creation_mode 加载 outline 模板，提取项目 docx 格式参考，输出章节大纲",
                "output": "章节大纲 Markdown",
                "next_when": "大纲确认通过",
            },
            {
                "step": 5,
                "tool": "project_doc_write",
                "purpose": "在大纲上按项目资料填充正文，生成决策建议，执行内容净化自检",
                "output": "完整 Markdown 正文",
                "next_when": "正文完成",
            },
            {
                "step": 6,
                "tool": "append_change_log",
                "purpose": "向项目 .project/变更记录.md 追加变更记录",
                "output": "变更记录文件路径",
                "next_when": "每次生成/更新文档后",
            },
            {
                "step": 7,
                "tool": "generate_project_docx",
                "purpose": "（可选）将 Markdown 正文转为 docx 并输出下载地址",
                "output": "download_url 与 file_path",
                "next_when": "用户需要 Word 文件时",
            },
            {
                "step": 8,
                "tool": "manage_project_log",
                "purpose": "向 .project/project_log.md 追加主操作记录",
                "output": "操作记录",
                "next_when": "工作流结束时",
            },
        ],
        "note": (
            "本工具仅返回执行计划；请按 step 顺序调用对应工具，"
            "每个 step 完成后再进入下一步。严禁跳过澄清步骤。"
        ),
    }

    end_time = datetime.now()
    duration_ms = int((end_time - start_time).total_seconds() * 1000)
    _send_tool_stop(
        writer,
        tool_name,
        tool_call_id,
        {"status": "success", "checklist": checklist},
        duration_ms,
    )

    return Command(
        update={
            "messages": [
                ToolMessage(
                    content=json.dumps(
                        {
                            "status": "success",
                            "tool": tool_name,
                            "checklist": checklist,
                            "duration_ms": duration_ms,
                        },
                        ensure_ascii=False,
                    ),
                    tool_call_id=tool_call_id,
                )
            ]
        }
    )


@tool(args_schema=ManageProjectLogInput, description="管理 .project/project_log.md，支持 append/read")
def manage_project_log(
    project_id: str,
    operation: str,
    content: str,
    runtime: ToolRuntime = None,
) -> Command:
    """
    【管理项目主日志】对 data/project/<project_id>/.project/project_log.md 进行追加或读取。

    调用时机：
    - 每个 skill 流程结束后追加主操作记录
    - 需要查看历史操作记录

    Args:
        project_id: 项目标识，用于拼接 data/project/<project_id>/.project/project_log.md
        operation: 操作类型，支持 "append" / "read"
        content: operation="append" 时为要追加的记录内容；operation="read" 时可为空
        runtime: 工具运行时上下文

    Returns:
        Command: 包含操作结果与日志内容（read 时）的 ToolMessage

    Raises:
        本工具不向上抛出异常；错误通过 ToolMessage 返回
    """
    tool_name = "manage_project_log"
    tool_call_id = _tool_call_id(runtime)
    start_time = datetime.now()
    writer = _safe_get_stream_writer()

    _send_tool_start(
        writer,
        tool_name,
        tool_call_id,
        {"project_id": project_id, "operation": operation, "content": content},
        f"开始管理项目日志: {operation}",
    )

    project_root = _resolve_project_root(project_id)
    project_meta_dir = project_root / ".project"
    log_path = project_meta_dir / "project_log.md"

    try:
        if operation == "append":
            project_meta_dir.mkdir(parents=True, exist_ok=True)
            if not log_path.exists():
                header = (
                    f"# Project Log · {project_id}\n\n"
                    "## 操作记录\n\n"
                    "| 时间戳 | skill | 操作类型 | 修改内容 | 证据/路径 |\n"
                    "|---|---|---|---|---|\n"
                )
                log_path.write_text(header, encoding="utf-8")
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            row = f"| {now} | project | {operation} | {content} | .project/{project_id}/ |\n"
            with log_path.open("a", encoding="utf-8") as f:
                f.write(row)
            message = f"已追加日志: {log_path}"
            log_content = ""
        elif operation == "read":
            if not log_path.exists():
                return _error_command(tool_call_id, f"日志文件不存在: {log_path}")
            log_content = log_path.read_text(encoding="utf-8")
            message = f"已读取日志: {log_path}"
        else:
            return _error_command(
                tool_call_id, f"不支持的 operation: {operation}，仅支持 append/read"
            )
    except Exception as e:
        return _error_command(tool_call_id, f"日志操作失败: {e}")

    end_time = datetime.now()
    duration_ms = int((end_time - start_time).total_seconds() * 1000)
    _send_tool_stop(
        writer,
        tool_name,
        tool_call_id,
        {"status": "success", "log_path": str(log_path)},
        duration_ms,
    )

    return Command(
        update={
            "messages": [
                ToolMessage(
                    content=json.dumps(
                        {
                            "status": "success",
                            "tool": tool_name,
                            "operation": operation,
                            "log_path": str(log_path),
                            "message": message,
                            "content": log_content,
                            "duration_ms": duration_ms,
                        },
                        ensure_ascii=False,
                    ),
                    tool_call_id=tool_call_id,
                )
            ]
        }
    )


@tool(args_schema=AppendChangeLogInput, description="追加变更记录到 .project/变更记录.md")
def append_change_log(
    project_id: str,
    record: str,
    runtime: ToolRuntime = None,
) -> Command:
    """
    【追加变更记录】向 data/project/<project_id>/.project/变更记录.md 追加一行。

    调用时机：
    - 每次生成或更新项目文档后
    - 需要记录文档变更历史

    Args:
        project_id: 项目标识
        record: 变更记录摘要
        runtime: 工具运行时上下文

    Returns:
        Command: 包含变更记录文件路径的 ToolMessage

    Raises:
        本工具不向上抛出异常；错误通过 ToolMessage 返回
    """
    tool_name = "append_change_log"
    tool_call_id = _tool_call_id(runtime)
    start_time = datetime.now()
    writer = _safe_get_stream_writer()

    _send_tool_start(
        writer,
        tool_name,
        tool_call_id,
        {"project_id": project_id, "record": record},
        "开始追加变更记录",
    )

    project_root = _resolve_project_root(project_id)
    project_meta_dir = project_root / ".project"
    log_path = project_meta_dir / "变更记录.md"

    try:
        project_meta_dir.mkdir(parents=True, exist_ok=True)
        if not log_path.exists():
            header = (
                "# 变更记录\n\n"
                "> 本文件由 project 智能体自动维护。每次生成/更新文档时会追加一条记录。\n\n"
                "| 日期 | 项目编号 | 变更类型 | 文档名 | 摘要 | 操作人（系统） |\n"
                "|---|---|---|---|---|---|\n"
            )
            log_path.write_text(header, encoding="utf-8")
        today = datetime.now().strftime("%Y-%m-%d")
        row = f"| {today} | {project_id} | 追加 | - | {record} | project-agent |\n"
        with log_path.open("a", encoding="utf-8") as f:
            f.write(row)
    except Exception as e:
        return _error_command(tool_call_id, f"追加变更记录失败: {e}")

    end_time = datetime.now()
    duration_ms = int((end_time - start_time).total_seconds() * 1000)
    _send_tool_stop(
        writer,
        tool_name,
        tool_call_id,
        {"status": "success", "log_path": str(log_path)},
        duration_ms,
    )

    return Command(
        update={
            "messages": [
                ToolMessage(
                    content=json.dumps(
                        {
                            "status": "success",
                            "tool": tool_name,
                            "log_path": str(log_path),
                            "message": f"已追加变更记录: {log_path}",
                            "duration_ms": duration_ms,
                        },
                        ensure_ascii=False,
                    ),
                    tool_call_id=tool_call_id,
                )
            ]
        }
    )


@tool(args_schema=GenerateProjectDocxInput, description="将 Markdown 转换为 docx 并返回下载地址")
def generate_project_docx(
    project_id: str,
    markdown_content: str,
    title: str,
    runtime: ToolRuntime = None,
) -> Command:
    """
    【生成项目文档 Word】将 Markdown 正文转换为 docx，保存到下载目录并返回下载地址。

    调用时机：
    - project_doc_write 完成后需要导出 Word
    - 用户要求下载 docx 文件

    Args:
        project_id: 项目标识（用于上下文展示，不影响保存路径）
        markdown_content: Markdown 格式正文
        title: 文档标题（用于封面）
        runtime: 工具运行时上下文，需提供 session_id

    Returns:
        Command: 包含 download_url 与 file_path 的 ToolMessage

    Raises:
        本工具不向上抛出异常；错误通过 ToolMessage 返回
    """
    tool_name = "generate_project_docx"
    tool_call_id = _tool_call_id(runtime)
    start_time = datetime.now()
    writer = _safe_get_stream_writer()

    _send_tool_start(
        writer,
        tool_name,
        tool_call_id,
        {"project_id": project_id, "title": title},
        f"开始生成 Word 文档: {title}",
    )

    if WordReportGenerator is None or ReportConfig is None or SectionConfig is None:
        return _error_command(
            tool_call_id, "WordReportGenerator 不可用，无法生成 docx"
        )

    session_id = ""
    try:
        session_id = runtime.context.get("session_id", "default_session")
    except Exception:
        session_id = "default_session"

    _send_tool_progress(
        writer, tool_name, tool_call_id, 1, 3, "解析 Markdown 章节"
    )

    sections: List[SectionConfig] = []
    toc_entries: List[TocEntry] = []
    paragraph_lines: List[str] = []

    def _flush_paragraph() -> None:
        if paragraph_lines:
            text = " ".join(paragraph_lines).strip()
            if text:
                sections.append(
                    SectionConfig(section_type="paragraph", content=text)
                )
            paragraph_lines.clear()

    for raw_line in markdown_content.splitlines():
        line = raw_line.strip()
        heading_match = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading_match:
            _flush_paragraph()
            level = len(heading_match.group(1))
            heading_text = heading_match.group(2).strip()
            sections.append(
                SectionConfig(
                    section_type="heading",
                    content=heading_text,
                    level=level,
                    in_toc=True,
                )
            )
            toc_entries.append(TocEntry(text=heading_text, level=level - 1))
        elif line == "":
            _flush_paragraph()
        else:
            paragraph_lines.append(line)
    _flush_paragraph()

    _send_tool_progress(
        writer, tool_name, tool_call_id, 2, 3, "生成 Word 文档"
    )

    now_str = datetime.now().strftime("%Y年%m月%d日")
    cover = CoverConfig.from_legacy(
        title=title,
        date_text=f"生成日期：{now_str}",
        blank_lines_before_title=3,
        blank_lines_after_title=1,
        blank_lines_before_date=2,
    )
    toc = TocConfig(entries=toc_entries)

    config = ReportConfig(
        cover=cover,
        toc=toc,
        sections=sections,
        data={"title": title, "生成日期": now_str},
        footer=FooterConfig(format="第{page}页", start_from="content"),
    )

    try:
        generator = WordReportGenerator(config)
        generator.generate()
    except Exception as e:
        return _error_command(tool_call_id, f"Word 生成失败: {e}")

    _send_tool_progress(
        writer, tool_name, tool_call_id, 3, 3, "保存文件"
    )

    file_name = datetime.now().strftime("%Y%m%d_%H%M%S") + ".docx"
    download_dir = Path("data/download") / session_id
    download_dir.mkdir(parents=True, exist_ok=True)
    file_path = download_dir / file_name

    try:
        generator.save(str(file_path))
    except Exception as e:
        return _error_command(tool_call_id, f"保存 docx 失败: {e}")

    download_url = f"/api/core/download/file?path={file_name}"

    end_time = datetime.now()
    duration_ms = int((end_time - start_time).total_seconds() * 1000)
    _send_tool_stop(
        writer,
        tool_name,
        tool_call_id,
        {
            "status": "success",
            "download_url": download_url,
            "file_path": str(file_path),
        },
        duration_ms,
    )

    return Command(
        update={
            "messages": [
                ToolMessage(
                    content=json.dumps(
                        {
                            "status": "success",
                            "tool": tool_name,
                            "download_url": download_url,
                            "file_name": file_name,
                            "file_path": str(file_path),
                            "duration_ms": duration_ms,
                        },
                        ensure_ascii=False,
                    ),
                    tool_call_id=tool_call_id,
                )
            ]
        }
    )


# =============================================================================
# 工具注册（按 agent="project" 维度）
# =============================================================================

intent_clarification = register_tool(
    name="intent_clarification",
    agent="project",
    description="统一澄清协议，向用户发起结构化问题（1-4 个），等待用户回答",
)(intent_clarification)

project_doc_query = register_tool(
    name="project_doc_query",
    agent="project",
    description="项目事实查询：回答项目里有什么、何时交付、谁负责、评审怎么安排等问题",
)(project_doc_query)

project_doc_outline = register_tool(
    name="project_doc_outline",
    agent="project",
    description="按文档类型生成章节大纲（无正文），支持读取项目现有 docx 作为格式模板参考",
)(project_doc_outline)

project_doc_write = register_tool(
    name="project_doc_write",
    agent="project",
    description="在已确认的大纲上，按项目资料填充文档正文",
)(project_doc_write)

project_doc_workflow = register_tool(
    name="project_doc_workflow",
    agent="project",
    description="端到端项目文档工作流编排，返回可执行检查清单",
)(project_doc_workflow)

manage_project_log = register_tool(
    name="manage_project_log",
    agent="project",
    description="管理 data/project/<project_id>/.project/project_log.md，支持 append/read",
)(manage_project_log)

append_change_log = register_tool(
    name="append_change_log",
    agent="project",
    description="向 data/project/<project_id>/.project/变更记录.md 追加变更记录",
)(append_change_log)

generate_project_docx = register_tool(
    name="generate_project_docx",
    agent="project",
    description="将 Markdown 转换为 docx 并返回下载地址",
)(generate_project_docx)
