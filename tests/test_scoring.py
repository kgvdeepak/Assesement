from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from main import app
from app.db import get_db
from app.models import Base, ExamSession, Option, Question


@pytest.fixture()
def session_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(engine)

    yield TestingSessionLocal

    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def client(session_factory):
    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def create_multi_question(session: Session) -> tuple[int, list[int]]:
    question = Question(text="Select vowels", type="multi")
    question.options = [
        Option(text="A", is_correct=True),
        Option(text="B", is_correct=False),
        Option(text="E", is_correct=True),
    ]
    session.add(question)
    session.flush()
    correct_ids = [opt.id for opt in question.options if opt.is_correct]
    session.commit()
    return question.id, correct_ids


def start_attempt(client: TestClient, session_factory: sessionmaker) -> int:
    response = client.get("/exam/start")
    assert response.status_code == 201
    with session_factory() as db:
        attempt_id = db.query(ExamSession.id).first()[0]
    return attempt_id


def test_multi_choice_requires_exact_match(client: TestClient, session_factory: sessionmaker):
    with session_factory() as db:
        qid, correct_ids = create_multi_question(db)

    attempt_id = start_attempt(client, session_factory)

    partial_payload = {
        "attempt_id": attempt_id,
        "answers": [
            {"question_id": qid, "selected_option_ids": [correct_ids[0]]},
        ],
    }

    response = client.post("/exam/submit", json=partial_payload, allow_redirects=False)
    assert response.status_code == 303

    result_response = client.get(f"/exam/result/{attempt_id}")
    assert result_response.status_code == 200
    assert "0.0" in result_response.text or "0" in result_response.text
    assert "Fail" in result_response.text


def test_no_answers_yields_zero_score(client: TestClient, session_factory: sessionmaker):
    with session_factory() as db:
        create_multi_question(db)

    attempt_id = start_attempt(client, session_factory)

    payload = {"attempt_id": attempt_id, "answers": []}
    response = client.post("/exam/submit", json=payload, allow_redirects=False)
    assert response.status_code == 303

    result_response = client.get(f"/exam/result/{attempt_id}")
    assert result_response.status_code == 200
    assert "0.0" in result_response.text or "0" in result_response.text
    assert "Fail" in result_response.text


def test_invalid_attempt_returns_404(client: TestClient):
    payload = {"attempt_id": 9999, "answers": []}
    response = client.post("/exam/submit", json=payload)
    assert response.status_code == 404


def test_malformed_payload_returns_422(client: TestClient, session_factory: sessionmaker):
    with session_factory() as db:
        create_multi_question(db)

    attempt_id = start_attempt(client, session_factory)

    response = client.post(
        "/exam/submit",
        json={"attempt_id": attempt_id, "answers": "not-a-list"},
    )
    assert response.status_code == 422
