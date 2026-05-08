#!/usr/bin/env python
# -*- coding:utf-8 -*-
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import subprocess
import logging
from typing import List, Tuple

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

BASE_DIR = Path("e:/laboratory/AI/Agents/feature-agent-core/app/data/Knowledge")
SOURCE_DIRS = [
    "民政",
    "农业",
    "其他",
    "水利",
    "政策文件",
    "自然资源"
]

LIBREOFFICE_PATH = Path("D:/Program Files/LibreOffice/program/soffice.exe")

def find_doc_files(source_dir: Path) -> List[Path]:
    files = []
    if not source_dir.exists():
        logger.warning(f"源目录不存在: {source_dir}")
        return files
    for item in source_dir.rglob("*"):
        if item.suffix.lower() == ".doc" and item.is_file():
            files.append(item)
    return files

def convert_with_libreoffice(file_path: Path) -> Tuple[bool, str]:
    try:
        output_dir = file_path.parent
        cmd = [
            str(LIBREOFFICE_PATH),
            "--headless",
            "--convert-to", "docx",
            "--outdir", str(output_dir),
            str(file_path)
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            encoding='utf-8',
            errors='ignore',
            timeout=120
        )
        docx_path = file_path.with_suffix('.docx')
        if docx_path.exists():
            return True, "转换成功"
        if result.returncode == 0:
            return True, "转换成功"
        else:
            return False, f"LibreOffice返回错误: {result.stderr[:200] if result.stderr else 'None'}"
    except subprocess.TimeoutExpired:
        return False, "转换超时（120秒）"
    except FileNotFoundError:
        return False, "未找到LibreOffice命令，请确认已安装"
    except Exception as e:
        return False, f"转换失败: {str(e)}"

def batch_convert():
    print("=" * 60)
    print("DOC文件批量转换为DOCX脚本")
    print("=" * 60)
    
    print(f"\nLibreOffice路径检查...")
    if LIBREOFFICE_PATH.exists():
        print(f"LibreOffice路径: {LIBREOFFICE_PATH}")
        try:
            result = subprocess.run([str(LIBREOFFICE_PATH), "--version"], capture_output=True, text=True)
            print(f"LibreOffice版本: {result.stdout.strip()}")
        except Exception as e:
            print(f"无法获取版本信息: {e}")
    else:
        print(f"错误: LibreOffice未安装在指定路径: {LIBREOFFICE_PATH}")
        return
    
    print(f"\n源目录列表: {', '.join(SOURCE_DIRS)}")
    print("-" * 60)
    
    all_files: List[Path] = []
    for source_name in SOURCE_DIRS:
        source_dir = BASE_DIR / source_name
        files = find_doc_files(source_dir)
        all_files.extend(files)
        print(f"[{source_name}] 找到 {len(files)} 个 .doc 文件")
    
    print(f"\n总计找到 {len(all_files)} 个 .doc 文件待转换")
    print("-" * 60)
    
    if not all_files:
        print("没有找到需要转换的 .doc 文件！")
        return
    
    success_count = 0
    fail_count = 0
    failed_files = []
    
    for idx, file_path in enumerate(all_files, 1):
        print(f"\n[{idx}/{len(all_files)}] 正在处理: {file_path.name}")
        
        success, message = convert_with_libreoffice(file_path)
        if success:
            success_count += 1
            logger.info(f"  成功: {message}")
        else:
            fail_count += 1
            failed_files.append((str(file_path), message))
            logger.error(f"  失败: {message}")
    
    print("\n" + "=" * 60)
    print("转换完成统计")
    print("=" * 60)
    print(f"成功: {success_count}")
    print(f"失败: {fail_count}")
    print(f"总计: {len(all_files)}")
    
    if failed_files:
        print("\n失败的文件列表:")
        for f, msg in failed_files:
            print(f"  - {f}")
            print(f"    原因: {msg}")

if __name__ == "__main__":
    batch_convert()