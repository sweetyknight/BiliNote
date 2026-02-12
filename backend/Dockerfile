FROM python:3.11-slim

RUN rm -f /etc/apt/sources.list && \
    rm -rf /etc/apt/sources.list.d/* && \
    echo "deb https://mirrors.tuna.tsinghua.edu.cn/debian bookworm main contrib non-free non-free-firmware" > /etc/apt/sources.list && \
    echo "deb https://mirrors.tuna.tsinghua.edu.cn/debian bookworm-updates main contrib non-free non-free-firmware" >> /etc/apt/sources.list && \
    echo "deb https://mirrors.tuna.tsinghua.edu.cn/debian-security bookworm-security main contrib non-free non-free-firmware" >> /etc/apt/sources.list && \
    apt-get update && \
    apt-get install -y ffmpeg && \
    rm -rf /var/lib/apt/lists/*

ENV PATH="/usr/bin:${PATH}"
ENV HF_ENDPOINT=https://hf-mirror.com

WORKDIR /app

# 先复制依赖文件并安装（利用Docker层缓存）
COPY ./backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt

# 再复制源代码（代码变更不会触发重新安装依赖）
COPY ./backend /app

CMD ["python", "main.py"]
