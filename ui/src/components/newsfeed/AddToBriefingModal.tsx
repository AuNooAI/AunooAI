/**
 * Add to Briefing Modal
 * Modal for selecting which briefing to add an article or incident to
 */

import { useState, useEffect } from 'react';
import {
  X,
  Plus,
  Newspaper,
  FileText,
  AlertTriangle,
  Loader2,
  Check,
} from 'lucide-react';
import {
  fetchBriefings,
  createBriefing,
  addArticleToBriefing,
  addIncidentToBriefing,
  addEmergingTopicToBriefing,
  type BriefingSummary,
} from '../../services/briefingDeskApi';
import { TrendingUp } from 'lucide-react';

interface AddToBriefingModalProps {
  isOpen: boolean;
  onClose: () => void;
  itemType: 'article' | 'incident' | 'emerging_topic';
  article?: {
    uri: string;
    title: string;
    summary?: string;
    source?: string;
    publication_date?: string;
    topic?: string;
    url?: string;
    sentiment?: string;
    bias?: string;
    category?: string;
    analysis?: {
      key_insight?: string;
      executive_takeaway?: string;
      strategic_relevance?: string;
      category?: string;
      time_horizon?: string;
      risk_opportunity?: string;
      signal_strength?: string;
    };
  };
  incident?: {
    name: string;
    title?: string;
    type?: string;
    significance?: string;
    description?: string;
    summary?: string;
    topic?: string;
    timeline?: string;
    first_seen?: string;
    last_seen?: string;
    entities?: string[];
    article_uris?: string[];
    organizational_relevance?: string;
    strategic_relevance?: string;
    plausibility?: string;
    source_quality?: string;
    credibility_summary?: string;
    investigation_leads?: string[];
    analyst_notes?: Array<{
      id: string;
      timestamp: string;
      analyst: string;
      comment: string;
    }>;
    analysis?: {
      key_insight?: string;
      strategic_relevance?: string;
      category?: string;
      time_horizon?: string;
      risk_opportunity?: string;
    };
  };
  emergingTopic?: {
    name: string;
    summary?: string;
    description?: string;
    why_emerging?: string;
    key_takeaway?: string;
    article_count?: number;
    velocity?: string;
    trend_score?: Record<string, unknown>;
    key_entities?: string[];
    representative_keywords?: string[];
    key_themes?: string[];
    topic?: string;
    // Rich analysis fields
    implications?: Record<string, unknown>;
    organization_implications?: Record<string, unknown>;
    signals?: Record<string, unknown>;
    actors?: Record<string, unknown>;
    events?: Record<string, unknown>;
    // Source articles with links
    source_articles?: Array<{
      title: string;
      url?: string;
      source?: string;
      date?: string;
      summary?: string;
    }>;
  };
  onSuccess?: () => void;
}

export function AddToBriefingModal({
  isOpen,
  onClose,
  itemType,
  article,
  incident,
  emergingTopic,
  onSuccess,
}: AddToBriefingModalProps) {
  const [briefings, setBriefings] = useState<BriefingSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [adding, setAdding] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [newBriefingName, setNewBriefingName] = useState('');
  const [creating, setCreating] = useState(false);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Fetch briefings on open
  useEffect(() => {
    if (isOpen) {
      loadBriefings();
    }
  }, [isOpen]);

  const loadBriefings = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchBriefings();
      // Show all briefings (draft and finalized)
      setBriefings(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load briefings');
    } finally {
      setLoading(false);
    }
  };

  const handleAddToBriefing = async (briefingId: number, briefingName: string) => {
    setAdding(briefingId);
    setError(null);
    setSuccessMessage(null);

    try {
      if (itemType === 'article' && article) {
        await addArticleToBriefing(briefingId, article);
      } else if (itemType === 'incident' && incident) {
        await addIncidentToBriefing(briefingId, incident);
      } else if (itemType === 'emerging_topic' && emergingTopic) {
        await addEmergingTopicToBriefing(briefingId, emergingTopic);
      }

      setSuccessMessage(`Added to "${briefingName}"`);
      setTimeout(() => {
        onSuccess?.();
        onClose();
      }, 1000);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to add item');
    } finally {
      setAdding(null);
    }
  };

  const handleCreateAndAdd = async () => {
    if (!newBriefingName.trim()) return;

    setCreating(true);
    setError(null);

    try {
      const result = await createBriefing(newBriefingName.trim());
      const briefingId = result.briefing_id;

      // Add item to the new briefing
      if (itemType === 'article' && article) {
        await addArticleToBriefing(briefingId, article);
      } else if (itemType === 'incident' && incident) {
        await addIncidentToBriefing(briefingId, incident);
      }

      setSuccessMessage(`Created "${newBriefingName}" and added item`);
      setTimeout(() => {
        onSuccess?.();
        onClose();
      }, 1000);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to create briefing');
    } finally {
      setCreating(false);
    }
  };

  if (!isOpen) return null;

  const itemTitle =
    itemType === 'article'
      ? article?.title || 'Article'
      : incident?.name || incident?.title || 'Incident';

  return (
    <div className="fixed inset-0 z-[1200] flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/50"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="relative bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-md mx-4 max-h-[80vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-gray-700">
          <div className="flex items-center gap-2">
            <Newspaper className="w-5 h-5 text-pink-500" />
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
              Add to Briefing
            </h2>
          </div>
          <button
            onClick={onClose}
            className="p-1 hover:bg-gray-100 dark:hover:bg-gray-700 rounded"
          >
            <X className="w-5 h-5 text-gray-500" />
          </button>
        </div>

        {/* Item being added */}
        <div className="px-4 py-3 bg-gray-50 dark:bg-gray-900/50 border-b border-gray-200 dark:border-gray-700">
          <div className="flex items-start gap-2">
            {itemType === 'article' ? (
              <FileText className="w-4 h-4 text-blue-500 mt-0.5 flex-shrink-0" />
            ) : (
              <AlertTriangle className="w-4 h-4 text-amber-500 mt-0.5 flex-shrink-0" />
            )}
            <div className="min-w-0">
              <p className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
                {itemTitle}
              </p>
              <p className="text-xs text-gray-500 dark:text-gray-400">
                {itemType === 'article' ? 'Article' : 'Incident'}
                {(article?.topic || incident?.topic) && ` from ${article?.topic || incident?.topic}`}
              </p>
            </div>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4">
          {/* Success message */}
          {successMessage && (
            <div className="mb-4 p-3 bg-green-50 dark:bg-green-900/30 border border-green-200 dark:border-green-800 rounded-lg flex items-center gap-2">
              <Check className="w-5 h-5 text-green-600 dark:text-green-400" />
              <span className="text-sm text-green-800 dark:text-green-200">{successMessage}</span>
            </div>
          )}

          {/* Error message */}
          {error && (
            <div className="mb-4 p-3 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 rounded-lg text-sm text-red-800 dark:text-red-200">
              {error}
            </div>
          )}

          {/* Loading state */}
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="w-6 h-6 animate-spin text-gray-400" />
            </div>
          ) : (
            <>
              {/* Existing briefings */}
              {briefings.length > 0 && (
                <div className="space-y-2 mb-4">
                  <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                    Add to existing briefing
                  </p>
                  {briefings.map((briefing) => {
                    const isFinalized = briefing.status === 'finalized';
                    const isDisabled = adding !== null || successMessage !== null || isFinalized;

                    return (
                      <button
                        key={briefing.id}
                        onClick={() => !isFinalized && handleAddToBriefing(briefing.id, briefing.name)}
                        disabled={isDisabled}
                        title={isFinalized ? 'Cannot add to finalized briefings' : undefined}
                        className={`w-full flex items-center justify-between p-3 bg-white dark:bg-gray-800 border rounded-lg transition-colors ${
                          isFinalized
                            ? 'border-green-200 dark:border-green-800 opacity-60 cursor-not-allowed'
                            : 'border-gray-200 dark:border-gray-700 hover:border-pink-300 dark:hover:border-pink-600 hover:bg-pink-50 dark:hover:bg-pink-900/20'
                        } ${isDisabled && !isFinalized ? 'opacity-50' : ''}`}
                      >
                        <div className="flex items-center gap-3 min-w-0">
                          <Newspaper className={`w-4 h-4 flex-shrink-0 ${
                            isFinalized ? 'text-green-500' : 'text-gray-400'
                          }`} />
                          <div className="text-left min-w-0">
                            <div className="flex items-center gap-2">
                              <p className={`text-sm font-medium truncate ${
                                isFinalized ? 'text-gray-500 dark:text-gray-400' : 'text-gray-900 dark:text-gray-100'
                              }`}>
                                {briefing.name}
                              </p>
                              {isFinalized && (
                                <Check className="w-3 h-3 text-green-500 flex-shrink-0" />
                              )}
                            </div>
                            <p className="text-xs text-gray-500 dark:text-gray-400">
                              {briefing.articles_count} articles, {briefing.incidents_count} incidents
                              {isFinalized && ' • Finalized (read-only)'}
                            </p>
                          </div>
                        </div>
                        {adding === briefing.id ? (
                          <Loader2 className="w-4 h-4 animate-spin text-pink-500" />
                        ) : isFinalized ? (
                          <span className="text-[10px] text-gray-400">Locked</span>
                        ) : (
                          <Plus className="w-4 h-4 text-gray-400" />
                        )}
                      </button>
                    );
                  })}
                </div>
              )}

              {/* Create new briefing */}
              {showCreateForm ? (
                <div className="space-y-3">
                  <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                    Create new briefing
                  </p>
                  <input
                    type="text"
                    value={newBriefingName}
                    onChange={(e) => setNewBriefingName(e.target.value)}
                    placeholder="Briefing name"
                    className="w-full px-3 py-2 border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-pink-500"
                    autoFocus
                    disabled={creating || successMessage !== null}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && newBriefingName.trim()) {
                        handleCreateAndAdd();
                      }
                    }}
                  />
                  <div className="flex gap-2">
                    <button
                      onClick={() => {
                        setShowCreateForm(false);
                        setNewBriefingName('');
                      }}
                      disabled={creating}
                      className="flex-1 px-3 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
                    >
                      Cancel
                    </button>
                    <button
                      onClick={handleCreateAndAdd}
                      disabled={!newBriefingName.trim() || creating || successMessage !== null}
                      className="flex-1 px-3 py-2 text-sm bg-pink-500 text-white rounded-lg hover:bg-pink-600 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                    >
                      {creating ? (
                        <>
                          <Loader2 className="w-4 h-4 animate-spin" />
                          Creating...
                        </>
                      ) : (
                        <>
                          <Plus className="w-4 h-4" />
                          Create & Add
                        </>
                      )}
                    </button>
                  </div>
                </div>
              ) : (
                <button
                  onClick={() => setShowCreateForm(true)}
                  disabled={successMessage !== null}
                  className="w-full flex items-center justify-center gap-2 p-3 border-2 border-dashed border-gray-200 dark:border-gray-700 rounded-lg text-gray-600 dark:text-gray-400 hover:border-pink-300 dark:hover:border-pink-600 hover:text-pink-600 dark:hover:text-pink-400 transition-colors disabled:opacity-50"
                >
                  <Plus className="w-4 h-4" />
                  Create new briefing
                </button>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
