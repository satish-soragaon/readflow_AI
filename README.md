# ReadFlow AI

A Flask-based reading productivity app with RSVP speed reading, document management, AI study tools, and reading analytics.

## Features

- **RSVP Speed Reader** — word, chunk, sentence, and line modes with 100–1000 WPM control and smart pauses
- **Document Library** — upload PDF, DOCX, TXT, JPG, PNG, WEBP or paste text directly
- **OCR Support** — scanned PDF and image text extraction via EasyOCR + Poppler
- **Annotations** — bookmarks, notes, and highlights per document, saved without page reload
- **Reading Analytics** — session history, streak, total words read, average/peak WPM, 7-day chart
- **AI Study Tools** — summary, key takeaways, flashcards, quiz, study notes, and vocabulary (pluggable: Anthropic Claude, OpenAI, or disabled)
- **Global Search** — full-text search across documents, notes, and reading history (SQLite FTS5)
- **Preferences** — theme (dark/light), font size, default WPM, reading mode, smart pauses

## Tech Stack

- **Backend:** Flask 3.0, SQLite (WAL + FTS5), Flask-WTF (CSRF), Flask-Limiter
- **Document Processing:** pdfplumber, python-docx, EasyOCR, pdf2image
- **AI:** Anthropic Claude / OpenAI (pluggable via `ai_providers.py`)
- **Deployment:** Gunicorn, Docker, Render, Railway

## Quick Start

```bash
cd readflow-ai
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env   # add your SECRET_KEY and optional AI keys
python app.py
```

Open `http://127.0.0.1:5000`.

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | — | Required. Long random string for session security |
| `DATABASE_PATH` | `readflow.db` | SQLite database file path |
| `UPLOAD_DIR` | `uploads` | Directory for uploaded documents |
| `AI_PROVIDER` | `disabled` | `anthropic`, `openai`, or `disabled` |
| `ANTHROPIC_API_KEY` | — | Required if `AI_PROVIDER=anthropic` |
| `OPENAI_API_KEY` | — | Required if `AI_PROVIDER=openai` |

## Docker

```bash
docker build -t readflow-ai ./readflow-ai
docker run -p 8000:8000 \
  -e SECRET_KEY=your-secret-key \
  -v readflow_data:/data \
  readflow-ai
```

Open `http://127.0.0.1:8000`.

## Project Structure

```
readflow-ai/
├── app.py              # Flask factory, blueprint registration
├── config.py           # Environment-driven config
├── db.py               # SQLite schema, FTS5, migrations
├── auth.py             # Session auth, login_required decorator
├── ai_providers.py     # Pluggable AI provider (Anthropic / OpenAI)
├── document_utils.py   # Upload validation and text extraction dispatch
├── blueprints/         # Route handlers (library, reader, AI, search, etc.)
├── services/           # PDF, DOCX, image, OCR extraction services
├── templates/          # Jinja2 HTML templates
└── static/             # CSS and JavaScript (reader.js, upload.js)
```

## Deployment

See [`readflow-ai/README.md`](readflow-ai/README.md) for full Render, Railway, and Docker deployment guides including persistent storage setup and production checklist.
