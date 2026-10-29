"""Run the same CRUD HTTP contract against Python or Java, using isolated test data."""

import argparse
import os
import re
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
from project_contract import verify_project_contract  # noqa: E402


def authenticate(client, mode, username, password):
    if mode == "basic":
        client.auth = httpx.BasicAuth(username, password)
    elif mode == "form":
        page = client.get("/login")
        csrf = re.search(r'name="csrf" value="([^"]+)"', page.text).group(1)
        response = client.post("/login", data={"username": username, "password": password, "csrf": csrf})
        assert response.status_code in {302, 303}, response.status_code
    else:
        client.headers["Authorization"] = "Bearer " + os.environ["CONTRACT_ACCESS_TOKEN"]
        return
    page = client.get("/projects")
    csrf = re.search(r'name="_csrf" content="([^"]+)"', page.text).group(1)
    header = re.search(r'name="_csrf_header" content="([^"]+)"', page.text).group(1)
    client.headers[header] = csrf


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--auth", choices=["form", "basic", "bearer"], default="form")
    args = parser.parse_args()
    with httpx.Client(base_url=args.base_url, timeout=10, follow_redirects=False) as client:
        authenticate(
            client,
            args.auth,
            os.environ.get("CONTRACT_USERNAME", "user"),
            os.environ.get("CONTRACT_PASSWORD", ""),
        )
        verify_project_contract(client)
    print("PASS shared Project HTTP contract")


if __name__ == "__main__":
    main()
