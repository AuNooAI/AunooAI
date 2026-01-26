/**
 * Submit Articles App - React replacement for submit_article.html
 * Allows users to submit articles for AI analysis/enrichment via URL or pasted content
 */

import { useState, useEffect } from 'react';
import { SharedNavigation } from './components/SharedNavigation';
import { NotificationBell } from './components/gather/NotificationBell';
import { OnboardingWizard } from './components/onboarding/OnboardingWizard';
import { AuspexChat } from './components/auspex';
import { Button } from './components/ui/button';
import { Input } from './components/ui/input';
import { Label } from './components/ui/label';
import { Textarea } from './components/ui/textarea';
import { Checkbox } from './components/ui/checkbox';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from './components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from './components/ui/tabs';
import { Alert, AlertDescription } from './components/ui/alert';
import { Card, CardContent, CardHeader, CardTitle } from './components/ui/card';
import { Loader2, Plus, Link as LinkIcon, FileText, AlertCircle, ExternalLink, Trash2, Pencil, X, Save } from 'lucide-react';
import './components/gather/gather.css';

// Types
interface Topic {
  name: string;
  description?: string;
}

interface AIModel {
  name: string;
  provider: string;
}

interface AnalysisResult {
  uri: string;
  title: string;
  summary: string;
  news_source: string;
  publication_date?: string;
  category?: string;
  sentiment?: string;
  sentiment_explanation?: string;
  future_signal?: string;
  future_signal_explanation?: string;
  time_to_impact?: string;
  time_to_impact_explanation?: string;
  driver_type?: string;
  driver_type_explanation?: string;
  tags?: string[];
  bias?: string;
  factual_reporting?: string;
  mbfc_credibility_rating?: string;
  bias_country?: string;
  media_type?: string;
  popularity?: string;
  topic?: string;
  analyzed?: boolean;
}

interface RecentArticle {
  uri: string;
  title: string;
  summary?: string;
  news_source?: string;
  publication_date?: string;
  submission_date?: string;
  category?: string;
  sentiment?: string;
  future_signal?: string;
  time_to_impact?: string;
  driver_type?: string;
  tags?: string[];
  topic?: string;
  bias?: string;
  factual_reporting?: string;
}

interface DropdownOptions {
  categories: string[];
  sentiments: string[];
  futureSignals: string[];
  timeToImpacts: string[];
  driverTypes: string[];
}

// Parse tags from string or array format
function parseTags(tags: string | string[] | undefined): string[] {
  if (!tags) return [];
  if (Array.isArray(tags)) return tags;
  return tags.split(',').map(t => t.trim()).filter(t => t);
}

// Format error message consistently
function formatErrorMessage(err: unknown, prefix: string): string {
  const message = err instanceof Error ? err.message : 'Unknown error';
  return `${prefix}: ${message}`;
}

// Voice presets
const VOICE_PRESETS = [
  { value: 'business_analyst', label: 'Business Analyst' },
  { value: 'industry_analyst', label: 'Industry Analyst' },
  { value: 'tech_journalist', label: 'Tech Journalist' },
  { value: 'investment_advisor', label: 'Investment Advisor' },
  { value: 'principal_security_engineer', label: 'Principal Security Engineer' },
  { value: 'ciso', label: 'CISO' },
  { value: 'custom', label: 'Custom' },
];

// Summary length options
const SUMMARY_LENGTHS = [
  { value: '40', label: '40 words' },
  { value: '50', label: '50 words' },
  { value: '75', label: '75 words' },
  { value: '100', label: '100 words' },
  { value: 'custom', label: 'Custom' },
];

function SubmitArticlesApp() {
  // State for configuration
  const [topics, setTopics] = useState<Topic[]>([]);
  const [models, setModels] = useState<AIModel[]>([]);
  const [selectedTopic, setSelectedTopic] = useState('');
  const [selectedModel, setSelectedModel] = useState('');
  const [summaryLength, setSummaryLength] = useState('50');
  const [customSummaryLength, setCustomSummaryLength] = useState('');
  const [summaryVoice, setSummaryVoice] = useState('business_analyst');
  const [customVoice, setCustomVoice] = useState('');

  // State for URL tab
  const [urlList, setUrlList] = useState('');

  // State for paste content tab
  const [articleTitle, setArticleTitle] = useState('');
  const [articleSource, setArticleSource] = useState('');
  const [publicationDate, setPublicationDate] = useState('');
  const [sourceUrl, setSourceUrl] = useState('');
  const [pasteContent, setPasteContent] = useState('');

  // State for analysis results
  const [analysisResults, setAnalysisResults] = useState<AnalysisResult[]>([]);
  const [singleResult, setSingleResult] = useState<AnalysisResult | null>(null);
  const [promoteToIncident, setPromoteToIncident] = useState(false);
  const [bulkPromoteToIncident, setBulkPromoteToIncident] = useState(false);

  // State for dropdown options
  const [categories, setCategories] = useState<string[]>([]);
  const [sentiments, setSentiments] = useState<string[]>([]);
  const [futureSignals, setFutureSignals] = useState<string[]>([]);
  const [timeToImpacts, setTimeToImpacts] = useState<string[]>([]);
  const [driverTypes, setDriverTypes] = useState<string[]>([]);

  // State for recent articles
  const [recentArticles, setRecentArticles] = useState<RecentArticle[]>([]);

  // UI state
  const [loading, setLoading] = useState(true);
  const [analyzing, setAnalyzing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [isOnboardingOpen, setIsOnboardingOpen] = useState(false);
  const [activeTab, setActiveTab] = useState('url');

  // Load initial data
  useEffect(() => {
    Promise.all([
      fetchTopics(),
      fetchModels(),
      fetchDropdownOptions(),
      fetchRecentArticles(),
    ]).finally(() => setLoading(false));

    // Handle URL parameters for pre-population
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('url')) {
      setUrlList(urlParams.get('url') || '');
    }
    if (urlParams.get('topic')) {
      setTimeout(() => setSelectedTopic(urlParams.get('topic') || ''), 500);
    }
    if (urlParams.get('title')) {
      setArticleTitle(decodeURIComponent(urlParams.get('title') || ''));
    }
    if (urlParams.get('source')) {
      setArticleSource(decodeURIComponent(urlParams.get('source') || ''));
    }
    if (urlParams.get('publication_date')) {
      const dateStr = urlParams.get('publication_date') || '';
      const match = dateStr.match(/(\d{4}-\d{2}-\d{2})/);
      if (match) setPublicationDate(match[1]);
    }
  }, []);

  const fetchTopics = async () => {
    try {
      const response = await fetch('/api/topics');
      const data = await response.json();
      setTopics(data);
    } catch (err) {
      console.error('Error loading topics:', err);
    }
  };

  const fetchModels = async () => {
    try {
      const response = await fetch('/api/available_models');
      const data = await response.json();
      setModels(data);
    } catch (err) {
      console.error('Error loading models:', err);
    }
  };

  const fetchDropdownOptions = async () => {
    try {
      const [categoriesRes, sentimentsRes, futureSignalsRes, timeToImpactRes, driverTypesRes] = await Promise.all([
        fetch('/api/categories'),
        fetch('/api/sentiments'),
        fetch('/api/future_signals'),
        fetch('/api/time_to_impact'),
        fetch('/api/driver_types'),
      ]);
      setCategories(await categoriesRes.json());
      setSentiments(await sentimentsRes.json());
      setFutureSignals(await futureSignalsRes.json());
      setTimeToImpacts(await timeToImpactRes.json());
      setDriverTypes(await driverTypesRes.json());
    } catch (err) {
      console.error('Error loading dropdown options:', err);
    }
  };

  const fetchRecentArticles = async () => {
    try {
      const response = await fetch('/api/enriched_articles?limit=10');
      const data = await response.json();
      setRecentArticles(data || []);
    } catch (err) {
      console.error('Error loading recent articles:', err);
    }
  };

  const getSummaryLengthValue = () => {
    return summaryLength === 'custom' ? customSummaryLength || '50' : summaryLength;
  };

  const getSummaryVoiceValue = () => {
    return summaryVoice === 'custom' ? customVoice || 'business_analyst' : summaryVoice;
  };

  // Handle URL submission (bulk)
  const handleUrlSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccessMessage(null);

    if (!selectedTopic) {
      setError('Please select a topic before analyzing articles');
      return;
    }

    const urls = urlList.split('\n').filter(url => url.trim() !== '');
    if (urls.length === 0) {
      setError('Please enter at least one URL');
      return;
    }

    if (urls.length > 50) {
      setError('Maximum 50 URLs allowed');
      return;
    }

    setAnalyzing(true);
    setAnalysisResults([]);

    try {
      const requestData = {
        urls,
        summaryType: 'curious_ai_long',
        modelName: selectedModel,
        summaryLength: getSummaryLengthValue(),
        summaryVoice: getSummaryVoiceValue(),
        topic: selectedTopic,
      };

      const response = await fetch('/api/bulk-research-stream', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'application/x-ndjson',
        },
        body: JSON.stringify(requestData),
      });

      if (!response.ok || !response.body) {
        throw new Error(`Server error: ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.trim()) continue;
          try {
            const obj = JSON.parse(line);
            setAnalysisResults(prev => [...prev, obj]);
          } catch {
            console.error('Failed to parse NDJSON line', line);
          }
        }
      }

      // Parse any remaining buffer
      if (buffer.trim()) {
        try {
          const obj = JSON.parse(buffer);
          setAnalysisResults(prev => [...prev, obj]);
        } catch {
          console.error('Failed to parse last NDJSON fragment', buffer);
        }
      }
    } catch (err) {
      setError(formatErrorMessage(err, 'Error analyzing articles'));
    } finally {
      setAnalyzing(false);
    }
  };

  // Handle paste content submission
  const handlePasteSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccessMessage(null);

    if (!selectedTopic) {
      setError('Please select a topic before analyzing articles');
      return;
    }

    if (!pasteContent.trim()) {
      setError('Please enter article content');
      return;
    }

    if (!sourceUrl.trim()) {
      setError('Please enter a source URL');
      return;
    }

    setAnalyzing(true);
    setSingleResult(null);

    try {
      const formData = new FormData();
      formData.append('articleUrl', sourceUrl);
      formData.append('articleContent', pasteContent);
      formData.append('selectedTopic', selectedTopic);
      formData.append('modelName', selectedModel);
      formData.append('summaryType', 'curious_ai_long');
      formData.append('summaryVoice', getSummaryVoiceValue());
      formData.append('summaryLength', getSummaryLengthValue());

      const preservedData = {
        title: articleTitle,
        source: articleSource,
        publication_date: publicationDate,
      };
      formData.append('preservedMetadata', JSON.stringify(preservedData));

      const response = await fetch('/research', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(JSON.stringify(errorData));
      }

      const result = await response.json();

      // Apply preserved metadata
      result.title = articleTitle || result.title;
      result.news_source = articleSource || result.news_source;
      result.publication_date = publicationDate || result.publication_date;

      setSingleResult(result);
    } catch (err) {
      setError(formatErrorMessage(err, 'Error analyzing article'));
    } finally {
      setAnalyzing(false);
    }
  };

  // Update analysis result field
  const updateResultField = (index: number, field: keyof AnalysisResult, value: string | string[]) => {
    setAnalysisResults(prev => {
      const updated = [...prev];
      (updated[index] as any)[field] = value;
      return updated;
    });
  };

  // Update single result field
  const updateSingleResultField = (field: keyof AnalysisResult, value: string | string[]) => {
    setSingleResult(prev => prev ? { ...prev, [field]: value } : null);
  };

  // Remove result from bulk list
  const removeResult = (index: number) => {
    setAnalysisResults(prev => prev.filter((_, i) => i !== index));
  };

  // Save single article
  const saveSingleArticle = async () => {
    if (!singleResult) return;
    setSaving(true);
    setError(null);

    try {
      const articleData = {
        ...singleResult,
        topic: selectedTopic,
        tags: parseTags(singleResult.tags),
        submission_date: new Date().toISOString(),
      };

      const response = await fetch('/api/save_article', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(articleData),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to save article');
      }

      // Handle promote to incident
      if (promoteToIncident) {
        await createIncident(singleResult.uri, selectedTopic, articleData);
      }

      setSuccessMessage('Article saved successfully!' + (promoteToIncident ? ' Incident created.' : ''));
      fetchRecentArticles();

      // Clear form
      setSingleResult(null);
      setPasteContent('');
      setArticleTitle('');
      setArticleSource('');
      setPublicationDate('');
      setSourceUrl('');
    } catch (err) {
      setError(formatErrorMessage(err, 'Error saving article'));
    } finally {
      setSaving(false);
    }
  };

  // Save bulk articles
  const saveBulkArticles = async () => {
    if (analysisResults.length === 0) return;
    setSaving(true);
    setError(null);

    try {
      const articles = analysisResults.map(result => ({
        ...result,
        topic: selectedTopic,
        tags: parseTags(result.tags),
        submission_date: new Date().toISOString(),
        analyzed: true,
      }));

      const response = await fetch('/api/save-bulk-articles', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ articles }),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const result = await response.json();

      // Handle promote to incidents
      let incidentsCreated = 0;
      if (bulkPromoteToIncident && result.success?.length > 0) {
        for (const savedArticle of result.success) {
          try {
            await createIncident(savedArticle.uri, selectedTopic, savedArticle);
            incidentsCreated++;
          } catch (err) {
            console.error('Error creating incident:', err);
          }
        }
      }

      const successCount = result.success?.length || 0;
      const incidentMsg = incidentsCreated > 0 ? ` ${incidentsCreated} incident(s) created.` : '';
      setSuccessMessage(`${successCount} of ${articles.length} article(s) saved successfully!${incidentMsg}`);

      // Remove saved articles from list
      if (result.success?.length > 0) {
        const savedUris = new Set(result.success.map((a: any) => a.uri));
        setAnalysisResults(prev => prev.filter(r => !savedUris.has(r.uri)));
      }

      fetchRecentArticles();
    } catch (err) {
      setError(formatErrorMessage(err, 'Error saving articles'));
    } finally {
      setSaving(false);
    }
  };

  // Create incident from article
  const createIncident = async (articleUri: string, topic: string, articleData: any) => {
    const analyzeResponse = await fetch('/api/analyze-article-for-incident', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ article_uri: articleUri, topic }),
    });

    if (analyzeResponse.ok) {
      const analyzeResult = await analyzeResponse.json();
      if (analyzeResult.success && analyzeResult.suggested_incident) {
        const incidentToSave = {
          ...analyzeResult.suggested_incident,
          topic,
          article_uris: [articleUri],
          article_metadata: [{
            uri: articleUri,
            title: articleData.title,
            summary: articleData.summary,
            source: articleData.news_source,
            publication_date: articleData.publication_date,
          }],
        };

        await fetch('/api/news-feed/saved/incidents', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(incidentToSave),
        });
      }
    }
  };

  // Delete recent article
  const deleteRecentArticle = async (uri: string) => {
    if (!confirm('Delete this article?')) return;
    try {
      const response = await fetch(`/api/article?uri=${encodeURIComponent(uri)}`, { method: 'DELETE' });
      if (response.ok) {
        setRecentArticles(prev => prev.filter(a => a.uri !== uri));
      }
    } catch (err) {
      console.error('Error deleting article:', err);
    }
  };

  // Edit recent article (load into form)
  const editRecentArticle = async (uri: string) => {
    try {
      const response = await fetch(`/api/article?uri=${encodeURIComponent(uri)}`);
      if (response.ok) {
        const article = await response.json();
        setSingleResult(article);
        if (article.topic) setSelectedTopic(article.topic);
        setActiveTab('url');
        window.scrollTo({ top: 0, behavior: 'smooth' });
      }
    } catch (err) {
      console.error('Error loading article:', err);
    }
  };

  // Clear form and results
  const clearForm = () => {
    setSingleResult(null);
    setAnalysisResults([]);
    setUrlList('');
    setPasteContent('');
    setArticleTitle('');
    setArticleSource('');
    setPublicationDate('');
    setSourceUrl('');
    setPromoteToIncident(false);
    setBulkPromoteToIncident(false);
    setError(null);
    setSuccessMessage(null);
  };

  // Format date for display
  const formatDate = (dateStr?: string) => {
    if (!dateStr) return 'N/A';
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  // Get sentiment class for badge
  const getSentimentClass = (sentiment?: string): string => {
    if (!sentiment) return 'bg-gray-500';
    const sentimentClasses: Record<string, string> = {
      positive: 'bg-green-500',
      negative: 'bg-red-500',
      neutral: 'bg-gray-500',
    };
    return sentimentClasses[sentiment.toLowerCase()] || 'bg-blue-500';
  };

  if (loading) {
    return (
      <div className="gather-app">
        <div className="gather-layout">
          <SharedNavigation currentPage="gather" />
          <div className="gather-loading">
            <Loader2 className="gather-loading-spinner" />
            <p>Loading Submit Articles...</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="gather-app">
      <div className="gather-layout">
        <SharedNavigation currentPage="gather" />

        <div className="gather-content-area">
          {/* Top Header Bar */}
          <div className="gather-top-bar">
            <div className="gather-top-bar-left">
              <span className="gather-top-bar-title">Gather</span>
              <span className="gather-top-bar-separator">/</span>
              <span className="gather-top-bar-subtitle">Submit Article</span>
              <span className="gather-top-bar-separator">-</span>
              <span className="text-sm text-gray-500 dark:text-gray-400">Analyze and enrich news articles for your topics</span>
            </div>
            <div className="gather-top-bar-right">
              <NotificationBell />
              <button
                className="gather-top-bar-setup-btn"
                onClick={() => setIsOnboardingOpen(true)}
              >
                Set up topic
                <Plus className="w-4 h-4" />
              </button>
            </div>
          </div>

          <main className="gather-main p-6">
            {/* Error/Success Messages */}
            {error && (
              <Alert variant="destructive" className="mb-4">
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
            {successMessage && (
              <Alert className="mb-4 bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800">
                <AlertDescription className="text-green-800 dark:text-green-200">{successMessage}</AlertDescription>
              </Alert>
            )}

            {/* Configuration Card */}
            <Card className="mb-6">
              <CardHeader>
                <CardTitle>Add Article Content</CardTitle>
              </CardHeader>
              <CardContent>
                {/* Configuration Options */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
                  <div className="space-y-2">
                    <Label htmlFor="topic">Topic</Label>
                    <Select value={selectedTopic} onValueChange={setSelectedTopic}>
                      <SelectTrigger id="topic">
                        <SelectValue placeholder="Select a topic" />
                      </SelectTrigger>
                      <SelectContent>
                        {topics.map(topic => (
                          <SelectItem key={topic.name} value={topic.name}>
                            {topic.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="model">AI Model</Label>
                    <Select value={selectedModel} onValueChange={setSelectedModel}>
                      <SelectTrigger id="model">
                        <SelectValue placeholder="Select a model" />
                      </SelectTrigger>
                      <SelectContent>
                        {models.map(model => (
                          <SelectItem key={model.name} value={model.name}>
                            {model.name} ({model.provider})
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="summaryLength">Summary Length</Label>
                    <Select value={summaryLength} onValueChange={setSummaryLength}>
                      <SelectTrigger id="summaryLength">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {SUMMARY_LENGTHS.map(opt => (
                          <SelectItem key={opt.value} value={opt.value}>
                            {opt.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    {summaryLength === 'custom' && (
                      <Input
                        type="number"
                        placeholder="Enter custom length"
                        value={customSummaryLength}
                        onChange={e => setCustomSummaryLength(e.target.value)}
                        className="mt-2"
                      />
                    )}
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="summaryVoice">Summary Voice</Label>
                    <Select value={summaryVoice} onValueChange={setSummaryVoice}>
                      <SelectTrigger id="summaryVoice">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {VOICE_PRESETS.map(opt => (
                          <SelectItem key={opt.value} value={opt.value}>
                            {opt.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    {summaryVoice === 'custom' && (
                      <Input
                        placeholder="Enter custom voice"
                        value={customVoice}
                        onChange={e => setCustomVoice(e.target.value)}
                        className="mt-2"
                      />
                    )}
                  </div>
                </div>

                {/* Input Tabs */}
                <Tabs value={activeTab} onValueChange={setActiveTab}>
                  <TabsList className="mb-4">
                    <TabsTrigger value="url" className="flex items-center gap-2">
                      <LinkIcon className="w-4 h-4" />
                      URL
                    </TabsTrigger>
                    <TabsTrigger value="paste" className="flex items-center gap-2">
                      <FileText className="w-4 h-4" />
                      Paste Content
                    </TabsTrigger>
                  </TabsList>

                  {/* URL Tab */}
                  <TabsContent value="url">
                    <form onSubmit={handleUrlSubmit}>
                      <div className="space-y-4">
                        <div className="space-y-2">
                          <Label htmlFor="urlList">Enter one or more URLs (one per line, maximum 50)</Label>
                          <Textarea
                            id="urlList"
                            rows={5}
                            placeholder="https://example.com/article1
https://example.com/article2
https://example.com/article3"
                            value={urlList}
                            onChange={e => setUrlList(e.target.value)}
                          />
                        </div>
                        <Button type="submit" disabled={analyzing}>
                          {analyzing ? (
                            <>
                              <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                              Analyzing...
                            </>
                          ) : (
                            'Analyze Articles'
                          )}
                        </Button>
                      </div>
                    </form>
                  </TabsContent>

                  {/* Paste Content Tab */}
                  <TabsContent value="paste">
                    <form onSubmit={handlePasteSubmit}>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
                        <div className="space-y-2">
                          <Label htmlFor="articleTitle">Article Title</Label>
                          <Input
                            id="articleTitle"
                            placeholder="Enter article title"
                            value={articleTitle}
                            onChange={e => setArticleTitle(e.target.value)}
                            required
                          />
                        </div>
                        <div className="space-y-2">
                          <Label htmlFor="articleSource">Article Source</Label>
                          <Input
                            id="articleSource"
                            placeholder="e.g., The New York Times"
                            value={articleSource}
                            onChange={e => setArticleSource(e.target.value)}
                            required
                          />
                        </div>
                        <div className="space-y-2">
                          <Label htmlFor="publicationDate">Publication Date</Label>
                          <Input
                            id="publicationDate"
                            type="date"
                            value={publicationDate}
                            onChange={e => setPublicationDate(e.target.value)}
                          />
                        </div>
                        <div className="space-y-2">
                          <Label htmlFor="sourceUrl">Source URL</Label>
                          <Input
                            id="sourceUrl"
                            type="url"
                            placeholder="https://example.com/article"
                            value={sourceUrl}
                            onChange={e => setSourceUrl(e.target.value)}
                            required
                          />
                        </div>
                      </div>
                      <div className="space-y-2 mb-4">
                        <Label htmlFor="pasteContent">Article Content</Label>
                        <Textarea
                          id="pasteContent"
                          rows={10}
                          placeholder="Paste the full article content here..."
                          value={pasteContent}
                          onChange={e => setPasteContent(e.target.value)}
                          required
                        />
                      </div>
                      <Button type="submit" disabled={analyzing}>
                        {analyzing ? (
                          <>
                            <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                            Analyzing...
                          </>
                        ) : (
                          'Analyze Article'
                        )}
                      </Button>
                    </form>
                  </TabsContent>
                </Tabs>
              </CardContent>
            </Card>

            {/* Bulk Analysis Results */}
            {analysisResults.length > 0 && (
              <Card className="mb-6">
                <CardHeader>
                  <CardTitle>Analysis Results ({analysisResults.length} articles)</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-6">
                    {analysisResults.map((result, index) => (
                      <ArticleResultCard
                        key={`${result.uri}-${index}`}
                        result={result}
                        index={index}
                        options={{ categories, sentiments, futureSignals, timeToImpacts, driverTypes }}
                        onUpdate={updateResultField}
                        onRemove={removeResult}
                      />
                    ))}
                  </div>

                  <div className="mt-6 flex items-center gap-4">
                    <div className="flex items-center space-x-2">
                      <Checkbox
                        id="bulkPromoteToIncident"
                        checked={bulkPromoteToIncident}
                        onCheckedChange={(checked) => setBulkPromoteToIncident(checked === true)}
                      />
                      <Label htmlFor="bulkPromoteToIncident" className="font-medium">
                        Promote to Incidents - Also create incidents from these articles
                      </Label>
                    </div>
                  </div>

                  <div className="mt-4 flex gap-2">
                    <Button onClick={saveBulkArticles} disabled={saving}>
                      {saving ? (
                        <>
                          <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                          Saving...
                        </>
                      ) : (
                        <>
                          <Save className="w-4 h-4 mr-2" />
                          Save All Articles
                        </>
                      )}
                    </Button>
                    <Button variant="outline" onClick={() => setAnalysisResults([])}>
                      <X className="w-4 h-4 mr-2" />
                      Clear Results
                    </Button>
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Single Analysis Result */}
            {singleResult && (
              <Card className="mb-6">
                <CardHeader>
                  <CardTitle>Analysis Result</CardTitle>
                </CardHeader>
                <CardContent>
                  <SingleArticleResultCard
                    result={singleResult}
                    options={{ categories, sentiments, futureSignals, timeToImpacts, driverTypes }}
                    onUpdate={updateSingleResultField}
                  />

                  <div className="mt-6 flex items-center gap-4">
                    <div className="flex items-center space-x-2">
                      <Checkbox
                        id="promoteToIncident"
                        checked={promoteToIncident}
                        onCheckedChange={(checked) => setPromoteToIncident(checked === true)}
                      />
                      <Label htmlFor="promoteToIncident" className="font-medium">
                        Promote to Incident - Also create an incident from this article
                      </Label>
                    </div>
                  </div>

                  <div className="mt-4 flex gap-2">
                    <Button onClick={saveSingleArticle} disabled={saving}>
                      {saving ? (
                        <>
                          <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                          Saving...
                        </>
                      ) : (
                        <>
                          <Save className="w-4 h-4 mr-2" />
                          Save Article
                        </>
                      )}
                    </Button>
                    <Button variant="outline" onClick={() => setSingleResult(null)}>
                      <X className="w-4 h-4 mr-2" />
                      Clear
                    </Button>
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Recently Enriched Articles */}
            <Card>
              <CardHeader>
                <CardTitle>Recently Enriched Articles</CardTitle>
              </CardHeader>
              <CardContent>
                {recentArticles.length === 0 ? (
                  <p className="text-gray-500 dark:text-gray-400 text-center py-4">No enriched articles found</p>
                ) : (
                  <div className="space-y-4">
                    {recentArticles.map(article => (
                      <div
                        key={article.uri}
                        className="border border-gray-200 dark:border-gray-700 rounded-lg p-4"
                      >
                        <div className="flex justify-between items-start">
                          <div className="flex-1">
                            <a
                              href={article.uri}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-pink-600 hover:text-pink-700 font-medium flex items-center gap-1"
                            >
                              {article.title || 'Untitled'}
                              <ExternalLink className="w-3 h-3" />
                            </a>
                            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                              Source: {article.news_source || 'Unknown'}
                            </p>
                            {article.summary && (
                              <p className="text-sm mt-2">{article.summary}</p>
                            )}
                            <div className="flex flex-wrap gap-1 mt-2">
                              {article.category && (
                                <span className="px-2 py-0.5 text-xs rounded-full bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300">
                                  {article.category}
                                </span>
                              )}
                              {article.sentiment && (
                                <span className={`px-2 py-0.5 text-xs rounded-full text-white ${getSentimentClass(article.sentiment)}`}>
                                  {article.sentiment}
                                </span>
                              )}
                              {article.future_signal && (
                                <span className="px-2 py-0.5 text-xs rounded-full bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300">
                                  {article.future_signal}
                                </span>
                              )}
                            </div>
                            <p className="text-xs text-gray-400 mt-2">
                              Added: {formatDate(article.submission_date)}
                            </p>
                          </div>
                          <div className="flex gap-2 ml-4">
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => editRecentArticle(article.uri)}
                            >
                              <Pencil className="w-4 h-4" />
                            </Button>
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => deleteRecentArticle(article.uri)}
                            >
                              <Trash2 className="w-4 h-4 text-red-500" />
                            </Button>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </main>
        </div>
      </div>

      <OnboardingWizard
        open={isOnboardingOpen}
        onOpenChange={setIsOnboardingOpen}
      />
      <AuspexChat />
    </div>
  );
}

// Single Article Result Card Component
interface SingleArticleResultCardProps {
  result: AnalysisResult;
  options: DropdownOptions;
  onUpdate: (field: keyof AnalysisResult, value: string | string[]) => void;
}

function SingleArticleResultCard({
  result,
  options,
  onUpdate,
}: SingleArticleResultCardProps) {
  const { categories, sentiments, futureSignals, timeToImpacts, driverTypes } = options;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label>Title</Label>
          <Input
            value={result.title || ''}
            onChange={e => onUpdate('title', e.target.value)}
          />
        </div>
        <div className="space-y-2">
          <Label>Source</Label>
          <Input
            value={result.news_source || ''}
            onChange={e => onUpdate('news_source', e.target.value)}
          />
        </div>
      </div>

      <div className="space-y-2">
        <Label>URL</Label>
        <a href={result.uri} target="_blank" rel="noopener noreferrer" className="text-pink-600 hover:text-pink-700 flex items-center gap-1">
          {result.uri}
          <ExternalLink className="w-3 h-3" />
        </a>
      </div>

      {/* Media Bias Info */}
      {(result.bias || result.factual_reporting) && (
        <div className="space-y-2">
          <Label>Media Bias / Factual Reporting</Label>
          <div className="flex flex-wrap gap-2">
            {result.bias && (
              <span className="px-2 py-1 text-sm rounded bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300">
                {result.bias}
              </span>
            )}
            {result.factual_reporting && (
              <span className="px-2 py-1 text-sm rounded bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300">
                {result.factual_reporting}
              </span>
            )}
            {result.mbfc_credibility_rating && (
              <span className="px-2 py-1 text-sm rounded border border-gray-300 dark:border-gray-600">
                {result.mbfc_credibility_rating}
              </span>
            )}
          </div>
        </div>
      )}

      <div className="space-y-2">
        <Label>Summary</Label>
        <Textarea
          rows={4}
          value={result.summary || ''}
          onChange={e => onUpdate('summary', e.target.value)}
        />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label>Category</Label>
          <Select value={result.category || ''} onValueChange={v => onUpdate('category', v)}>
            <SelectTrigger>
              <SelectValue placeholder="Select category" />
            </SelectTrigger>
            <SelectContent>
              {categories.map(cat => (
                <SelectItem key={cat} value={cat}>{cat}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-2">
          <Label>Sentiment</Label>
          <Select value={result.sentiment || ''} onValueChange={v => onUpdate('sentiment', v)}>
            <SelectTrigger>
              <SelectValue placeholder="Select sentiment" />
            </SelectTrigger>
            <SelectContent>
              {sentiments.map(s => (
                <SelectItem key={s} value={s}>{s}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="space-y-2">
        <Label>Sentiment Explanation</Label>
        <Textarea
          rows={2}
          value={result.sentiment_explanation || ''}
          onChange={e => onUpdate('sentiment_explanation', e.target.value)}
        />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label>Future Signal</Label>
          <Select value={result.future_signal || ''} onValueChange={v => onUpdate('future_signal', v)}>
            <SelectTrigger>
              <SelectValue placeholder="Select future signal" />
            </SelectTrigger>
            <SelectContent>
              {futureSignals.map(fs => (
                <SelectItem key={fs} value={fs}>{fs}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-2">
          <Label>Time to Impact</Label>
          <Select value={result.time_to_impact || ''} onValueChange={v => onUpdate('time_to_impact', v)}>
            <SelectTrigger>
              <SelectValue placeholder="Select time to impact" />
            </SelectTrigger>
            <SelectContent>
              {timeToImpacts.map(tti => (
                <SelectItem key={tti} value={tti}>{tti}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label>Future Signal Explanation</Label>
          <Textarea
            rows={2}
            value={result.future_signal_explanation || ''}
            onChange={e => onUpdate('future_signal_explanation', e.target.value)}
          />
        </div>
        <div className="space-y-2">
          <Label>Time to Impact Explanation</Label>
          <Textarea
            rows={2}
            value={result.time_to_impact_explanation || ''}
            onChange={e => onUpdate('time_to_impact_explanation', e.target.value)}
          />
        </div>
      </div>

      <div className="space-y-2">
        <Label>Driver Type</Label>
        <Select value={result.driver_type || ''} onValueChange={v => onUpdate('driver_type', v)}>
          <SelectTrigger>
            <SelectValue placeholder="Select driver type" />
          </SelectTrigger>
          <SelectContent>
            {driverTypes.map(dt => (
              <SelectItem key={dt} value={dt}>{dt}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="space-y-2">
        <Label>Driver Type Explanation</Label>
        <Textarea
          rows={2}
          value={result.driver_type_explanation || ''}
          onChange={e => onUpdate('driver_type_explanation', e.target.value)}
        />
      </div>

      <div className="space-y-2">
        <Label>Tags (comma-separated)</Label>
        <Input
          value={Array.isArray(result.tags) ? result.tags.join(', ') : result.tags || ''}
          onChange={e => onUpdate('tags', e.target.value)}
        />
      </div>
    </div>
  );
}

// Article Result Card Component (for bulk results)
interface ArticleResultCardProps {
  result: AnalysisResult;
  index: number;
  options: DropdownOptions;
  onUpdate: (index: number, field: keyof AnalysisResult, value: string | string[]) => void;
  onRemove: (index: number) => void;
}

function ArticleResultCard({
  result,
  index,
  options,
  onUpdate,
  onRemove,
}: ArticleResultCardProps) {
  const [isExpanded, setIsExpanded] = useState(true);

  return (
    <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4">
      <div className="flex justify-between items-start mb-4">
        <div className="flex-1">
          <button
            type="button"
            className="text-left w-full"
            onClick={() => setIsExpanded(!isExpanded)}
          >
            <h4 className="font-medium text-lg">{result.title || 'Untitled Article'}</h4>
            <p className="text-sm text-gray-500 truncate">{result.uri}</p>
          </button>
        </div>
        <Button variant="ghost" size="sm" onClick={() => onRemove(index)}>
          <Trash2 className="w-4 h-4 text-red-500" />
        </Button>
      </div>

      {isExpanded && (
        <SingleArticleResultCard
          result={result}
          options={options}
          onUpdate={(field, value) => onUpdate(index, field, value)}
        />
      )}
    </div>
  );
}

export default SubmitArticlesApp;
