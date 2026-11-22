"""Packaged, framework-independent HTML element and CSS class primitives."""

from pathlib import Path
from typing import Literal

UIAsset = Literal["ui.css", "ui.js", "showcase.html"]


def asset_path(name: UIAsset) -> Path:
    """Return an allowlisted asset from the installed Foundation wheel."""
    if name not in {"ui.css", "ui.js", "showcase.html"}:
        raise ValueError("Unknown UI asset")
    return Path(__file__).parent / "static" / name
