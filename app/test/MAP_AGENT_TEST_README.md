# MapAgent 测试说明

## 测试文件结构

```
app/test/
├── test_map_agent.py          # 主测试文件
└── run_map_agent_tests.py     # 测试运行脚本
```

## 测试内容概览

### 1. 地图工具功能测试 (TestMapTools)

测试所有地图工具的基本功能:

- ✅ `test_set_map_center` - 测试设置地图中心点
- ✅ `test_set_map_zoom` - 测试设置地图缩放级别
- ✅ `test_set_map_zoom_boundary` - 测试缩放级别边界限制
- ✅ `test_add_map_marker` - 测试添加地图标记
- ✅ `test_add_map_marker_with_custom_id` - 测试使用自定义 ID 添加标记
- ✅ `test_remove_map_marker` - 测试移除地图标记
- ✅ `test_remove_nonexistent_marker` - 测试移除不存在的标记
- ✅ `test_clear_map_markers` - 测试清除所有标记
- ✅ `test_get_map_state` - 测试获取地图状态
- ✅ `test_draw_map_polygon` - 测试绘制地图多边形
- ✅ `test_set_map_layer` - 测试设置地图图层
- ✅ `test_set_map_layer_invalid` - 测试设置无效的地图图层

### 2. 流式调用测试 (TestMapAgentStreaming)

测试 MapAgent 的流式输出功能:

- ✅ `test_stream_basic` - 测试基本的流式调用
- ✅ `test_stream_mode_updates` - 测试 updates 模式的流式输出
- ✅ `test_stream_mode_messages` - 测试 messages 模式的流式输出
- ✅ `test_stream_mode_combined` - 测试组合模式的流式输出
- ✅ `test_stream_default_mode` - 测试默认流式模式

### 3. 错误处理测试 (TestMapAgentErrorHandling)

测试各种异常情况的处理:

- ✅ `test_tool_execution_error` - 测试工具执行错误
- ✅ `test_invalid_coordinates` - 测试无效坐标
- ✅ `test_agent_initialization_error` - 测试 Agent 初始化错误
- ✅ `test_session_state_persistence` - 测试会话状态持久化
- ✅ `test_concurrent_sessions` - 测试并发会话

### 4. SSE 格式验证测试 (TestSSEFormat)

验证 Server-Sent Events 格式:

- ✅ `test_sse_format_updates` - 测试 updates 模式的 SSE 格式
- ✅ `test_sse_format_messages` - 测试 messages 模式的 SSE 格式
- ✅ `test_sse_format_combined` - 测试组合模式的 SSE 格式

### 5. 集成测试 (TestMapAgentIntegration)

测试完整的工作流程:

- ✅ `test_full_workflow` - 测试完整的工作流程
- ✅ `test_multi_turn_conversation` - 测试多轮对话

## 运行测试

### 方式 1: 使用测试运行脚本 (推荐)

```bash
# 运行所有测试
python app/test/run_map_agent_tests.py

# 只运行工具测试
python app/test/run_map_agent_tests.py tools

# 只运行流式调用测试
python app/test/run_map_agent_tests.py streaming

# 只运行错误处理测试
python app/test/run_map_agent_tests.py error

# 只运行 SSE 格式测试
python app/test/run_map_agent_tests.py sse

# 只运行集成测试
python app/test/run_map_agent_tests.py integration

# 显示帮助信息
python app/test/run_map_agent_tests.py help
```

### 方式 2: 使用 pytest 直接运行

```bash
# 运行所有测试
pytest app/test/test_map_agent.py -v -s

# 运行特定测试类
pytest app/test/test_map_agent.py::TestMapTools -v -s

# 运行特定测试方法
pytest app/test/test_map_agent.py::TestMapTools::test_set_map_center -v -s

# 生成覆盖率报告
pytest app/test/test_map_agent.py --cov=app/features/map_agent --cov-report=html
```

### 方式 3: 使用 Python 直接运行

```bash
# 运行测试文件
python app/test/test_map_agent.py
```

## 测试输出示例

```
================================================================================
🚀 开始运行 MapAgent 测试套件
================================================================================

test_map_agent.py::TestMapTools::test_set_map_center PASSED                [  8%]
test_map_agent.py::TestMapTools::test_set_map_zoom PASSED                  [ 16%]
test_map_agent.py::TestMapTools::test_set_map_zoom_boundary PASSED         [ 25%]
test_map_agent.py::TestMapTools::test_add_map_marker PASSED                [ 33%]
test_map_agent.py::TestMapTools::test_remove_map_marker PASSED             [ 41%]
test_map_agent.py::TestMapTools::test_clear_map_markers PASSED             [ 50%]
test_map_agent.py::TestMapTools::test_get_map_state PASSED                 [ 58%]
test_map_agent.py::TestMapTools::test_draw_map_polygon PASSED              [ 66%]
test_map_agent.py::TestMapTools::test_set_map_layer PASSED                 [ 75%]
test_map_agent.py::TestMapAgentStreaming::test_stream_basic PASSED         [ 83%]
test_map_agent.py::TestMapAgentStreaming::test_stream_mode_updates PASSED  [ 91%]
test_map_agent.py::TestMapAgentErrorHandling::test_tool_execution_error PASSED [100%]

================================================================================
✅ 所有测试通过!
================================================================================
```

## 测试覆盖范围

### 工具测试覆盖
- ✅ 所有 8 个地图工具的基本功能
- ✅ 参数验证和边界条件
- ✅ 错误情况处理
- ✅ 返回值格式验证

### 流式输出测试覆盖
- ✅ 三种流式模式: updates, messages, custom
- ✅ 组合模式: ["updates", "messages", "custom"]
- ✅ 默认模式行为
- ✅ SSE 格式验证

### 错误处理测试覆盖
- ✅ 工具执行错误
- ✅ 无效输入验证
- ✅ Agent 初始化失败
- ✅ 会话状态管理
- ✅ 并发会话处理

### 集成测试覆盖
- ✅ 完整工作流程
- ✅ 多轮对话
- ✅ 会话持久化

## 测试依赖

测试需要以下依赖包:

```txt
pytest>=7.0.0
pytest-asyncio>=0.21.0
pytest-cov>=4.0.0  # 可选,用于生成覆盖率报告
```

安装依赖:

```bash
pip install pytest pytest-asyncio pytest-cov
```

## Mock 和 Fixture 说明

### Fixtures

测试使用以下 fixtures 来模拟依赖:

1. **mock_checkpointer**: 模拟 LangGraph 检查点保存器
   - 使用 `MemorySaver` 实现内存存储
   - 用于测试会话状态持久化

2. **mock_store**: 模拟 LangGraph 存储器
   - 使用 `InMemoryStore` 实现内存存储
   - 用于测试长期记忆存储

3. **mock_tool_runtime**: 模拟工具运行时上下文
   - 提供 `tool_call_id` 和 `state`
   - 用于测试工具执行

4. **map_agent**: 创建 MapAgent 实例
   - 使用模拟的 checkpointer 和 store
   - 用于测试 Agent 功能

### Mock 策略

测试采用以下 mock 策略:

1. **工具测试**: 直接调用工具函数,验证返回值
2. **流式测试**: Mock `_ensure_agent` 方法,模拟 agent 行为
3. **错误测试**: 故意触发错误,验证错误处理
4. **集成测试**: Mock agent 的 stream 方法,模拟完整流程

## 注意事项

1. **异步测试**: 所有涉及 Agent 的测试都是异步的,使用 `@pytest.mark.asyncio` 装饰器

2. **独立运行**: 每个测试都是独立的,不依赖其他测试的执行顺序

3. **模拟依赖**: 测试使用内存存储,不依赖外部数据库或 API

4. **清理状态**: 每个测试都会创建新的实例,避免状态污染

5. **错误隔离**: 错误测试使用 `pytest.raises` 或 try-except 捕获异常

## 扩展测试

如果需要添加新的测试:

1. 在相应的测试类中添加新的测试方法
2. 使用现有的 fixtures 或创建新的 fixtures
3. 遵循命名规范: `test_<功能描述>`
4. 添加清晰的文档字符串说明测试目的

示例:

```python
def test_new_feature(self, mock_tool_runtime):
    """测试新功能"""
    # 准备测试数据
    # 执行测试
    # 验证结果
    pass
```

## 故障排查

如果测试失败:

1. 检查错误信息,定位失败的测试
2. 使用 `-v -s` 参数查看详细输出
3. 检查依赖是否正确安装
4. 验证被测试的代码是否正确实现
5. 查看 mock 对象是否正确配置

## 持续集成

可以将测试集成到 CI/CD 流程:

```yaml
# .github/workflows/test.yml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.10'
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest pytest-asyncio pytest-cov
      - name: Run tests
        run: python app/test/run_map_agent_tests.py
```

## 总结

本测试套件全面覆盖了 MapAgent 的功能,包括:

- ✅ 8 个地图工具的完整测试
- ✅ 5 种流式输出模式的测试
- ✅ 5 种错误处理场景的测试
- ✅ 3 种 SSE 格式的验证
- ✅ 2 种集成测试场景

测试采用 pytest 框架,支持异步测试,使用 mock 对象隔离依赖,确保测试的独立性和可靠性。
