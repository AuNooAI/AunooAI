/**
 * GeopoliticalArticlesTab Component
 * Displays articles linked to geopolitical hotspots with filtering and search
 */

import { useState, useEffect, useCallback } from 'react';
import { Search, Newspaper, ChevronLeft, ChevronRight, MapPin, ExternalLink, Clock, Filter, X } from 'lucide-react';
import { getAllArticles, type LinkedArticle, type ThreatCategory, type RiskLevel, type Hotspot } from '../../services/geopoliticalHotspotsApi';
import { RISK_COLORS, THREAT_CATEGORIES, RISK_LEVELS } from '../../services/geopoliticalHotspotsApi';
import { GeopoliticalArticleDetailPanel } from './GeopoliticalArticleDetailPanel';

interface GeopoliticalArticlesTabProps {
  onArticleClick?: (article: LinkedArticle) => void;
  /** Pre-filter to show only articles from a specific hotspot */
  initialHotspot?: Hotspot | null;
  /** Callback when the hotspot filter is cleared */
  onHotspotFilterClear?: () => void;
  /** Pre-filter by risk level */
  initialRiskLevel?: RiskLevel | null;
}

export function GeopoliticalArticlesTab({ onArticleClick, initialHotspot, onHotspotFilterClear, initialRiskLevel }: GeopoliticalArticlesTabProps) {
  // State
  const [articles, setArticles] = useState<LinkedArticle[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  const [selectedArticle, setSelectedArticle] = useState<LinkedArticle | null>(null);

  // Filters
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);
  const [search, setSearch] = useState('');
  const [searchInput, setSearchInput] = useState('');
  const [selectedRiskLevel, setSelectedRiskLevel] = useState<RiskLevel | null>(initialRiskLevel || null);
  const [selectedCategory, setSelectedCategory] = useState<ThreatCategory | null>(null);
  const [sortBy, setSortBy] = useState<'date' | 'title' | 'relevance' | 'intensity'>('date');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');
  const [showFilters, setShowFilters] = useState(false);
  const [hotspotFilter, setHotspotFilter] = useState<Hotspot | null>(initialHotspot || null);

  // Update hotspot filter when prop changes
  useEffect(() => {
    if (initialHotspot) {
      setHotspotFilter(initialHotspot);
      setPage(1);
    }
  }, [initialHotspot]);

  // Update risk level filter when prop changes
  useEffect(() => {
    if (initialRiskLevel) {
      setSelectedRiskLevel(initialRiskLevel);
      setPage(1);
    }
  }, [initialRiskLevel]);

  // Handle article click - open detail panel
  const handleArticleClick = useCallback((article: LinkedArticle) => {
    setSelectedArticle(article);
    onArticleClick?.(article);
  }, [onArticleClick]);

  // Clear hotspot filter
  const clearHotspotFilter = useCallback(() => {
    setHotspotFilter(null);
    setPage(1);
    onHotspotFilterClear?.();
  }, [onHotspotFilterClear]);

  // Debounced search
  useEffect(() => {
    const timer = setTimeout(() => {
      setSearch(searchInput);
      setPage(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchInput]);

  // Fetch articles
  const fetchArticles = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await getAllArticles({
        page,
        pageSize,
        riskLevel: selectedRiskLevel || undefined,
        category: selectedCategory || undefined,
        hotspotId: hotspotFilter?.id || undefined,
        search: search || undefined,
        sortBy,
        sortOrder,
      });
      setArticles(result.data);
      setTotal(result.total);
      setTotalPages(result.total_pages);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch articles');
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, selectedRiskLevel, selectedCategory, hotspotFilter, search, sortBy, sortOrder]);

  useEffect(() => {
    fetchArticles();
  }, [fetchArticles]);

  // Clear all filters
  const clearFilters = useCallback(() => {
    setSelectedRiskLevel(null);
    setSelectedCategory(null);
    setHotspotFilter(null);
    setSearchInput('');
    setSearch('');
    setSortBy('date');
    setSortOrder('desc');
    setPage(1);
    onHotspotFilterClear?.();
  }, [onHotspotFilterClear]);

  // Format date
  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return 'Unknown';
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  };

  // Check if any filters are active
  const hasActiveFilters = selectedRiskLevel || selectedCategory || hotspotFilter || search;

  return (
    <div className="space-y-4">
      {/* Hotspot Filter Banner */}
      {hotspotFilter && (
        <div className="flex items-center justify-between p-3 bg-pink-50 dark:bg-pink-900/20 border border-pink-200 dark:border-pink-800 rounded-lg">
          <div className="flex items-center gap-2">
            <MapPin className="w-4 h-4 text-pink-600 dark:text-pink-400" />
            <span className="text-sm text-pink-700 dark:text-pink-300">
              Showing articles from <strong>{hotspotFilter.location_name}</strong>
              {hotspotFilter.country_name && ` (${hotspotFilter.country_name})`}
            </span>
            <span
              className="px-2 py-0.5 text-xs font-medium rounded-full text-white ml-2"
              style={{ backgroundColor: RISK_COLORS[hotspotFilter.risk_level] }}
            >
              {hotspotFilter.risk_level.toUpperCase()}
            </span>
          </div>
          <button
            onClick={clearHotspotFilter}
            className="flex items-center gap-1 text-sm text-pink-600 dark:text-pink-400 hover:text-pink-800 dark:hover:text-pink-300"
          >
            <X className="w-4 h-4" />
            Clear
          </button>
        </div>
      )}

      {/* Risk Level Filter Banner (from Overview click) */}
      {selectedRiskLevel && !hotspotFilter && (
        <div
          className="flex items-center justify-between p-3 rounded-lg border"
          style={{
            backgroundColor: `${RISK_COLORS[selectedRiskLevel]}15`,
            borderColor: `${RISK_COLORS[selectedRiskLevel]}40`,
          }}
        >
          <div className="flex items-center gap-2">
            <span
              className="w-3 h-3 rounded-full"
              style={{ backgroundColor: RISK_COLORS[selectedRiskLevel] }}
            />
            <span className="text-sm" style={{ color: RISK_COLORS[selectedRiskLevel] }}>
              Showing <strong className="capitalize">{selectedRiskLevel}</strong> risk articles
            </span>
          </div>
          <button
            onClick={() => {
              setSelectedRiskLevel(null);
              setPage(1);
              onHotspotFilterClear?.();
            }}
            className="flex items-center gap-1 text-sm hover:opacity-80 transition-opacity"
            style={{ color: RISK_COLORS[selectedRiskLevel] }}
          >
            <X className="w-4 h-4" />
            Clear
          </button>
        </div>
      )}

      {/* Search and Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        {/* Search Input */}
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            type="text"
            placeholder="Search articles..."
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            className="w-full pl-10 pr-4 py-2 text-sm bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-pink-500 dark:text-gray-100"
          />
          {searchInput && (
            <button
              onClick={() => {
                setSearchInput('');
                setSearch('');
              }}
              className="absolute right-3 top-1/2 transform -translate-y-1/2 text-gray-400 hover:text-gray-600"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>

        <div className="flex items-center gap-3">
          {/* Filter Toggle */}
          <button
            onClick={() => setShowFilters(!showFilters)}
            className={`flex items-center gap-2 px-3 py-2 text-sm rounded-lg border transition-colors ${
              showFilters || hasActiveFilters
                ? 'bg-pink-50 dark:bg-pink-900/20 border-pink-200 dark:border-pink-800 text-pink-700 dark:text-pink-300'
                : 'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300'
            }`}
          >
            <Filter className="w-4 h-4" />
            Filters
            {hasActiveFilters && (
              <span className="ml-1 px-1.5 py-0.5 text-xs bg-pink-500 text-white rounded-full">
                {[selectedRiskLevel, selectedCategory, hotspotFilter, search].filter(Boolean).length}
              </span>
            )}
          </button>

          {/* Sort Dropdown */}
          <select
            value={`${sortBy}-${sortOrder}`}
            onChange={(e) => {
              const [newSortBy, newSortOrder] = e.target.value.split('-');
              setSortBy(newSortBy as typeof sortBy);
              setSortOrder(newSortOrder as typeof sortOrder);
              setPage(1);
            }}
            className="px-3 py-2 text-sm bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg dark:text-gray-100"
          >
            <option value="date-desc">Newest First</option>
            <option value="date-asc">Oldest First</option>
            <option value="intensity-desc">Highest Intensity</option>
            <option value="relevance-desc">Most Relevant</option>
            <option value="title-asc">Title (A-Z)</option>
          </select>

          {/* Article Count */}
          <span className="text-sm text-gray-500 dark:text-gray-400">
            {total.toLocaleString()} articles
          </span>
        </div>
      </div>

      {/* Filters Panel */}
      {showFilters && (
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 space-y-4">
          <div className="flex items-center justify-between">
            <span className="font-medium text-gray-900 dark:text-gray-100">Filters</span>
            {hasActiveFilters && (
              <button
                onClick={clearFilters}
                className="text-sm text-pink-600 dark:text-pink-400 hover:underline"
              >
                Clear all
              </button>
            )}
          </div>

          {/* Risk Level Filter */}
          <div>
            <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Risk Level</h4>
            <div className="flex flex-wrap gap-2">
              {RISK_LEVELS.map((level) => (
                <button
                  key={level}
                  onClick={() => {
                    setSelectedRiskLevel(selectedRiskLevel === level ? null : level);
                    setPage(1);
                  }}
                  className={`px-3 py-1 text-xs rounded-full border transition-colors ${
                    selectedRiskLevel === level
                      ? 'text-white'
                      : 'bg-white dark:bg-gray-700 text-gray-600 dark:text-gray-300'
                  }`}
                  style={{
                    backgroundColor: selectedRiskLevel === level ? RISK_COLORS[level] : undefined,
                    borderColor: RISK_COLORS[level],
                  }}
                >
                  {level.charAt(0).toUpperCase() + level.slice(1)}
                </button>
              ))}
            </div>
          </div>

          {/* Category Filter */}
          <div>
            <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Category</h4>
            <div className="flex flex-wrap gap-2">
              {THREAT_CATEGORIES.map((category) => (
                <button
                  key={category}
                  onClick={() => {
                    setSelectedCategory(selectedCategory === category ? null : category);
                    setPage(1);
                  }}
                  className={`px-3 py-1 text-xs rounded-full border transition-colors ${
                    selectedCategory === category
                      ? 'bg-pink-500 border-pink-500 text-white'
                      : 'bg-white dark:bg-gray-700 border-gray-200 dark:border-gray-600 text-gray-600 dark:text-gray-300'
                  }`}
                >
                  {category.charAt(0).toUpperCase() + category.slice(1)}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Error State */}
      {error && (
        <div className="p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg text-red-700 dark:text-red-300 text-sm">
          {error}
        </div>
      )}

      {/* Loading State */}
      {loading ? (
        <div className="flex items-center justify-center h-64">
          <div className="animate-pulse text-gray-500 dark:text-gray-400">Loading articles...</div>
        </div>
      ) : articles.length === 0 ? (
        /* Empty State */
        <div className="flex flex-col items-center justify-center h-64 text-center">
          <Newspaper className="w-12 h-12 text-gray-400 dark:text-gray-600 mb-4" />
          <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100">No articles found</h3>
          <p className="text-gray-500 dark:text-gray-400 mt-1 max-w-md">
            {hasActiveFilters
              ? 'Try adjusting your filters'
              : 'Articles will appear here after running the "Update" process to extract locations and link articles to hotspots.'}
          </p>
          {hasActiveFilters && (
            <button
              onClick={clearFilters}
              className="mt-4 text-sm text-pink-600 dark:text-pink-400 hover:underline"
            >
              Clear all filters
            </button>
          )}
        </div>
      ) : (
        /* Articles List */
        <div className="space-y-3">
          {articles.map((article) => (
            <article
              key={article.uri}
              className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 hover:shadow-md transition-shadow cursor-pointer"
              onClick={() => handleArticleClick(article)}
            >
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  {/* Title */}
                  <h4 className="font-semibold text-gray-900 dark:text-gray-100 line-clamp-2 mb-2">
                    {article.title || 'Untitled Article'}
                  </h4>

                  {/* Summary */}
                  {article.summary && (
                    <p className="text-sm text-gray-600 dark:text-gray-400 line-clamp-2 mb-3">
                      {article.summary}
                    </p>
                  )}

                  {/* Metadata Row */}
                  <div className="flex flex-wrap items-center gap-3 text-xs text-gray-500 dark:text-gray-400">
                    {article.source && (
                      <span className="flex items-center gap-1">
                        <ExternalLink className="w-3 h-3" />
                        {article.source}
                      </span>
                    )}
                    {article.publication_date && (
                      <span className="flex items-center gap-1">
                        <Clock className="w-3 h-3" />
                        {formatDate(article.publication_date)}
                      </span>
                    )}
                    {article.category && (
                      <span className="px-2 py-0.5 bg-gray-100 dark:bg-gray-700 rounded">
                        {article.category}
                      </span>
                    )}
                  </div>
                </div>

                {/* Hotspot Info - show all linked locations */}
                <div className="flex-shrink-0 max-w-[200px]">
                  <div className="flex flex-wrap gap-1 justify-end">
                    {(article.hotspots || [{ name: article.hotspot_name, risk_level: article.risk_level }])
                      .slice(0, 4) // Show max 4 hotspots
                      .map((hotspot, idx) => (
                        <span
                          key={idx}
                          className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium rounded-full text-white"
                          style={{ backgroundColor: RISK_COLORS[hotspot.risk_level || 'info'] }}
                          title={`${hotspot.name} (${(hotspot.risk_level || 'info').toUpperCase()})`}
                        >
                          <MapPin className="w-2.5 h-2.5" />
                          <span className="truncate max-w-[80px]">{hotspot.name}</span>
                        </span>
                      ))}
                    {(article.hotspots?.length || 0) > 4 && (
                      <span className="px-2 py-0.5 text-xs text-gray-500 dark:text-gray-400">
                        +{article.hotspots!.length - 4} more
                      </span>
                    )}
                  </div>
                </div>
              </div>
            </article>
          ))}
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between">
          <span className="text-sm text-gray-500 dark:text-gray-400">
            Showing {(page - 1) * pageSize + 1}-{Math.min(page * pageSize, total)} of {total}
          </span>

          <div className="flex items-center gap-2">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
              className="p-2 rounded-lg border border-gray-200 dark:border-gray-700 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-50 dark:hover:bg-gray-700"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>

            <span className="text-sm text-gray-600 dark:text-gray-400">
              Page {page} of {totalPages}
            </span>

            <button
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page === totalPages}
              className="p-2 rounded-lg border border-gray-200 dark:border-gray-700 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-50 dark:hover:bg-gray-700"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}

      {/* Article Detail Panel */}
      {selectedArticle && (
        <GeopoliticalArticleDetailPanel
          article={selectedArticle}
          onClose={() => setSelectedArticle(null)}
        />
      )}
    </div>
  );
}
