/**
 * EOS Tune Modal - Multi-step prompt editor for Extreme Outlier Scenarios
 *
 * Allows editing of 4 agent prompts:
 * 1. Weak Signals - detecting faint patterns and anomalies
 * 2. Amplification - modeling cascade effects
 * 3. Scenario Building - constructing outlier narratives
 * 4. Implications - strategic hedging recommendations
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
import { Loader2, Save, RotateCcw, Eye, TrendingDown, Zap, Lightbulb, Settings2 } from 'lucide-react';
import { Alert, AlertDescription } from './ui/alert';

interface EOSAgent {
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

interface EOSConfig {
  scenario_count: number;
  include_black_swans: boolean;
  include_contrarian: boolean;
  include_wild_cards: boolean;
  time_horizon: 'near' | 'mid' | 'long';
}

interface EOSTuneModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  // Config values from parent
  scenarioCount: number;
  includeBlackSwans: boolean;
  includeContrarian: boolean;
  includeWildCards: boolean;
  timeHorizon: 'near' | 'mid' | 'long';
  // Callbacks to update parent state
  onScenarioCountChange: (value: number) => void;
  onIncludeBlackSwansChange: (value: boolean) => void;
  onIncludeContrarianChange: (value: boolean) => void;
  onIncludeWildCardsChange: (value: boolean) => void;
  onTimeHorizonChange: (value: 'near' | 'mid' | 'long') => void;
}

const AGENT_ICONS: Record<string, React.ReactNode> = {
  eos_weak_signals_agent: <Eye className="w-4 h-4" />,
  eos_amplification_agent: <TrendingDown className="w-4 h-4" />,
  eos_scenario_building_agent: <Zap className="w-4 h-4" />,
  eos_implications_agent: <Lightbulb className="w-4 h-4" />
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
    description: 'Higher variety and creativity. Best for scenario building.',
    color: 'bg-orange-100 text-orange-800'
  }
];

// Default models for each agent type
const DEFAULT_MODELS: Record<string, string> = {
  eos_weak_signals_agent: 'gpt-5.4',
  eos_amplification_agent: 'gpt-5.4',
  eos_scenario_building_agent: 'gpt-5.4',
  eos_implications_agent: 'gpt-5.4'
};

// Default temperatures for each agent type
const DEFAULT_TEMPS: Record<string, string> = {
  eos_weak_signals_agent: '0.3',
  eos_amplification_agent: '0.5',
  eos_scenario_building_agent: '0.7',
  eos_implications_agent: '0.4'
};

export function EOSTuneModal({
  open,
  onOpenChange,
  scenarioCount,
  includeBlackSwans,
  includeContrarian,
  includeWildCards,
  timeHorizon,
  onScenarioCountChange,
  onIncludeBlackSwansChange,
  onIncludeContrarianChange,
  onIncludeWildCardsChange,
  onTimeHorizonChange
}: EOSTuneModalProps) {
  const [agents, setAgents] = useState<EOSAgent[]>([]);
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
  const [editedScenarioCount, setEditedScenarioCount] = useState(scenarioCount);
  const [editedIncludeBlackSwans, setEditedIncludeBlackSwans] = useState(includeBlackSwans);
  const [editedIncludeContrarian, setEditedIncludeContrarian] = useState(includeContrarian);
  const [editedIncludeWildCards, setEditedIncludeWildCards] = useState(includeWildCards);
  const [editedTimeHorizon, setEditedTimeHorizon] = useState(timeHorizon);

  // Original values (for comparison)
  const [originalConfig, setOriginalConfig] = useState<EOSConfig | null>(null);

  const [activeAgent, setActiveAgent] = useState('eos_weak_signals_agent');

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
          fetch('/api/eos/prompts', { credentials: 'include' }),
          fetch('/api/eos/config', { credentials: 'include' }),
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
          initialTemps[agent.id] = temp !== undefined ? String(temp) : (DEFAULT_TEMPS[agent.id] || '0.5');
        }
        setEditedContent(initialContent);
        setEditedModels(initialModels);
        setEditedTemps(initialTemps);

        // Load config
        if (configRes.ok) {
          const configData = await configRes.json();
          setOriginalConfig(configData);
          setEditedScenarioCount(configData.scenario_count ?? 5);
          setEditedIncludeBlackSwans(configData.include_black_swans ?? true);
          setEditedIncludeContrarian(configData.include_contrarian ?? true);
          setEditedIncludeWildCards(configData.include_wild_cards ?? true);
          setEditedTimeHorizon(configData.time_horizon ?? 'mid');
          // Update parent state with saved values
          onScenarioCountChange(configData.scenario_count ?? 5);
          onIncludeBlackSwansChange(configData.include_black_swans ?? true);
          onIncludeContrarianChange(configData.include_contrarian ?? true);
          onIncludeWildCardsChange(configData.include_wild_cards ?? true);
          onTimeHorizonChange(configData.time_horizon ?? 'mid');
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
        console.error('Error fetching EOS data:', err);
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

      // Save config if changed
      if (hasConfigChanges()) {
        savePromises.push(
          fetch('/api/eos/config', {
            method: 'PUT',
            credentials: 'include',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              scenario_count: editedScenarioCount,
              include_black_swans: editedIncludeBlackSwans,
              include_contrarian: editedIncludeContrarian,
              include_wild_cards: editedIncludeWildCards,
              time_horizon: editedTimeHorizon
            })
          })
        );
      }

      // Save any agents with changes
      for (const agent of agents) {
        if (hasAgentChanges(agent.id)) {
          savePromises.push(
            fetch(`/api/eos/prompts/${agent.id}`, {
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
        scenario_count: editedScenarioCount,
        include_black_swans: editedIncludeBlackSwans,
        include_contrarian: editedIncludeContrarian,
        include_wild_cards: editedIncludeWildCards,
        time_horizon: editedTimeHorizon
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
      onScenarioCountChange(editedScenarioCount);
      onIncludeBlackSwansChange(editedIncludeBlackSwans);
      onIncludeContrarianChange(editedIncludeContrarian);
      onIncludeWildCardsChange(editedIncludeWildCards);
      onTimeHorizonChange(editedTimeHorizon);

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
      setEditedScenarioCount(originalConfig.scenario_count);
      setEditedIncludeBlackSwans(originalConfig.include_black_swans);
      setEditedIncludeContrarian(originalConfig.include_contrarian);
      setEditedIncludeWildCards(originalConfig.include_wild_cards);
      setEditedTimeHorizon(originalConfig.time_horizon);
    }

    // Reset agent values
    const resetContent: Record<string, string> = {};
    const resetModels: Record<string, string> = {};
    const resetTemps: Record<string, string> = {};

    for (const agent of agents) {
      resetContent[agent.id] = agent.content;
      resetModels[agent.id] = agent.metadata?.model_config?.model || DEFAULT_MODELS[agent.id] || 'gpt-5.4';
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
    return editedScenarioCount !== originalConfig.scenario_count ||
           editedIncludeBlackSwans !== originalConfig.include_black_swans ||
           editedIncludeContrarian !== originalConfig.include_contrarian ||
           editedIncludeWildCards !== originalConfig.include_wild_cards ||
           editedTimeHorizon !== originalConfig.time_horizon;
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
          <DialogTitle className="text-2xl font-bold">Tune: Extreme Outliers</DialogTitle>
          <DialogDescription>
            Customize the 4-step EOS workflow - prompts, models, and scenario settings
          </DialogDescription>
        </DialogHeader>

        {/* Single scrollable content area */}
        <div className="flex-1 overflow-y-auto overflow-x-hidden space-y-6 mt-4 pr-2">
          {/* Generation Settings */}
          <div className="bg-purple-50 border border-purple-200 rounded-lg p-4">
            <div className="flex items-center justify-between mb-3">
              <label className="text-sm font-semibold text-purple-900">
                Generation Settings
              </label>
              {hasConfigChanges() && (
                <span className="text-xs text-orange-600 flex items-center gap-1">
                  <Settings2 className="w-3 h-3" />
                  Modified
                </span>
              )}
            </div>

            <div className="flex flex-wrap gap-6">
              {/* Scenario Count */}
              <div className="w-32">
                <label className="text-xs font-medium text-purple-800 block mb-1">
                  Scenario Count
                </label>
                <p className="text-xs text-purple-600 mb-2">Total to generate</p>
                <input
                  type="number"
                  value={editedScenarioCount}
                  onChange={(e) => setEditedScenarioCount(Math.max(1, Math.min(10, Number(e.target.value))))}
                  min={1}
                  max={10}
                  className="w-full px-3 py-2 border rounded-md text-sm"
                />
              </div>

              {/* Time Horizon */}
              <div className="w-48">
                <label className="text-xs font-medium text-purple-800 block mb-1">
                  Time Horizon
                </label>
                <p className="text-xs text-purple-600 mb-2">Scenario timeframe</p>
                <select
                  value={editedTimeHorizon}
                  onChange={(e) => setEditedTimeHorizon(e.target.value as 'near' | 'mid' | 'long')}
                  className="w-full px-3 py-2 border rounded-md text-sm"
                >
                  <option value="near">Near-term (0-2 years)</option>
                  <option value="mid">Mid-term (2-5 years)</option>
                  <option value="long">Long-term (5-10+ years)</option>
                </select>
              </div>

              {/* Scenario Types */}
              <div className="flex-1 min-w-[250px]">
                <label className="text-xs font-medium text-purple-800 block mb-1">
                  Scenario Types
                </label>
                <p className="text-xs text-purple-600 mb-2">Include these categories</p>
                <div className="flex gap-4">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={editedIncludeBlackSwans}
                      onChange={(e) => setEditedIncludeBlackSwans(e.target.checked)}
                      className="rounded"
                    />
                    <span className="text-sm text-purple-700">Black Swan</span>
                  </label>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={editedIncludeContrarian}
                      onChange={(e) => setEditedIncludeContrarian(e.target.checked)}
                      className="rounded"
                    />
                    <span className="text-sm text-amber-700">Contrarian</span>
                  </label>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={editedIncludeWildCards}
                      onChange={(e) => setEditedIncludeWildCards(e.target.checked)}
                      className="rounded"
                    />
                    <span className="text-sm text-blue-700">Wild Card</span>
                  </label>
                </div>
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
              <Loader2 className="w-8 h-8 animate-spin text-purple-500" />
              <span className="ml-2 text-gray-600">Loading configuration...</span>
            </div>
          ) : (
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
                          ? 'bg-purple-500 text-white'
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
                    className="px-4 py-2 bg-purple-500 text-white hover:bg-purple-600 rounded-md text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed"
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
