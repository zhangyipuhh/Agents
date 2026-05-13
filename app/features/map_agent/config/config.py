#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
MapAgent 配置加载模块

从 .env 文件加载环境变量，初始化 MapAgentSettings 单例。
提供报告配置工厂函数，用于构建MapAgent专用的报告配置。

Date: 2026-04-20
"""

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
)


load_dotenv()
map_agent_settings = MapAgentSettings()


def get_report_config(data: dict) -> ReportConfig:
    """
    构建MapAgent专用的报告配置

    根据传入的数据字典，构建包含封面、目录、正文段落的完整报告配置对象。
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
    # 封面配置
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

    # 目录配置
    toc = TocConfig(
        title="目 录",
        title_font_name="黑体",
        title_font_size=16,
        title_bold=True,
        entries=[
            # 一级标题
            TocEntry(text="一、项目选址与要素保障", level=0, bold=True, font_name="黑体", font_size=16),
            # 二级标题
            TocEntry(text="（一）项目选址选线", level=1, font_name="楷体", font_size=14),
            # 三级标题
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
            TocEntry(text="二、 与主体功能区的协同性（可研编制大纲外事项）", level=0, bold=True, font_name="黑体", font_size=16),
            TocEntry(text="三、 其他空间管控分析（可研编制大纲外事项）",  level=0, bold=True, font_name="黑体", font_size=16),
            TocEntry(text="（一） 涉及自然保护地情况", level=1, font_name="楷体", font_size=14),
            TocEntry(text="（二） 历史文化保护情况", level=1, font_name="楷体", font_size=14),
            TocEntry(text="四、 其他国土空间用途管制要求（可研编制大纲外事项）",  level=0, bold=True, font_name="黑体", font_size=16),
            TocEntry(text="（一） 违法用地情况", level=1, font_name="楷体", font_size=14),
            TocEntry(text="（二） 林草地占用情况", level=1, font_name="楷体", font_size=14),
        ],
        entry_font_name="宋体",
        entry_font_size=12,
        indent_per_level=0.74,
    )

    # 正文段落配置
    sections = [
        # 分页符 - 正文开始
        SectionConfig(section_type="page_break"),
        
        # 一级标题
        SectionConfig(
            section_type="heading",
            content="一、项目选址与要素保障",
            level=1,
        ),
        
        # 二级标题
        SectionConfig(
            section_type="heading",
            content="（一）项目选址选线",
            level=2,
        ),
        
        # 三级标题
        SectionConfig(
            section_type="heading",
            content="1. 项目场址或线路的土地权属",
            level=3,
        ),
        # 正文段落
        SectionConfig(
            section_type="paragraph",
            content="项目用地涉及{{项目位置}}，土地权属情况如下...",
        ),
        
        # 三级标题
        SectionConfig(
            section_type="heading",
            content="2. 土地利用规划",
            level=3,
        ),
        SectionConfig(
            section_type="paragraph",
            content="根据土地利用总体规划，项目用地符合规划要求...",
        ),
        
        # 三级标题
        SectionConfig(
            section_type="heading",
            content="3. 地质灾害危险性评估",
            level=3,
        ),
        SectionConfig(
            section_type="paragraph",
            content="经评估，项目区域地质灾害危险性等级为...",
        ),
        
        # 二级标题
        SectionConfig(
            section_type="heading",
            content="（二）要素保障",
            level=2,
        ),
        
        # 三级标题
        SectionConfig(
            section_type="heading",
            content="1. 用地保障",
            level=3,
        ),
        SectionConfig(
            section_type="paragraph",
            content="项目用地总面积{{用地总面积}}公顷，其中农用地{{农用地面积}}公顷...",
        ),
        
        # 三级标题
        SectionConfig(
            section_type="heading",
            content="2. 用林保障",
            level=3,
        ),
        SectionConfig(
            section_type="paragraph",
            content="项目涉及使用林地{{林地面积}}公顷...",
        ),
        
        # 三级标题
        SectionConfig(
            section_type="heading",
            content="3. 用海保障",
            level=3,
        ),
        SectionConfig(
            section_type="paragraph",
            content="项目涉及用海面积{{用海面积}}公顷...",
        ),
        
        # 一级标题
        SectionConfig(
            section_type="heading",
            content="二、规划符合性分析",
            level=1,
        ),
        
        # 二级标题
        SectionConfig(
            section_type="heading",
            content="（一）国土空间规划",
            level=2,
        ),
        SectionConfig(
            section_type="paragraph",
            content="项目符合国土空间规划相关要求...",
        ),
        
        # 二级标题
        SectionConfig(
            section_type="heading",
            content="（二）生态保护红线",
            level=2,
        ),
        SectionConfig(
            section_type="paragraph",
            content="项目不涉及生态保护红线范围...",
        ),
        
        # 二级标题
        SectionConfig(
            section_type="heading",
            content="（三）资源环境承载力",
            level=2,
        ),
        SectionConfig(
            section_type="paragraph",
            content="项目所在区域资源环境承载力评价结果为...",
        ),
    ]

    return ReportConfig(
        page_setup=PageSetup(),
        cover=cover,
        toc=toc,
        sections=sections,
        data=data,
        default_font_name="宋体",
        default_font_size=12,
        footer=FooterConfig(
            format="-{page}-",
        ),
    )
