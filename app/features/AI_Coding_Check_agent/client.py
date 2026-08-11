#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
AI辅助编程效果评审客户端

命令行客户端，用于测试评审 API。

Date: 2026-04-21
Author: 张镒谱
"""

import os
import sys
import json
import argparse
from typing import Optional

import requests
from requests.exceptions import RequestException


class AICodingCheckClient:
    def __init__(self, base_url: str = None):
        self.base_url = base_url or os.environ.get("API_BASE_URL", "http://localhost:9001")
        self.token: Optional[str] = None
        self.session_id: Optional[str] = None

    def _bootstrap_creds(self) -> Optional[tuple]:
        """从环境变量读取默认管理员凭据。

        Returns:
            Optional[tuple]: (username, password) 元组；若任一变量缺失或为空,
                返回 None,调用方应跳过登录并显式告警。
        """
        username = os.environ.get("AUTH_DEFAULT_ADMIN_USERNAME")
        password = os.environ.get("AUTH_DEFAULT_ADMIN_PASSWORD")
        if not username or not password:
            print(
                "[AICodingCheckClient] 缺少 AUTH_DEFAULT_ADMIN_USERNAME/"
                "AUTH_DEFAULT_ADMIN_PASSWORD 环境变量,跳过登录"
            )
            return None
        return username, password

    def refresh_token(self) -> Optional[str]:
        """登录后端获取 access_token。

        凭据完全由环境变量 ``AUTH_DEFAULT_ADMIN_USERNAME`` /
        ``AUTH_DEFAULT_ADMIN_PASSWORD`` 决定;缺失时直接返回 None
        且不发请求(避免沿用历史 ``admin/123456`` 默认值)。

        Returns:
            Optional[str]: 新的 access_token,登录失败或凭据缺失时返回 None。
        """
        creds = self._bootstrap_creds()
        if creds is None:
            return None
        username, password = creds
        try:
            response = requests.post(
                f"{self.base_url}/api/auth/login",
                json={"username": username, "password": password},
                timeout=60
            )
            response.raise_for_status()
            self.token = response.json().get("access_token")
            return self.token
        except Exception as e:
            print(f"登录失败: {e}")
            return None

    def create_session(self) -> Optional[str]:
        if not self.token:
            self.refresh_token()
        if not self.token:
            return None
        try:
            response = requests.post(
                f"{self.base_url}/api/session/create",
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=60
            )
            response.raise_for_status()
            self.session_id = response.json().get("session_id")
            return self.session_id
        except Exception as e:
            print(f"创建会话失败: {e}")
            return None

    def review_developer(
        self,
        name: str,
        content: list,
        code: list,
        task: list = None,
    ) -> dict:
        if not self.session_id:
            self.create_session()

        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if self.session_id:
            headers["X-Session-ID"] = self.session_id

        payload = {
            "developer_data": {
                "name": name,
                "content": content,
                "code": code,
                "task": task or [],
            }
        }

        try:
            response = requests.post(
                f"{self.base_url}/api/ai-coding-check/review",
                json=payload,
                headers=headers,
                timeout=120
            )
            response.raise_for_status()
            return response.json()
        except RequestException as e:
            return {"code": 500, "message": str(e), "data": {}}


def main():
    parser = argparse.ArgumentParser(description='AI 编程效果评审客户端')
    parser.add_argument('--name', type=str, required=True, help='开发者姓名')
    parser.add_argument('--content', type=str, nargs='+', required=True, help='文档内容列表')
    parser.add_argument('--code', type=str, nargs='+', required=True, help='代码提交记录列表')
    parser.add_argument('--task', type=str, nargs='*', help='任务列表(可选)')
    parser.add_argument('--base-url', type=str, default=None, help='API 地址')
    args = parser.parse_args()

    client = AICodingCheckClient(args.base_url)

    print("正在连接服务器...")
    if not client.create_session():
        print("连接服务器失败")
        sys.exit(1)
    print(f"会话创建成功: {client.session_id}")

    print("正在提交评审...")
    result = client.review_developer(
        name=args.name,
        content=args.content,
        code=args.code,
        task=args.task if args.task else None
    )

    print("\n评审结果:")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
