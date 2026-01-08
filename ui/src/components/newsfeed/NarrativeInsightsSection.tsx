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
  Loader2,
  Calendar,
  FileText,
  MessageSquare,
  Settings2,
  Download,
  Table,
} from 'lucide-react';
import { openAuspexWithQuery } from '../../utils/auspexEvents';
import { type ArticleTheme, type ThemeArticle } from '../../services/narrativeExplorerApi';
import { type NewsArticle } from '../../services/newsFeedApi';
import { Button } from '../ui/button';
import { Skeleton } from '../ui/skeleton';
import { ExportService } from '../../services/exportService';

interface NarrativeInsightsSectionProps {
  themes: ArticleTheme[];
  loading?: boolean;
  onArticleClick?: (article: NewsArticle) => void;
  currentTopic?: string;
  onOpenConfig?: () => void;
  model?: string;
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

export function NarrativeInsightsSection({ themes, loading, onArticleClick, currentTopic, onOpenConfig, model }: NarrativeInsightsSectionProps) {
  const [expandedCards, setExpandedCards] = useState<Set<number>>(new Set());
  const [showAll, setShowAll] = useState(false);
  const [showDownloadDropdown, setShowDownloadDropdown] = useState(false);

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
          <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100">Narratives</h2>
          <div className="flex-1" />
          {onOpenConfig && (
            <button
              onClick={onOpenConfig}
              className="p-1.5 rounded-md hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
              title="Configure Narratives"
            >
              <Settings2 className="w-4 h-4 text-gray-500" />
            </button>
          )}
        </div>
        <p className="text-sm text-gray-600 dark:text-gray-400">No recent narratives, click refresh</p>
      </section>
    );
  }

  return (
    <section className="mb-8">
      {/* Section Header */}
      <div className="flex items-center gap-2 mb-4">
        <Brain className="w-5 h-5 text-indigo-500" />
        <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100">Narratives</h2>
        <span className="text-sm text-gray-600 dark:text-gray-400 ml-2">
          {themes.length} theme{themes.length !== 1 ? 's' : ''} identified
        </span>
        <div className="flex-1" />

        {/* Download Button */}
        {themes.length > 0 && (
          <div className="relative">
            <button
              onClick={() => setShowDownloadDropdown(!showDownloadDropdown)}
              className="p-1.5 rounded-md hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
              title="Download narratives"
            >
              <Download className="w-4 h-4 text-gray-500" />
            </button>

            {showDownloadDropdown && (
              <>
                {/* Backdrop */}
                <div
                  className="fixed inset-0 z-10"
                  onClick={() => setShowDownloadDropdown(false)}
                />
                {/* Dropdown */}
                <div className="absolute right-0 top-full mt-1 w-48 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg z-20 py-1">
                  <button
                    onClick={() => {
                      ExportService.exportNarrativesMarkdown(themes, currentTopic, model);
                      setShowDownloadDropdown(false);
                    }}
                    className="w-full px-4 py-2 text-left text-sm hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors flex items-center gap-2"
                  >
                    <FileText className="w-4 h-4 text-gray-500" />
                    <span>Export as Markdown</span>
                  </button>
                  <button
                    onClick={() => {
                      ExportService.exportNarrativesCSV(themes);
                      setShowDownloadDropdown(false);
                    }}
                    className="w-full px-4 py-2 text-left text-sm hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors flex items-center gap-2"
                  >
                    <Table className="w-4 h-4 text-gray-500" />
                    <span>Export as CSV</span>
                  </button>
                </div>
              </>
            )}
          </div>
        )}

        {onOpenConfig && (
          <button
            onClick={onOpenConfig}
            className="p-1.5 rounded-md hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
            title="Configure Narratives"
          >
            <Settings2 className="w-4 h-4 text-gray-500" />
          </button>
        )}
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
  // Build Auspex research prompt
  const buildResearchPrompt = () => {
    const topicArea = currentTopic || 'AI and Machine Learning';
    const detailedArticles = theme.articles?.slice(0, 15).map((article, idx) => {
      const date = article.publication_date
        ? new Date(article.publication_date).toLocaleDateString()
        : 'Unknown date';
      const brief = (article.summary || '').slice(0, 140).replace(/\n+/g, ' ');
      return `${idx + 1}. ${article.title} (${article.news_source || 'Unknown'}, ${date})\n   URI: ${article.uri}\n   Brief: ${brief}${brief.length >= 140 ? '...' : ''}`;
    }).join('\n') || '(no articles in theme)';

    const additionalUris = theme.articles?.slice(15, 50).map(a => `- ${a.title} — ${a.uri}`).join('\n') || '';
    const keyEntitiesText = theme.key_entities?.length
      ? `Key Entities: ${theme.key_entities.slice(0, 10).join(', ')}`
      : '';

    return `Conduct comprehensive analysis of the theme "${theme.theme_name}" identified from recent ${topicArea} articles.

THEME METADATA:
${theme.sentiment ? `Sentiment: ${theme.sentiment}` : ''}
${theme.confidence ? `Confidence: ${Math.round(theme.confidence)}%` : ''}
${theme.article_count ? `Articles: ${theme.article_count}` : ''}
${theme.source_count ? `Sources: ${theme.source_count}` : ''}
${keyEntitiesText}

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
2. Consider the theme sentiment (${theme.sentiment || 'unknown'}) and ${keyEntitiesText ? 'key entities' : 'entities involved'}.
3. Identify trends, relationships, and implications grounded in the dataset.
4. Suggest exactly 2-3 follow-up questions users could ask to expand analysis.
5. Provide strategic recommendations for decision-makers.

Write follow-up questions as natural language that users would ask, not as technical function calls.`;
  };

  return (
    <div className={`transition-all ${expanded ? 'bg-gray-50 dark:bg-gray-800/50' : ''}`}>
      {/* Header: Articles label + See More/Less toggle */}
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-gray-500 dark:text-gray-400">
          Articles
        </span>
        <button
          onClick={onToggleExpand}
          className="text-sm text-blue-600 hover:text-blue-700 dark:text-blue-400 dark:hover:text-blue-300 font-medium flex items-center gap-1"
        >
          {expanded ? (
            <>
              <ChevronUp className="w-4 h-4" />
              See Less
            </>
          ) : (
            <>
              <ChevronDown className="w-4 h-4" />
              See More
            </>
          )}
        </button>
      </div>

      {/* Theme Name */}
      <h3 className="font-bold text-gray-900 dark:text-gray-100 text-base mb-2 mt-3">
        {theme.theme_name}
      </h3>

      {/* Theme Summary / Description */}
      <p className={`text-sm text-gray-700 dark:text-gray-300 ${!expanded ? 'line-clamp-4' : ''}`}>
        {theme.theme_summary || theme.description}
      </p>

      {/* Expanded: Articles in Theme */}
      {expanded && theme.articles && theme.articles.length > 0 && (
        <div className="mt-4">
          <h4 className="text-sm font-medium text-gray-800 dark:text-gray-200 pb-3 border-b border-gray-300 dark:border-gray-600">
            Articles in Theme
          </h4>
          <div>
            {theme.articles.slice(0, 8).map((article, i) => (
              <div key={i} className="border-b border-gray-300 dark:border-gray-600 last:border-b-0">
                <ThemeArticleRow
                  article={article}
                  onClick={onArticleClick ? () => onArticleClick(themeArticleToNewsArticle(article)) : undefined}
                />
              </div>
            ))}
          </div>
          {theme.articles.length > 8 && (
            <p className="text-sm text-gray-600 dark:text-gray-400 pt-3">
              +{theme.articles.length - 8} more articles
            </p>
          )}

          {/* Ask Auspex button for the whole theme */}
          <button
            onClick={() => openAuspexWithQuery(buildResearchPrompt())}
            className="mt-4 inline-flex items-center gap-1.5 text-sm text-pink-600 dark:text-pink-400 hover:text-pink-700 dark:hover:text-pink-300 font-medium"
          >
            <MessageSquare className="w-4 h-4" />
            Ask Auspex about this theme
          </button>
        </div>
      )}
    </div>
  );
}

// New article row component matching mockup design
function ThemeArticleRow({
  article,
  onClick
}: {
  article: ThemeArticle;
  onClick?: () => void;
}) {
  // Format date as DD.MM.YYYY
  const formattedDate = article.publication_date
    ? (() => {
        const d = new Date(article.publication_date);
        const day = d.getDate().toString().padStart(2, '0');
        const month = (d.getMonth() + 1).toString().padStart(2, '0');
        const year = d.getFullYear();
        return `${day}.${month}.${year}`;
      })()
    : null;

  return (
    <div className="py-3 first:pt-0">
      {/* Date row with external link icon on right */}
      <div className="flex items-center justify-between mb-1">
        {formattedDate && (
          <div className="flex items-center gap-1.5">
            <Calendar className="w-3.5 h-3.5 text-gray-500 dark:text-gray-400" />
            <span className="text-xs text-gray-600 dark:text-gray-300">{formattedDate}</span>
          </div>
        )}
        <a
          href={article.uri}
          target="_blank"
          rel="noopener noreferrer"
          className="text-gray-500 hover:text-blue-600 dark:text-gray-400 dark:hover:text-blue-400"
          onClick={(e) => e.stopPropagation()}
        >
          <ExternalLink className="w-4 h-4" />
        </a>
      </div>

      {/* Title */}
      <p
        className="text-sm text-gray-900 dark:text-gray-100 font-medium cursor-pointer hover:text-blue-600 dark:hover:text-blue-400"
        onClick={onClick}
      >
        {article.title}
      </p>

      {/* Source link */}
      <a
        href={article.uri}
        target="_blank"
        rel="noopener noreferrer"
        className="text-xs text-blue-600 dark:text-blue-400 hover:underline mt-1 inline-block"
        onClick={(e) => e.stopPropagation()}
      >
        {article.news_source || 'Source'}
      </a>
    </div>
  );
}

