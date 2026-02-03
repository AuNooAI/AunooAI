/**
 * Utility functions to parse conversation statistics from Auspex chat messages
 */

export interface SourceLink {
  name: string;
  url: string;
}

export interface ConversationStats {
  totalArticles: number;
  sentimentBreakdown: {
    positive: number;
    neutral: number;
    negative: number;
    mixed: number;
  };
  categoryDistribution: Record<string, number>;
  sourceCount: number;
  topSources: string[];
  sourceLinks: SourceLink[];
  signalTypes: Record<string, number>;
  timeToImpact: Record<string, number>;
}

/**
 * Check if link text is a valid source name (not a URL or generic text)
 */
function isValidLinkText(text: string): boolean {
  const isReasonableLength = text.length > 2 && text.length < 100;
  const isNotUrl = !/^https?:/.test(text);
  const isNotGenericText = text !== 'link' && text !== 'here';
  return isReasonableLength && isNotUrl && isNotGenericText;
}

/**
 * Extract a readable source name from a domain
 */
function extractSourceFromDomain(domain: string): string | null {
  // Remove common prefixes/suffixes
  const cleanDomain = domain.toLowerCase().replace(/^www\./, '').replace(/\.(com|org|net|co\.uk|io)$/, '');

  // Known source mappings
  const knownSources: Record<string, string> = {
    'reuters': 'Reuters',
    'bloomberg': 'Bloomberg',
    'bbc': 'BBC',
    'cnn': 'CNN',
    'cnbc': 'CNBC',
    'nytimes': 'New York Times',
    'washingtonpost': 'Washington Post',
    'wsj': 'Wall Street Journal',
    'theguardian': 'The Guardian',
    'ft': 'Financial Times',
    'economist': 'The Economist',
    'forbes': 'Forbes',
    'businessinsider': 'Business Insider',
    'techcrunch': 'TechCrunch',
    'wired': 'Wired',
    'arstechnica': 'Ars Technica',
    'theverge': 'The Verge',
    'apnews': 'AP News',
    'npr': 'NPR',
    'axios': 'Axios',
    'politico': 'Politico',
    'yahoo': 'Yahoo News',
    'news': 'News',
  };

  if (knownSources[cleanDomain]) {
    return knownSources[cleanDomain];
  }

  // Capitalize first letter for unknown domains (if reasonable length)
  if (cleanDomain.length >= 3 && cleanDomain.length <= 20) {
    return cleanDomain.charAt(0).toUpperCase() + cleanDomain.slice(1);
  }

  return null;
}

const DEFAULT_STATS: ConversationStats = {
  totalArticles: 0,
  sentimentBreakdown: { positive: 0, neutral: 0, negative: 0, mixed: 0 },
  categoryDistribution: {},
  sourceCount: 0,
  topSources: [],
  sourceLinks: [],
  signalTypes: {},
  timeToImpact: {}
};

/**
 * Parse conversation messages to extract statistics about the analysis
 */
export function parseConversationStats(messages: Array<{ role: string; content: string }>): ConversationStats {
  const stats = { ...DEFAULT_STATS };
  stats.sentimentBreakdown = { positive: 0, neutral: 0, negative: 0, mixed: 0 };
  stats.categoryDistribution = {};
  stats.signalTypes = {};
  stats.timeToImpact = {};
  stats.sourceLinks = [];

  const allSources = new Set<string>();
  const sourceLinksMap = new Map<string, string>(); // url -> name

  for (const msg of messages) {
    if (msg.role !== 'assistant') continue;
    const content = msg.content;

    // Parse article counts - look for various patterns
    const articlePatterns = [
      /(\d+)\s*articles?\s*(?:analyzed|found|retrieved|examined)/gi,
      /analyzed\s*(\d+)\s*articles?/gi,
      /found\s*(\d+)\s*articles?/gi,
      /reviewing\s*(\d+)\s*articles?/gi,
      /article\s*count[:\s]+(\d+)/gi
    ];

    for (const pattern of articlePatterns) {
      let match;
      while ((match = pattern.exec(content)) !== null) {
        const count = parseInt(match[1]);
        if (count > stats.totalArticles) {
          stats.totalArticles = count;
        }
      }
    }

    // Parse sentiment distribution from text
    // Look for patterns like "Positive: 45" or "45 positive articles" or "45% positive"
    const sentimentPatterns = [
      { pattern: /positive[:\s]+(\d+)/gi, key: 'positive' as const },
      { pattern: /neutral[:\s]+(\d+)/gi, key: 'neutral' as const },
      { pattern: /negative[:\s]+(\d+)/gi, key: 'negative' as const },
      { pattern: /mixed[:\s]+(\d+)/gi, key: 'mixed' as const },
      { pattern: /(\d+)\s*(?:%\s*)?positive/gi, key: 'positive' as const },
      { pattern: /(\d+)\s*(?:%\s*)?neutral/gi, key: 'neutral' as const },
      { pattern: /(\d+)\s*(?:%\s*)?negative/gi, key: 'negative' as const },
      { pattern: /(\d+)\s*(?:%\s*)?mixed/gi, key: 'mixed' as const }
    ];

    for (const { pattern, key } of sentimentPatterns) {
      let match;
      while ((match = pattern.exec(content)) !== null) {
        const val = parseInt(match[1]);
        if (val > stats.sentimentBreakdown[key]) {
          stats.sentimentBreakdown[key] = val;
        }
      }
    }

    // Parse source mentions from markdown or text
    // Look for news source names commonly found in article citations

    // Extract source names and URLs from markdown links [text](url)
    const markdownLinkPattern = /\[([^\]]+)\]\((https?:\/\/[^\)]+)\)/g;
    let linkMatch;
    while ((linkMatch = markdownLinkPattern.exec(content)) !== null) {
      const linkText = linkMatch[1].trim();
      const fullUrl = linkMatch[2];
      const domain = fullUrl.match(/https?:\/\/([^\/]+)/)?.[1] || '';

      // Use link text if it looks like a source name (not a URL or generic text)
      if (isValidLinkText(linkText)) {
        allSources.add(linkText);
        // Store the full URL with the article title
        if (!sourceLinksMap.has(fullUrl)) {
          sourceLinksMap.set(fullUrl, linkText);
        }
      } else if (domain) {
        // Extract domain name as source (e.g., reuters.com -> Reuters)
        const domainName = extractSourceFromDomain(domain);
        if (domainName) {
          allSources.add(domainName);
          if (!sourceLinksMap.has(fullUrl)) {
            sourceLinksMap.set(fullUrl, domainName);
          }
        }
      }
    }

    // Extract sources from plain URLs
    const urlPattern = /https?:\/\/(?:www\.)?([a-zA-Z0-9-]+)\.[a-zA-Z]{2,}/g;
    let urlMatch;
    while ((urlMatch = urlPattern.exec(content)) !== null) {
      const domainName = extractSourceFromDomain(urlMatch[1]);
      if (domainName) {
        allSources.add(domainName);
      }
    }

    // Look for explicit source mentions
    const sourcePatterns = [
      /(?:from|source|by|via|according to)\s+([A-Z][a-zA-Z\s]+(?:News|Times|Post|Journal|Wire|Report|Today|Herald|Tribune|Magazine|Review|Reuters|Bloomberg|AP|AFP|BBC|CNN|CNBC|Guardian|Washington|New York|Wall Street))/gi,
      /(?:Source|Published by|Reported by)[:\s]+([A-Za-z][A-Za-z\s.]{2,40})/g,
      /cited(?:\s+by)?\s+([A-Z][a-zA-Z\s]{2,30})/g
    ];

    for (const pattern of sourcePatterns) {
      let match;
      while ((match = pattern.exec(content)) !== null) {
        const source = match[1].trim();
        // Filter out generic terms
        if (source.length > 2 && source.length < 50 &&
            !['Source', 'source', 'The', 'This', 'That', 'From'].includes(source)) {
          allSources.add(source);
        }
      }
    }

    // Parse category distribution from structured output
    // Look for category mentions in analysis
    const categoryPattern = /(?:category|topic|theme)[:\s]*["']?([A-Za-z\s&]+)["']?/gi;
    let catMatch;
    while ((catMatch = categoryPattern.exec(content)) !== null) {
      const cat = catMatch[1].trim();
      if (cat.length > 2 && cat.length < 50) {
        stats.categoryDistribution[cat] = (stats.categoryDistribution[cat] || 0) + 1;
      }
    }

    // Parse signal types
    const signalPattern = /(?:signal|trend|indicator)[:\s]*["']?([A-Za-z\s]+)["']?/gi;
    let sigMatch;
    while ((sigMatch = signalPattern.exec(content)) !== null) {
      const sig = sigMatch[1].trim();
      if (sig.length > 2 && sig.length < 50) {
        stats.signalTypes[sig] = (stats.signalTypes[sig] || 0) + 1;
      }
    }

    // Parse time to impact mentions
    const timePatterns = [
      /immediate/gi,
      /short[\s-]?term/gi,
      /medium[\s-]?term/gi,
      /long[\s-]?term/gi,
      /\d+-\d+\s*(?:month|year)s?/gi,
      /\d+\s*(?:month|year)s?/gi
    ];

    for (const pattern of timePatterns) {
      let match;
      while ((match = pattern.exec(content)) !== null) {
        const timeframe = match[0].toLowerCase();
        stats.timeToImpact[timeframe] = (stats.timeToImpact[timeframe] || 0) + 1;
      }
    }
  }

  stats.sourceCount = allSources.size;
  stats.topSources = Array.from(allSources).slice(0, 5);

  // Convert sourceLinksMap to array of SourceLink objects
  stats.sourceLinks = Array.from(sourceLinksMap.entries())
    .map(([url, name]) => ({ name, url }))
    .slice(0, 20); // Limit to 20 article links

  return stats;
}

/**
 * Check if there's enough content for meaningful insights
 */
export function hasEnoughContent(messages: Array<{ role: string; content: string }>): boolean {
  const assistantMessages = messages.filter(m => m.role === 'assistant');
  if (assistantMessages.length === 0) return false;

  const totalContent = assistantMessages.reduce((sum, m) => sum + m.content.length, 0);
  return totalContent > 200; // At least 200 chars of assistant content
}

/**
 * Format a number for display (e.g., 1234 -> "1.2K")
 */
export function formatNumber(num: number): string {
  if (num >= 1000000) {
    return (num / 1000000).toFixed(1) + 'M';
  }
  if (num >= 1000) {
    return (num / 1000).toFixed(1) + 'K';
  }
  return num.toString();
}

/**
 * Backend-computed article stats type (matches ArticleStats in auspexService.ts)
 */
export interface BackendArticleStats {
  total_articles: number;
  sentiment_breakdown: {
    positive: number;
    neutral: number;
    negative: number;
    mixed: number;
    critical: number;
  };
  category_distribution: Record<string, number>;
  source_distribution: Record<string, number>;
  signal_distribution: Record<string, number>;
  time_to_impact_distribution: Record<string, number>;
  date_range: {
    earliest: string | null;
    latest: string | null;
  };
  top_sources: Array<{
    name: string;
    count: number;
    sample_url?: string;
  }>;
}

/**
 * Extract backend-computed article stats from content
 * Looks for <!-- ARTICLE_STATS:...:END_STATS --> markers
 */
export function extractArticleStats(content: string): BackendArticleStats | null {
  const statsPattern = /<!-- ARTICLE_STATS:(.*?):END_STATS -->/s;
  const match = content.match(statsPattern);

  if (!match || !match[1]) {
    return null;
  }

  try {
    const statsJson = match[1].trim();
    const stats = JSON.parse(statsJson) as BackendArticleStats;
    return stats;
  } catch (e) {
    console.warn('Failed to parse article stats:', e);
    return null;
  }
}

/**
 * Remove all special markers from content for display
 * Removes: ARTICLE_STATS, CHART_DATA markers
 */
export function stripMarkers(content: string): string {
  let cleaned = content;

  // Remove article stats markers
  cleaned = cleaned.replace(/<!-- ARTICLE_STATS:.*?:END_STATS -->\n*/gs, '');

  // Remove chart data markers (but keep them - charts are processed separately)
  // Note: Charts are handled by AuspexChatModal, we just clean the display
  cleaned = cleaned.replace(/<!-- CHART_DATA:.*?:END_CHART -->\n*/gs, '');

  // Trim leading/trailing whitespace
  return cleaned.trim();
}

/**
 * Convert backend article stats to the ConversationStats format for display
 */
export function backendStatsToConversationStats(backendStats: BackendArticleStats): ConversationStats {
  return {
    totalArticles: backendStats.total_articles,
    sentimentBreakdown: {
      positive: backendStats.sentiment_breakdown.positive,
      neutral: backendStats.sentiment_breakdown.neutral,
      negative: backendStats.sentiment_breakdown.negative,
      mixed: backendStats.sentiment_breakdown.mixed
    },
    categoryDistribution: backendStats.category_distribution,
    sourceCount: Object.keys(backendStats.source_distribution).length,
    topSources: backendStats.top_sources.map(s => s.name),
    sourceLinks: backendStats.top_sources
      .filter(s => s.sample_url)
      .map(s => ({
        name: s.name,
        url: s.sample_url!
      })),
    signalTypes: backendStats.signal_distribution,
    timeToImpact: backendStats.time_to_impact_distribution
  };
}
