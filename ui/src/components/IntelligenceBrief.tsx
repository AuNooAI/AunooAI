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
  FileText,
  Target,
  Lightbulb,
  Calendar,
  ArrowRight,
  AlertOctagon,
  Sparkles
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
import remarkGfm from 'remark-gfm';

interface SIOArticle {
  id: number;
  title: string;
  uri: string;
  source: string;
  published_at?: string;
  credibility_score?: number;
  summary?: string;
}

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
  // Articles for references
  articles?: SIOArticle[];
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

// Article References Section
function ArticleReferencesSection({ articles }: { articles?: SIOArticle[] }) {
  const [expanded, setExpanded] = useState(false);

  if (!articles?.length) return null;

  const displayArticles = expanded ? articles : articles.slice(0, 10);

  return (
    <Card className="mt-6 border-gray-200">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm flex items-center gap-2">
          <FileText className="w-4 h-4 text-pink-500" />
          Source Articles ({articles.length})
        </CardTitle>
        <CardDescription className="text-xs">
          Articles analyzed for this intelligence brief
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="space-y-2 max-h-[400px] overflow-y-auto">
          {displayArticles.map((article, idx) => (
            <div key={article.id || idx} className="p-2 border rounded-lg hover:bg-gray-50 text-sm">
              <div className="flex items-start justify-between gap-2">
                <div className="flex-1 min-w-0">
                  {article.uri ? (
                    <a
                      href={article.uri}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="font-medium text-blue-600 hover:underline block truncate"
                    >
                      {idx + 1}. {article.title}
                    </a>
                  ) : (
                    <span className="font-medium text-gray-800 block truncate">
                      {idx + 1}. {article.title}
                    </span>
                  )}
                  <div className="flex items-center gap-2 mt-1 text-xs text-gray-500">
                    <span>{article.source}</span>
                    {article.credibility_score !== undefined && (
                      <span className={`px-1.5 py-0.5 rounded ${
                        article.credibility_score >= 80 ? 'bg-green-100 text-green-700' :
                        article.credibility_score >= 60 ? 'bg-yellow-100 text-yellow-700' :
                        'bg-red-100 text-red-700'
                      }`}>
                        {article.credibility_score}%
                      </span>
                    )}
                    {article.published_at && (
                      <span>{new Date(article.published_at).toLocaleDateString()}</span>
                    )}
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
        {articles.length > 10 && (
          <Button
            variant="ghost"
            size="sm"
            className="mt-2 w-full"
            onClick={() => setExpanded(!expanded)}
          >
            {expanded ? 'Show Less' : `Show ${articles.length - 10} More`}
          </Button>
        )}
      </CardContent>
    </Card>
  );
}

// Card component for Threat/Opportunity items
function ThreatOpportunityCard({
  type,
  title,
  description,
  confidence,
  timeframe
}: {
  type: 'threat' | 'opportunity';
  title: string;
  description: string;
  confidence?: string;
  timeframe?: string;
}) {
  const isThreat = type === 'threat';
  return (
    <div className={`p-4 rounded-lg border-l-4 ${
      isThreat
        ? 'bg-red-50 border-red-500'
        : 'bg-green-50 border-green-500'
    }`}>
      <div className="flex items-start gap-3">
        <div className={`p-2 rounded-full ${isThreat ? 'bg-red-100' : 'bg-green-100'}`}>
          {isThreat
            ? <AlertOctagon className="w-5 h-5 text-red-600" />
            : <Sparkles className="w-5 h-5 text-green-600" />
          }
        </div>
        <div className="flex-1">
          <div className="flex items-center justify-between">
            <h4 className={`font-semibold ${isThreat ? 'text-red-800' : 'text-green-800'}`}>
              {title}
            </h4>
            <div className="flex gap-2">
              {confidence && (
                <Badge variant="outline" className={isThreat ? 'border-red-300 text-red-700' : 'border-green-300 text-green-700'}>
                  {confidence}
                </Badge>
              )}
              {timeframe && (
                <Badge variant="outline" className="border-gray-300 text-gray-600">
                  <Clock className="w-3 h-3 mr-1" />
                  {timeframe}
                </Badge>
              )}
            </div>
          </div>
          <p className={`mt-2 text-sm ${isThreat ? 'text-red-700' : 'text-green-700'}`}>
            {description}
          </p>
        </div>
      </div>
    </div>
  );
}

// Card component for Implications
function ImplicationCard({
  category,
  content,
  icon
}: {
  category: string;
  content: string;
  icon?: 'strategic' | 'operational' | 'tactical' | 'default';
}) {
  const iconMap = {
    strategic: <Target className="w-5 h-5 text-purple-600" />,
    operational: <Zap className="w-5 h-5 text-blue-600" />,
    tactical: <ArrowRight className="w-5 h-5 text-orange-600" />,
    default: <Lightbulb className="w-5 h-5 text-amber-600" />
  };

  const bgMap = {
    strategic: 'bg-purple-50 border-purple-200',
    operational: 'bg-blue-50 border-blue-200',
    tactical: 'bg-orange-50 border-orange-200',
    default: 'bg-amber-50 border-amber-200'
  };

  const iconType = icon || 'default';

  return (
    <div className={`p-4 rounded-lg border ${bgMap[iconType]}`}>
      <div className="flex items-start gap-3">
        <div className="p-2 rounded-full bg-white shadow-sm">
          {iconMap[iconType]}
        </div>
        <div className="flex-1">
          <h4 className="font-semibold text-gray-800 mb-1">{category}</h4>
          <p className="text-sm text-gray-700">{content}</p>
        </div>
      </div>
    </div>
  );
}

// Timeline component for Recommended Actions
function ActionTimeline({
  actions
}: {
  actions: Array<{
    title: string;
    description: string;
    timeframe?: string;
    priority?: 'immediate' | 'short-term' | 'medium-term' | 'long-term';
  }>;
}) {
  const priorityColors = {
    immediate: 'bg-red-500',
    'short-term': 'bg-orange-500',
    'medium-term': 'bg-blue-500',
    'long-term': 'bg-gray-500'
  };

  const priorityLabels = {
    immediate: 'Immediate',
    'short-term': 'Short-term',
    'medium-term': 'Medium-term',
    'long-term': 'Long-term'
  };

  return (
    <div className="relative pl-8 space-y-6">
      {/* Vertical line */}
      <div className="absolute left-3 top-2 bottom-2 w-0.5 bg-gradient-to-b from-pink-500 via-purple-500 to-blue-500" />

      {actions.map((action, index) => (
        <div key={index} className="relative">
          {/* Timeline dot */}
          <div className={`absolute -left-5 w-4 h-4 rounded-full border-2 border-white shadow-md ${
            priorityColors[action.priority || 'medium-term']
          }`} />

          <div className="bg-white border border-gray-200 rounded-lg p-4 shadow-sm hover:shadow-md transition-shadow">
            <div className="flex items-center justify-between mb-2">
              <h4 className="font-semibold text-gray-900">{action.title}</h4>
              <div className="flex gap-2">
                {action.priority && (
                  <Badge className={`${priorityColors[action.priority]} text-white text-xs`}>
                    {priorityLabels[action.priority]}
                  </Badge>
                )}
                {action.timeframe && (
                  <Badge variant="outline" className="text-xs">
                    <Calendar className="w-3 h-3 mr-1" />
                    {action.timeframe}
                  </Badge>
                )}
              </div>
            </div>
            <p className="text-sm text-gray-600">{action.description}</p>
          </div>
        </div>
      ))}
    </div>
  );
}

// Enhanced section renderer that detects special sections and renders with cards/timeline
function EnhancedSectionRenderer({ content }: { content: string }) {
  // Split content by ## headings to identify sections
  const sections = content.split(/(?=^## )/m);

  return (
    <>
      {sections.map((section, idx) => {
        const headerMatch = section.match(/^## (.+?)[\r\n]/);
        const headerText = headerMatch ? headerMatch[1].toUpperCase() : '';

        // Check if this is a Threat & Opportunity Analysis section
        if (headerText.includes('THREAT') && headerText.includes('OPPORTUNIT')) {
          return <ThreatOpportunitySection key={idx} content={section} />;
        }

        // Check if this is a Recommended Actions section
        if (headerText.includes('RECOMMENDED ACTION') || headerText.includes('PRIORITY ACTION')) {
          return <RecommendedActionsSection key={idx} content={section} />;
        }

        // Check if this section contains "Implications" subsections
        if (section.includes('### ') && section.toLowerCase().includes('implication')) {
          return <ImplicationsSection key={idx} content={section} />;
        }

        // Default: render normally with ReactMarkdown
        return (
          <ReactMarkdown
            key={idx}
            remarkPlugins={[remarkGfm]}
            components={defaultMarkdownComponents}
          >
            {section}
          </ReactMarkdown>
        );
      })}
    </>
  );
}

// Render Threat & Opportunity section as two-column cards (like Strategic Recommendations)
function ThreatOpportunitySection({ content }: { content: string }) {
  // Split into ### subsections
  const subsections = content.split(/(?=^### )/m);

  // Extract header
  const headerMatch = content.match(/^(## .+?)[\r\n]/);
  const header = headerMatch ? headerMatch[1].replace('## ', '') : 'Threat & Opportunity Analysis';

  // Parse threats and opportunities from subsections
  let threatsContent = '';
  let opportunitiesContent = '';

  for (const sub of subsections) {
    if (/^### .*threat/i.test(sub)) {
      threatsContent = sub.replace(/^### .+?[\r\n]/, '').trim();
    } else if (/^### .*opportunit/i.test(sub)) {
      opportunitiesContent = sub.replace(/^### .+?[\r\n]/, '').trim();
    }
  }

  // Parse individual items from content
  const parseItems = (text: string): Array<{ name: string; details: string[] }> => {
    const items: Array<{ name: string; details: string[] }> = [];
    // Match **THREAT 1: Name** or **OPPORTUNITY 1: Name** patterns
    const itemRegex = /\*\*(?:THREAT|OPPORTUNITY)\s*\d*:?\s*(.+?)\*\*/gi;
    const matches = text.split(itemRegex);

    for (let i = 1; i < matches.length; i += 2) {
      const name = matches[i]?.trim() || '';
      const detailsText = matches[i + 1] || '';
      // Extract bullet points
      const details = detailsText
        .split(/\n/)
        .filter(line => line.trim().startsWith('-') || line.trim().startsWith('*'))
        .map(line => line.replace(/^[\s-*]+/, '').trim())
        .filter(Boolean);
      if (name) {
        items.push({ name, details });
      }
    }
    return items;
  };

  const threats = parseItems(threatsContent);
  const opportunities = parseItems(opportunitiesContent);

  // If we couldn't parse structured items, fall back to default rendering
  if (threats.length === 0 && opportunities.length === 0) {
    return (
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={defaultMarkdownComponents}>
        {content}
      </ReactMarkdown>
    );
  }

  return (
    <div className="my-8">
      <h2 className="text-xl font-bold text-gray-800 mb-6 pb-2 border-b border-gray-200 flex items-center gap-2">
        <Target className="w-5 h-5 text-pink-500" />
        {header}
      </h2>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Threats Column */}
        <div className="bg-white border border-gray-200 rounded-lg overflow-hidden shadow-sm">
          <div className="bg-red-50 p-4 border-b border-red-100">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-full bg-red-100 flex items-center justify-center">
                <AlertOctagon className="w-4 h-4 text-red-700" />
              </div>
              <h3 className="font-bold text-sm text-gray-900">IDENTIFIED THREATS</h3>
            </div>
          </div>
          <div className="p-4 space-y-4">
            {threats.length > 0 ? threats.map((threat, idx) => (
              <div key={idx} className="border-l-2 border-red-300 pl-3">
                <p className="font-semibold text-red-800 text-sm">{threat.name}</p>
                {threat.details.length > 0 && (
                  <ul className="mt-1 space-y-1">
                    {threat.details.map((detail, dIdx) => (
                      <li key={dIdx} className="text-xs text-gray-600 flex gap-1">
                        <span className="text-red-400">•</span>
                        <span>{detail}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )) : (
              <p className="text-sm text-gray-500 italic">No threats identified</p>
            )}
          </div>
        </div>

        {/* Opportunities Column */}
        <div className="bg-white border border-gray-200 rounded-lg overflow-hidden shadow-sm">
          <div className="bg-green-50 p-4 border-b border-green-100">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-full bg-green-100 flex items-center justify-center">
                <Sparkles className="w-4 h-4 text-green-700" />
              </div>
              <h3 className="font-bold text-sm text-gray-900">IDENTIFIED OPPORTUNITIES</h3>
            </div>
          </div>
          <div className="p-4 space-y-4">
            {opportunities.length > 0 ? opportunities.map((opp, idx) => (
              <div key={idx} className="border-l-2 border-green-300 pl-3">
                <p className="font-semibold text-green-800 text-sm">{opp.name}</p>
                {opp.details.length > 0 && (
                  <ul className="mt-1 space-y-1">
                    {opp.details.map((detail, dIdx) => (
                      <li key={dIdx} className="text-xs text-gray-600 flex gap-1">
                        <span className="text-green-400">•</span>
                        <span>{detail}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )) : (
              <p className="text-sm text-gray-500 italic">No opportunities identified</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// Render Recommended Actions section as 3-column timeframe cards (like Strategic Recommendations)
function RecommendedActionsSection({ content }: { content: string }) {
  // Split into ### subsections
  const subsections = content.split(/(?=^### )/m);

  // Extract header
  const headerMatch = content.match(/^(## .+?)[\r\n]/);
  const header = headerMatch ? headerMatch[1].replace('## ', '') : 'Recommended Actions';

  // Parse actions by timeframe
  const timeframes: { [key: string]: { label: string; timeframe: string; actions: Array<{ text: string; owner?: string }> } } = {
    immediate: { label: 'IMMEDIATE', timeframe: '0-48 hours', actions: [] },
    nearterm: { label: 'NEAR-TERM', timeframe: '1-2 weeks', actions: [] },
    strategic: { label: 'STRATEGIC', timeframe: '1-3 months', actions: [] }
  };

  for (const sub of subsections) {
    const subHeaderMatch = sub.match(/^### (.+?)[\r\n]/);
    if (!subHeaderMatch) continue;

    const subHeader = subHeaderMatch[1].toLowerCase();
    let targetKey = '';

    if (/immediate|0-48|48.hour|today|urgent/i.test(subHeader)) {
      targetKey = 'immediate';
      // Extract timeframe from header if present
      const tfMatch = subHeader.match(/\(([^)]+)\)/);
      if (tfMatch) timeframes.immediate.timeframe = tfMatch[1];
    } else if (/near.term|1-2 week|week|short/i.test(subHeader)) {
      targetKey = 'nearterm';
      const tfMatch = subHeader.match(/\(([^)]+)\)/);
      if (tfMatch) timeframes.nearterm.timeframe = tfMatch[1];
    } else if (/strategic|long|1-3 month|month|quarter/i.test(subHeader)) {
      targetKey = 'strategic';
      const tfMatch = subHeader.match(/\(([^)]+)\)/);
      if (tfMatch) timeframes.strategic.timeframe = tfMatch[1];
    }

    if (targetKey) {
      // Parse action items (checkbox format: - [ ] **Action** - Rationale - Owner: Function)
      const lines = sub.split('\n');
      for (const line of lines) {
        // Match checkbox items: - [ ] **Action** or - **Action**
        const actionMatch = line.match(/^[-*]\s*(?:\[[ x]?\])?\s*\*?\*?(.+?)\*?\*?\s*(?:[-–]|$)/);
        if (actionMatch) {
          let text = actionMatch[1].trim();
          // Extract owner if present
          const ownerMatch = line.match(/Owner:\s*(\w+)/i);
          const owner = ownerMatch ? ownerMatch[1] : undefined;
          // Clean up the text
          text = text.replace(/[-–]\s*Owner:\s*\w+/i, '').replace(/[-–]\s*$/, '').trim();
          if (text) {
            timeframes[targetKey].actions.push({ text, owner });
          }
        }
      }
    }
  }

  // If we couldn't parse any actions, fall back to default rendering
  const hasActions = Object.values(timeframes).some(tf => tf.actions.length > 0);
  if (!hasActions) {
    return (
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={defaultMarkdownComponents}>
        {content}
      </ReactMarkdown>
    );
  }

  return (
    <div className="my-8">
      <h2 className="text-xl font-bold text-gray-800 mb-6 pb-2 border-b border-gray-200 flex items-center gap-2">
        <Calendar className="w-5 h-5 text-pink-500" />
        {header}
      </h2>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Immediate Actions */}
        <div className="bg-white border border-gray-200 rounded-lg overflow-hidden shadow-sm hover:shadow-md transition-shadow">
          <div className="bg-red-50 p-4 border-b border-red-100">
            <div className="flex items-center gap-2 mb-1">
              <div className="w-8 h-8 rounded-full bg-red-100 flex items-center justify-center">
                <Zap className="w-4 h-4 text-red-700" />
              </div>
              <h3 className="font-bold text-sm text-gray-900">{timeframes.immediate.label}</h3>
            </div>
            <div className="text-xs font-medium text-gray-600">{timeframes.immediate.timeframe}</div>
          </div>
          <div className="p-4">
            {timeframes.immediate.actions.length > 0 ? (
              <ul className="space-y-3">
                {timeframes.immediate.actions.map((action, idx) => (
                  <li key={idx} className="text-sm text-gray-700 flex gap-2">
                    <span className="text-red-500 font-bold">•</span>
                    <span>{action.text}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-gray-400 italic">No immediate actions</p>
            )}
          </div>
        </div>

        {/* Near-term Actions */}
        <div className="bg-white border border-gray-200 rounded-lg overflow-hidden shadow-sm hover:shadow-md transition-shadow">
          <div className="bg-amber-50 p-4 border-b border-amber-100">
            <div className="flex items-center gap-2 mb-1">
              <div className="w-8 h-8 rounded-full bg-amber-100 flex items-center justify-center">
                <Clock className="w-4 h-4 text-amber-700" />
              </div>
              <h3 className="font-bold text-sm text-gray-900">{timeframes.nearterm.label}</h3>
            </div>
            <div className="text-xs font-medium text-gray-600">{timeframes.nearterm.timeframe}</div>
          </div>
          <div className="p-4">
            {timeframes.nearterm.actions.length > 0 ? (
              <ul className="space-y-3">
                {timeframes.nearterm.actions.map((action, idx) => (
                  <li key={idx} className="text-sm text-gray-700 flex gap-2">
                    <span className="text-amber-500 font-bold">•</span>
                    <span>{action.text}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-gray-400 italic">No near-term actions</p>
            )}
          </div>
        </div>

        {/* Strategic Actions */}
        <div className="bg-white border border-gray-200 rounded-lg overflow-hidden shadow-sm hover:shadow-md transition-shadow">
          <div className="bg-purple-50 p-4 border-b border-purple-100">
            <div className="flex items-center gap-2 mb-1">
              <div className="w-8 h-8 rounded-full bg-purple-100 flex items-center justify-center">
                <Target className="w-4 h-4 text-purple-700" />
              </div>
              <h3 className="font-bold text-sm text-gray-900">{timeframes.strategic.label}</h3>
            </div>
            <div className="text-xs font-medium text-gray-600">{timeframes.strategic.timeframe}</div>
          </div>
          <div className="p-4">
            {timeframes.strategic.actions.length > 0 ? (
              <ul className="space-y-3">
                {timeframes.strategic.actions.map((action, idx) => (
                  <li key={idx} className="text-sm text-gray-700 flex gap-2">
                    <span className="text-purple-500 font-bold">•</span>
                    <span>{action.text}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-gray-400 italic">No strategic actions</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// Render Implications as cards
function ImplicationsSection({ content }: { content: string }) {
  // Parse implication subsections
  const subsections = content.split(/(?=^### )/m);
  const implications: Array<{ category: string; content: string; icon: 'strategic' | 'operational' | 'tactical' | 'default' }> = [];

  // Extract main header
  const headerMatch = content.match(/^(## .+?)[\r\n]/);
  const header = headerMatch ? headerMatch[1].replace('## ', '') : 'Implications';

  for (const sub of subsections) {
    const subHeaderMatch = sub.match(/^### (.+?)[\r\n]/);
    if (subHeaderMatch && subHeaderMatch[1].toLowerCase().includes('implication')) {
      const category = subHeaderMatch[1].replace(/implications?:?\s*/i, '').trim();
      const contentText = sub.replace(/^### .+?[\r\n]/, '').trim();

      // Determine icon based on category
      let icon: 'strategic' | 'operational' | 'tactical' | 'default' = 'default';
      if (/strategic|strategy|long.term/i.test(category)) icon = 'strategic';
      else if (/operational|operation|process/i.test(category)) icon = 'operational';
      else if (/tactical|immediate|action/i.test(category)) icon = 'tactical';

      implications.push({ category, content: contentText, icon });
    }
  }

  // If we couldn't parse structured items, fall back to default rendering
  if (implications.length === 0) {
    return (
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={defaultMarkdownComponents}>
        {content}
      </ReactMarkdown>
    );
  }

  return (
    <div className="my-8">
      <h2 className="text-xl font-bold text-gray-800 mb-4 pb-2 border-b border-gray-200 flex items-center gap-2">
        <Lightbulb className="w-5 h-5 text-amber-500" />
        {header}
      </h2>
      <div className="grid gap-4 md:grid-cols-2">
        {implications.map((impl, idx) => (
          <ImplicationCard
            key={idx}
            category={impl.category}
            content={impl.content}
            icon={impl.icon}
          />
        ))}
      </div>
    </div>
  );
}

// Default markdown components for sections that don't need special rendering
const defaultMarkdownComponents = {
  h1: ({ children }: any) => (
    <h1 className="text-2xl font-bold text-gray-900 border-b-2 border-pink-500 pb-2 mb-6">{children}</h1>
  ),
  h2: ({ children }: any) => (
    <h2 className="text-xl font-bold text-gray-800 mt-8 mb-4 pb-2 border-b border-gray-200">{children}</h2>
  ),
  h3: ({ children }: any) => (
    <h3 className="text-lg font-semibold text-gray-700 mt-6 mb-3">{children}</h3>
  ),
  h4: ({ children }: any) => (
    <h4 className="text-base font-semibold text-gray-600 mt-4 mb-2">{children}</h4>
  ),
  p: ({ children }: any) => (
    <p className="my-3 text-gray-700 leading-relaxed">{children}</p>
  ),
  ul: ({ children }: any) => (
    <ul className="my-3 space-y-2 list-disc pl-5 text-gray-700">{children}</ul>
  ),
  ol: ({ children }: any) => (
    <ol className="my-3 space-y-2 list-decimal pl-5 text-gray-700">{children}</ol>
  ),
  li: ({ children }: any) => (
    <li className="text-gray-700 leading-relaxed">{children}</li>
  ),
  table: ({ children }: any) => (
    <div className="my-6 overflow-x-auto rounded-lg border border-gray-300 shadow-sm">
      <table className="min-w-full divide-y divide-gray-300">{children}</table>
    </div>
  ),
  thead: ({ children }: any) => (
    <thead className="bg-pink-500 text-white">{children}</thead>
  ),
  tbody: ({ children }: any) => (
    <tbody className="bg-white divide-y divide-gray-200">{children}</tbody>
  ),
  tr: ({ children }: any) => (
    <tr className="hover:bg-pink-50 transition-colors">{children}</tr>
  ),
  th: ({ children }: any) => (
    <th className="px-4 py-3 text-left text-xs font-bold uppercase tracking-wider text-white">{children}</th>
  ),
  td: ({ children }: any) => (
    <td className="px-4 py-3 text-sm text-gray-700 whitespace-normal">{children}</td>
  ),
  code: ({ children }: any) => (
    <code className="bg-gray-100 text-gray-800 px-1.5 py-0.5 rounded text-sm font-mono border border-gray-200">{children}</code>
  ),
  pre: ({ children }: any) => (
    <pre className="bg-gray-800 text-gray-100 p-4 rounded-lg overflow-x-auto my-4 text-sm">{children}</pre>
  ),
  blockquote: ({ children }: any) => (
    <blockquote className="border-l-4 border-pink-500 bg-pink-50 pl-4 pr-4 py-3 italic text-gray-700 my-4 rounded-r-lg">{children}</blockquote>
  ),
  hr: () => <hr className="my-8 border-t-2 border-gray-200" />,
  strong: ({ children }: any) => {
    const text = String(children);
    if (text.includes('CRITICAL') || text.includes('THREAT')) {
      return <strong className="text-red-600 font-bold bg-red-50 px-1 rounded">{children}</strong>;
    }
    if (text.includes('HIGH') || text.includes('OPPORTUNITY')) {
      return <strong className="text-orange-600 font-bold bg-orange-50 px-1 rounded">{children}</strong>;
    }
    if (text.includes('MEDIUM') || text.includes('MODERATE')) {
      return <strong className="text-yellow-700 font-bold bg-yellow-50 px-1 rounded">{children}</strong>;
    }
    if (text.includes('LOW') || text.includes('WATCH')) {
      return <strong className="text-blue-600 font-semibold">{children}</strong>;
    }
    return <strong className="font-bold text-gray-900">{children}</strong>;
  },
  em: ({ children }: any) => (
    <em className="text-gray-600 italic">{children}</em>
  ),
  a: ({ children, href }: any) => (
    <a href={href} className="text-pink-600 hover:text-pink-800 underline font-medium" target="_blank" rel="noopener noreferrer">{children}</a>
  ),
};

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
        <p className="text-sm mt-2">Click the refresh button to generate a strategic intelligence briefing.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Metadata summary - pink accent styling to match app theme */}
      {metadata && (
        <div className="flex items-center justify-between bg-gradient-to-r from-pink-50 to-pink-100 border border-pink-200 p-4 rounded-lg">
          <div className="flex items-center gap-6 text-sm text-gray-700">
            <span className="flex items-center gap-2">
              <Search className="w-4 h-4 text-pink-500" />
              <span className="font-medium">{metadata.articles_collected}</span> articles
            </span>
            <span className="flex items-center gap-2">
              <Zap className="w-4 h-4 text-amber-500" />
              <span className="font-medium">{metadata.events_analyzed}</span> events
            </span>
            {metadata.generated_at && (
              <span className="flex items-center gap-2">
                <Clock className="w-4 h-4 text-blue-500" />
                {new Date(metadata.generated_at).toLocaleString()}
              </span>
            )}
          </div>
          <Button
            variant="ghost"
            size="sm"
            className="text-pink-600 hover:bg-pink-200"
            onClick={() => setShowMetadata(!showMetadata)}
          >
            {showMetadata ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
            Details
          </Button>
        </div>
      )}

      {/* Quality Gates */}
      {metadata && (metadata.quality_gates_passed || metadata.quality_gates_failed) && (
        <div className="p-3 bg-gray-50 rounded-lg border border-gray-200">
          <p className="text-xs font-semibold text-gray-600 mb-2 uppercase tracking-wide">Quality Gates</p>
          <QualityGatesDisplay
            passed={metadata.quality_gates_passed}
            failed={metadata.quality_gates_failed}
          />
        </div>
      )}

      {showMetadata && metadata && (
        <Card className="bg-gray-50 border-gray-200">
          <CardContent className="pt-4">
            <pre className="text-xs overflow-auto max-h-48 text-gray-700">
              {JSON.stringify(metadata, null, 2)}
            </pre>
          </CardContent>
        </Card>
      )}

      {/* Events Summary */}
      <EventsSummary events={events} />

      {/* Brief content - enhanced rendering with cards and timeline for special sections */}
      <div className={`prose prose-gray prose-sm max-w-none ${isStreaming ? 'animate-pulse' : ''}`}>
        <EnhancedSectionRenderer content={content} />
        {isStreaming && (
          <span className="inline-block w-2 h-5 bg-pink-500 animate-pulse ml-1" />
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
  // Articles for references
  articles,
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
          Situation Assessment
        </h2>
        <p className="text-sm text-gray-500 mt-1">
          24-hour strategic intelligence scan with quality-verified sources
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
      <Card className="border-gray-200 shadow-md">
        <CardContent className="pt-6 bg-gradient-to-b from-white to-gray-50">
          <BriefDisplay
            content={briefContent}
            metadata={scanResult?.metadata}
            events={scanResult?.events}
            isStreaming={isScanning && currentStage === 'synthesis'}
          />
        </CardContent>
      </Card>

      {/* Article References Section */}
      {!isScanning && articles && articles.length > 0 && (
        <ArticleReferencesSection articles={articles} />
      )}

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
