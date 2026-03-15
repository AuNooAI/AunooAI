/**
 * Geopolitical Import Modal Component
 * Provides batch processing of articles to extract geopolitical hotspots
 */

import { useState, useCallback, useEffect, useRef } from 'react';
import { X, Database, Loader2, CheckCircle, AlertCircle, Play, Trash2, RefreshCw, Clock } from 'lucide-react';
import { GeopoliticalScheduleModal } from './GeopoliticalScheduleModal';

interface ProcessingStats {
  total_curated_articles: number;
  processed_articles: number;
  unprocessed_articles: number;
  total_hotspots: number;
  processing_percentage: number;
  topic?: string;
}

interface AvailableTopic {
  topic: string;
  total_articles: number;
  unprocessed_count: number;
}

interface ProcessResult {
  status: string;
  message: string;
  articles_processed: number;
  hotspots_created: number;
  hotspots_updated: number;
  articles_skipped: number;
  errors: number;
  // Background processing fields
  running?: boolean;
  progress?: number;
  total?: number;
  processed?: number;
  created?: number;
  updated?: number;
  skipped?: number;
  completed?: boolean;
  last_error?: string | null;
}

interface GeopoliticalImportModalProps {
  isOpen: boolean;
  onClose: () => void;
  onImportComplete?: () => void;
  model?: string;
}

const BATCH_SIZES = [10, 25, 50, 100, 200, 500];

export function GeopoliticalImportModal({
  isOpen,
  onClose,
  onImportComplete,
  model = 'gpt-4o-mini',
}: GeopoliticalImportModalProps) {
  // Processing options
  const [batchSize, setBatchSize] = useState(50);
  const [runLlmExtraction, setRunLlmExtraction] = useState(true);
  const [regenerateNarrative, setRegenerateNarrative] = useState(false);
  const [selectedTopic, setSelectedTopic] = useState<string>('');
  const [processAll, setProcessAll] = useState(false);

  // Schedule modal
  const [showScheduleModal, setShowScheduleModal] = useState(false);

  // Available topics
  const [availableTopics, setAvailableTopics] = useState<AvailableTopic[]>([]);
  const [loadingTopics, setLoadingTopics] = useState(false);

  // Processing state
  const [isProcessing, setIsProcessing] = useState(false);
  const [processingStats, setProcessingStats] = useState<ProcessingStats | null>(null);
  const [loadingStats, setLoadingStats] = useState(false);
  const [processResult, setProcessResult] = useState<ProcessResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [processingLog, setProcessingLog] = useState<string[]>([]);
  const [isClearing, setIsClearing] = useState(false);
  const [showClearConfirm, setShowClearConfirm] = useState(false);

  const statsLoadedRef = useRef(false);
  const topicsLoadedRef = useRef(false);
  const pollingIntervalRef = useRef<NodeJS.Timeout | null>(null);

  // Load available topics when modal opens
  useEffect(() => {
    if (isOpen && !topicsLoadedRef.current && !loadingTopics) {
      topicsLoadedRef.current = true;
      fetchAvailableTopics();
    }
  }, [isOpen, loadingTopics]);

  // Load processing stats when modal opens or topic changes
  useEffect(() => {
    if (isOpen && !loadingStats) {
      if (!statsLoadedRef.current || selectedTopic !== (processingStats?.topic || '')) {
        statsLoadedRef.current = true;
        fetchProcessingStats();
      }
    }
  }, [isOpen, loadingStats, selectedTopic]);

  // Reset state when modal closes
  useEffect(() => {
    if (!isOpen) {
      statsLoadedRef.current = false;
      topicsLoadedRef.current = false;
      setProcessResult(null);
      setError(null);
      setProcessingLog([]);
      setProcessAll(false);
      // Clear any polling interval
      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current);
        pollingIntervalRef.current = null;
      }
    }
  }, [isOpen]);

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current);
      }
    };
  }, []);

  const fetchAvailableTopics = async () => {
    setLoadingTopics(true);
    try {
      const response = await fetch('/api/geopolitical-hotspots/available-topics');
      if (response.ok) {
        const data = await response.json();
        setAvailableTopics(data.topics || []);
        // Set default topic to first topic with unprocessed articles, or "Geopolitical Hotspots" if available
        if (data.topics?.length > 0 && !selectedTopic) {
          const geoTopic = data.topics.find((t: AvailableTopic) => t.topic === 'Geopolitical Hotspots');
          setSelectedTopic(geoTopic ? geoTopic.topic : data.topics[0].topic);
        }
      } else {
        console.error('Failed to load available topics');
        topicsLoadedRef.current = false;
      }
    } catch (err) {
      console.error('Failed to fetch available topics:', err);
      topicsLoadedRef.current = false;
    } finally {
      setLoadingTopics(false);
    }
  };

  const fetchProcessingStats = async () => {
    setLoadingStats(true);
    try {
      const params = new URLSearchParams();
      if (selectedTopic) params.append('topic', selectedTopic);

      const response = await fetch(`/api/geopolitical-hotspots/processing-stats?${params}`);
      if (response.ok) {
        const data = await response.json();
        setProcessingStats(data);
      } else {
        setError('Failed to load processing stats');
        statsLoadedRef.current = false;
      }
    } catch (err) {
      console.error('Failed to fetch processing stats:', err);
      setError('Failed to load processing stats');
      statsLoadedRef.current = false;
    } finally {
      setLoadingStats(false);
    }
  };

  // Poll for processing status
  const pollProcessingStatus = useCallback(async () => {
    try {
      const response = await fetch('/api/geopolitical-hotspots/process-articles/status');
      if (!response.ok) return;

      const status = await response.json();

      // Update the result with background processing status
      setProcessResult({
        status: status.completed ? 'complete' : (status.running ? 'running' : 'pending'),
        message: status.message || '',
        articles_processed: status.processed || 0,
        hotspots_created: status.created || 0,
        hotspots_updated: status.updated || 0,
        articles_skipped: status.skipped || 0,
        errors: status.errors || 0,
        running: status.running,
        progress: status.progress,
        total: status.total,
        completed: status.completed,
        last_error: status.last_error,
      });

      // Update processing log
      if (status.progress && status.total) {
        setProcessingLog((prev) => {
          // Only add if different from last entry
          const progressLine = `Processing: ${status.progress}/${status.total} articles...`;
          if (prev[prev.length - 1] !== progressLine) {
            // Remove previous progress lines to avoid log spam
            const filtered = prev.filter(line => !line.startsWith('Processing:'));
            return [...filtered, progressLine];
          }
          return prev;
        });
      }

      // If completed, stop polling and finalize
      if (status.completed || (!status.running && status.progress === status.total)) {
        if (pollingIntervalRef.current) {
          clearInterval(pollingIntervalRef.current);
          pollingIntervalRef.current = null;
        }
        setIsProcessing(false);

        setProcessingLog((prev) => {
          const filtered = prev.filter(line => !line.startsWith('Processing:'));
          return [
            ...filtered,
            `Processed: ${status.processed || 0} articles`,
            `Hotspots created: ${status.created || 0}`,
            `Hotspots updated: ${status.updated || 0}`,
            `Skipped: ${status.skipped || 0}`,
            status.errors > 0 ? `Errors: ${status.errors}` : '',
            'Processing complete!',
          ].filter(Boolean);
        });

        // Refresh stats after processing
        await fetchProcessingStats();

        if (onImportComplete) {
          onImportComplete();
        }
      }
    } catch (err) {
      console.error('Error polling processing status:', err);
    }
  }, [fetchProcessingStats, onImportComplete]);

  const handleProcess = useCallback(async () => {
    setError(null);
    setIsProcessing(true);
    setProcessResult(null);
    const topicName = selectedTopic || 'Geopolitical Hotspots';
    const modeText = processAll ? 'all' : 'unprocessed';
    setProcessingLog([`Starting processing of ${batchSize} ${modeText} articles from "${topicName}" using ${model}...`]);

    try {
      const response = await fetch('/api/geopolitical-hotspots/process-articles', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          batch_size: batchSize,
          model: model,
          run_llm_extraction: runLlmExtraction,
          regenerate_narrative: regenerateNarrative,
          topic: selectedTopic || undefined,
          process_all: processAll,
        }),
      });

      // Check if response is JSON before parsing
      const contentType = response.headers.get('content-type');
      if (!contentType || !contentType.includes('application/json')) {
        const text = await response.text();
        if (response.status === 401 || response.status === 307) {
          throw new Error('Session expired. Please refresh the page and log in again.');
        }
        throw new Error(`Server returned non-JSON response (${response.status}): ${text.slice(0, 100)}...`);
      }

      const result = await response.json();

      // Handle authentication errors
      if (response.status === 401) {
        throw new Error('Session expired. Please refresh the page and log in again.');
      }

      if (response.ok) {
        // Check if background processing started
        if (result.status === 'started' || result.status === 'running') {
          setProcessingLog((prev) => [...prev, result.message || 'Processing started in background...']);

          // Start polling for status
          pollingIntervalRef.current = setInterval(pollProcessingStatus, 2000);
        } else {
          // Synchronous completion (shouldn't happen anymore, but handle it)
          setProcessResult(result);
          setProcessingLog((prev) => [
            ...prev,
            `Processed: ${result.articles_processed} articles`,
            `Hotspots created: ${result.hotspots_created}`,
            `Hotspots updated: ${result.hotspots_updated}`,
            `Skipped: ${result.articles_skipped}`,
            result.errors > 0 ? `Errors: ${result.errors}` : '',
            'Processing complete!',
          ].filter(Boolean));

          // Refresh stats after processing
          await fetchProcessingStats();
          setIsProcessing(false);

          if (onImportComplete) {
            onImportComplete();
          }
        }
      } else {
        setError(result.detail || 'Processing failed');
        setProcessingLog((prev) => [...prev, `Error: ${result.detail || 'Unknown error'}`]);
        setIsProcessing(false);
      }
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Processing failed';
      setError(errorMsg);
      setProcessingLog((prev) => [...prev, `Error: ${errorMsg}`]);
      setIsProcessing(false);
    }
  }, [batchSize, model, runLlmExtraction, regenerateNarrative, selectedTopic, processAll, onImportComplete, pollProcessingStatus]);

  const handleClearAllData = useCallback(async () => {
    setIsClearing(true);
    setError(null);

    try {
      const response = await fetch('/api/geopolitical-hotspots/clear-hotspots', {
        method: 'DELETE',
      });

      if (response.ok) {
        setShowClearConfirm(false);
        // Refresh stats after clearing
        await fetchProcessingStats();
        if (onImportComplete) {
          onImportComplete();
        }
      } else {
        const result = await response.json();
        setError(result.detail || 'Failed to clear data');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to clear data');
    } finally {
      setIsClearing(false);
    }
  }, [onImportComplete]);

  const handleClose = useCallback(() => {
    if (!isProcessing && !isClearing) {
      setShowClearConfirm(false);
      onClose();
    }
  }, [isProcessing, isClearing, onClose]);

  const resetAndClose = useCallback(() => {
    setProcessResult(null);
    setError(null);
    setProcessingLog([]);
    setIsProcessing(false);
    onClose();
  }, [onClose]);

  if (!isOpen) return null;

  const isComplete = processResult?.status === 'success' || processResult?.status === 'complete';
  const isFailed = !!error;

  return (
    <div className="fixed inset-0 z-[1100] flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/50"
        onClick={handleClose}
      />

      {/* Modal */}
      <div className="relative bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-lg max-h-[90vh] overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-700">
          <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100">
            Update Geopolitical Hotspots
          </h3>
          <button
            onClick={handleClose}
            disabled={isProcessing}
            className="text-gray-500 hover:text-gray-600 dark:hover:text-gray-500 disabled:opacity-50"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="p-4 overflow-y-auto max-h-[70vh]">
          {/* Processing Result Display */}
          {processResult && (
            <div className={`p-4 rounded-lg mb-4 ${
              isComplete
                ? 'bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800'
                : 'bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800'
            }`}>
              <div className="flex items-center gap-2 mb-2">
                {isComplete ? (
                  <CheckCircle className="w-5 h-5 text-green-500" />
                ) : (
                  <Loader2 className="w-5 h-5 text-blue-500 animate-spin" />
                )}
                <span className={`font-medium ${
                  isComplete
                    ? 'text-green-700 dark:text-green-300'
                    : 'text-blue-700 dark:text-blue-300'
                }`}>
                  {isComplete ? 'Processing Complete' : 'Processing...'}
                </span>
              </div>

              {/* Progress bar for background processing */}
              {processResult.running && processResult.total && processResult.total > 0 && (
                <div className="mb-3">
                  <div className="flex justify-between text-xs text-blue-600 dark:text-blue-400 mb-1">
                    <span>Progress</span>
                    <span>{processResult.progress || 0} / {processResult.total} articles</span>
                  </div>
                  <div className="w-full bg-blue-200 dark:bg-blue-800 rounded-full h-2">
                    <div
                      className="bg-blue-500 h-2 rounded-full transition-all duration-300"
                      style={{ width: `${((processResult.progress || 0) / processResult.total) * 100}%` }}
                    />
                  </div>
                </div>
              )}

              <div className="grid grid-cols-2 gap-2 text-sm">
                <div className="text-gray-600 dark:text-gray-300">Articles Processed:</div>
                <div className="text-gray-900 dark:text-gray-100">{processResult.articles_processed}</div>

                <div className="text-gray-600 dark:text-gray-300">Hotspots Created:</div>
                <div className="text-gray-900 dark:text-gray-100">{processResult.hotspots_created}</div>

                <div className="text-gray-600 dark:text-gray-300">Hotspots Updated:</div>
                <div className="text-gray-900 dark:text-gray-100">{processResult.hotspots_updated}</div>

                <div className="text-gray-600 dark:text-gray-300">Skipped:</div>
                <div className="text-gray-900 dark:text-gray-100">{processResult.articles_skipped}</div>

                {processResult.errors > 0 && (
                  <>
                    <div className="text-gray-600 dark:text-gray-300">Errors:</div>
                    <div className="text-red-600 dark:text-red-400">{processResult.errors}</div>
                  </>
                )}
              </div>

              {isComplete && (
                <button
                  onClick={resetAndClose}
                  className="mt-4 w-full px-4 py-2 text-sm bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
                >
                  Close
                </button>
              )}
            </div>
          )}

          {/* Database Tab Content */}
          {!processResult && (
            <div className="space-y-4">
              {/* Stats Display */}
              {loadingStats ? (
                <div className="flex items-center gap-2 px-3 py-4 text-sm text-gray-500 dark:text-gray-300">
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Loading processing stats...
                </div>
              ) : processingStats && (
                <div className="p-4 bg-pink-50 dark:bg-pink-900/20 rounded-lg border border-pink-200 dark:border-pink-800">
                  <div className="flex items-center gap-2 mb-3">
                    <Database className="w-5 h-5 text-pink-500" />
                    <span className="font-medium text-gray-900 dark:text-gray-100">
                      {processingStats.topic || 'Geopolitical Hotspots'}
                    </span>
                  </div>

                  <div className="grid grid-cols-2 gap-3 text-sm mb-3">
                    <div>
                      <div className="text-gray-500 dark:text-gray-400">Curated Articles</div>
                      <div className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                        {processingStats.total_curated_articles.toLocaleString()}
                      </div>
                    </div>
                    <div>
                      <div className="text-gray-500 dark:text-gray-400">Processed</div>
                      <div className="text-lg font-semibold text-green-600 dark:text-green-400">
                        {processingStats.processed_articles.toLocaleString()}
                      </div>
                    </div>
                    <div>
                      <div className="text-gray-500 dark:text-gray-400">
                        {processAll ? 'Available' : 'Remaining'}
                      </div>
                      <div className="text-lg font-semibold text-amber-600 dark:text-amber-400">
                        {processAll
                          ? processingStats.total_curated_articles.toLocaleString()
                          : processingStats.unprocessed_articles.toLocaleString()}
                      </div>
                    </div>
                    <div>
                      <div className="text-gray-500 dark:text-gray-400">Hotspots</div>
                      <div className="text-lg font-semibold text-pink-600 dark:text-pink-400">
                        {processingStats.total_hotspots.toLocaleString()}
                      </div>
                    </div>
                  </div>

                  {/* Progress Bar */}
                  <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
                    <div
                      className="bg-pink-500 h-2 rounded-full transition-all duration-500"
                      style={{ width: `${processingStats.processing_percentage}%` }}
                    />
                  </div>
                  <div className="text-xs text-gray-500 dark:text-gray-400 mt-1 text-right">
                    {processingStats.processing_percentage}% processed
                  </div>
                </div>
              )}

              {/* Topic Selector */}
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Topic
                </label>
                <div className="relative">
                  <select
                    value={selectedTopic}
                    onChange={(e) => {
                      setSelectedTopic(e.target.value);
                      statsLoadedRef.current = false;
                    }}
                    disabled={isProcessing || loadingTopics}
                    className="w-full px-3 py-2 text-sm bg-white dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-pink-500 dark:text-gray-100"
                  >
                    {loadingTopics ? (
                      <option>Loading topics...</option>
                    ) : availableTopics.length === 0 ? (
                      <option>No topics available</option>
                    ) : (
                      availableTopics.map((t) => (
                        <option key={t.topic} value={t.topic}>
                          {t.topic} ({t.unprocessed_count} unprocessed / {t.total_articles} total)
                        </option>
                      ))
                    )}
                  </select>
                  {loadingTopics && (
                    <Loader2 className="absolute right-8 top-1/2 -translate-y-1/2 w-4 h-4 animate-spin text-gray-400" />
                  )}
                </div>
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                  Select which topic's articles to process
                </p>
              </div>

              {/* Process All Checkbox */}
              <div className="p-3 bg-amber-50 dark:bg-amber-900/20 rounded-lg border border-amber-200 dark:border-amber-800">
                <label className="flex items-start gap-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={processAll}
                    onChange={(e) => setProcessAll(e.target.checked)}
                    disabled={isProcessing}
                    className="mt-0.5 w-4 h-4 text-amber-500 border-gray-300 rounded focus:ring-amber-500"
                  />
                  <div>
                    <span className="text-sm font-medium text-amber-800 dark:text-amber-200 flex items-center gap-2">
                      <RefreshCw className="w-4 h-4" />
                      Reprocess All Articles
                    </span>
                    <p className="text-xs text-amber-600 dark:text-amber-300 mt-1">
                      Include previously processed articles. This will re-extract locations and update existing hotspots.
                    </p>
                  </div>
                </label>
              </div>

              {/* Batch Size Selector */}
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Batch Size
                </label>
                <select
                  value={batchSize}
                  onChange={(e) => setBatchSize(Number(e.target.value))}
                  disabled={isProcessing}
                  className="w-full px-3 py-2 text-sm bg-white dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-pink-500 dark:text-gray-100"
                >
                  {BATCH_SIZES.map((size) => (
                    <option key={size} value={size}>
                      {size} articles
                    </option>
                  ))}
                </select>
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                  Number of articles to process in this batch
                </p>
              </div>

              {/* Model Display */}
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  AI Model
                </label>
                <div className="px-3 py-2 text-sm bg-gray-100 dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded-lg text-gray-700 dark:text-gray-300">
                  {model}
                </div>
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                  Model selected in page header is used for location extraction
                </p>
              </div>

              {/* Import Options */}
              <div className="space-y-3 pt-4 border-t border-gray-200 dark:border-gray-700">
                <h4 className="text-sm font-medium text-gray-900 dark:text-gray-100">
                  Processing Options
                </h4>

                <label className="flex items-start gap-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={runLlmExtraction}
                    onChange={(e) => setRunLlmExtraction(e.target.checked)}
                    disabled={isProcessing}
                    className="mt-0.5 w-4 h-4 text-pink-500 border-gray-300 rounded focus:ring-pink-500"
                  />
                  <div>
                    <span className="text-sm text-gray-700 dark:text-gray-300">
                      Run LLM location extraction
                    </span>
                    <p className="text-xs text-gray-500 dark:text-gray-400">
                      Use AI to extract geographic locations from article text
                    </p>
                  </div>
                </label>

                <label className="flex items-start gap-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={regenerateNarrative}
                    onChange={(e) => setRegenerateNarrative(e.target.checked)}
                    disabled={isProcessing}
                    className="mt-0.5 w-4 h-4 text-pink-500 border-gray-300 rounded focus:ring-pink-500"
                  />
                  <div>
                    <span className="text-sm text-gray-700 dark:text-gray-300">
                      Regenerate narrative after import
                    </span>
                    <p className="text-xs text-gray-500 dark:text-gray-400">
                      Generate a new strategic intelligence briefing
                    </p>
                  </div>
                </label>
              </div>
            </div>
          )}

          {/* Processing Log */}
          {processingLog.length > 0 && !processResult && (
            <div className="mt-4 p-3 bg-gray-50 dark:bg-gray-900 rounded-lg text-xs font-mono space-y-1 max-h-32 overflow-y-auto">
              {processingLog.map((log, i) => (
                <div
                  key={i}
                  className={
                    log.includes('Error')
                      ? 'text-red-500'
                      : log.includes('complete')
                        ? 'text-green-500'
                        : 'text-gray-600 dark:text-gray-400'
                  }
                >
                  {log}
                </div>
              ))}
            </div>
          )}

          {/* Error Display */}
          {error && !processResult && (
            <div className="mt-4 flex items-center gap-2 p-3 bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300 rounded-lg text-sm">
              <AlertCircle className="w-4 h-4 flex-shrink-0" />
              {error}
            </div>
          )}
        </div>

        {/* Clear Confirmation Dialog */}
        {showClearConfirm && (
          <div className="p-4 border-t border-gray-200 dark:border-gray-700 bg-red-50 dark:bg-red-900/20">
            <div className="flex items-start gap-3 mb-4">
              <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
              <div>
                <h4 className="text-sm font-medium text-red-800 dark:text-red-200">
                  Clear All Hotspot Data?
                </h4>
                <p className="text-xs text-red-600 dark:text-red-300 mt-1">
                  This will permanently delete all {processingStats?.total_hotspots || 0} hotspots and reset processing status. This action cannot be undone.
                </p>
              </div>
            </div>
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setShowClearConfirm(false)}
                disabled={isClearing}
                className="px-3 py-1.5 text-sm text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-600 disabled:opacity-50 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleClearAllData}
                disabled={isClearing}
                className="flex items-center gap-2 px-3 py-1.5 text-sm bg-red-500 text-white rounded-lg hover:bg-red-600 disabled:opacity-50 transition-colors"
              >
                {isClearing ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Clearing...
                  </>
                ) : (
                  <>
                    <Trash2 className="w-4 h-4" />
                    Clear All Data
                  </>
                )}
              </button>
            </div>
          </div>
        )}

        {/* Footer */}
        {!processResult && !showClearConfirm && (
          <div className="flex justify-between p-4 border-t border-gray-200 dark:border-gray-700">
            {/* Clear Data Button */}
            <button
              onClick={() => setShowClearConfirm(true)}
              disabled={isProcessing || !processingStats || processingStats.total_hotspots === 0}
              className="flex items-center gap-2 px-3 py-2 text-sm text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              <Trash2 className="w-4 h-4" />
              Clear All Data
            </button>

            <div className="flex gap-3">
              <button
                onClick={handleClose}
                disabled={isProcessing}
                className="px-4 py-2 text-sm text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600 disabled:opacity-50 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => setShowScheduleModal(true)}
                disabled={isProcessing}
                className="flex items-center gap-2 px-4 py-2 text-sm text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600 disabled:opacity-50 transition-colors"
              >
                <Clock className="w-4 h-4" />
                Schedule
              </button>
              <button
                onClick={handleProcess}
                disabled={
                  isProcessing ||
                  !processingStats ||
                  (processingStats.unprocessed_articles === 0 && !processAll) ||
                  (processingStats.total_curated_articles === 0)
                }
                className="flex items-center gap-2 px-4 py-2 text-sm bg-pink-500 text-white rounded-lg hover:bg-pink-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {isProcessing ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Processing...
                  </>
                ) : processAll ? (
                  <>
                    <RefreshCw className="w-4 h-4" />
                    Reprocess Batch
                  </>
                ) : (
                  <>
                    <Play className="w-4 h-4" />
                    Process Batch
                  </>
                )}
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Schedule Modal */}
      <GeopoliticalScheduleModal
        isOpen={showScheduleModal}
        onClose={() => setShowScheduleModal(false)}
      />
    </div>
  );
}
