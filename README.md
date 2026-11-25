# EduCite

EduCite is a locally running FastAPI/RAG application that verifies student claims against teacher-supplied material.

## Installation

```bat
cd educite
py -3.11 -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
copy .env.example .env
```

Install and start Ollama, then:

```bat
ollama pull qwen2.5:3b
ollama pull nomic-embed-text
```

Seed demo users and launch:

```bat
python -m auth.seed
uvicorn main:app --reload
```

Open `http://127.0.0.1:8000/login`.
New students can select **Create a student account** on the login page. Teacher accounts remain administrator-created.

## Demo credentials

Demo-only credentials are listed here and nowhere on the login page:

- Teacher: `teacher@educite.local` / `TeacherDemo!2026`
- Students: `aarav@educite.local`, `mina@educite.local`, or `leo@educite.local` / `StudentDemo!2026`

## Workflow

1. Teacher uploads PDF, DOCX, PPTX, or TXT reading material.
2. The document is extracted, chunked, embedded, and indexed.
3. Teacher creates a published assignment and generates/edits key points.
4. Student submits an answer. The Ollama pipeline extracts claims, retrieves evidence, verifies claims and computes AI-suggested marks.
5. Teacher reviews, overrides if needed, and releases the result.
6. Student views and exports the released report.

## Tests

```bat
pytest -q
```

## Known limitations

- OCR is not implemented.
- Legacy `.ppt` and `.doc` files are rejected.
- DOCX and TXT content has no reliable page number.
- Ollama must be running and both models must be installed.
- Document status refreshes automatically while embedding/indexing is in progress. If Ollama times out, the document shows a failure reason and can be re-indexed after Ollama is ready.
