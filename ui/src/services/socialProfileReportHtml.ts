// Self-contained downloadable HTML report for a social account profile.
// Modeled on brandReportHtml.ts — no runtime deps, inline CSS, CSS-bar charts.
import type { BWAccountProfile, BWAccountDeepDive } from './socialProfileApi';

const esc = (s: unknown): string =>
  String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

const num = (n?: number | null): string =>
  n == null ? '—' : n >= 1000 ? `${(n / 1000).toFixed(n >= 10000 ? 0 : 1)}k` : `${n}`;

const PLATFORM_LABEL: Record<string, string> = {
  twitter: 'X', bluesky: 'Bluesky', reddit: 'Reddit', instagram: 'Instagram', tiktok: 'TikTok',
};

function statCard(eyebrow: string, value: string, sub = ''): string {
  return `<div class="stat"><div class="eyebrow">${esc(eyebrow)}</div><div class="val">${esc(value)}</div>${sub ? `<div class="sub">${esc(sub)}</div>` : ''}</div>`;
}

function postRow(p: { text?: string | null; created_at?: string | null; likes?: number | null; comments?: number | null; plays?: number | null; url?: string | null }): string {
  const meta = [
    p.created_at ? esc(p.created_at.slice(0, 10)) : '',
    p.likes != null ? `♥ ${num(p.likes)}` : '',
    p.comments != null ? `💬 ${num(p.comments)}` : '',
    p.plays != null ? `▶ ${num(p.plays)}` : '',
  ].filter(Boolean).join(' · ');
  const link = p.url ? `<a href="${esc(p.url)}" target="_blank" rel="noopener">view</a>` : '';
  return `<div class="post"><div class="post-text">${esc(p.text || '(no text)')}</div><div class="post-meta">${meta} ${link}</div></div>`;
}

export function buildAccountReportHtml(p: BWAccountProfile, dd: BWAccountDeepDive | null, generatedAt: string): string {
  const s = p.post_sentiment;
  const scored = s?.scored || 0;
  const sentBar = scored ? `
    <div class="sentbar">
      <div style="width:${((s!.pos || 0) / scored) * 100}%;background:#10b981" title="${s!.pos} positive"></div>
      <div style="width:${((s!.neu || 0) / scored) * 100}%;background:#94a3b8" title="${s!.neu} neutral"></div>
      <div style="width:${((s!.neg || 0) / scored) * 100}%;background:#ef4444" title="${s!.neg} negative"></div>
    </div>
    <div class="muted">${s!.pos}+ · ${s!.neu}· · ${s!.neg}− across ${scored} posts${s!.net != null ? ` · net ${s!.net > 0 ? '+' : ''}${s!.net}` : ''}</div>` : '<div class="muted">No sentiment scored.</div>';

  const topics = (p.topics || []).map(t => `<span class="chip">${esc(t)}</span>`).join(' ');
  const tags = (p.tags || []).map(t => `<span class="chip tag">${esc(t)}</span>`).join(' ');
  const posts = (p.sample_posts || []).map(postRow).join('');

  // Deep-dive timeline as CSS bars.
  let ddHtml = '';
  if (dd) {
    const maxCount = Math.max(1, ...dd.timeline.map(d => d.count));
    const bars = dd.timeline.map(d =>
      `<div class="tl-row"><span class="tl-date">${esc(d.date)}</span><div class="tl-bar"><div style="width:${(d.count / maxCount) * 100}%"></div></div><span class="tl-n">${d.count} · ♥${num(d.likes)}</span></div>`).join('');
    const conns = (dd.connections || []).map(c => `<span class="chip">@${esc(c.handle)}${c.followers != null ? ` <span class="muted">(${num(c.followers)})</span>` : ''}</span>`).join(' ');
    ddHtml = `
      <section><h2>Deep dive</h2>
        <div class="stats">
          ${statCard('Posts analyzed', String(dd.posts_analyzed))}
          ${statCard('Total likes', num(dd.engagement.total_likes))}
          ${statCard('Avg likes', num(dd.engagement.avg_likes))}
          ${statCard('Total comments', num(dd.engagement.total_comments))}
        </div>
        <h3>Activity timeline</h3>
        <div class="timeline">${bars || '<div class="muted">No dated posts.</div>'}</div>
        ${conns ? `<h3>Follows (sample)</h3><div class="chips">${conns}</div>` : ''}
      </section>`;
  }

  return `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>${esc(p.display_name || p.handle)} — social profile</title>
<style>
:root{--fg:#1f2937;--muted:#6b7280;--line:#e5e7eb;--accent:#2563eb;--bg:#f9fafb}
*{box-sizing:border-box}body{margin:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;color:var(--fg);background:var(--bg);line-height:1.5}
main{max-width:820px;margin:0 auto;padding:32px 20px}
header{display:flex;gap:16px;align-items:center;border-bottom:2px solid var(--accent);padding-bottom:16px;margin-bottom:8px}
header img{width:64px;height:64px;border-radius:50%;object-fit:cover;background:#eee}
h1{font-size:22px;margin:0}h2{font-size:16px;margin:24px 0 8px;border-bottom:1px solid var(--line);padding-bottom:4px}h3{font-size:13px;margin:16px 0 6px;color:var(--muted);text-transform:uppercase;letter-spacing:.03em}
.handle{color:var(--accent);text-decoration:none;font-size:14px}
.muted{color:var(--muted);font-size:12px;margin-top:4px}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px;margin:12px 0}
.stat{background:#fff;border:1px solid var(--line);border-radius:8px;padding:10px 12px}
.stat .eyebrow{font-size:11px;color:var(--muted);text-transform:uppercase}.stat .val{font-size:20px;font-weight:700}.stat .sub{font-size:11px;color:var(--muted)}
.chip{display:inline-block;background:#eef2ff;color:#3730a3;border-radius:999px;padding:2px 9px;font-size:12px;margin:2px 2px}
.chip.tag{background:#dbeafe;color:#1e40af}
.chips{margin:4px 0}
.callout{background:#fffbeb;border:1px solid #fde68a;border-radius:8px;padding:10px 12px;margin:10px 0}
.sentbar{display:flex;height:12px;border-radius:999px;overflow:hidden;background:#f3f4f6;margin:8px 0 2px}
.post{border-bottom:1px solid var(--line);padding:8px 0}.post-text{font-size:14px}.post-meta{font-size:12px;color:var(--muted);margin-top:2px}.post-meta a{color:var(--accent)}
.timeline{background:#fff;border:1px solid var(--line);border-radius:8px;padding:10px}
.tl-row{display:flex;align-items:center;gap:8px;margin:3px 0;font-size:12px}
.tl-date{width:82px;color:var(--muted)}.tl-bar{flex:1;background:#f3f4f6;border-radius:4px;height:12px;overflow:hidden}.tl-bar>div{height:100%;background:var(--accent)}.tl-n{width:110px;text-align:right;color:var(--muted)}
footer{margin-top:32px;color:var(--muted);font-size:11px;border-top:1px solid var(--line);padding-top:10px}
</style></head><body><main>
<header>
  ${p.avatar_url ? `<img src="${esc(p.avatar_url)}" alt="" referrerpolicy="no-referrer">` : ''}
  <div>
    <h1>${esc(p.display_name || p.handle)}${p.verified ? ' ✓' : ''} <span class="chip">${esc(PLATFORM_LABEL[p.platform] || p.platform)}</span></h1>
    <a class="handle" href="${esc(p.profile_url || '#')}" target="_blank" rel="noopener">@${esc(p.handle)}</a>
    ${p.bio ? `<div class="muted">${esc(p.bio)}</div>` : ''}
  </div>
</header>

<section>
  <div class="stats">
    ${statCard('Followers', num(p.followers_count))}
    ${statCard('Following', num(p.following_count))}
    ${statCard(p.platform === 'reddit' ? 'Link karma' : 'Posts', num(p.posts_count))}
  </div>
  ${p.summary ? `<h3>Summary</h3><p>${esc(p.summary)}</p>` : ''}
  ${p.brand_context ? `<div class="callout"><strong>Brand context.</strong> ${esc(p.brand_context)}</div>` : ''}
  ${topics ? `<h3>Topics</h3><div class="chips">${topics}</div>` : ''}
  <h3>Sentiment${p.brand_context ? '' : ''}</h3>${sentBar}
  ${tags ? `<h3>Tags</h3><div class="chips">${tags}</div>` : ''}
  ${p.annotation?.text ? `<h3>Note</h3><p>${esc(p.annotation.text)}</p>` : ''}
</section>

${posts ? `<section><h2>Top posts</h2>${posts}</section>` : ''}
${ddHtml}

<footer>Generated ${esc(generatedAt.slice(0, 16).replace('T', ' '))} · Aunoo Brand Watcher · account profile is point-in-time from xpoz.</footer>
</main></body></html>`;
}

export function downloadAccountReport(p: BWAccountProfile, dd: BWAccountDeepDive | null): void {
  const html = buildAccountReportHtml(p, dd, new Date().toISOString());
  const blob = new Blob([html], { type: 'text/html' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `social-profile-${p.platform}-${p.handle}-${new Date().toISOString().slice(0, 10)}.html`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
