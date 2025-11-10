import './ai-disclosure-footer.css';

interface AIDisclosureFooterProps {
  dashboardName: string;
  modelUsed?: string;
  aiTools: string[];
  purpose: string;
}

export function AIDisclosureFooter({
  dashboardName,
  modelUsed,
  aiTools,
  purpose
}: AIDisclosureFooterProps) {
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
            <strong> AI Model:</strong> {modelUsed || aiTools[0]} |
            <strong> Purpose:</strong> {purpose} |
            <strong> Date:</strong> {currentDate}
          </p>
          <p>
            <strong>Author:</strong> {authorText} |
            All AI-generated content has been reviewed and validated. The system cross-references multiple sources and provides inline citations with full transparency.
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
