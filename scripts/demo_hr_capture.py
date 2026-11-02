"""Public HR reference -> persistent clarification, in an isolated SQLite test DB.

Uses the real configured local embedding model; no listening server or production DB.
The extraction draft is agent-authored, not an automated extraction benchmark.
"""

import argparse
import json
import os
import secrets
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from pydantic import SecretStr

from knowledge_app.app import create_app
from knowledge_app.models import Base
from knowledge_app.settings import Settings

URL = "https://www.aphis.usda.gov/careers/new-employee/supervisor"
SCOPE = "project:hr-onboarding-demo"
TEXT = """[테스트용 HR 초안 / 외부 가이드의 한국어 발췌 요약]
출처: USDA APHIS, New Employee Onboarding: Supervisor Resources.
원본 표시 수정일: 2026-03-16. 확인일: 2026-11-02.
원문 전체 복제나 공식 번역이 아니며 우리 조직의 확정 규정이 아니다.
입사 전에는 첫 출근 준비 사항을 안내한다.
첫날에는 팀 소개, 오리엔테이션, 서류 처리와 필요한 IT 자원 요청을 진행한다.
첫 주에는 업무를 배정하고 버디를 소개한다.
첫 달에는 성과 기대치를 정하고 개인 개발 계획과 교육을 지원한다.
출입 관리는 AAMD가 Lenel Application을 통해 수행하며 관련 문의는 Facility Manager에게 한다.
원문 짧은 인용: Request any IT resources/networks required for work
우리 조직에서 이 절차를 채택할지, 실제 담당자와 완료 기록 위치는 이 외부 자료로 확인할 수 없다.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default=".run/hr-onboarding-demo")
    parser.add_argument("--answers-file", help="Explicit test-user answers keyed by adoption/ownership")
    args = parser.parse_args()
    directory = Path(args.output_dir).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    os.chmod(directory, 0o700)
    token = secrets.token_urlsafe(24)
    settings = Settings(
        _env_file=None,
        database_url="sqlite:///" + str(directory / "knowledge.db"),
        environment="development",
        dev_api_token=SecretStr(token),
        dev_web_origin="",
        workflow_rdf_enabled=True,
        embedding_provider="local",
        embedding_device="cpu",
        embedding_model="dragonkue/snowflake-arctic-embed-l-v2.0-ko",
        embedding_revision="55ec6e9358a56d56af759bc8372e970caf8c305f",
    )
    app = create_app(settings)
    Base.metadata.create_all(app.state.engine)
    run = uuid4().hex
    checks = []
    with TestClient(app) as client:
        client.headers["Authorization"] = "Bearer " + token

        def call(method, path, body=None):
            response = (
                client.request(method, path, json=body) if body is not None else client.request(method, path)
            )
            if not response.is_success:
                raise RuntimeError(f"Demo request failed: {method} {path}: HTTP {response.status_code}")
            return response.json()

        saved = call(
            "POST",
            "/api/v1/knowledge",
            {
                "title": "[HR 테스트 초안] 신입사원 온보딩 — USDA 참고",
                "text": TEXT,
                "scope": SCOPE,
                "category": "HR 초안",
                "memory_kind": "DOCUMENT",
                "idempotency_key": "hr-demo-" + run,
                "sources": [
                    {
                        "kind": "url",
                        "location": URL,
                        "locator": "Onboarding Timeline; Facility Access",
                        "version": "page modified 2026-03-16; accessed 2026-11-02",
                    }
                ],
            },
        )
        assert app.state.service.process_one()
        assert call("GET", "/api/v1/jobs/" + saved["job_id"])["status"] == "READY"
        checks.append("real_local_embedding_ready")
        kid, rid = saved["knowledge_id"], saved["revision_id"]
        base = f"/api/v1/graph/reviews/{kid}"
        call(
            "POST",
            base + "/capture",
            {
                "revision_id": rid,
                "expected_version": 0,
                "summary": "신입사원 온보딩 단계와 지원 업무를 외부 가이드에서 수집한 초안. 회사별 적용·담당·기록 위치 확인 필요.",
                "hypotheses": ["우리 회사도 같은 순서와 지원 체계를 사용할 수 있으나 아직 확인되지 않았다."],
                "questions": [
                    {
                        "key": "adoption",
                        "question": "참고자료로만 유지할까요, 테스트용 회사 초안으로 채택할까요?",
                        "reason": "외부 가이드를 내부 확정 규정으로 오인하지 않기 위해",
                        "quote": "우리 조직의 확정 규정이 아니다.",
                        "options": ["외부 참고자료", "테스트용 초안"],
                    },
                    {
                        "key": "ownership",
                        "question": "온보딩 담당자와 완료 기록 위치는 어디인가요?",
                        "reason": "실제 운영 주체와 관리 위치를 임의로 만들지 않기 위해",
                        "quote": "실제 담당자와 완료 기록 위치는 이 외부 자료로 확인할 수 없다.",
                        "options": ["미정"],
                    },
                ],
            },
        )
        if args.answers_file:
            answers = json.loads(Path(args.answers_file).read_text())
            for key, answer in answers.items():
                current = call("GET", base + "/capture")
                call(
                    "POST",
                    base + "/capture/answers",
                    {
                        "revision_id": rid,
                        "expected_version": current["review"]["version"],
                        "question_key": key,
                        "text": answer["text"],
                        "disposition": answer["disposition"],
                    },
                )
        dialog = call("GET", base + "/capture")
        checks.append("dialog_reloaded_from_database")
        assert dialog["capture"]["classification"] == "UNVERIFIED_DRAFT"
        if dialog["capture"]["pending_question_keys"]:
            response = client.post(
                base,
                json={
                    "revision_id": rid,
                    "expected_version": dialog["review"]["version"],
                    "status": "COMPLETE",
                    "outcome": "NONE",
                    "note": "Attempt completion with unresolved question",
                },
            )
            assert response.status_code == 409
            checks.append("unresolved_question_blocks_completion")
        ids = {}
        for key, label in [
            ("day", "입사 첫날 업무"),
            ("week", "입사 첫 주 업무"),
            ("month", "입사 첫 달 업무"),
        ]:
            ids[key] = call(
                "POST",
                "/api/v1/graph/entities",
                {
                    "scope": SCOPE,
                    "identity_key": "hr-demo:" + run + ":" + key,
                    "label": label,
                    "kind": "task",
                },
            )["id"]
        quote = "첫날에는 팀 소개, 오리엔테이션, 서류 처리와 필요한 IT 자원 요청을 진행한다.\n첫 주에는 업무를 배정하고 버디를 소개한다.\n첫 달에는 성과 기대치를 정하고 개인 개발 계획과 교육을 지원한다."
        for subject, target in [("day", "week"), ("week", "month")]:
            call(
                "POST",
                "/api/v1/graph/assertions",
                {
                    "scope": SCOPE,
                    "subject_id": ids[subject],
                    "predicate": "precedes",
                    "object_id": ids[target],
                    "condition": "외부 가이드의 업무 단계 순서. 테스트용 초안이며 실제 수행·내부 승인 사실이 아님.",
                    "verified": True,
                    "evidence": [{"knowledge_id": kid, "revision_id": rid, "quote": quote}],
                },
            )
        graph = call("POST", "/api/v1/graph/search", {"knowledge_id": kid, "scopes": [SCOPE], "depth": 1})
        assert len(graph["edges"]) == 2
        checks.append("two_source_backed_stage_relations")
        search = call(
            "POST",
            "/api/v1/knowledge/search",
            {"query": "입사 초기에 동료가 적응을 도와주는 업무", "scopes": [SCOPE]},
        )
        assert any(row["knowledge_id"] == kid for row in search["items"])
        checks.append("korean_vector_search_returns_hr_source")
        report = {
            "source_url": URL,
            "source_is": "agent-authored Korean excerpt summary, not full manual",
            "storage": "isolated SQLite test DB; not Oracle or production MCP",
            "embedding": settings.embedding_model,
            "model_device": "cpu",
            "extraction": "authored by conversational agent; not measured automatic extractor",
            "kev": "not exercised in this demo",
            "knowledge_id": kid,
            "revision_id": rid,
            "scope": SCOPE,
            "source_status": "READY",
            "capture": dialog["capture"],
            "relations": graph["edges"],
            "search_result_count": len(search["items"]),
            "checks_passed": checks,
        }
        (directory / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print(
            json.dumps(
                {
                    "report": str(directory / "report.json"),
                    "knowledge_id": kid,
                    "checks_passed": checks,
                    "pending": dialog["capture"]["pending_question_keys"],
                },
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    main()
