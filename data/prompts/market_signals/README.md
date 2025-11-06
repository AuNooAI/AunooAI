# Market Signals Analysis Prompt

## Purpose

Analyzes articles to identify:
- Future signals and their frequency
- Disruption scenarios and bubble indicators
- Strategic opportunities
- Timeline risks

## Editing the Prompt

1. **Edit `current.json`** to modify the active prompt
2. **Test your changes** by triggering a new analysis
3. **Version your changes** by incrementing `version` field
4. **Use the Prompt Management API** to save versioned copies

## Prompt Structure

### System Prompt
Defines the AI's role and expertise areas. Keep this concise and focused on strategic analysis.

### User Prompt
Contains the actual analysis instructions and output format. This is where you:
- Define the JSON structure
- Specify signal types
- Set data quality requirements
- Provide examples

## Variables

The following variables are automatically substituted by the backend:

- `{topic}`: Name of the research topic (e.g., "Cloud Repatriation")
- `{article_count}`: Number of articles being analyzed
- `{date_range}`: Time period covered (e.g., "Last 30 days")
- `{articles}`: Formatted article content (auto-filled by backend)

## Output Schema

The prompt generates structured JSON with 4 main sections:

### 1. future_signals
Array of emerging patterns:
```json
{
  "signal": "Description of the signal",
  "frequency": "Low|Medium|High|Very High",
  "time_to_impact": "Timeframe description",
  "description": "Explanation"
}
```

**Guidelines:**
- Identify 3-5 distinct signals
- Frequency based on article mentions
- Use composite timeframes (e.g., "Immediate/Mid-term")

### 2. risk_cards
Array of disruption scenarios and risks (exactly 2 cards):
```json
{
  "title": "Risk title",
  "description": "Detailed description with data",
  "severity": "critical|high|medium|low",
  "icon": "warning|clock"
}
```

**Guidelines:**
- Card 1: General risk with "warning" icon
- Card 2: Timeline risk with "clock" icon
- Include specific statistics when available
- Focus on actionable concerns

### 3. opportunity_cards
Array of strategic opportunities (exactly 2 cards):
```json
{
  "title": "Opportunity title",
  "description": "Detailed description",
  "impact": "high|medium|low",
  "icon": "lightbulb|checkmark"
}
```

**Guidelines:**
- Card 1: Strategic opportunity with "lightbulb" icon
- Card 2: Proven advantage with "checkmark" icon
- Highlight competitive positioning
- Focus on actionable opportunities

### 4. quotes
Array of impactful quotes (2-3 quotes):
```json
{
  "text": "Quote text",
  "attribution": "Source attribution",
  "source": "URL (optional)"
}
```

**Guidelines:**
- Extract from articles or synthesize from consensus
- Include source name in attribution
- Add URL when available

## Best Practices

1. **Be Specific:** Use exact percentages, dates, and names from articles
2. **Balance Views:** Include both optimistic and pessimistic perspectives
3. **Actionable:** Focus on insights that inform decision-making
4. **Evidence-Based:** Ground claims in article data
5. **Structured:** Maintain the JSON schema strictly
6. **Consistent Icons:** Follow the 2+2 card pattern (warning, clock, lightbulb, checkmark)

## Card Layout Pattern

The UI displays cards in a 2x2 grid:

```
┌─────────────────────┬─────────────────────┐
│ ⚠️ Risk (Warning)   │ 💡 Opportunity      │
│                     │    (Lightbulb)      │
├─────────────────────┼─────────────────────┤
│ 🕐 Timeline Risk    │ ✅ Proven Advantage │
│    (Clock)          │    (Checkmark)      │
└─────────────────────┴─────────────────────┘
```

This pattern ensures visual balance and clear categorization.

## Testing Your Changes

After editing the prompt:

1. **Validate JSON:** Use a JSON validator to check syntax
2. **Test with API:**
   ```bash
   curl -X POST http://localhost:6005/api/market-signals/analysis?topic=YourTopic \
     -H "Cookie: session=your_session_cookie"
   ```
3. **Check Output:** Verify all 4 sections are present and well-formed
4. **Review Quality:** Ensure insights are actionable and evidence-based

## Version History

- **v1.0.0** (2025-01-06): Initial prompt with 2+2 card layout pattern
  - Future signals table with frequency badges
  - Risk cards (warning + clock icons)
  - Opportunity cards (lightbulb + checkmark icons)
  - Quote attributions with sources

## API Integration

This prompt is loaded by:
- **Route:** `app/routes/market_signals_routes.py`
- **Endpoint:** `GET /api/market-signals/analysis?topic={topic}`
- **Loader:** `app/services/prompt_loader.py`

The backend automatically:
1. Loads `current.json` from this directory
2. Fetches recent articles for the topic
3. Substitutes variables in the template
4. Calls AI model with structured prompt
5. Validates and returns JSON response

## Troubleshooting

**Problem:** AI returns invalid JSON
**Solution:** Add more explicit JSON formatting instructions in user_prompt

**Problem:** Cards don't match icon pattern
**Solution:** Emphasize "Generate exactly 2 risk cards..." in instructions

**Problem:** Quotes missing sources
**Solution:** Increase emphasis on source attribution in prompt

**Problem:** Generic insights lacking specifics
**Solution:** Add examples of good vs bad descriptions in prompt

## Related Documentation

- [MARKET_SIGNALS_SPEC.md](../../spec-files-aunoo/MARKET_SIGNALS_SPEC.md) - Full feature specification
- [compile.claude.md](../../spec-files-aunoo/compile.claude.md) - Prompt management pattern
- [Auspex Service](../../app/services/auspex_service.py) - AI analysis integration
