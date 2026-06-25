/**
 * Source Comparison — Existing news dataset vs Opoint, per brand.
 * Symmetric analytics: top domains, country coverage, volume over time, plus the
 * quality/value funnel (chargeable, relevance, precision, cost-per-usable).
 */
import { useState, useEffect, useCallback } from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend, Cell, AreaChart, Area } from 'recharts';
import { Loader2, BarChart3, Download } from 'lucide-react';
import { ChartDownloadButton } from './ChartDownloadButton';
import { getBrands, getSourceComparison, getPortfolio, getDomainArticles, reportUrl,
  type Brand, type SourceComparison, type SCPortfolio, type SCDomainArticle } from '../../services/sourceComparisonApi';

interface Props { onArticleClick?: (a: { uri: string; title?: string }) => void }

const CARD = "bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6";

export function SourceComparisonTab(_props: Props) {
  const [brands, setBrands] = useState<Brand[]>([]);
  const [brandId, setBrandId] = useState<number | null>(null);
  const [days, setDays] = useState(365);
  const [annualCost, setAnnualCost] = useState(20000);
  const [data, setData] = useState<SourceComparison | null>(null);
  const [loading, setLoading] = useState(false);
  const [portfolio, setPortfolio] = useState<SCPortfolio | null>(null);
  const [domainDrill, setDomainDrill] = useState<{ domain: string; dataset: 'opoint' | 'existing'; articles: SCDomainArticle[] } | null>(null);

  useEffect(() => {
    getBrands().then(bs => {
      setBrands(bs);
      if (bs.length && brandId == null) setBrandId(bs[0].id);
    }).catch(console.error);
  }, []);

  useEffect(() => { getPortfolio(days, annualCost).then(setPortfolio).catch(console.error); }, [days, annualCost]);

  const openDomain = useCallback(async (domain: string, dataset: 'opoint' | 'existing') => {
    if (brandId == null) return;
    setDomainDrill({ domain, dataset, articles: [] });
    try { const r = await getDomainArticles(brandId, domain, dataset, days); setDomainDrill({ domain, dataset, articles: r.articles }); }
    catch (e) { console.error(e); }
  }, [brandId, days]);

  const load = useCallback(async (bid: number, d: number, cost: number) => {
    setLoading(true);
    try { setData(await getSourceComparison(bid, d, 0.4, cost)); }
    catch (e) { console.error(e); setData(null); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { if (brandId != null) load(brandId, days, annualCost); }, [brandId, days, annualCost, load]);

  const num = (n: number) => n.toLocaleString();

  return (
    <div className="space-y-6">
      <div className="bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-200 dark:border-emerald-800 rounded-lg p-4">
        <div className="flex items-start gap-2">
          <BarChart3 className="w-5 h-5 text-emerald-500 mt-0.5 flex-shrink-0" />
          <div className="text-sm text-gray-700 dark:text-gray-300">
            <span className="font-semibold">Source comparison.</span> Our existing news dataset vs the Opoint feed for a brand — top source domains, country coverage, volume over time, and the quality/value funnel that answers "is Opoint worth it."
          </div>
        </div>
      </div>

      {/* Controls */}
      <div className="flex items-center gap-3 flex-wrap">
        <label className="text-xs font-medium text-gray-500 dark:text-gray-400">Brand:</label>
        <select value={brandId ?? ''} onChange={e => setBrandId(Number(e.target.value))}
          className="text-sm border border-gray-300 dark:border-gray-600 rounded-md px-2 py-1 bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-200">
          {brands.map(b => <option key={b.id} value={b.id}>{b.display_name}</option>)}
        </select>
        <label className="text-xs font-medium text-gray-500 dark:text-gray-400 ml-2">Window:</label>
        {[90, 180, 365].map(d => (
          <button key={d} onClick={() => setDays(d)}
            className={`text-xs px-3 py-1 rounded-full border transition-colors ${days === d ? 'bg-emerald-600 text-white border-emerald-600' : 'bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300 border-gray-300 dark:border-gray-600 hover:border-emerald-400'}`}>
            {d}d
          </button>
        ))}
        <label className="text-xs font-medium text-gray-500 dark:text-gray-400 ml-2">Opoint €/yr:</label>
        <input type="number" value={annualCost} onChange={e => setAnnualCost(Number(e.target.value) || 0)}
          className="text-sm w-24 border border-gray-300 dark:border-gray-600 rounded-md px-2 py-1 bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-200" />
        <a href={reportUrl(days, annualCost)} target="_blank" rel="noopener noreferrer"
          className="ml-auto text-xs px-3 py-1.5 rounded-md bg-emerald-600 hover:bg-emerald-700 text-white inline-flex items-center gap-1.5">
          <Download className="w-3.5 h-3.5" /> Download report
        </a>
      </div>

      {/* All-brands portfolio summary — the thesis in one glance */}
      {portfolio && (
        <div className={`${CARD} overflow-x-auto`}>
          <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">All brands — Existing vs Opoint ({portfolio.window_days}d)</h3>
          <p className="text-xs text-gray-400 mb-3">Cost-per-usable is annualized (chargeable projected to a full year vs the €{annualCost.toLocaleString()}/yr cost).</p>
          <table className="min-w-full text-sm">
            <thead><tr className="text-left text-xs text-gray-500 dark:text-gray-400 border-b border-gray-200 dark:border-gray-700">
              <th className="py-1.5">Brand</th><th className="py-1.5 text-right">Existing</th><th className="py-1.5 text-right">Opoint</th>
              <th className="py-1.5 text-right">Chargeable</th><th className="py-1.5 text-right">Annualized</th><th className="py-1.5 text-right">€/usable</th><th className="py-1.5 text-right">Rate</th></tr></thead>
            <tbody>
              {portfolio.brands.map(r => (
                <tr key={r.brand} className="border-b border-gray-50 dark:border-gray-700/40">
                  <td className="py-1.5 font-medium text-gray-900 dark:text-gray-100">{r.brand}</td>
                  <td className="py-1.5 text-right text-gray-600 dark:text-gray-300">{r.existing_articles.toLocaleString()}</td>
                  <td className="py-1.5 text-right text-gray-600 dark:text-gray-300">{r.opoint_articles.toLocaleString()}</td>
                  <td className="py-1.5 text-right text-gray-700 dark:text-gray-300">{r.chargeable.toLocaleString()}</td>
                  <td className="py-1.5 text-right text-gray-500">{Math.round(r.annualized_chargeable).toLocaleString()}</td>
                  <td className="py-1.5 text-right font-semibold text-amber-600 dark:text-amber-400">{r.cost_per_chargeable_eur != null ? `€${Math.round(r.cost_per_chargeable_eur).toLocaleString()}` : '—'}</td>
                  <td className="py-1.5 text-right text-gray-500">{r.chargeable_rate_pct}%</td>
                </tr>
              ))}
              <tr className="font-semibold border-t-2 border-gray-300 dark:border-gray-600">
                <td className="py-1.5">All brands</td>
                <td className="py-1.5 text-right">{portfolio.totals.existing_articles.toLocaleString()}</td>
                <td className="py-1.5 text-right">{portfolio.totals.opoint_articles.toLocaleString()}</td>
                <td className="py-1.5 text-right">{portfolio.totals.chargeable.toLocaleString()}</td>
                <td className="py-1.5 text-right">{Math.round(portfolio.totals.annualized_chargeable).toLocaleString()}</td>
                <td className="py-1.5 text-right text-amber-600 dark:text-amber-400">{portfolio.totals.cost_per_chargeable_eur != null ? `€${Math.round(portfolio.totals.cost_per_chargeable_eur).toLocaleString()}` : '—'}</td>
                <td className="py-1.5 text-right"></td>
              </tr>
            </tbody>
          </table>
        </div>
      )}

      {loading && <div className="flex items-center justify-center py-16 text-gray-500"><Loader2 className="w-5 h-5 animate-spin mr-2" /> Loading comparison…</div>}

      {!loading && data && (
        <>
          {/* Summary: Existing | Opoint */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {([['Existing news sources', data.summary.existing, 'gray'], ['Opoint', data.summary.opoint, 'emerald']] as const).map(([label, s, color]) => (
              <div key={label} className={`${CARD} ${color === 'emerald' ? 'border-emerald-200 dark:border-emerald-800' : ''}`}>
                <p className={`text-xs font-semibold uppercase mb-3 ${color === 'emerald' ? 'text-emerald-600 dark:text-emerald-400' : 'text-gray-500 dark:text-gray-400'}`}>{label}</p>
                <div className="grid grid-cols-3 gap-3">
                  <div><p className="text-2xl font-bold text-gray-900 dark:text-gray-100">{num(s.articles)}</p><p className="text-xs text-gray-400">articles</p></div>
                  <div><p className="text-2xl font-bold text-gray-900 dark:text-gray-100">{num(s.unique_sources)}</p><p className="text-xs text-gray-400">sources</p></div>
                  <div><p className="text-2xl font-bold text-gray-900 dark:text-gray-100">{num(s.countries)}</p><p className="text-xs text-gray-400">countries</p></div>
                </div>
              </div>
            ))}
          </div>

          {/* Top source domains — Existing | Opoint */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {([['Existing — top source domains', data.top_domains.existing, false], ['Opoint — top source domains', data.top_domains.opoint, true]] as const).map(([label, rows, isOpoint]) => (
              <div key={label} className={`${CARD} overflow-x-auto`}>
                <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">{label}</h3>
                <table className="min-w-full text-sm">
                  <thead><tr className="text-left text-xs text-gray-500 dark:text-gray-400 border-b border-gray-200 dark:border-gray-700">
                    <th className="py-1.5">Domain</th><th className="py-1.5 text-right">Articles</th>{isOpoint && <th className="py-1.5 text-right">Type</th>}</tr></thead>
                  <tbody>
                    {rows.map((d: any) => (
                      <tr key={d.domain} className="border-b border-gray-50 dark:border-gray-700/40">
                        <td className="py-1.5"><button onClick={() => openDomain(d.domain, isOpoint ? 'opoint' : 'existing')} className="text-gray-800 dark:text-gray-200 hover:text-emerald-600 dark:hover:text-emerald-400 hover:underline text-left">{d.domain}</button></td>
                        <td className="py-1.5 text-right text-gray-600 dark:text-gray-300">{num(d.articles)}</td>
                        {isOpoint && <td className="py-1.5 text-right">{d.scholarly ? <span className="text-xs text-amber-600 dark:text-amber-400">scholarly</span> : <span className="text-xs text-green-600 dark:text-green-400">news</span>}</td>}
                      </tr>
                    ))}
                    {rows.length === 0 && <tr><td colSpan={isOpoint ? 3 : 2} className="py-4 text-center text-gray-400 text-xs">no data</td></tr>}
                  </tbody>
                </table>
              </div>
            ))}
          </div>

          {/* Country coverage — Existing | Opoint */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {([['Existing — coverage by country', data.country_compare.existing, 'chart-sc-country-existing'], ['Opoint — coverage by country', data.country_compare.opoint, 'chart-sc-country-opoint']] as const).map(([label, rows, id]) => (
              <div key={id} id={id} className={CARD}>
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300">{label}</h3>
                  <ChartDownloadButton targetId={id} filename={id} />
                </div>
                {rows.length > 0 ? (
                  <ResponsiveContainer width="100%" height={220}>
                    <BarChart data={rows as any} layout="vertical" margin={{ top: 4, right: 16, left: 70, bottom: 4 }}>
                      <CartesianGrid strokeDasharray="3 3" className="opacity-30" />
                      <XAxis type="number" tick={{ fontSize: 11 }} />
                      <YAxis type="category" dataKey="country" tick={{ fontSize: 10 }} width={100} />
                      <Tooltip />
                      <Bar dataKey="count" fill={id.includes('opoint') ? '#10b981' : '#94a3b8'} />
                    </BarChart>
                  </ResponsiveContainer>
                ) : <p className="text-xs text-gray-400 py-8 text-center">No country data (existing side needs MBFC bias-country enrichment).</p>}
              </div>
            ))}
          </div>

          {/* Volume over time */}
          {data.monthly.length > 0 && (
            <div id="chart-sc-monthly" className={CARD}>
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300">Coverage over time — Existing vs Opoint</h3>
                <ChartDownloadButton targetId="chart-sc-monthly" filename="source-comparison-monthly" />
              </div>
              <ResponsiveContainer width="100%" height={240}>
                <AreaChart data={data.monthly} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" className="opacity-30" />
                  <XAxis dataKey="month" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip /><Legend />
                  <Area type="monotone" dataKey="existing" name="Existing" stackId="1" stroke="#94a3b8" fill="#cbd5e1" />
                  <Area type="monotone" dataKey="opoint" name="Opoint" stackId="1" stroke="#10b981" fill="#6ee7b7" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Cost-per-usable (annualized) */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div className={CARD}><p className="text-xs text-gray-500 dark:text-gray-400">Opoint annual cost</p><p className="text-2xl font-bold text-gray-900 dark:text-gray-100">€{num(data.cost.annual_eur)}</p></div>
            <div className={CARD}><p className="text-xs text-gray-500 dark:text-gray-400">Usable / year (projected)</p><p className="text-2xl font-bold text-gray-900 dark:text-gray-100">{num(Math.round(data.cost.annualized_chargeable))}</p><p className="text-xs text-gray-400">{num(data.cost.chargeable)} in {days}d → annualized</p></div>
            <div className={`${CARD} border-2 border-amber-300 dark:border-amber-700`}><p className="text-xs text-gray-500 dark:text-gray-400">Cost per usable article (annual)</p><p className="text-2xl font-bold text-amber-600 dark:text-amber-400">{data.cost.cost_per_chargeable_eur != null ? `€${num(data.cost.cost_per_chargeable_eur)}` : '—'}</p></div>
            <div className={CARD}><p className="text-xs text-gray-500 dark:text-gray-400">Chargeable rate</p><p className="text-2xl font-bold text-gray-900 dark:text-gray-100">{data.chargeable_value.chargeable_rate_pct}%</p><p className="text-xs text-gray-400">of Opoint volume</p></div>
          </div>

          {/* Sentiment + media-type split, and domain overlap */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div id="chart-sc-sentiment" className={CARD}>
              <div className="flex items-center justify-between mb-3"><h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300">Sentiment — Existing vs Opoint</h3><ChartDownloadButton targetId="chart-sc-sentiment" filename="sentiment-compare" /></div>
              {(() => {
                const keys = Array.from(new Set([...data.sentiment_compare.existing, ...data.sentiment_compare.opoint].map(x => x.sentiment)));
                const em = Object.fromEntries(data.sentiment_compare.existing.map(x => [x.sentiment, x.count]));
                const om = Object.fromEntries(data.sentiment_compare.opoint.map(x => [x.sentiment, x.count]));
                const rows = keys.map(k => ({ sentiment: k, Existing: em[k] || 0, Opoint: om[k] || 0 }));
                return (
                  <ResponsiveContainer width="100%" height={220}>
                    <BarChart data={rows} margin={{ top: 4, right: 16, left: 0, bottom: 4 }}>
                      <CartesianGrid strokeDasharray="3 3" className="opacity-30" /><XAxis dataKey="sentiment" tick={{ fontSize: 10 }} /><YAxis tick={{ fontSize: 11 }} /><Tooltip /><Legend />
                      <Bar dataKey="Existing" fill="#94a3b8" /><Bar dataKey="Opoint" fill="#10b981" />
                    </BarChart>
                  </ResponsiveContainer>
                );
              })()}
            </div>
            <div className={CARD}>
              <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">Domain overlap</h3>
              <div className="grid grid-cols-3 gap-3 mb-3">
                <div><p className="text-2xl font-bold text-gray-700 dark:text-gray-300">{num(data.overlap.existing_only)}</p><p className="text-xs text-gray-400">existing-only</p></div>
                <div><p className="text-2xl font-bold text-gray-900 dark:text-gray-100">{num(data.overlap.shared)}</p><p className="text-xs text-gray-400">shared</p></div>
                <div><p className="text-2xl font-bold text-emerald-600 dark:text-emerald-400">{num(data.overlap.opoint_only)}</p><p className="text-xs text-gray-400">Opoint-only</p></div>
              </div>
              <p className="text-xs text-gray-400 mb-1">Opoint-only domains (incremental reach):</p>
              <p className="text-xs text-gray-600 dark:text-gray-300">{data.overlap.opoint_only_domains.slice(0, 12).map(d => d.domain).join(', ') || '—'}</p>
            </div>
          </div>

          {/* Quality funnel */}
          <div className={`${CARD} border-2 border-emerald-300 dark:border-emerald-700`}>
            <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">Is Opoint worth it? — quality-adjusted funnel</h3>
            <p className="text-xs text-gray-400 mb-4">Of Opoint's raw volume: on-brand (relevance ≥ {data.chargeable_value.min_relevance}) → non-scholarly → incremental (a source we don't already cover) = chargeable.</p>
            <div className="flex items-end gap-2 flex-wrap">
              {([['Opoint raw', data.chargeable_value.opoint_total, 'bg-gray-300 dark:bg-gray-600'], ['On-brand', data.chargeable_value.on_brand, 'bg-emerald-300 dark:bg-emerald-800'], ['+ non-scholarly', data.chargeable_value.non_scholarly, 'bg-emerald-400 dark:bg-emerald-700'], ['+ incremental = CHARGEABLE', data.chargeable_value.chargeable, 'bg-emerald-600']] as const).map(([label, val, color], i) => (
                <div key={i} className="flex-1 min-w-[120px] text-center">
                  <div className={`${color} rounded-t-md mx-auto`} style={{ height: `${Math.max(8, (val / Math.max(data.chargeable_value.opoint_total, 1)) * 120)}px` }} />
                  <p className="text-lg font-bold text-gray-900 dark:text-gray-100 mt-1">{num(val)}</p>
                  <p className="text-[11px] text-gray-500 dark:text-gray-400 leading-tight">{label}</p>
                </div>
              ))}
            </div>
          </div>

          {/* Relevance histogram */}
          <div id="chart-sc-relhist" className={CARD}>
            <div className="flex items-center justify-between mb-1">
              <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300">On-brand relevance distribution (Opoint)</h3>
              <ChartDownloadButton targetId="chart-sc-relhist" filename="opoint-relevance-distribution" />
            </div>
            <p className="text-xs text-gray-400 mb-4">Mass at the low end = peripheral / citation mentions, not brand news.</p>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={data.relevance_histogram} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
                <CartesianGrid strokeDasharray="3 3" className="opacity-30" />
                <XAxis dataKey="bucket" tick={{ fontSize: 11 }} /><YAxis tick={{ fontSize: 11 }} /><Tooltip />
                <Bar dataKey="count" name="Opoint articles">
                  {data.relevance_histogram.map((b, i) => <Cell key={i} fill={parseFloat(b.bucket) >= data.chargeable_value.min_relevance ? '#10b981' : '#cbd5e1'} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Precision */}
          <div id="chart-sc-precision" className={CARD}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300">Brand-match precision: Opoint entities (Wikidata) vs keyword classification</h3>
              <ChartDownloadButton targetId="chart-sc-precision" filename="precision" />
            </div>
            <ResponsiveContainer width="100%" height={180}>
              <BarChart data={[{ method: 'Opoint entity-verified', count: data.precision.opoint_entity_verified }, { method: 'Keyword-classified', count: data.precision.keyword_classified }]} layout="vertical" margin={{ top: 8, right: 24, left: 80, bottom: 8 }}>
                <CartesianGrid strokeDasharray="3 3" className="opacity-30" />
                <XAxis type="number" tick={{ fontSize: 11 }} /><YAxis type="category" dataKey="method" tick={{ fontSize: 11 }} width={140} /><Tooltip />
                <Bar dataKey="count" fill="#10b981" />
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Chargeable drill-down */}
          <div className={`${CARD} overflow-x-auto`}>
            <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">The chargeable articles (sample)</h3>
            <p className="text-xs text-gray-400 mb-3">The actual high-value incremental items Opoint adds — eyeball whether they're worth paying for.</p>
            <table className="min-w-full text-sm">
              <thead><tr className="text-left text-xs text-gray-500 dark:text-gray-400 border-b border-gray-200 dark:border-gray-700">
                <th className="py-1.5">Article</th><th className="py-1.5">Source</th><th className="py-1.5 text-right">Relevance</th><th className="py-1.5 text-right">Rank</th></tr></thead>
              <tbody>
                {data.chargeable_samples.map((s, i) => (
                  <tr key={i} className="border-b border-gray-50 dark:border-gray-700/40">
                    <td className="py-1.5 max-w-md"><a href={s.url} target="_blank" rel="noopener noreferrer" className="text-gray-800 dark:text-gray-200 hover:text-emerald-600 dark:hover:text-emerald-400 line-clamp-1">{s.title}</a></td>
                    <td className="py-1.5 text-gray-500 dark:text-gray-400 text-xs">{s.source}</td>
                    <td className="py-1.5 text-right text-gray-700 dark:text-gray-300">{s.relevance.toFixed(2)}</td>
                    <td className="py-1.5 text-right text-gray-400 text-xs">{s.rank_global ? num(s.rank_global) : '—'}</td>
                  </tr>
                ))}
                {data.chargeable_samples.length === 0 && <tr><td colSpan={4} className="py-4 text-center text-gray-400 text-xs">No chargeable items in this window.</td></tr>}
              </tbody>
            </table>
          </div>
        </>
      )}

      {!loading && !data && brandId != null && <div className="text-center py-12 text-gray-400 text-sm">No comparison data.</div>}

      {/* Domain drill-down overlay */}
      {domainDrill && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={() => setDomainDrill(null)}>
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-2xl w-full max-h-[80vh] overflow-y-auto p-6" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-100">{domainDrill.domain} <span className="text-xs text-gray-400">· {domainDrill.dataset}</span></h3>
              <button onClick={() => setDomainDrill(null)} className="text-gray-400 hover:text-gray-700 text-lg leading-none">×</button>
            </div>
            {domainDrill.articles.length === 0 ? <div className="py-8 text-center text-gray-400 text-sm"><Loader2 className="w-4 h-4 animate-spin inline mr-2" />loading…</div> : (
              <table className="min-w-full text-sm">
                <thead><tr className="text-left text-xs text-gray-500 dark:text-gray-400 border-b border-gray-200 dark:border-gray-700"><th className="py-1.5">Article</th><th className="py-1.5 text-right">Date</th><th className="py-1.5 text-right">Sent.</th><th className="py-1.5 text-right">Rel.</th></tr></thead>
                <tbody>
                  {domainDrill.articles.map((a, i) => (
                    <tr key={i} className="border-b border-gray-50 dark:border-gray-700/40">
                      <td className="py-1.5 max-w-sm"><a href={a.uri} target="_blank" rel="noopener noreferrer" className="text-gray-800 dark:text-gray-200 hover:text-emerald-600 line-clamp-1">{a.title}</a></td>
                      <td className="py-1.5 text-right text-gray-400 text-xs">{a.publication_date ? a.publication_date.slice(0, 10) : '—'}</td>
                      <td className="py-1.5 text-right text-gray-500 text-xs">{a.sentiment || '—'}</td>
                      <td className="py-1.5 text-right text-gray-500 text-xs">{a.relevance != null ? a.relevance.toFixed(2) : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
