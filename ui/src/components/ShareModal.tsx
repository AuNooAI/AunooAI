/**
 * Share Modal - Email sharing for incidents, narratives, and briefings
 * Checks if email service is configured and saves recipient email to localStorage
 */

import { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { Button } from './ui/button';
import { Label } from './ui/label';
import { Loader2, Send, Mail, AlertCircle, CheckCircle2 } from 'lucide-react';
import { extractErrorMessage } from '../services/api';

// Types for different share content
export interface ShareArticleData {
  type: 'article';
  title: string;
  url?: string;
  source?: string;
  summary?: string;
  category?: string;
  topic?: string;
  sentiment?: string;
  publication_date?: string;
}

export interface ShareIncidentData {
  type: 'incident';
  incident_name: string;
  incident_type?: string;
  significance?: string;
  description?: string;
  topic?: string;
  entities?: string[];
  strategic_relevance?: string;
  plausibility?: string;
  source_quality?: string;
  credibility_summary?: string;
  timeline?: string | string[];
  investigation_leads?: string[];
  first_seen?: string;
  last_seen?: string;
  articles?: Array<{
    title?: string;
    source?: string;
    url?: string;
    summary?: string;
  }>;
  analyst_notes?: Array<{
    id: string;
    timestamp: string;
    analyst: string;
    comment: string;
  }>;
}

export interface ShareNarrativeData {
  type: 'narrative';
  narrative_name: string;
  description?: string;
  key_points?: string[];
  topic?: string;
  sentiment?: string;
  confidence?: number;
  article_count?: number;
  source_count?: number;
  key_entities?: string[];
  articles?: Array<{
    title?: string;
    source?: string;
    url?: string;
    summary?: string;
    date?: string;
  }>;
}

export interface ShareBriefingData {
  type: 'briefing';
  persona: string;
  executive_summary?: string;
  articles?: Array<{
    title?: string;
    headline?: string;
    executive_takeaway?: string;
    strategic_relevance?: string;
    category?: string;
    source?: string;
    date?: string;
    url?: string;
    summary?: string;
    signal_strength?: string;
    risk_opportunity?: string;
    time_horizon?: string;
  }>;
  key_themes?: string[];
}

export interface ShareBriefingCardData {
  type: 'briefing_card';
  title: string;
  headline?: string;
  executive_takeaway?: string;
  strategic_relevance?: string;
  category?: string;
  signal_strength?: string;
  risk_opportunity?: string;
  time_horizon?: string;
  source?: string;
  date?: string;
  url?: string;
  summary?: string;
  executive_actions?: string[];
  scores?: {
    relevance?: number;
    impact?: number;
    actionability?: number;
    timeliness?: number;
    credibility?: number;
    overall?: number;
  };
}

export interface ShareIncidentsData {
  type: 'incidents';
  topic?: string;
  incidents: Array<{
    incident_name: string;
    incident_type?: string;
    significance?: string;
    description?: string;
    entities?: string[];
    strategic_relevance?: string;
    plausibility?: string;
    source_quality?: string;
    articles?: Array<{
      title?: string;
      source?: string;
      url?: string;
      summary?: string;
    }>;
    analyst_notes?: Array<{
      id: string;
      timestamp: string;
      analyst: string;
      comment: string;
    }>;
  }>;
}

export interface ShareEmergingTopicData {
  type: 'emerging_topic';
  topic_id?: number;
  topic_label: string;
  topic_description?: string;
  score?: number;
  urgency?: string;
  velocity?: string;
  article_count?: number;
  key_themes?: string[];
  key_entities?: string[];
  why_emerging?: string;
  // Enhanced fields for full topic details
  key_takeaway?: string;
  trend_score?: {
    volume?: number;
    velocity?: number;
    diversity?: number;
    novelty?: number;
    composite?: number;
  };
  actors?: {
    companies?: string[];
    people?: string[];
    organizations?: string[];
  };
  events?: {
    trigger_event?: string;
    timeline?: Array<string | { date?: string; event?: string }>;
    current_status?: string;
  };
  implications?: {
    industry_impact?: string;
    regulatory?: string;
    market?: string;
  };
  organization_implications?: {
    strategic_relevance?: string;
    stakeholder_impact?: string;
    risk_assessment?: string;
    recommended_response?: string;
  };
  articles?: Array<{
    title?: string;
    news_source?: string;
    publication_date?: string;
    uri?: string;
  }>;
}

export interface ShareExecutiveSummaryData {
  type: 'executive_summary';
  topic_title: string;
  research_topic?: string;
  primary_horizon?: string;
  horizon_label?: string;
  opening_statement?: string;
  consensus_percentage?: number;
  minority_view?: {
    percentage_range: string;
    statement: string;
  };
  primary_signal?: string;
  decision_fork?: {
    condition_a?: {
      condition: string;
      outcome: string;
    };
    condition_b?: {
      condition: string;
      outcome: string;
    };
  };
  action_window?: {
    assessment?: { timeframe: string; action: string };
    positioning?: { timeframe: string; action: string };
  };
  source_scenarios?: string[];
}

export interface ShareDeskBriefingData {
  type: 'desk_briefing';
  briefing_id: number;
  name: string;
  description?: string;
  status?: 'draft' | 'finalized';
  synthesis?: string;
  themes?: Array<{
    theme_name: string;
    description?: string;
  }>;
  priority_actions?: Array<{
    action: string;
    urgency?: string;
    rationale?: string;
  }>;
  articles?: Array<{
    title?: string;
    source?: string;
    uri?: string;
    summary?: string;
    category?: string;
  }>;
  incidents?: Array<{
    name: string;
    type?: string;
    significance?: string;
    description?: string;
    entities?: string[];
  }>;
  emerging_topics?: Array<{
    name: string;
    summary?: string;
    trend_score?: number;
    velocity?: string;
  }>;
}

export type ShareData = ShareArticleData | ShareIncidentData | ShareNarrativeData | ShareBriefingData | ShareBriefingCardData | ShareIncidentsData | ShareEmergingTopicData | ShareExecutiveSummaryData | ShareDeskBriefingData;

interface ShareModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  data: ShareData;
  onSuccess?: () => void;
}

const LOCAL_STORAGE_KEY = 'aunoo_share_email';

export function ShareModal({ open, onOpenChange, data, onSuccess }: ShareModalProps) {
  const [email, setEmail] = useState('');
  const [isConfigured, setIsConfigured] = useState<boolean | null>(null);
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [includeNotes, setIncludeNotes] = useState(true);

  // Check if sharing content is an incident type (for showing checkbox)
  const isIncidentType = (): boolean => {
    return data.type === 'incident' || data.type === 'incidents';
  };

  // Count analyst notes across incidents
  const getNotesCount = (): number => {
    if (data.type === 'incident') {
      return data.analyst_notes?.length ?? 0;
    }
    if (data.type === 'incidents') {
      return data.incidents.reduce((sum, i) => sum + (i.analyst_notes?.length ?? 0), 0);
    }
    return 0;
  };

  // Load saved email and check configuration on mount
  useEffect(() => {
    if (open) {
      // Load saved email
      const savedEmail = localStorage.getItem(LOCAL_STORAGE_KEY);
      if (savedEmail) {
        setEmail(savedEmail);
      }

      // Check if email is configured
      checkEmailStatus();

      // Reset state
      setError(null);
      setSuccess(false);
    }
  }, [open]);

  const checkEmailStatus = async () => {
    try {
      const response = await fetch('/api/email/status', {
        credentials: 'include',
      });
      if (response.ok) {
        const data = await response.json();
        setIsConfigured(data.configured);
      } else {
        setIsConfigured(false);
      }
    } catch (err) {
      console.error('Failed to check email status:', err);
      setIsConfigured(false);
    }
  };

  const handleSend = async () => {
    if (!email.trim()) {
      setError('Please enter an email address');
      return;
    }

    // Basic email validation
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(email)) {
      setError('Please enter a valid email address');
      return;
    }

    setIsSending(true);
    setError(null);

    // Save email to localStorage
    localStorage.setItem(LOCAL_STORAGE_KEY, email);

    try {
      let endpoint: string;
      let body: Record<string, unknown>;

      if (data.type === 'article') {
        endpoint = '/api/share/article';
        body = {
          to_email: email,
          title: data.title,
          url: data.url,
          source: data.source,
          summary: data.summary,
          category: data.category,
          topic: data.topic,
          sentiment: data.sentiment,
          publication_date: data.publication_date,
        };
      } else if (data.type === 'incident') {
        endpoint = '/api/share/incident';
        const notesToSend = includeNotes ? data.analyst_notes : undefined;
        console.log('[ShareModal] DEBUG - data.analyst_notes:', JSON.stringify(data.analyst_notes));
        console.log('[ShareModal] DEBUG - includeNotes:', includeNotes);
        console.log('[ShareModal] DEBUG - notesToSend:', JSON.stringify(notesToSend));
        body = {
          to_email: email,
          incident_name: data.incident_name,
          incident_type: data.incident_type,
          significance: data.significance,
          description: data.description,
          topic: data.topic,
          entities: data.entities,
          strategic_relevance: data.strategic_relevance,
          plausibility: data.plausibility,
          source_quality: data.source_quality,
          credibility_summary: data.credibility_summary,
          timeline: data.timeline,
          investigation_leads: data.investigation_leads,
          first_seen: data.first_seen,
          last_seen: data.last_seen,
          articles: data.articles,
          analyst_notes: notesToSend,
        };
      } else if (data.type === 'incidents') {
        endpoint = '/api/share/incidents';
        // Include or exclude notes based on checkbox
        const incidentsToShare = includeNotes
          ? data.incidents
          : data.incidents.map(i => ({ ...i, analyst_notes: undefined }));
        body = {
          to_email: email,
          topic: data.topic,
          incidents: incidentsToShare,
        };
      } else if (data.type === 'narrative') {
        endpoint = '/api/share/narrative';
        body = {
          to_email: email,
          narrative_name: data.narrative_name,
          description: data.description,
          key_points: data.key_points,
          topic: data.topic,
          sentiment: data.sentiment,
          confidence: data.confidence,
          article_count: data.article_count,
          source_count: data.source_count,
          key_entities: data.key_entities,
          articles: data.articles,
        };
      } else if (data.type === 'emerging_topic') {
        endpoint = '/api/share/emerging-topic';
        body = {
          to_email: email,
          topic_id: data.topic_id,
          topic_label: data.topic_label,
          topic_description: data.topic_description,
          score: data.score,
          urgency: data.urgency,
          velocity: data.velocity,
          article_count: data.article_count,
          key_themes: data.key_themes,
          key_entities: data.key_entities,
          why_emerging: data.why_emerging,
          // Enhanced fields
          key_takeaway: data.key_takeaway,
          trend_score: data.trend_score,
          actors: data.actors,
          events: data.events,
          implications: data.implications,
          articles: data.articles,
        };
      } else if (data.type === 'briefing_card') {
        endpoint = '/api/share/briefing-card';
        body = {
          to_email: email,
          title: data.title,
          headline: data.headline,
          executive_takeaway: data.executive_takeaway,
          strategic_relevance: data.strategic_relevance,
          category: data.category,
          signal_strength: data.signal_strength,
          risk_opportunity: data.risk_opportunity,
          time_horizon: data.time_horizon,
          source: data.source,
          date: data.date,
          url: data.url,
          summary: data.summary,
          executive_actions: data.executive_actions,
          scores: data.scores,
        };
      } else if (data.type === 'executive_summary') {
        endpoint = '/api/share/executive-summary';
        body = {
          to_email: email,
          topic_title: data.topic_title,
          research_topic: data.research_topic,
          primary_horizon: data.primary_horizon,
          horizon_label: data.horizon_label,
          opening_statement: data.opening_statement,
          consensus_percentage: data.consensus_percentage,
          minority_view: data.minority_view,
          primary_signal: data.primary_signal,
          decision_fork: data.decision_fork,
          action_window: data.action_window,
          source_scenarios: data.source_scenarios,
        };
      } else if (data.type === 'desk_briefing') {
        endpoint = `/api/desk-briefings/${data.briefing_id}/share`;
        body = {
          to_email: email,
        };
      } else {
        endpoint = '/api/share/briefing';
        body = {
          to_email: email,
          persona: data.persona,
          executive_summary: data.executive_summary,
          articles: data.articles,
          key_themes: data.key_themes,
        };
      }

      const response = await fetch(endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify(body),
      });

      if (response.ok) {
        setSuccess(true);
        onSuccess?.();
        // Auto-close after success
        setTimeout(() => {
          onOpenChange(false);
        }, 1500);
      } else {
        const errorData = await response.json();
        setError(extractErrorMessage(errorData, 'Failed to send email'));
      }
    } catch (err) {
      console.error('Error sending share email:', err);
      setError('Failed to send email. Please try again.');
    } finally {
      setIsSending(false);
    }
  };

  // Get title based on share type
  const getTitle = () => {
    switch (data.type) {
      case 'article':
        return `Share Article: ${data.title.slice(0, 50)}${data.title.length > 50 ? '...' : ''}`;
      case 'incident':
        return `Share Incident: ${data.incident_name}`;
      case 'incidents':
        return `Share ${data.incidents.length} Incident${data.incidents.length > 1 ? 's' : ''}${data.topic ? ` - ${data.topic}` : ''}`;
      case 'narrative':
        return `Share Narrative: ${data.narrative_name}`;
      case 'briefing':
        return `Share Briefing: ${data.persona}`;
      case 'briefing_card':
        return `Share: ${data.title.slice(0, 50)}${data.title.length > 50 ? '...' : ''}`;
      case 'emerging_topic':
        return `Share Emerging Topic: ${data.topic_label}`;
      case 'executive_summary':
        return `Share Executive Summary: ${data.topic_title}`;
      case 'desk_briefing':
        return `Share Briefing: ${data.name}`;
      default:
        return 'Share via Email';
    }
  };

  if (!open) return null;

  const modalContent = (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-[1100] bg-black/50"
        onClick={() => onOpenChange(false)}
      />

      {/* Modal */}
      <div
        className="fixed z-[1100] bg-white dark:bg-gray-800 rounded-lg shadow-xl border border-gray-200 dark:border-gray-700 p-6"
        style={{
          top: '50%',
          left: '50%',
          transform: 'translate(-50%, -50%)',
          width: '380px',
          maxWidth: 'calc(100vw - 32px)',
        }}
      >
        {/* Close button */}
        <button
          onClick={() => onOpenChange(false)}
          className="absolute top-4 right-4 text-gray-500 hover:text-gray-600 dark:hover:text-gray-400"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>

        {/* Header */}
        <div className="mb-4 pr-8">
          <h2 className="text-lg font-semibold flex items-center gap-2 text-gray-900 dark:text-gray-100">
            <Mail className="w-5 h-5 text-pink-500" />
            Share via Email
          </h2>
          <p className="text-sm text-gray-500 dark:text-gray-300 truncate mt-1">
            {getTitle()}
          </p>
        </div>

        {/* Content */}
        <div className="py-2">
          {isConfigured === null ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="w-6 h-6 animate-spin text-gray-500" />
            </div>
          ) : !isConfigured ? (
            <div className="flex flex-col items-center justify-center py-6 text-center">
              <AlertCircle className="w-12 h-12 text-amber-500 mb-3" />
              <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-1">
                Email Not Configured
              </h3>
              <p className="text-sm text-gray-500 dark:text-gray-300">
                Email sharing requires the RESEND_API_KEY environment variable to be set.
                Contact your administrator to enable this feature.
              </p>
            </div>
          ) : success ? (
            <div className="flex flex-col items-center justify-center py-6 text-center">
              <CheckCircle2 className="w-12 h-12 text-green-500 mb-3" />
              <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-1">
                Email Sent!
              </h3>
              <p className="text-sm text-gray-500 dark:text-gray-300">
                Successfully shared to {email}
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              <div>
                <Label htmlFor="share-email" className="text-sm font-medium block text-gray-700 dark:text-gray-400">
                  Recipient Email
                </Label>
                <input
                  id="share-email"
                  type="email"
                  value={email}
                  onChange={(e) => {
                    setEmail(e.target.value);
                    setError(null);
                  }}
                  placeholder="colleague@company.com"
                  style={{ width: '100%', boxSizing: 'border-box' }}
                  className="mt-1.5 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-pink-500 disabled:opacity-50"
                  disabled={isSending}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !isSending) {
                      handleSend();
                    }
                  }}
                />
                {error && (
                  <p className="text-sm text-red-500 mt-1.5 flex items-center gap-1">
                    <AlertCircle className="w-3.5 h-3.5" />
                    {error}
                  </p>
                )}
              </div>
              {/* Include Analyst Notes checkbox - show for all incidents */}
              {isIncidentType() && (
                <label className={`flex items-center gap-2 ${getNotesCount() > 0 ? 'cursor-pointer' : 'cursor-not-allowed opacity-60'}`}>
                  <input
                    type="checkbox"
                    checked={includeNotes && getNotesCount() > 0}
                    onChange={(e) => setIncludeNotes(e.target.checked)}
                    className="w-4 h-4 rounded border-gray-300 dark:border-gray-600 text-pink-500 focus:ring-pink-500"
                    disabled={isSending || getNotesCount() === 0}
                  />
                  <span className="text-sm text-gray-700 dark:text-gray-300">
                    Include analyst notes
                    {getNotesCount() > 0 ? (
                      <span className="text-gray-500 dark:text-gray-400 ml-1">
                        ({getNotesCount()} note{getNotesCount() !== 1 ? 's' : ''})
                      </span>
                    ) : (
                      <span className="text-gray-400 dark:text-gray-500 ml-1">(none)</span>
                    )}
                  </span>
                </label>
              )}
              <p className="text-xs text-gray-500 dark:text-gray-300">
                Your email address will be saved for future shares.
              </p>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-2 mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
          {isConfigured && !success && (
            <>
              <Button
                variant="ghost"
                onClick={() => onOpenChange(false)}
                disabled={isSending}
              >
                Cancel
              </Button>
              <Button
                onClick={handleSend}
                disabled={isSending || !email.trim()}
                className="bg-pink-500 hover:bg-pink-600"
              >
                {isSending ? (
                  <>
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    Sending...
                  </>
                ) : (
                  <>
                    <Send className="w-4 h-4 mr-2" />
                    Send Email
                  </>
                )}
              </Button>
            </>
          )}
          {(!isConfigured || success) && (
            <Button variant="ghost" onClick={() => onOpenChange(false)}>
              Close
            </Button>
          )}
        </div>
      </div>
    </>
  );

  return createPortal(modalContent, document.body);
}

export default ShareModal;
