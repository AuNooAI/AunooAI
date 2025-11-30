/**
 * Synthetic Focus Group Component
 * Stakeholder personas with rich psychographic profiles
 */

import { useState, useEffect } from 'react';
import {
  Loader2,
  AlertCircle,
  CheckCircle2,
  Users,
  ChevronDown,
  ChevronUp,
  User,
  Briefcase,
  Brain,
  MessageSquare,
  AlertTriangle,
  Lightbulb,
  Shield,
  Eye,
  Target,
  Clock,
  Save,
  Trash2,
  FolderOpen,
  Download,
  Edit3,
  Check,
  X,
  Handshake,
  Swords,
  Scale
} from 'lucide-react';
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
  FG_STAGES,
  type Persona,
  type FGConfig,
  type FGResult,
  type InteractionDynamics,
  type SavedFocusGroup,
} from '../hooks/useFocusGroup';

interface FocusGroupProps {
  topic?: string;
  // Focus Group state from parent (hook lifted to App.tsx)
  isGenerating: boolean;
  currentStage: string;
  stageProgress: number;
  overallProgress: number;
  personas: Persona[];
  focusGroupSummary: string;
  interactionDynamics: InteractionDynamics | null;
  result: FGResult | null;
  error: string | null;
  mentionsFound: number;
  clustersFormed: number;
  personasCreated: number;
  // Saved focus groups
  savedFocusGroups: SavedFocusGroup[];
  isSaving: boolean;
  isLoadingSaved: boolean;
  // Config state
  maxPersonas: number;
  minEvidenceThreshold: number;
  includeDemographics: boolean;
  includePsychographics: boolean;
  includeVoice: boolean;
  onMaxPersonasChange: (value: number) => void;
  onMinEvidenceThresholdChange: (value: number) => void;
  onIncludeDemographicsChange: (value: boolean) => void;
  onIncludePsychographicsChange: (value: boolean) => void;
  onIncludeVoiceChange: (value: boolean) => void;
  // Actions
  onClearError: () => void;
  onClearResults: () => void;
  onUpdatePersona: (personaId: string, updates: Partial<Persona>) => void;
  // Save/Load actions
  onSaveFocusGroup: (topic: string, name: string, description?: string) => Promise<void>;
  onLoadSavedFocusGroups: (topic: string) => Promise<void>;
  onLoadSavedFocusGroup: (id: number) => Promise<void>;
  onDeleteSavedFocusGroup: (id: number) => Promise<void>;
}

// Stage indicator component
function FGStageIndicator({
  stages,
  currentStage,
  stageProgress
}: {
  stages: typeof FG_STAGES;
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
                  ${status === 'active' ? 'bg-indigo-500 text-white animate-pulse' : ''}
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
              <span className={`text-xs mt-1 ${status === 'active' ? 'text-indigo-600 font-medium' : 'text-gray-500'}`}>
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

// Stats display during generation
function GenerationStats({
  mentionsFound,
  clustersFormed,
  personasCreated,
}: {
  mentionsFound: number;
  clustersFormed: number;
  personasCreated: number;
}) {
  return (
    <div className="grid grid-cols-3 gap-4 mb-6">
      <Card>
        <CardContent className="pt-4">
          <div className="flex items-center gap-2">
            <Eye className="w-4 h-4 text-blue-500" />
            <div>
              <p className="text-2xl font-bold">{mentionsFound}</p>
              <p className="text-xs text-gray-500">Mentions Found</p>
            </div>
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="pt-4">
          <div className="flex items-center gap-2">
            <Target className="w-4 h-4 text-orange-500" />
            <div>
              <p className="text-2xl font-bold">{clustersFormed}</p>
              <p className="text-xs text-gray-500">Clusters Formed</p>
            </div>
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="pt-4">
          <div className="flex items-center gap-2">
            <Users className="w-4 h-4 text-indigo-500" />
            <div>
              <p className="text-2xl font-bold">{personasCreated}</p>
              <p className="text-xs text-gray-500">Personas Created</p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

// Risk tolerance visualization
function RiskToleranceBar({ value }: { value: number }) {
  const percentage = value * 100;
  const color = value < 0.3 ? 'bg-green-500' : value < 0.7 ? 'bg-yellow-500' : 'bg-red-500';

  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-2 bg-gray-200 rounded-full overflow-hidden">
        <div className={`h-full ${color} rounded-full`} style={{ width: `${percentage}%` }} />
      </div>
      <span className="text-xs text-gray-500">{value.toFixed(1)}</span>
    </div>
  );
}

// Persona card component
function PersonaCard({
  persona,
  onUpdate
}: {
  persona: Persona;
  onUpdate: (updates: Partial<Persona>) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [editingNotes, setEditingNotes] = useState(false);
  const [notes, setNotes] = useState(persona.user_notes || '');

  const handleSaveNotes = () => {
    onUpdate({ user_notes: notes });
    setEditingNotes(false);
  };

  // Determine stance color
  const stanceColors: Record<string, string> = {
    skeptic: 'text-red-600',
    pragmatist: 'text-yellow-600',
    enthusiast: 'text-green-600',
    evangelist: 'text-blue-600',
  };

  return (
    <Card className="border-l-4 border-l-indigo-500">
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 rounded-full bg-indigo-100 flex items-center justify-center">
              <User className="w-6 h-6 text-indigo-600" />
            </div>
            <div>
              <CardTitle className="text-lg">{persona.name}</CardTitle>
              <CardDescription className="text-sm font-medium text-indigo-600">
                {persona.archetype}
              </CardDescription>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {persona.user_edited && (
              <Badge variant="outline" className="text-xs text-orange-600">
                Edited
              </Badge>
            )}
            <Badge variant="outline" className="bg-white">
              Confidence: {Math.round(persona.confidence_score * 100)}%
            </Badge>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {/* Role & Sector */}
        <div className="flex items-center gap-4 mb-4 text-sm text-gray-600">
          <span className="flex items-center gap-1">
            <Briefcase className="w-4 h-4" />
            {persona.role_title}
          </span>
          <span className="text-gray-300">|</span>
          <span>{persona.sector}</span>
          <span className="text-gray-300">|</span>
          <span className="capitalize">{persona.experience_level}</span>
        </div>

        {/* Quick Attributes */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
          <div className="bg-gray-50 rounded p-2">
            <p className="text-xs text-gray-500">Change Receptivity</p>
            <p className="text-sm font-medium capitalize">{persona.change_receptivity}</p>
          </div>
          <div className="bg-gray-50 rounded p-2">
            <p className="text-xs text-gray-500">Tech Stance</p>
            <p className={`text-sm font-medium capitalize ${stanceColors[persona.technology_stance] || ''}`}>
              {persona.technology_stance}
            </p>
          </div>
          <div className="bg-gray-50 rounded p-2">
            <p className="text-xs text-gray-500">Decision Style</p>
            <p className="text-sm font-medium capitalize">{persona.decision_style}</p>
          </div>
          <div className="bg-gray-50 rounded p-2">
            <p className="text-xs text-gray-500">Risk Tolerance</p>
            <RiskToleranceBar value={persona.risk_tolerance} />
          </div>
        </div>

        {/* Primary Values */}
        <div className="mb-4">
          <p className="text-xs text-gray-500 mb-1">Primary Values</p>
          <div className="flex flex-wrap gap-1">
            {persona.primary_values.map((value, idx) => (
              <Badge key={idx} variant="secondary" className="text-xs">
                {value}
              </Badge>
            ))}
          </div>
        </div>

        {/* Primary Concerns */}
        <div className="mb-4">
          <p className="text-xs text-gray-500 mb-1">Primary Concerns</p>
          <ul className="text-sm space-y-1">
            {persona.primary_concerns.slice(0, expanded ? undefined : 2).map((concern, idx) => (
              <li key={idx} className="flex items-start gap-2">
                <AlertTriangle className="w-3 h-3 text-orange-400 mt-1 flex-shrink-0" />
                <span>{concern}</span>
              </li>
            ))}
          </ul>
        </div>

        {/* Expandable sections */}
        {expanded && (
          <>
            <Separator className="my-4" />

            {/* Fear Triggers & Opportunities */}
            <div className="grid md:grid-cols-2 gap-4 mb-4">
              <div>
                <h4 className="text-sm font-semibold flex items-center gap-2 mb-2">
                  <Shield className="w-4 h-4 text-red-500" />
                  Fear Triggers
                </h4>
                <ul className="text-sm space-y-1">
                  {persona.fear_triggers.map((trigger, idx) => (
                    <li key={idx} className="flex items-start gap-2">
                      <span className="text-red-400">•</span>
                      <span>{trigger}</span>
                    </li>
                  ))}
                </ul>
              </div>
              <div>
                <h4 className="text-sm font-semibold flex items-center gap-2 mb-2">
                  <Lightbulb className="w-4 h-4 text-green-500" />
                  Opportunity Interests
                </h4>
                <ul className="text-sm space-y-1">
                  {persona.opportunity_interests.map((interest, idx) => (
                    <li key={idx} className="flex items-start gap-2">
                      <span className="text-green-400">•</span>
                      <span>{interest}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>

            {/* Voice Description */}
            {persona.voice_description && (
              <div className="mb-4">
                <h4 className="text-sm font-semibold flex items-center gap-2 mb-2">
                  <MessageSquare className="w-4 h-4 text-blue-500" />
                  Voice & Communication Style
                </h4>
                <p className="text-sm text-gray-700 italic">"{persona.voice_description}"</p>
              </div>
            )}

            {/* Typical Questions */}
            {persona.typical_questions.length > 0 && (
              <div className="mb-4">
                <h4 className="text-sm font-semibold flex items-center gap-2 mb-2">
                  <Brain className="w-4 h-4 text-purple-500" />
                  Typical Questions They Ask
                </h4>
                <ul className="text-sm space-y-1">
                  {persona.typical_questions.map((q, idx) => (
                    <li key={idx} className="flex items-start gap-2 text-gray-700">
                      <span className="text-purple-400">?</span>
                      <span>"{q}"</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Influence Vectors */}
            {persona.influence_vectors.length > 0 && (
              <div className="mb-4">
                <h4 className="text-sm font-semibold flex items-center gap-2 mb-2">
                  <Target className="w-4 h-4 text-indigo-500" />
                  How to Influence Them
                </h4>
                <ul className="text-sm space-y-1">
                  {persona.influence_vectors.map((vector, idx) => (
                    <li key={idx} className="flex items-start gap-2">
                      <span className="text-indigo-400">{idx + 1}.</span>
                      <span>{vector}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Additional Attributes */}
            <div className="bg-gray-50 rounded-lg p-3 mb-4">
              <h4 className="text-xs font-semibold text-gray-500 mb-2">ADDITIONAL ATTRIBUTES</h4>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-2 text-xs">
                <div>
                  <span className="text-gray-500">Decision Authority: </span>
                  <span className="capitalize">{persona.decision_authority.replace('_', ' ')}</span>
                </div>
                <div>
                  <span className="text-gray-500">Time Horizon: </span>
                  <span className="capitalize">{persona.time_horizon_focus.replace('_', ' ')}</span>
                </div>
                <div>
                  <span className="text-gray-500">Info Consumption: </span>
                  <span className="capitalize">{persona.information_consumption.replace('_', ' ')}</span>
                </div>
                <div>
                  <span className="text-gray-500">Authority Trust: </span>
                  <span className="capitalize">{persona.authority_trust}</span>
                </div>
                <div>
                  <span className="text-gray-500">Media Trust: </span>
                  <span className="capitalize">{persona.media_trust}</span>
                </div>
                <div>
                  <span className="text-gray-500">Comm Preference: </span>
                  <span className="capitalize">{persona.communication_preference.replace('_', ' ')}</span>
                </div>
              </div>
            </div>

            {/* Source Articles */}
            {persona.source_articles.length > 0 && (
              <div className="bg-blue-50 rounded-lg p-3 mb-4">
                <h4 className="text-xs font-semibold text-gray-500 mb-2">
                  DERIVED FROM {persona.mention_count} ARTICLE MENTIONS
                </h4>
                <div className="text-xs text-gray-600 space-y-1">
                  {persona.source_articles.slice(0, 3).map((uri, idx) => (
                    <a
                      key={idx}
                      href={uri}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="block text-blue-600 hover:underline truncate"
                    >
                      {uri}
                    </a>
                  ))}
                  {persona.source_articles.length > 3 && (
                    <span className="text-gray-400">
                      +{persona.source_articles.length - 3} more articles
                    </span>
                  )}
                </div>
              </div>
            )}

            {/* User Notes */}
            <div className="border-t pt-4">
              <div className="flex items-center justify-between mb-2">
                <h4 className="text-sm font-semibold flex items-center gap-2">
                  <Edit3 className="w-4 h-4 text-gray-500" />
                  User Notes
                </h4>
                {!editingNotes && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setEditingNotes(true)}
                  >
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
                    placeholder="Add your notes about this persona..."
                    rows={3}
                  />
                  <div className="flex gap-2">
                    <Button size="sm" onClick={handleSaveNotes}>
                      <Check className="w-3 h-3 mr-1" />
                      Save
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        setNotes(persona.user_notes || '');
                        setEditingNotes(false);
                      }}
                    >
                      <X className="w-3 h-3 mr-1" />
                      Cancel
                    </Button>
                  </div>
                </div>
              ) : persona.user_notes ? (
                <p className="text-sm text-gray-600 bg-yellow-50 p-2 rounded italic">
                  {persona.user_notes}
                </p>
              ) : (
                <p className="text-sm text-gray-400 italic">No notes added</p>
              )}
            </div>
          </>
        )}

        {/* Expand/Collapse button */}
        <Button
          variant="ghost"
          size="sm"
          className="w-full mt-2"
          onClick={() => setExpanded(!expanded)}
        >
          {expanded ? (
            <>
              <ChevronUp className="w-4 h-4 mr-2" />
              Show Less
            </>
          ) : (
            <>
              <ChevronDown className="w-4 h-4 mr-2" />
              Show Full Profile
            </>
          )}
        </Button>
      </CardContent>
    </Card>
  );
}

// Interaction Dynamics Section
function InteractionDynamicsSection({ dynamics }: { dynamics: InteractionDynamics }) {
  const [expanded, setExpanded] = useState(true);

  return (
    <Card className="border-indigo-200">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-lg flex items-center gap-2">
            <Users className="w-5 h-5 text-indigo-500" />
            Focus Group Dynamics
          </CardTitle>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setExpanded(!expanded)}
          >
            {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </Button>
        </div>
        {/* Diversity Score */}
        <div className="flex items-center gap-2 mt-2">
          <Scale className="w-4 h-4 text-gray-500" />
          <span className="text-sm text-gray-600">Diversity Score:</span>
          <div className="flex-1 max-w-32 h-2 bg-gray-200 rounded-full overflow-hidden">
            <div
              className="h-full bg-indigo-500 rounded-full"
              style={{ width: `${dynamics.diversity_score * 100}%` }}
            />
          </div>
          <span className="text-sm font-medium">{Math.round(dynamics.diversity_score * 100)}%</span>
        </div>
      </CardHeader>
      {expanded && (
        <CardContent>
          {/* Key Insight */}
          {dynamics.key_insight && (
            <div className="bg-indigo-50 rounded-lg p-3 mb-4">
              <h4 className="text-sm font-semibold flex items-center gap-2 mb-1">
                <Lightbulb className="w-4 h-4 text-indigo-500" />
                Key Insight
              </h4>
              <p className="text-sm text-gray-700">{dynamics.key_insight}</p>
            </div>
          )}

          <div className="grid md:grid-cols-2 gap-4 mb-4">
            {/* Consensus Areas */}
            <div>
              <h4 className="text-sm font-semibold flex items-center gap-2 mb-2">
                <Handshake className="w-4 h-4 text-green-500" />
                Consensus Areas ({dynamics.consensus_areas.length})
              </h4>
              {dynamics.consensus_areas.length > 0 ? (
                <ul className="space-y-2">
                  {dynamics.consensus_areas.map((area, idx) => (
                    <li key={idx} className="bg-green-50 rounded p-2 text-sm">
                      <p className="font-medium text-green-700">{area.topic}</p>
                      <p className="text-gray-600 text-xs mt-1">{area.description}</p>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-gray-400 italic">No consensus areas identified</p>
              )}
            </div>

            {/* Tension Points */}
            <div>
              <h4 className="text-sm font-semibold flex items-center gap-2 mb-2">
                <Swords className="w-4 h-4 text-red-500" />
                Tension Points ({dynamics.tension_points.length})
              </h4>
              {dynamics.tension_points.length > 0 ? (
                <ul className="space-y-2">
                  {dynamics.tension_points.map((tension, idx) => (
                    <li key={idx} className="bg-red-50 rounded p-2 text-sm">
                      <p className="font-medium text-red-700">{tension.topic}</p>
                      <p className="text-gray-600 text-xs mt-1">{tension.description}</p>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-gray-400 italic">No significant tensions identified</p>
              )}
            </div>
          </div>

          {/* Diversity Analysis */}
          {dynamics.diversity_analysis && (
            <div className="mb-4">
              <h4 className="text-sm font-semibold mb-1">Diversity Analysis</h4>
              <p className="text-sm text-gray-600">{dynamics.diversity_analysis}</p>
            </div>
          )}

          {/* Blind Spots */}
          {dynamics.blind_spots.length > 0 && (
            <div className="bg-yellow-50 rounded-lg p-3">
              <h4 className="text-sm font-semibold flex items-center gap-2 mb-2">
                <AlertTriangle className="w-4 h-4 text-yellow-600" />
                Blind Spots (Missing Perspectives)
              </h4>
              <ul className="text-sm space-y-1">
                {dynamics.blind_spots.map((spot, idx) => (
                  <li key={idx} className="flex items-start gap-2">
                    <span className="text-yellow-500">•</span>
                    <span>{spot}</span>
                  </li>
                ))}
              </ul>
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
      <Users className="w-12 h-12 mx-auto mb-4 opacity-50" />
      <p>No focus group personas available.</p>
      <p className="text-sm mt-2">Click "Generate" to discover stakeholder personas from your articles.</p>
    </div>
  );
}

export function FocusGroup({
  topic,
  isGenerating,
  currentStage,
  stageProgress,
  overallProgress,
  personas,
  focusGroupSummary,
  interactionDynamics,
  result,
  error,
  mentionsFound,
  clustersFormed,
  personasCreated,
  savedFocusGroups,
  isSaving,
  isLoadingSaved,
  // Config
  maxPersonas,
  minEvidenceThreshold,
  includeDemographics,
  includePsychographics,
  includeVoice,
  onMaxPersonasChange,
  onMinEvidenceThresholdChange,
  onIncludeDemographicsChange,
  onIncludePsychographicsChange,
  onIncludeVoiceChange,
  // Actions
  onClearError,
  onClearResults,
  onUpdatePersona,
  onSaveFocusGroup,
  onLoadSavedFocusGroups,
  onLoadSavedFocusGroup,
  onDeleteSavedFocusGroup,
}: FocusGroupProps) {
  const [showConfig, setShowConfig] = useState(false);

  // Save dialog state
  const [showSaveDialog, setShowSaveDialog] = useState(false);
  const [saveName, setSaveName] = useState('');
  const [saveDescription, setSaveDescription] = useState('');
  const [saveError, setSaveError] = useState<string | null>(null);

  // Delete confirm state
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [fgToDelete, setFgToDelete] = useState<SavedFocusGroup | null>(null);

  // Fetch saved focus groups when topic changes
  useEffect(() => {
    if (topic) {
      onLoadSavedFocusGroups(topic);
    }
  }, [topic, onLoadSavedFocusGroups]);

  const handleSave = async () => {
    if (!topic || !saveName.trim()) return;

    setSaveError(null);
    try {
      await onSaveFocusGroup(topic, saveName.trim(), saveDescription.trim() || undefined);
      setShowSaveDialog(false);
      setSaveName('');
      setSaveDescription('');
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : 'Failed to save');
    }
  };

  const handleDelete = async () => {
    if (!fgToDelete) return;

    try {
      await onDeleteSavedFocusGroup(fgToDelete.id);
    } catch (err) {
      console.error('Error deleting focus group:', err);
    } finally {
      setShowDeleteConfirm(false);
      setFgToDelete(null);
    }
  };

  const handleExport = async (format: 'json' | 'markdown') => {
    if (!result) return;

    try {
      // For now, just create a client-side export
      let content: string;
      let filename: string;
      let mimeType: string;

      if (format === 'json') {
        content = JSON.stringify(result, null, 2);
        filename = `focus_group_${topic?.replace(/\s+/g, '_')}_${Date.now()}.json`;
        mimeType = 'application/json';
      } else {
        // Generate markdown
        const lines = [
          `# Focus Group: ${topic}`,
          '',
          `**Generated:** ${result.metadata?.generated_at || new Date().toISOString()}`,
          `**Personas:** ${personas.length}`,
          `**Articles Analyzed:** ${result.metadata?.articles_analyzed || 0}`,
          '',
          '## Summary',
          '',
          focusGroupSummary || 'No summary available.',
          '',
          '## Personas',
          '',
        ];

        for (const persona of personas) {
          lines.push(`### ${persona.name} - ${persona.archetype}`);
          lines.push('');
          lines.push(`**Role:** ${persona.role_title} | **Sector:** ${persona.sector}`);
          lines.push('');
          lines.push(`**Values:** ${persona.primary_values.join(', ')}`);
          lines.push('');
          lines.push('**Concerns:**');
          for (const concern of persona.primary_concerns) {
            lines.push(`- ${concern}`);
          }
          lines.push('');
          if (persona.voice_description) {
            lines.push(`**Voice:** "${persona.voice_description}"`);
            lines.push('');
          }
          lines.push('---');
          lines.push('');
        }

        content = lines.join('\n');
        filename = `focus_group_${topic?.replace(/\s+/g, '_')}_${Date.now()}.md`;
        mimeType = 'text/markdown';
      }

      // Create download
      const blob = new Blob([content], { type: mimeType });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error('Export error:', err);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-xl font-semibold text-gray-900 flex items-center gap-2">
          <Users className="w-5 h-5 text-indigo-500" />
          Synthetic Focus Group
        </h2>
        <p className="text-sm text-gray-500 mt-1">
          Discover stakeholder personas from article content
        </p>
      </div>

      {/* Quick config toggle */}
      <div className="flex items-center gap-4 text-sm">
        <button
          onClick={() => setShowConfig(!showConfig)}
          className="text-gray-500 hover:text-gray-700 flex items-center gap-1"
        >
          {showConfig ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          Generation Settings
        </button>
        <span className="text-gray-400">|</span>
        <span className="text-gray-500">
          Max Personas: {maxPersonas} · Min Evidence: {minEvidenceThreshold}
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
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div>
                <label className="text-sm font-medium text-gray-700">Max Personas</label>
                <p className="text-xs text-gray-400 mb-1">Upper limit (1-6)</p>
                <input
                  type="number"
                  value={maxPersonas}
                  onChange={(e) => onMaxPersonasChange(Number(e.target.value))}
                  min={1}
                  max={6}
                  className="mt-1 w-full px-3 py-2 border rounded-md text-sm"
                />
              </div>
              <div>
                <label className="text-sm font-medium text-gray-700">Evidence Threshold</label>
                <p className="text-xs text-gray-400 mb-1">Min article mentions</p>
                <input
                  type="number"
                  value={minEvidenceThreshold}
                  onChange={(e) => onMinEvidenceThresholdChange(Number(e.target.value))}
                  min={1}
                  max={5}
                  className="mt-1 w-full px-3 py-2 border rounded-md text-sm"
                />
              </div>
              <div className="col-span-2">
                <label className="text-sm font-medium text-gray-700">Profile Depth</label>
                <p className="text-xs text-gray-400 mb-2">Include these attribute sets</p>
                <div className="flex gap-4">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={includeDemographics}
                      onChange={(e) => onIncludeDemographicsChange(e.target.checked)}
                      className="rounded"
                    />
                    <span className="text-sm">Demographics</span>
                  </label>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={includePsychographics}
                      onChange={(e) => onIncludePsychographicsChange(e.target.checked)}
                      className="rounded"
                    />
                    <span className="text-sm">Psychographics</span>
                  </label>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={includeVoice}
                      onChange={(e) => onIncludeVoiceChange(e.target.checked)}
                      className="rounded"
                    />
                    <span className="text-sm">Voice/Querying</span>
                  </label>
                </div>
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
              <Loader2 className="w-5 h-5 animate-spin text-indigo-500" />
              Generating Focus Group...
            </CardTitle>
            <CardDescription>
              {FG_STAGES.find(s => s.name === currentStage)?.description || 'Initializing...'}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <FGStageIndicator
              stages={FG_STAGES}
              currentStage={currentStage}
              stageProgress={stageProgress}
            />
            <Progress value={overallProgress * 100} className="h-2 mb-4" />
            <GenerationStats
              mentionsFound={mentionsFound}
              clustersFormed={clustersFormed}
              personasCreated={personasCreated}
            />
          </CardContent>
        </Card>
      )}

      {/* Results display */}
      {!isGenerating && personas.length > 0 ? (
        <div className="space-y-6">
          {/* Focus Group Summary */}
          {focusGroupSummary && (
            <Card className="bg-indigo-50 border-indigo-200">
              <CardHeader className="pb-2">
                <CardTitle className="text-lg">Focus Group Overview</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-gray-700 whitespace-pre-wrap">{focusGroupSummary}</p>
              </CardContent>
            </Card>
          )}

          {/* Interaction Dynamics */}
          {interactionDynamics && (
            <InteractionDynamicsSection dynamics={interactionDynamics} />
          )}

          {/* Personas */}
          <div>
            <h3 className="text-lg font-semibold flex items-center gap-2 mb-4">
              <User className="w-5 h-5 text-indigo-500" />
              Stakeholder Personas ({personas.length})
            </h3>
            <div className="grid gap-4">
              {personas.map((persona) => (
                <PersonaCard
                  key={persona.id}
                  persona={persona}
                  onUpdate={(updates) => onUpdatePersona(persona.id, updates)}
                />
              ))}
            </div>
          </div>
        </div>
      ) : (
        !isGenerating && <EmptyState />
      )}

      {/* Action buttons - Save, Load, Clear, Export */}
      {result && !isGenerating && personas.length > 0 && (
        <div className="flex items-center justify-between pt-4 border-t">
          <div className="flex items-center gap-2">
            {/* Load saved focus groups dropdown */}
            {savedFocusGroups.length > 0 && (
              <Select
                onValueChange={(value) => {
                  if (value) {
                    onLoadSavedFocusGroup(parseInt(value, 10));
                  }
                }}
              >
                <SelectTrigger className="w-48">
                  <FolderOpen className="w-4 h-4 mr-1" />
                  <SelectValue placeholder="Load Saved..." />
                </SelectTrigger>
                <SelectContent>
                  {savedFocusGroups.map((fg) => (
                    <SelectItem key={fg.id} value={String(fg.id)}>
                      <div className="flex items-center justify-between w-full">
                        <span className="truncate">{fg.name}</span>
                        <button
                          onClick={(ev) => {
                            ev.stopPropagation();
                            setFgToDelete(fg);
                            setShowDeleteConfirm(true);
                          }}
                          className="ml-2 text-gray-400 hover:text-red-500"
                        >
                          <Trash2 className="w-3 h-3" />
                        </button>
                      </div>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </div>
          <div className="flex items-center gap-2">
            {/* Export buttons */}
            <Button variant="outline" size="sm" onClick={() => handleExport('json')}>
              <Download className="w-4 h-4 mr-1" />
              JSON
            </Button>
            <Button variant="outline" size="sm" onClick={() => handleExport('markdown')}>
              <Download className="w-4 h-4 mr-1" />
              Markdown
            </Button>
            <Button variant="outline" size="sm" onClick={() => setShowSaveDialog(true)} disabled={isSaving}>
              {isSaving ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : <Save className="w-4 h-4 mr-1" />}
              Save
            </Button>
            <Button variant="ghost" size="sm" onClick={onClearResults}>
              <Trash2 className="w-4 h-4 mr-1" />
              Clear
            </Button>
          </div>
        </div>
      )}

      {/* Save Dialog */}
      <Dialog open={showSaveDialog} onOpenChange={setShowSaveDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Save Focus Group</DialogTitle>
            <DialogDescription>
              Save this focus group for future reference.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            <div>
              <Label htmlFor="fg-save-name">Name</Label>
              <Input
                id="fg-save-name"
                placeholder="e.g., Market Stakeholders Q4"
                value={saveName}
                onChange={(e) => setSaveName(e.target.value)}
              />
            </div>

            <div>
              <Label htmlFor="fg-save-description">Description (optional)</Label>
              <Textarea
                id="fg-save-description"
                placeholder="Add notes about this focus group..."
                value={saveDescription}
                onChange={(e) => setSaveDescription(e.target.value)}
                rows={3}
              />
            </div>

            <div className="text-sm text-gray-500 bg-gray-50 p-3 rounded">
              <div>Topic: <strong>{topic}</strong></div>
              <div>Personas: <strong>{personas.length}</strong></div>
              <div>Articles Analyzed: <strong>{result?.metadata?.articles_analyzed || 0}</strong></div>
            </div>

            {saveError && (
              <Alert variant="destructive">
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>{saveError}</AlertDescription>
              </Alert>
            )}
          </div>

          <DialogFooter>
            <Button variant="ghost" onClick={() => setShowSaveDialog(false)}>
              Cancel
            </Button>
            <Button onClick={handleSave} disabled={!saveName.trim() || isSaving}>
              {isSaving ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Save className="w-4 h-4 mr-2" />}
              Save Focus Group
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={showDeleteConfirm} onOpenChange={setShowDeleteConfirm}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Delete Focus Group?</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete <strong>"{fgToDelete?.name}"</strong>?
              This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setShowDeleteConfirm(false)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={handleDelete}>
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

export default FocusGroup;
