import { useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { ExternalLink, X } from 'lucide-react';
import './article-citations.css';

interface Article {
  id: number;
  title: string;
  uri: string;
  source?: string;
  published_at?: string;
  retrieved_at?: string;
}

interface ArticleCitationsProps {
  dashboardType: 'consensus' | 'strategic' | 'market-signals' | 'timeline' | 'horizons';
  analysisId: string;
  topic: string;
}

export function ArticleCitations({ dashboardType, analysisId, topic }: ArticleCitationsProps) {
  const [articles, setArticles] = useState<Article[]>([]);
  const [loading, setLoading] = useState(false);
  const [showModal, setShowModal] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchArticles = async () => {
    setLoading(true);
    setError(null);
    try {
      // Standardized endpoint paths
      const endpoint = `/api/trend-convergence/${dashboardType}/${analysisId}/articles?topic=${encodeURIComponent(topic)}`;
      const response = await fetch(endpoint);

      if (!response.ok) {
        throw new Error(`Failed to fetch articles: ${response.statusText}`);
      }

      const data = await response.json();
      setArticles(data.articles || []);
    } catch (error) {
      console.error('Failed to fetch articles:', error);
      setError('Failed to load reference articles. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const handleOpen = () => {
    setShowModal(true);
    if (articles.length === 0) {
      fetchArticles();
    }
  };

  const handleDownloadTxt = () => {
    if (articles.length === 0) return;

    let txtContent = `Reference Articles - ${dashboardType}\n`;
    txtContent += `Total Articles: ${articles.length}\n`;
    txtContent += `Topic: ${topic}\n`;
    txtContent += `Generated: ${new Date().toLocaleString()}\n`;
    txtContent += '\n' + '='.repeat(80) + '\n\n';

    articles.forEach((article, idx) => {
      txtContent += `${idx + 1}. ${article.title || 'Untitled Article'}\n`;
      if (article.source) {
        txtContent += `   Source: ${article.source}\n`;
      }
      if (article.published_at) {
        txtContent += `   Published: ${new Date(article.published_at).toLocaleDateString()}\n`;
      }
      if (article.uri) {
        txtContent += `   URL: ${article.uri}\n`;
      }
      txtContent += '\n';
    });

    const blob = new Blob([txtContent], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `references-${dashboardType}-${Date.now()}.txt`;
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <>
      <button
        onClick={handleOpen}
        className="article-citations-trigger"
        aria-label="View reference articles"
      >
        <span>References</span>
      </button>

      <Dialog.Root open={showModal} onOpenChange={setShowModal}>
        <Dialog.Portal>
          <Dialog.Overlay className="article-citations-overlay" />
          <Dialog.Content className="article-citations-content">
            <div className="article-citations-header">
              <Dialog.Title className="article-citations-title">
                Reference Articles
              </Dialog.Title>
              <Dialog.Description className="article-citations-description">
                Articles analyzed for this dashboard ({articles.length} total)
              </Dialog.Description>
              <Dialog.Close asChild>
                <button className="article-citations-close" aria-label="Close">
                  <X />
                </button>
              </Dialog.Close>
            </div>

            <div className="article-citations-body">
              {loading ? (
                <div className="article-citations-loading">
                  <div className="spinner"></div>
                  <p>Loading articles...</p>
                </div>
              ) : error ? (
                <div className="article-citations-error">
                  <p>{error}</p>
                  <button onClick={fetchArticles} className="retry-button">
                    Retry
                  </button>
                </div>
              ) : articles.length === 0 ? (
                <p className="article-citations-empty">No articles found.</p>
              ) : (
                <div className="article-citations-list">
                  {articles.map((article, idx) => (
                    <div
                      key={article.id || idx}
                      className="article-citations-item"
                    >
                      <div className="article-citations-item-content">
                        {article.uri ? (
                          <a
                            href={article.uri}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="article-citations-item-title-link"
                          >
                            <h4 className="article-citations-item-title">
                              {idx + 1}. {article.title || 'Untitled Article'}
                            </h4>
                          </a>
                        ) : (
                          <h4 className="article-citations-item-title">
                            {idx + 1}. {article.title || 'Untitled Article'}
                          </h4>
                        )}
                        {article.source && (
                          <p className="article-citations-item-source">
                            Source: {article.source}
                          </p>
                        )}
                        {article.published_at && (
                          <p className="article-citations-item-date">
                            Published: {new Date(article.published_at).toLocaleDateString()}
                          </p>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="article-citations-footer">
              <button
                onClick={handleDownloadTxt}
                disabled={articles.length === 0}
                className="article-citations-download-button"
              >
                Download as TXT
              </button>
              <Dialog.Close asChild>
                <button className="article-citations-close-button">
                  Close
                </button>
              </Dialog.Close>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </>
  );
}
