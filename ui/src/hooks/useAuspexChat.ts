/**
 * useAuspexChat - React hook for managing Auspex chat state
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import {
  getTopics,
  getModels,
  createChatSession,
  getChatSessions,
  getChatMessages,
  deleteChatSession,
  sendChatMessage,
  startDeepResearch,
  getPluginTools,
  getModelContextLimit,
  type Topic,
  type Model,
  type ChatSession,
  type PluginTool,
  type ResearchMode
} from '../services/auspexService';
import { extractArticleStats, type BackendArticleStats } from '../utils/insightsParser';

export type SampleSizeMode = 'auto' | 'balanced' | 'comprehensive' | 'focused' | 'custom';
export type SamplingStrategy = 'auto' | 'recency_diversity' | 'quality_first' | 'latest' | 'diverse' | 'balanced_topics';
export type { ResearchMode } from '../services/auspexService';

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  isStreaming?: boolean;
}

interface UseAuspexChatReturn {
  // Data
  topics: Topic[];
  models: Model[];
  sessions: ChatSession[];
  messages: Message[];
  pluginTools: PluginTool[];
  backendArticleStats: BackendArticleStats | null;

  // Selection state
  selectedTopic: string;
  selectedModel: string;
  currentChatId: number | null;

  // UI state
  isLoading: boolean;
  isStreaming: boolean;
  error: string | null;

  // Settings
  toolsConfig: Record<string, boolean>;
  sampleSizeMode: SampleSizeMode;
  samplingStrategy: SamplingStrategy;
  customLimit: number;
  includeCharts: boolean;
  researchMode: ResearchMode;
  visibleTools: string[];
  toolOrder: string[];

  // Actions
  setSelectedTopic: (topic: string) => void;
  setSelectedModel: (model: string) => void;
  setSampleSizeMode: (mode: SampleSizeMode) => void;
  setSamplingStrategy: (strategy: SamplingStrategy) => void;
  setCustomLimit: (limit: number) => void;
  updateToolsConfig: (config: Record<string, boolean>) => void;
  setIncludeCharts: (include: boolean) => void;
  setResearchMode: (mode: ResearchMode) => void;
  setVisibleTools: (tools: string[]) => void;
  setToolOrder: (order: string[]) => void;

  // Chat actions
  createSession: () => Promise<void>;
  switchSession: (chatId: number) => Promise<void>;
  deleteSession: (chatId: number) => Promise<void>;
  clearAllSessions: () => Promise<void>;
  sendMessage: (message: string) => Promise<void>;
  clearMessages: () => void;
  exportChat: () => string;

  // Utility
  clearError: () => void;
  calculateOptimalSampleSize: () => number;
}

const STORAGE_KEYS = {
  topic: 'auspex_selected_topic',
  model: 'auspex_selected_model',
  sampleSizeMode: 'auspex_sample_size_mode',
  samplingStrategy: 'auspex_sampling_strategy',
  customLimit: 'auspex_custom_limit',
  toolsConfig: 'auspex_tools_config',
  includeCharts: 'auspex_include_charts',
  researchMode: 'auspex_research_mode',
  visibleTools: 'auspex_visible_tools',
  toolOrder: 'auspex_tool_order'
};

export function useAuspexChat(): UseAuspexChatReturn {
  // Data state
  const [topics, setTopics] = useState<Topic[]>([]);
  const [models, setModels] = useState<Model[]>([]);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [pluginTools, setPluginTools] = useState<PluginTool[]>([]);
  const [backendArticleStats, setBackendArticleStats] = useState<BackendArticleStats | null>(null);

  // Selection state
  const [selectedTopic, setSelectedTopicState] = useState<string>('');
  const [selectedModel, setSelectedModelState] = useState<string>('');
  const [currentChatId, setCurrentChatId] = useState<number | null>(null);

  // UI state
  const [isLoading, setIsLoading] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Settings
  const [toolsConfig, setToolsConfig] = useState<Record<string, boolean>>({});
  const [sampleSizeMode, setSampleSizeModeState] = useState<SampleSizeMode>('auto');
  const [samplingStrategy, setSamplingStrategyState] = useState<SamplingStrategy>('auto');
  const [customLimit, setCustomLimitState] = useState<number>(50);
  const [includeCharts, setIncludeChartsState] = useState<boolean>(false);
  const [researchMode, setResearchModeState] = useState<ResearchMode>('off');
  const [visibleTools, setVisibleToolsState] = useState<string[]>([]);
  const [toolOrder, setToolOrderState] = useState<string[]>([]);

  // Refs for SSE cancellation
  const abortControllerRef = useRef<AbortController | null>(null);

  // Load initial data
  useEffect(() => {
    const loadInitialData = async () => {
      try {
        setIsLoading(true);
        const [topicsData, modelsData, toolsData] = await Promise.all([
          getTopics(),
          getModels(),
          getPluginTools()
        ]);
        setTopics(topicsData);
        setModels(modelsData);
        setPluginTools(toolsData);

        // Initialize tools config
        const defaultConfig: Record<string, boolean> = {};
        toolsData.forEach(tool => {
          defaultConfig[tool.name] = tool.enabled !== false;
        });

        // Load saved settings
        const savedTopic = localStorage.getItem(STORAGE_KEYS.topic);
        const savedModel = localStorage.getItem(STORAGE_KEYS.model);
        const savedSampleMode = localStorage.getItem(STORAGE_KEYS.sampleSizeMode) as SampleSizeMode;
        const savedStrategy = localStorage.getItem(STORAGE_KEYS.samplingStrategy) as SamplingStrategy;
        const savedLimit = localStorage.getItem(STORAGE_KEYS.customLimit);
        const savedToolsConfig = localStorage.getItem(STORAGE_KEYS.toolsConfig);
        const savedIncludeCharts = localStorage.getItem(STORAGE_KEYS.includeCharts);
        const savedResearchMode = localStorage.getItem(STORAGE_KEYS.researchMode) as ResearchMode;
        const savedVisibleTools = localStorage.getItem(STORAGE_KEYS.visibleTools);
        const savedToolOrder = localStorage.getItem(STORAGE_KEYS.toolOrder);

        if (savedTopic && topicsData.some(t => t.name === savedTopic)) {
          setSelectedTopicState(savedTopic);
        } else {
          // Default to "All Topics" for better UX
          setSelectedTopicState('__all__');
        }
        if (savedModel && modelsData.some(m => m.id === savedModel)) {
          setSelectedModelState(savedModel);
        } else if (modelsData.length > 0) {
          setSelectedModelState(modelsData[0].id);
        }
        if (savedSampleMode) setSampleSizeModeState(savedSampleMode);
        if (savedStrategy) setSamplingStrategyState(savedStrategy);
        if (savedLimit) setCustomLimitState(parseInt(savedLimit, 10));
        if (savedIncludeCharts) setIncludeChartsState(savedIncludeCharts === 'true');
        if (savedResearchMode) setResearchModeState(savedResearchMode);
        if (savedToolsConfig) {
          try {
            setToolsConfig({ ...defaultConfig, ...JSON.parse(savedToolsConfig) });
          } catch {
            setToolsConfig(defaultConfig);
          }
        } else {
          setToolsConfig(defaultConfig);
        }

        // Initialize visible tools and tool order
        const allToolNames = toolsData.map(t => t.name);
        if (savedVisibleTools) {
          try {
            setVisibleToolsState(JSON.parse(savedVisibleTools));
          } catch {
            setVisibleToolsState(allToolNames);
          }
        } else {
          setVisibleToolsState(allToolNames);
        }
        if (savedToolOrder) {
          try {
            setToolOrderState(JSON.parse(savedToolOrder));
          } catch {
            setToolOrderState(allToolNames);
          }
        } else {
          setToolOrderState(allToolNames);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load initial data');
      } finally {
        setIsLoading(false);
      }
    };

    loadInitialData();
  }, []);

  // Load sessions when topic changes
  useEffect(() => {
    if (selectedTopic) {
      loadSessions(selectedTopic);
    }
  }, [selectedTopic]);

  const loadSessions = async (topic: string) => {
    try {
      const sessionsData = await getChatSessions(topic);
      setSessions(sessionsData);
    } catch (err) {
      console.error('Failed to load sessions:', err);
    }
  };

  // Selection handlers with persistence
  const setSelectedTopic = useCallback((topic: string) => {
    setSelectedTopicState(topic);
    localStorage.setItem(STORAGE_KEYS.topic, topic);
    setCurrentChatId(null);
    setMessages([]);
  }, []);

  const setSelectedModel = useCallback((model: string) => {
    setSelectedModelState(model);
    localStorage.setItem(STORAGE_KEYS.model, model);
  }, []);

  const setSampleSizeMode = useCallback((mode: SampleSizeMode) => {
    setSampleSizeModeState(mode);
    localStorage.setItem(STORAGE_KEYS.sampleSizeMode, mode);
  }, []);

  const setSamplingStrategy = useCallback((strategy: SamplingStrategy) => {
    setSamplingStrategyState(strategy);
    localStorage.setItem(STORAGE_KEYS.samplingStrategy, strategy);
  }, []);

  const setCustomLimit = useCallback((limit: number) => {
    setCustomLimitState(limit);
    localStorage.setItem(STORAGE_KEYS.customLimit, limit.toString());
  }, []);

  const updateToolsConfig = useCallback((config: Record<string, boolean>) => {
    setToolsConfig(config);
    localStorage.setItem(STORAGE_KEYS.toolsConfig, JSON.stringify(config));
  }, []);

  const setIncludeCharts = useCallback((include: boolean) => {
    setIncludeChartsState(include);
    localStorage.setItem(STORAGE_KEYS.includeCharts, include.toString());
  }, []);

  const setResearchMode = useCallback((mode: ResearchMode) => {
    setResearchModeState(mode);
    localStorage.setItem(STORAGE_KEYS.researchMode, mode);
  }, []);

  const setVisibleTools = useCallback((tools: string[]) => {
    setVisibleToolsState(tools);
    localStorage.setItem(STORAGE_KEYS.visibleTools, JSON.stringify(tools));
  }, []);

  const setToolOrder = useCallback((order: string[]) => {
    setToolOrderState(order);
    localStorage.setItem(STORAGE_KEYS.toolOrder, JSON.stringify(order));
  }, []);

  // Chat actions
  const createSession = useCallback(async () => {
    if (!selectedTopic || !selectedModel) return;

    try {
      setIsLoading(true);
      const session = await createChatSession(selectedTopic, selectedModel);
      setCurrentChatId(session.id);
      setSessions(prev => [session, ...prev]);
      setMessages([]);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create session');
    } finally {
      setIsLoading(false);
    }
  }, [selectedTopic, selectedModel]);

  const switchSession = useCallback(async (chatId: number) => {
    try {
      setIsLoading(true);
      const messagesData = await getChatMessages(chatId);
      setCurrentChatId(chatId);
      setMessages(messagesData.map(m => ({
        id: m.id.toString(),
        role: m.role,
        content: m.content,
        timestamp: new Date(m.timestamp)
      })));

      // Try to extract stats from the last assistant message (for sessions created after the update)
      const assistantMessages = messagesData.filter(m => m.role === 'assistant');
      if (assistantMessages.length > 0) {
        const lastMessage = assistantMessages[assistantMessages.length - 1];
        const stats = extractArticleStats(lastMessage.content);
        setBackendArticleStats(stats);
      } else {
        setBackendArticleStats(null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load messages');
    } finally {
      setIsLoading(false);
    }
  }, []);

  const deleteSession = useCallback(async (chatId: number) => {
    try {
      await deleteChatSession(chatId);
      setSessions(prev => prev.filter(s => s.id !== chatId));
      if (currentChatId === chatId) {
        setCurrentChatId(null);
        setMessages([]);
        setBackendArticleStats(null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete session');
    }
  }, [currentChatId]);

  const clearAllSessions = useCallback(async () => {
    try {
      setIsLoading(true);
      // Delete all sessions sequentially
      for (const session of sessions) {
        await deleteChatSession(session.id);
      }
      setSessions([]);
      setCurrentChatId(null);
      setMessages([]);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to clear sessions');
    } finally {
      setIsLoading(false);
    }
  }, [sessions]);

  const sendMessage = useCallback(async (message: string) => {
    if (!message.trim() || !selectedModel) return;

    // Create session if needed
    let chatId = currentChatId;
    if (!chatId) {
      try {
        const session = await createChatSession(selectedTopic || '__all__', selectedModel);
        chatId = session.id;
        setCurrentChatId(chatId);
        setSessions(prev => [session, ...prev]);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to create session');
        return;
      }
    }

    // Add user message
    const userMessage: Message = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: message,
      timestamp: new Date()
    };
    setMessages(prev => [...prev, userMessage]);

    // Add placeholder for assistant message
    const assistantMessageId = `assistant-${Date.now()}`;
    const assistantMessage: Message = {
      id: assistantMessageId,
      role: 'assistant',
      content: '',
      timestamp: new Date(),
      isStreaming: true
    };
    setMessages(prev => [...prev, assistantMessage]);
    setIsStreaming(true);

    try {
      // Route to appropriate endpoint based on research mode
      const generator = researchMode !== 'off'
        ? startDeepResearch({
            chatId,
            message,
            topic: selectedTopic || '__all__',
            researchMode,
            includeCharts
          })
        : sendChatMessage({
            chatId,
            message,
            model: selectedModel,
            topic: selectedTopic || undefined,
            sampleSizeMode,
            samplingStrategy,
            customLimit: calculateOptimalSampleSize(),  // Always send calculated sample size
            toolsConfig,
            includeCharts
          });

      let fullContent = '';
      for await (const chunk of generator) {
        fullContent += chunk;
        setMessages(prev => prev.map(m =>
          m.id === assistantMessageId
            ? { ...m, content: fullContent }
            : m
        ));
      }

      // Debug: Log final content to check for chart markers
      console.log('[useAuspexChat] Full response length:', fullContent.length);
      if (fullContent.includes('CHART_DATA')) {
        console.log('[useAuspexChat] Response contains CHART_DATA marker');
        console.log('[useAuspexChat] Marker index:', fullContent.indexOf('CHART_DATA'));
      } else {
        console.log('[useAuspexChat] No CHART_DATA marker found in response');
      }

      // Extract backend article stats from the response (if present)
      const stats = extractArticleStats(fullContent);
      if (stats) {
        setBackendArticleStats(stats);
      }

      // Mark as complete
      setMessages(prev => prev.map(m =>
        m.id === assistantMessageId
          ? { ...m, isStreaming: false }
          : m
      ));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to send message');
      // Remove failed assistant message
      setMessages(prev => prev.filter(m => m.id !== assistantMessageId));
    } finally {
      setIsStreaming(false);
    }
  }, [currentChatId, selectedTopic, selectedModel, sampleSizeMode, samplingStrategy, customLimit, toolsConfig, includeCharts, researchMode]);

  const clearMessages = useCallback(() => {
    setMessages([]);
    setCurrentChatId(null);
    setBackendArticleStats(null);
  }, []);

  const exportChat = useCallback(() => {
    const topic = topics.find(t => t.name === selectedTopic);
    const model = models.find(m => m.id === selectedModel);

    let markdown = '# Auspex Chat Export\n';
    markdown += `**Topic:** ${topic?.display_name || selectedTopic || 'All Topics'}\n`;
    markdown += `**Model:** ${model?.name || selectedModel}\n`;
    markdown += `**Date:** ${new Date().toLocaleString()}\n\n`;
    markdown += '---\n\n';

    messages.forEach(msg => {
      const speaker = msg.role === 'user' ? 'You' : 'Auspex';
      markdown += `## ${speaker}\n\n${msg.content}\n\n`;
    });

    return markdown;
  }, [messages, selectedTopic, selectedModel, topics, models]);

  const clearError = useCallback(() => {
    setError(null);
  }, []);

  const calculateOptimalSampleSize = useCallback(() => {
    switch (sampleSizeMode) {
      case 'focused':
        return 25;
      case 'balanced':
        return 50;
      case 'comprehensive':
        return 100;
      case 'custom':
        return customLimit;
      case 'auto':
      default: {
        // Calculate optimal size based on model context limit
        const contextLimit = getModelContextLimit(selectedModel);
        const systemPromptTokens = 2000;   // Reserved for system prompt
        const responseTokens = 4000;        // Reserved for AI response
        const overheadTokens = 1000;        // Buffer for formatting, etc.
        const tokensPerArticle = 800;       // Average tokens per article

        const availableTokens = contextLimit - systemPromptTokens - responseTokens - overheadTokens;
        const maxArticles = Math.floor(availableTokens / tokensPerArticle);

        // Clamp between 50 and 300 (MAX_CITATION_LIMIT)
        return Math.max(50, Math.min(300, maxArticles));
      }
    }
  }, [sampleSizeMode, customLimit, selectedModel]);

  return {
    // Data
    topics,
    models,
    sessions,
    messages,
    pluginTools,
    backendArticleStats,

    // Selection state
    selectedTopic,
    selectedModel,
    currentChatId,

    // UI state
    isLoading,
    isStreaming,
    error,

    // Settings
    toolsConfig,
    sampleSizeMode,
    samplingStrategy,
    customLimit,
    includeCharts,
    researchMode,
    visibleTools,
    toolOrder,

    // Actions
    setSelectedTopic,
    setSelectedModel,
    setSampleSizeMode,
    setSamplingStrategy,
    setCustomLimit,
    updateToolsConfig,
    setIncludeCharts,
    setResearchMode,
    setVisibleTools,
    setToolOrder,

    // Chat actions
    createSession,
    switchSession,
    deleteSession,
    clearAllSessions,
    sendMessage,
    clearMessages,
    exportChat,

    // Utility
    clearError,
    calculateOptimalSampleSize
  };
}
