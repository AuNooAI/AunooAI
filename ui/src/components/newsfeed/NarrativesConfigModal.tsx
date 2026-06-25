/**
 * Narratives Config Modal - Configure Narrative/Theme Analysis
 */

import { useState, useEffect } from 'react';
import {
  Info,
  MessageSquare,
  Save,
  RotateCcw,
  Brain,
} from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '../ui/dialog';
import { Button } from '../ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../ui/tabs';
import { Label } from '../ui/label';
import { Textarea } from '../ui/textarea';

interface NarrativesConfigModalProps {
  open: boolean;
  onClose: () => void;
}

export interface NarrativesConfig {
  system_prompt: string;
  user_prompt: string;
  additional_instructions: string;
}

const DEFAULT_SYSTEM_PROMPT = `You are a news analyst reviewing recent coverage of '{topic}'.
Identify 3-5 common themes or storylines emerging across these articles.

Writing style:
- Use factual, journalistic language - report what the articles say, not promotional claims
- Avoid marketing speak, hype, or sensationalist phrasing
- Be specific: cite companies, people, numbers, or events mentioned in the sources
- Summaries should read like news briefs, not press releases

For each theme:
1. Give it a specific, descriptive name (not vague or grandiose)
2. Write a 2-3 sentence summary grounded in what the articles actually report
3. List the URIs of 2-5 articles that cover this theme

Format as JSON:
[{
  "theme_name": "Name of Theme",
  "theme_summary": "Summary explanation...",
  "article_uris": ["uri1", "uri2", ...]
}, ...]`;

const DEFAULT_USER_PROMPT = `Here are recent articles about '{topic}' to analyze for common themes:

{articles_text}

Identify 3-5 themes and format as specified JSON.`;

const DEFAULT_CONFIG: NarrativesConfig = {
  system_prompt: DEFAULT_SYSTEM_PROMPT,
  user_prompt: DEFAULT_USER_PROMPT,
  additional_instructions: '',
};

const STORAGE_KEY = 'narrativesConfig';

export function NarrativesConfigModal({ open, onClose }: NarrativesConfigModalProps) {
  const [config, setConfig] = useState<NarrativesConfig>(DEFAULT_CONFIG);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load config when modal opens
  useEffect(() => {
    if (open) {
      loadConfig();
    }
  }, [open]);

  const loadConfig = () => {
    setLoading(true);
    setError(null);
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved);
        setConfig({ ...DEFAULT_CONFIG, ...parsed });
      } else {
        setConfig(DEFAULT_CONFIG);
      }
    } catch (err) {
      setError('Failed to load configuration');
      setConfig(DEFAULT_CONFIG);
    } finally {
      setLoading(false);
    }
  };

  const handleSave = () => {
    setSaving(true);
    setError(null);
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(config));
      onClose();
    } catch (err) {
      setError('Failed to save configuration');
    } finally {
      setSaving(false);
    }
  };

  const handleReset = () => {
    if (!confirm('Reset all configuration to defaults? This cannot be undone.')) {
      return;
    }
    setConfig(DEFAULT_CONFIG);
    localStorage.removeItem(STORAGE_KEY);
  };

  const updateField = (field: keyof NarrativesConfig, value: string) => {
    setConfig((prev) => ({ ...prev, [field]: value }));
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="w-auto min-w-[600px] max-w-[95vw] h-[80vh] flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Brain className="w-5 h-5 text-indigo-500" />
            Configure Narratives
          </DialogTitle>
          <DialogDescription>
            Customize how the AI analyzes articles to identify themes and narratives
          </DialogDescription>
        </DialogHeader>

        {error && (
          <div className="px-4 py-2 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
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
              <TabsTrigger value="prompt" className="flex-1 gap-1 text-xs px-2">
                <MessageSquare className="w-3.5 h-3.5 shrink-0" />
                <span className="hidden sm:inline">Prompts</span>
              </TabsTrigger>
            </TabsList>

            <div className="mt-4 pr-2">
              {/* Loading State */}
              {loading && (
                <div className="flex items-center justify-center py-12">
                  <div className="text-center">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-500 mx-auto mb-4"></div>
                    <p className="text-gray-700 dark:text-gray-300">Loading configuration...</p>
                  </div>
                </div>
              )}

              {/* Info Tab */}
              <TabsContent value="info" className="space-y-4 mt-0">
                <div className="bg-indigo-50 dark:bg-indigo-950 border border-indigo-200 dark:border-indigo-800 rounded-lg p-4">
                  <h4 className="font-semibold text-indigo-900 dark:text-indigo-100 flex items-center gap-2 mb-2">
                    <Info className="w-4 h-4" />
                    About Narratives Configuration
                  </h4>
                  <p className="text-sm text-indigo-800 dark:text-indigo-200">
                    This configuration panel controls how the AI analyzes your articles to
                    identify common themes and narrative patterns across your news sources.
                  </p>
                </div>

                <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <MessageSquare className="w-5 h-5 text-indigo-500" />
                    <h4 className="font-semibold text-gray-900 dark:text-gray-100">Prompt Templates</h4>
                  </div>
                  <p className="text-sm text-gray-600 dark:text-gray-300 mb-2">
                    The core instructions that guide the AI's thematic analysis approach.
                  </p>
                  <p className="text-xs text-gray-700 dark:text-gray-300 dark:text-gray-300">
                    <span className="font-medium">Use this when:</span> You want to change how themes are identified or structured.
                  </p>
                </div>

                <div className="bg-amber-50 dark:bg-amber-950 border border-amber-200 dark:border-amber-800 rounded-lg p-4">
                  <h4 className="font-semibold text-amber-900 dark:text-amber-100 mb-2">Available Placeholders</h4>
                  <ul className="text-sm text-amber-800 dark:text-amber-200 space-y-1 list-disc list-inside">
                    <li><code className="bg-amber-100 dark:bg-amber-900 px-1 rounded">{'{topic}'}</code> - The current analysis topic</li>
                    <li><code className="bg-amber-100 dark:bg-amber-900 px-1 rounded">{'{articles_text}'}</code> - Formatted article content</li>
                  </ul>
                </div>
              </TabsContent>

              {/* Prompts Tab */}
              <TabsContent value="prompt" className="space-y-4 mt-0 overflow-x-hidden">
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                  <div className="lg:col-span-2 space-y-4">
                    <div>
                      <Label className="font-semibold">System Prompt Template</Label>
                      <p className="text-sm text-gray-700 dark:text-gray-300 dark:text-gray-300 mb-2">
                        Defines the AI's role and how it should analyze articles to identify themes.
                      </p>
                      <Textarea
                        value={config.system_prompt || ''}
                        onChange={(e) => updateField('system_prompt', e.target.value)}
                        rows={12}
                        className="font-mono text-xs w-full resize-y"
                        disabled={loading}
                      />
                    </div>

                    <div>
                      <Label className="font-semibold">User Prompt Template</Label>
                      <p className="text-sm text-gray-700 dark:text-gray-300 dark:text-gray-300 mb-2">
                        The message sent with each request, containing the articles to analyze.
                      </p>
                      <Textarea
                        value={config.user_prompt || ''}
                        onChange={(e) => updateField('user_prompt', e.target.value)}
                        rows={6}
                        className="font-mono text-xs w-full resize-y"
                        disabled={loading}
                      />
                    </div>
                  </div>

                  <div className="space-y-4">
                    <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-4">
                      <h4 className="font-semibold text-gray-900 dark:text-gray-100 mb-3">Available Placeholders</h4>
                      <div className="space-y-2 text-sm">
                        <div>
                          <code className="text-indigo-600 dark:text-indigo-400 bg-indigo-50 dark:bg-indigo-950 px-1 py-0.5 rounded text-xs">{'{topic}'}</code>
                          <p className="text-gray-700 dark:text-gray-300 dark:text-gray-300 text-xs mt-0.5">Replaced with the selected topic name</p>
                        </div>
                        <div>
                          <code className="text-indigo-600 dark:text-indigo-400 bg-indigo-50 dark:bg-indigo-950 px-1 py-0.5 rounded text-xs">{'{articles_text}'}</code>
                          <p className="text-gray-700 dark:text-gray-300 dark:text-gray-300 text-xs mt-0.5">Replaced with formatted article content (title, source, summary, URI)</p>
                        </div>
                      </div>
                    </div>

                    <div className="bg-amber-50 dark:bg-amber-950 border border-amber-200 dark:border-amber-800 rounded-lg p-4">
                      <h4 className="font-semibold text-amber-900 dark:text-amber-100 mb-2">Important</h4>
                      <ul className="text-xs text-amber-800 dark:text-amber-200 space-y-1.5 list-disc list-inside">
                        <li>The AI must return valid JSON array format</li>
                        <li>Each theme needs: <code className="bg-amber-100 dark:bg-amber-900 px-1 rounded">theme_name</code>, <code className="bg-amber-100 dark:bg-amber-900 px-1 rounded">theme_summary</code>, <code className="bg-amber-100 dark:bg-amber-900 px-1 rounded">article_uris</code></li>
                        <li>URIs must match exactly as provided in the articles</li>
                      </ul>
                    </div>

                    <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-4">
                      <h4 className="font-semibold text-gray-900 dark:text-gray-100 mb-2">Tips</h4>
                      <ul className="text-xs text-gray-600 dark:text-gray-300 space-y-1.5 list-disc list-inside">
                        <li>Adjust "3-5 themes" to change how many themes are identified</li>
                        <li>Add domain expertise to improve relevance</li>
                        <li>Include specific focus areas or exclusions</li>
                        <li>Use Reset to restore defaults if needed</li>
                      </ul>
                    </div>
                  </div>
                </div>
              </TabsContent>

            </div>
          </Tabs>
        </div>

        <DialogFooter className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-2 border-t pt-4 shrink-0 mt-4">
          <Button variant="outline" onClick={onClose} className="order-3 sm:order-1">
            Cancel
          </Button>
          <div className="flex flex-col sm:flex-row gap-2 order-1 sm:order-2">
            <Button variant="outline" size="sm" onClick={handleReset} disabled={loading || saving} className="text-xs">
              <RotateCcw className="w-3.5 h-3.5 mr-1.5" />
              Reset
            </Button>
            <Button size="sm" onClick={handleSave} disabled={loading || saving} className="text-xs">
              <Save className="w-3.5 h-3.5 mr-1.5" />
              {saving ? 'Saving...' : 'Save'}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
