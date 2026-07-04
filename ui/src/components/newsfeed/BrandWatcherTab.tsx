/**
 * Brand Watcher Tab Component
 * Main container for brand intelligence dashboard
 */

import { useState, useCallback, useEffect, useMemo, useRef } from 'react';
import {
  RefreshCw, AlertCircle, X, Loader2, Target, Plus, Settings, Sparkles,
  BarChart3, TrendingUp, Users, FileText, ChevronDown, ChevronRight,
  Trash2, Edit2, ToggleLeft, ToggleRight, Zap, Clock, Play, Calendar,
  Download, AlertTriangle, Eye, Star, Image, FileDown, Copy, Check, Printer, Search, Bell,
  AtSign, UserCircle, Tag, BadgeCheck, Landmark,
} from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend, Cell, AreaChart, Area, PieChart, Pie, ReferenceLine } from 'recharts';
import { useBrandWatcher } from '../../hooks/useBrandWatcher';
import { ChartDownloadButton } from './ChartDownloadButton';
import { ExportService } from '../../services/exportService';
import { downloadBrandWatcherReport } from '../../services/brandReportHtml';
import { downloadSocialReport } from '../../services/socialReportHtml';
import { cleanSocialText, stripSocialMarkdown } from '../../services/socialText';
import {
  buildAccountProfile, getAccountProfile, listAccountProfiles, setAccountTags, setAccountAnnotation,
  deepDiveAccount, deleteAccountProfile, type BWAccountProfile, type BWAccountDeepDive,
} from '../../services/socialProfileApi';
import { downloadAccountReport } from '../../services/socialProfileReportHtml';
import {
  classifyArticles, getClassifyStatus, generateNarrative, getLatestNarrative,
  generateCategoryInsight, suggestKeywords, setupBrandMonitoring, getSchedules, createSchedule, deleteSchedule,
  getComparison, getShareOfVoice, getSocialPosts,
  runScheduleNow, getSentimentTrends, getBrandAlerts, exportBrandData, updateBrandConfig,
  getAlertConfig, updateAlertConfig, listAlertEvents, ackAlertEvent, evaluateAlertsNow, setFindingState,
  getOfficialSourcesStatus, pollOfficialSourcesNow, getStorySiblings, getArticles,
  type BWAlertConfig, type BWAlertEvent, type BWBrandSources,
  retrainClassifier, setupSocialMonitoring, CATEGORY_COLORS, CATEGORY_SHORT_NAMES,
  type Brand, type BrandCreate, type BWArticle, type BWSavedNarrative,
  type BWCategoryInsightResponse, type BWSchedule, type BWSentimentTrend, type BWAlert,
} from '../../services/brandWatcherApi';

// The brand/entity a social post belongs to, derived from its topic
// ("Brand Monitoring Wiley" -> "Wiley"). Module-level so it's referentially stable.
const socialBrandOf = (p: { topic?: string | null }) =>
  (p.topic || '').replace(/^Brand Monitoring\s+/i, '').trim() || 'Other';

// Sentiment grouping order for the CSV export (positive/fans first, critics grouped).
const SOCIAL_SENT_ORDER: Record<string, number> = { positive: 0, neutral: 1, negative: 2, unrated: 3 };

// Complaint themes for negative-post grouping ("what are they angry about").
// Keyword-based on purpose: zero LLM cost per refresh; themes are cumulative
// (a post can match several) and the remainder buckets as "other".
const SOCIAL_NEG_THEMES: Array<{ key: string; label: string; re: RegExp }> = [
  { key: 'legal', label: 'Legal / IP', re: /\b(lawsuit|sued|sues|court|copyright|infringe\w*|piracy|legal action|settlement|dmca)\b/i },
  { key: 'integrity', label: 'Ethics / integrity', re: /\b(fraud\w*|scam|predatory|unethical|greed\w*|exploit\w*|plagiar\w*|retract\w*|paper mill)\b/i },
  { key: 'pricing', label: 'Pricing / fees', re: /\b(pricing|priced?|costs?|costly|expensive|fees?|apcs?|charged?|charges|unaffordable|overpriced)\b/i },
  { key: 'access', label: 'Access / paywalls', re: /\b(paywall\w*|open access|locked|inaccessible|subscription|log ?in wall)\b/i },
  { key: 'quality', label: 'Quality / errors', re: /\b(errors?|typos?|mistakes?|wrong answers?|poor quality|shoddy|misprint\w*|badly (written|edited))\b/i },
  { key: 'service', label: 'Service / support', re: /\b(customer service|support ticket|refunds?|no (reply|response)|unresponsive|complaints?)\b/i },
  { key: 'exams', label: 'Exams / education', re: /\b(exams?|marking|graded?|grading|a-levels?|gcses?|sats?|syllabus|past papers?)\b/i },
  { key: 'ai', label: 'AI / data use', re: /\b(ai|artificial intelligence|llms?|machine learning|training data|chatgpt|genai)\b/i },
];
const socialThemeBlobOf = (p: { title?: string | null; summary?: string | null }) => `${p.title || ''} ${p.summary || ''}`;

// Alert rules + tunable thresholds — MUST mirror _ADVERSE_RULE_DEFAULTS in
// app/tasks/brand_watcher_monitor.py (values here are only the display defaults;
// the server merges bw_alert_config.rules over its own defaults).
const BW_ALERT_RULE_DEFS: Array<{ key: string; label: string; params: Array<{ k: string; label: string; def: number; step?: number }> }> = [
  { key: 'neg_social_spike', label: 'Negative-social spike', params: [
    { k: 'min_prior', label: 'min prior', def: 2 }, { k: 'multiplier', label: 'multiplier', def: 2, step: 0.5 }] },
  { key: 'high_reach_negative', label: 'High-reach negative post', params: [
    { k: 'min_engagement', label: 'min engagement', def: 50 }, { k: 'window_hours', label: 'window (h)', def: 24 }] },
  { key: 'news_net_negative', label: 'News net-negative', params: [
    { k: 'net_threshold', label: 'net ≤', def: -20 }, { k: 'min_scored', label: 'min scored', def: 5 }, { k: 'window_days', label: 'window (d)', def: 7 }] },
  { key: 'category_spike', label: 'Category spike', params: [
    { k: 'multiplier', label: 'multiplier', def: 2, step: 0.5 }, { k: 'min_count', label: 'min count', def: 5 }] },
  { key: 'high_risk_finding', label: 'High-severity risk finding', params: [
    { k: 'window_hours', label: 'window (h)', def: 24 }] },
  { key: 'neg_consensus_story', label: 'Negative-consensus story', params: [
    { k: 'min_scored', label: 'min sources', def: 3 }, { k: 'neg_share', label: 'neg share', def: 0.7, step: 0.05 }, { k: 'window_hours', label: 'window (h)', def: 48 }] },
  { key: 'new_critic', label: 'New critic', params: [
    { k: 'recent_hours', label: 'window (h)', def: 48 }, { k: 'min_recent_neg', label: 'min posts', def: 2 }, { k: 'min_engagement_single', label: 'or engagement ≥', def: 50 }, { k: 'lookback_days', label: 'lookback (d)', def: 30 }] },
  { key: 'coordinated_negative', label: 'Coordinated negativity', params: [
    { k: 'min_authors', label: 'min accounts', def: 3 }, { k: 'window_hours', label: 'window (h)', def: 72 }] },
];

// Extracted outside the component to prevent re-creation on every render (which causes focus loss)
function KeywordTagInput({ label, keywords, inputValue, setInputValue, onAdd, onRemove }: {
  label: string;
  keywords: string[];
  inputValue: string;
  setInputValue: (v: string) => void;
  onAdd: (value: string) => void;
  onRemove: (value: string) => void;
}) {
  return (
    <div>
      <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">{label}</label>
      <div className="flex flex-wrap gap-1 mb-1">
        {keywords.map(kw => (
          <span key={kw} className="inline-flex items-center gap-1 px-2 py-0.5 bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 rounded text-xs">
            {kw}
            <button onClick={() => onRemove(kw)} className="hover:text-red-500">
              <X className="w-3 h-3" />
            </button>
          </span>
        ))}
      </div>
      <input
        type="text"
        value={inputValue}
        onChange={e => setInputValue(e.target.value)}
        onKeyDown={e => {
          if (e.key === 'Enter' || e.key === ',') {
            e.preventDefault();
            onAdd(inputValue);
            setInputValue('');
          }
        }}
        placeholder="Type and press Enter"
        className="w-full px-2 py-1 text-sm border border-gray-200 dark:border-gray-700 rounded bg-white dark:bg-gray-800 dark:text-gray-100"
      />
    </div>
  );
}

interface BrandWatcherTabProps {
  onArticleClick?: (article: { uri: string; title?: string; [key: string]: any },
                    relatedArticles?: any[]) => void;
}

type SubTab = 'dashboard' | 'overview' | 'analysis' | 'comparison' | 'insights' | 'articles' | 'social' | 'accounts';

export function BrandWatcherTab({ onArticleClick }: BrandWatcherTabProps) {
  const {
    brands, topics, stats, categories, temporalData, articles,
    comparison, shareOfVoice, social, config,
    totalArticles, totalPages,
    loading, loadingStats, loadingCategories, loadingArticles, loadingSocial,
    error,
    updateConfig, clearError, refresh,
    fetchComparison, fetchShareOfVoice, fetchSocial,
    createBrand, updateBrand: updateBrandFn, deleteBrand: deleteBrandFn, toggleBrand: toggleBrandFn,
    setPrimary,
  } = useBrandWatcher();

  const [activeTab, setActiveTab] = useState<SubTab>('dashboard');
  const [socialMinRel, setSocialMinRel] = useState(0.4);  // default to evaluated, on-brand posts only
  const [socialInclUneval, setSocialInclUneval] = useState(false);  // include not-yet-scored posts (only matters at min rel = All)
  // Each social lane picks its own network + is filtered/sorted independently (lane A / lane B).
  const [showFansCritics, setShowFansCritics] = useState(true);
  const [exportingSocialReport, setExportingSocialReport] = useState(false);
  // Social scope toggle: primary brand only vs primary + competitors (adverse media
  // screening usually starts brand-only, widens for competitive context).
  const [socialScope, setSocialScope] = useState<'selected' | 'all'>('selected');
  // Dismissed problem-alerts (anti-wallpaper): keys are rule|brand|time-bucket so a
  // dismissal expires when the underlying window rolls over. Persisted locally.
  const [dismissedAlerts, setDismissedAlerts] = useState<Set<string>>(() => {
    try { return new Set(JSON.parse(localStorage.getItem('bw_dismissed_alerts') || '[]')); } catch { return new Set(); }
  });
  // Server-side alerting (bw_alert_config / bw_alert_events)
  const [alertCfg, setAlertCfg] = useState<BWAlertConfig | null>(null);
  const [alertEvents, setAlertEvents] = useState<BWAlertEvent[]>([]);
  const [showAlertSettings, setShowAlertSettings] = useState(false);
  const [alertSaving, setAlertSaving] = useState(false);
  const [alertRecipientsText, setAlertRecipientsText] = useState('');
  const loadAlertData = useCallback(() => {
    listAlertEvents(true, 20).then(setAlertEvents).catch(() => {});
  }, []);
  // Official/scholarly sources modal (SEC EDGAR, CourtListener, regulations.gov, Crossref, OpenAlex)
  const [showSourcesModal, setShowSourcesModal] = useState(false);
  const [sourcesStatus, setSourcesStatus] = useState<BWBrandSources[] | null>(null);
  const [sourcesSaving, setSourcesSaving] = useState(false);
  const [sourcesPolling, setSourcesPolling] = useState(false);
  const [sourcesPollMsg, setSourcesPollMsg] = useState<string | null>(null);
  const toggleBrandSource = useCallback((brandId: number, key: string) => {
    setSourcesStatus(prev => prev && prev.map(b => b.brand_id !== brandId ? b : {
      ...b, sources: b.sources.map(s => s.key !== key ? s : { ...s, enabled: !s.enabled }),
    }));
  }, []);
  // Open an article in the shared detail panel. Pass ALL fields we hold (the
  // panel's by-uri fetch can miss for alert-payload/syndicated URLs — the click
  // data is then the only source), and for ×N-source stories attach the sibling
  // republications so the panel renders the news-feed multi-article format.
  const openArticle = useCallback(async (a: any) => {
    let related: any[] | undefined;
    if (a.story_group_id && (a.story_size || 1) >= 2) {
      try {
        const sibs = await getStorySiblings(a.story_group_id, a.brand_id ?? null);
        related = sibs.filter(s => s.uri !== a.uri).map(s => ({ ...s, similarity_score: 1 }));
      } catch { /* siblings are best-effort */ }
    }
    onArticleClick?.({ ...a }, related);
  }, [onArticleClick]);
  // Competitor social benchmark: a small all-brands snapshot fetched independently
  // of the scope toggle, so "you vs competitor average" works even in "X only" view.
  const [benchSocial, setBenchSocial] = useState<Record<string, { pos: number; neg: number; scored: number }> | null>(null);
  const loadBenchSocial = useCallback(() => {
    if (brands.length < 2) { setBenchSocial(null); return; }
    const topics = brands.map(b => `Brand Monitoring ${b.display_name}`);
    getSocialPosts(topics, config.daysBack, 0.4, undefined, false, { limit: 500 }).then(data => {
      const agg: Record<string, { pos: number; neg: number; scored: number }> = {};
      (data.posts || []).forEach((p: any) => {
        const sen = socialSentimentOf(p.sentiment);
        if (sen === 'unrated') return;
        const b = socialBrandOf(p);
        if (!agg[b]) agg[b] = { pos: 0, neg: 0, scored: 0 };
        if (sen === 'positive') agg[b].pos++; else if (sen === 'negative') agg[b].neg++;
        agg[b].scored++;
      });
      setBenchSocial(agg);
    }).catch(() => setBenchSocial(null));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [brands, config.daysBack]);
  // Wider adverse-analysis pool for the dashboard: the paged `articles` state
  // follows the Articles tab (one page), which starves "what the negative
  // coverage is about" — fetch up to 200 recent articles for dashboard math.
  const [dashArticles, setDashArticles] = useState<BWArticle[] | null>(null);
  const loadDashArticles = useCallback(() => {
    getArticles({
      brand_ids: config.selectedBrandIds.length ? config.selectedBrandIds : undefined,
      topics: config.selectedTopics.length ? config.selectedTopics : undefined,
      days_back: config.daysBack,
      page: 1,
      per_page: 200,
    }).then(r => setDashArticles(r.articles)).catch(() => {});
  }, [config.selectedBrandIds, config.selectedTopics, config.daysBack]);
  // Per-finding review state (optimistic local overlay over articles payload)
  const [reviewOverrides, setReviewOverrides] = useState<Record<string, string>>({});
  const setReview = useCallback(async (uri: string, brandId: number | null, status: 'reviewed' | 'escalated' | 'dismissed') => {
    if (!brandId) return;
    setReviewOverrides(prev => ({ ...prev, [`${uri}|${brandId}`]: status }));
    try { await setFindingState(uri, brandId, status); } catch (e) { console.error('finding state failed', e); }
  }, []);
  const reviewStatusOf = useCallback((a: any) => reviewOverrides[`${a.uri}|${a.brand_id}`] || a.review_status || 'new', [reviewOverrides]);

  const dismissAlert = useCallback((k: string) => {
    setDismissedAlerts(prev => {
      const n = new Set(prev); n.add(k);
      try { localStorage.setItem('bw_dismissed_alerts', JSON.stringify(Array.from(n).slice(-200))); } catch { /* ignore */ }
      return n;
    });
  }, []);
  // Auto-loaded account profiles (metadata) for top fans/critics: platform:handle ->
  // profile | 'pending' | 'missing'. Missing ones are deep-analyzed in the background
  // and persist in social_accounts, so each account is built at most once.
  const [fcProfiles, setFcProfiles] = useState<Record<string, BWAccountProfile | 'pending' | 'missing'>>({});
  // Social CSV export modal
  const [showSocialExport, setShowSocialExport] = useState(false);
  const [expBrands, setExpBrands] = useState<number[]>([]);
  const [expSentiments, setExpSentiments] = useState<string[]>([]);
  const [expStart, setExpStart] = useState('');
  const [expEnd, setExpEnd] = useState('');
  const [expRelevance, setExpRelevance] = useState<'onbrand' | 'scored' | 'all'>('onbrand');
  const [exportingSocial, setExportingSocial] = useState(false);
  const [bskyFilter, setBskyFilter] = useState<{ platforms: string[]; sentiments: string[]; entity?: string; search: string; sort: 'recent' | 'oldest' | 'relevance' }>({ platforms: [], sentiments: [], search: '', sort: 'recent' });
  const [feedFilter, setFeedFilter] = useState<{ platforms: string[]; sentiments: string[]; entity?: string; search: string; sort: 'recent' | 'oldest' | 'relevance' }>({ platforms: [], sentiments: [], search: '', sort: 'recent' });
  // --- Accounts (per-account xpoz profiles) ---
  const [accountsList, setAccountsList] = useState<BWAccountProfile[]>([]);
  const [accountProfile, setAccountProfile] = useState<BWAccountProfile | null>(null);
  const [accSearch, setAccSearch] = useState<{ platform: string; handle: string }>({ platform: 'twitter', handle: '' });
  const [accLoading, setAccLoading] = useState(false);
  const [accError, setAccError] = useState<string | null>(null);
  const [accTagInput, setAccTagInput] = useState('');
  const [accNoteInput, setAccNoteInput] = useState('');
  const [accDeepDive, setAccDeepDive] = useState<BWAccountDeepDive | null>(null);
  const [accDeepLoading, setAccDeepLoading] = useState(false);
  const [enablingSocial, setEnablingSocial] = useState(false);
  // The social intro/onboarding banner should not nag forever: it auto-hides once
  // posts have been collected, and can be dismissed manually (remembered per browser).
  const [socialIntroDismissed, setSocialIntroDismissed] = useState<boolean>(() => {
    try { return localStorage.getItem('bw_social_intro_dismissed') === '1'; } catch { return false; }
  });
  const [showBrandConfig, setShowBrandConfig] = useState(false);
  const [showClassifyModal, setShowClassifyModal] = useState(false);
  const [classifyRunId, setClassifyRunId] = useState<number | null>(null);
  const [classifyStatus, setClassifyStatus] = useState<string>('');
  const [narrative, setNarrative] = useState<BWSavedNarrative | null>(null);
  const [loadingNarrative, setLoadingNarrative] = useState(false);
  const [generatingNarrative, setGeneratingNarrative] = useState(false);
  const [categoryInsight, setCategoryInsight] = useState<BWCategoryInsightResponse | null>(null);
  const [loadingInsight, setLoadingInsight] = useState(false);
  const [sentimentTrends, setSentimentTrends] = useState<BWSentimentTrend[]>([]);
  const [brandAlerts, setBrandAlerts] = useState<BWAlert[]>([]);
  const [expandedAlerts, setExpandedAlerts] = useState<Set<string>>(new Set());
  const [drillDownCategory, setDrillDownCategory] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const [exportingReport, setExportingReport] = useState(false);
  const [exportMenuOpen, setExportMenuOpen] = useState(false);
  const exportMenuRef = useRef<HTMLDivElement>(null);
  const [selectedCompetitor, setSelectedCompetitor] = useState<number | null>(null);
  const [showBrandDropdown, setShowBrandDropdown] = useState(false);
  const [compCategoryFilter, setCompCategoryFilter] = useState<string | null>(null);
  const [showCompCatDropdown, setShowCompCatDropdown] = useState(false);

  // Brand form state
  const [brandForm, setBrandForm] = useState<Partial<BrandCreate>>({});
  const [editingBrandId, setEditingBrandId] = useState<number | null>(null);
  const [brandKeywordInput, setBrandKeywordInput] = useState('');
  const [productKeywordInput, setProductKeywordInput] = useState('');
  const [peopleKeywordInput, setPeopleKeywordInput] = useState('');
  const [competitorKeywordInput, setCompetitorKeywordInput] = useState('');
  const [suggestingKeywords, setSuggestingKeywords] = useState(false);
  const [setupMonitoring, setSetupMonitoring] = useState(true);
  const [monitoringStatus, setMonitoringStatus] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  // --- Social: client-side filtering + analytics derived from the loaded posts ---
  const SOCIAL_SENTIMENT_COLORS: Record<string, string> = {
    positive: '#10b981', neutral: '#94a3b8', negative: '#ef4444', unrated: '#d1d5db',
  };
  // Per-network brand colors + display labels (news_source 'xpoz:twitter' -> platform 'twitter' -> 'X').
  const PLATFORM_COLORS: Record<string, string> = {
    twitter: '#0f172a', bluesky: '#0ea5e9', reddit: '#f97316',
    instagram: '#d6249f', tiktok: '#ff0050', social: '#6b7280',
  };
  const PLATFORM_LABELS: Record<string, string> = {
    twitter: 'X', bluesky: 'Bluesky', reddit: 'Reddit',
    instagram: 'Instagram', tiktok: 'TikTok', social: 'Other',
  };
  const PLATFORM_ORDER = ['twitter', 'bluesky', 'reddit', 'instagram', 'tiktok', 'social'];
  const platColor = (p: string) => PLATFORM_COLORS[p] || PLATFORM_COLORS.social;
  const platLabel = (p: string) => PLATFORM_LABELS[p] || p;
  const fmtCount = (n?: number | null) => n == null ? null : (n >= 1000 ? `${(n / 1000).toFixed(n >= 10000 ? 0 : 1)}k` : `${n}`);
  const socialSentimentOf = (s: string | null): 'positive' | 'neutral' | 'negative' | 'unrated' => {
    const t = (s || '').toLowerCase();
    // Social eval emits Positive/Neutral/Negative; NEWS enrichment emits richer labels
    // (Optimistic/Cautious/Concerned/Pessimistic/Critical/Alarming) — map both, or the
    // adverse screens silently miss negative news ("Concerned" used to fall to unrated).
    if (t.includes('pos') || t.includes('optimis')) return 'positive';
    if (t.includes('neg') || t.includes('concern') || t.includes('pessimis') || t.includes('critical') || t.includes('alarm')) return 'negative';
    if (t.includes('neu') || t.includes('cautious') || t === 'mixed') return 'neutral';
    return 'unrated';
  };
  // Social posts store the author in the title ("Post by @handle") and the real text in summary.
  const socialAuthorOf = (p: { title?: string | null; news_source?: string | null; platform?: string }) => {
    const m = (p.title || '').match(/@([\w.\-]+)/);
    return m ? `@${m[1]}` : (p.news_source || p.platform || 'unknown');
  };
  const socialBodyOf = (p: { title?: string | null; summary?: string | null }) => {
    const body = (p.summary || '').trim();
    if (body) return body;
    const stripped = (p.title || '').replace(/^Post by @[\w.\-]+\s*/i, '').trim();
    return stripped || (p.title || '').trim() || '(no text)';
  };
  // Social posts arrive as raw text that often contains markdown/HTML syntax
  // (**bold**, ### headings, ---, [text](url), bare links, escaped newlines, entities,
  // mojibake). Clean it, escape it, then re-apply a safe markdown subset. Everything is
  // escaped before any tag is injected, so it's XSS-safe.
  const socialBodyHtml = (p: { title?: string | null; summary?: string | null }) => {
    const esc = (s: string) => s
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    const link = (href: string, text: string) =>
      `<a href="${esc(href)}" target="_blank" rel="noopener noreferrer" class="text-blue-600 dark:text-blue-400 hover:underline break-all">${text}</a>`;
    let html = esc(cleanSocialText(socialBodyOf(p)));
    html = html.replace(/^\s*#{1,6}\s*/gm, '');                 // heading marks -> plain
    html = html.replace(/^\s*([-*_]\s*){3,}\s*$/gm, '');        // --- *** ___ rules -> drop
    html = html.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, (_m, label, url) => link(url, label));
    html = html.replace(/(^|[^"=>])((?:https?:\/\/)[^\s<]+)/g, (_m, pre, url) => `${pre}${link(url, url)}`);
    html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/(^|[^*])\*([^*\s][^*]*?)\*(?!\*)/g, '$1<em>$2</em>');
    html = html.replace(/^\s*[-*]\s+/gm, '• ');                 // list bullets
    html = html.replace(/\n{2,}/g, '\n');                       // collapse blank lines (feed is line-clamped)
    return html;
  };
  // Brand ordering + colors for grouping social tags by entity. Primary brand
  // (Wiley) ranks first, competitors follow alphabetically — used for the entity
  // filter order and the Wiley-first CSV sort.
  const brandRank = useMemo(() => {
    const ordered = [...brands].sort((a, b) =>
      (b.is_primary ? 1 : 0) - (a.is_primary ? 1 : 0) || a.display_name.localeCompare(b.display_name));
    const m: Record<string, number> = {};
    ordered.forEach((b, i) => { m[b.display_name] = i; });
    return m;
  }, [brands]);
  const brandColorOf = (name: string) => brands.find(b => b.display_name === name)?.color || '#6b7280';
  // Loaded posts grouped by brand/entity, each with its triggering keywords — drives
  // the per-lane entity filter (pick a whole brand, e.g. "All Wiley posts", or a keyword).
  const socialEntityOptions = useMemo(() => {
    const g: Record<string, { count: number; kws: Record<string, number> }> = {};
    (social?.posts || []).forEach(p => {
      const bn = socialBrandOf(p);
      if (!g[bn]) g[bn] = { count: 0, kws: {} };
      g[bn].count++;
      (p.matched_keywords || []).forEach(k => { g[bn].kws[k] = (g[bn].kws[k] || 0) + 1; });
    });
    return Object.entries(g).map(([name, v]) => ({
      name, count: v.count,
      isPrimary: !!brands.find(b => b.display_name === name)?.is_primary,
      keywords: Object.entries(v.kws).sort((a, b) => b[1] - a[1]),
    })).sort((a, b) => (brandRank[a.name] ?? 99) - (brandRank[b.name] ?? 99) || a.name.localeCompare(b.name));
  }, [social, brands, brandRank]);

  // Fans & Critics: aggregate on-brand (relevance ≥ 0.4) scored posts by author, then
  // rank consistently-positive authors (fans) vs consistently-negative (critics) by net
  // sentiment. Each links through to the Account Profile.
  const fansCritics = useMemo(() => {
    // Own-brand handles (e.g. @wileyhealth) are the brand promoting itself, not
    // third-party advocates — exclude them from Fans. A handle is "own" when its
    // leading segment starts with any of the brand's normalized keywords/slug.
    const norm = (s: string) => (s || '').toLowerCase().replace(/[^a-z0-9]/g, '');
    const ownTokens: Record<string, string[]> = {};
    brands.forEach(b => {
      ownTokens[b.display_name] = Array.from(new Set([b.name, ...(b.brand_keywords || [])].map(norm).filter(t => t.length >= 3)));
    });
    const isOwn = (handle: string, brand: string) => {
      const lead = norm((handle || '').split('.')[0]);
      return !!lead && (ownTokens[brand] || []).some(t => lead.startsWith(t));
    };
    const engOf = (p: any) => {
      const m = p.social_meta || {};
      return (m.likes || 0) + (m.reposts || 0) * 2 + (m.comments || 0) + (m.plays || 0) / 100;
    };
    const byAuthor: Record<string, {
      author: string; platform: string; brand: string;
      pos: number; neg: number; neu: number; total: number;
      posEng: number; negEng: number;              // engagement on aligned posts
      firstAt: string; lastAt: string;             // aligned-post date span
      recentAligned: number; priorAligned: number; // window halves, for the trend arrow
    }> = {};
    const dates = (social?.posts || []).map(p => p.publication_date || '').filter(Boolean).sort();
    const midDate = dates.length ? dates[Math.floor(dates.length / 2)] : '';
    (social?.posts || []).forEach(p => {
      if ((p.relevance ?? 0) < 0.4) return;
      const s = socialSentimentOf(p.sentiment);
      if (s === 'unrated') return;
      // Only real author handles — NOT the news_source fallback (e.g. "xpoz:instagram"),
      // which isn't a profileable account. Skip posts we can't attribute to an author.
      const sm = (p as any).social_meta || {};
      const m = (p.title || '').match(/@([\w.\-]+)/);
      const handle = (sm.author || (m ? m[1] : '')).trim();
      if (!handle || handle === 'unknown' || handle.includes(':')) return;
      const key = `${p.platform}:${handle.toLowerCase()}`;
      if (!byAuthor[key]) byAuthor[key] = {
        author: handle, platform: p.platform, brand: socialBrandOf(p),
        pos: 0, neg: 0, neu: 0, total: 0, posEng: 0, negEng: 0,
        firstAt: '', lastAt: '', recentAligned: 0, priorAligned: 0,
      };
      const a = byAuthor[key];
      a[s === 'positive' ? 'pos' : s === 'negative' ? 'neg' : 'neu']++;
      a.total++;
      if (s !== 'neutral') {
        if (s === 'positive') a.posEng += engOf(p); else a.negEng += engOf(p);
        const d = p.publication_date || '';
        if (d) {
          if (!a.firstAt || d < a.firstAt) a.firstAt = d;
          if (!a.lastAt || d > a.lastAt) a.lastAt = d;
          if (midDate && d >= midDate) a.recentAligned++; else a.priorAligned++;
        }
      }
    });
    // Influence score: each aligned post is worth a 5-engagement baseline, plus the
    // real engagement it earned — a critic with one 100-engagement post outranks one
    // with three unseen posts. (Followers show as a chip; they load async from
    // profiles, so they inform the reader, not the ordering.)
    const POST_BASE = 5;
    const spanDays = (a: { firstAt: string; lastAt: string }) =>
      a.firstAt && a.lastAt ? Math.max(0, Math.round((new Date(a.lastAt).getTime() - new Date(a.firstAt).getTime()) / 86400e3)) : 0;
    const arr = Object.values(byAuthor).map(a => ({
      ...a,
      net: a.pos - a.neg,
      own: isOwn(a.author, a.brand),
      damage: a.neg * POST_BASE + a.negEng,
      advocacy: a.pos * POST_BASE + a.posEng,
      spanDays: spanDays(a),
      trend: (a.recentAligned + a.priorAligned) >= 2
        ? (a.recentAligned > a.priorAligned ? 'up' : a.recentAligned < a.priorAligned ? 'down' : 'flat')
        : null as 'up' | 'down' | 'flat' | null,
    }));
    const fans = arr.filter(a => a.net > 0 && !a.own).sort((x, y) => y.advocacy - x.advocacy || y.pos - x.pos).slice(0, 10);
    const critics = arr.filter(a => a.net < 0).sort((x, y) => y.damage - x.damage || y.neg - x.neg).slice(0, 10);
    const ownHidden = arr.filter(a => a.net > 0 && a.own).length;
    return { fans, critics, authors: arr.length, ownHidden };
  }, [social, brands]);

  // Auto deep-analysis for top fans & critics: load stored profiles, build missing
  // ones in the background (sequential, max 4 per pass to be kind to xpoz). Profiles
  // persist server-side, so this is one-time per account.
  useEffect(() => {
    const targets = [...fansCritics.critics.slice(0, 5), ...fansCritics.fans.slice(0, 5)]
      .filter(a => ['twitter', 'bluesky', 'reddit', 'instagram', 'tiktok'].includes(a.platform));
    if (!targets.length) return;
    let cancelled = false;
    (async () => {
      const toBuild: Array<{ platform: string; author: string; key: string }> = [];
      for (const t of targets) {
        const key = `${t.platform}:${t.author.toLowerCase()}`;
        if (fcProfiles[key]) continue;
        setFcProfiles(prev => ({ ...prev, [key]: 'pending' }));
        try {
          const p = await getAccountProfile(t.platform, t.author);
          if (!cancelled) setFcProfiles(prev => ({ ...prev, [key]: p }));
        } catch {
          toBuild.push({ platform: t.platform, author: t.author, key });
        }
      }
      // Build missing profiles sequentially (critics queued before fans above).
      for (const b of toBuild.slice(0, 4)) {
        if (cancelled) return;
        try {
          const p = await buildAccountProfile(b.platform, b.author, selectedBrand?.display_name || null);
          if (!cancelled) setFcProfiles(prev => ({ ...prev, [b.key]: p }));
        } catch {
          if (!cancelled) setFcProfiles(prev => ({ ...prev, [b.key]: 'missing' }));
        }
      }
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fansCritics]);

  // Heuristic account type from the profile bio — a journalist-critic is a media-risk
  // precursor and reads differently from an unhappy customer.
  const accountTypeOf = (p: any): { label: string; cls: string } | null => {
    const bio = (p?.bio || '').toLowerCase();
    if (!bio) return null;
    if (/journalist|reporter|editor(?!ial board)|columnist|correspondent|newsroom|covering .* for/.test(bio))
      return { label: 'press', cls: 'bg-red-50 text-red-600 dark:bg-red-900/20 dark:text-red-400' };
    if (/professor|researcher|ph\.?d|scientist|academic|lecturer|postdoc|faculty/.test(bio))
      return { label: 'academic', cls: 'bg-indigo-50 text-indigo-600 dark:bg-indigo-900/20 dark:text-indigo-400' };
    if (/librar/.test(bio))
      return { label: 'librarian', cls: 'bg-teal-50 text-teal-600 dark:bg-teal-900/20 dark:text-teal-400' };
    if (/\bauthor\b|writer|novelist/.test(bio))
      return { label: 'author', cls: 'bg-amber-50 text-amber-700 dark:bg-amber-900/20 dark:text-amber-400' };
    return null;
  };
  // Metadata chips for a fan/critic row from its auto-built profile.
  const fcMeta = (platform: string, author: string) => {
    const p = fcProfiles[`${platform}:${author.toLowerCase()}`];
    if (!p || p === 'missing') return null;
    if (p === 'pending') return <Loader2 className="w-3 h-3 animate-spin text-gray-300 flex-shrink-0" />;
    const atype = accountTypeOf(p);
    return (
      <span className="flex items-center gap-1 flex-shrink-0" title={`${p.display_name || author}${p.bio ? ` — ${p.bio.slice(0, 140)}` : ''}`}>
        {p.verified && <BadgeCheck className="w-3 h-3 text-blue-500" />}
        {p.followers_count != null && <span className="text-[10px] text-gray-400 font-mono">{fmtCount(p.followers_count)}</span>}
        {atype && <span className={`text-[9px] px-1 py-px rounded-full font-semibold ${atype.cls}`}>{atype.label}</span>}
      </span>
    );
  };
  // Story-level coverage flags (from per-story sentiment mix across syndicated copies):
  // negative consensus = the story's framing is negative across sources, not one outlet's take.
  const isNegConsensus = (a: any) => (a.story_scored || 0) >= 3 && (a.story_neg || 0) / a.story_scored >= 0.7;
  const isPolarized = (a: any) => (a.story_scored || 0) >= 4
    && Math.min(a.story_neg || 0, a.story_pos || 0) / a.story_scored >= 0.3;
  // MBFC factuality chip (shared by dashboard rows and the Articles tab).
  const factualityChip = (f?: string | null) => {
    if (!f) return null;
    const t = f.toLowerCase();
    const cls = t.includes('very high') || t === 'high' ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-900/20 dark:text-emerald-400'
      : t.includes('mixed') || t.includes('mostly') ? 'bg-amber-50 text-amber-700 dark:bg-amber-900/20 dark:text-amber-400'
      : t.includes('low') ? 'bg-red-50 text-red-700 dark:bg-red-900/20 dark:text-red-400'
      : 'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400';
    return <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${cls}`} title="MBFC factual reporting rating">{f}</span>;
  };
  // Escalating/cooling arrow for a fan/critic (recent window-half vs prior half).
  const trendArrow = (t: 'up' | 'down' | 'flat' | null | undefined, kind: 'fan' | 'crit') => {
    if (!t || t === 'flat') return null;
    const up = t === 'up';
    const color = kind === 'crit' ? (up ? 'text-red-500' : 'text-emerald-500') : (up ? 'text-emerald-500' : 'text-gray-400');
    return <span className={`text-[10px] flex-shrink-0 ${color}`}
      title={up ? 'Escalating — more of their posts fall in the recent half of the window' : 'Cooling — their activity is tailing off'}>{up ? '▲' : '▼'}</span>;
  };
  // Author drill-down: set from a fan/critic row ("see their posts"), applied on
  // the social tab on top of the column filters; cleared via the banner chip.
  const [socialAuthorFilter, setSocialAuthorFilter] = useState<{ platform: string; author: string } | null>(null);
  const [socialDayFilter, setSocialDayFilter] = useState<string | null>(null);       // 'YYYY-MM-DD'
  const [socialThemeFilter, setSocialThemeFilter] = useState<string | null>(null);   // theme key | 'other'
  const postAuthorOf = (p: any): string => {
    const sm = p.social_meta || {};
    const m = (p.title || '').match(/@([\w.\-]+)/);
    return ((sm.author || (m ? m[1] : '')) as string).trim().toLowerCase();
  };
  const viewAuthorPosts = (platform: string, author: string) => {
    setSocialAuthorFilter({ platform, author });
    handleTabChange('social');
  };
  // Apply a column's sentiment/search/sort filter to a platform-split post list.
  const filterSortSocial = (posts: any[], f: { platforms?: string[]; sentiments?: string[]; entity?: string; search: string; sort: string }) => {
    const q = f.search.trim().toLowerCase();
    const plats = f.platforms || [];
    const sents = f.sentiments || [];
    const ent = f.entity || '';                       // '' | 'brand::<Name>' | 'kw::<Keyword>'
    const entBrand = ent.startsWith('brand::') ? ent.slice(7) : null;
    const entKw = ent.startsWith('kw::') ? ent.slice(4).toLowerCase() : null;
    const out = posts.filter(p => {
      if (socialAuthorFilter && (p.platform !== socialAuthorFilter.platform
        || postAuthorOf(p) !== socialAuthorFilter.author.toLowerCase())) return false;
      if (socialDayFilter && (p.publication_date || '').slice(0, 10) !== socialDayFilter) return false;
      if (socialThemeFilter) {
        if (socialSentimentOf(p.sentiment) !== 'negative') return false;
        const blob = socialThemeBlobOf(p);
        const th = SOCIAL_NEG_THEMES.find(t => t.key === socialThemeFilter);
        if (th ? !th.re.test(blob) : SOCIAL_NEG_THEMES.some(t => t.re.test(blob))) return false;
      }
      if (plats.length && !plats.includes(p.platform)) return false;
      if (sents.length && !sents.includes(socialSentimentOf(p.sentiment))) return false;
      if (entBrand && socialBrandOf(p) !== entBrand) return false;
      if (entKw && !(p.matched_keywords || []).some((k: string) => k.toLowerCase() === entKw)) return false;
      if (q && !`${p.title || ''} ${p.summary || ''} ${p.social_meta?.author || ''}`.toLowerCase().includes(q)) return false;
      return true;
    });
    return out.sort((a, b) => {
      if (f.sort === 'relevance') return (b.relevance ?? -1) - (a.relevance ?? -1);
      const da = a.publication_date || '', db = b.publication_date || '';
      return f.sort === 'oldest' ? da.localeCompare(db) : db.localeCompare(da);
    });
  };
  const socialView = useMemo(() => {
    if (!social) return null;
    const posts = social.posts || [];
    const sentCounts = { positive: 0, neutral: 0, negative: 0, unrated: 0 };
    const platCounts: Record<string, number> = {};
    const byDay: Record<string, any> = {};
    posts.forEach(p => {
      const s = socialSentimentOf(p.sentiment);
      sentCounts[s]++;
      platCounts[p.platform] = (platCounts[p.platform] || 0) + 1;
      const d = (p.publication_date || '').slice(0, 10);
      if (d) {
        if (!byDay[d]) byDay[d] = { date: d, positive: 0, neutral: 0, negative: 0, unrated: 0 };
        byDay[d][s]++;
      }
    });
    const scored = sentCounts.positive + sentCounts.neutral + sentCounts.negative;
    const netSentiment = scored ? Math.round(((sentCounts.positive - sentCounts.negative) / scored) * 100) : null;
    const sentPie = (['positive', 'neutral', 'negative', 'unrated'] as const)
      .map(k => ({ name: k, value: sentCounts[k] })).filter(d => d.value > 0);
    const platPie = Object.entries(platCounts).map(([name, value]) => ({ name, value }));
    const timeline = Object.values(byDay).sort((a: any, b: any) => a.date.localeCompare(b.date));
    // Platforms present, in canonical order — drives the lane filter chips.
    const platforms = PLATFORM_ORDER.filter(pl => platCounts[pl]);
    // Perception by network: net sentiment (%pos − %neg) among on-brand posts (relevance ≥ 0.4) per platform.
    const perc: Record<string, { pos: number; neg: number; neu: number; total: number }> = {};
    posts.forEach(p => {
      if ((p.relevance ?? 0) < 0.4) return;
      const pl = p.platform;
      if (!perc[pl]) perc[pl] = { pos: 0, neg: 0, neu: 0, total: 0 };
      const s = socialSentimentOf(p.sentiment);
      if (s === 'positive') perc[pl].pos++; else if (s === 'negative') perc[pl].neg++; else if (s === 'neutral') perc[pl].neu++;
      perc[pl].total++;
    });
    // Networks with <5 scored posts are muted + sorted last (a +100 from one post is noise).
    const perception = Object.entries(perc).map(([platform, c]) => {
      const scored = c.pos + c.neg + c.neu;
      return { platform, volume: c.total, net: scored ? Math.round(((c.pos - c.neg) / scored) * 100) : null, pos: c.pos, neg: c.neg, neu: c.neu, low: scored < 5 };
    }).filter(d => d.volume > 0).sort((a, b) => (Number(a.low) - Number(b.low)) || (b.net ?? -999) - (a.net ?? -999));
    return { all: posts, platforms, perception, sentCounts, netSentiment, sentPie, platPie, timeline, totalLoaded: posts.length };
  }, [social]);

  // Auto-split the two lanes onto distinct networks (best- vs worst-perceived) instead of
  // showing two identical "All networks" lanes. Only acts while BOTH lanes are still at the
  // 'all' default, so it never overrides a network the user has explicitly picked.
  useEffect(() => {
    if (!socialView) return;
    if (bskyFilter.platforms.length || feedFilter.platforms.length) return;
    const perc = socialView.perception;
    let left: string | null = null, right: string | null = null;
    if (perc.length >= 2) { left = perc[0].platform; right = perc[perc.length - 1].platform; }
    else if (socialView.platforms.length >= 2) { left = socialView.platforms[0]; right = socialView.platforms[1]; }
    if (left && right && left !== right) {
      const L = left, R = right;
      setBskyFilter(f => ({ ...f, platforms: [L] }));
      setFeedFilter(f => ({ ...f, platforms: [R] }));
    }
  }, [socialView, bskyFilter.platforms.length, feedFilter.platforms.length]);

  // One social post card (shared by both timeline columns).
  const renderSocialPostCard = (p: any) => {
    const sent = socialSentimentOf(p.sentiment);
    const sm = p.social_meta || {};
    const thumb = sm.thumbnail;
    const engagement: Array<[string, string | null]> = [
      ['♥', fmtCount(sm.likes)], ['↻', fmtCount(sm.reposts)],
      ['💬', fmtCount(sm.comments)], ['▶', fmtCount(sm.plays)],
    ];
    return (
      <div key={p.uri} className="flex gap-3 p-3 hover:bg-gray-50 dark:hover:bg-gray-750">
        <div className="w-1 rounded-full flex-shrink-0" style={{ backgroundColor: SOCIAL_SENTIMENT_COLORS[sent] }} title={sent} />
        {thumb && (
          <img src={thumb} alt="" loading="lazy" referrerPolicy="no-referrer"
            className="w-12 h-12 rounded object-cover flex-shrink-0 bg-gray-100 dark:bg-gray-700"
            onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = 'none'; }} />
        )}
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2 min-w-0">
              <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded-full text-white flex-shrink-0" style={{ backgroundColor: platColor(p.platform) }}>{platLabel(p.platform)}</span>
              {(() => {
                const h = p.social_meta?.author || (socialAuthorOf(p).startsWith('@') ? socialAuthorOf(p).slice(1) : null);
                const canProfile = h && ['twitter', 'bluesky', 'reddit', 'instagram', 'tiktok'].includes(p.platform);
                return canProfile ? (
                  <button onClick={() => openAccountFromAuthor(p.platform, h)} title={`Profile @${h}`}
                    className="text-sm font-semibold text-blue-700 dark:text-blue-400 hover:underline truncate">{socialAuthorOf(p)}</button>
                ) : (
                  <span className="text-sm font-semibold text-gray-800 dark:text-gray-100 truncate">{socialAuthorOf(p)}</span>
                );
              })()}
              {p.publication_date && <span className="text-xs text-gray-400 flex-shrink-0">{p.publication_date.slice(0, 10)}</span>}
            </div>
            <a href={p.uri} target="_blank" rel="noopener noreferrer" className="text-xs text-blue-600 dark:text-blue-400 hover:underline flex-shrink-0 inline-flex items-center gap-1">
              <Eye className="w-3 h-3" /> View
            </a>
          </div>
          <p className="text-sm text-gray-700 dark:text-gray-200 mt-1 line-clamp-3 whitespace-pre-wrap break-words"
             dangerouslySetInnerHTML={{ __html: socialBodyHtml(p) }} />
          <div className="flex items-center gap-2 mt-2 flex-wrap">
            {(() => { const bc = brandColorOf(socialBrandOf(p)); return (p.matched_keywords || []).map((k: string) => (
              <span key={k} title={`${socialBrandOf(p)} keyword "${k}"`}
                style={{ color: bc, borderColor: bc }}
                className="text-[11px] px-2 py-0.5 rounded-full border bg-transparent inline-flex items-center gap-1">
                <span className="opacity-60">#</span>{k}
              </span>
            )); })()}
            {p.relevance != null ? (
              <span className={`text-[11px] px-2 py-0.5 rounded-full ${
                p.relevance >= 0.6 ? 'bg-emerald-50 dark:bg-emerald-900/20 text-emerald-700 dark:text-emerald-400'
                : p.relevance >= 0.4 ? 'bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-400'
                : 'bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400'
              }`}>relevance {p.relevance.toFixed(2)}</span>
            ) : (
              <span className="text-[11px] px-2 py-0.5 rounded-full bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-400">not yet evaluated</span>
            )}
            {p.sentiment && (
              <span className={`text-[11px] px-2 py-0.5 rounded-full ${
                sent === 'positive' ? 'bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-400'
                : sent === 'negative' ? 'bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400'
                : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300'
              }`}>{p.sentiment}</span>
            )}
            {sm.subreddit && (
              <span className="text-[11px] text-gray-400">r/{sm.subreddit}</span>
            )}
            {engagement.filter(([, v]) => v != null).map(([icon, v]) => (
              <span key={icon} className="text-[11px] text-gray-500 dark:text-gray-400 inline-flex items-center gap-0.5" title="engagement">
                <span className="opacity-70">{icon}</span>{v}
              </span>
            ))}
          </div>
        </div>
      </div>
    );
  };

  // One social lane: platform filter chips + independent sentiment/search/sort controls + scrolling feed.
  // Each lane filters from ALL loaded posts by its own platform selection, so two lanes can compare any
  // two networks side by side (e.g. best-perceived vs worst-perceived).
  type LaneFilter = { platforms: string[]; sentiments: string[]; entity?: string; search: string; sort: 'recent' | 'oldest' | 'relevance' };
  const renderSocialLane = (
    filter: LaneFilter,
    setFilter: (f: LaneFilter) => void,
  ) => {
    const basePosts = socialView?.all || [];
    const platforms: string[] = socialView?.platforms || [];
    const items = filterSortSocial(basePosts, filter);
    const sel = filter.platforms;
    const accent = sel.length === 1 ? platColor(sel[0]) : '#6b7280';
    const label = sel.length === 0 ? 'All networks' : sel.length === 1 ? platLabel(sel[0]) : `${sel.length} networks`;
    const togglePlatform = (pl: string) => {
      if (pl === 'all') { setFilter({ ...filter, platforms: [] }); return; }
      setFilter({ ...filter, platforms: sel.includes(pl) ? sel.filter(x => x !== pl) : [...sel, pl] });
    };
    const toggleSentiment = (v: string) => {
      if (v === '') { setFilter({ ...filter, sentiments: [] }); return; }
      const cur = filter.sentiments;
      setFilter({ ...filter, sentiments: cur.includes(v) ? cur.filter(x => x !== v) : [...cur, v] });
    };
    return (
      <div className="flex flex-col bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
        <div className="flex items-center justify-between px-4 py-2.5 border-b border-gray-100 dark:border-gray-700">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full" style={{ backgroundColor: accent }} />
            <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-100">{label}</h3>
          </div>
          <span className="text-xs text-gray-400">{items.length}{items.length !== basePosts.length ? ` / ${basePosts.length}` : ''}</span>
        </div>
        {/* platform filter chips (multi-select; 'All' clears) */}
        <div className="flex items-center gap-1.5 px-3 pt-2 flex-wrap">
          {[{ pl: 'all', lbl: 'All' }, ...platforms.map(pl => ({ pl, lbl: platLabel(pl) }))].map(opt => {
            const active = opt.pl === 'all' ? sel.length === 0 : sel.includes(opt.pl);
            return (
              <button
                key={opt.pl}
                onClick={() => togglePlatform(opt.pl)}
                className={`text-xs px-2 py-0.5 rounded-full border transition-colors ${
                  active ? 'text-white border-transparent' : 'bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300 border-gray-300 dark:border-gray-600 hover:border-blue-400'
                }`}
                style={active ? { backgroundColor: opt.pl === 'all' ? '#4b5563' : platColor(opt.pl) } : undefined}
              >
                {opt.lbl}
              </button>
            );
          })}
        </div>
        {/* per-lane sentiment (multi-select) / search / sort controls */}
        <div className="flex items-center gap-1.5 px-3 py-2 border-b border-gray-100 dark:border-gray-700 flex-wrap">
          {([
            { label: 'All', val: '' }, { label: '+', val: 'positive' },
            { label: '·', val: 'neutral' }, { label: '−', val: 'negative' },
          ]).map(opt => {
            const active = opt.val === '' ? filter.sentiments.length === 0 : filter.sentiments.includes(opt.val);
            return (
              <button
                key={opt.val}
                onClick={() => toggleSentiment(opt.val)}
                title={opt.val || 'all sentiments'}
                className={`text-xs px-2 py-0.5 rounded-full border transition-colors ${
                  active
                    ? 'bg-blue-600 text-white border-blue-600'
                    : 'bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300 border-gray-300 dark:border-gray-600 hover:border-blue-400'
                }`}
              >
                {opt.label}
              </button>
            );
          })}
          <div className="relative flex-1 min-w-[100px]">
            <Search className="w-3 h-3 text-gray-400 absolute left-2 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={filter.search}
              onChange={e => setFilter({ ...filter, search: e.target.value })}
              placeholder="Search…"
              className="w-full text-xs pl-6 pr-2 py-1 rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200 focus:outline-none focus:border-blue-400"
            />
          </div>
          {socialEntityOptions.length > 0 && (
            <select
              value={filter.entity || ''}
              onChange={e => setFilter({ ...filter, entity: e.target.value || undefined })}
              title="Filter by entity (brand) or the keyword that triggered the post"
              className="text-xs px-1.5 py-1 rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200 focus:outline-none focus:border-blue-400 max-w-[160px]"
            >
              <option value="">All entities</option>
              {socialEntityOptions.map(g => (
                <optgroup key={g.name} label={`${g.name}${g.isPrimary ? ' ★' : ''} (${g.count})`}>
                  <option value={`brand::${g.name}`}>All {g.name} posts ({g.count})</option>
                  {g.keywords.map(([k, n]) => (
                    <option key={k} value={`kw::${k}`}>&nbsp;&nbsp;#{k} ({n})</option>
                  ))}
                </optgroup>
              ))}
            </select>
          )}
          <select
            value={filter.sort}
            onChange={e => setFilter({ ...filter, sort: e.target.value as 'recent' | 'oldest' | 'relevance' })}
            className="text-xs px-1.5 py-1 rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200 focus:outline-none focus:border-blue-400"
          >
            <option value="recent">Newest</option>
            <option value="oldest">Oldest</option>
            <option value="relevance">Relevant</option>
          </select>
        </div>
        {/* scrolling feed */}
        <div className="divide-y divide-gray-100 dark:divide-gray-700 overflow-y-auto" style={{ maxHeight: 640 }}>
          {items.map(renderSocialPostCard)}
          {items.length === 0 && basePosts.length > 0 && (
            <div className="p-6 text-center text-xs text-gray-400">No posts match this lane's filters.</div>
          )}
          {basePosts.length === 0 && (
            <div className="p-6 text-center text-xs text-gray-400">No social posts yet. Add social monitoring (Reddit / Bluesky / X / Instagram / TikTok) to this brand and run a collection cycle.</div>
          )}
        </div>
      </div>
    );
  };

  // Spike-alert row: expandable to reveal the actual articles driving the spike (with links).
  const toggleAlert = (cat: string) => setExpandedAlerts(prev => {
    const next = new Set(prev);
    if (next.has(cat)) next.delete(cat); else next.add(cat);
    return next;
  });
  const renderAlertRow = (alert: BWAlert) => {
    const open = expandedAlerts.has(alert.category);
    const arts = alert.articles || [];
    return (
      <div key={alert.category} className={`rounded-lg border ${
        alert.severity === 'high'
          ? 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800'
          : 'bg-orange-50 dark:bg-orange-900/20 border-orange-200 dark:border-orange-800'
      }`}>
        <button onClick={() => toggleAlert(alert.category)} className="w-full flex items-center gap-3 p-2 text-left">
          <ChevronRight className={`w-3.5 h-3.5 text-gray-400 flex-shrink-0 transition-transform ${open ? 'rotate-90' : ''}`} />
          <div className="w-3 h-3 rounded-full flex-shrink-0" style={{ backgroundColor: CATEGORY_COLORS[alert.category] || '#6b7280' }} />
          <span className="text-sm text-gray-700 dark:text-gray-300 flex-1">{alert.category}</span>
          <span className="text-xs font-mono text-gray-600 dark:text-gray-400">{alert.current_count} this week (avg: {alert.average_count})</span>
          <span className={`text-xs font-bold px-1.5 py-0.5 rounded ${
            alert.severity === 'high' ? 'bg-red-200 text-red-800 dark:bg-red-800 dark:text-red-200' : 'bg-orange-200 text-orange-800 dark:bg-orange-800 dark:text-orange-200'
          }`}>{alert.spike_ratio}x</span>
        </button>
        {open && (
          <div className="px-3 pb-2 pt-1 space-y-1.5 border-t border-black/5 dark:border-white/10">
            {arts.length === 0 && <p className="text-xs text-gray-400 pt-1.5">No articles available for this spike.</p>}
            {arts.map(a => (
              <div key={a.uri} className="flex items-center gap-2 text-xs">
                <button
                  onClick={() => onArticleClick?.({ ...a })}
                  className="text-blue-600 dark:text-blue-400 hover:underline text-left flex-1 line-clamp-1"
                  title={a.title}
                >{a.title}</button>
                {a.sentiment && (
                  <span className={`px-1.5 py-0.5 rounded-full flex-shrink-0 ${
                    a.sentiment.toLowerCase().includes('pos') ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400'
                    : a.sentiment.toLowerCase().includes('neg') ? 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400'
                    : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300'
                  }`}>{a.sentiment}</span>
                )}
                {a.publication_date && <span className="text-gray-400 flex-shrink-0">{a.publication_date.slice(0, 10)}</span>}
                <a href={a.uri} target="_blank" rel="noopener noreferrer" onClick={e => e.stopPropagation()}
                  className="text-gray-400 hover:text-blue-600 flex-shrink-0" title="Open source"><Eye className="w-3 h-3" /></a>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  };

  const selectedBrands = brands.filter(b => config.selectedBrandIds.includes(b.id));
  // With no header selection, the "X only" social scope means the primary brand.
  const selectedBrand = selectedBrands[0] || brands.find(b => b.is_primary) || brands[0] || undefined;
  const primarySelectedId = config.selectedBrandIds[0] || null;

  // --- Accounts: profile a handle, list saved, tags/notes, open-from-author ---
  const loadAccounts = useCallback(async () => {
    try { setAccountsList(await listAccountProfiles()); } catch { /* ignore */ }
  }, []);

  const profileAccount = useCallback(async (platform: string, handle: string) => {
    const h = handle.trim();
    if (!h) return;
    setAccLoading(true); setAccError(null);
    try {
      const brand = selectedBrand?.display_name || null;
      const prof = await buildAccountProfile(platform, h, brand);
      setAccountProfile(prof);
      setAccountsList(prev => [prof, ...prev.filter(p => p.id !== prof.id)]);
      setAccSearch(s => ({ ...s, handle: '' }));  // iterate: ready for the next handle
    } catch (e: any) {
      setAccError(e.message || 'Failed to build profile');
    } finally {
      setAccLoading(false);
    }
  }, [selectedBrand]);

  const handleDeleteAccount = useCallback(async (id: number) => {
    try { await deleteAccountProfile(id); } catch { /* ignore */ }
    setAccountsList(prev => prev.filter(p => p.id !== id));
    setAccountProfile(prev => (prev?.id === id ? null : prev));
  }, []);

  // Serialize posts to CSV, ordered primary brand (Wiley) first then competitors,
  // then by sentiment (fans→critics), then newest-first. Includes brand, sentiment,
  // and the triggering keywords.
  const writeSocialCsv = useCallback((posts: any[], suffix: string) => {
    if (!posts.length) return;
    const rows = [...posts].sort((a: any, b: any) => {
      const ra = brandRank[socialBrandOf(a)] ?? 99, rb = brandRank[socialBrandOf(b)] ?? 99;
      if (ra !== rb) return ra - rb;
      const sa = SOCIAL_SENT_ORDER[socialSentimentOf(a.sentiment)] ?? 9, sb = SOCIAL_SENT_ORDER[socialSentimentOf(b.sentiment)] ?? 9;
      if (sa !== sb) return sa - sb;
      return (b.publication_date || '').localeCompare(a.publication_date || '');
    });
    const esc = (v: unknown) => `"${String(v ?? '').replace(/"/g, '""')}"`;
    const header = ['brand', 'sentiment', 'keywords', 'platform', 'author', 'date', 'relevance', 'likes', 'reposts', 'comments', 'plays', 'text', 'url'];
    const lines = [header.map(esc).join(',')];
    rows.forEach((p: any) => {
      const sm = p.social_meta || {};
      lines.push([socialBrandOf(p), p.sentiment || socialSentimentOf(p.sentiment), (p.matched_keywords || []).join('; '),
        p.platform, sm.author || '', (p.publication_date || '').slice(0, 10),
        p.relevance ?? '', sm.likes ?? '', sm.reposts ?? '', sm.comments ?? '', sm.plays ?? '',
        stripSocialMarkdown(p.summary || p.title || ''), p.uri].map(esc).join(','));
    });
    const blob = new Blob([lines.join('\n')], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `social-posts-${suffix}-${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(a); a.click(); document.body.removeChild(a); URL.revokeObjectURL(url);
  }, [brandRank]);

  // Open the export modal, pre-filled with the selected brands and a 30-day window.
  const openSocialExport = useCallback(() => {
    const ids = config.selectedBrandIds.length ? config.selectedBrandIds : brands.map(b => b.id);
    setExpBrands(ids);
    setExpSentiments([]);
    const end = new Date(); const start = new Date(); start.setDate(end.getDate() - 30);
    setExpStart(start.toISOString().slice(0, 10));
    setExpEnd(end.toISOString().slice(0, 10));
    setShowSocialExport(true);
  }, [config.selectedBrandIds, brands]);

  // Fetch ALL posts matching the modal's brands/date-range/relevance (not the 200
  // on-screen sample), filter by sentiment, and download the CSV.
  const runSocialExport = useCallback(async () => {
    setExportingSocial(true);
    try {
      const chosen = brands.filter(b => expBrands.includes(b.id));
      const topics = chosen.map(b => `Brand Monitoring ${b.display_name}`);
      const minRel = expRelevance === 'onbrand' ? 0.4 : 0;
      const inclUneval = expRelevance === 'all';
      const data = await getSocialPosts(topics.length ? topics : undefined, 30, minRel, undefined, inclUneval,
        { startDate: expStart || undefined, endDate: expEnd || undefined, limit: 20000 });
      let posts = data.posts || [];
      if (expSentiments.length) posts = posts.filter((p: any) => expSentiments.includes(socialSentimentOf(p.sentiment)));
      if (!posts.length) { alert('No posts match the selected filters.'); return; }
      const suffix = chosen.length === 1 ? chosen[0].display_name.toLowerCase().replace(/\s+/g, '-') : `${chosen.length || 'all'}-brands`;
      writeSocialCsv(posts, suffix);
      setShowSocialExport(false);
    } catch (e) {
      console.error('social export error', e);
      alert('Export failed — see console for details.');
    } finally {
      setExportingSocial(false);
    }
  }, [brands, expBrands, expSentiments, expStart, expEnd, expRelevance, writeSocialCsv]);

  const openAccountFromAuthor = useCallback((platform: string, author?: string | null) => {
    const handle = (author || '').replace(/^@/, '');
    if (!handle) return;
    setActiveTab('accounts');
    setAccSearch({ platform, handle });
    setAccountProfile(null);
    loadAccounts();
    profileAccount(platform, handle);
  }, [loadAccounts, profileAccount]);

  const handleAddTag = useCallback(async () => {
    if (!accountProfile) return;
    const t = accTagInput.trim();
    if (!t) return;
    const next = Array.from(new Set([...(accountProfile.tags || []), t]));
    setAccTagInput('');
    try { setAccountProfile(await setAccountTags(accountProfile.id, next)); } catch { /* ignore */ }
  }, [accountProfile, accTagInput]);

  const handleRemoveTag = useCallback(async (tag: string) => {
    if (!accountProfile) return;
    const next = (accountProfile.tags || []).filter(t => t !== tag);
    try { setAccountProfile(await setAccountTags(accountProfile.id, next)); } catch { /* ignore */ }
  }, [accountProfile]);

  const handleSaveNote = useCallback(async () => {
    if (!accountProfile) return;
    try { setAccountProfile(await setAccountAnnotation(accountProfile.id, accNoteInput.trim())); } catch { /* ignore */ }
  }, [accountProfile, accNoteInput]);

  // Sync the note textarea + clear deep-dive when a different profile is opened.
  useEffect(() => { setAccNoteInput(accountProfile?.annotation?.text || ''); setAccDeepDive(null); }, [accountProfile?.id]);

  const handleDeepDive = useCallback(async () => {
    if (!accountProfile) return;
    setAccDeepLoading(true);
    try {
      setAccDeepDive(await deepDiveAccount(accountProfile.platform, accountProfile.handle, selectedBrand?.display_name || null));
    } catch { /* ignore */ } finally {
      setAccDeepLoading(false);
    }
  }, [accountProfile, selectedBrand]);

  // Create/refresh this brand's social monitoring group (Reddit + Bluesky) and re-fetch.
  const handleAddSocialMonitoring = useCallback(async () => {
    if (!primarySelectedId) { alert('Select a brand first.'); return; }
    setEnablingSocial(true);
    try {
      const r = await setupSocialMonitoring(primarySelectedId, 24);
      alert(`Social monitoring ${r.created ? 'enabled' : 'updated'}: "${r.group_name}" — ${r.keywords_added} keywords, polling every ${r.interval_hours}h. Posts collect on the next cycle; tune providers/interval/model in Gather → group Settings.`);
      fetchSocial(socialMinRel, undefined, socialInclUneval, socialScope);
    } catch (e: any) {
      alert('Failed to enable social monitoring: ' + e.message);
    } finally {
      setEnablingSocial(false);
    }
  }, [primarySelectedId, fetchSocial, socialMinRel, socialInclUneval]);

  // --- Suggest Keywords via LLM ---
  const handleSuggestKeywords = useCallback(async () => {
    const name = brandForm.display_name?.trim();
    if (!name) return;
    setSuggestingKeywords(true);
    try {
      const suggestions = await suggestKeywords(name, brandForm.description || undefined);
      setBrandForm(prev => ({
        ...prev,
        brand_keywords: [...new Set([...(prev.brand_keywords || []), ...suggestions.brand_keywords])],
        product_keywords: [...new Set([...(prev.product_keywords || []), ...suggestions.product_keywords])],
        people_keywords: [...new Set([...(prev.people_keywords || []), ...suggestions.people_keywords])],
        competitor_keywords: [...new Set([...(prev.competitor_keywords || []), ...suggestions.competitor_keywords])],
      }));
    } catch (err) {
      console.error('Error suggesting keywords:', err);
    } finally {
      setSuggestingKeywords(false);
    }
  }, [brandForm.display_name, brandForm.description]);

  // --- Tab change with data loading ---
  const handleTabChange = useCallback((tab: SubTab) => {
    setActiveTab(tab);
    if (tab === 'overview') {
      fetchShareOfVoice();
      fetchComparison();
      if (primarySelectedId) {
        getSentimentTrends(primarySelectedId, config.daysBack)
          .then(d => setSentimentTrends(d.trends)).catch(console.error);
        getBrandAlerts(primarySelectedId)
          .then(d => setBrandAlerts(d.alerts)).catch(console.error);
      }
    }
    if (tab === 'comparison') {
      fetchComparison();
      fetchShareOfVoice();
    }
    if (tab === 'social') {
      fetchSocial(socialMinRel, undefined, socialInclUneval, socialScope);
    }
    if (tab === 'dashboard') {
      // Combined view needs both sides: social posts + news trends/alerts.
      fetchSocial(socialMinRel, undefined, socialInclUneval, socialScope);
      loadAlertData();
      loadDashArticles();
      loadBenchSocial();
      if (primarySelectedId) {
        getSentimentTrends(primarySelectedId, config.daysBack)
          .then(d => setSentimentTrends(d.trends)).catch(console.error);
        getBrandAlerts(primarySelectedId)
          .then(d => setBrandAlerts(d.alerts)).catch(console.error);
      }
    }
    if (tab === 'accounts') {
      loadAccounts();
    }
    if (tab === 'insights' && primarySelectedId) {
      setLoadingNarrative(true);
      getLatestNarrative(primarySelectedId)
        .then(n => setNarrative(n))
        .catch(console.error)
        .finally(() => setLoadingNarrative(false));
    }
    if (tab === 'analysis' && primarySelectedId) {
      getSentimentTrends(primarySelectedId, config.daysBack)
        .then(d => setSentimentTrends(d.trends))
        .catch(console.error);
      getBrandAlerts(primarySelectedId)
        .then(d => setBrandAlerts(d.alerts))
        .catch(console.error);
      getLatestNarrative(primarySelectedId)
        .then(n => setNarrative(n))
        .catch(console.error);
      fetchComparison();
    }
  }, [primarySelectedId, config.daysBack, fetchComparison, fetchShareOfVoice, fetchSocial, socialMinRel, socialInclUneval, socialScope, loadDashArticles]);

  // --- Refresh overview data when brand/period changes (dashboard shares this data) ---
  useEffect(() => {
    if (activeTab !== 'overview' && activeTab !== 'dashboard') return;
    fetchShareOfVoice();
    fetchComparison();
    if (primarySelectedId) {
      getSentimentTrends(primarySelectedId, config.daysBack)
        .then(d => setSentimentTrends(d.trends)).catch(console.error);
      getBrandAlerts(primarySelectedId)
        .then(d => setBrandAlerts(d.alerts)).catch(console.error);
    } else {
      setSentimentTrends([]);
      setBrandAlerts([]);
    }
  }, [activeTab, primarySelectedId, config.daysBack, fetchShareOfVoice, fetchComparison]);

  // --- Refresh social when the period/topics change (handleTabChange only fires on tab switch) ---
  useEffect(() => {
    if (activeTab !== 'social' && activeTab !== 'dashboard') return;
    fetchSocial(socialMinRel, undefined, socialInclUneval, socialScope);
    if (activeTab === 'dashboard') { loadDashArticles(); loadBenchSocial(); }
    // brands.length: the initial fetch can fire before the brands list loads, in
    // which case "primary only" scope can't resolve a topic — refetch on arrival.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [config.daysBack, config.selectedTopics, config.selectedBrandIds, activeTab, socialScope, brands.length]);

  // --- Click-outside to close export menu ---
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (exportMenuRef.current && !exportMenuRef.current.contains(e.target as Node)) {
        setExportMenuOpen(false);
      }
    };
    if (exportMenuOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [exportMenuOpen]);

  // --- Export ---
  const handleExport = useCallback(async (format: 'csv' | 'json' = 'csv') => {
    if (!primarySelectedId) return;
    setExporting(true);
    try {
      await exportBrandData(primarySelectedId, format, config.daysBack);
    } catch (err) {
      console.error('Export error:', err);
    } finally {
      setExporting(false);
    }
  }, [primarySelectedId, config.daysBack]);

  // --- Full PDF Report Export (with charts) ---
  const handleExportPDFReport = useCallback(async () => {
    setExportingReport(true);
    try {
      // Pre-fetch all tab data in parallel
      const fetches: Promise<any>[] = [fetchComparison(), fetchShareOfVoice()];
      if (primarySelectedId) {
        fetches.push(
          getSentimentTrends(primarySelectedId, config.daysBack)
            .then(d => setSentimentTrends(d.trends)).catch(console.error),
          getBrandAlerts(primarySelectedId)
            .then(d => setBrandAlerts(d.alerts)).catch(console.error),
          getLatestNarrative(primarySelectedId)
            .then(n => setNarrative(n)).catch(console.error),
        );
      }
      await Promise.allSettled(fetches);

      // Wait for Recharts SVGs to render
      await new Promise<void>(resolve => {
        requestAnimationFrame(() => setTimeout(resolve, 800));
      });

      // Strip dark mode for capture
      const hadDark = document.documentElement.classList.contains('dark');
      if (hadDark) document.documentElement.classList.remove('dark');

      try {
        const filename = `brand-report-${(selectedBrand?.display_name || 'all').toLowerCase().replace(/\s+/g, '-')}-${Date.now()}`;
        await ExportService.exportPDFSectionAware('brand-watcher-export', filename);
      } finally {
        if (hadDark) document.documentElement.classList.add('dark');
      }
    } catch (err) {
      console.error('PDF report export error:', err);
    } finally {
      setExportingReport(false);
    }
  }, [primarySelectedId, config.daysBack, selectedBrand, fetchComparison, fetchShareOfVoice]);

  // --- Interactive HTML report (self-contained, downloadable) ---
  const handleExportHtmlReport = useCallback(async () => {
    setExportingReport(true);
    try {
      const bid = primarySelectedId;
      const topicsParam = config.selectedTopics.length ? config.selectedTopics : undefined;
      const socialTopics = selectedBrand ? [`Brand Monitoring ${selectedBrand.display_name}`] : topicsParam;
      const [comparisonD, sovD, socialD, trendsD, alertsD, narrativeD] = await Promise.all([
        getComparison(config.daysBack, topicsParam).catch(() => comparison),
        getShareOfVoice(config.daysBack, topicsParam).catch(() => shareOfVoice),
        getSocialPosts(socialTopics, config.daysBack, 0, undefined, true, { limit: 5000 }).catch(() => social),
        bid ? getSentimentTrends(bid, config.daysBack).then(r => r.trends).catch(() => sentimentTrends) : Promise.resolve([] as typeof sentimentTrends),
        bid ? getBrandAlerts(bid, config.daysBack).then(r => r.alerts).catch(() => brandAlerts) : Promise.resolve([] as typeof brandAlerts),
        bid ? getLatestNarrative(bid).catch(() => narrative) : Promise.resolve(null),
      ]);
      downloadBrandWatcherReport({
        brand: selectedBrand,
        daysBack: config.daysBack,
        stats, categories,
        sentimentTrends: trendsD,
        alerts: alertsD,
        comparison: comparisonD,
        shareOfVoice: sovD,
        narrative: narrativeD,
        social: socialD,
        generatedAt: new Date().toISOString(),
      });
    } catch (err) {
      console.error('HTML report export error:', err);
    } finally {
      setExportingReport(false);
    }
  }, [primarySelectedId, selectedBrand, config.daysBack, config.selectedTopics, stats, categories,
      comparison, shareOfVoice, social, sentimentTrends, brandAlerts, narrative]);

  // --- Dedicated Social report (HTML) — social listening only, not the full brand report ---
  const handleExportSocialReport = useCallback(async () => {
    setExportingSocialReport(true);
    try {
      const socialTopics = selectedBrand ? [`Brand Monitoring ${selectedBrand.display_name}`]
        : (config.selectedTopics.length ? config.selectedTopics : undefined);
      const socialD = await getSocialPosts(socialTopics, config.daysBack, 0, undefined, true, { limit: 5000 }).catch(() => social);
      downloadSocialReport({
        brand: selectedBrand,
        daysBack: config.daysBack,
        social: socialD,
        generatedAt: new Date().toISOString(),
      });
    } catch (err) {
      console.error('Social report export error:', err);
    } finally {
      setExportingSocialReport(false);
    }
  }, [selectedBrand, config.daysBack, config.selectedTopics, social]);

  // --- Category drill-down ---
  const handleCategoryDrillDown = useCallback((category: string) => {
    setDrillDownCategory(prev => prev === category ? null : category);
    if (category !== drillDownCategory) {
      updateConfig({ selectedCategories: [category], page: 1 });
      setActiveTab('articles');
    }
  }, [drillDownCategory, updateConfig]);

  // --- Classify ---
  const handleClassify = useCallback(async (runType: string = 'incremental', daysBack: number = 30) => {
    try {
      const res = await classifyArticles({
        brand_id: primarySelectedId || undefined,
        topics: config.selectedTopics.length > 0 ? config.selectedTopics : undefined,
        run_type: runType,
        days_back: daysBack,
      });
      setClassifyRunId(res.run_id);
      setClassifyStatus('running');

      // Poll for status
      const poll = setInterval(async () => {
        try {
          const status = await getClassifyStatus(res.run_id);
          setClassifyStatus(`${status.status} - ${status.articles_processed} processed, ${status.articles_categorized} categorized`);
          if (status.status !== 'running') {
            clearInterval(poll);
            refresh();
          }
        } catch {
          clearInterval(poll);
        }
      }, 3000);
    } catch (err) {
      console.error('Classification error:', err);
    }
  }, [primarySelectedId, config.selectedTopics, refresh]);

  // --- Generate narrative ---
  const handleGenerateNarrative = useCallback(async () => {
    if (!primarySelectedId) return;
    setGeneratingNarrative(true);
    try {
      const res = await generateNarrative({
        brand_id: primarySelectedId,
        days_back: config.daysBack,
      });
      setNarrative({
        id: 0, brand_id: primarySelectedId,
        brand_name: selectedBrand?.display_name || null,
        narrative: res.narrative,
        data_summary: res.data_summary as any,
        days_back: config.daysBack,
        date_range_start: res.data_summary.date_range?.start || null,
        date_range_end: res.data_summary.date_range?.end || null,
        generated_at: res.generated_at,
      });
    } catch (err) {
      console.error('Narrative generation error:', err);
    } finally {
      setGeneratingNarrative(false);
    }
  }, [primarySelectedId, config.daysBack, selectedBrand]);

  // --- Category insight ---
  const handleCategoryInsight = useCallback(async (category: string) => {
    if (!primarySelectedId) return;
    setLoadingInsight(true);
    setCategoryInsight(null);
    try {
      const res = await generateCategoryInsight({
        brand_id: primarySelectedId,
        category,
        days_back: config.daysBack,
      });
      setCategoryInsight(res);
    } catch (err) {
      console.error('Category insight error:', err);
    } finally {
      setLoadingInsight(false);
    }
  }, [primarySelectedId, config.daysBack]);

  // --- Brand form helpers ---
  const addKeyword = (field: 'brand_keywords' | 'product_keywords' | 'people_keywords' | 'competitor_keywords', value: string) => {
    if (!value.trim()) return;
    const current = (brandForm[field] as string[]) || [];
    if (!current.includes(value.trim())) {
      setBrandForm({ ...brandForm, [field]: [...current, value.trim()] });
    }
  };

  const removeKeyword = (field: 'brand_keywords' | 'product_keywords' | 'people_keywords' | 'competitor_keywords', value: string) => {
    const current = (brandForm[field] as string[]) || [];
    setBrandForm({ ...brandForm, [field]: current.filter(k => k !== value) });
  };

  const resetBrandForm = () => {
    setBrandForm({});
    setEditingBrandId(null);
    setBrandKeywordInput('');
    setProductKeywordInput('');
    setPeopleKeywordInput('');
    setCompetitorKeywordInput('');
    setSetupMonitoring(true);
  };

  const startEditBrand = (brand: Brand) => {
    setEditingBrandId(brand.id);
    setBrandForm({
      name: brand.name,
      display_name: brand.display_name,
      description: brand.description || '',
      brand_keywords: brand.brand_keywords || [],
      product_keywords: brand.product_keywords || [],
      people_keywords: brand.people_keywords || [],
      competitor_keywords: brand.competitor_keywords || [],
      color: brand.color || '',
    });
    setSetupMonitoring(false);
  };

  const handleSaveBrand = async () => {
    try {
      let brandId: number;
      if (editingBrandId) {
        await updateBrandFn(editingBrandId, {
          display_name: brandForm.display_name,
          description: brandForm.description,
          brand_keywords: brandForm.brand_keywords,
          product_keywords: brandForm.product_keywords,
          people_keywords: brandForm.people_keywords,
          competitor_keywords: brandForm.competitor_keywords,
          color: brandForm.color,
        });
        brandId = editingBrandId;
      } else {
        const created = await createBrand({
          name: brandForm.name || brandForm.display_name?.toLowerCase().replace(/[^a-z0-9]+/g, '-') || '',
          display_name: brandForm.display_name || '',
          description: brandForm.description,
          brand_keywords: brandForm.brand_keywords || [],
          product_keywords: brandForm.product_keywords,
          people_keywords: brandForm.people_keywords,
          competitor_keywords: brandForm.competitor_keywords,
          color: brandForm.color,
        });
        brandId = created.id;
      }

      // Setup monitoring if checked
      if (setupMonitoring) {
        try {
          const result = await setupBrandMonitoring(brandId);
          setMonitoringStatus({
            type: 'success',
            message: `Topic "${result.topic_name}" ${result.topic_created ? 'created' : 'already exists'}. `
              + `Keyword group "${result.group_name}" ${result.group_created ? 'created' : 'updated'} with ${result.keywords_added} keywords.`,
          });
          setTimeout(() => setMonitoringStatus(null), 8000);
        } catch (err) {
          console.error('Monitoring setup failed:', err);
          setMonitoringStatus({
            type: 'error',
            message: `Brand saved but monitoring setup failed: ${err instanceof Error ? err.message : 'Unknown error'}`,
          });
          setTimeout(() => setMonitoringStatus(null), 8000);
        }
      }

      resetBrandForm();
    } catch (err) {
      console.error('Error saving brand:', err);
    }
  };

  // Schedule state
  const [schedules, setSchedules] = useState<BWSchedule[]>([]);
  const [loadingSchedules, setLoadingSchedules] = useState(false);
  const [showScheduleForm, setShowScheduleForm] = useState(false);
  const [scheduleTopics, setScheduleTopics] = useState<string[]>([]);
  const [scheduleForm, setScheduleForm] = useState({
    name: '', run_type: 'incremental', days_back: 30,
    schedule_type: 'interval', schedule_interval: 24, schedule_unit: 'hours',
    schedule_time: '02:00',
  });

  const fetchSchedules = useCallback(async () => {
    setLoadingSchedules(true);
    try {
      const data = await getSchedules();
      setSchedules(data.schedules);
    } catch (err) {
      console.error('Error fetching schedules:', err);
    } finally {
      setLoadingSchedules(false);
    }
  }, []);

  const handleCreateSchedule = useCallback(async () => {
    try {
      await createSchedule({
        name: scheduleForm.name || `${selectedBrand?.display_name || 'All brands'} - ${scheduleForm.schedule_type}`,
        brand_id: primarySelectedId || undefined,
        topics: scheduleTopics.length > 0 ? scheduleTopics : undefined,
        run_type: scheduleForm.run_type,
        days_back: scheduleForm.days_back,
        schedule_type: scheduleForm.schedule_type,
        schedule_interval: scheduleForm.schedule_interval,
        schedule_unit: scheduleForm.schedule_unit,
        schedule_time: scheduleForm.schedule_type === 'daily' ? scheduleForm.schedule_time : undefined,
      });
      setShowScheduleForm(false);
      setScheduleTopics([]);
      setScheduleForm({ name: '', run_type: 'incremental', days_back: 30, schedule_type: 'interval', schedule_interval: 24, schedule_unit: 'hours', schedule_time: '02:00' });
      fetchSchedules();
    } catch (err) {
      console.error('Error creating schedule:', err);
    }
  }, [scheduleForm, scheduleTopics, primarySelectedId, selectedBrand, fetchSchedules]);

  const handleDeleteSchedule = useCallback(async (id: number) => {
    try {
      await deleteSchedule(id);
      setSchedules(prev => prev.filter(s => s.id !== id));
    } catch (err) {
      console.error('Error deleting schedule:', err);
    }
  }, []);

  const handleRunScheduleNow = useCallback(async (id: number) => {
    try {
      const res = await runScheduleNow(id);
      setClassifyRunId(res.run_id);
      setClassifyStatus('running');
      fetchSchedules();
      const poll = setInterval(async () => {
        try {
          const status = await getClassifyStatus(res.run_id);
          setClassifyStatus(`${status.status} - ${status.articles_processed} processed, ${status.articles_categorized} categorized`);
          if (status.status !== 'running') {
            clearInterval(poll);
            refresh();
          }
        } catch { clearInterval(poll); }
      }, 3000);
    } catch (err) {
      console.error('Error running schedule:', err);
    }
  }, [refresh]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100 flex items-center gap-2">
            <Target className="w-5 h-5 text-blue-500" />
            Brand Watcher
          </h2>
          <p className="text-sm text-gray-500 dark:text-gray-300 mt-1">
            {brands.length} brand{brands.length !== 1 ? 's' : ''} tracked
            {selectedBrands.length === 1 && ` — viewing: ${selectedBrands[0].display_name}`}
            {selectedBrands.length > 1 && ` — viewing: ${selectedBrands.length} brands`}
          </p>
        </div>

        <div className="flex items-center gap-2">
          {/* Brand selector - multiselect dropdown */}
          <div className="relative">
            <button
              onClick={() => setShowBrandDropdown(!showBrandDropdown)}
              className="flex items-center gap-2 px-3 py-2 text-sm bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg dark:text-gray-100 min-w-[160px]"
            >
              <span className="truncate">
                {config.selectedBrandIds.length === 0
                  ? 'All Brands'
                  : config.selectedBrandIds.length === 1
                  ? (brands.find(b => b.id === config.selectedBrandIds[0])?.display_name || 'Brand')
                  : `${config.selectedBrandIds.length} brands`}
              </span>
              <ChevronDown className="w-4 h-4 flex-shrink-0" />
            </button>
            {showBrandDropdown && (
              <>
                <div className="fixed inset-0 z-40" onClick={() => setShowBrandDropdown(false)} />
                <div className="absolute top-full left-0 mt-1 w-64 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg z-50 py-1 max-h-60 overflow-y-auto">
                  <button
                    onClick={() => { updateConfig({ selectedBrandIds: [] }); setShowBrandDropdown(false); }}
                    className={`w-full flex items-center gap-2 px-3 py-2 text-sm hover:bg-gray-50 dark:hover:bg-gray-750 text-left ${
                      config.selectedBrandIds.length === 0 ? 'text-blue-600 dark:text-blue-400 font-medium' : 'text-gray-700 dark:text-gray-300'
                    }`}
                  >
                    All Brands
                  </button>
                  {brands.filter(b => b.enabled).map(b => {
                    const isSelected = config.selectedBrandIds.includes(b.id);
                    return (
                      <label key={b.id}
                        className="flex items-center gap-2 px-3 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-750 cursor-pointer"
                      >
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={() => {
                            const next = isSelected
                              ? config.selectedBrandIds.filter(id => id !== b.id)
                              : [...config.selectedBrandIds, b.id];
                            updateConfig({ selectedBrandIds: next });
                          }}
                          className="rounded border-gray-300 dark:border-gray-600"
                        />
                        {b.color && <div className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ backgroundColor: b.color }} />}
                        <span className="flex-1 truncate">{b.display_name}</span>
                        {b.is_primary && <span className="text-[10px] text-yellow-500">★</span>}
                      </label>
                    );
                  })}
                </div>
              </>
            )}
          </div>

          {/* Days back */}
          <select
            value={config.daysBack}
            onChange={e => updateConfig({ daysBack: Number(e.target.value) })}
            className="px-3 py-2 text-sm bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg dark:text-gray-100"
          >
            <option value={7}>7 days</option>
            <option value={30}>30 days</option>
            <option value={90}>90 days</option>
            <option value={180}>6 months</option>
            <option value={365}>1 year</option>
            <option value={0}>All Time</option>
          </select>

          {/* Brand config */}
          <button onClick={() => setShowBrandConfig(true)} title="Brand Config"
            className="p-2 text-gray-600 dark:text-gray-300 bg-gray-50 dark:bg-gray-800 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700">
            <Settings className="w-4 h-4" />
          </button>

          {/* Classify */}
          <button onClick={() => { setShowClassifyModal(true); fetchSchedules(); }} title="Classify Articles"
            className="p-2 text-teal-700 dark:text-teal-300 bg-teal-50 dark:bg-teal-900/20 rounded-lg hover:bg-teal-100">
            <Zap className="w-4 h-4" />
          </button>

          {/* Export dropdown */}
          <div className="relative" ref={exportMenuRef}>
            <button
              onClick={() => setExportMenuOpen(!exportMenuOpen)}
              disabled={loading}
              title="Export report"
              className="p-2 text-blue-700 dark:text-blue-300 bg-blue-50 dark:bg-blue-900/20 rounded-lg hover:bg-blue-100 disabled:opacity-50"
            >
              <Download className="w-4 h-4" />
            </button>
            {exportMenuOpen && (
              <div className="absolute right-0 top-full mt-1 w-56 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg z-50 py-1">
                <button
                  onClick={() => { setExportMenuOpen(false); handleExportHtmlReport(); }}
                  className="w-full px-3 py-2 text-left text-sm hover:bg-gray-100 dark:hover:bg-gray-700 flex items-center gap-2 font-medium"
                >
                  <BarChart3 className="w-4 h-4 text-purple-500" />
                  <span>Interactive report <span className="text-[10px] text-gray-400">(HTML)</span></span>
                </button>
                <div className="border-t border-gray-200 dark:border-gray-700 my-1" />
                <button
                  onClick={() => {
                    ExportService.exportBrandWatcherMarkdown({
                      brandName: selectedBrand?.display_name,
                      daysBack: config.daysBack, stats, categories,
                      sentimentTrends, comparison, shareOfVoice,
                      alerts: brandAlerts, narrative, articles,
                      temporalData, selectedBrand,
                    });
                    setExportMenuOpen(false);
                  }}
                  className="w-full px-3 py-2 text-left text-sm hover:bg-gray-100 dark:hover:bg-gray-700 flex items-center gap-2"
                >
                  <FileText className="w-4 h-4 text-blue-500" />
                  Export Markdown
                </button>
                <button
                  onClick={() => {
                    setExportMenuOpen(false);
                    handleExportPDFReport();
                  }}
                  className="w-full px-3 py-2 text-left text-sm hover:bg-gray-100 dark:hover:bg-gray-700 flex items-center gap-2"
                >
                  <FileDown className="w-4 h-4 text-red-500" />
                  Export PDF (full report)
                </button>
                <button
                  onClick={async () => {
                    setExportMenuOpen(false);
                    try { await ExportService.exportImage('brand-watcher-export', `brand-watcher-${(selectedBrand?.display_name || 'all').toLowerCase().replace(/\s+/g, '-')}-${Date.now()}`); }
                    catch (err) { console.error('PNG export error:', err); }
                  }}
                  className="w-full px-3 py-2 text-left text-sm hover:bg-gray-100 dark:hover:bg-gray-700 flex items-center gap-2"
                >
                  <Image className="w-4 h-4 text-green-500" />
                  Export PNG
                </button>
                <div className="border-t border-gray-200 dark:border-gray-700 my-1" />
                <button
                  onClick={() => { handleExport('csv'); setExportMenuOpen(false); }}
                  disabled={!primarySelectedId || exporting}
                  className="w-full px-3 py-2 text-left text-sm hover:bg-gray-100 dark:hover:bg-gray-700 flex items-center gap-2 disabled:opacity-40"
                >
                  <Download className="w-4 h-4 text-gray-500" />
                  {exporting ? 'Exporting...' : 'Export CSV (articles)'}
                </button>
                <button
                  onClick={() => { handleExport('json'); setExportMenuOpen(false); }}
                  disabled={!primarySelectedId || exporting}
                  className="w-full px-3 py-2 text-left text-sm hover:bg-gray-100 dark:hover:bg-gray-700 flex items-center gap-2 disabled:opacity-40"
                >
                  <Download className="w-4 h-4 text-gray-500" />
                  Export JSON (articles)
                </button>
              </div>
            )}
          </div>

          {/* Refresh */}
          <button onClick={refresh} disabled={loading} title="Refresh"
            className="p-2 text-emerald-700 dark:text-emerald-300 bg-emerald-50 dark:bg-emerald-900/20 rounded-lg hover:bg-emerald-100 disabled:opacity-50">
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="flex items-start gap-3 p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
          <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0" />
          <p className="text-sm text-red-700 dark:text-red-300 flex-1">{error}</p>
          <button onClick={clearError} className="text-red-500 hover:text-red-700"><X className="w-4 h-4" /></button>
        </div>
      )}

      {/* Sub-tab navigation */}
      <div className="flex gap-1 border-b border-gray-200 dark:border-gray-700">
        {([
          { id: 'dashboard' as SubTab, label: 'Dashboard', icon: Sparkles },
          { id: 'overview' as SubTab, label: 'Overview', icon: BarChart3 },
          { id: 'analysis' as SubTab, label: 'Brand Analysis', icon: TrendingUp },
          { id: 'comparison' as SubTab, label: 'Comparison', icon: Users },
          { id: 'insights' as SubTab, label: 'Insights', icon: FileText },
          { id: 'articles' as SubTab, label: 'Articles', icon: Target },
          { id: 'social' as SubTab, label: 'Social', icon: Users },
          { id: 'accounts' as SubTab, label: 'Accounts', icon: AtSign },
        ]).map(tab => (
          <button
            key={tab.id}
            onClick={() => handleTabChange(tab.id)}
            className={`flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
              activeTab === tab.id
                ? 'border-blue-500 text-blue-600 dark:text-blue-400'
                : 'border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'
            }`}
          >
            <tab.icon className="w-4 h-4" />
            {tab.label}
          </button>
        ))}
      </div>

      {/* Loading overlay during report generation */}
      {exportingReport && (
        <div className="fixed inset-0 bg-black/50 z-[9999] flex items-center justify-center">
          <div className="bg-white rounded-lg p-6 flex items-center gap-3 shadow-xl">
            <Loader2 className="w-5 h-5 animate-spin text-blue-500" />
            <span className="text-gray-700 font-medium">Generating report...</span>
          </div>
        </div>
      )}

      {/* Wrap all tab content for export */}
      <div id="brand-watcher-export" className={exportingReport ? 'bg-white text-gray-900 p-8 flex flex-col' : ''}>

      {/* Report title block (only during export) */}
      {exportingReport && (
        <div className="order-1 text-center mb-8 pb-6 border-b-2 border-gray-300">
          <h1 className="text-3xl font-bold text-gray-900">Brand Intelligence Report</h1>
          <p className="text-lg text-gray-600 mt-2">{selectedBrand?.display_name || 'All Brands'}</p>
          <p className="text-sm text-gray-400 mt-1">
            Generated: {new Date().toLocaleString()} | Period: {config.daysBack === 0 ? 'All Time' : `Last ${config.daysBack} days`}
          </p>
          <p className="text-xs text-gray-400 mt-3 italic">
            AI Technology Disclosure: This report uses AI for article classification, sentiment analysis, and narrative generation. All content should be reviewed and validated.
          </p>
        </div>
      )}

      {/* ---- OVERVIEW TAB ---- */}
      {activeTab === 'dashboard' && (() => {
        // ---- News side (from sentimentTrends aggregate + stats + alerts) ----
        const newsSent = { pos: 0, neu: 0, neg: 0 };
        for (const t of sentimentTrends) {
          for (const [sK, cnt] of Object.entries(t.sentiments || {})) {
            const lo = sK.toLowerCase();
            if (lo.includes('pos') || lo.includes('optimis')) newsSent.pos += cnt as number;
            else if (lo.includes('neg') || lo.includes('pessimis') || lo.includes('concern') || lo.includes('critical')) newsSent.neg += cnt as number;
            else newsSent.neu += cnt as number;
          }
        }
        const newsScored = newsSent.pos + newsSent.neu + newsSent.neg;
        const newsNet = newsScored ? Math.round(((newsSent.pos - newsSent.neg) / newsScored) * 100) : null;
        // ---- Social side (from socialView) ----
        const sv = socialView;
        const socNet = sv?.netSentiment ?? null;
        const socScored = sv ? sv.sentCounts.positive + sv.sentCounts.neutral + sv.sentCounts.negative : 0;
        // ---- Competitor benchmarks: mean net sentiment across the OTHER brands ----
        const primaryName = selectedBrand?.display_name || '';
        const netFromBreakdown = (bd: Record<string, number>) => {
          let pos = 0, neg = 0, scored = 0;
          for (const [k, v] of Object.entries(bd || {})) {
            const sen = socialSentimentOf(k);
            if (sen === 'unrated') continue;
            if (sen === 'positive') pos += v; else if (sen === 'negative') neg += v;
            scored += v;
          }
          return scored >= 3 ? Math.round(((pos - neg) / scored) * 100) : null;
        };
        const newsCompNets = (comparison || [])
          .filter(c => c.brand_name !== primaryName)
          .map(c => ({ name: c.brand_name, net: netFromBreakdown(c.sentiment_breakdown) }))
          .filter(c => c.net != null) as Array<{ name: string; net: number }>;
        const newsCompAvg = newsCompNets.length
          ? Math.round(newsCompNets.reduce((a, c) => a + c.net, 0) / newsCompNets.length) : null;
        const socCompNets = Object.entries(benchSocial || {})
          .filter(([b, v]) => b !== primaryName && v.scored >= 3)
          .map(([b, v]) => ({ name: b, net: Math.round(((v.pos - v.neg) / v.scored) * 100) }));
        const socCompAvg = socCompNets.length
          ? Math.round(socCompNets.reduce((a, c) => a + c.net, 0) / socCompNets.length) : null;
        const benchChip = (own: number | null, compAvg: number | null, nets: Array<{ name: string; net: number }>) => {
          if (own == null || compAvg == null) return null;
          const d = own - compAvg;
          const cls = d >= 10 ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-900/20 dark:text-emerald-400'
            : d <= -10 ? 'bg-red-50 text-red-700 dark:bg-red-900/20 dark:text-red-400'
            : 'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400';
          return (
            <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-semibold flex-shrink-0 ${cls}`}
              title={`Competitor average ${compAvg > 0 ? '+' : ''}${compAvg} — ${nets.map(c => `${c.name} ${c.net > 0 ? '+' : ''}${c.net}`).join(' · ')}`}>
              {d > 0 ? '▲' : d < 0 ? '▼' : '='} {d > 0 ? '+' : ''}{d} vs comp avg
            </span>
          );
        };
        const highAlerts = brandAlerts.filter(a => a.severity === 'high').length;
        // ---- Social posts: adverse screening — NEGATIVE posts lead (by reach) ----
        const eng = (p: any) => { const m = p.social_meta || {}; return (m.likes || 0) + (m.reposts || 0) * 2 + (m.comments || 0) + (m.plays || 0) / 100; };
        const onBrandSocial = (sv?.all || []).filter(p => (p.relevance ?? 0) >= 0.4);
        // Damage/advocacy ledgers: most-amplified complaint first, most-amplified praise first.
        const negLedger = onBrandSocial.filter(p => socialSentimentOf(p.sentiment) === 'negative')
          .sort((a, b) => eng(b) - eng(a)).slice(0, 4);
        const posLedger = onBrandSocial.filter(p => socialSentimentOf(p.sentiment) === 'positive')
          .sort((a, b) => eng(b) - eng(a)).slice(0, 4);
        // ---- Adverse signal detection (dismissible; keys roll over with the window) ----
        const iso = (h: number) => new Date(Date.now() - h * 3600e3).toISOString();
        const bucket48 = Math.floor(Date.now() / (48 * 3600e3));
        const brandKey = selectedBrand?.display_name || 'all';
        const negRecent = onBrandSocial.filter(p => socialSentimentOf(p.sentiment) === 'negative' && (p.publication_date || '') >= iso(48));
        const negPrior = onBrandSocial.filter(p => { const d = p.publication_date || ''; return socialSentimentOf(p.sentiment) === 'negative' && d >= iso(96) && d < iso(48); });
        const problems: Array<{ key: string; sev: 'high' | 'medium'; text: string; jump: SubTab }> = [];
        if (negPrior.length >= 2 && negRecent.length >= negPrior.length * 2) {
          problems.push({ key: `adv|negspike|${brandKey}|${bucket48}`, sev: 'high', text: `Negative social posts doubled: ${negRecent.length} in the last 48h vs ${negPrior.length} in the prior 48h.`, jump: 'social' });
        }
        const hotNeg = onBrandSocial.filter(p => socialSentimentOf(p.sentiment) === 'negative' && eng(p) >= 50);
        if (hotNeg.length) {
          problems.push({ key: `adv|hotneg|${brandKey}|${bucket48}`, sev: 'high', text: `${hotNeg.length} high-reach negative post${hotNeg.length === 1 ? '' : 's'} circulating (>=50 engagement).`, jump: 'social' });
        }
        const activeCritics = fansCritics.critics.filter(c => c.neg >= 3);
        if (activeCritics.length) {
          problems.push({ key: `adv|critics|${brandKey}|${bucket48}`, sev: 'medium', text: `${activeCritics.length} account${activeCritics.length === 1 ? '' : 's'} posting repeated criticism (3+ negative posts): ${activeCritics.slice(0, 3).map(c => '@' + c.author).join(', ')}.`, jump: 'social' });
        }
        if (newsNet != null && newsNet <= -20) {
          problems.push({ key: `adv|negnews|${brandKey}|${bucket48}`, sev: 'high', text: `News coverage sentiment is net-negative (${newsNet}).`, jump: 'analysis' });
        }
        const visibleProblems = problems.filter(p => !dismissedAlerts.has(p.key));
        const weekBucket = Math.floor(Date.now() / (7 * 24 * 3600e3));
        const visibleSpikes = brandAlerts
          .filter(a => !dismissedAlerts.has(`spike|${a.category}|${brandKey}|${weekBucket}`))
          .sort((a, b) => (a.severity === 'high' ? 0 : 1) - (b.severity === 'high' ? 0 : 1) || b.spike_ratio - a.spike_ratio)
          .slice(0, 3);
        // ---- News rows: adverse-first, story-deduped, rich attributes ----
        const RISK_CAT = /legal|regulat|governance|leadership|financial|investor|crisis|controvers|integrity|litigation/i;
        const relDate = (d?: string | null) => {
          if (!d) return '';
          const ms = Date.now() - new Date(d).getTime();
          const days = Math.floor(ms / 86400e3);
          if (days <= 0) return 'today';
          if (days === 1) return '1d';
          if (days < 30) return `${days}d`;
          return `${Math.floor(days / 30)}mo`;
        };
        const domainOf = (src?: string | null) => (src || '').replace(/^www\./, '');
        // Dashboard math runs over the wide pool (up to 200 recent), not the
        // Articles-tab page — a 20-row page starves the adverse breakdowns.
        const poolArticles = dashArticles ?? articles;
        // Dedup by story cluster (fallback: normalized title), keep the row with the
        // richest story_size so the xN badge reflects total republication.
        const seenStory = new Set<string>();
        const dedupedNews: typeof articles = [];
        for (const a of poolArticles) {
          const k = a.story_group_id || (a.title || '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim().slice(0, 80);
          if (!k || seenStory.has(k)) continue;
          seenStory.add(k);
          dedupedNews.push(a);
        }
        const isNegNews = (a: any) => socialSentimentOf(a.sentiment) === 'negative' || (a.risks || []).length > 0 || isNegConsensus(a);
        const visibleNewsPool = dedupedNews.filter(a => reviewStatusOf(a) !== 'dismissed');
        const negNews = visibleNewsPool.filter(isNegNews).sort((a, b) => (b.story_size || 1) - (a.story_size || 1) || (b.publication_date || '').localeCompare(a.publication_date || ''));
        const otherNews = visibleNewsPool.filter(a => !isNegNews(a)).sort((a, b) => (b.publication_date || '').localeCompare(a.publication_date || ''));
        const newsRows = [...negNews, ...otherNews].slice(0, 8);
        const dividerAfter = negNews.length > 0 && negNews.length < newsRows.length ? negNews.length : -1;
        const newsRow = (a: any) => {
          const sent = socialSentimentOf(a.sentiment);
          const neg = sent === 'negative';
          const riskCats = (a.categories || []).filter((c: string) => RISK_CAT.test(c));
          const shownCats = [...riskCats, ...(a.categories || []).filter((c: string) => !RISK_CAT.test(c))].slice(0, 2);
          return (
            <div key={a.uri}
              className={`px-3 py-2 border-l-4 ${neg ? 'border-red-500 bg-red-50/40 dark:bg-red-900/10' : sent === 'positive' ? 'border-emerald-500' : 'border-gray-300 dark:border-gray-600'}`}>
              <div className="flex items-center gap-2">
                <button onClick={() => openArticle(a)}
                  className="text-sm font-semibold text-gray-800 dark:text-gray-100 hover:text-blue-600 text-left flex-1 line-clamp-1" title={a.title}>
                  {a.title}
                </button>
                {(a.story_size || 1) >= 2 && (
                  <span className={`text-[10px] px-1.5 py-0.5 rounded-full flex-shrink-0 font-semibold ${(a.story_size || 0) >= 3 ? 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300' : 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300'}`}
                    title={`Republished by ${a.story_size} sources — amplification signal`}>×{a.story_size} sources</span>
                )}
                {isNegConsensus(a) && (
                  <span className="text-[10px] px-1.5 py-0.5 rounded-full flex-shrink-0 font-semibold bg-red-600 text-white"
                    title={`${a.story_neg} of ${a.story_scored} sources frame this negatively — the negative reading is consensus, not one outlet's take`}>
                    ⚠ negative consensus
                  </span>
                )}
                {!isNegConsensus(a) && isPolarized(a) && (
                  <span className="text-[10px] px-1.5 py-0.5 rounded-full flex-shrink-0 font-semibold bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300"
                    title={`Coverage is split: ${a.story_pos} positive vs ${a.story_neg} negative of ${a.story_scored} scored sources — contested narrative`}>
                    ⚡ polarized coverage
                  </span>
                )}
                <span className="text-[11px] text-gray-400 flex-shrink-0 w-9 text-right">{relDate(a.publication_date)}</span>
              </div>
              <div className="flex items-center gap-2 mt-0.5 flex-wrap">
                <span className="text-[11px] text-gray-400">{domainOf(a.news_source)}</span>
                {a.factual_reporting && (() => {
                  const f = a.factual_reporting.toLowerCase();
                  const cls = f.includes('very high') || f === 'high' ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-900/20 dark:text-emerald-400'
                    : f.includes('mixed') || f.includes('mostly') ? 'bg-amber-50 text-amber-700 dark:bg-amber-900/20 dark:text-amber-400'
                    : f.includes('low') ? 'bg-red-50 text-red-700 dark:bg-red-900/20 dark:text-red-400'
                    : 'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400';
                  return <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${cls}`} title="MBFC factual reporting rating">{a.factual_reporting}</span>;
                })()}
                {(a.risks || []).map((r: any) => (
                  <span key={r.risk_type}
                    title={`Adverse risk: ${r.risk_type} (${r.severity})`}
                    className={`text-[10px] px-1.5 py-0.5 rounded-full font-semibold ${
                      r.severity === 'high' ? 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300'
                      : r.severity === 'medium' ? 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300'
                      : 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300'}`}>
                    ⚠ {r.risk_type.replace(/_/g, '/')}
                  </span>
                ))}
                {shownCats.map((c: string) => (
                  <span key={c} className={`text-[10px] px-1.5 py-0.5 rounded-full ${RISK_CAT.test(c) ? 'bg-red-50 text-red-700 dark:bg-red-900/20 dark:text-red-400' : 'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400'}`}>{c}</span>
                ))}
                {a.entity_match?.verified && (
                  <span title="Wikidata-verified brand mention"><BadgeCheck className="w-3 h-3 text-blue-400" /></span>
                )}
                <span className="flex-1" />
                {reviewStatusOf(a) !== 'new' && (
                  <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${
                    reviewStatusOf(a) === 'escalated' ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300'
                    : 'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400'}`}>{reviewStatusOf(a)}</span>
                )}
                <select value="" onChange={e => { const v = e.target.value as any; if (v) setReview(a.uri, a.brand_id, v); }}
                  title="Case state" className="text-[10px] px-1 py-0.5 rounded border border-gray-200 dark:border-gray-600 bg-transparent text-gray-400 hover:text-gray-600 cursor-pointer">
                  <option value="">act…</option>
                  <option value="reviewed">Mark reviewed</option>
                  <option value="escalated">Escalate</option>
                  <option value="dismissed">Dismiss</option>
                </select>
              </div>
              {neg && a.summary && (
                <p className="text-[11.5px] text-gray-500 dark:text-gray-400 mt-0.5 line-clamp-1">{stripSocialMarkdown(a.summary)}</p>
              )}
            </div>
          );
        };
        // ---- "New today" deltas ----
        const todayIso = new Date().toISOString().slice(0, 10);
        const newsToday = dedupedNews.filter(a => (a.publication_date || '').slice(0, 10) === todayIso).length;
        const socToday = onBrandSocial.filter(p => (p.publication_date || '').slice(0, 10) === todayIso).length;
        const negNewsToday = negNews.filter(a => (a.publication_date || '').slice(0, 10) === todayIso).length;
        // ---- Adverse category breakdown (what is the problem about) ----
        const negByCat: Record<string, number> = {};
        for (const a of poolArticles) if (isNegNews(a)) for (const c of (a.categories || [])) negByCat[c] = (negByCat[c] || 0) + 1;
        const negCats = Object.entries(negByCat).sort((x, y) => y[1] - x[1]).slice(0, 5);
        const maxNegCat = negCats[0]?.[1] || 1;
        const splitBar = (pos: number, neu: number, neg: number) => {
          const tot = pos + neu + neg || 1;
          return (
            <div className="flex h-3 rounded-full overflow-hidden bg-gray-100 dark:bg-gray-700 flex-1" title={`${pos}+ ${neu}· ${neg}−`}>
              <span style={{ width: `${(pos / tot) * 100}%`, backgroundColor: SOCIAL_SENTIMENT_COLORS.positive }} />
              <span style={{ width: `${(neu / tot) * 100}%`, backgroundColor: SOCIAL_SENTIMENT_COLORS.neutral }} />
              <span style={{ width: `${(neg / tot) * 100}%`, backgroundColor: SOCIAL_SENTIMENT_COLORS.negative }} />
            </div>
          );
        };
        const netChip = (net: number | null) => (
          <span className={`text-sm font-mono font-bold ${net == null ? 'text-gray-400' : net > 0 ? 'text-emerald-600' : net < 0 ? 'text-red-600' : 'text-gray-500'}`}>
            {net == null ? 'n/a' : `${net > 0 ? '+' : ''}${net}`}
          </span>
        );
        return (
          <div className="space-y-5">
            {/* 1. PROBLEMS — server alert events + adverse signals + category spikes */}
            {(alertEvents.length > 0 || visibleProblems.length > 0 || visibleSpikes.length > 0) && (
              <div className="space-y-2">
                {alertEvents.map(ev => (
                  <div key={`ev-${ev.id}`} className={`flex items-center gap-3 rounded-lg border p-3 ${
                    ev.severity === 'high' ? 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800' : 'bg-amber-50 dark:bg-amber-900/20 border-amber-200 dark:border-amber-800'}`}>
                    <Bell className={`w-4 h-4 flex-shrink-0 ${ev.severity === 'high' ? 'text-red-600' : 'text-amber-600'}`} />
                    <div className="flex-1 min-w-0">
                      <span className="text-sm text-gray-800 dark:text-gray-100 block">{ev.title}</span>
                      {ev.body && <span className="text-xs text-gray-500 dark:text-gray-400 line-clamp-1">{ev.body}</span>}
                    </div>
                    <span className="text-[10px] text-gray-400 flex-shrink-0">{(ev.created_at || '').slice(0, 16).replace('T', ' ')}</span>
                    <button onClick={() => { ackAlertEvent(ev.id).then(loadAlertData); }}
                      className="text-xs px-2 py-1 rounded border border-gray-300 dark:border-gray-600 text-gray-500 hover:text-gray-700 flex-shrink-0">Ack</button>
                  </div>
                ))}
                {visibleProblems.map(pr => (
                  <div key={pr.key} className={`flex items-center gap-3 rounded-lg border p-3 ${
                    pr.sev === 'high' ? 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800' : 'bg-amber-50 dark:bg-amber-900/20 border-amber-200 dark:border-amber-800'}`}>
                    <AlertTriangle className={`w-4 h-4 flex-shrink-0 ${pr.sev === 'high' ? 'text-red-600' : 'text-amber-600'}`} />
                    <button onClick={() => handleTabChange(pr.jump)} className="text-sm text-gray-800 dark:text-gray-100 flex-1 text-left hover:underline">{pr.text}</button>
                    <span className="text-xs text-gray-400 flex-shrink-0">investigate →</span>
                    <button onClick={() => dismissAlert(pr.key)} title="Dismiss (returns if it re-triggers)" className="text-gray-400 hover:text-gray-600 flex-shrink-0"><X className="w-3.5 h-3.5" /></button>
                  </div>
                ))}
                {visibleSpikes.map(alert => (
                  <div key={alert.category} className="flex items-center gap-2">
                    <div className="flex-1">{renderAlertRow(alert)}</div>
                    <button onClick={() => dismissAlert(`spike|${alert.category}|${brandKey}|${weekBucket}`)} title="Dismiss for this week" className="text-gray-400 hover:text-gray-600 flex-shrink-0 p-1"><X className="w-3.5 h-3.5" /></button>
                  </div>
                ))}
              </div>
            )}

            {/* 2. Stat cards, with scope toggle as header control + new-today deltas */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-semibold uppercase tracking-wide text-gray-400">At a glance</span>
                <div className="flex items-center gap-1.5">
                  <button onClick={() => {
                      setShowAlertSettings(true);
                      getAlertConfig().then(c => { setAlertCfg(c); setAlertRecipientsText((c.email_recipients || []).join(', ')); }).catch(console.error);
                    }}
                    className="text-xs px-2.5 py-1 rounded-full border border-purple-300 dark:border-purple-700 text-purple-600 dark:text-purple-300 hover:bg-purple-50 dark:hover:bg-purple-900/30 inline-flex items-center gap-1">
                    <Bell className="w-3 h-3" /> Alerts
                  </button>
                  <button onClick={() => {
                      setShowSourcesModal(true); setSourcesPollMsg(null);
                      getOfficialSourcesStatus().then(setSourcesStatus).catch(console.error);
                    }}
                    className="text-xs px-2.5 py-1 rounded-full border border-teal-300 dark:border-teal-700 text-teal-600 dark:text-teal-300 hover:bg-teal-50 dark:hover:bg-teal-900/30 inline-flex items-center gap-1">
                    <Landmark className="w-3 h-3" /> Sources
                  </button>
                  <span className="text-gray-300 dark:text-gray-600">|</span>
                  <span className="text-xs text-gray-400">Social scope:</span>
                  {([{ v: 'selected', l: `${selectedBrand?.display_name || 'Brand'} only` }, { v: 'all', l: '+ competitors' }] as const).map(o => (
                    <button key={o.v} onClick={() => setSocialScope(o.v)}
                      className={`text-xs px-2.5 py-1 rounded-full border transition-colors ${socialScope === o.v
                        ? 'bg-blue-600 text-white border-blue-600'
                        : 'bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300 border-gray-300 dark:border-gray-600 hover:border-blue-400'}`}>
                      {o.l}
                    </button>
                  ))}
                  {loadingSocial
                    ? <Loader2 className="w-3.5 h-3.5 animate-spin text-gray-400" />
                    : sv && <span className="text-[11px] text-gray-400">{sv.totalLoaded} posts · {new Set((sv.all || []).map(p => socialBrandOf(p))).size} brand{new Set((sv.all || []).map(p => socialBrandOf(p))).size === 1 ? '' : 's'}</span>}
                </div>
              </div>
              <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                {[
                  { label: 'News articles', value: stats?.total_articles?.toLocaleString() || '0', sub: newsToday ? `+${newsToday} today${negNewsToday ? ` · ${negNewsToday} negative` : ''}` : (config.daysBack === 0 ? 'all time' : `last ${config.daysBack}d`), tone: negNewsToday ? -1 : null },
                  { label: 'News sentiment', value: newsNet == null ? '—' : `${newsNet > 0 ? '+' : ''}${newsNet}`, sub: `${newsSent.pos}+ ${newsSent.neu}· ${newsSent.neg}−${newsNet != null && newsCompAvg != null ? ` · comp avg ${newsCompAvg > 0 ? '+' : ''}${newsCompAvg}` : ''}`, tone: newsNet },
                  { label: 'Social posts', value: (sv?.totalLoaded ?? 0).toLocaleString(), sub: socToday ? `+${socToday} today · ${socScored} scored` : `${socScored} scored` },
                  { label: 'Social sentiment', value: socNet == null ? '—' : `${socNet > 0 ? '+' : ''}${socNet}`, sub: sv ? `${sv.sentCounts.positive}+ ${sv.sentCounts.neutral}· ${sv.sentCounts.negative}−${socNet != null && socCompAvg != null ? ` · comp avg ${socCompAvg > 0 ? '+' : ''}${socCompAvg}` : ''}` : '', tone: socNet },
                  { label: 'Spike alerts', value: String(brandAlerts.length), sub: highAlerts ? `${highAlerts} high` : 'none high', tone: highAlerts ? -1 : null },
                ].map((c: any) => (
                  <div key={c.label} className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-3.5">
                    <div className="text-[10.5px] uppercase tracking-wide text-gray-400 font-semibold">{c.label}</div>
                    <div className={`text-2xl font-bold mt-0.5 ${c.tone == null ? 'text-gray-900 dark:text-gray-100' : c.tone > 0 ? 'text-emerald-600' : c.tone < 0 ? 'text-red-600' : 'text-gray-900 dark:text-gray-100'}`}>{c.value}</div>
                    {c.sub && <div className="text-[11px] text-gray-400 mt-0.5">{c.sub}</div>}
                  </div>
                ))}
              </div>
            </div>

            {/* 3. Sentiment overview: news vs social + what the negativity is about */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
                <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-100 mb-3">Sentiment — news vs social</h3>
                <div className="space-y-2.5">
                  <div className="flex items-center gap-3">
                    <span className="w-16 text-xs font-medium text-gray-500 flex-shrink-0">📰 News</span>
                    {splitBar(newsSent.pos, newsSent.neu, newsSent.neg)}
                    {netChip(newsNet)}
                    {benchChip(newsNet, newsCompAvg, newsCompNets)}
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="w-16 text-xs font-medium text-gray-500 flex-shrink-0">💬 Social</span>
                    {sv ? splitBar(sv.sentCounts.positive, sv.sentCounts.neutral, sv.sentCounts.negative) : <div className="flex-1 text-xs text-gray-400">loading…</div>}
                    {netChip(socNet)}
                    {benchChip(socNet, socCompAvg, socCompNets)}
                  </div>
                </div>
                {newsNet != null && socNet != null && Math.abs(newsNet - socNet) >= 25 && (
                  <p className="text-xs text-amber-600 dark:text-amber-400 mt-2.5">
                    ⚠ Perception gap: social sentiment is {Math.abs(newsNet - socNet)} points {socNet < newsNet ? 'below' : 'above'} news coverage.
                  </p>
                )}
              </div>
              <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
                <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-100 mb-3">What the negative coverage is about <span className="text-xs font-normal text-gray-400">(loaded articles)</span></h3>
                {negCats.length ? (
                  <div className="space-y-1.5">
                    {negCats.map(([cat, n]) => (
                      <button key={cat} onClick={() => { updateConfig({ selectedCategories: [cat], page: 1 }); setActiveTab('articles'); }}
                        className="w-full flex items-center gap-2 text-left hover:bg-gray-50 dark:hover:bg-gray-750 rounded px-1 py-0.5" title={`Open ${cat} articles`}>
                        <span className="text-xs text-gray-600 dark:text-gray-300 w-44 truncate flex-shrink-0">{cat}</span>
                        <div className="flex-1 h-3 bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden">
                          <div className="h-full rounded-full" style={{ width: `${(n / maxNegCat) * 100}%`, backgroundColor: SOCIAL_SENTIMENT_COLORS.negative }} />
                        </div>
                        <span className="text-xs font-mono text-gray-400 w-6 text-right flex-shrink-0">{n}</span>
                      </button>
                    ))}
                  </div>
                ) : <p className="text-xs text-gray-400">{negNews.length
                  ? `${negNews.length} negative article${negNews.length === 1 ? '' : 's'} in range, but none carry category tags yet.`
                  : 'No negative articles in the analyzed sample. 🎉'}</p>}
              </div>
            </div>

            {/* 4. The items: news (adverse first) + top social side by side */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
                <div className="flex items-center justify-between px-4 py-2.5 border-b border-gray-100 dark:border-gray-700">
                  <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-100">📰 News <span className="text-xs font-normal text-gray-400">adverse first · deduped</span></h3>
                  <button onClick={() => handleTabChange('articles')} className="text-xs text-blue-600 dark:text-blue-400 hover:underline">All articles →</button>
                </div>
                <div className="divide-y divide-gray-100 dark:divide-gray-700">
                  {newsRows.map((a, i) => (
                    <div key={a.uri}>
                      {i === dividerAfter && (
                        <div className="px-3 py-1 text-[10px] uppercase tracking-wide text-gray-400 bg-gray-50 dark:bg-gray-750">— other coverage —</div>
                      )}
                      {newsRow(a)}
                    </div>
                  ))}
                  {newsRows.length === 0 && <p className="px-4 py-6 text-center text-xs text-gray-400">{loadingArticles ? 'Loading…' : 'No classified articles in range.'}</p>}
                </div>
              </div>
              <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
                <div className="flex items-center justify-between px-4 py-2.5 border-b border-gray-100 dark:border-gray-700">
                  <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-100">💬 Social <span className="text-xs font-normal text-gray-400">most-amplified first</span></h3>
                  <button onClick={() => handleTabChange('social')} className="text-xs text-blue-600 dark:text-blue-400 hover:underline">All social →</button>
                </div>
                <div className="grid grid-cols-1 xl:grid-cols-2 divide-y xl:divide-y-0 xl:divide-x divide-gray-100 dark:divide-gray-700">
                  <div>
                    <div className="px-4 pt-2 pb-1 text-[10px] uppercase tracking-wide font-semibold text-red-600 dark:text-red-400">⚠ Negative — by reach</div>
                    <div className="divide-y divide-gray-100 dark:divide-gray-700">
                      {negLedger.map(renderSocialPostCard)}
                      {negLedger.length === 0 && <p className="px-4 py-4 text-center text-xs text-gray-400">{loadingSocial ? 'Loading…' : 'No negative posts in range. 🎉'}</p>}
                    </div>
                  </div>
                  <div>
                    <div className="px-4 pt-2 pb-1 text-[10px] uppercase tracking-wide font-semibold text-emerald-600 dark:text-emerald-400">＋ Positive — by reach</div>
                    <div className="divide-y divide-gray-100 dark:divide-gray-700">
                      {posLedger.map(renderSocialPostCard)}
                      {posLedger.length === 0 && <p className="px-4 py-4 text-center text-xs text-gray-400">{loadingSocial ? 'Loading…' : 'No positive posts in range.'}</p>}
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* 5. Compact fans & critics */}
            {(fansCritics.fans.length > 0 || fansCritics.critics.length > 0) && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-3">
                  <div className="text-xs font-semibold text-emerald-700 dark:text-emerald-400 mb-1.5 px-1.5">😊 Top fans <span className="font-normal text-gray-400">by advocacy reach</span></div>
                  {fansCritics.fans.slice(0, 5).map(a => (
                    <div key={`${a.platform}:${a.author}`} className="w-full flex items-center gap-2 hover:bg-gray-50 dark:hover:bg-gray-750 rounded px-1.5 py-1">
                      <span className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ backgroundColor: platColor(a.platform) }} />
                      <button onClick={() => openAccountFromAuthor(a.platform, a.author)} title="Open account profile"
                        className="text-xs font-semibold text-blue-700 dark:text-blue-400 truncate text-left hover:underline">@{a.author}</button>
                      {fcMeta(a.platform, a.author)}
                      {trendArrow((a as any).trend, 'fan')}
                      <span className="flex-1" />
                      <span className="text-[10px] text-gray-400 flex-shrink-0"
                        title={`${a.pos} positive post${a.pos === 1 ? '' : 's'} earning ${Math.round((a as any).posEng)} engagement${(a as any).spanDays > 0 ? ` over ${(a as any).spanDays}d` : ''}`}>
                        {a.pos}p · {fmtCount(Math.round((a as any).posEng))} reach{(a as any).spanDays > 0 ? ` · ${(a as any).spanDays}d` : ''}
                      </span>
                      <button onClick={() => viewAuthorPosts(a.platform, a.author)} title="See their posts"
                        className="flex-shrink-0 text-gray-300 hover:text-blue-500"><Eye className="w-3 h-3" /></button>
                    </div>
                  ))}
                </div>
                <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-3">
                  <div className="text-xs font-semibold text-red-700 dark:text-red-400 mb-1.5 px-1.5">😠 Top critics <span className="font-normal text-gray-400">by damage reach</span></div>
                  {fansCritics.critics.slice(0, 5).map(a => (
                    <div key={`${a.platform}:${a.author}`} className="w-full flex items-center gap-2 hover:bg-gray-50 dark:hover:bg-gray-750 rounded px-1.5 py-1">
                      <span className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ backgroundColor: platColor(a.platform) }} />
                      <button onClick={() => openAccountFromAuthor(a.platform, a.author)} title="Open account profile"
                        className="text-xs font-semibold text-blue-700 dark:text-blue-400 truncate text-left hover:underline">@{a.author}</button>
                      {fcMeta(a.platform, a.author)}
                      {trendArrow((a as any).trend, 'crit')}
                      <span className="flex-1" />
                      <span className="text-[10px] text-gray-400 flex-shrink-0"
                        title={`${a.neg} negative post${a.neg === 1 ? '' : 's'} earning ${Math.round((a as any).negEng)} engagement${(a as any).spanDays > 0 ? ` over ${(a as any).spanDays}d — repeat critic` : ''}`}>
                        {a.neg}n · {fmtCount(Math.round((a as any).negEng))} reach{(a as any).spanDays > 0 ? ` · ${(a as any).spanDays}d` : ''}
                      </span>
                      <button onClick={() => viewAuthorPosts(a.platform, a.author)} title="See their posts"
                        className="flex-shrink-0 text-gray-300 hover:text-blue-500"><Eye className="w-3 h-3" /></button>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        );
      })()}

      {(activeTab === 'overview' || exportingReport) && (
        <div className={`space-y-6 ${exportingReport ? 'order-3' : ''}`}>
          {exportingReport && (
            <h2 className="text-2xl font-bold text-gray-900 border-b-2 border-blue-500 pb-2 pt-6">2. Overview</h2>
          )}
          {/* Stat cards */}
          {(() => {
            // Aggregate sentiment from sentimentTrends — normalize labels
            const sentAgg: Record<string, number> = { Positive: 0, Neutral: 0, Negative: 0 };
            let sentTotal = 0;
            for (const t of sentimentTrends) {
              for (const [s, cnt] of Object.entries(t.sentiments)) {
                const lo = s.toLowerCase();
                if (lo === 'positive' || lo === 'optimistic' || lo === 'positive development') sentAgg.Positive += cnt;
                else if (lo === 'negative' || lo === 'pessimistic' || lo === 'concerning' || lo === 'concerned' || lo === 'critical' || lo === 'alarming') sentAgg.Negative += cnt;
                else sentAgg.Neutral += cnt;
                sentTotal += cnt;
              }
            }
            const positivePct = sentTotal > 0 ? Math.round((sentAgg.Positive / sentTotal) * 100) : null;
            const negativePct = sentTotal > 0 ? Math.round((sentAgg.Negative / sentTotal) * 100) : null;

            return (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div className="p-4 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
                  <p className="text-xs text-gray-500 dark:text-gray-400">Articles</p>
                  <p className="text-2xl font-bold text-gray-900 dark:text-gray-100">{stats?.total_articles ?? 0}</p>
                </div>
                <div className={`p-4 bg-white dark:bg-gray-800 rounded-lg border ${
                  primarySelectedId && (negativePct || 0) >= 15
                    ? 'border-red-300 dark:border-red-700'
                    : 'border-gray-200 dark:border-gray-700'
                }`}>
                  <p className="text-xs text-gray-500 dark:text-gray-400">Sentiment</p>
                  {primarySelectedId && positivePct !== null ? (
                    <div>
                      {(negativePct || 0) >= 15 ? (
                        <p className="text-2xl font-bold text-red-600 dark:text-red-400">
                          {negativePct}% <span className="text-sm font-normal text-red-500 dark:text-red-400">Neg</span>
                          <AlertTriangle className="w-4 h-4 inline ml-1 -mt-1 text-red-500" />
                        </p>
                      ) : (
                        <p className="text-2xl font-bold text-green-600 dark:text-green-400">{positivePct}% <span className="text-sm font-normal text-gray-500">Pos</span></p>
                      )}
                      <div className="flex mt-1 h-2 rounded-full overflow-hidden bg-gray-100 dark:bg-gray-700">
                        {sentAgg.Positive > 0 && <div className="h-full bg-green-500" style={{ width: `${positivePct}%` }} />}
                        {sentAgg.Neutral > 0 && <div className="h-full bg-slate-400" style={{ width: `${100 - (positivePct || 0) - (negativePct || 0)}%` }} />}
                        {sentAgg.Negative > 0 && <div className="h-full bg-red-500" style={{ width: `${negativePct}%` }} />}
                      </div>
                    </div>
                  ) : (
                    <p className="text-2xl font-bold text-gray-400">—</p>
                  )}
                </div>
                <div className="p-4 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
                  <p className="text-xs text-gray-500 dark:text-gray-400">Top Category</p>
                  <p className="text-sm font-semibold text-gray-900 dark:text-gray-100 truncate">
                    {stats?.most_active_category ? CATEGORY_SHORT_NAMES[stats.most_active_category] || stats.most_active_category : '—'}
                  </p>
                </div>
                <div className="p-4 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
                  <p className="text-xs text-gray-500 dark:text-gray-400">Alerts</p>
                  <div className="flex items-center gap-2">
                    <div className={`w-2.5 h-2.5 rounded-full ${
                      !primarySelectedId ? 'bg-gray-300 dark:bg-gray-600'
                      : brandAlerts.some(a => a.severity === 'high') ? 'bg-red-500'
                      : brandAlerts.length > 0 ? 'bg-orange-500'
                      : 'bg-green-500'
                    }`} />
                    <p className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                      {primarySelectedId ? brandAlerts.length : 0}
                    </p>
                  </div>
                </div>
              </div>
            );
          })()}

          {/* Spike Alerts Banner (brand selected, if alerts exist) */}
          {primarySelectedId && brandAlerts.length > 0 && (
            <div className="bg-white dark:bg-gray-800 rounded-lg border border-orange-200 dark:border-orange-800 p-4">
              <h3 className="text-sm font-semibold text-orange-700 dark:text-orange-300 mb-3 flex items-center gap-2">
                <AlertTriangle className="w-4 h-4" /> Category Spike Alerts
              </h3>
              <div className="space-y-2">
                {[...brandAlerts].sort((a, b) => b.spike_ratio - a.spike_ratio).slice(0, 3).map(renderAlertRow)}
              </div>
              {!exportingReport && brandAlerts.length > 3 && (
                <button onClick={() => handleTabChange('analysis')}
                  className="mt-2 text-xs text-orange-600 dark:text-orange-400 hover:underline">
                  View all {brandAlerts.length} alerts in Analysis →
                </button>
              )}
            </div>
          )}

          {/* Sentiment by Brand Tracker (multi-brand / all brands view only) */}
          {!primarySelectedId && comparison.length > 0 && comparison.some(c => Object.keys(c.sentiment_breakdown || {}).length > 0) && (
            <div id="chart-brand-sentiment-by-brand" className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300">Sentiment by Brand</h3>
                <ChartDownloadButton targetId="chart-brand-sentiment-by-brand" filename="sentiment-by-brand" />
              </div>
              <div className="space-y-3">
                {comparison.map(comp => {
                  const sentCounts = { positive: 0, neutral: 0, negative: 0 };
                  for (const [label, count] of Object.entries(comp.sentiment_breakdown || {})) {
                    const lo = label.toLowerCase();
                    if (lo === 'positive' || lo === 'optimistic' || lo === 'positive development') sentCounts.positive += count;
                    else if (lo === 'negative' || lo === 'pessimistic' || lo === 'concerning' || lo === 'concerned' || lo === 'critical' || lo === 'alarming') sentCounts.negative += count;
                    else sentCounts.neutral += count;
                  }
                  const total = sentCounts.positive + sentCounts.neutral + sentCounts.negative || 1;
                  const positivePct = (sentCounts.positive / total) * 100;
                  const negativePct = (sentCounts.negative / total) * 100;
                  // Trend indicator
                  const trendIcon = positivePct > 50 ? '↑' : negativePct > 20 ? '↓' : '—';
                  const trendColor = positivePct > 50
                    ? 'text-green-600 dark:text-green-400'
                    : negativePct > 20
                    ? 'text-red-600 dark:text-red-400'
                    : 'text-gray-400';
                  return (
                    <div key={comp.brand_id} className="flex items-center gap-3">
                      <div className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ backgroundColor: comp.color || '#6b7280' }} />
                      <span className="text-sm text-gray-700 dark:text-gray-300 w-28 truncate">{comp.brand_name}</span>
                      <div className="flex-1 h-4 bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden flex">
                        {sentCounts.positive > 0 && (
                          <div className="h-full bg-green-500" style={{ width: `${positivePct}%` }} />
                        )}
                        {sentCounts.neutral > 0 && (
                          <div className="h-full bg-gray-400" style={{ width: `${(sentCounts.neutral / total) * 100}%` }} />
                        )}
                        {sentCounts.negative > 0 && (
                          <div className="h-full bg-red-500" style={{ width: `${negativePct}%` }} />
                        )}
                      </div>
                      <span className={`text-sm font-bold ${trendColor}`}>{trendIcon}</span>
                      <div className="flex items-center gap-1.5 text-[10px] w-28 justify-end font-mono">
                        <span className="text-green-600">{sentCounts.positive}</span>
                        <span className="text-gray-400">/</span>
                        <span className="text-gray-500">{sentCounts.neutral}</span>
                        <span className="text-gray-400">/</span>
                        <span className="text-red-600">{sentCounts.negative}</span>
                      </div>
                    </div>
                  );
                })}
              </div>
              <div className="flex items-center gap-4 mt-3 pt-3 border-t border-gray-100 dark:border-gray-700">
                {[
                  { label: 'Positive', color: 'bg-green-500', icon: '↑' },
                  { label: 'Neutral', color: 'bg-gray-400', icon: '—' },
                  { label: 'Negative', color: 'bg-red-500', icon: '↓' },
                ].map(s => (
                  <span key={s.label} className="flex items-center gap-1 text-[10px] text-gray-500 dark:text-gray-400">
                    <div className={`w-2 h-2 rounded-full ${s.color}`} />
                    {s.label}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Sentiment Breakdown (brand selected) */}
          {primarySelectedId && sentimentTrends.length > 0 && (() => {
            // Normalize into 3 buckets
            const sentBuckets = { Positive: 0, Neutral: 0, Negative: 0 };
            let sentTotal = 0;
            for (const t of sentimentTrends) {
              for (const [s, cnt] of Object.entries(t.sentiments)) {
                const lo = s.toLowerCase();
                if (lo === 'positive' || lo === 'optimistic' || lo === 'positive development') sentBuckets.Positive += cnt;
                else if (lo === 'negative' || lo === 'pessimistic' || lo === 'concerning' || lo === 'concerned' || lo === 'critical' || lo === 'alarming') sentBuckets.Negative += cnt;
                else sentBuckets.Neutral += cnt;
                sentTotal += cnt;
              }
            }
            const bucketColors: Record<string, string> = {
              Positive: '#16a34a', Neutral: '#94a3b8', Negative: '#dc2626',
            };
            const bucketOrder: Array<'Positive' | 'Neutral' | 'Negative'> = ['Positive', 'Neutral', 'Negative'];
            const negPct = sentTotal > 0 ? (sentBuckets.Negative / sentTotal) * 100 : 0;
            const hasRisk = negPct >= 15;
            return (
              <div id="chart-brand-sentiment-overview" className={`bg-white dark:bg-gray-800 rounded-lg border p-6 ${
                hasRisk ? 'border-red-300 dark:border-red-700' : 'border-gray-200 dark:border-gray-700'
              }`}>
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300">
                    Sentiment Overview — {selectedBrand?.display_name}
                  </h3>
                  <ChartDownloadButton targetId="chart-brand-sentiment-overview" filename="sentiment-overview" />
                </div>
                {/* Risk banner */}
                {hasRisk && (
                  <div className="flex items-center gap-2 mb-3 p-2.5 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
                    <AlertTriangle className="w-4 h-4 text-red-500 flex-shrink-0" />
                    <span className="text-xs text-red-700 dark:text-red-300">
                      <strong>{negPct.toFixed(0)}% negative sentiment</strong> — {sentBuckets.Negative.toLocaleString()} of {sentTotal.toLocaleString()} articles are negative or concerning
                    </span>
                  </div>
                )}
                <div className="h-7 bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden flex">
                  {bucketOrder.map(sent => {
                    const cnt = sentBuckets[sent];
                    const pct = sentTotal > 0 ? (cnt / sentTotal) * 100 : 0;
                    return pct > 0 ? (
                      <div key={sent} className="h-full relative group"
                        style={{ width: `${pct}%`, backgroundColor: bucketColors[sent] }}>
                        {pct >= 8 && (
                          <span className="absolute inset-0 flex items-center justify-center text-[11px] font-semibold text-white drop-shadow-sm">
                            {pct.toFixed(0)}%
                          </span>
                        )}
                        <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-2 py-1 bg-gray-900 text-white text-xs rounded shadow-lg whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-10">
                          {sent}: {cnt.toLocaleString()} articles ({pct.toFixed(1)}%)
                        </div>
                      </div>
                    ) : null;
                  })}
                </div>
                <div className="flex items-center gap-5 mt-3">
                  {bucketOrder.map(sent => {
                    const cnt = sentBuckets[sent];
                    const rawPct = sentTotal > 0 ? (cnt / sentTotal) * 100 : 0;
                    const pct = cnt > 0 && rawPct < 0.5 ? '<1' : rawPct.toFixed(0);
                    return (
                      <span key={sent} className={`flex items-center gap-1.5 text-xs ${
                        sent === 'Negative' && hasRisk
                          ? 'text-red-600 dark:text-red-400 font-semibold'
                          : 'text-gray-600 dark:text-gray-400'
                      }`}>
                        <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: bucketColors[sent] }} />
                        {sent}: {cnt.toLocaleString()} ({pct}%)
                      </span>
                    );
                  })}
                </div>
              </div>
            );
          })()}

          {/* Sentiment Over Time + Brand Risk (brand selected) */}
          {primarySelectedId && sentimentTrends.length > 0 && (() => {
            // Build weekly time series — normalize sentiment labels
            const weeklyMap: Record<string, { Positive: number; Neutral: number; Negative: number; total: number }> = {};
            for (const t of sentimentTrends) {
              if (!weeklyMap[t.week]) weeklyMap[t.week] = { Positive: 0, Neutral: 0, Negative: 0, total: 0 };
              for (const [s, cnt] of Object.entries(t.sentiments)) {
                const lo = s.toLowerCase();
                if (lo === 'positive' || lo === 'optimistic' || lo === 'positive development') weeklyMap[t.week].Positive += cnt;
                else if (lo === 'negative' || lo === 'pessimistic' || lo === 'concerning' || lo === 'concerned' || lo === 'critical' || lo === 'alarming') weeklyMap[t.week].Negative += cnt;
                else weeklyMap[t.week].Neutral += cnt;
                weeklyMap[t.week].total += cnt;
              }
            }
            const weeks = Object.keys(weeklyMap).sort();
            const timeData = weeks.map(w => ({
              week: w.slice(5), // MM-DD
              Positive: weeklyMap[w].Positive,
              Neutral: weeklyMap[w].Neutral,
              Negative: weeklyMap[w].Negative,
              total: weeklyMap[w].total,
              negPct: weeklyMap[w].total > 0 ? Math.round((weeklyMap[w].Negative / weeklyMap[w].total) * 100) : 0,
            }));

            // Brand Risk Score: compare recent 4 weeks vs previous 4 weeks negative %
            const recentWeeks = timeData.slice(-4);
            const olderWeeks = timeData.slice(-8, -4);
            const recentNeg = recentWeeks.reduce((a, w) => a + w.Negative, 0);
            const recentTotal = recentWeeks.reduce((a, w) => a + w.total, 0);
            const olderNeg = olderWeeks.reduce((a, w) => a + w.Negative, 0);
            const olderTotal = olderWeeks.reduce((a, w) => a + w.total, 0);
            const recentNegPct = recentTotal > 0 ? (recentNeg / recentTotal) * 100 : 0;
            const olderNegPct = olderTotal > 0 ? (olderNeg / olderTotal) * 100 : 0;
            const negTrend = recentNegPct - olderNegPct; // positive = worsening
            const alertCount = brandAlerts.length;
            const highAlerts = brandAlerts.filter(a => a.severity === 'high').length;

            // Composite risk: 0-100 scale
            const riskScore = Math.min(100, Math.round(
              (recentNegPct * 1.5) + // base negative level
              (negTrend > 0 ? negTrend * 2 : 0) + // worsening trend penalty
              (alertCount * 5) + // spike alerts
              (highAlerts * 10) // high-severity bonus
            ));
            const riskLevel = riskScore >= 60 ? 'High' : riskScore >= 30 ? 'Elevated' : 'Low';
            const riskColor = riskScore >= 60 ? 'red' : riskScore >= 30 ? 'orange' : 'green';

            return (
              <>
                {/* Brand Risk Score */}
                <div className={`bg-white dark:bg-gray-800 rounded-lg border p-5 ${
                  riskColor === 'red' ? 'border-red-300 dark:border-red-700'
                  : riskColor === 'orange' ? 'border-orange-300 dark:border-orange-700'
                  : 'border-gray-200 dark:border-gray-700'
                }`}>
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 flex items-center gap-2">
                      Brand Risk Assessment
                      {riskColor !== 'green' && <AlertTriangle className={`w-4 h-4 ${riskColor === 'red' ? 'text-red-500' : 'text-orange-500'}`} />}
                    </h3>
                    <span className={`text-xs font-bold px-2.5 py-1 rounded-full ${
                      riskColor === 'red' ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
                      : riskColor === 'orange' ? 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400'
                      : 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                    }`}>
                      {riskLevel} Risk
                    </span>
                  </div>
                  {/* Risk meter */}
                  <div className="relative h-3 bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden mb-3">
                    <div className="absolute inset-y-0 left-0 rounded-full transition-all" style={{
                      width: `${riskScore}%`,
                      background: riskScore >= 60 ? 'linear-gradient(90deg, #f87171, #dc2626)'
                        : riskScore >= 30 ? 'linear-gradient(90deg, #fb923c, #ea580c)'
                        : 'linear-gradient(90deg, #4ade80, #16a34a)',
                    }} />
                  </div>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
                    <div>
                      <span className="text-gray-500 dark:text-gray-400">Risk Score</span>
                      <p className={`font-bold text-base ${
                        riskColor === 'red' ? 'text-red-600 dark:text-red-400'
                        : riskColor === 'orange' ? 'text-orange-600 dark:text-orange-400'
                        : 'text-green-600 dark:text-green-400'
                      }`}>{riskScore}/100</p>
                    </div>
                    <div>
                      <span className="text-gray-500 dark:text-gray-400">Recent Neg %</span>
                      <p className="font-semibold text-gray-800 dark:text-gray-200">{recentNegPct.toFixed(1)}%</p>
                    </div>
                    <div>
                      <span className="text-gray-500 dark:text-gray-400">Neg Trend (4wk)</span>
                      <p className={`font-semibold ${negTrend > 2 ? 'text-red-600 dark:text-red-400' : negTrend < -2 ? 'text-green-600 dark:text-green-400' : 'text-gray-800 dark:text-gray-200'}`}>
                        {negTrend > 0 ? '+' : ''}{negTrend.toFixed(1)}pp {negTrend > 2 ? '↑' : negTrend < -2 ? '↓' : '—'}
                      </p>
                    </div>
                    <div>
                      <span className="text-gray-500 dark:text-gray-400">Active Alerts</span>
                      <p className="font-semibold text-gray-800 dark:text-gray-200">{alertCount}{highAlerts > 0 ? ` (${highAlerts} high)` : ''}</p>
                    </div>
                  </div>
                  {/* Risk factors */}
                  {riskScore >= 30 && (
                    <div className="mt-3 pt-3 border-t border-gray-100 dark:border-gray-700">
                      <p className="text-[10px] font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-1.5">Contributing Factors</p>
                      <div className="flex flex-wrap gap-1.5">
                        {recentNegPct >= 15 && (
                          <span className="text-[10px] px-2 py-0.5 bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400 rounded-full border border-red-200 dark:border-red-800">
                            High negative volume ({recentNegPct.toFixed(0)}%)
                          </span>
                        )}
                        {negTrend > 2 && (
                          <span className="text-[10px] px-2 py-0.5 bg-orange-50 dark:bg-orange-900/20 text-orange-700 dark:text-orange-400 rounded-full border border-orange-200 dark:border-orange-800">
                            Negative sentiment rising (+{negTrend.toFixed(1)}pp)
                          </span>
                        )}
                        {highAlerts > 0 && (
                          <span className="text-[10px] px-2 py-0.5 bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400 rounded-full border border-red-200 dark:border-red-800">
                            {highAlerts} high-severity spike{highAlerts !== 1 ? 's' : ''}
                          </span>
                        )}
                        {alertCount > 0 && highAlerts === 0 && (
                          <span className="text-[10px] px-2 py-0.5 bg-orange-50 dark:bg-orange-900/20 text-orange-700 dark:text-orange-400 rounded-full border border-orange-200 dark:border-orange-800">
                            {alertCount} category spike{alertCount !== 1 ? 's' : ''}
                          </span>
                        )}
                      </div>
                    </div>
                  )}
                </div>

                {/* Sentiment Over Time — area chart */}
                <div id="chart-brand-sentiment" className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300">Sentiment Over Time</h3>
                    <ChartDownloadButton targetId="chart-brand-sentiment" filename="sentiment-over-time" />
                  </div>
                  <ResponsiveContainer width="100%" height={220}>
                    <AreaChart data={timeData} margin={{ top: 5, right: 5, bottom: 5, left: -15 }}>
                      <defs>
                        <linearGradient id="gradPos" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#16a34a" stopOpacity={0.3} />
                          <stop offset="95%" stopColor="#16a34a" stopOpacity={0.05} />
                        </linearGradient>
                        <linearGradient id="gradNeu" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#94a3b8" stopOpacity={0.3} />
                          <stop offset="95%" stopColor="#94a3b8" stopOpacity={0.05} />
                        </linearGradient>
                        <linearGradient id="gradNeg" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#dc2626" stopOpacity={0.4} />
                          <stop offset="95%" stopColor="#dc2626" stopOpacity={0.05} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.2} />
                      <XAxis dataKey="week" stroke="#9CA3AF" fontSize={11} />
                      <YAxis stroke="#9CA3AF" fontSize={11} />
                      <Tooltip
                        content={({ active, payload, label }) => {
                          if (!active || !payload?.length) return null;
                          const d = payload[0]?.payload;
                          if (!d) return null;
                          return (
                            <div className="bg-gray-900 text-white text-xs rounded-lg shadow-lg px-3 py-2">
                              <p className="font-semibold mb-1">Week of {label}</p>
                              <div className="space-y-0.5">
                                <p><span className="inline-block w-2 h-2 rounded-full bg-green-500 mr-1.5" />Positive: {d.Positive}</p>
                                <p><span className="inline-block w-2 h-2 rounded-full mr-1.5" style={{ backgroundColor: '#94a3b8' }} />Neutral: {d.Neutral}</p>
                                <p><span className="inline-block w-2 h-2 rounded-full bg-red-500 mr-1.5" />Negative: {d.Negative}</p>
                              </div>
                              <p className="text-gray-400 mt-1">Total: {d.total} | Neg: {d.negPct}%</p>
                            </div>
                          );
                        }}
                      />
                      <Area type="monotone" dataKey="Positive" stackId="1" stroke="#16a34a" fill="url(#gradPos)" strokeWidth={2} />
                      <Area type="monotone" dataKey="Neutral" stackId="1" stroke="#94a3b8" fill="url(#gradNeu)" strokeWidth={1.5} />
                      <Area type="monotone" dataKey="Negative" stackId="1" stroke="#dc2626" fill="url(#gradNeg)" strokeWidth={0} />
                      <Legend wrapperStyle={{ fontSize: '11px' }} />
                    </AreaChart>
                  </ResponsiveContainer>
                  {/* Negative trend annotation */}
                  {negTrend > 2 && (
                    <div className="flex items-center gap-2 mt-3 p-2 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
                      <TrendingUp className="w-4 h-4 text-red-500 flex-shrink-0" />
                      <span className="text-xs text-red-700 dark:text-red-300">
                        Negative sentiment is trending up — <strong>+{negTrend.toFixed(1)} percentage points</strong> over the last 4 weeks vs prior 4 weeks
                      </span>
                    </div>
                  )}
                  {negTrend < -2 && (
                    <div className="flex items-center gap-2 mt-3 p-2 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg">
                      <TrendingUp className="w-4 h-4 text-green-500 flex-shrink-0 rotate-180" />
                      <span className="text-xs text-green-700 dark:text-green-300">
                        Negative sentiment is improving — <strong>{negTrend.toFixed(1)} percentage points</strong> over the last 4 weeks vs prior 4 weeks
                      </span>
                    </div>
                  )}
                </div>
              </>
            );
          })()}

          {/* Monthly Volume — stacked recharts BarChart */}
          {temporalData.length > 0 && (() => {
            const topCats = categories.slice(0, 5).map(c => c.category);
            const chartData = temporalData.slice(-12).map(d => ({
              month: d.month.slice(5),
              ...Object.fromEntries(topCats.map(cat => [CATEGORY_SHORT_NAMES[cat] || cat, d.by_category?.[cat] || 0])),
              total: d.total,
            }));

            return (
              <div id="chart-brand-monthly-volume" className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300">Monthly Article Volume</h3>
                  <ChartDownloadButton targetId="chart-brand-monthly-volume" filename="monthly-article-volume" />
                </div>
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart data={chartData} margin={{ top: 5, right: 5, bottom: 5, left: -15 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.3} />
                    <XAxis dataKey="month" stroke="#9CA3AF" fontSize={12} />
                    <YAxis stroke="#9CA3AF" fontSize={12} />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: '#1F2937',
                        border: 'none',
                        borderRadius: '8px',
                        color: '#F3F4F6',
                        fontSize: '12px',
                      }}
                    />
                    <Legend wrapperStyle={{ fontSize: '11px' }} />
                    {topCats.map(cat => (
                      <Bar key={cat} dataKey={CATEGORY_SHORT_NAMES[cat] || cat}
                        stackId="a" fill={CATEGORY_COLORS[cat] || '#6b7280'} />
                    ))}
                  </BarChart>
                </ResponsiveContainer>
              </div>
            );
          })()}

          {/* Top Recent Articles Preview (brand selected) */}
          {config.selectedBrandIds.length > 0 && articles.length > 0 && (
            <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
              <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">Recent Articles</h3>
              <div className="space-y-2">
                {articles.slice(0, 3).map(article => (
                  <div key={`${article.uri}-${article.brand_id}`}
                    className="flex items-start gap-3 p-2 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-750 cursor-pointer transition-colors"
                    onClick={() => openArticle(article)}
                  >
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-gray-800 dark:text-gray-200 line-clamp-1">{article.title}</p>
                      <div className="flex items-center gap-2 mt-1 flex-wrap">
                        {article.categories.slice(0, 2).map(c => (
                          <span key={c} className="text-[10px] px-1.5 py-0.5 rounded" style={{
                            backgroundColor: (CATEGORY_COLORS[c] || '#6b7280') + '20',
                            color: CATEGORY_COLORS[c] || '#6b7280',
                          }}>{CATEGORY_SHORT_NAMES[c] || c}</span>
                        ))}
                        {article.sentiment && (
                          <span className={`inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded ${
                            article.sentiment.toLowerCase() === 'positive' || article.sentiment.toLowerCase() === 'optimistic'
                              ? 'bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-400'
                              : article.sentiment.toLowerCase() === 'negative' || article.sentiment.toLowerCase() === 'pessimistic'
                              ? 'bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400'
                              : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300'
                          }`}>
                            <span className={`w-1.5 h-1.5 rounded-full ${
                              article.sentiment.toLowerCase() === 'positive' || article.sentiment.toLowerCase() === 'optimistic' ? 'bg-green-500' :
                              article.sentiment.toLowerCase() === 'negative' || article.sentiment.toLowerCase() === 'pessimistic' ? 'bg-red-500' :
                              'bg-gray-400'
                            }`} />
                            {article.sentiment}
                          </span>
                        )}
                        {article.publication_date && <span className="text-[10px] text-gray-400">{article.publication_date.slice(0, 10)}</span>}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
              {!exportingReport && (
                <button onClick={() => handleTabChange('articles')}
                  className="mt-3 text-xs text-blue-600 dark:text-blue-400 hover:underline">
                  View all articles →
                </button>
              )}
            </div>
          )}

          {/* Category Distribution — Treemap-style Grid */}
          {loadingCategories ? (
            <div className="flex justify-center py-8"><Loader2 className="w-6 h-6 animate-spin text-blue-500" /></div>
          ) : categories.length > 0 ? (() => {
            const activeCats = categories.filter(c => c.article_count > 0);
            const totalArticles = activeCats.reduce((sum, c) => sum + c.article_count, 0);

            return (
              <div id="chart-brand-category-dist" className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300">Category Distribution</h3>
                  <div className="flex items-center gap-2">
                    {!exportingReport && <span className="text-[10px] text-gray-400">Click a category to view articles</span>}
                    <ChartDownloadButton targetId="chart-brand-category-dist" filename="category-distribution" />
                  </div>
                </div>
                {activeCats.length <= 2 ? (
                  /* Simple full-width rows for 1-2 categories */
                  <div className="space-y-2">
                    {activeCats.map(cat => {
                      const pct = totalArticles > 0 ? (cat.article_count / totalArticles) * 100 : 0;
                      return (
                        <button key={cat.category}
                          onClick={() => handleCategoryDrillDown(cat.category)}
                          className="w-full text-left p-4 rounded-lg transition-all hover:opacity-90 hover:scale-[1.01]"
                          style={{ backgroundColor: (CATEGORY_COLORS[cat.category] || '#6b7280') + '18' }}
                        >
                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2">
                              <div className="w-3 h-3 rounded-full" style={{ backgroundColor: CATEGORY_COLORS[cat.category] || '#6b7280' }} />
                              <span className="text-sm font-medium text-gray-800 dark:text-gray-200">
                                {CATEGORY_SHORT_NAMES[cat.category] || cat.category}
                              </span>
                            </div>
                            <div className="flex items-center gap-2">
                              <span className="text-sm font-bold text-gray-700 dark:text-gray-300">{cat.article_count.toLocaleString()}</span>
                              <span className="text-xs text-gray-500">({pct.toFixed(1)}%)</span>
                              <span className={`text-xs font-bold px-1.5 py-0.5 rounded ${
                                cat.recent_trend === 'up' ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400' :
                                cat.recent_trend === 'down' ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400' :
                                'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400'
                              }`}>
                                {cat.recent_trend === 'up' ? '↑' : cat.recent_trend === 'down' ? '↓' : '—'}
                              </span>
                            </div>
                          </div>
                        </button>
                      );
                    })}
                  </div>
                ) : (
                  /* Treemap-style proportional grid */
                  <div className="flex flex-wrap gap-2">
                    {activeCats.map(cat => {
                      const pct = totalArticles > 0 ? (cat.article_count / totalArticles) * 100 : 0;
                      const basisPct = Math.max(pct, 15); // min 15% for readability
                      const bgColor = CATEGORY_COLORS[cat.category] || '#6b7280';
                      return (
                        <button key={cat.category}
                          onClick={() => handleCategoryDrillDown(cat.category)}
                          className="relative rounded-lg p-3 transition-all hover:opacity-90 hover:scale-[1.02] cursor-pointer text-left overflow-hidden group"
                          style={{
                            flexBasis: `calc(${basisPct}% - 8px)`,
                            flexGrow: 1,
                            minHeight: '64px',
                            backgroundColor: bgColor + '18',
                            borderLeft: `3px solid ${bgColor}`,
                          }}
                        >
                          <div className="relative z-10">
                            <p className="text-xs font-semibold text-gray-800 dark:text-gray-200 leading-tight">
                              {CATEGORY_SHORT_NAMES[cat.category] || cat.category}
                            </p>
                            <div className="flex items-center gap-1.5 mt-1">
                              <span className="text-sm font-bold text-gray-700 dark:text-gray-300">{cat.article_count.toLocaleString()}</span>
                              <span className="text-[10px] text-gray-500 dark:text-gray-400">({pct.toFixed(1)}%)</span>
                              <span className={`text-[10px] font-bold px-1 py-0.5 rounded ${
                                cat.recent_trend === 'up' ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400' :
                                cat.recent_trend === 'down' ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400' :
                                'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400'
                              }`}>
                                {cat.recent_trend === 'up' ? '↑' : cat.recent_trend === 'down' ? '↓' : '—'}
                              </span>
                            </div>
                          </div>
                          {/* Background fill proportional indicator */}
                          <div className="absolute bottom-0 left-0 h-1 rounded-b-lg transition-all"
                            style={{ width: `${pct}%`, backgroundColor: bgColor, opacity: 0.4 }} />
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })() : (
            <div className="text-center py-12 text-gray-500 dark:text-gray-400">
              <Target className="w-12 h-12 mx-auto mb-3 opacity-30" />
              <p>No classified articles yet.</p>
              <p className="text-sm mt-1">Add brands and run classification to get started.</p>
            </div>
          )}
        </div>
      )}

      {/* ---- ANALYSIS TAB ---- */}
      {(activeTab === 'analysis' || exportingReport) && (
        <div className={`space-y-6 ${exportingReport ? 'order-4' : ''}`}>
          {exportingReport && (
            <h2 className="text-2xl font-bold text-gray-900 border-b-2 border-blue-500 pb-2 pt-6">3. Brand Analysis</h2>
          )}
          {config.selectedBrandIds.length === 0 ? (
            <div className="text-center py-12 text-gray-500 dark:text-gray-400">
              <p>Select a brand above to see detailed analysis.</p>
            </div>
          ) : (
            <>
              {/* Competitor sub-tabs (real brands) */}
              {(() => {
                const competitorBrands = brands.filter(b => b.enabled && !config.selectedBrandIds.includes(b.id));
                if (competitorBrands.length === 0) return null;
                return (
                  <div className="flex items-center gap-1 flex-wrap border-b border-gray-200 dark:border-gray-700 pb-2">
                    <button
                      onClick={() => setSelectedCompetitor(null)}
                      className={`px-3 py-1.5 text-xs font-medium border-b-2 transition-colors whitespace-nowrap ${
                        selectedCompetitor === null
                          ? 'border-blue-500 text-blue-600 dark:text-blue-400'
                          : 'border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700'
                      }`}
                    >
                      {selectedBrand?.display_name}
                    </button>
                    {competitorBrands.map(compBrand => {
                      const compData = comparison.find(c => c.brand_id === compBrand.id);
                      return (
                        <button key={compBrand.id}
                          onClick={() => setSelectedCompetitor(prev => prev === compBrand.id ? null : compBrand.id)}
                          className={`px-3 py-1.5 text-xs font-medium border-b-2 transition-colors whitespace-nowrap ${
                            selectedCompetitor === compBrand.id
                              ? 'border-blue-500 text-blue-600 dark:text-blue-400'
                              : 'border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700'
                          }`}
                        >
                          {compBrand.display_name}
                          {compData && <span className="ml-1 text-[10px] text-gray-400">({compData.total_articles})</span>}
                        </button>
                      );
                    })}
                  </div>
                );
              })()}

              {/* Competitor detail view — side-by-side comparison */}
              {selectedCompetitor !== null && (() => {
                const compBrand = brands.find(b => b.id === selectedCompetitor);
                const compData = comparison.find(c => c.brand_id === selectedCompetitor);
                const primaryData = comparison.find(c => c.brand_id === primarySelectedId);
                const compArticles = articles.filter(a => a.brand_id === selectedCompetitor);
                const primaryArticles = articles.filter(a => a.brand_id === primarySelectedId);

                // Merge all categories from both brands
                const allCats = new Set<string>();
                if (compData) Object.entries(compData.category_breakdown).forEach(([k, v]) => { if (v > 0) allCats.add(k); });
                if (primaryData) Object.entries(primaryData.category_breakdown).forEach(([k, v]) => { if (v > 0) allCats.add(k); });
                const sortedCats = [...allCats].sort((a, b) => {
                  const aTotal = (primaryData?.category_breakdown[a] || 0) + (compData?.category_breakdown[a] || 0);
                  const bTotal = (primaryData?.category_breakdown[b] || 0) + (compData?.category_breakdown[b] || 0);
                  return bTotal - aTotal;
                });

                // Sentiment for both
                const calcSentiment = (brandArticles: BWArticle[]) => {
                  const counts = { positive: 0, neutral: 0, negative: 0 };
                  for (const a of brandArticles) {
                    const s = (a.sentiment || '').toLowerCase();
                    if (s === 'positive' || s === 'optimistic') counts.positive++;
                    else if (s === 'negative' || s === 'pessimistic' || s === 'concerned') counts.negative++;
                    else counts.neutral++;
                  }
                  return counts;
                };
                const primarySent = calcSentiment(primaryArticles);
                const compSent = calcSentiment(compArticles);

                // Grouped bar chart data
                const chartData = sortedCats.slice(0, 8).map(cat => ({
                  category: CATEGORY_SHORT_NAMES[cat] || cat,
                  [selectedBrand?.display_name || 'You']: primaryData?.category_breakdown[cat] || 0,
                  [compBrand?.display_name || 'Competitor']: compData?.category_breakdown[cat] || 0,
                }));

                return (
                  <div className="space-y-4">
                    {/* Head-to-head stat cards */}
                    <div className="grid grid-cols-2 gap-4">
                      <div className="p-4 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 text-center">
                        <div className="flex items-center justify-center gap-2 mb-2">
                          {selectedBrand?.color && <div className="w-3 h-3 rounded-full" style={{ backgroundColor: selectedBrand.color }} />}
                          <p className="text-xs font-medium text-gray-500 dark:text-gray-400">{selectedBrand?.display_name}</p>
                        </div>
                        <p className="text-2xl font-bold text-gray-900 dark:text-gray-100">{primaryData?.total_articles || 0}</p>
                        <p className="text-[10px] text-gray-400">articles</p>
                      </div>
                      <div className="p-4 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 text-center">
                        <div className="flex items-center justify-center gap-2 mb-2">
                          {compBrand?.color && <div className="w-3 h-3 rounded-full" style={{ backgroundColor: compBrand.color }} />}
                          <p className="text-xs font-medium text-gray-500 dark:text-gray-400">{compBrand?.display_name}</p>
                        </div>
                        <p className="text-2xl font-bold text-gray-900 dark:text-gray-100">{compData?.total_articles || 0}</p>
                        <p className="text-[10px] text-gray-400">articles</p>
                      </div>
                    </div>

                    {/* Sentiment comparison */}
                    <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-5">
                      <h4 className="text-xs font-semibold text-gray-500 dark:text-gray-400 mb-3">Sentiment Comparison</h4>
                      {[
                        { label: selectedBrand?.display_name || 'You', color: selectedBrand?.color || '#3b82f6', sent: primarySent, total: primaryArticles.length },
                        { label: compBrand?.display_name || 'Competitor', color: compBrand?.color || '#6b7280', sent: compSent, total: compArticles.length },
                      ].map(row => {
                        const t = row.total || 1;
                        return (
                          <div key={row.label} className="mb-2.5 last:mb-0">
                            <div className="flex items-center gap-2 mb-1">
                              <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: row.color }} />
                              <span className="text-xs text-gray-700 dark:text-gray-300 flex-1">{row.label}</span>
                              <div className="flex items-center gap-2 text-[10px]">
                                <span className="text-green-600">{row.sent.positive}</span>
                                <span className="text-gray-400">{row.sent.neutral}</span>
                                <span className="text-red-600">{row.sent.negative}</span>
                              </div>
                            </div>
                            <div className="h-3 bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden flex">
                              {row.sent.positive > 0 && <div className="h-full bg-green-500" style={{ width: `${(row.sent.positive / t) * 100}%` }} />}
                              {row.sent.neutral > 0 && <div className="h-full bg-gray-400" style={{ width: `${(row.sent.neutral / t) * 100}%` }} />}
                              {row.sent.negative > 0 && <div className="h-full bg-red-500" style={{ width: `${(row.sent.negative / t) * 100}%` }} />}
                            </div>
                          </div>
                        );
                      })}
                    </div>

                    {/* Category comparison — grouped bar chart */}
                    {chartData.length > 0 && (
                      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
                        <h4 className="text-xs font-semibold text-gray-500 dark:text-gray-400 mb-3">Category Comparison</h4>
                        <ResponsiveContainer width="100%" height={Math.max(chartData.length * 40, 160)}>
                          <BarChart data={chartData} layout="vertical" margin={{ top: 0, right: 10, bottom: 0, left: 5 }}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.2} horizontal={false} />
                            <XAxis type="number" stroke="#9CA3AF" fontSize={11} />
                            <YAxis type="category" dataKey="category" stroke="#9CA3AF" fontSize={11} width={85} tick={{ fill: '#9CA3AF' }} />
                            <Tooltip contentStyle={{ backgroundColor: '#1F2937', border: 'none', borderRadius: '8px', color: '#F3F4F6', fontSize: '12px' }} />
                            <Legend wrapperStyle={{ fontSize: '11px' }} />
                            <Bar dataKey={selectedBrand?.display_name || 'You'} fill={selectedBrand?.color || '#3b82f6'} radius={[0, 4, 4, 0]} />
                            <Bar dataKey={compBrand?.display_name || 'Competitor'} fill={compBrand?.color || '#6b7280'} radius={[0, 4, 4, 0]} />
                          </BarChart>
                        </ResponsiveContainer>
                      </div>
                    )}

                    {/* Recent competitor articles */}
                    {compArticles.length > 0 && (
                      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
                        <h4 className="text-xs font-semibold text-gray-500 dark:text-gray-400 mb-3">
                          Recent {compBrand?.display_name} Articles
                        </h4>
                        <div className="space-y-2">
                          {compArticles.slice(0, 5).map(a => (
                            <div key={a.uri}
                              className="flex items-start gap-2 p-2 rounded hover:bg-gray-50 dark:hover:bg-gray-750 cursor-pointer"
                              onClick={() => onArticleClick?.({ ...a })}
                            >
                              <div className="flex-1 min-w-0">
                                <p className="text-sm text-gray-800 dark:text-gray-200 line-clamp-1">{a.title}</p>
                                <div className="flex items-center gap-2 mt-0.5">
                                  {a.categories.slice(0, 2).map(c => (
                                    <span key={c} className="text-[10px] px-1 py-0.5 rounded" style={{
                                      backgroundColor: (CATEGORY_COLORS[c] || '#6b7280') + '20',
                                      color: CATEGORY_COLORS[c] || '#6b7280',
                                    }}>{CATEGORY_SHORT_NAMES[c] || c}</span>
                                  ))}
                                  {a.publication_date && <span className="text-[10px] text-gray-400">{a.publication_date.slice(0, 10)}</span>}
                                </div>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                );
              })()}

              {/* Main brand analysis (shown when no competitor selected) */}
              {!selectedCompetitor && (
                <>
                  {/* Latest Narrative Preview */}
                  {narrative && (
                    <div className="bg-white dark:bg-gray-800 rounded-lg border border-blue-200 dark:border-blue-800 p-5">
                      <div className="flex items-center justify-between mb-2">
                        <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 flex items-center gap-2">
                          <Sparkles className="w-4 h-4 text-blue-500" /> Latest Insights
                        </h3>
                        <span className="text-[10px] text-gray-400">
                          {narrative.generated_at ? new Date(narrative.generated_at).toLocaleDateString() : ''}
                        </span>
                      </div>
                      <div className={`prose prose-sm dark:prose-invert max-w-none text-sm text-gray-600 dark:text-gray-300 ${exportingReport ? '' : 'line-clamp-3'}`}
                        dangerouslySetInnerHTML={{ __html: markdownToHtml(narrative.narrative) }}
                      />
                      {!exportingReport && (
                        <button
                          onClick={() => handleTabChange('insights')}
                          className="mt-2 text-xs text-blue-500 hover:text-blue-600 dark:text-blue-400 dark:hover:text-blue-300 font-medium"
                        >
                          View full in Insights &rarr;
                        </button>
                      )}
                    </div>
                  )}

                  {/* Category Trends Over Time — with clickable legend for AI insights */}
                  {temporalData.length > 1 && categories.length > 0 && (() => {
                    const topCats = categories.filter(c => c.article_count > 0).slice(0, 6).map(c => c.category);
                    const trendData = temporalData.map(d => ({
                      month: d.month.slice(5),
                      ...Object.fromEntries(topCats.map(cat => [CATEGORY_SHORT_NAMES[cat] || cat, d.by_category?.[cat] || 0])),
                    }));
                    return (
                      <div id="chart-brand-category-trends" className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
                        <div className="flex items-center justify-between mb-4">
                          <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300">Category Trends Over Time</h3>
                          <ChartDownloadButton targetId="chart-brand-category-trends" filename="category-trends" />
                        </div>
                        <ResponsiveContainer width="100%" height={220}>
                          <AreaChart data={trendData} margin={{ top: 5, right: 5, bottom: 5, left: -15 }}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.2} />
                            <XAxis dataKey="month" stroke="#9CA3AF" fontSize={11} />
                            <YAxis stroke="#9CA3AF" fontSize={11} />
                            <Tooltip
                              contentStyle={{ backgroundColor: '#1F2937', border: 'none', borderRadius: '8px', color: '#F3F4F6', fontSize: '12px' }}
                            />
                            {topCats.map(cat => (
                              <Area key={cat} type="monotone" dataKey={CATEGORY_SHORT_NAMES[cat] || cat}
                                stroke={CATEGORY_COLORS[cat] || '#6b7280'} fill={CATEGORY_COLORS[cat] || '#6b7280'}
                                fillOpacity={0.1} strokeWidth={1.5} dot={false} />
                            ))}
                          </AreaChart>
                        </ResponsiveContainer>
                        {/* Clickable category legend — triggers AI insight (hidden during export) */}
                        {!exportingReport && (
                          <div className="flex flex-wrap gap-2 mt-3 pt-3 border-t border-gray-100 dark:border-gray-700">
                            <span className="text-[10px] text-gray-400 self-center mr-1">Click for AI insight:</span>
                            {topCats.map(cat => {
                              const catInfo = categories.find(c => c.category === cat);
                              return (
                                <button key={cat}
                                  onClick={() => handleCategoryInsight(cat)}
                                  className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs hover:bg-gray-50 dark:hover:bg-gray-750 transition-colors border border-transparent hover:border-gray-200 dark:hover:border-gray-600"
                                  title={`Generate AI insight for ${cat}`}
                                >
                                  <div className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ backgroundColor: CATEGORY_COLORS[cat] || '#6b7280' }} />
                                  <span className="text-gray-600 dark:text-gray-400">{CATEGORY_SHORT_NAMES[cat] || cat}</span>
                                  {catInfo && <span className="font-medium text-gray-700 dark:text-gray-300">{catInfo.article_count}</span>}
                                  <Sparkles className="w-3 h-3 text-gray-400" />
                                </button>
                              );
                            })}
                          </div>
                        )}
                      </div>
                    );
                  })()}

                  {/* Category insight panel */}
                  {loadingInsight && (
                    <div className="flex justify-center py-8"><Loader2 className="w-6 h-6 animate-spin text-blue-500" /></div>
                  )}
                  {categoryInsight && !loadingInsight && (
                    <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
                      <div className="flex items-center justify-between mb-3">
                        <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300">
                          {categoryInsight.category} — AI Insight
                        </h3>
                        {!exportingReport && <button onClick={() => setCategoryInsight(null)} className="text-gray-400 hover:text-gray-600"><X className="w-4 h-4" /></button>}
                      </div>
                      <p className="text-sm text-gray-600 dark:text-gray-300 whitespace-pre-wrap">{categoryInsight.insight}</p>
                      {/* Top articles in this category */}
                      {(() => {
                        const catArticles = articles
                          .filter(a => a.categories.includes(categoryInsight.category))
                          .slice(0, 3);
                        return catArticles.length > 0 ? (
                          <div className="mt-4 pt-3 border-t border-gray-100 dark:border-gray-700">
                            <h4 className="text-xs font-semibold text-gray-500 dark:text-gray-400 mb-2">Recent Articles</h4>
                            <div className="space-y-1.5">
                              {catArticles.map(a => (
                                <div key={a.uri}
                                  className="flex items-center gap-2 p-1.5 rounded hover:bg-gray-50 dark:hover:bg-gray-750 cursor-pointer"
                                  onClick={() => onArticleClick?.({ ...a })}
                                >
                                  <div className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ backgroundColor: CATEGORY_COLORS[categoryInsight.category] || '#6b7280' }} />
                                  <span className="text-xs text-gray-700 dark:text-gray-300 flex-1 line-clamp-1">{a.title}</span>
                                  {a.publication_date && <span className="text-[10px] text-gray-400 flex-shrink-0">{a.publication_date.slice(0, 10)}</span>}
                                </div>
                              ))}
                            </div>
                          </div>
                        ) : null;
                      })()}
                    </div>
                  )}

                  {/* Spike Alerts */}
                  {brandAlerts.length > 0 && (
                    <div className="bg-white dark:bg-gray-800 rounded-lg border border-orange-200 dark:border-orange-800 p-6">
                      <h3 className="text-sm font-semibold text-orange-700 dark:text-orange-300 mb-3 flex items-center gap-2">
                        <AlertTriangle className="w-4 h-4" /> Category Spike Alerts
                      </h3>
                      <div className="space-y-2">
                        {brandAlerts.map(renderAlertRow)}
                      </div>
                      <p className="text-xs text-gray-400 mt-2">Click a spike to see the articles driving it.</p>
                    </div>
                  )}

                  {/* Sentiment Trends */}
                  {sentimentTrends.length > 0 && (
                    <div id="chart-brand-sentiment-by-category" className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
                      <div className="flex items-center justify-between mb-4">
                        <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300">Sentiment by Category (Weekly)</h3>
                        <ChartDownloadButton targetId="chart-brand-sentiment-by-category" filename="sentiment-by-category" />
                      </div>
                      <div className="space-y-2">
                        {(() => {
                          const byCat: Record<string, { Positive: number; Neutral: number; Negative: number }> = {};
                          for (const t of sentimentTrends) {
                            if (!byCat[t.category]) byCat[t.category] = { Positive: 0, Neutral: 0, Negative: 0 };
                            for (const [s, cnt] of Object.entries(t.sentiments)) {
                              const lo = s.toLowerCase();
                              if (lo === 'positive' || lo === 'optimistic' || lo === 'positive development') byCat[t.category].Positive += cnt;
                              else if (lo === 'negative' || lo === 'pessimistic' || lo === 'concerning' || lo === 'concerned' || lo === 'critical' || lo === 'alarming') byCat[t.category].Negative += cnt;
                              else byCat[t.category].Neutral += cnt;
                            }
                          }
                          const sentBucketOrder: Array<'Positive' | 'Neutral' | 'Negative'> = ['Positive', 'Neutral', 'Negative'];
                          const sentBucketColors: Record<string, string> = { Positive: '#16a34a', Neutral: '#94a3b8', Negative: '#dc2626' };
                          return Object.entries(byCat).map(([cat, sents]) => {
                            const total = sents.Positive + sents.Neutral + sents.Negative;
                            return (
                              <button key={cat} onClick={() => handleCategoryDrillDown(cat)}
                                className="w-full flex items-center gap-3 rounded-md px-1 py-0.5 -mx-1 hover:bg-gray-50 dark:hover:bg-gray-700/40 transition-colors text-left"
                                title={`View ${cat} articles`}>
                                <div className="w-3 h-3 rounded-full flex-shrink-0" style={{ backgroundColor: CATEGORY_COLORS[cat] || '#6b7280' }} />
                                <span className="text-xs text-gray-700 dark:text-gray-300 w-36 truncate">{CATEGORY_SHORT_NAMES[cat] || cat}</span>
                                <div className="flex-1 h-4 bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden flex">
                                  {sentBucketOrder.map(sent => {
                                    const cnt = sents[sent];
                                    const pct = total > 0 ? (cnt / total) * 100 : 0;
                                    return pct > 0 ? (
                                      <div key={sent} className="h-full" title={`${sent}: ${cnt} (${pct.toFixed(0)}%)`}
                                        style={{ width: `${pct}%`, backgroundColor: sentBucketColors[sent] }} />
                                    ) : null;
                                  })}
                                </div>
                                <span className="text-xs text-gray-500 w-8 text-right">{total}</span>
                                <ChevronRight className="w-3 h-3 text-gray-300 dark:text-gray-600 flex-shrink-0" />
                              </button>
                            );
                          });
                        })()}
                      </div>
                      <div className="flex items-center gap-3 mt-3 flex-wrap">
                        {[
                          { label: 'Positive', color: '#16a34a' },
                          { label: 'Neutral', color: '#94a3b8' },
                          { label: 'Negative', color: '#dc2626' },
                        ].map(s => (
                          <span key={s.label} className="flex items-center gap-1 text-[10px] text-gray-500 dark:text-gray-400">
                            <div className="w-2 h-2 rounded-full" style={{ backgroundColor: s.color }} />
                            {s.label}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </>
              )}

            </>
          )}
        </div>
      )}

      {activeTab === 'social' && (
        <div className="space-y-6">
          {!(social && social.total > 0) && !socialIntroDismissed && (
          <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-start gap-2">
                <Users className="w-5 h-5 text-blue-500 mt-0.5 flex-shrink-0" />
                <div className="text-sm text-gray-700 dark:text-gray-300">
                  <span className="font-semibold">Social mentions.</span> Posts that mention this brand across X, Bluesky, Reddit, Instagram &amp; TikTok. Each post is automatically scored for relevance ("is this actually about the brand?") and sentiment, so high-volume chatter stays readable.
                </div>
              </div>
              <div className="flex items-start gap-1 flex-shrink-0">
                <button
                  onClick={handleAddSocialMonitoring}
                  disabled={enablingSocial || !primarySelectedId}
                  className="text-xs px-3 py-1.5 rounded-md bg-blue-600 hover:bg-blue-700 text-white disabled:opacity-50 inline-flex items-center gap-1.5"
                  title={primarySelectedId ? 'Create/refresh this brand’s social monitoring group (X, Bluesky, Reddit, Instagram &amp; TikTok, own schedule)' : 'Select a brand first'}
                >
                  {enablingSocial ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Plus className="w-3.5 h-3.5" />}
                  {enablingSocial ? 'Enabling…' : 'Add social monitoring'}
                </button>
                <button
                  onClick={() => { setSocialIntroDismissed(true); try { localStorage.setItem('bw_social_intro_dismissed', '1'); } catch {} }}
                  className="p-1 rounded text-gray-400 hover:text-gray-600 dark:hover:text-gray-200"
                  title="Dismiss"
                  aria-label="Dismiss"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            </div>
          </div>
          )}

          {/* Social honours the header Brand selector (defaults to the primary brand). Use
              that dropdown to focus one brand or pick "All brands" to compare. */}

          {/* Global fetch controls (re-fetch). Source is no longer a global filter — each of the two
              lanes below picks its own network (All/X/Bsky/Reddit/IG/TikTok); sentiment/search/sort are per-lane. */}
          <div className="flex items-center gap-3 flex-wrap">
            <span className="text-xs font-medium text-gray-500 dark:text-gray-400">Scope:</span>
            {([{ v: 'selected', l: `${selectedBrand?.display_name || 'Selected brand'} only` }, { v: 'all', l: '+ competitors' }] as const).map(o => (
              <button key={o.v} onClick={() => setSocialScope(o.v)}
                className={`text-xs px-2.5 py-1 rounded-full border transition-colors ${socialScope === o.v
                  ? 'bg-blue-600 text-white border-blue-600'
                  : 'bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300 border-gray-300 dark:border-gray-600 hover:border-blue-400'}`}>
                {o.l}
              </button>
            ))}
            <span className="text-gray-300 dark:text-gray-600">|</span>
            <span className="text-xs font-medium text-gray-500 dark:text-gray-400">Min relevance:</span>
            {([
              { label: 'All', val: 0 },
              { label: '≥0.4', val: 0.4 },
              { label: '≥0.6', val: 0.6 },
            ]).map(opt => (
              <button
                key={opt.val}
                onClick={() => { setSocialMinRel(opt.val); fetchSocial(opt.val, undefined, socialInclUneval, socialScope); }}
                className={`text-xs px-3 py-1 rounded-full border transition-colors ${
                  socialMinRel === opt.val
                    ? 'bg-blue-600 text-white border-blue-600'
                    : 'bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300 border-gray-300 dark:border-gray-600 hover:border-blue-400'
                }`}
              >
                {opt.label}
              </button>
            ))}
            {socialMinRel === 0 && (
              <button
                onClick={() => { const v = !socialInclUneval; setSocialInclUneval(v); fetchSocial(socialMinRel, undefined, v, socialScope); }}
                className={`text-xs px-3 py-1 rounded-full border transition-colors ${
                  socialInclUneval
                    ? 'bg-blue-600 text-white border-blue-600'
                    : 'bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300 border-gray-300 dark:border-gray-600 hover:border-blue-400'
                }`}
                title="Show posts the lightweight social eval hasn't scored yet (substring matches, often noise). Hidden by default."
              >
                {socialInclUneval ? '✓ ' : ''}Include unevaluated
              </button>
            )}
            <span className="text-xs text-gray-400">≥0.4 = evaluated, on-brand. "All" shows scored-but-off-topic too; toggle to include not-yet-scored.</span>
            <button
              onClick={openSocialExport}
              disabled={brands.length === 0}
              className="ml-auto text-xs px-3 py-1 rounded-full border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300 hover:border-blue-400 disabled:opacity-50 inline-flex items-center gap-1.5"
              title="Export social posts as CSV — choose brands, sentiments and date range"
            >
              <FileDown className="w-3.5 h-3.5" /> Export CSV…
            </button>
            <button
              onClick={handleExportSocialReport}
              disabled={exportingSocialReport || brands.length === 0}
              className="text-xs px-3 py-1 rounded-full border border-purple-300 dark:border-purple-700 text-purple-600 dark:text-purple-300 hover:bg-purple-50 dark:hover:bg-purple-900/30 disabled:opacity-50 inline-flex items-center gap-1.5"
              title="Download a social listening report (HTML) — sentiment, perception, fans & critics, and the positive/negative posts"
            >
              {exportingSocialReport ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <BarChart3 className="w-3.5 h-3.5" />} Social report (HTML)
            </button>
            <button
              onClick={handleAddSocialMonitoring}
              disabled={enablingSocial || !primarySelectedId}
              className="text-xs px-3 py-1 rounded-full border border-blue-300 dark:border-blue-700 text-blue-600 dark:text-blue-300 hover:bg-blue-50 dark:hover:bg-blue-900/30 disabled:opacity-50 inline-flex items-center gap-1.5"
              title={primarySelectedId ? 'Create/refresh this brand’s social monitoring group (X, Bluesky, Reddit, Instagram &amp; TikTok, own schedule)' : 'Select a brand first'}
            >
              {enablingSocial ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Plus className="w-3.5 h-3.5" />}
              {enablingSocial ? 'Enabling…' : 'Add / refresh social monitoring'}
            </button>
          </div>

          {loadingSocial && (
            <div className="flex items-center justify-center py-12 text-gray-500">
              <Loader2 className="w-5 h-5 animate-spin mr-2" /> Loading social posts…
            </div>
          )}

          {!loadingSocial && social && socialView && (
            <>
              {/* Summary metrics */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div className="p-4 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
                  <p className="text-xs text-gray-500 dark:text-gray-400">Posts</p>
                  <p className="text-2xl font-bold text-gray-900 dark:text-gray-100">{social.total.toLocaleString()}</p>
                  <p className="text-xs text-gray-400">last {social.window_days}d</p>
                </div>
                <div className="p-4 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
                  <p className="text-xs text-gray-500 dark:text-gray-400">Evaluated</p>
                  <p className="text-2xl font-bold text-gray-900 dark:text-gray-100">{social.evaluated.toLocaleString()}</p>
                  <p className="text-xs text-gray-400">relevance + sentiment scored</p>
                </div>
                <div className="p-4 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
                  <p className="text-xs text-gray-500 dark:text-gray-400">Net sentiment</p>
                  <p className={`text-2xl font-bold ${
                    socialView.netSentiment == null ? 'text-gray-400'
                    : socialView.netSentiment > 0 ? 'text-green-600 dark:text-green-400'
                    : socialView.netSentiment < 0 ? 'text-red-600 dark:text-red-400'
                    : 'text-gray-600 dark:text-gray-300'
                  }`}>{socialView.netSentiment == null ? '—' : `${socialView.netSentiment > 0 ? '+' : ''}${socialView.netSentiment}`}</p>
                  <p className="text-xs text-gray-400">% positive − % negative</p>
                </div>
                <div className="p-4 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
                  <p className="text-xs text-gray-500 dark:text-gray-400">Best / worst network</p>
                  {socialView.perception.filter(d => d.net != null).length > 0 ? (
                    <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mt-1 leading-relaxed">
                      {(() => { const withNet = socialView.perception.filter(d => d.net != null); const best = withNet[0], worst = withNet[withNet.length - 1]; return (<>
                        <span className="font-semibold" style={{ color: platColor(best.platform) }}>{platLabel(best.platform)}</span> <span className="text-green-600 dark:text-green-400">{best.net! > 0 ? '+' : ''}{best.net}</span>
                        {worst && worst.platform !== best.platform && <> · <span className="font-semibold" style={{ color: platColor(worst.platform) }}>{platLabel(worst.platform)}</span> <span className="text-red-600 dark:text-red-400">{worst.net! > 0 ? '+' : ''}{worst.net}</span></>}
                      </>); })()}
                    </p>
                  ) : <p className="text-sm text-gray-400 mt-1">—</p>}
                  <p className="text-xs text-gray-400 mt-0.5">net sentiment, on-brand posts</p>
                </div>
              </div>

              {/* Analysis charts */}
              {socialView.totalLoaded > 0 && (
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                  <div id="chart-social-sentiment" className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
                    <div className="flex items-center justify-between mb-2">
                      <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300">Sentiment mix</h3>
                      <ChartDownloadButton targetId="chart-social-sentiment" filename="social-sentiment" />
                    </div>
                    <ResponsiveContainer width="100%" height={200}>
                      <PieChart>
                        <Pie data={socialView.sentPie} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius={45} outerRadius={75} paddingAngle={2}>
                          {socialView.sentPie.map(d => <Cell key={d.name} fill={SOCIAL_SENTIMENT_COLORS[d.name]} />)}
                        </Pie>
                        <Tooltip />
                        <Legend iconSize={8} wrapperStyle={{ fontSize: 11 }} />
                      </PieChart>
                    </ResponsiveContainer>
                  </div>
                  <div id="chart-social-platform" className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
                    <div className="flex items-center justify-between mb-2">
                      <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300">Platform mix</h3>
                      <ChartDownloadButton targetId="chart-social-platform" filename="social-platform" />
                    </div>
                    <ResponsiveContainer width="100%" height={200}>
                      <PieChart>
                        <Pie data={socialView.platPie} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius={45} outerRadius={75} paddingAngle={2}>
                          {socialView.platPie.map((d) => <Cell key={d.name} fill={platColor(d.name)} />)}
                        </Pie>
                        <Tooltip />
                        <Legend iconSize={8} wrapperStyle={{ fontSize: 11 }} />
                      </PieChart>
                    </ResponsiveContainer>
                  </div>
                  <div id="chart-social-timeline" className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
                    <div className="flex items-center justify-between mb-2">
                      <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300">Volume by day (sentiment)</h3>
                      <ChartDownloadButton targetId="chart-social-timeline" filename="social-volume" />
                    </div>
                    <ResponsiveContainer width="100%" height={200}>
                      <BarChart data={socialView.timeline} margin={{ top: 8, right: 8, left: -20, bottom: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" className="opacity-30" />
                        <XAxis dataKey="date" tick={{ fontSize: 10 }} tickFormatter={(d: string) => d.slice(5)} />
                        <YAxis tick={{ fontSize: 10 }} allowDecimals={false} />
                        <Tooltip />
                        <Bar dataKey="positive" stackId="s" fill={SOCIAL_SENTIMENT_COLORS.positive} />
                        <Bar dataKey="neutral" stackId="s" fill={SOCIAL_SENTIMENT_COLORS.neutral} />
                        <Bar dataKey="negative" stackId="s" fill={SOCIAL_SENTIMENT_COLORS.negative} />
                        <Bar dataKey="unrated" stackId="s" fill={SOCIAL_SENTIMENT_COLORS.unrated} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              )}

              {/* Sentiment views: trajectory, posted-vs-seen, and per-brand comparison */}
              {socialView.totalLoaded > 0 && (() => {
                const engOf = (p: any) => { const m = p.social_meta || {}; return (m.likes || 0) + (m.reposts || 0) * 2 + (m.comments || 0) + (m.plays || 0) / 100; };
                const onBrand = (socialView.all || []).filter((p: any) => (p.relevance ?? 0) >= 0.4);
                const scored = onBrand.filter((p: any) => socialSentimentOf(p.sentiment) !== 'unrated');
                // --- Net sentiment trend per day (3-day centered smoothing) ---
                const byDay: Record<string, { pos: number; neg: number; n: number }> = {};
                scored.forEach((p: any) => {
                  const d = (p.publication_date || '').slice(0, 10);
                  if (!d) return;
                  if (!byDay[d]) byDay[d] = { pos: 0, neg: 0, n: 0 };
                  const sen = socialSentimentOf(p.sentiment);
                  if (sen === 'positive') byDay[d].pos++; else if (sen === 'negative') byDay[d].neg++;
                  byDay[d].n++;
                });
                const rawDays = Object.entries(byDay).sort((a, b) => a[0].localeCompare(b[0]))
                  .map(([date, v]) => ({ date, net: v.n ? Math.round(((v.pos - v.neg) / v.n) * 100) : 0, n: v.n }));
                const trend = rawDays.map((d, i) => {
                  const win = rawDays.slice(Math.max(0, i - 1), i + 2);
                  const nSum = win.reduce((a, x) => a + x.n, 0);
                  return { ...d, smooth: nSum ? Math.round(win.reduce((a, x) => a + x.net * x.n, 0) / nSum) : d.net };
                });
                // --- Posted vs seen (reach-weighted) ---
                const mix = { posts: { pos: 0, neu: 0, neg: 0 }, reach: { pos: 0, neu: 0, neg: 0 } };
                scored.forEach((p: any) => {
                  const sen = socialSentimentOf(p.sentiment);
                  const k = sen === 'positive' ? 'pos' : sen === 'negative' ? 'neg' : 'neu';
                  mix.posts[k]++; mix.reach[k] += engOf(p) + 1;  // +1: a post with zero engagement was still posted
                });
                const netOf = (m: { pos: number; neu: number; neg: number }) => {
                  const t = m.pos + m.neu + m.neg;
                  return t ? Math.round(((m.pos - m.neg) / t) * 100) : null;
                };
                const mixBar = (m: { pos: number; neu: number; neg: number }) => {
                  const t = Math.max(1, m.pos + m.neu + m.neg);
                  return (
                    <div className="flex-1 h-3 rounded-full overflow-hidden bg-gray-100 dark:bg-gray-700 flex">
                      {m.pos > 0 && <span style={{ width: `${(m.pos / t) * 100}%`, backgroundColor: SOCIAL_SENTIMENT_COLORS.positive }} />}
                      {m.neu > 0 && <span style={{ width: `${(m.neu / t) * 100}%`, backgroundColor: SOCIAL_SENTIMENT_COLORS.neutral }} />}
                      {m.neg > 0 && <span style={{ width: `${(m.neg / t) * 100}%`, backgroundColor: SOCIAL_SENTIMENT_COLORS.negative }} />}
                    </div>
                  );
                };
                const netChipEl = (v: number | null) => (
                  <span className={`text-xs font-mono font-semibold w-10 text-right flex-shrink-0 ${v == null ? 'text-gray-400' : v > 0 ? 'text-emerald-600' : v < 0 ? 'text-red-600' : 'text-gray-500'}`}>
                    {v == null ? '—' : `${v > 0 ? '+' : ''}${v}`}
                  </span>
                );
                const postsNet = netOf(mix.posts), reachNet = netOf(mix.reach);
                const amplifiedNegatively = postsNet != null && reachNet != null && reachNet <= postsNet - 15;
                // --- Per-brand comparison (only meaningful with >1 brand loaded) ---
                const byBrand: Record<string, { pos: number; neu: number; neg: number }> = {};
                scored.forEach((p: any) => {
                  const b = socialBrandOf(p);
                  if (!byBrand[b]) byBrand[b] = { pos: 0, neu: 0, neg: 0 };
                  const sen = socialSentimentOf(p.sentiment);
                  byBrand[b][sen === 'positive' ? 'pos' : sen === 'negative' ? 'neg' : 'neu']++;
                });
                const brandRows = Object.entries(byBrand)
                  .map(([b, m]) => ({ brand: b, ...m, total: m.pos + m.neu + m.neg, net: netOf(m) }))
                  .filter(r => r.total >= 3)
                  .sort((a, b) => (b.net ?? -999) - (a.net ?? -999));
                return (
                  <>
                    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                      {trend.length >= 3 && (
                        <div id="chart-social-nettrend" className="lg:col-span-2 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
                          <div className="flex items-center justify-between mb-2">
                            <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300">Net sentiment trend <span className="text-xs font-normal text-gray-400">daily net % · 3-day smoothed</span></h3>
                            <ChartDownloadButton targetId="chart-social-nettrend" filename="social-net-trend" />
                          </div>
                          <ResponsiveContainer width="100%" height={180}>
                            <AreaChart data={trend} margin={{ top: 4, right: 8, left: -24, bottom: 0 }}>
                              <CartesianGrid strokeDasharray="3 3" className="opacity-30" vertical={false} />
                              <XAxis dataKey="date" tick={{ fontSize: 9 }} tickFormatter={(d: string) => d.slice(5)} />
                              <YAxis domain={[-100, 100]} tick={{ fontSize: 9 }} />
                              <Tooltip formatter={(v: any, name: any) => [v, name === 'smooth' ? 'net % (smoothed)' : 'net %']} labelFormatter={(d: any) => d} />
                              <ReferenceLine y={0} stroke="#9ca3af" />
                              <Area type="monotone" dataKey="smooth" stroke="#2563eb" strokeWidth={2} fill="#3b82f6" fillOpacity={0.12} dot={false} />
                            </AreaChart>
                          </ResponsiveContainer>
                        </div>
                      )}
                      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
                        <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">Posted vs seen</h3>
                        <p className="text-[11px] text-gray-400 mb-3">The same posts weighted by engagement — what the audience actually saw.</p>
                        <div className="space-y-2.5">
                          <div className="flex items-center gap-2">
                            <span className="text-xs text-gray-500 w-16 flex-shrink-0">By posts</span>
                            {mixBar(mix.posts)}
                            {netChipEl(postsNet)}
                          </div>
                          <div className="flex items-center gap-2">
                            <span className="text-xs text-gray-500 w-16 flex-shrink-0">By reach</span>
                            {mixBar(mix.reach)}
                            {netChipEl(reachNet)}
                          </div>
                        </div>
                        {amplifiedNegatively && (
                          <p className="text-xs text-amber-600 dark:text-amber-400 mt-2.5">
                            ⚠ Negative posts are being amplified: sentiment by reach is {postsNet! - reachNet!} points worse than by volume.
                          </p>
                        )}
                      </div>
                    </div>
                    {brandRows.length >= 2 && (
                      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
                        <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">Sentiment by brand <span className="text-xs font-normal text-gray-400">on-brand scored posts · best to worst</span></h3>
                        <div className="space-y-1.5">
                          {brandRows.map(r => (
                            <div key={r.brand} className="flex items-center gap-2">
                              <span className="text-xs font-medium w-36 truncate flex-shrink-0" style={{ color: brandColorOf(r.brand) }}>{r.brand}</span>
                              {mixBar(r)}
                              {netChipEl(r.net)}
                              <span className="text-[11px] text-gray-400 w-14 text-right flex-shrink-0">{r.total} posts</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </>
                );
              })()}

              {/* Perception by network — cross-platform brand sentiment comparison (best vs worst) */}
              {socialView.perception.length > 0 && (
                <div id="chart-social-perception" className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
                  <div className="flex items-start justify-between mb-3">
                    <div>
                      <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300">Perception by network</h3>
                      <p className="text-xs text-gray-400">net sentiment (% positive − % negative) among on-brand posts · click a network to load it into the left lane</p>
                    </div>
                    <ChartDownloadButton targetId="chart-social-perception" filename="social-perception" />
                  </div>
                  <div className="space-y-2">
                    {socialView.perception.map(d => {
                      const net = d.net ?? 0;
                      const scored = d.pos + d.neu + d.neg;
                      // Diverging bar: negatives red left of centre, positives green right —
                      // so a +18 net with 17 negatives still SHOWS the negatives.
                      const posPct = scored ? (d.pos / scored) * 100 : 0;
                      const negPct = scored ? (d.neg / scored) * 100 : 0;
                      return (
                        <button key={d.platform} onClick={() => setBskyFilter({ ...bskyFilter, platforms: [d.platform] })}
                          className={`w-full flex items-center gap-3 text-left hover:bg-gray-50 dark:hover:bg-gray-750 rounded px-1 py-0.5 ${d.low ? 'opacity-50' : ''}`}
                          title={`Load ${platLabel(d.platform)} into the left lane · ${d.pos}+ / ${d.neu}· / ${d.neg}−${d.low ? ' — low sample, treat as anecdotal' : ''}`}>
                          <span className="w-20 flex-shrink-0 text-xs font-semibold flex items-center gap-1.5" style={{ color: platColor(d.platform) }}>
                            <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: platColor(d.platform) }} />{platLabel(d.platform)}
                          </span>
                          <div className="flex-1 h-4 relative bg-gray-100 dark:bg-gray-700 rounded overflow-hidden">
                            <div className="absolute top-0 bottom-0" style={{ right: '50%', width: `${negPct / 2}%`, backgroundColor: '#ef4444' }} title={`${d.neg} negative`} />
                            <div className="absolute top-0 bottom-0" style={{ left: '50%', width: `${posPct / 2}%`, backgroundColor: '#10b981' }} title={`${d.pos} positive`} />
                            <div className="absolute top-0 bottom-0 left-1/2 w-px bg-gray-300 dark:bg-gray-600" />
                          </div>
                          <span className="w-12 flex-shrink-0 text-right text-xs font-mono font-semibold" style={{ color: d.net == null ? '#9ca3af' : net >= 0 ? '#059669' : '#dc2626' }}>
                            {d.net == null ? 'n/a' : `${net > 0 ? '+' : ''}${net}`}
                          </span>
                          <span className="w-28 flex-shrink-0 text-right text-xs text-gray-400 font-mono">
                            {d.pos}+ {d.neu}· {d.neg}−{d.low && <span className="ml-1 text-[9px] italic text-amber-500">low n</span>}
                          </span>
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Fans & Critics — authors ranked by net sentiment toward the brand(s). */}
              {(fansCritics.fans.length > 0 || fansCritics.critics.length > 0) && (() => {
                const maxVol = Math.max(1, ...fansCritics.fans.map(a => a.total), ...fansCritics.critics.map(a => a.total));
                const multiBrand = new Set([...fansCritics.fans, ...fansCritics.critics].map(a => a.brand)).size > 1;
                const row = (a: typeof fansCritics.fans[number], kind: 'fan' | 'crit') => (
                  <div key={`${a.platform}:${a.author}`}
                    title={`@${a.author} · ${a.pos}+ / ${a.neu}· / ${a.neg}− on-brand posts · ${fmtCount(Math.round(kind === 'crit' ? (a as any).negEng : (a as any).posEng))} ${kind === 'crit' ? 'negative' : 'positive'}-post engagement${(a as any).spanDays > 0 ? ` over ${(a as any).spanDays}d` : ''}`}
                    className="w-full flex items-center gap-2 text-left hover:bg-gray-50 dark:hover:bg-gray-750 rounded px-1.5 py-1">
                    <span className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ backgroundColor: platColor(a.platform) }} />
                    <button onClick={() => openAccountFromAuthor(a.platform, a.author)}
                      className="text-xs font-semibold text-blue-700 dark:text-blue-400 truncate max-w-[130px] hover:underline text-left">@{a.author}</button>
                    {fcMeta(a.platform, a.author)}
                    {trendArrow((a as any).trend, kind)}
                    {multiBrand && <span className="text-[10px] px-1.5 py-0.5 rounded-full text-white flex-shrink-0" style={{ backgroundColor: brandColorOf(a.brand) }}>{a.brand}</span>}
                    <div className="flex-1 h-2.5 rounded-full overflow-hidden bg-gray-100 dark:bg-gray-700 flex" style={{ maxWidth: 90 }} title={`${a.pos}+ / ${a.neu}· / ${a.neg}−`}>
                      {a.pos > 0 && <span style={{ width: `${(a.pos / a.total) * 100}%`, backgroundColor: SOCIAL_SENTIMENT_COLORS.positive }} />}
                      {a.neu > 0 && <span style={{ width: `${(a.neu / a.total) * 100}%`, backgroundColor: SOCIAL_SENTIMENT_COLORS.neutral }} />}
                      {a.neg > 0 && <span style={{ width: `${(a.neg / a.total) * 100}%`, backgroundColor: SOCIAL_SENTIMENT_COLORS.negative }} />}
                    </div>
                    <span className="w-10 text-right text-xs font-mono font-semibold flex-shrink-0" style={{ color: kind === 'fan' ? '#059669' : '#dc2626' }}>{a.net > 0 ? '+' : ''}{a.net}</span>
                    <span className="w-12 text-right text-[10px] text-gray-400 flex-shrink-0 font-mono" title={`${kind === 'crit' ? 'negative' : 'positive'}-post engagement (reach)`}>{fmtCount(Math.round(kind === 'crit' ? (a as any).negEng : (a as any).posEng))}</span>
                    <button onClick={() => viewAuthorPosts(a.platform, a.author)} title="See their posts"
                      className="flex-shrink-0 text-gray-300 hover:text-blue-500"><Eye className="w-3 h-3" /></button>
                  </div>
                );
                return (
                  <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
                    <button onClick={() => setShowFansCritics(v => !v)} className="w-full flex items-center justify-between px-4 py-2.5 border-b border-gray-100 dark:border-gray-700">
                      <div className="flex items-center gap-2">
                        <ChevronRight className={`w-3.5 h-3.5 text-gray-400 transition-transform ${showFansCritics ? 'rotate-90' : ''}`} />
                        <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-100">Fans &amp; Critics</h3>
                        <span className="text-xs text-gray-400">influence-ranked (posts × engagement) · {fansCritics.authors} authors</span>
                      </div>
                    </button>
                    {showFansCritics && (
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 p-3">
                        <div>
                          <div className="text-xs font-semibold text-emerald-700 dark:text-emerald-400 mb-1.5 px-1.5 flex items-center gap-1">😊 Top fans{fansCritics.ownHidden > 0 && <span className="font-normal text-gray-400">· {fansCritics.ownHidden} own account{fansCritics.ownHidden === 1 ? '' : 's'} hidden</span>}</div>
                          <div className="space-y-0.5">
                            {fansCritics.fans.length ? fansCritics.fans.map(a => row(a, 'fan')) : <p className="text-xs text-gray-400 px-1.5 py-2">No net-positive authors in range.</p>}
                          </div>
                        </div>
                        <div>
                          <div className="text-xs font-semibold text-red-700 dark:text-red-400 mb-1.5 px-1.5 flex items-center gap-1">😠 Top critics</div>
                          <div className="space-y-0.5">
                            {fansCritics.critics.length ? fansCritics.critics.map(a => row(a, 'crit')) : <p className="text-xs text-gray-400 px-1.5 py-2">No net-negative authors in range.</p>}
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })()}

              {(socialAuthorFilter || socialDayFilter || socialThemeFilter) && (
                <div className="flex items-center gap-2 flex-wrap px-3 py-2 rounded-lg bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800">
                  <span className="text-xs text-blue-700 dark:text-blue-300 font-medium">Filters:</span>
                  {socialAuthorFilter && (
                    <button onClick={() => setSocialAuthorFilter(null)} title="Clear author filter"
                      className="text-xs px-2 py-0.5 rounded-full border border-blue-300 dark:border-blue-700 text-blue-700 dark:text-blue-300 hover:bg-blue-100 dark:hover:bg-blue-900/40 inline-flex items-center gap-1">
                      @{socialAuthorFilter.author} · {socialAuthorFilter.platform} <X className="w-3 h-3" />
                    </button>
                  )}
                  {socialDayFilter && (
                    <button onClick={() => setSocialDayFilter(null)} title="Clear day filter"
                      className="text-xs px-2 py-0.5 rounded-full border border-blue-300 dark:border-blue-700 text-blue-700 dark:text-blue-300 hover:bg-blue-100 dark:hover:bg-blue-900/40 inline-flex items-center gap-1">
                      {socialDayFilter} <X className="w-3 h-3" />
                    </button>
                  )}
                  {socialThemeFilter && (
                    <button onClick={() => setSocialThemeFilter(null)} title="Clear theme filter"
                      className="text-xs px-2 py-0.5 rounded-full border border-blue-300 dark:border-blue-700 text-blue-700 dark:text-blue-300 hover:bg-blue-100 dark:hover:bg-blue-900/40 inline-flex items-center gap-1">
                      {SOCIAL_NEG_THEMES.find(t => t.key === socialThemeFilter)?.label || 'Other'} (negative) <X className="w-3 h-3" />
                    </button>
                  )}
                </div>
              )}

              {/* Sentiment timeline (diverging: positive up, negative down; click a day to filter)
                  + negativity themes ("what are they angry about"). */}
              {(() => {
                const all = (socialView?.all || []).filter(p => (p.relevance ?? 0) >= 0.4);
                const byDay: Record<string, { day: string; pos: number; neg: number }> = {};
                all.forEach(p => {
                  const d = (p.publication_date || '').slice(0, 10);
                  const sen = socialSentimentOf(p.sentiment);
                  if (!d || (sen !== 'positive' && sen !== 'negative')) return;
                  if (!byDay[d]) byDay[d] = { day: d, pos: 0, neg: 0 };
                  byDay[d][sen === 'positive' ? 'pos' : 'neg']++;
                });
                const days = Object.values(byDay).sort((a, b) => a.day.localeCompare(b.day))
                  .map(d => ({ ...d, negDown: -d.neg }));
                const negPosts = all.filter(p => socialSentimentOf(p.sentiment) === 'negative');
                const themes = SOCIAL_NEG_THEMES
                  .map(t => ({ key: t.key, label: t.label, n: negPosts.filter(p => t.re.test(socialThemeBlobOf(p))).length }))
                  .filter(t => t.n > 0).sort((a, b) => b.n - a.n);
                const otherN = negPosts.filter(p => !SOCIAL_NEG_THEMES.some(t => t.re.test(socialThemeBlobOf(p)))).length;
                if (otherN > 0) themes.push({ key: 'other', label: 'Other', n: otherN });
                const maxTheme = Math.max(1, ...themes.map(t => t.n));
                const clickDay = (d: any) => { if (d?.day) setSocialDayFilter(prev => prev === d.day ? null : d.day); };
                if (days.length < 2 && !themes.length) return null;
                return (
                  <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                    {days.length >= 2 && (
                      <div className="lg:col-span-2 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-3">
                        <div className="text-xs font-semibold text-gray-800 dark:text-gray-100 mb-1 px-1">
                          Sentiment timeline <span className="font-normal text-gray-400">positive up · negative down · click a day to filter</span>
                        </div>
                        <ResponsiveContainer width="100%" height={150}>
                          <BarChart data={days} margin={{ top: 4, right: 8, left: -24, bottom: 0 }}>
                            <CartesianGrid strokeDasharray="3 3" vertical={false} />
                            <XAxis dataKey="day" tick={{ fontSize: 9 }} tickFormatter={(d: string) => d.slice(5)} />
                            <YAxis tick={{ fontSize: 9 }} tickFormatter={(v: number) => String(Math.abs(v))} />
                            <Tooltip labelFormatter={(d: any) => d}
                              formatter={(v: any, name: any) => [Math.abs(Number(v)), name === 'negDown' ? 'negative' : 'positive']} />
                            <ReferenceLine y={0} stroke="#9ca3af" />
                            <Bar dataKey="pos" stackId="d" cursor="pointer" onClick={clickDay}>
                              {days.map(d => <Cell key={d.day} fill="#10b981" opacity={socialDayFilter && socialDayFilter !== d.day ? 0.3 : 1} />)}
                            </Bar>
                            <Bar dataKey="negDown" stackId="d" cursor="pointer" onClick={clickDay}>
                              {days.map(d => <Cell key={d.day} fill="#ef4444" opacity={socialDayFilter && socialDayFilter !== d.day ? 0.3 : 1} />)}
                            </Bar>
                          </BarChart>
                        </ResponsiveContainer>
                      </div>
                    )}
                    {themes.length > 0 && (
                      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-3">
                        <div className="text-xs font-semibold text-gray-800 dark:text-gray-100 mb-1.5 px-1">
                          What the negativity is about <span className="font-normal text-gray-400">click to filter</span>
                        </div>
                        <div className="space-y-1">
                          {themes.map(t => (
                            <button key={t.key}
                              onClick={() => setSocialThemeFilter(prev => prev === t.key ? null : t.key)}
                              className={`w-full flex items-center gap-2 text-left rounded px-1.5 py-0.5 hover:bg-gray-50 dark:hover:bg-gray-750 ${socialThemeFilter === t.key ? 'bg-red-50 dark:bg-red-900/20' : ''}`}>
                              <span className="text-xs text-gray-600 dark:text-gray-300 w-28 truncate flex-shrink-0">{t.label}</span>
                              <div className="flex-1 h-2.5 bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden">
                                <div className="h-full rounded-full bg-red-400" style={{ width: `${(t.n / maxTheme) * 100}%` }} />
                              </div>
                              <span className="text-xs font-mono text-gray-400 w-6 text-right flex-shrink-0">{t.n}</span>
                            </button>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                );
              })()}

              {/* Two lanes — each independently platform-filtered, sentiment-filtered, searched + sorted.
                  Pick a network per lane to compare any two side by side. */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {renderSocialLane(bskyFilter, setBskyFilter)}
                {renderSocialLane(feedFilter, setFeedFilter)}
              </div>
            </>
          )}

          {!loadingSocial && !social && (
            <div className="text-center py-12 text-gray-400 text-sm">No social data loaded.</div>
          )}
        </div>
      )}

      {activeTab === 'accounts' && (
        <div className="space-y-4">
          <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-100 dark:border-blue-800 rounded-lg p-4">
            <p className="text-sm text-gray-700 dark:text-gray-200">
              <span className="font-semibold">Accounts.</span> Profile any X, Reddit, Instagram or TikTok handle — identity, reach, what they post about{selectedBrand ? <> and their relationship to <span className="font-semibold">{selectedBrand.display_name}</span></> : null}. Built on demand from xpoz. Tip: click a post author in the Social tab to profile them directly.
            </p>
            <div className="flex items-center gap-2 mt-3 flex-wrap">
              <select value={accSearch.platform} onChange={e => setAccSearch({ ...accSearch, platform: e.target.value })}
                className="text-sm px-2 py-1.5 rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200">
                {['twitter', 'bluesky', 'reddit', 'instagram', 'tiktok'].map(p => <option key={p} value={p}>{platLabel(p)}</option>)}
              </select>
              <div className="relative flex-1 min-w-[180px]">
                <AtSign className="w-3.5 h-3.5 text-gray-400 absolute left-2.5 top-1/2 -translate-y-1/2" />
                <input type="text" value={accSearch.handle} placeholder="handle (without @)"
                  onChange={e => setAccSearch({ ...accSearch, handle: e.target.value })}
                  onKeyDown={e => { if (e.key === 'Enter') profileAccount(accSearch.platform, accSearch.handle); }}
                  className="w-full text-sm pl-8 pr-2 py-1.5 rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200 focus:outline-none focus:border-blue-400" />
              </div>
              <button onClick={() => profileAccount(accSearch.platform, accSearch.handle)} disabled={accLoading || !accSearch.handle.trim()}
                className="text-sm px-4 py-1.5 rounded-md bg-blue-600 text-white font-medium hover:bg-blue-700 disabled:opacity-50 inline-flex items-center gap-1.5">
                {accLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />} Profile
              </button>
            </div>
            {accError && <p className="text-sm text-red-600 dark:text-red-400 mt-2">{accError}</p>}
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            {/* Saved profiles list */}
            <div className="lg:col-span-1 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
              <div className="px-4 py-2.5 border-b border-gray-100 dark:border-gray-700 text-sm font-semibold text-gray-800 dark:text-gray-100">Saved profiles ({accountsList.length})</div>
              <div className="divide-y divide-gray-100 dark:divide-gray-700 max-h-[640px] overflow-y-auto">
                {accountsList.map(a => (
                  <div key={a.id} onClick={() => { setAccountProfile(a); setAccSearch({ platform: a.platform, handle: a.handle }); }}
                    className={`group w-full flex items-center gap-2.5 p-2.5 text-left cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-750 ${accountProfile?.id === a.id ? 'bg-blue-50 dark:bg-blue-900/20' : ''}`}>
                    {a.avatar_url ? <img src={a.avatar_url} alt="" referrerPolicy="no-referrer" className="w-8 h-8 rounded-full object-cover flex-shrink-0 bg-gray-100" onError={e => { (e.currentTarget as HTMLImageElement).style.display = 'none'; }} /> : <UserCircle className="w-8 h-8 text-gray-300 flex-shrink-0" />}
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5">
                        <span className="text-sm font-medium text-gray-800 dark:text-gray-100 truncate">{a.display_name || a.handle}</span>
                        {a.verified && <BadgeCheck className="w-3.5 h-3.5 text-blue-500 flex-shrink-0" />}
                      </div>
                      <div className="flex items-center gap-1.5">
                        <span className="text-[10px] font-semibold px-1 rounded text-white" style={{ backgroundColor: platColor(a.platform) }}>{platLabel(a.platform)}</span>
                        <span className="text-xs text-gray-400 truncate">@{a.handle}</span>
                      </div>
                    </div>
                    <button onClick={e => { e.stopPropagation(); handleDeleteAccount(a.id); }} title="Delete profile"
                      className="opacity-0 group-hover:opacity-100 text-gray-400 hover:text-red-500 flex-shrink-0"><Trash2 className="w-3.5 h-3.5" /></button>
                  </div>
                ))}
                {accountsList.length === 0 && <div className="p-6 text-center text-xs text-gray-400">No profiles yet. Profile a handle above.</div>}
              </div>
            </div>

            {/* Selected profile */}
            <div className="lg:col-span-2">
              {accLoading && !accountProfile && <div className="flex items-center justify-center py-16 text-gray-400"><Loader2 className="w-6 h-6 animate-spin" /></div>}
              {accountProfile && (() => {
                const p = accountProfile; const s = p.post_sentiment;
                return (
                  <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-5 space-y-4">
                    {/* header */}
                    <div className="flex items-start gap-3">
                      {p.avatar_url ? <img src={p.avatar_url} alt="" referrerPolicy="no-referrer" className="w-14 h-14 rounded-full object-cover flex-shrink-0 bg-gray-100" onError={e => { (e.currentTarget as HTMLImageElement).style.display = 'none'; }} /> : <UserCircle className="w-14 h-14 text-gray-300 flex-shrink-0" />}
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2 flex-wrap">
                          <h2 className="text-lg font-bold text-gray-900 dark:text-gray-100 truncate">{p.display_name || p.handle}</h2>
                          {p.verified && <BadgeCheck className="w-4 h-4 text-blue-500" />}
                          <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded-full text-white" style={{ backgroundColor: platColor(p.platform) }}>{platLabel(p.platform)}</span>
                        </div>
                        <a href={p.profile_url || '#'} target="_blank" rel="noopener noreferrer" className="text-sm text-blue-600 dark:text-blue-400 hover:underline">@{p.handle}</a>
                        {p.bio && <p className="text-sm text-gray-600 dark:text-gray-300 mt-1">{p.bio}</p>}
                      </div>
                      <div className="flex items-center gap-1.5 flex-shrink-0">
                        <button onClick={() => downloadAccountReport(p, accDeepDive)} title="Download HTML report"
                          className="text-xs px-2 py-1 rounded-md border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300 hover:border-blue-400 inline-flex items-center gap-1">
                          <Download className="w-3 h-3" /> Report
                        </button>
                        <button onClick={() => profileAccount(p.platform, p.handle)} disabled={accLoading} title="Refresh from xpoz"
                          className="text-xs px-2 py-1 rounded-md border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300 hover:border-blue-400 inline-flex items-center gap-1">
                          {accLoading ? <Loader2 className="w-3 h-3 animate-spin" /> : <RefreshCw className="w-3 h-3" />} Refresh
                        </button>
                        <button onClick={() => handleDeleteAccount(p.id)} title="Delete profile"
                          className="text-xs px-2 py-1 rounded-md border border-gray-300 dark:border-gray-600 text-gray-500 hover:border-red-400 hover:text-red-500 inline-flex items-center gap-1">
                          <Trash2 className="w-3 h-3" />
                        </button>
                      </div>
                    </div>

                    {/* reach stats */}
                    <div className="grid grid-cols-3 gap-2">
                      {[['Followers', p.followers_count], ['Following', p.following_count], [p.platform === 'reddit' ? 'Link karma' : 'Posts', p.posts_count]].map(([label, val]) => (
                        <div key={label as string} className="p-2.5 bg-gray-50 dark:bg-gray-750 rounded-lg text-center">
                          <p className="text-lg font-bold text-gray-900 dark:text-gray-100">{val == null ? '—' : (fmtCount(val as number) || val)}</p>
                          <p className="text-[11px] text-gray-400">{label}</p>
                        </div>
                      ))}
                    </div>

                    {p.summary && <div><p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Summary</p><p className="text-sm text-gray-700 dark:text-gray-200">{p.summary}</p></div>}
                    {p.brand_context && <div className="p-3 bg-amber-50 dark:bg-amber-900/20 border border-amber-100 dark:border-amber-800 rounded-lg"><p className="text-xs font-semibold text-amber-700 dark:text-amber-400 mb-0.5">Brand context</p><p className="text-sm text-gray-700 dark:text-gray-200">{p.brand_context}</p></div>}

                    {(p.topics && p.topics.length > 0) && (
                      <div className="flex items-center gap-1.5 flex-wrap">
                        {p.topics.map(t => <span key={t} className="text-xs px-2 py-0.5 rounded-full bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300">{t}</span>)}
                      </div>
                    )}

                    {s && s.scored ? (
                      <div>
                        <div className="flex items-center justify-between mb-1">
                          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Sentiment {selectedBrand ? `toward ${selectedBrand.display_name}` : ''}</p>
                          <span className={`text-xs font-mono font-semibold ${s.net == null ? 'text-gray-400' : s.net > 0 ? 'text-green-600' : s.net < 0 ? 'text-red-600' : 'text-gray-500'}`}>{s.net == null ? '' : `net ${s.net > 0 ? '+' : ''}${s.net}`}</span>
                        </div>
                        <div className="flex h-3 rounded-full overflow-hidden bg-gray-100 dark:bg-gray-700">
                          <div style={{ width: `${(s.pos || 0) / s.scored * 100}%`, backgroundColor: SOCIAL_SENTIMENT_COLORS.positive }} title={`${s.pos} positive`} />
                          <div style={{ width: `${(s.neu || 0) / s.scored * 100}%`, backgroundColor: SOCIAL_SENTIMENT_COLORS.neutral }} title={`${s.neu} neutral`} />
                          <div style={{ width: `${(s.neg || 0) / s.scored * 100}%`, backgroundColor: SOCIAL_SENTIMENT_COLORS.negative }} title={`${s.neg} negative`} />
                        </div>
                        <p className="text-[11px] text-gray-400 mt-1">{s.pos}+ · {s.neu}· · {s.neg}− across {s.scored} recent posts</p>
                      </div>
                    ) : null}

                    {/* Tags */}
                    <div>
                      <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1.5 flex items-center gap-1"><Tag className="w-3 h-3" /> Tags</p>
                      <div className="flex items-center gap-1.5 flex-wrap">
                        {(p.tags || []).map(t => (
                          <span key={t} className="text-xs px-2 py-0.5 rounded-full bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 inline-flex items-center gap-1">
                            {t}<button onClick={() => handleRemoveTag(t)} className="hover:text-red-500"><X className="w-3 h-3" /></button>
                          </span>
                        ))}
                        <input type="text" value={accTagInput} placeholder="add tag…" onChange={e => setAccTagInput(e.target.value)}
                          onKeyDown={e => { if (e.key === 'Enter') handleAddTag(); }}
                          className="text-xs px-2 py-0.5 rounded-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200 w-24 focus:outline-none focus:border-blue-400" />
                      </div>
                    </div>

                    {/* Note */}
                    <div>
                      <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1.5">Note</p>
                      <textarea value={accNoteInput} onChange={e => setAccNoteInput(e.target.value)} onBlur={handleSaveNote} rows={2}
                        placeholder="Analyst note…" className="w-full text-sm px-2.5 py-1.5 rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200 focus:outline-none focus:border-blue-400" />
                    </div>

                    {/* Top posts */}
                    {(p.sample_posts && p.sample_posts.length > 0) && (
                      <div>
                        <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1.5">Top posts</p>
                        <div className="space-y-2">
                          {p.sample_posts.map(sp => {
                            const psent = socialSentimentOf((sp as any).sentiment);
                            return (
                              <div key={sp.id} className="flex gap-2.5 p-2.5 bg-gray-50 dark:bg-gray-750 rounded-lg">
                                {sp.thumbnail && <img src={sp.thumbnail} alt="" referrerPolicy="no-referrer" className="w-10 h-10 rounded object-cover flex-shrink-0 bg-gray-100" onError={e => { (e.currentTarget as HTMLImageElement).style.display = 'none'; }} />}
                                <div className="min-w-0 flex-1">
                                  <p className="text-sm text-gray-700 dark:text-gray-200 whitespace-pre-wrap break-words">{sp.text || '(no text)'}</p>
                                  <div className="flex items-center gap-2 mt-1 text-[11px] text-gray-400 flex-wrap">
                                    {(sp as any).sentiment && <span className="px-1.5 rounded-full text-white" style={{ backgroundColor: SOCIAL_SENTIMENT_COLORS[psent] }}>{(sp as any).sentiment}</span>}
                                    {sp.created_at && <span>{sp.created_at.slice(0, 10)}</span>}
                                    {sp.likes != null && <span>♥ {fmtCount(sp.likes)}</span>}
                                    {sp.comments != null && <span>💬 {fmtCount(sp.comments)}</span>}
                                    {sp.plays != null && <span>▶ {fmtCount(sp.plays)}</span>}
                                    {sp.url && <a href={sp.url} target="_blank" rel="noopener noreferrer" className="text-blue-600 dark:text-blue-400 hover:underline">view</a>}
                                  </div>
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    )}

                    {/* Deep dive */}
                    <div className="border-t border-gray-100 dark:border-gray-700 pt-3">
                      {!accDeepDive && (
                        <button onClick={handleDeepDive} disabled={accDeepLoading}
                          className="text-sm px-3 py-1.5 rounded-md border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-200 hover:border-blue-400 inline-flex items-center gap-1.5 disabled:opacity-50">
                          {accDeepLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <TrendingUp className="w-4 h-4" />} Deep dive (activity, engagement, connections)
                        </button>
                      )}
                      {accDeepDive && (() => {
                        const dd = accDeepDive;
                        return (
                          <div className="space-y-3">
                            <div className="flex items-center justify-between">
                              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Deep dive · {dd.posts_analyzed} posts</p>
                              <button onClick={() => setAccDeepDive(null)} className="text-xs text-gray-400 hover:text-gray-600">collapse</button>
                            </div>
                            <div className="grid grid-cols-4 gap-2">
                              {[['Total likes', dd.engagement.total_likes], ['Avg likes', dd.engagement.avg_likes], ['Comments', dd.engagement.total_comments], ['Max likes', dd.engagement.max_likes]].map(([l, v]) => (
                                <div key={l as string} className="p-2 bg-gray-50 dark:bg-gray-750 rounded text-center">
                                  <p className="text-sm font-bold text-gray-900 dark:text-gray-100">{fmtCount(v as number) || v}</p>
                                  <p className="text-[10px] text-gray-400">{l}</p>
                                </div>
                              ))}
                            </div>
                            {dd.timeline.length > 0 && (
                              <div>
                                <p className="text-[11px] text-gray-400 mb-1">Activity by day (post volume)</p>
                                <ResponsiveContainer width="100%" height={140}>
                                  <BarChart data={dd.timeline} margin={{ top: 4, right: 4, left: -24, bottom: 0 }}>
                                    <CartesianGrid strokeDasharray="3 3" className="opacity-30" />
                                    <XAxis dataKey="date" tick={{ fontSize: 9 }} tickFormatter={(d: string) => d.slice(5)} />
                                    <YAxis tick={{ fontSize: 9 }} allowDecimals={false} />
                                    <Tooltip />
                                    <Bar dataKey="count" fill={platColor(dd.platform)} radius={[2, 2, 0, 0]} />
                                  </BarChart>
                                </ResponsiveContainer>
                              </div>
                            )}
                            {dd.connections.length > 0 && (
                              <div>
                                <p className="text-[11px] text-gray-400 mb-1">Follows (sample of {dd.connections.length})</p>
                                <div className="flex items-center gap-1.5 flex-wrap">
                                  {dd.connections.map(c => (
                                    <span key={c.handle} className="text-xs px-2 py-0.5 rounded-full bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300">
                                      @{c.handle}{c.followers != null && <span className="text-gray-400"> · {fmtCount(c.followers)}</span>}
                                    </span>
                                  ))}
                                </div>
                              </div>
                            )}
                            {dd.platform !== 'twitter' && dd.platform !== 'instagram' && dd.connections.length === 0 && (
                              <p className="text-[11px] text-gray-400">Connections not available for {platLabel(dd.platform)}.</p>
                            )}
                          </div>
                        );
                      })()}
                    </div>

                    {p.last_profiled_at && <p className="text-[11px] text-gray-400 text-right">profiled {p.last_profiled_at.slice(0, 10)}</p>}
                  </div>
                );
              })()}
              {!accLoading && !accountProfile && (
                <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-12 text-center text-sm text-gray-400">
                  Profile a handle or pick a saved profile to see identity, reach, sentiment, topics and top posts.
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {(activeTab === 'comparison' || exportingReport) && (
        <div className={`space-y-6 ${exportingReport ? 'order-5' : ''}`}>
          {exportingReport && (
            <h2 className="text-2xl font-bold text-gray-900 border-b-2 border-blue-500 pb-2 pt-6">4. Competitive Comparison</h2>
          )}
          {/* Share of Voice — Pie Chart */}
          {shareOfVoice.length > 0 && (() => {
            const pieData = shareOfVoice.map(sov => ({
              name: sov.brand_name,
              value: sov.mention_count,
              percentage: sov.percentage,
              fill: sov.color || '#6b7280',
            }));
            return (
              <div id="chart-brand-share-of-voice" className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300">Share of Voice</h3>
                  <ChartDownloadButton targetId="chart-brand-share-of-voice" filename="share-of-voice" />
                </div>
                <div className="flex flex-col md:flex-row items-center gap-6">
                  <ResponsiveContainer width="100%" height={240} className="md:max-w-[280px]">
                    <PieChart>
                      <Pie
                        data={pieData}
                        cx="50%"
                        cy="50%"
                        outerRadius={100}
                        innerRadius={50}
                        dataKey="value"
                        paddingAngle={2}
                        stroke="none"
                      >
                        {pieData.map((entry, i) => (
                          <Cell key={i} fill={entry.fill} />
                        ))}
                      </Pie>
                      <Tooltip
                        content={({ active, payload }) => {
                          if (!active || !payload?.length) return null;
                          const d = payload[0].payload;
                          return (
                            <div className="bg-gray-900 text-white text-xs rounded-lg shadow-lg px-3 py-2">
                              <p className="font-semibold">{d.name}</p>
                              <p>{d.value} articles ({d.percentage.toFixed(1)}%)</p>
                            </div>
                          );
                        }}
                      />
                    </PieChart>
                  </ResponsiveContainer>
                  <div className="flex-1 space-y-2">
                    {shareOfVoice.map(sov => (
                      <button key={sov.brand_id}
                        onClick={() => { updateConfig({ selectedBrandIds: [sov.brand_id], selectedCategories: [], page: 1 }); setActiveTab('articles'); }}
                        className="w-full flex items-center gap-3 rounded-md px-1 py-0.5 -mx-1 hover:bg-gray-50 dark:hover:bg-gray-700/40 transition-colors text-left"
                        title={`View ${sov.brand_name} articles`}>
                        <div className="w-3 h-3 rounded-full flex-shrink-0" style={{ backgroundColor: sov.color || '#6b7280' }} />
                        <span className="text-sm text-gray-700 dark:text-gray-300 flex-1 truncate">{sov.brand_name}</span>
                        <span className="text-sm font-bold text-gray-900 dark:text-gray-100">{sov.percentage.toFixed(1)}%</span>
                        <span className="text-xs text-gray-400 w-20 text-right">{sov.mention_count} articles</span>
                        <ChevronRight className="w-3 h-3 text-gray-300 dark:text-gray-600 flex-shrink-0" />
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            );
          })()}

          {/* Category Breakdown by Brand — stacked bar chart with category dropdown */}
          {comparison.length > 0 && (() => {
            // Collect all categories across all brands
            const allCatsSet = new Set<string>();
            comparison.forEach(comp => {
              Object.entries(comp.category_breakdown).forEach(([k, v]) => { if (v > 0) allCatsSet.add(k); });
            });
            const allCats = [...allCatsSet].sort((a, b) => {
              const aTotal = comparison.reduce((sum, c) => sum + (c.category_breakdown[a] || 0), 0);
              const bTotal = comparison.reduce((sum, c) => sum + (c.category_breakdown[b] || 0), 0);
              return bTotal - aTotal;
            });

            // If a category is selected, show only that category
            const displayCats = compCategoryFilter ? [compCategoryFilter] : allCats.slice(0, 8);

            const chartData = displayCats.map(cat => {
              const row: Record<string, string | number> = { category: CATEGORY_SHORT_NAMES[cat] || cat };
              comparison.forEach(comp => {
                row[comp.brand_name] = comp.category_breakdown[cat] || 0;
              });
              return row;
            });

            return (
              <div id="chart-brand-category-breakdown" className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300">Category Breakdown</h3>
                  <div className="flex items-center gap-2">
                  {/* Category filter dropdown (hidden during export) */}
                  {!exportingReport && (
                    <div className="relative">
                      <button
                        onClick={() => setShowCompCatDropdown(!showCompCatDropdown)}
                        className="flex items-center gap-2 px-3 py-1.5 text-xs bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg dark:text-gray-100"
                      >
                        <span>{compCategoryFilter ? (CATEGORY_SHORT_NAMES[compCategoryFilter] || compCategoryFilter) : 'All categories'}</span>
                        <ChevronDown className="w-3.5 h-3.5" />
                      </button>
                      {showCompCatDropdown && (
                        <>
                          <div className="fixed inset-0 z-40" onClick={() => setShowCompCatDropdown(false)} />
                          <div className="absolute top-full right-0 mt-1 w-56 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg z-50 py-1 max-h-60 overflow-y-auto">
                            <button
                              onClick={() => { setCompCategoryFilter(null); setShowCompCatDropdown(false); }}
                              className={`w-full flex items-center gap-2 px-3 py-2 text-xs hover:bg-gray-50 dark:hover:bg-gray-750 text-left ${
                                !compCategoryFilter ? 'text-blue-600 dark:text-blue-400 font-medium' : 'text-gray-700 dark:text-gray-300'
                              }`}
                            >
                              All categories (top 8)
                            </button>
                            {allCats.map(cat => (
                              <button key={cat}
                                onClick={() => { setCompCategoryFilter(cat); setShowCompCatDropdown(false); }}
                                className={`w-full flex items-center gap-2 px-3 py-2 text-xs hover:bg-gray-50 dark:hover:bg-gray-750 text-left ${
                                  compCategoryFilter === cat ? 'text-blue-600 dark:text-blue-400 font-medium' : 'text-gray-700 dark:text-gray-300'
                                }`}
                              >
                                <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: CATEGORY_COLORS[cat] || '#6b7280' }} />
                                <span className="flex-1 truncate">{CATEGORY_SHORT_NAMES[cat] || cat}</span>
                                <span className="text-gray-400">{comparison.reduce((s, c) => s + (c.category_breakdown[cat] || 0), 0)}</span>
                              </button>
                            ))}
                          </div>
                        </>
                      )}
                    </div>
                  )}
                  <ChartDownloadButton targetId="chart-brand-category-breakdown" filename="category-breakdown" />
                  </div>
                </div>
                <ResponsiveContainer width="100%" height={Math.max(displayCats.length * 44, 120)}>
                  <BarChart data={chartData} layout="vertical" margin={{ top: 0, right: 10, bottom: 0, left: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.2} horizontal={false} />
                    <XAxis type="number" stroke="#9CA3AF" fontSize={11} />
                    <YAxis type="category" dataKey="category" stroke="#9CA3AF" fontSize={11} width={85} tick={{ fill: '#9CA3AF' }} />
                    <Tooltip contentStyle={{ backgroundColor: '#1F2937', border: 'none', borderRadius: '8px', color: '#F3F4F6', fontSize: '12px' }} />
                    <Legend wrapperStyle={{ fontSize: '11px' }} />
                    {comparison.map(comp => (
                      <Bar key={comp.brand_id} dataKey={comp.brand_name} fill={comp.color || '#6b7280'} radius={[0, 4, 4, 0]} />
                    ))}
                  </BarChart>
                </ResponsiveContainer>
              </div>
            );
          })()}

          {/* Cross-brand comparison table */}
          {comparison.length > 0 && (
            <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6 overflow-x-auto">
              <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-4">Category Comparison</h3>
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-200 dark:border-gray-700">
                    <th className="text-left py-2 px-2 text-gray-500 dark:text-gray-400">Brand</th>
                    <th className="text-right py-2 px-2 text-gray-500 dark:text-gray-400">Total</th>
                    {Object.keys(CATEGORY_SHORT_NAMES).map(cat => (
                      <th key={cat} title={cat} className="text-right py-2 px-1 text-gray-500 dark:text-gray-400 text-xs">
                        {CATEGORY_SHORT_NAMES[cat]}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {comparison.map(comp => {
                    // Find which category this brand leads in
                    const maxCat = Object.entries(comp.category_breakdown).sort(([, a], [, b]) => b - a)[0]?.[0];
                    return (
                      <tr key={comp.brand_id} className="border-b border-gray-100 dark:border-gray-700/50">
                        <td className="py-2 px-2">
                          <div className="flex items-center gap-2">
                            <div className="w-2 h-2 rounded-full" style={{ backgroundColor: comp.color || '#6b7280' }} />
                            <span className="font-medium text-gray-700 dark:text-gray-300">{comp.brand_name}</span>
                          </div>
                        </td>
                        <td className="py-2 px-2 text-right font-bold text-gray-700 dark:text-gray-300">{comp.total_articles}</td>
                        {Object.keys(CATEGORY_SHORT_NAMES).map(cat => {
                          const count = comp.category_breakdown[cat] || 0;
                          const isLeading = cat === maxCat && count > 0;
                          return (
                            <td key={cat}
                              className={`py-2 px-1 text-right cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-750 transition-colors ${
                                isLeading ? 'font-bold text-gray-800 dark:text-gray-200' : 'text-gray-600 dark:text-gray-400'
                              }`}
                              title={`View ${comp.brand_name} — ${cat} articles`}
                              onClick={() => {
                                updateConfig({ selectedBrandIds: [comp.brand_id], selectedCategories: [cat], page: 1 });
                                setActiveTab('articles');
                              }}
                            >
                              {count > 0 ? count : <span className="text-gray-300 dark:text-gray-600">—</span>}
                            </td>
                          );
                        })}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              <p className="text-[10px] text-gray-400 mt-2">Click any cell to drill down to those articles. Bold = top category for that brand.</p>
            </div>
          )}

          {/* Sentiment Summary — uses sentiment_breakdown from comparison API */}
          {comparison.length > 0 && comparison.some(c => Object.keys(c.sentiment_breakdown || {}).length > 0) && (
            <div id="chart-brand-sentiment-summary" className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300">Sentiment Summary by Brand</h3>
                <ChartDownloadButton targetId="chart-brand-sentiment-summary" filename="sentiment-summary-by-brand" />
              </div>
              <div className="space-y-3">
                {comparison.map(comp => {
                  // Normalize sentiment labels into 3 buckets
                  const sentCounts = { positive: 0, neutral: 0, negative: 0 };
                  for (const [label, count] of Object.entries(comp.sentiment_breakdown || {})) {
                    const lo = label.toLowerCase();
                    if (lo === 'positive' || lo === 'optimistic' || lo === 'positive development') sentCounts.positive += count;
                    else if (lo === 'negative' || lo === 'pessimistic' || lo === 'concerning' || lo === 'concerned' || lo === 'critical' || lo === 'alarming') sentCounts.negative += count;
                    else sentCounts.neutral += count;
                  }
                  const total = sentCounts.positive + sentCounts.neutral + sentCounts.negative || 1;
                  return (
                    <div key={comp.brand_id} className="flex items-center gap-3">
                      <div className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ backgroundColor: comp.color || '#6b7280' }} />
                      <span className="text-sm text-gray-700 dark:text-gray-300 w-28 truncate">{comp.brand_name}</span>
                      <div className="flex-1 h-4 bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden flex">
                        {sentCounts.positive > 0 && (
                          <div className="h-full bg-green-500" title={`Positive: ${sentCounts.positive}`}
                            style={{ width: `${(sentCounts.positive / total) * 100}%` }} />
                        )}
                        {sentCounts.neutral > 0 && (
                          <div className="h-full bg-gray-400" title={`Neutral: ${sentCounts.neutral}`}
                            style={{ width: `${(sentCounts.neutral / total) * 100}%` }} />
                        )}
                        {sentCounts.negative > 0 && (
                          <div className="h-full bg-red-500" title={`Negative: ${sentCounts.negative}`}
                            style={{ width: `${(sentCounts.negative / total) * 100}%` }} />
                        )}
                      </div>
                      <div className="flex items-center gap-2 text-[10px] w-36 justify-end">
                        <span className="text-green-600">{sentCounts.positive}</span>
                        <span className="text-gray-400">{sentCounts.neutral}</span>
                        <span className="text-red-600">{sentCounts.negative}</span>
                      </div>
                    </div>
                  );
                })}
              </div>
              <div className="flex items-center gap-3 mt-2">
                {[
                  { label: 'Positive', color: 'bg-green-500' },
                  { label: 'Neutral', color: 'bg-gray-400' },
                  { label: 'Negative', color: 'bg-red-500' },
                ].map(s => (
                  <span key={s.label} className="flex items-center gap-1 text-[10px] text-gray-500 dark:text-gray-400">
                    <div className={`w-2 h-2 rounded-full ${s.color}`} />
                    {s.label}
                  </span>
                ))}
              </div>
            </div>
          )}

          {comparison.length === 0 && shareOfVoice.length === 0 && (
            <div className="text-center py-12 text-gray-500 dark:text-gray-400">
              <p>No comparison data available. Add brands and run classification first.</p>
            </div>
          )}
        </div>
      )}

      {/* ---- INSIGHTS TAB ---- */}
      {(activeTab === 'insights' || exportingReport) && (
        <div className={`space-y-6 ${exportingReport ? 'order-2' : ''}`}>
          {exportingReport && (
            <h2 className="text-2xl font-bold text-gray-900 border-b-2 border-blue-500 pb-2 pt-6">1. Executive Summary</h2>
          )}
          {config.selectedBrandIds.length === 0 ? (
            <div className="text-center py-12 text-gray-500 dark:text-gray-400">
              <p>Select a brand above to view or generate insights.</p>
            </div>
          ) : (
            <>
              {/* Stats cards */}
              <div className="grid grid-cols-3 gap-4">
                <div className="p-4 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
                  <p className="text-xs text-gray-500 dark:text-gray-400">Articles</p>
                  <p className="text-2xl font-bold text-gray-900 dark:text-gray-100">{stats?.total_articles ?? 0}</p>
                </div>
                <div className="p-4 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
                  <p className="text-xs text-gray-500 dark:text-gray-400">Categories</p>
                  <p className="text-2xl font-bold text-gray-900 dark:text-gray-100">{categories.filter(c => c.article_count > 0).length}</p>
                </div>
                <div className="p-4 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
                  <p className="text-xs text-gray-500 dark:text-gray-400">Brand</p>
                  <p className="text-sm font-semibold text-gray-900 dark:text-gray-100 truncate">{selectedBrand?.display_name || '—'}</p>
                </div>
              </div>

              {/* Company Profile Card */}
              {selectedBrand && (
                <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
                  <div className="flex items-center gap-3 mb-4">
                    {selectedBrand.color && (
                      <div className="w-10 h-10 rounded-lg flex items-center justify-center text-white font-bold text-lg" style={{ backgroundColor: selectedBrand.color }}>
                        {selectedBrand.display_name.charAt(0).toUpperCase()}
                      </div>
                    )}
                    <div>
                      <h3 className="text-base font-semibold text-gray-900 dark:text-gray-100">{selectedBrand.display_name}</h3>
                      {selectedBrand.description && (
                        <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{selectedBrand.description}</p>
                      )}
                    </div>
                    {selectedBrand.is_primary && (
                      <span className="ml-auto text-[10px] px-2 py-0.5 bg-yellow-50 dark:bg-yellow-900/20 text-yellow-700 dark:text-yellow-400 rounded-full border border-yellow-200 dark:border-yellow-800 flex items-center gap-1">
                        <Star className="w-3 h-3 fill-yellow-400 text-yellow-400" /> Primary
                      </span>
                    )}
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {(selectedBrand.brand_keywords?.length ?? 0) > 0 && (
                      <div>
                        <p className="text-[10px] font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-1">Brand Keywords</p>
                        <div className="flex flex-wrap gap-1">
                          {selectedBrand.brand_keywords!.map(kw => (
                            <span key={kw} className="text-xs px-2 py-0.5 bg-blue-50 dark:bg-blue-900/20 text-blue-600 dark:text-blue-400 rounded">{kw}</span>
                          ))}
                        </div>
                      </div>
                    )}
                    {(selectedBrand.product_keywords?.length ?? 0) > 0 && (
                      <div>
                        <p className="text-[10px] font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-1">Products</p>
                        <div className="flex flex-wrap gap-1">
                          {selectedBrand.product_keywords!.map(kw => (
                            <span key={kw} className="text-xs px-2 py-0.5 bg-purple-50 dark:bg-purple-900/20 text-purple-600 dark:text-purple-400 rounded">{kw}</span>
                          ))}
                        </div>
                      </div>
                    )}
                    {(selectedBrand.people_keywords?.length ?? 0) > 0 && (
                      <div>
                        <p className="text-[10px] font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-1">People</p>
                        <div className="flex flex-wrap gap-1">
                          {selectedBrand.people_keywords!.map(kw => (
                            <span key={kw} className="text-xs px-2 py-0.5 bg-green-50 dark:bg-green-900/20 text-green-600 dark:text-green-400 rounded">{kw}</span>
                          ))}
                        </div>
                      </div>
                    )}
                    {(selectedBrand.competitor_keywords?.length ?? 0) > 0 && (
                      <div>
                        <p className="text-[10px] font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-1">Competitors</p>
                        <div className="flex flex-wrap gap-1">
                          {selectedBrand.competitor_keywords!.map(kw => (
                            <span key={kw} className="text-xs px-2 py-0.5 bg-orange-50 dark:bg-orange-900/20 text-orange-600 dark:text-orange-400 rounded">{kw}</span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Generate / Regenerate button (hidden during export) */}
              {!exportingReport && (
                <button
                  onClick={handleGenerateNarrative}
                  disabled={generatingNarrative}
                  className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
                >
                  {generatingNarrative ? <Loader2 className="w-4 h-4 animate-spin" /> : <FileText className="w-4 h-4" />}
                  {narrative ? 'Regenerate Narrative' : 'Generate Narrative'}
                </button>
              )}

              {/* Narrative display */}
              {loadingNarrative && (
                <div className="flex justify-center py-8"><Loader2 className="w-6 h-6 animate-spin text-blue-500" /></div>
              )}
              {narrative && !loadingNarrative && (
                <div id="narrative-report-card" className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300">
                      Brand Intelligence Report — {narrative.brand_name || selectedBrand?.display_name}
                    </h3>
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-gray-400">{narrative.generated_at ? new Date(narrative.generated_at).toLocaleString() : ''}</span>
                      <NarrativeExportButtons narrative={narrative} brandName={narrative.brand_name || selectedBrand?.display_name || 'brand'} />
                    </div>
                  </div>
                  <div className="prose prose-sm dark:prose-invert max-w-none text-gray-700 dark:text-gray-300"
                    dangerouslySetInnerHTML={{ __html: markdownToHtml(narrative.narrative) }}
                  />
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* ---- ARTICLES TAB ---- */}
      {(activeTab === 'articles' || exportingReport) && (
        <div className={`space-y-4 ${exportingReport ? 'order-6' : ''}`}>
          {exportingReport && (
            <h2 className="text-2xl font-bold text-gray-900 border-b-2 border-blue-500 pb-2 pt-6">5. Articles</h2>
          )}
          {/* Category filter chips (hidden during export) */}
          {!exportingReport && (
            <div className="flex flex-wrap gap-2">
              {categories.filter(c => c.article_count > 0).map(cat => {
                const selected = config.selectedCategories.includes(cat.category);
                return (
                  <button key={cat.category}
                    onClick={() => {
                      const next = selected
                        ? config.selectedCategories.filter(c => c !== cat.category)
                        : [...config.selectedCategories, cat.category];
                      updateConfig({ selectedCategories: next });
                    }}
                    className={`px-3 py-1 text-xs rounded-full border transition-colors ${
                      selected
                        ? 'bg-blue-100 dark:bg-blue-900/30 border-blue-300 dark:border-blue-700 text-blue-700 dark:text-blue-300'
                        : 'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-750'
                    }`}
                  >
                    {CATEGORY_SHORT_NAMES[cat.category] || cat.category} ({cat.article_count})
                  </button>
                );
              })}
              {config.selectedCategories.length > 0 && (
                <button onClick={() => updateConfig({ selectedCategories: [] })}
                  className="px-3 py-1 text-xs text-red-500 hover:text-red-700">
                  Clear filters
                </button>
              )}
            </div>
          )}

          {/* Article list */}
          {loadingArticles ? (
            <div className="flex justify-center py-8"><Loader2 className="w-6 h-6 animate-spin text-blue-500" /></div>
          ) : articles.length === 0 ? (
            <div className="text-center py-12 text-gray-500 dark:text-gray-400">No articles found.</div>
          ) : (
            <div className="space-y-3">
              <p className="text-xs text-gray-500 dark:text-gray-400">
                {totalArticles} article{totalArticles !== 1 ? 's' : ''} — page {config.page} of {totalPages}
              </p>
              {articles.map(article => (
                <div key={`${article.uri}-${article.brand_id}`}
                  className="p-4 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 cursor-pointer hover:border-blue-300 dark:hover:border-blue-700 transition-colors"
                  onClick={() => openArticle(article)}
                >
                  <h4 className="text-sm font-medium text-gray-900 dark:text-gray-100 line-clamp-2">{article.title}</h4>
                  {article.summary && (
                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-1 line-clamp-2">{article.summary}</p>
                  )}
                  <div className="flex items-center gap-2 mt-2 flex-wrap">
                    {article.brand_name && (
                      <span className="text-xs px-2 py-0.5 bg-blue-50 dark:bg-blue-900/20 text-blue-600 dark:text-blue-400 rounded">
                        {article.brand_name}
                      </span>
                    )}
                    {article.categories.map(cat => (
                      <span key={cat} title={cat} className="text-xs px-2 py-0.5 rounded" style={{
                        backgroundColor: (CATEGORY_COLORS[cat] || '#6b7280') + '20',
                        color: CATEGORY_COLORS[cat] || '#6b7280',
                      }}>
                        {CATEGORY_SHORT_NAMES[cat] || cat}
                      </span>
                    ))}
                    {article.sentiment && (
                      <span className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded ${
                        article.sentiment.toLowerCase() === 'positive' ? 'bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-400' :
                        article.sentiment.toLowerCase() === 'negative' ? 'bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400' :
                        'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300'
                      }`}>
                        <span className={`w-1.5 h-1.5 rounded-full ${
                          article.sentiment.toLowerCase() === 'positive' ? 'bg-green-500' :
                          article.sentiment.toLowerCase() === 'negative' ? 'bg-red-500' :
                          'bg-gray-400'
                        }`} />
                        {article.sentiment}
                      </span>
                    )}
                    {article.matched_keywords?.length > 0 && (
                      <span className="text-xs px-2 py-0.5 bg-yellow-50 dark:bg-yellow-900/20 text-yellow-700 dark:text-yellow-400 rounded border border-yellow-200 dark:border-yellow-800">
                        Matched: {article.matched_keywords.join(', ')}
                      </span>
                    )}
                    {article.entity_match?.verified && (
                      <span
                        title={`Opoint entity match (Wikidata)${article.entity_match.relevance != null ? ` · relevance ${article.entity_match.relevance}` : ''}`}
                        className="text-xs px-2 py-0.5 bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-400 rounded border border-blue-200 dark:border-blue-800 inline-flex items-center gap-1"
                      >
                        <Sparkles className="w-3 h-3" /> Entity-verified{article.entity_match.relevance != null ? ` ${article.entity_match.relevance.toFixed(2)}` : ''}
                      </span>
                    )}
                    {factualityChip(article.factual_reporting)}
                    {(article.risks || []).map((r: any) => (
                      <span key={r.risk_type}
                        title={`Adverse risk: ${r.risk_type} (${r.severity})`}
                        className={`text-[10px] px-1.5 py-0.5 rounded-full font-semibold ${
                          r.severity === 'high' ? 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300'
                          : r.severity === 'medium' ? 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300'
                          : 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300'}`}>
                        ⚠ {r.risk_type.replace(/_/g, '/')}
                      </span>
                    ))}
                    {(article.story_size || 1) >= 2 && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300 font-semibold"
                        title={`Republished by ${article.story_size} sources`}>×{article.story_size}</span>
                    )}
                    {isNegConsensus(article) && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded-full font-semibold bg-red-600 text-white"
                        title={`${article.story_neg} of ${article.story_scored} sources frame this negatively`}>⚠ negative consensus</span>
                    )}
                    {!isNegConsensus(article) && isPolarized(article) && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded-full font-semibold bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300"
                        title={`Coverage split: ${article.story_pos} positive vs ${article.story_neg} negative`}>⚡ polarized</span>
                    )}
                    {article.news_source && (
                      <span className="text-xs text-gray-400">{article.news_source}</span>
                    )}
                    {article.publication_date && (
                      <span className="text-xs text-gray-400">{article.publication_date.slice(0, 10)}</span>
                    )}
                    <span className="flex-1" />
                    {reviewStatusOf(article) !== 'new' && (
                      <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${
                        reviewStatusOf(article) === 'escalated' ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300'
                        : 'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400'}`}>{reviewStatusOf(article)}</span>
                    )}
                    <select value="" onClick={e => e.stopPropagation()}
                      onChange={e => { const v = e.target.value as any; if (v) setReview(article.uri, article.brand_id, v); e.currentTarget.value = ''; }}
                      title="Case state" className="text-[10px] px-1 py-0.5 rounded border border-gray-200 dark:border-gray-600 bg-transparent text-gray-400 hover:text-gray-600 cursor-pointer">
                      <option value="">act…</option>
                      <option value="reviewed">Mark reviewed</option>
                      <option value="escalated">Escalate</option>
                      <option value="dismissed">Dismiss</option>
                    </select>
                  </div>
                </div>
              ))}

              {/* Pagination (hidden during export) */}
              {!exportingReport && totalPages > 1 && (
                <div className="flex justify-center gap-2 pt-4">
                  <button disabled={config.page <= 1}
                    onClick={() => updateConfig({ page: config.page - 1 })}
                    className="px-3 py-1 text-sm bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded disabled:opacity-50">
                    Previous
                  </button>
                  <span className="px-3 py-1 text-sm text-gray-600 dark:text-gray-400">
                    {config.page} / {totalPages}
                  </span>
                  <button disabled={config.page >= totalPages}
                    onClick={() => updateConfig({ page: config.page + 1 })}
                    className="px-3 py-1 text-sm bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded disabled:opacity-50">
                    Next
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      </div>{/* end brand-watcher-export */}

      {/* ---- BRAND CONFIG MODAL ---- */}
      {showAlertSettings && (
        <div className="fixed inset-0 z-[1100] flex items-center justify-center">
          <div className="absolute inset-0 bg-black/50" onClick={() => setShowAlertSettings(false)} />
          <div className="relative bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-lg max-h-[85vh] overflow-hidden flex flex-col">
            <div className="flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-700">
              <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100 flex items-center gap-2"><Bell className="w-5 h-5 text-purple-500" /> Adverse-media alerting</h3>
              <button onClick={() => setShowAlertSettings(false)} className="text-gray-500 hover:text-gray-600"><X className="w-5 h-5" /></button>
            </div>
            {!alertCfg ? (
              <div className="p-8 text-center"><Loader2 className="w-5 h-5 animate-spin inline text-gray-400" /></div>
            ) : (
              <div className="p-4 overflow-y-auto space-y-4">
                <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-200">
                  <input type="checkbox" checked={alertCfg.enabled} onChange={e => setAlertCfg({ ...alertCfg, enabled: e.target.checked })} />
                  Alerting enabled <span className="text-xs text-gray-400">(rules run server-side every ~15 min)</span>
                </label>
                <div>
                  <label className="text-xs font-semibold text-gray-700 dark:text-gray-200 uppercase tracking-wide mb-1.5 block">Channels</label>
                  <div className="flex gap-3">
                    {(['in_app', 'email', 'webhook'] as const).map(ch => (
                      <label key={ch} className="flex items-center gap-1.5 text-sm text-gray-700 dark:text-gray-200">
                        <input type="checkbox" checked={!!alertCfg.channels?.[ch]}
                          onChange={e => setAlertCfg({ ...alertCfg, channels: { ...alertCfg.channels, [ch]: e.target.checked } })} />
                        {ch === 'in_app' ? 'In-app' : ch === 'email' ? 'Email' : 'Webhook'}
                      </label>
                    ))}
                  </div>
                </div>
                <div className="flex items-center gap-2 flex-wrap">
                  <label className="flex items-center gap-1.5 text-sm text-gray-700 dark:text-gray-200">
                    <input type="checkbox" checked={!!alertCfg.channels?.digest?.enabled}
                      onChange={e => setAlertCfg({ ...alertCfg, channels: { ...alertCfg.channels, digest: { ...(alertCfg.channels?.digest || {}), enabled: e.target.checked } } })} />
                    Digest email
                  </label>
                  <select value={alertCfg.channels?.digest?.frequency || 'daily'}
                    onChange={e => setAlertCfg({ ...alertCfg, channels: { ...alertCfg.channels, digest: { ...(alertCfg.channels?.digest || {}), frequency: e.target.value as any } } })}
                    className="text-xs px-2 py-1 rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200">
                    <option value="daily">daily</option>
                    <option value="weekly">weekly (Mondays)</option>
                  </select>
                  <span className="text-xs text-gray-400">at</span>
                  <select value={alertCfg.channels?.digest?.hour_utc ?? 6}
                    onChange={e => setAlertCfg({ ...alertCfg, channels: { ...alertCfg.channels, digest: { ...(alertCfg.channels?.digest || {}), hour_utc: Number(e.target.value) } } })}
                    className="text-xs px-2 py-1 rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200">
                    {Array.from({ length: 24 }, (_, h) => <option key={h} value={h}>{String(h).padStart(2, '0')}:00 UTC</option>)}
                  </select>
                  <span className="text-xs text-gray-400">— sentiment, findings, alerts &amp; case actions to the recipients below</span>
                </div>
                <div>
                  <label className="text-xs font-semibold text-gray-700 dark:text-gray-200 uppercase tracking-wide mb-1.5 block">Email recipients <span className="normal-case font-normal text-gray-400">(comma-separated)</span></label>
                  <input type="text" value={alertRecipientsText} onChange={e => setAlertRecipientsText(e.target.value)}
                    placeholder="alerts@example.com, ceo@example.com"
                    className="w-full text-sm px-2 py-1.5 rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200" />
                </div>
                <div>
                  <label className="text-xs font-semibold text-gray-700 dark:text-gray-200 uppercase tracking-wide mb-1.5 block">Webhook URL <span className="normal-case font-normal text-gray-400">(Slack incoming-webhook compatible)</span></label>
                  <input type="text" value={alertCfg.webhook_url || ''} onChange={e => setAlertCfg({ ...alertCfg, webhook_url: e.target.value })}
                    placeholder="https://hooks.slack.com/services/…"
                    className="w-full text-sm px-2 py-1.5 rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200" />
                </div>
                <div className="flex items-center gap-2">
                  <label className="text-xs font-semibold text-gray-700 dark:text-gray-200 uppercase tracking-wide">Cooldown</label>
                  <select value={alertCfg.cooldown_hours} onChange={e => setAlertCfg({ ...alertCfg, cooldown_hours: Number(e.target.value) })}
                    className="text-sm px-2 py-1 rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200">
                    {[6, 12, 24, 48, 72].map(h => <option key={h} value={h}>{h}h</option>)}
                  </select>
                  <span className="text-xs text-gray-400">same rule+brand alerts at most once per window</span>
                </div>
                <div>
                  <label className="text-xs font-semibold text-gray-700 dark:text-gray-200 uppercase tracking-wide mb-1.5 block">Rules &amp; thresholds</label>
                  <div className="space-y-1.5">
                    {BW_ALERT_RULE_DEFS.map(rd => {
                      const rcfg = (alertCfg.rules || {})[rd.key] || {};
                      const enabled = rcfg.enabled !== false;
                      const setRule = (patch: Record<string, any>) =>
                        setAlertCfg({ ...alertCfg, rules: { ...(alertCfg.rules || {}), [rd.key]: { ...rcfg, ...patch } } });
                      return (
                        <div key={rd.key} className={`flex items-center gap-2 flex-wrap text-xs rounded-md px-2 py-1 ${enabled ? '' : 'opacity-50'} bg-gray-50 dark:bg-gray-750`}>
                          <label className="flex items-center gap-1.5 text-gray-700 dark:text-gray-200 w-52 flex-shrink-0">
                            <input type="checkbox" checked={enabled} onChange={e => setRule({ enabled: e.target.checked })} />
                            {rd.label}
                          </label>
                          {rd.params.map(pm => (
                            <label key={pm.k} className="flex items-center gap-1 text-gray-500 dark:text-gray-400">
                              {pm.label}
                              <input type="number" step={pm.step || 1} value={rcfg[pm.k] ?? pm.def}
                                onChange={e => setRule({ [pm.k]: e.target.value === '' ? pm.def : Number(e.target.value) })}
                                className="w-16 text-xs px-1 py-0.5 rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200" />
                            </label>
                          ))}
                        </div>
                      );
                    })}
                  </div>
                  <p className="text-[11px] text-gray-400 mt-1">Values shown are the server defaults until changed; unchecking disables a rule.</p>
                </div>
              </div>
            )}
            <div className="flex items-center justify-between gap-2 p-4 border-t border-gray-200 dark:border-gray-700">
              <button onClick={() => evaluateAlertsNow().then(r => { loadAlertData(); alert(`Evaluation ran — ${r.created} new event(s).`); }).catch(console.error)}
                className="text-xs px-3 py-1.5 rounded-md border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300">Run evaluation now</button>
              <div className="flex gap-2">
                <button onClick={() => setShowAlertSettings(false)} className="text-sm px-3 py-1.5 rounded-md border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300">Cancel</button>
                <button disabled={alertSaving || !alertCfg} onClick={async () => {
                    if (!alertCfg) return;
                    setAlertSaving(true);
                    try {
                      const recipients = alertRecipientsText.split(',').map(x => x.trim()).filter(Boolean);
                      const updated = await updateAlertConfig({ enabled: alertCfg.enabled, rules: alertCfg.rules, channels: alertCfg.channels, email_recipients: recipients, webhook_url: alertCfg.webhook_url, cooldown_hours: alertCfg.cooldown_hours });
                      setAlertCfg(updated); setShowAlertSettings(false);
                    } catch (e) { console.error(e); alert('Failed to save alert config'); }
                    finally { setAlertSaving(false); }
                  }}
                  className="text-sm px-4 py-1.5 rounded-md bg-purple-600 text-white hover:bg-purple-700 disabled:opacity-50">
                  {alertSaving ? 'Saving…' : 'Save'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ---- OFFICIAL SOURCES MODAL ---- */}
      {showSourcesModal && (
        <div className="fixed inset-0 z-[1100] flex items-center justify-center">
          <div className="absolute inset-0 bg-black/50" onClick={() => setShowSourcesModal(false)} />
          <div className="relative bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-2xl max-h-[85vh] overflow-hidden flex flex-col">
            <div className="flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-700">
              <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100 flex items-center gap-2">
                <Landmark className="w-5 h-5 text-teal-500" /> Official &amp; scholarly sources
              </h3>
              <button onClick={() => setShowSourcesModal(false)} className="text-gray-500 hover:text-gray-600"><X className="w-5 h-5" /></button>
            </div>
            {!sourcesStatus ? (
              <div className="p-8 text-center"><Loader2 className="w-5 h-5 animate-spin inline text-gray-400" /></div>
            ) : (
              <div className="p-4 overflow-y-auto space-y-5">
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  Structured records fetched directly for each brand — SEC filings, court opinions and regulatory
                  dockets match the company by name even when news coverage doesn't. Enabled sources are polled
                  once a day and land as authoritative articles (adverse findings get risk-screened automatically).
                </p>
                {sourcesStatus.map(b => (
                  <div key={b.brand_id}>
                    <div className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400 mb-1.5">{b.display_name}</div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
                      {b.sources.map(s => (
                        <label key={s.key}
                          className={`flex items-start gap-2 p-2 rounded-md border text-sm ${s.available ? 'cursor-pointer border-gray-200 dark:border-gray-700 hover:border-teal-400' : 'opacity-60 border-dashed border-gray-300 dark:border-gray-600'}`}>
                          <input type="checkbox" className="mt-0.5" checked={s.enabled} disabled={!s.available}
                            onChange={() => toggleBrandSource(b.brand_id, s.key)} />
                          <span className="min-w-0">
                            <span className="font-medium text-gray-800 dark:text-gray-100">{s.label}</span>
                            {s.article_count > 0 && <span className="ml-1.5 text-[11px] text-teal-600 dark:text-teal-300">{s.article_count} landed</span>}
                            <span className="block text-[11px] text-gray-400 leading-snug">
                              {s.description}
                              {!s.available && s.requires_key && <> — needs <code>{s.requires_key}</code> in the server env</>}
                              {s.available && s.last_polled_at && <> · polled {new Date(s.last_polled_at).toLocaleDateString()}</>}
                            </span>
                          </span>
                        </label>
                      ))}
                    </div>
                  </div>
                ))}
                {sourcesPollMsg && <p className="text-xs text-teal-600 dark:text-teal-300">{sourcesPollMsg}</p>}
              </div>
            )}
            <div className="flex items-center justify-between gap-2 p-4 border-t border-gray-200 dark:border-gray-700">
              <button disabled={sourcesPolling || !sourcesStatus} onClick={async () => {
                  setSourcesPolling(true); setSourcesPollMsg(null);
                  try {
                    const r = await pollOfficialSourcesNow();
                    setSourcesPollMsg(`Polled ${r.polled} source(s): ${r.new_articles} new record(s), ${r.risk_flagged} risk-flagged${r.errors ? `, ${r.errors} error(s)` : ''}.`);
                    getOfficialSourcesStatus().then(setSourcesStatus).catch(() => {});
                  } catch (e) { console.error(e); setSourcesPollMsg('Poll failed — see console.'); }
                  finally { setSourcesPolling(false); }
                }}
                className="text-xs px-3 py-1.5 rounded-md border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300 disabled:opacity-50 inline-flex items-center gap-1.5">
                {sourcesPolling && <Loader2 className="w-3 h-3 animate-spin" />} Poll enabled sources now
              </button>
              <div className="flex gap-2">
                <button onClick={() => setShowSourcesModal(false)} className="text-sm px-3 py-1.5 rounded-md border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300">Cancel</button>
                <button disabled={sourcesSaving || !sourcesStatus} onClick={async () => {
                    if (!sourcesStatus) return;
                    setSourcesSaving(true);
                    try {
                      for (const b of sourcesStatus) {
                        await updateBrandConfig(b.brand_id, { extra_sources: b.sources.filter(s => s.enabled).map(s => s.key) });
                      }
                      setShowSourcesModal(false);
                    } catch (e) { console.error(e); alert('Failed to save source settings'); }
                    finally { setSourcesSaving(false); }
                  }}
                  className="text-sm px-4 py-1.5 rounded-md bg-teal-600 text-white hover:bg-teal-700 disabled:opacity-50">
                  {sourcesSaving ? 'Saving…' : 'Save'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {showSocialExport && (
        <div className="fixed inset-0 z-[1100] flex items-center justify-center">
          <div className="absolute inset-0 bg-black/50" onClick={() => setShowSocialExport(false)} />
          <div className="relative bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-lg max-h-[85vh] overflow-hidden flex flex-col">
            <div className="flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-700">
              <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100 flex items-center gap-2">
                <FileDown className="w-5 h-5 text-blue-500" /> Export social posts (CSV)
              </h3>
              <button onClick={() => setShowSocialExport(false)} className="text-gray-500 hover:text-gray-600">
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="p-4 overflow-y-auto space-y-5">
              {/* Brands */}
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <label className="text-xs font-semibold text-gray-700 dark:text-gray-200 uppercase tracking-wide">Brands</label>
                  <div className="flex gap-2 text-[11px]">
                    <button className="text-blue-600 hover:underline" onClick={() => setExpBrands(brands.map(b => b.id))}>All</button>
                    <button className="text-blue-600 hover:underline" onClick={() => setExpBrands([])}>None</button>
                  </div>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {[...brands].sort((a, b) => (b.is_primary ? 1 : 0) - (a.is_primary ? 1 : 0) || a.display_name.localeCompare(b.display_name)).map(b => {
                    const on = expBrands.includes(b.id);
                    return (
                      <button key={b.id}
                        onClick={() => setExpBrands(on ? expBrands.filter(x => x !== b.id) : [...expBrands, b.id])}
                        style={on ? { backgroundColor: b.color || '#2563eb', borderColor: b.color || '#2563eb' } : { borderColor: b.color || undefined }}
                        className={`text-xs px-2.5 py-1 rounded-full border ${on ? 'text-white' : 'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200'}`}>
                        {b.display_name}{b.is_primary ? ' ★' : ''}
                      </button>
                    );
                  })}
                </div>
              </div>
              {/* Sentiments */}
              <div>
                <label className="text-xs font-semibold text-gray-700 dark:text-gray-200 uppercase tracking-wide mb-1.5 block">Sentiment <span className="normal-case text-gray-400 font-normal">(none = all)</span></label>
                <div className="flex flex-wrap gap-1.5">
                  {['positive', 'neutral', 'negative', 'unrated'].map(s => {
                    const on = expSentiments.includes(s);
                    return (
                      <button key={s}
                        onClick={() => setExpSentiments(on ? expSentiments.filter(x => x !== s) : [...expSentiments, s])}
                        className={`text-xs px-2.5 py-1 rounded-full border capitalize ${on ? 'bg-blue-600 text-white border-blue-600' : 'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200 border-gray-300 dark:border-gray-600'}`}>
                        {s}
                      </button>
                    );
                  })}
                </div>
              </div>
              {/* Date range */}
              <div>
                <label className="text-xs font-semibold text-gray-700 dark:text-gray-200 uppercase tracking-wide mb-1.5 block">Date range</label>
                <div className="flex items-center gap-2">
                  <input type="date" value={expStart} max={expEnd || undefined} onChange={e => setExpStart(e.target.value)}
                    className="text-sm px-2 py-1 rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200" />
                  <span className="text-gray-400 text-sm">to</span>
                  <input type="date" value={expEnd} min={expStart || undefined} onChange={e => setExpEnd(e.target.value)}
                    className="text-sm px-2 py-1 rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200" />
                </div>
                <div className="flex gap-2 mt-1.5 text-[11px]">
                  {[7, 30, 90, 180, 365].map(d => (
                    <button key={d} className="text-blue-600 hover:underline" onClick={() => {
                      const end = new Date(); const start = new Date(); start.setDate(end.getDate() - d);
                      setExpStart(start.toISOString().slice(0, 10)); setExpEnd(end.toISOString().slice(0, 10));
                    }}>{d < 365 ? `${d}d` : '1y'}</button>
                  ))}
                </div>
              </div>
              {/* Relevance */}
              <div>
                <label className="text-xs font-semibold text-gray-700 dark:text-gray-200 uppercase tracking-wide mb-1.5 block">Include</label>
                <select value={expRelevance} onChange={e => setExpRelevance(e.target.value as 'onbrand' | 'scored' | 'all')}
                  className="w-full text-sm px-2 py-1.5 rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200">
                  <option value="onbrand">On-brand only (relevance ≥ 0.4)</option>
                  <option value="scored">All scored posts (incl. off-topic)</option>
                  <option value="all">Everything (incl. not-yet-evaluated)</option>
                </select>
              </div>
              <p className="text-[11px] text-gray-400">Fetches the full matching set (not the on-screen sample). CSV is ordered by brand (primary first), then sentiment, then newest.</p>
            </div>
            <div className="flex items-center justify-end gap-2 p-4 border-t border-gray-200 dark:border-gray-700">
              <button onClick={() => setShowSocialExport(false)} className="text-sm px-3 py-1.5 rounded-md border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300">Cancel</button>
              <button onClick={runSocialExport} disabled={exportingSocial || expBrands.length === 0}
                className="text-sm px-4 py-1.5 rounded-md bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 inline-flex items-center gap-1.5">
                <FileDown className="w-4 h-4" /> {exportingSocial ? 'Exporting…' : 'Download CSV'}
              </button>
            </div>
          </div>
        </div>
      )}

      {showBrandConfig && (
        <div className="fixed inset-0 z-[1100] flex items-center justify-center">
          <div className="absolute inset-0 bg-black/50" onClick={() => { setShowBrandConfig(false); resetBrandForm(); }} />
          <div className="relative bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-2xl max-h-[85vh] overflow-hidden">
            <div className="flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-700">
              <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100">Brand Configuration</h3>
              <button onClick={() => { setShowBrandConfig(false); resetBrandForm(); }} className="text-gray-500 hover:text-gray-600">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-4 overflow-y-auto max-h-[65vh] space-y-6">
              {/* Monitoring status banner */}
              {monitoringStatus && (
                <div className={`flex items-start gap-2 p-3 rounded-lg text-sm ${
                  monitoringStatus.type === 'success'
                    ? 'bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-300 border border-green-200 dark:border-green-800'
                    : 'bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300 border border-red-200 dark:border-red-800'
                }`}>
                  <span className="flex-1">{monitoringStatus.message}</span>
                  <button onClick={() => setMonitoringStatus(null)} className="flex-shrink-0 opacity-60 hover:opacity-100">
                    <X className="w-4 h-4" />
                  </button>
                </div>
              )}

              {/* Existing brands */}
              <div>
                <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">Tracked Brands</h4>
                {brands.length === 0 ? (
                  <p className="text-sm text-gray-500 dark:text-gray-400">No brands configured. Add one below.</p>
                ) : (
                  <div className="space-y-2">
                    {brands.map(brand => (
                      <div key={brand.id} className="flex items-center gap-3 p-3 bg-gray-50 dark:bg-gray-750 rounded-lg">
                        {brand.color && <div className="w-3 h-3 rounded-full" style={{ backgroundColor: brand.color }} />}
                        <div className="flex-1">
                          <p className="text-sm font-medium text-gray-900 dark:text-gray-100">{brand.display_name}</p>
                          <p className="text-xs text-gray-500 dark:text-gray-400">
                            {(brand.brand_keywords || []).join(', ')}
                          </p>
                        </div>
                        <button onClick={() => setPrimary(brand.id)}
                          title={brand.is_primary ? 'Primary brand' : 'Set as primary brand for Analysis & Insights'}
                          className="text-gray-400 hover:text-yellow-500 transition-colors">
                          <Star className={`w-4 h-4 ${brand.is_primary ? 'fill-yellow-400 text-yellow-400' : ''}`} />
                        </button>
                        <button onClick={() => toggleBrandFn(brand.id)} title={brand.enabled ? 'Disable' : 'Enable'}
                          className="text-gray-400 hover:text-gray-600">
                          {brand.enabled ? <ToggleRight className="w-5 h-5 text-green-500" /> : <ToggleLeft className="w-5 h-5" />}
                        </button>
                        <button onClick={() => startEditBrand(brand)} className="text-gray-400 hover:text-blue-500">
                          <Edit2 className="w-4 h-4" />
                        </button>
                        <button onClick={() => { if (confirm('Delete this brand and its monitoring topic/keywords?')) deleteBrandFn(brand.id, true); }}
                          className="text-gray-400 hover:text-red-500">
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Add/Edit brand form */}
              <div className="border-t border-gray-200 dark:border-gray-700 pt-4">
                <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">
                  {editingBrandId ? 'Edit Brand' : 'Add New Brand'}
                </h4>
                <div className="space-y-3">
                  <div>
                    <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Display Name *</label>
                    <input type="text" value={brandForm.display_name || ''}
                      onChange={e => setBrandForm({ ...brandForm, display_name: e.target.value })}
                      placeholder="e.g. Apple Inc"
                      className="w-full px-3 py-2 text-sm border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 dark:text-gray-100" />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Description</label>
                    <input type="text" value={brandForm.description || ''}
                      onChange={e => setBrandForm({ ...brandForm, description: e.target.value })}
                      placeholder="Brief description"
                      className="w-full px-3 py-2 text-sm border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 dark:text-gray-100" />
                  </div>
                  <div className="flex items-end gap-3">
                    <div>
                      <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Color (hex)</label>
                      <input type="text" value={brandForm.color || ''}
                        onChange={e => setBrandForm({ ...brandForm, color: e.target.value })}
                        placeholder="#2563eb"
                        className="w-32 px-3 py-2 text-sm border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 dark:text-gray-100" />
                    </div>
                    <button onClick={handleSuggestKeywords}
                      disabled={!brandForm.display_name?.trim() || suggestingKeywords}
                      className="px-3 py-2 text-sm bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50 flex items-center gap-1.5 whitespace-nowrap">
                      {suggestingKeywords ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
                      {suggestingKeywords ? 'Suggesting...' : 'Suggest Keywords'}
                    </button>
                  </div>
                  <KeywordTagInput label="Brand Keywords" keywords={(brandForm.brand_keywords as string[]) || []}
                    inputValue={brandKeywordInput} setInputValue={setBrandKeywordInput}
                    onAdd={(v) => addKeyword('brand_keywords', v)} onRemove={(v) => removeKeyword('brand_keywords', v)} />
                  <KeywordTagInput label="Product Keywords" keywords={(brandForm.product_keywords as string[]) || []}
                    inputValue={productKeywordInput} setInputValue={setProductKeywordInput}
                    onAdd={(v) => addKeyword('product_keywords', v)} onRemove={(v) => removeKeyword('product_keywords', v)} />
                  <KeywordTagInput label="People Keywords" keywords={(brandForm.people_keywords as string[]) || []}
                    inputValue={peopleKeywordInput} setInputValue={setPeopleKeywordInput}
                    onAdd={(v) => addKeyword('people_keywords', v)} onRemove={(v) => removeKeyword('people_keywords', v)} />
                  <KeywordTagInput label="Competitor Keywords" keywords={(brandForm.competitor_keywords as string[]) || []}
                    inputValue={competitorKeywordInput} setInputValue={setCompetitorKeywordInput}
                    onAdd={(v) => addKeyword('competitor_keywords', v)} onRemove={(v) => removeKeyword('competitor_keywords', v)} />

                  <label className="flex items-start gap-2 p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg cursor-pointer">
                    <input type="checkbox" checked={setupMonitoring}
                      onChange={e => setSetupMonitoring(e.target.checked)}
                      className="mt-0.5 rounded" />
                    <div>
                      <span className="text-sm font-medium text-gray-700 dark:text-gray-200">
                        {editingBrandId ? 'Update monitoring topic & keyword group' : 'Create monitoring topic & keyword group'}
                      </span>
                      <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                        {editingBrandId
                          ? `Updates "Brand Monitoring ${brandForm.display_name || '...'}" topic and refreshes keyword group`
                          : `Creates "Brand Monitoring ${brandForm.display_name || '...'}" topic and keyword group for automatic article collection`
                        }
                      </p>
                    </div>
                  </label>

                  <div className="flex gap-2">
                    <button onClick={handleSaveBrand}
                      disabled={!brandForm.display_name?.trim()}
                      className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50">
                      {editingBrandId ? 'Update Brand' : 'Add Brand'}
                    </button>
                    {editingBrandId && (
                      <button onClick={resetBrandForm}
                        className="px-4 py-2 text-sm bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-200">
                        Cancel
                      </button>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ---- CLASSIFY MODAL ---- */}
      {showClassifyModal && (
        <div className="fixed inset-0 z-[1100] flex items-center justify-center">
          <div className="absolute inset-0 bg-black/50" onClick={() => setShowClassifyModal(false)} />
          <div className="relative bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-lg max-h-[85vh] overflow-hidden">
            <div className="flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-700">
              <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100">Classify Articles</h3>
              <button onClick={() => { setShowClassifyModal(false); setClassifyStatus(''); }}
                className="text-gray-500 hover:text-gray-600"><X className="w-5 h-5" /></button>
            </div>

            <div className="p-4 overflow-y-auto max-h-[70vh] space-y-5">
              <p className="text-sm text-gray-500 dark:text-gray-400">
                Run classification on articles matching your brand keywords.
                {primarySelectedId ? ` Targeting: ${selectedBrand?.display_name}` : ' Targeting: All brands'}
                {config.selectedTopics.length > 0 && ` | ${config.selectedTopics.length} topic${config.selectedTopics.length !== 1 ? 's' : ''} selected`}
              </p>

              {/* Topic multi-select */}
              <div>
                <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">
                  Topics to classify ({config.selectedTopics.length} selected)
                </label>
                <div className="max-h-40 overflow-y-auto border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 p-2 space-y-1">
                  {topics.map(t => (
                    <label key={t.topic} className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-750 rounded px-1 py-0.5 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={config.selectedTopics.includes(t.topic)}
                        onChange={e => {
                          const next = e.target.checked
                            ? [...config.selectedTopics, t.topic]
                            : config.selectedTopics.filter(s => s !== t.topic);
                          updateConfig({ selectedTopics: next });
                        }}
                        className="rounded border-gray-300 dark:border-gray-600"
                      />
                      <span className="flex-1 truncate">{t.topic}</span>
                      <span className="text-xs text-gray-400 flex-shrink-0">{t.article_count}</span>
                    </label>
                  ))}
                  {topics.length === 0 && (
                    <p className="text-xs text-gray-400 dark:text-gray-500 italic">No topics available</p>
                  )}
                </div>
                {config.selectedTopics.length > 0 && (
                  <button
                    onClick={() => updateConfig({ selectedTopics: [] })}
                    className="mt-1 text-xs text-blue-500 hover:text-blue-700"
                  >
                    Clear all
                  </button>
                )}
              </div>

              {/* Run now section */}
              <div>
                <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3 flex items-center gap-2">
                  <Zap className="w-4 h-4" /> Run Now
                </h4>
                <div className="space-y-2">
                  <button onClick={() => handleClassify('incremental_since_last', 0)}
                    className="w-full px-4 py-2.5 text-sm bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 flex items-center justify-center gap-2">
                    <Clock className="w-4 h-4" /> Incremental Since Last Update
                  </button>
                  <button onClick={() => handleClassify('incremental', 30)}
                    className="w-full px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700">
                    Incremental (last 30 days)
                  </button>
                  <button onClick={() => handleClassify('incremental', 90)}
                    className="w-full px-4 py-2 text-sm bg-blue-500 text-white rounded-lg hover:bg-blue-600">
                    Incremental (last 90 days)
                  </button>
                  <button onClick={() => handleClassify('full', 365)}
                    className="w-full px-4 py-2 text-sm bg-orange-500 text-white rounded-lg hover:bg-orange-600">
                    Full Reclassify (last year)
                  </button>
                </div>
              </div>

              {classifyStatus && (
                <div className="p-3 bg-gray-50 dark:bg-gray-750 rounded-lg text-sm text-gray-600 dark:text-gray-300 flex items-center gap-2">
                  {classifyStatus.includes('running') && <Loader2 className="w-4 h-4 animate-spin flex-shrink-0" />}
                  {classifyStatus}
                </div>
              )}

              {/* Scheduling section */}
              <div className="border-t border-gray-200 dark:border-gray-700 pt-4">
                <div className="flex items-center justify-between mb-3">
                  <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 flex items-center gap-2">
                    <Calendar className="w-4 h-4" /> Schedules
                  </h4>
                  <button onClick={() => { setShowScheduleForm(!showScheduleForm); if (!schedules.length) fetchSchedules(); }}
                    className="text-xs px-2 py-1 bg-blue-50 dark:bg-blue-900/20 text-blue-600 dark:text-blue-400 rounded hover:bg-blue-100">
                    {showScheduleForm ? 'Cancel' : '+ New Schedule'}
                  </button>
                </div>

                {/* Schedule creation form */}
                {showScheduleForm && (
                  <div className="p-3 bg-gray-50 dark:bg-gray-750 rounded-lg space-y-3 mb-3">
                    <div>
                      <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">Schedule Name</label>
                      <input type="text" value={scheduleForm.name}
                        onChange={e => setScheduleForm(prev => ({ ...prev, name: e.target.value }))}
                        placeholder={`${selectedBrand?.display_name || 'All brands'} daily`}
                        className="w-full px-2 py-1.5 text-sm border border-gray-200 dark:border-gray-700 rounded bg-white dark:bg-gray-800 dark:text-gray-100" />
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">Run Type</label>
                        <select value={scheduleForm.run_type}
                          onChange={e => setScheduleForm(prev => ({ ...prev, run_type: e.target.value }))}
                          className="w-full px-2 py-1.5 text-sm border border-gray-200 dark:border-gray-700 rounded bg-white dark:bg-gray-800 dark:text-gray-100">
                          <option value="incremental">Incremental</option>
                          <option value="incremental_since_last">Since last update</option>
                          <option value="full">Full reclassify</option>
                        </select>
                      </div>
                      <div>
                        <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">Days Back</label>
                        <select value={scheduleForm.days_back}
                          onChange={e => setScheduleForm(prev => ({ ...prev, days_back: Number(e.target.value) }))}
                          className="w-full px-2 py-1.5 text-sm border border-gray-200 dark:border-gray-700 rounded bg-white dark:bg-gray-800 dark:text-gray-100">
                          <option value={7}>7 days</option>
                          <option value={30}>30 days</option>
                          <option value={90}>90 days</option>
                          <option value={365}>1 year</option>
                        </select>
                      </div>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">Frequency</label>
                        <select value={scheduleForm.schedule_type}
                          onChange={e => setScheduleForm(prev => ({ ...prev, schedule_type: e.target.value }))}
                          className="w-full px-2 py-1.5 text-sm border border-gray-200 dark:border-gray-700 rounded bg-white dark:bg-gray-800 dark:text-gray-100">
                          <option value="interval">Every X hours</option>
                          <option value="daily">Daily at time</option>
                        </select>
                      </div>
                      {scheduleForm.schedule_type === 'interval' ? (
                        <div>
                          <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">Every (hours)</label>
                          <input type="number" min={1} max={168} value={scheduleForm.schedule_interval}
                            onChange={e => setScheduleForm(prev => ({ ...prev, schedule_interval: Number(e.target.value) }))}
                            className="w-full px-2 py-1.5 text-sm border border-gray-200 dark:border-gray-700 rounded bg-white dark:bg-gray-800 dark:text-gray-100" />
                        </div>
                      ) : (
                        <div>
                          <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">Time (HH:MM)</label>
                          <input type="time" value={scheduleForm.schedule_time}
                            onChange={e => setScheduleForm(prev => ({ ...prev, schedule_time: e.target.value }))}
                            className="w-full px-2 py-1.5 text-sm border border-gray-200 dark:border-gray-700 rounded bg-white dark:bg-gray-800 dark:text-gray-100" />
                        </div>
                      )}
                    </div>
                    {/* Topic selector for schedule */}
                    <div>
                      <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">
                        Topics ({scheduleTopics.length} selected)
                      </label>
                      <div className="max-h-32 overflow-y-auto border border-gray-200 dark:border-gray-700 rounded bg-white dark:bg-gray-800 p-1.5 space-y-0.5">
                        {topics.map(t => (
                          <label key={t.topic} className="flex items-center gap-2 text-xs text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-750 rounded px-1 py-0.5 cursor-pointer">
                            <input
                              type="checkbox"
                              checked={scheduleTopics.includes(t.topic)}
                              onChange={e => {
                                setScheduleTopics(prev =>
                                  e.target.checked ? [...prev, t.topic] : prev.filter(s => s !== t.topic)
                                );
                              }}
                              className="rounded border-gray-300 dark:border-gray-600"
                            />
                            <span className="flex-1 truncate">{t.topic}</span>
                            <span className="text-[10px] text-gray-400">{t.article_count}</span>
                          </label>
                        ))}
                        {topics.length === 0 && (
                          <p className="text-xs text-gray-400 italic">No topics available</p>
                        )}
                      </div>
                    </div>
                    <button onClick={handleCreateSchedule}
                      className="w-full px-3 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700">
                      Create Schedule
                    </button>
                  </div>
                )}

                {/* Existing schedules */}
                {!showScheduleForm && !loadingSchedules && schedules.length === 0 && (
                  <p className="text-xs text-gray-400 dark:text-gray-500">No schedules configured. Click "+ New Schedule" to set one up.</p>
                )}
                {loadingSchedules && (
                  <div className="flex justify-center py-4"><Loader2 className="w-4 h-4 animate-spin text-blue-500" /></div>
                )}
                {schedules.length > 0 && (
                  <div className="space-y-2">
                    {schedules.map(sched => (
                      <div key={sched.id} className="flex items-center gap-2 p-2.5 bg-gray-50 dark:bg-gray-750 rounded-lg">
                        <div className={`w-2 h-2 rounded-full flex-shrink-0 ${sched.schedule_enabled ? 'bg-green-500' : 'bg-gray-400'}`} />
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium text-gray-700 dark:text-gray-300 truncate">{sched.name}</p>
                          <p className="text-xs text-gray-500 dark:text-gray-400">
                            {sched.schedule_type === 'daily' ? `Daily at ${sched.schedule_time || '02:00'}` : `Every ${sched.schedule_interval}h`}
                            {sched.brand_name ? ` · ${sched.brand_name}` : ' · All brands'}
                            {sched.last_run_at ? ` · Last: ${new Date(sched.last_run_at).toLocaleDateString()}` : ''}
                          </p>
                        </div>
                        <button onClick={() => handleRunScheduleNow(sched.id)} title="Run now"
                          className="p-1 text-blue-500 hover:text-blue-700"><Play className="w-3.5 h-3.5" /></button>
                        <button onClick={() => { if (confirm('Delete this schedule?')) handleDeleteSchedule(sched.id); }} title="Delete"
                          className="p-1 text-gray-400 hover:text-red-500"><Trash2 className="w-3.5 h-3.5" /></button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// Export buttons for the narrative report card
function NarrativeExportButtons({ narrative, brandName }: { narrative: BWSavedNarrative; brandName: string }) {
  const [copied, setCopied] = useState(false);
  const [showMenu, setShowMenu] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  // Close menu on outside click
  useEffect(() => {
    if (!showMenu) return;
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setShowMenu(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [showMenu]);

  const slug = brandName.toLowerCase().replace(/\s+/g, '-');
  const dateStr = narrative.generated_at ? new Date(narrative.generated_at).toISOString().slice(0, 10) : 'report';
  const filename = `brand-report-${slug}-${dateStr}`;

  const handleCopyMarkdown = async () => {
    try {
      await navigator.clipboard.writeText(narrative.narrative);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch { /* fallback */ }
    setShowMenu(false);
  };

  const handleDownloadMarkdown = () => {
    const header = `# Brand Intelligence Report — ${brandName}\n_Generated: ${narrative.generated_at ? new Date(narrative.generated_at).toLocaleString() : 'N/A'}_\n\n`;
    const blob = new Blob([header + narrative.narrative], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = `${filename}.md`; a.click();
    URL.revokeObjectURL(url);
    setShowMenu(false);
  };

  const handleDownloadHTML = () => {
    const html = `<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Brand Intelligence Report — ${brandName}</title>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 800px; margin: 2rem auto; padding: 0 1rem; color: #1f2937; line-height: 1.6; }
  h1 { font-size: 1.5rem; border-bottom: 2px solid #3b82f6; padding-bottom: 0.5rem; }
  h2 { font-size: 1.15rem; margin-top: 1.5rem; }
  a { color: #2563eb; }
  li { margin-left: 1.5rem; list-style-type: disc; }
  .meta { color: #6b7280; font-size: 0.85rem; }
</style></head><body>
<h1>Brand Intelligence Report — ${brandName}</h1>
<p class="meta">Generated: ${narrative.generated_at ? new Date(narrative.generated_at).toLocaleString() : 'N/A'}</p>
${markdownToHtml(narrative.narrative)}
</body></html>`;
    const blob = new Blob([html], { type: 'text/html;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = `${filename}.html`; a.click();
    URL.revokeObjectURL(url);
    setShowMenu(false);
  };

  const handlePrint = () => {
    const el = document.getElementById('narrative-report-card');
    if (!el) return;
    const win = window.open('', '_blank');
    if (!win) return;
    win.document.write(`<!DOCTYPE html><html><head><meta charset="utf-8"><title>Brand Intelligence Report — ${brandName}</title>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 800px; margin: 2rem auto; padding: 0 1rem; color: #1f2937; line-height: 1.6; }
  h2 { font-size: 1.15rem; margin-top: 1.5rem; }
  h3 { font-size: 1rem; }
  a { color: #2563eb; }
  li { margin-left: 1.5rem; list-style-type: disc; }
  @media print { body { margin: 0; } }
</style></head><body>${el.innerHTML}</body></html>`);
    win.document.close();
    win.print();
    setShowMenu(false);
  };

  return (
    <div className="relative" ref={menuRef}>
      <button
        onClick={() => setShowMenu(!showMenu)}
        className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs text-gray-600 dark:text-gray-400 bg-gray-100 dark:bg-gray-700 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
        title="Export report"
      >
        {copied ? <Check className="w-3.5 h-3.5 text-green-500" /> : <Download className="w-3.5 h-3.5" />}
        {copied ? 'Copied' : 'Export'}
      </button>
      {showMenu && (
        <div className="absolute right-0 top-full mt-1 w-48 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg z-50 py-1">
          <button onClick={handleCopyMarkdown} className="flex items-center gap-2 w-full px-3 py-2 text-xs text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700">
            <Copy className="w-3.5 h-3.5" /> Copy as Markdown
          </button>
          <button onClick={handleDownloadMarkdown} className="flex items-center gap-2 w-full px-3 py-2 text-xs text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700">
            <FileDown className="w-3.5 h-3.5" /> Download .md
          </button>
          <button onClick={handleDownloadHTML} className="flex items-center gap-2 w-full px-3 py-2 text-xs text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700">
            <FileText className="w-3.5 h-3.5" /> Download .html
          </button>
          <button onClick={handlePrint} className="flex items-center gap-2 w-full px-3 py-2 text-xs text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700">
            <Printer className="w-3.5 h-3.5" /> Print / Save as PDF
          </button>
        </div>
      )}
    </div>
  );
}

// Simple markdown to HTML converter for narratives
function markdownToHtml(md: string): string {
  if (!md) return '';
  return md
    .replace(/^## (.+)$/gm, '<h2 class="text-lg font-semibold mt-6 mb-2">$1</h2>')
    .replace(/^### (.+)$/gm, '<h3 class="text-base font-semibold mt-4 mb-2">$1</h3>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer" class="text-blue-600 dark:text-blue-400 underline hover:text-blue-800 dark:hover:text-blue-300">$1</a>')
    .replace(/^- (.+)$/gm, '<li class="ml-4 list-disc">$1</li>')
    .replace(/\n\n/g, '</p><p class="mt-2">')
    .replace(/\n/g, '<br />');
}
