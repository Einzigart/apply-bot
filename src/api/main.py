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

    # Locate built React SPA dist folder
    exe_dir = Path(sys.executable).parent if getattr(sys, "frozen", False) else ROOT
    candidates = [
        ROOT / "ui" / "dist",
        Path(getattr(sys, "_MEIPASS", "")) / "ui" / "dist",
        exe_dir / "_internal" / "ui" / "dist",
        exe_dir / "ui" / "dist",
    ]
    ui_dist = next((p for p in candidates if p and p.exists() and (p / "index.html").exists()), None)

    if ui_dist:
        from starlette.responses import FileResponse

        # Explicit root index route
        @app.get("/")
        async def serve_root():
            return FileResponse(ui_dist / "index.html")

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
    parser.add_argument("--data-dir", type=str, default=None, help="Custom data directory")
    parser.add_argument("--logs-dir", type=str, default=None, help="Custom logs directory")
    args = parser.parse_args()

    import uvicorn
    app = create_app(data_dir=Path(args.data_dir) if args.data_dir else None, logs_dir=Path(args.logs_dir) if args.logs_dir else None)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
