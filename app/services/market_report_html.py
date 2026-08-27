"""A market as one self-contained HTML file.

Deliberately thin. ``html_report_common`` already supplies the document shell,
the base stylesheet and — importantly — the EU AI Act Article 50 markers, both
the machine-readable meta tag and the visible footer. Hand-rolling a second
document wrapper here would duplicate that and quietly ship a report without
the disclosure.

Charts are **inline SVG**, drawn from the stored figures with no library. That
is the same choice ``horizons_html`` makes and for the same reason: the page
has to render with no network access at all, so a CDN chart library or a remote
image is not an option. matplotlib PNGs are the deck path, not this one.

Nothing here computes. It renders what ``market_assessment``,
``market_analysis`` and ``market_publish`` already returned: which events are
material, which records are one event, and whose word an event rests on are
fields on the objects this module receives, never decisions it makes.
"""

import base64
import logging
import os
import re
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Dict, List, Optional

from app.services.html_report_common import esc, html_document, section_open

logger = logging.getLogger(__name__)

# The report's own styles, appended to BASE_CSS. Only what the shared sheet
# does not already carry.
# The shared-link treatment: a market news page rather than a report.
#
# Every rule is scoped under `.mm-news`, because `html_document` and `BASE_CSS`
# are shared with the consensus and horizons reports and an unscoped rule here
# would restyle all three.
#
# Self-contained by necessity — this file is emailed, saved and opened offline,
# so there are no icon fonts, no CDN scripts and no web fonts. The sparklines
# are inline SVG built from the same series the page quotes.
NEWS_CSS = """
.mm-news { --n-bg:#f4f6f8; --n-shell:#fff; --n-panel:#fff; --n-text:#111827;
           --n-muted:#596674; --n-line:#d9e0e5; --n-accent:#096b74;
           --n-accent-soft:#dff3f2; --n-blue:#2259a8; --n-green:#21734a;
           --n-orange:#9a5315; --n-purple:#6c48a1;
           margin:0 0 1.6rem; border:1px solid var(--n-line); border-radius:14px;
           overflow:hidden; background:var(--n-bg); color:var(--n-text); }
.mm-news * { box-sizing:border-box; }
/* Dark bar: the Cyberfuturists mark is drawn for a dark ground. */
.mm-news .n-top { display:flex; align-items:center; gap:12px 20px; padding:14px 18px;
                  flex-wrap:wrap;
                  background:#0b1220; color:#e6edf5; border-bottom:1px solid #1e293b; }
.mm-news .n-brand { display:flex; align-items:center; gap:9px; font-weight:500;
                    white-space:nowrap; }
.mm-news .n-brand a { color:inherit; text-decoration:none; }
.mm-news .n-brand a:hover { color:var(--n-accent); }
.mm-news .n-brand-made { font-weight:400; color:#aab7c7; font-size:.85rem; }
.mm-news .n-mark { display:block; height:36px; width:auto; }
.mm-news .n-brand-made .n-mark { height:22px; }
.mm-news .n-foot { display:flex; align-items:center; justify-content:space-between;
                   gap:14px; padding:14px 18px; border-top:1px solid #1e293b;
                   background:#0b1220; color:#e6edf5; font-size:.82rem;
                   flex-wrap:wrap; }
.mm-news .n-foot > span:last-child { color:#aab7c7; }
/* The section links take the whole second row: with the two brand marks, the
   page links and the market name on the first, they never fit beside them
   and were wrapping into a column. */
.mm-news .n-jump { display:flex; gap:4px; flex:1 1 100%; order:10; flex-wrap:wrap; }
.mm-news .n-jump a { border-radius:7px; padding:6px 10px; color:#aab7c7;
                     text-decoration:none; font-size:.82rem; }
.mm-news .n-jump a:hover { background:#1e293b; color:#fff; }
.mm-news .n-market { color:#aab7c7; white-space:nowrap; font-size:.85rem; }
.mm-news .n-jump-page { border:1px solid #334155; }
/* Page links and the feed: never hidden, whatever the width. */
.mm-news .n-pages { display:flex; align-items:center; gap:6px; margin-left:auto; }
.mm-news .n-pages a { border-radius:7px; padding:6px 10px; color:#aab7c7;
                      border:1px solid #334155; font-size:.82rem; white-space:nowrap; }
.mm-news .n-pages a:hover { background:#1e293b; color:#fff; }
/* The news river: a time, a source, a headline, and the other outlets. */
.mm-news .n-river { padding:24px; }
.mm-news .n-day { font-size:13px; font-weight:500; letter-spacing:.04em;
                  text-transform:uppercase; color:var(--n-muted);
                  border-bottom:2px solid var(--n-text); padding-bottom:6px;
                  margin:22px 0 6px; }
.mm-news .n-item { display:grid; grid-template-columns:48px minmax(0,1fr);
                   gap:10px; padding:4px 0; border-bottom:1px solid var(--n-line);
                   font-size:13.5px; line-height:1.4; }
.mm-news .n-item > div { min-width:0; }
.mm-news .n-item .n-src, .mm-news .n-item a.n-head, .mm-news .n-item .n-kind
  { display:inline; }
.mm-news .n-item time { color:var(--n-muted); font-variant-numeric:tabular-nums;
                        font-size:12.5px; padding-top:2px; }
.mm-news .n-item .n-src { color:var(--n-muted); }
.mm-news .n-item .n-src::after { content:":"; }
.mm-news .n-item a.n-head { color:var(--n-text); text-decoration:none; font-weight:500; }
.mm-news .n-item a.n-head:hover { color:var(--n-accent); text-decoration:underline; }
.mm-news .n-item .n-more { margin-top:2px; font-size:12.5px; color:var(--n-muted); }
.mm-news .n-item .n-more a { color:var(--n-muted); }
.mm-news .n-item .n-more a:hover { color:var(--n-accent); }
.mm-news .n-kind { font-size:10.5px; padding:0 5px; border-radius:4px;
                   background:var(--n-accent-soft); color:var(--n-accent);
                   margin-left:6px; white-space:nowrap; }
.mm-news .n-main { padding:24px; }
.mm-news .n-head { display:flex; align-items:flex-end; justify-content:space-between;
                   gap:20px; margin-bottom:18px; flex-wrap:wrap; }
.mm-news .n-kicker { color:var(--n-accent); font-size:.72rem; text-transform:uppercase;
                     letter-spacing:.08em; margin-bottom:5px; }
.mm-news h1 { font-size:clamp(23px,3vw,34px); font-weight:500;
              letter-spacing:-.025em; margin:0; }
.mm-news .n-sub { color:var(--n-muted); margin:7px 0 0; max-width:680px; }
.mm-news .n-period { color:var(--n-muted); font-size:.82rem; white-space:nowrap; }
.mm-news .n-summary { padding:18px 20px; background:var(--n-panel);
                      border:1px solid var(--n-line); border-radius:10px;
                      margin-bottom:14px; }
.mm-news .n-summary h2 { font-size:17px; font-weight:500; margin:0; }
.mm-news .n-summary p { margin:8px 0 0; color:var(--n-muted); max-width:940px; }
.mm-news .n-metrics { display:grid; grid-template-columns:repeat(4,minmax(0,1fr));
                      gap:10px; margin-bottom:22px; }
.mm-news .n-metric { min-width:0; padding:15px; background:var(--n-panel);
                     border:1px solid var(--n-line); border-radius:9px; }
.mm-news .n-metric-top { display:flex; justify-content:space-between; gap:8px;
                         color:var(--n-muted); font-size:12px; }
.mm-news .n-metric-value { margin-top:8px; font-size:24px; font-weight:500;
                           letter-spacing:-.02em; font-variant-numeric:tabular-nums; }
.mm-news .n-delta { color:var(--n-muted); font-size:12px; margin-top:4px; }
.mm-news .n-spark { width:100%; height:28px; margin-top:9px; display:block; }
.mm-news .n-spark path { fill:none; stroke:var(--n-accent); stroke-width:2; }
.mm-news .n-spark .base { stroke:var(--n-line); stroke-width:1; }
.mm-news .n-nospark { margin-top:9px; font-size:11px; color:var(--n-muted);
                      min-height:28px; display:flex; align-items:center; }
.mm-news .n-grid { display:grid; grid-template-columns:minmax(0,1.75fr) minmax(240px,.72fr);
                   gap:22px; align-items:start; }
.mm-news .n-sec-head { display:flex; align-items:center; justify-content:space-between;
                       gap:12px; padding-bottom:10px; border-bottom:2px solid var(--n-text); }
.mm-news .n-sec-head h2 { font-size:17px; font-weight:500; margin:0; }
.mm-news .n-updated { color:var(--n-muted); font-size:12px; }
.mm-news .n-filters { display:flex; flex-wrap:wrap; gap:4px; padding:10px 0 5px; }
.mm-news .n-filter { font-size:12px; padding:5px 8px; border:0; border-radius:7px;
                     background:transparent; color:var(--n-muted); cursor:pointer;
                     font-family:inherit; }
.mm-news .n-filter[aria-pressed="true"] { background:var(--n-accent-soft);
                                          color:var(--n-accent); }
.mm-news .n-story { padding:16px 0; border-bottom:1px solid var(--n-line); }
.mm-news .n-story:last-child { border-bottom:0; }
.mm-news .n-story-tag { color:var(--story,var(--n-accent)); font-size:11px;
                        text-transform:uppercase; letter-spacing:.07em;
                        margin-bottom:5px; }
.mm-news .n-story h3 { font-size:18px; line-height:1.28; font-weight:500; margin:0; }
.mm-news .n-story-sum { color:var(--n-muted); margin:6px 0 0; line-height:1.45; }
.mm-news .n-byline { display:flex; flex-wrap:wrap; gap:5px; margin-top:8px;
                     color:var(--n-muted); font-size:12px; }
.mm-news .n-why { margin-top:6px; color:var(--n-muted); font-size:11.5px;
                  font-style:italic; }
.mm-news .n-support { margin-top:9px; color:var(--n-muted); font-size:12px;
                      line-height:1.55; }
.mm-news .n-support strong { color:var(--n-text); font-weight:500; }
.mm-news .n-support a { color:var(--n-muted); }
.mm-news .n-support a:hover { color:var(--n-accent); }
.mm-news .n-aside { display:grid; gap:18px; }
.mm-news .n-card { background:var(--n-panel); border:1px solid var(--n-line);
                   border-radius:9px; padding:15px; }
.mm-news .n-card-title { display:flex; align-items:center; justify-content:space-between;
                         border-bottom:1px solid var(--n-line); padding-bottom:9px;
                         margin-bottom:5px; }
.mm-news .n-card-title h2 { font-size:15px; font-weight:500; margin:0; }
.mm-news .n-row { display:grid; grid-template-columns:24px minmax(0,1fr) auto;
                  gap:8px; align-items:center; padding:10px 0;
                  border-bottom:1px solid var(--n-line); }
.mm-news .n-row:last-child { border-bottom:0; }
.mm-news .n-rank { color:var(--n-muted); font-variant-numeric:tabular-nums; }
.mm-news .n-row-val { font-weight:500; white-space:nowrap;
                      font-variant-numeric:tabular-nums; }
.mm-news .n-row-label { font-size:12px; color:var(--n-muted); margin-top:2px; }
.mm-news .n-note { color:var(--n-muted); font-size:11px; margin-top:16px; }
/* Period selector, view switch and the RSS link. */
.mm-news .n-periods { display:flex; gap:4px; align-items:center; }
.mm-news .n-periods { justify-content:flex-end; margin-bottom:6px; }
.mm-news .n-periods a { font-size:13px; padding:6px 11px; border-radius:8px;
                        color:var(--n-text); text-decoration:none;
                        border:1px solid var(--n-line); background:#fff;
                        white-space:nowrap; }
.mm-news .n-periods a:hover { border-color:var(--n-accent);
                              color:var(--n-accent); }
.mm-news .n-periods a[aria-current="page"] { background:var(--n-accent);
                                             border-color:var(--n-accent);
                                             color:#fff; }
.mm-news .n-sec-actions { display:flex; align-items:center; gap:10px;
                          flex-wrap:wrap; }
/* Sized and coloured like controls. At 12px muted-on-white these were present
   in the markup and invisible on the page, which is the same as absent. */
.mm-news .n-views { display:flex; border:1px solid var(--n-line);
                    border-radius:8px; overflow:hidden; background:#fff; }
.mm-news .n-views button { font-size:13px; padding:7px 13px; border:0;
                           background:transparent; color:var(--n-text);
                           cursor:pointer; font-family:inherit; font-weight:500;
                           white-space:nowrap; }
.mm-news .n-views button + button { border-left:1px solid var(--n-line); }
.mm-news .n-views button:hover { background:var(--n-accent-soft); }
.mm-news .n-views button[aria-pressed="true"] { background:var(--n-accent);
                                                color:#fff; }
.mm-news .n-rss { display:inline-flex; align-items:center; gap:6px;
                  font-size:13px; font-weight:500; color:var(--n-text);
                  text-decoration:none; border:1px solid var(--n-line);
                  border-radius:8px; padding:7px 12px; background:#fff; }
.mm-news .n-rss svg { width:13px; height:13px; }
.mm-news .n-rss:hover { color:var(--n-accent); border-color:var(--n-accent); }
/* Headlines and River strip the page back without reordering it, so a reader
   scanning for one item is looking at the same list in the same order. */
.mm-news[data-view="headlines"] .n-story-sum,
.mm-news[data-view="headlines"] .n-support,
.mm-news[data-view="headlines"] .n-why,
.mm-news[data-view="river"] .n-story-sum,
.mm-news[data-view="river"] .n-support,
.mm-news[data-view="river"] .n-why { display:none; }
.mm-news[data-view="headlines"] .n-story { padding:9px 0; }
.mm-news[data-view="headlines"] .n-story h3 { font-size:15px; }
.mm-news[data-view="headlines"] .n-story-tag { margin-bottom:3px; }
.mm-news[data-view="headlines"] .n-byline { margin-top:4px; }
.mm-news[data-view="river"] .n-story { padding:11px 0; }
.mm-news[data-view="river"] .n-story h3 { font-size:15px; }
.mm-news[data-view="river"] .n-story-tag { display:none; }
/* Social highlights: a quote, not a row. */
.mm-news .n-social { padding:11px 0; border-bottom:1px solid var(--n-line); }
.mm-news .n-social:last-of-type { border-bottom:0; }
.mm-news .n-social-meta { color:var(--n-muted); font-size:11.5px; }
.mm-news .n-quote { margin:5px 0 0; line-height:1.45; font-size:13px; }
.mm-news .n-quote a { color:inherit; text-decoration:none; }
.mm-news .n-quote a:hover { text-decoration:underline; }
/* The drawers holding the working behind the page. Outside .mm-news, because
   they wrap the report's own sections and inherit that styling. */
.mm-drawer { max-width:1180px; margin:0 auto 10px; border:1px solid #e5e7eb;
             border-radius:10px; background:#fff; }
.mm-drawer > summary { list-style:none; cursor:pointer; padding:15px 20px;
                       display:flex; flex-direction:column; gap:3px; }
.mm-drawer > summary::-webkit-details-marker { display:none; }
.mm-drawer > summary::after { content:"Show"; position:absolute; right:24px;
                              font-size:12px; color:#6b7280; }
.mm-drawer[open] > summary::after { content:"Hide"; }
.mm-drawer > summary { position:relative; }
.mm-drawer > summary:hover .mm-drawer-t { color:#2563eb; }
.mm-drawer-t { font-size:15px; font-weight:500; color:#111827; }
.mm-drawer-b { font-size:12.5px; color:#6b7280; max-width:70ch; }
.mm-drawer-body { padding:0 8px 8px; }
@media print { .mm-drawer > summary::after { content:""; } }
.mm-news .n-empty { color:var(--n-muted); font-size:13px; padding:14px 0; }
@media (max-width:850px) {
  .mm-news .n-jump { display:none; }
  .mm-news .n-metrics { grid-template-columns:repeat(2,minmax(0,1fr)); }
  .mm-news .n-grid { grid-template-columns:1fr; }
}
@media (max-width:560px) {
  .mm-news .n-main { padding:16px; }
  .mm-news .n-metrics { grid-template-columns:1fr; }
  .mm-news .n-story h3 { font-size:16px; }
}
@media print {
  .mm-news .n-filters, .mm-news .n-jump { display:none; }
  .mm-news { border-color:#ccc; }
}
/* The metric strip reused inside a drawer: the cards without the shell. */
.mm-news.n-plain { border:0; background:transparent; margin:0 0 .6rem;
                   border-radius:0; overflow:visible; }
.mm-news.n-plain .n-metrics { margin-bottom:0; }
/* The findings-first lead. */
.mm-news .n-block { margin:0 0 26px; }
.mm-news .n-findings { list-style:none; margin:0; padding:0; counter-reset:f; }
.mm-news .n-finding { padding:14px 0 14px 34px; border-bottom:1px solid var(--n-line);
                      position:relative; counter-increment:f; }
.mm-news .n-finding::before { content:counter(f); position:absolute; left:0; top:15px;
                              width:24px; height:24px; border-radius:50%;
                              background:var(--n-accent); color:#fff; font-size:12px;
                              display:grid; place-items:center; }
.mm-news .n-finding:last-child { border-bottom:0; }
.mm-news .n-finding h3 { font-size:17px; font-weight:500; margin:0 0 4px; line-height:1.3; }
.mm-news .n-finding p { margin:0; line-height:1.5; }
.mm-news .n-evidence { margin:6px 0 0; padding-left:18px; color:var(--n-muted);
                       font-size:12.5px; line-height:1.5; }
.mm-news .n-cites { margin-top:6px; font-size:12px; color:var(--n-muted); }
.mm-news .n-cites a { color:var(--n-accent); }
.mm-news .n-coverage { margin-top:6px; font-size:11.5px; color:#92400e;
                       background:#fff8e6; border:1px solid #fde68a; border-radius:5px;
                       padding:3px 7px; display:inline-block; }
.mm-news .n-tablewrap { overflow-x:auto; }
.mm-news .n-moved td { font-size:13px; }
.mm-news .n-moved a { color:var(--n-text); text-decoration:none; }
.mm-news .n-moved a:hover { color:var(--n-accent); }
.mm-news .n-why-cell { color:var(--n-muted); font-size:12.5px; max-width:34ch; }
.mm-news .n-more { margin-top:10px; }
.mm-news .n-more > summary { font-size:13px; color:var(--n-accent); cursor:pointer; }
.mm-news .n-synth { display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr));
                    gap:14px; }
.mm-news .n-synth-item { background:var(--n-panel); border:1px solid var(--n-line);
                         border-radius:9px; padding:14px 16px; }
.mm-news .n-synth-item h3 { font-size:14px; font-weight:500; margin:0 0 6px; }
.mm-news .n-synth-item p { margin:0; font-size:13.5px; line-height:1.5; }
.mm-news .n-state { display:grid; grid-template-columns:12px 40px minmax(0,1fr); gap:8px;
                    align-items:center; padding:8px 0; border-bottom:1px solid var(--n-line);
                    font-size:13px; }
.mm-news .n-state:last-of-type { border-bottom:0; }
.mm-news .n-state .dot { width:9px; height:9px; border-radius:50%; }
.mm-news .n-distil { font-size:13px; color:var(--n-muted); margin:8px 0 4px; }
.mm-news .n-why { font-style:normal; color:var(--n-text); font-size:12.5px; }
"""


EXTRA_CSS = """

/* Shared view: most of the evidence is blurred behind a trial request. */
.mm-teaser { position: relative; margin: .4rem 0 1rem; }
.mm-teaser-body { filter: blur(6px); user-select: none; pointer-events: none;
                  opacity: .75; max-height: 560px; overflow: hidden; }
.mm-teaser-cta { position: absolute; top: 2.2rem; left: 0; right: 0;
                 display: flex; justify-content: center; }
.mm-teaser-cta > div { background: #fff; border: 1px solid #e5e7eb; border-radius: 10px;
                       padding: 1rem 1.25rem; max-width: 400px; text-align: center;
                       font-size: .9rem; color: #111827;
                       box-shadow: 0 8px 24px rgba(17, 24, 39, .12); }
.mm-btn { display: inline-block; margin-top: .6rem; background: #111827; color: #fff !important;
          border: 0; border-radius: 6px; padding: .5rem .9rem; font-size: .85rem;
          font-weight: 600; cursor: pointer; text-decoration: none !important; }
tr.mm-teaser-row td { filter: blur(5px); user-select: none; pointer-events: none; }
.mm-trial { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px;
            padding: 1.1rem 1.25rem; margin: 1.2rem 0; }
.mm-trial h2 { margin: 0 0 .3rem; font-size: 1.05rem; }
.mm-trial p { margin: 0 0 .7rem; font-size: .9rem; color: #334155; }
.mm-trial form { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
                 gap: .6rem; align-items: end; }
.mm-trial label { display: block; font-size: .72rem; color: #64748b; text-transform: uppercase;
                  letter-spacing: .05em; margin-bottom: .2rem; }
.mm-trial input { width: 100%; box-sizing: border-box; border: 1px solid #cbd5e1;
                  border-radius: 6px; padding: .45rem .55rem; font-size: .88rem; }
.mm-trial .mm-btn { margin-top: 0; }
.mm-trial-msg { grid-column: 1 / -1; font-size: .85rem; color: #0f7a4e; min-height: 1em; }
.mm-trial-msg.err { color: #be123c; }
.mm-stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
            gap: .7rem; margin: .8rem 0 1rem; }
.mm-stat { background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; padding: .7rem .85rem; }
.mm-stat .v { font-size: 1.5rem; font-weight: 700; color: #111827; }
.mm-stat .l { font-size: .72rem; color: #6b7280; text-transform: uppercase; letter-spacing: .05em; }
.mm-stat .h { font-size: .74rem; color: #6b7280; margin-top: .25rem; }
.mm-cover { font-size: .76rem; color: #92400e; background: #fff8e6;
            border: 1px solid #fde68a; border-radius: 5px; padding: .3rem .5rem;
            display: inline-block; margin: 0 0 .6rem; }
.mm-cover.full { color: #065f46; background: #ecfdf5; border-color: #a7f3d0; }
.mm-table { width: 100%; border-collapse: collapse; font-size: .82rem; }
.mm-table th { text-align: left; font-size: .7rem; text-transform: uppercase;
               letter-spacing: .05em; color: #6b7280; padding: .35rem .4rem;
               border-bottom: 1px solid #e5e7eb; }
.mm-table td { padding: .35rem .4rem; border-bottom: 1px solid #f3f4f6; vertical-align: top; }
.mm-num { text-align: right; font-variant-numeric: tabular-nums; }
.mm-kind { display: inline-block; font-size: .68rem; padding: .1rem .4rem;
           border-radius: 4px; background: #ecfdf5; color: #065f46;
           border: 1px solid #a7f3d0; }
.mm-src { font-size: .74rem; color: #6b7280; }
.mm-fold { margin: 10px 0; border-top: 1px solid #e5e7eb; }
.mm-fold > summary { cursor: pointer; padding: 8px 0; font-size: .86rem; color: #334155; }
.mm-fold > summary::marker { color: #94a3b8; }
.mm-fold-body { padding: 0 0 8px; }
svg.mm-chart { display: block; width: 100%; height: auto; }
details summary { cursor: pointer; font-size: .82rem; color: #475569;
                  padding: .3rem 0; }
.mm-reading { font-size: .95rem; margin: .2rem 0 .6rem; display: flex;
             align-items: center; gap: 6px; font-weight: 600; }
.mm-reading .dot { width: 8px; height: 8px; border-radius: 50%; flex: none; }
.mm-reading.pos { color: #0f7a4e; }
.mm-reading.pos .dot { background: #30a46c; }
.mm-reading.neg { color: #be123c; }
.mm-reading.neg .dot { background: #e5484d; }
.mm-reading.neutral { color: #374151; }
.mm-reading.neutral .dot { background: #9ca3af; }
"""


# ---------------------------------------------------------------------------
# Branding: by the Cyberfuturists, made using Aunoo
# ---------------------------------------------------------------------------
#
# The report is emailed and opened offline, so the marks are embedded as data
# URIs rather than linked. The files live under static/report-brand; a
# missing file drops the image and keeps the words.

_BRAND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "static", "report-brand")


@lru_cache(maxsize=4)
def _brand_data_uri(filename: str) -> str:
    path = os.path.join(_BRAND_DIR, filename)
    try:
        with open(path, "rb") as fh:
            payload = base64.b64encode(fh.read()).decode("ascii")
    except OSError:
        return ""
    return f"data:image/png;base64,{payload}"


def _brand_mark(filename: str, alt: str, height: int = 26) -> str:
    uri = _brand_data_uri(filename)
    if not uri:
        return ""
    return (f'<img class="n-mark" src="{uri}" alt="{esc(alt)}" '
            f'height="{height}" loading="lazy">')


def _brand_line() -> str:
    """The byline: who wrote it, and what it was made with."""
    return ('<span class="n-brand">'
            + _brand_mark("cyberfuturists-mark.png", "Cyberfuturists", height=36)
            + '<span>By the <a href="https://cyberfuturists.com/">'
            'Cyberfuturists</a></span></span>'
            '<span class="n-brand n-brand-made">'
            + _brand_mark("aunoo-mark.png", "Aunoo", height=22)
            + '<span>made using <a href="https://aunoo.ai/">Aunoo</a></span>'
            '</span>')


def _stat(label: str, value: str, hint: str = "") -> str:
    return (f'<div class="mm-stat"><div class="l">{esc(label)}</div>'
            f'<div class="v">{esc(value)}</div>'
            + (f'<div class="h">{esc(hint)}</div>' if hint else "")
            + "</div>")


def _signed(value: Optional[float]) -> str:
    if value is None:
        return "—"
    return f"+{value:g}" if value > 0 else f"{value:g}"


def _reading(net: Optional[float], *, subject: str = "Coverage in the latest week"
            ) -> str:
    """A plain-English positive/negative/mixed line with a colored dot.

    A raw signed percentage ("+22%") makes a reader do the sign-reading
    themselves. This says it in words and repeats the call in color, so
    color is never the only signal.
    """
    if net is None:
        return ""
    tone = "pos" if net > 10 else "neg" if net < -10 else "neutral"
    verb = "leaned positive" if tone == "pos" else \
           "leaned negative" if tone == "neg" else "was mixed"
    sign = "+" if net > 0 else ""
    return (f'<p class="mm-reading {tone}"><span class="dot"></span>'
            f'{esc(subject)} {verb} ({sign}{net}%).</p>')


def _stage_label(raw: Optional[str]) -> str:
    """Crunchbase's slug as words: series_a -> Series A."""
    if not raw or raw == "not stated":
        return "not stated"
    words = raw.replace("_", " ").split()
    return " ".join(w.upper() if len(w) == 1 else w.capitalize() for w in words)


def _money(musd: Optional[float]) -> str:
    """A funding total in the unit a reader would actually say out loud.

    $1,038M is technically correct and reads like a spreadsheet cell. Above
    $1,000M this switches to billions, which is how anyone would describe the
    figure in a sentence.
    """
    if musd is None:
        return "—"
    if musd >= 1000:
        return f"${musd / 1000:.3f}B"
    return f"${musd:,.0f}M"


def _fmt_range(start: str, end: str) -> str:
    """An ISO date pair as a reader would write it: '24 July–22 August 2026'.

    ``days=30`` alone leaves the actual boundary to the reader's arithmetic;
    every other report on this platform states the period it covers in
    words, not just as a parameter.
    """
    from datetime import date
    try:
        s, e = date.fromisoformat(start), date.fromisoformat(end)
    except ValueError:
        return f"{start} – {end}"
    if s.year == e.year:
        return f"{s.strftime('%-d %B')}–{e.strftime('%-d %B %Y')}"
    return f"{s.strftime('%-d %B %Y')} – {e.strftime('%-d %B %Y')}"


def _pct_row(label: str, measured: int, total: int) -> str:
    pct = f"{measured / total * 100:.0f}%" if total else "—"
    return (f'<tr><td>{esc(label)}</td>'
            f'<td class="mm-num">{measured} / {total}</td>'
            f'<td class="mm-num">{pct}</td></tr>')


def _coverage(coverage: Optional[Dict[str, Any]]) -> str:
    """The denominator, rendered so it cannot be skipped past.

    Amber when partial, green when complete. A chart in this report without one
    of these is a chart whose author forgot to say what it rests on. The
    ``label`` coming from ``market_analysis._coverage()`` is already a full
    clause ("81 of 83 vendors have a founding year") — no "Based on" prefix
    needed, and stacking one on produced "Based on 81 of 83 vendors have a
    founding year," which does not parse as a sentence.
    """
    if not coverage:
        return ""
    cls = "mm-cover full" if coverage.get("complete") else "mm-cover"
    label = coverage.get("label", "")
    return f'<div class="{cls}">{esc(label[:1].upper() + label[1:] if label else label)}.</div>'



def _coverage_row(a: Dict[str, Any], *, kind: Optional[str] = None) -> str:
    cluster = a.get("cluster")
    extra = (f' <span class="mm-kind">+{cluster["size"] - 1} more like this</span>'
             if cluster and cluster.get("size", 1) > 1 else "")
    badge = f'<span class="mm-kind">{esc(kind)}</span> ' if kind else ""
    headline = a.get("title") or a["uri"]
    return (f'<tr><td>{badge}<a href="{esc(a["uri"])}">'
            f'{esc(headline)}</a>{extra}'
            f'<div class="mm-src">{esc(a.get("news_source") or "")}'
            f' · {esc((a.get("published") or "")[:10])}</div></td></tr>')


# ---------------------------------------------------------------------------
# Charts, hand-drawn as SVG
# ---------------------------------------------------------------------------

# How many vendors the report names in its activity table. Ten by default, the
# same number the shared-link entitlement allows, so a full report and a shared
# one show a list of the same shape.
ACTIVITY_TOP_N = 10


def _activity_row(vendor: Dict[str, Any]) -> str:
    """One vendor's row in the activity table.

    A withheld index prints an em dash, never a zero. The three raw counts sit
    beside it because the index is a rank and the counts are the measurements
    it was computed from; a reader cannot check the first without the others.
    """
    index = vendor.get("activity_index")
    shown = str(index) if index is not None else "&mdash;"
    return ('<tr><td>' + esc(vendor.get("vendor") or "") + '</td>'
            '<td class="mm-num">' + shown + '</td>'
            '<td class="mm-num">' + str(vendor.get("posts") or 0) + '</td>'
            '<td class="mm-num">' + str(vendor.get("jobs") or 0) + '</td>'
            '<td class="mm-num">' + str(vendor.get("earned") or 0)
            + '</td></tr>')


def _bar_chart(rows: List[Dict[str, Any]], *, label_key: str, value_key: str,
               height: int = 180, colour: str = "#475569") -> str:
    """A plain vertical bar chart.

    Written out rather than pulled from a library because the page must render
    with no network access. Forty lines of SVG is cheaper than that constraint
    being violated by a script tag someone adds later.
    """
    rows = [r for r in rows if r.get(value_key) is not None]
    if not rows:
        return '<p class="mm-src">Nothing to plot.</p>'

    width, pad_l, pad_b, pad_t = 720, 34, 42, 10
    peak = max(float(r[value_key]) for r in rows) or 1
    plot_h = height - pad_b - pad_t
    slot = (width - pad_l - 8) / len(rows)
    bar_w = max(3.0, slot * 0.68)

    parts = [f'<svg class="mm-chart" viewBox="0 0 {width} {height}" '
             f'role="img" preserveAspectRatio="xMidYMid meet">']
    # Baseline and one gridline at the top of the scale.
    parts.append(f'<line x1="{pad_l}" y1="{pad_t}" x2="{width - 8}" y2="{pad_t}" '
                 'stroke="#e5e7eb" stroke-width="1"/>')
    parts.append(f'<text x="{pad_l - 6}" y="{pad_t + 4}" text-anchor="end" '
                 f'font-size="10" fill="#9ca3af">{int(peak)}</text>')
    parts.append(f'<line x1="{pad_l}" y1="{pad_t + plot_h}" x2="{width - 8}" '
                 f'y2="{pad_t + plot_h}" stroke="#9ca3af" stroke-width="1"/>')

    for i, row in enumerate(rows):
        value = float(row[value_key])
        bar_h = (value / peak) * plot_h
        x = pad_l + i * slot + (slot - bar_w) / 2
        y = pad_t + plot_h - bar_h
        parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" '
                     f'height="{bar_h:.1f}" fill="{colour}" rx="2"><title>'
                     f'{esc(str(row[label_key]))}: {esc(str(row[value_key]))}'
                     '</title></rect>')
        # Only label every nth category when they would collide, and give
        # a name as many characters as its slot can hold.
        step = max(1, len(rows) // 14)
        width_chars = max(6, int(slot / 5.6))
        if i % step == 0:
            parts.append(
                f'<text x="{pad_l + i * slot + slot / 2:.1f}" '
                f'y="{pad_t + plot_h + 14}" text-anchor="middle" font-size="10" '
                f'fill="#6b7280">{esc(_clip(str(row[label_key]), width_chars))}</text>')
    parts.append("</svg>")
    return "".join(parts)


def _stacked_chart(rows: List[Dict[str, Any]], *, label_key: str,
                   series: List[tuple], height_per_row: int = 20) -> str:
    """Horizontal stacked bars — one row per vendor, one segment per verdict."""
    if not rows:
        return '<p class="mm-src">Nothing to plot.</p>'

    width, pad_l = 720, 150
    row_h = height_per_row
    height = len(rows) * row_h + 24
    peak = max(sum(float(r.get(k) or 0) for k, _, _ in series) for r in rows) or 1
    scale = (width - pad_l - 90) / peak

    parts = [f'<svg class="mm-chart" viewBox="0 0 {width} {height}" role="img" '
             'preserveAspectRatio="xMidYMid meet">']
    for i, row in enumerate(rows):
        y = i * row_h + 4
        parts.append(f'<text x="{pad_l - 6}" y="{y + row_h * 0.68:.1f}" '
                     'text-anchor="end" font-size="11" fill="#374151">'
                     f'{esc(str(row[label_key])[:26])}</text>')
        x = pad_l
        total = 0
        for key, colour, name in series:
            value = float(row.get(key) or 0)
            total += value
            if value <= 0:
                continue
            seg = value * scale
            parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{seg:.1f}" '
                         f'height="{row_h - 6}" fill="{colour}"><title>'
                         f'{esc(name)}: {int(value)}</title></rect>')
            x += seg
        parts.append(f'<text x="{x + 6:.1f}" y="{y + row_h * 0.68:.1f}" '
                     f'font-size="10" fill="#6b7280">{int(total)}</text>')
    parts.append("</svg>")
    return "".join(parts)


def _line_chart(rows: List[Dict[str, Any]], *, x_key: str,
                series: List[tuple], height: int = 200) -> str:
    """One or more lines over an ordered x-axis.

    A None value breaks the line rather than being drawn as zero — used for
    weeks below a coverage or scored-count floor, where "no data" and "zero"
    read as the same point unless the gap is real.
    """
    if not rows:
        return '<p class="mm-src">Nothing to plot.</p>'
    all_vals = [float(r[key]) for key, _, _ in series for r in rows
                if r.get(key) is not None]
    if not all_vals:
        return '<p class="mm-src">Nothing to plot.</p>'

    width, pad_l, pad_r, pad_t, pad_b = 720, 40, 12, 22, 24
    plot_w, plot_h = width - pad_l - pad_r, height - pad_t - pad_b
    n = len(rows)
    step = plot_w / max(1, n - 1)
    lo, hi = min(0.0, min(all_vals)), max(0.0, max(all_vals))
    span = (hi - lo) or 1.0

    def _x(i: int) -> float:
        return pad_l + i * step

    def _y(v: float) -> float:
        return pad_t + plot_h - (v - lo) / span * plot_h

    parts = [f'<svg class="mm-chart" viewBox="0 0 {width} {height}" '
             'role="img" preserveAspectRatio="xMidYMid meet">']
    zero_y = _y(0)
    parts.append(f'<line x1="{pad_l}" y1="{zero_y:.1f}" x2="{width - pad_r}" '
                f'y2="{zero_y:.1f}" stroke="#e5e7eb" stroke-width="1"/>')
    parts.append(f'<text x="{pad_l - 6}" y="{pad_t + 4}" text-anchor="end" '
                f'font-size="10" fill="#9ca3af">{hi:.0f}</text>')
    parts.append(f'<text x="{pad_l - 6}" y="{pad_t + plot_h}" text-anchor="end" '
                f'font-size="10" fill="#9ca3af">{lo:.0f}</text>')

    for key, colour, name in series:
        segments: List[List[tuple]] = []
        current: List[tuple] = []
        for i, row in enumerate(rows):
            value = row.get(key)
            if value is None:
                if current:
                    segments.append(current)
                    current = []
                continue
            current.append((_x(i), _y(float(value))))
        if current:
            segments.append(current)
        for seg in segments:
            if len(seg) == 1:
                x, y = seg[0]
                parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.5" '
                            f'fill="{colour}"/>')
                continue
            d = "M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in seg)
            parts.append(f'<path d="{d}" fill="none" stroke="{colour}" '
                        'stroke-width="2"/>')

    label_idx = sorted({0, n // 2, n - 1})
    for i in label_idx:
        parts.append(f'<text x="{_x(i):.1f}" y="{height - 6}" '
                    'text-anchor="middle" font-size="10" fill="#6b7280">'
                    f'{esc(str(rows[i][x_key])[:10])}</text>')

    if len(series) > 1:
        lx = pad_l
        for key, colour, name in series:
            parts.append(f'<rect x="{lx}" y="2" width="8" height="8" '
                        f'fill="{colour}"/>')
            parts.append(f'<text x="{lx + 11}" y="10" font-size="9" '
                        f'fill="#374151">{esc(name)}</text>')
            lx += 20 + len(name) * 5.2
    parts.append("</svg>")
    return "".join(parts)


def _day(value: Any) -> str:
    """A date the way a person writes one, falling back to what we were given."""
    raw = str(value)[:10]
    try:
        return datetime.strptime(raw, "%Y-%m-%d").strftime("%-d %b %Y")
    except (ValueError, TypeError):
        return raw


_TIER_ORDER = ("executors", "innovators", "established", "emerging")
_TIER_COLOUR = {"executors": "#0f766e", "innovators": "#b45309",
                "established": "#1d4ed8", "emerging": "#6b7280"}


def _horizon_svg(rated: List[Dict[str, Any]], allowed: Optional[set],
                 cuts: Dict[str, Any]) -> str:
    """Vendors on a semicircle. Distance from the base is the overall
    position (the mean of scale and momentum); the angle is the balance
    between them — scale-heavy to the left, momentum-heavy to the right,
    balanced up the middle. The concentric arcs are the horizons. Names only
    where the viewer may see them; the dots give nothing away."""
    import math
    w, h = 720, 452
    cx, cy, radius = w / 2, h - 72, 330
    # The angle is the balance between the axes, scaled to the rated set's
    # own spread so the horizon is used whatever the market looks like: the
    # most lopsided vendor sits 80 degrees off the vertical.
    widest = max([abs(float(r["scale"]) - float(r["momentum"])) for r in rated] + [20.0])
    per_point = 80.0 / widest
    def place(r: Dict[str, Any]):
        pos = (float(r["scale"]) + float(r["momentum"])) / 2
        theta = math.radians(90 + (float(r["scale"]) - float(r["momentum"])) * per_point)
        d = radius * pos / 100
        return cx + d * math.cos(theta), cy - d * math.sin(theta)
    def arc(frac: float) -> str:
        d = radius * frac
        return f'M {cx - d:.1f} {cy:.1f} A {d:.1f} {d:.1f} 0 0 1 {cx + d:.1f} {cy:.1f}'
    parts = [f'<svg viewBox="0 0 {w} {h}" width="100%" style="max-width:{w}px" role="img" '
             'aria-label="Market Horizon: position and balance">',
             '<defs><marker id="mm-hz-arrow" viewBox="0 0 6 6" refX="5" refY="3" '
             'markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
             '<path d="M0,0 L6,3 L0,6 Z" fill="#94a3b8"/></marker></defs>',
             f'<path d="{arc(1.0)} Z" fill="#f8fafc" stroke="#e2e8f0"/>']
    for frac in (0.25, 0.5, 0.75):
        parts.append(f'<path d="{arc(frac)}" fill="none" stroke="#cbd5e1" stroke-dasharray="4 4"/>')
    parts += [f'<text x="{cx:.0f}" y="{cy - radius - 12:.0f}" text-anchor="middle" font-size="11" fill="#64748b">Executing — growing, and already large</text>',
              f'<text x="{cx - radius + 4:.0f}" y="{cy - 60:.0f}" font-size="11" fill="#64748b">Establishing</text>',
              f'<text x="{cx + radius - 4:.0f}" y="{cy - 60:.0f}" text-anchor="end" font-size="11" fill="#64748b">Accelerating</text>',
              f'<text x="{cx:.0f}" y="{cy + 16:.0f}" text-anchor="middle" font-size="11" fill="#64748b">Emerging — small, and not yet moving fast</text>',
              f'<text x="{cx - radius:.0f}" y="{cy + 30:.0f}" font-size="10" fill="#94a3b8">← scale-heavy</text>',
              f'<text x="{cx + radius:.0f}" y="{cy + 30:.0f}" text-anchor="end" font-size="10" fill="#94a3b8">momentum-heavy →</text>',
              # The legend for the three markers. Each is a ring style, so a
              # dot can carry all three without a second glyph.
              f'<circle cx="{cx - 250:.0f}" cy="{cy + 44:.0f}" r="6" fill="none" stroke="#0f172a" stroke-width="1.2" stroke-dasharray="2 2"/>',
              f'<text x="{cx - 240:.0f}" y="{cy + 48:.0f}" font-size="10" fill="#64748b">innovating — top third by product work</text>',
              f'<circle cx="{cx - 30:.0f}" cy="{cy + 44:.0f}" r="6" fill="none" stroke="#b45309" stroke-width="1.6" stroke-dasharray="1 2.2"/>',
              f'<text x="{cx - 20:.0f}" y="{cy + 48:.0f}" font-size="10" fill="#64748b">hiring — top third by open roles per head</text>',
              f'<circle cx="{cx + 190:.0f}" cy="{cy + 44:.0f}" r="6" fill="none" stroke="#1d4ed8" stroke-width="1"/>',
              f'<text x="{cx + 200:.0f}" y="{cy + 48:.0f}" font-size="10" fill="#64748b">funded — a round in the last year</text>']
    # A large move since the previous map is a trail from where the vendor
    # was, drawn under the dots so it never hides one.
    trails = [r for r in rated if r.get("big_move") and r.get("previous")]
    for r in trails:
        px, py = place(r["previous"])
        x, y = place(r)
        parts.append(f'<line x1="{px:.1f}" y1="{py:.1f}" x2="{x:.1f}" y2="{y:.1f}" '
                     'stroke="#94a3b8" stroke-width="1.2" marker-end="url(#mm-hz-arrow)"/>')
        parts.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="3" fill="none" stroke="#94a3b8"/>')
    if trails:
        parts.append(f'<line x1="{cx - 250:.0f}" y1="{cy + 58:.0f}" x2="{cx - 232:.0f}" y2="{cy + 58:.0f}" '
                     'stroke="#94a3b8" stroke-width="1.2" marker-end="url(#mm-hz-arrow)"/>')
        parts.append(f'<text x="{cx - 226:.0f}" y="{cy + 61:.0f}" font-size="10" fill="#64748b">'
                     'trail — moved 10 or more points on an axis since the previous map</text>')
    dots = [(r, *place(r)) for r in sorted(rated, key=lambda r: -(r["scale"] + r["momentum"]))]
    # Labels must not sit on another label or on any dot. Each label tries
    # right, left, above, below, then right at increasing drops, and takes
    # the first clear spot. Placed labels are boxes (x, y_top, w, h).
    def ring(r: Dict[str, Any]) -> float:
        return 14.0 if r.get("funded") else 11.5 if r.get("hiring") else 9.0 if r.get("innovating") else 6.0
    boxes: List[tuple] = [(x - ring(r), y - ring(r), 2 * ring(r), 2 * ring(r)) for r, x, y in dots]
    def clear(bx: float, by: float, bw: float, bh: float) -> bool:
        return not any(bx < ox + ow and ox < bx + bw and by < oy + oh and oy < by + bh
                       for ox, oy, ow, oh in boxes)
    for r, x, y in dots:
        colour = _TIER_COLOUR.get(r["tier"], "#6b7280")
        shown = allowed is None or r["vendor"] in allowed
        # The hover title names the vendor, so it is withheld with the label.
        title = (f'<title>{esc(r["vendor"])}: scale {r["scale"]}, momentum {r["momentum"]}</title>'
                 if shown else '')
        if r.get("innovating"):
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="8.5" fill="none" '
                         'stroke="#0f172a" stroke-width="1.2" stroke-dasharray="2 2"/>')
        if r.get("hiring"):
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="11" fill="none" '
                         'stroke="#b45309" stroke-width="1.6" stroke-dasharray="1 2.2"/>')
        if r.get("funded"):
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="13.5" fill="none" '
                         'stroke="#1d4ed8" stroke-width="1"/>')
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="{colour}" fill-opacity=".85">'
                     f'{title}</circle>')
        if not shown:
            continue
        width, height = 5.4 * len(r["vendor"]) + 2, 11
        g = ring(r) + 2
        candidates = [(x + g, y - 5, "start"), (x - g - width, y - 5, "end"),
                      (x - width / 2, y - g - 12, "middle"), (x - width / 2, y + g + 2, "middle")]
        for k in range(1, 6):
            candidates += [(x + g, y - 5 + 12 * k, "start"), (x - g - width, y - 5 + 12 * k, "end"),
                           (x + g, y - 5 - 12 * k, "start"), (x - g - width, y - 5 - 12 * k, "end")]
        for bx, by, anchor in candidates:
            if clear(bx, by, width, height):
                break
        boxes.append((bx, by, width, height))
        tx = bx if anchor == "start" else bx + width if anchor == "end" else bx + width / 2
        parts.append(f'<text x="{tx:.1f}" y="{by + 9:.1f}" text-anchor="{anchor}" '
                     f'font-size="10" fill="#0f172a">{esc(r["vendor"])}</text>')
    parts.append("</svg>")
    return "".join(parts)


_HORIZON_SLOT = "<!--mm-horizon-slot-->"


def _horizon_section(horizon: Dict[str, Any], allowed: Optional[set], *,
                     public_names: bool = False) -> str:
    """The map, the tiers, the not-rated list and the weights, in that order.

    ``public_names`` labels every rated vendor and lists every tier in full
    whatever the entitlement; the not-rated names still follow ``allowed``.
    """
    cfg = horizon.get("config") or {}
    rated = horizon.get("rated") or []
    not_rated = horizon.get("not_rated") or []
    names_allowed = None if public_names else allowed
    # The drawer's own title already says "Market Horizon"; no second heading.
    out = ['<section class="section">']
    out.append(f'<p class="mm-src">{esc(horizon.get("what_it_is_not") or "")} '
               f'Computed {esc((horizon.get("computed_at") or "")[:10])} over the '
               f'last {horizon.get("days")} days.</p>')
    out.append(_horizon_svg(rated, names_allowed, cfg.get("tiers") or {}))
    acquired = horizon.get("acquired") or []
    innovating = [r for r in rated if r.get("innovating")]
    full_view = allowed is None

    def fold(summary: str, inner: str) -> str:
        # The map is the page's opening picture; the lists behind it open on
        # request, so the eye lands on the horizon and not on a wall of names.
        return (f'<details class="mm-fold"><summary>{summary}</summary>'
                f'<div class="mm-fold-body">{inner}</div></details>')

    tiers_html = []
    for tier in _TIER_ORDER:
        info = (horizon.get("tiers") or {}).get(tier) or {}
        rows = [r for r in rated if r["tier"] == tier]
        if not rows:
            continue
        shown = [r for r in rows if names_allowed is None or r["vendor"] in names_allowed]
        hidden = len(rows) - len(shown)
        names = []
        for r in shown:
            name = esc(r["vendor"])
            if r.get("innovating"):
                name += ' <span class="mm-src" title="innovating">◌</span>'
            if r.get("hiring"):
                name += ' <span class="mm-src" title="hiring">⚒</span>'
            if r.get("funded"):
                name += ' <span class="mm-src" title="funded">$</span>'
            if r.get("moved") and (r.get("previous") or {}).get("tier") != tier:
                name += f' <span class="mm-src">(was {esc((r["previous"] or {}).get("tier", ""))})</span>'
            names.append(name)
        if hidden:
            names.append(f'{hidden} vendor{"s" if hidden > 1 else ""} not shown in this view')
        tiers_html.append(f'<h3>{esc(info.get("label") or tier.capitalize())} '
                          f'<span class="mm-src">({len(rows)}) — {esc(info.get("means") or "")}</span></h3>')
        tiers_html.append(f'<p>{", ".join(names)}</p>')
    if innovating:
        inames = [esc(r["vendor"]) for r in innovating
                  if names_allowed is None or r["vendor"] in names_allowed]
        ihidden = len(innovating) - len(inames)
        if ihidden:
            inames.append(f'{ihidden} vendor{"s" if ihidden > 1 else ""} not shown in this view')
        tiers_html.append(f'<h3>Innovating <span class="mm-src">({len(innovating)}) — top third by '
                          'launches, corroborated launches, research posts and engineering '
                          'hiring; a marker across every tier</span></h3>')
        tiers_html.append(f'<p>{", ".join(inames)}</p>')
    markers = horizon.get("markers") or {}
    hiring = markers.get("hiring") or []
    if hiring:
        hnames = [f'{esc(h["vendor"])} <span class="mm-src">({h["open_roles"]} open roles, '
                  f'{float(h["per_100"]):.0f} per 100 staff)</span>'
                  for h in hiring if names_allowed is None or h["vendor"] in names_allowed]
        hhidden = len(hiring) - len(hnames)
        if hhidden:
            hnames.append(f'{hhidden} vendor{"s" if hhidden > 1 else ""} not shown in this view')
        tiers_html.append(f'<h3>Hiring <span class="mm-src">({len(hiring)}) — top third by open '
                          f'roles per 100 staff, with at least {markers.get("min_open_roles", 3)} '
                          'roles open; a marker across every tier</span></h3>')
        tiers_html.append(f'<p>{", ".join(hnames)}</p>')
    funded = markers.get("funded") or []
    if funded:
        fnames = []
        for f in funded:
            if names_allowed is not None and f["vendor"] not in names_allowed:
                continue
            what = f.get("round") or "round not stated"
            fnames.append(f'{esc(f["vendor"])} <span class="mm-src">({esc(what)}, '
                          f'{esc((f.get("date") or "")[:7])})</span>')
        fhidden = len(funded) - len(fnames)
        if fhidden:
            fnames.append(f'{fhidden} vendor{"s" if fhidden > 1 else ""} not shown in this view')
        tiers_html.append(f'<h3>Funded <span class="mm-src">({len(funded)}) — a round dated inside '
                          f'the last {markers.get("funded_days", 365)} days, from the vendor\'s own '
                          'post, a matched news event or the Crunchbase news list</span></h3>')
        tiers_html.append(f'<p>{", ".join(fnames)}</p>')
    moves = horizon.get("moves") or []
    if moves:
        mnames = []
        for m in moves:
            if names_allowed is not None and m["vendor"] not in names_allowed:
                continue
            bits = [f'{"+" if m[a] > 0 else ""}{m[a]:g} {a}' for a in ("scale", "momentum")
                    if abs(m[a]) >= 1]
            tier_bit = (f'; {esc((horizon.get("tiers") or {}).get(m["previous_tier"], {}).get("label", m["previous_tier"]))}'
                        f' → {esc((horizon.get("tiers") or {}).get(m["tier"], {}).get("label", m["tier"]))}'
                        if m["previous_tier"] != m["tier"] else "")
            mnames.append(f'{esc(m["vendor"])} <span class="mm-src">({", ".join(bits)}{tier_bit})</span>')
        mhidden = len(moves) - len(mnames)
        if mhidden:
            mnames.append(f'{mhidden} vendor{"s" if mhidden > 1 else ""} not shown in this view')
        tiers_html.append(f'<h3>Moved <span class="mm-src">({len(moves)}) — {horizon.get("large_shift", 10):g} or '
                          f'more points on an axis since the map of '
                          f'{esc((horizon.get("previous_at") or "")[:10])}</span></h3>')
        tiers_html.append(f'<p>{", ".join(mnames)}</p>')
    if acquired:
        tiers_html.append(f'<h3>Acquired <span class="mm-src">({len(acquired)}) — listed, not placed</span></h3>')
        tiers_html.append('<p>' + "; ".join(
            esc(a["vendor"]) + (f' — by {esc(a["acquired_by"])}' if a.get("acquired_by") else "")
            + (f', {esc(a["status_date"])}' if a.get("status_date") else "")
            for a in acquired if names_allowed is None or a["vendor"] in names_allowed) + '</p>')
    tier_summary = ", ".join(
        f'{(horizon.get("tiers") or {}).get(t, {}).get("label", t)} {sum(1 for r in rated if r["tier"] == t)}'
        for t in _TIER_ORDER)
    out.append(fold(f"Who is where — {esc(tier_summary)}"
                    + (f", innovating {len(innovating)}" if innovating else "")
                    + (f", hiring {len(hiring)}" if hiring else "")
                    + (f", funded {len(funded)}" if funded else "")
                    + (f", moved {len(moves)}" if moves else "")
                    + (f", acquired {len(acquired)}" if acquired else ""),
                    "".join(tiers_html)))

    if full_view:
        noted = [r for r in rated if r.get("analyst_note") or r.get("multipliers")]
        noted += [a for a in acquired if a.get("note")]
        if noted:
            lines = []
            for r in noted:
                bits = []
                if r.get("multipliers"):
                    bits.append("weights " + ", ".join(f"{k} ×{v:g}" for k, v in r["multipliers"].items()))
                if r.get("analyst_note") or r.get("note"):
                    bits.append(esc(r.get("analyst_note") or r.get("note")))
                lines.append(f'<li><strong>{esc(r["vendor"])}</strong>: ' + "; ".join(bits) + '</li>')
            out.append(fold(f"Analyst notes and adjustments ({len(noted)})",
                            '<ul class="mm-src">' + "".join(lines) + '</ul>'))

    # What is missing is the operator's to-do, not the reader's business:
    # the not-rated list is in the full view only.
    if not_rated and full_view:
        by_reason: Dict[str, int] = {}
        for nr in not_rated:
            for g in nr.get("missing") or []:
                by_reason[g["label"]] = by_reason.get(g["label"], 0) + 1
        reasons = "; ".join(f"{n} lack {esc(label.lower())}" for label, n in
                            sorted(by_reason.items(), key=lambda kv: -kv[1]))
        inner = (f'<p class="mm-src">A vendor is rated only when every input was '
                 f'measured. {reasons}.</p>')
        if True:
            inner += '<p class="mm-src">' + "; ".join(
                f'{esc(nr["vendor"])}: ' + ", ".join(esc(g["label"].lower()) for g in nr["missing"])
                for nr in not_rated) + '</p>'
        out.append(fold(f"Not rated ({len(not_rated)}) — what each one lacks", inner))

    inputs = cfg.get("inputs") or {}
    ordered = sorted(inputs.items(), key=lambda kv: (0 if kv[1].get("axis") == "scale" else 1,
                                                     -float(kv[1].get("weight") or 0)))
    weights = ('<table class="mm-table"><thead><tr><th>Input</th>'
               '<th>Axis</th><th class="mm-num">Weight</th></tr></thead><tbody>'
               + "".join(f'<tr><td>{esc(v.get("label") or k)}'
                         + (f' <span class="mm-src">{esc(v["note"])}</span>' if v.get("note") else "")
                         + (' <span class="mm-src">(optional)</span>' if v.get("optional") else "")
                         + f'</td><td>{esc(v.get("axis") or "")}</td>'
                         f'<td class="mm-num">{float(v.get("weight") or 0):.2f}</td></tr>'
                         for k, v in ordered)
               + "</tbody></table>")
    weights += ('<p class="mm-src">Each input is a percentile rank among the rated '
                'vendors; an axis is the weighted mean of its inputs. On the map, distance '
                'from the base is the mean of the two axes and the angle is their balance. '
                f'A vendor at or above {cfg.get("tiers", {}).get("scale_cut", 50)} on scale '
                f'and {cfg.get("tiers", {}).get("momentum_cut", 50)} on momentum is '
                'Executing; high on one only is Establishing (scale) or Accelerating '
                '(momentum); below both is Emerging.</p>')
    out.append(fold("How the map is computed — weights and rules", weights))
    out.append("</section>")
    return "".join(out)


def _mask_names(names: List[str], allowed: Optional[set]) -> List[str]:
    """The names the viewer may see, plus a count for the rest."""
    if allowed is None:
        return list(names)
    shown = [n for n in names if n in allowed]
    hidden = len(names) - len(shown)
    if hidden:
        shown.append(f"{hidden} vendor{'s' if hidden > 1 else ''} not shown in this view")
    return shown


def _voice_row(v: Dict[str, Any]) -> str:
    """One account in the voices table: linked handle, who they are if we
    have profiled them, and a link to their latest relevant post."""
    handle = f'@{esc(v["author"])}'
    if v.get("profile_url"):
        handle = f'<a href="{esc(v["profile_url"])}">{handle}</a>'
    acct = v.get("account") or {}
    tag = v.get("vendor_tag") or {}
    prefix = ""
    if tag:
        prefix = (f'<strong>{esc(tag["label"].capitalize())}</strong>'
                  + (f' ({esc(tag["org"])})' if tag.get("org") else "") + " · ")
    if acct.get("profiled"):
        bits = []
        if acct.get("display_name"):
            bits.append(esc(acct["display_name"]))
        if acct.get("followers") is not None:
            bits.append(f'{int(acct["followers"]):,} followers')
        who = prefix + " · ".join(bits)
        if acct.get("summary"):
            who += f'<div class="mm-src">{esc(_clip(acct["summary"], 160))}</div>'
    else:
        who = prefix + '<span class="mm-src">not profiled</span>'
    latest = v.get("latest_post") or {}
    if latest.get("url"):
        latest_cell = (f'<a href="{esc(latest["url"])}">'
                       f'{esc((v.get("last_seen") or "")[:10] or "post")}</a>')
    else:
        latest_cell = esc((v.get("last_seen") or "")[:10])
    return (f'<tr><td>{handle}</td><td>{who}</td>'
            f'<td>{esc(v["platform"])}</td>'
            f'<td class="mm-num">{v["posts"]}</td>'
            f'<td class="mm-num">{v["engagement"]}</td>'
            f'<td class="mm-src">{latest_cell}</td></tr>')


def _clip(text_value: str, limit: int) -> str:
    """Cut at a word, not through one. Slicing raw left "World Wide Technol"."""
    text_value = (text_value or "").strip()
    if len(text_value) <= limit:
        return text_value
    cut = text_value[:limit].rsplit(" ", 1)[0].rstrip(" ,;:—-")
    return (cut or text_value[:limit]) + "…"


def _norm_words(text_value: str) -> str:
    """Text reduced to comparable words, for spotting a repeated sentence."""
    return re.sub(r"[^a-z0-9 ]", " ",
                  re.sub(r"\s+", " ", (text_value or "").lower())).strip()


def _spark(values: List[float], *, label: str) -> str:
    """A sparkline, or nothing.

    Refuses to draw fewer than four points. Two readings joined by a line is a
    picture of a trend built from no trend, and this report spent a lot of
    effort today not doing that elsewhere — the headcount series currently has
    two weekly points and its own ``thin_coverage`` flag.
    """
    pts = [v for v in values if isinstance(v, (int, float))]
    if len(pts) < 4:
        return ""
    lo, hi = min(pts), max(pts)
    span = (hi - lo) or 1
    step = 180 / (len(pts) - 1)
    coords = " ".join(
        f"{'M' if i == 0 else 'L'}{i * step:.0f} {24 - (v - lo) / span * 20:.0f}"
        for i, v in enumerate(pts))
    return (f'<svg class="n-spark" viewBox="0 0 180 28" role="img" '
            f'aria-label="{esc(label)}">'
            f'<path class="base" d="M0 24H180"/><path d="{coords}"/></svg>')


def _metric_card(label: str, hint: str, value: str, note: str,
                 spark: str = "", nospark: str = "", caption: str = "") -> str:
    body = spark or (f'<div class="n-nospark">{esc(nospark)}</div>'
                     if nospark else "")
    if spark and caption:
        body += f'<div class="n-nospark">{esc(caption)}</div>' 
    return (
        '<article class="n-metric">'
        f'<div class="n-metric-top"><span>{esc(label)}</span>'
        f'<span>{esc(hint)}</span></div>'
        f'<div class="n-metric-value">{esc(value)}</div>'
        f'<div class="n-delta">{esc(note)}</div>{body}</article>')


def _delta(now: float, prev: Optional[float], *, unit: str = "",
           period: str = "the period before",
           since: Optional[str] = None) -> str:
    """A change, or why there is not one.

    Percentages off a base of zero are not percentages, and a comparison
    against a period we were not measuring in is not a comparison. Both come
    back as a sentence rather than a number pretending to be one.
    """
    if prev is None:
        return ("No earlier period to compare with yet"
                + (f"; collection began {since}" if since else ""))
    delta = now - prev
    if not delta:
        return f"Unchanged on {period}"
    if not prev:
        return f"Up from none in {period}"
    return (f'{(delta / prev) * 100:+.0f}% on {period} '
            f'({prev:,.0f} → {now:,.0f}{unit})')


def _news_metrics(*, headcount: Optional[Dict[str, Any]],
                  jobs_total: int, jobs_new: int, jobs_state: str,
                  funding: Optional[Dict[str, Any]],
                  earned: int, earned_note: str,
                  earned_prev: Optional[int],
                  movers: Optional[Dict[str, Any]],
                  weekly: List[Dict[str, Any]],
                  started: Optional[str] = None) -> str:
    """The four figures at the top, each with its own denominator.

    Every one carries how much of the market it covers, because the number
    alone is the thing this product spent the day learning not to print.
    """
    cards: List[str] = []

    if headcount:
        cohort = headcount.get("cohort") or 0
        total = headcount.get("registry_total") or 0
        # A market total needs one reading per vendor; a market *change* needs
        # two of the same vendor, and 83 of 84 have one. So the delta states
        # what actually moved rather than a market figure it cannot support.
        # How often we have read each vendor is our business, not the
        # reader's. Until two readings cover the market there is no change
        # to report, and that is all the card says.
        head_delta = "No market-wide change to report yet."
        cards.append(_metric_card(
            "Staff", f"counted at {cohort} of {total} vendors",
            f"{headcount.get('observed_market_headcount', 0):,}",
            head_delta,
            # The weekly headcount series has two points and its own
            # thin-coverage flag, so there is nothing honest to draw.
            nospark=""))

    cards.append(_metric_card(
        "Open roles", "LinkedIn and company job boards",
        f"{jobs_total:,}" if jobs_state != "unmeasured" else "—",
        (f"{jobs_new} of them newly posted" if jobs_new else "Roles open today"),
        nospark="Roles open today, not roles advertised this month."))

    if funding:
        cov = funding.get("coverage") or {}
        disclosed = sum(int(r.get("vendors") or 0)
                        for r in (funding.get("stages") or [])
                        if (r.get("stage") or "") != "not stated")
        cards.append(_metric_card(
            "Vendors with a known funding stage",
            f'of {cov.get("measured", 0)} Crunchbase profiles read',
            f"{disclosed:,}",
            "Funding stage and investors, from Crunchbase.",
            nospark="Stages only. No round sizes, so no largest raise."))

    # Weeks that are still filling are left out of the line rather than drawn
    # as a fall. The newest bar always under-reads — the week is not over, and
    # matching runs days behind publication — so plotting it draws a collapse
    # that is not there.
    settled = [w for w in weekly if not w.get("partial")]
    dropped = len(weekly) - len(settled)
    cards.append(_metric_card(
        "Written about by others", "excludes the vendors' own posts",
        f"{earned:,}",
        _delta(earned, earned_prev, period="the 30 days before", since=started)
        + (f". {earned_note}" if earned_note else ""),
        _spark([w.get("n") or 0 for w in settled],
               label="Articles and posts matched each week, completed weeks only")
        or "",
        nospark=("Not enough completed weeks to chart." if dropped and not settled
                 else "" if settled else "Not enough weeks to chart."),
        caption=("Completed weeks only. This week and last are still "
                 "coming in." if dropped else "")))

    return f'<section class="n-metrics">{"".join(cards)}</section>'


_PLATFORM_NAMES = {"linkedin": "LinkedIn", "twitter": "X", "x": "X",
                   "bluesky": "Bluesky", "reddit": "Reddit",
                   "mastodon": "Mastodon"}


def _evidence_label(row: Dict[str, Any], seen: set) -> str:
    """A link somebody would click, not "linkedin" and not "source 2".

    The vendor's own announcement is named as that. A publisher is named by
    its masthead. A repeated label takes the record's title instead, because
    two links both reading "LinkedIn" tell a reader nothing about which to
    open.
    """
    source = (row.get("source") or "").strip()
    title = (row.get("title") or "").strip()
    platform = _PLATFORM_NAMES.get(source.lower(), source)

    if row.get("source_type") == "jobs":
        label = (f"a job listing on {platform}"
                 if source.lower() in _PLATFORM_NAMES else "a job listing")
    elif row.get("voice") == "owned" and row.get("social"):
        label = (f"the company's {platform} post" if platform
                 else "the company's own announcement")
    elif row.get("voice") == "owned":
        label = "the company's website"
    elif row.get("voice") == "primary":
        label = f"a filing on {platform}" if platform else "a primary document"
    elif row.get("author") and row.get("social"):
        # An account, not a network: six links all reading "X" tell the
        # reader nothing about who said it.
        label = f"@{row['author']} on {platform}" if platform else f"@{row['author']}"
    else:
        label = platform or "an outside report"

    if label.lower() in seen and title:
        label = _clip(title, 60)
    seen.add(label.lower())
    return label


def _story_evidence(f: Dict[str, Any]) -> str:
    """Every record behind a finding, split into records and discussion.

    The split is *whose voice*, not whether the item carries social metadata.
    A vendor announcing a product on LinkedIn is the announcement — filing it
    under "Social" beside practitioner chatter said the company's own statement
    was somebody talking about it.
    """
    rows = [r for r in (f.get("supporting") or []) if r.get("uri")]
    measured = [r for r in (f.get("supporting") or [])
                if r.get("voice") == "measured"]
    if not rows:
        if measured:
            return ('<div class="n-support"><strong>Evidence:</strong> '
                    f'{esc(measured[0].get("title") or "platform readings")}'
                    '</div>')
        held = int(f.get("evidence_count") or 0)
        if not held:
            return ""
        return ('<div class="n-support"><strong>Evidence:</strong> '
                f'{held} record{"" if held == 1 else "s"} held, none with a '
                'public link</div>')

    seen: set = set()
    records = [r for r in rows if r.get("voice") == "owned" or not r.get("social")]
    discussion = [r for r in rows if r not in records]

    def links(items):
        return ", ".join(f'<a href="{esc(r["uri"])}">'
                         f'{esc(_evidence_label(r, seen))}</a>' for r in items)

    out = ['<div class="n-support">']
    if records:
        # "Evidence" when there is one record and nothing to add to it;
        # "More" when the list actually continues past the byline.
        label = "Evidence" if len(records) == 1 and not discussion else "More"
        out.append(f"<div><strong>{label}:</strong> {links(records)}</div>")
    if discussion:
        out.append(f"<div><strong>Social:</strong> {links(discussion)}</div>")
    out.append("</div>")
    return "".join(out)


def _relink(params: Dict[str, Any], **overrides: Any) -> str:
    """The current query string with some values replaced.

    The period links have to carry the signed token through, or a shared
    reader switching from 30 days to 7 lands on a 404. `days` is not part of
    what the token signs, so only the window changes.
    """
    from urllib.parse import urlencode

    merged = {k: v for k, v in {**params, **overrides}.items() if v is not None}
    return esc(urlencode(merged))


# ---------------------------------------------------------------------------
# The shared view: a few figures in full, the rest blurred behind a trial form
# ---------------------------------------------------------------------------
#
# A restricted reader (shared link or public market) sees the lead, the market
# scope, the period comparison, the snapshot and the formation section in
# full. Funding onwards, the registry beyond its first rows, and the coverage
# figures are rendered and then blurred. Blur alone is not a paywall: the
# figures would still be in the page source, so every digit in the blurred
# text is replaced with an 8 first. The shape of the evidence stays, the
# values do not.

_TEASER_START = "<!--mm-teaser-start-->"
_TEASER_END = "<!--mm-teaser-end-->"
TEASER_REGISTRY_ROWS = 3

_TRIAL_JS = """
(function(){var f=document.getElementById('mm-trial-form');if(!f)return;
var m=document.getElementById('mm-trial-msg');var el=f.elements;
f.addEventListener('submit',function(e){e.preventDefault();
var b=f.querySelector('button');b.disabled=true;m.className='mm-trial-msg';
m.textContent='Sending…';
var d={name:el['name'].value,email:el['email'].value,title:el['title'].value};
fetch(f.getAttribute('data-endpoint'),{method:'POST',
headers:{'Content-Type':'application/json'},body:JSON.stringify(d)})
.then(function(r){return r.json().then(function(j){return {ok:r.ok,j:j};});})
.then(function(x){if(x.ok){f.reset();
m.textContent='Thanks. We will be in touch at '+d.email+'.';}
else{b.disabled=false;m.className='mm-trial-msg err';
m.textContent=(x.j&&x.j.detail&&typeof x.j.detail==='string')?x.j.detail:'Could not send the request.';}})
.catch(function(){b.disabled=false;m.className='mm-trial-msg err';
m.textContent='Could not send the request from this copy of the page.';});});})();
"""


def _teaser_open(what: str) -> str:
    """Marks where blurring starts; ``what`` names the blurred figures."""
    return f"{_TEASER_START}[{esc(what)}]"


def _scrub_digits(fragment: str) -> str:
    """Every digit in the text of ``fragment`` becomes 8. Tags and attributes
    are left alone, so the markup still lays out as it did."""
    return re.sub(r">([^<]*)<",
                  lambda m: ">" + re.sub(r"\d", "8", m.group(1)) + "<",
                  fragment)


def _teaser_row(row_html: str) -> str:
    return _scrub_digits(row_html).replace("<tr>", '<tr class="mm-teaser-row">', 1)


def _apply_teasers(rendered: str) -> str:
    """Wrap every marked range: scrubbed and blurred, with the request card
    on top. Runs on the finished document so the ranges can span sections."""
    def _wrap(m):
        what, inner = m.group(1), m.group(2)
        return ('<div class="mm-teaser">'
                '<div class="mm-teaser-body" aria-hidden="true">'
                + _scrub_digits(inner) + "</div>"
                '<div class="mm-teaser-cta"><div>'
                f"{what} are blurred in this shared view."
                '<br><a class="mm-btn" href="#mm-trial">Request a trial</a>'
                "</div></div></div>")
    return re.sub(re.escape(_TEASER_START) + r"\[(.*?)\](.*?)" + re.escape(_TEASER_END),
                  _wrap, rendered, flags=re.S)


_MISSING_JS = """
(function(){var f=document.getElementById('mm-missing-form');if(!f)return;
var m=document.getElementById('mm-missing-msg');var el=f.elements;
f.addEventListener('submit',function(e){e.preventDefault();
var b=f.querySelector('button');b.disabled=true;m.className='mm-trial-msg';
m.textContent='Sending…';
var d={company:el['company'].value,website:el['website'].value,
email:el['email'].value,note:el['note'].value};
fetch(f.getAttribute('data-endpoint'),{method:'POST',
headers:{'Content-Type':'application/json'},body:JSON.stringify(d)})
.then(function(r){return r.json().then(function(j){return {ok:r.ok,j:j};});})
.then(function(x){if(x.ok){f.reset();
m.textContent='Thanks. We will look at '+d.company+' and reply at '+d.email+'.';}
else{b.disabled=false;m.className='mm-trial-msg err';
m.textContent=(x.j&&x.j.detail&&typeof x.j.detail==='string')?x.j.detail:'Could not send the request.';}})
.catch(function(){b.disabled=false;m.className='mm-trial-msg err';
m.textContent='Could not send the request from this copy of the page.';});});})();
"""


def _missing_panel(market_id: int, market_name: str) -> str:
    """"Is your company missing?" — a vendor asks to be on the list."""
    return (
        '<section class="mm-trial" id="mm-missing">'
        "<h2>Is your company missing?</h2>"
        f"<p>If your company competes in {esc(market_name)} and is not on "
        "the list above, tell us and we will look at it. We add vendors on "
        "the evidence, not on request, so a website we can read helps.</p>"
        '<form id="mm-missing-form" data-endpoint='
        f'"/api/market-monitor/markets/{int(market_id)}/vendor-request">'
        '<div><label for="mm-missing-company">Company</label>'
        '<input id="mm-missing-company" name="company" required maxlength="200" '
        'autocomplete="organization"></div>'
        '<div><label for="mm-missing-website">Website</label>'
        '<input id="mm-missing-website" name="website" maxlength="300" '
        'autocomplete="url" placeholder="https://"></div>'
        '<div><label for="mm-missing-email">Your email</label>'
        '<input id="mm-missing-email" name="email" type="email" required '
        'maxlength="254" autocomplete="email"></div>'
        '<div><label for="mm-missing-note">What you do (optional)</label>'
        '<input id="mm-missing-note" name="note" maxlength="2000"></div>'
        '<div><button type="submit" class="mm-btn">Tell us</button></div>'
        '<div class="mm-trial-msg" id="mm-missing-msg" role="status"></div>'
        "</form>"
        f"<script>{_MISSING_JS}</script>"
        "</section>")


def _trial_panel(market_id: int) -> str:
    """The request form. One per page; the blurred blocks link to it."""
    return (
        '<section class="mm-trial" id="mm-trial">'
        "<h2>Get the full report and the data behind it</h2>"
        "<p>This shared view shows part of the market. A trial gives you the "
        "whole of it: every vendor and every figure, an RSS feed, an MCP "
        "server for your own tools, CSV export of the data, and a weekly "
        "report by email.</p>"
        '<form id="mm-trial-form" data-endpoint='
        f'"/api/market-monitor/markets/{int(market_id)}/trial-request">'
        '<div><label for="mm-trial-name">Name</label>'
        '<input id="mm-trial-name" name="name" required maxlength="200" '
        'autocomplete="name"></div>'
        '<div><label for="mm-trial-email">Company email</label>'
        '<input id="mm-trial-email" name="email" type="email" required '
        'maxlength="254" autocomplete="email"></div>'
        '<div><label for="mm-trial-title">Title</label>'
        '<input id="mm-trial-title" name="title" maxlength="200" '
        'autocomplete="organization-title"></div>'
        '<div><button type="submit" class="mm-btn">Request trial</button></div>'
        '<div class="mm-trial-msg" id="mm-trial-msg" role="status"></div>'
        "</form>"
        f"<script>{_TRIAL_JS}</script>"
        "</section>")


def _drawer_open(title: str, blurb: str, anchor: str = "", *,
                 opened: bool = False) -> str:
    """A collapsed section of the report, named by what is inside it.

    ``<details>`` rather than a scripted toggle: it opens with the keyboard,
    prints open, is found by the browser's own in-page search, and works in a
    file saved to disk with scripting off. The summary says what the drawer
    holds, because "More" on a closed drawer is a reason not to open it.
    """
    # The id goes on the <details>, not on a marker before it. An anchor
    # landing just outside a closed drawer scrolls to a shut door; on the
    # element itself, the script walking up from the target opens it.
    ident = f' id="{esc(anchor)}"' if anchor else ""
    # `opened` for the one drawer that is the page's opening picture.
    return (f'<details class="mm-drawer"{ident}{" open" if opened else ""}><summary>'
            f'<span class="mm-drawer-t">{esc(title)}</span>'
            f'<span class="mm-drawer-b">{esc(blurb)}</span>'
            f'</summary><div class="mm-drawer-body">')


def _drawer_close() -> str:
    return "</div></details>"


# ---------------------------------------------------------------------------
# The lead: findings, who moved, what it says, the developments
# ---------------------------------------------------------------------------
#
# Every function below takes the structures ``market_assessment.assess``
# returns and lays them out. None of them decides what is material, what
# merges with what, or whose word an event rests on — those are fields on the
# objects they receive.

#: Colour for a development's kind tag, by the analysis' canonical type.
_KIND_COLOUR = {
    "acquisition": "var(--n-purple)", "market_exit": "var(--n-purple)",
    "market_entry": "var(--n-purple)", "funding": "var(--n-purple)",
    "customer": "var(--n-orange)", "partnership": "var(--n-orange)",
    "product_launch": "var(--n-blue)", "product_expansion": "var(--n-blue)",
    "executive_appointment": "var(--n-accent)",
    "significant_hiring": "var(--n-green)", "headcount_change": "var(--n-green)",
}

#: Colour for an observation state's dot.
_STATE_COLOUR = {
    "material_change": "var(--n-accent)",
    "monitored_no_material_change": "var(--n-green)",
    "incomplete_coverage": "var(--n-orange)",
    "paused": "var(--n-muted)",
    "not_yet_collected": "var(--n-line)",
}

#: Client-side behaviour: open the drawer an anchor points into. Inline
#: because the report is opened from a saved file as often as from a URL.
_NEWS_JS = """
(function(){
// A link to an anchor inside a closed <details> does not scroll, because the
// target is not laid out. Open the drawer first, then let the jump happen.
function open_for(hash){if(!hash)return;var t=document.getElementById(
hash.slice(1));while(t){if(t.tagName==='DETAILS')t.open=true;t=t.parentElement;}}
[].slice.call(document.querySelectorAll('a[href^="#"]')).forEach(function(a){
a.addEventListener('click',function(){open_for(a.getAttribute('href'));
setTimeout(function(){var t=document.getElementById(
a.getAttribute('href').slice(1));if(t)t.scrollIntoView();},0);});});
if(location.hash)open_for(location.hash);})();
"""


def _dev_anchor(dev: Dict[str, Any]) -> str:
    if dev.get("event_type") == "significant_hiring":
        return "dev-hiring"
    return f'dev-{dev.get("rank") or 0}'


def _dev_date(dev: Dict[str, Any]) -> str:
    """The event's date as a reader writes it, or an honest absence."""
    if dev.get("date"):
        return _day(dev["date"]) if dev.get("date_established", True) \
            else f'seen {_day(dev["date"])}, date not established'
    if dev.get("event_type") == "significant_hiring":
        return "observed this period"
    return "date not established"


def _dev_sources(dev: Dict[str, Any]) -> str:
    n = int(dev.get("source_count") or 0)
    if dev.get("provenance") == "measured":
        return "two LinkedIn readings"
    return f'{n} observed source{"" if n == 1 else "s"}'


def _render_findings(findings: List[Dict[str, Any]],
                     devs_by_id: Dict[str, Dict[str, Any]]) -> str:
    """The executive assessment: each finding with its evidence and its
    coverage line, and a link to every development it rests on."""
    if not findings:
        return ('<p class="n-empty">The period holds too little evidence to '
                'support a finding. The developments and the coverage table '
                'below say what was observed.</p>')
    out = ['<ol class="n-findings">']
    for f in findings:
        out.append('<li class="n-finding">')
        out.append(f'<h3>{esc(f["headline"])}</h3>')
        out.append(f'<p>{esc(f["body"])}</p>')
        linked = [devs_by_id[i] for i in (f.get("developments") or [])
                  if i in devs_by_id]
        if f.get("evidence"):
            items = []
            for e in f["evidence"]:
                # An evidence line that opens with a development's headline
                # is that development's citation, so it links there.
                dev = next((d for d in linked if e.startswith(d["headline"])), None)
                if dev:
                    items.append(f'<li><a href="#{_dev_anchor(dev)}">'
                                 f'{esc(dev["headline"])}</a>'
                                 f'{esc(e[len(dev["headline"]):])}</li>')
                else:
                    items.append(f'<li>{esc(e)}</li>')
            out.append('<ul class="n-evidence">' + "".join(items) + "</ul>")
        # Links only when the finding rests on a handful of developments the
        # evidence lines have not already named; a list of 23 is the
        # developments section, not a citation.
        named = " ".join(f.get("evidence") or [])
        if linked and len(linked) <= 5 and not all(
                d["headline"] in named for d in linked):
            links = ", ".join(
                f'<a href="#{_dev_anchor(d)}">{esc(_clip(d["headline"], 48))}</a>'
                for d in linked[:5])
            more = len(linked) - min(len(linked), 5)
            out.append('<div class="n-cites">Developments: ' + links
                       + (f" and {more} more" if more > 0 else "") + "</div>")
        if f.get("coverage"):
            out.append(f'<div class="n-coverage">{esc(f["coverage"])}</div>')
        out.append("</li>")
    out.append("</ol>")
    return "".join(out)


def _dev_evidence_links(dev: Dict[str, Any]) -> str:
    """The records behind one development, reusing the story-evidence
    renderer so the labelling rules are the same everywhere."""
    return _story_evidence({"supporting": dev.get("evidence") or [],
                            "evidence_count": dev.get("evidence_count") or 0})


def _render_moved_table(devs: List[Dict[str, Any]]) -> str:
    """Vendors showing material change: the centrepiece table."""
    if not devs:
        return ('<p class="n-empty">No vendor showed a material change in '
                'the period, on the sources we collect.</p>')
    out = ['<div class="n-tablewrap"><table class="mm-table n-moved"><thead><tr>'
           '<th>Vendor</th><th>Material change</th><th>Evidence</th>'
           '<th>Why it matters</th></tr></thead><tbody>']
    for d in devs:
        vendors = ", ".join(v.get("vendor") or "" for v in d.get("vendors") or [])
        out.append(
            "<tr>"
            f'<td><strong>{esc(vendors)}</strong></td>'
            f'<td><a href="#{_dev_anchor(d)}">{esc(_clip(d["headline"], 110))}</a>'
            f'<div class="mm-src">{esc(d["event_type_label"])} · '
            f'{esc(_dev_date(d))}</div></td>'
            f'<td class="mm-src">{_dev_top_link(d)}{esc(_dev_sources(d))}<br>'
            f'{esc(d["provenance_label"])}</td>'
            f'<td class="n-why-cell">{esc(d["why_it_matters"])}</td>'
            "</tr>")
    out.append("</tbody></table></div>")
    return "".join(out)


def _dev_top_link(dev: Dict[str, Any]) -> str:
    """The one record a reader should open first: an outside report where
    there is one, the vendor's own otherwise."""
    rows = [e for e in (dev.get("evidence") or []) if e.get("uri")]
    if not rows:
        return ""
    rows.sort(key=lambda e: {"independent": 0, "primary": 1}.get(e.get("voice"), 2))
    return (f'<a href="{esc(rows[0]["uri"])}">'
            f'{esc(_evidence_label(rows[0], set()))}</a> · ')


def _render_other_developments(devs: List[Dict[str, Any]]) -> str:
    if not devs:
        return ""
    rows = "".join(
        f'<tr><td>{esc(", ".join(v.get("vendor") or "" for v in d["vendors"]))}</td>'
        f'<td><a href="#{_dev_anchor(d)}">{esc(_clip(d["headline"], 90))}</a></td>'
        f'<td class="mm-src">{esc(d["event_type_label"])} · {esc(_dev_date(d))}</td>'
        f'<td class="mm-src">{esc(_dev_sources(d))} · {esc(d["provenance_label"])}</td>'
        "</tr>" for d in devs)
    return (f'<details class="n-more"><summary>Other observed developments '
            f'({len(devs)})</summary><div class="n-tablewrap">'
            f'<table class="mm-table"><tbody>{rows}</tbody></table></div></details>')


def _render_synthesis(paragraphs: List[Dict[str, Any]]) -> str:
    if not paragraphs:
        return ('<p class="n-empty">Too few developments in the period to say '
                'what the distribution means.</p>')
    out = ['<div class="n-synth">']
    for p in paragraphs:
        out.append(f'<div class="n-synth-item"><h3>{esc(p["heading"])}</h3>'
                   f'<p>{esc(p["text"])}</p>'
                   + (f'<div class="n-coverage">{esc(p["coverage"])}</div>'
                      if p.get("coverage") else "")
                   + "</div>")
    out.append("</div>")
    return "".join(out)


def _render_observation(observation: Dict[str, Any]) -> str:
    """Observed vendor activity, as states — never "vendors with no signal"."""
    out = ['<section class="n-card" id="mm-observation"><div class="n-card-title">'
           '<h2>Observed vendor activity</h2>'
           f'<span class="n-updated">{observation.get("total", 0)} vendors</span>'
           '</div>']
    for s in observation.get("states") or []:
        if not s["n"]:
            continue
        colour = _STATE_COLOUR.get(s["state"], "var(--n-muted)")
        out.append(f'<div class="n-state"><span class="dot" '
                   f'style="background:{colour}"></span>'
                   f'<span class="n-row-val">{s["n"]}</span>'
                   f'<span>{esc(s["label"])}</span></div>')
    names = {"linkedin_company_post": "LinkedIn page", "vendor_web": "website",
             "linkedin_jobs": "job listings", "crunchbase_company": "Crunchbase page"}
    required = [names.get(s, s.replace("_", " "))
                for s in observation.get("required_sources") or []]
    out.append('<p class="n-note">A vendor counts as showing no material '
               'change only when its '
               + (esc(" and ".join(required)) if required else "expected sources")
               + ' were read during the period. Otherwise it is listed as '
               'incompletely observed.</p>')
    out.append("</section>")
    return "".join(out)


def _render_hiring_block(devs: List[Dict[str, Any]]) -> str:
    """Hiring developments as one block: a vendor, a count, a mix. Eleven
    entries each listing thirty job titles is the jobs table, not the news."""
    if not devs:
        return ""
    rows = []
    for d in devs:
        attrs = d.get("attributes") or {}
        mix = ", ".join(f"{k} {v}" for k, v in sorted(
            (attrs.get("by_function") or {}).items(), key=lambda kv: -kv[1])[:3])
        vendor = ", ".join(v.get("vendor") or "" for v in d.get("vendors") or [])
        rows.append(f'<div class="n-row"><span class="n-rank"></span>'
                    f'<div><strong>{esc(vendor)}</strong>'
                    + (f'<div class="n-row-label">{esc(mix)}</div>' if mix else "")
                    + f'</div><span class="n-row-val">{attrs.get("openings", "")}'
                    ' open roles</span></div>')
    first = devs[0]
    return (f'<article class="n-story" id="{_dev_anchor(first)}" '
            'style="--story:var(--n-green)">'
            '<div class="n-story-tag">Hiring</div>'
            f'<h3>{len(devs)} vendors with {massess_min_openings()} or more open '
            'roles observed</h3>'
            '<div class="n-byline">Job boards · observed this period · '
            'Vendor source only</div>'
            + "".join(rows) + "</article>")


def massess_min_openings() -> int:
    from app.services.market_assessment import MIN_OPENINGS_FOR_HIRING
    return MIN_OPENINGS_FOR_HIRING


def _render_developments(devs: List[Dict[str, Any]]) -> str:
    """Material market developments, one entry per event."""
    if not devs:
        return '<p class="n-empty">No material development in the period.</p>'
    out = []
    hiring = [d for d in devs if d["event_type"] == "significant_hiring"]
    for d in devs:
        if d["event_type"] == "significant_hiring":
            continue
        colour = _KIND_COLOUR.get(d["event_type"], "var(--n-accent)")
        vendors = ", ".join(v.get("vendor") or "" for v in d.get("vendors") or [])
        out.append(f'<article class="n-story" id="{_dev_anchor(d)}" '
                   f'style="--story:{colour}">')
        out.append(f'<div class="n-story-tag">{esc(d["event_type_label"])}</div>')
        out.append(f'<h3>{esc(d["headline"])}</h3>')
        summary = (d.get("summary") or "").strip()
        head_key = _norm_words(d["headline"])
        sum_key = _norm_words(summary)
        # A summary that repeats the headline is not a summary. The title is
        # often the post's own first line, so compare inside, not at the start.
        duplicate = bool(head_key) and (head_key[:60] in sum_key
                                        or sum_key[:60] in head_key)
        if summary and not duplicate:
            out.append(f'<p class="n-story-sum">{esc(_clip(summary, 320))}</p>')
        bits = [vendors, _dev_date(d), _dev_sources(d), d["provenance_label"]]
        out.append('<div class="n-byline">'
                   + " · ".join(esc(b) for b in bits if b) + "</div>")
        out.append(_dev_evidence_links(d))
        out.append("</article>")
    out.append(_render_hiring_block(hiring))
    return "".join(out)


def _render_corpus(clustered: List[Dict[str, Any]], *, collected: int,
                   shown: int) -> str:
    if not clustered:
        return ""
    head = (f'View underlying coverage: the {shown} most recent of {collected} '
            'collected records' if collected > shown else
            f'View underlying coverage: all {shown} collected records')
    return (f'<details class="n-more"><summary>{esc(head)}</summary>'
            '<p class="n-note">Everything matched to this market in the '
            'period, including general discussion and anything that did not '
            'become a development.</p><div class="n-tablewrap">'
            '<table class="mm-table"><tbody>'
            + "".join(_coverage_row(a) for a in clustered)
            + "</tbody></table></div></details>")


def _river_source(row: Dict[str, Any]) -> str:
    """Who published it, the way a river labels a line: an outlet, a
    vendor's own channel, or an account on a network."""
    meta = row.get("social_meta") or {}
    kind = row.get("article_class")
    source = (row.get("news_source") or "").strip()
    platform = _PLATFORM_NAMES.get(
        (meta.get("platform") or source.split(":")[-1] or "").lower(), "")
    vendors = [v.get("vendor") for v in (row.get("vendors") or []) if v.get("vendor")]
    if kind == "social":
        return f"{vendors[0]} on LinkedIn" if vendors else "LinkedIn"
    if kind == "discussion":
        author = meta.get("author")
        return (f"@{author} on {platform}" if author and platform
                else f"@{author}" if author else platform or source)
    if kind == "vendor":
        return vendors[0] if vendors else (re.sub(r"^www\.", "", source) or "vendor site")
    return re.sub(r"^www\.", "", source) or "news"


def _river_time(published: Optional[str]) -> str:
    raw = str(published or "")
    try:
        stamp = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return stamp.strftime("%H:%M")
    except ValueError:
        return raw[11:16] if len(raw) >= 16 else ""


def _river_day(published: Optional[str]) -> str:
    raw = str(published or "")[:10]
    try:
        return datetime.strptime(raw, "%Y-%m-%d").strftime("%A %-d %B %Y")
    except ValueError:
        return raw or "Undated"


def render_news_river(rows: List[Dict[str, Any]]) -> str:
    from app.services import market_assessment as massess
    """Every record in the period, newest first, grouped by day.

    A line is a time, a source and a headline. Where several records carry
    one story the first is the line and the rest are the "More:" links,
    named by outlet or account, so the reader sees one story once.
    """
    if not rows:
        return '<p class="n-empty">Nothing collected in the period.</p>'
    out = []
    day = None
    for row in rows:
        this_day = _river_day(row.get("published"))
        if this_day != day:
            day = this_day
            out.append(f'<h2 class="n-day">{esc(day)}</h2>')
        # The extractor prefixes a post with its vendor ("Elezar: Most
        # SOCs…"); the source label already says who, so the prefix comes off.
        headline = massess.headline_of(row) if row.get("title") else row["uri"]
        # A practitioner post is stored as "@handle: text"; the source label
        # already names the handle.
        author = (row.get("social_meta") or {}).get("author")
        if author and headline.lower().startswith(f"@{author}:".lower()):
            headline = headline[len(author) + 2:].strip() or headline
        kind = row.get("article_class") or ""
        badge = (f'<span class="n-kind">{esc(kind)}</span>'
                 if kind in ("vendor", "social", "research") else "")
        more = ""
        others = ((row.get("cluster") or {}).get("others")) or []
        if others:
            seen: set = set()
            links = []
            for o in others:
                label = _river_source({**o, "vendors": row.get("vendors"),
                                       "social_meta": {"author": o.get("author")}})
                if label.lower() in seen and o.get("title"):
                    label = _clip(o["title"], 60)
                seen.add(label.lower())
                links.append(f'<a href="{esc(o["uri"])}">{esc(label)}</a>')
            more = '<div class="n-more">More: ' + ", ".join(links) + "</div>"
        out.append(
            '<div class="n-item">'
            f'<time>{esc(_river_time(row.get("published")))}</time>'
            f'<div><span class="n-src">{esc(_river_source(row))}</span> '
            f'<a class="n-head" href="{esc(row["uri"])}">{esc(_clip(headline, 180))}</a>'
            f'{badge}{more}</div></div>')
    return "".join(out)


def build_market_news_page(conn, market: Dict[str, Any], *, days: int = 30,
                           allowed_brand_ids: Optional[List[int]] = None,
                           link_params: Optional[Dict[str, Any]] = None
                           ) -> bytes:
    """The river: everything matched to the market in the period, as a
    time-ordered list of headlines with their sources. No analysis."""
    from app.services import market_analysis as man
    from app.services import market_corpus as mcorp
    from app.services import market_entitlements as ent
    from app.services import market_publish as mp

    link_params = dict(link_params or {})
    withheld = ent.withheld_names(conn, market["id"], allowed_brand_ids)
    rows = mcorp.articles(conn, market["id"], limit=2000, days=days,
                          require_signal_for_social=False)
    if allowed_brand_ids is not None:
        rows = ent.drop_text_mentioning(rows, withheld)
    vendor_names = [d["vendor"] for d in mp.build_dataset(conn, market["id"])]
    clustered = mcorp.cluster(rows, vendor_names) if rows else []
    try:
        pc = man.period_comparison(conn, market["id"], days=days)
        period_txt = _fmt_range(*pc["current_range"])
    except Exception:                                              # noqa: BLE001
        period_txt = f"last {days} days"

    periods = "".join(
        f'<a href="?{_relink(link_params, days=d, view="news")}"'
        + (' aria-current="page"' if d == days else "")
        + f'>{d} days</a>' for d in (7, 30, 90))
    rss = ""
    if market.get("is_public"):
        rss = (f'<a class="n-rss" href="feed.xml?days={days}" '
               'title="Subscribe in a feed reader">RSS</a>')
    body = [f"<style>{EXTRA_CSS}{NEWS_CSS}</style>", '<div class="mm-news">',
            '<div class="n-top">' + _brand_line()
            + '<nav class="n-pages" aria-label="Pages">'
            f'<a href="?{_relink(link_params, days=days)}">Assessment</a>'
            f'{rss}</nav>'
            f'<span class="n-market">{esc(market["name"])}</span></div>',
            '<main class="n-river">',
            '<div class="n-head"><div>'
            f'<div class="n-kicker">Market monitor · {esc(period_txt)}</div>'
            f'<h1>{esc(market["name"])}: news river</h1>'
            f'<p class="n-sub">{len(rows)} articles and posts matched in the '
            f'period, {len(clustered)} stories, newest first.</p></div>'
            f'<div><nav class="n-periods" aria-label="Reporting period">'
            f'{periods}{rss}</nav></div></div>',
            render_news_river(clustered),
            "</main>",
            '<div class="n-foot">' + _brand_line()
            + f'<span>{esc(market["name"])} · {esc(period_txt)}</span></div>',
            "</div>"]
    rendered = html_document(f'{market["name"]} — news river', "".join(body))
    ent.assert_no_withheld(rendered, withheld,
                           context=f'market {market["id"]} news river')
    return rendered.encode("utf-8")


def _render_briefing_card(conn, market: Dict[str, Any], *, withheld: List[str],
                          restricted: bool, link_params: Dict[str, Any],
                          briefing: Optional[Dict[str, Any]] = None) -> str:
    """The latest approved briefing as one block, or nothing when there is
    none. Never the text: the shared view may not name most vendors, and the
    page-level check would refuse the page."""
    from app.services import market_briefing as mbr

    briefing = briefing or mbr.latest_approved(conn, market["id"])
    if not briefing:
        return ""
    summary = mbr.safe_sentences(
        mbr.feed_summary(briefing.get("report_content") or ""), withheld)
    approved = briefing.get("updated_at")
    when = (approved.strftime("%d %B %Y") if hasattr(approved, "strftime")
            else str(approved or "")[:10])
    if restricted:
        cta = ('<p class="n-distil">The briefing itself is part of the trial. '
               '<a class="mm-btn" href="#mm-trial">Request a trial</a></p>')
    else:
        cta = (f'<p><a class="mm-btn" href="?{_relink(link_params, view="briefing", id=briefing["id"])}">'
               'Read the briefing</a></p>')
    return ('<section class="n-block" id="mm-briefing">'
            '<div class="n-sec-head"><h2>Weekly briefing</h2>'
            f'<span class="n-updated">{esc(briefing.get("period_label", ""))}'
            f' · approved {esc(when)}</span></div>'
            f'<h3>{esc(briefing.get("title", ""))}</h3>'
            + (f'<p>{esc(summary)}</p>' if summary else "")
            + cta + "</section>")


def build_market_briefing_page(conn, market: Dict[str, Any], *,
                               briefing_id: Optional[int] = None,
                               days: int = 30,
                               allowed_brand_ids: Optional[List[int]] = None,
                               link_params: Optional[Dict[str, Any]] = None
                               ) -> bytes:
    """``?view=briefing``: one approved briefing in full for a reader with a
    session; for a shared reader, the card only. A draft is never served here,
    whoever asks — approval is what makes a briefing part of the report."""
    from app.services import market_briefing as mbr
    from app.services import market_entitlements as ent

    link_params = dict(link_params or {})
    withheld = ent.withheld_names(conn, market["id"], allowed_brand_ids)
    restricted = allowed_brand_ids is not None
    briefing = (mbr.get(conn, market["id"], briefing_id) if briefing_id
                else mbr.latest_approved(conn, market["id"]))
    if not briefing or briefing.get("status") != "approved":
        briefing = None

    nav = ('<div class="n-top">' + _brand_line()
           + '<nav class="n-pages" aria-label="Pages">'
           f'<a href="?{_relink(link_params, days=days)}">Assessment</a>'
           f'<a href="?{_relink(link_params, days=days, view="news")}">News</a>'
           '</nav>'
           f'<span class="n-market">{esc(market["name"])}</span></div>')
    if not briefing:
        main = ('<main class="n-river"><div class="n-head"><div>'
                f'<h1>{esc(market["name"])}: briefing</h1>'
                '<p class="n-sub">No approved briefing yet.</p></div></div></main>')
    elif restricted:
        main = ('<main class="n-river">'
                + _render_briefing_card(conn, market, withheld=withheld,
                                        restricted=True, link_params=link_params,
                                        briefing=briefing)
                + '<p class="n-distil"><a href="?' + _relink(link_params, days=days)
                + '#mm-trial">Request a trial on the assessment page</a></p></main>')
    else:
        others = [b for b in mbr.approved_listing(conn, market["id"])
                  if b["id"] != briefing["id"]]
        more = ""
        if others:
            more = ('<h2>Earlier briefings</h2><ul>' + "".join(
                f'<li><a href="?{_relink(link_params, view="briefing", id=b["id"])}">'
                f'{esc(b.get("title") or b.get("period_label", ""))}</a></li>'
                for b in others) + "</ul>")
        main = ('<main class="n-river"><div class="n-head"><div>'
                f'<div class="n-kicker">Market monitor · '
                f'{esc(briefing.get("period_label", ""))}</div>'
                f'<h1>{esc(briefing.get("title", ""))}</h1></div></div>'
                + mbr.render_body(briefing) + more + "</main>")
    body = (f"<style>{EXTRA_CSS}{NEWS_CSS}</style>" '<div class="mm-news">'
            + nav + main
            + '<div class="n-foot">' + _brand_line()
            + f'<span>{esc(market["name"])}</span></div></div>')
    rendered = html_document(f'{market["name"]} — briefing', body)
    ent.assert_no_withheld(rendered, withheld,
                           context=f'market {market["id"]} briefing page')
    return rendered.encode("utf-8")


def build_market_report(conn, market: Dict[str, Any], *, days: int = 30,
                        allowed_brand_ids: Optional[List[int]] = None,
                        link_params: Optional[Dict[str, Any]] = None
                        ) -> bytes:
    """One market, one file, no external requests.

    Order: what changed (the findings), who changed (the table), what that
    says about the market, which vendors were actually observed, the
    deduplicated developments with their sources — then, collapsed, the
    evidence the conclusions rest on, the registry and the method. A reader
    can stop after the first two screens and know what happened.
    """
    from app.services import market_analysis as man
    from app.services import market_assessment as massess
    from app.services import market_corpus as mcorp
    from app.services import market_metrics as mmet
    from app.services import market_publish as mp

    from app.services import market_entitlements as ent

    overview = mp.build_overview(conn, market, days=days)
    analyses = {}
    for name in man.ANALYSES:
        try:
            analyses[name] = man.run(conn, market["id"], name, days=days)
        except Exception as exc:  # noqa: BLE001 — a missing panel is not a
            logger.warning("report analysis %s failed: %s", name, exc)

    # A restricted viewer gets a report assembled from only the vendors it may
    # see. The assessment takes the allowed list itself, so its findings are
    # computed from what the reader may see rather than filtered afterwards;
    # every other payload is filtered once, below, and the rendered bytes are
    # checked again at the end.
    allowed_names = None
    withheld = ent.withheld_names(conn, market["id"], allowed_brand_ids)
    if allowed_brand_ids is not None:
        allowed_names = set(
            ent.vendor_names(conn, market["id"], allowed_brand_ids).values())

    assessment = massess.assess(conn, market, days=days,
                                allowed_brand_ids=allowed_brand_ids)

    formation = analyses.get("formation")
    sn = analyses.get("signal_noise")
    funding = analyses.get("funding")
    hiring = analyses.get("hiring")
    sov = analyses.get("share_of_voice")

    try:
        pc = man.period_comparison(conn, market["id"], days=days)
    except Exception as exc:  # noqa: BLE001 — the report still stands without it
        logger.warning("period comparison failed: %s", exc)
        pc = None
    try:
        voices = man.top_voices(conn, market["id"], days=days, limit=20)
    except Exception as exc:  # noqa: BLE001
        logger.warning("top voices failed: %s", exc)
        voices = None
    try:
        highlights = man.social_highlights(conn, market["id"], days=days,
                                           limit=3)
    except Exception as exc:                                      # noqa: BLE001
        logger.warning("social highlights failed: %s", exc)
        highlights = []
    try:
        movers = mp.market_movers(conn, market, days=days)
    except Exception as exc:                                      # noqa: BLE001
        logger.warning("market movers failed: %s", exc)
        movers = None
    earned_prev = None
    if pc and pc.get("comparable"):
        try:
            earned_prev = int(man.share_of_voice(
                conn, market["id"], days=days * 2,
                until_days_ago=days).get("earned_total") or 0)
        except Exception as exc:                                  # noqa: BLE001
            logger.warning("previous-period share of voice failed: %s", exc)
    started_iso = (pc or {}).get("collection_started")
    started_txt = (datetime.fromisoformat(started_iso).strftime("%-d %B %Y")
                   if started_iso else None)

    link_params = dict(link_params or {})

    dataset = mp.build_dataset(conn, market["id"])
    articles = mcorp.articles(conn, market["id"], limit=60, days=days)
    try:
        from app.services import market_lists as mlists
        joblist = mlists.jobs(conn, market["id"], page_size=1)
    except Exception as exc:                                      # noqa: BLE001
        logger.warning("report jobs failed: %s", exc)
        joblist = None
    try:
        headcount = mp.headcount_market(conn, market)
    except Exception as exc:                                      # noqa: BLE001
        logger.warning("report headcount failed: %s", exc)
        headcount = None

    # ── The entitlement gate ────────────────────────────────────────────
    # A restricted reader also gets the teaser treatment below: some
    # figures in full, the rest blurred behind the trial form.
    teaser = allowed_brand_ids is not None
    if allowed_brand_ids is not None:
        overview = ent.filter_rows(overview, allowed_brand_ids, allowed_names)
        analyses = ent.filter_rows(analyses, allowed_brand_ids, allowed_names)
        formation = analyses.get("formation")
        sn = analyses.get("signal_noise")
        funding = analyses.get("funding")
        hiring = analyses.get("hiring")
        sov = analyses.get("share_of_voice")
        pc = ent.filter_rows(pc, allowed_brand_ids, allowed_names)
        voices = ent.filter_rows(voices, allowed_brand_ids, allowed_names)
        dataset = ent.filter_rows(dataset, allowed_brand_ids, allowed_names)
        articles = ent.drop_text_mentioning(articles, withheld)
        # An investor row lists the vendors it backs as a plain list of
        # names, which filter_rows cannot see. The first overlap on market 2
        # (one investor behind two vendors outside the ten) named both and
        # tripped the fail-closed check, so the whole page was a 500. Keep
        # the fact — this investor backs N vendors — and withhold the names.
        if funding and funding.get("shared_investors"):
            funding["shared_investors"] = [
                {**i, "backing": _mask_names(i.get("backing") or [], allowed_names)}
                for i in funding["shared_investors"]]
        if joblist:
            joblist["data"] = ent.filter_rows(joblist.get("data") or [],
                                              allowed_brand_ids, allowed_names)
        # The assessment was computed from the allowed vendors, but a
        # development's headline can still name a partner we withhold.
        for key in ("developments", "main_developments", "other_developments",
                    "discussion"):
            assessment[key] = ent.drop_text_mentioning(
                assessment.get(key) or [], withheld)
        assessment["findings"] = ent.drop_text_mentioning(
            assessment.get("findings") or [], withheld)
        assessment["synthesis"] = ent.drop_text_mentioning(
            assessment.get("synthesis") or [], withheld)

    developments = assessment["developments"]
    devs_by_id = {d["event_id"]: d for d in developments}
    observation = assessment["observation"]
    vendor_state = {v["vendor"]: v for v in observation.get("vendors") or []}

    vendor_names = [d["vendor"] for d in dataset]
    clustered = mcorp.cluster(articles, vendor_names) if articles else []

    # Per-vendor, from the developments: when a vendor last moved and how
    # often, for the registry's sort and its columns.
    last_material: Dict[str, str] = {}
    announced: Dict[str, int] = {}
    for d in developments:
        for v in d.get("vendors") or []:
            name = v.get("vendor")
            if not name:
                continue
            if (d.get("date") or "") > last_material.get(name, ""):
                last_material[name] = d.get("date") or ""
            announced[name] = announced.get(name, 0) + 1

    generated = datetime.now(timezone.utc)
    body: List[str] = [f"<style>{EXTRA_CSS}{NEWS_CSS}</style>"]

    period_range = _fmt_range(*pc["current_range"]) if pc else None
    period_txt = (period_range or f"last {days} days")
    vendor_count = (overview["coverage"]["registry"]
                    - overview["coverage"]["excluded"])
    registry_total = vendor_count

    sov_block = sov or {}
    earned = int(sov_block.get("earned_total") or 0)
    earned_note = ""
    jobs_total = int(((joblist or {}).get("meta") or {})
                     .get("pagination", {}).get("total") or 0)
    jobs_meta = ((joblist or {}).get("meta") or {}).get("metric") or {}
    # reader_notes, not notes: the operator notes say how often we have
    # checked a vendor, which is not something a customer needs to read.
    jobs_notes = ((joblist or {}).get("meta") or {}).get("reader_notes") or []

    # ================================================================
    # The lead
    # ================================================================
    body.append('<div class="mm-news">')
    body.append('<div class="n-top">'
                + _brand_line()
                + '<nav class="n-jump" aria-label="Jump to section">'
                '<a href="#mm-horizon">Horizon</a>'
                '<a href="#mm-assessment">Assessment</a>'
                '<a href="#mm-moved">Who moved</a>'
                '<a href="#mm-developments">Developments</a>'
                '<a href="#mm-analysis">Evidence</a>'
                '<a href="#mm-registry">Vendors</a>'
                '<a href="#mm-method">Method</a></nav>'
                '<nav class="n-pages" aria-label="Pages">'
                f'<a href="?{_relink(link_params, days=days, view="news")}">News river</a>'
                + (f'<a class="n-rss" href="feed.xml?days={days}" title="Subscribe in a feed reader">RSS</a>'
                   if market.get("is_public") else "")
                + '</nav>'
                f'<span class="n-market">{esc(market["name"])}</span></div>')

    body.append('<main class="n-main"><span id="mm-overview"></span>')
    periods = "".join(
        f'<a href="?{_relink(link_params, days=d)}"'
        + (' aria-current="page"' if d == days else "")
        + f'>{d} days</a>' for d in (7, 30, 90))
    question = (market.get("question") or "").strip()
    scope_text = (market.get("market_scope_description") or "").strip()
    body.append('<div class="n-head"><div>'
                f'<div class="n-kicker">Market monitor · {esc(period_txt)}</div>'
                f'<h1>{esc(market["name"])}: market assessment</h1>'
                + (f'<p class="n-sub"><strong>{esc(question[:400])}</strong></p>'
                   if question else "")
                + f'<p class="n-sub">{esc(scope_text[:500]) + " " if scope_text else ""}'
                f'{vendor_count} vendors, {esc(period_txt)}.</p></div>'
                f'<div><nav class="n-periods" aria-label="Reporting period">'
                f'{periods}</nav>'
                f'<div class="n-period">Generated '
                f'{generated.strftime("%d %B %Y, %H:%M UTC")}</div></div></div>')

    # 1. Executive assessment
    # ---- Market Horizon first: the map is the page's opening picture
    try:
        from app.services import market_horizon as mh
        stored = mh.latest(conn, market["id"], n=2)
    except Exception as exc:  # noqa: BLE001 — the report stands without it
        logger.warning("market horizon unavailable: %s", exc)
        stored = []
    horizon_html = ""
    if stored:
        horizon = mh.with_movement(stored[0], stored[1] if len(stored) > 1 else None)
        body.append(_drawer_open(
            "Market Horizon",
            f"Where {horizon['counts']['rated']} of the market's "
            f"{horizon['counts']['eligible']} vendors sit today: how big they "
            "are, and how fast they are moving.",
            anchor="mm-horizon", opened=True))
        # The horizon names every rated vendor in the shared view too — the
        # placement is the public draw; each vendor's inputs and the
        # not-rated names stay in the full report. The fail-closed check
        # below scans the page for withheld names, so this one section is
        # rendered apart and put back after the check (`public_names`).
        horizon_html = _horizon_section(horizon, allowed_names, public_names=True)
        body.append(_HORIZON_SLOT)
        body.append(_drawer_close())

    body.append('<section class="n-block" id="mm-assessment">'
                '<div class="n-sec-head"><h2>Executive assessment</h2>'
                f'<span class="n-updated">{len(assessment["findings"])} '
                'findings</span></div>')
    body.append(_render_findings(assessment["findings"], devs_by_id))
    body.append("</section>")

    # 1b. The latest approved briefing. The card names the period and gives
    # the summary sentences this reader may see; the text is behind the link
    # for a reader with a session, and behind the trial for anyone else.
    body.append(_render_briefing_card(conn, market, withheld=withheld,
                                      restricted=teaser,
                                      link_params=link_params))

    # 2. Vendors showing material change
    main_devs = assessment["main_developments"]
    other_devs = assessment["other_developments"]
    body.append('<section class="n-block" id="mm-moved">'
                '<div class="n-sec-head"><h2>Vendors showing material change</h2>'
                f'<span class="n-updated">{len(developments)} developments · '
                f'{observation["counts"].get("material_change", 0)} vendors'
                '</span></div>')
    body.append(_render_moved_table(main_devs))
    body.append(_render_other_developments(other_devs))
    body.append("</section>")

    # 3. What this says about the market
    body.append('<section class="n-block" id="mm-synthesis">'
                '<div class="n-sec-head"><h2>What this says about the market</h2>'
                '</div>')
    body.append(_render_synthesis(assessment["synthesis"]))
    body.append("</section>")

    # 4. The developments, with the observation states beside them
    body.append('<div class="n-grid"><section id="mm-developments">')
    # A feed reader carries no session, so the RSS link is only real on a
    # market that serves anonymously. Drawn inline: this file fetches nothing.
    rss = ""
    if market.get("is_public"):
        rss = (f'<a class="n-rss" href="feed.xml?days={days}" '
               'title="Subscribe in a feed reader">'
               '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" '
               'stroke-width="2" stroke-linecap="round" aria-hidden="true">'
               '<path d="M4 11a9 9 0 0 1 9 9"/><path d="M4 4a16 16 0 0 1 16 16"/>'
               '<circle cx="5" cy="19" r="1" fill="currentColor"/></svg>'
               '<span>RSS</span></a>')
    body.append('<div class="n-sec-head"><h2>Material market developments</h2>'
                f'<div class="n-sec-actions">{rss}'
                f'<span class="n-updated">{esc(period_txt)}</span></div></div>')
    collected = int(assessment.get("collected_records") or 0)
    body.append(f'<p class="n-distil">{collected:,} collected records &rarr; '
                f'{len(developments)} material development'
                f'{"" if len(developments) == 1 else "s"}</p>')
    body.append(_render_developments(developments))
    body.append(_render_corpus(clustered, collected=collected,
                               shown=len(articles)))
    body.append("</section>")

    body.append('<aside class="n-aside">')
    body.append(_render_observation(observation))
    body.append("</aside></div></main>")
    body.append('<div class="n-foot">' + _brand_line()
                + f'<span>{esc(market["name"])} · {esc(period_txt)}</span></div>')
    body.append("</div>")
    body.append(f"<script>{_NEWS_JS}</script>")
    if teaser:
        body.append(_trial_panel(market["id"]))

    # ================================================================
    # The evidence behind the conclusions, collapsed
    # ================================================================
    body.append(_drawer_open(
        "The evidence behind this",
        "The figures the assessment rests on: formation, funding and "
        "investors, hiring, headcount, the vendors' own announcements, "
        "sentiment, and who is talking.",
        anchor="mm-analysis"))

    body.append('<div class="mm-news n-plain">' + _news_metrics(
        headcount=headcount, jobs_total=jobs_total, jobs_new=0,
        jobs_state=(jobs_meta.get("data_state") or "healthy"),
        funding=funding, earned=earned, earned_note=earned_note,
        earned_prev=earned_prev, movers=movers,
        weekly=((overview.get("corpus") or {}).get("by_week") or []),
        started=started_txt) + "</div>")

    # ---- Market scope, where one has been written
    if scope_text:
        body.append(section_open("Market scope"))
        body.append(f'<p>{esc(scope_text)}</p>')
        if market.get("inclusion_criteria"):
            body.append(f'<p><strong>Included:</strong> '
                        f'{esc(market["inclusion_criteria"])}</p>')
        if market.get("exclusion_criteria"):
            body.append(f'<p><strong>Excluded:</strong> '
                        f'{esc(market["exclusion_criteria"])}</p>')
        body.append("</section>")

    if pc:
        body.append('<span id="mm-changed"></span>')
        body.append(section_open("Compared with the previous period"))
        if not pc.get("comparable"):
            body.append(
                '<p class="mm-src">'
                + (f'Collection began {esc(started_txt)}, so figures for '
                   'this period are a floor. ' if started_txt else "")
                + f'A comparison with the {days} days before'
                + (f' will be available from '
                   f'{esc(_day(pc["comparable_from"]))}'
                   if pc.get("comparable_from") else " is not yet possible")
                + '.</p>')
        else:
            labels_pc = {
                "_coverage": "Articles and posts", "launch": "Product launches",
                "partnership": "Partnerships", "customer": "Customer announcements",
                "funding": "Funding announcements", "acquisition": "Acquisitions",
                "hiring": "Posts about people joining", "_jobs": "Open roles",
            }
            order_pc = ("_coverage", "launch", "partnership", "customer",
                        "funding", "acquisition", "hiring", "_jobs")
            rows_pc = []
            for key in order_pc:
                cur, prev = pc["current"].get(key, 0), pc["previous"].get(key, 0)
                if cur == 0 and prev == 0:
                    continue
                if prev == 0:
                    change = "nothing to compare against"
                else:
                    d = cur - prev
                    change = f'{"+" if d > 0 else ""}{d}'
                rows_pc.append(
                    f'<tr><td>{esc(labels_pc[key])}</td>'
                    f'<td class="mm-num">{cur}</td>'
                    f'<td class="mm-num">{prev}</td>'
                    f'<td class="mm-src">{esc(change)}</td></tr>')
            if rows_pc:
                body.append(f'<p class="mm-src">'
                            f'{esc(_fmt_range(*pc["current_range"]))} against '
                            f'{esc(_fmt_range(*pc["previous_range"]))}. Where we '
                            'were not measuring something yet in the earlier '
                            'period, we say so rather than show it as a rise '
                            'from zero.</p>')
                body.append('<table class="mm-table"><thead><tr><th>Metric</th>'
                            '<th class="mm-num">Current</th>'
                            '<th class="mm-num">Previous</th><th>Change</th>'
                            "</tr></thead><tbody>" + "".join(rows_pc)
                            + "</tbody></table>")
        body.append("</section>")

    # ---- Market snapshot
    cov, fund = overview["coverage"], overview["funding"]
    corpus = overview.get("corpus") or {}
    with_year = ((formation or {}).get("coverage") or {}).get("measured") \
        or (formation or {}).get("vendors_in_scope") or 0
    body.append(section_open("Market snapshot"))
    body.append('<div class="mm-stats">')
    body.append(_stat("Vendors in this market",
                      str(cov["registry"] - cov["excluded"]),
                      f'{cov["watching"]} currently monitored'))
    body.append(_stat("Money raised, where disclosed",
                      _money(fund["total_musd"]),
                      f'{fund["disclosed"]} of '
                      f'{fund["disclosed"] + fund["undisclosed"]} vendors have '
                      'published a figure'))
    if formation and with_year:
        cutoff = massess._founding_cutoff()
        recent = sum(int(r.get("vendors") or 0)
                     for r in formation.get("founded_by_year") or []
                     if r.get("year") and int(r["year"]) >= cutoff)
        body.append(_stat(f"Founded since {cutoff}", str(recent),
                          f'of the {with_year} whose founding year we know'))
    body.append(_stat("Articles and posts collected",
                      str(corpus.get("recent", corpus.get("total", 0))),
                      f'over the {days} days covered here'))
    body.append("</div></section>")

    # ---- Market formation
    if formation:
        cutoff = massess._founding_cutoff()
        recent = sum(int(r.get("vendors") or 0)
                     for r in formation.get("founded_by_year") or []
                     if r.get("year") and int(r["year"]) >= cutoff)
        body.append(section_open("Market formation"))
        body.append(f'<p>{recent} of the {with_year} vendors with a known '
                    f'founding year were founded in {cutoff} or later.</p>')
        body.append(_coverage(formation.get("coverage")))
        body.append(_bar_chart(formation["founded_by_year"],
                               label_key="year", value_key="vendors"))
        body.append("<h3>Announcements per month</h3>")
        body.append(_coverage(formation.get("announcement_coverage")))
        body.append(_bar_chart(formation["announcements_by_month"],
                               label_key="month", value_key="signal",
                               colour="#30a46c"))
        body.append("</section>")

    # ---- Funding and investor activity
    if teaser:
        body.append(_teaser_open("Funding, hiring, headcount, announcements, "
                                 "sentiment and who is talking"))
    body.append(section_open("Funding and investor activity"))
    capital_devs = [d for d in developments
                    if d["event_type"] in ("funding", "acquisition")]
    if capital_devs:
        body.append("<h3>Funding and acquisition events in the period</h3>")
        body.append('<table class="mm-table"><tbody>' + "".join(
            f'<tr><td><a href="#{_dev_anchor(d)}">{esc(d["headline"])}</a>'
            f'<div class="mm-src">{esc(d["event_type_label"])} · '
            f'{esc(_dev_date(d))} · {esc(d["provenance_label"])}</div></td></tr>'
            for d in capital_devs) + "</tbody></table>")
    else:
        body.append('<p class="mm-src">No funding round or acquisition was '
                    'observed in the period on the sources we collect. That '
                    'is what we saw, not a statement that none happened.</p>')
    top_funded = overview.get("top_funded") or []
    if top_funded:
        body.append("<h3>Disclosed funding</h3>")
        body.append(f'<p class="mm-src">{fund["disclosed"]} of '
                    f'{fund["disclosed"] + fund["undisclosed"]} vendors have a '
                    f'published total, adding to {_money(fund["total_musd"])}. '
                    'The best-funded of them:</p>')
        body.append('<table class="mm-table"><thead><tr><th>Vendor</th>'
                    '<th class="mm-num">Disclosed total</th><th>Last round</th>'
                    "</tr></thead><tbody>" + "".join(
            f'<tr><td>{esc(r.get("vendor") or "")}</td>'
            f'<td class="mm-num">{_money(float(r["musd"]) if r.get("musd") is not None else None)}</td>'
            f'<td class="mm-src">{esc(_stage_label(r.get("last_round")) if r.get("last_round") else "—")}</td></tr>'
            for r in top_funded[:10]) + "</tbody></table>")
    if funding:
        body.append("<h3>Funding stage across the market</h3>")
        body.append(_coverage(funding.get("coverage")))
        body.append(_bar_chart(
            [{**r, "stage": _stage_label(r.get("stage"))} for r in funding["stages"]],
            label_key="stage", value_key="vendors"))
        if funding.get("shared_investors"):
            body.append("<h3>Investors backing more than one vendor</h3>")
            body.append('<table class="mm-table"><tbody>' + "".join(
                f'<tr><td>{esc(i["investor"])}</td>'
                f'<td class="mm-src">{esc(", ".join(i["backing"]))}</td></tr>'
                for i in funding["shared_investors"]) + "</tbody></table>")
        # Crunchbase's own scores, as secondary data and labelled as theirs.
        # A level that did not move in the period is not a development.
        read_n = (funding.get("coverage") or {}).get("measured") or 0
        comparable = bool((pc or {}).get("comparable"))
        events = funding.get("momentum_events") or []
        body.append("<h3>Crunchbase scores</h3>")
        body.append('<p class="mm-src">Crunchbase\'s own Growth and '
                    'Attention (Heat) scores, 0 to 100, for reference.</p>')
        if comparable and events:
            body.append("<h4>Crunchbase score changes between two readings</h4>")
            body.append('<table class="mm-table"><thead><tr><th>Vendor</th>'
                        '<th class="mm-num">Attention/Heat Δ</th>'
                        '<th class="mm-num">Growth Δ</th><th>Last observed</th>'
                        "</tr></thead><tbody>" + "".join(
                f'<tr><td>{esc(e["vendor"])}</td>'
                f'<td class="mm-num">{_signed(e.get("heat_delta"))}</td>'
                f'<td class="mm-num">{_signed(e.get("growth_delta"))}</td>'
                f'<td class="mm-src">{esc((e.get("observed_at") or "")[:10])}</td>'
                "</tr>" for e in events[:15]) + "</tbody></table>")
        else:
            body.append(f'<p class="mm-src">Read for {read_n} of '
                        f'{registry_total} vendors. '
                        + ('Changes will appear after a full period of '
                           'readings.' if not comparable else
                           'No score changed in the period.') + '</p>')
        fm_with_data = [r for r in funding.get("by_month") or []
                        if r.get("avg_heat_score") is not None]
        if len(fm_with_data) >= 2:
            body.append("<h4>Crunchbase Growth and Attention scores, as of each month</h4>")
            body.append(_line_chart(
                funding["by_month"], x_key="month",
                series=[("avg_heat_score", "#475569", "Crunchbase Attention (Heat) score"),
                        ("avg_growth_score", "#30a46c", "Crunchbase Growth score")]))
    body.append("</section>")

    # ---- Hiring
    if hiring and hiring.get("openings"):
        body.append(section_open("Hiring"))
        body.append(f'<p>We found {hiring["openings"]} open roles across '
                    f'{len(hiring["by_vendor"])} vendors.</p>')
        top = hiring["by_vendor"]
        if len(top) >= 2:
            body.append(f'<p>{esc(top[0]["vendor"])} accounts for '
                        f'{top[0]["openings"]} of the {hiring["openings"]} '
                        f'observed openings, with {esc(top[1]["vendor"])} '
                        f'accounting for another {top[1]["openings"]}.</p>')
        body.append(_coverage(hiring.get("coverage")))
        body.append(_bar_chart(hiring["by_function"], label_key="function",
                               value_key="openings"))
        body.append("</section>")

    # ---- Headcount
    hc_trend = mp.headcount_trend(conn, market, weeks=26)
    hc_with_data = [p for p in hc_trend["points"]
                    if p.get("avg_pct_vs_baseline") is not None]
    if hc_with_data or (movers and movers.get("movers")):
        body.append(section_open("Headcount"))
        moved = [m for m in ((movers or {}).get("movers") or [])
                 if m.get("metric") == "Staff"]
        if moved:
            body.append("<h3>Vendors whose LinkedIn headcount moved</h3>")
            body.append('<table class="mm-table"><tbody>' + "".join(
                f'<tr><td>{esc(m.get("vendor") or "")}</td>'
                f'<td class="mm-num">{esc(m.get("value") or "")}</td>'
                f'<td class="mm-src">{esc(m.get("detail") or "")}</td></tr>'
                for m in moved[:10]) + "</tbody></table>")
        if hc_with_data:
            if len(hc_with_data) < 3:
                readings = "; ".join(
                    f'the week of {_day(p["week"])} at '
                    f'{"+" if p["avg_pct_vs_baseline"] > 0 else ""}'
                    f'{p["avg_pct_vs_baseline"]}%' for p in hc_with_data)
                body.append(f'<p>We have {len(hc_with_data)} week'
                            f'{"" if len(hc_with_data) == 1 else "s"} of '
                            f'readings so far: {esc(readings)} against where '
                            'these vendors started. Three weeks makes a line.</p>')
            else:
                body.append('<p class="mm-src">Average change from each '
                            "vendor's first reading. Weeks covering fewer "
                            f'than half of the {hc_trend["watching"]} vendors '
                            'are less reliable.</p>')
                body.append(_line_chart(
                    hc_trend["points"], x_key="week",
                    series=[("avg_pct_vs_baseline", "#475569",
                             "Average change since first reading")]))
        body.append("</section>")

    # ---- Vendor announcements
    if sn and sn.get("vendors"):
        totals = sn["totals"]
        body.append(section_open("Vendor announcements"))
        body.append(f'<p>{totals["signal"]} of '
                    f'{sum(totals.values())} collected vendor posts contained '
                    'a concrete company claim or announcement. The rest were '
                    'commentary, event promotion or other non-company '
                    'updates.</p>')
        body.append(_coverage(sn.get("coverage")))
        body.append(_stacked_chart(
            sn["vendors"][:20], label_key="vendor",
            series=[("signal", "#30a46c", "Concrete claim"),
                    ("commentary", "#8b93a1", "Commentary"),
                    ("noise", "#d4d8de", "No content")]))
        if sn.get("signal_kinds"):
            body.append("<p>" + " ".join(
                f'<span class="mm-kind">{esc(k["kind"])} {k["n"]}</span>'
                for k in sn["signal_kinds"]) + "</p>")
        body.append("</section>")

    # ---- Sentiment
    partial_weeks = {w.get("week") for w in (corpus.get("by_week") or [])
                     if w.get("partial")}
    sentiment_trend = [r for r in (corpus.get("sentiment_trend") or [])
                       if r.get("week") not in partial_weeks]
    if any(r.get("net_all") is not None for r in sentiment_trend):
        body.append(section_open("Sentiment"))
        latest_row = next(
            (r for r in reversed(sentiment_trend)
             if r.get("net_all") is not None), None)
        if latest_row:
            body.append(_reading(
                latest_row["net_all"],
                subject=(f'Coverage in the week of {_day(latest_row["week"])}, '
                         'the latest complete week,')))
        body.append('<p class="mm-src">Share of articles classed positive '
                    'minus share classed negative, by week. Weeks with too '
                    'few classified articles are left blank.</p>')
        vendor_points = sum(1 for r in sentiment_trend
                            if r.get("net_vendor") is not None)
        series = [("net_broad", "#475569", "The market as a whole")]
        if vendor_points >= 3:
            series.append(("net_vendor", "#30a46c", "Coverage of these vendors"))
        body.append(_line_chart(sentiment_trend, x_key="week", series=series))
        body.append("</section>")

    # ---- Who is being heard
    body.append(section_open("Who is being heard"))
    active = overview.get("most_active") or []
    scored = [v for v in active if v.get("activity_index") is not None]
    top = (scored or active)[:ACTIVITY_TOP_N]
    if top:
        body.append("<h3>Most active vendors</h3>")
        body.append(
            f'<p class="mm-src">Ranked on LinkedIn posts, open roles and '
            f'outside articles in the last {days} days; the score averages '
            'the three ranks. Only vendors measured on all three are '
            'scored.</p>')
        if scored:
            body.append(_bar_chart(top, label_key="vendor",
                                   value_key="activity_index"))
        body.append(
            '<table class="mm-table"><thead><tr><th>Vendor</th>'
            '<th class="mm-num">Score</th>'
            '<th class="mm-num">Own posts</th>'
            '<th class="mm-num">Open roles</th>'
            '<th class="mm-num">Written about</th></tr></thead><tbody>'
            + "".join(_activity_row(v) for v in top)
            + "</tbody></table>")
        unscored = sum(1 for v in active if v.get("activity_index") is None)
        if unscored:
            body.append(
                f'<p class="mm-src">{unscored} vendor'
                f'{"" if unscored == 1 else "s"} unscored: one of the three '
                'could not be measured.</p>')
    if sov and not sov.get("error") and sov.get("vendors"):
        earned_rows = sorted(
            [v for v in sov["vendors"] if v.get("earned")],
            key=lambda v: v.get("earned_share") or 0, reverse=True)
        if earned_rows and sov.get("earned_share_reliable"):
            body.append("<h3>Share of voice</h3>")
            body.append(f'<p class="mm-src">How {sov["earned_total"]} '
                        'mentions by people outside these companies were '
                        "split between them. The vendors' own posts are "
                        'counted separately.</p>')
            body.append(_bar_chart(
                [{"vendor": v["vendor"], "pct": round((v["earned_share"] or 0) * 100)}
                 for v in earned_rows],
                label_key="vendor", value_key="pct", colour="#30a46c"))
        loud_rows = [v for v in sov.get("vendors") or []
                     if v.get("reactions_per_post") is not None]
        if loud_rows:
            body.append("<h3>Posts and response</h3>")
            body.append('<p class="mm-src">Vendors with fewer than five posts '
                        'are left out.</p>')
            loud_rows = sorted(loud_rows, key=lambda v: v["own_posts"], reverse=True)
            body.append('<table class="mm-table"><thead><tr><th>Vendor</th>'
                        '<th class="mm-num">Posts</th>'
                        '<th class="mm-num">Reactions/post</th>'
                        '<th class="mm-num">Mentions by others</th>'
                        "</tr></thead><tbody>" + "".join(
                f'<tr><td>{esc(v["vendor"])}</td>'
                f'<td class="mm-num">{v["own_posts"]}</td>'
                f'<td class="mm-num">{v["reactions_per_post"]}</td>'
                f'<td class="mm-num">{v["earned"]}</td></tr>'
                for v in loud_rows[:20]) + "</tbody></table>")
    consistent = (voices or {}).get("consistent") or []
    if consistent:
        body.append("<h3>Accounts posting repeatedly about the market</h3>")
        body.append(f'<p class="mm-src">Accounts with at least '
                    f'{(voices or {}).get("consistent_min_posts", 3)} posts in '
                    "the period. Vendors' LinkedIn company posts are counted "
                    "elsewhere; a vendor's own account here is marked as one.</p>")
        body.append('<table class="mm-table"><thead><tr><th>Account</th>'
                    '<th>Who</th><th>Platform</th><th class="mm-num">Posts</th>'
                    '<th class="mm-num">Reactions</th><th>Latest post</th>'
                    "</tr></thead><tbody>" + "".join(
            _voice_row(v) for v in consistent[:20]) + "</tbody></table>")
    elif voices and voices.get("voices"):
        body.append('<p class="mm-src">No outside account posted about the '
                    'market more than once or twice in the period.</p>')
    if highlights:
        body.append("<h3>Outside voices, quoted</h3>")
        for h in highlights[:3]:
            meta = " · ".join(x for x in (
                f'@{h.get("author")}' if h.get("author") else "",
                h.get("platform") or "",
                (f'{h["engagement"]:,} reactions, comments and reposts'
                 if h.get("engagement") else "no measured response")) if x)
            quote = _clip(h.get("quote") or "", 190)
            link = (f'<a href="{esc(h["uri"])}">&ldquo;{esc(quote)}&rdquo;</a>'
                    if h.get("uri") else f'&ldquo;{esc(quote)}&rdquo;')
            body.append(f'<p class="mm-src">{esc(meta)}</p><p>{link}</p>')
    body.append("</section>")

    # ---- What people are saying: the discussion that became no development
    discussion_rows = assessment.get("discussion") or []
    if discussion_rows:
        body.append(section_open("What people are saying"))
        body.append('<p class="mm-src">Practitioner and analyst discussion '
                    'of the market, not vendor news.</p>')
        body.append('<table class="mm-table"><tbody>'
                    + "".join(_coverage_row(a) for a in discussion_rows[:20])
                    + "</tbody></table>")
        body.append("</section>")

    # ================================================================
    # The registry
    # ================================================================
    def _tracked(r: Dict[str, Any]) -> bool:
        if r.get("role") == "excluded" or not r.get("collecting"):
            return False
        if r.get("last_observed"):
            return True
        return any(int(r.get(k) or 0) for k in
                   ("articles_attributed", "open_jobs", "posts_30d"))

    candidates = [r for r in dataset if r.get("role") != "excluded"]
    registry_rows = [r for r in candidates if _tracked(r)]
    left_out = len(candidates) - len(registry_rows)
    state_order = {"material_change": 0, "monitored_no_material_change": 1,
                   "incomplete_coverage": 2, "not_yet_collected": 3, "paused": 4}
    def _registry_key(r: Dict[str, Any]) -> tuple:
        state = (vendor_state.get(r["vendor"]) or {}).get("state")
        latest = last_material.get(r["vendor"], "").replace("-", "")[:8]
        return (state_order.get(state, 9),
                -int(latest) if latest.isdigit() else 0, r["vendor"])

    registry_rows.sort(key=_registry_key)
    if teaser:
        body.append(_TEASER_END)
    body.append(_drawer_close())

    body.append(_drawer_open(
        "The vendors we track",
        f"{len(registry_rows)} companies we watch, with each one's "
        "observation state, country, founding year, staff, funding and open "
        "roles.",
        anchor="mm-registry"))
    body.append(section_open("Vendor registry"))
    body.append('<p><a class="mm-btn" href="#mm-missing">Is your company missing?</a></p>')
    body.append('<p class="mm-src">Sorted by observation state, then by the '
                "date of each vendor's latest development, then by name."
                + (f' {left_out} vendor{"" if left_out == 1 else "s"} on the '
                   'list are not shown, because collection is off for them or '
                   'we have never read anything about them.' if left_out else "")
                + '</p>')
    body.append('<table class="mm-table"><thead><tr>'
                "<th>Vendor</th><th>Observation</th><th>Country</th>"
                "<th>Founded</th>"
                '<th class="mm-num">LinkedIn headcount</th>'
                '<th class="mm-num">Disclosed funding</th>'
                f'<th class="mm-num">Developments, {days}d</th>'
                '<th class="mm-num">Open roles</th>'
                "<th>Latest development</th></tr></thead><tbody>")
    short_state = {"material_change": "Changed",
                   "monitored_no_material_change": "No change observed",
                   "incomplete_coverage": "Incomplete",
                   "paused": "Paused", "not_yet_collected": "Not collected"}
    for i, row in enumerate(registry_rows):
        raised = row.get("total_funding_musd")
        watched = bool(row.get("collecting"))
        jobs_cell = str(row.get("open_jobs") or 0) if watched else "—"
        st = vendor_state.get(row["vendor"]) or {}
        state = st.get("state") or ""
        label = short_state.get(state, state or "—")
        reasons = "; ".join(st.get("reasons") or [])
        last_sig = last_material.get(row["vendor"], "")
        row_html = (
            f'<tr><td>{esc(row["vendor"])}</td>'
            f'<td class="mm-src" title="{esc(reasons)}">{esc(label)}</td>'
            f'<td>{esc(row.get("country") or "—")}</td>'
            f'<td>{esc(str(row.get("founded_year") or "—"))}</td>'
            f'<td class="mm-num">{esc(str(row.get("headcount_linkedin") or row.get("headcount_workbook") or "—"))}</td>'
            f'<td class="mm-num">{_money(raised) if raised else esc(row.get("funding_status") or "—")}</td>'
            f'<td class="mm-num">{announced.get(row["vendor"], 0) if watched else "—"}</td>'
            f'<td class="mm-num">{esc(jobs_cell)}</td>'
            f'<td class="mm-src">{esc(last_sig[:10]) if last_sig else "—"}</td></tr>')
        body.append(_teaser_row(row_html)
                    if teaser and i >= TEASER_REGISTRY_ROWS else row_html)
    body.append("</tbody></table>"
                '<p class="mm-src">A dash under developments or open roles '
                'means collection is paused for that vendor.</p>'
                + ((f'<p class="mm-src">Rows after the first {TEASER_REGISTRY_ROWS} '
                    'are blurred in this shared view. <a href="#mm-trial">Request a '
                    'trial</a> for the full registry.</p>') if teaser else "")
                + "</section>")

    # ================================================================
    # How this was measured
    # ================================================================
    body.append(_drawer_close())
    body.append(_missing_panel(market["id"], market["name"]))
    body.append(_drawer_open(
        "How this was measured",
        "Which sources we read, how much of the market each one reached, what "
        "every figure counts, and the records behind it.",
        anchor="mm-method"))
    if teaser:
        body.append(_teaser_open("Coverage figures"))
    body.append(section_open("How much of the market we checked"))
    body.append(
        "<p>Per source: vendors it could read, set up for it, attempted, and "
        "read successfully.</p>")
    body.append('<table class="mm-table"><thead><tr><th>Source</th>'
                '<th>State</th>'
                '<th class="mm-num">Eligible</th>'
                '<th class="mm-num">Configured</th>'
                '<th class="mm-num">Attempted</th>'
                '<th class="mm-num">Collected</th><th>Notes</th>'
                "</tr></thead><tbody>")
    # A source nobody has set up for any vendor is not a measurement of the
    # market. Listing it as a row of zeros beside the sources we read makes
    # the table look like it is reporting on broken collectors. It is named
    # once below the table instead, so the reader still knows what the
    # figures do not cover.
    not_covered = []
    for src in assessment.get("source_coverage") or []:
        if src.get("state") == "not_configured":
            not_covered.append(src)
            continue
        body.append(
            f'<tr><td>{esc(src["name"])}</td>'
            f'<td>{esc(src.get("state_label") or "")}</td>'
            f'<td class="mm-num">{src["eligible"]} / {src["registry_total"]}</td>'
            f'<td class="mm-num">{src["configured"]}</td>'
            f'<td class="mm-num">{src["attempted"]}</td>'
            f'<td class="mm-num">{src["successful"]}</td>'
            f'<td class="mm-src">{esc(src.get("note") or "")}</td></tr>')
    body.append("</tbody></table>")
    if not_covered:
        body.append('<p class="mm-src">Not read for this market: '
                    + "; ".join(f'{esc(s["name"])} ({esc(s["note"])})' if s.get("note")
                                else esc(s["name"]) for s in not_covered)
                    + ".</p>")
    body.append('<table class="mm-table"><thead><tr><th>Coverage</th>'
                '<th class="mm-num">Vendors</th><th class="mm-num">%</th>'
                "</tr></thead><tbody>")
    body.append(_pct_row("Being watched", cov["watching"], registry_total))
    if cov.get("paused"):
        body.append(_pct_row("Paused", cov["paused"], registry_total))
    body.append(_pct_row("We have seen something from", cov["observed"], registry_total))
    if formation and formation.get("announcement_coverage"):
        ac = formation["announcement_coverage"]
        body.append(_pct_row("Posting on LinkedIn in the period",
                             ac["measured"], ac["total"]))
    if funding and funding.get("coverage"):
        fc = funding["coverage"]
        body.append(_pct_row("Crunchbase profile read", fc["measured"], fc["total"]))
    if hiring and hiring.get("coverage"):
        hc = hiring["coverage"]
        # hiring["coverage"] counts vendors with at least one listing in the
        # window, not vendors whose board we read. Labelled "Job boards read"
        # it sat under a table row saying 82 boards were read and showed 20.
        body.append(_pct_row("Have job listings we have seen",
                             hc["measured"], hc["total"]))
    body.append("</tbody></table>")
    counts = observation.get("counts") or {}
    body.append(
        f'<p class="mm-src">Of the {registry_total} vendors, '
        f'{counts.get("material_change", 0)} showed a material change, '
        f'{counts.get("monitored_no_material_change", 0)} were monitored with '
        f'no material change observed, {counts.get("incomplete_coverage", 0)} '
        'were observed incompletely'
        + (f', {counts.get("paused", 0)} are paused' if counts.get("paused") else "")
        + (f' and {counts.get("not_yet_collected", 0)} have not been collected yet'
           if counts.get("not_yet_collected") else "")
        + '.</p>')
    body.append("</section>")

    if teaser:
        body.append(_TEASER_END)
    body.append(section_open("About this report"))
    body.append(
        "<p>Aunoo matches everything it collects against the phrases that "
        "define this market and the names of its vendors. Company and funding "
        "details come from LinkedIn and Crunchbase.</p>"
        + (f"<p>Collection began {esc(started_txt)}; anything dated earlier "
           "was collected afterwards as backlog.</p>" if started_txt else "")
        + "<p>A development is one event, however many records discuss it: "
        "records about the same vendor and the same kind of event, within "
        "two weeks of each other, sharing a name or subject, are merged and "
        "all stay linked under it. &ldquo;Reported independently&rdquo; "
        "means another source carried the same event, not that anyone "
        "verified it.</p>")
    body.append("</section>")

    body.append(section_open("Where the numbers come from"))
    body.append("<h3>Which sources we use</h3>")
    body.append("<p>Each source, where it is published, and the provider "
                "we get it through.</p>")
    body.append('<table class="mm-table"><thead><tr>'
                "<th>What</th><th>Published on</th>"
                "<th>We get it from</th><th>Whose words</th>"
                "</tr></thead><tbody>")
    for row in mmet.SOURCE_LEGEND:
        body.append(f'<tr><td>{esc(row["content"])}</td>'
                    f'<td>{esc(row["platform"])}</td>'
                    f'<td>{esc(row["provider"])}</td>'
                    f'<td>{esc(row["ownership"])}</td></tr>')
    body.append("</tbody></table>")
    if jobs_notes:
        body.append("<h3>How the job figures were assembled</h3>")
        body.append("<ul>" + "".join(f"<li>{esc(n)}</li>"
                                     for n in jobs_notes) + "</ul>")
    body.append("<h3>What each figure counts</h3>")
    seen_metrics = set()
    for meta in _metric_blocks(overview, analyses, headcount):
        if not meta or meta.get("metric_id") in seen_metrics:
            continue
        seen_metrics.add(meta["metric_id"])
        body.append(f'<h4>{esc(meta["label"])}</h4>')
        body.append(f'<p>{esc(meta["definition"])}</p>')
        bits = [f'Counts {esc(meta["numerator"])}']
        if meta.get("denominator"):
            bits.append(f'out of {esc(meta["denominator"])}')
        if (meta.get("window") or {}).get("days"):
            bits.append(f'over the last {meta["window"]["days"]} days')
        note = meta.get("state_detail_public") or meta.get("state_detail") or ""
        note = (note[0].upper() + note[1:].rstrip(".") + ".") if note else ""
        body.append(f'<p class="mm-src">{", ".join(bits)}. {esc(note)}</p>')
        if meta.get("limitations"):
            body.append("<ul>" + "".join(
                f"<li>{esc(l)}</li>" for l in meta["limitations"]) + "</ul>")
    body.append("<h3>Post classification</h3>")
    body.append(
        "<p>Vendor posts are classed as <strong>announcement</strong> (a "
        "company event or verifiable update), <strong>commentary</strong> "
        "(interpretation or educational material), <strong>promotion</strong> "
        "(marketing with no event in it) or <strong>unreviewed</strong>.</p>")
    body.append("<h3>How developments are chosen</h3>")
    body.append(
        "<p>A development is an acquisition, funding, product launch or "
        "expansion, partnership, customer or deployment, executive "
        "appointment, hiring above a floor, headcount change, or a market "
        "entry or exit. A vendor's own post counts when the review pass "
        "judged it a concrete announcement; a third-party page counts when "
        "its headline says so and it names a tracked vendor. Practitioner "
        "posts attach as evidence to a development or are listed as "
        "discussion. Job-seeking posts, course completions, adverts and "
        "market-size reports are filtered out.</p>")
    body.append("</section>")
    body.append(_drawer_close())

    if allowed_brand_ids is not None:
        from sqlalchemy import text as _sql

        total = conn.execute(_sql("""
            SELECT COUNT(*) FROM bw_market_brands
             WHERE market_id = :m AND role <> 'excluded'
        """), {"m": market["id"]}).scalar() or 0
        body.append(
            '<p class="mm-src">This is a shared view. It covers the '
            f'{len(allowed_brand_ids)} most active of the {total} vendors we '
            'watch, and leaves the rest out. Figures that cover the whole '
            'market say so. <a href="#mm-trial">Request a trial</a> to see '
            'all of it.</p>')

    rendered = html_document(f'{market["name"]} — Market Monitor',
                             "".join(body))
    if teaser:
        rendered = _apply_teasers(rendered)

    # Fail closed. Serving a page that names a vendor the viewer is not
    # entitled to see cannot be undone, and a refusal can.
    ent.assert_no_withheld(rendered, withheld,
                           context=f'market {market["id"]} report')

    # The one deliberate exception, put back after the check: the Market
    # Horizon names every rated vendor by decision (27 August 2026).
    rendered = rendered.replace(_HORIZON_SLOT, horizon_html)

    return rendered.encode("utf-8")


def _metric_blocks(overview: Dict[str, Any], analyses: Dict[str, Any],
                   headcount: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Every metric block carried by the payloads this report already renders.

    Collected by walking what is there rather than naming each one, so a metric
    added to an aggregate shows up in the methodology appendix without anyone
    having to remember to list it here.
    """
    out: List[Dict[str, Any]] = []
    for payload in [overview, headcount] + list((analyses or {}).values()):
        if not isinstance(payload, dict):
            continue
        for key, value in payload.items():
            if key == "metric" and isinstance(value, dict):
                out.append(value)
            elif key.endswith("_metric") and isinstance(value, dict):
                out.append(value)
    return out
