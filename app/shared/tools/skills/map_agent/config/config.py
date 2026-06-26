#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
MapAgent 配置加载模块

从 .env 文件加载环境变量，初始化 MapAgentSettings 单例。
提供报告配置工厂函数，用于构建MapAgent专用的报告配置。
正文内容从JSON文件加载，样式通过HeadingStyleConfig和ParagraphStyleConfig统一管理。

Date: 2026-04-20
"""

from decimal import Decimal
from typing import List, Optional, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, Field

from app.shared.tools.skills.map_agent.config.settings import MapAgentSettings
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


# ==================== 项目选址报告数据模型 ====================

class AreaValue(BaseModel):
    """
    面积数值模型
    
    用于表示各类土地面积的数值和是否涉及的状态。
    
    Attributes:
        value: 面积数值，单位为公顷，必须大于等于0
        is_involved: 是否涉及该类型土地
    """
    value: Decimal = Field(default=Decimal("0"), description="面积数值（公顷）", ge=0)
    is_involved: bool = Field(default=False, description="是否涉及")


class RegionAreaDetail(BaseModel):
    """
    区域面积详情模型
    
    包含一个区域（县、乡、村）的所有面积类型详情。
    
    Attributes:
        cultivated_land: 耕地面积
        paddy_field: 水田面积
        black_soil: 黑土耕地面积
        permanent_basic_farmland: 永久基本农田面积
        forest_land: 林地面积
        grassland: 草地面积
        mineral_press_area: 矿产压覆面积
        ecological_red_line: 生态保护红线面积
        nature_reserve: 自然保护地面积
        illegal_land: 违法用地面积
    """
    cultivated_land: AreaValue = Field(default_factory=lambda: AreaValue(), description="耕地")
    paddy_field: AreaValue = Field(default_factory=lambda: AreaValue(), description="水田")
    black_soil: AreaValue = Field(default_factory=lambda: AreaValue(), description="黑土耕地")
    permanent_basic_farmland: AreaValue = Field(default_factory=lambda: AreaValue(), description="永久基本农田")
    forest_land: AreaValue = Field(default_factory=lambda: AreaValue(), description="林地")
    grassland: AreaValue = Field(default_factory=lambda: AreaValue(), description="草地")
    mineral_press_area: AreaValue = Field(default_factory=lambda: AreaValue(), description="矿产压覆面积")
    ecological_red_line: AreaValue = Field(default_factory=lambda: AreaValue(), description="生态保护红线")
    nature_reserve: AreaValue = Field(default_factory=lambda: AreaValue(), description="自然保护地")
    illegal_land: AreaValue = Field(default_factory=lambda: AreaValue(), description="违法用地")


class Village(BaseModel):
    """
    村级区域模型
    
    Attributes:
        name: 村名称
        area_detail: 村级面积详情
    """
    name: str = Field(..., description="村名称")
    area_detail: RegionAreaDetail = Field(default_factory=lambda: RegionAreaDetail(), description="面积详情")


class Town(BaseModel):
    """
    乡（镇）级区域模型
    
    Attributes:
        name: 乡（镇）名称
        villages: 下辖村列表
        area_detail: 乡级面积详情
    """
    name: str = Field(..., description="乡（镇）名称")
    villages: List[Village] = Field(default_factory=list, description="下辖村列表")
    area_detail: RegionAreaDetail = Field(default_factory=lambda: RegionAreaDetail(), description="面积详情")


class County(BaseModel):
    """
    县（市、区）级区域模型
    
    Attributes:
        name: 县（市、区）名称
        towns: 下辖乡（镇）列表
        area_detail: 县级面积详情
    """
    name: str = Field(..., description="县（市、区）名称")
    towns: List[Town] = Field(default_factory=list, description="下辖乡（镇）列表")
    area_detail: RegionAreaDetail = Field(default_factory=lambda: RegionAreaDetail(), description="面积详情")


class AreaSummary(BaseModel):
    """
    面积汇总信息模型
    
    存储项目所有区域各类土地面积的总和。
    
    Attributes:
        total_land_area: 用地总面积
        agricultural_land: 农用地面积
        cultivated_land: 耕地总面积
        paddy_field: 水田总面积
        black_soil: 黑土耕地总面积
        permanent_basic_farmland: 永久基本农田总面积
        forest_land: 林地总面积
        grassland: 草地总面积
        ecological_red_line: 生态保护红线总面积
        nature_reserve: 自然保护地总面积
        illegal_land: 违法用地总面积
    """
    total_land_area: Decimal = Field(default=Decimal("0"), description="用地总面积（公顷）")
    agricultural_land: Decimal = Field(default=Decimal("0"), description="农用地面积（公顷）")
    cultivated_land: Decimal = Field(default=Decimal("0"), description="耕地总面积（公顷）")
    paddy_field: Decimal = Field(default=Decimal("0"), description="水田总面积（公顷）")
    black_soil: Decimal = Field(default=Decimal("0"), description="黑土耕地总面积（公顷）")
    permanent_basic_farmland: Decimal = Field(default=Decimal("0"), description="永久基本农田总面积（公顷）")
    forest_land: Decimal = Field(default=Decimal("0"), description="林地总面积（公顷）")
    grassland: Decimal = Field(default=Decimal("0"), description="草地总面积（公顷）")
    ecological_red_line: Decimal = Field(default=Decimal("0"), description="生态保护红线总面积（公顷）")
    nature_reserve: Decimal = Field(default=Decimal("0"), description="自然保护地总面积（公顷）")
    illegal_land: Decimal = Field(default=Decimal("0"), description="违法用地总面积（公顷）")


class ProjectSiteSelectionData(BaseModel):
    """
    项目选址自然资源和规划"一点通"服务技术参考数据模型
    
    完整描述项目选址报告所需的所有数据，采用三级区域结构（县-乡-村）。
    
    Attributes:
        project_name: 项目名称
        reference_year: 依据年度（如：2023年度）
        counties: 涉及的县（市、区）列表
        summary: 面积汇总信息
        land_parcel_count: 宗地数量
        state_owned_unit_count: 国有单位数量
    
    Example:
        >>> data = ProjectSiteSelectionData(
        ...     project_name="某新能源项目",
        ...     reference_year="2023年度",
        ...     counties=[
        ...         County(
        ...             name="五常市",
        ...             area_detail=RegionAreaDetail(
        ...                 cultivated_land=AreaValue(value=Decimal("60.0"), is_involved=True),
        ...                 paddy_field=AreaValue(value=Decimal("40.0"), is_involved=True),
        ...             ),
        ...             towns=[...]
        ...         )
        ...     ],
        ...     summary=AreaSummary(
        ...         total_land_area=Decimal("156.0"),
        ...         cultivated_land=Decimal("105.0"),
        ...     )
        ... )
    """
    project_id: str = Field(..., description="项目唯一标识")
    project_name: str = Field(..., description="项目名称")
    reference_year: str = Field(..., description="依据年度（如：2023年度）")
    counties: List[County] = Field(default_factory=list, description="涉及的县（市、区）列表")
    summary: AreaSummary = Field(default_factory=lambda: AreaSummary(), description="面积汇总")
    land_parcel_count: int = Field(default=0, description="宗地数量")
    state_owned_unit_count: int = Field(default=0, description="国有单位数量")

    class Config:
        json_encoders = {
            Decimal: lambda v: float(v)
        }


class ProjectSiteSelectionCollection(BaseModel):
    """
    多项目选址数据集合模型

    用于管理多个项目的选址报告数据。

    Attributes:
        collection_id: 集合唯一标识
        collection_name: 集合名称（如"2024年第一批项目"）
        projects: 项目列表
        create_time: 创建时间
        update_time: 更新时间

    Example:
        >>> collection = ProjectSiteSelectionCollection(
        ...     collection_id="batch_2024_001",
        ...     collection_name="2024年新能源项目批次",
        ...     projects=[
        ...         ProjectSiteSelectionData(
        ...             project_id="proj_001",
        ...             project_name="风电场一期",
        ...             ...
        ...         ),
        ...         ProjectSiteSelectionData(
        ...             project_id="proj_002",
        ...             project_name="光伏电站",
        ...             ...
        ...         )
        ...     ]
        ... )
    """
    collection_id: str = Field(..., description="集合唯一标识")
    collection_name: str = Field(..., description="集合名称")
    projects: List[ProjectSiteSelectionData] = Field(default_factory=list, description="项目列表")
    create_time: Optional[str] = Field(None, description="创建时间")
    update_time: Optional[str] = Field(None, description="更新时间")

    class Config:
        json_encoders = {
            Decimal: lambda v: float(v)
        }

    def get_project_by_id(self, project_id: str) -> Optional[ProjectSiteSelectionData]:
        """根据项目ID获取项目数据"""
        for project in self.projects:
            if project.project_id == project_id:
                return project
        return None

    def get_project_by_name(self, project_name: str) -> Optional[ProjectSiteSelectionData]:
        """根据项目名称获取项目数据"""
        for project in self.projects:
            if project.project_name == project_name:
                return project
        return None

    def add_project(self, project: ProjectSiteSelectionData) -> None:
        """添加项目到集合"""
        self.projects.append(project)

    def remove_project_by_id(self, project_id: str) -> bool:
        """根据项目ID移除项目"""
        for i, project in enumerate(self.projects):
            if project.project_id == project_id:
                self.projects.pop(i)
                return True
        return False

    def get_total_summary(self) -> AreaSummary:
        """计算所有项目的面积总和"""
        total = AreaSummary()
        for project in self.projects:
            total.total_land_area += project.summary.total_land_area
            total.agricultural_land += project.summary.agricultural_land
            total.cultivated_land += project.summary.cultivated_land
            total.paddy_field += project.summary.paddy_field
            total.black_soil += project.summary.black_soil
            total.permanent_basic_farmland += project.summary.permanent_basic_farmland
            total.forest_land += project.summary.forest_land
            total.grassland += project.summary.grassland
            total.ecological_red_line += project.summary.ecological_red_line
            total.nature_reserve += project.summary.nature_reserve
            total.illegal_land += project.summary.illegal_land
        return total


def _format_area(value: Decimal) -> str:
    """
    格式化面积数值，去除末尾多余零

    将 Decimal 类型的面积值格式化为字符串，
    自动去除末尾无意义的零，如 60.00 → "60"，60.50 → "60.5"。

    Args:
        value: 面积数值（Decimal类型）

    Returns:
        str: 格式化后的字符串
    """
    return str(value.normalize()) if value == value.normalize() else f"{value:f}".rstrip('0').rstrip('.')


def convert_square_meters_to_hectares(square_meters: str | int | float | Decimal) -> Decimal:
    """
    将平方米转换为公顷

    转换公式：1公顷 = 10000平方米，因此 1平方米 = 0.0001公顷。
    该函数用于处理从外部传入的原始面积数据，确保报告生成前单位统一为公顷。

    Args:
        square_meters: 平方米值，可以是字符串、数字或Decimal类型

    Returns:
        Decimal: 转换后的公顷值，保留6位小数精度

    Raises:
        无显式抛出异常，转换失败时返回 Decimal("0")

    Example:
        >>> convert_square_meters_to_hectares("10000")
        Decimal('1.0')
        >>> convert_square_meters_to_hectares(5000)
        Decimal('0.5')
        >>> convert_square_meters_to_hectares(Decimal("25000.5"))
        Decimal('2.500005')
    """
    try:
        sq_m = Decimal(str(square_meters))
        return (sq_m * Decimal("0.0001")).quantize(Decimal("0.000001"))
    except Exception:
        return Decimal("0")


def _convert_region_area_detail(area_detail: RegionAreaDetail) -> None:
    """
    将 RegionAreaDetail 中所有 AreaValue 的 value 从平方米转换为公顷

    Args:
        area_detail: 区域面积详情对象

    Returns:
        无返回值，直接修改传入对象的字段值
    """
    area_fields = [
        "cultivated_land",
        "paddy_field",
        "black_soil",
        "permanent_basic_farmland",
        "forest_land",
        "grassland",
        "mineral_press_area",
        "ecological_red_line",
        "nature_reserve",
        "illegal_land",
    ]
    for field_name in area_fields:
        area_value = getattr(area_detail, field_name)
        if area_value.value:
            area_value.value = convert_square_meters_to_hectares(area_value.value)


def _convert_area_summary(summary: AreaSummary) -> None:
    """
    将 AreaSummary 中所有面积字段的 value 从平方米转换为公顷

    Args:
        summary: 面积汇总对象

    Returns:
        无返回值，直接修改传入对象的字段值
    """
    area_fields = [
        "total_land_area",
        "agricultural_land",
        "cultivated_land",
        "paddy_field",
        "black_soil",
        "permanent_basic_farmland",
        "forest_land",
        "grassland",
        "ecological_red_line",
        "nature_reserve",
        "illegal_land",
    ]
    for field_name in area_fields:
        value = getattr(summary, field_name)
        if value:
            setattr(summary, field_name, convert_square_meters_to_hectares(value))


def _count_towns_and_villages(counties: List[County]) -> tuple:
    """
    统计乡镇数和村数

    遍历所有县下的乡镇和村，统计总乡镇数和总村数。

    Args:
        counties: 县（市、区）列表

    Returns:
        tuple: (乡镇数, 村数)
    """
    town_count = 0
    village_count = 0
    for county in counties:
        town_count += len(county.towns)
        for town in county.towns:
            village_count += len(town.villages)
    return town_count, village_count


def _build_county_names_text(counties: List[County]) -> str:
    """
    生成县名列举文本

    根据县列表生成列举文本，如"xx县、xx县和xx县"。
    单个县直接返回名称，两个县用"和"连接，三个及以上用顿号+和连接。

    Args:
        counties: 县（市、区）列表

    Returns:
        str: 县名列举文本
    """
    names = [c.name for c in counties]
    if len(names) == 0:
        return "xx"
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]}和{names[1]}"
    return f"{'、'.join(names[:-1])}和{names[-1]}"


def _build_land_use_paragraph(project: ProjectSiteSelectionData) -> str:
    """
    根据项目数据生成1.土地利用状况段落文本

    拼接项目用地涉及的县、乡镇、村、国有单位、宗地数等信息，
    以及依据年度国土变更调查成果的各类面积数据。

    Args:
        project: 项目选址数据

    Returns:
        str: 土地利用状况段落文本
    """
    county_names = _build_county_names_text(project.counties)
    town_count, village_count = _count_towns_and_villages(project.counties)
    county_count = len(project.counties)

    return (
        f"{project.project_name}项目用地涉及{county_names}等{county_count}个县（市、区）的"
        f"{town_count}个乡镇{village_count}个村和{project.state_owned_unit_count}个国有单位，"
        f"共{project.land_parcel_count}宗地。依据{project.reference_year}国土变更调查成果，"
        f"项目用地总面积{_format_area(project.summary.total_land_area)}公顷，"
        f"农用地{_format_area(project.summary.agricultural_land)}公顷"
        f"（其中耕地{_format_area(project.summary.cultivated_land)}公顷、"
        f"林地{_format_area(project.summary.forest_land)}公顷），"
        f"占用永久基本农田{_format_area(project.summary.permanent_basic_farmland)}公顷、"
        f"黑土耕地{_format_area(project.summary.black_soil)}公顷。"
    )


def _build_mineral_press_paragraphs(project: ProjectSiteSelectionData) -> list:
    """
    根据项目数据生成矿产压覆及地质灾害易发区相关段落文本

    遍历项目涉及的县，检查矿产压覆情况生成对应文本，
    并追加地质灾害易发区占位段落。

    Args:
        project: 项目选址数据

    Returns:
        list: 段落文本列表
    """
    paragraphs = []
    # 检查是否有任何县涉及矿产压覆
    has_mineral = any(
        county.area_detail.mineral_press_area.is_involved
        for county in project.counties
    )
    if has_mineral:
        total_value = sum(
            county.area_detail.mineral_press_area.value
            for county in project.counties
            if county.area_detail.mineral_press_area.is_involved
        )
        paragraphs.append(
            f"{project.project_name}项目涉及压覆{_format_area(total_value)}公顷矿产资源。"
        )
    else:
        paragraphs.append(f"{project.project_name}项目不涉及压覆矿产资源。")

    # 地质灾害易发区（无数据字段，保留占位文本）
    paragraphs.append(f"{project.project_name}项目不位于地质灾害易发区。")
    return paragraphs


def _build_cultivated_land_detail_paragraphs(project: ProjectSiteSelectionData) -> list:
    """
    根据项目数据生成占用耕地和永久基本农田逐县逐乡镇段落文本

    遍历项目涉及的县和乡镇，对每个涉及耕地或永久基本农田的乡镇
    生成一段描述文本。若均不涉及，生成不涉及声明。

    Args:
        project: 项目选址数据

    Returns:
        list: 段落文本列表
    """
    paragraphs = []
    has_any = False
    for county in project.counties:
        # 县级汇总
        county_cultivated = county.area_detail.cultivated_land
        county_paddy = county.area_detail.paddy_field
        county_black = county.area_detail.black_soil
        county_farmland = county.area_detail.permanent_basic_farmland

        if county_cultivated.is_involved or county_farmland.is_involved:
            has_any = True
            town_names = "、".join(t.name for t in county.towns) if county.towns else county.name
            paragraphs.append(
                f"{project.project_name}项目占用{county.name}、{town_names}"
                f"耕地{_format_area(county_cultivated.value)}公顷"
                f"（其中水田{_format_area(county_paddy.value)}公顷、"
                f"黑土耕地{_format_area(county_black.value)}公顷）"
                f"和永久基本农田{_format_area(county_farmland.value)}公顷。"
            )

    if not has_any:
        paragraphs.append(f"{project.project_name}项目不涉及永久占用耕地和永久基本农田。")
    return paragraphs


def _build_ecological_red_line_paragraph(project: ProjectSiteSelectionData) -> str:
    """
    根据项目数据生成涉及生态保护红线情况段落文本

    根据生态保护红线的 is_involved 字段判断选择何种文本模板，
    涉及时附带法规引用。

    Args:
        project: 项目选址数据

    Returns:
        str: 生态保护红线情况段落文本
    """
    # 使用汇总数据
    red_line = project.summary.ecological_red_line
    if red_line > 0:
        return (
            f"{project.project_name}项目涉及生态保护红线{_format_area(red_line)}公顷，"
            f"按规定应符合《自然资源部 生态环境部 国家林业和草原局关于加强生态保护红线管理的通知（试行）》"
            f"（自然资发〔2022〕142号）有关规定。"
        )
    return f"{project.project_name}项目不涉及生态保护红线。"


def _build_nature_reserve_paragraph(project: ProjectSiteSelectionData) -> str:
    """
    根据项目数据生成涉及自然保护地情况段落文本

    根据自然保护地的 is_involved 字段判断选择何种文本模板。

    Args:
        project: 项目选址数据

    Returns:
        str: 自然保护地情况段落文本
    """
    # 检查各县是否有涉及自然保护地
    has_reserve = any(
        county.area_detail.nature_reserve.is_involved
        for county in project.counties
    )
    if has_reserve:
        total_value = sum(
            county.area_detail.nature_reserve.value
            for county in project.counties
            if county.area_detail.nature_reserve.is_involved
        )
        return f"{project.project_name}项目占用自然保护地{_format_area(total_value)}公顷，应符合自然保护地管理规定。"
    return f"{project.project_name}项目用地不位于自然保护地范围内。"


def _build_illegal_land_paragraph(project: ProjectSiteSelectionData) -> str:
    """
    根据项目数据生成违法用地情况段落文本

    根据违法用地的 is_involved 字段判断选择何种文本模板。

    Args:
        project: 项目选址数据

    Returns:
        str: 违法用地情况段落文本
    """
    has_illegal = any(
        county.area_detail.illegal_land.is_involved
        for county in project.counties
    )
    if has_illegal:
        total_value = sum(
            county.area_detail.illegal_land.value
            for county in project.counties
            if county.area_detail.illegal_land.is_involved
        )
        return f"{project.project_name}项目用地范围内涉及疑似违法用地，疑似违法用地面积{_format_area(total_value)}公顷。"
    return f"{project.project_name}项目用地范围内无疑似违法用地。"


def _build_forest_grassland_paragraph(project: ProjectSiteSelectionData) -> str:
    """
    根据项目数据生成林草地占用情况段落文本

    根据林地和草地的 is_involved 字段判断选择何种文本模板，
    涉及时按县乡镇列举面积。

    Args:
        project: 项目选址数据

    Returns:
        str: 林草地占用情况段落文本
    """
    has_forest = any(
        county.area_detail.forest_land.is_involved
        for county in project.counties
    )
    has_grassland = any(
        county.area_detail.grassland.is_involved
        for county in project.counties
    )

    if not has_forest and not has_grassland:
        return (
            f"依据{project.reference_year}国土变更调查和林草湿荒普查成果，"
            f"{project.project_name}项目用地不涉及占用林地、草地。"
        )

    # 涉及林草地，按县列举
    detail_parts = []
    for county in project.counties:
        county_forest = county.area_detail.forest_land
        county_grassland = county.area_detail.grassland
        if county_forest.is_involved or county_grassland.is_involved:
            town_names = "、".join(t.name for t in county.towns) if county.towns else county.name
            parts = []
            if county_forest.is_involved:
                parts.append(f"林地{_format_area(county_forest.value)}公顷")
            if county_grassland.is_involved:
                parts.append(f"草地{_format_area(county_grassland.value)}公顷")
            detail_parts.append(f"{county.name}、{town_names}{'、'.join(parts)}")

    return (
        f"依据{project.reference_year}国土变更调查和林草湿荒普查成果，"
        f"{project.project_name}项目用地涉及占用{'、'.join(detail_parts)}。"
    )


def _build_land_use_efficiency_paragraphs(project: ProjectSiteSelectionData) -> list[str]:
    """
    根据项目数据生成节约集约用地段落文本

    从 project 中安全获取 project_type 和 land_use_control_indicator，
    若属性不存在则使用 'xx' 占位符。保留符合/不符合两条文本。

    Args:
        project: 项目选址数据

    Returns:
        list[str]: 段落文本列表
    """
    project_type = getattr(project, "project_type", "xx")
    indicator = getattr(project, "land_use_control_indicator", "xx")
    total_area = _format_area(project.summary.total_land_area)

    paragraphs = [
        f"{project.project_name}项目用地总面积{total_area}公顷，"
        f"{project_type}类建设项目建设用地控制指标为{indicator}公顷，"
        f"初步判定用地规模符合土地使用标准。",
        f"【或者】：{project.project_name}项目用地总面积{total_area}公顷，"
        f"{project_type}类建设项目建设用地控制指标为{indicator}公顷，"
        f"初步判定用地规模不符合土地使用标准。",
    ]
    return paragraphs


def _build_section_disclaimer(collection: ProjectSiteSelectionCollection) -> list[dict]:
    """
    构建"一点通"服务免责声明章节

    根据 ProjectSiteSelectionCollection 中的项目名称，
    动态生成包含项目信息的免责声明内容。

    Args:
        collection: 多项目选址数据集合

    Returns:
        list[dict]: 章节段落列表
    """
    # 获取项目名称：单项目直接使用项目名称，多项目使用集合名称
    if len(collection.projects) == 1:
        project_name = collection.projects[0].project_name
    else:
        project_name = collection.collection_name

    return [
        # 一级标题：居中
        {"type": "heading", "level": 1, "alignment": 1, "content": "\"一点通\"服务免责声明"},
        # 第一段正文
        {
            "type": "paragraph",
            "alignment": 0,
            "content": f"欢迎使用沈阳市自然资源和规划\"一点通\"服务（以下简称\"本服务\"）。本服务由沈阳市自然资源局研发，用于生成《{project_name}选址自然资源和规划\"一点通\"服务技术参考》（以下简称《技术参考》），作为项目选址咨询的过程性参考材料。为保障您的合法权益，请在使用本服务前仔细阅读并充分理解本声明全部内容。若您继续使用本服务，即视为已完全知晓、理解并同意本声明的全部条款及内容。本服务将免费向您提供《技术参考》。"
        },
        # 一、查询结果用途限制
        {"type": "heading", "level": 1, "alignment": 0, "content": "一、查询结果用途限制", "in_toc": False},
        {
            "type": "paragraph",
            "alignment": 0,
            "content": "（一）本服务提供的选址分析结果（包括图表、文档、数据等）仅供项目选址参考，不具备法律或行政效力，不可直接用于以下场景："
        },
        {"type": "paragraph", "alignment": 0, "content": "1. 行政审批、政府信息公开申请、行政复议、行政诉讼、行政裁定、信访等程序；"},
        {"type": "paragraph", "alignment": 0, "content": "2. 市场宣传、营利活动（如广告、投资推介）或不正当竞争行为；"},
        {"type": "paragraph", "alignment": 0, "content": "3. 其他可能损害本单位、第三方、国家或社会公共利益的行为；"},
        {"type": "paragraph", "alignment": 0, "content": "4. 法律法规禁止的其他行为。"},
        {
            "type": "paragraph",
            "alignment": 0,
            "content": "（二）严禁歪曲、篡改、恶意解读或公开发布查询结果。严禁利用查询结果制造、散布不良社会舆论，或从事任何可能损害政府公信力、扰乱社会秩序的活动。"
        },
        # 二、数据时效性与准确性
        {"type": "heading", "level": 1, "alignment": 0, "content": "二、数据时效性与准确性", "in_toc": False},
        {
            "type": "paragraph",
            "alignment": 0,
            "content": "（一）《技术参考》基于沈阳市自然资源管理和国土空间规划\"一张图\"平台现有入库数据自动生成，受数据更新周期、技术口径、现场条件影响，可能与实际情况存在差异。仅供选址咨询参考，不代表审批意见。"
        },
        {
            "type": "paragraph",
            "alignment": 0,
            "content": "（二）项目选址合规性、用地可行性最终以行业主管部门正式审查、审批结论为准。"
        },
        # 三、保密与数据安全责任
        {"type": "heading", "level": 1, "alignment": 0, "content": "三、保密与数据安全责任", "in_toc": False},
        {
            "type": "paragraph",
            "alignment": 0,
            "content": "用户应严格遵守《中华人民共和国保守国家秘密法》《中华人民共和国数据安全法》《中华人民共和国测绘法》等相关法律法规、规章及规范性文件的规定，对通过本服务查询获取的结果信息履行保密义务。"
        },
        {
            "type": "paragraph",
            "alignment": 0,
            "content": "严禁以任何方式或技术手段窃取、篡改、非法利用本服务系统数据。因用户行为导致数据泄露或损害公共利益的，本单位有权追究法律责任。"
        },
        # 四、责任豁免
        {"type": "heading", "level": 1, "alignment": 0, "content": "四、责任豁免", "in_toc": False},
        {
            "type": "paragraph",
            "alignment": 0,
            "content": "因以下行为产生的一切后果由用户自行承担，本单位不承担任何直接或间接责任："
        },
        {
            "type": "paragraph",
            "alignment": 0,
            "content": "（一）不当使用本服务或超出声明允许范围的行为（如未经授权的数据修改、非法传播）；"
        },
        {"type": "paragraph", "alignment": 0, "content": "（二）因数据误差导致的决策损失。"},
        # 五、特别声明
        {"type": "heading", "level": 1, "alignment": 0, "content": "五、特别声明", "in_toc": False},
        {
            "type": "paragraph",
            "alignment": 0,
            "content": "（一）本服务中各类数据的所有权、解释权及更新责任归属各原始数据管理部门（如自然资源主管部门、生态环境主管部门等）。用户如需政策咨询，请直接联系相关部门。"
        },
        {
            "type": "paragraph",
            "alignment": 0,
            "content": "（二）本服务提供的《技术参考》不属于《中华人民共和国政府信息公开条例》规定的政务信息公开范畴，如需政务公开数据，请依法向相关部门申请。"
        },
        {
            "type": "paragraph",
            "alignment": 0,
            "content": "（三）用户违反本声明的，本单位将通过一切合法途径维护自身权益、政府公信力及社会公共利益。"
        },
        {
            "type": "paragraph",
            "alignment": 0,
            "content": "（四）本《技术参考》属于行政咨询指导行为、过程性信息，依据《最高人民法院关于适用〈中华人民共和国行政诉讼法〉的解释》第一条第二款第三项、第六项、第十项，本服务不可复议、不可诉。"
        },
        # 六、声明约束力及解释权
        {"type": "heading", "level": 1, "alignment": 0, "content": "六、声明约束力及解释权", "in_toc": False},
        {
            "type": "paragraph",
            "alignment": 0,
            "content": "本声明自用户使用本服务时起生效，使用行为即视为接受全部条款。"
        },
        {
            "type": "paragraph",
            "alignment": 0,
            "content": "本声明的最终解释权和修订权归本单位所有。"
        },
        # 落款：右对齐
        {"type": "paragraph", "alignment": 2, "content": "沈阳市自然资源局"},
    ]


def _build_section_site_selection(collection: ProjectSiteSelectionCollection) -> list[dict]:
    """
    构建一、项目选址与要素保障章节

    根据 ProjectSiteSelectionCollection 中的项目数据，
    动态生成各三级标题下的段落文本。多项目时每个项目生成独立段落。

    Args:
        collection: 多项目选址数据集合

    Returns:
        list[dict]: 章节段落列表
    """
    sections = [
        {"type": "page_break"},
        {"type": "heading", "level": 1, "content": "一、项目选址与要素保障"},
        {"type": "heading", "level": 2, "content": "（一）项目选址选线"},
        {"type": "heading", "level": 3, "content": "1.土地利用状况"},
    ]

    # 1.土地利用状况：每个项目生成一段
    for project in collection.projects:
        sections.append({"type": "paragraph", "content": _build_land_use_paragraph(project)})

    # 2.涉及矿产压覆及地质灾害易发区情况
    sections.append({"type": "heading", "level": 3, "content": "2.涉及矿产压覆及地质灾害易发区情况"})
    for project in collection.projects:
        for para in _build_mineral_press_paragraphs(project):
            sections.append({"type": "paragraph", "content": para})

    # 3.占用耕地和永久基本农田情况（逐县明细）
    sections.append({"type": "heading", "level": 3, "content": "3.占用耕地和永久基本农田情况"})
    for project in collection.projects:
        for para in _build_cultivated_land_detail_paragraphs(project):
            sections.append({"type": "paragraph", "content": para})

    # 4.涉及生态保护红线情况
    sections.append({"type": "heading", "level": 3, "content": "4.涉及生态保护红线情况"})
    for project in collection.projects:
        sections.append({"type": "paragraph", "content": _build_ecological_red_line_paragraph(project)})

    # 5.项目类型及供地方式（固定占位文本）
    sections.append({"type": "heading", "level": 3, "content": "5.项目类型及供地方式"})
    sections.append({"type": "paragraph", "content": "符合《划拨用地目录》第（x）项xxx用地（明确所对应的项目类型），可按照划拨或出让方式供地。"})
    sections.append({"type": "paragraph", "content": "【或者】：项目类型（能源、交通、水利等），不符合《划拨用地目录》要求，应按照出让方式供地。"})

    # （二）要素保障分析
    sections.append({"type": "heading", "level": 2, "content": "（二）要素保障分析"})
    sections.append({"type": "heading", "level": 3, "content": "1.相关的国土空间规划"})
    sections.append({"type": "paragraph", "content": "（1）自然资源管理和国土空间规划\"一张图\"落位情况。项目未在自然资源管理和国土空间规划\"一张图\"上图落位。"})
    sections.append({"type": "paragraph", "content": "【或者】：项目已在自然资源管理和国土空间规划\"一张图\"上图落位。"})
    sections.append({"type": "paragraph", "content": "（2）国土空间总体规划。《xx级国土空间总体规划》重点项目安排表中的\"xxx项目\"与该项目一致，符合《xx级国土空间总体规划》。"})
    sections.append({"type": "paragraph", "content": "【或者】：《xx级国土空间总体规划》重点项目安排表中未查询到该项目名称，不符合《xx级国土空间总体规划》。"})
    sections.append({"type": "paragraph", "content": "（3）国土空间详细规划。项目用地符合xx详细规划或xx村庄规划。"})
    sections.append({"type": "paragraph", "content": "【或者】：项目用地无xx详细规划或xx村庄规划。"})
    sections.append({"type": "paragraph", "content": "（4）国土空间专项规划。项目已纳入xx专项规划。"})
    sections.append({"type": "paragraph", "content": "【或者】：经查询，该项目名称未查询到相关专项规划。"})
    sections.append({"type": "heading", "level": 3, "content": "2.土地利用年度计划"})
    sections.append({"type": "paragraph", "content": "该项目可按规定配置用地计划指标。"})
    sections.append({"type": "heading", "level": 3, "content": "3.节约集约用地"})
    for project in collection.projects:
        for para in _build_land_use_efficiency_paragraphs(project):
            sections.append({"type": "paragraph", "content": para})
    sections.append({"type": "heading", "level": 3, "content": "4.农用地转用和土地征收手续办理安排"})
    sections.append({"type": "paragraph", "content": "在项目审批（核准）阶段同步开展农用地转用和土地征收前期工作。"})
    sections.append({"type": "heading", "level": 3, "content": "5.耕地占补平衡可行性"})
    sections.append({"type": "paragraph", "content": "项目不涉及占用耕地。"})
    sections.append({"type": "paragraph", "content": "【或者】：项目占用耕地xx公顷，占用耕地质量等别为xx，坡度级别为xx，产能约xx公斤，应在农用地转用和土地征收阶段按规定落实补充耕地。经核实，当前xx县（市、区）补充耕地储备库中指标可满足该项目补充耕地需求。"})
    sections.append({"type": "heading", "level": 3, "content": "6.永久基本农田占用补划可行性"})
    sections.append({"type": "paragraph", "content": "项目不涉及占用永久基本农田。"})
    sections.append({"type": "paragraph", "content": "【或者】：项目占用永久基本农田xx公顷，应按规定办理永久基本农田占用补划手续。"})

    return sections


def _build_section_space_control(collection: ProjectSiteSelectionCollection) -> list[dict]:
    """
    构建二、其他空间管控分析章节

    根据 ProjectSiteSelectionCollection 中的项目数据，
    为每个项目生成主体功能区占位段落，以及自然保护地和历史文化保护内容。

    Args:
        collection: 多项目选址数据集合

    Returns:
        list[dict]: 章节段落列表
    """
    sections = [
        {"type": "heading", "level": 1, "content": "二、其他空间管控分析"},
    ]
    for project in collection.projects:
        sections.append({
            "type": "paragraph",
            "content": f"{project.project_name}项目用地所在区域主体功能区为城市化地区/农产品主产区/重点生态功能区及特殊功能区。",
        })

    sections.append({"type": "heading", "level": 2, "content": "（一）涉及自然保护地情况"})
    for project in collection.projects:
        sections.append({"type": "paragraph", "content": _build_nature_reserve_paragraph(project)})

    sections.append({"type": "heading", "level": 2, "content": "（二）历史文化保护情况"})
    sections.append({"type": "paragraph", "content": "项目涉及历史文化名城名镇名村。"})
    sections.append({"type": "paragraph", "content": "【或者】：项目不涉及历史文化名城名镇名村。"})

    return sections


def _build_section_land_use(collection: ProjectSiteSelectionCollection) -> list[dict]:
    """
    构建三、其他国土空间用途管制要求章节

    根据 ProjectSiteSelectionCollection 中的项目数据，
    动态生成违法用地、信访和林草地占用情况段落。

    Args:
        collection: 多项目选址数据集合

    Returns:
        list[dict]: 章节段落列表
    """
    sections = [
        {"type": "heading", "level": 1, "content": "三、其他国土空间用途管制要求"},
        {"type": "heading", "level": 2, "content": "（一）违法用地情况"},
    ]
    for project in collection.projects:
        sections.append({"type": "paragraph", "content": _build_illegal_land_paragraph(project)})

    sections.append({"type": "heading", "level": 2, "content": "（二）涉及信访情况"})
    sections.append({"type": "paragraph", "content": "项目用地范围内不涉及信访问题。"})
    sections.append({"type": "paragraph", "content": "【或者】：项目用地范围内涉及信访问题，应按规定处理。"})

    sections.append({"type": "heading", "level": 2, "content": "（三）林草地占用情况"})
    for project in collection.projects:
        sections.append({"type": "paragraph", "content": _build_forest_grassland_paragraph(project)})

    return sections


def _build_section_tips(collection: ProjectSiteSelectionCollection) -> list[dict]:
    """
    构建※《技术参考》使用提示章节

    根据 ProjectSiteSelectionCollection 中的项目数据，
    动态生成违法用地和林草地占用情况段落。

    Args:
        collection: 多项目选址数据集合

    Returns:
        list[dict]: 章节段落列表
    """
    sections = [
        {"type": "page_break"},
        {"type": "heading", "level": 1, "content": "※《技术参考》使用提示："},
        {"type": "paragraph","bold": True, "content": "1.本《技术参考》有关结论依据项目单位提供的项目范围，基于自然资源管理和国土空间规划\"一张图\"平台数据核实形成，无人工实质性审查环节，仅为项目前期咨询参考材料，如对核实结果有疑问，建议咨询相关数据主管部门。"},
        {"type": "paragraph","bold": True, "content": "2.本服务属于行政指导行为，不产生强制约束力，不属于行政复议、行政诉讼受案范围。"},
        {"type": "paragraph", "bold": True,"content": "3.本《技术参考》所有内容仅反映数据比对的阶段性状态，后续因规划调整、政策更新、数据修正产生的内容变动，本单位不承担主动告知义务。"},
        {"type": "paragraph", "bold": True,"content": "4.项目单位可依托本《技术参考》开展前期工作，作为项目单位编制项目选址综合论证报告和项目可行性研究报告等参考，但不作为自然资源主管部门规划与用地审批意见，不具备行政审批效力，最终以正式审批为准。"},
    ]

    return sections


def _load_report_content(collection: ProjectSiteSelectionCollection) -> list[dict]:
    """
    拼装报告正文内容

    通过调用各章节构建子方法，拼装完整的报告内容列表。
    每个子方法负责构建一个 level 1 章节的内容，
    根据 ProjectSiteSelectionCollection 中的数据动态生成段落文本。

    Args:
        collection: 多项目选址数据集合

    Returns:
        list[dict]: 段落内容列表，每个元素包含type、level、content等字段
    """
    sections = []
    sections.extend(_build_section_disclaimer(collection))
    sections.extend(_build_section_site_selection(collection))
    sections.extend(_build_section_space_control(collection))
    sections.extend(_build_section_land_use(collection))
    sections.extend(_build_section_tips(collection))
    return sections


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
                alignment=item.get("alignment"),
                in_toc=item.get("in_toc", True),
            ))
        elif section_type == "paragraph":
            sections.append(SectionConfig(
                section_type="paragraph",
                content=item.get("content", ""),
                alignment=item.get("alignment"),
                bold=item.get("bold"),
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
            font_size=16,
            bold=False,
            space_before=0,
            space_after=0,
            left_indent=0,
        ),
        2: HeadingStyleConfig(
            font_name="楷体",
            font_size=16,
            bold=False,
            space_before=0,
            space_after=0,
            left_indent=0.74,
        ),
        3: HeadingStyleConfig(
            font_name="方正仿宋_GB2312",
            font_size=16,
            bold=True,
            space_before=0,
            space_after=0,
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
        font_name="仿宋",
        font_size=16,
        bold=False,
        first_line_indent_chars=2,
        line_spacing_rule="auto",
        line_spacing_value=1.5,
        space_before=0,
        space_after=0,
        left_indent=0,
    )


def get_report_config(data: dict, collection: ProjectSiteSelectionCollection = None) -> ReportConfig:
    """
    构建MapAgent专用的报告配置

    根据传入的数据字典和项目选址数据集合，构建包含封面、目录、正文段落的完整报告配置对象。
    正文内容根据 ProjectSiteSelectionCollection 中的数据动态生成，
    样式通过统一样式配置管理。
    封面标题使用"{{项目名称}}项目选址自然资源和规划"一点通"服务技术参考"格式，日期使用"{{生成日期}}"占位符。

    Args:
        data: 变量替换数据字典，应包含以下键：
            - 项目名称: 报告标题中的项目名称
            - 生成日期: 报告生成日期，如"2026年5月12日"
            以及其他需要在正文中使用的变量
        collection: 多项目选址数据集合，用于动态生成报告正文。
            若为None，则使用空的集合生成占位文本。

    Returns:
        ReportConfig: 完整的报告配置对象，可直接用于WordReportGenerator

    Example:
        >>> collection = ProjectSiteSelectionCollection(
        ...     collection_id="batch_001",
        ...     collection_name="2024年新能源项目批次",
        ...     projects=[...]
        ... )
        >>> config = get_report_config({
        ...     "项目名称": "XX高速公路",
        ...     "生成日期": "2026年5月12日",
        ... }, collection=collection)
        >>> generator = WordReportGenerator(config)
        >>> doc = generator.generate()
    """
    if collection is None:
        collection = ProjectSiteSelectionCollection(
            collection_id="default",
            collection_name="默认集合",
            projects=[],
        )

    # 将 data 中的面积字段从平方米转换为公顷
    # 避免修改原始字典，创建副本进行处理
    processed_data = data.copy()
    area_keys = ["用地总面积", "农用地面积", "林地面积", "用海面积"]
    for key in area_keys:
        if key in processed_data:
            processed_data[key] = str(convert_square_meters_to_hectares(processed_data[key]))

    # 将 collection 中所有 area_detail 的面积字段从平方米转换为公顷
    for project in collection.projects:
        _convert_area_summary(project.summary)
        for county in project.counties:
            _convert_region_area_detail(county.area_detail)
            for town in county.towns:
                _convert_region_area_detail(town.area_detail)
                for village in town.villages:
                    _convert_region_area_detail(village.area_detail)

    cover = CoverConfig(
        title=CoverElementConfig(
            text="{{项目名称}}项目选址自然资源和规划“一点通”服务技术参考",
            font_name="黑体",
            font_size=22,
            bold=True,
            space_before=3,
            space_after=0,
        ),
        subtitle=CoverElementConfig(
            text="技术参考",
            font_name="宋体",
            font_size=22,
            bold=True,
            space_before=0,
            space_after=0,
        ),
        custom_elements=[
            CoverElementConfig(
                text="项目类型：{{项目类型}}",
                font_name="宋体",
                font_size=16,
                bold=True,
                space_before=11,
                space_after=0,
            ),
            CoverElementConfig(
                text="生成日期：{{生成日期}}",
                font_name="宋体",
                font_size=16,
                bold=True,
                space_before=0,
                space_after=0,
            ),
        ],
        footer_note=CoverElementConfig(
            text='（根据查询时间的"一张图"数据分析结果，仅供参考）',
            font_name="宋体",
            font_size=10,
            bold=False,
            space_before=2,
            space_after=0,
        ),
    )

    toc = TocConfig(
        title="目 录",
        title_font_name="黑体",
        title_font_size=16,
        title_bold=True,
        entries=[
            TocEntry(text="\"一点通\"服务免责声明", level=0, bold=True, font_name="黑体", font_size=15),
            TocEntry(text="一、项目选址与要素保障", level=0, bold=True, font_name="黑体", font_size=15),
            TocEntry(text="（一）项目选址选线", level=1, font_name="楷体", font_size=14),
            TocEntry(text="1. 土地利用状况", level=2, font_name="方正仿宋_GB2312"),
            TocEntry(text="2. 涉及矿产压覆及地质灾害易发区情况", level=2, font_name="方正仿宋_GB2312"),
            TocEntry(text="3. 占用耕地和永久基本农田情况", level=2, font_name="方正仿宋_GB2312"),
            TocEntry(text="4. 涉及生态保护红线情况", level=2, font_name="方正仿宋_GB2312"),
            TocEntry(text="5. 项目类型及供地方式", level=2, font_name="方正仿宋_GB2312"),
            TocEntry(text="（二）要素保障分析", level=1, font_name="楷体", font_size=14),
            TocEntry(text="1. 相关的国土空间规划", level=2, font_name="方正仿宋_GB2312"),
            TocEntry(text="2. 土地利用年度计划", level=2, font_name="方正仿宋_GB2312"),
            TocEntry(text="3. 节约集约用地", level=2, font_name="方正仿宋_GB2312"),
            TocEntry(text="4. 农用地转用和土地征收手续办理安排", level=2, font_name="方正仿宋_GB2312"),
            TocEntry(text="5. 耕地占补平衡可行性", level=2, font_name="方正仿宋_GB2312"),
            TocEntry(text="6. 永久基本农田占用补划可行性", level=2, font_name="方正仿宋_GB2312"),
            TocEntry(text="二、 其他空间管控分析", level=0, bold=True, font_name="黑体", font_size=15),
            TocEntry(text="（一）涉及自然保护地情况", level=1, font_name="楷体", font_size=14),
            TocEntry(text="（二）历史文化保护情况", level=1, font_name="楷体", font_size=14),
            TocEntry(text="三、其他国土空间用途管制要求", level=0, bold=True, font_name="黑体", font_size=15),
            TocEntry(text="（一） 违法用地情况", level=1, font_name="楷体", font_size=14),
            TocEntry(text="（二） 涉及信访情况", level=1, font_name="楷体", font_size=14),
            TocEntry(text="（三）林草地占用情况", level=1, font_name="楷体", font_size=14),
            TocEntry(text="※《技术参考》使用提示：", level=0, bold=True, font_name="黑体", font_size=15)
        ],
        entry_font_name="宋体",
        entry_font_size=12,
        indent_per_level=0.74,
    )

    content_list = _load_report_content(collection)
    sections = _build_sections(content_list)

    return ReportConfig(
        page_setup=PageSetup(),
        cover=cover,
        toc=toc,
        sections=sections,
        data=processed_data,
        default_font_name="宋体",
        default_font_size=12,
        heading_styles=_get_heading_styles(),
        paragraph_style=_get_paragraph_style(),
        footer=FooterConfig(
            format="-{page}-",
        ),
    )
