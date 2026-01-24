/**
 * PromoteToIncidentModal - Modal for promoting an article to an incident
 * Allows creating a new incident with AI-suggested classification or adding to an existing incident
 */

import { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../ui/tabs';
import { ScrollArea } from '../ui/scroll-area';
import {
  Loader2,
  AlertTriangle,
  CheckCircle2,
  PlusCircle,
  FolderPlus,
  Search,
  X,
  Sparkles,
} from 'lucide-react';
import {
  type NewsArticle,
  type SavedIncident,
  analyzeArticleForIncident,
  saveIncident,
  getSavedIncidents,
  addArticleToIncident,
} from '../../services/newsFeedApi';

interface PromoteToIncidentModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  article: NewsArticle | null;
  topic?: string;
  profileId?: number;
  onSuccess?: () => void;
}

export function PromoteToIncidentModal({
  open,
  onOpenChange,
  article,
  topic,
  profileId,
  onSuccess,
}: PromoteToIncidentModalProps) {
  const [activeTab, setActiveTab] = useState<'create' | 'existing'>('create');
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // Create new incident state
  const [suggestedIncident, setSuggestedIncident] = useState<SavedIncident | null>(null);
  const [editedIncident, setEditedIncident] = useState<Partial<SavedIncident>>({});

  // Add to existing incident state
  const [existingIncidents, setExistingIncidents] = useState<SavedIncident[]>([]);
  const [loadingIncidents, setLoadingIncidents] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedIncident, setSelectedIncident] = useState<SavedIncident | null>(null);

  // Reset state when modal opens
  useEffect(() => {
    if (open && article) {
      setError(null);
      setSuccess(null);
      setSuggestedIncident(null);
      setEditedIncident({});
      setSelectedIncident(null);
      setSearchQuery('');
      setActiveTab('create');

      // Start analysis for new incident
      analyzeArticle();

      // Load existing incidents
      loadExistingIncidents();
    }
  }, [open, article?.uri]);

  const analyzeArticle = async () => {
    if (!article) return;

    setIsAnalyzing(true);
    setError(null);

    try {
      const result = await analyzeArticleForIncident(
        article.uri,
        topic || article.topic,
        profileId
      );

      if (result.success && result.suggested_incident) {
        setSuggestedIncident(result.suggested_incident as SavedIncident);
        setEditedIncident(result.suggested_incident);
      }
    } catch (err) {
      console.error('Error analyzing article:', err);
      setError(err instanceof Error ? err.message : 'Failed to analyze article');
    } finally {
      setIsAnalyzing(false);
    }
  };

  const loadExistingIncidents = async () => {
    setLoadingIncidents(true);
    try {
      const incidents = await getSavedIncidents(topic);
      setExistingIncidents(incidents);
    } catch (err) {
      console.error('Error loading incidents:', err);
    } finally {
      setLoadingIncidents(false);
    }
  };

  const handleSaveNewIncident = async () => {
    if (!article || !editedIncident.name) {
      setError('Incident name is required');
      return;
    }

    setIsSaving(true);
    setError(null);

    try {
      const incidentTopic = editedIncident.topic || topic || article.topic || '';
      console.log('[PromoteToIncidentModal] Saving incident with topic:', incidentTopic, 'editedIncident.topic:', editedIncident.topic, 'prop topic:', topic, 'article.topic:', article.topic);
      const incidentToSave: SavedIncident = {
        ...editedIncident,
        name: editedIncident.name,
        topic: incidentTopic,
        article_uris: [article.uri],
        article_metadata: [
          {
            uri: article.uri,
            title: article.title,
            summary: article.summary,
            source: article.source?.name,
            publication_date: article.publication_date,
          },
        ],
      };

      // Save the full incident data to saved_incidents table
      const saved = await saveIncident(incidentToSave);

      if (saved) {
        setSuccess('Incident created successfully');
        onSuccess?.();
        setTimeout(() => onOpenChange(false), 1500);
      } else {
        setError('Failed to save incident');
      }
    } catch (err) {
      console.error('Error saving incident:', err);
      setError(err instanceof Error ? err.message : 'Failed to save incident');
    } finally {
      setIsSaving(false);
    }
  };

  const handleAddToExisting = async () => {
    if (!article || !selectedIncident) {
      setError('Please select an incident');
      return;
    }

    setIsSaving(true);
    setError(null);

    try {
      const result = await addArticleToIncident(
        selectedIncident.name,
        selectedIncident.topic || topic || '',
        article.uri,
        {
          uri: article.uri,
          title: article.title,
          summary: article.summary,
          source: article.source?.name,
          publication_date: article.publication_date,
        }
      );

      if (result.success) {
        setSuccess(result.message || 'Article added to incident');
        onSuccess?.();
        setTimeout(() => onOpenChange(false), 1500);
      } else {
        setError('Failed to add article to incident');
      }
    } catch (err) {
      console.error('Error adding to incident:', err);
      setError(err instanceof Error ? err.message : 'Failed to add article to incident');
    } finally {
      setIsSaving(false);
    }
  };

  const filteredIncidents = existingIncidents.filter(
    (incident) =>
      !searchQuery ||
      incident.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      incident.description?.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const updateField = (field: keyof SavedIncident, value: any) => {
    setEditedIncident((prev) => ({ ...prev, [field]: value }));
  };

  if (!open) return null;

  const modalContent = (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 z-50 bg-black/50" onClick={() => onOpenChange(false)} />

      {/* Modal */}
      <div
        className="fixed z-50 bg-white dark:bg-gray-800 rounded-lg shadow-xl border border-gray-200 dark:border-gray-700"
        style={{
          top: '50%',
          left: '50%',
          transform: 'translate(-50%, -50%)',
          width: '560px',
          maxWidth: 'calc(100vw - 32px)',
          maxHeight: 'calc(100vh - 64px)',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-700">
          <div className="flex items-center gap-2">
            <Sparkles className="w-5 h-5 text-pink-500" />
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
              Promote to Incident
            </h2>
          </div>
          <button
            onClick={() => onOpenChange(false)}
            className="p-1 text-gray-500 hover:text-gray-700 dark:hover:text-gray-300 rounded"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Article info */}
        {article && (
          <div className="px-6 py-3 bg-gray-50 dark:bg-gray-900 border-b border-gray-200 dark:border-gray-700">
            <p className="text-sm font-medium text-gray-900 dark:text-gray-100 line-clamp-2">
              {article.title}
            </p>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
              {article.source?.name} • {article.topic || topic || 'No topic'}
            </p>
          </div>
        )}

        {/* Success message */}
        {success && (
          <div className="mx-6 mt-4 p-3 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg flex items-center gap-2">
            <CheckCircle2 className="w-5 h-5 text-green-600 dark:text-green-400" />
            <span className="text-sm text-green-700 dark:text-green-300">{success}</span>
          </div>
        )}

        {/* Error message */}
        {error && (
          <div className="mx-6 mt-4 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg flex items-center gap-2">
            <AlertTriangle className="w-5 h-5 text-red-600 dark:text-red-400" />
            <span className="text-sm text-red-700 dark:text-red-300">{error}</span>
          </div>
        )}

        {/* Tabs */}
        <Tabs
          value={activeTab}
          onValueChange={(v) => setActiveTab(v as 'create' | 'existing')}
          className="flex-1 flex flex-col overflow-hidden"
        >
          <div className="px-6 pt-4">
            <TabsList className="w-full">
              <TabsTrigger value="create" className="flex-1 flex items-center gap-1.5">
                <PlusCircle className="w-4 h-4" />
                Create New
              </TabsTrigger>
              <TabsTrigger value="existing" className="flex-1 flex items-center gap-1.5">
                <FolderPlus className="w-4 h-4" />
                Add to Existing
              </TabsTrigger>
            </TabsList>
          </div>

          {/* Create New Tab */}
          <TabsContent value="create" className="flex-1 overflow-hidden px-6 pb-4">
            {isAnalyzing ? (
              <div className="flex flex-col items-center justify-center py-12">
                <Loader2 className="w-8 h-8 animate-spin text-pink-500 mb-3" />
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  Analyzing article with AI...
                </p>
              </div>
            ) : suggestedIncident ? (
              <ScrollArea className="h-[350px] pr-4 mt-4">
                <div className="space-y-4">
                  {/* Name */}
                  <div>
                    <Label htmlFor="incident-name" className="text-sm font-medium">
                      Name *
                    </Label>
                    <Input
                      id="incident-name"
                      value={editedIncident.name || ''}
                      onChange={(e) => updateField('name', e.target.value)}
                      placeholder="Incident name"
                      className="mt-1.5"
                    />
                  </div>

                  {/* Type & Subtype */}
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <Label htmlFor="incident-type" className="text-sm font-medium">
                        Type
                      </Label>
                      <select
                        id="incident-type"
                        value={editedIncident.type || ''}
                        onChange={(e) => updateField('type', e.target.value)}
                        className="mt-1.5 w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 text-sm"
                      >
                        <option value="incident">Incident</option>
                        <option value="event">Event</option>
                        <option value="entity">Entity</option>
                        <option value="expertise">Expertise</option>
                        <option value="informed_insider">Informed Insider</option>
                        <option value="trend_signal">Trend Signal</option>
                        <option value="strategic_shift">Strategic Shift</option>
                      </select>
                    </div>
                    <div>
                      <Label htmlFor="incident-significance" className="text-sm font-medium">
                        Significance
                      </Label>
                      <select
                        id="incident-significance"
                        value={editedIncident.significance || ''}
                        onChange={(e) => updateField('significance', e.target.value)}
                        className="mt-1.5 w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 text-sm"
                      >
                        <option value="low">Low</option>
                        <option value="medium">Medium</option>
                        <option value="high">High</option>
                      </select>
                    </div>
                  </div>

                  {/* Description */}
                  <div>
                    <Label htmlFor="incident-description" className="text-sm font-medium">
                      Description
                    </Label>
                    <textarea
                      id="incident-description"
                      value={editedIncident.description || ''}
                      onChange={(e) => updateField('description', e.target.value)}
                      placeholder="Incident description"
                      rows={3}
                      className="mt-1.5 w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 text-sm resize-none"
                    />
                  </div>

                  {/* Entities */}
                  <div>
                    <Label htmlFor="incident-entities" className="text-sm font-medium">
                      Entities (comma-separated)
                    </Label>
                    <Input
                      id="incident-entities"
                      value={
                        Array.isArray(editedIncident.entities)
                          ? editedIncident.entities.join(', ')
                          : ''
                      }
                      onChange={(e) =>
                        updateField(
                          'entities',
                          e.target.value.split(',').map((s) => s.trim()).filter(Boolean)
                        )
                      }
                      placeholder="Company A, Person B, Product C"
                      className="mt-1.5"
                    />
                  </div>

                  {/* Timeline */}
                  <div>
                    <Label htmlFor="incident-timeline" className="text-sm font-medium">
                      Timeline
                    </Label>
                    <Input
                      id="incident-timeline"
                      value={
                        typeof editedIncident.timeline === 'string'
                          ? editedIncident.timeline
                          : Array.isArray(editedIncident.timeline)
                          ? editedIncident.timeline.join('; ')
                          : ''
                      }
                      onChange={(e) => updateField('timeline', e.target.value)}
                      placeholder="When this happened/is happening"
                      className="mt-1.5"
                    />
                  </div>

                  {/* Source Quality & Plausibility */}
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <Label htmlFor="incident-source-quality" className="text-sm font-medium">
                        Source Quality
                      </Label>
                      <select
                        id="incident-source-quality"
                        value={editedIncident.source_quality || ''}
                        onChange={(e) => updateField('source_quality', e.target.value)}
                        className="mt-1.5 w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 text-sm"
                      >
                        <option value="high">High</option>
                        <option value="mixed">Mixed</option>
                        <option value="low">Low</option>
                      </select>
                    </div>
                    <div>
                      <Label htmlFor="incident-plausibility" className="text-sm font-medium">
                        Plausibility
                      </Label>
                      <select
                        id="incident-plausibility"
                        value={editedIncident.plausibility || ''}
                        onChange={(e) => updateField('plausibility', e.target.value)}
                        className="mt-1.5 w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 text-sm"
                      >
                        <option value="likely">Likely</option>
                        <option value="questionable">Questionable</option>
                        <option value="implausible">Implausible</option>
                      </select>
                    </div>
                  </div>

                  {/* Investigation Leads */}
                  <div>
                    <Label htmlFor="incident-leads" className="text-sm font-medium">
                      Investigation Leads (one per line)
                    </Label>
                    <textarea
                      id="incident-leads"
                      value={
                        Array.isArray(editedIncident.investigation_leads)
                          ? editedIncident.investigation_leads.join('\n')
                          : ''
                      }
                      onChange={(e) =>
                        updateField(
                          'investigation_leads',
                          e.target.value.split('\n').filter(Boolean)
                        )
                      }
                      placeholder="Follow-up questions or areas to investigate"
                      rows={2}
                      className="mt-1.5 w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 text-sm resize-none"
                    />
                  </div>

                  {/* Organizational Relevance */}
                  {editedIncident.organizational_relevance && (
                    <div>
                      <Label htmlFor="incident-relevance" className="text-sm font-medium">
                        Organizational Relevance
                      </Label>
                      <textarea
                        id="incident-relevance"
                        value={editedIncident.organizational_relevance || ''}
                        onChange={(e) => updateField('organizational_relevance', e.target.value)}
                        rows={2}
                        className="mt-1.5 w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 text-sm resize-none"
                      />
                    </div>
                  )}
                </div>
              </ScrollArea>
            ) : (
              <div className="flex flex-col items-center justify-center py-12 text-center">
                <AlertTriangle className="w-8 h-8 text-amber-500 mb-3" />
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  {error || 'Failed to analyze article. Please try again.'}
                </p>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={analyzeArticle}
                  className="mt-3"
                  disabled={isAnalyzing}
                >
                  Retry Analysis
                </Button>
              </div>
            )}
          </TabsContent>

          {/* Add to Existing Tab */}
          <TabsContent value="existing" className="flex-1 overflow-hidden px-6 pb-4">
            <div className="mt-4 space-y-4">
              {/* Search */}
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                <Input
                  placeholder="Search incidents..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-9"
                />
              </div>

              {/* Incidents list */}
              {loadingIncidents ? (
                <div className="flex items-center justify-center py-12">
                  <Loader2 className="w-6 h-6 animate-spin text-gray-400" />
                </div>
              ) : filteredIncidents.length === 0 ? (
                <div className="text-center py-12">
                  <p className="text-sm text-gray-500 dark:text-gray-400">
                    {searchQuery
                      ? 'No incidents match your search'
                      : 'No saved incidents yet. Create one first!'}
                  </p>
                </div>
              ) : (
                <ScrollArea className="h-[300px]">
                  <div className="space-y-2 pr-4">
                    {filteredIncidents.map((incident) => (
                      <button
                        key={`${incident.name}-${incident.topic}`}
                        onClick={() => setSelectedIncident(incident)}
                        className={`w-full text-left p-3 rounded-lg border transition-colors ${
                          selectedIncident?.name === incident.name &&
                          selectedIncident?.topic === incident.topic
                            ? 'border-pink-500 bg-pink-50 dark:bg-pink-900/20'
                            : 'border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600 bg-white dark:bg-gray-800'
                        }`}
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div className="flex-1 min-w-0">
                            <p className="font-medium text-sm text-gray-900 dark:text-gray-100 truncate">
                              {incident.name}
                            </p>
                            <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 line-clamp-2">
                              {incident.description || 'No description'}
                            </p>
                          </div>
                          <div className="flex flex-col items-end gap-1">
                            {incident.type && (
                              <span className="text-xs px-1.5 py-0.5 bg-gray-100 dark:bg-gray-700 rounded">
                                {incident.type}
                              </span>
                            )}
                            {incident.significance && (
                              <span
                                className={`text-xs px-1.5 py-0.5 rounded ${
                                  incident.significance === 'high'
                                    ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
                                    : incident.significance === 'medium'
                                    ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400'
                                    : 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-400'
                                }`}
                              >
                                {incident.significance}
                              </span>
                            )}
                          </div>
                        </div>
                        {incident.article_uris && incident.article_uris.length > 0 && (
                          <p className="text-xs text-gray-400 mt-2">
                            {incident.article_uris.length} article
                            {incident.article_uris.length !== 1 ? 's' : ''} linked
                          </p>
                        )}
                      </button>
                    ))}
                  </div>
                </ScrollArea>
              )}
            </div>
          </TabsContent>
        </Tabs>

        {/* Footer */}
        <div className="flex justify-end gap-2 px-6 py-4 border-t border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900">
          <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={isSaving}>
            Cancel
          </Button>
          {activeTab === 'create' ? (
            <Button
              onClick={handleSaveNewIncident}
              disabled={isSaving || isAnalyzing || !editedIncident.name}
              className="bg-pink-500 hover:bg-pink-600"
            >
              {isSaving ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  Saving...
                </>
              ) : (
                <>
                  <PlusCircle className="w-4 h-4 mr-2" />
                  Create Incident
                </>
              )}
            </Button>
          ) : (
            <Button
              onClick={handleAddToExisting}
              disabled={isSaving || !selectedIncident}
              className="bg-pink-500 hover:bg-pink-600"
            >
              {isSaving ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  Adding...
                </>
              ) : (
                <>
                  <FolderPlus className="w-4 h-4 mr-2" />
                  Add to Incident
                </>
              )}
            </Button>
          )}
        </div>
      </div>
    </>
  );

  return createPortal(modalContent, document.body);
}

export default PromoteToIncidentModal;
