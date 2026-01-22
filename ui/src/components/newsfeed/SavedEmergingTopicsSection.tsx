/**
 * Saved Emerging Topics Section - Display tracked emerging topics
 * Shows in the Saved tab alongside saved incidents and podcasts
 */

import { useState, useEffect } from 'react';
import {
  TrendingUp,
  TrendingDown,
  Circle,
  Sparkles,
  Calendar,
  BookmarkX,
  MoreVertical,
  Share2,
} from 'lucide-react';
import { Card, CardContent } from '../ui/card';
import { Badge } from '../ui/badge';
import { Skeleton } from '../ui/skeleton';

interface TrendScore {
  volume: number;
  velocity: number;
  diversity: number;
  novelty: number;
  composite: number;
}

interface TrackedTopic {
  id: number;
  topic_label: string;
  topic_description: string;
  detection_date: string;
  detection_type: string;
  article_count: number;
  velocity: 'accelerating' | 'stable' | 'decelerating';
  trend_score?: TrendScore;
  key_entities?: string[];
  tracked_at?: string;
}

interface SavedEmergingTopicsSectionProps {
  className?: string;
  onTopicClick?: (topicId: number) => void;
}

// Velocity badge styling - returns icon dynamically to avoid initialization issues
function getVelocityStyle(velocity: string) {
  switch (velocity) {
    case 'accelerating':
      return {
        label: 'Accelerating',
        className: 'text-green-600 dark:text-green-400',
        icon: <TrendingUp className="w-3 h-3" />,
      };
    case 'decelerating':
      return {
        label: 'Slowing',
        className: 'text-orange-600 dark:text-orange-400',
        icon: <TrendingDown className="w-3 h-3" />,
      };
    default:
      return {
        label: 'Stable',
        className: 'text-gray-600 dark:text-gray-300',
        icon: <Circle className="w-3 h-3" />,
      };
  }
}

function getScoreColor(score: number): string {
  if (score >= 70) return 'text-green-600 dark:text-green-400';
  if (score >= 40) return 'text-yellow-600 dark:text-yellow-400';
  return 'text-gray-600 dark:text-gray-300';
}

export function SavedEmergingTopicsSection({
  className,
  onTopicClick,
}: SavedEmergingTopicsSectionProps) {
  const [topics, setTopics] = useState<TrackedTopic[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Menu state
  const [menuOpenId, setMenuOpenId] = useState<number | null>(null);

  // Fetch tracked topics on mount
  useEffect(() => {
    fetchTrackedTopics();
  }, []);

  // Close menu on outside click
  useEffect(() => {
    const handleClick = () => setMenuOpenId(null);
    if (menuOpenId !== null) {
      document.addEventListener('click', handleClick);
    }
    return () => document.removeEventListener('click', handleClick);
  }, [menuOpenId]);

  const fetchTrackedTopics = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch('/api/emerging-topics/tracked', {
        credentials: 'include',
      });
      if (!res.ok) {
        throw new Error('Failed to fetch tracked topics');
      }
      const data = await res.json();
      setTopics(data.topics || []);
    } catch (err) {
      console.error('Error fetching tracked topics:', err);
      setError(err instanceof Error ? err.message : 'Failed to load tracked topics');
    } finally {
      setLoading(false);
    }
  };

  const handleUntrack = async (topicId: number) => {
    try {
      const res = await fetch(`/api/emerging-topics/topics/${topicId}/track`, {
        method: 'DELETE',
        credentials: 'include',
      });
      if (res.ok) {
        setTopics((prev) => prev.filter((t) => t.id !== topicId));
      }
    } catch (err) {
      console.error('Error untracking topic:', err);
    }
    setMenuOpenId(null);
  };

  const handleShare = (topic: TrackedTopic) => {
    // TODO: Implement share functionality for emerging topics
    console.log('Share topic:', topic.topic_label);
    setMenuOpenId(null);
  };

  // Loading state
  if (loading) {
    return (
      <div className={className}>
        <div className="flex items-center gap-2 mb-4">
          <Sparkles className="w-5 h-5 text-purple-500" />
          <h3 className="font-semibold text-gray-900 dark:text-gray-100">
            Tracked Emerging Topics
          </h3>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-32 rounded-lg" />
          ))}
        </div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className={className}>
        <div className="flex items-center gap-2 mb-4">
          <Sparkles className="w-5 h-5 text-purple-500" />
          <h3 className="font-semibold text-gray-900 dark:text-gray-100">
            Tracked Emerging Topics
          </h3>
        </div>
        <div className="text-center py-8 text-red-500">{error}</div>
      </div>
    );
  }

  // Empty state
  if (topics.length === 0) {
    return (
      <div className={className}>
        <div className="flex items-center gap-2 mb-4">
          <Sparkles className="w-5 h-5 text-purple-500" />
          <h3 className="font-semibold text-gray-900 dark:text-gray-100">
            Tracked Emerging Topics
          </h3>
        </div>
        <Card>
          <CardContent className="py-8 text-center">
            <Sparkles className="w-12 h-12 mx-auto text-gray-600 dark:text-gray-300 dark:text-gray-600 mb-3" />
            <p className="text-gray-700 dark:text-gray-300 dark:text-gray-300">No tracked topics yet</p>
            <p className="text-sm text-gray-600 dark:text-gray-300 dark:text-gray-700 dark:text-gray-300 mt-1">
              Save emerging topics from the Emerging Topics tab to track them here
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className={className}>
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Sparkles className="w-5 h-5 text-purple-500" />
          <h3 className="font-semibold text-gray-900 dark:text-gray-100">
            Tracked Emerging Topics
          </h3>
          <Badge variant="secondary" className="text-xs">
            {topics.length}
          </Badge>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {topics.map((topic) => {
          const velocityStyle = getVelocityStyle(topic.velocity);

          return (
            <Card
              key={topic.id}
              className="hover:shadow-md transition-shadow cursor-pointer relative"
              onClick={() => onTopicClick?.(topic.id)}
            >
              <CardContent className="p-4">
                {/* Header with menu */}
                <div className="flex items-start justify-between mb-2">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <Badge className="text-xs bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200">
                        <Sparkles className="w-3 h-3 mr-1" />
                        Detected
                      </Badge>
                    </div>
                    <h4 className="font-semibold text-gray-900 dark:text-gray-100 line-clamp-2">
                      {topic.topic_label}
                    </h4>
                  </div>

                  {/* Menu button */}
                  <div className="relative ml-2">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setMenuOpenId(menuOpenId === topic.id ? null : topic.id);
                      }}
                      className="p-1 hover:bg-gray-100 dark:hover:bg-gray-700 rounded"
                    >
                      <MoreVertical className="w-4 h-4 text-gray-600 dark:text-gray-300" />
                    </button>

                    {menuOpenId === topic.id && (
                      <div
                        className="absolute right-0 top-full mt-1 w-32 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg z-50 py-1"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <button
                          onClick={() => handleShare(topic)}
                          className="w-full px-3 py-2 text-left text-sm hover:bg-gray-100 dark:hover:bg-gray-700 flex items-center gap-2"
                        >
                          <Share2 className="w-4 h-4" /> Share
                        </button>
                        <button
                          onClick={() => handleUntrack(topic.id)}
                          className="w-full px-3 py-2 text-left text-sm text-red-600 hover:bg-red-50 dark:hover:bg-red-900/30 flex items-center gap-2"
                        >
                          <BookmarkX className="w-4 h-4" /> Untrack
                        </button>
                      </div>
                    )}
                  </div>
                </div>

                {/* Description */}
                <p className="text-sm text-gray-600 dark:text-gray-300 line-clamp-2 mb-3">
                  {topic.topic_description}
                </p>

                {/* Key entities */}
                {topic.key_entities && topic.key_entities.length > 0 && (
                  <div className="flex flex-wrap gap-1 mb-3">
                    {topic.key_entities.slice(0, 3).map((entity, i) => (
                      <Badge key={i} variant="outline" className="text-xs">
                        {entity}
                      </Badge>
                    ))}
                    {topic.key_entities.length > 3 && (
                      <Badge variant="outline" className="text-xs text-gray-600 dark:text-gray-300">
                        +{topic.key_entities.length - 3}
                      </Badge>
                    )}
                  </div>
                )}

                {/* Stats row */}
                <div className="flex items-center justify-between text-xs text-gray-700 dark:text-gray-300">
                  <div className="flex items-center gap-3">
                    <span className="font-medium text-gray-900 dark:text-gray-100">
                      {topic.article_count} articles
                    </span>
                    <span className={`flex items-center gap-1 ${velocityStyle.className}`}>
                      {velocityStyle.icon}
                      {velocityStyle.label}
                    </span>
                  </div>
                  {topic.trend_score && (
                    <span className={`font-bold ${getScoreColor(topic.trend_score.composite)}`}>
                      {Math.round(topic.trend_score.composite)}
                    </span>
                  )}
                </div>

                {/* Detection date */}
                <div className="flex items-center gap-1 text-xs text-gray-600 dark:text-gray-300 mt-2">
                  <Calendar className="w-3 h-3" />
                  Detected {new Date(topic.detection_date).toLocaleDateString()}
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}

export default SavedEmergingTopicsSection;
