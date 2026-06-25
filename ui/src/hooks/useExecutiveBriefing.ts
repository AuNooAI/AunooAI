/**
 * Custom React hook for Executive Briefing functionality
 * Handles SSE streaming for real-time generation progress
 */

import { useState, useCallback, useRef, useEffect } from 'react';
import { extractErrorMessage } from '../services/api';

// Types
export interface BriefingArticle {
  title: string;
  source: string;
  date: string;
  url: string;
  uri: string;
  executive_takeaway: string;
  summary: string;
  strategic_relevance: string;
  time_horizon: 'Immediate' | 'Medium' | 'Long-term';
  risk_opportunity: 'risk' | 'opportunity' | 'mixed';
  signal_strength: 'weak' | 'moderate' | 'strong';
  category: 'policy' | 'market' | 'tech' | 'workforce' | 'security' | 'society';
  executive_action: string[];
  key_entities: string[];
  related_topics: string[];
  scores: {
    relevance: number;
    novelty: number;
    credibility: number;
    representativeness: number;
  };
  selection_rationale: string;
  overall_score: number;
  user_notes?: string;
  user_edited: boolean;
}

export interface Theme {
  theme_name: string;
  description: string;
  articles_supporting: number[];
  strategic_implication: string;
}

export interface PriorityAction {
  action: string;
  urgency: 'immediate' | 'this_week' | 'this_month' | 'this_quarter';
  rationale: string;
  related_themes: string[];
}

export interface RiskSummary {
  overall_risk_level: 'low' | 'moderate' | 'elevated' | 'high';
  key_risks: string[];
  mitigation_opportunities: string[];
}

export interface OpportunitySummary {
  overall_opportunity_level: 'limited' | 'moderate' | 'significant' | 'transformative';
  key_opportunities: string[];
  action_windows: string[];
}

export interface FocusArea {
  area: string;
  reason: string;
  time_sensitivity: string;
}

export interface EBConfig {
  topic: string;
  persona: string;
  article_count: number;
  days_back: number;
  custom_persona?: {
    priorities: string;
    risk_appetite: string;
    focus: string;
  };
  include_synthesis: boolean;
  include_podcast_script?: boolean;
  podcast_duration?: 'short' | 'medium' | 'long';
}

export interface EBStageInfo {
  name: string;
  label: string;
  description: string;
}

export const EB_STAGES: EBStageInfo[] = [
  {
    name: 'selection',
    label: 'Selection',
    description: 'Scoring and selecting top articles',
  },
  {
    name: 'analysis',
    label: 'Analysis',
    description: 'Generating executive analysis',
  },
  {
    name: 'synthesis',
    label: 'Synthesis',
    description: 'Creating briefing summary and themes',
  },
];

export interface EBResult {
  scan_id: string;
  articles: BriefingArticle[];
  briefing_summary: string;
  themes: Theme[];
  priority_actions: PriorityAction[];
  risk_summary: RiskSummary;
  opportunity_summary: OpportunitySummary;
  focus_areas: FocusArea[];
  podcast_script?: string;
  metadata: {
    topic: string;
    persona: string;
    articles_analyzed: number;
    articles_total: number;
    generated_at: string;
    config: {
      article_count: number;
      days_back: number;
      include_synthesis: boolean;
      include_podcast_script?: boolean;
    };
  };
  total_articles?: number;
}

interface EBProgress {
  stage: string;
  status: string;
  progress: number;
  scan_id?: string;
  total_articles?: number;
  articles_selected?: number;
  articles_to_analyze?: number;
  articles_analyzed?: number;
  current_article?: number;
  article_title?: string;
  articles?: BriefingArticle[];
  briefing_summary?: string;
  themes?: Theme[];
  priority_actions?: PriorityAction[];
  risk_summary?: RiskSummary;
  opportunity_summary?: OpportunitySummary;
  focus_areas?: FocusArea[];
  podcast_script?: string;
  script_length?: number;
  metadata?: any;
  error?: string;
}

export interface SavedBriefing {
  id: number;
  name: string;
  description?: string;
  persona: string;
  article_count: number;
  created_at: string;
  updated_at: string;
  articles_used?: number;
  model_used?: string;
}

export interface UseExecutiveBriefingReturn {
  // State
  isGenerating: boolean;
  currentStage: string;
  stageProgress: number;
  overallProgress: number;
  articles: BriefingArticle[];
  briefingSummary: string;
  themes: Theme[];
  priorityActions: PriorityAction[];
  riskSummary: RiskSummary | null;
  opportunitySummary: OpportunitySummary | null;
  focusAreas: FocusArea[];
  podcastScript: string;
  result: EBResult | null;
  error: string | null;

  // Stats during generation
  articlesSelected: number;
  articlesAnalyzed: number;
  currentArticle: number;
  currentArticleTitle: string;

  // Saved briefings
  savedBriefings: SavedBriefing[];
  isSaving: boolean;
  isLoadingSaved: boolean;

  // Actions
  startGeneration: (config: EBConfig) => void;
  cancelGeneration: () => void;
  clearResults: () => void;
  clearError: () => void;
  loadResult: (articles: BriefingArticle[], result?: EBResult) => void;
  updateArticle: (index: number, updates: Partial<BriefingArticle>) => void;
  setPodcastScript: (script: string) => void;

  // Save/Load actions
  saveBriefing: (topic: string, name: string, description?: string) => Promise<void>;
  loadSavedBriefings: (topic: string) => Promise<void>;
  loadSavedBriefing: (id: number) => Promise<void>;
  deleteSavedBriefing: (id: number) => Promise<void>;
}

const STORAGE_KEY = 'eb_last_result';

export function useExecutiveBriefing(): UseExecutiveBriefingReturn {
  // Core state
  const [isGenerating, setIsGenerating] = useState(false);
  const [currentStage, setCurrentStage] = useState('');
  const [stageProgress, setStageProgress] = useState(0);
  const [overallProgress, setOverallProgress] = useState(0);
  const [articles, setArticles] = useState<BriefingArticle[]>([]);
  const [briefingSummary, setBriefingSummary] = useState('');
  const [themes, setThemes] = useState<Theme[]>([]);
  const [priorityActions, setPriorityActions] = useState<PriorityAction[]>([]);
  const [riskSummary, setRiskSummary] = useState<RiskSummary | null>(null);
  const [opportunitySummary, setOpportunitySummary] = useState<OpportunitySummary | null>(null);
  const [focusAreas, setFocusAreas] = useState<FocusArea[]>([]);
  const [podcastScript, setPodcastScript] = useState('');
  const [result, setResult] = useState<EBResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Stats
  const [articlesSelected, setArticlesSelected] = useState(0);
  const [articlesAnalyzed, setArticlesAnalyzed] = useState(0);
  const [currentArticle, setCurrentArticle] = useState(0);
  const [currentArticleTitle, setCurrentArticleTitle] = useState('');

  // Saved briefings
  const [savedBriefings, setSavedBriefings] = useState<SavedBriefing[]>([]);
  const [isSaving, setIsSaving] = useState(false);
  const [isLoadingSaved, setIsLoadingSaved] = useState(false);

  // Ref for cleanup function
  const abortControllerRef = useRef<AbortController | null>(null);

  // Load cached result on mount
  useEffect(() => {
    try {
      const cached = localStorage.getItem(STORAGE_KEY);
      if (cached) {
        const data = JSON.parse(cached) as EBResult;
        setResult(data);
        setArticles(data.articles);
        setBriefingSummary(data.briefing_summary);
        setThemes(data.themes);
        setPriorityActions(data.priority_actions);
        setRiskSummary(data.risk_summary);
        setOpportunitySummary(data.opportunity_summary);
        setFocusAreas(data.focus_areas);
      }
    } catch (err) {
      console.error('Error loading cached executive briefing result:', err);
    }
  }, []);

  // Calculate overall progress based on stages
  const calculateOverallProgress = useCallback(
    (stage: string, progress: number): number => {
      const stageWeights: Record<string, { start: number; weight: number }> = {
        selection: { start: 0, weight: 0.25 },
        analysis: { start: 0.25, weight: 0.50 },
        synthesis: { start: 0.75, weight: 0.25 },
      };

      const stageInfo = stageWeights[stage];
      if (!stageInfo) return 0;

      return stageInfo.start + progress * stageInfo.weight;
    },
    []
  );

  // Start generation with SSE streaming
  const startGeneration = useCallback(
    async (config: EBConfig) => {
      // Reset state
      setIsGenerating(true);
      setCurrentStage('selection');
      setStageProgress(0);
      setOverallProgress(0);
      setArticles([]);
      setBriefingSummary('');
      setThemes([]);
      setPriorityActions([]);
      setRiskSummary(null);
      setOpportunitySummary(null);
      setFocusAreas([]);
      setPodcastScript('');
      setResult(null);
      setError(null);
      setArticlesSelected(0);
      setArticlesAnalyzed(0);
      setCurrentArticle(0);
      setCurrentArticleTitle('');

      // Create abort controller
      const abortController = new AbortController();
      abortControllerRef.current = abortController;

      try {
        const response = await fetch('/api/executive-briefing/scan', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          credentials: 'include',
          body: JSON.stringify({
            topic: config.topic,
            persona: config.persona,
            article_count: config.article_count,
            days_back: config.days_back,
            custom_persona: config.custom_persona,
            include_synthesis: config.include_synthesis,
            include_podcast_script: config.include_podcast_script || false,
            podcast_duration: config.podcast_duration || 'short',
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
                const data: EBProgress = JSON.parse(line.slice(6));

                // Update stage and progress
                setCurrentStage(data.stage);
                setStageProgress(data.progress);
                setOverallProgress(calculateOverallProgress(data.stage, data.progress));

                // Update stats
                if (data.articles_selected !== undefined) {
                  setArticlesSelected(data.articles_selected);
                }
                if (data.articles_analyzed !== undefined) {
                  setArticlesAnalyzed(data.articles_analyzed);
                }
                if (data.current_article !== undefined) {
                  setCurrentArticle(data.current_article);
                }
                if (data.article_title !== undefined) {
                  setCurrentArticleTitle(data.article_title);
                }

                // Handle completion
                if (data.stage === 'complete' && data.articles) {
                  setIsGenerating(false);
                  setCurrentStage('complete');
                  setStageProgress(1);
                  setOverallProgress(1);
                  setArticles(data.articles);
                  setBriefingSummary(data.briefing_summary || '');
                  setThemes(data.themes || []);
                  setPriorityActions(data.priority_actions || []);
                  setRiskSummary(data.risk_summary || null);
                  setOpportunitySummary(data.opportunity_summary || null);
                  setFocusAreas(data.focus_areas || []);
                  setPodcastScript(data.podcast_script || '');
                  setArticlesAnalyzed(data.articles.length);

                  const fullResult: EBResult = {
                    scan_id: data.scan_id || '',
                    articles: data.articles,
                    briefing_summary: data.briefing_summary || '',
                    themes: data.themes || [],
                    priority_actions: data.priority_actions || [],
                    risk_summary: data.risk_summary || {
                      overall_risk_level: 'moderate',
                      key_risks: [],
                      mitigation_opportunities: [],
                    },
                    opportunity_summary: data.opportunity_summary || {
                      overall_opportunity_level: 'moderate',
                      key_opportunities: [],
                      action_windows: [],
                    },
                    focus_areas: data.focus_areas || [],
                    podcast_script: data.podcast_script || '',
                    metadata: data.metadata,
                    total_articles: data.total_articles,
                  };
                  setResult(fullResult);

                  // Cache the result
                  try {
                    localStorage.setItem(STORAGE_KEY, JSON.stringify(fullResult));
                  } catch (err) {
                    console.error('Error caching executive briefing result:', err);
                  }
                }

                // Handle error
                if (data.stage === 'error' || data.status === 'error') {
                  setIsGenerating(false);
                  setError(extractErrorMessage(data.error, 'Generation failed'));
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
          setError(err.message || 'Failed to generate executive briefing');
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
    setArticles([]);
    setBriefingSummary('');
    setThemes([]);
    setPriorityActions([]);
    setRiskSummary(null);
    setOpportunitySummary(null);
    setFocusAreas([]);
    setPodcastScript('');
    setCurrentStage('');
    setStageProgress(0);
    setOverallProgress(0);
    setArticlesSelected(0);
    setArticlesAnalyzed(0);
    setCurrentArticle(0);
    setCurrentArticleTitle('');

    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch (err) {
      console.error('Error clearing cached executive briefing result:', err);
    }
  }, []);

  // Clear error
  const clearError = useCallback(() => {
    setError(null);
  }, []);

  // Load a saved result
  const loadResult = useCallback((loadedArticles: BriefingArticle[], loadedResult?: EBResult) => {
    setArticles(loadedArticles);
    setArticlesAnalyzed(loadedArticles.length);
    if (loadedResult) {
      setResult(loadedResult);
      setBriefingSummary(loadedResult.briefing_summary);
      setThemes(loadedResult.themes);
      setPriorityActions(loadedResult.priority_actions);
      setRiskSummary(loadedResult.risk_summary);
      setOpportunitySummary(loadedResult.opportunity_summary);
      setFocusAreas(loadedResult.focus_areas);
    } else {
      const newResult: EBResult = {
        scan_id: '',
        articles: loadedArticles,
        briefing_summary: '',
        themes: [],
        priority_actions: [],
        risk_summary: {
          overall_risk_level: 'moderate',
          key_risks: [],
          mitigation_opportunities: [],
        },
        opportunity_summary: {
          overall_opportunity_level: 'moderate',
          key_opportunities: [],
          action_windows: [],
        },
        focus_areas: [],
        metadata: {
          topic: '',
          persona: '',
          articles_analyzed: loadedArticles.length,
          articles_total: 0,
          generated_at: new Date().toISOString(),
          config: {
            article_count: loadedArticles.length,
            days_back: 7,
            include_synthesis: true,
          },
        },
      };
      setResult(newResult);
    }
    setCurrentStage('complete');
    setOverallProgress(1);
    setStageProgress(1);
  }, []);

  // Update an article (inline editing)
  const updateArticle = useCallback((index: number, updates: Partial<BriefingArticle>) => {
    setArticles((prev) =>
      prev.map((a, i) =>
        i === index ? { ...a, ...updates, user_edited: true } : a
      )
    );
    setResult((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        articles: prev.articles.map((a, i) =>
          i === index ? { ...a, ...updates, user_edited: true } : a
        ),
      };
    });
  }, []);

  // Save briefing to database
  const saveBriefing = useCallback(
    async (topic: string, name: string, description?: string) => {
      if (!result || articles.length === 0) {
        throw new Error('No briefing to save');
      }

      setIsSaving(true);
      try {
        const response = await fetch('/api/executive-briefing/save', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({
            topic,
            name,
            description,
            persona: result.metadata?.persona || 'CEO',
            article_count: articles.length,
            articles,
            briefing_summary: briefingSummary,
            themes,
            priority_actions: priorityActions,
            config: result.metadata?.config,
            metadata: result.metadata,
            articles_used: articles.length,
          }),
        });

        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}));
          throw new Error(errorData.detail || 'Failed to save briefing');
        }

        // Refresh the saved list
        await loadSavedBriefings(topic);
      } finally {
        setIsSaving(false);
      }
    },
    [result, articles, briefingSummary, themes, priorityActions]
  );

  // Load saved briefings for a topic
  const loadSavedBriefings = useCallback(async (topic: string) => {
    setIsLoadingSaved(true);
    try {
      const response = await fetch(`/api/executive-briefing/saved/${encodeURIComponent(topic)}`, {
        credentials: 'include',
      });

      if (!response.ok) {
        throw new Error('Failed to load saved briefings');
      }

      const data = await response.json();
      setSavedBriefings(data.saved_briefings || []);
    } catch (err) {
      console.error('Error loading saved briefings:', err);
      setSavedBriefings([]);
    } finally {
      setIsLoadingSaved(false);
    }
  }, []);

  // Load a specific saved briefing
  const loadSavedBriefing = useCallback(async (id: number) => {
    setIsLoadingSaved(true);
    try {
      const response = await fetch(`/api/executive-briefing/saved/load/${id}`, {
        credentials: 'include',
      });

      if (!response.ok) {
        throw new Error('Failed to load briefing');
      }

      const data = await response.json();
      const briefing = data.briefing;

      if (briefing) {
        const loadedResult: EBResult = {
          scan_id: '',
          articles: briefing.articles || [],
          briefing_summary: briefing.briefing_summary || '',
          themes: briefing.themes || [],
          priority_actions: briefing.priority_actions || [],
          risk_summary: {
            overall_risk_level: 'moderate',
            key_risks: [],
            mitigation_opportunities: [],
          },
          opportunity_summary: {
            overall_opportunity_level: 'moderate',
            key_opportunities: [],
            action_windows: [],
          },
          focus_areas: [],
          metadata: {
            topic: briefing.topic,
            persona: briefing.persona,
            articles_analyzed: briefing.articles_used || 0,
            articles_total: 0,
            generated_at: briefing.created_at,
            config: briefing.config || {},
          },
          total_articles: briefing.articles_used,
        };

        loadResult(briefing.articles || [], loadedResult);
      }
    } catch (err: any) {
      setError(err.message || 'Failed to load briefing');
    } finally {
      setIsLoadingSaved(false);
    }
  }, [loadResult]);

  // Delete a saved briefing
  const deleteSavedBriefing = useCallback(async (id: number) => {
    try {
      const response = await fetch(`/api/executive-briefing/saved/${id}`, {
        method: 'DELETE',
        credentials: 'include',
      });

      if (!response.ok) {
        throw new Error('Failed to delete briefing');
      }

      // Remove from local list
      setSavedBriefings((prev) => prev.filter((b) => b.id !== id));
    } catch (err: any) {
      setError(err.message || 'Failed to delete briefing');
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
    articles,
    briefingSummary,
    themes,
    priorityActions,
    riskSummary,
    opportunitySummary,
    focusAreas,
    podcastScript,
    result,
    error,
    articlesSelected,
    articlesAnalyzed,
    currentArticle,
    currentArticleTitle,
    savedBriefings,
    isSaving,
    isLoadingSaved,
    startGeneration,
    cancelGeneration,
    clearResults,
    clearError,
    loadResult,
    updateArticle,
    setPodcastScript,
    saveBriefing,
    loadSavedBriefings,
    loadSavedBriefing,
    deleteSavedBriefing,
  };
}
