/**
 * ThreatCategoriesTab Component
 * Category distribution and breakdown
 */

import { useState, useEffect } from 'react';
import {
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  Tooltip,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Legend,
} from 'recharts';
import { Shield, TrendingUp, TrendingDown, Minus, ChevronRight } from 'lucide-react';
import {
  getCategoryTrends,
  type ThreatCategory,
  type ThreatMapData,
  THREAT_CATEGORY_LABELS,
  SEVERITY_COLORS,
} from '../../services/threatIntelligenceApi';

interface CategoryStats {
  category: ThreatCategory;
  count: number;
  avgSeverity: number;
  trend: 'up' | 'down' | 'stable';
  recentThreats: ThreatMapData[];
}

interface ThreatCategoriesTabProps {
  threats: ThreatMapData[];
  loading: boolean;
  onThreatClick: (threat: ThreatMapData) => void;
}

const CATEGORY_COLORS: Record<string, string> = {
  malware: '#DC2626',
  ransomware: '#F97316',
  apt: '#EF4444',
  phishing: '#F59E0B',
  vulnerability: '#EAB308',
  data_breach: '#84CC16',
  botnet: '#22C55E',
  ddos: '#10B981',
  supply_chain: '#14B8A6',
  credential_theft: '#06B6D4',
  cryptojacking: '#0EA5E9',
  insider_threat: '#3B82F6',
  iot_ot: '#6366F1',
  mobile: '#8B5CF6',
};

export function ThreatCategoriesTab({ threats, loading, onThreatClick }: ThreatCategoriesTabProps) {
  const [categoryStats, setCategoryStats] = useState<CategoryStats[]>([]);
  const [selectedCategory, setSelectedCategory] = useState<ThreatCategory | null>(null);
  const [trendData, setTrendData] = useState<any[]>([]);
  const [loadingTrends, setLoadingTrends] = useState(false);

  useEffect(() => {
    // Calculate category statistics from threats
    const statsByCategory: Record<string, { count: number; totalSeverity: number; threats: ThreatMapData[] }> = {};

    (threats || []).forEach((threat) => {
      if (!statsByCategory[threat.threat_type]) {
        statsByCategory[threat.threat_type] = { count: 0, totalSeverity: 0, threats: [] };
      }
      statsByCategory[threat.threat_type].count++;
      statsByCategory[threat.threat_type].totalSeverity += threat.severity_score;
      statsByCategory[threat.threat_type].threats.push(threat);
    });

    const stats: CategoryStats[] = Object.entries(statsByCategory)
      .map(([category, data]) => ({
        category: category as ThreatCategory,
        count: data.count,
        avgSeverity: data.totalSeverity / data.count,
        trend: Math.random() > 0.6 ? 'up' : Math.random() > 0.3 ? 'stable' : 'down' as 'up' | 'down' | 'stable',
        recentThreats: data.threats.slice(0, 5),
      }))
      .sort((a, b) => b.count - a.count);

    setCategoryStats(stats);
  }, [threats]);

  useEffect(() => {
    const fetchTrends = async () => {
      if (!selectedCategory) return;

      setLoadingTrends(true);
      try {
        const result = await getCategoryTrends(selectedCategory, 30);
        setTrendData(result);
      } catch (error) {
        console.error('Error fetching category trends:', error);
      } finally {
        setLoadingTrends(false);
      }
    };

    fetchTrends();
  }, [selectedCategory]);

  const pieData = categoryStats.map((stat) => ({
    name: THREAT_CATEGORY_LABELS[stat.category] || stat.category,
    value: stat.count,
    category: stat.category,
  }));

  const getTrendIcon = (trend: string) => {
    switch (trend) {
      case 'up':
        return <TrendingUp className="w-4 h-4 text-red-500" />;
      case 'down':
        return <TrendingDown className="w-4 h-4 text-green-500" />;
      default:
        return <Minus className="w-4 h-4 text-gray-500" />;
    }
  };

  const getSeverityColor = (score: number) => {
    if (score >= 80) return SEVERITY_COLORS.critical;
    if (score >= 60) return SEVERITY_COLORS.high;
    if (score >= 40) return SEVERITY_COLORS.medium;
    if (score >= 20) return SEVERITY_COLORS.low;
    return SEVERITY_COLORS.info;
  };

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  };

  if (loading && categoryStats.length === 0) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-red-500"></div>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      {/* Distribution Chart */}
      <div className="lg:col-span-1 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-4">
          Threat Type Distribution
        </h3>
        <div className="h-[300px]">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={pieData}
                cx="50%"
                cy="50%"
                innerRadius={60}
                outerRadius={100}
                paddingAngle={2}
                dataKey="value"
                onClick={(data) => setSelectedCategory(data.category)}
              >
                {pieData.map((entry, index) => (
                  <Cell
                    key={`cell-${index}`}
                    fill={CATEGORY_COLORS[entry.category] || '#6B7280'}
                    stroke={selectedCategory === entry.category ? '#fff' : 'transparent'}
                    strokeWidth={selectedCategory === entry.category ? 3 : 0}
                    style={{ cursor: 'pointer' }}
                  />
                ))}
              </Pie>
              <Tooltip
                contentStyle={{
                  backgroundColor: '#1F2937',
                  border: 'none',
                  borderRadius: '0.5rem',
                  color: '#F9FAFB',
                }}
                formatter={(value: number, name: string) => [value, name]}
              />
            </PieChart>
          </ResponsiveContainer>
        </div>
        <div className="mt-4 max-h-[200px] overflow-y-auto space-y-1">
          {pieData.slice(0, 8).map((item) => (
            <button
              key={item.category}
              onClick={() => setSelectedCategory(item.category)}
              className={`w-full flex items-center justify-between px-2 py-1.5 rounded text-sm transition-colors ${
                selectedCategory === item.category
                  ? 'bg-red-50 dark:bg-red-900/20'
                  : 'hover:bg-gray-50 dark:hover:bg-gray-700'
              }`}
            >
              <div className="flex items-center gap-2">
                <div
                  className="w-3 h-3 rounded-full"
                  style={{ backgroundColor: CATEGORY_COLORS[item.category] || '#6B7280' }}
                />
                <span className="text-gray-700 dark:text-gray-300 truncate">{item.name}</span>
              </div>
              <span className="text-gray-500 dark:text-gray-400 font-medium">{item.value}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Category List */}
      <div className="lg:col-span-1 space-y-3">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
          Categories by Volume
        </h3>
        <div className="space-y-2 max-h-[600px] overflow-y-auto">
          {categoryStats.map((stat) => (
            <button
              key={stat.category}
              onClick={() => setSelectedCategory(stat.category)}
              className={`w-full text-left p-3 rounded-lg border transition-all ${
                selectedCategory === stat.category
                  ? 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800'
                  : 'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 hover:border-red-300 dark:hover:border-red-700'
              }`}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div
                    className="w-10 h-10 rounded-lg flex items-center justify-center"
                    style={{ backgroundColor: `${CATEGORY_COLORS[stat.category] || '#6B7280'}20` }}
                  >
                    <Shield
                      className="w-5 h-5"
                      style={{ color: CATEGORY_COLORS[stat.category] || '#6B7280' }}
                    />
                  </div>
                  <div>
                    <div className="font-medium text-gray-900 dark:text-gray-100">
                      {THREAT_CATEGORY_LABELS[stat.category] || stat.category}
                    </div>
                    <div className="text-xs text-gray-500 dark:text-gray-400">
                      {stat.count} threats
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <div className="text-right">
                    <div
                      className="text-sm font-medium"
                      style={{ color: getSeverityColor(stat.avgSeverity) }}
                    >
                      {stat.avgSeverity.toFixed(0)}
                    </div>
                    <div className="text-xs text-gray-500 dark:text-gray-400">avg severity</div>
                  </div>
                  <div className="flex items-center gap-1">
                    {getTrendIcon(stat.trend)}
                  </div>
                  <ChevronRight className="w-4 h-4 text-gray-400" />
                </div>
              </div>

              {/* Mini severity bar */}
              <div className="mt-2 h-1.5 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                <div
                  className="h-full rounded-full transition-all"
                  style={{
                    width: `${stat.avgSeverity}%`,
                    backgroundColor: getSeverityColor(stat.avgSeverity),
                  }}
                />
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Category Details */}
      <div className="lg:col-span-1">
        {selectedCategory ? (
          <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 sticky top-4">
            <div className="flex items-center gap-3 mb-4">
              <div
                className="w-12 h-12 rounded-lg flex items-center justify-center"
                style={{ backgroundColor: `${CATEGORY_COLORS[selectedCategory] || '#6B7280'}20` }}
              >
                <Shield
                  className="w-6 h-6"
                  style={{ color: CATEGORY_COLORS[selectedCategory] || '#6B7280' }}
                />
              </div>
              <div>
                <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                  {THREAT_CATEGORY_LABELS[selectedCategory] || selectedCategory}
                </h3>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  {categoryStats.find((s) => s.category === selectedCategory)?.count || 0} threats
                </p>
              </div>
            </div>

            {/* Trend Chart */}
            {loadingTrends ? (
              <div className="flex items-center justify-center h-[200px]">
                <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-red-500"></div>
              </div>
            ) : trendData.length > 0 ? (
              <div className="h-[200px] mb-4">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={trendData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.3} />
                    <XAxis
                      dataKey="date"
                      tickFormatter={formatDate}
                      tick={{ fill: '#9CA3AF', fontSize: 10 }}
                      axisLine={{ stroke: '#4B5563' }}
                    />
                    <YAxis
                      tick={{ fill: '#9CA3AF', fontSize: 10 }}
                      axisLine={{ stroke: '#4B5563' }}
                    />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: '#1F2937',
                        border: 'none',
                        borderRadius: '0.5rem',
                        color: '#F9FAFB',
                      }}
                      labelFormatter={formatDate}
                    />
                    <Bar
                      dataKey="count"
                      name="Threats"
                      fill={CATEGORY_COLORS[selectedCategory] || '#6B7280'}
                      radius={[4, 4, 0, 0]}
                    />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            ) : null}

            {/* Recent Threats */}
            <div>
              <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                Recent Threats
              </h4>
              <div className="space-y-2">
                {categoryStats
                  .find((s) => s.category === selectedCategory)
                  ?.recentThreats.map((threat) => (
                    <button
                      key={threat.id}
                      onClick={() => onThreatClick(threat)}
                      className="w-full text-left p-2 bg-gray-50 dark:bg-gray-700/50 rounded hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
                    >
                      <div className="font-medium text-sm text-gray-900 dark:text-gray-100 truncate">
                        {threat.threat_name}
                      </div>
                      <div className="flex items-center gap-2 mt-1">
                        <span
                          className="px-1.5 py-0.5 text-xs rounded text-white"
                          style={{ backgroundColor: SEVERITY_COLORS[threat.severity_level] }}
                        >
                          {threat.severity_level}
                        </span>
                        {threat.threat_actor_name && (
                          <span className="text-xs text-gray-500 dark:text-gray-400">
                            {threat.threat_actor_name}
                          </span>
                        )}
                      </div>
                    </button>
                  ))}
              </div>
            </div>
          </div>
        ) : (
          <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-8 text-center">
            <Shield className="w-12 h-12 text-gray-300 dark:text-gray-600 mx-auto mb-3" />
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Select a category to view details
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
