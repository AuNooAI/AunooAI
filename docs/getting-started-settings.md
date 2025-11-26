# Settings Overview

## App Configuration

**Settings → App Configuration**

Manage core system settings across six tabs:

### Providers
Configure news collection services (NewsAPI, TheNewsAPI, etc.) and web scraping tools (Firecrawl). Add API keys and enable/disable providers.

### AI Models
Set up AI model providers (OpenAI, Anthropic, Google Gemini). Configure API keys and select which models to use for article analysis, summarization, and enrichment.

### Database
View current database type (PostgreSQL or SQLite), connection status, and health metrics. Download backups (SQLite only) or view connection details (PostgreSQL).

### Datasets
Manage reference datasets like media bias ratings, organization profiles, and threat actor information. Upload CSV files to update datasets or create custom ones.

### Security
Configure password policies, session timeouts, and API rate limits. View security audit logs and manage access controls.

### Users
Add/remove users, assign roles, and manage permissions. View user activity and last login times.

---

## AI-Guided Topic Setup

**Settings → AI-guided Topic Setup** or click "Set up topic" button anywhere

A 3-step wizard that helps you configure new topic monitoring:

**Step 1: API Keys** (auto-skipped if already configured)
- Configure AI provider keys (OpenAI, Anthropic, Gemini)
- Configure news provider keys (NewsAPI, TheNewsAPI, etc.)
- Configure Firecrawl for web scraping

**Step 2: Topic Setup**
- Enter a topic name (e.g., "APT28 Campaigns")
- Provide a description of what you want to monitor
- AI suggests relevant keywords based on your topic

**Step 3: Keywords**
- Review AI-suggested keywords
- Add/remove/edit keywords as needed
- Keywords are used by Gather for automated collection

**When to Use:**
- Setting up your first topics
- Adding new threat categories to monitor
- Getting AI help with keyword brainstorming

---

## Topic Editor

**Settings → Topic Editor**

Manually create and manage topics without the wizard:

- **Create Topics**: Add new categories like "Ransomware", "APT Groups", "Critical Vulnerabilities"
- **Edit Topics**: Change names, descriptions, or associated keywords
- **Delete Topics**: Remove unused topics
- **View Topics**: See all configured topics and their keyword counts

**Use Topic Editor when:**
- You know exactly what keywords you want (no AI help needed)
- Editing existing topics
- Reorganizing your topic structure

---

## Quick Reference

| Task | Go To |
|------|-------|
| Add API keys | App Configuration → Providers or AI Models |
| Set up new monitoring topic (with AI help) | AI-guided Topic Setup |
| Set up new topic manually | Topic Editor |
| View database status | App Configuration → Database |
| Update media bias data | App Configuration → Datasets |
| Manage users | App Configuration → Users |
| Change password policy | App Configuration → Security |

---

*Last updated: 2025-11-25*
