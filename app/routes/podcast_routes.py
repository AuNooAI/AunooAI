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
from ..utils.audio import combine_audio_files, save_audio_file, AUDIO_DIR, ensure_audio_directory
from ..config import settings
import requests
from sqlalchemy.orm import Session
from ..models.article import Article
import uuid
import random
import io
from pathlib import Path
import re

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

# Add template storage
TEMPLATES = {
    "default": {
        "name": "Default Template",
        "content": """
[Host]: Welcome to our podcast! Today we'll be discussing some fascinating developments in {topic}.

{articles_discussion}

[Host]: That wraps up our discussion for today. Thanks for listening!
"""
    }
}

class PodcastTemplate(BaseModel):
    name: str
    content: str

@router.get("/podcast_templates/{template_name}")  # Changed from /templates to /podcast_templates
async def get_podcast_template(template_name: str):
    """Get a podcast script template by name.

    The front‑end expects a JSON object with a `template` key holding
    the template markdown itself. We therefore wrap the stored
    template's `content` so the structure matches what the UI expects.
    """
    if template_name not in TEMPLATES:
        raise HTTPException(status_code=404, detail=f"Template '{template_name}' not found")

    template = TEMPLATES[template_name]
    # Backwards compatible payload – both old (content) and new (template)
    return {
        "name": template_name,
        "content": template["content"],
        "template": template["content"],  # alias used by existing JS
    }

@router.post("/podcast_templates")  # Changed from /templates to /podcast_templates
async def save_podcast_template(template: PodcastTemplate):
    """Save a podcast script template."""
    TEMPLATES[template.name] = {
        "name": template.name,
        "content": template.content
    }
    return {"message": f"Template '{template.name}' saved successfully"}

@router.get("/podcast_templates")  # Changed from /templates to /podcast_templates
async def list_podcast_templates():
    """List all available podcast templates."""
    return list(TEMPLATES.values())

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
    podcast_name: str
    episode_title: str
    script: str
    host_name: Optional[str] = "Aunoo"
    host_voice_id: str
    guest_voice_id: Optional[str] = None
    guest_title: str
    guest_name: str
    mode: str = "conversation"  # "conversation" or "bulletin"
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
            return data.get("system_prompt", "")
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

        system_prompt = prompt_template.format(
            podcast_name=request.podcast_name,
            episode_title=request.episode_title,
            host_name=(request.host_name or "Aunoo"),
            guest_title=(request.guest_title or "Guest"),
            guest_name=(request.guest_name or "Auspex"),
        )
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
        
        logger.info("Processing model response")
        script = response
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

@router.post("/generate_tts_podcast")
async def generate_tts_podcast(
    request: TTSPodcastRequest,
    podcast_name: str = "Aunoo Live",
    episode_title: str = "Latest Updates",
    guest_name: str = "Auspex",
    output_filename: str = None
):
    """
    Generate a TTS podcast from the provided script.
    
    Args:
        request: TTSPodcastRequest object containing script and voice settings
        podcast_name: Name of the podcast (default: "Aunoo Live")
        episode_title: Title of the episode (default: "Latest Updates")
        guest_name: Name of the guest (default: "Auspex")
        output_filename: Optional output filename
        
    Returns:
        dict: Response containing podcast details
    """
    podcast_id = None
    try:
        # Generate a unique podcast ID
        podcast_id = str(uuid.uuid4())
        
        # Validate API keys before proceeding
        validate_api_keys()
        
        # Create initial podcast record
        with get_database_instance().get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO podcasts (
                    id, title, status, created_at, transcript
                ) VALUES (?, ?, 'processing', CURRENT_TIMESTAMP, ?)
            """, (
                podcast_id,
                f"{podcast_name} - {episode_title}",
                request.script
            ))
            conn.commit()
        
        # Determine mode and guest voice
        available_voices = await get_available_voices()

        if request.mode == "bulletin":
            guest_voice = None  # Not used
        else:
            # If user specified a guest voice id try to match it; otherwise randomise
            if request.guest_voice_id:
                guest_voice = next((v for v in available_voices if v.voice_id == request.guest_voice_id), None)
                if guest_voice is None:
                    raise HTTPException(status_code=400, detail="Invalid guest_voice_id provided")
            else:
                guest_voice = random.choice([v for v in available_voices if v.voice_id != request.host_voice_id])

            # Randomise name/title if requested or missing
            if not request.guest_name or request.guest_name.lower() == "random":
                request.guest_name = guest_voice.name.split()[0] if guest_voice and guest_voice.name else "Guest"

            if not request.guest_title or request.guest_title.lower() == "random":
                random_titles = [
                    "Industry Expert",
                    "Chief Futurist",
                    "Senior Analyst",
                    "Innovation Strategist",
                ]
                request.guest_title = random.choice(random_titles)
        
        # Determine host alias list for voice selection
        host_aliases = { (request.host_name or "Aunoo").lower(), "annie", "host" }

        # Split script into sections by speaker
        script_sections = []
        current_section = {"speaker": None, "text": "", "emotion": None}

        for line in request.script.split('\n'):
            raw = line.strip()
            # Remove leading markdown bold/italic markers for detection
            stripped = raw.lstrip('*').lstrip('_').strip()

            speaker_detected = None
            role = None

            # Pattern 1: [Speaker - Role]
            if stripped.startswith('[') and ']' in stripped:
                # Save the previous section before starting a new one
                if current_section["speaker"]:
                    script_sections.append(current_section)

                # Extract the first bracket block – this always contains the speaker (and optional role)
                first_close_idx = stripped.find(']')
                header = stripped[1:first_close_idx]
                speaker, role = (header.split(' - ') + [None])[:2] if ' - ' in header else (header, None)

                # Attempt to extract a second bracket block which might hold an emotion/context label
                emotion = None
                remaining_after_first = stripped[first_close_idx + 1:].lstrip()
                if remaining_after_first.startswith('[') and ']' in remaining_after_first:
                    second_close_idx = remaining_after_first.find(']')
                    emotion = remaining_after_first[1:second_close_idx].strip()
                    remaining_after_first = remaining_after_first[second_close_idx + 1:].lstrip()

                # Anything left after the bracket blocks is actual spoken text – capture it
                initial_text = remaining_after_first + "\n" if remaining_after_first else ""

                speaker_detected = speaker
                current_section = {
                    "speaker": speaker_detected,
                    "role": role,
                    "text": initial_text,
                    "emotion": emotion
                }
            else:
                # Pattern 2: **Speaker**: text
                m = re.match(r"^\*\*(.+?)\*\*:\s*(.*)$", raw)
                if m:
                    speaker_detected = m.group(1).strip()
                    line_text = m.group(2)
                    # Save previous
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

        # Add last section
        if current_section["speaker"]:
            script_sections.append(current_section)

        # Fallback: if no speaker blocks detected, treat the entire script as one host section
        if not script_sections:
            logger.warning("No speaker blocks detected in script; using entire script as single host section")
            script_sections.append({
                "speaker": "annie",  # default host speaker identifier
                "role": "Host",
                "text": request.script,
                "emotion": None,
            })

        # Generate audio for each section
        audio_segments = []
        client = ElevenLabs(api_key=ELEVENLABS_API_KEY)

        # Utility to clean out non‑verbal stage directions (e.g. "Intro music fades in")
        def clean_text(raw: str) -> str:
            text = raw
            # Remove [bracket] or (parenthesis) stage directions that mention music/sfx
            text = re.sub(r"\[(?:[^\]]*(music|sound|sfx|fade)[^\]]*)\]", "", text, flags=re.IGNORECASE)
            text = re.sub(r"\((?:[^)]*(music|sound|sfx|fade)[^)]*)\)", "", text, flags=re.IGNORECASE)

            # Remove bold speaker cues (again) during cleaning step
            text = re.sub(r"^\*\*[\w\s\-]+:\*\*", "", text, flags=re.MULTILINE)
            text = re.sub(r"^\*\*[\w\s\-]+\*\*:\s*", "", text, flags=re.MULTILINE)

            cleaned_lines = []
            for ln in text.splitlines():
                lowered = ln.lower()
                # Skip if line still primarily looks like a stage direction
                if any(kw in lowered for kw in ["intro music", "music fades", "sound effect", "sfx", "fade in", "fade out"]):
                    continue
                # Skip heading lines like "Podcast Script for ..."
                if "podcast script" in lowered:
                    continue
                cleaned_lines.append(ln)
            return "\n".join(cleaned_lines)

        for section in script_sections:
            # Determine voice mapping
            if request.mode == "bulletin":
                voice_id = request.host_voice_id
            else:
                voice_id = request.host_voice_id if section["speaker"].lower() in host_aliases else guest_voice.voice_id

            # Convert voice settings to dict for the API
            voice_settings_dict = {
                "stability": request.voice_settings.stability,
                "similarity_boost": request.voice_settings.similarity_boost,
                "style": request.voice_settings.style,
                "use_speaker_boost": request.voice_settings.use_speaker_boost,
                "speed": request.voice_settings.speed
            }

            # ElevenLabs currently has a ~2.5 k character limit per TTS request.
            # Break long sections into safe-sized chunks so we do not silently lose content.
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

                    # Collect audio bytes
                    audio_bytes = b"".join(b if isinstance(b, bytes) else b.encode() for b in audio_generator)

                    # Verify audio bytes
                    if not audio_bytes:
                        logger.warning(f"Empty audio bytes received for section: {section['speaker']} (chunk {chunk_index})")
                        continue

                    audio_segments.append(audio_bytes)
                    logger.info(
                        f"Successfully generated audio for section: {section['speaker']} (chunk {chunk_index}, size: {len(audio_bytes)} bytes)"
                    )
                except Exception as e:
                    logger.error(
                        f"Error generating audio for section {section['speaker']} (chunk {chunk_index}): {str(e)}"
                    )
                    # Continue with other chunks / sections even if one fails
                    continue
        
        # Check if we have any audio segments
        if not audio_segments:
            raise ValueError("No audio segments were generated successfully")
        
        # Generate output filename
        if not output_filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_filename = f"podcast_{podcast_id}_{timestamp}.mp3"
        
        try:
            # Ensure audio directory exists
            if not ensure_audio_directory():
                raise RuntimeError("Could not create or access audio directories")
            
            # Combine all audio segments using the utility function
            duration = combine_audio_files(audio_segments, output_filename)
            
            # Update podcast record with success
            with get_database_instance().get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE podcasts 
                    SET status = 'completed',
                        audio_url = ?,
                        completed_at = CURRENT_TIMESTAMP,
                        error = NULL
                    WHERE id = ?
                """, (
                    f"/static/audio/{output_filename}",
                    podcast_id
                ))
                conn.commit()
            
            return {
                "success": True,
                "podcast_id": podcast_id,
                "name": podcast_name,
                "episode_title": episode_title,
                "guest_name": guest_name,
                "filename": output_filename,
                "status": "completed",
                "audio_url": f"/static/audio/{output_filename}",
                "transcript": request.script,
                "duration": duration
            }
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error saving podcast audio: {error_msg}")
            
            # Update podcast record with error
            with get_database_instance().get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE podcasts 
                    SET status = 'error',
                        error = ?,
                        completed_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (error_msg, podcast_id))
                conn.commit()
            
            raise HTTPException(
                status_code=500,
                detail=f"Error saving podcast audio: {error_msg}"
            )
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error generating TTS podcast: {error_msg}")
        
        if podcast_id:
            try:
                # Update podcast record with error
                with get_database_instance().get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        UPDATE podcasts 
                        SET status = 'error',
                            error = ?,
                            completed_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                    """, (error_msg, podcast_id))
                    conn.commit()
            except Exception as db_error:
                logger.error(f"Error updating podcast status: {str(db_error)}")
        
        raise HTTPException(
            status_code=500,
            detail=error_msg
        )

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
                source={
                    "type": "text",
                    "text": source_text
                },
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
                ','.join(request.article_uris)  # article_uris as comma-separated string
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
                SELECT title, transcript
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
                SELECT id, title, status, audio_url, created_at, completed_at, error, transcript
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
                    "transcript": row[7] if row[7] else ""  # Ensure transcript is never null
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
                SELECT id, title, status, audio_url, created_at, completed_at, error, transcript
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
                "transcript": result[7]
            }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting podcast status: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

@router.get("/list", response_model=List[PodcastResponse])
async def list_podcasts():
    try:
        client = ElevenLabs(api_key=os.getenv("ELEVENLABS_API_KEY"))
        podcasts = client.studio.list_podcasts()
        
        return [
            PodcastResponse(
                podcast_id=p["podcast_id"],
                title=p["title"],
                status=p["status"],
                created_at=datetime.fromtimestamp(p["created_at"]),
                audio_url=p.get("audio_url"),
                transcript=p.get("transcript")
            )
            for p in podcasts
        ]
    except Exception as e:
        logger.error(f"Error listing podcasts: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

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