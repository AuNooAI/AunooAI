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
            
            # Save to both traditional env var and the PROVIDER_ prefix version
            env_var_names = ['NEWSAPI_KEY', 'PROVIDER_NEWSAPI_KEY']
            for env_var_name in env_var_names:
                logger.info(f"Setting {env_var_name} in {env_path}")
                
                try:
                    # Read existing content
                    try:
                        with open(env_path, "r") as env_file:
                            lines = env_file.readlines()
                    except FileNotFoundError:
                        lines = []
                    
                    # Update or add the key
                    new_line = f'{env_var_name}=\'{api_key}\'\n'
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
                        
                    logger.info(f"Successfully wrote {env_var_name} to {env_path}")
                except Exception as e:
                    logger.error(f"Error writing to .env: {str(e)}")
                    raise HTTPException(status_code=500, detail=f"Failed to save API key: {str(e)}")
                    
                # Update environment variable in memory
                os.environ[env_var_name] = api_key
                
                # Double-check that the key was set correctly
                if not os.getenv(env_var_name):
                    logger.error(f"Failed to set {env_var_name} in environment variables")
                    raise HTTPException(status_code=500, detail=f"Failed to set {env_var_name} in environment")
                    
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
                
                # Save to all expected environment variable names
                env_var_names = ['FIRECRAWL_KEY', 'FIRECRAWL_API_KEY', 'BRIGHTDATA_KEY', 'PROVIDER_FIRECRAWL_KEY']
                
                for env_var_name in env_var_names:
                    logger.info(f"Setting {env_var_name} in {env_path}")
                    
                    try:
                        # Read existing content
                        try:
                            with open(env_path, "r") as env_file:
                                lines = env_file.readlines()
                        except FileNotFoundError:
                            lines = []
                        
                        # Update or add the key
                        new_line = f'{env_var_name}=\'{api_key}\'\n'
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
                            
                        logger.info(f"Successfully wrote {env_var_name} to {env_path}")
                    except Exception as e:
                        logger.error(f"Error writing to .env: {str(e)}")
                        continue  # Try the next env var name
                    
                    # Update environment variable in memory
                    os.environ[env_var_name] = api_key
                
            except HTTPException:
                raise
            except Exception as e:
                error_msg = str(e)
                if "401" in error_msg:
                    error_msg = "Invalid Firecrawl API key"
                raise HTTPException(status_code=400, detail=f"Firecrawl error: {error_msg}")
                    
        elif provider == "openai":
            # Save OpenAI key to .env with all required model-specific names
            base_env_var_name = 'OPENAI_API_KEY'
            model_env_var_names = [
                base_env_var_name,  # Base env var
                'OPENAI_API_KEY_GPT_3.5_TURBO',
                'OPENAI_API_KEY_GPT_4O',
                'OPENAI_API_KEY_GPT_4O_MINI'  # 01-mini as requested by user
            ]
            
            for env_var_name in model_env_var_names:
                logger.info(f"Setting {env_var_name} in {env_path}")
                
                try:
                    # Read existing content
                    try:
                        with open(env_path, "r") as env_file:
                            lines = env_file.readlines()
                    except FileNotFoundError:
                        lines = []
                    
                    # Update or add the key
                    new_line = f'{env_var_name}=\'{api_key}\'\n'
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
                        
                    logger.info(f"Successfully wrote {env_var_name} to {env_path}")
                except Exception as e:
                    logger.error(f"Error writing to .env: {str(e)}")
                    continue  # Try the next env var name
                
                # Update environment variable in memory
                os.environ[env_var_name] = api_key
            
        elif provider == "anthropic":
            # Save Anthropic key to .env with Claude 3.7 Sonnet as requested by user
            base_env_var_name = 'ANTHROPIC_API_KEY'
            model_env_var_names = [
                base_env_var_name,  # Base env var
                'ANTHROPIC_API_KEY_CLAUDE_3_7_SONNET_LATEST',  # As requested by user
                'ANTHROPIC_API_KEY_CLAUDE_3_5_SONNET_LATEST'
            ]
            
            for env_var_name in model_env_var_names:
                logger.info(f"Setting {env_var_name} in {env_path}")
                
                try:
                    # Read existing content
                    try:
                        with open(env_path, "r") as env_file:
                            lines = env_file.readlines()
                    except FileNotFoundError:
                        lines = []
                    
                    # Update or add the key
                    new_line = f'{env_var_name}=\'{api_key}\'\n'
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
                        
                    logger.info(f"Successfully wrote {env_var_name} to {env_path}")
                except Exception as e:
                    logger.error(f"Error writing to .env: {str(e)}")
                    continue  # Try the next env var name
                
                # Update environment variable in memory
                os.environ[env_var_name] = api_key
            
        elif provider == "huggingface":
            # Save Hugging Face key with model-specific names
            env_var_names = ['HUGGINGFACE_API_KEY', 'HUGGINGFACE_API_KEY_MIXTRAL_8X7B']
            
            for env_var_name in env_var_names:
                logger.info(f"Setting {env_var_name} in {env_path}")
                
                try:
                    # Read existing content
                    try:
                        with open(env_path, "r") as env_file:
                            lines = env_file.readlines()
                    except FileNotFoundError:
                        lines = []
                    
                    # Update or add the key
                    new_line = f'{env_var_name}=\'{api_key}\'\n'
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
                        
                    logger.info(f"Successfully wrote {env_var_name} to {env_path}")
                except Exception as e:
                    logger.error(f"Error writing to .env: {str(e)}")
                    continue  # Try the next env var name
                
                # Update environment variable in memory
                os.environ[env_var_name] = api_key
            
        elif provider == "gemini":
            # Save Google API key
            env_var_names = ['GEMINI_API_KEY', 'GEMINI_API_KEY_GEMINI_PRO']
            
            for env_var_name in env_var_names:
                logger.info(f"Setting {env_var_name} in {env_path}")
                
                try:
                    # Read existing content
                    try:
                        with open(env_path, "r") as env_file:
                            lines = env_file.readlines()
                    except FileNotFoundError:
                        lines = []
                    
                    # Update or add the key
                    new_line = f'{env_var_name}=\'{api_key}\'\n'
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
                        
                    logger.info(f"Successfully wrote {env_var_name} to {env_path}")
                except Exception as e:
                    logger.error(f"Error writing to .env: {str(e)}")
                    continue  # Try the next env var name
                
                # Update environment variable in memory
                os.environ[env_var_name] = api_key
            
        else:
            raise HTTPException(status_code=400, detail="Unsupported provider")
        
        # Force reload environment variables to make sure other parts of the app can see them
        load_dotenv(override=True)
            
        return JSONResponse(content={"status": "valid", "configured": True})
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error validating API key: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

async def check_api_keys():
    """Check which API keys are configured in .env and return masked versions"""
    load_dotenv()
    
    def mask_key(key):
        """Return a masked version of the key if it exists"""
        if not key:
            return None
        if len(key) <= 8:
            return key
        return f"{key[:4]}...{key[-4:]}"
    
    # Check for all required api keys
    newsapi_key = os.getenv("PROVIDER_NEWSAPI_KEY") or os.getenv("NEWSAPI_KEY")
    firecrawl_key = os.getenv("PROVIDER_FIRECRAWL_KEY") or os.getenv("FIRECRAWL_API_KEY") or os.getenv("BRIGHTDATA_KEY") or os.getenv("FIRECRAWL_KEY")
    openai_key = os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY_GPT_3.5_TURBO") or os.getenv("OPENAI_API_KEY_GPT_4O") or os.getenv("OPENAI_API_KEY_GPT_4O_MINI")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_API_KEY_CLAUDE_3_7_SONNET_LATEST") or os.getenv("ANTHROPIC_API_KEY_CLAUDE_3_5_SONNET_LATEST")
    huggingface_key = os.getenv("HUGGINGFACE_API_KEY") or os.getenv("HUGGINGFACE_API_KEY_MIXTRAL_8X7B")
    gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY_GEMINI_PRO")
    
    # Log which keys are found
    logger.info(f"NewsAPI Key: {bool(newsapi_key)}")
    logger.info(f"Firecrawl Key: {bool(firecrawl_key)}")
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

Each topic has specific characteristics:

1. Topic Name: A clear description that could be a question, market, field, or group
2. Categories: Components that help analyze and understand the topic deeply
   Example: For "AI Hype" - AI in Finance, Research Breakthroughs, Industry Adoption

3. Future Signals: Indicators of topic direction
   - For markets: "Market Convergence", "Growth Stalling"
   - For questions: "AI is hype", "AI is evolving gradually"
   - For tracking: "New Hire", "New Feature"

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

Please suggest appropriate attributes for a new topic called "{topic_name}".
Focus on providing:
1. 5-10 relevant categories
2. 3-5 future signals
3. 2-3 relevant keywords for monitoring (focus on companies, technologies, people, or domain names)
4. A brief explanation of why these suggestions are relevant

Format your response as JSON with the following structure:
{{
    "categories": ["category1", "category2", ...],
    "future_signals": ["signal1", "signal2", ...],
    "keywords": ["keyword1", "keyword2", "keyword3"],
    "explanation": "Your explanation here"
}}"""

        # Get response from LLM
        messages = [{"role": "user", "content": prompt}]
        response = completion(
            model="gpt-4",
            messages=messages,
            max_tokens=1000
        )
        
        # Parse and return suggestions
        suggestions = json.loads(response.choices[0].message.content)
        return JSONResponse(content=suggestions)
        
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
        # Ensure required fields exist
        if not topic_data.get("name"):
            raise HTTPException(
                status_code=400,
                detail="Topic name is required"
            )

        # Load current config to get standard values
        config_path = 'app/config/config.json'
        with open(config_path, 'r') as f:
            config = json.load(f)

        # Get standard values from Trend Monitoring topic (most generic)
        standard_topic = next(
            (topic for topic in config['topics'] 
             if topic['name'] == "Trend Monitoring"),
            config['topics'][0]  # Fallback to first topic if not found
        )

        # Format topic data to match config.json structure
        formatted_topic = {
            "name": topic_data["name"],
            "categories": topic_data.get("categories", []),
            "future_signals": topic_data.get("future_signals", []),
            "sentiment": topic_data.get("sentiment", standard_topic["sentiment"]),
            "time_to_impact": topic_data.get("time_to_impact", standard_topic["time_to_impact"]),
            "driver_types": topic_data.get("driver_types", standard_topic["driver_types"])
        }

        # Check if topic exists in config
        existing_topic_index = next(
            (i for i, topic in enumerate(config['topics']) 
             if topic['name'] == formatted_topic['name']),
            None
        )

        # Check if topic exists in database
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM articles WHERE topic = ? LIMIT 1",
                (topic_data["name"],)
            )
            topic_exists = cursor.fetchone() is not None

        # If topic exists in either place, return warning
        if existing_topic_index is not None or topic_exists:
            if not topic_data.get("requires_confirmation", False) or not topic_data.get("confirmed", False):
                return JSONResponse(
                    content={
                        "status": "warning",
                        "message": "Topic already exists. Saving will overwrite existing data.",
                        "requires_confirmation": True
                    },
                    status_code=409
                )

        # Update or create topic in config.json
        if existing_topic_index is not None:
            config['topics'][existing_topic_index] = formatted_topic
        else:
            config['topics'].append(formatted_topic)

        # Save updated config
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)

        # Create or update topic in database
        if topic_exists:
            db.update_topic(topic_data["name"])
        else:
            db.create_topic(topic_data["name"])

        # Handle keyword group
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id FROM keyword_groups WHERE name = ? AND topic = ?",
                (topic_data["name"], topic_data["name"])
            )
            group = cursor.fetchone()

            if group:
                group_id = group[0]
                # Clear existing keywords
                cursor.execute(
                    "DELETE FROM monitored_keywords WHERE group_id = ?",
                    (group_id,)
                )
            else:
                # Create new group
                cursor.execute(
                    "INSERT INTO keyword_groups (name, topic) VALUES (?, ?)",
                    (topic_data["name"], topic_data["name"])
                )
                group_id = cursor.lastrowid

            # Add keywords
            keywords = topic_data.get("keywords", [])
            for keyword in keywords:
                cursor.execute(
                    "INSERT INTO monitored_keywords (group_id, keyword) "
                    "VALUES (?, ?)",
                    (group_id, keyword)
                )

            conn.commit()

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