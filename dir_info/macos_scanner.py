import os
import json
from pathlib import Path
from typing import Union


import subprocess

from sqlite_db import fetch_from_db, init_db, path_exists_in_db, store_scan_result

def get_native_file_size(path: str) -> int:
    """Use 'du' to get actual size of directory or file in bytes."""
    try:
        result = subprocess.run(
            ['du', '-sk', path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
        size_kb = int(result.stdout.split()[0])
        return size_kb * 1024  # Convert to bytes
    except Exception as e:
        print(f"Error getting size for {path}: {e}")
        return 0

def get_native_file_size_short(path: Union[str, Path]) -> int:
    """Uses macOS native API to get size of file or folder (like Finder's Get Info)."""
    url = NSURL.fileURLWithPath_(str(path))
    try:
        resource_values, error = url.resourceValuesForKeys_error_(
            ["NSURLTotalFileSizeKey", "NSURLTotalFileAllocatedSizeKey", "NSURLIsDirectoryKey"],
            None
        )
        # Try both size keys in order
        size = resource_values.get("NSURLTotalFileAllocatedSizeKey") or resource_values.get("NSURLTotalFileSizeKey")
        return int(size) if size else 0
    except Exception:
        return 0

def scan_directory(path: str, depth=0, max_depth=3):
    path_obj = Path(path)
    if depth > max_depth:
        return None

    is_dir = path_obj.is_dir()

    result = {
        "name": path_obj.name,
        "path": str(path_obj.resolve()),
        "size": get_native_file_size(path_obj),
        "total_items": 0,
    }

    if is_dir:
        try:
            items = list(path_obj.iterdir())
        except PermissionError:
            items = []
        result["total_items"] = len(items)
        result["children"] = []

        for item in items:
            child = scan_directory(item, depth + 1, max_depth)
            if child:
                result["children"].append(child)

    return result



def scan_and_index(path: str, max_depth=3):
    """Scans and indexes only if path is not in DB."""
    abs_path = str(Path(path).resolve())
    if path_exists_in_db(abs_path):
        print(f"Already indexed: {path}")
        return fetch_from_db(abs_path)
    result = scan_directory(path, depth=0, max_depth=max_depth)
    if result:
        store_scan_result(result)
    return result

def refresh(path, max_depth=3):
    """Force re-scan and update existing records."""
    result = scan_directory(path, depth=0, max_depth=max_depth)
    if result:
        store_scan_result(result)
    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Scan and index macOS folders.")
    parser.add_argument("directory", help="Directory to scan")
    parser.add_argument("--refresh", action="store_true", help="Force re-scan and update existing records")
    args = parser.parse_args()

    init_db()
    path = str(Path(args.directory).resolve())

    if args.refresh:
        result = scan_directory(path)
        store_scan_result(result)
        print(json.dumps(result, indent=2))
    else:
        output = scan_and_index(path)
        if output:
            print(json.dumps(output, indent=2))
        else:
            print(f"{path} is already in the database.")