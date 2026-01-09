from openai import OpenAI
import json

client = OpenAI(
    api_key="sk-d5652bb2e21c43debd1f22fbed6468cf",
    base_url="https://api.deepseek.com"
)

response = client.chat.completions.create(
    model="deepseek-chat",
    messages=[{"role": "user", "content": "查询北京的天气"}],
     tools=[
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "获取天气信息",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location": {"type": "string"},
                        "date": {"type": "string"}
                    },
                    "required": ["location"]
                }
            }
        }
    ],  # 你的工具定义
    stream=True
)

tool_calls_buffer = []
full_content = ""

for chunk in response:
    if chunk.choices[0].delta.tool_calls:
        tool_call_delta = chunk.choices[0].delta.tool_calls[0]
        
        if hasattr(tool_call_delta, 'function') and tool_call_delta.function:
            if tool_call_delta.function.arguments:
                # 这里会一次性获取完整的参数JSON
                args = tool_call_delta.function.arguments
                print(f"完整工具参数: {args}")
    
    # 同时处理普通文本输出
    if chunk.choices[0].delta.content:
        content = chunk.choices[0].delta.content
        full_content += content
        print(content, end="", flush=True)