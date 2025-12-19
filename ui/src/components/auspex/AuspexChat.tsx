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

import { useState, useMemo, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { useAuspexChat } from '../../hooks/useAuspexChat';
import { AuspexChatButton } from './AuspexChatButton';
import { AuspexChatModal } from './AuspexChatModal';
import { getModelContextLimit } from '../../services/auspexService';

interface AuspexChatProps {
  /** Additional class names for the floating button */
  buttonClassName?: string;
}

export function AuspexChat({ buttonClassName }: AuspexChatProps) {
  const [isOpen, setIsOpen] = useState(false);

  const {
    // Data
    topics,
    models,
    sessions,
    messages,
    pluginTools,
    savedSnippets,

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

    // Snippet actions
    saveTextSnippet,
    removeSnippet,

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

  const handleOpen = () => {
    setIsOpen(true);
  };

  const handleClose = () => {
    setIsOpen(false);
  };

  const handleNewChat = () => {
    clearMessages();
    createSession();
  };

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
        savedSnippets={savedSnippets}
        onSaveSnippet={saveTextSnippet}
        onDeleteSnippet={removeSnippet}
      />
    </>
  );
}
