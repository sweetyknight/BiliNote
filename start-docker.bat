@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title BiliNote Docker 一键启动

echo ============================================================
echo        BiliNote Docker 一键启动脚本
echo ============================================================
echo.

:: 解析命令行参数
set "FORCE_BUILD=0"
set "SKIP_GPU_CHECK=0"
if "%1"=="--build" set "FORCE_BUILD=1"
if "%1"=="-b" set "FORCE_BUILD=1"
if "%1"=="--cpu" set "SKIP_GPU_CHECK=1"

:: 检查 Docker 是否运行
docker info >nul 2>&1
if !errorlevel! neq 0 (
    echo [错误] Docker 未运行，请先启动 Docker Desktop
    echo.
    pause
    exit /b 1
)
echo [OK] Docker 正在运行

:: 检查 NVIDIA Docker 支持
set "COMPOSE_FILE=docker-compose.yml"
set "GPU_MODE=CPU"

if "!SKIP_GPU_CHECK!"=="1" (
    echo [*] 跳过 GPU 检测，使用 CPU 模式
    goto :after_gpu_check
)

echo [*] 检测 NVIDIA GPU 支持...
:: 先检查本地是否有 nvidia-smi 命令，避免拉取镜像
where nvidia-smi >nul 2>&1
if !errorlevel! equ 0 (
    :: 本地有 nvidia-smi，检查 Docker GPU 支持
    docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi >nul 2>&1
    if !errorlevel! equ 0 (
        echo [OK] NVIDIA GPU 支持已启用
        set "COMPOSE_FILE=docker-compose.gpu.yml"
        set "GPU_MODE=GPU"
        goto :after_gpu_check
    )
)

echo [!] NVIDIA GPU 支持未检测到
echo     可能原因:
echo     1. 未安装 NVIDIA 驱动
echo     2. 未安装 NVIDIA Container Toolkit
echo     3. 系统无 NVIDIA GPU
echo.
set /p "USER_CHOICE=是否使用 CPU 版本继续? (Y/N): "
if /i not "!USER_CHOICE!"=="Y" (
    pause
    exit /b 1
)
echo [*] 使用 CPU 版本...

:after_gpu_check

:: 检查 .env 文件是否存在
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
        echo WHISPER_MODEL_SIZE=large-v3-turbo
        echo STATIC=/static
        echo OUT_DIR=./static/screenshots
        echo LOCAL_VIDEO_PATH=D:\bilibiliDown
    ) > .env
    echo [OK] 已创建默认 .env 文件
)

:: 检查镜像是否已存在（通过检查输出是否为空）
set "NEED_BUILD=0"
set "BACKEND_IMAGE="
set "FRONTEND_IMAGE="

:: 检查 backend 镜像
for /f "delims=" %%i in ('docker images -q bilinote-backend 2^>nul') do set "BACKEND_IMAGE=%%i"
if "!BACKEND_IMAGE!"=="" (
    echo [!] 未找到 bilinote-backend 镜像
    set "NEED_BUILD=1"
) else (
    echo [OK] 找到 bilinote-backend 镜像
)

:: 检查 frontend 镜像
for /f "delims=" %%i in ('docker images -q bilinote-frontend 2^>nul') do set "FRONTEND_IMAGE=%%i"
if "!FRONTEND_IMAGE!"=="" (
    echo [!] 未找到 bilinote-frontend 镜像
    set "NEED_BUILD=1"
) else (
    echo [OK] 找到 bilinote-frontend 镜像
)

:: 如果强制构建，则设置 NEED_BUILD
if "!FORCE_BUILD!"=="1" set "NEED_BUILD=1"

echo.
echo [*] 停止旧容器...
docker-compose -f !COMPOSE_FILE! down 2>nul

echo.
if "!NEED_BUILD!"=="1" (
    echo [*] 构建并启动 Docker 容器...
    echo     使用配置文件: !COMPOSE_FILE!
    echo     首次构建可能需要几分钟，请耐心等待...
    echo.
    docker-compose -f !COMPOSE_FILE! up --build -d
) else (
    echo [*] 启动 Docker 容器...
    echo     使用配置文件: !COMPOSE_FILE!
    echo     镜像已存在，跳过构建。如需重新构建，请运行: start-docker.bat --build
    echo.
    docker-compose -f !COMPOSE_FILE! up -d
)

if !errorlevel! neq 0 (
    echo.
    echo [错误] Docker 容器启动失败！
    echo 请查看日志: docker-compose -f !COMPOSE_FILE! logs
    pause
    exit /b 1
)

echo.
echo ============================================================
echo                    启动成功！
echo ============================================================
echo   访问地址: http://localhost:8080
echo   计算模式: !GPU_MODE!
echo.
echo   常用命令:
echo   查看日志: docker-compose -f !COMPOSE_FILE! logs -f
echo   停止服务: docker-compose -f !COMPOSE_FILE! down
echo   重新构建: start-docker.bat --build
echo   强制CPU:  start-docker.bat --cpu
echo ============================================================
echo.

:: 自动打开浏览器
timeout /t 5 >nul
start http://localhost:8080

endlocal
pause
