/**
 * Add/Edit Agent Modal
 * Modal for creating or editing research agents with action configuration
 */

import { useState, useEffect } from 'react';
import { Bot, Loader2, X, Bell, FileText, Workflow, Info, Tag, ChevronDown, ChevronRight, Pencil } from 'lucide-react';
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
4. Provide actionable recommendations
5. Note any gaps or areas requiring further investigation

Format your response as a structured markdown report with clear sections.`;

export function AddAgentModal({
  open,
  onClose,
  onSave,
  topics = [],
  loading = false,
  editAgent = null,
}: AddAgentModalProps) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [instruction, setInstruction] = useState('');
  const [topic, setTopic] = useState<string>('');
  const [isActive, setIsActive] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Actions configuration
  const [actionNotify, setActionNotify] = useState(true);
  const [actionTagArticles, setActionTagArticles] = useState(true);
  const [actionReport, setActionReport] = useState(false);
  const [reportPrompt, setReportPrompt] = useState(DEFAULT_REPORT_PROMPT);
  const [showReportPrompt, setShowReportPrompt] = useState(false);
  const [actionWorkflow, setActionWorkflow] = useState(false);

  const isEditMode = !!editAgent;

  // Populate form when editing
  useEffect(() => {
    if (editAgent && open) {
      setName(editAgent.name || '');
      setDescription(editAgent.description || '');
      setInstruction(editAgent.instruction || '');
      setTopic(editAgent.topic || '');
      setIsActive(editAgent.is_active !== false);
      setActionReport(editAgent.generate_report || false);
      setReportPrompt(editAgent.report_prompt || DEFAULT_REPORT_PROMPT);
      setShowReportPrompt(editAgent.generate_report || false);
      setError(null);
    }
  }, [editAgent, open]);

  const resetForm = () => {
    setName('');
    setDescription('');
    setInstruction('');
    setTopic('');
    setIsActive(true);
    setActionNotify(true);
    setActionTagArticles(true);
    setActionReport(false);
    setReportPrompt(DEFAULT_REPORT_PROMPT);
    setShowReportPrompt(false);
    setActionWorkflow(false);
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

    setSaving(true);
    setError(null);

    try {
      const success = await onSave({
        name: name.trim(),
        description: description.trim(),
        instruction: instruction.trim(),
        topic: topic || null,
        is_active: isActive,
        generate_report: actionReport,
        report_prompt: actionReport ? reportPrompt.trim() : null,
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
  ];

  const applyExample = (example: { name: string; instruction: string }) => {
    setName(example.name);
    setInstruction(example.instruction);
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
            {isEditMode ? 'Edit Research Agent' : 'Create Research Agent'}
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
                <SelectValue placeholder="All Topics (Global)" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__all__">All Topics (Global)</SelectItem>
                {topics.map((t) => (
                  <SelectItem key={t} value={t}>
                    {t}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-gray-500">
              Optionally limit this agent to articles from a specific topic
            </p>
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
            <p className="text-xs text-gray-500">
              The AI will follow these instructions when analyzing articles and explain why each match is relevant
            </p>
          </div>

          {/* Example Instructions */}
          <div className="space-y-2">
            <Label className="text-gray-500">Quick Start Templates</Label>
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

          {/* Actions Section */}
          <div className="space-y-3 pt-4 border-t">
            <div className="flex items-center gap-2">
              <Label className="text-base font-medium">When Matches Are Found</Label>
            </div>
            <p className="text-sm text-gray-500 -mt-1">
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
                  <p className="text-sm text-gray-500 mt-0.5">
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
                  <p className="text-sm text-gray-500 mt-0.5">
                    Add a "SIGNAL_{'{'}agent_name{'}'}" tag to matched articles for filtering
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
                    <p className="text-sm text-gray-500 mt-0.5">
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
                        <div className="flex justify-between items-center">
                          <p className="text-xs text-gray-400">
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
                    <span className="text-xs text-gray-400 bg-gray-100 px-1.5 py-0.5 rounded">Soon</span>
                  </div>
                  <p className="text-sm text-gray-500 mt-0.5">
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
                  <Info className="w-4 h-4 text-gray-400 cursor-help" />
                  <div className="absolute bottom-full left-0 mb-2 w-64 p-2 bg-gray-900 text-white text-xs rounded-lg opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-10">
                    Active agents will be included when you click "Run All". Paused agents can still be run individually.
                  </div>
                </div>
              </div>
              <p className="text-sm text-gray-500">
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
