# Prompt Workshop - Implementation Guide

## Quick Start

This guide provides a step-by-step implementation plan for the Prompt Workshop feature. Full technical specifications are in [PROMPT_WORKSHOP_SPECS.md](./PROMPT_WORKSHOP_SPECS.md).

---

## Implementation Order

### Step 1: Database Layer (1-2 hours)

**Create Migration:**
```bash
cd /home/orochford/tenants/gp.aunoo.ai
alembic revision -m "add_prompt_workshop_tables"
```

**Files to modify:**
1. `alembic/versions/YYYYMMDD_add_prompt_workshop_tables.py` - Copy from specs section 1.2
2. Run migration: `alembic upgrade head`

**Verification:**
```sql
-- Check table exists
SELECT * FROM sqlite_master WHERE type='table' AND name='auspex_prompt_drafts';

-- Check indexes
SELECT * FROM sqlite_master WHERE type='index' AND tbl_name='auspex_prompt_drafts';
```

---

### Step 2: Database Facade (2-3 hours)

**Add methods to `app/database_query_facade.py`:**

Core CRUD operations needed:
- `create_prompt_draft()` - Create new draft record
- `get_prompt_draft()` - Retrieve draft by ID
- `list_prompt_drafts()` - List user's drafts
- `update_prompt_draft()` - Update draft fields
- `append_draft_test_result()` - Add test result to JSON array
- `delete_prompt_draft()` - Remove draft

**Copy implementations from:** Specs section 4

**Test each method:**
```python
# test_prompt_drafts.py
from app.database import get_database_instance

db = get_database_instance()

# Test create
draft_id = db.facade.create_prompt_draft(
    user_id="test_user",
    draft_content="Test prompt content",
    draft_name="Test Draft"
)
print(f"Created draft {draft_id}")

# Test retrieve
draft = db.facade.get_prompt_draft(draft_id)
assert draft['draft_name'] == "Test Draft"

# Test update
success = db.facade.update_prompt_draft(
    draft_id=draft_id,
    user_id="test_user",
    draft_content="Updated content",
    status="testing"
)
assert success

# Test list
drafts = db.facade.list_prompt_drafts("test_user")
assert len(drafts) >= 1

# Clean up
db.facade.delete_prompt_draft(draft_id)
```

---

### Step 3: Service Layer (3-4 hours)

**Add methods to `app/services/auspex_service.py`:**

Key methods:
1. `create_prompt_workshop()` - Initialize workshop session
2. `test_draft_prompt()` - Execute test query
3. `commit_draft_to_prompt()` - Finalize to permanent prompt
4. `clone_prompt_to_draft()` - Clone existing prompt
5. `_get_workshop_meta_prompt()` - Workshop assistant instructions

**Copy implementations from:** Specs section 3

**Key integration points:**
- Uses existing `create_chat_session()` for workshop chat
- Uses existing `chat_with_tools()` for test execution
- Uses existing `create_auspex_prompt()` for commit
- Uses existing `delete_chat_session()` for cleanup

**Test service methods:**
```python
# test_workshop_service.py
from app.services.auspex_service import get_auspex_service
import asyncio

async def test_workshop():
    auspex = get_auspex_service()

    # Test create workshop
    result = await auspex.create_prompt_workshop(
        user_id="test_user",
        requirements="I need a financial analysis prompt"
    )

    draft_id = result['draft_id']
    print(f"Workshop created: draft_id={draft_id}, chat_id={result['chat_id']}")

    # Test test_draft_prompt
    test_result = await auspex.test_draft_prompt(
        draft_id=draft_id,
        user_id="test_user",
        test_query="Analyze AI trends",
        topic="AI Adoption",
        limit=10
    )

    print(f"Test completed: {test_result['article_count']} articles")

    # Clean up
    auspex.delete_prompt_draft(draft_id, "test_user")

asyncio.run(test_workshop())
```

---

### Step 4: API Routes (2-3 hours)

**Add routes to `app/routes/auspex_routes.py`:**

Routes to implement:
1. `POST /api/auspex/prompts/workshop/start` - Start session
2. `GET /api/auspex/prompts/workshop/drafts` - List drafts
3. `GET /api/auspex/prompts/workshop/drafts/{id}` - Get draft
4. `PUT /api/auspex/prompts/workshop/drafts/{id}` - Update draft
5. `POST /api/auspex/prompts/workshop/drafts/{id}/test` - Run test
6. `GET /api/auspex/prompts/workshop/drafts/{id}/tests` - Test history
7. `POST /api/auspex/prompts/workshop/drafts/{id}/commit` - Commit
8. `DELETE /api/auspex/prompts/workshop/drafts/{id}` - Delete
9. `POST /api/auspex/prompts/{name}/clone` - Clone prompt

**Copy implementations from:** Specs section 2.2

**Test API endpoints:**
```bash
# Start workshop
curl -X POST http://localhost:8000/api/auspex/prompts/workshop/start \
  -H "Content-Type: application/json" \
  -d '{"requirements": "Test"}'

# List drafts
curl http://localhost:8000/api/auspex/prompts/workshop/drafts

# Get draft
curl http://localhost:8000/api/auspex/prompts/workshop/drafts/1

# Run test
curl -X POST http://localhost:8000/api/auspex/prompts/workshop/drafts/1/test \
  -H "Content-Type: application/json" \
  -d '{"test_query": "Test", "topic": "AI Adoption"}'

# Commit
curl -X POST http://localhost:8000/api/auspex/prompts/workshop/drafts/1/commit \
  -H "Content-Type: application/json" \
  -d '{"name": "test_prompt", "title": "Test", "description": "Test"}'
```

---

### Step 5: Frontend UI (4-6 hours)

**Create new files:**

1. **HTML Template:** `templates/prompt-workshop.html`
   - Copy complete structure from specs section 5.1
   - Two-panel layout: conversation | editor
   - Tabs for Draft/Test/History

2. **CSS Styles:** `static/css/prompt-workshop.css`
   - Copy styles from specs section 5.2
   - Responsive design
   - Professional appearance

3. **JavaScript Controller:** `static/js/prompt-workshop.js`
   - Copy `PromptWorkshop` class from specs section 5.3
   - Handles all UI interactions
   - API communication
   - Real-time updates

**Add route handler:**

In `app/main.py` or relevant router:
```python
@app.get("/prompt-workshop")
async def prompt_workshop_page(request: Request, session=Depends(verify_session)):
    """Render prompt workshop interface."""
    return templates.TemplateResponse(
        "prompt-workshop.html",
        {"request": request, "user": session.get('user')}
    )
```

---

### Step 6: Integration (1-2 hours)

**Update existing UI components:**

1. **Prompt Manager** (`templates/auspex-prompt-manager.html`):
   ```html
   <!-- Add Workshop button -->
   <button class="btn btn-primary" onclick="location.href='/prompt-workshop'">
       <i class="fas fa-flask"></i> Workshop Mode
   </button>
   ```

2. **Auspex Chat** (`static/js/auspex-chat.js`):
   ```javascript
   // Add clone option to prompt actions
   clonePrompt(promptName) {
       window.location.href = `/prompt-workshop?clone=${promptName}`;
   }
   ```

3. **Navigation** (`templates/base.html`):
   ```html
   <li class="nav-item">
       <a class="nav-link" href="/prompt-workshop">
           <i class="fas fa-brain"></i> Prompt Workshop
       </a>
   </li>
   ```

---

## Testing Plan

### Unit Tests

```python
# tests/test_prompt_workshop.py
import pytest
from app.database import get_database_instance
from app.services.auspex_service import get_auspex_service

@pytest.fixture
def db():
    return get_database_instance()

@pytest.fixture
def auspex():
    return get_auspex_service()

def test_create_draft(db):
    """Test draft creation in database."""
    draft_id = db.facade.create_prompt_draft(
        user_id="test",
        draft_content="Test content"
    )
    assert draft_id > 0

    draft = db.facade.get_prompt_draft(draft_id)
    assert draft['draft_content'] == "Test content"

    db.facade.delete_prompt_draft(draft_id)

@pytest.mark.asyncio
async def test_workshop_flow(auspex):
    """Test complete workshop workflow."""
    # Create workshop
    result = await auspex.create_prompt_workshop(
        user_id="test",
        requirements="Test prompt"
    )
    draft_id = result['draft_id']

    # Update draft
    success = auspex.update_prompt_draft(
        draft_id=draft_id,
        user_id="test",
        draft_content="Updated prompt content",
        status="testing"
    )
    assert success

    # Run test
    test_result = await auspex.test_draft_prompt(
        draft_id=draft_id,
        user_id="test",
        test_query="Test query",
        topic="AI Adoption",
        limit=5
    )
    assert test_result['test_id']

    # Commit
    prompt_id = await auspex.commit_draft_to_prompt(
        draft_id=draft_id,
        user_id="test",
        name="test_prompt_123",
        title="Test Prompt"
    )
    assert prompt_id > 0

    # Cleanup
    auspex.db.delete_auspex_prompt("test_prompt_123")
```

### Integration Tests

**Manual testing checklist:**
- [ ] Create new workshop session
- [ ] Converse with workshop assistant
- [ ] Extract prompt from code block
- [ ] Edit prompt manually
- [ ] Save draft (auto and manual)
- [ ] Run test query
- [ ] View test results
- [ ] Rate test result
- [ ] View test history
- [ ] Update draft status
- [ ] Commit draft to permanent prompt
- [ ] Verify prompt appears in prompt list
- [ ] Clone existing prompt
- [ ] Delete draft
- [ ] Close workshop

---

## Deployment Steps

### 1. Database Migration

```bash
# Backup database first
cp app.db app.db.backup

# Run migration
python -m alembic upgrade head

# Verify
python -c "from app.database import get_database_instance; db = get_database_instance(); print(db.facade.list_prompt_drafts('test_user'))"
```

### 2. Code Deployment

```bash
# Ensure all files are in place
ls -la templates/prompt-workshop.html
ls -la static/css/prompt-workshop.css
ls -la static/js/prompt-workshop.js

# Restart server
# For development:
python app/run.py

# For production:
sudo systemctl restart aunooai
```

### 3. Verification

1. Visit `http://localhost:8000/prompt-workshop`
2. Check console for JavaScript errors
3. Test API endpoints
4. Run through complete workflow

---

## Common Issues & Solutions

### Issue: Draft not saving
**Solution:** Check browser console for API errors. Verify `draft_id` is set correctly.

### Issue: Test execution fails
**Solution:** Ensure draft has valid content (min 100 chars). Check topic exists in database.

### Issue: Commit fails with duplicate name
**Solution:** Prompt names must be unique. Check existing prompts first.

### Issue: Workshop assistant not responding
**Solution:** Verify chat session created correctly. Check AI model API keys.

### Issue: Code block extraction not working
**Solution:** Ensure message contains triple backticks. Check regex pattern.

---

## Performance Considerations

### Database

- Drafts table will grow over time - consider cleanup job for old drafts
- Index on `user_id` ensures fast listing
- JSON `test_results` field can get large - limit to last 20 tests

### API

- Test execution can take 5-30 seconds depending on query
- Use streaming for chat responses
- Implement rate limiting on test endpoint

### Frontend

- Auto-save debounced to 2 seconds
- Chat history loaded once on page load
- Test history refreshed only after new tests

---

## Monitoring

### Metrics to Track

- Workshop sessions created per day
- Average tests per draft
- Commit rate (drafts → permanent prompts)
- User engagement (time in workshop)
- Most cloned prompts

### Logging

```python
# Add to auspex_service.py
logger.info(f"Workshop created: user={user_id}, draft_id={draft_id}")
logger.info(f"Test executed: draft_id={draft_id}, articles={article_count}, time={execution_time_ms}ms")
logger.info(f"Draft committed: draft_id={draft_id}, name={name}")
```

---

## Future Enhancements

### Phase 2 (Next Sprint)

1. **Prompt Templates Library**
   - Pre-built templates for common use cases
   - One-click start from template

2. **Version History**
   - Track prompt evolution over time
   - Diff view between versions
   - Restore previous versions

3. **Collaborative Editing**
   - Share drafts with team members
   - Real-time collaboration
   - Comments and suggestions

### Phase 3 (Future)

1. **AI-Powered Suggestions**
   - Analyze test results
   - Suggest prompt improvements
   - Auto-detect issues (citations, structure)

2. **A/B Testing Framework**
   - Compare two prompt versions
   - Track performance metrics
   - Statistical significance testing

3. **Public Prompt Sharing**
   - Community prompt library
   - Ratings and reviews
   - Fork and modify public prompts

---

## Resources

- **Full Specs:** [PROMPT_WORKSHOP_SPECS.md](./PROMPT_WORKSHOP_SPECS.md)
- **Database Schema:** See specs section 1
- **API Documentation:** See specs section 2
- **UI Components:** See specs section 5

---

## Support

For questions or issues:
1. Check this implementation guide
2. Review full specs document
3. Check common issues section
4. Review code comments

---

**Last Updated:** 2025-01-15
**Implementation Status:** Ready to Begin
