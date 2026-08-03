/**
 * Add/Edit Agent Modal
 * Modal for creating or editing research agents with action configuration
 */

import { useState, useEffect } from 'react';
import { useModules } from '../../hooks/useModules';
import { Bot, Loader2, X, Bell, FileText, Workflow, Info, Tag, ChevronDown, ChevronRight, Pencil, Cpu, Search, Mail, MessageCircle, Mic, Star, Clock } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '../ui/dialog';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Textarea } from '../ui/textarea';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../ui/select';
import { Switch } from '../ui/switch';
import { Checkbox } from '../ui/checkbox';
import { type CreateAgentRequest, type ResearchAgent } from '../../services/researchAgentsApi';
import { getAvailableModels } from '../../services/newsFeedApi';

interface Voice {
  voice_id: string;
  name: string;
  category?: string;
  description?: string;
}

interface AddAgentModalProps {
  open: boolean;
  onClose: () => void;
  onSave: (agent: CreateAgentRequest) => Promise<boolean>;
  topics?: string[];
  loading?: boolean;
  /** If provided, modal will be in edit mode */
  editAgent?: ResearchAgent | null;
}

const DEFAULT_REPORT_PROMPT = `Analyze the following signal matches and create a comprehensive intelligence report.

## Your Task
1. Summarize the key findings across all matched articles
2. Identify common themes and patterns
3. Assess the overall significance and urgency
4. Note any gaps or areas requiring further investigation

Format your response as a structured markdown report with clear sections.`;

const DEFAULT_PODCAST_PROMPT = `Create a podcast-style audio script summarizing these intelligence findings. Write it as if you're a host delivering a briefing to listeners.

## Requirements
1. Start with a brief, engaging intro (e.g., "Welcome to today's intelligence briefing...")
2. Summarize the most important findings in conversational, easy-to-follow language
3. Highlight threat levels and urgency where relevant
4. Connect related stories if patterns emerge
5. End with key takeaways and recommended actions
6. Keep the tone professional but accessible
7. Target length: 2-3 minutes when read aloud (approximately 400-500 words)`;

export function AddAgentModal({
  open,
  onClose,
  onSave,
  topics = [],
  loading = false,
  editAgent = null,
}: AddAgentModalProps) {
  // Dedicated Brand Watcher tenants: agents must target a Brand Monitoring topic
  const { dedicatedMode } = useModules();
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [instruction, setInstruction] = useState('');
  const [topic, setTopic] = useState<string>('');
  const [model, setModel] = useState<string>('');
  const [isActive, setIsActive] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [availableModels, setAvailableModels] = useState<Array<{ id: string; name: string; provider: string }>>([]);
  const [loadingModels, setLoadingModels] = useState(false);

  // Actions configuration
  const [actionNotify, setActionNotify] = useState(true);
  const [actionTagArticles, setActionTagArticles] = useState(true);
  const [actionStarArticles, setActionStarArticles] = useState(false);
  const [actionReport, setActionReport] = useState(false);
  const [reportPrompt, setReportPrompt] = useState(DEFAULT_REPORT_PROMPT);
  const [showReportPrompt, setShowReportPrompt] = useState(false);
  const [includeRecommendations, setIncludeRecommendations] = useState(false);
  const [actionDeepResearch, setActionDeepResearch] = useState(false);
  const [actionSendEmail, setActionSendEmail] = useState(false);
  const [emailRecipient, setEmailRecipient] = useState('');
  const [attachPdfReport, setAttachPdfReport] = useState(false);
  const [showEmailConfig, setShowEmailConfig] = useState(false);
  const [actionBlueskyDm, setActionBlueskyDm] = useState(false);
  const [blueskyRecipient, setBlueskyRecipient] = useState('');
  const [showBlueskyConfig, setShowBlueskyConfig] = useState(false);
  const [actionWorkflow, setActionWorkflow] = useState(false);
  const [actionPodcast, setActionPodcast] = useState(false);
  const [podcastPrompt, setPodcastPrompt] = useState(DEFAULT_PODCAST_PROMPT);
  const [showPodcastPrompt, setShowPodcastPrompt] = useState(false);
  const [podcastVoices, setPodcastVoices] = useState<Voice[]>([]);
  const [selectedPodcastVoice, setSelectedPodcastVoice] = useState<string>('');
  const [loadingVoices, setLoadingVoices] = useState(false);
  const [entitiesToMonitor, setEntitiesToMonitor] = useState('');
  const [entitiesPlaceholder, setEntitiesPlaceholder] = useState('Enter company names, people, or brands to monitor (one per line or comma-separated)');
  const [searchStrategy, setSearchStrategy] = useState<'recent' | 'chunked' | 'semantic'>('recent');
  const [maxArticles, setMaxArticles] = useState<number>(100);
  const [alertThreshold, setAlertThreshold] = useState<number>(1);

  // Scheduling state
  const [scheduleEnabled, setScheduleEnabled] = useState(false);
  const [scheduleType, setScheduleType] = useState<'interval' | 'daily'>('interval');
  const [scheduleInterval, setScheduleInterval] = useState<number>(24);
  const [scheduleUnit, setScheduleUnit] = useState<'minutes' | 'hours' | 'days'>('hours');
  const [scheduleTime, setScheduleTime] = useState<string>('09:00');
  const [scheduleDaysBack, setScheduleDaysBack] = useState<number>(7);

  const isEditMode = !!editAgent;

  // Load available models when modal opens
  useEffect(() => {
    if (open && availableModels.length === 0 && !loadingModels) {
      setLoadingModels(true);
      getAvailableModels()
        .then(models => setAvailableModels(models))
        .catch(() => setAvailableModels([]))
        .finally(() => setLoadingModels(false));
    }
  }, [open, availableModels.length, loadingModels]);

  // Load available voices when podcast is enabled
  useEffect(() => {
    if (open && actionPodcast && podcastVoices.length === 0 && !loadingVoices) {
      setLoadingVoices(true);
      fetch('/api/available_voices', { credentials: 'include' })
        .then(res => res.ok ? res.json() : [])
        .then((voices: Voice[]) => {
          setPodcastVoices(voices);
          // Set default voice if not already set
          if (!selectedPodcastVoice && voices.length > 0) {
            const defaultVoice = voices.find(v => v.category === 'premade') || voices[0];
            setSelectedPodcastVoice(defaultVoice.voice_id);
          }
        })
        .catch(() => setPodcastVoices([]))
        .finally(() => setLoadingVoices(false));
    }
  }, [open, actionPodcast, podcastVoices.length, loadingVoices, selectedPodcastVoice]);

  // Populate form when editing
  useEffect(() => {
    if (editAgent && open) {
      setName(editAgent.name || '');
      setDescription(editAgent.description || '');
      setInstruction(editAgent.instruction || '');
      setTopic(editAgent.topic || '');
      // Extract settings from config if present
      const configModel = editAgent.config?.model as string | undefined;
      const configDeepResearch = editAgent.config?.deep_research as boolean | undefined;
      const configSendEmail = editAgent.config?.send_email as boolean | undefined;
      const configEmailRecipient = editAgent.config?.email_recipient as string | undefined;
      const configBlueskyDm = editAgent.config?.bluesky_dm as boolean | undefined;
      const configBlueskyRecipient = editAgent.config?.bluesky_recipient as string | undefined;
      const configEntities = editAgent.config?.entities_to_monitor as string[] | undefined;
      const configSearchStrategy = editAgent.config?.search_strategy as 'recent' | 'chunked' | 'semantic' | undefined;
      const configMaxArticles = editAgent.config?.max_articles as number | undefined;
      const configAlertThreshold = editAgent.config?.alert_threshold as number | undefined;
      const configPodcast = editAgent.config?.generate_podcast as boolean | undefined;
      const configPodcastPrompt = editAgent.config?.podcast_prompt as string | undefined;
      const configPodcastVoice = editAgent.config?.podcast_voice_id as string | undefined;
      const configStarArticles = editAgent.config?.star_flagged_articles as boolean | undefined;
      setModel(configModel || '');
      setActionStarArticles(configStarArticles || false);
      setActionPodcast(configPodcast || false);
      setPodcastPrompt(configPodcastPrompt || DEFAULT_PODCAST_PROMPT);
      setShowPodcastPrompt(configPodcast || false);
      if (configPodcastVoice) {
        setSelectedPodcastVoice(configPodcastVoice);
      }
      setEntitiesToMonitor(configEntities?.join('\n') || '');
      setSearchStrategy(configSearchStrategy || 'recent');
      setMaxArticles(configMaxArticles || 100);
      setAlertThreshold(configAlertThreshold || 1);
      setActionDeepResearch(configDeepResearch || false);
      setActionSendEmail(configSendEmail || false);
      setEmailRecipient(configEmailRecipient || '');
      setAttachPdfReport((editAgent.config?.attach_pdf_report as boolean | undefined) || false);
      setIncludeRecommendations((editAgent.config?.include_recommendations as boolean | undefined) || false);
      setShowEmailConfig(configSendEmail || false);
      setActionBlueskyDm(configBlueskyDm || false);
      setBlueskyRecipient(configBlueskyRecipient || '');
      setShowBlueskyConfig(configBlueskyDm || false);
      setIsActive(editAgent.is_active !== false);
      setActionReport(editAgent.generate_report || false);
      setReportPrompt(editAgent.report_prompt || DEFAULT_REPORT_PROMPT);
      setShowReportPrompt(editAgent.generate_report || false);
      // Scheduling fields
      setScheduleEnabled(editAgent.schedule_enabled || false);
      setScheduleType((editAgent.schedule_type as 'interval' | 'daily') || 'interval');
      setScheduleInterval(editAgent.schedule_interval || 24);
      setScheduleUnit((editAgent.schedule_unit as 'minutes' | 'hours' | 'days') || 'hours');
      setScheduleTime(editAgent.schedule_time || '09:00');
      const configDaysBack = editAgent.config?.days_back as number | undefined;
      setScheduleDaysBack(configDaysBack || 7);
      setError(null);
    }
  }, [editAgent, open]);

  const resetForm = () => {
    setName('');
    setDescription('');
    setInstruction('');
    setTopic('');
    setModel('');
    setIsActive(true);
    setActionNotify(true);
    setActionTagArticles(true);
    setActionStarArticles(false);
    setActionReport(false);
    setReportPrompt(DEFAULT_REPORT_PROMPT);
    setShowReportPrompt(false);
    setActionDeepResearch(false);
    setActionSendEmail(false);
    setEmailRecipient('');
    setShowEmailConfig(false);
    setActionBlueskyDm(false);
    setBlueskyRecipient('');
    setShowBlueskyConfig(false);
    setActionWorkflow(false);
    setActionPodcast(false);
    setPodcastPrompt(DEFAULT_PODCAST_PROMPT);
    setShowPodcastPrompt(false);
    setSelectedPodcastVoice('');
    setEntitiesToMonitor('');
    setEntitiesPlaceholder('Enter company names, people, or brands to monitor (one per line or comma-separated)');
    setSearchStrategy('recent');
    setMaxArticles(100);
    setAlertThreshold(1);
    // Scheduling fields
    setScheduleEnabled(false);
    setScheduleType('interval');
    setScheduleInterval(24);
    setScheduleUnit('hours');
    setScheduleTime('09:00');
    setScheduleDaysBack(7);
    setError(null);
  };

  const handleClose = () => {
    if (!isEditMode) {
      resetForm();
    }
    onClose();
  };

  const handleSave = async () => {
    // Validation
    if (!name.trim()) {
      setError('Agent name is required');
      return;
    }
    if (!instruction.trim()) {
      setError('Research instruction is required');
      return;
    }
    if (dedicatedMode === true && !topic.startsWith('Brand Monitoring')) {
      setError('Agents on this tenant report on brand data only — choose a brand topic');
      return;
    }

    setSaving(true);
    setError(null);

    try {
      // Build config object with all action settings
      const config: Record<string, unknown> = {};
      if (model) config.model = model;
      // Always save days_back for scheduled runs
      config.days_back = scheduleDaysBack;
      if (includeRecommendations) config.include_recommendations = true;
      if (actionStarArticles) config.star_flagged_articles = true;
      if (actionDeepResearch) config.deep_research = true;
      if (actionSendEmail) {
        config.send_email = true;
        if (emailRecipient.trim()) config.email_recipient = emailRecipient.trim();
        if (attachPdfReport) config.attach_pdf_report = true;
      }
      if (actionBlueskyDm) {
        config.bluesky_dm = true;
        if (blueskyRecipient.trim()) config.bluesky_recipient = blueskyRecipient.trim();
      }
      if (entitiesToMonitor.trim()) {
        // Parse comma or newline separated entities
        const entities = entitiesToMonitor
          .split(/[,\n]/)
          .map(e => e.trim())
          .filter(e => e.length > 0);
        if (entities.length > 0) {
          config.entities_to_monitor = entities;
        }
      }
      // Search strategy and limits
      if (searchStrategy !== 'recent') {
        config.search_strategy = searchStrategy;
      }
      if (maxArticles !== 100) {
        config.max_articles = maxArticles;
      }
      if (alertThreshold !== 1) {
        config.alert_threshold = alertThreshold;
      }
      if (actionPodcast) {
        config.generate_podcast = true;
        // Only save custom prompt if it differs from default
        if (podcastPrompt.trim() && podcastPrompt.trim() !== DEFAULT_PODCAST_PROMPT.trim()) {
          config.podcast_prompt = podcastPrompt.trim();
        }
        // Save selected voice
        if (selectedPodcastVoice) {
          config.podcast_voice_id = selectedPodcastVoice;
        }
      }

      const success = await onSave({
        name: name.trim(),
        description: description.trim(),
        instruction: instruction.trim(),
        topic: topic || null,
        is_active: isActive,
        generate_report: actionReport,
        report_prompt: actionReport ? reportPrompt.trim() : null,
        config: Object.keys(config).length > 0 ? config : null,
        // Scheduling fields
        schedule_enabled: scheduleEnabled,
        schedule_type: scheduleEnabled ? scheduleType : null,
        schedule_interval: scheduleEnabled && scheduleType === 'interval' ? scheduleInterval : null,
        schedule_unit: scheduleEnabled && scheduleType === 'interval' ? scheduleUnit : null,
        schedule_time: scheduleEnabled && scheduleType === 'daily' ? scheduleTime : null,
      });

      if (success) {
        resetForm();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save agent');
    } finally {
      setSaving(false);
    }
  };

  const exampleInstructions = [
    {
      name: 'Executive Mentions',
      instruction: 'Flag any articles that mention C-level executives (CEO, CTO, CFO, etc.) making announcements, policy changes, or strategic decisions. Focus on direct quotes and business-critical information. Explain why each match is relevant to executive leadership.',
    },
    {
      name: 'Regulatory Changes',
      instruction: 'Identify articles discussing new regulations, policy changes, government actions, or compliance requirements that could impact business operations. For each match, explain the specific regulatory change and its potential business impact.',
    },
    {
      name: 'Competitive Intelligence',
      instruction: 'Monitor for articles about competitor activities including product launches, partnerships, acquisitions, market expansion, or strategic shifts. Explain how each finding relates to competitive positioning.',
    },
    {
      name: 'Emerging Threats',
      instruction: 'Watch for emerging security threats, vulnerabilities, data breaches, or cyber attacks. Rate the severity (high/medium/low) and explain the potential impact and affected systems.',
    },
    {
      name: 'Adverse Media Screening',
      instruction: 'Screen for negative news coverage including fraud allegations, corruption, sanctions violations, money laundering, bribery, criminal activity, lawsuits, regulatory fines, environmental violations, or reputational damage. Flag any mentions of individuals or organizations under investigation or facing legal action. Rate risk level (high/medium/low) and summarize the specific adverse finding.',
      entities: 'Enter company names, individuals, or organizations to screen',
    },
    {
      name: 'Brand Monitoring',
      instruction: 'Monitor brand mentions across news coverage including product reviews, customer complaints, PR crises, social media controversies, executive scandals, product recalls, or service outages. Track sentiment (positive/negative/neutral) and identify potential reputation risks or opportunities. Flag any coverage that could impact brand perception or require a response.',
      entities: 'Enter your brand name and any related brands to monitor',
    },
    {
      name: 'Competitor Monitoring',
      instruction: 'Track competitor news including new product launches, pricing changes, market expansion, executive hires, funding rounds, partnerships, M&A activity, patent filings, and strategic announcements. Identify competitive threats and opportunities. Summarize how each development could impact market position or require a strategic response.',
      entities: 'Enter competitor company names to track',
    },
  ];

  const applyExample = (example: { name: string; instruction: string; entities?: string }) => {
    setName(example.name);
    setInstruction(example.instruction);
    if (example.entities) {
      setEntitiesPlaceholder(example.entities);
      setEntitiesToMonitor(''); // Clear any existing value so placeholder shows
    }
    setError(null);
  };

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[600px] max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {isEditMode ? (
              <Pencil className="w-5 h-5 text-pink-500" />
            ) : (
              <Bot className="w-5 h-5 text-pink-500" />
            )}
            {isEditMode ? 'Edit Observer Agent' : 'Create Observer Agent'}
          </DialogTitle>
          <DialogDescription>
            {isEditMode
              ? 'Update the agent configuration and save your changes.'
              : 'Create an AI agent to automatically monitor articles and take action when matches are found.'}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          {/* Error Display */}
          {error && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-3 flex items-center justify-between">
              <span className="text-sm text-red-800">{error}</span>
              <button onClick={() => setError(null)} className="text-red-600 hover:text-red-800">
                <X className="w-4 h-4" />
              </button>
            </div>
          )}

          {/* Agent Name */}
          <div className="space-y-2">
            <Label htmlFor="agent-name">Agent Name *</Label>
            <Input
              id="agent-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g., Executive Announcements Monitor"
              disabled={saving || loading}
            />
          </div>

          {/* Description */}
          <div className="space-y-2">
            <Label htmlFor="agent-description">Description</Label>
            <Input
              id="agent-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Brief description of what this agent monitors"
              disabled={saving || loading}
            />
          </div>

          {/* Topic Filter */}
          <div className="space-y-2">
            <Label htmlFor="agent-topic">Topic Filter</Label>
            <Select value={topic || '__all__'} onValueChange={(val) => setTopic(val === '__all__' ? '' : val)} disabled={saving || loading}>
              <SelectTrigger>
                <SelectValue placeholder={dedicatedMode === true ? 'Choose a brand topic' : 'All Topics (Global)'} />
              </SelectTrigger>
              <SelectContent>
                {dedicatedMode !== true && (
                  <SelectItem value="__all__">All Topics (Global)</SelectItem>
                )}
                {topics.map((t) => (
                  <SelectItem key={t} value={t}>
                    {t}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-gray-700 dark:text-gray-300">
              {dedicatedMode === true
                ? 'Agents on this tenant report on brand data only — pick which brand this agent watches'
                : 'Optionally limit this agent to articles from a specific topic'}
            </p>
          </div>

          {/* Model Selection */}
          <div className="space-y-2">
            <Label htmlFor="agent-model" className="flex items-center gap-2">
              <Cpu className="w-4 h-4 text-purple-500" />
              AI Model
            </Label>
            <Select
              value={model || '__default__'}
              onValueChange={(val) => setModel(val === '__default__' ? '' : val)}
              disabled={saving || loading || loadingModels}
            >
              <SelectTrigger>
                <SelectValue placeholder={loadingModels ? "Loading models..." : "Default (gpt-5.4-mini)"} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__default__">Default (gpt-5.4-mini)</SelectItem>
                {/* An existing agent can hold a model that is no longer offered;
                    keep it listed so editing the agent does not change it. */}
                {model && !availableModels.some(m => m.id === model) && (
                  <SelectItem value={model}>{model}</SelectItem>
                )}
                {availableModels.map((m) => (
                  <SelectItem key={m.id} value={m.id}>
                    {m.name} ({m.provider})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-gray-700 dark:text-gray-300">
              Select the AI model to use for analyzing articles
            </p>
          </div>

          {/* Quick Start Templates */}
          <div className="space-y-2">
            <Label className="text-gray-700 dark:text-gray-300">Quick Start Templates</Label>
            <div className="flex flex-wrap gap-2">
              {exampleInstructions.map((example) => (
                <button
                  key={example.name}
                  onClick={() => applyExample(example)}
                  className="px-2 py-1 text-xs bg-gray-100 hover:bg-gray-200 rounded-md text-gray-700 transition-colors"
                  disabled={saving || loading}
                >
                  {example.name}
                </button>
              ))}
            </div>
          </div>

          {/* Instruction */}
          <div className="space-y-2">
            <Label htmlFor="agent-instruction">Research Instruction *</Label>
            <Textarea
              id="agent-instruction"
              value={instruction}
              onChange={(e) => setInstruction(e.target.value)}
              placeholder="Describe what this agent should look for in articles. Be specific about the types of content, entities, or events to flag. Include instructions for explaining why matches are relevant."
              rows={4}
              disabled={saving || loading}
            />
            <p className="text-xs text-gray-700 dark:text-gray-300">
              The AI will follow these instructions when analyzing articles and explain why each match is relevant
            </p>
          </div>

          {/* Entities to Monitor */}
          <div className="space-y-2">
            <Label htmlFor="agent-entities">Entities to Monitor</Label>
            <Textarea
              id="agent-entities"
              value={entitiesToMonitor}
              onChange={(e) => setEntitiesToMonitor(e.target.value)}
              placeholder={entitiesPlaceholder}
              rows={3}
              disabled={saving || loading}
            />
            <p className="text-xs text-gray-700 dark:text-gray-300">
              Specific entities mentioned here will be prioritized in article matching
            </p>
          </div>

          {/* Search Strategy & Limits */}
          <div className="space-y-4 pt-4 border-t">
            <div className="flex items-center gap-2">
              <Label className="text-base font-medium">Search Strategy & Limits</Label>
            </div>

            <div className="grid grid-cols-2 gap-4">
              {/* Search Strategy */}
              <div className="space-y-2">
                <Label htmlFor="search-strategy">Search Strategy</Label>
                <Select
                  value={searchStrategy}
                  onValueChange={(val) => setSearchStrategy(val as 'recent' | 'chunked' | 'semantic')}
                  disabled={saving || loading}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="recent">Recent Articles (Fast)</SelectItem>
                    <SelectItem value="chunked">Chunked Processing (Thorough)</SelectItem>
                    <SelectItem value="semantic">Semantic Search (Precise)</SelectItem>
                  </SelectContent>
                </Select>
                <p className="text-xs text-gray-700 dark:text-gray-300">
                  {searchStrategy === 'recent' && 'Analyzes the most recent articles only'}
                  {searchStrategy === 'chunked' && 'Processes all articles in batches'}
                  {searchStrategy === 'semantic' && 'Uses vector search to find relevant articles first'}
                </p>
              </div>

              {/* Max Articles */}
              <div className="space-y-2">
                <Label htmlFor="max-articles">Max Articles</Label>
                <Input
                  id="max-articles"
                  type="number"
                  min={10}
                  max={1000}
                  value={maxArticles}
                  onChange={(e) => setMaxArticles(Math.min(1000, Math.max(10, parseInt(e.target.value) || 100)))}
                  disabled={saving || loading}
                />
                <p className="text-xs text-gray-700 dark:text-gray-300">
                  Maximum articles to analyze (10-1000)
                </p>
              </div>
            </div>

            {/* Alert Threshold */}
            <div className="space-y-2">
              <Label htmlFor="alert-threshold">Alert Threshold</Label>
              <div className="flex items-center gap-2">
                <Input
                  id="alert-threshold"
                  type="number"
                  min={1}
                  max={100}
                  value={alertThreshold}
                  onChange={(e) => setAlertThreshold(Math.min(100, Math.max(1, parseInt(e.target.value) || 1)))}
                  disabled={saving || loading}
                  className="w-24"
                />
                <span className="text-sm text-gray-600">matches to trigger alert actions</span>
              </div>
              <p className="text-xs text-gray-700 dark:text-gray-300">
                Email/DM notifications only sent when this many matches are found
              </p>
            </div>
          </div>

          {/* Actions Section */}
          <div className="space-y-3 pt-4 border-t">
            <div className="flex items-center gap-2">
              <Label className="text-base font-medium">When Matches Are Found</Label>
            </div>
            <p className="text-sm text-gray-700 dark:text-gray-300 -mt-1">
              Configure what happens when the agent finds matching articles
            </p>

            <div className="space-y-3">
              {/* Notify Action */}
              <label className="flex items-start gap-3 p-3 rounded-lg border border-gray-200 cursor-pointer hover:bg-gray-50">
                <Checkbox
                  checked={actionNotify}
                  onCheckedChange={(checked) => setActionNotify(checked as boolean)}
                  disabled={saving || loading}
                />
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <Bell className="w-4 h-4 text-pink-500" />
                    <span className="font-medium text-gray-900">Add Notification</span>
                  </div>
                  <p className="text-sm text-gray-700 dark:text-gray-300 mt-0.5">
                    Add alerts to the notification bell for review
                  </p>
                </div>
              </label>

              {/* Tag Articles Action */}
              <label className="flex items-start gap-3 p-3 rounded-lg border border-gray-200 cursor-pointer hover:bg-gray-50">
                <Checkbox
                  checked={actionTagArticles}
                  onCheckedChange={(checked) => setActionTagArticles(checked as boolean)}
                  disabled={saving || loading}
                />
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <Tag className="w-4 h-4 text-green-500" />
                    <span className="font-medium text-gray-900">Tag Matching Articles</span>
                  </div>
                  <p className="text-sm text-gray-700 dark:text-gray-300 mt-0.5">
                    Add a "SIGNAL_{'{'}agent_name{'}'}" tag to matched articles for filtering
                  </p>
                </div>
              </label>

              {/* Star Articles Action */}
              <label className="flex items-start gap-3 p-3 rounded-lg border border-gray-200 cursor-pointer hover:bg-gray-50">
                <Checkbox
                  checked={actionStarArticles}
                  onCheckedChange={(checked) => setActionStarArticles(checked as boolean)}
                  disabled={saving || loading}
                />
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <Star className="w-4 h-4 text-yellow-500" />
                    <span className="font-medium text-gray-900">Star Matching Articles</span>
                  </div>
                  <p className="text-sm text-gray-700 dark:text-gray-300 mt-0.5">
                    Add matched articles to your starred collection
                  </p>
                </div>
              </label>

              {/* Report Action - Now Enabled */}
              <div className="rounded-lg border border-gray-200">
                <label className="flex items-start gap-3 p-3 cursor-pointer hover:bg-gray-50">
                  <Checkbox
                    checked={actionReport}
                    onCheckedChange={(checked) => {
                      setActionReport(checked as boolean);
                      if (checked) {
                        setShowReportPrompt(true);
                      }
                    }}
                    disabled={saving || loading}
                  />
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <FileText className="w-4 h-4 text-blue-500" />
                      <span className="font-medium text-gray-900">Generate Report</span>
                    </div>
                    <p className="text-sm text-gray-700 dark:text-gray-300 mt-0.5">
                      Automatically generate a summary report when matches are found
                    </p>
                  </div>
                </label>

                {/* Report Prompt Editor */}
                {actionReport && (
                  <div className="border-t border-gray-200">
                    <button
                      type="button"
                      onClick={() => setShowReportPrompt(!showReportPrompt)}
                      className="w-full flex items-center gap-2 p-3 text-sm text-gray-600 hover:bg-gray-50"
                    >
                      {showReportPrompt ? (
                        <ChevronDown className="w-4 h-4" />
                      ) : (
                        <ChevronRight className="w-4 h-4" />
                      )}
                      <span>Customize Report Prompt</span>
                    </button>

                    {showReportPrompt && (
                      <div className="p-3 pt-0 space-y-2">
                        <Textarea
                          value={reportPrompt}
                          onChange={(e) => setReportPrompt(e.target.value)}
                          placeholder="Enter custom instructions for report generation..."
                          rows={6}
                          disabled={saving || loading}
                          className="font-mono text-sm"
                        />
                        <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300 cursor-pointer"
                          title="Off by default: reports state findings, themes and significance only. Turn on to add a 'Recommendations & guidance' section scoped to your organization's remit.">
                          <input type="checkbox" checked={includeRecommendations}
                            onChange={(e) => setIncludeRecommendations(e.target.checked)}
                            disabled={saving || loading} />
                          Include recommendations &amp; guidance
                        </label>
                        <div className="flex justify-between items-center">
                          <p className="text-xs text-gray-600 dark:text-gray-300">
                            This prompt tells the AI how to analyze and summarize matched articles
                          </p>
                          <button
                            type="button"
                            onClick={() => setReportPrompt(DEFAULT_REPORT_PROMPT)}
                            className="text-xs text-blue-600 hover:text-blue-700"
                            disabled={saving || loading}
                          >
                            Reset to default
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* Generate Podcast Summary */}
              <div className="rounded-lg border border-gray-200">
                <label className="flex items-start gap-3 p-3 cursor-pointer hover:bg-gray-50">
                  <Checkbox
                    checked={actionPodcast}
                    onCheckedChange={(checked) => {
                      setActionPodcast(checked as boolean);
                      if (checked) {
                        setShowPodcastPrompt(true);
                      }
                    }}
                    disabled={saving || loading}
                  />
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <Mic className="w-4 h-4 text-purple-500" />
                      <span className="font-medium text-gray-900">Generate Podcast Summary</span>
                    </div>
                    <p className="text-sm text-gray-700 dark:text-gray-300 mt-0.5">
                      Create an audio-friendly narrative summary of matches for podcast-style delivery
                    </p>
                  </div>
                </label>

                {/* Podcast Voice & Prompt Settings */}
                {actionPodcast && (
                  <div className="border-t border-gray-200">
                    {/* Voice Selector */}
                    <div className="p-3 space-y-2">
                      <Label htmlFor="podcast-voice" className="text-sm font-medium">Podcast Voice</Label>
                      <Select
                        value={selectedPodcastVoice}
                        onValueChange={setSelectedPodcastVoice}
                        disabled={saving || loading || loadingVoices}
                      >
                        <SelectTrigger id="podcast-voice">
                          <SelectValue placeholder={loadingVoices ? "Loading voices..." : "Select a voice"} />
                        </SelectTrigger>
                        <SelectContent>
                          {podcastVoices.map((voice) => (
                            <SelectItem key={voice.voice_id} value={voice.voice_id}>
                              <div className="flex items-center gap-2">
                                <span>{voice.name}</span>
                                {voice.category && (
                                  <span className="text-xs text-gray-600 dark:text-gray-300">({voice.category})</span>
                                )}
                              </div>
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <p className="text-xs text-gray-600 dark:text-gray-300">
                        Select the voice to use when generating audio from the podcast summary
                      </p>
                    </div>

                    {/* Customize Prompt Toggle */}
                    <button
                      type="button"
                      onClick={() => setShowPodcastPrompt(!showPodcastPrompt)}
                      className="w-full flex items-center gap-2 p-3 text-sm text-gray-600 hover:bg-gray-50 border-t border-gray-300 dark:border-gray-700"
                    >
                      {showPodcastPrompt ? (
                        <ChevronDown className="w-4 h-4" />
                      ) : (
                        <ChevronRight className="w-4 h-4" />
                      )}
                      <span>Customize Podcast Prompt</span>
                    </button>

                    {showPodcastPrompt && (
                      <div className="p-3 pt-0 space-y-2">
                        <Textarea
                          value={podcastPrompt}
                          onChange={(e) => setPodcastPrompt(e.target.value)}
                          placeholder="Enter custom instructions for podcast summary generation..."
                          rows={6}
                          disabled={saving || loading}
                          className="font-mono text-sm"
                        />
                        <div className="flex justify-between items-center">
                          <p className="text-xs text-gray-600 dark:text-gray-300">
                            This prompt tells the AI how to create an audio-friendly summary
                          </p>
                          <button
                            type="button"
                            onClick={() => setPodcastPrompt(DEFAULT_PODCAST_PROMPT)}
                            className="text-xs text-purple-600 hover:text-purple-700"
                            disabled={saving || loading}
                          >
                            Reset to default
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* Deep Research Action */}
              <label className="flex items-start gap-3 p-3 rounded-lg border border-gray-200 cursor-pointer hover:bg-gray-50">
                <Checkbox
                  checked={actionDeepResearch}
                  onCheckedChange={(checked) => setActionDeepResearch(checked as boolean)}
                  disabled={saving || loading}
                />
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <Search className="w-4 h-4 text-orange-500" />
                    <span className="font-medium text-gray-900">Deep Research</span>
                  </div>
                  <p className="text-sm text-gray-700 dark:text-gray-300 mt-0.5">
                    Trigger a deep research process to gather additional related articles from the dataset
                  </p>
                </div>
              </label>

              {/* Send Email Action */}
              <div className="rounded-lg border border-gray-200">
                <label className="flex items-start gap-3 p-3 cursor-pointer hover:bg-gray-50">
                  <Checkbox
                    checked={actionSendEmail}
                    onCheckedChange={(checked) => {
                      setActionSendEmail(checked as boolean);
                      if (checked) {
                        setShowEmailConfig(true);
                      }
                    }}
                    disabled={saving || loading}
                  />
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <Mail className="w-4 h-4 text-cyan-500" />
                      <span className="font-medium text-gray-900">Send Email</span>
                    </div>
                    <p className="text-sm text-gray-700 dark:text-gray-300 mt-0.5">
                      Send an email notification when matches are found
                    </p>
                  </div>
                </label>

                {/* Email Configuration */}
                {actionSendEmail && (
                  <div className="border-t border-gray-200">
                    <button
                      type="button"
                      onClick={() => setShowEmailConfig(!showEmailConfig)}
                      className="w-full flex items-center gap-2 p-3 text-sm text-gray-600 hover:bg-gray-50"
                    >
                      {showEmailConfig ? (
                        <ChevronDown className="w-4 h-4" />
                      ) : (
                        <ChevronRight className="w-4 h-4" />
                      )}
                      <span>Configure Email Recipient</span>
                    </button>

                    {showEmailConfig && (
                      <div className="p-3 pt-0 space-y-2">
                        <Input
                          value={emailRecipient}
                          onChange={(e) => setEmailRecipient(e.target.value)}
                          placeholder="recipient@example.com"
                          type="email"
                          disabled={saving || loading}
                        />
                        <p className="text-xs text-gray-600 dark:text-gray-300">
                          Leave blank to use the default notification email
                        </p>
                        <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300 cursor-pointer"
                          title="Also attach the generated report to the email as a PDF file. Emails always carry a no-login download link; the attachment makes the report readable offline and forwardable.">
                          <input type="checkbox" checked={attachPdfReport}
                            onChange={(e) => setAttachPdfReport(e.target.checked)}
                            disabled={saving || loading} />
                          Attach report as PDF
                        </label>
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* Bluesky DM Action */}
              <div className="rounded-lg border border-gray-200">
                <label className="flex items-start gap-3 p-3 cursor-pointer hover:bg-gray-50">
                  <Checkbox
                    checked={actionBlueskyDm}
                    onCheckedChange={(checked) => {
                      setActionBlueskyDm(checked as boolean);
                      if (checked) {
                        setShowBlueskyConfig(true);
                      }
                    }}
                    disabled={saving || loading}
                  />
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <MessageCircle className="w-4 h-4 text-sky-500" />
                      <span className="font-medium text-gray-900">Send Bluesky DM</span>
                    </div>
                    <p className="text-sm text-gray-700 dark:text-gray-300 mt-0.5">
                      Send a direct message on Bluesky when matches are found
                    </p>
                  </div>
                </label>

                {/* Bluesky Configuration */}
                {actionBlueskyDm && (
                  <div className="border-t border-gray-200">
                    <button
                      type="button"
                      onClick={() => setShowBlueskyConfig(!showBlueskyConfig)}
                      className="w-full flex items-center gap-2 p-3 text-sm text-gray-600 hover:bg-gray-50"
                    >
                      {showBlueskyConfig ? (
                        <ChevronDown className="w-4 h-4" />
                      ) : (
                        <ChevronRight className="w-4 h-4" />
                      )}
                      <span>Configure Bluesky Recipient</span>
                    </button>

                    {showBlueskyConfig && (
                      <div className="p-3 pt-0 space-y-2">
                        <Input
                          value={blueskyRecipient}
                          onChange={(e) => setBlueskyRecipient(e.target.value)}
                          placeholder="@username or username.bsky.social"
                          disabled={saving || loading}
                        />
                        <p className="text-xs text-gray-600 dark:text-gray-300">
                          Bluesky handle to receive DM alerts
                        </p>
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* Workflow Action */}
              <label className="flex items-start gap-3 p-3 rounded-lg border border-gray-200 cursor-pointer hover:bg-gray-50 opacity-60">
                <Checkbox
                  checked={actionWorkflow}
                  onCheckedChange={(checked) => setActionWorkflow(checked as boolean)}
                  disabled={true}
                />
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <Workflow className="w-4 h-4 text-purple-500" />
                    <span className="font-medium text-gray-900">Trigger Workflow</span>
                    <span className="text-xs text-gray-600 dark:text-gray-300 bg-gray-100 px-1.5 py-0.5 rounded">Soon</span>
                  </div>
                  <p className="text-sm text-gray-700 dark:text-gray-300 mt-0.5">
                    Execute a custom workflow (e.g., send to Slack, create task)
                  </p>
                </div>
              </label>
            </div>
          </div>

          {/* Active Toggle */}
          <div className="flex items-start justify-between py-3 border-t">
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <Label htmlFor="agent-active" className="font-medium">Active Status</Label>
                <div className="group relative">
                  <Info className="w-4 h-4 text-gray-600 dark:text-gray-300 cursor-help" />
                  <div className="absolute bottom-full left-0 mb-2 w-64 p-2 bg-gray-900 text-white text-xs rounded-lg opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-10">
                    Active agents will be included when you click "Run All". Paused agents can still be run individually.
                  </div>
                </div>
              </div>
              <p className="text-sm text-gray-700 dark:text-gray-300">
                {isActive
                  ? 'Agent will run when "Run All" is clicked'
                  : 'Agent is paused and must be run manually'
                }
              </p>
            </div>
            <Switch
              id="agent-active"
              checked={isActive}
              onCheckedChange={setIsActive}
              disabled={saving || loading}
            />
          </div>

          {/* Scheduling Section */}
          <div className="space-y-4 pt-4 border-t">
            <div className="flex items-start justify-between">
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <Clock className="w-4 h-4 text-pink-500" />
                  <Label htmlFor="schedule-enabled" className="font-medium">Scheduled Execution</Label>
                </div>
                <p className="text-sm text-gray-700 dark:text-gray-300">
                  {scheduleEnabled
                    ? 'Agent will run automatically on schedule'
                    : 'Enable to run this agent on a schedule'
                  }
                </p>
              </div>
              <Switch
                id="schedule-enabled"
                checked={scheduleEnabled}
                onCheckedChange={setScheduleEnabled}
                disabled={saving || loading}
              />
            </div>

            {/* Schedule Configuration - only show when enabled */}
            {scheduleEnabled && (
              <div className="space-y-4 pl-6 border-l-2 border-pink-200">
                {/* Schedule Type */}
                <div className="space-y-2">
                  <Label>Schedule Type</Label>
                  <Select
                    value={scheduleType}
                    onValueChange={(val) => setScheduleType(val as 'interval' | 'daily')}
                    disabled={saving || loading}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="interval">Run at Interval</SelectItem>
                      <SelectItem value="daily">Run Daily at Specific Time</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                {/* Interval Configuration */}
                {scheduleType === 'interval' && (
                  <div className="space-y-2">
                    <Label>Run Every</Label>
                    <div className="flex items-center gap-2">
                      <Input
                        type="number"
                        min={1}
                        max={scheduleUnit === 'minutes' ? 1440 : scheduleUnit === 'hours' ? 168 : 30}
                        value={scheduleInterval}
                        onChange={(e) => setScheduleInterval(Math.max(1, parseInt(e.target.value) || 1))}
                        disabled={saving || loading}
                        className="w-24"
                      />
                      <Select
                        value={scheduleUnit}
                        onValueChange={(val) => setScheduleUnit(val as 'minutes' | 'hours' | 'days')}
                        disabled={saving || loading}
                      >
                        <SelectTrigger className="w-32">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="minutes">Minutes</SelectItem>
                          <SelectItem value="hours">Hours</SelectItem>
                          <SelectItem value="days">Days</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <p className="text-xs text-gray-700 dark:text-gray-300">
                      Agent will run every {scheduleInterval} {scheduleUnit}
                    </p>
                  </div>
                )}

                {/* Daily Time Configuration */}
                {scheduleType === 'daily' && (
                  <div className="space-y-2">
                    <Label>Run at Time</Label>
                    <Input
                      type="time"
                      value={scheduleTime}
                      onChange={(e) => setScheduleTime(e.target.value)}
                      disabled={saving || loading}
                      className="w-40"
                    />
                    <p className="text-xs text-gray-700 dark:text-gray-300">
                      Agent will run daily at {scheduleTime} (server time)
                    </p>
                  </div>
                )}

                {/* Days Back - Article Timeframe */}
                <div className="space-y-2">
                  <Label>Article Timeframe</Label>
                  <Select
                    value={scheduleDaysBack.toString()}
                    onValueChange={(val) => setScheduleDaysBack(parseInt(val))}
                    disabled={saving || loading}
                  >
                    <SelectTrigger className="w-48">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="1">Last 24 hours</SelectItem>
                      <SelectItem value="3">Last 3 days</SelectItem>
                      <SelectItem value="7">Last 7 days</SelectItem>
                      <SelectItem value="14">Last 2 weeks</SelectItem>
                      <SelectItem value="30">Last 30 days</SelectItem>
                    </SelectContent>
                  </Select>
                  <p className="text-xs text-gray-700 dark:text-gray-300">
                    Analyze articles from the last {scheduleDaysBack} day{scheduleDaysBack !== 1 ? 's' : ''} on each run
                  </p>
                </div>

                {/* Email Notification for Scheduled Runs */}
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <Label>Email Notification</Label>
                    <Switch
                      checked={actionSendEmail}
                      onCheckedChange={(checked) => {
                        setActionSendEmail(checked);
                        setShowEmailConfig(checked);
                      }}
                      disabled={saving || loading}
                    />
                  </div>
                  {actionSendEmail && (
                    <div className="space-y-2">
                      <Input
                        value={emailRecipient}
                        onChange={(e) => setEmailRecipient(e.target.value)}
                        placeholder="recipient@example.com"
                        type="email"
                        disabled={saving || loading}
                      />
                      <p className="text-xs text-gray-700 dark:text-gray-300">
                        Receive email alerts when matches are found during scheduled runs
                      </p>
                    </div>
                  )}
                </div>

                {/* Next Run Preview */}
                {isEditMode && editAgent?.next_run_at && (
                  <div className="p-3 bg-gray-50 rounded-lg">
                    <p className="text-xs font-medium text-gray-700 dark:text-gray-300">Next Scheduled Run</p>
                    <p className="text-sm text-gray-700">
                      {new Date(editAgent.next_run_at).toLocaleString()}
                    </p>
                    {editAgent.last_run_at && (
                      <>
                        <p className="text-xs font-medium text-gray-700 dark:text-gray-300 mt-2">Last Run</p>
                        <p className="text-sm text-gray-700">
                          {new Date(editAgent.last_run_at).toLocaleString()}
                          {editAgent.last_run_status && (
                            <span className={`ml-2 px-1.5 py-0.5 text-xs rounded ${
                              editAgent.last_run_status === 'success'
                                ? 'bg-green-100 text-green-700'
                                : editAgent.last_run_status === 'error'
                                ? 'bg-red-100 text-red-700'
                                : 'bg-yellow-100 text-yellow-700'
                            }`}>
                              {editAgent.last_run_status}
                            </span>
                          )}
                        </p>
                      </>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-2 pt-4 border-t">
          <Button variant="outline" onClick={handleClose} disabled={saving}>
            Cancel
          </Button>
          <Button
            onClick={handleSave}
            disabled={saving || loading || !name.trim() || !instruction.trim()}
            className="bg-pink-500 hover:bg-pink-600"
          >
            {saving ? (
              <>
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                {isEditMode ? 'Saving...' : 'Creating...'}
              </>
            ) : (
              <>
                {isEditMode ? <Pencil className="w-4 h-4 mr-2" /> : <Bot className="w-4 h-4 mr-2" />}
                {isEditMode ? 'Save Changes' : 'Create Agent'}
              </>
            )}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
