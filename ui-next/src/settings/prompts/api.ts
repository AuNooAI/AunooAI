import { api } from '../../shell';

/*
 * The versioned prompts in data/prompts/, through app/routes/prompt_routes.py, as the old
 * Prompt Engineering page (templates/promptmanager.html) used them.
 */

export interface PromptType { name: string; display_name: string }

export interface PromptVersion {
  hash: string;
  version: string;
  system_prompt: string;
  user_prompt: string;
  created_at: string;
  expected_output_schema?: Record<string, unknown> | null;
  variables?: Record<string, string> | null;
  metadata?: Record<string, unknown> | null;
  prompt_name?: string | null;
  feature?: string | null;
  description?: string | null;
  author?: string | null;
  [key: string]: unknown;
}

const enc = encodeURIComponent;

export const listTypes = () => api<{ types: PromptType[] }>('/api/prompts/types').then((r) => r.types ?? []);
/** Every saved version, including the active one (hash "current") */
export const listVersions = (type: string) => api<{ versions: PromptVersion[] }>(`/api/prompts/${enc(type)}/versions`).then((r) => r.versions ?? []);
export const getVersion = (type: string, hash: string) => api<PromptVersion>(`/api/prompts/${enc(type)}/${enc(hash)}`);
/** Saves a new version and makes it the active one */
export const saveVersion = (type: string, data: Partial<PromptVersion> & { system_prompt: string; user_prompt: string }) =>
  api<PromptVersion>(`/api/prompts/${enc(type)}`, { method: 'POST', json: data });
/** Makes an older version the active one again */
export const restoreVersion = (type: string, hash: string) => api<PromptVersion>(`/api/prompts/${enc(type)}/${enc(hash)}/restore`, { method: 'POST' });
export const deleteVersion = (type: string, hash: string) => api(`/api/prompts/${enc(type)}/${enc(hash)}`, { method: 'DELETE' });

/** Dashboard prompts end with a fixed output format the page code depends on; only the part before it is editable */
export const FORMAT_MARKER = 'REQUIRED OUTPUT FORMAT:';

export function splitUserPrompt(user: string): { instructions: string; format: string | null } {
  const i = user.indexOf(FORMAT_MARKER);
  if (i < 0) return { instructions: user, format: null };
  return { instructions: user.slice(0, i).trim(), format: user.slice(i) };
}

export const joinUserPrompt = (instructions: string, format: string | null) => (format ? `${instructions.trim()}\n\n${format}` : instructions);

/** The variables shown when a prompt doesn't list its own (as the old page's defaults) */
export const DEFAULT_VARIABLES: { group: string; vars: [string, string][] }[] = [
  {
    group: 'Content analysis',
    vars: [
      ['article_text', 'Full article content'],
      ['title', 'Article title'],
      ['source', 'Article source'],
      ['uri', 'Article address'],
      ['summary_length', 'Requested summary length'],
      ['summary_voice', 'Summary voice style'],
      ['summary_type', 'Type of summary'],
      ['categories', 'Available categories'],
      ['future_signals', 'Available future signals'],
      ['sentiment_options', 'Available sentiment options'],
      ['time_to_impact_options', 'Available time to impact options'],
      ['driver_types', 'Available driver types'],
    ],
  },
  { group: 'Date extraction', vars: [['content', 'Article content (first 1,000 characters)']] },
];
