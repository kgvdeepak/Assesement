from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.models import ExamSession, Question, UserResponse
from app.schemas import QuestionOut, ResultOut, QuestionResult

router = APIRouter(prefix="/exam", tags=["exam"])

# Copilot: adjust template directories if project structure changes.
templates = Jinja2Templates(directory="templates")

DEFAULT_PER_PAGE = 10
MAX_PER_PAGE = 50


def paginate_query(query, page: int, per_page: int):
    return query.offset((page - 1) * per_page).limit(per_page)


@router.get("", response_class=HTMLResponse)
async def list_exam_questions(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(DEFAULT_PER_PAGE, ge=1, le=MAX_PER_PAGE),
    db: Session = Depends(get_db),
):
    total_questions = db.query(func.count(Question.id)).scalar() or 0
    questions_query = (
        db.query(Question)
        .options(selectinload(Question.options))
        .order_by(Question.id.asc())
    )
    questions: List[Question] = paginate_query(questions_query, page, per_page).all()
    serialized = [QuestionOut.model_validate(question) for question in questions]

    context = {
        "request": request,
        "questions": serialized,
        "page": page,
        "per_page": per_page,
        "total": total_questions,
        "total_pages": max(1, (total_questions + per_page - 1) // per_page),
    }
    return templates.TemplateResponse("exam_list.html", context)


@router.get("/start", response_class=HTMLResponse)
async def start_exam(
    request: Request,
    db: Session = Depends(get_db),
):
    question_count: int = db.query(func.count(Question.id)).scalar() or 0
    exam_session = ExamSession(
        started_at=datetime.now(timezone.utc).replace(tzinfo=None),
        max_score=float(question_count),
    )
    db.add(exam_session)
    db.commit()
    db.refresh(exam_session)

    questions = (
        db.query(Question)
        .options(selectinload(Question.options))
        .order_by(Question.id.asc())
        .all()
    )
    serialized = [QuestionOut.model_validate(question) for question in questions]

    context = {
        "request": request,
        "attempt_id": str(exam_session.id),
        "questions": serialized,
        "max_score": exam_session.max_score,
    }
    return templates.TemplateResponse(
        "exam_form.html",
        context,
        status_code=status.HTTP_201_CREATED,
    )


def build_result(exam_session: ExamSession) -> ResultOut:
    breakdown: List[QuestionResult] = []
    score = 0.0

    for response in exam_session.responses:
        question: Question = response.question
        correct_options = {option.id for option in question.options if option.is_correct}
        selected_options = set(response.selected_option_ids)

        if question.type == "single":
            is_correct = len(selected_options) == 1 and selected_options.issubset(correct_options)
        else:
            is_correct = selected_options == correct_options

        question_score = 1.0 if is_correct else 0.0
        score += question_score

        breakdown.append(
            QuestionResult(
                question_id=question.id,
                selected_option_ids=response.selected_option_ids,
                correct=is_correct,
                score=question_score,
            )
        )

    max_score = float(exam_session.max_score or len(breakdown))
    passed = bool(exam_session.passed or score >= (0.7 * max_score if max_score else 0))

    return ResultOut(
        score=score,
        max_score=max_score,
        passed=passed,
        breakdown=breakdown,
    )


@router.get("/result/{attempt_id}", response_class=HTMLResponse)
async def view_result(
    request: Request,
    attempt_id: int,
    db: Session = Depends(get_db),
):
    exam_session: Optional[ExamSession] = (
        db.query(ExamSession)
        .options(
            selectinload(ExamSession.responses)
            .selectinload(UserResponse.question)
            .selectinload(Question.options)
        )
        .filter(ExamSession.id == attempt_id)
        .one_or_none()
    )

    if exam_session is None:
        return templates.TemplateResponse(
            "404.html",
            {"request": request, "message": "Attempt not found."},
            status_code=status.HTTP_404_NOT_FOUND,
        )

    result = build_result(exam_session)

    return templates.TemplateResponse(
        "result.html",
        {
            "request": request,
            "attempt_id": attempt_id,
            "result": result,
        },
    )
