/**
 * Briefing Section - "Your Briefing" executive intelligence area
 * Displays rich executive briefing data with takeaways, strategic relevance,
 * indicators, and action items
 */

import { useState } from 'react';
import {
  Sparkles,
  ExternalLink,
  Clock,
  TrendingUp,
  TrendingDown,
  AlertTriangle,
  Target,
  Zap,
  ChevronDown,
  ChevronUp,
  Building2,
  Star,
  StarOff,
  MessageSquare
} from 'lucide-react';
import { type NewsArticle, type SixArticlesReport, type TopStory } from '../../services/newsFeedApi';
import { Skeleton } from '../ui/skeleton';

interface BriefingSectionProps {
  articles: NewsArticle[];
  sixArticles: SixArticlesReport | null;
  loadingSixArticles: boolean;
  starredArticles: string[];
  onStar: (uri: string) => void;
  onUnstar: (uri: string) => void;
  onArticleClick?: (article: NewsArticle) => void;
}

// Get color for risk/opportunity indicator
function getRiskOpportunityStyle(value?: string): { bg: string; text: string; icon: React.ReactNode } {
  if (!value) return { bg: 'bg-gray-100', text: 'text-gray-600', icon: null };
  const lower = value.toLowerCase();
  if (lower === 'opportunity') return { bg: 'bg-green-100', text: 'text-green-700', icon: <TrendingUp className="w-3 h-3" /> };
  if (lower === 'risk') return { bg: 'bg-red-100', text: 'text-red-700', icon: <TrendingDown className="w-3 h-3" /> };
  return { bg: 'bg-amber-100', text: 'text-amber-700', icon: <AlertTriangle className="w-3 h-3" /> };
}

// Get color for signal strength
function getSignalStrengthStyle(value?: string): { bg: string; text: string } {
  if (!value) return { bg: 'bg-gray-100', text: 'text-gray-600' };
  const lower = value.toLowerCase();
  if (lower === 'strong') return { bg: 'bg-pink-100', text: 'text-pink-700' };
  if (lower === 'moderate') return { bg: 'bg-blue-100', text: 'text-blue-700' };
  return { bg: 'bg-gray-100', text: 'text-gray-600' };
}

// Get time horizon style
function getTimeHorizonStyle(value?: string): { bg: string; text: string } {
  if (!value) return { bg: 'bg-gray-100', text: 'text-gray-600' };
  const lower = value.toLowerCase();
  if (lower === 'immediate') return { bg: 'bg-red-50', text: 'text-red-600' };
  if (lower === 'medium') return { bg: 'bg-amber-50', text: 'text-amber-600' };
  return { bg: 'bg-green-50', text: 'text-green-600' };
}

// Get category badge style
function getCategoryStyle(category?: string): { bg: string; text: string } {
  if (!category) return { bg: 'bg-gray-100', text: 'text-gray-600' };
  const lower = category.toLowerCase();
  const styles: Record<string, { bg: string; text: string }> = {
    'policy': { bg: 'bg-purple-100', text: 'text-purple-700' },
    'market': { bg: 'bg-emerald-100', text: 'text-emerald-700' },
    'tech': { bg: 'bg-blue-100', text: 'text-blue-700' },
    'workforce': { bg: 'bg-orange-100', text: 'text-orange-700' },
    'security': { bg: 'bg-red-100', text: 'text-red-700' },
    'society': { bg: 'bg-teal-100', text: 'text-teal-700' },
  };
  return styles[lower] || { bg: 'bg-gray-100', text: 'text-gray-600' };
}

export function BriefingSection({
  articles,
  sixArticles,
  loadingSixArticles,
  starredArticles,
  onStar,
  onUnstar,
  onArticleClick,
}: BriefingSectionProps) {
  const [expandedIndex, setExpandedIndex] = useState<number | null>(null);

  // Get top stories from six articles report
  const topStories = sixArticles?.articles || [];
  // Check for executive data - handle flat structure where fields are directly on story
  const hasExecutiveData = topStories.length > 0 && topStories.some(s => {
    const story = s as any;
    return story.executive_takeaway || story.strategic_relevance || story.time_horizon;
  });

  // Debug logging
  console.log('[BriefingSection] Raw sixArticles:', sixArticles);
  console.log('[BriefingSection] topStories count:', topStories.length);
  console.log('[BriefingSection] hasExecutiveData:', hasExecutiveData);
  if (topStories.length > 0) {
    const first = topStories[0] as any;
    console.log('[BriefingSection] First story:', first);
    console.log('[BriefingSection] First story executive_takeaway:', first.executive_takeaway);
    console.log('[BriefingSection] First story strategic_relevance:', first.strategic_relevance);
  }

  return (
    <section className="mb-8">
      {/* Section Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Sparkles className="w-5 h-5 text-pink-500" />
          <h2 className="text-xl font-semibold text-gray-900">Your Briefing</h2>
          {sixArticles?.generated_at && (
            <span className="text-xs text-gray-600 ml-2">
              Updated {new Date(sixArticles.generated_at).toLocaleTimeString()}
            </span>
          )}
        </div>
      </div>

      {/* Executive Summary */}
      {sixArticles?.executive_summary && (
        <div className="mb-6 p-4 bg-gradient-to-r from-pink-50 to-purple-50 rounded-lg border border-pink-100">
          <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-wide mb-2">
            Executive Summary
          </h3>
          <p className="text-gray-700 leading-relaxed">
            {sixArticles.executive_summary}
          </p>
        </div>
      )}

      {/* Loading State */}
      {loadingSixArticles && !sixArticles ? (
        <div className="space-y-4">
          <Skeleton className="h-48 rounded-lg" />
          <Skeleton className="h-48 rounded-lg" />
          <Skeleton className="h-48 rounded-lg" />
        </div>
      ) : topStories.length > 0 ? (
        /* Executive Briefing Cards - always show if we have topStories */
        <div className="space-y-4">
          {topStories.map((story, index) => {
            const storyAny = story as any;
            const storyUri = storyAny.url || storyAny.uri || storyAny.primary_article?.uri || `story-${index}`;
            return (
              <BriefingCard
                key={storyUri}
                story={story}
                index={index}
                isExpanded={expandedIndex === index}
                onToggle={() => setExpandedIndex(expandedIndex === index ? null : index)}
                isStarred={starredArticles.includes(storyUri)}
                onStar={onStar}
                onUnstar={onUnstar}
              />
            );
          })}
        </div>
      ) : (
        /* Fallback to simple article list if no six articles data */
        <div className="space-y-3">
          {articles.slice(0, 6).map((article) => (
            <div
              key={article.uri}
              className="p-4 bg-white border border-gray-200 rounded-lg hover:shadow-md transition-shadow cursor-pointer"
              onClick={() => onArticleClick?.(article)}
            >
              <h3 className="font-medium text-gray-900">{article.title}</h3>
              <p className="text-sm text-gray-600 mt-1">{article.source?.name}</p>
            </div>
          ))}
        </div>
      )}

      {/* Key Themes */}
      {sixArticles?.key_themes && sixArticles.key_themes.length > 0 && (
        <div className="mt-6 p-4 bg-gray-50 rounded-lg">
          <h3 className="text-sm font-semibold text-gray-600 uppercase tracking-wide mb-3">
            Key Themes
          </h3>
          <div className="flex flex-wrap gap-2">
            {sixArticles.key_themes.map((theme, i) => (
              <span
                key={i}
                className="text-sm bg-white text-gray-700 px-3 py-1.5 rounded-full border border-gray-200"
              >
                {theme}
              </span>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

/**
 * Individual briefing card with executive intelligence
 */
interface BriefingCardProps {
  story: TopStory;
  index: number;
  isExpanded: boolean;
  onToggle: () => void;
  isStarred: boolean;
  onStar: (uri: string) => void;
  onUnstar: (uri: string) => void;
}

function BriefingCard({ story, index, isExpanded, onToggle, isStarred, onStar, onUnstar }: BriefingCardProps) {
  // Handle both nested (primary_article) and flat data structures
  const storyData = story as any; // Allow flexible access

  // Debug: log what we receive
  console.log(`[BriefingCard ${index}] storyData:`, storyData);
  console.log(`[BriefingCard ${index}] title:`, storyData.title);
  console.log(`[BriefingCard ${index}] executive_takeaway:`, storyData.executive_takeaway);
  console.log(`[BriefingCard ${index}] category:`, storyData.category);

  const riskStyle = getRiskOpportunityStyle(storyData.risk_opportunity);
  const signalStyle = getSignalStrengthStyle(storyData.signal_strength);
  const timeStyle = getTimeHorizonStyle(storyData.time_horizon);
  const categoryStyle = getCategoryStyle(storyData.category);

  // Get URL - handle both flat and nested structures
  const articleUrl = storyData.url || storyData.primary_article?.url || storyData.primary_article?.uri || '';
  const articleUri = storyData.url || storyData.primary_article?.uri || '';

  // Get display values - handle both structures
  const displayTitle = storyData.title || storyData.headline || storyData.primary_article?.title || 'Untitled';
  const displaySource = storyData.source || storyData.primary_article?.source?.name || '';
  const displayDate = storyData.date || storyData.primary_article?.publication_date || '';
  const displaySummary = storyData.summary || storyData.primary_article?.summary || '';
  const displayScores = storyData.scores || {};
  const executiveActions = Array.isArray(storyData.executive_action)
    ? storyData.executive_action
    : (storyData.executive_action ? [storyData.executive_action] : []);

  console.log(`[BriefingCard ${index}] displayTitle:`, displayTitle);
  console.log(`[BriefingCard ${index}] displaySource:`, displaySource);
  console.log(`[BriefingCard ${index}] displaySummary:`, displaySummary?.substring(0, 50));

  const handleStarClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (isStarred) {
      onUnstar(articleUri);
    } else {
      onStar(articleUri);
    }
  };

  const handleAskAuspex = (e: React.MouseEvent) => {
    e.stopPropagation();
    // Open Auspex floating chat and pre-fill with article details
    const floatingChat = (window as any).floatingChatInstance;
    const prompt = `Analyze this article: "${displayTitle}"\n\nExecutive Takeaway: ${storyData.executive_takeaway || 'N/A'}\n\nStrategic Relevance: ${storyData.strategic_relevance || 'N/A'}`;

    if (floatingChat && floatingChat.modalInstance) {
      floatingChat.modalInstance.show();
      setTimeout(() => {
        const input = document.getElementById('floatingChatInput') as HTMLTextAreaElement;
        if (input) {
          input.value = prompt;
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
            input.value = prompt;
            input.focus();
          }
        }, 300);
      }
    }
  };

  return (
    <article className="bg-white border border-gray-200 rounded-lg overflow-hidden hover:shadow-md transition-shadow">
      {/* Header - Always visible */}
      <div
        className="p-5 cursor-pointer"
        onClick={onToggle}
      >
        <div className="flex items-start justify-between gap-4">
          <div className="flex-1">
            {/* Category and indicators row */}
            <div className="flex flex-wrap items-center gap-2 mb-2">
              {storyData.category && (
                <span className={`text-xs font-medium px-2 py-0.5 rounded ${categoryStyle.bg} ${categoryStyle.text} uppercase`}>
                  {storyData.category}
                </span>
              )}
              {displayScores.overall && (
                <span className="text-xs font-bold text-pink-600 bg-pink-50 px-2 py-0.5 rounded">
                  Score: {displayScores.overall}/5
                </span>
              )}
            </div>

            {/* Title */}
            <h3 className="text-lg font-semibold text-gray-900 leading-tight">
              {displayTitle}
            </h3>

            {/* Source and date */}
            <div className="flex items-center gap-2 mt-2 text-sm text-gray-600">
              <Building2 className="w-3.5 h-3.5" />
              <span>{displaySource}</span>
              {displayDate && (
                <>
                  <span className="text-gray-400">•</span>
                  <span>{displayDate}</span>
                </>
              )}
            </div>

            {/* Executive Takeaway - Always visible */}
            {storyData.executive_takeaway && (
              <div className="mt-3 p-3 bg-pink-50 rounded-lg border-l-4 border-pink-400">
                <p className="text-sm font-medium text-gray-800">
                  {storyData.executive_takeaway}
                </p>
              </div>
            )}
          </div>

          {/* Right side - indicators and expand */}
          <div className="flex flex-col items-end gap-2">
            <button
              onClick={handleStarClick}
              className="p-1.5 hover:bg-gray-100 rounded-full transition-colors"
            >
              {isStarred ? (
                <Star className="w-4 h-4 text-yellow-500 fill-yellow-500" />
              ) : (
                <StarOff className="w-4 h-4 text-gray-400" />
              )}
            </button>

            {/* Executive Indicators */}
            <div className="flex flex-col gap-1 items-end">
              {storyData.time_horizon && (
                <span className={`text-xs px-2 py-0.5 rounded ${timeStyle.bg} ${timeStyle.text}`}>
                  <Clock className="w-3 h-3 inline mr-1" />
                  {storyData.time_horizon}
                </span>
              )}
              {storyData.risk_opportunity && (
                <span className={`text-xs px-2 py-0.5 rounded flex items-center gap-1 ${riskStyle.bg} ${riskStyle.text}`}>
                  {riskStyle.icon}
                  {storyData.risk_opportunity}
                </span>
              )}
              {storyData.signal_strength && (
                <span className={`text-xs px-2 py-0.5 rounded ${signalStyle.bg} ${signalStyle.text}`}>
                  <Zap className="w-3 h-3 inline mr-1" />
                  {storyData.signal_strength}
                </span>
              )}
            </div>

            <button className="p-1 text-gray-400 hover:text-gray-600">
              {isExpanded ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
            </button>
          </div>
        </div>
      </div>

      {/* Expanded Content */}
      {isExpanded && (
        <div className="px-5 pb-5 border-t border-gray-100 pt-4">
          {/* Summary */}
          {displaySummary && (
            <div className="mb-4">
              <h4 className="text-sm font-semibold text-gray-600 uppercase tracking-wide mb-2">
                Summary
              </h4>
              <p className="text-gray-700 leading-relaxed">
                {displaySummary}
              </p>
            </div>
          )}

          {/* Strategic Relevance */}
          {storyData.strategic_relevance && (
            <div className="mb-4 p-4 bg-blue-50 rounded-lg">
              <h4 className="text-sm font-semibold text-blue-700 uppercase tracking-wide mb-2 flex items-center gap-1">
                <Target className="w-4 h-4" />
                Strategic Relevance
              </h4>
              <p className="text-gray-700 leading-relaxed">
                {storyData.strategic_relevance}
              </p>
            </div>
          )}

          {/* Executive Actions */}
          {executiveActions.length > 0 && (
            <div className="mb-4">
              <h4 className="text-sm font-semibold text-gray-600 uppercase tracking-wide mb-2">
                Executive Actions
              </h4>
              <ul className="space-y-2">
                {executiveActions.map((action: string, i: number) => (
                  <li key={i} className="flex items-start gap-2 text-gray-700">
                    <span className="text-pink-500 mt-1">→</span>
                    <span>{action}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Scores breakdown (if available) */}
          {displayScores && Object.keys(displayScores).length > 1 && (
            <div className="mb-4">
              <h4 className="text-sm font-semibold text-gray-600 uppercase tracking-wide mb-2">
                Score Breakdown
              </h4>
              <div className="grid grid-cols-3 md:grid-cols-5 gap-2">
                {displayScores.relevance !== undefined && (
                  <ScorePill label="Relevance" value={displayScores.relevance} />
                )}
                {displayScores.impact !== undefined && (
                  <ScorePill label="Impact" value={displayScores.impact} />
                )}
                {displayScores.actionability !== undefined && (
                  <ScorePill label="Actionability" value={displayScores.actionability} />
                )}
                {displayScores.timeliness !== undefined && (
                  <ScorePill label="Timeliness" value={displayScores.timeliness} />
                )}
                {displayScores.credibility !== undefined && (
                  <ScorePill label="Credibility" value={displayScores.credibility} />
                )}
              </div>
            </div>
          )}

          {/* Action Links */}
          <div className="flex items-center gap-4">
            {articleUrl && (
              <a
                href={articleUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 text-sm text-pink-600 hover:text-pink-700 font-medium transition-colors"
              >
                <ExternalLink className="w-3.5 h-3.5" />
                Read Original Article
              </a>
            )}
            <button
              onClick={handleAskAuspex}
              className="inline-flex items-center gap-1.5 text-sm text-gray-500 hover:text-pink-600 transition-colors"
            >
              <MessageSquare className="w-3.5 h-3.5" />
              Ask Auspex
            </button>
          </div>
        </div>
      )}
    </article>
  );
}

/**
 * Score pill component
 */
function ScorePill({ label, value }: { label: string; value: number }) {
  return (
    <div className="text-center p-2 bg-gray-50 rounded">
      <div className="text-lg font-bold text-gray-900">{value}</div>
      <div className="text-xs text-gray-600">{label}</div>
    </div>
  );
}
