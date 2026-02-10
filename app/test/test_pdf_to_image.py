#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
PDF转图片功能测试脚本

本脚本用于测试 convert_pdfs_to_images 函数的功能。
"""
import shutil
from pathlib import Path
import fitz
from app.utils.files.pdfToImage import convert_pdfs_to_images


def create_test_pdf(output_path: str, num_pages: int = 3):
    """创建测试用的PDF文件
    
    Args:
        output_path: 输出PDF文件路径
        num_pages: PDF页数，默认为3页
    """
    doc = fitz.open()
    
    for i in range(num_pages):
        page = doc.new_page(width=595, height=842)  # A4 尺寸
        
        page.insert_text(
            point=(50, 100),
            text=f"测试PDF - 第 {i + 1} 页",
            fontsize=24,
            color=(0, 0, 0)
        )
        
        page.insert_text(
            point=(50, 150),
            text=f"这是一个用于测试PDF转图片功能的示例文档。",
            fontsize=14,
            color=(0, 0, 0)
        )
        
        page.insert_text(
            point=(50, 200),
            text=f"页码: {i + 1} / {num_pages}",
            fontsize=12,
            color=(0.5, 0.5, 0.5)
        )
        
        page.draw_rect(
            rect=fitz.Rect(50, 250, 545, 750),
            color=(0.8, 0.8, 0.9),
            fill=(0.9, 0.9, 0.95)
        )
    
    doc.save(output_path)
    doc.close()
    print(f"测试PDF文件已创建: {output_path}")


def test_convert_pdfs_to_images():
    """测试 convert_pdfs_to_images 函数"""
    
    # 配置测试参数 - 使用已存在的PDF文件
    test_session_id = "1"
    test_file_id = "3"
    
    print(f"\n开始测试 convert_pdfs_to_images 函数...")
    print(f"会话ID: {test_session_id}")
    print(f"文件ID: {test_file_id}")
    print(f"PDF路径: app/data/upload/{test_session_id}/{test_file_id}.pdf")
    
    try:
        # 调用转换函数
        step_id = convert_pdfs_to_images(
            session_id=test_session_id,
            file_ids=[test_file_id],
            dpi=150,
            max_workers=2,
            output_format='jpg'
        )
        
        print(f"\n✓ 转换成功!")
        print(f"生成的Step ID: {step_id}")
        
        # 验证输出目录结构
        expected_output_dir = Path("app/data/images") / test_session_id / step_id / test_file_id
        print(f"\n检查输出目录: {expected_output_dir}")
        
        if expected_output_dir.exists():
            print(f"✓ 输出目录存在")
            
            # 列出生成的图片文件
            image_files = list(expected_output_dir.glob("*.jpg"))
            print(f"✓ 生成了 {len(image_files)} 张图片:")
            for img_file in sorted(image_files):
                print(f"  - {img_file.name}")
            
            print(f"\n✓ 测试通过!")
        else:
            print(f"✗ 输出目录不存在")
            
    except Exception as e:
        print(f"\n✗ 测试失败: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    print("=" * 60)
    print("PDF转图片功能测试")
    print("=" * 60)
    
    test_convert_pdfs_to_images()
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)
