"""Create a private .env template without replacing an existing configuration."""

import secrets
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def initialize(root: Path) -> bool:
    target = root / ".env"
    text = (
        (root / ".env.example")
        .read_text()
        .replace("DEV_API_TOKEN=\n", "DEV_API_TOKEN=" + secrets.token_urlsafe(32) + "\n")
        .replace("KNOWLEDGE_MACHINE_ID=\n", "KNOWLEDGE_MACHINE_ID=" + str(uuid.uuid4()) + "\n")
    )
    try:
        with target.open("x") as stream:
            target.chmod(0o600)
            stream.write(text)
    except FileExistsError:
        return False
    return True


if __name__ == "__main__":
    print(
        "Created .env (mode 600). Fill Oracle credentials and Wallet path."
        if initialize(ROOT)
        else "Existing .env preserved."
    )
