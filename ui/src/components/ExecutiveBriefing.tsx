/**
 * Executive Briefing Component
 * Persona-based executive analysis of news articles
 */

import { useState, useEffect } from 'react';
import {
  Loader2,
  AlertCircle,
  CheckCircle2,
  Newspaper,
  ChevronDown,
  ChevronUp,
  Briefcase,
  Clock,
  TrendingUp,
  TrendingDown,
  AlertTriangle,
  Lightbulb,
  Target,
  Save,
  Edit3,
  Check,
  X,
  ExternalLink,
  Zap,
  Shield,
  BarChart3,
  Volume2,
} from 'lucide-react';
import { extractErrorMessage } from '../services/api';
import { Button } from './ui/button';
import { Progress } from './ui/progress';
import { Alert, AlertDescription, AlertTitle } from './ui/alert';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';
import { Badge } from './ui/badge';
import { Separator } from './ui/separator';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Textarea } from './ui/textarea';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from './ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from './ui/select';
import {
  EB_STAGES,
  type BriefingArticle,
  type Theme,
  type PriorityAction,
  type RiskSummary,
  type OpportunitySummary,
  type FocusArea,
  type EBResult,
  type SavedBriefing,
} from '../hooks/useExecutiveBriefing';
import { PodcastScriptModal } from './PodcastScriptModal';

interface ExecutiveBriefingProps {
  topic?: string;
  // State from hook
  isGenerating: boolean;
  currentStage: string;
  stageProgress: number;
  overallProgress: number;
  articles: BriefingArticle[];
  briefingSummary: string;
  themes: Theme[];
  priorityActions: PriorityAction[];
  riskSummary: RiskSummary | null;
  opportunitySummary: OpportunitySummary | null;
  focusAreas: FocusArea[];
  podcastScript: string;
  result: EBResult | null;
  error: string | null;
  articlesSelected: number;
  articlesAnalyzed: number;
  currentArticle: number;
  currentArticleTitle: string;
  // Saved briefings
  savedBriefings: SavedBriefing[];
  isSaving: boolean;
  isLoadingSaved: boolean;
  // Config state
  persona: string;
  articleCount: number;
  daysBack: number;
  includePodcastScript: boolean;
  podcastDuration: 'short' | 'medium' | 'long';
  onPersonaChange: (value: string) => void;
  onArticleCountChange: (value: number) => void;
  onDaysBackChange: (value: number) => void;
  onIncludePodcastScriptChange: (value: boolean) => void;
  onPodcastDurationChange: (value: 'short' | 'medium' | 'long') => void;
  onPodcastScriptChange: (value: string) => void;
  // Actions
  onClearError: () => void;
  onClearResults: () => void;
  onUpdateArticle: (index: number, updates: Partial<BriefingArticle>) => void;
  // Save/Load actions
  onSaveBriefing: (topic: string, name: string, description?: string) => Promise<void>;
  onLoadSavedBriefings: (topic: string) => Promise<void>;
  onLoadSavedBriefing: (id: number) => Promise<void>;
  onDeleteSavedBriefing: (id: number) => Promise<void>;
  // Podcast modal control (controlled from App.tsx header)
  showPodcastModal?: boolean;
  onPodcastModalChange?: (open: boolean) => void;
}

// Stage indicator component
function EBStageIndicator({
  stages,
  currentStage,
  stageProgress
}: {
  stages: typeof EB_STAGES;
  currentStage: string;
  stageProgress: number;
}) {
  const getStageStatus = (stageName: string) => {
    const currentIndex = stages.findIndex(s => s.name === currentStage);
    const stageIndex = stages.findIndex(s => s.name === stageName);

    if (currentStage === 'complete') return 'complete';
    if (stageIndex < currentIndex) return 'complete';
    if (stageIndex === currentIndex) return 'active';
    return 'pending';
  };

  return (
    <div className="flex items-center gap-2 mb-6">
      {stages.map((stage, index) => {
        const status = getStageStatus(stage.name);
        return (
          <div key={stage.name} className="flex items-center">
            <div className="flex flex-col items-center">
              <div
                className={`
                  w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium
                  ${status === 'complete' ? 'bg-green-500 text-white' : ''}
                  ${status === 'active' ? 'bg-blue-500 text-white animate-pulse' : ''}
                  ${status === 'pending' ? 'bg-gray-200 text-gray-500' : ''}
                `}
              >
                {status === 'complete' ? (
                  <CheckCircle2 className="w-4 h-4" />
                ) : status === 'active' ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  index + 1
                )}
              </div>
              <span className={`text-xs mt-1 ${status === 'active' ? 'text-blue-600 font-medium' : 'text-gray-500'}`}>
                {stage.label}
              </span>
            </div>
            {index < stages.length - 1 && (
              <div className={`w-12 h-0.5 mx-2 ${
                getStageStatus(stages[index + 1].name) !== 'pending' ? 'bg-green-500' : 'bg-gray-200'
              }`} />
            )}
          </div>
        );
      })}
    </div>
  );
}

// Article card component
function ArticleCard({
  article,
  index,
  onUpdate
}: {
  article: BriefingArticle;
  index: number;
  onUpdate: (updates: Partial<BriefingArticle>) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [editingNotes, setEditingNotes] = useState(false);
  const [notes, setNotes] = useState(article.user_notes || '');

  const handleSaveNotes = () => {
    onUpdate({ user_notes: notes });
    setEditingNotes(false);
  };

  const getRiskOpportunityColor = (type: string) => {
    switch (type) {
      case 'risk': return 'bg-red-100 text-red-700';
      case 'opportunity': return 'bg-green-100 text-green-700';
      default: return 'bg-yellow-100 text-yellow-700';
    }
  };

  const getSignalStrengthColor = (strength: string) => {
    switch (strength) {
      case 'strong': return 'bg-blue-100 text-blue-700';
      case 'moderate': return 'bg-gray-100 text-gray-700';
      default: return 'bg-gray-50 text-gray-500';
    }
  };

  const getTimeHorizonIcon = (horizon: string) => {
    switch (horizon) {
      case 'Immediate': return <Zap className="w-3 h-3" />;
      case 'Medium': return <Clock className="w-3 h-3" />;
      default: return <Target className="w-3 h-3" />;
    }
  };

  return (
    <Card className={`border-l-4 ${
      article.risk_opportunity === 'risk' ? 'border-l-red-500' :
      article.risk_opportunity === 'opportunity' ? 'border-l-green-500' :
      'border-l-yellow-500'
    }`}>
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between">
          <div className="flex-1">
            <CardTitle className="text-base">{article.title}</CardTitle>
            <CardDescription className="text-sm flex items-center gap-2 mt-1">
              <span>{article.source}</span>
              <span className="text-gray-300">|</span>
              <span>{article.date}</span>
              {article.url && (
                <a href={article.url} target="_blank" rel="noopener noreferrer" className="text-blue-500 hover:underline">
                  <ExternalLink className="w-3 h-3" />
                </a>
              )}
            </CardDescription>
          </div>
          <div className="flex items-center gap-2">
            {article.user_edited && (
              <Badge variant="outline" className="text-xs text-orange-600">Edited</Badge>
            )}
            <Badge className={getRiskOpportunityColor(article.risk_opportunity)}>
              {article.risk_opportunity === 'risk' ? <TrendingDown className="w-3 h-3 mr-1" /> :
               article.risk_opportunity === 'opportunity' ? <TrendingUp className="w-3 h-3 mr-1" /> :
               <BarChart3 className="w-3 h-3 mr-1" />}
              {article.risk_opportunity}
            </Badge>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {/* Executive Takeaway */}
        <div className="bg-blue-50 rounded p-3 mb-4">
          <p className="text-sm font-semibold text-blue-900 flex items-center gap-2">
            <Lightbulb className="w-4 h-4" />
            Executive Takeaway
          </p>
          <p className="text-sm text-blue-800 mt-1">{article.executive_takeaway}</p>
        </div>

        {/* Quick Info */}
        <div className="flex flex-wrap gap-2 mb-4">
          <Badge variant="outline" className="text-xs">
            {getTimeHorizonIcon(article.time_horizon)}
            <span className="ml-1">{article.time_horizon}</span>
          </Badge>
          <Badge className={getSignalStrengthColor(article.signal_strength)}>
            Signal: {article.signal_strength}
          </Badge>
          <Badge variant="secondary" className="text-xs capitalize">
            {article.category}
          </Badge>
        </div>

        {/* Summary */}
        <div className="mb-4">
          <p className="text-sm text-gray-700">{article.summary}</p>
        </div>

        {/* Expandable sections */}
        {expanded && (
          <>
            <Separator className="my-4" />

            {/* Strategic Relevance */}
            <div className="mb-4">
              <h4 className="text-sm font-semibold flex items-center gap-2 mb-2">
                <Target className="w-4 h-4 text-indigo-500" />
                Strategic Relevance
              </h4>
              <p className="text-sm text-gray-700">{article.strategic_relevance}</p>
            </div>

            {/* Executive Actions */}
            {article.executive_action.length > 0 && (
              <div className="mb-4">
                <h4 className="text-sm font-semibold flex items-center gap-2 mb-2">
                  <Briefcase className="w-4 h-4 text-green-500" />
                  Recommended Actions
                </h4>
                <ul className="text-sm space-y-1">
                  {article.executive_action.map((action, idx) => (
                    <li key={idx} className="flex items-start gap-2">
                      <span className="text-green-500 mt-0.5">{idx + 1}.</span>
                      <span>{action}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Scores */}
            <div className="bg-gray-50 rounded-lg p-3 mb-4">
              <h4 className="text-xs font-semibold text-gray-500 mb-2">SCORES</h4>
              <div className="grid grid-cols-4 gap-2 text-xs">
                <div>
                  <span className="text-gray-500">Relevance: </span>
                  <span className="font-medium">{article.scores.relevance}/5</span>
                </div>
                <div>
                  <span className="text-gray-500">Novelty: </span>
                  <span className="font-medium">{article.scores.novelty}/5</span>
                </div>
                <div>
                  <span className="text-gray-500">Credibility: </span>
                  <span className="font-medium">{article.scores.credibility}/5</span>
                </div>
                <div>
                  <span className="text-gray-500">Representativeness: </span>
                  <span className="font-medium">{article.scores.representativeness}/5</span>
                </div>
              </div>
            </div>

            {/* User Notes */}
            <div className="border-t pt-4">
              <div className="flex items-center justify-between mb-2">
                <h4 className="text-sm font-semibold flex items-center gap-2">
                  <Edit3 className="w-4 h-4 text-gray-500" />
                  Notes
                </h4>
                {!editingNotes && (
                  <Button variant="ghost" size="sm" onClick={() => setEditingNotes(true)}>
                    <Edit3 className="w-3 h-3 mr-1" />
                    Edit
                  </Button>
                )}
              </div>
              {editingNotes ? (
                <div className="space-y-2">
                  <Textarea
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                    placeholder="Add your notes..."
                    rows={3}
                  />
                  <div className="flex gap-2">
                    <Button size="sm" onClick={handleSaveNotes}>
                      <Check className="w-3 h-3 mr-1" />
                      Save
                    </Button>
                    <Button variant="ghost" size="sm" onClick={() => {
                      setNotes(article.user_notes || '');
                      setEditingNotes(false);
                    }}>
                      <X className="w-3 h-3 mr-1" />
                      Cancel
                    </Button>
                  </div>
                </div>
              ) : article.user_notes ? (
                <p className="text-sm text-gray-600 bg-yellow-50 p-2 rounded italic">{article.user_notes}</p>
              ) : (
                <p className="text-sm text-gray-400 italic">No notes added</p>
              )}
            </div>
          </>
        )}

        {/* Expand/Collapse button */}
        <Button variant="ghost" size="sm" className="w-full mt-2" onClick={() => setExpanded(!expanded)}>
          {expanded ? (
            <>
              <ChevronUp className="w-4 h-4 mr-2" />
              Show Less
            </>
          ) : (
            <>
              <ChevronDown className="w-4 h-4 mr-2" />
              Show Full Analysis
            </>
          )}
        </Button>
      </CardContent>
    </Card>
  );
}

// Synthesis Panel
function SynthesisPanel({
  briefingSummary,
  themes,
  priorityActions,
  riskSummary,
  opportunitySummary,
  focusAreas,
}: {
  briefingSummary: string;
  themes: Theme[];
  priorityActions: PriorityAction[];
  riskSummary: RiskSummary | null;
  opportunitySummary: OpportunitySummary | null;
  focusAreas: FocusArea[];
}) {
  const [expanded, setExpanded] = useState(true);

  return (
    <Card className="border-blue-200 bg-blue-50/50">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-lg flex items-center gap-2">
            <BarChart3 className="w-5 h-5 text-blue-500" />
            Briefing Synthesis
          </CardTitle>
          <Button variant="ghost" size="sm" onClick={() => setExpanded(!expanded)}>
            {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </Button>
        </div>
      </CardHeader>
      {expanded && (
        <CardContent className="space-y-6">
          {/* Executive Summary */}
          {briefingSummary && (
            <div>
              <h4 className="text-sm font-semibold mb-2">Executive Summary</h4>
              <p className="text-sm text-gray-700">{briefingSummary}</p>
            </div>
          )}

          {/* Themes */}
          {themes.length > 0 && (
            <div>
              <h4 className="text-sm font-semibold mb-2">Key Themes</h4>
              <div className="space-y-2">
                {themes.map((theme, idx) => (
                  <div key={idx} className="bg-white rounded p-3">
                    <p className="font-medium text-sm">{theme.theme_name}</p>
                    <p className="text-xs text-gray-600 mt-1">{theme.description}</p>
                    {theme.strategic_implication && (
                      <p className="text-xs text-blue-600 mt-1 italic">{theme.strategic_implication}</p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Priority Actions */}
          {priorityActions.length > 0 && (
            <div>
              <h4 className="text-sm font-semibold mb-2">Priority Actions</h4>
              <ul className="space-y-2">
                {priorityActions.map((action, idx) => (
                  <li key={idx} className="flex items-start gap-2 bg-white rounded p-2">
                    <Badge variant="outline" className="text-xs capitalize shrink-0">
                      {action.urgency.replace('_', ' ')}
                    </Badge>
                    <div>
                      <p className="text-sm font-medium">{action.action}</p>
                      {action.rationale && (
                        <p className="text-xs text-gray-500 mt-1">{action.rationale}</p>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Risk & Opportunity Summary */}
          <div className="grid md:grid-cols-2 gap-4">
            {riskSummary && (
              <div className="bg-red-50 rounded p-3">
                <h4 className="text-sm font-semibold flex items-center gap-2 mb-2 text-red-700">
                  <Shield className="w-4 h-4" />
                  Risk Assessment: {riskSummary.overall_risk_level}
                </h4>
                <ul className="text-xs space-y-1">
                  {riskSummary.key_risks.map((risk, idx) => (
                    <li key={idx} className="flex items-start gap-1">
                      <span className="text-red-500">•</span>
                      <span>{risk}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {opportunitySummary && (
              <div className="bg-green-50 rounded p-3">
                <h4 className="text-sm font-semibold flex items-center gap-2 mb-2 text-green-700">
                  <Lightbulb className="w-4 h-4" />
                  Opportunity Level: {opportunitySummary.overall_opportunity_level}
                </h4>
                <ul className="text-xs space-y-1">
                  {opportunitySummary.key_opportunities.map((opp, idx) => (
                    <li key={idx} className="flex items-start gap-1">
                      <span className="text-green-500">•</span>
                      <span>{opp}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          {/* Focus Areas */}
          {focusAreas.length > 0 && (
            <div>
              <h4 className="text-sm font-semibold mb-2">Focus Areas</h4>
              <div className="flex flex-wrap gap-2">
                {focusAreas.map((area, idx) => (
                  <Badge key={idx} variant="secondary" className="text-xs">
                    {area.area}
                  </Badge>
                ))}
              </div>
            </div>
          )}
        </CardContent>
      )}
    </Card>
  );
}

// Empty state
function EmptyState() {
  return (
    <div className="text-center py-12 text-gray-500">
      <Newspaper className="w-12 h-12 mx-auto mb-4 opacity-50" />
      <p>No executive briefing available.</p>
      <p className="text-sm mt-2">Click "Generate" to create a briefing from your articles.</p>
    </div>
  );
}

export function ExecutiveBriefing({
  topic,
  isGenerating,
  currentStage,
  stageProgress,
  overallProgress,
  articles,
  briefingSummary,
  themes,
  priorityActions,
  riskSummary,
  opportunitySummary,
  focusAreas,
  podcastScript,
  result,
  error,
  articlesSelected,
  articlesAnalyzed,
  currentArticle,
  currentArticleTitle,
  savedBriefings,
  isSaving,
  isLoadingSaved,
  persona,
  articleCount,
  daysBack,
  includePodcastScript,
  podcastDuration,
  onPersonaChange,
  onArticleCountChange,
  onDaysBackChange,
  onIncludePodcastScriptChange,
  onPodcastDurationChange,
  onPodcastScriptChange,
  onClearError,
  onClearResults,
  onUpdateArticle,
  onSaveBriefing,
  onLoadSavedBriefings,
  onLoadSavedBriefing,
  onDeleteSavedBriefing,
  showPodcastModal,
  onPodcastModalChange,
}: ExecutiveBriefingProps) {
  const [showConfig, setShowConfig] = useState(false);
  const [showSaveDialog, setShowSaveDialog] = useState(false);
  const [saveName, setSaveName] = useState('');
  const [saveDescription, setSaveDescription] = useState('');
  const [saveError, setSaveError] = useState<string | null>(null);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [briefingToDelete, setBriefingToDelete] = useState<SavedBriefing | null>(null);

  // Podcast state (local state for UI, script comes from props or generated on-demand)
  const [localPodcastScript, setLocalPodcastScript] = useState('');
  const [isGeneratingScript, setIsGeneratingScript] = useState(false);
  const [isGeneratingAudio, setIsGeneratingAudio] = useState(false);
  const [podcastAudioUrl, setPodcastAudioUrl] = useState<string | null>(null);
  const [podcastError, setPodcastError] = useState<string | null>(null);

  // Use podcastScript from props if available, otherwise use local state
  const effectivePodcastScript = podcastScript || localPodcastScript;

  // Fetch saved briefings when topic changes
  useEffect(() => {
    if (topic) {
      onLoadSavedBriefings(topic);
    }
  }, [topic, onLoadSavedBriefings]);

  const handleSave = async () => {
    if (!topic || !saveName.trim()) return;

    setSaveError(null);
    try {
      await onSaveBriefing(topic, saveName.trim(), saveDescription.trim() || undefined);
      setShowSaveDialog(false);
      setSaveName('');
      setSaveDescription('');
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : 'Failed to save');
    }
  };

  const handleDelete = async () => {
    if (!briefingToDelete) return;

    try {
      await onDeleteSavedBriefing(briefingToDelete.id);
    } catch (err) {
      console.error('Error deleting briefing:', err);
    } finally {
      setShowDeleteConfirm(false);
      setBriefingToDelete(null);
    }
  };

  // Generate podcast script when modal opens using LLM API (only if not already provided from generation)
  useEffect(() => {
    if (showPodcastModal && briefingSummary && !effectivePodcastScript && !isGeneratingScript) {
      const generateScript = async () => {
        setIsGeneratingScript(true);
        setPodcastError(null);

        try {
          const response = await fetch('/api/executive-briefing/generate-podcast-script', {
            method: 'POST',
            credentials: 'include',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              topic: topic || 'Intelligence Report',
              briefing_summary: briefingSummary,
              themes: themes.slice(0, 5),
              priority_actions: priorityActions.slice(0, 5),
              articles: articles.slice(0, 6).map(a => ({
                title: a.title,
                executive_takeaway: a.executive_takeaway,
                summary: a.summary,
                strategic_relevance: a.strategic_relevance
              })),
              duration: podcastDuration || 'short',
              model: 'gpt-4o'
            })
          });

          if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || 'Failed to generate script');
          }

          const data = await response.json();
          if (data.success && data.script) {
            setLocalPodcastScript(data.script);
            // Also update the parent if a handler is provided
            if (onPodcastScriptChange) {
              onPodcastScriptChange(data.script);
            }
          } else {
            throw new Error('No script returned from API');
          }
        } catch (err) {
          console.error('Error generating podcast script:', err);
          setPodcastError(err instanceof Error ? err.message : 'Failed to generate script');

          // Fallback to basic script generation
          const scriptParts = [];
          scriptParts.push(`# Executive Briefing: ${topic || 'Intelligence Report'}\n`);
          scriptParts.push(`## Overview\n${briefingSummary}\n`);

          if (themes.length > 0) {
            scriptParts.push(`## Key Themes\n`);
            themes.slice(0, 3).forEach((theme, i) => {
              scriptParts.push(`### ${i + 1}. ${theme.theme_name}\n${theme.description}\n`);
            });
          }

          if (priorityActions.length > 0) {
            scriptParts.push(`## Priority Actions\n`);
            priorityActions.slice(0, 3).forEach((action, i) => {
              scriptParts.push(`${i + 1}. **${action.action}** (${action.urgency.replace('_', ' ')})\n`);
            });
          }

          scriptParts.push(`\n## Closing\nThat concludes this executive briefing on ${topic || 'the latest developments'}.`);
          setLocalPodcastScript(scriptParts.join('\n'));
        } finally {
          setIsGeneratingScript(false);
        }
      };

      generateScript();
    }
  }, [showPodcastModal, briefingSummary, themes, priorityActions, topic, effectivePodcastScript, isGeneratingScript, articles, podcastDuration, onPodcastScriptChange]);

  // Regenerate podcast script - clears script to trigger useEffect
  const handleRegeneratePodcastScript = () => {
    setLocalPodcastScript('');
    if (onPodcastScriptChange) {
      onPodcastScriptChange('');
    }
    // The useEffect above will regenerate when script becomes empty
  };

  // Generate audio from script
  const handleGenerateAudio = async (editedScript: string, voiceId: string, duration: string) => {
    setIsGeneratingAudio(true);
    setPodcastError(null);

    try {
      const res = await fetch('/api/generate_tts_podcast', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          podcast_name: topic || 'Executive Briefing',
          episode_title: `Executive Briefing - ${new Date().toLocaleDateString()}`,
          script: editedScript,
          mode: 'bulletin',
          duration: duration,
          host_voice_id: voiceId
        })
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || 'Failed to generate audio');
      }

      const data = await res.json();

      // Poll for completion if we get a podcast_id
      if (data.podcast_id) {
        const pollInterval = setInterval(async () => {
          try {
            const statusRes = await fetch(`/api/podcast/status/${data.podcast_id}`, {
              credentials: 'include'
            });
            if (statusRes.ok) {
              const statusData = await statusRes.json();
              if (statusData.status === 'completed') {
                clearInterval(pollInterval);
                setPodcastAudioUrl(statusData.audio_url);
                setIsGeneratingAudio(false);
                if (onPodcastModalChange) onPodcastModalChange(false);
              } else if (statusData.status === 'failed') {
                clearInterval(pollInterval);
                setPodcastError(extractErrorMessage(statusData.error, 'Audio generation failed'));
                setIsGeneratingAudio(false);
              }
            }
          } catch (pollErr) {
            console.error('Error polling podcast status:', pollErr);
          }
        }, 2000);

        setTimeout(() => {
          clearInterval(pollInterval);
          if (isGeneratingAudio) {
            setPodcastError('Audio generation timed out');
            setIsGeneratingAudio(false);
          }
        }, 300000);
      } else if (data.audio_url) {
        setPodcastAudioUrl(data.audio_url);
        setIsGeneratingAudio(false);
        if (onPodcastModalChange) onPodcastModalChange(false);
      }
    } catch (err) {
      setPodcastError(err instanceof Error ? err.message : 'Failed to generate audio');
      setIsGeneratingAudio(false);
      console.error('Error generating audio:', err);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-xl font-semibold text-gray-900 flex items-center gap-2">
          <Briefcase className="w-5 h-5 text-blue-500" />
          Executive Briefing
        </h2>
        <p className="text-sm text-gray-500 mt-1">
          Persona-based analysis of top articles
        </p>
      </div>

      {/* Quick config toggle */}
      <div className="flex items-center gap-4 text-sm">
        <button
          onClick={() => setShowConfig(!showConfig)}
          className="text-gray-500 hover:text-gray-700 flex items-center gap-1"
        >
          {showConfig ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          Settings
        </button>
        <span className="text-gray-400">|</span>
        <span className="text-gray-500">
          Persona: <Badge variant="outline">{persona}</Badge>
        </span>
        <span className="text-gray-500">
          Articles: {articleCount}
        </span>
        {topic && (
          <>
            <span className="text-gray-400">|</span>
            <Badge variant="outline">{topic}</Badge>
          </>
        )}
      </div>

      {/* Expandable config */}
      {showConfig && (
        <Card>
          <CardContent className="pt-4">
            <div className="grid grid-cols-3 gap-4">
              <div>
                <label className="text-sm font-medium text-gray-700">Persona</label>
                <Select value={persona} onValueChange={onPersonaChange}>
                  <SelectTrigger className="mt-1">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="CEO">CEO</SelectItem>
                    <SelectItem value="CMO">CMO</SelectItem>
                    <SelectItem value="CTO">CTO</SelectItem>
                    <SelectItem value="CISO">CISO</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <label className="text-sm font-medium text-gray-700">Articles</label>
                <input
                  type="number"
                  value={articleCount}
                  onChange={(e) => onArticleCountChange(Number(e.target.value))}
                  min={1}
                  max={8}
                  className="mt-1 w-full px-3 py-2 border rounded-md text-sm"
                />
              </div>
              <div>
                <label className="text-sm font-medium text-gray-700">Days Back</label>
                <Select value={daysBack.toString()} onValueChange={(v) => onDaysBackChange(parseInt(v))}>
                  <SelectTrigger className="mt-1 w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="1">Last 24 hours</SelectItem>
                    <SelectItem value="7">Last 7 days</SelectItem>
                    <SelectItem value="30">Last 30 days</SelectItem>
                    <SelectItem value="60">Last 60 days</SelectItem>
                    <SelectItem value="90">Last 90 days</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            {/* Podcast script generation options */}
            <div className="mt-4 pt-4 border-t">
              <div className="flex items-center gap-4">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={includePodcastScript}
                    onChange={(e) => onIncludePodcastScriptChange(e.target.checked)}
                    className="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                  />
                  <span className="text-sm font-medium text-gray-700 flex items-center gap-1">
                    <Volume2 className="w-4 h-4" />
                    Generate podcast script with briefing
                  </span>
                </label>

                {includePodcastScript && (
                  <div className="flex items-center gap-2">
                    <label className="text-sm text-gray-600">Duration:</label>
                    <Select value={podcastDuration} onValueChange={onPodcastDurationChange}>
                      <SelectTrigger className="w-28">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="short">Short (2-3m)</SelectItem>
                        <SelectItem value="medium">Medium (4-5m)</SelectItem>
                        <SelectItem value="long">Long (7-10m)</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                )}
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Error display */}
      {error && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>Generation Error</AlertTitle>
          <AlertDescription className="flex items-center justify-between">
            {error}
            <Button variant="ghost" size="sm" onClick={onClearError}>
              Dismiss
            </Button>
          </AlertDescription>
        </Alert>
      )}

      {/* Generation progress */}
      {isGenerating && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg flex items-center gap-2">
              <Loader2 className="w-5 h-5 animate-spin text-blue-500" />
              Generating Briefing...
            </CardTitle>
            <CardDescription>
              {currentStage === 'analysis' && currentArticleTitle
                ? `Analyzing: ${currentArticleTitle}`
                : EB_STAGES.find(s => s.name === currentStage)?.description || 'Initializing...'}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <EBStageIndicator stages={EB_STAGES} currentStage={currentStage} stageProgress={stageProgress} />
            <Progress value={overallProgress * 100} className="h-2 mb-4" />
            <div className="grid grid-cols-3 gap-4 text-sm">
              <div className="bg-gray-50 rounded p-2 text-center">
                <p className="text-2xl font-bold">{articlesSelected}</p>
                <p className="text-xs text-gray-500">Selected</p>
              </div>
              <div className="bg-gray-50 rounded p-2 text-center">
                <p className="text-2xl font-bold">{articlesAnalyzed}</p>
                <p className="text-xs text-gray-500">Analyzed</p>
              </div>
              <div className="bg-gray-50 rounded p-2 text-center">
                <p className="text-2xl font-bold">{currentArticle}</p>
                <p className="text-xs text-gray-500">Current</p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Results display */}
      {!isGenerating && articles.length > 0 ? (
        <div className="space-y-6">
          {/* Synthesis Panel */}
          {(briefingSummary || themes.length > 0 || priorityActions.length > 0) && (
            <SynthesisPanel
              briefingSummary={briefingSummary}
              themes={themes}
              priorityActions={priorityActions}
              riskSummary={riskSummary}
              opportunitySummary={opportunitySummary}
              focusAreas={focusAreas}
            />
          )}

          {/* Articles */}
          <div>
            <h3 className="text-lg font-semibold flex items-center gap-2 mb-4">
              <Newspaper className="w-5 h-5 text-blue-500" />
              Analyzed Articles ({articles.length})
            </h3>
            <div className="grid gap-4">
              {articles.map((article, idx) => (
                <ArticleCard
                  key={idx}
                  article={article}
                  index={idx}
                  onUpdate={(updates) => onUpdateArticle(idx, updates)}
                />
              ))}
            </div>
          </div>
        </div>
      ) : (
        !isGenerating && <EmptyState />
      )}

      {/* Save Dialog */}
      <Dialog open={showSaveDialog} onOpenChange={setShowSaveDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Save Briefing</DialogTitle>
            <DialogDescription>Save this briefing for future reference.</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label htmlFor="eb-save-name">Name</Label>
              <Input
                id="eb-save-name"
                placeholder="e.g., Q4 Market Analysis"
                value={saveName}
                onChange={(e) => setSaveName(e.target.value)}
              />
            </div>
            <div>
              <Label htmlFor="eb-save-description">Description (optional)</Label>
              <Textarea
                id="eb-save-description"
                placeholder="Add notes..."
                value={saveDescription}
                onChange={(e) => setSaveDescription(e.target.value)}
                rows={3}
              />
            </div>
            <div className="text-sm text-gray-500 bg-gray-50 p-3 rounded">
              <div>Topic: <strong>{topic}</strong></div>
              <div>Persona: <strong>{persona}</strong></div>
              <div>Articles: <strong>{articles.length}</strong></div>
            </div>
            {saveError && (
              <Alert variant="destructive">
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>{saveError}</AlertDescription>
              </Alert>
            )}
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setShowSaveDialog(false)}>Cancel</Button>
            <Button onClick={handleSave} disabled={!saveName.trim() || isSaving}>
              {isSaving ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Save className="w-4 h-4 mr-2" />}
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={showDeleteConfirm} onOpenChange={setShowDeleteConfirm}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Delete Briefing?</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete <strong>"{briefingToDelete?.name}"</strong>?
              This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setShowDeleteConfirm(false)}>Cancel</Button>
            <Button variant="destructive" onClick={handleDelete}>Delete</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Podcast Audio Player - shown when audio is ready */}
      {podcastAudioUrl && (
        <Card className="fixed bottom-4 right-4 w-80 shadow-lg z-50">
          <CardContent className="p-4">
            <div className="flex items-center gap-3 mb-3">
              <div className="w-10 h-10 rounded-full bg-blue-100 flex items-center justify-center">
                <Volume2 className="w-5 h-5 text-blue-600" />
              </div>
              <div>
                <p className="font-medium text-sm">Executive Briefing Podcast</p>
                <p className="text-xs text-gray-500">{topic}</p>
              </div>
              <Button
                variant="ghost"
                size="sm"
                className="ml-auto"
                onClick={() => setPodcastAudioUrl(null)}
              >
                <X className="w-4 h-4" />
              </Button>
            </div>
            <audio
              src={podcastAudioUrl}
              controls
              className="w-full"
              autoPlay={false}
            />
          </CardContent>
        </Card>
      )}

      {/* Podcast Script Modal */}
      <PodcastScriptModal
        open={showPodcastModal || false}
        onOpenChange={onPodcastModalChange || (() => {})}
        script={effectivePodcastScript}
        isGeneratingScript={isGeneratingScript}
        onRegenerateScript={handleRegeneratePodcastScript}
        onGenerateAudio={handleGenerateAudio}
        isGeneratingAudio={isGeneratingAudio}
        mode="bulletin"
        duration={podcastDuration || "short"}
        topic={topic}
      />

      {/* Podcast Error Alert */}
      {podcastError && (
        <div className="fixed bottom-4 left-4 z-50">
          <Alert variant="destructive" className="w-80">
            <AlertCircle className="h-4 w-4" />
            <AlertTitle>Podcast Error</AlertTitle>
            <AlertDescription className="flex items-center justify-between">
              <span>{podcastError}</span>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setPodcastError(null)}
              >
                <X className="w-4 h-4" />
              </Button>
            </AlertDescription>
          </Alert>
        </div>
      )}
    </div>
  );
}

export default ExecutiveBriefing;
