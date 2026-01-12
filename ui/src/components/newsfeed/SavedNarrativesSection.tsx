/**
 * Saved Narratives Section - Display saved narratives/themes
 * Used in the Saved tab to show user-saved narrative themes
 */

import { useState, useEffect } from 'react';
import {
  Brain,
  Bookmark,
  BookmarkX,
  ChevronDown,
  ChevronUp,
  MoreVertical,
  Share2,
  Download,
  FileText,
  Table,
  Loader2,
} from 'lucide-react';
import { Card, CardContent } from '../ui/card';
import { ShareModal, type ShareNarrativeData } from '../ShareModal';
import { ExportService } from '../../services/exportService';

interface SavedNarrative {
  name: string;
  description?: string;
  sentiment?: string;
  confidence?: number;
  article_count?: number;
  source_count?: number;
  key_entities?: string[];
  saved_at?: string;
  topic?: string;
}

interface SavedNarrativesSectionProps {
  className?: string;
  onNarrativeClick?: (name: string) => void;
}

export function SavedNarrativesSection({
  className = '',
  onNarrativeClick,
}: SavedNarrativesSectionProps) {
  const [savedNarratives, setSavedNarratives] = useState<SavedNarrative[]>([]);
  const [loading, setLoading] = useState(true);
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [menuOpenId, setMenuOpenId] = useState<string | null>(null);
  const [showShareModal, setShowShareModal] = useState(false);
  const [shareData, setShareData] = useState<ShareNarrativeData | null>(null);

  // Load saved narratives from localStorage (or could be API)
  useEffect(() => {
    loadSavedNarratives();
  }, []);

  const loadSavedNarratives = () => {
    setLoading(true);
    try {
      const saved = localStorage.getItem('savedNarratives');
      if (saved) {
        setSavedNarratives(JSON.parse(saved));
      }
    } catch (e) {
      console.error('Failed to load saved narratives:', e);
    } finally {
      setLoading(false);
    }
  };

  const handleUnsave = (name: string) => {
    const updated = savedNarratives.filter(n => n.name !== name);
    setSavedNarratives(updated);
    localStorage.setItem('savedNarratives', JSON.stringify(updated));
    setMenuOpenId(null);
  };

  const handleShare = (narrative: SavedNarrative) => {
    setShareData({
      type: 'narrative',
      narrative_name: narrative.name,
      description: narrative.description,
      topic: narrative.topic,
      sentiment: narrative.sentiment,
      confidence: narrative.confidence,
      article_count: narrative.article_count,
      source_count: narrative.source_count,
      key_entities: narrative.key_entities,
    });
    setShowShareModal(true);
    setMenuOpenId(null);
  };

  const handleExportMarkdown = (narrative: SavedNarrative) => {
    const theme = {
      theme_name: narrative.name,
      theme_summary: narrative.description,
      sentiment: narrative.sentiment,
      confidence: narrative.confidence,
      article_count: narrative.article_count,
      source_count: narrative.source_count,
      key_entities: narrative.key_entities,
    };
    ExportService.exportNarrativesMarkdown([theme as any], narrative.topic);
    setMenuOpenId(null);
  };

  const handleExportCSV = (narrative: SavedNarrative) => {
    const theme = {
      theme_name: narrative.name,
      theme_summary: narrative.description,
      sentiment: narrative.sentiment,
      confidence: narrative.confidence,
      article_count: narrative.article_count,
      source_count: narrative.source_count,
      key_entities: narrative.key_entities,
    };
    ExportService.exportNarrativesCSV([theme as any]);
    setMenuOpenId(null);
  };

  // Empty state
  if (!loading && savedNarratives.length === 0) {
    return (
      <section className={className}>
        <div className="flex items-center gap-2 mb-3">
          <Brain className="w-5 h-5 text-indigo-500" />
          <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Saved Narratives</h3>
        </div>
        <p className="text-sm text-gray-700 dark:text-gray-300 dark:text-gray-600 dark:text-gray-600 dark:text-gray-400">
          No saved narratives yet. Use the menu on narrative cards to save them.
        </p>
      </section>
    );
  }

  return (
    <section className={className}>
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Brain className="w-5 h-5 text-indigo-500" />
          <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Saved Narratives</h3>
          <span className="text-sm text-gray-700 dark:text-gray-300 dark:text-gray-600 dark:text-gray-600 dark:text-gray-400">
            ({savedNarratives.length})
          </span>
        </div>
        <button
          onClick={() => setIsCollapsed(!isCollapsed)}
          className="p-1 hover:bg-gray-100 dark:hover:bg-gray-700 rounded transition-colors"
        >
          {isCollapsed ? (
            <ChevronDown className="w-5 h-5 text-gray-700 dark:text-gray-300" />
          ) : (
            <ChevronUp className="w-5 h-5 text-gray-700 dark:text-gray-300" />
          )}
        </button>
      </div>

      {/* Loading state */}
      {loading && (
        <div className="flex items-center justify-center py-8">
          <Loader2 className="w-6 h-6 animate-spin text-gray-600 dark:text-gray-600 dark:text-gray-400" />
        </div>
      )}

      {/* Content */}
      {!loading && !isCollapsed && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {savedNarratives.map((narrative) => (
            <Card
              key={narrative.name}
              className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 hover:shadow-md transition-shadow cursor-pointer"
              onClick={() => onNarrativeClick?.(narrative.name)}
            >
              <CardContent className="p-4">
                {/* Header with menu */}
                <div className="flex items-start justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <span className="flex items-center gap-1 text-[10px] bg-amber-100 dark:bg-amber-900/50 text-amber-700 dark:text-amber-300 px-1.5 py-0.5 rounded">
                      <Bookmark className="w-3 h-3 fill-current" />
                      Saved
                    </span>
                    {narrative.topic && (
                      <span className="text-[10px] text-gray-700 dark:text-gray-300 dark:text-gray-600 dark:text-gray-600 dark:text-gray-400">
                        {narrative.topic}
                      </span>
                    )}
                  </div>
                  {/* Menu */}
                  <div className="relative">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setMenuOpenId(menuOpenId === narrative.name ? null : narrative.name);
                      }}
                      className="p-1 hover:bg-gray-100 dark:hover:bg-gray-700 rounded transition-colors"
                    >
                      <MoreVertical className="w-4 h-4 text-gray-700 dark:text-gray-300" />
                    </button>
                    {menuOpenId === narrative.name && (
                      <>
                        <div
                          className="fixed inset-0 z-10"
                          onClick={(e) => {
                            e.stopPropagation();
                            setMenuOpenId(null);
                          }}
                        />
                        <div className="absolute right-0 top-full mt-1 w-40 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg z-20 py-1">
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              handleUnsave(narrative.name);
                            }}
                            className="w-full px-3 py-2 text-left text-sm text-gray-900 dark:text-gray-100 hover:bg-gray-100 dark:hover:bg-gray-700 flex items-center gap-2"
                          >
                            <BookmarkX className="w-4 h-4 text-gray-700 dark:text-gray-600 dark:text-gray-600 dark:text-gray-600 dark:text-gray-400" />
                            Unsave
                          </button>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              handleShare(narrative);
                            }}
                            className="w-full px-3 py-2 text-left text-sm text-gray-900 dark:text-gray-100 hover:bg-gray-100 dark:hover:bg-gray-700 flex items-center gap-2"
                          >
                            <Share2 className="w-4 h-4 text-gray-700 dark:text-gray-600 dark:text-gray-600 dark:text-gray-600 dark:text-gray-400" />
                            Share
                          </button>
                          <div className="h-px bg-gray-200 dark:bg-gray-700 my-1" />
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              handleExportMarkdown(narrative);
                            }}
                            className="w-full px-3 py-2 text-left text-sm text-gray-900 dark:text-gray-100 hover:bg-gray-100 dark:hover:bg-gray-700 flex items-center gap-2"
                          >
                            <FileText className="w-4 h-4 text-gray-700 dark:text-gray-600 dark:text-gray-600 dark:text-gray-600 dark:text-gray-400" />
                            Export Markdown
                          </button>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              handleExportCSV(narrative);
                            }}
                            className="w-full px-3 py-2 text-left text-sm text-gray-900 dark:text-gray-100 hover:bg-gray-100 dark:hover:bg-gray-700 flex items-center gap-2"
                          >
                            <Table className="w-4 h-4 text-gray-700 dark:text-gray-600 dark:text-gray-600 dark:text-gray-600 dark:text-gray-400" />
                            Export CSV
                          </button>
                        </div>
                      </>
                    )}
                  </div>
                </div>

                {/* Title */}
                <h4 className="font-semibold text-gray-900 dark:text-gray-100 text-sm mb-2 line-clamp-2">
                  {narrative.name}
                </h4>

                {/* Description */}
                {narrative.description && (
                  <p className="text-xs text-gray-600 dark:text-gray-600 dark:text-gray-400 line-clamp-3 mb-2">
                    {narrative.description}
                  </p>
                )}

                {/* Stats */}
                <div className="flex items-center gap-3 text-xs text-gray-700 dark:text-gray-300 dark:text-gray-600 dark:text-gray-600 dark:text-gray-400">
                  {narrative.article_count && (
                    <span>{narrative.article_count} articles</span>
                  )}
                  {narrative.source_count && (
                    <span>{narrative.source_count} sources</span>
                  )}
                  {narrative.confidence && (
                    <span>{Math.round(narrative.confidence)}% confidence</span>
                  )}
                </div>

                {/* Key entities */}
                {narrative.key_entities && narrative.key_entities.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-2">
                    {narrative.key_entities.slice(0, 3).map((entity, i) => (
                      <span
                        key={i}
                        className="text-[10px] bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-600 dark:text-gray-600 dark:text-gray-400 px-1.5 py-0.5 rounded"
                      >
                        {entity}
                      </span>
                    ))}
                    {narrative.key_entities.length > 3 && (
                      <span className="text-[10px] text-gray-600 dark:text-gray-600 dark:text-gray-400">
                        +{narrative.key_entities.length - 3} more
                      </span>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>
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
    </section>
  );
}

// Helper function to save a narrative (called from NarrativeInsightsSection)
export function saveNarrative(narrative: {
  name: string;
  description?: string;
  sentiment?: string;
  confidence?: number;
  article_count?: number;
  source_count?: number;
  key_entities?: string[];
  topic?: string;
}) {
  try {
    const saved = localStorage.getItem('savedNarratives');
    const narratives: SavedNarrative[] = saved ? JSON.parse(saved) : [];

    // Check if already saved
    if (narratives.some(n => n.name === narrative.name)) {
      return false;
    }

    narratives.push({
      ...narrative,
      saved_at: new Date().toISOString(),
    });

    localStorage.setItem('savedNarratives', JSON.stringify(narratives));
    return true;
  } catch (e) {
    console.error('Failed to save narrative:', e);
    return false;
  }
}

// Helper function to unsave a narrative
export function unsaveNarrative(name: string) {
  try {
    const saved = localStorage.getItem('savedNarratives');
    if (!saved) return false;

    const narratives: SavedNarrative[] = JSON.parse(saved);
    const updated = narratives.filter(n => n.name !== name);
    localStorage.setItem('savedNarratives', JSON.stringify(updated));
    return true;
  } catch (e) {
    console.error('Failed to unsave narrative:', e);
    return false;
  }
}

// Helper function to get saved narrative names
export function getSavedNarrativeNames(): string[] {
  try {
    const saved = localStorage.getItem('savedNarratives');
    if (!saved) return [];
    const narratives: SavedNarrative[] = JSON.parse(saved);
    return narratives.map(n => n.name);
  } catch (e) {
    console.error('Failed to get saved narrative names:', e);
    return [];
  }
}
