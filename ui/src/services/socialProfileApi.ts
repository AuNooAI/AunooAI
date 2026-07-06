// Account Profiles API — xpoz-powered per-account brand intelligence (Brand Watcher Phase 2).
const BASE = '/api/brand-watcher/accounts';

export interface BWAccountSamplePost {
  id: string;
  text?: string | null;
  created_at?: string | null;
  likes?: number | null;
  reposts?: number | null;
  comments?: number | null;
  plays?: number | null;
  thumbnail?: string | null;
  url?: string | null;
}

export interface BWAccountSentiment {
  pos?: number; neu?: number; neg?: number; scored?: number; net?: number | null;
}

export interface BWAccountProfile {
  id: number;
  platform: string;
  handle: string;
  handle_canonical: string;
  display_name?: string | null;
  avatar_url?: string | null;
  bio?: string | null;
  profile_url?: string | null;
  verified?: boolean | null;
  followers_count?: number | null;
  following_count?: number | null;
  posts_count?: number | null;
  account_created_at?: string | null;
  topics?: string[] | null;
  post_sentiment?: BWAccountSentiment | null;
  summary?: string | null;
  brand_context?: string | null;
  sample_posts?: BWAccountSamplePost[] | null;
  tags?: string[] | null;
  annotation?: { text?: string; by?: string; at?: string } | null;
  last_profiled_at?: string | null;
  watchlisted?: boolean;
}

async function j<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = `${res.status}`;
    try { detail = (await res.json()).detail || detail; } catch { /* ignore */ }
    throw new Error(detail);
  }
  return res.json();
}

export async function buildAccountProfile(platform: string, handle: string, brand?: string | null): Promise<BWAccountProfile> {
  const res = await fetch(`${BASE}/profile`, {
    method: 'POST', credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ platform, handle, brand: brand || null }),
  });
  return j<BWAccountProfile>(res);
}

export async function getAccountProfile(platform: string, handle: string): Promise<BWAccountProfile> {
  const res = await fetch(`${BASE}/profile?platform=${encodeURIComponent(platform)}&handle=${encodeURIComponent(handle)}`, { credentials: 'include' });
  return j<BWAccountProfile>(res);
}

export async function listAccountProfiles(): Promise<BWAccountProfile[]> {
  const res = await fetch(`${BASE}/profiles`, { credentials: 'include' });
  const d = await j<{ profiles: BWAccountProfile[] }>(res);
  return d.profiles || [];
}

export async function setAccountTags(id: number, tags: string[]): Promise<BWAccountProfile> {
  const res = await fetch(`${BASE}/profile/${id}/tags`, {
    method: 'PUT', credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tags }),
  });
  return j<BWAccountProfile>(res);
}

export interface BWAccountDeepDive {
  platform: string;
  handle: string;
  brand?: string | null;
  posts_analyzed: number;
  timeline: { date: string; count: number; likes: number }[];
  engagement: { posts: number; total_likes: number; total_comments: number; avg_likes: number; max_likes: number };
  connections: { handle?: string | null; name?: string | null; followers?: number | null }[];
  top_posts: BWAccountSamplePost[];
}

export async function deepDiveAccount(platform: string, handle: string, brand?: string | null): Promise<BWAccountDeepDive> {
  const q = new URLSearchParams({ platform, handle });
  if (brand) q.append('brand', brand);
  const res = await fetch(`${BASE}/deepdive?${q}`, { credentials: 'include' });
  return j<BWAccountDeepDive>(res);
}

export async function setAccountAnnotation(id: number, text: string): Promise<BWAccountProfile> {
  const res = await fetch(`${BASE}/profile/${id}/annotation`, {
    method: 'POST', credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  });
  return j<BWAccountProfile>(res);
}

export async function deleteAccountProfile(id: number): Promise<void> {
  const res = await fetch(`${BASE}/profile/${id}`, { method: 'DELETE', credentials: 'include' });
  if (!res.ok) throw new Error(`${res.status}`);
}

export async function setAccountWatchlist(id: number, watchlisted: boolean): Promise<BWAccountProfile> {
  const res = await fetch(`${BASE}/profile/${id}/watchlist`, {
    method: 'PUT', credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ watchlisted }),
  });
  return j<BWAccountProfile>(res);
}

export async function emailAccountReport(id: number, to: string, html: string): Promise<void> {
  const res = await fetch(`${BASE}/profile/${id}/email`, {
    method: 'POST', credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ to, html }),
  });
  if (!res.ok) {
    const d = await res.json().catch(() => ({}));
    throw new Error(d.detail || `${res.status}`);
  }
}
