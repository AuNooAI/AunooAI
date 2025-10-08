# Spec-Driven Development for AunooAI

This project uses **spec-driven development** methodology where Markdown specifications serve as both documentation and programming instructions for AI coding agents.

## Overview

Based on the [GitHub blog article on spec-driven development](https://github.blog/ai-and-ml/generative-ai/spec-driven-development-using-markdown-as-a-programming-language-when-building-with-ai/), we maintain three core files:

1. **`main.md`** - The complete application specification
2. **Compilation prompts** - Instructions for AI agents to generate code
3. **Linting prompts** - Instructions to optimize the specification

## File Structure

```
AunooAI/specs/
├── main.md                    # Main specification (single source of truth)
├── compile.prompt.md          # For GitHub Copilot (VS Code)
├── compile.claude.md          # For Claude (Cline/Claude Dev/API)
├── lint.prompt.md             # Lint prompt for GitHub Copilot
├── lint.claude.md             # Lint prompt for Claude
└── README_SPEC_DRIVEN.md      # This file
```

## The Workflow

### 1. Edit the Specification

Edit `main.md` to describe new features, changes, or requirements:

```markdown
### Article Collection

When user clicks "Collect Articles":
- Fetch articles from NewsAPI using stored API key
- Filter by date range (last 7 days default)
- For each article:
  - Validate required fields (title, url, publishedAt)
  - Check if article already exists by URI
  - If new, store in database with topic
- Return count of new articles collected
```

### 2. Compile to Code

#### Using GitHub Copilot (VS Code)

1. Open the file you want to modify
2. Open GitHub Copilot Chat
3. Type `@workspace /compile.prompt.md` or reference the file
4. Add context: "Focus on implementing article collection"
5. Review and apply the generated code

#### Using Claude (Cline/Claude Dev)

1. Open your Claude-based coding tool
2. Use the command to reference a file: `@compile.claude.md`
3. Add context: "Implement the article collection feature from main.md"
4. Review the implementation
5. Apply changes

#### Using Claude API Directly

```python
import anthropic

client = anthropic.Anthropic(api_key="your-api-key")

with open("main.md", "r") as f:
    spec = f.read()

with open("compile.claude.md", "r") as f:
    instructions = f.read()

message = client.messages.create(
    model="claude-3-5-sonnet-20241022",
    max_tokens=4096,
    messages=[
        {
            "role": "user",
            "content": f"{instructions}\n\nSpecification:\n{spec}\n\nTask: Implement the article collection feature"
        }
    ]
)

print(message.content[0].text)
```

### 3. Test and Iterate

```bash
# Run the application
python app/main.py

# Test the feature
curl -X POST http://localhost:8000/api/collect/newsapi \
  -H "Content-Type: application/json" \
  -d '{"topic": "artificial intelligence", "days": 7}'

# If something doesn't work, update main.md and repeat
```

### 4. Lint the Specification

As the spec grows, keep it clean and consistent:

#### Using GitHub Copilot

1. Open `main.md`
2. Open GitHub Copilot Chat
3. Type `@workspace /lint.prompt.md`
4. Review the suggested improvements
5. Apply changes

#### Using Claude

1. Reference `@lint.claude.md`
2. Ask: "Optimize the main.md specification"
3. Review the optimized version
4. Replace `main.md` with the improved version

## Best Practices

### Writing Specifications

**Use procedural, programming-like language:**

✅ Good:
```markdown
### User Login Flow

When user submits login form:
- Validate email format
- If invalid:
  - Return error "Invalid email format"
  - Stop processing
- Query database for user by email
- If user not found:
  - Return error "User not found"
  - Stop processing
- Verify password with bcrypt
- If password incorrect:
  - Return error "Invalid password"
  - Increment failed_attempts counter
  - Stop processing
- Create new session with user_id
- Set secure session cookie
- Redirect to dashboard
```

❌ Avoid vague descriptions:
```markdown
The login system should authenticate users properly and handle errors.
```

### Specification Structure

Organize like a programming language:

```markdown
## Configuration
Environment variables and settings

## Database Schema
Tables, fields, relationships

## Core Functions
Main business logic flows

## API Endpoints
Request/response specifications

## Error Handling
Error codes and messages

## Deployment
Build and run instructions
```

### Making Changes

**Small, focused changes:**
```markdown
# ✅ Good - specific and testable
Add pagination to article listing:
- Accept `page` and `page_size` query parameters
- Default page_size to 20
- Return max 100 items per page
- Include total_count in response
```

```markdown
# ❌ Avoid - too vague
Improve the article listing feature
```

## AI Agent Compatibility

### GitHub Copilot

**Strengths:**
- Excellent at catching small specification changes automatically
- Great for in-IDE workflow
- Fast iteration with `/` commands

**Best for:**
- Incremental updates to existing code
- Refactoring within files
- Quick fixes and improvements

**How to use:**
- Use `compile.prompt.md` with `@workspace` references
- Use `/` commands for quick invocations
- Focus on specific files or changes

### Claude (Cline/Claude Dev/API)

**Strengths:**
- Better at understanding complex specifications
- Excellent at explaining reasoning
- Great for architectural decisions
- Handles larger context windows

**Best for:**
- New feature implementation
- Cross-file refactoring
- Complex business logic
- Code review and improvement suggestions

**How to use:**
- Use `compile.claude.md` with detailed instructions
- Reference multiple files with `@` syntax
- Ask for explanations and alternatives
- Request test cases and documentation

## Example Session

### Scenario: Add New Feature

1. **Update specification in `main.md`:**
```markdown
### Keyword Alerts

When user creates keyword alert:
- Accept keyword, topic, and threshold
- Validate keyword (min 3 chars, max 100 chars)
- Check if alert already exists for user
- If exists, return error "Alert already exists"
- Store alert in keyword_alerts table
- Set is_active to TRUE
- Return alert_id and created_at
```

2. **Compile with Claude:**
```
@compile.claude.md

Implement the keyword alerts feature from main.md. 
Focus on the backend API endpoint and database operations.
```

3. **Claude generates:**
- New route in `app/routes/keyword_alerts.py`
- Database model in `app/database_models.py`
- Service class in `app/services/keyword_alert_service.py`
- Pydantic models for validation

4. **Test:**
```bash
pytest tests/test_keyword_alerts.py -v
```

5. **Lint specification:**
```
@lint.claude.md

Optimize the main.md specification for clarity and remove any duplicates.
```

## Tips and Tricks

### For Better Code Generation

1. **Be specific about error handling:**
```markdown
If API call fails:
- Log error with full traceback
- Return HTTP 503 Service Unavailable
- Include retry-after header (60 seconds)
```

2. **Specify data validation:**
```markdown
Validate article data:
- title: Required, max 500 chars
- url: Required, valid HTTP/HTTPS URL
- published_at: Required, ISO 8601 format
```

3. **Include examples:**
```markdown
Example request:
```json
{"keyword": "artificial intelligence", "threshold": 5}
```

Example response:
```json
{"alert_id": 42, "created_at": "2024-01-15T10:30:00Z"}
```
```

### For Better Specifications

1. **Use consistent terminology** (run lint prompt regularly)
2. **Break complex features into steps**
3. **Specify database schema changes explicitly**
4. **Include deployment considerations**
5. **Document configuration requirements**

## Troubleshooting

### Code doesn't match specification

- Make sure the AI agent read the latest version of `main.md`
- Be more specific in the specification
- Provide examples of expected behavior
- Reference existing code patterns

### Specification is getting messy

- Run the lint prompt regularly
- Break large specifications into modules
- Use cross-references instead of duplication
- Remove obsolete sections

### AI agent makes breaking changes

- Add to specification: "Preserve existing functionality"
- Use minimal change requests
- Review generated code before applying
- Maintain version control

## Benefits

1. **Single Source of Truth**: Specification is always up to date
2. **Faster Development**: AI agents handle boilerplate
3. **Better Documentation**: Spec = docs = code
4. **Easier Onboarding**: New developers read the spec
5. **Consistent Code**: AI follows same patterns
6. **Language Agnostic**: Could regenerate in different language

## Future Possibilities

From the [GitHub blog article](https://github.blog/ai-and-ml/generative-ai/spec-driven-development-using-markdown-as-a-programming-language-when-building-with-ai/):

- **Language switching**: Regenerate entire codebase in different language
- **Module breaking**: Split large apps into microservices
- **Testing generation**: Auto-generate test suites from specs
- **Documentation generation**: Create user docs from technical specs

## Learn More

- [GitHub Blog: Spec-Driven Development](https://github.blog/ai-and-ml/generative-ai/spec-driven-development-using-markdown-as-a-programming-language-when-building-with-ai/)
- GitHub Copilot Documentation
- Claude API Documentation
- Cline (Claude Dev) Extension for VS Code

---

**Remember**: The specification in `main.md` is your programming language. Keep it clear, consistent, and complete, and AI agents will help you build and maintain high-quality code.

