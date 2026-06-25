/**
 * ThreatIntelligenceTab Component
 * Main container for the threat intelligence analysis feature
 */

import { useState, useCallback } from 'react';
import { RefreshCw, AlertCircle, X, Shield, Download, Calendar } from 'lucide-react';
import { useThreatIntelligence } from '../../hooks/useThreatIntelligence';
import { ThreatIntelligenceTabs, type ThreatIntelTab } from './ThreatIntelligenceTabs';
import { ThreatOverviewTab } from './ThreatOverviewTab';
import { ThreatMapTab } from './ThreatMapTab';
import { ThreatTimelineTab } from './ThreatTimelineTab';
import { ThreatActorsTab } from './ThreatActorsTab';
import { ThreatCategoriesTab } from './ThreatCategoriesTab';
import { ThreatAnalysisTab } from './ThreatAnalysisTab';
import { ThreatInsightsTab } from './ThreatInsightsTab';
import { ThreatArticlesTab } from './ThreatArticlesTab';
import { ThreatImportModal } from './ThreatImportModal';
import { ThreatScheduleModal } from './ThreatScheduleModal';
import type { ThreatMapData, ThreatCategory, SeverityLevel, ThreatActor } from '../../services/threatIntelligenceApi';

interface ThreatIntelligenceTabProps {
  onArticleClick?: (article: { uri: string; title?: string }) => void;
  model?: string;
}

export function ThreatIntelligenceTab({ onArticleClick, model = 'gpt-5.4-mini' }: ThreatIntelligenceTabProps) {
  const [showImportModal, setShowImportModal] = useState(false);
  const [showScheduleModal, setShowScheduleModal] = useState(false);

  const {
    stats,
    mapThreats,
    threats,
    totalThreats,
    totalPages,
    timeline,
    dailyCounts,
    categories,
    config,
    loading,
    loadingStats,
    loadingMap,
    loadingThreats,
    loadingTimeline,
    loadingDailyCounts,
    loadingCategories,
    error,
    updateConfig,
    fetchTimeline,
    fetchDailyCounts,
    fetchCategories,
    refresh,
    clearError,
  } = useThreatIntelligence();

  const [activeTab, setActiveTab] = useState<ThreatIntelTab>('overview');
  const [selectedThreat, setSelectedThreat] = useState<ThreatMapData | null>(null);
  const [articleThreatFilter, setArticleThreatFilter] = useState<ThreatMapData | null>(null);
  const [articleSeverityFilter, setArticleSeverityFilter] = useState<SeverityLevel | null>(null);
  const [articleActorFilter, setArticleActorFilter] = useState<ThreatActor | null>(null);
  const [articleCampaignFilter, setArticleCampaignFilter] = useState<{ id: number; name: string } | null>(null);

  // Handle threat click from any tab - navigate to articles with filter
  const handleThreatClick = useCallback((threat: ThreatMapData) => {
    setSelectedThreat(threat);
    setArticleThreatFilter(threat);
    setArticleActorFilter(null);
    setActiveTab('articles');
  }, []);

  // Handle actor articles click - navigate to articles filtered by actor
  const handleActorArticlesClick = useCallback((actor: ThreatActor) => {
    setArticleActorFilter(actor);
    setArticleThreatFilter(null);
    setArticleSeverityFilter(null);
    setArticleCampaignFilter(null);
    setActiveTab('articles');
  }, []);

  // Handle campaign articles click - navigate to articles filtered by campaign
  const handleCampaignArticlesClick = useCallback((campaignId: number, campaignName: string) => {
    setArticleCampaignFilter({ id: campaignId, name: campaignName });
    setArticleActorFilter(null);
    setArticleThreatFilter(null);
    setArticleSeverityFilter(null);
    setActiveTab('articles');
  }, []);

  // Clear the filters on articles tab
  const handleThreatFilterClear = useCallback(() => {
    setArticleThreatFilter(null);
    setArticleSeverityFilter(null);
    setArticleActorFilter(null);
    setArticleCampaignFilter(null);
  }, []);

  // Handle severity level filter from overview tab
  const handleOverviewSeverityFilter = useCallback((level: SeverityLevel) => {
    setArticleSeverityFilter(level);
    setArticleThreatFilter(null);
    setArticleActorFilter(null);
    setActiveTab('articles');
  }, []);

  // Handle threat type filter change
  const handleThreatTypesChange = useCallback(
    (threatTypes: ThreatCategory[]) => {
      updateConfig({ selectedThreatTypes: threatTypes, page: 1 });
    },
    [updateConfig]
  );

  // Handle severity level filter change
  const handleSeverityLevelsChange = useCallback(
    (levels: SeverityLevel[]) => {
      updateConfig({ selectedSeverityLevels: levels, page: 1 });
    },
    [updateConfig]
  );

  // Handle sort change
  const handleSortChange = useCallback(
    (sortBy: string, sortOrder: string) => {
      updateConfig({
        sortBy: sortBy as typeof config.sortBy,
        sortOrder: sortOrder as typeof config.sortOrder,
        page: 1,
      });
    },
    [updateConfig]
  );

  // Handle page change
  const handlePageChange = useCallback(
    (page: number) => {
      updateConfig({ page });
    },
    [updateConfig]
  );

  // Handle days back change
  const handleDaysBackChange = useCallback(
    (daysBack: number) => {
      updateConfig({ daysBack });
    },
    [updateConfig]
  );

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 relative z-[1001]">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-red-100 dark:bg-red-900/30 rounded-lg">
            <Shield className="w-6 h-6 text-red-600 dark:text-red-400" />
          </div>
          <div>
            <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100">
              Threat Intelligence
            </h2>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Cyber threat tracking and analysis
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {/* Tab Navigation */}
          <ThreatIntelligenceTabs activeTab={activeTab} onTabChange={setActiveTab} />

          {/* Days Back Selector */}
          <select
            value={config.daysBack}
            onChange={(e) => handleDaysBackChange(Number(e.target.value))}
            className="px-3 py-2 text-sm bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-red-500 dark:text-gray-100"
          >
            <option value={7}>Last 7 days</option>
            <option value={30}>Last 30 days</option>
            <option value={90}>Last 90 days</option>
            <option value={180}>Last 6 months</option>
            <option value={365}>Last year</option>
          </select>

          {/* Schedule Button */}
          <button
            onClick={() => setShowScheduleModal(true)}
            className="flex items-center gap-2 px-3 py-2 text-sm bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors border border-gray-200 dark:border-gray-700"
          >
            <Calendar className="w-4 h-4" />
            Schedule
          </button>

          {/* Update Button */}
          <button
            onClick={() => setShowImportModal(true)}
            className="flex items-center gap-2 px-3 py-2 text-sm bg-red-500 text-white rounded-lg hover:bg-red-600 transition-colors"
          >
            <Download className="w-4 h-4" />
            Update
          </button>

          {/* Refresh Button */}
          <button
            onClick={refresh}
            disabled={loading}
            className="flex items-center gap-2 px-3 py-2 text-sm bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300 rounded-lg hover:bg-red-100 dark:hover:bg-red-900/30 disabled:opacity-50 transition-colors"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* Error Alert */}
      {error && (
        <div className="flex items-start gap-3 p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
          <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
          <div className="flex-1">
            <p className="text-sm text-red-700 dark:text-red-300">{error}</p>
          </div>
          <button
            onClick={clearError}
            className="text-red-500 hover:text-red-700 dark:hover:text-red-300"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Tab Content */}
      {activeTab === 'overview' && (
        <ThreatOverviewTab
          stats={stats}
          threats={mapThreats}
          loading={loadingStats || loadingMap}
          onThreatClick={handleThreatClick}
          onSeverityFilter={handleOverviewSeverityFilter}
          onCategoryFilter={(category) => {
            handleThreatTypesChange([category as ThreatCategory]);
            setActiveTab('articles');
          }}
        />
      )}

      {activeTab === 'map' && (
        <ThreatMapTab
          threats={mapThreats}
          loading={loadingMap}
          selectedThreatTypes={config.selectedThreatTypes}
          selectedSeverityLevels={config.selectedSeverityLevels}
          onThreatTypesChange={handleThreatTypesChange}
          onSeverityLevelsChange={handleSeverityLevelsChange}
          onThreatClick={handleThreatClick}
        />
      )}

      {activeTab === 'timeline' && (
        <ThreatTimelineTab
          timeline={timeline}
          dailyCounts={dailyCounts}
          loading={loadingTimeline || loadingDailyCounts}
          onLoad={() => {
            fetchTimeline();
            fetchDailyCounts();
          }}
          onCampaignArticlesClick={handleCampaignArticlesClick}
        />
      )}

      {activeTab === 'actors' && (
        <ThreatActorsTab
          onThreatClick={handleThreatClick}
          onActorArticlesClick={handleActorArticlesClick}
        />
      )}

      {activeTab === 'categories' && (
        <ThreatCategoriesTab
          categories={categories}
          loading={loadingCategories}
          onLoad={fetchCategories}
          onCategoryFilter={(category) => {
            handleThreatTypesChange([category as ThreatCategory]);
            setActiveTab('articles');
          }}
        />
      )}

      {activeTab === 'analysis' && (
        <ThreatAnalysisTab
          onCategoryFilter={(category) => {
            handleThreatTypesChange([category as ThreatCategory]);
            setActiveTab('articles');
          }}
          onCampaignArticlesClick={handleCampaignArticlesClick}
        />
      )}

      {activeTab === 'insights' && (
        <ThreatInsightsTab
          stats={stats}
          threats={mapThreats}
          loading={loadingStats}
          model={model}
        />
      )}

      {activeTab === 'articles' && (
        <ThreatArticlesTab
          onArticleClick={(article) => {
            console.log('Article clicked:', article);
          }}
          onThreatClick={(threatId, threatName) => {
            // Find the threat from mapThreats and filter articles by it
            const threat = mapThreats.find((t) => t.id === threatId);
            if (threat) {
              setArticleThreatFilter(threat);
              setArticleActorFilter(null);
            }
          }}
          initialThreat={articleThreatFilter ? { id: articleThreatFilter.id, threat_name: articleThreatFilter.threat_name } : null}
          initialActor={articleActorFilter ? { id: articleActorFilter.id, name: articleActorFilter.name } : null}
          initialCampaign={articleCampaignFilter}
          onThreatFilterClear={handleThreatFilterClear}
          initialSeverityLevel={articleSeverityFilter}
        />
      )}

      {/* Import Modal */}
      <ThreatImportModal
        isOpen={showImportModal}
        onClose={() => setShowImportModal(false)}
        onImportComplete={refresh}
        model={model}
      />

      {/* Schedule Modal */}
      <ThreatScheduleModal
        isOpen={showScheduleModal}
        onClose={() => setShowScheduleModal(false)}
      />
    </div>
  );
}
