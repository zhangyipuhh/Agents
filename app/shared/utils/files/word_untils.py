"""
Word处理助手 - 负责处理Word文档，包括读取和修改
"""
import os
from pathlib import Path
from typing import Dict, List, Optional, Any, Union, Tuple
import io
import re

import docx
from docx import Document
from docx.shared import RGBColor
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from app.core.config.config import WORD_OUTPUT_CONFIG

class WordProcessor:
    """Word处理器类"""
    
    def __init__(self):
        """初始化Word处理器"""
        pass
    def read_contract_word(self, file_path: str,pattern:str,pattern_replace: str) -> Tuple[str,dict]:
        """
        专门读取制式合同Word文档内容，合同格式固定且没有表格，如果有表格这个暂时搞不定
        
        Args:
            file_path: Word文档路径
            pattern: 要替换的文本
            pattern_replace: 替换后的文本
        Returns:
            文档文本内容,段落数据
        """
        try:
            doc = Document(file_path)
            full_text = []
            
            # 提取段落文本，在提取段落文本时，如果is_replace_words为True，则替换文本
            #每个段落标记一个序号，生成一个字典
            '''
            格式示例
            [
                {
                    "paragraph_type": "标题",#第几条款,比如1、2、3、4
                    "paragraph_num": 1,#段落的实际索引
                    "paragraph_text": "段落1文本"
                },
                {
                    "paragraph_type": "正文",#第几条款
                    "paragraph_num": 2,#段落的实际索引
                    "paragraph_text": "段落2文本"
                }
            ]
            '''
            _index = 0
            _paragraph_data = []
            _tmp_match = ""#比如都是第四条，type都写一样的，直到遇到新的条款
            #为空的行不记录，但是index会加1
            _tmp_index = 0#条款索引
            for para in doc.paragraphs:
                #para.text = para.text.replace(" ", "")
                para.text = re.sub(pattern,pattern_replace,para.text)
                full_text.append(para.text)
                _is_match = re.match(pattern, para.text)
                if _is_match:
                    _tmp_index += 1
                if para.text.strip():
                    
                    _paragraph_data.append({
                        "paragraph_type":_tmp_index,
                        "paragraph_num": _index,
                        "paragraph_text": para.text
                    })
                    _index += 1
                else:
                    _index += 1
            # 提取表格文本
            for table in doc.tables:
                for row in table.rows:
                    row_text = []
                    for cell in row.cells:
                        row_text.append(cell.text)
                    full_text.append(" | ".join(row_text))
            
            return "\n".join(full_text),_paragraph_data
        except Exception as e:
            print(f"读取Word文档时出错: {str(e)}")
            return ""
    def read_word(self, file_path: str,is_replace_words: bool = False,pattern: str = None,pattern_replace: str = None) -> str:
        """
        读取Word文档内容
        
        Args:
            file_path: Word文档路径
            is_replace_words: 是否替换文本
            pattern: 要替换的文本
            pattern_replace: 替换后的文本
        Returns:
            文档文本内容
        """
        try:
            doc = Document(file_path)
            full_text = []
            
            # 提取段落文本
            for para in doc.paragraphs:
                if is_replace_words and pattern and pattern_replace:
                    para.text = re.sub(pattern,pattern_replace,para.text)
                full_text.append(para.text)
            
            # 提取表格文本
            for table in doc.tables:
                for row in table.rows:
                    row_text = []
                    for cell in row.cells:
                        row_text.append(cell.text)
                    full_text.append(" | ".join(row_text))
            
            return "\n".join(full_text)
        except Exception as e:
            print(f"读取Word文档时出错: {str(e)}")
            return ""
    def read_word_by_paragraphs(self, file_path: str,paragraph_num: int) -> str:
        """
        读取Word文档内容
        
        Args:
            file_path: Word文档路径
            
        Returns:
            文档文本内容
        """
        try:
            doc = Document(file_path)
            full_text = []
            index = 0
            # 提取段落文本
            for para in doc.paragraphs :
                if para.text.strip() == "":
                    continue
                if index > paragraph_num:
                    break
                full_text.append(para.text)
                index += 1
            
            
            
            return "\n".join(full_text)
        except Exception as e:
            print(f"读取Word文档时出错: {str(e)}")
            return ""

    def highlight_text(self, doc_path: str, text_to_highlight: str, output_path: str = None) -> str:
        """
        在Word文档中高亮指定文本
        
        Args:
            doc_path: Word文档路径
            text_to_highlight: 要高亮的文本
            output_path: 输出文档路径，如果为None则使用默认路径
            
        Returns:
            输出文档的路径
        """
        if output_path is None:
            # 创建输出目录
            os.makedirs(WORD_OUTPUT_CONFIG["output_dir"], exist_ok=True)
            
            # 生成输出文件名
            file_name = os.path.basename(doc_path)
            base_name, ext = os.path.splitext(file_name)
            output_path = os.path.join(WORD_OUTPUT_CONFIG["output_dir"], f"{base_name}_标记{ext}")
        
        try:
            # 加载文档
            doc = Document(doc_path)
            
            # 高亮颜色
            highlight_color = WORD_OUTPUT_CONFIG["highlight_color"]
            color = RGBColor.from_string(highlight_color)
            
            # 编译正则表达式用于匹配文本
            pattern = re.compile(re.escape(text_to_highlight), re.IGNORECASE)
            
            # 遍历段落并高亮匹配文本
            for paragraph in doc.paragraphs:
                text = paragraph.text
                if text_to_highlight in text:
                    # 查找所有匹配项的位置
                    matches = list(pattern.finditer(text))
                    
                    if matches:
                        # 重建段落的文本运行(runs)，确保每个匹配项都在单独的运行中
                        runs = []
                        last_end = 0
                        
                        for match in matches:
                            start, end = match.span()
                            
                            # 添加匹配前的文本
                            if start > last_end:
                                runs.append((text[last_end:start], False))
                            
                            # 添加高亮文本
                            runs.append((text[start:end], True))
                            
                            last_end = end
                        
                        # 添加最后一个匹配后的文本
                        if last_end < len(text):
                            runs.append((text[last_end:], False))
                        
                        # 清除原有的运行并添加新运行
                        for run in paragraph.runs:
                            run.clear()
                        
                        paragraph.clear()
                        for run_text, highlight in runs:
                            run = paragraph.add_run(run_text)
                            if highlight:
                                run.font.color.rgb = color
            
            # 遍历表格单元格并高亮匹配文本
            for table in doc.tables:
                for row in table.rows:
                    for cell in row.cells:
                        for paragraph in cell.paragraphs:
                            text = paragraph.text
                            if text_to_highlight in text:
                                # 查找所有匹配项的位置
                                matches = list(pattern.finditer(text))
                                
                                if matches:
                                    # 重建段落的文本运行
                                    runs = []
                                    last_end = 0
                                    
                                    for match in matches:
                                        start, end = match.span()
                                        
                                        # 添加匹配前的文本
                                        if start > last_end:
                                            runs.append((text[last_end:start], False))
                                        
                                        # 添加高亮文本
                                        runs.append((text[start:end], True))
                                        
                                        last_end = end
                                    
                                    # 添加最后一个匹配后的文本
                                    if last_end < len(text):
                                        runs.append((text[last_end:], False))
                                    
                                    # 清除原有的运行并添加新运行
                                    for run in paragraph.runs:
                                        run.clear()
                                    
                                    paragraph.clear()
                                    for run_text, highlight in runs:
                                        run = paragraph.add_run(run_text)
                                        if highlight:
                                            run.font.color.rgb = color
            
            # 保存文档
            doc.save(output_path)
            print(f"已将标记结果保存至: {output_path}")
            return output_path
        
        except Exception as e:
            print(f"高亮文本时出错: {str(e)}")
            return doc_path
    def highlight_text_without_changing_format(self, doc_path, text_to_find, color=(255, 0, 0), output_path=None, only_first_occurrence=False):
        """
        在Word文档中查找并高亮文本，保留原始格式
        
        参数:
            doc_path: Word文档路径
            text_to_find: 要查找的文本，可以是逗号分隔的多个文本
            color: RGB颜色元组，默认为红色 (255, 0, 0)，用于背景高亮
            output_path: 输出文档路径，如果为None则覆盖原文件
            only_first_occurrence: 是否只标记第一次出现的位置，默认为False
        """
        # 加载文档
        doc = Document(doc_path)
    
        color_hex = f"{color[0]:02x}{color[1]:02x}{color[2]:02x}"
        
        # 分割text_to_find为列表，处理可能的引号和空格问题
        texts_to_find = []
        for item in text_to_find.split(','):
            item = item.strip()
            # 移除可能的引号
            if (item.startswith('"') and item.endswith('"')) or (item.startswith("'") and item.endswith("'")):
                item = item[1:-1]
            if item:  # 确保不添加空字符串
                texts_to_find.append(item)
        
        # 删除可能的重复项
        texts_to_find = list(dict.fromkeys(texts_to_find))
        
        # 打印调试信息
        print(f"待标记的文本项: {texts_to_find}")
        
        # 全局计数器，记录每个待查找文本已标记的次数
        text_marked_count = {text: 0 for text in texts_to_find}
        
        # 定义应用高亮样式的函数
        def apply_highlighting_to_run(run, color_hex):
            """为一个run应用高亮样式"""
            try:
                rPr = run._r.get_or_add_rPr()
                
                # 删除现有的阴影元素
                for shd in rPr.findall(qn("w:shd")):
                    rPr.remove(shd)
                
                # 创建新的阴影元素
                shd = OxmlElement("w:shd")
                shd.set(qn("w:val"), "clear")
                shd.set(qn("w:color"), "auto")
                shd.set(qn("w:fill"), color_hex)
                rPr.append(shd)
                return True
            except Exception as e:
                print(f"应用高亮样式时出错: {str(e)}")
                return False
            
        # 检查一个run是否完全匹配查找文本
        def is_exact_match(run_text, text_to_highlight):
            return run_text == text_to_highlight
            
        # 查找段落中的文本并高亮
        def find_and_highlight_in_paragraph(paragraph, text_to_highlight):
            """在段落中查找文本并高亮，不改变段落结构"""
            if not text_to_highlight or not paragraph.text:
                return False
            
            # 快速检查：如果段落不包含要查找的文本，直接返回
            if text_to_highlight not in paragraph.text:
                return False
            
            # 检查是否已全局标记过且只需标记一次
            if only_first_occurrence and text_marked_count[text_to_highlight] > 0:
                return False
                
            highlighted = False
            
            # 检查每个run是否精确匹配查找文本
            for run in paragraph.runs:
                # 如果run文本精确匹配查找文本
                if is_exact_match(run.text, text_to_highlight):
                    if apply_highlighting_to_run(run, color_hex):
                        highlighted = True
                        text_marked_count[text_to_highlight] += 1
                        if only_first_occurrence:
                            return True
            
            # 如果没有精确匹配，则查找部分匹配
            if not highlighted:
                # 构建段落完整文本并定位每个run
                full_text = ""
                run_positions = []
                for i, run in enumerate(paragraph.runs):
                    start_pos = len(full_text)
                    full_text += run.text
                    end_pos = len(full_text)
                    run_positions.append((start_pos, end_pos, run))
                
                # 查找所有匹配位置
                start_idx = 0
                while True:
                    idx = full_text.find(text_to_highlight, start_idx)
                    if idx == -1:
                        break
                        
                    # 找出哪些run包含这个匹配
                    match_end = idx + len(text_to_highlight)
                    matching_runs = []
                    
                    for start_pos, end_pos, run in run_positions:
                        # 如果run与匹配区域有重叠
                        if not (end_pos <= idx or start_pos >= match_end):
                            matching_runs.append(run)
                    
                    # 如果匹配横跨多个run，或者匹配只是run的一部分
                    if matching_runs:
                        for run in matching_runs:
                            if apply_highlighting_to_run(run, color_hex):
                                highlighted = True
                        
                        if highlighted:
                            text_marked_count[text_to_highlight] += 1
                            if only_first_occurrence:
                                return True
                    
                    start_idx = idx + 1  # 继续搜索下一个匹配项
            
            return highlighted
        
        # 收集所有段落（主文档和表格）
        all_paragraphs = []
        
        # 收集主文档段落
        for paragraph in doc.paragraphs:
            all_paragraphs.append(paragraph)
        
        # 收集表格段落
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for paragraph in cell.paragraphs:
                        all_paragraphs.append(paragraph)
        
        # 处理每个要查找的文本
        for text_to_find in texts_to_find:
            # 重置计数器
            text_marked_count[text_to_find] = 0
            
            # 处理所有段落
            for paragraph in all_paragraphs:
                try:
                    # 如果已经标记过且只需标记一次，则跳过
                    if only_first_occurrence and text_marked_count[text_to_find] > 0:
                        break
                        
                    find_and_highlight_in_paragraph(paragraph, text_to_find)
                except Exception as e:
                    print(f"处理段落时出错: {str(e)}")
                    continue
        
        # 保存文档
        try:
            if output_path:
                doc.save(output_path)
            else:
                doc.save(doc_path)
            
            return output_path if output_path else doc_path
        except Exception as e:
            print(f"保存文档时出错: {str(e)}")
            return doc_path

    def highlight_text_in_specific_paragraph(
        self, 
        doc_path: str, 
        text_to_find: Union[str, List[str]], 
        paragraph_indices: Union[int, List[int]], 
        color: Tuple[int, int, int] = (255, 0, 0), 
        output_path: str = None
    ) -> str:
        """
        在Word文档的指定段落中批量标记特定文本，文本和段落一一对应
        
        Args:
            doc_path: Word文档路径
            text_to_find: 要标记的文本，可以是单个字符串或字符串列表
            paragraph_indices: 要标记的段落索引（从0开始），可以是单个整数或整数列表，
                             必须与text_to_find一一对应
            color: RGB颜色元组，默认为红色 (255, 0, 0)
            output_path: 输出文档路径，如果为None则覆盖原文件
            
        Returns:
            输出文档的路径
            
        Examples:
            # 单个文本和段落
            processor.highlight_text_in_specific_paragraph("doc.docx", "要标记的文本", 1)
            
            # 多个文本在对应的段落（一一对应）
            processor.highlight_text_in_specific_paragraph(
                "doc.docx", 
                ["文本1", "文本2"], # 文本1在第1段，文本2在第2段
                [1, 2]
            )
        """
        try:
            # 加载文档
            doc = Document(doc_path)
            
            # 转换颜色为十六进制
            color_hex = f"{color[0]:02x}{color[1]:02x}{color[2]:02x}"
            
            # 将输入转换为列表形式
            texts = [text_to_find] if isinstance(text_to_find, str) else text_to_find
            indices = [paragraph_indices] if isinstance(paragraph_indices, int) else paragraph_indices
            
            # 参数验证
            if not texts or not indices:
                print("文本列表或段落索引列表不能为空")
                return doc_path
                
            # 确保文本和段落索引数量相同
            if len(texts) != len(indices):
                print(f"文本数量({len(texts)})与段落索引数量({len(indices)})不匹配")
                return doc_path
                
            # 验证段落索引的有效性，如果超出范围会提醒
            total_paragraphs = len(doc.paragraphs)
            # 检查每个段落索引数组中的索引是否有效
            invalid_indices = []
            for idx_array in indices:
                # 如果是单个索引,转换为列表方便统一处理
                if isinstance(idx_array, int):
                    idx_array = [idx_array]
                    
                # 检查数组中每个索引的有效性
                for idx in idx_array:
                    if idx < 0 or idx >= total_paragraphs:
                        invalid_indices.append(idx)
            #invalid_indices = [idx for idx in indices if idx < 0 or idx >= total_paragraphs]
            if invalid_indices:
                print(f"发现无效的段落索引 {invalid_indices}。文档共有 {total_paragraphs} 个段落")
                return doc_path
            
            # 对每对文本和段落进行处理
            for text,para_idx in zip(texts,indices):
                # 构建段落完整文本并定位每个run
                full_text = ""
                run_positions = []
                
                #将整个条款都拼到一起
                for para_idx_tmp in para_idx:
                    paragraph = doc.paragraphs[para_idx_tmp]
                    for run in paragraph.runs:
                        start_pos = len(full_text)
                        full_text += run.text
                        end_pos = len(full_text)
                        run_positions.append((start_pos, end_pos, run))
                
                
                
                # 如果段落中不包含目标文本，跳过此段落
                if text not in full_text:
                    #如果没有尝试去掉左右空格，因为原文档如果不标准，会存在大量空格
                    if text.replace(" ", "") not in full_text.replace(" ", ""):
                        print(f"未找到文本: {text}")
                        continue
                    
                # 查找所有匹配位置
                start_idx = 0
                while True:
                    idx = full_text.find(text, start_idx)
                    if idx == -1:
                        #去掉空格后要进行一定偏移
                        idx = full_text.replace(" ", "").find(text.replace(" ", ""), start_idx)
                        
                        if idx == -1:
                            #print(f"未找到文本: {text}, 尝试去掉空格后未找到")
                            break
                        else:
                            idx = idx+3
                    
                    # 找出哪些run包含这个匹配
                    match_end = idx + len(text)
                    matching_runs = []
                    
                    for start_pos, end_pos, run in run_positions:
                        # 如果run与匹配区域有重叠
                        if not (end_pos <= idx or start_pos >= match_end):
                            matching_runs.append(run)
                    
                    # 为匹配的runs应用高亮样式
                    for run in matching_runs:
                        rPr = run._r.get_or_add_rPr()
                        
                        # 删除现有的阴影元素
                        for shd in rPr.findall(qn("w:shd")):
                            rPr.remove(shd)
                        
                        # 创建新的阴影元素
                        shd = OxmlElement("w:shd")
                        shd.set(qn("w:val"), "clear")
                        shd.set(qn("w:color"), "auto")
                        shd.set(qn("w:fill"), color_hex)
                        rPr.append(shd)
                    
                    start_idx = idx + 1  # 继续搜索下一个匹配项
            
            # 保存文档
            save_path = output_path if output_path else doc_path
            doc.save(save_path)
            print(f"文档已保存至: {save_path}")
            return save_path
            
        except Exception as e:
            print(f"标记文本时出错: {str(e)}")
            return doc_path

if __name__ == "__main__":
    word_processor = WordProcessor()
    
    #替换文本测试
    contract_text,paragraph_data = word_processor.read_contract_word(r"D:\DocumentLoader\WordLoader.docx",r'^\s*(第[\u4e00-\u9fa5\d]+条)',r'\1条款')
    print(contract_text)
    print(paragraph_data)
    #添加标记测试
    word_processor.highlight_text_in_specific_paragraph(r"WordLoader.docx", ["210113005010GB90004","本合同","本合同"],[45,46,47], (255, 0, 0), r"D:\DocumentLoader\WordLoader——1mark.docx")
    #添加标记测试
