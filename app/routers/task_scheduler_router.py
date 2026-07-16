#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
智能体定时任务 Admin Router 模块。

提供 /api/admin/task-schedules 下的定时任务 CRUD、启停、手动触发和执行历史查询接口。
所有接口均要求 admin 权限，服务实例由 app/core/server.py lifespan 初始化到 app.state.task_scheduler_service。
"""

from typing import Any, Dict, List, Literal, Optional

from asyncpg import PostgresError as _AsyncPGPostgresError
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, model_validator

from app.shared.utils.agent.task_scheduler_service import (
    TaskScheduleNotFoundError,
    TaskScheduleValidationError,
    TaskSchedulerService,
)
from app.shared.utils.auth.Safety import require_admin


router = APIRouter(
    prefix="/api/admin/task-schedules",
    tags=["Task Scheduler Admin"],
    dependencies=[Depends(require_admin)],
)


class CreateTaskScheduleRequest(BaseModel):
    """创建定时任务请求体。

    Attributes:
        name: 任务名称。
        description: 任务描述。
        target_type: 目标类型，'agent' 或 'script'，默认 'agent'。
        agent_name: 目标智能体名称（target_type='agent' 时必填）。
        prompt: 定时触发时发送给智能体的提示词（target_type='agent' 时必填）。
        script_name: 目标脚本名（target_type='script' 时必填）。
        script_args: 脚本参数（target_type='script' 时使用）。
        cron_expression: 5 段 crontab 表达式。
        timezone: IANA 时区名称。
        enabled: 是否启用。
        context_overrides: 注入 AgentContext 的扩展字段。
        max_concurrent_runs: 单任务最大并发，第一版固定用于配置记录。
    """

    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    target_type: Literal["agent", "script"] = Field(default="agent")
    agent_name: Optional[str] = Field(None, min_length=1, max_length=100)
    prompt: Optional[str] = Field(None, min_length=1)
    script_name: Optional[str] = Field(None, min_length=1, max_length=100)
    script_args: Dict[str, Any] = Field(default_factory=dict)
    cron_expression: str = Field(..., min_length=1, max_length=100)
    timezone: str = Field(default="Asia/Shanghai", min_length=1, max_length=64)
    enabled: bool = Field(default=True)
    context_overrides: Dict[str, Any] = Field(default_factory=dict)
    max_concurrent_runs: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def _validate_target_fields(self) -> "CreateTaskScheduleRequest":
        """跨字段校验：target_type 与 agent_name/prompt/script_name 一致性。

        返回:
            CreateTaskScheduleRequest: 校验通过后的实例。

        异常:
            ValueError: 字段组合非法时抛出。
        """
        if self.target_type == "agent":
            if not self.agent_name or not self.prompt:
                raise ValueError(
                    "agent_name and prompt are required when target_type='agent'"
                )
            if self.script_name:
                raise ValueError(
                    "script_name must be empty when target_type='agent'"
                )
        else:  # script
            if not self.script_name:
                raise ValueError(
                    "script_name is required when target_type='script'"
                )
            if self.agent_name or self.prompt:
                raise ValueError(
                    "agent_name and prompt must be empty when target_type='script'"
                )
        return self


class UpdateTaskScheduleRequest(BaseModel):
    """更新定时任务请求体，未传字段保持原值。

    Attributes:
        name: 任务名称。
        description: 任务描述。
        target_type: 目标类型，'agent' 或 'script'。
        agent_name: 目标智能体名称。
        prompt: 定时触发时发送给智能体的提示词。
        script_name: 目标脚本名。
        script_args: 脚本参数。
        cron_expression: 5 段 crontab 表达式。
        timezone: IANA 时区名称。
        enabled: 是否启用。
        context_overrides: 注入 AgentContext 的扩展字段。
        max_concurrent_runs: 单任务最大并发。
    """

    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    target_type: Optional[Literal["agent", "script"]] = Field(None)
    agent_name: Optional[str] = Field(None, min_length=1, max_length=100)
    prompt: Optional[str] = Field(None, min_length=1)
    script_name: Optional[str] = Field(None, min_length=1, max_length=100)
    script_args: Optional[Dict[str, Any]] = Field(None)
    cron_expression: Optional[str] = Field(None, min_length=1, max_length=100)
    timezone: Optional[str] = Field(None, min_length=1, max_length=64)
    enabled: Optional[bool] = Field(None)
    context_overrides: Optional[Dict[str, Any]] = Field(None)
    max_concurrent_runs: Optional[int] = Field(None, ge=1)

    @model_validator(mode="after")
    def _validate_target_fields_partial(self) -> "UpdateTaskScheduleRequest":
        """部分更新时的跨字段校验。

        仅在显式提供了 target_type 或相关字段时触发，避免部分更新误判。

        返回:
            UpdateTaskScheduleRequest: 校验通过后的实例。

        异常:
            ValueError: 字段组合非法时抛出。
        """
        # 若未提供 target_type，跳过跨字段校验（由 service 层 merged 后再校验）
        if self.target_type is None:
            return self
        if self.target_type == "agent":
            # 部分更新时不强制 agent_name/prompt 必填（可能保留原值）
            # 但若显式提供了 script_name，则视为冲突
            if self.script_name:
                raise ValueError(
                    "script_name must be empty when target_type='agent'"
                )
        else:  # script
            if self.agent_name or self.prompt:
                raise ValueError(
                    "agent_name and prompt must be empty when target_type='script'"
                )
        return self


class SetTaskScheduleEnabledRequest(BaseModel):
    """启用 / 禁用定时任务请求体。

    Attributes:
        enabled: True 启用，False 禁用。
    """

    enabled: bool = Field(...)


def _get_service(request: Request) -> TaskSchedulerService:
    """从 app.state 获取 TaskSchedulerService。

    参数:
        request: FastAPI Request 对象。

    返回:
        TaskSchedulerService: 定时任务服务实例。

    异常:
        HTTPException: 服务未初始化时抛出 500。
    """
    service = getattr(request.app.state, "task_scheduler_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="TaskSchedulerService not initialized",
        )
    return service


def _request_user_id(request: Request) -> int:
    """从 request.state 获取当前用户 ID。

    参数:
        request: FastAPI Request 对象。

    返回:
        int: 用户 ID，缺失时返回 0。
    """
    return int(getattr(request.state, "user_id", 0) or 0)


def _handle_service_error(exc: Exception) -> None:
    """将 service 异常转换为 HTTPException。

    参数:
        exc: service 层异常。

    返回:
        None。

    异常:
        HTTPException: 根据异常类型抛出对应 HTTP 错误。
    """
    if isinstance(exc, TaskScheduleNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, TaskScheduleValidationError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    # 数据库错误兜底：避免错误信息被中间件吞掉只显示 401/500 而无业务 detail。
    if isinstance(exc, _AsyncPGPostgresError):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"database error: {type(exc).__name__}: {exc}",
        )
    raise exc


@router.get("", response_model=List[Dict[str, Any]])
async def list_task_schedules(request: Request) -> List[Dict[str, Any]]:
    """列出所有智能体定时任务。

    参数:
        request: FastAPI Request 对象。

    返回:
        List[Dict[str, Any]]: 定时任务列表。
    """
    service = _get_service(request)
    return await service.list_schedules()


@router.get("/{schedule_id}", response_model=Dict[str, Any])
async def get_task_schedule(request: Request, schedule_id: int) -> Dict[str, Any]:
    """获取单个智能体定时任务。

    参数:
        request: FastAPI Request 对象。
        schedule_id: 定时任务 ID。

    返回:
        Dict[str, Any]: 定时任务记录。
    """
    service = _get_service(request)
    try:
        return await service.get_schedule(schedule_id)
    except Exception as exc:
        _handle_service_error(exc)
        raise


@router.post("", status_code=status.HTTP_201_CREATED, response_model=Dict[str, Any])
async def create_task_schedule(
    request: Request,
    body: CreateTaskScheduleRequest,
) -> Dict[str, Any]:
    """创建智能体定时任务。

    参数:
        request: FastAPI Request 对象。
        body: 创建请求体。

    返回:
        Dict[str, Any]: 新建任务记录。
    """
    service = _get_service(request)
    try:
        return await service.create_schedule(
            body.model_dump(),
            created_by_user_id=_request_user_id(request),
        )
    except Exception as exc:
        _handle_service_error(exc)
        raise


@router.put("/{schedule_id}", response_model=Dict[str, Any])
async def update_task_schedule(
    request: Request,
    schedule_id: int,
    body: UpdateTaskScheduleRequest,
) -> Dict[str, Any]:
    """更新智能体定时任务。

    参数:
        request: FastAPI Request 对象。
        schedule_id: 定时任务 ID。
        body: 更新请求体。

    返回:
        Dict[str, Any]: 更新后的任务记录。
    """
    service = _get_service(request)
    try:
        return await service.update_schedule(
            schedule_id,
            body.model_dump(exclude_unset=True),
        )
    except Exception as exc:
        _handle_service_error(exc)
        raise


@router.delete("/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task_schedule(request: Request, schedule_id: int) -> None:
    """删除智能体定时任务。

    参数:
        request: FastAPI Request 对象。
        schedule_id: 定时任务 ID。

    返回:
        None。
    """
    service = _get_service(request)
    try:
        await service.delete_schedule(schedule_id)
    except Exception as exc:
        _handle_service_error(exc)
        raise


@router.put("/{schedule_id}/enabled", response_model=Dict[str, Any])
async def set_task_schedule_enabled(
    request: Request,
    schedule_id: int,
    body: SetTaskScheduleEnabledRequest,
) -> Dict[str, Any]:
    """启用或禁用智能体定时任务。

    参数:
        request: FastAPI Request 对象。
        schedule_id: 定时任务 ID。
        body: 启停请求体。

    返回:
        Dict[str, Any]: 更新后的任务记录。
    """
    service = _get_service(request)
    try:
        return await service.set_schedule_enabled(schedule_id, body.enabled)
    except Exception as exc:
        _handle_service_error(exc)
        raise


@router.post("/{schedule_id}/trigger", status_code=status.HTTP_202_ACCEPTED, response_model=Dict[str, Any])
async def trigger_task_schedule(request: Request, schedule_id: int) -> Dict[str, Any]:
    """手动立即运行一次智能体定时任务。

    参数:
        request: FastAPI Request 对象。
        schedule_id: 定时任务 ID。

    返回:
        Dict[str, Any]: pending 状态的执行记录。
    """
    service = _get_service(request)
    try:
        return await service.trigger_schedule(schedule_id)
    except Exception as exc:
        _handle_service_error(exc)
        raise


@router.get("/{schedule_id}/runs", response_model=List[Dict[str, Any]])
async def list_task_runs(
    request: Request,
    schedule_id: int,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """查询智能体定时任务执行历史。

    参数:
        request: FastAPI Request 对象。
        schedule_id: 定时任务 ID。
        limit: 最大返回条数。

    返回:
        List[Dict[str, Any]]: 执行历史列表。
    """
    service = _get_service(request)
    return await service.list_runs(schedule_id, limit=limit)
