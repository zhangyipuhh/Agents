# AI Agent Web Interface

一个精美的 AI 聊天助手界面，基于 Vue 3 + Vite 构建。

## 🎯 项目预览

现代化的三栏式布局，包含侧边栏导航、聊天对话区域和底部输入框。参考 MiniMax Agent 设计风格，打造专业级用户体验。

## 📁 项目结构

```
web/Agent/
├── src/
│   ├── components/
│   │   ├── Sidebar.vue        # 左侧边栏 (260px)
│   │   ├── TopBar.vue         # 顶部栏
│   │   ├── SkillTags.vue      # 快捷功能标签
│   │   ├── ChatArea.vue       # 聊天消息区
│   │   ├── MessageBubble.vue  # 消息气泡
│   │   └── InputBox.vue       # 底部输入框
│   ├── styles/
│   │   ├── variables.css      # 120+ CSS 设计变量
│   │   └── main.css          # 全局样式 + 动画库
│   ├── App.vue                # 主布局容器
│   └── main.js                # 入口文件
├── package.json
└── vite.config.js
```

## 🎨 组件功能

| 组件 | 功能亮点 |
|------|---------|
| **Sidebar** | Logo、导航菜单、ZYP实验室、专家、历史记录(可折叠)、用户信息 |
| **TopBar** | 动态标题、新建按钮、分享按钮(带下拉动画) |
| **SkillTags** | 5个技能标签、横向滚动、选中光晕效果 |
| **ChatArea** | 用户/AI消息、思考时间展开、功能列表、空状态、滚动到底部 |
| **InputBox** | 自适应输入框、工具栏、全能模式切换、发送按钮、免责声明 |

## 🚀 快速开始

```bash
# 进入项目目录
cd web/Agent

# 安装依赖
npm install

# 启动开发服务器
npm run dev

# 构建生产版本
npm run build

# 预览生产构建
npm run preview
```

## ✨ 设计特点

### 视觉规范
- 配色方案：纯白背景、灰色边框、层次化文字颜色
- 圆角规范：8-12px 圆角
- 阴影效果：轻微卡片阴影
- 字体系统：系统无衬线字体栈（支持中文）

### 交互动效
- 流畅的过渡动画（0.15s - 0.4s）
- 悬停效果与焦点状态
- 消息入场动画
- 下拉菜单平滑展开

### 技术特性
- Vue 3 Composition API
- CSS 变量设计系统（120+ token）
- CSS Containment 性能优化
- 无障碍支持（ARIA、焦点管理）
- 响应式设计

## 📦 技术栈

- **框架**: Vue 3.4
- **构建工具**: Vite 5.2
- **样式**: CSS3（变量系统 + Flexbox + Grid）

## 📝 许可证

MIT License