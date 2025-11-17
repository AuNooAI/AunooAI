# Status Messaging System - Quick Reference

## File Locations at a Glance

| Component | File Path | Purpose |
|-----------|-----------|---------|
| WebSocket Manager | `/app/routes/websocket_routes.py` | Real-time job updates |
| Task Manager | `/app/services/background_task_manager.py` | Background job tracking |
| Notification API | `/app/routes/notification_routes.py` | User notifications API |
| Notification DB Methods | `/app/database_query_facade.py` (lines 6643-6830) | Notification CRUD |
| Notification Schema | `/app/database_models.py` (lines 700-714) | DB table definition |
| Auto-Ingest Integration | `/app/services/automated_ingest_service.py` (lines 435-578) | Real-world usage example |
| Analysis Queue | `/app/services/analysis_queue.py` | Concurrent task processing |
| Background API Routes | `/app/routes/background_tasks.py` | Task management endpoints |

## WebSocket Endpoints

```
ws://localhost:8000/ws/bulk-process/{job_id}
  └─ For monitoring bulk processing jobs

ws://localhost:8000/ws/progress/{topic_id}
  └─ For topic-specific progress updates
```

## Key Helper Functions

### WebSocket Updates
```python
from app.routes.websocket_routes import (
    send_progress_update,      # Sends progress with percentage
    send_completion_update,    # Sends completion with results
    send_error_update,         # Sends error message
    send_batch_update          # Sends batch completion info
)
```

### Task Manager
```python
from app.services.background_task_manager import (
    get_task_manager,
    run_bulk_analysis_task,
    run_bulk_save_task,
    run_auto_ingest_task,
    run_keyword_check_task
)
```

### Database Notifications
```python
from app.database import get_database_instance

db = get_database_instance()

# Create notification
db.facade.create_notification(
    username="user",
    type="event_type",
    title="Title",
    message="Message",
    link="/path"
)

# Read notifications
db.facade.get_user_notifications(username, unread_only=False, limit=50)
db.facade.get_unread_count(username)

# Update status
db.facade.mark_notification_as_read(notification_id, username)
db.facade.mark_all_notifications_as_read(username)

# Delete
db.facade.delete_notification(notification_id, username)
db.facade.delete_read_notifications(username)
```

## API Endpoints Summary

### Background Tasks
```
POST   /api/background-tasks/bulk-analysis      Start bulk analysis
POST   /api/background-tasks/bulk-save           Start bulk save
GET    /api/background-tasks/task/{id}           Get task status
GET    /api/background-tasks/tasks               List all tasks
GET    /api/background-tasks/summary             Get summary
DELETE /api/background-tasks/task/{id}           Cancel task
POST   /api/background-tasks/cleanup             Cleanup old tasks
```

### Notifications
```
GET    /api/notifications                        Get user notifications
GET    /api/notifications/unread-count           Get unread count
POST   /api/notifications/{id}/mark-read         Mark as read
POST   /api/notifications/mark-all-read          Mark all as read
DELETE /api/notifications/{id}                   Delete notification
DELETE /api/notifications/read                   Delete all read
POST   /api/notifications/create                 Create notification
```

## Task Status States

```
PENDING   → RUNNING  → COMPLETED
                    ↘ FAILED
                    ↘ CANCELLED
```

## Notification Types (Examples)

```
auto_ingest_complete      - Auto-collect finished
auto_ingest_error         - Auto-collect failed
evaluation_complete       - Evaluation finished
article_analysis          - Article analyzed
task_complete            - Generic task complete
system                   - System-wide notification
```

## Message Format Examples

### WebSocket Progress Update
```json
{
  "type": "job_update",
  "job_id": "bulk_123_456",
  "timestamp": "2024-11-10T10:30:00.000Z",
  "status": "progress",
  "progress": 45.5,
  "processed": 45,
  "total": 100,
  "message": "Processing batch 3/5",
  "stage": "processing"
}
```

### WebSocket Completion
```json
{
  "type": "job_update",
  "job_id": "bulk_123_456",
  "timestamp": "2024-11-10T10:35:00.000Z",
  "status": "completed",
  "results": {
    "saved": 95,
    "errors": 5,
    "processed": 100
  }
}
```

### Task Status Response
```json
{
  "success": true,
  "task": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "Bulk Analysis: Climate",
    "status": "running",
    "progress": 65.0,
    "processed_items": 650,
    "total_items": 1000,
    "current_item": "article-title-123",
    "created_at": "2024-11-10T10:00:00",
    "started_at": "2024-11-10T10:01:00",
    "completed_at": null,
    "error": null
  }
}
```

## Common Integration Code

### Creating a Background Task
```python
from app.services.background_task_manager import get_task_manager, run_bulk_analysis_task
from fastapi import BackgroundTasks

task_manager = get_task_manager()

# Create task
task_id = task_manager.create_task(
    name="Analyze articles",
    total_items=len(urls),
    metadata={"topic": "climate"}
)

# Run in background (through BackgroundTasks or direct)
background_tasks.add_task(
    task_manager.run_task,
    task_id,
    run_bulk_analysis_task,
    urls=urls,
    topic="climate"
)

# Client polls or uses WebSocket to check status
status = task_manager.get_task_status(task_id)
```

### WebSocket Progress Tracking
```python
async def process_with_updates(job_id, items):
    from app.routes.websocket_routes import send_progress_update, send_completion_update
    
    try:
        for i, item in enumerate(items):
            # Process item
            result = await process_item(item)
            
            # Send progress
            await send_progress_update(job_id, {
                "processed": i + 1,
                "total": len(items),
                "progress": ((i + 1) / len(items)) * 100,
                "current_item": item.title
            })
        
        # Send completion
        await send_completion_update(job_id, {"status": "success"})
    except Exception as e:
        from app.routes.websocket_routes import send_error_update
        await send_error_update(job_id, str(e))
```

### Sending Notifications
```python
async def task_completed(username: str, task_name: str):
    db = get_database_instance()
    db.facade.create_notification(
        username=username,
        type="task_complete",
        title=f"{task_name} Completed",
        message=f"Your {task_name} operation has finished successfully",
        link="/tasks"
    )
```

## Configuration Constants

| Setting | Location | Default | Purpose |
|---------|----------|---------|---------|
| Max concurrent tasks | `background_task_manager.py:56` | 3 | Limit parallel tasks |
| Task cleanup interval | `background_task_manager.py:57` | 3600s | Clean old tasks |
| Max analysis queue size | `analysis_queue.py:30` | 100 | Queue capacity |
| Analysis workers | `analysis_queue.py:27` | 3 | Concurrent workers |
| Notification limit | `notification_routes.py` | 50 | Default fetch limit |

## Debugging Tips

1. **Check WebSocket Connection**
   ```javascript
   // In browser console
   const ws = new WebSocket('ws://localhost:8000/ws/bulk-process/job-id');
   ws.onopen = () => console.log('Connected');
   ws.onerror = (e) => console.error('WS Error:', e);
   ```

2. **Monitor Task Status**
   ```python
   # Check specific task
   task_manager = get_task_manager()
   print(task_manager.get_task_status("task-id"))
   
   # Get all tasks summary
   print(task_manager.get_task_summary())
   ```

3. **View Notifications**
   ```python
   db = get_database_instance()
   notifications = db.facade.get_user_notifications("username")
   print(f"Total: {len(notifications)}, Unread: {db.facade.get_unread_count('username')}")
   ```

4. **Check Logs**
   ```bash
   # Look for WebSocket events
   grep -r "WebSocket" logs/
   
   # Look for task manager events
   grep -r "Task.*started\|Task.*completed" logs/
   ```

## Performance Considerations

1. **WebSocket Limits**: Keep message frequency under 10/sec per client
2. **Task Queue**: Monitor `_max_concurrent_tasks` (default 3) to prevent overload
3. **Notifications**: Old notifications are only cleaned on explicit request
4. **Progress Updates**: Consider throttling to 5-10 updates/sec per job
5. **Memory**: Task history kept in memory; cleanup regularly for long-running services

## Security Considerations

1. **WebSocket**: No authentication check - consider adding session verification
2. **Notifications**: Scoped to username or system-wide (NULL username)
3. **Task Access**: Anyone can query any task - consider adding user ownership check
4. **API Endpoints**: Notification endpoints require session authentication
5. **Notification Links**: Can be external URLs - validate to prevent XSS

## Future Enhancement Ideas

1. Persist task history to database
2. Add WebSocket authentication and user scoping
3. Implement task priority queue
4. Add email notifications for important events
5. Task scheduling/cron integration
6. Real-time notification push to clients
7. Task result streaming for large datasets
8. Task dependency chains
