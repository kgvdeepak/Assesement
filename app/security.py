"""Lightweight CSRF helpers used by the exam routes.

If ``fastapi-csrf-protect`` is installed, we expose a ready-to-wire dependency
that mirrors the library's quick-start example. Otherwise we fall back to a
simple token pattern: generate a random value when creating an ``ExamSession``,
store it (e.g. on an ``ExamSession.csrf_token`` column), include it in the form,
and call :func:`verify_csrf` during submission.
"""

from __future__ import annotations

import os
import secrets
from typing import Optional

from fastapi import Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import ExamSession

try:  # pragma: no cover - optional dependency wiring
    from fastapi_csrf_protect import CsrfProtect, CsrfProtectError  # type: ignore
except ImportError:  # pragma: no cover - executed when the package is absent
    CsrfProtect = None  # type: ignore
    CsrfProtectError = Exception  # type: ignore


class CsrfSettings(BaseModel):
    """Configuration model consumed by ``fastapi-csrf-protect`` when available."""

    secret_key: str = os.getenv("CSRF_SECRET_KEY", "change_me")


if CsrfProtect is not None:  # pragma: no cover - configuration is library specific

    @CsrfProtect.load_config
    def get_csrf_config() -> CsrfSettings:
        return CsrfSettings()


def issue_csrf_token(exam_session: ExamSession) -> str:
    """Return a CSRF token, generating and persisting one as needed.

    When the optional ``fastapi-csrf-protect`` package is present we delegate to
    it, otherwise we fall back to a per-attempt random token stored on the
    ``ExamSession`` model.
    """

    if CsrfProtect is not None:  # pragma: no cover - external library heavy
        protect = CsrfProtect()  # type: ignore[call-arg]
        return protect.generate_csrf_tokens()[0]

    token_attr = "csrf_token"
    token = getattr(exam_session, token_attr, None)
    if not token:
        token = secrets.token_urlsafe(32)
        setattr(exam_session, token_attr, token)
    return token


def verify_csrf(attempt_id: int, token: Optional[str], db: Session = Depends(get_db)) -> ExamSession:
    """Hydrate an ``ExamSession`` and ensure the supplied token matches.

    This helper raises ``HTTPException`` with the appropriate status code on any
    validation failure and returns the validated ``ExamSession`` for callers that
    need to continue processing the submission.
    """

    if not token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing CSRF token.")

    exam_session: Optional[ExamSession] = (
        db.query(ExamSession).filter(ExamSession.id == attempt_id).one_or_none()
    )
    if exam_session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exam session not found.")

    if CsrfProtect is not None:  # pragma: no cover - external library heavy
        protect = CsrfProtect()  # type: ignore[call-arg]
        try:
            protect.validate_csrf(token)
        except CsrfProtectError as exc:  # type: ignore[misc]
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
        return exam_session

    expected = getattr(exam_session, "csrf_token", None)
    if not expected or not secrets.compare_digest(str(expected), str(token)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token.")

    return exam_session
