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

# Set up logging
logger = logging.getLogger(__name__)

# Get API keys from environment with defaults
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
ELEVENLABS_API_KEY = os.getenv('ELEVENLABS_API_KEY')
DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # Rachel's voice ID

# Default podcast script prompt template
PODCAST_SCRIPT_PROMPT = """
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
    """Get a podcast script template by name."""
    if template_name not in TEMPLATES:
        raise HTTPException(status_code=404, detail=f"Template '{template_name}' not found")
    return TEMPLATES[template_name]

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
    host_voice_id: str
    guest_title: str
    guest_name: str
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
    guest_title: str
    guest_name: str
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
        
        # Prepare the system prompt
        system_prompt = PODCAST_SCRIPT_PROMPT.format(
            podcast_name=request.podcast_name,
            episode_title=request.episode_title,
            guest_title=request.guest_title,
            guest_name=request.guest_name
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
        
        # Get available voices for guest selection
        available_voices = await get_available_voices()
        guest_voice = random.choice([v for v in available_voices if v.voice_id != request.host_voice_id])
        
        # Split script into sections by speaker
        script_sections = []
        current_section = {"speaker": None, "text": "", "emotion": None}
        
        for line in request.script.split('\n'):
            if line.strip().startswith('[') and ']' in line:
                # Save previous section if exists
                if current_section["speaker"]:
                    script_sections.append(current_section)
                
                # Parse new section header
                header = line[line.find('[')+1:line.find(']')]
                if ' - ' in header:
                    speaker, role = header.split(' - ')
                else:
                    speaker = header
                    role = None
                
                # Look for emotion in next bracket
                emotion = None
                if ']' in line and '[' in line[line.find(']')+1:]:
                    emotion = line[line.find(']')+1:line.find(']', line.find(']')+1)].strip()
                
                current_section = {
                    "speaker": speaker,
                    "role": role,
                    "text": "",
                    "emotion": emotion
                }
            else:
                current_section["text"] += line + "\n"
        
        # Add last section
        if current_section["speaker"]:
            script_sections.append(current_section)
        
        # Generate audio for each section
        audio_segments = []
        client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
        
        for section in script_sections:
            voice_id = request.host_voice_id if section["speaker"].lower() == "annie" else guest_voice.voice_id
            
            # Convert voice settings to dict for the API
            voice_settings_dict = {
                "stability": request.voice_settings.stability,
                "similarity_boost": request.voice_settings.similarity_boost,
                "style": request.voice_settings.style,
                "use_speaker_boost": request.voice_settings.use_speaker_boost,
                "speed": request.voice_settings.speed
            }
            
            audio_generator = client.text_to_speech.convert(
                voice_id=voice_id,
                text=section["text"].strip(),
                model_id=request.model_id,
                output_format=request.output_format,
                voice_settings=voice_settings_dict
            )
            
            # Collect audio bytes
            audio_bytes = b''
            for chunk in audio_generator:
                if isinstance(chunk, bytes):
                    audio_bytes += chunk
                else:
                    audio_bytes += chunk.encode()
            
            # Add audio bytes to segments list
            audio_segments.append(audio_bytes)
        
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