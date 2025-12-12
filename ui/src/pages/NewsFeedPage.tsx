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
  Download,
  SlidersHorizontal,
  Filter,
  Settings,
  LayoutGrid,
  Table,
  GripVertical,
} from 'lucide-react';
import { useNewsFeed } from '../hooks/useNewsFeed';
import { useNarrativeExplorer } from '../hooks/useNarrativeExplorer';
import { SharedNavigation } from '../components/SharedNavigation';
import { NewsFeedHeader } from '../components/newsfeed/NewsFeedHeader';
import { BriefingSection } from '../components/newsfeed/BriefingSection';
import { HighlightsSection } from '../components/newsfeed/HighlightsSection';
import { NarrativeInsightsSection } from '../components/newsfeed/NarrativeInsightsSection';
import { TopicCluster, getCategoryIcon } from '../components/newsfeed/TopicCluster';
import { ArticleDetailPanel } from '../components/newsfeed/ArticleDetailPanel';
import { CategoryViewModal } from '../components/newsfeed/CategoryViewModal';
import { IncidentConfigModal } from '../components/newsfeed/IncidentConfigModal';
import { type NewsArticle, type ArticleCluster, type ClusterRelatedArticle, getArticleByUri, getClusteredArticles, clusterArticleToNewsArticle } from '../services/newsFeedApi';
import { FilterPanel, createEmptyFilters, applyFilters, type IncidentFilters, type SortOption } from '../components/newsfeed/FilterPanel';
import { NotificationBell } from '../components/gather/NotificationBell';
import { Alert, AlertDescription, AlertTitle } from '../components/ui/alert';
import { Button } from '../components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '../components/ui/dropdown-menu';
import '../components/gather/gather.css';

export function NewsFeedPage() {
  // Articles hook
  const {
    articles,
    groupedArticles,
    sixArticles,
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

  // UI State
  const [isConfigOpen, setIsConfigOpen] = useState(false);
  const [isFilterOpen, setIsFilterOpen] = useState(false);
  const [filters, setFilters] = useState<IncidentFilters>(createEmptyFilters());
  const [sortBy, setSortBy] = useState<SortOption>('date_desc');
  const [viewMode, setViewMode] = useState<'cards' | 'table'>('cards');
  const [hiddenCategories, setHiddenCategories] = useState<Set<string>>(new Set());
  const [categoryOrder, setCategoryOrder] = useState<string[]>([]);
  const [isCategorySettingsOpen, setIsCategorySettingsOpen] = useState(false);
  const [selectedArticle, setSelectedArticle] = useState<NewsArticle | null>(null);
  const [selectedArticleRelated, setSelectedArticleRelated] = useState<ClusterRelatedArticle[]>([]);
  const [selectedCategory, setSelectedCategory] = useState<{ name: string; topic?: string } | null>(null);
  const [loadingArticleDetail, setLoadingArticleDetail] = useState(false);

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

  // Refresh handler - fetches articles AND generates all analyses
  const handleRefresh = useCallback(async () => {
    // Fetch articles first
    await fetchArticles();
    // Then generate all analyses (Highlights + Narratives)
    if (narrativeConfig.selectedTopics.length > 0) {
      await generateAll(false);
    }
  }, [fetchArticles, generateAll, narrativeConfig.selectedTopics]);

  // Force regenerate
  const handleForceRegenerate = useCallback(async () => {
    if (narrativeConfig.selectedTopics.length > 0) {
      await generateAll(true);
    }
  }, [generateAll, narrativeConfig.selectedTopics]);

  // Handle incident update (refresh after status change/delete)
  const handleIncidentUpdate = useCallback(() => {
    // Re-fetch incidents after status update
    if (narrativeConfig.selectedTopics.length > 0) {
      generateAll(false);
    }
  }, [generateAll, narrativeConfig.selectedTopics]);

  // Clear filters
  const handleClearFilters = () => {
    setFilters(createEmptyFilters());
  };

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

  // Export functions
  const exportMarkdown = () => {
    // TODO: Implement markdown export
    alert('Markdown export coming soon');
  };

  const exportPDF = () => {
    // TODO: Implement PDF export
    alert('PDF export coming soon');
  };

  const exportCSV = () => {
    // TODO: Implement CSV export
    alert('CSV export coming soon');
  };

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
            <span className="gather-top-bar-subtitle">News Feed</span>
          </div>
          <div className="gather-top-bar-right">
            <NotificationBell />
            <a
              href="/trend-convergence?onboarding=true"
              className="gather-top-bar-setup-btn"
            >
              Set up topic
              <Plus className="w-4 h-4" />
            </a>
          </div>
        </div>

        {/* Filters Header */}
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
        />

        {/* Narrative Explorer Toolbar */}
        <div className="bg-white border-b border-gray-200 px-6 py-2 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-gray-500">View Options</span>
            <div className="flex border border-gray-200 rounded-md">
              <button
                onClick={() => setViewMode('cards')}
                className={`px-3 py-1.5 text-sm flex items-center gap-1 ${
                  viewMode === 'cards'
                    ? 'bg-pink-50 text-pink-600'
                    : 'text-gray-600 hover:bg-gray-50'
                }`}
                title="Card view"
              >
                <LayoutGrid className="w-4 h-4" />
              </button>
              <button
                onClick={() => setViewMode('table')}
                className={`px-3 py-1.5 text-sm flex items-center gap-1 border-l border-gray-200 ${
                  viewMode === 'table'
                    ? 'bg-pink-50 text-pink-600'
                    : 'text-gray-600 hover:bg-gray-50'
                }`}
                title="Table view"
              >
                <Table className="w-4 h-4" />
              </button>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {/* Export Dropdown */}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline" size="sm" className="gap-2">
                  <Download className="w-4 h-4" />
                  Export
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onClick={exportMarkdown}>
                  Export Markdown
                </DropdownMenuItem>
                <DropdownMenuItem onClick={exportPDF}>
                  Export PDF
                </DropdownMenuItem>
                <DropdownMenuItem onClick={exportCSV}>
                  Export CSV
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>

            {/* Config Button */}
            <Button
              variant="outline"
              size="sm"
              onClick={() => setIsConfigOpen(true)}
              className="gap-2"
              title="Configure Incident Tracking"
            >
              <SlidersHorizontal className="w-4 h-4" />
              Config
            </Button>

            {/* Filter Button */}
            <div className="relative">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setIsFilterOpen(!isFilterOpen)}
                className={`gap-2 ${isFilterOpen ? 'bg-pink-50 text-pink-600 border-pink-300' : ''}`}
              >
                <Filter className="w-4 h-4" />
                Filter
              </Button>
              <FilterPanel
                open={isFilterOpen}
                onClose={() => setIsFilterOpen(false)}
                filters={filters}
                sortBy={sortBy}
                onFiltersChange={setFilters}
                onSortChange={setSortBy}
                onClearFilters={handleClearFilters}
              />
            </div>
          </div>
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
            {/* Loading State */}
            {loading && articles.length === 0 ? (
              <div className="flex items-center justify-center h-64">
                <div className="flex flex-col items-center gap-4">
                  <Loader2 className="w-8 h-8 animate-spin text-pink-500" />
                  <p className="text-gray-500">Loading articles...</p>
                </div>
              </div>
            ) : (
              <>
                {/* Section 1: Your Briefing - Top Stories (executive summary at top) */}
                <BriefingSection
                  articles={articles}
                  sixArticles={sixArticles}
                  loadingSixArticles={loadingSixArticles}
                  starredArticles={starredArticles}
                  onStar={starArticle}
                  onUnstar={unstarArticle}
                  onArticleClick={handleArticleClick}
                />

                {/* Section 2: Highlights - Incident Tracking */}
                <HighlightsSection
                  incidents={filteredIncidents}
                  loading={loadingHighlights}
                  onIncidentUpdate={handleIncidentUpdate}
                  onArticleClick={handleArticleClick}
                />

                {/* Section 3: Narratives - Article Themes */}
                <NarrativeInsightsSection
                  themes={themes}
                  loading={loadingNarratives}
                  onArticleClick={handleArticleClick}
                  currentTopic={config.topic}
                />

                {/* Section 4: Your Topics - Google News style multi-column grid */}
                {sortedCategories.length > 0 && (
                  <div className="mt-8">
                    <div className="flex items-center justify-between mb-6">
                      <div className="flex items-center gap-2">
                        <h2 className="text-xl font-semibold text-gray-900">Your topics</h2>
                      </div>
                      {/* Gear icon for category settings */}
                      <div className="relative">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setIsCategorySettingsOpen(!isCategorySettingsOpen)}
                          className="gap-1"
                        >
                          <Settings className="w-4 h-4" />
                          Manage
                        </Button>
                        {isCategorySettingsOpen && (
                          <CategorySettingsPanel
                            categories={sortedCategories}
                            hiddenCategories={hiddenCategories}
                            onToggle={toggleCategoryVisibility}
                            onReorder={updateCategoryOrder}
                            onClose={() => setIsCategorySettingsOpen(false)}
                          />
                        )}
                      </div>
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
                      <div className="mt-6 pt-4 border-t border-gray-200">
                        <div className="flex flex-wrap gap-2">
                          {sortedCategories.slice(9).map((category) => {
                            const catArticles = groupedArticles[category] || [];
                            const catTopic = catArticles[0]?.topic;
                            return (
                              <button
                                key={category}
                                onClick={() => setSelectedCategory({ name: category, topic: catTopic })}
                                className="px-3 py-1.5 text-sm bg-gray-100 hover:bg-gray-200 rounded-full text-gray-700 transition-colors"
                              >
                                {category}
                                <span className="ml-1 text-gray-400">({catArticles.length})</span>
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
                    <Newspaper className="w-12 h-12 text-gray-300 mb-4" />
                    <h3 className="text-lg font-medium text-gray-900">No articles found</h3>
                    <p className="text-gray-500 mt-1">
                      Try adjusting your date range or topic filters
                    </p>
                  </div>
                )}
              </>
            )}
          </div>
        </main>
      </div>

      {/* Incident Config Modal */}
      <IncidentConfigModal
        open={isConfigOpen}
        onClose={() => setIsConfigOpen(false)}
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
      </div>
    </div>
  );
}

// Category Settings Panel - for showing/hiding and reordering categories
function CategorySettingsPanel({
  categories,
  hiddenCategories,
  onToggle,
  onReorder,
  onClose,
}: {
  categories: string[];
  hiddenCategories: Set<string>;
  onToggle: (category: string) => void;
  onReorder: (newOrder: string[]) => void;
  onClose: () => void;
}) {
  const [draggedIndex, setDraggedIndex] = useState<number | null>(null);
  const [dragOverIndex, setDragOverIndex] = useState<number | null>(null);

  const handleDragStart = (e: React.DragEvent, index: number) => {
    setDraggedIndex(index);
    e.dataTransfer.effectAllowed = 'move';
    // Set drag image opacity
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

    const newOrder = [...categories];
    const [draggedItem] = newOrder.splice(draggedIndex, 1);
    newOrder.splice(dropIndex, 0, draggedItem);
    onReorder(newOrder);
    setDraggedIndex(null);
    setDragOverIndex(null);
  };

  return (
    <div className="absolute right-0 top-full mt-1 w-72 bg-white rounded-lg shadow-lg border border-gray-200 z-50">
      <div className="p-3 border-b border-gray-200">
        <h4 className="font-semibold text-gray-900">Manage Categories</h4>
        <p className="text-xs text-gray-500 mt-1">
          Drag to reorder, click to show/hide
        </p>
      </div>
      <div className="max-h-80 overflow-y-auto p-2">
        {categories.map((category, index) => (
          <div
            key={category}
            draggable
            onDragStart={(e) => handleDragStart(e, index)}
            onDragEnd={handleDragEnd}
            onDragOver={(e) => handleDragOver(e, index)}
            onDrop={(e) => handleDrop(e, index)}
            className={`flex items-center gap-2 px-2 py-2 rounded cursor-grab active:cursor-grabbing transition-colors ${
              dragOverIndex === index && draggedIndex !== index
                ? 'bg-pink-50 border-t-2 border-pink-300'
                : 'hover:bg-gray-50'
            } ${draggedIndex === index ? 'opacity-50' : ''}`}
          >
            <GripVertical className="w-4 h-4 text-gray-400 shrink-0" />
            <input
              type="checkbox"
              checked={!hiddenCategories.has(category)}
              onChange={() => onToggle(category)}
              onClick={(e) => e.stopPropagation()}
              className="rounded border-gray-300 text-pink-500 focus:ring-pink-500 shrink-0"
            />
            <span className="text-sm text-gray-700 flex-1 truncate">{category}</span>
            <span className="text-xs text-gray-400">#{index + 1}</span>
          </div>
        ))}
      </div>
      <div className="p-2 border-t border-gray-200">
        <Button variant="ghost" size="sm" className="w-full" onClick={onClose}>
          Done
        </Button>
      </div>
    </div>
  );
}
