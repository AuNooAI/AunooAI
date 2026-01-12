/**
 * RSS Feeds Tab - Display and manage RSS feed sources
 */

import { useState, useEffect, useCallback } from 'react';
import {
  getRSSFeeds,
  deleteRSSFeed,
  fetchRSSFeed,
  getRSSMonitorStatus,
  type RSSFeed,
  type RSSMonitorStatus
} from '../../services/gatherApi';
import { RSSFeedModal } from './RSSFeedModal';
import {
  Rss,
  Plus,
  Trash2,
  Play,
  RefreshCw,
  AlertCircle,
  CheckCircle,
  Clock,
  ExternalLink,
  MoreVertical,
  Edit
} from 'lucide-react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '../ui/dropdown-menu';
import { ProcessingStatusBadge } from './ProcessingStatusBadge';

interface RSSFeedsTabProps {
  topics: string[];
}

export function RSSFeedsTab({ topics }: RSSFeedsTabProps) {
  const [feeds, setFeeds] = useState<RSSFeed[]>([]);
  const [monitorStatus, setMonitorStatus] = useState<RSSMonitorStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingFeed, setEditingFeed] = useState<RSSFeed | null>(null);
  const [fetchingFeedId, setFetchingFeedId] = useState<number | null>(null);

  // Load feeds and status
  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      const [feedsData, statusData] = await Promise.all([
        getRSSFeeds(),
        getRSSMonitorStatus()
      ]);
      setFeeds(feedsData);
      setMonitorStatus(statusData);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load feeds');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Handle delete feed
  const handleDelete = async (feedId: number, feedName: string) => {
    if (!confirm(`Delete RSS feed "${feedName}"? This cannot be undone.`)) {
      return;
    }

    try {
      await deleteRSSFeed(feedId);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete feed');
    }
  };

  // Handle manual fetch
  const handleFetch = async (feedId: number) => {
    try {
      setFetchingFeedId(feedId);
      await fetchRSSFeed(feedId);
      // Wait a moment then reload
      setTimeout(() => {
        loadData();
        setFetchingFeedId(null);
      }, 1000);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch feed');
      setFetchingFeedId(null);
    }
  };

  // Handle edit
  const handleEdit = (feed: RSSFeed) => {
    setEditingFeed(feed);
    setIsModalOpen(true);
  };

  // Handle modal close
  const handleModalClose = () => {
    setIsModalOpen(false);
    setEditingFeed(null);
  };

  // Handle modal save
  const handleModalSave = async () => {
    await loadData();
    handleModalClose();
  };

  // Format date for display
  const formatDate = (dateStr: string | undefined) => {
    if (!dateStr) return 'Never';
    const date = new Date(dateStr);
    return date.toLocaleString();
  };

  // Format interval for display
  const formatInterval = (interval: number, unit: string) => {
    if (unit === 'hours') return `${interval} hour${interval !== 1 ? 's' : ''}`;
    if (unit === 'days') return `${interval} day${interval !== 1 ? 's' : ''}`;
    return `${interval} minute${interval !== 1 ? 's' : ''}`;
  };

  // Get status icon
  const getStatusIcon = (feed: RSSFeed) => {
    if (feed.last_error) {
      return <AlertCircle className="w-4 h-4 text-red-500" />;
    }
    if (feed.last_checked_at) {
      return <CheckCircle className="w-4 h-4 text-green-500" />;
    }
    return <Clock className="w-4 h-4 text-gray-400" />;
  };

  if (loading) {
    return (
      <div className="rss-feeds-loading">
        <RefreshCw className="w-8 h-8 animate-spin text-pink-500" />
        <p>Loading RSS feeds...</p>
      </div>
    );
  }

  return (
    <div className="rss-feeds-tab">
      {/* Header */}
      <div className="rss-feeds-header">
        <div className="rss-feeds-header-left">
          <h2 className="rss-feeds-title">
            <Rss className="w-5 h-5" />
            RSS Feeds
          </h2>
          {monitorStatus && (
            <span className="rss-feeds-status-badge">
              {monitorStatus.active_feeds} active / {monitorStatus.total_feeds} total
            </span>
          )}
          <ProcessingStatusBadge />
        </div>
        <button
          className="rss-feeds-add-btn"
          onClick={() => setIsModalOpen(true)}
        >
          <Plus className="w-4 h-4" />
          Add Feed
        </button>
      </div>

      {/* Error display */}
      {error && (
        <div className="rss-feeds-error">
          <AlertCircle className="w-4 h-4" />
          {error}
          <button onClick={() => setError(null)}>Dismiss</button>
        </div>
      )}

      {/* Feeds grid */}
      {feeds.length === 0 ? (
        <div className="rss-feeds-empty">
          <Rss className="w-12 h-12 text-gray-300" />
          <h3>No RSS feeds configured</h3>
          <p>Add RSS feeds to automatically collect articles from your favorite sources.</p>
          <button
            className="rss-feeds-empty-cta"
            onClick={() => setIsModalOpen(true)}
          >
            <Plus className="w-4 h-4" />
            Add Your First Feed
          </button>
        </div>
      ) : (
        <div className="rss-feeds-grid">
          {feeds.map(feed => (
            <div key={feed.id} className={`rss-feed-card ${!feed.is_active ? 'inactive' : ''}`}>
              <div className="rss-feed-card-header">
                <div className="rss-feed-card-title-row">
                  {getStatusIcon(feed)}
                  <h3 className="rss-feed-card-title">{feed.name}</h3>
                  {!feed.is_active && (
                    <span className="rss-feed-inactive-badge">Paused</span>
                  )}
                </div>
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <button className="rss-feed-card-menu-btn">
                      <MoreVertical className="w-4 h-4" />
                    </button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem onClick={() => handleEdit(feed)}>
                      <Edit className="w-4 h-4 mr-2" />
                      Edit
                    </DropdownMenuItem>
                    <DropdownMenuItem onClick={() => handleFetch(feed.id)}>
                      <Play className="w-4 h-4 mr-2" />
                      Fetch Now
                    </DropdownMenuItem>
                    <DropdownMenuItem
                      onClick={() => handleDelete(feed.id, feed.name)}
                      className="text-red-600"
                    >
                      <Trash2 className="w-4 h-4 mr-2" />
                      Delete
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </div>

              <div className="rss-feed-card-topic">
                <span className="rss-feed-topic-badge">{feed.topic}</span>
              </div>

              <a
                href={feed.url}
                target="_blank"
                rel="noopener noreferrer"
                className="rss-feed-card-url"
              >
                {feed.url.length > 50 ? feed.url.substring(0, 50) + '...' : feed.url}
                <ExternalLink className="w-3 h-3" />
              </a>

              <div className="rss-feed-card-stats">
                <div className="rss-feed-stat">
                  <span className="rss-feed-stat-value">{formatDate(feed.last_checked_at)}</span>
                  <span className="rss-feed-stat-label">Last Scan</span>
                </div>
                <div className="rss-feed-stat">
                  <span className="rss-feed-stat-value">{feed.articles_fetched}</span>
                  <span className="rss-feed-stat-label">Detected</span>
                </div>
                <div className="rss-feed-stat">
                  <span className="rss-feed-stat-value">{feed.articles_enriched}</span>
                  <span className="rss-feed-stat-label">Enriched</span>
                </div>
              </div>

              <div className="rss-feed-card-footer">
                <span className="rss-feed-interval-info">
                  Checks every {formatInterval(feed.check_interval, feed.interval_unit)}
                </span>
                {feed.last_error && (
                  <span className="rss-feed-error-text" title={feed.last_error}>
                    Error: {feed.last_error.substring(0, 50)}...
                  </span>
                )}
              </div>

              {fetchingFeedId === feed.id && (
                <div className="rss-feed-card-fetching">
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  Fetching...
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Add/Edit Modal */}
      <RSSFeedModal
        isOpen={isModalOpen}
        onClose={handleModalClose}
        onSave={handleModalSave}
        feed={editingFeed}
        topics={topics}
      />
    </div>
  );
}
