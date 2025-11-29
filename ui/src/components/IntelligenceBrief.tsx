/**
 * Strategic Intelligence Oracle - Intelligence Brief Component
 * Displays the 24-hour intelligence scan with real-time progress
 */

import { useState, useEffect } from 'react';
import {
  Loader2,
  AlertCircle,
  CheckCircle2,
  Clock,
  Search,
  Filter,
  Zap,
  Eye,
  ChevronDown,
  ChevronUp,
  AlertTriangle,
  Shield,
  TrendingUp,
  FileText
} from 'lucide-react';
import { Button } from './ui/button';
import { Progress } from './ui/progress';
import { Alert, AlertDescription, AlertTitle } from './ui/alert';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';
import { Badge } from './ui/badge';
import { Separator } from './ui/separator';
import {
  SIO_STAGES,
  type SIOConfig
} from '../hooks/useStrategicIntelligence';
import ReactMarkdown from 'react-markdown';

interface IntelligenceBriefProps {
  topic?: string;
  profileId?: number;
  // SIO state from parent (hook lifted to App.tsx)
  isScanning: boolean;
  currentStage: string;
  stageProgress: number;
  overallProgress: number;
  briefContent: string;
  scanResult: any;
  error: string | null;
  articlesCollected: number;
  articlesScreened: number;
  eventsIdentified: number;
  eventsAnalyzed: number;
  currentEvent: string;
  // SIO config state
  hoursBack: number;
  maxEvents: number;
  credibilityThreshold: number;
  onHoursBackChange: (value: number) => void;
  onMaxEventsChange: (value: number) => void;
  onCredibilityThresholdChange: (value: number) => void;
  // Actions
  onClearError: () => void;
  onClearResults: () => void;
}

// Stage indicator component
function StageIndicator({
  stages,
  currentStage,
  stageProgress
}: {
  stages: typeof SIO_STAGES;
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
                  ${status === 'active' ? 'bg-pink-500 text-white animate-pulse' : ''}
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
              <span className={`text-xs mt-1 ${status === 'active' ? 'text-pink-600 font-medium' : 'text-gray-500'}`}>
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

// Stats display during scan
function ScanStats({
  articlesCollected,
  articlesScreened,
  eventsIdentified,
  eventsAnalyzed,
  currentEvent,
}: {
  articlesCollected: number;
  articlesScreened: number;
  eventsIdentified: number;
  eventsAnalyzed: number;
  currentEvent: string;
}) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
      <Card>
        <CardContent className="pt-4">
          <div className="flex items-center gap-2">
            <Search className="w-4 h-4 text-blue-500" />
            <div>
              <p className="text-2xl font-bold">{articlesCollected}</p>
              <p className="text-xs text-gray-500">Articles Found</p>
            </div>
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="pt-4">
          <div className="flex items-center gap-2">
            <Filter className="w-4 h-4 text-green-500" />
            <div>
              <p className="text-2xl font-bold">{articlesScreened}</p>
              <p className="text-xs text-gray-500">Passed Screening</p>
            </div>
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="pt-4">
          <div className="flex items-center gap-2">
            <Zap className="w-4 h-4 text-yellow-500" />
            <div>
              <p className="text-2xl font-bold">{eventsIdentified}</p>
              <p className="text-xs text-gray-500">Events Identified</p>
            </div>
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="pt-4">
          <div className="flex items-center gap-2">
            <Eye className="w-4 h-4 text-purple-500" />
            <div>
              <p className="text-2xl font-bold">{eventsAnalyzed}</p>
              <p className="text-xs text-gray-500">Events Analyzed</p>
            </div>
          </div>
        </CardContent>
      </Card>
      {currentEvent && (
        <div className="col-span-full">
          <p className="text-sm text-gray-600 flex items-center gap-2">
            <Loader2 className="w-3 h-3 animate-spin" />
            Analyzing: <span className="font-medium">{currentEvent}</span>
          </p>
        </div>
      )}
    </div>
  );
}

// Quality Gates Display
function QualityGatesDisplay({
  passed,
  failed
}: {
  passed?: string[];
  failed?: string[]
}) {
  if (!passed?.length && !failed?.length) return null;

  const gateLabels: Record<string, string> = {
    'source_diversity': 'Source Diversity',
    'credibility_minimum': 'Credibility Check',
    'temporal_freshness': 'Freshness',
    'geographic_diversity': 'Geographic Coverage',
    'contradiction_check': 'Contradiction Check'
  };

  return (
    <div className="flex flex-wrap gap-2">
      {passed?.map(gate => (
        <Badge key={gate} variant="outline" className="bg-green-50 text-green-700 border-green-200">
          <CheckCircle2 className="w-3 h-3 mr-1" />
          {gateLabels[gate] || gate}
        </Badge>
      ))}
      {failed?.map(gate => (
        <Badge key={gate} variant="outline" className="bg-red-50 text-red-700 border-red-200">
          <AlertTriangle className="w-3 h-3 mr-1" />
          {gateLabels[gate] || gate}
        </Badge>
      ))}
    </div>
  );
}

// Events Summary List
function EventsSummary({ events }: { events?: any[] }) {
  const [expanded, setExpanded] = useState(false);

  if (!events?.length) return null;

  const displayEvents = expanded ? events : events.slice(0, 5);

  const importanceColors: Record<string, string> = {
    'critical': 'text-red-600 bg-red-50',
    'high': 'text-orange-600 bg-orange-50',
    'medium': 'text-yellow-600 bg-yellow-50',
    'monitoring': 'text-gray-600 bg-gray-50'
  };

  return (
    <Card className="mb-4">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm flex items-center gap-2">
          <TrendingUp className="w-4 h-4" />
          Events Analyzed ({events.length})
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-2">
          {displayEvents.map((event, idx) => (
            <div key={idx} className="flex items-center justify-between text-sm p-2 rounded-md hover:bg-gray-50">
              <div className="flex items-center gap-2 flex-1 min-w-0">
                <Badge
                  variant="outline"
                  className={`text-xs ${importanceColors[event.importance] || ''}`}
                >
                  {event.importance?.toUpperCase()}
                </Badge>
                <span className="truncate">{event.title}</span>
              </div>
              <div className="flex items-center gap-2 text-gray-500">
                <span className="text-xs">{event.source_count} sources</span>
                <Badge variant="outline" className="text-xs">
                  {Math.round((event.confidence || 0) * 100)}%
                </Badge>
              </div>
            </div>
          ))}
        </div>
        {events.length > 5 && (
          <Button
            variant="ghost"
            size="sm"
            className="mt-2 w-full"
            onClick={() => setExpanded(!expanded)}
          >
            {expanded ? 'Show Less' : `Show ${events.length - 5} More`}
          </Button>
        )}
      </CardContent>
    </Card>
  );
}

// Brief display with markdown rendering
function BriefDisplay({
  content,
  metadata,
  events,
  isStreaming
}: {
  content: string;
  metadata?: any;
  events?: any[];
  isStreaming: boolean;
}) {
  const [showMetadata, setShowMetadata] = useState(false);

  if (!content) {
    return (
      <div className="text-center py-12 text-gray-500">
        <FileText className="w-12 h-12 mx-auto mb-4 opacity-50" />
        <p>No intelligence brief available.</p>
        <p className="text-sm mt-2">Click "Generate Brief" to start a 24-hour scan.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Metadata summary */}
      {metadata && (
        <div className="flex items-center justify-between bg-gray-50 p-3 rounded-lg">
          <div className="flex items-center gap-4 text-sm text-gray-600">
            <span className="flex items-center gap-1">
              <Search className="w-4 h-4" />
              {metadata.articles_collected} articles
            </span>
            <span className="flex items-center gap-1">
              <Zap className="w-4 h-4" />
              {metadata.events_analyzed} events
            </span>
            {metadata.generated_at && (
              <span className="flex items-center gap-1">
                <Clock className="w-4 h-4" />
                {new Date(metadata.generated_at).toLocaleString()}
              </span>
            )}
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setShowMetadata(!showMetadata)}
          >
            {showMetadata ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
            Details
          </Button>
        </div>
      )}

      {/* Quality Gates */}
      {metadata && (metadata.quality_gates_passed || metadata.quality_gates_failed) && (
        <div className="p-3 bg-gray-50 rounded-lg">
          <p className="text-xs text-gray-500 mb-2">Quality Gates</p>
          <QualityGatesDisplay
            passed={metadata.quality_gates_passed}
            failed={metadata.quality_gates_failed}
          />
        </div>
      )}

      {showMetadata && metadata && (
        <Card className="bg-gray-50">
          <CardContent className="pt-4">
            <pre className="text-xs overflow-auto max-h-48">
              {JSON.stringify(metadata, null, 2)}
            </pre>
          </CardContent>
        </Card>
      )}

      {/* Events Summary */}
      <EventsSummary events={events} />

      {/* Brief content */}
      <div className={`prose prose-sm max-w-none ${isStreaming ? 'animate-pulse' : ''}`}>
        <ReactMarkdown
          components={{
            // Custom rendering for headings
            h1: ({ children }) => (
              <h1 className="text-2xl font-bold text-gray-900 border-b pb-2 mb-4">{children}</h1>
            ),
            h2: ({ children }) => (
              <h2 className="text-xl font-semibold text-gray-800 mt-6 mb-3 flex items-center gap-2">
                {children}
              </h2>
            ),
            h3: ({ children }) => (
              <h3 className="text-lg font-medium text-gray-700 mt-4 mb-2">{children}</h3>
            ),
            // Custom rendering for confidence indicators
            p: ({ children }) => {
              const text = String(children);
              // Check for confidence badges
              if (text.includes('HIGH CONFIDENCE')) {
                return <p className="my-2">{children}</p>;
              }
              return <p className="my-2 text-gray-700 leading-relaxed">{children}</p>;
            },
            // Style lists
            ul: ({ children }) => (
              <ul className="my-2 space-y-1 list-disc pl-5">{children}</ul>
            ),
            li: ({ children }) => (
              <li className="text-gray-700">{children}</li>
            ),
            // Style code/pre for audit sections
            code: ({ children }) => (
              <code className="bg-gray-100 px-1 py-0.5 rounded text-sm">{children}</code>
            ),
            // Style blockquotes
            blockquote: ({ children }) => (
              <blockquote className="border-l-4 border-pink-300 pl-4 italic text-gray-600 my-4">
                {children}
              </blockquote>
            ),
            // Style horizontal rules
            hr: () => <Separator className="my-6" />,
            // Style strong/bold with importance indicators
            strong: ({ children }) => {
              const text = String(children);
              if (text.includes('CRITICAL')) {
                return <strong className="text-red-600 font-bold">{children}</strong>;
              }
              if (text.includes('HIGH')) {
                return <strong className="text-orange-600 font-semibold">{children}</strong>;
              }
              return <strong className="font-semibold text-gray-900">{children}</strong>;
            },
          }}
        >
          {content}
        </ReactMarkdown>
        {isStreaming && (
          <span className="inline-block w-2 h-4 bg-pink-500 animate-pulse ml-1" />
        )}
      </div>
    </div>
  );
}

export function IntelligenceBrief({
  topic,
  profileId,
  // SIO state from parent
  isScanning,
  currentStage,
  stageProgress,
  overallProgress,
  briefContent,
  scanResult,
  error,
  articlesCollected,
  articlesScreened,
  eventsIdentified,
  eventsAnalyzed,
  currentEvent,
  // Config state
  hoursBack,
  maxEvents,
  credibilityThreshold,
  onHoursBackChange,
  onMaxEventsChange,
  onCredibilityThresholdChange,
  // Actions
  onClearError,
  onClearResults,
}: IntelligenceBriefProps) {
  const [showConfig, setShowConfig] = useState(false);

  return (
    <div className="space-y-6">
      {/* Header - title only, buttons are in App.tsx header */}
      <div>
        <h2 className="text-xl font-semibold text-gray-900 flex items-center gap-2">
          <Shield className="w-5 h-5 text-pink-500" />
          Strategic Intelligence Oracle
        </h2>
        <p className="text-sm text-gray-500 mt-1">
          24-hour news analysis with BBC/Wiley quality standards
        </p>
      </div>

      {/* Quick config toggle with clearer labels */}
      <div className="flex items-center gap-4 text-sm">
        <button
          onClick={() => setShowConfig(!showConfig)}
          className="text-gray-500 hover:text-gray-700 flex items-center gap-1"
        >
          {showConfig ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          Scan Settings
        </button>
        <span className="text-gray-400">|</span>
        <span className="text-gray-500">
          Lookback: {hoursBack}h · Max events: {maxEvents} · Min credibility: {credibilityThreshold}%
        </span>
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
            <div className="grid grid-cols-3 gap-4">
              <div>
                <label className="text-sm font-medium text-gray-700">Lookback Period (hours)</label>
                <p className="text-xs text-gray-400 mb-1">How far back to search for news</p>
                <input
                  type="number"
                  value={hoursBack}
                  onChange={(e) => onHoursBackChange(Number(e.target.value))}
                  min={1}
                  max={168}
                  className="mt-1 w-full px-3 py-2 border rounded-md text-sm"
                />
              </div>
              <div>
                <label className="text-sm font-medium text-gray-700">Events to Analyze</label>
                <p className="text-xs text-gray-400 mb-1">Top N events for deep analysis</p>
                <input
                  type="number"
                  value={maxEvents}
                  onChange={(e) => onMaxEventsChange(Number(e.target.value))}
                  min={5}
                  max={100}
                  className="mt-1 w-full px-3 py-2 border rounded-md text-sm"
                />
              </div>
              <div>
                <label className="text-sm font-medium text-gray-700">Minimum Credibility (%)</label>
                <p className="text-xs text-gray-400 mb-1">Filter out low-quality sources</p>
                <input
                  type="number"
                  value={credibilityThreshold}
                  onChange={(e) => onCredibilityThresholdChange(Number(e.target.value))}
                  min={0}
                  max={100}
                  className="mt-1 w-full px-3 py-2 border rounded-md text-sm"
                />
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Error display */}
      {error && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>Scan Error</AlertTitle>
          <AlertDescription className="flex items-center justify-between">
            {error}
            <Button variant="ghost" size="sm" onClick={onClearError}>
              Dismiss
            </Button>
          </AlertDescription>
        </Alert>
      )}

      {/* Scanning progress */}
      {isScanning && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg flex items-center gap-2">
              <Loader2 className="w-5 h-5 animate-spin text-pink-500" />
              Scanning Intelligence Sources...
            </CardTitle>
            <CardDescription>
              {SIO_STAGES.find(s => s.name === currentStage)?.description || 'Initializing...'}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <StageIndicator
              stages={SIO_STAGES}
              currentStage={currentStage}
              stageProgress={stageProgress}
            />
            <Progress value={overallProgress * 100} className="h-2 mb-4" />
            <ScanStats
              articlesCollected={articlesCollected}
              articlesScreened={articlesScreened}
              eventsIdentified={eventsIdentified}
              eventsAnalyzed={eventsAnalyzed}
              currentEvent={currentEvent}
            />
          </CardContent>
        </Card>
      )}

      {/* Brief display */}
      <Card>
        <CardContent className="pt-6">
          <BriefDisplay
            content={briefContent}
            metadata={scanResult?.metadata}
            events={scanResult?.events}
            isStreaming={isScanning && currentStage === 'synthesis'}
          />
        </CardContent>
      </Card>

      {/* Clear results button */}
      {scanResult && !isScanning && (
        <div className="flex justify-end">
          <Button variant="ghost" size="sm" onClick={onClearResults}>
            Clear Results
          </Button>
        </div>
      )}
    </div>
  );
}

export default IntelligenceBrief;
