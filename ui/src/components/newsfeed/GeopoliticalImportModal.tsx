/**
 * Geopolitical Import Modal Component
 * Provides batch processing of articles to extract geopolitical hotspots
 * Styled to match Brand Watcher's classify modal
 */

import { useState, useCallback, useEffect, useRef } from 'react';
import { X, Loader2, AlertCircle, Play, Trash2, Clock, Zap, Calendar, RefreshCw } from 'lucide-react';
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

export function GeopoliticalImportModal({
  isOpen,
  onClose,
  onImportComplete,
  model = 'gpt-5.4-mini',
}: GeopoliticalImportModalProps) {
  const [selectedTopic, setSelectedTopic] = useState<string>('');
  const [availableTopics, setAvailableTopics] = useState<AvailableTopic[]>([]);
  const [loadingTopics, setLoadingTopics] = useState(false);
  const [processingStats, setProcessingStats] = useState<ProcessingStats | null>(null);
  const [loadingStats, setLoadingStats] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [processResult, setProcessResult] = useState<ProcessResult | null>(null);
  const [statusMessage, setStatusMessage] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [showScheduleModal, setShowScheduleModal] = useState(false);
  const [showClearConfirm, setShowClearConfirm] = useState(false);
  const [isClearing, setIsClearing] = useState(false);

  const statsLoadedRef = useRef(false);
  const topicsLoadedRef = useRef(false);
  const pollingIntervalRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    if (isOpen && !topicsLoadedRef.current && !loadingTopics) {
      topicsLoadedRef.current = true;
      fetchAvailableTopics();
    }
  }, [isOpen, loadingTopics]);

  useEffect(() => {
    if (isOpen && !loadingStats) {
      if (!statsLoadedRef.current || selectedTopic !== (processingStats?.topic || '')) {
        statsLoadedRef.current = true;
        fetchProcessingStats();
      }
    }
  }, [isOpen, loadingStats, selectedTopic]);

  useEffect(() => {
    if (!isOpen) {
      statsLoadedRef.current = false;
      topicsLoadedRef.current = false;
      setProcessResult(null);
      setError(null);
      setStatusMessage('');
      setShowClearConfirm(false);
      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current);
        pollingIntervalRef.current = null;
      }
    }
  }, [isOpen]);

  useEffect(() => {
    return () => {
      if (pollingIntervalRef.current) clearInterval(pollingIntervalRef.current);
    };
  }, []);

  const fetchAvailableTopics = async () => {
    setLoadingTopics(true);
    try {
      const response = await fetch('/api/geopolitical-hotspots/available-topics');
      if (response.ok) {
        const data = await response.json();
        setAvailableTopics(data.topics || []);
        if (data.topics?.length > 0 && !selectedTopic) {
          const geoTopic = data.topics.find((t: AvailableTopic) => t.topic === 'Geopolitical Hotspots');
          setSelectedTopic(geoTopic ? geoTopic.topic : data.topics[0].topic);
        }
      } else {
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
        statsLoadedRef.current = false;
      }
    } catch (err) {
      console.error('Failed to fetch processing stats:', err);
      statsLoadedRef.current = false;
    } finally {
      setLoadingStats(false);
    }
  };

  const pollProcessingStatus = useCallback(async () => {
    try {
      const response = await fetch('/api/geopolitical-hotspots/process-articles/status');
      if (!response.ok) return;
      const status = await response.json();

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

      if (status.progress && status.total) {
        setStatusMessage(`Processing ${status.progress}/${status.total} articles...`);
      }

      if (status.completed || (!status.running && status.progress === status.total)) {
        if (pollingIntervalRef.current) {
          clearInterval(pollingIntervalRef.current);
          pollingIntervalRef.current = null;
        }
        setIsProcessing(false);
        setStatusMessage(`Done: ${status.processed || 0} processed, ${status.created || 0} created, ${status.updated || 0} updated`);
        await fetchProcessingStats();
        if (onImportComplete) onImportComplete();
      }
    } catch (err) {
      console.error('Error polling processing status:', err);
    }
  }, [fetchProcessingStats, onImportComplete]);

  const handleProcess = useCallback(async (mode: 'incremental' | 'full', batchSize: number) => {
    setError(null);
    setIsProcessing(true);
    setProcessResult(null);
    const processAll = mode === 'full';
    const modeLabel = processAll ? 'full reprocess' : 'incremental';
    setStatusMessage(`Starting ${modeLabel} (${batchSize} articles)...`);

    try {
      const response = await fetch('/api/geopolitical-hotspots/process-articles', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          batch_size: batchSize,
          model,
          topic: selectedTopic || undefined,
          process_all: processAll,
        }),
      });

      const contentType = response.headers.get('content-type');
      if (!contentType || !contentType.includes('application/json')) {
        const text = await response.text();
        if (response.status === 401 || response.status === 307) {
          throw new Error('Session expired. Please refresh the page and log in again.');
        }
        throw new Error(`Server returned non-JSON response (${response.status}): ${text.slice(0, 100)}...`);
      }

      const result = await response.json();

      if (response.status === 401) {
        throw new Error('Session expired. Please refresh the page and log in again.');
      }

      if (response.ok) {
        if (result.status === 'started' || result.status === 'running') {
          setStatusMessage(result.message || 'Processing started in background...');
          pollingIntervalRef.current = setInterval(pollProcessingStatus, 2000);
        } else {
          setProcessResult(result);
          setStatusMessage(`Done: ${result.articles_processed} processed, ${result.hotspots_created} created, ${result.hotspots_updated} updated`);
          await fetchProcessingStats();
          setIsProcessing(false);
          if (onImportComplete) onImportComplete();
        }
      } else {
        const detail = result.detail;
        setError(typeof detail === 'string' ? detail : Array.isArray(detail) ? detail.map((d: any) => d.msg || JSON.stringify(d)).join('; ') : 'Processing failed');
        setIsProcessing(false);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Processing failed');
      setIsProcessing(false);
    }
  }, [model, selectedTopic, onImportComplete, pollProcessingStatus]);

  const handleClearAllData = useCallback(async () => {
    setIsClearing(true);
    setError(null);
    try {
      const response = await fetch('/api/geopolitical-hotspots/clear-hotspots', { method: 'DELETE' });
      if (response.ok) {
        setShowClearConfirm(false);
        await fetchProcessingStats();
        if (onImportComplete) onImportComplete();
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
    if (!isProcessing && !isClearing) onClose();
  }, [isProcessing, isClearing, onClose]);

  if (!isOpen) return null;

  const unprocessedCount = processingStats?.unprocessed_articles || 0;
  const totalCount = processingStats?.total_curated_articles || 0;

  return (
    <div className="fixed inset-0 z-[1100] flex items-center justify-center">
      <div className="absolute inset-0 bg-black/50" onClick={handleClose} />
      <div className="relative bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-lg max-h-[85vh] overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-700">
          <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100">Update Hotspots</h3>
          <button onClick={handleClose} disabled={isProcessing}
            className="text-gray-500 hover:text-gray-600 disabled:opacity-50"><X className="w-5 h-5" /></button>
        </div>

        <div className="p-4 overflow-y-auto max-h-[70vh] space-y-5">
          {/* Description */}
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Extract geopolitical hotspots from curated articles using AI.
            {processingStats && ` ${unprocessedCount} unprocessed of ${totalCount} total articles.`}
          </p>

          {/* Topic selector */}
          <div>
            <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Topic</label>
            <select
              value={selectedTopic}
              onChange={(e) => { setSelectedTopic(e.target.value); statsLoadedRef.current = false; }}
              disabled={isProcessing || loadingTopics}
              className="w-full px-3 py-2 text-sm bg-white dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded-lg dark:text-gray-100"
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
          </div>

          {/* Run Now section */}
          <div>
            <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3 flex items-center gap-2">
              <Zap className="w-4 h-4" /> Run Now
            </h4>
            <div className="space-y-2">
              <button onClick={() => handleProcess('incremental', unprocessedCount || 50)}
                disabled={isProcessing || unprocessedCount === 0}
                className="w-full px-4 py-2.5 text-sm bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 disabled:opacity-50 flex items-center justify-center gap-2">
                <Clock className="w-4 h-4" /> Incremental — {unprocessedCount} New Articles
              </button>
              <button onClick={() => handleProcess('incremental', 50)}
                disabled={isProcessing || unprocessedCount === 0}
                className="w-full px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50">
                Incremental (batch of 50)
              </button>
              <button onClick={() => handleProcess('incremental', 200)}
                disabled={isProcessing || unprocessedCount === 0}
                className="w-full px-4 py-2 text-sm bg-blue-500 text-white rounded-lg hover:bg-blue-600 disabled:opacity-50">
                Incremental (batch of 200)
              </button>
              <button onClick={() => handleProcess('full', 500)}
                disabled={isProcessing || totalCount === 0}
                className="w-full px-4 py-2 text-sm bg-orange-500 text-white rounded-lg hover:bg-orange-600 disabled:opacity-50">
                Full Reprocess (batch of 500)
              </button>
            </div>
          </div>

          {/* Status / progress */}
          {(statusMessage || isProcessing) && (
            <div className="p-3 bg-gray-50 dark:bg-gray-750 rounded-lg text-sm text-gray-600 dark:text-gray-300 flex items-center gap-2">
              {isProcessing && <Loader2 className="w-4 h-4 animate-spin flex-shrink-0" />}
              {statusMessage}
              {processResult?.running && processResult.total && processResult.total > 0 && (
                <div className="flex-1">
                  <div className="w-full bg-blue-200 dark:bg-blue-800 rounded-full h-1.5 ml-2">
                    <div className="bg-blue-500 h-1.5 rounded-full transition-all duration-300"
                      style={{ width: `${((processResult.progress || 0) / processResult.total) * 100}%` }} />
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Error */}
          {error && (
            <div className="flex items-center gap-2 p-3 bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300 rounded-lg text-sm">
              <AlertCircle className="w-4 h-4 flex-shrink-0" />
              {error}
            </div>
          )}

          {/* Scheduling section */}
          <div className="border-t border-gray-200 dark:border-gray-700 pt-4">
            <div className="flex items-center justify-between mb-3">
              <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 flex items-center gap-2">
                <Calendar className="w-4 h-4" /> Schedules
              </h4>
              <button onClick={() => setShowScheduleModal(true)}
                className="text-xs px-2 py-1 bg-blue-50 dark:bg-blue-900/20 text-blue-600 dark:text-blue-400 rounded hover:bg-blue-100">
                Configure
              </button>
            </div>
            <p className="text-xs text-gray-400 dark:text-gray-500">
              Use the schedule configuration to set up automated processing runs.
            </p>
          </div>

          {/* Clear data section */}
          <div className="border-t border-gray-200 dark:border-gray-700 pt-4">
            {!showClearConfirm ? (
              <button
                onClick={() => setShowClearConfirm(true)}
                disabled={isProcessing || !processingStats || processingStats.total_hotspots === 0}
                className="text-xs text-red-500 hover:text-red-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Clear all hotspot data ({processingStats?.total_hotspots || 0} hotspots)
              </button>
            ) : (
              <div className="p-3 bg-red-50 dark:bg-red-900/20 rounded-lg">
                <p className="text-xs text-red-600 dark:text-red-300 mb-2">
                  This will permanently delete all {processingStats?.total_hotspots || 0} hotspots. This cannot be undone.
                </p>
                <div className="flex justify-end gap-2">
                  <button onClick={() => setShowClearConfirm(false)} disabled={isClearing}
                    className="px-3 py-1.5 text-xs text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded-lg hover:bg-gray-50 disabled:opacity-50">
                    Cancel
                  </button>
                  <button onClick={handleClearAllData} disabled={isClearing}
                    className="flex items-center gap-1 px-3 py-1.5 text-xs bg-red-500 text-white rounded-lg hover:bg-red-600 disabled:opacity-50">
                    {isClearing ? <Loader2 className="w-3 h-3 animate-spin" /> : <Trash2 className="w-3 h-3" />}
                    Confirm Delete
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      <GeopoliticalScheduleModal
        isOpen={showScheduleModal}
        onClose={() => setShowScheduleModal(false)}
      />
    </div>
  );
}
