"""Shared configuration constants for the Paladin Control Plane backend."""

import os
from pathlib import Path

DATA_ROOT = Path(
    os.environ.get(
        "PALADIN_DATA_ROOT",
        str(Path.home() / "paladin-control" / "data" / "projects"),
    )
)
