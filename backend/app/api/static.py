"""Serve the production React build, with client-side-routing fallback."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse


def mount_frontend(app: FastAPI, dist: Optional[Path]) -> None:
    """Must be called after all API routes: the catch-all would shadow them."""
    if dist is None or not (dist / "index.html").is_file():
        @app.get("/", include_in_schema=False)
        def home():
            return {"message": "Welcome to NekoAI Backend", "frontend": "not built"}
        return

    root = dist.resolve()
    index = root / "index.html"

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(404, "Not found")
        try:
            candidate = (root / full_path).resolve()
            if full_path and candidate.is_file() and candidate.is_relative_to(root):
                return FileResponse(candidate)
        except (OSError, ValueError):
            pass
        return FileResponse(index, headers={"Cache-Control": "no-cache"})