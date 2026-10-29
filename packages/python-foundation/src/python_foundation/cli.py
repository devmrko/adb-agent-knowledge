"""Small project generator. Generated applications consume a versioned wheel."""

import argparse
import keyword
import re
from importlib.resources import files
from pathlib import Path


def generate(destination: Path, package: str, database: str, auth: str) -> None:
    if not re.fullmatch(r"[a-z][a-z0-9_]*", package) or keyword.iskeyword(package):
        raise ValueError("Use a lowercase Python package identifier")
    if not re.fullmatch(r"[a-z][a-z0-9-]*", destination.name):
        raise ValueError("Destination name must be a lowercase project name")
    if database not in {"sqlite", "oracle"} or auth not in {"session", "token", "mixed"}:
        raise ValueError("Unsupported database or authentication mode")
    source = files("python_foundation").joinpath("templates/app.py.tpl").read_text()
    source = source.replace("__AUTH__", auth).replace("__APP_NAME__", destination.name)
    source = source.replace(
        "__DATABASE_FIELD__", "database_url: SecretStr = Field(...)" if database == "oracle" else ""
    )
    dependency = "devmrko-python-foundation" + ("[oracle]" if database == "oracle" else "")
    contents = {
        "pyproject.toml": f'''[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "{destination.name}"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["{dependency}==0.1.0"]

[tool.hatch.build.targets.wheel]
packages = ["src/{package}"]
''',
        f"src/{package}/__init__.py": "",
        f"src/{package}/app.py": source,
        ".gitignore": ".venv/\n.env\n*.db\n__pycache__/\ndist/\n",
        "README.md": f"""# {destination.name}

Python 3.12+. Install the pinned Foundation wheel or configure a private package repository before uv sync.
PyPI publication is not configured by the generator.

uv sync
uv run uvicorn {package}.app:create_app --factory --host 127.0.0.1 --port 8000

Database: {database}. Authentication: {auth}.
For Oracle, set FOUNDATION_DATABASE_URL to an oracle+oracledb SQLAlchemy URL.
For session/mixed, set FOUNDATION_DEVELOPMENT_PASSWORD (12+ characters); username is user.
GET /login gives a CSRF token and cookie. POST /login with form username/password/csrf rotates the session.
Use the returned csrf in X-CSRF-TOKEN for session mutation requests. POST /logout accepts the csrf form field.
For token/mixed, set FOUNDATION_ISSUER, FOUNDATION_AUDIENCE and FOUNDATION_JWKS_URL.
Access tokens must be RS256, typ=at+jwt, with issuer/audience/subject/expiration validation.
Mixed /api/** accepts Bearer only. A session is never an alternative on those paths.

/api/ping is authenticated. /actuator/health checks the DB connection.
No application tables are created. Add application-owned models, repositories and Alembic migrations.
Production requires a real user authenticator and a shared SessionStore for session modes.
The example memory store is single-process only. Never commit real secrets.
""",
    }
    destination.mkdir(parents=True, exist_ok=False)
    for relative, content in contents.items():
        path = destination / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--package", required=True)
    parser.add_argument("--database", choices=["sqlite", "oracle"], default="sqlite")
    parser.add_argument("--auth", choices=["session", "token", "mixed"], default="session")
    args = parser.parse_args()
    try:
        generate(args.destination, args.package, args.database, args.auth)
    except (ValueError, FileExistsError) as failure:
        parser.error(str(failure))
    print(f"Created {args.destination}; read README.md for authentication and dependency setup.")
