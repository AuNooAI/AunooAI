# Scenario Builder

The **Scenario Builder** is an interactive web interface used to compose analytical *Scenarios* from reusable **Building-Blocks**.
A Scenario combines a set of Building-Blocks with a short topic description and is later used to generate structured prompts for an LLM-powered pipeline.

This document explains how the tool works, how to use it, and how to extend it.

---

## 1  Key Concepts

| Concept | Description |
|---------|-------------|
| **Building-Block** | A small, single-purpose analysis step such as *sentiment*, *categorisation* or *summarisation*. Each block stores: `name`, `kind`, `prompt` and an optional list of `options`. |
| **Scenario** | A named collection of Building-Blocks plus a markdown *description* (`topic`). Saving a Scenario automatically creates a dedicated articles table so that the resulting analyses remain isolated. |

---

## 2  User Interface Walk-through

Open the builder at `http://localhost:8000/scenario-editor` (or `/scenario_editor`).

1. **Available Building-Blocks** – left column
   * Lists all blocks stored in the database.
   * Click to select; double-click to edit; ♻︎ to refresh; ✕ to delete.
2. **Selected Blocks** – right column
   * Shows the current selection. Drag-and-drop ordering is preserved by selection order.
   * Click ✕ to remove a block from the selection.
3. **Scenario Form** – below the selected blocks
   * `name` – unique scenario identifier.
   * `topic` – markdown description used during prompt generation.
4. **Saved Scenarios** – collapsible accordion
   * Click a scenario to load it back into the editor.
   * ✕ deletes the scenario (including its article table).
5. **Generate Prompt** button – active once a saved scenario is loaded
   * Produces *system* and *user* prompts based on the scenario definition.

Both block columns are vertically scroll-able (`max-height: calc(100vh - 220px)`) so the Saved Scenarios area is never overlapped.

---

## 3  Typical Workflow

```text
Create or refresh Building-Blocks  →  Select blocks  →  Fill in Scenario details  →  Save  →  (re-)Load Scenario  →  Generate Prompt
```

1. **Create blocks** – press *New* or duplicate an existing block.
2. **Select blocks** – click each card in *Available Building-Blocks*; order matters.
3. **Fill scenario form** – provide a descriptive name and topic.
4. **Save Scenario** – data is persisted and the related article table is created.
5. **Generate Prompt** – use the result directly in the LLM chain.

---

## 4  Block Kinds & Defaults

| Kind | Default Prompt | Default Options |
|------|----------------|-----------------|
| `categorization` | *Classify the article into one of the provided categories…* | `Other` is always appended. |
| `sentiment` | *Determine whether the article sentiment is Positive…* | `Positive`, `Negative`, `Neutral` |
| `relationship` | *Does the article act as a blocker, catalyst…* | – |
| `weighting` | *On a scale of 0–1 how objective is this article?* | – |
| `classification` | *Assign the article to one of the listed classes…* | Must specify ≥ 2 options. |
| `summarization` | *Summarise the article in three concise sentences…* | – |
| `keywords` | *Generate 3–5 relevant keyword tags…* | – |

`templates/scenario_editor.html` holds the help-text tooltips and hard-coded defaults.

---

## 5  REST API Reference

All endpoints are prefixed with `/api` (see `app/routes/scenario_routes.py`).

### Building-Blocks

* `POST  /building_blocks` – create (`BuildingBlockCreate`)
* `GET   /building_blocks` – list all
* `PATCH /building_blocks/{id}` – partial update (`BuildingBlockUpdate`)
* `DELETE /building_blocks/{id}` – delete

### Scenarios

* `POST  /scenarios` – create (`ScenarioCreate`)
* `GET   /scenarios` – list all
* `GET   /scenarios/{id}` – details
* `PATCH /scenarios/{id}` – partial update (`ScenarioUpdate`)
* `DELETE /scenarios/{id}` – delete (and article table)
* `GET   /scenarios/{id}/prompt` – compose system & user prompts

---

## 6  Developer Notes

### 6.1  Running Locally

```bash
# 1. Install dependencies
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Start the application (SQLite default)
uvicorn run:app --reload

# 3. Open the Scenario Builder
open http://localhost:8000/scenario-editor
```

### 6.2  Database

`app/database.py` exposes `get_database_instance()` which is responsible for migrations and table creation. A new table `articles_scenario_{id}` is created for every saved scenario.

### 6.3  Extending

1. **Add a new block kind**
   * Update the `kinds` array and `helpTexts` in `templates/scenario_editor.html`.
   * Provide default prompts / options as needed.
   * Handle kind-specific validation in `app/services/ontology_service.py` → `create_building_block()`.
2. **Change prompt placeholders** – Edit `compose_prompt()` inside `ontology_service.py`.
3. **UI styling** – Tweak `static/css/scenario_builder.css`.

---

## 7  Known Limitations

* No drag-and-drop re-ordering inside *Selected Blocks* – order is determined by selection sequence.
* Deleting a Building-Block that is already linked to a Scenario is blocked at the database layer.
* Placeholders (`{categories}`, `{future_signals}` …) rely on `config/config.json`; ensure topics are up-to-date.

---

## 8  Credits

Originally developed for the *AuNoo* strategic foresight platform.
Contributions are welcome – open a PR or file an issue. 