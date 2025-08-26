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
                "Integrity error inserting building block: %s",
                exc,
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
            # --- Start: Validate block_ids ---
            if block_ids:  # Only check if there are block_ids to validate
                placeholders = ",".join(["?"] * len(block_ids))
                query = f"SELECT COUNT(id) FROM building_blocks WHERE id IN ({placeholders})"
                cursor.execute(query, block_ids)
                count_row = cursor.fetchone()
                if count_row is None or count_row[0] != len(block_ids):
                    # Find which IDs are missing for a more detailed (optional) error
                    # For now, a general message:
                    conn.rollback()  # Rollback any potential transaction start
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="One or more selected building blocks could not be found. "
                        "Please refresh the block list and try again.",
                    )
            # --- End: Validate block_ids ---

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
        except sqlite3.IntegrityError as exc:
            conn.rollback()
            logger.error("Integrity error creating scenario: %s", exc)
            if "UNIQUE constraint failed: scenarios.name" in str(exc).lower():
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,  # 409 Conflict is more appropriate
                    detail=f"A scenario with the name '{name}' already exists. Please choose a different name.",
                ) from exc
            # For other integrity errors (e.g., related to scenario_blocks foreign keys if block_ids were not validated early enough)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Could not create scenario due to a data integrity issue. Ensure all selected blocks are valid.",
            ) from exc
        except Exception as exc:  # General catch-all
            conn.rollback()
            logger.error(
                "Error creating scenario: %s",
                exc,
            )
            # Keep existing generic error for other non-IntegrityError exceptions
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Could not create scenario",
            ) from exc

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
            cursor.execute(
                "DELETE FROM scenario_blocks WHERE scenario_id = ?", (scenario_id,)
            )
            for bid in block_ids:
                cursor.execute(
                    "INSERT INTO scenario_blocks (scenario_id, building_block_id) VALUES (?, ?)",
                    (scenario_id, bid),
                )

        if (
            cursor.rowcount == 0
            and name is None
            and topic is None
            and block_ids is None
        ):
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
                "Could not drop article table %s: %s",
                article_table,
                exc,
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
                "UPDATE building_blocks SET " f"{', '.join(fields)} WHERE id = ?"
            )
            cursor.execute(query_sql, params)
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="Block not found")
            conn.commit()
            cursor.execute("SELECT * FROM building_blocks WHERE id = ?", (block_id,))
            row = cursor.fetchone()
        except sqlite3.IntegrityError as exc:
            logger.error(
                "Integrity error updating block: %s",
                exc,
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


# Helper to parse options like ["key:value", "key2: value2"] into a dict
def _parse_key_value_options(options: Optional[List[str]]) -> Dict[str, str]:
    parsed = {}
    if not options:
        return parsed
    for opt in options:
        if ":" in opt:
            parts = opt.split(":", 1)
            parsed[parts[0].strip().lower()] = parts[1].strip()
    return parsed


# Updated compose_prompt function
def compose_prompt(scenario_id: int) -> Dict[str, str]:
    """Return system_prompt and user_prompt built from scenario blocks."""

    db_instance = get_database_instance()
    with db_instance.get_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM scenarios WHERE id = ?", (scenario_id,))
        scenario_row = cursor.fetchone()
        if not scenario_row:
            raise HTTPException(status_code=404, detail="Scenario not found")

        cursor.execute(
            """SELECT b.id, b.name, b.kind, b.prompt, b.options 
            FROM scenario_blocks sb
            JOIN building_blocks b ON sb.building_block_id = b.id
            WHERE sb.scenario_id = ? ORDER BY sb.rowid""",
            (scenario_id,),
        )
        block_rows = cursor.fetchall()

    if not block_rows:
        return {
            "system_prompt": "You are a helpful assistant.",
            "user_prompt": "No building blocks selected for this scenario.",
        }

    system_prompt_parts: List[str] = []
    user_prompt_analysis_sections: List[Dict[str, str]] = []
    summary_details: Dict[str, str] = {}
    DEFAULT_SUMMARY_LENGTH = "150"
    DEFAULT_SUMMARY_VOICE = "a neutral"

    processed_block_ids_for_specific_handling = set()

    for block_row in block_rows:
        block_id = block_row["id"]
        block_name = block_row["name"]
        block_kind = block_row["kind"].lower()
        block_prompt_text = block_row["prompt"]
        block_options_list = (
            _decode_options(block_row["options"]) 
            if block_row["options"] else []
        )

        handled_specifically = False
        # --- Start Block Processing --- 
        if block_kind == "summarization":
            parsed_opts = _parse_key_value_options(block_options_list)
            summary_details["length"] = parsed_opts.get(
                "length", DEFAULT_SUMMARY_LENGTH
            )
            summary_details["voice"] = parsed_opts.get("voice", DEFAULT_SUMMARY_VOICE)
            processed_block_ids_for_specific_handling.add(block_id)
            handled_specifically = True

        elif block_kind == "categorization":
            options_str = (
                ", ".join(block_options_list) if block_options_list else "Not specified"
            )
            text = (
                f"Classify the article into one of these categories:\n{options_str}"
                "\nIf none of these categories fit, suggest a new category or "
                'classify it as "Other".'
            )
            user_prompt_analysis_sections.append({"title": "Category", "text": text})
            processed_block_ids_for_specific_handling.add(block_id)
            handled_specifically = True

        elif block_kind == "classification":
            options_str = (
                ", ".join(block_options_list) if block_options_list else "Not specified"
            )
            clean_block_name = block_name.lower()
            section_data = None
            if "future signal" in clean_block_name:
                text = (
                    f"Classify the article into one of these Future Signals:\n{options_str}"
                    "\nBase your classification on the overall tone and content of the "
                    "article regarding the future of the topic."
                    "\nProvide a brief explanation for your classification."
                )
                section_data = {"title": "Future Signal", "text": text}
            elif "time to impact" in clean_block_name:
                text = (
                    f"Classify the time to impact as one of:\n{options_str}"
                    "\nProvide a brief explanation for your classification."
                )
                section_data = {"title": "Time to Impact", "text": text}
            elif "driver type" in clean_block_name:
                text = (
                    f"Classify the article into one of these Driver Types:\n{options_str}"
                    "\nProvide a brief explanation for your classification."
                )
                section_data = {"title": "Driver Type", "text": text}

            if section_data:
                user_prompt_analysis_sections.append(section_data)
                processed_block_ids_for_specific_handling.add(block_id)
                handled_specifically = True

        elif block_kind == "sentiment":
            options_str = (
                ", ".join(block_options_list) if block_options_list else "Not specified"
            )
            text = (
                f"Classify the sentiment as one of:\n{options_str}"
                "\nProvide a brief explanation for your classification."
            )
            user_prompt_analysis_sections.append({"title": "Sentiment", "text": text})
            processed_block_ids_for_specific_handling.add(block_id)
            handled_specifically = True

        # Use the new 'generation' kind
        elif block_kind == "generation": 
            # Default title is the block name, default text is the block prompt
            title = block_name 
            text = block_prompt_text
            
            # Special handling if it's the "Relevant Tags" generator
            if block_name.lower() == "relevant tags":
                title = "Relevant Tags" # Ensure consistent title for format mapping
                default_tags_prompt = (
                    "Generate 3-5 relevant tags for the article. These should be "
                    "concise keywords or short phrases that capture the main topics "
                    "or themes of the article."
                )
                text = block_prompt_text if block_prompt_text else default_tags_prompt
            # Add other specific generator name checks here if needed
            
            user_prompt_analysis_sections.append({"title": title, "text": text})
            processed_block_ids_for_specific_handling.add(block_id)
            handled_specifically = True
            
        # --- End Block Processing --- 
        
    # Second pass for generic blocks (those whose kind wasn't specifically handled)
    for block_row in block_rows:
        block_id = block_row["id"]
        if block_id in processed_block_ids_for_specific_handling:
            continue
        
        block_name = block_row["name"]
        block_kind = block_row["kind"].lower()
        block_prompt_text = block_row["prompt"]
        
        # Exclude 'keywords' kind entirely from the prompt
        if block_kind == "keywords":
            continue
            
        # Add other unhandled blocks
        if block_prompt_text: 
            user_prompt_analysis_sections.append({
                "title": block_name, # Use the block's name as title
                "text": block_prompt_text
            })

    if summary_details:
        summary_voice = summary_details["voice"]
        system_prompt_parts.append(f"Style of {summary_voice}.")

    final_system_prompt = " ".join(system_prompt_parts)
    if not final_system_prompt:
        final_system_prompt = "You are a helpful research assistant."

    if summary_details:
        sum_len = summary_details["length"]
        sum_voice = summary_details["voice"]
        user_prompt_preamble = (
            f"Summarize the following news article in {sum_len} words, "
            f"using the voice of a {sum_voice}.\n\n"
            "Title: {{title}}\nSource: {{source}}\nURL: {{uri}}\nContent: {{article_text}}\n\n"
            "Provide a summary with the following characteristics:\n"
            f"Length: Maximum {sum_len} words\n"
            f"Voice: {sum_voice}\n"
            "\nSummarize the content using the specified characteristics. "
            "Format your response as follows:\nSummary: [Your summary here]"
        )
    else:
        user_prompt_preamble = (
            "Analyze the following news article:\n\n"
            "Title: {{title}}\nSource: {{source}}\nURL: {{uri}}\nContent: {{article_text}}"
        )

    numbered_analysis_text = ""
    if user_prompt_analysis_sections:
        sections_formatted = []
        for idx, section in enumerate(user_prompt_analysis_sections):
            title = section["title"]
            text_content = section["text"].strip()
            formatted_section = f"{idx + 1}. {title}:\n{text_content}"
            sections_formatted.append(formatted_section)
        numbered_analysis_text = "\n\n".join(sections_formatted)

    format_lines = ["Title: [Your title here]"]
    if summary_details:
        format_lines.append("Summary: [Your summary here]")

    analysis_format_map = {
        "Category": "Category: [Your classification here]",
        "Future Signal": "Future Signal: [Your classification here]\n"
        "Future Signal Explanation: [Your explanation here]",
        "Sentiment": "Sentiment: [Your classification here]\n"
        "Sentiment Explanation: [Your explanation here]",
        "Time to Impact": "Time to Impact: [Your classification here]\n"
        "Time to Impact Explanation: [Your explanation here]",
        "Driver Type": "Driver Type: [Your classification here]\n"
        "Driver Type Explanation: [Your explanation here]",
        # Generic blocks (handled by the second pass) might not have specific format lines here
        # unless we dynamically add their titles to analysis_format_map or accept a generic format line.
        # For now, their output is expected as per their own prompt text.
    }
    for section in user_prompt_analysis_sections:
        title = section["title"]
        if title in analysis_format_map:
            format_lines.append(analysis_format_map[title])
        # else: # For generic blocks, we don't add a specific format line by default.
        # If their prompt asks for a specific format, it's part of their text.

    final_format_instructions = ""
    if format_lines:  # Only add format instructions if there are any format lines
        joined_format_lines = "\n".join(format_lines)
        final_format_instructions = (
            f"\n\nFormat your response as follows:\n{joined_format_lines}"
        )

    final_user_prompt = user_prompt_preamble
    if numbered_analysis_text:
        final_user_prompt += (
            "\n\nThen, provide the following analyses:\n\n" + numbered_analysis_text
        )
    final_user_prompt += final_format_instructions

    return {
        "system_prompt": final_system_prompt.strip(),
        "user_prompt": final_user_prompt.strip(),
    }
