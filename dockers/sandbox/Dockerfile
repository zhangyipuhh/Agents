# docker/sandbox/Dockerfile
FROM python:3.12-slim

# 配置国内 PyPI 镜像加速（可选）
RUN pip config set global.index-url https://mirrors.aliyun.com/pypi/simple && \
    pip config set global.timeout 600 && \
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