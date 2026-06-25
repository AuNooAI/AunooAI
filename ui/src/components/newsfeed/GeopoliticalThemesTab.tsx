/**
 * GeopoliticalThemesTab Component
 * Comprehensive themes analysis with 6 sub-views for geopolitical analysis
 */

import { useState, useEffect, useMemo } from 'react';
import {
  BarChart2,
  TrendingUp,
  Globe,
  Map,
  Users,
  AlertTriangle,
  ArrowUpRight,
  ArrowDownRight,
  ArrowRight,
} from 'lucide-react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
  AreaChart,
  Area,
  LineChart,
  Line,
  Legend,
} from 'recharts';
import {
  getCategoriesData,
  getCountriesData,
  getRegionsData,
  getDailyCounts,
  getCategoryTrends,
  getActors,
  getEscalationMarkers,
  type CategoryData,
  type CountryStats,
  type RegionData,
  type DailyCount,
  type CategoryTrendPeriod,
  type ActorData,
  type EscalationData,
} from '../../services/geopoliticalHotspotsApi';

type ThemeView = 'categories' | 'trends' | 'countries' | 'regions' | 'actors' | 'escalation';

interface GeopoliticalThemesTabProps {
  onCategoryFilter?: (category: string) => void;
}

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

// Actor type colors
const ACTOR_TYPE_COLORS: Record<string, string> = {
  state: '#3B82F6',
  non_state: '#EF4444',
  organization: '#8B5CF6',
  location: '#6B7280',
};

// Escalation marker colors
const ESCALATION_COLORS: Record<string, string> = {
  'Military Buildup': '#DC2626',
  'Diplomatic Breakdown': '#F97316',
  'Economic Sanctions': '#8B5CF6',
  'Civil Unrest': '#EAB308',
  'Armed Conflict': '#EF4444',
  'Terrorist Activity': '#DC2626',
  'Cyber Operations': '#06B6D4',
  Other: '#6B7280',
};

export function GeopoliticalThemesTab({ onCategoryFilter }: GeopoliticalThemesTabProps) {
  const [activeView, setActiveView] = useState<ThemeView>('categories');

  // Data state
  const [categories, setCategories] = useState<CategoryData[]>([]);
  const [countries, setCountries] = useState<CountryStats[]>([]);
  const [regions, setRegions] = useState<RegionData[]>([]);
  const [dailyCounts, setDailyCounts] = useState<DailyCount[]>([]);
  const [categoryTrends, setCategoryTrends] = useState<CategoryTrendPeriod[]>([]);
  const [actors, setActors] = useState<ActorData[]>([]);
  const [escalation, setEscalation] = useState<EscalationData | null>(null);

  // Loading state
  const [loadingCategories, setLoadingCategories] = useState(false);
  const [loadingCountries, setLoadingCountries] = useState(false);
  const [loadingRegions, setLoadingRegions] = useState(false);
  const [loadingDailyCounts, setLoadingDailyCounts] = useState(false);
  const [loadingTrends, setLoadingTrends] = useState(false);
  const [loadingActors, setLoadingActors] = useState(false);
  const [loadingEscalation, setLoadingEscalation] = useState(false);

  // Fetch data based on active view
  useEffect(() => {
    switch (activeView) {
      case 'categories':
        if (categories.length === 0) fetchCategories();
        break;
      case 'trends':
        if (categoryTrends.length === 0) fetchCategoryTrends();
        break;
      case 'countries':
        if (countries.length === 0) fetchCountries();
        break;
      case 'regions':
        if (regions.length === 0) fetchRegions();
        break;
      case 'actors':
        if (actors.length === 0) fetchActors();
        break;
      case 'escalation':
        if (!escalation) fetchEscalation();
        break;
    }
  }, [activeView]);

  const fetchCategories = async () => {
    setLoadingCategories(true);
    try {
      const data = await getCategoriesData();
      setCategories(data);
    } catch (err) {
      console.error('Error fetching categories:', err);
    } finally {
      setLoadingCategories(false);
    }
  };

  const fetchCountries = async () => {
    setLoadingCountries(true);
    try {
      const data = await getCountriesData();
      setCountries(data);
    } catch (err) {
      console.error('Error fetching countries:', err);
    } finally {
      setLoadingCountries(false);
    }
  };

  const fetchRegions = async () => {
    setLoadingRegions(true);
    try {
      const data = await getRegionsData();
      setRegions(data);
    } catch (err) {
      console.error('Error fetching regions:', err);
    } finally {
      setLoadingRegions(false);
    }
  };

  const fetchDailyCounts = async () => {
    setLoadingDailyCounts(true);
    try {
      const data = await getDailyCounts(undefined, 60);
      setDailyCounts(data);
    } catch (err) {
      console.error('Error fetching daily counts:', err);
    } finally {
      setLoadingDailyCounts(false);
    }
  };

  const fetchCategoryTrends = async () => {
    setLoadingTrends(true);
    try {
      const data = await getCategoryTrends(undefined, 90, 'weekly');
      setCategoryTrends(data);
    } catch (err) {
      console.error('Error fetching category trends:', err);
    } finally {
      setLoadingTrends(false);
    }
  };

  const fetchActors = async () => {
    setLoadingActors(true);
    try {
      const data = await getActors(undefined, 30);
      setActors(data);
    } catch (err) {
      console.error('Error fetching actors:', err);
    } finally {
      setLoadingActors(false);
    }
  };

  const fetchEscalation = async () => {
    setLoadingEscalation(true);
    try {
      const data = await getEscalationMarkers(undefined, 30);
      setEscalation(data);
    } catch (err) {
      console.error('Error fetching escalation:', err);
    } finally {
      setLoadingEscalation(false);
    }
  };

  // Prepare category data with intensity indicator
  const categoryChartData = useMemo(() => {
    const totalCount = categories.reduce((sum, c) => sum + c.count, 0);
    return categories
      .filter((c) => c.count > 0)
      .sort((a, b) => b.count - a.count)
      .map((c) => ({
        category: c.category.charAt(0).toUpperCase() + c.category.slice(1),
        rawCategory: c.category,
        count: c.count,
        percentage: totalCount > 0 ? (c.count / totalCount) * 100 : 0,
        articles: c.total_articles,
        intensity: c.avg_intensity,
      }));
  }, [categories]);

  // Prepare trends data for stacked area chart
  const trendsChartData = useMemo(() => {
    if (categoryTrends.length === 0) return [];

    // Get top 6 categories by total count
    const categoryCounts: Record<string, number> = {};
    categoryTrends.forEach((period) => {
      Object.entries(period.by_category).forEach(([cat, count]) => {
        categoryCounts[cat] = (categoryCounts[cat] || 0) + count;
      });
    });
    const topCategories = Object.entries(categoryCounts)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 6)
      .map(([cat]) => cat);

    return categoryTrends.map((period) => {
      const formattedDate = new Date(period.period).toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
      });
      const dataPoint: Record<string, any> = { period: formattedDate };
      topCategories.forEach((cat) => {
        dataPoint[cat] = period.by_category[cat] || 0;
      });
      return dataPoint;
    });
  }, [categoryTrends]);

  // Get top categories for trends legend
  const topTrendCategories = useMemo(() => {
    if (categoryTrends.length === 0) return [];
    const categoryCounts: Record<string, number> = {};
    categoryTrends.forEach((period) => {
      Object.entries(period.by_category).forEach(([cat, count]) => {
        categoryCounts[cat] = (categoryCounts[cat] || 0) + count;
      });
    });
    return Object.entries(categoryCounts)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 6)
      .map(([cat]) => cat);
  }, [categoryTrends]);

  // Prepare countries data
  const countriesChartData = useMemo(() => {
    const byHotspots = [...countries]
      .sort((a, b) => b.total_hotspots - a.total_hotspots)
      .slice(0, 10)
      .map((c) => ({
        country: c.country_name || c.country_code,
        hotspots: c.total_hotspots,
        articles: c.total_articles,
      }));

    const byArticles = [...countries]
      .sort((a, b) => b.total_articles - a.total_articles)
      .slice(0, 10)
      .map((c) => ({
        country: c.country_name || c.country_code,
        hotspots: c.total_hotspots,
        articles: c.total_articles,
      }));

    return { byHotspots, byArticles };
  }, [countries]);

  // Prepare regions data
  const regionsChartData = useMemo(() => {
    return regions
      .filter((r) => r.hotspot_count > 0)
      .sort((a, b) => b.hotspot_count - a.hotspot_count)
      .map((r) => ({
        region: r.region,
        hotspots: r.hotspot_count,
        articles: r.article_count,
      }));
  }, [regions]);

  // Prepare actors data
  const actorsChartData = useMemo(() => {
    return actors.slice(0, 15).map((a) => ({
      actor: a.actor,
      mentions: a.mention_count,
      percentage: a.percentage,
      type: a.actor_type,
    }));
  }, [actors]);

  const loading =
    loadingCategories ||
    loadingCountries ||
    loadingRegions ||
    loadingTrends ||
    loadingActors ||
    loadingEscalation;

  return (
    <div className="space-y-6">
      {/* View Selector */}
      <div className="flex flex-wrap gap-1 bg-gray-100 dark:bg-gray-700 rounded-lg p-0.5">
        {[
          { id: 'categories', label: 'Categories', icon: BarChart2 },
          { id: 'trends', label: 'Trends', icon: TrendingUp },
          { id: 'countries', label: 'Countries', icon: Globe },
          { id: 'regions', label: 'Regions', icon: Map },
          { id: 'actors', label: 'Actors', icon: Users },
          { id: 'escalation', label: 'Escalation', icon: AlertTriangle },
        ].map((view) => (
          <button
            key={view.id}
            onClick={() => setActiveView(view.id as ThemeView)}
            className={`px-3 py-1.5 text-sm font-medium rounded-md transition-colors flex items-center gap-1.5 ${
              activeView === view.id
                ? 'bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 shadow-sm'
                : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200'
            }`}
          >
            <view.icon className="w-4 h-4" />
            <span className="hidden sm:inline">{view.label}</span>
          </button>
        ))}
      </div>

      {/* Categories View */}
      {activeView === 'categories' && (
        <div className="space-y-6">
          {loadingCategories ? (
            <LoadingState message="Loading categories..." />
          ) : (
            <>
              <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
                <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-1">
                  All Threat Categories
                </h3>
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-4">
                  All 14 threat categories with article counts and intensity scores. Click to filter.
                </p>
                <ResponsiveContainer width="100%" height={400}>
                  <BarChart data={categoryChartData} layout="vertical">
                    <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
                    <XAxis type="number" tick={{ fontSize: 12 }} />
                    <YAxis
                      type="category"
                      dataKey="category"
                      tick={{ fontSize: 11 }}
                      width={100}
                    />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: 'rgba(31, 41, 55, 0.95)',
                        border: 'none',
                        borderRadius: '0.5rem',
                        color: '#F9FAFB',
                      }}
                      formatter={(value: number, name: string, props: any) => [
                        `${value} ${name === 'count' ? 'hotspots' : name} (${props.payload.articles} articles, ${props.payload.intensity.toFixed(0)}% intensity)`,
                        '',
                      ]}
                    />
                    <Bar
                      dataKey="count"
                      radius={[0, 4, 4, 0]}
                      cursor="pointer"
                      onClick={(data) => {
                        if (onCategoryFilter) {
                          onCategoryFilter(data.rawCategory);
                        }
                      }}
                    >
                      {categoryChartData.map((entry, index) => (
                        <Cell
                          key={`cell-${index}`}
                          fill={CATEGORY_COLORS[entry.rawCategory] || '#6B7280'}
                        />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>

              {/* Category breakdown list */}
              <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
                <div className="p-4 border-b border-gray-200 dark:border-gray-700">
                  <h3 className="font-semibold text-gray-900 dark:text-gray-100">
                    Category Details
                  </h3>
                </div>
                <div className="divide-y divide-gray-200 dark:divide-gray-700">
                  {categoryChartData.map((item) => (
                    <button
                      key={item.rawCategory}
                      onClick={() => onCategoryFilter?.(item.rawCategory)}
                      className="w-full p-3 hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors text-left flex items-center gap-3"
                    >
                      <div
                        className="w-3 h-3 rounded-full flex-shrink-0"
                        style={{ backgroundColor: CATEGORY_COLORS[item.rawCategory] || '#6B7280' }}
                      />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between mb-1">
                          <span className="font-medium text-gray-900 dark:text-gray-100">
                            {item.category}
                          </span>
                          <span className="text-sm text-gray-600 dark:text-gray-400">
                            {item.count} hotspots ({item.percentage.toFixed(1)}%)
                          </span>
                        </div>
                        <div className="flex items-center gap-4 text-xs text-gray-500 dark:text-gray-400">
                          <span>{item.articles} articles</span>
                          <span
                            className={
                              item.intensity >= 60
                                ? 'text-red-500'
                                : item.intensity >= 40
                                  ? 'text-orange-500'
                                  : 'text-green-500'
                            }
                          >
                            {item.intensity.toFixed(0)}% intensity
                          </span>
                        </div>
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            </>
          )}
        </div>
      )}

      {/* Trends View */}
      {activeView === 'trends' && (
        <div className="space-y-6">
          {loadingTrends ? (
            <LoadingState message="Loading trends..." />
          ) : (
            <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
              <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-1">
                Category Evolution Over Time
              </h3>
              <p className="text-xs text-gray-500 dark:text-gray-400 mb-4">
                Top 6 categories showing weekly article counts over the past 90 days
              </p>
              {trendsChartData.length > 0 ? (
                <ResponsiveContainer width="100%" height={400}>
                  <AreaChart data={trendsChartData}>
                    <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
                    <XAxis dataKey="period" tick={{ fontSize: 11 }} />
                    <YAxis tick={{ fontSize: 12 }} />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: 'rgba(31, 41, 55, 0.95)',
                        border: 'none',
                        borderRadius: '0.5rem',
                        color: '#F9FAFB',
                      }}
                    />
                    <Legend />
                    {topTrendCategories.map((cat, index) => (
                      <Area
                        key={cat}
                        type="monotone"
                        dataKey={cat}
                        stackId="1"
                        stroke={CATEGORY_COLORS[cat] || '#6B7280'}
                        fill={CATEGORY_COLORS[cat] || '#6B7280'}
                        fillOpacity={0.6}
                        name={cat.charAt(0).toUpperCase() + cat.slice(1)}
                      />
                    ))}
                  </AreaChart>
                </ResponsiveContainer>
              ) : (
                <EmptyState message="No trend data available" />
              )}
            </div>
          )}
        </div>
      )}

      {/* Countries View */}
      {activeView === 'countries' && (
        <div className="space-y-6">
          {loadingCountries ? (
            <LoadingState message="Loading countries..." />
          ) : (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* By Hotspots */}
              <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
                <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-1">
                  Top Countries by Hotspots
                </h3>
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-4">
                  Countries with the most active geopolitical hotspots
                </p>
                <ResponsiveContainer width="100%" height={350}>
                  <BarChart data={countriesChartData.byHotspots} layout="vertical">
                    <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
                    <XAxis type="number" tick={{ fontSize: 12 }} />
                    <YAxis
                      type="category"
                      dataKey="country"
                      tick={{ fontSize: 11 }}
                      width={100}
                    />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: 'rgba(31, 41, 55, 0.95)',
                        border: 'none',
                        borderRadius: '0.5rem',
                        color: '#F9FAFB',
                      }}
                      formatter={(value: number, name: string, props: any) => [
                        `${value} ${name} (${props.payload.articles} articles)`,
                        '',
                      ]}
                    />
                    <Bar dataKey="hotspots" fill="#EC4899" radius={[0, 4, 4, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>

              {/* By Articles */}
              <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
                <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-1">
                  Top Countries by Article Count
                </h3>
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-4">
                  Countries with the most coverage in analyzed articles
                </p>
                <ResponsiveContainer width="100%" height={350}>
                  <BarChart data={countriesChartData.byArticles} layout="vertical">
                    <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
                    <XAxis type="number" tick={{ fontSize: 12 }} />
                    <YAxis
                      type="category"
                      dataKey="country"
                      tick={{ fontSize: 11 }}
                      width={100}
                    />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: 'rgba(31, 41, 55, 0.95)',
                        border: 'none',
                        borderRadius: '0.5rem',
                        color: '#F9FAFB',
                      }}
                      formatter={(value: number, name: string, props: any) => [
                        `${value} ${name} (${props.payload.hotspots} hotspots)`,
                        '',
                      ]}
                    />
                    <Bar dataKey="articles" fill="#3B82F6" radius={[0, 4, 4, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Regions View */}
      {activeView === 'regions' && (
        <div className="space-y-6">
          {loadingRegions ? (
            <LoadingState message="Loading regions..." />
          ) : (
            <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
              <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-1">
                Regional Distribution
              </h3>
              <p className="text-xs text-gray-500 dark:text-gray-400 mb-4">
                Hotspots and articles by geographic region
              </p>
              {regionsChartData.length > 0 ? (
                <ResponsiveContainer width="100%" height={350}>
                  <BarChart data={regionsChartData} layout="vertical">
                    <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
                    <XAxis type="number" tick={{ fontSize: 12 }} />
                    <YAxis
                      type="category"
                      dataKey="region"
                      tick={{ fontSize: 11 }}
                      width={120}
                    />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: 'rgba(31, 41, 55, 0.95)',
                        border: 'none',
                        borderRadius: '0.5rem',
                        color: '#F9FAFB',
                      }}
                      formatter={(value: number, name: string) => [
                        `${value} ${name}`,
                        name.charAt(0).toUpperCase() + name.slice(1),
                      ]}
                    />
                    <Legend />
                    <Bar
                      dataKey="hotspots"
                      fill="#EC4899"
                      name="Hotspots"
                      radius={[0, 4, 4, 0]}
                    />
                    <Bar
                      dataKey="articles"
                      fill="#3B82F6"
                      name="Articles"
                      radius={[0, 4, 4, 0]}
                    />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <EmptyState message="No regional data available" />
              )}
            </div>
          )}
        </div>
      )}

      {/* Actors View */}
      {activeView === 'actors' && (
        <div className="space-y-6">
          {loadingActors ? (
            <LoadingState message="Loading actors..." />
          ) : (
            <>
              <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
                <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-1">
                  Key Actors & Entities
                </h3>
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-4">
                  Countries, organizations, and groups mentioned in geopolitical coverage
                </p>
                {actorsChartData.length > 0 ? (
                  <ResponsiveContainer width="100%" height={400}>
                    <BarChart data={actorsChartData} layout="vertical">
                      <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
                      <XAxis type="number" tick={{ fontSize: 12 }} />
                      <YAxis
                        type="category"
                        dataKey="actor"
                        tick={{ fontSize: 11 }}
                        width={120}
                      />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: 'rgba(31, 41, 55, 0.95)',
                          border: 'none',
                          borderRadius: '0.5rem',
                          color: '#F9FAFB',
                        }}
                        formatter={(value: number, name: string, props: any) => [
                          `${value} mentions (${props.payload.percentage}%)`,
                          props.payload.type,
                        ]}
                      />
                      <Bar dataKey="mentions" radius={[0, 4, 4, 0]}>
                        {actorsChartData.map((entry, index) => (
                          <Cell
                            key={`cell-${index}`}
                            fill={ACTOR_TYPE_COLORS[entry.type] || '#6B7280'}
                          />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                ) : (
                  <EmptyState message="No actor data available" />
                )}
              </div>

              {/* Actor type legend */}
              <div className="flex flex-wrap gap-4 px-4">
                {Object.entries(ACTOR_TYPE_COLORS).map(([type, color]) => (
                  <div key={type} className="flex items-center gap-2">
                    <div
                      className="w-3 h-3 rounded-full"
                      style={{ backgroundColor: color }}
                    />
                    <span className="text-sm text-gray-600 dark:text-gray-400 capitalize">
                      {type.replace('_', ' ')}
                    </span>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      )}

      {/* Escalation View */}
      {activeView === 'escalation' && (
        <div className="space-y-6">
          {loadingEscalation ? (
            <LoadingState message="Loading escalation data..." />
          ) : escalation ? (
            <>
              {/* Escalation Markers */}
              <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
                <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-1">
                  Escalation Indicators
                </h3>
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-4">
                  Types of escalation markers detected in article analysis
                </p>
                {escalation.markers.length > 0 ? (
                  <ResponsiveContainer width="100%" height={300}>
                    <BarChart data={escalation.markers} layout="vertical">
                      <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
                      <XAxis type="number" tick={{ fontSize: 12 }} />
                      <YAxis
                        type="category"
                        dataKey="marker_type"
                        tick={{ fontSize: 11 }}
                        width={140}
                      />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: 'rgba(31, 41, 55, 0.95)',
                          border: 'none',
                          borderRadius: '0.5rem',
                          color: '#F9FAFB',
                        }}
                        formatter={(value: number, name: string, props: any) => [
                          `${value} articles (${props.payload.percentage}%)`,
                          '',
                        ]}
                      />
                      <Bar dataKey="article_count" radius={[0, 4, 4, 0]}>
                        {escalation.markers.map((entry, index) => (
                          <Cell
                            key={`cell-${index}`}
                            fill={ESCALATION_COLORS[entry.marker_type] || '#6B7280'}
                          />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                ) : (
                  <EmptyState message="No escalation markers found" />
                )}
              </div>

              {/* Escalation Trends */}
              <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
                <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-1">
                  Escalation Trends
                </h3>
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-4">
                  Weekly intensity and escalation activity over time
                </p>
                {escalation.trends.length > 0 ? (
                  <ResponsiveContainer width="100%" height={300}>
                    <LineChart data={escalation.trends}>
                      <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
                      <XAxis dataKey="period" tick={{ fontSize: 11 }} />
                      <YAxis tick={{ fontSize: 12 }} />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: 'rgba(31, 41, 55, 0.95)',
                          border: 'none',
                          borderRadius: '0.5rem',
                          color: '#F9FAFB',
                        }}
                      />
                      <Legend />
                      <Line
                        type="monotone"
                        dataKey="avg_intensity"
                        stroke="#EC4899"
                        strokeWidth={2}
                        dot={{ fill: '#EC4899', strokeWidth: 2 }}
                        name="Avg Intensity"
                      />
                      <Line
                        type="monotone"
                        dataKey="total_articles"
                        stroke="#3B82F6"
                        strokeWidth={2}
                        dot={{ fill: '#3B82F6', strokeWidth: 2 }}
                        name="Articles"
                      />
                      <Line
                        type="monotone"
                        dataKey="escalating_count"
                        stroke="#EF4444"
                        strokeWidth={2}
                        dot={{ fill: '#EF4444', strokeWidth: 2 }}
                        name="Escalating"
                      />
                    </LineChart>
                  </ResponsiveContainer>
                ) : (
                  <EmptyState message="No escalation trend data available" />
                )}
              </div>
            </>
          ) : (
            <EmptyState message="No escalation data available" />
          )}
        </div>
      )}
    </div>
  );
}

// Loading state component
function LoadingState({ message }: { message: string }) {
  return (
    <div className="flex items-center justify-center h-64">
      <div className="animate-pulse text-gray-500 dark:text-gray-400">{message}</div>
    </div>
  );
}

// Empty state component
function EmptyState({ message }: { message: string }) {
  return (
    <div className="flex flex-col items-center justify-center h-64 text-center">
      <BarChart2 className="w-12 h-12 text-gray-400 dark:text-gray-600 mb-4" />
      <p className="text-gray-500 dark:text-gray-400">{message}</p>
    </div>
  );
}
