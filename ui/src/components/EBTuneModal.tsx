/**
 * EB Tune Modal - Multi-step prompt editor for Executive Briefing
 *
 * Allows editing of:
 * 1. Persona definitions (CEO/CMO/CTO/CISO + custom)
 * 2. Selection Agent - Scores and selects top articles
 * 3. Analysis Agent - Generates executive analysis per article
 * 4. Synthesis Agent - Creates briefing-level synthesis
 */

import { useState, useEffect } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle
} from './ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { Loader2, Save, RotateCcw, Filter, FileText, Layers, Settings2, Users, Plus, Trash2, Mic } from 'lucide-react';
import { Alert, AlertDescription } from './ui/alert';

interface EBAgent {
  id: string;
  name: string;
  description: string;
  content: string;
  metadata: Record<string, any>;
}

interface AvailableModel {
  name: string;
  provider?: string;
}

interface PersonaDefinition {
  name?: string;
  priorities: string | string[];
  risk_appetite: string;
  focus: string | string[];
}

// Helper to normalize string or array to array
function toArray(value: string | string[] | undefined): string[] {
  if (!value) return [];
  if (Array.isArray(value)) return value;
  // Split by comma or newline
  return value.split(/[,\n]/).map(s => s.trim()).filter(Boolean);
}

// Helper to get display string from string or array
function toDisplayString(value: string | string[] | undefined, limit?: number): string {
  const arr = toArray(value);
  if (limit && arr.length > limit) {
    return arr.slice(0, limit).join(', ') + '...';
  }
  return arr.join(', ');
}

// Helper to get persona display name
function getPersonaName(id: string, def: PersonaDefinition): string {
  if (def.name) return def.name;
  // Built-in personas use their ID as name
  return id.toUpperCase();
}

interface EBConfig {
  default_persona: string;
  default_article_count: number;
  personas: Record<string, PersonaDefinition>;
}

interface EBTuneModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  // Config values from parent
  persona: string;
  articleCount: number;
  // Callbacks to update parent state
  onPersonaChange: (value: string) => void;
  onArticleCountChange: (value: number) => void;
}

const AGENT_ICONS: Record<string, React.ReactNode> = {
  eb_selection_agent: <Filter className="w-4 h-4" />,
  eb_analysis_agent: <FileText className="w-4 h-4" />,
  eb_synthesis_agent: <Layers className="w-4 h-4" />,
  eb_podcast_agent: <Mic className="w-4 h-4" />
};

// User-friendly temperature presets
const CREATIVITY_PRESETS = [
  {
    value: '0.1',
    label: 'Precise',
    description: 'Highly focused and deterministic. Best for factual analysis.',
    color: 'bg-blue-100 text-blue-800'
  },
  {
    value: '0.3',
    label: 'Balanced',
    description: 'Mix of precision and variety. Good for most tasks.',
    color: 'bg-green-100 text-green-800'
  },
  {
    value: '0.5',
    label: 'Exploratory',
    description: 'More varied responses. Good for brainstorming.',
    color: 'bg-yellow-100 text-yellow-800'
  },
  {
    value: '0.7',
    label: 'Creative',
    description: 'Higher variety and creativity. Best for synthesis.',
    color: 'bg-orange-100 text-orange-800'
  }
];

// Default models for each agent type
const DEFAULT_MODELS: Record<string, string> = {
  eb_selection_agent: 'gpt-4o',
  eb_analysis_agent: 'gpt-4o',
  eb_synthesis_agent: 'gpt-4o',
  eb_podcast_agent: 'gpt-4o'
};

// Default temperatures for each agent type
const DEFAULT_TEMPS: Record<string, string> = {
  eb_selection_agent: '0.3',
  eb_analysis_agent: '0.5',
  eb_synthesis_agent: '0.5',
  eb_podcast_agent: '0.7'
};

// Risk appetite options
const RISK_APPETITES = ['low', 'moderate', 'high', 'aggressive'];

export function EBTuneModal({
  open,
  onOpenChange,
  persona,
  articleCount,
  onPersonaChange,
  onArticleCountChange
}: EBTuneModalProps) {
  const [agents, setAgents] = useState<EBAgent[]>([]);
  const [availableModels, setAvailableModels] = useState<AvailableModel[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Edited values (local state)
  const [editedContent, setEditedContent] = useState<Record<string, string>>({});
  const [editedModels, setEditedModels] = useState<Record<string, string>>({});
  const [editedTemps, setEditedTemps] = useState<Record<string, string>>({});

  // Config edited values
  const [editedPersona, setEditedPersona] = useState(persona);
  const [editedArticleCount, setEditedArticleCount] = useState(articleCount);
  const [editedPersonas, setEditedPersonas] = useState<Record<string, PersonaDefinition>>({});

  // Original values (for comparison)
  const [originalConfig, setOriginalConfig] = useState<EBConfig | null>(null);

  const [activeTab, setActiveTab] = useState<'personas' | 'agents'>('personas');
  const [activeAgent, setActiveAgent] = useState('eb_selection_agent');
  const [editingPersona, setEditingPersona] = useState<string | null>(null);

  // Fetch agent prompts, config, and available models when modal opens
  useEffect(() => {
    if (!open) return;

    const fetchData = async () => {
      setLoading(true);
      setError(null);
      setSuccessMessage(null);

      try {
        // Fetch prompts, config, and models in parallel
        const [configRes, modelsRes] = await Promise.all([
          fetch('/api/executive-briefing/config', { credentials: 'include' }),
          fetch('/api/available_models', { credentials: 'include' })
        ]);

        // Load config first
        if (configRes.ok) {
          const configData = await configRes.json();
          setOriginalConfig(configData);
          setEditedPersona(configData.default_persona ?? 'ceo');
          setEditedArticleCount(configData.default_article_count ?? 6);
          setEditedPersonas(configData.personas ?? {});
          // Update parent state with saved values
          onPersonaChange(configData.default_persona ?? 'ceo');
          onArticleCountChange(configData.default_article_count ?? 6);
        }

        // Fetch agent prompts for each agent
        const agentIds = ['eb_selection_agent', 'eb_analysis_agent', 'eb_synthesis_agent', 'eb_podcast_agent'];
        const promptsResults = await Promise.all(
          agentIds.map(id =>
            fetch(`/api/executive-briefing/prompts/${id}`, { credentials: 'include' })
              .then(res => res.ok ? res.json() : null)
          )
        );

        const loadedAgents: EBAgent[] = [];
        const initialContent: Record<string, string> = {};
        const initialModels: Record<string, string> = {};
        const initialTemps: Record<string, string> = {};

        promptsResults.forEach((data, index) => {
          if (data) {
            const agent = {
              id: agentIds[index],
              name: data.name || agentIds[index].replace('eb_', '').replace('_agent', ''),
              description: data.description || '',
              content: data.content || '',
              metadata: data.metadata || {}
            };
            loadedAgents.push(agent);
            initialContent[agent.id] = agent.content;
            initialModels[agent.id] = agent.metadata?.model_config?.model || DEFAULT_MODELS[agent.id] || 'gpt-4o';
            const temp = agent.metadata?.model_config?.temperature;
            initialTemps[agent.id] = temp !== undefined ? String(temp) : (DEFAULT_TEMPS[agent.id] || '0.5');
          }
        });

        setAgents(loadedAgents);
        setEditedContent(initialContent);
        setEditedModels(initialModels);
        setEditedTemps(initialTemps);

        // Parse available models
        if (modelsRes.ok) {
          const modelsData = await modelsRes.json();
          setAvailableModels(modelsData || []);
        }
      } catch (err) {
        console.error('Error fetching EB data:', err);
        setError(err instanceof Error ? err.message : 'Failed to load data');
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [open]);

  // Save all changes (config + agents)
  const saveAll = async () => {
    setSaving(true);
    setError(null);
    setSuccessMessage(null);

    try {
      const savePromises: Promise<Response>[] = [];

      // Save config if changed
      if (hasConfigChanges()) {
        savePromises.push(
          fetch('/api/executive-briefing/config', {
            method: 'PUT',
            credentials: 'include',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              default_persona: editedPersona,
              default_article_count: editedArticleCount,
              personas: editedPersonas
            })
          })
        );
      }

      // Save any agents with changes
      for (const agent of agents) {
        if (hasAgentChanges(agent.id)) {
          savePromises.push(
            fetch(`/api/executive-briefing/prompts/${agent.id}`, {
              method: 'PUT',
              credentials: 'include',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                content: editedContent[agent.id],
                model: editedModels[agent.id],
                temperature: parseFloat(editedTemps[agent.id])
              })
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

      // Check for errors
      const failed = results.filter(r => !r.ok);
      if (failed.length > 0) {
        throw new Error(`Failed to save ${failed.length} item(s)`);
      }

      // Update original values to match edited values
      setOriginalConfig({
        default_persona: editedPersona,
        default_article_count: editedArticleCount,
        personas: editedPersonas
      });

      // Update agents state with saved values
      setAgents(prev => prev.map(a => ({
        ...a,
        content: editedContent[a.id],
        metadata: {
          ...a.metadata,
          model_config: {
            ...a.metadata?.model_config,
            model: editedModels[a.id],
            temperature: parseFloat(editedTemps[a.id])
          }
        }
      })));

      // Update parent state
      onPersonaChange(editedPersona);
      onArticleCountChange(editedArticleCount);

      setSuccessMessage('All changes saved successfully');
    } catch (err) {
      console.error('Error saving:', err);
      setError(err instanceof Error ? err.message : 'Failed to save');
    } finally {
      setSaving(false);
    }
  };

  // Reset all changes
  const resetAll = () => {
    // Reset config
    if (originalConfig) {
      setEditedPersona(originalConfig.default_persona);
      setEditedArticleCount(originalConfig.default_article_count);
      setEditedPersonas(originalConfig.personas);
    }

    // Reset agent values
    const resetContent: Record<string, string> = {};
    const resetModels: Record<string, string> = {};
    const resetTemps: Record<string, string> = {};

    for (const agent of agents) {
      resetContent[agent.id] = agent.content;
      resetModels[agent.id] = agent.metadata?.model_config?.model || DEFAULT_MODELS[agent.id] || 'gpt-4o';
      const temp = agent.metadata?.model_config?.temperature;
      resetTemps[agent.id] = temp !== undefined ? String(temp) : (DEFAULT_TEMPS[agent.id] || '0.5');
    }

    setEditedContent(resetContent);
    setEditedModels(resetModels);
    setEditedTemps(resetTemps);
    setSuccessMessage(null);
  };

  // Check if config has changed
  const hasConfigChanges = () => {
    if (!originalConfig) return false;
    if (editedPersona !== originalConfig.default_persona) return true;
    if (editedArticleCount !== originalConfig.default_article_count) return true;
    // Deep compare personas
    const origPersonas = JSON.stringify(originalConfig.personas);
    const editedPersonasStr = JSON.stringify(editedPersonas);
    return origPersonas !== editedPersonasStr;
  };

  // Check if a specific agent has changes
  const hasAgentChanges = (agentId: string) => {
    const agent = agents.find(a => a.id === agentId);
    if (!agent) return false;

    const contentChanged = editedContent[agentId] !== agent.content;
    const savedModel = agent.metadata?.model_config?.model || DEFAULT_MODELS[agentId];
    const modelChanged = editedModels[agentId] !== savedModel;
    const origTemp = agent.metadata?.model_config?.temperature;
    const savedTemp = origTemp !== undefined ? String(origTemp) : DEFAULT_TEMPS[agentId];
    const tempChanged = editedTemps[agentId] !== savedTemp;

    return contentChanged || modelChanged || tempChanged;
  };

  // Check if ANY changes exist
  const hasAnyChanges = () => {
    if (hasConfigChanges()) return true;
    return agents.some(a => hasAgentChanges(a.id));
  };

  // Get current creativity preset label
  const getCreativityLabel = (temp: string) => {
    const preset = CREATIVITY_PRESETS.find(p => p.value === temp);
    return preset?.label || 'Custom';
  };

  // Add a new custom persona
  const addCustomPersona = () => {
    const customId = `custom_${Date.now()}`;
    setEditedPersonas(prev => ({
      ...prev,
      [customId]: {
        name: 'Custom Persona',
        priorities: ['Strategic relevance', 'Business impact'],
        risk_appetite: 'moderate',
        focus: ['Industry trends', 'Competitive landscape']
      }
    }));
    setEditingPersona(customId);
  };

  // Delete a persona (only custom ones)
  const deletePersona = (personaId: string) => {
    if (['ceo', 'cmo', 'cto', 'ciso'].includes(personaId)) return;
    setEditedPersonas(prev => {
      const updated = { ...prev };
      delete updated[personaId];
      return updated;
    });
    if (editingPersona === personaId) {
      setEditingPersona(null);
    }
  };

  // Update a persona field
  const updatePersonaField = (personaId: string, field: keyof PersonaDefinition, value: any) => {
    setEditedPersonas(prev => ({
      ...prev,
      [personaId]: {
        ...prev[personaId],
        [field]: value
      }
    }));
  };

  const activeAgentData = agents.find(a => a.id === activeAgent);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-[95vw] w-[95vw] h-[95vh] max-h-[95vh] overflow-hidden flex flex-col overflow-x-hidden">
        <DialogHeader>
          <DialogTitle className="text-2xl font-bold">Tune: Executive Briefing</DialogTitle>
          <DialogDescription>
            Customize personas and the 3-step briefing workflow - prompts, models, and settings
          </DialogDescription>
        </DialogHeader>

        {/* Tab Switcher */}
        <div className="flex gap-2 border-b pb-2">
          <button
            onClick={() => setActiveTab('personas')}
            className={`flex items-center gap-2 px-4 py-2 rounded-t-lg text-sm font-medium transition-colors ${
              activeTab === 'personas'
                ? 'bg-emerald-500 text-white'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            <Users className="w-4 h-4" />
            Personas
          </button>
          <button
            onClick={() => setActiveTab('agents')}
            className={`flex items-center gap-2 px-4 py-2 rounded-t-lg text-sm font-medium transition-colors ${
              activeTab === 'agents'
                ? 'bg-emerald-500 text-white'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            <Settings2 className="w-4 h-4" />
            Agent Prompts
          </button>
        </div>

        {/* Single scrollable content area */}
        <div className="flex-1 overflow-y-auto overflow-x-hidden space-y-6 mt-4 pr-2">
          {/* Generation Settings */}
          <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-4">
            <div className="flex items-center justify-between mb-3">
              <label className="text-sm font-semibold text-emerald-900">
                Default Settings
              </label>
              {hasConfigChanges() && (
                <span className="text-xs text-orange-600 flex items-center gap-1">
                  <Settings2 className="w-3 h-3" />
                  Modified
                </span>
              )}
            </div>

            <div className="flex flex-wrap gap-6">
              {/* Default Persona */}
              <div className="w-48">
                <label className="text-xs font-medium text-emerald-800 block mb-1">
                  Default Persona
                </label>
                <p className="text-xs text-emerald-600 mb-2">Analysis perspective</p>
                <Select
                  value={editedPersona}
                  onValueChange={setEditedPersona}
                >
                  <SelectTrigger className="w-full h-9">
                    <SelectValue placeholder="Select persona" />
                  </SelectTrigger>
                  <SelectContent>
                    {Object.entries(editedPersonas).map(([id, def]) => (
                      <SelectItem key={id} value={id}>
                        {getPersonaName(id, def)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* Default Article Count */}
              <div className="w-40">
                <label className="text-xs font-medium text-emerald-800 block mb-1">
                  Default Article Count
                </label>
                <p className="text-xs text-emerald-600 mb-2">Articles to select (1-8)</p>
                <input
                  type="number"
                  value={editedArticleCount}
                  onChange={(e) => setEditedArticleCount(Math.max(1, Math.min(8, Number(e.target.value))))}
                  min={1}
                  max={8}
                  className="w-full px-3 py-2 border rounded-md text-sm"
                />
              </div>
            </div>
          </div>

          {error && (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          {successMessage && (
            <Alert className="bg-green-50 border-green-200">
              <AlertDescription className="text-green-700">{successMessage}</AlertDescription>
            </Alert>
          )}

          {loading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-8 h-8 animate-spin text-emerald-500" />
              <span className="ml-2 text-gray-600">Loading configuration...</span>
            </div>
          ) : (
            <>
              {/* Personas Tab */}
              {activeTab === 'personas' && (
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <label className="text-sm font-semibold text-gray-700">Executive Personas</label>
                    <button
                      onClick={addCustomPersona}
                      className="flex items-center gap-2 px-3 py-1.5 bg-emerald-100 text-emerald-700 hover:bg-emerald-200 rounded-md text-sm font-medium"
                    >
                      <Plus className="w-4 h-4" />
                      Add Custom Persona
                    </button>
                  </div>

                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                    {Object.entries(editedPersonas).map(([personaId, personaDef]) => {
                      const isBuiltIn = ['ceo', 'cmo', 'cto', 'ciso'].includes(personaId);
                      const isExpanded = editingPersona === personaId;

                      return (
                        <div
                          key={personaId}
                          className={`border rounded-lg p-4 ${isExpanded ? 'ring-2 ring-emerald-500' : ''} ${
                            isBuiltIn ? 'bg-gray-50' : 'bg-white'
                          }`}
                        >
                          <div className="flex items-center justify-between mb-2">
                            <div className="flex items-center gap-2">
                              <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                                isBuiltIn ? 'bg-gray-200 text-gray-700' : 'bg-emerald-100 text-emerald-700'
                              }`}>
                                {isBuiltIn ? personaId.toUpperCase() : 'Custom'}
                              </span>
                              {isExpanded ? (
                                <input
                                  type="text"
                                  value={personaDef.name || personaId.toUpperCase()}
                                  onChange={(e) => updatePersonaField(personaId, 'name', e.target.value)}
                                  className="font-semibold text-gray-800 border-b border-emerald-500 bg-transparent focus:outline-none"
                                />
                              ) : (
                                <h4 className="font-semibold text-gray-800">{getPersonaName(personaId, personaDef)}</h4>
                              )}
                            </div>
                            <div className="flex gap-1">
                              <button
                                onClick={() => setEditingPersona(isExpanded ? null : personaId)}
                                className="p-1 hover:bg-gray-200 rounded"
                              >
                                <Settings2 className="w-4 h-4 text-gray-500" />
                              </button>
                              {!isBuiltIn && (
                                <button
                                  onClick={() => deletePersona(personaId)}
                                  className="p-1 hover:bg-red-100 rounded"
                                >
                                  <Trash2 className="w-4 h-4 text-red-500" />
                                </button>
                              )}
                            </div>
                          </div>

                          {isExpanded ? (
                            <div className="space-y-3 mt-3">
                              {/* Risk Appetite */}
                              <div>
                                <label className="text-xs font-medium text-gray-600 block mb-1">Risk Appetite</label>
                                <Select
                                  value={personaDef.risk_appetite}
                                  onValueChange={(value) => updatePersonaField(personaId, 'risk_appetite', value)}
                                >
                                  <SelectTrigger className="w-full h-8">
                                    <SelectValue />
                                  </SelectTrigger>
                                  <SelectContent>
                                    {RISK_APPETITES.map(ra => (
                                      <SelectItem key={ra} value={ra}>
                                        {ra.charAt(0).toUpperCase() + ra.slice(1)}
                                      </SelectItem>
                                    ))}
                                  </SelectContent>
                                </Select>
                              </div>

                              {/* Priorities */}
                              <div>
                                <label className="text-xs font-medium text-gray-600 block mb-1">
                                  Priorities (one per line)
                                </label>
                                <textarea
                                  value={toArray(personaDef.priorities).join('\n')}
                                  onChange={(e) => updatePersonaField(personaId, 'priorities', e.target.value.split('\n').filter(Boolean))}
                                  className="w-full h-20 px-2 py-1 border rounded text-sm"
                                  placeholder="Strategic growth&#10;Revenue impact&#10;..."
                                />
                              </div>

                              {/* Focus Areas */}
                              <div>
                                <label className="text-xs font-medium text-gray-600 block mb-1">
                                  Focus Areas (one per line)
                                </label>
                                <textarea
                                  value={toArray(personaDef.focus).join('\n')}
                                  onChange={(e) => updatePersonaField(personaId, 'focus', e.target.value.split('\n').filter(Boolean))}
                                  className="w-full h-20 px-2 py-1 border rounded text-sm"
                                  placeholder="Industry trends&#10;Competitive landscape&#10;..."
                                />
                              </div>
                            </div>
                          ) : (
                            <div className="text-sm text-gray-600 space-y-1">
                              <p><span className="font-medium">Risk:</span> {personaDef.risk_appetite}</p>
                              <p><span className="font-medium">Focus:</span> {toDisplayString(personaDef.focus, 2)}</p>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Agent Prompts Tab */}
              {activeTab === 'agents' && (
                <>
                  {/* Agent Tabs */}
                  <div>
                    <label className="text-sm font-semibold mb-2 block text-gray-700">Select Agent Step</label>
                    <div className="flex gap-2 flex-wrap">
                      {agents.map((agent) => (
                        <button
                          key={agent.id}
                          onClick={() => setActiveAgent(agent.id)}
                          className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                            activeAgent === agent.id
                              ? 'bg-emerald-500 text-white'
                              : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                          }`}
                        >
                          {AGENT_ICONS[agent.id]}
                          {agent.name}
                          {hasAgentChanges(agent.id) && (
                            <span className="w-2 h-2 rounded-full bg-orange-400" title="Unsaved changes" />
                          )}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Active Agent Settings */}
                  {activeAgentData && (
                    <>
                      {/* Agent Description & Model Settings */}
                      <div className="bg-gray-50 border rounded-lg p-4">
                        <div className="mb-3">
                          <h3 className="font-semibold text-gray-800">{activeAgentData.name} Agent</h3>
                          <p className="text-sm text-gray-600">{activeAgentData.description}</p>
                        </div>
                        <div className="flex items-center gap-6">
                          {/* Model Selection */}
                          <div>
                            <label className="text-xs font-medium text-gray-500 block mb-1">AI Model</label>
                            <Select
                              value={editedModels[activeAgent] || ''}
                              onValueChange={(value) => setEditedModels(prev => ({ ...prev, [activeAgent]: value }))}
                            >
                              <SelectTrigger className="w-48 h-9">
                                <SelectValue placeholder="Select model" />
                              </SelectTrigger>
                              <SelectContent>
                                {availableModels.map((model) => (
                                  <SelectItem key={model.name} value={model.name}>
                                    {model.name}
                                  </SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                          </div>

                          {/* Creativity/Temperature Selection */}
                          <div>
                            <label className="text-xs font-medium text-gray-500 block mb-1">Response Style</label>
                            <Select
                              value={editedTemps[activeAgent] || '0.5'}
                              onValueChange={(value) => setEditedTemps(prev => ({ ...prev, [activeAgent]: value }))}
                            >
                              <SelectTrigger className="w-40 h-9">
                                <SelectValue>
                                  {getCreativityLabel(editedTemps[activeAgent])}
                                </SelectValue>
                              </SelectTrigger>
                              <SelectContent>
                                {CREATIVITY_PRESETS.map((preset) => (
                                  <SelectItem key={preset.value} value={preset.value}>
                                    <div className="flex flex-col">
                                      <span className="font-medium">{preset.label}</span>
                                      <span className="text-gray-500 text-xs">{preset.description}</span>
                                    </div>
                                  </SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                          </div>
                        </div>
                      </div>

                      {/* Prompt Editor */}
                      <div>
                        <label className="text-sm font-semibold mb-2 block text-gray-700">Agent Instructions</label>
                        <p className="text-xs text-gray-500 mb-2">
                          The prompt that guides how this agent performs its task
                        </p>
                        <textarea
                          value={editedContent[activeAgent] || ''}
                          onChange={(e) => setEditedContent(prev => ({
                            ...prev,
                            [activeAgent]: e.target.value
                          }))}
                          className="w-full h-[400px] p-4 border rounded-lg font-mono text-xs leading-relaxed resize-y"
                          placeholder="Agent prompt content..."
                        />
                      </div>
                    </>
                  )}
                </>
              )}

              {/* Save/Reset Buttons */}
              <div className="flex items-center justify-between pt-4 border-t">
                <div className="text-sm text-gray-500">
                  {hasAnyChanges() ? (
                    <span className="text-orange-600 flex items-center gap-1">
                      <Settings2 className="w-4 h-4" />
                      Unsaved changes
                    </span>
                  ) : (
                    <span className="text-green-600">All settings saved</span>
                  )}
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={resetAll}
                    disabled={!hasAnyChanges()}
                    className="px-4 py-2 text-gray-700 hover:bg-gray-100 rounded-md text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    <RotateCcw className="w-4 h-4 inline mr-2" />
                    Reset All
                  </button>
                  <button
                    onClick={saveAll}
                    disabled={!hasAnyChanges() || saving}
                    className="px-4 py-2 bg-emerald-500 text-white hover:bg-emerald-600 rounded-md text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {saving ? (
                      <Loader2 className="w-4 h-4 inline mr-2 animate-spin" />
                    ) : (
                      <Save className="w-4 h-4 inline mr-2" />
                    )}
                    Save All
                  </button>
                  <button
                    onClick={() => onOpenChange(false)}
                    className="px-4 py-2 text-gray-700 hover:bg-gray-100 rounded-md text-sm font-medium"
                  >
                    Close
                  </button>
                </div>
              </div>
            </>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
