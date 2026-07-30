"""Self-contained interactive HTML renderer for the Wiley quarterly brief.

Produces ONE standalone .html file — all CSS + JS + data inlined, no external
requests — so it's emailable and archivable exactly like the PPTX/DOCX, but
explorable: a consensus×evidence calibration matrix you click into per-trend
evidence ledgers, an events explorer with source links, and the exec summary.

Same inputs as ``forecast_bundle_pptx.build_bundle_pptx`` (reuses the same
``_calibration_read`` + ``events_for_scenario`` so the HTML and the deck tell
the identical story). Consumed by ``wiley_delivery_service.generate_bundle_html``
and ``GET /api/forecast/deliverables/bundle.html``.
"""
from __future__ import annotations

import html
import json
from typing import Optional

from app.compliance.ai_disclosure import (
    disclosure_footer_html as _ai_footer,
    html_meta_tags as _ai_meta,
)


def _esc(s) -> str:
    return html.escape(str(s) if s is not None else "")


def _build_report_data(items, *, period_label, cadence, bundle_synthesis,
                       events_by_topic, data_quality_note) -> dict:
    """Assemble the JSON the page renders from. One trend = one scenario."""
    from app.services.forecast_pptx_export import _calibration_read
    from app.services.wiley_event_extraction import events_for_scenario

    synth = bundle_synthesis or {}
    payload = synth.get("payload") or synth  # tolerate either shape
    events_by_topic = events_by_topic or {}

    def _ev_dict(e):
        return {
            "actor": e.get("actor"), "action": e.get("action"),
            "subject": e.get("subject"),
            "magnitude": (f"{e['magnitude_value']:g} {e.get('magnitude_unit') or ''}".strip()
                          if e.get("magnitude_value") is not None else None),
            "date": (str(e.get("event_date"))[:10] if e.get("event_date") else None),
            "sources": e.get("source_urls") or [],
            "confidence": e.get("confidence"),
        }

    trends = []
    for assessment, _run, _prior in items:
        topic = assessment.get("topic") or "—"
        t_events = events_by_topic.get(topic) or []
        for v in (assessment.get("scenario_verdicts") or []):
            if v.get("verdict_label") == "Done":
                continue
            deck_info = (v.get("top_articles") or {}).get("deck_info") or {}
            name = deck_info.get("deck_scenario_name") or v.get("scenario_title") or "—"
            basis = deck_info.get("consensus_pct")
            conf, ctr = events_for_scenario(t_events, name)
            read_text, category = _calibration_read(basis, len(conf), len(ctr))
            trends.append({
                "topic": topic,
                "scenario": name,
                "horizon": (v.get("horizon_type") or "").upper(),
                "basis_pct": (round(float(basis), 1) if isinstance(basis, (int, float)) else None),
                "primary_signal": deck_info.get("primary_signal") or "",
                "n_confirm": len(conf),
                "n_counter": len(ctr),
                "read": read_text,
                "category": category,
                "confirming": [_ev_dict(e) for e in conf[:6]],
                "countering": [_ev_dict(e) for e in ctr[:6]],
            })

    # All deck-included events for the explorer (deduped, period-scoped already).
    all_events = []
    seen = set()
    for topic, evs in events_by_topic.items():
        for e in evs:
            key = (e.get("actor"), e.get("action"), e.get("subject"), str(e.get("event_date")))
            if key in seen:
                continue
            seen.add(key)
            d = _ev_dict(e)
            d["topic"] = topic
            all_events.append(d)
    all_events.sort(key=lambda e: e.get("date") or "", reverse=True)

    per_topic = []
    for assessment, _run, _prior in items:
        summary = assessment.get("summary") or {}
        briefing = summary.get("topic_briefing") or {}
        per_topic.append({
            "topic": assessment.get("topic") or "—",
            "headline": briefing.get("headline") or "",
            "lede": briefing.get("lede") or "",
            "recommendations": summary.get("strategic_recommendations") or [],
            "next_steps": summary.get("next_steps") or [],
        })

    return {
        "period_label": period_label,
        "cadence": cadence,
        "data_quality_note": data_quality_note or "",
        "exec_summary": (payload.get("exec_summary") or {}).get("letter") or "",
        "expert_commentary": payload.get("expert_commentary") or "",
        "strategic_overview": payload.get("strategic_overview") or "",
        "cross_cutting_themes": payload.get("cross_cutting_themes") or [],
        "decision_framework": payload.get("executive_decision_framework") or [],
        "whats_changed": payload.get("whats_changed") or {},
        "trends": trends,
        "events": all_events,
        "per_topic": per_topic,
    }


_CSS = """
:root{--navy:#0f172a;--ink:#1f2937;--muted:#64748b;--line:#e2e8f0;
--pink:#d6346c;--pink-d:#b11e57;--amber:#d97706;--green:#059669;--bg:#f8fafc;--card:#fff;}
*{box-sizing:border-box}body{margin:0;font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;color:var(--ink);background:var(--bg)}
a{color:var(--pink-d)}
header.brief{background:var(--navy);color:#fff;padding:28px 40px;border-bottom:4px solid var(--pink)}
header.brief .eyebrow{color:#f9a8c4;font-size:12px;font-weight:700;letter-spacing:.08em;text-transform:uppercase}
header.brief h1{margin:6px 0 2px;font-size:30px}
header.brief .sub{color:#cbd5e1;font-style:italic}
.gap{background:#fffbeb;border-left:4px solid var(--amber);color:#7c4a03;padding:10px 16px;margin:0;font-size:13px}
main{max-width:1100px;margin:0 auto;padding:28px 40px 80px}
section{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:22px 24px;margin:18px 0;box-shadow:0 1px 2px rgba(0,0,0,.03)}
h2{margin:0 0 4px;font-size:20px;color:var(--navy)}
.section-sub{color:var(--muted);font-size:13px;margin:0 0 16px}
/* calibration matrix — explicit 3-col × (header+2) grid so the 2×2 can't
   mis-place (auto-flow + a spanning axis label was scrambling the quadrants) */
.matrix{display:grid;grid-template-columns:92px 1fr 1fr;grid-template-rows:26px 1fr 1fr;gap:8px;align-items:stretch}
.m-colhead{grid-row:1;align-self:end;text-align:center;font-size:11px;font-weight:700;color:var(--muted);letter-spacing:.05em;text-transform:uppercase}
.m-colhead.thin{grid-column:2}.m-colhead.conf{grid-column:3}
.rowlabel{font-weight:700;color:var(--muted);font-size:12px;display:flex;align-items:center;justify-content:center;text-align:center}
.rowlabel.hi{grid-row:2;grid-column:1}.rowlabel.lo{grid-row:3;grid-column:1}
.cell{border:1px dashed var(--line);border-radius:10px;padding:12px;min-height:150px}
.cell h4{margin:0 0 8px;font-size:11px;letter-spacing:.05em;text-transform:uppercase;color:var(--muted)}
.cell.hot{background:#fff7ed;border-color:#fdba74}
.cell.gold{background:#ecfdf5;border-color:#6ee7b7}
#cell-hi-thin{grid-row:2;grid-column:2}#cell-hi-conf{grid-row:2;grid-column:3}
#cell-lo-thin{grid-row:3;grid-column:2}#cell-lo-conf{grid-row:3;grid-column:3}
.chip{display:inline-block;margin:3px 4px 3px 0;padding:5px 10px;border-radius:16px;font-size:12.5px;cursor:pointer;border:1px solid var(--line);background:#fff;transition:.12s}
.chip:hover{border-color:var(--pink);box-shadow:0 1px 4px rgba(214,52,108,.2)}
.chip .dot{font-size:11px;margin-right:4px}
.chip.crowd_wrong{border-color:#fdba74;background:#fff7ed}
.chip.outlier_confirming{border-color:#6ee7b7;background:#ecfdf5}
/* ledger panel */
#ledger{position:fixed;top:0;right:0;width:min(520px,92vw);height:100vh;background:#fff;border-left:1px solid var(--line);box-shadow:-8px 0 24px rgba(0,0,0,.12);transform:translateX(100%);transition:.22s;overflow-y:auto;z-index:50}
#ledger.open{transform:none}
#ledger .lhead{background:var(--navy);color:#fff;padding:18px 22px;position:sticky;top:0}
#ledger .lhead .x{float:right;cursor:pointer;font-size:22px;line-height:1;opacity:.8}
#ledger .lbody{padding:18px 22px}
.basis{font-weight:700;color:var(--pink-d)}
.read{padding:10px 12px;border-radius:8px;font-weight:600;margin:12px 0}
.read.crowd_wrong{background:#fff7ed;color:#9a3412}.read.outlier_confirming{background:#ecfdf5;color:#065f46}
.read.holding,.read.leaning{background:#f1f5f9;color:#334155}.read.doubt{background:#fef2f2;color:#991b1b}
.read.noise,.read.early,.read.contested{background:#f8fafc;color:#64748b}
.evgrp{margin:14px 0}.evgrp h5{margin:0 0 6px;font-size:12px;letter-spacing:.04em;text-transform:uppercase}
.evgrp.c h5{color:var(--green)}.evgrp.x h5{color:var(--pink-d)}
.ev{border-left:3px solid var(--line);padding:6px 10px;margin:6px 0;background:#fafafa;border-radius:0 6px 6px 0;font-size:13.5px}
.ev.c{border-color:var(--green)}.ev.x{border-color:var(--pink-d)}
.ev .meta{color:var(--muted);font-size:12px}
.overlay{position:fixed;inset:0;background:rgba(15,23,42,.3);opacity:0;pointer-events:none;transition:.2s;z-index:40}
.overlay.on{opacity:1;pointer-events:auto}
/* events explorer */
.filters{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px}
.filters select,.filters input{padding:6px 10px;border:1px solid var(--line);border-radius:6px;font-size:13px}
.evrow{border-bottom:1px solid var(--line);padding:9px 0}
.evrow .t{font-weight:600}
.tag{display:inline-block;font-size:11px;padding:2px 7px;border-radius:10px;margin-left:6px}
.tag.conf{background:#ecfdf5;color:#065f46}.tag.ctr{background:#fef2f2;color:#991b1b}
.letter{white-space:pre-wrap;font-size:15.5px;line-height:1.7}
.theme{margin:12px 0}.theme .lead{font-weight:700;color:var(--navy)}
details.method{margin-top:18px}details.method summary{cursor:pointer;font-weight:600;color:var(--muted)}
.topic-block{border-top:1px solid var(--line);padding-top:14px;margin-top:14px}
.muted{color:var(--muted)} .small{font-size:12.5px}
/* print-only linear calibration (built by JS, hidden on screen) */
.print-only{display:none}
.pcard{border:1px solid var(--line);border-radius:8px;padding:12px 14px;margin:10px 0}
.phead{font-weight:700;color:var(--navy)}
.pgrouphead{margin:16px 0 4px;font-size:13px;letter-spacing:.04em;text-transform:uppercase;color:var(--muted)}
.pgrouphead.hot{color:var(--amber)} .pgrouphead.gold{color:var(--green)}
/* ===== PRINT / PDF ===== An interactive screen layout (CSS-grid matrix +
   fixed click-drawer) shatters across page breaks, so for print we hide the
   interactive bits and show a linear, paginate-safe rendering with every
   ledger expanded inline (you can't click in a PDF). */
@media print{
  body{background:#fff;font-size:12px}
  header.brief{padding:14px 0;border-bottom:3px solid var(--pink)}
  header.brief h1{font-size:24px}
  main{max-width:none;margin:0;padding:0 6px}
  section{break-inside:avoid;box-shadow:none;border:none;border-bottom:1px solid var(--line);border-radius:0;padding:12px 0;margin:8px 0}
  #ledger,.overlay,.filters,.matrix,.screen-only{display:none !important}
  .print-only{display:block !important}
  .pcard,.evrow,.theme,.topic-block,.evgrp{break-inside:avoid}
  .letter{font-size:12.5px;line-height:1.5}
  a{color:#1f2937;text-decoration:none}
}
"""


def _matrix_cell_trends(trends, want_categories):
    out = [t for t in trends if t["category"] in want_categories]
    return out


def build_bundle_html(items, *, period_label, cadence, updates_only=False,
                      bundle_synthesis=None, eos_per_topic=None,
                      events_by_topic=None, data_quality_note=None,
                      review_findings=None, review_verdict=None) -> bytes:
    data = _build_report_data(
        items, period_label=period_label, cadence=cadence,
        bundle_synthesis=bundle_synthesis, events_by_topic=events_by_topic,
        data_quality_note=data_quality_note,
    )
    data_json = json.dumps(data, default=str)

    gap_html = (f'<p class="gap">{_esc(data["data_quality_note"])}</p>'
                if data["data_quality_note"] else "")

    cadence_label = {"monthly": "Monthly", "quarterly": "Quarterly",
                     "all": "Strategic"}.get(cadence, "")

    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
{_ai_meta()}
<title>Wiley {cadence_label} Foresight Update — {_esc(period_label)}</title>
<style>{_CSS}</style></head>
<body>
<header class="brief">
  <div class="eyebrow">Wiley Horizons · Foresight{(" · What's changed" if updates_only else "")}</div>
  <h1>{cadence_label} Foresight Update — {_esc(period_label)}</h1>
  <div class="sub">Consensus is the forecast basis; named events are the test. Produced by AunooAI.</div>
</header>
{gap_html}
<main>
  <section id="exec">
    <h2>Executive summary</h2>
    <div class="letter" id="execLetter"></div>
  </section>

  <section id="expert" style="display:none">
    <h2>Expert view — emerging themes</h2>
    <div class="letter" id="expertCommentary"></div>
  </section>

  <section id="calib">
    <h2>Calibration — where consensus and evidence diverge</h2>
    <p class="section-sub"><span class="screen-only">Each trend placed by the consensus at forecast time (vertical) against the evidence since (horizontal). Click any trend for its evidence ledger.</span><span class="print-only">Trends grouped by the consensus×evidence read; divergences first. Each ledger is expanded below.</span> The highlighted cells are the high-value divergences.</p>
    <div class="matrix screen-only">
      <div class="m-colhead thin">← evidence thin / counter</div>
      <div class="m-colhead conf">evidence confirming →</div>
      <div class="rowlabel hi">HIGH<br>consensus</div>
      <div class="cell hot" id="cell-hi-thin"><h4>⚠ Consensus, evidence thin — crowd may be wrong (or too early)</h4></div>
      <div class="cell" id="cell-hi-conf"><h4>● Consensus holding — wisdom of crowds</h4></div>
      <div class="rowlabel lo">LOW<br>consensus</div>
      <div class="cell" id="cell-lo-thin"><h4>· Outlier, quiet — not (yet) bearing out</h4></div>
      <div class="cell gold" id="cell-lo-conf"><h4>★ Outlier confirming — signal the crowd missed</h4></div>
    </div>
    <div class="print-only" id="printCalib"></div>
  </section>

  <section id="whatschanged">
    <h2>What's changed</h2>
    <p class="section-sub">Named events this period, plus scenario drift, new themes, and where press attention moved.</p>
    <div id="wcBlocks"></div>
  </section>

  <section id="overview">
    <h2>Strategic overview</h2>
    <div class="letter" id="ovText"></div>
  </section>

  <section id="themes">
    <h2>Cross-cutting themes</h2>
    <div id="themeList"></div>
  </section>

  <section id="decisions">
    <h2>Executive decision framework</h2>
    <div id="decList"></div>
  </section>

  <section id="topics">
    <h2>By topic</h2>
    <div id="topicList"></div>
  </section>

  <section id="events">
    <h2>Events explorer</h2>
    <div class="filters screen-only">
      <select id="fTopic"><option value="">All topics</option></select>
      <select id="fDir">
        <option value="">All directions</option>
        <option value="conf">Confirming</option>
        <option value="ctr">Countering</option>
      </select>
      <input id="fText" placeholder="filter text…" size="20">
      <span class="muted small" id="evCount"></span>
    </div>
    <div id="evList"></div>
  </section>

  <details class="method"><summary>How this brief is made (methodology)</summary>
    <p class="small muted">Each tracked trend is a claim. The consensus measured at forecast time is the
    prevailing expectation (what most sources expected — not proof). Named real-world events extracted
    from the corpus since then either bear the claim out or don't; the divergence between the two is the
    finding. Articles are filtered to a topic by a relevance score, events are de-duplicated and tagged
    as confirming or countering each trend, and AI-slop is stripped from the prose. We never present a
    moving "accuracy %" or "the forecast is playing out".</p>
  </details>
</main>

<div class="overlay" id="overlay" onclick="closeLedger()"></div>
<aside id="ledger"><div class="lhead"><span class="x" onclick="closeLedger()">&times;</span>
  <div id="ledgerHead"></div></div><div class="lbody" id="ledgerBody"></div></aside>

<script type="application/json" id="data">{data_json}</script>
<script>
const D = JSON.parse(document.getElementById('data').textContent);

function el(tag, cls, html){{const e=document.createElement(tag); if(cls)e.className=cls; if(html!=null)e.innerHTML=html; return e;}}
function esc(s){{return (s==null?'':String(s)).replace(/[&<>]/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;'}}[c]));}}

// exec summary + overview (render **bold** markers)
function md(s){{return esc(s).replace(/\\*\\*(.+?)\\*\\*/g,'<strong>$1</strong>');}}
document.getElementById('execLetter').innerHTML = md(D.exec_summary || '(no summary)');
if((D.expert_commentary||'').trim()){{
  document.getElementById('expert').style.display='';
  document.getElementById('expertCommentary').innerHTML =
    (D.expert_commentary||'').split(/\\n\\s*\\n/).map(p=>'<p>'+md(p)+'</p>').join('');
}}
document.getElementById('ovText').innerHTML = md(D.strategic_overview || '');

// calibration matrix — place each trend by its ACTUAL axes (basis × evidence
// direction), not by category. (Category only drives the chip colour/dot so
// genuine divergences pop within their cell.) This keeps a high-consensus
// no-evidence-yet trend out of the "low / outlier" row.
function cellFor(t){{
  const hi = (t.basis_pct!=null) && t.basis_pct >= 60;
  const confirming = (t.n_confirm - t.n_counter) > 0;
  if(hi && confirming) return 'cell-hi-conf';
  if(hi && !confirming) return 'cell-hi-thin';
  if(!hi && confirming) return 'cell-lo-conf';
  return 'cell-lo-thin';
}}
D.trends.forEach((t,i)=>{{
  const c=document.getElementById(cellFor(t)); if(!c)return;
  const dot=t.category==='crowd_wrong'?'⚠':t.category==='outlier_confirming'?'★':t.category==='holding'||t.category==='leaning'?'●':'·';
  const chip=el('span','chip '+t.category,'<span class="dot">'+dot+'</span>'+esc(t.scenario));
  chip.title=t.topic+' — '+t.read; chip.onclick=()=>openLedger(i);
  c.appendChild(chip);
}});

// ledger drawer
function openLedger(i){{
  const t=D.trends[i];
  document.getElementById('ledgerHead').innerHTML='<div style="font-size:12px;color:#f9a8c4">'+esc(t.topic)+(t.horizon?' · '+t.horizon:'')+'</div><div style="font-size:19px;font-weight:700;margin-top:3px">'+esc(t.scenario)+'</div>';
  let h='';
  if(t.basis_pct!=null) h+='<p><span class="basis">Forecast basis: '+t.basis_pct+'%</span> of sources framed this as likely at forecast time.</p>';
  if(t.primary_signal) h+='<p class="small muted">Outlier watch: '+esc(t.primary_signal)+'</p>';
  h+='<div class="read '+t.category+'">'+esc(t.read)+'</div>';
  h+=evGroup('New evidence — confirming', t.confirming, 'c');
  h+=evGroup('Counter-evidence', t.countering, 'x');
  document.getElementById('ledgerBody').innerHTML=h;
  document.getElementById('ledger').classList.add('open');
  document.getElementById('overlay').classList.add('on');
}}
function evGroup(title, evs, k){{
  let h='<div class="evgrp '+k+'"><h5>'+title+' ('+evs.length+')</h5>';
  if(!evs.length) h+='<div class="small muted">None this cycle.</div>';
  evs.forEach(e=>{{
    const mag=e.magnitude?' ('+esc(e.magnitude)+')':''; const dt=e.date?' — '+esc(e.date):'';
    const src=(e.sources&&e.sources.length)?' <a href="'+esc(e.sources[0])+'" target="_blank" rel="noopener">source</a>':'';
    h+='<div class="ev '+k+'">'+esc(e.actor)+' '+esc(e.action)+' '+esc(e.subject)+mag+'<div class="meta">'+dt+src+'</div></div>';
  }});
  return h+'</div>';
}}
function closeLedger(){{document.getElementById('ledger').classList.remove('open');document.getElementById('overlay').classList.remove('on');}}
document.addEventListener('keydown',e=>{{if(e.key==='Escape')closeLedger();}});

// print-only linear calibration — every ledger expanded inline, grouped so
// the divergences lead. (Interactive matrix + drawer are hidden in print.)
(function(){{
  const order=[['crowd_wrong','⚠ Consensus not bearing out — crowd may be wrong','hot'],
    ['outlier_confirming','★ Outlier confirming — signal the crowd missed','gold'],
    ['holding','● Consensus holding — wisdom of crowds',''],
    ['leaning','Evidence leaning toward the trend',''],
    ['doubt','Counter-evidence outweighs confirming',''],
    ['contested','Contested — evidence split',''],
    ['noise','Outlier, quiet',''],['early','Too early — no events yet','']];
  const byCat={{}}; D.trends.forEach(t=>{{(byCat[t.category]=byCat[t.category]||[]).push(t);}});
  let h='';
  order.forEach(([cat,label,cls])=>{{
    const ts=byCat[cat]; if(!ts||!ts.length)return;
    h+='<div class="pgrouphead '+cls+'">'+esc(label)+' ('+ts.length+')</div>';
    ts.forEach(t=>{{
      h+='<div class="pcard"><div class="phead">'+esc(t.scenario)+' <span class="muted small">· '+esc(t.topic)+(t.horizon?' · '+t.horizon:'')+'</span></div>';
      if(t.basis_pct!=null) h+='<div class="small"><span class="basis">Forecast basis: '+t.basis_pct+'%</span> of sources framed this as likely at forecast time.</div>';
      h+='<div class="small" style="margin:4px 0 6px"><em>'+esc(t.read)+'</em></div>';
      if(t.confirming.length||t.countering.length){{
        h+=evGroup('Confirming', t.confirming, 'c')+evGroup('Counter-evidence', t.countering, 'x');
      }}
      h+='</div>';
    }});
  }});
  document.getElementById('printCalib').innerHTML=h;
}})();

// what's changed
(function(){{
  const wc=D.whats_changed||{{}}; const map=[['events','Named events this period'],['scenario_drift','Scenarios that moved'],['emerging','New on the watch'],['coverage_shifts','Where press attention shifted']];
  let h=''; map.forEach(([k,lbl])=>{{const arr=wc[k]||[]; if(!arr.length)return; h+='<div class="evgrp"><h5>'+lbl+'</h5><ul style="margin:4px 0 0;padding-left:20px">'+arr.map(x=>'<li>'+esc(x)+'</li>').join('')+'</ul></div>';}});
  document.getElementById('wcBlocks').innerHTML = h || '<p class="muted small">No changes recorded this period.</p>';
}})();

// events explorer
const fTopic=document.getElementById('fTopic'),fDir=document.getElementById('fDir'),fText=document.getElementById('fText');
[...new Set(D.events.map(e=>e.topic))].forEach(t=>{{const o=el('option');o.value=t;o.textContent=t;fTopic.appendChild(o);}});
function renderEvents(){{
  const q=(fText.value||'').toLowerCase(), tp=fTopic.value;
  const rows=D.events.filter(e=>(!tp||e.topic===tp)&&(!q||(e.actor+' '+e.action+' '+e.subject).toLowerCase().includes(q)));
  document.getElementById('evCount').textContent=rows.length+' events';
  document.getElementById('evList').innerHTML=rows.map(e=>{{
    const mag=e.magnitude?' ('+esc(e.magnitude)+')':''; const dt=e.date?'<span class="muted small"> · '+esc(e.date)+'</span>':'';
    const src=(e.sources&&e.sources.length)?' · <a href="'+esc(e.sources[0])+'" target="_blank" rel="noopener">source</a>':'';
    return '<div class="evrow"><span class="t">'+esc(e.actor)+' '+esc(e.action)+' '+esc(e.subject)+'</span>'+mag+dt+'<span class="muted small"> · '+esc(e.topic)+src+'</span></div>';
  }}).join('') || '<p class="muted small">No matching events.</p>';
}}
[fTopic,fText].forEach(x=>x.addEventListener('input',renderEvents)); renderEvents();

// themes / decisions / topics
document.getElementById('themeList').innerHTML=(D.cross_cutting_themes||[]).map(t=>'<div class="theme"><span class="lead">'+esc(t.lead||t.name||'')+'</span> '+esc(t.body||'')+'</div>').join('')||'<p class="muted small">—</p>';
document.getElementById('decList').innerHTML=(D.decision_framework||[]).map(t=>'<div class="theme"><span class="lead">'+esc(t.headline||t.name||'')+'</span> '+esc(t.body||'')+'</div>').join('')||'<p class="muted small">—</p>';
document.getElementById('topicList').innerHTML=(D.per_topic||[]).map(t=>{{
  let h='<div class="topic-block"><h3 style="margin:0 0 2px">'+esc(t.topic)+'</h3>';
  if(t.headline)h+='<div class="muted small" style="margin-bottom:6px">'+esc(t.headline)+'</div>';
  if(t.lede)h+='<p>'+esc(t.lede)+'</p>';
  if((t.recommendations||[]).length){{
    h+='<div class="small"><strong>Strategic recommendations:</strong><ul style="margin:4px 0;padding-left:20px">';
    h+=t.recommendations.slice(0,4).map(r=>{{
      if(typeof r==='string') return '<li>'+esc(r)+'</li>';
      const head=esc(r.headline||r.body||r.recommendation||'');
      const hz=r.horizon?' <span class="muted">('+esc(r.horizon)+')</span>':'';
      const why=r.rationale?'<div class="muted" style="margin:2px 0 6px">'+esc(r.rationale)+'</div>':'';
      return '<li><strong>'+head+'</strong>'+hz+why+'</li>';
    }}).join('');
    h+='</ul></div>';
  }}
  if((t.next_steps||[]).length){{
    h+='<div class="small"><strong>Next steps:</strong><ul style="margin:4px 0;padding-left:20px">';
    h+=t.next_steps.slice(0,4).map(s=>{{
      if(typeof s==='string') return '<li>'+esc(s)+'</li>';
      const cat=s.category?'<span class="muted">'+esc(s.category)+': </span>':'';
      return '<li>'+cat+esc(s.action||s.body||'')+'</li>';
    }}).join('');
    h+='</ul></div>';
  }}
  return h+'</div>';
}}).join('');
</script>
{_ai_footer()}
</body></html>"""
    return page.encode("utf-8")
