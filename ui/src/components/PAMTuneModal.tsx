/**
 * PAM Tune Modal - Enhanced Configuration & Prompt Editor
 *
 * Features:
 * - Analysis settings (type, horizon, data range, article limit)
 * - Individual tool toggles (Semantic Scholar, Google Search)
 * - Per-agent prompt editing with model and temperature selection
 * - Trend focus checkboxes
 * - Specialized search buttons (M&A Activity, Regulation Scan)
 *
 * Following the same pattern as NewsletterTuneModal, EBTuneModal
 */

import React, { useState, useEffect } from 'react';
import {
  Settings, Zap, Eye, DollarSign, Clock, Target, Info, Globe, Cpu,
  ChevronDown, ChevronUp, Sliders, Save, RotateCcw, FileText, TrendingUp,
  Loader2, GraduationCap, Search, Scale, Building2, Sparkles, Users, Plus, Trash2, Tag
} from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from './ui/dialog';
import { Button } from './ui/button';
import { Label } from './ui/label';
import { Input } from './ui/input';
import { Textarea } from './ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { Checkbox } from './ui/checkbox';
import { Switch } from './ui/switch';
import { Badge } from './ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from './ui/tabs';
import { Alert, AlertDescription } from './ui/alert';

interface PAMTuneModalProps {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  // Analysis type
  analysisType: string;
  onAnalysisTypeChange: (value: 'comprehensive' | 'power' | 'attention' | 'money') => void;
  // Time horizon
  timeHorizon: string;
  onTimeHorizonChange: (value: 'current' | '6_months' | '1_year' | '5_years' | '2030') => void;
  // Trend focus
  trendFocus: string[];
  onTrendFocusChange: (trends: string[]) => void;
  // Days back
  daysBack: number;
  onDaysBackChange: (days: number) => void;
  // Article limit
  articleLimit: number;
  onArticleLimitChange: (limit: number) => void;
  // v2 options
  relevanceThreshold?: number;
  onRelevanceThresholdChange?: (threshold: number) => void;
  articlesPerTopic?: number;
  onArticlesPerTopicChange?: (count: number) => void;
  enableExternalData?: boolean;
  onEnableExternalDataChange?: (enabled: boolean) => void;
  parallelAgents?: boolean;
  onParallelAgentsChange?: (enabled: boolean) => void;
  powerModel?: string;
  onPowerModelChange?: (model: string) => void;
  attentionModel?: string;
  onAttentionModelChange?: (model: string) => void;
  moneyModel?: string;
  onMoneyModelChange?: (model: string) => void;
  // Specialized search callbacks
  onMASearch?: () => void;
  onRegulationSearch?: () => void;
}

interface PAMPrompt {
  id: string;
  name: string;
  description: string;
  model: string;
  temperature: number;
  version: string;
  content?: string;
}

interface ProviderStatus {
  google_search: {
    available: boolean;
    reason?: string;
  };
  semantic_scholar: {
    available: boolean;
    reason?: string;
  };
}

interface AvailableModel {
  name: string;
  provider?: string;
}

interface MonitoredEntity {
  id: string;
  entity_name: string;
  entity_type: string;
  entity_subtype?: string;
  created_at: string;
}

interface KeywordPreset {
  name: string;
  description: string;
  keywords_count: {
    cost_dynamics: number;
    ma_activity: number;
    regulatory: number;
  };
  entities: string[];
}

const ENTITY_TYPES = [
  { value: 'brand', label: 'Brand', description: 'Company brand or product line' },
  { value: 'publisher', label: 'Publisher', description: 'News or content publisher' },
  { value: 'tech_company', label: 'Tech Company', description: 'Technology company' },
  { value: 'research_institution', label: 'Research Institution', description: 'University or research org' },
  { value: 'government', label: 'Government', description: 'Government agency or body' },
  { value: 'competitor', label: 'Competitor', description: 'Competitive entity' },
];

const MODEL_OPTIONS = [
  { value: 'default', label: 'Default' },
  { value: 'gpt-4.1-mini', label: 'GPT-4.1 Mini' },
  { value: 'gpt-4.1', label: 'GPT-4.1' },
  { value: 'gpt-4o', label: 'GPT-4o' },
  { value: 'claude-3-5-sonnet-20241022', label: 'Claude 3.5 Sonnet' },
  { value: 'claude-3-5-haiku-20241022', label: 'Claude 3.5 Haiku' },
];

const CREATIVITY_PRESETS = [
  { value: '0.2', label: 'Precise', description: 'Highly focused and deterministic', color: 'bg-blue-100 text-blue-800' },
  { value: '0.3', label: 'Balanced', description: 'Mix of precision and variety', color: 'bg-green-100 text-green-800' },
  { value: '0.5', label: 'Engaging', description: 'More varied responses', color: 'bg-yellow-100 text-yellow-800' },
  { value: '0.7', label: 'Creative', description: 'Higher variety and creativity', color: 'bg-orange-100 text-orange-800' },
];

const TREND_OPTIONS = [
  { id: 'T1', name: 'Invisible LLM Ecosystems', description: 'AI assistants as primary gateway, brand visibility decline' },
  { id: 'T2', name: 'Agentic AI Workflows', description: 'AI agents automating research and literature review' },
  { id: 'T3', name: 'SEO to GEO Shift', description: 'Generative engine optimization replaces traditional SEO' },
  { id: 'T4', name: 'Regulatory Pressures', description: 'AI regulations, copyright, and provenance requirements' },
  { id: 'T5', name: 'Market Consolidation', description: 'Concentration around compute, data, and AI giants' },
];

const AGENT_CONFIG = [
  { id: 'pam_power_agent', name: 'Power Agent', icon: Zap, color: 'text-yellow-500', description: 'Infrastructure control, regulatory influence, network centrality' },
  { id: 'pam_attention_agent', name: 'Attention Agent', icon: Eye, color: 'text-blue-500', description: 'Academic visibility, AI engine exposure, brand visibility' },
  { id: 'pam_money_agent', name: 'Money Agent', icon: DollarSign, color: 'text-green-500', description: 'Funding flows, M&A activity, revenue dynamics' },
  { id: 'pam_trend_agent', name: 'Trend Agent', icon: TrendingUp, color: 'text-pink-500', description: 'T1-T5 trend velocity and direction analysis' },
  { id: 'pam_synthesis_agent', name: 'Synthesis Agent', icon: Sparkles, color: 'text-purple-500', description: 'Executive summary and strategic recommendations' },
];

export const PAMTuneModal: React.FC<PAMTuneModalProps> = ({
  isOpen,
  onOpenChange,
  analysisType,
  onAnalysisTypeChange,
  timeHorizon,
  onTimeHorizonChange,
  trendFocus,
  onTrendFocusChange,
  daysBack,
  onDaysBackChange,
  articleLimit,
  onArticleLimitChange,
  // v2 options
  relevanceThreshold = 0.65,
  onRelevanceThresholdChange,
  articlesPerTopic = 20,
  onArticlesPerTopicChange,
  enableExternalData = true,
  onEnableExternalDataChange,
  parallelAgents = true,
  onParallelAgentsChange,
  powerModel = '',
  onPowerModelChange,
  attentionModel = '',
  onAttentionModelChange,
  moneyModel = '',
  onMoneyModelChange,
  onMASearch,
  onRegulationSearch,
}) => {
  const [activeTab, setActiveTab] = useState('settings');
  const [activeAgent, setActiveAgent] = useState('pam_power_agent');

  // Prompt management state
  const [prompts, setPrompts] = useState<PAMPrompt[]>([]);
  const [editedContent, setEditedContent] = useState<Record<string, string>>({});
  const [editedModels, setEditedModels] = useState<Record<string, string>>({});
  const [editedTemps, setEditedTemps] = useState<Record<string, string>>({});
  const [originalContent, setOriginalContent] = useState<Record<string, string>>({});
  const [originalModels, setOriginalModels] = useState<Record<string, string>>({});
  const [originalTemps, setOriginalTemps] = useState<Record<string, string>>({});

  // External data providers
  const [providerStatus, setProviderStatus] = useState<ProviderStatus | null>(null);
  const [semanticScholarEnabled, setSemanticScholarEnabled] = useState(true);
  const [googleSearchEnabled, setGoogleSearchEnabled] = useState(true);

  // Loading/saving state
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Monitored entities state
  const [entities, setEntities] = useState<MonitoredEntity[]>([]);
  const [newEntityName, setNewEntityName] = useState('');
  const [newEntityType, setNewEntityType] = useState('brand');
  const [entitiesLoading, setEntitiesLoading] = useState(false);
  const [entitySaving, setEntitySaving] = useState(false);

  // Keyword presets state
  const [availablePresets, setAvailablePresets] = useState<KeywordPreset[]>([]);
  const [currentPreset, setCurrentPreset] = useState<string>('scholarly_publishing');
  const [presetSaving, setPresetSaving] = useState(false);

  // Fetch data when modal opens
  useEffect(() => {
    if (!isOpen) return;

    const fetchData = async () => {
      setLoading(true);
      setError(null);
      setSuccessMessage(null);

      try {
        // Fetch prompts, config, provider status, entities, and presets in parallel
        const [promptsRes, configRes, providerRes, entitiesRes, presetsRes] = await Promise.all([
          fetch('/api/pam/prompts', { credentials: 'include' }),
          fetch('/api/pam/config', { credentials: 'include' }),
          fetch('/api/pam/provider-status', { credentials: 'include' }),
          fetch('/api/pam/entities', { credentials: 'include' }),
          fetch('/api/pam/presets', { credentials: 'include' }),
        ]);

        // Parse prompts list
        if (promptsRes.ok) {
          const promptsData = await promptsRes.json();
          const promptsList = promptsData.data?.prompts || [];
          setPrompts(promptsList);

          // Initialize edited values with defaults
          const initModels: Record<string, string> = {};
          const initTemps: Record<string, string> = {};
          for (const p of promptsList) {
            initModels[p.id] = p.model || 'gpt-4.1-mini';
            initTemps[p.id] = String(p.temperature || 0.3);
          }
          setEditedModels(initModels);
          setEditedTemps(initTemps);
          setOriginalModels({ ...initModels });
          setOriginalTemps({ ...initTemps });
        }

        // Parse config
        if (configRes.ok) {
          const configData = await configRes.json();
          const config = configData.data || configData;

          // Set external data toggles
          const extData = config.external_data || {};
          setSemanticScholarEnabled(extData.semantic_scholar?.enabled !== false);
          setGoogleSearchEnabled(extData.google_search?.enabled !== false);
        }

        // Parse provider status
        if (providerRes.ok) {
          const providerData = await providerRes.json();
          setProviderStatus(providerData);
        }

        // Parse entities
        if (entitiesRes.ok) {
          const entitiesData = await entitiesRes.json();
          setEntities(entitiesData.data?.entities || []);
        }

        // Parse presets
        if (presetsRes.ok) {
          const presetsData = await presetsRes.json();
          setAvailablePresets(presetsData.data?.available || []);
          setCurrentPreset(presetsData.data?.current || 'scholarly_publishing');
        }
      } catch (err) {
        console.error('Error fetching PAM data:', err);
        setError(err instanceof Error ? err.message : 'Failed to load data');
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [isOpen]);

  // Fetch individual prompt content when agent tab changes
  useEffect(() => {
    if (!isOpen || !activeAgent || editedContent[activeAgent]) return;

    const fetchPrompt = async () => {
      try {
        const res = await fetch(`/api/pam/prompts/${activeAgent}`, { credentials: 'include' });
        if (res.ok) {
          const data = await res.json();
          const content = data.data?.content || '';
          setEditedContent(prev => ({ ...prev, [activeAgent]: content }));
          setOriginalContent(prev => ({ ...prev, [activeAgent]: content }));
        }
      } catch (err) {
        console.error(`Error fetching prompt ${activeAgent}:`, err);
      }
    };

    fetchPrompt();
  }, [isOpen, activeAgent, editedContent]);

  const handleTrendToggle = (trendId: string) => {
    if (trendFocus.includes(trendId)) {
      onTrendFocusChange(trendFocus.filter(t => t !== trendId));
    } else {
      onTrendFocusChange([...trendFocus, trendId]);
    }
  };

  // Check if there are unsaved changes
  const hasAgentChanges = (agentId: string) => {
    return editedContent[agentId] !== originalContent[agentId] ||
           editedModels[agentId] !== originalModels[agentId] ||
           editedTemps[agentId] !== originalTemps[agentId];
  };

  const hasAnyPromptChanges = () => {
    return Object.keys(editedContent).some(id => hasAgentChanges(id));
  };

  // Save all prompt changes
  const savePromptChanges = async () => {
    setSaving(true);
    setError(null);
    setSuccessMessage(null);

    try {
      const savePromises: Promise<Response>[] = [];

      for (const agentId of Object.keys(editedContent)) {
        if (hasAgentChanges(agentId)) {
          savePromises.push(
            fetch(`/api/pam/prompts/${agentId}`, {
              method: 'PUT',
              credentials: 'include',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                content: editedContent[agentId],
                model: editedModels[agentId] === 'default' ? undefined : editedModels[agentId] || undefined,
                temperature: editedTemps[agentId] ? parseFloat(editedTemps[agentId]) : undefined,
              }),
            })
          );
        }
      }

      if (savePromises.length === 0) {
        setSuccessMessage('No changes to save');
        setSaving(false);
        return;
      }

      const results = await Promise.all(savePromises);
      const failed = results.filter(r => !r.ok);

      if (failed.length > 0) {
        throw new Error(`Failed to save ${failed.length} prompt(s)`);
      }

      // Update originals
      setOriginalContent({ ...editedContent });
      setOriginalModels({ ...editedModels });
      setOriginalTemps({ ...editedTemps });

      setSuccessMessage('All prompt changes saved successfully');
    } catch (err) {
      console.error('Error saving prompts:', err);
      setError(err instanceof Error ? err.message : 'Failed to save');
    } finally {
      setSaving(false);
    }
  };

  // Save external data config
  const saveExternalDataConfig = async () => {
    setSaving(true);
    setError(null);

    try {
      const res = await fetch('/api/pam/config', {
        method: 'PUT',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          external_data: {
            semantic_scholar: { enabled: semanticScholarEnabled },
            google_search: { enabled: googleSearchEnabled },
          },
        }),
      });

      if (!res.ok) throw new Error('Failed to save config');
      setSuccessMessage('External data settings saved');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save config');
    } finally {
      setSaving(false);
    }
  };

  // Reset prompt changes
  const resetPromptChanges = () => {
    setEditedContent({ ...originalContent });
    setEditedModels({ ...originalModels });
    setEditedTemps({ ...originalTemps });
    setSuccessMessage(null);
  };

  // Add new entity
  const addEntity = async () => {
    if (!newEntityName.trim()) return;

    setEntitySaving(true);
    setError(null);

    try {
      const res = await fetch('/api/pam/entities', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          entity_name: newEntityName.trim(),
          entity_type: newEntityType,
        }),
      });

      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || 'Failed to add entity');
      }

      const data = await res.json();
      setEntities(prev => [...prev, data.data]);
      setNewEntityName('');
      setSuccessMessage(`Added "${newEntityName}" to monitored entities`);
    } catch (err) {
      console.error('Error adding entity:', err);
      setError(err instanceof Error ? err.message : 'Failed to add entity');
    } finally {
      setEntitySaving(false);
    }
  };

  // Delete entity
  const deleteEntity = async (entityId: string, entityName: string) => {
    setEntitySaving(true);
    setError(null);

    try {
      const res = await fetch(`/api/pam/entities/${entityId}`, {
        method: 'DELETE',
        credentials: 'include',
      });

      if (!res.ok) {
        throw new Error('Failed to delete entity');
      }

      setEntities(prev => prev.filter(e => e.id !== entityId));
      setSuccessMessage(`Removed "${entityName}" from monitored entities`);
    } catch (err) {
      console.error('Error deleting entity:', err);
      setError(err instanceof Error ? err.message : 'Failed to delete entity');
    } finally {
      setEntitySaving(false);
    }
  };

  // Save preset selection
  const savePreset = async (presetName: string) => {
    setPresetSaving(true);
    setError(null);

    try {
      const res = await fetch('/api/pam/presets', {
        method: 'PUT',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ preset: presetName }),
      });

      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || 'Failed to save preset');
      }

      setCurrentPreset(presetName);
      const preset = availablePresets.find(p => p.name === presetName);
      setSuccessMessage(`Switched to "${preset?.description || presetName}" preset`);
    } catch (err) {
      console.error('Error saving preset:', err);
      setError(err instanceof Error ? err.message : 'Failed to save preset');
    } finally {
      setPresetSaving(false);
    }
  };

  const getCreativityLabel = (temp: string) => {
    const preset = CREATIVITY_PRESETS.find(p => p.value === temp);
    return preset?.label || 'Custom';
  };

  const currentAgentConfig = AGENT_CONFIG.find(a => a.id === activeAgent);
  const AgentIcon = currentAgentConfig?.icon || FileText;

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-[95vw] w-[95vw] h-[90vh] max-h-[90vh] flex flex-col p-0">
        <DialogHeader className="p-6 pb-0 shrink-0">
          <DialogTitle className="text-2xl font-bold flex items-center gap-2">
            <Settings className="w-6 h-6 text-pink-500" />
            PAM Analysis Settings
            <Badge variant="outline" className="ml-2 text-pink-600 border-pink-200">v2.0</Badge>
          </DialogTitle>
          <DialogDescription>
            Configure analysis parameters, edit agent prompts, and manage external data sources
          </DialogDescription>
        </DialogHeader>

        <Tabs value={activeTab} onValueChange={setActiveTab} className="flex-1 flex flex-col min-h-0">
          <TabsList className="mx-6 mt-4 grid grid-cols-4 w-auto">
            <TabsTrigger value="settings" className="flex items-center gap-2">
              <Sliders className="w-4 h-4" />
              Settings
            </TabsTrigger>
            <TabsTrigger value="prompts" className="flex items-center gap-2">
              <FileText className="w-4 h-4" />
              Agent Prompts
              {hasAnyPromptChanges() && <span className="w-2 h-2 rounded-full bg-orange-500" />}
            </TabsTrigger>
            <TabsTrigger value="entities" className="flex items-center gap-2">
              <Users className="w-4 h-4" />
              Entities
              {entities.length > 0 && (
                <span className="px-1.5 py-0.5 text-xs rounded-full bg-pink-100 text-pink-700">{entities.length}</span>
              )}
            </TabsTrigger>
            <TabsTrigger value="external" className="flex items-center gap-2">
              <Globe className="w-4 h-4" />
              External Data
            </TabsTrigger>
          </TabsList>

          {/* Scrollable content */}
          <div className="flex-1 overflow-y-auto px-6 py-4 min-h-0">
            {error && (
              <Alert variant="destructive" className="mb-4">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
            {successMessage && (
              <Alert className="mb-4 bg-green-50 border-green-200">
                <AlertDescription className="text-green-700">{successMessage}</AlertDescription>
              </Alert>
            )}

            {/* SETTINGS TAB */}
            <TabsContent value="settings" className="space-y-6 mt-0">
              {/* Analysis Type Row */}
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label className="flex items-center gap-2">
                    <Target className="w-4 h-4 text-gray-500" />
                    Analysis Type
                  </Label>
                  <Select value={analysisType} onValueChange={onAnalysisTypeChange}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="comprehensive">
                        <div className="flex items-center gap-2">
                          <span>Comprehensive</span>
                          <span className="text-xs text-gray-500">All dimensions</span>
                        </div>
                      </SelectItem>
                      <SelectItem value="power">
                        <div className="flex items-center gap-2">
                          <Zap className="w-4 h-4 text-yellow-500" />
                          <span>Power Focus</span>
                        </div>
                      </SelectItem>
                      <SelectItem value="attention">
                        <div className="flex items-center gap-2">
                          <Eye className="w-4 h-4 text-blue-500" />
                          <span>Attention Focus</span>
                        </div>
                      </SelectItem>
                      <SelectItem value="money">
                        <div className="flex items-center gap-2">
                          <DollarSign className="w-4 h-4 text-green-500" />
                          <span>Money Focus</span>
                        </div>
                      </SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-2">
                  <Label className="flex items-center gap-2">
                    <Clock className="w-4 h-4 text-gray-500" />
                    Outlook Horizon
                  </Label>
                  <Select value={timeHorizon} onValueChange={onTimeHorizonChange}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="current">Current State</SelectItem>
                      <SelectItem value="6_months">6 Months</SelectItem>
                      <SelectItem value="1_year">1 Year</SelectItem>
                      <SelectItem value="5_years">5 Years</SelectItem>
                      <SelectItem value="2030">2030 Horizon</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>

              {/* Data Range and Article Limit */}
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>Data Range (Days Back)</Label>
                  <Select value={daysBack.toString()} onValueChange={(v) => onDaysBackChange(parseInt(v))}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="30">Last 30 days</SelectItem>
                      <SelectItem value="60">Last 60 days</SelectItem>
                      <SelectItem value="90">Last 90 days</SelectItem>
                      <SelectItem value="180">Last 180 days</SelectItem>
                      <SelectItem value="365">Last year</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-2">
                  <Label>Article Limit</Label>
                  <Select value={articleLimit.toString()} onValueChange={(v) => onArticleLimitChange(parseInt(v))}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="50">50 articles</SelectItem>
                      <SelectItem value="100">100 articles</SelectItem>
                      <SelectItem value="200">200 articles</SelectItem>
                      <SelectItem value="500">500 articles</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>

              {/* v2.0 Options */}
              <div className="space-y-4 p-4 bg-pink-50 rounded-lg border border-pink-200">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Cpu className="w-4 h-4 text-pink-500" />
                    <Label className="text-pink-700 font-medium">v2.0 Agent Settings</Label>
                  </div>
                  <div className="flex items-center gap-4">
                    {onParallelAgentsChange && (
                      <label className="flex items-center gap-2 cursor-pointer">
                        <Switch
                          checked={parallelAgents}
                          onCheckedChange={onParallelAgentsChange}
                        />
                        <span className="text-sm">Parallel Agents</span>
                      </label>
                    )}
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  {onRelevanceThresholdChange && (
                    <div className="space-y-2">
                      <Label className="text-sm flex items-center gap-1">
                        <Sliders className="w-3 h-3" />
                        Relevance Threshold
                        <span className="text-gray-400 font-normal">(lower = stricter)</span>
                      </Label>
                      <div className="flex items-center gap-2">
                        <input
                          type="range"
                          min="0.3"
                          max="0.9"
                          step="0.05"
                          value={relevanceThreshold}
                          onChange={(e) => onRelevanceThresholdChange(parseFloat(e.target.value))}
                          className="flex-1 accent-pink-500"
                        />
                        <span className="text-sm font-mono w-12 text-right">{relevanceThreshold.toFixed(2)}</span>
                      </div>
                    </div>
                  )}

                  {onArticlesPerTopicChange && (
                    <div className="space-y-2">
                      <Label className="text-sm">Articles per Topic</Label>
                      <Select value={articlesPerTopic.toString()} onValueChange={(v) => onArticlesPerTopicChange(parseInt(v))}>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="10">10 articles</SelectItem>
                          <SelectItem value="15">15 articles</SelectItem>
                          <SelectItem value="20">20 articles</SelectItem>
                          <SelectItem value="30">30 articles</SelectItem>
                          <SelectItem value="50">50 articles</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  )}
                </div>
              </div>

              {/* Trend Focus */}
              <div className="space-y-3">
                <Label className="flex items-center gap-2">
                  <Target className="w-4 h-4 text-gray-500" />
                  2030 Trend Focus
                </Label>
                <div className="bg-gray-50 rounded-lg p-4 space-y-3">
                  {TREND_OPTIONS.map((trend) => (
                    <label key={trend.id} className="flex items-start gap-3 cursor-pointer">
                      <Checkbox
                        checked={trendFocus.includes(trend.id)}
                        onCheckedChange={() => handleTrendToggle(trend.id)}
                        className="mt-0.5"
                      />
                      <div className="flex-1">
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-semibold text-pink-600 bg-pink-100 px-1.5 py-0.5 rounded">
                            {trend.id}
                          </span>
                          <span className="font-medium text-gray-900">{trend.name}</span>
                        </div>
                        <p className="text-sm text-gray-500">{trend.description}</p>
                      </div>
                    </label>
                  ))}
                </div>
              </div>
            </TabsContent>

            {/* PROMPTS TAB */}
            <TabsContent value="prompts" className="mt-0">
              {loading ? (
                <div className="flex items-center justify-center py-12">
                  <Loader2 className="w-8 h-8 animate-spin text-pink-500" />
                  <span className="ml-2 text-gray-600">Loading prompts...</span>
                </div>
              ) : (
                <div className="space-y-4">
                  {/* Agent selector */}
                  <div className="flex flex-wrap gap-2">
                    {AGENT_CONFIG.map((agent) => {
                      const Icon = agent.icon;
                      const hasChanges = hasAgentChanges(agent.id);
                      return (
                        <button
                          key={agent.id}
                          onClick={() => setActiveAgent(agent.id)}
                          className={`flex items-center gap-2 px-3 py-2 rounded-lg border transition-all ${
                            activeAgent === agent.id
                              ? 'bg-pink-50 border-pink-300 text-pink-700'
                              : 'bg-white border-gray-200 hover:border-gray-300'
                          }`}
                        >
                          <Icon className={`w-4 h-4 ${agent.color}`} />
                          <span className="text-sm font-medium">{agent.name}</span>
                          {hasChanges && <span className="w-2 h-2 rounded-full bg-orange-500" />}
                        </button>
                      );
                    })}
                  </div>

                  {/* Agent prompt editor */}
                  <div className="border rounded-lg p-4 space-y-4">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <AgentIcon className={`w-5 h-5 ${currentAgentConfig?.color}`} />
                        <h3 className="font-semibold">{currentAgentConfig?.name}</h3>
                        {hasAgentChanges(activeAgent) && (
                          <Badge className="bg-orange-100 text-orange-700">Modified</Badge>
                        )}
                      </div>
                      <p className="text-sm text-gray-500">{currentAgentConfig?.description}</p>
                    </div>

                    {/* Model and Temperature */}
                    <div className="grid grid-cols-2 gap-4">
                      <div className="space-y-2">
                        <Label className="text-sm">Model</Label>
                        <Select
                          value={editedModels[activeAgent] || ''}
                          onValueChange={(v) => setEditedModels(prev => ({ ...prev, [activeAgent]: v }))}
                        >
                          <SelectTrigger>
                            <SelectValue placeholder="Default" />
                          </SelectTrigger>
                          <SelectContent>
                            {MODEL_OPTIONS.map(opt => (
                              <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                      <div className="space-y-2">
                        <Label className="text-sm">
                          Response Style: {getCreativityLabel(editedTemps[activeAgent] || '0.3')}
                        </Label>
                        <Select
                          value={editedTemps[activeAgent] || '0.3'}
                          onValueChange={(v) => setEditedTemps(prev => ({ ...prev, [activeAgent]: v }))}
                        >
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {CREATIVITY_PRESETS.map(preset => (
                              <SelectItem key={preset.value} value={preset.value}>
                                <div className="flex items-center gap-2">
                                  <span className={`px-2 py-0.5 rounded text-xs ${preset.color}`}>{preset.label}</span>
                                  <span className="text-xs text-gray-500">{preset.description}</span>
                                </div>
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                    </div>

                    {/* Prompt content */}
                    <div className="space-y-2">
                      <Label className="text-sm">Prompt Instructions</Label>
                      <Textarea
                        value={editedContent[activeAgent] || ''}
                        onChange={(e) => setEditedContent(prev => ({ ...prev, [activeAgent]: e.target.value }))}
                        placeholder="Loading prompt..."
                        className="min-h-[400px] font-mono text-sm"
                      />
                    </div>
                  </div>

                  {/* Save/Reset buttons */}
                  <div className="flex items-center justify-between pt-4 border-t">
                    <Button variant="outline" onClick={resetPromptChanges} disabled={!hasAnyPromptChanges()}>
                      <RotateCcw className="w-4 h-4 mr-2" />
                      Reset All Changes
                    </Button>
                    <Button
                      onClick={savePromptChanges}
                      disabled={saving || !hasAnyPromptChanges()}
                      className="bg-pink-500 hover:bg-pink-600"
                    >
                      {saving ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Save className="w-4 h-4 mr-2" />}
                      Save Prompt Changes
                    </Button>
                  </div>
                </div>
              )}
            </TabsContent>

            {/* ENTITIES TAB */}
            <TabsContent value="entities" className="mt-0 space-y-6">
              {/* Domain Preset Selector */}
              <div className="bg-gradient-to-r from-purple-50 to-pink-50 border border-purple-200 rounded-lg p-4">
                <h3 className="font-semibold text-purple-900 mb-2 flex items-center gap-2">
                  <Sliders className="w-5 h-5" />
                  Domain Preset
                </h3>
                <p className="text-sm text-purple-700 mb-4">
                  Select a keyword preset to configure deep search for cost dynamics, M&A activity, regulatory events, and entity variations.
                </p>

                <div className="grid grid-cols-2 gap-3">
                  {availablePresets.map((preset) => {
                    const isSelected = currentPreset === preset.name;
                    const totalKeywords = preset.keywords_count.cost_dynamics +
                      preset.keywords_count.ma_activity +
                      preset.keywords_count.regulatory;

                    return (
                      <button
                        key={preset.name}
                        onClick={() => !isSelected && savePreset(preset.name)}
                        disabled={presetSaving}
                        className={`relative p-4 rounded-lg border-2 text-left transition-all ${
                          isSelected
                            ? 'border-purple-500 bg-white shadow-md'
                            : 'border-gray-200 bg-white hover:border-purple-300 hover:shadow-sm'
                        }`}
                      >
                        {isSelected && (
                          <div className="absolute top-2 right-2">
                            <Badge className="bg-purple-100 text-purple-700 text-xs">Active</Badge>
                          </div>
                        )}
                        <h4 className="font-medium text-gray-900 capitalize mb-1">
                          {preset.name.replace(/_/g, ' ')}
                        </h4>
                        <p className="text-xs text-gray-500 mb-2 line-clamp-2">
                          {preset.description}
                        </p>
                        <div className="flex flex-wrap gap-1.5 text-xs">
                          <span className="px-2 py-0.5 bg-green-100 text-green-700 rounded">
                            {totalKeywords} keywords
                          </span>
                          {preset.entities.length > 0 && (
                            <span className="px-2 py-0.5 bg-blue-100 text-blue-700 rounded">
                              {preset.entities.length} entities
                            </span>
                          )}
                        </div>
                        {preset.entities.length > 0 && (
                          <p className="text-xs text-gray-400 mt-2 truncate">
                            {preset.entities.slice(0, 3).join(', ')}
                            {preset.entities.length > 3 && ` +${preset.entities.length - 3} more`}
                          </p>
                        )}
                      </button>
                    );
                  })}
                </div>

                {presetSaving && (
                  <div className="mt-3 flex items-center gap-2 text-sm text-purple-600">
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Switching preset...
                  </div>
                )}
              </div>

              <div className="bg-pink-50 border border-pink-200 rounded-lg p-4">
                <h3 className="font-semibold text-pink-900 mb-2 flex items-center gap-2">
                  <Users className="w-5 h-5" />
                  Monitored Entities
                </h3>
                <p className="text-sm text-pink-700 mb-4">
                  Track specific brands, companies, or organizations. PAM analysis will monitor their visibility, mentions, and influence across articles.
                </p>

                {/* Add new entity form */}
                <div className="flex gap-3 mb-6 p-4 bg-white rounded-lg border">
                  <div className="flex-1">
                    <Label className="text-sm mb-1.5 block">Entity Name</Label>
                    <Input
                      placeholder="e.g., OpenAI, Microsoft, EU Commission"
                      value={newEntityName}
                      onChange={(e) => setNewEntityName(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && addEntity()}
                    />
                  </div>
                  <div className="w-48">
                    <Label className="text-sm mb-1.5 block">Type</Label>
                    <Select value={newEntityType} onValueChange={setNewEntityType}>
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {ENTITY_TYPES.map(type => (
                          <SelectItem key={type.value} value={type.value}>
                            {type.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="flex items-end">
                    <Button
                      onClick={addEntity}
                      disabled={!newEntityName.trim() || entitySaving}
                      className="bg-pink-500 hover:bg-pink-600"
                    >
                      {entitySaving ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        <Plus className="w-4 h-4" />
                      )}
                    </Button>
                  </div>
                </div>

                {/* Entity list */}
                <div className="space-y-2">
                  {entities.length === 0 ? (
                    <div className="text-center py-8 text-gray-500">
                      <Users className="w-12 h-12 mx-auto mb-3 opacity-30" />
                      <p>No entities being monitored</p>
                      <p className="text-sm">Add brands or organizations above to track their visibility</p>
                    </div>
                  ) : (
                    entities.map((entity) => {
                      const typeConfig = ENTITY_TYPES.find(t => t.value === entity.entity_type);
                      return (
                        <div
                          key={entity.id}
                          className="flex items-center justify-between p-3 bg-white rounded-lg border hover:border-pink-200 transition-colors"
                        >
                          <div className="flex items-center gap-3">
                            <div className="w-8 h-8 rounded-full bg-pink-100 flex items-center justify-center">
                              <Tag className="w-4 h-4 text-pink-500" />
                            </div>
                            <div>
                              <h4 className="font-medium">{entity.entity_name}</h4>
                              <p className="text-xs text-gray-500">
                                {typeConfig?.label || entity.entity_type}
                                {entity.entity_subtype && ` • ${entity.entity_subtype}`}
                              </p>
                            </div>
                          </div>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => deleteEntity(entity.id, entity.entity_name)}
                            disabled={entitySaving}
                            className="text-gray-400 hover:text-red-500 hover:bg-red-50"
                          >
                            <Trash2 className="w-4 h-4" />
                          </Button>
                        </div>
                      );
                    })
                  )}
                </div>
              </div>

              {/* Info about entity tracking */}
              <div className="grid grid-cols-2 gap-4">
                <div className="p-4 bg-gray-50 rounded-lg border">
                  <h4 className="font-medium text-gray-900 flex items-center gap-2">
                    <Eye className="w-4 h-4 text-blue-500" />
                    Visibility Tracking
                  </h4>
                  <ul className="mt-2 text-sm text-gray-600 space-y-1">
                    <li>• Article mention frequency</li>
                    <li>• AI citation monitoring</li>
                    <li>• Sentiment analysis</li>
                    <li>• Share of voice metrics</li>
                  </ul>
                </div>

                <div className="p-4 bg-gray-50 rounded-lg border">
                  <h4 className="font-medium text-gray-900 flex items-center gap-2">
                    <TrendingUp className="w-4 h-4 text-green-500" />
                    Influence Analysis
                  </h4>
                  <ul className="mt-2 text-sm text-gray-600 space-y-1">
                    <li>• Market position tracking</li>
                    <li>• Competitive comparison</li>
                    <li>• Partnership mentions</li>
                    <li>• Strategic move detection</li>
                  </ul>
                </div>
              </div>
            </TabsContent>

            {/* EXTERNAL DATA TAB */}
            <TabsContent value="external" className="mt-0 space-y-6">
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                <h3 className="font-semibold text-blue-900 mb-2 flex items-center gap-2">
                  <Globe className="w-5 h-5" />
                  External Data Sources
                </h3>
                <p className="text-sm text-blue-700 mb-4">
                  Enable or disable external data providers for PAM analysis. These supplement article-based analysis with real-time data.
                </p>

                <div className="space-y-4">
                  {/* Semantic Scholar */}
                  <div className="flex items-center justify-between p-3 bg-white rounded-lg border">
                    <div className="flex items-center gap-3">
                      <GraduationCap className="w-6 h-6 text-purple-500" />
                      <div>
                        <h4 className="font-medium">Semantic Scholar</h4>
                        <p className="text-sm text-gray-500">Academic citations, paper metrics, research impact</p>
                        <p className="text-xs text-gray-400">Used by: Attention Agent</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      {providerStatus?.semantic_scholar.available ? (
                        <Badge className="bg-green-100 text-green-700">Available</Badge>
                      ) : (
                        <Badge className="bg-gray-100 text-gray-500">Not Configured</Badge>
                      )}
                      <Switch
                        checked={semanticScholarEnabled}
                        onCheckedChange={setSemanticScholarEnabled}
                        disabled={!providerStatus?.semantic_scholar.available}
                        className="data-[state=unchecked]:bg-gray-300 data-[state=checked]:bg-purple-500"
                      />
                    </div>
                  </div>

                  {/* Google Search */}
                  <div className="flex items-center justify-between p-3 bg-white rounded-lg border">
                    <div className="flex items-center gap-3">
                      <Search className="w-6 h-6 text-blue-500" />
                      <div>
                        <h4 className="font-medium">Google Search</h4>
                        <p className="text-sm text-gray-500">Funding announcements, M&A news, regulatory updates</p>
                        <p className="text-xs text-gray-400">Used by: Power Agent, Money Agent</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      {providerStatus?.google_search.available ? (
                        <Badge className="bg-green-100 text-green-700">Available</Badge>
                      ) : (
                        <Badge className="bg-gray-100 text-gray-500">
                          {providerStatus?.google_search.reason || 'Not Configured'}
                        </Badge>
                      )}
                      <Switch
                        checked={googleSearchEnabled}
                        onCheckedChange={setGoogleSearchEnabled}
                        disabled={!providerStatus?.google_search.available}
                        className="data-[state=unchecked]:bg-gray-300 data-[state=checked]:bg-blue-500"
                      />
                    </div>
                  </div>
                </div>

                <div className="mt-4 flex justify-end">
                  <Button
                    onClick={saveExternalDataConfig}
                    disabled={saving}
                    className="bg-blue-500 hover:bg-blue-600"
                  >
                    {saving ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Save className="w-4 h-4 mr-2" />}
                    Save External Data Settings
                  </Button>
                </div>
              </div>

              {/* Info about what each provider does */}
              <div className="grid grid-cols-2 gap-4">
                <div className="p-4 bg-purple-50 rounded-lg border border-purple-200">
                  <h4 className="font-medium text-purple-900 flex items-center gap-2">
                    <GraduationCap className="w-4 h-4" />
                    Semantic Scholar Data
                  </h4>
                  <ul className="mt-2 text-sm text-purple-700 space-y-1">
                    <li>• Citation counts and velocity</li>
                    <li>• Influential citations tracking</li>
                    <li>• Academic visibility metrics</li>
                    <li>• Research impact scoring</li>
                  </ul>
                </div>

                <div className="p-4 bg-blue-50 rounded-lg border border-blue-200">
                  <h4 className="font-medium text-blue-900 flex items-center gap-2">
                    <Search className="w-4 h-4" />
                    Google Search Data
                  </h4>
                  <ul className="mt-2 text-sm text-blue-700 space-y-1">
                    <li>• Real-time funding announcements</li>
                    <li>• M&A deal tracking</li>
                    <li>• Regulatory news updates</li>
                    <li>• Market trend signals</li>
                  </ul>
                </div>
              </div>
            </TabsContent>

          </div>
        </Tabs>

        <DialogFooter className="p-6 pt-4 border-t shrink-0">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Close
          </Button>
          <Button onClick={() => onOpenChange(false)} className="bg-pink-500 hover:bg-pink-600">
            Apply Settings
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default PAMTuneModal;
