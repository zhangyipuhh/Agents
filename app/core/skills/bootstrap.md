**Tool Mapping for This Environment:**

- `sandbox` → 启动沙箱子智能体，用于在隔离 Docker 容器中执行代码/脚本/命令；实现位于 `app/core/tools/SandboxTools.py`。
- `explore` → 启动文件系统探索子智能体，用于搜索并读取当前 session 上传目录中的文件；实现位于 `app/core/tools/FilesystemReadTools.py`。
- `load_skill` → 加载已注册的 skill 正文及同目录下的参考文件；实现位于 `app/core/skills/tool.py`。
- `todowrite` → 任务规划工具，用于创建/更新/完成待办任务列表。

Use the native tools above. Do not reference third-party platform-specific tool names.
