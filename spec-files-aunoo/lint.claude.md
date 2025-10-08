# AunooAI Specification Linting for Claude

## Your Task

Optimize [the application specification](main.md) for clarity, consistency, and maintainability. Think of English as a programming language where consistent terminology and structure matter.

## Objectives

### 1. Language Consistency

Replace synonyms with standard terms throughout the document:

**Data Operations:**
- Use "fetch" (not pull/get/retrieve) - for external API calls
- Use "retrieve" (not fetch/get/read) - for database queries  
- Use "collect" (not gather/acquire/obtain) - for data collection pipeline
- Use "store" (not save/persist/write) - for database writes

**Analysis Operations:**
- Use "analyze" (not process/evaluate/examine/assess) - for AI operations
- Use "validate" (not check/verify/confirm) - for input validation
- Use "compute" (not calculate/determine) - for calculations

**Example transformation:**
```markdown
❌ Before:
- Get articles from the database
- Process them with AI
- Save results back to storage

✅ After:
- Retrieve articles from the database
- Analyze them with AI
- Store results back to database
```

### 2. Remove Duplication

Find and eliminate redundant information:
- If a concept is explained in detail in one section, don't repeat it elsewhere
- Consolidate related information into single sections
- Use cross-references instead of repeating content

**Example:**
```markdown
❌ Before:
## Security
Authentication uses sessions...

## API Routes
Each route requires authentication with sessions...

✅ After:
## Security
Authentication uses sessions... (detailed explanation)

## API Routes
Each route requires authentication (see [Security](#security))
```

### 3. Improve Structure

Reorganize content for better flow:
- Group related concepts together
- Use logical section ordering (general → specific)
- Ensure consistent heading levels
- Make dependencies explicit

### 4. Technical Precision

Replace vague language with specific terms:

```markdown
❌ Vague:
- The system handles errors appropriately
- API keys should be configured

✅ Precise:
- The system catches SQLite IntegrityError and returns HTTP 409 Conflict
- Store API keys in .env file with OPENAI_API_KEY environment variable
```

### 5. Standardize Formatting

Ensure consistent markdown usage:
- Use `code` for file names, variables, and technical terms
- Use **bold** for emphasis and key concepts
- Use > for quotes or important notes
- Use tables for comparisons
- Use consistent bullet point style (- not * or +)

## Specific Optimization Areas

### Database Schema Section

**Current issues to fix:**
- Inconsistent field descriptions
- Missing data type specifications
- Unclear relationships between tables
- Duplicate information

**Make it programming-like:**
```markdown
## Database Schema

SQLite database at `{DATABASE_DIR}/{instance}/fnaapp.db`

### table:articles
- Primary key: `uri` (Text, unique)
- Indexes:
  - `idx_topic` on `topic`
  - `idx_analyzed` on `analyzed`
  - `idx_publication_date` on `publication_date`
  
Fields:
- `uri`: Article unique identifier (from source URL)
- `title`: Article headline (Text, max 500 chars)
- `news_source`: Publication name (Text)
- `publication_date`: ISO 8601 timestamp (Text)
- `analyzed`: Analysis completion flag (Boolean, default FALSE)
...
```

### API Endpoints Section

**Make it more structured:**
```markdown
## API Endpoints

### Authentication Required
All endpoints require `session=Depends(verify_session)` except OAuth routes.

### POST /api/articles/analyze
Analyze articles with AI models.

Request:
```json
{
  "topic": "string (required)",
  "limit": "integer (optional, default 100)",
  "model": "string (optional, default gpt-4-mini)"
}
```

Response (200 OK):
```json
{
  "status": "success",
  "analyzed": 45,
  "results": [...]
}
```

Errors:
- 400: Missing required fields
- 404: Topic not found
- 500: Analysis failed
```

### Configuration Section

**Standardize environment variables:**
```markdown
## Configuration

Store in `.env` file at project root.

### Required Variables
- `OPENAI_API_KEY`: OpenAI API authentication (required for AI analysis)
- `NEWSAPI_KEY`: NewsAPI.org key (required for news collection)
- `SECRET_KEY`: Session encryption key (minimum 32 chars)

### Optional Variables
- `ANTHROPIC_API_KEY`: Anthropic Claude API key
- `DATABASE_DIR`: Database storage path (default: `app/data`)
- `ENVIRONMENT`: Deployment environment (dev|staging|production, default: dev)
```

## Quality Checks

Run these checks on the optimized specification:

### ✓ Consistency Check
- [ ] All "fetch/get/retrieve" replaced with standard terms
- [ ] All "process/analyze" made consistent
- [ ] All file paths use consistent format (e.g., `app/routes/file.py`)
- [ ] All code blocks have language specified (```python, ```bash, etc.)

### ✓ Completeness Check
- [ ] No sections duplicate information
- [ ] All cross-references work
- [ ] All acronyms defined on first use
- [ ] All code examples are complete and runnable

### ✓ Clarity Check
- [ ] Each sentence has single clear meaning
- [ ] Technical jargon is explained or avoided
- [ ] Examples illustrate concepts effectively
- [ ] Relationships between components are explicit

### ✓ Structure Check
- [ ] Sections follow logical order
- [ ] Heading hierarchy is consistent (## then ### then ####)
- [ ] Related information is grouped
- [ ] No orphaned sections

## Optimization Process

### Step 1: Read Through
Read the entire specification once to understand the content and identify issues.

### Step 2: Create Terminology Map
List all synonyms found and their standard replacements:
```
fetch/get/retrieve → "fetch" for APIs, "retrieve" for database
process/analyze/evaluate → "analyze"
save/store/persist → "store"
```

### Step 3: Section-by-Section Optimization
Work through each section:
1. Apply terminology standards
2. Remove duplicate content
3. Improve structure
4. Add missing details
5. Fix formatting

### Step 4: Verify Cross-References
Ensure all internal links work and references are accurate.

### Step 5: Final Review
Read through the optimized version to ensure it flows well and is easier to understand than the original.

## Output Format

Provide the complete optimized `main.md` file with:

1. **Summary of Changes**: Brief list of major improvements made
2. **Terminology Updates**: List of standardized terms
3. **Structural Changes**: Outline of reorganized sections
4. **Removed Duplicates**: List of eliminated redundant content
5. **Complete Optimized File**: The full updated specification

## Important Guidelines

### Preserve Critical Information
Do NOT remove or change:
- Technical specifications and requirements
- Database schema details
- API endpoint definitions
- Security requirements
- Performance requirements
- Error handling specifications
- Configuration requirements

### Focus on Presentation
Your goal is to make the SAME information clearer and more accessible, not to change what the application does.

### Use Active Voice
```markdown
❌ Passive: "Articles are stored in the database"
✅ Active: "Store articles in the database"

❌ Passive: "The API key should be configured"
✅ Active: "Configure the API key in .env"
```

### Use Present Tense
```markdown
❌ Past/Future: "The system will validate inputs"
✅ Present: "The system validates inputs"
```

### Use Imperative for Requirements
```markdown
❌ Descriptive: "The code should use type hints"
✅ Imperative: "Use type hints for all function signatures"
```

## Success Metrics

The optimization is successful when:

1. **Easier to Read**: Someone new can understand the system faster
2. **Easier to Maintain**: Updates can be made without confusion
3. **More Consistent**: Same concepts use same terminology throughout
4. **More Complete**: No gaps in critical information
5. **More Precise**: Technical details are specific and unambiguous
6. **Better Organized**: Logical flow makes sense
7. **More Actionable**: Developers can implement directly from spec

## Example Transformation

**Before:**
```markdown
## Articles

Articles can be fetched from various sources and then they get processed 
and stored. The system will analyze them and save the results.
```

**After:**
```markdown
## Article Processing Pipeline

1. **Collect** articles from data sources (NewsAPI, arXiv, Bluesky)
2. **Validate** article data format and completeness
3. **Analyze** content with AI models (sentiment, categorization, future signals)
4. **Store** enriched articles in database with metadata
5. **Index** articles in ChromaDB for semantic search
```

Focus on making the specification a clear, consistent, maintainable document that serves as the single source of truth for the AunooAI platform.

