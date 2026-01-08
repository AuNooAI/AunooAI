/**
 * News Feed Page - Google News style layout
 * Main page for exploring news articles with AI-powered insights
 * Section order: Highlights → Narratives → Your Topics
 */

import { useState, useEffect, useCallback } from 'react';
import {
  Loader2,
  AlertCircle,
  Newspaper,
  Plus,
  Settings2,
  GripVertical,
  Bot,
  Rss,
  FileText,
  Check,
} from 'lucide-react';
import { useNewsFeed } from '../hooks/useNewsFeed';
import { useNarrativeExplorer } from '../hooks/useNarrativeExplorer';
import { useResearchAgents } from '../hooks/useResearchAgents';
import { SharedNavigation } from '../components/SharedNavigation';
import { NewsFeedHeader } from '../components/newsfeed/NewsFeedHeader';
import { BriefingSection } from '../components/newsfeed/BriefingSection';
import { HighlightsSection } from '../components/newsfeed/HighlightsSection';
import { NarrativeInsightsSection } from '../components/newsfeed/NarrativeInsightsSection';
import { ResearchAgentsSection } from '../components/newsfeed/ResearchAgentsSection';
import { SignalReportsTab } from '../components/newsfeed/SignalReportsTab';
import { TopicCluster, getCategoryIcon } from '../components/newsfeed/TopicCluster';
import { OnboardingWizard } from '../components/onboarding/OnboardingWizard';
import { AuspexChat } from '../components/auspex';
import { ArticleDetailPanel } from '../components/newsfeed/ArticleDetailPanel';
import { CategoryViewModal } from '../components/newsfeed/CategoryViewModal';
import { IncidentConfigModal } from '../components/newsfeed/IncidentConfigModal';
import { SixArticlesTuneModal } from '../components/SixArticlesTuneModal';
import { type NewsArticle, type ArticleCluster, type ClusterRelatedArticle, getArticleByUri, getClusteredArticles, clusterArticleToNewsArticle } from '../services/newsFeedApi';
import { applyFilters, createEmptyFilters, type IncidentFilters } from '../components/newsfeed/FilterPanel';
import { getSignalReportsCount } from '../services/researchAgentsApi';
import { NotificationBell } from '../components/gather/NotificationBell';
import { Alert, AlertDescription, AlertTitle } from '../components/ui/alert';
import { Button } from '../components/ui/button';
import '../components/gather/gather.css';

// Section visibility settings
interface VisibleSections {
  briefing: boolean;
  incidents: boolean;
  narratives: boolean;
  topics: boolean;
}

const VISIBLE_SECTIONS_KEY = 'explore_visibleSections';
const DEFAULT_VISIBLE_SECTIONS: VisibleSections = {
  briefing: true,
  incidents: true,
  narratives: true,
  topics: true,
};

export function NewsFeedPage() {
  console.log('[NewsFeedPage] Component rendering');

  // Articles hook
  const {
    articles,
    groupedArticles,
    sixArticles,
    sixArticlesConfig,
    categories,
    topics: newsFeedTopics,
    profiles: newsFeedProfiles,
    models: newsFeedModels,
    config,
    totalArticles,
    loading,
    loadingSixArticles,
    error,
    updateConfig,
    fetchArticles,
    fetchSixArticles,
    starArticle,
    unstarArticle,
    clearError,
    starredArticles,
  } = useNewsFeed();

  // Narrative Explorer hook (Highlights & Narratives)
  const {
    incidents,
    themes,
    topics: narrativeTopics,
    profiles: narrativeProfiles,
    models: narrativeModels,
    config: narrativeConfig,
    incidentResponse,
    loadingHighlights,
    loadingNarratives,
    loadingInitial: loadingNarrativeInitial,
    highlightsError,
    narrativesError,
    updateConfig: updateNarrativeConfig,
    generateHighlights,
    generateNarratives,
    generateAll,
    clearErrors: clearNarrativeErrors,
  } = useNarrativeExplorer();

  // Research Agents hook
  const {
    agents: researchAgents,
    alerts: researchAlerts,
    podcastSummaries,
    unacknowledgedCount: researchAlertsCount,
    loading: loadingResearchAgents,
    loadingAgents,
    loadingAlerts,
    runningAgents,
    error: researchAgentsError,
    addAgent,
    updateAgent,
    removeAgent,
    runAgent,
    runAllAgents,
    acknowledgeOne,
    acknowledgeAll,
    clearError: clearResearchAgentsError,
  } = useResearchAgents(config.topic);

  // State for managing displayed podcast summaries (allows dismissing)
  const [dismissedPodcasts, setDismissedPodcasts] = useState<Set<number>>(new Set());
  const visiblePodcasts = podcastSummaries.filter((_, i) => !dismissedPodcasts.has(i));
  const handleDismissPodcast = (index: number) => {
    setDismissedPodcasts(prev => new Set(prev).add(index));
  };

  // UI State
  const [currentTab, setCurrentTab] = useState<'feed' | 'agents' | 'reports'>('feed');
  const [reportsCount, setReportsCount] = useState(0);
  const [isConfigOpen, setIsConfigOpen] = useState(false);
  const [isBriefingConfigOpen, setIsBriefingConfigOpen] = useState(false);
  const [isOnboardingOpen, setIsOnboardingOpen] = useState(false);
  const [filters] = useState<IncidentFilters>(createEmptyFilters());
  const [hiddenCategories, setHiddenCategories] = useState<Set<string>>(new Set());
  const [categoryOrder, setCategoryOrder] = useState<string[]>([]);
  const [selectedArticle, setSelectedArticle] = useState<NewsArticle | null>(null);
  const [selectedArticleRelated, setSelectedArticleRelated] = useState<ClusterRelatedArticle[]>([]);
  const [selectedCategory, setSelectedCategory] = useState<{ name: string; topic?: string } | null>(null);
  const [loadingArticleDetail, setLoadingArticleDetail] = useState(false);

  // Section visibility state with localStorage persistence
  const [visibleSections, setVisibleSections] = useState<VisibleSections>(() => {
    try {
      const saved = localStorage.getItem(VISIBLE_SECTIONS_KEY);
      if (saved) {
        return { ...DEFAULT_VISIBLE_SECTIONS, ...JSON.parse(saved) };
      }
    } catch (e) {
      console.warn('Failed to load visible sections from localStorage:', e);
    }
    return DEFAULT_VISIBLE_SECTIONS;
  });

  // Persist visible sections to localStorage
  useEffect(() => {
    try {
      localStorage.setItem(VISIBLE_SECTIONS_KEY, JSON.stringify(visibleSections));
    } catch (e) {
      console.warn('Failed to save visible sections to localStorage:', e);
    }
  }, [visibleSections]);

  // Toggle section visibility
  const toggleSection = useCallback((section: keyof VisibleSections) => {
    setVisibleSections(prev => ({ ...prev, [section]: !prev[section] }));
  }, []);

  // Clustering state - clusters grouped by category
  const [categoryClusters, setCategoryClusters] = useState<Record<string, ArticleCluster[]>>({});
  const [loadingClusters, setLoadingClusters] = useState(false);

  // Handler to fetch full article data and open detail panel
  // Used by Narratives and Highlights which may have partial article data
  // Accepts optional related articles from clusters
  const handleArticleClick = useCallback(async (
    article: NewsArticle | { uri: string; title?: string },
    relatedArticles?: ClusterRelatedArticle[]
  ) => {
    // Set related articles if provided
    console.log(`[NewsFeedPage] handleArticleClick - related articles:`, relatedArticles?.length || 0, relatedArticles);
    setSelectedArticleRelated(relatedArticles || []);

    // If it's already a full NewsArticle with summary, use it directly
    if ('summary' in article && article.summary && article.summary !== '') {
      setSelectedArticle(article as NewsArticle);
      return;
    }

    // Otherwise, fetch full article data by URI
    setLoadingArticleDetail(true);
    try {
      const fullArticle = await getArticleByUri(article.uri);
      if (fullArticle) {
        setSelectedArticle(fullArticle);
      } else {
        // Fallback to partial data if fetch fails
        setSelectedArticle({
          uri: article.uri,
          title: article.title || 'Unknown Title',
          summary: '',
          source: { name: 'Unknown Source' },
          tags: [],
        });
      }
    } catch (err) {
      console.error('Failed to fetch article details:', err);
      // Fallback to partial data
      setSelectedArticle({
        uri: article.uri,
        title: article.title || 'Unknown Title',
        summary: '',
        source: { name: 'Unknown Source' },
        tags: [],
      });
    } finally {
      setLoadingArticleDetail(false);
    }
  }, []);

  // Use narrative explorer data for topics/profiles/models (they have the same data)
  const topics = narrativeTopics.length > 0 ? narrativeTopics : newsFeedTopics;
  const profiles = narrativeProfiles.length > 0 ? narrativeProfiles : newsFeedProfiles;
  const models = narrativeModels.length > 0 ? narrativeModels : newsFeedModels;

  // Combined loading state for analyses
  const isGeneratingAnalyses = loadingHighlights || loadingNarratives;

  // Filter and sort incidents
  const filteredIncidents = applyFilters(incidents, filters);

  // Sync topic selection from newsFeed config to narrative config
  useEffect(() => {
    if (config.topic && !narrativeConfig.selectedTopics.includes(config.topic)) {
      updateNarrativeConfig({ selectedTopics: [config.topic] });
    }
  }, [config.topic]);

  // Sync model and profileId from settings modal to narrative config
  useEffect(() => {
    if (config.model !== narrativeConfig.model || config.profileId !== narrativeConfig.profileId) {
      updateNarrativeConfig({
        model: config.model,
        profileId: config.profileId,
      });
    }
  }, [config.model, config.profileId]);

  // Load hidden categories and category order from localStorage
  useEffect(() => {
    try {
      const savedHidden = localStorage.getItem('hiddenCategories');
      if (savedHidden) {
        setHiddenCategories(new Set(JSON.parse(savedHidden)));
      }
      const savedOrder = localStorage.getItem('categoryOrder');
      if (savedOrder) {
        setCategoryOrder(JSON.parse(savedOrder));
      }
    } catch (e) {
      console.error('Failed to load category settings:', e);
    }
  }, []);

  // Fetch signal reports count
  useEffect(() => {
    const fetchReportsCount = async () => {
      try {
        const response = await getSignalReportsCount({ topic: config.topic || undefined });
        setReportsCount(response.count || 0);
      } catch (err) {
        console.error('Failed to fetch reports count:', err);
      }
    };
    fetchReportsCount();
  }, [config.topic]);

  // Fetch clusters when categories change
  useEffect(() => {
    const fetchClustersForCategories = async () => {
      if (categories.length === 0) return;

      setLoadingClusters(true);
      try {
        // Fetch clusters for each category in parallel (limit to top 9 for 3x3 grid)
        const categoriesToFetch = categories.slice(0, 9);
        const clusterPromises = categoriesToFetch.map(async (category) => {
          try {
            const result = await getClusteredArticles({
              category,
              topic: config.topic,
              dateRange: config.dateRange,
              maxArticles: 100,  // Increased to get more articles for clustering
              similarityThreshold: 0.2,  // Stricter - only very similar articles (same story)
              maxClusterSize: 5,
            });
            return { category, clusters: result.clusters };
          } catch (err) {
            console.warn(`Failed to fetch clusters for ${category}:`, err);
            return { category, clusters: [] };
          }
        });

        const results = await Promise.all(clusterPromises);
        const clustersByCategory: Record<string, ArticleCluster[]> = {};
        results.forEach(({ category, clusters }) => {
          clustersByCategory[category] = clusters;
        });
        setCategoryClusters(clustersByCategory);
      } catch (err) {
        console.error('Failed to fetch clusters:', err);
      } finally {
        setLoadingClusters(false);
      }
    };

    fetchClustersForCategories();
  }, [categories, config.topic, config.dateRange]);

  // Save hidden categories to localStorage
  const toggleCategoryVisibility = (category: string) => {
    setHiddenCategories((prev) => {
      const next = new Set(prev);
      if (next.has(category)) {
        next.delete(category);
      } else {
        next.add(category);
      }
      try {
        localStorage.setItem('hiddenCategories', JSON.stringify([...next]));
      } catch (e) {
        console.error('Failed to save hidden categories:', e);
      }
      return next;
    });
  };

  // Update category order and save to localStorage
  const updateCategoryOrder = (newOrder: string[]) => {
    setCategoryOrder(newOrder);
    try {
      localStorage.setItem('categoryOrder', JSON.stringify(newOrder));
    } catch (e) {
      console.error('Failed to save category order:', e);
    }
  };

  // Refresh handler - fetches articles AND generates analyses for VISIBLE sections only
  const handleRefresh = useCallback(async () => {
    // Fetch articles first (always needed for Latest News section)
    await fetchArticles();

    // Only generate for visible sections - saves API calls and time
    if (narrativeConfig.selectedTopics.length > 0) {
      const promises: Promise<void>[] = [];

      if (visibleSections.incidents) {
        promises.push(generateHighlights(true));
      }
      if (visibleSections.narratives) {
        promises.push(generateNarratives(true));
      }

      if (promises.length > 0) {
        await Promise.all(promises);
      }
    }

    // Fetch briefing only if visible
    if (visibleSections.briefing) {
      await fetchSixArticles(true);
    }
  }, [fetchArticles, fetchSixArticles, generateHighlights, generateNarratives, narrativeConfig.selectedTopics, visibleSections]);

  // Force regenerate - respects visibility
  const handleForceRegenerate = useCallback(async () => {
    if (narrativeConfig.selectedTopics.length > 0) {
      const promises: Promise<void>[] = [];

      if (visibleSections.incidents) {
        promises.push(generateHighlights(true));
      }
      if (visibleSections.narratives) {
        promises.push(generateNarratives(true));
      }

      if (promises.length > 0) {
        await Promise.all(promises);
      }
    }
  }, [generateHighlights, generateNarratives, narrativeConfig.selectedTopics, visibleSections]);

  // Handle incident update (refresh after status change/delete)
  const handleIncidentUpdate = useCallback(() => {
    // Re-fetch incidents only if section is visible
    if (narrativeConfig.selectedTopics.length > 0 && visibleSections.incidents) {
      generateHighlights(false);
    }
  }, [generateHighlights, narrativeConfig.selectedTopics, visibleSections.incidents]);

  // Helper to get all articles from clusters for a category
  // This ensures the CategoryViewModal shows the same articles as TopicCluster
  const getCategoryArticlesFromClusters = useCallback((categoryName: string): NewsArticle[] => {
    const clusters = categoryClusters[categoryName];

    // If we have clusters, extract all articles from them
    if (clusters && clusters.length > 0) {
      const allArticles: NewsArticle[] = [];

      for (const cluster of clusters) {
        // Add primary article
        allArticles.push(clusterArticleToNewsArticle(cluster.primary));

        // Add related articles
        for (const related of cluster.related) {
          allArticles.push({
            uri: related.uri,
            title: related.title,
            summary: related.summary || '',
            publication_date: related.publication_date,
            source: {
              name: related.news_source,
              bias: related.bias as any,
              factuality: related.factual_reporting as any,
            },
            tags: [],
          });
        }
      }

      return allArticles;
    }

    // Fallback to groupedArticles if no clusters
    return groupedArticles[categoryName] || [];
  }, [categoryClusters, groupedArticles]);

  // Sort categories: use custom order if set, otherwise by article count
  const sortedCategories = [...categories]
    .filter((cat) => !hiddenCategories.has(cat))
    .sort((a, b) => {
      // If we have a custom order, use it
      if (categoryOrder.length > 0) {
        const indexA = categoryOrder.indexOf(a);
        const indexB = categoryOrder.indexOf(b);
        // Categories in the order list come first, in that order
        // New categories not in the list go to the end, sorted by article count
        if (indexA !== -1 && indexB !== -1) return indexA - indexB;
        if (indexA !== -1) return -1;
        if (indexB !== -1) return 1;
      }
      // Default: sort by article count (descending)
      const countA = groupedArticles[a]?.length || 0;
      const countB = groupedArticles[b]?.length || 0;
      return countB - countA;
    });

  return (
    <div className="gather-app">
      <div className="gather-layout">
        {/* Shared Navigation Sidebar */}
        <SharedNavigation currentPage="investigate" />

      {/* Main Content */}
      <div className="gather-content-area">
        {/* Top Header Bar - matching Gather page style */}
        <div className="gather-top-bar">
          <div className="gather-top-bar-left">
            <span className="gather-top-bar-title">Explore</span>
            <span className="gather-top-bar-separator">/</span>
            <span className="gather-top-bar-subtitle">
              {currentTab === 'agents' ? 'Research Agents' : currentTab === 'reports' ? 'Reports' : 'News Feed'}
            </span>
          </div>
          <div className="gather-top-bar-right">
            {currentTab === 'feed' && (
              <SectionSettingsDropdown
                visibleSections={visibleSections}
                onToggleSection={toggleSection}
                categories={sortedCategories}
                allCategories={categories}
                hiddenCategories={hiddenCategories}
                onToggleCategory={toggleCategoryVisibility}
                onReorderCategories={updateCategoryOrder}
              />
            )}
            <NotificationBell />
            <button
              onClick={() => setIsOnboardingOpen(true)}
              className="gather-top-bar-setup-btn"
            >
              Set up topic
              <Plus className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Filters Header - visible on all tabs for consistent UI */}
        <NewsFeedHeader
          config={config}
          narrativeConfig={narrativeConfig}
          topics={topics}
          profiles={profiles}
          models={models}
          loading={loading || isGeneratingAnalyses}
          onConfigChange={updateConfig}
          onNarrativeConfigChange={updateNarrativeConfig}
          onRefresh={handleRefresh}
          onOpenConfig={currentTab === 'feed' ? () => setIsConfigOpen(true) : undefined}
        />

        {/* Tab Navigation */}
        <div className="explore-tab-navigation">
          <button
            className={`explore-tab-btn ${currentTab === 'feed' ? 'active' : ''}`}
            onClick={() => setCurrentTab('feed')}
          >
            <Rss className="w-4 h-4" />
            News Feed
          </button>
          <button
            className={`explore-tab-btn ${currentTab === 'agents' ? 'active' : ''}`}
            onClick={() => setCurrentTab('agents')}
          >
            <Bot className="w-4 h-4" />
            Research Agents
            {researchAlertsCount > 0 && (
              <span className="explore-tab-badge">{researchAlertsCount}</span>
            )}
          </button>
          <button
            className={`explore-tab-btn ${currentTab === 'reports' ? 'active' : ''}`}
            onClick={() => setCurrentTab('reports')}
          >
            <FileText className="w-4 h-4" />
            Reports
            {reportsCount > 0 && (
              <span className="explore-tab-badge">{reportsCount}</span>
            )}
          </button>
        </div>

        {/* Error Alerts */}
        {(error || highlightsError || narrativesError) && (
          <div className="px-6 py-2 space-y-2">
            {error && (
              <Alert variant="destructive">
                <AlertCircle className="h-4 w-4" />
                <AlertTitle>Error</AlertTitle>
                <AlertDescription className="flex items-center justify-between">
                  <span>{error}</span>
                  <button onClick={clearError} className="text-sm underline hover:no-underline">
                    Dismiss
                  </button>
                </AlertDescription>
              </Alert>
            )}
            {highlightsError && (
              <Alert variant="destructive">
                <AlertCircle className="h-4 w-4" />
                <AlertTitle>Incidents Error</AlertTitle>
                <AlertDescription className="flex items-center justify-between">
                  <span>{highlightsError}</span>
                  <button onClick={clearNarrativeErrors} className="text-sm underline hover:no-underline">
                    Dismiss
                  </button>
                </AlertDescription>
              </Alert>
            )}
            {narrativesError && (
              <Alert variant="destructive">
                <AlertCircle className="h-4 w-4" />
                <AlertTitle>Narratives Error</AlertTitle>
                <AlertDescription className="flex items-center justify-between">
                  <span>{narrativesError}</span>
                  <button onClick={clearNarrativeErrors} className="text-sm underline hover:no-underline">
                    Dismiss
                  </button>
                </AlertDescription>
              </Alert>
            )}
          </div>
        )}

        {/* Main Content Area */}
        <main className="gather-main">
          <div className="max-w-7xl mx-auto">
            {/* Feed Tab Content */}
            {currentTab === 'feed' && (
              <>
                {/* Loading State */}
                {loading && articles.length === 0 ? (
                  <div className="flex items-center justify-center h-64">
                    <div className="flex flex-col items-center gap-4">
                      <Loader2 className="w-8 h-8 animate-spin text-pink-500" />
                      <p className="text-gray-500 dark:text-gray-400">Loading articles...</p>
                    </div>
                  </div>
                ) : (
                  <>
                    {/* Section 1: Your Briefing - Top Stories (executive summary at top) */}
                    {visibleSections.briefing && (
                      <BriefingSection
                        articles={articles}
                        sixArticles={sixArticles}
                        loadingSixArticles={loadingSixArticles}
                        starredArticles={starredArticles}
                        onStar={starArticle}
                        onUnstar={unstarArticle}
                        onArticleClick={handleArticleClick}
                        persona={config.persona}
                        onPersonaChange={(persona, forceRegenerate) => {
                          updateConfig({ persona });
                          if (forceRegenerate) {
                            // Small delay to ensure config is updated first
                            setTimeout(() => fetchSixArticles(true), 100);
                          }
                        }}
                        sixArticlesConfig={sixArticlesConfig}
                        onOpenConfig={() => setIsBriefingConfigOpen(true)}
                      />
                    )}

                    {/* Section 2: Highlights - Incident Tracking */}
                    {visibleSections.incidents && (
                      <HighlightsSection
                        incidents={filteredIncidents}
                        loading={loadingHighlights}
                        onIncidentUpdate={handleIncidentUpdate}
                        onArticleClick={handleArticleClick}
                      />
                    )}

                    {/* Section 3: Narratives - Article Themes */}
                    {visibleSections.narratives && (
                      <NarrativeInsightsSection
                        themes={themes}
                        loading={loadingNarratives}
                        onArticleClick={handleArticleClick}
                        currentTopic={config.topic}
                      />
                    )}

                    {/* Section 4: Your Topics - Google News style multi-column grid */}
                {visibleSections.topics && sortedCategories.length > 0 && (
                  <div className="mt-8">
                    <div className="flex items-center justify-between mb-6">
                      <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100">Latest News</h2>
                    </div>

                    {/* Multi-column grid layout like Google News */}
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-x-8 gap-y-2">
                      {sortedCategories.slice(0, 9).map((category) => {
                        const categoryArticles = groupedArticles[category] || [];
                        const categoryTopic = categoryArticles[0]?.topic;
                        const clusters = categoryClusters[category];
                        return (
                          <TopicCluster
                            key={category}
                            category={category}
                            topic={categoryTopic}
                            articles={categoryArticles}
                            clusters={clusters}
                            starredArticles={starredArticles}
                            onStar={starArticle}
                            onUnstar={unstarArticle}
                            onArticleClick={handleArticleClick}
                            onSeeMore={(cat, topic) => setSelectedCategory({ name: cat, topic })}
                            maxItems={4}
                          />
                        );
                      })}
                    </div>

                    {/* Show remaining categories as clickable chips */}
                    {sortedCategories.length > 9 && (
                      <div className="mt-6 pt-4 border-t border-gray-200 dark:border-gray-700">
                        <h3 className="text-sm font-medium text-gray-600 dark:text-gray-400 mb-3">More topics</h3>
                        <div className="flex flex-wrap gap-2">
                          {sortedCategories.slice(9).map((category) => {
                            const catArticles = groupedArticles[category] || [];
                            const catTopic = catArticles[0]?.topic;
                            return (
                              <button
                                key={category}
                                onClick={() => setSelectedCategory({ name: category, topic: catTopic })}
                                className="px-3 py-1.5 text-sm bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-full text-gray-700 dark:text-gray-300 transition-colors"
                              >
                                {category}
                                <span className="ml-1 text-gray-500 dark:text-gray-400">({catArticles.length})</span>
                              </button>
                            );
                          })}
                        </div>
                      </div>
                    )}
                  </div>
                )}

                    {/* Empty State */}
                    {articles.length === 0 && !loading && (
                      <div className="flex flex-col items-center justify-center h-64 text-center">
                        <Newspaper className="w-12 h-12 text-gray-300 dark:text-gray-600 mb-4" />
                        <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100">No articles found</h3>
                        <p className="text-gray-500 dark:text-gray-400 mt-1">
                          Try adjusting your date range or topic filters
                        </p>
                      </div>
                    )}
                  </>
                )}
              </>
            )}

            {/* Research Agents Tab Content */}
            {currentTab === 'agents' && (
              <ResearchAgentsSection
                agents={researchAgents}
                alerts={researchAlerts}
                podcastSummaries={visiblePodcasts}
                unacknowledgedCount={researchAlertsCount}
                loading={loadingResearchAgents}
                loadingAgents={loadingAgents}
                loadingAlerts={loadingAlerts}
                runningAgents={runningAgents}
                error={researchAgentsError}
                onAddAgent={addAgent}
                onUpdateAgent={updateAgent}
                onDeleteAgent={removeAgent}
                onRunAgent={(agentId, options) => runAgent(agentId, { topic: config.topic, daysBack: options?.daysBack, tagArticles: options?.tagArticles })}
                onRunAllAgents={(options) => runAllAgents({ topic: config.topic, daysBack: options?.daysBack, tagArticles: options?.tagArticles })}
                onAcknowledgeAlert={acknowledgeOne}
                onAcknowledgeAll={acknowledgeAll}
                onDismissPodcast={handleDismissPodcast}
                topics={topics.map(t => t.name)}
              />
            )}

            {/* Signal Reports Tab Content */}
            {currentTab === 'reports' && (
              <SignalReportsTab topic={config.topic || undefined} />
            )}
          </div>
        </main>
      </div>

      {/* Incident Config Modal */}
      <IncidentConfigModal
        open={isConfigOpen}
        onClose={() => setIsConfigOpen(false)}
      />

      {/* Six Articles / Briefing Config Modal */}
      <SixArticlesTuneModal
        open={isBriefingConfigOpen}
        onOpenChange={setIsBriefingConfigOpen}
        onConfigSaved={() => {
          // Refresh six articles after config is saved
          fetchSixArticles(true);
        }}
      />

      {/* Article Detail Slide-in Panel */}
      <ArticleDetailPanel
        article={selectedArticle}
        relatedArticles={selectedArticleRelated}
        isStarred={selectedArticle ? starredArticles.includes(selectedArticle.uri) : false}
        onClose={() => {
          setSelectedArticle(null);
          setSelectedArticleRelated([]);
        }}
        onStar={starArticle}
        onUnstar={unstarArticle}
        onRelatedArticleClick={(uri) => {
          // Fetch and display the related article
          handleArticleClick({ uri });
        }}
      />

      {/* Category View Modal */}
      {selectedCategory && (
        <CategoryViewModal
          category={selectedCategory.name}
          topic={selectedCategory.topic}
          articles={getCategoryArticlesFromClusters(selectedCategory.name)}
          starredArticles={starredArticles}
          onStar={starArticle}
          onUnstar={unstarArticle}
          onArticleClick={handleArticleClick}
          onClose={() => setSelectedCategory(null)}
        />
      )}

      {/* Onboarding Wizard Modal */}
      <OnboardingWizard
        open={isOnboardingOpen}
        onOpenChange={setIsOnboardingOpen}
      />
      <AuspexChat />
      </div>
    </div>
  );
}

// Section Settings Dropdown - combined control for sections and categories
interface SectionSettingsDropdownProps {
  visibleSections: VisibleSections;
  onToggleSection: (section: keyof VisibleSections) => void;
  categories: string[];
  allCategories: string[];
  hiddenCategories: Set<string>;
  onToggleCategory: (category: string) => void;
  onReorderCategories: (newOrder: string[]) => void;
}

function SectionSettingsDropdown({
  visibleSections,
  onToggleSection,
  categories,
  allCategories,
  hiddenCategories,
  onToggleCategory,
  onReorderCategories,
}: SectionSettingsDropdownProps) {
  const [showSettings, setShowSettings] = useState(false);
  const [activeTab, setActiveTab] = useState<'sections' | 'categories'>('sections');
  const [draggedIndex, setDraggedIndex] = useState<number | null>(null);
  const [dragOverIndex, setDragOverIndex] = useState<number | null>(null);

  const sections = [
    { id: 'briefing' as keyof VisibleSections, label: 'Your Briefing' },
    { id: 'incidents' as keyof VisibleSections, label: 'Incidents' },
    { id: 'narratives' as keyof VisibleSections, label: 'Narratives' },
    { id: 'topics' as keyof VisibleSections, label: 'Latest News' },
  ];

  // Drag handlers for categories
  const handleDragStart = (e: React.DragEvent, index: number) => {
    setDraggedIndex(index);
    e.dataTransfer.effectAllowed = 'move';
    const target = e.currentTarget as HTMLElement;
    target.style.opacity = '0.5';
  };

  const handleDragEnd = (e: React.DragEvent) => {
    const target = e.currentTarget as HTMLElement;
    target.style.opacity = '1';
    setDraggedIndex(null);
    setDragOverIndex(null);
  };

  const handleDragOver = (e: React.DragEvent, index: number) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    setDragOverIndex(index);
  };

  const handleDrop = (e: React.DragEvent, dropIndex: number) => {
    e.preventDefault();
    if (draggedIndex === null || draggedIndex === dropIndex) return;

    const newOrder = [...allCategories];
    const [draggedItem] = newOrder.splice(draggedIndex, 1);
    newOrder.splice(dropIndex, 0, draggedItem);
    onReorderCategories(newOrder);
    setDraggedIndex(null);
    setDragOverIndex(null);
  };

  return (
    <div className="relative">
      <button
        onClick={() => setShowSettings(!showSettings)}
        className="gather-icon-button"
        title="Manage Sections"
      >
        <Settings2 className="w-5 h-5" />
      </button>

      {showSettings && (
        <>
          {/* Backdrop to close dropdown when clicking outside */}
          <div
            className="fixed inset-0 z-40"
            onClick={() => setShowSettings(false)}
          />

          <div className="absolute right-0 top-full mt-2 w-72 bg-white dark:bg-gray-800 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 z-50">
            {/* Tab buttons */}
            <div className="flex border-b border-gray-200 dark:border-gray-700">
              <button
                className={`flex-1 px-4 py-2 text-sm font-medium ${
                  activeTab === 'sections'
                    ? 'text-pink-600 border-b-2 border-pink-500'
                    : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'
                }`}
                onClick={() => setActiveTab('sections')}
              >
                Sections
              </button>
              <button
                className={`flex-1 px-4 py-2 text-sm font-medium ${
                  activeTab === 'categories'
                    ? 'text-pink-600 border-b-2 border-pink-500'
                    : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'
                }`}
                onClick={() => setActiveTab('categories')}
              >
                Categories
              </button>
            </div>

            {/* Sections tab content */}
            {activeTab === 'sections' && (
              <div className="p-2">
                <p className="text-xs text-gray-500 dark:text-gray-400 px-2 py-1 mb-1">
                  Show or hide page sections
                </p>
                {sections.map((section) => (
                  <button
                    key={section.id}
                    onClick={() => onToggleSection(section.id)}
                    className="w-full flex items-center justify-between px-3 py-2 rounded hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
                  >
                    <span className="text-sm text-gray-700 dark:text-gray-300">{section.label}</span>
                    {visibleSections[section.id] ? (
                      <Check className="w-4 h-4 text-pink-500" />
                    ) : (
                      <div className="w-4 h-4" />
                    )}
                  </button>
                ))}
              </div>
            )}

            {/* Categories tab content */}
            {activeTab === 'categories' && (
              <div className="p-2">
                <p className="text-xs text-gray-500 dark:text-gray-400 px-2 py-1 mb-1">
                  Drag to reorder, click to show/hide
                </p>
                <div className="max-h-64 overflow-y-auto">
                  {allCategories.map((category, index) => (
                    <div
                      key={category}
                      draggable
                      onDragStart={(e) => handleDragStart(e, index)}
                      onDragEnd={handleDragEnd}
                      onDragOver={(e) => handleDragOver(e, index)}
                      onDrop={(e) => handleDrop(e, index)}
                      className={`flex items-center gap-2 px-2 py-2 rounded cursor-grab active:cursor-grabbing transition-colors ${
                        dragOverIndex === index && draggedIndex !== index
                          ? 'bg-pink-50 dark:bg-pink-900/30 border-t-2 border-pink-300'
                          : 'hover:bg-gray-50 dark:hover:bg-gray-700'
                      } ${draggedIndex === index ? 'opacity-50' : ''}`}
                    >
                      <GripVertical className="w-4 h-4 text-gray-400 shrink-0" />
                      <input
                        type="checkbox"
                        checked={!hiddenCategories.has(category)}
                        onChange={() => onToggleCategory(category)}
                        onClick={(e) => e.stopPropagation()}
                        className="rounded border-gray-300 dark:border-gray-600 text-pink-500 focus:ring-pink-500 shrink-0"
                      />
                      <span className="text-sm text-gray-700 dark:text-gray-300 flex-1 truncate">{category}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Done button */}
            <div className="p-2 border-t border-gray-200 dark:border-gray-700">
              <Button
                variant="ghost"
                size="sm"
                className="w-full"
                onClick={() => setShowSettings(false)}
              >
                Done
              </Button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

