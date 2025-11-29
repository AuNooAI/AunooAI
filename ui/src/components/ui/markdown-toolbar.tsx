/**
 * Markdown Toolbar Component
 * Full-featured toolbar for markdown editing with formatting, insertion, and article search
 */

import { useState, useEffect } from 'react';
import {
  Bold,
  Italic,
  Strikethrough,
  Heading1,
  Heading2,
  Heading3,
  Link2,
  Image,
  List,
  ListOrdered,
  Quote,
  Code2,
  Table,
  Minus,
  Undo2,
  Redo2,
  Eye,
  EyeOff,
  FileText,
  Search,
  Loader2,
  ChevronDown
} from 'lucide-react';
import { Button } from './button';
import { Separator } from './separator';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from './tooltip';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from './dropdown-menu';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from './popover';
import { Input } from './input';
import { ScrollArea } from './scroll-area';
import { useArticleSearch, type SearchableArticle } from '../../hooks/useArticleSearch';

type MarkdownAction =
  | 'bold' | 'italic' | 'strikethrough'
  | 'h1' | 'h2' | 'h3'
  | 'link' | 'image'
  | 'bulletList' | 'numberedList'
  | 'blockquote' | 'codeBlock' | 'inlineCode'
  | 'table' | 'horizontalRule';

interface MarkdownToolbarProps {
  onAction: (action: MarkdownAction, extra?: string) => void;
  onUndo: () => void;
  onRedo: () => void;
  canUndo: boolean;
  canRedo: boolean;
  showPreview: boolean;
  onTogglePreview: () => void;
  wordCount: number;
  daysBack: number;
  topic?: string;
  onInsertArticle: (article: SearchableArticle) => void;
}

interface ToolbarButtonProps {
  icon: React.ReactNode;
  label: string;
  shortcut?: string;
  onClick: () => void;
  disabled?: boolean;
  active?: boolean;
}

function ToolbarButton({ icon, label, shortcut, onClick, disabled, active }: ToolbarButtonProps) {
  return (
    <TooltipProvider delayDuration={300}>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant={active ? "secondary" : "ghost"}
            size="sm"
            onClick={onClick}
            disabled={disabled}
            className="h-8 w-8 p-0"
          >
            {icon}
          </Button>
        </TooltipTrigger>
        <TooltipContent side="bottom" className="text-xs">
          <p>{label}</p>
          {shortcut && <p className="text-gray-400">{shortcut}</p>}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

function ArticleSearchDropdown({
  daysBack,
  topic,
  onInsertArticle
}: {
  daysBack: number;
  topic?: string;
  onInsertArticle: (article: SearchableArticle) => void;
}) {
  const [open, setOpen] = useState(false);
  const {
    articles,
    loading,
    error,
    searchTerm,
    setSearchTerm,
    fetchArticles,
    articleCount
  } = useArticleSearch({ daysBack, topic });

  // Fetch articles when dropdown opens
  useEffect(() => {
    if (open && articleCount === 0) {
      fetchArticles();
    }
  }, [open, articleCount, fetchArticles]);

  const handleSelect = (article: SearchableArticle) => {
    console.log('📰 Article selected in toolbar:', article.title);
    // Close popover first, then insert
    setOpen(false);
    setSearchTerm('');
    // Use setTimeout to ensure the popover is closed before inserting
    setTimeout(() => {
      console.log('📰 Calling onInsertArticle callback');
      onInsertArticle(article);
    }, 50);
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="sm" className="h-8 gap-1 px-2">
          <FileText className="w-4 h-4" />
          <span className="text-xs">Insert Article</span>
          <ChevronDown className="w-3 h-3" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-96 p-0" align="start">
        <div className="p-3 border-b">
          <div className="relative">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <Input
              placeholder="Search articles..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="h-8 pl-9 text-sm"
            />
          </div>
          <p className="text-xs text-gray-500 mt-2">
            {articleCount} articles from last {daysBack} days
          </p>
        </div>
        <ScrollArea className="h-80">
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="w-5 h-5 animate-spin text-gray-400" />
            </div>
          ) : error ? (
            <div className="py-8 text-center text-red-500 text-sm px-4">
              {error}
              <Button
                variant="link"
                size="sm"
                onClick={fetchArticles}
                className="block mx-auto mt-2"
              >
                Retry
              </Button>
            </div>
          ) : articles.length === 0 ? (
            <div className="py-8 text-center text-gray-500 text-sm">
              {searchTerm ? 'No articles match your search' : 'No articles found'}
            </div>
          ) : (
            <div className="p-2 space-y-1">
              {articles.slice(0, 50).map(article => (
                <button
                  type="button"
                  key={article.uri}
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    handleSelect(article);
                  }}
                  className="w-full text-left p-2 rounded hover:bg-gray-100 transition-colors cursor-pointer"
                >
                  <div className="font-medium text-sm line-clamp-1">{article.title}</div>
                  <div className="text-xs text-gray-500 flex items-center gap-1">
                    <span>{article.source}</span>
                    <span>•</span>
                    <span>{article.date}</span>
                  </div>
                </button>
              ))}
            </div>
          )}
        </ScrollArea>
      </PopoverContent>
    </Popover>
  );
}

function LinkInsertPopover({
  onInsert
}: {
  onInsert: (url: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [url, setUrl] = useState('');

  const handleInsert = () => {
    if (url.trim()) {
      onInsert(url.trim());
      setUrl('');
      setOpen(false);
    }
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="sm" className="h-8 w-8 p-0">
          <Link2 className="w-4 h-4" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-72" align="start">
        <div className="space-y-3">
          <p className="text-sm font-medium">Insert Link</p>
          <Input
            placeholder="https://..."
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleInsert()}
            className="h-8 text-sm"
          />
          <div className="flex justify-end gap-2">
            <Button variant="ghost" size="sm" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button size="sm" onClick={handleInsert} disabled={!url.trim()}>
              Insert
            </Button>
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}

export function MarkdownToolbar({
  onAction,
  onUndo,
  onRedo,
  canUndo,
  canRedo,
  showPreview,
  onTogglePreview,
  wordCount,
  daysBack,
  topic,
  onInsertArticle
}: MarkdownToolbarProps) {
  return (
    <div className="flex items-center gap-1 p-2 border-b bg-slate-50 rounded-t-lg flex-wrap">
      {/* Text Formatting */}
      <ToolbarButton
        icon={<Bold className="w-4 h-4" />}
        label="Bold"
        shortcut="Ctrl+B"
        onClick={() => onAction('bold')}
      />
      <ToolbarButton
        icon={<Italic className="w-4 h-4" />}
        label="Italic"
        shortcut="Ctrl+I"
        onClick={() => onAction('italic')}
      />
      <ToolbarButton
        icon={<Strikethrough className="w-4 h-4" />}
        label="Strikethrough"
        onClick={() => onAction('strikethrough')}
      />

      <Separator orientation="vertical" className="h-6 mx-1" />

      {/* Headers Dropdown */}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="sm" className="h-8 gap-1 px-2">
            <Heading1 className="w-4 h-4" />
            <ChevronDown className="w-3 h-3" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start">
          <DropdownMenuItem onClick={() => onAction('h1')}>
            <Heading1 className="w-4 h-4 mr-2" />
            Heading 1
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => onAction('h2')}>
            <Heading2 className="w-4 h-4 mr-2" />
            Heading 2
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => onAction('h3')}>
            <Heading3 className="w-4 h-4 mr-2" />
            Heading 3
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <Separator orientation="vertical" className="h-6 mx-1" />

      {/* Lists & Structure */}
      <ToolbarButton
        icon={<List className="w-4 h-4" />}
        label="Bullet List"
        onClick={() => onAction('bulletList')}
      />
      <ToolbarButton
        icon={<ListOrdered className="w-4 h-4" />}
        label="Numbered List"
        onClick={() => onAction('numberedList')}
      />
      <ToolbarButton
        icon={<Quote className="w-4 h-4" />}
        label="Blockquote"
        onClick={() => onAction('blockquote')}
      />
      <ToolbarButton
        icon={<Code2 className="w-4 h-4" />}
        label="Code Block"
        onClick={() => onAction('codeBlock')}
      />

      <Separator orientation="vertical" className="h-6 mx-1" />

      {/* Insert */}
      <LinkInsertPopover onInsert={(url) => onAction('link', url)} />
      <ToolbarButton
        icon={<Image className="w-4 h-4" />}
        label="Image"
        onClick={() => onAction('image')}
      />
      <ToolbarButton
        icon={<Table className="w-4 h-4" />}
        label="Table"
        onClick={() => onAction('table')}
      />
      <ToolbarButton
        icon={<Minus className="w-4 h-4" />}
        label="Horizontal Rule"
        onClick={() => onAction('horizontalRule')}
      />

      <Separator orientation="vertical" className="h-6 mx-1" />

      {/* Article Search */}
      <ArticleSearchDropdown
        daysBack={daysBack}
        topic={topic}
        onInsertArticle={onInsertArticle}
      />

      <div className="flex-1" />

      {/* Right side: Undo/Redo, Word Count, Preview */}
      <ToolbarButton
        icon={<Undo2 className="w-4 h-4" />}
        label="Undo"
        shortcut="Ctrl+Z"
        onClick={onUndo}
        disabled={!canUndo}
      />
      <ToolbarButton
        icon={<Redo2 className="w-4 h-4" />}
        label="Redo"
        shortcut="Ctrl+Shift+Z"
        onClick={onRedo}
        disabled={!canRedo}
      />

      <Separator orientation="vertical" className="h-6 mx-1" />

      <span className="text-xs text-gray-500 px-2 min-w-[70px] text-right">
        {wordCount} words
      </span>

      <Separator orientation="vertical" className="h-6 mx-1" />

      <ToolbarButton
        icon={showPreview ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
        label={showPreview ? "Edit" : "Preview"}
        onClick={onTogglePreview}
        active={showPreview}
      />
    </div>
  );
}
