#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
文件转换工具类模块

本模块提供将PDF文件转换为图片的功能。

Date: 2026/2/9
Author: 张镒谱
"""
import fitz  # PyMuPDF
from concurrent.futures import ThreadPoolExecutor

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
    """并行转换
    
    Args:
        pdf_path: PDF 文件路径
        output_dir: 输出目录
        dpi: 输出图片的 DPI（清晰度）
        max_workers: 最大并行工作线程数
        output_format: 输出格式，支持 'png', 'jpg', 'jpeg', 'tiff', 'bmp'
    """
    doc = fitz.open(pdf_path)
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = []
        for page in doc:
            future = executor.submit(convert_page, page, output_dir, dpi, output_format)
            futures.append(future)
        
        for future in futures:
            result = future.result()
            print(f"已保存: {result}")
    
    doc.close()

if __name__ == '__main__':
    # 使用示例 - 输出为 JPG
    pdf_to_images_parallel(
        r'D:\documents\多测项目规整20260107\1、未来花珺\未来花珺建筑工程竣工测量成果报告书.pdf', 
        r'E:\laboratory\AI\Agents\app\data\upload', 
        dpi=200, 
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
