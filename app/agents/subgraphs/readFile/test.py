#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
Ollama图片识别测试程序

Date: 2026/1/9 12:07
Author: 张镒谱
"""
from app.agents.llmcalls.ollama import create_model
from langchain.messages import ToolMessage, AIMessage, HumanMessage, SystemMessage


class ImageChatbot:
    def __init__(self, model_name: str = "qwen3-vl:30b", temperature: float = 0.0):
        self.model = create_model(
            model_name=model_name,
            api_key=None,
            temperature=temperature,
            base_url="http://192.168.1.107:11434",
        )

    def recognize_images(self, image_paths: list[str], prompt: str = "描述这些图片") -> str:
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


if __name__ == "__main__":
    image_paths = [
        'e:/laboratory/AI/Agents/app/data/upload/418353f9-0902-4641-b4b7-12f516bc3faf/35d43c19-5e2c-4d53-b962-3bb90aba70d3/c2f44085-5ae9-4a18-9b8c-795aa43a279c/page_000.jpg',
        'e:/laboratory/AI/Agents/app/data/upload/418353f9-0902-4641-b4b7-12f516bc3faf/35d43c19-5e2c-4d53-b962-3bb90aba70d3/c2f44085-5ae9-4a18-9b8c-795aa43a279c/page_001.jpg'
    ]
    
    if len(image_paths) == 1:
        result = recognize_image(image_paths[0])
    else:
        result = recognize_multiple_images(image_paths)
    print(f"\n图片: {image_paths}")
    print(f"识别结果: {result}")
