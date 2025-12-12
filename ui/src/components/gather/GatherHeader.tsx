/**
 * GatherHeader - Header component with controls
 */

import { Switch } from '../ui/switch';
import { Button } from '../ui/button';
import { RefreshCw, Settings, List, ExternalLink, Loader2, FlaskConical } from 'lucide-react';
import type { MonitorStatus } from '../../services/gatherApi';

interface GatherHeaderProps {
  status: MonitorStatus | null;
  checkingKeywords: boolean;
  onToggleCollection: () => void;
  onUpdateNow: () => void;
  onOpenAutoCollect: () => void;
  onOpenManageKeywords: () => void;
  onTestProcess?: () => void;
}

export function GatherHeader({
  status,
  checkingKeywords,
  onToggleCollection,
  onUpdateNow,
  onOpenAutoCollect,
  onOpenManageKeywords,
  onTestProcess,
}: GatherHeaderProps) {
  const isCollectionEnabled = status?.is_enabled ?? false;

  // Format last check time
  const formatLastCheck = () => {
    if (!status?.last_check_time) return 'Never';
    const date = new Date(status.last_check_time);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMins / 60);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    return date.toLocaleDateString();
  };

  return (
    <header className="gather-header">
      <div className="gather-header-top">
        <div className="gather-header-title">
          <h1>Gather</h1>
          <p className="gather-header-subtitle">Automated data collection management</p>
        </div>

        <div className="gather-header-status">
          {status && (
            <>
              <span className="gather-status-item">
                <span className="gather-status-label">API Usage:</span>
                <span className="gather-status-value">
                  {status.requests_today}/{status.daily_limit}
                </span>
              </span>
              <span className="gather-status-item">
                <span className="gather-status-label">Last check:</span>
                <span className="gather-status-value">{formatLastCheck()}</span>
              </span>
            </>
          )}
        </div>
      </div>

      <div className="gather-header-controls">
        <div className="gather-header-controls-left">
          {/* Auto-Collection Toggle (scheduled background collection + processing) */}
          <div className="gather-toggle-control">
            <label htmlFor="auto-collection" className="gather-toggle-label">
              Auto-Collect
            </label>
            <Switch
              id="auto-collection"
              checked={isCollectionEnabled}
              onCheckedChange={onToggleCollection}
            />
            <span className={`gather-toggle-status ${isCollectionEnabled ? 'active' : ''}`}>
              {isCollectionEnabled ? 'ON' : 'OFF'}
            </span>
            {onTestProcess && (
              <button
                onClick={onTestProcess}
                className="gather-test-button"
                title="Test LLM processing on a single article"
              >
                <FlaskConical className="h-3.5 w-3.5" />
              </button>
            )}
          </div>

          {/* Submit Articles Link */}
          <a href="/submit-articles" className="gather-link-button">
            <ExternalLink className="h-4 w-4" />
            Submit Articles
          </a>
        </div>

        <div className="gather-header-controls-right">
          {/* Update Now Button */}
          <Button
            onClick={onUpdateNow}
            disabled={checkingKeywords}
            className="gather-action-button"
          >
            {checkingKeywords ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Checking...
              </>
            ) : (
              <>
                <RefreshCw className="h-4 w-4" />
                Update Now
              </>
            )}
          </Button>

          {/* Auto-Collect Button (Settings) */}
          <Button
            onClick={onOpenAutoCollect}
            variant="outline"
            className="gather-secondary-button"
          >
            <Settings className="h-4 w-4" />
            Auto-Collect
          </Button>

          {/* Manage Keywords Button */}
          <Button
            onClick={onOpenManageKeywords}
            variant="outline"
            className="gather-secondary-button"
          >
            <List className="h-4 w-4" />
            Manage Keywords
          </Button>
        </div>
      </div>
    </header>
  );
}
