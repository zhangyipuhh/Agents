# Router 模块文档

本文档描述了 `app/core/router` 模块的功能和调用方式，包含文件上传和文件下载两个子模块。

## 目录结构

```
app/core/router/
├── __init__.py              # 路由模块入口，导出上传和下载路由
├── file_upload_router.py    # 文件上传相关接口
└── file_download_router.py  # 文件下载相关接口
```

## 模块概述

Router 模块提供了一套完整的文件上传和下载 API，支持以下核心功能：

- **文件上传**：支持单文件/多文件上传、大文件分片上传
- **文件下载**：支持单文件下载、批量下载、断点续传
- **会话隔离**：基于 session_id 的文件存储隔离
- **文档解析**：支持本地和远程两种文档解析模式

---

## 文件上传模块 (file_upload_router)

**基础路径**: `/api/core`

### 接口列表

| 接口 | 方法 | 路径 | 功能描述 |
|------|------|------|----------|
| 单文件/多文件上传 | POST | `/uploadfile` | 支持多文件上传，自动解析文档内容 |
| 分片上传 | POST | `/upload-chunk` | 大文件分片上传接口 |
| 合并分片 | POST | `/merge-chunks` | 合并已上传的分片文件 |

### 1. 单文件/多文件上传

上传一个或多个文件，系统会自动解析文档内容并保存为文本格式。

**请求参数**:

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| files | List[File] | 是 | 要上传的文件列表 |

**响应参数**:

| 参数名 | 类型 | 说明 |
|--------|------|------|
| files | List[UploadedFileInfo] | 上传成功的文件信息列表 |
| count | int | 上传成功的文件数量 |
| parser_mode | str | 解析模式（"remote" 或 "local"） |

**UploadedFileInfo 结构**:

| 参数名 | 类型 | 说明 |
|--------|------|------|
| filename | str | 原始文件名 |
| stored_path | str | 存储路径 |
| file_type | str | 文件类型 |

#### 调用示例

**curl:**
```bash
curl -X POST "http://localhost:8000/api/core/uploadfile" \
  -H "Content-Type: multipart/form-data" \
  -F "files=@document.pdf" \
  -F "files=@image.jpg"
```

**Python requests:**
```python
import requests

url = "http://localhost:8000/api/core/uploadfile"
files = [
    ("files", ("document.pdf", open("document.pdf", "rb"), "application/pdf")),
    ("files", ("image.jpg", open("image.jpg", "rb"), "image/jpeg"))
]
response = requests.post(url, files=files)
print(response.json())
```

**JavaScript fetch:**
```javascript
const formData = new FormData();
formData.append("files", fileInput.files[0]);

fetch("http://localhost:8000/api/core/uploadfile", {
  method: "POST",
  body: formData
})
.then(response => response.json())
.then(data => console.log(data));
```

### 2. 分片上传

用于大文件分片上传，将文件切分成多个小块逐个上传。

**请求参数**:

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| chunk | File | 是 | 当前分片文件 |
| file_id | str | 是 | 文件唯一标识符 |
| chunk_index | int | 是 | 当前分片索引（从0开始） |
| total_chunks | int | 是 | 总分片数量 |
| filename | str | 是 | 原始文件名 |

**响应参数**:

| 参数名 | 类型 | 说明 |
|--------|------|------|
| file_id | str | 文件唯一标识符 |
| chunk_index | int | 已接收的分片索引 |
| received | bool | 是否接收成功 |

#### 调用示例

**curl:**
```bash
curl -X POST "http://localhost:8000/api/core/upload-chunk" \
  -F "chunk=@chunk_0.bin" \
  -F "file_id=unique_file_id_123" \
  -F "chunk_index=0" \
  -F "total_chunks=10" \
  -F "filename=large_file.zip"
```

**Python requests:**
```python
import requests

url = "http://localhost:8000/api/core/upload-chunk"
with open("chunk_0.bin", "rb") as f:
    files = {"chunk": f}
    data = {
        "file_id": "unique_file_id_123",
        "chunk_index": 0,
        "total_chunks": 10,
        "filename": "large_file.zip"
    }
    response = requests.post(url, files=files, data=data)
    print(response.json())
```

### 3. 合并分片

将所有已上传的分片合并成完整文件。

**请求参数**:

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| file_id | str | 是 | 文件唯一标识符 |
| filename | str | 是 | 原始文件名 |
| total_chunks | int | 是 | 总分片数量 |

**响应参数**: 同单文件上传响应

#### 调用示例

**curl:**
```bash
curl -X POST "http://localhost:8000/api/core/merge-chunks" \
  -H "Content-Type: application/json" \
  -d '{
    "file_id": "unique_file_id_123",
    "filename": "large_file.zip",
    "total_chunks": 10
  }'
```

**Python requests:**
```python
import requests

url = "http://localhost:8000/api/core/merge-chunks"
payload = {
    "file_id": "unique_file_id_123",
    "filename": "large_file.zip",
    "total_chunks": 10
}
response = requests.post(url, json=payload)
print(response.json())
```

---

## 文件下载模块 (file_download_router)

**基础路径**: `/api/core/download`

### 接口列表

| 接口 | 方法 | 路径 | 功能描述 |
|------|------|------|----------|
| 文件下载 | GET | `/file` | 支持断点续传、自定义下载文件名 |
| 按名称下载 | GET | `/by-name` | 根据文件名模糊匹配下载 |
| 批量下载 | POST | `/batch` | 多文件打包成 ZIP 下载 |
| 文件列表 | GET | `/list` | 列出可下载的文件列表 |

### 1. 文件下载

下载指定路径的文件，支持断点续传和自定义下载文件名。

**请求参数**:

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| path | str | 是 | 相对于 session 下载目录的文件路径 |
| filename | str | 否 | 自定义下载文件名 |

**请求头**:

| 参数名 | 说明 |
|--------|------|
| Range | 断点续传范围，如 `bytes=1024-` |

#### 调用示例

**curl:**
```bash
# 普通下载
curl -O -J "http://localhost:8000/api/core/download/file?path=document.txt"

# 自定义文件名
curl -O -J "http://localhost:8000/api/core/download/file?path=document.txt&filename=mydoc.txt"

# 断点续传（从第 1024 字节开始）
curl -H "Range: bytes=1024-" -O -J "http://localhost:8000/api/core/download/file?path=document.txt"
```

**Python requests:**
```python
import requests

# 普通下载
url = "http://localhost:8000/api/core/download/file?path=document.txt"
response = requests.get(url, stream=True)
with open("document.txt", "wb") as f:
    for chunk in response.iter_content(chunk_size=8192):
        f.write(chunk)

# 断点续传
headers = {"Range": "bytes=1024-"}
response = requests.get(url, headers=headers, stream=True)
with open("document.txt", "ab") as f:  # 注意使用 ab 模式追加
    for chunk in response.iter_content(chunk_size=8192):
        f.write(chunk)
```

### 2. 按名称下载

根据文件名模糊匹配或精确匹配下载文件。如果匹配到多个文件，返回候选列表。

**请求参数**:

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| name | str | 是 | 文件名（支持模糊匹配） |
| exact | bool | 否 | 是否精确匹配，默认 false |

**响应状态码 300**（多选情况）:

| 参数名 | 类型 | 说明 |
|--------|------|------|
| message | str | 提示信息 |
| files | List[MultipleChoiceFileInfo] | 匹配的文件列表 |

#### 调用示例

**curl:**
```bash
# 模糊匹配
curl -O -J "http://localhost:8000/api/core/download/by-name?name=report"

# 精确匹配
curl -O -J "http://localhost:8000/api/core/download/by-name?name=report.pdf&exact=true"
```

**Python requests:**
```python
import requests

url = "http://localhost:8000/api/core/download/by-name"
params = {"name": "report", "exact": False}
response = requests.get(url, params=params, stream=True)

if response.status_code == 300:
    # 多个匹配结果
    data = response.json()
    print(data["message"])
    for file in data["files"]:
        print(f"  - {file['name']} ({file['size']} bytes)")
elif response.status_code == 200:
    # 单个匹配结果，保存文件
    with open("report.pdf", "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
```

### 3. 批量下载

将多个文件打包成 ZIP 格式下载。

**请求参数**:

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| paths | List[str] | 是 | 要下载的文件路径列表 |
| zip_filename | str | 否 | 自定义 ZIP 文件名 |

#### 调用示例

**curl:**
```bash
curl -X POST "http://localhost:8000/api/core/download/batch" \
  -H "Content-Type: application/json" \
  -d '{
    "paths": ["file1.txt", "file2.txt"],
    "zip_filename": "my_files.zip"
  }' \
  -O -J
```

**Python requests:**
```python
import requests

url = "http://localhost:8000/api/core/download/batch"
payload = {
    "paths": ["file1.txt", "file2.txt", "documents/report.pdf"],
    "zip_filename": "my_files.zip"
}
response = requests.post(url, json=payload, stream=True)

with open("my_files.zip", "wb") as f:
    for chunk in response.iter_content(chunk_size=8192):
        f.write(chunk)
```

### 4. 文件列表

列出当前 session 可下载的文件列表。

**请求参数**:

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| subdir | str | 否 | 子目录路径 |
| recursive | bool | 否 | 是否递归列出子目录，默认 false |

**响应参数**:

| 参数名 | 类型 | 说明 |
|--------|------|------|
| files | List[DownloadableFileInfo] | 文件信息列表 |
| count | int | 文件数量 |

**DownloadableFileInfo 结构**:

| 参数名 | 类型 | 说明 |
|--------|------|------|
| name | str | 文件名 |
| path | str | 相对路径 |
| size | int | 文件大小（字节） |
| modified_time | float | 修改时间戳 |
| is_dir | bool | 是否为目录 |

#### 调用示例

**curl:**
```bash
# 列出当前目录文件
curl "http://localhost:8000/api/core/download/list"

# 列出子目录文件
curl "http://localhost:8000/api/core/download/list?subdir=documents"

# 递归列出所有文件
curl "http://localhost:8000/api/core/download/list?recursive=true"
```

**Python requests:**
```python
import requests

url = "http://localhost:8000/api/core/download/list"
params = {"subdir": "documents", "recursive": True}
response = requests.get(url, params=params)
data = response.json()

print(f"共 {data['count']} 个文件:")
for file in data["files"]:
    print(f"  - {file['name']} ({file['size']} bytes)")
```

---

## 配置说明

### 文件解析配置 (FILE_PARSER_CONFIG)

文件上传模块支持两种解析模式，通过配置文件控制：

```python
FILE_PARSER_CONFIG = {
    "enabled": False,           # 是否启用远程解析服务
    "server_url": "...",        # 远程解析服务地址
    "api_url": "...",           # 解析 API 地址
    "output_format": "md",      # 输出格式（如 md、txt）
    "max_retries": 3,           # 最大重试次数
    "poll_interval": 2,         # 轮询间隔（秒）
    "timeout": 300              # 超时时间（秒）
}
```

- **本地模式** (`enabled: false`): 使用 `DocumentLoader` 本地解析文档
- **远程模式** (`enabled: true`): 调用远程解析服务处理文档

---

## 目录结构说明

### 上传文件存储路径

```
data/upload/
└── {session_id}/           # 按 session 隔离
    ├── file1.txt
    ├── file2.md
    └── ...
```

### 下载文件存储路径

```
data/download/
└── {session_id}/           # 按 session 隔离
    ├── document.txt
    ├── report.pdf
    └── ...
```

### 分片上传临时存储路径

```
data/upload_chunks/
└── {file_id}/              # 按文件 ID 隔离
    ├── chunk_0
    ├── chunk_1
    └── ...
```

---

## 核心特性说明

### 1. 会话隔离

所有文件操作都基于 `session_id` 进行隔离，确保不同用户/会话的文件互不干扰。`session_id` 从请求上下文中获取，默认为 `"default"`。

### 2. 安全路径校验

下载模块使用 `_safe_path` 函数校验路径，防止目录遍历攻击，确保只能访问当前 session 目录下的文件。

### 3. 断点续传支持

下载接口支持 HTTP Range 请求头，可以实现断点续传功能：
- `Range: bytes=1024-` - 从第 1024 字节下载到文件末尾
- `Range: bytes=0-1023` - 下载前 1024 字节
- `Range: bytes=-1024` - 下载最后 1024 字节

### 4. 大文件分片上传

对于大文件，建议：
1. 将文件切分成多个小块（如每块 1MB）
2. 使用 `/upload-chunk` 接口逐个上传分片
3. 所有分片上传完成后，调用 `/merge-chunks` 合并

---

## 错误码说明

| 状态码 | 说明 |
|--------|------|
| 200 | 请求成功 |
| 206 | 部分内容（断点续传） |
| 300 | 多个匹配结果（按名称下载时） |
| 400 | 请求参数错误 |
| 404 | 文件不存在 |
| 416 | Range 请求范围无效 |
| 500 | 服务器内部错误 |
| 503 | 远程解析服务不可用 |
