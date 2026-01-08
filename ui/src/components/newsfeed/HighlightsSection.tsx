/**
 * Highlights Section - Full Incident Tracking Display
 * Matches createIndividualIncidentCard from news_feed_new.html
 */

import { useState, useRef, useEffect } from 'react';
import { createPortal } from 'react-dom';
import {
  Crosshair,
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  Search,
  Eye,
  EyeOff,
  Trash2,
  StickyNote,
  Scale,
  Building,
  Calendar,
  Info,
  X,
  MoreVertical,
  Bookmark,
  Share2,
  ThumbsUp,
  ThumbsDown,
  Settings2,
} from 'lucide-react';
import { openAuspexWithQuery } from '../../utils/auspexEvents';
import {
  type Incident,
  type IncidentArticle,
  type IncidentType,
  getTypeBadgeColor,
  getSignificanceBadgeColor,
  getPlausibilityBadgeColor,
  getSourceQualityBadgeColor,
  getFactualityClass,
  getMBFCCredibilityClass,
  getBiasClass,
  getTopicColor,
  prettifyMisinfoFlag,
  updateIncidentStatus,
  deleteIncident as apiDeleteIncident,
} from '../../services/narrativeExplorerApi';
import { Card, CardContent } from '../ui/card';
import { Button } from '../ui/button';
import { Skeleton } from '../ui/skeleton';
import { AgentSignalBadge, extractSignalTags } from './AgentSignalBadge';

interface HighlightsSectionProps {
  incidents: Incident[];
  loading?: boolean;
  onIncidentUpdate?: () => void;
  onArticleClick?: (article: { uri: string; title?: string }) => void;
  onOpenConfig?: () => void;
}

export function HighlightsSection({ incidents, loading, onIncidentUpdate, onArticleClick, onOpenConfig }: HighlightsSectionProps) {
  const [expandedCards, setExpandedCards] = useState<Set<string>>(new Set());
  const [selectedIncidentId, setSelectedIncidentId] = useState<string | null>(null);

  // Arrow scroll navigation
  const scrollRef = useRef<HTMLDivElement>(null);
  const [showLeftArrow, setShowLeftArrow] = useState(false);
  const [showRightArrow, setShowRightArrow] = useState(false);

  const checkScrollArrows = () => {
    if (scrollRef.current) {
      const { scrollLeft, scrollWidth, clientWidth } = scrollRef.current;
      setShowLeftArrow(scrollLeft > 0);
      setShowRightArrow(scrollLeft < scrollWidth - clientWidth - 1);
    }
  };

  const scroll = (direction: 'left' | 'right') => {
    if (scrollRef.current) {
      scrollRef.current.scrollBy({
        left: direction === 'left' ? -240 : 240,
        behavior: 'smooth'
      });
    }
  };

  // Check scroll arrows when incidents change
  useEffect(() => {
    checkScrollArrows();
    window.addEventListener('resize', checkScrollArrows);
    return () => window.removeEventListener('resize', checkScrollArrows);
  }, [incidents.length]);

  const selectedIncident = selectedIncidentId
    ? incidents.find((i, idx) => (i.id || i.name || `incident-${idx}`) === selectedIncidentId)
    : null;

  const toggleExpand = (id: string) => {
    setExpandedCards((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const handleCompactCardClick = (incidentId: string) => {
    setSelectedIncidentId(selectedIncidentId === incidentId ? null : incidentId);
  };

  // Empty state - simple inline text
  if (!incidents.length && !loading) {
    return (
      <section className="mb-6">
        <div className="flex items-center gap-2 mb-2">
          <Crosshair className="w-5 h-5 text-pink-500" />
          <h2 className="text-xl font-semibold text-gray-900">Incidents</h2>
          <div className="flex-1" />
          {onOpenConfig && (
            <button
              onClick={onOpenConfig}
              className="p-1.5 rounded-md hover:bg-gray-100 transition-colors"
              title="Configure Incidents"
            >
              <Settings2 className="w-4 h-4 text-gray-500" />
            </button>
          )}
        </div>
        <p className="text-sm text-gray-500">No recent incidents, click refresh</p>
      </section>
    );
  }

  return (
    <section className="mb-8">
      {/* Section Header */}
      <div className="flex items-center gap-2 mb-4">
        <Crosshair className="w-5 h-5 text-pink-500" />
        <h2 className="text-xl font-semibold text-gray-900">Incidents</h2>
        <span className="text-sm text-gray-500 ml-2">
          {incidents.length} incident{incidents.length !== 1 ? 's' : ''} tracked
        </span>
        <div className="flex-1" />
        {onOpenConfig && (
          <button
            onClick={onOpenConfig}
            className="p-1.5 rounded-md hover:bg-gray-100 transition-colors"
            title="Configure Incidents"
          >
            <Settings2 className="w-4 h-4 text-gray-500" />
          </button>
        )}
      </div>

      {/* Loading State */}
      {loading ? (
        <div className="flex overflow-x-auto gap-3 pb-2 snap-x">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="flex-shrink-0 w-[220px] h-[100px] rounded-lg" />
          ))}
        </div>
      ) : (
        <>
          {/* Compact Incidents - horizontal scroll with arrows */}
          <div className="relative">
            {/* Left Arrow */}
            {showLeftArrow && (
              <button
                onClick={() => scroll('left')}
                className="absolute left-1 top-1/2 -translate-y-1/2 z-10 bg-white dark:bg-gray-800 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-full p-2 shadow-lg border border-gray-200 dark:border-gray-600"
              >
                <ChevronLeft className="w-5 h-5 text-gray-600 dark:text-gray-300" />
              </button>
            )}

            <div
              ref={scrollRef}
              onScroll={checkScrollArrows}
              className="flex overflow-x-auto gap-3 pb-2 snap-x scrollbar-hide"
            >
              {incidents.map((incident, index) => {
                const incidentKey = incident.id || incident.name || `incident-${index}`;
                return (
                  <CompactIncidentCard
                    key={incidentKey}
                    incident={incident}
                    onClick={() => handleCompactCardClick(incidentKey)}
                  />
                );
              })}
            </div>

            {/* Right Arrow */}
            {showRightArrow && (
              <button
                onClick={() => scroll('right')}
                className="absolute right-1 top-1/2 -translate-y-1/2 z-10 bg-white dark:bg-gray-800 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-full p-2 shadow-lg border border-gray-200 dark:border-gray-600"
              >
                <ChevronRight className="w-5 h-5 text-gray-600 dark:text-gray-300" />
              </button>
            )}
          </div>

          {/* Expanded Card Detail (when a compact card is clicked) */}
          {selectedIncident && (
            <div className="mt-4">
              <IncidentCard
                incident={selectedIncident}
                expanded={true}
                onToggleExpand={() => setSelectedIncidentId(null)}
                onIncidentUpdate={onIncidentUpdate}
                onArticleClick={onArticleClick}
              />
            </div>
          )}
        </>
      )}
    </section>
  );
}

/**
 * Compact incident card for horizontal scroll display
 * Shows: date, type badges, headline, plausibility/source ratings, topic
 */
interface CompactIncidentCardProps {
  incident: Incident;
  onClick?: () => void;
}

// Badge tooltip explanations for incidents
function getTypeBadgeTooltip(type: string): string {
  const lower = type.toLowerCase();
  if (lower === 'incident') return 'A specific event or occurrence that requires attention';
  if (lower === 'event') return 'A notable happening or development';
  if (lower === 'expertise') return 'Expert analysis or specialized knowledge';
  if (lower === 'trend') return 'An emerging pattern or direction';
  return `Type: ${type}`;
}

function getSignificanceTooltip(significance: string): string {
  const lower = significance.toLowerCase();
  if (lower === 'high') return 'High significance - requires immediate attention';
  if (lower === 'medium') return 'Medium significance - worth monitoring';
  if (lower === 'low') return 'Low significance - for awareness';
  return `Significance: ${significance}`;
}

function getPlausibilityTooltip(plausibility: string): string {
  const lower = plausibility.toLowerCase();
  if (lower === 'high' || lower === 'plausible') return 'High plausibility - likely to be accurate';
  if (lower === 'medium') return 'Medium plausibility - some uncertainty';
  if (lower === 'low' || lower === 'implausible') return 'Low plausibility - treat with caution';
  return `Plausibility: ${plausibility}`;
}

function getSourceQualityTooltip(quality: string): string {
  const lower = quality.toLowerCase();
  if (lower === 'high') return 'High quality sources - reliable and credible';
  if (lower === 'medium') return 'Medium quality sources - generally reliable';
  if (lower === 'low') return 'Low quality sources - verify independently';
  return `Source quality: ${quality}`;
}

function CompactIncidentCard({ incident, onClick }: CompactIncidentCardProps) {
  const [hoveredBadge, setHoveredBadge] = useState<string | null>(null);
  const [badgeTooltipPos, setBadgeTooltipPos] = useState({ top: 0, left: 0 });
  const [showMenu, setShowMenu] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const name = incident.name || incident.title || 'Unnamed Incident';
  const type = incident.type || 'event';
  const significance = incident.significance || 'medium';
  const displaySummary = incident.description || incident.summary || '';

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

  // Menu action handlers
  const handleMenuAction = (action: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setShowMenu(false);
    // TODO: Implement actual actions
    console.log(`Menu action: ${action} for incident: ${name}`);
  };

  // Format date for display
  const formatDisplayDate = (dateStr?: string | string[]) => {
    const dateVal = Array.isArray(dateStr) ? dateStr[0] : dateStr;
    if (!dateVal) return '';
    try {
      const date = new Date(dateVal);
      return date.toLocaleDateString('en-GB', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric'
      }).replace(/\//g, '.');
    } catch {
      return String(dateVal);
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
      case 'type':
        return getTypeBadgeTooltip(type);
      case 'significance':
        return getSignificanceTooltip(significance);
      case 'plausibility':
        return incident.plausibility ? getPlausibilityTooltip(incident.plausibility) : '';
      case 'source':
        return incident.source_quality ? getSourceQualityTooltip(incident.source_quality) : '';
      default:
        return '';
    }
  };

  return (
    <div className="relative">
      <div
        onClick={onClick}
        className="flex-shrink-0 w-[260px] bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-4 cursor-pointer hover:shadow-md hover:border-gray-300 dark:hover:border-gray-600 transition-all snap-start"
      >
        {/* Top row: Date + See More + Menu */}
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-1 text-[11px] text-gray-600 dark:text-gray-300">
            <Calendar className="w-3 h-3" />
            <span>{formatDisplayDate(incident.timeline)}</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[11px] text-blue-600 dark:text-blue-400 flex items-center gap-0.5">
              <ChevronDown className="w-3 h-3" />
              See More
            </span>
            {/* Kebab menu */}
            <div ref={menuRef} className="relative">
              <button
                onClick={(e) => { e.stopPropagation(); setShowMenu(!showMenu); }}
                className="p-1 hover:bg-gray-100 dark:hover:bg-gray-700 rounded transition-colors"
              >
                <MoreVertical className="w-4 h-4 text-gray-500 dark:text-gray-400" />
              </button>
              {showMenu && (
                <div className="absolute right-0 top-full mt-1 w-36 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg z-50 py-1">
                  <button
                    onClick={(e) => handleMenuAction('save', e)}
                    className="w-full px-3 py-2 text-left text-sm text-gray-900 dark:text-gray-100 hover:bg-gray-100 dark:hover:bg-gray-700 flex items-center gap-2"
                  >
                    <Bookmark className="w-4 h-4 text-gray-700 dark:text-gray-300" />
                    Save
                  </button>
                  <button
                    onClick={(e) => handleMenuAction('share', e)}
                    className="w-full px-3 py-2 text-left text-sm text-gray-900 dark:text-gray-100 hover:bg-gray-100 dark:hover:bg-gray-700 flex items-center gap-2"
                  >
                    <Share2 className="w-4 h-4 text-gray-700 dark:text-gray-300" />
                    Share
                  </button>
                  <button
                    onClick={(e) => handleMenuAction('more', e)}
                    className="w-full px-3 py-2 text-left text-sm text-gray-900 dark:text-gray-100 hover:bg-gray-100 dark:hover:bg-gray-700 flex items-center gap-2"
                  >
                    <ThumbsUp className="w-4 h-4 text-gray-700 dark:text-gray-300" />
                    More like this
                  </button>
                  <button
                    onClick={(e) => handleMenuAction('less', e)}
                    className="w-full px-3 py-2 text-left text-sm text-gray-900 dark:text-gray-100 hover:bg-gray-100 dark:hover:bg-gray-700 flex items-center gap-2"
                  >
                    <ThumbsDown className="w-4 h-4 text-gray-700 dark:text-gray-300" />
                    Less like this
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Title - fully legible */}
        <h4 className="font-semibold text-gray-900 dark:text-gray-100 text-sm mb-2">
          {name}
        </h4>

        {/* Summary - displayed on card */}
        {displaySummary && (
          <p className="text-[11px] text-gray-700 dark:text-gray-300 line-clamp-3 mb-2">
            {displaySummary}
          </p>
        )}

        {/* Type + Significance badges row - with hover tooltips */}
        <div className="flex flex-wrap gap-1 mb-2">
          <span
            className={`text-[10px] font-medium px-1.5 py-0.5 rounded cursor-help ${getTypeBadgeColor(type)}`}
            onMouseEnter={(e) => handleBadgeHover('type', e)}
            onMouseLeave={() => setHoveredBadge(null)}
          >
            {type}
          </span>
          <span
            className={`text-[10px] font-medium px-1.5 py-0.5 rounded cursor-help ${getSignificanceBadgeColor(significance)}`}
            onMouseEnter={(e) => handleBadgeHover('significance', e)}
            onMouseLeave={() => setHoveredBadge(null)}
          >
            {significance}
          </span>
        </div>

        {/* Plausibility + Source Quality badges - with hover tooltips */}
        <div className="flex flex-wrap gap-1 mb-2">
          {incident.plausibility && (
            <span
              className={`text-[10px] font-medium px-1.5 py-0.5 rounded cursor-help ${getPlausibilityBadgeColor(incident.plausibility)}`}
              onMouseEnter={(e) => handleBadgeHover('plausibility', e)}
              onMouseLeave={() => setHoveredBadge(null)}
            >
              {incident.plausibility}
            </span>
          )}
          {incident.source_quality && (
            <span
              className={`text-[10px] font-medium px-1.5 py-0.5 rounded cursor-help ${getSourceQualityBadgeColor(incident.source_quality)}`}
              onMouseEnter={(e) => handleBadgeHover('source', e)}
              onMouseLeave={() => setHoveredBadge(null)}
            >
              {incident.source_quality}
            </span>
          )}
        </div>

        {/* Topic badge */}
        {incident.topic && (
          <span
            className="text-[10px] font-medium px-1.5 py-0.5 rounded"
            style={{ backgroundColor: getTopicColor(incident.topic), color: 'white' }}
          >
            {incident.topic}
          </span>
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

interface IncidentCardProps {
  incident: Incident;
  expanded: boolean;
  onToggleExpand: () => void;
  onIncidentUpdate?: () => void;
  onArticleClick?: (article: { uri: string; title?: string }) => void;
}

function IncidentCard({ incident, expanded, onToggleExpand, onIncidentUpdate, onArticleClick }: IncidentCardProps) {
  const [actionLoading, setActionLoading] = useState(false);

  // Get display values with fallbacks
  const name = incident.name || incident.title || 'Unnamed Incident';
  const description = incident.description || incident.summary || '';
  const type = incident.type || 'event';
  const significance = incident.significance || 'medium';
  const status = incident.status || 'active';

  // Check for low quality indicators
  const isLowQuality =
    incident.plausibility === 'implausible' ||
    incident.source_quality === 'low' ||
    (incident.misinfo_flags?.some((f) =>
      ['low_factuality_source', 'low_credibility_source', 'fringe_bias'].includes(f)
    ) ?? false);

  // Get articles from either format
  const articles = incident.articles || [];
  const articleUris = incident.article_uris || articles.map((a) => a.uri);

  // Get investigation leads - handle both snake_case and camelCase, ensure it's an array
  const incidentAny = incident as any;
  const rawLeads = incident.investigation_leads || incidentAny.investigationLeads;
  const investigationLeads: string[] = Array.isArray(rawLeads) ? rawLeads : [];

  // Timeline handling
  const timeline = incident.timeline;
  const timelineDates = Array.isArray(timeline)
    ? timeline.map((t) => new Date(t).getTime()).filter((t) => !isNaN(t)).sort((a, b) => a - b)
    : timeline
    ? [new Date(timeline).getTime()].filter((t) => !isNaN(t))
    : [];

  // Handle status toggle
  const handleStatusToggle = async () => {
    if (actionLoading) return;
    setActionLoading(true);
    try {
      const newStatus = status === 'seen' ? 'active' : 'seen';
      await updateIncidentStatus(name, newStatus);
      onIncidentUpdate?.();
    } catch (err) {
      console.error('Failed to update status:', err);
    } finally {
      setActionLoading(false);
    }
  };

  // Handle delete
  const handleDelete = async () => {
    if (actionLoading) return;
    if (!confirm(`Delete incident "${name}"? This cannot be undone.`)) return;
    setActionLoading(true);
    try {
      await apiDeleteIncident(name);
      onIncidentUpdate?.();
    } catch (err) {
      console.error('Failed to delete:', err);
    } finally {
      setActionLoading(false);
    }
  };

  // Launch Auspex research with full incident context
  const launchResearch = (queryOrLead: string, isInvestigationLead: boolean = false) => {
    // Build entity list
    const entityList = incident.entities?.slice(0, 10).join(', ') || 'None identified';

    // Build article list (first 10 URIs)
    const articleList = articleUris.slice(0, 10).map(uri => `- ${uri}`).join('\n');
    const moreArticles = articleUris.length > 10 ? `... and ${articleUris.length - 10} more articles` : '';

    // Build quality indicators
    const qualityInfo = [];
    if (incident.plausibility) qualityInfo.push(`Plausibility: ${incident.plausibility}`);
    if (incident.source_quality) qualityInfo.push(`Source Quality: ${incident.source_quality}`);
    const qualityText = qualityInfo.length > 0 ? qualityInfo.join(', ') : '';

    let researchPrompt: string;

    if (isInvestigationLead) {
      // Investigation lead - include parent incident context
      researchPrompt = `Research this investigation lead: "${queryOrLead}"

PARENT INCIDENT: "${name}"
${description ? `Context: ${description}` : ''}
${incident.organizational_relevance ? `Why This Matters: ${incident.organizational_relevance}` : ''}
${entityList !== 'None identified' ? `Related Entities: ${entityList}` : ''}

Please investigate this specific angle and provide findings with citations.`;
    } else {
      // Full incident investigation
      researchPrompt = `Investigate this incident: "${name}"

INCIDENT CONTEXT:
Type: ${type}
Significance: ${significance}
${incident.topic ? `Topic: ${incident.topic}` : ''}
${qualityText ? `Quality Indicators: ${qualityText}` : ''}
${description ? `Description: ${description}` : ''}
${incident.organizational_relevance ? `Why This Matters: ${incident.organizational_relevance}` : ''}

Key Entities: ${entityList}

Source Articles (${articleUris.length} total):
${articleList}
${moreArticles}

Please analyze:
1. What is known about this incident from the source articles
2. Key entities and organizations involved
3. Timeline of events if available
4. Potential implications and significance
5. Related incidents or patterns

Provide comprehensive analysis with citations to the source articles.`;
    }

    openAuspexWithQuery(researchPrompt);
  };

  // Format date for display
  const formatDisplayDate = (dateStr?: string | string[]) => {
    const dateVal = Array.isArray(dateStr) ? dateStr[0] : dateStr;
    if (!dateVal) return '';
    try {
      const date = new Date(dateVal);
      return date.toLocaleDateString('en-GB', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric'
      }).replace(/\//g, '.');
    } catch {
      return String(dateVal);
    }
  };

  return (
    <Card
      className={`overflow-hidden hover:shadow-md transition-shadow bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 ${
        status === 'seen' ? 'opacity-75' : ''
      } ${isLowQuality ? 'border-l-4 border-l-red-500' : ''}`}
    >
      <CardContent className="p-0">
        {/* Significance stripe */}
        <div
          className={`h-1 ${
            significance === 'high'
              ? 'bg-red-500'
              : significance === 'medium'
              ? 'bg-yellow-500'
              : 'bg-blue-500'
          }`}
        />

        <div className="p-4">
          {/* Top row: Date + See More/Less */}
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-1.5 text-xs text-gray-500 dark:text-gray-400">
              <Calendar className="w-3.5 h-3.5" />
              <span>{formatDisplayDate(incident.timeline)}</span>
            </div>
            <button
              onClick={onToggleExpand}
              className="flex items-center gap-1 text-sm text-blue-600 dark:text-blue-400 hover:text-blue-700"
            >
              <ChevronDown className="w-4 h-4" />
              See More
            </button>
          </div>

          {/* Header */}
          <div className="flex items-start justify-between gap-2 mb-2">
            <div className="flex items-center gap-2 flex-wrap flex-1 min-w-0">
              <h3 className="font-semibold text-gray-900 dark:text-gray-100 text-sm break-words">{name}</h3>
              {incident.topic && (
                <span
                  className="text-[10px] px-1.5 py-0.5 rounded"
                  style={{ backgroundColor: getTopicColor(incident.topic), color: 'white' }}
                >
                  {incident.topic}
                </span>
              )}
              {status === 'seen' && (
                <span className="text-xs bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded flex items-center gap-1">
                  <Eye className="w-3 h-3" />
                  Seen
                </span>
              )}
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <span className={`text-xs px-2 py-0.5 rounded ${getTypeBadgeColor(type)}`}>
                {type}
              </span>
              <span className={`text-xs px-2 py-0.5 rounded ${getSignificanceBadgeColor(significance)}`}>
                {significance}
              </span>
              <button
                onClick={onToggleExpand}
                className="p-1 hover:bg-gray-100 rounded-full transition-colors"
                title="Close"
              >
                <X className="w-4 h-4 text-gray-500" />
              </button>
            </div>
          </div>

          {/* Plausibility & Source Quality badges */}
          {(incident.plausibility || incident.source_quality) && (
            <div className="flex gap-1 mb-2 flex-wrap">
              {incident.plausibility && (
                <span className={`text-xs px-2 py-0.5 rounded ${getPlausibilityBadgeColor(incident.plausibility)}`}>
                  Plausibility: {incident.plausibility}
                </span>
              )}
              {incident.source_quality && (
                <span className={`text-xs px-2 py-0.5 rounded ${getSourceQualityBadgeColor(incident.source_quality)}`}>
                  Source: {incident.source_quality}
                </span>
              )}
            </div>
          )}

          {/* Description */}
          <p className={`text-sm text-gray-600 dark:text-gray-400 mb-3 ${expanded ? '' : 'line-clamp-3'}`}>
            {description}
          </p>

          {/* Strategic Relevance / Why This Matters - quote block style */}
          {incident.organizational_relevance && (
            <div className="bg-gray-50 dark:bg-gray-900 rounded-lg p-3 mb-3 border-l-4 border-blue-500">
              <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">
                Strategic Relevance
              </h4>
              <p className="text-sm text-gray-600 dark:text-gray-400">
                {incident.organizational_relevance}
              </p>
            </div>
          )}

          {/* Credibility Assessment */}
          {incident.credibility_summary && (
            <div className="mb-3">
              <h4 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-1">
                Credibility Assessment
              </h4>
              <p className={`text-sm text-gray-600 dark:text-gray-400 ${expanded ? '' : 'line-clamp-2'}`}>
                {incident.credibility_summary}
              </p>
            </div>
          )}

          {/* Misinfo Warnings */}
          {incident.misinfo_flags && incident.misinfo_flags.length > 0 && (
            <div className="bg-red-50 border border-red-100 rounded-lg p-2 mb-2">
              <div className="flex items-start gap-2">
                <AlertTriangle className="w-4 h-4 text-red-500 shrink-0 mt-0.5" />
                <div className="flex flex-wrap gap-1">
                  {incident.misinfo_flags.map((flag, i) => (
                    <span key={i} className="text-xs bg-red-100 text-red-700 px-1.5 py-0.5 rounded">
                      {prettifyMisinfoFlag(flag)}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Timeline */}
          {timelineDates.length > 0 && (
            <div className="mb-2">
              <p className="text-xs text-gray-500 font-medium mb-1 flex items-center gap-1">
                <Calendar className="w-3 h-3" />
                {timelineDates.length === 1 ? 'Date:' : 'Timeline:'}
              </p>
              {timelineDates.length === 1 ? (
                <span className="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded">
                  {new Date(timelineDates[0]).toLocaleDateString()}
                </span>
              ) : (
                <TimelineRuler dates={timelineDates} />
              )}
            </div>
          )}

          {/* Entities */}
          {incident.entities && incident.entities.length > 0 && (
            <div className="mb-2">
              <div className="flex flex-wrap gap-1">
                {incident.entities.slice(0, expanded ? undefined : 3).map((entity, i) => (
                  <span key={i} className="text-xs bg-indigo-50 text-indigo-600 px-2 py-0.5 rounded">
                    {entity}
                  </span>
                ))}
                {!expanded && incident.entities.length > 3 && (
                  <span className="text-xs text-gray-400">+{incident.entities.length - 3} more</span>
                )}
              </div>
            </div>
          )}

          {/* Source Articles */}
          {expanded && articleUris.length > 0 && (
            <div className="mt-3 pt-3 border-t border-gray-100">
              <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
                Source Articles ({articleUris.length})
              </h4>
              <div className="space-y-2">
                {articleUris.slice(0, 3).map((uri, i) => {
                  const metadata = incident.article_metadata?.[i];
                  const article = articles[i];
                  return (
                    <ArticleLink
                      key={uri}
                      uri={uri}
                      metadata={metadata}
                      article={article}
                      onClick={onArticleClick ? () => onArticleClick({ uri, title: metadata?.title || article?.title }) : undefined}
                    />
                  );
                })}
                {articleUris.length > 3 && (
                  <p className="text-xs text-gray-400">+{articleUris.length - 3} more articles</p>
                )}
              </div>
            </div>
          )}

          {/* Investigation Leads */}
          {expanded && investigationLeads.length > 0 && (
            <div className="mt-3 pt-3 border-t border-gray-100 dark:border-gray-700">
              <p className="text-xs text-gray-500 dark:text-gray-400 font-medium mb-2">Investigation Leads:</p>
              <div className="flex flex-wrap gap-1">
                {investigationLeads.map((lead, i) => (
                  <button
                    key={i}
                    onClick={() => launchResearch(lead, true)}
                    className="text-xs bg-white dark:bg-gray-700 border border-blue-200 dark:border-blue-700 text-blue-600 dark:text-blue-400 px-2 py-1 rounded-full hover:bg-blue-50 dark:hover:bg-blue-900/30 transition-colors flex items-center gap-1"
                    title={`Research: ${lead}`}
                  >
                    <Search className="w-3 h-3" />
                    {lead.length > 20 ? lead.substring(0, 20) + '...' : lead}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Expand/Collapse button */}
          <button
            onClick={onToggleExpand}
            className="mt-3 text-xs text-pink-600 hover:text-pink-700 font-medium flex items-center gap-1"
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

          {/* Analysis buttons */}
          {expanded && (
            <div className="mt-3 pt-3 border-t border-gray-100 dark:border-gray-700">
              <p className="text-xs text-gray-500 dark:text-gray-400 font-medium mb-2">Analysis</p>
              <div className="flex flex-wrap items-center gap-4">
                <button
                  onClick={() => launchResearch(name)}
                  className="inline-flex items-center gap-1.5 text-sm text-pink-600 dark:text-pink-400 hover:text-pink-700 dark:hover:text-pink-300 font-medium transition-colors"
                >
                  <Search className="w-3.5 h-3.5" />
                  Investigate
                </button>
                {articleUris.length > 0 && (
                  <button
                    onClick={() => {
                      // Build article list with source info (first 20)
                      const articleList = articleUris.slice(0, 20).map((uri, i) => {
                        const article = incident.articles?.[i];
                        const source = article?.news_source || article?.source?.name || 'Unknown';
                        return `- ${source}: ${uri}`;
                      }).join('\n');
                      const moreArticles = articleUris.length > 20 ? `\n... and ${articleUris.length - 20} more sources` : '';

                      const consensusPrompt = `Perform a consensus analysis on: "${name}"

${description ? `CONTEXT: ${description}` : ''}

SOURCE ARTICLES (${articleUris.length} total):
${articleList}${moreArticles}

Please analyze:
1. What different sources are reporting about this incident
2. Points of agreement across sources
3. Points of disagreement or contradiction
4. Overall consensus assessment (strong/moderate/weak/disputed)
5. Key facts: well-established vs. still uncertain

Provide balanced analysis of how this story is being covered across sources, citing specific articles.`;
                      openAuspexWithQuery(consensusPrompt);
                    }}
                    className="inline-flex items-center gap-1.5 text-sm text-pink-600 dark:text-pink-400 hover:text-pink-700 dark:hover:text-pink-300 font-medium transition-colors"
                  >
                    <Scale className="w-3.5 h-3.5" />
                    Consensus
                  </button>
                )}
              </div>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

function TimelineRuler({ dates }: { dates: number[] }) {
  if (dates.length < 2) return null;

  const min = dates[0];
  const max = dates[dates.length - 1];
  const range = Math.max(1, max - min);

  return (
    <div>
      <div className="relative h-2 bg-gray-200 rounded-full">
        {dates.map((date, i) => {
          const position = ((date - min) / range) * 100;
          return (
            <div
              key={i}
              className="absolute w-1 h-2 bg-blue-500 rounded"
              style={{ left: `${position}%` }}
            />
          );
        })}
      </div>
      <div className="flex justify-between mt-1">
        <span className="text-[10px] text-gray-400">
          {new Date(dates[0]).toLocaleDateString()}
        </span>
        <span className="text-[10px] text-gray-400">
          {new Date(dates[dates.length - 1]).toLocaleDateString()}
        </span>
      </div>
    </div>
  );
}

function ArticleLink({
  uri,
  metadata,
  article,
  onClick,
}: {
  uri: string;
  metadata?: { title: string; news_source: string; factual_reporting?: string; mbfc_credibility_rating?: string; bias?: string; tags?: string[] };
  article?: IncidentArticle;
  onClick?: () => void;
}) {
  const title = metadata?.title || article?.title || 'View Article';
  const source = metadata?.news_source || article?.source || '';
  const hasMBFC = metadata?.factual_reporting || metadata?.mbfc_credibility_rating || metadata?.bias ||
                  article?.factual_reporting || article?.mbfc_credibility_rating || article?.bias;

  const factual = metadata?.factual_reporting || article?.factual_reporting;
  const credibility = metadata?.mbfc_credibility_rating || article?.mbfc_credibility_rating;
  const bias = metadata?.bias || article?.bias;
  const signalTags = extractSignalTags(metadata?.tags);

  const handleClick = (e: React.MouseEvent) => {
    if (onClick) {
      e.preventDefault();
      onClick();
    }
  };

  return (
    <a
      href={uri}
      target={onClick ? undefined : "_blank"}
      rel={onClick ? undefined : "noopener noreferrer"}
      onClick={handleClick}
      className="block p-2 rounded bg-gray-50 hover:bg-gray-100 transition-colors cursor-pointer"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <p className="text-xs font-medium text-gray-900 line-clamp-1">{title}</p>
          <p className="text-xs text-gray-500 mt-0.5">{source}</p>
          {hasMBFC ? (
            <div className="flex flex-wrap gap-1 mt-1">
              {factual && (
                <span className={`text-[10px] px-1 py-0.5 rounded ${getFactualityClass(factual)}`}>
                  {factual}
                </span>
              )}
              {credibility && (
                <span className={`text-[10px] px-1 py-0.5 rounded ${getMBFCCredibilityClass(credibility)}`}>
                  {credibility}
                </span>
              )}
              {bias && (
                <span className={`text-[10px] px-1 py-0.5 rounded ${getBiasClass(bias)}`}>
                  {bias}
                </span>
              )}
              {signalTags.length > 0 && (
                <AgentSignalBadge agentNames={signalTags} compact />
              )}
            </div>
          ) : (
            <div className="flex flex-wrap gap-1 mt-1">
              <span className="inline-block text-[10px] bg-yellow-100 text-yellow-700 dark:bg-yellow-900/50 dark:text-yellow-300 px-1 py-0.5 rounded">
                Factuality Inferred
              </span>
              {signalTags.length > 0 && (
                <AgentSignalBadge agentNames={signalTags} compact />
              )}
            </div>
          )}
        </div>
        <ExternalLink className="w-3 h-3 text-gray-400 shrink-0" />
      </div>
    </a>
  );
}
