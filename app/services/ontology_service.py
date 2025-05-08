"""Service helpers for Ontological Building Blocks and Scenarios."""

from __future__ import annotations

import logging
import sqlite3
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status

from app.database import get_database_instance

logger = logging.getLogger(__name__)

# Two blank lines before the first helper to satisfy PEP8

db = get_database_instance()

# ---------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------

def _encode_options(options: Optional[List[str]]) -> Optional[str]:
    import json
    return json.dumps(options) if options else None


def _decode_options(raw: Optional[str]) -> Optional[List[str]]:
    import json
    if raw:
        try:
            return json.loads(raw)
        except Exception:  # pragma: no cover – defensive
            logger.warning("Could not decode options JSON: %s", raw)
    return None


def create_building_block(
    name: str,
    kind: str,
    prompt: str,
    options: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Insert a new building block (name must be unique, case-insensitive)."""

    name = name.strip()
    if not name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Name must not be empty",
        )

    with db.get_connection() as conn:
        cursor = conn.cursor()
        try:
            # Kind-specific default/validation -----------------------------------
            if kind.lower() == "categorization":
                if options is None:
                    options = ["Other"]
                elif "Other" not in options:
                    options.append("Other")

            if kind.lower() == "classification":
                if not options or len(options) < 2:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Classification blocks require at least two options",
                    )

            if kind.lower() == "sentiment" and (not options):
                options = ["Positive", "Negative", "Neutral"]

            insert_sql = (
                "INSERT INTO building_blocks "
                "(name, kind, prompt, options) "
                "VALUES (?,?,?,?)"
            )
            cursor.execute(
                insert_sql,
                (name, kind, prompt, _encode_options(options)),
            )
            conn.commit()
        except sqlite3.IntegrityError as exc:
            logger.error(
                "Integrity error inserting building block: %s", exc,
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Building block already exists",
            ) from exc

        block_id = cursor.lastrowid
        cursor.execute("SELECT * FROM building_blocks WHERE id = ?", (block_id,))
        row = cursor.fetchone()

        # Convert row to dict
        block = dict(zip([col[0] for col in cursor.description], row))
        block["options"] = _decode_options(block.get("options"))
        return block

def list_building_blocks() -> List[Dict[str, Any]]:
    """Return all building blocks ordered by creation time (desc)."""

    with db.get_connection() as conn:
        conn.row_factory = sqlite3.Row  # type: ignore
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM building_blocks ORDER BY created_at DESC",
        )
        blocks = [dict(row) for row in cursor.fetchall()]
        for blk in blocks:
            blk["options"] = _decode_options(blk.get("options"))
        return blocks

# ---------------------------------------------------------------------
# Scenario helpers
# ---------------------------------------------------------------------

def create_scenario(name: str, topic: str, block_ids: List[int]) -> Dict[str, Any]:
    """Create a scenario, link blocks, then create its dedicated articles table."""

    name = name.strip()

    with db.get_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO scenarios (name, topic) VALUES (?, ?)",
                (name, topic),
            )
            scenario_id = cursor.lastrowid

            table_name = f"articles_scenario_{scenario_id}"
            cursor.execute(
                "UPDATE scenarios SET article_table = ? WHERE id = ?",
                (table_name, scenario_id),
            )

            # Link selected building blocks
            insert_sql = (
                "INSERT INTO scenario_blocks (scenario_id, building_block_id) "
                "VALUES (?, ?)"
            )
            for bid in block_ids:
                cursor.execute(insert_sql, (scenario_id, bid))

            conn.commit()
        except Exception as exc:
            conn.rollback()
            logger.error(
                "Error creating scenario: %s", exc,
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Could not create scenario",
            ) from exc

    # Get names of blocks for table columns --------------------------------
    with db.get_connection() as conn:
        cursor = conn.cursor()
        placeholder = ",".join(["?"] * len(block_ids))
        query = (
            "SELECT name FROM building_blocks WHERE id IN ("
            f"{placeholder})"
        )
        cursor.execute(query, block_ids)
        block_names = [row[0] for row in cursor.fetchall()]

    # Create the dedicated articles table ----------------------------------
    db.create_custom_articles_table(table_name, block_names)

    # Return the freshly created scenario ----------------------------------
    with db.get_connection() as conn:
        conn.row_factory = sqlite3.Row  # type: ignore
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM scenarios WHERE id = ?", (scenario_id,))
        row = cursor.fetchone()

    scenario = dict(row)

    # attach block ids
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT building_block_id FROM scenario_blocks WHERE scenario_id = ?",
            (scenario_id,),
        )
        scenario["block_ids"] = [r[0] for r in cursor.fetchall()]

    return scenario

def get_scenario(scenario_id: int) -> Dict[str, Any]:
    """Fetch a scenario by id."""

    with db.get_connection() as conn:
        conn.row_factory = sqlite3.Row  # type: ignore
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM scenarios WHERE id = ?", (scenario_id,))
        row = cursor.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Scenario not found")

    scenario = dict(row)

    # attach block ids
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT building_block_id FROM scenario_blocks WHERE scenario_id = ?",
            (scenario_id,),
        )
        scenario["block_ids"] = [r[0] for r in cursor.fetchall()]

    return scenario

def list_scenarios() -> List[Dict[str, Any]]:
    """Return all scenarios."""

    with db.get_connection() as conn:
        conn.row_factory = sqlite3.Row  # type: ignore
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM scenarios ORDER BY created_at DESC")
        return [dict(row) for row in cursor.fetchall()]

# ---------------------------------------------------------------------
# Scenario update helper
# ---------------------------------------------------------------------

def update_scenario(
    scenario_id: int,
    name: Optional[str] = None,
    topic: Optional[str] = None,
    block_ids: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """Partial update of a scenario."""

    with db.get_connection() as conn:
        cursor = conn.cursor()

        if name is not None:
            cursor.execute(
                "UPDATE scenarios SET name = ? WHERE id = ?",
                (name.strip(), scenario_id),
            )

        if topic is not None:
            cursor.execute(
                "UPDATE scenarios SET topic = ? WHERE id = ?",
                (topic.strip(), scenario_id),
            )

        if block_ids is not None:
            cursor.execute("DELETE FROM scenario_blocks WHERE scenario_id = ?", (scenario_id,))
            for bid in block_ids:
                cursor.execute(
                    "INSERT INTO scenario_blocks (scenario_id, building_block_id) VALUES (?, ?)",
                    (scenario_id, bid),
                )

        if cursor.rowcount == 0 and name is None and topic is None and block_ids is None:
            raise HTTPException(status_code=400, detail="Nothing to update")

        conn.commit()

    return get_scenario(scenario_id)

# ---------------------------------------------------------------------
# Delete Scenario helper (top-level)
# ---------------------------------------------------------------------

def delete_scenario(scenario_id: int) -> Dict[str, Any]:
    """Remove a scenario, its links and dedicated article table."""

    # Fetch article table name (if any)
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT article_table FROM scenarios WHERE id = ?",
            (scenario_id,),
        )
        row = cursor.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Scenario not found")

    article_table: Optional[str] = row[0]

    # Drop dedicated articles table (ignore errors)
    if article_table and db.table_exists(article_table):
        try:
            with db.get_connection() as conn:
                conn.execute(f"DROP TABLE IF EXISTS {article_table}")
        except Exception as exc:
            logger.warning(
                "Could not drop article table %s: %s", article_table, exc,
            )

    # Delete scenario row (cascades to scenario_blocks)
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM scenarios WHERE id = ?", (scenario_id,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Scenario not found")
        conn.commit()

    return {"message": "deleted"}

# ---------------------------------------------------------------------
# Update / patch helpers
# ---------------------------------------------------------------------

def update_building_block(
    block_id: int,
    name: Optional[str] = None,
    kind: Optional[str] = None,
    prompt: Optional[str] = None,
    options: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Update an existing Building-Block (partial update)."""

    fields = []
    params = []
    if name is not None:
        fields.append("name = ?")
        params.append(name.strip())
    if kind is not None:
        fields.append("kind = ?")
        params.append(kind)
    if prompt is not None:
        fields.append("prompt = ?")
        params.append(prompt)
    if options is not None:
        fields.append("options = ?")
        params.append(_encode_options(options))

    if not fields:
        raise HTTPException(status_code=400, detail="Nothing to update")

    params.append(block_id)

    with db.get_connection() as conn:
        cursor = conn.cursor()
        try:
            query_sql = (
                "UPDATE building_blocks SET "
                f"{', '.join(fields)} WHERE id = ?"
            )
            cursor.execute(query_sql, params)
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="Block not found")
            conn.commit()
            cursor.execute("SELECT * FROM building_blocks WHERE id = ?", (block_id,))
            row = cursor.fetchone()
        except sqlite3.IntegrityError as exc:
            logger.error(
                "Integrity error updating block: %s", exc,
            )
            raise HTTPException(status_code=409, detail="Name already exists") from exc

    block = dict(zip([col[0] for col in cursor.description], row))
    block["options"] = _decode_options(block.get("options"))
    return block

# ---------------------------------------------------------------------
# Delete helper
# ---------------------------------------------------------------------

def delete_building_block(block_id: int) -> Dict[str, Any]:
    """Remove a building block (fails if linked to scenarios)."""

    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM building_blocks WHERE id = ?", (block_id,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Block not found")
        conn.commit()
    return {"message": "deleted"}

# ---------------------------------------------------------------------
# Prompt composition
# ---------------------------------------------------------------------

def _load_topic_defaults(topic: str) -> Dict[str, list[str]]:
    import json, os
    cfg_path = os.path.join(os.path.dirname(__file__), "../config/config.json")
    with open(cfg_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    for t in data.get("topics", []):
        if t.get("name") == topic:
            return {
                "categories": t.get("categories", []),
                "future_signals": t.get("future_signals", []),
                "sentiment_options": t.get("sentiment", []),
                "time_to_impact_options": t.get("time_to_impact", []),
                "driver_types": t.get("driver_types", []),
            }

    # fall back empty lists
    return {
        "categories": [],
        "future_signals": [],
        "sentiment_options": [],
        "time_to_impact_options": [],
        "driver_types": [],
    }

def compose_prompt(scenario_id: int, summary_voice="analyst", summary_type="bullet", summary_length=120) -> Dict[str, str]:
    """Return system_prompt and user_prompt built from scenario blocks."""

    scen = get_scenario(scenario_id)
    topic_defaults = _load_topic_defaults(scen["topic"])

    # Fetch block prompts (+kind & options) in the order they were linked
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT b.prompt, b.kind, b.options FROM scenario_blocks sb "
            "JOIN building_blocks b ON sb.building_block_id = b.id "
            "WHERE sb.scenario_id = ? ORDER BY sb.rowid",
            (scenario_id,),
        )
        rows = cursor.fetchall()

    # helper mapping placeholder → list[str]
    def _list_for_placeholder(placeholder: str, blk_opts: list[str] | None) -> str:
        src = blk_opts if blk_opts else topic_defaults.get(placeholder, [])
        return ", ".join(src)

    processed_prompts: list[str] = []
    for row in rows:
        p_text, p_kind, p_opts_json = row
        blk_opts: list[str] | None = None
        if p_opts_json:
            import json
            try:
                blk_opts = json.loads(p_opts_json)
            except Exception:  # pragma: no cover – defensive
                blk_opts = None

        # Replace known placeholders if they exist in the text ------------
        for placeholder in (
            "categories",
            "future_signals",
            "sentiment_options",
            "time_to_impact_options",
            "driver_types",
        ):
            token = "{" + placeholder + "}"
            if token in p_text:
                p_text = p_text.replace(token, _list_for_placeholder(placeholder, blk_opts))

        processed_prompts.append(p_text)

    analyses = "\n\n" + "\n\n".join(
        f"{idx + 1}. {text}" for idx, text in enumerate(processed_prompts)
    )

    # System-level instruction fed to the model controlling tone & format
    system_prompt = f"style of {summary_voice} and format of {summary_type}."

    user_prompt = (
        f"Summarize the following news article in {summary_length} words, "
        f"using the voice of a {summary_voice}.\n\n"
        "Title: {title}\n"
        "Source: {source}\n"
        "URL: {uri}\n"
        "Content: {article_text}\n\n"
        "Provide a summary with the following characteristics:\n"
        f"Length: Maximum {summary_length} words\n"
        f"Voice: {summary_voice}\n"
        f"Type: {summary_type}\n\n"
        "Summarize the content using the specified characteristics. "
        "Format your response as follows:\n"
        "Summary: [Your summary here]"
    )

    format_spec = (
        "\n\nFormat your response as follows:\n"
        "Title: [Your title here]\n"
        "Summary: [Your summary here]\n"
        "Category: [Your classification here]\n"
        "Future Signal: [Your classification here]\n"
        "Future Signal Explanation: [Your explanation here]\n"
        "Sentiment: [Your classification here]\n"
        "Sentiment Explanation: [Your explanation here]\n"
        "Time to Impact: [Your classification here]\n"
        "Time to Impact Explanation: [Your explanation here]\n"
        "Driver Type: [Your classification here]\n"
        "Driver Type Explanation: [Your explanation here]\n"
        "Tags: [tag1, tag2, tag3, ...]"
    )

    merged = user_prompt + "\n\nThen, provide the following analyses:\n" + analyses + format_spec

    # substitute placeholders with topic defaults
    merged = (
        merged.replace("{categories}", ", ".join(topic_defaults["categories"]))
        .replace("{future_signals}", ", ".join(topic_defaults["future_signals"]))
        .replace("{sentiment_options}", ", ".join(topic_defaults["sentiment_options"]))
        .replace("{time_to_impact_options}", ", ".join(topic_defaults["time_to_impact_options"]))
        .replace("{driver_types}", ", ".join(topic_defaults["driver_types"]))
    )

    return {
        "system_prompt": system_prompt,
        "user_prompt": merged,
    } 