/**
 * KeywordGroupDetailPanel - Slide-out panel with detailed group view
 */

import { useState, useEffect } from 'react';
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
  SheetFooter,
} from '../ui/sheet';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Badge } from '../ui/badge';
import { ScrollArea } from '../ui/scroll-area';
import { HoverCard, HoverCardTrigger, HoverCardContent } from '../ui/hover-card';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '../ui/dialog';
import {
  RefreshCw,
  Trash2,
  Plus,
  Edit2,
  X,
  Check,
  ExternalLink,
  AlertCircle,
  AlertTriangle,
  Loader2,
  FileText,
  FlaskConical,
  Sparkles,
  Replace,
  PlusCircle,
  MinusCircle,
} from 'lucide-react';
import {
  getRecentArticlesForGroup,
  getKeywordSuggestions,
  applyKeywordSuggestion,
  type ArticleMatch,
  type KeywordGroupSummary,
  type MonitoredKeyword,
  type KeywordStats,
  type KeywordSuggestionResult,
} from '../../services/gatherApi';

interface KeywordGroupDetailPanelProps {
  group: KeywordGroupSummary | null;
  keywords: MonitoredKeyword[];
  keywordStats: KeywordStats[];
  isOpen: boolean;
  onClose: () => void;
  onRunCheck: (groupId: number) => void;
  onDeleteGroup: (groupId: number) => void;
  onAddKeyword: (groupId: number, keyword: string) => Promise<MonitoredKeyword | null>;
  onEditKeyword: (keywordId: number, keyword: string) => Promise<boolean>;
  onDeleteKeyword: (keywordId: number) => Promise<boolean>;
  checkingKeywords: boolean;
  onTestProcessArticle?: (uri: string, groupId: number) => void;
}

export function KeywordGroupDetailPanel({
  group,
  keywords,
  keywordStats,
  isOpen,
  onClose,
  onRunCheck,
  onDeleteGroup,
  onAddKeyword,
  onEditKeyword,
  onDeleteKeyword,
  checkingKeywords,
  onTestProcessArticle,
}: KeywordGroupDetailPanelProps) {
  const [recentArticles, setRecentArticles] = useState<ArticleMatch[]>([]);
  const [loadingArticles, setLoadingArticles] = useState(false);
  const [newKeyword, setNewKeyword] = useState('');
  const [addingKeyword, setAddingKeyword] = useState(false);
  const [editingKeywordId, setEditingKeywordId] = useState<number | null>(null);
  const [editingKeywordValue, setEditingKeywordValue] = useState('');
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  // Keyword suggestion state
  const [loadingSuggestions, setLoadingSuggestions] = useState<number | null>(null);
  const [suggestions, setSuggestions] = useState<Record<number, KeywordSuggestionResult>>({});
  const [applyingAction, setApplyingAction] = useState<string | null>(null);
  const [suggestionDialogKeyword, setSuggestionDialogKeyword] = useState<MonitoredKeyword | null>(null);

  // Load recent articles when group changes
  useEffect(() => {
    if (group && isOpen) {
      loadRecentArticles();
    }
  }, [group?.id, isOpen]);

  const loadRecentArticles = async () => {
    if (!group) return;

    setLoadingArticles(true);
    try {
      const articles = await getRecentArticlesForGroup(group.id, 20);
      setRecentArticles(articles);
    } catch (err) {
      console.error('Failed to load articles:', err);
    } finally {
      setLoadingArticles(false);
    }
  };

  const handleAddKeyword = async () => {
    if (!group || !newKeyword.trim()) return;

    setAddingKeyword(true);
    const result = await onAddKeyword(group.id, newKeyword.trim());
    if (result) {
      setNewKeyword('');
    }
    setAddingKeyword(false);
  };

  const handleStartEdit = (keyword: MonitoredKeyword) => {
    setEditingKeywordId(keyword.id);
    setEditingKeywordValue(keyword.keyword);
  };

  const handleSaveEdit = async () => {
    if (editingKeywordId && editingKeywordValue.trim()) {
      await onEditKeyword(editingKeywordId, editingKeywordValue.trim());
    }
    setEditingKeywordId(null);
    setEditingKeywordValue('');
  };

  const handleCancelEdit = () => {
    setEditingKeywordId(null);
    setEditingKeywordValue('');
  };

  const handleDelete = () => {
    if (group) {
      onDeleteGroup(group.id);
      setShowDeleteConfirm(false);
    }
  };

  // Load keyword suggestions
  const handleGetSuggestions = async (keywordId: number) => {
    if (!group) return;

    setLoadingSuggestions(keywordId);
    try {
      const result = await getKeywordSuggestions(keywordId, group.id);
      setSuggestions(prev => ({ ...prev, [keywordId]: result }));
    } catch (err) {
      console.error('Failed to get suggestions:', err);
    } finally {
      setLoadingSuggestions(null);
    }
  };

  // Apply a suggestion
  const handleApplySuggestion = async (
    keywordId: number,
    type: 'replace' | 'add' | 'exclude',
    keyword: string,
    reason?: string
  ) => {
    if (!group) return;

    const actionKey = `${keywordId}-${type}-${keyword}`;
    setApplyingAction(actionKey);

    try {
      const result = await applyKeywordSuggestion(keywordId, group.id, {
        suggestion_type: type,
        suggested_keyword: keyword,
        reason,
      });

      if (result.success) {
        // Clear suggestions for this keyword
        setSuggestions(prev => {
          const next = { ...prev };
          delete next[keywordId];
          return next;
        });
        // Trigger a refresh to update the keyword list
        loadRecentArticles();
      } else {
        console.error('Failed to apply suggestion:', result.error);
      }
    } catch (err) {
      console.error('Failed to apply suggestion:', err);
    } finally {
      setApplyingAction(null);
    }
  };

  // Get stats for a specific keyword
  const getKeywordStat = (keywordId: number): KeywordStats | undefined => {
    return keywordStats.find(s => s.keyword_id === keywordId);
  };

  // Build health warnings
  const getHealthWarnings = () => {
    if (!group) return [];
    const warnings: { type: 'error' | 'warning'; message: string }[] = [];

    // Check if recent articles are unscored (indicates current LLM processing issues)
    if (recentArticles.length > 0) {
      const recentToCheck = recentArticles.slice(0, 10); // Check 10 most recent
      const unscoredRecent = recentToCheck.filter(a => a.keyword_relevance_score == null).length;
      if (unscoredRecent >= 5) {
        warnings.push({
          type: 'warning',
          message: `${unscoredRecent} of the last ${recentToCheck.length} articles are unscored - LLM processing may have failed or is still running.`,
        });
      }
    }

    // High irrelevant rate warning
    const scoredCount = (group.relevant_count || 0) + (group.irrelevant_count || 0);
    const irrelevantPct = scoredCount > 0
      ? ((group.irrelevant_count || 0) / scoredCount) * 100
      : 0;
    if (scoredCount > 100 && irrelevantPct > 80) {
      warnings.push({
        type: 'warning',
        message: `${Math.round(irrelevantPct)}% of articles marked irrelevant. Consider refining keywords for better matches.`,
      });
    }

    // Error from last check
    if (group.last_error) {
      warnings.push({
        type: 'error',
        message: group.last_error,
      });
    }

    return warnings;
  };

  if (!group) return null;

  const healthWarnings = getHealthWarnings();

  return (
    <>
    <Sheet open={isOpen} onOpenChange={onClose}>
      <SheetContent
        className="gather-detail-panel"
        side="right"
        style={{ backgroundColor: '#ffffff' }}
      >
        <SheetHeader>
          <SheetTitle className="gather-detail-title">
            {group.name}
          </SheetTitle>
          <SheetDescription className="gather-detail-description">
            <Badge variant="outline" className="gather-topic-badge">{group.topic}</Badge>
            <span className="gather-detail-meta">
              {group.keyword_count} keywords • {group.total_articles.toLocaleString()} articles
            </span>
          </SheetDescription>
        </SheetHeader>

        <ScrollArea className="gather-detail-content">
          {/* Health Warnings */}
          {healthWarnings.length > 0 && (
            <div className="gather-detail-section">
              {healthWarnings.map((warning, idx) => (
                <div key={idx} className={`gather-health-warning gather-health-${warning.type}`}>
                  {warning.type === 'error' ? (
                    <AlertCircle className="h-4 w-4" />
                  ) : (
                    <AlertTriangle className="h-4 w-4" />
                  )}
                  <span>{warning.message}</span>
                </div>
              ))}
            </div>
          )}

          {/* Keywords List with Stats */}
          <div className="gather-detail-section">
            <h4 className="gather-detail-section-title">Keywords & Performance</h4>
            <div className="gather-detail-keywords">
              {keywords.map(kw => {
                const stats = getKeywordStat(kw.id);
                const kwSuggestions = suggestions[kw.id];
                const isLoadingSuggestion = loadingSuggestions === kw.id;
                // Show optimize button when there's enough data to analyze (lowered to 3)
                const hasEnoughData = stats && stats.total_matches >= 3;
                // Highlight sparkle for low-performing keywords
                const needsOptimization = hasEnoughData && stats.avg_relevance < 0.5;

                return (
                  <div key={kw.id} className="gather-keyword-item-enhanced">
                    {editingKeywordId === kw.id ? (
                      <div className="gather-keyword-edit">
                        <Input
                          value={editingKeywordValue}
                          onChange={e => setEditingKeywordValue(e.target.value)}
                          onKeyDown={e => {
                            if (e.key === 'Enter') handleSaveEdit();
                            if (e.key === 'Escape') handleCancelEdit();
                          }}
                          autoFocus
                        />
                        <Button size="sm" variant="ghost" onClick={handleSaveEdit}>
                          <Check className="h-4 w-4" />
                        </Button>
                        <Button size="sm" variant="ghost" onClick={handleCancelEdit}>
                          <X className="h-4 w-4" />
                        </Button>
                      </div>
                    ) : (
                      <>
                        <div className="gather-keyword-header">
                          <span className="gather-keyword-text">{kw.keyword}</span>
                          <div className="gather-keyword-actions">
                            {/* Optimize/Suggest Button - opens dialog */}
                            <Button
                              size="sm"
                              variant="ghost"
                              className={`gather-optimize-btn ${needsOptimization ? 'needs-optimization' : ''}`}
                              onClick={() => {
                                setSuggestionDialogKeyword(kw);
                                if (!kwSuggestions && hasEnoughData) handleGetSuggestions(kw.id);
                              }}
                              disabled={!hasEnoughData}
                              title={hasEnoughData ? "Get AI suggestions to improve this keyword" : "Need at least 3 matched articles to analyze"}
                            >
                              {isLoadingSuggestion ? (
                                <Loader2 className="h-3 w-3 animate-spin" />
                              ) : (
                                <Sparkles className="h-3 w-3" />
                              )}
                            </Button>
                            <Button size="sm" variant="ghost" onClick={() => handleStartEdit(kw)}>
                              <Edit2 className="h-3 w-3" />
                            </Button>
                            <Button size="sm" variant="ghost" onClick={() => onDeleteKeyword(kw.id)}>
                              <X className="h-3 w-3" />
                            </Button>
                          </div>
                        </div>
                        {stats ? (
                          <div className="gather-keyword-stats">
                            <span className="gather-keyword-stat-text">
                              {stats.total_matches.toLocaleString()} matches
                            </span>
                            <span className="gather-keyword-stat-separator">•</span>
                            <span className={`gather-keyword-relevance ${stats.avg_relevance >= 0.5 ? 'high' : stats.avg_relevance >= 0.3 ? 'medium' : 'low'}`}>
                              {Math.round(stats.avg_relevance * 100)}% avg
                            </span>
                            <div className="gather-relevance-bar" title={`High: ${Math.round(stats.high_relevance_pct)}% | Low: ${Math.round(stats.low_relevance_pct)}%`}>
                              <div
                                className="gather-relevance-bar-high"
                                style={{ width: `${stats.high_relevance_pct}%` }}
                              />
                              <div
                                className="gather-relevance-bar-low"
                                style={{ width: `${stats.low_relevance_pct}%` }}
                              />
                            </div>
                          </div>
                        ) : (
                          <div className="gather-keyword-stats gather-keyword-no-stats">
                            <span>No articles matched yet</span>
                          </div>
                        )}
                      </>
                    )}
                  </div>
                );
              })}

              {/* Add Keyword */}
              <div className="gather-keyword-add">
                <Input
                  placeholder="Add new keyword..."
                  value={newKeyword}
                  onChange={e => setNewKeyword(e.target.value)}
                  onKeyDown={e => {
                    if (e.key === 'Enter') handleAddKeyword();
                  }}
                  disabled={addingKeyword}
                />
                <Button
                  size="sm"
                  onClick={handleAddKeyword}
                  disabled={!newKeyword.trim() || addingKeyword}
                >
                  {addingKeyword ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
                </Button>
              </div>
            </div>
          </div>

          {/* Recent Articles */}
          <div className="gather-detail-section">
            <h4 className="gather-detail-section-title">Recent Articles</h4>
            {loadingArticles ? (
              <div className="gather-detail-loading">
                <Loader2 className="h-5 w-5 animate-spin" />
                <span>Loading articles...</span>
              </div>
            ) : recentArticles.length === 0 ? (
              <div className="gather-detail-empty">
                <FileText className="h-8 w-8" />
                <p>No articles collected yet</p>
              </div>
            ) : (
              <div className="gather-detail-articles">
                {recentArticles.map(article => {
                  // Determine relevance status
                  const isRelevant = article.keyword_relevance_score != null && article.keyword_relevance_score >= 0.39;
                  const isScored = article.keyword_relevance_score != null;

                  // Sentiment styling
                  const sentimentClass = article.sentiment === 'Positive' ? 'positive'
                    : article.sentiment === 'Negative' ? 'negative'
                    : article.sentiment === 'Mixed' ? 'mixed'
                    : 'neutral';

                  return (
                    <HoverCard key={article.id} openDelay={200} closeDelay={100}>
                      <HoverCardTrigger asChild>
                        <a
                          href={article.uri}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="gather-article-item"
                        >
                          <div className="gather-article-title">
                            {article.title || 'Untitled'}
                            <ExternalLink className="h-3 w-3" />
                          </div>
                          <div className="gather-article-meta">
                            <span>
                              {article.source || 'Unknown source'}
                              {article.publication_date && (
                                <span className="gather-article-date">
                                  {' · '}{new Date(article.publication_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
                                </span>
                              )}
                            </span>
                            {isScored ? (
                              <span className={`gather-article-relevance ${isRelevant ? 'gather-relevance-high' : 'gather-relevance-low'}`}>
                                {Math.round(article.keyword_relevance_score! * 100)}%
                              </span>
                            ) : (
                              <span className="gather-article-relevance gather-relevance-unscored">
                                Unscored
                              </span>
                            )}
                          </div>
                          {/* Enrichment badges row - only show if there's content */}
                          {(article.sentiment || article.time_to_impact || article.driver_type || article.category || (onTestProcessArticle && (!isScored || !article.sentiment))) && (
                            <div className="gather-article-enrichment">
                              {article.sentiment && (
                                <Badge variant="outline" className={`gather-enrichment-badge gather-sentiment-${sentimentClass}`}>
                                  {article.sentiment}
                                </Badge>
                              )}
                              {article.time_to_impact && (
                                <Badge variant="outline" className="gather-enrichment-badge gather-time-impact">
                                  {article.time_to_impact}
                                </Badge>
                              )}
                              {article.driver_type && (
                                <Badge variant="outline" className="gather-enrichment-badge gather-driver-type">
                                  {article.driver_type}
                                </Badge>
                              )}
                              {article.category && (
                                <Badge variant="outline" className="gather-enrichment-badge gather-article-category">
                                  {article.category}
                                </Badge>
                              )}
                              {/* Test process button - shows for unscored or unenriched articles */}
                              {onTestProcessArticle && (!isScored || !article.sentiment) && (
                                <button
                                  onClick={(e) => {
                                    e.preventDefault();
                                    e.stopPropagation();
                                    onTestProcessArticle(article.uri, group!.id);
                                  }}
                                  className="gather-article-test-btn"
                                  title="Test LLM enrichment on this article"
                                >
                                  <FlaskConical className="h-3 w-3" />
                                </button>
                              )}
                            </div>
                          )}
                        </a>
                      </HoverCardTrigger>
                      <HoverCardContent className="gather-article-hover-card" side="left" align="start">
                        {/* Scores Section */}
                        <div className="gather-hover-section">
                          <div className="gather-hover-section-title">Relevance Scores</div>
                          <div className="gather-hover-scores">
                            <div className="gather-hover-score-row">
                              <span className="gather-hover-score-label">Keyword Relevance:</span>
                              <span className={`gather-hover-score-value ${isRelevant ? 'high' : 'low'}`}>
                                {article.keyword_relevance_score != null ? `${Math.round(article.keyword_relevance_score * 100)}%` : 'N/A'}
                              </span>
                            </div>
                            <div className="gather-hover-score-row">
                              <span className="gather-hover-score-label">Topic Alignment:</span>
                              <span className="gather-hover-score-value">
                                {article.topic_alignment_score != null ? `${Math.round(article.topic_alignment_score * 100)}%` : 'N/A'}
                              </span>
                            </div>
                          </div>
                          {article.overall_match_explanation && (
                            <p className="gather-hover-explanation">{article.overall_match_explanation}</p>
                          )}
                        </div>

                        {/* Summary */}
                        {article.summary && (
                          <div className="gather-hover-section">
                            <div className="gather-hover-section-title">Summary</div>
                            <p className="gather-hover-summary">{article.summary}</p>
                          </div>
                        )}

                        {/* Sentiment */}
                        {article.sentiment && (
                          <div className="gather-hover-section">
                            <div className="gather-hover-section-title">Sentiment</div>
                            <Badge variant="outline" className={`gather-enrichment-badge gather-sentiment-${sentimentClass}`}>
                              {article.sentiment}
                            </Badge>
                            {article.sentiment_explanation && (
                              <p className="gather-hover-explanation">{article.sentiment_explanation}</p>
                            )}
                          </div>
                        )}

                        {/* Time to Impact */}
                        {article.time_to_impact && (
                          <div className="gather-hover-section">
                            <div className="gather-hover-section-title">Time to Impact</div>
                            <Badge variant="outline" className="gather-enrichment-badge gather-time-impact">
                              {article.time_to_impact}
                            </Badge>
                            {article.time_to_impact_explanation && (
                              <p className="gather-hover-explanation">{article.time_to_impact_explanation}</p>
                            )}
                          </div>
                        )}

                        {/* Driver Type */}
                        {article.driver_type && (
                          <div className="gather-hover-section">
                            <div className="gather-hover-section-title">Driver Type</div>
                            <Badge variant="outline" className="gather-enrichment-badge gather-driver-type">
                              {article.driver_type}
                            </Badge>
                            {article.driver_type_explanation && (
                              <p className="gather-hover-explanation">{article.driver_type_explanation}</p>
                            )}
                          </div>
                        )}

                        {/* Category */}
                        {article.category && (
                          <div className="gather-hover-section">
                            <div className="gather-hover-section-title">Category</div>
                            <Badge variant="secondary">{article.category}</Badge>
                          </div>
                        )}
                      </HoverCardContent>
                    </HoverCard>
                  );
                })}
              </div>
            )}
          </div>
        </ScrollArea>

        <SheetFooter className="gather-detail-footer">
          <div className="gather-detail-actions">
            <Button
              onClick={() => onRunCheck(group.id)}
              disabled={checkingKeywords}
              className="gather-action-button"
            >
              {checkingKeywords ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Running...
                </>
              ) : (
                <>
                  <RefreshCw className="h-4 w-4" />
                  Run Check
                </>
              )}
            </Button>

            {showDeleteConfirm ? (
              <div className="gather-delete-confirm">
                <span>Delete this group?</span>
                <Button variant="destructive" size="sm" onClick={handleDelete}>
                  Yes, Delete
                </Button>
                <Button variant="outline" size="sm" onClick={() => setShowDeleteConfirm(false)}>
                  Cancel
                </Button>
              </div>
            ) : (
              <Button
                variant="outline"
                onClick={() => setShowDeleteConfirm(true)}
                className="gather-danger-button"
              >
                <Trash2 className="h-4 w-4" />
                Delete Group
              </Button>
            )}
          </div>
        </SheetFooter>
      </SheetContent>
    </Sheet>

    {/* Keyword Suggestions Dialog */}
    <Dialog open={!!suggestionDialogKeyword} onOpenChange={(open) => !open && setSuggestionDialogKeyword(null)}>
      <DialogContent className="gather-suggestions-dialog">
        <DialogHeader>
          <DialogTitle className="gather-suggestions-dialog-title">
            <Sparkles className="h-5 w-5 text-purple-500" />
            AI Suggestions for "{suggestionDialogKeyword?.keyword}"
          </DialogTitle>
        </DialogHeader>

        {(() => {
          if (!suggestionDialogKeyword) return null;
          const kwSuggestions = suggestions[suggestionDialogKeyword.id];
          const isLoadingSuggestion = loadingSuggestions === suggestionDialogKeyword.id;

          if (isLoadingSuggestion) {
            return (
              <div className="gather-suggestions-loading">
                <Loader2 className="h-5 w-5 animate-spin" />
                <span>Analyzing keyword performance...</span>
              </div>
            );
          }

          if (kwSuggestions?.error || kwSuggestions?.status === 'insufficient_data') {
            return (
              <div className="gather-suggestions-message">
                <AlertCircle className="h-4 w-4" />
                <span>{kwSuggestions.message || kwSuggestions.error}</span>
              </div>
            );
          }

          if (kwSuggestions?.status === 'good') {
            return (
              <div className="gather-suggestions-good">
                <Check className="h-5 w-5 text-green-600" />
                <div>
                  <strong>Keyword performing well</strong>
                  <p>{kwSuggestions.message || 'No low-relevance articles found. This keyword has good relevance.'}</p>
                </div>
              </div>
            );
          }

          if (kwSuggestions) {
            return (
              <div className="gather-suggestions-content">
                {kwSuggestions.confidence && (
                  <Badge variant="outline" className="gather-confidence-badge">
                    {Math.round(kwSuggestions.confidence * 100)}% confident
                  </Badge>
                )}

                {kwSuggestions.analysis && (
                  <p className="gather-suggestions-analysis">{kwSuggestions.analysis}</p>
                )}

                {/* Replacements */}
                {kwSuggestions.suggestions?.replacements?.length > 0 && (
                  <div className="gather-suggestion-group">
                    <div className="gather-suggestion-group-title">
                      <Replace className="h-3 w-3" />
                      <span>Replace with</span>
                    </div>
                    {kwSuggestions.suggestions.replacements.map((s, i) => (
                      <div key={i} className="gather-suggestion-item">
                        <div className="gather-suggestion-keyword">{s.keyword}</div>
                        <div className="gather-suggestion-reason">{s.reason}</div>
                        <Button
                          size="sm"
                          variant="outline"
                          className="gather-suggestion-apply"
                          disabled={applyingAction !== null}
                          onClick={() => handleApplySuggestion(suggestionDialogKeyword.id, 'replace', s.keyword, s.reason)}
                        >
                          {applyingAction === `${suggestionDialogKeyword.id}-replace-${s.keyword}` ? (
                            <Loader2 className="h-3 w-3 animate-spin" />
                          ) : (
                            <>Apply</>
                          )}
                        </Button>
                      </div>
                    ))}
                  </div>
                )}

                {/* Additions */}
                {kwSuggestions.suggestions?.additions?.length > 0 && (
                  <div className="gather-suggestion-group">
                    <div className="gather-suggestion-group-title">
                      <PlusCircle className="h-3 w-3" />
                      <span>Add alongside</span>
                    </div>
                    {kwSuggestions.suggestions.additions.map((s, i) => (
                      <div key={i} className="gather-suggestion-item">
                        <div className="gather-suggestion-keyword">{s.keyword}</div>
                        <div className="gather-suggestion-reason">{s.reason}</div>
                        <Button
                          size="sm"
                          variant="outline"
                          className="gather-suggestion-apply"
                          disabled={applyingAction !== null}
                          onClick={() => handleApplySuggestion(suggestionDialogKeyword.id, 'add', s.keyword, s.reason)}
                        >
                          {applyingAction === `${suggestionDialogKeyword.id}-add-${s.keyword}` ? (
                            <Loader2 className="h-3 w-3 animate-spin" />
                          ) : (
                            <>Add</>
                          )}
                        </Button>
                      </div>
                    ))}
                  </div>
                )}

                {/* Exclusions */}
                {kwSuggestions.suggestions?.exclusions?.length > 0 && (
                  <div className="gather-suggestion-group">
                    <div className="gather-suggestion-group-title">
                      <MinusCircle className="h-3 w-3" />
                      <span>Exclude terms</span>
                    </div>
                    {kwSuggestions.suggestions.exclusions.map((s, i) => (
                      <div key={i} className="gather-suggestion-item">
                        <div className="gather-suggestion-keyword gather-exclusion">{s.keyword}</div>
                        <div className="gather-suggestion-reason">{s.reason}</div>
                        <Button
                          size="sm"
                          variant="outline"
                          className="gather-suggestion-apply"
                          disabled={applyingAction !== null}
                          onClick={() => handleApplySuggestion(suggestionDialogKeyword.id, 'exclude', s.keyword, s.reason)}
                        >
                          {applyingAction === `${suggestionDialogKeyword.id}-exclude-${s.keyword}` ? (
                            <Loader2 className="h-3 w-3 animate-spin" />
                          ) : (
                            <>Add</>
                          )}
                        </Button>
                      </div>
                    ))}
                  </div>
                )}

                {/* Sample articles with links */}
                {kwSuggestions.sample_low_relevance_articles?.length > 0 ? (
                  <details className="gather-suggestion-samples">
                    <summary>Sample low-relevance articles ({kwSuggestions.sample_low_relevance_articles.length})</summary>
                    <ul>
                      {kwSuggestions.sample_low_relevance_articles.map((article, i) => (
                        <li key={i}>
                          <a href={article.url} target="_blank" rel="noopener noreferrer" className="gather-sample-article-link">
                            {article.title}
                          </a>
                          <span className="gather-sample-relevance">({article.relevance_score}%)</span>
                        </li>
                      ))}
                    </ul>
                  </details>
                ) : kwSuggestions.sample_low_relevance_titles?.length > 0 && (
                  <details className="gather-suggestion-samples">
                    <summary>Sample low-relevance articles</summary>
                    <ul>
                      {kwSuggestions.sample_low_relevance_titles.map((title, i) => (
                        <li key={i}>{title}</li>
                      ))}
                    </ul>
                  </details>
                )}
              </div>
            );
          }

          return (
            <div className="gather-suggestions-loading">
              <span>Loading suggestions...</span>
            </div>
          );
        })()}
      </DialogContent>
    </Dialog>
    </>
  );
}
