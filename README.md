# Exam Workshop

Interactive exam platform built with FastAPI, SQLAlchemy, and Jinja2 templates. Use it to manage question banks, run timed exams, and surface detailed scoring to candidates.

## Product Backlog

- **Epic: Visitor Discovery**
	- As an anonymous user I can view a paginated list of exam questions.
- **Epic: Candidate Journey**
	- As a candidate I can start an exam and receive a unique attempt id.
	- As a candidate I can submit my answers and see pass/fail.
- **Epic: Content Operations**
	- As an admin I can seed questions from JSON.

These stories are intentionally lightweight so they can be split into sprint-sized tasks.

## Local Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt
python scripts/seed_questions.py
uvicorn main:app --reload
```

The seed script loads sample questions into the SQLite database before you start the development server.

## Run Tests

```powershell
pytest
```

Add `-k` or individual file paths to narrow the scope when iterating on a specific flow.
