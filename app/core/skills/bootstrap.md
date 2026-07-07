# Skill System Bootstrap

**Tool Mapping for This Environment:**

- `sandbox` → 启动沙箱子智能体，用于在隔离 Docker 容器中执行代码/脚本/命令。
- `explore` → 启动文件系统探索子智能体，用于搜索并读取当前 session 上传目录中的文件。
- `load_skill` → 加载已注册的 skill 正文及同目录下的参考文件。
- `read_skill_file` → 读取已注册的 skill 文件内容。
- `todowrite` → 任务规划工具，用于创建/更新/完成待办任务列表。

Use the native tools above. Do not reference third-party platform-specific tool names.

## Tool Selection Rules (CRITICAL)

Follow this strict order when deciding which tool to call for a task:

1. **Skill first**
   - Before doing anything else, inspect `<available_skills>` in your system prompt.
   - If any skill name or description matches the current task — even loosely or with low confidence — you MUST call `load_skill(name)` first.
   - After `load_skill` returns the skill body, follow its instructions exactly. Do not fall back to explore/sandbox unless the skill explicitly tells you to.

2. **File exploration fallback**
   - Only use `explore` when:
     - No skill in `<available_skills>` matches the task, AND
     - The task requires complex file search, reading multiple uploaded documents, or extracting content from the session upload directory.

3. **Sandbox fallback**
   - Only use `sandbox` when:
     - No skill matches, AND
     - The task requires executing code/scripts in an isolated environment.

4. **Reading skill companion files**
   - After `load_skill(name)` returns `<skill_files>`, use `read_skill_file(absolute_path)` to read scripts, examples, or reference documents that the skill lists.
   - Never use filesystem tools to read SKILL.md directly — that is what `load_skill` is for.

Remember: the skill system exists to give you detailed, tested workflows. Ignoring it and calling explore/sandbox directly is almost always the wrong choice.
