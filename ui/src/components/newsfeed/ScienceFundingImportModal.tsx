/**
 * ScienceWatch Classify Articles Modal
 * Matches the Brand Watcher classify modal pattern exactly
 */

import { useState, useCallback, useRef, useEffect } from 'react';
import { X, Loader2, AlertCircle, Clock, Zap, Calendar, Upload, Globe, FileText, ChevronDown, ChevronRight } from 'lucide-react';
import { ScienceScheduleModal } from './ScienceScheduleModal';
import {
  runClassification,
  getClassifyStatus,
  uploadCSVFile,
  importFromURL,
  getImportStatus,
  type ImportStatus,
  type ClassificationRun,
  DEFAULT_SCIENCE_TOPIC,
} from '../../services/scienceFundingApi';

interface TopicItem {
  topic: string;
  article_count: number;
}

interface ScienceFundingImportModalProps {
  isOpen: boolean;
  onClose: () => void;
  onImportComplete?: () => void;
  topic?: string;
  daysBack?: number;
}

export function ScienceFundingImportModal({
  isOpen,
  onClose,
  onImportComplete,
  topic: defaultTopic = DEFAULT_SCIENCE_TOPIC,
  daysBack = 365,
}: ScienceFundingImportModalProps) {
  // Topics state
  const [topics, setTopics] = useState<TopicItem[]>([]);
  const [selectedTopics, setSelectedTopics] = useState<string[]>([]);

  // Classification state
  const [classifyStatus, setClassifyStatus] = useState('');
  const [isProcessing, setIsProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Import data section (collapsed by default)
  const [showImportSection, setShowImportSection] = useState(false);
  const [importMode, setImportMode] = useState<'url' | 'file'>('url');
  const [fetchFromTracker, setFetchFromTracker] = useState(false);
  const [customUrl, setCustomUrl] = useState('');
  const [startDate, setStartDate] = useState('2025-01-20');
  const [endDate, setEndDate] = useState(new Date().toISOString().split('T')[0]);
  const [file, setFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [importId, setImportId] = useState<number | null>(null);
  const [importStatus, setImportStatus] = useState<ImportStatus | null>(null);

  // Schedule modal
  const [showScheduleModal, setShowScheduleModal] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const pollIntervalRef = useRef<NodeJS.Timeout | null>(null);

  // Fetch topics when modal opens
  useEffect(() => {
    if (isOpen) {
      fetch('/api/brand-watcher/topics', { credentials: 'include' })
        .then(r => r.ok ? r.json() : [])
        .then((data: TopicItem[]) => setTopics(data))
        .catch(() => setTopics([]));
    }
  }, [isOpen]);

  // Reset on close
  useEffect(() => {
    if (!isOpen) {
      setClassifyStatus('');
      setError(null);
      setFile(null);
      setShowImportSection(false);
      setImportId(null);
      setImportStatus(null);
      setIsProcessing(false);
      setSelectedTopics([]);
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
        pollIntervalRef.current = null;
      }
    }
  }, [isOpen]);

  // Poll for import status (for URL/file imports)
  useEffect(() => {
    if (importId && isProcessing) {
      const pollStatus = async () => {
        try {
          const status = await getImportStatus(importId);
          setImportStatus(status);
          if (status.status === 'completed' || status.status === 'failed') {
            setIsProcessing(false);
            if (pollIntervalRef.current) {
              clearInterval(pollIntervalRef.current);
              pollIntervalRef.current = null;
            }
            if (status.status === 'completed') {
              setClassifyStatus(`Done: ${status.articles_created} articles created, ${status.categories_added} categories added`);
              if (onImportComplete) onImportComplete();
            } else {
              setClassifyStatus('Import failed');
            }
          } else {
            setClassifyStatus(`Processing... ${status.rows_processed} rows processed`);
          }
        } catch (err) {
          console.error('Failed to poll import status:', err);
        }
      };
      pollIntervalRef.current = setInterval(pollStatus, 2000);
      pollStatus();
      return () => { if (pollIntervalRef.current) clearInterval(pollIntervalRef.current); };
    }
  }, [importId, isProcessing, onImportComplete]);

  // Cleanup on unmount
  useEffect(() => {
    return () => { if (pollIntervalRef.current) clearInterval(pollIntervalRef.current); };
  }, []);

  // --- Classify (matches Brand Watcher pattern) ---
  const handleClassify = useCallback(async (runType: string = 'incremental', days: number = 30) => {
    const topicsToRun = selectedTopics.length > 0 ? selectedTopics : [defaultTopic];
    setError(null);
    setIsProcessing(true);
    setClassifyStatus(`running ${topicsToRun.length} topic(s)...`);

    let totalProcessed = 0;
    let totalCategorized = 0;

    try {
      for (let i = 0; i < topicsToRun.length; i++) {
        const t = topicsToRun[i];
        setClassifyStatus(`Running topic ${i + 1}/${topicsToRun.length}: ${t}...`);

        const res = await runClassification({
          topic: t,
          run_type: runType,
          days_back: days,
        });

        // Poll until this topic completes
        await new Promise<void>((resolve, reject) => {
          const poll = setInterval(async () => {
            try {
              const status = await getClassifyStatus(res.run_id);
              setClassifyStatus(`Topic ${i + 1}/${topicsToRun.length} "${t}": ${status.status} - ${status.articles_processed} processed, ${status.articles_categorized} categorized`);
              if (status.status === 'completed' || status.status === 'failed') {
                clearInterval(poll);
                totalProcessed += status.articles_processed;
                totalCategorized += status.articles_categorized;
                resolve();
              }
            } catch {
              clearInterval(poll);
              reject(new Error(`Failed to get status for topic ${t}`));
            }
          }, 2000);
          pollIntervalRef.current = poll;
        });
      }

      setClassifyStatus(`Done: ${totalProcessed} processed, ${totalCategorized} categorized across ${topicsToRun.length} topic(s)`);
      setIsProcessing(false);
      if (onImportComplete) onImportComplete();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Classification failed');
      setIsProcessing(false);
      setClassifyStatus('');
    }
  }, [selectedTopics, defaultTopic, onImportComplete]);

  // Handle URL/File import (secondary action)
  const handleImportData = useCallback(async () => {
    setError(null);
    setIsProcessing(true);
    setClassifyStatus('Starting import...');

    try {
      let result;
      if (importMode === 'file') {
        if (!file) { setError('Please select a CSV file'); setIsProcessing(false); return; }
        result = await uploadCSVFile(file, { topic: defaultTopic, runLlmClassification: true, regenerateNarrative: false });
      } else {
        result = await importFromURL({
          url: fetchFromTracker ? undefined : customUrl || undefined,
          start_date: fetchFromTracker ? startDate : undefined,
          end_date: fetchFromTracker ? endDate : undefined,
          topic: defaultTopic,
          run_llm_classification: true,
          regenerate_narrative: false,
        });
      }
      setImportId(result.import_id);
      setClassifyStatus('Import started...');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Import failed');
      setIsProcessing(false);
    }
  }, [importMode, file, fetchFromTracker, customUrl, startDate, endDate, defaultTopic]);

  const handleFileSelect = useCallback((selectedFile: File) => {
    if (selectedFile.type === 'text/csv' || selectedFile.name.endsWith('.csv')) {
      setFile(selectedFile);
      setError(null);
    } else {
      setError('Please select a CSV file');
    }
  }, []);

  const handleClose = useCallback(() => {
    if (!isProcessing) onClose();
  }, [isProcessing, onClose]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[1100] flex items-center justify-center">
      <div className="absolute inset-0 bg-black/50" onClick={handleClose} />
      <div className="relative bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-lg max-h-[85vh] overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-700">
          <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100">Classify Articles</h3>
          <button onClick={() => { handleClose(); setClassifyStatus(''); }}
            className="text-gray-500 hover:text-gray-600 disabled:opacity-50"><X className="w-5 h-5" /></button>
        </div>

        <div className="p-4 overflow-y-auto max-h-[70vh] space-y-5">
          {/* Description */}
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Run ML classification on ScienceWatch articles to categorize them into science funding topics.
            {selectedTopics.length > 0 && ` | ${selectedTopics.length} topic${selectedTopics.length !== 1 ? 's' : ''} selected`}
          </p>

          {/* Topic multi-select */}
          <div>
            <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">
              Topics to classify ({selectedTopics.length} selected)
            </label>
            <div className="max-h-40 overflow-y-auto border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 p-2 space-y-1">
              {topics.map(t => (
                <label key={t.topic} className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-750 rounded px-1 py-0.5 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={selectedTopics.includes(t.topic)}
                    onChange={e => {
                      const next = e.target.checked
                        ? [...selectedTopics, t.topic]
                        : selectedTopics.filter(s => s !== t.topic);
                      setSelectedTopics(next);
                    }}
                    className="rounded border-gray-300 dark:border-gray-600"
                  />
                  <span className="flex-1 truncate">{t.topic}</span>
                  <span className="text-xs text-gray-400 flex-shrink-0">{t.article_count}</span>
                </label>
              ))}
              {topics.length === 0 && (
                <p className="text-xs text-gray-400 dark:text-gray-500 italic">Loading topics...</p>
              )}
            </div>
            {selectedTopics.length > 0 && (
              <button
                onClick={() => setSelectedTopics([])}
                className="mt-1 text-xs text-blue-500 hover:text-blue-700"
              >
                Clear all
              </button>
            )}
          </div>

          {/* Run Now section */}
          <div>
            <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3 flex items-center gap-2">
              <Zap className="w-4 h-4" /> Run Now
            </h4>
            <div className="space-y-2">
              <button onClick={() => handleClassify('incremental', 30)}
                disabled={isProcessing}
                className="w-full px-4 py-2.5 text-sm bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 disabled:opacity-50 flex items-center justify-center gap-2">
                <Clock className="w-4 h-4" /> Incremental (last 30 days)
              </button>
              <button onClick={() => handleClassify('incremental', 90)}
                disabled={isProcessing}
                className="w-full px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50">
                Incremental (last 90 days)
              </button>
              <button onClick={() => handleClassify('incremental', 365)}
                disabled={isProcessing}
                className="w-full px-4 py-2 text-sm bg-blue-500 text-white rounded-lg hover:bg-blue-600 disabled:opacity-50">
                Incremental (last year)
              </button>
              <button onClick={() => handleClassify('full', 365)}
                disabled={isProcessing}
                className="w-full px-4 py-2 text-sm bg-orange-500 text-white rounded-lg hover:bg-orange-600 disabled:opacity-50">
                Full Reclassify (last year)
              </button>
            </div>
          </div>

          {/* Status */}
          {classifyStatus && (
            <div className="p-3 bg-gray-50 dark:bg-gray-750 rounded-lg text-sm text-gray-600 dark:text-gray-300 flex items-center gap-2">
              {classifyStatus.includes('running') && <Loader2 className="w-4 h-4 animate-spin flex-shrink-0" />}
              {classifyStatus}
            </div>
          )}

          {/* Error */}
          {error && (
            <div className="flex items-center gap-2 p-3 bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300 rounded-lg text-sm">
              <AlertCircle className="w-4 h-4 flex-shrink-0" />
              {error}
            </div>
          )}

          {/* Import Data section (collapsible) */}
          <div className="border-t border-gray-200 dark:border-gray-700 pt-4">
            <button
              onClick={() => setShowImportSection(!showImportSection)}
              className="flex items-center gap-2 text-sm font-semibold text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-gray-100"
            >
              {showImportSection ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
              <Upload className="w-4 h-4" /> Import Data
            </button>
            <p className="text-xs text-gray-400 dark:text-gray-500 mt-1 ml-6">
              Import articles from URL or CSV file
            </p>

            {showImportSection && (
              <div className="mt-3 space-y-3 ml-6">
                <div className="flex gap-2">
                  <button onClick={() => setImportMode('url')}
                    className={`flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg transition-colors ${
                      importMode === 'url' ? 'bg-emerald-500 text-white' : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300'
                    }`}>
                    <Globe className="w-3.5 h-3.5" /> URL
                  </button>
                  <button onClick={() => setImportMode('file')}
                    className={`flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg transition-colors ${
                      importMode === 'file' ? 'bg-emerald-500 text-white' : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300'
                    }`}>
                    <FileText className="w-3.5 h-3.5" /> File
                  </button>
                </div>

                {importMode === 'url' && (
                  <div className="space-y-2">
                    <label className="flex items-start gap-2 p-2 bg-emerald-50 dark:bg-emerald-900/20 rounded-lg cursor-pointer text-xs">
                      <input type="checkbox" checked={fetchFromTracker}
                        onChange={(e) => setFetchFromTracker(e.target.checked)}
                        className="mt-0.5 w-3.5 h-3.5 text-emerald-500 border-gray-300 rounded" />
                      <span className="text-gray-700 dark:text-gray-300">Fetch from Science Data Source</span>
                    </label>
                    {fetchFromTracker ? (
                      <div className="grid grid-cols-2 gap-2">
                        <div>
                          <label className="block text-xs text-gray-400 mb-0.5">Start</label>
                          <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)}
                            className="w-full px-2 py-1.5 text-xs bg-white dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded-lg dark:text-gray-100" />
                        </div>
                        <div>
                          <label className="block text-xs text-gray-400 mb-0.5">End</label>
                          <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)}
                            className="w-full px-2 py-1.5 text-xs bg-white dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded-lg dark:text-gray-100" />
                        </div>
                      </div>
                    ) : (
                      <input type="url" value={customUrl} onChange={(e) => setCustomUrl(e.target.value)}
                        placeholder="https://example.com/science-data.csv"
                        className="w-full px-2 py-1.5 text-xs bg-white dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded-lg dark:text-gray-100" />
                    )}
                  </div>
                )}

                {importMode === 'file' && (
                  <div
                    onDrop={(e) => { e.preventDefault(); setIsDragging(false); if (e.dataTransfer.files[0]) handleFileSelect(e.dataTransfer.files[0]); }}
                    onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
                    onDragLeave={(e) => { e.preventDefault(); setIsDragging(false); }}
                    onClick={() => fileInputRef.current?.click()}
                    className={`border-2 border-dashed rounded-lg p-4 text-center cursor-pointer text-xs transition-colors ${
                      isDragging ? 'border-emerald-500 bg-emerald-50 dark:bg-emerald-900/20'
                        : 'border-gray-300 dark:border-gray-600 hover:border-emerald-400'
                    }`}
                  >
                    <input ref={fileInputRef} type="file" accept=".csv,text/csv"
                      onChange={(e) => { if (e.target.files?.[0]) handleFileSelect(e.target.files[0]); }}
                      className="hidden" />
                    {file ? (
                      <div className="flex items-center justify-center gap-2">
                        <FileText className="w-5 h-5 text-emerald-500" />
                        <div className="text-left">
                          <p className="font-medium text-gray-900 dark:text-gray-100">{file.name}</p>
                          <p className="text-gray-500">{(file.size / 1024).toFixed(1)} KB</p>
                        </div>
                      </div>
                    ) : (
                      <p className="text-gray-500 dark:text-gray-400">Drop a CSV file here or click to browse</p>
                    )}
                  </div>
                )}

                <button onClick={handleImportData}
                  disabled={isProcessing || (importMode === 'file' && !file) || (importMode === 'url' && !fetchFromTracker && !customUrl)}
                  className="w-full px-3 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 flex items-center justify-center gap-2">
                  <Upload className="w-4 h-4" /> Import & Classify
                </button>
              </div>
            )}
          </div>

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
              Use the schedule configuration to set up automated classification runs.
            </p>
          </div>
        </div>
      </div>

      <ScienceScheduleModal
        isOpen={showScheduleModal}
        onClose={() => setShowScheduleModal(false)}
        onScheduleRun={onImportComplete}
        topic={defaultTopic}
      />
    </div>
  );
}
