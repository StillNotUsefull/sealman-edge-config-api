import asyncio
import logging
from collections.abc import Callable, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Set

from fastapi import FastAPI, HTTPException, Request, Security
from fastapi.datastructures import Default
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html, get_swagger_ui_oauth2_redirect_html
from fastapi.params import Depends
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute, APIRouter
from fastapi.staticfiles import StaticFiles
from fastapi.utils import generate_unique_id
from starlette.middleware import Middleware
from starlette.responses import Response
from starlette.routing import BaseRoute
from starlette.types import Lifespan

from sealman._internal.auth import validate_jwt, SWAGGER_CLIENT_ID, refresh_jwks_cache, fetch_oidc_issuer
from sealman._internal.constants import (
    DEVICE_CACHE_INTERVAL,
    IOT_HUB_NAME,
    CORS_ALLOWED_ORIGINS,
    VERSION,
    ROOT_PATH,
    ALLOW_STARTUP_WITHOUT_OIDC,
    BOOTSTRAP_ENABLED,
    ENABLE_DOCS,
)
from sealman._internal.db.repos.device import DeviceRepository
from sealman._internal.exceptions import APIError
from sealman._internal.db.session import AsyncSessionLocal, get_repository
from sealman._internal.db.migration import run_migrations
from sealman._internal.periodic_task import create_periodic_task
from sealman._internal.routers.devices.routes.get_devices import populate_cache_from_iot_hub_query
from sealman._internal.routers.smart_ems.password_renewal_task_processor import process_password_renewal_tasks
from sealman._internal.smart_ems import init_smart_ems
from sealman._internal.bootstrap import bootstrap_sems, bootstrap_iothub_base_deployment
from sealman._internal.helper import AuditTrail

from sealman._internal.routers.cmd_proxy.router import cmd_proxy
from sealman._internal.routers.general.router import general
from sealman._internal.routers.module_config.router import module_config
from sealman._internal.routers.smart_ems.router import smart_ems
from sealman._internal.routers.network_discovery.router import network_discovery
from sealman._internal.routers.auth.router import auth
from sealman._internal.routers.lines.router import lines
from sealman._internal.routers.platform_configuration.router import platform_config
from sealman._internal.routers.compose_deployments.router import compose_deployment, active_deployment
from sealman._internal.routers.devices.router import devices

# Logger
logger = logging.getLogger("EdgeConfigAPI")
logger.setLevel(logging.INFO)
_log_handler = logging.StreamHandler()
_log_handler.setFormatter(
    logging.Formatter(fmt="%(levelname)s:     %(asctime)s >> %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
)
logger.addHandler(_log_handler)

# Static assets bundled with the package
_STATIC_DIR = Path(__file__).parent / "static"

# Module-level defaults (evaluated once at import time from environment)
_DEFAULT_TITLE = "Edge Configuration API"
_DEFAULT_DESCRIPTION = f"API for configuring Edge Device Modules on IoTHub ({IOT_HUB_NAME})."
_DEFAULT_ROOT_PATH = ROOT_PATH or ""


class App(FastAPI):
    """
    Sealman Core application.

    Drop-in FastAPI app with all built-in routers, middleware, lifespan, and
    exception handlers wired up. Pass extra APIRouter instances to extend it.

    All standard FastAPI ``__init__`` keyword arguments are supported and will
    override Sealman's built-in defaults when supplied.

    Usage::

        from sealman import App

        app = App()

        # Override FastAPI params:
        app = App(title="My API", debug=True)

        # Add custom routers:
        app = App(routers=[my_router])

    Note: ``dependencies=None`` keeps the default JWT auth guard.
    Pass ``dependencies=[]`` to disable authentication entirely.
    """

    def __init__(
        self,
        *,
        # ── Sealman extension ────────────────────────────────────────────────
        routers: Sequence[APIRouter] = (),
        # ── App identity ─────────────────────────────────────────────────────
        debug: bool = False,
        title: str = _DEFAULT_TITLE,
        summary: str | None = None,
        description: str = _DEFAULT_DESCRIPTION,
        version: str = VERSION,
        # ── OpenAPI / Docs ────────────────────────────────────────────────────
        openapi_url: str | None = "/openapi.json",
        openapi_tags: list[dict[str, Any]] | None = None,
        openapi_prefix: str = "",
        docs_url: str | None = None,           # disabled — custom /docs route handles it
        redoc_url: str | None = None,          # disabled
        swagger_ui_oauth2_redirect_url: str | None = "/docs/oauth2-redirect",
        swagger_ui_init_oauth: dict[str, Any] | None = None,   # None → PKCE default
        swagger_ui_parameters: dict[str, Any] | None = None,
        # ── Routing ──────────────────────────────────────────────────────────
        routes: list[BaseRoute] | None = None,
        redirect_slashes: bool = True,
        root_path: str = _DEFAULT_ROOT_PATH,
        root_path_in_servers: bool = True,
        servers: list[dict[str, Any]] | None = None,
        # ── Auth / Dependencies ───────────────────────────────────────────────
        dependencies: Sequence[Depends] | None = None,    # None → [Security(validate_jwt)]
        # ── Responses ────────────────────────────────────────────────────────
        default_response_class: type[Response] = Default(JSONResponse),  # type: ignore[assignment]
        responses: dict[int | str, dict[str, Any]] | None = None,
        # ── Lifespan / Events ─────────────────────────────────────────────────
        lifespan: Lifespan[FastAPI] | None = None,    # None → sealman internal lifespan
        on_startup: Sequence[Callable[[], Any]] | None = None,
        on_shutdown: Sequence[Callable[[], Any]] | None = None,
        # ── Middleware / Exception handlers ───────────────────────────────────
        middleware: Sequence[Middleware] | None = None,
        exception_handlers: dict[Any, Callable[..., Any]] | None = None,
        # ── Metadata ─────────────────────────────────────────────────────────
        terms_of_service: str | None = None,
        contact: dict[str, str | Any] | None = None,
        license_info: dict[str, str | Any] | None = None,
        # ── Extra routing ─────────────────────────────────────────────────────
        callbacks: list[BaseRoute] | None = None,
        webhooks: APIRouter | None = None,
        # ── Misc ─────────────────────────────────────────────────────────────
        generate_unique_id_function: Callable[[APIRoute], str] = Default(generate_unique_id),  # type: ignore[assignment]
        separate_input_output_schemas: bool = True,
    ) -> None:
        logger.info(f"Edge-Config-API ({VERSION})")

        background_tasks: Set[asyncio.Task] = set()

        async def _populate_cache():
            async with AsyncSessionLocal() as session:
                repo = get_repository(DeviceRepository)(session)
                await populate_cache_from_iot_hub_query(repo)

        @asynccontextmanager
        async def _sealman_lifespan(app: FastAPI):
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, run_migrations)

            jwks_refresh_task = None
            try:
                await fetch_oidc_issuer()
                jwks_refresh_task = asyncio.create_task(refresh_jwks_cache())
            except Exception as ex:
                if not ALLOW_STARTUP_WITHOUT_OIDC:
                    raise
                logger.warning(
                    "OIDC discovery unavailable during startup. "
                    "Continuing because ALLOW_STARTUP_WITHOUT_OIDC=true. "
                    f"Authentication-protected requests may fail until the provider is reachable: {ex}"
                )

            if BOOTSTRAP_ENABLED:
                await bootstrap_sems()
                await bootstrap_iothub_base_deployment()

            sems_token_refresh = asyncio.create_task(init_smart_ems())

            background_tasks.add(asyncio.create_task(create_periodic_task(
                func=_populate_cache,
                interval=DEVICE_CACHE_INTERVAL,
            )))
            background_tasks.add(asyncio.create_task(create_periodic_task(
                func=process_password_renewal_tasks,
                interval=(30 * 60),
                initial_delay=60,
            )))

            yield

            if jwks_refresh_task is not None:
                jwks_refresh_task.cancel()
            sems_token_refresh.cancel()
            for task in background_tasks:
                task.cancel()
            if background_tasks:
                await asyncio.gather(*background_tasks, return_exceptions=True)

        # Always run sealman's core lifespan. If the caller supplied their own,
        # nest it inside so core startup always runs first and core shutdown last.
        if lifespan is not None:
            _caller_lifespan = lifespan

            @asynccontextmanager
            async def _combined_lifespan(app: FastAPI):
                async with _sealman_lifespan(app):
                    async with _caller_lifespan(app):
                        yield

            _lifespan = _combined_lifespan
        else:
            _lifespan = _sealman_lifespan
        # Core JWT auth always present; caller deps are appended after it
        _dependencies = [Security(validate_jwt), *(dependencies or [])]

        # Core PKCE config is the base; caller can override individual keys
        _swagger_ui_init_oauth = {
            "usePkceWithAuthorizationCodeGrant": True,
            "clientId": SWAGGER_CLIENT_ID,
            **(swagger_ui_init_oauth or {}),
        }

        super().__init__(
            debug=debug,
            routes=routes,
            title=title,
            summary=summary,
            description=description,
            version=version,
            openapi_url=openapi_url,
            openapi_tags=openapi_tags,
            servers=servers,
            dependencies=_dependencies,
            default_response_class=default_response_class,
            redirect_slashes=redirect_slashes,
            docs_url=docs_url,
            redoc_url=redoc_url,
            swagger_ui_oauth2_redirect_url=swagger_ui_oauth2_redirect_url,
            swagger_ui_init_oauth=_swagger_ui_init_oauth,
            swagger_ui_parameters=swagger_ui_parameters,
            middleware=middleware,
            exception_handlers=exception_handlers,
            on_startup=on_startup,
            on_shutdown=on_shutdown,
            lifespan=_lifespan,
            terms_of_service=terms_of_service,
            contact=contact,
            license_info=license_info,
            openapi_prefix=openapi_prefix,
            root_path=root_path,
            root_path_in_servers=root_path_in_servers,
            responses=responses,
            callbacks=callbacks,
            webhooks=webhooks,
            generate_unique_id_function=generate_unique_id_function,
            separate_input_output_schemas=separate_input_output_schemas,
        )

        # ── CORS ──────────────────────────────────────────────────────────────
        allowed_origins = []
        if CORS_ALLOWED_ORIGINS:
            allowed_origins.extend(CORS_ALLOWED_ORIGINS.split(","))
        self.add_middleware(
            CORSMiddleware,  # type: ignore[arg-type]
            allow_origins=allowed_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
            expose_headers=["*"],
        )

        # ── Audit-trail middleware ─────────────────────────────────────────────
        @self.middleware("http")
        async def add_path_to_audit_trail_log(request: Request, call_next):
            query_params = ""
            if request.query_params:
                query_params = f"?{request.query_params}"
            await AuditTrail.log_route(f"{request.method} {request.url.path}{query_params}")
            return await call_next(request)

        # ── Static files ──────────────────────────────────────────────────────
        self.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

        # ── Built-in routers ──────────────────────────────────────────────────
        for router in (
            auth, general, compose_deployment, active_deployment,
            module_config, smart_ems, cmd_proxy, network_discovery,
            lines, platform_config, devices,
        ):
            self.include_router(router)

        # ── Caller-supplied extra routers ─────────────────────────────────────
        for router in routers:
            self.include_router(router)

        # ── Swagger docs (bypass JWT dependency) ──────────────────────────────
        root = root_path or ""

        async def _swagger_ui(req: Request):
            return get_swagger_ui_html(
                openapi_url=f"{root}/openapi.json",
                title="",
                oauth2_redirect_url=f"{root}/docs/oauth2-redirect",
                swagger_favicon_url="/static/api-logo.png",
                init_oauth=self.swagger_ui_init_oauth,
                swagger_ui_parameters=self.swagger_ui_parameters,
            )

        async def _swagger_redirect(req: Request):
            return get_swagger_ui_oauth2_redirect_html()

        if ENABLE_DOCS:
            self.add_route("/docs", _swagger_ui, include_in_schema=False)
            self.add_route("/docs/oauth2-redirect", _swagger_redirect, include_in_schema=False)

        # ── Exception handlers ────────────────────────────────────────────────
        @self.exception_handler(APIError)
        async def handle_api_error(request: Request, ex: APIError):
            logger.error(f"APIError: [{ex}]")
            return JSONResponse(status_code=ex.status_code, content={"message": str(ex.message)})

        @self.exception_handler(HTTPException)
        async def handle_http_exception(request: Request, ex: HTTPException):
            logger.error(f"HTTPException: [{ex}]")
            return JSONResponse(status_code=ex.status_code, content={"message": ex.detail})

        @self.exception_handler(RequestValidationError)
        async def handle_validation_error(request: Request, ex: RequestValidationError):
            logger.error(f"RequestValidationError: [{ex}]")
            return JSONResponse(status_code=400, content={"message": ex.body})

        @self.exception_handler(Exception)
        async def handle_unhandled(request: Request, ex: Exception):
            logger.error(f"Unhandled exception: [{ex}]")
            return JSONResponse(status_code=500, content={"message": str(ex)})
