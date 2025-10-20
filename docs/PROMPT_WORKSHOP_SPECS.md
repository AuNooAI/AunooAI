# Auspex Prompt Workshop - Technical Specifications

## Overview

The Prompt Workshop enables users to design, test, and refine custom Auspex system prompts through conversational AI assistance. This document provides complete technical specifications for implementation.

---

## 1. Database Schema

### 1.1 New Table: `auspex_prompt_drafts`

```sql
CREATE TABLE auspex_prompt_drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    draft_name TEXT,
    draft_content TEXT NOT NULL,
    draft_description TEXT,
    workshop_chat_id INTEGER,
    parent_prompt_name TEXT,
    status TEXT DEFAULT 'draft' CHECK(status IN ('draft', 'testing', 'ready')),
    test_results TEXT,  -- JSON array of test result objects
    metadata TEXT,  -- JSON for extensibility
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id) REFERENCES users(username) ON DELETE CASCADE,
    FOREIGN KEY (workshop_chat_id) REFERENCES auspex_chats(id) ON DELETE SET NULL,
    FOREIGN KEY (parent_prompt_name) REFERENCES auspex_prompts(name) ON DELETE SET NULL
);

CREATE INDEX idx_prompt_drafts_user_id ON auspex_prompt_drafts(user_id);
CREATE INDEX idx_prompt_drafts_status ON auspex_prompt_drafts(status);
CREATE INDEX idx_prompt_drafts_parent ON auspex_prompt_drafts(parent_prompt_name);
```

**Field Descriptions:**
- `id`: Auto-incrementing primary key
- `user_id`: Owner of the draft (FK to users.username)
- `draft_name`: Working title for the draft (nullable until commit)
- `draft_content`: The actual prompt text being developed
- `draft_description`: Optional notes about the prompt's purpose
- `workshop_chat_id`: Links to the conversational design session
- `parent_prompt_name`: If cloned from existing prompt, reference here
- `status`: Workflow state (draft → testing → ready)
- `test_results`: JSON array storing test query results
- `metadata`: JSON for future extensibility (tags, categories, etc.)
- `created_at`, `updated_at`: Timestamps

**Test Results JSON Structure:**
```json
[
  {
    "test_id": "uuid-string",
    "query": "Sample query text",
    "topic": "AI Adoption",
    "response_preview": "First 500 chars of response...",
    "full_response_stored": false,
    "response_length": 2500,
    "tools_used": ["enhanced_database_search"],
    "article_count": 45,
    "execution_time_ms": 3200,
    "timestamp": "2025-01-15T10:30:00Z",
    "user_rating": 4,
    "notes": "Good but needs more emphasis on timelines"
  }
]
```

### 1.2 Migration Script

**File:** `alembic/versions/YYYYMMDD_add_prompt_workshop.py`

```python
"""Add prompt workshop tables

Revision ID: <generated>
Revises: d8d9cdcec340
Create Date: 2025-01-15
"""
from alembic import op
import sqlalchemy as sa

def upgrade():
    op.create_table(
        'auspex_prompt_drafts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Text(), nullable=False),
        sa.Column('draft_name', sa.Text(), nullable=True),
        sa.Column('draft_content', sa.Text(), nullable=False),
        sa.Column('draft_description', sa.Text(), nullable=True),
        sa.Column('workshop_chat_id', sa.Integer(), nullable=True),
        sa.Column('parent_prompt_name', sa.Text(), nullable=True),
        sa.Column('status', sa.Text(), nullable=True),
        sa.Column('test_results', sa.Text(), nullable=True),
        sa.Column('metadata', sa.Text(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('updated_at', sa.TIMESTAMP(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.username'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['workshop_chat_id'], ['auspex_chats.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['parent_prompt_name'], ['auspex_prompts.name'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint("status IN ('draft', 'testing', 'ready')", name='valid_status')
    )

    op.create_index('idx_prompt_drafts_user_id', 'auspex_prompt_drafts', ['user_id'])
    op.create_index('idx_prompt_drafts_status', 'auspex_prompt_drafts', ['status'])
    op.create_index('idx_prompt_drafts_parent', 'auspex_prompt_drafts', ['parent_prompt_name'])

def downgrade():
    op.drop_index('idx_prompt_drafts_parent', table_name='auspex_prompt_drafts')
    op.drop_index('idx_prompt_drafts_status', table_name='auspex_prompt_drafts')
    op.drop_index('idx_prompt_drafts_user_id', table_name='auspex_prompt_drafts')
    op.drop_table('auspex_prompt_drafts')
```

---

## 2. Backend API Specifications

### 2.1 Request/Response Models

**File:** `app/routes/auspex_routes.py` (add these models)

```python
from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime

# ============================================================================
# WORKSHOP REQUEST/RESPONSE MODELS
# ============================================================================

class PromptWorkshopStartRequest(BaseModel):
    """Request to start a new prompt workshop session."""
    starting_prompt: str | None = Field(
        None,
        description="Optional initial prompt text to start with"
    )
    parent_prompt_name: str | None = Field(
        None,
        description="Name of existing prompt to clone and modify"
    )
    draft_name: str | None = Field(
        None,
        min_length=3,
        max_length=100,
        description="Working name for this draft"
    )
    requirements: str | None = Field(
        None,
        description="Initial requirements/goals for the prompt"
    )

class PromptWorkshopStartResponse(BaseModel):
    """Response when workshop session is created."""
    draft_id: int
    chat_id: int
    draft_name: str | None
    status: str
    initial_message: str  # First message from workshop assistant
    created_at: str

class PromptDraftUpdateRequest(BaseModel):
    """Request to update draft content."""
    draft_content: str = Field(..., min_length=50)
    draft_name: str | None = Field(None, max_length=100)
    draft_description: str | None = Field(None, max_length=500)
    status: str | None = Field(None, pattern="^(draft|testing|ready)$")

class TestQueryRequest(BaseModel):
    """Request to test a draft prompt."""
    test_query: str = Field(..., min_length=10, max_length=1000)
    topic: str = Field(..., min_length=1)
    limit: int = Field(50, ge=5, le=200)
    model: str | None = Field(None)
    store_full_response: bool = Field(
        False,
        description="Store complete response (uses more storage)"
    )
    user_rating: int | None = Field(None, ge=1, le=5)
    notes: str | None = Field(None, max_length=500)

class TestResultResponse(BaseModel):
    """Response from testing a draft prompt."""
    test_id: str
    query: str
    topic: str
    response_preview: str  # First 500 chars
    response_length: int
    tools_used: List[str]
    article_count: int
    execution_time_ms: int
    timestamp: str
    user_rating: int | None
    notes: str | None

class CommitDraftRequest(BaseModel):
    """Request to commit draft to permanent prompt."""
    name: str = Field(..., min_length=3, max_length=50, pattern="^[a-z0-9_]+$")
    title: str = Field(..., min_length=5, max_length=100)
    description: str | None = Field(None, max_length=500)

    @validator('name')
    def validate_name_format(cls, v):
        """Ensure name is lowercase with underscores only."""
        if not v.islower():
            raise ValueError('Name must be lowercase')
        if ' ' in v:
            raise ValueError('Use underscores instead of spaces')
        return v

class PromptDraftResponse(BaseModel):
    """Response model for draft details."""
    id: int
    user_id: str
    draft_name: str | None
    draft_content: str
    draft_description: str | None
    workshop_chat_id: int | None
    parent_prompt_name: str | None
    status: str
    test_count: int
    created_at: str
    updated_at: str

class PromptDraftListResponse(BaseModel):
    """Response for listing drafts."""
    drafts: List[PromptDraftResponse]
    total: int
```

### 2.2 API Endpoints

**File:** `app/routes/auspex_routes.py` (add these routes)

```python
# ============================================================================
# PROMPT WORKSHOP ENDPOINTS
# ============================================================================

@router.post("/prompts/workshop/start", status_code=status.HTTP_201_CREATED)
async def start_prompt_workshop(
    req: PromptWorkshopStartRequest,
    session=Depends(verify_session)
) -> PromptWorkshopStartResponse:
    """
    Start a new prompt engineering workshop session.

    Creates:
    - A special chat session for conversational prompt design
    - A draft record to track the prompt being developed
    - Initial workshop assistant message

    Workflow:
    1. Create draft record
    2. Create workshop chat session
    3. Initialize with workshop meta-prompt
    4. Send initial message based on requirements
    5. Return draft_id and chat_id for frontend
    """
    logger.info(f"Starting prompt workshop for user: {session.get('user')}")

    auspex = get_auspex_service()
    user_id = session.get('user')

    try:
        # Create workshop session
        result = await auspex.create_prompt_workshop(
            user_id=user_id,
            starting_prompt=req.starting_prompt,
            parent_prompt_name=req.parent_prompt_name,
            draft_name=req.draft_name,
            requirements=req.requirements
        )

        return PromptWorkshopStartResponse(
            draft_id=result['draft_id'],
            chat_id=result['chat_id'],
            draft_name=result['draft_name'],
            status=result['status'],
            initial_message=result['initial_message'],
            created_at=result['created_at']
        )

    except Exception as e:
        logger.error(f"Error starting workshop: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start workshop: {str(e)}"
        )


@router.get("/prompts/workshop/drafts", status_code=status.HTTP_200_OK)
async def list_prompt_drafts(
    status_filter: str | None = None,
    session=Depends(verify_session)
) -> PromptDraftListResponse:
    """
    List user's prompt drafts.

    Query params:
    - status_filter: Optional filter by status (draft|testing|ready)
    """
    auspex = get_auspex_service()
    user_id = session.get('user')

    drafts = auspex.list_prompt_drafts(
        user_id=user_id,
        status_filter=status_filter
    )

    return PromptDraftListResponse(
        drafts=drafts,
        total=len(drafts)
    )


@router.get("/prompts/workshop/drafts/{draft_id}", status_code=status.HTTP_200_OK)
async def get_prompt_draft(
    draft_id: int,
    session=Depends(verify_session)
) -> PromptDraftResponse:
    """Get detailed information about a specific draft."""
    auspex = get_auspex_service()
    user_id = session.get('user')

    draft = auspex.get_prompt_draft(draft_id, user_id)

    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    return PromptDraftResponse(**draft)


@router.put("/prompts/workshop/drafts/{draft_id}", status_code=status.HTTP_200_OK)
async def update_prompt_draft(
    draft_id: int,
    req: PromptDraftUpdateRequest,
    session=Depends(verify_session)
):
    """
    Update draft content, name, description, or status.

    Used when:
    - User manually edits prompt text
    - Conversation produces new draft version
    - Status transitions (draft → testing → ready)
    """
    auspex = get_auspex_service()
    user_id = session.get('user')

    success = auspex.update_prompt_draft(
        draft_id=draft_id,
        user_id=user_id,
        draft_content=req.draft_content,
        draft_name=req.draft_name,
        draft_description=req.draft_description,
        status=req.status
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Draft not found or access denied"
        )

    return {"message": "Draft updated successfully"}


@router.post("/prompts/workshop/drafts/{draft_id}/test", status_code=status.HTTP_200_OK)
async def test_draft_prompt(
    draft_id: int,
    req: TestQueryRequest,
    session=Depends(verify_session)
) -> TestResultResponse:
    """
    Test a draft prompt with a sample query.

    Process:
    1. Retrieve draft content
    2. Create temporary chat session
    3. Apply draft as custom_prompt
    4. Execute test query
    5. Capture response and metrics
    6. Store test result in draft.test_results
    7. Clean up temporary chat
    8. Return response preview and metrics
    """
    logger.info(f"Testing draft {draft_id} with query: {req.test_query[:50]}...")

    auspex = get_auspex_service()
    user_id = session.get('user')

    try:
        test_result = await auspex.test_draft_prompt(
            draft_id=draft_id,
            user_id=user_id,
            test_query=req.test_query,
            topic=req.topic,
            limit=req.limit,
            model=req.model,
            store_full_response=req.store_full_response,
            user_rating=req.user_rating,
            notes=req.notes
        )

        return TestResultResponse(**test_result)

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error testing draft: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Test failed: {str(e)}"
        )


@router.get("/prompts/workshop/drafts/{draft_id}/tests", status_code=status.HTTP_200_OK)
async def get_draft_test_results(
    draft_id: int,
    session=Depends(verify_session)
):
    """Retrieve all test results for a draft."""
    auspex = get_auspex_service()
    user_id = session.get('user')

    test_results = auspex.get_draft_test_results(draft_id, user_id)

    if test_results is None:
        raise HTTPException(status_code=404, detail="Draft not found")

    return {
        "draft_id": draft_id,
        "test_results": test_results,
        "total_tests": len(test_results)
    }


@router.post("/prompts/workshop/drafts/{draft_id}/commit", status_code=status.HTTP_201_CREATED)
async def commit_draft_to_prompt(
    draft_id: int,
    req: CommitDraftRequest,
    session=Depends(verify_session)
):
    """
    Commit a draft to the permanent prompts library.

    Validations:
    - Draft exists and user owns it
    - Prompt name not already taken
    - Draft content meets minimum quality (length, structure)

    Process:
    1. Validate draft ownership
    2. Check name availability
    3. Create record in auspex_prompts
    4. Optionally delete draft or mark as committed
    5. Return new prompt info
    """
    logger.info(f"Committing draft {draft_id} as prompt '{req.name}'")

    auspex = get_auspex_service()
    user_id = session.get('user')

    try:
        prompt_id = await auspex.commit_draft_to_prompt(
            draft_id=draft_id,
            user_id=user_id,
            name=req.name,
            title=req.title,
            description=req.description
        )

        return {
            "prompt_id": prompt_id,
            "name": req.name,
            "message": f"Draft committed as prompt '{req.name}'"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error committing draft: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Commit failed: {str(e)}"
        )


@router.delete("/prompts/workshop/drafts/{draft_id}", status_code=status.HTTP_200_OK)
async def delete_prompt_draft(
    draft_id: int,
    session=Depends(verify_session)
):
    """Delete a draft (with associated workshop chat)."""
    auspex = get_auspex_service()
    user_id = session.get('user')

    success = auspex.delete_prompt_draft(draft_id, user_id)

    if not success:
        raise HTTPException(
            status_code=404,
            detail="Draft not found or access denied"
        )

    return {"message": "Draft deleted successfully"}


@router.post("/prompts/{prompt_name}/clone", status_code=status.HTTP_201_CREATED)
async def clone_existing_prompt(
    prompt_name: str,
    clone_name: str | None = None,
    session=Depends(verify_session)
):
    """
    Clone an existing prompt into a new draft for modification.

    Process:
    1. Load existing prompt
    2. Create new draft with prompt content
    3. Set parent_prompt_name for reference
    4. Create workshop chat
    5. Return draft_id for editing
    """
    auspex = get_auspex_service()
    user_id = session.get('user')

    try:
        result = await auspex.clone_prompt_to_draft(
            prompt_name=prompt_name,
            user_id=user_id,
            clone_name=clone_name
        )

        return {
            "draft_id": result['draft_id'],
            "chat_id": result['chat_id'],
            "parent_prompt": prompt_name,
            "message": f"Cloned '{prompt_name}' to editable draft"
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error cloning prompt: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Clone failed: {str(e)}"
        )
```

---

## 3. Service Layer Specifications

**File:** `app/services/auspex_service.py` (add these methods to AuspexService class)

```python
import json
import uuid
from datetime import datetime
from typing import Dict, List, Optional

class AuspexService:
    # ... existing methods ...

    # ========================================================================
    # PROMPT WORKSHOP METHODS
    # ========================================================================

    async def create_prompt_workshop(
        self,
        user_id: str,
        starting_prompt: Optional[str] = None,
        parent_prompt_name: Optional[str] = None,
        draft_name: Optional[str] = None,
        requirements: Optional[str] = None
    ) -> Dict:
        """
        Create a new prompt engineering workshop session.

        Returns:
            dict: {
                'draft_id': int,
                'chat_id': int,
                'draft_name': str,
                'status': str,
                'initial_message': str,
                'created_at': str
            }
        """
        try:
            # If cloning, load parent prompt
            if parent_prompt_name:
                parent = self.db.get_auspex_prompt(parent_prompt_name)
                if not parent:
                    raise ValueError(f"Parent prompt '{parent_prompt_name}' not found")
                starting_prompt = parent['content']
                if not draft_name:
                    draft_name = f"Modified {parent['title']}"

            # Create workshop chat session
            chat_id = await self.create_chat_session(
                topic="__prompt_workshop__",  # Special topic flag
                user_id=user_id,
                title=draft_name or "Prompt Engineering Workshop"
            )

            # Create draft record
            draft_id = self.db.create_prompt_draft(
                user_id=user_id,
                draft_name=draft_name,
                draft_content=starting_prompt or "",
                workshop_chat_id=chat_id,
                parent_prompt_name=parent_prompt_name,
                status='draft'
            )

            # Initialize workshop with meta-prompt
            workshop_meta_prompt = self._get_workshop_meta_prompt()

            # Add system message to chat
            self.db.add_auspex_message(
                chat_id=chat_id,
                role='system',
                content=workshop_meta_prompt
            )

            # Generate initial assistant message
            if requirements:
                initial_user_msg = f"I want to create a custom Auspex prompt with these requirements: {requirements}"
            elif parent_prompt_name:
                initial_user_msg = f"I want to modify the '{parent_prompt_name}' prompt for my specific needs."
            else:
                initial_user_msg = "I want to create a custom Auspex prompt. Can you help me design it?"

            # Add user's initial "message" (auto-generated)
            self.db.add_auspex_message(
                chat_id=chat_id,
                role='user',
                content=initial_user_msg
            )

            # Generate AI response
            messages = [
                {"role": "system", "content": workshop_meta_prompt},
                {"role": "user", "content": initial_user_msg}
            ]

            ai_model = get_ai_model(DEFAULT_MODEL)
            initial_response = ai_model.generate_response(messages)

            # Store assistant response
            self.db.add_auspex_message(
                chat_id=chat_id,
                role='assistant',
                content=initial_response
            )

            return {
                'draft_id': draft_id,
                'chat_id': chat_id,
                'draft_name': draft_name,
                'status': 'draft',
                'initial_message': initial_response,
                'created_at': datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Error creating workshop: {e}")
            raise

    def _get_workshop_meta_prompt(self) -> str:
        """Return the meta-prompt for workshop assistant."""
        return """You are a prompt engineering assistant helping to design custom system prompts for Auspex, an AI research assistant.

**Your Role:**
Help the user create an effective, well-structured system prompt tailored to their specific research needs.

**Conversation Flow:**
1. **Understand Requirements** - Ask clarifying questions:
   - What type of analysis or research will this prompt support?
   - What's the target audience? (executives, researchers, technical experts)
   - What tone and style are preferred? (formal, conversational, technical)
   - Are there specific output formats needed? (tables, bullet points, narratives)
   - Which Auspex tools should be emphasized or constrained?
   - Any special instructions or constraints?

2. **Draft Prompt** - Based on their answers, generate a draft prompt that includes:
   - Clear role definition for Auspex
   - Specific research focus areas
   - Output style and formatting guidelines
   - Tool usage strategies
   - Quality standards and requirements
   - Citation and sourcing rules

3. **Iterate** - Refine based on feedback:
   - Ask if the draft captures their needs
   - Suggest improvements
   - Adjust based on test results

**When Generating Draft Prompts:**
- Use clear, structured markdown
- Include specific instructions, not vague guidance
- Reference the existing DEFAULT_AUSPEX_PROMPT as a template
- Maintain core principles: inline citations, evidence-based analysis, intellectual honesty
- Customize the research focus, tone, and output format

**Output Format:**
When you generate or update a draft prompt, present it in a code block:

```
[Your draft prompt text here]
```

Then ask for feedback or suggest next steps (testing, refinement).

**Remember:** You're designing a SYSTEM PROMPT that will guide Auspex's behavior. Be specific and actionable."""

    def list_prompt_drafts(
        self,
        user_id: str,
        status_filter: Optional[str] = None
    ) -> List[Dict]:
        """
        List user's prompt drafts with optional status filter.

        Returns list of draft summaries (without full content).
        """
        try:
            drafts = self.db.list_prompt_drafts(user_id, status_filter)

            # Add test count to each draft
            for draft in drafts:
                test_results = json.loads(draft.get('test_results', '[]'))
                draft['test_count'] = len(test_results)

            return drafts

        except Exception as e:
            logger.error(f"Error listing drafts: {e}")
            return []

    def get_prompt_draft(self, draft_id: int, user_id: str) -> Optional[Dict]:
        """Get detailed draft information including full content."""
        try:
            draft = self.db.get_prompt_draft(draft_id)

            if not draft or draft['user_id'] != user_id:
                return None

            # Parse test results
            test_results = json.loads(draft.get('test_results', '[]'))
            draft['test_count'] = len(test_results)

            return draft

        except Exception as e:
            logger.error(f"Error getting draft: {e}")
            return None

    def update_prompt_draft(
        self,
        draft_id: int,
        user_id: str,
        draft_content: Optional[str] = None,
        draft_name: Optional[str] = None,
        draft_description: Optional[str] = None,
        status: Optional[str] = None
    ) -> bool:
        """Update draft fields."""
        try:
            return self.db.update_prompt_draft(
                draft_id=draft_id,
                user_id=user_id,
                draft_content=draft_content,
                draft_name=draft_name,
                draft_description=draft_description,
                status=status
            )
        except Exception as e:
            logger.error(f"Error updating draft: {e}")
            return False

    async def test_draft_prompt(
        self,
        draft_id: int,
        user_id: str,
        test_query: str,
        topic: str,
        limit: int = 50,
        model: Optional[str] = None,
        store_full_response: bool = False,
        user_rating: Optional[int] = None,
        notes: Optional[str] = None
    ) -> Dict:
        """
        Test a draft prompt with a sample query.

        Returns test result dictionary with response preview and metrics.
        """
        try:
            # Get draft
            draft = self.db.get_prompt_draft(draft_id)
            if not draft or draft['user_id'] != user_id:
                raise ValueError("Draft not found or access denied")

            # Create temporary test chat
            test_chat_id = await self.create_chat_session(
                topic=topic,
                user_id=user_id,
                title=f"Test: {draft['draft_name'] or 'Untitled'}"
            )

            start_time = datetime.now()

            # Execute query with draft prompt
            response_chunks = []
            tools_used = set()
            article_count = 0

            async for chunk in self.chat_with_tools(
                chat_id=test_chat_id,
                message=test_query,
                model=model or DEFAULT_MODEL,
                limit=limit,
                custom_prompt=draft['draft_content']
            ):
                response_chunks.append(chunk)

                # Track tools used (basic detection)
                if 'enhanced_database_search' in chunk:
                    tools_used.add('enhanced_database_search')
                if 'articles analyzed' in chunk.lower():
                    # Try to extract article count
                    import re
                    match = re.search(r'(\d+)\s+articles?\s+analyzed', chunk, re.IGNORECASE)
                    if match:
                        article_count = max(article_count, int(match.group(1)))

            end_time = datetime.now()
            execution_time_ms = int((end_time - start_time).total_seconds() * 1000)

            full_response = "".join(response_chunks)

            # Create test result
            test_id = str(uuid.uuid4())
            test_result = {
                "test_id": test_id,
                "query": test_query,
                "topic": topic,
                "response_preview": full_response[:500],
                "response_length": len(full_response),
                "tools_used": list(tools_used),
                "article_count": article_count,
                "execution_time_ms": execution_time_ms,
                "timestamp": datetime.now().isoformat(),
                "user_rating": user_rating,
                "notes": notes
            }

            # Optionally store full response
            if store_full_response:
                test_result["full_response"] = full_response

            # Append to draft's test_results
            self.db.append_draft_test_result(draft_id, test_result)

            # Update draft status to 'testing' if still in 'draft'
            if draft['status'] == 'draft':
                self.db.update_prompt_draft(
                    draft_id=draft_id,
                    user_id=user_id,
                    status='testing'
                )

            # Clean up test chat
            self.delete_chat_session(test_chat_id)

            return test_result

        except Exception as e:
            logger.error(f"Error testing draft: {e}")
            raise

    def get_draft_test_results(
        self,
        draft_id: int,
        user_id: str
    ) -> Optional[List[Dict]]:
        """Get all test results for a draft."""
        try:
            draft = self.db.get_prompt_draft(draft_id)

            if not draft or draft['user_id'] != user_id:
                return None

            test_results = json.loads(draft.get('test_results', '[]'))
            return test_results

        except Exception as e:
            logger.error(f"Error getting test results: {e}")
            return None

    async def commit_draft_to_prompt(
        self,
        draft_id: int,
        user_id: str,
        name: str,
        title: str,
        description: Optional[str] = None
    ) -> int:
        """
        Commit a draft to permanent prompts library.

        Returns prompt_id of created prompt.
        """
        try:
            # Get draft
            draft = self.db.get_prompt_draft(draft_id)
            if not draft or draft['user_id'] != user_id:
                raise ValueError("Draft not found or access denied")

            # Validate name availability
            existing = self.db.get_auspex_prompt(name)
            if existing:
                raise ValueError(f"Prompt name '{name}' already exists")

            # Validate content length
            if len(draft['draft_content']) < 100:
                raise ValueError("Prompt content too short (minimum 100 characters)")

            # Create permanent prompt
            prompt_id = self.db.create_auspex_prompt(
                name=name,
                title=title,
                content=draft['draft_content'],
                description=description or draft.get('draft_description'),
                is_default=False,
                user_created=user_id
            )

            # Update draft status
            self.db.update_prompt_draft(
                draft_id=draft_id,
                user_id=user_id,
                status='committed'
            )

            logger.info(f"Draft {draft_id} committed as prompt '{name}' (ID: {prompt_id})")

            return prompt_id

        except Exception as e:
            logger.error(f"Error committing draft: {e}")
            raise

    def delete_prompt_draft(self, draft_id: int, user_id: str) -> bool:
        """Delete a draft and its associated workshop chat."""
        try:
            draft = self.db.get_prompt_draft(draft_id)

            if not draft or draft['user_id'] != user_id:
                return False

            # Delete associated chat if exists
            if draft.get('workshop_chat_id'):
                self.delete_chat_session(draft['workshop_chat_id'])

            # Delete draft
            return self.db.delete_prompt_draft(draft_id)

        except Exception as e:
            logger.error(f"Error deleting draft: {e}")
            return False

    async def clone_prompt_to_draft(
        self,
        prompt_name: str,
        user_id: str,
        clone_name: Optional[str] = None
    ) -> Dict:
        """
        Clone an existing prompt into a draft for modification.

        Returns dict with draft_id and chat_id.
        """
        try:
            # Get original prompt
            prompt = self.db.get_auspex_prompt(prompt_name)
            if not prompt:
                raise ValueError(f"Prompt '{prompt_name}' not found")

            # Create workshop session with cloned content
            result = await self.create_prompt_workshop(
                user_id=user_id,
                starting_prompt=prompt['content'],
                parent_prompt_name=prompt_name,
                draft_name=clone_name or f"Modified {prompt['title']}",
                requirements=f"Modify the existing '{prompt['title']}' prompt"
            )

            return result

        except Exception as e:
            logger.error(f"Error cloning prompt: {e}")
            raise
```

---

## 4. Database Facade Methods

**File:** `app/database_query_facade.py` (add these methods)

```python
class DatabaseQueryFacade:
    # ... existing methods ...

    # ========================================================================
    # PROMPT DRAFT METHODS
    # ========================================================================

    def create_prompt_draft(
        self,
        user_id: str,
        draft_content: str,
        draft_name: str = None,
        draft_description: str = None,
        workshop_chat_id: int = None,
        parent_prompt_name: str = None,
        status: str = 'draft'
    ) -> int:
        """Create a new prompt draft. Returns draft_id."""
        query = """
            INSERT INTO auspex_prompt_drafts
            (user_id, draft_name, draft_content, draft_description,
             workshop_chat_id, parent_prompt_name, status, test_results,
             created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, '[]', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """
        cursor = self.db.conn.cursor()
        cursor.execute(query, (
            user_id, draft_name, draft_content, draft_description,
            workshop_chat_id, parent_prompt_name, status
        ))
        self.db.conn.commit()
        return cursor.lastrowid

    def get_prompt_draft(self, draft_id: int) -> Optional[Dict]:
        """Get draft by ID."""
        query = """
            SELECT id, user_id, draft_name, draft_content, draft_description,
                   workshop_chat_id, parent_prompt_name, status, test_results,
                   metadata, created_at, updated_at
            FROM auspex_prompt_drafts
            WHERE id = ?
        """
        cursor = self.db.conn.cursor()
        cursor.execute(query, (draft_id,))
        row = cursor.fetchone()

        if not row:
            return None

        return dict(row)

    def list_prompt_drafts(
        self,
        user_id: str,
        status_filter: str = None
    ) -> List[Dict]:
        """List user's drafts (without full content)."""
        query = """
            SELECT id, user_id, draft_name, draft_description,
                   workshop_chat_id, parent_prompt_name, status,
                   created_at, updated_at,
                   LENGTH(draft_content) as content_length
            FROM auspex_prompt_drafts
            WHERE user_id = ?
        """
        params = [user_id]

        if status_filter:
            query += " AND status = ?"
            params.append(status_filter)

        query += " ORDER BY updated_at DESC"

        cursor = self.db.conn.cursor()
        cursor.execute(query, params)

        return [dict(row) for row in cursor.fetchall()]

    def update_prompt_draft(
        self,
        draft_id: int,
        user_id: str,
        draft_content: str = None,
        draft_name: str = None,
        draft_description: str = None,
        status: str = None
    ) -> bool:
        """Update draft fields. Returns True if successful."""
        # Build dynamic update query
        updates = []
        params = []

        if draft_content is not None:
            updates.append("draft_content = ?")
            params.append(draft_content)

        if draft_name is not None:
            updates.append("draft_name = ?")
            params.append(draft_name)

        if draft_description is not None:
            updates.append("draft_description = ?")
            params.append(draft_description)

        if status is not None:
            updates.append("status = ?")
            params.append(status)

        if not updates:
            return False

        updates.append("updated_at = CURRENT_TIMESTAMP")

        query = f"""
            UPDATE auspex_prompt_drafts
            SET {', '.join(updates)}
            WHERE id = ? AND user_id = ?
        """
        params.extend([draft_id, user_id])

        cursor = self.db.conn.cursor()
        cursor.execute(query, params)
        self.db.conn.commit()

        return cursor.rowcount > 0

    def append_draft_test_result(self, draft_id: int, test_result: Dict) -> bool:
        """Append a test result to draft's test_results JSON array."""
        # Get current test_results
        draft = self.get_prompt_draft(draft_id)
        if not draft:
            return False

        test_results = json.loads(draft.get('test_results', '[]'))
        test_results.append(test_result)

        query = """
            UPDATE auspex_prompt_drafts
            SET test_results = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """
        cursor = self.db.conn.cursor()
        cursor.execute(query, (json.dumps(test_results), draft_id))
        self.db.conn.commit()

        return cursor.rowcount > 0

    def delete_prompt_draft(self, draft_id: int) -> bool:
        """Delete a draft."""
        query = "DELETE FROM auspex_prompt_drafts WHERE id = ?"
        cursor = self.db.conn.cursor()
        cursor.execute(query, (draft_id,))
        self.db.conn.commit()
        return cursor.rowcount > 0
```

---

## 5. Frontend Specifications

### 5.1 UI Component Structure

**File:** `templates/prompt-workshop.html`

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Prompt Workshop | AuNoo</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="/static/css/auspex-chat.css">
    <link rel="stylesheet" href="/static/css/prompt-workshop.css">
</head>
<body>
    <!-- Main Container -->
    <div class="container-fluid h-100">
        <div class="row h-100">

            <!-- Left Panel: Conversation -->
            <div class="col-md-5 border-end workshop-chat-panel">
                <div class="workshop-header p-3 border-bottom">
                    <h5><i class="fas fa-brain"></i> Prompt Design Assistant</h5>
                    <small class="text-muted">Collaborative prompt engineering</small>
                </div>

                <!-- Chat Messages -->
                <div id="workshop-messages" class="workshop-messages p-3">
                    <!-- Messages rendered here -->
                </div>

                <!-- Chat Input -->
                <div class="workshop-input p-3 border-top">
                    <div class="input-group">
                        <textarea
                            id="workshop-user-input"
                            class="form-control"
                            rows="3"
                            placeholder="Describe your requirements or ask for changes..."
                        ></textarea>
                    </div>
                    <div class="mt-2 d-flex justify-content-between">
                        <button id="send-workshop-message" class="btn btn-primary">
                            <i class="fas fa-paper-plane"></i> Send
                        </button>
                        <button id="extract-prompt" class="btn btn-outline-secondary">
                            <i class="fas fa-code"></i> Extract Draft
                        </button>
                    </div>
                </div>
            </div>

            <!-- Right Panel: Draft Editor & Testing -->
            <div class="col-md-7 workshop-editor-panel">

                <!-- Draft Metadata -->
                <div class="workshop-metadata p-3 border-bottom">
                    <div class="row">
                        <div class="col-md-8">
                            <input
                                type="text"
                                id="draft-name"
                                class="form-control form-control-lg"
                                placeholder="Draft Name"
                            />
                        </div>
                        <div class="col-md-4">
                            <select id="draft-status" class="form-select">
                                <option value="draft">Draft</option>
                                <option value="testing">Testing</option>
                                <option value="ready">Ready</option>
                            </select>
                        </div>
                    </div>
                    <div class="mt-2">
                        <input
                            type="text"
                            id="draft-description"
                            class="form-control"
                            placeholder="Description (optional)"
                        />
                    </div>
                </div>

                <!-- Tabs: Draft | Test | Results -->
                <ul class="nav nav-tabs px-3 pt-3" id="workshop-tabs">
                    <li class="nav-item">
                        <button class="nav-link active" data-bs-toggle="tab" data-bs-target="#tab-draft">
                            <i class="fas fa-edit"></i> Draft
                        </button>
                    </li>
                    <li class="nav-item">
                        <button class="nav-link" data-bs-toggle="tab" data-bs-target="#tab-test">
                            <i class="fas fa-flask"></i> Test
                        </button>
                    </li>
                    <li class="nav-item">
                        <button class="nav-link" data-bs-toggle="tab" data-bs-target="#tab-history">
                            <i class="fas fa-history"></i> Test History (<span id="test-count">0</span>)
                        </button>
                    </li>
                </ul>

                <div class="tab-content p-3">

                    <!-- Draft Tab -->
                    <div class="tab-pane fade show active" id="tab-draft">
                        <div class="draft-editor-container">
                            <textarea
                                id="draft-content"
                                class="form-control font-monospace"
                                rows="20"
                                placeholder="Your custom system prompt will appear here..."
                            ></textarea>
                            <div class="mt-3 d-flex justify-content-between">
                                <div>
                                    <button id="save-draft" class="btn btn-success">
                                        <i class="fas fa-save"></i> Save Draft
                                    </button>
                                    <button id="reset-draft" class="btn btn-outline-warning">
                                        <i class="fas fa-undo"></i> Reset
                                    </button>
                                </div>
                                <div>
                                    <span id="char-count" class="text-muted">0 characters</span>
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- Test Tab -->
                    <div class="tab-pane fade" id="tab-test">
                        <div class="test-query-section">
                            <h6>Test Configuration</h6>
                            <div class="row g-3 mb-3">
                                <div class="col-md-8">
                                    <label class="form-label">Topic</label>
                                    <select id="test-topic" class="form-select">
                                        <!-- Populated dynamically -->
                                    </select>
                                </div>
                                <div class="col-md-4">
                                    <label class="form-label">Model</label>
                                    <select id="test-model" class="form-select">
                                        <option value="gpt-4.1-mini">GPT-4.1 Mini</option>
                                        <option value="gpt-4.1">GPT-4.1</option>
                                        <option value="gpt-4o-mini">GPT-4o Mini</option>
                                    </select>
                                </div>
                            </div>

                            <label class="form-label">Test Query</label>
                            <textarea
                                id="test-query"
                                class="form-control mb-3"
                                rows="3"
                                placeholder="Enter a sample query to test your prompt..."
                            ></textarea>

                            <button id="run-test" class="btn btn-primary">
                                <i class="fas fa-play"></i> Run Test
                            </button>

                            <div id="test-output" class="test-output mt-3" style="display:none;">
                                <h6>Test Results</h6>
                                <div id="test-metrics" class="test-metrics mb-2">
                                    <!-- Metrics rendered here -->
                                </div>
                                <div id="test-response" class="test-response p-3 border rounded">
                                    <!-- Response rendered here -->
                                </div>
                                <div class="mt-3">
                                    <label class="form-label">Rate this result:</label>
                                    <div class="rating-stars">
                                        <i class="far fa-star" data-rating="1"></i>
                                        <i class="far fa-star" data-rating="2"></i>
                                        <i class="far fa-star" data-rating="3"></i>
                                        <i class="far fa-star" data-rating="4"></i>
                                        <i class="far fa-star" data-rating="5"></i>
                                    </div>
                                    <textarea
                                        id="test-notes"
                                        class="form-control mt-2"
                                        rows="2"
                                        placeholder="Notes about this test (optional)"
                                    ></textarea>
                                    <button id="save-test-feedback" class="btn btn-sm btn-secondary mt-2">
                                        Save Feedback
                                    </button>
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- Test History Tab -->
                    <div class="tab-pane fade" id="tab-history">
                        <div id="test-history-list">
                            <!-- Test history rendered here -->
                        </div>
                    </div>

                </div>

                <!-- Footer Actions -->
                <div class="workshop-footer p-3 border-top bg-light">
                    <div class="d-flex justify-content-between">
                        <div>
                            <button id="close-workshop" class="btn btn-outline-secondary">
                                <i class="fas fa-times"></i> Close
                            </button>
                        </div>
                        <div>
                            <button id="commit-prompt" class="btn btn-success btn-lg" disabled>
                                <i class="fas fa-check-circle"></i> Commit as Prompt
                            </button>
                        </div>
                    </div>
                </div>
            </div>

        </div>
    </div>

    <!-- Commit Modal -->
    <div class="modal fade" id="commitModal" tabindex="-1">
        <div class="modal-dialog">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title">Commit Prompt</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body">
                    <div class="mb-3">
                        <label class="form-label">Prompt Name (unique identifier)</label>
                        <input type="text" id="commit-name" class="form-control"
                               pattern="^[a-z0-9_]+$"
                               placeholder="e.g., financial_analyst_executive">
                        <small class="form-text text-muted">Lowercase letters, numbers, underscores only</small>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">Display Title</label>
                        <input type="text" id="commit-title" class="form-control"
                               placeholder="e.g., Financial Analyst (Executive Level)">
                    </div>
                    <div class="mb-3">
                        <label class="form-label">Description</label>
                        <textarea id="commit-description" class="form-control" rows="3"
                                  placeholder="Describe what this prompt is for..."></textarea>
                    </div>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
                    <button type="button" id="confirm-commit" class="btn btn-success">
                        <i class="fas fa-check"></i> Commit
                    </button>
                </div>
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script src="/static/js/prompt-workshop.js"></script>
</body>
</html>
```

### 5.2 CSS Styles

**File:** `static/css/prompt-workshop.css`

```css
/* Prompt Workshop Styles */

.workshop-chat-panel,
.workshop-editor-panel {
    height: 100vh;
    display: flex;
    flex-direction: column;
}

.workshop-header {
    flex-shrink: 0;
}

.workshop-messages {
    flex: 1;
    overflow-y: auto;
    background: #f8f9fa;
}

.workshop-message {
    margin-bottom: 1rem;
    padding: 0.75rem;
    border-radius: 0.5rem;
}

.workshop-message.user {
    background: #e3f2fd;
    margin-left: 2rem;
}

.workshop-message.assistant {
    background: #ffffff;
    border: 1px solid #dee2e6;
    margin-right: 2rem;
}

.workshop-message .message-role {
    font-weight: 600;
    font-size: 0.875rem;
    margin-bottom: 0.25rem;
    color: #495057;
}

.workshop-message .message-content {
    white-space: pre-wrap;
}

.workshop-message .message-content code {
    display: block;
    background: #f5f5f5;
    padding: 1rem;
    border-radius: 0.25rem;
    font-family: 'Courier New', monospace;
    overflow-x: auto;
}

.workshop-input {
    flex-shrink: 0;
    background: #ffffff;
}

#workshop-user-input {
    resize: none;
}

/* Draft Editor */
.draft-editor-container {
    height: calc(100vh - 280px);
    display: flex;
    flex-direction: column;
}

#draft-content {
    flex: 1;
    font-family: 'Courier New', monospace;
    font-size: 0.9rem;
    resize: none;
}

#char-count {
    font-size: 0.875rem;
}

/* Test Section */
.test-query-section {
    height: calc(100vh - 280px);
    overflow-y: auto;
}

.test-output {
    max-height: 400px;
    overflow-y: auto;
}

.test-metrics {
    display: flex;
    gap: 1rem;
    flex-wrap: wrap;
}

.test-metric {
    padding: 0.5rem 1rem;
    background: #f8f9fa;
    border-radius: 0.25rem;
    font-size: 0.875rem;
}

.test-metric strong {
    display: block;
    color: #6c757d;
    font-weight: 600;
}

.test-response {
    background: #ffffff;
    max-height: 300px;
    overflow-y: auto;
}

/* Rating Stars */
.rating-stars {
    display: flex;
    gap: 0.5rem;
    font-size: 1.5rem;
}

.rating-stars i {
    cursor: pointer;
    color: #ffc107;
}

.rating-stars i:hover,
.rating-stars i.fas {
    color: #ff9800;
}

/* Test History */
.test-history-item {
    padding: 1rem;
    border: 1px solid #dee2e6;
    border-radius: 0.5rem;
    margin-bottom: 1rem;
    cursor: pointer;
    transition: background 0.2s;
}

.test-history-item:hover {
    background: #f8f9fa;
}

.test-history-header {
    display: flex;
    justify-content: space-between;
    margin-bottom: 0.5rem;
}

.test-history-query {
    font-weight: 600;
    color: #495057;
}

.test-history-timestamp {
    font-size: 0.875rem;
    color: #6c757d;
}

.test-history-metrics {
    display: flex;
    gap: 1rem;
    font-size: 0.875rem;
    color: #6c757d;
}

/* Footer */
.workshop-footer {
    flex-shrink: 0;
}

/* Loading States */
.loading-spinner {
    display: inline-block;
    width: 1rem;
    height: 1rem;
    border: 2px solid #f3f3f3;
    border-top: 2px solid #007bff;
    border-radius: 50%;
    animation: spin 1s linear infinite;
}

@keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
}

/* Responsive */
@media (max-width: 768px) {
    .workshop-chat-panel {
        height: 50vh;
    }

    .workshop-editor-panel {
        height: 50vh;
    }

    .draft-editor-container,
    .test-query-section {
        height: auto;
        min-height: 300px;
    }
}
```

### 5.3 JavaScript Controller

**File:** `static/js/prompt-workshop.js`

```javascript
/**
 * Prompt Workshop Controller
 * Manages conversational prompt engineering workflow
 */

class PromptWorkshop {
    constructor() {
        this.draftId = null;
        this.chatId = null;
        this.currentTestId = null;
        this.autoSaveTimer = null;

        this.initializeFromURL();
        this.bindEvents();
        this.loadTopics();
    }

    initializeFromURL() {
        const params = new URLSearchParams(window.location.search);
        const draftId = params.get('draft_id');

        if (draftId) {
            this.loadDraft(parseInt(draftId));
        } else {
            this.startNewWorkshop();
        }
    }

    async startNewWorkshop() {
        const params = new URLSearchParams(window.location.search);
        const parentPrompt = params.get('clone');

        const response = await fetch('/api/auspex/prompts/workshop/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                parent_prompt_name: parentPrompt || null
            })
        });

        if (!response.ok) {
            alert('Failed to start workshop');
            return;
        }

        const data = await response.json();
        this.draftId = data.draft_id;
        this.chatId = data.chat_id;

        // Update URL without reload
        window.history.pushState({}, '', `?draft_id=${this.draftId}`);

        // Display initial message
        this.addMessage('assistant', data.initial_message);
    }

    async loadDraft(draftId) {
        const response = await fetch(`/api/auspex/prompts/workshop/drafts/${draftId}`);

        if (!response.ok) {
            alert('Draft not found');
            return;
        }

        const draft = await response.json();
        this.draftId = draft.id;
        this.chatId = draft.workshop_chat_id;

        // Populate UI
        document.getElementById('draft-name').value = draft.draft_name || '';
        document.getElementById('draft-description').value = draft.draft_description || '';
        document.getElementById('draft-status').value = draft.status;
        document.getElementById('draft-content').value = draft.draft_content;
        document.getElementById('test-count').textContent = draft.test_count;

        this.updateCharCount();

        // Load chat history
        await this.loadChatHistory();

        // Load test history
        await this.loadTestHistory();
    }

    async loadChatHistory() {
        const response = await fetch(`/api/auspex/chat/sessions/${this.chatId}/messages`);
        const data = await response.json();

        const messagesContainer = document.getElementById('workshop-messages');
        messagesContainer.innerHTML = '';

        data.messages.forEach(msg => {
            if (msg.role !== 'system') {
                this.addMessage(msg.role, msg.content);
            }
        });

        this.scrollMessagesToBottom();
    }

    async loadTestHistory() {
        const response = await fetch(
            `/api/auspex/prompts/workshop/drafts/${this.draftId}/tests`
        );
        const data = await response.json();

        const historyContainer = document.getElementById('test-history-list');
        historyContainer.innerHTML = '';

        if (data.test_results.length === 0) {
            historyContainer.innerHTML = '<p class="text-muted">No tests run yet</p>';
            return;
        }

        data.test_results.forEach(test => {
            const item = this.createTestHistoryItem(test);
            historyContainer.appendChild(item);
        });
    }

    createTestHistoryItem(test) {
        const div = document.createElement('div');
        div.className = 'test-history-item';
        div.onclick = () => this.viewTestResult(test);

        div.innerHTML = `
            <div class="test-history-header">
                <div class="test-history-query">${this.truncate(test.query, 60)}</div>
                <div class="test-history-timestamp">${this.formatTimestamp(test.timestamp)}</div>
            </div>
            <div class="test-history-metrics">
                <span><i class="fas fa-file-alt"></i> ${test.article_count} articles</span>
                <span><i class="fas fa-clock"></i> ${test.execution_time_ms}ms</span>
                ${test.user_rating ? `<span><i class="fas fa-star"></i> ${test.user_rating}/5</span>` : ''}
            </div>
        `;

        return div;
    }

    bindEvents() {
        // Send workshop message
        document.getElementById('send-workshop-message').onclick = () => this.sendMessage();
        document.getElementById('workshop-user-input').onkeydown = (e) => {
            if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
                this.sendMessage();
            }
        };

        // Extract prompt from conversation
        document.getElementById('extract-prompt').onclick = () => this.extractPrompt();

        // Draft editing
        document.getElementById('draft-content').oninput = () => {
            this.updateCharCount();
            this.scheduleAutoSave();
        };

        document.getElementById('draft-name').onchange = () => this.scheduleAutoSave();
        document.getElementById('draft-description').onchange = () => this.scheduleAutoSave();
        document.getElementById('draft-status').onchange = () => this.saveDraft();

        document.getElementById('save-draft').onclick = () => this.saveDraft();
        document.getElementById('reset-draft').onclick = () => this.resetDraft();

        // Testing
        document.getElementById('run-test').onclick = () => this.runTest();
        document.getElementById('save-test-feedback').onclick = () => this.saveTestFeedback();

        // Rating stars
        document.querySelectorAll('.rating-stars i').forEach(star => {
            star.onclick = (e) => this.setRating(parseInt(e.target.dataset.rating));
        });

        // Commit
        document.getElementById('commit-prompt').onclick = () => this.showCommitModal();
        document.getElementById('confirm-commit').onclick = () => this.commitPrompt();

        // Close
        document.getElementById('close-workshop').onclick = () => this.closeWorkshop();
    }

    async sendMessage() {
        const input = document.getElementById('workshop-user-input');
        const message = input.value.trim();

        if (!message) return;

        // Add user message to UI
        this.addMessage('user', message);
        input.value = '';

        // Send to backend
        const response = await fetch('/api/auspex/chat/message', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                chat_id: this.chatId,
                message: message,
                model: 'gpt-4.1-mini',
                limit: 10
            })
        });

        if (!response.ok) {
            this.addMessage('assistant', 'Error: Failed to send message');
            return;
        }

        // Stream response
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let assistantMessage = '';

        const messageDiv = this.addMessage('assistant', '');
        const contentDiv = messageDiv.querySelector('.message-content');

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value);
            const lines = chunk.split('\n\n');

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const data = JSON.parse(line.slice(6));
                    if (data.content) {
                        assistantMessage += data.content;
                        contentDiv.textContent = assistantMessage;
                    }
                    if (data.done) break;
                }
            }
        }

        this.scrollMessagesToBottom();

        // Check if message contains code block (potential prompt)
        if (assistantMessage.includes('```')) {
            document.getElementById('extract-prompt').classList.add('btn-warning');
            document.getElementById('extract-prompt').innerHTML =
                '<i class="fas fa-code"></i> Extract Prompt <span class="badge bg-danger">New</span>';
        }
    }

    extractPrompt() {
        const messages = document.querySelectorAll('.workshop-message.assistant');
        const lastMessage = messages[messages.length - 1];
        const content = lastMessage.querySelector('.message-content').textContent;

        // Extract code block
        const match = content.match(/```([^`]+)```/s);
        if (match) {
            const extractedPrompt = match[1].trim();
            document.getElementById('draft-content').value = extractedPrompt;
            this.updateCharCount();
            this.saveDraft();

            // Switch to draft tab
            const draftTab = document.querySelector('[data-bs-target="#tab-draft"]');
            new bootstrap.Tab(draftTab).show();

            // Reset button
            document.getElementById('extract-prompt').classList.remove('btn-warning');
            document.getElementById('extract-prompt').innerHTML =
                '<i class="fas fa-code"></i> Extract Draft';
        } else {
            alert('No code block found in the last message');
        }
    }

    scheduleAutoSave() {
        clearTimeout(this.autoSaveTimer);
        this.autoSaveTimer = setTimeout(() => this.saveDraft(), 2000);
    }

    async saveDraft() {
        const data = {
            draft_content: document.getElementById('draft-content').value,
            draft_name: document.getElementById('draft-name').value,
            draft_description: document.getElementById('draft-description').value,
            status: document.getElementById('draft-status').value
        };

        const response = await fetch(
            `/api/auspex/prompts/workshop/drafts/${this.draftId}`,
            {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            }
        );

        if (response.ok) {
            this.showSaveIndicator();
            this.updateCommitButton();
        }
    }

    async runTest() {
        const query = document.getElementById('test-query').value.trim();
        const topic = document.getElementById('test-topic').value;
        const model = document.getElementById('test-model').value;

        if (!query) {
            alert('Please enter a test query');
            return;
        }

        // Save draft first
        await this.saveDraft();

        // Show loading
        const button = document.getElementById('run-test');
        const originalHTML = button.innerHTML;
        button.innerHTML = '<span class="loading-spinner"></span> Running...';
        button.disabled = true;

        const response = await fetch(
            `/api/auspex/prompts/workshop/drafts/${this.draftId}/test`,
            {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    test_query: query,
                    topic: topic,
                    model: model,
                    limit: 50
                })
            }
        );

        button.innerHTML = originalHTML;
        button.disabled = false;

        if (!response.ok) {
            alert('Test failed');
            return;
        }

        const result = await response.json();
        this.currentTestId = result.test_id;

        // Display results
        this.displayTestResult(result);

        // Update test count
        const count = parseInt(document.getElementById('test-count').textContent) + 1;
        document.getElementById('test-count').textContent = count;

        // Reload test history
        await this.loadTestHistory();
    }

    displayTestResult(result) {
        const output = document.getElementById('test-output');
        output.style.display = 'block';

        // Metrics
        const metrics = document.getElementById('test-metrics');
        metrics.innerHTML = `
            <div class="test-metric">
                <strong>Articles</strong>
                ${result.article_count}
            </div>
            <div class="test-metric">
                <strong>Time</strong>
                ${result.execution_time_ms}ms
            </div>
            <div class="test-metric">
                <strong>Length</strong>
                ${result.response_length} chars
            </div>
        `;

        // Response
        const response = document.getElementById('test-response');
        response.innerHTML = this.renderMarkdown(result.response_preview);

        // Reset rating
        document.querySelectorAll('.rating-stars i').forEach(star => {
            star.classList.remove('fas');
            star.classList.add('far');
        });

        document.getElementById('test-notes').value = '';
    }

    setRating(rating) {
        document.querySelectorAll('.rating-stars i').forEach(star => {
            const starRating = parseInt(star.dataset.rating);
            if (starRating <= rating) {
                star.classList.remove('far');
                star.classList.add('fas');
            } else {
                star.classList.remove('fas');
                star.classList.add('far');
            }
        });
    }

    async saveTestFeedback() {
        // Rating and notes are captured when running the test
        // This would update the existing test result
        alert('Feedback saved!');
    }

    showCommitModal() {
        const draftName = document.getElementById('draft-name').value;
        const draftDescription = document.getElementById('draft-description').value;

        // Pre-fill modal
        document.getElementById('commit-name').value =
            this.slugify(draftName) || 'custom_prompt';
        document.getElementById('commit-title').value = draftName || '';
        document.getElementById('commit-description').value = draftDescription || '';

        const modal = new bootstrap.Modal(document.getElementById('commitModal'));
        modal.show();
    }

    async commitPrompt() {
        const data = {
            name: document.getElementById('commit-name').value,
            title: document.getElementById('commit-title').value,
            description: document.getElementById('commit-description').value
        };

        // Validation
        if (!data.name || !data.title) {
            alert('Name and title are required');
            return;
        }

        const response = await fetch(
            `/api/auspex/prompts/workshop/drafts/${this.draftId}/commit`,
            {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            }
        );

        if (!response.ok) {
            const error = await response.json();
            alert(`Failed to commit: ${error.detail}`);
            return;
        }

        const result = await response.json();

        // Close modal
        bootstrap.Modal.getInstance(document.getElementById('commitModal')).hide();

        // Show success and redirect
        alert(`Prompt "${data.name}" created successfully!`);
        window.location.href = '/auspex-chat';
    }

    updateCommitButton() {
        const content = document.getElementById('draft-content').value;
        const button = document.getElementById('commit-prompt');

        // Enable if content is substantial
        if (content.length >= 100) {
            button.disabled = false;
        } else {
            button.disabled = true;
        }
    }

    // Utility methods
    addMessage(role, content) {
        const messagesContainer = document.getElementById('workshop-messages');
        const messageDiv = document.createElement('div');
        messageDiv.className = `workshop-message ${role}`;
        messageDiv.innerHTML = `
            <div class="message-role">${role === 'user' ? 'You' : 'Workshop Assistant'}</div>
            <div class="message-content">${this.renderMarkdown(content)}</div>
        `;
        messagesContainer.appendChild(messageDiv);
        return messageDiv;
    }

    scrollMessagesToBottom() {
        const container = document.getElementById('workshop-messages');
        container.scrollTop = container.scrollHeight;
    }

    updateCharCount() {
        const content = document.getElementById('draft-content').value;
        document.getElementById('char-count').textContent = `${content.length} characters`;
    }

    showSaveIndicator() {
        const button = document.getElementById('save-draft');
        const originalHTML = button.innerHTML;
        button.innerHTML = '<i class="fas fa-check"></i> Saved';
        setTimeout(() => {
            button.innerHTML = originalHTML;
        }, 2000);
    }

    renderMarkdown(text) {
        // Basic markdown rendering (use marked.js in production)
        return text
            .replace(/```([^`]+)```/gs, '<code>$1</code>')
            .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
            .replace(/\*([^*]+)\*/g, '<em>$1</em>');
    }

    slugify(text) {
        return text
            .toLowerCase()
            .replace(/[^a-z0-9]+/g, '_')
            .replace(/^_+|_+$/g, '');
    }

    truncate(text, length) {
        return text.length > length ? text.slice(0, length) + '...' : text;
    }

    formatTimestamp(iso) {
        const date = new Date(iso);
        return date.toLocaleString();
    }

    async loadTopics() {
        // Load available topics for testing
        const response = await fetch('/api/topics');
        const topics = await response.json();

        const select = document.getElementById('test-topic');
        topics.forEach(topic => {
            const option = document.createElement('option');
            option.value = topic.name;
            option.textContent = topic.name;
            select.appendChild(option);
        });
    }

    async closeWorkshop() {
        if (confirm('Close workshop? Your draft will be saved.')) {
            await this.saveDraft();
            window.location.href = '/auspex-chat';
        }
    }

    resetDraft() {
        if (confirm('Reset draft content? This cannot be undone.')) {
            document.getElementById('draft-content').value = '';
            this.updateCharCount();
        }
    }

    viewTestResult(test) {
        // Switch to test tab and display result
        const testTab = document.querySelector('[data-bs-target="#tab-test"]');
        new bootstrap.Tab(testTab).show();

        // Display the test result
        this.displayTestResult(test);
    }
}

// Initialize when page loads
document.addEventListener('DOMContentLoaded', () => {
    window.workshop = new PromptWorkshop();
});
```

---

## 6. Integration Points

### 6.1 Existing Prompt Manager Integration

Update `templates/auspex-prompt-manager.html` to add "Workshop" button:

```html
<div class="prompt-actions">
    <button class="btn btn-primary" onclick="window.location.href='/prompt-workshop'">
        <i class="fas fa-flask"></i> Workshop Mode
    </button>
    <button class="btn btn-success" onclick="promptManager.editPrompt()">
        <i class="fas fa-plus"></i> New Prompt
    </button>
</div>
```

### 6.2 Auspex Chat Integration

Add "Clone & Modify" option to prompt selector in `static/js/auspex-chat.js`:

```javascript
// When user selects a prompt
if (action === 'clone') {
    window.location.href = `/prompt-workshop?clone=${promptName}`;
}
```

### 6.3 Main Navigation

Add workshop link to navigation menu in `templates/base.html`:

```html
<li class="nav-item">
    <a class="nav-link" href="/prompt-workshop">
        <i class="fas fa-brain"></i> Prompt Workshop
    </a>
</li>
```

---

## 7. Testing Checklist

- [ ] Database migration runs cleanly
- [ ] Workshop session creation works
- [ ] Chat conversation flows properly
- [ ] Prompt extraction from code blocks works
- [ ] Draft auto-save functions correctly
- [ ] Test execution completes successfully
- [ ] Test results stored properly
- [ ] Rating system works
- [ ] Test history displays correctly
- [ ] Commit validation works
- [ ] Duplicate name checking works
- [ ] Committed prompts appear in prompt list
- [ ] Clone existing prompt works
- [ ] Draft deletion cleans up chat
- [ ] Character count updates
- [ ] Responsive design on mobile
- [ ] Error handling for API failures

---

## 8. Future Enhancements

### Phase 2
- Prompt templates library
- Version history/comparison
- Collaborative editing (multiple users)
- Prompt analytics dashboard

### Phase 3
- AI-suggested improvements
- A/B testing framework
- Public prompt sharing
- Community ratings

---

## Next Steps

1. **Review specifications** with team
2. **Create database migration**
3. **Implement backend API** (routes + service)
4. **Build frontend UI** (HTML + CSS + JS)
5. **Test workflow end-to-end**
6. **Deploy to staging**
7. **Gather user feedback**
8. **Iterate**

---

**Document Version:** 1.0
**Last Updated:** 2025-01-15
**Status:** Ready for Implementation
