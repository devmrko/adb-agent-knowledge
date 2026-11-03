import asyncio
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.parse import quote

from fastapi import Depends, FastAPI, File, Form, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import ValidationError
from sqlalchemy import text

from knowledge_app.agent_memory_contracts import MemoryQuery, MemoryRename, MemorySave, ProfileSave
from knowledge_app.agent_memory_repository import SDKRepository
from knowledge_app.agent_memory_service import AgentMemoryService
from knowledge_app.audit_service import AuditService, ResolveReview
from knowledge_app.browser_session import BrowserSessions, install_browser_sessions
from knowledge_app.capture_contracts import CaptureAnswer, CaptureDraft
from knowledge_app.contracts import (
    ContextRequest,
    CreateKnowledge,
    MemoryKind,
    Provenance,
    RestoreKnowledge,
    RetireKnowledge,
    ReviseKnowledge,
    Search,
    normalize_scope,
)
from knowledge_app.database import database
from knowledge_app.embedding import Embedder, create_embedder
from knowledge_app.extraction import PPTX_MIME
from knowledge_app.graph_auto_contracts import AgentGraphPrepare, ReviewCandidate
from knowledge_app.graph_auto_service import AutoGraphService
from knowledge_app.graph_contracts import (
    AssertionInput,
    AssertionRevision,
    EntityInput,
    GraphSearch,
    GraphSeed,
)
from knowledge_app.graph_ops_contracts import GraphExplore, IdentityBind, IdentityResolve, ReviewUpdate
from knowledge_app.graph_ops_service import GraphOpsService
from knowledge_app.graph_service import GraphService
from knowledge_app.indexes import EntryInput, IndexEdit, IndexInput, IndexService
from knowledge_app.memory_connection_contracts import EvidenceInput, MemoryGraph, MemoryLink
from knowledge_app.memory_connections import MemoryConnections
from knowledge_app.navigation import NavigationRequest, NavigationService
from knowledge_app.principles import PrincipleScopes, PrincipleService, PrincipleWrite
from knowledge_app.routing import MemoryRouter, RoutingSettings
from knowledge_app.service import KnowledgeService, fail
from knowledge_app.settings import Settings
from knowledge_app.source_transfer import SourceTransferService
from knowledge_app.v3_pilot import VersionedMemoryPilot
from knowledge_app.workflow import WorkflowInput
from python_foundation.database import sessions
from python_foundation.errors import AuthenticationRequired, BusinessError
from python_foundation.security import Actor, Security, TokenVerifier, current_actor
from python_foundation.settings import FoundationSettings
from python_foundation.web import install_web

bearer = HTTPBearer(auto_error=False)


def authenticated_actor(
    request: Request, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]
) -> Actor:
    browser: BrowserSessions | None = request.app.state.browser_sessions
    if "authorization" not in request.headers and browser is not None:
        return browser.authenticate(request)
    return current_actor(request)


ActorDep = Annotated[Actor, Depends(authenticated_actor)]


class DevelopmentVerifier:
    def __init__(self, token: str) -> None:
        if len(token) < 24:
            raise ValueError("DEV_API_TOKEN must contain at least 24 characters")
        self.token = token

    def verify(self, token: str) -> Actor:
        if not secrets.compare_digest(token, self.token):
            raise AuthenticationRequired()
        return Actor("local-development", "developer", frozenset())


def create_app(
    settings: Settings | None = None,
    *,
    embedder: Embedder | None = None,
    verifier: TokenVerifier | None = None,
    router: MemoryRouter | None = None,
) -> FastAPI:
    settings = settings or Settings()
    if settings.environment == "development" and verifier is None:
        if settings.dev_api_token is None:
            raise ValueError("Set DEV_API_TOKEN for local development")
        verifier = DevelopmentVerifier(settings.dev_api_token.get_secret_value())
    foundation = FoundationSettings(
        auth_mode="token",
        environment=settings.environment,
        issuer=settings.issuer,
        audience=settings.audience,
        jwks_url=settings.jwks_url,
        max_request_bytes=max(settings.max_source_bytes, settings.max_pptx_source_bytes) + 65536,
    )
    engine = database(settings)
    service = KnowledgeService(sessions(engine), embedder or create_embedder(settings), settings)
    principles = PrincipleService(sessions(engine))
    memory_repo = SDKRepository(settings, service.embedder)
    memories = AgentMemoryService(memory_repo, engine, settings.agent_memory_enabled)
    connections = MemoryConnections(memories, service, sessions(engine))
    graph_service = GraphService(sessions(engine), settings)
    transfer_repo = None
    transfer = None
    if settings.knowledge_source_backend == "v3":
        if settings.knowledge_v3_store_id == settings.agent_memory_store_id:
            raise ValueError("v3 source store must be separate from agent memory store")
        transfer_repo = SDKRepository(
            settings.model_copy(update={"agent_memory_store_id": settings.knowledge_v3_store_id}),
            service.embedder,
        )
        transfer = SourceTransferService(VersionedMemoryPilot(service, transfer_repo, graph_service))
        service.content_reader = transfer.content_owned
        graph_service.source_reader = transfer.content_owned
    graph_ops = GraphOpsService(sessions(engine), settings)
    audit = AuditService(sessions(engine), settings.workflow_rdf_enabled)
    auto_graph = AutoGraphService(sessions(engine), settings)
    indexes = IndexService(sessions(engine), settings.workflow_rdf_enabled)
    navigation = NavigationService(service, indexes, graph_service, router or MemoryRouter(RoutingSettings()))

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            if transfer_repo is not None:
                transfer_repo.close()
            memory_repo.close()
            engine.dispose()

    app = FastAPI(title="Agent Knowledge for Oracle ADB", version="0.2.0", lifespan=lifespan)
    install_web(app, Security(foundation, verifier=verifier))
    install_browser_sessions(app, settings)
    app.state.service, app.state.engine = service, engine
    app.state.source_transfer = transfer
    app.state.auto_graph = auto_graph
    app.state.agent_memory = memories
    app.state.memory_connections = connections

    assets = Path(__file__).parent / "static"
    ui_headers = {
        "Cache-Control": "no-store",
        "Content-Security-Policy": "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'",
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
    }

    @app.get("/", include_in_schema=False)
    def home() -> RedirectResponse:
        return RedirectResponse("/knowledge")

    @app.get("/knowledge", include_in_schema=False)
    def knowledge_page() -> FileResponse:
        return FileResponse(assets / "index.html", headers=ui_headers)

    @app.get("/knowledge-assets/app.js", include_in_schema=False)
    def knowledge_script() -> FileResponse:
        return FileResponse(assets / "app.js", media_type="text/javascript", headers=ui_headers)

    @app.get("/knowledge-assets/common.css", include_in_schema=False)
    def knowledge_common_style() -> FileResponse:
        return FileResponse(assets / "common.css", media_type="text/css", headers=ui_headers)

    @app.get("/knowledge-assets/style.css", include_in_schema=False)
    def knowledge_style() -> FileResponse:
        return FileResponse(assets / "style.css", media_type="text/css", headers=ui_headers)

    @app.post("/knowledge/local-connection", include_in_schema=False)
    def local_connection(request: Request) -> JSONResponse:
        loopback = {"127.0.0.1", "::1", "localhost"}
        origin = f"{request.url.scheme}://{request.url.netloc}"
        allowed = (
            settings.ui_auto_connect
            and not settings.web_public_origin
            and settings.environment == "development"
            and isinstance(verifier, DevelopmentVerifier)
            and settings.api_host in loopback
            and request.client is not None
            and request.client.host in {"127.0.0.1", "::1"}
            and request.url.hostname in loopback
            and request.headers.get("origin") == origin
            and request.headers.get("sec-fetch-site") == "same-origin"
            and request.headers.get("x-knowledge-ui") == "1"
            and settings.dev_api_token is not None
        )
        if not allowed:
            return JSONResponse({"available": False}, status_code=404, headers={"Cache-Control": "no-store"})
        assert settings.dev_api_token is not None
        return JSONResponse(
            {"token": settings.dev_api_token.get_secret_value()}, headers={"Cache-Control": "no-store"}
        )

    @app.get("/actuator/health")
    def health() -> dict[str, str]:
        with engine.connect() as con:
            con.execute(text("SELECT 1 FROM DUAL" if engine.dialect.name == "oracle" else "SELECT 1"))
        return {"status": "UP"}

    @app.get("/api/v1/principles")
    def principle_current(actor: ActorDep) -> dict[str, Any]:
        return principles.current(actor)

    @app.put("/api/v1/principles")
    def principle_replace(command: PrincipleWrite, actor: ActorDep) -> dict[str, Any]:
        return principles.replace(actor, command)

    @app.post("/api/v1/principles/resolve")
    def principle_resolve(command: PrincipleScopes, actor: ActorDep) -> dict[str, Any]:
        return principles.resolve(actor, command)

    @app.get("/api/v1/principles/history")
    def principle_history(
        actor: ActorDep, offset: int = Query(0, ge=0), limit: int = Query(10, ge=1, le=50)
    ) -> dict[str, Any]:
        return principles.history(actor, offset, limit)

    @app.get("/api/v1/agent-memory/profiles")
    def memory_profiles(actor: ActorDep) -> dict[str, Any]:
        return memories.profiles(actor)

    @app.post("/api/v1/agent-memory/profiles")
    def memory_profile_save(command: ProfileSave, actor: ActorDep) -> dict[str, Any]:
        return memories.save_profile(command, actor)

    @app.get("/api/v1/agent-memory/references")
    def memory_references(
        actor: ActorDep,
        memory_id: str | None = None,
        knowledge_id: str | None = None,
        offset: Annotated[int, Query(ge=0, le=100000)] = 0,
        limit: Annotated[int, Query(ge=1, le=50)] = 20,
    ) -> dict[str, Any]:
        return connections.references(
            actor, memory_id=memory_id, knowledge_id=knowledge_id, offset=offset, limit=limit
        )

    @app.get("/api/v1/agent-memory/{memory_id}/prepare-links")
    def memory_prepare_links(memory_id: str, actor: ActorDep) -> dict[str, Any]:
        return connections.prepare(memory_id, actor)

    @app.post("/api/v1/agent-memory/evidence")
    def memory_evidence(command: EvidenceInput, actor: ActorDep) -> dict[str, Any]:
        return connections.link_evidence(command, actor)

    @app.post("/api/v1/agent-memory/links")
    def memory_link(command: MemoryLink, actor: ActorDep) -> dict[str, Any]:
        return connections.link(command, actor)

    @app.post("/api/v1/agent-memory/graph")
    def memory_graph(command: MemoryGraph, actor: ActorDep) -> dict[str, Any]:
        return connections.graph(command, actor)

    @app.post("/api/v1/agent-memory/search")
    def memory_search(command: MemoryQuery, actor: ActorDep) -> dict[str, Any]:
        result = memories.query(command, actor)
        if command.include_connections:
            for item in result["items"][:5]:
                try:
                    item["references"] = connections.references(
                        actor,
                        memory_id=item["memory_id"],
                        limit=5,
                        scopes=[command.scope] if command.scope else None,
                    )
                    item["graph"] = connections.graph(
                        MemoryGraph(
                            memory_id=item["memory_id"],
                            depth=1,
                            max_edges=10,
                            scopes=[command.scope] if command.scope else None,
                        ),
                        actor,
                    )
                except BusinessError:
                    item["connections_status"] = "UNAVAILABLE"
            result["connections_limit"] = 5
        return result

    @app.post("/api/v1/agent-memory/title")
    def memory_rename(command: MemoryRename, actor: ActorDep) -> dict[str, Any]:
        return memories.rename(command, actor)

    @app.post("/api/v1/agent-memory")
    def memory_save(command: MemorySave, actor: ActorDep) -> dict[str, Any]:
        result = memories.save(command, actor)
        result["next_step"] = (
            "Use memory_prepare_links, read exact revisions and conditions, then memory_link_knowledge only for supported claims. Inspect memory_graph before adding memory links."
        )
        return result

    @app.post("/api/v1/knowledge", status_code=202)
    def create(command: CreateKnowledge, actor: ActorDep) -> dict[str, str]:
        return service.create(command, actor)

    @app.post("/api/v1/knowledge/files", status_code=202)
    def upload(
        actor: ActorDep,
        file: Annotated[UploadFile, File()],
        title: Annotated[str, Form(min_length=1, max_length=300)],
        memory_kind: Annotated[MemoryKind, Form()] = "DOCUMENT",
        scope: Annotated[str, Form()] = "global",
        idempotency_key: Annotated[str | None, Form(max_length=100)] = None,
        provenance: Annotated[str, Form(max_length=300000)] = "{}",
    ) -> dict[str, str]:
        limit = (
            settings.max_pptx_source_bytes if file.content_type == PPTX_MIME else settings.max_source_bytes
        )
        data = file.file.read(limit + 1)
        name = (file.filename or "upload").replace("\\", "/").split("/")[-1][:300]
        if not title.strip():
            raise fail("BLANK_TITLE")
        try:
            scope = normalize_scope(scope)
        except ValueError:
            raise fail("INVALID_SCOPE") from None
        try:
            source_metadata = Provenance.model_validate_json(provenance)
        except ValidationError:
            raise fail("INVALID_PROVENANCE") from None
        return service.create(
            CreateKnowledge(
                title=title,
                memory_kind=memory_kind,
                scope=scope,
                idempotency_key=idempotency_key,
                **source_metadata.model_dump(),
            ),
            actor,
            data=data,
            filename=name,
            mime=file.content_type or "application/octet-stream",
        )

    @app.get("/api/v1/graph/extraction/schema")
    def graph_extraction_schema(actor: ActorDep) -> dict[str, Any]:
        return auto_graph.schema()

    @app.post("/api/v1/graph/extraction/knowledge/{item_id}/prepare")
    def graph_agent_prepare(item_id: str, command: AgentGraphPrepare, actor: ActorDep) -> dict[str, Any]:
        return auto_graph.prepare(actor, item_id, command)

    @app.get("/api/v1/graph/extraction/runs")
    def graph_extraction_runs(
        actor: ActorDep,
        knowledge_id: str | None = None,
        offset: Annotated[int, Query(ge=0, le=1000000)] = 0,
        limit: Annotated[int, Query(ge=1, le=100)] = 30,
    ) -> dict[str, Any]:
        return auto_graph.listing(actor, False, knowledge_id, offset, limit)

    @app.post("/api/v1/graph/extraction/knowledge/{item_id}")
    def graph_extraction_enqueue(item_id: str, actor: ActorDep) -> dict[str, Any]:
        return auto_graph.enqueue(actor, item_id)

    @app.post("/api/v1/graph/extraction/runs/{run_id}/retry")
    def graph_extraction_retry(run_id: str, actor: ActorDep) -> dict[str, Any]:
        return auto_graph.retry(actor, run_id)

    @app.get("/api/v1/graph/proposals")
    def graph_proposals(
        actor: ActorDep,
        knowledge_id: str | None = None,
        offset: Annotated[int, Query(ge=0, le=1000000)] = 0,
        limit: Annotated[int, Query(ge=1, le=100)] = 30,
    ) -> dict[str, Any]:
        return auto_graph.listing(actor, True, knowledge_id, offset, limit)

    @app.post("/api/v1/graph/proposals/{proposal_id}/review")
    def graph_proposal_review(proposal_id: str, command: ReviewCandidate, actor: ActorDep) -> dict[str, Any]:
        return auto_graph.review(actor, proposal_id, command)

    @app.get("/api/v1/changes")
    def change_list(
        actor: ActorDep,
        table: Annotated[str | None, Query(max_length=40)] = None,
        target_id: Annotated[str | None, Query(max_length=36)] = None,
        offset: Annotated[int, Query(ge=0, le=1000000)] = 0,
        limit: Annotated[int, Query(ge=1, le=100)] = 30,
    ) -> dict[str, Any]:
        return audit.changes(actor, table=table, target_id=target_id, offset=offset, limit=limit)

    @app.get("/api/v1/changes/{event_id}")
    def change_get(event_id: str, actor: ActorDep) -> dict[str, Any]:
        return audit.get(actor, event_id)

    @app.post("/api/v1/changes/{event_id}/retry")
    def change_retry(event_id: str, actor: ActorDep) -> dict[str, Any]:
        return audit.retry(actor, event_id)

    @app.get("/api/v1/change-reviews")
    def review_list(
        actor: ActorDep,
        status: Literal["OPEN", "RESOLVED"] = "OPEN",
        offset: Annotated[int, Query(ge=0, le=1000000)] = 0,
        limit: Annotated[int, Query(ge=1, le=100)] = 30,
    ) -> dict[str, Any]:
        return audit.reviews(actor, status, offset, limit)

    @app.post("/api/v1/change-reviews/{review_id}/resolve")
    def review_resolve(review_id: str, command: ResolveReview, actor: ActorDep) -> dict[str, Any]:
        return audit.resolve(actor, review_id, command)

    @app.post("/api/v1/knowledge/recall")
    async def recall(command: NavigationRequest, actor: ActorDep) -> dict[str, Any]:
        result = await navigation.execute(actor, command)
        if command.include_agent_memory and settings.agent_memory_enabled and not command.contains_sensitive:
            memory_items: dict[str, Any] = {}
            statuses = []
            memory_scopes: list[str | None] = list(command.scopes) if command.scopes else [None]
            for scope in memory_scopes:
                try:
                    found = await asyncio.to_thread(
                        memory_search,
                        MemoryQuery(
                            query=command.text[:2000],
                            scope=scope,
                            limit=5,
                            include_connections=command.graph_mode == "always"
                            or (command.graph_mode == "auto" and result.get("plan", {}).get("graph", False)),
                        ),
                        actor,
                    )
                    memory_items.update({i["memory_id"]: i for i in found["items"]})
                    statuses.append(
                        {
                            "scope": scope,
                            "status": found["status"],
                            "truncated": found.get("truncated", False),
                        }
                    )
                except BusinessError:
                    statuses.append({"scope": scope, "status": "UNAVAILABLE"})
            result["agent_memories"] = {
                "items": list(memory_items.values()),
                "scopes": statuses,
                "time_filters_applied": False,
                "note": "Separate SDK results; scores are not merged with knowledge.",
            }
        return result

    @app.post("/api/v1/knowledge/prepare-save")
    async def prepare_save(command: NavigationRequest, actor: ActorDep) -> dict[str, Any]:
        return await navigation.execute(actor, command, save=True)

    def index_scopes(scope: str | None) -> list[str] | None:
        if scope is None:
            return None
        try:
            return [normalize_scope(v) for v in scope.split(",")]
        except ValueError:
            raise fail("INVALID_SCOPE") from None

    @app.get("/api/v1/graph/reviews")
    def graph_review_backlog(
        actor: ActorDep,
        scope: str | None = None,
        offset: Annotated[int, Query(ge=0, le=1000000)] = 0,
        limit: Annotated[int, Query(ge=1, le=100)] = 30,
    ) -> dict[str, Any]:
        return graph_ops.backlog(actor, index_scopes(scope), offset, limit)

    @app.post("/api/v1/graph/reviews/{item_id}")
    def graph_review_update(item_id: str, command: ReviewUpdate, actor: ActorDep) -> dict[str, Any]:
        return graph_ops.review(actor, item_id, command)

    @app.get("/api/v1/graph/reviews/{item_id}/capture")
    def capture_get(item_id: str, actor: ActorDep, revision_id: str | None = None) -> dict[str, Any]:
        return graph_ops.capture_get(actor, item_id, revision_id)

    @app.post("/api/v1/graph/reviews/{item_id}/capture")
    def capture_draft(item_id: str, command: CaptureDraft, actor: ActorDep) -> dict[str, Any]:
        return graph_ops.capture_write(actor, item_id, command)

    @app.post("/api/v1/graph/reviews/{item_id}/capture/answers")
    def capture_answer(item_id: str, command: CaptureAnswer, actor: ActorDep) -> dict[str, Any]:
        return graph_ops.capture_write(actor, item_id, command)

    @app.get("/api/v1/graph/entities/{entity_id}/identities")
    def graph_entity_identities(
        entity_id: str,
        actor: ActorDep,
        offset: Annotated[int, Query(ge=0, le=1000000)] = 0,
        limit: Annotated[int, Query(ge=1, le=100)] = 30,
    ) -> dict[str, Any]:
        return graph_ops.bindings(actor, entity_id, offset, limit)

    @app.post("/api/v1/graph/identities/resolve")
    def graph_identity_resolve(command: IdentityResolve, actor: ActorDep) -> dict[str, Any]:
        return graph_ops.resolve(actor, command)

    @app.post("/api/v1/graph/identities")
    def graph_identity_bind(command: IdentityBind, actor: ActorDep) -> dict[str, Any]:
        return graph_ops.bind(actor, command)

    @app.get("/api/v1/graph/operations/{target_id}")
    def graph_operation_history(
        target_id: str,
        actor: ActorDep,
        offset: Annotated[int, Query(ge=0, le=1000000)] = 0,
        limit: Annotated[int, Query(ge=1, le=100)] = 30,
    ) -> dict[str, Any]:
        return graph_ops.history(actor, target_id, offset, limit)

    @app.post("/api/v1/graph/explore")
    def graph_explore(command: GraphExplore, actor: ActorDep) -> dict[str, Any]:
        return graph_ops.explore(actor, command)

    @app.get("/api/v1/indexes")
    def index_catalog(
        actor: ActorDep,
        scope: str | None = None,
        query: Annotated[str, Query(max_length=200)] = "",
        offset: Annotated[int, Query(ge=0, le=1000000)] = 0,
        limit: Annotated[int, Query(ge=1, le=100)] = 30,
    ) -> dict[str, Any]:
        return indexes.catalog(actor, index_scopes(scope), query, offset, limit)

    @app.get("/api/v1/indexes/unfiled")
    def unfiled(
        actor: ActorDep,
        scope: str | None = None,
        offset: Annotated[int, Query(ge=0, le=1000000)] = 0,
        limit: Annotated[int, Query(ge=1, le=100)] = 30,
    ) -> dict[str, Any]:
        return indexes.entries(actor, None, index_scopes(scope), offset, limit)

    @app.post("/api/v1/indexes")
    def index_create(command: IndexInput, actor: ActorDep) -> dict[str, Any]:
        return indexes.write(actor, command)

    @app.get("/api/v1/indexes/{index_id}")
    def index_get(index_id: str, actor: ActorDep) -> dict[str, Any]:
        return indexes.get(actor, index_id)

    @app.put("/api/v1/indexes/{index_id}")
    def index_edit(index_id: str, command: IndexEdit, actor: ActorDep) -> dict[str, Any]:
        return indexes.write(actor, command, index_id)

    @app.get("/api/v1/indexes/{index_id}/entries")
    def index_entries(
        index_id: str,
        actor: ActorDep,
        scope: str | None = None,
        offset: Annotated[int, Query(ge=0, le=1000000)] = 0,
        limit: Annotated[int, Query(ge=1, le=100)] = 30,
    ) -> dict[str, Any]:
        return indexes.entries(actor, index_id, index_scopes(scope), offset, limit)

    @app.put("/api/v1/indexes/{index_id}/entries")
    def index_link(index_id: str, command: EntryInput, actor: ActorDep) -> dict[str, Any]:
        return indexes.link(actor, index_id, command)

    @app.get("/api/v1/indexes/{index_id}/history")
    def index_history(
        index_id: str,
        actor: ActorDep,
        offset: Annotated[int, Query(ge=0, le=1000000)] = 0,
        limit: Annotated[int, Query(ge=1, le=100)] = 30,
    ) -> dict[str, Any]:
        return indexes.history(actor, index_id, offset, limit)

    @app.post("/api/v1/knowledge/{item_id}/refresh-derived")
    def refresh_derived(item_id: str, actor: ActorDep) -> dict[str, Any]:
        return service.refresh_derived(actor, item_id)

    @app.get("/api/v1/knowledge/{item_id}/references")
    def references(
        item_id: str,
        actor: ActorDep,
        revision_id: str | None = None,
        offset: Annotated[int, Query(ge=0, le=1000000)] = 0,
        limit: Annotated[int, Query(ge=1, le=100)] = 30,
    ) -> dict[str, Any]:
        return indexes.references(actor, item_id, offset, limit, revision_id)

    @app.get("/api/v1/knowledge/{item_id}/revisions/{revision_id}/original")
    def original(item_id: str, revision_id: str, actor: ActorDep) -> Response:
        data, mime, name = service.original(actor, item_id, revision_id)
        return Response(
            data,
            media_type=mime,
            headers={
                "Content-Disposition": "attachment; filename*=UTF-8''" + quote(name, safe=""),
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )

    @app.get("/api/v1/knowledge/{item_id}/revisions/{revision_id}/summary")
    def knowledge_summary(item_id: str, revision_id: str, actor: ActorDep) -> dict[str, Any]:
        return service.summary(actor, item_id, revision_id)

    @app.post("/api/v1/graph/entities")
    def graph_entity(command: EntityInput, actor: ActorDep) -> dict[str, Any]:
        return graph_service.entity(actor, command)

    @app.get("/api/v1/graph/entities")
    def graph_entities(
        actor: ActorDep, query: Annotated[str, Query(max_length=2000)] = "", scope: str | None = None
    ) -> dict[str, Any]:
        if scope:
            try:
                scope = normalize_scope(scope)
            except ValueError:
                raise fail("INVALID_SCOPE") from None
        return graph_service.entities(actor, query, [scope] if scope else None)

    @app.post("/api/v1/graph/assertions")
    def graph_assertion(command: AssertionInput, actor: ActorDep) -> dict[str, Any]:
        return graph_service.assertion(actor, command)

    @app.put("/api/v1/graph/assertions/{assertion_id}")
    def graph_revise(assertion_id: str, command: AssertionRevision, actor: ActorDep) -> dict[str, Any]:
        return graph_service.assertion(actor, command, assertion_id)

    @app.get("/api/v1/graph/assertions/{assertion_id}/history")
    def graph_history(assertion_id: str, actor: ActorDep) -> dict[str, Any]:
        return graph_service.history(actor, assertion_id)

    @app.post("/api/v1/graph/search")
    def graph_search(command: GraphSearch, actor: ActorDep) -> dict[str, Any]:
        return graph_service.search(actor, command)

    @app.get("/api/v1/knowledge")
    def listing(
        actor: ActorDep,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        category: str | None = None,
        memory_kind: MemoryKind | None = None,
        scope: str | None = None,
        include_retired: bool = False,
        has_relations: bool = False,
    ) -> dict[str, Any]:
        if scope is not None:
            try:
                scope = normalize_scope(scope)
            except ValueError:
                raise fail("INVALID_SCOPE") from None
        return service.listing(
            actor, offset, limit, category, memory_kind, scope, include_retired, has_relations
        )

    @app.get("/api/v1/knowledge/categories")
    def categories(actor: ActorDep) -> dict[str, Any]:
        return service.categories(actor)

    @app.post("/api/v1/knowledge/search")
    def search(command: Search, actor: ActorDep) -> dict[str, Any]:
        result = service.search(actor, command)
        if command.include_graph:
            try:
                result["graph"] = graph_service.search(
                    actor,
                    GraphSearch(
                        query=command.query,
                        scopes=command.scopes,
                        include_entity_matches=True,
                        seed_revisions=[
                            GraphSeed(knowledge_id=i["knowledge_id"], revision_id=i["revision_id"])
                            for i in result["items"][:3]
                        ],
                        max_edges=20,
                    ),
                )
            except BusinessError:
                result["graph"] = {"status": "UNAVAILABLE"}
            result["graph_filter_applies_to"] = (
                "owner_and_scopes; document category/type filters apply to direct hits only"
            )
        return result

    @app.post("/api/v1/knowledge/context")
    def context(command: ContextRequest, actor: ActorDep) -> dict[str, Any]:
        return service.context(actor, command)

    @app.put("/api/v1/knowledge/{item_id}/revisions/{revision_id}/workflow")
    def set_workflow(
        item_id: str, revision_id: str, command: WorkflowInput, actor: ActorDep
    ) -> dict[str, Any]:
        return service.set_workflow(actor, item_id, revision_id, command)

    @app.get("/api/v1/knowledge/{item_id}/revisions/{revision_id}/workflow")
    def get_workflow(item_id: str, revision_id: str, actor: ActorDep) -> dict[str, Any]:
        return service.get_workflow(actor, item_id, revision_id)

    @app.post("/api/v1/knowledge/{item_id}/revisions", status_code=202)
    def revise(item_id: str, command: ReviseKnowledge, actor: ActorDep) -> dict[str, str]:
        return service.revise(actor, item_id, command)

    @app.post("/api/v1/knowledge/{item_id}/retire")
    def retire(item_id: str, command: RetireKnowledge, actor: ActorDep) -> dict[str, Any]:
        return service.retire(actor, item_id, command)

    @app.post("/api/v1/knowledge/{item_id}/restore")
    def restore(item_id: str, command: RestoreKnowledge, actor: ActorDep) -> dict[str, Any]:
        return service.restore(actor, item_id, command)

    @app.get("/api/v1/knowledge/{item_id}/history")
    def history(item_id: str, actor: ActorDep) -> dict[str, Any]:
        return service.history(actor, item_id)

    @app.get("/api/v1/knowledge/{item_id}")
    def get(item_id: str, actor: ActorDep) -> dict[str, Any]:
        return service.get(actor, item_id)

    @app.get("/api/v1/knowledge/{item_id}/revisions/{revision_id}/content")
    def content(item_id: str, revision_id: str, actor: ActorDep) -> dict[str, Any]:
        return service.content(actor, item_id, revision_id)

    @app.get("/api/v1/jobs/{job_id}")
    def job(job_id: str, actor: ActorDep) -> dict[str, Any]:
        return service.job(actor, job_id)

    @app.post("/api/v1/jobs/{job_id}/retry", status_code=202)
    def retry(job_id: str, actor: ActorDep) -> dict[str, str]:
        return service.retry(actor, job_id)

    return app
