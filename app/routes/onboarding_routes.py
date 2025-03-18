from fastapi import APIRouter, Request, Depends, HTTPException, Body, Query
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from app.security.session import verify_session
from app.database import Database, get_database_instance
import os
import aiohttp
import logging
from typing import Dict
import json
from dotenv import load_dotenv, set_key
from litellm import completion

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/api/onboarding/validate-api-key")
async def validate_api_key(request: Request, key_data: Dict = Body(...)):
    """Validate and store API keys."""
    try:
        provider = key_data.get("provider")
        api_key = key_data.get("api_key")
        model = key_data.get("model", "")  # Get the specific model if provided
        
        if not provider or not api_key:
            raise HTTPException(
                status_code=400,
                detail="provider and api_key are required"
            )

        # Use the same path resolution as main.py
        env_path = os.path.join(os.path.dirname(__file__), '..', '..', '.env')
        logger.info(f"Using .env path: {env_path}")
        logger.info(f"File exists: {os.path.exists(env_path)}")

        # Test the API key before saving
        if provider == "newsapi":
            # Test NewsAPI key
            url = f"https://newsapi.org/v2/top-headlines?country=us&apiKey={api_key}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        error_data = await response.json()
                        error_msg = error_data.get('message', 'Invalid NewsAPI key')
                        raise HTTPException(status_code=400, detail=error_msg)
            
            # Save API key - using primary format
            primary_env_var = 'PROVIDER_NEWSAPI_KEY'
            secondary_env_var = 'NEWSAPI_KEY'

            # Read existing content
            try:
                with open(env_path, "r") as env_file:
                    lines = env_file.readlines()
            except FileNotFoundError:
                lines = []

            # Update or add both keys
            primary_line = f'{primary_env_var}="{api_key}"\n'
            secondary_line = f'{secondary_env_var}="{api_key}"\n'
            
            primary_found = False
            secondary_found = False

            for i, line in enumerate(lines):
                if line.startswith(f'{primary_env_var}='):
                    lines[i] = primary_line
                    primary_found = True
                elif line.startswith(f'{secondary_env_var}='):
                    lines[i] = secondary_line
                    secondary_found = True

            if not primary_found:
                lines.append(primary_line)
            if not secondary_found:
                lines.append(secondary_line)

            # Write back to .env
            with open(env_path, "w") as env_file:
                env_file.writelines(lines)

            # Update environment
            os.environ[primary_env_var] = api_key
            os.environ[secondary_env_var] = api_key
                    
        elif provider == "firecrawl":
            # Test Firecrawl key
            try:
                # Import here to avoid circular imports
                from firecrawl import FirecrawlApp
                firecrawl = FirecrawlApp(api_key=api_key)
                
                # Try a simple test scrape
                test_result = firecrawl.scrape_url(
                    "https://example.com",
                    params={'formats': ['markdown']}
                )
                
                if 'markdown' not in test_result:
                    raise HTTPException(
                        status_code=400, 
                        detail="Invalid Firecrawl API key"
                    )
                
                # Save API key - using primary format
                primary_env_var = 'PROVIDER_FIRECRAWL_KEY'
                secondary_env_var = 'FIRECRAWL_API_KEY'

                # Read existing content
                try:
                    with open(env_path, "r") as env_file:
                        lines = env_file.readlines()
                except FileNotFoundError:
                    lines = []

                # Update or add both keys
                primary_line = f'{primary_env_var}="{api_key}"\n'
                secondary_line = f'{secondary_env_var}="{api_key}"\n'
                
                primary_found = False
                secondary_found = False

                for i, line in enumerate(lines):
                    if line.startswith(f'{primary_env_var}='):
                        lines[i] = primary_line
                        primary_found = True
                    elif line.startswith(f'{secondary_env_var}='):
                        lines[i] = secondary_line
                        secondary_found = True

                if not primary_found:
                    lines.append(primary_line)
                if not secondary_found:
                    lines.append(secondary_line)

                # Write back to .env
                with open(env_path, "w") as env_file:
                    env_file.writelines(lines)

                # Update environment variables
                os.environ[primary_env_var] = api_key
                os.environ[secondary_env_var] = api_key
                
            except HTTPException:
                raise
            except Exception as e:
                error_msg = str(e)
                if "401" in error_msg:
                    error_msg = "Invalid Firecrawl API key"
                raise HTTPException(status_code=400, detail=f"Firecrawl error: {error_msg}")
                    
        elif provider == "thenewsapi":
            # Save TheNewsAPI key
            primary_env_var = 'PROVIDER_THENEWSAPI_KEY'
            secondary_env_var = 'THENEWSAPI_KEY'

            # Read existing content
            try:
                with open(env_path, "r") as env_file:
                    lines = env_file.readlines()
            except FileNotFoundError:
                lines = []

            # Update or add both keys
            primary_line = f'{primary_env_var}="{api_key}"\n'
            secondary_line = f'{secondary_env_var}="{api_key}"\n'
            
            primary_found = False
            secondary_found = False

            for i, line in enumerate(lines):
                if line.startswith(f'{primary_env_var}='):
                    lines[i] = primary_line
                    primary_found = True
                elif line.startswith(f'{secondary_env_var}='):
                    lines[i] = secondary_line
                    secondary_found = True

            if not primary_found:
                lines.append(primary_line)
            if not secondary_found:
                lines.append(secondary_line)

            # Write back to .env
            with open(env_path, "w") as env_file:
                env_file.writelines(lines)

            # Update environment
            os.environ[primary_env_var] = api_key
            os.environ[secondary_env_var] = api_key
                    
        elif provider == "openai":
            # Save OpenAI key to .env
            env_var_name = 'OPENAI_API_KEY'

            # Read existing content
            try:
                with open(env_path, "r") as env_file:
                    lines = env_file.readlines()
            except FileNotFoundError:
                lines = []

            # Update or add the key
            new_line = f'{env_var_name}="{api_key}"\n'
            key_found = False

            for i, line in enumerate(lines):
                if line.startswith(f'{env_var_name}='):
                    lines[i] = new_line
                    key_found = True
                    break

            if not key_found:
                lines.append(new_line)

            # Write back to .env
            with open(env_path, "w") as env_file:
                env_file.writelines(lines)

            # Update environment
            os.environ[env_var_name] = api_key
            
            # Also set model-specific keys for litellm
            model_keys = {
                'OPENAI_API_KEY_GPT_3.5_TURBO': api_key,
                'OPENAI_API_KEY_GPT_4O': api_key,
                'OPENAI_API_KEY_GPT_4O_MINI': api_key
            }
            
            # Add model-specific keys to .env file
            for key_name, key_value in model_keys.items():
                key_found = False
                for i, line in enumerate(lines):
                    if line.startswith(f'{key_name}='):
                        lines[i] = f'{key_name}=\'{key_value}\'\n'  # Use single quotes to match existing format
                        key_found = True
                        break
                
                if not key_found:
                    lines.append(f'{key_name}=\'{key_value}\'\n')
                
                # Also set in current environment
                os.environ[key_name] = key_value
                
            # Write all updates back to .env
            with open(env_path, "w") as env_file:
                env_file.writelines(lines)
            
        elif provider == "anthropic":
            # Save Anthropic key to .env
            env_var_name = 'ANTHROPIC_API_KEY'

            # Read existing content
            try:
                with open(env_path, "r") as env_file:
                    lines = env_file.readlines()
            except FileNotFoundError:
                lines = []

            # Update or add the key
            new_line = f'{env_var_name}="{api_key}"\n'
            key_found = False

            for i, line in enumerate(lines):
                if line.startswith(f'{env_var_name}='):
                    lines[i] = new_line
                    key_found = True
                    break

            if not key_found:
                lines.append(new_line)

            # Add model-specific keys
            model_keys = {
                'ANTHROPIC_API_KEY_CLAUDE_3_7_SONNET_LATEST': api_key,
                'ANTHROPIC_API_KEY_CLAUDE_3_5_SONNET_LATEST': api_key
            }
            
            # Update or add model-specific keys
            for key_name, key_value in model_keys.items():
                key_found = False
                for i, line in enumerate(lines):
                    if line.startswith(f'{key_name}='):
                        lines[i] = f'{key_name}=\'{key_value}\'\n'
                        key_found = True
                        break
                
                if not key_found:
                    lines.append(f'{key_name}=\'{key_value}\'\n')
                
                # Also set in current environment
                os.environ[key_name] = key_value
            
            # Write back to .env
            with open(env_path, "w") as env_file:
                env_file.writelines(lines)

            # Update environment
            os.environ[env_var_name] = api_key
            
        elif provider == "huggingface":
            # Save Hugging Face key
            env_var_name = 'HUGGINGFACE_API_KEY'

            # Read existing content
            try:
                with open(env_path, "r") as env_file:
                    lines = env_file.readlines()
            except FileNotFoundError:
                lines = []

            # Update or add the key
            new_line = f'{env_var_name}="{api_key}"\n'
            key_found = False

            for i, line in enumerate(lines):
                if line.startswith(f'{env_var_name}='):
                    lines[i] = new_line
                    key_found = True
                    break

            if not key_found:
                lines.append(new_line)
                
            # Add model-specific key
            model_key_name = 'HUGGINGFACE_API_KEY_MIXTRAL_8X7B'
            model_key_found = False
            
            for i, line in enumerate(lines):
                if line.startswith(f'{model_key_name}='):
                    lines[i] = f'{model_key_name}=\'{api_key}\'\n'
                    model_key_found = True
                    break
            
            if not model_key_found:
                lines.append(f'{model_key_name}=\'{api_key}\'\n')

            # Write back to .env
            with open(env_path, "w") as env_file:
                env_file.writelines(lines)

            # Update environment
            os.environ[env_var_name] = api_key
            os.environ[model_key_name] = api_key
            
        elif provider == "gemini":
            # Save Google API key
            env_var_name = 'GEMINI_API_KEY'

            # Read existing content
            try:
                with open(env_path, "r") as env_file:
                    lines = env_file.readlines()
            except FileNotFoundError:
                lines = []

            # Update or add the key
            new_line = f'{env_var_name}="{api_key}"\n'
            key_found = False

            for i, line in enumerate(lines):
                if line.startswith(f'{env_var_name}='):
                    lines[i] = new_line
                    key_found = True
                    break

            if not key_found:
                lines.append(new_line)
                
            # Add model-specific key
            model_key_name = 'GEMINI_API_KEY_GEMINI_PRO'
            model_key_found = False
            
            for i, line in enumerate(lines):
                if line.startswith(f'{model_key_name}='):
                    lines[i] = f'{model_key_name}=\'{api_key}\'\n'
                    model_key_found = True
                    break
            
            if not model_key_found:
                lines.append(f'{model_key_name}=\'{api_key}\'\n')

            # Write back to .env
            with open(env_path, "w") as env_file:
                env_file.writelines(lines)

            # Update environment
            os.environ[env_var_name] = api_key
            os.environ[model_key_name] = api_key
            
        else:
            raise HTTPException(status_code=400, detail="Unsupported provider")
        
        # Force reload environment variables to make sure other parts of the app can see them
        load_dotenv(dotenv_path=env_path, override=True)
            
        return JSONResponse(content={"status": "valid", "configured": True})
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error validating API key: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

async def check_api_keys():
    """Check which API keys are configured in .env and return masked versions"""
    # Make sure we're loading from the right .env file
    env_path = os.path.join(os.path.dirname(__file__), '..', '..', '.env')
    logger.info(f"Loading keys from .env: {env_path}")
    logger.info(f"File exists: {os.path.exists(env_path)}")
    load_dotenv(dotenv_path=env_path, override=True)
    
    def mask_key(key):
        """Return a masked version of the key if it exists"""
        if not key:
            return None
        if len(key) <= 8:
            return key
        return f"{key[:4]}...{key[-4:]}"
    
    # Check for all required api keys
    newsapi_key = os.getenv("PROVIDER_NEWSAPI_KEY") or os.getenv("NEWSAPI_KEY")
    firecrawl_key = os.getenv("PROVIDER_FIRECRAWL_KEY") or os.getenv("FIRECRAWL_API_KEY")
    thenewsapi_key = os.getenv("PROVIDER_THENEWSAPI_KEY") or os.getenv("THENEWSAPI_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    huggingface_key = os.getenv("HUGGINGFACE_API_KEY")
    gemini_key = os.getenv("GEMINI_API_KEY")
    
    # Ensure both primary and secondary keys are set
    if newsapi_key:
        os.environ["PROVIDER_NEWSAPI_KEY"] = newsapi_key
        os.environ["NEWSAPI_KEY"] = newsapi_key
        
    if firecrawl_key:
        os.environ["PROVIDER_FIRECRAWL_KEY"] = firecrawl_key
        os.environ["FIRECRAWL_API_KEY"] = firecrawl_key
    
    if thenewsapi_key:
        os.environ["PROVIDER_THENEWSAPI_KEY"] = thenewsapi_key
        os.environ["THENEWSAPI_KEY"] = thenewsapi_key
    
    # Log which keys are found
    logger.info(f"NewsAPI Key: {bool(newsapi_key)}")
    logger.info(f"Firecrawl Key: {bool(firecrawl_key)}")
    logger.info(f"TheNewsAPI Key: {bool(thenewsapi_key)}")
    logger.info(f"OpenAI Key: {bool(openai_key)}")
    logger.info(f"Anthropic Key: {bool(anthropic_key)}")
    logger.info(f"HuggingFace Key: {bool(huggingface_key)}")
    logger.info(f"Gemini Key: {bool(gemini_key)}")
    
    # Log all available env vars for debugging
    for key, value in os.environ.items():
        if "API_KEY" in key or "KEY" in key and not "SECRET" in key:
            logger.info(f"Found env var: {key}={mask_key(value)}")
    
    return {
        "newsapi": bool(newsapi_key),
        "newsapi_key": mask_key(newsapi_key),
        "firecrawl": bool(firecrawl_key),
        "firecrawl_key": mask_key(firecrawl_key),
        "thenewsapi": bool(thenewsapi_key),
        "thenewsapi_key": mask_key(thenewsapi_key),
        "openai": bool(openai_key),
        "openai_key": mask_key(openai_key),
        "anthropic": bool(anthropic_key),
        "anthropic_key": mask_key(anthropic_key),
        "huggingface": bool(huggingface_key),
        "huggingface_key": mask_key(huggingface_key),
        "gemini": bool(gemini_key),
        "gemini_key": mask_key(gemini_key)
    }

@router.get("/api/onboarding/check-keys")
async def get_api_key_status():
    """Get status of configured API keys"""
    try:
        key_status = await check_api_keys()
        return JSONResponse(content=key_status)
    except Exception as e:
        logger.error(f"Error checking API keys: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/onboarding", response_class=HTMLResponse)
async def onboarding_page(
    request: Request,
    session=Depends(verify_session),
    redo: bool = Query(False)
):
    """Show the onboarding wizard page."""
    from app.main import templates  # Import here to avoid circular import
    
    # Check if user has completed onboarding
    db = Database()
    user = request.session.get("user")
    if not user:
        return RedirectResponse(url="/login")
        
    user_data = db.get_user(user)
    
    # Allow access if redo=true or if onboarding not completed
    if user_data.get("completed_onboarding") and not redo:
        return RedirectResponse(url="/")

    # Load example values from config.json
    with open('app/config/config.json', 'r') as f:
        config = json.load(f)
    
    # Extract unique values from all topics
    example_categories = list(set(
        cat for topic in config['topics'] 
        for cat in topic.get('categories', [])
    ))
    example_signals = list(set(
        signal for topic in config['topics'] 
        for signal in topic.get('future_signals', [])
    ))
    example_sentiments = list(set(
        sent for topic in config['topics'] 
        for sent in topic.get('sentiment', [])
    ))
    example_time_to_impact = list(set(
        time for topic in config['topics'] 
        for time in topic.get('time_to_impact', [])
    ))
    example_driver_types = list(set(
        driver for topic in config['topics'] 
        for driver in topic.get('driver_types', [])
    ))
        
    return templates.TemplateResponse(
        "onboarding/wizard.html",
        {
            "request": request,
            "example_categories": example_categories,
            "example_signals": example_signals,
            "example_sentiments": example_sentiments,
            "example_time_to_impact": example_time_to_impact,
            "example_driver_types": example_driver_types
        }
    )

@router.post("/api/onboarding/suggest-topic-attributes")
async def suggest_topic_attributes(
    topic_data: Dict = Body(...),
    db: Database = Depends(get_database_instance)
):
    """Use LLM to suggest topic attributes based on examples."""
    try:
        topic_name = topic_data.get("topic_name")
        if not topic_name:
            raise HTTPException(
                status_code=400,
                detail="topic_name is required"
            )
            
        # Get optional description
        description = topic_data.get("topic_description", "")

        # Load example topics
        with open('app/config/config.json', 'r') as f:
            config = json.load(f)
            
        # Format examples for the LLM
        examples = json.dumps(config["topics"], indent=2)
        
        # Prepare prompt with detailed topic characteristics
        prompt = f"""Given these example topics and their attributes:

{examples}

A topic in our system can represent various types of information collections:

1. Markets (e.g., Cloud Service Providers, EV Battery Suppliers)
2. Scientific/Knowledge Fields (e.g., Neurology, AI, Archeology)
3. Groups/Organizations (e.g., AI researchers, competitors, sports teams)
4. Scenarios/Questions (e.g., "Is AI hype?", "How strong is Cloud Repatriation?")

I want to create a topic called "{topic_name}".
{f"Additional description: {description}" if description else ""}

Each topic has specific characteristics:

1. Topic Name: A clear description that could be a question, market, field, or group

2. Categories: Components that help analyze and understand the topic deeply
   Example: For "AI Hype" - AI in Finance, AI in Science, AI Research Breakthroughs

3. Future Signals: CRITICAL - These are alternative possible futures or outcomes, NOT just developments
   IMPORTANT: Signals should be short, clear statements about what MIGHT happen
   
   Examples of GOOD future signals for "AI Hype":
   - "AI is just hype"
   - "AI is a bubble"
   - "AI is accelerating"
   - "AI has plateaued"
   - "AI will evolve gradually"
   
   Examples of GOOD future signals for "Cloud Repatriation":
   - "Widespread cloud exit"
   - "Selective workload repatriation"
   - "Hybrid equilibrium emerges"
   - "Cloud dominance continues"
   
   Examples of BAD future signals (too vague, not alternative futures):
   - "Advancement in AI technology"
   - "Significant growth in adoption"
   - "Breakthrough in methods"

4. Sentiments: Attitude towards the topic
   - Basic: Positive, Neutral, Negative
   - Advanced: Critical, Skeptical, Mocking, Hyperbolic

5. Time to Impact:
   - Immediate (0-6 months)
   - Short-term (6-18 months)
   - Mid-term (18-60 months)
   - Long-term (60+ months)

6. Driver Types: Effect on topic
   - Accelerator: Speeds up progress
   - Inhibitor: Slows progress
   - Blocker: Prevents progress
   - Initiator: Starts new developments
   - Catalyst: Triggers rapid change
   - Terminator: Ends developments
   - Validator: Confirms developments

Please suggest appropriate attributes for this topic.
First provide a brief (2-3 sentences), technical explanation of why your suggestions are appropriate, and then provide:
1. 5-8 relevant categories - specific components of the topic
2. 4-5 future signals - these MUST be short, alternative possible futures (5-8 words each)
3. 3-4 relevant keywords for monitoring - specific searchable terms

Format your response as JSON with the following structure:
{{
    "explanation": "Your explanation here",
    "categories": ["category1", "category2", ...],
    "future_signals": ["signal1", "signal2", ...],
    "keywords": ["keyword1", "keyword2", "keyword3"]
}}"""

        # Get response from LLM
        try:
            messages = [{"role": "user", "content": prompt}]
            response = completion(
                model="gpt-4",
                messages=messages,
                max_tokens=1000
            )
            
            # Parse the response
            suggestions = json.loads(response.choices[0].message.content)
            
            # Validate and clean up the suggestions
            if not suggestions.get("explanation") or len(suggestions.get("explanation", "")) < 20:
                # Add a default explanation if missing or too short
                suggestions["explanation"] = f"These attributes were selected to comprehensively track '{topic_name}' with focused categories and plausible alternative futures."
            
            # Ensure future signals are properly formatted (concise, alternative futures)
            future_signals = suggestions.get("future_signals", [])
            cleaned_signals = []
            
            for i, signal in enumerate(future_signals):
                # Remove quotes if present
                if signal.startswith('"') and signal.endswith('"'):
                    signal = signal[1:-1]
                
                # Truncate overly long signals
                if len(signal) > 40:
                    signal = signal[:37] + "..."
                
                # Skip signals that aren't alternative futures (contain certain problematic words)
                problematic_terms = ["advancement", "breakthrough", "progress in", "development of", "adoption of"]
                if not any(term in signal.lower() for term in problematic_terms):
                    cleaned_signals.append(signal)
            
            # Ensure we have enough signals even after filtering
            if len(cleaned_signals) < 3:
                default_outcomes = [
                    f"{topic_name} becomes mainstream",
                    f"{topic_name} remains niche",
                    f"{topic_name} disrupts industry",
                    f"{topic_name} evolves gradually"
                ]
                cleaned_signals.extend(default_outcomes[:5-len(cleaned_signals)])
            
            # Limit to 5 signals maximum
            suggestions["future_signals"] = cleaned_signals[:5]
            
            # Ensure we have enough keywords
            if len(suggestions.get("keywords", [])) < 3:
                # Extract potential keywords from categories if needed
                categories = suggestions.get("categories", [])
                additional_keywords = [c.split()[-1] for c in categories[:3] if len(c.split()) > 1]
                suggestions["keywords"] = list(set(suggestions.get("keywords", []) + additional_keywords))[:4]
            
            logger.info(f"Generated suggestions for topic '{topic_name}'")
            return JSONResponse(content=suggestions)
            
        except Exception as e:
            logger.error(f"Error in LLM processing: {str(e)}")
            # Fallback response with reasonable defaults
            return JSONResponse(content={
                "explanation": f"These are baseline attributes for tracking the future trajectory of {topic_name}.",
                "categories": [f"{topic_name} Analysis", f"{topic_name} Development", f"{topic_name} Impacts", 
                               f"{topic_name} Applications", f"{topic_name} Challenges"],
                "future_signals": [f"{topic_name} becomes mainstream", f"{topic_name} remains niche", 
                                  f"{topic_name} disrupts industry", f"{topic_name} evolves gradually"],
                "keywords": [topic_name, topic_name.lower().split()[-1] if " " in topic_name else topic_name]
            })
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error suggesting topic attributes: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/onboarding/save-topic")
async def save_topic(
    topic_data: Dict = Body(...),
    db: Database = Depends(get_database_instance)
):
    """Save a new topic configuration."""
    try:
        logger.info(f"Saving topic: {topic_data.get('name', 'unknown')}")
        logger.info(f"Topic data: {json.dumps(topic_data, indent=2)}")
        
        # Ensure required fields exist
        if not topic_data.get("name"):
            logger.error("Topic name is required but was not provided")
            raise HTTPException(
                status_code=400,
                detail="Topic name is required"
            )
            
        # Get keywords if provided (optional)
        keywords = topic_data.get("keywords", [])

        # Get absolute path to config.json
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        config_path = os.path.join(base_dir, 'app', 'config', 'config.json')
        logger.info(f"Using absolute config path: {config_path}")
        logger.info(f"Config path exists: {os.path.exists(config_path)}")
        logger.info(f"Config path is file: {os.path.isfile(config_path)}")
        logger.info(f"Config path permissions: {oct(os.stat(config_path).st_mode)}")
        
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
                logger.info(f"Successfully loaded config with {len(config.get('topics', []))} topics")
        except Exception as e:
            logger.error(f"Error loading config: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to load config: {str(e)}"
            )

        # Get standard values from Trend Monitoring topic (most generic)
        standard_topic = next(
            (topic for topic in config['topics'] 
             if topic['name'] == "Trend Monitoring"),
            config['topics'][0]  # Fallback to first topic if not found
        )
        logger.info(f"Using standard topic: {standard_topic['name']}")

        # Format topic data to match config.json structure
        formatted_topic = {
            "name": topic_data["name"],
            "description": topic_data.get("description", ""),
            "categories": topic_data.get("categories", []),
            "future_signals": topic_data.get("future_signals", []),
            "sentiment": topic_data.get("sentiment", standard_topic["sentiment"]),
            "time_to_impact": topic_data.get("time_to_impact", standard_topic["time_to_impact"]),
            "driver_types": topic_data.get("driver_types", standard_topic["driver_types"]),
            "keywords": keywords
        }
        logger.info(f"Formatted topic: {json.dumps(formatted_topic, indent=2)}")

        # Check if topic exists in config
        existing_topic_index = next(
            (i for i, topic in enumerate(config['topics']) 
             if topic['name'] == formatted_topic['name']),
            None
        )
        logger.info(f"Topic exists in config: {existing_topic_index is not None}")

        # Check if topic exists in database
        try:
            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT 1 FROM articles WHERE topic = ? LIMIT 1",
                    (topic_data["name"],)
                )
                topic_exists = cursor.fetchone() is not None
                logger.info(f"Topic exists in database: {topic_exists}")
        except Exception as e:
            logger.warning(f"Error checking if topic exists in database: {str(e)}")
            topic_exists = False

        # If topic exists in either place, return warning
        if existing_topic_index is not None or topic_exists:
            if not topic_data.get("requires_confirmation", False) or not topic_data.get("confirmed", False):
                logger.info("Topic exists and requires confirmation")
                return JSONResponse(
                    content={
                        "status": "warning",
                        "message": "Topic already exists. Saving will overwrite existing data.",
                        "requires_confirmation": True
                    },
                    status_code=409
                )
            else:
                logger.info("Topic exists but user confirmed overwrite")

        # Update or create topic in config.json
        if existing_topic_index is not None:
            logger.info(f"Updating existing topic at index {existing_topic_index}")
            config['topics'][existing_topic_index] = formatted_topic
        else:
            logger.info("Adding new topic to config")
            config['topics'].append(formatted_topic)

        # Save updated config
        try:
            logger.info(f"Saving config to {config_path}")
            # First create a temp file and then rename to ensure atomic write
            temp_config_path = f"{config_path}.temp"
            with open(temp_config_path, 'w') as f:
                json.dump(config, f, indent=2)
            
            # Check if temp file was created successfully
            if not os.path.exists(temp_config_path):
                raise Exception(f"Failed to create temp file at {temp_config_path}")
                
            # Rename the temp file to the actual config file
            os.replace(temp_config_path, config_path)
            logger.info("Config saved successfully")
        except Exception as e:
            logger.error(f"Error saving config: {str(e)}")
            # Try direct write as fallback
            try:
                logger.info("Trying direct write as fallback")
                with open(config_path, 'w') as f:
                    json.dump(config, f, indent=2)
                logger.info("Config saved successfully with direct write")
            except Exception as direct_write_error:
                logger.error(f"Direct write also failed: {str(direct_write_error)}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to save config: {str(e)}"
                )

        # Handle keyword group
        try:
            logger.info("Setting up keyword group")
            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id FROM keyword_groups WHERE name = ? AND topic = ?",
                    (topic_data["name"], topic_data["name"])
                )
                group = cursor.fetchone()

                if group:
                    group_id = group[0]
                    logger.info(f"Found existing keyword group with ID {group_id}")
                    # Clear existing keywords
                    cursor.execute(
                        "DELETE FROM monitored_keywords WHERE group_id = ?",
                        (group_id,)
                    )
                    logger.info(f"Cleared existing keywords for group {group_id}")
                else:
                    # Create new group
                    logger.info("Creating new keyword group")
                    cursor.execute(
                        "INSERT INTO keyword_groups (name, topic) VALUES (?, ?)",
                        (topic_data["name"], topic_data["name"])
                    )
                    group_id = cursor.lastrowid
                    logger.info(f"Created new keyword group with ID {group_id}")

                # Add keywords
                logger.info(f"Adding {len(keywords)} keywords to group {group_id}")
                for keyword in keywords:
                    cursor.execute(
                        "INSERT INTO monitored_keywords (group_id, keyword) "
                        "VALUES (?, ?)",
                        (group_id, keyword)
                    )
                    logger.info(f"Added keyword: {keyword}")

                conn.commit()
                logger.info("Database changes committed")
        except Exception as e:
            logger.error(f"Error handling keyword group: {str(e)}")
            # Continue despite keyword group error - config.json update is the priority

        logger.info("Topic saved successfully")
        return JSONResponse(content={
            "status": "success",
            "message": "Topic saved successfully"
        })

    except Exception as e:
        logger.error(f"Error saving topic: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save topic: {str(e)}"
        )

@router.post("/api/onboarding/complete")
async def complete_onboarding(
    request: Request,
    db: Database = Depends(get_database_instance)
):
    """Mark onboarding as complete for the user."""
    try:
        user = request.session.get("user")
        if not user:
            raise HTTPException(status_code=401, detail="Not authenticated")
            
        # Update user record
        db.update_user_onboarding(user, True)
        
        return JSONResponse(content={"status": "success"})
        
    except Exception as e:
        logger.error(f"Error completing onboarding: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/onboarding/reset")
async def reset_onboarding(
    request: Request,
    db: Database = Depends(get_database_instance)
):
    """Reset onboarding status for the user."""
    try:
        user = request.session.get("user")
        if not user:
            raise HTTPException(status_code=401, detail="Not authenticated")
            
        # Update user record to mark onboarding as not completed
        db.update_user_onboarding(user, False)
        
        return JSONResponse(content={"status": "success"})
        
    except Exception as e:
        logger.error(f"Error resetting onboarding: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e)) 