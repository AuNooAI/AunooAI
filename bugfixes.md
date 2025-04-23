## 2024‑06‑12 – Recent Feature & Bug‑Fix Summary

### ✨ New Features
- **Dynamic Prompt Templates**
  - Prompts now loaded from `data/prompts/script_templates` and selected by `mode` (conversation│bulletin) + `duration` (short│medium│long).
  - Place‑holders supported for `podcast_name`, `episode_title`, `host_name`, `guest_name`, `guest_title`.

- **Template CRUD API**
  - `GET /api/podcast_templates` – list.
  - `GET /api/podcast_templates/{name}` – fetch.
  - `POST /api/podcast_templates` – save / update.

- **Extended Script Generation**
  - `PodcastScriptRequest` adds `duration`, `host_name`, `guest_name`, `guest_title`.
  - Rich article metadata passed to the LLM.

- **Voice Assignment Logic**
  - Robust speaker parsing supports `[Speaker – Role]` **and** `**Speaker**: text`.
  - Host aliases `{host_name.lower(), "annie", "host"}`; guest voice chosen by id or randomised (excluding host voice).

- **TTS Pipeline Enhancements**
  - `clean_text()` removes stage directions and bold speaker labels before sending to ElevenLabs.
  - Long sections split into ≤ 2 500‑char chunks.

- **Database & Settings**
  - `settings_podcasts` table (renamed/migrated) stores default voices & show metadata.
  - `podcasts` table records transcript, status timestamps, and errors.

- **CLI Launcher** (`run.py`)
  - Executes `scripts/setup.py` (FFmpeg check) then starts Uvicorn with logging.

### 🐞 Bug Fixes
- Fixed issue where host and guest shared the same voice by improving speaker detection & mapping.
- Removed lingering `**Speaker**` labels from TTS input to prevent names being spoken aloud.
- Added fallback when no speaker markers detected – script voiced entirely by host with warning.
- Improved error handling and DB status updates during TTS generation failures.
- Corrected API key validation messages for ElevenLabs.

### ⚠️ Outstanding Linter Tasks
- Many long lines & unused imports in `app/routes/podcast_routes.py`.
- Duplicate `list_podcasts()` route definition.
- Will be addressed in an upcoming refactor pass focused on linting & style compliance.
