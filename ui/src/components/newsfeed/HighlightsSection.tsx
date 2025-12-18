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
} from 'lucide-react';
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

interface HighlightsSectionProps {
  incidents: Incident[];
  loading?: boolean;
  onIncidentUpdate?: () => void;
  onArticleClick?: (article: { uri: string; title?: string }) => void;
}

export function HighlightsSection({ incidents, loading, onIncidentUpdate, onArticleClick }: HighlightsSectionProps) {
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
 * Shows: headline, type, significance stripe, topic
 */
interface CompactIncidentCardProps {
  incident: Incident;
  onClick?: () => void;
}

function CompactIncidentCard({ incident, onClick }: CompactIncidentCardProps) {
  const [showTooltip, setShowTooltip] = useState(false);
  const [tooltipPos, setTooltipPos] = useState({ top: 0, left: 0 });
  const cardRef = useRef<HTMLDivElement>(null);
  const name = incident.name || incident.title || 'Unnamed Incident';
  const type = incident.type || 'event';
  const significance = incident.significance || 'medium';
  const tooltipContent = incident.description || incident.summary;

  // Get border color based on significance (matching BriefingCard pattern)
  const significanceBorder =
    significance === 'high' ? 'border-t-red-500' :
    significance === 'medium' ? 'border-t-yellow-500' :
    'border-t-blue-500';

  const handleMouseEnter = () => {
    if (cardRef.current) {
      const rect = cardRef.current.getBoundingClientRect();
      // Position tooltip above the card, centered horizontally
      // Clamp to viewport bounds
      const tooltipWidth = 288; // w-72 = 18rem = 288px
      let left = rect.left + (rect.width / 2) - (tooltipWidth / 2);
      // Keep tooltip within viewport
      left = Math.max(8, Math.min(left, window.innerWidth - tooltipWidth - 8));
      const top = rect.top - 8; // 8px gap above card
      setTooltipPos({ top, left });
    }
    setShowTooltip(true);
  };

  return (
    <div
      ref={cardRef}
      className="relative"
      onMouseEnter={handleMouseEnter}
      onMouseLeave={() => setShowTooltip(false)}
    >
      <div
        onClick={onClick}
        className={`flex-shrink-0 w-[220px] bg-white border border-gray-200 border-t-4 ${significanceBorder} rounded-lg p-3 cursor-pointer hover:shadow-md hover:border-gray-300 transition-all snap-start`}
      >
        {/* Title */}
        <h4 className="font-semibold text-gray-900 text-sm line-clamp-2 mb-2 min-h-[40px]">
          {name}
        </h4>

        {/* Badges row */}
        <div className="flex flex-wrap gap-1">
          <span className={`text-[10px] px-1.5 py-0.5 rounded ${getTypeBadgeColor(type)}`}>
            {type}
          </span>
          {incident.topic && (
            <span
              className="text-[10px] px-1.5 py-0.5 rounded"
              style={{ backgroundColor: getTopicColor(incident.topic), color: 'white' }}
            >
              {incident.topic}
            </span>
          )}
        </div>
      </div>

      {/* Hover tooltip - rendered via portal to escape overflow containers */}
      {showTooltip && (tooltipContent || incident.organizational_relevance) && createPortal(
        <div
          className="fixed z-[9999] w-72 p-3 bg-white rounded-lg shadow-lg border border-gray-200 pointer-events-none"
          style={{
            top: tooltipPos.top,
            left: tooltipPos.left,
            transform: 'translateY(-100%)'
          }}
        >
          {tooltipContent && (
            <p className="text-xs text-gray-600 leading-relaxed line-clamp-4">
              {tooltipContent}
            </p>
          )}
          {incident.organizational_relevance && (
            <p className="text-xs text-blue-600 mt-2 line-clamp-2">
              <strong>Why it matters:</strong> {incident.organizational_relevance}
            </p>
          )}
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

  // Launch Auspex research
  const launchResearch = (query: string) => {
    window.location.href = `/auspex?query=${encodeURIComponent(query)}`;
  };

  return (
    <Card
      className={`overflow-hidden hover:shadow-md transition-shadow ${
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
          {/* Header */}
          <div className="flex items-start justify-between gap-2 mb-2">
            <div className="flex items-center gap-2 flex-wrap flex-1 min-w-0">
              <h3 className="font-semibold text-gray-900 text-sm break-words">{name}</h3>
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
          <p className={`text-sm text-gray-600 mb-2 ${expanded ? '' : 'line-clamp-3'}`}>
            {description}
          </p>

          {/* Organizational Relevance */}
          {incident.organizational_relevance && (
            <div className="bg-blue-50 border border-blue-100 rounded-lg p-2 mb-2">
              <p className="text-xs text-blue-800">
                <Building className="w-3 h-3 inline mr-1" />
                <strong>Why This Matters:</strong> {incident.organizational_relevance}
              </p>
            </div>
          )}

          {/* Credibility Summary - Always visible */}
          {incident.credibility_summary && (
            <div className="bg-gray-50 rounded-lg p-2 mb-2">
              <p className="text-xs text-gray-500 font-medium mb-1">Credibility Assessment:</p>
              <p className={`text-xs text-gray-600 ${expanded ? '' : 'line-clamp-2'}`}>
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
          {expanded && Array.isArray(incident.investigation_leads) && incident.investigation_leads.length > 0 && (
            <div className="mt-3 pt-3 border-t border-gray-100">
              <p className="text-xs text-gray-500 font-medium mb-2">Investigation Leads:</p>
              <div className="flex flex-wrap gap-1">
                {incident.investigation_leads.map((lead, i) => (
                  <button
                    key={i}
                    onClick={() => launchResearch(lead)}
                    className="text-xs bg-white border border-blue-200 text-blue-600 px-2 py-1 rounded-full hover:bg-blue-50 transition-colors flex items-center gap-1"
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

          {/* Action buttons */}
          {expanded && (
            <div className="mt-3 pt-3 border-t border-gray-100">
              <div className="mb-2">
                <p className="text-xs text-gray-500 font-medium mb-1">Analysis</p>
                <div className="flex flex-wrap gap-1">
                  <Button
                    variant="outline"
                    size="sm"
                    className="text-xs gap-1 h-7"
                    onClick={() => launchResearch(name)}
                  >
                    <Search className="w-3 h-3" />
                    Investigate
                  </Button>
                  {articleUris.length > 0 && (
                    <Button
                      variant="outline"
                      size="sm"
                      className="text-xs gap-1 h-7"
                      onClick={() => window.location.href = `/consensus?uri=${encodeURIComponent(articleUris[0])}`}
                    >
                      <Scale className="w-3 h-3" />
                      Consensus
                    </Button>
                  )}
                </div>
              </div>
              <div>
                <p className="text-xs text-gray-500 font-medium mb-1">Actions</p>
                <div className="flex flex-wrap gap-1">
                  {articleUris.length > 0 && (
                    <Button
                      variant="outline"
                      size="sm"
                      className="text-xs gap-1 h-7"
                      onClick={() => window.location.href = `/annotate?uri=${encodeURIComponent(articleUris[0])}`}
                    >
                      <StickyNote className="w-3 h-3" />
                    </Button>
                  )}
                  <Button
                    variant="outline"
                    size="sm"
                    className="text-xs gap-1 h-7"
                    onClick={handleStatusToggle}
                    disabled={actionLoading}
                  >
                    {status === 'seen' ? (
                      <EyeOff className="w-3 h-3" />
                    ) : (
                      <Eye className="w-3 h-3" />
                    )}
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    className="text-xs gap-1 h-7 text-red-600 hover:text-red-700"
                    onClick={handleDelete}
                    disabled={actionLoading}
                  >
                    <Trash2 className="w-3 h-3" />
                  </Button>
                </div>
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
  metadata?: { title: string; news_source: string; factual_reporting?: string; mbfc_credibility_rating?: string; bias?: string };
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
            </div>
          ) : (
            <span className="inline-block text-[10px] bg-amber-100 text-amber-700 px-1 py-0.5 rounded mt-1">
              📊 AI-Rated
            </span>
          )}
        </div>
        <ExternalLink className="w-3 h-3 text-gray-400 shrink-0" />
      </div>
    </a>
  );
}
