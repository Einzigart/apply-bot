"""FastAPI application factory and entry point."""
from __future__ import annotations

import argparse
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .. import db
from ..config import DATA_DIR, LOGS_DIR, ROOT
from .routers import applications, dashboard, jobs, profile, runs, settings


def create_app(data_dir: Path | None = None, logs_dir: Path | None = None) -> FastAPI:
    data_path = Path(data_dir or DATA_DIR)
    logs_path = Path(logs_dir or LOGS_DIR)
    db_path = data_path / "jobs.db"

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Startup: ensure schema and mark interrupted runs
        conn = db.connect(db_path)
        db.mark_interrupted_runs(conn)
        conn.close()
        yield
        # Shutdown cleanup

    app = FastAPI(
        title="apply-bot API",
        version="0.1.0-beta.1",
        lifespan=lifespan,
    )

    # Attach shared paths to state
    app.state.data_dir = data_path
    app.state.logs_dir = logs_path
    app.state.db_path = db_path

    # CORS for Vite dev server
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routers
    app.include_router(dashboard.router)
    app.include_router(jobs.router)
    app.include_router(applications.router)
    app.include_router(runs.router)
    app.include_router(profile.router)
    app.include_router(settings.router)

    # If built React SPA dist folder exists, serve it with SPA fallback
    ui_dist = (ROOT / "ui" / "dist")
    if not ui_dist.exists():
        resource_root = Path(getattr(sys, "_MEIPASS", ROOT))
        ui_dist = resource_root / "ui" / "dist"

    if ui_dist.exists():
        from starlette.responses import FileResponse

        # Serve static assets
        app.mount("/assets", StaticFiles(directory=str(ui_dist / "assets")), name="assets")

        # Catch-all for SPA client routing (HTML5 history)
        @app.get("/{full_path:path}")
        async def serve_spa(full_path: str):
            file_path = ui_dist / full_path
            if file_path.is_file():
                return FileResponse(file_path)
            return FileResponse(ui_dist / "index.html")

    return app


def main():
    parser = argparse.ArgumentParser(description="apply-bot FastAPI server")
    parser.add_argument("--port", type=int, default=5139, help="Port to bind (default: 5139)")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host (default: 127.0.0.1)")
    args = parser.parse_args()

    import uvicorn
    app = create_app()
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
