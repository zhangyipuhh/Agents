# 简单的测试脚本
print("DEBUG: 开始执行调试脚本")

# 测试模型是否能正常使用
from langchain_deepseek import ChatDeepSeek

print("DEBUG: 正在初始化模型")
model = ChatDeepSeek(model_name="deepseek-chat", api_key="sk-d5652bb2e21c43debd1f22fbed6468cf", temperature=0)

print("DEBUG: 模型初始化成功")

# 测试简单的模型调用
print("DEBUG: 正在测试模型调用")
response = model.invoke("你好")
print(f"DEBUG: 模型响应: {response.content}")

print("DEBUG: 调试脚本执行完成")