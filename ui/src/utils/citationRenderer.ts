/**
 * Utility for rendering citations as clickable links
 */

export interface Article {
  id: number;
  url?: string;
  uri?: string;  // Backend uses 'uri' field
  title: string;
  source?: string;
}

/**
 * Transform citation numbers [1], [2], [3] into clickable HTML links
 * @param text Text containing citation numbers like [1], [2], [3]
 * @param articleList List of articles with id, url/uri, title, source
 * @returns HTML string with clickable citation links
 */
export function renderCitationsAsLinks(text: string, articleList: Article[]): string {
  if (!text || !articleList || articleList.length === 0) {
    return text;
  }

  const htmlText = text.replace(/\[(\d+)\]/g, (match, num) => {
    const articleNum = parseInt(num, 10);
    const article = articleList.find(a => a.id === articleNum);

    if (article) {
      // Support both 'url' and 'uri' field names
      const articleUrl = article.url || article.uri;

      if (articleUrl) {
        const title = article.title || 'Untitled';
        const source = article.source || 'Unknown Source';
        return `<a href="${articleUrl}" target="_blank" rel="noopener noreferrer" class="citation-link" title="${title} - ${source}">[${num}]</a>`;
      }
    }

    // If article not found or no URL, return original
    return match;
  });

  return htmlText;
}
