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

import React, { useState, useMemo } from 'react';
import { Loader2, AlertCircle, BarChart3, Zap, Eye, DollarSign, Target, TrendingUp, TrendingDown, Minus, BookOpen, ExternalLink, ChevronDown, ChevronUp, Info, HelpCircle } from 'lucide-react';
import { Alert, AlertDescription } from '../ui/alert';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Progress } from '../ui/progress';
import { Badge } from '../ui/badge';
import { Tooltip, TooltipContent, TooltipTrigger } from '../ui/tooltip';
import type { PAMData, TrendStatus, ReferenceArticle } from '../../hooks/usePAM';
import { renderCitationsAsLinks, Article } from '../../utils/citationRenderer';
import '../../styles/citations.css';

// Score explanations
const SCORE_EXPLANATIONS = {
  power: "Power Index measures infrastructure control, regulatory influence, network centrality, and IP positioning. Higher scores indicate greater concentration of power in the knowledge economy.",
  attention: "Attention Index measures AI visibility, brand recognition, citation exposure, and GEO readiness. Higher scores indicate greater risk of attention being diverted away from traditional channels.",
  money: "Money Flow tracks funding patterns, M&A activity, revenue concentration, and cost dynamics. Higher scores indicate greater financial disruption or consolidation.",
  overall: "Overall threat assessment combining all PAM dimensions. 0-39: Low, 40-54: Moderate, 55-69: Elevated, 70-79: High, 80+: Critical.",
  trend: "Trend score indicates the current intensity and momentum of this trend based on recent article coverage. Higher scores mean the trend is more prominent in current news.",
  analysis: "Score from 0-100 indicating the strength or risk level of this dimension. Higher scores generally indicate greater disruption potential or market concentration.",
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

const SCENARIO_EXPLANATIONS = {
  probability: "Probability percentage indicates how likely this scenario is based on current trend analysis. Derived from PAM scores and trend velocities.",
  mostLikely: "The 'Most Likely' scenario is determined by analyzing current power structures, attention flows, and money movements. It represents the trajectory we're most likely heading toward if current trends continue.",
};

// Metric explanations for Attention pillar
const ATTENTION_METRIC_EXPLANATIONS = {
  trainingDataExposure: "Training Data Exposure indicates how likely your content is to be included in AI model training datasets. Low = rarely used, Medium = sometimes used, High = frequently scraped for AI training.",
  metadataReadiness: "Metadata Readiness measures how well-structured your content metadata is for AI consumption (0-100). Higher scores indicate better machine-readable metadata.",
  provenanceStrength: "Provenance Strength measures how well your content maintains attribution chains and origin verification (0-100). Important for trust and regulatory compliance.",
  synthesisExposure: "Synthesis Exposure measures how often your content appears in AI-generated summaries and answers without proper attribution.",
  zeroClickRisk: "Zero-Click Risk indicates how often users get answers from AI without visiting your site. Low = users still visit, High = answers synthesized without clicks.",
  attributionRate: "Attribution Rate shows how often AI systems credit your content when using it (0-100). Higher is better for brand visibility.",
};

// Metric explanations for Money pillar
const MONEY_METRIC_EXPLANATIONS = {
  maActivity: "M&A Activity Level indicates the intensity of mergers, acquisitions, and consolidation in the sector. Derived from recent deal announcements and market signals.",
  consolidationTrend: "Consolidation Trend shows whether market concentration is accelerating (more deals), stable, or slowing (fewer deals).",
  vcActivity: "VC Activity tracks venture capital investment trends in the knowledge economy. Increasing = more funding flowing in.",
  governmentFunding: "Government Funding tracks public research grants and subsidies. Increasing = more policy support for the sector.",
};

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
              'bg-gray-100 text-gray-500'
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
      <button type="button" className={`inline-flex items-center text-gray-400 hover:text-gray-600 ${className}`}>
        <HelpCircle className="w-4 h-4" />
      </button>
    </TooltipTrigger>
    <TooltipContent className="max-w-xs bg-gray-900 text-white text-xs p-2">
      {text}
    </TooltipContent>
  </Tooltip>
);

// Score Card component
const ScoreCard: React.FC<{
  label: string;
  score: number;
  icon: React.ReactNode;
  color: string;
  explanation?: string;
}> = ({ label, score, icon, color, explanation }) => {
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
              <p className="text-sm text-gray-500">{label}</p>
              {explanation && <InfoTooltip text={explanation} />}
            </div>
          </div>
        </div>
        <Progress value={score} className="mt-3 h-2" />
      </CardContent>
    </Card>
  );
};

// Trend item component with expandable details
const TrendItem: React.FC<{ trend: TrendStatus; articles?: Article[] }> = ({ trend, articles = [] }) => {
  const [isExpanded, setIsExpanded] = useState(false);

  const getVelocityIcon = (velocity: string) => {
    switch (velocity) {
      case 'accelerating': return <TrendingUp className="w-4 h-4 text-red-500" />;
      case 'decelerating': return <TrendingDown className="w-4 h-4 text-green-500" />;
      default: return <Minus className="w-4 h-4 text-gray-400" />;
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
            <span className="font-medium text-gray-900">{trend.name}</span>
          </div>
          <div className="flex items-center gap-2">
            {getVelocityIcon(trend.velocity)}
            <span className="text-sm font-semibold">{trend.score}%</span>
            {isExpanded ? <ChevronUp className="w-4 h-4 text-gray-400" /> : <ChevronDown className="w-4 h-4 text-gray-400" />}
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
              <h5 className="text-xs font-semibold text-gray-500 uppercase mb-1">Key Drivers</h5>
              <ul className="space-y-1">
                {trend.keyDrivers.slice(0, 3).map((driver: string, i: number) => (
                  <li key={i} className="text-sm text-gray-700 flex items-start gap-1">
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
              <h5 className="text-xs font-semibold text-gray-500 uppercase mb-1">Evidence</h5>
              <ul className="space-y-1">
                {trend.evidence.slice(0, 2).map((ev: any, i: number) => (
                  <li key={i} className="text-sm text-gray-600 flex items-start gap-1">
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
              <h5 className="text-xs font-semibold text-gray-500 uppercase mb-1">Publisher Implications</h5>
              <p className="text-sm text-gray-700">
                <CitationText text={trend.publisherImplications} articles={articles} />
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

// Executive Overview View
const ExecutiveOverview: React.FC<{ data: PAMData; articles: Article[] }> = ({ data, articles }) => {
  // Calculate threat level dynamically from actual scores (ignores cached/stale threat level)
  const powerScore = data.scores?.powerScore || 0;
  const attentionScore = data.scores?.attentionScore || 0;
  const moneyScore = data.scores?.moneyScore || 0;
  const threatLevel = calculateThreatLevel(powerScore, attentionScore, moneyScore);
  const overallScore = calculateOverallScore(powerScore, attentionScore, moneyScore);

  return (
    <div className="space-y-6">
      {/* Headline */}
      {data.executiveSummary?.headline && (
        <Card className="border-l-4 border-l-pink-500">
          <CardContent className="pt-6">
            <p className="text-lg font-medium text-gray-900">
              <CitationText text={data.executiveSummary.headline} articles={articles} />
            </p>
          </CardContent>
        </Card>
      )}

      {/* Score Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <ScoreCard
          label="Power Index"
          score={powerScore}
          icon={<Zap className="w-5 h-5 text-yellow-600" />}
          color="bg-yellow-100"
          explanation={SCORE_EXPLANATIONS.power}
        />
        <ScoreCard
          label="Attention Index"
          score={attentionScore}
          icon={<Eye className="w-5 h-5 text-blue-600" />}
          color="bg-blue-100"
          explanation={SCORE_EXPLANATIONS.attention}
        />
        <ScoreCard
          label="Money Flow"
          score={moneyScore}
          icon={<DollarSign className="w-5 h-5 text-green-600" />}
          color="bg-green-100"
          explanation={SCORE_EXPLANATIONS.money}
        />
        <Card>
          <CardContent className="pt-6">
            <div className="text-center">
              <div className="flex items-center justify-center gap-1">
                <p className="text-sm text-gray-500 uppercase tracking-wide">Threat Level</p>
                <InfoTooltip text={SCORE_EXPLANATIONS.overall} />
              </div>
              <p className={`text-2xl font-bold mt-2 ${
                threatLevel === 'critical' ? 'text-red-600' :
                threatLevel === 'high' ? 'text-orange-500' :
                threatLevel === 'elevated' ? 'text-yellow-500' :
                threatLevel === 'moderate' ? 'text-blue-500' :
                'text-green-500'
              }`}>
                {threatLevel.toUpperCase()}
              </p>
              <p className="text-xs text-gray-400 mt-1">Overall: {overallScore}</p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Trends and Insights Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Trend Radar */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Target className="w-5 h-5 text-pink-500" />
              2030 Trends Radar
              <InfoTooltip text={SCORE_EXPLANATIONS.trend} />
            </CardTitle>
            <p className="text-xs text-gray-500 mt-1">Click any trend to see key drivers, evidence, and implications</p>
          </CardHeader>
          <CardContent className="space-y-3">
            {(data.trendAnalysis?.trends || []).map(trend => (
              <TrendItem key={trend.id} trend={trend} articles={articles} />
            ))}
          </CardContent>
        </Card>

        {/* Key Insights */}
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Key Events</CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="space-y-2">
                {(data.executiveSummary?.keyEvents || []).slice(0, 5).map((event, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-gray-700">
                    <span className="text-pink-500 mt-1">•</span>
                    <CitationText text={event} articles={articles} />
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Emerging Signals</CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="space-y-2">
                {(data.executiveSummary?.emergingSignals || []).slice(0, 5).map((signal, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-gray-700">
                    <span className="text-blue-500 mt-1">→</span>
                    <CitationText text={signal} articles={articles} />
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Strategic Priorities */}
      {data.executiveSummary?.strategicPriorities && data.executiveSummary.strategicPriorities.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Strategic Priorities</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {data.executiveSummary.strategicPriorities.map((p, i) => (
                <div key={i} className="flex items-center gap-3 p-3 bg-gray-50 rounded-lg">
                  <Badge className={
                    p.urgency === 'immediate' ? 'bg-red-100 text-red-700' :
                    p.urgency === 'near_term' ? 'bg-yellow-100 text-yellow-700' :
                    'bg-green-100 text-green-700'
                  }>
                    {p.urgency.replace('_', ' ')}
                  </Badge>
                  <span className="text-sm text-gray-700">{p.priority}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
};

// Power View (simplified)
const PowerView: React.FC<{ data: PAMData; articles: Article[] }> = ({ data, articles }) => {
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
              score={power.infrastructureControl?.score}
              items={power.infrastructureControl?.developments || power.infrastructureControl?.keyPlayers}
              badge={power.infrastructureControl?.concentrationLevel}
              articles={articles}
            />
            <AnalysisSection
              title="Regulatory Influence"
              score={power.regulatoryInfluence?.score}
              items={[
                ...(power.regulatoryInfluence?.activeRegulations || []),
                ...(power.regulatoryInfluence?.keyDevelopments || [])
              ].filter(Boolean)}
              badge={power.regulatoryInfluence?.direction}
              articles={articles}
            />
            <AnalysisSection
              title="Network Centrality"
              score={power.networkCentrality?.score}
              items={power.networkCentrality?.influentialEntities}
              description={power.networkCentrality?.collaborationTrends}
              articles={articles}
            />
            <AnalysisSection
              title="IP Positioning"
              score={power.ipPositioning?.score}
              items={power.ipPositioning?.keyDeals}
              description={power.ipPositioning?.trends}
              articles={articles}
            />
          </div>
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
                            'border-gray-300 text-gray-600'
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
              <p className="text-gray-700">
                <CitationText text={power.summary} articles={articles} />
              </p>
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
            <AnalysisSection
              title="Academic Visibility"
              score={attention.academicVisibility?.score}
              description={attention.academicVisibility?.citationTrends}
              items={attention.academicVisibility?.keyIndicators}
              articles={articles}
            />
            {/* AI Engine Visibility with detailed metrics */}
            <div className="p-4 bg-gray-50 rounded-lg">
              <div className="flex items-center justify-between mb-2">
                <h4 className="font-medium">AI Engine Visibility</h4>
                {attention.aiVisibility?.score !== undefined && (
                  <div className="flex items-center gap-1">
                    <span className="text-lg font-semibold">{attention.aiVisibility.score}/100</span>
                    <InfoTooltip text={SCORE_EXPLANATIONS.analysis} />
                  </div>
                )}
              </div>
              {attention.aiVisibility?.score !== undefined && (
                <Progress value={attention.aiVisibility.score} className="h-2 mb-3" />
              )}
              <div className="space-y-2 text-sm">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1">
                    <span className="text-gray-500">Training data exposure:</span>
                    <InfoTooltip text={ATTENTION_METRIC_EXPLANATIONS.trainingDataExposure} />
                  </div>
                  <span className="font-medium capitalize">{attention.aiVisibility?.trainingDataExposure || 'N/A'}</span>
                </div>
                {attention.aiVisibility?.metadataReadiness !== undefined && (
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1">
                      <span className="text-gray-500">Metadata readiness:</span>
                      <InfoTooltip text={ATTENTION_METRIC_EXPLANATIONS.metadataReadiness} />
                    </div>
                    <span className="font-medium">{attention.aiVisibility.metadataReadiness}/100</span>
                  </div>
                )}
                {attention.aiVisibility?.provenanceStrength !== undefined && (
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1">
                      <span className="text-gray-500">Provenance strength:</span>
                      <InfoTooltip text={ATTENTION_METRIC_EXPLANATIONS.provenanceStrength} />
                    </div>
                    <span className="font-medium">{attention.aiVisibility.provenanceStrength}/100</span>
                  </div>
                )}
              </div>
              {/* Description with citations */}
              {attention.aiVisibility?.trainingDataExposureDescription && (
                <p className="mt-3 pt-3 border-t border-gray-200 text-sm text-gray-600">
                  <CitationText text={attention.aiVisibility.trainingDataExposureDescription} articles={articles} />
                </p>
              )}
            </div>
            <AnalysisSection
              title="Brand Visibility"
              score={attention.brandVisibility?.score}
              description={attention.brandVisibility?.trafficTrends}
              items={attention.brandVisibility?.keyChannels}
              articles={articles}
            />
            {/* Synthesis Exposure with detailed metrics */}
            <div className="p-4 bg-gray-50 rounded-lg">
              <div className="flex items-center justify-between mb-2">
                <h4 className="font-medium">Synthesis Exposure</h4>
                {attention.synthesisExposure?.score !== undefined && (
                  <div className="flex items-center gap-1">
                    <span className="text-lg font-semibold">{attention.synthesisExposure.score}/100</span>
                    <InfoTooltip text={ATTENTION_METRIC_EXPLANATIONS.synthesisExposure} />
                  </div>
                )}
              </div>
              {attention.synthesisExposure?.score !== undefined && (
                <Progress value={attention.synthesisExposure.score} className="h-2 mb-3" />
              )}
              <div className="space-y-2 text-sm">
                {attention.synthesisExposure?.zeroClickRisk && (
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1">
                      <span className="text-gray-500">Zero-click risk:</span>
                      <InfoTooltip text={ATTENTION_METRIC_EXPLANATIONS.zeroClickRisk} />
                    </div>
                    <Badge variant="outline" className="capitalize">{attention.synthesisExposure.zeroClickRisk}</Badge>
                  </div>
                )}
                {attention.synthesisExposure?.attributionRate !== undefined && (
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1">
                      <span className="text-gray-500">Attribution rate:</span>
                      <InfoTooltip text={ATTENTION_METRIC_EXPLANATIONS.attributionRate} />
                    </div>
                    <span className="font-medium">{attention.synthesisExposure.attributionRate}/100</span>
                  </div>
                )}
              </div>
              {/* Description with citations */}
              {attention.synthesisExposure?.description && (
                <p className="mt-3 pt-3 border-t border-gray-200 text-sm text-gray-600">
                  <CitationText text={attention.synthesisExposure.description} articles={articles} />
                </p>
              )}
            </div>
          </div>
          {/* GEO Readiness - Placeholder for external data integration */}
          <div className="p-4 bg-gray-50 rounded-lg border-2 border-dashed border-gray-300">
            <h4 className="font-medium mb-2">GEO Readiness (Generative Engine Optimization)</h4>
            <p className="text-sm text-gray-500 mb-3">
              Measures how well content is optimized for AI discovery and attribution.
            </p>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-3">
              <div className="text-center p-2 bg-white rounded opacity-50">
                <p className="text-lg font-semibold text-gray-400">--</p>
                <p className="text-xs text-gray-400">Structured Metadata</p>
              </div>
              <div className="text-center p-2 bg-white rounded opacity-50">
                <p className="text-lg font-semibold text-gray-400">--</p>
                <p className="text-xs text-gray-400">Machine-Readable Rights</p>
              </div>
              <div className="text-center p-2 bg-white rounded opacity-50">
                <p className="text-lg font-semibold text-gray-400">--</p>
                <p className="text-xs text-gray-400">Provenance Tagging</p>
              </div>
              <div className="text-center p-2 bg-white rounded opacity-50">
                <p className="text-lg font-semibold text-gray-400">--</p>
                <p className="text-xs text-gray-400">API Accessibility</p>
              </div>
              <div className="text-center p-2 bg-white rounded opacity-50">
                <p className="text-lg font-semibold text-gray-400">--</p>
                <p className="text-xs text-gray-400">AI Training Licensing</p>
              </div>
            </div>
            <div className="flex items-center gap-2 text-xs text-amber-600 bg-amber-50 p-2 rounded">
              <Info className="w-4 h-4" />
              <span>Requires external data source integration (e.g., GEO audit service, metadata crawlers)</span>
            </div>
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
                            'border-gray-300 text-gray-600'
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
          {attention.summary && (
            <div className="p-4 bg-gray-50 rounded-lg">
              <h4 className="font-medium mb-2">Summary</h4>
              <p className="text-gray-700">
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
const MoneyView: React.FC<{ data: PAMData; articles: Article[] }> = ({ data, articles }) => {
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
            <div className="p-4 bg-gray-50 rounded-lg">
              <h4 className="font-medium mb-2">Funding Flows</h4>
              <p className="text-2xl font-bold text-green-600 mb-2">
                {money.fundingFlows?.totalEstimatedUsd || 'N/A'}
              </p>
              <div className="space-y-1 text-sm">
                <div className="flex items-center gap-1">
                  <span className="text-gray-500">VC Activity:</span>
                  <span className="capitalize">{money.fundingFlows?.vcActivity || 'N/A'}</span>
                  <InfoTooltip text={MONEY_METRIC_EXPLANATIONS.vcActivity} />
                </div>
                <div className="flex items-center gap-1">
                  <span className="text-gray-500">Government:</span>
                  <span className="capitalize">{money.fundingFlows?.governmentFunding || 'N/A'}</span>
                  <InfoTooltip text={MONEY_METRIC_EXPLANATIONS.governmentFunding} />
                </div>
              </div>
              {money.fundingFlows?.keyDeals && money.fundingFlows.keyDeals.length > 0 && (
                <ul className="mt-2 space-y-1">
                  {money.fundingFlows.keyDeals.slice(0, 3).map((deal: any, i: number) => (
                    <li key={i} className="text-sm text-gray-600">
                      • <CitationText text={typeof deal === 'string' ? deal : deal.deal} articles={articles} />
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div className="p-4 bg-gray-50 rounded-lg">
              <h4 className="font-medium mb-2">Revenue Concentration</h4>
              <p className="text-xl font-bold text-gray-900 mb-2 capitalize">
                {money.revenueConcentration?.concentrationLevel || 'Unknown'}
              </p>
              <p className="text-sm text-gray-500">
                Top players share: {money.revenueConcentration?.topPlayersShare}%
              </p>
              {money.revenueConcentration?.keyMetrics && (
                <ul className="mt-2 space-y-1">
                  {money.revenueConcentration.keyMetrics.slice(0, 3).map((metric: string, i: number) => (
                    <li key={i} className="text-sm text-gray-600">
                      • <CitationText text={metric} articles={articles} />
                    </li>
                  ))}
                </ul>
              )}
            </div>
            {/* M&A Activity with explanations and citations */}
            <div className="p-4 bg-gray-50 rounded-lg">
              <div className="flex items-center justify-between mb-2">
                <h4 className="font-medium">M&A Activity</h4>
                <InfoTooltip text={MONEY_METRIC_EXPLANATIONS.maActivity} />
              </div>
              <p className="text-xl font-bold text-gray-900 mb-2 capitalize">
                {money.maActivity?.activityLevel || 'Unknown'}
              </p>
              <div className="flex items-center gap-1 text-sm text-gray-500 mb-2">
                <span className="capitalize">{money.maActivity?.consolidationTrend || 'stable'}</span>
                <InfoTooltip text={MONEY_METRIC_EXPLANATIONS.consolidationTrend} />
              </div>
              {money.maActivity?.recentDeals && money.maActivity.recentDeals.length > 0 && (
                <ul className="mt-2 space-y-2">
                  {money.maActivity.recentDeals.slice(0, 3).map((deal: any, i: number) => (
                    <li key={i} className="text-sm text-gray-600">
                      <div className="flex items-start gap-1">
                        <span>•</span>
                        <div>
                          <span className="font-medium">{deal.acquirer}</span>
                          <span className="text-gray-400"> → </span>
                          <span className="font-medium">{deal.target}</span>
                          {deal.value && <span className="text-green-600 ml-1">({deal.value})</span>}
                          {deal.type && <Badge variant="outline" className="ml-1 text-xs">{deal.type}</Badge>}
                          {/* Show citation if available */}
                          {deal.citations && deal.citations.length > 0 && (
                            <span className="ml-1">
                              <CitationText text={`[${deal.citations.join('][')}]`} articles={articles} />
                            </span>
                          )}
                        </div>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
              {(!money.maActivity?.recentDeals || money.maActivity.recentDeals.length === 0) && (
                <p className="text-sm text-gray-400 italic">No recent deals found in analyzed articles</p>
              )}
            </div>
            <div className="p-4 bg-gray-50 rounded-lg">
              <h4 className="font-medium mb-2">Cost Dynamics</h4>
              <div className="space-y-1 text-sm">
                <p><span className="text-gray-500">Compute:</span> <span className="capitalize">{money.costDynamics?.computeCostTrend || 'N/A'}</span></p>
                <p><span className="text-gray-500">Publishing:</span> <span className="capitalize">{money.costDynamics?.publishingCosts || 'N/A'}</span></p>
              </div>
              {money.costDynamics?.keyFactors && (
                <ul className="mt-2 space-y-1">
                  {money.costDynamics.keyFactors.slice(0, 3).map((factor: string, i: number) => (
                    <li key={i} className="text-sm text-gray-600">
                      • <CitationText text={factor} articles={articles} />
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
          {/* Licensing Trends */}
          {money.licensingTrends && (
            <div className="p-4 bg-gray-50 rounded-lg">
              <h4 className="font-medium mb-2">AI Training & Licensing Trends</h4>
              <div className="grid grid-cols-2 gap-4 mb-3">
                {money.licensingTrends.aiTrainingRightsValue && (
                  <div>
                    <p className="text-lg font-bold text-green-600">{money.licensingTrends.aiTrainingRightsValue}</p>
                    <p className="text-xs text-gray-500">AI Training Rights Value</p>
                  </div>
                )}
                {money.licensingTrends.growthRate && (
                  <div>
                    <p className="text-lg font-bold text-blue-600">{money.licensingTrends.growthRate}</p>
                    <p className="text-xs text-gray-500">Annual Growth Rate</p>
                  </div>
                )}
              </div>
              {money.licensingTrends.keyDeals && money.licensingTrends.keyDeals.length > 0 && (
                <ul className="space-y-1">
                  {money.licensingTrends.keyDeals.slice(0, 3).map((deal: any, i: number) => (
                    <li key={i} className="text-sm text-gray-600">
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
                            'border-gray-300 text-gray-600'
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
              <p className="text-gray-700">
                <CitationText text={money.summary} articles={articles} />
              </p>
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
              <div className="flex justify-between text-xs text-gray-500 mt-1">
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
              <div className="flex justify-between text-xs text-gray-500 mt-1">
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
              <div className="absolute -left-2 top-1/2 -translate-y-1/2 -rotate-90 text-xs text-gray-500 whitespace-nowrap">
                ← Low Regulation | High Regulation →
              </div>
              <div className="absolute bottom-0 left-1/2 -translate-x-1/2 text-xs text-gray-500">
                ← Distributed | Concentrated →
              </div>

              {/* Matrix grid */}
              <div className="grid grid-cols-2 gap-2 ml-6 mb-6">
                {/* Top row: High Regulation */}
                {scenarioList.filter(s => s.quadrant.includes('High Regulation')).map(s => {
                  const scenarioData = scenarios.scenarios?.[s.id];
                  const isMostLikely = mostLikelyNormalized === s.id;
                  const probability = scenarioData?.currentProbability
                    ? (scenarioData.currentProbability * 100).toFixed(0)
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
                            <h4 className="font-semibold text-sm">{s.name}</h4>
                            <p className="text-xs text-gray-500">{s.quadrant}</p>
                          </div>
                        </div>
                        {isMostLikely && <Badge className="bg-pink-500 text-xs">Most Likely</Badge>}
                      </div>
                      <p className="text-xs text-gray-600 mb-3">{s.longDesc}</p>
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-1">
                          <span className="text-2xl font-bold">{probability}%</span>
                          <InfoTooltip text={SCENARIO_EXPLANATIONS.probability} />
                        </div>
                        <div className="text-right text-xs">
                          <p className="text-gray-500">Regulation: <span className="font-medium capitalize">{scenarioData?.regulationLevel || 'N/A'}</span></p>
                          <p className="text-gray-500">Concentration: <span className="font-medium capitalize">{scenarioData?.concentrationLevel || 'N/A'}</span></p>
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
                    ? (scenarioData.currentProbability * 100).toFixed(0)
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
                            <h4 className="font-semibold text-sm">{s.name}</h4>
                            <p className="text-xs text-gray-500">{s.quadrant}</p>
                          </div>
                        </div>
                        {isMostLikely && <Badge className="bg-pink-500 text-xs">Most Likely</Badge>}
                      </div>
                      <p className="text-xs text-gray-600 mb-3">{s.longDesc}</p>
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-1">
                          <span className="text-2xl font-bold">{probability}%</span>
                          <InfoTooltip text={SCENARIO_EXPLANATIONS.probability} />
                        </div>
                        <div className="text-right text-xs">
                          <p className="text-gray-500">Regulation: <span className="font-medium capitalize">{scenarioData?.regulationLevel || 'N/A'}</span></p>
                          <p className="text-gray-500">Concentration: <span className="font-medium capitalize">{scenarioData?.concentrationLevel || 'N/A'}</span></p>
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
              <h4 className="font-medium mb-2 flex items-center gap-2">
                <TrendingUp className="w-4 h-4 text-purple-600" />
                Current Trajectory
              </h4>
              <p className="text-gray-700">
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
                <div key={s.id} className={`p-3 rounded-lg border ${isMostLikely ? 'border-pink-300 bg-pink-50' : 'border-gray-200'}`}>
                  <div className="flex items-center gap-2 mb-2">
                    <span>{s.icon}</span>
                    <h5 className="font-medium">{s.name}</h5>
                    {isMostLikely && <Badge className="bg-pink-500 text-xs">Focus Here</Badge>}
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-sm">
                    <div>
                      <p className="text-gray-500 text-xs uppercase mb-1">Key Actions</p>
                      <p className="text-gray-700">
                        {s.id === 'trustedEcosystem' && 'Invest in provenance tech, build trust signals, diversify partnerships'}
                        {s.id === 'fragmentedCompliance' && 'Build compliance infrastructure, seek regional partnerships, automate reporting'}
                        {s.id === 'openChaos' && 'Focus on speed and reach, build direct audience relationships, embrace remix culture'}
                        {s.id === 'behemothControl' && 'Partner with platforms early, optimize for AI discovery, protect core IP'}
                      </p>
                    </div>
                    <div>
                      <p className="text-gray-500 text-xs uppercase mb-1">Risks</p>
                      <p className="text-gray-700">
                        {s.id === 'trustedEcosystem' && 'Compliance costs, slower innovation, regulatory capture'}
                        {s.id === 'fragmentedCompliance' && 'Market fragmentation, high overhead, regional lock-in'}
                        {s.id === 'openChaos' && 'Revenue erosion, attribution loss, quality degradation'}
                        {s.id === 'behemothControl' && 'Commoditization, margin compression, dependency risk'}
                      </p>
                    </div>
                    <div>
                      <p className="text-gray-500 text-xs uppercase mb-1">Opportunities</p>
                      <p className="text-gray-700">
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
  items?: string[];
  description?: string;
  badge?: string;
  articles?: Article[];
}> = ({ title, score, items, description, badge, articles = [] }) => {
  const hasContent = description || (items && items.length > 0);

  return (
    <div className="p-4 bg-gray-50 rounded-lg">
      <div className="flex items-center justify-between mb-2">
        <h4 className="font-medium">{title}</h4>
        {score !== undefined && (
          <div className="flex items-center gap-1">
            <span className="text-lg font-semibold">{score}/100</span>
            <InfoTooltip text={SCORE_EXPLANATIONS.analysis} />
          </div>
        )}
      </div>
      {score !== undefined && <Progress value={score} className="h-2 mb-2" />}
      {badge && (
        <Badge variant="outline" className="mb-2 capitalize">{badge}</Badge>
      )}
      {description && (
        <p className="text-sm text-gray-600">
          <CitationText text={description} articles={articles} />
        </p>
      )}
      {items && items.length > 0 && (
        <ul className="mt-2 space-y-1">
          {items.slice(0, 5).map((item, i) => (
            <li key={i} className="text-sm text-gray-600">
              • <CitationText text={item} articles={articles} />
            </li>
          ))}
        </ul>
      )}
      {!hasContent && (
        <p className="text-sm text-gray-400 italic mt-2">No specific data found in analyzed articles</p>
      )}
    </div>
  );
};

const EmptyState: React.FC<{ message: string }> = ({ message }) => (
  <div className="text-center py-12 text-gray-500">
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
                <span className="text-xs text-gray-400 mt-1 w-6">{idx + 1}.</span>
                <div className="flex-1 min-w-0">
                  <a
                    href={article.uri}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm font-medium text-gray-900 hover:text-pink-600 flex items-center gap-1"
                  >
                    <span className="truncate">{article.title}</span>
                    <ExternalLink className="w-3 h-3 flex-shrink-0" />
                  </a>
                  <div className="flex items-center gap-2 mt-0.5">
                    <span className="text-xs text-gray-500">{article.source}</span>
                    {article.publicationDate && (
                      <>
                        <span className="text-gray-300">•</span>
                        <span className="text-xs text-gray-500">
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
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
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
              <p className="text-gray-600">
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
            <h2 className="text-2xl font-semibold text-gray-900 mb-2">
              Power, Attention & Money Dashboard
            </h2>
            <p className="text-gray-600 mb-6 max-w-lg mx-auto">
              Strategic intelligence tracking the three fundamental flows reshaping the knowledge economy.
              Analyzes articles across <strong>all topics</strong> using trend-specific semantic queries.
            </p>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 max-w-2xl mx-auto text-left mb-6">
              <div className="p-4 bg-yellow-50 rounded-lg">
                <Zap className="w-6 h-6 text-yellow-600 mb-2" />
                <h3 className="font-medium">Power</h3>
                <p className="text-sm text-gray-600">Infrastructure control, regulatory influence, network centrality</p>
              </div>
              <div className="p-4 bg-blue-50 rounded-lg">
                <Eye className="w-6 h-6 text-blue-600 mb-2" />
                <h3 className="font-medium">Attention</h3>
                <p className="text-sm text-gray-600">AI visibility, brand recognition, citation exposure</p>
              </div>
              <div className="p-4 bg-green-50 rounded-lg">
                <DollarSign className="w-6 h-6 text-green-600 mb-2" />
                <h3 className="font-medium">Money</h3>
                <p className="text-sm text-gray-600">Funding flows, M&A activity, market consolidation</p>
              </div>
            </div>
            <p className="text-gray-500 text-sm">
              Click <strong>Refresh</strong> above to run cross-topic PAM analysis. Use <strong>Tune</strong> to configure trends and time horizon.
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  // Convert reference articles to Article format for citation renderer
  const citationArticles: Article[] = useMemo(() => {
    return (data?.referenceArticles || []).map(article => ({
      id: article.id,
      url: article.uri,
      uri: article.uri,
      title: article.title,
      source: article.source,
    }));
  }, [data?.referenceArticles]);

  // Data available - show dashboard
  return (
    <div className="p-6">
      <ViewTabs activeView={activeView} onViewChange={onViewChange} />

      {activeView === 'executive' && <ExecutiveOverview data={data} articles={citationArticles} />}
      {activeView === 'power' && <PowerView data={data} articles={citationArticles} />}
      {activeView === 'attention' && <AttentionView data={data} articles={citationArticles} />}
      {activeView === 'money' && <MoneyView data={data} articles={citationArticles} />}
      {activeView === 'scenarios' && <ScenariosView data={data} articles={citationArticles} />}

      {/* Footer with metadata */}
      <div className="mt-6 pt-4 border-t flex items-center justify-between text-sm text-gray-500">
        <span>Analyzed {data.articlesAnalyzed} articles</span>
        <span>Model: {data.modelUsed}</span>
        <span>Generated: {new Date(data.createdAt).toLocaleString()}</span>
      </div>

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
