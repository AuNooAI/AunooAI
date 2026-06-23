/**
 * Brand Watcher Tab Component
 * Main container for brand intelligence dashboard
 */

import { useState, useCallback, useEffect, useMemo, useRef } from 'react';
import {
  RefreshCw, AlertCircle, X, Loader2, Target, Plus, Settings, Sparkles,
  BarChart3, TrendingUp, Users, FileText, ChevronDown, ChevronRight,
  Trash2, Edit2, ToggleLeft, ToggleRight, Zap, Clock, Play, Calendar,
  Download, AlertTriangle, Eye, Star, Image, FileDown, Copy, Check, Printer, Search,
} from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend, Cell, AreaChart, Area, PieChart, Pie } from 'recharts';
import { useBrandWatcher } from '../../hooks/useBrandWatcher';
import { ChartDownloadButton } from './ChartDownloadButton';
import { ExportService } from '../../services/exportService';
import {
  classifyArticles, getClassifyStatus, generateNarrative, getLatestNarrative,
  generateCategoryInsight, suggestKeywords, setupBrandMonitoring, getSchedules, createSchedule, deleteSchedule,
  runScheduleNow, getSentimentTrends, getBrandAlerts, exportBrandData, updateBrandConfig,
  retrainClassifier, setupSocialMonitoring, CATEGORY_COLORS, CATEGORY_SHORT_NAMES,
  type Brand, type BrandCreate, type BWArticle, type BWSavedNarrative,
  type BWCategoryInsightResponse, type BWSchedule, type BWSentimentTrend, type BWAlert,
} from '../../services/brandWatcherApi';

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
  onArticleClick?: (article: { uri: string; title?: string }) => void;
}

type SubTab = 'overview' | 'analysis' | 'comparison' | 'insights' | 'articles' | 'social';

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

  const [activeTab, setActiveTab] = useState<SubTab>('overview');
  const [socialSource, setSocialSource] = useState<string>('');  // '' = all, 'reddit', 'bluesky'
  const [socialMinRel, setSocialMinRel] = useState(0.4);  // default to evaluated, on-brand posts only
  const [socialInclUneval, setSocialInclUneval] = useState(false);  // include not-yet-scored posts (only matters at min rel = All)
  const [socialSentiment, setSocialSentiment] = useState<string>('');  // '' = all, 'positive', 'neutral', 'negative'
  const [socialSearch, setSocialSearch] = useState('');  // free-text filter over title/summary
  const [socialSort, setSocialSort] = useState<'recent' | 'oldest' | 'relevance'>('recent');
  const [enablingSocial, setEnablingSocial] = useState(false);
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
  const socialSentimentOf = (s: string | null): 'positive' | 'neutral' | 'negative' | 'unrated' => {
    const t = (s || '').toLowerCase();
    if (t.includes('pos')) return 'positive';
    if (t.includes('neg')) return 'negative';
    if (t.includes('neu') || t === 'mixed') return 'neutral';
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
  const socialView = useMemo(() => {
    if (!social) return null;
    const posts = social.posts || [];
    const q = socialSearch.trim().toLowerCase();
    let filtered = posts.filter(p => {
      if (socialSentiment && socialSentimentOf(p.sentiment) !== socialSentiment) return false;
      if (q && !`${p.title || ''} ${p.summary || ''}`.toLowerCase().includes(q)) return false;
      return true;
    });
    filtered = [...filtered].sort((a, b) => {
      if (socialSort === 'relevance') return (b.relevance ?? -1) - (a.relevance ?? -1);
      const da = a.publication_date || '', db = b.publication_date || '';
      return socialSort === 'oldest' ? da.localeCompare(db) : db.localeCompare(da);
    });
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
    return { filtered, sentCounts, netSentiment, sentPie, platPie, timeline, totalLoaded: posts.length };
  }, [social, socialSentiment, socialSearch, socialSort]);

  const selectedBrands = brands.filter(b => config.selectedBrandIds.includes(b.id));
  const selectedBrand = selectedBrands[0] || undefined;
  const primarySelectedId = config.selectedBrandIds[0] || null;

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
      fetchSocial(socialMinRel, socialSource || undefined, socialInclUneval);
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
  }, [primarySelectedId, config.daysBack, fetchComparison, fetchShareOfVoice, fetchSocial, socialMinRel, socialSource, socialInclUneval]);

  // --- Refresh overview data when brand/period changes ---
  useEffect(() => {
    if (activeTab !== 'overview') return;
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
              <div className="absolute right-0 top-full mt-1 w-48 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg z-50 py-1">
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
          { id: 'overview' as SubTab, label: 'Overview', icon: BarChart3 },
          { id: 'analysis' as SubTab, label: 'Brand Analysis', icon: TrendingUp },
          { id: 'comparison' as SubTab, label: 'Comparison', icon: Users },
          { id: 'insights' as SubTab, label: 'Insights', icon: FileText },
          { id: 'articles' as SubTab, label: 'Articles', icon: Target },
          { id: 'social' as SubTab, label: 'Social', icon: Users },
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
                {[...brandAlerts].sort((a, b) => b.spike_ratio - a.spike_ratio).slice(0, 3).map(alert => (
                  <div key={alert.category}
                    className={`flex items-center gap-3 p-2 rounded-lg ${
                      alert.severity === 'high'
                        ? 'bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800'
                        : 'bg-orange-50 dark:bg-orange-900/20 border border-orange-200 dark:border-orange-800'
                    }`}
                  >
                    <div className="w-3 h-3 rounded-full flex-shrink-0" style={{ backgroundColor: CATEGORY_COLORS[alert.category] || '#6b7280' }} />
                    <span className="text-sm text-gray-700 dark:text-gray-300 flex-1">{alert.category}</span>
                    <span className="text-xs font-mono text-gray-600 dark:text-gray-400">
                      {alert.current_count} this week (avg: {alert.average_count})
                    </span>
                    <span className={`text-xs font-bold px-1.5 py-0.5 rounded ${
                      alert.severity === 'high' ? 'bg-red-200 text-red-800 dark:bg-red-800 dark:text-red-200' : 'bg-orange-200 text-orange-800 dark:bg-orange-800 dark:text-orange-200'
                    }`}>
                      {alert.spike_ratio}x
                    </span>
                  </div>
                ))}
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
                    onClick={() => onArticleClick?.({ ...article })}
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
                        {brandAlerts.map(alert => (
                          <div key={alert.category}
                            className={`flex items-center gap-3 p-2 rounded-lg ${
                              alert.severity === 'high'
                                ? 'bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800'
                                : 'bg-orange-50 dark:bg-orange-900/20 border border-orange-200 dark:border-orange-800'
                            }`}
                          >
                            <div className="w-3 h-3 rounded-full flex-shrink-0" style={{ backgroundColor: CATEGORY_COLORS[alert.category] || '#6b7280' }} />
                            <span className="text-sm text-gray-700 dark:text-gray-300 flex-1">{alert.category}</span>
                            <span className="text-xs font-mono text-gray-600 dark:text-gray-400">
                              {alert.current_count} this week (avg: {alert.average_count})
                            </span>
                            <span className={`text-xs font-bold px-1.5 py-0.5 rounded ${
                              alert.severity === 'high' ? 'bg-red-200 text-red-800 dark:bg-red-800 dark:text-red-200' : 'bg-orange-200 text-orange-800 dark:bg-orange-800 dark:text-orange-200'
                            }`}>
                              {alert.spike_ratio}x
                            </span>
                          </div>
                        ))}
                      </div>
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
                              <div key={cat} className="flex items-center gap-3">
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
                              </div>
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
          <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-start gap-2">
                <Users className="w-5 h-5 text-blue-500 mt-0.5 flex-shrink-0" />
                <div className="text-sm text-gray-700 dark:text-gray-300">
                  <span className="font-semibold">Social mentions.</span> Reddit + Bluesky posts mentioning this brand, with a lightweight relevance score ("is this actually about the brand?") and sentiment evaluated by a local/Bedrock model built for volume.
                </div>
              </div>
              <button
                onClick={async () => {
                  if (!primarySelectedId) { alert('Select a brand first.'); return; }
                  setEnablingSocial(true);
                  try {
                    const r = await setupSocialMonitoring(primarySelectedId, 24);
                    alert(`Social monitoring ${r.created ? 'enabled' : 'updated'}: "${r.group_name}" — ${r.keywords_added} keywords, polling every ${r.interval_hours}h. Posts collect on the next cycle; tune providers/interval/model in Gather → group Settings.`);
                    fetchSocial(socialMinRel, socialSource || undefined, socialInclUneval);
                  } catch (e: any) {
                    alert('Failed to enable social monitoring: ' + e.message);
                  } finally {
                    setEnablingSocial(false);
                  }
                }}
                disabled={enablingSocial || !primarySelectedId}
                className="flex-shrink-0 text-xs px-3 py-1.5 rounded-md bg-blue-600 hover:bg-blue-700 text-white disabled:opacity-50 inline-flex items-center gap-1.5"
                title={primarySelectedId ? 'Create/refresh this brand’s social monitoring group (Reddit + Bluesky, own schedule)' : 'Select a brand first'}
              >
                {enablingSocial ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Plus className="w-3.5 h-3.5" />}
                {enablingSocial ? 'Enabling…' : 'Add social monitoring'}
              </button>
            </div>
          </div>

          {/* Server-side filters (re-fetch): source + min relevance */}
          <div className="flex items-center gap-3 flex-wrap">
            <span className="text-xs font-medium text-gray-500 dark:text-gray-400">Source:</span>
            {([
              { label: 'All', val: '' },
              { label: 'Reddit', val: 'reddit' },
              { label: 'Bluesky', val: 'bluesky' },
            ]).map(opt => (
              <button
                key={opt.val}
                onClick={() => { setSocialSource(opt.val); fetchSocial(socialMinRel, opt.val || undefined, socialInclUneval); }}
                className={`text-xs px-3 py-1 rounded-full border transition-colors ${
                  socialSource === opt.val
                    ? 'bg-blue-600 text-white border-blue-600'
                    : 'bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300 border-gray-300 dark:border-gray-600 hover:border-blue-400'
                }`}
              >
                {opt.label}
              </button>
            ))}
            <span className="text-xs font-medium text-gray-500 dark:text-gray-400 ml-2">Min relevance:</span>
            {([
              { label: 'All', val: 0 },
              { label: '≥0.4', val: 0.4 },
              { label: '≥0.6', val: 0.6 },
            ]).map(opt => (
              <button
                key={opt.val}
                onClick={() => { setSocialMinRel(opt.val); fetchSocial(opt.val, socialSource || undefined, socialInclUneval); }}
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
                onClick={() => { const v = !socialInclUneval; setSocialInclUneval(v); fetchSocial(socialMinRel, socialSource || undefined, v); }}
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
          </div>

          {/* Client-side filters (no re-fetch): sentiment + search + sort */}
          <div className="flex items-center gap-3 flex-wrap">
            <span className="text-xs font-medium text-gray-500 dark:text-gray-400">Sentiment:</span>
            {([
              { label: 'All', val: '' },
              { label: 'Positive', val: 'positive' },
              { label: 'Neutral', val: 'neutral' },
              { label: 'Negative', val: 'negative' },
            ]).map(opt => (
              <button
                key={opt.val}
                onClick={() => setSocialSentiment(opt.val)}
                className={`text-xs px-3 py-1 rounded-full border transition-colors ${
                  socialSentiment === opt.val
                    ? 'bg-blue-600 text-white border-blue-600'
                    : 'bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300 border-gray-300 dark:border-gray-600 hover:border-blue-400'
                }`}
              >
                {opt.label}
              </button>
            ))}
            <div className="relative ml-2">
              <Search className="w-3.5 h-3.5 text-gray-400 absolute left-2.5 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                value={socialSearch}
                onChange={e => setSocialSearch(e.target.value)}
                placeholder="Search posts…"
                className="text-xs pl-7 pr-2 py-1.5 rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200 w-44 focus:outline-none focus:border-blue-400"
              />
            </div>
            <select
              value={socialSort}
              onChange={e => setSocialSort(e.target.value as 'recent' | 'oldest' | 'relevance')}
              className="text-xs px-2 py-1.5 rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200 focus:outline-none focus:border-blue-400"
            >
              <option value="recent">Newest first</option>
              <option value="oldest">Oldest first</option>
              <option value="relevance">Most relevant</option>
            </select>
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
                  <p className="text-xs text-gray-500 dark:text-gray-400">Showing</p>
                  <p className="text-2xl font-bold text-gray-900 dark:text-gray-100">{socialView.filtered.length.toLocaleString()}</p>
                  <p className="text-xs text-gray-400">of {socialView.totalLoaded.toLocaleString()} loaded</p>
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
                          {socialView.platPie.map((d, i) => <Cell key={d.name} fill={d.name === 'reddit' ? '#f97316' : d.name === 'bluesky' ? '#0ea5e9' : ['#8b5cf6', '#14b8a6', '#eab308'][i % 3]} />)}
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

              {/* Posts list (client-filtered + sorted) */}
              <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 divide-y divide-gray-100 dark:divide-gray-700">
                {socialView.filtered.map(p => {
                  const sent = socialSentimentOf(p.sentiment);
                  return (
                  <div key={p.uri} className="flex gap-3 p-4 hover:bg-gray-50 dark:hover:bg-gray-750">
                    {/* sentiment rail */}
                    <div className="w-1 rounded-full flex-shrink-0" style={{ backgroundColor: SOCIAL_SENTIMENT_COLORS[sent] }} title={sent} />
                    <div className="min-w-0 flex-1">
                      {/* byline */}
                      <div className="flex items-center justify-between gap-3">
                        <div className="flex items-center gap-2 min-w-0">
                          <span className="text-sm font-semibold text-gray-800 dark:text-gray-100 truncate">{socialAuthorOf(p)}</span>
                          <span className={`text-[10px] px-1.5 py-0.5 rounded-full flex-shrink-0 ${
                            p.platform === 'reddit' ? 'bg-orange-50 dark:bg-orange-900/20 text-orange-700 dark:text-orange-400'
                            : 'bg-sky-50 dark:bg-sky-900/20 text-sky-700 dark:text-sky-400'
                          }`}>{p.platform}</span>
                          {p.publication_date && <span className="text-xs text-gray-400 flex-shrink-0">{p.publication_date.slice(0, 10)}</span>}
                        </div>
                        <a href={p.uri} target="_blank" rel="noopener noreferrer" className="text-xs text-blue-600 dark:text-blue-400 hover:underline flex-shrink-0 inline-flex items-center gap-1">
                          <Eye className="w-3 h-3" /> View
                        </a>
                      </div>
                      {/* post body */}
                      <p className="text-sm text-gray-700 dark:text-gray-200 mt-1 line-clamp-3 whitespace-pre-wrap">{socialBodyOf(p)}</p>
                      {/* metadata */}
                      <div className="flex items-center gap-2 mt-2 flex-wrap">
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
                        {p.news_source && p.news_source.toLowerCase() !== p.platform && (
                          <span className="text-[11px] text-gray-400">{p.news_source}</span>
                        )}
                      </div>
                    </div>
                  </div>
                  );
                })}
                {socialView.filtered.length === 0 && socialView.totalLoaded > 0 && (
                  <div className="p-8 text-center text-sm text-gray-400">No posts match the current sentiment/search filters.</div>
                )}
                {socialView.totalLoaded === 0 && (
                  <div className="p-8 text-center text-sm text-gray-400">No social posts yet. Add Reddit/Bluesky to this brand's collection sources and run a collection cycle.</div>
                )}
              </div>
            </>
          )}

          {!loadingSocial && !social && (
            <div className="text-center py-12 text-gray-400 text-sm">No social data loaded.</div>
          )}
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
                      <div key={sov.brand_id} className="flex items-center gap-3">
                        <div className="w-3 h-3 rounded-full flex-shrink-0" style={{ backgroundColor: sov.color || '#6b7280' }} />
                        <span className="text-sm text-gray-700 dark:text-gray-300 flex-1 truncate">{sov.brand_name}</span>
                        <span className="text-sm font-bold text-gray-900 dark:text-gray-100">{sov.percentage.toFixed(1)}%</span>
                        <span className="text-xs text-gray-400 w-20 text-right">{sov.mention_count} articles</span>
                      </div>
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
                  onClick={() => onArticleClick?.({ ...article })}
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
                    {article.news_source && (
                      <span className="text-xs text-gray-400">{article.news_source}</span>
                    )}
                    {article.publication_date && (
                      <span className="text-xs text-gray-400">{article.publication_date.slice(0, 10)}</span>
                    )}
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
