#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
Ollama图片识别测试程序
使用滚动窗口机制，每次只处理一张图片，避免内存占用过高

Date: 2026/1/9 12:07
Author: 张镒谱
"""
from app.agents.llmcalls.ollama import create_model
from langchain.messages import ToolMessage, AIMessage, HumanMessage, SystemMessage
from pathlib import Path
from langchain.tools import tool, ToolRuntime
from langchain_core.tools import BaseTool
from dataclasses import dataclass
from langchain.agents import create_agent
@tool("recognize_images",description="返回降雨情况")
def recognize_images() -> str:
        """
        返回降雨情况
        """
        
        print(f"路过识别图片方法~~~~~~~~~~~~~~~~~~~~~~")
        return "1234456"

@tool("extract_fields",description="返回温度情况")
def extract_fields() -> dict:
        """返回温度情况"""
        print(f"路过提取字段方法~~~~~~~~~~~~~~~~~~~~~~")
        return {"容积率": "1.5"}

@tool("analyze_document",description="分析文档图片")
def analyze_document( image_paths: list[str]) -> dict:
        """分析文档图片"""
        print(f"路过分析文档方法~~~~~~~~~~~~~~~~~~~~~~")
        return {"分析类型": "降雨和温度情况", "结果": "分析结果"}
    
class ImageChatbot:
    def __init__(self, model_name: str = "qwen3-vl:30b", temperature: float = 0.0):
        
        self.model = create_model(
            model_name=model_name,
            api_key=None,
            temperature=temperature,
            base_url="http://192.168.1.107:11434"
        )
        self.model=self.model.bind_tools([recognize_images, extract_fields, analyze_document])
        # 绑定工具,通过映射调用工具
        self.model_tools_names = ["recognize_images", "extract_fields", "analyze_document"]
        self.model_bind_tools=[recognize_images, extract_fields, analyze_document]
        self.agent = create_agent(
            model=self.model,
            tools=self.model_bind_tools,
            system_prompt="你是一个乐于助人的助手",
        )
    def run(self, query: str) -> str:
        """
        运行图片识别助手
        Args:
            query (str): 用户查询
        Returns:
            str: 助手回复
        """
        response = self.agent.invoke({"input": query})
        return response["messages"][-1].content
    

    
    
    def recognize_images(self, image_paths: list[str] | None = None, prompt: str = "描述这些图片") -> str:
        if image_paths is None or len(image_paths) == 0:
            messages = [HumanMessage(content=prompt)]
        else:
            content = [{"type": "text", "text": prompt}]
            for path in image_paths:
                content.append({"type": "image_url", "image_url": {"url": path}})
            messages = [HumanMessage(content=content)]
        response = self.model.invoke(messages)
        return response.content

    def recognize_image(self, image_path: str, prompt: str = "描述这张图片") -> str:
        return self.recognize_images([image_path], prompt)


def recognize_image(image_path: str, prompt: str = "请详细描述这张图片的内容"):
    chatbot = ImageChatbot(model_name="qwen3-vl:30b", temperature=0.1)
    return chatbot.recognize_image(image_path, prompt)


def recognize_multiple_images(image_paths: list[str], prompt: str = "请描述所有图片"):
    chatbot = ImageChatbot(model_name="qwen3-vl:30b", temperature=0.1)
    return chatbot.recognize_images(image_paths, prompt)


class SlidingWindowImageProcessor:
    def __init__(self, window_size: int = 2, step: int = 1):
        self.window_size = window_size
        self.step = step
    
    
    def get_sliding_windows(
        self,
        image_groups: list[list[str]]
    ) -> list[dict]:
        windows = []
        for group_idx, image_group in enumerate(image_groups):
            if len(image_group) <= self.window_size:
                windows.append({
                    "group_index": group_idx,
                    "image_paths": image_group,
                    "window_start": 0,
                    "window_end": len(image_group)
                })
                continue

            for start_idx in range(0, len(image_group), self.step):
                end_idx = min(start_idx + self.window_size, len(image_group))
                window_images = image_group[start_idx:end_idx]

                if start_idx > 0:
                    overlap_end = min(start_idx + self.window_size - 1, len(image_group))
                    window_images = image_group[start_idx-1:overlap_end]

                windows.append({
                    "group_index": group_idx,
                    "image_paths": window_images,
                    "window_start": start_idx,
                    "window_end": end_idx
                })

                if end_idx >= len(image_group):
                    break

        return windows

    def get_images_with_sliding_window(
        self,
        image_paths: list[str]
    ) -> list[dict]:
        return self.get_sliding_windows([image_paths])


def get_images_from_folder(folder_path: str, extensions: tuple = (".jpg", ".jpeg", ".png", ".bmp")) -> list[str]:
    folder = Path(folder_path)
    image_files = sorted([str(f) for f in folder.iterdir() if f.suffix.lower() in extensions])
    return image_files


def generate_multi_field_prompt() -> str:
    """生成多字段提取的提示词"""
    return """你是一个专业的文档信息提取助手。请从图片中提取以下信息：

## 需要提取的字段：

1. **容积率**
   - 类型: 单一数值
   - 说明: 在综合技术指标表中查找容积率数值
   - JSON路径: `floor_area_ratio`

2. **建设工程规划许可证**
   - 类型: 许可证编号
   - 说明: 查找许可证上的编号，只需要纯数字或字母数字组合
   - 示例: "130400202200065" 或 "2026-001号"
   - 重要: 不要包含"建设工程规划许可证号："等前缀文字，只返回编号本身
   - JSON路径: `planning_license`

3. **主要建筑物一览表-长度**
   - 类型: 表格数据
   - 说明: 从主要建筑物一览表中提取所有建筑物的长度（米）数据
   - JSON路径: `building_lengths`

## 返回格式要求：

请严格按照以下JSON格式返回结果：

```json
{
    "floor_area_ratio": "2.5",
    "planning_license": "130400202200065",
    "building_lengths": ["120m", "85m"]
}
```

## 重要说明：

1. **许可证格式**: 只返回编号本身，不要前缀文字，如 "130400202200065" 而不是 "建设工程规划许可证号：130400202200065"
2. **跨页处理**: 如果某个字段的信息分散在多张图片中，请综合所有图片的信息进行提取
3. **表格处理**: 对于建筑物长度列表，按顺序提取所有建筑物的长度
4. **缺失处理**: 如果某个字段在所有图片中都未找到，设置其值为 `null`（文本）或 `[]`（列表）
5. **准确性**: 只提取你确定的信息，不要猜测或推理

请开始提取信息，严格按照JSON格式返回。"""


def clean_license_number(text: str) -> str:
    """清理许可证编号，去除可能的前缀文字"""
    import re
    # 去除常见前缀模式
    patterns = [
        r'建设工程规划许可证[：:\s]*',
        r'许可证[：:\s]*',
        r'编号[：:\s]*',
        r'证号[：:\s]*',
    ]
    cleaned = text
    for pattern in patterns:
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def merge_multi_field_results(results: list[dict]) -> dict:
    """合并多窗口的多字段提取结果"""
    merged = {
        "floor_area_ratio": None,
        "planning_license": None,
        "building_lengths": []
    }
    
    for window_result in results:
        content = window_result.get('result', '')
        
        # 尝试提取各个字段
        import re
        
        # 提取容积率
        floor_ratio_match = re.search(r'"floor_area_ratio"\s*:\s*"([^"]+)"', content)
        if floor_ratio_match and merged["floor_area_ratio"] is None:
            merged["floor_area_ratio"] = floor_ratio_match.group(1)
        
        # 提取许可证（清理前缀）
        license_match = re.search(r'"planning_license"\s*:\s*"([^"]+)"', content)
        if license_match and merged["planning_license"] is None:
            raw_license = license_match.group(1)
            merged["planning_license"] = clean_license_number(raw_license)
        
        # 提取建筑物长度列表
        lengths_match = re.search(r'"building_lengths"\s*:\s*\[([^\]]+)\]', content)
        if lengths_match:
            lengths_str = lengths_match.group(1)
            lengths = re.findall(r'"([^"]+)"', lengths_str)
            merged["building_lengths"].extend(lengths)
    
    # 去重建筑物长度（保持顺序）
    seen = set()
    unique_lengths = []
    for length in merged["building_lengths"]:
        if length not in seen:
            seen.add(length)
            unique_lengths.append(length)
    merged["building_lengths"] = unique_lengths
    
    return merged


def process_all_fields(chatbot: ImageChatbot, windows: list[dict]) -> dict:
    """使用多字段提示词处理所有窗口并合并结果"""
    prompt = generate_multi_field_prompt()
    
    results = []
    for window in windows:
        print(f"处理窗口: {window['image_paths']}")
        result = chatbot.recognize_images(window['image_paths'], prompt)
        window['result'] = result
        results.append(window)
        print(f"识别结果: {result}\n")
    
    merged_result = merge_multi_field_results(results)
    
    return merged_result







    

if __name__ == "__main__":
    
    
    agent =  ImageChatbot(model_name="qwen3-vl:30b", temperature=0.1)
    agent.recognize_images(prompt=r"获取降雨和温度情况")
    agent.run(r"获取降雨和温度情况")
    folder_path = r'E:\laboratory\AI\Agents\app\data\upload\418353f9-0902-4641-b4b7-12f516bc3faf\35d43c19-5e2c-4d53-b962-3bb90aba70d3\c2f44085-5ae9-4a18-9b8c-795aa43a279c'
    image_paths = get_images_from_folder(folder_path)
    print(f"找到 {len(image_paths)} 张图片:")
    for img in image_paths:
        print(f"  - {img}")

    processor = SlidingWindowImageProcessor(window_size=2, step=1)
    windows = processor.get_images_with_sliding_window(image_paths)

    chatbot = ImageChatbot(model_name="qwen3-vl:30b", temperature=0.1)

    # 使用新的多字段提取功能
    print("\n" + "=" * 50)
    print("开始多字段提取（容积率、许可证、建筑物长度）")
    print("=" * 50 + "\n")

    final_result = process_all_fields(chatbot, windows)

    print("=" * 50)
    print("所有窗口处理完成!")
    print(f"共处理 {len(windows)} 个窗口")
    print("\n最终合并结果:")
    print(f"  容积率: {final_result['floor_area_ratio']}")
    print(f"  建设工程规划许可证: {final_result['planning_license']}")
    print(f"  建筑物长度列表: {final_result['building_lengths']}")