/**
 * Brand Watcher Tab Component
 * Main container for brand intelligence dashboard
 */

import { useState, useCallback } from 'react';
import {
  RefreshCw, AlertCircle, X, Loader2, Target, Plus, Settings, Sparkles,
  BarChart3, TrendingUp, Users, FileText, ChevronDown, ChevronRight,
  Trash2, Edit2, ToggleLeft, ToggleRight, Zap, Clock, Play, Calendar,
} from 'lucide-react';
import { useBrandWatcher } from '../../hooks/useBrandWatcher';
import {
  classifyArticles, getClassifyStatus, generateNarrative, getLatestNarrative,
  generateCategoryInsight, suggestKeywords, setupBrandMonitoring, getSchedules, createSchedule, deleteSchedule,
  runScheduleNow, CATEGORY_COLORS, CATEGORY_SHORT_NAMES,
  type Brand, type BrandCreate, type BWArticle, type BWSavedNarrative,
  type BWCategoryInsightResponse, type BWSchedule,
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

type SubTab = 'overview' | 'analysis' | 'comparison' | 'insights' | 'articles';

export function BrandWatcherTab({ onArticleClick }: BrandWatcherTabProps) {
  const {
    brands, topics, stats, categories, temporalData, articles,
    comparison, shareOfVoice, config,
    totalArticles, totalPages,
    loading, loadingStats, loadingCategories, loadingArticles,
    error,
    updateConfig, clearError, refresh,
    fetchComparison, fetchShareOfVoice,
    createBrand, updateBrand: updateBrandFn, deleteBrand: deleteBrandFn, toggleBrand: toggleBrandFn,
  } = useBrandWatcher();

  const [activeTab, setActiveTab] = useState<SubTab>('overview');
  const [showBrandConfig, setShowBrandConfig] = useState(false);
  const [showClassifyModal, setShowClassifyModal] = useState(false);
  const [classifyRunId, setClassifyRunId] = useState<number | null>(null);
  const [classifyStatus, setClassifyStatus] = useState<string>('');
  const [narrative, setNarrative] = useState<BWSavedNarrative | null>(null);
  const [loadingNarrative, setLoadingNarrative] = useState(false);
  const [generatingNarrative, setGeneratingNarrative] = useState(false);
  const [categoryInsight, setCategoryInsight] = useState<BWCategoryInsightResponse | null>(null);
  const [loadingInsight, setLoadingInsight] = useState(false);

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

  const selectedBrand = brands.find(b => b.id === config.selectedBrandId);

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
    if (tab === 'comparison') {
      fetchComparison();
      fetchShareOfVoice();
    }
    if (tab === 'insights' && config.selectedBrandId) {
      setLoadingNarrative(true);
      getLatestNarrative(config.selectedBrandId)
        .then(n => setNarrative(n))
        .catch(console.error)
        .finally(() => setLoadingNarrative(false));
    }
  }, [config.selectedBrandId, fetchComparison, fetchShareOfVoice]);

  // --- Classify ---
  const handleClassify = useCallback(async (runType: string = 'incremental', daysBack: number = 30) => {
    try {
      const res = await classifyArticles({
        brand_id: config.selectedBrandId || undefined,
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
  }, [config.selectedBrandId, config.selectedTopics, refresh]);

  // --- Generate narrative ---
  const handleGenerateNarrative = useCallback(async () => {
    if (!config.selectedBrandId) return;
    setGeneratingNarrative(true);
    try {
      const res = await generateNarrative({
        brand_id: config.selectedBrandId,
        days_back: config.daysBack,
      });
      setNarrative({
        id: 0, brand_id: config.selectedBrandId,
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
  }, [config.selectedBrandId, config.daysBack, selectedBrand]);

  // --- Category insight ---
  const handleCategoryInsight = useCallback(async (category: string) => {
    if (!config.selectedBrandId) return;
    setLoadingInsight(true);
    setCategoryInsight(null);
    try {
      const res = await generateCategoryInsight({
        brand_id: config.selectedBrandId,
        category,
        days_back: config.daysBack,
      });
      setCategoryInsight(res);
    } catch (err) {
      console.error('Category insight error:', err);
    } finally {
      setLoadingInsight(false);
    }
  }, [config.selectedBrandId, config.daysBack]);

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
        brand_id: config.selectedBrandId || undefined,
        topics: config.selectedTopics.length > 0 ? config.selectedTopics : undefined,
        run_type: scheduleForm.run_type,
        days_back: scheduleForm.days_back,
        schedule_type: scheduleForm.schedule_type,
        schedule_interval: scheduleForm.schedule_interval,
        schedule_unit: scheduleForm.schedule_unit,
        schedule_time: scheduleForm.schedule_type === 'daily' ? scheduleForm.schedule_time : undefined,
      });
      setShowScheduleForm(false);
      setScheduleForm({ name: '', run_type: 'incremental', days_back: 30, schedule_type: 'interval', schedule_interval: 24, schedule_unit: 'hours', schedule_time: '02:00' });
      fetchSchedules();
    } catch (err) {
      console.error('Error creating schedule:', err);
    }
  }, [scheduleForm, config.selectedBrandId, selectedBrand, fetchSchedules]);

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
            {selectedBrand && ` — viewing: ${selectedBrand.display_name}`}
          </p>
        </div>

        <div className="flex items-center gap-2">
          {/* Brand selector */}
          <select
            value={config.selectedBrandId || ''}
            onChange={e => updateConfig({ selectedBrandId: e.target.value ? Number(e.target.value) : null })}
            className="px-3 py-2 text-sm bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg dark:text-gray-100"
          >
            <option value="">All Brands</option>
            {brands.filter(b => b.enabled).map(b => (
              <option key={b.id} value={b.id}>{b.display_name}</option>
            ))}
          </select>

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

      {/* ---- OVERVIEW TAB ---- */}
      {activeTab === 'overview' && (
        <div className="space-y-6">
          {/* Stats cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="p-4 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
              <p className="text-xs text-gray-500 dark:text-gray-400">Articles</p>
              <p className="text-2xl font-bold text-gray-900 dark:text-gray-100">{stats?.total_articles ?? 0}</p>
            </div>
            <div className="p-4 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
              <p className="text-xs text-gray-500 dark:text-gray-400">Brands</p>
              <p className="text-2xl font-bold text-gray-900 dark:text-gray-100">{stats?.total_brands ?? 0}</p>
            </div>
            <div className="p-4 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
              <p className="text-xs text-gray-500 dark:text-gray-400">Top Category</p>
              <p className="text-sm font-semibold text-gray-900 dark:text-gray-100 truncate">
                {stats?.most_active_category ? CATEGORY_SHORT_NAMES[stats.most_active_category] || stats.most_active_category : '—'}
              </p>
            </div>
            <div className="p-4 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
              <p className="text-xs text-gray-500 dark:text-gray-400">Multi-category</p>
              <p className="text-2xl font-bold text-gray-900 dark:text-gray-100">{stats?.multi_category_count ?? 0}</p>
            </div>
          </div>

          {/* Category distribution */}
          {loadingCategories ? (
            <div className="flex justify-center py-8"><Loader2 className="w-6 h-6 animate-spin text-blue-500" /></div>
          ) : categories.length > 0 ? (
            <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
              <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-4">Category Distribution</h3>
              <div className="space-y-3">
                {categories.filter(c => c.article_count > 0).map(cat => (
                  <div key={cat.category} className="flex items-center gap-3">
                    <div className="w-3 h-3 rounded-full flex-shrink-0" style={{ backgroundColor: CATEGORY_COLORS[cat.category] || '#6b7280' }} />
                    <span className="text-sm text-gray-700 dark:text-gray-300 w-48 truncate">{cat.category}</span>
                    <div className="flex-1 h-5 bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden">
                      <div className="h-full rounded-full transition-all" style={{
                        width: `${Math.max(cat.percentage, 2)}%`,
                        backgroundColor: CATEGORY_COLORS[cat.category] || '#6b7280',
                      }} />
                    </div>
                    <span className="text-sm font-medium text-gray-600 dark:text-gray-400 w-16 text-right">
                      {cat.article_count} ({cat.percentage}%)
                    </span>
                    <span className={`text-xs px-1.5 py-0.5 rounded ${
                      cat.recent_trend === 'up' ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400' :
                      cat.recent_trend === 'down' ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400' :
                      'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400'
                    }`}>
                      {cat.recent_trend === 'up' ? '↑' : cat.recent_trend === 'down' ? '↓' : '—'}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="text-center py-12 text-gray-500 dark:text-gray-400">
              <Target className="w-12 h-12 mx-auto mb-3 opacity-30" />
              <p>No classified articles yet.</p>
              <p className="text-sm mt-1">Add brands and run classification to get started.</p>
            </div>
          )}

          {/* Temporal trends (simple monthly chart) */}
          {temporalData.length > 0 && (
            <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
              <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-4">Monthly Article Volume</h3>
              <div className="flex items-end gap-1" style={{ height: '128px' }}>
                {temporalData.slice(-12).map(d => {
                  const maxTotal = Math.max(...temporalData.slice(-12).map(t => t.total), 1);
                  const barHeight = Math.max((d.total / maxTotal) * 100, 4);
                  return (
                    <div key={d.month} className="flex-1 flex flex-col items-center justify-end" style={{ height: '100%' }} title={`${d.month}: ${d.total} articles`}>
                      <span className="text-[10px] text-gray-600 dark:text-gray-400 mb-1">{d.total}</span>
                      <div className="w-full bg-blue-500 rounded-t" style={{ height: `${barHeight}%` }} />
                      <span className="text-[10px] text-gray-400 mt-1 whitespace-nowrap">{d.month.slice(5)}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ---- ANALYSIS TAB ---- */}
      {activeTab === 'analysis' && (
        <div className="space-y-6">
          {!config.selectedBrandId ? (
            <div className="text-center py-12 text-gray-500 dark:text-gray-400">
              <p>Select a brand above to see detailed analysis.</p>
            </div>
          ) : (
            <>
              {/* Per-brand category breakdown with click for insight */}
              <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
                <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-4">
                  Category Breakdown for {selectedBrand?.display_name}
                </h3>
                <div className="space-y-2">
                  {categories.filter(c => c.article_count > 0).map(cat => (
                    <div key={cat.category}
                      className="flex items-center gap-3 p-2 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-750 cursor-pointer transition-colors"
                      onClick={() => handleCategoryInsight(cat.category)}
                    >
                      <div className="w-3 h-3 rounded-full flex-shrink-0" style={{ backgroundColor: CATEGORY_COLORS[cat.category] || '#6b7280' }} />
                      <span className="text-sm text-gray-700 dark:text-gray-300 flex-1">{cat.category}</span>
                      <span className="text-sm font-medium text-gray-600 dark:text-gray-400">
                        {cat.article_count} ({cat.percentage}%)
                      </span>
                      <ChevronRight className="w-4 h-4 text-gray-400" />
                    </div>
                  ))}
                </div>
              </div>

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
                    <button onClick={() => setCategoryInsight(null)} className="text-gray-400 hover:text-gray-600"><X className="w-4 h-4" /></button>
                  </div>
                  <p className="text-sm text-gray-600 dark:text-gray-300 whitespace-pre-wrap">{categoryInsight.insight}</p>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* ---- COMPARISON TAB ---- */}
      {activeTab === 'comparison' && (
        <div className="space-y-6">
          {/* Share of Voice */}
          {shareOfVoice.length > 0 && (
            <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
              <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-4">Share of Voice</h3>
              <div className="space-y-3">
                {shareOfVoice.map(sov => (
                  <div key={sov.brand_id} className="flex items-center gap-3">
                    <div className="w-3 h-3 rounded-full flex-shrink-0" style={{ backgroundColor: sov.color || '#6b7280' }} />
                    <span className="text-sm text-gray-700 dark:text-gray-300 w-32 truncate">{sov.brand_name}</span>
                    <div className="flex-1 h-5 bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden">
                      <div className="h-full rounded-full" style={{
                        width: `${Math.max(sov.percentage, 2)}%`,
                        backgroundColor: sov.color || '#6b7280',
                      }} />
                    </div>
                    <span className="text-sm font-medium text-gray-600 dark:text-gray-400 w-24 text-right">
                      {sov.mention_count} ({sov.percentage}%)
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

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
                      <th key={cat} className="text-right py-2 px-1 text-gray-500 dark:text-gray-400 text-xs">
                        {CATEGORY_SHORT_NAMES[cat]}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {comparison.map(comp => (
                    <tr key={comp.brand_id} className="border-b border-gray-100 dark:border-gray-700/50">
                      <td className="py-2 px-2 font-medium text-gray-700 dark:text-gray-300">{comp.brand_name}</td>
                      <td className="py-2 px-2 text-right font-bold text-gray-700 dark:text-gray-300">{comp.total_articles}</td>
                      {Object.keys(CATEGORY_SHORT_NAMES).map(cat => (
                        <td key={cat} className="py-2 px-1 text-right text-gray-600 dark:text-gray-400">
                          {comp.category_breakdown[cat] || 0}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
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
      {activeTab === 'insights' && (
        <div className="space-y-6">
          {!config.selectedBrandId ? (
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

              {/* Generate / Regenerate button */}
              <button
                onClick={handleGenerateNarrative}
                disabled={generatingNarrative}
                className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
              >
                {generatingNarrative ? <Loader2 className="w-4 h-4 animate-spin" /> : <FileText className="w-4 h-4" />}
                {narrative ? 'Regenerate Narrative' : 'Generate Narrative'}
              </button>

              {/* Narrative display */}
              {loadingNarrative && (
                <div className="flex justify-center py-8"><Loader2 className="w-6 h-6 animate-spin text-blue-500" /></div>
              )}
              {narrative && !loadingNarrative && (
                <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300">
                      Brand Intelligence Report — {narrative.brand_name || selectedBrand?.display_name}
                    </h3>
                    <span className="text-xs text-gray-400">{narrative.generated_at ? new Date(narrative.generated_at).toLocaleString() : ''}</span>
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
      {activeTab === 'articles' && (
        <div className="space-y-4">
          {/* Category filter chips */}
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
                  onClick={() => onArticleClick?.({ uri: article.uri, title: article.title })}
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
                      <span key={cat} className="text-xs px-2 py-0.5 rounded" style={{
                        backgroundColor: (CATEGORY_COLORS[cat] || '#6b7280') + '20',
                        color: CATEGORY_COLORS[cat] || '#6b7280',
                      }}>
                        {CATEGORY_SHORT_NAMES[cat] || cat}
                      </span>
                    ))}
                    {article.matched_keywords?.length > 0 && (
                      <span className="text-xs px-2 py-0.5 bg-yellow-50 dark:bg-yellow-900/20 text-yellow-700 dark:text-yellow-400 rounded border border-yellow-200 dark:border-yellow-800">
                        Matched: {article.matched_keywords.join(', ')}
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

              {/* Pagination */}
              {totalPages > 1 && (
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
                {config.selectedBrandId ? ` Targeting: ${selectedBrand?.display_name}` : ' Targeting: All brands'}
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

// Simple markdown to HTML converter for narratives
function markdownToHtml(md: string): string {
  if (!md) return '';
  return md
    .replace(/^## (.+)$/gm, '<h2 class="text-lg font-semibold mt-6 mb-2">$1</h2>')
    .replace(/^### (.+)$/gm, '<h3 class="text-base font-semibold mt-4 mb-2">$1</h3>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/^- (.+)$/gm, '<li class="ml-4 list-disc">$1</li>')
    .replace(/\n\n/g, '</p><p class="mt-2">')
    .replace(/\n/g, '<br />');
}
