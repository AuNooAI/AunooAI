# Status Messaging System Documentation Index

## Overview

This directory contains comprehensive documentation for the Aunoo AI Status Messaging System, a multi-layered architecture for real-time progress tracking and persistent notifications.

## Documents

### 1. STATUS_MESSAGING_SYSTEM.md (Main Documentation)
**Size:** ~19 KB | **Sections:** 25

Complete technical documentation covering:
- Component Overview (WebSocket, Task Manager, Notifications)
- Detailed implementation of each layer
- Integration points and usage examples
- Configuration options
- Common usage patterns

**Best for:** Understanding the full system architecture and detailed implementation.

### 2. STATUS_MESSAGING_QUICK_REFERENCE.md (Quick Lookup)
**Size:** ~9 KB | **Sections:** 15

Quick-access reference guide including:
- File locations at a glance
- API endpoint summary with HTTP methods
- Key helper functions and imports
- Example code snippets for common tasks
- Configuration constants
- Debugging tips
- Performance and security considerations

**Best for:** Developers actively coding against the system - quick copy/paste solutions.

### 3. STATUS_MESSAGING_ARCHITECTURE.md (Visual Guide)
**Size:** ~32 KB | **Sections:** 18

Visual architecture documentation with ASCII diagrams:
- High-level system architecture
- Component relationships and interactions
- Data flow diagrams
- State transitions
- Concurrency and resource management
- Error handling flows
- Performance characteristics table
- Security boundaries

**Best for:** Understanding how components fit together and data flows through the system.

## Quick Navigation

### I Need To...

#### Implement a New Feature
1. Start with: **STATUS_MESSAGING_SYSTEM.md** → Integration Points section
2. Reference: **STATUS_MESSAGING_QUICK_REFERENCE.md** → Common Integration Code

#### Fix a Bug / Debug
1. Check: **STATUS_MESSAGING_QUICK_REFERENCE.md** → Debugging Tips
2. Deep dive: **STATUS_MESSAGING_ARCHITECTURE.md** → Error Handling & Recovery
3. Reference: **STATUS_MESSAGING_SYSTEM.md** → Your specific component

#### Understand the System
1. Start with: **STATUS_MESSAGING_ARCHITECTURE.md** → High-Level System Architecture
2. Deep dive: **STATUS_MESSAGING_SYSTEM.md** → Component Overview
3. Reference diagrams as needed

#### Use the API
1. Quick lookup: **STATUS_MESSAGING_QUICK_REFERENCE.md** → API Endpoints Summary
2. Full details: **STATUS_MESSAGING_SYSTEM.md** → Component sections (Background Task Manager, Database Notifications)

#### Write Integration Code
1. Examples: **STATUS_MESSAGING_QUICK_REFERENCE.md** → Common Integration Code
2. Full reference: **STATUS_MESSAGING_SYSTEM.md** → Usage Examples sections
3. Architecture: **STATUS_MESSAGING_ARCHITECTURE.md** → Data Flow diagrams

## System Components Summary

### WebSocket Real-Time Updates
- **File:** `/app/routes/websocket_routes.py`
- **Purpose:** Live progress during long operations
- **Endpoints:** `/ws/bulk-process/{job_id}`, `/ws/progress/{topic_id}`
- **Key Class:** `ConnectionManager`

### Background Task Manager
- **File:** `/app/services/background_task_manager.py`
- **Purpose:** Track async jobs and provide status
- **Key Class:** `BackgroundTaskManager`
- **Provides:** Task tracking, progress callbacks, state management

### Database Notifications
- **Files:** 
  - `/app/routes/notification_routes.py` (API)
  - `/app/database_query_facade.py` (Database methods)
  - `/app/database_models.py` (Schema)
- **Purpose:** Persistent user notifications
- **Key Methods:** `create_notification()`, `get_user_notifications()`, etc.

### Analysis Queue
- **File:** `/app/services/analysis_queue.py`
- **Purpose:** Concurrent task processing
- **Key Class:** `AnalysisQueue`

### Auto-Ingest Integration
- **File:** `/app/services/automated_ingest_service.py`
- **Purpose:** Real-world usage example of all components

## File Cross-References

| Component | Covered In | Primary Section |
|-----------|-----------|-----------------|
| WebSocket Manager | All 3 docs | SYSTEM.md: Component 1 |
| Task Manager | All 3 docs | SYSTEM.md: Component 2 |
| Notifications | All 3 docs | SYSTEM.md: Component 3 |
| Auto-Ingest Integration | SYSTEM.md, ARCHITECTURE.md | SYSTEM.md: Integration Points |
| API Endpoints | QUICK_REF.md, SYSTEM.md | QUICK_REF.md: API Endpoints |
| Code Examples | QUICK_REF.md, SYSTEM.md | QUICK_REF.md: Common Integration |
| Architecture Diagrams | ARCHITECTURE.md | All sections |

## Key Concepts

### Task States
```
PENDING → RUNNING → COMPLETED
                 ↘ FAILED
                 ↘ CANCELLED
```

### Message Flow
```
User Action → API Endpoint → Task Manager/WebSocket → Database/Memory → Client
```

### Three-Layer Architecture
1. **Immediate Feedback:** WebSocket for real-time updates
2. **Tracking:** Task Manager for status and progress
3. **Persistence:** Database notifications for record-keeping

## Configuration

All configuration is in source code (no external config files):
- Task Manager limits: `background_task_manager.py` lines 56-57
- Analysis Queue settings: `analysis_queue.py` lines 27-30
- Auto-Ingest config: `/api/auto-ingest/config` endpoint

## Security Notes

Read **STATUS_MESSAGING_QUICK_REFERENCE.md** → Security Considerations

**Important:** WebSocket endpoints have no authentication - consider adding user scoping in production.

## Performance Notes

Read **STATUS_MESSAGING_QUICK_REFERENCE.md** → Performance Considerations

Key limits:
- Max concurrent tasks: 3
- Max analysis queue size: 100
- Max concurrent workers: 3

## Real-World Example

The **Auto-Ingest Service** (`/app/services/automated_ingest_service.py`) demonstrates all three components:
- Lines 435-444: WebSocket progress updates
- Lines 509-520: Batch completion updates
- Lines 554-557: Completion updates
- Lines 348-365 (background_task_manager.py): Notification creation

## Related Files (Not in This Guide)

- **`/app/routes/auto_ingest.py`** - API endpoints for auto-ingest
- **`/app/routes/background_tasks.py`** - API endpoints for task management
- **`/app/routes/notification_routes.py`** - API endpoints for notifications
- **`/app/database.py`** - Database singleton and initialization
- **`/app/database_query_facade.py`** - Complete facade interface

## Document Statistics

| Document | Lines | Sections | Code Examples | Diagrams |
|----------|-------|----------|---------------|----------|
| SYSTEM.md | 611 | 25 | 15+ | 3 |
| QUICK_REF.md | 310 | 15 | 20+ | 5 |
| ARCHITECTURE.md | 542 | 18 | 10 | 10+ |
| **Total** | **1463** | **58** | **45+** | **18+** |

## Last Updated

Created: November 10, 2024
Based on: Current codebase at `/home/orochford/tenants/multi.aunoo.ai`

## Contributing

When updating the system, please update these documents:
1. SYSTEM.md - for detailed technical changes
2. QUICK_REF.md - for API/method changes
3. ARCHITECTURE.md - for flow/structure changes
4. This INDEX - for major structural reorganization

---

**For questions about specific components, start with the appropriate document above.**
