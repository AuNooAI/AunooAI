# GitHub Issues for AunooAI

Copy each issue below to create in GitHub.

---

## Issue 1

**Title:** [Docs] Add Docker verification command to installation guide

**Labels:** `documentation`, `good first issue`

**Body:**
### Description
Add a command to verify Docker is running correctly before starting the AunooAI installation.

### Suggested Addition
Add the following to the Docker installation section:

```bash
# Verify Docker is running
docker run hello-world
```

### Location
- README.md
- DOCKER_DEPLOYMENT.md

---

## Issue 2

**Title:** [Ops] Docker port is hardcoded to 10001 - should be configurable

**Labels:** `enhancement`, `docker`, `operations`

**Body:**
### Description
The Docker container port is fixed to 10001. For administrative and deployment flexibility, the port should be configurable via environment variable or docker-compose configuration.

### Expected Behavior
Users should be able to configure the exposed port via:
- Environment variable (e.g., `PORT` or `AUNOO_PORT`)
- docker-compose.yml configuration

### Current Behavior
Port is hardcoded to 10001.

### Impact
- Cannot run multiple instances on same host
- May conflict with other services
- Inflexible for different deployment environments

---

## Issue 3

**Title:** [Bug] 500 error "Failed to initialize collector" when clicking Update Now in Gather

**Labels:** `bug`, `critical`, `collector`

**Body:**
### Description
After creating a topic in Settings -> Topic Editor, clicking "Update Now" in Gather results in a 500 error. The error persists even after deleting all topics.

### Steps to Reproduce
1. Go to Settings -> Topic Editor
2. Create a new topic
3. Go to Gather
4. Click "Update Now"
5. Observe 500 error

### Error Log
```
File "/app/app/routes/keyword_monitor.py", line 307, in check_now
    raise HTTPException(status_code=500, detail=result.get('error', 'Unknown error'))
fastapi.exceptions.HTTPException: 500: Failed to initialize collector
```

### Expected Behavior
The collector should initialize and fetch articles for the configured topic.

### Additional Context
This issue may be related to #[NewsAPI/TheNewsAPI mismatch issue number] - the backend appears to be looking for the wrong provider.

---

## Issue 4

**Title:** [Bug] Discord invite link does not work from web browser

**Labels:** `bug`, `community`, `low-priority`

**Body:**
### Description
The Discord invite link (https://discord.com/invite/hEUNYDm5KH) does not work when accessed from a web browser, but works correctly when opened in the Discord app.

### Steps to Reproduce
1. Click Discord invite link from documentation/website
2. Open in web browser
3. Invite fails or shows error

### Expected Behavior
Link should work in both web browser and Discord app.

### Workaround
Open the link directly in the Discord application.

---

## Issue 5

**Title:** [Bug] Dark Mode toggle has no effect

**Labels:** `bug`, `ui`, `frontend`

**Body:**
### Description
The Dark Mode setting in the UI does not apply any visual changes. The toggle appears functional but is a no-op.

### Steps to Reproduce
1. Open Settings or find Dark Mode toggle
2. Enable Dark Mode
3. Observe no visual change

### Expected Behavior
UI should switch to dark color scheme when Dark Mode is enabled.

### Technical Notes
- Check if dark mode CSS/styles are implemented
- Verify theme state is being applied to components
- Check React context/state management for theme

---

## Issue 6

**Title:** [Feature] Add password reset functionality and documentation

**Labels:** `enhancement`, `security`, `access-management`

**Body:**
### Description
There is no documented process for resetting a forgotten password. Currently, if an admin forgets their password, they must reinstall the entire application.

### Expected Behavior
- Admin should be able to reset password via CLI command
- OR self-service password reset via email
- At minimum, documentation for manual database password reset

### Suggested Solutions

**Option 1: CLI Script**
```bash
python scripts/reset_password.py --username admin
```

**Option 2: Documentation for manual reset**
Document how to update password hash directly in PostgreSQL:
```sql
UPDATE users SET hashed_password = '...' WHERE username = 'admin';
```

### Impact
- Security concern if admins resort to weak passwords to avoid lockout
- Poor user experience
- Unnecessary reinstallation wastes time and data

---

## Issue 7

**Title:** [Bug] NewsAPI configuration uses wrong provider (TheNewsAPI) in backend

**Labels:** `bug`, `critical`, `collector`, `configuration`

**Body:**
### Description
When configuring "NewsAPI" in the UI, the backend attempts to initialize "thenewsapi" collector instead, causing collector initialization to fail.

### Steps to Reproduce
1. Go to Settings -> Providers
2. Configure NewsAPI with valid API key
3. Observe UI shows "NewsAPI - Configured"
4. Trigger article collection (Gather -> Update Now)
5. Check logs - backend searches for `thenewsapi` instead of `newsapi`

### Error Log
```
2025-12-01 17:47:07,722 - app.tasks.keyword_monitor - INFO - Initializing collectors for providers: ['thenewsapi']
2025-12-01 17:47:07,722 - app.collectors.thenewsapi_collector - ERROR - TheNewsAPI key not found in environment
2025-12-01 17:47:07,722 - app.tasks.keyword_monitor - ERROR - ✗ Failed to initialize thenewsapi: TheNewsAPI key not configured
2025-12-01 17:47:07,722 - app.tasks.keyword_monitor - ERROR - No collectors were initialized successfully
```

### Expected Behavior
- Configuring "NewsAPI" should use `newsapi_collector`
- Provider name mapping should be consistent between UI and backend

### Root Cause Investigation
Check:
- `app/tasks/keyword_monitor.py` - provider initialization
- `app/collectors/collector_factory.py` - provider name mapping
- Provider configuration storage (database or settings)

---

## Issue 8

**Title:** [Feature] Add "Test Connection" button for provider configuration

**Labels:** `enhancement`, `ui`, `ux`, `configuration`

**Body:**
### Description
When configuring API providers (NewsAPI, OpenAI, Anthropic, etc.), there is no way to verify the configuration is correct. Users must trigger an action and check logs to confirm.

### Expected Behavior
Each provider configuration should have a "Test" or "Verify" button that:
1. Validates API key format
2. Makes a test API call to the provider
3. Shows success/failure message in the UI

### Example UI
```
NewsAPI    [API Key: ****1234]    [Test] [Save] [Remove]
                                   ✓ Connection successful
```

### Benefits
- Immediate feedback on configuration errors
- No need to check container logs
- Better user experience
- Reduces support requests

---

## Issue 9

**Title:** [Bug] Provider configuration errors not displayed in UI

**Labels:** `bug`, `ui`, `error-handling`

**Body:**
### Description
When a provider is misconfigured (e.g., invalid API key), no error is shown in the UI. Errors only appear in container logs, making debugging difficult for users.

### Steps to Reproduce
1. Configure a provider with an invalid API key
2. Save configuration
3. UI shows "Configured" status (no error)
4. Trigger collection
5. Check container logs to see actual error

### Error Log (only visible in container)
```
2025-12-01 17:45:14,082 - app.collectors.thenewsapi_collector - ERROR - TheNewsAPI HTTP ERROR
2025-12-01 17:45:14,082 - app.collectors.thenewsapi_collector - ERROR - Status Code: 401
2025-12-01 17:45:14,083 - app.collectors.thenewsapi_collector - ERROR - Error Response (JSON): {'error': {'code': 'invalid_api_token', 'message': 'An invalid API token was supplied.'}}
```

### Expected Behavior
- Configuration errors should be surfaced in the UI
- Provider status should show "Error" or "Invalid" when API calls fail
- Error message should be displayed to user

### Technical Notes
- Add error state to provider configuration UI
- Return validation errors from backend API
- Consider periodic health checks for configured providers

---

## Summary Table

| Issue | Title | Priority | Labels |
|-------|-------|----------|--------|
| 1 | Docker verification docs | Low | documentation |
| 2 | Configurable Docker port | Medium | enhancement, docker |
| 3 | 500 error on Update Now | Critical | bug, collector |
| 4 | Discord link broken | Low | bug, community |
| 5 | Dark Mode no-op | Low | bug, ui |
| 6 | Password reset feature | Medium | enhancement, security |
| 7 | NewsAPI/TheNewsAPI mismatch | Critical | bug, collector |
| 8 | Add Test button for providers | Medium | enhancement, ui |
| 9 | Provider errors not in UI | Medium | bug, error-handling |

**Recommended Fix Order:** 7 → 3 → 8 → 9 → 6 → 2 → 5 → 1 → 4
