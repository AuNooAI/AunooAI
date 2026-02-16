/**
 * GeopoliticalRegionsTab Component
 * Regional breakdown of geopolitical hotspots
 */

import { useEffect } from 'react';
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
import type { RegionData, CategoryData } from '../../services/geopoliticalHotspotsApi';
import { ChartDownloadButton } from './ChartDownloadButton';

interface GeopoliticalRegionsTabProps {
  regions: RegionData[];
  categories: CategoryData[];
  loadingRegions: boolean;
  loadingCategories: boolean;
  onLoadRegions: () => void;
  onLoadCategories: () => void;
}

// Colors for regions
const REGION_COLORS = [
  '#EC4899', // Pink
  '#F97316', // Orange
  '#EAB308', // Yellow
  '#22C55E', // Green
  '#3B82F6', // Blue
  '#8B5CF6', // Purple
  '#06B6D4', // Cyan
  '#DC2626', // Red
  '#84CC16', // Lime
  '#6366F1', // Indigo
];

export function GeopoliticalRegionsTab({
  regions,
  categories,
  loadingRegions,
  loadingCategories,
  onLoadRegions,
  onLoadCategories,
}: GeopoliticalRegionsTabProps) {
  // Load data on mount
  useEffect(() => {
    if (regions.length === 0) {
      onLoadRegions();
    }
    if (categories.length === 0) {
      onLoadCategories();
    }
  }, [regions.length, categories.length, onLoadRegions, onLoadCategories]);

  const loading = loadingRegions || loadingCategories;

  if (loading && regions.length === 0 && categories.length === 0) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-pulse text-gray-500 dark:text-gray-400">Loading regions...</div>
      </div>
    );
  }

  // Prepare region data with colors
  const regionData = regions.map((region, index) => ({
    ...region,
    color: REGION_COLORS[index % REGION_COLORS.length],
  }));

  // Prepare category data
  const categoryData = categories.map((cat, index) => ({
    ...cat,
    displayName: cat.category.charAt(0).toUpperCase() + cat.category.slice(1),
    color: REGION_COLORS[(index + 5) % REGION_COLORS.length],
  }));

  // Total hotspots for percentage calculation
  const totalHotspots = regions.reduce((sum, r) => sum + r.hotspot_count, 0);

  return (
    <div className="space-y-6">
      {/* Regional Overview */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Regions Bar Chart */}
        <div id="chart-geo-hotspots-by-region" className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-semibold text-gray-900 dark:text-gray-100">
              Hotspots by Region
            </h3>
            <ChartDownloadButton targetId="chart-geo-hotspots-by-region" filename="hotspots-by-region" />
          </div>
          <ResponsiveContainer width="100%" height={350}>
            <BarChart data={regionData} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
              <XAxis type="number" tick={{ fontSize: 12 }} />
              <YAxis
                type="category"
                dataKey="region"
                tick={{ fontSize: 11 }}
                width={100}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: 'rgba(31, 41, 55, 0.9)',
                  border: 'none',
                  borderRadius: '0.5rem',
                  color: '#F9FAFB',
                }}
                formatter={(value: number, name: string) => [
                  value,
                  name === 'hotspot_count' ? 'Hotspots' : 'Articles',
                ]}
              />
              <Bar dataKey="hotspot_count" name="Hotspots" fill="#EC4899" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Regions Pie Chart */}
        <div id="chart-geo-regional-distribution" className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-semibold text-gray-900 dark:text-gray-100">
              Regional Distribution
            </h3>
            <ChartDownloadButton targetId="chart-geo-regional-distribution" filename="regional-distribution" />
          </div>
          <ResponsiveContainer width="100%" height={350}>
            <PieChart>
              <Pie
                data={regionData}
                cx="50%"
                cy="50%"
                innerRadius={60}
                outerRadius={100}
                paddingAngle={2}
                dataKey="hotspot_count"
                nameKey="region"
                label={({ region, percent }) =>
                  percent > 0.05 ? `${region} ${(percent * 100).toFixed(0)}%` : ''
                }
                labelLine={false}
              >
                {regionData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={entry.color} />
                ))}
              </Pie>
              <Tooltip
                contentStyle={{
                  backgroundColor: 'rgba(31, 41, 55, 0.9)',
                  border: 'none',
                  borderRadius: '0.5rem',
                  color: '#F9FAFB',
                }}
              />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Region Cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
        {regionData.slice(0, 10).map((region) => {
          const percentage = totalHotspots > 0
            ? ((region.hotspot_count / totalHotspots) * 100).toFixed(1)
            : '0';
          return (
            <div
              key={region.region}
              className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4"
            >
              <div
                className="w-3 h-3 rounded-full mb-2"
                style={{ backgroundColor: region.color }}
              />
              <h4 className="font-medium text-gray-900 dark:text-gray-100 text-sm">
                {region.region}
              </h4>
              <div className="text-2xl font-bold text-gray-900 dark:text-gray-100 mt-1">
                {region.hotspot_count}
              </div>
              <div className="text-xs text-gray-500 dark:text-gray-400">
                {percentage}% of total
              </div>
              <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                {region.article_count} articles
              </div>
            </div>
          );
        })}
      </div>

      {/* Category Analysis */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Categories Bar Chart */}
        <div id="chart-geo-threat-categories" className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-semibold text-gray-900 dark:text-gray-100">
              Threat Categories
            </h3>
            <ChartDownloadButton targetId="chart-geo-threat-categories" filename="threat-categories" />
          </div>
          <ResponsiveContainer width="100%" height={350}>
            <BarChart data={categoryData} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
              <XAxis type="number" tick={{ fontSize: 12 }} />
              <YAxis
                type="category"
                dataKey="displayName"
                tick={{ fontSize: 11 }}
                width={100}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: 'rgba(31, 41, 55, 0.9)',
                  border: 'none',
                  borderRadius: '0.5rem',
                  color: '#F9FAFB',
                }}
              />
              <Bar dataKey="count" name="Hotspots" fill="#3B82F6" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Category Intensity */}
        <div id="chart-geo-avg-intensity" className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-semibold text-gray-900 dark:text-gray-100">
              Average Intensity by Category
            </h3>
            <ChartDownloadButton targetId="chart-geo-avg-intensity" filename="avg-intensity-by-category" />
          </div>
          <ResponsiveContainer width="100%" height={350}>
            <BarChart data={categoryData} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
              <XAxis type="number" domain={[0, 100]} tick={{ fontSize: 12 }} />
              <YAxis
                type="category"
                dataKey="displayName"
                tick={{ fontSize: 11 }}
                width={100}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: 'rgba(31, 41, 55, 0.9)',
                  border: 'none',
                  borderRadius: '0.5rem',
                  color: '#F9FAFB',
                }}
                formatter={(value: number) => [`${value.toFixed(1)}%`, 'Avg Intensity']}
              />
              <Bar dataKey="avg_intensity" name="Intensity" fill="#F97316" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
