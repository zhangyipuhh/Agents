#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
PDF帮助类 - 负责处理PDF文件，包括文本提取和OCR识别
"""
import os
import tempfile
import fitz
import pypdf
import numpy as np
import cv2
import api.app.config as config
from api.tools.image_untils import convert_image_to_text

class PDFProcessor:
    """PDF处理器类"""
    
    def __init__(self):
        """初始化PDF处理器"""
        #self.ocr_handler = OCRHandler()
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
            return self.extract_scanned_pdf_by_pages(file_path,page_num)
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
    
    def extract_text_from_scanned_pdf(self, file_path: str) -> str:
        """
        从扫描PDF中提取所有文本（使用easyOCR）
        
        Args:
            file_path: PDF文件路径
            
        Returns:
            OCR识别的文本
        """
        text = ""
        try:
            # 打开PDF文件
            doc = fitz.open(file_path)
            # 将PDF转换为图像
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                # 保留原始分辨率，不放大。fitz.Matrix(2,2)是放大
                pix = page.get_pixmap(matrix=fitz.Matrix(4,4))
        
                # 创建临时文件名
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.png',    dir=config.TEMP_FILE_CONFIG["temp_dir"])
                temp_img_path = temp_file.name
                temp_file.close()
                # 保存图像到临时文件
                pix.save(temp_img_path)
                
                text += convert_image_to_text(temp_img_path)
                
                # 删除临时文件
                os.remove(temp_img_path)

            # 关闭文档释放资源
            doc.close()
             
            return text
        except Exception as e:
            print(f"OCR处理扫描PDF时出错: {str(e)}")
            return ""
    
    def is_scanned_pdf(self, file_path: str) -> bool:
        """
        检测PDF是否为扫描件
        
        Args:
            file_path: PDF文件路径
            
        Returns:
            如果是扫描件返回True，否则返回False
        """
        try:
            # 打开PDF
            with open(file_path, 'rb') as file:
                pdf_reader = pypdf.PdfReader(file)
                
                # 如果PDF没有页面，返回False
                if len(pdf_reader.pages) == 0:
                    return False
                
                # 取样前10页或所有页面（取较小值）
                num_pages_to_check = min(10, len(pdf_reader.pages))
                text_length = 0
                
                # 检查前几页的文本长度
                for page_num in range(num_pages_to_check):
                    page = pdf_reader.pages[page_num]
                    page_text = page.extract_text()
                    text_length += len(page_text)
                
                # 计算平均每页文本长度
                avg_text_per_page = text_length / num_pages_to_check
                
                # 如果平均每页文本长度低于阈值，认为是扫描件
                threshold = 100  # 可根据需要调整阈值
                return avg_text_per_page < threshold
        except Exception as e:
            print(f"检测PDF类型时出错: {str(e)}")
            # 出错时默认作为扫描件处理
            return True
    
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
    def extract_scanned_pdf_by_pages(self, file_path: str,page_num: int) -> str:
        """
        处理扫描PDF，使用OCR识别每页内容
        
        Args:
            file_path: PDF文件路径
            
        Returns:
            列表，每个元素为元组 (页内容, 元数据)
        """
        text = ""
        try:
            # 打开PDF文件
            doc =fitz .open(file_path)
            #检查页数不能大于文档最大页数
            if page_num > len(doc):
                page_num = len(doc)
            # 将PDF转换为图像
            for page_num in range(page_num):
                page = doc.load_page(page_num)
                # 保留原始分辨率，不放大。fitz.Matrix(2,2)是放大
                pix = page.get_pixmap(matrix=fitz.Matrix(4,4))
        
                # 创建临时文件名
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.png',    dir=config.TEMP_FILE_CONFIG["temp_dir"])
                temp_img_path = temp_file.name
                temp_file.close()
                # 保存图像到临时文件
                pix.save(temp_img_path)
                
                text += convert_image_to_text(temp_img_path)
                
                # 删除临时文件
                os.remove(temp_img_path)
            # 关闭文档释放资源
            doc.close()
             
            return text
        except Exception as e:
            print(f"OCR处理扫描PDF时出错: {str(e)}")
            return ""
    def correct_skew(self,image_path: str) -> np.ndarray:
        '''
        矫正图像倾斜
        Args:
            image_path: 图像路径
        Returns:
            矫正后的图像
        '''
        # 读取图像
        image = cv2.imread(image_path)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    
        # 二值化处理
        _, binary = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY_INV)
    
        # 查找轮廓
        coords = np.column_stack(np.where(binary > 0))
        angle = cv2.minAreaRect(coords)[-1]
    
        # 计算旋转角度
        if angle < -45:
            angle = -(90 + angle)
        else:
            angle = -angle
    
        # 旋转图像
        (h, w) = image.shape[:2]
        center = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(center, angle, 1.0)
        rotated = cv2.warpAffine(image, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    
        return rotated
if __name__ == "__main__":
    pdf_processor = PDFProcessor()
    print(pdf_processor.read_pdf(r"E:\laboratory\AI\AIagent_env\api\data\documents\辽宁消应特种装备成交确认书.PDF"))

