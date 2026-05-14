#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
MapAgent 配置加载模块

从 .env 文件加载环境变量，初始化 MapAgentSettings 单例。
提供报告配置工厂函数，用于构建MapAgent专用的报告配置。
正文内容从JSON文件加载，样式通过HeadingStyleConfig和ParagraphStyleConfig统一管理。

Date: 2026-04-20
"""

import json
import os

from dotenv import load_dotenv

from app.features.map_agent.config.settings import MapAgentSettings
from app.shared.utils.report.word.config import (
    ReportConfig,
    CoverConfig,
    CoverElementConfig,
    TocConfig,
    TocEntry,
    SectionConfig,
    PageSetup,
    FooterConfig,
    HeadingStyleConfig,
    ParagraphStyleConfig,
)


load_dotenv()
map_agent_settings = MapAgentSettings()

_JSON_CONTENT_PATH = os.path.join(os.path.dirname(__file__), "report_content.json")


def _load_report_content() -> list[dict]:
    """
    从JSON文件加载报告正文内容

    Returns:
        list[dict]: 段落内容列表，每个元素包含type、level、content等字段

    Raises:
        FileNotFoundError: 当report_content.json文件不存在时抛出
        json.JSONDecodeError: 当JSON文件格式错误时抛出
    """
    with open(_JSON_CONTENT_PATH, "r", encoding="utf-8") as f:
        content = json.load(f)
    return content.get("sections", [])


def _build_sections(content_list: list[dict]) -> list[SectionConfig]:
    """
    从JSON内容列表构建SectionConfig列表

    遍历JSON中的段落内容，根据type字段创建对应的SectionConfig对象。
    样式由ReportConfig中的heading_styles和paragraph_style统一管理，
    此处仅设置段落类型、内容和级别，不再重复设置样式参数。

    Args:
        content_list: JSON内容列表，每个元素为包含type/level/content字段的字典

    Returns:
        list[SectionConfig]: 可直接用于ReportConfig的段落配置列表
    """
    sections = []
    for item in content_list:
        section_type = item.get("type", "paragraph")
        if section_type == "page_break":
            sections.append(SectionConfig(section_type="page_break"))
        elif section_type == "heading":
            sections.append(SectionConfig(
                section_type="heading",
                content=item.get("content", ""),
                level=item.get("level", 1),
            ))
        elif section_type == "paragraph":
            sections.append(SectionConfig(
                section_type="paragraph",
                content=item.get("content", ""),
            ))
    return sections


def _get_heading_styles() -> dict[int, HeadingStyleConfig]:
    """
    获取MapAgent报告各级标题的统一样式配置

    修改此处的样式参数，全文所有同级别标题将同步更新。
    三号字16号，小三15 ， 四号字14号  小四 12号
    Returns:
        dict[int, HeadingStyleConfig]: 键为标题级别(1/2/3)，值为样式配置
    """
    return {
        1: HeadingStyleConfig(
            font_name="黑体",
            font_size=18,
            bold=True,
            space_before=12,
            space_after=6,
            left_indent=0,
        ),
        2: HeadingStyleConfig(
            font_name="黑体",
            font_size=13,
            bold=True,
            space_before=9,
            space_after=5,
            left_indent=0.74,
        ),
        3: HeadingStyleConfig(
            font_name="黑体",
            font_size=12,
            bold=True,
            space_before=6,
            space_after=3,
            left_indent=1.48,
        ),
    }


def _get_paragraph_style() -> ParagraphStyleConfig:
    """
    获取MapAgent报告正文段落的统一样式配置

    修改此处的样式参数，全文所有正文段落将同步更新。

    Returns:
        ParagraphStyleConfig: 正文段落样式配置
    """
    return ParagraphStyleConfig(
        font_name="宋体",
        font_size=12,
        bold=False,
        first_line_indent_chars=2,
        line_spacing_rule="auto",
        line_spacing_value=1.5,
        space_before=0,
        space_after=0,
        left_indent=0,
    )


def get_report_config(data: dict) -> ReportConfig:
    """
    构建MapAgent专用的报告配置

    根据传入的数据字典，构建包含封面、目录、正文段落的完整报告配置对象。
    正文内容从report_content.json文件加载，样式通过统一样式配置管理。
    封面标题使用"{{项目名称}}前期选址协同服务报告"格式，日期使用"{{生成日期}}"占位符。

    Args:
        data: 变量替换数据字典，应包含以下键：
            - 项目名称: 报告标题中的项目名称
            - 生成日期: 报告生成日期，如"2026年5月12日"
            以及其他需要在正文中使用的变量

    Returns:
        ReportConfig: 完整的报告配置对象，可直接用于WordReportGenerator

    Example:
        >>> config = get_report_config({
        ...     "项目名称": "XX高速公路",
        ...     "生成日期": "2026年5月12日",
        ...     "项目位置": "xx县xx镇"
        ... })
        >>> generator = WordReportGenerator(config)
        >>> doc = generator.generate()
    """
    cover = CoverConfig(
        title=CoverElementConfig(
            text="{{项目名称}}前期选址协同服务报告",
            font_name="黑体",
            font_size=22,
            bold=True,
            space_before=3,
            space_after=0,
        ),
        subtitle=CoverElementConfig(
            text="（大纲）",
            font_name="宋体",
            font_size=22,
            bold=True,
            space_before=0,
            space_after=0,
        ),
        date=CoverElementConfig(
            text="生成日期：{{生成日期}}",
            font_name="宋体",
            font_size=16,
            bold=True,
            space_before=11,
            space_after=0,
        ),
        attachment=CoverElementConfig(
            text="附件2",
            font_name="宋体",
            font_size=12,
            bold=True,
            alignment="left",
            space_before=0,
            space_after=0,
        ),
    )

    toc = TocConfig(
        title="目 录",
        title_font_name="黑体",
        title_font_size=16,
        title_bold=True,
        entries=[
            TocEntry(text="一、项目选址与要素保障", level=0, bold=True, font_name="黑体", font_size=15),
            TocEntry(text="（一）项目选址选线", level=1, font_name="楷体", font_size=14),
            TocEntry(text="1. 项目场址或线路的土地权属", level=2, font_name="方正仿宋_GB2312"),
            TocEntry(text="2. 供地方式", level=2, font_name="方正仿宋_GB2312"),
            TocEntry(text="3. 土地利用状况", level=2, font_name="方正仿宋_GB2312"),
            TocEntry(text="4. 矿产压覆", level=2, font_name="方正仿宋_GB2312"),
            TocEntry(text="5. 占用耕地和永久基本农田", level=2, font_name="方正仿宋_GB2312"),
            TocEntry(text="6. 涉及生态保护红线情况", level=2, font_name="方正仿宋_GB2312"),
            TocEntry(text="7. 地质灾害危险性评估", level=2, font_name="方正仿宋_GB2312"),
            TocEntry(text="（二） 要素保障分析", level=1, font_name="楷体", font_size=14),
            TocEntry(text="1. 相关的国土空间规划", level=2, font_name="方正仿宋_GB2312"),
            TocEntry(text="2. 土地利用年度计划", level=2, font_name="方正仿宋_GB2312"),
            TocEntry(text="3. 建设用地控制指标", level=2, font_name="方正仿宋_GB2312"),
            TocEntry(text="4. 节地水平", level=2, font_name="方正仿宋_GB2312"),
            TocEntry(text="5. 农用地转用和土地征收手续办理安排", level=2, font_name="方正仿宋_GB2312"),
            TocEntry(text="6. 耕地占补平衡可行性", level=2, font_name="方正仿宋_GB2312"),
            TocEntry(text="7. 永久基本农田占用补划可行性", level=2, font_name="方正仿宋_GB2312"),
            TocEntry(text="二、 与主体功能区的协同性（可研编制大纲外事项）", level=0, bold=True, font_name="黑体", font_size=15),
            TocEntry(text="三、 其他空间管控分析（可研编制大纲外事项）", level=0, bold=True, font_name="黑体", font_size=15),
            TocEntry(text="（一） 涉及自然保护地情况", level=1, font_name="楷体", font_size=14),
            TocEntry(text="（二） 历史文化保护情况", level=1, font_name="楷体", font_size=14),
            TocEntry(text="四、 其他国土空间用途管制要求（可研编制大纲外事项）", level=0, bold=True, font_name="黑体", font_size=15),
            TocEntry(text="（一） 违法用地情况", level=1, font_name="楷体", font_size=14),
            TocEntry(text="（二） 林草地占用情况", level=1, font_name="楷体", font_size=14),
        ],
        entry_font_name="宋体",
        entry_font_size=12,
        indent_per_level=0.74,
    )

    content_list = _load_report_content()
    sections = _build_sections(content_list)

    return ReportConfig(
        page_setup=PageSetup(),
        cover=cover,
        toc=toc,
        sections=sections,
        data=data,
        default_font_name="宋体",
        default_font_size=12,
        heading_styles=_get_heading_styles(),
        paragraph_style=_get_paragraph_style(),
        footer=FooterConfig(
            format="-{page}-",
        ),
    )
