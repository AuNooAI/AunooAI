/**
 * ScienceWatch Themes Tab
 * Thematic analysis: themes, entities, geography, escalation markers
 */

import { useState, useEffect } from 'react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  AreaChart,
  Area,
  Legend,
  LineChart,
  Line,
  PieChart,
  Pie,
  Cell,
} from 'recharts';
import { Loader2 } from 'lucide-react';
import { ChartDownloadButton } from './ChartDownloadButton';
import type {
  ThemeData,
  ThemeEvolution,
  EntityData,
  GeographyData,
  EscalationMarkerData,
  EscalationTrend,
} from '../../services/scienceFundingApi';
import { THEME_COLORS, ESCALATION_COLORS } from '../../services/scienceFundingApi';

interface ScienceThemesTabProps {
  themes: ThemeData[];
  themesEvolution: ThemeEvolution[];
  entities: EntityData[];
  geography: GeographyData[];
  escalationMarkers: EscalationMarkerData[];
  escalationTrends: EscalationTrend[];
  loadingThemes: boolean;
  loadingEntities: boolean;
  loadingGeography: boolean;
  loadingEscalation: boolean;
  onLoadThemes: () => void;
  onLoadEntities: () => void;
  onLoadGeography: () => void;
  onLoadEscalation: () => void;
}

type ThemeView = 'themes' | 'evolution' | 'entities' | 'geography' | 'escalation';

export function ScienceThemesTab({
  themes,
  themesEvolution,
  entities,
  geography,
  escalationMarkers,
  escalationTrends,
  loadingThemes,
  loadingEntities,
  loadingGeography,
  loadingEscalation,
  onLoadThemes,
  onLoadEntities,
  onLoadGeography,
  onLoadEscalation,
}: ScienceThemesTabProps) {
  const [activeView, setActiveView] = useState<ThemeView>('themes');

  // Load data on mount and view change
  useEffect(() => {
    if (activeView === 'themes' || activeView === 'evolution') {
      if (themes.length === 0) onLoadThemes();
    } else if (activeView === 'entities') {
      if (entities.length === 0) onLoadEntities();
    } else if (activeView === 'geography') {
      if (geography.length === 0) onLoadGeography();
    } else if (activeView === 'escalation') {
      if (escalationMarkers.length === 0) onLoadEscalation();
    }
  }, [activeView]);

  const isLoading =
    (activeView === 'themes' || activeView === 'evolution') && loadingThemes ||
    activeView === 'entities' && loadingEntities ||
    activeView === 'geography' && loadingGeography ||
    activeView === 'escalation' && loadingEscalation;

  // Get top 6 themes for evolution chart
  const topThemes = [...themes]
    .sort((a, b) => b.article_count - a.article_count)
    .slice(0, 6)
    .map(t => t.theme);

  // Transform evolution data for stacked chart
  const evolutionStackedData = themesEvolution.map((item) => ({
    month: item.month,
    ...item.by_theme,
  }));

  // Split geography into domestic and international
  const domesticGeo = geography.filter(g => g.location_type === 'domestic');
  const internationalGeo = geography.filter(g => g.location_type === 'international');

  return (
    <div className="space-y-6">
      {/* View Selector */}
      <div id="chart-science-themes" className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100">
              Thematic Analysis
            </h3>
            <ChartDownloadButton targetId="chart-science-themes" filename="science-thematic-analysis" />
          </div>
          <div className="flex gap-1 bg-gray-100 dark:bg-gray-700 rounded-lg p-0.5">
            <button
              onClick={() => setActiveView('themes')}
              className={`px-2.5 py-1 text-xs font-medium rounded-md transition-colors ${
                activeView === 'themes'
                  ? 'bg-white dark:bg-gray-600 text-gray-900 dark:text-gray-100 shadow-sm'
                  : 'text-gray-600 dark:text-gray-300'
              }`}
            >
              Themes
            </button>
            <button
              onClick={() => setActiveView('evolution')}
              className={`px-2.5 py-1 text-xs font-medium rounded-md transition-colors ${
                activeView === 'evolution'
                  ? 'bg-white dark:bg-gray-600 text-gray-900 dark:text-gray-100 shadow-sm'
                  : 'text-gray-600 dark:text-gray-300'
              }`}
            >
              Evolution
            </button>
            <button
              onClick={() => setActiveView('entities')}
              className={`px-2.5 py-1 text-xs font-medium rounded-md transition-colors ${
                activeView === 'entities'
                  ? 'bg-white dark:bg-gray-600 text-gray-900 dark:text-gray-100 shadow-sm'
                  : 'text-gray-600 dark:text-gray-300'
              }`}
            >
              Entities
            </button>
            <button
              onClick={() => setActiveView('geography')}
              className={`px-2.5 py-1 text-xs font-medium rounded-md transition-colors ${
                activeView === 'geography'
                  ? 'bg-white dark:bg-gray-600 text-gray-900 dark:text-gray-100 shadow-sm'
                  : 'text-gray-600 dark:text-gray-300'
              }`}
            >
              Geography
            </button>
            <button
              onClick={() => setActiveView('escalation')}
              className={`px-2.5 py-1 text-xs font-medium rounded-md transition-colors ${
                activeView === 'escalation'
                  ? 'bg-white dark:bg-gray-600 text-gray-900 dark:text-gray-100 shadow-sm'
                  : 'text-gray-600 dark:text-gray-300'
              }`}
            >
              Escalation
            </button>
          </div>
        </div>

        {isLoading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 className="w-6 h-6 animate-spin text-emerald-500" />
            <span className="ml-2 text-gray-500 dark:text-gray-300">Loading...</span>
          </div>
        ) : (
          <>
            {/* Theme Frequency */}
            {activeView === 'themes' && (
              <div>
                <p className="text-xs text-gray-500 dark:text-gray-300 mb-4">
                  Article counts by theme (keyword-based detection)
                </p>
                <ResponsiveContainer width="100%" height={350}>
                  <BarChart
                    data={themes}
                    layout="vertical"
                    margin={{ top: 5, right: 30, left: 120, bottom: 5 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.3} />
                    <XAxis type="number" stroke="#9CA3AF" fontSize={12} />
                    <YAxis
                      type="category"
                      dataKey="theme"
                      stroke="#9CA3AF"
                      fontSize={11}
                      width={115}
                    />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: '#1F2937',
                        border: 'none',
                        borderRadius: '8px',
                        color: '#F9FAFB',
                      }}
                      formatter={(value: number, name: string, props: any) => [
                        `${value} articles (${props.payload.percentage}%)`,
                        'Count'
                      ]}
                    />
                    <Bar
                      dataKey="article_count"
                      radius={[0, 4, 4, 0]}
                      fill="#10B981"
                    >
                      {themes.map((entry, index) => (
                        <Cell
                          key={`cell-${index}`}
                          fill={THEME_COLORS[entry.theme] || '#6B7280'}
                        />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}

            {/* Theme Evolution */}
            {activeView === 'evolution' && (
              <div>
                <p className="text-xs text-gray-500 dark:text-gray-300 mb-4">
                  Theme evolution over time (top 6 themes)
                </p>
                <ResponsiveContainer width="100%" height={350}>
                  <AreaChart
                    data={evolutionStackedData}
                    margin={{ top: 5, right: 30, left: 20, bottom: 5 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.3} />
                    <XAxis dataKey="month" stroke="#9CA3AF" fontSize={12} />
                    <YAxis stroke="#9CA3AF" fontSize={12} />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: '#1F2937',
                        border: 'none',
                        borderRadius: '8px',
                        color: '#F9FAFB',
                      }}
                    />
                    <Legend wrapperStyle={{ fontSize: '11px' }} />
                    {topThemes.map((theme) => (
                      <Area
                        key={theme}
                        type="monotone"
                        dataKey={theme}
                        stackId="1"
                        stroke={THEME_COLORS[theme] || '#6B7280'}
                        fill={THEME_COLORS[theme] || '#6B7280'}
                        fillOpacity={0.6}
                      />
                    ))}
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            )}

            {/* Entities */}
            {activeView === 'entities' && (
              <div>
                <p className="text-xs text-gray-500 dark:text-gray-300 mb-4">
                  Research institutions and organizations mentioned
                </p>
                <ResponsiveContainer width="100%" height={350}>
                  <BarChart
                    data={entities.slice(0, 12)}
                    margin={{ top: 5, right: 30, left: 20, bottom: 5 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.3} />
                    <XAxis dataKey="entity" stroke="#9CA3AF" fontSize={10} angle={-45} textAnchor="end" height={80} />
                    <YAxis stroke="#9CA3AF" fontSize={12} />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: '#1F2937',
                        border: 'none',
                        borderRadius: '8px',
                        color: '#F9FAFB',
                      }}
                      formatter={(value: number, name: string, props: any) => [
                        `${value} mentions (${props.payload.percentage}%)`,
                        'Mentions'
                      ]}
                    />
                    <Bar dataKey="mention_count" fill="#0D9488" name="Mentions" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}

            {/* Geography */}
            {activeView === 'geography' && (
              <div>
                <p className="text-xs text-gray-500 dark:text-gray-300 mb-4">
                  Geographic focus: domestic vs international locations
                </p>
                <div className="grid grid-cols-2 gap-4">
                  {/* Domestic */}
                  <div>
                    <h4 className="text-xs font-medium text-gray-700 dark:text-gray-300 mb-2">
                      Domestic (US States)
                    </h4>
                    <ResponsiveContainer width="100%" height={300}>
                      <BarChart
                        data={domesticGeo.slice(0, 8)}
                        layout="vertical"
                        margin={{ top: 5, right: 20, left: 80, bottom: 5 }}
                      >
                        <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.3} />
                        <XAxis type="number" stroke="#9CA3AF" fontSize={10} />
                        <YAxis type="category" dataKey="location" stroke="#9CA3AF" fontSize={10} width={75} />
                        <Tooltip
                          contentStyle={{
                            backgroundColor: '#1F2937',
                            border: 'none',
                            borderRadius: '8px',
                            color: '#F9FAFB',
                          }}
                        />
                        <Bar dataKey="mention_count" fill="#10B981" radius={[0, 4, 4, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                  {/* International */}
                  <div>
                    <h4 className="text-xs font-medium text-gray-700 dark:text-gray-300 mb-2">
                      International
                    </h4>
                    <ResponsiveContainer width="100%" height={300}>
                      <BarChart
                        data={internationalGeo.slice(0, 8)}
                        layout="vertical"
                        margin={{ top: 5, right: 20, left: 80, bottom: 5 }}
                      >
                        <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.3} />
                        <XAxis type="number" stroke="#9CA3AF" fontSize={10} />
                        <YAxis type="category" dataKey="location" stroke="#9CA3AF" fontSize={10} width={75} />
                        <Tooltip
                          contentStyle={{
                            backgroundColor: '#1F2937',
                            border: 'none',
                            borderRadius: '8px',
                            color: '#F9FAFB',
                          }}
                        />
                        <Bar dataKey="mention_count" fill="#0D9488" radius={[0, 4, 4, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              </div>
            )}

            {/* Escalation Markers */}
            {activeView === 'escalation' && (
              <div className="space-y-6">
                <div>
                  <p className="text-xs text-gray-500 dark:text-gray-300 mb-4">
                    Escalation markers: language indicating intensification
                  </p>
                  <ResponsiveContainer width="100%" height={250}>
                    <BarChart
                      data={escalationMarkers}
                      margin={{ top: 5, right: 30, left: 20, bottom: 5 }}
                    >
                      <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.3} />
                      <XAxis dataKey="marker_type" stroke="#9CA3AF" fontSize={11} />
                      <YAxis stroke="#9CA3AF" fontSize={12} />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: '#1F2937',
                          border: 'none',
                          borderRadius: '8px',
                          color: '#F9FAFB',
                        }}
                        formatter={(value: number, name: string, props: any) => [
                          `${value} articles (${props.payload.percentage}%)`,
                          'Count'
                        ]}
                      />
                      <Bar dataKey="article_count" radius={[4, 4, 0, 0]}>
                        {escalationMarkers.map((entry, index) => (
                          <Cell
                            key={`cell-${index}`}
                            fill={ESCALATION_COLORS[entry.marker_type] || '#EF4444'}
                          />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>

                {/* Escalation Trends */}
                {escalationTrends.length > 0 && (
                  <div>
                    <p className="text-xs text-gray-500 dark:text-gray-300 mb-4">
                      Escalation marker trends over time
                    </p>
                    <ResponsiveContainer width="100%" height={250}>
                      <LineChart
                        data={escalationTrends}
                        margin={{ top: 5, right: 30, left: 20, bottom: 5 }}
                      >
                        <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.3} />
                        <XAxis dataKey="period" stroke="#9CA3AF" fontSize={12} />
                        <YAxis stroke="#9CA3AF" fontSize={12} />
                        <Tooltip
                          contentStyle={{
                            backgroundColor: '#1F2937',
                            border: 'none',
                            borderRadius: '8px',
                            color: '#F9FAFB',
                          }}
                        />
                        <Legend wrapperStyle={{ fontSize: '10px' }} />
                        <Line
                          type="monotone"
                          dataKey="total_escalation_articles"
                          stroke="#EF4444"
                          strokeWidth={2}
                          name="Total Escalation"
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
