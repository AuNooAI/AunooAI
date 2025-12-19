/**
 * AuspexChatModal - Main chat modal dialog
 * Fullscreen workbench layout matching the original design
 */

import { useState, useMemo, useEffect, useRef } from 'react';
import * as DialogPrimitive from '@radix-ui/react-dialog';
import * as VisuallyHidden from '@radix-ui/react-visually-hidden';

// Chart data extraction utility
interface ChartData {
  type?: string;
  format?: string;
  chart_type?: string;  // Backend uses this for sentiment_donut, etc.
  title?: string;
  data: any;
  layout?: any;
}

function extractChartsFromContent(content: string): { text: string; charts: ChartData[] } {
  const chartRegex = /<!-- CHART_DATA:([\s\S]*?):END_CHART -->/g;
  const errorRegex = /<!-- CHART_ERROR:([\s\S]*?):END_CHART -->/g;

  const charts: ChartData[] = [];
  let textContent = content;

  // Debug: Log if content contains chart markers
  if (content.includes('CHART_DATA')) {
    console.log('[Chart Extract] Content contains CHART_DATA, length:', content.length);
    console.log('[Chart Extract] Content snippet around marker:', content.substring(content.indexOf('CHART_DATA') - 10, content.indexOf('CHART_DATA') + 200));
  }

  let match;
  while ((match = chartRegex.exec(content)) !== null) {
    console.log('[Chart Extract] Found chart match, JSON length:', match[1].length);
    try {
      const chartData = JSON.parse(match[1]);
      console.log('[Chart Extract] Parsed chart successfully:', chartData.type || 'unknown type');
      charts.push(chartData);
      textContent = textContent.replace(match[0], '');
    } catch (e) {
      console.warn('[Chart Extract] Failed to parse chart JSON:', e, 'JSON preview:', match[1].substring(0, 200));
    }
  }

  // Remove error markers
  textContent = textContent.replace(errorRegex, '');

  console.log('[Chart Extract] Final result: charts found:', charts.length);
  return { text: textContent.trim(), charts };
}
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from '../ui/select';
import {
  Bot,
  Plus,
  Download,
  Wrench,
  Maximize2,
  Minimize2,
  X,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  ChevronDown,
  History,
  MessageSquare,
  Trash2,
  Info,
  BarChart3,
  Sparkles,
  PanelRightClose,
  PanelRightOpen,
  Settings2,
  Eye,
  EyeOff
} from 'lucide-react';
import { cn } from '../ui/utils';
import { AuspexChatMessages } from './AuspexChatMessages';
import { AuspexChatInput, AuspexChatInputHandle } from './AuspexChatInput';
import { AuspexToolsConfig } from './AuspexToolsConfig';
import { InsightsPanel } from './InsightsPanel';
import type { SampleSizeMode, SamplingStrategy, ResearchMode } from '../../hooks/useAuspexChat';
import type { BackendArticleStats } from '../../utils/insightsParser';

interface Topic {
  name: string;
  display_name: string;
}

interface Model {
  id: string;
  name: string;
}

interface ChatSession {
  id: number;
  topic: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count?: number;
}

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  isStreaming?: boolean;
}

interface PluginTool {
  name: string;
  description: string;
}

interface ToolsConfig {
  [key: string]: boolean;
}

interface ContextStats {
  articles: number;
  tokens: number;
  percentage: number;
}

interface AuspexChatModalProps {
  isOpen: boolean;
  onClose: () => void;
  topics: Topic[];
  models: Model[];
  sessions: ChatSession[];
  messages: Message[];
  pluginTools: PluginTool[];
  selectedTopic: string;
  selectedModel: string;
  currentChatId: number | null;
  onTopicChange: (topic: string) => void;
  onModelChange: (model: string) => void;
  sampleSizeMode: SampleSizeMode;
  samplingStrategy: SamplingStrategy;
  customLimit: number;
  toolsConfig: ToolsConfig;
  includeCharts: boolean;
  researchMode: ResearchMode;
  visibleTools: string[];
  toolOrder: string[];
  onSampleSizeModeChange: (mode: SampleSizeMode) => void;
  onSamplingStrategyChange: (strategy: SamplingStrategy) => void;
  onCustomLimitChange: (limit: number) => void;
  onToolsConfigChange: (config: ToolsConfig) => void;
  onIncludeChartsChange: (include: boolean) => void;
  onResearchModeChange: (mode: ResearchMode) => void;
  onVisibleToolsChange: (tools: string[]) => void;
  onToolOrderChange: (order: string[]) => void;
  isLoading: boolean;
  isStreaming: boolean;
  onSendMessage: (text: string) => void;
  onNewChat: () => void;
  onSelectSession: (chatId: number) => void;
  onDeleteSession: (chatId: number) => void;
  onClearAllSessions: () => void;
  onExportChat: () => string;
  contextStats?: ContextStats;
  backendArticleStats?: BackendArticleStats | null;
}

function formatToolName(name: string): string {
  return name.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
}

export function AuspexChatModal({
  isOpen,
  onClose,
  topics,
  models,
  sessions,
  messages,
  pluginTools,
  selectedTopic,
  selectedModel,
  currentChatId,
  onTopicChange,
  onModelChange,
  sampleSizeMode,
  samplingStrategy,
  customLimit,
  toolsConfig,
  includeCharts,
  researchMode,
  visibleTools,
  toolOrder,
  onSampleSizeModeChange,
  onSamplingStrategyChange,
  onCustomLimitChange,
  onToolsConfigChange,
  onIncludeChartsChange,
  onResearchModeChange,
  onVisibleToolsChange,
  onToolOrderChange,
  isLoading,
  isStreaming,
  onSendMessage,
  onNewChat,
  onSelectSession,
  onDeleteSession,
  onClearAllSessions,
  onExportChat,
  contextStats,
  backendArticleStats
}: AuspexChatModalProps) {
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [isRightPanelOpen, setIsRightPanelOpen] = useState(true);
  const [isToolsConfigOpen, setIsToolsConfigOpen] = useState(false);
  const [isToolSettingsOpen, setIsToolSettingsOpen] = useState(false);
  const [rightPanelTab, setRightPanelTab] = useState<'insights' | 'charts'>('insights');
  const [isMinimized, setIsMinimized] = useState(false);
  const chartRefs = useRef<Map<number, HTMLDivElement>>(new Map());
  const inputRef = useRef<AuspexChatInputHandle>(null);

  // Get sorted and filtered tools based on visibility and order
  const displayedTools = useMemo(() => {
    // Filter to only visible tools
    const visible = pluginTools.filter(tool => visibleTools.includes(tool.name));
    // Sort by toolOrder
    return visible.sort((a, b) => {
      const aIndex = toolOrder.indexOf(a.name);
      const bIndex = toolOrder.indexOf(b.name);
      // Tools not in order go to end
      if (aIndex === -1) return 1;
      if (bIndex === -1) return -1;
      return aIndex - bIndex;
    });
  }, [pluginTools, visibleTools, toolOrder]);

  // Helper to toggle tool visibility
  const toggleToolVisibility = (toolName: string) => {
    if (visibleTools.includes(toolName)) {
      onVisibleToolsChange(visibleTools.filter(t => t !== toolName));
    } else {
      onVisibleToolsChange([...visibleTools, toolName]);
    }
  };

  // Helper to move tool up in order
  const moveToolUp = (toolName: string) => {
    const idx = toolOrder.indexOf(toolName);
    if (idx > 0) {
      const newOrder = [...toolOrder];
      [newOrder[idx - 1], newOrder[idx]] = [newOrder[idx], newOrder[idx - 1]];
      onToolOrderChange(newOrder);
    }
  };

  // Helper to move tool down in order
  const moveToolDown = (toolName: string) => {
    const idx = toolOrder.indexOf(toolName);
    if (idx < toolOrder.length - 1) {
      const newOrder = [...toolOrder];
      [newOrder[idx], newOrder[idx + 1]] = [newOrder[idx + 1], newOrder[idx]];
      onToolOrderChange(newOrder);
    }
  };

  // Handle delete with confirmation
  const handleDeleteSession = (chatId: number) => {
    if (window.confirm('Are you sure you want to delete this chat? This cannot be undone.')) {
      onDeleteSession(chatId);
    }
  };

  // Handle clear all with confirmation
  const handleClearAllSessions = () => {
    if (sessions.length === 0) return;
    if (window.confirm(`Are you sure you want to delete all ${sessions.length} chat sessions? This cannot be undone.`)) {
      onClearAllSessions();
    }
  };

  // Default context stats if not provided
  const stats = contextStats || { articles: 0, tokens: 0, percentage: 0 };

  // Process messages to extract charts and clean text
  const { processedMessages, allCharts } = useMemo(() => {
    const processed = messages.map(msg => {
      if (msg.role === 'assistant') {
        // Debug: Check if content contains chart markers
        const hasChartMarker = msg.content.includes('<!-- CHART_DATA:');
        if (hasChartMarker) {
          console.log('[Auspex] Found CHART_DATA marker in message');
          console.log('[Auspex] Content preview:', msg.content.substring(0, 500));
        }
        const { text, charts } = extractChartsFromContent(msg.content);
        if (charts.length > 0) {
          console.log('[Auspex] Extracted charts:', charts.length, charts);
        }
        return { ...msg, content: text, charts };
      }
      return { ...msg, charts: [] as ChartData[] };
    });

    // Collect all charts from all messages
    const charts = processed.flatMap((msg, idx) =>
      (msg.charts || []).map((chart, chartIdx) => ({
        ...chart,
        messageIndex: idx,
        chartIndex: chartIdx,
        id: `chart-${idx}-${chartIdx}`
      }))
    );

    console.log('[Auspex] Total charts found:', charts.length);
    return { processedMessages: processed, allCharts: charts };
  }, [messages]);

  // Auto-switch to charts tab when new chart arrives
  useEffect(() => {
    if (allCharts.length > 0 && rightPanelTab !== 'charts') {
      setRightPanelTab('charts');
      setIsRightPanelOpen(true);
    }
  }, [allCharts.length]);

  // State to track when chart containers are ready
  const [chartContainersReady, setChartContainersReady] = useState(0);

  // Re-render charts when switching to charts tab
  useEffect(() => {
    if (rightPanelTab === 'charts' && allCharts.length > 0) {
      // Clear existing refs and trigger re-render
      chartRefs.current.clear();
      setChartContainersReady(prev => prev + 1);
    }
  }, [rightPanelTab, allCharts.length]);

  // Render charts using Plotly - delayed to ensure DOM is ready
  useEffect(() => {
    if (typeof window !== 'undefined' && (window as any).Plotly && allCharts.length > 0 && rightPanelTab === 'charts') {
      // Small delay to ensure refs are set after JSX renders
      const timeoutId = setTimeout(() => {
        console.log('[Auspex] Rendering charts:', allCharts.length);
        allCharts.forEach((chart) => {
          const containerKey = chart.messageIndex * 100 + chart.chartIndex;
          const container = chartRefs.current.get(containerKey);
          console.log('[Auspex] Chart container for key', containerKey, ':', container ? 'found' : 'NOT FOUND');

          if (container && chart.data) {
            try {
              let plotlyData: any[];
              let plotlyLayout: any;

              // Vibrant sentiment colors (case-insensitive lookup)
              const SENTIMENT_COLORS: Record<string, string> = {
                'positive': '#22c55e',   // Green
                'negative': '#ef4444',   // Red
                'neutral': '#94a3b8',    // Slate gray
                'mixed': '#f59e0b',      // Amber
                'critical': '#f97316',   // Orange
                'hyperbolic': '#3b82f6', // Blue
                'unknown': '#6b7280',    // Gray
              };

              const getColor = (label: string | null | undefined) =>
                label ? (SENTIMENT_COLORS[label.toLowerCase()] || '#6b7280') : '#6b7280';

              // Vibrant color palette for charts
              const CHART_COLORS = [
                '#3b82f6', // Blue
                '#22c55e', // Green
                '#f59e0b', // Amber
                '#ef4444', // Red
                '#8b5cf6', // Purple
                '#ec4899', // Pink
                '#14b8a6', // Teal
                '#f97316', // Orange
                '#6366f1', // Indigo
                '#84cc16', // Lime
              ];

              // Helper to enhance pie chart with consistent styling
              const enhancePieChart = (labels: (string | null)[], values: number[], title: string) => {
                // Normalize labels - replace null/undefined with 'Unknown'
                const normalizedLabels = labels.map(l => l || 'Unknown');

                // Check if labels are sentiment-related (use sentiment colors) or general (use chart colors)
                const isSentimentChart = normalizedLabels.some(l =>
                  ['positive', 'negative', 'neutral', 'mixed', 'critical'].includes(l.toLowerCase())
                );

                const colors = isSentimentChart
                  ? normalizedLabels.map(getColor)
                  : normalizedLabels.map((_, i) => CHART_COLORS[i % CHART_COLORS.length]);

                const total = values.reduce((a, b) => a + b, 0);
                const legendLabels = normalizedLabels.map((label, i) => {
                  const pct = ((values[i] / total) * 100).toFixed(1);
                  return `${label} (${pct}%)`;
                });

                return {
                  data: [{
                    type: 'pie',
                    labels: legendLabels,
                    values: values,
                    marker: { colors },
                    hole: 0.4,
                    textinfo: 'none',
                    hovertemplate: '<b>%{label}</b><br>Count: %{value}<extra></extra>'
                  }],
                  layout: {
                    title: { text: title, font: { size: 11 }, y: 0.98, x: 0.5, xanchor: 'center' },
                    showlegend: true,
                    legend: { orientation: 'h', yanchor: 'top', y: -0.05, xanchor: 'center', x: 0.5, font: { size: 9 } }
                  }
                };
              };

              // Helper to enhance bar charts with colorful styling
              const enhanceBarChart = (trace: any, title: string) => {
                const isHorizontal = trace.orientation === 'h';
                const values = isHorizontal ? trace.x : trace.y;
                const labels = isHorizontal ? trace.y : trace.x;
                const numBars = values?.length || 0;

                // Generate colors for each bar
                const colors = Array.from({ length: numBars }, (_, i) => CHART_COLORS[i % CHART_COLORS.length]);

                // Calculate left margin based on longest label
                let leftMargin = 20;
                if (isHorizontal && labels) {
                  const maxLabelLength = Math.max(...labels.map((l: any) => (l || '').toString().length));
                  leftMargin = Math.min(Math.max(maxLabelLength * 7, 100), 200);
                }

                return {
                  data: [{
                    ...trace,
                    marker: { color: colors }
                  }],
                  layout: {
                    title: { text: title, font: { size: 11 }, y: 0.98, x: 0.5, xanchor: 'center' },
                    margin: { t: 40, r: 20, b: 40, l: leftMargin },
                    yaxis: isHorizontal ? { autorange: 'reversed', tickfont: { size: 9 } } : {},
                    xaxis: { tickfont: { size: 9 } }
                  }
                };
              };

              // Extract data based on format
              let rawData: any[] = [];
              let rawLayout: any = {};
              const chartTitle = chart.title || chart.layout?.title || chart.data?.layout?.title || 'Chart';

              // Format 1: deep_research format (direct data.labels/values)
              if (chart.data?.labels && chart.data?.values) {
                const enhanced = enhancePieChart(chart.data.labels, chart.data.values, chartTitle);
                plotlyData = enhanced.data;
                plotlyLayout = enhanced.layout;
              }
              // Format 2: Nested Plotly JSON (data.data array)
              else if (chart.data?.data && Array.isArray(chart.data.data)) {
                rawData = chart.data.data;
                rawLayout = chart.data.layout || {};

                // Check chart type and enhance accordingly
                const firstTrace = rawData[0];
                if (firstTrace?.type === 'pie' && firstTrace?.labels && firstTrace?.values) {
                  const enhanced = enhancePieChart(firstTrace.labels, firstTrace.values, chartTitle);
                  plotlyData = enhanced.data;
                  plotlyLayout = enhanced.layout;
                } else if (firstTrace?.type === 'bar') {
                  const enhanced = enhanceBarChart(firstTrace, chartTitle);
                  plotlyData = enhanced.data;
                  plotlyLayout = { ...rawLayout, ...enhanced.layout };
                } else {
                  plotlyData = rawData;
                  plotlyLayout = rawLayout;
                }
              }
              // Format 3: Direct Plotly data array
              else if (Array.isArray(chart.data)) {
                rawData = chart.data;
                rawLayout = chart.layout || {};

                const firstTrace = rawData[0];
                if (firstTrace?.type === 'pie' && firstTrace?.labels && firstTrace?.values) {
                  const enhanced = enhancePieChart(firstTrace.labels, firstTrace.values, chartTitle);
                  plotlyData = enhanced.data;
                  plotlyLayout = enhanced.layout;
                } else if (firstTrace?.type === 'bar') {
                  const enhanced = enhanceBarChart(firstTrace, chartTitle);
                  plotlyData = enhanced.data;
                  plotlyLayout = { ...rawLayout, ...enhanced.layout };
                } else {
                  plotlyData = rawData;
                  plotlyLayout = rawLayout;
                }
              } else {
                console.warn('[Auspex] Unknown chart format:', chart);
                return;
              }

              // Enhanced layout for better display
              const enhancedLayout = {
                ...plotlyLayout,
                paper_bgcolor: 'transparent',
                plot_bgcolor: 'transparent',
                font: { color: '#6b7280', size: 10 },
                margin: { t: 40, r: 20, b: 60, l: 20, autoexpand: true },
                autosize: true,
                title: typeof plotlyLayout.title === 'string'
                  ? { text: plotlyLayout.title, font: { size: 12, color: '#374151' }, y: 0.95 }
                  : plotlyLayout.title,
                legend: plotlyLayout.legend || {
                  orientation: 'h',
                  yanchor: 'top',
                  y: -0.1,
                  xanchor: 'center',
                  x: 0.5,
                  font: { size: 9 }
                }
              };

              console.log('[Auspex] Calling Plotly.newPlot with:', { plotlyData, enhancedLayout });
              (window as any).Plotly.newPlot(
                container,
                plotlyData,
                enhancedLayout,
                {
                  responsive: true,
                  displayModeBar: 'hover',
                  modeBarButtonsToRemove: ['sendDataToCloud', 'lasso2d', 'select2d', 'autoScale2d'],
                  displaylogo: false
                }
              );
            } catch (e) {
              console.error('[Auspex] Error rendering chart:', e);
            }
          }
        });
      }, 100);  // Small delay for DOM to be ready

      return () => clearTimeout(timeoutId);
    }
  }, [allCharts, chartContainersReady, rightPanelTab]);

  const handleExport = () => {
    const content = onExportChat();
    const blob = new Blob([content], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `auspex-chat-${new Date().toISOString().slice(0, 10)}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const handleToolClick = (tool: PluginTool) => {
    const prompt = `Use the ${tool.name.replace(/_/g, ' ')} tool to analyze the current topic`;
    // Insert into input instead of auto-sending - let user edit/finetune
    inputRef.current?.insertText(prompt);
  };

  const isDisabled = !selectedTopic || !selectedModel;

  return (
    <>
      <DialogPrimitive.Root open={isOpen} onOpenChange={(open) => !open && onClose()}>
        <DialogPrimitive.Portal>
          {/* Hide overlay when minimized */}
          {!isMinimized && <DialogPrimitive.Overlay className="fixed inset-0 z-40 bg-black/50" />}
          <DialogPrimitive.Content
            className={cn(
              "fixed z-50 flex flex-col bg-white dark:bg-gray-900 transition-all duration-300",
              isMinimized
                ? "bottom-4 right-4 w-[500px] h-[600px] rounded-lg shadow-2xl border border-gray-200 dark:border-gray-700"
                : "inset-0"
            )}
            onPointerDownOutside={(e) => isMinimized ? undefined : e.preventDefault()}
            aria-describedby={undefined}
          >
            {/* Visually hidden title for accessibility */}
            <VisuallyHidden.Root>
              <DialogPrimitive.Title>Auspex AI Assistant</DialogPrimitive.Title>
            </VisuallyHidden.Root>

            {/* Header */}
            <div className={cn(
              "flex-shrink-0 border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900",
              isMinimized ? "px-2 py-1" : "px-4 py-2"
            )}>
              <div className="flex items-center justify-between">
              {/* Left: Title */}
              <div className={cn("flex items-center gap-2", isMinimized && "flex-shrink-0")}>
                <Bot className={cn(isMinimized ? "w-4 h-4" : "w-5 h-5", "text-pink-500")} />
                <span className={cn(
                  "font-semibold text-gray-900 dark:text-gray-100",
                  isMinimized ? "text-sm" : "text-base"
                )}>
                  {isMinimized ? "Auspex" : "Auspex AI Assistant"}
                </span>
              </div>

              {/* Center: Controls - simplified when minimized */}
              <div className={cn("flex items-center", isMinimized ? "gap-1" : "gap-3")}>
                {/* Topic selector - always shown but smaller when minimized */}
                <Select value={selectedTopic} onValueChange={onTopicChange}>
                  <SelectTrigger className={cn(
                    "h-8 text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 border-gray-300 dark:border-gray-600 [&>span]:text-gray-900 dark:[&>span]:text-gray-100 [&>span]:truncate [&>span]:max-w-[calc(100%-20px)]",
                    isMinimized ? "w-[120px]" : "w-[180px]"
                  )}>
                    <SelectValue placeholder="Topic..." className="text-gray-900 dark:text-gray-100" />
                  </SelectTrigger>
                  <SelectContent className="max-w-[280px]">
                    <SelectItem value="__all__">All Topics</SelectItem>
                    {topics.map((t) => (
                      <SelectItem key={t.name} value={t.name} className="truncate">{t.display_name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>

                {/* Model selector - always shown but smaller when minimized */}
                <Select value={selectedModel} onValueChange={onModelChange}>
                  <SelectTrigger className={cn(
                    "h-8 text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 border-gray-300 dark:border-gray-600 [&>span]:text-gray-900 dark:[&>span]:text-gray-100",
                    isMinimized ? "w-[100px]" : "w-[180px]"
                  )}>
                    <SelectValue placeholder="Model..." className="text-gray-900 dark:text-gray-100" />
                  </SelectTrigger>
                  <SelectContent>
                    {models.map((m) => (
                      <SelectItem key={m.id} value={m.id}>{m.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>

                {/* Sample size - hidden when minimized */}
                {!isMinimized && (
                <>
                <Select value={sampleSizeMode} onValueChange={onSampleSizeModeChange}>
                  <SelectTrigger className="w-[120px] h-8 text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 border-gray-300 dark:border-gray-600">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="auto">Auto-size</SelectItem>
                    <SelectItem value="balanced">Balanced</SelectItem>
                    <SelectItem value="comprehensive">Comprehensive</SelectItem>
                    <SelectItem value="focused">Focused</SelectItem>
                    <SelectItem value="custom">Custom</SelectItem>
                  </SelectContent>
                </Select>
                {sampleSizeMode === 'custom' && (
                  <input
                    type="number"
                    min="10"
                    max="500"
                    value={customLimit}
                    onChange={(e) => onCustomLimitChange(parseInt(e.target.value) || 50)}
                    className="w-[70px] h-8 px-2 text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 border border-gray-300 dark:border-gray-600 rounded-md"
                    placeholder="50"
                  />
                )}
                </>
                )}

                {/* Sampling strategy - hidden when minimized */}
                {!isMinimized && (
                <Select value={samplingStrategy} onValueChange={onSamplingStrategyChange}>
                  <SelectTrigger className="w-[140px] h-8 text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 border-gray-300 dark:border-gray-600">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="auto">Auto Strategy</SelectItem>
                    <SelectItem value="recency_diversity">Recent + Diverse</SelectItem>
                    <SelectItem value="quality_first">Quality First</SelectItem>
                    <SelectItem value="latest">Latest Only</SelectItem>
                    <SelectItem value="diverse">Max Diversity</SelectItem>
                    <SelectItem value="balanced_topics">Topic Balanced</SelectItem>
                  </SelectContent>
                </Select>
                )}

                {/* Context Badge - hidden when minimized */}
                {!isMinimized && (
                <div
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-50 dark:bg-blue-900/30 rounded border border-blue-200 dark:border-blue-800 cursor-help"
                  title={`Token Breakdown:
• System prompt: ~2,000 tokens
• Articles content: ~${Math.max(0, stats.tokens - 2000).toLocaleString()} tokens
• Total: ~${stats.tokens.toLocaleString()} tokens

Context Usage: ${stats.percentage.toFixed(1)}% of model limit
Model: ${selectedModel || 'Not selected'}
Sample size: ${stats.articles} articles`}
                >
                  <Info className="w-4 h-4 text-blue-500" />
                  <span className="text-sm text-blue-700 dark:text-blue-300 whitespace-nowrap">
                    Context: {stats.articles} articles, ~{stats.tokens.toLocaleString()} tokens ({stats.percentage.toFixed(1)}%)
                  </span>
                </div>
                )}

                {/* Action Icons - fewer when minimized */}
                <div className="flex items-center gap-0.5">
                  {!isMinimized && (
                  <>
                    <button onClick={onNewChat} className="p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded" title="New chat">
                      <Plus className="w-5 h-5 text-gray-600 dark:text-gray-300" />
                    </button>
                    <button onClick={handleExport} disabled={messages.length === 0} className="p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded" title="Export">
                      <Download className="w-5 h-5 text-gray-600 dark:text-gray-300" />
                    </button>
                    <button onClick={() => setIsToolsConfigOpen(true)} className="p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded" title="Tools config">
                      <Wrench className="w-5 h-5 text-gray-600 dark:text-gray-300" />
                    </button>
                  </>
                  )}
                  <button
                    onClick={() => setIsMinimized(!isMinimized)}
                    className="p-1.5 hover:bg-gray-100 dark:hover:bg-gray-800 rounded"
                    title={isMinimized ? "Maximize" : "Minimize"}
                  >
                    {isMinimized ? <Maximize2 className="w-4 h-4 text-gray-600 dark:text-gray-300" /> : <Minimize2 className="w-5 h-5 text-gray-600 dark:text-gray-300" />}
                  </button>
                  <button onClick={onClose} className="p-1.5 hover:bg-gray-100 dark:hover:bg-gray-800 rounded" title="Close">
                    <X className={cn(isMinimized ? "w-4 h-4" : "w-5 h-5", "text-gray-600 dark:text-gray-300")} />
                  </button>
                </div>
              </div>
              </div>
            </div>

            {/* Body */}
            <div className="flex-1 flex overflow-hidden">
              {/* Left Sidebar - hidden when minimized */}
              {!isMinimized && (
              <div className={cn(
                'flex-shrink-0 bg-gray-50 dark:bg-gray-900 border-r border-gray-200 dark:border-gray-700 flex flex-col transition-all duration-300',
                isSidebarOpen ? 'w-56' : 'w-0 overflow-hidden'
              )}>
                {/* Sidebar Header */}
                <div className="flex items-center justify-between p-3 border-b border-gray-200 dark:border-gray-700">
                  <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 flex items-center gap-2">
                    <History className="w-4 h-4" />
                    Chat History
                  </h3>
                  <div className="flex items-center gap-1">
                    {sessions.length > 0 && (
                      <button
                        onClick={handleClearAllSessions}
                        className="p-1 hover:bg-red-100 dark:hover:bg-red-900/30 rounded text-gray-400 hover:text-red-500"
                        title="Clear all chat history"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    )}
                    <button
                      onClick={() => setIsSidebarOpen(false)}
                      className="p-1 hover:bg-gray-200 dark:hover:bg-gray-700 rounded text-gray-500"
                    >
                      <ChevronLeft className="w-4 h-4" />
                    </button>
                  </div>
                </div>

                {/* Sessions */}
                <div className="flex-1 overflow-y-auto p-2">
                  {sessions.length === 0 ? (
                    <div className="text-center py-8 text-gray-400">
                      <MessageSquare className="w-8 h-8 mx-auto mb-2 opacity-50" />
                      <p className="text-sm">No chat history</p>
                      <p className="text-xs mt-1">Select a topic to see chats</p>
                    </div>
                  ) : (
                    <div className="space-y-1">
                      {sessions.map((session) => (
                        <div
                          key={session.id}
                          onClick={() => onSelectSession(session.id)}
                          className={cn(
                            'group relative px-2 py-2 rounded cursor-pointer transition-colors',
                            session.id === currentChatId
                              ? 'bg-pink-100 dark:bg-pink-900/30 border-l-2 border-pink-500'
                              : 'hover:bg-gray-100 dark:hover:bg-gray-800'
                          )}
                        >
                          <p className={cn(
                            'text-sm font-medium truncate pr-5',
                            session.id === currentChatId ? 'text-pink-700 dark:text-pink-300' : 'text-gray-700 dark:text-gray-300'
                          )}>
                            {session.title || `Chat ${session.id}`}
                          </p>
                          <div className="flex items-center gap-1.5 text-xs text-gray-400 mt-0.5">
                            <span>{new Date(session.updated_at || session.created_at).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</span>
                            {session.message_count && (
                              <>
                                <MessageSquare className="w-3 h-3" />
                                <span>{session.message_count}</span>
                              </>
                            )}
                          </div>
                          <button
                            onClick={(e) => { e.stopPropagation(); handleDeleteSession(session.id); }}
                            className="absolute right-1 top-1/2 -translate-y-1/2 p-1 rounded text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/30"
                            title="Delete this chat"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
              )}

              {/* Sidebar collapsed toggle - hidden when minimized */}
              {!isMinimized && !isSidebarOpen && (
                <button
                  onClick={() => setIsSidebarOpen(true)}
                  className="flex-shrink-0 w-6 flex items-center justify-center bg-gray-50 dark:bg-gray-900 border-r border-gray-200 dark:border-gray-700 hover:bg-gray-100 dark:hover:bg-gray-800"
                >
                  <History className="w-4 h-4 text-gray-500" />
                </button>
              )}

              {/* Main Content */}
              <div className="flex-1 flex flex-col min-w-0 bg-white dark:bg-gray-950">
                {/* Messages */}
                <AuspexChatMessages messages={processedMessages} isLoading={isLoading} />

                {/* Bottom: Analysis Tools - hidden when minimized */}
                <div className="flex-shrink-0 border-t border-gray-200 dark:border-gray-700">
                  {!isMinimized && (
                  <div className="px-4 py-2 bg-gray-50 dark:bg-gray-900 flex items-center gap-4">
                    {/* Deep Research */}
                    <div className="flex items-center gap-2">
                      <span className="text-sm text-gray-600 dark:text-gray-400">Deep Research:</span>
                      <Select value={researchMode} onValueChange={(v) => onResearchModeChange(v as ResearchMode)}>
                        <SelectTrigger className={cn(
                          "w-[100px] h-8 text-sm border-gray-300 dark:border-gray-600",
                          researchMode !== 'off'
                            ? "bg-pink-50 dark:bg-pink-900/30 text-pink-600 dark:text-pink-400 border-pink-300 dark:border-pink-700"
                            : "bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                        )}>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="off">Off</SelectItem>
                          <SelectItem value="internal">Internal</SelectItem>
                          <SelectItem value="hybrid">Hybrid</SelectItem>
                          <SelectItem value="external">External</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>

                    {/* Charts button - toggles includeCharts and opens panel */}
                    <button
                      disabled={isDisabled}
                      onClick={() => {
                        onIncludeChartsChange(!includeCharts);
                        setRightPanelTab('charts');
                        setIsRightPanelOpen(true);
                      }}
                      className={cn(
                        'flex items-center gap-1.5 px-3 py-1.5 text-sm rounded border transition-colors disabled:opacity-50',
                        includeCharts
                          ? 'bg-pink-50 dark:bg-pink-900/30 text-pink-600 dark:text-pink-400 border-pink-300 dark:border-pink-700'
                          : 'border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700'
                      )}
                      title={includeCharts ? 'Charts enabled - click to disable' : 'Click to enable automatic chart generation'}
                    >
                      <BarChart3 className="w-4 h-4" />
                      Charts {includeCharts && '✓'}
                    </button>

                    {/* Separator */}
                    <div className="h-6 w-px bg-gray-300 dark:bg-gray-600" />

                    {/* Analysis Tools Label with Settings */}
                    <div className="flex items-center gap-1">
                      <span className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">Analysis Tools:</span>
                      <div className="relative">
                        <button
                          onClick={() => setIsToolSettingsOpen(!isToolSettingsOpen)}
                          className="p-1 hover:bg-gray-200 dark:hover:bg-gray-700 rounded text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
                          title="Configure visible tools"
                        >
                          <Settings2 className="w-4 h-4" />
                        </button>
                        {/* Tool Settings Dropdown */}
                        {isToolSettingsOpen && (
                          <div className="absolute top-full left-0 mt-1 w-64 bg-white dark:bg-gray-800 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 z-50 max-h-80 overflow-y-auto">
                            <div className="p-2 border-b border-gray-200 dark:border-gray-700">
                              <span className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">Tool Visibility & Order</span>
                            </div>
                            <div className="p-2 space-y-1">
                              {toolOrder.map((toolName, idx) => {
                                const tool = pluginTools.find(t => t.name === toolName);
                                if (!tool) return null;
                                const isVisible = visibleTools.includes(toolName);
                                return (
                                  <div key={toolName} className="flex items-center gap-2 py-1 px-2 rounded hover:bg-gray-100 dark:hover:bg-gray-700">
                                    <button
                                      onClick={() => toggleToolVisibility(toolName)}
                                      className={cn(
                                        'p-1 rounded',
                                        isVisible ? 'text-green-500' : 'text-gray-400'
                                      )}
                                      title={isVisible ? 'Hide tool' : 'Show tool'}
                                    >
                                      {isVisible ? <Eye className="w-4 h-4" /> : <EyeOff className="w-4 h-4" />}
                                    </button>
                                    <span className={cn(
                                      'flex-1 text-sm truncate',
                                      isVisible ? 'text-gray-700 dark:text-gray-300' : 'text-gray-400'
                                    )}>
                                      {formatToolName(toolName)}
                                    </span>
                                    <div className="flex items-center gap-0.5">
                                      <button
                                        onClick={() => moveToolUp(toolName)}
                                        disabled={idx === 0}
                                        className="p-0.5 rounded hover:bg-gray-200 dark:hover:bg-gray-600 disabled:opacity-30"
                                        title="Move up"
                                      >
                                        <ChevronUp className="w-4 h-4 text-gray-500" />
                                      </button>
                                      <button
                                        onClick={() => moveToolDown(toolName)}
                                        disabled={idx === toolOrder.length - 1}
                                        className="p-0.5 rounded hover:bg-gray-200 dark:hover:bg-gray-600 disabled:opacity-30"
                                        title="Move down"
                                      >
                                        <ChevronDown className="w-4 h-4 text-gray-500" />
                                      </button>
                                    </div>
                                  </div>
                                );
                              })}
                            </div>
                            <div className="p-2 border-t border-gray-200 dark:border-gray-700 flex gap-2">
                              <button
                                onClick={() => onVisibleToolsChange(pluginTools.map(t => t.name))}
                                className="flex-1 px-2 py-1 text-xs bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 rounded text-gray-600 dark:text-gray-300"
                              >
                                Show All
                              </button>
                              <button
                                onClick={() => onVisibleToolsChange([])}
                                className="flex-1 px-2 py-1 text-xs bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 rounded text-gray-600 dark:text-gray-300"
                              >
                                Hide All
                              </button>
                            </div>
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Tool buttons - horizontal row */}
                    <div className="flex items-center gap-2 flex-wrap">
                      {displayedTools.map((tool) => (
                        <button
                          key={tool.name}
                          onClick={() => handleToolClick(tool)}
                          disabled={isDisabled || isStreaming}
                          className={cn(
                            'px-3 py-1.5 text-sm rounded border transition-colors',
                            isDisabled || isStreaming
                              ? 'bg-gray-100 dark:bg-gray-800 text-gray-400 border-gray-200 dark:border-gray-700 cursor-not-allowed'
                              : 'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 border-gray-300 dark:border-gray-600 hover:bg-pink-50 dark:hover:bg-pink-900/20 hover:text-pink-600 hover:border-pink-300'
                          )}
                          title={tool.description}
                        >
                          {formatToolName(tool.name)}
                        </button>
                      ))}
                    </div>
                  </div>
                  )}

                  {/* Input */}
                  <AuspexChatInput ref={inputRef} onSend={onSendMessage} disabled={isDisabled} isStreaming={isStreaming} />
                </div>
              </div>

              {/* Right Panel collapsed toggle - hidden when minimized */}
              {!isMinimized && !isRightPanelOpen && (
                <button
                  onClick={() => setIsRightPanelOpen(true)}
                  className="flex-shrink-0 w-6 flex items-center justify-center bg-gray-100 dark:bg-gray-800 border-l border-gray-200 dark:border-gray-700 hover:bg-gray-200 dark:hover:bg-gray-700"
                  title="Show insights panel"
                >
                  <PanelRightOpen className="w-4 h-4 text-gray-500" />
                </button>
              )}

              {/* Right Panel - wider for better chart display - hidden when minimized */}
              {!isMinimized && (
              <div className={cn(
                'flex-shrink-0 bg-gray-100 dark:bg-gray-800 border-l border-gray-200 dark:border-gray-700 flex flex-col transition-all duration-300',
                isRightPanelOpen ? 'w-96' : 'w-0 overflow-hidden'
              )}>
                {/* Panel Header with tabs */}
                <div className="flex-shrink-0 border-b border-gray-200 dark:border-gray-700">
                  <div className="flex items-center justify-between px-2 py-1.5">
                    <div className="flex">
                      <button
                        onClick={() => setRightPanelTab('insights')}
                        className={cn(
                          'px-3 py-2 text-xs font-medium transition-colors rounded-t',
                          rightPanelTab === 'insights'
                            ? 'bg-white dark:bg-gray-700 text-pink-600 dark:text-pink-400'
                            : 'text-gray-500 hover:text-gray-700 dark:hover:text-gray-300'
                        )}
                      >
                        <Sparkles className="w-4 h-4 mx-auto mb-0.5" />
                        Insights
                      </button>
                      <button
                        onClick={() => setRightPanelTab('charts')}
                        className={cn(
                          'px-3 py-2 text-xs font-medium transition-colors rounded-t',
                          rightPanelTab === 'charts'
                            ? 'bg-white dark:bg-gray-700 text-pink-600 dark:text-pink-400'
                            : 'text-gray-500 hover:text-gray-700 dark:hover:text-gray-300'
                        )}
                      >
                        <BarChart3 className="w-4 h-4 mx-auto mb-0.5" />
                        Charts
                      </button>
                    </div>
                    <button
                      onClick={() => setIsRightPanelOpen(false)}
                      className="p-1 hover:bg-gray-200 dark:hover:bg-gray-700 rounded text-gray-500"
                      title="Hide panel"
                    >
                      <ChevronRight className="w-4 h-4" />
                    </button>
                  </div>
                </div>

                {/* Panel Content */}
                <div className="flex-1 overflow-y-auto p-4">
                  {rightPanelTab === 'insights' && (
                    <InsightsPanel
                      messages={messages.map(m => ({ role: m.role, content: m.content }))}
                      chatId={currentChatId}
                      backendArticleStats={backendArticleStats}
                    />
                  )}
                  {rightPanelTab === 'charts' && (
                    <div className="space-y-4">
                      {allCharts.length === 0 ? (
                        <div className="text-center py-8 text-gray-400">
                          <BarChart3 className="w-12 h-12 mx-auto mb-3 opacity-50" />
                          <h3 className="text-sm font-medium text-gray-600 dark:text-gray-400 mb-1">
                            Visualizations
                          </h3>
                          <p className="text-xs text-gray-400">
                            Charts and graphs from your analysis will appear here
                          </p>
                        </div>
                      ) : (
                        allCharts.map((chart, idx) => (
                          <div
                            key={chart.id}
                            className="bg-white dark:bg-gray-800 rounded-lg p-2 shadow-sm border border-gray-200 dark:border-gray-700"
                          >
                            <div
                              ref={(el) => {
                                const key = chart.messageIndex * 100 + chart.chartIndex;
                                // Only set and trigger if this is a new element
                                if (el && !chartRefs.current.has(key)) {
                                  chartRefs.current.set(key, el);
                                  // Trigger re-render to run the chart rendering effect
                                  setChartContainersReady(prev => prev + 1);
                                }
                              }}
                              className="min-h-[280px] w-full"
                            />
                          </div>
                        ))
                      )}
                    </div>
                  )}
                </div>
              </div>
              )}
            </div>
          </DialogPrimitive.Content>
        </DialogPrimitive.Portal>
      </DialogPrimitive.Root>

      {/* Tools Config Modal */}
      <AuspexToolsConfig
        isOpen={isToolsConfigOpen}
        onClose={() => setIsToolsConfigOpen(false)}
        config={toolsConfig}
        onSave={onToolsConfigChange}
      />
    </>
  );
}
