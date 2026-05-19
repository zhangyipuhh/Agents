# ==================================================================
# 警告：此文件由 generate_docker 自动生成
# 请勿直接修改此文件。请更新 docker-template/Dockerfile
# 然后重新生成此文件。
# ==================================================================

# 第一阶段：构建阶段
FROM python:3.11-slim as builder

# 设置工作目录
WORKDIR /app

# 安装构建依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libpq-dev \
    python3-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 升级 pip
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# 复制并安装 mcpClient
COPY mcpClient/ /app/mcpClient/
RUN pip install --no-cache-dir --prefix=/install /app/mcpClient

# 复制并安装项目依赖
COPY app/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --prefix=/install -r /app/requirements.txt

# 第二阶段：运行阶段
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 安装运行时依赖（仅安装必要的库）
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    ripgrep \
    && rm -rf /var/lib/apt/lists/*

# 从构建阶段复制安装的包
COPY --from=builder /install /usr/local

# 复制应用代码
COPY app/ /app/app/

# 暴露端口
EXPOSE 8001

# 设置环境变量
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# NumPy和OpenBLAS配置（性能优化）
ENV OPENBLAS_NUM_THREADS=1
ENV OMP_NUM_THREADS=1
ENV NUMBA_NUM_THREADS=1
ENV MKL_NUM_THREADS=1
ENV VECLIB_MAXIMUM_THREADS=1
ENV NUMEXPR_NUM_THREADS=1

# 启动命令
CMD ["python", "-m", "app.main", "--host", "0.0.0.0", "--port", "8001"]
