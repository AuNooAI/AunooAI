/**
 * Trend Convergence Dashboard - Figma Design Implementation
 */

import { useState, useEffect } from 'react';
import { useTrendConvergence } from './hooks/useTrendConvergence';
import { SharedNavigation } from './components/SharedNavigation';
import { TabNavigation } from './components/TabNavigation';
import { TimelineBar } from './components/TimelineBar';
import { ConvergenceCard } from './components/ConvergenceCard';
import { ImpactTimelineCard } from './components/ImpactTimelineCard';
import { FutureHorizons } from './components/FutureHorizons';
import { OrganizationalProfileModal } from './components/OrganizationalProfileModal';
import { OnboardingWizard } from './components/onboarding/OnboardingWizard';
import { Bell, Settings, Download, Image as ImageIcon, FileText, RefreshCw, Clock, TrendingUp, Target } from 'lucide-react';
import { Button } from './components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './components/ui/select';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from './components/ui/dialog';
import { Loader2, AlertCircle } from 'lucide-react';
import { Alert, AlertDescription, AlertTitle } from './components/ui/alert';
import { calculateContextInfo, type ContextInfo } from './utils/contextCalculation';

function App() {
  const {
    data,
    topics,
    profiles,
    models,
    config,
    loading,
    error,
    generateAnalysis,
    updateConfig,
    clearError,
  } = useTrendConvergence();

  const [activeTab, setActiveTab] = useState('strategic-recommendations');
  const [isConfigOpen, setIsConfigOpen] = useState(false);
  const [isProfileModalOpen, setIsProfileModalOpen] = useState(false);
  const [isOnboardingOpen, setIsOnboardingOpen] = useState(false);
  const [contextInfo, setContextInfo] = useState<ContextInfo | null>(null);

  // Check URL parameters for auto-opening onboarding wizard
  useEffect(() => {
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('onboarding') === 'true') {
      setIsOnboardingOpen(true);
      // Remove the parameter from URL without reloading
      window.history.replaceState({}, '', window.location.pathname);
    }
  }, []);

  // Calculate context info when model or sample size changes
  useEffect(() => {
    if (config.model) {
      const sampleSizeMode = config.custom_limit ? 'custom' : 'auto';
      const info = calculateContextInfo(config.model, sampleSizeMode, config.custom_limit);
      setContextInfo(info);
    }
  }, [config.model, config.custom_limit]);

  const handleGenerate = async () => {
    await generateAnalysis();
    setIsConfigOpen(false);
  };

  return (
    <div className="flex h-screen bg-gray-50">
      {/* Shared Navigation */}
      <SharedNavigation currentPage="anticipate" />

      {/* Main Content */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Top Header */}
        <div className="bg-white border-b border-gray-200 px-6 py-3 flex items-center justify-between">
          {/* Breadcrumb */}
          <div className="flex items-center gap-2 text-sm text-gray-700">
            <span>Explore</span>
            <span>/</span>
            <span className="font-medium text-gray-950">Strategic Recommendations</span>
            <span>•</span>
            <span>Current indicators and potential disruption scenarios</span>
          </div>

          {/* Right Icons */}
          <div className="flex items-center gap-2">
            <button className="p-2 hover:bg-gray-100 rounded-md">
              <Bell className="w-5 h-5 text-gray-700" />
            </button>
            <button
              onClick={() => setIsOnboardingOpen(true)}
              className="px-4 py-2 bg-gray-100 hover:bg-gray-200 rounded-md text-sm font-medium flex items-center gap-2 text-gray-950"
            >
              Set up topic
              <span className="text-gray-500">+</span>
            </button>
          </div>
        </div>

        {/* Configuration Dialog - now only triggered from tab buttons */}
        <Dialog open={isConfigOpen} onOpenChange={setIsConfigOpen}>
          <DialogContent className="max-w-4xl">
            <DialogHeader>
              <DialogTitle className="text-2xl font-bold">Configure Trend Convergence Analysis</DialogTitle>
              <DialogDescription className="sr-only">
                    Configure your analysis settings
                  </DialogDescription>
                </DialogHeader>

                <div className="grid grid-cols-2 gap-x-6 gap-y-6 mt-6">
                  {/* Left Column */}
                  <div className="space-y-6">
                    {/* Topic Selection */}
                    <div>
                      <label className="text-sm font-semibold mb-2 block">Topic</label>
                      <Select value={config.topic} onValueChange={(value) => updateConfig({ topic: value })}>
                        <SelectTrigger className="w-full">
                          <SelectValue placeholder="Cloud Repatriation" />
                        </SelectTrigger>
                        <SelectContent>
                          {topics.map((topic) => (
                            <SelectItem key={topic.name} value={topic.name}>
                              {topic.display_name}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>

                    {/* Analysis Timeframe */}
                    <div>
                      <label className="text-sm font-semibold mb-2 block">Analysis Timeframe</label>
                      <Select
                        value={config.timeframe_days.toString()}
                        onValueChange={(value) => updateConfig({ timeframe_days: parseInt(value) })}
                      >
                        <SelectTrigger className="w-full">
                          <SelectValue placeholder="All Time" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="0">All Time</SelectItem>
                          <SelectItem value="30">Last 30 days</SelectItem>
                          <SelectItem value="90">Last 90 days</SelectItem>
                          <SelectItem value="180">Last 180 days</SelectItem>
                          <SelectItem value="365">Last year</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>

                    {/* AI Model */}
                    <div>
                      <label className="text-sm font-semibold mb-2 block">AI Model</label>
                      <Select value={config.model} onValueChange={(value) => updateConfig({ model: value })}>
                        <SelectTrigger className="w-full">
                          <SelectValue placeholder="gpt-4.1-mini" />
                        </SelectTrigger>
                        <SelectContent>
                          {models.map((model) => (
                            <SelectItem key={model.id} value={model.id}>
                              {model.name}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  </div>

                  {/* Right Column */}
                  <div className="space-y-6">
                    {/* Analysis Depth */}
                    <div>
                      <label className="text-sm font-semibold mb-2 block">Analysis Depth</label>
                      <Select value={config.analysis_depth} onValueChange={(value) => updateConfig({ analysis_depth: value })}>
                        <SelectTrigger className="w-full">
                          <SelectValue placeholder="Standard analysis" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="quick">Quick Overview</SelectItem>
                          <SelectItem value="standard">Standard analysis</SelectItem>
                          <SelectItem value="deep">Deep Dive</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>

                    {/* Organizational Profile */}
                    <div>
                      <label className="text-sm font-semibold mb-2 block">Organizational Profile</label>
                      <div className="flex gap-2">
                        <Select
                          value={config.profile_id?.toString() || ''}
                          onValueChange={(value) => updateConfig({ profile_id: value ? parseInt(value) : undefined })}
                        >
                          <SelectTrigger className="flex-1">
                            <SelectValue placeholder="Select Profile" />
                          </SelectTrigger>
                          <SelectContent>
                            {profiles.map((profile) => (
                              <SelectItem key={profile.id} value={profile.id!.toString()}>
                                {profile.name}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                        <Button
                          variant="outline"
                          size="icon"
                          className="shrink-0 bg-pink-500 hover:bg-pink-600 text-white border-0"
                          onClick={() => setIsProfileModalOpen(true)}
                        >
                          <Settings className="w-4 h-4" />
                        </Button>
                      </div>
                    </div>

                    {/* Article Sample Size */}
                    <div>
                      <label className="text-sm font-semibold mb-2 block">Article Sample Size</label>
                      <Select
                        value={config.custom_limit?.toString() || 'auto'}
                        onValueChange={(value) => {
                          if (value === 'auto') {
                            updateConfig({ custom_limit: undefined, sample_size_mode: 'auto' });
                          } else {
                            updateConfig({ custom_limit: parseInt(value), sample_size_mode: 'custom' });
                          }
                        }}
                      >
                        <SelectTrigger className="w-full">
                          <SelectValue placeholder="Auto Size" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="auto">Auto Size</SelectItem>
                          <SelectItem value="50">50 articles</SelectItem>
                          <SelectItem value="100">100 articles</SelectItem>
                          <SelectItem value="200">200 articles</SelectItem>
                        </SelectContent>
                      </Select>
                      {/* Context info */}
                      {contextInfo && (
                        <div className="mt-2 p-3 bg-cyan-50 rounded-lg flex items-start gap-2">
                          <AlertCircle className="w-4 h-4 text-cyan-600 mt-0.5 shrink-0" />
                          <div className="text-xs">
                            <span className={`font-medium ${contextInfo.colorClass}`}>
                              {contextInfo.displayText}
                            </span>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                </div>

                {/* Error Display */}
                {error && (
                  <Alert variant="destructive" className="mt-6">
                    <AlertCircle className="h-4 w-4" />
                    <AlertTitle>Error</AlertTitle>
                    <AlertDescription>{error}</AlertDescription>
                  </Alert>
                )}

                {/* Action Buttons */}
                <div className="flex justify-end gap-3 mt-8">
                  <Button
                    variant="outline"
                    onClick={() => setIsConfigOpen(false)}
                    className="px-6"
                  >
                    Clear
                  </Button>
                  <Button
                    onClick={handleGenerate}
                    disabled={loading || !config.topic}
                    className="px-6 bg-pink-500 hover:bg-pink-600"
                  >
                    {loading ? (
                      <>
                        <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                        Loading...
                      </>
                    ) : (
                      <>
                        Load analysis
                        <span className="ml-2">▶</span>
                      </>
                    )}
                  </Button>
                </div>
              </DialogContent>
            </Dialog>

        {/* Sub-header with tabs */}
        <div className="bg-white px-6 py-4">
          <TabNavigation activeTab={activeTab} onTabChange={setActiveTab} />
        </div>

        {/* Topic and Controls */}
        <div className="bg-white px-6 py-4 border-b border-gray-200">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Clock className="w-5 h-5 text-gray-500" />
              <div>
                <span className="text-sm text-gray-600">Topic:</span>
                <span className="ml-2 font-medium text-gray-950">{config.topic || 'Cloud Repatriation'}</span>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-sm text-gray-600">Last Updated:</span>
              <span className="text-sm font-medium">
                {data?._cache_info?.last_updated || new Date().toLocaleDateString('en-GB', { day: '2-digit', month: '2-digit', year: 'numeric' }).replace(/\//g, '.')}
              </span>
              <button
                onClick={() => generateAnalysis(true)}
                disabled={loading}
                className="p-2 hover:bg-gray-100 rounded-md disabled:opacity-50 disabled:cursor-not-allowed"
                title="Refresh analysis (bypass cache)"
              >
                <RefreshCw className={`w-4 h-4 text-gray-700 ${loading ? 'animate-spin' : ''}`} />
              </button>
            </div>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="bg-white px-6 py-3 border-b border-gray-200 flex justify-between items-center">
          <button
            onClick={() => setIsConfigOpen(true)}
            className="px-4 py-2 text-pink-500 hover:bg-pink-50 rounded-md text-sm font-medium flex items-center gap-2"
          >
            <Settings className="w-4 h-4" />
            Configure
          </button>
          <div className="flex items-center gap-2">
            <button className="px-3 py-2 hover:bg-gray-100 rounded-md text-sm font-medium flex items-center gap-2 text-pink-500">
              <FileText className="w-4 h-4" />
              Columns
            </button>
            <button className="px-3 py-2 hover:bg-gray-100 rounded-md text-sm font-medium flex items-center gap-2 text-pink-500">
              <ImageIcon className="w-4 h-4" />
              Image
            </button>
            <button className="px-3 py-2 hover:bg-gray-100 rounded-md text-sm font-medium flex items-center gap-2 text-pink-500">
              <Download className="w-4 h-4" />
              PDF
            </button>
          </div>
        </div>

        {/* Main Scrollable Content */}
        <div className="flex-1 overflow-y-auto px-6 py-6">
          {loading ? (
            <div className="flex items-center justify-center h-64">
              <div className="text-center">
                <Loader2 className="w-12 h-12 animate-spin text-pink-500 mx-auto mb-4" />
                <p className="text-gray-700">Analyzing trends and generating recommendations...</p>
              </div>
            </div>
          ) : !data ? (
            <div className="flex items-center justify-center h-64">
              <div className="text-center">
                <Target className="w-16 h-16 text-gray-300 mx-auto mb-4" />
                <h3 className="text-lg font-medium text-gray-950 mb-2">Ready to Analyze Trends</h3>
                <p className="text-gray-600 mb-4">Configure your analysis settings to get started</p>
                <Button onClick={() => setIsConfigOpen(true)}>
                  <Settings className="w-4 h-4 mr-2" />
                  Configure Analysis
                </Button>
              </div>
            </div>
          ) : (
            <div className="space-y-6 max-w-6xl">
              {/* Impact Timeline Tab */}
              {activeTab === 'impact-timeline' && (
                <>
                  {/* Impact Timeline Cards */}
                  <div className="space-y-4">
                    {(data.impact_timeline || []).map((item, idx) => {
                      const colors = ['orange', 'purple', 'green', 'blue', 'pink', 'lime'];
                      const color = colors[idx % colors.length] as any;

                      return (
                        <ImpactTimelineCard
                          key={idx}
                          title={typeof item === 'string' ? item : item.title || item.name}
                          description={typeof item === 'string' ? '' : item.description || ''}
                          timelineStart={typeof item === 'string' ? 2024 : item.timeline_start || 2024}
                          timelineEnd={typeof item === 'string' ? 2030 : item.timeline_end || 2030}
                          tooltipPositions={typeof item === 'string' ? [] : item.tooltip_positions || []}
                          color={color}
                        />
                      );
                    })}
                  </div>

                  {/* Key Insights from Evidence Synthesis */}
                  {data.key_insights && data.key_insights.length > 0 && (
                    <div className="mt-8 bg-cyan-50 border border-cyan-200 rounded-xl p-6">
                      <div className="flex items-center gap-2 mb-4">
                        <FileText className="w-5 h-5 text-cyan-600" />
                        <h2 className="text-xl font-bold">Key Insights from Evidence Synthesis</h2>
                      </div>
                      <div className="grid grid-cols-2 gap-4">
                        {data.key_insights.map((insight, idx) => {
                          const dotColors = ['bg-blue-500', 'bg-green-500', 'bg-red-500', 'bg-orange-500'];
                          const dotColor = dotColors[idx % dotColors.length];

                          return (
                            <div key={idx} className="flex gap-3">
                              <div className={`w-3 h-3 ${dotColor} rounded-full mt-1 shrink-0`}></div>
                              <div>
                                <div className="text-sm font-semibold text-gray-950 mb-1">
                                  {typeof insight === 'string' ? insight : insight.quote || insight.insight}
                                </div>
                                <div className="text-xs text-gray-700">
                                  {typeof insight === 'string' ? '' : insight.relevance || insight.source || ''}
                                </div>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}
                </>
              )}

              {/* Market Signals & Strategic Risks Tab */}
              {activeTab === 'market-signals' && (
                <>
                  {/* Future Signal Table */}
                  <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
                    <table className="w-full">
                      <thead className="bg-gray-50">
                        <tr>
                          <th className="text-left px-6 py-3 text-sm font-semibold text-gray-800">Future Signal</th>
                          <th className="text-left px-6 py-3 text-sm font-semibold text-gray-800">Frequency</th>
                          <th className="text-left px-6 py-3 text-sm font-semibold text-gray-800">Time to Impact</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-200">
                        {(data.future_signals || []).map((signal, idx) => (
                          <tr key={idx} className="hover:bg-gray-50">
                            <td className="px-6 py-4 text-sm text-gray-950">
                              {typeof signal === 'string' ? signal : signal.name || signal.description}
                            </td>
                            <td className="px-6 py-4">
                              <span className="inline-block px-3 py-1 text-xs font-medium bg-pink-100 text-pink-700 rounded">
                                {typeof signal === 'string' ? 'Badge' : signal.frequency || 'Badge'}
                              </span>
                            </td>
                            <td className="px-6 py-4 text-sm text-gray-700">
                              {typeof signal === 'string' ? 'Immediate/Mid/Long-term' : signal.time_to_impact || 'Immediate/Mid/Long-term'}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>

                  {/* Current Indicators and Opportunities */}
                  <div className="grid grid-cols-2 gap-6">
                    {/* Disruption Scenarios - Left Column */}
                    <div className="space-y-4">
                      <div className="bg-white border border-gray-200 rounded-xl p-5">
                        <div className="flex items-start gap-3">
                          <div className="flex-shrink-0 w-8 h-8 rounded-full bg-red-100 flex items-center justify-center">
                            <AlertCircle className="w-5 h-5 text-red-600" />
                          </div>
                          <div className="flex-1">
                            <h3 className="font-semibold text-gray-950 mb-2">
                              {data.disruption_scenarios?.[0]?.title || 'Current indicators and potential disruption scenarios'}
                            </h3>
                            <p className="text-sm text-gray-700">
                              {data.disruption_scenarios?.[0]?.description || 'High investment levels create bubble risk. 98% of investors worried about power reliability for datacenters, yet 70% anticipate increased funding driven by AI demand.'}
                            </p>
                          </div>
                        </div>
                      </div>

                      <div className="bg-white border border-gray-200 rounded-xl p-5">
                        <div className="flex items-start gap-3">
                          <div className="flex-shrink-0 w-8 h-8 rounded-full bg-red-100 flex items-center justify-center">
                            <AlertCircle className="w-5 h-5 text-red-600" />
                          </div>
                          <div className="flex-1">
                            <h3 className="font-semibold text-gray-950 mb-2">
                              {data.disruption_scenarios?.[1]?.title || 'Timeline Risk: AGI Overexpectation'}
                            </h3>
                            <p className="text-sm text-gray-700">
                              {data.disruption_scenarios?.[1]?.description || 'Ambitious timelines for achieving AGI may be overly optimistic due to diminishing returns and operational challenges.'}
                            </p>
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Opportunities - Right Column */}
                    <div className="space-y-4">
                      <div className="bg-white border border-gray-200 rounded-xl p-5">
                        <div className="flex items-start gap-3">
                          <div className="flex-shrink-0 w-8 h-8 rounded-full bg-green-100 flex items-center justify-center">
                            <Target className="w-5 h-5 text-green-600" />
                          </div>
                          <div className="flex-1">
                            <h3 className="font-semibold text-gray-950 mb-2">
                              {data.opportunities?.[0]?.title || 'Opportunity: Infrastructure Build-out'}
                            </h3>
                            <p className="text-sm text-gray-700">
                              {data.opportunities?.[0]?.description || 'Data center expansion creates competitive advantages for early movers who secure energy and infrastructure partnerships.'}
                            </p>
                          </div>
                        </div>
                      </div>

                      <div className="bg-white border border-gray-200 rounded-xl p-5">
                        <div className="flex items-start gap-3">
                          <div className="flex-shrink-0 w-8 h-8 rounded-full bg-green-100 flex items-center justify-center">
                            <Target className="w-5 h-5 text-green-600" />
                          </div>
                          <div className="flex-1">
                            <h3 className="font-semibold text-gray-950 mb-2">
                              {data.opportunities?.[1]?.title || 'Opportunity: Gradual Adoption Advantage'}
                            </h3>
                            <p className="text-sm text-gray-700">
                              {data.opportunities?.[1]?.description || 'Companies focusing on sustainable, gradual AI integration may outperform those chasing unrealistic AGI timelines.'}
                            </p>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Quoted Insights */}
                  <div className="space-y-4">
                    {(data.key_insights || []).slice(0, 2).map((insight, idx) => (
                      <div key={idx} className="bg-cyan-50 border border-cyan-200 rounded-xl p-6">
                        <div className="flex gap-4">
                          <div className="text-4xl text-cyan-400 font-serif leading-none">"</div>
                          <div className="flex-1">
                            <p className="text-gray-800 mb-2 italic">
                              {typeof insight === 'string' ? insight : insight.quote || insight.insight || insight.description}
                            </p>
                            <p className="text-sm text-gray-700 text-right">
                              — {typeof insight === 'string' ? 'Industry Analysis' : insight.source || insight.attribution || 'Industry Analysis'}
                            </p>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </>
              )}

              {/* Consensus Analysis Tab */}
              {activeTab === 'consensus' && (
                <>
                  {/* Convergence Cards */}
                  <div className="space-y-4">
                    {(data.convergences || []).map((convergence, idx) => {
                      const colors = ['purple', 'orange', 'blue', 'green', 'pink', 'indigo'];
                      const color = colors[idx % colors.length];

                      return (
                        <ConvergenceCard
                          key={idx}
                          name={convergence.name || 'Unnamed Convergence'}
                          description={convergence.description || ''}
                          consensusPercentage={convergence.consensus_percentage || 80}
                          timelineStartYear={convergence.timeline_start_year || 2024}
                          timelineEndYear={convergence.timeline_end_year || 2050}
                          optimisticOutlier={convergence.optimistic_outlier || {
                            year: 2024,
                            description: 'Optimistic scenario',
                            source_percentage: 25
                          }}
                          pessimisticOutlier={convergence.pessimistic_outlier || {
                            year: 2040,
                            description: 'Pessimistic scenario',
                            source_percentage: 35
                          }}
                          strategicImplication={convergence.strategic_implication || 'Strategic planning required'}
                          keyArticles={convergence.key_articles || []}
                          color={color}
                        />
                      );
                    })}
                  </div>

                  {/* Key Insights from Evidence Synthesis */}
                  {data.key_insights && data.key_insights.length > 0 && (
                    <div className="mt-8 bg-cyan-50 border border-cyan-200 rounded-xl p-6">
                      <div className="flex items-center gap-2 mb-4">
                        <FileText className="w-5 h-5 text-cyan-600" />
                        <h2 className="text-xl font-bold">Key Insights from Evidence Synthesis</h2>
                      </div>
                      <div className="grid grid-cols-2 gap-4">
                        {data.key_insights.map((insight, idx) => {
                          const dotColors = ['bg-blue-500', 'bg-green-500', 'bg-red-500', 'bg-orange-500'];
                          const dotColor = dotColors[idx % dotColors.length];

                          return (
                            <div key={idx} className="flex gap-3">
                              <div className={`w-3 h-3 ${dotColor} rounded-full mt-1 shrink-0`}></div>
                              <div>
                                <div className="text-sm font-semibold text-gray-950 mb-1">
                                  {typeof insight === 'string' ? insight : insight.quote || insight.insight}
                                </div>
                                <div className="text-xs text-gray-700">
                                  {typeof insight === 'string' ? '' : insight.relevance || insight.source || ''}
                                </div>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}
                </>
              )}

              {/* Strategic Recommendations Tab */}
              {activeTab === 'strategic-recommendations' && (
              <>
                {/* Strategic Recommendations */}
                <div>
                <h2 className="text-2xl font-bold mb-6">Strategic Recommendations</h2>
                <div className="grid grid-cols-3 gap-6">
                  {/* Near-term */}
                  <div className="bg-white border border-gray-200 rounded-lg overflow-hidden shadow-sm hover:shadow-md transition-shadow">
                    <div className="bg-green-50 p-6 border-b border-green-100">
                      <div className="flex items-center gap-2 mb-2">
                        <div className="w-8 h-8 rounded-full bg-green-100 flex items-center justify-center">
                          <Clock className="w-4 h-4 text-green-700" />
                        </div>
                        <h3 className="font-bold text-sm text-gray-900">NEAR-TERM</h3>
                      </div>
                      <div className="text-sm font-medium text-gray-700">
                        {data.strategic_recommendations?.near_term?.timeframe || '2025-2027'}
                      </div>
                    </div>
                    <div className="p-6">
                      <ul className="space-y-3">
                        {(data.strategic_recommendations?.near_term?.trends || []).slice(0, 4).map((trend, idx) => (
                          <li key={idx} className="text-sm text-gray-700 leading-relaxed flex gap-2">
                            <span className="text-green-600 font-bold">•</span>
                            <span>{typeof trend === 'string' ? trend : trend.name || trend.description}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                    <div className="px-6 pb-6">
                      <TimelineBar startYear={2024} endYear={2030} color="green" />
                    </div>
                  </div>

                  {/* Mid-term */}
                  <div className="bg-white border border-gray-200 rounded-lg overflow-hidden shadow-sm hover:shadow-md transition-shadow">
                    <div className="bg-amber-50 p-6 border-b border-amber-100">
                      <div className="flex items-center gap-2 mb-2">
                        <div className="w-8 h-8 rounded-full bg-amber-100 flex items-center justify-center">
                          <TrendingUp className="w-4 h-4 text-amber-700" />
                        </div>
                        <h3 className="font-bold text-sm text-gray-900">MID-TERM</h3>
                      </div>
                      <div className="text-sm font-medium text-gray-700">
                        {data.strategic_recommendations?.mid_term?.timeframe || '2027-2032'}
                      </div>
                    </div>
                    <div className="p-6">
                      <ul className="space-y-3">
                        {(data.strategic_recommendations?.mid_term?.trends || []).slice(0, 4).map((trend, idx) => (
                          <li key={idx} className="text-sm text-gray-700 leading-relaxed flex gap-2">
                            <span className="text-amber-600 font-bold">•</span>
                            <span>{typeof trend === 'string' ? trend : trend.name || trend.description}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                    <div className="px-6 pb-6">
                      <TimelineBar startYear={2027} endYear={2033} color="yellow" />
                    </div>
                  </div>

                  {/* Long-term */}
                  <div className="bg-white border border-gray-200 rounded-lg overflow-hidden shadow-sm hover:shadow-md transition-shadow">
                    <div className="bg-rose-50 p-6 border-b border-rose-100">
                      <div className="flex items-center gap-2 mb-2">
                        <div className="w-8 h-8 rounded-full bg-rose-100 flex items-center justify-center">
                          <Target className="w-4 h-4 text-rose-700" />
                        </div>
                        <h3 className="font-bold text-sm text-gray-900">LONG-TERM (2032+)</h3>
                      </div>
                      <div className="text-sm font-medium text-gray-700">
                        {data.strategic_recommendations?.long_term?.timeframe || '2032+'}
                      </div>
                    </div>
                    <div className="p-6">
                      <ul className="space-y-3">
                        {(data.strategic_recommendations?.long_term?.trends || []).slice(0, 4).map((trend, idx) => (
                          <li key={idx} className="text-sm text-gray-700 leading-relaxed flex gap-2">
                            <span className="text-rose-600 font-bold">•</span>
                            <span>{typeof trend === 'string' ? trend : trend.name || trend.description}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                    <div className="px-6 pb-6">
                      <TimelineBar startYear={2032} endYear={2040} color="red" />
                    </div>
                  </div>
                </div>
              </div>

              {/* Executive Decision Framework */}
              <div className="bg-orange-50 border border-orange-200 rounded-xl p-6">
                <div className="flex items-center gap-2 mb-4">
                  <Target className="w-5 h-5 text-orange-600" />
                  <h2 className="text-xl font-bold">Executive Decision Framework</h2>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  {(data.executive_decision_framework?.principles || []).map((principle, idx) => (
                    <div key={idx} className="bg-white rounded-lg p-4 border border-orange-200">
                      <h3 className="font-semibold text-sm mb-2">
                        {principle.title || principle.name}
                      </h3>
                      <p className="text-sm text-gray-800">
                        {principle.description || principle.content || principle.rationale}
                      </p>
                    </div>
                  ))}
                </div>
              </div>

              {/* Next Steps */}
              <div className="bg-white border border-gray-200 rounded-xl p-6">
                <div className="flex items-center gap-2 mb-4">
                  <FileText className="w-5 h-5 text-gray-700" />
                  <h2 className="text-xl font-bold">Next Steps:</h2>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  {(data.next_steps || []).map((step, idx) => (
                    <div key={idx} className="flex gap-3 p-4 bg-gray-50 rounded-lg border border-gray-200">
                      <div className="flex-shrink-0 w-6 h-6 rounded-full bg-gray-200 flex items-center justify-center text-sm font-medium text-gray-800">
                        {idx + 1}
                      </div>
                      <div className="flex-1">
                        <p className="text-sm text-gray-800">
                          {typeof step === 'string' ? step : step.action || step.description || JSON.stringify(step)}
                        </p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
              </>
              )}

              {/* Future Horizons Tab */}
              {activeTab === 'future-horizons' && (
                <FutureHorizons scenarios={data.scenarios || []} />
              )}
            </div>
          )}
        </div>
      </div>

      {/* Organizational Profile Modal */}
      <OrganizationalProfileModal
        open={isProfileModalOpen}
        onOpenChange={setIsProfileModalOpen}
        profiles={profiles}
        onSave={async (profile) => {
          // TODO: Implement save profile API call
          console.log('Saving profile:', profile);
        }}
      />

      {/* Onboarding Wizard */}
      <OnboardingWizard
        open={isOnboardingOpen}
        onOpenChange={setIsOnboardingOpen}
        onComplete={() => {
          // Reload topics after onboarding
          window.location.reload();
        }}
      />
    </div>
  );
}

export default App;
