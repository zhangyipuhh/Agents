#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
批量文件转换脚本

将 Knowledge 目录下的多个子文件夹中的所有文件（doc/docx/pdf/xls等格式）转换为 md 格式，
并保存到 tmp 目录，保持原有文件夹层级结构。

使用方法：
    python app/test/batch_convert_to_md.py

Date: 2026/05/08
Author: AI Assistant
"""
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import os
import time
import logging
from typing import List, Set
from app.core.config.config import FILE_PARSER_CONFIG
from app.shared.utils.files.file_parser_client import FileParserClient

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
TARGET_DIR = BASE_DIR / "tmp"

SUPPORTED_EXTENSIONS: Set[str] = {".doc", ".docx", ".pdf", ".xls", ".xlsx", ".wps"}

def get_source_dir_name(source_file: Path) -> str:
    """获取源文件所属的源目录名称"""
    for source_name in SOURCE_DIRS:
        source_path = BASE_DIR / source_name
        try:
            source_file.relative_to(source_path)
            return source_name
        except ValueError:
            continue
    return ""

def get_target_path(source_file: Path) -> Path:
    """根据源文件路径计算目标 md 文件路径，保留源目录结构"""
    source_dir_name = get_source_dir_name(source_file)
    relative_to_source = source_file.relative_to(BASE_DIR / source_dir_name)
    target_path = TARGET_DIR / source_dir_name / relative_to_source
    target_path = target_path.with_suffix(".md")
    return target_path

def should_convert(file_path: Path) -> bool:
    """检查文件是否应该被转换"""
    return file_path.suffix.lower() in SUPPORTED_EXTENSIONS and file_path.is_file()

def collect_files(source_dir: Path) -> List[Path]:
    """递归收集源目录中的所有支持的文件"""
    files = []
    if not source_dir.exists():
        logger.warning(f"源目录不存在: {source_dir}")
        return files
    
    for item in source_dir.rglob("*"):
        if should_convert(item):
            files.append(item)
    return files

def convert_single_file(client: FileParserClient, source_file: Path) -> bool:
    """转换单个文件，返回是否成功"""
    try:
        target_path = get_target_path(source_file)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"正在转换: {source_file.name}")
        logger.info(f"  目标路径: {target_path}")
        
        result_path = client.parse(
            file_path=str(source_file),
            output_dir=str(target_path.parent),
            api_url=FILE_PARSER_CONFIG["api_url"],
            output_format="md",
        )
        
        if result_path and Path(result_path).exists():
            logger.info(f"  转换成功: {result_path}")
            return True
        else:
            logger.error(f"  转换失败: 未生成结果文件")
            return False
            
    except FileNotFoundError as e:
        logger.error(f"  转换失败: 文件不存在 - {e}")
        return False
    except Exception as e:
        logger.error(f"  转换失败: {type(e).__name__} - {e}")
        return False

def batch_convert():
    """批量转换主函数"""
    print("=" * 60)
    print("批量文件转换脚本")
    print("=" * 60)
    
    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    
    print(f"\n目标输出目录: {TARGET_DIR}")
    print(f"支持的格式: {', '.join(SUPPORTED_EXTENSIONS)}")
    print()
    
    if not FILE_PARSER_CONFIG.get("enabled", False):
        print("警告: FILE_PARSER_CONFIG 中 enabled=False，远程解析服务可能未启用")
        print(f"配置: {FILE_PARSER_CONFIG}")
        print()
    
    client = FileParserClient(
        server_url=FILE_PARSER_CONFIG["server_url"],
        max_retries=FILE_PARSER_CONFIG["max_retries"],
        poll_interval=FILE_PARSER_CONFIG["poll_interval"],
        timeout=FILE_PARSER_CONFIG["timeout"],
    )
    
    all_files: List[Path] = []
    for source_name in SOURCE_DIRS:
        source_dir = BASE_DIR / source_name
        files = collect_files(source_dir)
        all_files.extend(files)
        print(f"[{source_name}] 找到 {len(files)} 个支持的文件")
    
    print(f"\n总计找到 {len(all_files)} 个文件待转换")
    print("-" * 60)
    
    if not all_files:
        print("没有找到需要转换的文件！")
        return
    
    success_count = 0
    fail_count = 0
    failed_files = []
    
    for idx, source_file in enumerate(all_files, 1):
        print(f"\n[{idx}/{len(all_files)}]", end=" ")
        target_path = get_target_path(source_file)
        
        if target_path.exists():
            print(f"跳过（已存在）: {source_file.name}")
            success_count += 1
            continue
        
        if convert_single_file(client, source_file):
            success_count += 1
        else:
            fail_count += 1
            failed_files.append(str(source_file))
    
    print("\n" + "=" * 60)
    print("转换完成统计")
    print("=" * 60)
    print(f"成功: {success_count}")
    print(f"失败: {fail_count}")
    print(f"总计: {len(all_files)}")
    
    if failed_files:
        print("\n失败的文件列表:")
        for f in failed_files:
            print(f"  - {f}")

if __name__ == "__main__":
    batch_convert()