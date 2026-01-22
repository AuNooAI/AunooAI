/**
 * Custom React hook for Power, Attention & Money (PAM) dashboard
 *
 * Tracks the three fundamental flows reshaping the knowledge economy:
 * - POWER: Infrastructure control, regulatory influence, research networks
 * - ATTENTION: Citation visibility, AI engine exposure, brand recognition
 * - MONEY: Funding flows, M&A activity, market concentration
 *
 * Follows the same pattern as useNewsletter, useFocusGroup for App.tsx integration.
 */

import { useState, useCallback, useRef } from 'react';
import { extractErrorMessage } from '../services/api';

// Utility function to convert snake_case to camelCase recursively
function snakeToCamelCase(str: string): string {
  return str.replace(/_([a-z])/g, (_, letter) => letter.toUpperCase());
}

function transformKeys(obj: any): any {
  if (obj === null || obj === undefined) {
    return obj;
  }
  if (Array.isArray(obj)) {
    return obj.map(item => transformKeys(item));
  }
  if (typeof obj === 'object') {
    const transformed: any = {};
    for (const key of Object.keys(obj)) {
      const camelKey = snakeToCamelCase(key);
      transformed[camelKey] = transformKeys(obj[key]);
    }
    return transformed;
  }
  return obj;
}

// Types
export interface PAMConfig {
  topic: string;
  analysisType: 'comprehensive' | 'power' | 'attention' | 'money';
  entityType: 'publisher' | 'tech_company' | 'research_institution' | 'government' | 'all';
  timeHorizon: 'current' | '6_months' | '1_year' | '5_years' | '2030';
  trendFocus: ('T1' | 'T2' | 'T3' | 'T4' | 'T5')[];
  daysBack: number;
  articleLimit: number;
  model: string;
}

export interface TrendStatus {
  id: 'T1' | 'T2' | 'T3' | 'T4' | 'T5';
  name: string;
  score: number;
  velocity: 'accelerating' | 'stable' | 'decelerating';
  confidence: 'high' | 'medium' | 'low';
  keyDrivers: string[];
  evidence: Array<{ finding: string; source: string }>;
  publisherImplications: string;
  urgency: 'immediate' | 'near_term' | 'medium_term';
}

export interface PAMScores {
  powerScore: number;
  attentionScore: number;
  moneyScore: number;
  overallScore: number;
  threatLevel: 'low' | 'moderate' | 'elevated' | 'high' | 'critical';
  // v2 data source indicators
  weightsUsed?: {
    power: number;
    attention: number;
    money: number;
  };
  dataSources?: {
    power: string[];
    attention: string[];
    money: string[];
  };
}

export interface ExecutiveSummary {
  headline: string;
  threatLevel: string;
  powerTakeaway: string;
  attentionTakeaway: string;
  moneyTakeaway: string;
  criticalTrend?: {
    id: string;
    name: string;
    urgency: string;
  };
  strategicPriorities: Array<{ priority: string; urgency: string }>;
  keyEvents: string[];
  emergingSignals: string[];
}

export interface PowerAnalysis {
  powerScore: number;
  infrastructureControl: {
    score: number;
    keyPlayers: string[];
    developments: string[];
    concentrationLevel: string;
  };
  regulatoryInfluence: {
    score: number;
    activeRegulations: string[];
    keyDevelopments: string[];
    direction: string;
  };
  networkCentrality: {
    score: number;
    influentialEntities: string[];
    collaborationTrends: string;
  };
  ipPositioning: {
    score: number;
    keyDeals: string[];
    trends: string;
  };
  // T2: Agentic AI Evidence
  t2Evidence?: {
    trendName: string;
    evidenceCount: number;
    trendDirection: string;
    toolsMentioned: string[];
    adoptionSignals: Array<{ entity: string; toolOrChange: string; source: string }>;
    automationExamples: string[];
    summary: string;
  };
  keyEvents: Array<{ event: string; impact: string; source: string }>;
  summary: string;
}

export interface AttentionAnalysis {
  attentionScore: number;
  academicVisibility: {
    score: number;
    citationTrends: string;
    keyIndicators: string[];
  };
  aiVisibility: {
    score: number;
    trainingDataExposure: string;
    metadataReadiness: number;
    provenanceStrength: number;
  };
  brandVisibility: {
    score: number;
    trafficTrends: string;
    keyChannels: string[];
  };
  synthesisExposure: {
    score: number;
    attributionRate: number;
    zeroClickRisk: string;
  };
  geoReadiness: {
    structuredMetadata: number;
    machineReadableRights: number;
    provenanceTagging: number;
    apiAccessibility: number;
    aiTrainingLicensing: number;
  };
  keyEvents: Array<{ event: string; impact: string; source: string }>;
  summary: string;
  // Entity tracking fields from attention agent
  entityMentions?: Array<{
    entity: string;
    mentionCount?: number;
    mention_count?: number;
    sentiment?: string;
    context?: string;
    articles?: string[];
  }>;
  entitySearchResults?: Record<string, number>;
  entityArticles?: Record<string, Array<{ uri: string; title: string; source: string }>>;
}

export interface MoneyAnalysis {
  moneyScore: number;
  fundingFlows: {
    totalEstimatedUsd: string;
    vcActivity: string;
    governmentFunding: string;
    keyDeals: Array<{ deal: string; value: string; parties: string[] }>;
  };
  revenueConcentration: {
    concentrationLevel: string;
    topPlayersShare: number;
    trend: string;
    keyMetrics: string[];
  };
  maActivity: {
    activityLevel: string;
    recentDeals: Array<{
      acquirer: string;
      target: string;
      value: string;
      type: string;
    }>;
    consolidationTrend: string;
  };
  costDynamics: {
    computeCostTrend: string;
    publishingCosts: string;
    keyFactors: string[];
  };
  keyEvents: Array<{ event: string; value?: string; impact: string; source: string }>;
  summary: string;
}

export interface ScenarioAnalysis {
  scenarios: {
    [key: string]: {
      name: string;
      description: string;
      baseProbability: number;
      currentProbability: number;
      regulationLevel: string;
      concentrationLevel: string;
    };
  };
  mostLikely: string;
  currentTrajectory: string;
  keyVariables: {
    regulationStrength: number;
    consolidationStrength: number;
  };
}

export interface Recommendation {
  title: string;
  description: string;
  dimension: 'power' | 'attention' | 'money';
  addressesTrends: string[];
  urgency: 'immediate' | 'near_term' | 'medium_term';
  effort: 'low' | 'medium' | 'high';
  impact: 'low' | 'medium' | 'high';
  rationale: string;
}

export interface ReferenceArticle {
  id: number;  // 1-based index for citation matching
  uri: string;
  title: string;
  source: string;
  publicationDate: string;
  topic: string;
  matchedTrend: string;
}

// v2 Config used in analysis
export interface PAMConfigUsed {
  relevanceThreshold?: number;
  articlesPerTopic?: number;
  enableExternalData?: boolean;
  parallelAgents?: boolean;
  models?: {
    power?: string;
    attention?: string;
    money?: string;
    trend?: string;
  };
}

export interface PAMData {
  runId: string;
  topic: string;
  analysisType: string;
  entityType: string;
  timeHorizon: string;
  executiveSummary: ExecutiveSummary;
  scores: PAMScores;
  powerAnalysis: PowerAnalysis | null;
  attentionAnalysis: AttentionAnalysis | null;
  moneyAnalysis: MoneyAnalysis | null;
  trendAnalysis: {
    trends: TrendStatus[];
    overallTrajectory: string;
    dominantTrend: string;
    emergingSignals: string[];
    scenarioImplications?: {
      mostLikelyScenario: string;
      probabilityShift: string;
    };
  };
  scenarioAnalysis: ScenarioAnalysis;
  strategicRecommendations: Recommendation[];
  articlesAnalyzed: number;
  articleUris: string[];
  referenceArticles: ReferenceArticle[];
  modelUsed: string;
  durationSeconds: number;
  createdAt: string;
  // v2 fields
  architectureVersion?: string;
  configUsed?: PAMConfigUsed;
  pillarQueries?: {
    power: string[];
    attention: string[];
    money: string[];
  };
}

export interface TrendDefinition {
  id: string;
  name: string;
  shortName: string;
  description: string;
  dimension: string;
  keywords: string[];
}

export interface PublisherPillar {
  id: string;
  name: string;
  description: string;
  components: string[];
}

export type PAMStage = 'idle' | 'fetching' | 'analyzing_power' | 'analyzing_attention' | 'analyzing_money' | 'synthesizing' | 'complete' | 'error';

export const PAM_STAGES = [
  { name: 'fetching', label: 'Fetching Articles', description: 'Gathering relevant articles from database' },
  { name: 'analyzing_power', label: 'Analyzing Power', description: 'Analyzing infrastructure & regulatory dynamics' },
  { name: 'analyzing_attention', label: 'Analyzing Attention', description: 'Analyzing visibility & discovery metrics' },
  { name: 'analyzing_money', label: 'Analyzing Money', description: 'Analyzing funding & market dynamics' },
  { name: 'synthesizing', label: 'Synthesizing', description: 'Creating executive summary & recommendations' },
  { name: 'complete', label: 'Complete', description: 'Analysis ready' },
];

export interface UsePAMReturn {
  // Generation state
  isGenerating: boolean;
  isLoadingCache: boolean;
  currentStage: PAMStage;
  stageProgress: number;
  overallProgress: number;

  // Data
  data: PAMData | null;
  trendDefinitions: TrendDefinition[];
  publisherPillars: PublisherPillar[];

  // Stats
  articlesFetched: number;
  articlesAnalyzed: number;

  // State
  error: string | null;
  hasCachedData: boolean;

  // Actions
  startGeneration: (config: PAMConfig) => Promise<void>;
  clearError: () => void;
  clearResults: () => void;
  loadDefinitions: () => Promise<void>;
  loadCachedReport: (topic?: string) => Promise<void>;
}

export function usePAM(): UsePAMReturn {
  // Generation state
  const [isGenerating, setIsGenerating] = useState(false);
  const [isLoadingCache, setIsLoadingCache] = useState(false);
  const [hasCachedData, setHasCachedData] = useState(false);
  const [currentStage, setCurrentStage] = useState<PAMStage>('idle');
  const [stageProgress, setStageProgress] = useState(0);
  const [overallProgress, setOverallProgress] = useState(0);

  // Data
  const [data, setData] = useState<PAMData | null>(null);
  const [trendDefinitions, setTrendDefinitions] = useState<TrendDefinition[]>([]);
  const [publisherPillars, setPublisherPillars] = useState<PublisherPillar[]>([]);

  // Stats
  const [articlesFetched, setArticlesFetched] = useState(0);
  const [articlesAnalyzed, setArticlesAnalyzed] = useState(0);

  // Error
  const [error, setError] = useState<string | null>(null);

  // Abort controller for cancellation
  const abortControllerRef = useRef<AbortController | null>(null);

  const loadDefinitions = useCallback(async () => {
    try {
      // Load trend definitions
      const trendResponse = await fetch('/api/pam/trends/definitions');
      if (trendResponse.ok) {
        const trendData = await trendResponse.json();
        if (trendData.success) {
          setTrendDefinitions(trendData.data.trends);
        }
      }

      // Load publisher pillars
      const pillarResponse = await fetch('/api/pam/publisher-pillars');
      if (pillarResponse.ok) {
        const pillarData = await pillarResponse.json();
        if (pillarData.success) {
          setPublisherPillars(pillarData.data.pillars);
        }
      }
    } catch (err) {
      console.error('Error loading PAM definitions:', err);
    }
  }, []);

  const loadCachedReport = useCallback(async (topic?: string) => {
    setIsLoadingCache(true);
    try {
      const url = topic
        ? `/api/pam/cached/latest?topic=${encodeURIComponent(topic)}`
        : '/api/pam/cached/latest';

      const response = await fetch(url);
      if (!response.ok) {
        console.log('📊 No cached PAM report available');
        return;
      }

      const result = await response.json();
      if (result.success && result.data && result.data.content_json) {
        // Parse the cached content
        const cachedContent = typeof result.data.content_json === 'string'
          ? JSON.parse(result.data.content_json)
          : result.data.content_json;

        // Transform the cached data using the same transformation as live data
        const transformedData: PAMData = {
          runId: cachedContent.run_id || '',
          topic: cachedContent.topic || '',
          analysisType: cachedContent.analysis_type || 'comprehensive',
          entityType: cachedContent.entity_type || 'publisher',
          timeHorizon: cachedContent.time_horizon || '1_year',
          executiveSummary: transformKeys(cachedContent.executive_summary) || {},
          scores: {
            powerScore: cachedContent.scores?.power_score || 50,
            attentionScore: cachedContent.scores?.attention_score || 50,
            moneyScore: cachedContent.scores?.money_score || 50,
            overallScore: cachedContent.scores?.overall_score || 50,
            threatLevel: cachedContent.scores?.threat_level || 'moderate',
            // v2 fields
            weightsUsed: cachedContent.scores?.weights_used ? transformKeys(cachedContent.scores.weights_used) : undefined,
            dataSources: cachedContent.scores?.data_sources ? transformKeys(cachedContent.scores.data_sources) : undefined,
          },
          powerAnalysis: cachedContent.power_analysis ? transformKeys(cachedContent.power_analysis) : null,
          attentionAnalysis: cachedContent.attention_analysis ? transformKeys(cachedContent.attention_analysis) : null,
          moneyAnalysis: cachedContent.money_analysis ? transformKeys(cachedContent.money_analysis) : null,
          trendAnalysis: transformKeys(cachedContent.trend_analysis) || {
            trends: [],
            overallTrajectory: '',
            dominantTrend: '',
            emergingSignals: [],
          },
          scenarioAnalysis: transformKeys(cachedContent.scenario_analysis) || {},
          strategicRecommendations: transformKeys(cachedContent.strategic_recommendations) || [],
          articlesAnalyzed: cachedContent.articles_analyzed || 0,
          articleUris: cachedContent.article_uris || [],
          referenceArticles: (transformKeys(cachedContent.reference_articles) || []).map((article: any, index: number) => ({
            ...article,
            id: index + 1  // 1-based index for citation matching [1], [2], etc.
          })),
          modelUsed: cachedContent.model_used || '',
          durationSeconds: cachedContent.duration_seconds || 0,
          createdAt: cachedContent.created_at || new Date().toISOString(),
          // v2 fields
          architectureVersion: cachedContent.architecture_version,
          configUsed: cachedContent.config_used ? transformKeys(cachedContent.config_used) : undefined,
          pillarQueries: cachedContent.pillar_queries ? transformKeys(cachedContent.pillar_queries) : undefined,
        };

        console.log('📊 Loaded cached PAM report:', {
          runId: transformedData.runId,
          createdAt: transformedData.createdAt,
          articlesAnalyzed: transformedData.articlesAnalyzed
        });

        setData(transformedData);
        setArticlesAnalyzed(transformedData.articlesAnalyzed);
        setHasCachedData(true);
        setCurrentStage('complete');
      }
    } catch (err) {
      console.error('Error loading cached PAM report:', err);
    } finally {
      setIsLoadingCache(false);
    }
  }, []);

  const handleSSEEvent = useCallback((eventData: any) => {
    const { stage, progress, articles_found, articles_analyzed, chunk, data: resultData } = eventData;

    console.log('📊 PAM SSE event:', { stage, progress });

    if (stage === 'fetching') {
      setCurrentStage('fetching');
      setStageProgress(progress || 0);
      setOverallProgress((progress || 0) * 0.15);
      if (articles_found) {
        setArticlesFetched(articles_found);
      }
    } else if (stage === 'analyzing_power') {
      setCurrentStage('analyzing_power');
      setStageProgress(progress || 0);
      setOverallProgress(0.15 + (progress || 0) * 0.2);
      if (articles_analyzed) {
        setArticlesAnalyzed(articles_analyzed);
      }
    } else if (stage === 'analyzing_attention') {
      setCurrentStage('analyzing_attention');
      setStageProgress(progress || 0);
      setOverallProgress(0.35 + (progress || 0) * 0.2);
    } else if (stage === 'analyzing_money') {
      setCurrentStage('analyzing_money');
      setStageProgress(progress || 0);
      setOverallProgress(0.55 + (progress || 0) * 0.2);
    } else if (stage === 'synthesizing') {
      setCurrentStage('synthesizing');
      setStageProgress(progress || 0);
      setOverallProgress(0.75 + (progress || 0) * 0.2);
    } else if (stage === 'complete') {
      setCurrentStage('complete');
      setStageProgress(1);
      setOverallProgress(1);

      if (resultData) {
        // Transform snake_case to camelCase recursively for nested objects
        const transformedData: PAMData = {
          runId: resultData.run_id || '',
          topic: resultData.topic || '',
          analysisType: resultData.analysis_type || 'comprehensive',
          entityType: resultData.entity_type || 'publisher',
          timeHorizon: resultData.time_horizon || '1_year',
          executiveSummary: transformKeys(resultData.executive_summary) || {},
          scores: {
            powerScore: resultData.scores?.power_score || 50,
            attentionScore: resultData.scores?.attention_score || 50,
            moneyScore: resultData.scores?.money_score || 50,
            overallScore: resultData.scores?.overall_score || 50,
            threatLevel: resultData.scores?.threat_level || 'moderate',
            // v2 fields
            weightsUsed: resultData.scores?.weights_used ? transformKeys(resultData.scores.weights_used) : undefined,
            dataSources: resultData.scores?.data_sources ? transformKeys(resultData.scores.data_sources) : undefined,
          },
          powerAnalysis: resultData.power_analysis ? transformKeys(resultData.power_analysis) : null,
          attentionAnalysis: resultData.attention_analysis ? transformKeys(resultData.attention_analysis) : null,
          moneyAnalysis: resultData.money_analysis ? transformKeys(resultData.money_analysis) : null,
          trendAnalysis: transformKeys(resultData.trend_analysis) || {
            trends: [],
            overallTrajectory: '',
            dominantTrend: '',
            emergingSignals: [],
          },
          scenarioAnalysis: transformKeys(resultData.scenario_analysis) || {},
          strategicRecommendations: transformKeys(resultData.strategic_recommendations) || [],
          articlesAnalyzed: resultData.articles_analyzed || 0,
          articleUris: resultData.article_uris || [],
          referenceArticles: (transformKeys(resultData.reference_articles) || []).map((article: any, index: number) => ({
            ...article,
            id: index + 1  // 1-based index for citation matching [1], [2], etc.
          })),
          modelUsed: resultData.model_used || '',
          durationSeconds: resultData.duration_seconds || 0,
          createdAt: resultData.created_at || new Date().toISOString(),
          // v2 fields
          architectureVersion: resultData.architecture_version,
          configUsed: resultData.config_used ? transformKeys(resultData.config_used) : undefined,
          pillarQueries: resultData.pillar_queries ? transformKeys(resultData.pillar_queries) : undefined,
        };

        console.log('📊 Transformed PAM data:', transformedData);
        setData(transformedData);
        setArticlesAnalyzed(transformedData.articlesAnalyzed);
      }
    } else if (stage === 'error') {
      setCurrentStage('error');
      setError(extractErrorMessage(eventData.message || eventData.error, 'Analysis failed'));
    }
  }, []);

  const startGeneration = useCallback(async (config: PAMConfig) => {
    // Cancel any existing generation
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    abortControllerRef.current = new AbortController();

    setIsGenerating(true);
    setCurrentStage('fetching');
    setStageProgress(0);
    setOverallProgress(0);
    setError(null);
    setData(null);
    setArticlesFetched(0);
    setArticlesAnalyzed(0);

    try {
      console.log('📊 Starting PAM analysis with config:', config);
      const response = await fetch('/api/pam/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          topic: config.topic,
          analysis_type: config.analysisType,
          entity_type: config.entityType,
          time_horizon: config.timeHorizon,
          trend_focus: config.trendFocus,
          days_back: config.daysBack,
          article_limit: config.articleLimit,
          model: config.model,
        }),
        signal: abortControllerRef.current.signal,
      });

      console.log('📊 Response status:', response.status);

      // Check if we got SSE or JSON response
      const contentType = response.headers.get('content-type');

      if (contentType?.includes('text/event-stream')) {
        // SSE streaming response
        const reader = response.body?.getReader();
        if (!reader) throw new Error('No response stream');

        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) {
            console.log('📊 SSE stream ended');
            break;
          }

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                const eventData = JSON.parse(line.slice(6));
                handleSSEEvent(eventData);
              } catch (e) {
                console.warn('Failed to parse SSE event:', e, line);
              }
            }
          }
        }
      } else {
        // Non-streaming JSON response (fallback)
        if (!response.ok) {
          const text = await response.text();
          console.error('📊 Error response:', text);
          throw new Error(`Analysis failed: ${response.status}`);
        }

        const result = await response.json();

        if (result.success) {
          handleSSEEvent({ stage: 'complete', data: result.data });
        } else {
          throw new Error(result.message || 'Analysis failed');
        }
      }
    } catch (err: any) {
      if (err.name === 'AbortError') {
        console.log('PAM analysis cancelled');
      } else {
        console.error('PAM analysis error:', err);
        setError(err.message || 'Analysis failed');
        setCurrentStage('error');
      }
    } finally {
      setIsGenerating(false);
    }
  }, [handleSSEEvent]);

  const clearError = useCallback(() => {
    setError(null);
  }, []);

  const clearResults = useCallback(() => {
    setData(null);
    setCurrentStage('idle');
    setStageProgress(0);
    setOverallProgress(0);
    setArticlesFetched(0);
    setArticlesAnalyzed(0);
  }, []);

  return {
    isGenerating,
    isLoadingCache,
    currentStage,
    stageProgress,
    overallProgress,
    data,
    trendDefinitions,
    publisherPillars,
    articlesFetched,
    articlesAnalyzed,
    error,
    hasCachedData,
    startGeneration,
    clearError,
    clearResults,
    loadDefinitions,
    loadCachedReport,
  };
}

export default usePAM;
