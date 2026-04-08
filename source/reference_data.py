from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any
import json


REFERENCE_FILE = Path(__file__).resolve().parents[1] / "reference" / "app_reference.json"


@lru_cache(maxsize=1)
def load_reference_data() -> dict[str, Any]:
    with REFERENCE_FILE.open("r", encoding="utf-8") as handle:
        return json.load(handle)
