/**
 * Science Insights Tab Component
 * Narrative analysis and report generation with enhanced visual styling
 */

import { useState, useCallback, useEffect, useMemo } from 'react';
import {
  Sparkles, FileText, Loader2, AlertCircle, Download, Calendar, BarChart3, Clock, Tag,
  TrendingUp, Target, AlertTriangle, Lightbulb, ChevronRight, Zap, Globe, Users,
  ArrowUpRight, ArrowDownRight, Minus, BookOpen, Flag, Eye, Info, Bot
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  generateNarrative,
  getLatestNarrative,
  type NarrativeResponse,
  type ScienceCategory,
  type SavedNarrative,
} from '../../services/scienceFundingApi';

// AI Disclosure Footer Component
function AIDisclosureFooter({
  modelUsed,
  generatedAt,
  purpose
}: {
  modelUsed: string;
  generatedAt: string;
  purpose: string;
}) {
  // Get user info from session (if available)
  const userName = (window as any).userSession?.username;
  const userEmail = (window as any).userSession?.email;

  // Build author string
  let authorText = 'Aunoo AI';
  if (userName) {
    authorText += ` with ${userName}`;
    if (userEmail) {
      authorText += ` (${userEmail})`;
    }
  }

  // Format date
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
            <span className="font-semibold text-gray-700 dark:text-gray-300">Report:</span> Science Funding Intelligence Analysis
            <span className="mx-2">|</span>
            <span className="font-semibold text-gray-700 dark:text-gray-300">AI Model:</span> {modelUsed}
            <span className="mx-2">|</span>
            <span className="font-semibold text-gray-700 dark:text-gray-300">Generated:</span> {formattedDate}
          </p>
          <p>
            <span className="font-semibold text-gray-700 dark:text-gray-300">Purpose:</span> {purpose}
          </p>
          <p>
            <span className="font-semibold text-gray-700 dark:text-gray-300">Author:</span> {authorText}
            <span className="mx-2">|</span>
            <span className="font-semibold text-gray-700 dark:text-gray-300">Framework:</span> Critical analysis of science funding trends, grant impacts, and research infrastructure changes
          </p>
          <p className="text-gray-500 dark:text-gray-300 italic">
            All AI-generated content should be reviewed critically. This analysis operates under specific analytical assumptions and may not reflect all perspectives.
          </p>
        </div>
      </div>
    </div>
  );
}

interface ScienceInsightsTabProps {
  categories: ScienceCategory[];
  topic: string;
  daysBack: number;
  refreshTrigger?: number;
}

// Section configuration with icons and colors
const SECTION_CONFIG: Record<string, { icon: typeof TrendingUp; color: string; bgColor: string; borderColor: string }> = {
  'Executive Summary': { icon: BookOpen, color: 'text-blue-600 dark:text-blue-400', bgColor: 'bg-blue-50 dark:bg-blue-900/20', borderColor: 'border-blue-200 dark:border-blue-800' },
  'Trend Analysis': { icon: TrendingUp, color: 'text-emerald-600 dark:text-emerald-400', bgColor: 'bg-emerald-50 dark:bg-emerald-900/20', borderColor: 'border-emerald-200 dark:border-emerald-800' },
  'Thematic Spotlight': { icon: Target, color: 'text-violet-600 dark:text-violet-400', bgColor: 'bg-violet-50 dark:bg-violet-900/20', borderColor: 'border-violet-200 dark:border-violet-800' },
  'Escalation Assessment': { icon: AlertTriangle, color: 'text-amber-600 dark:text-amber-400', bgColor: 'bg-amber-50 dark:bg-amber-900/20', borderColor: 'border-amber-200 dark:border-amber-800' },
  'Forward-Looking Insights': { icon: Lightbulb, color: 'text-teal-600 dark:text-teal-400', bgColor: 'bg-teal-50 dark:bg-teal-900/20', borderColor: 'border-teal-200 dark:border-teal-800' },
  'Forward-Looking Concerns': { icon: Lightbulb, color: 'text-teal-600 dark:text-teal-400', bgColor: 'bg-teal-50 dark:bg-teal-900/20', borderColor: 'border-teal-200 dark:border-teal-800' },
  'Institutional Targets': { icon: Target, color: 'text-red-600 dark:text-red-400', bgColor: 'bg-red-50 dark:bg-red-900/20', borderColor: 'border-red-200 dark:border-red-800' },
  'Key Actors': { icon: Users, color: 'text-indigo-600 dark:text-indigo-400', bgColor: 'bg-indigo-50 dark:bg-indigo-900/20', borderColor: 'border-indigo-200 dark:border-indigo-800' },
  'Geographic Focus': { icon: Globe, color: 'text-cyan-600 dark:text-cyan-400', bgColor: 'bg-cyan-50 dark:bg-cyan-900/20', borderColor: 'border-cyan-200 dark:border-cyan-800' },
  'Recommendations': { icon: Flag, color: 'text-rose-600 dark:text-rose-400', bgColor: 'bg-rose-50 dark:bg-rose-900/20', borderColor: 'border-rose-200 dark:border-rose-800' },
  'Watchlist': { icon: Eye, color: 'text-orange-600 dark:text-orange-400', bgColor: 'bg-orange-50 dark:bg-orange-900/20', borderColor: 'border-orange-200 dark:border-orange-800' },
};

// Known section titles to look for
const KNOWN_SECTIONS = [
  'Executive Summary',
  'Trend Analysis',
  'Thematic Spotlight',
  'Escalation Assessment',
  'Forward-Looking Insights',
  'Forward Looking Insights',
  'Forward-Looking Concerns',
  'Forward Looking Concerns',
  'Institutional Targets',
  'Key Actors',
  'Geographic Focus',
  'Geographic & Institutional Focus',
  'Recommendations',
  'Watchlist',
  'Key Findings',
  'Analysis',
  'Overview',
  'Summary',
  'Conclusion',
  'Implications',
  'Funding Implications',
  'Strategic Implications',
  'Research Impact',
  'Science Funding Outlook',
];

// Parse narrative into sections - handles multiple formats
function parseNarrativeIntoSections(narrative: string): { title: string; content: string }[] {
  const sections: { title: string; content: string }[] = [];
  const lines = narrative.split('\n');

  let currentTitle = '';
  let currentContent: string[] = [];
  let foundFirstSection = false;

  // Helper to check if a line is a section header
  const isSectionHeader = (line: string): string | null => {
    const trimmed = line.trim();

    // Check for ## Header format
    if (trimmed.startsWith('## ')) {
      return trimmed.replace(/^## /, '').replace(/\*\*/g, '').trim();
    }

    // Check for # Header format (H1)
    if (trimmed.startsWith('# ') && !trimmed.startsWith('# ScienceWatch')) {
      return trimmed.replace(/^# /, '').replace(/\*\*/g, '').trim();
    }

    // Check for **Section Title** on its own line (bold text)
    const boldMatch = trimmed.match(/^\*\*([^*]+)\*\*:?$/);
    if (boldMatch) {
      const title = boldMatch[1].trim();
      // Check if it's a known section
      for (const known of KNOWN_SECTIONS) {
        if (title.toLowerCase().includes(known.toLowerCase()) ||
            known.toLowerCase().includes(title.toLowerCase())) {
          return title;
        }
      }
    }

    // Check for "Section Title:" format (ends with colon, no other content)
    if (trimmed.endsWith(':') && !trimmed.includes('.') && trimmed.length < 50) {
      const title = trimmed.replace(/:$/, '').replace(/\*\*/g, '').trim();
      for (const known of KNOWN_SECTIONS) {
        if (title.toLowerCase().includes(known.toLowerCase()) ||
            known.toLowerCase().includes(title.toLowerCase())) {
          return title;
        }
      }
    }

    // Check for known section names as standalone lines
    for (const known of KNOWN_SECTIONS) {
      const cleanLine = trimmed.replace(/\*\*/g, '').replace(/:$/, '').trim();
      if (cleanLine.toLowerCase() === known.toLowerCase()) {
        return known;
      }
    }

    return null;
  };

  // Process each line
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const sectionTitle = isSectionHeader(line);

    if (sectionTitle) {
      // Save previous section if exists and has non-empty content
      if (currentTitle) {
        const content = currentContent.join('\n').trim();
        if (content && content.length > 20) { // Must have substantial content
          sections.push({
            title: currentTitle,
            content: content
          });
        }
      } else if (!foundFirstSection && currentContent.length > 0) {
        // Content before first section header
        const preContent = currentContent.join('\n').trim();
        // Only add if it's substantial and not just metadata
        if (preContent && preContent.length > 50 && !preContent.match(/^(ScienceWatch|Time Period|Analysis of|\*\*Time Period)/i)) {
          sections.push({
            title: 'Overview',
            content: preContent
          });
        }
      }

      currentTitle = sectionTitle;
      currentContent = [];
      foundFirstSection = true;
    } else {
      // Skip title/metadata lines at the very start
      const trimmed = line.trim();
      if (!foundFirstSection && (
        trimmed.startsWith('ScienceWatch') ||
        trimmed.startsWith('Time Period:') ||
        trimmed.startsWith('**Time Period') ||
        trimmed.startsWith('**ScienceWatch') ||
        trimmed.match(/^#{1,2}\s*ScienceWatch/) ||
        trimmed === '' ||
        trimmed === '---'
      )) {
        continue;
      }
      currentContent.push(line);
    }
  }

  // Don't forget the last section
  if (currentTitle && currentContent.length > 0) {
    const content = currentContent.join('\n').trim();
    if (content && content.length > 20) {
      sections.push({
        title: currentTitle,
        content: content
      });
    }
  } else if (!foundFirstSection && currentContent.length > 0) {
    // No sections found at all - treat entire content as one section
    const content = currentContent.join('\n').trim();
    if (content && content.length > 50) {
      sections.push({
        title: 'Analysis Report',
        content: content
      });
    }
  }

  // If still no sections, return the whole narrative as one
  if (sections.length === 0 && narrative.trim()) {
    sections.push({
      title: 'Analysis Report',
      content: narrative.trim()
    });
  }

  // Filter out any "Overview" sections that are just metadata/titles
  const filteredSections = sections.filter(section => {
    // Skip "Overview" sections that are very short or just contain report titles
    if (section.title === 'Overview') {
      const content = section.content.toLowerCase();
      if (section.content.length < 150) return false;
      if (content.includes('analytical narrative report') && section.content.length < 300) return false;
      if (content.includes('sciencewatch insights') && section.content.length < 300) return false;
      if (content.match(/^\s*\d{4}-\d{2}-\d{2}/) && section.content.length < 200) return false;
    }
    return true;
  });

  return filteredSections.length > 0 ? filteredSections : sections;
}

// Get section config with fallback
function getSectionConfig(title: string) {
  // Try exact match first
  if (SECTION_CONFIG[title]) {
    return SECTION_CONFIG[title];
  }

  // Try partial match
  for (const [key, config] of Object.entries(SECTION_CONFIG)) {
    if (title.toLowerCase().includes(key.toLowerCase()) || key.toLowerCase().includes(title.toLowerCase())) {
      return config;
    }
  }

  // Default config
  return {
    icon: Zap,
    color: 'text-gray-600 dark:text-gray-300',
    bgColor: 'bg-gray-50 dark:bg-gray-800',
    borderColor: 'border-gray-200 dark:border-gray-700'
  };
}

// Section Card Component
function SectionCard({ title, content, index }: { title: string; content: string; index: number }) {
  const config = getSectionConfig(title);
  const Icon = config.icon;

  return (
    <div className={`rounded-xl border ${config.borderColor} overflow-hidden transition-all hover:shadow-md`}>
      {/* Section Header */}
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

      {/* Section Content */}
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
          prose-a:text-emerald-600 dark:prose-a:text-emerald-400 prose-a:no-underline hover:prose-a:underline
          prose-blockquote:border-l-4 prose-blockquote:border-emerald-300 dark:prose-blockquote:border-emerald-700 prose-blockquote:bg-emerald-50/50 dark:prose-blockquote:bg-emerald-900/20 prose-blockquote:py-2 prose-blockquote:px-4 prose-blockquote:rounded-r-lg prose-blockquote:not-italic">
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
function KeyMetricsBar({ dataSummary }: { dataSummary: NarrativeResponse['data_summary'] }) {
  const topCategories = useMemo(() => {
    return Object.entries(dataSummary.categories || {})
      .sort((a, b) => b[1] - a[1])
      .slice(0, 3);
  }, [dataSummary.categories]);

  const topThemes = useMemo(() => {
    return Object.entries(dataSummary.top_themes || {})
      .sort((a, b) => b[1] - a[1])
      .slice(0, 3);
  }, [dataSummary.top_themes]);

  const escalationTotal = useMemo(() => {
    return Object.values(dataSummary.escalation || {}).reduce((a, b) => a + b, 0);
  }, [dataSummary.escalation]);

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
      {/* Top Categories */}
      <div className="bg-gradient-to-br from-teal-50 to-teal-100/50 dark:from-teal-900/20 dark:to-teal-900/10 rounded-xl p-4 border border-teal-100 dark:border-teal-800/30">
        <div className="flex items-center gap-2 mb-3">
          <Tag className="w-4 h-4 text-teal-600 dark:text-teal-400" />
          <span className="text-xs font-semibold text-teal-700 dark:text-teal-300 uppercase tracking-wide">Top Categories</span>
        </div>
        <div className="space-y-2">
          {topCategories.map(([cat, count], idx) => (
            <div key={cat} className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className={`w-5 h-5 rounded-full flex items-center justify-center text-xs font-bold ${
                  idx === 0 ? 'bg-teal-500 text-white' : 'bg-teal-200 dark:bg-teal-800 text-teal-700 dark:text-teal-300'
                }`}>
                  {idx + 1}
                </span>
                <span className="text-sm text-gray-700 dark:text-gray-300 truncate max-w-[120px]">{cat}</span>
              </div>
              <span className="text-sm font-semibold text-gray-900 dark:text-gray-100">{count}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Top Themes */}
      <div className="bg-gradient-to-br from-emerald-50 to-emerald-100/50 dark:from-emerald-900/20 dark:to-emerald-900/10 rounded-xl p-4 border border-emerald-100 dark:border-emerald-800/30">
        <div className="flex items-center gap-2 mb-3">
          <TrendingUp className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
          <span className="text-xs font-semibold text-emerald-700 dark:text-emerald-300 uppercase tracking-wide">Top Themes</span>
        </div>
        <div className="space-y-2">
          {topThemes.map(([theme, count], idx) => (
            <div key={theme} className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className={`w-5 h-5 rounded-full flex items-center justify-center text-xs font-bold ${
                  idx === 0 ? 'bg-emerald-500 text-white' : 'bg-emerald-200 dark:bg-emerald-800 text-emerald-700 dark:text-emerald-300'
                }`}>
                  {idx + 1}
                </span>
                <span className="text-sm text-gray-700 dark:text-gray-300 truncate max-w-[120px]">{theme}</span>
              </div>
              <span className="text-sm font-semibold text-gray-900 dark:text-gray-100">{count}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Escalation Summary */}
      <div className="bg-gradient-to-br from-amber-50 to-amber-100/50 dark:from-amber-900/20 dark:to-amber-900/10 rounded-xl p-4 border border-amber-100 dark:border-amber-800/30">
        <div className="flex items-center gap-2 mb-3">
          <AlertTriangle className="w-4 h-4 text-amber-600 dark:text-amber-400" />
          <span className="text-xs font-semibold text-amber-700 dark:text-amber-300 uppercase tracking-wide">Escalation Signals</span>
        </div>
        <div className="flex items-center gap-4">
          <div className="text-3xl font-bold text-gray-900 dark:text-gray-100">
            {escalationTotal}
          </div>
          <div className="flex-1 space-y-1">
            {Object.entries(dataSummary.escalation || {})
              .filter(([, count]) => count > 0)
              .sort((a, b) => b[1] - a[1])
              .slice(0, 2)
              .map(([marker, count]) => (
                <div key={marker} className="flex items-center justify-between text-xs">
                  <span className="text-gray-600 dark:text-gray-300 truncate max-w-[100px]">{marker}</span>
                  <span className="font-medium text-gray-900 dark:text-gray-100">{count}</span>
                </div>
              ))}
          </div>
        </div>
      </div>
    </div>
  );
}

export function ScienceInsightsTab({ categories, topic, daysBack, refreshTrigger }: ScienceInsightsTabProps) {
  const [narrative, setNarrative] = useState<NarrativeResponse | null>(null);
  const [savedNarrative, setSavedNarrative] = useState<SavedNarrative | null>(null);
  const [loadingNarrative, setLoadingNarrative] = useState(false);
  const [loadingSavedNarrative, setLoadingSavedNarrative] = useState(true);
  const [narrativeError, setNarrativeError] = useState<string | null>(null);
  const [activeSection, setActiveSection] = useState(0);

  // Parse narrative into sections
  const sections = useMemo(() => {
    if (!narrative?.narrative) return [];
    return parseNarrativeIntoSections(narrative.narrative);
  }, [narrative?.narrative]);

  // Auto-load saved narrative on mount
  useEffect(() => {
    const loadSavedNarrative = async () => {
      setLoadingSavedNarrative(true);
      try {
        const saved = await getLatestNarrative(topic);
        if (saved) {
          setSavedNarrative(saved);
          setNarrative({
            narrative: saved.narrative,
            generated_at: saved.generated_at,
            data_summary: saved.data_summary,
          });
        }
      } catch (error) {
        console.error('Failed to load saved narrative:', error);
      } finally {
        setLoadingSavedNarrative(false);
      }
    };

    loadSavedNarrative();
  }, [topic]);

  // Regenerate narrative when refresh is triggered
  const [initialLoad, setInitialLoad] = useState(true);
  useEffect(() => {
    if (initialLoad) {
      setInitialLoad(false);
      return;
    }
    if (refreshTrigger !== undefined && refreshTrigger > 0 && narrative) {
      handleGenerateNarrative();
    }
  }, [refreshTrigger]);

  const handleGenerateNarrative = useCallback(async () => {
    setLoadingNarrative(true);
    setNarrativeError(null);
    try {
      const result = await generateNarrative({ topic, days_back: daysBack });
      setNarrative(result);
      setSavedNarrative(null);
      setActiveSection(0);
    } catch (error) {
      setNarrativeError(error instanceof Error ? error.message : 'Failed to generate narrative');
    } finally {
      setLoadingNarrative(false);
    }
  }, [topic, daysBack]);

  const handleDownloadNarrative = useCallback(() => {
    if (!narrative) return;

    const dateStr = new Date().toISOString().split('T')[0];
    const filename = `sciencewatch-report-${dateStr}.md`;

    const content = `# ScienceWatch Narrative Analysis

**Generated:** ${new Date(narrative.generated_at).toLocaleString()}
**Date Range:** ${narrative.data_summary.date_range.start} to ${narrative.data_summary.date_range.end}
**Articles Analyzed:** ${narrative.data_summary.total_articles}
**Articles with Categories:** ${narrative.data_summary.total_categorized}

---

${narrative.narrative}

---

## Data Summary

### Categories
${Object.entries(narrative.data_summary.categories || {})
  .sort((a, b) => b[1] - a[1])
  .map(([cat, count]) => `- **${cat}:** ${count}`)
  .join('\n')}

### Top Themes
${Object.entries(narrative.data_summary.top_themes || {})
  .sort((a, b) => b[1] - a[1])
  .slice(0, 5)
  .map(([theme, count]) => `- **${theme}:** ${count}`)
  .join('\n')}

### Escalation Markers
${Object.entries(narrative.data_summary.escalation || {})
  .sort((a, b) => b[1] - a[1])
  .map(([marker, count]) => `- **${marker}:** ${count}`)
  .join('\n')}
`;

    const blob = new Blob([content], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }, [narrative]);

  return (
    <div className="space-y-6">
      {/* Main Card */}
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden shadow-sm">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-100 dark:border-gray-700 bg-gradient-to-r from-emerald-50 via-teal-50/50 to-transparent dark:from-emerald-900/20 dark:via-teal-900/10 dark:to-transparent">
          <div className="flex items-center gap-3">
            <div className="p-2.5 bg-gradient-to-br from-emerald-500 to-teal-500 rounded-xl shadow-lg shadow-emerald-500/20">
              <Sparkles className="w-5 h-5 text-white" />
            </div>
            <div>
              <h3 className="text-base font-bold text-gray-900 dark:text-gray-100">
                Science Funding Intelligence Report
              </h3>
              <p className="text-xs text-gray-500 dark:text-gray-300">
                AI-powered analysis of science funding landscape trends
              </p>
            </div>
            {savedNarrative && (
              <span className="flex items-center gap-1.5 px-2.5 py-1 text-xs bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-400 rounded-full font-medium">
                <Clock className="w-3 h-3" />
                Saved
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            {narrative && (
              <button
                onClick={handleDownloadNarrative}
                className="flex items-center gap-2 px-3 py-2 text-xs font-medium bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
              >
                <Download className="w-3.5 h-3.5" />
                Export
              </button>
            )}
            {!loadingSavedNarrative && !narrative && (
              <button
                onClick={handleGenerateNarrative}
                disabled={loadingNarrative}
                className="flex items-center gap-2 px-4 py-2 text-sm font-medium bg-gradient-to-r from-emerald-500 to-teal-500 text-white rounded-lg hover:from-emerald-600 hover:to-teal-600 disabled:opacity-50 transition-all shadow-md shadow-emerald-500/20"
              >
                {loadingNarrative ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Generating...
                  </>
                ) : (
                  <>
                    <FileText className="w-4 h-4" />
                    Generate Report
                  </>
                )}
              </button>
            )}
          </div>
        </div>

        {/* Content */}
        <div className="p-5">
          {loadingSavedNarrative && (
            <div className="flex flex-col items-center justify-center gap-3 py-16">
              <div className="relative">
                <div className="w-12 h-12 rounded-full bg-emerald-100 dark:bg-emerald-900/30 flex items-center justify-center">
                  <Loader2 className="w-6 h-6 animate-spin text-emerald-500" />
                </div>
              </div>
              <span className="text-sm text-gray-500 dark:text-gray-300">Loading saved report...</span>
            </div>
          )}

          {!loadingSavedNarrative && !narrative && !narrativeError && (
            <div className="text-center py-16">
              <div className="relative inline-block mb-6">
                <div className="w-20 h-20 rounded-2xl bg-gradient-to-br from-emerald-100 to-teal-100 dark:from-emerald-900/30 dark:to-teal-900/30 flex items-center justify-center">
                  <FileText className="w-10 h-10 text-emerald-400 dark:text-emerald-500" />
                </div>
                <div className="absolute -bottom-1 -right-1 w-8 h-8 rounded-lg bg-teal-500 flex items-center justify-center">
                  <Sparkles className="w-4 h-4 text-white" />
                </div>
              </div>
              <h4 className="text-lg font-semibold text-gray-800 dark:text-gray-200 mb-2">
                Generate Your Science Funding Intelligence Report
              </h4>
              <p className="text-sm text-gray-500 dark:text-gray-300 max-w-lg mx-auto mb-6">
                Our AI will analyze your science funding data to generate a comprehensive report including
                trend analysis, thematic insights, escalation assessment, and forward-looking recommendations.
              </p>
              <div className="flex flex-wrap justify-center gap-2 text-xs text-gray-500 dark:text-gray-300">
                <span className="px-2 py-1 bg-gray-100 dark:bg-gray-700 rounded">Trend Analysis</span>
                <span className="px-2 py-1 bg-gray-100 dark:bg-gray-700 rounded">Theme Detection</span>
                <span className="px-2 py-1 bg-gray-100 dark:bg-gray-700 rounded">Escalation Signals</span>
                <span className="px-2 py-1 bg-gray-100 dark:bg-gray-700 rounded">Future Outlook</span>
              </div>
            </div>
          )}

          {narrativeError && (
            <div className="flex items-center gap-4 p-4 bg-red-50 dark:bg-red-900/20 rounded-xl border border-red-200 dark:border-red-800">
              <div className="p-3 bg-red-100 dark:bg-red-900/40 rounded-lg">
                <AlertCircle className="w-6 h-6 text-red-500" />
              </div>
              <div>
                <p className="text-sm font-semibold text-red-700 dark:text-red-300">Report Generation Failed</p>
                <p className="text-xs text-red-600 dark:text-red-400 mt-0.5">{narrativeError}</p>
              </div>
            </div>
          )}

          {narrative && (
            <div className="space-y-6">
              {/* Stats Row */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <div className="relative overflow-hidden p-4 bg-gradient-to-br from-emerald-500 to-emerald-600 rounded-xl text-white">
                  <BarChart3 className="absolute -right-2 -bottom-2 w-16 h-16 text-emerald-400/30" />
                  <div className="relative">
                    <span className="text-xs font-medium text-emerald-100 uppercase tracking-wide">Articles</span>
                    <p className="text-2xl font-bold mt-1">{narrative.data_summary.total_articles.toLocaleString()}</p>
                  </div>
                </div>
                <div className="relative overflow-hidden p-4 bg-gradient-to-br from-teal-500 to-teal-600 rounded-xl text-white">
                  <Tag className="absolute -right-2 -bottom-2 w-16 h-16 text-teal-400/30" />
                  <div className="relative">
                    <span className="text-xs font-medium text-teal-100 uppercase tracking-wide">Categorized</span>
                    <p className="text-2xl font-bold mt-1">{narrative.data_summary.total_categorized.toLocaleString()}</p>
                  </div>
                </div>
                <div className="relative overflow-hidden p-4 bg-gradient-to-br from-blue-500 to-blue-600 rounded-xl text-white">
                  <Calendar className="absolute -right-2 -bottom-2 w-16 h-16 text-blue-400/30" />
                  <div className="relative">
                    <span className="text-xs font-medium text-blue-100 uppercase tracking-wide">Period</span>
                    <p className="text-sm font-bold mt-1">{narrative.data_summary.date_range.start}</p>
                    <p className="text-xs text-blue-200">to {narrative.data_summary.date_range.end}</p>
                  </div>
                </div>
                <div className="relative overflow-hidden p-4 bg-gradient-to-br from-cyan-500 to-cyan-600 rounded-xl text-white">
                  <Sparkles className="absolute -right-2 -bottom-2 w-16 h-16 text-cyan-400/30" />
                  <div className="relative">
                    <span className="text-xs font-medium text-cyan-100 uppercase tracking-wide">Categories</span>
                    <p className="text-2xl font-bold mt-1">{Object.keys(narrative.data_summary.categories || {}).length}</p>
                  </div>
                </div>
              </div>

              {/* Key Metrics Bar */}
              <KeyMetricsBar dataSummary={narrative.data_summary} />

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
                          document.getElementById(`science-section-${idx}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
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
                  <div key={idx} id={`science-section-${idx}`}>
                    <SectionCard title={section.title} content={section.content} index={idx} />
                  </div>
                ))}
              </div>

              {/* If no sections parsed, show raw content */}
              {sections.length === 0 && narrative.narrative && (
                <div className="p-6 bg-gray-50 dark:bg-gray-750 rounded-xl border border-gray-200 dark:border-gray-700">
                  <div className="prose prose-sm dark:prose-invert max-w-none">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {narrative.narrative}
                    </ReactMarkdown>
                  </div>
                </div>
              )}

              {/* AI Disclosure Footer */}
              <AIDisclosureFooter
                modelUsed="GPT-4.1-mini (OpenAI)"
                generatedAt={narrative.generated_at}
                purpose="To analyze science funding data through a critical lens, identifying patterns of funding changes, research impact, and institutional effects on scientific infrastructure"
              />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
