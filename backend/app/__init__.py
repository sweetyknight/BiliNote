from fastapi import FastAPI
from fastapi.responses import JSONResponse

from .routers import note, provider, model, config



def create_app(lifespan) -> FastAPI:
    app = FastAPI(title="BiliNote",lifespan=lifespan)
    app.include_router(note.router, prefix="/api")
    app.include_router(provider.router, prefix="/api")
    app.include_router(model.router,prefix="/api")
    app.include_router(config.router,  prefix="/api")

    # 健康检查端点（用于 Docker 容器编排）
    @app.get("/health")
    async def health_check():
        return JSONResponse(content={"status": "ok"}, status_code=200)

    return app
