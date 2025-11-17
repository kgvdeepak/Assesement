from __future__ import annotations

import json
from datetime import datetime
from typing import Iterable, List, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship
from sqlalchemy.types import TypeDecorator


class Base(DeclarativeBase):
    """Base declarative class for all models."""


class JSONIntList(TypeDecorator):
    """Persist lists of ints as JSON strings for SQLite compatibility."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: Optional[Iterable[int]], dialect):  # type: ignore[override]
        if value is None:
            return None
        coerced = [int(v) for v in value]
        return json.dumps(coerced)

    def process_result_value(self, value: Optional[str], dialect):  # type: ignore[override]
        if value is None:
            return []
        try:
            raw_list = json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return []
        return [int(v) for v in raw_list]


class Question(Base):
    __tablename__ = "questions"
    __table_args__ = (
        CheckConstraint("type in ('single', 'multi')", name="ck_question_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    text: Mapped[str] = mapped_column(String(500), nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)

    options: Mapped[List[Option]] = relationship(
        "Option",
        back_populates="question",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def get_options(self, session: Session) -> List[Option]:
        """Return the options for this question using the provided session."""
        return (
            session.query(Option)
            .filter(Option.question_id == self.id)
            .order_by(Option.id.asc())
            .all()
        )


class Option(Base):
    __tablename__ = "options"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"), nullable=False)
    text: Mapped[str] = mapped_column(String(500), nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    question: Mapped[Question] = relationship("Question", back_populates="options")


class ExamSession(Base):
    __tablename__ = "exam_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), default=datetime.utcnow, nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=False), nullable=True)
    total_score: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    max_score: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    passed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    responses: Mapped[List[UserResponse]] = relationship(
        "UserResponse",
        back_populates="exam_session",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class UserResponse(Base):
    __tablename__ = "user_responses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    exam_session_id: Mapped[int] = mapped_column(ForeignKey("exam_sessions.id", ondelete="CASCADE"), nullable=False)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"), nullable=False)
    selected_option_ids: Mapped[List[int]] = mapped_column(JSONIntList, nullable=False, default=list)

    exam_session: Mapped[ExamSession] = relationship("ExamSession", back_populates="responses")
    question: Mapped[Question] = relationship("Question")

    @staticmethod
    def coerce_option_ids(option_ids: Iterable[int]) -> List[int]:
        """Ensure option identifiers are stored as ints."""
        return [int(option_id) for option_id in option_ids]

    def set_selected_option_ids(self, option_ids: Iterable[int]) -> None:
        """Store the provided option identifiers after int conversion."""
        self.selected_option_ids = self.coerce_option_ids(option_ids)


def create_all(engine) -> None:
    """Create database tables for all models."""
    Base.metadata.create_all(bind=engine)
