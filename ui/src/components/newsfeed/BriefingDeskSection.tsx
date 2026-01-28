/**
 * Briefing Desk Section
 * Main tab component for managing curated briefings
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import {
  Newspaper,
  Plus,
  Calendar,
  FileText,
  AlertTriangle,
  Trash2,
  Download,
  Send,
  Loader2,
  ChevronRight,
  X,
  MoreVertical,
  Check,
  Clock,
  Sparkles,
  ExternalLink,
  Pencil,
  Eye,
  Save,
  TrendingUp,
  Bold,
  Italic,
  Heading2,
  List,
  ListOrdered,
  Link,
  Quote,
  Mail,
  FileDown,
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import {
  fetchBriefings,
  fetchBriefing,
  createBriefing,
  deleteBriefing,
  removeArticleFromBriefing,
  removeIncidentFromBriefing,
  removeEmergingTopicFromBriefing,
  finalizeBriefing,
  downloadBriefing,
  downloadBriefingPdf,
  updateBriefingSynthesis,
  updateBriefingPriorityActions,
  updateBriefingThemes,
  reopenBriefing,
  type BriefingSummary,
  type DeskBriefing,
  type BriefingAction,
  type BriefingTheme,
  type FinalizeProgressEvent,
} from '../../services/briefingDeskApi';
import { Skeleton } from '../ui/skeleton';
import { ShareModal, ShareDeskBriefingData } from '../ShareModal';

interface BriefingDeskSectionProps {
  isFullTab?: boolean;
  model?: string;
  organizationalProfile?: string;
  persona?: string;
  onRefreshNeeded?: () => void;
}

// Format date for display
function formatDate(dateStr?: string): string {
  if (!dateStr) return 'Unknown';
  try {
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  } catch {
    return dateStr;
  }
}

export function BriefingDeskSection({ isFullTab = false, model, organizationalProfile, persona, onRefreshNeeded }: BriefingDeskSectionProps) {
  const [briefings, setBriefings] = useState<BriefingSummary[]>([]);
  const [selectedBriefing, setSelectedBriefing] = useState<DeskBriefing | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Create briefing state
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [newBriefingName, setNewBriefingName] = useState('');
  const [newBriefingDescription, setNewBriefingDescription] = useState('');
  const [creating, setCreating] = useState(false);

  // Finalize state
  const [finalizing, setFinalizing] = useState(false);
  const [finalizeProgress, setFinalizeProgress] = useState<FinalizeProgressEvent | null>(null);

  // Share modal state
  const [showShareModal, setShowShareModal] = useState(false);

  // Load briefings
  const loadBriefings = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchBriefings();
      setBriefings(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load briefings');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadBriefings();
  }, [loadBriefings]);

  // Load briefing detail
  const handleSelectBriefing = async (briefingId: number) => {
    setLoadingDetail(true);
    try {
      const detail = await fetchBriefing(briefingId);
      setSelectedBriefing(detail);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load briefing');
    } finally {
      setLoadingDetail(false);
    }
  };

  // Create new briefing
  const handleCreateBriefing = async () => {
    if (!newBriefingName.trim()) return;

    setCreating(true);
    try {
      await createBriefing(newBriefingName.trim(), newBriefingDescription.trim() || undefined);
      setShowCreateForm(false);
      setNewBriefingName('');
      setNewBriefingDescription('');
      await loadBriefings();
      onRefreshNeeded?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to create briefing');
    } finally {
      setCreating(false);
    }
  };

  // Delete briefing
  const handleDeleteBriefing = async (briefingId: number) => {
    if (!confirm('Are you sure you want to delete this briefing?')) return;

    try {
      await deleteBriefing(briefingId);
      if (selectedBriefing?.id === briefingId) {
        setSelectedBriefing(null);
      }
      await loadBriefings();
      onRefreshNeeded?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to delete briefing');
    }
  };

  // Remove article from briefing
  const handleRemoveArticle = async (articleUri: string) => {
    if (!selectedBriefing) return;

    try {
      await removeArticleFromBriefing(selectedBriefing.id, articleUri);
      // Refresh the detail
      const detail = await fetchBriefing(selectedBriefing.id);
      setSelectedBriefing(detail);
      await loadBriefings();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to remove article');
    }
  };

  // Remove incident from briefing
  const handleRemoveIncident = async (incidentName: string) => {
    if (!selectedBriefing) return;

    try {
      await removeIncidentFromBriefing(selectedBriefing.id, incidentName);
      // Refresh the detail
      const detail = await fetchBriefing(selectedBriefing.id);
      setSelectedBriefing(detail);
      await loadBriefings();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to remove incident');
    }
  };

  // Remove emerging topic from briefing
  const handleRemoveEmergingTopic = async (topicName: string) => {
    if (!selectedBriefing) return;

    try {
      await removeEmergingTopicFromBriefing(selectedBriefing.id, topicName);
      // Refresh the detail
      const detail = await fetchBriefing(selectedBriefing.id);
      setSelectedBriefing(detail);
      await loadBriefings();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to remove emerging topic');
    }
  };

  // Finalize briefing
  const handleFinalize = async () => {
    if (!selectedBriefing) return;

    setFinalizing(true);
    setFinalizeProgress(null);

    try {
      await finalizeBriefing(selectedBriefing.id, model || 'gpt-4o', (event) => {
        setFinalizeProgress(event);
      }, {
        organizational_profile: organizationalProfile,
        persona: persona,
      });

      // Refresh after finalization
      const detail = await fetchBriefing(selectedBriefing.id);
      setSelectedBriefing(detail);
      await loadBriefings();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to finalize briefing');
    } finally {
      setFinalizing(false);
      setFinalizeProgress(null);
    }
  };

  // Export briefing
  const handleExport = async (format: 'markdown' | 'html' | 'json') => {
    if (!selectedBriefing) return;

    try {
      await downloadBriefing(selectedBriefing.id, selectedBriefing.name, format);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to export briefing');
    }
  };

  // Update synthesis text
  const handleUpdateSynthesis = async (synthesis: string) => {
    if (!selectedBriefing) return;

    try {
      await updateBriefingSynthesis(selectedBriefing.id, synthesis);
      // Refresh the detail to get updated data
      const detail = await fetchBriefing(selectedBriefing.id);
      setSelectedBriefing(detail);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to update synthesis');
      throw e; // Re-throw so the editor knows it failed
    }
  };

  // Update priority actions
  const handleUpdatePriorityActions = async (actions: BriefingAction[]) => {
    if (!selectedBriefing) return;

    try {
      await updateBriefingPriorityActions(selectedBriefing.id, actions);
      // Refresh the detail to get updated data
      const detail = await fetchBriefing(selectedBriefing.id);
      setSelectedBriefing(detail);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to update priority actions');
      throw e; // Re-throw so the editor knows it failed
    }
  };

  // Reopen a finalized briefing
  const handleReopen = async () => {
    if (!selectedBriefing) return;

    try {
      await reopenBriefing(selectedBriefing.id);
      // Refresh the detail to get updated status
      const detail = await fetchBriefing(selectedBriefing.id);
      setSelectedBriefing(detail);
      await loadBriefings();
      onRefreshNeeded?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to reopen briefing');
    }
  };

  // Update themes
  const handleUpdateThemes = async (themes: BriefingTheme[]) => {
    if (!selectedBriefing) return;

    try {
      await updateBriefingThemes(selectedBriefing.id, themes);
      // Refresh the detail to get updated data
      const detail = await fetchBriefing(selectedBriefing.id);
      setSelectedBriefing(detail);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to update themes');
      throw e; // Re-throw so the editor knows it failed
    }
  };

  // Export as PDF
  const handleExportPdf = async () => {
    if (!selectedBriefing) return;

    try {
      await downloadBriefingPdf(selectedBriefing.id, selectedBriefing.name);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to export PDF');
    }
  };

  // Share via email - open modal
  const handleShareEmail = () => {
    if (!selectedBriefing) return;
    setShowShareModal(true);
  };

  // Build share data for modal
  const getShareData = (): ShareDeskBriefingData | null => {
    if (!selectedBriefing) return null;
    return {
      type: 'desk_briefing',
      briefing_id: selectedBriefing.id,
      name: selectedBriefing.name,
      description: selectedBriefing.description,
      status: selectedBriefing.status,
      synthesis: selectedBriefing.synthesis,
      themes: selectedBriefing.themes,
      priority_actions: selectedBriefing.priority_actions,
      articles: selectedBriefing.articles?.map(a => ({
        title: a.title,
        source: a.source,
        uri: a.uri,
        summary: a.summary,
        category: a.category,
      })),
      incidents: selectedBriefing.incidents?.map(i => ({
        name: i.name,
        type: i.type,
        significance: i.significance,
        description: i.description || i.summary,
        entities: i.entities,
      })),
      emerging_topics: selectedBriefing.emerging_topics?.map(t => ({
        name: t.name,
        summary: t.summary,
        trend_score: typeof t.trend_score === 'object' ? t.trend_score?.composite : undefined,
        velocity: t.velocity,
      })),
    };
  };

  // Loading skeleton
  if (loading) {
    return (
      <div className="p-4">
        <div className="flex items-center justify-between mb-4">
          <Skeleton className="h-6 w-40" />
          <Skeleton className="h-9 w-32" />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-32 rounded-lg" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className={`${isFullTab ? '' : 'p-4'}`}>
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Newspaper className="w-5 h-5 text-pink-500" />
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
            Briefing Desk
          </h2>
          <span className="text-sm text-gray-500 dark:text-gray-400">
            ({briefings.length} briefings)
          </span>
        </div>
        <button
          onClick={() => setShowCreateForm(true)}
          className="flex items-center gap-2 px-3 py-2 bg-pink-500 text-white rounded-lg hover:bg-pink-600 transition-colors"
        >
          <Plus className="w-4 h-4" />
          New Briefing
        </button>
      </div>

      {/* Error display */}
      {error && (
        <div className="mb-4 p-3 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 rounded-lg text-sm text-red-800 dark:text-red-200 flex items-center justify-between">
          <span>{error}</span>
          <button onClick={() => setError(null)} className="p-1 hover:bg-red-100 dark:hover:bg-red-800 rounded">
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Create form modal */}
      {showCreateForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-black/50" onClick={() => setShowCreateForm(false)} />
          <div className="relative bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-md mx-4 p-4">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">
              Create New Briefing
            </h3>
            <div className="space-y-3">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Name
                </label>
                <input
                  type="text"
                  value={newBriefingName}
                  onChange={(e) => setNewBriefingName(e.target.value)}
                  placeholder="e.g., Weekly Strategy Review"
                  className="w-full px-3 py-2 border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-pink-500"
                  autoFocus
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Description (optional)
                </label>
                <textarea
                  value={newBriefingDescription}
                  onChange={(e) => setNewBriefingDescription(e.target.value)}
                  placeholder="Brief description of this briefing..."
                  rows={2}
                  className="w-full px-3 py-2 border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-pink-500"
                />
              </div>
            </div>
            <div className="flex gap-2 mt-4">
              <button
                onClick={() => {
                  setShowCreateForm(false);
                  setNewBriefingName('');
                  setNewBriefingDescription('');
                }}
                className="flex-1 px-3 py-2 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg"
              >
                Cancel
              </button>
              <button
                onClick={handleCreateBriefing}
                disabled={!newBriefingName.trim() || creating}
                className="flex-1 px-3 py-2 bg-pink-500 text-white rounded-lg hover:bg-pink-600 disabled:opacity-50 flex items-center justify-center gap-2"
              >
                {creating ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Creating...
                  </>
                ) : (
                  'Create Briefing'
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Main content - Grid of briefings or detail view */}
      {selectedBriefing ? (
        <BriefingDetailPanel
          briefing={selectedBriefing}
          onClose={() => setSelectedBriefing(null)}
          onRemoveArticle={handleRemoveArticle}
          onRemoveIncident={handleRemoveIncident}
          onRemoveEmergingTopic={handleRemoveEmergingTopic}
          onFinalize={handleFinalize}
          onReopen={handleReopen}
          onExport={handleExport}
          onExportPdf={handleExportPdf}
          onShareEmail={handleShareEmail}
          onDelete={() => handleDeleteBriefing(selectedBriefing.id)}
          onUpdateSynthesis={handleUpdateSynthesis}
          onUpdatePriorityActions={handleUpdatePriorityActions}
          onUpdateThemes={handleUpdateThemes}
          finalizing={finalizing}
          finalizeProgress={finalizeProgress}
        />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {briefings.length === 0 ? (
            <div className="col-span-full text-center py-12">
              <Newspaper className="w-12 h-12 text-gray-300 dark:text-gray-600 mx-auto mb-3" />
              <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100 mb-1">
                No briefings yet
              </h3>
              <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
                Create a briefing to start curating articles and incidents
              </p>
              <button
                onClick={() => setShowCreateForm(true)}
                className="inline-flex items-center gap-2 px-4 py-2 bg-pink-500 text-white rounded-lg hover:bg-pink-600"
              >
                <Plus className="w-4 h-4" />
                Create Your First Briefing
              </button>
            </div>
          ) : (
            briefings.map((briefing) => (
              <BriefingCard
                key={briefing.id}
                briefing={briefing}
                onClick={() => handleSelectBriefing(briefing.id)}
                onDelete={() => handleDeleteBriefing(briefing.id)}
                loading={loadingDetail}
              />
            ))
          )}
        </div>
      )}

      {/* Share Modal */}
      {showShareModal && selectedBriefing && (
        <ShareModal
          open={showShareModal}
          onOpenChange={setShowShareModal}
          data={getShareData()!}
          onSuccess={() => {
            setShowShareModal(false);
          }}
        />
      )}
    </div>
  );
}

// ============================================================================
// BriefingCard Component
// ============================================================================

interface BriefingCardProps {
  briefing: BriefingSummary;
  onClick: () => void;
  onDelete: () => void;
  loading?: boolean;
}

function BriefingCard({ briefing, onClick, onDelete, loading }: BriefingCardProps) {
  const isDraft = briefing.status === 'draft';
  const isEmpty = briefing.articles_count === 0 && briefing.incidents_count === 0;

  return (
    <div
      onClick={onClick}
      className={`relative p-4 bg-white dark:bg-gray-800 border rounded-lg cursor-pointer transition-all hover:shadow-md ${
        isDraft
          ? 'border-gray-200 dark:border-gray-700 hover:border-pink-300 dark:hover:border-pink-600'
          : 'border-green-200 dark:border-green-800 bg-green-50/50 dark:bg-green-900/20'
      }`}
    >
      {/* Status badge */}
      <div className="absolute top-3 right-3">
        {isDraft ? (
          <span className="text-[10px] font-medium px-2 py-0.5 bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 rounded">
            Draft
          </span>
        ) : (
          <span className="text-[10px] font-medium px-2 py-0.5 bg-green-100 dark:bg-green-900/50 text-green-700 dark:text-green-300 rounded flex items-center gap-1">
            <Check className="w-3 h-3" />
            Finalized
          </span>
        )}
      </div>

      {/* Title */}
      <h3 className="font-semibold text-gray-900 dark:text-gray-100 pr-16 mb-1">
        {briefing.name}
      </h3>

      {/* Description */}
      {briefing.description && (
        <p className="text-sm text-gray-600 dark:text-gray-400 line-clamp-2 mb-3">
          {briefing.description}
        </p>
      )}

      {/* Stats */}
      <div className="flex items-center gap-4 text-sm text-gray-500 dark:text-gray-400 mb-3">
        <span className="flex items-center gap-1">
          <FileText className="w-3.5 h-3.5" />
          {briefing.articles_count} articles
        </span>
        <span className="flex items-center gap-1">
          <AlertTriangle className="w-3.5 h-3.5" />
          {briefing.incidents_count} incidents
        </span>
      </div>

      {/* Date and actions */}
      <div className="flex items-center justify-between">
        <span className="text-xs text-gray-400 dark:text-gray-500 flex items-center gap-1">
          <Calendar className="w-3 h-3" />
          {formatDate(briefing.updated_at)}
        </span>

        <div className="flex items-center gap-1">
          <button
            onClick={(e) => {
              e.stopPropagation();
              onDelete();
            }}
            className="p-1.5 text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/30 rounded transition-colors"
            title="Delete briefing"
          >
            <Trash2 className="w-4 h-4" />
          </button>
          <ChevronRight className="w-4 h-4 text-gray-400" />
        </div>
      </div>

      {/* Empty state indicator */}
      {isEmpty && isDraft && (
        <div className="mt-3 pt-3 border-t border-gray-100 dark:border-gray-700">
          <p className="text-xs text-gray-400 dark:text-gray-500 italic">
            Add articles or incidents via the "Add to Briefing" menu
          </p>
        </div>
      )}
    </div>
  );
}

// ============================================================================
// BriefingDetailPanel Component
// ============================================================================

interface BriefingDetailPanelProps {
  briefing: DeskBriefing;
  onClose: () => void;
  onRemoveArticle: (uri: string) => void;
  onRemoveIncident: (name: string) => void;
  onRemoveEmergingTopic: (name: string) => void;
  onFinalize: () => void;
  onReopen: () => void;
  onExport: (format: 'markdown' | 'html' | 'json') => void;
  onExportPdf: () => void;
  onShareEmail: () => void;
  onDelete: () => void;
  onUpdateSynthesis: (synthesis: string) => Promise<void>;
  onUpdatePriorityActions: (actions: BriefingAction[]) => Promise<void>;
  onUpdateThemes: (themes: BriefingTheme[]) => Promise<void>;
  finalizing: boolean;
  finalizeProgress: FinalizeProgressEvent | null;
}

function BriefingDetailPanel({
  briefing,
  onClose,
  onRemoveArticle,
  onRemoveIncident,
  onRemoveEmergingTopic,
  onFinalize,
  onReopen,
  onExport,
  onExportPdf,
  onShareEmail,
  onDelete,
  onUpdateSynthesis,
  onUpdatePriorityActions,
  onUpdateThemes,
  finalizing,
  finalizeProgress,
}: BriefingDetailPanelProps) {
  const [activeTab, setActiveTab] = useState<'content' | 'synthesis'>('content');
  const [showExportMenu, setShowExportMenu] = useState(false);

  // Markdown editor state
  const [isEditing, setIsEditing] = useState(false);
  const [editedSynthesis, setEditedSynthesis] = useState(briefing.synthesis || '');
  const [saving, setSaving] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Themes editor state
  const [isEditingThemes, setIsEditingThemes] = useState(false);
  const [editedThemes, setEditedThemes] = useState<BriefingTheme[]>(briefing.themes || []);
  const [savingThemes, setSavingThemes] = useState(false);

  // Markdown formatting helper
  const insertMarkdown = (before: string, after: string = '', placeholder: string = '') => {
    const textarea = textareaRef.current;
    if (!textarea) return;

    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const selectedText = editedSynthesis.substring(start, end);
    const textToInsert = selectedText || placeholder;

    const newText =
      editedSynthesis.substring(0, start) +
      before + textToInsert + after +
      editedSynthesis.substring(end);

    setEditedSynthesis(newText);

    // Set cursor position after update
    setTimeout(() => {
      textarea.focus();
      const newCursorPos = start + before.length + textToInsert.length + after.length;
      textarea.setSelectionRange(
        selectedText ? newCursorPos : start + before.length,
        selectedText ? newCursorPos : start + before.length + placeholder.length
      );
    }, 0);
  };

  // Priority actions editor state
  const [isEditingActions, setIsEditingActions] = useState(false);
  const [editedActions, setEditedActions] = useState<BriefingAction[]>(briefing.priority_actions || []);
  const [savingActions, setSavingActions] = useState(false);

  const isDraft = briefing.status === 'draft';
  const canFinalize = isDraft && (briefing.articles.length > 0 || briefing.incidents.length > 0);

  // Sync edited synthesis when briefing changes
  useEffect(() => {
    setEditedSynthesis(briefing.synthesis || '');
  }, [briefing.synthesis]);

  // Sync edited actions when briefing changes
  useEffect(() => {
    setEditedActions(briefing.priority_actions || []);
  }, [briefing.priority_actions]);

  // Handle saving synthesis
  const handleSaveSynthesis = async () => {
    setSaving(true);
    try {
      await onUpdateSynthesis(editedSynthesis);
      setIsEditing(false);
    } catch {
      // Error is handled by parent
    } finally {
      setSaving(false);
    }
  };

  // Handle cancel editing
  const handleCancelEdit = () => {
    setEditedSynthesis(briefing.synthesis || '');
    setIsEditing(false);
  };

  // Handle saving priority actions
  const handleSaveActions = async () => {
    setSavingActions(true);
    try {
      await onUpdatePriorityActions(editedActions);
      setIsEditingActions(false);
    } catch {
      // Error is handled by parent
    } finally {
      setSavingActions(false);
    }
  };

  // Handle cancel editing actions
  const handleCancelEditActions = () => {
    setEditedActions(briefing.priority_actions || []);
    setIsEditingActions(false);
  };

  // Add new action
  const handleAddAction = () => {
    setEditedActions([
      ...editedActions,
      { action: '', urgency: 'this_week', rationale: '' }
    ]);
  };

  // Update an action
  const handleUpdateAction = (index: number, field: keyof BriefingAction, value: string) => {
    const updated = [...editedActions];
    updated[index] = { ...updated[index], [field]: value };
    setEditedActions(updated);
  };

  // Delete an action
  const handleDeleteAction = (index: number) => {
    setEditedActions(editedActions.filter((_, i) => i !== index));
  };

  // Handle saving themes
  const handleSaveThemes = async () => {
    setSavingThemes(true);
    try {
      await onUpdateThemes(editedThemes);
      setIsEditingThemes(false);
    } catch {
      // Error is handled by parent
    } finally {
      setSavingThemes(false);
    }
  };

  // Handle cancel editing themes
  const handleCancelEditThemes = () => {
    setEditedThemes(briefing.themes || []);
    setIsEditingThemes(false);
  };

  // Update a theme field
  const handleUpdateTheme = (index: number, field: keyof BriefingTheme, value: string | string[]) => {
    const updated = [...editedThemes];
    updated[index] = { ...updated[index], [field]: value };
    setEditedThemes(updated);
  };

  // Delete a theme
  const handleDeleteTheme = (index: number) => {
    setEditedThemes(editedThemes.filter((_, i) => i !== index));
  };

  // Add new theme
  const handleAddTheme = () => {
    setEditedThemes([
      ...editedThemes,
      { theme_name: '', description: '', strategic_implication: '' }
    ]);
  };

  return (
    <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-gray-700">
        <div className="flex items-center gap-3 min-w-0">
          <button
            onClick={onClose}
            className="p-1 hover:bg-gray-100 dark:hover:bg-gray-700 rounded"
          >
            <ChevronRight className="w-5 h-5 text-gray-500 rotate-180" />
          </button>
          <div className="min-w-0">
            <h2 className="font-semibold text-gray-900 dark:text-gray-100 truncate">
              {briefing.name}
            </h2>
            {briefing.description && (
              <p className="text-sm text-gray-500 dark:text-gray-400 truncate">
                {briefing.description}
              </p>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* Status badge */}
          {isDraft ? (
            <>
              <span className="text-xs font-medium px-2 py-1 bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 rounded">
                Draft
              </span>
              {canFinalize && (
                <button
                  onClick={onFinalize}
                  disabled={finalizing}
                  className="flex items-center gap-1 text-xs font-medium px-2 py-1 bg-pink-500 text-white rounded hover:bg-pink-600 disabled:opacity-50"
                  title="Generate AI synthesis"
                >
                  {finalizing ? (
                    <Loader2 className="w-3 h-3 animate-spin" />
                  ) : (
                    <Sparkles className="w-3 h-3" />
                  )}
                  {finalizing ? 'Generating...' : 'Generate'}
                </button>
              )}
            </>
          ) : (
            <>
              <span className="text-xs font-medium px-2 py-1 bg-green-100 dark:bg-green-900/50 text-green-700 dark:text-green-300 rounded flex items-center gap-1">
                <Check className="w-3 h-3" />
                Finalized
              </span>
              <button
                onClick={onReopen}
                className="text-xs font-medium px-2 py-1 bg-amber-100 dark:bg-amber-900/50 text-amber-700 dark:text-amber-300 rounded hover:bg-amber-200 dark:hover:bg-amber-800/50 transition-colors"
                title="Reopen to add more content"
              >
                Reopen
              </button>
            </>
          )}

          {/* Export menu */}
          <div className="relative">
            <button
              onClick={() => setShowExportMenu(!showExportMenu)}
              className="p-2 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700 rounded"
              title="Export"
            >
              <Download className="w-4 h-4" />
            </button>
            {showExportMenu && (
              <div className="absolute right-0 top-full mt-1 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg z-10 py-1 min-w-[160px]">
                <button
                  onClick={() => { onExportPdf(); setShowExportMenu(false); }}
                  className="w-full px-3 py-2 text-left text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 flex items-center gap-2"
                >
                  <FileDown className="w-4 h-4 text-red-500" />
                  Download PDF
                </button>
                <div className="border-t border-gray-100 dark:border-gray-700 my-1" />
                <button
                  onClick={() => { onExport('markdown'); setShowExportMenu(false); }}
                  className="w-full px-3 py-2 text-left text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700"
                >
                  Markdown
                </button>
                <button
                  onClick={() => { onExport('html'); setShowExportMenu(false); }}
                  className="w-full px-3 py-2 text-left text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700"
                >
                  HTML
                </button>
                <button
                  onClick={() => { onExport('json'); setShowExportMenu(false); }}
                  className="w-full px-3 py-2 text-left text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700"
                >
                  JSON
                </button>
              </div>
            )}
          </div>

          {/* Email share button */}
          <button
            onClick={onShareEmail}
            className="p-2 text-gray-500 hover:text-pink-500 hover:bg-pink-50 dark:hover:bg-pink-900/30 rounded"
            title="Share via email"
          >
            <Mail className="w-4 h-4" />
          </button>

          {/* Delete button */}
          <button
            onClick={onDelete}
            className="p-2 text-gray-500 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/30 rounded"
            title="Delete briefing"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-gray-200 dark:border-gray-700">
        <button
          onClick={() => setActiveTab('content')}
          className={`px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors ${
            activeTab === 'content'
              ? 'border-pink-500 text-pink-600'
              : 'border-transparent text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100'
          }`}
        >
          Content ({briefing.articles.length + briefing.incidents.length})
        </button>
        <button
          onClick={() => setActiveTab('synthesis')}
          className={`px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors flex items-center gap-1.5 ${
            activeTab === 'synthesis'
              ? 'border-pink-500 text-pink-600'
              : 'border-transparent text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100'
          }`}
        >
          <Sparkles className="w-4 h-4" />
          Synthesis
          {!isDraft && <Check className="w-3 h-3 text-green-500" />}
        </button>
      </div>

      {/* Content */}
      <div className="p-4 max-h-[60vh] overflow-y-auto">
        {activeTab === 'content' ? (
          <div className="space-y-4">
            {/* Articles */}
            {briefing.articles.length > 0 && (
              <div>
                <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2 flex items-center gap-2">
                  <FileText className="w-4 h-4 text-blue-500" />
                  Articles ({briefing.articles.length})
                </h3>
                <div className="space-y-2">
                  {briefing.articles.map((article, idx) => (
                    <div
                      key={article.uri || idx}
                      className="flex items-start justify-between p-3 bg-gray-50 dark:bg-gray-900/50 rounded-lg group"
                    >
                      <div className="min-w-0 flex-1">
                        <p className="font-medium text-gray-900 dark:text-gray-100 text-sm">
                          {article.title}
                        </p>
                        <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                          {article.source} • {article.topic}
                        </p>
                      </div>
                      {isDraft && (
                        <button
                          onClick={() => onRemoveArticle(article.uri)}
                          className="p-1.5 text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/30 rounded transition-colors"
                          title="Remove from briefing"
                        >
                          <X className="w-4 h-4" />
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Incidents */}
            {briefing.incidents.length > 0 && (
              <div>
                <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2 flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4 text-amber-500" />
                  Incidents ({briefing.incidents.length})
                </h3>
                <div className="space-y-2">
                  {briefing.incidents.map((incident, idx) => (
                    <div
                      key={incident.name || idx}
                      className="flex items-start justify-between p-3 bg-amber-50 dark:bg-amber-900/20 rounded-lg group"
                    >
                      <div className="min-w-0 flex-1">
                        <p className="font-medium text-gray-900 dark:text-gray-100 text-sm">
                          {incident.name}
                        </p>
                        <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                          {incident.type} • {incident.significance} • {incident.topic}
                        </p>
                      </div>
                      {isDraft && (
                        <button
                          onClick={() => onRemoveIncident(incident.name)}
                          className="p-1.5 text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/30 rounded transition-colors"
                          title="Remove from briefing"
                        >
                          <X className="w-4 h-4" />
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Emerging Topics */}
            {briefing.emerging_topics && briefing.emerging_topics.length > 0 && (
              <div>
                <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2 flex items-center gap-2">
                  <TrendingUp className="w-4 h-4 text-purple-500" />
                  Emerging Topics ({briefing.emerging_topics.length})
                </h3>
                <div className="space-y-2">
                  {briefing.emerging_topics.map((topic, idx) => (
                    <div
                      key={topic.name || idx}
                      className="flex items-start justify-between p-3 bg-purple-50 dark:bg-purple-900/20 rounded-lg group"
                    >
                      <div className="min-w-0 flex-1">
                        <p className="font-medium text-gray-900 dark:text-gray-100 text-sm">
                          {topic.name}
                        </p>
                        <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                          {topic.article_count && `${topic.article_count} articles`}
                          {topic.velocity && ` • ${topic.velocity}`}
                          {topic.topic && ` • ${topic.topic}`}
                        </p>
                        {topic.key_takeaway && (
                          <p className="text-xs text-purple-600 dark:text-purple-400 mt-1">
                            {topic.key_takeaway}
                          </p>
                        )}
                      </div>
                      {isDraft && (
                        <button
                          onClick={() => onRemoveEmergingTopic(topic.name)}
                          className="p-1.5 text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/30 rounded transition-colors"
                          title="Remove from briefing"
                        >
                          <X className="w-4 h-4" />
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Empty state */}
            {briefing.articles.length === 0 && briefing.incidents.length === 0 && (!briefing.emerging_topics || briefing.emerging_topics.length === 0) && (
              <div className="text-center py-8">
                <Newspaper className="w-10 h-10 text-gray-300 dark:text-gray-600 mx-auto mb-2" />
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  No content yet. Use "Add to Briefing" from article, incident, or emerging topic menus.
                </p>
              </div>
            )}

            {/* Finalize progress indicator */}
            {isDraft && finalizing && (
              <div className="pt-4 border-t border-gray-200 dark:border-gray-700">
                <div className="flex items-center justify-center gap-2 text-sm text-gray-600 dark:text-gray-400">
                  <Loader2 className="w-4 h-4 animate-spin text-pink-500" />
                  {finalizeProgress?.stage === 'analysis'
                    ? `Analyzing ${finalizeProgress.current_item || 0}/${finalizeProgress.total_items || 0}...`
                    : 'Synthesizing...'}
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="space-y-4">
            {briefing.synthesis ? (
              <>
                {/* Executive Summary with Edit/Preview toggle */}
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wide">
                      Executive Summary
                    </h3>
                    <div className="flex items-center gap-2">
                      {isEditing ? (
                        <>
                          <button
                            onClick={handleCancelEdit}
                            disabled={saving}
                            className="flex items-center gap-1 px-2 py-1 text-xs text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 rounded"
                          >
                            <X className="w-3 h-3" />
                            Cancel
                          </button>
                          <button
                            onClick={handleSaveSynthesis}
                            disabled={saving}
                            className="flex items-center gap-1 px-2 py-1 text-xs bg-pink-500 text-white rounded hover:bg-pink-600 disabled:opacity-50"
                          >
                            {saving ? (
                              <Loader2 className="w-3 h-3 animate-spin" />
                            ) : (
                              <Save className="w-3 h-3" />
                            )}
                            Save
                          </button>
                        </>
                      ) : (
                        <button
                          onClick={() => setIsEditing(true)}
                          className="flex items-center gap-1 px-2 py-1 text-xs text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 rounded"
                        >
                          <Pencil className="w-3 h-3" />
                          Edit
                        </button>
                      )}
                    </div>
                  </div>

                  {isEditing ? (
                    <div className="space-y-2">
                      {/* Markdown Toolbar */}
                      <div className="flex items-center gap-1 p-1 bg-gray-100 dark:bg-gray-800 rounded-t-lg border border-b-0 border-gray-200 dark:border-gray-700">
                        <button
                          type="button"
                          onClick={() => insertMarkdown('**', '**', 'bold text')}
                          className="p-1.5 hover:bg-gray-200 dark:hover:bg-gray-700 rounded text-gray-600 dark:text-gray-400"
                          title="Bold (Ctrl+B)"
                        >
                          <Bold className="w-4 h-4" />
                        </button>
                        <button
                          type="button"
                          onClick={() => insertMarkdown('*', '*', 'italic text')}
                          className="p-1.5 hover:bg-gray-200 dark:hover:bg-gray-700 rounded text-gray-600 dark:text-gray-400"
                          title="Italic (Ctrl+I)"
                        >
                          <Italic className="w-4 h-4" />
                        </button>
                        <div className="w-px h-5 bg-gray-300 dark:bg-gray-600 mx-1" />
                        <button
                          type="button"
                          onClick={() => insertMarkdown('## ', '', 'Heading')}
                          className="p-1.5 hover:bg-gray-200 dark:hover:bg-gray-700 rounded text-gray-600 dark:text-gray-400"
                          title="Heading"
                        >
                          <Heading2 className="w-4 h-4" />
                        </button>
                        <button
                          type="button"
                          onClick={() => insertMarkdown('- ', '', 'list item')}
                          className="p-1.5 hover:bg-gray-200 dark:hover:bg-gray-700 rounded text-gray-600 dark:text-gray-400"
                          title="Bullet List"
                        >
                          <List className="w-4 h-4" />
                        </button>
                        <button
                          type="button"
                          onClick={() => insertMarkdown('1. ', '', 'list item')}
                          className="p-1.5 hover:bg-gray-200 dark:hover:bg-gray-700 rounded text-gray-600 dark:text-gray-400"
                          title="Numbered List"
                        >
                          <ListOrdered className="w-4 h-4" />
                        </button>
                        <div className="w-px h-5 bg-gray-300 dark:bg-gray-600 mx-1" />
                        <button
                          type="button"
                          onClick={() => insertMarkdown('[', '](url)', 'link text')}
                          className="p-1.5 hover:bg-gray-200 dark:hover:bg-gray-700 rounded text-gray-600 dark:text-gray-400"
                          title="Link"
                        >
                          <Link className="w-4 h-4" />
                        </button>
                        <button
                          type="button"
                          onClick={() => insertMarkdown('> ', '', 'quote')}
                          className="p-1.5 hover:bg-gray-200 dark:hover:bg-gray-700 rounded text-gray-600 dark:text-gray-400"
                          title="Quote"
                        >
                          <Quote className="w-4 h-4" />
                        </button>
                      </div>
                      <textarea
                        ref={textareaRef}
                        value={editedSynthesis}
                        onChange={(e) => setEditedSynthesis(e.target.value)}
                        className="w-full h-48 p-3 text-sm font-mono bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-b-lg rounded-t-none text-gray-900 dark:text-gray-100 resize-y focus:outline-none focus:ring-2 focus:ring-pink-500"
                        placeholder="Enter synthesis (Markdown supported)..."
                      />
                    </div>
                  ) : (
                    <div className="prose prose-sm dark:prose-invert max-w-none text-gray-700 dark:text-gray-300 leading-relaxed">
                      <ReactMarkdown>{briefing.synthesis}</ReactMarkdown>
                    </div>
                  )}
                </div>

                {/* Themes */}
                {((briefing.themes && briefing.themes.length > 0) || isEditingThemes) && (
                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wide">
                        Key Themes
                      </h3>
                      <div className="flex items-center gap-2">
                        {isEditingThemes ? (
                          <>
                            <button
                              onClick={handleCancelEditThemes}
                              disabled={savingThemes}
                              className="flex items-center gap-1 px-2 py-1 text-xs text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 rounded"
                            >
                              <X className="w-3 h-3" />
                              Cancel
                            </button>
                            <button
                              onClick={handleSaveThemes}
                              disabled={savingThemes}
                              className="flex items-center gap-1 px-2 py-1 text-xs bg-pink-500 text-white rounded hover:bg-pink-600 disabled:opacity-50"
                            >
                              {savingThemes ? (
                                <Loader2 className="w-3 h-3 animate-spin" />
                              ) : (
                                <Save className="w-3 h-3" />
                              )}
                              Save
                            </button>
                          </>
                        ) : (
                          <button
                            onClick={() => setIsEditingThemes(true)}
                            className="flex items-center gap-1 px-2 py-1 text-xs text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 rounded"
                          >
                            <Pencil className="w-3 h-3" />
                            Edit
                          </button>
                        )}
                      </div>
                    </div>

                    {isEditingThemes ? (
                      <div className="space-y-3">
                        {editedThemes.map((theme, idx) => (
                          <div key={idx} className="p-3 bg-gray-50 dark:bg-gray-900/50 rounded-lg space-y-2">
                            <div className="flex items-start gap-2">
                              <input
                                type="text"
                                value={theme.theme_name}
                                onChange={(e) => handleUpdateTheme(idx, 'theme_name', e.target.value)}
                                placeholder="Theme name"
                                className="flex-1 text-sm font-medium px-2 py-1 border border-gray-200 dark:border-gray-700 rounded bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                              />
                              <button
                                onClick={() => handleDeleteTheme(idx)}
                                className="p-1 text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/30 rounded"
                              >
                                <Trash2 className="w-4 h-4" />
                              </button>
                            </div>
                            <textarea
                              value={theme.description}
                              onChange={(e) => handleUpdateTheme(idx, 'description', e.target.value)}
                              placeholder="Description"
                              rows={2}
                              className="w-full text-sm px-2 py-1 border border-gray-200 dark:border-gray-700 rounded bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-400 resize-none"
                            />
                            <input
                              type="text"
                              value={theme.strategic_implication || ''}
                              onChange={(e) => handleUpdateTheme(idx, 'strategic_implication', e.target.value)}
                              placeholder="Strategic implication"
                              className="w-full text-sm px-2 py-1 border border-gray-200 dark:border-gray-700 rounded bg-white dark:bg-gray-800 text-pink-600 dark:text-pink-400"
                            />
                          </div>
                        ))}
                        <button
                          onClick={handleAddTheme}
                          className="w-full flex items-center justify-center gap-2 px-3 py-2 border-2 border-dashed border-gray-200 dark:border-gray-700 rounded-lg text-sm text-gray-500 hover:border-pink-300 hover:text-pink-600 transition-colors"
                        >
                          <Plus className="w-4 h-4" />
                          Add Theme
                        </button>
                      </div>
                    ) : (
                      <div className="space-y-3">
                        {briefing.themes?.map((theme, idx) => (
                          <div key={idx} className="p-3 bg-gray-50 dark:bg-gray-900/50 rounded-lg">
                            <h4 className="font-medium text-gray-900 dark:text-gray-100">
                              {theme.theme_name}
                            </h4>
                            <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                              {theme.description}
                            </p>
                            {theme.strategic_implication && (
                              <p className="text-sm text-pink-600 dark:text-pink-400 mt-2">
                                <strong>Strategic Implication:</strong> {theme.strategic_implication}
                              </p>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                {/* Priority Actions */}
                {(briefing.priority_actions && briefing.priority_actions.length > 0) || isEditingActions ? (
                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wide">
                        Priority Actions
                      </h3>
                      <div className="flex items-center gap-2">
                        {isEditingActions ? (
                          <>
                            <button
                              onClick={handleCancelEditActions}
                              disabled={savingActions}
                              className="flex items-center gap-1 px-2 py-1 text-xs text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 rounded"
                            >
                              <X className="w-3 h-3" />
                              Cancel
                            </button>
                            <button
                              onClick={handleSaveActions}
                              disabled={savingActions}
                              className="flex items-center gap-1 px-2 py-1 text-xs bg-pink-500 text-white rounded hover:bg-pink-600 disabled:opacity-50"
                            >
                              {savingActions ? (
                                <Loader2 className="w-3 h-3 animate-spin" />
                              ) : (
                                <Save className="w-3 h-3" />
                              )}
                              Save
                            </button>
                          </>
                        ) : (
                          <button
                            onClick={() => setIsEditingActions(true)}
                            className="flex items-center gap-1 px-2 py-1 text-xs text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 rounded"
                          >
                            <Pencil className="w-3 h-3" />
                            Edit
                          </button>
                        )}
                      </div>
                    </div>

                    {isEditingActions ? (
                      <div className="space-y-3">
                        {editedActions.map((action, idx) => (
                          <div key={idx} className="p-3 bg-gray-50 dark:bg-gray-900/50 rounded-lg space-y-2">
                            <div className="flex items-start gap-2">
                              <select
                                value={action.urgency}
                                onChange={(e) => handleUpdateAction(idx, 'urgency', e.target.value as BriefingAction['urgency'])}
                                className="text-xs px-2 py-1 border border-gray-200 dark:border-gray-700 rounded bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300"
                              >
                                <option value="immediate">Immediate</option>
                                <option value="this_week">This Week</option>
                                <option value="this_month">This Month</option>
                                <option value="this_quarter">This Quarter</option>
                              </select>
                              <input
                                type="text"
                                value={action.action}
                                onChange={(e) => handleUpdateAction(idx, 'action', e.target.value)}
                                placeholder="Action description"
                                className="flex-1 text-sm px-2 py-1 border border-gray-200 dark:border-gray-700 rounded bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                              />
                              <button
                                onClick={() => handleDeleteAction(idx)}
                                className="p-1 text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/30 rounded"
                              >
                                <Trash2 className="w-4 h-4" />
                              </button>
                            </div>
                            <input
                              type="text"
                              value={action.rationale || ''}
                              onChange={(e) => handleUpdateAction(idx, 'rationale', e.target.value)}
                              placeholder="Rationale (optional)"
                              className="w-full text-xs px-2 py-1 border border-gray-200 dark:border-gray-700 rounded bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-400"
                            />
                          </div>
                        ))}
                        <button
                          onClick={handleAddAction}
                          className="w-full flex items-center justify-center gap-2 px-3 py-2 border-2 border-dashed border-gray-200 dark:border-gray-700 rounded-lg text-sm text-gray-500 hover:border-pink-300 hover:text-pink-600 transition-colors"
                        >
                          <Plus className="w-4 h-4" />
                          Add Action
                        </button>
                      </div>
                    ) : (
                      <div className="space-y-2">
                        {briefing.priority_actions?.map((action, idx) => (
                          <div key={idx} className="flex items-start gap-3 p-3 bg-gray-50 dark:bg-gray-900/50 rounded-lg">
                            <span className={`text-[10px] font-medium px-2 py-0.5 rounded flex-shrink-0 ${
                              action.urgency === 'immediate' ? 'bg-red-100 text-red-700 dark:bg-red-900/50 dark:text-red-300' :
                              action.urgency === 'this_week' ? 'bg-orange-100 text-orange-700 dark:bg-orange-900/50 dark:text-orange-300' :
                              action.urgency === 'this_month' ? 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/50 dark:text-yellow-300' :
                              'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300'
                            }`}>
                              {action.urgency.replace('_', ' ')}
                            </span>
                            <div>
                              <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
                                {action.action}
                              </p>
                              {action.rationale && (
                                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                                  {action.rationale}
                                </p>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ) : null}

                {/* Metadata */}
                {briefing.metadata && (
                  <div className="pt-4 border-t border-gray-200 dark:border-gray-700">
                    <p className="text-xs text-gray-500 dark:text-gray-400">
                      Generated with {briefing.model_used || 'AI'} on {formatDate(briefing.finalized_at)}
                    </p>
                  </div>
                )}
              </>
            ) : isDraft ? (
              /* Empty synthesis state for drafts - show editable area */
              <div className="space-y-4">
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wide">
                      Executive Summary
                    </h3>
                    <div className="flex items-center gap-2">
                      {isEditing ? (
                        <>
                          <button
                            onClick={handleCancelEdit}
                            disabled={saving}
                            className="flex items-center gap-1 px-2 py-1 text-xs text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 rounded"
                          >
                            <X className="w-3 h-3" />
                            Cancel
                          </button>
                          <button
                            onClick={handleSaveSynthesis}
                            disabled={saving}
                            className="flex items-center gap-1 px-2 py-1 text-xs bg-pink-500 text-white rounded hover:bg-pink-600 disabled:opacity-50"
                          >
                            {saving ? (
                              <Loader2 className="w-3 h-3 animate-spin" />
                            ) : (
                              <Save className="w-3 h-3" />
                            )}
                            Save
                          </button>
                        </>
                      ) : (
                        <button
                          onClick={() => setIsEditing(true)}
                          className="flex items-center gap-1 px-2 py-1 text-xs text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 rounded"
                        >
                          <Pencil className="w-3 h-3" />
                          Write
                        </button>
                      )}
                    </div>
                  </div>

                  {isEditing ? (
                    <div className="space-y-2">
                      {/* Markdown Toolbar */}
                      <div className="flex items-center gap-1 p-1 bg-gray-100 dark:bg-gray-800 rounded-t-lg border border-b-0 border-gray-200 dark:border-gray-700">
                        <button
                          type="button"
                          onClick={() => insertMarkdown('**', '**', 'bold text')}
                          className="p-1.5 hover:bg-gray-200 dark:hover:bg-gray-700 rounded text-gray-600 dark:text-gray-400"
                          title="Bold (Ctrl+B)"
                        >
                          <Bold className="w-4 h-4" />
                        </button>
                        <button
                          type="button"
                          onClick={() => insertMarkdown('*', '*', 'italic text')}
                          className="p-1.5 hover:bg-gray-200 dark:hover:bg-gray-700 rounded text-gray-600 dark:text-gray-400"
                          title="Italic (Ctrl+I)"
                        >
                          <Italic className="w-4 h-4" />
                        </button>
                        <div className="w-px h-5 bg-gray-300 dark:bg-gray-600 mx-1" />
                        <button
                          type="button"
                          onClick={() => insertMarkdown('## ', '', 'Heading')}
                          className="p-1.5 hover:bg-gray-200 dark:hover:bg-gray-700 rounded text-gray-600 dark:text-gray-400"
                          title="Heading"
                        >
                          <Heading2 className="w-4 h-4" />
                        </button>
                        <button
                          type="button"
                          onClick={() => insertMarkdown('- ', '', 'list item')}
                          className="p-1.5 hover:bg-gray-200 dark:hover:bg-gray-700 rounded text-gray-600 dark:text-gray-400"
                          title="Bullet List"
                        >
                          <List className="w-4 h-4" />
                        </button>
                        <button
                          type="button"
                          onClick={() => insertMarkdown('1. ', '', 'list item')}
                          className="p-1.5 hover:bg-gray-200 dark:hover:bg-gray-700 rounded text-gray-600 dark:text-gray-400"
                          title="Numbered List"
                        >
                          <ListOrdered className="w-4 h-4" />
                        </button>
                        <div className="w-px h-5 bg-gray-300 dark:bg-gray-600 mx-1" />
                        <button
                          type="button"
                          onClick={() => insertMarkdown('[', '](url)', 'link text')}
                          className="p-1.5 hover:bg-gray-200 dark:hover:bg-gray-700 rounded text-gray-600 dark:text-gray-400"
                          title="Link"
                        >
                          <Link className="w-4 h-4" />
                        </button>
                        <button
                          type="button"
                          onClick={() => insertMarkdown('> ', '', 'quote')}
                          className="p-1.5 hover:bg-gray-200 dark:hover:bg-gray-700 rounded text-gray-600 dark:text-gray-400"
                          title="Quote"
                        >
                          <Quote className="w-4 h-4" />
                        </button>
                      </div>
                      <textarea
                        ref={textareaRef}
                        value={editedSynthesis}
                        onChange={(e) => setEditedSynthesis(e.target.value)}
                        className="w-full h-48 p-3 text-sm font-mono bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-b-lg rounded-t-none text-gray-900 dark:text-gray-100 resize-y focus:outline-none focus:ring-2 focus:ring-pink-500"
                        placeholder="Write your executive summary (Markdown supported)..."
                      />
                    </div>
                  ) : (
                    <div className="text-center py-6 bg-gray-50 dark:bg-gray-900/50 rounded-lg border border-dashed border-gray-200 dark:border-gray-700">
                      <Pencil className="w-8 h-8 text-gray-300 dark:text-gray-600 mx-auto mb-2" />
                      <p className="text-sm text-gray-500 dark:text-gray-400">
                        Click "Write" to add your own summary, or use "Generate" to create one with AI
                      </p>
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <div className="text-center py-8">
                <Sparkles className="w-10 h-10 text-gray-300 dark:text-gray-600 mx-auto mb-2" />
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  No synthesis available
                </p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default BriefingDeskSection;
