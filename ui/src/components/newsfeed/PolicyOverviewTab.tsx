/**
 * Policy Tracker Overview Tab
 * Main dashboard with stats and key charts
 */

import { Info } from 'lucide-react';
import type { PolicyStats, PolicyCategory, TemporalData, EscalationData } from '../../services/policyTrackerApi';
import { PolicyTrackerStats } from './PolicyTrackerStats';
import { PolicyTrackerCharts } from './PolicyTrackerCharts';

interface PolicyOverviewTabProps {
  stats: PolicyStats | null;
  categories: PolicyCategory[];
  temporalData: TemporalData[];
  escalationData: EscalationData[];
  loadingStats: boolean;
  loadingCharts: boolean;
}

export function PolicyOverviewTab({
  stats,
  categories,
  temporalData,
  loadingStats,
  loadingCharts,
}: PolicyOverviewTabProps) {
  return (
    <div className="space-y-6">
      {/* Data Source Credit */}
      <div className="flex justify-end">
        <a
          href="https://www.trumpactiontracker.info/about"
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 text-xs text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
        >
          <Info className="w-3 h-3" />
          <span>Data source</span>
        </a>
      </div>

      {/* Stats KPI Cards */}
      <PolicyTrackerStats stats={stats} loading={loadingStats} />

      {/* Charts Section */}
      <PolicyTrackerCharts
        categories={categories}
        temporalData={temporalData}
        loading={loadingCharts}
      />
    </div>
  );
}
