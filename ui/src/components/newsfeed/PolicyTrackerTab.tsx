/**
 * Policy Tracker Tab Component
 * Main container for the Policy Tracker dashboard with multi-tab interface
 */

import { useState, useCallback } from 'react';
import { RefreshCw, AlertCircle, X, Loader2, Download, Scale } from 'lucide-react';
import { usePolicyTracker } from '../../hooks/usePolicyTracker';
import { PolicyTrackerTabs, type PolicyTab } from './PolicyTrackerTabs';
import { PolicyOverviewTab } from './PolicyOverviewTab';
import { PolicyTimelineTab } from './PolicyTimelineTab';
import { PolicyThemesTab } from './PolicyThemesTab';
import { PolicyAnalysisTab } from './PolicyAnalysisTab';
import { PolicyInsightsTab } from './PolicyInsightsTab';
import { PolicyCategoryAnalysisTab } from './PolicyCategoryAnalysisTab';
import { PolicyArticleList } from './PolicyArticleList';
import { PolicyTrackerImportModal } from './PolicyTrackerImportModal';
import type { PolicyArticle } from '../../services/policyTrackerApi';

interface PolicyTrackerTabProps {
  onArticleClick?: (article: { uri: string; title?: string }) => void;
}

export function PolicyTrackerTab({ onArticleClick }: PolicyTrackerTabProps) {
  const {
    stats,
    articles,
    categories,
    temporalData,
    relatedArticles,
    searchResults,
    config,
    totalArticles,
    totalPages,
    loading,
    loadingStats,
    loadingArticles,
    loadingCategories,
    loadingTemporal,
    loadingRelated,
    loadingSearch,
    // EDA Analysis Data
    themes,
    themesEvolution,
    entities,
    geography,
    escalationMarkers,
    escalationTrends,
    dayOfWeek,
    dailyIntensity,
    cooccurrenceMatrix,
    loadingThemes,
    loadingEntities,
    loadingGeography,
    loadingEscalation,
    loadingTimeline,
    loadingMatrix,
    error,
    updateConfig,
    fetchRelatedArticles,
    searchArticles,
    fetchThemesData,
    fetchEntitiesData,
    fetchGeographyData,
    fetchEscalationData,
    fetchTimelineData,
    fetchMatrixData,
    clearSearch,
    clearError,
    refresh,
  } = usePolicyTracker();

  const [activeTab, setActiveTab] = useState<PolicyTab>('overview');
  const [searchQuery, setSearchQuery] = useState('');
  const [showRelatedModal, setShowRelatedModal] = useState(false);
  const [selectedArticleUri, setSelectedArticleUri] = useState<string | null>(null);
  const [showImportModal, setShowImportModal] = useState(false);
  const [refreshTrigger, setRefreshTrigger] = useState(0);

  // Handle article click
  const handleArticleClick = useCallback(
    (article: PolicyArticle) => {
      if (onArticleClick) {
        onArticleClick({ uri: article.uri, title: article.title });
      }
    },
    [onArticleClick]
  );

  // Handle find related articles
  const handleFindRelated = useCallback(
    async (uri: string) => {
      setSelectedArticleUri(uri);
      setShowRelatedModal(true);
      await fetchRelatedArticles(uri);
    },
    [fetchRelatedArticles]
  );

  // Handle search
  const handleSearch = useCallback(
    (query: string) => {
      setSearchQuery(query);
      searchArticles(query);
    },
    [searchArticles]
  );

  // Handle clear search
  const handleClearSearch = useCallback(() => {
    setSearchQuery('');
    clearSearch();
  }, [clearSearch]);

  // Handle category change
  const handleCategoryChange = useCallback(
    (selectedCategories: string[]) => {
      updateConfig({ selectedCategories });
    },
    [updateConfig]
  );

  // Handle sort change
  const handleSortChange = useCallback(
    (sortBy: 'date' | 'relevance' | 'category_count') => {
      updateConfig({ sortBy });
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
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100 flex items-center gap-2">
            <Scale className="w-5 h-5 text-violet-500" />
            Policy Tracker
          </h2>
          <p className="text-sm text-gray-500 dark:text-gray-300 mt-1">
            Analyzing policy categories from "{config.topic}"
          </p>
        </div>

        <div className="flex items-center gap-2">
          {/* Days Back Selector */}
          <select
            value={config.daysBack}
            onChange={(e) => handleDaysBackChange(Number(e.target.value))}
            className="px-3 py-2 text-sm bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg dark:text-gray-100"
          >
            <option value={7}>7 days</option>
            <option value={30}>30 days</option>
            <option value={90}>90 days</option>
            <option value={180}>6 months</option>
            <option value={365}>1 year</option>
            <option value={0}>All Time</option>
          </select>

          {/* Update Button */}
          <button
            onClick={() => setShowImportModal(true)}
            title="Update data"
            className="p-2 text-teal-700 dark:text-teal-300 bg-teal-50 dark:bg-teal-900/20 rounded-lg hover:bg-teal-100"
          >
            <Download className="w-4 h-4" />
          </button>

          {/* Refresh Button */}
          <button
            onClick={() => {
              refresh();
              if (activeTab === 'insights') {
                setRefreshTrigger(prev => prev + 1);
              }
            }}
            disabled={loading}
            title="Refresh"
            className="p-2 text-emerald-700 dark:text-emerald-300 bg-emerald-50 dark:bg-emerald-900/20 rounded-lg hover:bg-emerald-100 disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Sub-tab navigation */}
      <PolicyTrackerTabs activeTab={activeTab} onTabChange={setActiveTab} />

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
        <PolicyOverviewTab
          stats={stats}
          categories={categories}
          temporalData={temporalData}
          escalationData={[]}
          loadingStats={loadingStats}
          loadingCharts={loadingCategories || loadingTemporal}
        />
      )}

      {activeTab === 'timeline' && (
        <PolicyTimelineTab
          dayOfWeek={dayOfWeek}
          dailyIntensity={dailyIntensity}
          temporalData={temporalData}
          loading={loadingTimeline}
          onLoad={fetchTimelineData}
        />
      )}

      {activeTab === 'themes' && (
        <PolicyThemesTab
          themes={themes}
          themesEvolution={themesEvolution}
          entities={entities}
          geography={geography}
          escalationMarkers={escalationMarkers}
          escalationTrends={escalationTrends}
          loadingThemes={loadingThemes}
          loadingEntities={loadingEntities}
          loadingGeography={loadingGeography}
          loadingEscalation={loadingEscalation}
          onLoadThemes={fetchThemesData}
          onLoadEntities={fetchEntitiesData}
          onLoadGeography={fetchGeographyData}
          onLoadEscalation={fetchEscalationData}
        />
      )}

      {activeTab === 'analysis' && (
        <PolicyAnalysisTab
          cooccurrenceMatrix={cooccurrenceMatrix}
          categories={categories}
          loading={loadingMatrix}
          onLoad={fetchMatrixData}
          topic={config.topic}
          daysBack={config.daysBack}
        />
      )}

      {activeTab === 'insights' && (
        <PolicyInsightsTab
          categories={categories}
          topic={config.topic}
          daysBack={config.daysBack}
          refreshTrigger={refreshTrigger}
        />
      )}

      {activeTab === 'categories' && (
        <PolicyCategoryAnalysisTab
          categories={categories}
          topic={config.topic}
          daysBack={config.daysBack}
        />
      )}

      {activeTab === 'articles' && (
        <PolicyArticleList
          articles={articles}
          categories={categories}
          selectedCategories={config.selectedCategories}
          totalCount={totalArticles}
          page={config.page}
          totalPages={totalPages}
          sortBy={config.sortBy}
          loading={loadingArticles}
          searchQuery={searchQuery}
          searchResults={searchResults}
          loadingSearch={loadingSearch}
          onCategoryChange={handleCategoryChange}
          onSortChange={handleSortChange}
          onPageChange={handlePageChange}
          onSearch={handleSearch}
          onClearSearch={handleClearSearch}
          onArticleClick={handleArticleClick}
          onFindRelated={handleFindRelated}
        />
      )}

      {/* Related Articles Modal */}
      {showRelatedModal && (
        <div className="fixed inset-0 z-[1100] flex items-center justify-center">
          {/* Backdrop */}
          <div
            className="absolute inset-0 bg-black/50"
            onClick={() => setShowRelatedModal(false)}
          />

          {/* Modal */}
          <div className="relative bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-2xl max-h-[80vh] overflow-hidden">
            <div className="flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-700">
              <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100">
                Related Articles
              </h3>
              <button
                onClick={() => setShowRelatedModal(false)}
                className="text-gray-500 hover:text-gray-600 dark:hover:text-gray-500"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-4 overflow-y-auto max-h-[60vh]">
              {loadingRelated ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="w-6 h-6 animate-spin text-pink-500" />
                  <span className="ml-2 text-gray-500 dark:text-gray-300">
                    Finding related articles...
                  </span>
                </div>
              ) : relatedArticles.length === 0 ? (
                <p className="text-center py-8 text-gray-500 dark:text-gray-300">
                  No related articles found
                </p>
              ) : (
                <div className="space-y-3">
                  <p className="text-xs text-gray-500 dark:text-gray-300 mb-4">
                    Articles from all topics similar to the selected article
                  </p>
                  {relatedArticles.map((article) => (
                    <div
                      key={article.uri}
                      className="p-3 bg-gray-50 dark:bg-gray-750 rounded-lg cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
                      onClick={() => {
                        setShowRelatedModal(false);
                        if (onArticleClick) {
                          onArticleClick({ uri: article.uri, title: article.title });
                        }
                      }}
                    >
                      <h4 className="text-sm font-medium text-gray-900 dark:text-gray-100 line-clamp-2">
                        {article.title}
                      </h4>
                      <div className="flex items-center gap-3 mt-1 text-xs text-gray-500 dark:text-gray-300">
                        {article.news_source && <span>{article.news_source}</span>}
                        {article.topic && (
                          <span className="px-1.5 py-0.5 bg-gray-200 dark:bg-gray-600 rounded">
                            {article.topic}
                          </span>
                        )}
                        <span className="text-pink-500">
                          {Math.round(article.similarity_score * 100)}% similar
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Import Modal */}
      <PolicyTrackerImportModal
        isOpen={showImportModal}
        onClose={() => setShowImportModal(false)}
        onImportComplete={refresh}
        topic={config.topic}
      />
    </div>
  );
}
