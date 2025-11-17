from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
import uvicorn

# Copilot: replace placeholder routers with actual imports once available.
# Copilot: wire the remaining routers when they are implemented.
# Copilot: replace these placeholders when admin routers are ready.
from fastapi.routing import APIRouter

from importlib import import_module


def _load_testclient():
    try:
        module = import_module("fastapi.testclient")
    except ImportError:  # pragma: no cover - test utilities not available in prod.
        return None
    return getattr(module, "TestClient", None)


_FastAPITestClient = _load_testclient()

from app.routers.admin_router import router as admin_router
from app.routers.exam_router import router as exam_router
from app.routers.submission_router import router as submission_router
# Copilot: import DB session dependency helpers from app.db when wiring routes.


def _patch_testclient_allow_redirects() -> None:
    """Add allow_redirects compatibility for Starlette TestClient."""

    if _FastAPITestClient is None:
        return

    if getattr(_FastAPITestClient, "_allow_redirects_compat", False):
        return

    original_post = _FastAPITestClient.post

    def patched_post(self, url, **kwargs):
        allow_redirects = kwargs.pop("allow_redirects", None)
        if allow_redirects is not None and "follow_redirects" not in kwargs:
            kwargs["follow_redirects"] = allow_redirects
        return original_post(self, url, **kwargs)

    _FastAPITestClient.post = patched_post  # type: ignore[assignment]
    _FastAPITestClient._allow_redirects_compat = True  # type: ignore[attr-defined]


_patch_testclient_allow_redirects()

app = FastAPI(title="Exam Workshop")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:3000", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static", check_dir=False), name="static")
templates = Jinja2Templates(directory="templates")

app.include_router(exam_router)
app.include_router(submission_router)
app.include_router(admin_router)


@app.get("/", response_class=HTMLResponse)
async def landing_page(request: Request):
    return templates.TemplateResponse(
        "home.html",
        {"request": request},
    )


@app.get("/health")
def healthcheck():
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
