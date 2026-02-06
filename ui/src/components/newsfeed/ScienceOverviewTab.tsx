/**
 * ScienceWatch Overview Tab
 * Main dashboard with stats and key charts
 */

import type { ScienceStats, ScienceCategory, TemporalData, EscalationData } from '../../services/scienceFundingApi';
import { ScienceFundingStats } from './ScienceFundingStats';
import { ScienceFundingCharts } from './ScienceFundingCharts';

interface ScienceOverviewTabProps {
  stats: ScienceStats | null;
  categories: ScienceCategory[];
  temporalData: TemporalData[];
  escalationData: EscalationData[];
  loadingStats: boolean;
  loadingCharts: boolean;
}

export function ScienceOverviewTab({
  stats,
  categories,
  temporalData,
  loadingStats,
  loadingCharts,
}: ScienceOverviewTabProps) {
  return (
    <div className="space-y-6">
      {/* Stats KPI Cards */}
      <ScienceFundingStats stats={stats} loading={loadingStats} />

      {/* Charts Section */}
      <ScienceFundingCharts
        categories={categories}
        temporalData={temporalData}
        loading={loadingCharts}
      />
    </div>
  );
}
