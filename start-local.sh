#!/bin/bash

# BiliNote 本地一键启动脚本

set -e

echo "============================================================"
echo "           BiliNote 本地一键启动脚本"
echo "============================================================"
echo ""

# 获取脚本所在目录
ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

# 检测 Python 命令（兼容 Windows 和 Linux/Mac）
# Windows Git Bash 优先使用 python，Linux/Mac 优先使用 python3
if command -v python &> /dev/null && python --version 2>&1 | grep -q "Python 3"; then
    PYTHON_CMD="python"
elif command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
else
    echo "[错误] 未检测到 Python，请先安装 Python 3.11+"
    exit 1
fi
PYTHON_VERSION=$($PYTHON_CMD --version 2>&1)
echo "[OK] Python 已安装: $PYTHON_VERSION"

# 检查 Node.js 是否安装
if ! command -v node &> /dev/null; then
    echo "[错误] 未检测到 Node.js，请先安装 Node.js 18+"
    exit 1
fi
echo "[OK] Node.js 已安装: $(node --version)"

# 检查 pnpm 是否安装
echo "[*] 检查 pnpm..."
if ! command -v pnpm &> /dev/null; then
    echo "[!] 未检测到 pnpm，正在安装..."
    npm install -g pnpm
    if [ $? -ne 0 ]; then
        echo "[错误] pnpm 安装失败"
        exit 1
    fi
fi
echo "[OK] pnpm 已安装: $(pnpm --version)"

echo ""
echo "============================================================"
echo " 配置后端环境"
echo "============================================================"
echo ""

cd "$ROOT_DIR/backend"

# 检查虚拟环境
NEED_INSTALL_DEPS=0
if [ ! -d "venv" ]; then
    echo "[*] 正在创建 Python 虚拟环境..."
    $PYTHON_CMD -m venv venv
    if [ $? -ne 0 ]; then
        echo "[错误] 创建虚拟环境失败"
        exit 1
    fi
    NEED_INSTALL_DEPS=1
fi
echo "[OK] Python 虚拟环境已就绪"

# 激活虚拟环境（兼容 Windows Git Bash 和 Linux/Mac）
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
elif [ -f "venv/Scripts/activate" ]; then
    source venv/Scripts/activate
else
    echo "[错误] 无法找到虚拟环境激活脚本"
    exit 1
fi

# 检查关键依赖是否已安装 (uvicorn 和 torch)
if ! $PYTHON_CMD -c "import uvicorn, torch" &> /dev/null; then
    NEED_INSTALL_DEPS=1
fi

# 安装依赖（首次创建或关键依赖缺失时）
if [ "$NEED_INSTALL_DEPS" -eq 1 ]; then
    echo "[*] Installing backend dependencies..."
    pip install -r requirements.txt -q
    if [ $? -ne 0 ]; then
        echo "[ERROR] Failed to install backend dependencies"
        exit 1
    fi
    echo "[OK] Backend dependencies installed"
else
    echo "[OK] Backend dependencies ready (skipped)"
fi

# GPU 检测
echo ""
echo "[*] 检测 GPU 加速支持..."
GPU_MODE="CPU"
CUDA_AVAILABLE=0
CUDA_VERSION=""
TORCH_VERSION=""
GPU_NAME=""

# 先检查 torch 能否导入
if ! $PYTHON_CMD -c "import torch" &> /dev/null; then
    echo "[!] PyTorch 未安装或不可用，将使用 CPU 模式"
    echo "    如需启用 GPU 加速，请运行:"
    echo "    pip install torch --index-url https://download.pytorch.org/whl/cu124"
else
    # 获取 torch 版本信息
    TORCH_VERSION=$($PYTHON_CMD -c "import torch; print(torch.__version__)" 2>/dev/null)
    CUDA_VERSION=$($PYTHON_CMD -c "import torch; v=torch.version.cuda; print(v if v else '')" 2>/dev/null)
    
    # 检查 CUDA 是否可用
    if $PYTHON_CMD -c "import torch,sys; sys.exit(0 if torch.cuda.is_available() else 1)" 2>/dev/null; then
        CUDA_AVAILABLE=1
        GPU_NAME=$($PYTHON_CMD -c "import torch; print(torch.cuda.get_device_name(0))" 2>/dev/null)
    fi
    
    if [ "$CUDA_AVAILABLE" -eq 1 ]; then
        echo "[OK] GPU 加速已启用: $GPU_NAME"
        echo "    - PyTorch 版本: $TORCH_VERSION"
        echo "    - CUDA 版本: $CUDA_VERSION"
        GPU_MODE="GPU"
    else
        echo "[!] GPU 加速未启用，将使用 CPU 模式"
        echo "    - PyTorch 版本: $TORCH_VERSION"
        if [ -z "$CUDA_VERSION" ]; then
            echo "    - 当前 PyTorch 为 CPU 版 (CUDA 版本为空)"
        else
            echo "    - 当前 PyTorch CUDA 版本: $CUDA_VERSION"
        fi
        echo "    可能原因:"
        echo "    - 未安装 NVIDIA 显卡驱动"
        echo "    - PyTorch 未安装 CUDA 版本"
        echo "    - 系统无 NVIDIA GPU"
        echo ""
        echo "    如需启用 GPU 加速，请运行:"
        echo "    pip uninstall torch -y"
        echo "    pip install torch --index-url https://download.pytorch.org/whl/cu124"
    fi
fi

cd "$ROOT_DIR"

echo ""
echo "============================================================"
echo " 配置前端环境"
echo "============================================================"
echo ""

cd "$ROOT_DIR/BiliNote_frontend"

# 检查 node_modules
if [ ! -d "node_modules" ]; then
    echo "[*] 正在安装前端依赖..."
    pnpm install
    if [ $? -ne 0 ]; then
        echo "[错误] 前端依赖安装失败"
        exit 1
    fi
    echo "[OK] 前端依赖已安装"
else
    echo "[OK] 前端依赖已就绪 (跳过安装)"
fi

cd "$ROOT_DIR"

# 检查 .env 文件
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
# Whisper 模型大小: tiny base small medium large-v1 large-v2 large-v3-turbo
WHISPER_MODEL_SIZE=large-v3-turbo
STATIC=/static
OUT_DIR=./static/screenshots
EOF
    echo "[OK] 已创建默认 .env 文件"
fi

echo ""
echo "============================================================"
echo " 启动服务"
echo "============================================================"
echo ""

# 清理函数 - 在脚本退出时清理后台进程
cleanup() {
    echo ""
    echo "[*] Stopping services..."
    if [ ! -z "$TAIL_PID" ]; then
        kill $TAIL_PID 2>/dev/null || true
    fi
    if [ ! -z "$BACKEND_PID" ]; then
        kill $BACKEND_PID 2>/dev/null || true
    fi
    if [ ! -z "$FRONTEND_PID" ]; then
        kill $FRONTEND_PID 2>/dev/null || true
    fi
    echo "[OK] Services stopped"
    echo "日志文件保存在:"
    echo "  - 后端: $ROOT_DIR/backend/backend.log"
    echo "  - 前端: $ROOT_DIR/BiliNote_frontend/frontend.log"
    exit 0
}

trap cleanup SIGINT SIGTERM

# 启动后端服务（后台）
echo "[*] Starting backend server..."
cd "$ROOT_DIR/backend"
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
else
    source venv/Scripts/activate
fi

# 创建日志文件
BACKEND_LOG="$ROOT_DIR/backend/backend.log"
$PYTHON_CMD main.py > "$BACKEND_LOG" 2>&1 &
BACKEND_PID=$!
echo "[OK] Backend server started (PID: $BACKEND_PID)"

# 等待后端启动并检查是否成功
echo "[*] Waiting for backend to start..."
sleep 5

# 检查后端进程是否还在运行
if ! kill -0 $BACKEND_PID 2>/dev/null; then
    echo "[错误] 后端服务启动失败！"
    echo "错误日志:"
    echo "----------------------------------------"
    cat "$BACKEND_LOG"
    echo "----------------------------------------"
    exit 1
fi

# 检查后端是否响应
HEALTH_CHECK_URL="http://localhost:8483/api/sys_check"
if command -v curl &> /dev/null; then
    for i in 1 2 3 4 5; do
        if curl -s "$HEALTH_CHECK_URL" > /dev/null 2>&1; then
            echo "[OK] Backend health check passed"
            HEALTH_OK=1
            break
        fi
        if [ $i -eq 5 ]; then
            echo "[警告] 后端健康检查未通过，但进程仍在运行"
            echo "查看日志: cat $BACKEND_LOG"
            HEALTH_OK=0
        fi
        sleep 2
    done
fi

# 启动前端服务（后台）
echo "[*] Starting frontend server..."
cd "$ROOT_DIR/BiliNote_frontend"
FRONTEND_LOG="$ROOT_DIR/BiliNote_frontend/frontend.log"
pnpm run dev > "$FRONTEND_LOG" 2>&1 &
FRONTEND_PID=$!
echo "[OK] Frontend server started (PID: $FRONTEND_PID)"

# 等待前端启动
sleep 3

echo ""
echo "============================================================"
echo "                    启动成功！"
echo "============================================================"
echo "  前端地址: http://localhost:3015"
echo "  后端地址: http://localhost:8483"
echo "  计算模式: $GPU_MODE"
echo ""
echo "  日志文件:"
echo "  - 后端: $BACKEND_LOG"
echo "  - 前端: $FRONTEND_LOG"
echo ""
echo "  按 Ctrl+C 停止所有服务"
echo "============================================================"
echo ""

# 等待一下然后打开浏览器
sleep 2
if command -v xdg-open > /dev/null; then
    xdg-open http://localhost:3015 2>/dev/null || true
elif command -v open > /dev/null; then
    open http://localhost:3015 2>/dev/null || true
fi

# 实时显示后端日志
echo "显示后端日志 (按 Ctrl+C 停止所有服务):"
echo "----------------------------------------"
tail -f "$BACKEND_LOG" &
TAIL_PID=$!

# 等待用户中断
wait $BACKEND_PID $FRONTEND_PID 2>/dev/null
