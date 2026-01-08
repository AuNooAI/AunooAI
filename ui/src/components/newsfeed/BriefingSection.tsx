/**
 * Briefing Section - "Your Briefing" executive intelligence area
 * Displays rich executive briefing data with takeaways, strategic relevance,
 * indicators, and action items
 */

import React, { useState, useMemo } from 'react';
import { createPortal } from 'react-dom';
import {
  Sparkles,
  ExternalLink,
  Calendar,
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
  MessageSquare,
  User,
  RefreshCw,
  Settings2,
  X,
  Download,
  FileText,
  Table
} from 'lucide-react';
import { type NewsArticle, type SixArticlesReport, type TopStory, type Persona, type SixArticlesConfig } from '../../services/newsFeedApi';
import { Skeleton } from '../ui/skeleton';
import { openAuspexWithQuery } from '../../utils/auspexEvents';
import { AgentSignalBadge, extractSignalTags } from './AgentSignalBadge';
import { ExportService } from '../../services/exportService';

// Default personas (fallback if config not loaded)
const DEFAULT_PERSONAS: { value: string; label: string; description: string }[] = [
  { value: 'CEO', label: 'CEO', description: 'Strategic growth & market position' },
  { value: 'CMO', label: 'CMO', description: 'Brand, marketing & customer trends' },
  { value: 'CTO', label: 'CTO', description: 'Technology & innovation focus' },
  { value: 'CISO', label: 'CISO', description: 'Security & risk management' },
];

interface BriefingSectionProps {
  articles: NewsArticle[];
  sixArticles: SixArticlesReport | null;
  loadingSixArticles: boolean;
  starredArticles: string[];
  onStar: (uri: string) => void;
  onUnstar: (uri: string) => void;
  onArticleClick?: (article: NewsArticle) => void;
  persona?: Persona;
  onPersonaChange?: (persona: Persona, forceRegenerate?: boolean) => void;
  sixArticlesConfig?: SixArticlesConfig;
  onOpenConfig?: () => void;
  model?: string;
}

// Get color for risk/opportunity indicator - with dark mode support
function getRiskOpportunityStyle(value?: string): { bg: string; text: string; icon: React.ReactNode } {
  if (!value) return { bg: 'bg-gray-100 dark:bg-gray-700', text: 'text-gray-600 dark:text-gray-300', icon: null };
  const lower = value.toLowerCase();
  if (lower === 'opportunity') return { bg: 'bg-green-100 dark:bg-green-900/50', text: 'text-green-700 dark:text-green-300', icon: <TrendingUp className="w-3 h-3" /> };
  if (lower === 'risk') return { bg: 'bg-red-100 dark:bg-red-900/50', text: 'text-red-700 dark:text-red-300', icon: <TrendingDown className="w-3 h-3" /> };
  return { bg: 'bg-amber-100 dark:bg-amber-900/50', text: 'text-amber-700 dark:text-amber-300', icon: <AlertTriangle className="w-3 h-3" /> };
}

// Get color for signal strength - with dark mode support
function getSignalStrengthStyle(value?: string): { bg: string; text: string } {
  if (!value) return { bg: 'bg-gray-100 dark:bg-gray-700', text: 'text-gray-600 dark:text-gray-300' };
  const lower = value.toLowerCase();
  if (lower === 'strong') return { bg: 'bg-pink-100 dark:bg-pink-900/50', text: 'text-pink-700 dark:text-pink-300' };
  if (lower === 'moderate') return { bg: 'bg-blue-100 dark:bg-blue-900/50', text: 'text-blue-700 dark:text-blue-300' };
  return { bg: 'bg-gray-100 dark:bg-gray-700', text: 'text-gray-600 dark:text-gray-300' };
}

// Get time horizon style - with dark mode support
function getTimeHorizonStyle(value?: string): { bg: string; text: string } {
  if (!value) return { bg: 'bg-gray-100 dark:bg-gray-700', text: 'text-gray-600 dark:text-gray-300' };
  const lower = value.toLowerCase();
  if (lower === 'immediate') return { bg: 'bg-orange-100 dark:bg-orange-900/50', text: 'text-orange-700 dark:text-orange-300' };
  if (lower === 'medium' || lower === 'short-term' || lower === 'short') return { bg: 'bg-yellow-100 dark:bg-yellow-900/50', text: 'text-yellow-700 dark:text-yellow-300' };
  return { bg: 'bg-teal-100 dark:bg-teal-900/50', text: 'text-teal-700 dark:text-teal-300' };
}

// Strip source and date suffix from title (e.g., "Title (source.com, 2025-12-11)" -> "Title")
function cleanTitle(title: string): string {
  // Match pattern: " (something.com, YYYY-MM-DD)" or " (something, YYYY-MM-DD)" at end
  return title.replace(/\s*\([^)]+,\s*\d{4}-\d{2}-\d{2}\)\s*$/, '').trim();
}

// Get card gradient based on risk/opportunity
function getCardGradient(riskOpp?: string): string {
  if (!riskOpp) return 'bg-gradient-to-br from-white to-gray-50 dark:from-gray-800 dark:to-gray-900';
  const lower = riskOpp.toLowerCase();
  if (lower === 'opportunity') return 'bg-gradient-to-br from-white to-green-50/50 dark:from-gray-800 dark:to-green-900/30';
  if (lower === 'risk') return 'bg-gradient-to-br from-white to-red-50/50 dark:from-gray-800 dark:to-red-900/30';
  return 'bg-gradient-to-br from-white to-amber-50/50 dark:from-gray-800 dark:to-amber-900/30'; // mixed
}

// Get category badge style - with dark mode support
function getCategoryStyle(category?: string): { bg: string; text: string } {
  if (!category) return { bg: 'bg-gray-100 dark:bg-gray-700', text: 'text-gray-600 dark:text-gray-300' };
  const lower = category.toLowerCase();
  const styles: Record<string, { bg: string; text: string }> = {
    'policy': { bg: 'bg-purple-100 dark:bg-purple-900/50', text: 'text-purple-700 dark:text-purple-300' },
    'market': { bg: 'bg-emerald-100 dark:bg-emerald-900/50', text: 'text-emerald-700 dark:text-emerald-300' },
    'tech': { bg: 'bg-blue-100 dark:bg-blue-900/50', text: 'text-blue-700 dark:text-blue-300' },
    'workforce': { bg: 'bg-orange-100 dark:bg-orange-900/50', text: 'text-orange-700 dark:text-orange-300' },
    'security': { bg: 'bg-slate-100 dark:bg-slate-800', text: 'text-slate-700 dark:text-slate-300' },
    'society': { bg: 'bg-teal-100 dark:bg-teal-900/50', text: 'text-teal-700 dark:text-teal-300' },
  };
  return styles[lower] || { bg: 'bg-gray-100 dark:bg-gray-700', text: 'text-gray-600 dark:text-gray-300' };
}

// Tooltip explanations for badges
function getTimeHorizonTooltip(value: string): string {
  const lower = value.toLowerCase();
  if (lower.includes('immediate')) return 'Immediate impact expected within days to weeks';
  if (lower.includes('short')) return 'Short-term impact expected within 1-3 months';
  if (lower.includes('medium')) return 'Medium-term impact expected within 3-12 months';
  if (lower.includes('long')) return 'Long-term impact expected over 1+ years';
  return `Time horizon: ${value}`;
}

function getRiskOpportunityTooltip(value: string): string {
  const lower = value.toLowerCase();
  if (lower.includes('risk')) return 'This story represents a potential threat or challenge to monitor';
  if (lower.includes('opportunity')) return 'This story represents a potential advantage or opening to pursue';
  if (lower.includes('mixed')) return 'This story contains both risks and opportunities';
  return `Classification: ${value}`;
}

function getSignalStrengthTooltip(value: string): string {
  const lower = value.toLowerCase();
  if (lower.includes('weak')) return 'Early signal - may develop into something significant';
  if (lower.includes('moderate')) return 'Growing signal - worth monitoring closely';
  if (lower.includes('strong')) return 'Strong signal - high confidence in impact assessment';
  return `Signal strength: ${value}`;
}

// Badge component with hover tooltip
function BadgeWithTooltip({
  children,
  tooltip,
  className
}: {
  children: React.ReactNode;
  tooltip: string;
  className?: string;
}) {
  const [showTooltip, setShowTooltip] = useState(false);

  return (
    <div className="relative">
      <span
        className={`cursor-help ${className}`}
        onMouseEnter={() => setShowTooltip(true)}
        onMouseLeave={() => setShowTooltip(false)}
      >
        {children}
      </span>
      {showTooltip && (
        <div className="absolute right-0 top-full mt-1 z-50 w-48 p-2 text-xs text-white bg-gray-800 rounded shadow-lg pointer-events-none">
          {tooltip}
        </div>
      )}
    </div>
  );
}

export function BriefingSection({
  articles,
  sixArticles,
  loadingSixArticles,
  starredArticles,
  onStar,
  onUnstar,
  onArticleClick,
  persona = 'CEO',
  onPersonaChange,
  sixArticlesConfig,
  onOpenConfig,
  model,
}: BriefingSectionProps) {
  const [expandedIndex, setExpandedIndex] = useState<number | null>(null);
  const [showPersonaDropdown, setShowPersonaDropdown] = useState(false);
  const [showDownloadDropdown, setShowDownloadDropdown] = useState(false);

  // Build personas list from config (includes custom personas)
  const personas = useMemo(() => {
    if (!sixArticlesConfig?.personas) {
      return DEFAULT_PERSONAS;
    }

    return Object.entries(sixArticlesConfig.personas).map(([key, config]) => ({
      value: key,
      label: key,
      description: config.focus || `${key} perspective`,
    }));
  }, [sixArticlesConfig]);

  // Get top stories from six articles report
  const topStories = sixArticles?.articles || [];
  // Check for executive data - handle flat structure where fields are directly on story
  const hasExecutiveData = topStories.length > 0 && topStories.some(s => {
    const story = s as any;
    return story.executive_takeaway || story.strategic_relevance || story.time_horizon;
  });

  const currentPersona = personas.find(p => p.value === persona) || personas[0];

  // Handle persona change with force regenerate
  const handlePersonaChange = (newPersona: string) => {
    if (onPersonaChange) {
      onPersonaChange(newPersona as Persona, true); // Force regenerate
    }
    setShowPersonaDropdown(false);
  };

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

        {/* Right side controls */}
        <div className="flex items-center gap-2">
          {/* Download Button */}
          {sixArticles && sixArticles.articles?.length > 0 && (
            <div className="relative">
              <button
                onClick={() => setShowDownloadDropdown(!showDownloadDropdown)}
                className="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
                title="Download briefing"
              >
                <Download className="w-5 h-5" />
              </button>

              {showDownloadDropdown && (
                <>
                  {/* Backdrop */}
                  <div
                    className="fixed inset-0 z-10"
                    onClick={() => setShowDownloadDropdown(false)}
                  />
                  {/* Dropdown */}
                  <div className="absolute right-0 top-full mt-1 w-48 bg-white border border-gray-200 rounded-lg shadow-lg z-20 py-1">
                    <button
                      onClick={() => {
                        ExportService.exportBriefingMarkdown(sixArticles, persona, model);
                        setShowDownloadDropdown(false);
                      }}
                      className="w-full px-4 py-2 text-left text-sm hover:bg-gray-50 transition-colors flex items-center gap-2"
                    >
                      <FileText className="w-4 h-4 text-gray-500" />
                      <span>Export as Markdown</span>
                    </button>
                    <button
                      onClick={() => {
                        ExportService.exportBriefingCSV(sixArticles);
                        setShowDownloadDropdown(false);
                      }}
                      className="w-full px-4 py-2 text-left text-sm hover:bg-gray-50 transition-colors flex items-center gap-2"
                    >
                      <Table className="w-4 h-4 text-gray-500" />
                      <span>Export as CSV</span>
                    </button>
                  </div>
                </>
              )}
            </div>
          )}

          {/* Tune Button */}
          {onOpenConfig && (
            <button
              onClick={onOpenConfig}
              className="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
              title="Configure briefing settings"
            >
              <Settings2 className="w-5 h-5" />
            </button>
          )}

          {/* Persona Selector */}
          {onPersonaChange && (
            <div className="relative">
              <button
                onClick={() => setShowPersonaDropdown(!showPersonaDropdown)}
                disabled={loadingSixArticles}
                className="flex items-center gap-2 px-3 py-1.5 text-sm bg-white border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors disabled:opacity-50"
                title={loadingSixArticles ? 'Generating briefing...' : 'Change persona to regenerate'}
              >
                <RefreshCw className={`w-4 h-4 ${loadingSixArticles ? 'text-pink-500 animate-spin' : 'text-gray-400'}`} />
                <User className="w-4 h-4 text-gray-500" />
                <span className="font-medium text-gray-700">{currentPersona.label}</span>
                <ChevronDown className={`w-4 h-4 text-gray-400 transition-transform ${showPersonaDropdown ? 'rotate-180' : ''}`} />
              </button>

              {showPersonaDropdown && (
                <>
                  {/* Backdrop */}
                  <div
                    className="fixed inset-0 z-10"
                    onClick={() => setShowPersonaDropdown(false)}
                  />
                  {/* Dropdown */}
                  <div className="absolute right-0 top-full mt-1 w-64 bg-white border border-gray-200 rounded-lg shadow-lg z-20 py-1 max-h-80 overflow-y-auto">
                    {personas.map((p) => (
                      <button
                        key={p.value}
                        onClick={() => handlePersonaChange(p.value)}
                        className={`w-full px-4 py-2 text-left hover:bg-gray-50 transition-colors ${
                          persona === p.value ? 'bg-pink-50' : ''
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <span className={`font-medium ${persona === p.value ? 'text-pink-600' : 'text-gray-900'}`}>
                            {p.label}
                          </span>
                          {persona === p.value && (
                            <span className="text-pink-500">✓</span>
                          )}
                        </div>
                        <p className="text-xs text-gray-500 mt-0.5 line-clamp-2">{p.description}</p>
                      </button>
                    ))}
                  </div>
                </>
              )}
            </div>
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
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-[120px]" />
          ))}
        </div>
      ) : topStories.length > 0 ? (
        /* Compact Briefing Cards - 2-column grid with inline expansion */
        <div className="grid grid-cols-1 md:grid-cols-2 gap-0">
          {topStories.slice(0, 8).map((story, index) => {
            const storyAny = story as any;
            const storyUri = storyAny.url || storyAny.uri || storyAny.primary_article?.uri || `story-${index}`;
            const isExpanded = expandedIndex === index;
            return (
              <React.Fragment key={storyUri}>
                <div
                  className={`p-4 border-b border-gray-300 dark:border-gray-600 md:odd:border-r ${isExpanded ? 'bg-gray-50 dark:bg-gray-800/50' : ''}`}
                >
                  <CompactBriefingCard
                    story={story}
                    onClick={() => setExpandedIndex(isExpanded ? null : index)}
                    isExpanded={isExpanded}
                  />
                </div>
                {/* Expanded detail appears right after the clicked card, spanning full width */}
                {isExpanded && (
                  <div className="col-span-1 md:col-span-2 border-b border-gray-300 dark:border-gray-600">
                    <BriefingCard
                      story={story}
                      index={index}
                      isExpanded={true}
                      onToggle={() => setExpandedIndex(null)}
                      isStarred={starredArticles.includes(storyUri)}
                      onStar={onStar}
                      onUnstar={onUnstar}
                    />
                  </div>
                )}
              </React.Fragment>
            );
          })}
        </div>
      ) : (
        /* Fallback to simple article list if no six articles data */
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {articles.slice(0, 8).map((article) => (
            <div
              key={article.uri}
              className="p-3 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
              onClick={() => onArticleClick?.(article)}
            >
              <h4 className="font-medium text-gray-900 dark:text-gray-100 text-sm">{article.title}</h4>
              <p className="text-xs text-gray-600 dark:text-gray-400 mt-1">{article.source?.name}</p>
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
 * Compact briefing card for horizontal scroll display
 * Shows: date, category, headline, rating badges, source
 */
interface CompactBriefingCardProps {
  story: TopStory;
  onClick?: () => void;
  isExpanded?: boolean;
}

function CompactBriefingCard({ story, onClick, isExpanded }: CompactBriefingCardProps) {
  const [hoveredBadge, setHoveredBadge] = useState<string | null>(null);
  const [badgeTooltipPos, setBadgeTooltipPos] = useState({ top: 0, left: 0 });
  const storyData = story as any;

  const riskStyle = getRiskOpportunityStyle(storyData.risk_opportunity);
  const signalStyle = getSignalStrengthStyle(storyData.signal_strength);
  const timeStyle = getTimeHorizonStyle(storyData.time_horizon);
  const categoryStyle = getCategoryStyle(storyData.category);

  const rawTitle = storyData.title || storyData.headline || storyData.primary_article?.title || 'Untitled';
  const displayTitle = cleanTitle(rawTitle);
  const displayDate = storyData.date || storyData.primary_article?.publication_date || '';
  const displaySource = storyData.source || storyData.primary_article?.source?.name || '';
  const articleUrl = storyData.url || storyData.primary_article?.url || '';

  // Format date for display
  const formatDisplayDate = (dateStr?: string) => {
    if (!dateStr) return '';
    try {
      const date = new Date(dateStr);
      return date.toLocaleDateString('en-GB', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric'
      }).replace(/\//g, '.');
    } catch {
      return dateStr;
    }
  };

  // Handle badge hover for tooltip
  const handleBadgeHover = (badgeType: string, e: React.MouseEvent) => {
    const rect = (e.target as HTMLElement).getBoundingClientRect();
    setBadgeTooltipPos({
      top: rect.bottom + 4,
      left: rect.left + rect.width / 2
    });
    setHoveredBadge(badgeType);
  };

  // Get tooltip text for badge
  const getBadgeTooltipText = (badgeType: string): string => {
    switch (badgeType) {
      case 'risk':
        return storyData.risk_opportunity ? getRiskOpportunityTooltip(storyData.risk_opportunity) : '';
      case 'time':
        return storyData.time_horizon ? getTimeHorizonTooltip(storyData.time_horizon) : '';
      case 'signal':
        return storyData.signal_strength ? getSignalStrengthTooltip(storyData.signal_strength) : '';
      default:
        return '';
    }
  };

  return (
    <div className="relative">
      <div
        onClick={onClick}
        className={`cursor-pointer transition-all ${isExpanded ? 'bg-gray-50 dark:bg-gray-800/50' : 'hover:bg-gray-50 dark:hover:bg-gray-800/30'}`}
      >
        {/* Top row: Date + See More */}
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-1 text-xs text-gray-600 dark:text-gray-400">
            <Calendar className="w-3.5 h-3.5" />
            <span>{formatDisplayDate(displayDate)}</span>
          </div>
          <span className="text-xs text-blue-600 dark:text-blue-400 flex items-center gap-0.5 font-medium">
            {isExpanded ? (
              <>
                <ChevronUp className="w-3.5 h-3.5" />
                See Less
              </>
            ) : (
              <>
                <ChevronDown className="w-3.5 h-3.5" />
                See More
              </>
            )}
          </span>
        </div>

        {/* Category badge */}
        {storyData.category && (
          <span className={`inline-block text-xs font-medium px-2 py-0.5 rounded-full mb-2 ${categoryStyle.bg} ${categoryStyle.text}`}>
            {storyData.category.toUpperCase()}
          </span>
        )}

        {/* Title with Agent Signal Badge */}
        <div className="flex items-start gap-2 mb-2">
          <h4 className="font-bold text-gray-900 dark:text-gray-100 text-base flex-1">
            {displayTitle}
          </h4>
          {extractSignalTags(storyData.tags || storyData.primary_article?.tags).length > 0 && (
            <AgentSignalBadge
              agentNames={extractSignalTags(storyData.tags || storyData.primary_article?.tags)}
              compact
            />
          )}
        </div>

        {/* Rating badges row - with hover tooltips */}
        <div className="flex flex-wrap gap-1.5 mb-2">
          {storyData.risk_opportunity && (
            <span
              className={`text-xs font-medium px-2 py-0.5 rounded flex items-center gap-0.5 cursor-help ${riskStyle.bg} ${riskStyle.text}`}
              onMouseEnter={(e) => handleBadgeHover('risk', e)}
              onMouseLeave={() => setHoveredBadge(null)}
            >
              {riskStyle.icon}
              {storyData.risk_opportunity}
            </span>
          )}
          {storyData.time_horizon && (
            <span
              className={`text-xs font-medium px-2 py-0.5 rounded cursor-help ${timeStyle.bg} ${timeStyle.text}`}
              onMouseEnter={(e) => handleBadgeHover('time', e)}
              onMouseLeave={() => setHoveredBadge(null)}
            >
              {storyData.time_horizon}
            </span>
          )}
          {storyData.signal_strength && (
            <span
              className={`text-xs font-medium px-2 py-0.5 rounded cursor-help ${signalStyle.bg} ${signalStyle.text}`}
              onMouseEnter={(e) => handleBadgeHover('signal', e)}
              onMouseLeave={() => setHoveredBadge(null)}
            >
              {storyData.signal_strength}
            </span>
          )}
        </div>

        {/* Source link */}
        {displaySource && (
          <a
            href={articleUrl || '#'}
            target="_blank"
            rel="noopener noreferrer"
            onClick={(e) => e.stopPropagation()}
            className="inline-flex items-center gap-1 text-xs text-blue-600 dark:text-blue-400 hover:underline"
          >
            <ExternalLink className="w-3.5 h-3.5 shrink-0" />
            <span>{displaySource}</span>
          </a>
        )}
      </div>

      {/* Badge tooltip - rendered via portal */}
      {hoveredBadge && createPortal(
        <div
          className="fixed z-[9999] w-48 p-2 bg-gray-900 text-white text-xs rounded shadow-lg pointer-events-none"
          style={{
            top: badgeTooltipPos.top,
            left: badgeTooltipPos.left,
            transform: 'translateX(-50%)'
          }}
        >
          {getBadgeTooltipText(hoveredBadge)}
        </div>,
        document.body
      )}
    </div>
  );
}

/**
 * Individual briefing card with executive intelligence (full version)
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

  const riskStyle = getRiskOpportunityStyle(storyData.risk_opportunity);
  const signalStyle = getSignalStrengthStyle(storyData.signal_strength);
  const timeStyle = getTimeHorizonStyle(storyData.time_horizon);
  const categoryStyle = getCategoryStyle(storyData.category);

  // Get URL - handle both flat and nested structures
  const articleUrl = storyData.url || storyData.primary_article?.url || storyData.primary_article?.uri || '';
  const articleUri = storyData.url || storyData.primary_article?.uri || '';

  // Get display values - handle both structures
  const rawTitle = storyData.title || storyData.headline || storyData.primary_article?.title || 'Untitled';
  const displayTitle = cleanTitle(rawTitle);
  const displaySource = storyData.source || storyData.primary_article?.source?.name || '';
  const displayDate = storyData.date || storyData.primary_article?.publication_date || '';
  const displaySummary = storyData.summary || storyData.primary_article?.summary || '';
  const displayScores = storyData.scores || {};
  const executiveActions = Array.isArray(storyData.executive_action)
    ? storyData.executive_action
    : (storyData.executive_action ? [storyData.executive_action] : []);

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

    // Build scores string if available
    const scoresText = displayScores && Object.keys(displayScores).length > 0
      ? `Scores: ${displayScores.relevance ? `Relevance=${displayScores.relevance}` : ''}${displayScores.impact ? `, Impact=${displayScores.impact}` : ''}${displayScores.actionability ? `, Actionability=${displayScores.actionability}` : ''}${displayScores.overall ? `, Overall=${displayScores.overall}/5` : ''}`
      : '';

    // Build executive actions string
    const actionsText = executiveActions.length > 0
      ? `Recommended Actions:\n${executiveActions.map((a: string) => `- ${a}`).join('\n')}`
      : '';

    // Build comprehensive research prompt with full article context
    const prompt = `Analyze this article: "${displayTitle}"
${articleUri ? `Article URI: ${articleUri}` : ''}
${displaySource ? `Source: ${displaySource}` : ''}

ARTICLE CONTEXT:
Category: ${storyData.category || 'N/A'}
Time Horizon: ${storyData.time_horizon || 'N/A'}
Signal Strength: ${storyData.signal_strength || 'N/A'}
Risk/Opportunity: ${storyData.risk_opportunity || 'N/A'}
${scoresText}

EXECUTIVE BRIEFING:
Executive Takeaway: ${storyData.executive_takeaway || 'N/A'}
Strategic Relevance: ${storyData.strategic_relevance || 'N/A'}
${actionsText}

${displaySummary ? `ARTICLE SUMMARY:\n${displaySummary}` : ''}

Please provide:
1. Deeper analysis of the key strategic points
2. Potential implications for our organization
3. Additional actions or areas to monitor beyond what's listed
4. Related trends or developments to watch
5. Questions to investigate further`;

    openAuspexWithQuery(prompt);
  };

  // Format date for display
  const formatDisplayDate = (dateStr?: string) => {
    if (!dateStr) return '';
    try {
      const date = new Date(dateStr);
      return date.toLocaleDateString('en-GB', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric'
      }).replace(/\//g, '.');
    } catch {
      return dateStr;
    }
  };

  return (
    <article className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden hover:shadow-md transition-shadow">
      {/* Header - Always visible */}
      <div
        className="p-5 cursor-pointer"
        onClick={onToggle}
      >
        {/* Top row: Date + See More/Less */}
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-1.5 text-xs text-gray-500 dark:text-gray-400">
            <Calendar className="w-3.5 h-3.5" />
            <span>{formatDisplayDate(displayDate)}</span>
          </div>
          <button
            onClick={(e) => { e.stopPropagation(); onToggle(); }}
            className="flex items-center gap-1 text-xs text-blue-600 dark:text-blue-400 hover:text-blue-700"
          >
            {isExpanded ? (
              <>
                <ChevronUp className="w-3.5 h-3.5" />
                See Less
              </>
            ) : (
              <>
                <ChevronDown className="w-3.5 h-3.5" />
                See More
              </>
            )}
          </button>
        </div>

        {/* Category badge */}
        {storyData.category && (
          <span className={`inline-block text-xs font-medium px-2.5 py-1 rounded-full mb-3 ${categoryStyle.bg} ${categoryStyle.text} dark:bg-opacity-20`}>
            {storyData.category.toUpperCase()}
          </span>
        )}

        {/* Title with Agent Signal Badge */}
        <div className="flex items-start gap-2 mb-2">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 leading-tight flex-1">
            {displayTitle}
          </h3>
          {extractSignalTags(storyData.tags || storyData.primary_article?.tags).length > 0 && (
            <AgentSignalBadge
              agentNames={extractSignalTags(storyData.tags || storyData.primary_article?.tags)}
              compact
            />
          )}
        </div>

        {/* Rating badges row */}
        <div className="flex flex-wrap items-center gap-2 mb-3">
          {storyData.time_horizon && (
            <span className={`text-xs font-medium px-2 py-0.5 rounded ${timeStyle.bg} ${timeStyle.text}`}>
              {storyData.time_horizon}
            </span>
          )}
          {storyData.risk_opportunity && (
            <span className={`text-xs font-medium px-2 py-0.5 rounded flex items-center gap-1 ${riskStyle.bg} ${riskStyle.text}`}>
              {riskStyle.icon}
              {storyData.risk_opportunity}
            </span>
          )}
          {storyData.signal_strength && (
            <span className={`text-xs font-medium px-2 py-0.5 rounded ${signalStyle.bg} ${signalStyle.text}`}>
              {storyData.signal_strength}
            </span>
          )}
          {displayScores.overall && (
            <span className="text-xs font-bold text-pink-600 dark:text-pink-400 bg-pink-50 dark:bg-pink-900/30 px-2 py-0.5 rounded">
              Score: {displayScores.overall}/5
            </span>
          )}
        </div>

        {/* Source link */}
        {displaySource && (
          <a
            href={articleUrl}
            target="_blank"
            rel="noopener noreferrer"
            onClick={(e) => e.stopPropagation()}
            className="inline-flex items-center gap-1 text-sm text-blue-600 dark:text-blue-400 hover:underline mb-3"
          >
            <ExternalLink className="w-3.5 h-3.5" />
            {displaySource}
          </a>
        )}

        {/* Executive Takeaway - "Why this matters" quote block */}
        {storyData.executive_takeaway && (
          <div className="mt-3 p-3 bg-pink-50 dark:bg-pink-900/20 rounded-lg border-l-4 border-pink-500">
            <h4 className="text-xs font-semibold text-pink-700 dark:text-pink-400 uppercase tracking-wide mb-1">
              Why This Matters
            </h4>
            <p className="text-sm text-gray-700 dark:text-gray-300">
              {storyData.executive_takeaway}
            </p>
          </div>
        )}
      </div>

      {/* Expanded Content */}
      {isExpanded && (
        <div className="px-5 pb-5 border-t border-gray-100 dark:border-gray-700 pt-4">
          {/* Summary */}
          {displaySummary && (
            <div className="pb-4 border-b border-gray-300 dark:border-gray-600">
              <h4 className="text-sm font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wide mb-2">
                Summary
              </h4>
              <p className="text-gray-700 dark:text-gray-300 leading-relaxed">
                {displaySummary}
              </p>
            </div>
          )}

          {/* Strategic Relevance - blue styling */}
          {storyData.strategic_relevance && (
            <div className="py-4 border-b border-gray-300 dark:border-gray-600">
              <div className="p-4 bg-blue-50 dark:bg-blue-900/20 rounded-lg border-l-4 border-blue-500">
                <h4 className="text-sm font-semibold text-blue-700 dark:text-blue-400 mb-2 flex items-center gap-1">
                  <Target className="w-4 h-4 text-blue-600 dark:text-blue-400" />
                  Strategic Relevance
                </h4>
                <p className="text-gray-700 dark:text-gray-300 leading-relaxed">
                  {storyData.strategic_relevance}
                </p>
              </div>
            </div>
          )}

          {/* Executive Actions */}
          {executiveActions.length > 0 && (
            <div className="py-4 border-b border-gray-300 dark:border-gray-600">
              <h4 className="text-sm font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wide mb-2">
                Executive Actions
              </h4>
              <ul className="space-y-2">
                {executiveActions.map((action: string, i: number) => (
                  <li key={i} className="flex items-start gap-2 text-gray-700 dark:text-gray-300">
                    <span className="text-pink-500 mt-0.5">→</span>
                    <span>{action}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Scores breakdown (if available) */}
          {displayScores && Object.keys(displayScores).length > 1 && (
            <div className="py-4 border-b border-gray-300 dark:border-gray-600">
              <h4 className="text-sm font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wide mb-2">
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
          <div className="flex items-center gap-4 pt-4">
            {articleUrl && (
              <a
                href={articleUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 text-sm text-blue-600 dark:text-blue-400 hover:underline font-medium transition-colors"
              >
                <ExternalLink className="w-3.5 h-3.5" />
                Read Original Article
              </a>
            )}
            <button
              onClick={handleAskAuspex}
              className="inline-flex items-center gap-1.5 text-sm text-pink-600 dark:text-pink-400 hover:text-pink-700 dark:hover:text-pink-300 font-medium transition-colors"
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
    <div className="text-center p-2 bg-gray-50 dark:bg-gray-900 rounded">
      <div className="text-lg font-bold text-gray-900 dark:text-gray-100">{value}</div>
      <div className="text-xs text-gray-600 dark:text-gray-400">{label}</div>
    </div>
  );
}
