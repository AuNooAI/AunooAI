/**
 * GeopoliticalArticlesTab Component
 * Filterable list of articles linked to hotspots
 */

import { useState, useCallback } from 'react';
import { Newspaper, ChevronLeft, ChevronRight, ExternalLink, MapPin } from 'lucide-react';
import type { Hotspot, ThreatCategory, RiskLevel } from '../../services/geopoliticalHotspotsApi';
import { RISK_COLORS, THREAT_CATEGORIES, RISK_LEVELS } from '../../services/geopoliticalHotspotsApi';

interface GeopoliticalArticlesTabProps {
  hotspots: Hotspot[];
  totalHotspots: number;
  totalPages: number;
  currentPage: number;
  loading: boolean;
  selectedCategories: ThreatCategory[];
  selectedRiskLevels: RiskLevel[];
  sortBy: string;
  sortOrder: string;
  onPageChange: (page: number) => void;
  onCategoriesChange: (categories: ThreatCategory[]) => void;
  onRiskLevelsChange: (levels: RiskLevel[]) => void;
  onSortChange: (sortBy: string, sortOrder: string) => void;
  onHotspotClick?: (hotspot: Hotspot) => void;
}

export function GeopoliticalArticlesTab({
  hotspots,
  totalHotspots,
  totalPages,
  currentPage,
  loading,
  selectedCategories,
  selectedRiskLevels,
  sortBy,
  sortOrder,
  onPageChange,
  onCategoriesChange,
  onRiskLevelsChange,
  onSortChange,
  onHotspotClick,
}: GeopoliticalArticlesTabProps) {
  const [showFilters, setShowFilters] = useState(false);

  const toggleCategory = useCallback(
    (category: ThreatCategory) => {
      if (selectedCategories.includes(category)) {
        onCategoriesChange(selectedCategories.filter((c) => c !== category));
      } else {
        onCategoriesChange([...selectedCategories, category]);
      }
    },
    [selectedCategories, onCategoriesChange]
  );

  const toggleRiskLevel = useCallback(
    (level: RiskLevel) => {
      if (selectedRiskLevels.includes(level)) {
        onRiskLevelsChange(selectedRiskLevels.filter((l) => l !== level));
      } else {
        onRiskLevelsChange([...selectedRiskLevels, level]);
      }
    },
    [selectedRiskLevels, onRiskLevelsChange]
  );

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return 'Unknown';
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  };

  return (
    <div className="space-y-4">
      {/* Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <button
            onClick={() => setShowFilters(!showFilters)}
            className={`px-3 py-2 text-sm rounded-lg border transition-colors ${
              showFilters
                ? 'bg-pink-50 dark:bg-pink-900/20 border-pink-200 dark:border-pink-800 text-pink-700 dark:text-pink-300'
                : 'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300'
            }`}
          >
            Filters
            {(selectedCategories.length > 0 || selectedRiskLevels.length > 0) && (
              <span className="ml-1 px-1.5 py-0.5 text-xs bg-pink-500 text-white rounded-full">
                {selectedCategories.length + selectedRiskLevels.length}
              </span>
            )}
          </button>

          <span className="text-sm text-gray-500 dark:text-gray-400">
            {totalHotspots} hotspots
          </span>
        </div>

        <div className="flex items-center gap-3">
          <select
            value={`${sortBy}-${sortOrder}`}
            onChange={(e) => {
              const [newSortBy, newSortOrder] = e.target.value.split('-');
              onSortChange(newSortBy, newSortOrder);
            }}
            className="px-3 py-2 text-sm bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg"
          >
            <option value="intensity-desc">Intensity (High to Low)</option>
            <option value="intensity-asc">Intensity (Low to High)</option>
            <option value="articles-desc">Most Articles</option>
            <option value="recent-desc">Most Recent Activity</option>
            <option value="name-asc">Name (A-Z)</option>
          </select>
        </div>
      </div>

      {/* Filters Panel */}
      {showFilters && (
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 space-y-4">
          <div>
            <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Risk Level
            </h4>
            <div className="flex flex-wrap gap-2">
              {RISK_LEVELS.map((level) => (
                <button
                  key={level}
                  onClick={() => toggleRiskLevel(level)}
                  className={`px-3 py-1 text-xs rounded-full border transition-colors ${
                    selectedRiskLevels.includes(level)
                      ? 'text-white'
                      : 'bg-white dark:bg-gray-700 text-gray-600 dark:text-gray-300'
                  }`}
                  style={{
                    backgroundColor: selectedRiskLevels.includes(level)
                      ? RISK_COLORS[level]
                      : undefined,
                    borderColor: RISK_COLORS[level],
                  }}
                >
                  {level.charAt(0).toUpperCase() + level.slice(1)}
                </button>
              ))}
            </div>
          </div>
          <div>
            <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Category
            </h4>
            <div className="flex flex-wrap gap-2">
              {THREAT_CATEGORIES.map((category) => (
                <button
                  key={category}
                  onClick={() => toggleCategory(category)}
                  className={`px-3 py-1 text-xs rounded-full border transition-colors ${
                    selectedCategories.includes(category)
                      ? 'bg-pink-500 border-pink-500 text-white'
                      : 'bg-white dark:bg-gray-700 border-gray-200 dark:border-gray-600 text-gray-600 dark:text-gray-300'
                  }`}
                >
                  {category.charAt(0).toUpperCase() + category.slice(1)}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Hotspots List */}
      {loading ? (
        <div className="flex items-center justify-center h-64">
          <div className="animate-pulse text-gray-500 dark:text-gray-400">Loading...</div>
        </div>
      ) : hotspots.length === 0 ? (
        <div className="flex flex-col items-center justify-center h-64 text-center">
          <Newspaper className="w-12 h-12 text-gray-400 dark:text-gray-600 mb-4" />
          <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100">
            No hotspots found
          </h3>
          <p className="text-gray-500 dark:text-gray-400 mt-1">
            Try adjusting your filters
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {hotspots.map((hotspot) => (
            <div
              key={hotspot.id}
              className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 hover:shadow-md transition-shadow cursor-pointer"
              onClick={() => onHotspotClick?.(hotspot)}
            >
              <div className="flex items-start justify-between">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <h4 className="font-semibold text-gray-900 dark:text-gray-100 truncate">
                      {hotspot.location_name}
                    </h4>
                    <span
                      className="px-2 py-0.5 text-xs font-medium rounded-full text-white flex-shrink-0"
                      style={{ backgroundColor: RISK_COLORS[hotspot.risk_level] }}
                    >
                      {hotspot.risk_level.toUpperCase()}
                    </span>
                    {hotspot.primary_category && (
                      <span className="px-2 py-0.5 text-xs font-medium rounded-full bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 flex-shrink-0">
                        {hotspot.primary_category}
                      </span>
                    )}
                  </div>

                  <div className="flex items-center gap-4 text-sm text-gray-500 dark:text-gray-400">
                    {hotspot.country_name && (
                      <span className="flex items-center gap-1">
                        <MapPin className="w-3 h-3" />
                        {hotspot.country_name}
                      </span>
                    )}
                    <span>{hotspot.article_count} articles</span>
                    <span>{hotspot.recent_article_count} recent</span>
                    {hotspot.last_article_date && (
                      <span>Last: {formatDate(hotspot.last_article_date)}</span>
                    )}
                  </div>
                </div>

                <div className="text-right ml-4">
                  <div className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                    {Math.round(hotspot.intensity_score)}
                  </div>
                  <div className="text-xs text-gray-500 dark:text-gray-400">intensity</div>
                  {hotspot.trend && (
                    <div
                      className={`text-xs mt-1 ${
                        hotspot.trend === 'escalating'
                          ? 'text-red-500'
                          : hotspot.trend === 'de-escalating'
                            ? 'text-green-500'
                            : 'text-gray-500'
                      }`}
                    >
                      {hotspot.trend === 'escalating'
                        ? '↑ Escalating'
                        : hotspot.trend === 'de-escalating'
                          ? '↓ De-escalating'
                          : '→ Stable'}
                    </div>
                  )}
                </div>
              </div>

              {/* Tags */}
              {hotspot.tags && hotspot.tags.length > 0 && (
                <div className="flex flex-wrap gap-1 mt-2">
                  {hotspot.tags.slice(0, 5).map((tag, index) => (
                    <span
                      key={index}
                      className="px-2 py-0.5 text-xs bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 rounded"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2">
          <button
            onClick={() => onPageChange(currentPage - 1)}
            disabled={currentPage === 1}
            className="p-2 rounded-lg border border-gray-200 dark:border-gray-700 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-50 dark:hover:bg-gray-700"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>

          <span className="text-sm text-gray-600 dark:text-gray-400">
            Page {currentPage} of {totalPages}
          </span>

          <button
            onClick={() => onPageChange(currentPage + 1)}
            disabled={currentPage === totalPages}
            className="p-2 rounded-lg border border-gray-200 dark:border-gray-700 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-50 dark:hover:bg-gray-700"
          >
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      )}
    </div>
  );
}
