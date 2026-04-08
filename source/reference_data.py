from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any
import json


REFERENCE_DIR = Path(__file__).resolve().parents[1] / "reference"
REFERENCE_FILES = {
    "common": "common_data.json",
    "method_api": "method_api.json",
    "test_data": "test_data.json",
}


@lru_cache(maxsize=1)
def load_reference_data() -> dict[str, Any]:
    return {
        name: _load_json(REFERENCE_DIR / filename)
        for name, filename in REFERENCE_FILES.items()
    }


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)
