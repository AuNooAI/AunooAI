/**
 * Swiss Election Watch: the panels behind each sub-tab.
 * Plain tables and recharts, in the same visual vocabulary as the other modules.
 */

import { useEffect, useMemo, useState } from 'react';
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  AreaChart, Area, ReferenceLine,
} from 'recharts';
import { Loader2, ExternalLink, ChevronLeft, Sparkles, RefreshCw } from 'lucide-react';
import type { UseSwissDisinfo } from '../../hooks/useSwissDisinfo';
import type { Narrative } from '../../services/swissDisinfoApi';

export const LANG_COLORS: Record<string, string> = { de: '#2563eb', fr: '#dc2626', it: '#16a34a', en: '#6b7280' };
export const STANCE_COLORS: Record<string, string> = { promotes: '#dc2626', reports: '#2563eb', debunks: '#16a34a' };
const TIER_LABEL: Record<string, string> = {
  state_media: 'State media', alt_media: 'Alternative media', mainstream: 'Mainstream', party: 'Party',
  fact_checker: 'Fact-checker', institution: 'Institution', research: 'Research', unknown: 'Unknown',
};
const TIER_CLASS: Record<string, string> = {
  state_media: 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-200',
  alt_media: 'bg-orange-100 text-orange-800 dark:bg-orange-900/40 dark:text-orange-200',
  mainstream: 'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-200',
  party: 'bg-purple-100 text-purple-800 dark:bg-purple-900/40 dark:text-purple-200',
  fact_checker: 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-200',
  institution: 'bg-slate-100 text-slate-800 dark:bg-slate-700 dark:text-slate-200',
  research: 'bg-teal-100 text-teal-800 dark:bg-teal-900/40 dark:text-teal-200',
  unknown: 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-200',
};

export const card = 'bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4';
const th = 'text-left text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400 py-2 pr-3';
const td = 'py-2 pr-3 text-sm text-gray-800 dark:text-gray-200 align-top';

export function Spinner() {
  return <div className="flex items-center justify-center h-40"><Loader2 className="w-6 h-6 animate-spin text-red-500" /></div>;
}

export function Empty({ text }: { text: string }) {
  return <div className="text-sm text-gray-500 dark:text-gray-400 py-8 text-center">{text}</div>;
}

export function TierBadge({ tier }: { tier: string | null }) {
  const t = tier || 'unknown';
  return <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${TIER_CLASS[t] || TIER_CLASS.unknown}`}>{TIER_LABEL[t] || t}</span>;
}

export function LangBadge({ lang }: { lang: string | null }) {
  if (!lang) return null;
  return <span className="inline-block px-1.5 py-0.5 rounded text-xs font-semibold text-white" style={{ background: LANG_COLORS[lang] || '#6b7280' }}>{lang.toUpperCase()}</span>;
}

export function StanceBadge({ stance }: { stance: string }) {
  return <span className="inline-block px-2 py-0.5 rounded text-xs font-medium text-white" style={{ background: STANCE_COLORS[stance] || '#6b7280' }}>{stance}</span>;
}

function Trend({ now, prev }: { now: number; prev: number }) {
  if (!now && !prev) return <span className="text-gray-400">–</span>;
  const up = now > prev, flat = now === prev;
  return <span className={flat ? 'text-gray-500' : up ? 'text-red-600' : 'text-green-600'}>{now} <span className="text-xs">({flat ? '=' : up ? '▲' : '▼'} {prev})</span></span>;
}

// ---------------------------------------------------------------- Narratives
export function NarrativesPanel({ h }: { h: UseSwissDisinfo }) {
  const [lang, setLang] = useState('');
  const [stance, setStance] = useState('');
  const [openId, setOpenId] = useState<number | null>(null);
  useEffect(() => { h.loadNarratives(lang || undefined, stance || undefined); }, [h.loadNarratives, lang, stance]);
  useEffect(() => { if (openId) h.loadNarrativeDetail(openId); }, [openId, h.loadNarrativeDetail]);
  // Hooks stay unconditional; the detail view below only reads the result.
  const series = useMemo(() => {
    const d = h.narrativeDetail;
    if (!d) return [];
    const byDay: Record<string, Record<string, number>> = {};
    for (const p of d.language_series) { (byDay[p.day] ||= { de: 0, fr: 0, it: 0, en: 0 })[p.language] = p.count; }
    return Object.entries(byDay).sort().map(([day, v]) => ({ day, ...v }));
  }, [h.narrativeDetail]);

  if (openId && h.narrativeDetail && h.narrativeDetail.id === openId) {
    const d = h.narrativeDetail;
    return (
      <div className="space-y-4">
        <button onClick={() => { setOpenId(null); h.setNarrativeDetail(null); }} className="flex items-center gap-1 text-sm text-blue-600 hover:underline"><ChevronLeft className="w-4 h-4" /> All narratives</button>
        <div className={card}>
          <div className="text-lg font-semibold text-gray-900 dark:text-gray-100">{d.name}</div>
          <div className="text-sm text-gray-600 dark:text-gray-300 mt-1">{d.statement}</div>
          <div className="flex flex-wrap gap-2 mt-3 text-xs text-gray-500">
            <span>First seen {d.first_seen ?? '–'}</span><span>·</span><span>Last seen {d.last_seen ?? '–'}</span><span>·</span>
            <span>{d.article_count} articles</span><span>·</span><span>Attribution as reported: <b>{d.attribution ?? 'unattributed'}</b></span>
            <span>·</span>{d.languages.map((l) => <LangBadge key={l} lang={l} />)}
          </div>
        </div>
        {series.length > 1 && (
          <div className={card}>
            <div className="text-sm font-semibold mb-2 text-gray-700 dark:text-gray-200">By language over time</div>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={series}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="day" fontSize={11} /><YAxis allowDecimals={false} fontSize={11} /><Tooltip /><Legend />
                {(['de', 'fr', 'it', 'en'] as const).map((l) => <Bar key={l} isAnimationActive={false} dataKey={l} stackId="a" fill={LANG_COLORS[l]} />)}
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
        {d.fact_checks.length > 0 && (
          <div className={card}>
            <div className="text-sm font-semibold mb-2 text-gray-700 dark:text-gray-200">Fact-checks attached</div>
            {d.fact_checks.map((f) => <div key={f.uri} className="text-sm text-gray-700 dark:text-gray-300 py-1">{f.date}: <b>{f.fact_check.verdict}</b> — {f.fact_check.claim} <span className="text-gray-500">({f.fact_check.checker})</span></div>)}
          </div>
        )}
        <div className={card}>
          <div className="text-sm font-semibold mb-2 text-gray-700 dark:text-gray-200">Articles</div>
          <table className="w-full"><thead><tr><th className={th}>Date</th><th className={th}>Title</th><th className={th}>Outlet</th><th className={th}>Stance</th><th className={th}>Lang</th></tr></thead>
            <tbody>{d.articles.map((a) => (
              <tr key={a.uri} className="border-t border-gray-100 dark:border-gray-700">
                <td className={td}>{a.article_date}</td>
                <td className={td}>{a.url
                  ? <a href={a.url} target="_blank" rel="noreferrer" className="text-blue-600 dark:text-blue-400 hover:underline inline-flex items-start gap-1">{a.title}<ExternalLink className="w-3 h-3 mt-0.5 shrink-0" /></a>
                  : a.title}</td>
                <td className={td}><div>{a.source_domain}</div><TierBadge tier={a.source_tier} /></td>
                <td className={td}><StanceBadge stance={a.stance} /></td>
                <td className={td}><LangBadge lang={a.language} /></td>
              </tr>))}</tbody></table>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2 items-center text-sm">
        <select value={lang} onChange={(e) => setLang(e.target.value)} className="border rounded px-2 py-1 dark:bg-gray-800 dark:border-gray-600">
          <option value="">All languages</option><option value="de">German</option><option value="fr">French</option><option value="it">Italian</option><option value="en">English</option>
        </select>
        <select value={stance} onChange={(e) => setStance(e.target.value)} className="border rounded px-2 py-1 dark:bg-gray-800 dark:border-gray-600">
          <option value="">All stances</option><option value="promotes">Promotes</option><option value="reports">Reports</option><option value="debunks">Debunks</option>
        </select>
        <span className="text-gray-500">Last {h.daysBack} days · {h.narratives.length} narratives</span>
      </div>
      {h.loading.narratives ? <Spinner /> : h.narratives.length === 0 ? <Empty text="No narratives in this window. Run processing on the Overview tab if articles are waiting." /> : (
        <div className={card + ' overflow-x-auto'}>
          <table className="w-full min-w-[900px]"><thead><tr>
            <th className={th}>Narrative</th><th className={th}>7d (prev)</th><th className={th}>Stance</th><th className={th}>Languages</th><th className={th}>Attribution</th><th className={th}>Top outlets</th><th className={th}>Seen</th>
          </tr></thead>
            <tbody>{h.narratives.map((n: Narrative) => (
              <tr key={n.id} className="border-t border-gray-100 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700/40 cursor-pointer" onClick={() => setOpenId(n.id)}>
                <td className={td}><div className="font-medium text-gray-900 dark:text-gray-100">{n.name}</div>{n.name !== n.statement && <div className="text-xs text-gray-500 mt-0.5">{n.statement}</div>}</td>
                <td className={td}><Trend now={n.last7} prev={n.prev7} /></td>
                <td className={td}><span className="text-red-600">{n.promotes}</span> / <span className="text-blue-600">{n.reports}</span> / <span className="text-green-600">{n.debunks}</span></td>
                <td className={td}><div className="flex gap-1">{n.languages.map((l) => <LangBadge key={l} lang={l} />)}</div></td>
                <td className={td}>{n.attribution ?? 'unattributed'}</td>
                <td className={td + ' text-xs'}>{n.top_outlets.join(', ')}</td>
                <td className={td + ' text-xs whitespace-nowrap'}>{n.first_seen} → {n.last_seen}</td>
              </tr>))}</tbody></table>
          <div className="text-xs text-gray-500 mt-2">Stance counts are promotes / reports / debunks. Attribution is what the articles say, not a finding of this tool.</div>
        </div>
      )}
    </div>
  );
}

// ------------------------------------------------------------------- Sources
export function SourcesPanel({ h }: { h: UseSwissDisinfo }) {
  useEffect(() => { h.loadSources(); }, [h.loadSources]);
  const [tier, setTier] = useState('');
  const rows = h.sources.filter((s) => !tier || s.tier === tier);
  const co = h.cooccurrence;
  const grid = useMemo(() => {
    if (!co) return null;
    const idx: Record<string, number> = {};
    for (const c of co.cells) idx[`${c.source}|${c.narrative_id}`] = c.count;
    return idx;
  }, [co]);
  return (
    <div className="space-y-4">
      <div className="flex gap-2 items-center text-sm">
        <select value={tier} onChange={(e) => setTier(e.target.value)} className="border rounded px-2 py-1 dark:bg-gray-800 dark:border-gray-600">
          <option value="">All tiers</option>{Object.entries(TIER_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <span className="text-gray-500">Last {h.daysBack} days · {rows.length} outlets</span>
      </div>
      {h.loading.sources ? <Spinner /> : rows.length === 0 ? <Empty text="No outlets in this window." /> : (
        <div className={card + ' overflow-x-auto'}>
          <table className="w-full min-w-[800px]"><thead><tr>
            <th className={th}>Outlet</th><th className={th}>Tier</th><th className={th}>Lang</th><th className={th}>Articles</th><th className={th}>Last 7d</th><th className={th}>Narratives</th><th className={th}>Promoted</th><th className={th}>Seen</th>
          </tr></thead><tbody>{rows.map((s) => (
            <tr key={s.domain} className="border-t border-gray-100 dark:border-gray-700">
              <td className={td}><div className="font-medium">{s.name}</div><div className="text-xs text-gray-500">{s.domain}</div></td>
              <td className={td}><TierBadge tier={s.tier} /></td><td className={td}><LangBadge lang={s.language} /></td>
              <td className={td}>{s.articles}</td><td className={td}>{s.last7}</td><td className={td}>{s.narratives}</td>
              <td className={td}>{s.promoted}</td><td className={td + ' text-xs whitespace-nowrap'}>{s.first_seen} → {s.last_seen}</td>
            </tr>))}</tbody></table>
        </div>
      )}
      {co && grid && co.sources.length > 0 && (
        <div className={card + ' overflow-x-auto'}>
          <div className="text-sm font-semibold mb-1 text-gray-700 dark:text-gray-200">Who carries what</div>
          <div className="text-xs text-gray-500 mb-3">Outlet by narrative. Several outlets on one row within days of each other is what a coordinated push looks like in this data.</div>
          <table className="min-w-full"><thead><tr><th className={th}>Narrative</th>{co.sources.map((s) => <th key={s} className={th + ' whitespace-nowrap'}>{s.replace(/^www\./, '')}</th>)}</tr></thead>
            <tbody>{co.narratives.map((n) => (
              <tr key={n.id} className="border-t border-gray-100 dark:border-gray-700">
                <td className={td + ' max-w-xs'}>{n.name}</td>
                {co.sources.map((s) => { const v = grid[`${s}|${n.id}`] || 0; return <td key={s} className="py-1 pr-2 text-center text-sm" style={{ background: v ? `rgba(220,38,38,${Math.min(0.15 + v * 0.2, 0.9)})` : undefined, color: v >= 3 ? 'white' : undefined }}>{v || ''}</td>; })}
              </tr>))}</tbody></table>
        </div>
      )}
    </div>
  );
}

// ------------------------------------------------------- Targets & techniques
export function TargetsPanel({ h }: { h: UseSwissDisinfo }) {
  useEffect(() => { h.loadTargets(); }, [h.loadTargets]);
  const active = h.targets.filter((t) => t.articles > 0);
  const seeded = h.targets.filter((t) => t.articles === 0);
  const techs = h.techniques.filter((t) => t.technique !== 'none_reported');
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <div className={card}>
        <div className="text-sm font-semibold mb-2 text-gray-700 dark:text-gray-200">Targets, last {h.daysBack} days</div>
        {h.loading.targets ? <Spinner /> : active.length === 0 ? <Empty text="No targets named in this window." /> : (
          <table className="w-full"><thead><tr><th className={th}>Target</th><th className={th}>Type</th><th className={th}>Articles</th><th className={th}>7d</th><th className={th}>Last</th></tr></thead>
            <tbody>{active.map((t) => <tr key={t.type + t.name} className="border-t border-gray-100 dark:border-gray-700"><td className={td}>{t.name}</td><td className={td + ' text-xs'}>{t.type}</td><td className={td}>{t.articles}</td><td className={td}>{t.last7}</td><td className={td + ' text-xs'}>{t.last_seen}</td></tr>)}</tbody></table>
        )}
        {seeded.length > 0 && <div className="text-xs text-gray-500 mt-3">Watched, nothing yet: {seeded.map((t) => t.name).join(' · ')}</div>}
      </div>
      <div className={card}>
        <div className="text-sm font-semibold mb-2 text-gray-700 dark:text-gray-200">Techniques reported</div>
        {h.loading.techniques ? <Spinner /> : (
          <>
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={techs} layout="vertical" margin={{ left: 120 }}><CartesianGrid strokeDasharray="3 3" /><XAxis type="number" allowDecimals={false} fontSize={11} /><YAxis type="category" dataKey="technique" fontSize={11} width={120} /><Tooltip /><Bar isAnimationActive={false} dataKey="articles" fill="#dc2626" name="Articles" /><Bar isAnimationActive={false} dataKey="last7" fill="#f59e0b" name="Last 7d" /></BarChart>
            </ResponsiveContainer>
            <div className="text-xs text-gray-500 mt-2">A first deepfake or synthetic text aimed at a named person raises an alert on the Calendar tab.</div>
          </>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- Languages
export function LanguagesPanel({ h }: { h: UseSwissDisinfo }) {
  useEffect(() => { h.loadLanguages(); }, [h.loadLanguages]);
  const d = h.languages;
  if (h.loading.languages || !d) return <Spinner />;
  const total = Object.values(d.totals).reduce((a, b) => a + b, 0);
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {(['de', 'fr', 'it', 'en'] as const).map((l) => (
          <div key={l} className={card}><div className="flex items-center gap-2"><LangBadge lang={l} /><span className="text-xs text-gray-500">{{ de: 'German', fr: 'French', it: 'Italian', en: 'English' }[l]}</span></div>
            <div className="text-2xl font-semibold mt-1 text-gray-900 dark:text-gray-100">{d.totals[l] || 0}</div>
            <div className="text-xs text-gray-500">{total ? Math.round(100 * (d.totals[l] || 0) / total) : 0}% of extracted articles</div></div>
        ))}
      </div>
      <div className={card}>
        <div className="text-sm font-semibold mb-2 text-gray-700 dark:text-gray-200">Articles per week by language</div>
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={d.weekly}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="week" fontSize={11} /><YAxis allowDecimals={false} fontSize={11} /><Tooltip /><Legend />
            {(['de', 'fr', 'it', 'en'] as const).map((l) => <Bar key={l} isAnimationActive={false} dataKey={l} stackId="a" fill={LANG_COLORS[l]} />)}
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className={card}>
        <div className="text-sm font-semibold mb-1 text-gray-700 dark:text-gray-200">Narratives that crossed a language border</div>
        <div className="text-xs text-gray-500 mb-3">A storyline first seen in one language and later in another is being carried across the border by someone. Lag is days between first sightings.</div>
        {d.crossings.length === 0 ? <Empty text="No narrative has appeared in a second language in this window." /> : (
          <table className="w-full"><thead><tr><th className={th}>Narrative</th><th className={th}>From</th><th className={th}>To</th><th className={th}>Lag</th><th className={th}>Articles by language</th></tr></thead>
            <tbody>{d.crossings.map((n) => <tr key={n.id} className="border-t border-gray-100 dark:border-gray-700">
              <td className={td}>{n.name}</td><td className={td}><LangBadge lang={n.crossed_from!} /></td>
              <td className={td}><div className="flex gap-1">{n.crossed_to!.map((l) => <LangBadge key={l} lang={l} />)}</div></td>
              <td className={td}>{n.lag_days} d</td>
              <td className={td + ' text-xs'}>{Object.entries(n.by_language).map(([l, c]) => `${l.toUpperCase()} ${c}`).join(' · ')}</td></tr>)}</tbody></table>
        )}
      </div>
      <div className={card}>
        <div className="text-sm font-semibold mb-2 text-gray-700 dark:text-gray-200">All narratives by language</div>
        <table className="w-full"><thead><tr><th className={th}>Narrative</th><th className={th}>DE</th><th className={th}>FR</th><th className={th}>IT</th><th className={th}>EN</th></tr></thead>
          <tbody>{d.narratives.map((n) => <tr key={n.id} className="border-t border-gray-100 dark:border-gray-700"><td className={td}>{n.name}</td>{(['de', 'fr', 'it', 'en'] as const).map((l) => <td key={l} className={td}>{n.by_language[l] || ''}</td>)}</tr>)}</tbody></table>
      </div>
    </div>
  );
}

// ----------------------------------------------------------------- Calendar
export function CalendarPanel({ h }: { h: UseSwissDisinfo }) {
  useEffect(() => { h.loadCalendar(); }, [h.loadCalendar]);
  const d = h.calendar;
  if (h.loading.calendar || !d) return <Spinner />;
  const upcoming = d.votes.filter((v) => v.days_to >= 0);
  const alerts = d.events.filter((e) => e.event_type === 'alert');
  const inWindow = d.votes.filter((v) => d.daily.length && v.date >= d.daily[0].day && v.date <= d.daily[d.daily.length - 1].day);
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {upcoming.slice(0, 3).map((v) => (
          <div key={v.date} className={card}><div className="text-xs text-gray-500">{v.date}</div><div className="font-medium text-gray-900 dark:text-gray-100">{v.label}</div><div className="text-2xl font-semibold text-red-600 mt-1">{v.days_to} <span className="text-sm font-normal text-gray-500">days</span></div></div>
        ))}
      </div>
      <div className={card}>
        <div className="text-sm font-semibold mb-2 text-gray-700 dark:text-gray-200">Narrative articles per day, vote dates marked</div>
        {d.daily.length === 0 ? <Empty text="Nothing extracted in this window yet." /> : (
          <ResponsiveContainer width="100%" height={240}>
            <AreaChart data={d.daily}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="day" fontSize={11} /><YAxis allowDecimals={false} fontSize={11} /><Tooltip /><Legend />
              <Area type="monotone" isAnimationActive={false} dataKey="count" name="All" stroke="#2563eb" fill="#2563eb" fillOpacity={0.15} />
              <Area type="monotone" isAnimationActive={false} dataKey="promotes" name="Promotes" stroke="#dc2626" fill="#dc2626" fillOpacity={0.25} />
              {inWindow.map((v) => <ReferenceLine key={v.date} x={v.date} stroke="#111827" strokeDasharray="4 2" label={{ value: 'vote', position: 'top', fontSize: 10 }} />)}
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className={card}>
          <div className="text-sm font-semibold mb-2 text-gray-700 dark:text-gray-200">Alerts</div>
          {alerts.length === 0 ? <Empty text="No alerts. Rules: new narrative on two outlets in 48h, 3x weekly volume, first crossing into a second language, synthetic media aimed at a person." /> :
            alerts.map((e) => <div key={e.id} className="py-2 border-t border-gray-100 dark:border-gray-700 text-sm"><span className="text-xs text-gray-500 mr-2">{e.event_date}</span><span className={e.significance === 'high' ? 'text-red-600 font-medium' : ''}>{e.title}</span></div>)}
        </div>
        <div className={card}>
          <div className="text-sm font-semibold mb-2 text-gray-700 dark:text-gray-200">Narratives first seen</div>
          {d.first_seen.length === 0 ? <Empty text="None in this window." /> :
            d.first_seen.map((f) => <div key={f.id} className="py-1.5 border-t border-gray-100 dark:border-gray-700 text-sm"><span className="text-xs text-gray-500 mr-2">{f.day}</span>{f.name}</div>)}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- Responses
export function ResponsesPanel({ h }: { h: UseSwissDisinfo }) {
  useEffect(() => { h.loadResponses(); }, [h.loadResponses]);
  const d = h.responses;
  if (h.loading.responses || !d) return <Spinner />;
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <div className={card}>
        <div className="text-sm font-semibold mb-2 text-gray-700 dark:text-gray-200">Fact-checks</div>
        {d.fact_checks.length === 0 ? <Empty text="No fact-check articles in this window." /> : d.fact_checks.map((f) => (
          <div key={f.uri} className="py-2 border-t border-gray-100 dark:border-gray-700 text-sm">
            <div className="text-xs text-gray-500">{f.date} · {f.fact_check.checker || f.news_source}</div>
            <div><b className={f.fact_check.verdict === 'false' ? 'text-red-600' : ''}>{f.fact_check.verdict}</b> — {f.fact_check.claim}</div>
            {f.url && <a href={f.url} target="_blank" rel="noreferrer" className="text-xs text-blue-600 hover:underline inline-flex items-center gap-1">{f.title}<ExternalLink className="w-3 h-3" /></a>}
          </div>))}
      </div>
      <div className={card}>
        <div className="text-sm font-semibold mb-2 text-gray-700 dark:text-gray-200">Institutional and platform responses</div>
        {d.responses.length === 0 ? <Empty text="No responses recorded in this window." /> : d.responses.map((r) => (
          <div key={r.uri} className="py-2 border-t border-gray-100 dark:border-gray-700 text-sm">
            <div className="text-xs text-gray-500">{r.date} · {r.news_source}</div>
            <div><b>{r.response.actor}</b>: {r.response.action}</div>
            {r.url && <a href={r.url} target="_blank" rel="noreferrer" className="text-xs text-blue-600 hover:underline inline-flex items-center gap-1">{r.title}<ExternalLink className="w-3 h-3" /></a>}
          </div>))}
      </div>
    </div>
  );
}

// ----------------------------------------------------------------- Insights
export function InsightsPanel({ h }: { h: UseSwissDisinfo }) {
  useEffect(() => { h.loadBrief(); }, [h.loadBrief]);
  const b = h.brief;
  const sections = (b?.sections || {}) as Record<string, string>;
  const order: [string, string][] = [['summary', 'This week'], ['narratives', 'Narratives'], ['actors_and_vectors', 'Actors and vectors'], ['targets', 'Targets'], ['outlook', 'Outlook']];
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <button onClick={() => h.makeBrief(7)} disabled={h.loading.brief} className="inline-flex items-center gap-2 px-3 py-1.5 rounded bg-red-600 text-white text-sm hover:bg-red-700 disabled:opacity-50">
          {h.loading.brief ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />} Generate weekly brief
        </button>
        {b && <span className="text-xs text-gray-500">Latest: {new Date(b.created_at).toLocaleString()} · {b.article_count} articles · {b.narrative_count} narratives · {b.model}</span>}
      </div>
      {!b ? <Empty text="No brief yet." /> : (
        <div className={card + ' space-y-4'}>
          {sections.headline && <div className="text-lg font-semibold text-gray-900 dark:text-gray-100">{sections.headline}</div>}
          {order.map(([k, label]) => sections[k] ? <div key={k}><div className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-1">{label}</div><div className="text-sm text-gray-800 dark:text-gray-200 whitespace-pre-line">{sections[k]}</div></div> : null)}
          {!sections.summary && <div className="text-sm whitespace-pre-line text-gray-800 dark:text-gray-200">{b.brief_text}</div>}
        </div>
      )}
    </div>
  );
}

export function RefreshButton({ onClick, loading }: { onClick: () => void; loading?: boolean }) {
  return <button onClick={onClick} className="inline-flex items-center gap-1 text-sm text-gray-600 dark:text-gray-300 hover:text-gray-900"><RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />Refresh</button>;
}

// ------------------------------------------------------------- How it works
const step = 'relative pl-6 pb-4 border-l border-gray-200 dark:border-gray-700 last:border-l-0 last:pb-0';
const dot = 'absolute -left-[5px] top-1 w-2.5 h-2.5 rounded-full bg-red-500';

export function HowItWorksPanel({ h }: { h: UseSwissDisinfo }) {
  useEffect(() => { h.loadHowItWorks(); }, [h.loadHowItWorks]);
  const d = h.howItWorks;
  if (h.loading.how || !d) return <Spinner />;
  const s = d.settings;
  const news = d.keyword_groups.filter((g) => g.kind === 'news');
  const social = d.keyword_groups.filter((g) => g.kind === 'social');
  const liveFeeds = d.feeds.filter((f) => f.is_active);
  const offFeeds = d.feeds.filter((f) => !f.is_active);
  const pct = (n: number, of: number) => (of ? `${Math.round((100 * n) / of)}%` : '–');

  return (
    <div className="space-y-4">
      <div className={card}>
        <div className="text-sm font-semibold mb-1 text-gray-700 dark:text-gray-200">What this watch does</div>
        <p className="text-sm text-gray-700 dark:text-gray-300">{d.blurb}</p>
        <p className="text-sm text-gray-600 dark:text-gray-400 mt-2">
          Everything below is read from the running system, not written down, so the source list is
          what is actually being collected right now.
        </p>
      </div>

      <div className={card}>
        <div className="text-sm font-semibold mb-3 text-gray-700 dark:text-gray-200">The pipeline</div>
        <div className="space-y-0">
          <div className={step}><div className={dot} />
            <div className="font-medium text-sm text-gray-900 dark:text-gray-100">1. Collect</div>
            <div className="text-sm text-gray-600 dark:text-gray-400">
              {news.length} keyword {news.length === 1 ? 'group' : 'groups'} query news providers,
              {' '}{liveFeeds.length} RSS feeds are polled on their own schedule, and
              {' '}{social.length} social {social.length === 1 ? 'group' : 'groups'} read Bluesky and Telegram.
              A keyword is an AND of its words, so every term carries an anchor that ties it to this watch.
              Article body text is searched as well as title and description ({s.search_fields}).
            </div>
          </div>
          <div className={step}><div className={dot} />
            <div className="font-medium text-sm text-gray-900 dark:text-gray-100">2. Relevance gate</div>
            <div className="text-sm text-gray-600 dark:text-gray-400">
              Each article is scored against this watch's description. Below {s.relevance_threshold ?? '0.40'} it
              is kept but marked rejected, so nothing is lost and the board is not flooded. Social posts are
              scored separately and reach the analysis at {s.social_min_alignment} or above.
            </div>
          </div>
          <div className={step}><div className={dot} />
            <div className="font-medium text-sm text-gray-900 dark:text-gray-100">3. Extraction</div>
            <div className="text-sm text-gray-600 dark:text-gray-400">
              One pass per article on <code className="text-xs">{s.extraction_model}</code>, returning the
              storylines it carries and the stance towards each ({s.stances.join(', ')}), what is targeted,
              who the article says is behind it, the technique, the language, and any fact-check or official
              response. What counts as in scope depends on the source: an outlet we classify as state or
              alternative media pushing a line is itself the signal, while ordinary opinion in the mainstream
              press is not.
            </div>
          </div>
          <div className={step}><div className={dot} />
            <div className="font-medium text-sm text-gray-900 dark:text-gray-100">4. Group into storylines</div>
            <div className="text-sm text-gray-600 dark:text-gray-400">
              A new statement is compared by meaning against the existing storylines in this watch, and the
              closest few (above {s.narrative_shortlist_floor}) are put to the model to decide whether it is
              the same storyline. A wording match alone is not enough to merge, which is what lets one
              storyline be tracked across German, French, Italian and English.
            </div>
          </div>
          <div className={step}><div className={dot} />
            <div className="font-medium text-sm text-gray-900 dark:text-gray-100">5. Alert and brief</div>
            <div className="text-sm text-gray-600 dark:text-gray-400">
              Four rules raise an alert: a new storyline on two outlets within two days, a week's volume more
              than triple the week before, a first crossing into another language, and synthetic media aimed
              at a named person. The weekly brief is written on <code className="text-xs">{s.brief_model}</code> from
              this data only.
            </div>
          </div>
        </div>
      </div>

      <div className={card + ' overflow-x-auto'}>
        <div className="text-sm font-semibold mb-1 text-gray-700 dark:text-gray-200">Keyword groups</div>
        <div className="text-xs text-gray-500 mb-3">Each group has its own language, providers and terms.</div>
        <table className="w-full min-w-[720px]"><thead><tr>
          <th className={th}>Group</th><th className={th}>Lang</th><th className={th}>Kind</th>
          <th className={th}>Providers</th><th className={th}>Terms</th><th className={th}>Last run</th>
        </tr></thead><tbody>{d.keyword_groups.map((g) => (
          <tr key={g.id} className="border-t border-gray-100 dark:border-gray-700">
            <td className={td}>{g.name.replace(d.topic, '').replace(/^ - /, '').trim() || 'primary'}
              {!g.is_active && <span className="ml-2 text-xs text-gray-400">off</span>}</td>
            <td className={td}><LangBadge lang={g.language} /></td>
            <td className={td + ' text-xs'}>{g.kind}</td>
            <td className={td + ' text-xs'}>{(g.providers || '').replace(/[[\]"]/g, '') || 'default'}</td>
            <td className={td + ' text-xs'}>{g.keywords.join(' · ')}</td>
            <td className={td + ' text-xs whitespace-nowrap'}>{g.last_checked?.slice(0, 16).replace('T', ' ') ?? '–'}</td>
          </tr>))}</tbody></table>
      </div>

      {d.telegram_channels.length > 0 && (
        <div className={card}>
          <div className="text-sm font-semibold mb-1 text-gray-700 dark:text-gray-200">Telegram channels</div>
          <div className="text-xs text-gray-500 mb-3">Public channel previews only. No account, no private channels.</div>
          {d.telegram_channels.map((c) => (
            <div key={c.channel} className="flex items-center gap-3 py-1 text-sm border-t border-gray-100 dark:border-gray-700">
              <a href={c.url} target="_blank" rel="noreferrer" className="text-blue-600 dark:text-blue-400 hover:underline inline-flex items-center gap-1">@{c.channel}<ExternalLink className="w-3 h-3" /></a>
              <TierBadge tier={c.tier} />
            </div>))}
        </div>
      )}

      <div className={card + ' overflow-x-auto'}>
        <div className="text-sm font-semibold mb-1 text-gray-700 dark:text-gray-200">Feeds ({liveFeeds.length} live)</div>
        <div className="text-xs text-gray-500 mb-3">Polled directly, independently of the keyword search.</div>
        <table className="w-full min-w-[760px]"><thead><tr>
          <th className={th}>Feed</th><th className={th}>Tier</th><th className={th}>Fetched</th>
          <th className={th}>Kept</th><th className={th}>Last poll</th><th className={th}>Status</th>
        </tr></thead><tbody>{liveFeeds.map((f) => (
          <tr key={f.id} className="border-t border-gray-100 dark:border-gray-700">
            <td className={td}><a href={f.url} target="_blank" rel="noreferrer" className="text-blue-600 dark:text-blue-400 hover:underline">{f.name}</a></td>
            <td className={td}><TierBadge tier={f.tier} /></td>
            <td className={td}>{f.fetched ?? 0}</td>
            <td className={td}>{f.produced.approved} <span className="text-xs text-gray-500">of {f.produced.articles} ({pct(f.produced.approved, f.produced.articles)})</span></td>
            <td className={td + ' text-xs whitespace-nowrap'}>{f.last_checked?.slice(0, 16).replace('T', ' ') ?? '–'}</td>
            <td className={td + ' text-xs'}>{f.error ? <span className="text-red-600">{f.error.slice(0, 40)}</span> : 'ok'}</td>
          </tr>))}</tbody></table>
        {offFeeds.length > 0 && (
          <div className="text-xs text-gray-500 mt-3">
            Switched off, kept for the record: {offFeeds.map((f) => f.name).join(' · ')}
          </div>
        )}
      </div>

      <div className={card}>
        <div className="text-sm font-semibold mb-1 text-gray-700 dark:text-gray-200">What each source has produced</div>
        <div className="text-xs text-gray-500 mb-3">Everything this watch has collected, by outlet, kept versus total.</div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-6">
          {d.produced_by_source.map((p) => (
            <div key={p.source} className="flex justify-between gap-2 py-1 text-sm border-t border-gray-100 dark:border-gray-700">
              <span className="truncate text-gray-700 dark:text-gray-300">{p.source}</span>
              <span className="whitespace-nowrap text-gray-500">{p.approved}/{p.articles}</span>
            </div>))}
        </div>
      </div>

      <div className={card}>
        <div className="text-sm font-semibold mb-2 text-gray-700 dark:text-gray-200">Schedule</div>
        {d.schedules.length === 0 ? <Empty text="No schedule for this watch." /> : d.schedules.map((sc) => (
          <div key={sc.name} className="text-sm text-gray-700 dark:text-gray-300 py-1 border-t border-gray-100 dark:border-gray-700">
            <b>{sc.name}</b> — every {sc.every} on {sc.model}, {sc.runs} runs so far, last {sc.last_run?.slice(0, 16).replace('T', ' ') ?? '–'} ({sc.status ?? '–'}), next {sc.next_run?.slice(0, 16).replace('T', ' ') ?? '–'}.
            {!sc.enabled && <span className="text-gray-400"> Disabled.</span>}
          </div>))}
        <div className="text-xs text-gray-500 mt-3">
          Source tiers used: {s.tiers.join(', ')}. Techniques recorded: {s.techniques.filter((t) => t !== 'none_reported').join(', ')}.
          Attribution is always what the articles report, never a finding of this tool.
        </div>
      </div>
    </div>
  );
}
