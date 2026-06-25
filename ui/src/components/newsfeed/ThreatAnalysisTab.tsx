/**
 * ThreatAnalysisTab Component
 * IOC analysis and Active Campaigns tracking
 */

import { useState, useEffect, useCallback } from 'react';
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
import { Target, Zap, Users, Globe, Shield, TrendingUp, AlertTriangle, ChevronRight } from 'lucide-react';
import {
  getIOCs,
  getCampaigns,
  type IOC,
  type Campaign,
  SEVERITY_COLORS,
} from '../../services/threatIntelligenceApi';
import { CampaignDetailModal } from './CampaignDetailModal';

interface ThreatAnalysisTabProps {
  loading?: boolean;
  onCategoryFilter?: (category: string) => void;
  onCampaignArticlesClick?: (campaignId: number, campaignName: string) => void;
}

const IOC_TYPE_LABELS: Record<string, string> = {
  ip: 'IP Address',
  domain: 'Domain',
  hash_md5: 'MD5 Hash',
  hash_sha256: 'SHA256 Hash',
  hash_sha1: 'SHA1 Hash',
  url: 'URL',
  email: 'Email',
  cve: 'CVE',
};

const IOC_COLORS = [
  '#DC2626', // red
  '#F97316', // orange
  '#EAB308', // yellow
  '#22C55E', // green
  '#06B6D4', // cyan
  '#3B82F6', // blue
  '#8B5CF6', // purple
  '#EC4899', // pink
];

export function ThreatAnalysisTab({ loading: parentLoading, onCategoryFilter, onCampaignArticlesClick }: ThreatAnalysisTabProps) {
  const [iocs, setIocs] = useState<IOC[]>([]);
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedCampaign, setSelectedCampaign] = useState<Campaign | null>(null);
  const [iocStats, setIocStats] = useState<{
    total: number;
    byConfidence: { high: number; medium: number; low: number };
  }>({ total: 0, byConfidence: { high: 0, medium: 0, low: 0 } });

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [iocResult, campaignResult] = await Promise.all([
        getIOCs({ page: 1, pageSize: 100 }),
        getCampaigns({ page: 1, pageSize: 20, isActive: true }),
      ]);
      setIocs(iocResult.data);
      setCampaigns(campaignResult.data);

      // Calculate IOC confidence breakdown
      const stats = {
        total: iocResult.total,
        byConfidence: {
          high: 0,
          medium: 0,
          low: 0,
        },
      };
      iocResult.data.forEach((ioc) => {
        if (ioc.confidence >= 80) stats.byConfidence.high++;
        else if (ioc.confidence >= 50) stats.byConfidence.medium++;
        else stats.byConfidence.low++;
      });
      setIocStats(stats);
    } catch (error) {
      console.error('Error fetching analysis data:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // IOC type distribution
  const iocByType = iocs.reduce((acc, ioc) => {
    acc[ioc.indicator_type] = (acc[ioc.indicator_type] || 0) + 1;
    return acc;
  }, {} as Record<string, number>);

  const iocChartData = Object.entries(iocByType)
    .map(([type, count]) => ({
      name: IOC_TYPE_LABELS[type] || type,
      count,
      type,
    }))
    .sort((a, b) => b.count - a.count);

  // Pie chart data for IOC types
  const iocPieData = iocChartData.slice(0, 6).map((item, idx) => ({
    ...item,
    color: IOC_COLORS[idx % IOC_COLORS.length],
  }));

  if (loading || parentLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-red-500"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Summary Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
          <div className="flex items-center gap-2 text-orange-500 mb-2">
            <Target className="w-5 h-5" />
            <span className="text-sm font-medium">Total IOCs</span>
          </div>
          <div className="text-2xl font-bold text-gray-900 dark:text-gray-100">
            {iocStats.total}
          </div>
        </div>

        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
          <div className="flex items-center gap-2 text-red-500 mb-2">
            <AlertTriangle className="w-5 h-5" />
            <span className="text-sm font-medium">High Confidence</span>
          </div>
          <div className="text-2xl font-bold text-gray-900 dark:text-gray-100">
            {iocStats.byConfidence.high}
          </div>
        </div>

        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
          <div className="flex items-center gap-2 text-yellow-500 mb-2">
            <Zap className="w-5 h-5" />
            <span className="text-sm font-medium">Active Campaigns</span>
          </div>
          <div className="text-2xl font-bold text-gray-900 dark:text-gray-100">
            {campaigns.length}
          </div>
        </div>

        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
          <div className="flex items-center gap-2 text-blue-500 mb-2">
            <TrendingUp className="w-5 h-5" />
            <span className="text-sm font-medium">IOC Types</span>
          </div>
          <div className="text-2xl font-bold text-gray-900 dark:text-gray-100">
            {Object.keys(iocByType).length}
          </div>
        </div>
      </div>

      {/* IOC Analysis */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* IOC Type Distribution Chart */}
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
          <div className="flex items-center gap-2 mb-4">
            <Target className="w-5 h-5 text-orange-500" />
            <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
              IOC Distribution by Type
            </h3>
          </div>

          <div className="grid grid-cols-2 gap-4">
            {/* Bar Chart */}
            <div className="h-[250px]">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={iocChartData} layout="vertical" margin={{ left: 80 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.3} />
                  <XAxis
                    type="number"
                    tick={{ fill: '#9CA3AF', fontSize: 12 }}
                    axisLine={{ stroke: '#4B5563' }}
                  />
                  <YAxis
                    type="category"
                    dataKey="name"
                    tick={{ fill: '#9CA3AF', fontSize: 11 }}
                    axisLine={{ stroke: '#4B5563' }}
                    width={75}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#1F2937',
                      border: 'none',
                      borderRadius: '0.5rem',
                      color: '#F9FAFB',
                    }}
                  />
                  <Bar dataKey="count" fill="#F97316" radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>

            {/* Pie Chart */}
            <div className="h-[250px]">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={iocPieData}
                    dataKey="count"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    outerRadius={80}
                    label={({ name, percent }) =>
                      `${name.split(' ')[0]} ${(percent * 100).toFixed(0)}%`
                    }
                    labelLine={false}
                  >
                    {iocPieData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#1F2937',
                      border: 'none',
                      borderRadius: '0.5rem',
                      color: '#F9FAFB',
                    }}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>

        {/* Recent IOCs List */}
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <Shield className="w-5 h-5 text-red-500" />
              <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                Recent Indicators
              </h3>
            </div>
            <span className="text-xs text-gray-500 dark:text-gray-400">
              Showing top {Math.min(iocs.length, 12)} by confidence
            </span>
          </div>

          <div className="space-y-2 max-h-[300px] overflow-y-auto">
            {iocs
              .sort((a, b) => b.confidence - a.confidence)
              .slice(0, 12)
              .map((ioc) => (
                <div
                  key={ioc.id}
                  className="flex items-center justify-between p-2 bg-gray-50 dark:bg-gray-700/50 rounded text-sm"
                >
                  <div className="flex items-center gap-2 min-w-0 flex-1">
                    <span className="px-1.5 py-0.5 text-xs bg-orange-100 dark:bg-orange-900/30 text-orange-700 dark:text-orange-300 rounded whitespace-nowrap">
                      {IOC_TYPE_LABELS[ioc.indicator_type] || ioc.indicator_type}
                    </span>
                    <span className="font-mono text-xs text-gray-700 dark:text-gray-300 truncate">
                      {ioc.indicator_value.length > 35
                        ? ioc.indicator_value.substring(0, 35) + '...'
                        : ioc.indicator_value}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 ml-2">
                    <div
                      className={`w-2 h-2 rounded-full ${
                        ioc.confidence >= 80
                          ? 'bg-red-500'
                          : ioc.confidence >= 50
                          ? 'bg-yellow-500'
                          : 'bg-gray-400'
                      }`}
                    />
                    <span className="text-xs text-gray-500 dark:text-gray-400 whitespace-nowrap">
                      {ioc.confidence}%
                    </span>
                  </div>
                </div>
              ))}
          </div>

          {iocs.length === 0 && (
            <div className="text-center py-8">
              <Target className="w-10 h-10 text-gray-300 dark:text-gray-600 mx-auto mb-2" />
              <p className="text-sm text-gray-500 dark:text-gray-400">No IOCs tracked yet</p>
            </div>
          )}
        </div>
      </div>

      {/* Active Campaigns */}
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Zap className="w-5 h-5 text-yellow-500" />
            <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
              Active Campaigns
            </h3>
          </div>
          <span className="text-xs text-gray-500 dark:text-gray-400">
            {campaigns.length} active
          </span>
        </div>

        {campaigns.length === 0 ? (
          <div className="text-center py-8">
            <Zap className="w-10 h-10 text-gray-300 dark:text-gray-600 mx-auto mb-2" />
            <p className="text-sm text-gray-500 dark:text-gray-400">No active campaigns tracked</p>
            <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
              Campaigns are auto-detected from threat patterns or can be manually created
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {campaigns.map((campaign) => (
              <div
                key={campaign.id}
                onClick={() => setSelectedCampaign(campaign)}
                className="group p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg border border-gray-200 dark:border-gray-600 hover:border-yellow-400 dark:hover:border-yellow-500 cursor-pointer transition-colors"
              >
                <div className="flex items-start justify-between mb-2">
                  <h4 className="font-medium text-gray-900 dark:text-gray-100">
                    {campaign.name}
                  </h4>
                  <div className="flex items-center gap-2">
                    {campaign.is_active && (
                      <span className="px-2 py-0.5 text-xs bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 rounded-full">
                        Active
                      </span>
                    )}
                    <ChevronRight className="w-4 h-4 text-gray-400 opacity-0 group-hover:opacity-100 transition-opacity" />
                  </div>
                </div>

                {campaign.threat_actor_name && (
                  <div className="flex items-center gap-1 text-xs text-gray-500 dark:text-gray-400 mb-2">
                    <Users className="w-3 h-3" />
                    {campaign.threat_actor_name}
                  </div>
                )}

                {campaign.description && (
                  <p className="text-sm text-gray-600 dark:text-gray-400 line-clamp-2 mb-3">
                    {campaign.description}
                  </p>
                )}

                <div className="flex flex-wrap gap-1.5">
                  {campaign.target_countries?.slice(0, 3).map((country) => (
                    <span
                      key={country}
                      className="flex items-center gap-1 px-2 py-0.5 text-xs bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-300 rounded"
                    >
                      <Globe className="w-3 h-3" />
                      {country}
                    </span>
                  ))}
                  {campaign.target_industries?.slice(0, 2).map((industry) => (
                    <span
                      key={industry}
                      className="px-2 py-0.5 text-xs bg-purple-50 dark:bg-purple-900/20 text-purple-700 dark:text-purple-300 rounded"
                    >
                      {industry}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
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
