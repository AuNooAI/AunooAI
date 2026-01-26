/**
 * ThreatMapTab Component
 * Geographic visualization of threats
 */

import { useState } from 'react';
import { Filter, X } from 'lucide-react';
import { ThreatMap } from './map/ThreatMap';
import {
  type ThreatMapData,
  type ThreatCategory,
  type SeverityLevel,
  THREAT_CATEGORIES,
  THREAT_CATEGORY_LABELS,
  SEVERITY_LEVELS,
  SEVERITY_LABELS,
  SEVERITY_COLORS,
} from '../../services/threatIntelligenceApi';

interface ThreatMapTabProps {
  threats: ThreatMapData[];
  loading: boolean;
  selectedThreatTypes: ThreatCategory[];
  selectedSeverityLevels: SeverityLevel[];
  onThreatTypesChange: (types: ThreatCategory[]) => void;
  onSeverityLevelsChange: (levels: SeverityLevel[]) => void;
  onThreatClick: (threat: ThreatMapData) => void;
}

export function ThreatMapTab({
  threats,
  loading,
  selectedThreatTypes,
  selectedSeverityLevels,
  onThreatTypesChange,
  onSeverityLevelsChange,
  onThreatClick,
}: ThreatMapTabProps) {
  const [showFilters, setShowFilters] = useState(false);

  const toggleThreatType = (type: ThreatCategory) => {
    if (selectedThreatTypes.includes(type)) {
      onThreatTypesChange(selectedThreatTypes.filter((t) => t !== type));
    } else {
      onThreatTypesChange([...selectedThreatTypes, type]);
    }
  };

  const toggleSeverityLevel = (level: SeverityLevel) => {
    if (selectedSeverityLevels.includes(level)) {
      onSeverityLevelsChange(selectedSeverityLevels.filter((l) => l !== level));
    } else {
      onSeverityLevelsChange([...selectedSeverityLevels, level]);
    }
  };

  const clearFilters = () => {
    onThreatTypesChange([]);
    onSeverityLevelsChange([]);
  };

  const hasFilters = selectedThreatTypes.length > 0 || selectedSeverityLevels.length > 0;

  return (
    <div className="space-y-4">
      {/* Filter Controls */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowFilters(!showFilters)}
            className={`flex items-center gap-2 px-3 py-2 text-sm rounded-lg border transition-colors ${
              showFilters
                ? 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800 text-red-700 dark:text-red-300'
                : 'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700'
            }`}
          >
            <Filter className="w-4 h-4" />
            Filters
            {hasFilters && (
              <span className="px-1.5 py-0.5 text-xs bg-red-500 text-white rounded-full">
                {selectedThreatTypes.length + selectedSeverityLevels.length}
              </span>
            )}
          </button>

          {hasFilters && (
            <button
              onClick={clearFilters}
              className="flex items-center gap-1 px-2 py-1 text-xs text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
            >
              <X className="w-3 h-3" />
              Clear
            </button>
          )}
        </div>

        <div className="text-sm text-gray-500 dark:text-gray-400">
          {threats.length} threats with location data
        </div>
      </div>

      {/* Filter Panel */}
      {showFilters && (
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Severity Levels */}
            <div>
              <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
                Severity Level
              </h4>
              <div className="flex flex-wrap gap-2">
                {SEVERITY_LEVELS.map((level) => (
                  <button
                    key={level}
                    onClick={() => toggleSeverityLevel(level)}
                    className={`flex items-center gap-2 px-3 py-1.5 text-sm rounded-full border transition-colors ${
                      selectedSeverityLevels.includes(level)
                        ? 'border-transparent text-white'
                        : 'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300'
                    }`}
                    style={
                      selectedSeverityLevels.includes(level)
                        ? { backgroundColor: SEVERITY_COLORS[level] }
                        : {}
                    }
                  >
                    <div
                      className={`w-2 h-2 rounded-full ${
                        selectedSeverityLevels.includes(level) ? 'bg-white' : ''
                      }`}
                      style={
                        !selectedSeverityLevels.includes(level)
                          ? { backgroundColor: SEVERITY_COLORS[level] }
                          : {}
                      }
                    />
                    {SEVERITY_LABELS[level]}
                  </button>
                ))}
              </div>
            </div>

            {/* Threat Types */}
            <div>
              <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
                Threat Type
              </h4>
              <div className="flex flex-wrap gap-2">
                {THREAT_CATEGORIES.slice(0, 8).map((type) => (
                  <button
                    key={type}
                    onClick={() => toggleThreatType(type)}
                    className={`px-3 py-1.5 text-sm rounded-full border transition-colors ${
                      selectedThreatTypes.includes(type)
                        ? 'bg-red-500 border-red-500 text-white'
                        : 'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300 hover:border-red-300 dark:hover:border-red-700'
                    }`}
                  >
                    {THREAT_CATEGORY_LABELS[type]}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Map */}
      {loading ? (
        <div className="flex items-center justify-center h-[500px] bg-gray-100 dark:bg-gray-800 rounded-lg">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-red-500"></div>
        </div>
      ) : (
        <ThreatMap
          threats={threats}
          onThreatClick={onThreatClick}
          fillContainer
          showLegend
        />
      )}
    </div>
  );
}
