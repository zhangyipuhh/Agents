# -*- coding:utf-8 -*-
"""输入消毒路由集成测试：携带 XSS 载荷的请求经 Pydantic 模型层即被剥离标签。

测试策略：直接实例化路由请求模型断言字段值（模型层即消毒边界,
handler 逻辑零改动）；不走 client 全链路（避免 DB mock 噪音）。
"""

from app.shared.routers.user_router import (
    ProfileUpdateRequest,
    UserCreateRequest,
    UsernameUpdateRequest,
    UserUpdateRequest,
)
from app.shared.routers.auth_router import RegisterRequest
from app.shared.routers.project_router import (
    ProjectCreateRequest,
    RenameProjectRequest,
)
from app.shared.routers.session_router import SessionTitleUpdateRequest

PAYLOAD = "<script>alert(1)</script>"


def test_profile_update_request_sanitizes_department_position():
    """profile 部门/职位载荷剥离（渗透报告 sink #1）。"""
    req = ProfileUpdateRequest(
        phone="", email="", department=PAYLOAD, position=PAYLOAD,
    )
    assert req.department == "alert(1)"
    assert req.position == "alert(1)"
    assert "<" not in req.department and "<" not in req.position


def test_username_update_request_sanitizes_new_username():
    """用户名修改载荷剥离。"""
    req = UsernameUpdateRequest(new_username=PAYLOAD)
    assert "<" not in req.new_username


def test_user_create_request_sanitizes_text_fields():
    """admin 创建用户的文本字段载荷剥离；password/role 不受影响。"""
    req = UserCreateRequest(
        username=PAYLOAD, password="Aa!23456", role="user",
        real_name=PAYLOAD, department=PAYLOAD, position=PAYLOAD,
    )
    assert "<" not in req.username
    assert "<" not in req.real_name
    assert "<" not in req.department
    assert "<" not in req.position
    assert req.password == "Aa!23456"
    assert req.role == "user"


def test_user_update_request_sanitizes_text_fields():
    """admin 更新用户的文本字段载荷剥离。"""
    req = UserUpdateRequest(real_name=PAYLOAD, department=PAYLOAD, position=PAYLOAD)
    assert "<" not in req.real_name
    assert "<" not in req.department
    assert "<" not in req.position


def test_register_request_sanitizes_text_fields():
    """注册请求文本字段载荷剥离（渗透报告点名 registration）。"""
    req = RegisterRequest(
        username=PAYLOAD, password="Aa!23456", confirm_password="Aa!23456",
        real_name=PAYLOAD, phone="13800138000", email="a@b.com",
        department=PAYLOAD, position=PAYLOAD,
        captcha_key="k", captcha_code="c",
    )
    assert "<" not in req.username
    assert "<" not in req.real_name
    assert "<" not in req.department
    assert "<" not in req.position


def test_project_create_request_sanitizes_name():
    """项目名载荷剥离（渗透报告 sink #2）。"""
    req = ProjectCreateRequest(name=PAYLOAD)
    assert req.name == "alert(1)"
    assert "<" not in req.name


def test_project_rename_request_sanitizes_name():
    """项目重命名载荷剥离。"""
    req = RenameProjectRequest(name=PAYLOAD)
    assert "<" not in req.name


def test_session_title_update_request_sanitizes_title():
    """会话标题载荷剥离（渗透报告 sink #3）。"""
    req = SessionTitleUpdateRequest(title=PAYLOAD)
    assert req.title == "alert(1)"
    assert "<" not in req.title
