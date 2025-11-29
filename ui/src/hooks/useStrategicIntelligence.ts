/**
 * Custom React hook for Strategic Intelligence Oracle (SIO) functionality
 * Handles SSE streaming for real-time scan progress
 */

import { useState, useCallback, useRef, useEffect } from 'react';
import {
  startSIOScanStream,
  type SIOScanRequest,
  type SIOScanProgress,
  type SIOBriefData,
} from '../services/api';

export interface SIOConfig {
  topic?: string;
  hours_back: number;
  max_events: number;
  credibility_threshold: number;
  profile_id?: number;
}

export interface SIOStageInfo {
  name: string;
  label: string;
  description: string;
}

export const SIO_STAGES: SIOStageInfo[] = [
  {
    name: 'discovery',
    label: 'Discovery',
    description: 'Gathering articles from the past 24 hours',
  },
  {
    name: 'triage',
    label: 'Triage',
    description: 'Screening for credibility and clustering into events',
  },
  {
    name: 'deep_analysis',
    label: 'Deep Analysis',
    description: 'Analyzing top events with cross-verification',
  },
  {
    name: 'synthesis',
    label: 'Synthesis',
    description: 'Generating intelligence brief',
  },
];

export interface UseStrategicIntelligenceReturn {
  // State
  isScanning: boolean;
  currentStage: string;
  stageProgress: number;
  overallProgress: number;
  briefContent: string;
  briefChunks: string[];
  scanResult: SIOBriefData | null;
  error: string | null;

  // Stats during scan
  articlesCollected: number;
  articlesScreened: number;
  eventsIdentified: number;
  eventsAnalyzed: number;
  currentEvent: string;

  // Actions
  startScan: (config: SIOConfig) => void;
  cancelScan: () => void;
  clearResults: () => void;
  clearError: () => void;
}

const DEFAULT_CONFIG: SIOConfig = {
  hours_back: 24,
  max_events: 30,
  credibility_threshold: 60,
};

const STORAGE_KEY = 'sio_last_brief';

export function useStrategicIntelligence(): UseStrategicIntelligenceReturn {
  // Core state
  const [isScanning, setIsScanning] = useState(false);
  const [currentStage, setCurrentStage] = useState('');
  const [stageProgress, setStageProgress] = useState(0);
  const [overallProgress, setOverallProgress] = useState(0);
  const [briefContent, setBriefContent] = useState('');
  const [briefChunks, setBriefChunks] = useState<string[]>([]);
  const [scanResult, setScanResult] = useState<SIOBriefData | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Stats
  const [articlesCollected, setArticlesCollected] = useState(0);
  const [articlesScreened, setArticlesScreened] = useState(0);
  const [eventsIdentified, setEventsIdentified] = useState(0);
  const [eventsAnalyzed, setEventsAnalyzed] = useState(0);
  const [currentEvent, setCurrentEvent] = useState('');

  // Ref for cleanup function
  const cancelRef = useRef<(() => void) | null>(null);

  // Load cached brief on mount
  useEffect(() => {
    try {
      const cached = localStorage.getItem(STORAGE_KEY);
      if (cached) {
        const data = JSON.parse(cached) as SIOBriefData;
        setScanResult(data);
        setBriefContent(data.brief);
      }
    } catch (err) {
      console.error('Error loading cached SIO brief:', err);
    }
  }, []);

  // Calculate overall progress based on stages
  const calculateOverallProgress = useCallback(
    (stage: string, progress: number): number => {
      const stageWeights: Record<string, { start: number; weight: number }> = {
        discovery: { start: 0, weight: 0.2 },
        triage: { start: 0.2, weight: 0.15 },
        deep_analysis: { start: 0.35, weight: 0.45 },
        synthesis: { start: 0.8, weight: 0.2 },
      };

      const stageInfo = stageWeights[stage];
      if (!stageInfo) return 0;

      return stageInfo.start + progress * stageInfo.weight;
    },
    []
  );

  // Handle progress updates
  const handleProgress = useCallback(
    (data: SIOScanProgress) => {
      setCurrentStage(data.stage);
      setStageProgress(data.progress);
      setOverallProgress(calculateOverallProgress(data.stage, data.progress));

      // Update stats
      if (data.articles_collected !== undefined) {
        setArticlesCollected(data.articles_collected);
      }
      if (data.articles_screened !== undefined) {
        setArticlesScreened(data.articles_screened);
      }
      if (data.events_identified !== undefined) {
        setEventsIdentified(data.events_identified);
      }
      if (data.events_analyzed !== undefined) {
        setEventsAnalyzed(data.events_analyzed);
      }
      if (data.current_event) {
        setCurrentEvent(data.current_event);
      }

      // Handle streaming brief chunks
      if (data.chunk) {
        setBriefChunks((prev) => [...prev, data.chunk!]);
        setBriefContent((prev) => prev + data.chunk);
      }
    },
    [calculateOverallProgress]
  );

  // Handle completion
  const handleComplete = useCallback((data: SIOBriefData) => {
    setIsScanning(false);
    setCurrentStage('complete');
    setStageProgress(1);
    setOverallProgress(1);
    setScanResult(data);
    setBriefContent(data.brief);

    // Update final stats
    if (data.metadata) {
      setArticlesCollected(data.metadata.articles_collected);
      setArticlesScreened(data.metadata.articles_screened);
      setEventsIdentified(data.metadata.events_identified);
      setEventsAnalyzed(data.metadata.events_analyzed);
    }

    // Cache the result
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
    } catch (err) {
      console.error('Error caching SIO brief:', err);
    }
  }, []);

  // Handle errors
  const handleError = useCallback((errorMsg: string) => {
    setIsScanning(false);
    setError(errorMsg);
  }, []);

  // Start a scan
  const startScan = useCallback(
    (config: SIOConfig) => {
      // Reset state
      setIsScanning(true);
      setCurrentStage('discovery');
      setStageProgress(0);
      setOverallProgress(0);
      setBriefContent('');
      setBriefChunks([]);
      setScanResult(null);
      setError(null);
      setArticlesCollected(0);
      setArticlesScreened(0);
      setEventsIdentified(0);
      setEventsAnalyzed(0);
      setCurrentEvent('');

      // Build request
      const request: SIOScanRequest = {
        topic: config.topic || undefined,
        hours_back: config.hours_back,
        max_events: config.max_events,
        credibility_threshold: config.credibility_threshold,
        profile_id: config.profile_id,
        stream: true,
      };

      // Start streaming
      const cancel = startSIOScanStream(
        request,
        handleProgress,
        handleComplete,
        handleError
      );

      cancelRef.current = cancel;
    },
    [handleProgress, handleComplete, handleError]
  );

  // Cancel a running scan
  const cancelScan = useCallback(() => {
    if (cancelRef.current) {
      cancelRef.current();
      cancelRef.current = null;
    }
    setIsScanning(false);
    setError('Scan cancelled');
  }, []);

  // Clear results
  const clearResults = useCallback(() => {
    setScanResult(null);
    setBriefContent('');
    setBriefChunks([]);
    setCurrentStage('');
    setStageProgress(0);
    setOverallProgress(0);
    setArticlesCollected(0);
    setArticlesScreened(0);
    setEventsIdentified(0);
    setEventsAnalyzed(0);
    setCurrentEvent('');

    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch (err) {
      console.error('Error clearing cached SIO brief:', err);
    }
  }, []);

  // Clear error
  const clearError = useCallback(() => {
    setError(null);
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (cancelRef.current) {
        cancelRef.current();
      }
    };
  }, []);

  return {
    isScanning,
    currentStage,
    stageProgress,
    overallProgress,
    briefContent,
    briefChunks,
    scanResult,
    error,
    articlesCollected,
    articlesScreened,
    eventsIdentified,
    eventsAnalyzed,
    currentEvent,
    startScan,
    cancelScan,
    clearResults,
    clearError,
  };
}
