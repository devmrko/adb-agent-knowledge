"""Read-only synthetic context-routing evaluation against configured Kev; no knowledge writes."""

import argparse
import asyncio
import json
from pathlib import Path

from knowledge_app.routing import MemoryDecision, MemoryRouter, RoutingSettings

CASES = [
    (
        "이 중에서 끝나지 않은 항목을 이어서 부탁드립니다.",
        "user: Oracle v3 설치를 검증해줘. assistant: 이력과 새 계정 검증이 남았습니다.",
        True,
    ),
    (
        "What still needs testing?",
        "user: Validate the Oracle memory deployment. assistant: New-schema setup is pending.",
        True,
    ),
    (
        "그 방식이면 신규 입사자는 언제 제출해야 하죠?",
        "user: HR 온보딩 절차를 정리해줘. assistant: 복지 선택과 제출 기한을 확인해야 합니다.",
        True,
    ),
    (
        "지난번 카페 원두 구매 기록을 찾아줘",
        "user: Oracle v3 설치를 검증해줘. assistant: 스키마 검증 중입니다.",
        False,
    ),
    (
        "다른 주제로 넘어가서 HTTP 캐시를 설명해줘",
        "user: HR 온보딩 절차를 정리해줘. assistant: 복지 제출 기록을 확인했습니다.",
        False,
    ),
    (
        "이제 Cafesto 배포 환경을 찾아줘",
        "user: Oracle v3 설치를 검증해줘. assistant: 새 스키마 검증이 남았습니다.",
        False,
    ),
    (
        "두 번째 것으로 하되 기존 조건을 그대로 유지해 주세요.",
        "user: 배포 방식을 비교해줘. assistant: 첫째 수동 배포, 둘째 승인 후 자동 배포입니다.",
        True,
    ),
    (
        "Show my saved espresso recipe.",
        "user: Validate Oracle memory. assistant: Migration validation is pending.",
        False,
    ),
    (
        "이제 그건 취소하고 새 프로젝트의 테스트 계획을 세워줘",
        "user: 기존 사이트 배포해줘. assistant: 기존 사이트 배포를 준비했습니다.",
        False,
    ),
    ("그것과 반대인 경우는요?", "", None),
]


async def evaluate():
    router = MemoryRouter(RoutingSettings())
    rows = []
    for prompt, context, expected in CASES:
        result = await router.decide(
            MemoryDecision(operation="lookup", text=prompt, context=context, resolve_context=True)
        )
        rows.append({"prompt": prompt, "context": context, "expected_context": expected, **result})
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = asyncio.run(evaluate())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                "cases": len(rows),
                "review": sum(r["retrieval_query"] is None for r in rows),
                "wrong_context": sum(
                    r["retrieval_query"] is not None and r["context_used"] != r["expected_context"]
                    for r in rows
                ),
            }
        )
    )


if __name__ == "__main__":
    main()
