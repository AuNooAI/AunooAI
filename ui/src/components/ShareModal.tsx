/**
 * Share Modal - Email sharing for incidents, narratives, and briefings
 * Checks if email service is configured and saves recipient email to localStorage
 */

import { useState, useEffect } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from './ui/dialog';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Loader2, Send, Mail, AlertCircle, CheckCircle2 } from 'lucide-react';

// Types for different share content
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
}

export interface ShareBriefingData {
  type: 'briefing';
  persona: string;
  executive_summary?: string;
  articles?: Array<{ title?: string; headline?: string; executive_takeaway?: string; category?: string; source?: string; date?: string; url?: string }>;
  key_themes?: string[];
}

export type ShareData = ShareIncidentData | ShareNarrativeData | ShareBriefingData;

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

      if (data.type === 'incident') {
        endpoint = '/api/share/incident';
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
        };
      } else if (data.type === 'narrative') {
        endpoint = '/api/share/narrative';
        body = {
          to_email: email,
          narrative_name: data.narrative_name,
          description: data.description,
          key_points: data.key_points,
          topic: data.topic,
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
        setError(errorData.detail || 'Failed to send email');
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
      case 'incident':
        return `Share Incident: ${data.incident_name}`;
      case 'narrative':
        return `Share Narrative: ${data.narrative_name}`;
      case 'briefing':
        return `Share Briefing: ${data.persona}`;
      default:
        return 'Share via Email';
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md w-[calc(100%-2rem)] overflow-hidden">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Mail className="w-5 h-5 text-pink-500" />
            Share via Email
          </DialogTitle>
          <DialogDescription className="text-sm text-gray-500 dark:text-gray-400 truncate">
            {getTitle()}
          </DialogDescription>
        </DialogHeader>

        <div className="py-4">
          {isConfigured === null ? (
            // Loading state
            <div className="flex items-center justify-center py-8">
              <Loader2 className="w-6 h-6 animate-spin text-gray-400" />
            </div>
          ) : !isConfigured ? (
            // Not configured state
            <div className="flex flex-col items-center justify-center py-6 text-center">
              <AlertCircle className="w-12 h-12 text-amber-500 mb-3" />
              <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-1">
                Email Not Configured
              </h3>
              <p className="text-sm text-gray-500 dark:text-gray-400 max-w-xs">
                Email sharing requires the RESEND_API_KEY environment variable to be set.
                Contact your administrator to enable this feature.
              </p>
            </div>
          ) : success ? (
            // Success state
            <div className="flex flex-col items-center justify-center py-6 text-center">
              <CheckCircle2 className="w-12 h-12 text-green-500 mb-3" />
              <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-1">
                Email Sent!
              </h3>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                Successfully shared to {email}
              </p>
            </div>
          ) : (
            // Input state
            <div className="space-y-4">
              <div>
                <Label htmlFor="share-email" className="text-sm font-medium">
                  Recipient Email
                </Label>
                <Input
                  id="share-email"
                  type="email"
                  value={email}
                  onChange={(e) => {
                    setEmail(e.target.value);
                    setError(null);
                  }}
                  placeholder="colleague@company.com"
                  className="mt-1.5 w-full max-w-full"
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

              <p className="text-xs text-gray-500 dark:text-gray-400">
                Your email address will be saved for future shares.
              </p>
            </div>
          )}
        </div>

        <DialogFooter>
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
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default ShareModal;
