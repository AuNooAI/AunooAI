/**
 * RSS Feed Modal - Add/Edit RSS feed configuration
 */

import { useState, useEffect } from 'react';
import {
  createRSSFeed,
  updateRSSFeed,
  testRSSFeedUrl,
  type RSSFeed,
  type RSSFeedCreate,
  type RSSFeedUpdate,
  type RSSFeedTestResult
} from '../../services/gatherApi';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '../ui/dialog';
import { Label } from '../ui/label';
import { Input } from '../ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../ui/select';
import { Switch } from '../ui/switch';
import { Rss, CheckCircle, AlertCircle, Loader2 } from 'lucide-react';

interface RSSFeedModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSave: () => void;
  feed: RSSFeed | null;
  topics: string[];
}

export function RSSFeedModal({
  isOpen,
  onClose,
  onSave,
  feed,
  topics
}: RSSFeedModalProps) {
  const isEditing = !!feed;

  // Form state
  const [name, setName] = useState('');
  const [url, setUrl] = useState('');
  const [topic, setTopic] = useState('');
  const [description, setDescription] = useState('');
  const [isActive, setIsActive] = useState(true);
  const [checkInterval, setCheckInterval] = useState(60);
  const [intervalUnit, setIntervalUnit] = useState('minutes');
  const [relevanceThreshold, setRelevanceThreshold] = useState(0);

  // UI state
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<RSSFeedTestResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Initialize form when feed changes
  useEffect(() => {
    if (feed) {
      setName(feed.name);
      setUrl(feed.url);
      setTopic(feed.topic);
      setDescription(feed.description || '');
      setIsActive(feed.is_active);
      setCheckInterval(feed.check_interval);
      setIntervalUnit(feed.interval_unit);
      setRelevanceThreshold(feed.relevance_threshold || 0);
    } else {
      // Reset to defaults
      setName('');
      setUrl('');
      setTopic(topics[0] || '');
      setDescription('');
      setIsActive(true);
      setCheckInterval(60);
      setIntervalUnit('minutes');
      setRelevanceThreshold(0);
    }
    setTestResult(null);
    setError(null);
  }, [feed, topics, isOpen]);

  // Test the URL
  const handleTestUrl = async () => {
    if (!url) {
      setError('Please enter a URL');
      return;
    }

    try {
      setTesting(true);
      setError(null);
      setTestResult(null);

      const result = await testRSSFeedUrl(url);
      setTestResult(result);

      // Auto-fill name if empty and test succeeded
      if (result.valid && !name && result.title) {
        setName(result.title);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to test URL');
    } finally {
      setTesting(false);
    }
  };

  // Handle save
  const handleSave = async () => {
    // Validation
    if (!name.trim()) {
      setError('Name is required');
      return;
    }
    if (!url.trim()) {
      setError('URL is required');
      return;
    }
    if (!topic) {
      setError('Topic is required');
      return;
    }

    try {
      setSaving(true);
      setError(null);

      if (isEditing && feed) {
        // Update existing feed
        const updates: RSSFeedUpdate = {
          name: name.trim(),
          url: url.trim(),
          topic,
          description: description.trim() || undefined,
          is_active: isActive,
          check_interval: checkInterval,
          interval_unit: intervalUnit,
          relevance_threshold: relevanceThreshold
        };
        await updateRSSFeed(feed.id, updates);
      } else {
        // Create new feed
        const newFeed: RSSFeedCreate = {
          name: name.trim(),
          url: url.trim(),
          topic,
          description: description.trim() || undefined,
          is_active: isActive,
          check_interval: checkInterval,
          interval_unit: intervalUnit,
          relevance_threshold: relevanceThreshold
        };
        await createRSSFeed(newFeed);
      }

      onSave();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save feed');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="rss-feed-modal">
        <DialogHeader>
          <DialogTitle className="rss-feed-modal-title">
            <Rss className="w-5 h-5 text-pink-500" />
            {isEditing ? 'Edit RSS Feed' : 'Add RSS Feed'}
          </DialogTitle>
        </DialogHeader>

        <div className="rss-feed-modal-content">
          {/* URL field with test button */}
          <div className="rss-feed-modal-field">
            <Label htmlFor="feed-url">Feed URL</Label>
            <div className="rss-feed-url-row">
              <Input
                id="feed-url"
                type="url"
                placeholder="https://example.com/feed.xml"
                value={url}
                onChange={(e) => {
                  setUrl(e.target.value);
                  setTestResult(null);
                }}
              />
              <button
                type="button"
                className="rss-feed-test-btn"
                onClick={handleTestUrl}
                disabled={testing || !url}
              >
                {testing ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  'Test'
                )}
              </button>
            </div>
            {testResult && (
              <div className={`rss-feed-test-result ${testResult.valid ? 'success' : 'error'}`}>
                {testResult.valid ? (
                  <>
                    <CheckCircle className="w-4 h-4" />
                    <span>
                      Valid {testResult.feed_type} feed: "{testResult.title}" ({testResult.entry_count} entries)
                    </span>
                  </>
                ) : (
                  <>
                    <AlertCircle className="w-4 h-4" />
                    <span>{testResult.error || 'Invalid feed'}</span>
                  </>
                )}
              </div>
            )}
          </div>

          {/* Name field */}
          <div className="rss-feed-modal-field">
            <Label htmlFor="feed-name">Name</Label>
            <Input
              id="feed-name"
              placeholder="My RSS Feed"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>

          {/* Topic selector */}
          <div className="rss-feed-modal-field">
            <Label htmlFor="feed-topic">Topic</Label>
            <Select value={topic} onValueChange={setTopic}>
              <SelectTrigger id="feed-topic">
                <SelectValue placeholder="Select a topic" />
              </SelectTrigger>
              <SelectContent>
                {topics.map(t => (
                  <SelectItem key={t} value={t}>{t}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Description field */}
          <div className="rss-feed-modal-field">
            <Label htmlFor="feed-description">Description (optional)</Label>
            <Input
              id="feed-description"
              placeholder="A brief description of this feed"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>

          {/* Schedule settings */}
          <div className="rss-feed-modal-field">
            <Label>Check Interval</Label>
            <div className="rss-feed-interval-row">
              <Input
                type="number"
                min={1}
                value={checkInterval}
                onChange={(e) => setCheckInterval(parseInt(e.target.value) || 60)}
                className="rss-feed-interval-input"
              />
              <Select value={intervalUnit} onValueChange={setIntervalUnit}>
                <SelectTrigger className="rss-feed-interval-unit">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="minutes">Minutes</SelectItem>
                  <SelectItem value="hours">Hours</SelectItem>
                  <SelectItem value="days">Days</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Active toggle */}
          <div className="rss-feed-modal-field rss-feed-switch-row">
            <div className="rss-feed-switch-label">
              <Label htmlFor="feed-active">Active</Label>
              <span className="rss-feed-switch-hint">Enable automatic fetching</span>
            </div>
            <Switch
              id="feed-active"
              checked={isActive}
              onCheckedChange={setIsActive}
            />
          </div>

          {/* Relevance threshold slider */}
          <div className="rss-feed-modal-field">
            <Label htmlFor="feed-relevance">
              Relevance Threshold: {relevanceThreshold === 0 ? 'Off' : `${relevanceThreshold}%`}
            </Label>
            <input
              id="feed-relevance"
              type="range"
              min={0}
              max={100}
              step={5}
              value={relevanceThreshold}
              onChange={(e) => setRelevanceThreshold(parseInt(e.target.value))}
              className="rss-feed-relevance-slider"
            />
            <span className="rss-feed-switch-hint">
              {relevanceThreshold === 0
                ? 'All articles will be enriched without relevance filtering'
                : `Only articles with ${relevanceThreshold}%+ relevance will be enriched`
              }
            </span>
          </div>

          {/* Error display */}
          {error && (
            <div className="rss-feed-modal-error">
              <AlertCircle className="w-4 h-4" />
              {error}
            </div>
          )}
        </div>

        <DialogFooter>
          <button
            type="button"
            className="rss-feed-modal-cancel"
            onClick={onClose}
            disabled={saving}
          >
            Cancel
          </button>
          <button
            type="button"
            className="rss-feed-modal-save"
            onClick={handleSave}
            disabled={saving || !name || !url || !topic}
          >
            {saving ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Saving...
              </>
            ) : (
              isEditing ? 'Update Feed' : 'Add Feed'
            )}
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
