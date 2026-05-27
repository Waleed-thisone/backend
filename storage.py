import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

STATE_FILE = Path("state.json")


def save(data: dict) -> None:
    try:
        temp_file = STATE_FILE.with_suffix(".tmp")
        with temp_file.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        temp_file.replace(STATE_FILE)
    except OSError as exc:
        logger.exception("Failed to write state.json")
        raise RuntimeError(f"Failed to write state: {exc}") from exc


def load() -> Optional[dict]:
    if not STATE_FILE.exists():
        return None
    try:
        with STATE_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        logger.exception("Failed to read state.json")
        raise RuntimeError(f"Failed to read state: {exc}") from exc
