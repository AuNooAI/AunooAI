/**
 * Custom React hook for Extreme Outlier Scenarios (EOS) functionality
 * Handles SSE streaming for real-time generation progress
 */

import { useState, useCallback, useRef, useEffect } from 'react';

// Types
export interface EOSScenario {
  id: string;
  category: 'black_swan' | 'contrarian' | 'wild_card';
  title: string;
  subtitle: string;
  description: string;
  probability: 'very_low' | 'low' | 'moderate';
  impact_rating: number;
  time_horizon: string;
  weak_signals: string[];
  amplification_path: string;
  trigger_events: string[];
  early_warning_signs: string[];
  strategic_implications: string;
  preparation_actions: string[];
  source_trends: string[];
  source_consensus: string[];
}

export interface EOSConfig {
  topic: string;
  scenario_count: number;
  include_black_swans: boolean;
  include_contrarian: boolean;
  include_wild_cards: boolean;
  time_horizon: 'near' | 'mid' | 'long';
  source_analysis?: any;
}

export interface EOSStageInfo {
  name: string;
  label: string;
  description: string;
}

export const EOS_STAGES: EOSStageInfo[] = [
  {
    name: 'weak_signals',
    label: 'Weak Signals',
    description: 'Detecting faint patterns and anomalies',
  },
  {
    name: 'amplification',
    label: 'Amplification',
    description: 'Modeling cascade potential',
  },
  {
    name: 'scenario_building',
    label: 'Scenario Building',
    description: 'Constructing outlier narratives',
  },
  {
    name: 'implications',
    label: 'Implications',
    description: 'Generating strategic recommendations',
  },
];

export interface EOSResult {
  scan_id: string;
  scenarios: EOSScenario[];
  metadata: {
    topic: string;
    signals_detected: number;
    pathways_explored: number;
    scenarios_generated: number;
    generated_at: string;
    config: EOSConfig;
  };
}

interface EOSProgress {
  stage: string;
  status: string;
  progress: number;
  signals_detected?: number;
  pathways_identified?: number;
  scenarios_built?: number;
  scenarios?: EOSScenario[];
  scan_id?: string;
  metadata?: any;
  error?: string;
}

export interface UseExtremeOutliersReturn {
  // State
  isGenerating: boolean;
  currentStage: string;
  stageProgress: number;
  overallProgress: number;
  scenarios: EOSScenario[];
  result: EOSResult | null;
  error: string | null;

  // Stats during generation
  signalsDetected: number;
  pathwaysIdentified: number;
  scenariosGenerated: number;

  // Actions
  startGeneration: (config: EOSConfig) => void;
  cancelGeneration: () => void;
  clearResults: () => void;
  clearError: () => void;
}

const STORAGE_KEY = 'eos_last_result';

export function useExtremeOutliers(): UseExtremeOutliersReturn {
  // Core state
  const [isGenerating, setIsGenerating] = useState(false);
  const [currentStage, setCurrentStage] = useState('');
  const [stageProgress, setStageProgress] = useState(0);
  const [overallProgress, setOverallProgress] = useState(0);
  const [scenarios, setScenarios] = useState<EOSScenario[]>([]);
  const [result, setResult] = useState<EOSResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Stats
  const [signalsDetected, setSignalsDetected] = useState(0);
  const [pathwaysIdentified, setPathwaysIdentified] = useState(0);
  const [scenariosGenerated, setScenariosGenerated] = useState(0);

  // Ref for cleanup function
  const abortControllerRef = useRef<AbortController | null>(null);

  // Load cached result on mount
  useEffect(() => {
    try {
      const cached = localStorage.getItem(STORAGE_KEY);
      if (cached) {
        const data = JSON.parse(cached) as EOSResult;
        setResult(data);
        setScenarios(data.scenarios);
      }
    } catch (err) {
      console.error('Error loading cached EOS result:', err);
    }
  }, []);

  // Calculate overall progress based on stages
  const calculateOverallProgress = useCallback(
    (stage: string, progress: number): number => {
      const stageWeights: Record<string, { start: number; weight: number }> = {
        weak_signals: { start: 0, weight: 0.2 },
        amplification: { start: 0.2, weight: 0.25 },
        scenario_building: { start: 0.45, weight: 0.35 },
        implications: { start: 0.8, weight: 0.2 },
      };

      const stageInfo = stageWeights[stage];
      if (!stageInfo) return 0;

      return stageInfo.start + progress * stageInfo.weight;
    },
    []
  );

  // Start generation with SSE streaming
  const startGeneration = useCallback(
    async (config: EOSConfig) => {
      // Reset state
      setIsGenerating(true);
      setCurrentStage('weak_signals');
      setStageProgress(0);
      setOverallProgress(0);
      setScenarios([]);
      setResult(null);
      setError(null);
      setSignalsDetected(0);
      setPathwaysIdentified(0);
      setScenariosGenerated(0);

      // Create abort controller
      const abortController = new AbortController();
      abortControllerRef.current = abortController;

      try {
        const response = await fetch('/api/eos/scan', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          credentials: 'include',
          body: JSON.stringify({
            topic: config.topic,
            scenario_count: config.scenario_count,
            include_black_swans: config.include_black_swans,
            include_contrarian: config.include_contrarian,
            include_wild_cards: config.include_wild_cards,
            time_horizon: config.time_horizon,
            source_analysis: config.source_analysis || {},
            stream: true,
          }),
          signal: abortController.signal,
        });

        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }

        const reader = response.body?.getReader();
        if (!reader) {
          throw new Error('No reader available');
        }

        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                const data: EOSProgress = JSON.parse(line.slice(6));

                // Update stage and progress
                setCurrentStage(data.stage);
                setStageProgress(data.progress);
                setOverallProgress(calculateOverallProgress(data.stage, data.progress));

                // Update stats
                if (data.signals_detected !== undefined) {
                  setSignalsDetected(data.signals_detected);
                }
                if (data.pathways_identified !== undefined) {
                  setPathwaysIdentified(data.pathways_identified);
                }
                if (data.scenarios_built !== undefined) {
                  setScenariosGenerated(data.scenarios_built);
                }

                // Handle completion
                if (data.stage === 'complete' && data.scenarios) {
                  setIsGenerating(false);
                  setCurrentStage('complete');
                  setStageProgress(1);
                  setOverallProgress(1);
                  setScenarios(data.scenarios);
                  setScenariosGenerated(data.scenarios.length);

                  const fullResult: EOSResult = {
                    scan_id: data.scan_id || '',
                    scenarios: data.scenarios,
                    metadata: data.metadata,
                  };
                  setResult(fullResult);

                  // Cache the result
                  try {
                    localStorage.setItem(STORAGE_KEY, JSON.stringify(fullResult));
                  } catch (err) {
                    console.error('Error caching EOS result:', err);
                  }
                }

                // Handle error
                if (data.stage === 'error' || data.status === 'error') {
                  setIsGenerating(false);
                  setError(data.error || 'Generation failed');
                }
              } catch (parseError) {
                console.error('Error parsing SSE data:', parseError);
              }
            }
          }
        }
      } catch (err: any) {
        if (err.name === 'AbortError') {
          setError('Generation cancelled');
        } else {
          setError(err.message || 'Failed to generate scenarios');
        }
        setIsGenerating(false);
      }
    },
    [calculateOverallProgress]
  );

  // Cancel a running generation
  const cancelGeneration = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setIsGenerating(false);
    setError('Generation cancelled');
  }, []);

  // Clear results
  const clearResults = useCallback(() => {
    setResult(null);
    setScenarios([]);
    setCurrentStage('');
    setStageProgress(0);
    setOverallProgress(0);
    setSignalsDetected(0);
    setPathwaysIdentified(0);
    setScenariosGenerated(0);

    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch (err) {
      console.error('Error clearing cached EOS result:', err);
    }
  }, []);

  // Clear error
  const clearError = useCallback(() => {
    setError(null);
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, []);

  return {
    isGenerating,
    currentStage,
    stageProgress,
    overallProgress,
    scenarios,
    result,
    error,
    signalsDetected,
    pathwaysIdentified,
    scenariosGenerated,
    startGeneration,
    cancelGeneration,
    clearResults,
    clearError,
  };
}
