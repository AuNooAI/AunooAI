/**
 * Power, Attention & Money (PAM) Dashboard
 *
 * Strategic intelligence dashboard for tracking the three fundamental flows
 * reshaping the knowledge economy, structured around the 5 Key Trends for 2030.
 *
 * This component follows the same pattern as Newsletter, FocusGroup, etc.
 * - Receives all state and config from parent (App.tsx)
 * - Uses global topic selector and toolbar buttons
 * - No internal header or controls
 */

import React, { useState, useMemo, useEffect } from 'react';
import { Loader2, AlertCircle, BarChart3, Zap, Eye, DollarSign, Target, TrendingUp, TrendingDown, Minus, BookOpen, ExternalLink, ChevronDown, ChevronUp, Info, HelpCircle, Database, Bot, Globe, GraduationCap, Lightbulb, Scale, Building2, Calendar, Briefcase } from 'lucide-react';
import { Alert, AlertDescription } from '../ui/alert';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Progress } from '../ui/progress';
import { Badge } from '../ui/badge';
import { Tooltip, TooltipContent, TooltipTrigger } from '../ui/tooltip';
import type { PAMData, TrendStatus, ReferenceArticle, Recommendation } from '../../hooks/usePAM';
import { renderCitationsAsLinks, Article } from '../../utils/citationRenderer';
import '../../styles/citations.css';
import TrendsRadarCompact, { TREND_TO_PILLAR } from './TrendsRadarCompact';
import ScenarioMiniMatrix from './ScenarioMiniMatrix';
import RecommendationCard from './RecommendationCard';

// Qualitative level type and helpers
type QualitativeLevel = 'none' | 'low' | 'medium' | 'high' | 'very_high';

const LEVEL_CONFIG: Record<QualitativeLevel, { label: string; color: string; bgColor: string; numericEquiv: number }> = {
  none: { label: 'None', color: 'text-gray-500 dark:text-gray-300', bgColor: 'bg-gray-100', numericEquiv: 0 },
  low: { label: 'Low', color: 'text-green-600', bgColor: 'bg-green-100', numericEquiv: 25 },
  medium: { label: 'Medium', color: 'text-yellow-600', bgColor: 'bg-yellow-100', numericEquiv: 50 },
  high: { label: 'High', color: 'text-orange-600', bgColor: 'bg-orange-100', numericEquiv: 75 },
  very_high: { label: 'Very High', color: 'text-red-600', bgColor: 'bg-red-100', numericEquiv: 95 },
};

// Convert qualitative level to numeric (for backward compatibility with overall calculations)
const levelToNumeric = (level: string | undefined | null): number => {
  if (!level) return 50; // Default to medium
  const config = LEVEL_CONFIG[level as QualitativeLevel];
  return config?.numericEquiv ?? 50;
};

// Get level from numeric score (for backward compatibility with old data)
const numericToLevel = (score: number | undefined | null): QualitativeLevel => {
  if (score === null || score === undefined) return 'medium';
  if (score <= 10) return 'none';
  if (score <= 35) return 'low';
  if (score <= 60) return 'medium';
  if (score <= 80) return 'high';
  return 'very_high';
};

// Score explanations
const SCORE_EXPLANATIONS = {
  power: "Power level measures infrastructure control, regulatory influence, network centrality, and IP positioning. Higher levels indicate greater concentration of power in the knowledge economy.",
  attention: "Attention level measures AI visibility, brand recognition, citation exposure, and GEO readiness. Higher levels indicate greater risk of attention being diverted away from traditional channels.",
  money: "Money Flow tracks funding patterns, M&A activity, revenue concentration, and cost dynamics. Higher scores indicate greater financial disruption or consolidation.",
  overall: "Overall threat assessment combining all PAM dimensions. Based on qualitative levels for Power/Attention and numeric score for Money.",
  trend: "Trend score indicates the current intensity and momentum of this trend based on recent article coverage. Higher scores mean the trend is more prominent in current news.",
  analysis: "Assessment indicating the strength or risk level of this dimension. Higher levels generally indicate greater disruption potential or market concentration.",
};

// Calculate threat level dynamically from scores (in case cached data has wrong value)
const calculateThreatLevel = (powerScore: number, attentionScore: number, moneyScore: number): string => {
  const overall = (powerScore * 0.35) + (attentionScore * 0.35) + (moneyScore * 0.30);
  if (overall >= 80) return 'critical';
  if (overall >= 70) return 'high';
  if (overall >= 55) return 'elevated';
  if (overall >= 40) return 'moderate';
  return 'low';
};

// Calculate overall score
const calculateOverallScore = (powerScore: number, attentionScore: number, moneyScore: number): number => {
  return Math.round(((powerScore * 0.35) + (attentionScore * 0.35) + (moneyScore * 0.30)) * 10) / 10;
};

// Format currency values properly (handle billions, millions, thousands)
const formatCurrency = (value: number | null | undefined): string => {
  if (value === null || value === undefined) return 'N/A';

  const absValue = Math.abs(value);

  if (absValue >= 1_000_000_000) {
    // Billions
    const billions = value / 1_000_000_000;
    return `$${billions.toFixed(billions >= 10 ? 0 : 1)}B`;
  } else if (absValue >= 1_000_000) {
    // Millions
    const millions = value / 1_000_000;
    return `$${millions.toFixed(millions >= 100 ? 0 : 1)}M`;
  } else if (absValue >= 1_000) {
    // Thousands
    const thousands = value / 1_000;
    return `$${thousands.toFixed(0)}K`;
  } else {
    return `$${value.toFixed(0)}`;
  }
};

// Deal types that should be hidden (internal metadata)
const HIDDEN_DEAL_TYPES = ['horizontal', 'vertical', 'internal', 'unknown'];

const SCENARIO_EXPLANATIONS = {
  probability: "Probability percentage indicates how likely this scenario is based on current trend analysis. Derived from PAM scores and trend velocities.",
  mostLikely: "The 'Most Likely' scenario is determined by analyzing current power structures, attention flows, and money movements. It represents the trajectory we're most likely heading toward if current trends continue.",
};

// Metric explanations for Attention pillar (evaluated indirectly via news reporting)
const ATTENTION_METRIC_EXPLANATIONS = {
  trainingDataExposure: "Training Data Exposure indicates the prevalence of content being used in AI training datasets, as reported in news and disclosed agreements. Low = rarely mentioned, Medium = some coverage, High = frequently reported.",
  metadataReadiness: "Metadata Readiness measures how well-structured publisher content metadata is for AI consumption (0-100), based on industry assessments and reported standards adoption.",
  provenanceStrength: "Provenance Strength measures how well publisher content maintains attribution chains and origin verification (0-100), based on reported compliance and trust initiatives.",
  synthesisExposure: "Synthesis Exposure measures how often publisher content appears in AI-generated summaries without attribution, based on reported trends and industry studies.",
  zeroClickRisk: "Zero-Click Risk assesses the trend of users getting AI-synthesized answers instead of visiting publisher sites, based on news coverage and industry reports. Low = minimal impact reported, High = significant displacement reported.",
  attributionRate: "Attribution Rate reflects how often AI systems properly credit source content (0-100), based on news coverage of attribution practices and licensing agreements.",
};

// Metric explanations for Money pillar
const MONEY_METRIC_EXPLANATIONS = {
  maActivity: "M&A Activity Level indicates the intensity of mergers, acquisitions, and consolidation in the sector. Derived from recent deal announcements and market signals.",
  consolidationTrend: "Consolidation Trend shows whether market concentration is accelerating (more deals), stable, or slowing (fewer deals).",
  vcActivity: "VC Activity tracks venture capital investment trends in the knowledge economy. Increasing = more funding flowing in.",
  governmentFunding: "Government Funding tracks public research grants and subsidies. Increasing = more policy support for the sector.",
};

// Event types for extracted events
interface FinancialEvent {
  id: string;
  event_date: string;
  event_type: string;
  acquirer: string;
  target: string;
  deal_value_usd: number | null;
  funding_round: string | null;
  headline: string;
  summary: string;
  strategic_significance: string;
}

interface RegulatoryEvent {
  id: string;
  event_date: string;
  jurisdiction: string;
  regulation_name: string;
  event_type: string;
  headline: string;
  summary: string;
  publisher_implications: string;
  tech_implications: string;
  t4_impact_score: number | null;
}

// Stage definitions for progress indicator
export const PAM_STAGES = [
  { name: 'fetching', label: 'Fetching Articles', icon: '📥' },
  { name: 'analyzing_power', label: 'Analyzing Power', icon: '⚡' },
  { name: 'analyzing_attention', label: 'Analyzing Attention', icon: '👁' },
  { name: 'analyzing_money', label: 'Analyzing Money', icon: '💰' },
  { name: 'synthesizing', label: 'Synthesizing', icon: '🔄' },
  { name: 'complete', label: 'Complete', icon: '✓' },
];

interface PAMDashboardProps {
  topic?: string;
  // State from parent
  isGenerating: boolean;
  currentStage: string;
  stageProgress: number;
  data: PAMData | null;
  error: string | null;
  // View state
  activeView: 'executive' | 'power' | 'attention' | 'money' | 'scenarios';
  onViewChange: (view: 'executive' | 'power' | 'attention' | 'money' | 'scenarios') => void;
  // Actions
  onClearError: () => void;
}

// Stage indicator component
function StageIndicator({
  stages,
  currentStage,
  stageProgress
}: {
  stages: typeof PAM_STAGES;
  currentStage: string;
  stageProgress: number;
}) {
  const getStageStatus = (stageName: string) => {
    const currentIndex = stages.findIndex(s => s.name === currentStage);
    const stageIndex = stages.findIndex(s => s.name === stageName);

    if (currentStage === 'complete') return 'complete';
    if (stageIndex < currentIndex) return 'complete';
    if (stageIndex === currentIndex) return 'active';
    return 'pending';
  };

  return (
    <div className="flex items-center gap-2 mb-6">
      {stages.map((stage, index) => {
        const status = getStageStatus(stage.name);
        return (
          <React.Fragment key={stage.name}>
            <div className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm ${
              status === 'complete' ? 'bg-pink-100 text-pink-700' :
              status === 'active' ? 'bg-pink-500 text-white' :
              'bg-gray-100 text-gray-500 dark:text-gray-300'
            }`}>
              <span>{stage.icon}</span>
              <span className="hidden sm:inline">{stage.label}</span>
            </div>
            {index < stages.length - 1 && (
              <div className={`w-8 h-0.5 ${
                status === 'complete' ? 'bg-pink-300' : 'bg-gray-200'
              }`} />
            )}
          </React.Fragment>
        );
      })}
    </div>
  );
}

// Info icon with tooltip helper
const InfoTooltip: React.FC<{ text: string; className?: string }> = ({ text, className = '' }) => (
  <Tooltip>
    <TooltipTrigger asChild>
      <button type="button" className={`inline-flex items-center text-gray-400 dark:text-gray-400 hover:text-gray-600 dark:text-gray-300 ${className}`}>
        <HelpCircle className="w-4 h-4" />
      </button>
    </TooltipTrigger>
    <TooltipContent className="max-w-xs bg-gray-900 text-white text-xs p-2">
      {text}
    </TooltipContent>
  </Tooltip>
);

// Data Source Badge - shows whether metric is measured or LLM-estimated
type DataSourceType = 'measured' | 'external_api' | 'llm_analysis' | 'calculated';

const DATA_SOURCE_CONFIG: Record<DataSourceType, { label: string; icon: React.ReactNode; color: string; description: string }> = {
  measured: {
    label: 'Measured',
    icon: <Database className="w-3 h-3" />,
    color: 'bg-green-100 text-green-700 border-green-200',
    description: 'Based on countable metrics from article analysis'
  },
  external_api: {
    label: 'External API',
    icon: <Globe className="w-3 h-3" />,
    color: 'bg-blue-100 text-blue-700 border-blue-200',
    description: 'Data from external APIs (Semantic Scholar, Google Search)'
  },
  llm_analysis: {
    label: 'LLM Analysis',
    icon: <Bot className="w-3 h-3" />,
    color: 'bg-purple-100 text-purple-700 border-purple-200',
    description: 'Estimated by AI model analysis'
  },
  calculated: {
    label: 'Calculated',
    icon: <BarChart3 className="w-3 h-3" />,
    color: 'bg-amber-100 text-amber-700 border-amber-200',
    description: 'Derived from weighted formula of other metrics'
  }
};

const DataSourceBadge: React.FC<{ source: DataSourceType; className?: string }> = ({ source, className = '' }) => {
  const config = DATA_SOURCE_CONFIG[source];
  if (!config) return null;

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs border ${config.color} ${className}`}>
          {config.icon}
          <span className="hidden sm:inline">{config.label}</span>
        </span>
      </TooltipTrigger>
      <TooltipContent className="max-w-xs bg-gray-900 text-white text-xs p-2">
        {config.description}
      </TooltipContent>
    </Tooltip>
  );
};

// Config used indicator for v2 analysis
interface ConfigUsedProps {
  config?: {
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
  };
  architectureVersion?: string;
}

const ConfigUsedIndicator: React.FC<ConfigUsedProps> = ({ config, architectureVersion }) => {
  if (!config && !architectureVersion) return null;

  const isV2 = architectureVersion === '2.0';

  return (
    <div className="mt-4 p-3 bg-gray-50 rounded-lg border border-gray-200">
      <div className="flex items-center gap-2 mb-2">
        <Badge variant={isV2 ? 'default' : 'outline'} className={isV2 ? 'bg-pink-500' : ''}>
          {isV2 ? 'v2.0 Agent Architecture' : 'v1.0 Legacy'}
        </Badge>
        {config?.enableExternalData && (
          <Badge variant="outline" className="text-blue-600 border-blue-200">
            <Globe className="w-3 h-3 mr-1" />
            External Data
          </Badge>
        )}
        {config?.parallelAgents && (
          <Badge variant="outline" className="text-green-600 border-green-200">
            Parallel Agents
          </Badge>
        )}
      </div>
      {config && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs text-gray-600 dark:text-gray-300">
          {config.relevanceThreshold && (
            <span>Relevance: {config.relevanceThreshold}</span>
          )}
          {config.articlesPerTopic && (
            <span>Articles/Topic: {config.articlesPerTopic}</span>
          )}
          {config.models?.power && (
            <span>Power: {config.models.power.split('/').pop()}</span>
          )}
          {config.models?.attention && (
            <span>Attention: {config.models.attention.split('/').pop()}</span>
          )}
        </div>
      )}
    </div>
  );
};

// Score Card component (for Money - keeps numeric score)
const ScoreCard: React.FC<{
  label: string;
  score: number;
  icon: React.ReactNode;
  color: string;
  explanation?: string;
  dataSource?: DataSourceType;
}> = ({ label, score, icon, color, explanation, dataSource }) => {
  const getScoreClass = (score: number) => {
    if (score >= 70) return 'text-red-500';
    if (score >= 50) return 'text-yellow-500';
    return 'text-green-500';
  };

  return (
    <Card>
      <CardContent className="pt-6">
        <div className="flex items-center justify-between">
          <div className={`p-2 rounded-lg ${color}`}>
            {icon}
          </div>
          <div className="text-right">
            <p className={`text-3xl font-bold ${getScoreClass(score)}`}>{score}</p>
            <div className="flex items-center justify-end gap-1">
              <p className="text-sm text-gray-500 dark:text-gray-300">{label}</p>
              {explanation && <InfoTooltip text={explanation} />}
            </div>
          </div>
        </div>
        <Progress value={score} className="mt-3 h-2" />
        {dataSource && (
          <div className="mt-2 flex justify-end">
            <DataSourceBadge source={dataSource} />
          </div>
        )}
      </CardContent>
    </Card>
  );
};

// Level Card component (for Power/Attention - qualitative display)
const LevelCard: React.FC<{
  label: string;
  level: string | undefined | null;
  numericFallback?: number;
  icon: React.ReactNode;
  iconBgColor: string;
  explanation?: string;
}> = ({ label, level, numericFallback, icon, iconBgColor, explanation }) => {
  // Determine the level - prefer explicit level, fall back to converting numeric
  const effectiveLevel: QualitativeLevel = level
    ? (level as QualitativeLevel)
    : numericToLevel(numericFallback);

  const config = LEVEL_CONFIG[effectiveLevel] || LEVEL_CONFIG.medium;

  return (
    <Card>
      <CardContent className="pt-6">
        <div className="flex items-center justify-between">
          <div className={`p-2 rounded-lg ${iconBgColor}`}>
            {icon}
          </div>
          <div className="text-right">
            <p className={`text-2xl font-bold ${config.color}`}>{config.label}</p>
            <div className="flex items-center justify-end gap-1">
              <p className="text-sm text-gray-500 dark:text-gray-300">{label}</p>
              {explanation && <InfoTooltip text={explanation} />}
            </div>
          </div>
        </div>
        {/* Level indicator bar */}
        <div className="mt-3 flex gap-1">
          {(['none', 'low', 'medium', 'high', 'very_high'] as QualitativeLevel[]).map((lvl) => {
            const isActive = ['none', 'low', 'medium', 'high', 'very_high'].indexOf(lvl) <= ['none', 'low', 'medium', 'high', 'very_high'].indexOf(effectiveLevel);
            return (
              <div
                key={lvl}
                className={`h-2 flex-1 rounded-sm ${isActive ? config.bgColor : 'bg-gray-200'}`}
              />
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
};

// Trend item component with expandable details
const TrendItem: React.FC<{ trend: TrendStatus; articles?: Article[] }> = ({ trend, articles = [] }) => {
  const [isExpanded, setIsExpanded] = useState(false);

  const getVelocityIcon = (velocity: string) => {
    switch (velocity) {
      case 'accelerating': return <TrendingUp className="w-4 h-4 text-green-500" />;
      case 'decelerating': return <TrendingDown className="w-4 h-4 text-amber-500" />;
      default: return <Minus className="w-4 h-4 text-gray-400 dark:text-gray-400" />;
    }
  };

  const getVelocityLabel = (velocity: string) => {
    switch (velocity) {
      case 'accelerating': return 'Accelerating';
      case 'decelerating': return 'Decelerating';
      default: return 'Stable';
    }
  };

  const getUrgencyColor = (urgency: string) => {
    switch (urgency) {
      case 'immediate': return 'bg-red-100 text-red-700 border-red-200';
      case 'near_term': return 'bg-yellow-100 text-yellow-700 border-yellow-200';
      default: return 'bg-blue-100 text-blue-700 border-blue-200';
    }
  };

  return (
    <div className="p-4 bg-gray-50 rounded-lg">
      <div
        className="cursor-pointer"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="text-pink-600 border-pink-200">
              {trend.id}
            </Badge>
            <span className="font-medium text-gray-900 dark:text-gray-100">{trend.name}</span>
          </div>
          <div className="flex items-center gap-2">
            {getVelocityIcon(trend.velocity)}
            <span className="text-sm font-semibold">{Math.round(trend.score)}%</span>
            {isExpanded ? <ChevronUp className="w-4 h-4 text-gray-400 dark:text-gray-400" /> : <ChevronDown className="w-4 h-4 text-gray-400 dark:text-gray-400" />}
          </div>
        </div>
        <Progress value={trend.score} className="h-2 mb-2" />
        <div className="flex items-center gap-2 flex-wrap">
          <Badge variant="outline" className="text-xs">
            {getVelocityLabel(trend.velocity)}
          </Badge>
          {trend.confidence && (
            <Badge variant="outline" className="text-xs capitalize">
              {trend.confidence} confidence
            </Badge>
          )}
          {trend.urgency && (
            <Badge className={`text-xs ${getUrgencyColor(trend.urgency)}`}>
              {trend.urgency === 'immediate' ? 'Urgent' : trend.urgency === 'near_term' ? 'Near Term' : 'Medium Term'}
            </Badge>
          )}
        </div>
      </div>

      {/* Expanded details */}
      {isExpanded && (
        <div className="mt-3 pt-3 border-t border-gray-200 space-y-3">
          {/* Key Drivers */}
          {trend.keyDrivers && trend.keyDrivers.length > 0 && (
            <div>
              <h5 className="text-xs font-semibold text-gray-500 dark:text-gray-300 uppercase mb-1">Key Drivers</h5>
              <ul className="space-y-1">
                {trend.keyDrivers.slice(0, 3).map((driver: string, i: number) => (
                  <li key={i} className="text-sm text-gray-700 dark:text-gray-200 flex items-start gap-1">
                    <span className="text-pink-500">•</span>
                    <CitationText text={driver} articles={articles} />
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Evidence */}
          {trend.evidence && trend.evidence.length > 0 && (
            <div>
              <h5 className="text-xs font-semibold text-gray-500 dark:text-gray-300 uppercase mb-1">Evidence</h5>
              <ul className="space-y-1">
                {trend.evidence.slice(0, 2).map((ev: any, i: number) => (
                  <li key={i} className="text-sm text-gray-600 dark:text-gray-300 flex items-start gap-1">
                    <span className="text-blue-500">→</span>
                    <CitationText text={typeof ev === 'string' ? ev : ev.finding} articles={articles} />
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Publisher Implications */}
          {trend.publisherImplications && (
            <div>
              <h5 className="text-xs font-semibold text-gray-500 dark:text-gray-300 uppercase mb-1">Publisher Implications</h5>
              <p className="text-sm text-gray-700 dark:text-gray-200">
                <CitationText text={trend.publisherImplications} articles={articles} />
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

// Urgency order for sorting recommendations
const URGENCY_ORDER: Record<string, number> = {
  immediate: 0,
  near_term: 1,
  medium_term: 2,
};

// Executive Overview View - REDESIGNED
const ExecutiveOverview: React.FC<{
  data: PAMData;
  articles: Article[];
  onViewChange: (view: 'power' | 'attention' | 'money' | 'scenarios') => void;
}> = ({ data, articles, onViewChange }) => {
  // State to show all recommendations
  const [showAllRecommendations, setShowAllRecommendations] = useState(false);

  // Extract qualitative levels (new format) and numeric scores (for backward compatibility)
  // All pillars now use qualitative levels: none, low, medium, high, very_high
  const powerLevel = data.power?.powerLevel || data.power?.power_level || null;
  const attentionLevel = data.attention?.attentionLevel || data.attention?.attention_level || null;
  const moneyLevel = data.money?.moneyLevel || data.money?.money_level || null;

  // Convert levels to numeric for overall threat calculation (backward compat)
  const powerScore = powerLevel ? levelToNumeric(powerLevel) : (data.scores?.powerScore || 0);
  const attentionScore = attentionLevel ? levelToNumeric(attentionLevel) : (data.scores?.attentionScore || 0);
  const moneyScore = moneyLevel ? levelToNumeric(moneyLevel) : (data.scores?.moneyScore || 0);

  const threatLevel = calculateThreatLevel(powerScore, attentionScore, moneyScore);
  const overallScore = calculateOverallScore(powerScore, attentionScore, moneyScore);

  // Handle trend click -> switch to relevant pillar tab
  const handleTrendClick = (trendId: string) => {
    const pillar = TREND_TO_PILLAR[trendId];
    if (pillar) {
      onViewChange(pillar);
    }
  };

  // Handle scenario click -> switch to scenarios tab
  const handleScenarioClick = () => {
    onViewChange('scenarios');
  };

  // Sort recommendations by urgency
  const sortedRecommendations = [...(data.strategicRecommendations || [])]
    .sort((a, b) => (URGENCY_ORDER[a.urgency] || 2) - (URGENCY_ORDER[b.urgency] || 2));

  return (
    <div className="space-y-6">
      {/* Headline with Trajectory and Dominant Trend */}
      <Card className="border-l-4 border-l-pink-500">
        <CardContent className="pt-4 pb-4">
          {data.executiveSummary?.headline && (
            <p className="text-lg font-medium text-gray-900 dark:text-gray-100 mb-2">
              <CitationText text={data.executiveSummary.headline} articles={articles} />
            </p>
          )}
          <div className="flex flex-wrap items-center gap-3 text-sm">
            {/* Overall Trajectory */}
            {data.trendAnalysis?.overallTrajectory && (
              <span className="text-gray-600 dark:text-gray-300">
                <strong>Trajectory:</strong> {data.trendAnalysis.overallTrajectory}
              </span>
            )}
            {/* Dominant Trend */}
            {data.trendAnalysis?.dominantTrend && (
              <Badge
                className="bg-red-100 text-red-700 cursor-pointer hover:bg-red-200"
                onClick={() => handleTrendClick(data.trendAnalysis?.dominantTrend?.split(':')[0] || '')}
              >
                Dominant: {data.trendAnalysis.dominantTrend}
              </Badge>
            )}
            {/* Threat Level */}
            <Badge className={`${
              threatLevel === 'critical' ? 'bg-red-600 text-white' :
              threatLevel === 'high' ? 'bg-orange-500 text-white' :
              threatLevel === 'elevated' ? 'bg-yellow-500 text-white' :
              threatLevel === 'moderate' ? 'bg-blue-500 text-white' :
              'bg-green-500 text-white'
            }`}>
              {threatLevel.toUpperCase()} ({overallScore})
            </Badge>
          </div>
        </CardContent>
      </Card>

      {/* PAM Cards - Power/Attention use qualitative levels, Money uses numeric */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <LevelCard
          label="Power"
          level={powerLevel}
          numericFallback={powerScore}
          icon={<Zap className="w-4 h-4 text-yellow-600" />}
          iconBgColor="bg-yellow-100"
          explanation={SCORE_EXPLANATIONS.power}
        />
        <LevelCard
          label="Attention"
          level={attentionLevel}
          numericFallback={attentionScore}
          icon={<Eye className="w-4 h-4 text-blue-600" />}
          iconBgColor="bg-blue-100"
          explanation={SCORE_EXPLANATIONS.attention}
        />
        <LevelCard
          label="Money"
          level={moneyLevel}
          numericFallback={moneyScore}
          icon={<DollarSign className="w-4 h-4 text-green-600" />}
          iconBgColor="bg-green-100"
          explanation={SCORE_EXPLANATIONS.money}
        />
        <Card className="cursor-pointer hover:shadow-md transition-shadow" onClick={handleScenarioClick}>
          <CardContent className="pt-4 pb-4">
            <div className="text-center">
              <p className="text-xs text-gray-500 dark:text-gray-300 uppercase">Most Likely</p>
              <p className="text-sm font-bold mt-1 text-pink-600">
                {data.scenarioAnalysis?.mostLikely?.replace(/_/g, ' ') || 'Unknown'}
              </p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Trends Radar + Scenario Matrix - Side by Side */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Trends Radar - 2 columns */}
        <div className="lg:col-span-2">
          <TrendsRadarCompact
            trends={data.trendAnalysis?.trends || []}
            onTrendClick={handleTrendClick}
          />
        </div>

        {/* Scenario Mini Matrix - 1 column */}
        <div>
          <ScenarioMiniMatrix
            scenarios={data.scenarioAnalysis?.scenarios}
            mostLikely={data.scenarioAnalysis?.mostLikely}
            probabilityShift={data.trendAnalysis?.scenarioImplications?.probabilityShift}
            onClick={handleScenarioClick}
          />
        </div>
      </div>

      {/* Strategic Recommendations */}
      {sortedRecommendations.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2">
              <Lightbulb className="w-5 h-5 text-amber-500" />
              Strategic Recommendations
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {(showAllRecommendations ? sortedRecommendations : sortedRecommendations.slice(0, 3)).map((rec, i) => (
              <RecommendationCard
                key={i}
                recommendation={rec}
                onTrendClick={handleTrendClick}
                compact
              />
            ))}
            {sortedRecommendations.length > 3 && (
              <button
                className="text-sm text-pink-600 hover:text-pink-700 font-medium"
                onClick={() => setShowAllRecommendations(!showAllRecommendations)}
              >
                {showAllRecommendations
                  ? '← Show fewer recommendations'
                  : `View all ${sortedRecommendations.length} recommendations →`}
              </button>
            )}
          </CardContent>
        </Card>
      )}

      {/* Key Events & Emerging Signals - Collapsed */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Key Events</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-1.5">
              {(data.executiveSummary?.keyEvents || []).slice(0, 4).map((event, i) => (
                <li key={i} className="flex items-start gap-2 text-sm text-gray-700 dark:text-gray-200">
                  <span className="text-pink-500 mt-0.5">•</span>
                  <CitationText text={event} articles={articles} />
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Emerging Signals</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-1.5">
              {(data.executiveSummary?.emergingSignals || []).slice(0, 4).map((signal, i) => (
                <li key={i} className="flex items-start gap-2 text-sm text-gray-700 dark:text-gray-200">
                  <span className="text-blue-500 mt-0.5">→</span>
                  <CitationText text={signal} articles={articles} />
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

// Power View (simplified)
const PowerView: React.FC<{ data: PAMData; articles: Article[]; regulatoryEvents: RegulatoryEvent[]; eventsLoading: boolean }> = ({ data, articles, regulatoryEvents, eventsLoading }) => {
  const power = data.powerAnalysis;
  if (!power) return <EmptyState message="No power analysis available" />;

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Zap className="w-5 h-5 text-yellow-500" />
            Power Flow Analysis
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <AnalysisSection
              title="Infrastructure Control"
              level={power.infrastructureControl?.level}
              score={power.infrastructureControl?.score}
              items={power.infrastructureControl?.developments || power.infrastructureControl?.keyPlayers || power.infrastructureControl?.key_findings}
              badge={power.infrastructureControl?.concentrationLevel || power.infrastructureControl?.trend}
              articles={articles}
            />
            <AnalysisSection
              title="Regulatory Influence"
              level={power.regulatoryInfluence?.level}
              score={power.regulatoryInfluence?.score}
              items={[
                ...(power.regulatoryInfluence?.activeRegulations || power.regulatoryInfluence?.active_regulations || []),
                ...(power.regulatoryInfluence?.keyDevelopments || power.regulatoryInfluence?.key_developments || [])
              ].filter(Boolean)}
              badge={power.regulatoryInfluence?.direction || power.regulatoryInfluence?.trend}
              articles={articles}
            />
            <AnalysisSection
              title="Network Centrality"
              level={power.networkCentrality?.level}
              score={power.networkCentrality?.score}
              items={power.networkCentrality?.influentialEntities || power.networkCentrality?.key_partnerships}
              description={power.networkCentrality?.collaborationTrends || power.networkCentrality?.emerging_alliances?.join(', ')}
              articles={articles}
            />
            <AnalysisSection
              title="IP Positioning"
              level={power.ipPositioning?.level}
              score={power.ipPositioning?.score}
              items={power.ipPositioning?.keyDeals || power.ipPositioning?.licensing_trends}
              description={power.ipPositioning?.trends || power.ipPositioning?.patent_activity}
              articles={articles}
            />
          </div>

          {/* T2: Agentic AI Tools & Adoption */}
          {power.t2Evidence && (power.t2Evidence.toolsMentioned?.length > 0 || power.t2Evidence.adoptionSignals?.length > 0) && (
            <div className="p-4 bg-yellow-50 rounded-lg border border-yellow-200">
              <div className="flex items-center justify-between mb-3">
                <h4 className="font-medium flex items-center gap-2 text-black">
                  <Bot className="w-4 h-4 text-yellow-600" />
                  T2: Agentic AI Adoption
                </h4>
                {power.t2Evidence.trendDirection && (
                  <Badge variant="outline" className="capitalize text-black">
                    {power.t2Evidence.trendDirection}
                  </Badge>
                )}
              </div>

              {/* AI Tools Mentioned */}
              {power.t2Evidence.toolsMentioned && power.t2Evidence.toolsMentioned.length > 0 && (
                <div className="mb-3">
                  <p className="text-xs text-black uppercase mb-1 font-semibold">AI Tools Mentioned in News</p>
                  <div className="flex flex-wrap gap-1">
                    {power.t2Evidence.toolsMentioned.map((tool: string, i: number) => (
                      <Badge key={i} variant="outline" className="bg-white text-black">
                        {tool}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}

              {/* Adoption Signals */}
              {power.t2Evidence.adoptionSignals && power.t2Evidence.adoptionSignals.length > 0 && (
                <div className="mb-3">
                  <p className="text-xs text-black uppercase mb-1 font-semibold">Adoption Signals</p>
                  <ul className="space-y-1">
                    {power.t2Evidence.adoptionSignals.slice(0, 5).map((signal: any, i: number) => (
                      <li key={i} className="text-sm text-black flex items-start gap-1">
                        <span className="text-yellow-600">→</span>
                        <span>
                          <strong>{signal.entity}</strong>: {signal.toolOrChange}
                          {signal.source && (
                            <span className="text-gray-700 ml-1">
                              <CitationText text={signal.source} articles={articles} />
                            </span>
                          )}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Summary */}
              {power.t2Evidence.summary && power.t2Evidence.summary !== 'No T2 evidence found in articles' && (
                <p className="text-sm text-black pt-2 border-t border-yellow-200">
                  <CitationText text={power.t2Evidence.summary} articles={articles} />
                </p>
              )}
            </div>
          )}
          {/* Key Events */}
          {power.keyEvents && power.keyEvents.length > 0 && (
            <div className="p-4 bg-gray-50 rounded-lg">
              <h4 className="font-medium mb-2">Key Power Events</h4>
              <ul className="space-y-2">
                {power.keyEvents.slice(0, 5).map((event: any, i: number) => (
                  <li key={i} className="flex items-start gap-2 text-sm">
                    <span className="text-yellow-500 mt-1">⚡</span>
                    <div className="flex-1">
                      <CitationText text={typeof event === 'string' ? event : event.event} articles={articles} />
                      {typeof event !== 'string' && event.impact && (
                        <Badge
                          variant="outline"
                          className={`ml-2 text-xs ${
                            event.impact === 'high' ? 'border-red-300 text-red-600' :
                            event.impact === 'medium' ? 'border-yellow-300 text-yellow-600' :
                            'border-gray-300 text-gray-600 dark:text-gray-300'
                          }`}
                        >
                          {event.impact} impact
                        </Badge>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {power.summary && (
            <div className="p-4 bg-gray-50 rounded-lg">
              <h4 className="font-medium mb-2">Summary</h4>
              <p className="text-gray-700 dark:text-gray-200">
                <CitationText text={power.summary} articles={articles} />
              </p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Extracted Regulatory Events */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <Scale className="w-5 h-5 text-purple-500" />
            Extracted Regulatory Events
            {regulatoryEvents.length > 0 && (
              <Badge variant="outline" className="ml-2">{regulatoryEvents.length}</Badge>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {eventsLoading ? (
            <div className="flex items-center justify-center py-4">
              <Loader2 className="w-5 h-5 animate-spin text-purple-500" />
              <span className="ml-2 text-sm text-gray-500 dark:text-gray-300">Loading events...</span>
            </div>
          ) : regulatoryEvents.length === 0 ? (
            <p className="text-sm text-gray-400 dark:text-gray-400 italic py-2">No regulatory events extracted yet. Run event extraction from Tune modal.</p>
          ) : (
            <div className="space-y-3">
              {regulatoryEvents.slice(0, 8).map((event) => (
                <div key={event.id} className="p-3 bg-purple-50 rounded-lg border border-purple-100">
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex-1">
                      <h5 className="font-medium text-sm text-black">{event.headline}</h5>
                      <div className="flex items-center gap-2 mt-1 text-xs text-black">
                        <Badge variant="outline" className="text-xs text-black">{event.jurisdiction}</Badge>
                        <Badge variant="outline" className="text-xs capitalize text-black">{event.event_type.replace('_', ' ')}</Badge>
                        {event.event_date && (
                          <span className="flex items-center gap-1">
                            <Calendar className="w-3 h-3" />
                            {event.event_date}
                          </span>
                        )}
                      </div>
                      {event.summary && (
                        <p className="text-xs text-black mt-2">{event.summary}</p>
                      )}
                      {event.publisher_implications && (
                        <p className="text-xs text-purple-800 mt-1">
                          <strong>Publisher impact:</strong> {event.publisher_implications}
                        </p>
                      )}
                    </div>
                    {event.t4_impact_score && (
                      <div className="text-right">
                        <span className="text-lg font-bold text-purple-700">{Math.round(event.t4_impact_score * 100)}</span>
                        <p className="text-xs text-black">impact</p>
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

// Attention View (simplified)
const AttentionView: React.FC<{ data: PAMData; articles: Article[] }> = ({ data, articles }) => {
  const attention = data.attentionAnalysis;
  if (!attention) return <EmptyState message="No attention analysis available" />;

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Eye className="w-5 h-5 text-blue-500" />
            Attention Economy Analysis
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* AI Engine Visibility with qualitative level */}
            {(() => {
              const aiVisLevel = attention.aiVisibility?.level || (attention.aiVisibility?.score != null ? numericToLevel(attention.aiVisibility.score) : null);
              const aiVisConfig = aiVisLevel ? LEVEL_CONFIG[aiVisLevel as QualitativeLevel] : null;
              return (
                <div className="p-4 bg-gray-50 rounded-lg">
                  <div className="flex items-center justify-between mb-2">
                    <h4 className="font-medium">AI Engine Visibility</h4>
                    {aiVisConfig && (
                      <div className="flex items-center gap-1">
                        <span className={`text-lg font-semibold ${aiVisConfig.color}`}>{aiVisConfig.label}</span>
                        <InfoTooltip text={SCORE_EXPLANATIONS.analysis} />
                      </div>
                    )}
                  </div>
                  {aiVisConfig && (
                    <div className="flex gap-1 mb-3">
                      {(['none', 'low', 'medium', 'high', 'very_high'] as QualitativeLevel[]).map((lvl) => {
                        const isActive = ['none', 'low', 'medium', 'high', 'very_high'].indexOf(lvl) <= ['none', 'low', 'medium', 'high', 'very_high'].indexOf(aiVisLevel as QualitativeLevel);
                        return (
                          <div key={lvl} className={`h-2 flex-1 rounded-sm ${isActive ? aiVisConfig.bgColor : 'bg-gray-200'}`} />
                        );
                      })}
                    </div>
                  )}
                  <div className="space-y-2 text-sm">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-1">
                        <span className="text-gray-500 dark:text-gray-300">Training data exposure:</span>
                        <InfoTooltip text={ATTENTION_METRIC_EXPLANATIONS.trainingDataExposure} />
                      </div>
                      <span className="font-medium capitalize">{attention.aiVisibility?.trainingDataExposure || attention.aiVisibility?.training_data_exposure || 'N/A'}</span>
                    </div>
                  </div>
                  {/* Description with citations */}
                  {(attention.aiVisibility?.trainingDataExposureDescription || attention.aiVisibility?.training_data_exposure_description) && (
                    <p className="mt-3 pt-3 border-t border-gray-200 text-sm text-gray-600 dark:text-gray-300">
                      <CitationText text={attention.aiVisibility.trainingDataExposureDescription || attention.aiVisibility.training_data_exposure_description} articles={articles} />
                    </p>
                  )}
                </div>
              );
            })()}
            <AnalysisSection
              title="Brand Visibility"
              level={attention.brandVisibility?.level}
              score={attention.brandVisibility?.score}
              description={attention.brandVisibility?.trafficTrends}
              items={attention.brandVisibility?.keyChannels || attention.brandVisibility?.key_channels}
              badge={attention.brandVisibility?.trend}
              articles={articles}
            />
            {/* Synthesis Exposure with qualitative level */}
            {(() => {
              const synthLevel = attention.synthesisExposure?.level || (attention.synthesisExposure?.score != null ? numericToLevel(attention.synthesisExposure.score) : null);
              const synthConfig = synthLevel ? LEVEL_CONFIG[synthLevel as QualitativeLevel] : null;
              return (
                <div className="p-4 bg-gray-50 rounded-lg">
                  <div className="flex items-center justify-between mb-2">
                    <h4 className="font-medium">Synthesis Exposure</h4>
                    {synthConfig && (
                      <div className="flex items-center gap-1">
                        <span className={`text-lg font-semibold ${synthConfig.color}`}>{synthConfig.label}</span>
                        <InfoTooltip text={ATTENTION_METRIC_EXPLANATIONS.synthesisExposure} />
                      </div>
                    )}
                  </div>
                  {synthConfig && (
                    <div className="flex gap-1 mb-3">
                      {(['none', 'low', 'medium', 'high', 'very_high'] as QualitativeLevel[]).map((lvl) => {
                        const isActive = ['none', 'low', 'medium', 'high', 'very_high'].indexOf(lvl) <= ['none', 'low', 'medium', 'high', 'very_high'].indexOf(synthLevel as QualitativeLevel);
                        return (
                          <div key={lvl} className={`h-2 flex-1 rounded-sm ${isActive ? synthConfig.bgColor : 'bg-gray-200'}`} />
                        );
                      })}
                    </div>
                  )}
                  <div className="space-y-2 text-sm">
                    {(attention.synthesisExposure?.zeroClickRisk || attention.synthesisExposure?.zero_click_risk) && (
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-1">
                          <span className="text-gray-500 dark:text-gray-300">Zero-click risk:</span>
                          <InfoTooltip text={ATTENTION_METRIC_EXPLANATIONS.zeroClickRisk} />
                        </div>
                        <Badge variant="outline" className="capitalize">{attention.synthesisExposure.zeroClickRisk || attention.synthesisExposure.zero_click_risk}</Badge>
                      </div>
                    )}
                    {(attention.synthesisExposure?.attributionQuality || attention.synthesisExposure?.attribution_quality) && (
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-1">
                          <span className="text-gray-500 dark:text-gray-300">Attribution quality:</span>
                          <InfoTooltip text={ATTENTION_METRIC_EXPLANATIONS.attributionRate} />
                        </div>
                        <span className="font-medium capitalize">{attention.synthesisExposure.attributionQuality || attention.synthesisExposure.attribution_quality}</span>
                      </div>
                    )}
                  </div>
                  {/* Description with citations */}
                  {attention.synthesisExposure?.description && (
                    <p className="mt-3 pt-3 border-t border-gray-200 text-sm text-gray-600 dark:text-gray-300">
                      <CitationText text={attention.synthesisExposure.description} articles={articles} />
                    </p>
                  )}
                </div>
              );
            })()}
          </div>
          {/* Key Attention Events */}
          {attention.keyEvents && attention.keyEvents.length > 0 && (
            <div className="p-4 bg-gray-50 rounded-lg">
              <h4 className="font-medium mb-2">Key Attention Events</h4>
              <ul className="space-y-2">
                {attention.keyEvents.slice(0, 5).map((event: any, i: number) => (
                  <li key={i} className="flex items-start gap-2 text-sm">
                    <span className="text-blue-500 mt-1">👁</span>
                    <div className="flex-1">
                      <CitationText text={typeof event === 'string' ? event : event.event} articles={articles} />
                      {typeof event !== 'string' && event.impact && (
                        <Badge
                          variant="outline"
                          className={`ml-2 text-xs ${
                            event.impact === 'high' ? 'border-red-300 text-red-600' :
                            event.impact === 'medium' ? 'border-yellow-300 text-yellow-600' :
                            'border-gray-300 text-gray-600 dark:text-gray-300'
                          }`}
                        >
                          {event.impact} impact
                        </Badge>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {/* Entity Mentions (from monitored brands) */}
          {(attention.entityMentions && attention.entityMentions.length > 0) || attention.entitySearchResults ? (
            <div className="p-4 bg-blue-50 rounded-lg border border-blue-100">
              <h4 className="font-medium mb-3 flex items-center gap-2 text-black">
                <Building2 className="w-4 h-4 text-blue-600" />
                <span className="text-blue-700">Monitored Entity Tracking</span>
              </h4>

              {/* Show entity search results (SQL ground truth) */}
              {attention.entitySearchResults && Object.keys(attention.entitySearchResults).length > 0 && (
                <div className="mb-3 p-2 bg-white rounded border border-blue-100">
                  <p className="text-xs text-black mb-2 font-semibold">Database Search Results:</p>
                  <div className="flex flex-wrap gap-2">
                    {Object.entries(attention.entitySearchResults).map(([entity, count]: [string, any]) => (
                      <Badge key={entity} variant="outline" className={`text-xs text-black ${count > 0 ? 'border-blue-300 bg-blue-50' : 'border-gray-200'}`}>
                        {entity}: {count} article{count !== 1 ? 's' : ''}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}

              {/* Show LLM-analyzed mentions */}
              {attention.entityMentions && attention.entityMentions.length > 0 ? (
                <div className="space-y-3">
                  {attention.entityMentions.map((mention: any, i: number) => (
                    <div key={i} className="flex items-start justify-between p-3 bg-white rounded border border-blue-100">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="font-medium text-black">{mention.entity}</span>
                          <Badge variant="outline" className="text-xs border-blue-300 text-black">
                            {mention.mentionCount || mention.mention_count || 1} mention{(mention.mentionCount || mention.mention_count || 1) !== 1 ? 's' : ''}
                          </Badge>
                          {mention.sentiment && (
                            <Badge
                              variant="outline"
                              className={`text-xs ${
                                mention.sentiment === 'positive' ? 'border-green-300 bg-green-50 text-green-800' :
                                mention.sentiment === 'negative' ? 'border-red-300 bg-red-50 text-red-800' :
                                'border-gray-300 bg-gray-50 text-black'
                              }`}
                            >
                              {mention.sentiment}
                            </Badge>
                          )}
                        </div>
                        {mention.context && (
                          <p className="text-sm text-black mt-2">{mention.context}</p>
                        )}
                        {mention.articles && mention.articles.length > 0 && (
                          <p className="text-xs text-gray-700 mt-1">
                            Found in: {mention.articles.join(', ')}
                          </p>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-black italic">No specific entity mentions extracted from the analyzed articles.</p>
              )}
            </div>
          ) : null}
          {attention.summary && (
            <div className="p-4 bg-gray-50 rounded-lg">
              <h4 className="font-medium mb-2">Summary</h4>
              <p className="text-gray-700 dark:text-gray-200">
                <CitationText text={attention.summary} articles={articles} />
              </p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

// Money View (simplified)
const MoneyView: React.FC<{ data: PAMData; articles: Article[]; financialEvents: FinancialEvent[]; eventsLoading: boolean }> = ({ data, articles, financialEvents, eventsLoading }) => {
  const money = data.moneyAnalysis;
  if (!money) return <EmptyState message="No money analysis available" />;

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <DollarSign className="w-5 h-5 text-green-500" />
            Money Flows Analysis
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Funding Flows - with qualitative level display */}
            <AnalysisSection
              title="Funding Flows"
              level={money.fundingFlows?.level || (money.fundingFlows?.vcActivity === 'increasing' ? 'high' : money.fundingFlows?.vcActivity === 'stable' ? 'medium' : money.fundingFlows?.vcActivity === 'decreasing' ? 'low' : undefined) || (money.fundingFlows?.vc_activity === 'increasing' ? 'high' : money.fundingFlows?.vc_activity === 'stable' ? 'medium' : money.fundingFlows?.vc_activity === 'decreasing' ? 'low' : undefined)}
              badge={money.fundingFlows?.vcActivity || money.fundingFlows?.vc_activity}
              description={money.fundingFlows?.totalEstimatedUsd || money.fundingFlows?.total_estimated_usd}
              items={[
                ...(money.fundingFlows?.keyInvestments || money.fundingFlows?.key_investments || []),
                ...(money.fundingFlows?.governmentFunding ? [`Government: ${money.fundingFlows.governmentFunding}`] : []),
                ...(money.fundingFlows?.government_funding ? [`Government: ${money.fundingFlows.government_funding}`] : [])
              ].filter(Boolean)}
              articles={articles}
            />

            {/* Revenue Concentration - with qualitative level display (fallback: concentrationLevel maps to level) */}
            <AnalysisSection
              title="Revenue Concentration"
              level={money.revenueConcentration?.level || money.revenueConcentration?.concentrationLevel || money.revenueConcentration?.concentration_level}
              badge={money.revenueConcentration?.trend}
              items={money.revenueConcentration?.licensingTrends || money.revenueConcentration?.licensing_trends || []}
              articles={articles}
            />

            {/* M&A Activity - with qualitative level display (fallback: activityLevel/activity_intensity maps to level) */}
            <AnalysisSection
              title="M&A Activity"
              level={money.maActivity?.level || money.maActivity?.activityLevel || money.maActivity?.activity_intensity}
              badge={money.maActivity?.consolidationTrend || money.maActivity?.consolidation_trend}
              items={[
                ...(money.maActivity?.keyDeals || money.maActivity?.key_deals || []),
                ...(money.maActivity?.keyAcquirers?.map((a: string) => `Key acquirer: ${a}`) || money.maActivity?.key_acquirers?.map((a: string) => `Key acquirer: ${a}`) || [])
              ].filter(Boolean)}
              articles={articles}
            />

            {/* Cost Dynamics - with qualitative level display */}
            <AnalysisSection
              title="Cost Dynamics"
              level={money.costDynamics?.level}
              badge={money.costDynamics?.computeCostTrend || money.costDynamics?.compute_cost_trend}
              description={money.costDynamics?.publishingCostTrend ? `Publishing: ${money.costDynamics.publishingCostTrend}` :
                          (money.costDynamics?.publishing_cost_trend ? `Publishing: ${money.costDynamics.publishing_cost_trend}` : undefined)}
              items={money.costDynamics?.keyFindings || money.costDynamics?.key_findings || []}
              articles={articles}
            />
          </div>
          {/* Licensing Trends */}
          {money.licensingTrends && (
            <div className="p-4 bg-gray-50 rounded-lg">
              <h4 className="font-medium mb-2">AI Training & Licensing Trends</h4>
              <div className="grid grid-cols-2 gap-4 mb-3">
                {money.licensingTrends.aiTrainingRightsValue && (
                  <div>
                    <p className="text-lg font-bold text-green-600">{money.licensingTrends.aiTrainingRightsValue}</p>
                    <p className="text-xs text-gray-500 dark:text-gray-300">AI Training Rights Value</p>
                  </div>
                )}
                {money.licensingTrends.growthRate && (
                  <div>
                    <p className="text-lg font-bold text-blue-600">{money.licensingTrends.growthRate}</p>
                    <p className="text-xs text-gray-500 dark:text-gray-300">Annual Growth Rate</p>
                  </div>
                )}
              </div>
              {money.licensingTrends.keyDeals && money.licensingTrends.keyDeals.length > 0 && (
                <ul className="space-y-1">
                  {money.licensingTrends.keyDeals.slice(0, 3).map((deal: any, i: number) => (
                    <li key={i} className="text-sm text-gray-600 dark:text-gray-300">
                      • <CitationText text={typeof deal === 'string' ? deal : deal.deal} articles={articles} />
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
          {/* Key Financial Events with citations */}
          {money.keyEvents && money.keyEvents.length > 0 && (
            <div className="p-4 bg-gray-50 rounded-lg">
              <h4 className="font-medium mb-2">Key Financial Events</h4>
              <ul className="space-y-2">
                {money.keyEvents.slice(0, 5).map((event: any, i: number) => (
                  <li key={i} className="flex items-start gap-2 text-sm">
                    <span className="text-green-500 mt-1">$</span>
                    <div className="flex-1">
                      <CitationText
                        text={typeof event === 'string' ? event : event.event}
                        articles={articles}
                      />
                      {typeof event !== 'string' && event.value && (
                        <span className="text-green-600 ml-1">({event.value})</span>
                      )}
                      {typeof event !== 'string' && event.impact && (
                        <Badge
                          variant="outline"
                          className={`ml-1 text-xs ${
                            event.impact === 'high' ? 'border-red-300 text-red-600' :
                            event.impact === 'medium' ? 'border-yellow-300 text-yellow-600' :
                            'border-gray-300 text-gray-600 dark:text-gray-300'
                          }`}
                        >
                          {event.impact}
                        </Badge>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {money.summary && (
            <div className="p-4 bg-gray-50 rounded-lg">
              <h4 className="font-medium mb-2">Summary</h4>
              <p className="text-gray-700 dark:text-gray-200">
                <CitationText text={money.summary} articles={articles} />
              </p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Extracted Financial Events */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <Briefcase className="w-5 h-5 text-emerald-500" />
            Extracted M&A & Funding Events
            {financialEvents.length > 0 && (
              <Badge variant="outline" className="ml-2">{financialEvents.length}</Badge>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {eventsLoading ? (
            <div className="flex items-center justify-center py-4">
              <Loader2 className="w-5 h-5 animate-spin text-emerald-500" />
              <span className="ml-2 text-sm text-gray-500 dark:text-gray-300">Loading events...</span>
            </div>
          ) : financialEvents.length === 0 ? (
            <p className="text-sm text-gray-400 dark:text-gray-400 italic py-2">No financial events extracted yet. Run event extraction from Tune modal.</p>
          ) : (
            <div className="space-y-3">
              {financialEvents.slice(0, 10).map((event) => (
                <div key={event.id} className="p-3 bg-emerald-50 rounded-lg border border-emerald-100">
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex-1">
                      <h5 className="font-medium text-sm text-black">{event.headline}</h5>
                      <div className="flex items-center gap-2 mt-1 text-xs text-black">
                        <Badge
                          variant="outline"
                          className={`text-xs capitalize ${
                            event.event_type === 'acquisition' ? 'border-red-200 bg-red-50 text-red-800' :
                            event.event_type === 'funding_round' ? 'border-blue-200 bg-blue-50 text-blue-800' :
                            event.event_type === 'partnership' ? 'border-purple-200 bg-purple-50 text-purple-800' :
                            event.event_type === 'merger' ? 'border-orange-200 bg-orange-50 text-orange-800' :
                            'border-gray-200 text-black'
                          }`}
                        >
                          {event.event_type.replace('_', ' ')}
                        </Badge>
                        {event.event_date && (
                          <span className="flex items-center gap-1">
                            <Calendar className="w-3 h-3" />
                            {event.event_date}
                          </span>
                        )}
                      </div>
                      {(event.acquirer || event.target) && (
                        <p className="text-xs text-black mt-1">
                          <span className="font-medium">{event.acquirer || 'Unknown'}</span>
                          <span className="text-gray-700 mx-1">→</span>
                          <span className="font-medium">{event.target || 'Unknown'}</span>
                        </p>
                      )}
                      {event.strategic_significance && (
                        <p className="text-xs text-emerald-800 mt-1">
                          <strong>Significance:</strong> {event.strategic_significance}
                        </p>
                      )}
                    </div>
                    {event.deal_value_usd && (
                      <div className="text-right">
                        <span className="text-lg font-bold text-emerald-700">
                          {formatCurrency(event.deal_value_usd)}
                        </span>
                        <p className="text-xs text-black">deal value</p>
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

// Scenarios View (enhanced)
const ScenariosView: React.FC<{ data: PAMData; articles: Article[] }> = ({ data, articles }) => {
  const scenarios = data.scenarioAnalysis;
  if (!scenarios) return <EmptyState message="No scenario analysis available" />;

  // Use camelCase IDs since transformKeys converts all keys
  const scenarioList = [
    {
      id: 'trustedEcosystem',
      name: 'Trusted Ecosystem',
      desc: 'Publishers as trusted custodians of verified knowledge',
      longDesc: 'Strong regulatory frameworks ensure attribution and provenance. Publishers thrive as trust intermediaries. Diverse ecosystem with multiple viable players.',
      color: 'bg-green-100 border-green-300',
      icon: '🛡️',
      quadrant: 'High Regulation / Low Concentration'
    },
    {
      id: 'fragmentedCompliance',
      name: 'Fragmented Compliance',
      desc: 'Multiple standards, regional silos, compliance burden',
      longDesc: 'Heavy but fragmented regulation creates compliance complexity. Large players dominate due to compliance costs. Regional silos limit global reach.',
      color: 'bg-yellow-100 border-yellow-300',
      icon: '🧩',
      quadrant: 'High Regulation / High Concentration'
    },
    {
      id: 'openChaos',
      name: 'Open Chaos',
      desc: 'Wild west AI, no attribution, trust erosion',
      longDesc: 'Minimal regulation allows unrestricted AI use. Content is freely scraped without attribution. Trust erodes but innovation flourishes chaotically.',
      color: 'bg-gray-100 border-gray-300',
      icon: '🌪️',
      quadrant: 'Low Regulation / Low Concentration'
    },
    {
      id: 'behemothControl',
      name: 'Behemoth Control',
      desc: '3-5 giants own everything, publishers commoditized',
      longDesc: 'A few tech giants control AI infrastructure and content distribution. Publishers become commoditized content suppliers. Winner-take-all dynamics prevail.',
      color: 'bg-red-100 border-red-300',
      icon: '🏢',
      quadrant: 'Low Regulation / High Concentration'
    },
  ];

  // Get key variables
  const regulationStrength = scenarios.keyVariables?.regulationStrength || 50;
  const consolidationStrength = scenarios.keyVariables?.consolidationStrength || 50;

  // Determine most likely scenario
  const mostLikelyNormalized = scenarios.mostLikely?.replace(/_([a-z])/g, (_, l: string) => l.toUpperCase());

  return (
    <div className="space-y-6">
      {/* Key Variables */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <BarChart3 className="w-5 h-5 text-purple-500" />
            Scenario Drivers
            <InfoTooltip text="The two key variables that determine which 2030 scenario is most likely. Based on current PAM analysis." />
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium">Regulation Strength</span>
                <span className="text-lg font-bold">{regulationStrength.toFixed(0)}%</span>
              </div>
              <Progress value={regulationStrength} className="h-3" />
              <div className="flex justify-between text-xs text-gray-500 dark:text-gray-300 mt-1">
                <span>Minimal oversight</span>
                <span>Heavy regulation</span>
              </div>
            </div>
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium">Market Consolidation</span>
                <span className="text-lg font-bold">{consolidationStrength.toFixed(0)}%</span>
              </div>
              <Progress value={consolidationStrength} className="h-3" />
              <div className="flex justify-between text-xs text-gray-500 dark:text-gray-300 mt-1">
                <span>Distributed market</span>
                <span>Concentrated power</span>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Scenario Matrix */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Target className="w-5 h-5 text-purple-500" />
            2030 Scenario Matrix
            <InfoTooltip text="Four possible 2030 futures based on regulation strength and market consolidation. Current trajectory points toward the highlighted scenario." />
          </CardTitle>
        </CardHeader>
        <CardContent>
          {/* 2x2 Matrix Visualization */}
          <div className="mb-6">
            <div className="relative">
              {/* Axis labels */}
              <div className="absolute -left-2 top-1/2 -translate-y-1/2 -rotate-90 text-xs text-gray-500 dark:text-gray-300 whitespace-nowrap">
                ← Low Regulation | High Regulation →
              </div>
              <div className="absolute bottom-0 left-1/2 -translate-x-1/2 text-xs text-gray-500 dark:text-gray-300">
                ← Distributed | Concentrated →
              </div>

              {/* Matrix grid */}
              <div className="grid grid-cols-2 gap-2 ml-6 mb-6">
                {/* Top row: High Regulation */}
                {scenarioList.filter(s => s.quadrant.includes('High Regulation')).map(s => {
                  const scenarioData = scenarios.scenarios?.[s.id];
                  const isMostLikely = mostLikelyNormalized === s.id;
                  const probability = scenarioData?.currentProbability
                    ? scenarioData.currentProbability.toFixed(0)
                    : '--';

                  return (
                    <div
                      key={s.id}
                      className={`p-4 rounded-lg border-2 transition-all ${s.color} ${isMostLikely ? 'ring-2 ring-pink-500 shadow-lg scale-[1.02]' : 'opacity-80'}`}
                    >
                      <div className="flex items-start justify-between mb-2">
                        <div className="flex items-center gap-2">
                          <span className="text-2xl">{s.icon}</span>
                          <div>
                            <h4 className="font-semibold text-sm text-black">{s.name}</h4>
                            <p className="text-xs text-black">{s.quadrant}</p>
                          </div>
                        </div>
                        {isMostLikely && <Badge className="bg-pink-500 text-xs">Most Likely</Badge>}
                      </div>
                      <p className="text-xs text-black mb-3">{s.longDesc}</p>
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-1">
                          <span className="text-2xl font-bold text-black">{probability}%</span>
                          <InfoTooltip text={SCENARIO_EXPLANATIONS.probability} />
                        </div>
                        <div className="text-right text-xs">
                          <p className="text-black">Regulation: <span className="font-medium capitalize text-black">{scenarioData?.regulationLevel || 'N/A'}</span></p>
                          <p className="text-black">Concentration: <span className="font-medium capitalize text-black">{scenarioData?.concentrationLevel || 'N/A'}</span></p>
                        </div>
                      </div>
                    </div>
                  );
                })}
                {/* Bottom row: Low Regulation */}
                {scenarioList.filter(s => s.quadrant.includes('Low Regulation')).map(s => {
                  const scenarioData = scenarios.scenarios?.[s.id];
                  const isMostLikely = mostLikelyNormalized === s.id;
                  const probability = scenarioData?.currentProbability
                    ? scenarioData.currentProbability.toFixed(0)
                    : '--';

                  return (
                    <div
                      key={s.id}
                      className={`p-4 rounded-lg border-2 transition-all ${s.color} ${isMostLikely ? 'ring-2 ring-pink-500 shadow-lg scale-[1.02]' : 'opacity-80'}`}
                    >
                      <div className="flex items-start justify-between mb-2">
                        <div className="flex items-center gap-2">
                          <span className="text-2xl">{s.icon}</span>
                          <div>
                            <h4 className="font-semibold text-sm text-black">{s.name}</h4>
                            <p className="text-xs text-black">{s.quadrant}</p>
                          </div>
                        </div>
                        {isMostLikely && <Badge className="bg-pink-500 text-xs">Most Likely</Badge>}
                      </div>
                      <p className="text-xs text-black mb-3">{s.longDesc}</p>
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-1">
                          <span className="text-2xl font-bold text-black">{probability}%</span>
                          <InfoTooltip text={SCENARIO_EXPLANATIONS.probability} />
                        </div>
                        <div className="text-right text-xs">
                          <p className="text-black">Regulation: <span className="font-medium capitalize text-black">{scenarioData?.regulationLevel || 'N/A'}</span></p>
                          <p className="text-black">Concentration: <span className="font-medium capitalize text-black">{scenarioData?.concentrationLevel || 'N/A'}</span></p>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>

          {/* Current Trajectory */}
          {scenarios.currentTrajectory && (
            <div className="p-4 bg-purple-50 rounded-lg border border-purple-200">
              <h4 className="font-medium mb-2 flex items-center gap-2 text-black">
                <TrendingUp className="w-4 h-4 text-purple-600" />
                Current Trajectory
              </h4>
              <p className="text-black">
                <CitationText text={scenarios.currentTrajectory} articles={articles} />
              </p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Strategic Implications */}
      <Card>
        <CardHeader>
          <CardTitle>Strategic Implications by Scenario</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {scenarioList.map(s => {
              const isMostLikely = mostLikelyNormalized === s.id;
              return (
                <div key={s.id} className={`p-3 rounded-lg border-2 ${s.color} ${isMostLikely ? 'ring-2 ring-pink-500' : ''}`}>
                  <div className="flex items-center gap-2 mb-2">
                    <span>{s.icon}</span>
                    <h5 className="font-medium text-black">{s.name}</h5>
                    {isMostLikely && <Badge className="bg-pink-500 text-xs">Focus Here</Badge>}
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-sm">
                    <div>
                      <p className="text-black text-xs uppercase mb-1 font-semibold">Key Actions</p>
                      <p className="text-black">
                        {s.id === 'trustedEcosystem' && 'Invest in provenance tech, build trust signals, diversify partnerships'}
                        {s.id === 'fragmentedCompliance' && 'Build compliance infrastructure, seek regional partnerships, automate reporting'}
                        {s.id === 'openChaos' && 'Focus on speed and reach, build direct audience relationships, embrace remix culture'}
                        {s.id === 'behemothControl' && 'Partner with platforms early, optimize for AI discovery, protect core IP'}
                      </p>
                    </div>
                    <div>
                      <p className="text-black text-xs uppercase mb-1 font-semibold">Risks</p>
                      <p className="text-black">
                        {s.id === 'trustedEcosystem' && 'Compliance costs, slower innovation, regulatory capture'}
                        {s.id === 'fragmentedCompliance' && 'Market fragmentation, high overhead, regional lock-in'}
                        {s.id === 'openChaos' && 'Revenue erosion, attribution loss, quality degradation'}
                        {s.id === 'behemothControl' && 'Commoditization, margin compression, dependency risk'}
                      </p>
                    </div>
                    <div>
                      <p className="text-black text-xs uppercase mb-1 font-semibold">Opportunities</p>
                      <p className="text-black">
                        {s.id === 'trustedEcosystem' && 'Premium positioning, licensing revenue, validator role'}
                        {s.id === 'fragmentedCompliance' && 'Compliance-as-service, regional expertise, B2B tools'}
                        {s.id === 'openChaos' && 'Viral reach, community building, new formats'}
                        {s.id === 'behemothControl' && 'Platform integration, scale economics, data partnerships'}
                      </p>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

// Helper component for rendering text with clickable citations
const CitationText: React.FC<{
  text: string;
  articles: Article[];
  className?: string;
}> = ({ text, articles, className = '' }) => {
  if (!text) return null;
  const htmlContent = renderCitationsAsLinks(text, articles);
  return (
    <span
      className={className}
      dangerouslySetInnerHTML={{ __html: htmlContent }}
    />
  );
};

// Helper components
const AnalysisSection: React.FC<{
  title: string;
  score?: number;
  level?: string;  // New: qualitative level (none, low, medium, high, very_high)
  items?: string[];
  description?: string;
  badge?: string;
  articles?: Article[];
}> = ({ title, score, level, items, description, badge, articles = [] }) => {
  const hasContent = description || (items && items.length > 0);

  // Prefer qualitative level if provided, otherwise fall back to numeric
  const effectiveLevel: QualitativeLevel | null = level
    ? (level as QualitativeLevel)
    : (score != null ? numericToLevel(score) : null);

  const levelConfig = effectiveLevel ? LEVEL_CONFIG[effectiveLevel] : null;

  return (
    <div className="p-4 bg-gray-50 rounded-lg">
      <div className="flex items-center justify-between mb-2">
        <h4 className="font-medium">{title}</h4>
        {effectiveLevel && levelConfig && (
          <div className="flex items-center gap-1">
            <span className={`text-lg font-semibold ${levelConfig.color}`}>{levelConfig.label}</span>
            <InfoTooltip text={SCORE_EXPLANATIONS.analysis} />
          </div>
        )}
      </div>
      {/* Level indicator bar for qualitative display */}
      {effectiveLevel && levelConfig && (
        <div className="flex gap-1 mb-2">
          {(['none', 'low', 'medium', 'high', 'very_high'] as QualitativeLevel[]).map((lvl) => {
            const isActive = ['none', 'low', 'medium', 'high', 'very_high'].indexOf(lvl) <= ['none', 'low', 'medium', 'high', 'very_high'].indexOf(effectiveLevel);
            return (
              <div
                key={lvl}
                className={`h-2 flex-1 rounded-sm ${isActive ? levelConfig.bgColor : 'bg-gray-200'}`}
              />
            );
          })}
        </div>
      )}
      {badge && (
        <Badge variant="outline" className="mb-2 capitalize">{badge}</Badge>
      )}
      {description && (
        <p className="text-sm text-gray-600 dark:text-gray-300">
          <CitationText text={description} articles={articles} />
        </p>
      )}
      {items && items.length > 0 && (
        <ul className="mt-2 space-y-1">
          {items.slice(0, 5).map((item, i) => (
            <li key={i} className="text-sm text-gray-600 dark:text-gray-300">
              • <CitationText text={item} articles={articles} />
            </li>
          ))}
        </ul>
      )}
      {!hasContent && (
        <p className="text-sm text-gray-400 dark:text-gray-400 italic mt-2">No specific data found in analyzed articles</p>
      )}
    </div>
  );
};

const EmptyState: React.FC<{ message: string }> = ({ message }) => (
  <div className="text-center py-12 text-gray-500 dark:text-gray-300">
    <BarChart3 className="w-12 h-12 mx-auto mb-4 opacity-50" />
    <p>{message}</p>
  </div>
);

// References Section component - collapsed shows just title, expanded shows all articles
const ReferencesSection: React.FC<{ articles: ReferenceArticle[] }> = ({ articles }) => {
  const [isExpanded, setIsExpanded] = useState(false);

  if (!articles || articles.length === 0) {
    return null;
  }

  return (
    <Card className="mt-6">
      <CardHeader
        className="pb-3 cursor-pointer hover:bg-gray-50 transition-colors"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <CardTitle className="flex items-center justify-between text-base">
          <div className="flex items-center gap-2">
            <BookOpen className="w-5 h-5 text-pink-500" />
            References ({articles.length} articles analyzed)
          </div>
          <button className="flex items-center gap-1 text-sm text-pink-600 hover:text-pink-700">
            {isExpanded ? (
              <>
                <ChevronUp className="w-4 h-4" />
                <span className="hidden sm:inline">Collapse</span>
              </>
            ) : (
              <>
                <ChevronDown className="w-4 h-4" />
                <span className="hidden sm:inline">Expand</span>
              </>
            )}
          </button>
        </CardTitle>
      </CardHeader>
      {isExpanded && (
        <CardContent>
          <div className="space-y-3">
            {articles.map((article, idx) => (
              <div key={article.uri || idx} className="flex items-start gap-3 p-2 rounded hover:bg-gray-50">
                <span className="text-xs text-gray-400 dark:text-gray-400 mt-1 w-6">{idx + 1}.</span>
                <div className="flex-1 min-w-0">
                  <a
                    href={article.uri}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm font-medium text-gray-900 dark:text-gray-100 hover:text-pink-600 flex items-center gap-1"
                  >
                    <span className="truncate">{article.title}</span>
                    <ExternalLink className="w-3 h-3 flex-shrink-0" />
                  </a>
                  <div className="flex items-center gap-2 mt-0.5">
                    <span className="text-xs text-gray-500 dark:text-gray-300">{article.source}</span>
                    {article.publicationDate && (
                      <>
                        <span className="text-gray-300">•</span>
                        <span className="text-xs text-gray-500 dark:text-gray-300">
                          {new Date(article.publicationDate).toLocaleDateString()}
                        </span>
                      </>
                    )}
                    {article.matchedTrend && article.matchedTrend !== 'database' && article.matchedTrend !== 'general' && (
                      <>
                        <span className="text-gray-300">•</span>
                        <Badge variant="outline" className="text-xs px-1 py-0 h-4">
                          {article.matchedTrend}
                        </Badge>
                      </>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      )}
    </Card>
  );
};

// AI Disclaimer component
const AIDisclaimer: React.FC<{ modelUsed: string }> = ({ modelUsed }) => {
  return (
    <div className="mt-8 p-4 bg-amber-50 border border-amber-200 rounded-lg">
      <div className="flex items-start gap-3">
        <Info className="w-5 h-5 text-amber-600 mt-0.5 flex-shrink-0" />
        <div className="text-sm text-amber-800">
          <p className="font-medium mb-1">AI-Generated Analysis Disclaimer</p>
          <p className="text-amber-700">
            This analysis was generated using <strong>{modelUsed || 'AI'}</strong> based on the referenced articles.
            AI-generated content may contain inaccuracies, biases, or outdated information.
            This analysis is intended for informational purposes only and should not be the sole basis for
            strategic decisions. Always verify critical information with primary sources and consult
            domain experts before taking action.
          </p>
        </div>
      </div>
    </div>
  );
};

// View tabs component
const ViewTabs: React.FC<{
  activeView: string;
  onViewChange: (view: any) => void;
}> = ({ activeView, onViewChange }) => {
  const views = [
    { id: 'executive', label: 'Executive', icon: BarChart3 },
    { id: 'power', label: 'Power', icon: Zap },
    { id: 'attention', label: 'Attention', icon: Eye },
    { id: 'money', label: 'Money', icon: DollarSign },
    { id: 'scenarios', label: 'Scenarios', icon: Target },
  ];

  return (
    <div className="flex gap-2 mb-6 border-b pb-4">
      {views.map(view => {
        const Icon = view.icon;
        return (
          <button
            key={view.id}
            onClick={() => onViewChange(view.id)}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg transition-colors ${
              activeView === view.id
                ? 'bg-pink-500 text-white'
                : 'bg-gray-100 text-gray-700 dark:text-gray-200 hover:bg-gray-200'
            }`}
          >
            <Icon className="w-4 h-4" />
            <span>{view.label}</span>
          </button>
        );
      })}
    </div>
  );
};

// Main Dashboard Component
export const PAMDashboard: React.FC<PAMDashboardProps> = ({
  topic,
  isGenerating,
  currentStage,
  stageProgress,
  data,
  error,
  activeView,
  onViewChange,
  onClearError,
}) => {
  // State for extracted events
  const [financialEvents, setFinancialEvents] = useState<FinancialEvent[]>([]);
  const [regulatoryEvents, setRegulatoryEvents] = useState<RegulatoryEvent[]>([]);
  const [eventsLoading, setEventsLoading] = useState(false);

  // Fetch extracted events on mount and when data changes
  useEffect(() => {
    const fetchEvents = async () => {
      setEventsLoading(true);
      try {
        const [finRes, regRes] = await Promise.all([
          fetch('/api/pam/events/financial?days_back=90&limit=20', { credentials: 'include' }),
          fetch('/api/pam/events/regulatory?days_back=90&limit=15', { credentials: 'include' }),
        ]);

        if (finRes.ok) {
          const finData = await finRes.json();
          setFinancialEvents(finData.data?.events || []);
        }
        if (regRes.ok) {
          const regData = await regRes.json();
          setRegulatoryEvents(regData.data?.events || []);
        }
      } catch (err) {
        console.error('Failed to fetch extracted events:', err);
      } finally {
        setEventsLoading(false);
      }
    };

    fetchEvents();
  }, [data]); // Refetch when data changes

  // Convert reference articles to Article format for citation renderer
  // IMPORTANT: This must be called before any early returns to keep hook count stable
  const citationArticles: Article[] = useMemo(() => {
    return (data?.referenceArticles || []).map(article => ({
      id: article.id,
      url: article.uri,
      uri: article.uri,
      title: article.title,
      source: article.source,
    }));
  }, [data?.referenceArticles]);

  // Error state
  if (error) {
    return (
      <div className="p-6">
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription className="flex items-center justify-between">
            <span>{error}</span>
            <button onClick={onClearError} className="text-sm underline">Dismiss</button>
          </AlertDescription>
        </Alert>
      </div>
    );
  }

  // Generating state
  if (isGenerating) {
    return (
      <div className="p-6">
        <Card>
          <CardContent className="pt-6">
            <StageIndicator
              stages={PAM_STAGES}
              currentStage={currentStage}
              stageProgress={stageProgress}
            />
            <div className="text-center py-8">
              <Loader2 className="w-12 h-12 mx-auto mb-4 animate-spin text-pink-500" />
              <p className="text-gray-600 dark:text-gray-300">
                Analyzing power, attention, and money flows across all topics...
              </p>
              <Progress value={stageProgress} className="mt-4 max-w-md mx-auto" />
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  // No data yet - prompt to generate
  if (!data) {
    return (
      <div className="p-6">
        <Card>
          <CardContent className="pt-6 text-center py-12">
            <BarChart3 className="w-16 h-16 mx-auto mb-4 text-pink-300" />
            <h2 className="text-2xl font-semibold text-gray-900 dark:text-gray-100 mb-2">
              Power, Attention & Money Dashboard
            </h2>
            <p className="text-gray-600 dark:text-gray-300 mb-6 max-w-lg mx-auto">
              Strategic intelligence tracking the three fundamental flows reshaping the knowledge economy.
              Analyzes articles across <strong>all topics</strong> using trend-specific semantic queries.
            </p>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 max-w-2xl mx-auto text-left mb-6">
              <div className="p-4 bg-yellow-50 rounded-lg">
                <Zap className="w-6 h-6 text-yellow-600 mb-2" />
                <h3 className="font-medium text-black">Power</h3>
                <p className="text-sm text-black">Infrastructure control, regulatory influence, network centrality</p>
              </div>
              <div className="p-4 bg-blue-50 rounded-lg">
                <Eye className="w-6 h-6 text-blue-600 mb-2" />
                <h3 className="font-medium text-black">Attention</h3>
                <p className="text-sm text-black">AI visibility, brand recognition, citation exposure</p>
              </div>
              <div className="p-4 bg-green-50 rounded-lg">
                <DollarSign className="w-6 h-6 text-green-600 mb-2" />
                <h3 className="font-medium text-black">Money</h3>
                <p className="text-sm text-black">Funding flows, M&A activity, market consolidation</p>
              </div>
            </div>
            <p className="text-gray-500 dark:text-gray-300 text-sm">
              Click <strong>Refresh</strong> above to run cross-topic PAM analysis. Use <strong>Tune</strong> to configure trends and time horizon.
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  // Data available - show dashboard
  return (
    <div className="p-6">
      <ViewTabs activeView={activeView} onViewChange={onViewChange} />

      {activeView === 'executive' && <ExecutiveOverview data={data} articles={citationArticles} onViewChange={onViewChange} />}
      {activeView === 'power' && <PowerView data={data} articles={citationArticles} regulatoryEvents={regulatoryEvents} eventsLoading={eventsLoading} />}
      {activeView === 'attention' && <AttentionView data={data} articles={citationArticles} />}
      {activeView === 'money' && <MoneyView data={data} articles={citationArticles} financialEvents={financialEvents} eventsLoading={eventsLoading} />}
      {activeView === 'scenarios' && <ScenariosView data={data} articles={citationArticles} />}

      {/* Footer with metadata */}
      <div className="mt-6 pt-4 border-t flex items-center justify-between text-sm text-gray-500 dark:text-gray-300">
        <span>Analyzed {data.articlesAnalyzed} articles</span>
        <span>Model: {data.modelUsed}</span>
        <span>Generated: {new Date(data.createdAt).toLocaleString()}</span>
      </div>

      {/* v2 Config Used indicator */}
      <ConfigUsedIndicator
        config={data.configUsed}
        architectureVersion={data.architectureVersion}
      />

      {/* Data Sources Summary for v2 */}
      {data.scores?.dataSources && (
        <div className="mt-4 p-3 bg-gray-100 dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
          <h4 className="text-sm font-medium mb-2 flex items-center gap-2">
            <Database className="w-4 h-4 text-gray-600 dark:text-gray-300" />
            Data Sources Used
          </h4>
          <div className="grid grid-cols-3 gap-4 text-xs">
            <div>
              <span className="text-gray-700 dark:text-gray-300 flex items-center gap-1 font-medium">
                <Zap className="w-3 h-3" /> Power:
              </span>
              <div className="flex flex-wrap gap-1 mt-1">
                {data.scores.dataSources.power && data.scores.dataSources.power.length > 0 ? (
                  data.scores.dataSources.power.map((s: string, i: number) => (
                    <DataSourceBadge key={i} source={s as DataSourceType} />
                  ))
                ) : (
                  <span className="text-gray-600 dark:text-gray-400 italic">Article database</span>
                )}
              </div>
            </div>
            <div>
              <span className="text-gray-700 dark:text-gray-300 flex items-center gap-1 font-medium">
                <Eye className="w-3 h-3" /> Attention:
              </span>
              <div className="flex flex-wrap gap-1 mt-1">
                {data.scores.dataSources.attention && data.scores.dataSources.attention.length > 0 ? (
                  data.scores.dataSources.attention.map((s: string, i: number) => (
                    <DataSourceBadge key={i} source={s as DataSourceType} />
                  ))
                ) : (
                  <span className="text-gray-600 dark:text-gray-400 italic">Article database</span>
                )}
              </div>
            </div>
            <div>
              <span className="text-gray-700 dark:text-gray-300 flex items-center gap-1 font-medium">
                <DollarSign className="w-3 h-3" /> Money:
              </span>
              <div className="flex flex-wrap gap-1 mt-1">
                {data.scores.dataSources.money && data.scores.dataSources.money.length > 0 ? (
                  data.scores.dataSources.money.map((s: string, i: number) => (
                    <DataSourceBadge key={i} source={s as DataSourceType} />
                  ))
                ) : (
                  <span className="text-gray-600 dark:text-gray-400 italic">Article database</span>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* AI Disclaimer */}
      <AIDisclaimer modelUsed={data.modelUsed} />

      {/* References section at bottom - collapsed by default */}
      {data.referenceArticles && data.referenceArticles.length > 0 && (
        <ReferencesSection articles={data.referenceArticles} />
      )}
    </div>
  );
};

export default PAMDashboard;
