import { useState, useEffect, useCallback, useRef } from 'react';
import { X, ChevronLeft, ChevronRight, ChevronsUp, Loader2, PartyPopper, Play } from 'lucide-react';
import { getTriageArticles, type TriageArticle } from '../../services/trainingApi';
import { recordArticlePreference } from '../../services/newsFeedApi';

const FEEDBACK_GOAL = 500;
const PREFETCH_THRESHOLD = 10;
const BATCH_SIZE = 50;

type SlideDirection = 'left' | 'right' | 'up' | null;

interface RelevanceTriageOverlayProps {
  totalExistingFeedback: number;
  onClose: () => void;
}

export function RelevanceTriageOverlay({ totalExistingFeedback, onClose }: RelevanceTriageOverlayProps) {
  const [articles, setArticles] = useState<TriageArticle[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [slideDirection, setSlideDirection] = useState<SlideDirection>(null);
  const [totalAvailable, setTotalAvailable] = useState(0);
  const [availableTopics, setAvailableTopics] = useState<string[]>([]);
  const [selectedTopic, setSelectedTopic] = useState<string>('');
  const [sessionRelevant, setSessionRelevant] = useState(0);
  const [sessionNotRelevant, setSessionNotRelevant] = useState(0);
  const [sessionSkipped, setSessionSkipped] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [offset, setOffset] = useState(0);
  const [exhausted, setExhausted] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const animatingRef = useRef(false);

  const totalFeedback = totalExistingFeedback + sessionRelevant + sessionNotRelevant;
  const remaining = Math.max(0, FEEDBACK_GOAL - totalFeedback);
  const progressPct = Math.min((totalFeedback / FEEDBACK_GOAL) * 100, 100);
  const reachedGoal = totalFeedback >= FEEDBACK_GOAL;

  const loadArticles = useCallback(async (topicFilter: string, currentOffset: number, append: boolean) => {
    if (!append) setLoading(true);
    setError(null);
    try {
      const data = await getTriageArticles({
        topic: topicFilter || undefined,
        limit: BATCH_SIZE,
        offset: currentOffset,
      });
      if (append) {
        setArticles(prev => [...prev, ...data.articles]);
      } else {
        setArticles(data.articles);
        setCurrentIndex(0);
      }
      setTotalAvailable(data.total_available);
      setAvailableTopics(data.available_topics);
      if (data.articles.length < BATCH_SIZE) {
        setExhausted(true);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load articles');
    } finally {
      setLoading(false);
    }
  }, []);

  // Initial load
  useEffect(() => {
    loadArticles(selectedTopic, 0, false);
  }, [selectedTopic, loadArticles]);

  // Prefetch next batch
  useEffect(() => {
    const remaining_in_batch = articles.length - currentIndex;
    if (remaining_in_batch <= PREFETCH_THRESHOLD && !exhausted && !loading) {
      const newOffset = offset + BATCH_SIZE;
      setOffset(newOffset);
      loadArticles(selectedTopic, newOffset, true);
    }
  }, [currentIndex, articles.length, exhausted, loading, offset, selectedTopic, loadArticles]);

  // Focus container for keyboard events
  useEffect(() => {
    containerRef.current?.focus();
  }, []);

  const currentArticle = articles[currentIndex] ?? null;
  const hasMore = currentIndex < articles.length - 1 || !exhausted;

  const advanceCard = useCallback((direction: SlideDirection) => {
    if (animatingRef.current) return;
    animatingRef.current = true;
    setSlideDirection(direction);
    setTimeout(() => {
      setCurrentIndex(prev => prev + 1);
      setSlideDirection(null);
      animatingRef.current = false;
    }, 200);
  }, []);

  const handleRelevant = useCallback(async () => {
    if (!currentArticle || submitting || animatingRef.current) return;
    setSubmitting(true);
    try {
      await recordArticlePreference(currentArticle.uri, 'more');
      setSessionRelevant(prev => prev + 1);
      advanceCard('right');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to record preference');
    } finally {
      setSubmitting(false);
    }
  }, [currentArticle, submitting, advanceCard]);

  const handleNotRelevant = useCallback(async () => {
    if (!currentArticle || submitting || animatingRef.current) return;
    setSubmitting(true);
    try {
      await recordArticlePreference(currentArticle.uri, 'less');
      setSessionNotRelevant(prev => prev + 1);
      advanceCard('left');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to record preference');
    } finally {
      setSubmitting(false);
    }
  }, [currentArticle, submitting, advanceCard]);

  const handleSkip = useCallback(() => {
    if (!currentArticle || animatingRef.current) return;
    setSessionSkipped(prev => prev + 1);
    advanceCard('up');
  }, [currentArticle, advanceCard]);

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
        return;
      }
      if (!currentArticle || submitting) return;
      if (e.key === 'ArrowRight') {
        e.preventDefault();
        handleRelevant();
      } else if (e.key === 'ArrowLeft') {
        e.preventDefault();
        handleNotRelevant();
      } else if (e.key === ' ') {
        e.preventDefault();
        handleSkip();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [currentArticle, submitting, handleRelevant, handleNotRelevant, handleSkip, onClose]);

  const getSlideClass = () => {
    if (!slideDirection) return 'translate-x-0 opacity-100';
    if (slideDirection === 'left') return '-translate-x-full opacity-0';
    if (slideDirection === 'right') return 'translate-x-full opacity-0';
    if (slideDirection === 'up') return '-translate-y-full opacity-0';
    return '';
  };

  const formatScore = (score: number | null) => {
    if (score === null || score === undefined) return null;
    return `${Math.round(score * 100)}%`;
  };

  const formatTags = (tags: string | null) => {
    if (!tags) return [];
    try {
      const parsed = JSON.parse(tags);
      if (Array.isArray(parsed)) return parsed.slice(0, 5);
    } catch {
      // might be comma-separated
    }
    return tags.split(',').map(t => t.trim()).filter(Boolean).slice(0, 5);
  };

  return (
    <div
      ref={containerRef}
      tabIndex={-1}
      className="fixed inset-0 z-50 bg-gray-900/80 backdrop-blur-sm flex items-center justify-center"
      style={{ outline: 'none' }}
    >
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl mx-4 max-h-[90vh] flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <div className="flex items-center gap-3">
            <button
              onClick={onClose}
              className="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
            <h2 className="text-lg font-semibold text-gray-900">Relevance Triage</h2>
          </div>
          <select
            value={selectedTopic}
            onChange={(e) => {
              setSelectedTopic(e.target.value);
              setOffset(0);
              setExhausted(false);
            }}
            className="text-sm border border-gray-200 rounded-lg px-3 py-1.5 text-gray-700 bg-white"
          >
            <option value="">All Topics</option>
            {availableTopics.map(t => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        </div>

        {/* Progress Section */}
        <div className="px-6 py-3 bg-gray-50 border-b border-gray-100">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-xs font-medium text-gray-600">
              Progress: {totalFeedback}/{FEEDBACK_GOAL}
              {remaining > 0 && <span className="text-gray-400 ml-1">({remaining} more needed)</span>}
            </span>
            <span className="text-xs text-gray-500">
              {totalAvailable.toLocaleString()} unreviewed
            </span>
          </div>
          <div className="h-2 bg-gray-200 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-300 ${reachedGoal ? 'bg-green-500' : 'bg-pink-500'}`}
              style={{ width: `${progressPct}%` }}
            />
          </div>
          <div className="flex items-center gap-4 mt-2 text-xs text-gray-500">
            <span>Session: <strong className="text-green-600">{sessionRelevant}</strong> relevant</span>
            <span><strong className="text-red-600">{sessionNotRelevant}</strong> not relevant</span>
            <span><strong className="text-gray-500">{sessionSkipped}</strong> skipped</span>
          </div>
        </div>

        {/* Article Card Area */}
        <div className="flex-1 px-6 py-6 overflow-hidden relative min-h-[320px]">
          {loading && articles.length === 0 ? (
            <div className="flex items-center justify-center h-full">
              <Loader2 className="w-8 h-8 animate-spin text-pink-500" />
            </div>
          ) : error ? (
            <div className="flex flex-col items-center justify-center h-full text-center">
              <p className="text-red-600 text-sm mb-2">{error}</p>
              <button
                onClick={() => loadArticles(selectedTopic, 0, false)}
                className="text-sm text-pink-600 hover:text-pink-700 underline"
              >
                Retry
              </button>
            </div>
          ) : !currentArticle && !hasMore ? (
            reachedGoal ? (
              <div className="flex flex-col items-center justify-center h-full text-center">
                <PartyPopper className="w-16 h-16 text-pink-500 mb-4" />
                <h3 className="text-xl font-bold text-gray-900 mb-2">Goal Reached!</h3>
                <p className="text-gray-600 mb-6">
                  You've collected {totalFeedback} feedback entries. The relevance model is ready to train.
                </p>
                <button
                  onClick={onClose}
                  className="px-6 py-2.5 bg-green-500 hover:bg-green-600 text-white font-semibold rounded-lg transition-colors flex items-center gap-2"
                >
                  <Play className="w-4 h-4" />
                  Train Relevance Model
                </button>
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center h-full text-center">
                <p className="text-gray-600 text-sm">No more articles to review.</p>
                <p className="text-gray-400 text-xs mt-1">Collect more articles to continue.</p>
              </div>
            )
          ) : currentArticle ? (
            <div
              className={`transition-all duration-200 ease-out ${getSlideClass()}`}
            >
              <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
                {/* Source / Category / Topic pills */}
                <div className="flex flex-wrap gap-2 mb-3">
                  {currentArticle.news_source && (
                    <span className="px-2 py-0.5 bg-blue-50 text-blue-700 text-xs rounded font-medium">
                      {currentArticle.news_source}
                    </span>
                  )}
                  {currentArticle.category && (
                    <span className="px-2 py-0.5 bg-purple-50 text-purple-700 text-xs rounded font-medium">
                      {currentArticle.category}
                    </span>
                  )}
                  {currentArticle.topic && (
                    <span className="px-2 py-0.5 bg-pink-50 text-pink-700 text-xs rounded font-medium">
                      {currentArticle.topic}
                    </span>
                  )}
                  {currentArticle.publication_date && (
                    <span className="px-2 py-0.5 bg-gray-50 text-gray-600 text-xs rounded">
                      {currentArticle.publication_date.split('T')[0]}
                    </span>
                  )}
                </div>

                {/* Title */}
                <h3 className="text-lg font-bold text-gray-900 mb-3 leading-snug">
                  {currentArticle.title || 'Untitled'}
                </h3>

                {/* Summary */}
                <p className="text-sm text-gray-600 leading-relaxed mb-4 line-clamp-6">
                  {currentArticle.summary || 'No summary available.'}
                </p>

                {/* Tags */}
                {formatTags(currentArticle.tags).length > 0 && (
                  <div className="flex flex-wrap gap-1.5 mb-3">
                    {formatTags(currentArticle.tags).map((tag, i) => (
                      <span key={i} className="px-2 py-0.5 bg-gray-100 text-gray-600 text-[11px] rounded">
                        {tag}
                      </span>
                    ))}
                  </div>
                )}

                {/* Bottom metadata */}
                <div className="flex items-center gap-3 pt-3 border-t border-gray-100">
                  {currentArticle.sentiment && (
                    <span className={`text-xs font-medium px-2 py-0.5 rounded ${
                      currentArticle.sentiment.toLowerCase().includes('positive') ? 'bg-green-50 text-green-700' :
                      currentArticle.sentiment.toLowerCase().includes('negative') ? 'bg-red-50 text-red-700' :
                      'bg-gray-50 text-gray-600'
                    }`}>
                      {currentArticle.sentiment}
                    </span>
                  )}
                  {formatScore(currentArticle.keyword_relevance_score) && (
                    <span className="text-xs text-gray-500">
                      Score: <strong className="text-gray-700">{formatScore(currentArticle.keyword_relevance_score)}</strong>
                    </span>
                  )}
                </div>
              </div>
            </div>
          ) : null}
        </div>

        {/* Action Buttons */}
        <div className="px-6 py-4 border-t border-gray-100 bg-gray-50">
          <div className="flex items-center justify-between">
            <button
              onClick={handleNotRelevant}
              disabled={!currentArticle || submitting || animatingRef.current}
              className="flex items-center gap-2 px-5 py-2.5 bg-red-500 hover:bg-red-600 text-white font-semibold rounded-lg transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <ChevronLeft className="w-4 h-4" />
              Not Relevant
            </button>
            <button
              onClick={handleSkip}
              disabled={!currentArticle || animatingRef.current}
              className="flex items-center gap-2 px-5 py-2.5 bg-gray-200 hover:bg-gray-300 text-gray-700 font-semibold rounded-lg transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Skip
              <ChevronsUp className="w-4 h-4" />
            </button>
            <button
              onClick={handleRelevant}
              disabled={!currentArticle || submitting || animatingRef.current}
              className="flex items-center gap-2 px-5 py-2.5 bg-green-500 hover:bg-green-600 text-white font-semibold rounded-lg transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Relevant
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
          <div className="text-center text-[11px] text-gray-400 mt-2">
            <kbd className="px-1.5 py-0.5 bg-white border border-gray-200 rounded text-[10px]">&larr;</kbd> Not Relevant
            &nbsp;&middot;&nbsp;
            <kbd className="px-1.5 py-0.5 bg-white border border-gray-200 rounded text-[10px]">Space</kbd> Skip
            &nbsp;&middot;&nbsp;
            <kbd className="px-1.5 py-0.5 bg-white border border-gray-200 rounded text-[10px]">&rarr;</kbd> Relevant
            &nbsp;&middot;&nbsp;
            <kbd className="px-1.5 py-0.5 bg-white border border-gray-200 rounded text-[10px]">Esc</kbd> Close
          </div>
        </div>
      </div>
    </div>
  );
}
