#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
PDF帮助类 - 负责处理PDF文件，包括文本提取和OCR识别
"""
from asyncio.windows_events import NULL

import pypdf
import numpy as np


class PDFProcessor:
    """PDF处理器类"""
    
    def __init__(self):
        """初始化PDF处理器"""

    def read_pdf_by_pages(self, file_path: str,page_num: int) -> str:
        """
        按页读取PDF内容
        Args:
            file_path: PDF文件路径
            page_num: 页码
        Returns:
            PDF文本内容
        """
        # 检查是否为扫描PDF
        is_scanned = self.is_scanned_pdf(file_path)
        
        if is_scanned:
            return ""
        else:
            return self.extract_pdf_by_pages(file_path,page_num)
        
    def read_pdf(self, file_path: str) -> str:
        """
        读取PDF文件内容
        
        Args:
            file_path: PDF文件路径
            
        Returns:
            PDF文本内容
        """
        # 检查是否为扫描PDF
        is_scanned = self.is_scanned_pdf(file_path)
        
        if is_scanned:
            print(f"检测到扫描PDF: {file_path}，将使用OCR处理")
            return self.extract_text_from_scanned_pdf(file_path)
        else:
            print(f"处理文本PDF: {file_path}")
            return self.extract_text_from_pdf(file_path)
    
    def extract_text_from_pdf(self, file_path: str) -> str:
        """
        从文本PDF中提取所有文本
        
        Args:
            file_path: PDF文件路径
            
        Returns:
            提取的文本
        """
        text = ""
        try:
            with open(file_path, 'rb') as file:
                pdf_reader = pypdf.PdfReader(file)
                for page_num in range(len(pdf_reader.pages)):
                    page = pdf_reader.pages[page_num]
                    text += page.extract_text() + "\n\n"
            
            return text
        except Exception as e:
            print(f"从PDF提取文本时出错: {str(e)}")
            return ""
       
    
    def extract_pdf_by_pages(self, file_path: str,page_num: int) ->str:
        """
        按页提取PDF内容，返回指定页数之前的内容
        
        Args:
            file_path: PDF文件路径
            
        Returns:
            列表，每个元素为元组 (页内容, 元数据)
        """
        text = ""
        try:
            with open(file_path, 'rb') as file:
                #检查页数不能大于文档最大页数
                pdf_reader = pypdf.PdfReader(file)
                if page_num > len(pdf_reader.pages):
                    page_num = len(pdf_reader.pages)
                for page_num in range(page_num):
                    page = pdf_reader.pages[page_num]
                    text += page.extract_text() + "\n\n"
            return text
        except Exception as e:
            print(f"从PDF提取文本时出错: {str(e)}")
            return ""
    
if __name__ == "__main__":
    pdf_processor = PDFProcessor()
    print(pdf_processor.read_pdf(r"E:\laboratory\AI\AIagent_env\api\data\documents\辽宁消应特种装备成交确认书.PDF"))

