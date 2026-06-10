from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, List, Optional
from pathlib import Path
import json
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from macos_scanner import refresh as refresh_fn
from sqlite_db import fetch_sizes_for_paths  # Import the macOS scan function here
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pathlib import Path
from typing import Optional

from macos_scanner import (
    init_db,
    scan_directory,
    scan_and_index,
    store_scan_result,
)




# Initialize SQLite DB on app startup
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 🔁 Runs before the app starts serving
    print("🚀 App starting... initializing")
    init_db()

    yield  # ⏸️ Hand off to FastAPI app to start serving

    # 🧹 Runs on shutdown (if needed)
    print("🛑 App shutting down... cleanup here if needed")


app = FastAPI(lifespan=lifespan)

# Allow CORS for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/ui", StaticFiles(directory=".", html=True), name="htmls")



@app.get("/api/dir_info")
def get_dir_info(dirpath: str = Query(...), refresh: bool = Query(False)):
    """
    Scan and return directory info.
    If refresh=True, force rescan and update DB.
    Otherwise, only scan and index if not already indexed.
    """
    path = Path(dirpath).expanduser().resolve()

    if not path.exists():
        return JSONResponse(status_code=404, content={"error": "Path not found"})
    result = {}
    if refresh:
      result = refresh_fn(str(path), max_depth=3)
    else:
      result = scan_and_index(str(path), max_depth=3)
    
    return result

def build_children_with_db(path: Path, db_cache: dict) -> list[dict]:
    """Return immediate children of a directory with DB sizes if available (one level only)."""
    children = []
    try:
        for child in path.iterdir():
            abs_path = str(child.resolve())
            db_info = db_cache.get(abs_path, {"size": None, "total_items": 0})

            item = {
                "name": child.name,
                "path": abs_path,
                "size": db_info["size"],
                "total_items": db_info["total_items"],
            }

            if child.is_dir():
                # Only mark it, deeper children handled in /ls
                item["children"] = []
            children.append(item)
    except Exception:
        pass
    return children


@app.get("/api/ls")
def list_directory(dirpath: str = Query(...)):
    """
    List immediate files and folders in a directory (2 levels deep).
    Uses DB values for size/total_items if present, else None/0.
    """
    path = Path(dirpath).expanduser().resolve()

    if not path.exists():
        raise HTTPException(status_code=404, detail="Directory not found")
    if not path.is_dir():
        raise HTTPException(status_code=400, detail="Path is not a directory")

    # Collect paths for parent + immediate children + grandchildren
    all_paths = [str(path.resolve())]
    first_level = list(path.iterdir())
    all_paths.extend(str(c.resolve()) for c in first_level if c.exists())

    for child in first_level:
        if child.is_dir():
            try:
                all_paths.extend(str(gc.resolve()) for gc in child.iterdir())
            except Exception:
                pass

    # Query DB once for all collected paths
    db_cache = fetch_sizes_for_paths(all_paths)

    # Build response
    items = []
    for child in first_level:
        abs_path = str(child.resolve())
        db_info = db_cache.get(abs_path, {"size": None, "total_items": 0})

        item = {
            "name": child.name,
            "path": abs_path,
            "size": db_info["size"],
            "total_items": db_info["total_items"],
        }

        if child.is_dir():
            item["children"] = build_children_with_db(child, db_cache)

        items.append(item)

    return items
