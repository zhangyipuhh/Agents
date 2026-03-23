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

    def mark_contract_dynamic_values(
        self,
        doc_path: str,
        marking_rules: List[Dict[str, Any]],
        output_path: str = None
    ) -> str:
        """
        根据标记规则自动识别并标记合同中的动态值
        
        Args:
            doc_path: Word文档路径
            marking_rules: 标记规则列表，每个规则包含：
                - clause_pattern: 条款编号模式（如"第六条"、"第五条"）
                - prefix_pattern: 动态值前缀
                - suffix_pattern: 动态值后缀（可选）
                - color: RGB颜色元组
            output_path: 输出文档路径，如果为None则覆盖原文件
        
        Returns:
            输出文档的路径
        
        Raises:
            IOError: 文件操作失败时抛出
            ValueError: 参数验证失败时抛出
        
        Examples:
            marking_rules = [
                {
                    "clause_pattern": "第六条",
                    "prefix_pattern": "用途为",
                    "suffix_pattern": None,
                    "color": (255, 0, 0)
                },
                {
                    "clause_pattern": "第五条",
                    "prefix_pattern": "大写",
                    "suffix_pattern": "（小写",
                    "color": (255, 0, 0)
                }
            ]
            processor.mark_contract_dynamic_values("contract.docx", marking_rules)
        """
        # 参数验证：确保文档路径存在
        if not os.path.exists(doc_path):
            raise IOError(f"文档路径不存在: {doc_path}")
        
        # 参数验证：确保标记规则不为空
        if not marking_rules:
            raise ValueError("标记规则不能为空")
        
        try:
            # 加载文档
            doc = Document(doc_path)
            
            # 处理每条标记规则
            for rule in marking_rules:
                clause_pattern = rule.get("clause_pattern")
                prefix_pattern = rule.get("prefix_pattern")
                suffix_pattern = rule.get("suffix_pattern")
                color = rule.get("color", (255, 0, 0))
                
                # 验证规则必要字段
                if not clause_pattern or not prefix_pattern:
                    print(f"警告: 规则缺少必要字段，跳过该规则: {rule}")
                    continue
                
                # 转换颜色为十六进制格式
                color_hex = f"{color[0]:02x}{color[1]:02x}{color[2]:02x}"
                
                # 查找条款所在的段落索引
                clause_paragraph_indices = self._find_clause_paragraphs(doc, clause_pattern)
                
                # 如果未找到条款，记录警告并跳过
                if not clause_paragraph_indices:
                    print(f"警告: 未找到条款 '{clause_pattern}'，跳过该规则")
                    continue
                
                # 在条款段落中标记动态值
                self._mark_dynamic_value_in_clause(
                    doc, clause_paragraph_indices, prefix_pattern, suffix_pattern, color_hex
                )
            
            # 确定保存路径
            save_path = output_path if output_path else doc_path
            
            # 保存文档
            doc.save(save_path)
            print(f"文档已保存至: {save_path}")
            return save_path
            
        except Exception as e:
            raise IOError(f"处理文档时出错: {str(e)}")
    
    def _find_clause_paragraphs(self, doc: Document, clause_pattern: str) -> List[int]:
        """
        查找包含指定条款编号的所有段落索引
        
        Args:
            doc: Document对象
            clause_pattern: 条款编号模式（如"第六条"）
        
        Returns:
            包含该条款的段落索引列表
        
        Note:
            条款可能跨越多个段落，此方法返回从条款开始到下一个条款之间的所有段落索引
        """
        clause_indices = []
        found_clause = False
        
        clause_regex = re.compile(clause_pattern)
        next_clause_regex = re.compile(r'第[\u4e00-\u9fa5\d]+条')
        
        for i, paragraph in enumerate(doc.paragraphs):
            if found_clause:
                if next_clause_regex.search(paragraph.text) and not clause_regex.search(paragraph.text):
                    break
                clause_indices.append(i)
            elif clause_regex.search(paragraph.text):
                found_clause = True
                clause_indices.append(i)
        
        return clause_indices
    
    def _mark_dynamic_value_in_clause(
        self,
        doc: Document,
        clause_paragraph_indices: List[int],
        prefix_pattern: str,
        suffix_pattern: Optional[str],
        color_hex: str
    ) -> bool:
        """
        在指定条款段落中标记动态值
        
        Args:
            doc: Document对象
            clause_paragraph_indices: 条款段落索引列表
            prefix_pattern: 动态值前缀
            suffix_pattern: 动态值后缀（可选）
            color_hex: 十六进制颜色值
        
        Returns:
            是否成功标记
        """
        for para_idx in clause_paragraph_indices:
            paragraph = doc.paragraphs[para_idx]
            para_text = paragraph.text
            
            if prefix_pattern not in para_text and prefix_pattern.replace(" ", "") not in para_text.replace(" ", ""):
                continue
            
            full_text = ""
            run_positions = []
            
            for run in paragraph.runs:
                start_pos = len(full_text)
                full_text += run.text
                end_pos = len(full_text)
                run_positions.append((start_pos, end_pos, run))
            
            prefix_idx = full_text.find(prefix_pattern)
            if prefix_idx == -1:
                prefix_idx = full_text.replace(" ", "").find(prefix_pattern.replace(" ", ""))
                if prefix_idx == -1:
                    continue
                space_count_before = full_text[:prefix_idx + 3].count(" ") - prefix_pattern[:3].count(" ")
                prefix_idx = prefix_idx + space_count_before
            
            dynamic_value_start = prefix_idx + len(prefix_pattern)
            
            if suffix_pattern:
                suffix_idx = full_text.find(suffix_pattern, dynamic_value_start)
                if suffix_idx == -1:
                    text_after_prefix = full_text[dynamic_value_start:]
                    suffix_idx_in_sub = text_after_prefix.replace(" ", "").find(suffix_pattern.replace(" ", ""))
                    if suffix_idx_in_sub == -1:
                        print(f"警告: 在段落{para_idx}中未找到后缀 '{suffix_pattern}'")
                        continue
                    space_count = text_after_prefix[:suffix_idx_in_sub].count(" ")
                    suffix_idx = dynamic_value_start + suffix_idx_in_sub + space_count
                
                dynamic_value_end = suffix_idx
            else:
                dynamic_value_end = len(full_text)
            
            dynamic_value = full_text[dynamic_value_start:dynamic_value_end].strip()
            if not dynamic_value:
                print(f"警告: 动态值为空，前缀 '{prefix_pattern}'")
                continue
            
            print(f"识别到动态值: '{dynamic_value}'")
            
            # 收集需要处理的runs（与动态值范围有重叠的）
            para_runs_to_process = []
            for run_start, run_end, run in run_positions:
                if not (run_end <= dynamic_value_start or run_start >= dynamic_value_end):
                    para_runs_to_process.append((run_start, run_end, run))
            
            if not para_runs_to_process:
                continue
            
            # 获取原始格式
            original_font = None
            original_size = None
            original_bold = None
            original_italic = None
            original_underline = None
            
            if para_runs_to_process:
                first_run = para_runs_to_process[0][2]
                if first_run.font:
                    original_font = first_run.font.name
                    original_size = first_run.font.size
                    original_bold = first_run.font.bold
                    original_italic = first_run.font.italic
                    original_underline = first_run.font.underline
            
            # 按原始顺序重建段落，保持正确的文本顺序
            paragraph.clear()
            
            for run_start, run_end, run in run_positions:
                text_in_run = run.text
                
                # 检查这个run是否需要处理（是否与动态值范围重叠）
                if run_end <= dynamic_value_start or run_start >= dynamic_value_end:
                    # 不需要处理，直接添加
                    new_run = paragraph.add_run(text_in_run)
                else:
                    # 需要处理，分割文本
                    rel_start = max(0, dynamic_value_start - run_start)
                    rel_end = min(len(text_in_run), dynamic_value_end - run_start)
                    
                    # 添加动态值前的部分（不标记）
                    if rel_start > 0:
                        new_run = paragraph.add_run(text_in_run[:rel_start])
                        if run.font:
                            if run.font.name:
                                new_run.font.name = run.font.name
                            if run.font.size:
                                new_run.font.size = run.font.size
                            if run.font.bold is not None:
                                new_run.font.bold = run.font.bold
                            if run.font.italic is not None:
                                new_run.font.italic = run.font.italic
                            if run.font.underline is not None:
                                new_run.font.underline = run.font.underline
                    
                    # 添加动态值部分（标记）
                    if rel_end > rel_start:
                        new_run = paragraph.add_run(text_in_run[rel_start:rel_end])
                        if original_font:
                            new_run.font.name = original_font
                        if original_size:
                            new_run.font.size = original_size
                        if original_bold is not None:
                            new_run.font.bold = original_bold
                        if original_italic is not None:
                            new_run.font.italic = original_italic
                        if original_underline is not None:
                            new_run.font.underline = original_underline
                        new_run.font.color.rgb = RGBColor.from_string(color_hex)
                    
                    # 添加动态值后的部分（不标记）
                    if rel_end < len(text_in_run):
                        new_run = paragraph.add_run(text_in_run[rel_end:])
                        if run.font:
                            if run.font.name:
                                new_run.font.name = run.font.name
                            if run.font.size:
                                new_run.font.size = run.font.size
                            if run.font.bold is not None:
                                new_run.font.bold = run.font.bold
                            if run.font.italic is not None:
                                new_run.font.italic = run.font.italic
                            if run.font.underline is not None:
                                new_run.font.underline = run.font.underline
            
            print(f"已标记动态值: '{dynamic_value}'")
            return True
        
        print(f"警告: 在条款段落中未找到前缀 '{prefix_pattern}'")
        return False

if __name__ == "__main__":
    word_processor = WordProcessor()

    marking_rules = [
        {
            "clause_pattern": "第六条",
            "prefix_pattern": "用途为",
            "suffix_pattern": "。",
            "color": (255, 0, 0)
        },
        {
            "clause_pattern": "第五条",
            "prefix_pattern": "宗地总面积为大写",
            "suffix_pattern": "平方米",
            "color": (255, 0, 0)
        }
    ]

    result = word_processor.mark_contract_dynamic_values(
        r"C:\Users\54299\Desktop\新版国有建设用地使用权出让合同.docx",
        marking_rules,
        r"C:\Users\54299\Desktop\新版国有建设用地使用权出让合同_marked.docx"
    )
