#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
FileParserClient 模块

文件解析上传客户端，支持将文件上传到远程解析服务（如 MinerU）并生成结果文件。
- 支持 JSON 和 Markdown 两种输出格式，通过 output_format 参数控制
- 异步任务提交和状态轮询机制
- 自动创建输出目录和文件写入

Date: 2026/05/02
Author: 张镒谱
"""

import time
import json
import requests
from pathlib import Path
from typing import Dict, Any, Literal
from requests import RequestException


class FileParserClient:
    """
    文件解析客户端

    将文件上传到远程解析服务，根据返回结果在指定位置生成 JSON 或 MD 文件。
    支持异步任务提交和状态轮询机制。

    Attributes:
        default_params: 默认请求参数
        max_retries: 最大轮询重试次数
        poll_interval: 轮询间隔（秒）
        timeout: 请求超时时间（秒）
    """

    def __init__(
        self,
        server_url: str = "http://mineru-openai-server:30000",
        max_retries: int = 60,
        poll_interval: float = 2.0,
        timeout: int = 300,
        **override_params
    ):
        """
        初始化文件解析客户端

        Args:
            server_url: 远程服务器 URL
            max_retries: 最大轮询重试次数，默认为 60
            poll_interval: 轮询间隔（秒），默认为 2.0
            timeout: 请求超时时间（秒），默认为 300
            **override_params: 可选参数，用于覆盖默认请求参数
        """
        self.max_retries = max_retries
        self.poll_interval = poll_interval
        self.timeout = timeout

        self.default_params: Dict[str, Any] = {
            "return_middle_json": False,
            "return_model_output": False,
            "return_md": False,
            "return_images": False,
            "end_page_id": 99999,
            "parse_method": "auto",
            "start_page_id": 0,
            "lang_list": "ch",
            "server_url": server_url,
            "return_content_list": True,
            "backend": "vlm-http-client",
            "table_enable": True,
            "response_format_zip": False,
            "return_original_file": False,
            "formula_enable": False,
        }
        self.default_params.update(override_params)

    def _build_request_params(self, output_format: Literal["json", "md"]) -> Dict[str, Any]:
        """
        根据输出格式构建请求参数

        Args:
            output_format: 输出格式，"json" 或 "md"

        Returns:
            Dict[str, Any]: 请求参数字典
        """
        params = self.default_params.copy()

        if output_format == "json":
            params["return_content_list"] = True
            params["return_md"] = False
        elif output_format == "md":
            params["return_md"] = True
            params["return_content_list"] = False
        else:
            raise ValueError(f"不支持的输出格式: {output_format}，仅支持 'json' 或 'md'")

        return params

    def _ensure_output_dir(self, output_dir: str) -> Path:
        """
        确保输出目录存在

        Args:
            output_dir: 输出目录路径

        Returns:
            Path: 输出目录 Path 对象
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        return output_path

    def _write_json_file(self, file_path: Path, content: Any) -> None:
        """
        写入 JSON 文件

        Args:
            file_path: 文件路径
            content: JSON 内容
        """
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(content, f, ensure_ascii=False, indent=2)

    def _write_markdown_file(self, file_path: Path, content: str) -> None:
        """
        写入 Markdown 文件

        Args:
            file_path: 文件路径
            content: Markdown 内容
        """
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

    def _make_request(self, method: str, url: str, **kwargs) -> requests.Response:
        """
        发送 HTTP 请求

        Args:
            method: HTTP 方法
            url: 请求 URL
            **kwargs: 其他 requests 参数

        Returns:
            requests.Response: 响应对象
        """
        response = requests.request(method, url, **kwargs)
        return response

    def _send_parse_request(self, api_url: str, file_path: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        发送文件解析请求

        Args:
            api_url: API 地址
            file_path: 要解析的文件路径
            params: 请求参数

        Returns:
            Dict[str, Any]: API 响应结果

        Raises:
            RequestException: 请求发送失败
            ValueError: 任务创建失败
        """
        file_path_obj = Path(file_path)
        mime_type = self._get_mime_type(file_path_obj.suffix)

        try:
            with open(file_path, "rb") as f:
                files = {"files": (file_path_obj.name, f, mime_type)}

                response = self._make_request(
                    "POST",
                    api_url,
                    data=params,
                    files=files,
                    timeout=self.timeout
                )

                if response.status_code != 200:
                    raise RequestException(
                        f"请求失败，状态码: {response.status_code}，响应: {response.text}"
                    )

                result = response.json()

                if "task_id" not in result:
                    raise ValueError(f"任务创建失败，响应内容: {result}")

                return result

        except RequestException as e:
            raise RequestException(f"发送请求失败: {str(e)}")

    def _get_mime_type(self, extension: str) -> str:
        """
        根据文件扩展名获取 MIME 类型

        Args:
            extension: 文件扩展名（如 .pdf, .docx）

        Returns:
            str: MIME 类型
        """
        mime_types = {
            ".pdf": "application/pdf",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".doc": "application/msword",
            ".txt": "text/plain",
            ".md": "text/markdown",
            ".csv": "text/csv",
            ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ".xls": "application/vnd.ms-excel",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
        }
        return mime_types.get(extension.lower(), "application/octet-stream")

    def _poll_task_status(self, status_url: str) -> Dict[str, Any]:
        """
        轮询任务状态直到完成

        Args:
            status_url: 状态查询 URL

        Returns:
            Dict[str, Any]: 任务状态响应

        Raises:
            TimeoutError: 轮询超时
            RuntimeError: 任务执行失败
        """
        for attempt in range(self.max_retries):
            try:
                response = self._make_request("GET", status_url, timeout=self.timeout)

                if response.status_code != 200:
                    raise RequestException(f"状态查询失败，状态码: {response.status_code}")

                status_result = response.json()
                status = status_result.get("status", "")

                if status == "completed":
                    return status_result
                elif status == "failed":
                    error_msg = status_result.get("error", "未知错误")
                    raise RuntimeError(f"任务执行失败: {error_msg}")
                else:
                    time.sleep(self.poll_interval)

            except RequestException as e:
                if attempt < self.max_retries - 1:
                    time.sleep(self.poll_interval)
                    continue
                raise RequestException(f"轮询任务状态失败: {str(e)}")

        raise TimeoutError(f"轮询超时，已达到最大重试次数 {self.max_retries}")

    def _fetch_result(self, result_url: str) -> Dict[str, Any]:
        """
        获取解析结果

        Args:
            result_url: 结果获取 URL

        Returns:
            Dict[str, Any]: 解析结果

        Raises:
            RequestException: 获取结果失败
        """
        try:
            response = self._make_request("GET", result_url, timeout=self.timeout)

            if response.status_code != 200:
                raise RequestException(f"获取结果失败，状态码: {response.status_code}")

            return response.json()

        except RequestException as e:
            raise RequestException(f"获取解析结果失败: {str(e)}")

    def parse(
        self,
        file_path: str,
        output_dir: str,
        api_url: str,
        output_format: Literal["json", "md"] = "json"
    ) -> str:
        """
        解析文件并生成输出文件

        将文件上传到远程解析服务，轮询任务状态，获取解析结果并写入指定格式的文件。

        Args:
            file_path: 要解析的文件路径
            output_dir: 输出目录路径
            api_url: 解析服务 API 地址
            output_format: 输出格式，"json" 或 "md"，默认为 "json"

        Returns:
            str: 生成的文件路径

        Raises:
            FileNotFoundError: 文件不存在
            RequestException: 请求发送失败
            ValueError: 任务创建失败
            RuntimeError: 任务执行失败
            TimeoutError: 轮询超时
            IOError: 文件写入失败
        """
        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        output_path = self._ensure_output_dir(output_dir)

        params = self._build_request_params(output_format)

        try:
            task_result = self._send_parse_request(api_url, file_path, params)

            task_id = task_result["task_id"]
            status_url = task_result["status_url"]
            result_url = task_result["result_url"]

            self._poll_task_status(status_url)

            result = self._fetch_result(result_url)

            original_filename = file_path_obj.stem
            file_results = result.get("results", {})

            for filename, file_data in file_results.items():
                if output_format == "json":
                    content = file_data.get("content_list", [])
                    if isinstance(content, str):
                        content = json.loads(content)
                    output_file = output_path / f"{original_filename}.json"
                    self._write_json_file(output_file, content)
                elif output_format == "md":
                    content = file_data.get("md_content", "")
                    output_file = output_path / f"{original_filename}.md"
                    self._write_markdown_file(output_file, content)

                return str(output_file)

            raise ValueError("解析结果中未找到文件数据")

        except RequestException as e:
            raise RequestException(f"文件解析请求失败: {str(e)}")
        except TimeoutError as e:
            raise TimeoutError(f"轮询超时: {str(e)}")
        except IOError as e:
            raise IOError(f"文件写入失败: {str(e)}")


if __name__ == "__main__":
    client = FileParserClient()
    print("FileParserClient 初始化成功")