# Six Articles Configuration System - Custom Prompts & Organizational Profile Integration

## Issue Type
✨ Feature Implementation - Complete

## Summary
Implemented full integration of custom Six Articles configuration (prompts, personas, format specs) with organizational profile data. Previously, the configuration modal saved settings to the database but the actual article generation used hardcoded defaults. Now the system loads user-specific configurations and applies them during AI generation.

## Problem Statement
1. **Custom prompts not applied**: Users could customize Six Articles prompts via the configuration modal, but these were stored but never used in actual generation
2. **Organizational profiles underutilized**: While org profile data was fetched, it wasn't deeply integrated with persona contexts
3. **Cache pollution risk**: Without user_id in cache keys, users with custom configs could see each other's cached results
4. **Persona customization ignored**: Custom persona definitions (priorities, risk appetite, focus) were saved but never loaded during generation

## Solution Implemented

### 1. Schema Changes
**File**: `app/schemas/news_feed.py`
- Added `user_id: Optional[int]` field to `NewsFeedRequest` schema
- Enables passing authenticated user identity through request pipeline

### 2. API Route Updates
**File**: `app/routes/news_feed_routes.py:202-250`
- Added `session=Depends(verify_session)` dependency to `/api/news-feed/six-articles` endpoint
- Extract user_id from session: `user_id = session.get("user_id")`
- Pass user_id in NewsFeedRequest object for downstream processing

### 3. Prompt Builder Refactoring
**File**: `app/services/news_feed_service.py`

#### Simple Prompt Builder (`_build_six_articles_analyst_prompt()` - lines 920-1135)
```python
def _build_six_articles_analyst_prompt(
    self,
    articles_data: List[Dict],
    date: datetime,
    org_profile: Optional[Dict] = None,
    persona: str = "CEO",
    article_count: int = 6,
    starred_articles: Optional[List[str]] = None,
    user_id: Optional[int] = None  # NEW
) -> str:
```

**Changes**:
- Loads custom configuration from database using `self.facade.get_six_articles_config(user_id)`
- Merges custom persona definitions with hardcoded defaults
- Supports custom prompt templates with placeholder substitution:
  - `{persona}` - Persona title (CEO, CMO, CTO, CISO)
  - `{article_count}` - Number of articles to select
  - `{persona_description}` - Full persona description
  - `{persona_focus}` - Persona-specific focus areas
  - `{starred_instruction}` - Starred articles instruction (if applicable)
  - `{audience_profile}` - Audience profile (org or persona defaults)
  - `{articles_summary}` - Article corpus for selection
- Falls back to hardcoded default prompt if no custom config exists

#### Enhanced Prompt Builder (`_build_enhanced_six_articles_analyst_prompt()` - lines 1203-1340+)
```python
def _build_enhanced_six_articles_analyst_prompt(
    self,
    articles_data: List[Dict],
    articles_with_bias: List[Dict],
    articles_by_source: Dict,
    date: datetime,
    org_profile: Optional[Dict] = None,
    persona: str = "CEO",
    article_count: int = 6,
    starred_articles: Optional[List[str]] = None,
    user_id: Optional[int] = None  # NEW
) -> str:
```

**Changes**:
- Same custom config loading logic as simple builder
- Additional placeholders for enhanced political analysis context:
  - `{bias_context}` - Political bias distribution across sources
  - `{source_context}` - Source distribution statistics
- Maintains full backward compatibility

### 4. Organizational Profile Integration
**File**: `app/services/news_feed_service.py:1137-1201`

#### Enhanced `_build_audience_profile_from_org()` method
```python
def _build_audience_profile_from_org(
    self,
    org_profile: Dict,
    persona_info: Optional[Dict] = None  # NEW
) -> str:
```

**Changes**:
- Now accepts optional `persona_info` parameter
- Merges organizational profile data with persona-specific priorities:
  - Combines org's `key_concerns` + `strategic_priorities` + persona `priorities`
  - Removes duplicates while preserving order
  - Adds persona focus to profile text section
- Creates unified audience profile that respects both organizational context and persona selection
- Example output:
  ```markdown
  ## Audience Profile (Acme Corp)
  - **Organization**: Acme Corp (Enterprise)
  - **Industry**: Technology
  - **Region**: North America
  - **Risk Appetite**: Moderate (balanced between innovation and caution)
  - **Innovation Appetite**: Aggressive (cutting-edge technology adoption)
  - **Strategic Interests**: AI regulation, data privacy, enterprise adoption, Technical breakthroughs, infrastructure
  - **Persona Focus**: technical architecture, development practices, technology stack decisions
  - **Competitive Focus**: Google Cloud AI, AWS Bedrock
  - **Regulatory Concerns**: GDPR compliance, AI Act readiness
  ```

### 5. Cache Key Updates
**File**: `app/services/news_feed_service.py:637-688`

**Changes**:
- Updated cache key format to **v5**: `six_articles_v5_{date}_{topic}_{persona}_{article_count}_{user_id}`
- Previous v4 format: `six_articles_v4_{date}_{topic}_{persona}_{article_count}` (missing user_id)
- Prevents cross-user cache pollution when users have different custom configurations
- Added `user_id` to cache metadata for debugging and auditing:
  ```json
  {
    "date": "2025-10-30",
    "topic": "all",
    "persona": "CTO",
    "requested_article_count": 6,
    "returned_article_count": 6,
    "source_article_count": 50,
    "user_id": 42,
    "format_version": "ceo_daily_v5"
  }
  ```

### 6. Call Chain Updates
**File**: `app/services/news_feed_service.py:786-800`

Updated `_generate_six_articles_with_political_analysis()` to pass user_id:
```python
prompt = self._build_enhanced_six_articles_analyst_prompt(
    articles_data,
    articles_with_bias,
    articles_by_source,
    date,
    org_profile,
    persona=request.persona,
    article_count=request.article_count,
    starred_articles=request.starred_articles,
    user_id=request.user_id  # NEW
)
```

## Data Flow

### End-to-End Flow
1. **User customizes configuration** in modal (UI) → saved to `user_preferences` table via `POST /api/news-feed/six-articles/config`
2. **User selects persona + article count** (e.g., "CTO, 3 articles") and clicks "Write"
3. **Frontend sends request** to `GET /api/news-feed/six-articles?persona=CTO&article_count=3`
4. **Backend extracts user_id** from authenticated session
5. **Request object created** with `user_id` field populated
6. **Prompt builder invoked** with `user_id` parameter
7. **Custom config loaded** from database: `db.facade.get_six_articles_config(user_id)`
8. **If custom config exists**:
   - Custom persona definitions merged with defaults (custom overrides default)
   - Custom prompt template loaded
   - Placeholders replaced with actual values
9. **If organizational profile selected**:
   - Org profile data loaded
   - Combined with persona context
   - Strategic interests merged (org concerns + persona priorities)
10. **AI generates articles** using fully customized prompt
11. **Result cached** with user-specific key: `six_articles_v5_2025-10-30_all_CTO_3_{user_id}`
12. **Articles returned** to frontend for display

### Database Schema Usage

#### `user_preferences` table
```sql
CREATE TABLE user_preferences (
    user_id INTEGER NOT NULL,
    preference_key TEXT NOT NULL,
    config_value TEXT,  -- JSON blob containing custom config
    updated_at TIMESTAMP,
    PRIMARY KEY (user_id, preference_key)
);
```

#### Config structure (JSON)
```json
{
  "systemPrompt": "🎯 {persona} Daily Top-{article_count} AI Articles...",
  "personas": {
    "CEO": {
      "priorities": "Custom priorities here",
      "riskAppetite": "high",
      "focus": "Custom focus areas"
    },
    "CMO": { ... },
    "CTO": { ... },
    "CISO": { ... }
  },
  "formatSpec": { ... }
}
```

## Benefits

✅ **Custom prompts now actively used** - Configuration modal changes directly affect article generation
✅ **Organizational context integrated** - Company risk appetite, strategic interests, and regulatory concerns influence article selection
✅ **User-specific caching** - No cache pollution between users with different configurations
✅ **Backward compatible** - Users without custom config automatically use sensible hardcoded defaults
✅ **Flexible customization** - Users can customize prompts while maintaining structural integrity via placeholders
✅ **Intelligent merging** - Org profile priorities + persona priorities combined with deduplication
✅ **Cache invalidation fixed** - Changing persona, article count, or user config properly invalidates cache

## Testing Recommendations

### Manual Testing Scenarios

1. **Default behavior (no custom config)**
   - User without custom config clicks "Write"
   - Should use hardcoded default prompts
   - Should behave identically to previous version

2. **Custom prompt template**
   - User saves custom prompt with placeholders in modal
   - Click "Write" with CEO persona
   - Verify AI response uses custom prompt structure
   - Check logs for: `"Using custom prompt template for user {user_id}"`

3. **Custom persona definitions**
   - Customize CMO persona priorities in modal
   - Select CMO persona and generate
   - Verify generated articles reflect custom priorities

4. **Organizational profile integration**
   - Create org profile with specific risk tolerance and strategic interests
   - Select org profile + CTO persona
   - Verify audience profile includes both org data and persona focus
   - Check articles reflect combined context

5. **Cache isolation**
   - User A saves custom config
   - User B uses default config
   - Both generate for same date/persona/count
   - Verify User B doesn't get User A's customized results

6. **Placeholder replacement**
   - Create custom prompt with all placeholders
   - Generate articles with different personas and counts
   - Verify all placeholders correctly substituted

7. **Fallback behavior**
   - User saves invalid JSON config
   - Should log warning and fall back to defaults
   - Article generation should still work

### Automated Test Cases (Recommended)

```python
# Test 1: Config loading
def test_load_custom_config():
    config = db.facade.get_six_articles_config(user_id=123)
    assert config['systemPrompt'] is not None
    assert 'CEO' in config['personas']

# Test 2: Persona merging
def test_merge_custom_persona():
    custom_config = {
        'personas': {
            'CEO': {'priorities': 'Custom priorities'}
        }
    }
    # Verify merge logic produces correct result

# Test 3: Cache key uniqueness
def test_cache_key_includes_user_id():
    request1 = NewsFeedRequest(user_id=1, persona='CEO', article_count=6)
    request2 = NewsFeedRequest(user_id=2, persona='CEO', article_count=6)
    cache_key1 = generate_cache_key(request1)
    cache_key2 = generate_cache_key(request2)
    assert cache_key1 != cache_key2

# Test 4: Placeholder replacement
def test_placeholder_replacement():
    prompt = "{persona} - {article_count} articles"
    result = replace_placeholders(prompt, persona='CTO', article_count=3)
    assert result == "CTO - 3 articles"

# Test 5: Org profile + persona merging
def test_org_profile_persona_merge():
    org_profile = {'key_concerns': ['Security', 'Compliance']}
    persona_info = {'priorities': 'Tech, Infrastructure'}
    profile = build_audience_profile(org_profile, persona_info)
    assert 'Security' in profile
    assert 'Tech' in profile
    # Verify no duplicates
```

## Migration Notes

### Breaking Changes
❌ **None** - Fully backward compatible

### Cache Invalidation
⚠️ Existing cached six articles will remain in cache but won't be used due to v4→v5 cache key format change. Old cache entries will naturally expire over time (1 hour TTL).

### Database Changes
✅ No schema changes required - Uses existing `user_preferences` table

## Documentation Updates Needed

1. **User Guide**: Document how to use custom Six Articles configuration modal
2. **Developer Guide**: Explain placeholder system and custom prompt format
3. **API Docs**: Document new `user_id` field in NewsFeedRequest schema
4. **Admin Guide**: Explain cache key format for debugging

## Related Issues/PRs

- Original issue: Six Articles prompt customization + org profile integration
- Cache invalidation bug fix (v3→v4): Persona and article count not in cache key
- User-specific caching (v4→v5): Added user_id to prevent cross-user pollution

## Estimated Completion Time
✅ **Complete** - Approximately 2 hours of AI development time

## Files Modified

1. `app/schemas/news_feed.py` - Added user_id field to NewsFeedRequest
2. `app/routes/news_feed_routes.py` - Added session dependency and user_id extraction
3. `app/services/news_feed_service.py` - Refactored prompt builders, integrated config loading, enhanced org profile merging, updated cache keys
4. `app/database_query_facade.py` - Previously added get/save_six_articles_config methods (already implemented)

## Verification Commands

```bash
# Syntax check
python3 -m py_compile app/services/news_feed_service.py app/schemas/news_feed.py app/routes/news_feed_routes.py

# Check for user_id in cache keys
grep -n "six_articles_v5" app/services/news_feed_service.py

# Verify custom config loading
grep -n "get_six_articles_config" app/services/news_feed_service.py

# Check org profile integration
grep -n "_build_audience_profile_from_org" app/services/news_feed_service.py
```

## Screenshots/Examples

### Before (v3/v4)
- Custom config saved but ignored ❌
- Hardcoded persona contexts always used ❌
- Org profile fetched but not deeply integrated ❌
- Cache key: `six_articles_v4_2025-10-30_all_CEO_6` (missing user_id) ⚠️

### After (v5)
- Custom config loaded and applied ✅
- Custom persona definitions merged with defaults ✅
- Org profile + persona priorities intelligently combined ✅
- Cache key: `six_articles_v5_2025-10-30_all_CEO_6_42` (includes user_id) ✅

---

**Status**: ✅ Implementation Complete
**Priority**: High
**Labels**: `enhancement`, `feature`, `six-articles`, `configuration`, `organizational-profile`, `caching`
**Assignee**: AI Agent (Claude Code)
**Milestone**: Six Articles Configuration System v1.0
