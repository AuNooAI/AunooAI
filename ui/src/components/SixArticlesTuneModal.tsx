/**
 * Six Articles Tune Modal - Configuration editor for Your Briefing
 *
 * Allows editing of:
 * 1. Persona definitions (CEO/CMO/CTO/CISO + custom)
 * 2. System Prompt - The main prompt template for article selection/analysis
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
import { Loader2, Save, RotateCcw, FileText, Settings2, Users, Plus, Trash2 } from 'lucide-react';
import { Alert, AlertDescription } from './ui/alert';

interface PersonaDefinition {
  name?: string;
  priorities: string;
  riskAppetite: string;
  focus: string;
}

interface SixArticlesConfig {
  systemPrompt: string | null;
  personas: Record<string, PersonaDefinition>;
  formatSpec: string | null;
}

interface SixArticlesTuneModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfigSaved?: () => void;
}

// Risk appetite options
const RISK_APPETITES = ['low', 'moderate', 'high', 'aggressive'];

// Default prompt template (matches backend)
const DEFAULT_PROMPT_TEMPLATE = `🎯 {persona} Daily Top-{article_count} AI Articles — Analyst Prompt

You are an analyst selecting the {article_count} most important articles published in the last 24 hours for {persona_description} interested in AI's strategic, technical, and societal impacts, with specific focus on {persona_focus}.
{starred_instruction}

{audience_profile}

## Selection Rules
Choose exactly {article_count} articles from the provided corpus (news, filings, research, regulator posts). Each must score high on at least two:
1) Strategic relevance, 2) Novelty, 3) Credibility, 4) Representativeness (captures a bigger debate/trend).

- **Diversity**: Cover ≥3 domains (e.g., policy, business/market, tech/R&D, workforce/society).
- **No redundancy**: Don't select multiple pieces on the same event unless they provide non-overlapping value (e.g., a filing + a data-driven analysis).
- **Recency**: Past 24 hours only.

## Article Corpus
{articles_summary}

{bias_context}
{source_context}

## What to Output per Article

**title** — Full headline with source and date: "Headline (Source, YYYY-MM-DD, Author)"
**source** — Publisher name (e.g., "Reuters")
**date** — YYYY-MM-DD
**url** — Plain canonical URL (no markdown, no tracking params)
**executive_takeaway** — 1 sentence: the critical gist for a CEO in ~15 words
**summary** — 2–3 sentences of core facts/developments
**strategic_relevance** — 1 short paragraph on why this matters (policy, competition, tech, workforce, risk posture)
**time_horizon** — Immediate (0–6m) | Medium (6–18m) | Long-term (18m+)
**risk_opportunity** — "risk" | "opportunity" | "mixed" + brief rationale
**signal_strength** — "weak" | "moderate" | "strong" with a short justification
**executive_action** — Array of 1–2 bullets: what to watch, decide, or delegate now
**category** — "policy" | "market" | "tech" | "workforce" | "security" | "society"
**scores** — Optional scoring object: {"relevance": 0-5, "novelty": 0-5, "credibility": 0-5, "representativeness": 0-5}

Return ONLY a valid JSON array with the articles. No markdown, no explanations.`;

export function SixArticlesTuneModal({
  open,
  onOpenChange,
  onConfigSaved
}: SixArticlesTuneModalProps) {
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Config state
  const [originalConfig, setOriginalConfig] = useState<SixArticlesConfig | null>(null);
  const [editedPrompt, setEditedPrompt] = useState<string>('');
  const [editedPersonas, setEditedPersonas] = useState<Record<string, PersonaDefinition>>({});

  // UI state
  const [activeTab, setActiveTab] = useState<'personas' | 'prompt'>('personas');
  const [editingPersona, setEditingPersona] = useState<string | null>(null);

  // Fetch config when modal opens
  useEffect(() => {
    if (!open) return;

    const fetchConfig = async () => {
      setLoading(true);
      setError(null);
      setSuccessMessage(null);

      try {
        const res = await fetch('/api/news-feed/six-articles/config', {
          credentials: 'include'
        });

        if (res.ok) {
          const config = await res.json();
          setOriginalConfig(config);
          setEditedPrompt(config.systemPrompt || DEFAULT_PROMPT_TEMPLATE);
          setEditedPersonas(config.personas || {});
        } else {
          throw new Error('Failed to load configuration');
        }
      } catch (err) {
        console.error('Error fetching config:', err);
        setError(err instanceof Error ? err.message : 'Failed to load configuration');
      } finally {
        setLoading(false);
      }
    };

    fetchConfig();
  }, [open]);

  // Check if config has changed
  const hasChanges = () => {
    if (!originalConfig) return false;

    const originalPrompt = originalConfig.systemPrompt || DEFAULT_PROMPT_TEMPLATE;
    if (editedPrompt !== originalPrompt) return true;

    const origPersonas = JSON.stringify(originalConfig.personas);
    const editedPersonasStr = JSON.stringify(editedPersonas);
    return origPersonas !== editedPersonasStr;
  };

  // Save changes
  const saveConfig = async () => {
    setSaving(true);
    setError(null);
    setSuccessMessage(null);

    try {
      const configToSave: SixArticlesConfig = {
        systemPrompt: editedPrompt === DEFAULT_PROMPT_TEMPLATE ? null : editedPrompt,
        personas: editedPersonas,
        formatSpec: originalConfig?.formatSpec || null
      };

      const res = await fetch('/api/news-feed/six-articles/config', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(configToSave)
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || 'Failed to save configuration');
      }

      // Update original config to match saved
      setOriginalConfig(configToSave);
      setSuccessMessage('Configuration saved successfully');

      if (onConfigSaved) {
        onConfigSaved();
      }
    } catch (err) {
      console.error('Error saving config:', err);
      setError(err instanceof Error ? err.message : 'Failed to save configuration');
    } finally {
      setSaving(false);
    }
  };

  // Reset to original values
  const resetConfig = () => {
    if (originalConfig) {
      setEditedPrompt(originalConfig.systemPrompt || DEFAULT_PROMPT_TEMPLATE);
      setEditedPersonas(originalConfig.personas || {});
    }
    setSuccessMessage(null);
  };

  // Reset prompt to default
  const resetPromptToDefault = () => {
    setEditedPrompt(DEFAULT_PROMPT_TEMPLATE);
  };

  // Add custom persona
  const addCustomPersona = () => {
    const customId = `Custom_${Date.now()}`;
    setEditedPersonas(prev => ({
      ...prev,
      [customId]: {
        name: 'Custom Persona',
        priorities: 'Strategic relevance, Business impact, Innovation',
        riskAppetite: 'moderate',
        focus: 'Industry trends, Competitive landscape'
      }
    }));
    setEditingPersona(customId);
  };

  // Delete persona (only custom ones)
  const deletePersona = (personaId: string) => {
    if (['CEO', 'CMO', 'CTO', 'CISO'].includes(personaId)) return;
    setEditedPersonas(prev => {
      const updated = { ...prev };
      delete updated[personaId];
      return updated;
    });
    if (editingPersona === personaId) {
      setEditingPersona(null);
    }
  };

  // Update persona field
  const updatePersonaField = (personaId: string, field: keyof PersonaDefinition, value: string) => {
    setEditedPersonas(prev => ({
      ...prev,
      [personaId]: {
        ...prev[personaId],
        [field]: value
      }
    }));
  };

  // Get display name for persona
  const getPersonaName = (id: string, def: PersonaDefinition): string => {
    if (def.name) return def.name;
    return id;
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-[95vw] w-[95vw] h-[95vh] max-h-[95vh] overflow-hidden flex flex-col overflow-x-hidden">
        <DialogHeader>
          <DialogTitle className="text-2xl font-bold">Tune: Your Briefing</DialogTitle>
          <DialogDescription>
            Customize the personas and prompt template for the Six Articles briefing generation
          </DialogDescription>
        </DialogHeader>

        {/* Tab Switcher */}
        <div className="flex gap-2 border-b pb-2">
          <button
            onClick={() => setActiveTab('personas')}
            className={`flex items-center gap-2 px-4 py-2 rounded-t-lg text-sm font-medium transition-colors ${
              activeTab === 'personas'
                ? 'bg-pink-500 text-white'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            <Users className="w-4 h-4" />
            Personas
          </button>
          <button
            onClick={() => setActiveTab('prompt')}
            className={`flex items-center gap-2 px-4 py-2 rounded-t-lg text-sm font-medium transition-colors ${
              activeTab === 'prompt'
                ? 'bg-pink-500 text-white'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            <FileText className="w-4 h-4" />
            System Prompt
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto overflow-x-hidden space-y-6 mt-4 pr-2">
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
              {/* Personas Tab */}
              {activeTab === 'personas' && (
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <label className="text-sm font-semibold text-gray-700">Executive Personas</label>
                      <p className="text-xs text-gray-500">Define perspectives for article selection and analysis</p>
                    </div>
                    <button
                      onClick={addCustomPersona}
                      className="flex items-center gap-2 px-3 py-1.5 bg-pink-100 text-pink-700 hover:bg-pink-200 rounded-md text-sm font-medium"
                    >
                      <Plus className="w-4 h-4" />
                      Add Custom Persona
                    </button>
                  </div>

                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                    {Object.entries(editedPersonas).map(([personaId, personaDef]) => {
                      const isBuiltIn = ['CEO', 'CMO', 'CTO', 'CISO'].includes(personaId);
                      const isExpanded = editingPersona === personaId;

                      return (
                        <div
                          key={personaId}
                          className={`border rounded-lg p-4 ${isExpanded ? 'ring-2 ring-pink-500' : ''} ${
                            isBuiltIn ? 'bg-gray-50' : 'bg-white'
                          }`}
                        >
                          <div className="flex items-center justify-between mb-2">
                            <div className="flex items-center gap-2">
                              <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                                isBuiltIn ? 'bg-gray-200 text-gray-700' : 'bg-pink-100 text-pink-700'
                              }`}>
                                {isBuiltIn ? personaId : 'Custom'}
                              </span>
                              {isExpanded && !isBuiltIn ? (
                                <input
                                  type="text"
                                  value={personaDef.name || personaId}
                                  onChange={(e) => updatePersonaField(personaId, 'name', e.target.value)}
                                  className="font-semibold text-gray-800 border-b border-pink-500 bg-transparent focus:outline-none"
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
                                  value={personaDef.riskAppetite}
                                  onValueChange={(value) => updatePersonaField(personaId, 'riskAppetite', value)}
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
                                  Priorities
                                </label>
                                <textarea
                                  value={personaDef.priorities}
                                  onChange={(e) => updatePersonaField(personaId, 'priorities', e.target.value)}
                                  className="w-full h-20 px-2 py-1 border rounded text-sm"
                                  placeholder="Strategic growth, Revenue impact, ..."
                                />
                              </div>

                              {/* Focus Areas */}
                              <div>
                                <label className="text-xs font-medium text-gray-600 block mb-1">
                                  Focus Areas
                                </label>
                                <textarea
                                  value={personaDef.focus}
                                  onChange={(e) => updatePersonaField(personaId, 'focus', e.target.value)}
                                  className="w-full h-20 px-2 py-1 border rounded text-sm"
                                  placeholder="Industry trends, Competitive landscape, ..."
                                />
                              </div>
                            </div>
                          ) : (
                            <div className="text-sm text-gray-600 space-y-1">
                              <p><span className="font-medium">Risk:</span> {personaDef.riskAppetite}</p>
                              <p className="truncate"><span className="font-medium">Focus:</span> {personaDef.focus}</p>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Prompt Tab */}
              {activeTab === 'prompt' && (
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <label className="text-sm font-semibold text-gray-700">System Prompt Template</label>
                      <p className="text-xs text-gray-500 mt-1">
                        The prompt template used to generate the Six Articles briefing. Use placeholders like {'{persona}'}, {'{article_count}'}, {'{audience_profile}'}, etc.
                      </p>
                    </div>
                    <button
                      onClick={resetPromptToDefault}
                      className="flex items-center gap-2 px-3 py-1.5 bg-gray-100 text-gray-700 hover:bg-gray-200 rounded-md text-sm font-medium"
                    >
                      <RotateCcw className="w-4 h-4" />
                      Reset to Default
                    </button>
                  </div>

                  {/* Available Placeholders */}
                  <div className="bg-pink-50 border border-pink-200 rounded-lg p-3">
                    <p className="text-xs font-medium text-pink-800 mb-2">Available Placeholders:</p>
                    <div className="flex flex-wrap gap-2">
                      {[
                        '{persona}',
                        '{article_count}',
                        '{persona_description}',
                        '{persona_focus}',
                        '{starred_instruction}',
                        '{audience_profile}',
                        '{articles_summary}',
                        '{bias_context}',
                        '{source_context}'
                      ].map(placeholder => (
                        <code
                          key={placeholder}
                          className="px-2 py-0.5 bg-white text-pink-700 text-xs rounded border border-pink-200 cursor-pointer hover:bg-pink-100"
                          onClick={() => {
                            navigator.clipboard.writeText(placeholder);
                          }}
                          title="Click to copy"
                        >
                          {placeholder}
                        </code>
                      ))}
                    </div>
                  </div>

                  {/* Prompt Editor */}
                  <textarea
                    value={editedPrompt}
                    onChange={(e) => setEditedPrompt(e.target.value)}
                    className="w-full h-[500px] p-4 border rounded-lg font-mono text-xs leading-relaxed resize-y"
                    placeholder="Enter system prompt template..."
                  />
                </div>
              )}

              {/* Save/Reset Buttons */}
              <div className="flex items-center justify-between pt-4 border-t">
                <div className="text-sm text-gray-500">
                  {hasChanges() ? (
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
                    onClick={resetConfig}
                    disabled={!hasChanges()}
                    className="px-4 py-2 text-gray-700 hover:bg-gray-100 rounded-md text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    <RotateCcw className="w-4 h-4 inline mr-2" />
                    Reset
                  </button>
                  <button
                    onClick={saveConfig}
                    disabled={!hasChanges() || saving}
                    className="px-4 py-2 bg-pink-500 text-white hover:bg-pink-600 rounded-md text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {saving ? (
                      <Loader2 className="w-4 h-4 inline mr-2 animate-spin" />
                    ) : (
                      <Save className="w-4 h-4 inline mr-2" />
                    )}
                    Save
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
