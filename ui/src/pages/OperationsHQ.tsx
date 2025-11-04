/**
 * Operations HQ - Main dashboard with world clock and system health
 */

import { useState, useEffect } from 'react';
import { Clock, Newspaper, TrendingUp, Tags, Folder, Cpu, HardDrive, Activity, FileText, Settings, Bell } from 'lucide-react';
import { SharedNavigation } from '../components/SharedNavigation';
import { WorldClockConfig, type ClockConfig } from '../components/WorldClockConfig';
import { Button } from '../components/ui/button';

interface Stats {
  total_articles: number;
  articles_today: number;
  keyword_groups: number;
  topics: number;
}

interface HealthData {
  status: string;
  uptime: {
    days: number;
    hours: number;
    minutes: number;
  };
  warnings: string[];
  cpu: {
    process_percent: number;
    system_percent: number;
    core_count: number;
    load_average?: number[];
  };
  memory: {
    process: {
      rss_mb: number;
      percent: number;
      num_threads: number;
    };
    system: {
      used_gb: number;
      total_gb: number;
      percent: number;
    };
  };
  disk: {
    root: {
      used_gb: number;
      total_gb: number;
      free_gb: number;
      percent: number;
    };
  };
  file_descriptors: {
    open: number;
    soft_limit: number;
    available: number;
    connections: number;
    files: number;
    usage_percent: number;
  };
}

interface ClockData extends ClockConfig {
  time: string;
  date: string;
}

const DEFAULT_TIMEZONES: ClockConfig[] = [
  { timezone: 'America/Los_Angeles', city: 'San Francisco' },
  { timezone: 'America/New_York', city: 'New York' },
  { timezone: 'Europe/London', city: 'London' },
  { timezone: 'Europe/Berlin', city: 'Berlin' },
  { timezone: 'Europe/Moscow', city: 'Moscow' },
  { timezone: 'Asia/Dubai', city: 'Dubai' },
  { timezone: 'Asia/Shanghai', city: 'Beijing' },
  { timezone: 'Asia/Tokyo', city: 'Tokyo' },
];

export function OperationsHQ() {
  const [clocks, setClocks] = useState<ClockData[]>([]);
  const [selectedTimezones, setSelectedTimezones] = useState<ClockConfig[]>(() => {
    const saved = localStorage.getItem('worldClockTimezones');
    return saved ? JSON.parse(saved) : DEFAULT_TIMEZONES;
  });
  const [isClockConfigOpen, setIsClockConfigOpen] = useState(false);
  const [stats, setStats] = useState<Stats | null>(null);
  const [healthData, setHealthData] = useState<HealthData | null>(null);
  const [loading, setLoading] = useState(true);

  // Update clocks every second
  useEffect(() => {
    const updateClocks = () => {
      const newClocks = selectedTimezones.map(({ timezone, city }) => {
        const now = new Date();
        const formatter = new Intl.DateTimeFormat('en-US', {
          timeZone: timezone,
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
          hour12: false
        });
        const dateFormatter = new Intl.DateTimeFormat('en-US', {
          timeZone: timezone,
          month: 'short',
          day: 'numeric'
        });
        return {
          timezone,
          city,
          time: formatter.format(now),
          date: dateFormatter.format(now)
        };
      });
      setClocks(newClocks);
    };

    updateClocks();
    const interval = setInterval(updateClocks, 1000);
    return () => clearInterval(interval);
  }, [selectedTimezones]);

  const handleSaveClocks = (newClocks: ClockConfig[]) => {
    setSelectedTimezones(newClocks);
    localStorage.setItem('worldClockTimezones', JSON.stringify(newClocks));
  };

  // Fetch stats and health data
  useEffect(() => {
    const fetchData = async () => {
      try {
        const [statsRes, healthRes] = await Promise.all([
          fetch('/api/dashboard/stats'),
          fetch('/api/health')
        ]);

        if (statsRes.ok) {
          const statsData = await statsRes.json();
          setStats(statsData);
        }

        if (healthRes.ok) {
          const healthData = await healthRes.json();
          setHealthData(healthData);
        }
      } catch (error) {
        console.error('Error fetching dashboard data:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
    // Refresh health data every 30 seconds
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, []);

  const getStatusColor = (status: string) => {
    switch (status?.toLowerCase()) {
      case 'healthy':
        return 'bg-green-500';
      case 'degraded':
        return 'bg-yellow-500';
      case 'critical':
        return 'bg-red-500';
      default:
        return 'bg-gray-500';
    }
  };

  const getProgressColor = (percent: number) => {
    if (percent >= 90) return 'bg-red-500';
    if (percent >= 75) return 'bg-yellow-500';
    return 'bg-green-500';
  };

  return (
    <div className="flex h-screen bg-gray-50">
      {/* Shared Navigation */}
      <SharedNavigation currentPage="health" />

      {/* Main Content */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Top Header */}
        <div className="bg-white border-b border-gray-200 px-6 py-3 flex items-center justify-between">
          {/* Breadcrumb */}
          <div className="flex items-center gap-2 text-sm text-gray-600">
            <span>Operations</span>
            <span>/</span>
            <span className="font-medium text-gray-900">System Health</span>
            <span>•</span>
            <span>Monitor system status and world operations</span>
          </div>

          {/* Right Icons */}
          <div className="flex items-center gap-2">
            <button className="p-2 hover:bg-gray-100 rounded-md">
              <Bell className="w-5 h-5 text-gray-600" />
            </button>
          </div>
        </div>

        {/* Scrollable Content */}
        <div className="flex-1 overflow-y-auto p-6">
          <div className="max-w-7xl mx-auto">

          {/* System Health Status - Top Priority */}
          {healthData && (
            <div className="mb-6">
              {/* Health Status Header */}
              <div className="bg-white rounded-lg shadow-md p-6 text-center">
                <div className={`inline-block px-6 py-2 rounded-full text-white font-bold text-lg ${getStatusColor(healthData.status)}`}>
                  {healthData.status.toUpperCase()}
                </div>
                <p className="text-gray-600 mt-2">
                  Uptime: {healthData.uptime.days}d {healthData.uptime.hours % 24}h {healthData.uptime.minutes % 60}m
                </p>

                {healthData.warnings && healthData.warnings.length > 0 && (
                  <div className="mt-4 bg-yellow-50 border border-yellow-200 rounded-lg p-4 text-left">
                    <p className="font-semibold text-yellow-800 mb-2">⚠ Warnings:</p>
                    <ul className="list-disc list-inside text-yellow-700 text-sm">
                      {healthData.warnings.map((warning, idx) => (
                        <li key={idx}>{warning}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* World Clock */}
          <div className="bg-white rounded-lg shadow-md mb-6 p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-gray-800 flex items-center gap-2">
                <Clock className="w-5 h-5" />
                World Clock
              </h2>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setIsClockConfigOpen(true)}
                className="flex items-center gap-2"
              >
                <Settings className="w-4 h-4" />
                Configure
              </Button>
            </div>
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-4">
            {clocks.map((clock) => (
              <div
                key={clock.timezone}
                className="bg-gray-50 rounded-lg p-3 hover:bg-white hover:shadow-md transition-all"
              >
                <div className="text-xs font-semibold text-gray-700 mb-1">{clock.city}</div>
                <div className="text-lg font-mono text-pink-500">{clock.time}</div>
                <div className="text-xs text-gray-500">{clock.date}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Stats Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-6">
          <div className="bg-white rounded-lg shadow-md p-6 hover:shadow-lg transition-shadow cursor-pointer"
               onClick={() => window.location.href = '/database-editor'}>
            <div className="flex items-center justify-between">
              <div>
                <p className="text-gray-600 text-sm">Total Articles</p>
                <p className="text-3xl font-bold text-pink-500">{stats?.total_articles || 0}</p>
              </div>
              <Newspaper className="w-12 h-12 text-pink-200" />
            </div>
          </div>

          <div className="bg-white rounded-lg shadow-md p-6 hover:shadow-lg transition-shadow cursor-pointer"
               onClick={() => window.location.href = '/keyword-alerts'}>
            <div className="flex items-center justify-between">
              <div>
                <p className="text-gray-600 text-sm">Articles Today</p>
                <p className="text-3xl font-bold text-pink-500">{stats?.articles_today || 0}</p>
              </div>
              <TrendingUp className="w-12 h-12 text-pink-200" />
            </div>
          </div>

          <div className="bg-white rounded-lg shadow-md p-6 hover:shadow-lg transition-shadow cursor-pointer"
               onClick={() => window.location.href = '/keyword-monitor'}>
            <div className="flex items-center justify-between">
              <div>
                <p className="text-gray-600 text-sm">Keyword Groups</p>
                <p className="text-3xl font-bold text-pink-500">{stats?.keyword_groups || 0}</p>
              </div>
              <Tags className="w-12 h-12 text-pink-200" />
            </div>
          </div>

          <div className="bg-white rounded-lg shadow-md p-6 hover:shadow-lg transition-shadow cursor-pointer"
               onClick={() => window.location.href = '/create_topic'}>
            <div className="flex items-center justify-between">
              <div>
                <p className="text-gray-600 text-sm">Topics</p>
                <p className="text-3xl font-bold text-pink-500">{stats?.topics || 0}</p>
              </div>
              <Folder className="w-12 h-12 text-pink-200" />
            </div>
          </div>
        </div>

        {/* System Health Metrics */}
        {healthData && (
          <div className="mb-6">
            <h2 className="text-xl font-bold text-gray-800 mb-4">Detailed Metrics</h2>
            {/* Metrics Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
              {/* CPU */}
              <div className="bg-white rounded-lg shadow-md p-6">
                <div className="flex items-center gap-3 mb-4 pb-3 border-b-2 border-pink-500">
                  <Cpu className="w-6 h-6 text-pink-500" />
                  <h3 className="text-lg font-semibold">CPU</h3>
                </div>
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-gray-600">Process:</span>
                    <span className="font-semibold">{healthData.cpu.process_percent}%</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">System:</span>
                    <span className="font-semibold">{healthData.cpu.system_percent}%</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">Cores:</span>
                    <span className="font-semibold">{healthData.cpu.core_count}</span>
                  </div>
                  {healthData.cpu.load_average && (
                    <div className="flex justify-between">
                      <span className="text-gray-600">Load (1/5/15m):</span>
                      <span className="font-semibold text-xs">
                        {healthData.cpu.load_average.map(l => l.toFixed(2)).join(' / ')}
                      </span>
                    </div>
                  )}
                </div>
              </div>

              {/* Memory */}
              <div className="bg-white rounded-lg shadow-md p-6">
                <div className="flex items-center gap-3 mb-4 pb-3 border-b-2 border-pink-500">
                  <HardDrive className="w-6 h-6 text-pink-500" />
                  <h3 className="text-lg font-semibold">Memory</h3>
                </div>
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-gray-600">Process RSS:</span>
                    <span className="font-semibold">{healthData.memory.process.rss_mb} MB</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">Process %:</span>
                    <span className="font-semibold">{healthData.memory.process.percent}%</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">Threads:</span>
                    <span className="font-semibold">{healthData.memory.process.num_threads}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">System:</span>
                    <span className="font-semibold">{healthData.memory.system.used_gb} / {healthData.memory.system.total_gb} GB</span>
                  </div>
                  <div className="mt-3">
                    <div className="w-full bg-gray-200 rounded-full h-4 overflow-hidden">
                      <div
                        className={`h-full flex items-center justify-center text-white text-xs font-semibold ${getProgressColor(healthData.memory.system.percent)}`}
                        style={{ width: `${healthData.memory.system.percent}%` }}
                      >
                        {healthData.memory.system.percent}%
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {/* Disk */}
              <div className="bg-white rounded-lg shadow-md p-6">
                <div className="flex items-center gap-3 mb-4 pb-3 border-b-2 border-pink-500">
                  <HardDrive className="w-6 h-6 text-pink-500" />
                  <h3 className="text-lg font-semibold">Disk</h3>
                </div>
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-gray-600">Used:</span>
                    <span className="font-semibold">{healthData.disk.root.used_gb} / {healthData.disk.root.total_gb} GB</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">Free:</span>
                    <span className="font-semibold">{healthData.disk.root.free_gb} GB</span>
                  </div>
                  <div className="mt-3">
                    <div className="w-full bg-gray-200 rounded-full h-4 overflow-hidden">
                      <div
                        className={`h-full flex items-center justify-center text-white text-xs font-semibold ${getProgressColor(healthData.disk.root.percent)}`}
                        style={{ width: `${healthData.disk.root.percent}%` }}
                      >
                        {healthData.disk.root.percent}%
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {/* File Descriptors */}
              <div className="bg-white rounded-lg shadow-md p-6">
                <div className="flex items-center gap-3 mb-4 pb-3 border-b-2 border-pink-500">
                  <FileText className="w-6 h-6 text-pink-500" />
                  <h3 className="text-lg font-semibold">File Descriptors</h3>
                </div>
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-gray-600">Open:</span>
                    <span className="font-semibold">{healthData.file_descriptors.open} / {healthData.file_descriptors.soft_limit}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">Available:</span>
                    <span className="font-semibold">{healthData.file_descriptors.available}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">Connections:</span>
                    <span className="font-semibold">{healthData.file_descriptors.connections}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">Files:</span>
                    <span className="font-semibold">{healthData.file_descriptors.files}</span>
                  </div>
                  <div className="mt-3">
                    <div className="w-full bg-gray-200 rounded-full h-4 overflow-hidden">
                      <div
                        className={`h-full flex items-center justify-center text-white text-xs font-semibold ${getProgressColor(healthData.file_descriptors.usage_percent)}`}
                        style={{ width: `${healthData.file_descriptors.usage_percent}%` }}
                      >
                        {healthData.file_descriptors.usage_percent}%
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

          {loading && !healthData && (
            <div className="text-center py-12">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-pink-500 mx-auto"></div>
              <p className="text-gray-600 mt-4">Loading system metrics...</p>
            </div>
          )}
          </div>
        </div>
      </div>

      {/* World Clock Configuration Modal */}
      <WorldClockConfig
        open={isClockConfigOpen}
        onOpenChange={setIsClockConfigOpen}
        currentClocks={selectedTimezones}
        onSave={handleSaveClocks}
      />
    </div>
  );
}
