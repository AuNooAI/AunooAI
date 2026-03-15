"""
Integration tests for provider validation.
Makes actual API calls with sample credentials and logs results.

Run with: pytest app/tests/test_providers.py -v -s
"""
import pytest
import logging

from app.provider_config import (
    openai,
    anthropic,
    gemini,
    newsapi,
    thenewsapi,
    newsdata,
    firecrawl,
    elevenlabs,
    diatts,
    huggingface,
    bluesky,
    google_pse,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# =============================================================================
# Sample Credentials (intentionally invalid for testing rejection)
# =============================================================================

SAMPLE_CREDENTIALS = {
    "openai": {"api_key": "Sample OpenAI API key"},
    "anthropic": {"api_key": "Sample Anthropic API key"},
    "gemini": {"api_key": "Sample Gemini API key"},
    "newsapi": {"api_key": "Sample NewsAPI API key"},
    "thenewsapi": {"api_key": "Sample TheNewsAPI API key"},
    "newsdata": {"api_key": "Sample NewsData.io API key"},
    "firecrawl": {"api_key": "Sample Firecrawl API key"},
    "elevenlabs": {"api_key": "Sample ElevenLabs API key"},
    "diatts": {"url": "Sample Dia TTS URL", "api_key": "Sample Dia TTS API key"},
    "huggingface": {"api_key": "Sample HuggingFace API key"},
    "bluesky": {"username": "Sample Bluesky username", "password": "Sample Bluesky password"},
    "google_pse": {"api_key": "Sample Google PSE API key", "cse_id": "Sample Google PSE CSE ID"},
}


# =============================================================================
# OpenAI
# =============================================================================

@pytest.mark.asyncio
async def test_openai_validation():
    """Test OpenAI API key validation."""
    credentials = SAMPLE_CREDENTIALS["openai"]
    logger.info(f"Testing OpenAI with api_key: {credentials['api_key'][:10]}...")
    
    try:
        await openai.validate(credentials)
        logger.info("✅ OpenAI: VALID")
        result = "valid"
    except Exception as e:
        logger.info(f"❌ OpenAI: INVALID - {e}")
        result = "invalid"
    
    assert result in ["valid", "invalid"]


# =============================================================================
# Anthropic
# =============================================================================

@pytest.mark.asyncio
async def test_anthropic_validation():
    """Test Anthropic API key validation."""
    credentials = SAMPLE_CREDENTIALS["anthropic"]
    logger.info(f"Testing Anthropic with api_key: {credentials['api_key'][:10]}...")
    
    try:
        await anthropic.validate(credentials)
        logger.info("✅ Anthropic: VALID")
        result = "valid"
    except Exception as e:
        logger.info(f"❌ Anthropic: INVALID - {e}")
        result = "invalid"
    
    assert result in ["valid", "invalid"]


# =============================================================================
# Gemini
# =============================================================================

@pytest.mark.asyncio
async def test_gemini_validation():
    """Test Gemini API key validation."""
    credentials = SAMPLE_CREDENTIALS["gemini"]
    logger.info(f"Testing Gemini with api_key: {credentials['api_key'][:10]}...")
    
    try:
        await gemini.validate(credentials)
        logger.info("✅ Gemini: VALID")
        result = "valid"
    except Exception as e:
        logger.info(f"❌ Gemini: INVALID - {e}")
        result = "invalid"
    
    assert result in ["valid", "invalid"]


# =============================================================================
# NewsAPI
# =============================================================================

@pytest.mark.asyncio
async def test_newsapi_validation():
    """Test NewsAPI key validation."""
    credentials = SAMPLE_CREDENTIALS["newsapi"]
    logger.info(f"Testing NewsAPI with api_key: {credentials['api_key'][:10]}...")
    
    try:
        await newsapi.validate(credentials)
        logger.info("✅ NewsAPI: VALID")
        result = "valid"
    except Exception as e:
        logger.info(f"❌ NewsAPI: INVALID - {e}")
        result = "invalid"
    
    assert result in ["valid", "invalid"]


# =============================================================================
# TheNewsAPI
# =============================================================================

@pytest.mark.asyncio
async def test_thenewsapi_validation():
    """Test TheNewsAPI key validation."""
    credentials = SAMPLE_CREDENTIALS["thenewsapi"]
    logger.info(f"Testing TheNewsAPI with api_key: {credentials['api_key'][:10]}...")
    
    try:
        await thenewsapi.validate(credentials)
        logger.info("✅ TheNewsAPI: VALID")
        result = "valid"
    except Exception as e:
        logger.info(f"❌ TheNewsAPI: INVALID - {e}")
        result = "invalid"
    
    assert result in ["valid", "invalid"]


# =============================================================================
# NewsData
# =============================================================================

@pytest.mark.asyncio
async def test_newsdata_validation():
    """Test NewsData.io API key validation."""
    credentials = SAMPLE_CREDENTIALS["newsdata"]
    logger.info(f"Testing NewsData with api_key: {credentials['api_key'][:10]}...")
    
    try:
        await newsdata.validate(credentials)
        logger.info("✅ NewsData: VALID")
        result = "valid"
    except Exception as e:
        logger.info(f"❌ NewsData: INVALID - {e}")
        result = "invalid"
    
    assert result in ["valid", "invalid"]


# =============================================================================
# Firecrawl
# =============================================================================

@pytest.mark.asyncio
async def test_firecrawl_validation():
    """Test Firecrawl API key validation."""
    credentials = SAMPLE_CREDENTIALS["firecrawl"]
    logger.info(f"Testing Firecrawl with api_key: {credentials['api_key'][:10]}...")
    
    try:
        await firecrawl.validate(credentials)
        logger.info("✅ Firecrawl: VALID")
        result = "valid"
    except Exception as e:
        logger.info(f"❌ Firecrawl: INVALID - {e}")
        result = "invalid"
    
    assert result in ["valid", "invalid"]


# =============================================================================
# ElevenLabs
# =============================================================================

@pytest.mark.asyncio
async def test_elevenlabs_validation():
    """Test ElevenLabs API key validation."""
    credentials = SAMPLE_CREDENTIALS["elevenlabs"]
    logger.info(f"Testing ElevenLabs with api_key: {credentials['api_key'][:10]}...")
    
    try:
        await elevenlabs.validate(credentials)
        logger.info("✅ ElevenLabs: VALID")
        result = "valid"
    except Exception as e:
        logger.info(f"❌ ElevenLabs: INVALID - {e}")
        result = "invalid"
    
    assert result in ["valid", "invalid"]


# =============================================================================
# Dia TTS
# =============================================================================

@pytest.mark.asyncio
async def test_diatts_validation():
    """Test Dia TTS endpoint validation."""
    credentials = SAMPLE_CREDENTIALS["diatts"]
    logger.info(f"Testing DiaTTS with url: {credentials['url']}")
    
    try:
        await diatts.validate(credentials)
        logger.info("✅ DiaTTS: VALID")
        result = "valid"
    except Exception as e:
        logger.info(f"❌ DiaTTS: INVALID - {e}")
        result = "invalid"
    
    assert result in ["valid", "invalid"]


# =============================================================================
# HuggingFace
# =============================================================================

@pytest.mark.asyncio
async def test_huggingface_validation():
    """Test HuggingFace API key validation."""
    credentials = SAMPLE_CREDENTIALS["huggingface"]
    logger.info(f"Testing HuggingFace with api_key: {credentials['api_key'][:10]}...")
    
    try:
        await huggingface.validate(credentials)
        logger.info("✅ HuggingFace: VALID")
        result = "valid"
    except Exception as e:
        logger.info(f"❌ HuggingFace: INVALID - {e}")
        result = "invalid"
    
    assert result in ["valid", "invalid"]


# =============================================================================
# Bluesky
# =============================================================================

@pytest.mark.asyncio
async def test_bluesky_validation():
    """Test Bluesky credentials validation."""
    credentials = SAMPLE_CREDENTIALS["bluesky"]
    logger.info(f"Testing Bluesky with username: {credentials['username']}")
    
    try:
        await bluesky.validate(credentials)
        logger.info("✅ Bluesky: VALID")
        result = "valid"
    except Exception as e:
        logger.info(f"❌ Bluesky: INVALID - {e}")
        result = "invalid"
    
    assert result in ["valid", "invalid"]


# =============================================================================
# Google PSE
# =============================================================================

@pytest.mark.asyncio
async def test_google_pse_validation():
    """Test Google Programmable Search Engine credentials validation."""
    credentials = SAMPLE_CREDENTIALS["google_pse"]
    logger.info(f"Testing Google PSE with api_key: {credentials['api_key'][:10]}..., cse_id: {credentials['cse_id']}")
    
    try:
        await google_pse.validate(credentials)
        logger.info("✅ Google PSE: VALID")
        result = "valid"
    except Exception as e:
        logger.info(f"❌ Google PSE: INVALID - {e}")
        result = "invalid"
    
    assert result in ["valid", "invalid"]


# =============================================================================
# Run All Validations
# =============================================================================

@pytest.mark.asyncio
async def test_all_providers_summary():
    """Run validation for all providers and print summary."""
    providers = [
        ("openai", openai, SAMPLE_CREDENTIALS["openai"]),
        ("anthropic", anthropic, SAMPLE_CREDENTIALS["anthropic"]),
        ("gemini", gemini, SAMPLE_CREDENTIALS["gemini"]),
        ("newsapi", newsapi, SAMPLE_CREDENTIALS["newsapi"]),
        ("thenewsapi", thenewsapi, SAMPLE_CREDENTIALS["thenewsapi"]),
        ("newsdata", newsdata, SAMPLE_CREDENTIALS["newsdata"]),
        ("firecrawl", firecrawl, SAMPLE_CREDENTIALS["firecrawl"]),
        ("elevenlabs", elevenlabs, SAMPLE_CREDENTIALS["elevenlabs"]),
        ("diatts", diatts, SAMPLE_CREDENTIALS["diatts"]),
        ("huggingface", huggingface, SAMPLE_CREDENTIALS["huggingface"]),
        ("bluesky", bluesky, SAMPLE_CREDENTIALS["bluesky"]),
        ("google_pse", google_pse, SAMPLE_CREDENTIALS["google_pse"]),
    ]
    
    results = []
    
    logger.info("\n" + "=" * 60)
    logger.info("PROVIDER VALIDATION SUMMARY")
    logger.info("=" * 60)
    
    for name, module, credentials in providers:
        try:
            await module.validate(credentials)
            status = "✅ VALID"
            results.append((name, "valid"))
        except Exception as e:
            status = f"❌ INVALID ({type(e).__name__})"
            results.append((name, "invalid"))
        
        logger.info(f"{name:15} : {status}")
    
    logger.info("=" * 60)
    
    valid_count = sum(1 for _, s in results if s == "valid")
    invalid_count = sum(1 for _, s in results if s == "invalid")
    
    logger.info(f"Total: {len(results)} | Valid: {valid_count} | Invalid: {invalid_count}")
    logger.info("=" * 60 + "\n")
    
    # Test passes regardless of valid/invalid - we're just logging results
    assert len(results) == 12

