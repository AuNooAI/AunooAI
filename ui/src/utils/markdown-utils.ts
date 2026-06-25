/**
 * Markdown Editing Utilities
 * Functions for manipulating markdown text in a textarea
 */

export interface TextSelection {
  start: number;
  end: number;
  selectedText: string;
}

export interface InsertResult {
  newContent: string;
  newCursorPosition: number;
  newSelectionEnd?: number;
}

/**
 * Get current selection from textarea
 */
export function getSelection(textarea: HTMLTextAreaElement): TextSelection {
  return {
    start: textarea.selectionStart,
    end: textarea.selectionEnd,
    selectedText: textarea.value.substring(textarea.selectionStart, textarea.selectionEnd)
  };
}

/**
 * Insert markdown syntax at cursor/selection
 */
export function insertMarkdown(
  content: string,
  selection: TextSelection,
  prefix: string,
  suffix: string = '',
  placeholder: string = ''
): InsertResult {
  const { start, end, selectedText } = selection;
  const textToWrap = selectedText || placeholder;

  const before = content.substring(0, start);
  const after = content.substring(end);
  const newText = prefix + textToWrap + suffix;

  return {
    newContent: before + newText + after,
    newCursorPosition: start + prefix.length,
    newSelectionEnd: start + prefix.length + textToWrap.length
  };
}

/**
 * Wrap selection with markdown (e.g., bold, italic)
 */
export function wrapSelection(
  content: string,
  selection: TextSelection,
  wrapper: string
): InsertResult {
  return insertMarkdown(content, selection, wrapper, wrapper, 'text');
}

/**
 * Insert block-level markdown (handles newlines)
 */
export function insertBlock(
  content: string,
  selection: TextSelection,
  blockPrefix: string
): InsertResult {
  const { start, end } = selection;
  const before = content.substring(0, start);
  const selectedText = content.substring(start, end);
  const after = content.substring(end);

  // Ensure we're on a new line
  const needsNewlineBefore = before.length > 0 && !before.endsWith('\n');
  const prefix = needsNewlineBefore ? '\n' + blockPrefix : blockPrefix;

  const newContent = before + prefix + (selectedText || '') + after;

  return {
    newContent,
    newCursorPosition: before.length + prefix.length + (selectedText?.length || 0)
  };
}

/**
 * Insert a table template
 */
export function insertTable(
  content: string,
  selection: TextSelection,
  rows: number = 3,
  cols: number = 3
): InsertResult {
  const { start, end } = selection;
  const before = content.substring(0, start);
  const after = content.substring(end);

  // Build table
  const headers = Array(cols).fill(0).map((_, i) => `Header ${i + 1}`);
  const separator = Array(cols).fill('----------');
  const dataRows = Array(rows - 1).fill(0).map((_, rowIdx) =>
    Array(cols).fill(0).map((_, colIdx) => `Cell ${rowIdx + 1}-${colIdx + 1}`)
  );

  let table = '\n| ' + headers.join(' | ') + ' |\n';
  table += '| ' + separator.join(' | ') + ' |\n';
  dataRows.forEach(row => {
    table += '| ' + row.join(' | ') + ' |\n';
  });
  table += '\n';

  // Ensure newline before table
  const needsNewline = before.length > 0 && !before.endsWith('\n');
  const fullInsert = (needsNewline ? '\n' : '') + table;

  return {
    newContent: before + fullInsert + after,
    newCursorPosition: before.length + fullInsert.length
  };
}

/**
 * Count words in text (excludes markdown syntax)
 */
export function countWords(text: string): number {
  if (!text || text.trim() === '') return 0;

  // Remove markdown syntax for accurate count
  const cleanText = text
    .replace(/```[\s\S]*?```/g, '') // Remove code blocks
    .replace(/`[^`]+`/g, '') // Remove inline code
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1') // Replace links with text
    .replace(/!\[([^\]]*)\]\([^)]+\)/g, '$1') // Replace images with alt text
    .replace(/[#*_~`>|]/g, '') // Remove markdown chars
    .replace(/\s+/g, ' ') // Normalize whitespace
    .trim();

  return cleanText.split(/\s+/).filter(word => word.length > 0).length;
}

/**
 * Count characters in text
 */
export function countCharacters(text: string): number {
  return text.length;
}

/**
 * Markdown action handlers
 */
export const markdownActions = {
  bold: (content: string, selection: TextSelection) =>
    wrapSelection(content, selection, '**'),

  italic: (content: string, selection: TextSelection) =>
    wrapSelection(content, selection, '*'),

  strikethrough: (content: string, selection: TextSelection) =>
    wrapSelection(content, selection, '~~'),

  h1: (content: string, selection: TextSelection) =>
    insertBlock(content, selection, '# '),

  h2: (content: string, selection: TextSelection) =>
    insertBlock(content, selection, '## '),

  h3: (content: string, selection: TextSelection) =>
    insertBlock(content, selection, '### '),

  link: (content: string, selection: TextSelection, url: string = 'url') =>
    insertMarkdown(content, selection, '[', `](${url})`, selection.selectedText || 'link text'),

  image: (content: string, selection: TextSelection, url: string = 'image-url') =>
    insertMarkdown(content, selection, '![', `](${url})`, 'alt text'),

  bulletList: (content: string, selection: TextSelection) =>
    insertBlock(content, selection, '- '),

  numberedList: (content: string, selection: TextSelection) =>
    insertBlock(content, selection, '1. '),

  blockquote: (content: string, selection: TextSelection) =>
    insertBlock(content, selection, '> '),

  codeBlock: (content: string, selection: TextSelection) => {
    const { start, end, selectedText } = selection;
    const before = content.substring(0, start);
    const after = content.substring(end);
    const needsNewline = before.length > 0 && !before.endsWith('\n');
    const prefix = (needsNewline ? '\n' : '') + '```\n';
    const suffix = '\n```\n';
    const text = selectedText || 'code';

    return {
      newContent: before + prefix + text + suffix + after,
      newCursorPosition: before.length + prefix.length + text.length
    };
  },

  inlineCode: (content: string, selection: TextSelection) =>
    wrapSelection(content, selection, '`'),

  table: (content: string, selection: TextSelection) =>
    insertTable(content, selection),

  horizontalRule: (content: string, selection: TextSelection) =>
    insertBlock(content, selection, '\n---\n')
};

/**
 * Format an article as markdown for insertion
 */
export function formatArticleAsMarkdown(article: {
  title: string;
  source?: string;
  date?: string;
  summary?: string;
  url?: string;
  uri?: string;
}): string {
  let md = `\n### ${article.title}\n`;
  if (article.source || article.date) {
    md += `*${article.source || 'Unknown'}*`;
    if (article.date) md += ` | ${article.date}`;
    md += '\n\n';
  }
  if (article.summary) {
    md += `${article.summary}\n\n`;
  }
  const url = article.url || article.uri;
  if (url) {
    md += `[Read more](${url})\n`;
  }
  return md;
}
