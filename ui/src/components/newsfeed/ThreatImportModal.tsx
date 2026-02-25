/**
 * ThreatImportModal Component
 * Modal for importing/processing articles to extract threats
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { X, Play, RefreshCw, CheckCircle, AlertCircle, Clock, FileText } from 'lucide-react';
import {
  processArticles,
  getProcessingStatus,
  getAvailableTopics,
  type ProcessingStatus,
  type AvailableTopic,
} from '../../services/threatIntelligenceApi';

interface ThreatImportModalProps {
  isOpen: boolean;
  onClose: () => void;
  onImportComplete?: () => void;
  model?: string;
}

export function ThreatImportModal({ isOpen, onClose, onImportComplete, model = 'gpt-4o-mini' }: ThreatImportModalProps) {
  const [status, setStatus] = useState<ProcessingStatus | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [articleLimit, setArticleLimit] = useState(100);
  const [selectedTopic, setSelectedTopic] = useState<string>('');
  const [processAll, setProcessAll] = useState(false);
  const [availableTopics, setAvailableTopics] = useState<AvailableTopic[]>([]);
  const [loadingTopics, setLoadingTopics] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollIntervalRef = useRef<NodeJS.Timeout | null>(null);

  // Fetch available topics when modal opens
  useEffect(() => {
    if (isOpen) {
      setLoadingTopics(true);
      getAvailableTopics()
        .then((topics) => {
          setAvailableTopics(topics);
          if (topics.length > 0 && !selectedTopic) {
            setSelectedTopic(topics[0].topic);
          }
        })
        .catch((err) => {
          console.error('Error fetching topics:', err);
        })
        .finally(() => {
          setLoadingTopics(false);
        });
    }
  }, [isOpen]);

  const fetchStatus = useCallback(async () => {
    try {
      const result = await getProcessingStatus();
      setStatus(result);

      if (result.status === 'completed' || result.status === 'failed') {
        if (pollIntervalRef.current) {
          clearInterval(pollIntervalRef.current);
          pollIntervalRef.current = null;
        }
        setIsProcessing(false);
        if (result.status === 'completed') {
          onImportComplete?.();
        }
      }
    } catch (err) {
      console.error('Error fetching status:', err);
    }
  }, [onImportComplete]);

  useEffect(() => {
    if (isOpen) {
      fetchStatus();
    }
    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
      }
    };
  }, [isOpen, fetchStatus]);

  const handleStartProcessing = async () => {
    setIsProcessing(true);
    setError(null);

    try {
      await processArticles({
        batch_size: articleLimit,
        model: model,
        topic: selectedTopic || undefined,
        process_all: processAll,
      });

      // Start polling for status
      pollIntervalRef.current = setInterval(fetchStatus, 2000);
      fetchStatus();
    } catch (err: any) {
      setError(err.message || 'Failed to start processing');
      setIsProcessing(false);
    }
  };

  const getStatusColor = (statusValue: string) => {
    switch (statusValue) {
      case 'completed':
        return 'text-green-500';
      case 'processing':
        return 'text-blue-500';
      case 'failed':
        return 'text-red-500';
      default:
        return 'text-gray-500';
    }
  };

  const getStatusIcon = (statusValue: string) => {
    switch (statusValue) {
      case 'completed':
        return <CheckCircle className="w-5 h-5 text-green-500" />;
      case 'processing':
        return <RefreshCw className="w-5 h-5 text-blue-500 animate-spin" />;
      case 'failed':
        return <AlertCircle className="w-5 h-5 text-red-500" />;
      default:
        return <Clock className="w-5 h-5 text-gray-500" />;
    }
  };

  if (!isOpen) return null;

  const progress = status?.processed && status?.total_articles
    ? Math.round((status.processed / status.total_articles) * 100)
    : 0;

  const showConfig = !status || status.status === 'idle' || status.status === 'completed' || status.status === 'failed';

  return (
    <div className="fixed inset-0 z-[9999] flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="relative bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-lg mx-4">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-700">
          <div className="flex items-center gap-2">
            <FileText className="w-5 h-5 text-red-500" />
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
              Process Articles for Threats
            </h2>
          </div>
          <button
            onClick={onClose}
            className="p-1 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
          >
            <X className="w-5 h-5 text-gray-500" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-6">
          {/* Configuration */}
          {showConfig && (
            <div className="space-y-4">
              {/* Topic Selector */}
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Topic
                </label>
                <select
                  value={selectedTopic}
                  onChange={(e) => setSelectedTopic(e.target.value)}
                  disabled={loadingTopics}
                  className="w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-red-500 dark:text-gray-100"
                >
                  <option value="">All Topics</option>
                  {availableTopics.map((t) => (
                    <option key={t.topic} value={t.topic}>
                      {t.topic} ({t.total_articles} articles, {t.unprocessed_count} unprocessed)
                    </option>
                  ))}
                </select>
                <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                  Select a topic to process articles from, or leave empty for all topics
                </p>
              </div>

              {/* Article Limit */}
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Maximum Articles
                </label>
                <input
                  type="number"
                  min={10}
                  max={500}
                  value={articleLimit}
                  onChange={(e) => setArticleLimit(Number(e.target.value))}
                  className="w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-red-500 dark:text-gray-100"
                />
                <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                  Maximum number of articles to analyze (10-500)
                </p>
              </div>

              {/* Process All Toggle */}
              <div className="flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                <div>
                  <div className="text-sm font-medium text-gray-700 dark:text-gray-300">
                    Reprocess All Articles
                  </div>
                  <div className="text-xs text-gray-500 dark:text-gray-400">
                    {processAll
                      ? 'Will reprocess articles even if already analyzed'
                      : 'Only process articles not yet analyzed'}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setProcessAll(!processAll)}
                  className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                    processAll ? 'bg-red-500' : 'bg-gray-300 dark:bg-gray-600'
                  }`}
                >
                  <span
                    className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                      processAll ? 'translate-x-6' : 'translate-x-1'
                    }`}
                  />
                </button>
              </div>
            </div>
          )}

          {/* Processing Status */}
          {status && (status.status === 'processing' || status.status === 'completed' || status.status === 'failed') && (
            <div className="space-y-4">
              {/* Status Header */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  {getStatusIcon(status.status)}
                  <span className={`font-medium capitalize ${getStatusColor(status.status)}`}>
                    {status.status}
                  </span>
                </div>
                {status.status === 'processing' && (
                  <span className="text-sm text-gray-500 dark:text-gray-400">
                    {progress}%
                  </span>
                )}
              </div>

              {/* Progress Bar */}
              {status.status === 'processing' && (
                <div className="w-full h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-red-500 transition-all duration-500"
                    style={{ width: `${progress}%` }}
                  />
                </div>
              )}

              {/* Stats */}
              <div className="grid grid-cols-4 gap-3">
                <div className="p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg text-center">
                  <div className="text-xl font-bold text-gray-900 dark:text-gray-100">
                    {status.processed || 0}
                  </div>
                  <div className="text-xs text-gray-500 dark:text-gray-400">Processed</div>
                </div>
                <div className="p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg text-center">
                  <div className="text-xl font-bold text-red-600">
                    {status.threats_extracted || 0}
                  </div>
                  <div className="text-xs text-gray-500 dark:text-gray-400">Threats</div>
                </div>
                <div className="p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg text-center">
                  <div className="text-xl font-bold text-orange-600">
                    {status.actors_identified || 0}
                  </div>
                  <div className="text-xs text-gray-500 dark:text-gray-400">Actors</div>
                </div>
                <div className="p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg text-center">
                  <div className="text-xl font-bold text-blue-600">
                    {status.iocs_extracted || 0}
                  </div>
                  <div className="text-xs text-gray-500 dark:text-gray-400">IOCs</div>
                </div>
              </div>

              {/* Current Article */}
              {status.status === 'processing' && status.current_article && (
                <div className="p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg">
                  <div className="text-xs text-blue-600 dark:text-blue-400 font-medium mb-1">
                    Currently Processing
                  </div>
                  <div className="text-sm text-gray-700 dark:text-gray-300 line-clamp-2">
                    {status.current_article}
                  </div>
                </div>
              )}

              {/* Completion Message */}
              {status.status === 'completed' && (
                <div className="p-4 bg-green-50 dark:bg-green-900/20 rounded-lg">
                  <div className="flex items-center gap-2 text-green-700 dark:text-green-300">
                    <CheckCircle className="w-5 h-5" />
                    <span className="font-medium">Processing Complete</span>
                  </div>
                  <p className="mt-2 text-sm text-green-600 dark:text-green-400">
                    Successfully extracted {status.threats_extracted} threats from {status.processed} articles.
                  </p>
                </div>
              )}

              {/* Error Message */}
              {status.status === 'failed' && status.error && (
                <div className="p-4 bg-red-50 dark:bg-red-900/20 rounded-lg">
                  <div className="flex items-center gap-2 text-red-700 dark:text-red-300">
                    <AlertCircle className="w-5 h-5" />
                    <span className="font-medium">Processing Failed</span>
                  </div>
                  <p className="mt-2 text-sm text-red-600 dark:text-red-400">
                    {status.error}
                  </p>
                </div>
              )}
            </div>
          )}

          {/* Error */}
          {error && (
            <div className="p-4 bg-red-50 dark:bg-red-900/20 rounded-lg">
              <div className="flex items-center gap-2 text-red-700 dark:text-red-300">
                <AlertCircle className="w-5 h-5" />
                <span>{error}</span>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 p-4 border-t border-gray-200 dark:border-gray-700">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
          >
            {status?.status === 'completed' ? 'Close' : 'Cancel'}
          </button>

          {showConfig && (
            <button
              onClick={handleStartProcessing}
              disabled={isProcessing}
              className="flex items-center gap-2 px-4 py-2 text-sm bg-red-500 text-white rounded-lg hover:bg-red-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {isProcessing ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  Starting...
                </>
              ) : (
                <>
                  <Play className="w-4 h-4" />
                  Start Processing
                </>
              )}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
