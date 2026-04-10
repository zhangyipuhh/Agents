# 工具输出格式规范 v1.0

## 概述

本文档定义了所有工具的统一输出格式，确保前端可以一致地解析和展示工具执行结果。

## 核心原则

✅ **双重输出策略** - ToolMessage 告诉大模型简短摘要，get_stream_writer 发送详细数据  
✅ **不占用主模型 token** - 详细数据不添加到 messages 状态  
✅ **流式输出** - 使用 `get_stream_writer()` 实时发送数据  
✅ **统一格式** - 所有工具使用相同的 header/body/footer 结构  
✅ **易于解析** - 前端可以根据 status 和结构进行统一处理

---

## 双重输出策略

### 核心思想

```
┌─────────────────────────────────────────────────────────┐
│  工具执行                                                │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  1. ToolMessage (简短摘要)                               │
│     └─> 添加到 messages 状态                             │
│     └─> 大模型可以看到                                   │
│     └─> 告诉大模型工具执行了什么                         │
│                                                          │
│  2. get_stream_writer (详细数据)                         │
│     └─> 流式发送到前端                                   │
│     └─> 不添加到 messages 状态                           │
│     └─> 大模型看不到详细内容                             │
│     └─> 前端实时显示                                     │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

### 示例对比

#### ❌ 传统方式（占用大量 token）

```python
# 工具返回大量日志数据
return Command(
    update={
        "messages": [
            ToolMessage(
                content="日志内容：\n" + "\n".join(log_lines),  # 可能几千行
                tool_call_id=tool_call_id
            )
        ]
    }
)
# 结果：messages 状态包含几千行日志，占用大量 token
```

#### ✅ 双重输出策略（不占用 token）

```python
# 1. 流式发送详细数据
writer({
    "header": {..., "status": "progress"},
    "body": {
        "data": log_lines,  # 详细数据
        "metadata": {...}
    },
    "footer": None
})

# 2. 返回简短摘要
return Command(
    update={
        "messages": [
            ToolMessage(
                content="成功获取 100 行日志",  # 简短摘要
                tool_call_id=tool_call_id
            )
        ],
        "tool_results": {...}
    }
)
# 结果：messages 状态只包含简短摘要，详细数据已流式发送
```

---

## 统一输出格式

### 完整结构

```python
{
    "header": {
        "tool_name": str,           # 工具名称
        "tool_call_id": str,        # 工具调用 ID
        "timestamp": str,           # ISO 8601 时间戳
        "status": str,              # start | progress | complete | error
        "version": str              # 格式版本，当前为 "1.0"
    },
    "body": {
        "data": Any,                # 实际数据内容
        "metadata": dict            # 元数据（根据工具类型不同）
    },
    "footer": {
        "success": bool,            # 是否成功
        "message": str,             # 完成消息
        "stats": {                  # 统计信息
            "total": int,           # 总数
            "processed": int,       # 已处理数
            "failed": int           # 失败数
        }
    }
}
```

### 状态说明

| status | 说明 | 是否包含 body | 是否包含 footer |
|--------|------|--------------|----------------|
| `start` | 工具开始执行 | ✅ 包含初始化信息 | ❌ 无 |
| `progress` | 执行进度更新 | ✅ 包含部分数据 | ❌ 无 |
| `complete` | 执行完成 | ✅ 包含最终元数据 | ✅ 包含统计信息 |
| `error` | 执行失败 | ✅ 包含错误信息 | ✅ 包含失败统计 |

---

## 使用示例

### 1. 工具实现（Python）

```python
from langchain.tools import tool, ToolRuntime
from langgraph.types import Command
from langgraph.config import get_stream_writer
from datetime import datetime

@tool(description="工具描述")
def my_tool(param: str, runtime: ToolRuntime = None) -> Command:
    """工具函数"""
    writer = get_stream_writer()
    
    if runtime is None:
        writer({
            "header": {
                "tool_name": "my_tool",
                "tool_call_id": "unknown",
                "timestamp": datetime.now().isoformat(),
                "status": "error",
                "version": "1.0"
            },
            "body": {
                "data": None,
                "metadata": {"error": "运行时上下文不能为空"}
            },
            "footer": {
                "success": False,
                "message": "运行时上下文不能为空",
                "stats": {"total": 0, "processed": 0, "failed": 1}
            }
        })
        
        return Command(update={"tool_results": {"unknown": {
            "tool": "my_tool",
            "status": "error",
            "error": "运行时上下文不能为空"
        }}})
    
    tool_call_id = runtime.tool_call_id
    
    # 1. 发送开始标记
    writer({
        "header": {
            "tool_name": "my_tool",
            "tool_call_id": tool_call_id,
            "timestamp": datetime.now().isoformat(),
            "status": "start",
            "version": "1.0"
        },
        "body": {
            "data": None,
            "metadata": {"param": param}
        },
        "footer": None
    })
    
    try:
        # 2. 执行任务
        results = []
        total = 100
        
        for i in range(total):
            # 处理数据
            result = process_item(i)
            results.append(result)
            
            # 3. 发送进度更新（每 10 个发送一次）
            if (i + 1) % 10 == 0:
                writer({
                    "header": {
                        "tool_name": "my_tool",
                        "tool_call_id": tool_call_id,
                        "timestamp": datetime.now().isoformat(),
                        "status": "progress",
                        "version": "1.0"
                    },
                    "body": {
                        "data": results[-10:],  # 最近 10 个结果
                        "metadata": {
                            "total": total,
                            "current": i + 1,
                            "percentage": int(((i + 1) / total) * 100)
                        }
                    },
                    "footer": None
                })
        
        # 4. 发送完成标记
        writer({
            "header": {
                "tool_name": "my_tool",
                "tool_call_id": tool_call_id,
                "timestamp": datetime.now().isoformat(),
                "status": "complete",
                "version": "1.0"
            },
            "body": {
                "data": None,
                "metadata": {"param": param, "total": total}
            },
            "footer": {
                "success": True,
                "message": f"成功处理 {total} 个项目",
                "stats": {"total": total, "processed": total, "failed": 0}
            }
        })
        
        # 5. 返回 Command（不包含 messages）
        return Command(update={"tool_results": {tool_call_id: {
            "tool": "my_tool",
            "status": "success",
            "total": total,
            "summary": f"成功处理 {total} 个项目"
        }}})
    
    except Exception as e:
        # 6. 发送错误标记
        writer({
            "header": {
                "tool_name": "my_tool",
                "tool_call_id": tool_call_id,
                "timestamp": datetime.now().isoformat(),
                "status": "error",
                "version": "1.0"
            },
            "body": {
                "data": None,
                "metadata": {"error": str(e)}
            },
            "footer": {
                "success": False,
                "message": f"执行失败: {str(e)}",
                "stats": {"total": 0, "processed": 0, "failed": 1}
            }
        })
        
        return Command(update={"tool_results": {tool_call_id: {
            "tool": "my_tool",
            "status": "error",
            "error": str(e)
        }}})
```

### 2. 前端解析（TypeScript/JavaScript）

```typescript
// 类型定义
interface ToolOutputHeader {
  tool_name: string;
  tool_call_id: string;
  timestamp: string;
  status: 'start' | 'progress' | 'complete' | 'error';
  version: string;
}

interface ToolOutputBody {
  data: any;
  metadata: Record<string, any>;
}

interface ToolOutputFooter {
  success: boolean;
  message: string;
  stats: {
    total: number;
    processed: number;
    failed: number;
  };
}

interface ToolOutput {
  header: ToolOutputHeader;
  body: ToolOutputBody | null;
  footer: ToolOutputFooter | null;
}

// 解析函数
class ToolOutputParser {
  private currentTool: string | null = null;
  private accumulatedData: any[] = [];
  
  parse(chunk: ToolOutput): void {
    const { header, body, footer } = chunk;
    
    switch (header.status) {
      case 'start':
        this.handleStart(header, body);
        break;
      
      case 'progress':
        this.handleProgress(header, body);
        break;
      
      case 'complete':
        this.handleComplete(header, body, footer);
        break;
      
      case 'error':
        this.handleError(header, body, footer);
        break;
    }
  }
  
  private handleStart(header: ToolOutputHeader, body: ToolOutputBody | null): void {
    this.currentTool = header.tool_name;
    this.accumulatedData = [];
    
    console.log(`🔧 开始执行工具: ${header.tool_name}`);
    console.log(`   调用 ID: ${header.tool_call_id}`);
    console.log(`   时间: ${header.timestamp}`);
    
    if (body?.metadata) {
      console.log(`   参数:`, body.metadata);
    }
  }
  
  private handleProgress(header: ToolOutputHeader, body: ToolOutputBody | null): void {
    if (!body) return;
    
    const { data, metadata } = body;
    
    // 累积数据
    if (Array.isArray(data)) {
      this.accumulatedData.push(...data);
    }
    
    // 显示进度
    if (metadata.percentage !== undefined) {
      const progressBar = this.renderProgressBar(metadata.percentage);
      console.log(`⏳ 进度: ${progressBar} ${metadata.percentage}%`);
    }
    
    if (metadata.current !== undefined && metadata.total !== undefined) {
      console.log(`   处理: ${metadata.current}/${metadata.total}`);
    }
  }
  
  private handleComplete(
    header: ToolOutputHeader, 
    body: ToolOutputBody | null, 
    footer: ToolOutputFooter | null
  ): void {
    console.log(`\n✅ 工具执行完成: ${header.tool_name}`);
    
    if (footer) {
      console.log(`   消息: ${footer.message}`);
      console.log(`   统计:`);
      console.log(`     - 总数: ${footer.stats.total}`);
      console.log(`     - 已处理: ${footer.stats.processed}`);
      console.log(`     - 失败: ${footer.stats.failed}`);
    }
    
    // 显示累积的数据
    if (this.accumulatedData.length > 0) {
      console.log(`   数据总量: ${this.accumulatedData.length} 条`);
    }
    
    this.currentTool = null;
    this.accumulatedData = [];
  }
  
  private handleError(
    header: ToolOutputHeader, 
    body: ToolOutputBody | null, 
    footer: ToolOutputFooter | null
  ): void {
    console.error(`\n❌ 工具执行失败: ${header.tool_name}`);
    
    if (body?.metadata?.error) {
      console.error(`   错误: ${body.metadata.error}`);
    }
    
    if (footer) {
      console.error(`   消息: ${footer.message}`);
    }
    
    this.currentTool = null;
    this.accumulatedData = [];
  }
  
  private renderProgressBar(percentage: number): string {
    const filled = Math.floor(percentage / 5);
    const empty = 20 - filled;
    return '█'.repeat(filled) + '░'.repeat(empty);
  }
}

// 使用示例
const parser = new ToolOutputParser();

// 模拟接收流式数据
async function handleStreamOutput(graph: any, inputs: any) {
  for await (const chunk of graph.astream(inputs, { 
    stream_mode: 'custom', 
    version: 'v2' 
  })) {
    if (chunk.type === 'custom') {
      parser.parse(chunk.data);
    }
  }
}
```

### 3. React 组件示例

```tsx
import React, { useState, useEffect } from 'react';

interface ToolExecutionProps {
  toolName: string;
  toolCallId: string;
}

const ToolExecution: React.FC<ToolExecutionProps> = ({ toolName, toolCallId }) => {
  const [status, setStatus] = useState<'idle' | 'running' | 'complete' | 'error'>('idle');
  const [progress, setProgress] = useState(0);
  const [message, setMessage] = useState('');
  const [data, setData] = useState<any[]>([]);
  
  useEffect(() => {
    // 监听流式输出
    const eventSource = new EventSource(`/api/tools/stream/${toolCallId}`);
    
    eventSource.onmessage = (event) => {
      const output: ToolOutput = JSON.parse(event.data);
      
      switch (output.header.status) {
        case 'start':
          setStatus('running');
          setMessage('开始执行...');
          break;
        
        case 'progress':
          if (output.body?.metadata?.percentage) {
            setProgress(output.body.metadata.percentage);
          }
          if (Array.isArray(output.body?.data)) {
            setData(prev => [...prev, ...output.body.data]);
          }
          break;
        
        case 'complete':
          setStatus('complete');
          setProgress(100);
          setMessage(output.footer?.message || '执行完成');
          break;
        
        case 'error':
          setStatus('error');
          setMessage(output.footer?.message || '执行失败');
          break;
      }
    };
    
    return () => eventSource.close();
  }, [toolCallId]);
  
  return (
    <div className="tool-execution">
      <div className="tool-header">
        <span className="tool-name">🔧 {toolName}</span>
        <span className={`status status-${status}`}>
          {status === 'running' && '⏳ 执行中'}
          {status === 'complete' && '✅ 完成'}
          {status === 'error' && '❌ 失败'}
        </span>
      </div>
      
      {status === 'running' && (
        <div className="progress-bar">
          <div className="progress-fill" style={{ width: `${progress}%` }} />
          <span className="progress-text">{progress}%</span>
        </div>
      )}
      
      <div className="message">{message}</div>
      
      {data.length > 0 && (
        <div className="data-preview">
          <div>已接收 {data.length} 条数据</div>
          <pre>{JSON.stringify(data.slice(-5), null, 2)}</pre>
        </div>
      )}
    </div>
  );
};
```

---

## 最佳实践

### 1. 数据分批发送

```python
# ✅ 推荐：分批发送大量数据
batch_size = 10
for i in range(0, total, batch_size):
    batch = data[i:i + batch_size]
    writer({
        "header": {..., "status": "progress"},
        "body": {"data": batch, "metadata": {...}},
        "footer": None
    })

# ❌ 不推荐：一次性发送所有数据
writer({
    "header": {..., "status": "complete"},
    "body": {"data": all_data},  # 可能非常大
    "footer": {...}
})
```

### 2. 错误处理

```python
# ✅ 推荐：详细的错误信息
writer({
    "header": {..., "status": "error"},
    "body": {
        "data": None,
        "metadata": {
            "error": str(e),
            "error_type": type(e).__name__,
            "stack_trace": traceback.format_exc()
        }
    },
    "footer": {...}
})

# ❌ 不推荐：简单的错误消息
writer({"error": str(e)})
```

### 3. 元数据一致性

```python
# ✅ 推荐：一致的元数据字段
"metadata": {
    "total": 100,
    "current": 50,
    "percentage": 50,
    "batch_index": 5,
    "batch_size": 10
}

# ❌ 不推荐：不一致的字段名
"metadata": {
    "total_count": 100,
    "current_item": 50,
    "percent": 50
}
```

---

## 模板工具清单

以下工具已实现统一输出格式：

- ✅ `get_system_logs` - 获取系统日志
- ⏳ `execute_batch_commands` - 批量执行命令（待改造）
- ⏳ `execute_command` - 执行单个命令（待改造）

---

## 版本历史

- **v1.0** (2026-04-08) - 初始版本，定义统一输出格式
