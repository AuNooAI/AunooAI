/**
 * Saved Incidents Section - Display saved incidents
 * Can be used as a small section (horizontal scroll) or as a full tab (grid layout)
 */

import { useState, useRef, useEffect } from 'react';
import { createPortal } from 'react-dom';
import {
  Bookmark,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  ChevronUp,
  Calendar,
  MoreVertical,
  Share2,
  Trash2,
  BookmarkX,
  ExternalLink,
  AlertTriangle,
  Search,
  Scale,
  X,
  Download,
  FileText,
  Table,
} from 'lucide-react';
import {
  type Incident,
  type IncidentArticle,
  getTypeBadgeColor,
  getSignificanceBadgeColor,
  getPlausibilityBadgeColor,
  getSourceQualityBadgeColor,
  getTopicColor,
  getFactualityClass,
  getMBFCCredibilityClass,
  getBiasClass,
  prettifyMisinfoFlag,
} from '../../services/narrativeExplorerApi';
import { Skeleton } from '../ui/skeleton';
import { Card, CardContent } from '../ui/card';
import { AgentSignalBadge, extractSignalTags } from './AgentSignalBadge';
import { openAuspexWithQuery } from '../../utils/auspexEvents';
import { ShareModal, type ShareIncidentData } from '../ShareModal';
import { ExportService } from '../../services/exportService';

// Helper to extract all signal tags from an incident's article metadata
function getIncidentSignalTags(incident: Incident): string[] {
  const allTags: string[] = [];
  if (incident.article_metadata) {
    for (const meta of incident.article_metadata) {
      if (meta.tags) {
        allTags.push(...meta.tags);
      }
    }
  }
  return extractSignalTags(allTags);
}

interface SavedIncidentsSectionProps {
  incidents: Incident[];
  savedIncidentNames: string[];
  loading?: boolean;
  onUnsaveIncident?: (incidentName: string) => void;
  onArticleClick?: (article: { uri: string; title?: string }) => void;
  isFullTab?: boolean;
}

export function SavedIncidentsSection({
  incidents,
  savedIncidentNames,
  loading,
  onUnsaveIncident,
  onArticleClick,
  isFullTab = false,
}: SavedIncidentsSectionProps) {
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [selectedIncidentId, setSelectedIncidentId] = useState<string | null>(null);

  // Share modal state
  const [showShareModal, setShowShareModal] = useState(false);
  const [shareData, setShareData] = useState<ShareIncidentData | null>(null);

  // Download dropdown state
  const [showDownloadDropdown, setShowDownloadDropdown] = useState(false);

  // Arrow scroll navigation (only for compact mode)
  const scrollRef = useRef<HTMLDivElement>(null);
  const [showLeftArrow, setShowLeftArrow] = useState(false);
  const [showRightArrow, setShowRightArrow] = useState(false);

  // Filter incidents to only show saved ones
  const savedIncidents = incidents.filter((incident) => {
    const name = incident.name || incident.title || '';
    return savedIncidentNames.includes(name);
  });

  // Find selected incident for expansion
  const selectedIncident = selectedIncidentId
    ? savedIncidents.find((i, idx) => (i.id || i.name || `saved-incident-${idx}`) === selectedIncidentId)
    : null;

  const handleCompactCardClick = (incidentId: string) => {
    setSelectedIncidentId(selectedIncidentId === incidentId ? null : incidentId);
  };

  // Share handler - opens modal with incident data
  const handleShare = (incident: Incident) => {
    const name = incident.name || incident.title || 'Unnamed Incident';
    setShareData({
      type: 'incident',
      incident_name: name,
      incident_type: incident.type,
      significance: incident.significance,
      description: incident.description || incident.summary,
      topic: incident.topic,
      entities: incident.entities,
      strategic_relevance: incident.organizational_relevance,
      plausibility: incident.plausibility,
      source_quality: incident.source_quality,
    });
    setShowShareModal(true);
  };

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
        behavior: 'smooth',
      });
    }
  };

  // Check scroll arrows when saved incidents change
  useEffect(() => {
    if (!isFullTab) {
      checkScrollArrows();
      window.addEventListener('resize', checkScrollArrows);
      return () => window.removeEventListener('resize', checkScrollArrows);
    }
  }, [savedIncidents.length, isFullTab]);

  // Full Tab View
  if (isFullTab) {
    return (
      <div className="p-6">
        {/* Tab Header */}
        <div className="flex items-center gap-3 mb-6">
          <Bookmark className="w-6 h-6 text-amber-500 fill-amber-500" />
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Saved Incidents</h1>
          <span className="text-sm text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 px-2 py-1 rounded-full">
            {savedIncidents.length} saved
          </span>
          <div className="flex-1" />

          {/* Download Button */}
          {savedIncidents.length > 0 && (
            <div className="relative">
              <button
                onClick={() => setShowDownloadDropdown(!showDownloadDropdown)}
                className="p-2 rounded-md hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
                title="Download saved incidents"
              >
                <Download className="w-5 h-5 text-gray-700 dark:text-gray-300" />
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
                        ExportService.exportIncidentsMarkdown(savedIncidents);
                        setShowDownloadDropdown(false);
                      }}
                      className="w-full px-4 py-2 text-left text-sm hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors flex items-center gap-2"
                    >
                      <FileText className="w-4 h-4 text-gray-700 dark:text-gray-300" />
                      <span>Export as Markdown</span>
                    </button>
                    <button
                      onClick={() => {
                        ExportService.exportIncidentsCSV(savedIncidents);
                        setShowDownloadDropdown(false);
                      }}
                      className="w-full px-4 py-2 text-left text-sm hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors flex items-center gap-2"
                    >
                      <Table className="w-4 h-4 text-gray-700 dark:text-gray-300" />
                      <span>Export as CSV</span>
                    </button>
                  </div>
                </>
              )}
            </div>
          )}
        </div>

        {/* Loading State */}
        {loading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-[200px] rounded-lg" />
            ))}
          </div>
        ) : savedIncidents.length === 0 ? (
          /* Empty State */
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <BookmarkX className="w-16 h-16 text-gray-600 dark:text-gray-300 dark:text-gray-600 mb-4" />
            <h2 className="text-xl font-semibold text-gray-700 dark:text-gray-300 mb-2">
              No Saved Incidents
            </h2>
            <p className="text-gray-700 dark:text-gray-300 dark:text-gray-300 max-w-md">
              Save incidents from the News Feed tab by clicking the menu (⋮) on any incident card
              and selecting "Save". Your saved incidents will appear here.
            </p>
          </div>
        ) : (
          <>
            {/* Grid Layout for Full Tab */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {savedIncidents.map((incident, index) => {
                const incidentKey = incident.id || incident.name || `saved-incident-${index}`;
                return (
                  <SavedIncidentCard
                    key={incidentKey}
                    incident={incident}
                    onUnsave={onUnsaveIncident}
                    onArticleClick={onArticleClick}
                    onShare={handleShare}
                    onClick={() => handleCompactCardClick(incidentKey)}
                    isFullWidth={true}
                  />
                );
              })}
            </div>

            {/* Expanded Card Detail (when a card is clicked) */}
            {selectedIncident && (
              <div className="mt-4">
                <ExpandedSavedIncidentCard
                  incident={selectedIncident}
                  onClose={() => setSelectedIncidentId(null)}
                  onUnsave={onUnsaveIncident}
                  onArticleClick={onArticleClick}
                />
              </div>
            )}
          </>
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

  // Compact Section View (original horizontal scroll)
  // Don't render if no saved incidents
  if (savedIncidentNames.length === 0 && !loading) {
    return null;
  }

  return (
    <section className="mb-8">
      {/* Section Header */}
      <div className="flex items-center gap-2 mb-4">
        <Bookmark className="w-5 h-5 text-amber-500 fill-amber-500" />
        <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100">Saved Incidents</h2>
        <span className="text-sm text-gray-700 dark:text-gray-300 ml-2">
          {savedIncidents.length} saved
        </span>
        <div className="flex-1" />

        {/* Download Button */}
        {savedIncidents.length > 0 && (
          <div className="relative">
            <button
              onClick={() => setShowDownloadDropdown(!showDownloadDropdown)}
              className="p-1.5 rounded-md hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
              title="Download saved incidents"
            >
              <Download className="w-4 h-4 text-gray-700 dark:text-gray-300" />
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
                      ExportService.exportIncidentsMarkdown(savedIncidents);
                      setShowDownloadDropdown(false);
                    }}
                    className="w-full px-4 py-2 text-left text-sm hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors flex items-center gap-2"
                  >
                    <FileText className="w-4 h-4 text-gray-700 dark:text-gray-300" />
                    <span>Export as Markdown</span>
                  </button>
                  <button
                    onClick={() => {
                      ExportService.exportIncidentsCSV(savedIncidents);
                      setShowDownloadDropdown(false);
                    }}
                    className="w-full px-4 py-2 text-left text-sm hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors flex items-center gap-2"
                  >
                    <Table className="w-4 h-4 text-gray-700 dark:text-gray-300" />
                    <span>Export as CSV</span>
                  </button>
                </div>
              </>
            )}
          </div>
        )}

        <button
          onClick={() => setIsCollapsed(!isCollapsed)}
          className="p-1.5 rounded-md hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
          title={isCollapsed ? 'Expand section' : 'Collapse section'}
        >
          {isCollapsed ? (
            <ChevronDown className="w-4 h-4 text-gray-700 dark:text-gray-300" />
          ) : (
            <ChevronUp className="w-4 h-4 text-gray-700 dark:text-gray-300" />
          )}
        </button>
      </div>

      {/* Collapsed state */}
      {isCollapsed && (
        <p className="text-sm text-gray-700 dark:text-gray-300 dark:text-gray-300">
          {savedIncidents.length} incident{savedIncidents.length !== 1 ? 's' : ''} saved
        </p>
      )}

      {/* Expanded content */}
      {!isCollapsed && (
        <>
          {/* Loading State */}
          {loading ? (
            <div className="flex overflow-x-auto gap-3 pb-2 snap-x">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="flex-shrink-0 w-[220px] h-[100px] rounded-lg" />
              ))}
            </div>
          ) : savedIncidents.length === 0 ? (
            <p className="text-sm text-gray-700 dark:text-gray-300 dark:text-gray-300">
              No saved incidents yet. Use the menu on any incident card to save it.
            </p>
          ) : (
            /* Saved Incidents - horizontal scroll with arrows */
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
                {savedIncidents.map((incident, index) => {
                  const incidentKey = incident.id || incident.name || `saved-incident-${index}`;
                  return (
                    <SavedIncidentCard
                      key={incidentKey}
                      incident={incident}
                      onUnsave={onUnsaveIncident}
                      onArticleClick={onArticleClick}
                      onShare={handleShare}
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
          )}
        </>
      )}

      {/* Share Modal */}
      {shareData && (
        <ShareModal
          open={showShareModal}
          onOpenChange={setShowShareModal}
          data={shareData}
        />
      )}
    </section>
  );
}

/**
 * Saved Incident Card - compact card for saved incidents display
 */
interface SavedIncidentCardProps {
  incident: Incident;
  onUnsave?: (incidentName: string) => void;
  onArticleClick?: (article: { uri: string; title?: string }) => void;
  onShare?: (incident: Incident) => void;
  onClick?: () => void;
  isFullWidth?: boolean;
}

function SavedIncidentCard({ incident, onUnsave, onArticleClick, onShare, onClick, isFullWidth = false }: SavedIncidentCardProps) {
  const [showMenu, setShowMenu] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  const name = incident.name || incident.title || 'Unnamed Incident';
  const type = incident.type || 'event';
  const significance = incident.significance || 'medium';
  const displaySummary = incident.description || incident.summary || '';
  const signalTags = getIncidentSignalTags(incident);

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

  // Handle card click - expand the card
  const handleCardClick = () => {
    onClick?.();
  };

  // Handle unsave action
  const handleUnsave = (e: React.MouseEvent) => {
    e.stopPropagation();
    setShowMenu(false);
    onUnsave?.(name);
  };

  // Handle share action
  const handleShareClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    setShowMenu(false);
    onShare?.(incident);
  };

  // Format date for display
  const formatDisplayDate = (dateStr?: string | string[]) => {
    const dateVal = Array.isArray(dateStr) ? dateStr[0] : dateStr;
    if (!dateVal) return '';
    try {
      const date = new Date(dateVal);
      return date
        .toLocaleDateString('en-GB', {
          day: '2-digit',
          month: '2-digit',
          year: 'numeric',
        })
        .replace(/\//g, '.');
    } catch {
      return String(dateVal);
    }
  };

  const cardClasses = isFullWidth
    ? 'bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-700 rounded-lg p-4 cursor-pointer hover:shadow-md hover:border-amber-300 dark:hover:border-amber-600 transition-all'
    : 'flex-shrink-0 w-[260px] bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-700 rounded-lg p-4 cursor-pointer hover:shadow-md hover:border-amber-300 dark:hover:border-amber-600 transition-all snap-start';

  return (
    <div className={isFullWidth ? '' : 'relative'}>
      <div onClick={handleCardClick} className={cardClasses}>
        {/* Top row: Date + See More + Saved badge + Menu */}
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
            <span className="flex items-center gap-1 text-[10px] bg-amber-100 dark:bg-amber-800/50 text-amber-700 dark:text-amber-300 px-1.5 py-0.5 rounded">
              <Bookmark className="w-3 h-3 fill-current" />
              Saved
            </span>
            {/* Kebab menu */}
            <div ref={menuRef} className="relative">
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  setShowMenu(!showMenu);
                }}
                className="p-1 hover:bg-amber-100 dark:hover:bg-amber-800/50 rounded transition-colors"
              >
                <MoreVertical className="w-4 h-4 text-gray-700 dark:text-gray-300 dark:text-gray-300" />
              </button>
              {showMenu && (
                <div className="absolute right-0 top-full mt-1 w-32 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg z-50 py-1">
                  <button
                    onClick={handleShareClick}
                    className="w-full px-3 py-2 text-left text-sm text-gray-900 dark:text-gray-100 hover:bg-gray-100 dark:hover:bg-gray-700 flex items-center gap-2"
                  >
                    <Share2 className="w-4 h-4 text-gray-700 dark:text-gray-300" />
                    Share
                  </button>
                  <button
                    onClick={handleUnsave}
                    className="w-full px-3 py-2 text-left text-sm text-red-600 dark:text-red-400 hover:bg-gray-100 dark:hover:bg-gray-700 flex items-center gap-2"
                  >
                    <Trash2 className="w-4 h-4" />
                    Unsave
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Title */}
        <h4 className="font-semibold text-gray-900 dark:text-gray-100 text-sm mb-2">{name}</h4>

        {/* Summary */}
        {displaySummary && (
          <p className={`text-[11px] text-gray-700 dark:text-gray-300 mb-2 ${isFullWidth ? 'line-clamp-4' : 'line-clamp-3'}`}>
            {displaySummary}
          </p>
        )}

        {/* Type + Significance badges */}
        <div className="flex flex-wrap gap-1 mb-2">
          <span
            className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${getTypeBadgeColor(type)}`}
          >
            {type}
          </span>
          <span
            className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${getSignificanceBadgeColor(
              significance
            )}`}
          >
            {significance}
          </span>
          {signalTags.length > 0 && <AgentSignalBadge agentNames={signalTags} compact />}
        </div>

        {/* Plausibility + Source Quality badges */}
        <div className="flex flex-wrap gap-1 mb-2">
          {incident.plausibility && (
            <span
              className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${getPlausibilityBadgeColor(
                incident.plausibility
              )}`}
            >
              {incident.plausibility}
            </span>
          )}
          {incident.source_quality && (
            <span
              className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${getSourceQualityBadgeColor(
                incident.source_quality
              )}`}
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
    </div>
  );
}

/**
 * Expanded Saved Incident Card - shows full details like the feed tab
 */
interface ExpandedSavedIncidentCardProps {
  incident: Incident;
  onClose: () => void;
  onUnsave?: (incidentName: string) => void;
  onArticleClick?: (article: { uri: string; title?: string }) => void;
}

function ExpandedSavedIncidentCard({ incident, onClose, onUnsave, onArticleClick }: ExpandedSavedIncidentCardProps) {
  // Get display values with fallbacks
  const name = incident.name || incident.title || 'Unnamed Incident';
  const description = incident.description || incident.summary || '';
  const type = incident.type || 'event';
  const significance = incident.significance || 'medium';
  const signalTags = getIncidentSignalTags(incident);

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

  // Get investigation leads
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

  // Launch Auspex research with full incident context
  const launchResearch = (queryOrLead: string, isInvestigationLead: boolean = false) => {
    const entityList = incident.entities?.slice(0, 10).join(', ') || 'None identified';
    const articleList = articleUris.slice(0, 10).map(uri => `- ${uri}`).join('\n');
    const moreArticles = articleUris.length > 10 ? `... and ${articleUris.length - 10} more articles` : '';
    const qualityInfo = [];
    if (incident.plausibility) qualityInfo.push(`Plausibility: ${incident.plausibility}`);
    if (incident.source_quality) qualityInfo.push(`Source Quality: ${incident.source_quality}`);
    const qualityText = qualityInfo.length > 0 ? qualityInfo.join(', ') : '';

    let researchPrompt: string;

    if (isInvestigationLead) {
      researchPrompt = `Research this investigation lead: "${queryOrLead}"

PARENT INCIDENT: "${name}"
${description ? `Context: ${description}` : ''}
${incident.organizational_relevance ? `Why This Matters: ${incident.organizational_relevance}` : ''}
${entityList !== 'None identified' ? `Related Entities: ${entityList}` : ''}

Please investigate this specific angle and provide findings with citations.`;
    } else {
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
      className={`overflow-hidden bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-700 ${
        isLowQuality ? 'border-l-4 border-l-red-500' : ''
      }`}
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
          {/* Top row: Date + Close button */}
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-1.5 text-xs text-gray-700 dark:text-gray-300 dark:text-gray-300">
              <Calendar className="w-3.5 h-3.5" />
              <span>{formatDisplayDate(incident.timeline)}</span>
              <span className="flex items-center gap-1 ml-2 text-[10px] bg-amber-100 dark:bg-amber-800/50 text-amber-700 dark:text-amber-300 px-1.5 py-0.5 rounded">
                <Bookmark className="w-3 h-3 fill-current" />
                Saved
              </span>
            </div>
            <button
              onClick={onClose}
              className="p-1 hover:bg-amber-100 dark:hover:bg-amber-800 rounded-full transition-colors"
              title="Close"
            >
              <X className="w-4 h-4 text-gray-700 dark:text-gray-300" />
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
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <span className={`text-xs px-2 py-0.5 rounded ${getTypeBadgeColor(type)}`}>
                {type}
              </span>
              <span className={`text-xs px-2 py-0.5 rounded ${getSignificanceBadgeColor(significance)}`}>
                {significance}
              </span>
              {signalTags.length > 0 && (
                <AgentSignalBadge agentNames={signalTags} compact />
              )}
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
          <p className="text-sm text-gray-600 dark:text-gray-300 mb-3">
            {description}
          </p>

          {/* Strategic Relevance / Why This Matters */}
          {incident.organizational_relevance && (
            <div className="bg-white dark:bg-gray-800 rounded-lg p-3 mb-3 border-l-4 border-blue-500">
              <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">
                Strategic Relevance
              </h4>
              <p className="text-sm text-gray-600 dark:text-gray-300">
                {incident.organizational_relevance}
              </p>
            </div>
          )}

          {/* Credibility Assessment */}
          {incident.credibility_summary && (
            <div className="mb-3">
              <h4 className="text-xs font-semibold text-gray-700 dark:text-gray-300 dark:text-gray-300 uppercase tracking-wide mb-1">
                Credibility Assessment
              </h4>
              <p className="text-sm text-gray-600 dark:text-gray-300">
                {incident.credibility_summary}
              </p>
            </div>
          )}

          {/* Misinfo Warnings */}
          {incident.misinfo_flags && incident.misinfo_flags.length > 0 && (
            <div className="bg-red-50 dark:bg-red-900/30 border border-red-100 dark:border-red-800 rounded-lg p-2 mb-2">
              <div className="flex items-start gap-2">
                <AlertTriangle className="w-4 h-4 text-red-500 shrink-0 mt-0.5" />
                <div className="flex flex-wrap gap-1">
                  {incident.misinfo_flags.map((flag, i) => (
                    <span key={i} className="text-xs bg-red-100 dark:bg-red-800 text-red-700 dark:text-red-300 px-1.5 py-0.5 rounded">
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
              <p className="text-xs text-gray-700 dark:text-gray-300 font-medium mb-1 flex items-center gap-1">
                <Calendar className="w-3 h-3" />
                {timelineDates.length === 1 ? 'Date:' : 'Timeline:'}
              </p>
              {timelineDates.length === 1 ? (
                <span className="text-xs bg-blue-100 dark:bg-blue-900/50 text-blue-700 dark:text-blue-300 px-2 py-0.5 rounded">
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
                {incident.entities.map((entity, i) => (
                  <span key={i} className="text-xs bg-indigo-50 dark:bg-indigo-900/50 text-indigo-600 dark:text-indigo-300 px-2 py-0.5 rounded">
                    {entity}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Source Articles */}
          {articleUris.length > 0 && (
            <div className="mt-3 pt-3 border-t border-amber-200 dark:border-amber-700">
              <h4 className="text-xs font-semibold text-gray-700 dark:text-gray-300 dark:text-gray-300 uppercase tracking-wide mb-2">
                Source Articles ({articleUris.length})
              </h4>
              <div className="space-y-2">
                {articleUris.slice(0, 5).map((uri, i) => {
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
                {articleUris.length > 5 && (
                  <p className="text-xs text-gray-600 dark:text-gray-300">+{articleUris.length - 5} more articles</p>
                )}
              </div>
            </div>
          )}

          {/* Investigation Leads */}
          {investigationLeads.length > 0 && (
            <div className="mt-3 pt-3 border-t border-amber-200 dark:border-amber-700">
              <p className="text-xs text-gray-700 dark:text-gray-300 dark:text-gray-300 font-medium mb-2">Investigation Leads:</p>
              <div className="flex flex-wrap gap-1">
                {investigationLeads.map((lead, i) => (
                  <button
                    key={i}
                    onClick={() => launchResearch(lead, true)}
                    className="text-xs bg-white dark:bg-gray-700 border border-blue-200 dark:border-blue-700 text-blue-600 dark:text-blue-400 px-2 py-1 rounded-full hover:bg-blue-50 dark:hover:bg-blue-900/30 transition-colors flex items-center gap-1"
                    title={`Research: ${lead}`}
                  >
                    <Search className="w-3 h-3" />
                    {lead.length > 25 ? lead.substring(0, 25) + '...' : lead}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Analysis buttons */}
          <div className="mt-3 pt-3 border-t border-amber-200 dark:border-amber-700">
            <p className="text-xs text-gray-700 dark:text-gray-300 dark:text-gray-300 font-medium mb-2">Analysis</p>
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
              {onUnsave && (
                <button
                  onClick={() => onUnsave(name)}
                  className="inline-flex items-center gap-1.5 text-sm text-red-600 dark:text-red-400 hover:text-red-700 dark:hover:text-red-300 font-medium transition-colors"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                  Unsave
                </button>
              )}
            </div>
          </div>

          {/* Collapse button */}
          <button
            onClick={onClose}
            className="mt-3 text-xs text-pink-600 hover:text-pink-700 font-medium flex items-center gap-1"
          >
            <ChevronUp className="w-3 h-3" />
            Show less
          </button>
        </div>
      </CardContent>
    </Card>
  );
}

/**
 * Timeline Ruler - visual timeline display
 */
function TimelineRuler({ dates }: { dates: number[] }) {
  if (dates.length < 2) return null;

  const min = dates[0];
  const max = dates[dates.length - 1];
  const range = Math.max(1, max - min);

  return (
    <div>
      <div className="relative h-2 bg-gray-200 dark:bg-gray-700 rounded-full">
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
        <span className="text-[10px] text-gray-600 dark:text-gray-300">
          {new Date(dates[0]).toLocaleDateString()}
        </span>
        <span className="text-[10px] text-gray-600 dark:text-gray-300">
          {new Date(dates[dates.length - 1]).toLocaleDateString()}
        </span>
      </div>
    </div>
  );
}

/**
 * Article Link - article link with source quality badges
 */
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
      className="block p-2 rounded bg-white dark:bg-gray-800 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors cursor-pointer"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <p className="text-xs font-medium text-gray-900 dark:text-gray-100 line-clamp-1">{title}</p>
          <p className="text-xs text-gray-700 dark:text-gray-300 dark:text-gray-300 mt-0.5">{source}</p>
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
        <ExternalLink className="w-3 h-3 text-gray-600 dark:text-gray-300 shrink-0" />
      </div>
    </a>
  );
}
