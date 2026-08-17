/**
 * SIO Tune Modal - Multi-step prompt editor for Strategic Intelligence Oracle
 *
 * Allows editing of 4 agent prompts:
 * 1. Discovery - search query generation
 * 2. Triage - event clustering and credibility filtering
 * 3. Deep Analysis - comprehensive event analysis
 * 4. Synthesis - final brief generation
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
import { Loader2, Save, RotateCcw, Search, Filter, Zap, FileText, Settings2 } from 'lucide-react';
import { Alert, AlertDescription } from './ui/alert';

interface SIOAgent {
  id: string;
  name: string;
  description: string;
  content: string;
  metadata: Record<string, any>;
}

interface AvailableModel {
  /** The id stored in config — must be a real litellm alias. */
  name: string;
  /** Human-readable label for the dropdown. */
  label?: string;
  provider?: string;
}

interface SIOConfig {
  credibility_threshold: number;
  hours_back: number;
  max_events: number;
}

interface SIOTuneModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  // Global config values from parent
  credibilityThreshold: number;
  hoursBack: number;
  maxEvents: number;
  // Callbacks to update parent state
  onCredibilityThresholdChange: (value: number) => void;
  onHoursBackChange: (value: number) => void;
  onMaxEventsChange: (value: number) => void;
}

const AGENT_ICONS: Record<string, React.ReactNode> = {
  sio_discovery_agent: <Search className="w-4 h-4" />,
  sio_triage_agent: <Filter className="w-4 h-4" />,
  sio_deep_analysis_agent: <Zap className="w-4 h-4" />,
  sio_synthesis_agent: <FileText className="w-4 h-4" />
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
    description: 'Higher variety and creativity. May be less consistent.',
    color: 'bg-orange-100 text-orange-800'
  }
];

// Default models for each agent type
const DEFAULT_MODELS: Record<string, string> = {
  sio_discovery_agent: 'gpt-5.4-mini',
  sio_triage_agent: 'gpt-5.4-mini',
  sio_deep_analysis_agent: 'gpt-5.4',
  sio_synthesis_agent: 'gpt-5.4'
};

// Default temperatures for each agent type
const DEFAULT_TEMPS: Record<string, string> = {
  sio_discovery_agent: '0.3',
  sio_triage_agent: '0.1',
  sio_deep_analysis_agent: '0.3',
  sio_synthesis_agent: '0.5'
};

export function SIOTuneModal({
  open,
  onOpenChange,
  credibilityThreshold,
  hoursBack,
  maxEvents,
  onCredibilityThresholdChange,
  onHoursBackChange,
  onMaxEventsChange
}: SIOTuneModalProps) {
  const [agents, setAgents] = useState<SIOAgent[]>([]);
  const [availableModels, setAvailableModels] = useState<AvailableModel[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Edited values (local state)
  const [editedContent, setEditedContent] = useState<Record<string, string>>({});
  const [editedModels, setEditedModels] = useState<Record<string, string>>({});
  const [editedTemps, setEditedTemps] = useState<Record<string, string>>({});

  // Global config edited values
  const [editedCredibility, setEditedCredibility] = useState(credibilityThreshold);
  const [editedHoursBack, setEditedHoursBack] = useState(hoursBack);
  const [editedMaxEvents, setEditedMaxEvents] = useState(maxEvents);

  // Original values (for comparison)
  const [originalConfig, setOriginalConfig] = useState<SIOConfig | null>(null);

  const [activeAgent, setActiveAgent] = useState('sio_discovery_agent');

  // Fetch agent prompts, config, and available models when modal opens
  useEffect(() => {
    if (!open) return;

    const fetchData = async () => {
      setLoading(true);
      setError(null);
      setSuccessMessage(null);

      try {
        // Fetch prompts, config, and models in parallel
        const [promptsRes, configRes, modelsRes] = await Promise.all([
          fetch('/api/sio/prompts', { credentials: 'include' }),
          fetch('/api/sio/config', { credentials: 'include' }),
          fetch('/api/trend-convergence/models', { credentials: 'include' })
        ]);

        if (!promptsRes.ok) {
          throw new Error(`Failed to fetch prompts: ${promptsRes.status}`);
        }

        const promptsData = await promptsRes.json();
        setAgents(promptsData.prompts || []);

        // Initialize edited content, models, and temps
        const initialContent: Record<string, string> = {};
        const initialModels: Record<string, string> = {};
        const initialTemps: Record<string, string> = {};

        for (const agent of promptsData.prompts || []) {
          initialContent[agent.id] = agent.content;
          initialModels[agent.id] = agent.metadata?.model_config?.model || DEFAULT_MODELS[agent.id] || 'gpt-5.4';
          const temp = agent.metadata?.model_config?.temperature;
          initialTemps[agent.id] = temp !== undefined ? String(temp) : (DEFAULT_TEMPS[agent.id] || '0.3');
        }
        setEditedContent(initialContent);
        setEditedModels(initialModels);
        setEditedTemps(initialTemps);

        // Load global config
        if (configRes.ok) {
          const configData = await configRes.json();
          setOriginalConfig(configData);
          setEditedCredibility(configData.credibility_threshold ?? 60);
          setEditedHoursBack(configData.hours_back ?? 24);
          setEditedMaxEvents(configData.max_events ?? 30);
          // Update parent state with saved values
          onCredibilityThresholdChange(configData.credibility_threshold ?? 60);
          onHoursBackChange(configData.hours_back ?? 24);
          onMaxEventsChange(configData.max_events ?? 30);
        }

        // Parse available models
        if (modelsRes.ok) {
          // {id, name} — store the id as the value, the name as the label.
          const modelsData = await modelsRes.json();
          setAvailableModels((modelsData || []).map(
            (m: {id: string; name: string; provider?: string}) =>
              ({ name: m.id, label: m.name, provider: m.provider })));
        }
      } catch (err) {
        console.error('Error fetching SIO data:', err);
        setError(err instanceof Error ? err.message : 'Failed to load data');
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [open]);

  // Save all changes (config + current agent)
  const saveAll = async () => {
    setSaving(true);
    setError(null);
    setSuccessMessage(null);

    try {
      const savePromises: Promise<Response>[] = [];

      // Save global config if changed
      if (hasConfigChanges()) {
        savePromises.push(
          fetch('/api/sio/config', {
            method: 'PUT',
            credentials: 'include',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              credibility_threshold: editedCredibility,
              hours_back: editedHoursBack,
              max_events: editedMaxEvents
            })
          })
        );
      }

      // Save any agents with changes
      for (const agent of agents) {
        if (hasAgentChanges(agent.id)) {
          savePromises.push(
            fetch(`/api/sio/prompts/${agent.id}`, {
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
        credibility_threshold: editedCredibility,
        hours_back: editedHoursBack,
        max_events: editedMaxEvents
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
      onCredibilityThresholdChange(editedCredibility);
      onHoursBackChange(editedHoursBack);
      onMaxEventsChange(editedMaxEvents);

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
    // Reset global config
    if (originalConfig) {
      setEditedCredibility(originalConfig.credibility_threshold);
      setEditedHoursBack(originalConfig.hours_back);
      setEditedMaxEvents(originalConfig.max_events);
    }

    // Reset agent values
    const resetContent: Record<string, string> = {};
    const resetModels: Record<string, string> = {};
    const resetTemps: Record<string, string> = {};

    for (const agent of agents) {
      resetContent[agent.id] = agent.content;
      resetModels[agent.id] = agent.metadata?.model_config?.model || DEFAULT_MODELS[agent.id] || 'gpt-5.4';
      const temp = agent.metadata?.model_config?.temperature;
      resetTemps[agent.id] = temp !== undefined ? String(temp) : (DEFAULT_TEMPS[agent.id] || '0.3');
    }

    setEditedContent(resetContent);
    setEditedModels(resetModels);
    setEditedTemps(resetTemps);
    setSuccessMessage(null);
  };

  // Check if global config has changed
  const hasConfigChanges = () => {
    if (!originalConfig) return false;
    return editedCredibility !== originalConfig.credibility_threshold ||
           editedHoursBack !== originalConfig.hours_back ||
           editedMaxEvents !== originalConfig.max_events;
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

  const activeAgentData = agents.find(a => a.id === activeAgent);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-[95vw] w-[95vw] h-[95vh] max-h-[95vh] overflow-hidden flex flex-col overflow-x-hidden">
        <DialogHeader>
          <DialogTitle className="text-2xl font-bold">Tune: Situation Assessment</DialogTitle>
          <DialogDescription>
            Customize the multi-step SIO workflow - prompts, models, and behavior
          </DialogDescription>
        </DialogHeader>

        {/* Single scrollable content area - ALL content inside this div */}
        <div className="flex-1 overflow-y-auto overflow-x-hidden space-y-6 mt-4 pr-2">
          {/* Global Settings */}
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
            <div className="flex items-center justify-between mb-3">
              <label className="text-sm font-semibold text-blue-900">
                Scan Settings
              </label>
              {hasConfigChanges() && (
                <span className="text-xs text-orange-600 flex items-center gap-1">
                  <Settings2 className="w-3 h-3" />
                  Modified
                </span>
              )}
            </div>

            <div className="flex flex-wrap gap-6">
              {/* Lookback Period */}
              <div className="w-32">
                <label className="text-xs font-medium text-blue-800 block mb-1">
                  Lookback Period
                </label>
                <p className="text-xs text-blue-600 mb-2">Hours to search</p>
                <input
                  type="number"
                  value={editedHoursBack}
                  onChange={(e) => setEditedHoursBack(Math.max(1, Math.min(168, Number(e.target.value))))}
                  min={1}
                  max={168}
                  className="w-full px-3 py-2 border rounded-md text-sm"
                />
              </div>

              {/* Max Events */}
              <div className="w-32">
                <label className="text-xs font-medium text-blue-800 block mb-1">
                  Events to Analyze
                </label>
                <p className="text-xs text-blue-600 mb-2">Top N events</p>
                <input
                  type="number"
                  value={editedMaxEvents}
                  onChange={(e) => setEditedMaxEvents(Math.max(5, Math.min(100, Number(e.target.value))))}
                  min={5}
                  max={100}
                  className="w-full px-3 py-2 border rounded-md text-sm"
                />
              </div>

              {/* Credibility Threshold */}
              <div className="flex-1 min-w-[200px] max-w-[350px]">
                <label className="text-xs font-medium text-blue-800 block mb-1">
                  Source Credibility Filter
                </label>
                <p className="text-xs text-blue-600 mb-2">Minimum quality threshold</p>
                <div className="flex items-center gap-3">
                  <input
                    type="range"
                    min="0"
                    max="100"
                    step="10"
                    value={editedCredibility}
                    onChange={(e) => setEditedCredibility(Number(e.target.value))}
                    className="flex-1"
                  />
                  <span className={`text-xs font-medium px-2 py-1 rounded min-w-[50px] text-center ${
                    editedCredibility >= 80 ? 'bg-green-100 text-green-800' :
                    editedCredibility >= 60 ? 'bg-yellow-100 text-yellow-800' :
                    editedCredibility >= 40 ? 'bg-orange-100 text-orange-800' :
                    'bg-red-100 text-red-800'
                  }`}>
                    ≥{editedCredibility}%
                  </span>
                </div>
              </div>
            </div>

            <p className="text-xs text-blue-700 mt-3 italic">
              Note: This lookback period (hours) is for real-time intelligence scanning.
              The "Analysis Timeframe" in Configure Future Narratives (days) is for longer-term trend analysis.
            </p>
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
              <Loader2 className="w-8 h-8 animate-spin text-pink-500" />
              <span className="ml-2 text-gray-600">Loading configuration...</span>
            </div>
          ) : (
            <>
              {/* Agent Tabs - Simple button row */}
              <div>
                <label className="text-sm font-semibold mb-2 block text-gray-700">Select Agent Step</label>
                <div className="flex gap-2 flex-wrap">
                  {agents.map((agent) => (
                    <button
                      key={agent.id}
                      onClick={() => setActiveAgent(agent.id)}
                      className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                        activeAgent === agent.id
                          ? 'bg-pink-500 text-white'
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
                            {/* An already-saved model may no longer be offered; keep it listed
                                so the trigger is not blank. */}
                            {editedModels[activeAgent] && !availableModels.some(m => m.name === editedModels[activeAgent]) && (
                              <SelectItem value={editedModels[activeAgent]}>{editedModels[activeAgent]}</SelectItem>
                            )}
                            {availableModels.map((model) => (
                              <SelectItem key={model.name} value={model.name}>
                                {model.label || model.name}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>

                      {/* Creativity/Temperature Selection */}
                      <div>
                        <label className="text-xs font-medium text-gray-500 block mb-1">Response Style</label>
                        <Select
                          value={editedTemps[activeAgent] || '0.3'}
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

              {/* Save/Reset Buttons - INSIDE the scrollable area */}
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
                    className="px-4 py-2 bg-pink-500 text-white hover:bg-pink-600 rounded-md text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed"
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
