"""Small, process-local JSON storage for the single-process development server."""
import json
import os
import tempfile
from pathlib import Path
from threading import RLock

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
_lock = RLock()

class StorageError(Exception):
    pass

def _path(collection: str) -> Path:
    return DATA_DIR / f"{collection}.json"

def _ensure_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        _atomic_write(path, [])

def _atomic_write(path: Path, records: list[dict]) -> None:
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.stem}-", suffix=".tmp", dir=path.parent, text=True)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(records, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise

def read_records(collection: str) -> list[dict]:
    with _lock:
        path = _path(collection)
        _ensure_file(path)
        try:
            with path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError) as error:
            raise StorageError(f"Cannot read {path.name}; it was not changed.") from error
        if not isinstance(data, list):
            raise StorageError(f"Cannot read {path.name}; it must contain a JSON array.")
        return data

def update_records(collection: str, mutate):
    """Run one read-modify-write transaction under the process-local lock."""
    with _lock:
        records = read_records(collection)
        result = mutate(records)
        _atomic_write(_path(collection), records)
        return result
