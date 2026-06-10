import os
from pathlib import Path
import sqlite3
from typing import Optional

DB_PATH = "dir_info.db"

def get_db_connection():
    return sqlite3.connect(DB_PATH)

def init_db():
    with get_db_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS dir_info (
                path TEXT PRIMARY KEY,
                name TEXT,
                size INTEGER,
                total_items INTEGER
            )
        """)
        conn.commit()

def path_exists_in_db(path: str) -> bool:
    with get_db_connection() as conn:
        cursor = conn.execute("SELECT 1 FROM dir_info WHERE path = ?", (path,))
        return cursor.fetchone() is not None

def insert_or_update_entry(record: dict):
    with get_db_connection() as conn:
        conn.execute("""
            INSERT INTO dir_info (path, name, size, total_items)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
                name=excluded.name,
                size=excluded.size,
                total_items=excluded.total_items
        """, (
            record["path"],
            record["name"],
            record["size"],
            record["total_items"]
        ))
        conn.commit()

def delete_entry(path: str):
    with get_db_connection() as conn:
        conn.execute("DELETE FROM dir_info WHERE path = ?", (path,))
        conn.commit()

def store_scan_result(scan_result: Optional[dict]):
    """Stores scan result recursively."""
    if not scan_result:
        return
    insert_or_update_entry(scan_result)
    if "children" in scan_result:
        for child in scan_result["children"]:
            store_scan_result(child)
    return scan_result


def fetch_from_db(root_path: str) -> dict:
    root_path = str(Path(root_path).resolve())

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        # Fetch all rows where path starts with root_path
        like_pattern = root_path + "%"  # SQLite LIKE pattern
        cursor.execute("""
            SELECT path, name, size, total_items
            FROM dir_info
            WHERE path LIKE ?
            ORDER BY LENGTH(path) ASC
        """, (like_pattern,))
        rows = cursor.fetchall()

    if not rows:
        return None

    # Step 1: Build a dict of nodes
    nodes = {}
    for path, name, size, total_items in rows:
        nodes[path] = {
            "name": name,
            "path": path,
            "size": size,
            "total_items": total_items,
            "children": []
        }

    # Step 2: Nest children into parents
    for path in sorted(nodes.keys(), key=lambda x: x.count(os.sep), reverse=True):
        parent_path = str(Path(path).parent)
        if parent_path in nodes and parent_path != path:
            nodes[parent_path]["children"].append(nodes[path])

    # Step 3: Return the root node
    return nodes[root_path]

def fetch_sizes_for_paths(paths: list[str]) -> dict[str, dict]:
    """
    Fetch size + total_items for a list of absolute paths.
    Returns { path: {"size": int|None, "total_items": int|0} }
    """
    if not paths:
        return {}

    placeholders = ",".join("?" for _ in paths)
    query = f"""
        SELECT path, size, total_items
        FROM dir_info
        WHERE path IN ({placeholders})
    """

    result = {}
    with get_db_connection() as conn:
        cursor = conn.execute(query, paths)
        for path, size, total_items in cursor.fetchall():
            result[path] = {
                "size": size,
                "total_items": total_items
            }
    return result
