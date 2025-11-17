import React, { useState } from 'react';
import TimelineVisualization from './TimelineVisualization';
import SentimentChart from './SentimentChart';
import DecisionWindows from './DecisionWindows';
import './consensus.css';

interface ConsensusType {
  summary: string;
  distribution: {
    positive: number;
    neutral: number;
    critical: number;
  };
  confidence_level: number;
}

interface TimelineConsensus {
  distribution: { [key: string]: number };
  consensus_window: {
    start_year: number;
    end_year: number;
    label: string;
  };
}

interface ConfidenceLevel {
  majority_agreement: number;
  consensus_strength: 'Strong' | 'Moderate' | 'Emerging';
  evidence_quality: 'High' | 'Medium' | 'Low';
}

interface Outlier {
  scenario: string;
  details: string;
  year: number;
  source_percentage: number;
  reference: string;
}

interface KeyArticle {
  title: string;
  url: string;
  summary: string;
  sentiment: string;
  relevance_score: number;
}

interface DecisionWindow {
  urgency: 'Critical' | 'High' | 'Medium' | 'Low';
  window: string;
  action: string;
  rationale: string;
  owner: string;
  dependencies: string[];
  success_metrics: string[];
}

interface TimeframeAnalysis {
  immediate: string;
  short_term: string;
  mid_term: string;
  key_milestones: Array<{
    year: number;
    milestone: string;
    significance: string;
  }>;
}

interface ConsensusCategoryData {
  category_name: string;
  category_description: string;
  articles_analyzed: number;
  '1_consensus_type': ConsensusType;
  '2_timeline_consensus': TimelineConsensus;
  '3_confidence_level': ConfidenceLevel;
  '4_optimistic_outliers': Outlier[];
  '5_pessimistic_outliers': Outlier[];
  '6_key_articles': KeyArticle[];
  '7_strategic_implications': string;
  '8_key_decision_windows': DecisionWindow[];
  '9_timeframe_analysis': TimeframeAnalysis;
}

interface Article {
  id: number;
  title: string;
  source: string;
  url: string;
  publication_date: string;
}

interface ConsensusCategoryCardProps {
  category: ConsensusCategoryData;
  articleList: Article[];
  color?: string;
  index?: number;
}

const CATEGORY_COLORS = ['#a855f7', '#f97316', '#3b82f6', '#10b981', '#ec4899', '#6366f1'];

const ConsensusCategoryCard: React.FC<ConsensusCategoryCardProps> = ({
  category,
  articleList,
  color,
  index = 0
}) => {
  const [isExpanded, setIsExpanded] = useState(false);

  const consensusType = category['1_consensus_type'];
  const timelineConsensus = category['2_timeline_consensus'];
  const confidenceLevel = category['3_confidence_level'];
  const optimisticOutliers = category['4_optimistic_outliers'] || [];
  const pessimisticOutliers = category['5_pessimistic_outliers'] || [];
  const keyArticles = category['6_key_articles'] || [];
  const strategicImplications = category['7_strategic_implications'];
  const keyDecisionWindows = category['8_key_decision_windows'] || [];
  const timeframeAnalysis = category['9_timeframe_analysis'];

  const categoryColor = color || CATEGORY_COLORS[index % CATEGORY_COLORS.length];
  const consensusPercentage = confidenceLevel.majority_agreement;

  // Normalize sentiment distribution - handle fractions, raw counts, or percentages
  const normalizedDistribution = (() => {
    const { positive, neutral, critical } = consensusType.distribution;
    const sum = positive + neutral + critical;

    // If sum is around 1.0, they're fractions (0.6, 0.3, 0.1) - convert to percentages
    if (sum > 0.9 && sum <= 1.1) {
      return {
        positive: positive * 100,
        neutral: neutral * 100,
        critical: critical * 100,
      };
    }

    // If sum is very small (< 10), they're raw counts (1, 2, 3) - scale to percentages
    if (sum < 10 && sum > 0) {
      return {
        positive: (positive / sum) * 100,
        neutral: (neutral / sum) * 100,
        critical: (critical / sum) * 100,
      };
    }

    // Otherwise assume they're already percentages (60, 30, 10)
    return { positive, neutral, critical };
  })();

  const toggleExpanded = () => {
    setIsExpanded(!isExpanded);
  };

  // Replace numbered citations [1], [2], [3] with clickable article links
  const replaceCitations = (text: string): string => {
    if (!text || !articleList || articleList.length === 0) return text;

    // Replace [1], [2], [3], etc. with article links
    const htmlText = text.replace(/\[(\d+)\]/g, (match, num) => {
      const articleNum = parseInt(num, 10);
      const article = articleList.find(a => a.id === articleNum);

      if (article && article.url) {
        return `<a href="${article.url}" target="_blank" rel="noopener noreferrer" class="citation-link" title="${article.title} - ${article.source}">[${num}]</a>`;
      }

      // If article not found or no URL, return original
      return match;
    });

    return htmlText;
  };

  // Truncate description to first sentence or 80 chars for unexpanded view
  const truncateDescription = (text: string, maxLength: number = 80): string => {
    if (!text) return '';
    // Try to get first sentence
    const firstSentence = text.split(/[.!?]/)[0];
    if (firstSentence && firstSentence.length <= maxLength) {
      return firstSentence;
    }
    // Otherwise truncate at maxLength
    return text.length > maxLength ? text.substring(0, maxLength) + '...' : text;
  };

  const getConfidenceBadgeClass = (strength: string): string => {
    const classMap: { [key: string]: string } = {
      'Strong': 'badge-strong',
      'Moderate': 'badge-moderate',
      'Emerging': 'badge-emerging'
    };
    return `metric-badge ${classMap[strength] || 'badge-moderate'}`;
  };

  return (
    <div
      className={`consensus-card-simple ${isExpanded ? 'expanded' : ''}`}
      onClick={toggleExpanded}
    >
      {/* Unexpanded View - Always Visible */}
      <div className="consensus-card-header">
        {/* Left side: Icon + Title + Description */}
        <div className="consensus-card-title-section">
          <div className="consensus-card-icon" style={{ backgroundColor: categoryColor }}>
            <svg className="brain-icon" width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M15.375 7.75008C15.3741 7.0981 15.1849 6.46025 14.8301 5.91328C14.4753 5.3663 13.97 4.9335 13.375 4.66696V4.50008C13.3743 3.86569 13.1639 3.24931 12.7764 2.74699C12.389 2.24467 11.8462 1.8846 11.2328 1.7229C10.6193 1.56119 9.96965 1.60692 9.38491 1.85297C8.80017 2.09902 8.31323 2.53156 7.99996 3.08321C7.68668 2.53156 7.19974 2.09902 6.615 1.85297C6.03026 1.60692 5.38057 1.56119 4.76713 1.7229C4.15368 1.8846 3.61095 2.24467 3.22349 2.74699C2.83602 3.24931 2.62559 3.86569 2.62496 4.50008V4.66696C2.02949 4.93261 1.52372 5.36507 1.1688 5.91205C0.813878 6.45903 0.625 7.0971 0.625 7.74914C0.625 8.40118 0.813878 9.03926 1.1688 9.58624C1.52372 10.1332 2.02949 10.5657 2.62496 10.8313V11.0001C2.62559 11.6345 2.83602 12.2508 3.22349 12.7532C3.61095 13.2555 4.15368 13.6156 4.76713 13.7773C5.38057 13.939 6.03026 13.8932 6.615 13.6472C7.19974 13.4011 7.68668 12.9686 7.99996 12.417C8.31323 12.9686 8.80017 13.4011 9.38491 13.6472C9.96965 13.8932 10.6193 13.939 11.2328 13.7773C11.8462 13.6156 12.389 13.2555 12.7764 12.7532C13.1639 12.2508 13.3743 11.6345 13.375 11.0001V10.8313C13.97 10.5653 14.4753 10.1329 14.8302 9.58619C15.185 9.03949 15.3742 8.40184 15.375 7.75008ZM5.49996 13.1251C4.94766 13.1253 4.41696 12.9106 4.0203 12.5263C3.62364 12.142 3.39217 11.6184 3.37496 11.0663C3.581 11.1054 3.79024 11.1251 3.99996 11.1251H4.49996C4.59941 11.1251 4.69479 11.0856 4.76512 11.0152C4.83545 10.9449 4.87496 10.8495 4.87496 10.7501C4.87496 10.6506 4.83545 10.5552 4.76512 10.4849C4.69479 10.4146 4.59941 10.3751 4.49996 10.3751H3.99996C3.38035 10.3756 2.78054 10.1569 2.30666 9.75772C1.83278 9.35854 1.51538 8.80459 1.41062 8.19391C1.30586 7.58323 1.42049 6.95517 1.73424 6.42088C2.04798 5.88658 2.54061 5.48049 3.12496 5.27446C3.1981 5.2486 3.26142 5.20069 3.3062 5.13733C3.35097 5.07397 3.375 4.99829 3.37496 4.92071V4.50008C3.37496 3.9365 3.59884 3.39599 3.99735 2.99748C4.39587 2.59896 4.93637 2.37508 5.49996 2.37508C6.06354 2.37508 6.60404 2.59896 7.00256 2.99748C7.40107 3.39599 7.62496 3.9365 7.62496 4.50008V9.06571C7.35599 8.76933 7.02797 8.53253 6.66199 8.37053C6.29601 8.20854 5.90018 8.12493 5.49996 8.12508C5.4005 8.12508 5.30512 8.16459 5.23479 8.23492C5.16446 8.30524 5.12496 8.40062 5.12496 8.50008C5.12496 8.59954 5.16446 8.69492 5.23479 8.76525C5.30512 8.83557 5.4005 8.87508 5.49996 8.87508C6.06354 8.87508 6.60404 9.09896 7.00256 9.49748C7.40107 9.89599 7.62496 10.4365 7.62496 11.0001C7.62496 11.5637 7.40107 12.1042 7.00256 12.5027C6.60404 12.9012 6.06354 13.1251 5.49996 13.1251ZM12 10.3751H11.5C11.4005 10.3751 11.3051 10.4146 11.2348 10.4849C11.1645 10.5552 11.125 10.6506 11.125 10.7501C11.125 10.8495 11.1645 10.9449 11.2348 11.0152C11.3051 11.0856 11.4005 11.1251 11.5 11.1251H12C12.2097 11.1251 12.4189 11.1054 12.625 11.0663C12.6119 11.4835 12.4763 11.8877 12.2351 12.2283C11.9938 12.569 11.6576 12.831 11.2683 12.9817C10.879 13.1324 10.454 13.1652 10.0463 13.0759C9.63851 12.9865 9.2661 12.7791 8.9755 12.4794C8.68491 12.1798 8.489 11.8012 8.41223 11.3909C8.33547 10.9806 8.38124 10.5568 8.54384 10.1723C8.70644 9.78786 8.97867 9.45982 9.32654 9.22912C9.67442 8.99842 10.0825 8.87528 10.5 8.87508C10.5994 8.87508 10.6948 8.83557 10.7651 8.76525C10.8354 8.69492 10.875 8.59954 10.875 8.50008C10.875 8.40062 10.8354 8.30524 10.7651 8.23492C10.6948 8.16459 10.5994 8.12508 10.5 8.12508C10.0997 8.12493 9.7039 8.20854 9.33792 8.37053C8.97195 8.53253 8.64393 8.76933 8.37496 9.06571V4.50008C8.37496 3.9365 8.59884 3.39599 8.99735 2.99748C9.39587 2.59896 9.93637 2.37508 10.5 2.37508C11.0635 2.37508 11.604 2.59896 12.0026 2.99748C12.4011 3.39599 12.625 3.9365 12.625 4.50008V4.92071C12.6249 4.99829 12.6489 5.07397 12.6937 5.13733C12.7385 5.20069 12.8018 5.2486 12.875 5.27446C13.4593 5.48049 13.9519 5.88658 14.2657 6.42088C14.5794 6.95517 14.6941 7.58323 14.5893 8.19391C14.4845 8.80459 14.1671 9.35854 13.6932 9.75772C13.2194 10.1569 12.6196 10.3756 12 10.3751ZM12.875 7.00008C12.875 7.09954 12.8354 7.19492 12.7651 7.26525C12.6948 7.33557 12.5994 7.37508 12.5 7.37508H12.25C11.6864 7.37508 11.1459 7.1512 10.7474 6.75268C10.3488 6.35417 10.125 5.81367 10.125 5.25008V5.00008C10.125 4.90063 10.1645 4.80524 10.2348 4.73492C10.3051 4.66459 10.4005 4.62508 10.5 4.62508C10.5994 4.62508 10.6948 4.66459 10.7651 4.73492C10.8354 4.80524 10.875 4.90063 10.875 5.00008V5.25008C10.875 5.61475 11.0198 5.96449 11.2777 6.22235C11.5355 6.48022 11.8853 6.62508 12.25 6.62508H12.5C12.5994 6.62508 12.6948 6.66459 12.7651 6.73492C12.8354 6.80524 12.875 6.90062 12.875 7.00008ZM3.74996 7.37508H3.49996C3.4005 7.37508 3.30512 7.33557 3.23479 7.26525C3.16447 7.19492 3.12496 7.09954 3.12496 7.00008C3.12496 6.90062 3.16447 6.80524 3.23479 6.73492C3.30512 6.66459 3.4005 6.62508 3.49996 6.62508H3.74996C4.11463 6.62508 4.46437 6.48022 4.72223 6.22235C4.98009 5.96449 5.12496 5.61475 5.12496 5.25008V5.00008C5.12496 4.90063 5.16446 4.80524 5.23479 4.73492C5.30512 4.66459 5.4005 4.62508 5.49996 4.62508C5.59941 4.62508 5.69479 4.66459 5.76512 4.73492C5.83545 4.80524 5.87496 4.90063 5.87496 5.00008V5.25008C5.87496 5.81367 5.65107 6.35417 5.25256 6.75268C4.85404 7.1512 4.31354 7.37508 3.74996 7.37508Z" fill="white"/>
            </svg>
          </div>
          <div>
            <h3 className="consensus-card-title">{category.category_name}</h3>
            {!isExpanded && (
              <p
                className="consensus-card-subtitle"
                dangerouslySetInnerHTML={{
                  __html: replaceCitations(truncateDescription(category.category_description, 100))
                }}
              />
            )}
          </div>
        </div>

        {/* Right side: Consensus Badge + Arrow */}
        <div className="consensus-card-actions">
          <div
            className="consensus-percentage-badge"
            style={{
              backgroundColor: `${categoryColor}20`,
              color: categoryColor,
              border: `1px solid ${categoryColor}40`
            }}
          >
            {consensusPercentage}% Consensus
          </div>
          <div className={`expand-arrow ${isExpanded ? 'rotated' : ''}`}>
            ▼
          </div>
        </div>
      </div>

      {/* Timeline Visualization - Always Visible */}
      <div className="consensus-card-timeline">
        <TimelineVisualization
          timelineConsensus={timelineConsensus}
          optimisticOutliers={optimisticOutliers}
          pessimisticOutliers={pessimisticOutliers}
          color={categoryColor}
        />
      </div>

      {/* Expanded Content - Only visible when expanded */}
      {isExpanded && (
        <div className="consensus-card-expanded-content" onClick={(e) => e.stopPropagation()}>
          {/* Full Description */}
          <div style={{ marginBottom: '24px', fontSize: '15px', lineHeight: '1.6', color: '#374151' }}>
            <p dangerouslySetInnerHTML={{ __html: replaceCitations(category.category_description) }} />
          </div>

          {/* Consensus Metrics */}
          <div className="consensus-metrics">
            <div className="metric-item">
              <div className="metric-label">Consensus Type</div>
              <div className="metric-value">{consensusType.summary}</div>
            </div>
            <div className="metric-item">
              <div className="metric-label">Agreement</div>
              <div className="metric-value">{confidenceLevel.majority_agreement}%</div>
            </div>
            <div className="metric-item">
              <div className="metric-label">Strength</div>
              <div className={getConfidenceBadgeClass(confidenceLevel.consensus_strength)}>
                {confidenceLevel.consensus_strength}
              </div>
            </div>
            <div className="metric-item">
              <div className="metric-label">Evidence Quality</div>
              <div className={getConfidenceBadgeClass(confidenceLevel.evidence_quality)}>
                {confidenceLevel.evidence_quality}
              </div>
            </div>
            <div className="metric-item">
              <div className="metric-label">Articles</div>
              <div className="metric-value">{category.articles_analyzed}</div>
            </div>
          </div>

          {/* Sentiment Distribution */}
          <SentimentChart distribution={normalizedDistribution} />

          {/* Strategic Implications */}
          <div className="strategic-implications-box">
            <div className="section-title-small">
              💡 Strategic Implications
            </div>
            <div
              className="section-content-small"
              dangerouslySetInnerHTML={{ __html: replaceCitations(strategicImplications) }}
            />
          </div>

          {/* Key Decision Windows */}
          {keyDecisionWindows.length > 0 && (
            <DecisionWindows windows={keyDecisionWindows} />
          )}

          {/* Timeframe Analysis */}
          {timeframeAnalysis && (
            <div className="content-section">
              <div className="section-title">
                <span>📅</span>
                <span>Timeframe Analysis</span>
              </div>
              <div className="timeframe-grid">
                <div className="timeframe-box">
                  <div className="timeframe-label">Immediate (0-6 months)</div>
                  <div className="timeframe-content">{timeframeAnalysis.immediate}</div>
                </div>
                <div className="timeframe-box">
                  <div className="timeframe-label">Short-term (6-18 months)</div>
                  <div className="timeframe-content">{timeframeAnalysis.short_term}</div>
                </div>
                <div className="timeframe-box">
                  <div className="timeframe-label">Mid-term (18-36 months)</div>
                  <div className="timeframe-content">{timeframeAnalysis.mid_term}</div>
                </div>
              </div>

              {/* Key Milestones */}
              {timeframeAnalysis.key_milestones && timeframeAnalysis.key_milestones.length > 0 && (
                <div style={{ marginTop: '16px' }}>
                  <div style={{ fontSize: '14px', fontWeight: 600, marginBottom: '12px', color: '#6b7280' }}>
                    Key Milestones
                  </div>
                  <div className="milestones-list">
                    {timeframeAnalysis.key_milestones.map((milestone, index) => (
                      <div key={index} className="milestone-item">
                        <div className="milestone-year">{milestone.year}</div>
                        <div className="milestone-info">
                          <div className="milestone-title">{milestone.milestone}</div>
                          <div className="milestone-significance">{milestone.significance}</div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Outliers */}
          {(optimisticOutliers.length > 0 || pessimisticOutliers.length > 0) && (
            <div className="content-section">
              <div className="section-title">
                <span>🔍</span>
                <span>Outlier Perspectives</span>
              </div>
              <div className="outliers-grid">
                {optimisticOutliers.length > 0 && (
                  <div>
                    <div style={{ fontSize: '14px', fontWeight: 600, marginBottom: '12px', color: '#10b981' }}>
                      Optimistic Outliers
                    </div>
                    {optimisticOutliers.map((outlier, index) => (
                      <div key={index} className="outlier-card optimistic" style={{ marginBottom: '12px' }}>
                        <div className="outlier-scenario">
                          {outlier.scenario} ({outlier.year})
                        </div>
                        <div className="outlier-details">{outlier.details}</div>
                        <div className="outlier-reference">
                          {outlier.source_percentage}% of sources • {outlier.reference}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
                {pessimisticOutliers.length > 0 && (
                  <div>
                    <div style={{ fontSize: '14px', fontWeight: 600, marginBottom: '12px', color: '#ef4444' }}>
                      Pessimistic Outliers
                    </div>
                    {pessimisticOutliers.map((outlier, index) => (
                      <div key={index} className="outlier-card pessimistic" style={{ marginBottom: '12px' }}>
                        <div className="outlier-scenario">
                          {outlier.scenario} ({outlier.year})
                        </div>
                        <div className="outlier-details">{outlier.details}</div>
                        <div className="outlier-reference">
                          {outlier.source_percentage}% of sources • {outlier.reference}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Key Articles */}
          {keyArticles.length > 0 && (
            <div className="content-section">
              <div className="section-title">
                <span>📰</span>
                <span>Key Supporting Articles</span>
              </div>
              <div className="articles-list">
                {keyArticles.slice(0, 5).map((article, index) => (
                  <div key={index} className="article-item">
                    <div className="article-title">
                      <a href={article.url} target="_blank" rel="noopener noreferrer">
                        {article.title}
                      </a>
                      {article.sentiment && (
                        <span style={{
                          marginLeft: '8px',
                          fontSize: '11px',
                          color: article.sentiment === 'positive' ? '#10b981' : article.sentiment === 'critical' ? '#ef4444' : '#6b7280',
                          fontWeight: 600,
                          textTransform: 'uppercase'
                        }}>
                          {article.sentiment}
                        </span>
                      )}
                    </div>
                    <div className="article-summary">{article.summary}</div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default ConsensusCategoryCard;
