from fastapi import APIRouter, Request, Depends, HTTPException, Body, Query
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from app.security.session import verify_session
from app.database import Database, get_database_instance
from app.database_query_facade import DatabaseQueryFacade
import os
import aiohttp
import logging
from typing import Dict
import json
import yaml
from dotenv import load_dotenv, set_key
from litellm import completion
from app.ai_models import ai_get_available_models  # Add this import at the top

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

        logger.info(f"Validating API key for provider: {provider}, model: {model}")
            
        # Use the same path resolution as main.py
        env_path = os.path.join(os.path.dirname(__file__), '..', '..', '.env')
        
        # Handle the model-specific case
        if model:
            # Determine which provider this model belongs to
            if provider == "openai":
                # Define environment variable name for this model
                model_env_var = f"OPENAI_API_KEY_{model.replace('-', '_').replace('.', '_').upper()}"
                logger.info(f"Setting model-specific key: {model_env_var}")
                
                # Read existing content
                try:
                    with open(env_path, "r") as env_file:
                        lines = env_file.readlines()
                except FileNotFoundError:
                    lines = []
                
                # Also set the general provider key
                provider_env_var = "OPENAI_API_KEY"
                
                # Update or add the keys
                model_key_line = f'{model_env_var}="{api_key}"\n'
                provider_key_line = f'{provider_env_var}="{api_key}"\n'
                
                model_key_found = False
                provider_key_found = False
                
                for i, line in enumerate(lines):
                    if line.startswith(f'{model_env_var}='):
                        lines[i] = model_key_line
                        model_key_found = True
                    elif line.startswith(f'{provider_env_var}='):
                        lines[i] = provider_key_line
                        provider_key_found = True
                
                if not model_key_found:
                    lines.append(model_key_line)
                if not provider_key_found:
                    lines.append(provider_key_line)
                
                # Write back to .env
                with open(env_path, "w") as env_file:
                    env_file.writelines(lines)
                
                # Update environment
                os.environ[model_env_var] = api_key
                os.environ[provider_env_var] = api_key
                
                logger.info(f"Successfully configured API key for model: {model}")
                
            elif provider == "anthropic":
                # Similar approach for Anthropic models
                model_env_var = f"ANTHROPIC_API_KEY_{model.replace('-', '_').replace('.', '_').upper()}"
                logger.info(f"Setting model-specific key: {model_env_var}")
                
                # Read existing content
                try:
                    with open(env_path, "r") as env_file:
                        lines = env_file.readlines()
                except FileNotFoundError:
                    lines = []
                
                # Also set the general provider key
                provider_env_var = "ANTHROPIC_API_KEY"
                
                # Update or add the keys
                model_key_line = f'{model_env_var}="{api_key}"\n'
                provider_key_line = f'{provider_env_var}="{api_key}"\n'
                
                model_key_found = False
                provider_key_found = False
                
                for i, line in enumerate(lines):
                    if line.startswith(f'{model_env_var}='):
                        lines[i] = model_key_line
                        model_key_found = True
                    elif line.startswith(f'{provider_env_var}='):
                        lines[i] = provider_key_line
                        provider_key_found = True
                
                if not model_key_found:
                    lines.append(model_key_line)
                if not provider_key_found:
                    lines.append(provider_key_line)
                
                # Write back to .env
                with open(env_path, "w") as env_file:
                    env_file.writelines(lines)
                
                # Update environment
                os.environ[model_env_var] = api_key
                os.environ[provider_env_var] = api_key
                
                logger.info(f"Successfully configured API key for model: {model}")
            
            # Continue with existing validation code for other providers
            
        elif provider == "newsapi":
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
                
                # Validation: if the call returns without raising an exception,
                # we consider the key valid – no need to inspect the payload.
                firecrawl.scrape_url("https://example.com", formats=["markdown"])
                
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
                    lines[i] = f'{model_key_name}="{api_key}"\n'
                    model_key_found = True
                    break
            
            if not model_key_found:
                lines.append(f'{model_key_name}="{api_key}"\n')

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
                    lines[i] = f'{model_key_name}="{api_key}"\n'
                    model_key_found = True
                    break
            
            if not model_key_found:
                lines.append(f'{model_key_name}="{api_key}"\n')

            # Write back to .env
            with open(env_path, "w") as env_file:
                env_file.writelines(lines)

            # Update environment
            os.environ[env_var_name] = api_key
            os.environ[model_key_name] = api_key
            
        else:
            raise HTTPException(status_code=400, detail="Unsupported provider")
        
        # After saving the key, force reload environment variables
        load_dotenv(dotenv_path=env_path, override=True)
        
        # Return the masked key in the response
        masked_key = f"{api_key[:4]}...{api_key[-4:]}" if len(api_key) > 8 else "[SET]"
        return JSONResponse(content={
            "status": "valid", 
            "configured": True,
            "masked_key": masked_key
        })
        
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
    
    # Get all configured models and their keys
    configured_models = []
    
    # Get all environment variables
    for key, value in os.environ.items():
        # Check for OpenAI model-specific keys
        if key.startswith("OPENAI_API_KEY_") and key != "OPENAI_API_KEY":
            model_name = key.replace("OPENAI_API_KEY_", "").lower().replace("_", "-")
            configured_models.append({
                "name": model_name,
                "provider": "openai",
                "key": mask_key(value)
            })
        
        # Check for Anthropic model-specific keys
        elif key.startswith("ANTHROPIC_API_KEY_") and key != "ANTHROPIC_API_KEY":
            model_name = key.replace("ANTHROPIC_API_KEY_", "").lower().replace("_", "-")
            configured_models.append({
                "name": model_name,
                "provider": "anthropic",
                "key": mask_key(value)
            })
    
    # Log what we found
    logger.info(f"Found {len(configured_models)} configured AI models")
    for model in configured_models:
        logger.info(f"  - {model['name']} ({model['provider']})")
    
    # Return the data
    result = {
        "newsapi": bool(newsapi_key),
        "newsapi_key": mask_key(newsapi_key),
        "firecrawl": bool(firecrawl_key),
        "firecrawl_key": mask_key(firecrawl_key),
        "configured_models": configured_models
    }
    
    return result

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
    
    # Handle case where user_data is None (database schema issue)
    if user_data is None:
        # Redirect to login to recreate the user
        return RedirectResponse(url="/login?error=db_schema_updated")
    
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

def ensure_structured_keywords(raw_keywords, topic_name):
    # If already structured, ensure all keys exist
    if isinstance(raw_keywords, dict):
        for k in ["companies", "technologies", "general", "people", "exclusions"]:
            if k not in raw_keywords or not isinstance(raw_keywords[k], list):
                raw_keywords[k] = []
        return raw_keywords
    # If flat list, map to general
    elif isinstance(raw_keywords, list):
        return {
            "companies": [],
            "technologies": [],
            "general": raw_keywords,
            "people": [],
            "exclusions": []
        }
    # Otherwise, return all empty
    return {
        "companies": [],
        "technologies": [],
        "general": [],
        "people": [],
        "exclusions": []
    }

def extract_json_from_text(text):
    """Extract valid JSON from text, even if embedded in markdown or explanations."""
    import re
    
    # Log the input for debugging
    logger.info(f"Attempting to extract JSON from text: {text[:200]}...")
    
    # First try direct loading (maybe it's already valid JSON)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    
    # Clean up the text - remove markdown code blocks
    text = re.sub(r'```json\s*|\s*```', '', text)
    
    # Try to find a JSON object with curly braces
    json_pattern = r'({[\s\S]*?})'
    matches = re.findall(json_pattern, text)
    
    for potential_json in matches:
        try:
            parsed = json.loads(potential_json)
            logger.info(f"Successfully extracted JSON: {json.dumps(parsed)[:200]}...")
            return parsed
        except json.JSONDecodeError:
            continue
    
    # If no valid JSON found, try more aggressive extraction
    # Look for the deepest level of nested braces
    text = text.replace('\n', ' ')
    start_idx = text.find('{')
    if start_idx != -1:
        # Find matching closing brace
        brace_count = 1
        for i in range(start_idx + 1, len(text)):
            if text[i] == '{':
                brace_count += 1
            elif text[i] == '}':
                brace_count -= 1
                if brace_count == 0:
                    try:
                        potential_json = text[start_idx:i+1]
                        parsed = json.loads(potential_json)
                        logger.info(f"Last-resort JSON extraction worked: {json.dumps(parsed)[:200]}...")
                        return parsed
                    except json.JSONDecodeError:
                        break
    
    logger.error("Could not extract any valid JSON")
    return None

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
        keyword_prompt = topic_data.get("keyword_prompt", None)

        # Load example topics
        with open('app/config/config.json', 'r') as f:
            config = json.load(f)
        
        # Format examples for the LLM
        examples = json.dumps(config["topics"], indent=2)
        
        # Set system prompt to force JSON response
        system_prompt = "You are a JSON-only assistant. You must respond with a valid JSON object only, no explanations, no markdown formatting, no additional text. Every response must be properly formatted JSON that can be directly parsed."
        
        # Prepare prompt with detailed topic characteristics
        if keyword_prompt:
            prompt = f"""Respond with VALID JSON ONLY. NO explanations, NO markdown.

{keyword_prompt}

Format your JSON response with these keys exactly:
{{
    "explanation": "Brief explanation",
    "keywords": {{
        "companies": ["real company1", "real company2", ...],
        "technologies": ["real technology1", "real technology2", ...],
        "general": ["keyword1", "keyword2", ...],
        "people": ["real person1", "real person2", ...],
        "exclusions": ["exclusion1", "exclusion2", ...]
    }}
}}"""
        else:
            prompt = f"""Given these example topics and their attributes:

{examples}

A topic in our system can represent various types of information collections:

1. Markets (e.g., Cloud Service Providers, EV Battery Suppliers)
2. Scientific/Knowledge Fields (e.g., Neurology, AI, Archeology)
3. Groups/Organizations (e.g., AI researchers, competitors, sports teams)
4. Scenarios/Questions (e.g., \"Is AI hype?\", \"How strong is Cloud Repatriation?\")

I want to create a topic called \"{topic_name}\".
{f"Additional description: {description}" if description else ""}

Each topic has specific characteristics:

1. Topic Name: A clear description that could be a question, market, field, or group

2. Categories: Components that help analyze and understand the topic deeply
   Example: For \"AI Hype\" - AI in Finance, AI in Science, AI Research Breakthroughs

3. Future Signals: CRITICAL - These are alternative possible futures or outcomes, NOT just developments
   IMPORTANT: Signals should be short, clear statements about what MIGHT happen
   
   Examples of GOOD future signals for \"AI Hype\":
   - \"AI is just hype\"
   - \"AI is a bubble\"
   - \"AI is accelerating\"
   - \"AI has plateaued\"
   - \"AI will evolve gradually\"
   
   Examples of GOOD future signals for \"Cloud Repatriation\":
   - \"Widespread cloud exit\"
   - \"Selective workload repatriation\"
   - \"Hybrid equilibrium emerges\"
   - \"Cloud dominance continues\"
   
   Examples of BAD future signals (too vague, not alternative futures):
   - \"Advancement in AI technology\"
   - \"Significant growth in adoption\"
   - \"Breakthrough in methods\"

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

For the keywords section, return a JSON object with these keys: companies, technologies, general, people, exclusions. For companies, technologies, and people, ONLY include real, verifiable entities that are relevant to the topic. If you cannot verify a real company, technology, or person, leave the list empty. Do NOT invent names. For exclusions, include only common spam, scam, or misinformation terms relevant to the topic, or leave blank if none are known.

IMPORTANT: You must respond with VALID JSON only. No explanations, no markdown formatting, no additional text.

Format your response EXACTLY as follows:
{{
    "explanation": "Your explanation here",
    "categories": ["category1", "category2", ...],
    "future_signals": ["signal1", "signal2", ...],
    "keywords": {{
        "companies": ["company1", ...],
        "technologies": ["tech1", ...],
        "general": ["general1", ...],
        "people": ["person1", ...],
        "exclusions": ["exclusion1", ...]
    }}
}}"""

        # Get response from LLM
        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ]
            
            logger.info(f"Sending prompt to LLM: {prompt[:200]}...")
            
            response = completion(
                model="gpt-4-1106-preview",
                messages=messages,
                max_tokens=1500,
                temperature=0.2  # Lower temperature for more consistent JSON formatting
            )
            
            # Parse the response - try to extract JSON even from non-JSON responses
            raw_content = response.choices[0].message.content
            logger.info(f"Raw LLM response: {raw_content}")  # Log the full response for debugging
            
            # Try to parse as JSON directly first
            try:
                suggestions = json.loads(raw_content)
                logger.info("Direct JSON parsing successful")
            except json.JSONDecodeError as e:
                # If direct parsing fails, try to extract JSON from text
                logger.warning(f"JSON parsing failed: {str(e)}, attempting to extract JSON from text")
                suggestions = extract_json_from_text(raw_content)
                
                # If extraction also fails, use fallback
                if not suggestions:
                    logger.error("Could not extract valid JSON from LLM response")
                    raise ValueError("Failed to parse LLM response as JSON")
            
            # Verify keywords structure is present to avoid fallback
            if not suggestions.get("keywords"):
                logger.error("LLM response didn't include keywords structure")
                suggestions["keywords"] = {}
            
            # Continue with the rest of the processing
            if not suggestions.get("explanation") or len(suggestions.get("explanation", "")) < 20:
                suggestions["explanation"] = f"These attributes were selected to comprehensively track '{topic_name}' with focused categories and plausible alternative futures."
            # Ensure future signals are properly formatted (concise, alternative futures)
            future_signals = suggestions.get("future_signals", [])
            cleaned_signals = []
            for i, signal in enumerate(future_signals):
                if signal.startswith('"') and signal.endswith('"'):
                    signal = signal[1:-1]
                if len(signal) > 40:
                    signal = signal[:37] + "..."
                problematic_terms = ["advancement", "breakthrough", "progress in", "development of", "adoption of"]
                if not any(term in signal.lower() for term in problematic_terms):
                    cleaned_signals.append(signal)
            if len(cleaned_signals) < 3:
                default_outcomes = [
                    f"{topic_name} becomes mainstream",
                    f"{topic_name} remains niche",
                    f"{topic_name} disrupts industry",
                    f"{topic_name} evolves gradually"
                ]
                cleaned_signals.extend(default_outcomes[:5-len(cleaned_signals)])
            suggestions["future_signals"] = cleaned_signals[:5]
            # --- KEYWORD STRUCTURE FIX ---
            suggestions["keywords"] = ensure_structured_keywords(suggestions.get("keywords", {}), topic_name)
            
            # Only use fallback if we have empty keyword lists
            has_any_keywords = any(
                len(suggestions["keywords"].get(cat, [])) > 0 
                for cat in ["companies", "technologies", "general", "people", "exclusions"]
            )
            
            if not has_any_keywords:
                logger.warning("No keywords found in LLM response, using fallback")
                # Use fallback only for keywords
                suggestions["keywords"] = {
                    "companies": [f"{topic_name} Corp", f"{topic_name} Inc"],
                    "technologies": [f"{topic_name} Tech", f"{topic_name} Platform"],
                    "general": [topic_name, topic_name.lower().split()[-1] if " " in topic_name else topic_name],
                    "people": [f"{topic_name} Expert"],
                    "exclusions": ["-scam", "-unrelated"]
                }
            
            logger.info(f"Generated suggestions for topic '{topic_name}'")
            return JSONResponse(content=suggestions)
        except Exception as e:
            logger.error(f"Error in LLM processing: {str(e)}")
            # Fallback response with plausible values for each category
            fallback_keywords = {
                "companies": [f"{topic_name} Corp", f"{topic_name} Inc"],
                "technologies": [f"{topic_name} Tech", f"{topic_name} Platform"],
                "general": [topic_name, topic_name.lower().split()[-1] if " " in topic_name else topic_name],
                "people": [f"{topic_name} Expert"],
                "exclusions": ["-scam", "-unrelated"]
            }
            return JSONResponse(content={
                "explanation": f"These are baseline attributes for tracking the future trajectory of {topic_name}.",
                "categories": [f"{topic_name} Analysis", f"{topic_name} Development", f"{topic_name} Impacts", f"{topic_name} Applications", f"{topic_name} Challenges"],
                "future_signals": [f"{topic_name} becomes mainstream", f"{topic_name} remains niche", f"{topic_name} disrupts industry", f"{topic_name} evolves gradually"],
                "keywords": fallback_keywords
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
            topic_exists = (DatabaseQueryFacade(db, logger)).topic_exists(topic)
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

            group = (DatabaseQueryFacade(db, logger)).get_keyword_group_id_by_name_and_topic(topic_data["name"], topic_data["name"])

            if group:
                group_id = group[0]
                logger.info(f"Found existing keyword group with ID {group_id}")
                # Clear existing keywords
                (DatabaseQueryFacade(db, logger)).delete_group_keywords(group_id)
                logger.info(f"Cleared existing keywords for group {group_id}")
            else:
                # Create new group
                logger.info("Creating new keyword group")
                group_id = (DatabaseQueryFacade(db, logger)).create_group(topic_data["name"], topic_data["name"])
                logger.info(f"Created new keyword group with ID {group_id}")

            # Add keywords
            logger.info(f"Adding {len(keywords)} keywords to group {group_id}")
            for keyword in keywords:
                (DatabaseQueryFacade(db, logger)).add_keywords_to_group(group_id, keyword)
                logger.info(f"Added keyword: {keyword}")

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

@router.get("/api/onboarding/available-models")
async def get_available_models():
    """Get list of all available AI models from litellm_config.yaml (regardless of API key configuration)."""
    try:
        # Read the litellm config file
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'litellm_config.yaml')
        
        if not os.path.exists(config_path):
            logger.error(f"LiteLLM config file not found at: {config_path}")
            return JSONResponse(content={"models": []})
        
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        available_models = []
        
        # Get all models from the config (regardless of API key configuration)
        for model_config in config.get('model_list', []):
            model_name = model_config.get('model_name')
            litellm_params = model_config.get('litellm_params', {})
            
            if model_name:
                # Extract provider from the litellm model path
                litellm_model = litellm_params.get('model', '')
                provider = litellm_model.split('/')[0] if '/' in litellm_model else 'unknown'
                
                available_models.append({
                    "name": model_name,
                    "provider": provider,
                    "display_name": f"{model_name} ({provider})",
                    "id": model_name
                })
        
        logger.info(f"Retrieved {len(available_models)} available models from litellm_config.yaml")
        
        # Return flat list of models
        return JSONResponse(content={"models": available_models})
    except Exception as e:
        logger.error(f"Error getting available models from litellm config: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/onboarding/configured-models")
async def get_configured_models():
    """Get list of AI models that have API keys configured from litellm_config.yaml."""
    try:
        # Read the litellm config file
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'litellm_config.yaml')
        
        if not os.path.exists(config_path):
            logger.error(f"LiteLLM config file not found at: {config_path}")
            return JSONResponse(content={"models": []})
        
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        configured_models = []
        
        # Check each model in the config to see if it has a valid API key
        for model_config in config.get('model_list', []):
            model_name = model_config.get('model_name')
            litellm_params = model_config.get('litellm_params', {})
            api_key_ref = litellm_params.get('api_key', '')
            
            # Extract environment variable name from the api_key reference
            if api_key_ref.startswith('os.environ/'):
                env_var_name = api_key_ref.replace('os.environ/', '')
                api_key_value = os.getenv(env_var_name)
                
                # Only include models that have actual API keys configured
                if api_key_value and api_key_value.strip():
                    # Extract provider from the litellm model path
                    litellm_model = litellm_params.get('model', '')
                    provider = litellm_model.split('/')[0] if '/' in litellm_model else 'unknown'
                    
                    configured_models.append({
                        "name": model_name,
                        "provider": provider,
                        "display_name": f"{model_name} ({provider})",
                        "id": model_name
                    })
                    logger.debug(f"✅ Found configured model: {model_name} ({provider})")
                else:
                    logger.debug(f"⚠️ Model {model_name} defined but no API key found for {env_var_name}")
            else:
                logger.debug(f"⚠️ Model {model_name} has invalid API key reference: {api_key_ref}")
        
        logger.info(f"Retrieved {len(configured_models)} configured models from litellm_config.yaml")
        
        # Return flat list of models
        return JSONResponse(content={"models": configured_models})
    except Exception as e:
        logger.error(f"Error getting configured models from litellm config: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e)) 