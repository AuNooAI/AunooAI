# Status Messaging System Architecture

## High-Level System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           CLIENT APPLICATIONS                               │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐          │
│  │   Web UI         │  │   Mobile App     │  │   Admin Panel    │          │
│  │  (React/JS)      │  │  (WebSocket)     │  │  (WebSocket)     │          │
│  └────────┬─────────┘  └────────┬─────────┘  └────────┬─────────┘          │
└───────────┼──────────────────────┼──────────────────────┼───────────────────┘
            │                      │                      │
            │ HTTP API Calls       │ WebSocket Conns      │ HTTP API Calls
            │                      │                      │
┌───────────┼──────────────────────┼──────────────────────┼───────────────────┐
│           │        FASTAPI SERVER                        │                   │
│           │                      │                      │                   │
│  ┌────────▼───────────────────────────────────────────▼────────┐            │
│  │           API ROUTES / WebSocket Handlers                    │            │
│  │  ┌────────────────────┬─────────────────────────────────┐   │            │
│  │  │ /api/background-   │  /ws/bulk-process/{job_id}     │   │            │
│  │  │ tasks/*            │  /ws/progress/{topic_id}       │   │            │
│  │  │                    │                                 │   │            │
│  │  │ /api/notifications │  WebSocket Connection Manager  │   │            │
│  │  │ /*                 │                                 │   │            │
│  │  └────────────────────┴─────────────────────────────────┘   │            │
│  └──────────┬───────────────────────────┬────────────────────────┘            │
│             │                           │                                     │
│  ┌──────────▼─────────────────┐  ┌──────▼──────────────────────────────────┐ │
│  │  BACKGROUND TASK MANAGER   │  │   WEBSOCKET MANAGER                    │ │
│  │  ┌──────────────────────┐  │  │   ┌────────────────────────────────┐  │ │
│  │  │ TaskStatus Enum      │  │  │   │ ConnectionManager              │  │ │
│  │  │ PENDING              │  │  │   │ - active_connections          │  │ │
│  │  │ RUNNING              │  │  │   │ - job_subscribers             │  │ │
│  │  │ COMPLETED            │  │  │   │                               │  │ │
│  │  │ FAILED               │  │  │   │ send_progress_update()       │  │ │
│  │  │ CANCELLED            │  │  │   │ send_completion_update()     │  │ │
│  │  └──────────────────────┘  │  │   │ send_error_update()          │  │ │
│  │  ┌──────────────────────┐  │  │   │ send_batch_update()          │  │ │
│  │  │ TaskInfo DataClass   │  │  │   └────────────────────────────────┘  │ │
│  │  │ - id                 │  │  │   ┌────────────────────────────────┐  │ │
│  │  │ - name               │  │  │   │ Message Format                 │  │ │
│  │  │ - status             │  │  │   │ {                              │  │ │
│  │  │ - progress           │  │  │   │   "type": "job_update",       │  │ │
│  │  │ - processed_items    │  │  │   │   "job_id": "...",            │  │ │
│  │  │ - total_items        │  │  │   │   "timestamp": "ISO 8601",    │  │ │
│  │  │ - result/error       │  │  │   │   "status": "progress|...",   │  │ │
│  │  │ - metadata           │  │  │   │   "progress": 45.5,           │  │ │
│  │  └──────────────────────┘  │  │   │   "message": "..."            │  │ │
│  │  ┌──────────────────────┐  │  │   │ }                              │  │ │
│  │  │ API Methods          │  │  │   └────────────────────────────────┘  │ │
│  │  │ create_task()        │  │  │                                        │ │
│  │  │ run_task()           │  │  │                                        │ │
│  │  │ get_task_status()    │  │  │                                        │ │
│  │  │ list_tasks()         │  │  │                                        │ │
│  │  │ cancel_task()        │  │  │                                        │ │
│  │  │ cleanup_old_tasks()  │  │  │                                        │ │
│  │  │ get_task_summary()   │  │  │                                        │ │
│  │  └──────────────────────┘  │  │                                        │ │
│  └───────────┬────────────────┘  └────────────────────────────────────────┘ │
│              │                                                               │
│  ┌───────────▼────────────────────────────────────────────────────────────┐ │
│  │        SERVICE LAYER                                                    │ │
│  │  ┌──────────────────────┬─────────────────────────────────────────┐   │ │
│  │  │ Auto-Ingest Service  │  Analysis Queue                        │   │ │
│  │  │ ┌──────────────────┐ │  ┌────────────────────────────────┐    │   │ │
│  │  │ │ run_auto_ingest()│ │  │ AnalysisTask                   │    │   │ │
│  │  │ │ process_articles │ │  │ - url                          │    │   │ │
│  │  │ │ _batch()         │ │  │ - topic                        │    │   │ │
│  │  │ │ get_pending_     │ │  │ - metadata                     │    │   │ │
│  │  │ │ articles()       │ │  │                                │    │   │ │
│  │  │ │                  │ │  │ AnalysisQueue                  │    │   │ │
│  │  │ │ WebSocket        │ │  │ - task_queue                   │    │   │ │
│  │  │ │ Integration:     │ │  │ - result_queue                 │    │   │ │
│  │  │ │ - progress       │ │  │ - workers[]                    │    │   │ │
│  │  │ │ - batch updates  │ │  │ - max_concurrent = 3           │    │   │ │
│  │  │ │ - completion     │ │  │ - max_queue_size = 100         │    │   │ │
│  │  │ │ - errors         │ │  │                                │    │   │ │
│  │  │ └──────────────────┘ │  │ async add_tasks()              │    │   │ │
│  │  │                      │  │ async wait_completion()        │    │   │ │
│  │  │ Notification         │  │ get_progress()                 │    │   │ │
│  │  │ Integration:         │  └────────────────────────────────┘    │   │ │
│  │  │ - auto_ingest_      │                                         │   │ │
│  │  │   complete          │                                         │   │ │
│  │  │ - auto_ingest_error │                                         │   │ │
│  │  └──────────────────────┘                                         │   │ │
│  └────────────────────────────────────────────────────────────────────┘   │ │
│              │                                                               │
│  ┌───────────▼────────────────────────────────────────────────────────────┐ │
│  │        DATABASE LAYER                                                   │ │
│  │  ┌──────────────────────────────────────────────────────────────────┐  │ │
│  │  │ Database Query Facade                                            │  │ │
│  │  │  ┌────────────────────────────────────────────────────────────┐ │  │ │
│  │  │  │ Notification Methods                                       │ │  │ │
│  │  │  │ create_notification()                                      │ │  │ │
│  │  │  │ get_user_notifications()                                   │ │  │ │
│  │  │  │ get_unread_count()                                         │ │  │ │
│  │  │  │ mark_notification_as_read()                                │ │  │ │
│  │  │  │ mark_all_notifications_as_read()                           │ │  │ │
│  │  │  │ delete_notification()                                      │ │  │ │
│  │  │  │ delete_read_notifications()                                │ │  │ │
│  │  │  └────────────────────────────────────────────────────────────┘ │  │ │
│  │  └──────────────────────────────────────────────────────────────────┘  │ │
│  └────────┬─────────────────────────────────────────────────────────────────┘ │
│           │                                                                   │
└───────────┼───────────────────────────────────────────────────────────────────┘
            │
            │ SQL Queries
            │
┌───────────▼──────────────────────────────────────────────────────────────┐
│                    POSTGRESQL DATABASE                                    │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │ Table: notifications                                               │  │
│  │  id (int, PK)                                                      │  │
│  │  username (text, FK to users, nullable)                            │  │
│  │  type (varchar(50))                                                │  │
│  │  title (varchar(255))                                              │  │
│  │  message (text)                                                    │  │
│  │  link (varchar(500), nullable)                                     │  │
│  │  read (bool, default=false)                                        │  │
│  │  created_at (datetime, default=CURRENT_TIMESTAMP)                  │  │
│  │                                                                    │  │
│  │  Indexes:                                                          │  │
│  │  - ix_notifications_username                                       │  │
│  │  - ix_notifications_read                                           │  │
│  │  - ix_notifications_created_at                                     │  │
│  │  - ix_notifications_username_read                                  │  │
│  └────────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────────────┘
```

## Data Flow: Auto-Ingest Operation

```
┌─────────────────┐
│  User Clicks    │
│  "Run Auto      │
│  Collect"       │
└────────┬────────┘
         │
         ▼
┌──────────────────────────────────────┐
│ POST /api/auto-ingest/run            │
│ (or background-tasks endpoint)       │
└────────┬─────────────────────────────┘
         │
         ├─────────────────────────────────┐
         │                                 │
         ▼                                 ▼
┌──────────────────────┐      ┌──────────────────────┐
│ Create Task ID       │      │ Start Auto-Ingest    │
│ (task manager)       │      │ Service              │
│ Returns: task_id     │      │ Process Articles     │
└──────────────────────┘      └──────────┬───────────┘
         │                              │
         │                    ┌─────────▼──────────┐
         │                    │ For Each Article   │
         │                    │ - Analyze          │
         │                    │ - Check Relevance  │
         │                    │ - Assess Quality   │
         │                    │ - Save to DB       │
         │                    └────────┬───────────┘
         │                             │
         │        ┌────────────────────┼────────────────────┐
         │        │                    │                    │
         │        ▼                    ▼                    ▼
         │   ┌────────────┐      ┌────────────┐      ┌─────────────┐
         │   │ WebSocket  │      │ Task Info  │      │ Notification│
         │   │ Updates    │      │ Updated    │      │ Created     │
         │   │            │      │            │      │             │
         │   │ progress   │      │ progress%  │      │ type:       │
         │   │ processed  │      │ processed_ │      │ auto_ingest_│
         │   │ total      │      │ items      │      │ complete    │
         │   │ message    │      │ status     │      │ title: .... │
         │   │ stage      │      │ result     │      │ message: .. │
         │   │            │      │            │      │ link: /kw.. │
         │   └────────────┘      └────────────┘      └─────────────┘
         │        │                    │                    │
         │        │                    │                    ▼
         │        │                    │             ┌────────────────┐
         │        │                    │             │ Store in DB    │
         │        │                    │             │ notifications  │
         │        │                    │             │ table          │
         │        │                    │             └────────────────┘
         │        │                    │
         │        ▼                    ▼
         │   ┌─────────────────────────────────┐
         │   │ Client WebSocket Handler        │
         │   │ onmessage:                      │
         │   │ - Update Progress Bar           │
         │   │ - Show Current Article          │
         │   │ - Display Results as Received   │
         │   └─────────────────────────────────┘
         │
         └──────────────┬───────────────────────┐
                        │                       │
                        ▼                       ▼
              ┌────────────────────┐  ┌──────────────────┐
              │ Polling Option     │  │ WebSocket Option │
              │                    │  │                  │
              │ GET /api/          │  │ ws://server/ws/  │
              │ background-tasks/  │  │ bulk-process/    │
              │ task/{task_id}     │  │ {job_id}         │
              │                    │  │                  │
              │ Returns: Task info │  │ Real-time msgs   │
              │ with current       │  │ with timestamps  │
              │ progress           │  │                  │
              └────────────────────┘  └──────────────────┘
                        │                       │
                        ▼                       ▼
              ┌────────────────────┐  ┌──────────────────┐
              │ UI Updates         │  │ UI Updates       │
              │ Status: COMPLETED  │  │ Status: COMPLETED│
              │ Progress: 100%     │  │ Progress: 100%   │
              └────────────────────┘  └──────────────────┘
```

## Component Interactions

### 1. WebSocket to Task Manager Flow

```
Client Opens WebSocket
    ↓
/ws/bulk-process/{job_id} handler
    ↓
ConnectionManager.connect(ws, connection_id)
    ↓
ConnectionManager.subscribe_to_job(connection_id, job_id)
    ↓
Auto-Ingest Service Processing
    ├─→ send_progress_update(job_id, {...})
    │   └─→ ConnectionManager.send_job_update(job_id, data)
    │       └─→ Send to all subscribers of job_id
    │
    ├─→ send_batch_update(job_id, {...})
    │   └─→ Same as above
    │
    └─→ send_completion_update(job_id, results)
        └─→ Send final update with results
    
Client Receives Updates
    ↓
Update UI Progress Bar
Update Results Display
Close WebSocket (Optional)
```

### 2. Background Task Tracking Flow

```
API Request
    ↓
BackgroundTaskManager.create_task()
    │
    └─→ Create TaskInfo(status=PENDING)
        └─→ Store in _tasks dict
        └─→ Return task_id
    ↓
BackgroundTasks.add_task()
    ├─→ Queue task execution
    ├─→ Inject progress_callback
    └─→ Return immediately
    ↓
Task Execution (Background)
    ├─→ TaskInfo.status = RUNNING
    ├─→ Call task_func() with progress_callback
    │   └─→ Task calls progress_callback() updates
    │       └─→ Updates TaskInfo.progress, processed_items
    │
    ├─→ On Success:
    │   ├─→ TaskInfo.status = COMPLETED
    │   ├─→ TaskInfo.result = {...}
    │   └─→ Create Notification
    │
    ├─→ On Error:
    │   ├─→ TaskInfo.status = FAILED
    │   ├─→ TaskInfo.error = error_msg
    │   └─→ Create Error Notification
    │
    └─→ On Cancel:
        ├─→ TaskInfo.status = CANCELLED
        └─→ Log cancellation
    ↓
Client Polls Status
    ↓
GET /api/background-tasks/task/{task_id}
    │
    └─→ BackgroundTaskManager.get_task_status(task_id)
        └─→ Return TaskInfo as JSON dict
    ↓
Client Receives Latest Status
    ├─→ If RUNNING: Show progress
    ├─→ If COMPLETED: Show results
    └─→ If FAILED: Show error message
```

### 3. Notification Creation & Delivery Flow

```
Auto-Ingest Task Completes
    ↓
db.facade.create_notification(
    username="john",
    type="auto_ingest_complete",
    title="Auto-Collect Complete",
    message="...",
    link="/keyword-alerts"
)
    ↓
INSERT into notifications table
    │
    └─→ Set created_at = NOW()
    └─→ Set read = false
    ↓
Return notification_id
    ↓
Later: User Opens Notification Panel
    ↓
GET /api/notifications?unread_only=true
    ├─→ db.facade.get_user_notifications()
    │   └─→ Query notifications where:
    │       - (username=user OR username=NULL)
    │       - read=false
    │       - Ordered by created_at DESC
    │
    └─→ Return list of notifications
    ↓
User Clicks Notification
    ↓
POST /api/notifications/{id}/mark-read
    ├─→ UPDATE notifications SET read=true
    │   WHERE id={id} AND (username=user OR username=NULL)
    │
    └─→ Return success
    ↓
Notification Marked as Read
    ├─→ UI removes from unread count
    └─→ Notification still visible in history
```

## State Diagram: Task Lifecycle

```
┌────────┐
│PENDING │
└───┬────┘
    │ .run_task() called
    │
    ▼
┌────────┐
│RUNNING │
└───┬────┘
    │
    ├────────────────────┬────────────────────┬──────────────────┐
    │                    │                    │                  │
    │ Success            │ Error              │ Cancellation     │
    │ (task completes)   │ (exception)        │ (.cancel_task()) │
    │                    │                    │                  │
    ▼                    ▼                    ▼                  ▼
┌─────────┐          ┌────────┐          ┌──────────┐
│COMPLETED│          │ FAILED │          │CANCELLED │
└──────┬──┘          └───┬────┘          └──────┬───┘
       │                 │                      │
       │ (optional)      │ (optional)           │ (optional)
       │ Task remains in │ Task remains in      │ Task remains in
       │ memory until:   │ memory until:        │ memory until:
       │ 1) Cleanup      │ 1) Cleanup request   │ 1) Cleanup request
       │ 2) Expiration   │ 2) Expiration        │ 2) Expiration
       │    (24h)        │    (24h)             │    (24h)
       │                 │                      │
       ▼                 ▼                      ▼
    ┌──────────────────────────────────────────────┐
    │ DELETED from BackgroundTaskManager._tasks    │
    │ (via cleanup_old_tasks())                    │
    └──────────────────────────────────────────────┘
```

## Concurrency & Resource Management

```
BackgroundTaskManager
    │
    ├─→ _max_concurrent_tasks = 3
    │   (Prevents more than 3 tasks from RUNNING state)
    │
    └─→ _running_tasks: Dict[str, asyncio.Task]
        (Tracks active asyncio tasks)

AnalysisQueue (For Bulk Analysis)
    │
    ├─→ max_concurrent = 3
    │   (Worker pool size)
    │
    ├─→ max_queue_size = 100
    │   (Max tasks queued)
    │
    └─→ workers: List[asyncio.Task]
        (Background worker tasks)

WebSocket Manager
    │
    ├─→ active_connections: Dict[str, WebSocket]
    │   (Tracks open connections)
    │
    └─→ job_subscribers: Dict[str, List[str]]
        (Tracks subscriptions: job_id → [connection_ids])
```

## API Response Patterns

```
Task Creation:
{
    "success": true,
    "task_id": "550e8400-e29b-41d4-a716-446655440000",
    "message": "Started..."
}

Status Query:
{
    "success": true,
    "task": {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "name": "Bulk Analysis",
        "status": "running",
        "progress": 45.5,
        "processed_items": 450,
        "total_items": 1000,
        "current_item": "article-123",
        "created_at": "2024-11-10T10:00:00",
        "started_at": "2024-11-10T10:01:00",
        "completed_at": null,
        "result": null,
        "error": null,
        "metadata": {...}
    }
}

List Tasks:
{
    "success": true,
    "tasks": [...],  // Array of task objects
    "summary": {
        "total": 5,
        "running": 1,
        "pending": 2,
        "completed": 1,
        "failed": 1,
        "cancelled": 0
    }
}

Get Notifications:
{
    "notifications": [
        {
            "id": 123,
            "username": "john",
            "type": "auto_ingest_complete",
            "title": "Auto-Collect Complete",
            "message": "Processed 100 articles...",
            "link": "/keyword-alerts",
            "read": false,
            "created_at": "2024-11-10T10:30:00"
        }
    ],
    "count": 5
}
```

## Error Handling & Recovery

```
WebSocket Disconnection
    │
    ├─→ ConnectionManager.disconnect() called
    │   ├─→ Remove from active_connections
    │   ├─→ Remove from all job_subscribers
    │   └─→ Log disconnection
    │
    └─→ send_job_update() detects missing connection
        └─→ Removes from subscribers list
           (Graceful cleanup)

Task Timeout
    │
    ├─→ asyncio.wait_for() timeout triggers
    │   └─→ Cancels asyncio task
    │
    └─→ Task status set to FAILED
        ├─→ Error message recorded
        └─→ Notification sent

Failed Database Operation
    │
    ├─→ _execute_with_rollback() catches exception
    │   └─→ Rolls back transaction
    │
    └─→ Logger records error
        └─→ Caller receives exception
```

## Performance Characteristics

| Operation | Time Complexity | Space Complexity | Notes |
|-----------|-----------------|------------------|-------|
| create_task() | O(1) | O(1) | UUID generation + dict insert |
| get_task_status() | O(1) | O(1) | Dict lookup |
| list_tasks() | O(n) | O(n) | n = total tasks in memory |
| cancel_task() | O(1) | O(1) | asyncio.Task.cancel() |
| send_job_update() | O(m) | O(m) | m = subscribers for job |
| create_notification() | O(1) | O(1) | Single DB insert |
| get_user_notifications() | O(log n) | O(k) | n = total notifications, k = results |

## Security Boundaries

```
┌─────────────────────────────────────┐
│      Unauthenticated Endpoints      │
│  /ws/bulk-process/{job_id}          │
│  /ws/progress/{topic_id}            │
│  GET /api/background-tasks/*        │
│  POST /api/background-tasks/*       │  ⚠️  No user scoping!
│  DELETE /api/background-tasks/*     │
└─────────────────────────────────────┘
                 ↓
        SECURITY CONSIDERATION:
    Anyone can view/cancel any task


┌─────────────────────────────────────┐
│    Authenticated Endpoints          │
│  GET /api/notifications             │
│  GET /api/notifications/unread-...  │  ✓  Session verified
│  POST /api/notifications/{id}/...   │  ✓  User scoped
│  DELETE /api/notifications/*        │
│  POST /api/auto-ingest/run          │
└─────────────────────────────────────┘
```

