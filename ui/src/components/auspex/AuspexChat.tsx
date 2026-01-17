/**
 * AuspexChat - Main container component for the Auspex chat assistant
 *
 * This component provides a floating chat button and modal interface
 * for interacting with the Auspex AI research assistant.
 *
 * Usage:
 * ```tsx
 * import { AuspexChat } from './components/auspex';
 *
 * function App() {
 *   return (
 *     <div>
 *       {/* Your app content *\/}
 *       <AuspexChat />
 *     </div>
 *   );
 * }
 * ```
 */

import { useState, useMemo, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { useAuspexChat } from '../../hooks/useAuspexChat';
import { AuspexChatButton } from './AuspexChatButton';
import { AuspexChatModal } from './AuspexChatModal';
import { getModelContextLimit } from '../../services/auspexService';
import { AUSPEX_OPEN_EVENT, type AuspexOpenEventDetail } from '../../utils/auspexEvents';

interface AuspexChatProps {
  /** Additional class names for the floating button */
  buttonClassName?: string;
}

export function AuspexChat({ buttonClassName }: AuspexChatProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [initialQuery, setInitialQuery] = useState<string>('');

  const {
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
  } = useAuspexChat();

  // Calculate context stats based on sample size and model
  const contextStats = useMemo(() => {
    const sampleSize = calculateOptimalSampleSize();
    const avgTokensPerArticle = 800;
    const estimatedTokens = sampleSize * avgTokensPerArticle;
    const contextLimit = getModelContextLimit(selectedModel);
    const percentage = contextLimit > 0 ? (estimatedTokens / contextLimit) * 100 : 0;

    return {
      articles: sampleSize,
      tokens: estimatedTokens,
      percentage: Math.min(percentage, 100)
    };
  }, [selectedModel, calculateOptimalSampleSize]);

  const handleOpen = useCallback(() => {
    setIsOpen(true);
  }, []);

  const handleClose = useCallback(() => {
    setIsOpen(false);
    // Clear initial query when closing
    setInitialQuery('');
  }, []);

  const handleNewChat = useCallback(() => {
    clearMessages();
    createSession();
  }, [clearMessages, createSession]);

  // Listen for global Auspex open events
  useEffect(() => {
    const handleAuspexOpen = (event: CustomEvent<AuspexOpenEventDetail>) => {
      console.log('[AuspexChat] Received open event:', event.detail);
      const { query, topic } = event.detail;
      if (query) {
        setInitialQuery(query);
      }
      // Set topic filter if provided
      if (topic && topics.includes(topic)) {
        setSelectedTopic(topic);
      }
      setIsOpen(true);
      console.log('[AuspexChat] Modal opened with query:', query);
    };

    console.log('[AuspexChat] Setting up event listener for:', AUSPEX_OPEN_EVENT);
    window.addEventListener(AUSPEX_OPEN_EVENT, handleAuspexOpen as EventListener);
    return () => {
      window.removeEventListener(AUSPEX_OPEN_EVENT, handleAuspexOpen as EventListener);
    };
  }, [topics, setSelectedTopic]);

  // Show error alert when error state changes
  useEffect(() => {
    if (error) {
      console.error('Auspex Chat Error:', error);
      // Show user-friendly error notification
      alert(`Auspex Error: ${error}`);
      clearError();
    }
  }, [error, clearError]);

  return (
    <>
      {/* Floating Button - rendered in a portal to ensure it's above everything */}
      {createPortal(
        <AuspexChatButton
          onClick={handleOpen}
          className={buttonClassName}
        />,
        document.body
      )}

      {/* Chat Modal */}
      <AuspexChatModal
        isOpen={isOpen}
        onClose={handleClose}
        topics={topics}
        models={models}
        sessions={sessions}
        messages={messages}
        pluginTools={pluginTools}
        selectedTopic={selectedTopic}
        selectedModel={selectedModel}
        currentChatId={currentChatId}
        onTopicChange={setSelectedTopic}
        onModelChange={setSelectedModel}
        sampleSizeMode={sampleSizeMode}
        samplingStrategy={samplingStrategy}
        customLimit={customLimit}
        toolsConfig={toolsConfig}
        includeCharts={includeCharts}
        researchMode={researchMode}
        visibleTools={visibleTools}
        toolOrder={toolOrder}
        onSampleSizeModeChange={setSampleSizeMode}
        onSamplingStrategyChange={setSamplingStrategy}
        onCustomLimitChange={setCustomLimit}
        onToolsConfigChange={updateToolsConfig}
        onIncludeChartsChange={setIncludeCharts}
        onResearchModeChange={setResearchMode}
        onVisibleToolsChange={setVisibleTools}
        onToolOrderChange={setToolOrder}
        isLoading={isLoading}
        isStreaming={isStreaming}
        onSendMessage={sendMessage}
        onNewChat={handleNewChat}
        onSelectSession={switchSession}
        onDeleteSession={deleteSession}
        onClearAllSessions={clearAllSessions}
        onExportChat={exportChat}
        contextStats={contextStats}
        backendArticleStats={backendArticleStats}
        initialQuery={initialQuery}
        onInitialQueryHandled={() => setInitialQuery('')}
      />
    </>
  );
}
