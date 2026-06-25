/**
 * Geopolitical Article Detail Panel - Slide-in panel for full article details
 * Shows rich metadata, summary, hotspot links, and action buttons
 */

import { X, ExternalLink, Clock, Building2, MapPin, TrendingUp, AlertTriangle, Copy, Check, MoreVertical, ThumbsUp, ThumbsDown, Mail, MessageSquare, Loader2 } from 'lucide-react';
import { useState, useRef, useEffect } from 'react';
import type { LinkedArticle, RiskLevel } from '../../services/geopoliticalHotspotsApi';
import { RISK_COLORS } from '../../services/geopoliticalHotspotsApi';
import { recordArticlePreference } from '../../services/newsFeedApi';
import { openAuspexWithQuery } from '../../utils/auspexEvents';
import { ShareModal, type ShareArticleData } from '../ShareModal';
import { PromoteToIncidentModal } from './PromoteToIncidentModal';

interface GeopoliticalArticleDetailPanelProps {
  article: LinkedArticle | null;
  onClose: () => void;
  onHotspotClick?: (hotspotId: number, hotspotName: string) => void;
}

export function GeopoliticalArticleDetailPanel({
  article,
  onClose,
  onHotspotClick,
}: GeopoliticalArticleDetailPanelProps) {
  const [copied, setCopied] = useState(false);
  const [showMenu, setShowMenu] = useState(false);
  const [preferenceLoading, setPreferenceLoading] = useState(false);
  const [preference, setPreference] = useState<'more' | 'less' | null>(null);
  const [showShareModal, setShowShareModal] = useState(false);
  const [showPromoteModal, setShowPromoteModal] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  // Initialize preference from article data when article changes
  useEffect(() => {
    const artPref = (article as any)?.user_preference;
    setPreference(artPref === 'more' || artPref === 'less' ? artPref : null);
  }, [article?.uri]);

  // Close menu when clicking outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setShowMenu(false);
      }
    };
    if (showMenu) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [showMenu]);

  if (!article) return null;

  const formatDate = (dateStr?: string | null) => {
    if (!dateStr) return 'Unknown date';
    try {
      return new Date(dateStr).toLocaleDateString('en-US', {
        weekday: 'short',
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return dateStr;
    }
  };

  const getSentimentColor = (sentiment?: string | null): string => {
    if (!sentiment) return 'text-gray-600 dark:text-gray-400';
    const lower = sentiment.toLowerCase();
    if (lower === 'positive' || lower === 'bullish') return 'text-green-600 dark:text-green-400';
    if (lower === 'negative' || lower === 'bearish') return 'text-red-600 dark:text-red-400';
    if (lower === 'neutral') return 'text-gray-600 dark:text-gray-400';
    return 'text-gray-600 dark:text-gray-400';
  };

  const getSentimentBgColor = (sentiment?: string | null): string => {
    if (!sentiment) return 'bg-gray-100 dark:bg-gray-700';
    const lower = sentiment.toLowerCase();
    if (lower === 'positive' || lower === 'bullish') return 'bg-green-100 dark:bg-green-900/30';
    if (lower === 'negative' || lower === 'bearish') return 'bg-red-100 dark:bg-red-900/30';
    if (lower === 'neutral') return 'bg-gray-100 dark:bg-gray-700';
    return 'bg-gray-100 dark:bg-gray-700';
  };

  const handleCopyLink = async () => {
    try {
      await navigator.clipboard.writeText(article.uri);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy link:', err);
    }
  };

  const handleMenuAction = async (action: string) => {
    setShowMenu(false);

    if (action === 'more' || action === 'less') {
      try {
        setPreferenceLoading(true);
        const prefAction = action as 'more' | 'less';
        // Toggle: if clicking the same preference, clear it
        if (preference === prefAction) {
          await recordArticlePreference(article.uri, 'clear');
          setPreference(null);
        } else {
          await recordArticlePreference(article.uri, prefAction);
          setPreference(prefAction);
        }
      } catch (err) {
        console.error(`Failed to record preference: ${err}`);
      } finally {
        setPreferenceLoading(false);
      }
    } else if (action === 'copy') {
      handleCopyLink();
    } else if (action === 'share') {
      setShowShareModal(true);
    } else if (action === 'promote') {
      setShowPromoteModal(true);
    }
  };

  const handleAskAuspex = () => {
    const hotspotInfo = hotspots
      .map((h) => `${h.name} (${h.risk_level?.toUpperCase() || 'UNKNOWN'} risk, ${h.category || 'unknown category'})`)
      .join(', ');

    const prompt = `Analyze this geopolitical article: "${article.title}"
Article URI: ${article.uri}
Source: ${article.source || 'Unknown source'}

GEOPOLITICAL CONTEXT:
Linked Hotspots: ${hotspotInfo}
Risk Level: ${article.risk_level?.toUpperCase() || 'Unknown'}
${article.category ? `Category: ${article.category}` : ''}
${article.sentiment ? `Sentiment: ${article.sentiment}` : ''}

${article.summary ? `SUMMARY:\n${article.summary}` : ''}

Please provide:
1. Key geopolitical implications and strategic significance
2. Actors and entities involved (states, organizations, groups)
3. Potential escalation risks and scenarios
4. Regional impact assessment
5. Recommended monitoring priorities`;

    openAuspexWithQuery(prompt);
  };

  // Get all unique hotspots
  const hotspots = article.hotspots || [
    {
      id: article.hotspot_id,
      name: article.hotspot_name,
      risk_level: article.risk_level,
      category: article.hotspot_category,
      intensity: article.intensity_score,
    },
  ];

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/20 dark:bg-black/40 z-[1100]"
        onClick={onClose}
      />

      {/* Panel */}
      <div className="fixed inset-y-0 right-0 w-full max-w-lg bg-white dark:bg-gray-900 shadow-2xl z-[1100] overflow-y-auto transform transition-transform duration-300 animate-slide-in-right">
        {/* Header */}
        <div className="sticky top-0 bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-700 z-10">
          <div className="px-6 py-4 flex items-center justify-between">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 flex-1">
              Article Details
            </h2>

            {/* Right side: Menu and Close */}
            <div className="flex items-center gap-1">
              {/* Kebab menu */}
              <div ref={menuRef} className="relative">
                <button
                  onClick={() => setShowMenu(!showMenu)}
                  className="p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-full transition-colors"
                >
                  <MoreVertical className="w-5 h-5 text-gray-700 dark:text-gray-300" />
                </button>
                {showMenu && (
                  <div className="absolute right-0 top-full mt-1 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg z-[1200] py-1 min-w-[160px]">
                    <button
                      onClick={() => handleMenuAction('more')}
                      disabled={preferenceLoading}
                      className={`w-full px-4 py-2 text-left text-sm flex items-center gap-2 disabled:opacity-50 ${
                        preference === 'more'
                          ? 'bg-green-50 dark:bg-green-900/30 text-green-700 dark:text-green-300'
                          : 'text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700'
                      }`}
                    >
                      {preferenceLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <ThumbsUp className={`w-4 h-4 ${preference === 'more' ? 'text-green-600 dark:text-green-400 fill-green-600 dark:fill-green-400' : ''}`} />}
                      {preference === 'more' ? 'More like this ✓' : 'More like this'}
                    </button>
                    <button
                      onClick={() => handleMenuAction('less')}
                      disabled={preferenceLoading}
                      className={`w-full px-4 py-2 text-left text-sm flex items-center gap-2 disabled:opacity-50 ${
                        preference === 'less'
                          ? 'bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-300'
                          : 'text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700'
                      }`}
                    >
                      {preferenceLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <ThumbsDown className={`w-4 h-4 ${preference === 'less' ? 'text-red-600 dark:text-red-400 fill-red-600 dark:fill-red-400' : ''}`} />}
                      {preference === 'less' ? 'Less like this ✓' : 'Less like this'}
                    </button>
                    <button
                      onClick={() => handleMenuAction('copy')}
                      className="w-full px-4 py-2 text-left text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 flex items-center gap-2"
                    >
                      <Copy className="w-4 h-4" />
                      Copy link
                    </button>
                    <button
                      onClick={() => handleMenuAction('share')}
                      className="w-full px-4 py-2 text-left text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 flex items-center gap-2"
                    >
                      <Mail className="w-4 h-4" />
                      Share via email
                    </button>
                    <div className="border-t border-gray-200 dark:border-gray-700 my-1" />
                    <button
                      onClick={() => handleMenuAction('promote')}
                      className="w-full px-4 py-2 text-left text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 flex items-center gap-2"
                    >
                      <AlertTriangle className="w-4 h-4" />
                      Promote to Incident
                    </button>
                  </div>
                )}
              </div>
              <button
                onClick={onClose}
                className="p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-full transition-colors"
              >
                <X className="w-5 h-5 text-gray-700 dark:text-gray-300" />
              </button>
            </div>
          </div>
        </div>

        {/* Content */}
        <div className="p-6">
          {/* Category badge */}
          {article.category && (
            <span className="inline-block bg-pink-100 dark:bg-pink-900/30 text-pink-700 dark:text-pink-300 text-xs font-medium px-2 py-1 rounded mb-3">
              {article.category}
            </span>
          )}

          {/* Title */}
          <h1 className="text-xl font-bold text-gray-900 dark:text-gray-100 leading-tight">
            {article.title || 'Untitled Article'}
          </h1>

          {/* Source and date */}
          <div className="flex items-center gap-2 mt-3 text-sm text-gray-600 dark:text-gray-400">
            <Building2 className="w-4 h-4" />
            <span className="font-medium">{article.source || 'Unknown source'}</span>
            <span className="text-gray-400 dark:text-gray-500">•</span>
            <Clock className="w-4 h-4" />
            <span>{formatDate(article.publication_date)}</span>
          </div>

          {/* Linked Hotspots Section */}
          <div className="mt-6">
            <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wide mb-3 flex items-center gap-2">
              <MapPin className="w-4 h-4" />
              Linked Hotspots ({hotspots.length})
            </h3>
            <div className="space-y-2">
              {hotspots.map((hotspot, idx) => (
                <button
                  key={hotspot.id || idx}
                  onClick={() => onHotspotClick?.(hotspot.id, hotspot.name)}
                  className="w-full text-left p-3 rounded-lg border border-gray-200 dark:border-gray-700 hover:border-pink-300 dark:hover:border-pink-600 hover:bg-pink-50 dark:hover:bg-pink-900/10 transition-colors group"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span
                        className="w-2.5 h-2.5 rounded-full"
                        style={{ backgroundColor: RISK_COLORS[hotspot.risk_level || 'info'] }}
                      />
                      <span className="font-medium text-gray-900 dark:text-gray-100">
                        {hotspot.name}
                      </span>
                    </div>
                    <span
                      className="px-2 py-0.5 text-xs font-medium rounded-full text-white"
                      style={{ backgroundColor: RISK_COLORS[hotspot.risk_level || 'info'] }}
                    >
                      {(hotspot.risk_level || 'info').toUpperCase()}
                    </span>
                  </div>
                  <div className="flex items-center gap-3 mt-1 text-xs text-gray-500 dark:text-gray-400">
                    {hotspot.category && (
                      <span className="capitalize">{hotspot.category}</span>
                    )}
                    {hotspot.intensity > 0 && (
                      <span className="flex items-center gap-1">
                        <TrendingUp className="w-3 h-3" />
                        Intensity: {Math.round(hotspot.intensity)}
                      </span>
                    )}
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* Summary */}
          <div className="mt-6">
            <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wide mb-2">
              Summary
            </h3>
            <p className="text-gray-700 dark:text-gray-300 leading-relaxed">
              {article.summary || 'No summary available.'}
            </p>
          </div>

          {/* Metadata Grid */}
          <div className="mt-6 grid grid-cols-2 gap-4">
            {/* Sentiment */}
            {article.sentiment && (
              <div className={`rounded-lg p-3 ${getSentimentBgColor(article.sentiment)}`}>
                <div className="flex items-center gap-1.5 text-xs text-gray-500 dark:text-gray-400 mb-1">
                  <AlertTriangle className="w-4 h-4" />
                  <span className="uppercase tracking-wide">Sentiment</span>
                </div>
                <div className={`font-medium capitalize ${getSentimentColor(article.sentiment)}`}>
                  {article.sentiment}
                </div>
              </div>
            )}

            {/* Relevance Score */}
            {article.relevance_score !== null && article.relevance_score !== undefined && (
              <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-3">
                <div className="flex items-center gap-1.5 text-xs text-gray-500 dark:text-gray-400 mb-1">
                  <TrendingUp className="w-4 h-4" />
                  <span className="uppercase tracking-wide">Relevance</span>
                </div>
                <div className="font-medium text-gray-900 dark:text-gray-100">
                  {Math.round(article.relevance_score * 100)}%
                </div>
              </div>
            )}

            {/* Mention Type */}
            {article.mention_type && (
              <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-3">
                <div className="text-xs text-gray-500 dark:text-gray-400 mb-1 uppercase tracking-wide">
                  Mention Type
                </div>
                <div className="font-medium text-gray-900 dark:text-gray-100 capitalize">
                  {article.mention_type}
                </div>
              </div>
            )}

            {/* Primary Risk Level */}
            <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-3">
              <div className="text-xs text-gray-500 dark:text-gray-400 mb-1 uppercase tracking-wide">
                Highest Risk
              </div>
              <div className="font-medium flex items-center gap-2">
                <span
                  className="w-2.5 h-2.5 rounded-full"
                  style={{ backgroundColor: RISK_COLORS[article.risk_level] }}
                />
                <span
                  className="capitalize"
                  style={{ color: RISK_COLORS[article.risk_level] }}
                >
                  {article.risk_level}
                </span>
              </div>
            </div>
          </div>

          {/* Action buttons */}
          <div className="mt-8 flex items-center gap-4 flex-wrap">
            {/* Read Original */}
            <a
              href={article.uri}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 px-4 py-2 text-sm bg-pink-500 text-white rounded-lg hover:bg-pink-600 font-medium transition-colors"
            >
              <ExternalLink className="w-4 h-4" />
              Read Original
            </a>

            {/* Ask Auspex */}
            <button
              onClick={handleAskAuspex}
              className="inline-flex items-center gap-1.5 px-4 py-2 text-sm border border-pink-300 dark:border-pink-600 text-pink-600 dark:text-pink-400 rounded-lg hover:bg-pink-50 dark:hover:bg-pink-900/20 font-medium transition-colors"
            >
              <MessageSquare className="w-4 h-4" />
              Ask Auspex
            </button>

            {/* Copy Link */}
            <button
              onClick={handleCopyLink}
              className="inline-flex items-center gap-1.5 px-4 py-2 text-sm border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 font-medium transition-colors"
            >
              {copied ? (
                <>
                  <Check className="w-4 h-4 text-green-500" />
                  Copied!
                </>
              ) : (
                <>
                  <Copy className="w-4 h-4" />
                  Copy Link
                </>
              )}
            </button>
          </div>
        </div>
      </div>

      {/* Share Modal */}
      <ShareModal
        open={showShareModal}
        onOpenChange={setShowShareModal}
        data={{
          type: 'article',
          title: article.title || 'Untitled Article',
          url: article.uri,
          source: article.source,
          summary: article.summary,
          category: article.category,
          sentiment: article.sentiment,
          publication_date: article.publication_date,
        } as ShareArticleData}
      />

      {/* Promote to Incident Modal */}
      <PromoteToIncidentModal
        open={showPromoteModal}
        onOpenChange={setShowPromoteModal}
        article={{
          uri: article.uri,
          title: article.title || 'Untitled Article',
          summary: article.summary,
          source: article.source ? { name: article.source } : undefined,
          category: article.category,
          sentiment: article.sentiment,
          publication_date: article.publication_date,
          topic: 'Geopolitical Hotspots',
        } as any}
        topic="Geopolitical Hotspots"
      />

      {/* Animation keyframes */}
      <style>{`
        @keyframes slide-in-right {
          from {
            transform: translateX(100%);
          }
          to {
            transform: translateX(0);
          }
        }
        .animate-slide-in-right {
          animation: slide-in-right 0.3s ease-out;
        }
      `}</style>
    </>
  );
}
