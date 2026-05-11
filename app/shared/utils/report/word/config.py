#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
Word报告配置数据类模块

定义报告生成所需的页面设置、封面、目录、段落等配置数据结构，
支持A4纸张排版规范，包含宋体/黑体字体、多级标题样式等参数。

Date: 2026-05-11
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Literal


@dataclass
class PageSetup:
    """
    页面设置配置类

    定义Word文档的页面尺寸和边距参数，默认使用A4纸张尺寸和标准公文边距。

    Attributes:
        page_width: 页面宽度，单位cm，默认21.0（A4宽度）
        page_height: 页面高度，单位cm，默认29.7（A4高度）
        top_margin: 上边距，单位cm，默认2.54
        bottom_margin: 下边距，单位cm，默认2.54
        left_margin: 左边距，单位cm，默认3.17
        right_margin: 右边距，单位cm，默认3.17

    Example:
        >>> setup = PageSetup()
        >>> print(f"页面: {setup.page_width}x{setup.page_height}cm")
        页面: 21.0x29.7cm
    """

    page_width: float = 21.0
    """页面宽度，单位cm，默认21.0对应A4纸张宽度"""

    page_height: float = 29.7
    """页面高度，单位cm，默认29.7对应A4纸张高度"""

    top_margin: float = 2.54
    """上边距，单位cm，默认2.54cm（约1英寸）"""

    bottom_margin: float = 2.54
    """下边距，单位cm，默认2.54cm（约1英寸）"""

    left_margin: float = 3.17
    """左边距，单位cm，默认3.17cm，适用于装订侧留白"""

    right_margin: float = 3.17
    """右边距，单位cm，默认3.17cm"""


@dataclass
class CoverConfig:
    """
    封面配置类

    定义报告封面的文本内容、字体样式和排版间距参数。
    封面布局从上到下依次为：附件编号 -> 空行 -> 主标题 -> 空行 -> 副标题 -> 空行 -> 日期文本。

    Attributes:
        title: 主标题文本，支持{{变量}}占位符，如"{{项目名称}}前期选址协同服务报告"
        subtitle: 副标题文本，如"（大纲）"
        date_text: 日期文本，支持{{变量}}占位符，如"生成日期：{{生成日期}}"
        attachment_no: 附件编号，右对齐显示，如"附件2"
        title_font_name: 主标题字体名称，默认"黑体"
        title_font_size: 主标题字号，单位pt，默认22
        title_bold: 主标题是否加粗，默认True
        subtitle_font_name: 副标题字体名称，默认"宋体"
        subtitle_font_size: 副标题字号，单位pt，默认12
        date_font_name: 日期字体名称，默认"宋体"
        date_font_size: 日期字号，单位pt，默认12
        blank_lines_before_title: 主标题前空行数，默认3
        blank_lines_after_title: 主标题后空行数，默认1
        blank_lines_before_date: 日期前空行数，默认2

    Example:
        >>> cover = CoverConfig(
        ...     title="{{项目名称}}前期选址协同服务报告",
        ...     subtitle="（大纲）",
        ...     date_text="生成日期：{{生成日期}}",
        ...     attachment_no="附件2"
        ... )
    """

    title: str = ""
    """主标题文本，支持{{变量}}占位符，如"{{项目名称}}前期选址协同服务报告" """

    subtitle: str = ""
    """副标题文本，如"（大纲）" """

    date_text: str = ""
    """日期文本，支持{{变量}}占位符，如"生成日期：{{生成日期}}" """

    attachment_no: str = ""
    """附件编号，右对齐显示，如"附件2" """

    title_font_name: str = "黑体"
    """主标题字体名称，默认"黑体"，适用于公文标题"""

    title_font_size: int = 22
    """主标题字号，单位pt，默认22，对应二号字"""

    title_bold: bool = True
    """主标题是否加粗，默认True"""

    subtitle_font_name: str = "宋体"
    """副标题字体名称，默认"宋体" """

    subtitle_font_size: int = 12
    """副标题字号，单位pt，默认12，对应小四号字"""

    date_font_name: str = "宋体"
    """日期字体名称，默认"宋体" """

    date_font_size: int = 12
    """日期字号，单位pt，默认12，对应小四号字"""

    blank_lines_before_title: int = 3
    """主标题前空行数，默认3行，用于在附件编号和标题之间留出间距"""

    blank_lines_after_title: int = 1
    """主标题后空行数，默认1行，用于标题和副标题之间的间距"""

    blank_lines_before_date: int = 2
    """日期前空行数，默认2行，用于副标题和日期之间的间距"""


@dataclass
class TocEntry:
    """
    目录条目类

    表示目录中的一个条目，包含文本内容和缩进级别。
    缩进级别用于控制目录的层级显示，0为一级标题，1为二级标题，2为三级标题。

    Attributes:
        text: 条目文本内容，如"一、项目选址与要素保障"
        level: 缩进级别，0=一级，1=二级，2=三级，默认0

    Example:
        >>> entry = TocEntry(text="一、项目选址与要素保障", level=0)
        >>> entry_sub = TocEntry(text="（一）项目选址选线", level=1)
    """

    text: str
    """条目文本内容，如"一、项目选址与要素保障" """

    level: int = 0
    """缩进级别，0=一级，1=二级，2=三级，默认0"""


@dataclass
class TocConfig:
    """
    目录配置类

    定义报告目录的标题样式、条目列表和缩进参数。
    目录标题居中显示，条目按层级缩进排列。

    Attributes:
        title: 目录标题文本，默认"目 录"
        title_font_name: 目录标题字体名称，默认"黑体"
        title_font_size: 目录标题字号，单位pt，默认16
        title_bold: 目录标题是否加粗，默认True
        entries: 目录条目列表，默认为空列表
        entry_font_name: 条目字体名称，默认"宋体"
        entry_font_size: 条目字号，单位pt，默认12
        indent_per_level: 每级缩进量，单位cm，默认0.74（约2个中文字符宽度）

    Example:
        >>> toc = TocConfig(
        ...     entries=[
        ...         TocEntry(text="一、项目选址与要素保障", level=0),
        ...         TocEntry(text="（一）项目选址选线", level=1),
        ...         TocEntry(text="1. 项目场址或线路的土地权属", level=2),
        ...     ]
        ... )
    """

    title: str = "目 录"
    """目录标题文本，默认"目 录"，居中显示"""

    title_font_name: str = "黑体"
    """目录标题字体名称，默认"黑体" """

    title_font_size: int = 16
    """目录标题字号，单位pt，默认16，对应三号字"""

    title_bold: bool = True
    """目录标题是否加粗，默认True"""

    entries: list[TocEntry] = field(default_factory=list)
    """目录条目列表，默认为空列表，通过TocEntry定义每个条目的文本和层级"""

    entry_font_name: str = "宋体"
    """条目字体名称，默认"宋体" """

    entry_font_size: int = 12
    """条目字号，单位pt，默认12，对应小四号字"""

    indent_per_level: float = 0.74
    """每级缩进量，单位cm，默认0.74cm，约等于2个中文字符宽度"""


@dataclass
class SectionConfig:
    """
    段落配置类（核心类）

    定义报告正文中每个段落/标题的类型、内容、字体样式和排版参数。
    支持三种段落类型：标题(heading)、正文(paragraph)、分页符(page_break)。

    对于font_name、font_size、bold、alignment、first_line_indent、space_before、
    space_after、left_indent等属性，当值为None或空/0时，将使用默认值：
    - heading类型：字体"黑体"，字号按级别14/13/12，加粗True，无首行缩进，
      段前间距12/9/6pt，段后间距6/5/3pt，左缩进0/0.74/1.48cm
    - paragraph类型：字体"宋体"，字号12，不加粗，首行缩进，
      段前段后间距0，无左缩进

    Attributes:
        section_type: 段落类型，"heading"=标题 / "paragraph"=正文 / "page_break"=分页符
        content: 文本内容，支持{{变量}}占位符，也支持可调用对象（如lambda或函数），
                 可调用对象在渲染时被调用以获取实际文本
        level: 标题级别1-3，仅heading类型有效，默认1
        font_name: 字体名称，为空字符串时使用默认值（heading用"黑体"，paragraph用"宋体"）
        font_size: 字号，单位pt，为0时使用默认值（heading按级别14/13/12，paragraph为12）
        bold: 是否加粗，None时使用默认值（heading为True，paragraph为False）
        alignment: 对齐方式，WD_ALIGN_PARAGRAPH枚举值，None时使用默认左对齐
        first_line_indent: 是否首行缩进，None时paragraph默认True，heading默认False
        line_spacing: 行距倍数，默认1.5
        space_before: 段前间距，单位pt，None时heading按级别12/9/6，paragraph为0
        space_after: 段后间距，单位pt，None时heading按级别6/5/3，paragraph为0
        left_indent: 左缩进，单位cm，None时heading按级别0/0.74/1.48，paragraph为0

    Example:
        >>> # 一级标题
        >>> section_heading = SectionConfig(
        ...     section_type="heading",
        ...     content="一、项目选址与要素保障",
        ...     level=1
        ... )
        >>> # 正文段落
        >>> section_para = SectionConfig(
        ...     section_type="paragraph",
        ...     content="项目用地涉及xx县..."
        ... )
        >>> # 分页符
        >>> section_break = SectionConfig(section_type="page_break")
        >>> # 使用可调用对象作为内容
        >>> section_dynamic = SectionConfig(
        ...     section_type="paragraph",
        ...     content=lambda d: f"项目用地总面积{d['用地总面积']}公顷"
        ... )
    """

    section_type: Literal["heading", "paragraph", "page_break"]
    """
    段落类型，使用Literal类型约束取值范围：
    - "heading": 标题段落，支持多级标题样式
    - "paragraph": 正文段落，默认首行缩进
    - "page_break": 分页符，content字段无效
    """

    content: str | Callable = ""
    """
    文本内容，支持两种形式：
    - str: 直接文本，支持{{变量}}占位符（如"{{项目名称}}"）
    - Callable: 可调用对象，接收data字典作为参数，返回str文本
    """

    level: int = 1
    """标题级别1-3，仅heading类型有效，1=一级标题，2=二级标题，3=三级标题"""

    font_name: str = ""
    """字体名称，为空字符串时使用默认值：heading用"黑体"，paragraph用"宋体" """

    font_size: int = 0
    """字号，单位pt，为0时使用默认值：heading按级别14/13/12，paragraph为12 """

    bold: bool | None = None
    """是否加粗，None时使用默认值：heading为True，paragraph为False """

    alignment: int | None = None
    """对齐方式，WD_ALIGN_PARAGRAPH枚举值，None时使用默认左对齐 """

    first_line_indent: bool | None = None
    """是否首行缩进，None时paragraph默认True（缩进0.74cm约2字符），heading默认False """

    line_spacing: float = 1.5
    """行距倍数，默认1.5倍行距，符合中文文档格式要求"""

    space_before: float | None = None
    """
    段前间距，单位pt，None时使用默认值：
    - heading: 按级别分别为12pt(一级)/9pt(二级)/6pt(三级)
    - paragraph: 0pt
    """

    space_after: float | None = None
    """
    段后间距，单位pt，None时使用默认值：
    - heading: 按级别分别为6pt(一级)/5pt(二级)/3pt(三级)
    - paragraph: 0pt
    """

    left_indent: float | None = None
    """
    左缩进，单位cm，None时使用默认值：
    - heading: 按级别分别为0cm(一级)/0.74cm(二级)/1.48cm(三级)
    - paragraph: 0cm
    """


@dataclass
class ReportConfig:
    """
    报告总配置类

    报告生成的顶层配置，整合页面设置、封面、目录和正文段落的所有配置参数。
    通过data字典提供变量替换数据，用于填充内容中的{{变量}}占位符。

    Attributes:
        page_setup: 页面设置配置，默认使用A4纸张和标准边距
        cover: 封面配置，None则不生成封面
        toc: 目录配置，None则不生成目录
        sections: 正文段落配置列表，按顺序排列，每个元素定义一个段落/标题/分页符
        data: 变量替换数据字典，用于填充content中的{{变量}}占位符
        default_font_name: 默认正文字体名称，默认"宋体"
        default_font_size: 默认正文字号，单位pt，默认12

    Example:
        >>> config = ReportConfig(
        ...     cover=CoverConfig(
        ...         title="{{项目名称}}前期选址协同服务报告",
        ...         date_text="生成日期：{{生成日期}}",
        ...         attachment_no="附件2"
        ...     ),
        ...     toc=TocConfig(
        ...         entries=[
        ...             TocEntry(text="一、项目选址与要素保障", level=0),
        ...             TocEntry(text="（一）项目选址选线", level=1),
        ...         ]
        ...     ),
        ...     sections=[
        ...         SectionConfig(section_type="heading", content="一、项目选址与要素保障", level=1),
        ...         SectionConfig(section_type="paragraph", content="项目用地涉及..."),
        ...         SectionConfig(section_type="page_break"),
        ...     ],
        ...     data={"项目名称": "XX高速公路", "生成日期": "2026年5月11日"}
        ... )
    """

    page_setup: PageSetup = field(default_factory=PageSetup)
    """页面设置配置，默认使用A4纸张(21x29.7cm)和标准公文边距"""

    cover: CoverConfig | None = None
    """封面配置，None则不生成封面，设置后按CoverConfig参数生成封面页"""

    toc: TocConfig | None = None
    """目录配置，None则不生成目录，设置后按TocConfig参数生成目录页"""

    sections: list[SectionConfig] = field(default_factory=list)
    """正文段落配置列表，按顺序排列，每个SectionConfig定义一个段落/标题/分页符"""

    data: dict = field(default_factory=dict)
    """
    变量替换数据字典，用于填充content中的{{变量}}占位符。
    键为变量名（如"项目名称"），值为替换内容。
    当content为Callable时，此字典将作为参数传入可调用对象。
    """

    default_font_name: str = "宋体"
    """默认正文字体名称，默认"宋体"，用于未指定字体时的回退值"""

    default_font_size: int = 12
    """默认正文字号，单位pt，默认12（小四号字），用于未指定字号时的回退值"""
