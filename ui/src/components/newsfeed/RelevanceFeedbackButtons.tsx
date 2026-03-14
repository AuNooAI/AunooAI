/**
 * Relevance Feedback Buttons
 *
 * "More like this" / "Less like this" buttons for training relevance model.
 * Allows users to provide feedback on article relevance.
 */

import { useState, useEffect } from 'react';
import { ThumbsUp, ThumbsDown, Loader2 } from 'lucide-react';
import {
  recordRelevanceFeedback,
  getArticleFeedback,
  deleteRelevanceFeedback,
  type RelevanceFeedbackRequest,
} from '../../services/trainingApi';

interface RelevanceFeedbackButtonsProps {
  articleUri: string;
  topic: string;
  relevanceScore?: number;
  classifierScore?: number;
  embeddingScore?: number;
  articleMetadata?: Record<string, unknown>;
  size?: 'sm' | 'md';
  onFeedbackChange?: (feedbackType: string | null) => void;
}

export function RelevanceFeedbackButtons({
  articleUri,
  topic,
  relevanceScore,
  classifierScore,
  embeddingScore,
  articleMetadata,
  size = 'sm',
  onFeedbackChange,
}: RelevanceFeedbackButtonsProps) {
  const [feedbackType, setFeedbackType] = useState<string | null>(null);
  const [feedbackId, setFeedbackId] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [initialLoading, setInitialLoading] = useState(true);

  // Load existing feedback on mount
  useEffect(() => {
    let mounted = true;

    async function loadFeedback() {
      try {
        const response = await getArticleFeedback(articleUri);
        if (mounted) {
          if (response.has_feedback && response.feedback) {
            setFeedbackType(response.feedback.feedback_type);
            setFeedbackId(response.feedback.id);
          }
        }
      } catch (error) {
        console.error('Failed to load feedback:', error);
      } finally {
        if (mounted) {
          setInitialLoading(false);
        }
      }
    }

    loadFeedback();

    return () => {
      mounted = false;
    };
  }, [articleUri]);

  const handleFeedback = async (type: 'more_like_this' | 'less_like_this') => {
    if (loading) return;

    setLoading(true);
    try {
      // If clicking the same button, toggle off (delete feedback)
      if (feedbackType === type && feedbackId) {
        await deleteRelevanceFeedback(feedbackId);
        setFeedbackType(null);
        setFeedbackId(null);
        onFeedbackChange?.(null);
      } else {
        // Record new feedback (will upsert if exists)
        const request: RelevanceFeedbackRequest = {
          article_uri: articleUri,
          topic,
          feedback_type: type,
          relevance_score: relevanceScore,
          classifier_score: classifierScore,
          embedding_score: embeddingScore,
          article_metadata: articleMetadata,
        };

        const response = await recordRelevanceFeedback(request);
        setFeedbackType(type);
        setFeedbackId(response.id);
        onFeedbackChange?.(type);
      }
    } catch (error) {
      console.error('Failed to record feedback:', error);
    } finally {
      setLoading(false);
    }
  };

  const iconSize = size === 'sm' ? 'w-4 h-4' : 'w-5 h-5';
  const buttonSize = size === 'sm' ? 'p-1.5' : 'p-2';

  if (initialLoading) {
    return (
      <div className="flex items-center gap-1">
        <Loader2 className={`${iconSize} animate-spin text-gray-400`} />
      </div>
    );
  }

  return (
    <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
      {/* More like this */}
      <button
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          handleFeedback('more_like_this');
        }}
        disabled={loading}
        className={`${buttonSize} rounded transition-colors ${
          feedbackType === 'more_like_this'
            ? 'bg-green-100 dark:bg-green-900/30 text-green-600 dark:text-green-400'
            : 'hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-500 dark:text-gray-400'
        }`}
        title="More like this"
      >
        {loading && feedbackType !== 'less_like_this' ? (
          <Loader2 className={`${iconSize} animate-spin`} />
        ) : (
          <ThumbsUp
            className={`${iconSize} ${
              feedbackType === 'more_like_this' ? 'fill-current' : ''
            }`}
          />
        )}
      </button>

      {/* Less like this */}
      <button
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          handleFeedback('less_like_this');
        }}
        disabled={loading}
        className={`${buttonSize} rounded transition-colors ${
          feedbackType === 'less_like_this'
            ? 'bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400'
            : 'hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-500 dark:text-gray-400'
        }`}
        title="Less like this"
      >
        {loading && feedbackType !== 'more_like_this' ? (
          <Loader2 className={`${iconSize} animate-spin`} />
        ) : (
          <ThumbsDown
            className={`${iconSize} ${
              feedbackType === 'less_like_this' ? 'fill-current' : ''
            }`}
          />
        )}
      </button>
    </div>
  );
}
