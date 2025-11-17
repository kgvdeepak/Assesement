from __future__ import annotations

from typing import Dict, Iterable, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class OptionOut(BaseModel):
    id: int
    text: str
    is_correct: bool = Field(..., description="Indicates whether the option is correct.")

    model_config = ConfigDict(from_attributes=True)


class QuestionOut(BaseModel):
    id: int
    text: str
    type: Literal["single", "multi"]
    options: List[OptionOut]

    model_config = ConfigDict(from_attributes=True)

    @field_validator("options")
    def ensure_options_present(cls, value: List[OptionOut]) -> List[OptionOut]:
        if not value:
            raise ValueError("Each question must expose at least one option.")
        return value


class AnswerSelection(BaseModel):
    question_id: int
    selected_option_ids: List[int]

    @field_validator("selected_option_ids", mode="before")
    def coerce_ids(cls, value) -> List[int]:
        if isinstance(value, str):
            tokens = [token.strip() for token in value.split(",") if token.strip()]
            return [int(token) for token in tokens]
        if isinstance(value, Iterable):
            return [int(token) for token in value]
        raise TypeError("selected_option_ids must be a list of option identifiers.")

    @field_validator("selected_option_ids")
    def validate_ids(cls, value: List[int]) -> List[int]:
        if not value:
            raise ValueError("At least one option must be selected.")
        if len(set(value)) != len(value):
            raise ValueError("Duplicate option ids are not allowed.")
        return value


class ExamSubmissionIn(BaseModel):
    attempt_id: Optional[int] = Field(default=None, description="Client-supplied attempt correlation id.")
    answers: List[AnswerSelection]
    question_type_map: Optional[Dict[int, Literal["single", "multi"]]] = Field(
        default=None,
        exclude=True,
        description="Internal use only: map question id to its type for validation.",
    )

    model_config = ConfigDict(extra="forbid")

    @field_validator("attempt_id", mode="before")
    def coerce_attempt_id(cls, value):
        if value in (None, ""):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            if not value.strip():
                return None
            try:
                return int(value)
            except ValueError as exc:  # pragma: no cover - defensive guard.
                raise ValueError("Attempt id must be an integer.") from exc
        raise TypeError("Attempt id must be an integer value.")

    @field_validator("answers")
    def ensure_unique_questions(cls, answers: List[AnswerSelection]) -> List[AnswerSelection]:
        seen = set()
        for answer in answers:
            if answer.question_id in seen:
                raise ValueError("Duplicate answers for the same question are not allowed.")
            seen.add(answer.question_id)
        return answers

    @model_validator(mode="after")
    def enforce_question_types(cls, model: "ExamSubmissionIn") -> "ExamSubmissionIn":
        question_types: Dict[int, Literal["single", "multi"]] = model.question_type_map or {}
        for answer in model.answers:
            q_type = question_types.get(answer.question_id)
            if not q_type:
                continue  # Question type absent means validation happens downstream.
            if q_type == "single" and len(answer.selected_option_ids) != 1:
                raise ValueError(f"Question {answer.question_id} accepts a single answer.")
            if q_type == "multi" and len(answer.selected_option_ids) < 1:
                raise ValueError(f"Question {answer.question_id} requires at least one selection.")
        return model


class QuestionResult(BaseModel):
    question_id: int
    selected_option_ids: List[int]
    correct: bool
    score: Optional[float] = None


class ResultOut(BaseModel):
    score: float
    max_score: float
    passed: bool
    breakdown: List[QuestionResult]

    model_config = ConfigDict(from_attributes=True)
