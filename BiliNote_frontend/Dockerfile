# === 前端构建阶段 ===
FROM node:18-alpine AS builder

# 安装 pnpm
RUN npm install -g pnpm

# 设置 CI 环境变量
ENV CI=true

# 设置工作目录
WORKDIR /app

# 先复制依赖文件（利用Docker层缓存）
COPY ./BiliNote_frontend/package.json ./BiliNote_frontend/pnpm-lock.yaml* ./

# 安装依赖
RUN pnpm install

# 复制源代码（排除node_modules，由.dockerignore处理）
COPY ./BiliNote_frontend/src ./src
COPY ./BiliNote_frontend/public ./public
COPY ./BiliNote_frontend/index.html ./
COPY ./BiliNote_frontend/vite.config.ts ./
COPY ./BiliNote_frontend/tsconfig*.json ./
COPY ./BiliNote_frontend/tailwind.config.cjs ./
COPY ./BiliNote_frontend/postcss.config.cjs ./
COPY ./BiliNote_frontend/eslint.config.js ./
COPY ./BiliNote_frontend/components.json ./

# 构建
RUN pnpm run build

# --- 阶段2：使用 nginx 作为静态服务器 ---
FROM nginx:1.25-alpine

# 安装 curl 用于健康检查
RUN apk add --no-cache curl

# 删除默认配置
RUN rm -rf /etc/nginx/conf.d/default.conf

# 创建模板目录并复制配置模板
RUN mkdir -p /etc/nginx/templates
COPY ./BiliNote_frontend/deploy/default.conf.template /etc/nginx/templates/default.conf.template

# 复制启动脚本并设置执行权限
# 使用 sed 转换 Windows CRLF 行结尾为 Unix LF
COPY ./BiliNote_frontend/deploy/start.sh /start.sh
RUN sed -i 's/\r$//' /start.sh && chmod +x /start.sh

# 拷贝构建产物
COPY --from=builder /app/dist /usr/share/nginx/html

# 使用启动脚本作为入口点（动态替换环境变量）
CMD ["/start.sh"]
