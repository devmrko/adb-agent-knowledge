"""Kev routes retrieval; deterministic catalog access remains available independently."""

import asyncio
from typing import Any, Literal
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator

from knowledge_app.contracts import Search, normalize_scope
from knowledge_app.graph_contracts import GraphSearch, GraphSeed
from knowledge_app.graph_service import GraphService
from knowledge_app.indexes import IndexService
from knowledge_app.routing import MemoryDecision, MemoryRouter
from knowledge_app.service import KnowledgeService
from python_foundation.errors import BusinessError
from python_foundation.security import Actor


class NavigationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=6000)
    scopes: list[str] | None = Field(default=None, min_length=1, max_length=10)
    context: str = Field(default="", max_length=1000)
    graph_mode: Literal["auto", "always", "never"] = "auto"
    mode: Literal["auto", "direct", "index", "both"] = "auto"
    index_ids: list[UUID] = Field(default_factory=list, max_length=3)
    catalog_offset: int = Field(default=0, ge=0, le=1000000)
    top_k: int = Field(default=5, ge=1, le=10)
    explicit_request: bool = False
    verified: bool = False
    storage_allowed: bool = True
    contains_sensitive: bool = False

    @field_validator("text")
    @classmethod
    def nonblank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Blank request")
        return v.strip()

    @field_validator("scopes")
    @classmethod
    def valid_scopes(cls, v: list[str] | None) -> list[str] | None:
        return None if v is None else list(dict.fromkeys(normalize_scope(s) for s in v))


class NavigationService:
    def __init__(
        self, knowledge: KnowledgeService, indexes: IndexService, graph: GraphService, router: MemoryRouter
    ):
        self.knowledge, self.indexes, self.graph, self.router = knowledge, indexes, graph, router

    async def plan(
        self, command: NavigationRequest, catalog: dict[str, Any], operation: str
    ) -> dict[str, Any]:
        if command.contains_sensitive:
            return {
                "route": "agent_review",
                "reason": "sensitive_input_not_sent",
                "model_called": False,
                "index_ids": [],
            }
        if operation == "save" and (not command.storage_allowed or not command.verified):
            return {
                "route": "skip",
                "reason": "storage_opt_out_or_unverified",
                "model_called": False,
                "index_ids": [],
            }
        if operation == "lookup" and (command.mode != "auto" or command.index_ids):
            return {
                "route": command.mode if command.mode != "auto" else "index",
                "reason": "explicit_path",
                "model_called": False,
                "index_ids": [str(i) for i in command.index_ids],
                "graph": False,
            }
        questions = {
            "direct": "이 요청에는 구체적인 사실이나 문서를 직접 검색하는 것이 유용한가?",
            "index": "이 요청에는 프로젝트나 주제의 전체 구성, 관련 지식 목록 또는 저장할 지식의 분류를 인덱스에서 확인하는 것이 유용한가?",
            "graph": "이 요청에 답하려면 여러 프로젝트나 업무 단계 사이의 의존, 연결, 순서 관계를 확인해야 하는가?",
            "revise": "이 저장 후보는 기존 지식을 보완하거나 정정할 가능성이 있어 정확한 기존 원문과 이력 확인이 필요한가? 이름만 같다는 것은 동일성의 근거가 아니다.",
        }
        for n, _index in enumerate(catalog["items"]):
            questions[f"i{n}"] = (
                f"이 요청을 조회하거나 이 지식을 분류할 때 인덱스 {n}의 수록 범위가 관련 있는가?"
            )
        state = {
            "request": command.text,
            "context": command.context,
            "operation": operation,
            "catalog": [
                {"n": n, "title": i["title"], "scope": i["scope"], "description": i["summary"][:300]}
                for n, i in enumerate(catalog["items"])
            ],
        }
        try:
            scores = await self.router.provider.score(state, questions)
        except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError):
            return {
                "route": "agent_review",
                "reason": "kev_unavailable_or_invalid",
                "model_called": False,
                "index_ids": [i["id"] for i in catalog["items"][:2]],
                "graph": False,
            }
        direct, index = scores["direct"] >= 0.3, scores["index"] >= 0.3
        route = "both" if direct and index else "direct" if direct else "index" if index else "agent_review"
        ranked = sorted([(scores[f"i{n}"], i["id"]) for n, i in enumerate(catalog["items"])], reverse=True)
        selected = [i for score, i in ranked if score >= 0.3][:2]
        if index and not selected:
            route = "agent_review"
        return {
            "route": route,
            "reason": "kev_navigation_scores",
            "model_called": True,
            "scores": scores,
            "index_ids": selected,
            "graph": scores["graph"] >= 0.4,
            "revision_candidate": scores["revise"] >= 0.4,
            "prompt_version": "index-navigation-v1",
            "thresholds_provisional": True,
        }

    async def execute(
        self, actor: Actor, command: NavigationRequest, *, save: bool = False
    ) -> dict[str, Any]:
        operation = "save" if save else "lookup"
        if command.contains_sensitive or (save and (not command.storage_allowed or not command.verified)):
            return {
                "plan": await self.plan(command, {"items": []}, operation),
                "items": [],
                "indexes": [],
                "writes_performed": False,
            }
        if save:
            worth = await self.router.decide(
                MemoryDecision(
                    operation="save",
                    text=command.text,
                    context=command.context,
                    verified=command.verified,
                    explicit_request=command.explicit_request,
                    storage_allowed=command.storage_allowed,
                )
            )
            if worth["action"] == "skip":
                return {
                    "plan": {"route": "skip", "reason": worth["reason"]},
                    "items": [],
                    "indexes": [],
                    "writes_performed": False,
                }
        catalog = await asyncio.to_thread(
            self.indexes.catalog, actor, command.scopes, "", command.catalog_offset, 20
        )
        plan = await self.plan(command, catalog, operation)
        route = plan["route"]
        selected = plan.get("index_ids", [])
        if command.index_ids:
            selected = [str(i) for i in command.index_ids]
        result: dict[str, Any] = {
            "plan": plan,
            "catalog": catalog,
            "items": [],
            "indexes": [],
            "writes_performed": False,
            "fallbacks": [],
        }
        # A failed/uncertain classifier never closes the only retrieval path.
        direct = save or route in {"direct", "both", "agent_review"}
        browse = route in {"index", "both", "agent_review"} or save
        if browse:
            for index_id in selected[:3]:
                try:
                    doc = await asyncio.to_thread(self.indexes.get, actor, index_id)
                    page = await asyncio.to_thread(
                        self.indexes.entries, actor, index_id, command.scopes, 0, 8
                    )
                    result["indexes"].append({"index": {k: v for k, v in doc.items() if k != "body"}, **page})
                except BusinessError:
                    if command.index_ids:
                        raise
                    result["fallbacks"].append("index_changed_or_unavailable")
            if not any(i["items"] for i in result["indexes"]):
                direct = True
                result["fallbacks"].append("index_empty_use_direct")
        if direct:
            data = await asyncio.to_thread(
                self.knowledge.search,
                actor,
                Search(query=command.text[:2000], scopes=command.scopes, top_k=command.top_k),
            )
            result["items"] = [
                {k: v for k, v in item.items() if k not in {"matches"}} for item in data["items"]
            ]
            if not result["items"] and not result["indexes"]:
                result["fallbacks"].append("direct_empty_browse_catalog")
                # Return the catalog even without a model-selected index; the caller can page it deterministically.
                for index in catalog["items"][:2]:
                    page = await asyncio.to_thread(
                        self.indexes.entries, actor, index["id"], command.scopes, 0, 8
                    )
                    result["indexes"].append({"index": index, **page})
        if (
            (command.graph_mode == "always" or (command.graph_mode == "auto" and plan.get("graph")))
            and not save
            and not command.contains_sensitive
        ):
            seeds = [
                GraphSeed(knowledge_id=i["knowledge_id"], revision_id=i["revision_id"])
                for i in result["items"][:3]
            ]
            try:
                result["graph"] = await asyncio.to_thread(
                    self.graph.search,
                    actor,
                    GraphSearch(
                        query=command.text[:2000],
                        include_entity_matches=True,
                        seed_revisions=seeds,
                        scopes=command.scopes,
                        max_edges=20,
                    ),
                )
            except BusinessError:
                result["graph"] = {"status": "UNAVAILABLE"}
        result["navigation_complete"] = False  # A bounded preview is never an exhaustive proof of absence.
        result["next_step"] = (
            "Read exact content/history before save/revise; after READY link verified memberships. Do not merge from routing scores."
            if save
            else "Read exact revision content before answering; page catalog/index entries when coverage is insufficient."
        )
        # Summary previews have a total character budget; stable IDs and paging remain available.
        remaining = 6000
        cards = result["items"] + [entry for index in result["indexes"] for entry in index["items"]]
        for card in cards:
            value = card.get("summary", "")
            size = min(len(value), remaining, 800)
            card["summary"] = value[:size]
            card["summary_truncated"] = size < len(value)
            remaining -= size
        return result
