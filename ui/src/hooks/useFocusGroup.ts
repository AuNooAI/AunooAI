/**
 * Custom React hook for Synthetic Focus Group functionality
 * Handles SSE streaming for real-time generation progress
 */

import { useState, useCallback, useRef, useEffect } from 'react';

// Types
export interface Persona {
  id: string;
  name: string;
  archetype: string;
  role_title: string;
  sector: string;
  experience_level: 'junior' | 'mid' | 'senior' | 'executive';
  decision_authority: 'individual' | 'team_influencer' | 'budget_holder' | 'c_suite';
  primary_values: string[];
  risk_tolerance: number;
  time_horizon_focus: 'immediate' | 'quarterly' | 'annual' | 'multi_year';
  change_receptivity: 'resistant' | 'cautious' | 'adaptive' | 'embracing';
  technology_stance: 'skeptic' | 'pragmatist' | 'enthusiast' | 'evangelist';
  authority_trust: 'distrustful' | 'questioning' | 'neutral' | 'trusting';
  media_trust: 'cynical' | 'selective' | 'moderate' | 'high';
  topic_attitudes: Record<string, string>;
  information_consumption: 'scanner' | 'deep_reader' | 'curator' | 'sharer';
  decision_style: 'analytical' | 'intuitive' | 'consultative' | 'directive';
  communication_preference: 'formal' | 'data_driven' | 'narrative' | 'visual';
  primary_concerns: string[];
  fear_triggers: string[];
  opportunity_interests: string[];
  voice_description: string;
  typical_questions: string[];
  decision_factors: string[];
  influence_vectors: string[];
  source_articles: string[];
  confidence_score: number;
  mention_count: number;
  user_notes?: string;
  user_edited: boolean;
}

export interface InteractionDynamics {
  consensus_areas: Array<{
    topic: string;
    description: string;
    supporting_personas: string[];
  }>;
  tension_points: Array<{
    topic: string;
    description: string;
    opposing_sides: {
      side_a: string[];
      side_b: string[];
    };
  }>;
  power_dynamics: {
    most_influential: string;
    most_vulnerable: string;
    likely_coalition: string[];
  };
  diversity_score: number;
  diversity_analysis: string;
  blind_spots: string[];
  key_insight: string;
}

export interface FGConfig {
  topic: string;
  max_personas: number;
  min_evidence_threshold: number;
  include_demographics: boolean;
  include_psychographics: boolean;
  include_voice: boolean;
}

export interface FGStageInfo {
  name: string;
  label: string;
  description: string;
}

export const FG_STAGES: FGStageInfo[] = [
  {
    name: 'discovery',
    label: 'Discovery',
    description: 'Extracting stakeholder mentions from articles',
  },
  {
    name: 'clustering',
    label: 'Clustering',
    description: 'Grouping mentions into archetypes',
  },
  {
    name: 'profiling',
    label: 'Profiling',
    description: 'Building rich psychographic profiles',
  },
  {
    name: 'synthesis',
    label: 'Synthesis',
    description: 'Generating group dynamics',
  },
];

export interface FGResult {
  scan_id: string;
  personas: Persona[];
  focus_group_summary: string;
  interaction_dynamics: InteractionDynamics;
  metadata: {
    topic: string;
    articles_analyzed: number;
    mentions_found: number;
    personas_generated: number;
    generated_at: string;
    config: FGConfig;
  };
  article_count?: number;
}

interface FGProgress {
  stage: string;
  status: string;
  progress: number;
  mentions_found?: number;
  clusters_formed?: number;
  personas_created?: number;
  personas?: Persona[];
  focus_group_summary?: string;
  interaction_dynamics?: InteractionDynamics;
  scan_id?: string;
  metadata?: any;
  article_count?: number;
  error?: string;
}

export interface SavedFocusGroup {
  id: number;
  name: string;
  description?: string;
  created_at: string;
  updated_at: string;
  articles_used?: number;
  model_used?: string;
  persona_count?: number;
}

export interface UseFocusGroupReturn {
  // State
  isGenerating: boolean;
  currentStage: string;
  stageProgress: number;
  overallProgress: number;
  personas: Persona[];
  focusGroupSummary: string;
  interactionDynamics: InteractionDynamics | null;
  result: FGResult | null;
  error: string | null;

  // Stats during generation
  mentionsFound: number;
  clustersFormed: number;
  personasCreated: number;

  // Saved focus groups
  savedFocusGroups: SavedFocusGroup[];
  isSaving: boolean;
  isLoadingSaved: boolean;

  // Actions
  startGeneration: (config: FGConfig) => void;
  cancelGeneration: () => void;
  clearResults: () => void;
  clearError: () => void;
  loadResult: (personas: Persona[], result?: FGResult) => void;
  updatePersona: (personaId: string, updates: Partial<Persona>) => void;

  // Save/Load actions
  saveFocusGroup: (topic: string, name: string, description?: string) => Promise<void>;
  loadSavedFocusGroups: (topic: string) => Promise<void>;
  loadSavedFocusGroup: (id: number) => Promise<void>;
  deleteSavedFocusGroup: (id: number) => Promise<void>;
}

const STORAGE_KEY = 'fg_last_result';

export function useFocusGroup(): UseFocusGroupReturn {
  // Core state
  const [isGenerating, setIsGenerating] = useState(false);
  const [currentStage, setCurrentStage] = useState('');
  const [stageProgress, setStageProgress] = useState(0);
  const [overallProgress, setOverallProgress] = useState(0);
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [focusGroupSummary, setFocusGroupSummary] = useState('');
  const [interactionDynamics, setInteractionDynamics] = useState<InteractionDynamics | null>(null);
  const [result, setResult] = useState<FGResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Stats
  const [mentionsFound, setMentionsFound] = useState(0);
  const [clustersFormed, setClustersFormed] = useState(0);
  const [personasCreated, setPersonasCreated] = useState(0);

  // Saved focus groups
  const [savedFocusGroups, setSavedFocusGroups] = useState<SavedFocusGroup[]>([]);
  const [isSaving, setIsSaving] = useState(false);
  const [isLoadingSaved, setIsLoadingSaved] = useState(false);

  // Ref for cleanup function
  const abortControllerRef = useRef<AbortController | null>(null);

  // Load cached result on mount
  useEffect(() => {
    try {
      const cached = localStorage.getItem(STORAGE_KEY);
      if (cached) {
        const data = JSON.parse(cached) as FGResult;
        setResult(data);
        setPersonas(data.personas);
        setFocusGroupSummary(data.focus_group_summary);
        setInteractionDynamics(data.interaction_dynamics);
      }
    } catch (err) {
      console.error('Error loading cached focus group result:', err);
    }
  }, []);

  // Calculate overall progress based on stages
  const calculateOverallProgress = useCallback(
    (stage: string, progress: number): number => {
      const stageWeights: Record<string, { start: number; weight: number }> = {
        discovery: { start: 0, weight: 0.20 },
        clustering: { start: 0.20, weight: 0.25 },
        profiling: { start: 0.45, weight: 0.35 },
        synthesis: { start: 0.80, weight: 0.20 },
      };

      const stageInfo = stageWeights[stage];
      if (!stageInfo) return 0;

      return stageInfo.start + progress * stageInfo.weight;
    },
    []
  );

  // Start generation with SSE streaming
  const startGeneration = useCallback(
    async (config: FGConfig) => {
      // Reset state
      setIsGenerating(true);
      setCurrentStage('discovery');
      setStageProgress(0);
      setOverallProgress(0);
      setPersonas([]);
      setFocusGroupSummary('');
      setInteractionDynamics(null);
      setResult(null);
      setError(null);
      setMentionsFound(0);
      setClustersFormed(0);
      setPersonasCreated(0);

      // Create abort controller
      const abortController = new AbortController();
      abortControllerRef.current = abortController;

      try {
        const response = await fetch('/api/focus-groups/scan', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          credentials: 'include',
          body: JSON.stringify({
            topic: config.topic,
            max_personas: config.max_personas,
            min_evidence_threshold: config.min_evidence_threshold,
            include_demographics: config.include_demographics,
            include_psychographics: config.include_psychographics,
            include_voice: config.include_voice,
            stream: true,
          }),
          signal: abortController.signal,
        });

        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}));
          throw new Error(errorData.detail || `HTTP error! status: ${response.status}`);
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
                const data: FGProgress = JSON.parse(line.slice(6));

                // Update stage and progress
                setCurrentStage(data.stage);
                setStageProgress(data.progress);
                setOverallProgress(calculateOverallProgress(data.stage, data.progress));

                // Update stats
                if (data.mentions_found !== undefined) {
                  setMentionsFound(data.mentions_found);
                }
                if (data.clusters_formed !== undefined) {
                  setClustersFormed(data.clusters_formed);
                }
                if (data.personas_created !== undefined) {
                  setPersonasCreated(data.personas_created);
                }

                // Handle completion
                if (data.stage === 'complete' && data.personas) {
                  setIsGenerating(false);
                  setCurrentStage('complete');
                  setStageProgress(1);
                  setOverallProgress(1);
                  setPersonas(data.personas);
                  setFocusGroupSummary(data.focus_group_summary || '');
                  setInteractionDynamics(data.interaction_dynamics || null);
                  setPersonasCreated(data.personas.length);

                  const fullResult: FGResult = {
                    scan_id: data.scan_id || '',
                    personas: data.personas,
                    focus_group_summary: data.focus_group_summary || '',
                    interaction_dynamics: data.interaction_dynamics || {
                      consensus_areas: [],
                      tension_points: [],
                      power_dynamics: {
                        most_influential: '',
                        most_vulnerable: '',
                        likely_coalition: [],
                      },
                      diversity_score: 0,
                      diversity_analysis: '',
                      blind_spots: [],
                      key_insight: '',
                    },
                    metadata: data.metadata,
                    article_count: data.article_count,
                  };
                  setResult(fullResult);

                  // Cache the result
                  try {
                    localStorage.setItem(STORAGE_KEY, JSON.stringify(fullResult));
                  } catch (err) {
                    console.error('Error caching focus group result:', err);
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
          setError(err.message || 'Failed to generate focus group');
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
    setPersonas([]);
    setFocusGroupSummary('');
    setInteractionDynamics(null);
    setCurrentStage('');
    setStageProgress(0);
    setOverallProgress(0);
    setMentionsFound(0);
    setClustersFormed(0);
    setPersonasCreated(0);

    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch (err) {
      console.error('Error clearing cached focus group result:', err);
    }
  }, []);

  // Clear error
  const clearError = useCallback(() => {
    setError(null);
  }, []);

  // Load a saved result (e.g., from saved focus groups)
  const loadResult = useCallback((loadedPersonas: Persona[], loadedResult?: FGResult) => {
    setPersonas(loadedPersonas);
    setPersonasCreated(loadedPersonas.length);
    if (loadedResult) {
      setResult(loadedResult);
      setFocusGroupSummary(loadedResult.focus_group_summary);
      setInteractionDynamics(loadedResult.interaction_dynamics);
    } else {
      const newResult: FGResult = {
        scan_id: '',
        personas: loadedPersonas,
        focus_group_summary: '',
        interaction_dynamics: {
          consensus_areas: [],
          tension_points: [],
          power_dynamics: {
            most_influential: '',
            most_vulnerable: '',
            likely_coalition: [],
          },
          diversity_score: 0,
          diversity_analysis: '',
          blind_spots: [],
          key_insight: '',
        },
        metadata: {
          topic: '',
          articles_analyzed: 0,
          mentions_found: 0,
          personas_generated: loadedPersonas.length,
          generated_at: new Date().toISOString(),
          config: {} as FGConfig,
        },
      };
      setResult(newResult);
    }
    setCurrentStage('complete');
    setOverallProgress(1);
    setStageProgress(1);
  }, []);

  // Update a persona (inline editing)
  const updatePersona = useCallback((personaId: string, updates: Partial<Persona>) => {
    setPersonas((prev) =>
      prev.map((p) =>
        p.id === personaId ? { ...p, ...updates, user_edited: true } : p
      )
    );
    setResult((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        personas: prev.personas.map((p) =>
          p.id === personaId ? { ...p, ...updates, user_edited: true } : p
        ),
      };
    });
  }, []);

  // Save focus group to database
  const saveFocusGroup = useCallback(
    async (topic: string, name: string, description?: string) => {
      if (!result || personas.length === 0) {
        throw new Error('No focus group to save');
      }

      setIsSaving(true);
      try {
        const response = await fetch('/api/focus-groups/save', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({
            topic,
            name,
            description,
            personas,
            focus_group_summary: focusGroupSummary,
            interaction_dynamics: interactionDynamics,
            config: result.metadata?.config,
            metadata: result.metadata,
            articles_used: result.article_count || result.metadata?.articles_analyzed,
            persona_count: personas.length,
          }),
        });

        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}));
          throw new Error(errorData.detail || 'Failed to save focus group');
        }

        // Refresh the saved list
        await loadSavedFocusGroups(topic);
      } finally {
        setIsSaving(false);
      }
    },
    [result, personas, focusGroupSummary, interactionDynamics]
  );

  // Load saved focus groups for a topic
  const loadSavedFocusGroups = useCallback(async (topic: string) => {
    setIsLoadingSaved(true);
    try {
      const response = await fetch(`/api/focus-groups/saved/${encodeURIComponent(topic)}`, {
        credentials: 'include',
      });

      if (!response.ok) {
        throw new Error('Failed to load saved focus groups');
      }

      const data = await response.json();
      setSavedFocusGroups(data.saved_focus_groups || []);
    } catch (err) {
      console.error('Error loading saved focus groups:', err);
      setSavedFocusGroups([]);
    } finally {
      setIsLoadingSaved(false);
    }
  }, []);

  // Load a specific saved focus group
  const loadSavedFocusGroup = useCallback(async (id: number) => {
    setIsLoadingSaved(true);
    try {
      const response = await fetch(`/api/focus-groups/saved/load/${id}`, {
        credentials: 'include',
      });

      if (!response.ok) {
        throw new Error('Failed to load focus group');
      }

      const data = await response.json();
      const fg = data.focus_group;

      if (fg) {
        const loadedResult: FGResult = {
          scan_id: '',
          personas: fg.personas || [],
          focus_group_summary: fg.focus_group_summary || '',
          interaction_dynamics: fg.interaction_dynamics || {
            consensus_areas: [],
            tension_points: [],
            power_dynamics: {
              most_influential: '',
              most_vulnerable: '',
              likely_coalition: [],
            },
            diversity_score: 0,
            diversity_analysis: '',
            blind_spots: [],
            key_insight: '',
          },
          metadata: {
            topic: fg.topic,
            articles_analyzed: fg.articles_used || 0,
            mentions_found: 0,
            personas_generated: fg.persona_count || (fg.personas?.length || 0),
            generated_at: fg.created_at,
            config: fg.config || {},
          },
          article_count: fg.articles_used,
        };

        loadResult(fg.personas || [], loadedResult);
      }
    } catch (err: any) {
      setError(err.message || 'Failed to load focus group');
    } finally {
      setIsLoadingSaved(false);
    }
  }, [loadResult]);

  // Delete a saved focus group
  const deleteSavedFocusGroup = useCallback(async (id: number) => {
    try {
      const response = await fetch(`/api/focus-groups/saved/${id}`, {
        method: 'DELETE',
        credentials: 'include',
      });

      if (!response.ok) {
        throw new Error('Failed to delete focus group');
      }

      // Remove from local list
      setSavedFocusGroups((prev) => prev.filter((fg) => fg.id !== id));
    } catch (err: any) {
      setError(err.message || 'Failed to delete focus group');
    }
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
    personas,
    focusGroupSummary,
    interactionDynamics,
    result,
    error,
    mentionsFound,
    clustersFormed,
    personasCreated,
    savedFocusGroups,
    isSaving,
    isLoadingSaved,
    startGeneration,
    cancelGeneration,
    clearResults,
    clearError,
    loadResult,
    updatePersona,
    saveFocusGroup,
    loadSavedFocusGroups,
    loadSavedFocusGroup,
    deleteSavedFocusGroup,
  };
}
