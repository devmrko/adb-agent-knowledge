"""Factory wires dependencies explicitly; imports do not start databases or servers."""

import secrets
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, cast

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from sqlalchemy import text

from example_app.models import CreateProject, ProjectListing, ProjectView, RenameProject
from example_app.service import ProjectService
from python_foundation.database import create_database, sessions
from python_foundation.errors import AuthenticationRequired, BusinessError, ErrorCategory, ErrorSpec
from python_foundation.security import Actor, Security, SessionStore, TokenVerifier, current_actor
from python_foundation.settings import FoundationSettings
from python_foundation.web import configure_logging, install_web

ActorDependency = Annotated[Actor, Depends(current_actor)]
Authenticator = Callable[[str, str], Actor | None]


def create_app(
    settings: FoundationSettings | None = None,
    *,
    store: SessionStore | None = None,
    verifier: TokenVerifier | None = None,
    authenticate_user: Authenticator | None = None,
) -> FastAPI:
    settings = settings or FoundationSettings()
    security = Security(settings, store=store, verifier=verifier)
    if settings.auth_mode != "token" and authenticate_user is None:
        if settings.environment == "production" or settings.development_password is None:
            raise ValueError(
                "Provide authenticate_user, or set FOUNDATION_DEVELOPMENT_PASSWORD for development"
            )
        password = settings.development_password.get_secret_value().encode()
        if len(password) < 12:
            raise ValueError("Development password must contain at least 12 characters")

        def development_login(username: str, supplied: str) -> Actor | None:
            valid_password = secrets.compare_digest(supplied.encode(), password)
            if username == "user" and valid_password:
                return Actor("local", "user", frozenset({"ROLE_USER"}))
            return None

        authenticate_user = development_login

    engine = create_database(settings)
    service = ProjectService(sessions(engine))
    templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        configure_logging()
        try:
            yield
        finally:
            engine.dispose()

    app = FastAPI(
        title="Python Foundation",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.engine = engine
    app.state.projects = service
    install_web(app, security)

    @app.get("/actuator/health")
    def health() -> dict[str, str]:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1 FROM DUAL" if engine.dialect.name == "oracle" else "SELECT 1"))
        return {"status": "UP"}

    @app.get("/openapi.json")
    def schema(actor: ActorDependency) -> dict[str, object]:
        return cast(dict[str, object], app.openapi())

    @app.get("/api/v1/projects")
    def list_projects(actor: ActorDependency, page: int = 0) -> ProjectListing:
        return service.list(page, actor)

    @app.post("/api/v1/projects", status_code=201)
    def create_project(command: CreateProject, actor: ActorDependency, request: Request) -> JSONResponse:
        result = service.create(command, actor)
        return JSONResponse(
            result.model_dump(),
            status_code=201,
            headers={"Location": str(request.url_for("get_project", project_id=result.id))},
        )

    @app.get("/api/v1/projects/{project_id}", name="get_project")
    def get_project(project_id: str, actor: ActorDependency) -> ProjectView:
        return service.get(project_id, actor)

    @app.put("/api/v1/projects/{project_id}")
    def update_project(project_id: str, command: RenameProject, actor: ActorDependency) -> ProjectView:
        return service.update(project_id, command, actor)

    @app.delete("/api/v1/projects/{project_id}", status_code=204)
    def delete_project(project_id: str, actor: ActorDependency) -> Response:
        service.delete(project_id, actor)
        return Response(status_code=204)

    # The form routes are absent in token-only applications.
    if settings.auth_mode != "token":

        @app.get("/login", name="login_page")
        def login_page(request: Request) -> HTMLResponse:
            cookie_response = Response()
            csrf = security.begin_login(request, cookie_response)
            response = templates.TemplateResponse(request, "login.html", {"csrf": csrf})
            if "set-cookie" in cookie_response.headers:
                response.headers["set-cookie"] = cookie_response.headers["set-cookie"]
            return response

        @app.post("/login")
        def login(
            request: Request,
            username: Annotated[str, Form(max_length=160)],
            password: Annotated[str, Form(max_length=1024)],
            csrf: Annotated[str, Form()],
        ) -> RedirectResponse:
            security.check_csrf(request, csrf)
            assert authenticate_user is not None
            actor = authenticate_user(username, password)
            if actor is None:
                raise AuthenticationRequired()
            response = RedirectResponse(str(request.url_for("projects_page")), status_code=303)
            security.login(request, response, actor, csrf)
            return response

        @app.post("/logout")
        def logout(request: Request, csrf: Annotated[str, Form()]) -> RedirectResponse:
            response = RedirectResponse(str(request.url_for("login_page")), status_code=303)
            security.logout(request, response, csrf)
            return response

        @app.get("/")
        def home() -> RedirectResponse:
            return RedirectResponse("/projects", status_code=303)

        @app.get("/projects", name="projects_page")
        def projects_page(
            request: Request, actor: Annotated[Actor, Depends(security.authenticate)], page: int = 0
        ) -> HTMLResponse:
            return templates.TemplateResponse(
                request,
                "projects.html",
                {"listing": service.list(page, actor), "csrf": security.csrf(request)},
            )

        @app.post("/projects")
        def create_page(
            request: Request,
            actor: Annotated[Actor, Depends(security.authenticate)],
            name: Annotated[str, Form(min_length=1, max_length=160)],
            csrf: Annotated[str, Form()],
        ) -> RedirectResponse:
            security.check_csrf(request, csrf)
            try:
                command = CreateProject(name=name)
            except ValidationError as failure:
                raise BusinessError(
                    ErrorSpec("VALIDATION_FAILED", ErrorCategory.VALIDATION, "Input validation failed")
                ) from failure
            service.create(command, actor)
            return RedirectResponse(str(request.url_for("projects_page")), status_code=303)

    return app
