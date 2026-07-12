import sys
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from conf.system import SYS_CONFIG
from server.database import Base, engine
from server.routers import chat, session
from server.services.conversation_service import conversation_service
from src.logger import logger


Base.metadata.create_all(bind=engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize local SQLite session storage."""
    db_path = Path(SYS_CONFIG.session_database_dir) / "session_database.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(db_path, timeout=30) as db:
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("PRAGMA synchronous=NORMAL;")
        await db.execute("PRAGMA busy_timeout=5000;")
        await db.commit()
    stale_count = await conversation_service.mark_stale_running_sessions()
    logger.info(f"Startup stale running sessions cleanup done: count={stale_count}")
    yield


app = FastAPI(title=f"{SYS_CONFIG.app_name} Local API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:9502", "http://localhost:9502"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

static_dir = Path(__file__).parent / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
async def local_ui():
    """Serve the local browser UI."""
    return FileResponse(static_dir / "index.html")


app.include_router(chat.router, tags=["Workflow"])
app.include_router(session.router, prefix="/api", tags=["Session"])


if __name__ == "__main__":
    import uvicorn

    host = "127.0.0.1"
    logger.info(f"Starting local server on http://{host}:{SYS_CONFIG.api_port}")
    uvicorn.run("server.main:app", host=host, port=SYS_CONFIG.api_port, reload=False, workers=1)
