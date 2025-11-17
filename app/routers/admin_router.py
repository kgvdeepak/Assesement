from __future__ import annotations

import os
from typing import Dict

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from scripts.seed_questions import main as seed_main

router = APIRouter(prefix="/admin", tags=["admin"])

# Copilot: replace DEV_ADMIN_TOKEN with an env var or real auth mechanism in production.
DEV_ADMIN_TOKEN = os.getenv("DEV_ADMIN_TOKEN", "changeme")

templates = Jinja2Templates(directory="templates")


@router.get("", include_in_schema=False)
async def admin_dashboard_no_slash() -> RedirectResponse:
    return RedirectResponse(url="/admin/", status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@router.get("/", response_class=HTMLResponse)
async def admin_dashboard(request: Request) -> HTMLResponse:
    context = {
        "request": request,
        "dev_token": DEV_ADMIN_TOKEN,
    }
    return templates.TemplateResponse("admin_dashboard.html", context)


def verify_admin_token(x_admin_token: str = Header(...)) -> None:
    if x_admin_token != DEV_ADMIN_TOKEN:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin token.")


@router.post("/seed")
async def run_seed(
    __: None = Depends(verify_admin_token),
) -> Dict[str, str]:
    # Copilot: this endpoint is intended for local development only.
    code = seed_main()
    if code != 0:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Seed script failed.")
    return {"status": "ok", "message": "Seeding completed."}
