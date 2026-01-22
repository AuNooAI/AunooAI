/**
 * Article List View - Chronological list of articles
 * Shows articles sorted by publication date (newest first) without clustering
 * Features: filters, compact mode, multi-select, bulk actions, time grouping
 */

import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import {
  Loader2,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  ChevronUp,
  Newspaper,
  ArrowUpDown,
  Filter,
  Clock,
  TrendingUp,
  Building2,
  Star,
  CheckSquare,
  Square,
  Check,
  Copy,
  ExternalLink,
  List,
  AlignJustify,
  Download,
  Sparkles,
  X,
  MoreVertical,
  ThumbsUp,
  ThumbsDown,
  Mail,
  RefreshCw,
} from 'lucide-react';
import { type NewsArticle, getArticlesList, getArticleFilterOptions, getTopics, getTopicCategories, type DateRange, type ArticleFilterOptions, recordArticlePreference } from '../../services/newsFeedApi';
import { getCategoryBadgeColor, formatRelativeTime, getTimePeriodLabel } from './cardUtils';
import { ArticleBiasIndicator } from './ArticleBiasIndicator';
import { openAuspexWithQuery } from '../../utils/auspexEvents';
import { ShareModal, type ShareArticleData } from '../ShareModal';

interface ArticleListViewProps {
  dateRange: DateRange;
  topic?: string;
  categories?: string[];
  starredArticles: string[];
  onStar: (uri: string) => void;
  onUnstar: (uri: string) => void;
  onArticleClick: (article: NewsArticle) => void;
  excludedArticles?: string[];
  onExcludeArticle?: (uri: string) => void;
}

type SortOption = 'date_desc' | 'date_asc' | 'source' | 'category';

// Factuality levels for filtering
const FACTUALITY_LEVELS = [
  { key: 'very high', label: 'Very High', color: 'bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300' },
  { key: 'high', label: 'High', color: 'bg-green-50 text-green-600 dark:bg-green-800 dark:text-green-300' },
  { key: 'mostly factual', label: 'Mostly Factual', color: 'bg-yellow-50 text-yellow-700 dark:bg-yellow-900 dark:text-yellow-300' },
  { key: 'mixed', label: 'Mixed', color: 'bg-orange-100 text-orange-700 dark:bg-orange-900 dark:text-orange-300' },
  { key: 'low', label: 'Low', color: 'bg-red-100 text-red-600 dark:bg-red-900 dark:text-red-300' },
];

// Political bias levels for filtering
const BIAS_LEVELS = [
  { key: 'left', label: 'Left', color: 'bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300' },
  { key: 'left-center', label: 'Left-Center', color: 'bg-blue-50 text-blue-600 dark:bg-blue-800 dark:text-blue-300' },
  { key: 'center', label: 'Center', color: 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300' },
  { key: 'right-center', label: 'Right-Center', color: 'bg-red-50 text-red-600 dark:bg-red-800 dark:text-red-300' },
  { key: 'right', label: 'Right', color: 'bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300' },
];

export function ArticleListView({
  dateRange,
  topic,
  categories = [],
  starredArticles,
  onStar,
  onUnstar,
  onArticleClick,
  excludedArticles = [],
  onExcludeArticle,
}: ArticleListViewProps) {
  const [allArticles, setAllArticles] = useState<NewsArticle[]>([]);
  const [filteredArticles, setFilteredArticles] = useState<NewsArticle[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(0);
  const [totalCount, setTotalCount] = useState(0);
  const [selectedCategories, setSelectedCategories] = useState<string[]>([]);
  const [sortBy, setSortBy] = useState<SortOption>('date_desc');
  const [availableCategories, setAvailableCategories] = useState<string[]>([]);

  // New state for enhanced features
  const [compactMode, setCompactMode] = useState(false);
  const [selectedSources, setSelectedSources] = useState<string[]>([]);
  const [selectedFactuality, setSelectedFactuality] = useState<string[]>([]);
  const [selectedBias, setSelectedBias] = useState<string[]>([]);
  const [selectMode, setSelectMode] = useState(false);
  const [selectedUris, setSelectedUris] = useState<Set<string>>(new Set());
  const [showTimeGrouping, setShowTimeGrouping] = useState(true);
  const [readArticles, setReadArticles] = useState<Set<string>>(new Set());
  const [showUnreadOnly, setShowUnreadOnly] = useState(false);

  // Filter options from API (all sources/factuality across all pages)
  const [filterOptions, setFilterOptions] = useState<ArticleFilterOptions | null>(null);
  const [showAllSources, setShowAllSources] = useState(false);
  const [showAllCategories, setShowAllCategories] = useState(false);

  // Topic filter state
  const [availableTopics, setAvailableTopics] = useState<Array<{ name: string; description?: string }>>([]);
  const [selectedTopic, setSelectedTopic] = useState<string | undefined>(topic);
  const [topicCategories, setTopicCategories] = useState<string[]>([]);

  // Share modal state
  const [showShareModal, setShowShareModal] = useState(false);
  const [shareData, setShareData] = useState<ShareArticleData | null>(null);

  const perPage = 25;

  // Available sources from API filter options
  const availableSources = useMemo(() => {
    if (!filterOptions) return [];
    return filterOptions.sources.map((s) => s.name).filter(Boolean) as string[];
  }, [filterOptions]);

  // Available factuality levels from API filter options
  const availableFactuality = useMemo(() => {
    if (!filterOptions) return [];
    return filterOptions.factuality.map((f) => f.level?.toLowerCase()).filter(Boolean) as string[];
  }, [filterOptions]);

  // Available bias levels from API filter options
  const availableBias = useMemo(() => {
    if (!filterOptions) return [];
    return filterOptions.bias.map((b) => b.level?.toLowerCase()).filter(Boolean) as string[];
  }, [filterOptions]);

  const fetchArticles = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await getArticlesList({
        dateRange,
        topic: selectedTopic,
        page,
        perPage,
      });

      setAllArticles(result.articles);
      setTotalPages(result.totalPages);
      setTotalCount(result.totalCount);

      // Build available categories from fetched articles (before filtering)
      const articleCategories = [...new Set(result.articles.map((a) => a.category).filter(Boolean))] as string[];
      // When a topic is selected, only show categories for that topic (from config + actual articles)
      // When no topic is selected, show all categories from articles + provided categories prop
      const mergedCategories = selectedTopic
        ? [...new Set([...topicCategories, ...articleCategories])].sort()
        : [...new Set([...categories, ...articleCategories])].sort();
      setAvailableCategories(mergedCategories);
    } catch (err) {
      console.error('Failed to fetch articles list:', err);
      setError('Failed to load articles. Please try again.');
    } finally {
      setLoading(false);
    }
  }, [dateRange, selectedTopic, page, perPage, categories, topicCategories]);

  // Apply filters and sorting whenever articles or filters change
  useEffect(() => {
    let result = [...allArticles];

    // Apply category filter
    if (selectedCategories.length > 0) {
      result = result.filter((a) => selectedCategories.includes(a.category || ''));
    }

    // Apply source filter
    if (selectedSources.length > 0) {
      result = result.filter((a) => selectedSources.includes(a.source?.name || ''));
    }

    // Apply factuality filter
    if (selectedFactuality.length > 0) {
      result = result.filter((a) =>
        selectedFactuality.includes(a.source?.factuality?.toLowerCase() || '')
      );
    }

    // Apply bias filter
    if (selectedBias.length > 0) {
      result = result.filter((a) =>
        selectedBias.includes(a.source?.bias?.toLowerCase() || '')
      );
    }

    // Apply unread filter
    if (showUnreadOnly) {
      result = result.filter((a) => !readArticles.has(a.uri));
    }

    // Apply sorting
    result.sort((a, b) => {
      switch (sortBy) {
        case 'date_desc':
          return new Date(b.publication_date || 0).getTime() - new Date(a.publication_date || 0).getTime();
        case 'date_asc':
          return new Date(a.publication_date || 0).getTime() - new Date(b.publication_date || 0).getTime();
        case 'source':
          return (a.source?.name || '').localeCompare(b.source?.name || '');
        case 'category':
          return (a.category || '').localeCompare(b.category || '');
        default:
          return 0;
      }
    });

    setFilteredArticles(result);
  }, [allArticles, selectedCategories, selectedSources, selectedFactuality, selectedBias, sortBy, showUnreadOnly, readArticles]);

  // Group articles by time period
  const groupedArticles = useMemo(() => {
    if (!showTimeGrouping || sortBy !== 'date_desc') {
      return [{ label: '', articles: filteredArticles }];
    }

    const groups: { label: string; articles: NewsArticle[] }[] = [];
    let currentLabel = '';
    let currentArticles: NewsArticle[] = [];

    for (const article of filteredArticles) {
      const label = getTimePeriodLabel(article.publication_date);
      if (label !== currentLabel) {
        if (currentArticles.length > 0) {
          groups.push({ label: currentLabel, articles: currentArticles });
        }
        currentLabel = label;
        currentArticles = [];
      }
      currentArticles.push(article);
    }

    if (currentArticles.length > 0) {
      groups.push({ label: currentLabel, articles: currentArticles });
    }

    return groups;
  }, [filteredArticles, showTimeGrouping, sortBy]);

  // Fetch articles when parameters change
  useEffect(() => {
    fetchArticles();
  }, [fetchArticles]);

  // Fetch filter options when date range or topic changes
  useEffect(() => {
    const fetchFilterOptions = async () => {
      try {
        const options = await getArticleFilterOptions({
          dateRange,
          topic: selectedTopic,
        });
        setFilterOptions(options);
      } catch (err) {
        console.error('Failed to fetch filter options:', err);
      }
    };
    fetchFilterOptions();
  }, [dateRange, selectedTopic]);

  // Reset to page 1 when date/topic filters change
  useEffect(() => {
    setPage(1);
    setSelectedCategories([]);
    setSelectedSources([]);
    setSelectedFactuality([]);
    setSelectedBias([]);
    setSelectedUris(new Set());
    setShowAllSources(false);
    setShowAllCategories(false);
  }, [dateRange, selectedTopic]);

  // Fetch available topics on mount
  useEffect(() => {
    const fetchTopics = async () => {
      try {
        const topics = await getTopics();
        setAvailableTopics(topics);
      } catch (err) {
        console.error('Failed to fetch topics:', err);
      }
    };
    fetchTopics();
  }, []);

  // Sync selectedTopic with prop when prop changes
  useEffect(() => {
    setSelectedTopic(topic);
  }, [topic]);

  // Fetch topic-specific categories when selectedTopic changes
  useEffect(() => {
    const fetchCategories = async () => {
      if (!selectedTopic) {
        setTopicCategories([]);
        return;
      }
      try {
        const result = await getTopicCategories(selectedTopic);
        setTopicCategories(result.categories || []);
      } catch (err) {
        console.error('Failed to fetch topic categories:', err);
        setTopicCategories([]);
      }
    };
    fetchCategories();
  }, [selectedTopic]);

  // Mark article as read when clicked
  const handleArticleClick = (article: NewsArticle) => {
    setReadArticles((prev) => new Set(prev).add(article.uri));
    onArticleClick(article);
  };

  const handlePreviousPage = () => {
    if (page > 1) {
      setPage(page - 1);
      // Scroll to top of page and any scrollable parent containers
      window.scrollTo({ top: 0, behavior: 'smooth' });
      document.querySelector('.article-list-container')?.scrollTo({ top: 0, behavior: 'smooth' });
    }
  };

  const handleNextPage = () => {
    if (page < totalPages) {
      setPage(page + 1);
      // Scroll to top of page and any scrollable parent containers
      window.scrollTo({ top: 0, behavior: 'smooth' });
      document.querySelector('.article-list-container')?.scrollTo({ top: 0, behavior: 'smooth' });
    }
  };

  const toggleCategory = (category: string) => {
    setSelectedCategories((prev) =>
      prev.includes(category)
        ? prev.filter((c) => c !== category)
        : [...prev, category]
    );
  };

  const toggleSource = (source: string) => {
    setSelectedSources((prev) =>
      prev.includes(source)
        ? prev.filter((s) => s !== source)
        : [...prev, source]
    );
  };

  const toggleFactuality = (factuality: string) => {
    setSelectedFactuality((prev) =>
      prev.includes(factuality)
        ? prev.filter((f) => f !== factuality)
        : [...prev, factuality]
    );
  };

  const toggleBias = (bias: string) => {
    setSelectedBias((prev) =>
      prev.includes(bias)
        ? prev.filter((b) => b !== bias)
        : [...prev, bias]
    );
  };

  const clearAllFilters = () => {
    setSelectedCategories([]);
    setSelectedSources([]);
    setSelectedBias([]);
    setSelectedFactuality([]);
    setShowUnreadOnly(false);
  };

  // Multi-select handlers
  const toggleSelection = (uri: string) => {
    setSelectedUris((prev) => {
      const newSet = new Set(prev);
      if (newSet.has(uri)) {
        newSet.delete(uri);
      } else {
        newSet.add(uri);
      }
      return newSet;
    });
  };

  const selectAll = () => {
    setSelectedUris(new Set(filteredArticles.map((a) => a.uri)));
  };

  const clearSelection = () => {
    setSelectedUris(new Set());
    setSelectMode(false);
  };

  // Bulk action handlers
  const handleBulkStar = () => {
    selectedUris.forEach((uri) => {
      if (!starredArticles.includes(uri)) {
        onStar(uri);
      }
    });
    clearSelection();
  };

  const handleBulkExport = () => {
    const selected = allArticles.filter((a) => selectedUris.has(a.uri));
    const markdown = selected
      .map((a) =>
        `## ${a.title}\n\n` +
        `**Source:** ${a.source?.name || 'Unknown'}\n` +
        `**Date:** ${a.publication_date || 'Unknown'}\n` +
        `**Category:** ${a.category || 'Uncategorized'}\n` +
        `**URL:** ${a.url || ''}\n\n` +
        `${a.summary || ''}\n`
      )
      .join('\n---\n\n');

    const blob = new Blob([markdown], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `articles-export-${new Date().toISOString().split('T')[0]}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    clearSelection();
  };

  const handleSendToAuspex = () => {
    const selected = allArticles.filter((a) => selectedUris.has(a.uri));

    // Build comprehensive article context for each selected article
    const articlesContext = selected.map((article, index) => {
      const sourceName = article.source?.name || 'Unknown';
      const sourceInfo = [];
      if (article.source?.bias) sourceInfo.push(`Bias: ${article.source.bias}`);
      if (article.source?.factuality) sourceInfo.push(`Factuality: ${article.source.factuality}`);
      const sourceText = sourceInfo.length > 0 ? sourceInfo.join(', ') : '';

      const tagsText = article.tags
        ? (Array.isArray(article.tags) ? article.tags.join(', ') : article.tags)
        : '';

      return `### Article ${index + 1}: "${article.title}"
URI: ${article.uri}
Source: ${sourceName}${sourceText ? ` (${sourceText})` : ''}
${article.publication_date ? `Published: ${article.publication_date}` : ''}
${article.category ? `Category: ${article.category}` : ''}
${article.topic ? `Topic: ${article.topic}` : ''}
${article.sentiment ? `Sentiment: ${article.sentiment}` : ''}
${tagsText ? `Tags: ${tagsText}` : ''}
${article.url ? `URL: ${article.url}` : ''}

${article.summary ? `Summary:\n${article.summary}` : ''}`;
    }).join('\n\n---\n\n');

    const prompt = `Analyze these ${selected.length} articles:

${articlesContext}

Please provide:
1. Common themes and patterns across these articles
2. Key entities and organizations mentioned
3. Divergent perspectives or conflicting information
4. Overall implications and significance
5. Suggested follow-up questions or areas to monitor`;

    openAuspexWithQuery(prompt);
    clearSelection();
  };

  // Share handler
  const handleShareArticle = (article: NewsArticle) => {
    setShareData({
      type: 'article',
      title: article.title,
      url: article.url || article.uri,
      source: article.source?.name,
      summary: article.summary,
      category: article.category,
      topic: article.topic,
      sentiment: article.sentiment,
      publication_date: article.publication_date,
    });
    setShowShareModal(true);
  };

  // Replace/exclude article handler
  const handleExcludeArticle = (uri: string) => {
    if (onExcludeArticle) {
      onExcludeArticle(uri);
    }
  };

  // Check if any filters are active
  const hasActiveFilters = selectedCategories.length > 0 || selectedSources.length > 0 || selectedFactuality.length > 0 || selectedBias.length > 0 || showUnreadOnly;

  // Loading state
  if (loading && allArticles.length === 0) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="flex flex-col items-center gap-4">
          <Loader2 className="w-8 h-8 animate-spin text-pink-500" />
          <p className="text-gray-500 dark:text-gray-300">Loading articles...</p>
        </div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-center">
        <p className="text-red-500 dark:text-red-400 mb-4">{error}</p>
        <button
          onClick={fetchArticles}
          className="px-4 py-2 text-sm bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-md transition-colors"
        >
          Try Again
        </button>
      </div>
    );
  }

  // Empty state (no articles at all) - still show topic filter so user can change selection
  if (allArticles.length === 0) {
    return (
      <div>
        {/* Topic Filter - always show so user can change selection */}
        {availableTopics.length > 0 && (
          <div className="flex items-center gap-2 mb-3 flex-wrap pb-2 border-b border-gray-200 dark:border-gray-700">
            <TrendingUp className="w-3.5 h-3.5 text-gray-600 dark:text-gray-300" />
            <span className="text-xs font-medium text-gray-700 dark:text-gray-300">Topic:</span>
            <button
              onClick={() => setSelectedTopic(undefined)}
              className={`px-2.5 py-1 text-xs rounded-full transition-colors ${
                !selectedTopic
                  ? 'bg-purple-100 dark:bg-purple-900 text-purple-700 dark:text-purple-300'
                  : 'bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700'
              }`}
            >
              All Topics
            </button>
            {availableTopics.map((t) => (
              <button
                key={t.name}
                onClick={() => setSelectedTopic(t.name)}
                title={t.description}
                className={`px-2.5 py-1 text-xs rounded-full transition-colors ${
                  selectedTopic === t.name
                    ? 'bg-purple-100 dark:bg-purple-900 text-purple-700 dark:text-purple-300'
                    : 'bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700'
                }`}
              >
                {t.name}
              </button>
            ))}
          </div>
        )}
        <div className="flex flex-col items-center justify-center h-64 text-center">
          <Newspaper className="w-12 h-12 text-gray-500 dark:text-gray-600 mb-4" />
          <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100">No articles found</h3>
          <p className="text-gray-500 dark:text-gray-300 mt-1">
            {selectedTopic ? `No articles for "${selectedTopic}"` : 'Try adjusting your date range or topic'}
          </p>
          {selectedTopic && (
            <button
              onClick={() => setSelectedTopic(undefined)}
              className="mt-3 px-4 py-2 text-sm bg-purple-100 dark:bg-purple-900 text-purple-700 dark:text-purple-300 hover:bg-purple-200 dark:hover:bg-purple-800 rounded-md transition-colors"
            >
              Show All Topics
            </button>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="article-list-container">
      {/* Topic Filter - at very top */}
      {availableTopics.length > 0 && (
        <div className="flex items-center gap-2 mb-3 flex-wrap pb-2 border-b border-gray-200 dark:border-gray-700">
          <TrendingUp className="w-3.5 h-3.5 text-gray-600 dark:text-gray-300" />
          <span className="text-xs font-medium text-gray-700 dark:text-gray-300">Topic:</span>
          <button
            onClick={() => setSelectedTopic(undefined)}
            className={`px-2.5 py-1 text-xs rounded-full transition-colors ${
              !selectedTopic
                ? 'bg-purple-100 dark:bg-purple-900 text-purple-700 dark:text-purple-300'
                : 'bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700'
            }`}
          >
            All Topics
          </button>
          {availableTopics.map((t) => (
            <button
              key={t.name}
              onClick={() => setSelectedTopic(t.name)}
              title={t.description}
              className={`px-2.5 py-1 text-xs rounded-full transition-colors ${
                selectedTopic === t.name
                  ? 'bg-purple-100 dark:bg-purple-900 text-purple-700 dark:text-purple-300'
                  : 'bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700'
              }`}
            >
              {t.name}
            </button>
          ))}
        </div>
      )}

      {/* Category Filter Chips (multiselect) */}
      {availableCategories.length > 0 && (
        <div className="flex items-center gap-2 mb-2 flex-wrap">
          <Filter className="w-3.5 h-3.5 text-gray-600 dark:text-gray-300" />
          <span className="text-xs text-gray-700 dark:text-gray-300">Categories:</span>
          <button
            onClick={clearAllFilters}
            className={`px-2.5 py-1 text-xs rounded-full transition-colors ${
              !hasActiveFilters
                ? 'bg-pink-100 dark:bg-pink-900 text-pink-700 dark:text-pink-300'
                : 'bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700'
            }`}
          >
            All
          </button>
          {(showAllCategories ? availableCategories : availableCategories.slice(0, 8)).map((cat) => (
            <button
              key={cat}
              onClick={() => toggleCategory(cat)}
              className={`px-2.5 py-1 text-xs rounded-full transition-colors ${
                selectedCategories.includes(cat)
                  ? 'bg-pink-100 dark:bg-pink-900 text-pink-700 dark:text-pink-300'
                  : 'bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700'
              }`}
            >
              {cat}
            </button>
          ))}
          {availableCategories.length > 8 && (
            <button
              onClick={() => setShowAllCategories(!showAllCategories)}
              className="px-2 py-0.5 text-xs text-pink-600 dark:text-pink-400 hover:underline flex items-center gap-0.5"
            >
              {showAllCategories ? (
                <>Show less <ChevronUp className="w-3 h-3" /></>
              ) : (
                <>+{availableCategories.length - 8} more <ChevronDown className="w-3 h-3" /></>
              )}
            </button>
          )}
        </div>
      )}

      {/* Source Filter Chips */}
      {availableSources.length > 0 && (
        <div className="flex items-center gap-2 mb-2 flex-wrap">
          <Building2 className="w-3.5 h-3.5 text-gray-600 dark:text-gray-300" />
          <span className="text-xs text-gray-700 dark:text-gray-300">Sources ({availableSources.length}):</span>
          {(showAllSources ? availableSources : availableSources.slice(0, 10)).map((source) => (
            <button
              key={source}
              onClick={() => toggleSource(source)}
              className={`px-2 py-0.5 text-xs rounded-full transition-colors ${
                selectedSources.includes(source)
                  ? 'bg-blue-100 dark:bg-blue-900 text-blue-700 dark:text-blue-300'
                  : 'bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700'
              }`}
            >
              {source}
            </button>
          ))}
          {availableSources.length > 10 && (
            <button
              onClick={() => setShowAllSources(!showAllSources)}
              className="px-2 py-0.5 text-xs text-pink-600 dark:text-pink-400 hover:underline flex items-center gap-0.5"
            >
              {showAllSources ? (
                <>Show less <ChevronUp className="w-3 h-3" /></>
              ) : (
                <>+{availableSources.length - 10} more <ChevronDown className="w-3 h-3" /></>
              )}
            </button>
          )}
        </div>
      )}

      {/* Factuality Filter Chips */}
      {availableFactuality.length > 0 && (
        <div className="flex items-center gap-2 mb-2 flex-wrap">
          <span className="text-xs text-gray-700 dark:text-gray-300 ml-5">Factuality:</span>
          {FACTUALITY_LEVELS.filter((f) => availableFactuality.includes(f.key)).map((level) => (
            <button
              key={level.key}
              onClick={() => toggleFactuality(level.key)}
              className={`px-2 py-0.5 text-xs rounded-full transition-colors ${
                selectedFactuality.includes(level.key)
                  ? level.color
                  : 'bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700'
              }`}
            >
              {level.label}
            </button>
          ))}
        </div>
      )}

      {/* Bias Filter Chips */}
      {availableBias.length > 0 && (
        <div className="flex items-center gap-2 mb-3 flex-wrap">
          <span className="text-xs text-gray-700 dark:text-gray-300 ml-5">Bias:</span>
          {BIAS_LEVELS.filter((b) => availableBias.includes(b.key)).map((level) => (
            <button
              key={level.key}
              onClick={() => toggleBias(level.key)}
              className={`px-2 py-0.5 text-xs rounded-full transition-colors ${
                selectedBias.includes(level.key)
                  ? level.color
                  : 'bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700'
              }`}
            >
              {level.label}
            </button>
          ))}
        </div>
      )}

      {/* Bulk Action Bar (shown when selections exist) */}
      {selectedUris.size > 0 && (
        <div className="flex items-center gap-2 p-2 mb-3 bg-pink-50 dark:bg-pink-900/30 rounded-lg border border-pink-200 dark:border-pink-800">
          <span className="text-sm font-medium text-pink-700 dark:text-pink-300">
            {selectedUris.size} selected
          </span>
          <div className="flex-1" />
          <button
            onClick={selectAll}
            className="px-2 py-1 text-xs bg-white dark:bg-gray-800 rounded hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
          >
            Select All
          </button>
          <button
            onClick={handleBulkStar}
            className="px-2 py-1 text-xs bg-yellow-100 dark:bg-yellow-900 text-yellow-700 dark:text-yellow-300 rounded hover:bg-yellow-200 dark:hover:bg-yellow-800 transition-colors flex items-center gap-1"
          >
            <Star className="w-3 h-3" />
            Star All
          </button>
          <button
            onClick={handleBulkExport}
            className="px-2 py-1 text-xs bg-blue-100 dark:bg-blue-900 text-blue-700 dark:text-blue-300 rounded hover:bg-blue-200 dark:hover:bg-blue-800 transition-colors flex items-center gap-1"
          >
            <Download className="w-3 h-3" />
            Export
          </button>
          <button
            onClick={handleSendToAuspex}
            className="px-2 py-1 text-xs bg-purple-100 dark:bg-purple-900 text-purple-700 dark:text-purple-300 rounded hover:bg-purple-200 dark:hover:bg-purple-800 transition-colors flex items-center gap-1"
          >
            <Sparkles className="w-3 h-3" />
            Ask Auspex
          </button>
          <button
            onClick={clearSelection}
            className="p-1 text-gray-500 hover:text-gray-700 dark:hover:text-gray-500 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Navigation and Controls Bar */}
      <div className="flex items-center justify-between mb-2 gap-4">
        {/* Left: Back/Forward Navigation */}
        <div className="flex items-center gap-1">
          <button
            onClick={handlePreviousPage}
            disabled={page <= 1 || loading}
            className={`p-1.5 rounded-md transition-colors ${
              page <= 1 || loading
                ? 'text-gray-500 dark:text-gray-600 cursor-not-allowed'
                : 'text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800'
            }`}
            title="Previous page"
          >
            <ChevronLeft className="w-5 h-5" />
          </button>
          <span className="text-sm text-gray-500 dark:text-gray-300 min-w-[60px] text-center">
            {page} / {totalPages}
          </span>
          <button
            onClick={handleNextPage}
            disabled={page >= totalPages || loading}
            className={`p-1.5 rounded-md transition-colors ${
              page >= totalPages || loading
                ? 'text-gray-500 dark:text-gray-600 cursor-not-allowed'
                : 'text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800'
            }`}
            title="Next page"
          >
            <ChevronRight className="w-5 h-5" />
          </button>
        </div>

        {/* Right: Controls + Sort + Count */}
        <div className="flex items-center gap-2">
          {/* Select Mode Toggle */}
          <button
            onClick={() => {
              setSelectMode(!selectMode);
              if (selectMode) setSelectedUris(new Set());
            }}
            className={`p-1.5 rounded-md transition-colors ${
              selectMode
                ? 'bg-pink-100 dark:bg-pink-900 text-pink-700 dark:text-pink-300'
                : 'text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800'
            }`}
            title="Toggle selection mode"
          >
            <CheckSquare className="w-4 h-4" />
          </button>

          {/* Compact Mode Toggle */}
          <button
            onClick={() => setCompactMode(!compactMode)}
            className={`p-1.5 rounded-md transition-colors ${
              compactMode
                ? 'bg-pink-100 dark:bg-pink-900 text-pink-700 dark:text-pink-300'
                : 'text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800'
            }`}
            title={compactMode ? 'Show summaries' : 'Hide summaries (compact mode)'}
          >
            {compactMode ? <List className="w-4 h-4" /> : <AlignJustify className="w-4 h-4" />}
          </button>

          {/* Unread Filter Toggle */}
          <button
            onClick={() => setShowUnreadOnly(!showUnreadOnly)}
            className={`px-2 py-1 text-xs rounded-md transition-colors ${
              showUnreadOnly
                ? 'bg-pink-100 dark:bg-pink-900 text-pink-700 dark:text-pink-300'
                : 'text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800'
            }`}
            title="Show unread only"
          >
            Unread
          </button>

          {/* Sort Options */}
          <div className="relative">
            <ArrowUpDown className="w-3.5 h-3.5 absolute left-2 top-1/2 -translate-y-1/2 text-gray-500" />
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as SortOption)}
              className="pl-7 pr-8 py-1.5 text-xs bg-gray-100 dark:bg-gray-800 border-0 rounded-md text-gray-700 dark:text-gray-300 focus:ring-1 focus:ring-pink-500 appearance-none cursor-pointer"
            >
              <option value="date_desc">Newest First</option>
              <option value="date_asc">Oldest First</option>
              <option value="source">By Source</option>
              <option value="category">By Category</option>
            </select>
          </div>

          {/* Article Count */}
          <span className="text-xs text-gray-500 dark:text-gray-300">
            {filteredArticles.length} / {totalCount.toLocaleString()}
          </span>
        </div>
      </div>

      {/* Filtered empty state */}
      {filteredArticles.length === 0 && hasActiveFilters && (
        <div className="flex flex-col items-center justify-center h-48 text-center bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
          <Newspaper className="w-10 h-10 text-gray-500 dark:text-gray-600 mb-3" />
          <p className="text-sm text-gray-500 dark:text-gray-300">No articles match selected filters</p>
          <button
            onClick={clearAllFilters}
            className="mt-2 text-xs text-pink-600 dark:text-pink-400 hover:underline"
          >
            Clear all filters
          </button>
        </div>
      )}

      {/* Article List with Time Grouping */}
      {filteredArticles.length > 0 && (
        <div className="relative">
          {loading && (
            <div className="absolute inset-0 bg-white/50 dark:bg-gray-800/50 flex items-center justify-center z-10 rounded-lg">
              <Loader2 className="w-6 h-6 animate-spin text-pink-500" />
            </div>
          )}

          {groupedArticles.map((group, groupIndex) => (
            <div key={group.label || groupIndex}>
              {/* Time Period Header - solid background to hide content behind */}
              {group.label && showTimeGrouping && sortBy === 'date_desc' && (
                <div className="sticky -top-8 z-30 -mx-10 px-10 pt-10 pb-2 text-xs font-semibold text-gray-700 dark:text-gray-300 border-b border-gray-300 dark:border-gray-600 bg-[#ffffff] dark:bg-[#111827] shadow-sm">
                  {group.label}
                </div>
              )}

              <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 mb-2 mt-1">
                <div className="divide-y divide-gray-100 dark:divide-gray-700">
                  {group.articles.map((article) => (
                    <ArticleListItem
                      key={article.uri}
                      article={article}
                      isStarred={starredArticles.includes(article.uri)}
                      isRead={readArticles.has(article.uri)}
                      isSelected={selectedUris.has(article.uri)}
                      selectMode={selectMode}
                      compactMode={compactMode}
                      onStar={onStar}
                      onUnstar={onUnstar}
                      onClick={handleArticleClick}
                      onToggleSelect={() => toggleSelection(article.uri)}
                      onShare={handleShareArticle}
                      onExclude={onExcludeArticle ? handleExcludeArticle : undefined}
                    />
                  ))}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Bottom Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center mt-4 gap-2">
          <button
            onClick={handlePreviousPage}
            disabled={page <= 1 || loading}
            className={`p-1.5 rounded-md transition-colors ${
              page <= 1 || loading
                ? 'text-gray-500 dark:text-gray-600 cursor-not-allowed'
                : 'text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800'
            }`}
          >
            <ChevronLeft className="w-5 h-5" />
          </button>
          <span className="text-sm text-gray-500 dark:text-gray-300">
            Page {page} of {totalPages}
          </span>
          <button
            onClick={handleNextPage}
            disabled={page >= totalPages || loading}
            className={`p-1.5 rounded-md transition-colors ${
              page >= totalPages || loading
                ? 'text-gray-500 dark:text-gray-600 cursor-not-allowed'
                : 'text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800'
            }`}
          >
            <ChevronRight className="w-5 h-5" />
          </button>
        </div>
      )}

      {/* Share Modal */}
      {shareData && (
        <ShareModal
          open={showShareModal}
          onOpenChange={setShowShareModal}
          data={shareData}
        />
      )}
    </div>
  );
}

// Individual article list item component
interface ArticleListItemProps {
  article: NewsArticle;
  isStarred: boolean;
  isRead: boolean;
  isSelected: boolean;
  selectMode: boolean;
  compactMode: boolean;
  onStar: (uri: string) => void;
  onUnstar: (uri: string) => void;
  onClick: (article: NewsArticle) => void;
  onToggleSelect: () => void;
  onShare: (article: NewsArticle) => void;
  onExclude?: (uri: string) => void;
}

function ArticleListItem({
  article,
  isStarred,
  isRead,
  isSelected,
  selectMode,
  compactMode,
  onStar,
  onUnstar,
  onClick,
  onToggleSelect,
  onShare,
  onExclude,
}: ArticleListItemProps) {
  const [showMenu, setShowMenu] = useState(false);
  const [preferenceLoading, setPreferenceLoading] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  // Close menu when clicking outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setShowMenu(false);
      }
    };
    if (showMenu) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [showMenu]);

  const handleStarClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (isStarred) {
      onUnstar(article.uri);
    } else {
      onStar(article.uri);
    }
  };

  const handleCopyLink = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (article.url) {
      navigator.clipboard.writeText(article.url);
    }
  };

  const handleCheckboxClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    onToggleSelect();
  };

  const handleMenuClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    setShowMenu(!showMenu);
  };

  const handleMenuAction = async (action: string) => {
    setShowMenu(false);
    if (action === 'more' || action === 'less') {
      try {
        setPreferenceLoading(true);
        await recordArticlePreference(article.uri, action);
      } catch (err) {
        console.error(`Failed to record preference: ${err}`);
      } finally {
        setPreferenceLoading(false);
      }
    } else if (action === 'share') {
      onShare(article);
    } else if (action === 'exclude' && onExclude) {
      onExclude(article.uri);
    }
  };

  return (
    <div
      onClick={() => onClick(article)}
      className={`px-4 py-3 hover:bg-gray-50 dark:hover:bg-gray-750 cursor-pointer transition-colors relative group ${
        isRead ? 'opacity-60' : ''
      } ${isSelected ? 'bg-pink-50 dark:bg-pink-900/20' : ''}`}
    >
      {/* Selection Checkbox (shown in select mode) */}
      {selectMode && (
        <button
          onClick={handleCheckboxClick}
          className="absolute left-2 top-1/2 -translate-y-1/2 p-1"
        >
          {isSelected ? (
            <Check className="w-4 h-4 text-pink-600" />
          ) : (
            <Square className="w-4 h-4 text-gray-500" />
          )}
        </button>
      )}

      {/* Quick Actions (show on hover) - positioned in top-right */}
      <div className="absolute top-3 right-10 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
        <button
          onClick={handleCopyLink}
          className="p-1 rounded hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors"
          title="Copy link"
        >
          <Copy className="w-3.5 h-3.5 text-gray-500" />
        </button>
        {article.url && (
          <a
            href={article.url}
            target="_blank"
            rel="noopener noreferrer"
            onClick={(e) => e.stopPropagation()}
            className="p-1 rounded hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors"
            title="Open in new tab"
          >
            <ExternalLink className="w-3.5 h-3.5 text-gray-500" />
          </a>
        )}

        {/* Menu Button */}
        <div className="relative" ref={menuRef}>
          <button
            onClick={handleMenuClick}
            className={`p-1 rounded hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors ${
              preferenceLoading ? 'opacity-50' : ''
            }`}
            title="More options"
            disabled={preferenceLoading}
          >
            <MoreVertical className="w-3.5 h-3.5 text-gray-500" />
          </button>

          {/* Dropdown Menu */}
          {showMenu && (
            <div className="absolute right-0 top-full mt-1 w-40 bg-white dark:bg-gray-800 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 py-1 z-50">
              <button
                onClick={() => handleMenuAction('more')}
                className="w-full px-3 py-2 text-left text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 flex items-center gap-2"
              >
                <ThumbsUp className="w-3.5 h-3.5 text-green-500" />
                More like this
              </button>
              <button
                onClick={() => handleMenuAction('less')}
                className="w-full px-3 py-2 text-left text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 flex items-center gap-2"
              >
                <ThumbsDown className="w-3.5 h-3.5 text-red-500" />
                Less like this
              </button>
              <button
                onClick={() => handleMenuAction('share')}
                className="w-full px-3 py-2 text-left text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 flex items-center gap-2"
              >
                <Mail className="w-3.5 h-3.5 text-blue-500" />
                Share via email
              </button>
              {onExclude && (
                <button
                  onClick={() => handleMenuAction('exclude')}
                  className="w-full px-3 py-2 text-left text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 flex items-center gap-2"
                >
                  <RefreshCw className="w-3.5 h-3.5 text-orange-500" />
                  Replace
                </button>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Star button in top-right corner */}
      <button
        onClick={handleStarClick}
        className={`absolute top-3 right-3 p-1 rounded transition-colors ${
          isStarred
            ? 'text-yellow-500'
            : 'text-gray-500 dark:text-gray-600 opacity-0 group-hover:opacity-100 hover:text-yellow-500'
        }`}
        title={isStarred ? 'Remove from briefing' : 'Add to briefing'}
      >
        <Star className={`w-4 h-4 ${isStarred ? 'fill-yellow-500' : ''}`} />
      </button>

      {/* Content with optional left padding for checkbox */}
      <div className={selectMode ? 'pl-6' : ''}>
        {/* Top row: Category + Topic badges */}
        <div className="flex items-center gap-2 mb-1.5 pr-8">
          {article.category && (
            <span
              className={`text-xs font-medium px-2 py-0.5 rounded-full ${getCategoryBadgeColor(
                article.category
              )}`}
            >
              {article.category}
            </span>
          )}
          {article.topic && (
            <span className="text-xs text-gray-500 dark:text-gray-300 flex items-center gap-1">
              <TrendingUp className="w-3 h-3" />
              {article.topic}
            </span>
          )}
        </div>

        {/* Title */}
        <h4 className="text-sm font-medium text-gray-900 dark:text-gray-100 line-clamp-2 mb-1.5 pr-8">
          {article.title}
        </h4>

        {/* Summary (truncated) - hidden in compact mode */}
        {!compactMode && article.summary && (
          <p className="text-xs text-gray-600 dark:text-gray-300 line-clamp-2 mb-2">
            {article.summary}
          </p>
        )}

        {/* Bottom row: Source + Credibility Badge + Date */}
        <div className="flex items-center gap-3 text-xs text-gray-500 dark:text-gray-300">
          {article.source?.name && (
            <span className="flex items-center gap-1">
              <Building2 className="w-3 h-3" />
              {article.source.name}
            </span>
          )}
          {/* Source Credibility Badge */}
          {(article.source?.bias || article.source?.factuality) && (
            <ArticleBiasIndicator
              bias={article.source.bias}
              factuality={article.source.factuality}
              size="sm"
              showLabels={false}
            />
          )}
          {article.publication_date && (
            <span className="flex items-center gap-1">
              <Clock className="w-3 h-3" />
              {formatRelativeTime(article.publication_date)}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
