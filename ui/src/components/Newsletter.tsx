/**
 * Newsletter Generator Component
 * Generates newsletters with markdown editing and article annotation
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import {
  Loader2,
  AlertCircle,
  CheckCircle2,
  Edit3,
  Save,
  X,
  Eye,
  FileText,
  Download,
  Plus,
  MessageSquare,
  ChevronDown,
  ChevronUp,
  Search,
  Filter,
  Calendar,
  RefreshCw,
  ExternalLink,
  Trash2,
  FolderOpen,
} from 'lucide-react';
import { Button } from './ui/button';
import { Progress } from './ui/progress';
import { Alert, AlertDescription, AlertTitle } from './ui/alert';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';
import { Badge } from './ui/badge';
import { Separator } from './ui/separator';
import { Textarea } from './ui/textarea';
import { Input } from './ui/input';
import { Label } from './ui/label';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from './ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from './ui/select';
import {
  NEWSLETTER_STAGES,
  type NewsletterArticle,
} from '../hooks/useNewsletter';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { AIDisclosureFooter } from './AIDisclosureFooter';
import { MarkdownToolbar } from './ui/markdown-toolbar';
import { useUndoRedo } from '../hooks/useUndoRedo';
import { type SearchableArticle } from '../hooks/useArticleSearch';
import {
  getSelection,
  markdownActions,
  countWords,
  formatArticleAsMarkdown,
  type InsertResult
} from '../utils/markdown-utils';

// Saved newsletter summary for dropdown
interface SavedNewsletterSummary {
  id: number;
  name: string;
  description?: string;
  created_at: string;
  articles_used?: number;
  model_used?: string;
  days_back?: number;
  deep_dive_topic?: string;
}

interface NewsletterProps {
  topic?: string;
  // Newsletter state from parent
  isGenerating: boolean;
  currentStage: string;
  stageProgress: number;
  overallProgress: number;
  newsletterContent: string;
  editedContent: string;
  isEditing: boolean;
  availableArticles: NewsletterArticle[];
  selectedArticles: NewsletterArticle[];
  result: any;
  error: string | null;
  articlesFetched: number;
  articlesCategorized: number;
  // Config state
  daysBack: number;
  deepDiveTopic: string;
  newsletterTitle: string;
  newsletterIntro: string;
  onDaysBackChange: (value: number) => void;
  onDeepDiveTopicChange: (value: string) => void;
  onNewsletterTitleChange: (value: string) => void;
  onNewsletterIntroChange: (value: string) => void;
  // Actions
  onStartEditing: () => void;
  onSaveEdits: () => void;
  onDiscardEdits: () => void;
  onUpdateEditedContent: (content: string) => void;
  onToggleArticleSelection: (articleId: string) => void;
  onUpdateArticleAnnotation: (articleId: string, annotation: string) => void;
  onAddSelectedToNewsletter: () => void;
  onClearError: () => void;
  onClearResults: () => void;
  // Saved newsletters (optional callbacks for save/load)
  onLoadNewsletter?: (content: string, result?: any) => void;
  // Header button callbacks (controlled from App.tsx)
  onSave?: () => void;
  showSaveDialog?: boolean;
  onSaveDialogChange?: (open: boolean) => void;
}

// Stage indicator component
function StageIndicator({
  stages,
  currentStage,
  stageProgress
}: {
  stages: typeof NEWSLETTER_STAGES;
  currentStage: string;
  stageProgress: number;
}) {
  const getStageStatus = (stageName: string) => {
    const currentIndex = stages.findIndex(s => s.name === currentStage);
    const stageIndex = stages.findIndex(s => s.name === stageName);

    if (currentStage === 'complete') return 'complete';
    if (stageIndex < currentIndex) return 'complete';
    if (stageIndex === currentIndex) return 'active';
    return 'pending';
  };

  return (
    <div className="flex items-center gap-2 mb-6">
      {stages.map((stage, index) => {
        const status = getStageStatus(stage.name);
        return (
          <div key={stage.name} className="flex items-center">
            <div className="flex flex-col items-center">
              <div
                className={`
                  w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium
                  ${status === 'complete' ? 'bg-green-500 text-white' : ''}
                  ${status === 'active' ? 'bg-pink-500 text-white animate-pulse' : ''}
                  ${status === 'pending' ? 'bg-gray-200 text-gray-500' : ''}
                `}
              >
                {status === 'complete' ? (
                  <CheckCircle2 className="w-4 h-4" />
                ) : status === 'active' ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  index + 1
                )}
              </div>
              <span className={`text-xs mt-1 ${status === 'active' ? 'text-pink-600 font-medium' : 'text-gray-500'}`}>
                {stage.label}
              </span>
            </div>
            {index < stages.length - 1 && (
              <div className={`w-12 h-0.5 mx-2 ${
                getStageStatus(stages[index + 1].name) !== 'pending' ? 'bg-green-500' : 'bg-gray-200'
              }`} />
            )}
          </div>
        );
      })}
    </div>
  );
}

// Stats display during generation
function GenerationStats({
  articlesFetched,
  articlesCategorized,
}: {
  articlesFetched: number;
  articlesCategorized: number;
}) {
  return (
    <div className="grid grid-cols-2 gap-4 mb-6">
      <Card>
        <CardContent className="pt-4">
          <div className="flex items-center gap-2">
            <Search className="w-4 h-4 text-blue-500" />
            <div>
              <p className="text-2xl font-bold">{articlesFetched}</p>
              <p className="text-xs text-gray-500">Articles Found</p>
            </div>
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="pt-4">
          <div className="flex items-center gap-2">
            <Filter className="w-4 h-4 text-purple-500" />
            <div>
              <p className="text-2xl font-bold">{articlesCategorized}</p>
              <p className="text-xs text-gray-500">Categorized</p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

// Article card with selection and annotation
function ArticleCard({
  article,
  onToggleSelection,
  onUpdateAnnotation,
}: {
  article: NewsletterArticle;
  onToggleSelection: () => void;
  onUpdateAnnotation: (annotation: string) => void;
}) {
  const [isAnnotating, setIsAnnotating] = useState(false);
  const [annotationText, setAnnotationText] = useState(article.annotation || '');

  const handleSaveAnnotation = () => {
    onUpdateAnnotation(annotationText);
    setIsAnnotating(false);
  };

  return (
    <Card className={`transition-all ${article.selected ? 'ring-2 ring-pink-500 bg-pink-50' : ''}`}>
      <CardContent className="p-4">
        <div className="flex items-start gap-3">
          <input
            type="checkbox"
            checked={article.selected}
            onChange={onToggleSelection}
            className="mt-1 h-4 w-4 rounded border-gray-300 text-pink-600 focus:ring-pink-500"
          />
          <div className="flex-1 min-w-0">
            <h4 className="font-medium text-sm text-gray-900 truncate">{article.title}</h4>
            <div className="flex items-center gap-2 text-xs text-gray-500 mt-1">
              <span>{article.source}</span>
              <span>•</span>
              <span>{article.date}</span>
              {article.category && (
                <>
                  <span>•</span>
                  <Badge variant="outline" className="text-xs">{article.category}</Badge>
                </>
              )}
            </div>
            {article.summary && (
              <p className="text-xs text-gray-600 mt-2 line-clamp-2">{article.summary}</p>
            )}

            {/* Annotation section */}
            {isAnnotating ? (
              <div className="mt-3 space-y-2">
                <Textarea
                  placeholder="Add your annotation or commentary..."
                  value={annotationText}
                  onChange={(e) => setAnnotationText(e.target.value)}
                  className="text-sm"
                  rows={3}
                />
                <div className="flex gap-2">
                  <Button size="sm" onClick={handleSaveAnnotation}>
                    <Save className="w-3 h-3 mr-1" />
                    Save
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => setIsAnnotating(false)}>
                    Cancel
                  </Button>
                </div>
              </div>
            ) : article.annotation ? (
              <div className="mt-3 p-2 bg-yellow-50 rounded border border-yellow-200">
                <div className="flex items-start gap-2">
                  <MessageSquare className="w-3 h-3 text-yellow-600 mt-0.5" />
                  <div className="flex-1">
                    <p className="text-xs text-yellow-800">{article.annotation}</p>
                    <button
                      onClick={() => setIsAnnotating(true)}
                      className="text-xs text-yellow-600 hover:text-yellow-700 mt-1"
                    >
                      Edit annotation
                    </button>
                  </div>
                </div>
              </div>
            ) : (
              <button
                onClick={() => setIsAnnotating(true)}
                className="mt-2 text-xs text-gray-500 hover:text-gray-700 flex items-center gap-1"
              >
                <Plus className="w-3 h-3" />
                Add annotation
              </button>
            )}

            {(article.url || article.uri) && (
              <a
                href={article.url || article.uri}
                target="_blank"
                rel="noopener noreferrer"
                className="mt-2 text-xs text-blue-600 hover:text-blue-700 flex items-center gap-1"
              >
                <ExternalLink className="w-3 h-3" />
                Read article
              </a>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

// Article panel for selecting additional articles
function ArticlePanel({
  articles,
  selectedCount,
  onToggleSelection,
  onUpdateAnnotation,
  onAddSelected,
}: {
  articles: NewsletterArticle[];
  selectedCount: number;
  onToggleSelection: (id: string) => void;
  onUpdateAnnotation: (id: string, annotation: string) => void;
  onAddSelected: () => void;
}) {
  const [searchTerm, setSearchTerm] = useState('');
  const [isExpanded, setIsExpanded] = useState(false);

  const filteredArticles = articles.filter(a =>
    a.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
    a.source.toLowerCase().includes(searchTerm.toLowerCase()) ||
    (a.summary && a.summary.toLowerCase().includes(searchTerm.toLowerCase()))
  );

  return (
    <div className="border rounded-lg bg-white">
      <div
        className="p-4 flex items-center justify-between cursor-pointer hover:bg-gray-50"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div className="flex items-center gap-2">
          <FileText className="w-4 h-4 text-gray-500" />
          <span className="font-medium">Available Articles</span>
          <Badge variant="outline">{articles.length}</Badge>
          {selectedCount > 0 && (
            <Badge className="bg-pink-500">{selectedCount} selected</Badge>
          )}
        </div>
        {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
      </div>

      {isExpanded && (
        <div className="border-t p-4">
          <div className="flex gap-2 mb-4">
            <div className="flex-1 relative">
              <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
              <Input
                placeholder="Search articles..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="pl-9"
              />
            </div>
            {selectedCount > 0 && (
              <Button onClick={onAddSelected}>
                <Plus className="w-4 h-4 mr-1" />
                Add {selectedCount} to Newsletter
              </Button>
            )}
          </div>

          <div className="space-y-3 max-h-96 overflow-y-auto">
            {filteredArticles.length === 0 ? (
              <p className="text-sm text-gray-500 text-center py-4">
                No articles found
              </p>
            ) : (
              filteredArticles.map((article) => (
                <ArticleCard
                  key={article.id}
                  article={article}
                  onToggleSelection={() => onToggleSelection(article.id)}
                  onUpdateAnnotation={(annotation) => onUpdateAnnotation(article.id, annotation)}
                />
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// Markdown editor with full toolbar
function MarkdownEditor({
  content,
  onChange,
  onSave,
  onDiscard,
  daysBack,
  topic,
}: {
  content: string;
  onChange: (content: string) => void;
  onSave: () => void;
  onDiscard: () => void;
  daysBack: number;
  topic?: string;
}) {
  const [showPreview, setShowPreview] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const lastCursorPositionRef = useRef<{ start: number; end: number }>({ start: 0, end: 0 });
  const { value, set, undo, redo, canUndo, canRedo, reset } = useUndoRedo(content);

  // Sync with parent content when it changes externally
  useEffect(() => {
    if (content !== value) {
      reset(content);
    }
  }, [content]);

  // Handle content changes
  const handleChange = useCallback((newContent: string) => {
    set(newContent);
    onChange(newContent);
  }, [set, onChange]);

  // Save cursor position whenever it changes in the textarea
  const handleTextareaSelect = useCallback(() => {
    const textarea = textareaRef.current;
    if (textarea) {
      lastCursorPositionRef.current = {
        start: textarea.selectionStart,
        end: textarea.selectionEnd
      };
    }
  }, []);

  // Handle toolbar actions
  const handleToolbarAction = useCallback((action: string, extra?: string) => {
    const textarea = textareaRef.current;
    if (!textarea) return;

    const selection = getSelection(textarea);
    let result: InsertResult;

    if (action === 'link' && extra) {
      result = markdownActions.link(value, selection, extra);
    } else if (action === 'image') {
      result = markdownActions.image(value, selection, 'https://');
    } else if (action in markdownActions) {
      result = (markdownActions as any)[action](value, selection);
    } else {
      return;
    }

    handleChange(result.newContent);

    // Restore cursor position
    requestAnimationFrame(() => {
      textarea.focus();
      const pos = result.newSelectionEnd || result.newCursorPosition;
      textarea.setSelectionRange(result.newCursorPosition, pos);
    });
  }, [value, handleChange]);

  // Handle article insertion - uses saved cursor position
  const handleInsertArticle = useCallback((article: SearchableArticle) => {
    console.log('📰 Inserting article:', article.title);

    const md = formatArticleAsMarkdown(article);
    console.log('📰 Formatted markdown:', md.substring(0, 100) + '...');

    const textarea = textareaRef.current;

    // Use saved cursor position (which persists even after textarea loses focus)
    const cursorPos = lastCursorPositionRef.current.end;
    const currentValue = textarea?.value || value;
    const newContent = currentValue.substring(0, cursorPos) + md + currentValue.substring(cursorPos);
    console.log('📰 Inserting at saved cursor position:', cursorPos);

    set(newContent, true);
    onChange(newContent);

    // If in preview mode, switch to edit mode
    if (showPreview) {
      setShowPreview(false);
    }

    // Restore focus and set new cursor position
    if (textarea) {
      requestAnimationFrame(() => {
        textarea.focus();
        const newPos = cursorPos + md.length;
        textarea.setSelectionRange(newPos, newPos);
        // Update the saved position too
        lastCursorPositionRef.current = { start: newPos, end: newPos };
      });
    }
  }, [set, onChange, value, showPreview]);

  // Keyboard shortcuts
  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      const isMac = navigator.platform.toUpperCase().indexOf('MAC') >= 0;
      const modKey = isMac ? e.metaKey : e.ctrlKey;

      if (!modKey) return;

      switch (e.key.toLowerCase()) {
        case 'b':
          e.preventDefault();
          handleToolbarAction('bold');
          break;
        case 'i':
          e.preventDefault();
          handleToolbarAction('italic');
          break;
        case 'k':
          e.preventDefault();
          handleToolbarAction('link', 'https://');
          break;
        case 'z':
          e.preventDefault();
          if (e.shiftKey) {
            redo();
            onChange(value);
          } else {
            undo();
            onChange(value);
          }
          break;
        case 's':
          e.preventDefault();
          onSave();
          break;
      }
    };

    textarea.addEventListener('keydown', handleKeyDown);
    return () => textarea.removeEventListener('keydown', handleKeyDown);
  }, [handleToolbarAction, undo, redo, onSave, onChange, value]);

  return (
    <div className="border rounded-lg flex flex-col max-h-[80vh]">
      {/* Sticky Toolbar */}
      <div className="sticky top-0 z-10 bg-slate-50 border-b rounded-t-lg">
        <MarkdownToolbar
          onAction={handleToolbarAction}
          onUndo={() => { undo(); onChange(value); }}
          onRedo={() => { redo(); onChange(value); }}
          canUndo={canUndo}
          canRedo={canRedo}
          showPreview={showPreview}
          onTogglePreview={() => setShowPreview(!showPreview)}
          wordCount={countWords(value)}
          daysBack={daysBack}
          topic={topic}
          onInsertArticle={handleInsertArticle}
        />
      </div>

      {/* Scrollable Editor/Preview Area */}
      <div className="flex-1 overflow-auto">
        {showPreview ? (
          <div className="p-6 min-h-[500px] bg-white">
            <div className="prose prose-slate max-w-none">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  table: ({ children }) => (
                    <div className="my-6 overflow-x-auto rounded-lg border border-slate-300 shadow-sm">
                      <table className="min-w-full divide-y divide-slate-300">{children}</table>
                    </div>
                  ),
                  thead: ({ children }) => (
                    <thead className="bg-slate-700 text-white">{children}</thead>
                  ),
                  th: ({ children }) => (
                    <th className="px-4 py-3 text-left text-xs font-bold uppercase tracking-wider text-white">{children}</th>
                  ),
                  tbody: ({ children }) => (
                    <tbody className="divide-y divide-slate-200 bg-white">{children}</tbody>
                  ),
                  tr: ({ children }) => (
                    <tr className="hover:bg-slate-50 transition-colors">{children}</tr>
                  ),
                  td: ({ children }) => (
                    <td className="px-4 py-3 text-sm text-slate-700">{children}</td>
                  ),
                  a: ({ href, children }) => (
                    <a href={href} target="_blank" rel="noopener noreferrer" className="text-pink-600 hover:text-pink-700 underline">
                      {children}
                    </a>
                  ),
                  blockquote: ({ children }) => (
                    <blockquote className="border-l-4 border-yellow-400 pl-4 py-2 bg-yellow-50 italic text-yellow-800">
                      {children}
                    </blockquote>
                  ),
                }}
              >
                {value}
              </ReactMarkdown>
            </div>
          </div>
        ) : (
          <Textarea
            ref={textareaRef}
            value={value}
            onChange={(e) => handleChange(e.target.value)}
            onSelect={handleTextareaSelect}
            onClick={handleTextareaSelect}
            onKeyUp={handleTextareaSelect}
            className="min-h-[500px] font-mono text-sm border-0 rounded-none focus:ring-0 focus-visible:ring-0"
            placeholder="Newsletter content in markdown..."
          />
        )}
      </div>

      {/* Footer with Save/Discard */}
      <div className="flex items-center justify-end gap-2 p-2 border-t bg-slate-50">
        <Button size="sm" variant="outline" onClick={onDiscard}>
          <X className="w-4 h-4 mr-1" />
          Discard
        </Button>
        <Button size="sm" onClick={onSave}>
          <Save className="w-4 h-4 mr-1" />
          Save
        </Button>
      </div>
    </div>
  );
}

// Newsletter display (read-only)
function NewsletterDisplay({
  content,
  title,
  intro,
  topic
}: {
  content: string;
  title?: string;
  intro?: string;
  topic?: string;
}) {
  return (
    <div className="bg-white rounded-lg shadow-sm border">
      {/* Header bar */}
      <div className="bg-slate-800 text-white px-6 py-4 rounded-t-lg">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <FileText className="w-5 h-5" />
            <span className="font-semibold">{title || 'Newsletter'}</span>
          </div>
          <div className="text-sm text-slate-300">
            Generated {new Date().toLocaleDateString('en-GB', {
              day: '2-digit',
              month: 'short',
              year: 'numeric'
            })}
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="p-6">
        {/* Custom intro if provided */}
        {intro && (
          <div className="mb-6 p-4 bg-slate-50 rounded-lg border border-slate-200 italic text-slate-600">
            {intro}
          </div>
        )}

        <article className="prose prose-slate max-w-none prose-headings:text-slate-900 prose-p:text-slate-700 prose-strong:text-slate-900">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              table: ({ children }) => (
                <div className="my-6 overflow-x-auto rounded-lg border border-slate-300 shadow-sm">
                  <table className="min-w-full divide-y divide-slate-300">{children}</table>
                </div>
              ),
              thead: ({ children }) => (
                <thead className="bg-slate-700 text-white">{children}</thead>
              ),
              th: ({ children }) => (
                <th className="px-4 py-3 text-left text-xs font-bold uppercase tracking-wider text-white">{children}</th>
              ),
              tbody: ({ children }) => (
                <tbody className="divide-y divide-slate-200 bg-white">{children}</tbody>
              ),
              tr: ({ children }) => (
                <tr className="hover:bg-slate-50 transition-colors">{children}</tr>
              ),
              td: ({ children }) => (
                <td className="px-4 py-3 text-sm text-slate-700">{children}</td>
              ),
              a: ({ href, children }) => (
                <a href={href} target="_blank" rel="noopener noreferrer" className="text-pink-600 hover:text-pink-700 underline">
                  {children}
                </a>
              ),
              blockquote: ({ children }) => (
                <blockquote className="border-l-4 border-yellow-400 pl-4 py-2 bg-yellow-50 italic text-yellow-800">
                  {children}
                </blockquote>
              ),
              h1: ({ children }) => (
                <h1 className="text-2xl font-bold text-slate-900 border-b border-slate-200 pb-3">{children}</h1>
              ),
              h2: ({ children }) => (
                <h2 className="text-xl font-semibold text-slate-800 mt-8 mb-4">{children}</h2>
              ),
              h3: ({ children }) => (
                <h3 className="text-lg font-medium text-slate-700 mt-6 mb-3">{children}</h3>
              ),
            }}
          >
            {content}
          </ReactMarkdown>
        </article>
      </div>

      {/* AI Disclosure Footer */}
      <div className="border-t border-slate-200">
        <AIDisclosureFooter
          dashboardName={title || 'Newsletter'}
          modelUsed="GPT-4.1"
          aiTools={['GPT-4.1', 'OpenAI Embeddings']}
          purpose={`To generate a curated newsletter covering ${topic || 'selected topics'} with headlines, analysis, and insights`}
        />
      </div>
    </div>
  );
}

export function Newsletter({
  topic,
  isGenerating,
  currentStage,
  stageProgress,
  overallProgress,
  newsletterContent,
  editedContent,
  isEditing,
  availableArticles,
  selectedArticles,
  result,
  error,
  articlesFetched,
  articlesCategorized,
  daysBack,
  deepDiveTopic,
  newsletterTitle,
  newsletterIntro,
  onDaysBackChange,
  onDeepDiveTopicChange,
  onNewsletterTitleChange,
  onNewsletterIntroChange,
  onStartEditing,
  onSaveEdits,
  onDiscardEdits,
  onUpdateEditedContent,
  onToggleArticleSelection,
  onUpdateArticleAnnotation,
  onAddSelectedToNewsletter,
  onClearError,
  onClearResults,
  onLoadNewsletter,
  onSave,
  showSaveDialog: externalShowSaveDialog,
  onSaveDialogChange,
}: NewsletterProps) {
  // Save dialog state
  const [saveName, setSaveName] = useState('');
  const [saveDescription, setSaveDescription] = useState('');
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  // Saved newsletters state
  const [savedNewsletters, setSavedNewsletters] = useState<SavedNewsletterSummary[]>([]);
  const [loadingSaved, setLoadingSaved] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [newsletterToDelete, setNewsletterToDelete] = useState<SavedNewsletterSummary | null>(null);

  // Use external or internal save dialog state
  const [internalShowSaveDialog, setInternalShowSaveDialog] = useState(false);
  const actualShowSaveDialog = externalShowSaveDialog !== undefined ? externalShowSaveDialog : internalShowSaveDialog;
  const setActualShowSaveDialog = onSaveDialogChange || setInternalShowSaveDialog;

  // Fetch saved newsletters when topic changes
  useEffect(() => {
    if (topic) {
      fetchSavedNewsletters();
    }
  }, [topic]);

  const fetchSavedNewsletters = async () => {
    if (!topic) return;
    setLoadingSaved(true);
    try {
      const res = await fetch(`/api/newsletter/saved/${encodeURIComponent(topic)}`, {
        credentials: 'include'
      });
      if (res.ok) {
        const data = await res.json();
        setSavedNewsletters(data.newsletters || []);
      }
    } catch (err) {
      console.error('Error fetching saved newsletters:', err);
    } finally {
      setLoadingSaved(false);
    }
  };

  const handleSaveNewsletter = async () => {
    if (!topic || !saveName.trim() || !newsletterContent) return;

    setSaving(true);
    setSaveError(null);

    try {
      const res = await fetch('/api/newsletter/save', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          topic,
          name: saveName.trim(),
          description: saveDescription.trim() || undefined,
          newsletter_content: newsletterContent,
          config: { title: newsletterTitle, intro: newsletterIntro },
          days_back: daysBack,
          deep_dive_topic: deepDiveTopic || undefined,
          articles_used: result?.articles_used,
          model_used: result?.model_used || 'gpt-4.1'
        })
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || 'Failed to save newsletter');
      }

      // Success - close dialog and refresh list
      setActualShowSaveDialog(false);
      setSaveName('');
      setSaveDescription('');
      fetchSavedNewsletters();
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : 'Failed to save');
    } finally {
      setSaving(false);
    }
  };

  const handleLoadNewsletter = async (id: number) => {
    try {
      const res = await fetch(`/api/newsletter/saved/load/${id}`, {
        credentials: 'include'
      });
      if (res.ok) {
        const data = await res.json();
        const newsletter = data.newsletter;
        if (newsletter && onLoadNewsletter) {
          onLoadNewsletter(newsletter.newsletter_content, {
            articles_used: newsletter.articles_used,
            article_count: newsletter.articles_used,
            deep_dive_topic: newsletter.deep_dive_topic
          });
        }
      }
    } catch (err) {
      console.error('Error loading newsletter:', err);
    }
  };

  const handleDeleteNewsletter = async () => {
    if (!newsletterToDelete) return;

    try {
      const res = await fetch(`/api/newsletter/saved/${newsletterToDelete.id}`, {
        method: 'DELETE',
        credentials: 'include'
      });
      if (res.ok) {
        fetchSavedNewsletters();
      }
    } catch (err) {
      console.error('Error deleting newsletter:', err);
    } finally {
      setShowDeleteConfirm(false);
      setNewsletterToDelete(null);
    }
  };

  // Empty state - show welcome and saved newsletters
  if (!isGenerating && !newsletterContent && !error) {
    return (
      <div className="max-w-4xl mx-auto space-y-6">
        {/* Saved newsletters list - shown first */}
        {savedNewsletters.length > 0 && (
          <Card>
            <CardHeader>
              <CardTitle className="text-lg flex items-center gap-2">
                <FolderOpen className="w-5 h-5" />
                Saved Newsletters
              </CardTitle>
              <CardDescription>
                Previously saved newsletters for this topic
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {savedNewsletters.map((n) => (
                  <div
                    key={n.id}
                    className="flex items-center justify-between p-3 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors"
                  >
                    <div className="flex-1 min-w-0">
                      <p className="font-medium text-sm truncate">{n.name}</p>
                      <div className="flex items-center gap-2 text-xs text-gray-500">
                        <span>{new Date(n.created_at).toLocaleDateString()}</span>
                        {n.articles_used && <span>• {n.articles_used} articles</span>}
                        {n.deep_dive_topic && <span>• Deep dive: {n.deep_dive_topic}</span>}
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => handleLoadNewsletter(n.id)}
                      >
                        Load
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => {
                          setNewsletterToDelete(n);
                          setShowDeleteConfirm(true);
                        }}
                      >
                        <Trash2 className="w-4 h-4 text-gray-500 hover:text-red-500" />
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        )}

        {/* Generate newsletter prompt - shown after saved newsletters */}
        <Card className="border-dashed border-2">
          <CardContent className="py-16 text-center">
            <FileText className="w-16 h-16 mx-auto text-gray-400 mb-4" />
            <h3 className="text-xl font-semibold text-gray-700 mb-2">
              Generate a Newsletter
            </h3>
            <p className="text-gray-500 max-w-md mx-auto mb-6">
              Create a professional newsletter with curated headlines, deep analysis,
              market insights, and notable discoveries. Edit the output and add your own annotations.
            </p>
            <p className="text-sm text-gray-500">
              Select a topic and click the refresh button to generate
            </p>
          </CardContent>
        </Card>

        {/* Delete Confirmation Dialog for empty state */}
        <Dialog open={showDeleteConfirm} onOpenChange={setShowDeleteConfirm}>
          <DialogContent className="sm:max-w-md">
            <DialogHeader>
              <DialogTitle>Delete Newsletter?</DialogTitle>
              <DialogDescription>
                Are you sure you want to delete <strong>"{newsletterToDelete?.name}"</strong>?
                This action cannot be undone.
              </DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button variant="ghost" onClick={() => setShowDeleteConfirm(false)}>
                Cancel
              </Button>
              <Button variant="destructive" onClick={handleDeleteNewsletter}>
                Delete
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    );
  }

  // Error state
  if (error && !isGenerating) {
    return (
      <div className="max-w-4xl mx-auto">
        <Alert variant="destructive" className="mb-6">
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>Error</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
        <Button onClick={onClearError} variant="outline">
          Try Again
        </Button>
      </div>
    );
  }

  // Generating state
  if (isGenerating) {
    return (
      <div className="max-w-4xl mx-auto">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Loader2 className="w-5 h-5 animate-spin text-pink-500" />
              Generating Newsletter
            </CardTitle>
            <CardDescription>
              {topic ? `Creating newsletter for: ${topic}` : 'Creating newsletter...'}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <StageIndicator
              stages={NEWSLETTER_STAGES}
              currentStage={currentStage}
              stageProgress={stageProgress}
            />

            <Progress value={overallProgress * 100} className="mb-4" />
            <p className="text-sm text-gray-500 text-center">
              {Math.round(overallProgress * 100)}% complete
            </p>

            <Separator className="my-6" />

            <GenerationStats
              articlesFetched={articlesFetched}
              articlesCategorized={articlesCategorized}
            />

            {/* Show streaming content */}
            {newsletterContent && (
              <div className="mt-6">
                <h4 className="text-sm font-medium text-gray-700 mb-2">Preview</h4>
                <div className="border rounded-lg p-4 max-h-64 overflow-y-auto bg-gray-50">
                  <pre className="text-xs text-gray-600 whitespace-pre-wrap">
                    {newsletterContent.slice(-1000)}
                  </pre>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    );
  }

  // Complete state - show newsletter with editor
  return (
    <div className="max-w-5xl mx-auto space-y-6">
      {/* Result stats */}
      {result && (
        <Card>
          <CardContent className="py-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-6">
                <div>
                  <p className="text-2xl font-bold">{result.article_count}</p>
                  <p className="text-xs text-gray-500">Articles Found</p>
                </div>
                <div>
                  <p className="text-2xl font-bold">{result.articles_used}</p>
                  <p className="text-xs text-gray-500">Used in Newsletter</p>
                </div>
                {result.deep_dive_topic && (
                  <div>
                    <Badge variant="outline">Deep Dive: {result.deep_dive_topic}</Badge>
                  </div>
                )}
              </div>
              <div className="flex items-center gap-2">
                {/* Load saved newsletter dropdown */}
                {savedNewsletters.length > 0 && (
                  <Select
                    onValueChange={(value) => {
                      if (value) {
                        handleLoadNewsletter(parseInt(value, 10));
                      }
                    }}
                  >
                    <SelectTrigger className="w-48">
                      <FolderOpen className="w-4 h-4 mr-1" />
                      <SelectValue placeholder="Load Saved..." />
                    </SelectTrigger>
                    <SelectContent>
                      {savedNewsletters.map((n) => (
                        <SelectItem key={n.id} value={String(n.id)}>
                          <div className="flex items-center justify-between w-full">
                            <span className="truncate">{n.name}</span>
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                setNewsletterToDelete(n);
                                setShowDeleteConfirm(true);
                              }}
                              className="ml-2 text-gray-500 hover:text-red-500"
                            >
                              <Trash2 className="w-3 h-3" />
                            </button>
                          </div>
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
                {!isEditing && (
                  <Button variant="outline" onClick={onStartEditing}>
                    <Edit3 className="w-4 h-4 mr-1" />
                    Edit
                  </Button>
                )}
                <Button variant="outline" onClick={onClearResults}>
                  <Trash2 className="w-4 h-4 mr-1" />
                  Clear
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Article selection panel */}
      {availableArticles.length > 0 && isEditing && (
        <ArticlePanel
          articles={availableArticles}
          selectedCount={selectedArticles.length}
          onToggleSelection={onToggleArticleSelection}
          onUpdateAnnotation={onUpdateArticleAnnotation}
          onAddSelected={onAddSelectedToNewsletter}
        />
      )}

      {/* Newsletter content - editor or display */}
      {isEditing ? (
        <MarkdownEditor
          content={editedContent}
          onChange={onUpdateEditedContent}
          onSave={onSaveEdits}
          onDiscard={onDiscardEdits}
          daysBack={daysBack}
          topic={topic}
        />
      ) : (
        <NewsletterDisplay
          content={newsletterContent}
          title={newsletterTitle}
          intro={newsletterIntro}
          topic={topic}
        />
      )}

      {/* Save Newsletter Dialog */}
      <Dialog open={actualShowSaveDialog} onOpenChange={setActualShowSaveDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Save Newsletter</DialogTitle>
            <DialogDescription>
              Save this newsletter for future reference.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            <div>
              <Label htmlFor="newsletter-save-name">Newsletter Name</Label>
              <Input
                id="newsletter-save-name"
                placeholder="e.g., Weekly Digest Nov 29"
                value={saveName}
                onChange={(e) => setSaveName(e.target.value)}
              />
            </div>

            <div>
              <Label htmlFor="newsletter-save-description">Description (optional)</Label>
              <Textarea
                id="newsletter-save-description"
                placeholder="Add notes about this newsletter..."
                value={saveDescription}
                onChange={(e) => setSaveDescription(e.target.value)}
                rows={3}
              />
            </div>

            <div className="text-sm text-gray-500 bg-gray-50 p-3 rounded">
              <div>Topic: <strong>{topic}</strong></div>
              <div>Articles Used: <strong>{result?.articles_used || 0}</strong></div>
              <div>Days Back: <strong>{daysBack}</strong></div>
              {deepDiveTopic && <div>Deep Dive: <strong>{deepDiveTopic}</strong></div>}
            </div>

            {saveError && (
              <Alert variant="destructive">
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>{saveError}</AlertDescription>
              </Alert>
            )}
          </div>

          <DialogFooter>
            <Button variant="ghost" onClick={() => setActualShowSaveDialog(false)}>
              Cancel
            </Button>
            <Button onClick={handleSaveNewsletter} disabled={!saveName.trim() || saving}>
              {saving ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Save className="w-4 h-4 mr-2" />}
              Save Newsletter
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={showDeleteConfirm} onOpenChange={setShowDeleteConfirm}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Delete Newsletter?</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete <strong>"{newsletterToDelete?.name}"</strong>?
              This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setShowDeleteConfirm(false)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={handleDeleteNewsletter}>
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

    </div>
  );
}
