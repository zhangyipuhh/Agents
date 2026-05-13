from docx import Document
from docx.shared import Pt, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.section import WD_SECTION_START
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
import re
from typing import Callable

from app.shared.utils.report.word.config import ReportConfig, SectionConfig, CoverElementConfig, FooterConfig


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
    多级标题、正文段落、分页等元素的灵活组合，支持自动生成目录页码和页脚页码。
    """

    def __init__(self, config: ReportConfig):
        """
        初始化报告生成器

        Args:
            config: ReportConfig配置对象，定义报告的结构和内容
        """
        self.config = config
        self.doc = None
        self._heading_bookmarks = []

    def _add_field_code(self, paragraph, field_code: str, font_name: str = "宋体", font_size: int = 10):
        """
        在段落中添加Word域字段代码

        Args:
            paragraph: python-docx的Paragraph对象，域字段将作为段落的直接子元素添加
            field_code: 域字段代码，如"PAGE"、"NUMPAGES"、"PAGEREF bookmark_name"
            font_name: 字体名称，默认"宋体"
            font_size: 字号，单位pt，默认10

        Notes:
            使用w:fldChar元素创建Word域字段，实现页码等自动计算功能。
            标准域字段结构：每个部分（begin/instrText/separate/display/end）
            作为独立的w:r元素直接添加到段落w:p中，避免w:r嵌套导致Word解析异常。

            正确的XML结构：
            <w:p>
              <w:r><w:rPr>...</w:rPr><w:fldChar type="begin"/></w:r>
              <w:r><w:rPr>...</w:rPr><w:instrText> PAGE </w:instrText></w:r>
              <w:r><w:rPr>...</w:rPr><w:fldChar type="separate"/></w:r>
              <w:r><w:rPr>...</w:rPr><w:t>1</w:t></w:r>
              <w:r><w:rPr>...</w:rPr><w:fldChar type="end"/></w:r>
            </w:p>
        """
        def _make_run():
            run = OxmlElement('w:r')
            rPr = OxmlElement('w:rPr')
            rFonts = OxmlElement('w:rFonts')
            rFonts.set(qn('w:ascii'), font_name)
            rFonts.set(qn('w:hAnsi'), font_name)
            rFonts.set(qn('w:eastAsia'), font_name)
            rPr.append(rFonts)
            sz = OxmlElement('w:sz')
            sz.set(qn('w:val'), str(font_size * 2))
            rPr.append(sz)
            szCs = OxmlElement('w:szCs')
            szCs.set(qn('w:val'), str(font_size * 2))
            rPr.append(szCs)
            run.append(rPr)
            return run

        run_begin = _make_run()
        fldChar_begin = OxmlElement('w:fldChar')
        fldChar_begin.set(qn('w:fldCharType'), 'begin')
        run_begin.append(fldChar_begin)
        paragraph._p.append(run_begin)

        run_instr = _make_run()
        instrText = OxmlElement('w:instrText')
        instrText.set(qn('xml:space'), 'preserve')
        instrText.text = f' {field_code} '
        run_instr.append(instrText)
        paragraph._p.append(run_instr)

        run_separate = _make_run()
        fldChar_separate = OxmlElement('w:fldChar')
        fldChar_separate.set(qn('w:fldCharType'), 'separate')
        run_separate.append(fldChar_separate)
        paragraph._p.append(run_separate)

        run_display = _make_run()
        display_t = OxmlElement('w:t')
        display_t.text = '1'
        run_display.append(display_t)
        paragraph._p.append(run_display)

        run_end = _make_run()
        fldChar_end = OxmlElement('w:fldChar')
        fldChar_end.set(qn('w:fldCharType'), 'end')
        run_end.append(fldChar_end)
        paragraph._p.append(run_end)

    def _add_bookmark(self, paragraph, bookmark_name: str):
        """
        为段落添加书签

        Args:
            paragraph: python-docx的Paragraph对象
            bookmark_name: 书签名称

        Returns:
            str: 书签名称

        Notes:
            使用w:bookmarkStart和w:bookmarkEnd元素创建Word书签
        """
        # 生成唯一书签ID
        bookmark_id = str(len(self._heading_bookmarks))
        self._heading_bookmarks.append(bookmark_name)

        # 创建bookmarkStart元素
        bookmark_start = OxmlElement('w:bookmarkStart')
        bookmark_start.set(qn('w:id'), bookmark_id)
        bookmark_start.set(qn('w:name'), bookmark_name)

        # 创建bookmarkEnd元素
        bookmark_end = OxmlElement('w:bookmarkEnd')
        bookmark_end.set(qn('w:id'), bookmark_id)

        # 添加到段落的首个run之前和最后一个run之后
        if paragraph._p.getchildren():
            first_run = paragraph._p.find(qn('w:r'))
            if first_run is not None:
                paragraph._p.insert(paragraph._p.index(first_run), bookmark_start)
            else:
                paragraph._p.append(bookmark_start)
        else:
            paragraph._p.append(bookmark_start)

        paragraph._p.append(bookmark_end)

        return bookmark_name

    def _setup_page(self):
        """
        设置页面尺寸和边距

        根据ReportConfig中page_setup的配置，设置文档所有节的页面宽度、高度和四边边距。

        Notes:
            - 所有尺寸单位为厘米(cm)，通过Cm()转换为docx内部单位
            - 遍历文档所有section，确保每个节的页面参数一致
        """
        ps = self.config.page_setup
        for section in self.doc.sections:
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

    def _render_cover_element(self, element: CoverElementConfig):
        """
        渲染单个封面元素

        Args:
            element: CoverElementConfig配置对象，包含文本、字体、对齐和间距信息

        Notes:
            - 根据alignment设置对齐方式（left/center/right）
            - 应用space_before和space_after控制段前段后行数
            - 使用指定的字体名称、大小和加粗样式
        """
        if not element or not element.text:
            return

        # 段前行数
        for _ in range(element.space_before):
            self.doc.add_paragraph()

        # 创建段落
        p = self.doc.add_paragraph()

        # 设置对齐方式
        alignment_map = {
            "left": WD_ALIGN_PARAGRAPH.LEFT,
            "center": WD_ALIGN_PARAGRAPH.CENTER,
            "right": WD_ALIGN_PARAGRAPH.RIGHT,
        }
        p.alignment = alignment_map.get(element.alignment, WD_ALIGN_PARAGRAPH.CENTER)

        # 添加文本
        run = p.add_run(self._resolve_text(element.text))
        set_chinese_font(run, element.font_name, element.font_size, element.bold)

        # 段后行数
        for _ in range(element.space_after):
            self.doc.add_paragraph()

    def _render_cover(self):
        """
        渲染封面页

        根据CoverConfig配置生成封面，包含附件编号、标题、副标题、日期等元素。
        封面结束后自动添加新节（分节符），使封面成为独立的Section。

        Notes:
            - 附件编号：默认右对齐显示
            - 标题：默认居中显示，使用封面专用字体和字号
            - 副标题：默认居中显示
            - 日期：默认居中显示
            - 各元素通过space_before和space_after控制段前段后行数
            - 如果cover配置为None，则跳过封面渲染
            - 封面结束后使用add_section创建新节，便于独立控制页脚页码
        """
        cover = self.config.cover
        if not cover:
            return

        # 按顺序渲染各元素：附件编号 -> 主标题 -> 副标题 -> 日期
        self._render_cover_element(cover.attachment)
        self._render_cover_element(cover.title)
        self._render_cover_element(cover.subtitle)
        self._render_cover_element(cover.date)

        # 封面结束，添加新节（新页）
        self.doc.add_section(WD_SECTION_START.NEW_PAGE)

    def _render_toc(self):
        """
        渲染目录页

        根据TocConfig配置生成目录，支持多级缩进和自动页码。
        目录结束后自动添加新节（分节符），使目录成为独立的Section。

        Notes:
            - 目录标题：居中显示，使用目录专用字体和字号
            - 目录条目：根据level级别设置左缩进，实现层级效果
            - 缩进量 = indent_per_level * level（单位cm）
            - 页码：通过Word域字段自动生成，使用制表位右对齐
            - 引导符：标题与页码之间使用leader指定的字符连接
            - 如果toc配置为None，则跳过目录渲染
            - 目录结束后使用add_section创建新节，便于独立控制页脚页码
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
        for idx, entry in enumerate(toc.entries):
            p = self.doc.add_paragraph()

            # 设置制表位
            tab_stops = p.paragraph_format.tab_stops
            # 添加右对齐制表位，带引导符
            leader_map = {
                "...": 1,  # 点号引导
                "---": 2,  # 虚线引导
                "___": 3,  # 下划线引导
            }
            leader = leader_map.get(toc.leader, 0)  # 默认无引导符

            # 计算页码位置（页面宽度 - 右边距 - 左边距）
            page_width = self.config.page_setup.page_width
            left_margin = self.config.page_setup.left_margin
            right_margin = self.config.page_setup.right_margin
            tab_position = page_width - left_margin - right_margin - 1  # 留出1cm边距

            from docx.enum.text import WD_TAB_ALIGNMENT, WD_TAB_LEADER
            tab_stops.add_tab_stop(Cm(tab_position), WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.DOTS if leader == 1 else WD_TAB_LEADER.NONE)

            # 添加标题文本
            run = p.add_run(self._resolve_text(entry.text))
            set_chinese_font(run, toc.entry_font_name, toc.entry_font_size)

            # 添加制表符
            p.add_run("\t")

            # 添加页码（使用域字段）
            if toc.show_page_number and idx < len(self._heading_bookmarks):
                bookmark_name = self._heading_bookmarks[idx]
                self._add_field_code(
                    p, f"PAGEREF {bookmark_name}",
                    toc.page_number_font_name, toc.page_number_font_size
                )

            # 设置左缩进
            p.paragraph_format.left_indent = Cm(toc.indent_per_level * entry.level)

        # 目录结束，添加新节（新页）
        self.doc.add_section(WD_SECTION_START.NEW_PAGE)

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
            - 自动添加书签，用于目录页码引用
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

        # 添加书签，用于目录页码引用
        bookmark_name = f"_TocHeading_{len(self._heading_bookmarks)}"
        self._add_bookmark(paragraph, bookmark_name)

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

    def _set_start_page(self, section, start_page: int):
        """
        设置Section的起始页码

        Args:
            section: python-docx的Section对象
            start_page: 起始页码数值

        Notes:
            通过设置w:pgNumType元素的w:start属性来指定节的起始页码。
            如果w:pgNumType元素不存在则自动创建。
        """
        sectPr = section._sectPr
        pgNumType = sectPr.find(qn('w:pgNumType'))
        if pgNumType is None:
            pgNumType = OxmlElement('w:pgNumType')
            sectPr.append(pgNumType)
        pgNumType.set(qn('w:start'), str(start_page))

    def _render_footer(self):
        """
        渲染页脚页码

        根据FooterConfig配置，在文档各节的页脚中添加自动页码。
        根据Section角色（封面/目录/正文）和start_from配置分别处理页码显示逻辑。

        Notes:
            - 使用Word域字段PAGE和NUMPAGES实现自动页码
            - 支持{page}和{total}占位符
            - 封面Section：根据skip_cover决定是否显示页码
            - 目录Section：根据skip_toc决定是否显示页码
            - 正文Section：始终显示页码
            - start_from配置决定页码从哪个节开始计数（cover/toc/content）
            - 在start_from指定的节上设置起始页码，后续节延续计数
            - 通过_add_field_code方法添加Word域字段
        """
        footer_config = self.config.footer
        if not footer_config or not footer_config.enabled:
            return

        sections = self.doc.sections

        alignment_map = {
            "left": WD_ALIGN_PARAGRAPH.LEFT,
            "center": WD_ALIGN_PARAGRAPH.CENTER,
            "right": WD_ALIGN_PARAGRAPH.RIGHT,
        }
        alignment = alignment_map.get(footer_config.alignment, WD_ALIGN_PARAGRAPH.CENTER)

        has_cover = self.config.cover is not None
        has_toc = self.config.toc is not None

        section_roles = []
        if has_cover:
            section_roles.append("cover")
        if has_toc:
            section_roles.append("toc")
        while len(section_roles) < len(sections):
            section_roles.append("content")

        start_from = footer_config.start_from
        start_page_set = False

        for idx, section in enumerate(sections):
            role = section_roles[idx] if idx < len(section_roles) else "content"
            footer = section.footer
            footer.is_linked_to_previous = False

            for paragraph in footer.paragraphs:
                paragraph.clear()

            skip_page_number = False
            if role == "cover" and footer_config.skip_cover:
                skip_page_number = True
            elif role == "toc" and footer_config.skip_toc:
                skip_page_number = True

            if skip_page_number:
                continue

            if not start_page_set and role == start_from:
                self._set_start_page(section, footer_config.start_page)
                start_page_set = True

            if not footer.paragraphs:
                footer.add_paragraph()

            paragraph = footer.paragraphs[0]
            paragraph.alignment = alignment

            format_str = footer_config.format
            parts = re.split(r'(\{page\}|\{total\})', format_str)

            for part in parts:
                if part == "{page}":
                    self._add_field_code(
                        paragraph, "PAGE",
                        footer_config.font_name, footer_config.font_size
                    )
                elif part == "{total}":
                    self._add_field_code(
                        paragraph, "NUMPAGES",
                        footer_config.font_name, footer_config.font_size
                    )
                else:
                    run = paragraph.add_run(part)
                    set_chinese_font(run, footer_config.font_name, footer_config.font_size)

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

        按顺序执行：创建文档 -> 默认样式 -> 封面 -> 目录 -> 正文段落 -> 页面设置 -> 页脚页码

        Returns:
            Document: python-docx的Document对象，调用方可通过 doc.save() 保存为.docx文件

        Notes:
            - 每次调用generate()都会创建新的Document对象
            - 如果cover或toc配置为None，对应部分会被跳过
            - sections列表中的每个SectionConfig按顺序依次渲染
            - 标题自动添加书签，用于目录页码引用
            - 页脚页码通过Word域字段自动生成
            - 页面设置在所有节创建完成后执行，确保每个节的页面参数一致
        """
        self.doc = Document()
        self._heading_bookmarks = []
        self._setup_default_style()
        self._render_cover()
        self._render_toc()

        for section in self.config.sections:
            self._render_section(section)

        self._setup_page()
        self._render_footer()

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
