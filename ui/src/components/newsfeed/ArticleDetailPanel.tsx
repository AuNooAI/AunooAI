/**
 * Article Detail Panel - Slide-in panel for full article details
 * Shows rich metadata, summary, and action buttons
 * Supports related articles tab for clustered articles
 */

import { useState, useRef, useEffect } from 'react';
import { X, ExternalLink, Star, StarOff, MessageSquare, Clock, TrendingUp, Building2, Layers, ChevronRight, MoreVertical, ThumbsUp, ThumbsDown, Share, Copy, Mail, Bot, Loader2, AlertTriangle, Newspaper, BadgeCheck } from 'lucide-react';
import { type NewsArticle, type ClusterRelatedArticle, recordArticlePreference } from '../../services/newsFeedApi';
import { getSignalsDetail, runSignals, type BWArticleSignals } from '../../services/brandWatcherApi';
import { downloadPropagationReport } from '../../services/propagationReportHtml';
import { ArticleBiasIndicator } from './ArticleBiasIndicator';
import { Button } from '../ui/button';
import { openAuspexWithQuery } from '../../utils/auspexEvents';
import { ShareModal, type ShareArticleData } from '../ShareModal';
import { PromoteToIncidentModal } from './PromoteToIncidentModal';
import { AddToBriefingModal } from './AddToBriefingModal';

interface ArticleDetailPanelProps {
  article: NewsArticle | null;
  relatedArticles?: ClusterRelatedArticle[];
  isStarred?: boolean;
  onClose: () => void;
  onStar?: (uri: string) => void;
  onUnstar?: (uri: string) => void;
  onRelatedArticleClick?: (uri: string) => void;
  topic?: string;
  profileId?: number;
  onIncidentSaved?: () => void;
}

export function ArticleDetailPanel({
  article,
  relatedArticles = [],
  isStarred = false,
  onClose,
  onStar,
  onUnstar,
  onRelatedArticleClick,
  topic,
  profileId,
  onIncidentSaved,
}: ArticleDetailPanelProps) {
  const [activeTab, setActiveTab] = useState<'details' | 'related'>('details');
  const [showMenu, setShowMenu] = useState(false);
  const [preferenceLoading, setPreferenceLoading] = useState(false);
  const [preference, setPreference] = useState<'more' | 'less' | null>(null);
  const [showShareModal, setShowShareModal] = useState(false);
  const [showPromoteModal, setShowPromoteModal] = useState(false);
  const [showAddToBriefingModal, setShowAddToBriefingModal] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const hasRelated = relatedArticles.length > 0;

  // Five Signals screen (Brand Watcher articles carry brand_id; detail rows
  // live in bw_article_signals). Fetched when the article has been screened —
  // or on demand via the Run button — and polled while a run is live.
  const [bwSignals, setBwSignals] = useState<BWArticleSignals | null>(null);
  const [bwSignalsStarting, setBwSignalsStarting] = useState(false);
  const bwSigPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const bwBrandId: number | null = (article as any)?.brand_id ?? null;
  const bwScreenable = !!(bwBrandId && typeof article?.uri === 'string' && article.uri.startsWith('http'));
  const stopBwSigPoll = () => { if (bwSigPollRef.current) { clearInterval(bwSigPollRef.current); bwSigPollRef.current = null; } };
  const pollBwSignals = (uri: string, brandId: number) => {
    stopBwSigPoll();
    bwSigPollRef.current = setInterval(async () => {
      try {
        const d = await getSignalsDetail(uri, brandId);
        setBwSignals(d);
        if (d.status !== 'running') stopBwSigPoll();
      } catch { /* transient; keep polling */ }
    }, 5000);
  };
  useEffect(() => {
    setBwSignals(null); setBwSignalsStarting(false); stopBwSigPoll();
    if (!article?.uri || !bwBrandId) return;
    if (!(article as any)?.signals_summary) return;
    getSignalsDetail(article.uri, bwBrandId).then(d => {
      setBwSignals(d);
      if (d.status === 'running') pollBwSignals(article.uri, bwBrandId);
    }).catch(() => {});
    return stopBwSigPoll;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [article?.uri, bwBrandId]);
  const startBwSignals = async (mode: 'full' | 'validation' | 'reach' = 'full') => {
    if (!article?.uri || !bwBrandId) return;
    setBwSignalsStarting(true);
    try {
      const r = await runSignals(article.uri, bwBrandId, false, mode);
      if (r.status === 'completed') {
        // Already screened (cached server-side) — show it immediately.
        setBwSignals(await getSignalsDetail(article.uri, bwBrandId));
      } else {
        setBwSignals({ status: 'running', signals: null, verdict: null, composite_score: null, validation: null, reach: null, error: null, requested_by: 'user' });
        pollBwSignals(article.uri, bwBrandId);
      }
    } catch (e) {
      console.error('Five Signals run failed to start', e);
      setBwSignals({ status: 'failed', signals: null, verdict: null, composite_score: null, validation: null, reach: null,
        error: 'could not start — the saas integration may not be configured on this server', requested_by: null });
    } finally {
      setBwSignalsStarting(false);
    }
  };
  const BW_SIG_ORDER = ['veracity', 'source_credibility', 'corroboration', 'propagation', 'amplification_integrity'];
  const BW_SIG_BAND: Record<string, string> = {
    good: 'bg-emerald-100 text-emerald-800', warn: 'bg-amber-100 text-amber-800',
    bad: 'bg-red-100 text-red-800', nodata: 'bg-gray-100 text-gray-400',
  };
  const BW_SIG_SHORT: Record<string, string> = {
    veracity: 'V', source_credibility: 'S', corroboration: 'C',
    propagation: 'P', amplification_integrity: 'A',
  };

  // Sentiment bucket for the Full Coverage spread (news labels are richer than pos/neu/neg)
  const sentimentBucket = (s?: string | null): 'positive' | 'neutral' | 'negative' | null => {
    const t = (s || '').toLowerCase();
    if (!t) return null;
    if (t.includes('pos') || t.includes('optimis')) return 'positive';
    if (t.includes('neg') || t.includes('concern') || t.includes('pessimis') || t.includes('critical') || t.includes('alarm')) return 'negative';
    return 'neutral';
  };
  const SENT_CHIP: Record<string, string> = {
    positive: 'bg-emerald-100 text-emerald-700',
    neutral: 'bg-gray-100 text-gray-600',
    negative: 'bg-red-100 text-red-700',
  };
  const factChip = (f?: string | null) => {
    if (!f) return null;
    const t = f.toLowerCase();
    const cls = t.includes('very high') || t === 'high' ? 'bg-emerald-100 text-emerald-700'
      : t.includes('mixed') || t.includes('mostly') ? 'bg-amber-100 text-amber-700'
      : t.includes('low') ? 'bg-red-100 text-red-700' : 'bg-gray-100 text-gray-600';
    return <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${cls}`} title="MBFC factual reporting">{f}</span>;
  };
  // Spread across primary + related (only sources that carry a sentiment)
  const coverageSentiments = [article?.sentiment, ...relatedArticles.map(r => (r as any).sentiment)]
    .map(sentimentBucket).filter(Boolean) as ('positive' | 'neutral' | 'negative')[];
  const spread = {
    positive: coverageSentiments.filter(x => x === 'positive').length,
    neutral: coverageSentiments.filter(x => x === 'neutral').length,
    negative: coverageSentiments.filter(x => x === 'negative').length,
  };

  // Initialize preference from article data when article changes
  useEffect(() => {
    const artPref = article?.user_preference;
    setPreference(artPref === 'more' || artPref === 'less' ? artPref : null);
  }, [article?.uri]);

  // Close menu when clicking outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setShowMenu(false);
      }
    };
    if (showMenu) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [showMenu]);

  const handleMenuAction = async (action: string) => {
    setShowMenu(false);

    if (!article) return;

    if (action === 'more' || action === 'less') {
      try {
        setPreferenceLoading(true);
        const prefAction = action as 'more' | 'less';
        // Toggle: if clicking the same preference, clear it
        if (preference === prefAction) {
          await recordArticlePreference(article.uri, 'clear');
          setPreference(null);
        } else {
          await recordArticlePreference(article.uri, prefAction);
          setPreference(prefAction);
        }
      } catch (err) {
        console.error(`Failed to record preference: ${err}`);
      } finally {
        setPreferenceLoading(false);
      }
    } else if (action === 'copy') {
      // Copy article URL to clipboard
      const url = article.url || article.uri;
      if (url) {
        navigator.clipboard.writeText(url).catch(console.error);
      }
    } else if (action === 'share') {
      // Open share modal for email
      setShowShareModal(true);
    } else if (action === 'promote') {
      // Open promote to incident modal
      setShowPromoteModal(true);
    } else if (action === 'add-to-briefing') {
      // Open add to briefing modal
      setShowAddToBriefingModal(true);
    }
  };

  if (!article) return null;

  const handleStarClick = () => {
    if (isStarred) {
      onUnstar?.(article.uri);
    } else {
      onStar?.(article.uri);
    }
  };

  const handleAskAuspex = () => {
    // Build comprehensive article context
    const sourceName = article.source?.name || 'Unknown source';
    const sourceInfo = [];
    if (article.source?.bias) sourceInfo.push(`Bias: ${article.source.bias}`);
    if (article.source?.factuality) sourceInfo.push(`Factuality: ${article.source.factuality}`);
    if (article.source?.credibility_rating) sourceInfo.push(`Credibility: ${article.source.credibility_rating}`);
    const sourceText = sourceInfo.length > 0 ? sourceInfo.join(', ') : '';

    const tagsText = article.tags
      ? (Array.isArray(article.tags) ? article.tags.join(', ') : article.tags)
      : '';

    const prompt = `Analyze this article: "${article.title}"
Article URI: ${article.uri}
Source: ${sourceName}${sourceText ? ` (${sourceText})` : ''}

ARTICLE METADATA:
${article.category ? `Category: ${article.category}` : ''}
${article.topic ? `Topic: ${article.topic}` : ''}
${article.sentiment ? `Sentiment: ${article.sentiment}` : ''}
${article.time_to_impact ? `Time to Impact: ${article.time_to_impact}` : ''}
${tagsText ? `Tags: ${tagsText}` : ''}

${article.summary ? `SUMMARY:\n${article.summary}` : ''}

Please provide:
1. Key insights and implications from this article
2. Entities and organizations mentioned
3. Potential impact on our organization
4. Related trends or developments to monitor
5. Suggested follow-up questions`;

    openAuspexWithQuery(prompt);
  };

  const formatDate = (dateStr?: string) => {
    if (!dateStr) return 'Unknown date';
    try {
      return new Date(dateStr).toLocaleDateString('en-US', {
        weekday: 'short',
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
      });
    } catch {
      return dateStr;
    }
  };

  const formatRelativeTime = (dateStr?: string) => {
    if (!dateStr) return '';
    try {
      const date = new Date(dateStr);
      const now = new Date();
      const diffMs = now.getTime() - date.getTime();
      const diffMins = Math.floor(diffMs / 60000);
      const diffHours = Math.floor(diffMins / 60);
      const diffDays = Math.floor(diffHours / 24);

      if (diffMins < 60) return `${diffMins}m ago`;
      if (diffHours < 24) return `${diffHours}h ago`;
      if (diffDays < 7) return `${diffDays}d ago`;
      return date.toLocaleDateString();
    } catch {
      return dateStr;
    }
  };

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/20 z-[1100]"
        onClick={onClose}
      />

      {/* Panel */}
      <div className="fixed inset-y-0 right-0 w-full max-w-lg bg-white shadow-2xl z-[1100] overflow-y-auto transform transition-transform duration-300">
        {/* Header */}
        <div className="sticky top-0 bg-white border-b border-gray-200 z-10">
          <div className="px-6 py-4 flex items-center justify-between">
            {/* Left side: Star button */}
            <button
              onClick={handleStarClick}
              className="p-2 hover:bg-gray-100 rounded-full transition-colors"
              title={isStarred ? 'Remove from starred' : 'Add to starred'}
            >
              {isStarred ? (
                <Star className="w-5 h-5 text-yellow-500 fill-yellow-500" />
              ) : (
                <Star className="w-5 h-5 text-gray-600 dark:text-gray-300 hover:text-yellow-500" />
              )}
            </button>

            <h2 className="text-lg font-semibold text-gray-900 truncate px-4 flex-1 text-center">Article Details</h2>

            {/* Right side: Menu and Close */}
            <div className="flex items-center gap-1">
              {/* Kebab menu */}
              <div ref={menuRef} className="relative">
                <button
                  onClick={() => setShowMenu(!showMenu)}
                  className="p-2 hover:bg-gray-100 rounded-full transition-colors"
                >
                  <MoreVertical className="w-5 h-5 text-gray-700 dark:text-gray-300" />
                </button>
                {showMenu && (
                  <div className="absolute right-0 top-full mt-1 bg-white border border-gray-200 rounded-lg shadow-lg z-50 py-1 min-w-[160px]">
                    <button
                      onClick={() => handleMenuAction('more')}
                      disabled={preferenceLoading}
                      className={`w-full px-4 py-2 text-left text-sm flex items-center gap-2 disabled:opacity-50 ${
                        preference === 'more'
                          ? 'bg-green-50 text-green-700'
                          : 'text-gray-700 hover:bg-gray-50'
                      }`}
                    >
                      {preferenceLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <ThumbsUp className={`w-4 h-4 ${preference === 'more' ? 'text-green-600 fill-green-600' : ''}`} />}
                      {preference === 'more' ? 'More like this ✓' : 'More like this'}
                    </button>
                    <button
                      onClick={() => handleMenuAction('less')}
                      disabled={preferenceLoading}
                      className={`w-full px-4 py-2 text-left text-sm flex items-center gap-2 disabled:opacity-50 ${
                        preference === 'less'
                          ? 'bg-red-50 text-red-700'
                          : 'text-gray-700 hover:bg-gray-50'
                      }`}
                    >
                      {preferenceLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <ThumbsDown className={`w-4 h-4 ${preference === 'less' ? 'text-red-600 fill-red-600' : ''}`} />}
                      {preference === 'less' ? 'Less like this ✓' : 'Less like this'}
                    </button>
                    <button
                      onClick={() => handleMenuAction('copy')}
                      className="w-full px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-50 flex items-center gap-2"
                    >
                      <Copy className="w-4 h-4" />
                      Copy link
                    </button>
                    <button
                      onClick={() => handleMenuAction('share')}
                      className="w-full px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-50 flex items-center gap-2"
                    >
                      <Mail className="w-4 h-4" />
                      Share via email
                    </button>
                    <button
                      onClick={() => handleMenuAction('add-to-briefing')}
                      className="w-full px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-50 flex items-center gap-2"
                    >
                      <Newspaper className="w-4 h-4" />
                      Add to Briefing
                    </button>
                    <div className="border-t border-gray-200 my-1" />
                    <button
                      onClick={() => handleMenuAction('promote')}
                      className="w-full px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-50 flex items-center gap-2"
                    >
                      <AlertTriangle className="w-4 h-4" />
                      Promote to Incident
                    </button>
                  </div>
                )}
              </div>
              <button
                onClick={onClose}
                className="p-2 hover:bg-gray-100 rounded-full transition-colors"
              >
                <X className="w-5 h-5 text-gray-700 dark:text-gray-300" />
              </button>
            </div>
          </div>

          {/* Tabs - only show when there are related articles */}
          {hasRelated && (
            <div className="px-6 flex border-t border-gray-300 dark:border-gray-700">
              <button
                onClick={() => setActiveTab('details')}
                className={`px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors ${
                  activeTab === 'details'
                    ? 'border-pink-500 text-pink-600'
                    : 'border-transparent text-gray-700 dark:text-gray-300 hover:text-gray-700'
                }`}
              >
                Details
              </button>
              <button
                onClick={() => setActiveTab('related')}
                className={`px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors flex items-center gap-1.5 ${
                  activeTab === 'related'
                    ? 'border-pink-500 text-pink-600'
                    : 'border-transparent text-gray-700 dark:text-gray-300 hover:text-gray-700'
                }`}
              >
                <Layers className="w-4 h-4" />
                Related Coverage
                <span className="ml-1 px-1.5 py-0.5 text-xs bg-gray-100 rounded-full">
                  {relatedArticles.length}
                </span>
              </button>
            </div>
          )}
        </div>

        {/* Content - Details Tab */}
        {activeTab === 'details' && (
        <div className="p-6">
          {/* Category badge */}
          {article.category && (
            <span className="inline-block bg-pink-100 text-pink-700 text-xs font-medium px-2 py-1 rounded mb-3">
              {article.category}
            </span>
          )}

          {/* Title */}
          <h1 className="text-xl font-bold text-gray-900 leading-tight">
            {article.title}
          </h1>

          {/* Source and date */}
          <div className="flex items-center gap-2 mt-3 text-sm text-gray-700 dark:text-gray-300">
            <Building2 className="w-4 h-4" />
            <span className="font-medium">{article.source?.name || 'Unknown source'}</span>
            <span className="text-gray-600 dark:text-gray-300">•</span>
            <Clock className="w-4 h-4" />
            <span>{formatDate(article.publication_date)}</span>
          </div>

          {/* Bias and factuality indicators */}
          {article.source && (article.source.bias || article.source.factuality) && (
            <div className="mt-4">
              <ArticleBiasIndicator
                bias={article.source.bias}
                factuality={article.source.factuality}
                credibility={article.source.credibility_rating}
                showLabels
                size="md"
              />
            </div>
          )}

          {/* Five Signals screen (Brand Watcher articles only) */}
          {bwScreenable && (
            <div className="mt-4 p-3 rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50">
              <div className="flex items-center gap-2 mb-1">
                <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-200 inline-flex items-center gap-1.5 cursor-help"
                  title="Independent article screen: claim validation (verdict + per-claim checks, source reputation, corroboration) plus Bluesky propagation (spread, coordinated-amplification checks). Full documentation is on the Brand Watcher Help tab.">
                  <BadgeCheck className="w-4 h-4 text-blue-500" /> Five Signals screen
                </h3>
                <span className="flex-1" />
                {bwSignals?.status === 'completed' && bwSignals.composite_score != null && (
                  <span className="text-xs text-gray-500 cursor-help"
                    title="Mean of the available signal scores with Propagation inverted — 0-100, higher is healthier.">
                    composite <span className="font-semibold text-gray-700 dark:text-gray-200">{bwSignals.composite_score}</span>/100
                  </span>
                )}
                {bwSignals?.status === 'completed' && (
                  <button onClick={() => downloadPropagationReport({
                      articleTitle: article?.title || article?.uri || 'article', articleUri: article?.uri || '',
                      brandName: (article as any)?.brand_name || null,
                      signals: bwSignals, generatedAt: new Date().toISOString(),
                    })}
                    title="Download the story propagation report — spread sequence, timeline, per-network pickup, amplification read, claims context. Self-contained HTML."
                    className="text-[11px] px-2 py-0.5 rounded bg-blue-600 text-white hover:bg-blue-700">
                    propagation report ↓
                  </button>
                )}
              </div>
              {!bwSignals && !bwSignalsStarting && (
                <div className="flex items-center gap-2 flex-wrap">
                  <p className="text-xs text-gray-500 dark:text-gray-400">Not screened yet.</p>
                  <button onClick={() => startBwSignals('full')}
                    title="Runs both engines — claim validation + Bluesky propagation — and composes all five signals (2-4 min; result is cached)"
                    className="text-xs px-2.5 py-1 rounded-md bg-blue-600 text-white hover:bg-blue-700 inline-flex items-center gap-1">
                    <BadgeCheck className="w-3.5 h-3.5" /> Run Five Signals
                  </button>
                  <span className="text-[11px] text-gray-400">or one engine:</span>
                  <button onClick={() => startBwSignals('validation')}
                    title="Claim validation only (~1-3 min) — fills Veracity, Source credibility and Corroboration"
                    className="text-xs px-2 py-1 rounded border border-dashed border-gray-300 dark:border-gray-600 text-gray-500 hover:text-blue-600 hover:border-blue-400">
                    claim validation
                  </button>
                  <button onClick={() => startBwSignals('reach')}
                    title="Bluesky story-reach only (~1-2 min) — fills Propagation and Amplification integrity"
                    className="text-xs px-2 py-1 rounded border border-dashed border-gray-300 dark:border-gray-600 text-gray-500 hover:text-blue-600 hover:border-blue-400">
                    bsky reach
                  </button>
                </div>
              )}
              {(bwSignalsStarting || bwSignals?.status === 'running') && (
                <p className="text-xs text-gray-500 dark:text-gray-400 inline-flex items-center gap-1.5">
                  <Loader2 className="w-3 h-3 animate-spin" /> Screening — claim validation and propagation take 2–4 minutes; this panel updates automatically.
                </p>
              )}
              {bwSignals?.status === 'failed' && (
                <p className="text-xs text-red-500">Screen failed{bwSignals.error ? `: ${bwSignals.error}` : ''}.</p>
              )}
              {bwSignals?.status === 'completed' && (
                <div className="space-y-1.5">
                  {bwSignals.verdict && (
                    <p className="text-xs text-gray-600 dark:text-gray-300">
                      Claim-validation verdict: <span className={`px-1.5 py-0.5 rounded-full font-semibold ${
                        ['contested', 'non_independent', 'satire'].includes(bwSignals.verdict) ? 'bg-red-100 text-red-800'
                        : bwSignals.verdict === 'corroborated' ? 'bg-emerald-100 text-emerald-800'
                        : 'bg-amber-100 text-amber-800'}`}>{bwSignals.verdict}</span>
                    </p>
                  )}
                  {BW_SIG_ORDER.map(k => {
                    const s = bwSignals.signals?.[k];
                    if (!s) return null;
                    return (
                      <div key={k} className="flex items-start gap-2 text-xs">
                        <span className={`shrink-0 w-5 text-center py-0.5 rounded font-bold ${BW_SIG_BAND[s.band || 'nodata']}`}
                          title={`${s.label}${s.score != null ? `: ${s.score}/100` : ''}`}>{BW_SIG_SHORT[k]}</span>
                        <span className="text-gray-600 dark:text-gray-300">
                          <span className="font-medium">{s.label}{s.score != null ? ` (${s.score})` : ''}:</span> {s.summary}
                        </span>
                      </div>
                    );
                  })}
                  {!(bwSignals as any).validation && (
                    <button onClick={() => startBwSignals('validation')}
                      title="Claim validation has not been queried for this article yet (~1-3 min)"
                      className="text-[11px] text-blue-600 dark:text-blue-400 hover:underline">Validate claims →</button>
                  )}
                  {(() => {
                    const rp: any = (bwSignals as any).reach;
                    const xn: any = (bwSignals as any).xnet;
                    const xplats = Object.entries<any>((xn?.platforms) || {}).filter(([, p]) => p.posts > 0);
                    if (!rp && !xn) return (
                      <button onClick={() => startBwSignals('reach')}
                        title="The social propagation lookup (Bluesky live trace + other networks) has not been queried for this article yet (~1-2 min)"
                        className="text-[11px] text-blue-600 dark:text-blue-400 hover:underline">Query social reach →</button>
                    );
                    const posts: any[] = rp?.posts || [];
                    return (
                      <div className="pt-1">
                        {posts.length > 0 && (
                          <>
                            <p className="text-[11px] font-medium text-gray-600 dark:text-gray-300 cursor-help"
                              title="Bluesky posts sharing this article's URL, ordered by engagement — the raw material behind the Propagation signal.">Bluesky pickup ({rp.totals?.posts ?? posts.length} post{(rp.totals?.posts ?? posts.length) !== 1 ? 's' : ''}):</p>
                            {posts.slice(0, 3).map((p: any, i: number) => (
                              <p key={i} className="text-[11px] text-gray-500 dark:text-gray-400 truncate" title={p.text || ''}>
                                @{p.handle} · {p.total_engagement ?? 0} eng
                                {p.post_url && <> — <a href={p.post_url} target="_blank" rel="noreferrer" className="text-blue-500 hover:underline">view post</a></>}
                                {p.text ? <> — {p.text}</> : null}
                              </p>
                            ))}
                          </>
                        )}
                        {xplats.length > 0 && (
                          <p className="text-[11px] text-gray-500 dark:text-gray-400 mt-0.5 cursor-help"
                            title="Cross-network shares from the monitoring corpus + live xpoz query. Full breakdown and sample posts are in the propagation report.">
                            Other networks: {xplats.map(([k, p]) => `${k} ${p.posts}`).join(' · ')}
                          </p>
                        )}
                      </div>
                    );
                  })()}
                </div>
              )}
            </div>
          )}

          {/* Summary */}
          <div className="mt-6">
            <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-wide mb-2">Summary</h3>
            <p className="text-gray-700 leading-relaxed">
              {article.summary || 'No summary available.'}
            </p>
          </div>

          {/* Metadata Grid */}
          <div className="mt-6 grid grid-cols-2 gap-4">
            <MetadataItem
              icon={<TrendingUp className="w-4 h-4" />}
              label="Sentiment"
              value={article.sentiment}
              valueColor={getSentimentColor(article.sentiment)}
            />
            <MetadataItem
              icon={<Clock className="w-4 h-4" />}
              label="Time to Impact"
              value={article.time_to_impact}
            />
            {article.topic && (
              <MetadataItem
                label="Topic"
                value={article.topic}
              />
            )}
            {article.source?.credibility_rating && (
              <MetadataItem
                label="Credibility"
                value={article.source.credibility_rating}
              />
            )}
          </div>

          {/* Brand Watcher Classifications (shown when BW data is present) */}
          {(article as any).categories?.length > 0 && (
            <div className="mt-6">
              <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-wide mb-2">Brand Classifications</h3>
              <div className="flex flex-wrap gap-2">
                {(article as any).categories.map((cat: string) => {
                  const colors: Record<string, string> = {
                    'Product & Innovation': '#2563eb',
                    'Financial Performance': '#16a34a',
                    'Leadership & Governance': '#7c3aed',
                    'Brand Sentiment & Perception': '#db2777',
                    'Competitive Landscape': '#d97706',
                    'Legal & Regulatory': '#dc2626',
                    'Partnerships & Alliances': '#0891b2',
                    'ESG & Social Responsibility': '#059669',
                    'Customer & Product Issues': '#e11d48',
                    'Market Strategy & Expansion': '#4f46e5',
                    'Media & Advertising': '#9333ea',
                  };
                  const shortNames: Record<string, string> = {
                    'Product & Innovation': 'Product',
                    'Financial Performance': 'Financial',
                    'Leadership & Governance': 'Leadership',
                    'Brand Sentiment & Perception': 'Perception',
                    'Competitive Landscape': 'Competition',
                    'Legal & Regulatory': 'Legal',
                    'Partnerships & Alliances': 'Partnerships',
                    'ESG & Social Responsibility': 'ESG',
                    'Customer & Product Issues': 'Issues',
                    'Market Strategy & Expansion': 'Strategy',
                    'Media & Advertising': 'Media',
                  };
                  const color = colors[cat] || '#6b7280';
                  return (
                    <span key={cat} title={cat} className="px-2 py-1 text-sm rounded" style={{
                      backgroundColor: color + '20',
                      color: color,
                    }}>
                      {shortNames[cat] || cat}
                    </span>
                  );
                })}
              </div>
            </div>
          )}
          {(article as any).brand_name && (
            <div className="mt-4 grid grid-cols-2 gap-4">
              <MetadataItem label="Brand" value={(article as any).brand_name} />
            </div>
          )}
          {(article as any).matched_keywords?.length > 0 && (
            <div className="mt-4">
              <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-wide mb-2">Matched Keywords</h3>
              <div className="flex flex-wrap gap-1">
                {(article as any).matched_keywords.map((kw: string) => (
                  <span key={kw} className="px-2 py-0.5 text-xs bg-yellow-100 text-yellow-700 rounded">{kw}</span>
                ))}
              </div>
            </div>
          )}

          {/* Tags */}
          {article.tags && (Array.isArray(article.tags) ? article.tags.length > 0 : article.tags) && (
            <div className="mt-6">
              <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-wide mb-2">Tags</h3>
              <div className="flex flex-wrap gap-2">
                {(Array.isArray(article.tags)
                  ? article.tags
                  : String(article.tags).split(',').map(t => t.trim()).filter(Boolean)
                ).map((tag, i) => {
                  const isSignalTag = tag.startsWith('SIGNAL_');
                  const displayName = isSignalTag
                    ? tag.replace('SIGNAL_', '').replace(/_/g, ' ').split(' ')
                        .map(word => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
                        .join(' ')
                    : tag;

                  return (
                    <span
                      key={i}
                      className={`px-2 py-1 text-sm rounded inline-flex items-center gap-1 ${
                        isSignalTag
                          ? 'bg-pink-100 text-pink-700'
                          : 'bg-gray-100 text-gray-600'
                      }`}
                      title={isSignalTag ? `Matched by Research Agent: ${displayName}` : undefined}
                    >
                      {isSignalTag && <Bot className="w-3 h-3" />}
                      {displayName}
                    </span>
                  );
                })}
              </div>
            </div>
          )}

          {/* Action buttons */}
          <div className="mt-8 flex items-center gap-4">
            {(article.url || article.uri) && (
              <a
                href={article.url || article.uri}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 text-sm text-blue-600 hover:text-blue-700 font-medium transition-colors"
              >
                <ExternalLink className="w-3.5 h-3.5" />
                Read Original Article
              </a>
            )}

            <button
              onClick={handleAskAuspex}
              className="inline-flex items-center gap-1.5 text-sm text-pink-600 hover:text-pink-700 font-medium transition-colors"
            >
              <MessageSquare className="w-3.5 h-3.5" />
              Ask Auspex
            </button>
          </div>
        </div>
        )}

        {/* Content - Related Coverage Tab */}
        {activeTab === 'related' && hasRelated && (
          <div className="p-6">
            <div className="mb-4">
              <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-wide mb-1">
                Full Coverage
              </h3>
              <p className="text-xs text-gray-700 dark:text-gray-300">
                {relatedArticles.length + 1} sources reporting on this story
              </p>
              {coverageSentiments.length >= 2 && (
                <div className="mt-2 flex items-center gap-2">
                  <span className="text-[11px] text-gray-500">Sentiment across coverage:</span>
                  <div className="flex h-2.5 w-40 rounded-full overflow-hidden bg-gray-100">
                    {spread.positive > 0 && <div className="bg-emerald-400" style={{ width: `${(spread.positive / coverageSentiments.length) * 100}%` }} />}
                    {spread.neutral > 0 && <div className="bg-gray-300" style={{ width: `${(spread.neutral / coverageSentiments.length) * 100}%` }} />}
                    {spread.negative > 0 && <div className="bg-red-400" style={{ width: `${(spread.negative / coverageSentiments.length) * 100}%` }} />}
                  </div>
                  <span className="text-[11px] text-gray-500">{spread.positive}+ {spread.neutral}· {spread.negative}−</span>
                </div>
              )}
              {/* Screening flags: consensus negativity and acute polarization are the
                  two coverage patterns that warrant attention beyond any single article. */}
              {coverageSentiments.length >= 3 && spread.negative / coverageSentiments.length >= 0.7 && (
                <div className="mt-2 px-3 py-2 rounded-md bg-red-50 border border-red-200 text-xs text-red-700 font-medium">
                  ⚠ Negative consensus — {spread.negative} of {coverageSentiments.length} scored sources frame this story negatively. This is the story's framing, not one outlet's take.
                </div>
              )}
              {coverageSentiments.length >= 4 && spread.negative / coverageSentiments.length < 0.7
                && Math.min(spread.positive, spread.negative) / coverageSentiments.length >= 0.3 && (
                <div className="mt-2 px-3 py-2 rounded-md bg-purple-50 border border-purple-200 text-xs text-purple-700 font-medium">
                  ⚡ Polarized coverage — sources split {spread.positive} positive vs {spread.negative} negative. The narrative is contested; check which outlets take which side.
                </div>
              )}
            </div>

            {/* Primary article (current) */}
            <div className="mb-4 p-4 bg-pink-50 rounded-lg border border-pink-200">
              <div className="flex items-center gap-2 text-xs text-pink-600 mb-2">
                <span className="font-semibold">Primary Source</span>
                <span className="text-pink-400">•</span>
                <span>{article.source?.name}</span>
              </div>
              <h4 className="font-medium text-gray-900 mb-2">{article.title}</h4>
              {article.summary && (
                <p className="text-sm text-gray-600 line-clamp-3">{article.summary}</p>
              )}
            </div>

            {/* Related articles list */}
            <div className="space-y-3">
              {relatedArticles.map((related) => (
                <button
                  key={related.uri}
                  onClick={() => onRelatedArticleClick?.(related.uri)}
                  className="w-full text-left p-4 bg-gray-50 hover:bg-gray-100 rounded-lg border border-gray-200 hover:border-gray-300 transition-colors"
                >
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2 text-xs flex-wrap">
                      <span className="font-medium text-gray-700">{related.news_source}</span>
                      {related.publication_date && (
                        <>
                          <span className="text-gray-600 dark:text-gray-300">•</span>
                          <span className="text-gray-700 dark:text-gray-300">{formatRelativeTime(related.publication_date)}</span>
                        </>
                      )}
                      {sentimentBucket((related as any).sentiment) && (
                        <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${SENT_CHIP[sentimentBucket((related as any).sentiment)!]}`}>
                          {sentimentBucket((related as any).sentiment)}
                        </span>
                      )}
                      {factChip(related.factual_reporting)}
                      {related.bias && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-blue-50 text-blue-600" title="MBFC bias rating">{related.bias}</span>
                      )}
                    </div>
                    <ChevronRight className="w-4 h-4 text-gray-600 dark:text-gray-300 flex-shrink-0" />
                  </div>
                  <h4 className="font-medium text-gray-900 mb-2 line-clamp-2">{related.title}</h4>
                  {related.summary && (
                    <p className="text-sm text-gray-600 line-clamp-2">{related.summary}</p>
                  )}
                  {related.similarity_score && (
                    <div className="mt-2 flex items-center gap-1 text-xs text-gray-600 dark:text-gray-300">
                      <span className="inline-block w-1.5 h-1.5 rounded-full bg-green-400"></span>
                      <span>{Math.round(related.similarity_score * 100)}% similar</span>
                    </div>
                  )}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Share Modal */}
      {article && (
        <ShareModal
          open={showShareModal}
          onOpenChange={setShowShareModal}
          data={{
            type: 'article',
            title: article.title,
            url: article.url || article.uri,
            source: article.source?.name,
            summary: article.summary,
            category: article.category,
            topic: article.topic,
            sentiment: article.sentiment,
            publication_date: article.publication_date,
          } as ShareArticleData}
        />
      )}

      {/* Promote to Incident Modal */}
      <PromoteToIncidentModal
        open={showPromoteModal}
        onOpenChange={setShowPromoteModal}
        article={article}
        topic={topic || article?.topic}
        profileId={profileId}
        onSuccess={onIncidentSaved}
      />

      {/* Add to Briefing Modal */}
      <AddToBriefingModal
        isOpen={showAddToBriefingModal}
        onClose={() => setShowAddToBriefingModal(false)}
        itemType="article"
        article={{
          uri: article.uri,
          title: article.title,
          summary: article.summary,
          source: article.source?.name,
          publication_date: article.publication_date,
          topic: article.topic || topic,
          url: article.url || article.uri,
          sentiment: article.sentiment,
          bias: article.source?.bias,
          category: article.category,
          // Include analysis if available (from executive briefing context)
          analysis: (article as any).executive_takeaway || (article as any).strategic_relevance ? {
            executive_takeaway: (article as any).executive_takeaway,
            strategic_relevance: (article as any).strategic_relevance,
            time_horizon: (article as any).time_horizon,
            risk_opportunity: (article as any).risk_opportunity,
            signal_strength: (article as any).signal_strength,
          } : undefined,
        }}
      />
    </>
  );
}

interface MetadataItemProps {
  icon?: React.ReactNode;
  label: string;
  value?: string;
  valueColor?: string;
}

function MetadataItem({ icon, label, value, valueColor }: MetadataItemProps) {
  if (!value) return null;

  return (
    <div className="bg-gray-50 rounded-lg p-3">
      <div className="flex items-center gap-1.5 text-xs text-gray-700 dark:text-gray-300 mb-1">
        {icon}
        <span className="uppercase tracking-wide">{label}</span>
      </div>
      <div className={`font-medium ${valueColor || 'text-gray-900'}`}>
        {value}
      </div>
    </div>
  );
}

function getSentimentColor(sentiment?: string): string {
  if (!sentiment) return 'text-gray-900';
  const lower = sentiment.toLowerCase();
  if (lower === 'positive' || lower === 'bullish') return 'text-green-600';
  if (lower === 'negative' || lower === 'bearish') return 'text-red-600';
  if (lower === 'neutral') return 'text-gray-600';
  return 'text-gray-900';
}
