/**
 * Narrative Insights Section - Article Theme Display
 * Shows AI-identified narrative patterns, themes, and article clustering
 */

import { useState } from 'react';
import {
  Brain,
  ChevronDown,
  ChevronUp,
  ExternalLink,
  Search,
  RefreshCw,
  Tag,
  Lightbulb,
  Loader2
} from 'lucide-react';
import { type ArticleTheme, type ThemeArticle } from '../../services/narrativeExplorerApi';
import { type NewsArticle } from '../../services/newsFeedApi';
import { Card, CardContent } from '../ui/card';
import { Button } from '../ui/button';
import { Skeleton } from '../ui/skeleton';

interface NarrativeInsightsSectionProps {
  themes: ArticleTheme[];
  loading?: boolean;
  onArticleClick?: (article: NewsArticle) => void;
  currentTopic?: string;
}

// Convert ThemeArticle to NewsArticle for detail panel
function themeArticleToNewsArticle(article: ThemeArticle): NewsArticle {
  // Use short_summary (from backend) or summary as fallback
  const summaryText = article.short_summary || article.summary || '';
  return {
    uri: article.uri,
    title: article.title,
    summary: summaryText,
    url: article.uri, // Use uri as fallback URL
    publication_date: article.publication_date,
    source: {
      name: article.news_source || 'Unknown Source',
    },
    tags: [],
  };
}

export function NarrativeInsightsSection({ themes, loading, onArticleClick, currentTopic }: NarrativeInsightsSectionProps) {
  const [expandedCards, setExpandedCards] = useState<Set<number>>(new Set());
  const [showAll, setShowAll] = useState(false);

  const displayedThemes = showAll ? themes : themes.slice(0, 6);

  const toggleExpand = (index: number) => {
    setExpandedCards(prev => {
      const next = new Set(prev);
      if (next.has(index)) {
        next.delete(index);
      } else {
        next.add(index);
      }
      return next;
    });
  };

  // Empty state - simple inline text
  if (!themes.length && !loading) {
    return (
      <section className="mb-6">
        <div className="flex items-center gap-2 mb-2">
          <Brain className="w-5 h-5 text-indigo-500" />
          <h2 className="text-xl font-semibold text-gray-900">Narratives</h2>
        </div>
        <p className="text-sm text-gray-600">No recent narratives, click refresh</p>
      </section>
    );
  }

  return (
    <section className="mb-8">
      {/* Section Header */}
      <div className="flex items-center gap-2 mb-4">
        <Brain className="w-5 h-5 text-indigo-500" />
        <h2 className="text-xl font-semibold text-gray-900">Narratives</h2>
        <span className="text-sm text-gray-600 ml-2">
          {themes.length} theme{themes.length !== 1 ? 's' : ''} identified
        </span>
      </div>

      {/* Loading State */}
      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-64 rounded-lg" />
          ))}
        </div>
      ) : (
        <>
          {/* Themes Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {displayedThemes.map((theme, i) => (
              <ThemeCard
                key={i}
                theme={theme}
                expanded={expandedCards.has(i)}
                onToggleExpand={() => toggleExpand(i)}
                onArticleClick={onArticleClick}
                currentTopic={currentTopic}
              />
            ))}
          </div>

          {/* Show More/Less Button */}
          {themes.length > 6 && (
            <div className="mt-4 text-center">
              <Button
                variant="ghost"
                onClick={() => setShowAll(!showAll)}
                className="gap-2"
              >
                {showAll ? (
                  <>
                    <ChevronUp className="w-4 h-4" />
                    Show Less
                  </>
                ) : (
                  <>
                    <ChevronDown className="w-4 h-4" />
                    Show {themes.length - 6} More Narratives
                  </>
                )}
              </Button>
            </div>
          )}
        </>
      )}
    </section>
  );
}

interface ThemeCardProps {
  theme: ArticleTheme;
  expanded: boolean;
  onToggleExpand: () => void;
  onArticleClick?: (article: NewsArticle) => void;
  currentTopic?: string;
}

function ThemeCard({ theme, expanded, onToggleExpand, onArticleClick, currentTopic }: ThemeCardProps) {
  const sentimentColors: Record<string, string> = {
    'positive': 'bg-green-100 text-green-700',
    'negative': 'bg-red-100 text-red-700',
    'neutral': 'bg-gray-100 text-gray-700',
    'mixed': 'bg-yellow-100 text-yellow-700',
  };

  return (
    <Card className="overflow-hidden hover:shadow-md transition-shadow">
      <CardContent className="p-0">
        {/* Theme indicator stripe */}
        <div className="h-1 bg-gradient-to-r from-indigo-500 to-purple-500" />

        <div className="p-4">
          {/* Header */}
          <div className="flex items-start justify-between gap-2 mb-2">
            <div className="flex items-center gap-2">
              {theme.sentiment && (
                <span className={`text-xs px-2 py-0.5 rounded ${sentimentColors[theme.sentiment.toLowerCase()] || 'bg-gray-100 text-gray-700'}`}>
                  {theme.sentiment}
                </span>
              )}
            </div>
            <span className="text-xs text-gray-600">
              {theme.article_count} article{theme.article_count !== 1 ? 's' : ''}
            </span>
          </div>

          {/* Theme Name */}
          <h3 className="font-semibold text-gray-900 text-sm mb-2">
            {theme.theme_name}
          </h3>

          {/* Theme Summary / Description - always show full */}
          <p className="text-sm text-gray-600">
            {theme.theme_summary || theme.description}
          </p>

          {/* Source Metrics (if available) */}
          {(theme.confidence || theme.source_count) && (
            <div className="flex items-center gap-3 mt-2 text-xs text-gray-600">
              {theme.confidence && (
                <span className="flex items-center gap-1">
                  <span className="font-medium">{Math.round(theme.confidence)}%</span> confidence
                </span>
              )}
              {theme.source_count && (
                <span>{theme.source_count} source{theme.source_count !== 1 ? 's' : ''}</span>
              )}
            </div>
          )}

          {/* Key Entities */}
          {theme.key_entities && theme.key_entities.length > 0 && (
            <div className="mt-3">
              <div className="flex items-center gap-1 mb-1">
                <Tag className="w-3 h-3 text-gray-500" />
                <span className="text-xs text-gray-600 font-medium">Key Entities</span>
              </div>
              <div className="flex flex-wrap gap-1">
                {theme.key_entities.slice(0, expanded ? undefined : 4).map((entity, i) => (
                  <span
                    key={i}
                    className="text-xs bg-purple-50 text-purple-600 px-2 py-0.5 rounded"
                  >
                    {entity}
                  </span>
                ))}
                {!expanded && theme.key_entities.length > 4 && (
                  <span className="text-xs text-gray-600">
                    +{theme.key_entities.length - 4} more
                  </span>
                )}
              </div>
            </div>
          )}

          {/* Expanded: Articles List */}
          {expanded && theme.articles && theme.articles.length > 0 && (
            <div className="mt-4 pt-3 border-t border-gray-100">
              <h4 className="text-xs font-semibold text-gray-600 uppercase tracking-wide mb-2">
                Articles in Theme
              </h4>
              <div className="space-y-2">
                {theme.articles.slice(0, 5).map((article, i) => (
                  <ThemeArticleLink
                    key={i}
                    article={article}
                    themeSentiment={theme.sentiment}
                    themeConfidence={theme.confidence}
                    onClick={onArticleClick ? () => onArticleClick(themeArticleToNewsArticle(article)) : undefined}
                  />
                ))}
                {theme.articles.length > 5 && (
                  <p className="text-xs text-gray-600">
                    +{theme.articles.length - 5} more articles
                  </p>
                )}
              </div>
            </div>
          )}

          {/* Research Suggestions */}
          {expanded && theme.research_suggestions && theme.research_suggestions.length > 0 && (
            <div className="mt-4 pt-3 border-t border-gray-100">
              <div className="flex items-center gap-1 mb-2">
                <Lightbulb className="w-3 h-3 text-yellow-500" />
                <span className="text-xs text-gray-600 font-medium">Research Suggestions</span>
              </div>
              <ul className="space-y-1">
                {theme.research_suggestions.map((suggestion, i) => (
                  <li key={i} className="text-xs text-gray-600 flex items-start gap-1">
                    <span className="text-gray-500">•</span>
                    {suggestion}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Expand/Collapse button */}
          <button
            onClick={onToggleExpand}
            className="mt-3 text-xs text-indigo-600 hover:text-indigo-700 font-medium flex items-center gap-1"
          >
            {expanded ? (
              <>
                <ChevronUp className="w-3 h-3" />
                Show less
              </>
            ) : (
              <>
                <ChevronDown className="w-3 h-3" />
                Show more
              </>
            )}
          </button>

          {/* Action buttons */}
          {expanded && (
            <div className="mt-3 pt-3 border-t border-gray-100 flex gap-2">
              <Button
                variant="outline"
                size="sm"
                className="text-xs gap-1"
                onClick={() => {
                  // Build comprehensive research prompt with dataset context
                  const topicArea = currentTopic || 'AI and Machine Learning';

                  // Build article context from theme articles
                  const detailedArticles = theme.articles?.slice(0, 15).map((article, idx) => {
                    const date = article.publication_date
                      ? new Date(article.publication_date).toLocaleDateString()
                      : 'Unknown date';
                    const brief = (article.summary || '').slice(0, 140).replace(/\n+/g, ' ');
                    return `${idx + 1}. ${article.title} (${article.news_source || 'Unknown'}, ${date})\n   URI: ${article.uri}\n   Brief: ${brief}${brief.length >= 140 ? '...' : ''}`;
                  }).join('\n') || '(no articles in theme)';

                  const additionalUris = theme.articles?.slice(15, 50).map(a => `- ${a.title} — ${a.uri}`).join('\n') || '';

                  const researchPrompt = `Conduct comprehensive analysis of the theme "${theme.theme_name}" identified from recent ${topicArea} articles.

CONTEXT FROM ARTICLE ANALYSIS:
This theme emerged from AI analysis of recent articles in the news feed.

DATASET CONTEXT (top matches):
${detailedArticles}

Additional relevant articles (compact list):
${additionalUris}

RESEARCH FOCUS: "${theme.theme_name}"
TOPIC AREA: "${topicArea}"

Please use your tools to:
1. Start with the dataset items above; synthesize cross-article findings and cite URIs.
2. Identify trends, entities, relationships, and implications grounded in the dataset.
3. Suggest exactly 2-3 follow-up questions users could ask to expand analysis.
4. Provide strategic recommendations for decision-makers.

Write follow-up questions as natural language that users would ask, not as technical function calls.`;

                  // Open Auspex floating chat and pre-fill the comprehensive query
                  const floatingChat = (window as any).floatingChatInstance;
                  if (floatingChat && floatingChat.modalInstance) {
                    floatingChat.modalInstance.show();
                    setTimeout(() => {
                      const input = document.getElementById('floatingChatInput') as HTMLTextAreaElement;
                      if (input) {
                        input.value = researchPrompt;
                        input.focus();
                      }
                    }, 300);
                  } else {
                    const chatBtn = document.getElementById('floatingChatBtn');
                    if (chatBtn) {
                      chatBtn.click();
                      setTimeout(() => {
                        const input = document.getElementById('floatingChatInput') as HTMLTextAreaElement;
                        if (input) {
                          input.value = researchPrompt;
                          input.focus();
                        }
                      }, 300);
                    }
                  }
                }}
              >
                <Search className="w-3 h-3" />
                Research with Auspex
              </Button>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

function ThemeArticleLink({
  article,
  themeSentiment,
  themeConfidence,
  onClick
}: {
  article: ThemeArticle;
  themeSentiment?: string;
  themeConfidence?: number;
  onClick?: () => void;
}) {
  const [showTooltip, setShowTooltip] = useState(false);
  const tooltipContent = article.short_summary || article.summary;

  const sentimentColors: Record<string, string> = {
    'positive': 'bg-green-100 text-green-700',
    'negative': 'bg-red-100 text-red-700',
    'neutral': 'bg-gray-100 text-gray-700',
    'mixed': 'bg-yellow-100 text-yellow-700',
  };

  const handleClick = (e: React.MouseEvent) => {
    if (onClick) {
      e.preventDefault();
      onClick();
    }
  };

  return (
    <div
      className="relative"
      onMouseEnter={() => setShowTooltip(true)}
      onMouseLeave={() => setShowTooltip(false)}
    >
      <a
        href={article.uri}
        target={onClick ? undefined : "_blank"}
        rel={onClick ? undefined : "noopener noreferrer"}
        onClick={handleClick}
        className="block p-2 rounded bg-gray-50 hover:bg-gray-100 transition-colors cursor-pointer"
      >
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            <p className="text-xs font-medium text-gray-900 line-clamp-1">
              {article.title}
            </p>
            <p className="text-xs text-gray-600 mt-0.5">
              {article.news_source}
              {article.publication_date && ` • ${new Date(article.publication_date).toLocaleDateString()}`}
            </p>
          </div>
          <ExternalLink className="w-3 h-3 text-gray-500 shrink-0" />
        </div>
      </a>

      {/* Hover tooltip with full summary and theme metadata */}
      {showTooltip && tooltipContent && (
        <div className="absolute left-0 bottom-full mb-1 z-50 w-80 p-3 bg-white rounded-lg shadow-lg border border-gray-200 pointer-events-none">
          <p className="text-xs text-gray-600 leading-relaxed">
            {tooltipContent}
          </p>
          <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
            <span className="font-medium text-gray-700">{article.news_source}</span>
            {article.publication_date && (
              <>
                <span className="text-gray-400">•</span>
                <span className="text-gray-500">{new Date(article.publication_date).toLocaleDateString()}</span>
              </>
            )}
            {themeSentiment && (
              <>
                <span className="text-gray-400">•</span>
                <span className={`px-1.5 py-0.5 rounded ${sentimentColors[themeSentiment.toLowerCase()] || 'bg-gray-100 text-gray-700'}`}>
                  {themeSentiment}
                </span>
              </>
            )}
            {themeConfidence && (
              <>
                <span className="text-gray-400">•</span>
                <span className="text-indigo-600">{Math.round(themeConfidence)}% confidence</span>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
