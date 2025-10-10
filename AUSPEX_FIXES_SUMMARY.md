# Auspex Functionality Fixes - Summary

**Date**: 2025-10-10
**Session**: Auspex article links and custom prompts issues

---

## Issues Identified and Fixed

### Issue 1: Missing Article Links in Auspex Responses ✓ DIAGNOSED

**Root Cause**: ChromaDB vector store out of sync with PostgreSQL database

**Details**:
- PostgreSQL database: **31,155 articles**
- ChromaDB (before reindex): **~0 articles**
- Auspex uses ChromaDB for semantic search to find relevant articles
- When ChromaDB is empty → No articles found → No article links in responses

**Evidence from logs**:
```
app.vector_store - ERROR - Vector search failed for query 'What are the key insights?'
– Error executing plan: Internal error: Error finding id
```

**Solution**: ChromaDB reindexing in progress
- **Status**: Currently at 12.4% complete (3,851 / 31,155 articles)
- **Command**: `.venv/bin/python scripts/reindex_chromadb.py --force`
- **ETA**: Several more hours (running in background)
- **Monitoring**: Run `.venv/bin/python check_chromadb_count.py` to check progress

**Expected Outcome**: Once reindexing completes, Auspex will be able to:
1. Perform semantic searches across all 31,155 articles
2. Return relevant article links with proper markdown formatting
3. Provide citation instructions per lines 1479-1483 in `auspex_service.py`

---

### Issue 2: Custom Prompts Being Ignored ✓ FIXED

**Root Cause**: No mechanism to override default system prompt

**Problem**:
- Auspex always used the default "Curious AI Template" system prompt
- User-pasted custom prompts were treated as part of the user message, not as system instructions
- `get_enhanced_system_prompt()` method always returned the default template with topic/profile enhancements
- No way to override this behavior

**Solution Implemented**: Added `custom_prompt` parameter to chat flow

**Files Modified**:

1. **`app/routes/auspex_routes.py` (line 173)**:
   - Added `custom_prompt` field to `ChatMessageRequest` model
   ```python
   custom_prompt: str | None = Field(None, description="Custom system prompt to override the default template")
   ```

2. **`app/routes/auspex_routes.py` (line 314)**:
   - Pass `custom_prompt` to `chat_with_tools()` method
   ```python
   async for chunk in auspex.chat_with_tools(req.chat_id, req.message, req.model, req.limit, req.tools_config, req.profile_id, req.custom_prompt):
   ```

3. **`app/services/auspex_service.py` (line 930)**:
   - Modified `chat_with_tools()` method signature to accept `custom_prompt` parameter
   - Added logic to use custom prompt when provided:
   ```python
   async def chat_with_tools(self, chat_id: int, message: str, model: str = None, limit: int = 50, tools_config: Dict = None, profile_id: int = None, custom_prompt: str = None) -> AsyncGenerator[str, None]:
       """Chat with Auspex with optional tool usage and custom system prompt override."""
       # ...
       # Use custom prompt if provided, otherwise get enhanced system prompt
       if custom_prompt:
           logger.info(f"Using custom system prompt for chat {chat_id}")
           system_prompt_content = custom_prompt
       else:
           # Get system prompt and enhance it with topic information and profile context
           system_prompt = self.get_enhanced_system_prompt(chat_id, tools_config)
           system_prompt_content = system_prompt['content']
   ```

**Service Restart**: ✓ Completed
```bash
sudo systemctl restart skunkworkx.aunoo.ai
```

---

## How to Use Custom Prompts (Backend Ready)

### API Usage

The backend now supports custom prompts via the `/api/auspex/chat/message` endpoint:

```bash
curl -X POST http://localhost:PORT/api/auspex/chat/message \
  -H "Content-Type: application/json" \
  -d '{
    "chat_id": 1,
    "message": "Analyze the current AI landscape",
    "model": "gpt-4o-mini",
    "custom_prompt": "You are a technical analyst focused on concrete data and specific examples. Avoid generalities. Always cite sources."
  }'
```

### Frontend Implementation (TODO)

**Note**: The frontend (`static/js/auspex-chat.js`) does NOT yet send the `custom_prompt` field.

**To enable this feature in the UI, the frontend needs to**:
1. Detect when user pastes a large block of text (potential custom prompt)
2. Show a prompt selector/input UI element
3. Send the `custom_prompt` field in the POST request body

**Example frontend code needed**:
```javascript
// In auspex-chat.js, modify the sendMessage() function:
const requestBody = {
    chat_id: this.currentChatId,
    message: message,
    model: this.selectedModel,
    limit: this.articleLimit,
    tools_config: this.toolsConfig,
    profile_id: this.selectedProfileId,
    custom_prompt: this.customPromptField.value || null  // NEW FIELD
};
```

---

## Testing

### Test Custom Prompts (Backend)

```bash
# Create a chat session
CHAT_RESPONSE=$(curl -X POST http://localhost:10015/api/auspex/chat/sessions \
  -H "Content-Type: application/json" \
  -H "Cookie: session=YOUR_SESSION" \
  -d '{"topic": "AI and Machine Learning", "title": "Custom Prompt Test"}')

CHAT_ID=$(echo $CHAT_RESPONSE | jq -r '.chat_id')

# Send message with custom prompt
curl -X POST http://localhost:10015/api/auspex/chat/message \
  -H "Content-Type: application/json" \
  -H "Cookie: session=YOUR_SESSION" \
  -d "{
    \"chat_id\": $CHAT_ID,
    \"message\": \"What are the latest trends?\",
    \"custom_prompt\": \"You are a skeptical analyst. Focus on risks and challenges, not hype. Be concise and data-driven.\"
  }"
```

### Monitor ChromaDB Reindex

```bash
# Check progress
.venv/bin/python check_chromadb_count.py

# Expected output:
# ChromaDB articles collection count: 3851 (12.4%)
```

---

## Status Summary

| Issue | Status | Details |
|-------|--------|---------|
| **Missing Article Links** | 🟡 In Progress | ChromaDB reindex at 12.4%, ETA: several hours |
| **Custom Prompts Ignored** | ✅ Fixed | Backend complete, frontend needs update |
| **Service Restart** | ✅ Complete | skunkworkx.aunoo.ai service running |

---

## Next Steps

### Immediate (Backend Complete)
1. ✅ Modified API to accept `custom_prompt` parameter
2. ✅ Updated `chat_with_tools()` to use custom prompts when provided
3. ✅ Restarted service to apply changes

### ChromaDB Reindex (In Progress)
1. 🟡 Wait for reindex to complete (currently 12.4%)
2. ⏳ Monitor progress with `check_chromadb_count.py`
3. ⏳ Once complete, Auspex will show article links again

### Frontend (TODO - Not Implemented)
1. ❌ Add custom prompt input UI to Auspex chat interface
2. ❌ Detect when user pastes prompts vs regular messages
3. ❌ Send `custom_prompt` field in API requests
4. ❌ Add prompt management UI (save/load custom prompts)

---

## Technical References

### Modified Files
1. `/home/orochford/tenants/skunkworkx.aunoo.ai/app/routes/auspex_routes.py`
   - Line 173: Added `custom_prompt` to ChatMessageRequest
   - Line 314: Pass `custom_prompt` to service

2. `/home/orochford/tenants/skunkworkx.aunoo.ai/app/services/auspex_service.py`
   - Line 930: Updated `chat_with_tools()` signature
   - Lines 972-979: Custom prompt override logic

### Related Documentation
- `SIGNAL_DATE_FIX_TECHNICAL_NOTES.md` - Date format fixes for real-time signals
- ChromaDB reindex script: `scripts/reindex_chromadb.py`
- Progress check script: `check_chromadb_count.py` (created this session)

---

## Change Log

| Date | Change | Status |
|------|--------|--------|
| 2025-10-10 14:36 | Added custom_prompt parameter to API | ✅ Complete |
| 2025-10-10 14:36 | Modified chat_with_tools() to use custom prompts | ✅ Complete |
| 2025-10-10 14:36 | Restarted skunkworkx.aunoo.ai service | ✅ Complete |
| 2025-10-10 14:17 | Started ChromaDB reindex (31,155 articles) | 🟡 12.4% |
| 2025-10-10 14:35 | Created progress monitoring script | ✅ Complete |

