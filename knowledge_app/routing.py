"""Local Kev scoring for memory decisions; never executes a search or write."""

import math
import time
from pathlib import Path
from typing import Any, Literal, Protocol

import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Operation = Literal["lookup", "save", "graph_lookup", "graph_extract"]
ROOT = Path(__file__).resolve().parents[1]
LOOKUP_QUESTION = "이 요청에 제대로 답하려면 사용자가 과거에 저장한 결정, 선호, 프로젝트 관례, 이전 문제 해결 기록을 조회하는 것이 도움이 되는가?"
SAVE_QUESTION = "이 내용은 향후 다른 작업이나 대화에서도 재사용할 가치가 있는, 확정된 사용자 선호, 합의된 결정, 안정적인 프로젝트 사실 또는 검증된 문제 해결 방법인가? 일시적인 진행 상태, 인사, 단순 질문, 추측, 일반 상식은 저장할 가치가 낮다."


class RoutingSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore", env_prefix="KEV_")
    provider: Literal["kev"] = "kev"
    allow_remote: bool = False
    api_key: SecretStr = SecretStr("")
    url: str = "http://127.0.0.1:8009"
    model: str = "kev-latest"
    timeout_seconds: float = Field(default=2.0, ge=0.1, le=10)
    graph_lookup_threshold: float = Field(default=0.4, ge=0, le=1)
    graph_extract_threshold: float = Field(default=0.6, ge=0, le=1)
    graph_review_threshold: float = Field(default=0.2, ge=0, le=1)
    lookup_threshold: float = Field(default=0.2, ge=0, le=1)
    save_threshold: float = Field(default=0.7, ge=0, le=1)
    save_skip_threshold: float = Field(default=0.25, ge=0, le=1)

    @model_validator(mode="after")
    def ordered_thresholds(self) -> "RoutingSettings":
        from knowledge_app.provider_http import endpoint

        self.url = endpoint(self.url, allow_remote=self.allow_remote)
        if self.graph_review_threshold > min(self.graph_lookup_threshold, self.graph_extract_threshold):
            raise ValueError("Graph review threshold must not exceed action thresholds")
        if self.save_skip_threshold > self.save_threshold:
            raise ValueError("Save skip threshold must not exceed save threshold")
        return self


class MemoryDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: Operation
    text: str = Field(min_length=1, max_length=6000)
    context: str = Field(default="", max_length=2000)
    explicit_request: bool = False
    storage_allowed: bool = True
    contains_sensitive: bool = False
    verified: bool = False

    @field_validator("text")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Decision text must not be blank")
        return value.strip()


class DecisionProvider(Protocol):
    async def score(self, state: Any, questions: dict[str, str]) -> dict[str, float]: ...


class KevDecisionProvider:
    def __init__(self, settings: RoutingSettings, transport: httpx.AsyncBaseTransport | None = None):
        self.settings, self.transport = settings, transport

    async def score(self, state: Any, questions: dict[str, str]) -> dict[str, float]:
        key = self.settings.api_key.get_secret_value()
        async with httpx.AsyncClient(
            timeout=self.settings.timeout_seconds,
            trust_env=False,
            follow_redirects=False,
            transport=self.transport,
        ) as client:
            response = await client.post(
                self.settings.url + "/v1/systemone",
                headers={"Authorization": "Bearer " + key} if key else {},
                json={
                    "state": state,
                    "model": self.settings.model,
                    "questions": {k: {"type": "noul", "instructions": v} for k, v in questions.items()},
                },
            )
        response.raise_for_status()
        body = response.json()
        if body.get("truncated"):
            raise ValueError("Truncated routing input")
        scores: dict[str, float] = {}
        for k in questions:
            answer = body["answers"][k]
            value = answer["noul"]
            if (
                answer.get("type") != "noul"
                or isinstance(value, bool)
                or not isinstance(value, (float, int))
                or not math.isfinite(value)
                or not 0 <= value <= 1
            ):
                raise ValueError("Invalid routing score")
            scores[k] = float(value)
        return scores


class MemoryRouter:
    def __init__(
        self,
        settings: RoutingSettings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        provider: DecisionProvider | None = None,
    ) -> None:
        self.settings, self.transport = settings, transport
        self.provider = provider or KevDecisionProvider(settings, transport)

    async def decide(self, request: MemoryDecision) -> dict[str, Any]:
        def result(action: str, reason: str, **extra: Any) -> dict[str, Any]:
            return dict(
                operation=request.operation, action=action, reason=reason, model_called=False, **extra
            )

        if request.contains_sensitive:
            return result(
                "skip" if request.operation in {"save", "graph_extract"} else "agent_review",
                "sensitive_input_not_sent",
            )
        if request.operation in {"save", "graph_extract"} and not request.storage_allowed:
            return result("skip", "storage_opt_out")
        if request.explicit_request:
            return result(request.operation, "explicit_request")
        if request.operation in {"save", "graph_extract"} and not request.verified:
            return result("skip", "unverified_candidate")
        key, question = {
            "lookup": ("need_lookup", LOOKUP_QUESTION),
            "save": ("worth_saving", SAVE_QUESTION),
            "graph_lookup": (
                "need_workflow",
                "이 질문은 저장된 업무 절차의 단계 순서, 분기 조건, 담당 역할, 선행 조건 또는 의존 관계를 알아야 답할 수 있는가? 일반 개념 설명이나 단순 메모 검색은 제외한다.",
            ),
            "graph_extract": (
                "has_workflow",
                "이 확정된 원문에 프로젝트·서비스·머신·자원 간 사용, 배포, 의존 관계나 작업 순서, 장애의 영향 대상, 조치의 대응 대상이 명시적으로 기술되어 있는가? 단순 주제 나열이나 추측은 제외한다.",
            ),
        }[request.operation]
        state = request.text if not request.context else {"text": request.text, "context": request.context}
        started = time.perf_counter()
        try:
            score = (await self.provider.score(state, {key: question}))[key]
        except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError):
            return result(
                "agent_review",
                "kev_unavailable_or_invalid",
                latency_ms=round((time.perf_counter() - started) * 1000, 1),
            )
        threshold = {
            "lookup": self.settings.lookup_threshold,
            "save": self.settings.save_threshold,
            "graph_lookup": self.settings.graph_lookup_threshold,
            "graph_extract": self.settings.graph_extract_threshold,
        }[request.operation]
        action: str
        if score >= threshold:
            action = request.operation
        elif request.operation.startswith("graph_") and score >= self.settings.graph_review_threshold:
            action = "agent_review"
        elif request.operation == "save" and score >= self.settings.save_skip_threshold:
            action = "agent_review"
        else:
            action = "skip"
        return dict(
            operation=request.operation,
            action=action,
            reason="kev_score",
            model_called=True,
            model=self.settings.model,
            score=float(score),
            threshold=threshold,
            save_skip_threshold=self.settings.save_skip_threshold if request.operation == "save" else None,
            graph_review_threshold=self.settings.graph_review_threshold
            if request.operation.startswith("graph_")
            else None,
            latency_ms=round((time.perf_counter() - started) * 1000, 1),
            prompt_version="workflow-routing-v1"
            if request.operation.startswith("graph_")
            else "memory-routing-v1",
        )
