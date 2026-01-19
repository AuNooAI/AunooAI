/**
 * Saved Articles Section - Display starred/saved articles
 * Shows in the Saved tab alongside other saved content
 */

import { useState, useEffect, useRef } from 'react';
import {
  Star,
  ExternalLink,
  Calendar,
  Newspaper,
  MoreVertical,
  Share2,
  Trash2,
  Loader2,
} from 'lucide-react';
import { type NewsArticle, getArticleByUri } from '../../services/newsFeedApi';
import { Skeleton } from '../ui/skeleton';
import { ShareModal, type ShareArticleData } from '../ShareModal';

interface SavedArticlesSectionProps {
  starredArticles: string[];
  onUnstar: (uri: string) => void;
  onArticleClick?: (article: NewsArticle) => void;
  className?: string;
}

export function SavedArticlesSection({
  starredArticles,
  onUnstar,
  onArticleClick,
  className,
}: SavedArticlesSectionProps) {
  const [articles, setArticles] = useState<NewsArticle[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingUris, setLoadingUris] = useState<Set<string>>(new Set());

  // Share modal state
  const [showShareModal, setShowShareModal] = useState(false);
  const [shareData, setShareData] = useState<ShareArticleData | null>(null);

  // Fetch full article data for each starred URI
  useEffect(() => {
    const fetchArticles = async () => {
      if (starredArticles.length === 0) {
        setArticles([]);
        setLoading(false);
        return;
      }

      setLoading(true);
      const newLoadingUris = new Set(starredArticles);
      setLoadingUris(newLoadingUris);

      const fetchedArticles: NewsArticle[] = [];

      await Promise.all(
        starredArticles.map(async (uri) => {
          try {
            const article = await getArticleByUri(uri);
            if (article) {
              fetchedArticles.push(article);
            }
          } catch (err) {
            console.warn(`Failed to fetch article ${uri}:`, err);
          } finally {
            setLoadingUris((prev) => {
              const next = new Set(prev);
              next.delete(uri);
              return next;
            });
          }
        })
      );

      // Sort by publication date (newest first)
      fetchedArticles.sort((a, b) => {
        const dateA = a.publication_date ? new Date(a.publication_date).getTime() : 0;
        const dateB = b.publication_date ? new Date(b.publication_date).getTime() : 0;
        return dateB - dateA;
      });

      setArticles(fetchedArticles);
      setLoading(false);
    };

    fetchArticles();
  }, [starredArticles]);

  const formatDate = (dateStr?: string) => {
    if (!dateStr) return '';
    try {
      const date = new Date(dateStr);
      return date.toLocaleDateString('en-GB', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
      }).replace(/\//g, '.');
    } catch {
      return dateStr;
    }
  };

  const handleShare = (article: NewsArticle) => {
    setShareData({
      type: 'article',
      title: article.title,
      url: article.uri,
      source: article.source?.name,
      summary: article.summary,
      category: article.category,
      topic: article.topic,
      sentiment: article.sentiment,
      publication_date: article.publication_date,
    });
    setShowShareModal(true);
  };

  return (
    <div className={className}>
      {/* Section Header */}
      <div className="flex items-center gap-3 mb-4">
        <Star className="w-5 h-5 text-yellow-500 fill-yellow-500" />
        <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
          Starred Articles
        </h2>
        <span className="text-sm text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 px-2 py-0.5 rounded-full">
          {starredArticles.length} saved
        </span>
      </div>

      {/* Loading State */}
      {loading && starredArticles.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {Array.from({ length: Math.min(starredArticles.length, 4) }).map((_, i) => (
            <Skeleton key={i} className="h-[120px] rounded-lg" />
          ))}
        </div>
      )}

      {/* Empty State */}
      {!loading && articles.length === 0 && (
        <div className="flex flex-col items-center justify-center py-12 text-center">
          <Newspaper className="w-12 h-12 text-gray-400 mb-3" />
          <h3 className="text-lg font-medium text-gray-700 dark:text-gray-400 mb-1">
            No Starred Articles
          </h3>
          <p className="text-sm text-gray-500 dark:text-gray-400 max-w-xs">
            Star articles by clicking the star icon on any article to save them here for easy access.
          </p>
        </div>
      )}

      {/* Articles Grid */}
      {!loading && articles.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {articles.map((article) => (
            <ArticleCard
              key={article.uri}
              article={article}
              onUnstar={onUnstar}
              onArticleClick={onArticleClick}
              onShare={handleShare}
              formatDate={formatDate}
            />
          ))}
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

interface ArticleCardProps {
  article: NewsArticle;
  onUnstar: (uri: string) => void;
  onArticleClick?: (article: NewsArticle) => void;
  onShare: (article: NewsArticle) => void;
  formatDate: (date?: string) => string;
}

function ArticleCard({
  article,
  onUnstar,
  onArticleClick,
  onShare,
  formatDate,
}: ArticleCardProps) {
  const [showMenu, setShowMenu] = useState(false);
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

  return (
    <div
      className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-4 hover:shadow-md transition-shadow cursor-pointer"
      onClick={() => onArticleClick?.(article)}
    >
      {/* Header */}
      <div className="flex items-start justify-between mb-2">
        <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
          <Calendar className="w-3.5 h-3.5" />
          <span>{formatDate(article.publication_date)}</span>
          {article.source?.name && (
            <>
              <span className="text-gray-300 dark:text-gray-600">·</span>
              <span>{article.source.name}</span>
            </>
          )}
        </div>

        {/* Menu */}
        <div ref={menuRef} className="relative">
          <button
            onClick={(e) => {
              e.stopPropagation();
              setShowMenu(!showMenu);
            }}
            className="p-1 hover:bg-gray-100 dark:hover:bg-gray-700 rounded transition-colors"
          >
            <MoreVertical className="w-4 h-4 text-gray-500 dark:text-gray-400" />
          </button>
          {showMenu && (
            <div className="absolute right-0 top-full mt-1 w-40 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg z-20 py-1">
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onShare(article);
                  setShowMenu(false);
                }}
                className="w-full px-3 py-2 text-left text-sm text-gray-900 dark:text-gray-100 hover:bg-gray-100 dark:hover:bg-gray-700 flex items-center gap-2"
              >
                <Share2 className="w-4 h-4 text-gray-500 dark:text-gray-400" />
                Send via Email
              </button>
              {article.uri && (
                <a
                  href={article.uri}
                  target="_blank"
                  rel="noopener noreferrer"
                  onClick={(e) => e.stopPropagation()}
                  className="w-full px-3 py-2 text-left text-sm text-gray-900 dark:text-gray-100 hover:bg-gray-100 dark:hover:bg-gray-700 flex items-center gap-2"
                >
                  <ExternalLink className="w-4 h-4 text-gray-500 dark:text-gray-400" />
                  Open Original
                </a>
              )}
              <div className="h-px bg-gray-200 dark:bg-gray-700 my-1" />
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onUnstar(article.uri);
                  setShowMenu(false);
                }}
                className="w-full px-3 py-2 text-left text-sm text-red-600 dark:text-red-400 hover:bg-gray-100 dark:hover:bg-gray-700 flex items-center gap-2"
              >
                <Trash2 className="w-4 h-4" />
                Remove Star
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Category badge */}
      {article.category && (
        <span className="inline-block text-xs font-medium bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 px-2 py-0.5 rounded mb-2">
          {article.category}
        </span>
      )}

      {/* Title */}
      <h4 className="font-semibold text-gray-900 dark:text-gray-100 text-sm mb-2 line-clamp-2">
        {article.title}
      </h4>

      {/* Summary */}
      {article.summary && (
        <p className="text-xs text-gray-600 dark:text-gray-400 line-clamp-2">
          {article.summary}
        </p>
      )}

      {/* Star indicator */}
      <div className="flex items-center justify-end mt-3">
        <Star className="w-4 h-4 text-yellow-500 fill-yellow-500" />
      </div>
    </div>
  );
}
