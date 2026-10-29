"""Live smoke: creates one clearly labelled development document; never logs tokens."""

import argparse
import time

import httpx

from knowledge_app.settings import Settings

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--url", default="http://127.0.0.1:8000")
args = parser.parse_args()
settings = Settings()
assert settings.dev_api_token is not None
with httpx.Client(
    base_url=args.url,
    timeout=120,
    headers={"Authorization": "Bearer " + settings.dev_api_token.get_secret_value()},
) as client:
    response = client.post(
        "/api/v1/knowledge",
        json={
            "title": "[개발 검증] Oracle 접속 오류 해결",
            "knowledge_type": "TROUBLESHOOTING",
            "category": "Oracle",
            "tags": ["Wallet", "접속"],
            "text": "Autonomous Database 접속 시 ORA-01017 오류는 DB 사용자명과 비밀번호를 확인합니다. Wallet 암호는 DB 비밀번호와 별개입니다. 접속 별칭은 tnsnames.ora에서 확인합니다.",
        },
    )
    response.raise_for_status()
    ids = response.json()
    print("Registered:", ids, flush=True)
    for _ in range(90):
        response = client.get("/api/v1/jobs/" + ids["job_id"])
        response.raise_for_status()
        job = response.json()
        if job["status"] in {"READY", "FAILED"}:
            break
        time.sleep(2)
    assert job["status"] == "READY", job
    response = client.post(
        "/api/v1/knowledge/search",
        json={"query": "데이터베이스에 로그인할 때 암호가 잘못됐다고 나와요", "category": "Oracle"},
    )
    response.raise_for_status()
    found = response.json()["items"]
    assert any(i["knowledge_id"] == ids["knowledge_id"] for i in found), found
    match = next(i for i in found if i["knowledge_id"] == ids["knowledge_id"])
    response = client.get(match["content_uri"])
    response.raise_for_status()
    assert "ORA-01017" in response.json()["text"]
    print("PASS: real HTTP -> Oracle job -> CPU embedding -> Oracle vector search -> source text", flush=True)
