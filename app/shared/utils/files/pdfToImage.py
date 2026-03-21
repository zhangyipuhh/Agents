#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
文件转换工具类模块

本模块提供将PDF文件转换为图片的功能。

Date: 2026/2/9
Author: 张镒谱
"""
import os
import uuid
from pathlib import Path
from typing import List, Optional
import fitz  # PyMuPDF
from concurrent.futures import ThreadPoolExecutor


def _get_project_root() -> Path:
    return Path(__file__).parent.parent.parent.parent.parent


def _resolve_path(path: str) -> Path:
    """
    解析路径，支持相对路径和绝对路径

    相对路径基于项目根目录解析。

    Args:
        path (str): 路径字符串

    Returns:
        Path: 解析后的绝对路径
    """
    path_obj = Path(path)
    if path_obj.is_absolute():
        return path_obj.resolve()
    else:
        return (_get_project_root() / path).resolve()


def convert_page(page, output_dir, dpi=200, output_format='jpg'):
    """转换单页

    Args:
        page: PDF 页面对象
        output_dir: 输出目录
        dpi: 输出图片的 DPI（清晰度）
        output_format: 输出格式，支持 'png', 'jpg', 'jpeg', 'tiff', 'bmp'
    """
    pix = page.get_pixmap(dpi=dpi)
    output_path = f"{output_dir}/page_{page.number:03d}.{output_format}"
    pix.save(output_path)
    return output_path


def pdf_to_images_parallel(pdf_path, output_dir, dpi=300, max_workers=4, output_format='jpg'):
    """并行转换PDF为图片

    支持相对路径和绝对路径。相对路径基于项目根目录解析。

    Args:
        pdf_path: PDF 文件路径（支持相对路径和绝对路径）
        output_dir: 输出目录（支持相对路径和绝对路径）
        dpi: 输出图片的 DPI（清晰度）
        max_workers: 最大并行工作线程数
        output_format: 输出格式，支持 'png', 'jpg', 'jpeg', 'tiff', 'bmp'
    """
    pdf_path = _resolve_path(pdf_path)
    output_dir = _resolve_path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(str(pdf_path))

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = []
        for page in doc:
            future = executor.submit(convert_page, page, str(output_dir), dpi, output_format)
            futures.append(future)

        for future in futures:
            result = future.result()
            print(f"已保存: {result}")

    doc.close()


def convert_pdfs_to_images(
    session_id: str,
    file_ids: List[str],
    dpi: int = 300,
    max_workers: int = 4,
    output_format: str = 'jpg',
    upload_dir: str = "app/data/upload",
    output_dir: Optional[str] = None
) -> str:
    """批量转换PDF文件为图片

    将指定会话中的多个PDF文件转换为图片，并按照 session_id/step_id/file_id 的目录结构存储。
    支持相对路径和绝对路径。相对路径基于项目根目录解析。

    Args:
        session_id: 会话ID，用于标识用户会话
        file_ids: PDF文件的ID列表（不带扩展名的UUID）
        dpi: 输出图片的DPI（清晰度），默认为300
        max_workers: 最大并行工作线程数，默认为4
        output_format: 输出格式，支持 'png', 'jpg', 'jpeg', 'tiff', 'bmp'，默认为'jpg'
        upload_dir: 上传目录路径（支持相对路径和绝对路径），默认为"app/data/upload"
        output_dir: 输出目录路径（支持相对路径和绝对路径），默认与upload_dir相同

    Returns:
        str: 生成的step_id

    Raises:
        FileNotFoundError: 当指定的PDF文件不存在时抛出
        ValueError: 当file_ids列表为空时抛出
    """
    if not file_ids:
        raise ValueError("file_ids列表不能为空")

    upload_dir = _resolve_path(upload_dir)
    output_dir = _resolve_path(output_dir) if output_dir else upload_dir

    step_id = str(uuid.uuid4())

    step_output_dir = output_dir / session_id / step_id
    step_output_dir.mkdir(parents=True, exist_ok=True)

    for file_id in file_ids:
        pdf_file = upload_dir / session_id / f"{file_id}.pdf"

        if not pdf_file.exists():
            raise FileNotFoundError(f"找不到PDF文件: {file_id}")

        file_output_dir = step_output_dir / file_id
        file_output_dir.mkdir(parents=True, exist_ok=True)

        doc = fitz.open(str(pdf_file))

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = []
            for page in doc:
                future = executor.submit(convert_page, page, str(file_output_dir), dpi, output_format)
                futures.append(future)

            for future in futures:
                result = future.result()
                print(f"已保存: {result}")

        doc.close()

    return step_id

if __name__ == '__main__':
    # 使用示例 - 输出为 JPG
    pdf_to_images_parallel(
        r'D:\documents\多测项目规整20260107\1、未来花珺\未来花珺建筑工程竣工测量成果报告书.pdf', 
        r'E:\laboratory\AI\Agents\app\data\upload', 
        dpi=100, 
        max_workers=6,
        output_format='jpg'
    )
    
    # 使用示例 - 输出为 PNG（默认）
    # pdf_to_images_parallel(
    #     r'D:\documents\多测项目规整20260107\1、未来花珺\未来花珺建筑工程竣工测量成果报告书.pdf', 
    #     r'E:\laboratory\AI\Agents\app\data\upload', 
    #     dpi=200, 
    #     max_workers=6,
    #     output_format='png'
    # )
