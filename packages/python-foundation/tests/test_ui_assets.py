from pathlib import Path

import pytest

from python_foundation.ui_assets import asset_path


def test_packaged_ui_assets_are_allowlisted():
    for name in ("ui.css", "ui.js", "showcase.html"):
        asset = asset_path(name)
        assert asset.is_file()
        assert asset.parent == Path(__import__("python_foundation").__file__).parent / "static"
    for invalid in ("../settings.py", ".env", "/etc/passwd", "unknown.js"):
        with pytest.raises(ValueError, match="Unknown UI asset"):
            asset_path(invalid)
