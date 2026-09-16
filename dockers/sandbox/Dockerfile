# docker/sandbox/Dockerfile
FROM python:3.12-slim

# 2026-09-16 时区改造:与 app/Dockerfile 对齐,装 tzdata + 设 TZ=Asia/Shanghai
# 让 SSH 进沙箱子容器时 `date` 显示北京,避免运维误判
ENV TZ=Asia/Shanghai

# 配置国内 PyPI 镜像加速（可选）
RUN pip config set global.index-url https://mirrors.aliyun.com/pypi/simple && \
    pip config set global.timeout 600 && \
    apt-get update && apt-get install -y --no-install-recommends tzdata && \
    ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && \
    echo $TZ > /etc/timezone && \
    dpkg-reconfigure -f noninteractive tzdata && \
    rm -rf /var/lib/apt/lists/* && \
    pip install --no-cache-dir --upgrade pip setuptools wheel

# ━━━ 预装沙箱子智能体常用组件（按需增删） ━━━
# 办公文档三件套（版本号建议与 app/requirements.txt 保持一致）
RUN pip install --no-cache-dir \
    python-docx==1.2.0 \
    python-pptx==1.0.2 \
    xlsxwriter==3.2.9

# 数据分析套件（按需启用）
# RUN pip install --no-cache-dir pandas numpy matplotlib openpyxl

# 容器启动后保持运行，等待 docker exec
CMD ["tail", "-f", "/dev/null"]
