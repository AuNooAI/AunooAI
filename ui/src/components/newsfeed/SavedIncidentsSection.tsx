/**
 * Saved Incidents Section - Display saved incidents
 * Fetches incidents directly from saved_incidents table
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
  Loader2,
  MessageSquare,
  Send,
  User,
  Newspaper,
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
import { getSavedIncidents, deleteSavedIncident, addNoteToIncident, type SavedIncident, type AnalystNote } from '../../services/newsFeedApi';
import { Skeleton } from '../ui/skeleton';
import { Card, CardContent } from '../ui/card';
import { AgentSignalBadge, extractSignalTags } from './AgentSignalBadge';
import { openAuspexWithQuery } from '../../utils/auspexEvents';
import { ShareModal, type ShareIncidentData } from '../ShareModal';
import { ExportService } from '../../services/exportService';
import {
  getIncidentSignalTags,
  formatDisplayDate,
  formatNoteDate,
  NotesBadge,
  TimelineRuler,
  ArticleLink,
  getStoredAnalystName,
  setStoredAnalystName,
} from './incidentUtils';
import { AddToBriefingModal } from './AddToBriefingModal';

interface SavedIncidentsSectionProps {
  topic?: string;
  onArticleClick?: (article: { uri: string; title?: string }) => void;
  isFullTab?: boolean;
  refreshTrigger?: number; // Increment to trigger refresh
  onUnsave?: () => void; // Callback when an incident is unsaved
}

// Convert SavedIncident to Incident format for display
// Exported for reuse in NewsFeedPage to merge promoted incidents
export function savedToIncident(saved: SavedIncident): Incident {
  return {
    name: saved.name,
    title: saved.name,
    type: saved.type || 'event',
    significance: saved.significance || 'medium',
    description: saved.description,
    summary: saved.description,
    topic: saved.topic,
    entities: saved.entities,
    timeline: saved.timeline,
    organizational_relevance: saved.organizational_relevance,
    plausibility: saved.plausibility,
    source_quality: saved.source_quality,
    article_uris: saved.article_uris,
    article_metadata: saved.article_metadata,
    investigation_leads: saved.investigation_leads,
    analyst_notes: saved.analyst_notes,
  } as Incident;
}

export function SavedIncidentsSection({
  topic,
  onArticleClick,
  isFullTab = false,
  refreshTrigger,
  onUnsave,
}: SavedIncidentsSectionProps) {
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [selectedIncidentId, setSelectedIncidentId] = useState<string | null>(null);
  const [savedIncidents, setSavedIncidents] = useState<Incident[]>([]);
  const [loading, setLoading] = useState(false);

  // Share modal state
  const [showShareModal, setShowShareModal] = useState(false);
  const [shareData, setShareData] = useState<ShareIncidentData | null>(null);

  // Add to Briefing modal state
  const [showAddToBriefingModal, setShowAddToBriefingModal] = useState(false);
  const [selectedIncidentForBriefing, setSelectedIncidentForBriefing] = useState<Incident | null>(null);

  // Download dropdown state
  const [showDownloadDropdown, setShowDownloadDropdown] = useState(false);

  // Arrow scroll navigation (only for compact mode)
  const scrollRef = useRef<HTMLDivElement>(null);
  const [showLeftArrow, setShowLeftArrow] = useState(false);
  const [showRightArrow, setShowRightArrow] = useState(false);

  // Fetch saved incidents from saved_incidents table
  useEffect(() => {
    console.log('[SavedIncidentsSection] Fetching incidents for topic:', topic, 'refreshTrigger:', refreshTrigger);
    // Fetch all incidents when no topic filter, or filter by topic when specified
    setLoading(true);
    getSavedIncidents(topic || undefined)
      .then(incidents => {
        console.log('[SavedIncidentsSection] Received incidents:', incidents);
        setSavedIncidents(incidents.map(savedToIncident));
      })
      .catch(err => {
        console.error('Failed to load saved incidents:', err);
        setSavedIncidents([]);
      })
      .finally(() => setLoading(false));
  }, [topic, refreshTrigger]);

  // Handle unsave/delete incident
  const handleUnsaveIncident = async (incidentName: string) => {
    if (!topic) return;
    try {
      console.log('[SavedIncidentsSection] Attempting to unsave incident:', incidentName, 'topic:', topic);
      const success = await deleteSavedIncident(incidentName, topic);
      console.log('[SavedIncidentsSection] Delete result:', success);
      if (success) {
        setSavedIncidents(prev => prev.filter(i => (i.name || i.title) !== incidentName));
        // Notify parent to refresh promoted incidents
        onUnsave?.();
      } else {
        console.error('[SavedIncidentsSection] Failed to delete incident - API returned false');
      }
    } catch (err) {
      console.error('Failed to unsave incident:', err);
    }
  };

  // Find selected incident for expansion
  const selectedIncident = selectedIncidentId
    ? savedIncidents.find((i, idx) => (i.id || i.name || `saved-incident-${idx}`) === selectedIncidentId)
    : null;

  const handleCompactCardClick = (incidentId: string) => {
    setSelectedIncidentId(selectedIncidentId === incidentId ? null : incidentId);
  };

  // Share handler - opens modal with incident data
  // Handle Add to Briefing action
  const handleAddToBriefing = (incident: Incident) => {
    setSelectedIncidentForBriefing(incident);
    setShowAddToBriefingModal(true);
  };

  const handleShare = (incident: Incident) => {
    const name = incident.name || incident.title || 'Unnamed Incident';

    // Map articles with proper field names for email API
    const articles = incident.articles || [];
    const articleMetadata = incident.article_metadata || [];
    const mappedArticles = articles.map((article, i) => {
      const metadata = articleMetadata[i];
      return {
        title: article.title || metadata?.title || 'Untitled',
        source: article.news_source || metadata?.news_source || article.source || '',
        url: article.uri || '',
        summary: article.summary || '',
      };
    });

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
      analyst_notes: incident.analyst_notes,
      articles: mappedArticles.length > 0 ? mappedArticles : undefined,
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
                  <div className="absolute right-0 top-full mt-1 w-56 bg-white dark:bg-[#232326] border border-gray-200 dark:border-gray-600 rounded-lg shadow-lg z-20 py-1">
                    <button
                      type="button"
                      onClick={() => {
                        ExportService.exportIncidentsPDF(savedIncidents, topic);
                        setShowDownloadDropdown(false);
                      }}
                      className="w-full px-4 py-2 text-left text-sm hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors flex items-center gap-2 cursor-pointer"
                    >
                      <FileText className="w-4 h-4 text-pink-500" />
                      <span className="text-gray-800 dark:text-gray-100">Export as PDF (Styled)</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        ExportService.exportIncidentsStyledMarkdown(savedIncidents, topic);
                        setShowDownloadDropdown(false);
                      }}
                      className="w-full px-4 py-2 text-left text-sm hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors flex items-center gap-2 cursor-pointer"
                    >
                      <FileText className="w-4 h-4 text-blue-500" />
                      <span className="text-gray-800 dark:text-gray-100">Export as Markdown (Styled)</span>
                    </button>
                    <div className="border-t border-gray-200 dark:border-gray-600 my-1"></div>
                    <button
                      type="button"
                      onClick={() => {
                        ExportService.exportIncidentsMarkdown(savedIncidents, topic);
                        setShowDownloadDropdown(false);
                      }}
                      className="w-full px-4 py-2 text-left text-sm hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors flex items-center gap-2 cursor-pointer"
                    >
                      <FileText className="w-4 h-4 text-gray-400" />
                      <span className="text-gray-800 dark:text-gray-100">Export as Markdown (Plain)</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        ExportService.exportIncidentsCSV(savedIncidents);
                        setShowDownloadDropdown(false);
                      }}
                      className="w-full px-4 py-2 text-left text-sm hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors flex items-center gap-2 cursor-pointer"
                    >
                      <Table className="w-4 h-4 text-gray-400" />
                      <span className="text-gray-800 dark:text-gray-100">Export as CSV</span>
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
                    onUnsave={handleUnsaveIncident}
                    onArticleClick={onArticleClick}
                    onShare={handleShare}
                    onAddToBriefing={handleAddToBriefing}
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
                  onUnsave={handleUnsaveIncident}
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

        {/* Add to Briefing Modal */}
        {showAddToBriefingModal && selectedIncidentForBriefing && (
          <AddToBriefingModal
            isOpen={showAddToBriefingModal}
            onClose={() => {
              setShowAddToBriefingModal(false);
              setSelectedIncidentForBriefing(null);
            }}
            itemType="incident"
            incident={{
              name: selectedIncidentForBriefing.name || selectedIncidentForBriefing.title || 'Unnamed Incident',
              title: selectedIncidentForBriefing.title,
              type: selectedIncidentForBriefing.type,
              significance: selectedIncidentForBriefing.significance,
              description: selectedIncidentForBriefing.description,
              summary: selectedIncidentForBriefing.summary,
              topic: selectedIncidentForBriefing.topic || topic,
              timeline: Array.isArray(selectedIncidentForBriefing.timeline)
                ? selectedIncidentForBriefing.timeline[0]
                : selectedIncidentForBriefing.timeline,
              first_seen: selectedIncidentForBriefing.first_seen,
              last_seen: selectedIncidentForBriefing.last_seen,
              entities: selectedIncidentForBriefing.entities,
              article_uris: selectedIncidentForBriefing.article_uris,
              organizational_relevance: selectedIncidentForBriefing.organizational_relevance,
              plausibility: selectedIncidentForBriefing.plausibility,
              source_quality: selectedIncidentForBriefing.source_quality,
              credibility_summary: selectedIncidentForBriefing.credibility_summary,
              investigation_leads: selectedIncidentForBriefing.investigation_leads,
              analyst_notes: selectedIncidentForBriefing.analyst_notes,
            }}
          />
        )}
      </div>
    );
  }

  // Compact Section View (original horizontal scroll)
  // Don't render if no saved incidents
  if (savedIncidents.length === 0 && !loading) {
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
                      onUnsave={handleUnsaveIncident}
                      onArticleClick={onArticleClick}
                      onShare={handleShare}
                      onAddToBriefing={handleAddToBriefing}
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

      {/* Add to Briefing Modal */}
      {showAddToBriefingModal && selectedIncidentForBriefing && (
        <AddToBriefingModal
          isOpen={showAddToBriefingModal}
          onClose={() => {
            setShowAddToBriefingModal(false);
            setSelectedIncidentForBriefing(null);
          }}
          itemType="incident"
          incident={{
            name: selectedIncidentForBriefing.name || selectedIncidentForBriefing.title || 'Unnamed Incident',
            title: selectedIncidentForBriefing.title,
            type: selectedIncidentForBriefing.type,
            significance: selectedIncidentForBriefing.significance,
            description: selectedIncidentForBriefing.description,
            summary: selectedIncidentForBriefing.summary,
            topic: selectedIncidentForBriefing.topic || topic,
            timeline: Array.isArray(selectedIncidentForBriefing.timeline)
              ? selectedIncidentForBriefing.timeline[0]
              : selectedIncidentForBriefing.timeline,
            first_seen: selectedIncidentForBriefing.first_seen,
            last_seen: selectedIncidentForBriefing.last_seen,
            entities: selectedIncidentForBriefing.entities,
            article_uris: selectedIncidentForBriefing.article_uris,
            organizational_relevance: selectedIncidentForBriefing.organizational_relevance,
            plausibility: selectedIncidentForBriefing.plausibility,
            source_quality: selectedIncidentForBriefing.source_quality,
            credibility_summary: selectedIncidentForBriefing.credibility_summary,
            investigation_leads: selectedIncidentForBriefing.investigation_leads,
            analyst_notes: selectedIncidentForBriefing.analyst_notes,
          }}
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
  onAddToBriefing?: (incident: Incident) => void;
  onClick?: () => void;
  isFullWidth?: boolean;
}

function SavedIncidentCard({ incident, onUnsave, onArticleClick, onShare, onAddToBriefing, onClick, isFullWidth = false }: SavedIncidentCardProps) {
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

  // Handle add to briefing action
  const handleAddToBriefingClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    setShowMenu(false);
    onAddToBriefing?.(incident);
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
                    onClick={handleAddToBriefingClick}
                    className="w-full px-3 py-2 text-left text-sm text-gray-900 dark:text-gray-100 hover:bg-gray-100 dark:hover:bg-gray-700 flex items-center gap-2"
                  >
                    <Newspaper className="w-4 h-4 text-pink-500" />
                    Add to Briefing
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

        {/* Title with notes badge */}
        <div className="flex items-start gap-2 mb-2">
          <h4 className="font-semibold text-gray-900 dark:text-gray-100 text-sm flex-1">{name}</h4>
          <NotesBadge count={incident.analyst_notes?.length ?? 0} />
        </div>

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
  // State for analyst notes - initialized from incident data
  const [analystNotes, setAnalystNotes] = useState<AnalystNote[]>(
    (incident as any).analyst_notes || []
  );

  // Get display values with fallbacks
  const name = incident.name || incident.title || 'Unnamed Incident';
  const description = incident.description || incident.summary || '';
  const type = incident.type || 'event';
  const significance = incident.significance || 'medium';
  const signalTags = getIncidentSignalTags(incident);
  const topic = incident.topic || '';

  // Handle new note added
  const handleNoteAdded = (note: AnalystNote) => {
    setAnalystNotes(prev => [note, ...prev]);
  };

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

          {/* Analyst Notes Section */}
          <AnalystNotesSection
            notes={analystNotes}
            incidentName={name}
            topic={topic}
            savedId={(incident as any)._saved_id}
            onNoteAdded={handleNoteAdded}
          />

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
 * Analyst Notes Section - display and add analyst notes
 * Exported for reuse in HighlightsSection
 */
export interface AnalystNotesSectionProps {
  notes: AnalystNote[];
  incidentName: string;
  topic: string;
  savedId?: number;  // Unique database ID for the saved incident
  onNoteAdded: (note: AnalystNote) => void;
}

export function AnalystNotesSection({ notes, incidentName, topic, savedId, onNoteAdded }: AnalystNotesSectionProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [analystName, setAnalystName] = useState(getStoredAnalystName);
  const [comment, setComment] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!analystName.trim() || !comment.trim() || isSubmitting) return;

    setIsSubmitting(true);
    setError(null);

    try {
      // Save analyst name for future use
      setStoredAnalystName(analystName.trim());

      const result = await addNoteToIncident(
        incidentName,
        topic,
        analystName.trim(),
        comment.trim(),
        savedId  // Pass unique ID for proper targeting
      );

      if (result.success && result.note) {
        onNoteAdded(result.note);
        setComment(''); // Clear comment but keep analyst name
      }
    } catch (err) {
      console.error('Failed to add note:', err);
      setError(err instanceof Error ? err.message : 'Failed to add note');
    } finally {
      setIsSubmitting(false);
    }
  };

  // Collapsed view - just a small button
  if (!isExpanded) {
    return (
      <div className="mt-3 pt-3 border-t border-amber-200 dark:border-amber-700">
        <button
          onClick={() => setIsExpanded(true)}
          className="inline-flex items-center gap-1.5 text-xs text-amber-600 dark:text-amber-400 hover:text-amber-700 dark:hover:text-amber-300 font-medium transition-colors"
        >
          <MessageSquare className="w-3.5 h-3.5" />
          Analyst Notes {notes.length > 0 && `(${notes.length})`}
          <ChevronDown className="w-3 h-3" />
        </button>
      </div>
    );
  }

  // Expanded view
  return (
    <div className="mt-3 pt-3 border-t border-amber-200 dark:border-amber-700">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <MessageSquare className="w-4 h-4 text-amber-600 dark:text-amber-400" />
          <h4 className="text-xs font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wide">
            Analyst Notes ({notes.length})
          </h4>
        </div>
        <button
          onClick={(e) => {
            e.stopPropagation();
            setIsExpanded(false);
          }}
          className="inline-flex items-center gap-1 px-2 py-1 text-xs text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 hover:bg-amber-100 dark:hover:bg-amber-800 rounded transition-colors"
          title="Collapse"
        >
          <ChevronUp className="w-3.5 h-3.5" />
          Hide
        </button>
      </div>

      {/* Add Note Form */}
      <form onSubmit={handleSubmit} className="mb-3 bg-white dark:bg-gray-800 rounded-lg p-3 border border-amber-100 dark:border-amber-800">
        <div className="flex flex-col gap-2">
          <div className="flex items-center gap-2">
            <User className="w-4 h-4 text-gray-400 dark:text-gray-500" />
            <input
              type="text"
              value={analystName}
              onChange={(e) => setAnalystName(e.target.value)}
              placeholder="Your name"
              className="flex-1 text-sm px-2 py-1.5 border border-gray-200 dark:border-gray-600 rounded bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-amber-400 dark:focus:ring-amber-500"
            />
          </div>
          <div className="flex items-start gap-2">
            <MessageSquare className="w-4 h-4 text-gray-400 dark:text-gray-500 mt-2" />
            <textarea
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder="Add a note..."
              rows={2}
              className="flex-1 text-sm px-2 py-1.5 border border-gray-200 dark:border-gray-600 rounded bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-amber-400 dark:focus:ring-amber-500 resize-none"
            />
            <button
              type="submit"
              disabled={!analystName.trim() || !comment.trim() || isSubmitting}
              className="px-3 py-1.5 bg-amber-500 hover:bg-amber-600 disabled:bg-gray-300 dark:disabled:bg-gray-600 text-white rounded text-sm font-medium transition-colors flex items-center gap-1"
            >
              {isSubmitting ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <>
                  <Send className="w-3.5 h-3.5" />
                  Add
                </>
              )}
            </button>
          </div>
          {error && (
            <p className="text-xs text-red-500 dark:text-red-400">{error}</p>
          )}
        </div>
      </form>

      {/* Notes Timeline */}
      {notes.length > 0 && (
        <div className="space-y-3">
          {notes.map((note) => (
            <div key={note.id} className="flex gap-3">
              <div className="flex flex-col items-center">
                <div className="w-2 h-2 bg-amber-400 dark:bg-amber-500 rounded-full" />
                <div className="w-0.5 flex-1 bg-amber-200 dark:bg-amber-700" />
              </div>
              <div className="flex-1 pb-3">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xs font-medium text-gray-700 dark:text-gray-300">
                    {note.analyst}
                  </span>
                  <span className="text-[10px] text-gray-500 dark:text-gray-400">
                    {formatNoteDate(note.timestamp)}
                  </span>
                </div>
                <p className="text-sm text-gray-600 dark:text-gray-300 whitespace-pre-wrap">
                  {note.comment}
                </p>
              </div>
            </div>
          ))}
        </div>
      )}

      {notes.length === 0 && (
        <p className="text-xs text-gray-500 dark:text-gray-400 italic">
          No notes yet. Add the first note above.
        </p>
      )}
    </div>
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
