/**
 * ThreatAnalysisTab Component
 * Correlation analysis and MITRE ATT&CK breakdown
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
  Treemap,
  Cell,
} from 'recharts';
import { Network, Shield, Target, Zap, Users, Globe } from 'lucide-react';
import {
  getTTPAnalysis,
  getIOCs,
  getCampaigns,
  type TTPAnalysis,
  type IOC,
  type Campaign,
  SEVERITY_COLORS,
} from '../../services/threatIntelligenceApi';

interface ThreatAnalysisTabProps {
  loading: boolean;
}

const TTP_CATEGORY_COLORS: Record<string, string> = {
  'Initial Access': '#DC2626',
  'Execution': '#F97316',
  'Persistence': '#EAB308',
  'Privilege Escalation': '#84CC16',
  'Defense Evasion': '#22C55E',
  'Credential Access': '#14B8A6',
  'Discovery': '#06B6D4',
  'Lateral Movement': '#3B82F6',
  'Collection': '#6366F1',
  'Command and Control': '#8B5CF6',
  'Exfiltration': '#A855F7',
  'Impact': '#EC4899',
};

const IOC_TYPE_LABELS: Record<string, string> = {
  ip: 'IP Address',
  domain: 'Domain',
  hash_md5: 'MD5 Hash',
  hash_sha256: 'SHA256 Hash',
  url: 'URL',
  email: 'Email',
};

export function ThreatAnalysisTab({ loading: parentLoading }: ThreatAnalysisTabProps) {
  const [ttpData, setTtpData] = useState<TTPAnalysis[]>([]);
  const [iocs, setIocs] = useState<IOC[]>([]);
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedTtp, setSelectedTtp] = useState<TTPAnalysis | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [ttpResult, iocResult, campaignResult] = await Promise.all([
        getTTPAnalysis(),
        getIOCs({ page: 1, pageSize: 50 }),
        getCampaigns({ page: 1, pageSize: 20, isActive: true }),
      ]);
      setTtpData(ttpResult);
      setIocs(iocResult.data);
      setCampaigns(campaignResult.data);
    } catch (error) {
      console.error('Error fetching analysis data:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Group TTPs by tactic category
  const ttpByCategory = ttpData.reduce((acc, ttp) => {
    const category = ttp.tactic || 'Unknown';
    if (!acc[category]) {
      acc[category] = [];
    }
    acc[category].push(ttp);
    return acc;
  }, {} as Record<string, TTPAnalysis[]>);

  // Prepare treemap data
  const treemapData = Object.entries(ttpByCategory).map(([category, ttps]) => ({
    name: category,
    children: ttps.map((ttp) => ({
      name: ttp.technique_id,
      value: ttp.threat_count,
      technique: ttp,
    })),
  }));

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

  if (loading || parentLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-red-500"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* MITRE ATT&CK Analysis */}
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Network className="w-5 h-5 text-red-500" />
            <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
              MITRE ATT&CK Techniques
            </h3>
          </div>
          <span className="text-xs text-gray-500 dark:text-gray-400">
            {ttpData.length} techniques observed
          </span>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Technique Distribution Chart */}
          <div className="h-[400px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={ttpData.slice(0, 15)}
                layout="vertical"
                margin={{ left: 80 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.3} />
                <XAxis
                  type="number"
                  tick={{ fill: '#9CA3AF', fontSize: 12 }}
                  axisLine={{ stroke: '#4B5563' }}
                />
                <YAxis
                  type="category"
                  dataKey="technique_id"
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
                  formatter={(value: number, name: string, props: any) => [
                    `${value} threats`,
                    props.payload.technique_name || props.payload.technique_id,
                  ]}
                />
                <Bar
                  dataKey="threat_count"
                  fill="#DC2626"
                  radius={[0, 4, 4, 0]}
                  onClick={(data) => setSelectedTtp(data)}
                  cursor="pointer"
                />
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Tactic Categories */}
          <div className="space-y-3 max-h-[400px] overflow-y-auto">
            <h4 className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
              By Tactic Category
            </h4>
            {Object.entries(ttpByCategory)
              .sort((a, b) => b[1].length - a[1].length)
              .map(([category, ttps]) => (
                <div
                  key={category}
                  className="p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg"
                >
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <div
                        className="w-3 h-3 rounded-full"
                        style={{ backgroundColor: TTP_CATEGORY_COLORS[category] || '#6B7280' }}
                      />
                      <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
                        {category}
                      </span>
                    </div>
                    <span className="text-xs text-gray-500 dark:text-gray-400">
                      {ttps.length} techniques
                    </span>
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {ttps.slice(0, 6).map((ttp) => (
                      <button
                        key={ttp.technique_id}
                        onClick={() => setSelectedTtp(ttp)}
                        className="px-2 py-0.5 text-xs bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-600 rounded hover:border-red-300 dark:hover:border-red-700 transition-colors"
                      >
                        {ttp.technique_id}
                      </button>
                    ))}
                    {ttps.length > 6 && (
                      <span className="px-2 py-0.5 text-xs text-gray-400">
                        +{ttps.length - 6} more
                      </span>
                    )}
                  </div>
                </div>
              ))}
          </div>
        </div>

        {/* Selected TTP Details */}
        {selectedTtp && (
          <div className="mt-4 p-4 bg-red-50 dark:bg-red-900/20 rounded-lg border border-red-200 dark:border-red-800">
            <div className="flex items-start justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <span className="px-2 py-0.5 text-xs font-mono bg-red-500 text-white rounded">
                    {selectedTtp.technique_id}
                  </span>
                  <h4 className="font-medium text-gray-900 dark:text-gray-100">
                    {selectedTtp.technique_name}
                  </h4>
                </div>
                {selectedTtp.tactic && (
                  <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">
                    Tactic: {selectedTtp.tactic}
                  </p>
                )}
              </div>
              <div className="text-right">
                <div className="text-2xl font-bold text-red-600">{selectedTtp.threat_count}</div>
                <div className="text-xs text-gray-500 dark:text-gray-400">threats using this technique</div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* IOC Analysis and Active Campaigns */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* IOC Distribution */}
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
          <div className="flex items-center gap-2 mb-4">
            <Target className="w-5 h-5 text-orange-500" />
            <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
              Indicators of Compromise
            </h3>
          </div>

          <div className="h-[200px] mb-4">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={iocChartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.3} />
                <XAxis
                  dataKey="name"
                  tick={{ fill: '#9CA3AF', fontSize: 11 }}
                  axisLine={{ stroke: '#4B5563' }}
                  angle={-45}
                  textAnchor="end"
                  height={60}
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
                />
                <Bar dataKey="count" fill="#F97316" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="space-y-2 max-h-[200px] overflow-y-auto">
            <h4 className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
              Recent IOCs
            </h4>
            {iocs.slice(0, 8).map((ioc) => (
              <div
                key={ioc.id}
                className="flex items-center justify-between p-2 bg-gray-50 dark:bg-gray-700/50 rounded text-sm"
              >
                <div className="flex items-center gap-2 min-w-0">
                  <span className="px-1.5 py-0.5 text-xs bg-orange-100 dark:bg-orange-900/30 text-orange-700 dark:text-orange-300 rounded">
                    {IOC_TYPE_LABELS[ioc.indicator_type] || ioc.indicator_type}
                  </span>
                  <span className="font-mono text-xs text-gray-700 dark:text-gray-300 truncate">
                    {ioc.indicator_value.length > 40
                      ? ioc.indicator_value.substring(0, 40) + '...'
                      : ioc.indicator_value}
                  </span>
                </div>
                <span className="text-xs text-gray-500 dark:text-gray-400">
                  {ioc.confidence}%
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Active Campaigns */}
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
          <div className="flex items-center gap-2 mb-4">
            <Zap className="w-5 h-5 text-yellow-500" />
            <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
              Active Campaigns
            </h3>
          </div>

          {campaigns.length === 0 ? (
            <div className="text-center py-8">
              <Zap className="w-10 h-10 text-gray-300 dark:text-gray-600 mx-auto mb-2" />
              <p className="text-sm text-gray-500 dark:text-gray-400">No active campaigns tracked</p>
            </div>
          ) : (
            <div className="space-y-3">
              {campaigns.map((campaign) => (
                <div
                  key={campaign.id}
                  className="p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg"
                >
                  <div className="flex items-start justify-between">
                    <div>
                      <h4 className="font-medium text-gray-900 dark:text-gray-100">
                        {campaign.name}
                      </h4>
                      {campaign.threat_actor_name && (
                        <div className="flex items-center gap-1 mt-1 text-xs text-gray-500 dark:text-gray-400">
                          <Users className="w-3 h-3" />
                          {campaign.threat_actor_name}
                        </div>
                      )}
                    </div>
                    {campaign.is_active && (
                      <span className="px-2 py-0.5 text-xs bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 rounded-full">
                        Active
                      </span>
                    )}
                  </div>

                  {campaign.description && (
                    <p className="mt-2 text-sm text-gray-600 dark:text-gray-400 line-clamp-2">
                      {campaign.description}
                    </p>
                  )}

                  <div className="flex flex-wrap gap-2 mt-3">
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
      </div>

      {/* Correlation Matrix Placeholder */}
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
        <div className="flex items-center gap-2 mb-4">
          <Shield className="w-5 h-5 text-blue-500" />
          <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
            Threat Correlations
          </h3>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg text-center">
            <div className="text-2xl font-bold text-red-600">{ttpData.length}</div>
            <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">Unique TTPs</div>
          </div>
          <div className="p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg text-center">
            <div className="text-2xl font-bold text-orange-600">{iocs.length}</div>
            <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">IOCs Tracked</div>
          </div>
          <div className="p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg text-center">
            <div className="text-2xl font-bold text-yellow-600">{campaigns.length}</div>
            <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">Active Campaigns</div>
          </div>
          <div className="p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg text-center">
            <div className="text-2xl font-bold text-blue-600">
              {Object.keys(ttpByCategory).length}
            </div>
            <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">Tactic Categories</div>
          </div>
        </div>
      </div>
    </div>
  );
}
