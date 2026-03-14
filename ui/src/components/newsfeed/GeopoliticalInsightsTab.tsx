/**
 * GeopoliticalInsightsTab Component
 * Enhanced with rich section cards, markdown rendering, and key metrics
 * Matching the quality of PolicyInsightsTab
 */

import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import {
  Sparkles,
  Loader2,
  AlertCircle,
  Clock,
  FileText,
  ChevronDown,
  ChevronUp,
  Download,
  Globe,
  AlertTriangle,
  TrendingUp,
  Map,
  ChevronRight,
  Zap,
  Users,
  Target,
  Flag,
  Eye,
  BarChart3,
  Calendar,
  Tag,
  Bot,
  Lightbulb,
  BookOpen,
  Shield,
  Flame,
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { OverviewStats, Hotspot, RiskLevel } from '../../services/geopoliticalHotspotsApi';
import { RISK_COLORS } from '../../services/geopoliticalHotspotsApi';

interface Narrative {
  id: number;
  narrative_text: string;
  executive_summary: string | null;
  regional_analysis: string | null;
  emerging_threats: string | null;
  outlook: string | null;
  hotspot_count: number;
  article_count: number;
  top_regions: string[] | null;
  top_categories: string[] | null;
  risk_breakdown: Record<string, number> | null;
  model_used: string | null;
  topic: string | null;
  generated_at: string | null;
}

interface NarrativeSummary {
  id: number;
  executive_summary: string | null;
  hotspot_count: number;
  article_count: number;
  model_used: string | null;
  topic: string | null;
  generated_at: string | null;
}

interface GeopoliticalInsightsTabProps {
  stats: OverviewStats | null;
  hotspots: Hotspot[];
  loading: boolean;
  model?: string;
}

// Section configuration with icons and colors
const SECTION_CONFIG: Record<string, { icon: typeof TrendingUp; color: string; bgColor: string; borderColor: string }> = {
  'Executive Summary': { icon: BookOpen, color: 'text-blue-600 dark:text-blue-400', bgColor: 'bg-blue-50 dark:bg-blue-900/20', borderColor: 'border-blue-200 dark:border-blue-800' },
  'Summary': { icon: BookOpen, color: 'text-blue-600 dark:text-blue-400', bgColor: 'bg-blue-50 dark:bg-blue-900/20', borderColor: 'border-blue-200 dark:border-blue-800' },
  'Regional Analysis': { icon: Globe, color: 'text-cyan-600 dark:text-cyan-400', bgColor: 'bg-cyan-50 dark:bg-cyan-900/20', borderColor: 'border-cyan-200 dark:border-cyan-800' },
  'Regional': { icon: Globe, color: 'text-cyan-600 dark:text-cyan-400', bgColor: 'bg-cyan-50 dark:bg-cyan-900/20', borderColor: 'border-cyan-200 dark:border-cyan-800' },
  'Emerging Threats': { icon: AlertTriangle, color: 'text-amber-600 dark:text-amber-400', bgColor: 'bg-amber-50 dark:bg-amber-900/20', borderColor: 'border-amber-200 dark:border-amber-800' },
  'Threats': { icon: AlertTriangle, color: 'text-amber-600 dark:text-amber-400', bgColor: 'bg-amber-50 dark:bg-amber-900/20', borderColor: 'border-amber-200 dark:border-amber-800' },
  'Strategic Outlook': { icon: TrendingUp, color: 'text-emerald-600 dark:text-emerald-400', bgColor: 'bg-emerald-50 dark:bg-emerald-900/20', borderColor: 'border-emerald-200 dark:border-emerald-800' },
  'Outlook': { icon: TrendingUp, color: 'text-emerald-600 dark:text-emerald-400', bgColor: 'bg-emerald-50 dark:bg-emerald-900/20', borderColor: 'border-emerald-200 dark:border-emerald-800' },
  'Priority Areas': { icon: Target, color: 'text-red-600 dark:text-red-400', bgColor: 'bg-red-50 dark:bg-red-900/20', borderColor: 'border-red-200 dark:border-red-800' },
  'Priority': { icon: Target, color: 'text-red-600 dark:text-red-400', bgColor: 'bg-red-50 dark:bg-red-900/20', borderColor: 'border-red-200 dark:border-red-800' },
  'Key Actors': { icon: Users, color: 'text-indigo-600 dark:text-indigo-400', bgColor: 'bg-indigo-50 dark:bg-indigo-900/20', borderColor: 'border-indigo-200 dark:border-indigo-800' },
  'Escalation Assessment': { icon: Flame, color: 'text-orange-600 dark:text-orange-400', bgColor: 'bg-orange-50 dark:bg-orange-900/20', borderColor: 'border-orange-200 dark:border-orange-800' },
  'Risk Assessment': { icon: Shield, color: 'text-rose-600 dark:text-rose-400', bgColor: 'bg-rose-50 dark:bg-rose-900/20', borderColor: 'border-rose-200 dark:border-rose-800' },
  'Recommendations': { icon: Flag, color: 'text-violet-600 dark:text-violet-400', bgColor: 'bg-violet-50 dark:bg-violet-900/20', borderColor: 'border-violet-200 dark:border-violet-800' },
  'Watchlist': { icon: Eye, color: 'text-pink-600 dark:text-pink-400', bgColor: 'bg-pink-50 dark:bg-pink-900/20', borderColor: 'border-pink-200 dark:border-pink-800' },
  'Forward-Looking Insights': { icon: Lightbulb, color: 'text-yellow-600 dark:text-yellow-400', bgColor: 'bg-yellow-50 dark:bg-yellow-900/20', borderColor: 'border-yellow-200 dark:border-yellow-800' },
};

// Get section config with fallback
function getSectionConfig(title: string) {
  if (SECTION_CONFIG[title]) {
    return SECTION_CONFIG[title];
  }
  for (const [key, config] of Object.entries(SECTION_CONFIG)) {
    if (title.toLowerCase().includes(key.toLowerCase()) || key.toLowerCase().includes(title.toLowerCase())) {
      return config;
    }
  }
  return {
    icon: Zap,
    color: 'text-gray-600 dark:text-gray-300',
    bgColor: 'bg-gray-50 dark:bg-gray-800',
    borderColor: 'border-gray-200 dark:border-gray-700'
  };
}

// AI Disclosure Footer Component
function AIDisclosureFooter({
  modelUsed,
  generatedAt,
}: {
  modelUsed: string;
  generatedAt: string;
}) {
  const userName = (window as any).userSession?.username;
  const userEmail = (window as any).userSession?.email;

  let authorText = 'Aunoo AI';
  if (userName) {
    authorText += ` with ${userName}`;
    if (userEmail) {
      authorText += ` (${userEmail})`;
    }
  }

  const formattedDate = new Date(generatedAt).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  });

  return (
    <div className="mt-6 pt-4 border-t border-gray-200 dark:border-gray-700">
      <div className="bg-gray-50 dark:bg-gray-750 border border-gray-200 dark:border-gray-600 rounded-lg p-4">
        <div className="flex items-center gap-2 mb-3">
          <Bot className="w-4 h-4 text-gray-500 dark:text-gray-300" />
          <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300">
            AI Technology Disclosure
          </h4>
        </div>
        <div className="text-xs text-gray-600 dark:text-gray-300 space-y-1.5">
          <p>
            <span className="font-semibold text-gray-700 dark:text-gray-300">Report:</span> Strategic Intelligence Briefing
            <span className="mx-2">|</span>
            <span className="font-semibold text-gray-700 dark:text-gray-300">AI Model:</span> {modelUsed}
            <span className="mx-2">|</span>
            <span className="font-semibold text-gray-700 dark:text-gray-300">Generated:</span> {formattedDate}
          </p>
          <p>
            <span className="font-semibold text-gray-700 dark:text-gray-300">Purpose:</span> To analyze geopolitical hotspots and emerging threats through intelligence synthesis
          </p>
          <p>
            <span className="font-semibold text-gray-700 dark:text-gray-300">Author:</span> {authorText}
            <span className="mx-2">|</span>
            <span className="font-semibold text-gray-700 dark:text-gray-300">Framework:</span> Geopolitical risk analysis and threat assessment
          </p>
          <p className="text-gray-500 dark:text-gray-300 italic">
            All AI-generated content should be reviewed critically. This analysis operates under specific analytical assumptions and may not reflect all perspectives.
          </p>
        </div>
      </div>
    </div>
  );
}

// Section Card Component
function SectionCard({ title, content, index }: { title: string; content: string; index: number }) {
  const config = getSectionConfig(title);
  const Icon = config.icon;

  return (
    <div className={`rounded-xl border ${config.borderColor} overflow-hidden transition-all hover:shadow-md`}>
      <div className={`${config.bgColor} px-5 py-4 border-b ${config.borderColor}`}>
        <div className="flex items-center gap-3">
          <div className={`p-2 rounded-lg bg-white/60 dark:bg-gray-900/40`}>
            <Icon className={`w-5 h-5 ${config.color}`} />
          </div>
          <div className="flex-1">
            <div className="flex items-center gap-2">
              <span className={`text-xs font-medium ${config.color} uppercase tracking-wider`}>
                Section {index + 1}
              </span>
            </div>
            <h3 className="text-base font-bold text-gray-900 dark:text-gray-100 mt-0.5">
              {title}
            </h3>
          </div>
          <ChevronRight className={`w-5 h-5 ${config.color} opacity-50`} />
        </div>
      </div>

      <div className="p-5 bg-white dark:bg-gray-800">
        <div className="prose prose-sm dark:prose-invert max-w-none
          prose-headings:text-gray-900 dark:prose-headings:text-gray-100
          prose-h3:text-sm prose-h3:font-semibold prose-h3:text-gray-800 dark:prose-h3:text-gray-200 prose-h3:mt-4 prose-h3:mb-2
          prose-h4:text-sm prose-h4:font-medium prose-h4:text-gray-700 dark:prose-h4:text-gray-500
          prose-p:text-gray-600 dark:prose-p:text-gray-500 prose-p:leading-relaxed prose-p:mb-3
          prose-strong:text-gray-900 dark:prose-strong:text-gray-100 prose-strong:font-semibold
          prose-ul:text-gray-600 dark:prose-ul:text-gray-500 prose-ul:my-2 prose-ul:list-disc prose-ul:pl-6
          prose-ol:text-gray-600 dark:prose-ol:text-gray-500 prose-ol:my-2 prose-ol:list-decimal prose-ol:pl-6
          prose-li:text-gray-600 dark:prose-li:text-gray-500 prose-li:my-1.5 prose-li:pl-1
          prose-a:text-pink-600 dark:prose-a:text-pink-400 prose-a:no-underline hover:prose-a:underline
          prose-blockquote:border-l-4 prose-blockquote:border-pink-300 dark:prose-blockquote:border-pink-700 prose-blockquote:bg-pink-50/50 dark:prose-blockquote:bg-pink-900/20 prose-blockquote:py-2 prose-blockquote:px-4 prose-blockquote:rounded-r-lg prose-blockquote:not-italic">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              ul: ({children}) => (
                <ul className="list-disc pl-6 my-3 space-y-2">{children}</ul>
              ),
              ol: ({children}) => (
                <ol className="list-decimal pl-6 my-3 space-y-2">{children}</ol>
              ),
              li: ({children}) => (
                <li className="leading-relaxed">{children}</li>
              ),
            }}
          >
            {content}
          </ReactMarkdown>
        </div>
      </div>
    </div>
  );
}

// Key Metrics Bar Component
function KeyMetricsBar({ narrative, stats }: { narrative: Narrative; stats: OverviewStats | null }) {
  const topCategories = useMemo(() => {
    if (!stats?.by_category) return [];
    return Object.entries(stats.by_category)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 3);
  }, [stats?.by_category]);

  const topRegions = useMemo(() => {
    if (!narrative.top_regions) return [];
    return narrative.top_regions.slice(0, 3);
  }, [narrative.top_regions]);

  const riskBreakdown = narrative.risk_breakdown || {};
  const criticalAndHigh = (riskBreakdown.critical || 0) + (riskBreakdown.high || 0);

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
      {/* Top Categories */}
      <div className="bg-gradient-to-br from-violet-50 to-violet-100/50 dark:from-violet-900/20 dark:to-violet-900/10 rounded-xl p-4 border border-violet-100 dark:border-violet-800/30">
        <div className="flex items-center gap-2 mb-3">
          <Tag className="w-4 h-4 text-violet-600 dark:text-violet-400" />
          <span className="text-xs font-semibold text-violet-700 dark:text-violet-300 uppercase tracking-wide">Top Categories</span>
        </div>
        <div className="space-y-2">
          {topCategories.map(([cat, count], idx) => (
            <div key={cat} className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className={`w-5 h-5 rounded-full flex items-center justify-center text-xs font-bold ${
                  idx === 0 ? 'bg-violet-500 text-white' : 'bg-violet-200 dark:bg-violet-800 text-violet-700 dark:text-violet-300'
                }`}>
                  {idx + 1}
                </span>
                <span className="text-sm text-gray-700 dark:text-gray-300 truncate max-w-[120px]">{cat}</span>
              </div>
              <span className="text-sm font-semibold text-gray-900 dark:text-gray-100">{count}</span>
            </div>
          ))}
          {topCategories.length === 0 && (
            <span className="text-sm text-gray-500">No category data</span>
          )}
        </div>
      </div>

      {/* Top Regions */}
      <div className="bg-gradient-to-br from-emerald-50 to-emerald-100/50 dark:from-emerald-900/20 dark:to-emerald-900/10 rounded-xl p-4 border border-emerald-100 dark:border-emerald-800/30">
        <div className="flex items-center gap-2 mb-3">
          <Globe className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
          <span className="text-xs font-semibold text-emerald-700 dark:text-emerald-300 uppercase tracking-wide">Top Regions</span>
        </div>
        <div className="space-y-2">
          {topRegions.map((region, idx) => (
            <div key={region} className="flex items-center gap-2">
              <span className={`w-5 h-5 rounded-full flex items-center justify-center text-xs font-bold ${
                idx === 0 ? 'bg-emerald-500 text-white' : 'bg-emerald-200 dark:bg-emerald-800 text-emerald-700 dark:text-emerald-300'
              }`}>
                {idx + 1}
              </span>
              <span className="text-sm text-gray-700 dark:text-gray-300">{region}</span>
            </div>
          ))}
          {topRegions.length === 0 && (
            <span className="text-sm text-gray-500">No region data</span>
          )}
        </div>
      </div>

      {/* Risk Summary */}
      <div className="bg-gradient-to-br from-amber-50 to-amber-100/50 dark:from-amber-900/20 dark:to-amber-900/10 rounded-xl p-4 border border-amber-100 dark:border-amber-800/30">
        <div className="flex items-center gap-2 mb-3">
          <AlertTriangle className="w-4 h-4 text-amber-600 dark:text-amber-400" />
          <span className="text-xs font-semibold text-amber-700 dark:text-amber-300 uppercase tracking-wide">Risk Signals</span>
        </div>
        <div className="flex items-center gap-4">
          <div className="text-3xl font-bold text-gray-900 dark:text-gray-100">
            {criticalAndHigh}
          </div>
          <div className="flex-1 space-y-1">
            {(['critical', 'high', 'medium'] as const).map((level) => {
              const count = riskBreakdown[level] || 0;
              if (count === 0) return null;
              return (
                <div key={level} className="flex items-center justify-between text-xs">
                  <div className="flex items-center gap-1.5">
                    <div className="w-2 h-2 rounded-full" style={{ backgroundColor: RISK_COLORS[level] }} />
                    <span className="text-gray-600 dark:text-gray-300 capitalize">{level}</span>
                  </div>
                  <span className="font-medium text-gray-900 dark:text-gray-100">{count}</span>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}

type SectionId = 'summary' | 'regional' | 'threats' | 'outlook' | 'priority';

export function GeopoliticalInsightsTab({
  stats,
  hotspots,
  loading,
  model = 'gpt-4o-mini',
}: GeopoliticalInsightsTabProps) {
  const [generating, setGenerating] = useState(false);
  const [narrative, setNarrative] = useState<Narrative | null>(null);
  const [history, setHistory] = useState<NarrativeSummary[]>([]);
  const [loadingNarrative, setLoadingNarrative] = useState(true);
  const [showHistory, setShowHistory] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeSection, setActiveSection] = useState<number>(0);

  // Build sections from narrative
  const sections = useMemo(() => {
    if (!narrative) return [];
    const result: { id: SectionId; title: string; content: string }[] = [];

    if (narrative.executive_summary) {
      result.push({ id: 'summary', title: 'Executive Summary', content: narrative.executive_summary });
    }
    if (narrative.regional_analysis) {
      result.push({ id: 'regional', title: 'Regional Analysis', content: narrative.regional_analysis });
    }
    if (narrative.emerging_threats) {
      result.push({ id: 'threats', title: 'Emerging Threats', content: narrative.emerging_threats });
    }
    if (narrative.outlook) {
      result.push({ id: 'outlook', title: 'Strategic Outlook', content: narrative.outlook });
    }

    // If no structured sections but has narrative_text, use that
    if (result.length === 0 && narrative.narrative_text) {
      result.push({ id: 'summary', title: 'Analysis Report', content: narrative.narrative_text });
    }

    return result;
  }, [narrative]);

  // Fetch latest narrative on mount
  useEffect(() => {
    fetchLatestNarrative();
    fetchNarrativeHistory();
  }, []);

  const fetchLatestNarrative = async () => {
    setLoadingNarrative(true);
    try {
      const response = await fetch('/api/geopolitical-hotspots/narrative');
      if (response.ok) {
        const data = await response.json();
        setNarrative(data);
      }
    } catch (err) {
      console.error('Failed to fetch narrative:', err);
    } finally {
      setLoadingNarrative(false);
    }
  };

  const fetchNarrativeHistory = async () => {
    try {
      const response = await fetch('/api/geopolitical-hotspots/narratives?limit=5');
      if (response.ok) {
        const data = await response.json();
        setHistory(data);
      }
    } catch (err) {
      console.error('Failed to fetch narrative history:', err);
    }
  };

  const generateNarrative = useCallback(async () => {
    setGenerating(true);
    setError(null);

    try {
      const response = await fetch('/api/geopolitical-hotspots/generate-narrative', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model }),
      });

      const result = await response.json();

      if (response.ok) {
        await fetchLatestNarrative();
        await fetchNarrativeHistory();
        setActiveSection(0);
      } else {
        setError(result.detail || 'Failed to generate narrative');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to generate narrative');
    } finally {
      setGenerating(false);
    }
  }, [model]);

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return 'Unknown';
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  // Export narrative as markdown
  const exportNarrative = useCallback(() => {
    if (!narrative) return;

    const date = narrative.generated_at ? new Date(narrative.generated_at).toISOString().split('T')[0] : 'unknown';
    const filename = `geopolitical-briefing-${date}.md`;

    const markdown = `# Strategic Intelligence Briefing

**Generated:** ${formatDate(narrative.generated_at)}
**Model:** ${narrative.model_used || 'Unknown'}
**Hotspots Analyzed:** ${narrative.hotspot_count}
**Total Articles:** ${narrative.article_count}

---

## Executive Summary

${narrative.executive_summary || 'No executive summary available.'}

---

## Regional Analysis

${narrative.regional_analysis || 'No regional analysis available.'}

---

## Emerging Threats

${narrative.emerging_threats || 'No emerging threats analysis available.'}

---

## Strategic Outlook

${narrative.outlook || 'No strategic outlook available.'}

---

### Key Metrics

- **Total Hotspots:** ${narrative.hotspot_count}
- **Total Articles:** ${narrative.article_count}
- **Top Regions:** ${narrative.top_regions?.join(', ') || 'N/A'}
- **Top Categories:** ${narrative.top_categories?.join(', ') || 'N/A'}
- **Risk Breakdown:**
  - Critical: ${narrative.risk_breakdown?.critical || 0}
  - High: ${narrative.risk_breakdown?.high || 0}
  - Medium: ${narrative.risk_breakdown?.medium || 0}
  - Low: ${narrative.risk_breakdown?.low || 0}
  - Info: ${narrative.risk_breakdown?.info || 0}

---

*Generated by AunooAI Geopolitical Hotspots Analysis*
`;

    const blob = new Blob([markdown], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }, [narrative]);

  if (loading || loadingNarrative) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 py-16">
        <div className="relative">
          <div className="w-12 h-12 rounded-full bg-pink-100 dark:bg-pink-900/30 flex items-center justify-center">
            <Loader2 className="w-6 h-6 animate-spin text-pink-500" />
          </div>
        </div>
        <span className="text-sm text-gray-500 dark:text-gray-300">Loading intelligence briefing...</span>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Main Card */}
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden shadow-sm">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-100 dark:border-gray-700 bg-gradient-to-r from-pink-50 via-violet-50/50 to-transparent dark:from-pink-900/20 dark:via-violet-900/10 dark:to-transparent">
          <div className="flex items-center gap-3">
            <div className="p-2.5 bg-gradient-to-br from-pink-500 to-violet-500 rounded-xl shadow-lg shadow-pink-500/20">
              <Sparkles className="w-5 h-5 text-white" />
            </div>
            <div>
              <h3 className="text-base font-bold text-gray-900 dark:text-gray-100">
                Strategic Intelligence Briefing
              </h3>
              <p className="text-xs text-gray-500 dark:text-gray-300">
                AI-powered geopolitical threat analysis
              </p>
            </div>
            {narrative && (
              <span className="flex items-center gap-1.5 px-2.5 py-1 text-xs bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-400 rounded-full font-medium">
                <Clock className="w-3 h-3" />
                {formatDate(narrative.generated_at)}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            {narrative && (
              <button
                onClick={exportNarrative}
                className="flex items-center gap-2 px-3 py-2 text-xs font-medium bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
              >
                <Download className="w-3.5 h-3.5" />
                Export
              </button>
            )}
            <button
              onClick={generateNarrative}
              disabled={generating || !stats || stats.total_hotspots === 0}
              className="flex items-center gap-2 px-4 py-2 text-sm font-medium bg-gradient-to-r from-pink-500 to-violet-500 text-white rounded-lg hover:from-pink-600 hover:to-violet-600 disabled:opacity-50 transition-all shadow-md shadow-pink-500/20"
            >
              {generating ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Generating...
                </>
              ) : (
                <>
                  <Sparkles className="w-4 h-4" />
                  Generate New
                </>
              )}
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="p-5">
          {/* Error */}
          {error && (
            <div className="flex items-center gap-4 p-4 bg-red-50 dark:bg-red-900/20 rounded-xl border border-red-200 dark:border-red-800 mb-6">
              <div className="p-3 bg-red-100 dark:bg-red-900/40 rounded-lg">
                <AlertCircle className="w-6 h-6 text-red-500" />
              </div>
              <div>
                <p className="text-sm font-semibold text-red-700 dark:text-red-300">Report Generation Failed</p>
                <p className="text-xs text-red-600 dark:text-red-400 mt-0.5">{error}</p>
              </div>
            </div>
          )}

          {/* No Narrative State */}
          {!narrative && !generating && (
            <div className="text-center py-16">
              <div className="relative inline-block mb-6">
                <div className="w-20 h-20 rounded-2xl bg-gradient-to-br from-pink-100 to-violet-100 dark:from-pink-900/30 dark:to-violet-900/30 flex items-center justify-center">
                  <FileText className="w-10 h-10 text-pink-400 dark:text-pink-500" />
                </div>
                <div className="absolute -bottom-1 -right-1 w-8 h-8 rounded-lg bg-violet-500 flex items-center justify-center">
                  <Sparkles className="w-4 h-4 text-white" />
                </div>
              </div>
              <h4 className="text-lg font-semibold text-gray-800 dark:text-gray-200 mb-2">
                Generate Your Intelligence Briefing
              </h4>
              <p className="text-sm text-gray-500 dark:text-gray-300 max-w-lg mx-auto mb-6">
                {stats && stats.total_hotspots > 0
                  ? 'Our AI will analyze your geopolitical hotspot data to generate a comprehensive intelligence briefing including regional analysis, emerging threats, and strategic outlook.'
                  : 'Process some articles first to create hotspots, then generate a briefing.'}
              </p>
              <div className="flex flex-wrap justify-center gap-2 text-xs text-gray-500 dark:text-gray-300">
                <span className="px-2 py-1 bg-gray-100 dark:bg-gray-700 rounded">Regional Analysis</span>
                <span className="px-2 py-1 bg-gray-100 dark:bg-gray-700 rounded">Threat Detection</span>
                <span className="px-2 py-1 bg-gray-100 dark:bg-gray-700 rounded">Risk Assessment</span>
                <span className="px-2 py-1 bg-gray-100 dark:bg-gray-700 rounded">Strategic Outlook</span>
              </div>
            </div>
          )}

          {/* Narrative Content */}
          {narrative && (
            <div className="space-y-6">
              {/* Stats Row */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <div className="relative overflow-hidden p-4 bg-gradient-to-br from-pink-500 to-pink-600 rounded-xl text-white">
                  <BarChart3 className="absolute -right-2 -bottom-2 w-16 h-16 text-pink-400/30" />
                  <div className="relative">
                    <span className="text-xs font-medium text-pink-100 uppercase tracking-wide">Hotspots</span>
                    <p className="text-2xl font-bold mt-1">{narrative.hotspot_count.toLocaleString()}</p>
                  </div>
                </div>
                <div className="relative overflow-hidden p-4 bg-gradient-to-br from-violet-500 to-violet-600 rounded-xl text-white">
                  <FileText className="absolute -right-2 -bottom-2 w-16 h-16 text-violet-400/30" />
                  <div className="relative">
                    <span className="text-xs font-medium text-violet-100 uppercase tracking-wide">Articles</span>
                    <p className="text-2xl font-bold mt-1">{narrative.article_count.toLocaleString()}</p>
                  </div>
                </div>
                <div className="relative overflow-hidden p-4 bg-gradient-to-br from-blue-500 to-blue-600 rounded-xl text-white">
                  <Globe className="absolute -right-2 -bottom-2 w-16 h-16 text-blue-400/30" />
                  <div className="relative">
                    <span className="text-xs font-medium text-blue-100 uppercase tracking-wide">Regions</span>
                    <p className="text-2xl font-bold mt-1">{narrative.top_regions?.length || 0}</p>
                  </div>
                </div>
                <div className="relative overflow-hidden p-4 bg-gradient-to-br from-emerald-500 to-emerald-600 rounded-xl text-white">
                  <Tag className="absolute -right-2 -bottom-2 w-16 h-16 text-emerald-400/30" />
                  <div className="relative">
                    <span className="text-xs font-medium text-emerald-100 uppercase tracking-wide">Categories</span>
                    <p className="text-2xl font-bold mt-1">{narrative.top_categories?.length || 0}</p>
                  </div>
                </div>
              </div>

              {/* Key Metrics Bar */}
              <KeyMetricsBar narrative={narrative} stats={stats} />

              {/* Section Navigation */}
              {sections.length > 1 && (
                <div className="flex flex-wrap gap-2 p-3 bg-gray-50 dark:bg-gray-750 rounded-xl">
                  {sections.map((section, idx) => {
                    const config = getSectionConfig(section.title);
                    const Icon = config.icon;
                    return (
                      <button
                        key={idx}
                        onClick={() => {
                          setActiveSection(idx);
                          document.getElementById(`geo-section-${idx}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
                        }}
                        className={`flex items-center gap-2 px-3 py-1.5 text-xs font-medium rounded-lg transition-all ${
                          activeSection === idx
                            ? `${config.bgColor} ${config.color} shadow-sm`
                            : 'text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700'
                        }`}
                      >
                        <Icon className="w-3.5 h-3.5" />
                        <span className="hidden sm:inline">{section.title}</span>
                        <span className="sm:hidden">{idx + 1}</span>
                      </button>
                    );
                  })}
                </div>
              )}

              {/* Section Cards */}
              <div className="space-y-4">
                {sections.map((section, idx) => (
                  <div key={idx} id={`geo-section-${idx}`}>
                    <SectionCard title={section.title} content={section.content} index={idx} />
                  </div>
                ))}
              </div>

              {/* Priority Hotspots */}
              {stats && stats.top_hotspots.length > 0 && (
                <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6 shadow-sm">
                  <div className="flex items-center gap-2 mb-4">
                    <Map className="w-5 h-5 text-purple-500" />
                    <h4 className="font-semibold text-gray-900 dark:text-gray-100">
                      Priority Attention Areas
                    </h4>
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {stats.top_hotspots.slice(0, 6).map((hotspot, index) => (
                      <div
                        key={hotspot.id}
                        className="relative p-4 rounded-lg border border-gray-200 dark:border-gray-700 hover:shadow-md transition-all group"
                        style={{
                          borderLeftWidth: '4px',
                          borderLeftColor: RISK_COLORS[hotspot.risk_level],
                        }}
                      >
                        <div className="absolute top-2 right-2 w-6 h-6 rounded-full bg-gray-100 dark:bg-gray-700 flex items-center justify-center text-xs font-bold text-gray-500 dark:text-gray-400">
                          {index + 1}
                        </div>
                        <div className="flex items-start justify-between mb-2 pr-8">
                          <h5 className="font-medium text-gray-900 dark:text-gray-100">
                            {hotspot.location_name}
                          </h5>
                        </div>
                        {hotspot.country_name && (
                          <p className="text-sm text-gray-500 dark:text-gray-400 mb-2">
                            {hotspot.country_name}
                          </p>
                        )}
                        <div className="flex items-center justify-between">
                          <span className="text-sm text-gray-600 dark:text-gray-400">
                            {hotspot.article_count} articles
                          </span>
                          <div className="flex items-center gap-2">
                            <span
                              className={`px-2 py-0.5 text-xs font-medium rounded-full ${
                                hotspot.risk_level === 'critical'
                                  ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300'
                                  : hotspot.risk_level === 'high'
                                    ? 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300'
                                    : hotspot.risk_level === 'medium'
                                      ? 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-300'
                                      : 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300'
                              }`}
                            >
                              {hotspot.risk_level.toUpperCase()}
                            </span>
                            {hotspot.trend && (
                              <span
                                className={`text-xs ${
                                  hotspot.trend === 'escalating'
                                    ? 'text-red-500'
                                    : hotspot.trend === 'de-escalating'
                                      ? 'text-green-500'
                                      : 'text-gray-500'
                                }`}
                              >
                                {hotspot.trend === 'escalating'
                                  ? '↑'
                                  : hotspot.trend === 'de-escalating'
                                    ? '↓'
                                    : '→'}
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* AI Disclosure Footer */}
              <AIDisclosureFooter
                modelUsed={narrative.model_used || 'GPT-4o-mini (OpenAI)'}
                generatedAt={narrative.generated_at || new Date().toISOString()}
              />
            </div>
          )}
        </div>
      </div>

      {/* Narrative History */}
      {history.length > 1 && (
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm">
          <button
            onClick={() => setShowHistory(!showHistory)}
            className="w-full p-4 flex items-center justify-between text-left hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors rounded-xl"
          >
            <span className="font-medium text-gray-900 dark:text-gray-100">
              Briefing History ({history.length})
            </span>
            {showHistory ? (
              <ChevronUp className="w-5 h-5 text-gray-500" />
            ) : (
              <ChevronDown className="w-5 h-5 text-gray-500" />
            )}
          </button>

          {showHistory && (
            <div className="border-t border-gray-200 dark:border-gray-700 divide-y divide-gray-200 dark:divide-gray-700">
              {history.map((item) => (
                <div
                  key={item.id}
                  className={`p-4 ${item.id === narrative?.id ? 'bg-pink-50 dark:bg-pink-900/20' : ''}`}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
                      {formatDate(item.generated_at)}
                    </span>
                    {item.id === narrative?.id && (
                      <span className="text-xs text-pink-600 dark:text-pink-400">Current</span>
                    )}
                  </div>
                  <p className="text-sm text-gray-600 dark:text-gray-400 line-clamp-2">
                    {item.executive_summary || 'No summary available'}
                  </p>
                  <div className="flex items-center gap-4 mt-2 text-xs text-gray-500 dark:text-gray-400">
                    <span>{item.hotspot_count} hotspots</span>
                    <span>{item.model_used}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
