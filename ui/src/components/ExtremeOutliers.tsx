/**
 * Extreme Outlier Scenarios (EOS) Component
 * Black Swan events, Contrarian analysis, and Wild Card futures
 */

import { useState } from 'react';
import {
  Loader2,
  AlertCircle,
  CheckCircle2,
  AlertTriangle,
  Zap,
  Eye,
  TrendingDown,
  Shuffle,
  ChevronDown,
  ChevronUp,
  Target,
  Clock,
  Lightbulb,
  Shield,
  BarChart3
} from 'lucide-react';
import { Button } from './ui/button';
import { Progress } from './ui/progress';
import { Alert, AlertDescription, AlertTitle } from './ui/alert';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';
import { Badge } from './ui/badge';
import { Separator } from './ui/separator';
import {
  EOS_STAGES,
  type EOSScenario,
  type EOSConfig,
  type EOSResult
} from '../hooks/useExtremeOutliers';

interface ExtremeOutliersProps {
  topic?: string;
  // EOS state from parent (hook lifted to App.tsx)
  isGenerating: boolean;
  currentStage: string;
  stageProgress: number;
  overallProgress: number;
  scenarios: EOSScenario[];
  result: EOSResult | null;
  error: string | null;
  signalsDetected: number;
  pathwaysIdentified: number;
  scenariosGenerated: number;
  // Config state
  scenarioCount: number;
  includeBlackSwans: boolean;
  includeContrarian: boolean;
  includeWildCards: boolean;
  timeHorizon: 'near' | 'mid' | 'long';
  onScenarioCountChange: (value: number) => void;
  onIncludeBlackSwansChange: (value: boolean) => void;
  onIncludeContrarianChange: (value: boolean) => void;
  onIncludeWildCardsChange: (value: boolean) => void;
  onTimeHorizonChange: (value: 'near' | 'mid' | 'long') => void;
  // Actions
  onClearError: () => void;
  onClearResults: () => void;
}

// Stage indicator component for EOS workflow
function EOSStageIndicator({
  stages,
  currentStage,
  stageProgress
}: {
  stages: typeof EOS_STAGES;
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
          <div key={stage.name} className="flex items-center">
            <div className="flex flex-col items-center">
              <div
                className={`
                  w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium
                  ${status === 'complete' ? 'bg-green-500 text-white' : ''}
                  ${status === 'active' ? 'bg-purple-500 text-white animate-pulse' : ''}
                  ${status === 'pending' ? 'bg-gray-200 text-gray-500' : ''}
                `}
              >
                {status === 'complete' ? (
                  <CheckCircle2 className="w-4 h-4" />
                ) : status === 'active' ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  index + 1
                )}
              </div>
              <span className={`text-xs mt-1 ${status === 'active' ? 'text-purple-600 font-medium' : 'text-gray-500'}`}>
                {stage.label}
              </span>
            </div>
            {index < stages.length - 1 && (
              <div className={`w-12 h-0.5 mx-2 ${
                getStageStatus(stages[index + 1].name) !== 'pending' ? 'bg-green-500' : 'bg-gray-200'
              }`} />
            )}
          </div>
        );
      })}
    </div>
  );
}

// Stats display during generation
function GenerationStats({
  signalsDetected,
  pathwaysIdentified,
  scenariosGenerated,
}: {
  signalsDetected: number;
  pathwaysIdentified: number;
  scenariosGenerated: number;
}) {
  return (
    <div className="grid grid-cols-3 gap-4 mb-6">
      <Card>
        <CardContent className="pt-4">
          <div className="flex items-center gap-2">
            <Eye className="w-4 h-4 text-blue-500" />
            <div>
              <p className="text-2xl font-bold">{signalsDetected}</p>
              <p className="text-xs text-gray-500">Weak Signals</p>
            </div>
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="pt-4">
          <div className="flex items-center gap-2">
            <TrendingDown className="w-4 h-4 text-orange-500" />
            <div>
              <p className="text-2xl font-bold">{pathwaysIdentified}</p>
              <p className="text-xs text-gray-500">Amplification Paths</p>
            </div>
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="pt-4">
          <div className="flex items-center gap-2">
            <Zap className="w-4 h-4 text-purple-500" />
            <div>
              <p className="text-2xl font-bold">{scenariosGenerated}</p>
              <p className="text-xs text-gray-500">Scenarios Built</p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

// Category icon and color mapping
const CATEGORY_CONFIG: Record<string, { icon: React.ReactNode; bgColor: string; borderColor: string; textColor: string; label: string }> = {
  black_swan: {
    icon: <AlertTriangle className="w-5 h-5" />,
    bgColor: 'bg-purple-50',
    borderColor: 'border-purple-300',
    textColor: 'text-purple-700',
    label: 'Black Swan'
  },
  contrarian: {
    icon: <Shuffle className="w-5 h-5" />,
    bgColor: 'bg-amber-50',
    borderColor: 'border-amber-300',
    textColor: 'text-amber-700',
    label: 'Contrarian'
  },
  wild_card: {
    icon: <Zap className="w-5 h-5" />,
    bgColor: 'bg-blue-50',
    borderColor: 'border-blue-300',
    textColor: 'text-blue-700',
    label: 'Wild Card'
  }
};

// Probability badge colors
const PROBABILITY_COLORS: Record<string, string> = {
  very_low: 'bg-gray-100 text-gray-700',
  low: 'bg-yellow-100 text-yellow-700',
  moderate: 'bg-orange-100 text-orange-700'
};

// Time horizon labels
const TIME_HORIZON_LABELS: Record<string, string> = {
  near: '0-2 years',
  mid: '2-5 years',
  long: '5-10+ years'
};

// Individual scenario card
function ScenarioCard({ scenario }: { scenario: EOSScenario }) {
  const [expanded, setExpanded] = useState(false);
  const categoryConfig = CATEGORY_CONFIG[scenario.category] || CATEGORY_CONFIG.wild_card;

  return (
    <Card className={`${categoryConfig.bgColor} border-2 ${categoryConfig.borderColor}`}>
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-2">
            <span className={categoryConfig.textColor}>{categoryConfig.icon}</span>
            <Badge variant="outline" className={categoryConfig.textColor}>
              {categoryConfig.label}
            </Badge>
          </div>
          <div className="flex items-center gap-2">
            <Badge className={PROBABILITY_COLORS[scenario.probability]}>
              {scenario.probability.replace('_', ' ')} probability
            </Badge>
            <Badge variant="outline" className="bg-white">
              Impact: {scenario.impact_rating}/10
            </Badge>
          </div>
        </div>
        <CardTitle className="text-lg mt-2">{scenario.title}</CardTitle>
        <CardDescription className="text-sm font-medium">
          {scenario.subtitle}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <p className="text-gray-700 mb-4">{scenario.description}</p>

        {/* Time Horizon */}
        <div className="flex items-center gap-2 mb-4 text-sm text-gray-600">
          <Clock className="w-4 h-4" />
          <span>Time Horizon: {scenario.time_horizon}</span>
        </div>

        {/* Trigger Events */}
        <div className="mb-4">
          <h4 className="text-sm font-semibold flex items-center gap-2 mb-2">
            <Target className="w-4 h-4 text-red-500" />
            Trigger Events
          </h4>
          <ul className="text-sm space-y-1">
            {scenario.trigger_events.slice(0, expanded ? undefined : 2).map((event, idx) => (
              <li key={idx} className="flex items-start gap-2">
                <span className="text-red-400">•</span>
                <span>{event}</span>
              </li>
            ))}
          </ul>
        </div>

        {/* Expandable sections */}
        {expanded && (
          <>
            <Separator className="my-4" />

            {/* Weak Signals */}
            <div className="mb-4">
              <h4 className="text-sm font-semibold flex items-center gap-2 mb-2">
                <Eye className="w-4 h-4 text-blue-500" />
                Weak Signals Detected
              </h4>
              <ul className="text-sm space-y-1">
                {scenario.weak_signals.map((signal, idx) => (
                  <li key={idx} className="flex items-start gap-2">
                    <span className="text-blue-400">•</span>
                    <span>{signal}</span>
                  </li>
                ))}
              </ul>
            </div>

            {/* Amplification Path */}
            <div className="mb-4">
              <h4 className="text-sm font-semibold flex items-center gap-2 mb-2">
                <BarChart3 className="w-4 h-4 text-orange-500" />
                Amplification Path
              </h4>
              <p className="text-sm text-gray-700">{scenario.amplification_path}</p>
            </div>

            {/* Early Warning Signs */}
            <div className="mb-4">
              <h4 className="text-sm font-semibold flex items-center gap-2 mb-2">
                <AlertCircle className="w-4 h-4 text-yellow-500" />
                Early Warning Signs
              </h4>
              <ul className="text-sm space-y-1">
                {scenario.early_warning_signs.map((sign, idx) => (
                  <li key={idx} className="flex items-start gap-2">
                    <span className="text-yellow-500">•</span>
                    <span>{sign}</span>
                  </li>
                ))}
              </ul>
            </div>

            {/* Strategic Implications */}
            <div className="mb-4">
              <h4 className="text-sm font-semibold flex items-center gap-2 mb-2">
                <Lightbulb className="w-4 h-4 text-purple-500" />
                Strategic Implications
              </h4>
              <p className="text-sm text-gray-700">{scenario.strategic_implications}</p>
            </div>

            {/* Preparation Actions */}
            <div className="mb-4">
              <h4 className="text-sm font-semibold flex items-center gap-2 mb-2">
                <Shield className="w-4 h-4 text-green-500" />
                Preparation Actions
              </h4>
              <ul className="text-sm space-y-1">
                {scenario.preparation_actions.map((action, idx) => (
                  <li key={idx} className="flex items-start gap-2">
                    <span className="text-green-500">{idx + 1}.</span>
                    <span>{action}</span>
                  </li>
                ))}
              </ul>
            </div>

            {/* Source Trends & Consensus */}
            {(scenario.source_trends?.length > 0 || scenario.source_consensus?.length > 0) && (
              <div className="bg-white/50 rounded-lg p-3 mt-4">
                <h4 className="text-xs font-semibold text-gray-500 mb-2">DERIVED FROM</h4>
                {scenario.source_trends?.length > 0 && (
                  <div className="mb-2">
                    <span className="text-xs text-gray-500">Trends: </span>
                    <span className="text-xs">{scenario.source_trends.join(', ')}</span>
                  </div>
                )}
                {scenario.source_consensus?.length > 0 && (
                  <div>
                    <span className="text-xs text-gray-500">Consensus: </span>
                    <span className="text-xs">{scenario.source_consensus.join(', ')}</span>
                  </div>
                )}
              </div>
            )}
          </>
        )}

        {/* Expand/Collapse button */}
        <Button
          variant="ghost"
          size="sm"
          className="w-full mt-2"
          onClick={() => setExpanded(!expanded)}
        >
          {expanded ? (
            <>
              <ChevronUp className="w-4 h-4 mr-2" />
              Show Less
            </>
          ) : (
            <>
              <ChevronDown className="w-4 h-4 mr-2" />
              Show Details
            </>
          )}
        </Button>
      </CardContent>
    </Card>
  );
}

// Empty state
function EmptyState() {
  return (
    <div className="text-center py-12 text-gray-500">
      <AlertTriangle className="w-12 h-12 mx-auto mb-4 opacity-50" />
      <p>No extreme outlier scenarios available.</p>
      <p className="text-sm mt-2">Click "Generate" to create scenarios based on your current analysis.</p>
    </div>
  );
}

export function ExtremeOutliers({
  topic,
  // EOS state from parent
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
  // Config state
  scenarioCount,
  includeBlackSwans,
  includeContrarian,
  includeWildCards,
  timeHorizon,
  onScenarioCountChange,
  onIncludeBlackSwansChange,
  onIncludeContrarianChange,
  onIncludeWildCardsChange,
  onTimeHorizonChange,
  // Actions
  onClearError,
  onClearResults,
}: ExtremeOutliersProps) {
  const [showConfig, setShowConfig] = useState(false);

  // Group scenarios by category
  const blackSwanScenarios = scenarios.filter(s => s.category === 'black_swan');
  const contrarianScenarios = scenarios.filter(s => s.category === 'contrarian');
  const wildCardScenarios = scenarios.filter(s => s.category === 'wild_card');

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-xl font-semibold text-gray-900 flex items-center gap-2">
          <AlertTriangle className="w-5 h-5 text-purple-500" />
          Extreme Outlier Scenarios
        </h2>
        <p className="text-sm text-gray-500 mt-1">
          Black Swan events, Contrarian analysis, and Wild Card futures
        </p>
      </div>

      {/* Quick config toggle */}
      <div className="flex items-center gap-4 text-sm">
        <button
          onClick={() => setShowConfig(!showConfig)}
          className="text-gray-500 hover:text-gray-700 flex items-center gap-1"
        >
          {showConfig ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          Generation Settings
        </button>
        <span className="text-gray-400">|</span>
        <span className="text-gray-500">
          Scenarios: {scenarioCount} · Horizon: {TIME_HORIZON_LABELS[timeHorizon]}
        </span>
        <span className="text-gray-400">|</span>
        <div className="flex gap-1">
          {includeBlackSwans && <Badge variant="outline" className="text-xs text-purple-600">Black Swan</Badge>}
          {includeContrarian && <Badge variant="outline" className="text-xs text-amber-600">Contrarian</Badge>}
          {includeWildCards && <Badge variant="outline" className="text-xs text-blue-600">Wild Card</Badge>}
        </div>
        {topic && (
          <>
            <span className="text-gray-400">|</span>
            <Badge variant="outline">{topic}</Badge>
          </>
        )}
      </div>

      {/* Expandable config */}
      {showConfig && (
        <Card>
          <CardContent className="pt-4">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div>
                <label className="text-sm font-medium text-gray-700">Number of Scenarios</label>
                <p className="text-xs text-gray-400 mb-1">Total scenarios to generate</p>
                <input
                  type="number"
                  value={scenarioCount}
                  onChange={(e) => onScenarioCountChange(Number(e.target.value))}
                  min={1}
                  max={10}
                  className="mt-1 w-full px-3 py-2 border rounded-md text-sm"
                />
              </div>
              <div>
                <label className="text-sm font-medium text-gray-700">Time Horizon</label>
                <p className="text-xs text-gray-400 mb-1">Scenario timeframe focus</p>
                <select
                  value={timeHorizon}
                  onChange={(e) => onTimeHorizonChange(e.target.value as 'near' | 'mid' | 'long')}
                  className="mt-1 w-full px-3 py-2 border rounded-md text-sm"
                >
                  <option value="near">Near-term (0-2 years)</option>
                  <option value="mid">Mid-term (2-5 years)</option>
                  <option value="long">Long-term (5-10+ years)</option>
                </select>
              </div>
              <div className="col-span-2">
                <label className="text-sm font-medium text-gray-700">Scenario Types</label>
                <p className="text-xs text-gray-400 mb-2">Select which types to include</p>
                <div className="flex gap-4">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={includeBlackSwans}
                      onChange={(e) => onIncludeBlackSwansChange(e.target.checked)}
                      className="rounded"
                    />
                    <span className="text-sm text-purple-700">Black Swan</span>
                  </label>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={includeContrarian}
                      onChange={(e) => onIncludeContrarianChange(e.target.checked)}
                      className="rounded"
                    />
                    <span className="text-sm text-amber-700">Contrarian</span>
                  </label>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={includeWildCards}
                      onChange={(e) => onIncludeWildCardsChange(e.target.checked)}
                      className="rounded"
                    />
                    <span className="text-sm text-blue-700">Wild Card</span>
                  </label>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Error display */}
      {error && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>Generation Error</AlertTitle>
          <AlertDescription className="flex items-center justify-between">
            {error}
            <Button variant="ghost" size="sm" onClick={onClearError}>
              Dismiss
            </Button>
          </AlertDescription>
        </Alert>
      )}

      {/* Generation progress */}
      {isGenerating && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg flex items-center gap-2">
              <Loader2 className="w-5 h-5 animate-spin text-purple-500" />
              Generating Extreme Outlier Scenarios...
            </CardTitle>
            <CardDescription>
              {EOS_STAGES.find(s => s.name === currentStage)?.description || 'Initializing...'}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <EOSStageIndicator
              stages={EOS_STAGES}
              currentStage={currentStage}
              stageProgress={stageProgress}
            />
            <Progress value={overallProgress * 100} className="h-2 mb-4" />
            <GenerationStats
              signalsDetected={signalsDetected}
              pathwaysIdentified={pathwaysIdentified}
              scenariosGenerated={scenariosGenerated}
            />
          </CardContent>
        </Card>
      )}

      {/* Scenarios display */}
      {!isGenerating && scenarios.length > 0 ? (
        <div className="space-y-6">
          {/* Metadata summary */}
          {result?.metadata && (
            <div className="flex items-center gap-4 text-sm text-gray-600 bg-gray-50 p-3 rounded-lg">
              <span className="flex items-center gap-1">
                <Eye className="w-4 h-4" />
                {result.metadata.signals_detected} signals detected
              </span>
              <span className="flex items-center gap-1">
                <TrendingDown className="w-4 h-4" />
                {result.metadata.pathways_explored} pathways explored
              </span>
              <span className="flex items-center gap-1">
                <Zap className="w-4 h-4" />
                {result.metadata.scenarios_generated} scenarios generated
              </span>
              {result.metadata.generated_at && (
                <span className="flex items-center gap-1">
                  <Clock className="w-4 h-4" />
                  {new Date(result.metadata.generated_at).toLocaleString()}
                </span>
              )}
            </div>
          )}

          {/* Black Swan Scenarios */}
          {blackSwanScenarios.length > 0 && (
            <div>
              <h3 className="text-lg font-semibold text-purple-700 flex items-center gap-2 mb-4">
                <AlertTriangle className="w-5 h-5" />
                Black Swan Events ({blackSwanScenarios.length})
              </h3>
              <div className="grid gap-4">
                {blackSwanScenarios.map((scenario) => (
                  <ScenarioCard key={scenario.id} scenario={scenario} />
                ))}
              </div>
            </div>
          )}

          {/* Contrarian Scenarios */}
          {contrarianScenarios.length > 0 && (
            <div>
              <h3 className="text-lg font-semibold text-amber-700 flex items-center gap-2 mb-4">
                <Shuffle className="w-5 h-5" />
                Contrarian Analysis ({contrarianScenarios.length})
              </h3>
              <div className="grid gap-4">
                {contrarianScenarios.map((scenario) => (
                  <ScenarioCard key={scenario.id} scenario={scenario} />
                ))}
              </div>
            </div>
          )}

          {/* Wild Card Scenarios */}
          {wildCardScenarios.length > 0 && (
            <div>
              <h3 className="text-lg font-semibold text-blue-700 flex items-center gap-2 mb-4">
                <Zap className="w-5 h-5" />
                Wild Card Futures ({wildCardScenarios.length})
              </h3>
              <div className="grid gap-4">
                {wildCardScenarios.map((scenario) => (
                  <ScenarioCard key={scenario.id} scenario={scenario} />
                ))}
              </div>
            </div>
          )}
        </div>
      ) : (
        !isGenerating && <EmptyState />
      )}

      {/* Clear results button */}
      {result && !isGenerating && (
        <div className="flex justify-end">
          <Button variant="ghost" size="sm" onClick={onClearResults}>
            Clear Results
          </Button>
        </div>
      )}
    </div>
  );
}

export default ExtremeOutliers;
