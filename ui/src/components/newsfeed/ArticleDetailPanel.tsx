/**
 * Article Detail Panel - Slide-in panel for full article details
 * Shows rich metadata, summary, and action buttons
 * Supports related articles tab for clustered articles
 */

import { useState, useRef, useEffect } from 'react';
import { X, ExternalLink, Star, StarOff, MessageSquare, Clock, TrendingUp, Building2, Layers, ChevronRight, MoreVertical, ThumbsUp, ThumbsDown, Share, Bot } from 'lucide-react';
import { type NewsArticle, type ClusterRelatedArticle } from '../../services/newsFeedApi';
import { ArticleBiasIndicator } from './ArticleBiasIndicator';
import { Button } from '../ui/button';
import { openAuspexWithQuery } from '../../utils/auspexEvents';

interface ArticleDetailPanelProps {
  article: NewsArticle | null;
  relatedArticles?: ClusterRelatedArticle[];
  isStarred?: boolean;
  onClose: () => void;
  onStar?: (uri: string) => void;
  onUnstar?: (uri: string) => void;
  onRelatedArticleClick?: (uri: string) => void;
}

export function ArticleDetailPanel({
  article,
  relatedArticles = [],
  isStarred = false,
  onClose,
  onStar,
  onUnstar,
  onRelatedArticleClick
}: ArticleDetailPanelProps) {
  const [activeTab, setActiveTab] = useState<'details' | 'related'>('details');
  const [showMenu, setShowMenu] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const hasRelated = relatedArticles.length > 0;

  // Close menu when clicking outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setShowMenu(false);
      }
    };
    if (showMenu) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [showMenu]);

  const handleMenuAction = (action: string) => {
    setShowMenu(false);
    console.log(`Menu action: ${action} for article: ${article?.title}`);
  };

  if (!article) return null;

  const handleStarClick = () => {
    if (isStarred) {
      onUnstar?.(article.uri);
    } else {
      onStar?.(article.uri);
    }
  };

  const handleAskAuspex = () => {
    // Build comprehensive article context
    const sourceName = article.source?.name || 'Unknown source';
    const sourceInfo = [];
    if (article.source?.bias) sourceInfo.push(`Bias: ${article.source.bias}`);
    if (article.source?.factuality) sourceInfo.push(`Factuality: ${article.source.factuality}`);
    if (article.source?.credibility_rating) sourceInfo.push(`Credibility: ${article.source.credibility_rating}`);
    const sourceText = sourceInfo.length > 0 ? sourceInfo.join(', ') : '';

    const tagsText = article.tags
      ? (Array.isArray(article.tags) ? article.tags.join(', ') : article.tags)
      : '';

    const prompt = `Analyze this article: "${article.title}"
Article URI: ${article.uri}
Source: ${sourceName}${sourceText ? ` (${sourceText})` : ''}

ARTICLE METADATA:
${article.category ? `Category: ${article.category}` : ''}
${article.topic ? `Topic: ${article.topic}` : ''}
${article.sentiment ? `Sentiment: ${article.sentiment}` : ''}
${article.time_to_impact ? `Time to Impact: ${article.time_to_impact}` : ''}
${tagsText ? `Tags: ${tagsText}` : ''}

${article.summary ? `SUMMARY:\n${article.summary}` : ''}

Please provide:
1. Key insights and implications from this article
2. Entities and organizations mentioned
3. Potential impact on our organization
4. Related trends or developments to monitor
5. Suggested follow-up questions`;

    openAuspexWithQuery(prompt);
  };

  const formatDate = (dateStr?: string) => {
    if (!dateStr) return 'Unknown date';
    try {
      return new Date(dateStr).toLocaleDateString('en-US', {
        weekday: 'short',
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
      });
    } catch {
      return dateStr;
    }
  };

  const formatRelativeTime = (dateStr?: string) => {
    if (!dateStr) return '';
    try {
      const date = new Date(dateStr);
      const now = new Date();
      const diffMs = now.getTime() - date.getTime();
      const diffMins = Math.floor(diffMs / 60000);
      const diffHours = Math.floor(diffMins / 60);
      const diffDays = Math.floor(diffHours / 24);

      if (diffMins < 60) return `${diffMins}m ago`;
      if (diffHours < 24) return `${diffHours}h ago`;
      if (diffDays < 7) return `${diffDays}d ago`;
      return date.toLocaleDateString();
    } catch {
      return dateStr;
    }
  };

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/20 z-40"
        onClick={onClose}
      />

      {/* Panel */}
      <div className="fixed inset-y-0 right-0 w-full max-w-lg bg-white shadow-2xl z-50 overflow-y-auto transform transition-transform duration-300">
        {/* Header */}
        <div className="sticky top-0 bg-white border-b border-gray-200 z-10">
          <div className="px-6 py-4 flex items-center justify-between">
            {/* Left side: Star button */}
            <button
              onClick={handleStarClick}
              className="p-2 hover:bg-gray-100 rounded-full transition-colors"
              title={isStarred ? 'Remove from starred' : 'Add to starred'}
            >
              {isStarred ? (
                <Star className="w-5 h-5 text-yellow-500 fill-yellow-500" />
              ) : (
                <Star className="w-5 h-5 text-gray-400 hover:text-yellow-500" />
              )}
            </button>

            <h2 className="text-lg font-semibold text-gray-900 truncate px-4 flex-1 text-center">Article Details</h2>

            {/* Right side: Menu and Close */}
            <div className="flex items-center gap-1">
              {/* Kebab menu */}
              <div ref={menuRef} className="relative">
                <button
                  onClick={() => setShowMenu(!showMenu)}
                  className="p-2 hover:bg-gray-100 rounded-full transition-colors"
                >
                  <MoreVertical className="w-5 h-5 text-gray-500" />
                </button>
                {showMenu && (
                  <div className="absolute right-0 top-full mt-1 bg-white border border-gray-200 rounded-lg shadow-lg z-50 py-1 min-w-[160px]">
                    <button
                      onClick={() => handleMenuAction('more')}
                      className="w-full px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-50 flex items-center gap-2"
                    >
                      <ThumbsUp className="w-4 h-4" />
                      More like this
                    </button>
                    <button
                      onClick={() => handleMenuAction('less')}
                      className="w-full px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-50 flex items-center gap-2"
                    >
                      <ThumbsDown className="w-4 h-4" />
                      Less like this
                    </button>
                    <button
                      onClick={() => handleMenuAction('share')}
                      className="w-full px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-50 flex items-center gap-2"
                    >
                      <Share className="w-4 h-4" />
                      Share
                    </button>
                  </div>
                )}
              </div>
              <button
                onClick={onClose}
                className="p-2 hover:bg-gray-100 rounded-full transition-colors"
              >
                <X className="w-5 h-5 text-gray-500" />
              </button>
            </div>
          </div>

          {/* Tabs - only show when there are related articles */}
          {hasRelated && (
            <div className="px-6 flex border-t border-gray-100">
              <button
                onClick={() => setActiveTab('details')}
                className={`px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors ${
                  activeTab === 'details'
                    ? 'border-pink-500 text-pink-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700'
                }`}
              >
                Details
              </button>
              <button
                onClick={() => setActiveTab('related')}
                className={`px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors flex items-center gap-1.5 ${
                  activeTab === 'related'
                    ? 'border-pink-500 text-pink-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700'
                }`}
              >
                <Layers className="w-4 h-4" />
                Related Coverage
                <span className="ml-1 px-1.5 py-0.5 text-xs bg-gray-100 rounded-full">
                  {relatedArticles.length}
                </span>
              </button>
            </div>
          )}
        </div>

        {/* Content - Details Tab */}
        {activeTab === 'details' && (
        <div className="p-6">
          {/* Category badge */}
          {article.category && (
            <span className="inline-block bg-pink-100 text-pink-700 text-xs font-medium px-2 py-1 rounded mb-3">
              {article.category}
            </span>
          )}

          {/* Title */}
          <h1 className="text-xl font-bold text-gray-900 leading-tight">
            {article.title}
          </h1>

          {/* Source and date */}
          <div className="flex items-center gap-2 mt-3 text-sm text-gray-500">
            <Building2 className="w-4 h-4" />
            <span className="font-medium">{article.source?.name || 'Unknown source'}</span>
            <span className="text-gray-300">•</span>
            <Clock className="w-4 h-4" />
            <span>{formatDate(article.publication_date)}</span>
          </div>

          {/* Bias and factuality indicators */}
          {article.source && (article.source.bias || article.source.factuality) && (
            <div className="mt-4">
              <ArticleBiasIndicator
                bias={article.source.bias}
                factuality={article.source.factuality}
                credibility={article.source.credibility_rating}
                showLabels
                size="md"
              />
            </div>
          )}

          {/* Summary */}
          <div className="mt-6">
            <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-wide mb-2">Summary</h3>
            <p className="text-gray-700 leading-relaxed">
              {article.summary || 'No summary available.'}
            </p>
          </div>

          {/* Metadata Grid */}
          <div className="mt-6 grid grid-cols-2 gap-4">
            <MetadataItem
              icon={<TrendingUp className="w-4 h-4" />}
              label="Sentiment"
              value={article.sentiment}
              valueColor={getSentimentColor(article.sentiment)}
            />
            <MetadataItem
              icon={<Clock className="w-4 h-4" />}
              label="Time to Impact"
              value={article.time_to_impact}
            />
            {article.topic && (
              <MetadataItem
                label="Topic"
                value={article.topic}
              />
            )}
            {article.source?.credibility_rating && (
              <MetadataItem
                label="Credibility"
                value={article.source.credibility_rating}
              />
            )}
          </div>

          {/* Tags */}
          {article.tags && (Array.isArray(article.tags) ? article.tags.length > 0 : article.tags) && (
            <div className="mt-6">
              <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-wide mb-2">Tags</h3>
              <div className="flex flex-wrap gap-2">
                {(Array.isArray(article.tags)
                  ? article.tags
                  : String(article.tags).split(',').map(t => t.trim()).filter(Boolean)
                ).map((tag, i) => {
                  const isSignalTag = tag.startsWith('SIGNAL_');
                  const displayName = isSignalTag
                    ? tag.replace('SIGNAL_', '').replace(/_/g, ' ').split(' ')
                        .map(word => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
                        .join(' ')
                    : tag;

                  return (
                    <span
                      key={i}
                      className={`px-2 py-1 text-sm rounded inline-flex items-center gap-1 ${
                        isSignalTag
                          ? 'bg-pink-100 text-pink-700'
                          : 'bg-gray-100 text-gray-600'
                      }`}
                      title={isSignalTag ? `Matched by Research Agent: ${displayName}` : undefined}
                    >
                      {isSignalTag && <Bot className="w-3 h-3" />}
                      {displayName}
                    </span>
                  );
                })}
              </div>
            </div>
          )}

          {/* Action buttons */}
          <div className="mt-8 flex items-center gap-4">
            {(article.url || article.uri) && (
              <a
                href={article.url || article.uri}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 text-sm text-blue-600 hover:text-blue-700 font-medium transition-colors"
              >
                <ExternalLink className="w-3.5 h-3.5" />
                Read Original Article
              </a>
            )}

            <button
              onClick={handleAskAuspex}
              className="inline-flex items-center gap-1.5 text-sm text-pink-600 hover:text-pink-700 font-medium transition-colors"
            >
              <MessageSquare className="w-3.5 h-3.5" />
              Ask Auspex
            </button>
          </div>
        </div>
        )}

        {/* Content - Related Coverage Tab */}
        {activeTab === 'related' && hasRelated && (
          <div className="p-6">
            <div className="mb-4">
              <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-wide mb-1">
                Full Coverage
              </h3>
              <p className="text-xs text-gray-500">
                {relatedArticles.length + 1} sources reporting on this story
              </p>
            </div>

            {/* Primary article (current) */}
            <div className="mb-4 p-4 bg-pink-50 rounded-lg border border-pink-200">
              <div className="flex items-center gap-2 text-xs text-pink-600 mb-2">
                <span className="font-semibold">Primary Source</span>
                <span className="text-pink-400">•</span>
                <span>{article.source?.name}</span>
              </div>
              <h4 className="font-medium text-gray-900 mb-2">{article.title}</h4>
              {article.summary && (
                <p className="text-sm text-gray-600 line-clamp-3">{article.summary}</p>
              )}
            </div>

            {/* Related articles list */}
            <div className="space-y-3">
              {relatedArticles.map((related) => (
                <button
                  key={related.uri}
                  onClick={() => onRelatedArticleClick?.(related.uri)}
                  className="w-full text-left p-4 bg-gray-50 hover:bg-gray-100 rounded-lg border border-gray-200 hover:border-gray-300 transition-colors"
                >
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2 text-xs">
                      <span className="font-medium text-gray-700">{related.news_source}</span>
                      {related.publication_date && (
                        <>
                          <span className="text-gray-300">•</span>
                          <span className="text-gray-500">{formatRelativeTime(related.publication_date)}</span>
                        </>
                      )}
                    </div>
                    <ChevronRight className="w-4 h-4 text-gray-400" />
                  </div>
                  <h4 className="font-medium text-gray-900 mb-2 line-clamp-2">{related.title}</h4>
                  {related.summary && (
                    <p className="text-sm text-gray-600 line-clamp-2">{related.summary}</p>
                  )}
                  {related.similarity_score && (
                    <div className="mt-2 flex items-center gap-1 text-xs text-gray-400">
                      <span className="inline-block w-1.5 h-1.5 rounded-full bg-green-400"></span>
                      <span>{Math.round(related.similarity_score * 100)}% similar</span>
                    </div>
                  )}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </>
  );
}

interface MetadataItemProps {
  icon?: React.ReactNode;
  label: string;
  value?: string;
  valueColor?: string;
}

function MetadataItem({ icon, label, value, valueColor }: MetadataItemProps) {
  if (!value) return null;

  return (
    <div className="bg-gray-50 rounded-lg p-3">
      <div className="flex items-center gap-1.5 text-xs text-gray-500 mb-1">
        {icon}
        <span className="uppercase tracking-wide">{label}</span>
      </div>
      <div className={`font-medium ${valueColor || 'text-gray-900'}`}>
        {value}
      </div>
    </div>
  );
}

function getSentimentColor(sentiment?: string): string {
  if (!sentiment) return 'text-gray-900';
  const lower = sentiment.toLowerCase();
  if (lower === 'positive' || lower === 'bullish') return 'text-green-600';
  if (lower === 'negative' || lower === 'bearish') return 'text-red-600';
  if (lower === 'neutral') return 'text-gray-600';
  return 'text-gray-900';
}
