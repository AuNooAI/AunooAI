import { api } from '../../shell';

/*
 * The App Configuration page's server calls, all on routes the old templates/config.html used.
 * No route returns a stored key: provider routes answer only whether one is set, and the
 * Bluesky route returns the handle but never the password.
 */

export interface Provider { name: string; display_name: string; config_type?: string }
export interface ModelEntry { name: string; provider: string }
export interface DbInfo {
  db_type?: string; name?: string; host?: string; port?: number; path?: string; size?: number;
  total_articles?: number; total_topics?: number; first_entry?: string | null; last_entry?: string | null;
  tables?: { name: string; rows: number }[];
}
export interface DbEntry { id: string; name: string }
export interface UserRow { username: string; email: string; role: string; is_active: boolean; is_oauth?: boolean }
export interface Me { username: string; role: string }
export interface McpInstall { username: string; mcp_url: string; snippets: Record<string, string>; tools: string[]; prompts: string[] }
export interface McpKey { id: number; name: string; key_prefix: string; created_at?: string; expires_at?: string; last_used_at?: string; is_active: boolean; username?: string }
export interface McpConnection { client_id: string; client_name: string; connected_at?: string; last_used_at?: string; expires_at?: string }
export interface McpCall { created_at: string; username: string; auth_kind: string; tool_name: string; status: string; duration_ms?: number | null }
export interface MediaBiasSource {
  id: number; source: string; country?: string; bias?: string; factual_reporting?: string; press_freedom?: string;
  media_type?: string; popularity?: string; mbfc_credibility_rating?: string;
}
export interface MediaBiasStatus { enabled: boolean; total_sources: number; last_updated: string | null; source_file?: string | null }

/** Provider groups, in the old page's order. Bluesky and Google PSE have their own forms. */
export const PROVIDER_GROUPS: { name: string; providers: string[] }[] = [
  { name: 'News feeds', providers: ['newsapi', 'thenewsapi', 'newsdata', 'newsfirehose', 'opoint'] },
  { name: 'Scrapers', providers: ['firecrawl'] },
  { name: 'Text to speech', providers: ['elevenlabs', 'dia'] },
  { name: 'Social media', providers: ['bluesky'] },
  { name: 'Web search', providers: ['google_pse'] },
];

export const getProviders = () => api<{ providers: Provider[] }>('/api/providers').then((r) => r.providers ?? []);
export const providerStatus = (name: string) => api<{ configured: boolean; username?: string }>(`/config/${encodeURIComponent(name)}`);
export const saveProviderKey = (name: string, apiKey: string) => api(`/config/${encodeURIComponent(name)}`, { method: 'POST', json: { api_key: apiKey } });
export const removeProviderKey = (name: string) => api(`/config/${encodeURIComponent(name)}`, { method: 'DELETE' });
export const saveBluesky = (username: string, password: string) => api('/config/bluesky', { method: 'POST', json: { username, password } });
export const saveGooglePse = (apiKey: string, cseId: string) => api('/config/google_pse', { method: 'POST', json: { api_key: apiKey, extra_data: { GOOGLE_CSE_ID: cseId } } });
export const reloadEnvironment = () => api<{ message?: string; keys_available?: Record<string, boolean> }>('/api/reload_environment', { method: 'POST', json: {} });

export const getModelCatalogue = () => api<{ ai_models: ModelEntry[] }>('/api/ai_models_config').then((r) => r.ai_models ?? []);
export const getConfiguredModels = () => api<ModelEntry[]>('/api/ai_models');
export const addModel = (model_name: string, provider: string, api_key: string) =>
  api<{ message?: string; error?: string }>('/config/add_model', { method: 'POST', json: { model_name, provider, api_key } });
export const removeModel = (model_name: string, provider: string) => api('/config/remove_model', { method: 'POST', json: { model_name, provider } });

export const getDbInfo = () => api<DbInfo>('/api/database-info');
export const getDbHealth = () => api<{ stuck_transactions?: number }>('/api/database-health');
export const getDatabases = () => api<DbEntry[]>('/api/databases');
export const getActiveDatabase = () => api<{ name?: string }>('/api/active-database');

export const getMe = () => api<Me>('/api/users/me');
export const getUsers = () => api<{ users: UserRow[] }>('/api/users/').then((r) => r.users ?? []);

/** A file the browser saves, built from data already fetched */
export function saveFile(name: string, data: BlobPart, type = 'application/json') {
  const url = URL.createObjectURL(new Blob([data], { type }));
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export const today = () => new Date().toISOString().slice(0, 10);

export function fmtDate(v?: string | null) {
  if (!v) return '—';
  const d = new Date(v);
  return Number.isNaN(d.getTime()) ? v : d.toLocaleString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

export function fmtSize(bytes?: number) {
  if (!bytes) return '—';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let i = 0;
  let n = bytes;
  while (n >= 1024 && i < units.length - 1) {
    n /= 1024;
    i++;
  }
  return `${n.toFixed(i ? 1 : 0)} ${units[i]}`;
}
