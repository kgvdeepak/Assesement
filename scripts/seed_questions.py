from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, Iterable, Tuple

from sqlalchemy.orm import Session, selectinload

from app.db import SessionLocal, engine
from app.models import Option, Question, create_all

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_FILE = ROOT_DIR / "data" / "questions.json"


def load_spec(path: Path) -> Iterable[Dict]:
    if not path.exists():
        raise FileNotFoundError(f"Questions seed file not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, list):
        raise ValueError("Seed file must be a JSON array of question objects.")
    return payload


def normalise_question_type(raw_type: str) -> str:
    normalised = (raw_type or "").strip().lower()
    if normalised not in {"single", "multi"}:
        raise ValueError(f"Unsupported question type: {raw_type}")
    return normalised


def sync_options(session: Session, question: Question, option_specs: Iterable[Dict]) -> Tuple[int, int, int]:
    existing_by_text = {opt.text.strip(): opt for opt in question.options}
    seen_texts = set()

    inserted = updated = removed = 0

    for option_spec in option_specs:
        text = option_spec.get("text", "").strip()
        if not text:
            raise ValueError(f"Option text missing for question '{question.text}'.")
        is_correct = bool(option_spec.get("is_correct", False))
        seen_texts.add(text)

        option = existing_by_text.get(text)
        if option is None:
            question.options.append(Option(text=text, is_correct=is_correct))
            inserted += 1
            continue

        if option.is_correct != is_correct:
            option.is_correct = is_correct
            updated += 1

    for text, option in existing_by_text.items():
        if text not in seen_texts:
            session.delete(option)
            removed += 1

    return inserted, updated, removed


def upsert_question(session: Session, spec: Dict) -> Tuple[bool, bool, Tuple[int, int, int]]:
    text = spec.get("text", "").strip()
    if not text:
        raise ValueError("Question text is required.")
    question_type = normalise_question_type(spec.get("type", ""))
    options_spec = spec.get("options", [])
    if not options_spec:
        raise ValueError(f"Question '{text}' must define at least one option.")

    question = (
        session.query(Question)
        .options(selectinload(Question.options))
        .filter(Question.text == text)
        .one_or_none()
    )

    if question is None:
        question = Question(text=text, type=question_type)
        for option_spec in options_spec:
            option_text = option_spec.get("text", "").strip()
            if not option_text:
                raise ValueError(f"Option text missing for question '{text}'.")
            question.options.append(
                Option(
                    text=option_text,
                    is_correct=bool(option_spec.get("is_correct", False)),
                )
            )
        session.add(question)
        return True, True, (len(question.options), 0, 0)

    changed = False
    if question.type != question_type:
        question.type = question_type
        changed = True

    option_counts = sync_options(session, question, options_spec)
    if any(option_counts):
        changed = True

    return False, changed, option_counts


def main() -> int:
    create_all(engine)
    try:
        specs = load_spec(DATA_FILE)
    except (FileNotFoundError, ValueError) as exc:
        print(f"[seed] {exc}")
        return 1

    questions_inserted = questions_updated = 0
    options_inserted = options_updated = options_removed = 0

    with SessionLocal() as session:
        try:
            for spec in specs:
                inserted, changed, option_counts = upsert_question(session, spec)
                opt_ins, opt_upd, opt_del = option_counts

                options_inserted += opt_ins
                options_updated += opt_upd
                options_removed += opt_del

                if inserted:
                    questions_inserted += 1
                elif changed:
                    questions_updated += 1

            session.commit()
        except Exception:
            session.rollback()
            raise

    print(
        "[seed] questions inserted: {qi}, updated: {qu}; options inserted: {oi}, "
        "updated: {ou}, removed: {od}".format(
            qi=questions_inserted,
            qu=questions_updated,
            oi=options_inserted,
            ou=options_updated,
            od=options_removed,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
