from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Iterable, List

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.models import ExamSession, Question, UserResponse
from app.schemas import ExamSubmissionIn

router = APIRouter(prefix="/exam", tags=["exam-submission"])

templates = Jinja2Templates(directory="templates")

DEFAULT_PASS_THRESHOLD = 0.6  # 60% default pass threshold


def extract_threshold(request: Request) -> float:
    raw = request.query_params.get("pass_threshold")
    if raw is None:
        return DEFAULT_PASS_THRESHOLD
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_PASS_THRESHOLD
    return min(max(value, 0.0), 1.0)


async def parse_submission_payload(request: Request) -> Dict:
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise ValueError("JSON payload must be an object.")
        return payload

    form = await request.form()
    answers: List[Dict] = []
    for key in form.keys():
        key_base = key
        if key.endswith("[]"):
            key_base = key[:-2]

        if key_base.startswith("answer_"):
            _, _, raw_id = key_base.partition("_")
        elif key_base.startswith("q_"):
            _, _, raw_id = key_base.partition("_")
        else:
            continue

        if not raw_id.isdigit():
            continue

        question_id = int(raw_id)
        values = form.getlist(key)
        answers.append(
            {
                "question_id": question_id,
                "selected_option_ids": values,
            }
        )

    payload = {
        "attempt_id": form.get("attempt_id"),
        "answers": answers,
    }
    return payload


def build_question_map(questions: Iterable[Question]) -> Dict[int, Question]:
    return {question.id: question for question in questions}


def score_question(question: Question, selected_ids: Iterable[int]) -> float:
    correct_ids = {option.id for option in question.options if option.is_correct}
    selected_set = set(int(option_id) for option_id in selected_ids)

    if question.type == "single":
        if len(selected_set) != 1:
            return 0.0
        return 1.0 if selected_set.pop() in correct_ids else 0.0

    # Multi-choice earns a point only when the selection exactly matches the correct set.
    return 1.0 if selected_set == correct_ids else 0.0


@router.post("/submit")
async def submit_exam(
    request: Request,
    db: Session = Depends(get_db),
):
    try:
        raw_payload = await parse_submission_payload(request)
    except ValueError as exc:
        return templates.TemplateResponse(
            "400.html",
            {"request": request, "message": str(exc)},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    attempt_id = raw_payload.get("attempt_id")
    if attempt_id is None:
        return templates.TemplateResponse(
            "400.html",
            {"request": request, "message": "Attempt identifier missing."},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    try:
        attempt_id_int = int(attempt_id)
    except (TypeError, ValueError):
        return templates.TemplateResponse(
            "400.html",
            {"request": request, "message": "Invalid attempt identifier."},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    exam_session = (
        db.query(ExamSession)
        .options(selectinload(ExamSession.responses))
        .filter(ExamSession.id == attempt_id_int)
        .one_or_none()
    )
    if exam_session is None:
        return templates.TemplateResponse(
            "404.html",
            {"request": request, "message": "Attempt not found."},
            status_code=status.HTTP_404_NOT_FOUND,
        )

    questions = (
        db.query(Question)
        .options(selectinload(Question.options))
        .order_by(Question.id.asc())
        .all()
    )
    question_map = build_question_map(questions)
    raw_payload["question_type_map"] = {qid: q.type for qid, q in question_map.items()}

    raw_payload.setdefault("answers", [])
    raw_payload["attempt_id"] = attempt_id_int

    try:
        submission = ExamSubmissionIn.model_validate(raw_payload)
    except ValidationError as exc:
        return JSONResponse(
            {"detail": exc.errors()},
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    answers_by_question = {
        answer.question_id: answer.selected_option_ids
        for answer in submission.answers
    }

    db.query(UserResponse).filter(
        UserResponse.exam_session_id == exam_session.id
    ).delete(synchronize_session=False)

    score = 0.0
    question_count = len(question_map)

    for question in questions:
        selected = answers_by_question.get(question.id, [])
        score += score_question(question, selected)

        user_response = UserResponse(
            exam_session_id=exam_session.id,
            question_id=question.id,
        )
        # Store unanswered questions with an empty selection for auditing purposes.
        user_response.set_selected_option_ids(selected)
        db.add(user_response)

    max_score = float(exam_session.max_score or question_count or 0)
    if max_score == 0:
        max_score = float(question_count)

    threshold = extract_threshold(request)
    passed = bool(score >= (threshold * max_score if max_score else 0))

    exam_session.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    exam_session.total_score = score
    exam_session.max_score = max_score
    exam_session.passed = passed

    db.add(exam_session)
    db.commit()

    redirect_url = request.app.url_path_for("view_result", attempt_id=submission.attempt_id)
    return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)
