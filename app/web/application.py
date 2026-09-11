from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jinja2 import ChainableUndefined


def build_web_application(
    *,
    static_dir: Path,
    templates_dir: Path,
    routers: Iterable[APIRouter] = (),
) -> tuple[FastAPI, Jinja2Templates]:
    app = FastAPI(
        title="CoRA Mail Agent",
        description="Demo-first CoRA Mail Agent UI.",
        version="0.1.0",
    )
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    for router in routers:
        app.include_router(router)

    templates = Jinja2Templates(directory=templates_dir)
    templates.env.undefined = ChainableUndefined
    return app, templates
