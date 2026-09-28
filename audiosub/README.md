# AudioSub AI — MVP

Upload audio or video → speech recognition → timed original subtitles →
AI translation → online review/editing → export SRT / VTT / TXT (incl. bilingual SRT).

```
audiosub/
  backend/    Python · FastAPI · SQLAlchemy · FFmpeg · faster-whisper · Claude
  frontend/   Next.js · React · TypeScript · Tailwind CSS
```

## Core design: independent modules

```
Upload ─► Audio (FFmpeg) ─► ASR ─► Transcript ─► Segmentation ─► Segments ─► Translation ─► Export
          audio.wav         (raw, never edited)                (editable)   (editable)     (on demand)
```

Each stage stores its own output, so any stage can be re-run without the ones
before it:

| Change                                   | What re-runs                                   |
|------------------------------------------|------------------------------------------------|
| Target language / domain / glossary      | Translation only (`POST /api/projects/{id}/translate`) — **never ASR** |
| Edit original text / timings             | Nothing (saved per segment)                    |
| Re-segment from transcript               | Segmentation only (`/resegment`)               |
| A step failed (e.g. translation)         | Retry resumes from the failed step (`/retry`)  |

ASR and translation are behind provider interfaces
(`app/services/asr/`, `app/services/translation/`) and are selected with
`ASR_PROVIDER` / `TRANSLATION_PROVIDER`, so either model can be swapped
without touching the rest.

## Features (MVP scope)

- **Files:** MP3, WAV, M4A, MP4 (video audio is extracted with FFmpeg, resampled to 16 kHz mono and loudness-normalised). MOV/MKV/AAC/FLAC are one line away in `app/services/media.py`.
- **Languages:** source Auto Detect / Chinese / English / Portuguese; target Chinese / English / **Português de Portugal (`pt-PT`)**. Languages live in a registry (`app/languages.py`) — add Spanish, French… by adding an entry. Any Portuguese target is always stored and translated as `pt-PT`, with explicit European-Portuguese rules in the prompt (e.g. "estou a fazer", *equipa*, *ecrã*, *telemóvel*, *facto*).
- **Subtitle mode:** Original Only / Translation Only / Bilingual.
- **Domains:** General, Business, Accounting & Tax (keeps IVA, IRC, IRS, AT, SS, OCC, NIF… untranslated, uses Portuguese tax terminology), Legal.
- **Glossary:** global or per-project terms, optionally per target language. Priority: glossary > domain terminology > normal translation.
- **Context-aware translation:** subtitles are sent in batches (default 15 lines) plus 3 lines of read-only context on each side, and mapped back by segment id so timings never change. Lines the model skips are retried once.
- **Segmentation:** rule-based — breaks on sentence end and pauses, max 2 lines × 42 chars (18 for CJK), max 7 s, splits long runs at clause punctuation, min display time, no overlaps. Uses ASR word timestamps when available.
- **Processing page:** per-step status (✓ / ● / ○ / ✕), progress %, detected language, duration, segment count; failed steps show the error and a *Retry* button that keeps completed work.
- **Editor:** audio/video player with subtitle overlay, zoomable timeline, click a subtitle to jump & play (optional *stop at end*), current subtitle highlighted and followed, edit original / translation / start / end (or set to playhead), split (at playhead or middle), merge, add, delete, multi-select (shift-click), *Retranslate* / *Retranslate Selected* / *Retranslate All*, change target language / domain. **Autosave** (debounced, retried on failure, warns before leaving with unsaved edits). Low-confidence ASR lines are marked.
- **Export:** Original / Translated / Bilingual SRT (original-first or translation-first), Original / Translated VTT, TXT transcript, with preview.
- **Project history:** recent projects on the home page.

## Running locally

Requirements: Python 3.11+, Node 20+, FFmpeg on `PATH`.

### Backend

```bash
cd audiosub/backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # set ANTHROPIC_API_KEY, pick providers/database
uvicorn app.main:app --reload --port 8000
```

- Default database is SQLite (`./data/audiosub.db`) so it runs with no setup.
  For PostgreSQL: `docker compose up -d` in `audiosub/` and set
  `DATABASE_URL=postgresql+psycopg2://audiosub:audiosub@localhost:5432/audiosub`.
- **ASR:** `ASR_PROVIDER=faster_whisper` runs Whisper locally (`WHISPER_MODEL=large-v3`
  for best accuracy, `small`/`medium` for speed; downloads on first use; a GPU is
  strongly recommended for long files). `ASR_PROVIDER=openai` uses the hosted
  Whisper API (`pip install openai`, `OPENAI_API_KEY`; 25 MB upload limit).
  `ASR_PROVIDER=mock` returns a fixed sample transcript for UI work.
- **Translation:** `TRANSLATION_PROVIDER=claude` with `ANTHROPIC_API_KEY`
  (model `TRANSLATION_MODEL`, default `claude-opus-5`; server-side refusal
  fallback is enabled). `TRANSLATION_PROVIDER=mock` prefixes lines with the
  target language code.
- **Offline translation (no API key):** install [Ollama](https://ollama.com)
  (`winget install Ollama.Ollama` on Windows), run `ollama pull qwen2.5:7b`,
  and set `TRANSLATION_PROVIDER=ollama` (`OLLAMA_MODEL` to change the model;
  `qwen2.5:3b` for low-RAM machines, `qwen2.5:14b` for better quality).
  Free and private, but slower on CPU and lower quality than Claude; the same
  prompt (PT-PT rules, domain, glossary) is used, but small models follow it
  less reliably. Lower `TRANSLATION_BATCH_SIZE` (e.g. 8) if batches time out
  or lines go missing.
- **Storage:** local files under `./data/storage` by default. For production
  set `STORAGE_BACKEND=s3`, `S3_BUCKET`, and for Cloudflare R2 `S3_ENDPOINT_URL`
  (`pip install boto3`). Only storage keys are kept in the database.
- API docs: http://localhost:8000/docs

### Frontend

```bash
cd audiosub/frontend
npm install
cp .env.example .env.local    # NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev                   # http://localhost:3000
```

### Tests

```bash
cd audiosub/backend
pip install -r requirements-dev.txt
pytest
```

Tests use the mock ASR/translation providers and real FFmpeg (a bundled
binary from `imageio-ffmpeg` is used when `ffmpeg` is not installed). They
cover segmentation, export formats, context batching and glossary priority,
the Claude request shape, and the full API flow: upload MP4 → process →
edit / split / merge / add / delete → retranslate without ASR → export, plus
failure-and-retry of the translation step.

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/meta` | Languages, domains, modes, formats (UI options) |
| POST | `/api/projects` | Create project (source/target language, domain, subtitle mode) |
| GET | `/api/projects` | Recent projects |
| GET / PATCH / DELETE | `/api/projects/{id}` | Read / change settings / delete |
| POST | `/api/projects/{id}/upload` | Upload file (validated, probed for duration/audio) |
| POST | `/api/projects/{id}/process` | Generate Subtitle — full pipeline in the background |
| POST | `/api/projects/{id}/retry` | Resume from the failed step |
| POST | `/api/projects/{id}/transcribe` | Audio + ASR + segmentation only |
| POST | `/api/projects/{id}/resegment` | Rebuild subtitles from the stored transcript |
| POST | `/api/projects/{id}/translate` | Translation only; `segment_ids` for selected lines (sync) |
| GET | `/api/projects/{id}/media` | Stream the uploaded media (HTTP range) |
| GET / POST | `/api/projects/{id}/segments` | List / add subtitles |
| POST | `/api/projects/{id}/segments/merge` | Merge subtitles |
| PATCH / DELETE | `/api/segments/{id}` | Edit / delete a subtitle |
| POST | `/api/segments/{id}/split` | Split a subtitle |
| POST (GET) | `/api/projects/{id}/export` | `format` srt/vtt/txt, `content` original/translation/bilingual, `order` |
| GET/POST/PUT/DELETE | `/api/glossary` | Glossary terms |
| POST | `/api/transcribe` | Standalone ASR service: `{file_id, source_language}` → transcript + segments |
| POST | `/api/translate` | Standalone translation service: `{project_id, target_language, domain, glossary}` |

Project status: `CREATED → UPLOADED → PROCESSING_AUDIO → TRANSCRIBING → TRANSLATING → READY` (or `FAILED`, with per-step status in `steps`).

## Data model

- **Project** — id, user_id, filename, file_type, file_size, file_key, audio_key, duration, source_language, detected_language, target_language, domain, subtitle_mode, status, steps, progress, error_message, created_at, updated_at
- **Transcript** — raw ASR output (segments with word timestamps and confidence), provider, model, language
- **Segment** — id, project_id, segment_index, start_time, end_time, original_text, translated_text, translation_language, speaker (reserved for speaker detection), confidence, created_at, updated_at
- **GlossaryTerm** — term, translation, target_language, project_id (NULL = global), note

Tables are created on startup (`Base.metadata.create_all`); add Alembic when the schema starts changing in production.

## Known limits of this MVP

- Background jobs run in an in-process thread pool (2 workers). Jobs interrupted by a restart are marked failed and can be retried. For production, move `pipeline._run` to a real queue (RQ/Celery/Arq) — the step functions are already queue-ready.
- No authentication yet (`user_id` column is in place).
- Long files with the hosted OpenAI ASR need chunking (25 MB API limit); faster-whisper has no such limit.
