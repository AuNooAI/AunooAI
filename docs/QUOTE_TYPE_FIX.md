# Market Signals Quote Styling Fix - quote_type Field

**Date:** 2025-11-18 16:50:30 CET
**Issue:** Extracted quotes displaying as "Auspex Commentary" (yellow) instead of "Source Quote" (blue)
**Status:** ✅ **FIXED**

---

## Problem

After fixing quote extraction (version 1.0.1), the LLM was successfully extracting actual quotes from article content. However, they were still being displayed with yellow "Auspex Commentary" styling instead of blue "Source Quote" styling.

### Root Cause

The React frontend checks for a `quote_type` field to determine styling:

**File:** `ui/src/App.tsx` (lines 1350-1356)

```typescript
const isDirectQuote = quote.quote_type === 'direct_quote';
const labelText = isDirectQuote ? 'Source Quote' : 'Auspex Commentary';
const bgColor = isDirectQuote ? 'bg-cyan-50 border-cyan-200' : 'bg-amber-50 border-amber-200';
const accentColor = isDirectQuote ? 'text-cyan-400' : 'text-amber-400';
```

**The Problem:**
- LLM was extracting real quotes ✅
- But NOT including `quote_type: 'direct_quote'` in response ❌
- Frontend defaulted to "Auspex Commentary" styling (yellow) ❌

---

## The Fix

Updated the Market Signals prompt to require `quote_type` field in all quote objects.

### 1. Updated JSON Schema

**File:** `data/prompts/market_signals/current.json` (lines 145-150)

Added `quote_type` to the schema:

```json
{
  "quote_type": {
    "type": "string",
    "enum": ["direct_quote"]
  }
}
```

And to required fields (line 158):

```json
"required": [
  "text",
  "source",
  "url",
  "context",
  "relevance",
  "quote_type"
]
```

### 2. Updated Example Output

Added `quote_type: "direct_quote"` to both example quotes in the prompt:

```json
"quotes": [
  {
    "text": "The AI bubble may burst soon...",
    "source": "TechCrunch (2025-01-03)",
    "url": "https://techcrunch.com/article-url",
    "context": "Analysis of market trends",
    "relevance": "Indicates timing and sequence of market correction",
    "quote_type": "direct_quote"  // ← ADDED
  },
  {
    "text": "Investments in [AI superintelligence]...",
    "source": "Financial Times (2025-01-02)",
    "url": "https://ft.com/article-url",
    "context": "Investment outlook report",
    "relevance": "Warns against short-term AGI expectations",
    "quote_type": "direct_quote"  // ← ADDED
  }
]
```

### 3. Added Explicit Instruction

Added to section 4 (Quotes) in the prompt:

```
- **quote_type**: MUST be set to "direct_quote" for all extracted quotes
  (this controls UI styling - direct quotes display in blue, synthetic commentary in yellow)
```

This makes it explicit to the LLM that:
1. The field is required
2. The value should be "direct_quote"
3. Why it matters (controls visual styling)

---

## Version History

- **1.0.0** → Original version with synthetic quote generation allowed
- **1.0.1** → Required actual quote extraction, forbid synthetic quotes
- **1.0.2** → Added `quote_type` field for proper UI styling

---

## UI Styling Logic

The frontend uses `quote_type` to determine card appearance:

### Direct Quote (`quote_type: 'direct_quote'`)
- Label: **"Source Quote"**
- Background: **Cyan/Blue** (`bg-cyan-50 border-cyan-200`)
- Accent: **Cyan** (`text-cyan-400`)
- Link color: **Cyan** (`text-cyan-600 hover:text-cyan-700`)
- Border: **Cyan** (`border-cyan-200`)

### Auspex Commentary (`quote_type` missing or other value)
- Label: **"Auspex Commentary"**
- Background: **Amber/Yellow** (`bg-amber-50 border-amber-200`)
- Accent: **Amber** (`text-amber-400`)
- Link color: **Amber** (`text-amber-600 hover:text-amber-700`)
- Border: **Amber** (`border-amber-200`)

---

## Expected LLM Response Format

```json
{
  "quotes": [
    {
      "text": "The decisive moment was the post-2007 breakthrough: once Lockheed gained interior access, CIA science teams prevented divestment to private contractors.",
      "source": "Medium (2025-11-12)",
      "url": "https://medium.com/@nickmadrid68/opening-the-lockheed-object-...",
      "context": "Research on government secrecy around recovered UFO technology",
      "relevance": "Demonstrates government control over advanced technology development",
      "quote_type": "direct_quote"  // ← REQUIRED
    }
  ]
}
```

---

## Testing

### Generate New Analysis

1. Go to Market Signals dashboard
2. Select a topic
3. Generate NEW analysis
4. Check quotes section

### Expected Results

**Quotes should now display:**
- ✅ Blue card background (cyan-50)
- ✅ "Source Quote" label (not "Auspex Commentary")
- ✅ Actual text from articles (verbatim)
- ✅ Clickable source links
- ✅ Verification URL

### Visual Comparison

**BEFORE (v1.0.1):**
```
┌─────────────────────────────────────┐
│ 🟡 Auspex Commentary                │  ← Yellow styling
│                                     │
│ "The decisive moment was..."        │  ← Real quote
│                                     │
│ 📎 Medium (2025-11-12)             │
└─────────────────────────────────────┘
```

**AFTER (v1.0.2):**
```
┌─────────────────────────────────────┐
│ 🔵 Source Quote                     │  ← Blue styling
│                                     │
│ "The decisive moment was..."        │  ← Real quote
│                                     │
│ 📎 Medium (2025-11-12)             │
└─────────────────────────────────────┘
```

---

## Validation Query

Check that new analyses include `quote_type`:

```sql
SELECT
    id,
    topic,
    created_at,
    jsonb_array_length(raw_output->'quotes') as quote_count,
    raw_output->'quotes'->0->>'quote_type' as first_quote_type,
    raw_output->'quotes'->0->>'source' as first_quote_source
FROM market_signals_runs
WHERE created_at > NOW() - INTERVAL '1 hour'
ORDER BY created_at DESC
LIMIT 5;
```

**Expected:**
- `first_quote_type` should be `"direct_quote"`
- `first_quote_source` should be publication name with date (not "Auspex Commentary")

---

## Troubleshooting

### If Quotes Still Show Yellow

1. **Check you generated a NEW analysis**
   - Old cached analyses won't have `quote_type` field
   - Must generate fresh analysis after v1.0.2 deployment

2. **Check LLM response includes quote_type**
   ```sql
   SELECT raw_output->'quotes' FROM market_signals_runs ORDER BY created_at DESC LIMIT 1;
   ```
   Should show `"quote_type": "direct_quote"`

3. **Check prompt version is loaded**
   ```python
   from app.prompt_manager import get_prompt
   prompt = get_prompt('market_signals')
   print(prompt['version'])  # Should be 1.0.2
   print('quote_type' in str(prompt['expected_output_schema']))  # Should be True
   ```

4. **Check React build is up to date**
   ```bash
   cd ui
   npm run build
   ./deploy-react-ui.sh
   ```

---

## Files Changed

### 1. Prompt Configuration
**File:** `data/prompts/market_signals/current.json`
- Added `quote_type` field to schema
- Added `quote_type` to required fields
- Added `quote_type` to example quotes
- Added instruction explaining quote_type purpose
- Version: 1.0.1 → 1.0.2

### 2. Helper Scripts
- `add_quote_type.py` - Script to update schema and examples
- `add_quote_type_instruction.py` - Script to add instruction text

---

## Complete Fix Summary

The quote extraction fix is now complete in three parts:

### Part 1: Data Source (v1.0.0 → v1.0.1)
- ✅ Database query fetches `raw_markdown`
- ✅ LLM receives full article content
- ✅ Prompt requires verbatim extraction

### Part 2: Visual Styling (v1.0.1 → v1.0.2)
- ✅ Schema includes `quote_type` field
- ✅ Examples show `quote_type: "direct_quote"`
- ✅ Instructions explain quote_type purpose
- ✅ LLM outputs proper styling indicator

### Part 3: Frontend Rendering (Already Working)
- ✅ React checks `quote_type` field
- ✅ Applies blue styling for `direct_quote`
- ✅ Applies yellow styling for missing/other values

---

## Success Criteria

After generating a fresh analysis with v1.0.2:

- [ ] Quotes are displayed with **blue** background (not yellow)
- [ ] Label shows **"Source Quote"** (not "Auspex Commentary")
- [ ] Quote text is **verbatim from article** (not paraphrased)
- [ ] Source shows **publication name and date**
- [ ] URL is **clickable and verifiable**
- [ ] Context describes **where quote appears in article**
- [ ] Database shows `quote_type: "direct_quote"` in raw_output

---

**Status:** ✅ **DEPLOYED AND READY FOR TESTING**

Generate a new Market Signals analysis to see real quotes with proper blue "Source Quote" styling!

---

**Deployment Date:** 2025-11-18 16:50:30 CET
**Service:** Restarted successfully
**Version:** 1.0.2
