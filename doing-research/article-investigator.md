# Article Investigator

Article Investigator is your primary workspace for exploring, analyzing, and managing threat intelligence articles. This powerful tool provides multiple viewing modes, advanced filtering, and export capabilities to help you quickly find and assess the information that matters most.

***

### What is Article Investigator?

Article Investigator is designed for hands-on intelligence research, offering:

* Multiple View Modes: Switch between card, table, HUD, and reader layouts
* Advanced Filtering: Narrow results by topic, date, source, and more
* Quick Actions: Hide irrelevant articles, bookmark important ones, and restore hidden items
* Export Options: Save your findings as CSV, PDF, or Markdown

Pagination Controls: Navigate large article sets efficiently

***

### Getting Started

#### Step 1: Select Your Data Source

1. **At the top of the page, choose your focus:**

* Topics: Select one or more threat intelligence categories (e.g., APT Groups, Malware, Vulnerabilities)
* Date Range: Pick a time period using the date picker
* Sources (optional): Filter by specific news outlets or feeds

2. **Click the Load Articles or Refresh button to fetch matching articles**

<figure><img src="../.gitbook/assets/unknown.png" alt=""><figcaption></figcaption></figure>

#### Step 2: Choose Your View Mode

The Article Investigator offers four distinct viewing modes. Select the one that fits your workflow:

**Card View (Default)**

* Best for: Visual browsing and quick assessment
* Shows: Article title, source, date, summary, and key metadata
* Actions: Click to expand, hide unwanted articles, or bookmark

**Table View (Techmeme Style)**

* Best for: Scanning headlines quickly
* Shows: Condensed list with title, source, and date
* Actions: Compact format for fast review of many articles

**HUD View**

* Best for: Side-by-side comparison and deep analysis
* Shows: Split-pane layout with article list and content preview
* Actions: Click an article to view full content without leaving the page

<figure><img src="../.gitbook/assets/unknown (1).png" alt=""><figcaption></figcaption></figure>

**Reader View**

* Best for: Focused reading of full article text
* Shows: Clean, distraction-free article content
* Actions: Navigate between articles with keyboard or buttons

#### Step 3: Filter and Refine

Click the Filter button in the toolbar to access advanced filtering options:

* Topics: Narrow to specific threat categories
* Date Range: Adjust your time window
* Sources: Include or exclude specific publishers
* Entities: Filter by mentioned organizations, threat actors, or technologies
* Bias/Credibility: Filter by media bias or source credibility scores

Apply filters, then click Done to see updated results.

![](<../.gitbook/assets/unknown (2).png>)

***

### Key Features

#### Article Actions

Each article card or row provides quick actions:

* Expand/Collapse: Click the title or expand icon to view full details
* Hide Article: Remove irrelevant articles from your view (click the X or hide icon)
* Bookmark: Mark important articles for later review
* Open in New Tab: Click the external link icon to view the original source

#### Toolbar Options

The toolbar at the top of Article Investigator provides:

* View Options: Toggle between card, table, HUD, and reader modes
* Export: Download current results as CSV, PDF, or Markdown
* Filter: Access advanced filtering controls
* Restore Hidden: Unhide articles you previously removed (appears when articles are hidden)

#### Pagination

Navigate large article sets using pagination controls at the bottom:

* Show All: Display all articles on one page (use with caution for large sets)
* Paginated Mode: Browse 25 articles at a time (default)
* Page Navigation: Use Previous/Next buttons or jump to a specific page

***

### Narrative Explorer Configuration

The Narrative Explorer's Config button opens a configuration modal that controls how the AI analyzes articles to identify incidents, trends, entities, and emerging narratives.

#### **System Prompt**

Customize the core instructions that guide AI analysis.

**System Prompt Template**&#x20;

The main instructions defining what the AI looks for, how findings are structured, and what patterns to identify.

**User Prompt Template**&#x20;

Controls how articles are presented to the AI for analysis.

**Organizational Profile Integration**

* Profile Context Template: Define how org profile data is injected into prompts
* Toggle to enable/disable profile integration

**Available Placeholders:**

| Placeholder              | Purpose                        |
| ------------------------ | ------------------------------ |
| {topic}                  | Current analysis topic         |
| {ontology\_text}         | Generated ontology guidance    |
| {articles\_text}         | Formatted article content      |
| {profile\_context}       | Organizational profile context |
| {analysis\_instructions} | AI analysis instructions       |
| {quality\_guidelines}    | Quality control guidelines     |

**Actions:**&#x20;

Reset to Default, Preview with Sample Data, Validate Template

***

#### Ontology

Define the vocabulary, entity types, and classification rules the AI uses.

Base Ontology Core classification structure using a 7-Type system:

| Type              | Description                                |
| ----------------- | ------------------------------------------ |
| incident          | Disruptive occurrences requiring response  |
| event             | Noteworthy developments and announcements  |
| entity            | Organizations, people, products tracked    |
| expertise         | Expert analysis and authoritative insights |
| informed\_insider | Insider perspectives and leaks             |
| trend\_signal     | Market trends and behavioral shifts        |
| strategic\_shift  | Major strategic and policy changes         |

**Domain-Specific Overlays**&#x20;

Add industry-specific rules by entering a domain key (e.g., scientific\_publisher, finance, healthcare) or use vanilla for no overlay.

**Classification Examples**&#x20;

Provide concrete examples to improve classification accuracy.

**Required Output Fields:**&#x20;

name, type, subtype, description, timeline, significance, plausibility, investigation\_leads, source\_quality, misinfo\_flags

**Actions:**&#x20;

Reset to Default, Add Domain Overlay, Validate Structure

***

#### AI Guidance

_Fine-tune how the AI performs analysis._

**Analysis Instructions**

Specific instructions for analyzing articles and classifying incidents.

**Quality Control Guidelines**&#x20;

Rules for assessing credibility, handling extraordinary claims, and evaluating source quality.

**Output Format Requirements**&#x20;

JSON structure and formatting specifications.

**Best Practices:**

* Be specific about credibility assessment
* Include source quality indicators
* Flag extraordinary claims
* Provide investigation leads
* Be inclusive rather than restrictive

Actions: Test with Sample Articles, View Examples

***

Important Notes

* Changes affect future analyses only, not existing results
* Use template variables to make prompts dynamic
* Test changes with small datasets before full deployment
* Reset to defaults available in each section

***

### Tips & Tricks

#### Keyboard Shortcuts

* Arrow Keys: Navigate between articles in Reader View
* Esc: Close expanded article cards
* Ctrl/Cmd + Click: Open article in new tab

#### Efficient Filtering

* Start broad, then narrow: Begin with all articles, hide irrelevant ones, then apply filters to refine
* Save common filters: Bookmark your browser page with filter parameters for quick access
* Use entity filters: More precise than topic filters for specific threats

#### Managing Article Overload

* Use pagination for sets over 100 articles
* Hide articles aggressively during first pass
* Focus on sources you trust most
* Set narrower date ranges (3-7 days) for focused research

#### View Mode Selection

* Morning briefing: Use Table View for speed
* Deep research: Use HUD View for context
* Long-form reading: Use Reader View for focus
* Presenting findings: Use Card View for visual clarity

***

### Troubleshooting

**No articles appearing?**

* Verify your date range includes recent dates
* Check that at least one topic is selected
* Clear all filters and try again
* Refresh the page to reload article data

**Articles loading slowly?**

* Narrow your date range (fewer days = faster loading)
* Select fewer topics to reduce result set
* Use paginated mode instead of "Show All"
* Check your internet connection

**Filters not working?**

* Click "Apply" or "Done" after changing filter settings
* Clear browser cache if filters seem stuck
* Try clicking "Clear All" and reapplying filters

**Export not generating?**

* Ensure you have articles loaded before exporting
* Try a smaller date range if export times out
* Check browser's download folder for completed exports
* Disable popup blockers if PDF export fails

### Advanced Features

#### Hidden Articles Management

* View count of hidden articles in toolbar badge
* Click Restore Hidden to unhide all previously hidden articles
* Hidden articles persist during your session but reset on page refresh

#### Multi-Select Operations

* Hold Shift and click to select a range of articles (coming soon)
* Bulk hide or bookmark multiple articles at once (coming soon)

#### Smart Sorting

* Articles automatically sort by relevance and recency
* Most significant threats appear first
* Adjust sorting in filter dropdown (coming soon)
