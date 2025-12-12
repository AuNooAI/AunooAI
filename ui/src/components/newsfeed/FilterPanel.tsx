/**
 * Filter Panel Component - Dropdown panel for filtering incidents
 * Matches the filter-dropdown-panel pattern from news_feed_new.html
 */

import { X, Filter, RotateCcw } from 'lucide-react';
import { Button } from '../ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../ui/select';
import {
  type IncidentType,
  type IncidentSignificance,
  type IncidentStatus,
} from '../../services/narrativeExplorerApi';

export interface IncidentFilters {
  types: Set<IncidentType>;
  significance: Set<IncidentSignificance>;
  status: Set<IncidentStatus>;
}

export type SortOption = 'date_desc' | 'date_asc' | 'significance' | 'type';

interface FilterPanelProps {
  open: boolean;
  onClose: () => void;
  filters: IncidentFilters;
  sortBy: SortOption;
  onFiltersChange: (filters: IncidentFilters) => void;
  onSortChange: (sort: SortOption) => void;
  onClearFilters: () => void;
}

const INCIDENT_TYPES: { value: IncidentType; label: string; color: string }[] = [
  { value: 'incident', label: 'Incident', color: 'bg-red-100 text-red-700 border-red-200' },
  { value: 'event', label: 'Event', color: 'bg-green-100 text-green-700 border-green-200' },
  { value: 'entity', label: 'Entity', color: 'bg-blue-100 text-blue-700 border-blue-200' },
  { value: 'expertise', label: 'Expertise', color: 'bg-amber-100 text-amber-700 border-amber-200' },
  { value: 'informed_insider', label: 'Insider', color: 'bg-gray-800 text-white border-gray-800' },
  { value: 'trend_signal', label: 'Trend', color: 'bg-cyan-100 text-cyan-700 border-cyan-200' },
  { value: 'strategic_shift', label: 'Strategic', color: 'bg-gray-100 text-gray-700 border-gray-200' },
];

const SIGNIFICANCE_OPTIONS: { value: IncidentSignificance; label: string; color: string }[] = [
  { value: 'high', label: 'High', color: 'bg-red-100 text-red-700 border-red-200' },
  { value: 'medium', label: 'Medium', color: 'bg-yellow-100 text-yellow-700 border-yellow-200' },
  { value: 'low', label: 'Low', color: 'bg-blue-100 text-blue-700 border-blue-200' },
];

const STATUS_OPTIONS: { value: IncidentStatus; label: string; color: string }[] = [
  { value: 'active', label: 'Active', color: 'bg-green-100 text-green-700 border-green-200' },
  { value: 'seen', label: 'Seen', color: 'bg-gray-100 text-gray-600 border-gray-200' },
];

export function FilterPanel({
  open,
  onClose,
  filters,
  sortBy,
  onFiltersChange,
  onSortChange,
  onClearFilters,
}: FilterPanelProps) {
  if (!open) return null;

  const toggleType = (type: IncidentType) => {
    const newTypes = new Set(filters.types);
    if (newTypes.has(type)) {
      newTypes.delete(type);
    } else {
      newTypes.add(type);
    }
    onFiltersChange({ ...filters, types: newTypes });
  };

  const toggleSignificance = (sig: IncidentSignificance) => {
    const newSig = new Set(filters.significance);
    if (newSig.has(sig)) {
      newSig.delete(sig);
    } else {
      newSig.add(sig);
    }
    onFiltersChange({ ...filters, significance: newSig });
  };

  const toggleStatus = (status: IncidentStatus) => {
    const newStatus = new Set(filters.status);
    if (newStatus.has(status)) {
      newStatus.delete(status);
    } else {
      newStatus.add(status);
    }
    onFiltersChange({ ...filters, status: newStatus });
  };

  const hasActiveFilters =
    filters.types.size > 0 ||
    filters.significance.size > 0 ||
    filters.status.size > 0;

  return (
    <div className="absolute right-12 top-0 z-50 w-80 bg-white rounded-lg shadow-lg border border-gray-200">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200">
        <div className="flex items-center gap-2">
          <Filter className="w-4 h-4 text-gray-500" />
          <h3 className="font-semibold text-gray-900">Filter Incidents</h3>
        </div>
        <button
          onClick={onClose}
          className="p-1 hover:bg-gray-100 rounded-full transition-colors"
        >
          <X className="w-4 h-4 text-gray-500" />
        </button>
      </div>

      {/* Body */}
      <div className="p-4 space-y-4">
        {/* Type Filter */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Type
          </label>
          <div className="flex flex-wrap gap-1.5">
            {INCIDENT_TYPES.map(({ value, label, color }) => (
              <button
                key={value}
                onClick={() => toggleType(value)}
                className={`px-2 py-1 text-xs font-medium rounded-full border transition-all ${
                  filters.types.has(value)
                    ? color + ' ring-2 ring-offset-1 ring-pink-500'
                    : 'bg-white text-gray-600 border-gray-200 hover:border-gray-300'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        {/* Significance Filter */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Significance
          </label>
          <div className="flex flex-wrap gap-1.5">
            {SIGNIFICANCE_OPTIONS.map(({ value, label, color }) => (
              <button
                key={value}
                onClick={() => toggleSignificance(value)}
                className={`px-2 py-1 text-xs font-medium rounded-full border transition-all ${
                  filters.significance.has(value)
                    ? color + ' ring-2 ring-offset-1 ring-pink-500'
                    : 'bg-white text-gray-600 border-gray-200 hover:border-gray-300'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        {/* Status Filter */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Status
          </label>
          <div className="flex flex-wrap gap-1.5">
            {STATUS_OPTIONS.map(({ value, label, color }) => (
              <button
                key={value}
                onClick={() => toggleStatus(value)}
                className={`px-2 py-1 text-xs font-medium rounded-full border transition-all ${
                  filters.status.has(value)
                    ? color + ' ring-2 ring-offset-1 ring-pink-500'
                    : 'bg-white text-gray-600 border-gray-200 hover:border-gray-300'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        {/* Sort */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Sort By
          </label>
          <Select value={sortBy} onValueChange={(v) => onSortChange(v as SortOption)}>
            <SelectTrigger className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="date_desc">Newest First</SelectItem>
              <SelectItem value="date_asc">Oldest First</SelectItem>
              <SelectItem value="significance">By Significance</SelectItem>
              <SelectItem value="type">By Type</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* Footer */}
      <div className="px-4 py-3 border-t border-gray-200 flex justify-between">
        <Button
          variant="ghost"
          size="sm"
          onClick={onClearFilters}
          disabled={!hasActiveFilters}
          className="gap-1"
        >
          <RotateCcw className="w-3 h-3" />
          Clear Filters
        </Button>
        <Button size="sm" onClick={onClose}>
          Done
        </Button>
      </div>
    </div>
  );
}

/**
 * Create empty filters
 */
export function createEmptyFilters(): IncidentFilters {
  return {
    types: new Set(),
    significance: new Set(),
    status: new Set(),
  };
}

/**
 * Apply filters to incidents
 */
export function applyFilters<T extends { type?: string; significance?: string; status?: string }>(
  items: T[],
  filters: IncidentFilters
): T[] {
  return items.filter((item) => {
    // Type filter
    if (filters.types.size > 0 && item.type) {
      if (!filters.types.has(item.type as IncidentType)) {
        return false;
      }
    }

    // Significance filter
    if (filters.significance.size > 0 && item.significance) {
      if (!filters.significance.has(item.significance as IncidentSignificance)) {
        return false;
      }
    }

    // Status filter
    if (filters.status.size > 0) {
      const itemStatus = item.status || 'active';
      if (!filters.status.has(itemStatus as IncidentStatus)) {
        return false;
      }
    }

    return true;
  });
}
