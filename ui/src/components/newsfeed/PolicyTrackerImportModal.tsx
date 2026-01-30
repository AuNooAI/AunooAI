/**
 * Policy Tracker Import Modal Component
 * Provides file upload and URL import functionality with options for ML classification
 * Uses RoBERTa + DeBERTa ensemble classifier (F1: 0.9558) for policy categorization
 */

import { useState, useCallback, useRef, useEffect, useMemo } from 'react';
import { X, Upload, Globe, Loader2, CheckCircle, AlertCircle, FileText, Database } from 'lucide-react';
import {
  uploadCSVFile,
  importFromURL,
  getImportStatus,
  getFeedKeywordGroups,
  importFromFeed,
  type ImportStatus,
  type FeedKeywordGroup,
  DEFAULT_TRACKER_TOPIC,
} from '../../services/policyTrackerApi';

interface PolicyTrackerImportModalProps {
  isOpen: boolean;
  onClose: () => void;
  onImportComplete?: () => void;
  topic?: string;
}

type ImportTab = 'file' | 'url' | 'database';

export function PolicyTrackerImportModal({
  isOpen,
  onClose,
  onImportComplete,
  topic = DEFAULT_TRACKER_TOPIC,
}: PolicyTrackerImportModalProps) {
  const [activeTab, setActiveTab] = useState<ImportTab>('url');
  const [file, setFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);

  // URL import options
  const [fetchFromTracker, setFetchFromTracker] = useState(true);
  const [customUrl, setCustomUrl] = useState('');
  const [startDate, setStartDate] = useState('2025-01-20');
  const [endDate, setEndDate] = useState(new Date().toISOString().split('T')[0]);

  // Database import options
  const [feedKeywordGroups, setFeedKeywordGroups] = useState<FeedKeywordGroup[]>([]);
  const [selectedGroupId, setSelectedGroupId] = useState<number | null>(null);
  const [loadingGroups, setLoadingGroups] = useState(false);

  // Common options
  const [runLlmClassification, setRunLlmClassification] = useState(false);
  const [regenerateNarrative, setRegenerateNarrative] = useState(false);

  // Import state
  const [isImporting, setIsImporting] = useState(false);
  const [importId, setImportId] = useState<number | null>(null);
  const [importStatus, setImportStatus] = useState<ImportStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const pollIntervalRef = useRef<NodeJS.Timeout | null>(null);

  // Poll for import status
  useEffect(() => {
    if (importId && isImporting) {
      const pollStatus = async () => {
        try {
          const status = await getImportStatus(importId);
          setImportStatus(status);

          if (status.status === 'completed' || status.status === 'failed') {
            setIsImporting(false);
            if (pollIntervalRef.current) {
              clearInterval(pollIntervalRef.current);
              pollIntervalRef.current = null;
            }
            if (status.status === 'completed' && onImportComplete) {
              onImportComplete();
            }
          }
        } catch (err) {
          console.error('Failed to poll import status:', err);
        }
      };

      pollIntervalRef.current = setInterval(pollStatus, 2000);
      pollStatus(); // Initial poll

      return () => {
        if (pollIntervalRef.current) {
          clearInterval(pollIntervalRef.current);
        }
      };
    }
  }, [importId, isImporting, onImportComplete]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
      }
    };
  }, []);

  // Track if we've already loaded groups to prevent infinite loops
  const groupsLoadedRef = useRef(false);

  // Load feed keyword groups when switching to database tab
  useEffect(() => {
    if (activeTab === 'database' && !groupsLoadedRef.current && !loadingGroups) {
      groupsLoadedRef.current = true;
      const loadGroups = async () => {
        setLoadingGroups(true);
        try {
          const response = await getFeedKeywordGroups();
          setFeedKeywordGroups(response.groups);
          // Auto-select Trump Administration Tracker if available, otherwise first group
          if (response.groups.length > 0) {
            const trumpGroup = response.groups.find(g => g.name === 'Trump Administration Tracker');
            setSelectedGroupId(trumpGroup?.id ?? response.groups[0].id);
          }
        } catch (err) {
          console.error('Failed to load feed keyword groups:', err);
          setError('Failed to load feed keyword groups');
          groupsLoadedRef.current = false; // Allow retry on error
        } finally {
          setLoadingGroups(false);
        }
      };
      loadGroups();
    }
  }, [activeTab, loadingGroups]);

  const handleFileSelect = useCallback((selectedFile: File) => {
    if (selectedFile.type === 'text/csv' || selectedFile.name.endsWith('.csv')) {
      setFile(selectedFile);
      setError(null);
    } else {
      setError('Please select a CSV file');
    }
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);

    const droppedFile = e.dataTransfer.files[0];
    if (droppedFile) {
      handleFileSelect(droppedFile);
    }
  }, [handleFileSelect]);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const handleFileInputChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0];
    if (selectedFile) {
      handleFileSelect(selectedFile);
    }
  }, [handleFileSelect]);

  const handleImport = useCallback(async () => {
    setError(null);
    setIsImporting(true);
    setImportStatus(null);

    try {
      let result;

      if (activeTab === 'file') {
        if (!file) {
          setError('Please select a CSV file');
          setIsImporting(false);
          return;
        }
        result = await uploadCSVFile(file, {
          topic,
          runLlmClassification,
          regenerateNarrative,
        });
      } else if (activeTab === 'database') {
        // Database import from feed_items
        if (!selectedGroupId) {
          setError('Please select a keyword group');
          setIsImporting(false);
          return;
        }
        const feedResult = await importFromFeed({
          group_id: selectedGroupId,
          run_llm_classification: runLlmClassification,
          regenerate_narrative: regenerateNarrative,
          topic,
        });

        // If ML classification is running in background, set up polling
        if (feedResult.status === 'processing') {
          setImportId(feedResult.import_id);
          // Don't return - let polling handle updates
          return;
        }

        // For immediate results (keyword-based), show completion
        setImportStatus({
          id: feedResult.import_id,
          topic,
          import_type: 'keyword_group_process' as any,
          source_url: null,
          filename: null,
          status: 'completed',
          started_at: new Date().toISOString(),
          completed_at: new Date().toISOString(),
          rows_processed: feedResult.articles_imported + feedResult.articles_skipped,
          articles_created: feedResult.articles_imported,  // categorized
          articles_updated: feedResult.articles_skipped,   // no keyword match
          categories_added: 0,
          errors: 0,
          error_message: feedResult.message,
          run_llm_classification: runLlmClassification,
          narrative_id: null,
        });
        setIsImporting(false);
        if (onImportComplete) {
          onImportComplete();
        }
        return;
      } else {
        // URL import
        result = await importFromURL({
          url: fetchFromTracker ? undefined : customUrl || undefined,
          start_date: fetchFromTracker ? startDate : undefined,
          end_date: fetchFromTracker ? endDate : undefined,
          topic,
          run_llm_classification: runLlmClassification,
          regenerate_narrative: regenerateNarrative,
        });
      }

      setImportId(result.import_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Import failed');
      setIsImporting(false);
    }
  }, [activeTab, file, fetchFromTracker, customUrl, startDate, endDate, topic, runLlmClassification, regenerateNarrative, selectedGroupId, onImportComplete]);

  const handleClose = useCallback(() => {
    if (!isImporting) {
      setFile(null);
      setImportId(null);
      setImportStatus(null);
      setError(null);
      onClose();
    }
  }, [isImporting, onClose]);

  const resetAndClose = useCallback(() => {
    setFile(null);
    setImportId(null);
    setImportStatus(null);
    setError(null);
    setIsImporting(false);
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current);
      pollIntervalRef.current = null;
    }
    onClose();
  }, [onClose]);

  if (!isOpen) return null;

  const isComplete = importStatus?.status === 'completed';
  const isFailed = importStatus?.status === 'failed';

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
            Import Policy Tracker Data
          </h3>
          <button
            onClick={handleClose}
            disabled={isImporting && !isComplete && !isFailed}
            className="text-gray-500 hover:text-gray-600 dark:hover:text-gray-500 disabled:opacity-50"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="p-4 overflow-y-auto max-h-[70vh]">
          {/* Tab Navigation */}
          {!importId && !importStatus && (
            <div className="flex gap-2 mb-4">
              <button
                onClick={() => setActiveTab('url')}
                className={`flex-1 flex items-center justify-center gap-2 px-3 py-2 text-sm rounded-lg transition-colors ${
                  activeTab === 'url'
                    ? 'bg-pink-500 text-white'
                    : 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'
                }`}
              >
                <Globe className="w-4 h-4" />
                URL
              </button>
              <button
                onClick={() => setActiveTab('file')}
                className={`flex-1 flex items-center justify-center gap-2 px-3 py-2 text-sm rounded-lg transition-colors ${
                  activeTab === 'file'
                    ? 'bg-pink-500 text-white'
                    : 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'
                }`}
              >
                <Upload className="w-4 h-4" />
                File
              </button>
              <button
                onClick={() => setActiveTab('database')}
                className={`flex-1 flex items-center justify-center gap-2 px-3 py-2 text-sm rounded-lg transition-colors ${
                  activeTab === 'database'
                    ? 'bg-pink-500 text-white'
                    : 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'
                }`}
              >
                <Database className="w-4 h-4" />
                Database
              </button>
            </div>
          )}

          {/* Import Status Display */}
          {importStatus && (
            <div className={`p-4 rounded-lg mb-4 ${
              isComplete
                ? 'bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800'
                : isFailed
                ? 'bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800'
                : 'bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800'
            }`}>
              <div className="flex items-center gap-2 mb-2">
                {isComplete ? (
                  <CheckCircle className="w-5 h-5 text-green-500" />
                ) : isFailed ? (
                  <AlertCircle className="w-5 h-5 text-red-500" />
                ) : (
                  <Loader2 className="w-5 h-5 text-blue-500 animate-spin" />
                )}
                <span className={`font-medium ${
                  isComplete
                    ? 'text-green-700 dark:text-green-300'
                    : isFailed
                    ? 'text-red-700 dark:text-red-300'
                    : 'text-blue-700 dark:text-blue-300'
                }`}>
                  {isComplete ? 'Import Complete' : isFailed ? 'Import Failed' : 'Processing...'}
                </span>
              </div>

              <div className="grid grid-cols-2 gap-2 text-sm">
                {importStatus.import_type === 'keyword_group_process' ? (
                  <>
                    <div className="text-gray-600 dark:text-gray-300">Articles Categorized:</div>
                    <div className="text-gray-900 dark:text-gray-100">{importStatus.articles_created}</div>

                    <div className="text-gray-600 dark:text-gray-300">No Keyword Match:</div>
                    <div className="text-gray-900 dark:text-gray-100">{importStatus.articles_updated}</div>

                    {importStatus.errors > 0 && (
                      <>
                        <div className="text-gray-600 dark:text-gray-300">Errors:</div>
                        <div className="text-red-600 dark:text-red-400">{importStatus.errors}</div>
                      </>
                    )}
                  </>
                ) : (
                  <>
                    <div className="text-gray-600 dark:text-gray-300">Rows Processed:</div>
                    <div className="text-gray-900 dark:text-gray-100">{importStatus.rows_processed}</div>

                    <div className="text-gray-600 dark:text-gray-300">Articles Created:</div>
                    <div className="text-gray-900 dark:text-gray-100">{importStatus.articles_created}</div>

                    <div className="text-gray-600 dark:text-gray-300">Articles Updated:</div>
                    <div className="text-gray-900 dark:text-gray-100">{importStatus.articles_updated}</div>

                    <div className="text-gray-600 dark:text-gray-300">Categories Added:</div>
                    <div className="text-gray-900 dark:text-gray-100">{importStatus.categories_added}</div>

                    {importStatus.errors > 0 && (
                      <>
                        <div className="text-gray-600 dark:text-gray-300">Errors:</div>
                        <div className="text-red-600 dark:text-red-400">{importStatus.errors}</div>
                      </>
                    )}
                  </>
                )}
              </div>

              {importStatus.error_message && (
                <p className="mt-2 text-sm text-red-600 dark:text-red-400">
                  {importStatus.error_message}
                </p>
              )}

              {(isComplete || isFailed) && (
                <button
                  onClick={resetAndClose}
                  className="mt-4 w-full px-4 py-2 text-sm bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
                >
                  Close
                </button>
              )}
            </div>
          )}

          {/* URL Import Tab */}
          {!importId && !importStatus && activeTab === 'url' && (
            <div className="space-y-4">
              {/* Fetch from Trump Tracker checkbox */}
              <label className="flex items-start gap-3 p-3 bg-pink-50 dark:bg-pink-900/20 rounded-lg cursor-pointer hover:bg-pink-100 dark:hover:bg-pink-900/30 transition-colors">
                <input
                  type="checkbox"
                  checked={fetchFromTracker}
                  onChange={(e) => setFetchFromTracker(e.target.checked)}
                  className="mt-0.5 w-4 h-4 text-pink-500 border-gray-300 rounded focus:ring-pink-500"
                />
                <div>
                  <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
                    Fetch from Trump Action Tracker
                  </span>
                  <p className="text-xs text-gray-500 dark:text-gray-300 mt-0.5">
                    Automatically download CSV from trumpactiontracker.info
                  </p>
                </div>
              </label>

              {fetchFromTracker ? (
                <div className="space-y-3">
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs text-gray-500 dark:text-gray-300 mb-1">
                        Start Date
                      </label>
                      <input
                        type="date"
                        value={startDate}
                        onChange={(e) => setStartDate(e.target.value)}
                        className="w-full px-3 py-2 text-sm bg-white dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-pink-500 dark:text-gray-100"
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-gray-500 dark:text-gray-300 mb-1">
                        End Date
                      </label>
                      <input
                        type="date"
                        value={endDate}
                        onChange={(e) => setEndDate(e.target.value)}
                        className="w-full px-3 py-2 text-sm bg-white dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-pink-500 dark:text-gray-100"
                      />
                    </div>
                  </div>
                  <p className="text-xs text-gray-500 dark:text-gray-300">
                    Data will be fetched from: trumpactiontracker.info/?start={startDate}&end={endDate}
                  </p>
                </div>
              ) : (
                <div>
                  <label className="block text-xs text-gray-500 dark:text-gray-300 mb-1">
                    Custom CSV URL
                  </label>
                  <input
                    type="url"
                    value={customUrl}
                    onChange={(e) => setCustomUrl(e.target.value)}
                    placeholder="https://example.com/data.csv"
                    className="w-full px-3 py-2 text-sm bg-white dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-pink-500 dark:text-gray-100"
                  />
                </div>
              )}
            </div>
          )}

          {/* File Upload Tab */}
          {!importId && !importStatus && activeTab === 'file' && (
            <div className="space-y-4">
              {/* Drop Zone */}
              <div
                onDrop={handleDrop}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onClick={() => fileInputRef.current?.click()}
                className={`relative border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors ${
                  isDragging
                    ? 'border-pink-500 bg-pink-50 dark:bg-pink-900/20'
                    : 'border-gray-300 dark:border-gray-600 hover:border-pink-400 dark:hover:border-pink-500'
                }`}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".csv,text/csv"
                  onChange={handleFileInputChange}
                  className="hidden"
                />

                {file ? (
                  <div className="flex items-center justify-center gap-2">
                    <FileText className="w-8 h-8 text-pink-500" />
                    <div className="text-left">
                      <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
                        {file.name}
                      </p>
                      <p className="text-xs text-gray-500 dark:text-gray-300">
                        {(file.size / 1024).toFixed(1)} KB
                      </p>
                    </div>
                  </div>
                ) : (
                  <>
                    <Upload className="w-10 h-10 mx-auto text-gray-500 dark:text-gray-300 mb-2" />
                    <p className="text-sm text-gray-600 dark:text-gray-300">
                      Drag and drop a CSV file here, or click to browse
                    </p>
                    <p className="text-xs text-gray-500 dark:text-gray-300 mt-1">
                      CSV format from Trump Action Tracker
                    </p>
                  </>
                )}
              </div>
            </div>
          )}

          {/* Database Import Tab */}
          {!importId && !importStatus && activeTab === 'database' && (
            <div className="space-y-4">
              <p className="text-sm text-gray-600 dark:text-gray-300">
                Run policy categorization on articles from a keyword group. This will classify uncategorized articles into policy categories.
              </p>

              {/* Keyword Group Selector */}
              <div>
                <label className="block text-xs text-gray-500 dark:text-gray-300 mb-1">
                  Keyword Group
                </label>
                {loadingGroups ? (
                  <div className="flex items-center gap-2 px-3 py-2 text-sm text-gray-500 dark:text-gray-300">
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Loading keyword groups...
                  </div>
                ) : feedKeywordGroups.length === 0 ? (
                  <p className="text-sm text-gray-500 dark:text-gray-300 px-3 py-2">
                    No keyword groups found. Create one in the Gather section first.
                  </p>
                ) : (
                  <select
                    value={selectedGroupId || ''}
                    onChange={(e) => setSelectedGroupId(Number(e.target.value))}
                    className="w-full px-3 py-2 text-sm bg-white dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-pink-500 dark:text-gray-100"
                  >
                    {feedKeywordGroups.map((group) => (
                      <option key={group.id} value={group.id}>
                        {group.name} ({(group.total_feed_items - group.already_imported).toLocaleString()} uncategorized / {group.total_feed_items.toLocaleString()} total)
                      </option>
                    ))}
                  </select>
                )}
              </div>

              {/* Selected group info */}
              {selectedGroupId && feedKeywordGroups.length > 0 && (
                <div className="p-3 bg-pink-50 dark:bg-pink-900/20 rounded-lg">
                  {(() => {
                    const group = feedKeywordGroups.find(g => g.id === selectedGroupId);
                    if (!group) return null;
                    const uncategorized = group.total_feed_items - group.already_imported;
                    return (
                      <div className="text-sm">
                        <p className="text-pink-700 dark:text-pink-300">
                          <span className="font-medium">{uncategorized.toLocaleString()}</span> articles to categorize
                        </p>
                        <p className="text-xs text-pink-600 dark:text-pink-400 mt-1">
                          {group.already_imported.toLocaleString()} already categorized of {group.total_feed_items.toLocaleString()} total
                        </p>
                      </div>
                    );
                  })()}
                </div>
              )}
            </div>
          )}

          {/* Common Options */}
          {!importId && !importStatus && (
            <div className="mt-4 space-y-3 pt-4 border-t border-gray-200 dark:border-gray-700">
              <h4 className="text-sm font-medium text-gray-900 dark:text-gray-100">
                Import Options
              </h4>

              <label className="flex items-start gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={runLlmClassification}
                  onChange={(e) => setRunLlmClassification(e.target.checked)}
                  className="mt-0.5 w-4 h-4 text-pink-500 border-gray-300 rounded focus:ring-pink-500"
                />
                <div>
                  <span className="text-sm text-gray-700 dark:text-gray-300">
                    Run ML classification
                  </span>
                  <p className="text-xs text-gray-500 dark:text-gray-300">
                    Use ML ensemble (95.6% accuracy) to classify articles
                  </p>
                </div>
              </label>

              <label className="flex items-start gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={regenerateNarrative}
                  onChange={(e) => setRegenerateNarrative(e.target.checked)}
                  className="mt-0.5 w-4 h-4 text-pink-500 border-gray-300 rounded focus:ring-pink-500"
                />
                <div>
                  <span className="text-sm text-gray-700 dark:text-gray-300">
                    Regenerate narrative
                  </span>
                  <p className="text-xs text-gray-500 dark:text-gray-300">
                    Create a new narrative analysis after import
                  </p>
                </div>
              </label>
            </div>
          )}

          {/* Error Display */}
          {error && (
            <div className="mt-4 flex items-center gap-2 p-3 bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300 rounded-lg text-sm">
              <AlertCircle className="w-4 h-4 flex-shrink-0" />
              {error}
            </div>
          )}
        </div>

        {/* Footer */}
        {!importId && !importStatus && (
          <div className="flex justify-end gap-3 p-4 border-t border-gray-200 dark:border-gray-700">
            <button
              onClick={handleClose}
              className="px-4 py-2 text-sm text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={handleImport}
              disabled={isImporting || (activeTab === 'file' && !file) || (activeTab === 'url' && !fetchFromTracker && !customUrl) || (activeTab === 'database' && !selectedGroupId)}
              className="flex items-center gap-2 px-4 py-2 text-sm bg-pink-500 text-white rounded-lg hover:bg-pink-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {isImporting ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  {activeTab === 'database' ? 'Categorizing...' : 'Importing...'}
                </>
              ) : (
                <>
                  <Upload className="w-4 h-4" />
                  {activeTab === 'database' ? 'Categorize Articles' : 'Import'}
                </>
              )}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
