# Prompt Workshop - Visual Flow Diagram

## System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        USER INTERFACE                                │
├─────────────────────────────────────────────────────────────────────┤
│  ┌──────────────────────┐  ┌────────────────────────────────────┐  │
│  │  Conversation Panel  │  │    Editor & Testing Panel          │  │
│  ├──────────────────────┤  ├────────────────────────────────────┤  │
│  │                      │  │ ┌────┬──────┬─────────┐            │  │
│  │ • Workshop Assistant │  │ │Draft│Test │History  │ (Tabs)     │  │
│  │ • User Messages      │  │ └────┴──────┴─────────┘            │  │
│  │ • Code Block Extract │  │                                     │  │
│  │                      │  │ • Prompt Editor (Draft Tab)         │  │
│  │                      │  │ • Test Query Input (Test Tab)       │  │
│  │                      │  │ • Results Display (Test Tab)        │  │
│  │                      │  │ • Test History List (History Tab)   │  │
│  │                      │  │                                     │  │
│  │ [Send Message]       │  │ [Save] [Test] [Commit]              │  │
│  └──────────────────────┘  └────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
                               ↕ (API calls)
┌─────────────────────────────────────────────────────────────────────┐
│                         API LAYER                                    │
├─────────────────────────────────────────────────────────────────────┤
│  POST /prompts/workshop/start         → Create session              │
│  GET  /prompts/workshop/drafts        → List user's drafts          │
│  GET  /prompts/workshop/drafts/{id}   → Get draft details           │
│  PUT  /prompts/workshop/drafts/{id}   → Update draft                │
│  POST /prompts/workshop/drafts/{id}/test    → Run test query        │
│  GET  /prompts/workshop/drafts/{id}/tests   → Test history          │
│  POST /prompts/workshop/drafts/{id}/commit  → Finalize prompt       │
│  DELETE /prompts/workshop/drafts/{id} → Delete draft                │
│  POST /prompts/{name}/clone           → Clone to draft              │
└─────────────────────────────────────────────────────────────────────┘
                               ↕
┌─────────────────────────────────────────────────────────────────────┐
│                      SERVICE LAYER                                   │
├─────────────────────────────────────────────────────────────────────┤
│  AuspexService Methods:                                              │
│  • create_prompt_workshop()      → Initialize session                │
│  • test_draft_prompt()           → Execute test with draft prompt    │
│  • commit_draft_to_prompt()      → Convert draft to permanent        │
│  • clone_prompt_to_draft()       → Clone existing prompt             │
│  • _get_workshop_meta_prompt()   → Workshop assistant instructions   │
│                                                                       │
│  Uses existing:                                                       │
│  • create_chat_session()         → For workshop conversation         │
│  • chat_with_tools()             → For test execution                │
│  • create_auspex_prompt()        → For commit                        │
└─────────────────────────────────────────────────────────────────────┘
                               ↕
┌─────────────────────────────────────────────────────────────────────┐
│                   DATABASE LAYER                                     │
├─────────────────────────────────────────────────────────────────────┤
│  DatabaseQueryFacade Methods:                                        │
│  • create_prompt_draft()                                             │
│  • get_prompt_draft()                                                │
│  • list_prompt_drafts()                                              │
│  • update_prompt_draft()                                             │
│  • append_draft_test_result()                                        │
│  • delete_prompt_draft()                                             │
└─────────────────────────────────────────────────────────────────────┘
                               ↕
┌─────────────────────────────────────────────────────────────────────┐
│                      DATABASE TABLES                                 │
├─────────────────────────────────────────────────────────────────────┤
│  auspex_prompt_drafts (NEW)    auspex_chats (existing)              │
│  • id                           • id                                 │
│  • user_id                      • topic = "__prompt_workshop__"      │
│  • draft_name                   • user_id                            │
│  • draft_content                • messages                           │
│  • workshop_chat_id  ───────────┘                                    │
│  • status                                                             │
│  • test_results (JSON)                                               │
│                                                                       │
│  auspex_prompts (existing)                                           │
│  • name (committed prompts)                                          │
│  • content                                                            │
└─────────────────────────────────────────────────────────────────────┘
```

---

## User Journey Flow

### Scenario: Financial Analyst Prompt Creation

```
┌─────────────────────────────────────────────────────────────────────┐
│ STEP 1: Initiation                                                   │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│ User: [Clicks "Prompt Workshop" in navigation]                       │
│   ↓                                                                   │
│ System: Creates draft record & workshop chat                         │
│   ↓                                                                   │
│ UI: Displays workshop interface                                      │
│   ↓                                                                   │
│ Workshop Assistant:                                                  │
│   "Hello! I'll help you design a custom Auspex prompt.               │
│    What type of research or analysis do you need?"                   │
│                                                                       │
└─────────────────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────────────┐
│ STEP 2: Requirements Gathering                                       │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│ User: "I need a prompt for financial analysis focused on             │
│        executive-level risk assessment"                              │
│   ↓                                                                   │
│ Workshop Assistant:                                                  │
│   "Great! To design the best prompt, I need to know:                 │
│    1. What level of technical detail? (Executive summary vs deep)    │
│    2. Should quantitative data be emphasized?                        │
│    3. Which risk types? (market, credit, operational, etc.)          │
│    4. Preferred output format? (narrative, tables, bullets)"         │
│   ↓                                                                   │
│ User: "Executive level, highlight key numbers, focus on market       │
│        and operational risks, use bullet points"                     │
│                                                                       │
└─────────────────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────────────┐
│ STEP 3: Draft Generation                                             │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│ Workshop Assistant:                                                  │
│   "Perfect. Here's a draft prompt tailored to your needs:            │
│                                                                       │
│   ```                                                                 │
│   You are Auspex, a financial risk analyst specializing in           │
│   executive-level assessments.                                       │
│                                                                       │
│   ## Focus Areas:                                                    │
│   - **Market Risk:** Price volatility, market conditions             │
│   - **Operational Risk:** Business disruptions, process failures     │
│                                                                       │
│   ## Output Requirements:                                            │
│   - Use bullet points for key findings                               │
│   - **Bold** all quantitative metrics (%, $, numbers)                │
│   - Provide risk severity: Low/Medium/High/Critical                  │
│   - Include 2-3 actionable recommendations                           │
│                                                                       │
│   ## Citation Rules:                                                 │
│   - Cite every data point inline: [Article Title](URL)              │
│   - Note date of data for temporal context                           │
│   ```                                                                 │
│                                                                       │
│   Does this capture your requirements?"                              │
│   ↓                                                                   │
│ User: [Clicks "Extract Draft"]                                       │
│   ↓                                                                   │
│ System: Extracts prompt from code block → populates editor           │
│                                                                       │
└─────────────────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────────────┐
│ STEP 4: Testing & Validation                                         │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│ User: [Switches to "Test" tab]                                       │
│   ↓                                                                   │
│ User: Enters test query: "Analyze market risks for Tesla stock"      │
│       Topic: "Financial Markets"                                     │
│       Model: "gpt-4.1-mini"                                          │
│   ↓                                                                   │
│ User: [Clicks "Run Test"]                                            │
│   ↓                                                                   │
│ System:                                                               │
│   1. Saves current draft                                             │
│   2. Creates temporary chat with draft prompt                        │
│   3. Executes query with Auspex tools                                │
│   4. Captures response + metrics                                     │
│   5. Stores test result                                              │
│   6. Cleans up temp chat                                             │
│   ↓                                                                   │
│ UI Displays:                                                          │
│   Metrics:  [45 articles] [2,300ms] [1,850 chars]                   │
│   Response: "## Market Risk Analysis for Tesla                       │
│              • **Volatility:** 52-week range $138-299 (+117%)        │
│                [Tesla Stock Performance](url)                        │
│              • **Market Conditions:** EV sector headwinds...          │
│              [...]"                                                   │
│   ↓                                                                   │
│ User: Reviews output, rates 4/5 stars                                │
│                                                                       │
└─────────────────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────────────┐
│ STEP 5: Refinement (Optional)                                        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│ User: "The timeline info is weak. Add more emphasis on risk timing"  │
│   ↓                                                                   │
│ Workshop Assistant:                                                  │
│   "I'll update the prompt to emphasize risk timelines:               │
│                                                                       │
│   ```                                                                 │
│   ## Output Requirements:                                            │
│   - Use bullet points for key findings                               │
│   - **Bold** all quantitative metrics                                │
│   - **Specify risk timelines:**                                      │
│     - Immediate (0-3 months)                                         │
│     - Short-term (3-12 months)                                       │
│     - Medium-term (1-3 years)                                        │
│   - Provide risk severity + timeline for each risk                   │
│   ```"                                                                │
│   ↓                                                                   │
│ User: [Extracts → Tests again → Satisfied]                           │
│                                                                       │
└─────────────────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────────────┐
│ STEP 6: Commit to Production                                         │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│ User: [Clicks "Commit as Prompt"]                                    │
│   ↓                                                                   │
│ Modal: "Enter prompt details:"                                       │
│   Name: financial_risk_executive                                     │
│   Title: Financial Risk Analysis (Executive)                         │
│   Description: Executive-level risk assessment for financial markets │
│   ↓                                                                   │
│ User: [Clicks "Commit"]                                              │
│   ↓                                                                   │
│ System:                                                               │
│   1. Validates name uniqueness                                       │
│   2. Creates record in auspex_prompts table                          │
│   3. Marks draft as "committed"                                      │
│   4. Redirects to Auspex Chat                                        │
│   ↓                                                                   │
│ Success: "Prompt 'financial_risk_executive' created!"                │
│   ↓                                                                   │
│ User can now select this prompt in regular Auspex sessions           │
│                                                                       │
└─────────────────────────────────────────────────────────────────────┘
```

---

## State Transitions

### Draft Lifecycle

```
┌─────────┐
│  START  │
└────┬────┘
     │ create_prompt_workshop()
     ↓
┌─────────┐
│  DRAFT  │ ← User editing, conversing
└────┬────┘
     │ run test
     ↓
┌─────────┐
│ TESTING │ ← Running tests, getting feedback
└────┬────┘
     │ satisfied with tests
     ↓
┌─────────┐
│  READY  │ ← Prepared for commit
└────┬────┘
     │ commit_draft_to_prompt()
     ↓
┌───────────┐
│ COMMITTED │ → Permanent prompt in library
└───────────┘

Side branches:
- Any state → DELETE (user cancels)
- READY → back to DRAFT (more edits needed)
```

---

## Data Flow: Test Execution

```
┌──────────────────┐
│ User clicks      │
│ "Run Test"       │
└────────┬─────────┘
         │
         ↓
┌────────────────────────────────────────────────────────────────┐
│ Frontend (prompt-workshop.js)                                  │
├────────────────────────────────────────────────────────────────┤
│ 1. Collect inputs: query, topic, model                         │
│ 2. Save draft first (auto-save)                                │
│ 3. POST /api/auspex/prompts/workshop/drafts/{id}/test          │
│    Body: { test_query, topic, model, limit }                   │
└────────┬───────────────────────────────────────────────────────┘
         │
         ↓
┌────────────────────────────────────────────────────────────────┐
│ Backend Route (auspex_routes.py)                               │
├────────────────────────────────────────────────────────────────┤
│ 1. Verify draft ownership                                      │
│ 2. Call auspex.test_draft_prompt()                             │
└────────┬───────────────────────────────────────────────────────┘
         │
         ↓
┌────────────────────────────────────────────────────────────────┐
│ Service Layer (auspex_service.py)                              │
├────────────────────────────────────────────────────────────────┤
│ 1. Get draft content from database                             │
│ 2. Create temporary chat session                               │
│ 3. Execute: chat_with_tools(                                   │
│       chat_id=temp_chat,                                        │
│       message=test_query,                                       │
│       custom_prompt=draft['draft_content']  ← KEY!             │
│    )                                                            │
│ 4. Collect response chunks                                     │
│ 5. Measure: execution_time, article_count, tools_used          │
│ 6. Create test_result object                                   │
│ 7. Append to draft.test_results JSON array                     │
│ 8. Delete temporary chat                                       │
│ 9. Return test_result                                          │
└────────┬───────────────────────────────────────────────────────┘
         │
         ↓
┌────────────────────────────────────────────────────────────────┐
│ Database (auspex_prompt_drafts)                                │
├────────────────────────────────────────────────────────────────┤
│ test_results JSON structure:                                   │
│ [                                                               │
│   {                                                             │
│     "test_id": "uuid",                                          │
│     "query": "Analyze Tesla risks",                            │
│     "response_preview": "First 500 chars...",                  │
│     "article_count": 45,                                       │
│     "execution_time_ms": 2300,                                 │
│     "timestamp": "2025-01-15T10:30:00Z",                       │
│     "user_rating": null  ← Can be updated later                │
│   }                                                             │
│ ]                                                               │
└────────┬───────────────────────────────────────────────────────┘
         │
         ↓
┌────────────────────────────────────────────────────────────────┐
│ Frontend Display                                                │
├────────────────────────────────────────────────────────────────┤
│ • Show metrics: articles, time, length                          │
│ • Render response preview (markdown)                            │
│ • Enable rating (1-5 stars)                                    │
│ • Add to test history list                                     │
└────────────────────────────────────────────────────────────────┘
```

---

## Integration Points with Existing System

```
┌───────────────────────────────────────────────────────────────┐
│ Prompt Workshop (NEW)                                          │
└───────┬───────────────────────────────────────────────────────┘
        │
        ├─→ Uses: create_chat_session()
        │   Purpose: Workshop conversation + temp test chats
        │   Table: auspex_chats (existing)
        │
        ├─→ Uses: chat_with_tools()
        │   Purpose: Test query execution with draft prompt
        │   Via: custom_prompt parameter (existing)
        │
        ├─→ Uses: create_auspex_prompt()
        │   Purpose: Commit draft to permanent prompt library
        │   Table: auspex_prompts (existing)
        │
        ├─→ Uses: get_auspex_prompt()
        │   Purpose: Clone existing prompt to draft
        │   For: "Clone & Modify" workflow
        │
        └─→ Uses: delete_chat_session()
            Purpose: Clean up temporary test chats
```

---

## Error Handling Flow

```
User Action → Validation → Error Response

Examples:

1. Commit with duplicate name:
   User clicks "Commit"
     → Backend checks: existing = db.get_auspex_prompt(name)
     → If exists: raise HTTPException(400, "Name already exists")
     → Frontend: alert("Failed to commit: Name already exists")

2. Test with empty draft:
   User clicks "Run Test"
     → Backend validates: len(draft_content) >= 100
     → If too short: raise ValueError("Content too short")
     → Frontend: alert("Draft must be at least 100 characters")

3. Load non-existent draft:
   URL: /prompt-workshop?draft_id=999
     → Backend: draft = db.get_prompt_draft(999)
     → If None: HTTPException(404, "Draft not found")
     → Frontend: alert("Draft not found")

4. Access another user's draft:
   User tries to access draft owned by different user
     → Backend: draft['user_id'] != current_user
     → HTTPException(403, "Access denied")
     → Frontend: redirect to home
```

---

## Performance Considerations

### Database Queries

**Frequently accessed:**
- `get_prompt_draft(id)` - Single row lookup by PK (fast)
- `list_prompt_drafts(user_id)` - Indexed on user_id (fast)

**Heavy operations:**
- `test_draft_prompt()` - Creates temp chat, runs full Auspex query (5-30s)
- Solution: Show loading indicator, stream results if possible

**Storage growth:**
- `test_results` JSON grows with each test
- Mitigation: Keep only last 20 tests, truncate older

### API Response Times

| Endpoint | Expected Time | Notes |
|----------|--------------|-------|
| POST /workshop/start | 2-5s | Creates chat + generates initial message |
| GET /drafts | <100ms | Simple list query |
| PUT /drafts/{id} | <100ms | Update fields only |
| POST /drafts/{id}/test | 5-30s | Full Auspex execution |
| POST /drafts/{id}/commit | <200ms | Create prompt record |

### Frontend Optimization

- **Auto-save debouncing:** 2 seconds delay prevents excessive saves
- **Chat history:** Load once on page load, not on every tab switch
- **Test history:** Refresh only after running new test

---

This visual flow diagram complements the technical specifications and provides a clear understanding of how the Prompt Workshop operates at every level of the system.
