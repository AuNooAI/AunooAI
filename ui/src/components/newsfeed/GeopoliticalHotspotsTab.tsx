/**
 * GeopoliticalHotspotsTab Component
 * Main container for the geopolitical hotspots analysis feature
 */

import { useState, useCallback } from 'react';
import { RefreshCw, AlertCircle, X, Globe, Download } from 'lucide-react';
import { useGeopoliticalHotspots } from '../../hooks/useGeopoliticalHotspots';
import { GeopoliticalHotspotsTabs, type GeopoliticalTab } from './GeopoliticalHotspotsTabs';
import { GeopoliticalOverviewTab } from './GeopoliticalOverviewTab';
import { GeopoliticalMapTab } from './GeopoliticalMapTab';
import { GeopoliticalTimelineTab } from './GeopoliticalTimelineTab';
import { GeopoliticalRegionsTab } from './GeopoliticalRegionsTab';
import { GeopoliticalThemesTab } from './GeopoliticalThemesTab';
import { GeopoliticalInsightsTab } from './GeopoliticalInsightsTab';
import { GeopoliticalArticlesTab } from './GeopoliticalArticlesTab';
import { GeopoliticalImportModal } from './GeopoliticalImportModal';
import { GeopoliticalAnalysisTab } from './GeopoliticalAnalysisTab';
import type { Hotspot } from '../../services/geopoliticalHotspotsApi';

interface GeopoliticalHotspotsTabProps {
  onArticleClick?: (article: { uri: string; title?: string }) => void;
  model?: string;
}

export function GeopoliticalHotspotsTab({ onArticleClick, model = 'gpt-4o-mini' }: GeopoliticalHotspotsTabProps) {
  const [showImportModal, setShowImportModal] = useState(false);

  const {
    stats,
    mapHotspots,
    hotspots,
    totalHotspots,
    totalPages,
    timeline,
    regions,
    categories,
    config,
    loading,
    loadingStats,
    loadingMap,
    loadingHotspots,
    loadingTimeline,
    loadingRegions,
    loadingCategories,
    error,
    updateConfig,
    fetchTimeline,
    fetchRegions,
    fetchCategories,
    refresh,
    clearError,
  } = useGeopoliticalHotspots();

  const [activeTab, setActiveTab] = useState<GeopoliticalTab>('overview');
  const [selectedHotspot, setSelectedHotspot] = useState<Hotspot | null>(null);
  const [articleHotspotFilter, setArticleHotspotFilter] = useState<Hotspot | null>(null);
  const [articleRiskLevelFilter, setArticleRiskLevelFilter] = useState<'critical' | 'high' | 'medium' | 'low' | 'info' | null>(null);

  // Handle hotspot click from any tab - navigate to articles with filter
  const handleHotspotClick = useCallback((hotspot: Hotspot) => {
    setSelectedHotspot(hotspot);
    setArticleHotspotFilter(hotspot);
    setActiveTab('articles');
  }, []);

  // Clear the hotspot filter on articles tab
  const handleHotspotFilterClear = useCallback(() => {
    setArticleHotspotFilter(null);
    setArticleRiskLevelFilter(null);
  }, []);

  // Handle risk level filter from overview tab
  const handleOverviewRiskLevelFilter = useCallback((level: 'critical' | 'high' | 'medium' | 'low' | 'info') => {
    setArticleRiskLevelFilter(level);
    setArticleHotspotFilter(null); // Clear hotspot filter when filtering by risk
    setActiveTab('articles');
  }, []);

  // Handle category filter change
  const handleCategoriesChange = useCallback(
    (categories: typeof config.selectedCategories) => {
      updateConfig({ selectedCategories: categories, page: 1 });
    },
    [updateConfig]
  );

  // Handle risk level filter change
  const handleRiskLevelsChange = useCallback(
    (levels: typeof config.selectedRiskLevels) => {
      updateConfig({ selectedRiskLevels: levels, page: 1 });
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
      {/* Header - z-index ensures tabs stay above Leaflet controls */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 relative z-[1001]">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-pink-100 dark:bg-pink-900/30 rounded-lg">
            <Globe className="w-6 h-6 text-pink-600 dark:text-pink-400" />
          </div>
          <div>
            <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100">
              Geopolitical Hotspots
            </h2>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Global threat monitoring and analysis
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* Tab Navigation */}
          <GeopoliticalHotspotsTabs activeTab={activeTab} onTabChange={setActiveTab} />

          {/* Days Back Selector */}
          <select
            value={config.daysBack}
            onChange={(e) => handleDaysBackChange(Number(e.target.value))}
            className="px-3 py-2 text-sm bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-pink-500 dark:text-gray-100"
          >
            <option value={7}>Last 7 days</option>
            <option value={30}>Last 30 days</option>
            <option value={90}>Last 90 days</option>
            <option value={180}>Last 6 months</option>
            <option value={365}>Last year</option>
          </select>

          {/* Update Button */}
          <button
            onClick={() => setShowImportModal(true)}
            className="p-2 bg-pink-500 text-white rounded-lg hover:bg-pink-600 transition-colors"
            title="Update hotspots"
          >
            <Download className="w-4 h-4" />
          </button>

          {/* Refresh Button */}
          <button
            onClick={refresh}
            disabled={loading}
            className="p-2 bg-pink-50 dark:bg-pink-900/20 text-pink-700 dark:text-pink-300 rounded-lg hover:bg-pink-100 dark:hover:bg-pink-900/30 disabled:opacity-50 transition-colors"
            title="Refresh data"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
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
        <GeopoliticalOverviewTab
          stats={stats}
          hotspots={mapHotspots}
          loading={loadingStats || loadingMap}
          onHotspotClick={handleHotspotClick}
          onRiskLevelFilter={handleOverviewRiskLevelFilter}
          onCategoryFilter={(category) => {
            handleCategoriesChange([category as any]);
            setActiveTab('articles');
          }}
        />
      )}

      {activeTab === 'map' && (
        <GeopoliticalMapTab
          hotspots={mapHotspots}
          loading={loadingMap}
          selectedCategories={config.selectedCategories}
          selectedRiskLevels={config.selectedRiskLevels}
          onCategoriesChange={handleCategoriesChange}
          onRiskLevelsChange={handleRiskLevelsChange}
          onHotspotClick={handleHotspotClick}
        />
      )}

      {activeTab === 'timeline' && (
        <GeopoliticalTimelineTab
          timeline={timeline}
          loading={loadingTimeline}
          onLoad={fetchTimeline}
        />
      )}

      {activeTab === 'regions' && (
        <GeopoliticalRegionsTab
          regions={regions}
          categories={categories}
          loadingRegions={loadingRegions}
          loadingCategories={loadingCategories}
          onLoadRegions={fetchRegions}
          onLoadCategories={fetchCategories}
        />
      )}

      {activeTab === 'themes' && (
        <GeopoliticalThemesTab
          onCategoryFilter={(category) => {
            handleCategoriesChange([category as any]);
            setActiveTab('articles');
          }}
        />
      )}

      {activeTab === 'analysis' && (
        <GeopoliticalAnalysisTab
          onCategoryFilter={(category) => {
            handleCategoriesChange([category as any]);
            setActiveTab('articles');
          }}
        />
      )}

      {activeTab === 'insights' && (
        <GeopoliticalInsightsTab
          stats={stats}
          hotspots={mapHotspots}
          loading={loadingStats}
          model={model}
        />
      )}

      {activeTab === 'articles' && (
        <GeopoliticalArticlesTab
          onArticleClick={(article) => {
            console.log('Article clicked:', article);
          }}
          initialHotspot={articleHotspotFilter}
          onHotspotFilterClear={handleHotspotFilterClear}
          initialRiskLevel={articleRiskLevelFilter}
        />
      )}

      {/* Import Modal */}
      <GeopoliticalImportModal
        isOpen={showImportModal}
        onClose={() => setShowImportModal(false)}
        onImportComplete={refresh}
        model={model}
      />
    </div>
  );
}
