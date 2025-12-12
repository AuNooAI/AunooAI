/**
 * Narrative Theme Card - Individual narrative/theme display
 * Shows AI-identified narrative patterns
 */

import { BookOpen, ChevronRight, ExternalLink } from 'lucide-react';
import { type TopStory, type RelatedArticle } from '../../services/newsFeedApi';
import { Card, CardContent } from '../ui/card';
import { ArticleBiasIndicator } from './ArticleBiasIndicator';

interface NarrativeThemeCardProps {
  story: TopStory;
  expanded?: boolean;
  onToggleExpand?: () => void;
}

export function NarrativeThemeCard({
  story,
  expanded = false,
  onToggleExpand
}: NarrativeThemeCardProps) {
  return (
    <Card className="overflow-hidden hover:shadow-md transition-shadow">
      <CardContent className="p-4">
        {/* Header */}
        <div className="flex items-start gap-3">
          <div className="p-2 bg-indigo-100 rounded-lg">
            <BookOpen className="w-4 h-4 text-indigo-600" />
          </div>
          <div className="flex-1 min-w-0">
            <h3 className="font-semibold text-gray-900 line-clamp-2">
              {story.headline}
            </h3>
            <p className="mt-1 text-sm text-gray-600 line-clamp-2">
              {story.summary}
            </p>
          </div>
        </div>

        {/* Perspective Breakdown */}
        {story.perspective_breakdown && Object.keys(story.perspective_breakdown).length > 0 && (
          <div className="mt-4 space-y-2">
            <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
              Perspectives
            </h4>
            <div className="space-y-2">
              {Object.entries(story.perspective_breakdown).map(([perspective, points]) => (
                <div key={perspective} className="flex items-start gap-2">
                  <span className={`text-xs px-2 py-0.5 rounded font-medium ${getPerspectiveStyle(perspective)}`}>
                    {perspective}
                  </span>
                  <ul className="text-xs text-gray-600 space-y-1 flex-1">
                    {(points as string[]).slice(0, 2).map((point, i) => (
                      <li key={i} className="line-clamp-1">• {point}</li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Primary Article */}
        <div className="mt-4 p-3 bg-gray-50 rounded-lg">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-gray-500">Primary Source</span>
            <ArticleBiasIndicator
              bias={story.primary_article.source.bias}
              factuality={story.primary_article.source.factuality}
              size="sm"
            />
          </div>
          <a
            href={story.primary_article.url || '#'}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-1 text-sm font-medium text-gray-900 hover:text-pink-600 flex items-center gap-1 group"
          >
            {story.primary_article.title}
            <ExternalLink className="w-3 h-3 opacity-0 group-hover:opacity-100 transition-opacity" />
          </a>
          <p className="text-xs text-gray-500 mt-1">
            {story.primary_article.source.name}
          </p>
        </div>

        {/* Related Articles (expandable) */}
        {story.related_articles?.length > 0 && (
          <div className="mt-3">
            <button
              onClick={onToggleExpand}
              className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-700"
            >
              <ChevronRight className={`w-4 h-4 transition-transform ${expanded ? 'rotate-90' : ''}`} />
              {story.related_articles.length} related articles
            </button>

            {expanded && (
              <div className="mt-2 space-y-2 pl-5">
                {story.related_articles.map((article, i) => (
                  <RelatedArticleItem key={i} article={article} />
                ))}
              </div>
            )}
          </div>
        )}

        {/* Factuality Assessment */}
        {story.factuality_assessment && (
          <div className="mt-3 text-xs text-gray-500">
            <span className="font-medium">Assessment:</span> {story.factuality_assessment}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function RelatedArticleItem({ article }: { article: RelatedArticle }) {
  return (
    <div className="flex items-start gap-2 text-xs">
      <span className={`shrink-0 w-1.5 h-1.5 rounded-full mt-1.5 ${getBiasDot(article.bias)}`} />
      <div className="flex-1 min-w-0">
        <a
          href={article.url || '#'}
          target="_blank"
          rel="noopener noreferrer"
          className="text-gray-700 hover:text-pink-600 line-clamp-1"
        >
          {article.title}
        </a>
        <span className="text-gray-400">{article.source}</span>
      </div>
    </div>
  );
}

function getPerspectiveStyle(perspective: string): string {
  const lower = perspective.toLowerCase();
  if (lower === 'left') return 'bg-blue-100 text-blue-700';
  if (lower === 'center') return 'bg-gray-100 text-gray-700';
  if (lower === 'right') return 'bg-red-100 text-red-700';
  return 'bg-purple-100 text-purple-700';
}

function getBiasDot(bias?: string): string {
  if (!bias) return 'bg-gray-400';
  const lower = bias.toLowerCase();
  if (lower === 'left' || lower === 'left-center') return 'bg-blue-500';
  if (lower === 'center') return 'bg-gray-500';
  if (lower === 'right' || lower === 'right-center') return 'bg-red-500';
  return 'bg-purple-500';
}
