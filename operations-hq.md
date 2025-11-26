---
description: >-
  Operations HQ is your system monitoring and global operations dashboard. It
  provides real-time system health metrics, a customizable world clock for
  tracking global operations, and quick access to key
---

# Operations HQ

Operations HQ is your system monitoring and global operations dashboard. It provides real-time system health metrics, a customizable world clock for tracking global operations, and quick access to key statistics about your intelligence database.

***

### What's Here

#### System Health Status

At the top of the page, you'll see the current system status:

* Status Badge: Shows HEALTHY (green), DEGRADED (yellow), or CRITICAL (red)
* Uptime: How long the system has been running (days, hours, minutes)
* Warnings: Any active system warnings that need attention

#### World Clock

Displays current time across multiple cities for tracking global threat intel operations:

* Default Cities: San Francisco, New York, London, Berlin, Moscow, Dubai, Beijing, Tokyo
* Customizable: Click Configure to add/remove cities and change timezones
* Updates: Refreshes every second in real-time
* Persistent: Your configuration is saved in browser storage

To customize:

1. Click the Configure button
2. Add or remove cities/timezones
3. Click Save - your preferences are remembered

#### Statistics Cards

Four cards showing key database metrics (click any card to jump to that feature):

* Total Articles: All articles in your database → links to Database Editor
* Articles Today: New articles collected today → links to Keyword Alerts (Gather)
* Keyword Groups: Number of active keyword monitoring groups → links to Keyword Monitor
* Topics: Number of configured topic categories → links to Topic Management

#### Detailed System Metrics

Real-time resource usage broken down by category:

**CPU**

* Process: CPU used by the application
* System: Overall system CPU usage
* Cores: Number of CPU cores available
* Load Average: 1/5/15 minute load averages (Linux only)

**Memory**

* Process RSS: Memory used by the application
* Process %: Percentage of system memory used by app
* Threads: Number of active application threads
* System Used: Total system memory in use
* System %: Percentage of total memory used
* Progress bar: Visual indicator (green = healthy, yellow = warning, red = critical)

**Disk**

* Used: Disk space consumed
* Total: Total disk capacity
* Free: Available disk space
* Progress bar: Visual usage indicator

**File Descriptors**

* Open: Currently open file handles
* Soft Limit: Maximum allowed file descriptors
* Available: Remaining capacity
* Connections: Active network connections
* Files: Open file handles
* Usage %: Percentage of limit used

**Progress Bar Colors:**

* Green: < 75% usage (healthy)
* Yellow: 75-90% usage (warning)
* Red: > 90% usage (critical)

***

<br>
