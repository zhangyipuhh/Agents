# ==================================================================
# 警告：此文件由 generate_docker 自动生成
# 请勿直接修改此文件。请更新 docker-template/Dockerfile
# 然后重新生成此文件。
# ==================================================================

# 第一阶段：构建阶段
FROM python:3.11-slim as builder

WORKDIR /app

RUN sed -i 's/deb.debian.org/mirrors.tuna.tsinghua.edu.cn/g' /etc/apt/sources.list.d/*.sources /etc/apt/sources.list 2>/dev/null || true && \
    apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libpq-dev \
    python3-dev \
    build-essential && \
    rm -rf /var/lib/apt/lists/*

RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple && \
    pip config set global.timeout 600 && \
    pip install --no-cache-dir --upgrade pip setuptools wheel

COPY mcpClient/ /app/mcpClient/
RUN pip install --no-cache-dir --prefix=/install /app/mcpClient

COPY app/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --prefix=/install -r /app/requirements.txt

# 第二阶段：运行阶段
FROM python:3.11-slim

WORKDIR /app

RUN sed -i 's/deb.debian.org/mirrors.tuna.tsinghua.edu.cn/g' /etc/apt/sources.list.d/*.sources /etc/apt/sources.list 2>/dev/null || true && \
    apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    ripgrep \
    libreoffice-writer \
    libreoffice-core \
    iputils-ping \
    fonts-dejavu-core && \
    rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local

COPY app/ /app/app/

RUN pip install --no-cache-dir packaging>=23.0

EXPOSE 8001

ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
    PIP_TIMEOUT=600 \
    OPENBLAS_NUM_THREADS=1 \
    OMP_NUM_THREADS=1 \
    NUMBA_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    VECLIB_MAXIMUM_THREADS=1 \
    NUMEXPR_NUM_THREADS=1

# ==================================================================
# 沙箱功能部署说明（2026-06-12 新增）
#
# 默认构建的镜像不包含 Docker daemon，sandbox 工具默认走 local 模式。
# 若要在容器内使用 sandbox 工具的 Docker 沙箱，请选择以下方式之一：
#
# 1. socket 模式（推荐，安全性可控）：
#    启动时挂载宿主机 /var/run/docker.sock 和数据卷：
#      docker run -v /var/run/docker.sock:/var/run/docker.sock \
#                 -v ./data:/app/data \
#                 -e SANDBOX_DOCKER_MODE=socket \
#                 -e SANDBOX_DOCKER_HOST=unix:///var/run/docker.sock \
#                 -e SANDBOX_HOST_WORKSPACE_PREFIX=/app/data \
#                 <image>
#    或参考项目根 docker-compose.sandbox.example.yml
#
# 2. dind 模式：需 --privileged 启动，不推荐生产环境使用
#
# 3. local 模式：仅当应用直接跑在宿主机（无容器）时使用
# ==================================================================

CMD ["python", "-m", "app.main", "--host", "0.0.0.0", "--port", "8001"]