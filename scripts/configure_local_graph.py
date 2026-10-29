"""Apply the local Gemma profile without printing or replacing unrelated secrets."""

import argparse
from pathlib import Path

from dotenv import dotenv_values, set_key

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Update only local graph/RDF settings in .env")
    args = parser.parse_args()
    values = dotenv_values(ROOT / "config/gemma-local.env")
    if not args.apply:
        print("Local Gemma profile: loopback Ollama, no API key, review candidates only, RDF enabled.")
        print("After preparing RDF and Ollama, use --apply. Existing DB credentials are preserved.")
        return
    target = ROOT / ".env"
    if not target.is_file():
        raise SystemExit("Run scripts/setup.sh first")
    for key, value in values.items():
        if value is not None:
            set_key(str(target), key, value, quote_mode="always")
    target.chmod(0o600)
    print("Local Gemma profile applied. Restart API/MCP/workers after the smoke check succeeds.")


if __name__ == "__main__":
    main()
