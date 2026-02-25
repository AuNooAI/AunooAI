import React from 'react';
import { Shield } from 'lucide-react';
import type { Campaign } from '../../services/threatIntelligenceApi';

interface CampaignTimelineChartProps {
  campaigns: Campaign[];
  onCampaignClick: (campaign: Campaign) => void;
}

export function CampaignTimelineChart({ campaigns, onCampaignClick }: CampaignTimelineChartProps) {
  if (!campaigns || campaigns.length === 0) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3">Campaign Timeline</h3>
        <div className="flex items-center justify-center h-24 text-sm text-gray-500 dark:text-gray-400">
          No campaigns tracked yet
        </div>
      </div>
    );
  }

  // Sort campaigns by start date
  const sorted = [...campaigns].sort((a, b) => {
    const da = a.start_date ? new Date(a.start_date).getTime() : 0;
    const db = b.start_date ? new Date(b.start_date).getTime() : 0;
    return da - db;
  });

  // Determine overall date range
  const allDates = sorted.flatMap((c) => [
    c.start_date ? new Date(c.start_date).getTime() : null,
    c.end_date ? new Date(c.end_date).getTime() : null,
  ]).filter((d): d is number => d !== null);
  const minDate = allDates.length > 0 ? Math.min(...allDates) : Date.now() - 90 * 86400000;
  const maxDate = Math.max(Date.now(), ...(allDates.length > 0 ? [Math.max(...allDates)] : []));
  const range = maxDate - minDate || 1;

  const barColors = [
    'bg-red-500', 'bg-orange-500', 'bg-yellow-500', 'bg-purple-500',
    'bg-blue-500', 'bg-green-500', 'bg-pink-500', 'bg-indigo-500',
  ];

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
      <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-4">Campaign Timeline</h3>
      <div className="space-y-2">
        {sorted.map((campaign, idx) => {
          const start = campaign.start_date ? new Date(campaign.start_date).getTime() : minDate;
          const end = campaign.end_date ? new Date(campaign.end_date).getTime() : Date.now();
          const leftPct = ((start - minDate) / range) * 100;
          const widthPct = Math.max(((end - start) / range) * 100, 2); // min 2% width for visibility
          const color = barColors[idx % barColors.length];

          return (
            <div
              key={campaign.id}
              className="group relative cursor-pointer"
              onClick={() => onCampaignClick(campaign)}
            >
              <div className="flex items-center gap-2 mb-0.5">
                <Shield className="w-3 h-3 text-gray-400 flex-shrink-0" />
                <span className="text-xs font-medium text-gray-700 dark:text-gray-300 truncate max-w-[200px]">
                  {campaign.name}
                </span>
                {campaign.is_active && (
                  <span className="px-1.5 py-0.5 text-[10px] bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300 rounded-full leading-none">
                    Active
                  </span>
                )}
                <span className="text-[10px] text-gray-400 ml-auto">
                  {campaign.threat_count} threats · {campaign.article_count} articles
                </span>
              </div>
              <div className="relative h-4 bg-gray-100 dark:bg-gray-700 rounded overflow-hidden">
                <div
                  className={`absolute top-0 h-full ${color} rounded opacity-80 group-hover:opacity-100 transition-opacity`}
                  style={{ left: `${leftPct}%`, width: `${widthPct}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>
      {/* Date axis labels */}
      <div className="flex justify-between mt-2 text-[10px] text-gray-400">
        <span>{new Date(minDate).toLocaleDateString('en-US', { month: 'short', year: 'numeric' })}</span>
        <span>{new Date(maxDate).toLocaleDateString('en-US', { month: 'short', year: 'numeric' })}</span>
      </div>
    </div>
  );
}
