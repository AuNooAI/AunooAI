import { useEffect, useState } from 'react';
import './ai-disclosure-footer.css';

interface AIDisclosureFooterProps {
  dashboardName: string;
  modelUsed?: string;
  aiTools?: string[];
  purpose: string;
}

// This is a compliance disclosure (EU AI Act Art. 50): the model it names must
// be one that actually runs on this deployment. When the caller can't pass the
// model it used, we resolve the deployment's real model list once rather than
// fall back to a hardcoded vendor name — the old 'GPT-4' default named a model
// these sites do not serve.
let cachedModelNames: string | null = null;
function useDeployedModelNames(enabled: boolean): string | null {
  const [names, setNames] = useState<string | null>(cachedModelNames);
  useEffect(() => {
    if (!enabled || cachedModelNames) return;
    fetch('/api/trend-convergence/models', { credentials: 'include' })
      .then(r => (r.ok ? r.json() : []))
      .then((models: Array<{ name?: string }>) => {
        if (Array.isArray(models) && models.length > 0) {
          cachedModelNames = models.slice(0, 4).map(m => m.name).filter(Boolean).join(', ');
          setNames(cachedModelNames);
        }
      })
      .catch(() => undefined);
  }, [enabled]);
  return names;
}

export function AIDisclosureFooter({
  dashboardName,
  modelUsed,
  aiTools,
  purpose
}: AIDisclosureFooterProps) {
  const deployedNames = useDeployedModelNames(!modelUsed);
  const modelText = modelUsed
    || deployedNames
    || (aiTools && aiTools.length ? aiTools.join(', ') : 'site-configured models');
  // Get user info from session (if available in window object from server-side rendering)
  const userName = (window as any).userSession?.username;
  const userEmail = (window as any).userSession?.email;

  // Build author string
  let authorText = 'Aunoo AI';
  if (userName) {
    authorText += ` with ${userName}`;
    if (userEmail) {
      authorText += ` (${userEmail})`;
    }
  }

  // Get current date
  const currentDate = new Date().toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'long',
    day: 'numeric'
  });

  return (
    <div className="ai-disclosure-footer">
      <div className="ai-disclosure-footer-box">
        <h4 className="ai-disclosure-footer-title">AI Technology Disclosure</h4>
        <div className="ai-disclosure-footer-text">
          <p>
            <strong>Dashboard:</strong> {dashboardName} |
            <strong> AI Model:</strong> {modelText} |
            <strong> Purpose:</strong> {purpose} |
            <strong> Date:</strong> {currentDate}
          </p>
          <p>
            <strong>Author:</strong> {authorText} |
            Contains AI-generated content. The system cross-references multiple sources and provides inline citations; verify against the cited sources before external use.
          </p>
        </div>
      </div>
    </div>
  );
}

// Pre-configured disclosure configurations for each dashboard type
export const dashboardFooterConfigs = {
  consensus: {
    dashboardName: 'Consensus Analysis',
    aiTools: [],
    purpose: 'To analyze convergent themes across multiple sources and identify areas of agreement, emerging consensus, and divergent viewpoints'
  },
  strategic: {
    dashboardName: 'Strategic Recommendations',
    aiTools: [],
    purpose: 'To synthesize actionable strategic insights from analyzed content'
  },
  signals: {
    dashboardName: 'Market Signals & Strategic Risks',
    aiTools: [],
    purpose: 'To identify market trends, risks, and opportunities'
  },
  timeline: {
    dashboardName: 'Impact Timeline',
    aiTools: [],
    purpose: 'To project temporal sequences of anticipated impacts'
  },
  horizons: {
    dashboardName: 'Future Horizons',
    aiTools: [],
    purpose: 'To explore long-term implications and future scenarios'
  }
};
