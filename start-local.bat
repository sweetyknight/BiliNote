@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title BiliNote 本地启动

echo ============================================================
echo            BiliNote 本地一键启动脚本
echo ============================================================
echo.

:: 获取脚本所在目录
set "ROOT_DIR=%~dp0"
cd /d "%ROOT_DIR%"

:: 检查 Python 是否安装
call python --version >nul 2>&1
if !errorlevel! neq 0 (
    echo [错误] 未检测到 Python，请先安装 Python 3.11+
    pause
    exit /b 1
)
echo [OK] Python 已安装

:: 检查 Node.js 是否安装
call node --version >nul 2>&1
if !errorlevel! neq 0 (
    echo [错误] 未检测到 Node.js，请先安装 Node.js 18+
    pause
    exit /b 1
)
echo [OK] Node.js 已安装

:: 检查 pnpm 是否安装
echo [*] 检查 pnpm...
call pnpm --version >nul 2>&1
if !errorlevel! neq 0 (
    echo [!] 未检测到 pnpm，正在安装...
    call npm install -g pnpm
    if !errorlevel! neq 0 (
        echo [错误] pnpm 安装失败
        pause
        exit /b 1
    )
)
echo [OK] pnpm 已安装

echo.
echo ============================================================
echo  配置后端环境
echo ============================================================
echo.

cd /d "%ROOT_DIR%backend"

:: 检查虚拟环境
set "NEED_INSTALL_DEPS=0"
if not exist "venv" (
    echo [*] 正在创建 Python 虚拟环境...
    call python -m venv venv
    if !errorlevel! neq 0 (
        echo [错误] 创建虚拟环境失败
        pause
        exit /b 1
    )
    set "NEED_INSTALL_DEPS=1"
)
echo [OK] Python 虚拟环境已就绪

:: 激活虚拟环境
call venv\Scripts\activate.bat

:: 检查关键依赖是否已安装
python -c "import uvicorn, torch" >nul 2>&1
if !errorlevel! neq 0 (
    set "NEED_INSTALL_DEPS=1"
)

:: 安装依赖（首次创建或关键依赖缺失时）
if "!NEED_INSTALL_DEPS!"=="1" (
    echo [*] Installing backend dependencies...
    call pip install -r requirements.txt -q
    if !errorlevel! neq 0 (
        echo [ERROR] Failed to install backend dependencies
        pause
        exit /b 1
    )
    echo [OK] Backend dependencies installed
) else (
    echo [OK] Backend dependencies ready (skipped)
)

:: GPU 检测
echo.
echo [*] 检测 GPU 加速支持...
set "GPU_MODE=CPU"
set "CUDA_AVAILABLE=0"
set "CUDA_VERSION="
set "TORCH_VERSION="
set "GPU_NAME="

python -c "import torch" >nul 2>&1
set "TORCH_IMPORT_ERR=!errorlevel!"

if !TORCH_IMPORT_ERR! neq 0 (
    echo [!] PyTorch 未安装或不可用，将使用 CPU 模式
    echo     如需启用 GPU 加速，请运行:
    echo     pip install torch --index-url https://download.pytorch.org/whl/cu124
    goto :after_gpu_detect
)

call :detect_torch_info

if "!CUDA_AVAILABLE!"=="1" (
    echo [OK] GPU 加速已启用: !GPU_NAME!
    echo     - PyTorch 版本: !TORCH_VERSION!
    echo     - CUDA 版本: !CUDA_VERSION!
    set "GPU_MODE=GPU"
) else (
    echo [!] GPU 加速未启用，将使用 CPU 模式
    echo     - PyTorch 版本: !TORCH_VERSION!
    if "!CUDA_VERSION!"=="" (
        echo     - 当前 PyTorch 为 CPU 版 ^(CUDA 版本为空^)
    ) else (
        echo     - 当前 PyTorch CUDA 版本: !CUDA_VERSION!
    )
    echo     可能原因:
    echo     - 未安装 NVIDIA 显卡驱动
    echo     - PyTorch 未安装 CUDA 版本
    echo     - 系统无 NVIDIA GPU
    echo.
    echo     如需启用 GPU 加速，请运行:
    echo     pip uninstall torch -y
    echo     pip install torch --index-url https://download.pytorch.org/whl/cu124
)

:after_gpu_detect

cd /d "%ROOT_DIR%"

echo.
echo ============================================================
echo  配置前端环境
echo ============================================================
echo.

cd /d "%ROOT_DIR%BiliNote_frontend"

:: 检查 node_modules
if not exist "node_modules" (
    echo [*] 正在安装前端依赖...
    call pnpm install
    if !errorlevel! neq 0 (
        echo [错误] 前端依赖安装失败
        pause
        exit /b 1
    )
    echo [OK] 前端依赖已安装
) else (
    echo [OK] 前端依赖已就绪 (跳过安装)
)

cd /d "%ROOT_DIR%"

:: 检查 .env 文件
if not exist ".env" (
    echo [!] 未检测到 .env 文件，正在创建默认配置...
    (
        echo # BiliNote 环境变量配置
        echo BACKEND_PORT=8483
        echo BACKEND_HOST=0.0.0.0
        echo VITE_API_BASE_URL=http://localhost:8483
        echo VITE_FRONTEND_PORT=3015
        echo APP_PORT=8080
        echo TRANSCRIBER_TYPE=fast-whisper
        echo # Whisper 模型大小: tiny base small medium large-v1 large-v2 large-v3-turbo
        echo WHISPER_MODEL_SIZE=large-v3-turbo
        echo STATIC=/static
        echo OUT_DIR=./static/screenshots
    ) > .env
    echo [OK] 已创建默认 .env 文件
)

echo.
echo ============================================================
echo  启动服务
echo ============================================================
echo.

:: 启动后端服务（新窗口）
echo [*] Starting backend server...
start "BiliNote Backend" cmd /k "cd /d ""!ROOT_DIR!backend"" && call venv\Scripts\activate.bat && python main.py"

:: 等待后端启动
echo [*] Waiting for backend to start...
timeout /t 5 >nul

:: 启动前端服务（新窗口）
echo [*] Starting frontend server...
start "BiliNote Frontend" cmd /k "cd /d ""!ROOT_DIR!BiliNote_frontend"" && pnpm run dev"

echo.
echo ============================================================
echo                    启动成功！
echo ============================================================
echo   前端地址: http://localhost:3015
echo   后端地址: http://localhost:8483
echo   计算模式: !GPU_MODE!
echo.
echo   注意: 后端和前端已在独立窗口中运行
echo   关闭这些窗口即可停止服务
echo ============================================================
echo.

:: 等待一下然后打开浏览器
timeout /t 5 >nul
start http://localhost:3015

endlocal
pause
goto :eof

:: --------- 子程序：获取 Torch / CUDA 信息 ----------
:detect_torch_info
set "CUDA_AVAILABLE=0"
set "CUDA_VERSION="
set "TORCH_VERSION="
set "GPU_NAME="

for /f "delims=" %%i in ('python -c "import torch; print(torch.__version__)" 2^>nul') do set "TORCH_VERSION=%%i"
for /f "delims=" %%i in ('python -c "import torch; v=torch.version.cuda; print(v if v else '')" 2^>nul') do set "CUDA_VERSION=%%i"

python -c "import torch,sys; sys.exit(0 if torch.cuda.is_available() else 1)" >nul 2>&1
if not errorlevel 1 set "CUDA_AVAILABLE=1"

if "!CUDA_AVAILABLE!"=="1" for /f "delims=" %%i in ('python -c "import torch; print(torch.cuda.get_device_name(0))" 2^>nul') do set "GPU_NAME=%%i"

exit /b 0