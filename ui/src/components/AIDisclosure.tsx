import { Info } from 'lucide-react';
import * as Tooltip from '@radix-ui/react-tooltip';
import './ai-disclosure.css';

interface AIDisclosureProps {
  dashboardName: string;
  aiTools: string[];
  purpose: string;
  position?: 'top' | 'bottom' | 'left' | 'right';
}

export function AIDisclosure({
  dashboardName,
  aiTools,
  purpose,
  position = 'top'
}: AIDisclosureProps) {
  return (
    <Tooltip.Provider>
      <Tooltip.Root>
        <Tooltip.Trigger asChild>
          <button
            className="ai-disclosure-trigger"
            aria-label="AI Usage Disclosure"
          >
            <Info className="ai-disclosure-icon" />
            <span className="ai-disclosure-label">AI Disclosure</span>
          </button>
        </Tooltip.Trigger>
        <Tooltip.Portal>
          <Tooltip.Content
            className="ai-disclosure-content"
            side={position}
            sideOffset={5}
          >
            <div className="ai-disclosure-container">
              <h4 className="ai-disclosure-title">AI Technology Disclosure</h4>
              <div className="ai-disclosure-body">
                <p className="ai-disclosure-intro">
                  During the preparation of <strong>{dashboardName}</strong>, the following AI technologies were used:
                </p>
                <div className="ai-disclosure-section">
                  <strong>AI Tools:</strong> {aiTools.join(', ')}
                </div>
                <div className="ai-disclosure-section">
                  <strong>Purpose:</strong> {purpose}
                </div>
                <div className="ai-disclosure-section">
                  <strong>Review Process:</strong> All AI-generated content has been reviewed and validated.
                  The system cross-references multiple sources, provides inline citations, and maintains
                  full transparency about article sources.
                </div>
                <div className="ai-disclosure-section">
                  <strong>Author Responsibility:</strong> The content creator takes full responsibility for
                  the accuracy and integrity of this analysis. All cited sources are available for review.
                </div>
                <div className="ai-disclosure-section">
                  <strong>Methodology:</strong> Analysis is based on {aiTools[0]} processing of curated
                  article databases. Specific prompts, parameters, and review processes are documented in
                  the system's methodology appendix.
                </div>
              </div>
            </div>
            <Tooltip.Arrow className="ai-disclosure-arrow" />
          </Tooltip.Content>
        </Tooltip.Portal>
      </Tooltip.Root>
    </Tooltip.Provider>
  );
}

// Pre-configured disclosure configurations for each dashboard type
export const dashboardConfigs = {
  consensus: {
    dashboardName: 'Consensus Analysis',
    aiTools: ['GPT-4', 'OpenAI Embeddings'],
    purpose: 'To analyze convergent themes across multiple sources and identify areas of agreement, emerging consensus, and divergent viewpoints'
  },
  strategic: {
    dashboardName: 'Strategic Recommendations',
    aiTools: ['GPT-4', 'OpenAI Embeddings'],
    purpose: 'To synthesize actionable strategic insights from analyzed content'
  },
  signals: {
    dashboardName: 'Market Signals & Strategic Risks',
    aiTools: ['GPT-4', 'OpenAI Embeddings'],
    purpose: 'To identify market trends, risks, and opportunities'
  },
  timeline: {
    dashboardName: 'Impact Timeline',
    aiTools: ['GPT-4', 'OpenAI Embeddings'],
    purpose: 'To project temporal sequences of anticipated impacts'
  },
  horizons: {
    dashboardName: 'Future Horizons',
    aiTools: ['GPT-4', 'OpenAI Embeddings'],
    purpose: 'To explore long-term implications and future scenarios'
  }
};
