# Auspex deep research as a background job — spec

Status: built 16 Oct 2026 on bugfixing (canonical) and wileytest. See "As built" at the end.

## The problem

A deep research run lives inside one HTTP response. The browser POSTs to
`/api/auspex/research` and reads a Server-Sent Events stream for ten to twenty minutes while the
server plans, searches, reads batches of articles and writes the report. When that connection
closes for any reason, Starlette cancels the generator and the run dies without a log line.

Seen on wileytest on 16 Oct 2026:

- 12:43 run: another session restarted the service while the writer was streaming. nginx logged
  "upstream prematurely closed connection"; the report was lost.
- 14:40 run: the browser closed the connection at 14:46:30, six minutes in, with no page
  navigation around it. The server had just started relevance scoring. No synthesis or writer
  call ever happened and nothing was logged.

Two side effects of the same design: the restart gate (`scripts/restart_when_quiet.sh`) cannot
see a research run, because research writes no `auspex_messages` row and no `background_tasks`
row until the report is done; and on sites whose route predates 14 Oct the report was never saved
to the chat at all, so a reload lost it even after a successful run.

## What changes

The run becomes a server-side job. The HTTP response becomes a window onto it.

1. **`POST /api/auspex/research`** starts a job and returns the same SSE stream as before, so
   both existing browsers keep working unchanged. The first event is
   `{"stage": "job", "job_id": "<uuid>"}`. If the client goes away, only the stream stops; the
   job keeps running to the end and saves its report.
2. **`GET /api/auspex/research/jobs/{job_id}`** returns the job's status as JSON:
   `status` (pending, running, completed, failed, cancelled), `stage`, `message`, `progress`,
   `query`, `topic`, `chat_id`, timestamps, `error`, and `report` once completed. Only the user
   who started the job (or an admin) can read it.
3. **`GET /api/auspex/research/jobs/{job_id}/events`** is the same SSE stream, reattachable. It
   replays the stage events so far, then a single `{"stage": "writing", "chunk": "<text so
   far>"}` if the writer has started, then follows live.
4. **`GET /api/auspex/research/jobs?chat_id=N&active=1`** lists the caller's jobs, so a page
   that loads a chat with a run in progress can reattach.
5. **The report is saved to the chat** when `chat_id` is given: the question as a `user`
   message when the job starts, the report as an `assistant` message when it completes, both with
   `metadata.deep_research = true` and the job id. This already existed on canonical since 14 Oct
   and now runs inside the job, so it happens whether or not anyone is watching.
6. **A `background_tasks` row** named `deep_research` tracks the job (status, stage in
   `current_item`, progress, report length and chat message id in `result`). The restart gate's
   "jobs" signal therefore waits for research. After a restart the row is closed as failed with
   "Interrupted" by the existing startup reconciliation, so a browser polling the job sees a
   clean failure instead of waiting forever.

### Browser behaviour

`static/js/auspex-chat.js` (the floating chat on every Jinja page) and
`ui-next/src/shell/auspex/api.ts` (the Explore Auspex panel on sites with the new UI):

- Remember the `job_id` from the first event.
- If the stream ends without `done` or an `error` event and the user did not stop it, poll the
  status endpoint every three seconds until the job is terminal, then show the report or the
  error. A dropped connection no longer looks like a failed run.
- The floating chat also reattaches when a chat with a running job is opened: it shows the
  progress panel and follows `/events`.

### What does not change

- The research pipeline itself (`DeepResearchService.conduct_research`) and its event shapes.
- One run per user at a time is not enforced server-side; the browsers already refuse to start
  a second run while one is in progress on that page.
- Jobs live in process memory plus the `background_tasks` row. A job is not resumed after a
  restart; it is reported as interrupted and has to be run again.

## Event storage and memory

The writer streams the report in hundreds of small `chunk` events. The registry keeps them
as one growing string (`report_text`), not as events, and keeps the other events (at most 400)
for replay. Each live subscriber has its own `asyncio.Queue`; a slow or dead subscriber never
blocks the job because the queue is unbounded and the subscriber is dropped when its generator
closes. Finished jobs stay in memory for two hours, then only the `background_tasks` row and the
chat messages remain.

## Files

- `app/services/auspex_research_jobs.py` — the registry: `start`, `events`, `status`, `get`,
  `list_for`.
- `app/routes/auspex_routes.py` — the four endpoints above.
- `static/js/auspex-chat.js` — job id capture, poll-on-drop, reattach on chat load.
- `ui-next/src/shell/auspex/api.ts` — job id capture, poll-on-drop.
- `tests/test_auspex_research_jobs.py` — a fake research generator drives the registry: replay
  plus live tail, a subscriber leaving does not stop the job, failure path, chat save on
  completion, status after completion carries the report.

## As built (16 Oct 2026)

Commit bb9bfacb on bugfixing (branch fix/ingest-pipeline-spec), React bundle ac632296. Copied to wileytest the same day. Twelve tests (`tests/test_auspex_research_jobs.py`, `tests/test_auspex_research_routes.py`). Details, verification and propagation in `docs/changes.md` under 16 Oct 2026.

Differences from the text above: none in behaviour. Two things worth knowing: the `background_tasks` row is written directly through `facade.save_background_task`, not through `BackgroundTaskManager.run_task`, because the manager's three admission slots are shared with keyword checks, topic reports and forecast jobs and a 15-minute research run should neither wait for one nor hold one; and the floating chat used to swallow the job's own `error` event as a JSON-parse warning (the throw sat inside the parse `try`), which is fixed as part of the read-loop refactor.
