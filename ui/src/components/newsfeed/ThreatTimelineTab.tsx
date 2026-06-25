/**
 * ThreatTimelineTab Component
 * Temporal trends visualization with campaign timeline
 */

import { useEffect, useState, useCallback } from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  AreaChart,
  Area,
  Legend,
} from 'recharts';
import type { TimelineDataPoint, DailyCount, Campaign } from '../../services/threatIntelligenceApi';
import { getCampaigns } from '../../services/threatIntelligenceApi';
import { CampaignDetailModal } from './CampaignDetailModal';
import { CampaignTimelineChart } from './CampaignTimelineChart';

interface ThreatTimelineTabProps {
  timeline: TimelineDataPoint[];
  dailyCounts: DailyCount[];
  loading: boolean;
  onLoad: () => void;
  onCampaignClick?: (campaign: Campaign) => void;
  onCampaignArticlesClick?: (campaignId: number, campaignName: string) => void;
}

export function ThreatTimelineTab({ timeline, dailyCounts, loading, onLoad, onCampaignClick, onCampaignArticlesClick }: ThreatTimelineTabProps) {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [campaignsLoading, setCampaignsLoading] = useState(true);
  const [selectedCampaign, setSelectedCampaign] = useState<Campaign | null>(null);

  const handleCampaignClick = (campaign: Campaign) => {
    if (onCampaignClick) {
      onCampaignClick(campaign);
    } else {
      setSelectedCampaign(campaign);
    }
  };

  const fetchCampaigns = useCallback(async () => {
    setCampaignsLoading(true);
    try {
      const result = await getCampaigns({ page: 1, pageSize: 50 });
      setCampaigns(result.data);
    } catch (error) {
      console.error('Error fetching campaigns:', error);
    } finally {
      setCampaignsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (timeline.length === 0 || dailyCounts.length === 0) {
      onLoad();
    }
    fetchCampaigns();
  }, [onLoad, timeline.length, dailyCounts.length, fetchCampaigns]);

  if (loading && timeline.length === 0) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-red-500"></div>
      </div>
    );
  }

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  };

  return (
    <div className="space-y-6">
      {/* Campaign Timeline Chart */}
      {campaignsLoading ? (
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
          <div className="flex items-center justify-center h-32">
            <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-yellow-500"></div>
          </div>
        </div>
      ) : (
        <CampaignTimelineChart
          campaigns={campaigns}
          onCampaignClick={handleCampaignClick}
        />
      )}

      {/* Article Activity Chart */}
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-4">
          Threat Article Activity
        </h3>
        <div className="h-[300px]">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={dailyCounts}>
              <defs>
                <linearGradient id="articleGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#EF4444" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#EF4444" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.3} />
              <XAxis
                dataKey="date"
                tickFormatter={formatDate}
                tick={{ fill: '#9CA3AF', fontSize: 12 }}
                axisLine={{ stroke: '#4B5563' }}
              />
              <YAxis
                tick={{ fill: '#9CA3AF', fontSize: 12 }}
                axisLine={{ stroke: '#4B5563' }}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: '#1F2937',
                  border: 'none',
                  borderRadius: '0.5rem',
                  color: '#F9FAFB',
                }}
                labelFormatter={formatDate}
              />
              <Legend />
              <Area
                type="monotone"
                dataKey="article_count"
                name="Articles"
                stroke="#EF4444"
                fill="url(#articleGradient)"
                strokeWidth={2}
              />
              <Line
                type="monotone"
                dataKey="rolling_avg"
                name="7-day Avg"
                stroke="#F97316"
                strokeWidth={2}
                dot={false}
                strokeDasharray="5 5"
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Severity Trend Chart */}
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-4">
          Average Severity Over Time
        </h3>
        <div className="h-[250px]">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={timeline}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.3} />
              <XAxis
                dataKey="date"
                tickFormatter={formatDate}
                tick={{ fill: '#9CA3AF', fontSize: 12 }}
                axisLine={{ stroke: '#4B5563' }}
              />
              <YAxis
                domain={[0, 100]}
                tick={{ fill: '#9CA3AF', fontSize: 12 }}
                axisLine={{ stroke: '#4B5563' }}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: '#1F2937',
                  border: 'none',
                  borderRadius: '0.5rem',
                  color: '#F9FAFB',
                }}
                labelFormatter={formatDate}
                formatter={(value: number) => [value.toFixed(1), 'Avg Severity']}
              />
              <Line
                type="monotone"
                dataKey="avg_severity"
                stroke="#DC2626"
                strokeWidth={2}
                dot={{ fill: '#DC2626', r: 3 }}
                activeDot={{ r: 5 }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Threat Count Over Time */}
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-4">
          Active Threats Over Time
        </h3>
        <div className="h-[250px]">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={timeline}>
              <defs>
                <linearGradient id="threatGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#3B82F6" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#3B82F6" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.3} />
              <XAxis
                dataKey="date"
                tickFormatter={formatDate}
                tick={{ fill: '#9CA3AF', fontSize: 12 }}
                axisLine={{ stroke: '#4B5563' }}
              />
              <YAxis
                tick={{ fill: '#9CA3AF', fontSize: 12 }}
                axisLine={{ stroke: '#4B5563' }}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: '#1F2937',
                  border: 'none',
                  borderRadius: '0.5rem',
                  color: '#F9FAFB',
                }}
                labelFormatter={formatDate}
              />
              <Area
                type="monotone"
                dataKey="threat_count"
                name="Threats"
                stroke="#3B82F6"
                fill="url(#threatGradient)"
                strokeWidth={2}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Campaign Detail Modal */}
      {selectedCampaign && (
        <CampaignDetailModal
          campaign={selectedCampaign}
          onClose={() => setSelectedCampaign(null)}
          onViewArticles={onCampaignArticlesClick}
        />
      )}
    </div>
  );
}
