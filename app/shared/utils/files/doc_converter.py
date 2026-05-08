#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
文档格式转换工具 - 将旧版 .doc 格式转换为 .docx 格式

用于支持知识库中的 .doc 文件预览功能。

Date: 2026/05/08
"""

import os
import io
import tempfile
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

def convert_doc_to_docx(doc_path: str) -> Tuple[Optional[str], Optional[str]]:
    """
    将 .doc 文件转换为 .docx 格式

    Args:
        doc_path: .doc 文件的完整路径

    Returns:
        Tuple[转换后的文件路径, 错误信息]
        成功时: (docx_path, None)
        失败时: (None, error_message)
    """
    if not os.path.exists(doc_path):
        return None, f"文件不存在: {doc_path}"

    if not doc_path.lower().endswith('.doc'):
        return None, "文件不是 .doc 格式"

    temp_dir = tempfile.gettempdir()
    base_name = os.path.splitext(os.path.basename(doc_path))[0]
    docx_path = os.path.join(temp_dir, f"{base_name}_converted_{os.getpid()}.docx")

    try:
        try:
            import win32com.client
            return _convert_using_word(doc_path, docx_path)
        except ImportError:
            logger.warning("pywin32 未安装，尝试使用 LibreOffice 转换")
            return _convert_using_libreoffice(doc_path, docx_path)
    except Exception as e:
        logger.error(f"转换失败: {e}")
        return None, f"转换失败: {str(e)}"


def _convert_using_word(doc_path: str, output_path: str) -> Tuple[Optional[str], Optional[str]]:
    """
    使用 Microsoft Word COM 对象转换文档（仅 Windows）

    Args:
        doc_path: 源文件路径
        output_path: 输出文件路径

    Returns:
        Tuple[转换后的文件路径, 错误信息]
    """
    try:
        word = win32com.client.Dispatch("Word.Application")
        word.Visible = False

        doc = word.Documents.Open(os.path.abspath(doc_path))
        doc.SaveAs(os.path.abspath(output_path), FileFormat=16)
        doc.Close()
        word.Quit()

        if os.path.exists(output_path):
            return output_path, None
        else:
            return None, "Word 转换后文件未生成"

    except Exception as e:
        logger.error(f"Word COM 转换失败: {e}")
        return None, f"Word 转换失败: {str(e)}"


def _convert_using_libreoffice(doc_path: str, output_path: str) -> Tuple[Optional[str], Optional[str]]:
    """
    使用 LibreOffice 转换文档

    Args:
        doc_path: 源文件路径
        output_path: 输出文件路径

    Returns:
        Tuple[转换后的文件路径, 错误信息]
    """
    import subprocess
    import shutil

    libreoffice_paths = [
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
        "/usr/bin/libreoffice",
        "/usr/bin/soffice"
    ]

    soffice_path = None
    for path in libreoffice_paths:
        if os.path.exists(path):
            soffice_path = path
            break

    if not soffice_path:
        return None, "未找到 LibreOffice，无法转换"

    temp_dir = tempfile.mkdtemp()
    base_name = os.path.splitext(os.path.basename(doc_path))[0]

    try:
        cmd = [
            soffice_path,
            "--headless",
            "--convert-to", "docx",
            "--outdir", temp_dir,
            os.path.abspath(doc_path)
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120
        )

        if result.returncode == 0:
            converted_file = os.path.join(temp_dir, f"{base_name}.docx")
            if os.path.exists(converted_file):
                shutil.copy(converted_file, output_path)
                return output_path, None
            else:
                return None, "LibreOffice 转换后文件未生成"
        else:
            return None, f"LibreOffice 转换失败: {result.stderr}"

    except subprocess.TimeoutExpired:
        return None, "LibreOffice 转换超时"
    except Exception as e:
        logger.error(f"LibreOffice 转换异常: {e}")
        return None, f"LibreOffice 转换异常: {str(e)}"
    finally:
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except:
            pass


def create_simple_docx_from_text(text_content: str, output_path: str) -> Tuple[bool, Optional[str]]:
    """
    从纯文本内容创建简单的 .docx 文件
    这是一个兜底方案，当无法转换时使用

    Args:
        text_content: 文本内容
        output_path: 输出文件路径

    Returns:
        Tuple[是否成功, 错误信息]
    """
    try:
        from docx import Document
        from docx.shared import Pt

        doc = Document()
        for line in text_content.split('\n'):
            para = doc.add_paragraph()
            para.add_run(line)

        doc.save(output_path)
        return True, None

    except ImportError:
        return False, "python-docx 未安装"
    except Exception as e:
        logger.error(f"创建 docx 失败: {e}")
        return False, str(e)


def check_conversion_support() -> dict:
    """
    检查系统支持的转换方式

    Returns:
        dict: 支持情况
    """
    support = {
        "pywin32": False,
        "libreoffice": False,
        "python_docx": False
    }

    try:
        import win32com.client
        support["pywin32"] = True
    except ImportError:
        pass

    try:
        import subprocess
        for path in [r"C:\Program Files\LibreOffice\program\soffice.exe",
                     r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
                     "/usr/bin/soffice"]:
            if os.path.exists(path):
                support["libreoffice"] = True
                break
    except:
        pass

    try:
        from docx import Document
        support["python_docx"] = True
    except ImportError:
        pass

    return support


if __name__ == "__main__":
    support = check_conversion_support()
    print("转换支持情况:")
    for key, value in support.items():
        print(f"  {key}: {'支持' if value else '不支持'}")