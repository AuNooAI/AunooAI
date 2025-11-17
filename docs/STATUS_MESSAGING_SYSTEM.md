# Status Messaging System - Complete Documentation

## Overview

The Aunoo AI application implements a comprehensive status messaging system consisting of three main components:

1. **WebSocket Real-Time Updates** - For live progress tracking during long-running operations
2. **Background Task Manager** - For tracking async job status and progress
3. **Database Notifications** - For persistent user notifications

---

## Component 1: WebSocket Real-Time Updates

### File Location
**Location:** `/home/orochford/tenants/multi.aunoo.ai/app/routes/websocket_routes.py`

### Purpose
Provides real-time bidirectional communication channels for progress updates during long-running operations like bulk processing, auto-ingest, and analysis tasks.

### Key Components

#### ConnectionManager Class
```python
class ConnectionManager:
    """Manage WebSocket connections for real-time updates"""
    
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.job_subscribers: Dict[str, List[str]] = {}  # job_id -> list of connection_ids
```

**Responsibilities:**
- Manage active WebSocket connections
- Track job-to-connection subscriptions
- Handle connection lifecycle (connect/disconnect)
- Route messages to subscribers

#### Core Methods

1. **`async def connect(websocket, connection_id)`**
   - Accepts new WebSocket connections
   - Stores connection reference for future communication
   - Logs connection establishment

2. **`def disconnect(connection_id)`**
   - Removes connection from active connections
   - Cleans up job subscriptions for disconnected clients
   - Prevents orphaned resources

3. **`def subscribe_to_job(connection_id, job_id)`**
   - Links a WebSocket connection to a specific job
   - Enables targeted job updates to interested clients
   - Used for monitoring multiple jobs from single connection

4. **`async def send_job_update(job_id, data)`**
   - Broadcasts message to all subscribers of a job
   - Handles disconnected clients gracefully
   - Formats message with timestamp and job metadata

5. **`async def send_direct_message(connection_id, data)`**
   - Sends message to specific connection
   - Used for connection confirmation and direct responses
   - Returns success/failure status

#### WebSocket Endpoints

1. **`/ws/bulk-process/{job_id}`**
   - Purpose: Monitor bulk processing jobs
   - Message Types:
     - `ping` (client) -> `pong` (server): Keep-alive mechanism
     - `get_status` (client) -> `status_request` (server): Status check request
   - Initial Response: Connection confirmation with job_id

2. **`/ws/progress/{topic_id}`**
   - Purpose: Topic-specific progress updates
   - Message Types:
     - `subscribe_job` (client): Subscribe to specific job updates
   - Supports subscribing to multiple jobs within single topic

### Helper Functions (Exported)

```python
async def send_progress_update(job_id: str, progress_data: dict)
# Sends progress update with status: "progress"

async def send_completion_update(job_id: str, results: dict)
# Sends completion update with status: "completed"

async def send_error_update(job_id: str, error: str)
# Sends error update with status: "error"

async def send_batch_update(job_id: str, batch_info: dict)
# Sends batch processing update with status: "batch_update"
```

### Message Format

All WebSocket messages follow this structure:

```json
{
  "type": "job_update|direct_message|status_request|etc",
  "job_id": "string (optional)",
  "timestamp": "ISO 8601 timestamp",
  "status": "connected|progress|completed|error|batch_update|etc",
  "... additional fields specific to message type"
}
```

### Usage Example

**From automated_ingest_service.py (line 435-442):**
```python
if job_id:
    try:
        from app.routes.websocket_routes import send_progress_update
        await send_progress_update(job_id, {
            "progress": 0,
            "processed": 0,
            "total": total_articles,
            "message": f"Starting processing of {total_articles} articles",
            "stage": "initializing"
        })
    except Exception as e:
        self.logger.warning(f"Failed to send WebSocket update: {e}")
```

**From automated_ingest_service.py (line 509-520):**
```python
if job_id:
    try:
        from app.routes.websocket_routes import send_batch_update
        await send_batch_update(job_id, {
            "progress": progress_percentage,
            "processed": processed_count,
            "total": total_articles,
            "batch_completed": batch_number,
            "total_batches": total_batches,
            "message": f"Completed batch {batch_number}/{total_batches}",
            "results": results.copy()
        })
    except Exception as e:
        self.logger.warning(f"Failed to send WebSocket batch update: {e}")
```

---

## Component 2: Background Task Manager

### File Location
**Location:** `/home/orochford/tenants/multi.aunoo.ai/app/services/background_task_manager.py`

### Purpose
Tracks long-running async operations and provides status/progress information without blocking the UI.

### Key Components

#### TaskStatus Enum
```python
class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
```

#### TaskInfo Data Class
```python
@dataclass
class TaskInfo:
    id: str                              # Unique task identifier
    name: str                            # Human-readable task name
    status: TaskStatus                   # Current task status
    created_at: datetime                 # Task creation time
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    progress: float = 0.0                # Progress percentage (0-100)
    total_items: int = 0                 # Total items to process
    processed_items: int = 0             # Items processed so far
    current_item: Optional[str] = None   # Current item being processed
    result: Optional[Dict] = None        # Final result upon completion
    error: Optional[str] = None          # Error message if failed
    metadata: Optional[Dict] = None      # Additional metadata
```

#### BackgroundTaskManager Class

**Core Methods:**

1. **`create_task(name, total_items, metadata)`**
   - Creates new task record
   - Returns unique task_id
   - Initializes task in PENDING state

2. **`async def run_task(task_id, task_func, *args, **kwargs)`**
   - Executes async task function
   - Manages task state transitions
   - Provides progress callback mechanism
   - Handles errors and cancellation

3. **`get_task(task_id)`** / **`get_task_status(task_id)`**
   - Retrieves task info or status dictionary
   - Returns None if task not found

4. **`list_tasks(status=None)`**
   - Returns list of all tasks (optionally filtered by status)
   - Results sorted by creation time (newest first)
   - Each task returned as dictionary (JSON-serializable)

5. **`cancel_task(task_id)`**
   - Cancels running task by cancelling underlying asyncio.Task
   - Returns True if successful, False if task not running
   - Sets task status to CANCELLED

6. **`cleanup_old_tasks(max_age_hours=24)`**
   - Removes completed/failed/cancelled tasks older than specified age
   - Prevents memory accumulation from long-running processes
   - Logs cleanup statistics

7. **`get_task_summary()`**
   - Returns dictionary with counts by status:
     - total, running, pending, completed, failed, cancelled
   - Useful for UI status dashboards

### Progress Callback Mechanism

The `run_task()` method injects a progress callback into task kwargs:

```python
def update_progress(processed: int, current: str = None):
    task_info.processed_items = processed
    task_info.current_item = current
    if task_info.total_items > 0:
        task_info.progress = (processed / task_info.total_items) * 100
```

Tasks can call this to report progress without direct knowledge of task manager.

### API Endpoints

**Location:** `/home/orochford/tenants/multi.aunoo.ai/app/routes/background_tasks.py`

1. **`POST /api/background-tasks/bulk-analysis`**
   - Start bulk analysis task
   - Parameters: urls[], topic, summary_type, model_name, etc.
   - Returns: task_id
   - Internally uses `run_bulk_analysis_task()`

2. **`POST /api/background-tasks/bulk-save`**
   - Start bulk save task
   - Parameters: articles[]
   - Returns: task_id

3. **`GET /api/background-tasks/task/{task_id}`**
   - Get status of specific task
   - Returns: Full TaskInfo as dictionary

4. **`GET /api/background-tasks/tasks`**
   - List all tasks
   - Query Parameter: status (optional)
   - Returns: List of tasks + summary

5. **`DELETE /api/background-tasks/task/{task_id}`**
   - Cancel running task
   - Returns: Success message or error

6. **`GET /api/background-tasks/summary`**
   - Get summary counts
   - Returns: Task summary dictionary

7. **`POST /api/background-tasks/cleanup`**
   - Clean up old tasks
   - Parameter: max_age_hours
   - Returns: Cleanup confirmation

### Wrapper Functions for Common Tasks

1. **`run_bulk_analysis_task(urls, topic, **analysis_params)`**
   - Analyzes multiple articles
   - Uses AnalysisQueue for concurrent processing
   - Creates notifications for completion/errors
   - Returns results dictionary

2. **`run_bulk_save_task(articles)`**
   - Saves articles to database
   - Returns success/error count

3. **`run_auto_ingest_task(progress_callback, username)`**
   - Runs auto-ingest pipeline
   - Creates notifications for completion
   - Supports progress tracking

4. **`run_keyword_check_task(progress_callback, group_id)`**
   - Performs keyword checking
   - Optional group filtering
   - Reports progress and results

---

## Component 3: Database Notifications

### File Locations
- **Routes:** `/home/orochford/tenants/multi.aunoo.ai/app/routes/notification_routes.py`
- **Database Facade:** `/home/orochford/tenants/multi.aunoo.ai/app/database_query_facade.py` (lines 6643-6830)
- **Database Model:** `/home/orochford/tenants/multi.aunoo.ai/app/database_models.py` (lines 700-714)

### Purpose
Persistent user notifications stored in database, viewable across sessions.

### Database Schema

```python
t_notifications = Table(
    'notifications', metadata,
    Column('id', Integer, primary_key=True),
    Column('username', Text, ForeignKey('users.username', ondelete='CASCADE'), nullable=True),
    Column('type', String(50), nullable=False),
    Column('title', String(255), nullable=False),
    Column('message', Text, nullable=False),
    Column('link', String(500), nullable=True),
    Column('read', Boolean, nullable=False, server_default='false'),
    Column('created_at', DateTime, nullable=False, server_default=text('CURRENT_TIMESTAMP')),
    Index('ix_notifications_username', 'username'),
    Index('ix_notifications_read', 'read'),
    Index('ix_notifications_created_at', 'created_at'),
    Index('ix_notifications_username_read', 'username', 'read')
)
```

**Fields:**
- `id`: Unique notification identifier
- `username`: Target user (NULL for system-wide notifications)
- `type`: Notification category (e.g., 'auto_ingest_complete', 'evaluation_complete', 'article_analysis', 'system')
- `title`: Short notification title
- `message`: Full notification message
- `link`: Optional clickable link to related resource
- `read`: Read status (false by default)
- `created_at`: Timestamp with database default

### Facade Methods

1. **`create_notification(username, type, title, message, link=None)`**
   - Creates new notification
   - Returns notification ID
   - Logs creation event
   - Example usage in background tasks (line 348-353 of background_task_manager.py):
     ```python
     db.facade.create_notification(
         username=username,
         type='auto_ingest_complete',
         title='Auto-Collect Complete',
         message=f'Processed {processed} articles. Approved: {ingested}, Failed: {errors}',
         link='/keyword-alerts'
     )
     ```

2. **`get_user_notifications(username, unread_only=False, limit=50)`**
   - Retrieves notifications for user
   - Includes system-wide notifications (username=NULL)
   - Can filter for unread only
   - Returns list of notification dictionaries

3. **`get_unread_count(username)`**
   - Returns count of unread notifications
   - Includes system notifications
   - Useful for badge counts

4. **`mark_notification_as_read(notification_id, username)`**
   - Marks single notification as read
   - Validates ownership
   - Returns True on success

5. **`mark_all_notifications_as_read(username)`**
   - Marks all unread notifications as read for user
   - Returns count of marked notifications

6. **`delete_notification(notification_id, username)`**
   - Deletes notification
   - Validates ownership
   - Returns True on success

7. **`delete_read_notifications(username)`**
   - Bulk deletes all read notifications
   - Helps manage notification clutter
   - Returns count of deleted notifications

### API Endpoints

**Location:** `/home/orochford/tenants/multi.aunoo.ai/app/routes/notification_routes.py`

1. **`GET /api/notifications`**
   - Get notifications for authenticated user
   - Query Parameters:
     - `unread_only` (bool): Filter for unread
     - `limit` (int): Max results (default 50)
   - Returns: { notifications: [], count: int }

2. **`GET /api/notifications/unread-count`**
   - Quick unread count fetch
   - Returns: { count: int }

3. **`POST /api/notifications/{id}/mark-read`**
   - Mark single notification as read
   - Returns: { success: bool }

4. **`POST /api/notifications/mark-all-read`**
   - Mark all notifications as read
   - Returns: { count: int }

5. **`DELETE /api/notifications/{id}`**
   - Delete specific notification
   - Returns: { success: bool }

6. **`DELETE /api/notifications/read`**
   - Delete all read notifications
   - Returns: { count: int }

7. **`POST /api/notifications/create`**
   - Create new notification (admin endpoint)
   - Body: NotificationCreate (username, type, title, message, link)
   - Returns: { notification_id: int }

---

## Integration Points

### Auto-Ingest Service Integration

**File:** `/home/orochford/tenants/multi.aunoo.ai/app/services/automated_ingest_service.py`

The auto-ingest service integrates all three components:

1. **WebSocket Progress Updates** (lines 435-444, 509-520, 554-557, 577-578)
   - Sends progress as articles are processed
   - Provides batch completion updates
   - Notifies on errors

2. **Task Manager** (Used via background_tasks.py)
   - Wraps processing in tracked task
   - Provides job_id for WebSocket subscription

3. **Notifications**
   - Creates notifications for job completion
   - Includes summary of results
   - Links back to relevant UI sections

### Background Task Manager Integration

**File:** `/home/orochford/tenants/multi.aunoo.ai/app/services/background_task_manager.py`

The manager integrates:

1. **Task Tracking**
   - Maintains task state throughout execution
   - Updates progress via callback

2. **Notifications** (lines 348-365)
   - Auto-creates notification on task completion
   - Reports success/failure status
   - Provides user feedback

3. **WebSocket** (Optional)
   - Could be called from task wrappers
   - Not directly integrated, but available to tasks

---

## Connection Manager (HTTP Connections)

**Note:** This is different from WebSocket ConnectionManager

**File:** `/home/orochford/tenants/multi.aunoo.ai/app/services/connection_manager.py`

Purpose: Manages file descriptors and HTTP connections (not status messaging)

**Key Methods:**
- `get_fd_stats()` - Get file descriptor usage
- `cleanup_connections()` - Clean up idle connections
- `check_and_cleanup_if_needed()` - Monitor and clean as needed
- `start_monitoring()` / `stop_monitoring()` - Background monitoring

Not directly related to status messaging but important for system health during long operations.

---

## Analysis Queue (Async Processing)

**File:** `/home/orochford/tenants/multi.aunoo.ai/app/services/analysis_queue.py`

Purpose: Queues and processes multiple analysis tasks concurrently

**Key Components:**
- `AnalysisTask`: Data class representing single article analysis
- `AnalysisQueue`: Queue manager with configurable workers
- Progress tracking via callback
- Result collection and timeout handling

**Integration with Status System:**
- Used by `run_bulk_analysis_task()` wrapper
- Provides progress callbacks to task manager
- Results collected and saved to database

---

## Data Flow Diagram

```
User Initiates Long Operation
         |
         v
Background Task API Endpoint
         |
    +----|----+
    |         |
    v         v
Task Manager  Auto-Ingest Service
    |         |
    +---|-----+
        |
        v
   WebSocket Updates
   (progress, batch, completion, error)
        |
        +----> UI Real-Time Display
        |
        v
   Notifications Created
   (stored in database)
        |
        v
   User Notifications API
        |
        v
   UI Notification Display
```

---

## Configuration & Deployment

### Environment Variables
- Database URL for notifications
- WebSocket configuration (timeout, max connections)
- Task manager limits:
  - `_max_concurrent_tasks = 3` (background_task_manager.py:56)
  - `max_concurrent = 3` (analysis_queue.py:27)
  - `max_queue_size = 100` (analysis_queue.py:30)

### Auto-Ingest Config
- `enabled`: Turn pipeline on/off
- `quality_control_enabled`: Enable quality checks
- `min_relevance_threshold`: Filter threshold
- `batch_size`: Articles per batch
- `max_concurrent_batches`: Parallel batch processing

---

## Common Usage Patterns

### Pattern 1: Simple Background Task
```python
from app.services.background_task_manager import get_task_manager

task_manager = get_task_manager()
task_id = task_manager.create_task("My Task", total_items=100)
# Later...
status = task_manager.get_task_status(task_id)
```

### Pattern 2: Monitor Progress via WebSocket
```javascript
const ws = new WebSocket(`ws://localhost:8000/ws/bulk-process/${jobId}`);
ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    updateUI(data);
};
```

### Pattern 3: Create User Notification
```python
db = get_database_instance()
db.facade.create_notification(
    username="john_doe",
    type="task_complete",
    title="Analysis Complete",
    message="Your analysis has finished",
    link="/results"
)
```

### Pattern 4: Check Unread Notifications
```python
db = get_database_instance()
unread = db.facade.get_unread_count(username)
if unread > 0:
    notifications = db.facade.get_user_notifications(username, unread_only=True)
```

---

## Summary

The status messaging system provides three complementary layers:

1. **Real-Time Updates** via WebSocket for live progress during operations
2. **Task Tracking** via background task manager for non-blocking operations
3. **Persistent Notifications** in database for user awareness across sessions

This multi-layered approach ensures users have both immediate feedback during operations and persistent records of important events.
