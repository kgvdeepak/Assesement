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


def seed_questions(factory: sessionmaker) -> dict[str, object]:
    with factory() as db:  # type: Session
        single = Question(text="Capital of France", type="single")
        single.options = [
            Option(text="Berlin", is_correct=False),
            Option(text="Paris", is_correct=True),
        ]
        multi = Question(text="Select prime numbers", type="multi")
        multi.options = [
            Option(text="2", is_correct=True),
            Option(text="3", is_correct=True),
            Option(text="4", is_correct=False),
        ]

        db.add_all([single, multi])
        db.flush()

        single_correct = next(option.id for option in single.options if option.is_correct)
        multi_correct = [option.id for option in multi.options if option.is_correct]

        db.commit()

        return {
            "single_question_id": single.id,
            "single_correct_option_id": single_correct,
            "multi_question_id": multi.id,
            "multi_correct_option_ids": multi_correct,
        }


@pytest.fixture()
def seeded_db(session_factory):
    return seed_questions(session_factory)


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


def test_list_exam_questions(client: TestClient, seeded_db: dict[str, object]):
    response = client.get("/exam")
    assert response.status_code == 200
    assert "Exam Questions" in response.text
    assert 'name="per_page"' in response.text


def test_start_exam_creates_attempt(
    client: TestClient, session_factory: sessionmaker, seeded_db: dict[str, object]
):
    response = client.get("/exam/start")
    assert response.status_code == 201
    assert "Complete the Exam" in response.text

    with session_factory() as db:
        attempts = db.query(ExamSession).all()
        assert len(attempts) == 1
        attempt = attempts[0]
        assert float(attempt.max_score or 0) == 2.0


def test_submit_exam_redirects_to_result(
    client: TestClient,
    session_factory: sessionmaker,
    seeded_db: dict[str, object],
):
    client.get("/exam/start")

    with session_factory() as db:
        attempt_id = db.query(ExamSession.id).first()[0]

    payload = {
        "attempt_id": attempt_id,
        "answers": [
            {
                "question_id": seeded_db["single_question_id"],
                "selected_option_ids": [seeded_db["single_correct_option_id"]],
            },
            {
                "question_id": seeded_db["multi_question_id"],
                "selected_option_ids": seeded_db["multi_correct_option_ids"],
            },
        ],
    }

    response = client.post("/exam/submit", json=payload, allow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].endswith(f"/exam/result/{attempt_id}")


def test_result_page_shows_score_and_pass_status(
    client: TestClient,
    session_factory: sessionmaker,
    seeded_db: dict[str, object],
):
    client.get("/exam/start")

    with session_factory() as db:
        attempt_id = db.query(ExamSession.id).first()[0]

    payload = {
        "attempt_id": attempt_id,
        "answers": [
            {
                "question_id": seeded_db["single_question_id"],
                "selected_option_ids": [seeded_db["single_correct_option_id"]],
            },
            {
                "question_id": seeded_db["multi_question_id"],
                "selected_option_ids": seeded_db["multi_correct_option_ids"],
            },
        ],
    }

    submit_response = client.post("/exam/submit", json=payload, allow_redirects=False)
    assert submit_response.status_code == 303

    result_response = client.get(f"/exam/result/{attempt_id}")
    assert result_response.status_code == 200
    assert "2.0 / 2.0" in result_response.text or "2 / 2" in result_response.text
    assert "100.0%" in result_response.text or "100%" in result_response.text
    assert ">Pass<" in result_response.text or "Pass" in result_response.text
