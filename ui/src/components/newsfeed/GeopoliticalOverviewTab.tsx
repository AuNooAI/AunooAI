/**
 * GeopoliticalOverviewTab Component
 * Overview statistics and mini map for geopolitical hotspots
 */

import { AlertTriangle, TrendingUp, TrendingDown, MapPin, Newspaper, Globe, Flame } from 'lucide-react';
import { HotspotMap } from './map';
import type { OverviewStats, Hotspot } from '../../services/geopoliticalHotspotsApi';
import { RISK_COLORS, type RiskLevel, THREAT_CATEGORIES } from '../../services/geopoliticalHotspotsApi';
import {
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from 'recharts';

// Category colors for visualization
const CATEGORY_COLORS: Record<string, string> = {
  conflict: '#DC2626',
  protest: '#F97316',
  disaster: '#EAB308',
  diplomatic: '#3B82F6',
  economic: '#8B5CF6',
  terrorism: '#EF4444',
  cyber: '#06B6D4',
  health: '#22C55E',
  environmental: '#10B981',
  military: '#DC2626',
  crime: '#F43F5E',
  piracy: '#0EA5E9',
  infrastructure: '#6366F1',
  commodities: '#A855F7',
};

interface GeopoliticalOverviewTabProps {
  stats: OverviewStats | null;
  hotspots: Hotspot[];
  loading: boolean;
  onHotspotClick?: (hotspot: Hotspot) => void;
  onRiskLevelFilter?: (level: RiskLevel) => void;
  onCategoryFilter?: (category: string) => void;
}

export function GeopoliticalOverviewTab({
  stats,
  hotspots,
  loading,
  onHotspotClick,
  onRiskLevelFilter,
  onCategoryFilter,
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

  // Prepare category data for bar chart (top 8 for the chart)
  const categoryData = Object.entries(stats.by_category)
    .slice(0, 8)
    .map(([category, count]) => ({
      category: category.charAt(0).toUpperCase() + category.slice(1),
      count,
    }));

  // Full category data for breakdown section (all categories)
  const totalCategoryCount = Object.values(stats.by_category).reduce((a, b) => a + b, 0);
  const fullCategoryData = Object.entries(stats.by_category)
    .sort((a, b) => b[1] - a[1])
    .map(([category, count]) => ({
      category,
      count,
      percentage: totalCategoryCount > 0 ? (count / totalCategoryCount) * 100 : 0,
    }));

  // Most active category
  const mostActiveCategory = fullCategoryData.length > 0 ? fullCategoryData[0] : null;

  return (
    <div className="space-y-6">
      {/* Stats Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-4">
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
        {mostActiveCategory && (
          <button
            onClick={() => onCategoryFilter?.(mostActiveCategory.category)}
            className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 text-left hover:ring-2 hover:ring-pink-500 transition-all"
          >
            <div className="text-pink-500 mb-2"><Flame className="w-5 h-5" /></div>
            <div className="text-sm font-semibold text-gray-900 dark:text-gray-100 capitalize truncate">
              {mostActiveCategory.category}
            </div>
            <div className="text-sm text-gray-600 dark:text-gray-400">Most Active</div>
            <div className="text-xs text-gray-500 dark:text-gray-500">
              {mostActiveCategory.count} hotspots ({mostActiveCategory.percentage.toFixed(0)}%)
            </div>
          </button>
        )}
      </div>

      {/* Risk Level Breakdown - Clickable Cards */}
      <div className="grid grid-cols-5 gap-2">
        {(['critical', 'high', 'medium', 'low', 'info'] as RiskLevel[]).map((level) => (
          <button
            key={level}
            onClick={() => onRiskLevelFilter?.(level)}
            className="p-3 rounded-lg text-center transition-all hover:ring-2 hover:scale-105 cursor-pointer"
            style={{
              backgroundColor: `${RISK_COLORS[level]}20`,
              '--tw-ring-color': RISK_COLORS[level],
            } as React.CSSProperties}
            title={`Filter by ${level} risk level`}
          >
            <div className="text-2xl font-bold" style={{ color: RISK_COLORS[level] }}>
              {stats.by_risk_level[level] || 0}
            </div>
            <div className="text-xs text-gray-600 dark:text-gray-400 capitalize">{level}</div>
          </button>
        ))}
      </div>

      {/* Main Content Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Mini Map */}
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden flex flex-col" style={{ minHeight: '400px' }}>
          <div className="p-4 border-b border-gray-200 dark:border-gray-700">
            <h3 className="font-semibold text-gray-900 dark:text-gray-100">Overview Map</h3>
          </div>
          <div className="flex-1">
            <HotspotMap hotspots={hotspots} height="100%" onHotspotClick={onHotspotClick} />
          </div>
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

      {/* Risk Level Pie Chart - Full Width */}
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
        <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-4">
          Risk Level Distribution
        </h3>
        <p className="text-xs text-gray-500 dark:text-gray-400 mb-2 -mt-2">
          Click a segment to filter by risk level
        </p>
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
              onClick={(data) => {
                if (onRiskLevelFilter && data?.name) {
                  onRiskLevelFilter(data.name.toLowerCase() as RiskLevel);
                }
              }}
              cursor="pointer"
            >
              {riskLevelData.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={entry.color} />
              ))}
            </Pie>
            <Tooltip
              formatter={(value: number, name: string) => [
                `${value} hotspots`,
                name,
              ]}
              contentStyle={{
                backgroundColor: 'rgba(31, 41, 55, 0.95)',
                border: 'none',
                borderRadius: '0.5rem',
                color: '#F9FAFB',
              }}
            />
          </PieChart>
        </ResponsiveContainer>
      </div>

      {/* Full Category Breakdown */}
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
        <div className="p-4 border-b border-gray-200 dark:border-gray-700">
          <h3 className="font-semibold text-gray-900 dark:text-gray-100">Category Distribution</h3>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
            Click a category to filter articles
          </p>
        </div>
        <div className="divide-y divide-gray-200 dark:divide-gray-700">
          {fullCategoryData.map(({ category, count, percentage }) => (
            <button
              key={category}
              onClick={() => onCategoryFilter?.(category)}
              className="w-full p-3 hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors text-left flex items-center gap-3"
            >
              <div
                className="w-3 h-3 rounded-full flex-shrink-0"
                style={{ backgroundColor: CATEGORY_COLORS[category] || '#6B7280' }}
              />
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between mb-1">
                  <span className="font-medium text-gray-900 dark:text-gray-100 capitalize">
                    {category}
                  </span>
                  <span className="text-sm text-gray-600 dark:text-gray-400">
                    {count} hotspots ({percentage.toFixed(1)}%)
                  </span>
                </div>
                <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-1.5">
                  <div
                    className="h-1.5 rounded-full transition-all"
                    style={{
                      width: `${percentage}%`,
                      backgroundColor: CATEGORY_COLORS[category] || '#6B7280',
                    }}
                  />
                </div>
              </div>
            </button>
          ))}
          {fullCategoryData.length === 0 && (
            <div className="p-6 text-center text-gray-500 dark:text-gray-400">
              No categories found
            </div>
          )}
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
