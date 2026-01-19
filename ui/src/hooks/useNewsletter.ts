/**
 * Newsletter Generator Hook
 * Manages newsletter generation, editing, and article management
 */

import { useState, useCallback, useRef } from 'react';
import { extractErrorMessage } from '../services/api';

export interface NewsletterArticle {
  id: string;
  uri: string;
  title: string;
  source: string;
  date: string;
  summary: string;
  url?: string;
  selected: boolean;
  annotation?: string;
  category?: string;
}

export interface NewsletterSection {
  id: string;
  name: string;
  articles: NewsletterArticle[];
}

export interface NewsletterConfig {
  topic: string;
  days_back: number;
  start_date?: string;
  end_date?: string;
  deep_dive_topic?: string;
  model?: string;
}

export interface NewsletterResult {
  newsletter: string;
  article_count: number;
  articles_used: number;
  section_counts: Record<string, number>;
  metatrends?: Array<{ theme: string; count: number; examples: string[] }>;
  deep_dive_topic?: string;
  articles?: NewsletterArticle[];
}

export type NewsletterStage = 'idle' | 'fetching' | 'categorizing' | 'generating' | 'complete' | 'error';

export const NEWSLETTER_STAGES = [
  { name: 'fetching', label: 'Fetching Articles', description: 'Gathering articles from database' },
  { name: 'categorizing', label: 'Categorizing', description: 'Sorting by section and quality' },
  { name: 'generating', label: 'Generating', description: 'Creating newsletter content' },
  { name: 'complete', label: 'Complete', description: 'Newsletter ready' },
];

export function useNewsletter() {
  // Generation state
  const [isGenerating, setIsGenerating] = useState(false);
  const [currentStage, setCurrentStage] = useState<NewsletterStage>('idle');
  const [stageProgress, setStageProgress] = useState(0);
  const [overallProgress, setOverallProgress] = useState(0);

  // Content state
  const [newsletterContent, setNewsletterContent] = useState('');
  const [editedContent, setEditedContent] = useState('');
  const [isEditing, setIsEditing] = useState(false);

  // Articles state
  const [availableArticles, setAvailableArticles] = useState<NewsletterArticle[]>([]);
  const [selectedArticles, setSelectedArticles] = useState<NewsletterArticle[]>([]);

  // Result and error state
  const [result, setResult] = useState<NewsletterResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Stats
  const [articlesFetched, setArticlesFetched] = useState(0);
  const [articlesCategorized, setArticlesCategorized] = useState(0);

  // Abort controller for cancellation
  const abortControllerRef = useRef<AbortController | null>(null);

  const startGeneration = useCallback(async (config: NewsletterConfig) => {
    // Cancel any existing generation
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    abortControllerRef.current = new AbortController();

    setIsGenerating(true);
    setCurrentStage('fetching');
    setStageProgress(0);
    setOverallProgress(0);
    setError(null);
    setNewsletterContent('');
    setEditedContent('');
    setIsEditing(false);
    setArticlesFetched(0);
    setArticlesCategorized(0);

    try {
      console.log('📰 Starting newsletter generation with config:', config);
      const response = await fetch('/api/newsletter/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(config),
        signal: abortControllerRef.current.signal,
      });

      console.log('📰 Response status:', response.status);
      if (!response.ok) {
        const text = await response.text();
        console.error('📰 Error response:', text);
        throw new Error(`Generation failed: ${response.status}`);
      }

      const reader = response.body?.getReader();
      if (!reader) throw new Error('No response stream');

      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) {
          console.log('📰 SSE stream ended');
          break;
        }

        buffer += decoder.decode(value, { stream: true });
        console.log('📰 Received chunk:', buffer.slice(-200));
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              console.log('📰 SSE event:', data);
              handleSSEEvent(data);
            } catch (e) {
              console.warn('Failed to parse SSE event:', e, line);
            }
          }
        }
      }
    } catch (err: any) {
      if (err.name === 'AbortError') {
        console.log('Newsletter generation cancelled');
      } else {
        console.error('Newsletter generation error:', err);
        setError(err.message || 'Generation failed');
        setCurrentStage('error');
      }
    } finally {
      setIsGenerating(false);
    }
  }, []);

  const handleSSEEvent = useCallback((data: any) => {
    const { stage, status, progress } = data;

    if (stage === 'fetching') {
      setCurrentStage('fetching');
      setStageProgress(progress || 0);
      setOverallProgress(progress * 0.3 || 0);
      if (data.articles_found) {
        setArticlesFetched(data.articles_found);
      }
    } else if (stage === 'categorizing') {
      setCurrentStage('categorizing');
      setStageProgress(progress || 0);
      setOverallProgress(0.3 + progress * 0.2 || 0.3);
      if (data.categorized_count) {
        setArticlesCategorized(data.categorized_count);
      }
    } else if (stage === 'generating') {
      setCurrentStage('generating');
      setStageProgress(progress || 0);
      setOverallProgress(0.5 + progress * 0.5 || 0.5);
      if (data.chunk) {
        setNewsletterContent(prev => prev + data.chunk);
        setEditedContent(prev => prev + data.chunk);
      }
    } else if (stage === 'complete') {
      setCurrentStage('complete');
      setStageProgress(1);
      setOverallProgress(1);

      if (data.newsletter) {
        setNewsletterContent(data.newsletter);
        setEditedContent(data.newsletter);
      }

      if (data.articles) {
        const articlesWithSelection = data.articles.map((a: any) => ({
          ...a,
          selected: false,
        }));
        setAvailableArticles(articlesWithSelection);
      }

      setResult({
        newsletter: data.newsletter || '',
        article_count: data.article_count || 0,
        articles_used: data.articles_used || 0,
        section_counts: data.section_counts || {},
        metatrends: data.metatrends,
        deep_dive_topic: data.deep_dive_topic,
        articles: data.articles,
      });
    } else if (status === 'error') {
      setError(extractErrorMessage(data.error, 'Generation failed'));
      setCurrentStage('error');
    }
  }, []);

  const cancelGeneration = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    setIsGenerating(false);
    setCurrentStage('idle');
  }, []);

  const startEditing = useCallback(() => {
    setIsEditing(true);
  }, []);

  const saveEdits = useCallback(() => {
    setNewsletterContent(editedContent);
    setIsEditing(false);
  }, [editedContent]);

  const discardEdits = useCallback(() => {
    setEditedContent(newsletterContent);
    setIsEditing(false);
  }, [newsletterContent]);

  const updateEditedContent = useCallback((content: string) => {
    setEditedContent(content);
  }, []);

  // Article management
  const toggleArticleSelection = useCallback((articleId: string) => {
    setAvailableArticles(prev =>
      prev.map(a =>
        a.id === articleId ? { ...a, selected: !a.selected } : a
      )
    );
  }, []);

  const updateArticleAnnotation = useCallback((articleId: string, annotation: string) => {
    setAvailableArticles(prev =>
      prev.map(a =>
        a.id === articleId ? { ...a, annotation } : a
      )
    );
  }, []);

  const addSelectedToNewsletter = useCallback(() => {
    const selected = availableArticles.filter(a => a.selected);
    if (selected.length === 0) return;

    // Build markdown for selected articles
    const articlesMarkdown = selected.map(a => {
      let md = `\n### ${a.title}\n`;
      md += `*${a.source}* | ${a.date}\n\n`;
      if (a.summary) md += `${a.summary}\n\n`;
      if (a.annotation) md += `> **Editor's Note:** ${a.annotation}\n\n`;
      if (a.url || a.uri) md += `[Read more](${a.url || a.uri})\n`;
      return md;
    }).join('\n---\n');

    // Append to edited content
    const newContent = editedContent + '\n\n## Additional Selected Articles\n' + articlesMarkdown;
    setEditedContent(newContent);

    // Clear selections
    setAvailableArticles(prev => prev.map(a => ({ ...a, selected: false })));
  }, [availableArticles, editedContent]);

  const clearResults = useCallback(() => {
    setNewsletterContent('');
    setEditedContent('');
    setIsEditing(false);
    setResult(null);
    setError(null);
    setCurrentStage('idle');
    setAvailableArticles([]);
    setArticlesFetched(0);
    setArticlesCategorized(0);
  }, []);

  const clearError = useCallback(() => {
    setError(null);
  }, []);

  // Load content from a saved newsletter
  const loadContent = useCallback((content: string, loadedResult?: any) => {
    setNewsletterContent(content);
    setEditedContent(content);
    setIsEditing(false);
    if (loadedResult) {
      setResult(loadedResult);
    }
    setError(null);
    setCurrentStage('complete');
  }, []);

  return {
    // Generation state
    isGenerating,
    currentStage,
    stageProgress,
    overallProgress,

    // Content
    newsletterContent,
    editedContent,
    isEditing,

    // Articles
    availableArticles,
    selectedArticles: availableArticles.filter(a => a.selected),

    // Result and error
    result,
    error,

    // Stats
    articlesFetched,
    articlesCategorized,

    // Actions
    startGeneration,
    cancelGeneration,
    startEditing,
    saveEdits,
    discardEdits,
    updateEditedContent,
    toggleArticleSelection,
    updateArticleAnnotation,
    addSelectedToNewsletter,
    clearResults,
    clearError,
    loadContent,
  };
}
