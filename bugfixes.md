# Bug Fixes

## 2025-04-03: Fixed Tag Deletion Character Issue in Onboarding Wizard

### Issue
When users added tags in the onboarding wizard (step 2), the "×" deletion character was being treated as part of the tag text and saved to the database. For example, a tag like "Data Sovereignty" was being saved as "Data Sovereignty×".

### Root Cause
The issue was in the tag creation and retrieval process in the onboarding wizard:

1. When creating tags, the HTML was being set directly with `innerHTML`, which included both the tag value and the "×" remove button:
   ```javascript
   tag.innerHTML = `${value}<span class="remove">×</span>`;
   ```

2. When retrieving tags to save them, the code was using `textContent.trim()` which captured all text content including the "×" character:
   ```javascript
   function getTagsFromContainer(containerId) {
       const container = document.getElementById(containerId);
       const tags = [];
       container.querySelectorAll('.tag').forEach(tag => {
           tags.push(tag.textContent.trim());
       });
       return tags;
   }
   ```

### Fix
1. Modified the tag creation process to properly separate the tag value from the remove button:
   ```javascript
   function addTag(value) {
       if (tags.has(value)) return;
       tags.add(value);
       
       const tag = document.createElement('span');
       tag.className = 'tag';
       tag.setAttribute('data-value', value);
       
       // Create a text node for the value
       const textNode = document.createTextNode(value);
       tag.appendChild(textNode);
       
       // Create the remove button as a separate element
       const removeBtn = document.createElement('span');
       removeBtn.className = 'remove';
       removeBtn.textContent = '×';
       tag.appendChild(removeBtn);
       
       // ... rest of the function
   }
   ```

2. Updated the tag retrieval functions to use the data attribute instead of text content:
   ```javascript
   function getTagsFromContainer(containerId) {
       const container = document.getElementById(containerId);
       const tags = [];
       container.querySelectorAll('.tag').forEach(tag => {
           // Use the data-value attribute instead of textContent
           tags.push(tag.getAttribute('data-value'));
       });
       return tags;
   }
   ```

### Impact
- Tags are now saved correctly without the "×" character
- The visual appearance and functionality of the tags remain unchanged
- Existing data with the "×" character will need to be cleaned up separately

## 2025-04-03: Fixed Onboarding Reset Functionality

### Issue
When a user tried to reset the onboarding wizard, the following error occurred:
```
Error resetting onboarding: no such column: completed_onboarding
```

### Root Cause
There was a schema mismatch between different parts of the application that define the `users` table:

1. In `app/database.py`, the `users` table was defined with a `completed_onboarding` column:
   ```sql
   CREATE TABLE IF NOT EXISTS users (
       username TEXT PRIMARY KEY,
       password_hash TEXT NOT NULL,
       force_password_change BOOLEAN DEFAULT 0,
       completed_onboarding BOOLEAN DEFAULT 0
   )
   ```

2. In `app/utils/update_admin.py`, the `users` table was defined differently:
   ```sql
   CREATE TABLE IF NOT EXISTS users (
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       username TEXT UNIQUE,
       password_hash TEXT,
       force_password_change INTEGER DEFAULT 0,
       completed_onboarding INTEGER DEFAULT 0
   )
   ```

The existing database had the schema from `database.py` (with `username` as PRIMARY KEY), but the `completed_onboarding` column was missing from the actual database.

### Fix
1. Added a database migration function `_ensure_completed_onboarding` to check for and add the missing column:
   ```python
   def _ensure_completed_onboarding(self, cursor):
       """Ensure the completed_onboarding column exists in the users table"""
       try:
           # First check if the users table exists
           cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
           if not cursor.fetchone():
               logger.info("Creating users table with completed_onboarding column")
               cursor.execute("""
                   CREATE TABLE IF NOT EXISTS users (
                       username TEXT PRIMARY KEY,
                       password_hash TEXT NOT NULL,
                       force_password_change BOOLEAN DEFAULT 0,
                       completed_onboarding BOOLEAN DEFAULT 0
                   )
               """)
               return
               
           # Check if the column exists
           cursor.execute("PRAGMA table_info(users)")
           columns = [col[1] for col in cursor.fetchall()]
           
           if 'completed_onboarding' not in columns:
               logger.info("Adding completed_onboarding column to users table")
               cursor.execute("ALTER TABLE users ADD COLUMN completed_onboarding BOOLEAN DEFAULT 0")
               
       except Exception as e:
           logger.error(f"Error ensuring completed_onboarding column: {str(e)}")
           raise
   ```

2. Added the migration to the list of migrations to be applied:
   ```python
   migrations = [
       # ... existing migrations ...
       ("ensure_completed_onboarding", self._ensure_completed_onboarding),
   ]
   ```

3. Also fixed an import error in `app/main.py`:
   - Changed `from config.settings import config` to `from app.config.settings import config`

### Impact
- The onboarding reset functionality now works properly
- The database schema is consistent across the application
- The application starts up correctly with the fixed import path

### Recommendations
1. Consider implementing a more robust database migration system
2. Ensure consistent table definitions across the codebase
3. Add tests to verify database schema integrity

## 2025-04-03: Fixed Create/Update Topic Button Functionality

### Issue
The "Create/Update" button in the create_topic.html template was not functioning. When clicked, it did not trigger any action or form submission.

### Root Cause
The issue was that the form container was using a `<div>` element with an ID of "createTopicForm" instead of a proper HTML `<form>` element. While there was JavaScript code that correctly added an event listener to handle the form submission, a div cannot naturally trigger a submit event like a form element can.

```html
<!-- Original problematic code -->
<div id="createTopicForm" class="mt-4">
    <!-- Form fields -->
    <button type="submit" class="btn btn-primary mt-3">Create/Update Topic</button>
</div>
```

### Fix
Modified the HTML structure by changing the container from a div to a proper form element:

```html
<!-- Fixed code -->
<form id="createTopicForm" class="mt-4">
    <!-- Form fields -->
    <button type="submit" class="btn btn-primary mt-3">Create/Update Topic</button>
</form>
```

### Impact
- The Create/Update Topic button now properly triggers the form submission event
- Users can now successfully create new topics and update existing ones
- The existing JavaScript event listener works as intended without any modifications
