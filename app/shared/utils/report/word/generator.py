from docx import Document
from docx.shared import Pt, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
import re
from typing import Callable

from app.shared.utils.report.word.config import ReportConfig, SectionConfig


def set_chinese_font(run, font_name="宋体", font_size=12, bold=False):
    """
    设置中文字体的辅助函数

    Args:
        run: python-docx的Run对象，用于设置文本格式
        font_name: 字体名称，默认为"宋体"
        font_size: 字体大小（磅值），默认为12
        bold: 是否加粗，默认为False

    Returns:
        无返回值，直接修改run对象的字体属性
    """
    run.font.name = font_name
    run._element.rPr.rFonts.set(qn('w:eastAsia'), font_name)
    run.font.size = Pt(font_size)
    run.font.bold = bold


class WordReportGenerator:
    """
    Word报告通用生成器

    通过ReportConfig配置对象驱动生成Word文档，支持封面、目录、
    多级标题、正文段落、分页等元素的灵活组合。
    """

    def __init__(self, config: ReportConfig):
        """
        初始化报告生成器

        Args:
            config: ReportConfig配置对象，定义报告的结构和内容
        """
        self.config = config
        self.doc = None

    def _setup_page(self):
        """
        设置页面尺寸和边距

        根据ReportConfig中page_setup的配置，设置文档的页面宽度、高度和四边边距。

        Notes:
            - 所有尺寸单位为厘米(cm)，通过Cm()转换为docx内部单位
            - 修改文档第一个section的页面参数
        """
        ps = self.config.page_setup
        section = self.doc.sections[0]
        section.page_width = Cm(ps.page_width)
        section.page_height = Cm(ps.page_height)
        section.top_margin = Cm(ps.top_margin)
        section.bottom_margin = Cm(ps.bottom_margin)
        section.left_margin = Cm(ps.left_margin)
        section.right_margin = Cm(ps.right_margin)

    def _setup_default_style(self):
        """
        设置默认字体样式

        将文档Normal样式的字体设置为config中指定的默认字体名称和大小，
        同时设置东亚字体(w:eastAsia)以确保中文字符正确显示。

        Notes:
            - 修改Normal样式会影响文档中所有未单独指定字体的段落
            - rPr.rFonts.set(qn('w:eastAsia'), ...) 用于设置东亚文字字体
        """
        style = self.doc.styles['Normal']
        style.font.name = self.config.default_font_name
        style._element.rPr.rFonts.set(qn('w:eastAsia'), self.config.default_font_name)
        style.font.size = Pt(self.config.default_font_size)

    def _resolve_text(self, content):
        """
        解析文本内容，支持变量替换和可调用对象

        Args:
            content: 文本内容，可以是字符串（支持{{变量名}}占位符）或可调用对象

        Returns:
            str: 解析后的文本内容

        Notes:
            - 字符串中的{{变量名}}会被config.data中对应的值替换
            - 可调用对象会被调用，传入config.data作为参数，返回值作为文本
            - 如果content为None，返回空字符串
        """
        if callable(content):
            return str(content(self.config.data))
        if isinstance(content, str) and self.config.data:
            def replace_var(match):
                var_name = match.group(1)
                return str(self.config.data.get(var_name, match.group(0)))
            return re.sub(r'\{\{(.+?)\}\}', replace_var, content)
        return str(content) if content is not None else ""

    def _render_cover(self):
        """
        渲染封面页

        根据CoverConfig配置生成封面，包含附件编号、标题、副标题、日期等元素。
        封面结束后自动添加分页符。

        Notes:
            - 附件编号：右对齐显示
            - 标题：居中显示，使用封面专用字体和字号
            - 副标题：居中显示
            - 日期：居中显示
            - 各元素之间通过blank_lines配置控制空行数量
            - 如果cover配置为None，则跳过封面渲染
        """
        cover = self.config.cover
        if not cover:
            return

        # 附件编号（右对齐）
        if cover.attachment_no:
            p = self.doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            run = p.add_run(self._resolve_text(cover.attachment_no))
            set_chinese_font(run, self.config.default_font_name, self.config.default_font_size)

        # 标题前空行
        for _ in range(cover.blank_lines_before_title):
            self.doc.add_paragraph()

        # 主标题（居中）
        if cover.title:
            p = self.doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = p.add_run(self._resolve_text(cover.title))
            set_chinese_font(run, cover.title_font_name, cover.title_font_size, cover.title_bold)

        # 标题后空行
        for _ in range(cover.blank_lines_after_title):
            self.doc.add_paragraph()

        # 副标题（居中）
        if cover.subtitle:
            p = self.doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = p.add_run(self._resolve_text(cover.subtitle))
            set_chinese_font(run, cover.subtitle_font_name, cover.subtitle_font_size)

        # 日期前空行
        for _ in range(cover.blank_lines_before_date):
            self.doc.add_paragraph()

        # 日期（居中）
        if cover.date_text:
            p = self.doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = p.add_run(self._resolve_text(cover.date_text))
            set_chinese_font(run, cover.date_font_name, cover.date_font_size)

        # 封面结束分页
        self.doc.add_page_break()

    def _render_toc(self):
        """
        渲染目录页

        根据TocConfig配置生成目录，支持多级缩进。
        目录结束后自动添加分页符。

        Notes:
            - 目录标题：居中显示，使用目录专用字体和字号
            - 目录条目：根据level级别设置左缩进，实现层级效果
            - 缩进量 = indent_per_level * level（单位cm）
            - 如果toc配置为None，则跳过目录渲染
        """
        toc = self.config.toc
        if not toc:
            return

        # 目录标题（居中）
        p = self.doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run(toc.title)
        set_chinese_font(run, toc.title_font_name, toc.title_font_size, toc.title_bold)

        # 空行
        self.doc.add_paragraph()

        # 目录条目
        for entry in toc.entries:
            p = self.doc.add_paragraph()
            run = p.add_run(self._resolve_text(entry.text))
            set_chinese_font(run, toc.entry_font_name, toc.entry_font_size)
            p.paragraph_format.left_indent = Cm(toc.indent_per_level * entry.level)

        # 目录结束分页
        self.doc.add_page_break()

    def _render_heading(self, section: SectionConfig):
        """
        渲染标题段落

        Args:
            section: SectionConfig配置对象，包含标题的级别、文本和样式信息

        Notes:
            - 一级标题(level=1)：上边距12pt，下边距6pt
            - 二级标题(level=2)：左缩进0.74cm，上边距9pt，下边距5pt
            - 三级标题(level=3)：左缩进1.48cm，上边距6pt，下边距3pt
            - 默认字体为黑体，默认加粗
            - 默认字号：一级14pt，二级13pt，三级12pt
            - 可通过SectionConfig中的字段覆盖默认值
        """
        level = section.level
        text = self._resolve_text(section.content)

        font_name = section.font_name or "黑体"
        font_size = section.font_size or {1: 14, 2: 13, 3: 12}.get(level, 14)
        bold = section.bold if section.bold is not None else True

        paragraph = self.doc.add_paragraph()
        run = paragraph.add_run(text)
        set_chinese_font(run, font_name, font_size, bold)

        # 段前间距
        space_before = section.space_before if section.space_before is not None else {1: 12, 2: 9, 3: 6}.get(level, 12)
        paragraph.paragraph_format.space_before = Pt(space_before)

        # 段后间距
        space_after = section.space_after if section.space_after is not None else {1: 6, 2: 5, 3: 3}.get(level, 6)
        paragraph.paragraph_format.space_after = Pt(space_after)

        # 左缩进
        left_indent = section.left_indent if section.left_indent is not None else {1: 0, 2: 0.74, 3: 1.48}.get(level, 0)
        if left_indent:
            paragraph.paragraph_format.left_indent = Cm(left_indent)

        # 对齐方式
        if section.alignment is not None:
            paragraph.alignment = section.alignment

    def _render_paragraph(self, section: SectionConfig):
        """
        渲染正文段落

        Args:
            section: SectionConfig配置对象，包含段落的文本和样式信息

        Notes:
            - 默认首行缩进0.74cm（约2个中文字符）
            - 默认行距1.5倍
            - 默认左对齐
            - 默认不加粗
            - 可通过SectionConfig中的字段覆盖默认值
        """
        text = self._resolve_text(section.content)

        font_name = section.font_name or self.config.default_font_name
        font_size = section.font_size or self.config.default_font_size
        bold = section.bold if section.bold is not None else False

        paragraph = self.doc.add_paragraph()
        run = paragraph.add_run(text)
        set_chinese_font(run, font_name, font_size, bold)

        # 对齐方式
        if section.alignment is not None:
            paragraph.alignment = section.alignment
        else:
            paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT

        # 首行缩进
        first_indent = section.first_line_indent if section.first_line_indent is not None else True
        if first_indent:
            paragraph.paragraph_format.first_line_indent = Cm(0.74)

        # 行距
        paragraph.paragraph_format.line_spacing = section.line_spacing

        # 段前间距
        if section.space_before is not None:
            paragraph.paragraph_format.space_before = Pt(section.space_before)

        # 段后间距
        if section.space_after is not None:
            paragraph.paragraph_format.space_after = Pt(section.space_after)

        # 左缩进
        if section.left_indent is not None:
            paragraph.paragraph_format.left_indent = Cm(section.left_indent)

    def _render_page_break(self):
        """
        渲染分页符

        在当前位置插入一个分页符，后续内容将从新页面开始。

        Notes:
            - 分页符不会产生可见的段落内容
            - 常用于封面后、目录后等需要强制换页的场景
        """
        self.doc.add_page_break()

    def _render_section(self, section: SectionConfig):
        """
        根据段落类型分发渲染

        Args:
            section: SectionConfig配置对象

        Notes:
            根据 section_type 字段分发到对应的渲染方法：
            - "heading" -> _render_heading()
            - "paragraph" -> _render_paragraph()
            - "page_break" -> _render_page_break()
        """
        if section.section_type == "heading":
            self._render_heading(section)
        elif section.section_type == "paragraph":
            self._render_paragraph(section)
        elif section.section_type == "page_break":
            self._render_page_break()

    def generate(self) -> Document:
        """
        生成Word报告的主入口方法

        按顺序执行：创建文档 -> 页面设置 -> 默认样式 -> 封面 -> 目录 -> 正文段落

        Returns:
            Document: python-docx的Document对象，调用方可通过 doc.save() 保存为.docx文件

        Notes:
            - 每次调用generate()都会创建新的Document对象
            - 如果cover或toc配置为None，对应部分会被跳过
            - sections列表中的每个SectionConfig按顺序依次渲染
        """
        self.doc = Document()
        self._setup_page()
        self._setup_default_style()
        self._render_cover()
        self._render_toc()

        for section in self.config.sections:
            self._render_section(section)

        return self.doc

    def save(self, file_path: str):
        """
        保存Word文档到指定路径

        Args:
            file_path: 输出文件路径，如 "output/report.docx"

        Raises:
            ValueError: 如果尚未调用 generate() 生成文档

        Notes:
            - 调用前必须先调用generate()方法生成文档
            - 文件路径的目录必须存在，否则会抛出异常
            - 文件格式为.docx（Office Open XML格式）
        """
        if self.doc is None:
            raise ValueError("请先调用 generate() 方法生成文档")
        self.doc.save(file_path)
