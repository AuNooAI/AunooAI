/**
 * Incident Config Modal - Configure Incident Tracking Analysis
 * Matches incidentConfigModal from news_feed_new.html (lines 3448-3807)
 */

import { useState, useEffect } from 'react';
import {
  Settings,
  Info,
  MessageSquare,
  Network,
  Lightbulb,
  Save,
  RotateCcw,
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
import { Input } from '../ui/input';
import { Checkbox } from '../ui/checkbox';
import {
  type IncidentConfig,
  getIncidentConfig,
  saveIncidentConfig,
  resetIncidentConfigToDefaults,
} from '../../services/narrativeExplorerApi';

interface IncidentConfigModalProps {
  open: boolean;
  onClose: () => void;
}

// Default templates - matching news_feed_new.html
// Note: {topic_label} and {topic_focus} are dynamically set based on selected topic and org profile
const DEFAULT_SYSTEM_PROMPT = `You are a threat intelligence analyst tracking incidents, entities, and events in {topic_label}, with focus on {topic_focus}.

IMPORTANT: Assess credibility and plausibility. Treat extraordinary, self-reported breakthroughs with skepticism.
Use factual_reporting, MBFC credibility, and bias indicators. Down-rank or flag items from low/mixed credibility or fringe bias sources.

{profile_context}

{analysis_instructions}

{quality_guidelines}

{ontology_text}

Required fields for each item:
- name
- type: incident | entity | event | expertise | informed_insider | trend_signal | strategic_shift
- subtype: from the allowed list for the chosen type
- description
- article_uris
- timeline
- significance: low | medium | high (reduce if credibility concerns exist)
- investigation_leads
- related_entities
- plausibility: likely | questionable | implausible
- source_quality: high | mixed | low
- misinfo_flags: [] e.g., "extraordinary_claim", "no_independent_verification", "low_factuality_source", "fringe_bias"
- credibility_summary: 1-2 sentence rationale

Devil's Advocate Smell Test:
- Add a "devils_advocate" field with brief caution if the claim appears hyperbolic or extraordinary relative to typical evidence.
- Use label "Hyperbolic Claim" when applicable.

Output a pure JSON array only.`;

const DEFAULT_USER_PROMPT = `Analyze these {topic} articles for threat hunting incidents, entities, and events:

{articles_text}`;

const DEFAULT_BASE_ONTOLOGY = `ONTOLOGY — Types and Subtypes
Valid types: incident | event | entity | expertise | informed_insider | trend_signal | strategic_shift

Definitions:
- incident: Discrete occurrence with material operational/strategic/risk impact that may warrant response, remediation, or escalation.
- event: Noteworthy occurrence (signals, milestones, announcements) that informs context or trends but is not itself a disruptive incident.
- entity: Organization, person, product, venue, dataset (things we track, not occurrences).
- expertise: Expert analysis, predictions, or authoritative insights from recognized industry leaders, analysts, or researchers.
- informed_insider: Insider perspectives, leaked information, or privileged insights from people with direct access to relevant information.
- trend_signal: Market trends, behavioral shifts, or emerging patterns that indicate future developments.
- strategic_shift: Major strategic changes, policy pivots, or directional changes by key organizations or governments.

Recommended subtypes:
- incident: regulatory_action, compliance_breach, data_security, legal_ip, mna, layoffs, funding_cut, rd_spend_change, governance_change, market_disruption
- event: product_launch, feature_update, partnership_mou, funding_round, hiring, award, conference_announcement, roadmap_teaser, benchmark_result, pilot_program
- entity: company, person, product, dataset, venue, regulator, research_institution, government_agency
- expertise: industry_analysis, market_prediction, technical_assessment, strategic_forecast, expert_warning, research_finding
- informed_insider: leaked_strategy, internal_memo, insider_trading, confidential_roadmap, private_meeting, executive_communication
- trend_signal: adoption_trend, market_shift, behavioral_change, technology_uptake, regulatory_momentum, competitive_dynamic
- strategic_shift: policy_pivot, strategic_realignment, market_repositioning, technology_focus_change, regulatory_approach_change

Assignment rules:
- Use 'incident' for events requiring immediate attention or response (layoffs, breaches, regulatory actions, major failures).
- Use 'event' for announcements and developments (product launches, funding, partnerships, pilot programs).
- Use 'entity' for organizations, people, or products being tracked.
- Use 'expertise' when article features expert analysis, predictions, or authoritative insights from recognized leaders.
- Use 'informed_insider' when article contains insider information, leaks, or privileged access insights.
- Use 'trend_signal' when article identifies emerging patterns, market trends, or behavioral shifts.
- Use 'strategic_shift' when article describes major strategic changes, policy pivots, or directional changes.
- Always include a 'subtype' from the lists above.
- Be inclusive rather than restrictive - classify newsworthy content appropriately.`;

const DEFAULT_ONTOLOGY_EXAMPLES = `Labeling examples (JSON objects):
{"name": "SoftBank Vision Fund layoffs amid AI strategy shift", "type": "incident", "subtype": "layoffs"}
{"name": "US risks losing AI leadership to China", "type": "incident", "subtype": "governance_change"}
{"name": "Citi launches agentic AI pilot program", "type": "event", "subtype": "pilot_program"}
{"name": "OpenAI CEO discusses quantum computing partnership", "type": "event", "subtype": "partnership_mou"}
{"name": "Eric Schmidt warns about AI competitiveness", "type": "expertise", "subtype": "expert_warning"}
{"name": "Inside Tony Blair Institute AI strategy discussions", "type": "informed_insider", "subtype": "private_meeting"}
{"name": "Growing enterprise adoption of agentic AI", "type": "trend_signal", "subtype": "adoption_trend"}
{"name": "SoftBank shifts focus from consumer to enterprise AI", "type": "strategic_shift", "subtype": "strategic_realignment"}
{"name": "SoftBank Vision Fund", "type": "entity", "subtype": "company"}
{"name": "Eric Schmidt", "type": "entity", "subtype": "person"}
{"name": "Tony Blair Institute", "type": "entity", "subtype": "research_institution"}`;

const DEFAULT_ANALYSIS_INSTRUCTIONS = `Focus on extracting actionable intelligence from news articles. Prioritize:

1. Material business impacts and strategic changes (layoffs, restructuring, major funding changes)
2. Regulatory actions and compliance issues (government policies, regulatory warnings)
3. Security incidents and data breaches (cybersecurity events, data leaks)
4. Significant funding, M&A, or operational changes (acquisitions, major investments, closures)
5. Technology launches and competitive developments (new products, platform launches, AI model releases)
6. Leadership changes and strategic pivots (CEO changes, strategic direction shifts)
7. Market warnings and competitive threats (expert warnings, competitive analysis)

Classification Guidelines:
- INCIDENT: Events requiring immediate attention or response (layoffs, breaches, regulatory actions, major failures)
- EVENT: Significant announcements and developments (product launches, funding rounds, partnerships, strategic initiatives)
- ENTITY: Organizations, people, or products being tracked (companies mentioned, key executives, new technologies)

Be inclusive rather than restrictive - if an article discusses something newsworthy, classify it appropriately.`;

const DEFAULT_QUALITY_GUIDELINES = `Credibility Assessment:
- High credibility: Major news outlets, verified sources, multiple independent confirmations
- Mixed credibility: Single source reporting, unverified claims, industry blogs
- Low credibility: Social media rumors, fringe sources, extraordinary claims without evidence

Extraordinary Claims Protocol:
- Flag claims that seem too good to be true or represent major breakthroughs
- Require independent verification for significant technical achievements
- Down-rank significance for self-reported successes without third-party validation`;

const DEFAULT_OUTPUT_FORMAT = `Output must be a valid JSON array with each incident object containing all required fields.
Ensure proper JSON escaping of quotes and special characters.
Do not include any explanatory text outside the JSON array.`;

const DEFAULT_PROFILE_CONTEXT_TEMPLATE = `ORGANIZATIONAL CONTEXT:
Organization: {profile_name} ({organization_type} in {industry})
Region: {region}
Risk Tolerance: {risk_tolerance} | Innovation Appetite: {innovation_appetite}
Decision Making: {decision_making_style}

Key Concerns: {key_concerns}
Strategic Priorities: {strategic_priorities}
Key Stakeholders: {stakeholder_focus}
Competitive Landscape: {competitive_landscape}
Regulatory Environment: {regulatory_environment}

Custom Context: {custom_context}

ANALYSIS INSTRUCTIONS:
- Prioritize incidents and events that align with the organization's key concerns and strategic priorities
- Assess significance based on the organization's risk tolerance and decision-making style
- Consider impact on key stakeholders and competitive positioning
- Account for relevant regulatory and compliance implications
- Tailor investigation leads to organizational context and priorities`;

const DEFAULT_CONFIG: IncidentConfig = {
  system_prompt: DEFAULT_SYSTEM_PROMPT,
  user_prompt: DEFAULT_USER_PROMPT,
  base_ontology: DEFAULT_BASE_ONTOLOGY,
  domain_key: '',
  domain_overlay: '',
  ontology_examples: DEFAULT_ONTOLOGY_EXAMPLES,
  analysis_instructions: DEFAULT_ANALYSIS_INSTRUCTIONS,
  quality_guidelines: DEFAULT_QUALITY_GUIDELINES,
  output_format: DEFAULT_OUTPUT_FORMAT,
  profile_context_template: DEFAULT_PROFILE_CONTEXT_TEMPLATE,
  enable_profile_integration: true,
};

export function IncidentConfigModal({ open, onClose }: IncidentConfigModalProps) {
  const [config, setConfig] = useState<IncidentConfig>(DEFAULT_CONFIG);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load config when modal opens
  useEffect(() => {
    if (open) {
      loadConfig();
    }
  }, [open]);

  const loadConfig = async () => {
    setLoading(true);
    setError(null);
    try {
      // Start with defaults
      let mergedConfig = { ...DEFAULT_CONFIG };

      // Try to load from API
      try {
        const apiData = await getIncidentConfig();
        // Merge API data (only non-empty values)
        Object.entries(apiData).forEach(([key, value]) => {
          if (value !== undefined && value !== null && value !== '') {
            (mergedConfig as any)[key] = value;
          }
        });
      } catch (apiErr) {
        console.log('No API config found, checking localStorage');
      }

      // Try to load from localStorage as fallback
      try {
        const saved = localStorage.getItem('incidentTrackingConfig');
        if (saved) {
          const parsed = JSON.parse(saved);
          // Merge localStorage data (only non-empty values)
          Object.entries(parsed).forEach(([key, value]) => {
            if (value !== undefined && value !== null && value !== '') {
              // Map camelCase to snake_case if needed
              const snakeKey = key.replace(/([A-Z])/g, '_$1').toLowerCase();
              if (snakeKey in mergedConfig) {
                (mergedConfig as any)[snakeKey] = value;
              } else if (key in mergedConfig) {
                (mergedConfig as any)[key] = value;
              }
            }
          });
        }
      } catch (localErr) {
        console.log('No localStorage config found');
      }

      setConfig(mergedConfig);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load configuration');
      // Still use defaults on error
      setConfig(DEFAULT_CONFIG);
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      await saveIncidentConfig(config);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save configuration');
    } finally {
      setSaving(false);
    }
  };

  const handleReset = async () => {
    if (!confirm('Reset all configuration to defaults? This cannot be undone.')) {
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const defaults = await resetIncidentConfigToDefaults();
      setConfig(defaults);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to reset configuration');
    } finally {
      setLoading(false);
    }
  };

  const updateField = (field: keyof IncidentConfig, value: string | boolean) => {
    setConfig((prev) => ({ ...prev, [field]: value }));
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="w-auto min-w-[600px] max-w-[95vw] h-[90vh] flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Settings className="w-5 h-5" />
            Configure Incident Tracking
          </DialogTitle>
          <DialogDescription>
            Customize how the AI analyzes articles to identify incidents and narratives
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
              <TabsTrigger value="ontology" className="flex-1 gap-1 text-xs px-2">
                <Network className="w-3.5 h-3.5 shrink-0" />
                <span className="hidden sm:inline">Ontology</span>
              </TabsTrigger>
              <TabsTrigger value="guidance" className="flex-1 gap-1 text-xs px-2">
                <Lightbulb className="w-3.5 h-3.5 shrink-0" />
                <span className="hidden sm:inline">Guidance</span>
              </TabsTrigger>
            </TabsList>

            <div className="mt-4 pr-2">
              {/* Loading State */}
              {loading && (
                <div className="flex items-center justify-center py-12">
                  <div className="text-center">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-pink-500 mx-auto mb-4"></div>
                    <p className="text-gray-700 dark:text-gray-300">Loading configuration...</p>
                  </div>
                </div>
              )}

              {/* Info Tab */}
              <TabsContent value="info" className="space-y-4 mt-0">
                <div className="bg-blue-50 dark:bg-blue-950 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
                  <h4 className="font-semibold text-blue-900 dark:text-blue-100 flex items-center gap-2 mb-2">
                    <Info className="w-4 h-4" />
                    About Incident Tracking Configuration
                  </h4>
                  <p className="text-sm text-blue-800 dark:text-blue-200">
                    This configuration panel controls how the AI analyzes your articles to
                    identify incidents, trends, entities, and emerging narratives.
                  </p>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <InfoCard
                    icon={<MessageSquare className="w-5 h-5 text-blue-500" />}
                    title="System Prompt"
                    description="The core instructions that guide the AI's analysis approach. Defines what the AI should look for and how it should structure findings."
                    useCase="Change what types of incidents are detected or how they're categorized."
                  />
                  <InfoCard
                    icon={<Network className="w-5 h-5 text-green-500" />}
                    title="Ontology"
                    description="Defines the vocabulary, entity types, and relationships the AI should recognize. Think of it as teaching the AI your domain's language."
                    useCase="Add domain-specific terminology or specialized entities."
                  />
                  <InfoCard
                    icon={<Lightbulb className="w-5 h-5 text-amber-500" />}
                    title="AI Guidance"
                    description="Additional instructions and examples that refine the AI's behavior. Helps improve accuracy and consistency."
                    useCase="Fine-tuning analysis quality or providing domain-specific examples."
                  />
                  <InfoCard
                    icon={<Settings className="w-5 h-5 text-purple-500" />}
                    title="Organizational Profile"
                    description="Context about your organization, industry, and strategic priorities. Helps the AI provide relevant analysis."
                    useCase="Get analysis tailored to your organization's context."
                  />
                </div>

                <div className="bg-amber-50 dark:bg-amber-950 border border-amber-200 dark:border-amber-800 rounded-lg p-4">
                  <h4 className="font-semibold text-amber-900 dark:text-amber-100 mb-2">Important Notes</h4>
                  <ul className="text-sm text-amber-800 dark:text-amber-200 space-y-1 list-disc list-inside">
                    <li>Changes affect all future analyses, not existing results</li>
                    <li>Use template variables like {'{topic}'}, {'{ontology_text}'} for dynamic prompts</li>
                    <li>Test changes with a small dataset first</li>
                    <li>You can reset to defaults using the button below</li>
                  </ul>
                </div>
              </TabsContent>

              {/* System Prompt Tab */}
              <TabsContent value="prompt" className="space-y-4 mt-0 overflow-x-hidden">
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                  <div className="lg:col-span-2 space-y-4 min-w-0">
                    <div>
                      <Label className="font-semibold">System Prompt Template</Label>
                      <p className="text-sm text-gray-700 dark:text-gray-300 mb-2">
                        Customize the system prompt used for incident tracking analysis.
                        Use {'{topic}'} and {'{ontology_text}'} as placeholders.
                      </p>
                      <Textarea
                        value={config.system_prompt || ''}
                        onChange={(e) => updateField('system_prompt', e.target.value)}
                        rows={12}
                        className="font-mono text-xs w-full resize-y"
                        style={{ wordBreak: 'break-word', overflowWrap: 'break-word' }}
                        disabled={loading}
                      />
                    </div>

                    <div>
                      <Label className="font-semibold">User Prompt Template</Label>
                      <p className="text-sm text-gray-700 dark:text-gray-300 mb-2">
                        Customize how articles are presented to the AI.
                      </p>
                      <Textarea
                        value={config.user_prompt || ''}
                        onChange={(e) => updateField('user_prompt', e.target.value)}
                        rows={3}
                        className="font-mono text-xs w-full resize-y"
                        style={{ wordBreak: 'break-word', overflowWrap: 'break-word' }}
                        disabled={loading}
                      />
                    </div>

                    <div>
                      <Label className="font-semibold">Profile Context Template</Label>
                      <p className="text-sm text-gray-700 dark:text-gray-300 mb-2">
                        Configure how organizational profiles are integrated.
                      </p>
                      <Textarea
                        value={config.profile_context_template || ''}
                        onChange={(e) => updateField('profile_context_template', e.target.value)}
                        rows={4}
                        className="font-mono text-xs w-full resize-y"
                        style={{ wordBreak: 'break-word', overflowWrap: 'break-word' }}
                        disabled={loading}
                      />
                      <div className="flex items-center gap-2 mt-2">
                        <Checkbox
                          id="enable-profile"
                          checked={config.enable_profile_integration !== false}
                          onCheckedChange={(checked) =>
                            updateField('enable_profile_integration', checked === true)
                          }
                        />
                        <label htmlFor="enable-profile" className="text-sm text-gray-600">
                          Enable organizational profile integration
                        </label>
                      </div>
                    </div>
                  </div>

                  <div className="space-y-4">
                    <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-4">
                      <h4 className="font-semibold text-gray-900 dark:text-gray-100 mb-3 flex items-center gap-2">
                        <Info className="w-4 h-4" />
                        Available Placeholders
                      </h4>
                      <div className="space-y-2 text-sm">
                        <PlaceholderItem name="{topic}" desc="Current analysis topic (raw)" />
                        <PlaceholderItem name="{topic_label}" desc="Dynamic label based on topic/org (e.g., 'AI and Machine Learning', 'Publishing news')" />
                        <PlaceholderItem name="{topic_focus}" desc="Dynamic focus from org profile priorities or topic-specific interests" />
                        <PlaceholderItem name="{ontology_text}" desc="Generated ontology guidance" />
                        <PlaceholderItem name="{articles_text}" desc="Formatted article content" />
                        <PlaceholderItem name="{profile_context}" desc="Organizational profile context" />
                        <PlaceholderItem name="{analysis_instructions}" desc="AI analysis instructions" />
                        <PlaceholderItem name="{quality_guidelines}" desc="Quality control guidelines" />
                      </div>
                    </div>

                  </div>
                </div>
              </TabsContent>

              {/* Ontology Tab */}
              <TabsContent value="ontology" className="space-y-4 mt-0 overflow-x-hidden">
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                  <div className="lg:col-span-2 space-y-4 min-w-0">
                    <div>
                      <Label className="font-semibold">Base Ontology</Label>
                      <p className="text-sm text-gray-700 dark:text-gray-300 mb-2">
                        Define the types, subtypes, and classification rules.
                      </p>
                      <Textarea
                        value={config.base_ontology || ''}
                        onChange={(e) => updateField('base_ontology', e.target.value)}
                        rows={12}
                        className="font-mono text-xs w-full resize-y"
                        style={{ wordBreak: 'break-word', overflowWrap: 'break-word' }}
                        disabled={loading}
                      />
                    </div>

                    <div>
                      <Label className="font-semibold">Domain Key</Label>
                      <p className="text-sm text-gray-700 dark:text-gray-300 mb-2">
                        Use 'vanilla' for no domain-specific overlay.
                      </p>
                      <Input
                        value={config.domain_key || ''}
                        onChange={(e) => updateField('domain_key', e.target.value)}
                        placeholder="e.g., scientific_publisher, finance, healthcare"
                        disabled={loading}
                      />
                    </div>

                    <div>
                      <Label className="font-semibold">Domain Overlay</Label>
                      <Textarea
                        value={config.domain_overlay || ''}
                        onChange={(e) => updateField('domain_overlay', e.target.value)}
                        rows={6}
                        className="font-mono text-xs w-full resize-y"
                        style={{ wordBreak: 'break-word', overflowWrap: 'break-word' }}
                        placeholder="Domain-specific rules and examples..."
                        disabled={loading}
                      />
                    </div>

                    <div>
                      <Label className="font-semibold">Classification Examples</Label>
                      <Textarea
                        value={config.ontology_examples || ''}
                        onChange={(e) => updateField('ontology_examples', e.target.value)}
                        rows={4}
                        className="font-mono text-xs w-full resize-y"
                        style={{ wordBreak: 'break-word', overflowWrap: 'break-word' }}
                        disabled={loading}
                      />
                    </div>
                  </div>

                  <div className="space-y-4 min-w-0">
                    <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-4">
                      <h4 className="font-semibold text-gray-900 dark:text-gray-100 mb-3 flex items-center gap-2">
                        <Network className="w-4 h-4" />
                        7-Type Classification
                      </h4>
                      <div className="space-y-2 text-sm">
                        <TypeItem type="incident" desc="Disruptive occurrences requiring response" />
                        <TypeItem type="event" desc="Noteworthy developments and announcements" />
                        <TypeItem type="entity" desc="Organizations, people, products tracked" />
                        <TypeItem type="expertise" desc="Expert analysis and authoritative insights" />
                        <TypeItem type="informed_insider" desc="Insider perspectives and leaks" />
                        <TypeItem type="trend_signal" desc="Market trends and behavioral shifts" />
                        <TypeItem type="strategic_shift" desc="Major strategic and policy changes" />
                      </div>
                    </div>

                    <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-4">
                      <h4 className="font-semibold text-gray-900 dark:text-gray-100 mb-3">Required Fields</h4>
                      <ul className="text-sm text-gray-600 dark:text-gray-600 dark:text-gray-600 dark:text-gray-400 space-y-1 list-disc list-inside">
                        <li>name, type, subtype</li>
                        <li>description, timeline</li>
                        <li>significance, plausibility</li>
                        <li>investigation_leads</li>
                        <li>source_quality, misinfo_flags</li>
                      </ul>
                    </div>
                  </div>
                </div>
              </TabsContent>

              {/* AI Guidance Tab */}
              <TabsContent value="guidance" className="space-y-4 mt-0 overflow-x-hidden">
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                  <div className="lg:col-span-2 space-y-4 min-w-0">
                    <div>
                      <Label className="font-semibold">Analysis Instructions</Label>
                      <p className="text-sm text-gray-700 dark:text-gray-300 mb-2">
                        Specific instructions for how the AI should analyze articles.
                      </p>
                      <Textarea
                        value={config.analysis_instructions || ''}
                        onChange={(e) => updateField('analysis_instructions', e.target.value)}
                        rows={8}
                        className="font-mono text-xs w-full resize-y"
                        style={{ wordBreak: 'break-word', overflowWrap: 'break-word' }}
                        placeholder="Specific instructions for analysis behavior..."
                        disabled={loading}
                      />
                    </div>

                    <div>
                      <Label className="font-semibold">Quality Control Guidelines</Label>
                      <p className="text-sm text-gray-700 dark:text-gray-300 mb-2">
                        Guidelines for credibility, extraordinary claims, source quality.
                      </p>
                      <Textarea
                        value={config.quality_guidelines || ''}
                        onChange={(e) => updateField('quality_guidelines', e.target.value)}
                        rows={6}
                        className="font-mono text-xs w-full resize-y"
                        style={{ wordBreak: 'break-word', overflowWrap: 'break-word' }}
                        placeholder="Guidelines for quality control..."
                        disabled={loading}
                      />
                    </div>

                    <div>
                      <Label className="font-semibold">Output Format Requirements</Label>
                      <p className="text-sm text-gray-700 dark:text-gray-300 mb-2">
                        Specific JSON structure and formatting requirements.
                      </p>
                      <Textarea
                        value={config.output_format || ''}
                        onChange={(e) => updateField('output_format', e.target.value)}
                        rows={4}
                        className="font-mono text-xs w-full resize-y"
                        style={{ wordBreak: 'break-word', overflowWrap: 'break-word' }}
                        placeholder="Output format requirements..."
                        disabled={loading}
                      />
                    </div>
                  </div>

                  <div className="space-y-4 min-w-0">
                    <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-4">
                      <h4 className="font-semibold text-gray-900 dark:text-gray-100 mb-3 flex items-center gap-2">
                        <Lightbulb className="w-4 h-4 text-amber-500" />
                        Best Practices
                      </h4>
                      <div className="space-y-3 text-sm">
                        <div>
                          <p className="font-medium text-gray-700 dark:text-gray-200">Analysis Quality:</p>
                          <ul className="text-gray-600 dark:text-gray-600 dark:text-gray-600 dark:text-gray-400 list-disc list-inside mt-1 space-y-0.5">
                            <li>Be specific about credibility assessment</li>
                            <li>Include source quality indicators</li>
                            <li>Flag extraordinary claims</li>
                            <li>Provide investigation leads</li>
                            <li>Be inclusive rather than restrictive</li>
                          </ul>
                        </div>
                        <div>
                          <p className="font-medium text-gray-700 dark:text-gray-200">Profile Context:</p>
                          <ul className="text-gray-600 dark:text-gray-600 dark:text-gray-600 dark:text-gray-400 list-disc list-inside mt-1 space-y-0.5">
                            <li>Consider organizational priorities</li>
                            <li>Align with risk tolerance</li>
                            <li>Focus on relevant stakeholders</li>
                            <li>Account for industry context</li>
                          </ul>
                        </div>
                      </div>
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

function InfoCard({
  icon,
  title,
  description,
  useCase,
}: {
  icon: React.ReactNode;
  title: string;
  description: string;
  useCase: string;
}) {
  return (
    <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-4">
      <div className="flex items-center gap-2 mb-2">
        {icon}
        <h4 className="font-semibold text-gray-900 dark:text-gray-100">{title}</h4>
      </div>
      <p className="text-sm text-gray-600 dark:text-gray-600 dark:text-gray-600 dark:text-gray-400 mb-2">{description}</p>
      <p className="text-xs text-gray-700 dark:text-gray-300 dark:text-gray-600 dark:text-gray-600 dark:text-gray-400">
        <span className="font-medium">Use this when:</span> {useCase}
      </p>
    </div>
  );
}

function PlaceholderItem({ name, desc }: { name: string; desc: string }) {
  return (
    <div>
      <code className="text-pink-600 dark:text-pink-400 bg-pink-50 dark:bg-pink-950 px-1 py-0.5 rounded text-xs">{name}</code>
      <p className="text-gray-700 dark:text-gray-300 dark:text-gray-600 dark:text-gray-400 text-xs mt-0.5">{desc}</p>
    </div>
  );
}

function TypeItem({ type, desc }: { type: string; desc: string }) {
  return (
    <div>
      <code className="text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-950 px-1 py-0.5 rounded text-xs">{type}</code>
      <p className="text-gray-700 dark:text-gray-300 dark:text-gray-600 dark:text-gray-400 text-xs mt-0.5">{desc}</p>
    </div>
  );
}
