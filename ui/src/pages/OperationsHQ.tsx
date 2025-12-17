/**
 * Operations HQ - Main dashboard with world clock and system health
 */

import { useState, useEffect } from 'react';
import { Clock, Newspaper, TrendingUp, Tags, Folder, Cpu, HardDrive, Activity, Key, RefreshCw, Settings, Plus, Play, Pause, X, ChevronDown, RotateCw, Database } from 'lucide-react';
import { SharedNavigation } from '../components/SharedNavigation';
import { WorldClockConfig, type ClockConfig } from '../components/WorldClockConfig';
import { Button } from '../components/ui/button';
import { NotificationBell } from '../components/gather/NotificationBell';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '../components/ui/dialog';
import { Label } from '../components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../components/ui/select';
import { Switch } from '../components/ui/switch';
import '../components/gather/NotificationBell.css';
import { OnboardingWizard } from '../components/onboarding/OnboardingWizard';

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
    seconds?: number;
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
  api_health?: {
    status: string;
    apis: {
      collector: string;
      ai_provider: string;
      firecrawl: string;
    };
    configured_count: number;
    total_checked: number;
  };
  autopolling?: {
    status: string;
    message?: string;
    is_enabled?: boolean;
    requests_today?: number;
    daily_limit?: number;
    last_run?: string;
  };
  database?: {
    status: string;
    article_count?: number;
    size_mb?: number;
    locked?: boolean;
    error?: string;
  };
}

interface ClockData extends ClockConfig {
  time: string;
  date: string;
}

interface TickerArticle {
  title: string;
  uri: string;
  source?: string;
  published_at?: string;
}

interface TickerConfig {
  articleCount: number;
  timeRange: string;
  scrollSpeed: string;
  refreshInterval: number;
  showSource: boolean;
  showTime: boolean;
  enabled: boolean;
}

const DEFAULT_TICKER_CONFIG: TickerConfig = {
  articleCount: 15,
  timeRange: '7d',
  scrollSpeed: 'lazy',
  refreshInterval: 300,
  showSource: true,
  showTime: true,
  enabled: true
};

const SCROLL_SPEEDS: Record<string, number> = {
  lazy: 120,
  slow: 90,
  medium: 60,
  fast: 30
};

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
  const [isOnboardingOpen, setIsOnboardingOpen] = useState(false);
  const [stats, setStats] = useState<Stats | null>(null);
  const [healthData, setHealthData] = useState<HealthData | null>(null);
  const [loading, setLoading] = useState(true);
  const [tickerArticles, setTickerArticles] = useState<TickerArticle[]>([]);
  const [tickerVisible, setTickerVisible] = useState(() => {
    const saved = localStorage.getItem('tickerVisible');
    return saved !== 'false';
  });
  const [tickerPaused, setTickerPaused] = useState(false);
  const [tickerSettingsOpen, setTickerSettingsOpen] = useState(false);
  const [tickerConfig, setTickerConfig] = useState<TickerConfig>(() => {
    const saved = localStorage.getItem('tickerConfig');
    return saved ? JSON.parse(saved) : DEFAULT_TICKER_CONFIG;
  });

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

  // Fetch ticker articles based on config
  const fetchTickerArticles = async () => {
    try {
      const tickerRes = await fetch(`/api/news-feed/articles?per_page=${tickerConfig.articleCount}&date_range=${tickerConfig.timeRange}`);
      if (tickerRes.ok) {
        const tickerData = await tickerRes.json();
        const articles = tickerData.articles?.items || tickerData.articles || [];
        setTickerArticles(articles.slice(0, tickerConfig.articleCount).map((a: any) => ({
          title: a.title,
          uri: a.uri || a.url || a.link,
          source: a.source || a.source_name,
          published_at: a.published_at || a.date || a.published
        })));
      }
    } catch (error) {
      console.error('Error fetching ticker articles:', error);
    }
  };

  // Fetch stats and health data
  useEffect(() => {
    const fetchData = async () => {
      try {
        const [statsRes, healthRes] = await Promise.all([
          fetch('/api/dashboard/stats'),
          fetch('/health/detailed')
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
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, []);

  // Fetch ticker articles when config changes
  useEffect(() => {
    if (tickerConfig.enabled) {
      fetchTickerArticles();
      // Set up auto-refresh if configured
      if (tickerConfig.refreshInterval > 0) {
        const interval = setInterval(fetchTickerArticles, tickerConfig.refreshInterval * 1000);
        return () => clearInterval(interval);
      }
    }
  }, [tickerConfig]);

  // Save ticker config
  const saveTickerConfig = (newConfig: TickerConfig) => {
    setTickerConfig(newConfig);
    localStorage.setItem('tickerConfig', JSON.stringify(newConfig));
    setTickerSettingsOpen(false);
  };

  // Reset ticker config to defaults
  const resetTickerConfig = () => {
    setTickerConfig(DEFAULT_TICKER_CONFIG);
    localStorage.setItem('tickerConfig', JSON.stringify(DEFAULT_TICKER_CONFIG));
  };

  // Toggle ticker visibility
  const toggleTicker = () => {
    const newValue = !tickerVisible;
    setTickerVisible(newValue);
    localStorage.setItem('tickerVisible', String(newValue));
  };

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
          <div className="flex items-center gap-2 text-sm text-gray-700">
            <span>Operations</span>
            <span>/</span>
            <span className="font-medium text-gray-950">System Health</span>
            <span>•</span>
            <span>Monitor system status and world operations</span>
          </div>

          {/* Right Icons */}
          <div className="gather-top-bar-right">
            <NotificationBell />
            <button
              onClick={() => setIsOnboardingOpen(true)}
              className="gather-top-bar-setup-btn"
            >
              Set up topic
              <Plus className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* News Ticker */}
        {tickerVisible && tickerConfig.enabled && (
          <div className="bg-gray-50 border-b border-gray-200 border-l-4 border-l-blue-500 h-11 flex items-stretch overflow-hidden">
            <div className="bg-gradient-to-r from-blue-500 to-blue-600 text-white px-4 font-bold text-xs uppercase flex items-center tracking-wider">
              Latest
            </div>
            <div className="flex-1 overflow-hidden relative">
              {tickerArticles.length > 0 ? (
                <div
                  className={`inline-flex whitespace-nowrap h-full items-center ${tickerPaused ? '' : 'animate-scroll-left'}`}
                  style={{ animationDuration: `${SCROLL_SPEEDS[tickerConfig.scrollSpeed] || 120}s` }}
                >
                  {tickerArticles.map((article, idx) => (
                    <a
                      key={idx}
                      href={article.uri}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center px-4 text-sm text-gray-700 hover:text-blue-600 transition-colors"
                    >
                      {tickerConfig.showTime && article.published_at && (
                        <span className="text-gray-400 text-xs mr-2">
                          {new Date(article.published_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                        </span>
                      )}
                      <span className="truncate max-w-md">{article.title}</span>
                      {tickerConfig.showSource && article.source && (
                        <span className="text-gray-400 text-xs ml-2">— {article.source}</span>
                      )}
                    </a>
                  ))}
                </div>
              ) : (
                <div className="flex items-center h-full px-4 text-sm text-gray-500">
                  No recent articles available
                </div>
              )}
            </div>
            <div className="flex items-center gap-1 px-2 border-l border-gray-200">
              <button
                onClick={() => setTickerPaused(!tickerPaused)}
                className="p-1.5 hover:bg-gray-200 rounded text-gray-500 hover:text-gray-700"
                title={tickerPaused ? 'Play' : 'Pause'}
              >
                {tickerPaused ? <Play className="w-4 h-4" /> : <Pause className="w-4 h-4" />}
              </button>
              <button
                onClick={() => setTickerSettingsOpen(true)}
                className="p-1.5 hover:bg-gray-200 rounded text-gray-500 hover:text-gray-700"
                title="Ticker settings"
              >
                <Settings className="w-4 h-4" />
              </button>
              <button
                onClick={fetchTickerArticles}
                className="p-1.5 hover:bg-gray-200 rounded text-gray-500 hover:text-gray-700"
                title="Refresh"
              >
                <RotateCw className="w-4 h-4" />
              </button>
              <button
                onClick={toggleTicker}
                className="p-1.5 hover:bg-gray-200 rounded text-gray-500 hover:text-gray-700"
                title="Hide ticker"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}

        {/* Show ticker button when hidden */}
        {!tickerVisible && (
          <button
            onClick={toggleTicker}
            className="w-full bg-gray-100 hover:bg-gray-200 border-b border-gray-200 py-1 text-xs text-gray-500 flex items-center justify-center gap-1 transition-colors"
          >
            <ChevronDown className="w-3 h-3" />
            Show news ticker
          </button>
        )}

        {/* Scrollable Content */}
        <div className="flex-1 overflow-y-auto p-6">
          <div className="w-full">

          {/* System Health Status - Top Priority */}
          {healthData && (
            <div className="mb-6">
              {/* Health Status Header */}
              <div className="bg-white rounded-lg shadow-md p-6 text-center">
                <div className={`inline-block px-6 py-2 rounded-full text-white font-bold text-lg ${getStatusColor(healthData.status)}`}>
                  {healthData.status.toUpperCase()}
                </div>
                <p className="text-gray-700 mt-2">
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
                <div className="text-xs font-semibold text-gray-800 mb-1">{clock.city}</div>
                <div className="text-lg font-mono text-pink-500">{clock.time}</div>
                <div className="text-xs text-gray-600">{clock.date}</div>
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
                <p className="text-gray-700 text-sm">Total Articles</p>
                <p className="text-3xl font-bold text-pink-500">{stats?.total_articles || 0}</p>
              </div>
              <Newspaper className="w-12 h-12 text-pink-200" />
            </div>
          </div>

          <div className="bg-white rounded-lg shadow-md p-6 hover:shadow-lg transition-shadow cursor-pointer"
               onClick={() => window.location.href = '/gather'}>
            <div className="flex items-center justify-between">
              <div>
                <p className="text-gray-700 text-sm">Articles Today</p>
                <p className="text-3xl font-bold text-pink-500">{stats?.articles_today || 0}</p>
              </div>
              <TrendingUp className="w-12 h-12 text-pink-200" />
            </div>
          </div>

          <div className="bg-white rounded-lg shadow-md p-6 hover:shadow-lg transition-shadow cursor-pointer"
               onClick={() => window.location.href = '/gather?tab=keywords'}>
            <div className="flex items-center justify-between">
              <div>
                <p className="text-gray-700 text-sm">Keyword Groups</p>
                <p className="text-3xl font-bold text-pink-500">{stats?.keyword_groups || 0}</p>
              </div>
              <Tags className="w-12 h-12 text-pink-200" />
            </div>
          </div>

          <div className="bg-white rounded-lg shadow-md p-6 hover:shadow-lg transition-shadow cursor-pointer"
               onClick={() => window.location.href = '/explore'}>
            <div className="flex items-center justify-between">
              <div>
                <p className="text-gray-700 text-sm">Topics</p>
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
                    <span className="text-gray-700">Process:</span>
                    <span className="font-semibold">{healthData.cpu.process_percent}%</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-700">System:</span>
                    <span className="font-semibold">{healthData.cpu.system_percent}%</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-700">Cores:</span>
                    <span className="font-semibold">{healthData.cpu.core_count}</span>
                  </div>
                  {healthData.cpu.load_average && (
                    <div className="flex justify-between">
                      <span className="text-gray-700">Load (1/5/15m):</span>
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
                    <span className="text-gray-700">Process RSS:</span>
                    <span className="font-semibold">{healthData.memory.process.rss_mb} MB</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-700">Process %:</span>
                    <span className="font-semibold">{healthData.memory.process.percent}%</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-700">Threads:</span>
                    <span className="font-semibold">{healthData.memory.process.num_threads}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-700">System:</span>
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
                    <span className="text-gray-700">Used:</span>
                    <span className="font-semibold">{healthData.disk.root.used_gb} / {healthData.disk.root.total_gb} GB</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-700">Free:</span>
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

              {/* API Keys */}
              <div className="bg-white rounded-lg shadow-md p-6">
                <div className="flex items-center gap-3 mb-4 pb-3 border-b-2 border-pink-500">
                  <Key className="w-6 h-6 text-pink-500" />
                  <h3 className="text-lg font-semibold">API Keys</h3>
                </div>
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-gray-700">Status:</span>
                    <span className={`font-semibold ${
                      healthData.api_health?.status === 'healthy' ? 'text-green-600' :
                      healthData.api_health?.status === 'degraded' ? 'text-yellow-600' : 'text-red-600'
                    }`}>
                      {healthData.api_health?.status === 'healthy' ? 'All Configured' :
                       healthData.api_health?.status === 'degraded' ? 'Partial' : 'Critical'}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-700">Configured:</span>
                    <span className="font-semibold">{healthData.api_health?.configured_count || 0} / {healthData.api_health?.total_checked || 3}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-700">News Collector:</span>
                    <span className={`font-semibold ${healthData.api_health?.apis?.collector === 'configured' ? 'text-green-600' : 'text-red-600'}`}>
                      {healthData.api_health?.apis?.collector === 'configured' ? '✓' : '✗'}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-700">AI Provider:</span>
                    <span className={`font-semibold ${healthData.api_health?.apis?.ai_provider === 'configured' ? 'text-green-600' : 'text-red-600'}`}>
                      {healthData.api_health?.apis?.ai_provider === 'configured' ? '✓' : '✗'}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-700">Firecrawl:</span>
                    <span className={`font-semibold ${healthData.api_health?.apis?.firecrawl === 'configured' ? 'text-green-600' : 'text-red-600'}`}>
                      {healthData.api_health?.apis?.firecrawl === 'configured' ? '✓' : '✗'}
                    </span>
                  </div>
                </div>
              </div>

              {/* Auto-polling */}
              <div className="bg-white rounded-lg shadow-md p-6">
                <div className="flex items-center gap-3 mb-4 pb-3 border-b-2 border-pink-500">
                  <RefreshCw className="w-6 h-6 text-pink-500" />
                  <h3 className="text-lg font-semibold">Auto-polling</h3>
                </div>
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-gray-700">Status:</span>
                    <span className={`font-semibold ${
                      healthData.autopolling?.is_enabled ? 'text-green-600' : 'text-gray-500'
                    }`}>
                      {healthData.autopolling?.is_enabled ? 'Enabled' :
                       healthData.autopolling?.status === 'unknown' ? 'Not Configured' : 'Disabled'}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-700">Requests Today:</span>
                    <span className="font-semibold">
                      {healthData.autopolling?.requests_today ?? '--'} / {healthData.autopolling?.daily_limit ?? '--'}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-700">Last Run:</span>
                    <span className="font-semibold text-xs">
                      {healthData.autopolling?.last_run ?
                        new Date(healthData.autopolling.last_run).toLocaleString() : '--'}
                    </span>
                  </div>
                  {healthData.autopolling?.daily_limit && healthData.autopolling?.requests_today !== undefined && (
                    <div className="mt-3">
                      <div className="w-full bg-gray-200 rounded-full h-4 overflow-hidden">
                        <div
                          className={`h-full flex items-center justify-center text-white text-xs font-semibold ${
                            getProgressColor((healthData.autopolling.requests_today / healthData.autopolling.daily_limit) * 100)
                          }`}
                          style={{ width: `${Math.min((healthData.autopolling.requests_today / healthData.autopolling.daily_limit) * 100, 100)}%` }}
                        >
                          {Math.round((healthData.autopolling.requests_today / healthData.autopolling.daily_limit) * 100)}%
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              </div>

              {/* Database */}
              <div className="bg-white rounded-lg shadow-md p-6">
                <div className="flex items-center gap-3 mb-4 pb-3 border-b-2 border-pink-500">
                  <Database className="w-6 h-6 text-pink-500" />
                  <h3 className="text-lg font-semibold">Database</h3>
                </div>
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-gray-700">Status:</span>
                    <span className={`font-semibold ${
                      healthData.database?.status === 'healthy' ? 'text-green-600' : 'text-red-600'
                    }`}>
                      {healthData.database?.status === 'healthy' ? '✓ Healthy' : '✗ Unhealthy'}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-700">Articles:</span>
                    <span className="font-semibold">{healthData.database?.article_count?.toLocaleString() ?? '--'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-700">Size:</span>
                    <span className="font-semibold">{healthData.database?.size_mb ?? '--'} MB</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-700">Locked:</span>
                    <span className={`font-semibold ${healthData.database?.locked ? 'text-red-600' : 'text-green-600'}`}>
                      {healthData.database?.locked ? 'Yes' : 'No'}
                    </span>
                  </div>
                  {healthData.database?.error && (
                    <div className="mt-2 text-xs text-red-600 bg-red-50 p-2 rounded">
                      {healthData.database.error}
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

          {loading && !healthData && (
            <div className="text-center py-12">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-pink-500 mx-auto"></div>
              <p className="text-gray-700 mt-4">Loading system metrics...</p>
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

      {/* Onboarding Wizard Modal */}
      <OnboardingWizard
        open={isOnboardingOpen}
        onOpenChange={setIsOnboardingOpen}
      />

      {/* Ticker Settings Modal */}
      <Dialog open={tickerSettingsOpen} onOpenChange={setTickerSettingsOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Settings className="w-5 h-5" />
              News Ticker Settings
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            {/* Article Count */}
            <div className="space-y-2">
              <Label>Number of Articles</Label>
              <Select
                value={String(tickerConfig.articleCount)}
                onValueChange={(val) => setTickerConfig({ ...tickerConfig, articleCount: Number(val) })}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="5">5 articles</SelectItem>
                  <SelectItem value="10">10 articles</SelectItem>
                  <SelectItem value="15">15 articles</SelectItem>
                  <SelectItem value="20">20 articles</SelectItem>
                  <SelectItem value="25">25 articles</SelectItem>
                </SelectContent>
              </Select>
              <p className="text-xs text-gray-500">More articles = longer scroll cycle</p>
            </div>

            {/* Time Range */}
            <div className="space-y-2">
              <Label>Time Range</Label>
              <Select
                value={tickerConfig.timeRange}
                onValueChange={(val) => setTickerConfig({ ...tickerConfig, timeRange: val })}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="1h">Last Hour</SelectItem>
                  <SelectItem value="6h">Last 6 Hours</SelectItem>
                  <SelectItem value="24h">Last 24 Hours</SelectItem>
                  <SelectItem value="72h">Last 3 Days</SelectItem>
                  <SelectItem value="7d">Last 7 Days</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {/* Scroll Speed */}
            <div className="space-y-2">
              <Label>Scroll Speed</Label>
              <Select
                value={tickerConfig.scrollSpeed}
                onValueChange={(val) => setTickerConfig({ ...tickerConfig, scrollSpeed: val })}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="lazy">Lazy (120 seconds)</SelectItem>
                  <SelectItem value="slow">Slow (90 seconds)</SelectItem>
                  <SelectItem value="medium">Medium (60 seconds)</SelectItem>
                  <SelectItem value="fast">Fast (30 seconds)</SelectItem>
                </SelectContent>
              </Select>
              <p className="text-xs text-gray-500">Slower speeds are easier to read</p>
            </div>

            {/* Auto-Refresh */}
            <div className="space-y-2">
              <Label>Auto-Refresh</Label>
              <Select
                value={String(tickerConfig.refreshInterval)}
                onValueChange={(val) => setTickerConfig({ ...tickerConfig, refreshInterval: Number(val) })}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="0">Disabled</SelectItem>
                  <SelectItem value="60">Every 1 minute</SelectItem>
                  <SelectItem value="300">Every 5 minutes</SelectItem>
                  <SelectItem value="600">Every 10 minutes</SelectItem>
                  <SelectItem value="1800">Every 30 minutes</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {/* Display Options */}
            <div className="space-y-3">
              <Label>Display Options</Label>
              <div className="flex items-center justify-between">
                <span className="text-sm">Show article source</span>
                <Switch
                  checked={tickerConfig.showSource}
                  onCheckedChange={(checked) => setTickerConfig({ ...tickerConfig, showSource: checked })}
                  className="data-[state=checked]:bg-pink-500 data-[state=unchecked]:bg-gray-300"
                />
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm">Show publish time</span>
                <Switch
                  checked={tickerConfig.showTime}
                  onCheckedChange={(checked) => setTickerConfig({ ...tickerConfig, showTime: checked })}
                  className="data-[state=checked]:bg-pink-500 data-[state=unchecked]:bg-gray-300"
                />
              </div>
            </div>

            {/* Enable Ticker */}
            <div className="flex items-center justify-between pt-2 border-t">
              <span className="font-medium">Enable ticker on page load</span>
              <Switch
                checked={tickerConfig.enabled}
                onCheckedChange={(checked) => setTickerConfig({ ...tickerConfig, enabled: checked })}
                className="data-[state=checked]:bg-pink-500 data-[state=unchecked]:bg-gray-300"
              />
            </div>
          </div>
          <DialogFooter className="flex gap-2">
            <Button variant="outline" onClick={resetTickerConfig}>
              Reset to Defaults
            </Button>
            <Button onClick={() => saveTickerConfig(tickerConfig)}>
              Save Settings
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
