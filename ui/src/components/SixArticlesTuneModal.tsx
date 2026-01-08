/**
 * Six Articles Tune Modal - Configuration editor for Your Briefing
 * Styled to match IncidentConfigModal and NarrativesConfigModal
 */

import { useState, useEffect } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle
} from './ui/dialog';
import { Button } from './ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from './ui/tabs';
import { Label } from './ui/label';
import { Textarea } from './ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import {
  Save,
  RotateCcw,
  FileText,
  Users,
  Plus,
  Trash2,
  Info,
  Settings2,
  Newspaper,
} from 'lucide-react';

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
  articleCount?: number;
}

interface SixArticlesTuneModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfigSaved?: () => void;
  articleCount?: number;
  onArticleCountChange?: (count: number) => void;
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
  onConfigSaved,
  articleCount: propArticleCount,
  onArticleCountChange
}: SixArticlesTuneModalProps) {
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Config state
  const [originalConfig, setOriginalConfig] = useState<SixArticlesConfig | null>(null);
  const [editedPrompt, setEditedPrompt] = useState<string>('');
  const [editedPersonas, setEditedPersonas] = useState<Record<string, PersonaDefinition>>({});
  const [editedArticleCount, setEditedArticleCount] = useState<number>(propArticleCount ?? 6);

  // UI state
  const [editingPersona, setEditingPersona] = useState<string | null>(null);

  // Fetch config when modal opens
  useEffect(() => {
    if (!open) return;

    const fetchConfig = async () => {
      setLoading(true);
      setError(null);

      try {
        const res = await fetch('/api/news-feed/six-articles/config', {
          credentials: 'include'
        });

        if (res.ok) {
          const config = await res.json();
          setOriginalConfig(config);
          setEditedPrompt(config.systemPrompt || DEFAULT_PROMPT_TEMPLATE);
          setEditedPersonas(config.personas || {});
          setEditedArticleCount(config.articleCount ?? propArticleCount ?? 6);
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

  // Save changes
  const saveConfig = async () => {
    setSaving(true);
    setError(null);

    try {
      const configToSave: SixArticlesConfig = {
        systemPrompt: editedPrompt === DEFAULT_PROMPT_TEMPLATE ? null : editedPrompt,
        personas: editedPersonas,
        formatSpec: originalConfig?.formatSpec || null,
        articleCount: editedArticleCount
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

      setOriginalConfig(configToSave);

      // Notify parent of article count change
      if (onArticleCountChange) {
        onArticleCountChange(editedArticleCount);
      }

      onOpenChange(false);

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

  // Reset to defaults
  const resetConfig = () => {
    if (!confirm('Reset all configuration to defaults? This cannot be undone.')) {
      return;
    }
    setEditedPrompt(DEFAULT_PROMPT_TEMPLATE);
    // Reset personas to defaults would need to fetch from backend
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
      <DialogContent className="w-auto min-w-[600px] max-w-[95vw] h-[80vh] flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Newspaper className="w-5 h-5 text-pink-500" />
            Configure Your Briefing
          </DialogTitle>
          <DialogDescription>
            Customize personas and prompt template for the Six Articles briefing
          </DialogDescription>
        </DialogHeader>

        {error && (
          <div className="px-4 py-2 bg-red-50 dark:bg-red-950 border border-red-200 dark:border-red-800 rounded-lg text-red-700 dark:text-red-200 text-sm">
            {error}
          </div>
        )}

        <div className="flex-1 min-h-0 overflow-y-auto">
          <Tabs defaultValue="info" className="h-full">
            <TabsList className="w-full shrink-0 flex sticky top-0 bg-white dark:bg-gray-900 z-10">
              <TabsTrigger value="info" className="flex-1 gap-1 text-xs px-2">
                <Info className="w-3.5 h-3.5 shrink-0" />
                <span className="hidden sm:inline">Info</span>
              </TabsTrigger>
              <TabsTrigger value="personas" className="flex-1 gap-1 text-xs px-2">
                <Users className="w-3.5 h-3.5 shrink-0" />
                <span className="hidden sm:inline">Personas</span>
              </TabsTrigger>
              <TabsTrigger value="prompt" className="flex-1 gap-1 text-xs px-2">
                <FileText className="w-3.5 h-3.5 shrink-0" />
                <span className="hidden sm:inline">Prompt</span>
              </TabsTrigger>
            </TabsList>

            <div className="mt-4 pr-2">
              {/* Loading State */}
              {loading && (
                <div className="flex items-center justify-center py-12">
                  <div className="text-center">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-pink-500 mx-auto mb-4"></div>
                    <p className="text-gray-500 dark:text-gray-400">Loading configuration...</p>
                  </div>
                </div>
              )}

              {/* Info Tab */}
              <TabsContent value="info" className="space-y-4 mt-0">
                <div className="bg-pink-50 dark:bg-pink-950 border border-pink-200 dark:border-pink-800 rounded-lg p-4">
                  <h4 className="font-semibold text-pink-900 dark:text-pink-100 flex items-center gap-2 mb-2">
                    <Info className="w-4 h-4" />
                    About Your Briefing Configuration
                  </h4>
                  <p className="text-sm text-pink-800 dark:text-pink-200">
                    Configure how the AI selects and presents your daily briefing articles.
                    Customize personas to match different executive perspectives and priorities.
                  </p>
                </div>

                {/* Article Count Setting */}
                <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-4">
                  <div className="flex items-center gap-2 mb-3">
                    <Newspaper className="w-5 h-5 text-pink-500" />
                    <h4 className="font-semibold text-gray-900 dark:text-gray-100">Number of Articles</h4>
                  </div>
                  <p className="text-sm text-gray-600 dark:text-gray-300 mb-3">
                    Choose how many articles to include in your daily briefing (3-12).
                  </p>
                  <div className="flex items-center gap-4">
                    <input
                      type="range"
                      min="3"
                      max="12"
                      value={editedArticleCount}
                      onChange={(e) => setEditedArticleCount(Number(e.target.value))}
                      className="flex-1 h-2 bg-gray-200 dark:bg-gray-700 rounded-lg appearance-none cursor-pointer accent-pink-500"
                    />
                    <span className="w-8 text-center font-bold text-lg text-pink-600 dark:text-pink-400">
                      {editedArticleCount}
                    </span>
                  </div>
                </div>

                <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <Users className="w-5 h-5 text-pink-500" />
                    <h4 className="font-semibold text-gray-900 dark:text-gray-100">Personas</h4>
                  </div>
                  <p className="text-sm text-gray-600 dark:text-gray-300 mb-2">
                    Define executive perspectives (CEO, CMO, CTO, CISO) with specific priorities and focus areas.
                  </p>
                  <p className="text-xs text-gray-500 dark:text-gray-400">
                    <span className="font-medium">Use this when:</span> You want articles selected for specific leadership roles.
                  </p>
                </div>

                <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <FileText className="w-5 h-5 text-pink-500" />
                    <h4 className="font-semibold text-gray-900 dark:text-gray-100">Prompt Template</h4>
                  </div>
                  <p className="text-sm text-gray-600 dark:text-gray-300 mb-2">
                    The core instructions that guide how articles are selected and analyzed.
                  </p>
                  <p className="text-xs text-gray-500 dark:text-gray-400">
                    <span className="font-medium">Use this when:</span> You want to change selection criteria or output format.
                  </p>
                </div>

                <div className="bg-amber-50 dark:bg-amber-950 border border-amber-200 dark:border-amber-800 rounded-lg p-4">
                  <h4 className="font-semibold text-amber-900 dark:text-amber-100 mb-2">Available Placeholders</h4>
                  <ul className="text-sm text-amber-800 dark:text-amber-200 space-y-1 list-disc list-inside">
                    <li><code className="bg-amber-100 dark:bg-amber-900 px-1 rounded">{'{persona}'}</code> - Selected persona name</li>
                    <li><code className="bg-amber-100 dark:bg-amber-900 px-1 rounded">{'{article_count}'}</code> - Number of articles to select</li>
                    <li><code className="bg-amber-100 dark:bg-amber-900 px-1 rounded">{'{persona_focus}'}</code> - Persona's focus areas</li>
                    <li><code className="bg-amber-100 dark:bg-amber-900 px-1 rounded">{'{articles_summary}'}</code> - Available articles</li>
                  </ul>
                </div>
              </TabsContent>

              {/* Personas Tab */}
              <TabsContent value="personas" className="space-y-4 mt-0">
                <div className="flex items-center justify-between">
                  <div>
                    <Label className="font-semibold">Executive Personas</Label>
                    <p className="text-sm text-gray-500 dark:text-gray-400">
                      Define perspectives for article selection and analysis
                    </p>
                  </div>
                  <Button variant="outline" size="sm" onClick={addCustomPersona} className="text-xs">
                    <Plus className="w-3.5 h-3.5 mr-1.5" />
                    Add Custom
                  </Button>
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                  {Object.entries(editedPersonas).map(([personaId, personaDef]) => {
                    const isBuiltIn = ['CEO', 'CMO', 'CTO', 'CISO'].includes(personaId);
                    const isExpanded = editingPersona === personaId;

                    return (
                      <div
                        key={personaId}
                        className={`border rounded-lg p-4 ${isExpanded ? 'ring-2 ring-pink-500' : ''} ${
                          isBuiltIn
                            ? 'bg-gray-50 dark:bg-gray-800 border-gray-200 dark:border-gray-700'
                            : 'bg-white dark:bg-gray-900 border-gray-200 dark:border-gray-700'
                        }`}
                      >
                        <div className="flex items-center justify-between mb-2">
                          <div className="flex items-center gap-2">
                            <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                              isBuiltIn
                                ? 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300'
                                : 'bg-pink-100 dark:bg-pink-900 text-pink-700 dark:text-pink-300'
                            }`}>
                              {isBuiltIn ? personaId : 'Custom'}
                            </span>
                            <h4 className="font-semibold text-gray-800 dark:text-gray-200">
                              {getPersonaName(personaId, personaDef)}
                            </h4>
                          </div>
                          <div className="flex gap-1">
                            <button
                              onClick={() => setEditingPersona(isExpanded ? null : personaId)}
                              className="p-1 hover:bg-gray-200 dark:hover:bg-gray-700 rounded"
                            >
                              <Settings2 className="w-4 h-4 text-gray-500 dark:text-gray-400" />
                            </button>
                            {!isBuiltIn && (
                              <button
                                onClick={() => deletePersona(personaId)}
                                className="p-1 hover:bg-red-100 dark:hover:bg-red-900 rounded"
                              >
                                <Trash2 className="w-4 h-4 text-red-500" />
                              </button>
                            )}
                          </div>
                        </div>

                        {isExpanded ? (
                          <div className="space-y-3 mt-3">
                            <div>
                              <Label className="text-xs">Risk Appetite</Label>
                              <Select
                                value={personaDef.riskAppetite}
                                onValueChange={(value) => updatePersonaField(personaId, 'riskAppetite', value)}
                              >
                                <SelectTrigger className="w-full h-8 mt-1">
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

                            <div>
                              <Label className="text-xs">Priorities</Label>
                              <Textarea
                                value={personaDef.priorities}
                                onChange={(e) => updatePersonaField(personaId, 'priorities', e.target.value)}
                                className="mt-1 text-xs h-20"
                                placeholder="Strategic growth, Revenue impact, ..."
                              />
                            </div>

                            <div>
                              <Label className="text-xs">Focus Areas</Label>
                              <Textarea
                                value={personaDef.focus}
                                onChange={(e) => updatePersonaField(personaId, 'focus', e.target.value)}
                                className="mt-1 text-xs h-20"
                                placeholder="Industry trends, Competitive landscape, ..."
                              />
                            </div>
                          </div>
                        ) : (
                          <div className="text-sm text-gray-600 dark:text-gray-400 space-y-1">
                            <p><span className="font-medium">Risk:</span> {personaDef.riskAppetite}</p>
                            <p className="truncate"><span className="font-medium">Focus:</span> {personaDef.focus}</p>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </TabsContent>

              {/* Prompt Tab */}
              <TabsContent value="prompt" className="space-y-4 mt-0 overflow-x-hidden">
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                  <div className="lg:col-span-2 space-y-4">
                    <div>
                      <Label className="font-semibold">System Prompt Template</Label>
                      <p className="text-sm text-gray-500 dark:text-gray-400 mb-2">
                        The prompt template used to generate the Six Articles briefing.
                      </p>
                      <Textarea
                        value={editedPrompt}
                        onChange={(e) => setEditedPrompt(e.target.value)}
                        rows={20}
                        className="font-mono text-xs w-full resize-y"
                        disabled={loading}
                      />
                    </div>
                  </div>

                  <div className="space-y-4">
                    <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-4">
                      <h4 className="font-semibold text-gray-900 dark:text-gray-100 mb-3">Available Placeholders</h4>
                      <div className="space-y-2 text-sm">
                        {[
                          { name: '{persona}', desc: 'Selected persona name (CEO, CMO, etc.)' },
                          { name: '{article_count}', desc: 'Number of articles to select' },
                          { name: '{persona_description}', desc: 'Full persona description' },
                          { name: '{persona_focus}', desc: 'Persona focus areas' },
                          { name: '{audience_profile}', desc: 'Audience profile details' },
                          { name: '{articles_summary}', desc: 'Available articles to select from' },
                          { name: '{bias_context}', desc: 'Source bias information' },
                          { name: '{source_context}', desc: 'Source credibility context' },
                        ].map(({ name, desc }) => (
                          <div key={name}>
                            <code className="text-pink-600 dark:text-pink-400 bg-pink-50 dark:bg-pink-950 px-1 py-0.5 rounded text-xs">{name}</code>
                            <p className="text-gray-500 dark:text-gray-400 text-xs mt-0.5">{desc}</p>
                          </div>
                        ))}
                      </div>
                    </div>

                    <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-4">
                      <h4 className="font-semibold text-gray-900 dark:text-gray-100 mb-2">Tips</h4>
                      <ul className="text-xs text-gray-600 dark:text-gray-300 space-y-1.5 list-disc list-inside">
                        <li>Adjust article_count to change briefing size</li>
                        <li>Modify selection rules to change criteria</li>
                        <li>Customize output fields as needed</li>
                        <li>Use Reset to restore defaults</li>
                      </ul>
                    </div>
                  </div>
                </div>
              </TabsContent>
            </div>
          </Tabs>
        </div>

        <DialogFooter className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-2 border-t pt-4 shrink-0 mt-4">
          <Button variant="outline" onClick={() => onOpenChange(false)} className="order-3 sm:order-1">
            Cancel
          </Button>
          <div className="flex flex-col sm:flex-row gap-2 order-1 sm:order-2">
            <Button variant="outline" size="sm" onClick={resetConfig} disabled={loading || saving} className="text-xs">
              <RotateCcw className="w-3.5 h-3.5 mr-1.5" />
              Reset
            </Button>
            <Button size="sm" onClick={saveConfig} disabled={loading || saving} className="text-xs">
              <Save className="w-3.5 h-3.5 mr-1.5" />
              {saving ? 'Saving...' : 'Save'}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
