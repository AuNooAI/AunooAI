/**
 * Policy Article List Component
 * Displays filterable list of policy tracker articles
 */

import { useState } from 'react';
import {
  Search,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  Calendar,
  Tag,
  Filter,
  X,
  Loader2,
} from 'lucide-react';
import type { PolicyArticle, PolicyCategory } from '../../services/policyTrackerApi';
import { CATEGORY_COLORS, CATEGORY_SHORT_NAMES } from '../../services/policyTrackerApi';

interface PolicyArticleListProps {
  articles: PolicyArticle[];
  categories: PolicyCategory[];
  selectedCategories: string[];
  totalCount: number;
  page: number;
  totalPages: number;
  sortBy: 'date' | 'relevance' | 'category_count';
  loading: boolean;
  searchQuery: string;
  searchResults: PolicyArticle[];
  loadingSearch: boolean;
  onCategoryChange: (categories: string[]) => void;
  onSortChange: (sort: 'date' | 'relevance' | 'category_count') => void;
  onPageChange: (page: number) => void;
  onSearch: (query: string) => void;
  onClearSearch: () => void;
  onArticleClick: (article: PolicyArticle) => void;
  onFindRelated: (uri: string) => void;
}

export function PolicyArticleList({
  articles,
  categories,
  selectedCategories,
  totalCount,
  page,
  totalPages,
  sortBy,
  loading,
  searchQuery,
  searchResults,
  loadingSearch,
  onCategoryChange,
  onSortChange,
  onPageChange,
  onSearch,
  onClearSearch,
  onArticleClick,
  onFindRelated,
}: PolicyArticleListProps) {
  const [localSearchQuery, setLocalSearchQuery] = useState(searchQuery);
  const [showFilters, setShowFilters] = useState(false);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (localSearchQuery.trim()) {
      onSearch(localSearchQuery);
    }
  };

  const handleClearSearch = () => {
    setLocalSearchQuery('');
    onClearSearch();
  };

  const toggleCategory = (category: string) => {
    if (selectedCategories.includes(category)) {
      onCategoryChange(selectedCategories.filter((c) => c !== category));
    } else {
      onCategoryChange([...selectedCategories, category]);
    }
  };

  const clearAllFilters = () => {
    onCategoryChange([]);
  };

  const formatDate = (dateStr: string | null): string => {
    if (!dateStr) return '';
    try {
      const date = new Date(dateStr);
      return date.toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
      });
    } catch {
      return dateStr;
    }
  };

  // Use search results if searching, otherwise use regular articles
  const displayArticles = searchResults.length > 0 ? searchResults : articles;
  const isSearching = searchQuery.length > 0;

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
      {/* Header with Search and Filters */}
      <div className="p-4 border-b border-gray-200 dark:border-gray-700">
        <div className="flex flex-col sm:flex-row gap-3">
          {/* Search */}
          <form onSubmit={handleSearch} className="flex-1">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
              <input
                type="text"
                value={localSearchQuery}
                onChange={(e) => setLocalSearchQuery(e.target.value)}
                placeholder="Semantic search within policy articles..."
                className="w-full pl-10 pr-10 py-2 text-sm bg-gray-50 dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-pink-500 dark:text-gray-100"
              />
              {localSearchQuery && (
                <button
                  type="button"
                  onClick={handleClearSearch}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-600 dark:hover:text-gray-500"
                >
                  <X className="w-4 h-4" />
                </button>
              )}
            </div>
          </form>

          {/* Sort and Filter Controls */}
          <div className="flex gap-2">
            <select
              value={sortBy}
              onChange={(e) =>
                onSortChange(e.target.value as 'date' | 'relevance' | 'category_count')
              }
              className="px-3 py-2 text-sm bg-gray-50 dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-pink-500 dark:text-gray-100"
            >
              <option value="date">Sort by Date</option>
              <option value="category_count">Sort by Categories</option>
            </select>

            <button
              onClick={() => setShowFilters(!showFilters)}
              className={`flex items-center gap-2 px-3 py-2 text-sm border rounded-lg transition-colors ${
                showFilters || selectedCategories.length > 0
                  ? 'bg-pink-50 dark:bg-pink-900/20 border-pink-300 dark:border-pink-700 text-pink-700 dark:text-pink-300'
                  : 'bg-gray-50 dark:bg-gray-700 border-gray-200 dark:border-gray-600 text-gray-700 dark:text-gray-300'
              }`}
            >
              <Filter className="w-4 h-4" />
              Filters
              {selectedCategories.length > 0 && (
                <span className="px-1.5 py-0.5 text-xs bg-pink-500 text-white rounded-full">
                  {selectedCategories.length}
                </span>
              )}
            </button>
          </div>
        </div>

        {/* Category Filter Chips */}
        {showFilters && (
          <div className="mt-3 pt-3 border-t border-gray-200 dark:border-gray-700">
            <div className="flex items-center justify-between mb-2">
              <p className="text-xs text-gray-500 dark:text-gray-300">
                Filter by policy category
              </p>
              {selectedCategories.length > 0 && (
                <button
                  onClick={clearAllFilters}
                  className="text-xs text-pink-600 dark:text-pink-400 hover:underline"
                >
                  Clear all
                </button>
              )}
            </div>
            <div className="flex flex-wrap gap-2">
              {categories.map((cat) => (
                <button
                  key={cat.category}
                  onClick={() => toggleCategory(cat.category)}
                  className={`flex items-center gap-1.5 px-2.5 py-1 text-xs rounded-full transition-colors ${
                    selectedCategories.includes(cat.category)
                      ? 'text-white'
                      : 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'
                  }`}
                  style={
                    selectedCategories.includes(cat.category)
                      ? { backgroundColor: CATEGORY_COLORS[cat.category] }
                      : undefined
                  }
                >
                  <span
                    className="w-2 h-2 rounded-full"
                    style={{ backgroundColor: CATEGORY_COLORS[cat.category] }}
                  />
                  {CATEGORY_SHORT_NAMES[cat.category] || cat.category}
                  <span className="opacity-70">({cat.article_count})</span>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Results Info */}
      <div className="px-4 py-2 bg-gray-50 dark:bg-gray-750 border-b border-gray-200 dark:border-gray-700">
        <p className="text-xs text-gray-500 dark:text-gray-300">
          {isSearching ? (
            <>
              {loadingSearch ? (
                <span className="flex items-center gap-1">
                  <Loader2 className="w-3 h-3 animate-spin" />
                  Searching...
                </span>
              ) : (
                <>Found {searchResults.length} results for "{searchQuery}"</>
              )}
            </>
          ) : (
            <>
              Showing {articles.length} of {totalCount} articles
              {selectedCategories.length > 0 && (
                <> in {selectedCategories.length} selected categories</>
              )}
            </>
          )}
        </p>
      </div>

      {/* Article List */}
      <div className="divide-y divide-gray-100 dark:divide-gray-700">
        {loading ? (
          <div className="p-8 text-center">
            <Loader2 className="w-8 h-8 animate-spin text-pink-500 mx-auto mb-2" />
            <p className="text-sm text-gray-500 dark:text-gray-300">Loading articles...</p>
          </div>
        ) : displayArticles.length === 0 ? (
          <div className="p-8 text-center">
            <p className="text-gray-500 dark:text-gray-300">No articles found</p>
            {selectedCategories.length > 0 && (
              <button
                onClick={clearAllFilters}
                className="mt-2 text-sm text-pink-600 dark:text-pink-400 hover:underline"
              >
                Clear filters
              </button>
            )}
          </div>
        ) : (
          displayArticles.map((article) => (
            <div
              key={article.uri}
              className="p-4 hover:bg-gray-50 dark:hover:bg-gray-750 transition-colors cursor-pointer"
              onClick={() => onArticleClick(article)}
            >
              <div className="flex items-start gap-3">
                <div className="flex-1 min-w-0">
                  {/* Title */}
                  <h4 className="text-sm font-medium text-gray-900 dark:text-gray-100 line-clamp-2 mb-1">
                    {article.title}
                  </h4>

                  {/* Meta info */}
                  <div className="flex items-center gap-3 text-xs text-gray-500 dark:text-gray-300 mb-2">
                    {article.news_source && (
                      <span className="font-medium">{article.news_source}</span>
                    )}
                    {article.publication_date && (
                      <span className="flex items-center gap-1">
                        <Calendar className="w-3 h-3" />
                        {formatDate(article.publication_date)}
                      </span>
                    )}
                  </div>

                  {/* Summary */}
                  {article.summary && (
                    <p className="text-xs text-gray-600 dark:text-gray-300 line-clamp-2 mb-2">
                      {article.summary}
                    </p>
                  )}

                  {/* Category Tags */}
                  {article.categories.length > 0 && (
                    <div className="flex flex-wrap gap-1">
                      {article.categories.map((cat) => (
                        <span
                          key={cat}
                          className="inline-flex items-center gap-1 px-2 py-0.5 text-xs rounded-full"
                          style={{
                            backgroundColor: `${CATEGORY_COLORS[cat]}20`,
                            color: CATEGORY_COLORS[cat],
                          }}
                        >
                          <Tag className="w-2.5 h-2.5" />
                          {CATEGORY_SHORT_NAMES[cat] || cat}
                        </span>
                      ))}
                    </div>
                  )}
                </div>

                {/* Actions */}
                <div className="flex flex-col gap-1">
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onFindRelated(article.uri);
                    }}
                    className="p-1.5 text-gray-500 hover:text-pink-500 hover:bg-pink-50 dark:hover:bg-pink-900/20 rounded transition-colors"
                    title="Find related articles"
                  >
                    <ExternalLink className="w-4 h-4" />
                  </button>
                </div>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Pagination */}
      {!isSearching && totalPages > 1 && (
        <div className="flex items-center justify-between px-4 py-3 border-t border-gray-200 dark:border-gray-700">
          <button
            onClick={() => onPageChange(page - 1)}
            disabled={page === 1}
            className="flex items-center gap-1 px-3 py-1.5 text-sm text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-gray-100 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <ChevronLeft className="w-4 h-4" />
            Previous
          </button>

          <span className="text-sm text-gray-500 dark:text-gray-300">
            Page {page} of {totalPages}
          </span>

          <button
            onClick={() => onPageChange(page + 1)}
            disabled={page === totalPages}
            className="flex items-center gap-1 px-3 py-1.5 text-sm text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-gray-100 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Next
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      )}
    </div>
  );
}
