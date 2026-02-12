#!/bin/bash

# BiliNote Docker 一键启动脚本

set -e

echo "============================================================"
echo "        BiliNote Docker 一键启动脚本"
echo "============================================================"
echo ""

# 解析命令行参数
FORCE_BUILD=0
SKIP_GPU_CHECK=0
for arg in "$@"; do
    case $arg in
        --build|-b)
            FORCE_BUILD=1
            ;;
        --cpu)
            SKIP_GPU_CHECK=1
            ;;
    esac
done

# 检查 Docker 是否运行
if ! docker info > /dev/null 2>&1; then
    echo "[错误] Docker 未运行，请先启动 Docker"
    exit 1
fi
echo "[OK] Docker 正在运行"

# 检查 NVIDIA Docker 支持
COMPOSE_FILE="docker-compose.yml"
GPU_MODE="CPU"

if [ "$SKIP_GPU_CHECK" -eq 1 ]; then
    echo "[*] 跳过 GPU 检测，使用 CPU 模式"
else
    echo "[*] 检测 NVIDIA GPU 支持..."
    # 先检查本地是否有 nvidia-smi 命令，避免拉取镜像
    if command -v nvidia-smi &> /dev/null; then
        if docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi > /dev/null 2>&1; then
            echo "[OK] NVIDIA GPU 支持已启用"
            COMPOSE_FILE="docker-compose.gpu.yml"
            GPU_MODE="GPU"
        fi
    fi
    
    if [ "$GPU_MODE" = "CPU" ]; then
        echo "[!] NVIDIA GPU 支持未检测到"
        echo "    可能原因:"
        echo "    1. 未安装 NVIDIA 驱动"
        echo "    2. 未安装 NVIDIA Container Toolkit"
        echo "    3. 系统无 NVIDIA GPU"
        echo ""
        read -p "是否使用 CPU 版本继续? (y/n): " choice
        if [[ "$choice" != "y" && "$choice" != "Y" ]]; then
            exit 1
        fi
        echo "[*] 使用 CPU 版本..."
    fi
fi

# 检查 .env 文件是否存在
if [ ! -f ".env" ]; then
    echo "[!] 未检测到 .env 文件，正在创建默认配置..."
    cat > .env << EOF
# BiliNote 环境变量配置
BACKEND_PORT=8483
BACKEND_HOST=0.0.0.0
VITE_API_BASE_URL=http://localhost:8483
VITE_FRONTEND_PORT=3015
APP_PORT=8080
TRANSCRIBER_TYPE=fast-whisper
WHISPER_MODEL_SIZE=large-v3-turbo
STATIC=/static
OUT_DIR=./static/screenshots
LOCAL_VIDEO_PATH=/home/user/videos
EOF
    echo "[OK] 已创建默认 .env 文件"
fi

# 检查镜像是否已存在
NEED_BUILD=0
if ! docker images | grep -q "bilinote-backend"; then
    NEED_BUILD=1
fi
if ! docker images | grep -q "bilinote-frontend"; then
    NEED_BUILD=1
fi

# 如果强制构建或镜像不存在，则构建
if [ "$FORCE_BUILD" -eq 1 ]; then
    NEED_BUILD=1
fi

echo ""
echo "[*] 停止旧容器..."
docker-compose -f $COMPOSE_FILE down 2>/dev/null || true

echo ""
# 临时禁用 set -e，以便捕获 docker-compose 的退出码
set +e
if [ "$NEED_BUILD" -eq 1 ]; then
    echo "[*] 构建并启动 Docker 容器 (使用 $COMPOSE_FILE)..."
    echo "    首次构建可能需要几分钟，请耐心等待..."
    echo ""
    docker-compose -f $COMPOSE_FILE up --build -d
    COMPOSE_EXIT=$?
else
    echo "[*] 启动 Docker 容器 (使用 $COMPOSE_FILE)..."
    echo "    镜像已存在，跳过构建。如需重新构建，请运行: ./start-docker.sh --build"
    echo ""
    docker-compose -f $COMPOSE_FILE up -d
    COMPOSE_EXIT=$?
fi
set -e

# 等待 docker-compose 输出完成
sleep 1

if [ $COMPOSE_EXIT -ne 0 ]; then
    echo ""
    echo "[错误] Docker 容器启动失败！"
    echo "请查看日志: docker-compose -f $COMPOSE_FILE logs"
    exit 1
fi

echo ""
echo "============================================================"
echo "                    启动成功！"
echo "============================================================"
echo "  访问地址: http://localhost:8080"
echo "  计算模式: $GPU_MODE"
echo ""
echo "  常用命令:"
echo "    查看日志: docker-compose -f $COMPOSE_FILE logs -f"
echo "    停止服务: docker-compose -f $COMPOSE_FILE down"
echo "    重新构建: ./start-docker.sh --build"
echo "    强制CPU:  ./start-docker.sh --cpu"
echo "============================================================"
echo ""

# 尝试自动打开浏览器
sleep 2
if command -v xdg-open > /dev/null; then
    xdg-open http://localhost:8080 2>/dev/null || true
elif command -v open > /dev/null; then
    open http://localhost:8080 2>/dev/null || true
fi

echo "按 Ctrl+C 退出..."
