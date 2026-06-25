/**
 * ThreatArticlesTab Component
 * Article list with threat linking
 */

import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  FileText,
  Calendar,
  ExternalLink,
  Shield,
  Search,
  ChevronLeft,
  ChevronRight,
  AlertTriangle,
  Users,
  Zap,
  ArrowUpDown,
  Layers,
} from 'lucide-react';
import {
  getAllThreatArticles,
  type LinkedArticle,
  type SeverityLevel,
  SEVERITY_LEVELS,
  SEVERITY_LABELS,
  SEVERITY_COLORS,
} from '../../services/threatIntelligenceApi';

type SortByOption = 'date' | 'title' | 'relevance' | 'severity';
type SortOrder = 'asc' | 'desc';
type GroupByOption = 'none' | 'source' | 'severity' | 'date' | 'threat';
import { ThreatArticleDetailPanel } from './ThreatArticleDetailPanel';

interface ThreatArticlesTabProps {
  onArticleClick?: (article: LinkedArticle) => void;
  onThreatClick?: (threatId: number, threatName: string) => void;
  initialThreat?: { id: number; threat_name: string } | null;
  initialActor?: { id: number; name: string } | null;
  initialCampaign?: { id: number; name: string } | null;
  onThreatFilterClear?: () => void;
  initialSeverityLevel?: SeverityLevel | null;
}

export function ThreatArticlesTab({
  onArticleClick,
  onThreatClick,
  initialThreat,
  initialActor,
  initialCampaign,
  onThreatFilterClear,
  initialSeverityLevel,
}: ThreatArticlesTabProps) {
  const [articles, setArticles] = useState<LinkedArticle[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedSeverity, setSelectedSeverity] = useState<SeverityLevel | ''>(initialSeverityLevel || '');
  const [selectedThreatId, setSelectedThreatId] = useState<number | undefined>(initialThreat?.id);
  const [selectedActorId, setSelectedActorId] = useState<number | undefined>(initialActor?.id);
  const [selectedCampaignId, setSelectedCampaignId] = useState<number | undefined>(initialCampaign?.id);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalCount, setTotalCount] = useState(0);
  const [selectedArticle, setSelectedArticle] = useState<LinkedArticle | null>(null);
  const [sortBy, setSortBy] = useState<SortByOption>('date');
  const [sortOrder, setSortOrder] = useState<SortOrder>('desc');
  const [groupBy, setGroupBy] = useState<GroupByOption>('none');
  const pageSize = 20;

  // Update filters when initial props change
  useEffect(() => {
    if (initialSeverityLevel) {
      setSelectedSeverity(initialSeverityLevel);
    }
  }, [initialSeverityLevel]);

  useEffect(() => {
    setSelectedThreatId(initialThreat?.id);
  }, [initialThreat]);

  useEffect(() => {
    setSelectedActorId(initialActor?.id);
  }, [initialActor]);

  useEffect(() => {
    setSelectedCampaignId(initialCampaign?.id);
  }, [initialCampaign]);

  const fetchArticles = useCallback(async () => {
    setLoading(true);
    try {
      const result = await getAllThreatArticles({
        page,
        pageSize,
        search: searchQuery || undefined,
        severityLevel: selectedSeverity || undefined,
        threatId: selectedThreatId,
        actorId: selectedActorId,
        campaignId: selectedCampaignId,
        sortBy,
        sortOrder,
      });
      setArticles(result.data);
      setTotalPages(result.total_pages);
      setTotalCount(result.total);
    } catch (error) {
      console.error('Error fetching articles:', error);
    } finally {
      setLoading(false);
    }
  }, [page, searchQuery, selectedSeverity, selectedThreatId, selectedActorId, selectedCampaignId, sortBy, sortOrder]);

  useEffect(() => {
    fetchArticles();
  }, [fetchArticles]);

  useEffect(() => {
    setPage(1);
  }, [searchQuery, selectedSeverity, sortBy, sortOrder]);

  // Group articles based on groupBy selection
  const groupedArticles = useMemo(() => {
    if (groupBy === 'none') {
      return [{ key: 'all', label: '', articles }];
    }

    const groups: Record<string, LinkedArticle[]> = {};

    for (const article of articles) {
      let key: string;
      switch (groupBy) {
        case 'source':
          key = article.source || 'Unknown Source';
          break;
        case 'severity':
          key = article.severity_level || 'unknown';
          break;
        case 'date':
          key = article.publication_date
            ? new Date(article.publication_date).toLocaleDateString('en-US', {
                year: 'numeric',
                month: 'short',
                day: 'numeric',
              })
            : 'Unknown Date';
          break;
        case 'threat':
          key = article.threats && article.threats.length > 0
            ? article.threats[0].name
            : 'No Threat';
          break;
        default:
          key = 'all';
      }

      if (!groups[key]) {
        groups[key] = [];
      }
      groups[key].push(article);
    }

    // Sort groups based on the groupBy type
    const sortedKeys = Object.keys(groups).sort((a, b) => {
      if (groupBy === 'severity') {
        const order = ['critical', 'high', 'medium', 'low', 'info', 'unknown'];
        return order.indexOf(a) - order.indexOf(b);
      }
      if (groupBy === 'date') {
        return new Date(b).getTime() - new Date(a).getTime();
      }
      return a.localeCompare(b);
    });

    return sortedKeys.map((key) => ({
      key,
      label: groupBy === 'severity' ? SEVERITY_LABELS[key as SeverityLevel] || key : key,
      articles: groups[key],
    }));
  }, [articles, groupBy]);

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  };

  const formatTimeAgo = (dateStr: string) => {
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
    const diffDays = Math.floor(diffHours / 24);

    if (diffHours < 1) return 'Just now';
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    return formatDate(dateStr);
  };

  const handleArticleClick = (article: LinkedArticle) => {
    setSelectedArticle(article);
    onArticleClick?.(article);
  };

  const handleClosePanel = () => {
    setSelectedArticle(null);
  };

  const handleThreatClick = (threatId: number, threatName: string) => {
    setSelectedArticle(null);
    onThreatClick?.(threatId, threatName);
  };

  return (
    <div className="space-y-4">
      {/* Search and Filters */}
      <div className="flex flex-col gap-3">
        <div className="flex flex-col sm:flex-row gap-3">
          <div className="flex-1 relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input
              type="text"
              placeholder="Search articles..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-10 pr-4 py-2 text-sm bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-red-500"
            />
          </div>
          <select
            value={selectedSeverity}
            onChange={(e) => setSelectedSeverity(e.target.value as SeverityLevel | '')}
            className="px-3 py-2 text-sm bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-red-500"
          >
            <option value="">All Severities</option>
            {SEVERITY_LEVELS.map((level) => (
              <option key={level} value={level}>
                {SEVERITY_LABELS[level]}
              </option>
            ))}
          </select>
        </div>

        {/* Sort and Group Controls */}
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <div className="flex items-center gap-2">
            <ArrowUpDown className="w-4 h-4 text-gray-400" />
            <span className="text-gray-500 dark:text-gray-400">Sort:</span>
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as SortByOption)}
              className="px-2 py-1 text-sm bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded focus:outline-none focus:ring-1 focus:ring-red-500"
            >
              <option value="date">Date</option>
              <option value="title">Title</option>
              <option value="severity">Severity</option>
              <option value="relevance">Relevance</option>
            </select>
            <select
              value={sortOrder}
              onChange={(e) => setSortOrder(e.target.value as SortOrder)}
              className="px-2 py-1 text-sm bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded focus:outline-none focus:ring-1 focus:ring-red-500"
            >
              <option value="desc">Desc</option>
              <option value="asc">Asc</option>
            </select>
          </div>

          <div className="h-4 w-px bg-gray-300 dark:bg-gray-600" />

          <div className="flex items-center gap-2">
            <Layers className="w-4 h-4 text-gray-400" />
            <span className="text-gray-500 dark:text-gray-400">Group:</span>
            <select
              value={groupBy}
              onChange={(e) => setGroupBy(e.target.value as GroupByOption)}
              className="px-2 py-1 text-sm bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded focus:outline-none focus:ring-1 focus:ring-red-500"
            >
              <option value="none">None</option>
              <option value="source">Source</option>
              <option value="severity">Severity</option>
              <option value="date">Date</option>
              <option value="threat">Threat</option>
            </select>
          </div>
        </div>
      </div>

      {/* Active Threat Filter Badge */}
      {initialThreat && (
        <div className="flex items-center gap-2">
          <span className="text-sm text-gray-500 dark:text-gray-400">Filtering by threat:</span>
          <span className="inline-flex items-center gap-1.5 px-3 py-1 bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300 rounded-full text-sm">
            <Shield className="w-3.5 h-3.5" />
            {initialThreat.threat_name}
            <button
              onClick={() => {
                setSelectedThreatId(undefined);
                onThreatFilterClear?.();
              }}
              className="ml-1 hover:bg-red-200 dark:hover:bg-red-800/50 rounded-full p-0.5 transition-colors"
            >
              <span className="sr-only">Clear filter</span>
              <svg className="w-3 h-3" viewBox="0 0 12 12" fill="currentColor">
                <path d="M3.05 3.05a.75.75 0 011.06 0L6 4.94l1.89-1.89a.75.75 0 111.06 1.06L7.06 6l1.89 1.89a.75.75 0 11-1.06 1.06L6 7.06l-1.89 1.89a.75.75 0 11-1.06-1.06L4.94 6 3.05 4.11a.75.75 0 010-1.06z" />
              </svg>
            </button>
          </span>
        </div>
      )}

      {/* Active Actor Filter Badge */}
      {initialActor && (
        <div className="flex items-center gap-2">
          <span className="text-sm text-gray-500 dark:text-gray-400">Filtering by actor:</span>
          <span className="inline-flex items-center gap-1.5 px-3 py-1 bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300 rounded-full text-sm">
            <Users className="w-3.5 h-3.5" />
            {initialActor.name}
            <button
              onClick={() => {
                setSelectedActorId(undefined);
                onThreatFilterClear?.();
              }}
              className="ml-1 hover:bg-purple-200 dark:hover:bg-purple-800/50 rounded-full p-0.5 transition-colors"
            >
              <span className="sr-only">Clear filter</span>
              <svg className="w-3 h-3" viewBox="0 0 12 12" fill="currentColor">
                <path d="M3.05 3.05a.75.75 0 011.06 0L6 4.94l1.89-1.89a.75.75 0 111.06 1.06L7.06 6l1.89 1.89a.75.75 0 11-1.06 1.06L6 7.06l-1.89 1.89a.75.75 0 11-1.06-1.06L4.94 6 3.05 4.11a.75.75 0 010-1.06z" />
              </svg>
            </button>
          </span>
        </div>
      )}

      {/* Active Campaign Filter Badge */}
      {initialCampaign && (
        <div className="flex items-center gap-2">
          <span className="text-sm text-gray-500 dark:text-gray-400">Filtering by campaign:</span>
          <span className="inline-flex items-center gap-1.5 px-3 py-1 bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-300 rounded-full text-sm">
            <Zap className="w-3.5 h-3.5" />
            {initialCampaign.name}
            <button
              onClick={() => {
                setSelectedCampaignId(undefined);
                onThreatFilterClear?.();
              }}
              className="ml-1 hover:bg-yellow-200 dark:hover:bg-yellow-800/50 rounded-full p-0.5 transition-colors"
            >
              <span className="sr-only">Clear filter</span>
              <svg className="w-3 h-3" viewBox="0 0 12 12" fill="currentColor">
                <path d="M3.05 3.05a.75.75 0 011.06 0L6 4.94l1.89-1.89a.75.75 0 111.06 1.06L7.06 6l1.89 1.89a.75.75 0 11-1.06 1.06L6 7.06l-1.89 1.89a.75.75 0 11-1.06-1.06L4.94 6 3.05 4.11a.75.75 0 010-1.06z" />
              </svg>
            </button>
          </span>
        </div>
      )}

      {/* Results Count */}
      <div className="flex items-center justify-between text-sm text-gray-500 dark:text-gray-400">
        <span>
          {totalCount} articles with linked threats
          {searchQuery && ` matching "${searchQuery}"`}
        </span>
        <span>
          Page {page} of {totalPages}
        </span>
      </div>

      {/* Article List */}
      {loading ? (
        <div className="flex items-center justify-center h-64">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-red-500"></div>
        </div>
      ) : articles.length === 0 ? (
        <div className="text-center py-12">
          <FileText className="w-12 h-12 text-gray-300 dark:text-gray-600 mx-auto mb-3" />
          <p className="text-gray-500 dark:text-gray-400">No articles found</p>
        </div>
      ) : (
        <div className="space-y-4">
          {groupedArticles.map((group) => (
            <div key={group.key}>
              {/* Group Header */}
              {groupBy !== 'none' && (
                <div className="flex items-center gap-2 mb-2 mt-4 first:mt-0">
                  {groupBy === 'severity' && (
                    <span
                      className="w-3 h-3 rounded-full"
                      style={{ backgroundColor: SEVERITY_COLORS[group.key as SeverityLevel] || '#6B7280' }}
                    />
                  )}
                  <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300">
                    {group.label}
                  </h4>
                  <span className="text-xs text-gray-500 dark:text-gray-400">
                    ({group.articles.length})
                  </span>
                </div>
              )}

              {/* Articles in Group */}
              <div className="space-y-3">
                {group.articles.map((article) => (
                  <div
                    key={article.uri}
                    onClick={() => handleArticleClick(article)}
                    className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 hover:border-red-300 dark:hover:border-red-700 transition-colors cursor-pointer"
                  >
                    <div className="flex items-start gap-4">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-start justify-between gap-2">
                          <h3 className="font-medium text-gray-900 dark:text-gray-100 line-clamp-2">
                            {article.title}
                          </h3>
                          {article.uri && (
                            <a
                              href={article.uri}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="flex-shrink-0 text-gray-400 hover:text-red-500 transition-colors"
                              onClick={(e) => e.stopPropagation()}
                            >
                              <ExternalLink className="w-4 h-4" />
                            </a>
                          )}
                        </div>

                        <div className="flex items-center gap-3 mt-2 text-xs text-gray-500 dark:text-gray-400">
                          {article.source && (
                            <span className="font-medium">{article.source}</span>
                          )}
                          {article.publication_date && (
                            <span className="flex items-center gap-1">
                              <Calendar className="w-3 h-3" />
                              {formatTimeAgo(article.publication_date)}
                            </span>
                          )}
                        </div>

                        {article.summary && (
                          <p className="mt-2 text-sm text-gray-600 dark:text-gray-400 line-clamp-2">
                            {article.summary}
                          </p>
                        )}

                        {/* Linked Threats */}
                        {article.threats && article.threats.length > 0 && (
                          <div className="mt-3 pt-3 border-t border-gray-100 dark:border-gray-700">
                            <div className="flex items-center gap-2 mb-2">
                              <AlertTriangle className="w-3 h-3 text-red-500" />
                              <span className="text-xs font-medium text-gray-700 dark:text-gray-300">
                                Linked Threats ({article.threats.length})
                              </span>
                            </div>
                            <div className="flex flex-wrap gap-2">
                              {article.threats.slice(0, 5).map((threat) => (
                                <button
                                  key={threat.id}
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    handleThreatClick(threat.id, threat.name);
                                  }}
                                  className="flex items-center gap-1.5 px-2 py-1 bg-red-50 dark:bg-red-900/20 rounded text-xs hover:bg-red-100 dark:hover:bg-red-900/30 transition-colors"
                                >
                                  <Shield className="w-3 h-3 text-red-500" />
                                  <span className="text-gray-700 dark:text-gray-300 truncate max-w-[150px]">
                                    {threat.name}
                                  </span>
                                  <span
                                    className="px-1 py-0.5 rounded text-white text-[10px]"
                                    style={{ backgroundColor: SEVERITY_COLORS[threat.severity_level] }}
                                  >
                                    {threat.severity_level}
                                  </span>
                                </button>
                              ))}
                              {article.threats.length > 5 && (
                                <span className="px-2 py-1 text-xs text-gray-500 dark:text-gray-400">
                                  +{article.threats.length - 5} more
                                </span>
                              )}
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2 pt-4">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page === 1}
            className="flex items-center gap-1 px-3 py-2 text-sm bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
          >
            <ChevronLeft className="w-4 h-4" />
            Previous
          </button>

          <div className="flex items-center gap-1">
            {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
              let pageNum: number;
              if (totalPages <= 5) {
                pageNum = i + 1;
              } else if (page <= 3) {
                pageNum = i + 1;
              } else if (page >= totalPages - 2) {
                pageNum = totalPages - 4 + i;
              } else {
                pageNum = page - 2 + i;
              }

              return (
                <button
                  key={pageNum}
                  onClick={() => setPage(pageNum)}
                  className={`w-8 h-8 text-sm rounded-lg transition-colors ${
                    page === pageNum
                      ? 'bg-red-500 text-white'
                      : 'bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700'
                  }`}
                >
                  {pageNum}
                </button>
              );
            })}
          </div>

          <button
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page === totalPages}
            className="flex items-center gap-1 px-3 py-2 text-sm bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
          >
            Next
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Article Detail Panel */}
      <ThreatArticleDetailPanel
        article={selectedArticle}
        onClose={handleClosePanel}
        onThreatClick={handleThreatClick}
      />
    </div>
  );
}
