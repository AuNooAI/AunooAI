/**
 * KeywordGroupCard - Summary card for a keyword group
 */

import { FileText, CheckCircle2, XCircle, HelpCircle, Database, Calendar, Clock, CheckCircle, AlertCircle, Loader2, ChevronRight, X, Settings, Sliders } from 'lucide-react';
import type { KeywordGroupSummary } from '../../services/gatherApi';

interface KeywordGroupCardProps {
  group: KeywordGroupSummary;
  onClick: () => void;
  onDeleteUnscored?: (groupId: number) => void;
  onSettingsClick?: (groupId: number) => void;
}

// Simple sparkline component
function Sparkline({ data, width = 80, height = 24 }: { data: number[]; width?: number; height?: number }) {
  if (!data || data.length === 0) {
    return <div className="gather-sparkline-empty" style={{ width, height }} />;
  }

  const max = Math.max(...data, 1);
  const min = 0;
  const range = max - min || 1;

  // Generate path
  const points = data.map((value, index) => {
    const x = (index / (data.length - 1 || 1)) * width;
    const y = height - ((value - min) / range) * height;
    return `${x},${y}`;
  });

  const pathD = `M ${points.join(' L ')}`;

  // Area fill path
  const areaD = `M 0,${height} L ${points.join(' L ')} L ${width},${height} Z`;

  return (
    <svg width={width} height={height} className="gather-sparkline">
      <path d={areaD} fill="rgba(236, 72, 153, 0.1)" />
      <path d={pathD} fill="none" stroke="#ec4899" strokeWidth="1.5" />
    </svg>
  );
}

export function KeywordGroupCard({ group, onClick, onDeleteUnscored, onSettingsClick }: KeywordGroupCardProps) {
  // Check if group has custom settings
  const hasCustomSettings = group.has_custom_schedule || group.has_custom_providers;

  // Status icon and color
  const getStatusInfo = () => {
    // Check if group is inactive
    if (group.is_active === false) {
      return { icon: <Clock className="h-4 w-4" />, color: 'neutral', text: 'Paused' };
    }
    switch (group.status) {
      case 'success':
        return { icon: <CheckCircle className="h-4 w-4" />, color: 'success', text: 'OK' };
      case 'error':
        return { icon: <AlertCircle className="h-4 w-4" />, color: 'error', text: 'Error' };
      case 'pending':
        return { icon: <Loader2 className="h-4 w-4 animate-spin" />, color: 'pending', text: 'Running' };
      default:
        return { icon: <Clock className="h-4 w-4" />, color: 'neutral', text: 'Never run' };
    }
  };

  const statusInfo = getStatusInfo();

  // Format next check time
  const formatNextCheck = () => {
    if (!group.next_check_at) return null;
    const date = new Date(group.next_check_at);
    const now = new Date();
    const diff = date.getTime() - now.getTime();

    if (diff < 0) return 'Due now';
    if (diff < 60000) return 'In < 1 min';
    if (diff < 3600000) return `In ${Math.round(diff / 60000)} min`;
    if (diff < 86400000) return `In ${Math.round(diff / 3600000)} hr`;
    return `In ${Math.round(diff / 86400000)} days`;
  };

  // Format last checked time
  const formatLastChecked = () => {
    if (!group.last_checked) return 'Never';
    const date = new Date(group.last_checked);
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
    });
  };

  // Extract sparkline data from daily_counts
  const sparklineData = (group.daily_counts || []).map(([, count]) => count);

  // Calculate total collected (all articles matched to this group)
  const totalCollected = group.total_articles || 0;

  const nextCheckText = formatNextCheck();

  return (
    <div className="gather-card" onClick={onClick}>
      {/* Card Header */}
      <div className="gather-card-header">
        <div className="gather-card-icon">
          <FileText className="h-5 w-5" />
        </div>
        <div className="gather-card-title-section">
          <div className="gather-card-title-row">
            <h3 className="gather-card-title">{group.name}</h3>
            {hasCustomSettings && (
              <span className="gather-custom-badge" title="This group has custom collection settings">
                <Sliders className="h-3 w-3" />
                Custom
              </span>
            )}
            {group.is_active === false && (
              <span className="gather-paused-badge" title="Collection is paused for this group">
                Paused
              </span>
            )}
          </div>
          <p className="gather-card-subtitle">
            {group.topic} · {group.keyword_count} keyword{group.keyword_count !== 1 ? 's' : ''} monitored
          </p>
        </div>
        {onSettingsClick && (
          <button
            className="gather-card-settings-btn"
            onClick={(e) => {
              e.stopPropagation();
              onSettingsClick(group.id);
            }}
            title="Group collection settings"
          >
            <Settings className="h-4 w-4" />
          </button>
        )}
      </div>

      {/* Metrics Grid - Row 1: Relevance-based counts */}
      <div className="gather-card-metrics gather-card-metrics-row1">
        <div className="gather-metric">
          <div className="gather-metric-value">{totalCollected.toLocaleString()}</div>
          <div className="gather-metric-label">
            <Database className="h-3 w-3" />
            Total
          </div>
        </div>

        <div className="gather-metric">
          <div className="gather-metric-value gather-metric-value-success">{(group.relevant_count || 0).toLocaleString()}</div>
          <div className="gather-metric-label">
            <CheckCircle2 className="h-3 w-3" />
            Relevant
          </div>
        </div>

        <div className="gather-metric">
          <div className="gather-metric-value gather-metric-value-error">{(group.irrelevant_count || 0).toLocaleString()}</div>
          <div className="gather-metric-label">
            <XCircle className="h-3 w-3" />
            Irrelevant
          </div>
        </div>

        <div className="gather-metric gather-metric-unscored">
          <div className="gather-metric-value gather-metric-value-muted">
            {(group.unscored_count || 0).toLocaleString()}
            {(group.unscored_count || 0) > 0 && onDeleteUnscored && (
              <button
                className="gather-delete-unscored-btn"
                onClick={(e) => {
                  e.stopPropagation();
                  onDeleteUnscored(group.id);
                }}
                title="Delete unscored articles"
              >
                <X className="h-3 w-3" />
              </button>
            )}
          </div>
          <div className="gather-metric-label">
            <HelpCircle className="h-3 w-3" />
            Unscored
          </div>
        </div>
      </div>

      {/* Metrics Grid - Row 2: Time-based with Status and Sparkline */}
      <div className="gather-card-metrics gather-card-metrics-row2">
        <div className="gather-metric">
          <div className="gather-metric-value">{(group.articles_past_24h || 0).toLocaleString()}</div>
          <div className="gather-metric-label">
            <Clock className="h-3 w-3" />
            Last 24h
          </div>
        </div>

        <div className="gather-metric">
          <div className="gather-metric-value">{(group.articles_past_week || 0).toLocaleString()}</div>
          <div className="gather-metric-label">
            <Calendar className="h-3 w-3" />
            This Week
          </div>
        </div>

        <div className="gather-metric">
          <div className={`gather-metric-status gather-status-${statusInfo.color}`}>
            {statusInfo.icon}
          </div>
          <div className="gather-metric-label">{statusInfo.text}</div>
        </div>

        <div className="gather-metric gather-metric-sparkline">
          <Sparkline data={sparklineData} width={100} height={28} />
          <div className="gather-metric-label">30-Day Trend</div>
        </div>
      </div>

      {/* Card Footer */}
      <div className="gather-card-footer">
        <div className="gather-card-footer-left">
          <span className="gather-card-last-checked">
            Last checked: {formatLastChecked()}
          </span>
          {nextCheckText && (
            <span className="gather-card-next-check" title={group.next_check_at ? new Date(group.next_check_at).toLocaleString() : ''}>
              · Next: {nextCheckText}
            </span>
          )}
        </div>
        <span className="gather-card-view-details">
          View Details
          <ChevronRight className="h-4 w-4" />
        </span>
      </div>
    </div>
  );
}
