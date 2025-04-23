from pathlib import Path
import logging
import os
import tempfile
from pydub.utils import which
from pydub import AudioSegment
import io
import shutil
import stat
import time

logger = logging.getLogger(__name__)

# Define audio directory as a constant using absolute path
BASE_DIR = Path(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
AUDIO_DIR = BASE_DIR / "static" / "audio"
USER_TEMP_DIR = Path(tempfile.gettempdir()) / "aunoo_audio"

def ensure_audio_directory():
    """Ensure the audio directory exists and has proper permissions."""
    try:
        # Create the main audio directory if it doesn't exist
        AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        
        # Create user-specific temp directory
        USER_TEMP_DIR.mkdir(parents=True, exist_ok=True)
        
        # Set directory permissions to allow writing
        try:
            os.chmod(str(AUDIO_DIR), stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)
            os.chmod(str(USER_TEMP_DIR), stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)
        except Exception as e:
            logger.warning(f"Could not set permissions on directories: {str(e)}")
        
        # Verify write permissions by attempting to create a test file
        test_file = USER_TEMP_DIR / ".test_write"
        try:
            test_file.touch()
            test_file.unlink()
            logger.info(f"Write permissions verified for temp directory: {USER_TEMP_DIR}")
            return True
        except Exception as e:
            logger.error(f"No write permissions for temp directory: {str(e)}")
            return False
            
    except Exception as e:
        logger.error(f"Error ensuring audio directories exist: {str(e)}")
        return False

# Ensure the audio directory exists and has permissions
if not ensure_audio_directory():
    raise RuntimeError(f"Could not create or access audio directories")

# Configure pydub to use the correct ffmpeg path
FFMPEG_DIR = BASE_DIR / "ffmpeg" / "ffmpeg-master-latest-win64-gpl" / "bin"
FFPROBE_PATH = str(FFMPEG_DIR / "ffprobe.exe")
FFMPEG_PATH = str(FFMPEG_DIR / "ffmpeg.exe")

# Check if FFmpeg is available
if not os.path.exists(FFMPEG_PATH) or not os.path.exists(FFPROBE_PATH):
    logger.warning(f"FFmpeg not found at {FFMPEG_PATH} or {FFPROBE_PATH}")
    logger.warning("Trying to find FFmpeg in system PATH...")
    
    # Try to find FFmpeg in system PATH
    ffmpeg_path = shutil.which("ffmpeg")
    ffprobe_path = shutil.which("ffprobe")
    
    if ffmpeg_path and ffprobe_path:
        logger.info(f"Found FFmpeg in system PATH: {ffmpeg_path}")
        logger.info(f"Found FFprobe in system PATH: {ffprobe_path}")
        FFMPEG_PATH = ffmpeg_path
        FFPROBE_PATH = ffprobe_path
    else:
        logger.error("FFmpeg not found in system PATH. Audio processing may not work correctly.")
        # Try to find ffmpeg in common locations
        common_paths = [
            "/usr/bin/ffmpeg",
            "/usr/local/bin/ffmpeg",
            "/opt/homebrew/bin/ffmpeg",  # macOS Homebrew
            "/usr/local/opt/ffmpeg/bin/ffmpeg",  # macOS Homebrew alternative
            "C:\\ffmpeg\\bin\\ffmpeg.exe",  # Windows common location
            "C:\\Program Files\\ffmpeg\\bin\\ffmpeg.exe",  # Windows Program Files
            "C:\\Program Files (x86)\\ffmpeg\\bin\\ffmpeg.exe"  # Windows Program Files (x86)
        ]
        
        for path in common_paths:
            if os.path.exists(path):
                logger.info(f"Found FFmpeg at common location: {path}")
                FFMPEG_PATH = path
                # Try to find corresponding ffprobe
                ffprobe_path = path.replace("ffmpeg", "ffprobe")
                if os.path.exists(ffprobe_path):
                    FFPROBE_PATH = ffprobe_path
                    logger.info(f"Found FFprobe at: {ffprobe_path}")
                    break

# Override pydub's which function to use our paths
def custom_which(program):
    if program == "ffprobe":
        return FFPROBE_PATH if os.path.exists(FFPROBE_PATH) else None
    elif program == "ffmpeg":
        return FFMPEG_PATH if os.path.exists(FFMPEG_PATH) else None
    return which(program)

# Monkey patch pydub's which function
import pydub.utils
pydub.utils.which = custom_which

def save_audio_file(audio_content: bytes, filename: str) -> str:
    """
    Save audio content to a file in the audio directory.
    
    Args:
        audio_content: Raw audio content in bytes
        filename: Name of the file to save
        
    Returns:
        str: Filename of the saved file
    """
    try:
        # First save to temp directory
        temp_path = USER_TEMP_DIR / filename
        logger.info(f"Saving audio file to temp location: {temp_path}")
        
        with open(temp_path, "wb") as f:
            f.write(audio_content)
            f.flush()
            os.fsync(f.fileno())
        
        # Then move to final location
        final_path = AUDIO_DIR / filename
        logger.info(f"Moving audio file to final location: {final_path}")
        
        # Use shutil.move which handles cross-device moves
        shutil.move(str(temp_path), str(final_path))
            
        logger.info(f"Successfully saved audio file to: {final_path}")
        return filename
        
    except Exception as e:
        logger.error(f"Error saving audio file {filename}: {str(e)}")
        logger.error(f"Current working directory: {os.getcwd()}")
        logger.error(f"AUDIO_DIR absolute path: {AUDIO_DIR.absolute()}")
        raise

def combine_audio_files(audio_contents: list[bytes], output_filename: str) -> float:
    """
    Combine multiple audio segments into a single file and return its duration.
    
    Args:
        audio_contents: List of audio contents in bytes
        output_filename: Name of the output file
        
    Returns:
        float: Duration of the combined audio in seconds
    """
    temp_dir = None
    temp_files = []
    segments = []
    combined = None
    max_retries = 3
    retry_delay = 0.5
    
    def cleanup_temp_dir():
        """Clean up temporary directory and its contents."""
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
                logger.info(f"Successfully removed temporary directory: {temp_dir}")
            except Exception as e:
                logger.warning(f"Failed to remove temporary directory {temp_dir}: {str(e)}")
    
    try:
        # Create a temporary directory with a unique name inside USER_TEMP_DIR
        temp_dir = tempfile.mkdtemp(prefix="podcast_temp_", dir=str(USER_TEMP_DIR))
        logger.info(f"Created temporary directory: {temp_dir}")
        
        # Create temporary files for each segment
        for i, content in enumerate(audio_contents):
            temp_path = Path(temp_dir) / f"temp_{i}.mp3"
            logger.info(f"Creating temporary file: {temp_path}")
            
            # Write the file
            with open(temp_path, "wb") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            
            # Verify the file exists and has content
            if not temp_path.exists():
                raise FileNotFoundError(f"Failed to create temporary file: {temp_path}")
            if temp_path.stat().st_size == 0:
                raise ValueError(f"Temporary file is empty: {temp_path}")
            
            temp_files.append(temp_path)
            logger.info(f"Successfully created temporary file: {temp_path} (size: {temp_path.stat().st_size} bytes)")
        
        # Combine audio segments with retries
        combined = AudioSegment.empty()
        for i, temp_file in enumerate(temp_files):
            logger.info(f"Loading audio segment from: {temp_file}")
            
            # Add detailed file checks
            if not temp_file.exists():
                logger.error(f"File not found before loading: {temp_file}")
                logger.error(f"Directory contents: {list(Path(temp_dir).glob('*'))}")
                raise FileNotFoundError(f"Temporary file not found: {temp_file}")
            
            file_size = temp_file.stat().st_size
            logger.info(f"File size before loading: {file_size} bytes")
            
            if file_size == 0:
                logger.error(f"File is empty before loading: {temp_file}")
                raise ValueError(f"Temporary file is empty: {temp_file}")
            
            # Read file with retries
            for retry in range(max_retries):
                try:
                    # Add a small delay between retries
                    if retry > 0:
                        time.sleep(retry_delay)
                    
                    # Read the file directly
                    with open(temp_file, "rb") as f:
                        content = f.read()
                    
                    logger.info(f"Successfully read {len(content)} bytes from file")
                    
                    # Create audio segment from memory buffer
                    segment = AudioSegment.from_file(io.BytesIO(content), format="mp3")
                    segments.append(segment)
                    combined += segment
                    logger.info(f"Successfully loaded and added segment from: {temp_file}")
                    break
                except Exception as e:
                    logger.warning(f"Attempt {retry + 1} failed to load segment from {temp_file}: {str(e)}")
                    if retry == max_retries - 1:
                        logger.error(f"All retries failed for {temp_file}")
                        raise
        
        # Save combined audio to temp directory first
        temp_output = USER_TEMP_DIR / output_filename
        logger.info(f"Saving combined audio to temp location: {temp_output}")
        
        # Export with explicit format and codec settings
        combined.export(
            str(temp_output),
            format="mp3",
            parameters=["-acodec", "libmp3lame", "-ar", "44100", "-ab", "128k"]
        )
        
        # Ensure the temp file exists before moving
        if not temp_output.exists():
            raise FileNotFoundError(f"Failed to create temporary output file: {temp_output}")
        
        # Move to final location
        final_output = AUDIO_DIR / output_filename
        logger.info(f"Moving combined audio to final location: {final_output}")
        
        # Ensure the destination directory exists
        final_output.parent.mkdir(parents=True, exist_ok=True)
        
        # Use copy2 and then remove instead of move to avoid cross-device issues
        shutil.copy2(str(temp_output), str(final_output))
        temp_output.unlink()
        
        # Verify the output file was created and has content
        if not final_output.exists():
            raise FileNotFoundError(f"Failed to create output file: {final_output}")
        if final_output.stat().st_size == 0:
            raise ValueError(f"Output file is empty: {final_output}")
        
        # Get duration in seconds
        duration = len(combined) / 1000.0
        logger.info(f"Combined audio duration: {duration:.2f} seconds")
        
        return duration
        
    except Exception as e:
        logger.error(f"Error combining audio files: {str(e)}")
        logger.error(f"Current working directory: {os.getcwd()}")
        logger.error(f"AUDIO_DIR absolute path: {AUDIO_DIR.absolute()}")
        if temp_dir:
            logger.error(f"Temp directory contents: {list(Path(temp_dir).glob('*'))}")
        raise
        
    finally:
        # Clear references to segments to release file handles
        segments.clear()
        combined = None
        
        # Clean up temporary directory
        cleanup_temp_dir() 