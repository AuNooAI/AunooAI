# flake8: noqa
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, staticfiles, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from typing import List, Optional, Dict
from pydantic import BaseModel
from datetime import datetime
import os
import json
from elevenlabs import (
    ElevenLabs,
    PodcastConversationModeData,
    PodcastTextSource,
)
from elevenlabs.studio import (
    BodyCreatePodcastV1StudioPodcastsPostMode_Conversation,
    BodyCreatePodcastV1StudioPodcastsPostMode_Bulletin,
)
from app.database import Database, get_database_instance, get_db_session
import logging
from pydub import AudioSegment
import asyncio
from app.ai_models import LiteLLMModel
from app.utils.audio import combine_audio_files, save_audio_file, AUDIO_DIR, ensure_audio_directory
import requests
import uuid
import random
import math
from pathlib import Path
import re
import threading

# Set up logging
logger = logging.getLogger(__name__)

# Get API keys from environment with defaults
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
ELEVENLABS_API_KEY = os.getenv('ELEVENLABS_API_KEY')
DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # Rachel's voice ID

# Default podcast script prompt template
PODCAST_CONVERSATION_PROMPT = """
You are an expert podcast script writer. Create a podcast script for "{podcast_name}" episode titled "{episode_title}".
The script should be engaging, informative, and maintain a natural conversational flow between the host Annie and {guest_name}, our {guest_title}.

Guidelines:
1. Remove any instructions like "Intro music fades in" or sound effects
2. Format the script in markdown with clear speaker sections
3. Include emotional context for each section in [brackets]
4. Keep the conversation natural and flowing
5. Focus on the key insights and interesting aspects of the provided articles
6. Each speaker section should be clearly marked with their role

Example format:
[Annie - Host] [excited] Welcome to {podcast_name}! I'm Annie, and today we're joined by {guest_name}, our {guest_title} to discuss...

[{guest_name} - {guest_title}] [enthusiastic] Thank you for having me, Annie. I'm excited to share these insights...

[Annie - Host] [curious] That's fascinating! Could you tell us more about...
"""

# Bulletin (single‑presenter) prompt
PODCAST_BULLETIN_PROMPT = """
You are an expert news bulletin writer and presenter. Create a concise podcast bulletin for "{podcast_name}" episode titled "{episode_title}".

Guidelines:
1. Single presenter (Annie) speaking in the first person. No other speakers.
2. Use an engaging, authoritative tone suitable for a news bulletin.
3. Group related items, use clear transitions, and end with a brief sign‑off.
4. Do NOT include host/guest labels except [Annie - Host] for each section.
5. Remove any instructions like "Intro music fades in" or sound effects.
6. Format in markdown with speaker sections and emotional cues in [brackets].
7. Focus on the key insights and interesting aspects of the provided articles.

Example format:
[Annie - Host] [upbeat] Good day, this is your "{podcast_name}" bulletin. Our first story...  
[Annie - Host] [serious] Turning to...  
[Annie - Host] [warm] And finally, ...  
"""

router = APIRouter(prefix="/api")  # Add /api prefix to all routes

# Mount static directory for audio files
router.mount("/static", staticfiles.StaticFiles(directory="static"), name="static")

# ---------------------------------------------------------------------------
# Template helpers & API
# ---------------------------------------------------------------------------

TEMPLATE_DIR = (
    Path(__file__).resolve().parent.parent.parent / "data" / "prompts" / "script_templates"
)


def _sanitize_template_name(name: str) -> str:
    """Ensure only safe characters (letters, numbers, underscore) in name."""
    return re.sub(r"[^0-9a-zA-Z_]+", "_", name).strip("_")


def _template_path(name: str) -> Path:
    sanitized = _sanitize_template_name(name)
    return TEMPLATE_DIR / f"{sanitized}.json"


def _load_template_file(path: Path) -> Dict[str, str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        # Support both {"template": "..."} and split system/user prompt formats
        if "template" in data:
            return {"name": path.stem, "content": data["template"]}
        if "system_prompt" in data and "user_prompt" in data:
            # Concatenate for editing convenience
            system = data.get("system_prompt", "")
            user = data.get("user_prompt", "")
            return {
                "name": path.stem,
                "content": f"{system}\n\n{user}".strip(),
            }
    except Exception as exc:
        logger.error("Failed to load template %s: %s", path, exc)
    # Fallback: treat file as plain text
    return {"name": path.stem, "content": path.read_text(encoding="utf-8")}


def _save_template_file(name: str, content: str):
    TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
    path = _template_path(name)
    # Store under uniform structure so future parsing is easy
    payload = {
        "template": content,
        "version": "1.0.0",
        "updated_at": datetime.utcnow().isoformat() + "Z",
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


class PodcastTemplate(BaseModel):
    name: str
    content: str


@router.get("/podcast_templates/{template_name}")
async def get_podcast_template(template_name: str):
    """Return template content by name from disk."""
    path = _template_path(template_name)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Template '{template_name}' not found")

    tpl = _load_template_file(path)
    return {"name": tpl["name"], "content": tpl["content"], "template": tpl["content"]}


@router.post("/podcast_templates")
async def save_podcast_template(template: PodcastTemplate):
    """Create or update a template file on disk."""
    try:
        _save_template_file(template.name, template.content)
        return {"message": f"Template '{template.name}' saved successfully"}
    except Exception as exc:
        logger.error("Error saving template %s: %s", template.name, exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/podcast_templates")
async def list_podcast_templates():
    """List all template names and brief info."""
    try:
        TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
        templates = []
        for path in TEMPLATE_DIR.glob("*.json"):
            tpl = _load_template_file(path)
            templates.append(tpl)
        # Ensure at least default exists
        if not any(t["name"] == "default" for t in templates):
            templates.append(
                {
                    "name": "default",
                    "content": "[Host]: Welcome...\n\n{articles_discussion}\n\n[Host]: That wraps up...",
                }
            )
        return templates
    except Exception as exc:
        logger.error("Failed listing templates: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to list templates")

# ---------------------------------------------------------------------------
# Podcast setting helpers & API
# ---------------------------------------------------------------------------


class PodcastSettingModel(BaseModel):
    settings: Dict[str, str]


def _settings_key(mode: str) -> str:
    return f"defaults_{mode.lower()}"


@router.get("/podcast_settings/{mode}")
async def get_podcast_settings(mode: str, db: Database = Depends(get_database_instance)):
    """Fetch saved default settings for a mode (conversation/bulletin)."""
    key = _settings_key(mode)
    raw = db.get_podcast_setting(key)
    return json.loads(raw) if raw else {}


@router.post("/podcast_settings/{mode}")
async def save_podcast_settings(mode: str, payload: PodcastSettingModel, db: Database = Depends(get_database_instance)):
    """Save default settings (upsert)."""
    key = _settings_key(mode)
    db.set_podcast_setting(key, json.dumps(payload.settings))
    return {"message": "Settings saved"}

class PodcastRequest(BaseModel):
    title: str
    mode: str
    host_voice_id: str
    guest_voice_id: Optional[str] = None
    duration_scale: str = "default"
    quality_preset: str = "standard"
    article_uris: List[str]

class ScriptGenerationRequest(BaseModel):
    title: str
    model: str
    articles: List[dict]

class VoiceSettings(BaseModel):
    stability: float = 0.5
    similarity_boost: float = 0.75
    style: float = 0.0
    use_speaker_boost: bool = True
    speed: float = 1.0

class TTSPodcastRequest(BaseModel):
    # Core metadata
    podcast_name: str
    episode_title: str

    # Either a ready‑made script **or** article URIs to build the script from
    script: Optional[str] = None
    article_uris: Optional[List[str]] = None

    # Prompt / LLM configuration
    model: str = "gpt-4o"
    duration: str = "medium"  # short | medium | long

    # Speaker / voices
    host_name: Optional[str] = "Aunoo"
    host_voice_id: str
    guest_voice_id: Optional[str] = None
    guest_title: Optional[str] = None
    guest_name: Optional[str] = None
    mode: str = "conversation"  # "conversation" or "bulletin"
    topic: Optional[str] = None

    # ElevenLabs TTS settings
    model_id: str = "eleven_multilingual_v2"
    output_format: str = "mp3_44100_128"
    voice_settings: VoiceSettings = VoiceSettings()
    output_filename: Optional[str] = None

class PodcastResponse(BaseModel):
    podcast_id: str
    title: str
    status: str
    created_at: datetime
    audio_url: Optional[str] = None
    transcript: Optional[str] = None

class PodcastScriptRequest(BaseModel):
    podcast_name: str
    episode_title: str
    model: str
    mode: str = "conversation"  # "conversation" or "bulletin"
    duration: str = "medium"  # short | medium | long
    host_name: Optional[str] = None
    guest_title: Optional[str] = None
    guest_name: Optional[str] = None
    articles: List[dict]

class PodcastScriptResponse(BaseModel):
    title: str
    script: str

class TTSPodcastResponse(BaseModel):
    title: str
    audio_url: str
    duration: float
    transcript: str

class VoiceResponse(BaseModel):
    voice_id: str
    name: str
    category: Optional[str]
    description: Optional[str]
    labels: Optional[Dict[str, str]]
    preview_url: Optional[str]
    available_for_tiers: Optional[List[str]]

PROMPT_BASE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "prompts" / "script_templates"

def load_prompt_template(mode: str, duration: str) -> str:
    """Load a prompt template markdown from disk."""
    # Try JSON first (preferred format)
    json_path = PROMPT_BASE_DIR / f"{mode}_{duration}.json"
    if json_path.exists():
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            if "template" in data:
                return data["template"]
            system = data.get("system_prompt", "")
            user = data.get("user_prompt", "")
            return f"{system}\n\n{user}".strip()
        except Exception as e:
            logger.error(f"Failed to parse prompt template {json_path}: {e}")

    # Fallback to legacy markdown
    md_path = PROMPT_BASE_DIR / f"{mode}_{duration}.md"
    if md_path.exists():
        return md_path.read_text(encoding="utf-8")

    # Final fallback – built‑in prompts
    logger.warning(f"Prompt template for {mode}-{duration} not found – using default in‑code prompt")
    return PODCAST_CONVERSATION_PROMPT if mode == "conversation" else PODCAST_BULLETIN_PROMPT

def validate_api_keys():
    """Validate that required API keys are set"""
    missing_keys = []
    if not OPENAI_API_KEY:
        missing_keys.append("OpenAI")
    if not ELEVENLABS_API_KEY:
        missing_keys.append("ElevenLabs")
    
    if missing_keys:
        raise HTTPException(
            status_code=401,
            detail={
                "error": "Missing API keys",
                "missing_providers": missing_keys,
                "setup_instructions": "Please set up your API keys in the environment variables:\n" +
                                   ("- OPENAI_API_KEY\n" if "OpenAI" in missing_keys else "") +
                                   ("- ELEVENLABS_API_KEY\n" if "ElevenLabs" in missing_keys else "")
            }
        )

@router.post("/generate_podcast_script")
async def generate_podcast_script(
    request: PodcastScriptRequest,
    db: Database = Depends(get_database_instance)
):
    try:
        logger.info(f"Generating podcast script for {request.podcast_name} - {request.episode_title}")
        
        # Prepare article content
        article_texts = []
        for article in request.articles:
            article_text = [
                f"Title: {article['title']}",
                f"Summary: {article['summary']}",
                f"Category: {article.get('category', 'N/A')}",
                f"Future Signal: {article.get('future_signal', 'N/A')}",
                f"Future Signal Explanation: {article.get('future_signal_explanation', 'N/A')}",
                f"Sentiment: {article.get('sentiment', 'N/A')}",
                f"Sentiment Explanation: {article.get('sentiment_explanation', 'N/A')}",
                f"Time to Impact: {article.get('time_to_impact', 'N/A')}",
                f"Time to Impact Explanation: {article.get('time_to_impact_explanation', 'N/A')}",
                f"Driver Type: {article.get('driver_type', 'N/A')}",
                f"Driver Type Explanation: {article.get('driver_type_explanation', 'N/A')}"
            ]
            article_texts.append("\n".join(article_text))
        
        combined_articles = "\n\n---\n\n".join(article_texts)
        logger.info(f"Prepared article content, total length: {len(combined_articles)}")
        
        # Prepare the system prompt from external template
        prompt_template = load_prompt_template(request.mode, request.duration)

        class _SafeDict(dict):
            def __missing__(self, key):
                return "{" + key + "}"

        system_prompt = prompt_template.format_map(_SafeDict(
            podcast_name=request.podcast_name,
            episode_title=request.episode_title,
            host_name=(request.host_name or "Aunoo"),
            guest_title=(request.guest_title or "Guest"),
            guest_name=(request.guest_name or "Auspex"),
        ))

        # Add explicit generation guidelines to reduce excessive non-verbals and
        # extremely short / long lines which can cause the TTS engine to speed
        # up unnaturally.
        guidelines = (
            "### Generation Guidelines for Podcast Script\n"
            "1. Alternate speaker tags beginning with [S1] for the host and [S2] for the guest; never repeat the same tag twice in a row.\n"
            "2. Keep each spoken sentence between 5–20 seconds of speech (≈40–160 tokens).\n"
            "3. Use non-verbal cues *sparingly* — at most one per speaker turn — and never output a line that only contains a non-verbal.\n"
            "4. Allowed non-verbal tags: (laughs), (clears throat), (sighs), (gasps), (coughs), (singing), (sings), (mumbles), (beep), (groans), (sniffs), (claps), (screams), (inhales), (exhales), (applause), (burps), (humming), (sneezes), (chuckle), (whistles).\n"
            "5. Avoid very short (<5 s) or very long (>20 s) speaker blocks to prevent unnatural TTS speed.\n"
        )

        system_prompt = f"{system_prompt}\n\n{guidelines}"
        logger.info(f"Prepared system prompt: {system_prompt}")
        
        # Get the AI model
        logger.info(f"Initializing AI model {request.model}")
        model = LiteLLMModel.get_instance(request.model)
        if not model:
            logger.error(f"Failed to initialize {request.model} model")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to initialize {request.model} model"
            )
        
        # Generate the script
        logger.info("Generating script with AI model")
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": combined_articles}
        ]
        response = model.generate_response(messages)
        if not response:
            logger.error("Model returned empty response")
            raise HTTPException(
                status_code=500,
                detail="Failed to generate script"
            )
        
        logger.info("Processing model response – applying post-processing")
        script = _postprocess_script(response)
        logger.info(f"Generated script length: {len(script)}")
        
        return {
            "success": True,
            "script": script,
            "article_count": len(request.articles)
        }
        
    except Exception as e:
        logger.error(f"Error generating podcast script: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate podcast script: {str(e)}"
        )

# Note: we now launch the heavy TTS generation in the background so the HTTP
# request returns immediately. The UI can poll `/api/podcast/status/{id}` as
# before.

@router.post("/generate_tts_podcast")
async def generate_tts_podcast(request: TTSPodcastRequest):
    """
    Launch podcast generation. The heavy work is off‑loaded to a background
    task so that the request returns quickly with a `podcast_id` that the UI
    can poll using `/api/podcast/status/{podcast_id}`.
    """
    podcast_id = str(uuid.uuid4())

    # Immediately insert a DB record with status = processing so polling works.
    try:
        # Generate a unique podcast ID
        db = get_database_instance()
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO podcasts (
                    id, title, status, created_at, transcript, metadata
                ) VALUES (?, ?, 'processing', CURRENT_TIMESTAMP, ?, ?)
                """,
                (
                    podcast_id,
                    f"{request.podcast_name} - {request.episode_title}",
                    request.script or "",
                    json.dumps({}),
                ),
            )
            conn.commit()

        # Launch background processing task in a separate thread so that the
        # current ASGI worker is freed immediately.
        threading.Thread(
            target=lambda: asyncio.run(_run_tts_podcast_worker(podcast_id, request)),
            daemon=True,
        ).start()

        # Return immediately
        return {"success": True, "podcast_id": podcast_id, "status": "processing"}

    except Exception as exc:
        logger.error("Failed to enqueue podcast generation: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Worker that does the heavy TTS processing
# ---------------------------------------------------------------------------


async def _run_tts_podcast_worker(podcast_id: str, request: TTSPodcastRequest):
    """Perform the full TTS generation flow. Runs in the background."""
    logger.info("[Worker] Starting podcast generation %s", podcast_id)
    try:
        # --- RE‑RUN previous synchronous logic ----------------------------
        # Note: this block is essentially the previous implementation of the
        # generate_tts_podcast body (after the initial INSERT). Only minimal
        # adaptations were made – e.g. use the already‑supplied `podcast_id`.

        # Validate API keys
        validate_api_keys()

        # Determine mode defaults
        if not request.host_name:
            request.host_name = "Aunoo"
        if not request.guest_name:
            request.guest_name = "Auspex"

        # Auto‑generate script if needed (re‑use our helper)
        if (not request.script or not request.script.strip()) and request.article_uris:
            db = get_database_instance()
            records = [db.get_article(u) for u in request.article_uris]
            records = [r for r in records if r]
            if not records:
                raise ValueError("No articles found for provided URIs")

            request.script = _generate_script_from_articles(
                podcast_name=request.podcast_name,
                episode_title=request.episode_title,
                host_name=request.host_name,
                guest_name=request.guest_name,
                guest_title=request.guest_title or "Guest",
                duration=request.duration,
                mode=request.mode,
                articles=records,
                llm_model=request.model,
            )

        # ------------------------------------------------------------------
        # (The rest of this function is a verbatim move of the heavy loop from
        #  the original generate_tts_podcast implementation.)
        # ------------------------------------------------------------------

        # Determine mode and guest voice
        available_voices = await get_available_voices()

        if request.mode == "bulletin":
            guest_voice = None  # Not used
        else:
            if request.guest_voice_id:
                guest_voice = next((v for v in available_voices if v.voice_id == request.guest_voice_id), None)
                if guest_voice is None:
                    raise HTTPException(status_code=400, detail="Invalid guest_voice_id provided")
            else:
                guest_voice = random.choice([v for v in available_voices if v.voice_id != request.host_voice_id])

            if not request.guest_name:
                request.guest_name = guest_voice.name.split()[0] if guest_voice and guest_voice.name else "Guest"

            if not request.guest_title:
                request.guest_title = random.choice([
                    "Industry Expert",
                    "Chief Futurist",
                    "Senior Analyst",
                    "Innovation Strategist",
                ])

        host_aliases = {(request.host_name or "Aunoo").lower(), "annie", "host"}

        # ----------------- (Split script and generate audio) --------------
        script_sections = []
        current_section = {"speaker": None, "text": "", "emotion": None, "role": None}

        for line in request.script.split("\n"):
            raw = line.strip()
            stripped = raw.lstrip("*").lstrip("_").strip()

            speaker_detected = None
            role = None

            if stripped.startswith("[") and "]" in stripped:
                if current_section["speaker"]:
                    script_sections.append(current_section)

                first_close_idx = stripped.find("]")
                header = stripped[1:first_close_idx]
                parts = re.split(r"\s*[\-\u2010-\u2015]\s*", header, maxsplit=1)
                speaker = parts[0]
                role = parts[1] if len(parts) > 1 else None

                emotion = None
                remaining = stripped[first_close_idx + 1:].lstrip()
                if remaining.startswith("[") and "]" in remaining:
                    second_close_idx = remaining.find("]")
                    emotion = remaining[1:second_close_idx].strip()
                    remaining = remaining[second_close_idx + 1:].lstrip()

                initial_text = remaining + "\n" if remaining else ""

                speaker_detected = speaker
                current_section = {
                    "speaker": speaker_detected,
                    "role": role,
                    "text": initial_text,
                    "emotion": emotion,
                }
            else:
                m = re.match(r"^\*\*(.+?)\*\*: \s*(.*)$", raw)
                if m:
                    speaker_detected = m.group(1).strip()
                    line_text = m.group(2)
                    if current_section["speaker"]:
                        script_sections.append(current_section)
                    current_section = {
                        "speaker": speaker_detected,
                        "role": None,
                        "text": line_text + "\n",
                        "emotion": None,
                    }
                else:
                    current_section["text"] += line + "\n"

        if current_section["speaker"]:
            script_sections.append(current_section)

        if not script_sections:
            logger.warning("No speaker blocks detected in script; using entire script as host section")
            script_sections.append({
                "speaker": "annie",
                "role": "Host",
                "text": request.script,
                "emotion": None,
            })

        audio_segments = []
        client = ElevenLabs(api_key=ELEVENLABS_API_KEY)

        def clean_text(raw: str) -> str:
            text = raw
            text = re.sub(r"\[(?:[^\]]*(music|sound|sfx|fade)[^\]]*)\]", "", text, flags=re.IGNORECASE)
            text = re.sub(r"\((?:[^)]*(music|sound|sfx|fade)[^)]*)\)", "", text, flags=re.IGNORECASE)
            text = re.sub(r"^\*\*[\w\s\-]+:\*\*", "", text, flags=re.MULTILINE)
            text = re.sub(r"^\*\*[\w\s\-]+\*\*: \s*", "", text, flags=re.MULTILINE)
            cleaned_lines = []
            for ln in text.splitlines():
                lowered = ln.lower()
                if any(kw in lowered for kw in ["intro music", "music fades", "sound effect", "sfx", "fade in", "fade out"]):
                    continue
                if "podcast script" in lowered:
                    continue
                cleaned_lines.append(ln)
            return "\n".join(cleaned_lines)

        for section in script_sections:
            speaker_lower = section["speaker"].strip().lower()
            role_lower = (section.get("role") or "").lower()

            if request.guest_name and speaker_lower == request.guest_name.strip().lower():
                use_host = False
            elif speaker_lower in host_aliases:
                use_host = True
            elif "guest" in role_lower:
                use_host = False
            elif "host" in role_lower or "host" in speaker_lower:
                use_host = True
            else:
                use_host = True

            voice_id = request.host_voice_id if use_host else (guest_voice.voice_id if guest_voice else request.host_voice_id)

            voice_settings_dict = {
                "stability": request.voice_settings.stability,
                "similarity_boost": request.voice_settings.similarity_boost,
                "style": request.voice_settings.style,
                "use_speaker_boost": request.voice_settings.use_speaker_boost,
                "speed": request.voice_settings.speed,
            }

            cleaned = clean_text(section["text"])
            chunks = split_into_chunks(cleaned, max_chars=2500)

            for chunk_index, chunk_text in enumerate(chunks):
                previous_text = chunks[chunk_index - 1] if chunk_index > 0 else None
                next_text = chunks[chunk_index + 1] if chunk_index < len(chunks) - 1 else None
                try:
                    audio_generator = client.text_to_speech.convert(
                        voice_id=voice_id,
                        text=chunk_text.strip(),
                        model_id=request.model_id,
                        output_format=request.output_format,
                        voice_settings=voice_settings_dict,
                        previous_text=previous_text,
                        next_text=next_text,
                    )

                    audio_bytes = b"".join(b if isinstance(b, bytes) else b.encode() for b in audio_generator)

                    if not audio_bytes:
                        logger.warning("Empty audio bytes for section %s chunk %d", section["speaker"], chunk_index)
                        continue

                    audio_segments.append(audio_bytes)
                except Exception as e:
                    logger.error("Error generating audio: %s", e)
                    continue

        if not audio_segments:
            raise ValueError("No audio segments generated")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"podcast_{podcast_id}_{timestamp}.mp3"

        if not ensure_audio_directory():
            raise RuntimeError("Could not create audio directory")

        duration = combine_audio_files(audio_segments, output_filename)

        meta = {
            "duration": round(duration / 60, 2),
            "podcast_name": request.podcast_name,
            "episode_title": request.episode_title,
            "mode": request.mode,
            "topic": request.topic,
        }

        if request.mode == "conversation":
            meta["guest"] = request.guest_name
            meta["guest_title"] = request.guest_title

        db = get_database_instance()
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE podcasts
                SET status = 'completed',
                    audio_url = ?,
                    completed_at = CURRENT_TIMESTAMP,
                    error = NULL,
                    metadata = ?
                WHERE id = ?
                """,
                (
                    f"/static/audio/{output_filename}",
                    json.dumps(meta),
                    podcast_id,
                ),
            )
            conn.commit()

        logger.info("[Worker] Podcast %s completed", podcast_id)

    except Exception as err:
        logger.error("[Worker] Error generating TTS podcast %s: %s", podcast_id, err, exc_info=True)
        try:
            db = get_database_instance()
            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE podcasts
                    SET status = 'error', error = ?, completed_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (str(err), podcast_id),
                )
                conn.commit()
        except Exception as db_err:
            logger.error("[Worker] Failed updating error status for %s: %s", podcast_id, db_err)

def split_into_chunks(text: str, max_chars: int = 2500) -> List[str]:
    """Split text into chunks of maximum size while preserving sentence boundaries."""
    chunks = []
    current_chunk = []
    current_length = 0
    
    # Split into sentences (simple implementation)
    sentences = text.replace("! ", "!<SPLIT>").replace("? ", "?<SPLIT>").replace(". ", ".<SPLIT>").split("<SPLIT>")
    
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
            
        sentence_length = len(sentence)
        
        if current_length + sentence_length > max_chars and current_chunk:
            # Join current chunk and add to chunks
            chunks.append(" ".join(current_chunk))
            current_chunk = [sentence]
            current_length = sentence_length
        else:
            current_chunk.append(sentence)
            current_length += sentence_length
    
    # Add the last chunk if there is one
    if current_chunk:
        chunks.append(" ".join(current_chunk))
    
    return chunks

@router.post("/create", response_model=PodcastResponse)
async def create_podcast(request: PodcastRequest, db: Database = Depends(get_database_instance)):
    try:
        # Validate API keys before proceeding
        validate_api_keys()
        
        # Get articles from database
        articles_data = []
        for uri in request.article_uris:
            article = db.get_article(uri)
            if article:
                articles_data.append({
                    "title": article.get('title'),
                    "summary": article.get('summary'),
                    "sentiment": article.get('sentiment'),
                    "time_to_impact": article.get('time_to_impact'),
                    "driver_type": article.get('driver_type')
                })

        if not articles_data:
            raise HTTPException(status_code=404, detail="No articles found")

        # Prepare source text
        source_text = f"Welcome to {request.title}!\n\n"
        
        for article in articles_data:
            if request.mode == "conversation":
                source_text += f"Host: Let's discuss this interesting article titled '{article['title']}'.\n"
                source_text += f"Guest: Yes, this is fascinating. The article discusses {article['summary']}.\n"
                source_text += f"Host: What's particularly interesting is that the sentiment seems to be {article['sentiment']}.\n"
                source_text += f"Guest: And the time to impact is expected to be {article['time_to_impact']}.\n\n"
            else:
                source_text += f"Next up: {article['title']}.\n"
                source_text += f"{article['summary']}\n"
                source_text += f"The sentiment is {article['sentiment']} and the time to impact is {article['time_to_impact']}.\n\n"
        
        source_text += "Thank you for listening!"

        # Initialize ElevenLabs client with proper API key
        api_key = os.getenv("ELEVENLABS_API_KEY")
        if not api_key:
            raise HTTPException(
                status_code=500,
                detail="ELEVENLABS_API_KEY not found in environment variables"
            )
        
        if not api_key.startswith('sk_'):
            raise HTTPException(
                status_code=500,
                detail="Invalid ELEVENLABS_API_KEY format. API key should start with 'sk_'"
            )

        client = ElevenLabs(api_key=api_key)

        # Create podcast based on mode
        if request.mode == "conversation":
            mode = BodyCreatePodcastV1StudioPodcastsPostMode_Conversation(
                conversation=PodcastConversationModeData(
                    host_voice_id=request.host_voice_id,
                    guest_voice_id=request.guest_voice_id
                )
            )
        else:  # bulletin mode
            mode = BodyCreatePodcastV1StudioPodcastsPostMode_Bulletin(
                bulletin={
                    "host_voice_id": request.host_voice_id
                }
            )

        # Create podcast with correct source format
        try:
            response = client.studio.create_podcast(
                model_id="21m00Tcm4TlvDq8ikWAM",
                mode=mode,
                source=[PodcastTextSource(type="text", text=source_text)],
                duration_scale=request.duration_scale,
                quality_preset=request.quality_preset
            )
        except Exception as e:
            error_msg = str(e)
            if "invalid_subscription" in error_msg:
                raise HTTPException(
                    status_code=403,
                    detail="Your ElevenLabs account needs to be whitelisted for the Podcast API. Please contact ElevenLabs sales team."
                )
            elif "unauthorized" in error_msg.lower():
                raise HTTPException(
                    status_code=401,
                    detail="Invalid ElevenLabs API key. Please check your API key."
                )
            raise

        # Save to database
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO podcasts (
                    id, title, created_at, status, config, article_uris
                ) VALUES (?, ?, CURRENT_TIMESTAMP, 'processing', ?, ?)
            """, (
                response["podcast_id"],
                request.title,
                None,  # config
                ','.join(request.article_uris),  # article_uris as comma-separated string
                json.dumps({})  # metadata
            ))
            conn.commit()

        return PodcastResponse(
            podcast_id=response["podcast_id"],
            title=request.title,
            status="processing",
            created_at=datetime.now(),
            audio_url=None,
            transcript=None
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating podcast: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/podcast/{podcast_id}/transcript")
async def get_podcast_transcript(podcast_id: str):
    """Get the transcript of a podcast."""
    try:
        with get_database_instance().get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT title, transcript, metadata
                FROM podcasts
                WHERE id = ?
            """, (podcast_id,))
            
            result = cursor.fetchone()
            
            if not result:
                raise HTTPException(
                    status_code=404,
                    detail=f"Podcast {podcast_id} not found"
                )
            
            title = result[0]
            transcript = result[1] or ""
            metadata = json.loads(result[2]) if result[2] else {}
            
            # Return as plain text with a filename
            return PlainTextResponse(
                content=transcript,
                headers={
                    "Content-Disposition": f'attachment; filename="{title.replace(" ", "_")}_transcript.txt"'
                }
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting podcast transcript: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

@router.get("/podcast/list")
async def list_podcasts():
    """List all podcasts."""
    try:
        with get_database_instance().get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, title, status, audio_url, created_at, completed_at, error, transcript, metadata
                FROM podcasts
                ORDER BY created_at DESC
            """)
            
            podcasts = []
            for row in cursor.fetchall():
                # Handle null values and ensure proper JSON encoding
                podcast = {
                    "podcast_id": row[0],
                    "title": row[1],
                    "status": row[2],
                    "audio_url": row[3],
                    "created_at": row[4],
                    "completed_at": row[5],
                    "error": row[6],
                    "transcript": row[7] if row[7] else "",
                    "metadata": json.loads(row[8]) if row[8] else {}
                }
                podcasts.append(podcast)
            
            # Return as JSONResponse with proper encoding
            return JSONResponse(content=podcasts)
            
    except Exception as e:
        logger.error(f"Error listing podcasts: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

@router.get("/podcast/status/{podcast_id}")
async def get_podcast_status(podcast_id: str):
    """Get the status of a podcast generation."""
    try:
        with get_database_instance().get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, title, status, audio_url, created_at, completed_at, error, transcript, metadata
                FROM podcasts
                WHERE id = ?
            """, (podcast_id,))
            
            result = cursor.fetchone()
            
            if not result:
                raise HTTPException(
                    status_code=404,
                    detail=f"Podcast {podcast_id} not found"
                )
            
            return {
                "podcast_id": result[0],
                "title": result[1],
                "status": result[2],
                "audio_url": result[3],
                "created_at": result[4],
                "completed_at": result[5],
                "error": result[6],
                "transcript": result[7],
                "metadata": json.loads(result[8]) if result[8] else {}
            }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting podcast status: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

@router.get("/available_voices", response_model=List[VoiceResponse])
async def get_available_voices():
    """Get list of available voices from ElevenLabs."""
    try:
        # Validate API key
        validate_api_keys()
        
        # Make direct API request to ensure we get fresh data
        url = "https://api.elevenlabs.io/v2/voices"
        headers = {
            "xi-api-key": ELEVENLABS_API_KEY
        }
        params = {
            "include_total_count": True
        }
        
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        
        voices_data = response.json()
        
        # Transform the response into our model
        voices = []
        for voice in voices_data.get("voices", []):
            voices.append(VoiceResponse(
                voice_id=voice["voice_id"],
                name=voice["name"],
                category=voice.get("category"),
                description=voice.get("description"),
                labels=voice.get("labels"),
                preview_url=voice.get("preview_url"),
                available_for_tiers=voice.get("available_for_tiers")
            ))
            
            # Log available voices for debugging
            logger.info(f"Found voice: {voice['name']} ({voice['voice_id']})")
        
        if not voices:
            logger.warning("No voices found in the response")
            
        return voices
        
    except Exception as e:
        logger.error(f"Error fetching voices: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch voices: {str(e)}"
        )

@router.get("/voice/{voice_id}")
async def get_voice(voice_id: str):
    """Get details of a specific voice."""
    try:
        # Validate API key
        validate_api_keys()
        
        # Make direct API request
        url = f"https://api.elevenlabs.io/v2/voices/{voice_id}"
        headers = {
            "xi-api-key": ELEVENLABS_API_KEY
        }
        
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        voice = response.json()
        
        return {
            "voice_id": voice["voice_id"],
            "name": voice["name"],
            "category": voice.get("category"),
            "description": voice.get("description"),
            "labels": voice.get("labels"),
            "preview_url": voice.get("preview_url"),
            "settings": voice.get("settings"),
            "available_for_tiers": voice.get("available_for_tiers")
        }
        
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            raise HTTPException(
                status_code=404,
                detail=f"Voice not found: {voice_id}"
            )
        raise HTTPException(
            status_code=e.response.status_code,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error fetching voice {voice_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch voice: {str(e)}"
        )

@router.delete("/podcast/{podcast_id}")
async def delete_podcast(podcast_id: str):
    """Delete a podcast and its associated audio file."""
    try:
        with get_database_instance().get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT audio_url
                FROM podcasts
                WHERE id = ?
            """, (podcast_id,))
            
            result = cursor.fetchone()
            
            if not result:
                raise HTTPException(
                    status_code=404,
                    detail=f"Podcast {podcast_id} not found"
                )
            
            audio_url = result[0]
            
            # Delete podcast record
            cursor.execute("""
                DELETE FROM podcasts
                WHERE id = ?
            """, (podcast_id,))
            conn.commit()
            
            # Delete audio file
            if audio_url and audio_url.startswith("/static/audio/"):
                # Derive the file system path of the generated audio
                ensure_audio_directory()
                filename = audio_url.split("/static/audio/")[1]
                audio_path = AUDIO_DIR / filename
                if audio_path.exists():
                    audio_path.unlink()
            
            return {"message": f"Podcast {podcast_id} and associated audio file deleted successfully"}
            
    except Exception as e:
        logger.error(f"Error deleting podcast: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

# ---------------------------------------------------------------------------
# Helper – generate a podcast script from article records
# ---------------------------------------------------------------------------


def _generate_script_from_articles(
    *,
    podcast_name: str,
    episode_title: str,
    host_name: str,
    guest_name: str,
    guest_title: str,
    duration: str,
    mode: str,
    articles: List[dict],
    llm_model: str,
) -> str:
    """Call the LLM (via LiteLLMModel) to create a podcast script for the
    given set of articles. This mirrors the logic in the /generate_podcast_script
    endpoint so that we can auto‑generate the script before TTS.
    """

    # Prepare article blocks
    article_blocks: List[str] = []
    for art in articles:
        block = [
            f"Title: {art.get('title')}",
            f"Summary: {art.get('summary')}",
            f"Category: {art.get('category', 'N/A')}",
            f"Future Signal: {art.get('future_signal', 'N/A')}",
            f"Future Signal Explanation: {art.get('future_signal_explanation', 'N/A')}",
            f"Sentiment: {art.get('sentiment', 'N/A')}",
            f"Sentiment Explanation: {art.get('sentiment_explanation', 'N/A')}",
            f"Time to Impact: {art.get('time_to_impact', 'N/A')}",
            f"Time to Impact Explanation: {art.get('time_to_impact_explanation', 'N/A')}",
            f"Driver Type: {art.get('driver_type', 'N/A')}",
            f"Driver Type Explanation: {art.get('driver_type_explanation', 'N/A')}" ,
        ]
        article_blocks.append("\n".join(block))

    combined_articles = "\n\n---\n\n".join(article_blocks)

    # Load prompt template
    prompt_template = load_prompt_template(mode, duration)

    class _SafeDict(dict):
        def __missing__(self, key):
            return "{" + key + "}"

    system_prompt = prompt_template.format_map(
        _SafeDict(
            podcast_name=podcast_name,
            episode_title=episode_title,
            host_name=host_name,
            guest_title=guest_title,
            guest_name=guest_name,
        )
    )

    # Add explicit generation guidelines to reduce excessive non-verbals and
    # extremely short / long lines which can cause the TTS engine to speed
    # up unnaturally.
    guidelines = (
        "### Generation Guidelines for Podcast Script\n"
        "1. Alternate speaker tags beginning with [S1] for the host and [S2] for the guest; never repeat the same tag twice in a row.\n"
        "2. Keep each spoken sentence between 5–20 seconds of speech (≈40–160 tokens).\n"
        "3. Use non-verbal cues sparingly and where it has the greatest emotional impact. Never more than one per speaker turn. Never output a line that only contains a non-verbal.\n"
        "4. Allowed non-verbal tags: (laughs), (clears throat), (sighs), (gasps), (coughs), (singing), (sings), (mumbles), (beep), (groans), (sniffs), (claps), (screams), (inhales), (exhales), (applause), (burps), (humming), (sneezes), (chuckle), (whistles).\n"
        "5. Avoid very short (<5 s) or very long (>20 s) speaker blocks to prevent unnatural TTS speed.\n"
    )

    system_prompt = f"{system_prompt}\n\n{guidelines}"

    # Get model and generate
    model_instance = LiteLLMModel.get_instance(llm_model)
    if not model_instance:
        raise RuntimeError(f"AI model '{llm_model}' is not configured or unavailable")

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": combined_articles},
    ]

    logger.info("Generating podcast script via LLM – articles: %d", len(articles))
    raw_script = model_instance.generate_response(messages)
    script = _postprocess_script(raw_script or "")
    if not script:
        raise RuntimeError("LLM returned empty script")

    return script

def to_dia_tags(script: str) -> str:
    """Convert a markdown-like podcast script to Dia format.

    • Prepend alternating `[S1]` / `[S2]` tags for each non-blank paragraph.
    • Retain speaker names (if we can detect them) before the text so Dia can
      still voice-switch by tag while listeners hear the real name.
    • Emotional cues such as `(laughs)` are kept untouched.
    """

    if re.search(r"^\s*\[S[12]\]", script, flags=re.MULTILINE):
        # Collapse blank lines only
        return re.sub(r"\r?\n[ \t]*\r?\n", "\n", script)

    speaker_tag = "S1"
    out_lines: list[str] = []

    for raw in script.splitlines():
        text = raw.rstrip()

        # Skip fenced-code markers that sometimes remain at start/end
        if re.match(r"^(\[S[12]\]\s*)?```(?:markdown)?\s*$", text, re.I):
            continue

        # Remove leading/trailing bold/italic markers (**, __, *, _)
        text = re.sub(r"^\s*(\*\*|__|\*|_)+", "", text)
        text = re.sub(r"(\*\*|__|\*|_)+\s*$", "", text)

        name: str | None = None

        # Pattern 1: [Name - Role] ... optional second bracket for emotion
        m = re.match(r"^\[([^\]]+?)\]", text)
        if m:
            bracket_content = m.group(1)
            # Split on any Unicode dash (hyphen, figure dash, en/em, non-breaking, etc.)
            name = re.split(r"\s*[\-\u2010-\u2015]\s*", bracket_content, maxsplit=1)[0].strip()
            text = text[m.end():].lstrip()

        # Pattern 2: **Name:** dialogue
        if name is None:
            m = re.match(r"^\*\*(.+?)\*\*\s*:\s*(.*)", text)
            if m:
                name = m.group(1).strip()
                text = m.group(2).strip()

        # Pattern 3: Name: dialogue
        if name is None:
            m = re.match(r"^([A-Z][A-Za-z0-9 _\-]+?)\s*:\s*(.*)", text)
            if m:
                name = m.group(1).strip()
                text = m.group(2).strip()

        # After stripping speaker prefix, ignore if text now becomes empty or a structural heading
        if not text or re.match(r"^#", text) or re.match(r"^(intro|conclusion)[:\s]*$", text, re.I) or re.match(r"^segment\s+\d+[:\s]*$", text, re.I):
            continue

        # Assemble final line
        if name:
            out_lines.append(f"[{speaker_tag}] {name}: {text}")
        else:
            out_lines.append(f"[{speaker_tag}] {text}")

        speaker_tag = "S2" if speaker_tag == "S1" else "S1"

    cleaned = "\n".join(out_lines)
    # Collapse blank/whitespace-only lines (handles CRLF and spaces)
    cleaned = re.sub(r"\r?\n[ \t]*\r?\n", "\n", cleaned)
    return cleaned

# ---------------------------------------------------------------------------
# Dia format helper API
# ---------------------------------------------------------------------------

class DiaConvertRequest(BaseModel):
    script: str

@router.post("/dia/convert")
async def dia_convert_endpoint(req: DiaConvertRequest):
    """Return script converted to Dia `[S1]`/`[S2]` format."""
    if not req.script.strip():
        raise HTTPException(status_code=400, detail="Empty script")
    try:
        converted = to_dia_tags(req.script)
        return {"script": converted}
    except Exception as exc:
        logger.error("Dia convert error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))

# ---------------------------------------------------------------------------
# Simple Dia TTS proxy endpoint (front-end script editor)
# ---------------------------------------------------------------------------

class DiaTTSRequest(BaseModel):
    text: str
    output_format: str = "mp3"
    speed_factor: Optional[float] = None

@router.post("/dia/tts")
async def dia_tts_endpoint(req: DiaTTSRequest):
    """Proxy call to Dia service; returns raw audio bytes."""
    try:
        from app.services import dia_client
        if not req.text.strip():
            raise HTTPException(status_code=400, detail="Empty text")
        text = req.text
        if not text.strip().startswith("[S1]"):
            text = to_dia_tags(text)

        # Split overly long scripts to avoid Dia's ~30-second truncation
        MAX_CHARS = 2500  # ≈360 tokens / ~30 s of audio
        chunks = (
            [text]
            if len(text) <= MAX_CHARS
            else split_into_chunks(text, max_chars=MAX_CHARS)
        )

        audio_parts: list[bytes] = []
        for chunk in chunks:
            part = await dia_client.tts(
                chunk,
                output_format=req.output_format,
                speed_factor=req.speed_factor,
            )
            audio_parts.append(part)

        if len(audio_parts) == 1:
            audio = audio_parts[0]
        else:
            tmp_filename = f"dia_{uuid.uuid4().hex}.mp3"
            combine_audio_files(audio_parts, tmp_filename)
            final_path = (AUDIO_DIR / tmp_filename).resolve()
            audio = final_path.read_bytes()

        media_type = "audio/mpeg" if req.output_format.startswith("mp3") else "application/octet-stream"
        from fastapi.responses import Response
        return Response(content=audio, media_type=media_type)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Dia TTS endpoint error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))

# ---------------------------------------------------------------------------
# Full Dia podcast generation (background) – similar flow to ElevenLabs
# ---------------------------------------------------------------------------


class DiaPodcastRequest(BaseModel):
    """Payload for Dia podcast generation (with background worker).

    We keep the structure minimal – only script text is required.  If the
    script is omitted but *article_uris* are supplied, we auto-generate the
    script via the same LLM helper that ElevenLabs uses.
    """

    # Core metadata
    podcast_name: str = "Aunoo News"
    episode_title: str = "Untitled Episode"

    # Either ready script or articles list
    text: Optional[str] = None  # final Dia-formatted script (preferred)
    article_uris: Optional[List[str]] = None  # to auto-generate if text empty

    # Generation params
    speed_factor: float = 0.94
    seed: Optional[int] = None
    max_tokens: Optional[int] = None
    audio_prompt: Optional[str] = None  # base64 / URL handled upstream
    output_format: str = "mp3"

    # Script generation fallback extras
    model: str = "gpt-4o"
    duration: str = "medium"
    host_name: Optional[str] = "Aunoo"
    guest_name: Optional[str] = "Auspex"
    guest_title: Optional[str] = "Guest"
    mode: str = "conversation"  # conversation | bulletin
    topic: Optional[str] = None


@router.post("/dia/generate_podcast")
async def dia_generate_podcast(request: DiaPodcastRequest):
    """Launch Dia podcast generation in the background (returns podcast_id)."""

    podcast_id = str(uuid.uuid4())

    # Pre-insert DB row so UI can poll status
    try:
        db = get_database_instance()
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO podcasts (
                    id, title, status, created_at, transcript, metadata
                ) VALUES (?, ?, 'processing', CURRENT_TIMESTAMP, ?, ?)
                """,
                (
                    podcast_id,
                    f"{request.podcast_name} - {request.episode_title}",
                    request.text or "",
                    json.dumps({}),
                ),
            )
            conn.commit()

        # Run heavy generation in background thread so HTTP returns fast
        threading.Thread(
            target=lambda: asyncio.run(_run_dia_podcast_worker(podcast_id, request)),
            daemon=True,
        ).start()

        return {"success": True, "podcast_id": podcast_id, "status": "processing"}

    except Exception as exc:
        logger.error("Failed enqueue Dia podcast: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


async def _run_dia_podcast_worker(podcast_id: str, req: DiaPodcastRequest):
    """Background job that generates a Dia TTS podcast and stores result."""

    logger.info("[DiaWorker] Start podcast %s", podcast_id)
    try:
        # Step 1 – ensure script text
        script_text = (req.text or "").strip()
        if not script_text and req.article_uris:
            # Auto-generate via same helper
            db = get_database_instance()
            articles = [db.get_article(u) for u in req.article_uris]
            articles = [a for a in articles if a]
            if not articles:
                raise ValueError("No articles found for provided URIs")

            script_text = _generate_script_from_articles(
                podcast_name=req.podcast_name,
                episode_title=req.episode_title,
                host_name=req.host_name or "Aunoo",
                guest_name=req.guest_name or "Auspex",
                guest_title=req.guest_title or "Guest",
                duration=req.duration,
                mode=req.mode,
                articles=articles,
                llm_model=req.model,
            )

        if not script_text:
            raise ValueError("Empty script text for Dia podcast")

        # Ensure Dia tag format
        if not script_text.strip().startswith("[S1]"):
            script_text = to_dia_tags(script_text)

        # Prepare speaker-specific chunks (Dia ~30 s limit)
        chunks = _split_by_speaker(script_text, max_chars=2500)

        # Ensure audio directory exists
        if not ensure_audio_directory():
            raise RuntimeError("Unable to create audio directory")

        from app.services import dia_client

        seed = req.seed or random.randint(1, 2**31 - 1)

        audio_parts: list[bytes] = []
        for chunk in chunks:
            part = await dia_client.tts(
                chunk,
                output_format=req.output_format,
                speed_factor=req.speed_factor,
                seed=seed,
                max_tokens=req.max_tokens or math.ceil(len(chunk) / 6),
                audio_prompt=req.audio_prompt,
            )
            audio_parts.append(part)

        # Merge
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"dia_{podcast_id}_{timestamp}.{req.output_format}"

        duration = combine_audio_files(audio_parts, output_filename)

        meta = {
            "duration": round(duration / 60, 2),
            "podcast_name": req.podcast_name,
            "episode_title": req.episode_title,
            "mode": req.mode,
            "topic": req.topic,
            "seed": seed,
            "segments": len(chunks),
        }

        db = get_database_instance()
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE podcasts
                SET status = 'completed',
                    audio_url = ?,
                    completed_at = CURRENT_TIMESTAMP,
                    error = NULL,
                    metadata = ?
                WHERE id = ?
                """,
                (
                    f"/static/audio/{output_filename}",
                    json.dumps(meta),
                    podcast_id,
                ),
            )
            conn.commit()

        logger.info("[DiaWorker] Podcast %s completed", podcast_id)

    except Exception as err:
        logger.error("[DiaWorker] Error %s: %s", podcast_id, err, exc_info=True)
        try:
            db = get_database_instance()
            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE podcasts
                    SET status = 'error', error = ?, completed_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (str(err), podcast_id),
                )
                conn.commit()
        except Exception as db_err:
            logger.error("[DiaWorker] DB update fail %s: %s", podcast_id, db_err)

# ---------------------------------------------------------------------------
# Speaker-aware chunking helpers
# ---------------------------------------------------------------------------


def _split_by_speaker(text: str, max_chars: int = 2500) -> list[str]:
    """Return blocks that contain only one speaker tag and fit <= max_chars.

    Each input line is expected to start with `[S1]` or `[S2]` (after optional
    whitespace).  We accumulate consecutive lines for the same speaker until
    a different tag is encountered *or* adding the next line would exceed
    *max_chars*.  This prevents Dia from trying to voice-switch inside a
    single HTTP request and keeps each request under Dia's ~30-second limit.
    """

    blocks: list[str] = []
    current_lines: list[str] = []
    current_len = 0
    current_speaker = None

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue

        m = re.match(r"^\[S([12])\]", line)
        speaker = m.group(0) if m else None

        # Determine if we must flush: speaker change OR would exceed max_chars
        projected_len = current_len + len(line) + 1  # + newline
        if (
            (current_speaker is not None and speaker != current_speaker)
            or (projected_len > max_chars and current_lines)
        ):
            blocks.append("\n".join(current_lines))
            current_lines = [line]
            current_len = len(line) + 1
            current_speaker = speaker
        else:
            current_lines.append(line)
            current_len = projected_len
            current_speaker = current_speaker or speaker

    if current_lines:
        blocks.append("\n".join(current_lines))

    return blocks

# ---------------------------------------------------------------------------
# Post-processing helpers
# ---------------------------------------------------------------------------

_EMPTY_SPEAKER_RE = re.compile(
    r"^\s*\[S[12]\][^\]]*\]\s*(?:$|[\.,;!\?]?$)", re.IGNORECASE
)

def _postprocess_script(raw: str) -> str:
    """Remove empty speaker turns that contain only an emotion cue.

    The LLM sometimes emits lines like::

        [S1] Aunoo: [excited]

    which cause awkward silence and speed artefacts in TTS. We drop any line
    that matches this pattern (speaker tag + optional name + emotion cue) but
    no spoken words after the final closing bracket.
    """
    cleaned_lines: list[str] = []
    for line in raw.splitlines():
        if _EMPTY_SPEAKER_RE.match(line):
            continue  # skip empty expressive line
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines) 