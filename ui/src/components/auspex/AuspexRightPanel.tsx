/**
 * AuspexRightPanel - Right panel for charts, visualizations, and analysis results
 * Placeholder for future functionality
 */

import { useState } from 'react';
import {
  BarChart3,
  LineChart,
  PieChart,
  TrendingUp,
  FileText,
  Bookmark,
  Sparkles
} from 'lucide-react';
import { cn } from '../ui/utils';

interface AuspexRightPanelProps {
  isOpen: boolean;
  onToggle: () => void;
  isWorkbenchMode: boolean;
}

export function AuspexRightPanel({
  isOpen,
  onToggle,
  isWorkbenchMode
}: AuspexRightPanelProps) {
  const [activeTab, setActiveTab] = useState<'insights' | 'saved' | 'charts'>('insights');

  if (!isWorkbenchMode || !isOpen) {
    return null;
  }

  return (
    <div className="w-80 h-full flex flex-col">
      {/* Header with tabs */}
      <div className="flex-shrink-0 border-b border-gray-200 dark:border-gray-700">
        <div className="flex">
          <button
            onClick={() => setActiveTab('insights')}
            className={cn(
              'flex-1 px-3 py-3 text-xs font-medium transition-colors',
              'border-b-2',
              activeTab === 'insights'
                ? 'border-pink-500 text-pink-600 dark:text-pink-400'
                : 'border-transparent text-gray-500 hover:text-gray-700 dark:hover:text-gray-300'
            )}
          >
            <Sparkles className="w-4 h-4 mx-auto mb-1" />
            Insights
          </button>
          <button
            onClick={() => setActiveTab('saved')}
            className={cn(
              'flex-1 px-3 py-3 text-xs font-medium transition-colors',
              'border-b-2',
              activeTab === 'saved'
                ? 'border-pink-500 text-pink-600 dark:text-pink-400'
                : 'border-transparent text-gray-500 hover:text-gray-700 dark:hover:text-gray-300'
            )}
          >
            <Bookmark className="w-4 h-4 mx-auto mb-1" />
            Saved
          </button>
          <button
            onClick={() => setActiveTab('charts')}
            className={cn(
              'flex-1 px-3 py-3 text-xs font-medium transition-colors',
              'border-b-2',
              activeTab === 'charts'
                ? 'border-pink-500 text-pink-600 dark:text-pink-400'
                : 'border-transparent text-gray-500 hover:text-gray-700 dark:hover:text-gray-300'
            )}
          >
            <BarChart3 className="w-4 h-4 mx-auto mb-1" />
            Charts
          </button>
        </div>
      </div>

      {/* Content area */}
      <div className="flex-1 overflow-y-auto p-4">
        {activeTab === 'insights' && (
          <InsightsTab />
        )}
        {activeTab === 'saved' && (
          <SavedTab />
        )}
        {activeTab === 'charts' && (
          <ChartsTab />
        )}
      </div>
    </div>
  );
}

function InsightsTab() {
  return (
    <div className="space-y-4">
      <div className="text-center py-8 text-gray-400">
        <Sparkles className="w-12 h-12 mx-auto mb-3 opacity-50" />
        <h3 className="text-sm font-medium text-gray-600 dark:text-gray-400 mb-1">
          AI Insights
        </h3>
        <p className="text-xs text-gray-400">
          Insights from your conversation will appear here as you chat with Auspex
        </p>
      </div>

      {/* Placeholder cards for future insights */}
      <div className="space-y-3 opacity-50">
        <InsightCard
          icon={<TrendingUp className="w-4 h-4" />}
          title="Trend Detection"
          description="Automatically identify emerging trends"
        />
        <InsightCard
          icon={<FileText className="w-4 h-4" />}
          title="Key Findings"
          description="Important facts extracted from analysis"
        />
      </div>
    </div>
  );
}

function SavedTab() {
  return (
    <div className="text-center py-8 text-gray-400">
      <Bookmark className="w-12 h-12 mx-auto mb-3 opacity-50" />
      <h3 className="text-sm font-medium text-gray-600 dark:text-gray-400 mb-1">
        Saved Items
      </h3>
      <p className="text-xs text-gray-400">
        Save important responses, quotes, or findings for later reference
      </p>
    </div>
  );
}

function ChartsTab() {
  return (
    <div className="space-y-4">
      <div className="text-center py-8 text-gray-400">
        <BarChart3 className="w-12 h-12 mx-auto mb-3 opacity-50" />
        <h3 className="text-sm font-medium text-gray-600 dark:text-gray-400 mb-1">
          Visualizations
        </h3>
        <p className="text-xs text-gray-400">
          Charts and graphs from your analysis will appear here
        </p>
      </div>

      {/* Placeholder chart types */}
      <div className="grid grid-cols-2 gap-2 opacity-50">
        <ChartPlaceholder icon={<BarChart3 className="w-6 h-6" />} label="Bar Chart" />
        <ChartPlaceholder icon={<LineChart className="w-6 h-6" />} label="Line Chart" />
        <ChartPlaceholder icon={<PieChart className="w-6 h-6" />} label="Pie Chart" />
        <ChartPlaceholder icon={<TrendingUp className="w-6 h-6" />} label="Trends" />
      </div>
    </div>
  );
}

function InsightCard({
  icon,
  title,
  description
}: {
  icon: React.ReactNode;
  title: string;
  description: string;
}) {
  return (
    <div className="p-3 rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50">
      <div className="flex items-center gap-2 mb-1">
        <span className="text-pink-500">{icon}</span>
        <h4 className="text-xs font-medium text-gray-700 dark:text-gray-300">{title}</h4>
      </div>
      <p className="text-xs text-gray-500">{description}</p>
    </div>
  );
}

function ChartPlaceholder({
  icon,
  label
}: {
  icon: React.ReactNode;
  label: string;
}) {
  return (
    <div className="p-4 rounded-lg border border-dashed border-gray-300 dark:border-gray-600 flex flex-col items-center justify-center">
      <span className="text-gray-400 mb-1">{icon}</span>
      <span className="text-xs text-gray-400">{label}</span>
    </div>
  );
}
