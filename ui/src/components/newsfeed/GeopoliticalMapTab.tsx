/**
 * GeopoliticalMapTab Component
 * Full interactive map with filters for geopolitical hotspots
 */

import { useState } from 'react';
import { Filter, X } from 'lucide-react';
import { HotspotMap } from './map';
import type { Hotspot, ThreatCategory, RiskLevel } from '../../services/geopoliticalHotspotsApi';
import {
  THREAT_CATEGORIES,
  RISK_LEVELS,
  RISK_COLORS,
} from '../../services/geopoliticalHotspotsApi';

interface GeopoliticalMapTabProps {
  hotspots: Hotspot[];
  loading: boolean;
  selectedCategories: ThreatCategory[];
  selectedRiskLevels: RiskLevel[];
  onCategoriesChange: (categories: ThreatCategory[]) => void;
  onRiskLevelsChange: (levels: RiskLevel[]) => void;
  onHotspotClick?: (hotspot: Hotspot) => void;
}

export function GeopoliticalMapTab({
  hotspots,
  loading,
  selectedCategories,
  selectedRiskLevels,
  onCategoriesChange,
  onRiskLevelsChange,
  onHotspotClick,
}: GeopoliticalMapTabProps) {
  const [showFilters, setShowFilters] = useState(false);

  const toggleCategory = (category: ThreatCategory) => {
    if (selectedCategories.includes(category)) {
      onCategoriesChange(selectedCategories.filter((c) => c !== category));
    } else {
      onCategoriesChange([...selectedCategories, category]);
    }
  };

  const toggleRiskLevel = (level: RiskLevel) => {
    if (selectedRiskLevels.includes(level)) {
      onRiskLevelsChange(selectedRiskLevels.filter((l) => l !== level));
    } else {
      onRiskLevelsChange([...selectedRiskLevels, level]);
    }
  };

  const clearFilters = () => {
    onCategoriesChange([]);
    onRiskLevelsChange([]);
  };

  const hasFilters = selectedCategories.length > 0 || selectedRiskLevels.length > 0;

  return (
    <div className="space-y-4">
      {/* Filter Controls */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button
            onClick={() => setShowFilters(!showFilters)}
            className={`flex items-center gap-2 px-3 py-2 text-sm rounded-lg border transition-colors ${
              showFilters
                ? 'bg-pink-50 dark:bg-pink-900/20 border-pink-200 dark:border-pink-800 text-pink-700 dark:text-pink-300'
                : 'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700'
            }`}
          >
            <Filter className="w-4 h-4" />
            Filters
            {hasFilters && (
              <span className="px-1.5 py-0.5 text-xs bg-pink-500 text-white rounded-full">
                {selectedCategories.length + selectedRiskLevels.length}
              </span>
            )}
          </button>

          {hasFilters && (
            <button
              onClick={clearFilters}
              className="flex items-center gap-1 px-2 py-1 text-sm text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
            >
              <X className="w-4 h-4" />
              Clear
            </button>
          )}
        </div>

        <div className="text-sm text-gray-500 dark:text-gray-400">
          {hotspots.length} hotspots
        </div>
      </div>

      {/* Filter Panel */}
      {showFilters && (
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 space-y-4">
          {/* Risk Level Filters */}
          <div>
            <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Risk Level
            </h4>
            <div className="flex flex-wrap gap-2">
              {RISK_LEVELS.map((level) => (
                <button
                  key={level}
                  onClick={() => toggleRiskLevel(level)}
                  className={`px-3 py-1.5 text-sm rounded-full border transition-colors ${
                    selectedRiskLevels.includes(level)
                      ? 'text-white'
                      : 'bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-600'
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

          {/* Category Filters */}
          <div>
            <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Threat Category
            </h4>
            <div className="flex flex-wrap gap-2">
              {THREAT_CATEGORIES.map((category) => (
                <button
                  key={category}
                  onClick={() => toggleCategory(category)}
                  className={`px-3 py-1.5 text-sm rounded-full border transition-colors ${
                    selectedCategories.includes(category)
                      ? 'bg-pink-500 border-pink-500 text-white'
                      : 'bg-white dark:bg-gray-700 border-gray-200 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-600'
                  }`}
                >
                  {category.charAt(0).toUpperCase() + category.slice(1)}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Map */}
      {loading ? (
        <div className="flex items-center justify-center h-[600px] bg-gray-100 dark:bg-gray-800 rounded-lg">
          <div className="animate-pulse text-gray-500 dark:text-gray-400">Loading map...</div>
        </div>
      ) : (
        <HotspotMap hotspots={hotspots} height="600px" onHotspotClick={onHotspotClick} />
      )}
    </div>
  );
}
