"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from src.api.routes import router as api_router
from src.api.capture_routes import router as capture_router
from src.api.websocket import router as ws_router
from src.deps import set_session_factory
from src.models.database import create_db_engine, create_session_factory


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = create_db_engine()
    set_session_factory(create_session_factory(engine))
    yield


app = FastAPI(title="Poker Tracker", version="0.1.0", lifespan=lifespan)

app.include_router(api_router)
app.include_router(capture_router)
app.include_router(ws_router)

# Mount static files if the directory exists
_static_dir = Path(__file__).resolve().parent.parent / "static"
if _static_dir.is_dir():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("src.main:app", host="127.0.0.1", port=8000, reload=True)
