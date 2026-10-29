"""Start the separately installed Kev runtime, reading configuration without shell evaluation."""

import os
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
values = dotenv_values(ROOT / ".env")
repo = Path(
    os.environ.get("KEV_REPO_DIR") or values.get("KEV_REPO_DIR") or str(ROOT / ".tools/kev")
).expanduser()
if not repo.is_absolute():
    repo = ROOT / repo
python = repo / ".venv/bin/python"
if not python.is_file():
    raise SystemExit("Run ./scripts/setup_kev.sh or set KEV_REPO_DIR to an installed Kev checkout")
url = urlsplit(os.environ.get("KEV_URL") or values.get("KEV_URL") or "http://127.0.0.1:8009")
if url.scheme != "http" or url.hostname not in {"127.0.0.1", "localhost", "::1"}:
    raise SystemExit("KEV_URL must be local loopback HTTP")
run = os.environ.get("KEV_RUN") or values.get("KEV_RUN") or "jaredpalmer/kev-4b"
os.chdir(repo)
os.execv(
    str(python),
    [str(python), "-m", "kev.serve", "--run", run, "--host", url.hostname, "--port", str(url.port or 80)],
)
