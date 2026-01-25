/**
 * GeopoliticalOverviewTab Component
 * Overview statistics and mini map for geopolitical hotspots
 */

import { AlertTriangle, TrendingUp, TrendingDown, MapPin, Newspaper, Globe } from 'lucide-react';
import { HotspotMap } from './map';
import type { OverviewStats, Hotspot } from '../../services/geopoliticalHotspotsApi';
import { RISK_COLORS, type RiskLevel } from '../../services/geopoliticalHotspotsApi';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from 'recharts';

interface GeopoliticalOverviewTabProps {
  stats: OverviewStats | null;
  hotspots: Hotspot[];
  loading: boolean;
  onHotspotClick?: (hotspot: Hotspot) => void;
}

export function GeopoliticalOverviewTab({
  stats,
  hotspots,
  loading,
  onHotspotClick,
}: GeopoliticalOverviewTabProps) {
  if (loading || !stats) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-pulse text-gray-500 dark:text-gray-400">Loading overview...</div>
      </div>
    );
  }

  // Prepare risk level data for pie chart
  const riskLevelData = Object.entries(stats.by_risk_level)
    .filter(([_, count]) => count > 0)
    .map(([level, count]) => ({
      name: level.charAt(0).toUpperCase() + level.slice(1),
      value: count,
      color: RISK_COLORS[level as RiskLevel],
    }));

  // Prepare category data for bar chart
  const categoryData = Object.entries(stats.by_category)
    .slice(0, 8)
    .map(([category, count]) => ({
      category: category.charAt(0).toUpperCase() + category.slice(1),
      count,
    }));

  return (
    <div className="space-y-6">
      {/* Stats Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
        <StatCard
          icon={<AlertTriangle className="w-5 h-5" />}
          label="Total Hotspots"
          value={stats.total_hotspots}
          color="text-amber-500"
        />
        <StatCard
          icon={<MapPin className="w-5 h-5" />}
          label="Countries"
          value={stats.countries_affected}
          color="text-blue-500"
        />
        <StatCard
          icon={<Newspaper className="w-5 h-5" />}
          label="Total Articles"
          value={stats.total_articles}
          color="text-purple-500"
        />
        <StatCard
          icon={<Globe className="w-5 h-5" />}
          label="Recent Articles"
          value={stats.recent_articles}
          subtitle="Last 7 days"
          color="text-green-500"
        />
        <StatCard
          icon={<TrendingUp className="w-5 h-5" />}
          label="Escalating"
          value={stats.escalating_count}
          color="text-red-500"
        />
        <StatCard
          icon={<TrendingDown className="w-5 h-5" />}
          label="De-escalating"
          value={stats.de_escalating_count}
          color="text-emerald-500"
        />
      </div>

      {/* Risk Level Breakdown */}
      <div className="grid grid-cols-5 gap-2">
        {(['critical', 'high', 'medium', 'low', 'info'] as RiskLevel[]).map((level) => (
          <div
            key={level}
            className="p-3 rounded-lg text-center"
            style={{ backgroundColor: `${RISK_COLORS[level]}20` }}
          >
            <div className="text-2xl font-bold" style={{ color: RISK_COLORS[level] }}>
              {stats.by_risk_level[level] || 0}
            </div>
            <div className="text-xs text-gray-600 dark:text-gray-400 capitalize">{level}</div>
          </div>
        ))}
      </div>

      {/* Main Content Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Mini Map */}
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
          <div className="p-4 border-b border-gray-200 dark:border-gray-700">
            <h3 className="font-semibold text-gray-900 dark:text-gray-100">Global Hotspots</h3>
          </div>
          <HotspotMap hotspots={hotspots} height="300px" onHotspotClick={onHotspotClick} />
        </div>

        {/* Top Hotspots List */}
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
          <div className="p-4 border-b border-gray-200 dark:border-gray-700">
            <h3 className="font-semibold text-gray-900 dark:text-gray-100">Top Hotspots</h3>
          </div>
          <div className="divide-y divide-gray-200 dark:divide-gray-700">
            {stats.top_hotspots.map((hotspot, index) => (
              <div
                key={hotspot.id}
                className="p-3 hover:bg-gray-50 dark:hover:bg-gray-700/50 cursor-pointer transition-colors"
                onClick={() => {
                  const fullHotspot = hotspots.find((h) => h.id === hotspot.id);
                  if (fullHotspot && onHotspotClick) {
                    onHotspotClick(fullHotspot);
                  }
                }}
              >
                <div className="flex items-start gap-3">
                  <span className="text-lg font-bold text-gray-400 dark:text-gray-500 w-6">
                    {index + 1}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="font-medium text-gray-900 dark:text-gray-100 truncate">
                        {hotspot.location_name}
                      </span>
                      <span
                        className="px-1.5 py-0.5 text-[10px] font-medium rounded-full text-white"
                        style={{ backgroundColor: RISK_COLORS[hotspot.risk_level] }}
                      >
                        {hotspot.risk_level.toUpperCase()}
                      </span>
                    </div>
                    <div className="flex items-center gap-3 text-xs text-gray-500 dark:text-gray-400">
                      {hotspot.country_name && <span>{hotspot.country_name}</span>}
                      <span>{hotspot.article_count} articles</span>
                      {hotspot.trend && (
                        <span
                          className={
                            hotspot.trend === 'escalating'
                              ? 'text-red-500'
                              : hotspot.trend === 'de-escalating'
                                ? 'text-green-500'
                                : ''
                          }
                        >
                          {hotspot.trend === 'escalating'
                            ? '↑'
                            : hotspot.trend === 'de-escalating'
                              ? '↓'
                              : '→'}{' '}
                          {hotspot.trend}
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                      {Math.round(hotspot.intensity_score)}
                    </div>
                    <div className="text-[10px] text-gray-500 dark:text-gray-400">intensity</div>
                  </div>
                </div>
              </div>
            ))}
            {stats.top_hotspots.length === 0 && (
              <div className="p-6 text-center text-gray-500 dark:text-gray-400">
                No hotspots found
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Charts Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Risk Level Distribution Pie Chart */}
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
          <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-4">
            Risk Level Distribution
          </h3>
          <ResponsiveContainer width="100%" height={200}>
            <PieChart>
              <Pie
                data={riskLevelData}
                cx="50%"
                cy="50%"
                innerRadius={50}
                outerRadius={80}
                paddingAngle={2}
                dataKey="value"
                label={({ name, value }) => `${name}: ${value}`}
              >
                {riskLevelData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={entry.color} />
                ))}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        </div>

        {/* Category Distribution Bar Chart */}
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
          <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-4">
            Threat Categories
          </h3>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={categoryData} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
              <XAxis type="number" tick={{ fontSize: 12 }} />
              <YAxis
                type="category"
                dataKey="category"
                tick={{ fontSize: 11 }}
                width={80}
              />
              <Tooltip />
              <Bar dataKey="count" fill="#EC4899" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}

// Stat Card Component
interface StatCardProps {
  icon: React.ReactNode;
  label: string;
  value: number;
  subtitle?: string;
  color: string;
}

function StatCard({ icon, label, value, subtitle, color }: StatCardProps) {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
      <div className={`${color} mb-2`}>{icon}</div>
      <div className="text-2xl font-bold text-gray-900 dark:text-gray-100">{value.toLocaleString()}</div>
      <div className="text-sm text-gray-600 dark:text-gray-400">{label}</div>
      {subtitle && <div className="text-xs text-gray-500 dark:text-gray-500">{subtitle}</div>}
    </div>
  );
}
