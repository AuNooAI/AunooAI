# Getting Started with Operations HQ

## Overview

**Operations HQ** is your system monitoring and global operations dashboard. It provides real-time system health metrics, a customizable world clock for tracking global operations, and quick access to key statistics about your intelligence database.

## What's Here

### System Health Status

At the top of the page, you'll see the current system status:

- **Status Badge**: Shows HEALTHY (green), DEGRADED (yellow), or CRITICAL (red)
- **Uptime**: How long the system has been running (days, hours, minutes)
- **Warnings**: Any active system warnings that need attention

### World Clock

Displays current time across multiple cities for tracking global threat intel operations:

- **Default Cities**: San Francisco, New York, London, Berlin, Moscow, Dubai, Beijing, Tokyo
- **Customizable**: Click **Configure** to add/remove cities and change timezones
- **Updates**: Refreshes every second in real-time
- **Persistent**: Your configuration is saved in browser storage

**To customize:**
1. Click the **Configure** button
2. Add or remove cities/timezones
3. Click **Save** - your preferences are remembered

### Statistics Cards

Four cards showing key database metrics (click any card to jump to that feature):

- **Total Articles**: All articles in your database → links to Database Editor
- **Articles Today**: New articles collected today → links to Keyword Alerts (Gather)
- **Keyword Groups**: Number of active keyword monitoring groups → links to Keyword Monitor
- **Topics**: Number of configured topic categories → links to Topic Management

### Detailed System Metrics

Real-time resource usage broken down by category:

#### CPU
- **Process**: CPU used by the application
- **System**: Overall system CPU usage
- **Cores**: Number of CPU cores available
- **Load Average**: 1/5/15 minute load averages (Linux only)

#### Memory
- **Process RSS**: Memory used by the application
- **Process %**: Percentage of system memory used by app
- **Threads**: Number of active application threads
- **System Used**: Total system memory in use
- **System %**: Percentage of total memory used
- **Progress bar**: Visual indicator (green = healthy, yellow = warning, red = critical)

#### Disk
- **Used**: Disk space consumed
- **Total**: Total disk capacity
- **Free**: Available disk space
- **Progress bar**: Visual usage indicator

#### File Descriptors
- **Open**: Currently open file handles
- **Soft Limit**: Maximum allowed file descriptors
- **Available**: Remaining capacity
- **Connections**: Active network connections
- **Files**: Open file handles
- **Usage %**: Percentage of limit used

**Progress Bar Colors:**
- **Green**: < 75% usage (healthy)
- **Yellow**: 75-90% usage (warning)
- **Red**: > 90% usage (critical)

## When to Use Operations HQ

### Daily Check-In (30 seconds)
Quick morning review:
1. Verify system status is HEALTHY
2. Check "Articles Today" to see collection activity
3. Note any warnings

### Global Operations Coordination
When working with international teams or tracking threats across timezones:
1. Use World Clock to coordinate with analysts in other regions
2. Customize cities to match your team's locations or threat actor timezones
3. Reference when scheduling analyst shifts or incident response

### System Health Monitoring
If you notice performance issues or slowness:
1. Check CPU and Memory usage for bottlenecks
2. Review File Descriptors if connections are failing
3. Monitor Disk space to prevent storage issues
4. Check warnings for specific problems

### Capacity Planning
Before adding new data sources or scaling operations:
1. Review current resource usage trends
2. Check if disk space is sufficient
3. Verify memory and CPU have headroom
4. Plan upgrades based on actual metrics

## Tips

- **Bookmark this page**: Quick reference for system health during incidents
- **Refresh rate**: System metrics update every 30 seconds automatically
- **Customize clocks**: Add cities relevant to your threat landscape (e.g., attacker timezones)
- **Click cards**: Statistics cards are shortcuts to related features

## Troubleshooting

### Status shows DEGRADED or CRITICAL
Check the warnings section for specific issues. Common causes:
- High CPU usage (> 80%)
- Low disk space (< 10% free)
- High memory usage (> 90%)
- File descriptor limits approaching

### World Clock not updating
- Refresh the browser page
- Check that JavaScript is enabled
- Clear browser cache if clocks are stuck

### Statistics show zero or outdated
- Page may need refresh (reload browser)
- Database connection issue (check system health status)
- No data collected yet (normal for new installations)

## Related Documentation
- [Gather Guide](getting-started-gather.md) - For keyword monitoring and article collection
- [Explore View Guide](getting-started-explore-view.md) - For analyzing collected articles

---

*Last updated: 2025-11-25*
