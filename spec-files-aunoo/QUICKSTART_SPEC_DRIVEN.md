# Quick Start: Spec-Driven Development

## 🚀 5-Minute Setup

### Step 1: Understand the Files

You have several files for spec-driven development:

```
specs/main.md              ← Main specification (overview and context)
specs/database.md          ← Database schema specification
specs/compile.claude.md    ← Instructions for Claude to generate code
specs/compile.prompt.md    ← Instructions for GitHub Copilot
specs/lint.claude.md       ← Instructions for Claude to clean up main.md
specs/lint.prompt.md       ← Instructions for Copilot to clean up main.md
```

**Think of it like this:**
- `specs/main.md` = Your main requirements written in English
- `specs/database.md` = Detailed database schema and operations
- `specs/compile.*.md` = Instructions that tell AI how to turn requirements into Python code
- `specs/lint.*.md` = Instructions that tell AI how to clean up your requirements

### Step 2: Choose Your AI Tool

Pick ONE of these options based on what you have access to:

| Tool | Cost | Setup Difficulty | Best For |
|------|------|------------------|----------|
| **Cline (Claude in VS Code)** | $20/month | Easy | Most powerful option |
| **GitHub Copilot** | $10/month | Easiest | Quick iterations |
| **Claude.ai (Web/Desktop)** | Free/Pro | None | No installation needed |
| **Cursor IDE** | $20/month | Easy | All-in-one solution |

---

## 🎯 Method 1: Using Cline (Recommended)

Cline is a VS Code extension that gives you Claude directly in your editor.

### Installation

1. **Install VS Code** (if you don't have it)
2. **Install Cline extension**:
   - Open VS Code
   - Go to Extensions (Ctrl+Shift+X or Cmd+Shift+X)
   - Search for "Cline"
   - Click Install
3. **Add your Anthropic API key**:
   - Get key from: https://console.anthropic.com/
   - In VS Code, click the Cline icon in sidebar
   - Enter your API key when prompted

### Daily Usage

#### To Build a New Feature:

1. **Edit `specs/main.md`** - Add your feature description:
   ```markdown
   ### Export Articles to CSV
   
   When user clicks "Export" button:
   - Query articles table for current topic
   - Include fields: title, url, publication_date, sentiment, category
   - Generate CSV with UTF-8 encoding
   - Set filename: {topic}_articles_{date}.csv
   - Return file for download
   ```

2. **Open Cline** (click icon in VS Code sidebar)

3. **Type this command**:
   ```
   @specs/compile.claude.md implement the "Export Articles to CSV" feature from @specs/main.md
   ```

4. **Watch Cline work**:
   - It reads both files
   - Generates the code
   - Shows you what it's creating
   - Creates/modifies files automatically

5. **Review and test**:
   ```bash
   python app/main.py
   # Test the export feature
   ```

#### To Fix a Bug:

```
@compile.claude.md 

I'm getting an error when exporting articles: "UnicodeEncodeError"
Fix the CSV export to handle special characters properly.
Check the specification in @main.md and database schema in @specs/database.md
```

#### To Clean Up Your Spec:

```
@lint.claude.md

The main.md file is getting messy. Optimize it for clarity and remove duplicates.
```

---

## 🎯 Method 2: Using GitHub Copilot

If you have GitHub Copilot already (many developers do).

### Daily Usage

#### To Build a New Feature:

1. **Edit `main.md`** - Add your feature
2. **Open Copilot Chat** (Ctrl+Shift+I or Cmd+Shift+I)
3. **Type**:
   ```
   @workspace implement the export feature following /specs/compile.prompt.md and looking at specs/main.md
   ```

Or use the `/` command:
```
/specs/compile.prompt.md focus on CSV export functionality
```

#### Quick Inline Suggestions:

Copilot automatically reads `specs/main.md` if it's open, so:
1. Open `specs/main.md` and the Python file you're editing
2. Start typing a function name
3. Copilot suggests code based on the spec

---

## 🎯 Method 3: Using Claude.ai (Free)

No installation needed - use the web or desktop app.

### Daily Usage

#### To Build a New Feature:

1. **Go to claude.ai** or open Claude desktop app

2. **Start a new chat** and paste:
   ```
   I'm working on a Python/FastAPI application. I'll give you:
   1. Compilation instructions
   2. The specification
   3. The task
   
   [Paste entire contents of compile.claude.md]
   
   ---
   
   Here's the relevant part of the specification:
   [Paste the relevant section from main.md]
   
   ---
   
   Task: Implement the CSV export feature
   ```

3. **Claude generates code** - Copy and paste into your files

4. **For follow-ups**:
   ```
   Add error handling for the case where no articles exist
   ```

#### To Clean Up Your Spec:

1. **Start new chat**
2. **Paste**:
   ```
   [Paste entire contents of lint.claude.md]
   
   ---
   
   Here's the specification to optimize:
   [Paste entire main.md]
   ```

3. **Claude returns cleaned up version** - Replace your `main.md`

---

## 🎯 Method 4: Using Cursor IDE

Cursor is like VS Code but with AI built-in.

### Daily Usage

1. **Open Cursor**
2. **Press Cmd+K or Ctrl+K** (Cursor's AI command)
3. **Reference files with @**:
   ```
   @compile.claude.md implement CSV export from @main.md
   ```

Very similar to Cline but with different UI.

---

## 📝 Real-World Examples

### Example 1: Add User Profile Feature

**1. Edit `main.md`:**
```markdown
### User Profile Page

When user navigates to /profile:
- Display user information (username, email, created_at)
- Show list of user's topics (max 20)
- Include "Edit Profile" button
- If user clicks "Edit Profile":
  - Navigate to /profile/edit
  - Show form with username and email fields
  - On save, validate email format
  - Update users table
  - Show success message
```

**2. Use Cline:**
```
@compile.claude.md 

Implement the user profile feature from @main.md

Create:
1. Route in app/routes/profile_routes.py
2. HTML template in templates/profile.html
3. HTML template in templates/profile_edit.html
4. Update main.py to include the router
```

**3. Cline generates:**
- `/app/routes/profile_routes.py` (new file)
- `/templates/profile.html` (new file)
- `/templates/profile_edit.html` (new file)
- Updates to `/app/main.py`

**4. Test it:**
```bash
# Development (local)
python app/main.py
# Navigate to http://localhost:8000/profile

# Production (with reverse proxy)
python app/server_run.py
```

### Example 2: Fix Performance Issue

**1. Use Cline:**
```
@compile.claude.md

The article listing page is slow when there are 10,000+ articles.
According to @main.md, we should use pagination.

Optimize the /api/articles endpoint to:
1. Add pagination (page_size=20 default)
2. Add database index on publication_date
3. Return total_count in response
```

**2. Cline:**
- Analyzes current code
- Adds pagination logic
- Creates database migration for index
- Updates API response format

### Example 3: Clean Up Messy Spec

After months of updates, `main.md` has duplicates and inconsistencies.

**Use Cline:**
```
@lint.claude.md

The main.md specification has become messy:
- Same information repeated in multiple places
- Inconsistent terminology (get/fetch/retrieve used interchangeably)
- Database schema section is out of order

Please optimize it according to the linting guidelines.
```

**Cline returns:**
- Cleaned up version
- Summary of changes made
- You review and accept

---

## 🔄 The Complete Workflow

Here's how it all fits together day-to-day:

```
┌─────────────────────────────────────────────┐
│ 1. You have an idea or requirement          │
└─────────────┬───────────────────────────────┘
              ↓
┌─────────────────────────────────────────────┐
│ 2. Describe it in main.md                   │
│    (Use clear, procedural language)         │
└─────────────┬───────────────────────────────┘
              ↓
┌─────────────────────────────────────────────┐
│ 3. Use AI tool + compile.*.md               │
│    "Implement this feature from main.md"    │
└─────────────┬───────────────────────────────┘
              ↓
┌─────────────────────────────────────────────┐
│ 4. AI generates code                        │
│    (Following patterns in compile.*.md)     │
└─────────────┬───────────────────────────────┘
              ↓
┌─────────────────────────────────────────────┐
│ 5. Review the generated code                │
│    (Make sure it matches your intent)       │
└─────────────┬───────────────────────────────┘
              ↓
┌─────────────────────────────────────────────┐
│ 6. Test it                                  │
│    python app/main.py                       │
└─────────────┬───────────────────────────────┘
              ↓
         Does it work?
              ↓
         ┌────┴────┐
         │         │
        YES       NO
         │         │
         │         └─> Update main.md, try again
         ↓
┌─────────────────────────────────────────────┐
│ 7. Periodically: Run lint.*.md              │
│    To keep main.md clean                    │
└─────────────────────────────────────────────┘
```

---

## 💡 Pro Tips

### Tip 1: Keep main.md Open
When coding, keep `main.md` open in a tab. AI tools often read it automatically for context.

### Tip 2: Use Correct Entry Points
- **Development**: `python app/main.py` (local testing)
- **Production**: `python app/server_run.py` (internet-facing with reverse proxy)

### Tip 3: Be Specific in Tasks
❌ Bad: "Fix the articles"
✅ Good: "Fix the article collection to handle rate limiting from NewsAPI per the specification"

### Tip 4: Reference Existing Code
```
@compile.claude.md

Implement user notifications similar to how keyword alerts work in 
app/routes/keyword_alerts.py, but following the specification in @main.md
```

### Tip 5: Iterative Development
Don't try to build everything at once:
```
Step 1: @compile.claude.md implement basic CSV export (no filters)
Step 2: @compile.claude.md add date range filtering to CSV export
Step 3: @compile.claude.md add custom column selection to CSV export
```

### Tip 6: Use for Refactoring
```
@compile.claude.md

The article analysis code in app/research.py is hard to maintain.
Refactor it according to the patterns in @main.md:
- Extract AI model calls to separate service
- Add proper error handling
- Use async/await patterns
Keep existing functionality intact.
```

---

## 🆘 Troubleshooting

### "AI doesn't understand main.md"
**Solution:** Make main.md more specific and procedural:
```markdown
❌ "The system should handle errors well"
✅ "When API call fails, return HTTP 503 and log the full error"
```

### "Generated code doesn't match my style"
**Solution:** Update `compile.*.md` with your style guide:
```markdown
## Code Style
- Use single quotes for strings
- Max line length: 100 characters
- Always use trailing commas in lists
```

### "main.md is getting too long"
**Solution:** Break it into sections:
```
main.md              (overview and references)
specs/database.md    (detailed database spec)
specs/api.md         (detailed API spec)
specs/security.md    (detailed security spec)
```

Update references:
```markdown
## Database Schema
See [detailed database specification](specs/database.md)
```

### "I want to use different AI models"
You can! Just adapt the prompts:
- For GPT-4: Use compile.prompt.md as a base
- For Gemini: Similar to Claude prompts
- For local models: May need simpler prompts

---

## 📚 Learning More

1. **Read the GitHub article**: The methodology is explained there
2. **Experiment**: Try small features first
3. **Iterate**: Your first specs won't be perfect - that's okay!
4. **Share**: Your team can all use the same `main.md`

---

## 🎬 Quick Reference Card

**To implement a feature:**
```
@compile.claude.md implement [feature name] from @main.md
```

**To fix a bug:**
```
@compile.claude.md fix [issue] according to @main.md
```

**To refactor code:**
```
@compile.claude.md refactor [component] to match @main.md patterns
```

**To clean spec:**
```
@lint.claude.md optimize main.md for clarity
```

**To get help:**
```
@compile.claude.md 

I want to implement [feature] but I'm not sure how.
Look at @main.md and suggest an approach.
```

---

## ✅ Next Actions

1. **Choose your AI tool** (Cline recommended)
2. **Try a small feature** (add a new API endpoint)
3. **Update main.md** with what you learned
4. **Share with team** if working collaboratively

Remember: **main.md is your source of truth.** Everything else is generated from it!
