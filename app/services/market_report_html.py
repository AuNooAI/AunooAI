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
import math
import logging
import os
import re
from urllib.parse import urlparse
from datetime import datetime, timedelta, timezone
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
#: The type saas.aunoo.ai uses (``--aunoo-font``); the news pages load it
#: themselves because the report shell is system type.
_FONT_LINK = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
              '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
              '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=DM+Sans:'
              'wght@400;500;600;700&display=swap">')
#: The front page's type (aunoo-aisocnews-design-system.md §3): Geist for
#: headings, labels and numbers, Literata for the prose a person reads. One
#: request, both as variable fonts.
_FONT_LINK_V2 = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
                 '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
                 '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Geist:'
                 'wght@400..700&family=Literata:opsz,wght@7..72,400..600&display=swap">')

#: Theme: light is declared in the markup so there is no flash; a stored
#: choice is applied before the page paints, and the 36px icon button in the
#: bar switches it. prefers-color-scheme is deliberately not consulted.
_THEME_JS = """
(function(){var k='aisocnews-theme',t=null;try{t=localStorage.getItem(k);}catch(e){}
if(t==='dark'||t==='light'){document.documentElement.setAttribute('data-theme',t);}
function sync(){var d=document.documentElement.getAttribute('data-theme')==='dark';
var bs=document.querySelectorAll('.n-theme');for(var i=0;i<bs.length;i++){bs[i].setAttribute('aria-pressed',d?'true':'false');
bs[i].setAttribute('aria-label',d?'Switch to light theme':'Switch to dark theme');}}
document.addEventListener('click',function(e){var b=e.target.closest?e.target.closest('.n-theme'):null;if(!b)return;
var n=document.documentElement.getAttribute('data-theme')==='dark'?'light':'dark';
document.documentElement.setAttribute('data-theme',n);try{localStorage.setItem(k,n);}catch(e2){}sync();});
if(document.readyState!=='loading')sync();else document.addEventListener('DOMContentLoaded',sync);})();
"""


def _theme_toggle() -> str:
    """The icon-only theme button for the chrome bar. Shows the icon of the
    mode it switches *to*; the script keeps aria-label and aria-pressed true."""
    stroke = ('fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
              'stroke-linejoin="round" aria-hidden="true"')
    return ('<button type="button" class="n-theme" aria-label="Switch to dark theme" aria-pressed="false">'
            f'<svg class="n-theme-moon" viewBox="0 0 24 24" {stroke}>'
            '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>'
            f'<svg class="n-theme-sun" viewBox="0 0 24 24" {stroke}><circle cx="12" cy="12" r="5"/>'
            '<path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2'
            'M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg></button>')


def v2_document(title: str, body: str) -> str:
    """``html_document`` for a page of the front-page site: the light theme
    declared on <html>, and the theme script first in the body so a stored
    dark choice applies before anything paints."""
    rendered = html_document(title, f"<script>{_THEME_JS}</script>" + body)
    return rendered.replace('<html lang="en">', '<html lang="en" data-theme="light">', 1)

NEWS_CSS = """
.mm-news { font-family:"DM Sans", Inter, system-ui, sans-serif;
           --n-bg:#f7f6f2; --n-shell:#fff; --n-panel:#fff; --n-text:#211f26;
           --n-muted:#65636d; --n-line:#dbd8e0; --n-accent:#c2298a;
           --n-accent-soft:#fee9f5; --n-blue:#0d74ce; --n-green:#218358;
           --n-orange:#cc4e00; --n-purple:#6550b9;
           margin:0 0 1.6rem; border:1px solid var(--n-line); border-radius:14px;
           overflow:hidden; background:var(--n-bg); color:var(--n-text); }
.mm-news * { box-sizing:border-box; }
/* Dark bar: the Cyberfuturists mark is drawn for a dark ground. */
.mm-news .n-top { display:flex; align-items:center; gap:12px 20px; padding:14px 18px;
                  flex-wrap:wrap;
                  background:#1a1523; color:#f2eff3; border-bottom:1px solid #2d2a37; }
.mm-news .n-brand { display:flex; align-items:center; gap:9px; font-weight:500;
                    white-space:nowrap; }
.mm-news .n-brand a { color:inherit; text-decoration:none; }
.mm-news .n-brand a:hover { color:var(--n-accent); }
.mm-news .n-brand-made { font-weight:400; color:#bcbac7; font-size:.85rem; }
.mm-news .n-mark { display:block; height:36px; width:auto; }
.mm-news .n-brand-made .n-mark { height:22px; }
.mm-news .n-foot { display:flex; align-items:center; justify-content:space-between;
                   gap:14px; padding:14px 18px; border-top:1px solid #2d2a37;
                   background:#1a1523; color:#f2eff3; font-size:.82rem;
                   flex-wrap:wrap; }
.mm-news .n-foot > span:last-child { color:#bcbac7; }
/* The section links take the whole second row: with the two brand marks, the
   page links and the market name on the first, they never fit beside them
   and were wrapping into a column. */
.mm-news .n-jump { display:flex; gap:4px; flex:1 1 100%; order:10; flex-wrap:wrap; }
.mm-news .n-jump a { border-radius:7px; padding:6px 10px; color:#bcbac7;
                     text-decoration:none; font-size:.82rem; }
.mm-news .n-jump a:hover { background:#2d2a37; color:#fff; }
.mm-news .n-market { color:#bcbac7; white-space:nowrap; font-size:.85rem; }
.mm-news .n-jump-page { border:1px solid #65636d; }
/* Page links and the feed: never hidden, whatever the width. */
.mm-news .n-pages { display:flex; align-items:center; gap:6px; margin-left:auto; }
.mm-news .n-pages a { border-radius:7px; padding:6px 10px; color:#bcbac7;
                      border:1px solid #65636d; font-size:.82rem; white-space:nowrap; }
.mm-news .n-pages a:hover { background:#2d2a37; color:#fff; }
/* Schedule an inquiry: outlined in the accent, next to the filled Submit news. */
.mm-news .n-pages a.n-book { border-color:var(--n-accent); color:#fff; font-weight:600; }
.mm-news .n-pages a.n-book:hover { background:var(--n-accent); color:#fff; }
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
.mm-news .n-blur { filter:blur(5px); user-select:none; pointer-events:none; }
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
.mm-news .n-ai svg { color:var(--n-accent); }
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
.mm-drawer { max-width:1180px; margin:0 auto 10px; border:1px solid #dbd8e0;
             border-radius:10px; background:#fff; }
.mm-drawer > summary { list-style:none; cursor:pointer; padding:15px 20px;
                       display:flex; flex-direction:column; gap:3px; }
.mm-drawer > summary::-webkit-details-marker { display:none; }
.mm-drawer > summary::after { content:"Show"; position:absolute; right:24px;
                              font-size:12px; color:#84828e; }
.mm-drawer[open] > summary::after { content:"Hide"; }
.mm-drawer > summary { position:relative; }
.mm-drawer > summary:hover .mm-drawer-t { color:#0d74ce; }
.mm-drawer-t { font-size:15px; font-weight:500; color:#211f26; }
.mm-drawer-b { font-size:12.5px; color:#84828e; max-width:70ch; }
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
.mm-news .n-coverage { margin-top:6px; font-size:11.5px; color:#ab6400;
                       background:#fefbe9; border:1px solid #f3d673; border-radius:5px;
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
.mm-btn { display: inline-block; margin-top: .6rem; background: #211f26; color: #fff !important;
          border: 0; border-radius: 6px; padding: .5rem .9rem; font-size: .85rem;
          font-weight: 600; cursor: pointer; text-decoration: none !important; }
tr.mm-teaser-row td { filter: blur(5px); user-select: none; pointer-events: none; }
.mm-trial { background: #f7f6f2; border: 1px solid #dbd8e0; border-radius: 10px;
            padding: 1.1rem 1.25rem; margin: 1.2rem 0; }
.mm-trial h2 { margin: 0 0 .3rem; font-size: 1.05rem; }
.mm-trial p { margin: 0 0 .7rem; font-size: .9rem; color: #65636d; }
.mm-trial form { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
                 gap: .6rem; align-items: end; }
.mm-trial label { display: block; font-size: .72rem; color: #65636d; text-transform: uppercase;
                  letter-spacing: .05em; margin-bottom: .2rem; }
.mm-trial input { width: 100%; box-sizing: border-box; border: 1px solid #d0cdd7;
                  border-radius: 6px; padding: .45rem .55rem; font-size: .88rem; }
.mm-trial .mm-btn { margin-top: 0; }
.sr-only { position:absolute; width:1px; height:1px; overflow:hidden; clip:rect(0 0 0 0); white-space:nowrap; }
.mm-trial .mm-c-kind { grid-column: 1 / -1; }
.mm-trial select { width: 100%; max-width: 420px; box-sizing: border-box; border: 1px solid #d0cdd7;
                   border-radius: 6px; padding: .5rem .6rem; font: inherit; background: #fff; }
.mm-trial [hidden] { display: none; }
.mm-trial-msg { grid-column: 1 / -1; font-size: .85rem; color: #218358; min-height: 1em; }
.mm-trial-msg.err { color: #ce2c31; }
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
.mm-hz { position: relative; }
.mm-hz .mm-hz-dot { cursor: default; }
.mm-hz-switch { display: flex; gap: 4px; margin: 0 0 6px; }
.mm-hz-switch button { font: inherit; font-size: 12px; padding: 3px 10px; border: 1px solid #cbd5e1;
  border-radius: 999px; background: #fff; color: #475569; cursor: pointer; }
.mm-hz-switch button[aria-selected="true"] { background: #334155; border-color: #334155; color: #fff; }
.mm-hz-chips { display: inline-flex; gap: 4px; align-items: center; margin-left: 14px; font-size: 11px; color: #64748b; }
.mm-hz-chips button b { font-weight: 600; }
.mm-hz-chips button[aria-pressed="true"] { background: var(--mm-hl); border-color: var(--mm-hl); color: #fff; }
.mm-hz-pt.mm-dim { opacity: .3; }
.mm-hz-show { display: inline-flex; gap: 4px; align-items: center; margin-left: 14px; font-size: 11px; color: #64748b; }
.mm-hz-show button[aria-pressed="true"] { background: #334155; border-color: #334155; color: #fff; }
.mm-hz.mm-top .mm-hz-pt[data-tail], .mm-hz.mm-top .mm-hz-trail[data-tail] { display: none; }
.mm-hz.mm-top .mm-lbl-all, .mm-hz:not(.mm-top) .mm-lbl-top { display: none; }
.mm-hz-pt.mm-on .mm-core { fill: var(--mm-hl); fill-opacity: 1; }
.mm-hz-pt.mm-on .mm-lbl { font-weight: 600; }
.mm-hz-tip { position: absolute; z-index: 5; background: #fff; border: 1px solid #e2e8f0;
  border-radius: 6px; padding: 6px 9px; font-size: 12px; line-height: 1.35;
  box-shadow: 0 2px 8px rgba(15, 23, 42, .1); pointer-events: none; max-width: 19rem; }
.mm-hz-tip table { border-collapse: collapse; margin-top: 4px; font-size: 11px; }
.mm-hz-tip td { padding: 0 8px 0 0; }
.mm-hz-tip .mm-num { text-align: right; }
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


#: The JSON Feed for assistants, beside the RSS link: same items, JSON Feed 1.1.
_AI_FEED_LINK = ('<a class="n-rss n-ai" href="feed.json?days={days}" '
                 'title="JSON feed for AI assistants (JSON Feed 1.1)">' + '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 2l1.8 5.7L19.5 9.5l-5.7 1.8L12 17l-1.8-5.7L4.5 9.5l5.7-1.8z"/><path d="M19 14l.9 2.6 2.6.9-2.6.9L19 21l-.9-2.6-2.6-.9 2.6-.9z"/><path d="M5 15l.7 2 2 .7-2 .7L5 20.5l-.7-2-2-.7 2-.7z"/></svg>' + 'AI feed</a>')


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
# One slate tone per stage, light for Emerging through dark for Executing,
# so a dot shows its stage without a loud colour.
_TIER_COLOUR = {"emerging": "#94a3b8", "established": "#64748b",
                "innovators": "#475569", "executors": "#1e293b"}


def _horizon_tip(r: Dict[str, Any], tiers: Dict[str, Any], *, with_inputs: bool) -> str:
    """The hover panel for one dot: name, position, tier, markers, movement,
    and in the full view every reading behind it."""
    tier = (tiers.get(r.get("tier")) or {}).get("label") or (r.get("tier") or "").capitalize()
    band = f' · {esc(str(r["band"]))}' if r.get("band") else ""
    out = [f'<strong>{esc(r["vendor"])}</strong>',
           f'<div class="mm-src">scale {r["scale"]:g} · momentum {r["momentum"]:g} · {esc(tier)}{band}</div>']
    marks = []
    if r.get("innovating"):
        marks.append("innovating" + (f' (score {r["innovation"]:g})' if r.get("innovation") is not None else ""))
    if r.get("hiring") and r.get("hiring_detail"):
        d = r["hiring_detail"]
        marks.append(f'hiring — {int(d["open_roles"])} open roles, {float(d["per_100"]):.0f} per 100 staff')
    if r.get("funded"):
        f = r["funded"]
        marks.append(f'raised in the last year — {f.get("round") or "round not stated"}, {(f.get("date") or "")[:7]}')
    if marks:
        out.append("<div>" + "; ".join(esc(m) for m in marks) + "</div>")
    sh = r.get("shift")
    if sh and (abs(sh.get("scale", 0)) >= 1 or abs(sh.get("momentum", 0)) >= 1):
        out.append(f'<div class="mm-src">since previous map: {sh["scale"]:+g} scale, '
                   f'{sh["momentum"]:+g} momentum</div>')
    if with_inputs and r.get("inputs"):
        rows = "".join(
            f'<tr><td>{esc(k.replace("_", " "))}</td><td class="mm-num">{float(v["value"]):g}</td>'
            f'<td class="mm-num mm-src">p{float(v["percentile"]):.0f}</td></tr>'
            for k, v in r["inputs"].items())
        out.append(f'<table>{rows}</table>')
        if r.get("multipliers"):
            out.append('<div class="mm-src">analyst weights: ' + esc(", ".join(
                f"{k} ×{v:g}" for k, v in r["multipliers"].items())) + "</div>")
        if r.get("analyst_note"):
            out.append(f'<div class="mm-src">note: {esc(r["analyst_note"])}</div>')
    return "".join(out)


def _horizon_svg(rated: List[Dict[str, Any]], allowed: Optional[set],
                 cuts: Dict[str, Any], *, tiers: Optional[Dict[str, Any]] = None,
                 bands: Optional[Dict[str, Any]] = None, with_inputs: bool = False,
                 labels: Any = True, label_scale: float = 1.0) -> str:
    """Vendors on a semicircle. The angle is the stage, by scale: the
    smallest vendors on the left, the largest on the right, so a vendor's
    life runs left to right. The distance from the base is momentum: the
    outer band is accelerating, the inner band holding. Dashed lines from
    the base mark the stage cuts; dashed arcs mark the band cuts. Names
    only where the viewer may see them; the dots give nothing away.

    The grid in ``_horizon_grid_svg`` plots the same two scores on plain
    axes; the report offers both and the reader picks. ``labels`` is True
    for every name, False for none, or a number: the names of that many
    vendors, the largest and fastest first, for a copy of the map too small
    to carry them all. ``label_scale`` tells the placer how much larger
    than 11 px the page will draw the names, so they still keep apart."""
    from app.services.market_horizon import band_cuts, band_info, stage_cuts, tier_info
    w, h = 900, 532
    cx, cy, radius = w / 2, h - 72, 400
    cuts = cuts or {}
    def angle(scale: float) -> float:
        return math.radians(180 - 1.8 * max(0.0, min(100.0, scale)))
    def place(r: Dict[str, Any]):
        theta = angle(float(r["scale"]))
        d = radius * max(0.0, min(100.0, float(r["momentum"]))) / 100
        return cx + d * math.cos(theta), cy - d * math.sin(theta)
    def arc(frac: float) -> str:
        d = radius * frac
        return f'M {cx - d:.1f} {cy:.1f} A {d:.1f} {d:.1f} 0 0 1 {cx + d:.1f} {cy:.1f}'
    stage_names = {k: v["label"] for k, v in (tiers or tier_info(cuts)).items()}
    band_names = {k: v["label"] for k, v in (bands or band_info(cuts)).items()}
    parts = [f'<svg viewBox="0 0 {w} {h}" width="100%" style="max-width:{w}px" role="img" '
             'aria-label="Market Maturity Map: position and balance">',
             _horizon_arrow_def("mm-hz-arrow"),
             f'<path d="{arc(1.0)} Z" fill="#f8fafc" stroke="#e2e8f0"/>']
    # The band cuts are arcs; the stage cuts are lines from the base.
    b1, b2 = band_cuts(cuts)
    for frac in (b1 / 100, b2 / 100):
        parts.append(f'<path d="{arc(frac)}" fill="none" stroke="#cbd5e1" stroke-dasharray="4 4"/>')
    c1, c2, c3 = stage_cuts(cuts)
    for cut in (c1, c2, c3):
        t = angle(cut)
        parts.append(f'<line x1="{cx:.1f}" y1="{cy:.1f}" x2="{cx + radius * math.cos(t):.1f}" '
                     f'y2="{cy - radius * math.sin(t):.1f}" stroke="#cbd5e1" stroke-dasharray="4 4"/>')
    # Stage names run along the rim, each centred on its sector. Band names
    # go on the centre line just inside each arc; they are drawn after the
    # dots, with a halo, and the vendor labels keep off them.
    rim = radius + 9
    parts.append(f'<path id="mm-hz-rim" d="M {cx - rim:.1f} {cy:.1f} A {rim:.1f} {rim:.1f} 0 0 1 '
                 f'{cx + rim:.1f} {cy:.1f}" fill="none" stroke="none"/>')
    edges = [0.0, c1, c2, c3, 100.0]
    for k, key in enumerate(_STAGE_KEYS):
        parts.append(f'<text font-size="13" font-weight="600" fill="#334155" letter-spacing=".3">'
                     f'<textPath href="#mm-hz-rim" '
                     f'startOffset="{(edges[k] + edges[k + 1]) / 2:.1f}%" text-anchor="middle">'
                     f'{esc(stage_names.get(key) or key)}</textPath></text>')
        t = angle((edges[k] + edges[k + 1]) / 2)
        parts.append(_stage_icon(key, cx + (radius + 34) * math.cos(t), cy - (radius + 34) * math.sin(t)))
    # An arrow on the rim at each stage cut: a vendor's life runs left to right.
    for cut in (c1, c2, c3):
        parts.append(f'<text font-size="14" fill="#94a3b8"><textPath href="#mm-hz-rim" '
                     f'startOffset="{cut:.1f}%" text-anchor="middle">→</textPath></text>')
    # Each band name sits on its arc at the top, or failing a clear spot
    # there, at the nearest angle to the top that is clear of dots.
    # Dots closer than 13 px are nudged apart so each is visible; the
    # nudge is capped at 10 px from where the scores put the dot.
    order = sorted(rated, key=lambda r: -(r["scale"] + r["momentum"]))
    spread = dict(zip((r["brand_id"] for r in order), _spread([place(r) for r in order])))
    placed = [spread[r["brand_id"]] for r in rated]
    band_marks, band_text = [], []
    for key, frac in (("holding", b1 / 100), ("growing", b2 / 100), ("accelerating", 1.0)):
        word = (band_names.get(key) or key).lower()
        bw = _label_width(word) * 1.1
        best, best_gap = None, -1.0
        for deg in (90, 100, 80, 110, 70, 120, 60, 130, 50):
            t = math.radians(deg)
            px, py = cx + (radius * frac - 6) * math.cos(t), cy - (radius * frac - 6) * math.sin(t)
            gap = min([math.hypot(px - x, py - y) for x, y in placed] + [999.0])
            if gap > best_gap:
                best, best_gap = (px, py), gap
            if gap >= 28:
                break
        px, py = best
        band_marks.append((px - bw / 2, py - 6, bw, 12.0))
        band_text.append(_halo_text(px, py + 4, word))
    parts += ['<g class="mm-hz-axis">',
              f'<text x="{cx - radius:.0f}" y="{cy + 16:.0f}" font-size="11" fill="#64748b">← smaller by scale</text>',
              f'<text x="{cx + radius:.0f}" y="{cy + 16:.0f}" text-anchor="end" font-size="11" fill="#64748b">larger by scale →</text>',
              f'<text x="{cx:.0f}" y="{cy + 16:.0f}" text-anchor="middle" font-size="11" fill="#64748b">further from the base = more momentum</text>',
              '</g>']
    # The axis captions under the base are obstacles too, so a label that
    # drops below the base cannot land on them.
    captions = [(cx - radius, cy + 6, _label_width("← smaller by scale") * 1.1, 12.0),
                (cx + radius - _label_width("larger by scale →") * 1.1, cy + 6,
                 _label_width("larger by scale →") * 1.1, 12.0),
                (cx - _label_width("further from the base = more momentum") * 0.55, cy + 6,
                 _label_width("further from the base = more momentum") * 1.1, 12.0)]
    trails, dots_svg = _horizon_dot_layer(rated, allowed, order, spread, place,
                                          obstacles=band_marks + captions, width=w, max_y=cy + 26,
                                          tiers=tiers, with_inputs=with_inputs, arrow="mm-hz-arrow",
                                          labels=labels, label_scale=label_scale)
    parts += ['<g class="mm-hz-legend">'] + _horizon_legend(cx - 268, cy + 44, bool(trails)) + ['</g>']
    parts += trails + dots_svg + band_text
    parts.append("</svg>")
    return "".join(parts)


_STAGE_KEYS = ("emerging", "established", "innovators", "executors")

# One icon per stage (the designer's picks, from the Lucide set: a sprout,
# building blocks, a rising chart, a target), drawn as inline paths so the
# report needs no icon font. Stroke and size come from `_stage_icon`.
_STAGE_ICONS = {
    "emerging": '<path d="M7 20h10"/><path d="M10 20c5.5-2.5.8-6.4 3-10"/>'
                '<path d="M9.5 9.4c1.1.8 1.8 2.2 2.3 3.7-2 .4-3.5.4-4.8-.3-1.2-.6-2.3-1.9-3-4.2 2.8-.5 4.4 0 5.5.8z"/>'
                '<path d="M14.1 6a7 7 0 0 0-1.1 4c1.9-.1 3.3-.6 4.3-1.4 1-1 1.6-2.3 1.7-4.6-2.7.1-4 1-4.9 2z"/>',
    "established": '<rect width="7" height="7" x="14" y="3" rx="1"/>'
                   '<path d="M10 21V8a1 1 0 0 0-1-1H4a1 1 0 0 0-1 1v12a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-5a1 1 0 0 0-1-1H3"/>',
    "innovators": '<path d="M12 16v5"/><path d="M16 14v7"/><path d="M20 10v11"/>'
                  '<path d="m22 3-8.646 8.646a.5.5 0 0 1-.708 0L9.354 8.354a.5.5 0 0 0-.707 0L2 15"/>'
                  '<path d="M4 18v3"/><path d="M8 14v7"/>',
    "executors": '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/>',
}

# The three markers a reader can highlight, with the colour of their ring.
_MARKER_COLOURS = (("innovating", "#0f172a"), ("hiring", "#b45309"), ("funded", "#1d4ed8"))
#: The word the reader sees for each marker key. "funded" is a round dated
#: inside the last year, not a vendor that has ever raised, so it says so.
_MARKER_LABELS = {"innovating": "innovating", "hiring": "hiring", "funded": "raised in the last year"}


def _stage_icon(key: str, cx: float, cy: float, size: float = 16) -> str:
    """The stage's icon centred on (cx, cy)."""
    return (f'<svg x="{cx - size / 2:.1f}" y="{cy - size / 2:.1f}" width="{size:g}" height="{size:g}" '
            'viewBox="0 0 24 24" fill="none" stroke="#334155" stroke-width="2" '
            f'stroke-linecap="round" stroke-linejoin="round">{_STAGE_ICONS[key]}</svg>')


def _horizon_arrow_def(marker_id: str) -> str:
    return (f'<defs><marker id="{marker_id}" viewBox="0 0 6 6" refX="5" refY="3" '
            'markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
            '<path d="M0,0 L6,3 L0,6 Z" fill="#94a3b8"/></marker></defs>')


def _halo_text(x: float, y: float, word: str, anchor: str = "middle") -> str:
    """A band name: small grey text with a light halo so it reads over
    gridlines and dots alike."""
    return (f'<text x="{x:.0f}" y="{y:.0f}" text-anchor="{anchor}" '
            'font-size="11" font-weight="500" fill="#64748b" paint-order="stroke" '
            f'stroke="#f8fafc" stroke-width="4">{esc(word)}</text>')


def _horizon_legend(left: float, y: float, has_trails: bool) -> List[str]:
    """The legend for the three markers. Each is a ring style, so a dot can
    carry all three without a second glyph. ``left`` is the first ring's
    centre; the row is 700 px wide."""
    parts = [f'<circle cx="{left:.0f}" cy="{y:.0f}" r="6" fill="none" stroke="#0f172a" stroke-width="1.2" stroke-dasharray="2 2"/>',
             f'<text x="{left + 10:.0f}" y="{y + 4:.0f}" font-size="10" fill="#64748b">innovating — top third by product work</text>',
             f'<circle cx="{left + 224:.0f}" cy="{y:.0f}" r="6" fill="none" stroke="#b45309" stroke-width="1.6" stroke-dasharray="1 2.2"/>',
             f'<text x="{left + 234:.0f}" y="{y + 4:.0f}" font-size="10" fill="#64748b">hiring — top third by open roles per head</text>',
             f'<circle cx="{left + 466:.0f}" cy="{y:.0f}" r="6" fill="none" stroke="#1d4ed8" stroke-width="1"/>',
             f'<text x="{left + 476:.0f}" y="{y + 4:.0f}" font-size="10" fill="#64748b">raised in the last year</text>']
    if has_trails:
        parts.append(f'<line x1="{left + 18:.0f}" y1="{y + 14:.0f}" x2="{left + 36:.0f}" y2="{y + 14:.0f}" '
                     'stroke="#94a3b8" stroke-width="1.2" marker-end="url(#mm-hz-arrow)"/>')
        parts.append(f'<text x="{left + 42:.0f}" y="{y + 17:.0f}" font-size="10" fill="#64748b">'
                     'trail — moved 10 or more points on an axis since the previous map</text>')
    return parts


def _horizon_dot_layer(rated: List[Dict[str, Any]], allowed: Optional[set],
                       order: List[Dict[str, Any]], spread: Dict[int, tuple], place,
                       *, obstacles: List[tuple], width: float, max_y: float,
                       tiers: Optional[Dict[str, Any]], with_inputs: bool,
                       arrow: str, labels: Any = True, label_scale: float = 1.0) -> tuple:
    """The trails, dots, marker rings and vendor labels, the same on either
    map shape. ``place`` puts a vendor (or its previous scores) on the
    canvas; ``spread`` is the nudged position per brand id. Returns the
    trail parts and the dot parts, so the caller can draw the legend
    between them."""
    # A large move since the previous map is a trail from where the vendor
    # was, drawn under the dots so it never hides one.
    # ``order`` is largest and fastest first; a vendor's place in it is its
    # rank, and the ones past the top N carry ``data-tail`` so the map can
    # open on the top N and show the rest on request.
    rank = {r["brand_id"]: i + 1 for i, r in enumerate(order)}
    def tail(r: Dict[str, Any]) -> str:
        return ' data-tail="1"' if rank.get(r["brand_id"], 0) > _HORIZON_TOP else ''
    trails = []
    for r in rated:
        if not (r.get("big_move") and r.get("previous")):
            continue
        px, py = place(r["previous"])
        x, y = spread[r["brand_id"]]
        trails.append(f'<g class="mm-hz-trail"{tail(r)}><line x1="{px:.1f}" y1="{py:.1f}" x2="{x:.1f}" y2="{y:.1f}" '
                      f'stroke="#94a3b8" stroke-width="1.2" marker-end="url(#{arrow})"/>'
                      f'<circle cx="{px:.1f}" cy="{py:.1f}" r="3" fill="none" stroke="#94a3b8"/></g>')
    dots = [(r, *spread[r["brand_id"]]) for r in order]
    def ring(r: Dict[str, Any]) -> float:
        return 10.5 if r.get("funded") else 9.0 if r.get("hiring") else 7.5 if r.get("innovating") else 6.0
    shown = [allowed is None or r["vendor"] in allowed for r, _, _ in dots]

    def place_labels(idx: List[int]) -> Dict[int, Any]:
        """Label spots for the dots at ``idx``, placed among those dots only."""
        if not labels:
            return {}
        # ``order`` puts the largest and fastest first, so a number labels
        # the vendors a reader would look for first.
        limit = len(dots) if labels is True else int(labels)
        spots = _label_spots([(dots[i][1], dots[i][2], ring(dots[i][0]),
                               _label_width(dots[i][0]["vendor"]) * 1.1 * label_scale
                               if (shown[i] and i < limit) else 0.0)
                              for i in idx],
                             12.0 * label_scale, width, max_y, obstacles=obstacles)
        return dict(zip(idx, spots))

    # Labels are placed twice on a crowded map: among the top N dots for the
    # view the map opens on, and among all of them for "All". Placing them
    # once, among all, put the top-view labels far from their dots with
    # leader lines crossing the arc.
    crowd = len(dots) > _HORIZON_TOP
    spots_all = place_labels(list(range(len(dots))))
    spots_top = place_labels([i for i in range(len(dots)) if i < _HORIZON_TOP]) if crowd else spots_all

    def leader(spot) -> str:
        if not (spot and spot["leader"]):
            return ""
        # The label had to move away from its dot: a leader line says
        # which dot it belongs to. Drawn first, so it sits under the dot.
        (x1, y1), (x2, y2) = spot["leader"]
        return (f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
                'stroke="#64748b" stroke-width="1"/>'
                f'<circle cx="{x2:.1f}" cy="{y2:.1f}" r="1.8" fill="#64748b"/>')

    def label(spot, name: str) -> str:
        if spot is None:
            return ""
        return (f'<text class="mm-lbl" x="{spot["tx"]:.1f}" y="{spot["by"] + 10 * label_scale:.1f}" '
                f'text-anchor="{spot["anchor"]}" font-size="11" fill="#0f172a">{esc(name)}</text>')

    def layers(i: int, r: Dict[str, Any], part) -> str:
        if not crowd:
            return part(spots_all.get(i), r["vendor"]) if part is label else part(spots_all.get(i))
        a = part(spots_all.get(i), r["vendor"]) if part is label else part(spots_all.get(i))
        t = part(spots_top.get(i), r["vendor"]) if part is label else part(spots_top.get(i))
        return ((f'<g class="mm-lbl-all">{a}</g>' if a else "")
                + (f'<g class="mm-lbl-top">{t}</g>' if t else ""))

    parts = []
    for i, ((r, x, y), is_shown) in enumerate(zip(dots, shown)):
        colour = _TIER_COLOUR.get(r.get("tier") or "", "#475569")
        # The hover panel names the vendor, so it is withheld with the label.
        tip = (f' data-tip="{esc(_horizon_tip(r, tiers or {}, with_inputs=with_inputs))}"'
               if is_shown else '')
        marks = " ".join(k for k, _ in _MARKER_COLOURS if r.get(k))
        parts.append(f'<g class="mm-hz-pt{" mm-hz-dot" if is_shown else ""}" data-m="{marks}" '
                     f'data-rank="{rank.get(r["brand_id"], 0)}"{tail(r)}{tip}>')
        parts.append(layers(i, r, leader))
        if r.get("innovating"):
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="7.5" fill="none" '
                         'stroke="#0f172a" stroke-width="1.1" stroke-dasharray="2 2"/>')
        if r.get("hiring"):
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="9" fill="none" '
                         'stroke="#b45309" stroke-width="1.4" stroke-dasharray="1 2.2"/>')
        if r.get("funded"):
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="10.5" fill="none" '
                         'stroke="#1d4ed8" stroke-width="1"/>')
        parts.append(f'<circle class="mm-core" cx="{x:.1f}" cy="{y:.1f}" r="5" fill="{colour}" fill-opacity=".85"/>')
        parts.append(layers(i, r, label))
        parts.append('</g>')
    return trails, parts


def _momentum_floor(rated: List[Dict[str, Any]]) -> float:
    lows = [float(r["momentum"]) for r in rated]
    lows += [float(r["previous"]["momentum"]) for r in rated if r.get("big_move") and r.get("previous")]
    if not lows:
        return 0.0
    return max(0.0, min(20.0, 5 * math.floor((min(lows) - 3) / 5)))


def _horizon_grid_svg(rated: List[Dict[str, Any]], allowed: Optional[set],
                      cuts: Dict[str, Any], *, tiers: Optional[Dict[str, Any]] = None,
                      bands: Optional[Dict[str, Any]] = None, with_inputs: bool = False) -> str:
    """The same vendors on plain axes: scale left to right, momentum bottom
    to top, both 0 to 100. The stage cuts are vertical lines and the band
    cuts horizontal ones, so each is plainly a cut on one score. The
    semicircle reads as a life cycle; this one reads as a chart, and a
    vendor's left-right position depends on scale alone."""
    from app.services.market_horizon import band_cuts, band_info, stage_cuts, tier_info
    w, h = 900, 560
    x0, x1, y0, y1 = 58.0, 848.0, 40.0, 480.0
    cuts = cuts or {}
    def clamp(n: float) -> float:
        return max(0.0, min(100.0, float(n)))
    def sx(scale: float) -> float:
        return x0 + (x1 - x0) * clamp(scale) / 100
    # The momentum axis starts at a floor below the lowest dot (a multiple
    # of 5, at least 3 below it, never above 20), so the plot is not a
    # fifth empty when nobody is near zero. The tick names the floor.
    floor = _momentum_floor(rated)
    def sy(momentum: float) -> float:
        return y1 - (y1 - y0) * (clamp(momentum) - floor) / (100 - floor)
    def place(r: Dict[str, Any]):
        return sx(r["scale"]), sy(r["momentum"])
    stage_names = {k: v["label"] for k, v in (tiers or tier_info(cuts)).items()}
    band_names = {k: v["label"] for k, v in (bands or band_info(cuts)).items()}
    b1, b2 = band_cuts(cuts)
    c1, c2, c3 = stage_cuts(cuts)
    parts = [f'<svg viewBox="0 0 {w} {h}" width="100%" style="max-width:{w}px" role="img" '
             'aria-label="Market Maturity Map: scale against momentum">',
             _horizon_arrow_def("mm-hz-arrow-grid"),
             f'<rect x="{x0:.0f}" y="{y0:.0f}" width="{x1 - x0:.0f}" height="{y1 - y0:.0f}" fill="#f8fafc"/>']
    # The outer bands are washed a shade darker, so the three read as rows
    # even before the reader finds the names.
    for lo, hi in ((floor, b1), (b2, 100.0)):
        parts.append(f'<rect x="{x0:.0f}" y="{sy(hi):.1f}" width="{x1 - x0:.0f}" '
                     f'height="{sy(lo) - sy(hi):.1f}" fill="#eef2f6"/>')
    for cut in (b1, b2):
        parts.append(f'<line x1="{x0:.0f}" y1="{sy(cut):.1f}" x2="{x1:.0f}" y2="{sy(cut):.1f}" '
                     'stroke="#cbd5e1" stroke-dasharray="4 4"/>')
    for cut in (c1, c2, c3):
        parts.append(f'<line x1="{sx(cut):.1f}" y1="{y0:.0f}" x2="{sx(cut):.1f}" y2="{y1:.0f}" '
                     'stroke="#cbd5e1" stroke-dasharray="4 4"/>')
    parts.append(f'<rect x="{x0:.0f}" y="{y0:.0f}" width="{x1 - x0:.0f}" height="{y1 - y0:.0f}" '
                 'fill="none" stroke="#e2e8f0"/>')
    # Stage names above their columns; band names inside their rows at the
    # right edge, drawn after the dots and kept clear of the labels.
    edges = [0.0, c1, c2, c3, 100.0]
    for k, key in enumerate(_STAGE_KEYS):
        name = stage_names.get(key) or key
        mx = (sx(edges[k]) + sx(edges[k + 1])) / 2
        parts.append(f'<text x="{mx + 10:.0f}" y="{y0 - 12:.0f}" '
                     'text-anchor="middle" font-size="13" font-weight="600" fill="#334155" '
                     f'letter-spacing=".3">{esc(name)}</text>')
        parts.append(_stage_icon(key, mx + 10 - _label_width(name) * 0.68 - 14, y0 - 16.5))
    # An arrow between the stage names at each cut: the stages run left to right.
    for cut in (c1, c2, c3):
        parts.append(f'<text x="{sx(cut):.0f}" y="{y0 - 12:.0f}" text-anchor="middle" font-size="14" '
                     'fill="#94a3b8">→</text>')
    band_marks, band_text = [], []
    for key, top in (("holding", b1), ("growing", b2), ("accelerating", 100.0)):
        word = (band_names.get(key) or key).lower()
        bw = _label_width(word) * 1.1
        px, py = x1 - 8, sy(top) + 8
        band_marks.append((px - bw, py - 6, bw, 12.0))
        band_text.append(_halo_text(px, py + 4, word, anchor="end"))
    # Ticks at the cuts, so the numbers on the axes are the ones that matter.
    for v in (0.0, c1, c2, c3, 100.0):
        parts.append(f'<text x="{sx(v):.0f}" y="{y1 + 14:.0f}" text-anchor="middle" font-size="10" '
                     f'fill="#94a3b8">{v:g}</text>')
    for v in (floor, b1, b2, 100.0):
        parts.append(f'<text x="{x0 - 8:.0f}" y="{sy(v) + 3.5:.1f}" text-anchor="end" font-size="10" '
                     f'fill="#94a3b8">{v:g}</text>')
    parts += [f'<text x="{x0:.0f}" y="{y1 + 32:.0f}" font-size="11" fill="#64748b">← smaller by scale</text>',
              f'<text x="{x1:.0f}" y="{y1 + 32:.0f}" text-anchor="end" font-size="11" fill="#64748b">larger by scale →</text>',
              f'<text x="16" y="{(y0 + y1) / 2:.0f}" text-anchor="middle" font-size="11" fill="#64748b" '
              f'transform="rotate(-90 16 {(y0 + y1) / 2:.0f})">more momentum →</text>']
    order = sorted(rated, key=lambda r: -(r["scale"] + r["momentum"]))
    spread = dict(zip((r["brand_id"] for r in order), _spread([place(r) for r in order])))
    # Labels stay inside the plot: the gutters around it are obstacles.
    gutters = [(0.0, 0.0, x0 - 2, h), (0.0, 0.0, w, y0 - 2), (0.0, y1 + 2, w, h - y1)]
    trails, dots_svg = _horizon_dot_layer(rated, allowed, order, spread, place,
                                          obstacles=band_marks + gutters, width=x1 + 2, max_y=y1 + 2,
                                          tiers=tiers, with_inputs=with_inputs,
                                          arrow="mm-hz-arrow-grid")
    parts += _horizon_legend(x0 + 20, y1 + 54, bool(trails))
    parts += trails + dots_svg + band_text
    parts.append("</svg>")
    return "".join(parts)


def _spread(points: List[tuple], min_gap: float = 13.0, max_move: float = 10.0) -> List[tuple]:
    """Nudge dots apart until no two are closer than ``min_gap``, each moved
    at most ``max_move`` from where its scores put it. Vendors with all but
    the same scores would otherwise draw as one dot."""
    pos = [[x, y] for x, y in points]
    n = len(pos)
    for _ in range(40):
        moved = False
        for i in range(n):
            for j in range(i + 1, n):
                dx, dy = pos[j][0] - pos[i][0], pos[j][1] - pos[i][1]
                d = math.hypot(dx, dy)
                if d >= min_gap:
                    continue
                if d < 1e-6:
                    dx, dy, d = 1.0, 0.0, 1.0
                push = (min_gap - d) / 2
                pos[i][0] -= dx / d * push
                pos[i][1] -= dy / d * push
                pos[j][0] += dx / d * push
                pos[j][1] += dy / d * push
                moved = True
        for k, (ox, oy) in enumerate(points):
            mx, my = pos[k][0] - ox, pos[k][1] - oy
            m = math.hypot(mx, my)
            if m > max_move:
                pos[k] = [ox + mx / m * max_move, oy + my / m * max_move]
        if not moved:
            break
    return [(x, y) for x, y in pos]


def _seg_hits_box(x1: float, y1: float, x2: float, y2: float,
                  bx: float, by: float, bw: float, bh: float) -> bool:
    """Does the segment cross the box? Liang–Barsky clipping."""
    dx, dy = x2 - x1, y2 - y1
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, x1 - bx), (dx, bx + bw - x1), (-dy, y1 - by), (dy, by + bh - y1)):
        if p == 0:
            if q < 0:
                return False
            continue
        t = q / p
        if p < 0:
            if t > t1:
                return False
            t0 = max(t0, t)
        else:
            if t < t0:
                return False
            t1 = min(t1, t)
    return t0 <= t1


def _segs_cross(a: tuple, b: tuple) -> bool:
    """Do two segments (x1, y1, x2, y2) cross?"""
    def side(px, py, qx, qy, rx, ry):
        return (qx - px) * (ry - py) - (qy - py) * (rx - px)
    d1 = side(b[0], b[1], b[2], b[3], a[0], a[1])
    d2 = side(b[0], b[1], b[2], b[3], a[2], a[3])
    d3 = side(a[0], a[1], a[2], a[3], b[0], b[1])
    d4 = side(a[0], a[1], a[2], a[3], b[2], b[3])
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0))


def _seg_near_point(x1: float, y1: float, x2: float, y2: float, px: float, py: float) -> float:
    """How far the point is from the nearest point of the segment."""
    dx, dy = x2 - x1, y2 - y1
    l2 = dx * dx + dy * dy
    t = 0.0 if l2 == 0 else max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / l2))
    return math.hypot(x1 + t * dx - px, y1 + t * dy - py)


def _box_hits_ring(bx: float, by: float, bw: float, bh: float, cx: float, cy: float, r: float) -> bool:
    """Does the box overlap the circle?"""
    nx = max(bx, min(cx, bx + bw))
    ny = max(by, min(cy, by + bh))
    return math.hypot(nx - cx, ny - cy) < r


def _label_width(text: str) -> float:
    """About how wide the label is at 10px in a sans-serif face, from the
    letters in it. Slightly generous, so a wider face still fits."""
    total = 4.0
    for ch in text:
        if ch in "iljtfr .'-,":
            total += 3.0
        elif ch in "mwMW":
            total += 8.5
        elif ch.isupper() or ch.isdigit():
            total += 7.0
        else:
            total += 5.8
    return total


# Twenty-four directions a label can sit in, starting beside the dot and
# going round; and the distances it can stand off, nearest first.
_LABEL_DIRS = [(math.cos(math.radians(a)), math.sin(math.radians(a))) for a in range(0, 360, 15)]
_LABEL_STEPS = [0, 8, 16, 24, 34, 46, 60, 76, 94, 115, 140]


def _label_spots(dots: List[tuple], height: float, width: float, max_y: float,
                 obstacles: Optional[List[tuple]] = None) -> List[Optional[dict]]:
    """Where every dot's label goes, so no label sits on a dot, another
    label or a leader line, and no leader line crosses one either.

    ``dots`` is ``[(x, y, ring, label_width)]``; a zero label width is a dot
    with no label (it still keeps labels off itself). ``width`` and ``max_y``
    bound the labels on the right and below. Returns one entry per dot,
    ``None`` for the unlabelled, else a dict: ``bx``/``by`` the label box's
    top-left, ``tx`` the text anchor x, ``anchor``, ``hits`` (what it still
    overlaps, weighted — 0 unless the crowd left no room; text over text
    weighs most, a label brushing a ring least), and
    ``leader`` — ``None`` when the label touches its dot, else the line from
    the dot's ring to the label.

    Two passes. First, every label that fits beside its own dot takes that
    spot, most crowded dots first, so nothing later can take it. Then the
    labels that did not fit move out on a leader line, nearest clear spot
    first, preferring the side that faces away from the dot's neighbours so
    a crowd's labels fan outwards instead of across each other.
    """
    n = len(dots)
    # ``obstacles`` are boxes (x, y_top, w, h) already on the map that a
    # label must keep off, such as the band names.
    labels: List[tuple] = list(obstacles or [])
    leaders: List[tuple] = []
    def neighbours(i: int) -> List[int]:
        xi, yi = dots[i][0], dots[i][1]
        return [j for j in range(n) if j != i and abs(dots[j][0] - xi) < 48 and abs(dots[j][1] - yi) < 48]
    order = [i for i in sorted(range(n), key=lambda i: (-len(neighbours(i)), dots[i][1], dots[i][0]))
             if dots[i][3] > 0]
    out: List[Optional[dict]] = [None] * n

    def assess(i: int, px: float, py: float, ux: float, uy: float, near: bool) -> Optional[dict]:
        """The label for dot ``i`` whose box touches point ``(px, py)`` from
        direction ``(ux, uy)``; ``near`` when it sits beside the dot with no
        leader line. None if it leaves the canvas."""
        x, y, g, w = dots[i]
        bx = px - w / 2 + ux * w / 2
        by = py - height / 2 + uy * height / 2
        if bx < 0 or bx + w > width or by < 0 or by + height > max_y:
            return None
        # Overlap, weighted: text over text or over a dot is the worst
        # (10), a label under a leader line or a leader line over text next
        # (6), a leader line through a dot's core (2), a label brushing a
        # marker ring or two leader lines crossing (1). A leader line may
        # pass under a marker ring; the dot itself is drawn over it.
        hits = sum(10 if _box_hits_ring(bx, by, w, height, ox, oy, 6.0) else 1
                   for k, (ox, oy, r, _) in enumerate(dots) if k != i
                   and _box_hits_ring(bx - 2, by - 1, w + 4, height + 2, ox, oy, r))
        hits += sum(10 for ox, oy, ow, oh in labels
                    if bx - 3 < ox + ow and ox < bx + w + 3 and by - 2 < oy + oh and oy < by + height + 2)
        hits += sum(6 for seg in leaders if _seg_hits_box(*seg, bx, by, w, height))
        # The leader line runs from the dot's ring towards the label.
        lx, ly = px - x, py - y
        ln = math.hypot(lx, ly) or 1.0
        sx, sy = x + (g + 1) * lx / ln, y + (g + 1) * ly / ln
        if not near:
            hits += sum(2 for k, (ox, oy, _, _) in enumerate(dots) if k != i
                        and math.hypot(sx - ox, sy - oy) >= 6.0 and _seg_near_point(sx, sy, px, py, ox, oy) < 6.0)
            hits += sum(6 for ox, oy, ow, oh in labels if _seg_hits_box(sx, sy, px, py, ox, oy, ow, oh))
            hits += sum(1 for seg in leaders if _segs_cross((sx, sy, px, py), seg))
        anchor = "start" if ux > 0.35 else "end" if ux < -0.35 else "middle"
        return {"bx": bx, "by": by, "anchor": anchor,
                "tx": bx if anchor == "start" else bx + w if anchor == "end" else bx + w / 2,
                "leader": None if near else ((sx, sy), (px, py)), "hits": hits}

    def candidate(i: int, step: int, ux: float, uy: float) -> Optional[dict]:
        x, y, g, _ = dots[i]
        d = g + 2 + step
        return assess(i, x + d * ux, y + d * uy, ux, uy, step == 0)

    def take(i: int, spot: dict) -> None:
        labels.append((spot["bx"], spot["by"], dots[i][3], height))
        if spot["leader"]:
            (x1, y1), (x2, y2) = spot["leader"]
            leaders.append((x1, y1, x2, y2))
        out[i] = spot

    # Pass zero: clusters. Dots linked within 22 px, three or more of them,
    # get their labels fanned around the cluster in the order of their
    # angle from its centre, so the leader lines are short and never cross.
    parent = list(range(n))
    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for i in range(n):
        for j in range(i + 1, n):
            if math.hypot(dots[i][0] - dots[j][0], dots[i][1] - dots[j][1]) < 22:
                parent[find(i)] = find(j)
    groups: Dict[int, List[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    for members in sorted(groups.values(), key=len, reverse=True):
        labelled = [i for i in members if dots[i][3] > 0]
        if len(labelled) < 3:
            continue
        mx = sum(dots[i][0] for i in members) / len(members)
        my = sum(dots[i][1] for i in members) / len(members)
        rr0 = max(math.hypot(dots[i][0] - mx, dots[i][1] - my) + dots[i][2] for i in members) + 8
        by_angle = sorted(labelled, key=lambda i: math.atan2(dots[i][1] - my, dots[i][0] - mx))
        # A member whose name fits beside it, pointing away from the
        # cluster, keeps it; the fan is for the rest.
        for i in by_angle:
            th = math.atan2(dots[i][1] - my, dots[i][0] - mx)
            for ux, uy in sorted(_LABEL_DIRS, key=lambda u: -(u[0] * math.cos(th) + u[1] * math.sin(th))):
                if ux * math.cos(th) + uy * math.sin(th) < 0.5:
                    break
                c = candidate(i, 0, ux, uy)
                if c is not None and c["hits"] == 0:
                    take(i, c)
                    break
        for i in by_angle:
            if out[i] is not None:
                continue
            th = math.atan2(dots[i][1] - my, dots[i][0] - mx)
            pick = None
            for extra in (0, 12, 24, 36):
                for dth in (0.0, 0.16, -0.16, 0.32, -0.32):
                    ux, uy = math.cos(th + dth), math.sin(th + dth)
                    c = assess(i, mx + (rr0 + extra) * ux, my + (rr0 + extra) * uy, ux, uy, False)
                    if c is not None and c["hits"] == 0:
                        (sx, sy), (px, py) = c["leader"]
                        if math.hypot(px - sx, py - sy) <= 70:
                            pick = c
                        break
                if pick:
                    break
            if pick:
                take(i, pick)

    # Pass one: beside the dot, sideways before up or down.
    for i in order:
        if out[i] is not None:
            continue
        for ux, uy in sorted(_LABEL_DIRS, key=lambda u: abs(u[1])):
            c = candidate(i, 0, ux, uy)
            if c is not None and c["hits"] == 0:
                take(i, c)
                break
    # Pass two: out on a leader line.
    for i in order:
        if out[i] is not None:
            continue
        x, y = dots[i][0], dots[i][1]
        nb = neighbours(i)
        away = None
        if nb:
            mx = sum(dots[j][0] for j in nb) / len(nb)
            my = sum(dots[j][1] for j in nb) / len(nb)
            norm = math.hypot(x - mx, y - my)
            if norm > 0.5:
                away = ((x - mx) / norm, (y - my) / norm)
        # A spot's price is its distance plus what it overlaps; one point of
        # overlap costs the same as forty pixels of leader line, so a label
        # goes a long way round to avoid text but not to avoid a ring's edge.
        best, best_cost = None, float("inf")
        for step in _LABEL_STEPS:
            for ux, uy in _LABEL_DIRS:
                cost = step + 3 * abs(uy) + (0 if away is None else 12 * (1 - (ux * away[0] + uy * away[1])))
                if cost >= best_cost:
                    continue
                c = candidate(i, step, ux, uy)
                if c is not None and cost + 40 * c["hits"] < best_cost:
                    best, best_cost = c, cost + 40 * c["hits"]
            if best_cost <= step + 3:
                break
        assert best is not None
        take(i, best)
    return out


_HORIZON_SLOT = "<!--mm-horizon-slot-->"

# The hover panel on the horizon. Each dot carries its own panel as HTML in
# a data attribute, so the page needs no data beyond what it already shows;
# a tap holds the panel open on a touch screen.
#: The map opens on the top N vendors by scale plus momentum; a switch shows
#: all of them. Eighty dots on one arc is a crowd; forty reads.
_HORIZON_TOP = 40

_HORIZON_JS = """
(function(){var box=document.querySelector('.mm-hz');if(!box)return;
var tip=box.querySelector('.mm-hz-tip');var held=null;
function show(g,e){tip.innerHTML=g.getAttribute('data-tip');tip.hidden=false;move(e);}
function move(e){var r=box.getBoundingClientRect();var x=e.clientX-r.left+14,y=e.clientY-r.top+14;
if(x+tip.offsetWidth>r.width)x=Math.max(0,e.clientX-r.left-tip.offsetWidth-14);
if(y+tip.offsetHeight>r.height)y=Math.max(0,y-tip.offsetHeight-28);
tip.style.left=x+'px';tip.style.top=y+'px';}
[].forEach.call(box.querySelectorAll('.mm-hz-dot'),function(g){
g.addEventListener('mouseenter',function(e){if(!held)show(g,e);});
g.addEventListener('mousemove',function(e){if(!held)move(e);});
g.addEventListener('mouseleave',function(){if(!held)tip.hidden=true;});
g.addEventListener('click',function(e){e.stopPropagation();if(held===g){held=null;tip.hidden=true;}
else{held=g;show(g,e);}});});
document.addEventListener('click',function(){held=null;tip.hidden=true;});
[].forEach.call(box.querySelectorAll('.mm-hz-switch button[data-view]'),function(b){
b.addEventListener('click',function(){var v=b.getAttribute('data-view');held=null;tip.hidden=true;
[].forEach.call(box.querySelectorAll('.mm-hz-switch button[data-view]'),function(o){o.setAttribute('aria-selected',o===b?'true':'false');});
[].forEach.call(box.querySelectorAll('.mm-hz-view'),function(p){p.hidden=p.getAttribute('data-view')!==v;});});});
var chips=box.querySelectorAll('.mm-hz-chips button');
[].forEach.call(chips,function(b){b.addEventListener('click',function(){
var k=b.getAttribute('aria-pressed')==='true'?null:b.getAttribute('data-hl');
[].forEach.call(chips,function(o){o.setAttribute('aria-pressed',o.getAttribute('data-hl')===k?'true':'false');});
if(k)box.style.setProperty('--mm-hl',b.style.getPropertyValue('--mm-hl'));
[].forEach.call(box.querySelectorAll('.mm-hz-pt'),function(g){var on=k&&(' '+g.getAttribute('data-m')+' ').indexOf(' '+k+' ')>=0;
g.classList.toggle('mm-on',!!on);g.classList.toggle('mm-dim',!!k&&!on);});});});
[].forEach.call(box.querySelectorAll('.mm-hz-show button'),function(b){b.addEventListener('click',function(){
var v=b.getAttribute('data-show');held=null;tip.hidden=true;box.classList.toggle('mm-top',v==='top');
[].forEach.call(box.querySelectorAll('.mm-hz-show button'),function(o){o.setAttribute('aria-pressed',o===b?'true':'false');});});});})();
"""


def _horizon_section(horizon: Dict[str, Any], allowed: Optional[set], *,
                     public_names: bool = False) -> str:
    """The map, the tiers, the not-rated list and the weights, in that order.

    ``public_names`` labels every rated vendor and lists every tier in full
    whatever the entitlement; the not-rated names still follow ``allowed``.
    """
    from app.services import market_horizon as mh

    # Weights and cuts are the stored map's: the vendors were placed with
    # them. The words beside each input are copy, so they come from the
    # live config, or a copy edit would wait for the next recompute.
    cfg = dict(horizon.get("config") or {})
    live_inputs = (mh.load_config().get("inputs") or {})
    cfg["inputs"] = {k: {**v, **{w: live_inputs[k][w] for w in ("label", "note")
                                if w in live_inputs.get(k, {})}}
                     for k, v in (cfg.get("inputs") or {}).items()}
    live_label = lambda g: (live_inputs.get(g.get("key"), {}).get("label") or g["label"])
    rated = horizon.get("rated") or []
    not_rated = horizon.get("not_rated") or []
    names_allowed = None if public_names else allowed
    # The drawer's own title already says "Market Maturity Map"; no second heading.
    out = ['<section class="section">']
    # The caption is copy, so it comes from code, not from the stored map.
    out.append(f'<p class="mm-src">{esc(mh.WHAT_IT_IS_NOT)} '
               f'Computed {esc((horizon.get("computed_at") or "")[:10])} over the '
               f'last {horizon.get("days")} days.</p>')
    full_view = allowed is None
    # Two shapes of the same map. The semicircle reads as a life cycle; the
    # grid puts scale on one axis and momentum on the other. The reader
    # picks; the arc is the one shown first.
    draw = dict(tiers=horizon.get("tiers") or {}, bands=horizon.get("bands") or {},
                with_inputs=full_view)
    crowd = len(rated) > _HORIZON_TOP
    show = ('' if not crowd else
            '<span class="mm-hz-show" role="group" aria-label="Vendors shown">Show '
            f'<button type="button" aria-pressed="true" data-show="top">Top {_HORIZON_TOP}</button>'
            f'<button type="button" aria-pressed="false" data-show="all">All {len(rated)}</button></span>')
    out.append(f'<div class="mm-hz{" mm-top" if crowd else ""}">'
               '<div class="mm-hz-switch" role="tablist" aria-label="Map layout">'
               '<button type="button" role="tab" aria-selected="true" data-view="arc">Arc</button>'
               '<button type="button" role="tab" aria-selected="false" data-view="grid">Grid</button>'
               '<span class="mm-hz-chips">Highlight '
               + "".join(f'<button type="button" aria-pressed="false" data-hl="{k}" style="--mm-hl:{c}">'
                         f'{_MARKER_LABELS.get(k, k)} <b>{sum(1 for r in rated if r.get(k))}</b></button>'
                         for k, c in _MARKER_COLOURS)
               + '</span>' + show + '</div>'
               '<div class="mm-hz-view" data-view="arc">'
               + _horizon_svg(rated, names_allowed, cfg.get("tiers") or {}, **draw)
               + '</div><div class="mm-hz-view" data-view="grid" hidden>'
               + _horizon_grid_svg(rated, names_allowed, cfg.get("tiers") or {}, **draw)
               + '</div><div class="mm-hz-tip" hidden></div></div>'
               + f'<script>{_HORIZON_JS}</script>')
    # The stored list holds every vendor listed-not-placed; pivoted ones get
    # their own line, since "bought" and "left for another market" are
    # different facts about a name that has gone from the map.
    listed = horizon.get("acquired") or []
    pivoted = [a for a in listed if a.get("status") == "pivoted"]
    acquired = [a for a in listed if a.get("status") != "pivoted"]
    innovating = [r for r in rated if r.get("innovating")]

    def fold(summary: str, inner: str) -> str:
        # The map is the page's opening picture; the lists behind it open on
        # request, so the eye lands on the horizon and not on a wall of names.
        return (f'<details class="mm-fold"><summary>{summary}</summary>'
                f'<div class="mm-fold-body">{inner}</div></details>')

    tiers_html = []
    # The stored map carries the descriptions with their "{c1}" placeholders;
    # the cut scores are written in here.
    live_tiers = mh.tier_info(cfg.get("tiers") or {})
    live_bands = mh.band_info(cfg.get("tiers") or {})
    for tier in _TIER_ORDER:
        info = {**((horizon.get("tiers") or {}).get(tier) or {}), **live_tiers.get(tier, {})}
        rows = [r for r in rated if r["tier"] == tier]
        if not rows:
            continue
        # By scale, not by the stored rank order: a newly rated vendor has no
        # rank yet and would trail the list, which reads as a bottom placing.
        rows.sort(key=lambda r: r.get("scale") or 0, reverse=True)
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
                name += ' <span class="mm-src" title="raised in the last year">$</span>'
            if r.get("moved") and (r.get("previous") or {}).get("tier") != tier:
                name += f' <span class="mm-src">(was {esc((r["previous"] or {}).get("tier", ""))})</span>'
            names.append(name)
        if hidden:
            names.append(f'{hidden} vendor{"s" if hidden > 1 else ""} not shown in this view')
        tiers_html.append(f'<h3>{esc(info.get("label") or tier.capitalize())} '
                          f'<span class="mm-src">({len(rows)}) — {esc(info.get("means") or "")}</span></h3>')
        tiers_html.append(f'<p>{", ".join(names)}</p>')
    # JSONB hands the bands back in its own key order; fastest first here.
    bands = {k: {**v, **live_bands.get(k, {})} for k, v in (horizon.get("bands") or {}).items()}
    band_order = [k for k in ("accelerating", "growing", "holding") if k in bands] + \
                 [k for k in bands if k not in ("accelerating", "growing", "holding")]
    for band in band_order:
        binfo = bands[band]
        brows = [r for r in rated if r.get("band") == band]
        # Same reason as the tier lists: momentum order, not stored order.
        brows.sort(key=lambda r: r.get("momentum") or 0, reverse=True)
        bnames = [esc(r["vendor"]) for r in brows if names_allowed is None or r["vendor"] in names_allowed]
        bhidden = len(brows) - len(bnames)
        if bhidden:
            bnames.append(f'{bhidden} vendor{"s" if bhidden > 1 else ""} not shown in this view')
        tiers_html.append(f'<h3>{esc(binfo.get("label") or band.capitalize())} '
                          f'<span class="mm-src">({len(brows)}) — {esc(binfo.get("means") or "")}</span></h3>')
        tiers_html.append(f'<p>{", ".join(bnames) or "none"}</p>')
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
        tiers_html.append(f'<h3>Raised in the last year <span class="mm-src">({len(funded)}) — a round dated inside '
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
        tiers_html.append(f'<h3>Acquired <span class="mm-src">({len(acquired)}) — on the record, not on the map</span></h3>')
        tiers_html.append('<p>' + "; ".join(
            esc(a["vendor"]) + (f' — by {esc(a["acquired_by"])}' if a.get("acquired_by") else "")
            + (f', {esc(a["status_date"])}' if a.get("status_date") else "")
            for a in acquired if names_allowed is None or a["vendor"] in names_allowed) + '</p>')
    if pivoted:
        tiers_html.append(f'<h3>Pivoted <span class="mm-src">({len(pivoted)}) — left this market for another; on the record, not on the map</span></h3>')
        tiers_html.append('<p>' + "; ".join(
            esc(a["vendor"]) + (f' — {esc(a["note"])}' if a.get("note") else "")
            + (f' ({esc(a["status_date"])})' if a.get("status_date") else "")
            for a in pivoted if names_allowed is None or a["vendor"] in names_allowed) + '</p>')
    tier_summary = ", ".join(
        f'{(horizon.get("tiers") or {}).get(t, {}).get("label", t)} {sum(1 for r in rated if r["tier"] == t)}'
        for t in _TIER_ORDER)
    band_summary = ", ".join(
        f'{binfo.get("label", band).lower()} {sum(1 for r in rated if r.get("band") == band)}'
        for band, binfo in ((k, bands[k]) for k in band_order))
    marks_key = ('<p class="mm-src">Marks after a name: ◌ innovating · ⚒ hiring · '
                 '$ raised in the last year · "(was …)" moved stage since the previous map. '
                 'Each mark belongs to the name before it.</p>')
    out.append(fold(f"Who is where — {esc(tier_summary)}"
                    + (f"; {esc(band_summary)}" if band_summary else "")
                    + (f", innovating {len(innovating)}" if innovating else "")
                    + (f", hiring {len(hiring)}" if hiring else "")
                    + (f", raised in the last year {len(funded)}" if funded else "")
                    + (f", moved {len(moves)}" if moves else "")
                    + (f", acquired {len(acquired)}" if acquired else "")
                    + (f", pivoted {len(pivoted)}" if pivoted else ""),
                    marks_key + "".join(tiers_html)))

    if full_view:
        noted = [r for r in rated if r.get("analyst_note") or r.get("multipliers")]
        noted += [a for a in acquired + pivoted if a.get("note")]
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
                by_reason[live_label(g)] = by_reason.get(live_label(g), 0) + 1
        reasons = "; ".join(f"{n} lack {esc(label.lower())}" for label, n in
                            sorted(by_reason.items(), key=lambda kv: -kv[1]))
        inner = (f'<p class="mm-src">A vendor is rated only when we have every '
                 f'input. {reasons}.</p>')
        if True:
            inner += '<p class="mm-src">' + "; ".join(
                f'{esc(nr["vendor"])}: ' + ", ".join(esc(live_label(g).lower()) for g in nr["missing"])
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
    from app.services.market_horizon import band_cuts, stage_cuts
    c1, c2, c3 = stage_cuts(cfg.get("tiers") or {})
    b1, b2 = band_cuts(cfg.get("tiers") or {})
    weights += ('<p class="mm-src">Each input is a percentile rank among the rated '
                'vendors; an axis is the weighted mean of its inputs. On the map, the angle '
                'is the stage, by scale: Emerging under '
                f'{c1:g}, Building from {c1:g}, Scaling from {c2:g}, Executing from {c3:g}, '
                'left to right. The distance from the base is momentum: holding under '
                f'{b1:g}, growing from {b1:g}, accelerating from {b2:g}. A vendor moves right '
                'as it grows and outward as it speeds up.</p>')
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
            return ('<div class="n-support"><strong>Source:</strong> '
                    f'{esc(measured[0].get("title") or "platform data")}'
                    '</div>')
        held = int(f.get("evidence_count") or 0)
        if not held:
            return ""
        return ('<div class="n-support"><strong>Source:</strong> '
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
        # "Source" when there is one record and nothing to add to it;
        # "More" when the list actually continues past the byline.
        label = "Source" if len(records) == 1 and not discussion else "More"
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
                f'<strong>Want more data?</strong><span class="sr-only"> {what} are blurred '
                'in this shared view.</span>'
                '<br><a class="mm-btn" href="#mm-trial">Get the full report</a>'
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


_TIP_JS = """
(function(){var f=document.getElementById('mm-tip-form');if(!f)return;
var m=document.getElementById('mm-tip-msg');var el=f.elements;
f.addEventListener('submit',function(e){e.preventDefault();
var b=f.querySelector('button');b.disabled=true;m.className='mm-trial-msg';
m.textContent='Sending…';
var d={url:el['url'].value,note:el['note'].value,email:el['email2'].value};
fetch(f.getAttribute('data-endpoint'),{method:'POST',
headers:{'Content-Type':'application/json'},body:JSON.stringify(d)})
.then(function(r){return r.json().then(function(j){return {ok:r.ok,j:j};});})
.then(function(x){if(x.ok){f.reset();b.disabled=false;
m.textContent='Thanks. We will read it.';}
else{b.disabled=false;m.className='mm-trial-msg err';
m.textContent=(x.j&&x.j.detail&&typeof x.j.detail==='string')?x.j.detail:'Could not send the tip.';}})
.catch(function(){b.disabled=false;m.className='mm-trial-msg err';
m.textContent='Could not send the tip from this copy of the page.';});});})();
"""


def _tip_panel(market_id: int, market_name: str) -> str:
    """"Submit news" — a reader points us at a story we missed."""
    return (
        '<section class="mm-trial" id="mm-tip">'
        "<h2>Submit news</h2>"
        f"<p>Seen something about {esc(market_name)} that is not here? Send the "
        "link. We read every tip; what goes on the page is our call.</p>"
        '<form id="mm-tip-form" data-endpoint='
        f'"/api/market-monitor/markets/{int(market_id)}/news-tip">'
        '<div><label for="mm-tip-url">Link</label>'
        '<input id="mm-tip-url" name="url" type="url" required maxlength="1000" '
        'autocomplete="url" placeholder="https://"></div>'
        '<div><label for="mm-tip-note">What it is (optional)</label>'
        '<input id="mm-tip-note" name="note" maxlength="2000"></div>'
        '<div><label for="mm-tip-email">Your email (optional)</label>'
        '<input id="mm-tip-email" name="email" type="email" maxlength="254" '
        'autocomplete="email"></div>'
        '<div><button type="submit" class="mm-btn">Send</button></div>'
        '<div class="mm-trial-msg" id="mm-tip-msg" role="status"></div>'
        "</form>"
        f"<script>{_TIP_JS}</script>"
        "</section>")


_CONTACT_JS = """
(function(){var f=document.getElementById('mm-contact-form');if(!f)return;
var sel=f.elements['kind'];var m=document.getElementById('mm-contact-msg');var base=f.getAttribute('data-base');
var groups=f.querySelectorAll('[data-kind]');var btn=f.querySelector('button');
var labels={news:'Send',missing:'Tell us',trial:'Request trial'};
function show(){var k=sel.value;for(var i=0;i<groups.length;i++){var g=groups[i];
var on=g.getAttribute('data-kind').split(' ').indexOf(k)>=0;g.hidden=!on;
var inp=g.querySelector('input');if(inp){inp.required=on&&g.hasAttribute('data-required');}}
btn.textContent=labels[k]||'Send';m.textContent='';m.className='mm-trial-msg';}
sel.addEventListener('change',show);
var urls=f.querySelectorAll('input[type=url],input[name=website]');
for(var u=0;u<urls.length;u++){urls[u].addEventListener('blur',function(){var v=this.value.trim();
if(!v)return;if(/^https?:[/][/]/i.test(v)){this.value=v;return;}
v=v.replace(/^[a-z]*:?[/]+/i,'');this.value='https://'+v;});}
var h=location.hash;if(h==='#mm-trial'&&sel.querySelector('option[value=trial]'))sel.value='trial';
if(h==='#mm-missing')sel.value='missing';show();
f.addEventListener('submit',function(e){e.preventDefault();var k=sel.value;var el=f.elements;
btn.disabled=true;m.className='mm-trial-msg';m.textContent='Sending\u2026';
var d,ep,ok;if(k==='news'){ep='news-tip';d={url:el['url'].value,note:el['note'].value,email:el['email2'].value};ok='Thanks. We will read it.';}
else if(k==='missing'){ep='vendor-request';d={company:el['company'].value,website:el['website'].value,email:el['email'].value,note:el['note'].value};ok='Thanks. We will look at '+d.company+' and reply at '+d.email+'.';}
else{ep='trial-request';d={name:el['name'].value,email:el['email'].value,title:el['title'].value};ok='Thanks. We will be in touch at '+d.email+'.';}
fetch(base+ep,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(d)})
.then(function(r){return r.json().then(function(j){return {ok:r.ok,j:j};});})
.then(function(x){btn.disabled=false;if(x.ok){f.reset();sel.value=k;show();m.textContent=ok;}
else{m.className='mm-trial-msg err';
m.textContent=(x.j&&x.j.detail&&typeof x.j.detail==='string')?x.j.detail:'Could not send it.';}})
.catch(function(){btn.disabled=false;m.className='mm-trial-msg err';
m.textContent='Could not send it from this copy of the page.';});});})();
"""


def _book_link(market: Dict[str, Any]) -> str:
    """The "Schedule an inquiry" link for the top bars: only on a public
    market, and only when Stripe and the calendar are configured, so a
    tenant without them shows nothing rather than a dead button."""
    from app.services import market_inquiry as inq

    if not market.get("is_public") or not inq.is_configured():
        return ""
    return f'<a class="n-book" href="{inq.inquiry_href(market["id"])}">Schedule an inquiry</a>'


def _book_line(market_id: int) -> str:
    """One sentence in the contact panel pointing at the paid call, when
    it is configured."""
    from app.services import market_inquiry as inq

    if not inq.is_configured():
        return ""
    return (f'<p>Want to talk it through? <a href="{inq.inquiry_href(market_id)}">'
            "Book a 30 or 60 minute analyst call</a>.</p>")


def _contact_panel(market_id: int, market_name: str, *, trial: bool) -> str:
    """One form at the foot of the page. A dropdown says what it is about
    — a news tip, a missing vendor, a trial (shared view only) — and shows
    the fields for that; each kind posts to its own endpoint. ``#mm-tip``
    and ``#mm-trial`` still land here, preselected."""
    opts = ['<option value="news">Submit news</option>',
            '<option value="missing">My company is missing from the list</option>']
    if trial:
        opts.append('<option value="trial">Get the full report and data</option>')
    field = lambda kind, name, label, req=False, extra="": (  # noqa: E731
        f'<div data-kind="{kind}"{" data-required" if req else ""}><label for="mm-c-{name}">{label}</label>'
        f'<input id="mm-c-{name}" name="{name}" maxlength="500" {extra}></div>')
    return (
        '<section class="mm-trial" id="mm-contact"><span id="mm-tip"></span>'
        + ('<span id="mm-trial"></span>' if trial else "")
        + "<h2>Get in touch</h2>"
        f"<p>Send us a story about {esc(market_name)} that is not here, tell us your company "
        "belongs on the list" + (", or ask for the full report and data" if trial else "")
        + ". We read everything; what goes on the page is our call.</p>"
        + _book_line(market_id)
        + f'<form id="mm-contact-form" data-base="/api/market-monitor/markets/{int(market_id)}/">'
        '<div class="mm-c-kind"><label for="mm-c-kind">What is it about?</label>'
        f'<select id="mm-c-kind" name="kind">{"".join(opts)}</select></div>'
        + field("news", "url", "Link", True, 'type="url" autocomplete="url" placeholder="https://"')
        + field("missing", "company", "Company", True, 'autocomplete="organization"')
        + field("missing", "website", "Website", False, 'autocomplete="url" placeholder="https://"')
        + field("trial", "name", "Name", True, 'autocomplete="name"')
        + field("trial", "title", "Title", False, 'autocomplete="organization-title"')
        + field("missing trial", "email", "Your email", True, 'type="email" autocomplete="email"')
        + field("news", "email2", "Your email (optional)", False, 'type="email" autocomplete="email"')
        + field("news missing", "note", "Anything else (optional)")
        + '<div><button type="submit" class="mm-btn">Send</button></div>'
        '<div class="mm-trial-msg" id="mm-contact-msg" role="status"></div>'
        "</form>"
        f"<script>{_CONTACT_JS}</script>"
        "</section>")


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
        "<h2>Get the full report and data</h2>"
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
            else f'seen {_day(dev["date"])}, date unknown'
    if dev.get("event_type") == "significant_hiring":
        return "this period"
    return "date unknown"


def _dev_sources(dev: Dict[str, Any]) -> str:
    n = int(dev.get("source_count") or 0)
    if dev.get("provenance") == "measured":
        return "LinkedIn headcount on two dates"
    return f'{n} source{"" if n == 1 else "s"}'


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
        out.append(_finding_body(f, devs_by_id))
        out.append("</li>")
    out.append("</ol>")
    return "".join(out)


def _finding_body(f: Dict[str, Any], devs_by_id: Dict[str, Dict[str, Any]]) -> str:
    """Everything under a finding's headline: the statement, its evidence
    lines, the developments it rests on, and its coverage line."""
    out = [f'<p>{esc(f["body"])}</p>']
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
    return "".join(out)


def _dev_evidence_links(dev: Dict[str, Any]) -> str:
    """The records behind one development, reusing the story-evidence
    renderer so the labelling rules are the same everywhere."""
    return _story_evidence({"supporting": dev.get("evidence") or [],
                            "evidence_count": dev.get("evidence_count") or 0})


def _render_moved_table(devs: List[Dict[str, Any]]) -> str:
    """Vendors with a development: the centrepiece table."""
    if not devs:
        return ('<p class="n-empty">No vendor had a development in '
                'the period, on the sources we collect.</p>')
    out = ['<div class="n-tablewrap"><table class="mm-table n-moved"><thead><tr>'
           '<th>Vendor</th><th>Development</th><th>Evidence</th>'
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
    return (f'<details class="n-more"><summary>Other developments '
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
    """Vendor activity, as states — never "vendors with no signal"."""
    out = ['<section class="n-card" id="mm-observation"><div class="n-card-title">'
           '<h2>Vendor activity</h2>'
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
    out.append('<p class="n-note">A vendor counts as having no development '
               'only when its '
               + (esc(" and ".join(required)) if required else "expected sources")
               + ' were read during the period. Otherwise it is listed as '
               'partly collected.</p>')
    out.append("</section>")
    return "".join(out)


def _render_hiring_block(devs: List[Dict[str, Any]], *,
                         total: Optional[int] = None,
                         logos: Optional[Dict[str, str]] = None) -> str:
    """Hiring developments as one block: a vendor, a count, a mix. Eleven
    entries each listing thirty job titles is the jobs table, not the news.
    ``total`` is the number of vendors above the floor when ``devs`` is only
    the top of that list, so the heading says so."""
    if not devs:
        return ""
    rows = []
    for d in devs:
        attrs = d.get("attributes") or {}
        mix = ", ".join(f"{k} {v}" for k, v in sorted(
            (attrs.get("by_function") or {}).items(), key=lambda kv: -kv[1])[:3])
        vendor = ", ".join(v.get("vendor") or "" for v in d.get("vendors") or [])
        openings = str(attrs.get("openings", ""))
        # A withheld recruiter's figures are scrubbed (every digit becomes 8)
        # and blurred, like the teaser tables: blur alone leaves the real
        # numbers in the page source, and a role mix plus a count is enough
        # to name a vendor from its careers page.
        blur = ""
        if d.get("withheld"):
            mix = re.sub(r"\d", "8", mix)
            openings = re.sub(r"\d", "8", openings)
            blur = " n-blur"
        rows.append(f'<div class="n-row"><span class="n-rank"></span>'
                    f'<div><strong>{_vendor_line(d, logos) if logos else esc(vendor)}</strong>'
                    + (f'<div class="n-row-label{blur}" aria-hidden="true">{esc(mix)}</div>' if mix else "")
                    + f'</div><span class="n-row-val{blur}" aria-hidden="true">{esc(openings)}'
                    ' open roles</span></div>')
    first = devs[0]
    return (f'<article class="n-story" id="{_dev_anchor(first)}" '
            'style="--story:var(--n-green)">'
            '<div class="n-story-tag">Hiring</div>'
            + (f'<h3>Top {len(devs)} by open roles</h3>'
               if total and total > len(devs) else
               f'<h3>{len(devs)} vendors with {massess_min_openings()} or more open '
               'roles</h3>')
            + '<div class="n-byline">Job listings · this period</div>'
            + "".join(rows) + "</article>")


def massess_min_openings() -> int:
    from app.services.market_assessment import MIN_OPENINGS_FOR_HIRING
    return MIN_OPENINGS_FOR_HIRING


def _summary_unless_duplicate(dev: Dict[str, Any]) -> str:
    """The development's summary, or nothing when it repeats the headline.

    A summary that repeats the headline is not a summary. The title is
    often the post's own first line, so compare inside, not at the start.
    """
    summary = (dev.get("summary") or "").strip()
    head_key = _norm_words(dev.get("headline") or "")
    sum_key = _norm_words(summary)
    duplicate = bool(head_key) and (head_key[:60] in sum_key
                                    or sum_key[:60] in head_key)
    return "" if duplicate else summary


#: LinkedIn image variants, sharpest first. A link preview (``articleshare``)
#: is often an upscaled og:image and reads blurred at any size.
_IMAGE_KIND_RANK = ("feedshare-image-high-res", "feedshare-shrink", "image-shrink",
                    "article-cover", "image/", "articleshare")


def _image_rank(url: str) -> int:
    for i, kind in enumerate(_IMAGE_KIND_RANK):
        if kind in url:
            return i
    return len(_IMAGE_KIND_RANK)


def _dev_image(dev: Dict[str, Any], images: Optional[Dict[str, str]], *,
               previews: bool = True) -> str:
    """The sharpest image among the development's evidence records, or
    nothing. ``previews=False`` (the lead) refuses a link preview: a blurred
    picture at that size is worse than none."""
    if not images:
        return ""
    found = [images[e["uri"]] for e in (dev.get("evidence") or [])
             if e.get("uri") and images.get(e["uri"])]
    if not previews:
        found = [u for u in found if "articleshare" not in u]
    return min(found, key=_image_rank) if found else ""


def _vendor_line(dev: Dict[str, Any], logos: Optional[Dict[str, str]]) -> str:
    """The development's vendors, each with its mark when there is one."""
    names = [v.get("vendor") or "" for v in dev.get("vendors") or []]
    # One span per vendor, so a flex byline keeps the mark with its name.
    return ", ".join(f'<span class="v2-vendor">{_mark(logos, n)}{esc(n)}</span>'
                     for n in names if n)


def _render_developments(devs: List[Dict[str, Any]], *,
                         tag_for=None, images: Optional[Dict[str, str]] = None,
                         logos: Optional[Dict[str, str]] = None) -> str:
    """Material market developments, one entry per event. ``tag_for``
    names the tag over a story; the default is the event type's label.
    ``images`` maps a record's uri to its image, for a thumbnail."""
    if not devs:
        return '<p class="n-empty">No material development in the period.</p>'
    out = []
    hiring = [d for d in devs if d["event_type"] == "significant_hiring"]
    for d in devs:
        if d["event_type"] == "significant_hiring":
            continue
        colour = _KIND_COLOUR.get(d["event_type"], "var(--n-accent)")
        vendors = ", ".join(v.get("vendor") or "" for v in d.get("vendors") or [])
        image = _dev_image(d, images)
        out.append(f'<article class="n-story{" n-story-img" if image else ""}" id="{_dev_anchor(d)}" '
                   f'style="--story:{colour}">')
        if image:
            out.append(f'<img class="n-thumb" src="{esc(image)}" alt="" loading="lazy">')
        tag = tag_for(d) if tag_for else d["event_type_label"]
        out.append(f'<div class="n-story-tag">{esc(tag)}</div>')
        out.append(f'<h3>{esc(d["headline"])}</h3>')
        summary = _summary_unless_duplicate(d)
        if summary:
            out.append(f'<p class="n-story-sum">{esc(_clip(summary, 320))}</p>')
        bits = [_vendor_line(d, logos) if logos else esc(vendors),
                esc(_dev_date(d)), esc(_dev_sources(d)), esc(d["provenance_label"])]
        out.append('<div class="n-byline">' + " · ".join(b for b in bits if b) + "</div>")
        out.append(_dev_evidence_links(d))
        out.append("</article>")
    out.append(_render_hiring_block(hiring, logos=logos))
    return "".join(out)


def _render_corpus(clustered: List[Dict[str, Any]], *, collected: int,
                   shown: int) -> str:
    if not clustered:
        return ""
    head = (f'Everything we collected: the {shown} most recent of {collected} '
            'records' if collected > shown else
            f'Everything we collected: all {shown} records')
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
    if row.get("firm"):
        return str(row["firm"])
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
    # News is editorial: open to every vendor's coverage for any reader
    # (operator policy, 9 Sep 2026). Metrics stay tier-restricted elsewhere.
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
               'title="Subscribe in a feed reader">RSS</a>' + _AI_FEED_LINK.format(days=days))
    body = [f"{_FONT_LINK_V2}<style>{EXTRA_CSS}{NEWS_CSS}{DARK_CSS}{V2_CSS}</style>", '<div class="mm-news mm-v2">',
            '<div class="n-top">' + _brand_line()
            + '<nav class="n-pages" aria-label="Pages">'
            f'<a href="?{_relink(link_params, days=days, view="v2")}">Front page</a>'
            f'<a href="?{_relink(link_params, days=days, view="report")}">Analyst View</a>'
            f'{rss}{_book_link(market)}{_theme_toggle()}</nav>'
            f'<span class="n-market">{esc(market["name"])}</span></div>',
            '<main class="n-river">',
            '<div class="n-head"><div>'
            f'<div class="n-kicker">Market monitor · {esc(period_txt)}</div>'
            f'<h1>{esc(market["name"])}: news river</h1>'
            f'<p class="n-sub">{len(rows)} articles and posts matched in the '
            f'period, {len(clustered)} stories, newest first.</p></div>'
            f'<div><nav class="n-periods" aria-label="Reporting period">'
            f'{periods}</nav><nav class="n-periods" aria-label="Feeds">{rss}</nav></div></div>',
            '<section class="v2-river">' + render_news_river(clustered) + "</section>",
            "</main>",
            '<div class="n-foot">' + _brand_line()
            + f'<span>{esc(market["name"])} · {esc(period_txt)}</span></div>',
            "</div>"]
    rendered = v2_document(f'{market["name"]} — news river', "".join(body))
    rendered = ent.enforce_no_withheld(rendered, [],
                                       context=f'market {market["id"]} news river')
    return rendered.encode("utf-8")


# ---------------------------------------------------------------------------
# The front page: the same period laid out like a news site
# ---------------------------------------------------------------------------
#
# ``?view=v2``. A masthead, one lead story, and a section for each kind of
# development, with the map, the findings and the numbers in a sidebar.
# ``?view=v2&section=hiring`` is one section as its own page, listing
# everything in it for the period. Nothing here classifies: the sections are
# the developments ``market_assessment`` already returns, bucketed by their
# type, and the thought-leadership section is what the assessment computed as
# discussion and the report never showed.

#: A dark site with each page as one light card on it. The disclosure
#: footer and the shared-view note sit on the dark ground, so they take the
#: masthead's muted text colour. Emitted by every page of the report.
DARK_CSS = """
html, body { background:#1a1523; }
/* The disclosure footer carries an inline grey, invisible on the dark ground. */
.container > .ai-disclosure, .container > p.mm-src { color:#bcbac7 !important; }
.container > .ai-disclosure a, .container > p.mm-src a { color:#f2eff3; }
.mm-news { border-color:#2d2a37; box-shadow:0 12px 40px rgba(0,0,0,.35); }
"""

V2_CSS = """/* ---- aisocnews design system (aunoo-aisocnews-design-system.md, Sept 2026).
   Tokens live on <html> so the page ground can use them; everything else is
   scoped under .mm-v2. Light is the default and is declared in the markup
   (html[data-theme="light"]); dark is opt-in through the toggle in the bar.
   prefers-color-scheme is deliberately not consulted (spec §2.1). */
html {
  --area-outer:#1A1B1E; --nav-bg:#212225; --area-bg:#ECEDF3;
  --wrap:rgba(255,255,255,.80); --wrap-2:rgba(255,255,255,.55);
  --sidebar-border:#e0e1e9; --separator-dark:rgba(181,178,188,.15); --mark-bg:#F2F1F6;
  --text-primary:#1a1a2e; --text-secondary:#3d3a4a; --text-muted:#65636D;
  --text-subtle:#9b99a6; --text-on-dark:#B5B2BC; --text-timestamp:#c0bdc8;
  --accent:#6E56CF; --accent-strong:#6E56CF; --accent-strong-hover:#5B45B8;
  --accent-ink:#5B45B8; --accent-text-active:#B9A6FF;
  --accent-tint-30:rgba(110,86,207,.30); --accent-tint-15:rgba(110,86,207,.15);
  --accent-tint-08:rgba(110,86,207,.08); --on-accent:#FFFFFF;
  --beat-moves:#8145B5; --beat-launches:#0D74CE; --beat-hiring:#1F7A4A;
  --beat-cases:#BF4900; --beat-voices:#5B45B8; --beat-social:#00658A; --beat-research:#8A6212;
  --m-green:#1F7A4A; --m-red:#C42A2F; --m-amber:#8A6212; --m-orange:#BF4900;
  --live:#4CAF50; --star-active:#E8A838; --mention:#0D74CE; --mention-tint:rgba(13,116,206,.10);
  --chip-soft:rgba(0,0,0,.05); --chip-soft-hover:rgba(0,0,0,.09); --chip-count:rgba(0,0,0,.08);
  --chip-muted:rgba(101,99,109,.08); --chip-muted-hover:rgba(101,99,109,.14);
  --chip-dark:rgba(235,234,248,.0784);
  --shadow-hairline:0 1px 2px rgba(26,26,46,.04); --shadow-lift:0 2px 14px rgba(26,26,46,.08);
  --shadow-pop:0 12px 32px rgba(26,26,46,.16); --shadow-panel:0 18px 48px rgba(0,0,0,.42);
  --w-read:400;
  --font-sans:"Geist", ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  --font-read:"Literata", Georgia, "Times New Roman", serif;
  --fs-micro:11px; --fs-meta:12px; --fs-small:13px; --fs-body:14px; --fs-lead:16px;
  --fs-h3:18px; --fs-h2:21px; --fs-h1:26px;
  --s-1:4px; --s-2:8px; --s-3:12px; --s-4:16px; --s-5:20px; --s-6:24px; --s-7:32px; --s-8:40px;
  --area-gap:16px;
  --r-xs:3px; --r-sm:4px; --r-md:5px; --r-control:8px; --r-xl:10px; --r-2xl:12px;
  --r-card:14px; --r-area:16px; --r-pill:999px;
  --t-fast:.13s ease; --t:.2s ease;
  color-scheme:light;
}
html[data-theme="dark"] {
  --area-outer:#0B0C0D; --nav-bg:#17181A; --area-bg:#1F2023;
  --wrap:rgba(255,255,255,.045); --wrap-2:rgba(255,255,255,.028);
  --sidebar-border:rgba(181,178,188,.16); --separator-dark:rgba(181,178,188,.14); --mark-bg:#CFCBD8;
  --text-primary:#ECEBF0; --text-secondary:#C9C6D1; --text-muted:#A09DA8;
  --text-subtle:#83808C; --text-timestamp:#7B7885;
  --accent:#7B62DD; --accent-strong:#7B62DD; --accent-strong-hover:#8B74E8; --accent-ink:#B9A6FF;
  --accent-tint-30:rgba(123,98,221,.32); --accent-tint-15:rgba(123,98,221,.18);
  --accent-tint-08:rgba(123,98,221,.10);
  --beat-moves:#B08CE0; --beat-launches:#5EACEA; --beat-hiring:#48B77A;
  --beat-cases:#F0762B; --beat-voices:#B9A6FF; --beat-social:#3FAFC9; --beat-research:#D2A03C;
  --m-green:#48B77A; --m-red:#F0666B; --m-amber:#D2A03C; --m-orange:#F0762B; --mention:#5EACEA;
  --chip-soft:rgba(255,255,255,.06); --chip-soft-hover:rgba(255,255,255,.10); --chip-count:rgba(255,255,255,.09);
  --chip-muted:rgba(235,234,248,.07); --chip-muted-hover:rgba(235,234,248,.12);
  --shadow-hairline:0 1px 2px rgba(0,0,0,.35); --shadow-lift:0 2px 14px rgba(0,0,0,.4);
  --shadow-pop:0 12px 32px rgba(0,0,0,.55); --shadow-panel:0 18px 48px rgba(0,0,0,.5);
  --w-read:450;
  color-scheme:dark;
}
/* The page ground is dark in both themes; one light panel floats inside it. */
html, body { background:var(--area-outer); }
body { font-family:var(--font-sans); color:var(--text-primary); }
.container { max-width:1240px; padding:var(--area-gap) var(--area-gap) var(--s-8); }
.container > .ai-disclosure, .container > p.mm-src { color:var(--text-on-dark) !important;
  border-top-color:var(--separator-dark) !important; font-family:var(--font-sans); }
.container > .ai-disclosure a, .container > p.mm-src a { color:var(--accent-text-active); }
/* The old names, remapped so the shared news rules pick up the new values.
   Also on a nested .mm-news, whose own rule would otherwise reset them. */
.mm-news.mm-v2, .mm-v2 .mm-news { --n-bg:var(--area-bg); --n-shell:var(--wrap); --n-panel:var(--wrap); --n-text:var(--text-primary);
  --n-muted:var(--text-muted); --n-line:var(--sidebar-border); --n-accent:var(--accent-ink);
  --n-accent-soft:var(--accent-tint-08); --n-blue:var(--beat-launches); --n-green:var(--beat-hiring);
  --n-orange:var(--beat-cases); --n-purple:var(--beat-moves); --n-cyan:var(--beat-social);
  --n-amber:var(--beat-research); }
.mm-news.mm-v2 { font-family:var(--font-sans);
  margin:0 0 var(--s-4); border:0; border-radius:var(--r-area); box-shadow:var(--shadow-panel);
  background:var(--area-bg); color:var(--text-primary); line-height:1.5; }
.mm-v2 ::selection { background:var(--accent-tint-30); }
.mm-v2 :focus-visible { outline:2px solid var(--accent); outline-offset:2px; border-radius:var(--r-xs); }
.mm-v2 a { color:var(--accent-ink); }
.mm-v2 a, .mm-v2 button, .mm-v2 summary { transition:color var(--t-fast), background-color var(--t-fast), border-color var(--t-fast); }
.mm-v2 h1, .mm-v2 h2, .mm-v2 h3, .mm-v2 h4 { color:var(--text-primary); font-weight:600;
  line-height:1.24; letter-spacing:-.018em; text-wrap:pretty; margin:0; }
.mm-v2 img { max-width:100%; }
.mm-v2 [hidden] { display:none !important; }
.mm-v2 .n-num, .mm-v2 .n-rank, .mm-v2 .n-row-val, .mm-v2 .n-metric-value, .mm-v2 .v2-bar-n,
.mm-v2 .v2-move, .mm-v2 .n-delta { font-variant-numeric:tabular-nums; }
/* Reading prose is the serif; everything else is the sans. */
.mm-v2 .n-story-sum, .mm-v2 .v2-hl-body > p, .mm-v2 .n-quote, .mm-v2 .v2-piece-body,
.mm-v2 .v2-about p, .mm-v2 .mm-trial > p, .mm-v2 .v2-side .n-block > p, .mm-v2 .n-summary p,
.mm-v2 .n-sub, .mm-v2 .v2-inq p { font-family:var(--font-read); font-optical-sizing:auto;
  font-weight:var(--w-read); font-size:var(--fs-body); line-height:1.6; color:var(--text-secondary); }
.mm-v2 .n-story-sum { margin:var(--s-2) 0 0; max-width:66ch; }
/* ---- chrome bar (top) and footer: dark in both themes */
.mm-v2 .n-top, .mm-v2 .n-foot { background:var(--nav-bg); color:var(--text-on-dark);
  padding:var(--s-3) var(--s-6); gap:var(--s-2) var(--s-3); border-color:var(--separator-dark);
  font-size:var(--fs-meta); letter-spacing:.006em; }
.mm-v2 .n-top { border-bottom:1px solid var(--separator-dark); }
.mm-v2 .n-foot { border-top:1px solid var(--separator-dark); line-height:1.6; }
.mm-v2 .n-foot > span:last-child { color:var(--text-on-dark); }
.mm-v2 .n-foot a { color:inherit; text-decoration:underline; text-decoration-color:var(--separator-dark); }
.mm-v2 .n-foot a:hover { color:#fff; text-decoration-color:currentColor; }
.mm-v2 .n-brand { font-size:var(--fs-small); font-weight:500; color:var(--text-on-dark); }
.mm-v2 .n-brand a { color:inherit; }
.mm-v2 .n-brand a:hover { color:#fff; }
.mm-v2 .n-brand-made { font-size:var(--fs-meta); color:var(--text-on-dark); }
.mm-v2 .n-market { color:var(--text-on-dark); font-size:var(--fs-meta); }
.mm-v2 .n-pages { gap:var(--s-1); margin-left:auto; flex-wrap:wrap; }
.mm-v2 .n-pages a, .mm-v2 .n-theme { display:inline-flex; align-items:center; gap:6px;
  min-height:36px; padding:0 var(--s-3); border:0; border-radius:var(--r-control);
  background:transparent; color:var(--text-on-dark); font:inherit; font-size:var(--fs-meta);
  font-weight:500; line-height:1.2; text-decoration:none; white-space:nowrap; cursor:pointer; }
.mm-v2 .n-pages a:hover, .mm-v2 .n-theme:hover { background:var(--chip-dark); color:#fff; }
.mm-v2 .n-pages a.n-rss { border:0; background:transparent; }
.mm-v2 .n-rss svg, .mm-v2 .n-ai svg { width:13px; height:13px; color:currentColor; }
/* One filled button in the bar (Hick's Law): Submit news. Everything else is quiet. */
.mm-v2 .n-pages a.n-tip { background:var(--accent-strong); color:var(--on-accent); font-weight:500; }
.mm-v2 .n-pages a.n-tip:hover { background:var(--accent-strong-hover); color:var(--on-accent); filter:none; }
.mm-v2 .n-pages a.n-book { border:0; color:var(--text-on-dark); font-weight:500; }
.mm-v2 .n-pages a.n-book:hover { background:var(--chip-dark); color:#fff; }
.mm-v2 .n-theme { width:36px; height:36px; padding:0; justify-content:center; }
.mm-v2 .n-theme svg { width:16px; height:16px; }
.mm-v2 .n-theme .n-theme-moon { display:none; }
html[data-theme="dark"] .mm-v2 .n-theme .n-theme-moon { display:block; }
html[data-theme="dark"] .mm-v2 .n-theme .n-theme-sun { display:none; }
.mm-v2 .n-jump { gap:var(--s-1); padding-top:var(--s-2); border-top:1px solid var(--separator-dark); }
.mm-v2 .n-jump a, .mm-v2 .n-jump .n-jump-label { display:inline-flex; align-items:center; min-height:32px;
  padding:0 var(--s-3); border-radius:var(--r-control); color:var(--text-on-dark);
  font-size:var(--fs-small); font-weight:500; text-decoration:none; border:0; }
.mm-v2 .n-jump a:hover, .mm-v2 .n-jump a[aria-current="page"] { background:var(--accent-tint-30);
  color:var(--accent-text-active); }
.mm-v2 .n-jump-page { border:0; color:var(--text-on-dark); }
.mm-v2 .n-top .n-market { display:none; }
/* ---- masthead */
.mm-v2 .v2-mast, .mm-v2 div.n-head { display:flex; justify-content:space-between; align-items:flex-end; flex-wrap:wrap;
  margin:0;
  gap:var(--s-4) var(--s-6); padding:var(--s-7) var(--s-7) var(--s-5);
  border-bottom:1px solid var(--sidebar-border); }
.mm-v2 .v2-mast h1, .mm-v2 div.n-head h1 { font-size:clamp(32px,4.8vw,52px); font-weight:600; line-height:1.0;
  letter-spacing:-.038em; color:var(--text-primary); }
.mm-v2 .n-kicker { color:var(--text-muted); font-size:var(--fs-meta); font-weight:500;
  letter-spacing:.006em; text-transform:none; margin:0 0 var(--s-2); }
.mm-v2 .v2-mast .n-sub, .mm-v2 .n-sub { margin:var(--s-2) 0 0; max-width:62ch; font-size:var(--fs-lead); }
.mm-v2 .n-period { color:var(--text-timestamp); font-size:var(--fs-meta); letter-spacing:.006em;
  margin-top:var(--s-2); text-align:right; }
/* Segmented control */
.mm-v2 .n-periods { display:inline-flex; gap:0; padding:2px; margin:0; background:var(--chip-soft);
  border-radius:10px; justify-content:flex-start; }
.mm-v2 .n-periods + .n-periods { margin-left:var(--s-2); }
.mm-v2 .n-periods a { display:inline-flex; align-items:center; min-height:32px; padding:0 var(--s-3);
  border:0; border-radius:var(--r-control); background:transparent; color:var(--text-muted);
  font-size:var(--fs-small); font-weight:500; line-height:1.2; }
.mm-v2 .n-periods a:hover { background:var(--wrap-2); color:var(--text-primary); }
.mm-v2 .n-periods a[aria-current="page"] { background:var(--accent-strong); color:var(--on-accent); }
.mm-v2 .n-periods .n-rss { margin-left:var(--s-2); }
/* ---- the grid: main 2, rail 1 */
.mm-v2 .v2-grid { display:grid; grid-template-columns:minmax(0,2fr) minmax(280px,1fr);
  gap:var(--s-5); align-items:start; padding:var(--s-5) var(--s-6); }
.mm-v2 .v2-main { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:var(--s-5);
  align-content:start; min-width:0; }
.mm-v2 .v2-main.v2-one { grid-template-columns:1fr; }
.mm-v2 .v2-lead, .mm-v2 .v2-wide { grid-column:1/-1; }
.mm-v2 .v2-side { display:grid; gap:var(--s-5); align-content:start; min-width:0; }
/* ---- content box: a fill and a hairline, no shadow */
.mm-v2 .v2-sec, .mm-v2 .v2-card, .mm-v2 .v2-lead > .v2-lead-story, .mm-v2 .v2-findings,
.mm-v2 .v2-side > .n-block, .mm-v2 .mm-trial, .mm-v2 .v2-about, .mm-v2 .v2-one > .v2-piece-page,
.mm-v2 .v2-one > .mm-news { background:var(--wrap); border:1px solid var(--sidebar-border);
  border-radius:var(--r-card); padding:var(--s-5) var(--s-6) var(--s-4); min-width:0; }
.mm-v2 .v2-sec { border-top:2px solid var(--sec,var(--accent)); }
.mm-v2 .v2-card, .mm-v2 .v2-side > .n-block { padding:var(--s-5); }
.mm-v2 .v2-lead { display:grid; gap:var(--s-5); }
.mm-v2 .v2-lead > .v2-lead-story { border-top:2px solid var(--accent); padding:var(--s-6); }
.mm-v2 .mm-trial { border-top:2px solid var(--accent); margin:var(--s-5) var(--s-6) var(--s-6); }
/* Section head: title in the beat hue, the "All N" link quiet */
.mm-v2 .v2-sec .n-sec-head { border:0; padding:0; align-items:baseline; gap:var(--s-3); }
.mm-v2 .v2-sec .n-sec-head h2 { font-size:var(--fs-h2); font-weight:600; line-height:1.24;
  letter-spacing:-.022em; text-transform:none; color:var(--sec,var(--accent-ink)); }
.mm-v2 .v2-more { font-size:var(--fs-meta); font-weight:500; color:var(--text-muted); letter-spacing:.006em; }
.mm-v2 .v2-more:hover { color:var(--accent-ink); }
.mm-v2 .v2-subline { margin:var(--s-1) 0 0; font-size:var(--fs-meta); color:var(--text-muted);
  letter-spacing:.006em; line-height:1.6; }
.mm-v2 .v2-strip { font-size:var(--fs-small); margin:var(--s-3) 0 0; color:var(--text-secondary); }
.mm-v2 .v2-strip strong { font-weight:600; color:var(--text-primary); font-variant-numeric:tabular-nums; }
.mm-v2 .v2-sub { font-size:var(--fs-meta); font-weight:500; text-transform:none; letter-spacing:.006em;
  color:var(--text-muted); margin:var(--s-4) 0 var(--s-1); }
/* Rail card titles */
.mm-v2 .v2-card > h2, .mm-v2 .v2-side .n-block .n-sec-head h2, .mm-v2 .n-card-title h2 {
  font-size:var(--fs-h3); font-weight:600; line-height:1.24; letter-spacing:-.02em; text-transform:none;
  color:var(--text-primary); border:0; padding:0; margin:0; }
.mm-v2 .v2-card > h2 { border-bottom:1px solid var(--sidebar-border); padding-bottom:var(--s-3);
  margin-bottom:var(--s-1); }
.mm-v2 .v2-side .n-block .n-sec-head { flex-direction:column; align-items:flex-start; gap:var(--s-1);
  border-bottom:1px solid var(--sidebar-border); padding-bottom:var(--s-3); margin-bottom:var(--s-3); }
.mm-v2 .v2-side .n-block h3 { font-size:var(--fs-lead); font-weight:600; line-height:1.32; margin:var(--s-2) 0; }
.mm-v2 .v2-side .n-block > p { margin:0 0 var(--s-3); }
.mm-v2 .n-updated { color:var(--text-muted); font-size:var(--fs-meta); letter-spacing:.006em; }
/* ---- stories */
.mm-v2 .n-story { padding:var(--s-4) 0; border-bottom:1px solid var(--sidebar-border); }
.mm-v2 .n-story:last-child { border-bottom:0; padding-bottom:var(--s-1); }
.mm-v2 .n-story h3, .mm-v2 .n-story h2 { font-size:var(--fs-h3); font-weight:600; line-height:1.32;
  letter-spacing:-.018em; margin:0; }
.mm-v2 .v2-sec .n-story h3 { font-size:17px; line-height:1.34; }
.mm-v2 .n-story h3 a, .mm-v2 .n-story h2 a { color:inherit; text-decoration:none; }
.mm-v2 .n-story h3 a:hover, .mm-v2 .n-story h2 a:hover { color:var(--accent-ink); }
.mm-v2 .v2-sec .n-story-sum { font-size:var(--fs-body); }
/* Badge: a 13% tint of the story's hue, the hue as text */
.mm-v2 .n-story-tag { display:inline-flex; align-items:center; justify-self:start; width:auto;
  padding:var(--s-1) var(--s-3); border-radius:var(--r-sm); margin:0 0 var(--s-2);
  font-size:var(--fs-micro); font-weight:500; line-height:1.4; letter-spacing:.01em; text-transform:none;
  color:var(--story,var(--accent-ink));
  background:color-mix(in srgb, var(--story,var(--accent-ink)) 13%, transparent); }
.mm-v2 .n-story-tag:empty { display:none; }
/* Byline and provenance */
.mm-v2 .n-byline { display:block; margin-top:var(--s-2); color:var(--text-muted); font-size:var(--fs-meta);
  line-height:1.6; letter-spacing:.006em; }
.mm-v2 .n-byline a { color:var(--accent-ink); text-decoration:none; }
.mm-v2 .n-byline a:hover { text-decoration:underline; }
.mm-v2 .n-support { margin-top:var(--s-2); padding:var(--s-2) var(--s-3); background:var(--chip-muted);
  border-left:2px solid var(--chip-count); border-radius:0 var(--r-md) var(--r-md) 0;
  color:var(--text-muted); font-size:var(--fs-meta); line-height:1.6; letter-spacing:.006em; }
.mm-v2 .n-support strong { color:var(--text-secondary); font-weight:500; }
.mm-v2 .n-support a { color:var(--text-muted); text-decoration:underline; text-decoration-color:var(--chip-count); }
.mm-v2 .n-support a:hover { color:var(--accent-ink); text-decoration-color:currentColor; }
.mm-v2 .n-why { color:var(--text-secondary); font-size:var(--fs-meta); }
/* Thumbnails: 16:10, the middle kept; the lead's shown whole */
.mm-v2 .n-story-img { display:grid; grid-template-columns:minmax(0,1fr) clamp(104px,30%,152px); gap:var(--s-1) var(--s-4); }
.mm-v2 .n-story-img > * { grid-column:1; }
.mm-v2 .n-story-img > .n-thumb { grid-column:2; grid-row:1 / span 6; width:100%; height:auto;
  aspect-ratio:16/10; object-fit:cover; object-position:center; border-radius:var(--r-xl);
  background:var(--chip-soft); border:0; }
.mm-v2 .v2-sec .n-story-img { grid-template-columns:minmax(0,1fr) clamp(84px,24%,120px); }
.mm-v2 .v2-lead-story.n-story-img { grid-template-columns:minmax(0,1fr) clamp(220px,32%,320px); gap:var(--s-2) var(--s-6); }
.mm-v2 .v2-lead-story.n-story-img > .n-thumb { object-fit:contain; border-radius:var(--r-2xl); background:var(--chip-soft); }
/* The lead */
.mm-v2 .v2-lead-story { padding-top:var(--s-6); }
.mm-v2 .v2-lead-story h2 { font-size:clamp(26px,3.2vw,36px); line-height:1.18; letter-spacing:-.03em;
  font-weight:600; margin:var(--s-1) 0 0; }
.mm-v2 .v2-lead-story .n-story-sum { font-size:var(--fs-lead); max-width:62ch; }
/* Highlights: a neutral box of disclosure rows */
.mm-v2 .v2-findings { counter-reset:hl; }
.mm-v2 .v2-findings h2 { font-size:var(--fs-h3); font-weight:600; letter-spacing:-.02em; text-transform:none;
  margin:0; padding:0 0 var(--s-3); border:0; border-bottom:1px solid var(--sidebar-border); }
.mm-v2 .v2-hl { border-bottom:1px solid var(--sidebar-border); padding:0; counter-increment:hl; }
.mm-v2 .v2-hl:last-child { border-bottom:0; }
.mm-v2 .v2-hl > summary { min-height:52px; margin:0 calc(-1 * var(--s-2)); padding:var(--s-3) var(--s-2);
  border-radius:var(--r-control); display:grid; grid-template-columns:22px minmax(0,1fr) 28px; gap:var(--s-3);
  align-items:center; font-size:var(--fs-h3); font-weight:500; line-height:1.35; letter-spacing:-.012em;
  color:var(--text-primary); list-style:none; cursor:pointer; }
.mm-v2 .v2-hl > summary::-webkit-details-marker, .mm-v2 .v2-mv > summary::-webkit-details-marker { display:none; }
.mm-v2 .v2-hl > summary::before { content:counter(hl); width:auto; height:auto; border-radius:0;
  background:transparent; color:var(--accent-ink); font-size:var(--fs-small); font-weight:600;
  font-variant-numeric:tabular-nums; display:block; text-align:left; }
.mm-v2 .v2-hl > summary::after { content:"+"; color:var(--text-subtle); font-size:18px; line-height:1;
  text-align:center; width:28px; }
.mm-v2 .v2-hl[open] > summary::after { content:"\\2212"; }
.mm-v2 .v2-hl > summary:hover { background:var(--chip-soft); color:var(--accent-ink); }
.mm-v2 .v2-hl > summary:hover::after { color:var(--accent-ink); }
.mm-v2 .v2-hl-body { padding:0 0 var(--s-3) 34px; animation:v2-reveal .16s ease; }
.mm-v2 .v2-hl-body > p { margin:0; }
@keyframes v2-reveal { from { opacity:0; transform:translateY(-2px); } to { opacity:1; transform:none; } }
.mm-v2 .n-evidence { margin:var(--s-2) 0 0; padding-left:18px; color:var(--text-muted);
  font-size:var(--fs-meta); line-height:1.6; letter-spacing:.006em; }
.mm-v2 .n-evidence a { color:var(--text-muted); text-decoration:underline; text-decoration-color:var(--chip-count); }
.mm-v2 .n-evidence a:hover { color:var(--accent-ink); text-decoration-color:currentColor; }
/* Data rows */
.mm-v2 .n-row { grid-template-columns:22px minmax(0,1fr) auto; gap:var(--s-3); padding:var(--s-3) 0;
  border-bottom:1px solid var(--sidebar-border); font-size:var(--fs-small); }
.mm-v2 .n-row:last-child { border-bottom:0; }
.mm-v2 .n-rank { color:var(--text-subtle); }
.mm-v2 .n-row strong { font-weight:500; color:var(--text-primary); }
.mm-v2 .n-row-val { font-weight:500; color:var(--text-primary); }
.mm-v2 .n-row-label { font-size:var(--fs-meta); color:var(--text-muted); letter-spacing:.006em; }
/* Bar rows: name, track, value, trailing note */
.mm-v2 .v2-bars { display:grid; gap:var(--s-2); margin-top:var(--s-2); }
.mm-v2 .v2-bars + .v2-sub { margin-top:var(--s-4); }
.mm-v2 .v2-bar { display:grid; grid-template-columns:minmax(0,1fr) 68px auto auto; gap:var(--s-2);
  align-items:center; font-size:var(--fs-small); }
.mm-v2 .v2-bar-name { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-weight:500; color:var(--text-primary); }
.mm-v2 .v2-bar-name a { color:inherit; text-decoration:none; }
.mm-v2 .v2-bar-track { height:7px; background:var(--chip-count); border-radius:var(--r-pill); overflow:hidden; }
.mm-v2 .v2-bar-fill { height:100%; background:var(--accent); border-radius:var(--r-pill); }
.mm-v2 .v2-bar-n { min-width:2.2em; text-align:right; font-weight:500; color:var(--text-primary); }
.mm-v2 .v2-move { font-size:var(--fs-micro); white-space:nowrap; }
.mm-v2 .v2-vendor { white-space:nowrap; }
.mm-v2 .v2-move.up { color:var(--m-green); }
.mm-v2 .v2-move.down { color:var(--m-orange); }
.mm-v2 .v2-move.same { color:var(--text-subtle); }
.mm-v2 .v2-bar-name a:hover { color:var(--accent-ink); }
/* Who moved: compact disclosure rows */
.mm-v2 .v2-mv { border-bottom:1px solid var(--sidebar-border); padding:0; }
.mm-v2 .v2-mv:last-child { border-bottom:0; }
.mm-v2 .v2-mv > summary { list-style:none; cursor:pointer; display:grid; align-items:center; min-height:48px; margin:0 calc(-1 * var(--s-2)); padding:var(--s-3) var(--s-2);
  border-radius:var(--r-control); grid-template-columns:minmax(0,1fr) 28px; gap:var(--s-2); }
.mm-v2 .v2-mv > summary::after { content:"+"; color:var(--text-subtle); font-size:18px; width:28px; text-align:center; }
.mm-v2 .v2-mv[open] > summary::after { content:"\\2212"; }
.mm-v2 .v2-mv > summary:hover { background:var(--chip-soft); }
.mm-v2 .v2-mv > summary:hover strong, .mm-v2 .v2-mv > summary:hover .v2-mv-head a,
.mm-v2 .v2-mv > summary:hover::after { color:var(--accent-ink); }
.mm-v2 .v2-mv-head { margin:0; font-size:var(--fs-small); font-weight:500; line-height:1.35; }
.mm-v2 .v2-mv-head a { color:var(--text-primary); text-decoration:none; }
.mm-v2 .v2-mv-head a:hover { color:var(--accent-ink); }
.mm-v2 .v2-mv-body { padding:0 0 var(--s-3); font-size:var(--fs-small); animation:v2-reveal .16s ease; }
.mm-v2 .v2-mv-body .n-story-sum { font-size:var(--fs-small); margin-top:var(--s-1); }
/* Social and thought-leadership quotes */
.mm-v2 .n-social { padding:var(--s-3) 0; border-bottom:1px solid var(--sidebar-border); }
.mm-v2 .n-social:last-of-type { border-bottom:0; }
.mm-v2 .n-social-meta { color:var(--text-muted); font-size:var(--fs-meta); letter-spacing:.006em; line-height:1.6; }
.mm-v2 .n-quote { margin:var(--s-1) 0 0; font-size:17px; line-height:1.5; color:var(--text-primary); }
.mm-v2 .n-quote a { color:inherit; }
.mm-v2 .n-quote a:hover { color:var(--accent-ink); text-decoration:underline; }
/* Research: the cited-by line */
.mm-v2 .v2-rs-cited { margin:var(--s-1) 0 0; font-size:var(--fs-meta); color:var(--text-muted); letter-spacing:.006em; }
.mm-v2 .v2-rs-cited a { color:var(--text-secondary); text-decoration:none; white-space:nowrap; }
.mm-v2 .v2-rs-cited a:hover { text-decoration:underline; }
.mm-v2 .v2-rs-cited a:hover { color:var(--accent-ink); }
/* Third-party logos on a light ground; the mark is often dark-on-transparent */
.mm-v2 .v2-mark { width:18px; height:18px; border-radius:var(--r-sm); background:var(--mark-bg);
  object-fit:contain; vertical-align:-4px; margin-right:5px; }
.mm-v2 .v2-rs-cited .v2-mark { width:16px; height:16px; }
/* Metric tiles: a nested tile drops back to the panel colour */
.mm-v2 .n-metrics { gap:var(--s-3); margin-bottom:var(--s-3); }
.mm-v2 .v2-numbers { grid-template-columns:repeat(2,minmax(0,1fr)); margin:var(--s-3) 0 0; }
.mm-v2 .v2-numbers .n-metric { cursor:help; }
.mm-v2 .n-metric { background:var(--area-bg); border:1px solid var(--sidebar-border); border-radius:var(--r-xl);
  padding:var(--s-3) var(--s-4); }
.mm-v2 .n-metric-top { color:var(--text-muted); font-size:var(--fs-meta); letter-spacing:.006em; }
.mm-v2 .n-metric-value { margin-top:var(--s-2); font-size:28px; font-weight:600; line-height:1; letter-spacing:-.036em;
  color:var(--text-primary); }
.mm-v2 .n-delta { color:var(--text-subtle); font-size:var(--fs-micro); margin-top:var(--s-1); }
.mm-v2 .n-spark path { stroke:var(--accent); }
.mm-v2 .n-spark .base { stroke:var(--sidebar-border); }
.mm-v2 .n-nospark { color:var(--text-subtle); font-size:var(--fs-micro); }
.mm-v2 .n-note { color:var(--text-muted); font-size:var(--fs-meta); margin-top:var(--s-4); letter-spacing:.006em; }
.mm-v2 .n-distil { font-size:var(--fs-small); color:var(--text-muted); }
.mm-v2 .n-empty { color:var(--text-muted); font-size:var(--fs-small); padding:var(--s-3) 0; }
/* Topics card */
.mm-v2 .v2-topic a { color:var(--text-primary); }
.mm-v2 .v2-topic a:hover { color:var(--accent-ink); }
/* The Market Maturity Map: the SVG carries hardcoded fills, remapped here so
   the theme switch works without touching the drawing. */
.mm-v2 .v2-hz svg { width:100%; height:auto; max-width:none; }
.mm-v2 .v2-hz svg svg, .mm-v2 .v2-hz .mm-hz-legend, .mm-v2 .v2-hz .mm-hz-axis { display:none; }
.mm-v2 .v2-hz svg text { font-size:26px; font-family:var(--font-sans); }
.mm-v2 .v2-hz svg text.mm-lbl { font-size:22px; }
.mm-v2 .mm-hz svg [fill="#f8fafc"] { fill:var(--wrap-2); }
.mm-v2 .mm-hz svg [stroke="#f8fafc"] { stroke:var(--wrap); }
.mm-v2 .mm-hz svg [stroke="#e2e8f0"], .mm-v2 .mm-hz svg [stroke="#cbd5e1"] { stroke:var(--sidebar-border); }
.mm-v2 .mm-hz svg [fill="#64748b"], .mm-v2 .mm-hz svg [fill="#475569"], .mm-v2 .mm-hz svg [fill="#334155"] { fill:var(--text-muted); }
.mm-v2 .mm-hz svg [stroke="#64748b"], .mm-v2 .mm-hz svg [stroke="#334155"] { stroke:var(--text-muted); }
.mm-v2 .mm-hz svg [fill="#94a3b8"] { fill:var(--text-subtle); }
.mm-v2 .mm-hz svg [fill="#0f172a"], .mm-v2 .mm-hz svg [fill="#1e293b"] { fill:var(--text-primary); }
.mm-v2 .mm-hz svg [stroke="#0f172a"] { stroke:var(--text-primary); }
.mm-v2 .mm-hz svg [stroke="#1d4ed8"] { stroke:var(--mention); }
.mm-v2 .mm-hz svg [stroke="#b45309"] { stroke:var(--m-amber); }
.mm-v2 .mm-hz-pt.mm-on .mm-core { fill:var(--accent); }
.mm-v2 .mm-hz-tip { background:var(--area-bg); border:1px solid var(--sidebar-border); border-radius:var(--r-control);
  padding:var(--s-2) var(--s-3); font-size:var(--fs-meta); color:var(--text-primary); box-shadow:var(--shadow-pop);
  max-width:20rem; }
.mm-v2 .mm-hz-tip .mm-src, .mm-v2 .mm-src { color:var(--text-muted); font-size:var(--fs-meta); }
.mm-v2 .mm-hz-switch button, .mm-v2 .mm-hz-chips button, .mm-v2 .mm-hz-show button { font-family:inherit;
  font-size:var(--fs-meta); min-height:28px; padding:0 var(--s-3); border:1px solid var(--sidebar-border);
  border-radius:var(--r-control); background:transparent; color:var(--text-muted); cursor:pointer; }
.mm-v2 .mm-hz-switch button[aria-selected="true"], .mm-v2 .mm-hz-show button[aria-pressed="true"] {
  background:var(--accent-strong); border-color:var(--accent-strong); color:var(--on-accent); }
/* ---- our pieces, about, topic pages */
.mm-v2 .v2-piece h3 a, .mm-v2 .v2-piece h2 a { color:inherit; text-decoration:none; }
.mm-v2 .v2-piece h3 a:hover, .mm-v2 .v2-piece h2 a:hover { color:var(--accent-ink); }
.mm-v2 #v2-analysis .n-story { display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:var(--s-5); }
.mm-v2 #v2-analysis .v2-piece { display:block; }
.mm-v2 #v2-analysis > .v2-piece + .v2-piece { border-top:0; }
.mm-v2 .v2-piece-page h1 { font-size:clamp(26px,3.2vw,36px); line-height:1.18; letter-spacing:-.03em;
  margin:var(--s-1) 0 var(--s-2); font-weight:600; }
.mm-v2 .v2-piece-page > .n-byline { font-size:var(--fs-small); margin-bottom:var(--s-5); }
.mm-v2 .v2-piece-body { max-width:66ch; font-size:var(--fs-lead); }
.mm-v2 .v2-piece-body h2 { font-size:var(--fs-h2); letter-spacing:-.022em; margin:var(--s-6) 0 var(--s-2); font-family:var(--font-sans); }
.mm-v2 .v2-piece-body h3 { font-size:var(--fs-h3); letter-spacing:-.02em; margin:var(--s-5) 0 var(--s-2); font-family:var(--font-sans); }
.mm-v2 .v2-piece-body p, .mm-v2 .v2-piece-body li { margin:0 0 var(--s-3); }
.mm-v2 .v2-piece-body blockquote { border-left:2px solid var(--chip-count); margin:0 0 var(--s-3);
  padding:var(--s-1) var(--s-4); color:var(--text-muted); }
.mm-v2 .v2-piece-body table { border-collapse:collapse; font-size:var(--fs-body); font-family:var(--font-sans); }
.mm-v2 .v2-piece-body td, .mm-v2 .v2-piece-body th { border:1px solid var(--sidebar-border); padding:var(--s-1) var(--s-2); }
.mm-v2 .v2-ai-note { max-width:66ch; margin:var(--s-6) 0 0; font-size:var(--fs-meta); color:var(--text-muted); }
.mm-v2 .v2-ai-note .ai-disclosure { border-top-color:var(--sidebar-border) !important; color:var(--text-muted) !important; padding-left:0 !important; }
.mm-v2 .v2-ai-note p { margin:var(--s-1) 0 0; }
.mm-v2 .v2-ai-note a { color:inherit; }
.mm-v2 .v2-about { max-width:none; }
.mm-v2 .v2-about .v2-mast { padding:0 0 var(--s-5); }
.mm-v2 .v2-about section { margin-top:var(--s-6); max-width:66ch; }
.mm-v2 .v2-about h2 { font-size:var(--fs-h2); letter-spacing:-.022em; text-transform:none; margin:0 0 var(--s-2);
  border:0; padding:0; }
.mm-v2 .v2-about p { margin:0 0 var(--s-3); }
.mm-v2 .mm-news { margin:0; border:0; border-radius:0; box-shadow:none; background:transparent; overflow:visible; }
.mm-v2 .n-block > p:not([class]), .mm-v2 .section p:not([class]), .mm-v2 .section li, .mm-v2 .mm-drawer-body > p:not([class]) {
  font-family:var(--font-read); font-optical-sizing:auto; font-weight:var(--w-read); font-size:var(--fs-body); line-height:1.6;
  color:var(--text-secondary); max-width:66ch; }
.mm-v2 .v2-one > .mm-news .n-river { padding:0; }
.mm-v2 .n-day { color:var(--text-muted); font-size:var(--fs-meta); font-weight:500; letter-spacing:.006em;
  text-transform:none; border-bottom:1px solid var(--sidebar-border); padding-bottom:var(--s-2); margin:var(--s-5) 0 var(--s-1); }
.mm-v2 .n-item { font-size:var(--fs-small); border-bottom-color:var(--sidebar-border); padding:var(--s-2) 0; }
.mm-v2 .n-item time { color:var(--text-timestamp); font-size:var(--fs-meta); }
.mm-v2 .n-item a.n-head { color:var(--text-primary); }
.mm-v2 .n-item a.n-head:hover { color:var(--accent-ink); }
.mm-v2 .n-kind { font-size:var(--fs-micro); font-weight:500; padding:0 var(--s-2); border-radius:var(--r-sm);
  background:var(--accent-tint-08); color:var(--accent-ink); }
/* ---- teaser and inline callout: a left-bordered note, not a floating panel */
.mm-v2 .mm-teaser { margin:var(--s-2) 0 var(--s-3); }
.mm-v2 .mm-teaser-body { filter:blur(6px); opacity:.5; max-height:190px; }
.mm-v2 .mm-teaser-cta { position:static; display:block; margin-top:var(--s-3); }
.mm-v2 .mm-teaser-cta > div, .mm-v2 .v2-callout { background:var(--accent-tint-08); border:1px solid var(--sidebar-border);
  border-left:2px solid var(--accent); border-radius:0 var(--r-md) var(--r-md) 0; padding:var(--s-3) var(--s-4);
  max-width:none; text-align:left; font-size:var(--fs-small); color:var(--text-secondary); box-shadow:none; }
/* ---- buttons and the form. One filled button per view (Hick's Law): the
   form's submit. Every other .mm-btn on a page is a link in the accent ink. */
.mm-v2 .mm-btn { display:inline; min-height:0; padding:0; margin:0; border:0; background:transparent;
  color:var(--accent-ink) !important; font:inherit; font-size:var(--fs-small); font-weight:500; cursor:pointer;
  text-decoration:underline !important; text-decoration-color:var(--chip-count) !important; }
.mm-v2 .mm-btn:hover { background:transparent; text-decoration-color:currentColor !important; }
.mm-v2 .mm-trial .mm-btn, .mm-v2 .v2-inq .mm-btn { display:inline-flex; align-items:center; justify-content:center; min-height:40px;
  padding:0 var(--s-4); margin:0; border:0; border-radius:var(--r-control); background:var(--accent-strong);
  color:var(--on-accent) !important; font-family:inherit; font-size:var(--fs-small); font-weight:500; line-height:1.2;
  cursor:pointer; text-decoration:none !important; transition:background var(--t-fast); }
.mm-v2 .mm-trial .mm-btn:hover, .mm-v2 .v2-inq .mm-btn:hover { background:var(--accent-strong-hover); }
.mm-v2 .mm-trial .mm-btn:active, .mm-v2 .v2-inq .mm-btn:active { background:var(--accent-strong-hover); transform:translateY(1px); }
.mm-v2 .mm-btn:disabled { opacity:.55; cursor:default; transform:none; }
.mm-v2 .mm-trial h2 { font-size:var(--fs-h3); letter-spacing:-.02em; margin:0 0 var(--s-2); }
.mm-v2 .mm-trial > p { margin:0 0 var(--s-3); max-width:66ch; }
.mm-v2 .mm-trial form { grid-template-columns:repeat(auto-fit,minmax(190px,1fr)); gap:var(--s-4); align-items:end;
  margin-top:var(--s-4); }
.mm-v2 .mm-trial label { font-size:var(--fs-meta); font-weight:500; color:var(--text-secondary);
  text-transform:none; letter-spacing:.006em; margin-bottom:var(--s-1); }
.mm-v2 .mm-trial input, .mm-v2 .mm-trial select, .mm-v2 .mm-trial textarea { width:100%; min-height:40px; max-width:none;
  padding:0 var(--s-3); border:1px solid var(--sidebar-border); border-radius:var(--r-control);
  background:var(--area-bg); color:var(--text-primary); font-family:inherit; font-size:var(--fs-body);
  transition:border-color var(--t-fast), box-shadow var(--t-fast); }
.mm-v2 .mm-trial select { max-width:420px; }
.mm-v2 .mm-trial input::placeholder { color:var(--text-subtle); }
.mm-v2 .mm-trial input:focus, .mm-v2 .mm-trial select:focus, .mm-v2 .mm-trial textarea:focus { outline:0;
  border-color:var(--accent); box-shadow:0 0 0 3px var(--accent-tint-15); }
.mm-v2 .mm-trial-msg { font-size:var(--fs-small); color:var(--m-green); }
.mm-v2 .mm-trial-msg.err { color:var(--m-red); }
.mm-v2 .mm-trial .mm-btn { margin:0; }
/* Fine print between the footer and the form sits on the panel */
.mm-v2 > p.mm-src { margin:var(--s-5) var(--s-6) 0; font-size:var(--fs-meta); color:var(--text-muted); line-height:1.6;
  letter-spacing:.006em; max-width:66ch; }
.mm-v2 > p.mm-src a { color:var(--accent-ink); }

/* ---- Analyst View, news river and briefing: the same shell, other blocks */
.mm-v2 .n-main, .mm-v2 .n-river { padding:0; }
.mm-v2 .n-main > .n-head, .mm-v2 .n-river > .n-head { margin-bottom:var(--s-5); }
.mm-v2 .v2-mast > div:last-child, .mm-v2 div.n-head > div:last-child { display:grid; justify-items:end; gap:var(--s-2); }
.mm-v2 .v2-mast .n-periods, .mm-v2 div.n-head .n-periods { margin-bottom:0; }
.mm-v2 .n-main > .n-block, .mm-v2 .n-main > .mm-drawer, .mm-v2 .n-main > .n-grid, .mm-v2 .n-main > .n-distil,
.mm-v2 > .mm-drawer, .mm-v2 .n-river > .n-block, .mm-v2 .n-river > .n-distil, .mm-v2 .n-river > .v2-river {
  margin:0 var(--s-6) var(--s-5); }
.mm-v2 .n-main > .n-block, .mm-v2 .n-grid > section, .mm-v2 .n-card, .mm-v2 .mm-drawer, .mm-v2 .n-river > .n-block,
.mm-v2 .v2-river { background:var(--wrap); border:1px solid var(--sidebar-border); border-radius:var(--r-card);
  padding:var(--s-5) var(--s-6) var(--s-4); min-width:0; max-width:none; box-shadow:none; }
.mm-v2 .n-card { padding:var(--s-5); }
.mm-v2 .n-grid { display:grid; grid-template-columns:minmax(0,2fr) minmax(280px,1fr); gap:var(--s-5); align-items:start; }
.mm-v2 .n-aside { display:grid; gap:var(--s-5); align-content:start; min-width:0; }
.mm-v2 .n-block, .mm-v2 .n-block .n-sec-head { margin-bottom:0; }
.mm-v2 .n-sec-head { border:0; border-bottom:1px solid var(--sidebar-border); padding:0 0 var(--s-3); margin:0 0 var(--s-3);
  align-items:baseline; gap:var(--s-3); }
.mm-v2 .n-sec-head h2, .mm-v2 .n-card-title h2 { font-size:var(--fs-h2); font-weight:600; line-height:1.24; letter-spacing:-.022em;
  color:var(--text-primary); text-transform:none; }
.mm-v2 .n-card-title { border-bottom:1px solid var(--sidebar-border); padding-bottom:var(--s-3); margin-bottom:var(--s-3); }
.mm-v2 .n-card-title h2 { font-size:var(--fs-h3); letter-spacing:-.02em; }
.mm-v2 .n-sec-actions { gap:var(--s-2); }
.mm-v2 .n-sec-actions .n-rss { display:inline-flex; align-items:center; gap:6px; min-height:32px; padding:0 var(--s-3);
  border:1px solid var(--sidebar-border); border-radius:var(--r-control); background:transparent; color:var(--text-muted);
  font-size:var(--fs-small); font-weight:500; }
.mm-v2 .n-sec-actions .n-rss:hover { color:var(--accent-ink); border-color:var(--accent-ink); }
.mm-v2 .n-block h3 { font-size:var(--fs-h3); letter-spacing:-.02em; line-height:1.32; margin:0 0 var(--s-2); }
/* Findings: the number is a numeral, not a filled circle */
.mm-v2 .n-finding { padding:var(--s-3) 0 var(--s-3) 34px; border-bottom:1px solid var(--sidebar-border); }
.mm-v2 .n-finding::before { top:var(--s-3); width:22px; height:auto; border-radius:0; background:transparent;
  color:var(--accent-ink); font-size:var(--fs-small); font-weight:600; font-variant-numeric:tabular-nums; display:block; line-height:1.5; }
.mm-v2 .n-finding h3 { font-size:var(--fs-h3); font-weight:600; line-height:1.32; letter-spacing:-.018em; margin:0 0 var(--s-1); }
.mm-v2 .n-finding p { font-family:var(--font-read); font-optical-sizing:auto; font-weight:var(--w-read); font-size:var(--fs-body);
  line-height:1.6; color:var(--text-secondary); max-width:66ch; }
/* Synthesis tiles nest on the panel colour */
.mm-v2 .n-synth { gap:var(--s-3); }
.mm-v2 .n-synth-item { background:var(--area-bg); border:1px solid var(--sidebar-border); border-radius:var(--r-xl); padding:var(--s-3) var(--s-4); }
.mm-v2 .n-synth-item h3 { font-size:var(--fs-body); font-weight:600; margin:0 0 var(--s-1); }
.mm-v2 .n-synth-item p { font-family:var(--font-read); font-optical-sizing:auto; font-weight:var(--w-read); font-size:var(--fs-body);
  line-height:1.6; color:var(--text-secondary); }
.mm-v2 .n-coverage, .mm-v2 .mm-cover { font-family:var(--font-sans); font-size:var(--fs-micro); font-weight:500; letter-spacing:.01em;
  color:var(--m-amber); background:color-mix(in srgb, var(--m-amber) 13%, transparent); border:0; border-radius:var(--r-sm);
  padding:var(--s-1) var(--s-3); display:inline-flex; margin:var(--s-2) 0 0; }
.mm-v2 .mm-cover.full { color:var(--m-green); background:color-mix(in srgb, var(--m-green) 13%, transparent); }
.mm-v2 .n-state { grid-template-columns:12px 40px minmax(0,1fr); padding:var(--s-2) 0; border-bottom:1px solid var(--sidebar-border);
  font-size:var(--fs-small); }
.mm-v2 .n-state:last-of-type { border-bottom:0; }
/* Tables */
.mm-v2 .mm-table { font-size:var(--fs-small); }
.mm-v2 .mm-table th { font-size:var(--fs-meta); font-weight:500; text-transform:none; letter-spacing:.006em; color:var(--text-muted);
  padding:var(--s-2) var(--s-2); border-bottom:1px solid var(--sidebar-border); }
.mm-v2 .mm-table td { padding:var(--s-2); border-bottom:1px solid var(--sidebar-border); color:var(--text-secondary); }
.mm-v2 .mm-table tr:last-child td { border-bottom:0; }
.mm-v2 .mm-table strong, .mm-v2 .n-moved a { color:var(--text-primary); font-weight:500; }
.mm-v2 .n-why-cell { color:var(--text-muted); font-size:var(--fs-meta); }
.mm-v2 .mm-kind { font-size:var(--fs-micro); font-weight:500; letter-spacing:.01em; padding:2px var(--s-2); border:0;
  border-radius:var(--r-sm); color:var(--m-green); background:color-mix(in srgb, var(--m-green) 13%, transparent); }
.mm-v2 .n-more > summary { font-size:var(--fs-small); font-weight:500; color:var(--accent-ink); padding:var(--s-2) 0; }
/* Stat tiles inside the evidence drawer */
.mm-v2 .mm-stats { gap:var(--s-3); margin:var(--s-3) 0 var(--s-4); }
.mm-v2 .mm-stat { background:var(--area-bg); border:1px solid var(--sidebar-border); border-radius:var(--r-xl); padding:var(--s-3) var(--s-4); }
.mm-v2 .mm-stat .v { font-size:28px; font-weight:600; line-height:1; letter-spacing:-.036em; color:var(--text-primary);
  font-variant-numeric:tabular-nums; margin:var(--s-2) 0 var(--s-1); }
.mm-v2 .mm-stat .l { font-size:var(--fs-meta); font-weight:400; text-transform:none; letter-spacing:.006em; color:var(--text-muted); }
.mm-v2 .mm-stat .h { font-size:var(--fs-micro); color:var(--text-subtle); }
.mm-v2 .n-plain .n-metric { background:var(--area-bg); }
/* Drawers: a content box whose summary is one disclosure row */
.mm-v2 .mm-drawer { margin-top:0; }
.mm-v2 .mm-drawer > summary { position:relative; display:grid; grid-template-columns:minmax(0,1fr) 28px; gap:var(--s-1) var(--s-3);
  align-items:center; min-height:52px; margin:calc(-1 * var(--s-3)) calc(-1 * var(--s-2)); padding:var(--s-3) var(--s-2);
  border-radius:var(--r-control); cursor:pointer; list-style:none; }
.mm-v2 .mm-drawer > summary::-webkit-details-marker { display:none; }
.mm-v2 .mm-drawer > summary::after { content:"+"; position:static; grid-column:2; grid-row:1 / span 2; color:var(--text-subtle);
  font-size:18px; line-height:1; text-align:center; }
.mm-v2 .mm-drawer[open] > summary::after { content:"\\2212"; }
.mm-v2 .mm-drawer > summary:hover { background:var(--chip-soft); }
.mm-v2 .mm-drawer > summary:hover .mm-drawer-t, .mm-v2 .mm-drawer > summary:hover::after { color:var(--accent-ink); }
.mm-v2 .mm-drawer-t { font-size:var(--fs-h3); font-weight:500; line-height:1.35; letter-spacing:-.012em; color:var(--text-primary); }
.mm-v2 .mm-drawer-b { font-size:var(--fs-meta); color:var(--text-muted); letter-spacing:.006em; max-width:66ch; }
.mm-v2 .mm-drawer-body { padding:var(--s-4) 0 0; animation:v2-reveal .16s ease; }
.mm-v2 .mm-drawer[open] > summary { margin-bottom:0; border-bottom:1px solid var(--sidebar-border); border-radius:var(--r-control) var(--r-control) 0 0; }
.mm-v2 .section { margin-top:var(--s-5); }
.mm-v2 .section:first-child { margin-top:0; }
.mm-v2 .section h2 { font-size:var(--fs-h2); font-weight:600; letter-spacing:-.022em; margin:0 0 var(--s-2); }
.mm-v2 .section h3 { font-size:var(--fs-lead); font-weight:600; letter-spacing:-.018em; margin:var(--s-4) 0 var(--s-2); }
.mm-v2 .section p, .mm-v2 .section li { font-size:var(--fs-body); line-height:1.6; color:var(--text-secondary); max-width:66ch; }
.mm-v2 .section p.mm-src, .mm-v2 .section .mm-src { font-size:var(--fs-meta); color:var(--text-muted); letter-spacing:.006em; }
.mm-v2 .section-eyebrow { color:var(--text-muted); font-size:var(--fs-meta); font-weight:500; letter-spacing:.006em; text-transform:none; }
.mm-v2 .mm-fold { margin:var(--s-3) 0; border-top:1px solid var(--sidebar-border); }
.mm-v2 .mm-fold > summary { font-size:var(--fs-small); font-weight:500; color:var(--text-secondary); padding:var(--s-3) 0; }
.mm-v2 .mm-fold > summary::marker { color:var(--text-subtle); }
.mm-v2 .mm-fold > summary:hover { color:var(--accent-ink); }
.mm-v2 .mm-reading { font-size:var(--fs-body); }
.mm-v2 .mm-reading.pos { color:var(--m-green); } .mm-v2 .mm-reading.pos .dot { background:var(--m-green); }
.mm-v2 .mm-reading.neg { color:var(--m-red); } .mm-v2 .mm-reading.neg .dot { background:var(--m-red); }
.mm-v2 .mm-reading.neutral { color:var(--text-secondary); } .mm-v2 .mm-reading.neutral .dot { background:var(--text-subtle); }
/* Charts drawn with literal colours: remapped so they follow the theme */
.mm-v2 svg.mm-chart [fill="#f8fafc"], .mm-v2 svg.mm-chart [fill="#eef2f6"] { fill:var(--wrap-2); }
.mm-v2 svg.mm-chart [stroke="#e5e7eb"], .mm-v2 svg.mm-chart [stroke="#e2e8f0"], .mm-v2 svg.mm-chart [stroke="#cbd5e1"] { stroke:var(--sidebar-border); }
.mm-v2 svg.mm-chart [fill="#64748b"], .mm-v2 svg.mm-chart [fill="#6b7280"], .mm-v2 svg.mm-chart [fill="#475569"],
.mm-v2 svg.mm-chart [fill="#374151"], .mm-v2 svg.mm-chart [fill="#334155"] { fill:var(--text-muted); }
.mm-v2 svg.mm-chart [stroke="#64748b"], .mm-v2 svg.mm-chart [stroke="#475569"], .mm-v2 svg.mm-chart [stroke="#334155"],
.mm-v2 svg.mm-chart [stroke="#9ca3af"] { stroke:var(--text-muted); }
.mm-v2 svg.mm-chart [fill="#94a3b8"], .mm-v2 svg.mm-chart [fill="#9ca3af"], .mm-v2 svg.mm-chart [fill="#8b93a1"] { fill:var(--text-subtle); }
.mm-v2 svg.mm-chart [fill="#d4d8de"] { fill:var(--chip-count); }
.mm-v2 svg.mm-chart [fill="#0f172a"], .mm-v2 svg.mm-chart [fill="#1e293b"] { fill:var(--text-primary); }
.mm-v2 svg.mm-chart [stroke="#0f172a"] { stroke:var(--text-primary); }
.mm-v2 svg.mm-chart [fill="#30a46c"] { fill:var(--m-green); } .mm-v2 svg.mm-chart [stroke="#30a46c"] { stroke:var(--m-green); }
.mm-v2 svg.mm-chart [stroke="#1d4ed8"] { stroke:var(--mention); } .mm-v2 svg.mm-chart [stroke="#b45309"] { stroke:var(--m-amber); }
.mm-v2 svg.mm-chart text { font-family:var(--font-sans); }
/* The news river as a box of day groups */
.mm-v2 .v2-river .n-day:first-child { margin-top:0; }
.mm-v2 .n-item .n-src { color:var(--text-muted); }
.mm-v2 .n-item .n-more, .mm-v2 .n-item .n-more a { color:var(--text-muted); font-size:var(--fs-meta); }
.mm-v2 .n-item .n-more a:hover { color:var(--accent-ink); }
/* Briefing body */
.mm-v2 .v2-briefing { max-width:66ch; }
.mm-v2 .v2-briefing h2 { font-size:var(--fs-h2); letter-spacing:-.022em; margin:var(--s-6) 0 var(--s-2); }
.mm-v2 .v2-briefing h3 { font-size:var(--fs-h3); letter-spacing:-.02em; margin:var(--s-5) 0 var(--s-2); }
.mm-v2 .v2-briefing p, .mm-v2 .v2-briefing li { font-family:var(--font-read); font-optical-sizing:auto; font-weight:var(--w-read);
  font-size:var(--fs-lead); line-height:1.6; color:var(--text-secondary); margin:0 0 var(--s-3); }
.mm-v2 .v2-briefing ul, .mm-v2 .v2-briefing ol { padding-left:20px; }
@media (max-width:1080px) { .mm-v2 .n-grid { grid-template-columns:1fr; } }
@media (max-width:860px) {
  .mm-v2 .n-main > .n-block, .mm-v2 .n-main > .mm-drawer, .mm-v2 .n-main > .n-grid, .mm-v2 .n-main > .n-distil,
  .mm-v2 > .mm-drawer, .mm-v2 .n-river > .n-block, .mm-v2 .n-river > .n-distil, .mm-v2 .n-river > .v2-river { margin:0 var(--s-5) var(--s-4); }
  .mm-v2 .n-main > .n-block, .mm-v2 .n-grid > section, .mm-v2 .mm-drawer, .mm-v2 .v2-river { padding:var(--s-4) var(--s-5); }
}
@media (max-width:560px) {
  .mm-v2 .n-main > .n-block, .mm-v2 .n-main > .mm-drawer, .mm-v2 .n-main > .n-grid, .mm-v2 .n-main > .n-distil,
  .mm-v2 > .mm-drawer, .mm-v2 .n-river > .n-block, .mm-v2 .n-river > .n-distil, .mm-v2 .n-river > .v2-river { margin:0 var(--s-4) var(--s-4); }
  .mm-v2 .n-main > .n-block, .mm-v2 .n-grid > section, .mm-v2 .n-card, .mm-v2 .mm-drawer, .mm-v2 .v2-river { padding:var(--s-4); }
  .mm-v2 .n-metrics { grid-template-columns:1fr; }
}
/* ---- motion */
html { scroll-behavior:smooth; }
.mm-v2 [id] { scroll-margin-top:var(--s-5); }
@media (prefers-reduced-motion: reduce) {
  html { scroll-behavior:auto; }
  .mm-v2 *, .mm-v2 *::before, .mm-v2 *::after { transition:none !important; animation:none !important; }
  .mm-v2 .mm-btn:active { transform:none; }
}
/* ---- breakpoints */
@media (max-width:1080px) {
  .mm-v2 .v2-grid { grid-template-columns:1fr; }
  .mm-v2 .v2-side { grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); }
  .mm-v2 .v2-numbers { grid-template-columns:repeat(2,minmax(0,1fr)); }
}
@media (max-width:860px) {
  .container { padding:var(--s-3) var(--s-3) var(--s-7); }
  .mm-v2 .v2-mast, .mm-v2 div.n-head { padding:var(--s-6) var(--s-5) var(--s-4); align-items:flex-start; }
  .mm-v2 .v2-mast > div:last-child { text-align:left; }
  .mm-v2 .n-period { text-align:left; }
  .mm-v2 .v2-grid { padding:var(--s-4) var(--s-5); }
  .mm-v2 .v2-sec, .mm-v2 .v2-lead > .v2-lead-story, .mm-v2 .v2-findings, .mm-v2 .v2-about,
  .mm-v2 .v2-one > .v2-piece-page { padding:var(--s-4) var(--s-5); }
  .mm-v2 .mm-trial { margin:var(--s-4) var(--s-5) var(--s-5); }
  .mm-v2 > p.mm-src { margin:var(--s-4) var(--s-5) 0; }
  .mm-v2 .n-jump { display:flex; }
}
@media (max-width:760px) {
  .mm-v2 .v2-main { grid-template-columns:1fr; }
  .mm-v2 .v2-side { grid-template-columns:1fr; }
}
@media (max-width:560px) {
  .mm-news.mm-v2 { border-radius:var(--r-2xl); }
  .mm-v2 .n-top, .mm-v2 .n-foot { padding:var(--s-3) var(--s-4); }
  .mm-v2 .v2-mast, .mm-v2 div.n-head { padding:var(--s-5) var(--s-4) var(--s-4); }
  .mm-v2 .v2-grid { padding:var(--s-4); }
  .mm-v2 .v2-sec, .mm-v2 .v2-card, .mm-v2 .v2-lead > .v2-lead-story, .mm-v2 .v2-findings,
  .mm-v2 .v2-side > .n-block, .mm-v2 .mm-trial, .mm-v2 .v2-about, .mm-v2 .v2-one > .v2-piece-page { padding:var(--s-4); }
  .mm-v2 .mm-trial { margin:var(--s-4); }
  .mm-v2 > p.mm-src { margin:var(--s-4) var(--s-4) 0; }
  .mm-v2 .n-story-img, .mm-v2 .v2-sec .n-story-img, .mm-v2 .v2-lead-story.n-story-img { grid-template-columns:1fr; }
  .mm-v2 .n-story-img > .n-thumb, .mm-v2 .v2-lead-story.n-story-img > .n-thumb { grid-column:1; grid-row:auto;
    width:100%; aspect-ratio:16/9; object-fit:cover; border-radius:var(--r-xl); }
  .mm-v2 .v2-numbers, .mm-v2 .n-metrics { grid-template-columns:1fr; }
  .mm-v2 .v2-hl > summary { font-size:var(--fs-lead); }
}
@media print {
  html, body { background:#fff; }
  .mm-news.mm-v2 { box-shadow:none; }
  .mm-v2 .n-theme { display:none; }
}
"""

#: The sections, in page order. ``thing`` completes "No … in the last N days".
V2_SECTIONS: Dict[str, Dict[str, str]] = {
    "analysis": {"heading": "Analysis", "colour": "var(--n-text)",
                 "thing": "analysis",
                 "empty": "No analysis published yet.",
                 "subline": "Analysis and notes written by the Cyberfuturists team."},
    "moves": {"heading": "Market moves", "colour": "var(--n-purple)",
              "thing": "market move",
              "subline": "Deals, funding, partnerships, leadership changes "
                         "and named customers."},
    "launches": {"heading": "Product launches", "colour": "var(--n-blue)",
                 "thing": "product launch",
                 "subline": "New products, and expansions of existing ones."},
    "hiring": {"heading": "Hiring", "colour": "var(--n-green)",
               "thing": "vendor with 5 or more open roles",
               "subline": "Vendors with 5 or more open roles, and LinkedIn "
                          "headcount changes of 10% or more."},
    "cases": {"heading": "Case studies", "colour": "var(--n-orange)",
              "thing": "case study",
              "subline": "Customer stories where the customer is not named."},
    "voices": {"heading": "Thought leadership", "colour": "var(--n-accent)",
               "thing": "opinion or research",
               "subline": "Opinion and research from vendors and researchers that "
                          "is not about a specific announcement."},
    "social": {"heading": "Social", "colour": "var(--n-cyan)",
               "thing": "practitioner post",
               "subline": "What practitioners are saying on X, Bluesky, Reddit and "
                          "LinkedIn, newest first, and the most shared posts."},
    "research": {"heading": "Research firms", "colour": "var(--n-amber)",
                 "thing": "analyst report or post",
                 "subline": "Reports in which analyst firms have named vendors, and the "
                            "firms' own public posts. The reports are behind paywalls; "
                            "every item links to its source."},
}
_V2_LAUNCH_TYPES = {"product_launch", "product_expansion"}
_V2_HIRING_TYPES = {"significant_hiring", "headcount_change"}
#: How many items a section shows on the front page; its own page shows all.
_V2_CAPS = {"analysis": 3, "research": 4, "moves": 4, "launches": 4, "hiring": 5, "cases": 3,
            "voices": 6, "social": 6}
#: A new piece of ours leads the front page for this many days after publication.
_V2_PIECE_LEAD_DAYS = 3
# The lead should be news: a development from the last week outranks an older
# one however well the older ranks (user, 2 Sep 2026 — the Cribl-Radiant
# acquisition led for two weeks). A quiet market keeps its best older story
# rather than an empty slot: small markets won't have many large signal
# events (user, same day).
_V2_LEAD_MAX_AGE_DAYS = 7
_PIECES_SLOT = "<!--mm-pieces-slot-->"
_V2_HIGHLIGHTS = 3
#: Vendors named on the sidebar map, and on the most-active list.
_V2_HORIZON_NAMES = 8
_V2_TOP_VENDORS = 5


def _customer_named(dev: Dict[str, Any]) -> bool:
    """Whether the review pass recorded the customer's name. A vendor's
    story about an unnamed customer is a case study, not a customer."""
    reading = (dev.get("attributes") or {}).get("customer") or {}
    return bool(reading.get("named"))


def _v2_tag(dev: Dict[str, Any]) -> str:
    if dev.get("event_type") == "customer":
        return "Customer" if _customer_named(dev) else "Case study"
    return dev.get("event_type_label") or ""


def _v2_is_voice(row: Dict[str, Any]) -> bool:
    """A vendor post that is opinion or research rather than an
    announcement. Practitioner discussion arrives separately, already
    filtered, as the assessment's ``discussion`` list."""
    verdict = (row.get("review_verdict") or "").lower()
    kind = (row.get("review_kind") or "").lower()
    if row.get("article_class") != "social" or verdict in ("noise", "excluded"):
        return False
    return ((verdict == "commentary" and kind in ("opinion", "research"))
            or (verdict == "signal" and kind == "research"))


def _v2_sections(developments: List[Dict[str, Any]],
                 corpus_rows: List[Dict[str, Any]],
                 discussion: List[Dict[str, Any]],
                 highlights: List[Dict[str, Any]], *,
                 lead_from_developments: bool = True) -> Dict[str, Any]:
    """Every development in exactly one place: the lead, or one section.

    The lead is the highest-ranked development that is not a hiring count.
    Launches and expansions are one section, hiring and headcount another,
    unnamed customer stories a third; everything else is a market move.
    Thought leadership is the vendor opinion and research posts and the
    research papers; Social is the practitioner posts; both minus anything
    already cited as evidence, and the most-shared posts go with Social.
    """
    lead = None
    if lead_from_developments:
        cutoff = (datetime.now(timezone.utc)
                  - timedelta(days=_V2_LEAD_MAX_AGE_DAYS)).strftime("%Y-%m-%d")
        # Rank order, but only among developments young enough to lead; an
        # undated development cannot show it is fresh, so it cannot lead.
        fresh = [d for d in developments if str(d.get("date") or "") >= cutoff]
        for pool in (fresh, developments):
            lead = next((d for d in pool
                         if d.get("event_type") not in _V2_HIRING_TYPES), None)
            if lead is None and pool:
                lead = pool[0]
            if lead is not None:
                break
    buckets: Dict[str, List[Dict[str, Any]]] = {k: [] for k in V2_SECTIONS}
    for d in developments:
        if d is lead:
            continue
        kind = d.get("event_type")
        if kind in _V2_LAUNCH_TYPES:
            buckets["launches"].append(d)
        elif kind in _V2_HIRING_TYPES:
            buckets["hiring"].append(d)
        elif kind == "customer" and not _customer_named(d):
            buckets["cases"].append(d)
        else:
            buckets["moves"].append(d)
    # Hiring is ordered by open roles, most first, then the headcount moves
    # by size, so the front page's top five are the five biggest recruiters.
    def hiring_key(d: Dict[str, Any]) -> tuple:
        attrs = d.get("attributes") or {}
        if d.get("event_type") == "significant_hiring":
            return (0, -int(attrs.get("openings") or 0))
        return (1, -abs(float(attrs.get("pct") or 0)))
    buckets["hiring"].sort(key=hiring_key)
    # The development sections read newest first everywhere (user, 2 Sep
    # 2026, superseding the ranked front-page order chosen that morning).
    # Stable, so equal days keep their rank order; an undated item goes
    # last. Hiring stays ranked by open roles on the front page by design.
    for key in ("moves", "launches", "cases"):
        buckets[key].sort(key=lambda d: str(d.get("date") or ""), reverse=True)
    used = {e.get("uri") for d in developments for e in (d.get("evidence") or [])}
    voices: Dict[str, Dict[str, Any]] = {}
    for row in [r for r in (corpus_rows or []) if _v2_is_voice(r)] + list(discussion or []):
        uri = row.get("uri")
        if uri and uri not in used and uri not in voices:
            voices[uri] = row
    newest = sorted(voices.values(), key=lambda r: str(r.get("published") or ""),
                    reverse=True)
    buckets["social"] = [r for r in newest if r.get("article_class") == "discussion"]
    buckets["voices"] = [r for r in newest if r.get("article_class") != "discussion"]
    shared = [h for h in (highlights or [])
              if h.get("uri") and h["uri"] not in used and h["uri"] not in voices]
    return {"lead": lead, "buckets": buckets, "highlights": shared[:_V2_HIGHLIGHTS]}


def _piece_is_fresh(piece_row: Dict[str, Any], days: int = _V2_PIECE_LEAD_DAYS) -> bool:
    stamp = piece_row.get("published_at")
    if not hasattr(stamp, "tzinfo"):
        return False
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - stamp).days < days


def _piece_when(piece_row: Dict[str, Any]) -> str:
    stamp = piece_row.get("published_at") or piece_row.get("updated_at")
    return stamp.strftime("%-d %b %Y") if hasattr(stamp, "strftime") else str(stamp or "")[:10]


def _piece_href(link_params: Dict[str, Any], piece_row: Dict[str, Any]) -> str:
    return "?" + _relink(link_params, view="v2", piece=piece_row["id"])


def _plain(md: str) -> str:
    """Markdown as plain words for a summary: emphasis marks, code ticks
    and link syntax removed, the link text kept."""
    out = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", md or "")
    out = re.sub(r"[*_`]{1,3}", "", out)
    return re.sub(r"\s+", " ", out).strip()


def _piece_tag(piece_row: Dict[str, Any]) -> str:
    kind = piece_row.get("kind") or "analysis"
    return "Our analysis" if kind == "analysis" else "Our analysis · Note"


def _v2_piece_card(piece_row: Dict[str, Any], link_params: Dict[str, Any], *,
                   lead: bool = False) -> str:
    """One of our pieces as a story: the kind, the title, the opening
    paragraph, who wrote it and when. The lead version is larger."""
    from app.services import market_briefing as mbr

    opening = _plain(mbr.feed_summary(piece_row.get("report_content") or ""))
    href = _piece_href(link_params, piece_row)
    title = esc(piece_row.get("title") or "")
    head = f'<h2><a href="{href}">{title}</a></h2>' if lead else f'<h3><a href="{href}">{title}</a></h3>'
    return (f'<article class="n-story v2-piece{" v2-lead-story" if lead else ""}" '
            'style="--story:var(--n-text)">'
            f'<div class="n-story-tag">{esc(_piece_tag(piece_row))}</div>'
            + head
            + (f'<p class="n-story-sum">{esc(_clip(opening, 480 if lead else 260))}</p>' if opening else "")
            + f'<div class="n-byline">{esc(mbr.provenance_line(piece_row))} · {esc(_piece_when(piece_row))}'
            f' · <a href="{href}">Read &rarr;</a></div></article>')


#: Pages of the site that are not sections: ``?page=about``.
V2_PAGES = ("about",)


def _v2_about_page(market: Dict[str, Any], link_params: Optional[Dict[str, Any]], days: int) -> str:
    """About, how the page is made, the AI disclosure, privacy, contact and
    the disclaimer. Plain statements of what the site does; nothing here is
    computed from the data."""
    from app.compliance.ai_disclosure import AI_DISCLOSURE_LONG

    name = esc(market["name"])
    front = "?" + _relink(link_params, days=days, view="v2")
    return (
        '<article class="v2-about" id="v2-about">'
        '<header class="v2-mast"><div><p class="n-kicker">About this site</p>'
        f'<h1>{name}</h1>'
        '<p class="n-sub">A market news page made by the Cyberfuturists with Aunoo: '
        'who makes it, how, and what happens to your data.</p></div></header>'

        '<section><h2>What this is</h2>'
        f'<p>{name} tracks the vendors in one market: their announcements and hiring, '
        'customer stories, what practitioners say about the products, and the analyst '
        'coverage they pick up. New material appears as it is collected, and the period '
        'selector at the top shows the last 7, 30 or 90 days of it. It is written for '
        'people who work in or around this market.</p>'
        '<p>It is published by the <a href="https://cyberfuturists.com/">Cyberfuturists</a>, a '
        'cybersecurity advisory, and made with <a href="https://aunoo.ai/">Aunoo</a>, its market '
        'intelligence platform.</p></section>'

        '<section id="how"><h2>How it is made</h2>'
        '<p>The material is collected automatically from public sources: press releases and '
        'news coverage, the vendors\u2019 own websites, blogs and LinkedIn company pages, their '
        'public job listings, posts on X, Bluesky and Reddit that mention the market, and what '
        'the analyst firms publish in the open. Every item links back to where it was found, '
        'so you can always read the original.</p>'
        '<p>AI models make the first pass over what arrives: they match each item to a vendor, '
        'sort announcements from commentary and marketing, and draft the summaries. People at '
        'the Cyberfuturists write the rules the models work to and check what they produce. '
        'The exception is the Analysis section, where every piece is written by the person '
        'named on it.</p>'
        '<p>No vendor pays to appear here, and none can pay to stay off. The list is our own '
        'judgement, and we add a company when the public record gives us enough to cover it. '
        'If yours belongs here and is missing, tell us through the form on the front page and '
        'we will look.</p>'
        '</section>'

        '<section id="ai"><h2>AI disclosure</h2>'
        f'<p>{esc(AI_DISCLOSURE_LONG)}</p>'
        '<p>The summaries, the highlights, the sorting of items into sections, the map of '
        'vendors by scale and momentum and the automatic briefings are all produced by AI '
        'models, and any of them can contain errors. Headlines and quoted text are the '
        'sources\u2019 own words, and pieces under Analysis are written by the person named '
        'on them. This notice is given under Article 50 of the EU AI Act.</p></section>'

        '<section id="privacy"><h2>Privacy</h2>'
        '<p>The data controller is Oliver Rochford Ltd, trading as Cyberfuturists (see Contact '
        'and imprint below).</p>'
        '<p><strong>Reading the page.</strong> The site has no accounts, cookies or analytics '
        'scripts. Our web server does keep a standard access log of your IP address, browser '
        'string and the pages you request; we use it to run the site and to stop abuse, and '
        'we delete it after 14 days.</p>'
        '<p><strong>Fonts.</strong> The page loads its typeface from Google Fonts, so your '
        'browser makes a request to Google when it opens the page; Google\u2019s privacy policy '
        'applies to that request.</p>'
        '<p><strong>Forms.</strong> If you send a news tip, tell us your company is missing, or '
        'ask for a trial, we store what you type together with your IP address and browser '
        'string, and the message is emailed to the editors. We use it to answer you and to '
        'limit repeated submissions from one address, and for nothing else; we do not sell it '
        'or share it. If you want it deleted, write to us through the same forms.</p>'
        '<p><strong>Booking a call.</strong> If you book an analyst call, payment is taken by '
        'Stripe on its own pages; we never see your card. Stripe passes us your name, email '
        'address, the amount paid and, if you gave one, your billing address, and applies '
        'its own privacy policy to what it holds. We keep that, what you told us the call is '
        'about, your IP address and browser string, to run the call and for our accounts, '
        'which UK tax law makes us keep for six years. Choosing a time happens on a Google '
        'Calendar booking page under Google\u2019s terms.</p>'
        '<p><strong>Links.</strong> Every item links out to a third-party site with its own '
        'privacy terms, and the images shown with posts load from the network they were '
        'posted on.</p>'
        '<p><strong>People named on the page.</strong> The page shows public posts and public '
        'profiles of people who write about this market, with a link to the original. Who '
        'appears is our editorial choice: the material is public, and we do not add or remove '
        'people on request. If an entry misattributes something to you or links to the wrong '
        'person, tell us through the news-tip form and we will correct the mistake.</p></section>'

        '<section id="disclaimer"><h2>Disclaimer</h2>'
        '<p>None of this is advice. Because the page is assembled automatically from public '
        'sources, it can be wrong, incomplete or out of date, and you should check the linked '
        'source before relying on anything here. The Cyberfuturists and Aunoo accept no '
        'liability for decisions made on it. Company names, product names and the names of '
        'analyst reports are their owners’ trademarks and appear here only to identify '
        'them.</p></section>'

        '<section id="contact"><h2>Contact and imprint</h2>'
        '<p>Cyberfuturists is the trading name of Oliver Rochford Ltd, a private limited '
        'company registered in England and Wales, company number '
        '<a href="https://find-and-update.company-information.service.gov.uk/company/14480528">'
        '14480528</a>. Registered office: 7 High Street East, Glossop, Derbyshire, SK13 8DA, '
        'United Kingdom. Website: <a href="https://cyberfuturists.com/">cyberfuturists.com</a>.</p>'
        '<p>For this page, the forms on the <a href="' + front + '">front page</a> reach the '
        'editors directly.</p></section>'
        '</article>')


def _v2_piece_page(piece_row: Dict[str, Any], others: List[Dict[str, Any]],
                   link_params: Dict[str, Any]) -> str:
    """The piece in full: title, who wrote it, the text, and the other pieces."""
    from app.services import market_briefing as mbr

    more = ""
    if others:
        more = ('<h2 class="v2-sub">More of our pieces</h2>' + "".join(
            f'<div class="n-row"><span class="n-rank"></span><div>'
            f'<a href="{_piece_href(link_params, o)}"><strong>{esc(o.get("title") or "")}</strong></a>'
            f'<div class="n-row-label">{esc(mbr.provenance_line(o))} · {esc(_piece_when(o))}</div>'
            '</div></div>' for o in others))
    return ('<article class="v2-piece-page">'
            f'<div class="n-story-tag">{esc(_piece_tag(piece_row))}</div>'
            f'<h1>{esc(piece_row.get("title") or "")}</h1>'
            f'<p class="n-byline">{esc(mbr.provenance_line(piece_row))} · {esc(_piece_when(piece_row))}</p>'
            '<div class="v2-piece-body">' + mbr.render_body(piece_row) + '</div>'
            + _v2_piece_ai_note(link_params) + more + "</article>")


def _v2_piece_ai_note(link_params: Optional[Dict[str, Any]]) -> str:
    """The site's standard AI disclosure at the foot of every piece: the
    same Article 50 notice the Anticipate reports carry, from
    app.compliance.ai_disclosure, followed by the About page's AI section."""
    from app.compliance.ai_disclosure import disclosure_footer_html

    about = "?" + _relink(link_params or {}, view="v2", page="about")
    return ('<div class="v2-ai-note">' + disclosure_footer_html(long=True)
            + f'<p><a href="{about}#ai">AI disclosure</a></p></div>')


def _v2_lead(dev: Dict[str, Any], images: Optional[Dict[str, str]] = None,
             logos: Optional[Dict[str, str]] = None) -> str:
    colour = _KIND_COLOUR.get(dev.get("event_type") or "", "var(--n-accent)")
    vendors = ", ".join(v.get("vendor") or "" for v in dev.get("vendors") or [])
    image = _dev_image(dev, images, previews=False)
    out = [f'<article class="n-story v2-lead-story{" n-story-img" if image else ""}" '
           f'id="{_dev_anchor(dev)}" style="--story:{colour}">',
           (f'<img class="n-thumb v2-lead-img" src="{esc(image)}" alt="">' if image else ""),
           f'<div class="n-story-tag">Top development · {esc(_v2_tag(dev))}</div>',
           f'<h2>{esc(dev.get("headline") or "")}</h2>']
    summary = _summary_unless_duplicate(dev)
    if summary:
        out.append(f'<p class="n-story-sum">{esc(_clip(summary, 480))}</p>')
    if dev.get("why_it_matters"):
        out.append(f'<p class="n-why">{esc(dev["why_it_matters"])}</p>')
    bits = [_vendor_line(dev, logos) if logos else esc(vendors), esc(_dev_date(dev)),
            esc(_dev_sources(dev)), esc(dev.get("provenance_label") or "")]
    out.append('<div class="n-byline">' + " · ".join(b for b in bits if b) + "</div>")
    out.append(_dev_evidence_links(dev))
    out.append("</article>")
    return "".join(out)


def _v2_highlights(findings: List[Dict[str, Any]],
                   devs_by_id: Dict[str, Dict[str, Any]]) -> str:
    """The findings as headlines, each opening to its statement and
    evidence: a reader skims the list and opens the one that matters."""
    if not findings:
        return ""
    return ('<div class="v2-findings"><h2>Highlights</h2>'
            + "".join(f'<details class="v2-hl"><summary>{esc(f["headline"])}</summary>'
                      f'<div class="v2-hl-body">{_finding_body(f, devs_by_id)}</div></details>'
                      for f in findings)
            + "</div>")


def _v2_section(key: str, inner: str, *, count: int, days: int,
                more_href: Optional[str] = None, wide: bool = False) -> str:
    """One section: its name, a line saying what it holds, and its items or
    a line saying there are none. The front page links to the full list."""
    sec = V2_SECTIONS[key]
    more = (f'<a class="v2-more" href="{more_href}">All {count} &rarr;</a>'
            if more_href and count else "")
    if not inner:
        inner = ('<p class="n-empty">' + esc(sec["empty"]) + '</p>' if sec.get("empty") else
                 f'<p class="n-empty">No {esc(sec["thing"])} in the '
                 f'last {days} days.</p>')
    return (f'<section class="v2-sec{" v2-wide" if wide else ""}" id="v2-{key}" '
            f'style="--sec:{sec["colour"]}">'
            f'<div class="n-sec-head"><h2>{esc(sec["heading"])}</h2>{more}</div>'
            f'<p class="v2-subline">{esc(sec["subline"])}</p>'
            + inner + "</section>")


def _v2_stories(devs: List[Dict[str, Any]],
                images: Optional[Dict[str, str]] = None,
                logos: Optional[Dict[str, str]] = None) -> str:
    return (_render_developments(devs, tag_for=_v2_tag, images=images, logos=logos)
            if devs else "")


def _v2_hiring(devs: List[Dict[str, Any]], hiring: Dict[str, Any], *,
               total: Optional[int] = None,
               logos: Optional[Dict[str, str]] = None) -> str:
    """The hiring block for the vendors above the floor, a row per headcount
    move, and the market-wide count of open roles with its coverage.
    ``total`` is how many hiring developments the period holds when ``devs``
    is the front page's top of the list."""
    out = []
    openings = int(hiring.get("openings") or 0)
    coverage = hiring.get("coverage") or {}
    if openings:
        out.append(f'<p class="v2-strip"><strong>{openings}</strong> open roles; '
                   f'{esc(coverage.get("label") or "coverage unknown")}.</p>')
    shown = [d for d in devs if d.get("event_type") == "significant_hiring"]
    out.append(_render_hiring_block(shown, total=total, logos=logos))
    heads = [d for d in devs if d.get("event_type") == "headcount_change"]
    if heads:
        rows = []
        for d in heads:
            attrs = d.get("attributes") or {}
            vendor = ", ".join(v.get("vendor") or "" for v in d.get("vendors") or [])
            prev, latest = attrs.get("previous"), attrs.get("latest")
            detail = (f"{prev} to {latest} on LinkedIn"
                      if prev is not None and latest is not None else "LinkedIn headcount")
            pct = f"{_signed(attrs.get('pct'))}%"
            blur = ""
            if d.get("withheld"):
                detail = re.sub(r"\d", "8", detail)
                pct = re.sub(r"\d", "8", pct)
                blur = " n-blur"
            rows.append(f'<div class="n-row"><span class="n-rank"></span>'
                        f'<div><strong>{_mark(logos, vendor)}{esc(vendor)}</strong>'
                        f'<div class="n-row-label{blur}">{esc(detail)} · {esc(_dev_date(d))}</div></div>'
                        f'<span class="n-row-val{blur}" aria-hidden="true">{esc(pct)}</span></div>')
        out.append('<article class="n-story" style="--story:var(--n-green)">'
                   '<div class="n-story-tag">Headcount</div>'
                   f'<h3>{len(heads)} vendor{"" if len(heads) == 1 else "s"} whose '
                   'LinkedIn headcount moved 10% or more</h3>' + "".join(rows)
                   + "</article>")
    return "".join(out)


def _v2_voice_row(row: Dict[str, Any]) -> str:
    from app.services import market_assessment as massess
    headline = massess.headline_of(row) if row.get("title") else row["uri"]
    author = (row.get("social_meta") or {}).get("author")
    if author and headline.lower().startswith(f"@{author}:".lower()):
        headline = headline[len(author) + 2:].strip() or headline
    when = _day(row.get("published")) if row.get("published") else ""
    return ('<div class="n-social">'
            f'<div class="n-social-meta">{esc(_river_source(row))}'
            + (f" · {esc(when)}" if when else "") + "</div>"
            f'<p class="n-quote"><a href="{esc(row["uri"])}">{esc(_clip(headline, 220))}</a></p>'
            "</div>")


def _v2_voices(rows: List[Dict[str, Any]], highlights: List[Dict[str, Any]]) -> str:
    out = [_v2_voice_row(r) for r in rows]
    if highlights:
        out.append('<h3 class="v2-sub">Most shared posts</h3>')
        for h in highlights:
            who = (f'@{h["author"]} on {_PLATFORM_NAMES.get(str(h.get("platform") or "").lower(), h.get("platform") or "")}'
                   if h.get("author") else str(h.get("platform") or ""))
            out.append('<div class="n-social">'
                       f'<div class="n-social-meta">{esc(who)} · '
                       f'{int(h.get("engagement") or 0)} reactions</div>'
                       f'<p class="n-quote"><a href="{esc(h["uri"])}">'
                       f'{esc(_clip(h.get("quote") or "", 200))}</a></p></div>')
    return "".join(out)


def _v2_research(items: List[Dict[str, Any]], logos: Optional[Dict[str, str]] = None) -> str:
    """The Latest research section: reports vendors cite, each with the
    vendors named in it (``market_research.group_citations``), then the
    analyst firms' own posts (``market_research.analyst_posts``). The two
    kinds get a sub-heading only when both are present."""
    groups = [i for i in items if i.get("item") == "group"]
    posts = [i for i in items if i.get("item") == "post"]
    out: List[str] = []
    if groups and posts:
        out.append('<h3 class="v2-sub">Reports vendors cite</h3>')
    for g in groups:
        meta = " · ".join(x for x in (g.get("firm"), g.get("family"), _day(g["latest"]) if g.get("latest") else "") if x)
        named = [v for v in g["vendors"] if v.get("position")]
        lead_word = "Named" if named and len(named) == len(g["vendors"]) else "Cited by"
        vendors = ", ".join(
            f'<a href="{esc(v["uri"])}">{_mark(logos, v["vendor"], 16)}{esc(v["vendor"])}'
            + (f' ({esc(v["position"])})' if v.get("position") else "") + "</a>"
            for v in g["vendors"])
        out.append('<div class="n-social v2-rs">'
                   f'<div class="n-social-meta">{esc(meta)}</div>'
                   f'<p class="n-quote"><a href="{esc(g["uri"])}">{esc(_clip(g["label"], 160))}</a></p>'
                   f'<p class="v2-rs-cited">{lead_word} {vendors}</p></div>')
    if groups and posts:
        out.append('<h3 class="v2-sub">From the analyst firms</h3>')
    for r in posts:
        headline = r.get("title") or r["uri"]
        when = _day(r.get("published")) if r.get("published") else ""
        meta = " · ".join(x for x in (r.get("firm"), r.get("research_kind"), when) if x)
        out.append('<div class="n-social">'
                   f'<div class="n-social-meta">{esc(meta)}</div>'
                   f'<p class="n-quote"><a href="{esc(r["uri"])}">{esc(_clip(headline, 220))}</a></p>'
                   "</div>")
    return "".join(out)


def _v2_vendor_domains(conn, market_id: int) -> Dict[str, str]:
    """Domain → vendor display name for the market's vendors, so a vendor's
    own blog post is named like its LinkedIn posts."""
    from sqlalchemy import text as _sql

    rows = conn.execute(_sql("""
        SELECT vi.normalized_value, b.display_name
          FROM bw_market_brands mb
          JOIN bw_brands b ON b.id = mb.brand_id
          JOIN bw_vendor_identifiers vi ON vi.brand_id = b.id
         WHERE mb.market_id = :m AND mb.role <> 'excluded'
           AND vi.kind = 'domain' AND vi.valid_to IS NULL
    """), {"m": market_id}).fetchall()
    return {re.sub(r"^www\.", "", str(r[0]).lower()): r[1] for r in rows if r[0] and r[1]}


_VOICE_ROLES = {"practitioner": "Practitioner", "analyst_or_press": "Analyst / press"}
_V2_VOICES_SHOWN = 10
_V2_VOICES_MORE = 10


def _v2_tracked_voices(conn, limit: int = _V2_VOICES_SHOWN + _V2_VOICES_MORE) -> List[Dict[str, Any]]:
    """The people we track for this market: the accounts we follow first,
    then profiled practitioners and analysts, by reach. From the profiles,
    not from who happened to post this period, so the list is stable."""
    from sqlalchemy import text as _sql

    return [dict(r) for r in conn.execute(_sql("""
        SELECT id, platform, handle, display_name, followers_count, profile_url,
               watchlisted, metadata->>'market_role' AS role
          FROM social_accounts
         WHERE last_profiled_at IS NOT NULL
           AND (watchlisted OR metadata->>'market_role' = ANY(:roles))
         ORDER BY watchlisted DESC, followers_count DESC NULLS LAST, handle
         LIMIT :lim
    """), {"roles": list(_VOICE_ROLES), "lim": limit}).mappings().all()]


def _v2_voices_card(rows: List[Dict[str, Any]], tv: Optional[Dict[str, Any]], *,
                    teaser: bool) -> str:
    """The tracked voices as a sidebar card: name, handle, why they are
    here, reach, and their posts this period when they made any. The first
    ten are readable; the rest are blurred in the shared view."""
    if not rows:
        return ""
    period: Dict[tuple, Dict[str, Any]] = {}
    for v in (tv or {}).get("voices") or []:
        period[(str(v.get("platform") or "").lower(), str(v.get("author") or "").lower())] = v

    def row_html(r: Dict[str, Any]) -> str:
        handle = f'@{esc(str(r["handle"]))}'
        if r.get("profile_url"):
            handle = f'<a href="{esc(r["profile_url"])}">{handle}</a>'
        name = esc(r.get("display_name") or "")
        platform = _PLATFORM_NAMES.get(str(r.get("platform") or "").lower(), r.get("platform") or "")
        tag = "Following" if r.get("watchlisted") else _VOICE_ROLES.get(r.get("role") or "", "")
        followers = int(r.get("followers_count") or 0)
        v = period.get((str(r.get("platform") or "").lower(), str(r.get("handle") or "").lower()))
        posts = int((v or {}).get("posts") or 0)
        latest = ((v or {}).get("latest_post") or {}).get("url")
        return ('<div class="n-row"><span class="n-rank"></span>'
                f'<div><strong>{name or handle}</strong>'
                + (f' <span class="mm-src">{handle} · {esc(platform)}</span>' if name
                   else f' <span class="mm-src">{esc(platform)}</span>')
                + f'<div class="n-row-label">{esc(tag)}'
                + (f' · {followers:,} followers' if followers else "")
                + (f' · <a href="{esc(latest)}">latest post</a>' if latest else "")
                + '</div></div>'
                + (f'<span class="n-row-val">{posts} post{"" if posts == 1 else "s"}</span>'
                   if posts else '<span class="n-row-val mm-src">quiet this period</span>')
                + '</div>')

    shown = rows[:_V2_VOICES_SHOWN]
    rest = rows[_V2_VOICES_SHOWN:]
    out = ['<p class="v2-subline">Accounts we follow first, then practitioners and analysts '
           'we have profiled, by reach.</p>', "".join(row_html(r) for r in shown)]
    if rest:
        more = "".join(row_html(r) for r in rest)
        out.append(_teaser_open("The rest of the voices we track") + more + _TEASER_END
                   if teaser else more)
    return "".join(out)


def _v2_numbers(assessment: Dict[str, Any], hiring: Dict[str, Any], days: int) -> str:
    """Four figures, each with what it is counted over."""
    devs = assessment.get("developments") or []
    obs = assessment.get("observation") or {}
    counts = obs.get("counts") or {}
    total = int(obs.get("total") or 0)
    coverage = hiring.get("coverage") or {}
    floor = massess_min_openings()
    cards = [
        ("Developments", str(len(devs)), f"in the last {days} days",
         "Something a vendor did that we could confirm: a launch, a partnership, "
         "a customer win, funding, an acquisition, a new executive, "
         f"{floor} or more open roles, or a headcount change of 10% or more. "
         "Counted once, however many articles mention it. Opinion and chatter "
         "don't count."),
        ("Records analysed", f'{int(assessment.get("collected_records") or 0):,}',
         "articles, posts and pages",
         "Everything we read about this market in the period: news articles, "
         "vendor posts and web pages, practitioner posts, research papers."),
        ("Open roles", str(int(hiring.get("openings") or 0)),
         coverage.get("label") or "no job listings seen",
         "Live job listings on LinkedIn and on vendors' careers pages. A role "
         "listed in both places counts once."),
        ("Vendors that moved", str(int(counts.get("material_change") or 0)),
         f"of {total} watched",
         "Vendors with at least one development this period."),
    ]
    return ('<div class="n-metrics v2-numbers">'
            + "".join(f'<div class="n-metric" title="{esc(what)}">'
                      f'<div class="n-metric-top"><span>{esc(label)}</span></div>'
                      f'<div class="n-metric-value">{esc(value)}</div>'
                      f'<div class="n-delta">{esc(note)}</div></div>'
                      for label, value, note, what in cards)
            + "</div>")


def _v2_top_vendors(by_vendor: List[Dict[str, Any]],
                    previous: Optional[Dict[str, int]] = None,
                    logos: Optional[Dict[str, str]] = None) -> str:
    """The vendors with the most developments in the period, top five, as
    bars, each against the same vendor's count in the period before: up,
    down or the same. ``previous`` is None when there is no earlier period
    to compare with, and the bars stand alone. A vendor the reader may not
    see is skipped, not shown as a placeholder."""
    rows = [r for r in by_vendor
            if r.get("vendor") and not r.get("withheld")][:_V2_TOP_VENDORS]
    if not rows:
        return ""
    top = max(int(r.get("n") or 0) for r in rows) or 1
    out = ['<h3 class="v2-sub">Most active vendors</h3>',
           '<p class="v2-subline">Developments in the period'
           + (', against the period before.' if previous is not None else '.') + '</p>',
           '<div class="v2-bars">']
    for r in rows:
        n = int(r.get("n") or 0)
        move = ""
        if previous is not None:
            before = int(previous.get(r["vendor"], 0))
            if n > before:
                move = f'<span class="v2-move up" title="{before} in the period before">&#9650; {n - before}</span>'
            elif n < before:
                move = f'<span class="v2-move down" title="{before} in the period before">&#9660; {before - n}</span>'
            else:
                move = '<span class="v2-move same" title="the same in the period before">=</span>'
        out.append('<div class="v2-bar">'
                   f'<div class="v2-bar-name">{_mark(logos, r["vendor"])}{esc(r["vendor"])}</div>'
                   f'<div class="v2-bar-track"><div class="v2-bar-fill" style="width:{100 * n / top:.0f}%"></div></div>'
                   f'<div class="v2-bar-n">{n}</div>{move}</div>')
    out.append("</div>")
    return "".join(out)


def _v2_topics_for_view(topics: Dict[str, Any], allowed_brand_ids: Optional[List[int]],
                        allowed_names: set, withheld: List[str]) -> Dict[str, Any]:
    """The stored run reduced to what a restricted reader may see.

    A subject's vendor list is cut to the allowed vendors, and a subject
    whose model-written name or sentence names a withheld vendor is dropped
    outright. Only the name and sentence are checked: the sample headlines
    and member uris are never printed on the front page, and a subject lost
    for a headline nobody sees is a subject lost for nothing. The two lists
    are ranked again over the survivors so a dropped entry is backfilled.
    """
    from app.services import market_entitlements as ent
    from app.services import market_topics as mt

    slim = dict(topics)
    kept = []
    for c in topics.get("clusters") or []:
        c = dict(c)
        if ent.drop_text_mentioning([{"name": c.get("name"), "summary": c.get("summary")}],
                                    withheld) == []:
            continue
        c["top_vendors"] = ent.filter_rows(list(c.get("top_vendors") or []),
                                           allowed_brand_ids, allowed_names)
        kept.append(c)
    slim["clusters"] = kept
    return mt.rank(slim)


def _v2_topics(topics: Optional[Dict[str, Any]], link_params: Dict[str, Any],
               days: int) -> str:
    """Being discussed and Emerging, as bars. Empty when there is no stored
    run or neither list has an entry, and the caller emits no card."""
    from datetime import datetime as _dt

    from app.services import market_topics as mt

    lists = mt.listed(topics)
    discussed, emerging = lists["being_discussed"], lists["emerging"]
    if not discussed and not emerging:
        return ""

    def _bars(rows: List[Dict[str, Any]], rise: bool) -> str:
        top = max(int(r.get("n_recent") or 0) for r in rows) or 1
        out = ['<div class="v2-bars">']
        for r in rows:
            n = int(r.get("n_recent") or 0)
            href = "?" + _relink(link_params, days=days, view="v2", topic=r["id"])
            # The rise shows wherever it is notable, so a subject that is
            # both the most discussed and rising says so on its one row.
            show_rise = rise or float(r.get("rise") or 0) >= mt.MIN_RISE
            move = (f'<span class="v2-move up" title="{n} of {int(r.get("n_total") or 0)}'
                    f' in the last 7 days">&#9650; {float(r.get("rise") or 0):.1f}&times;</span>'
                    if show_rise else "<span></span>")
            out.append('<div class="v2-bar">'
                       f'<div class="v2-bar-name"><a href="{href}" title="{esc(r.get("summary") or "")}">'
                       f'{esc(r.get("name") or "")}</a></div>'
                       f'<div class="v2-bar-track"><div class="v2-bar-fill" style="width:{100 * n / top:.0f}%"></div></div>'
                       f'<div class="v2-bar-n">{n}</div>{move}</div>')
        out.append("</div>")
        return "".join(out)

    out: List[str] = []
    if discussed:
        out.append('<h3 class="v2-sub">Being discussed</h3>'
                   '<p class="v2-subline">Articles in the last 7 days, by subject. '
                   '&#9650; marks a subject running above its 30-day pace.</p>'
                   + _bars(discussed, rise=False))
    if emerging:
        out.append('<h3 class="v2-sub">Emerging</h3>'
                   '<p class="v2-subline">Smaller subjects whose coverage is concentrated '
                   'in the last 7 days, against the last 30.</p>'
                   + _bars(emerging, rise=True))
    stamp = str((topics or {}).get("computed_at") or "")
    try:
        when = _dt.fromisoformat(stamp).strftime("%d %B")
    except ValueError:
        when = stamp[:10]
    out.append(f'<p class="v2-subline">From {int((topics or {}).get("n") or 0)} articles over '
               f'the last {int((topics or {}).get("window_days") or 30)} days, grouped {esc(when)}.</p>')
    return "".join(out)


def _v2_motion(rows: List[Dict[str, Any]],
               logos: Optional[Dict[str, str]] = None,
               prev: Optional[List[Dict[str, Any]]] = None) -> str:
    """Who got attention: the vendors whose own posts drew the most reactions,
    and the vendors others wrote about most. ``rows`` are share_of_voice's
    per-vendor rows, already reduced to the vendors the reader may see;
    ``prev`` is the same for the window before, so each bar can carry an
    up/down marker — without it a 30-day rolling sum reads as static."""
    def _delta(vendor: str, key: str, now: int) -> str:
        if prev is None:
            return ""
        before = next((int(p.get(key) or 0) for p in prev
                       if p.get("vendor") == vendor), 0)
        if now > before:
            return (f'<span class="v2-move up" title="{before:,} in the period '
                    f'before">&#9650; {now - before:,}</span>')
        if now < before:
            return (f'<span class="v2-move down" title="{before:,} in the period '
                    f'before">&#9660; {before - now:,}</span>')
        return '<span class="v2-move same" title="the same in the period before">=</span>'

    by_reactions = sorted((r for r in rows if int(r.get("reactions") or 0) > 0),
                          key=lambda r: -int(r.get("reactions") or 0))[:_V2_TOP_VENDORS]
    by_earned = sorted((r for r in rows if int(r.get("earned") or 0) > 0),
                       key=lambda r: -int(r.get("earned") or 0))[:_V2_TOP_VENDORS]
    if not by_reactions and not by_earned:
        return ""
    out = []
    if by_reactions:
        top = max(int(r["reactions"]) for r in by_reactions) or 1
        out.append('<h3 class="v2-sub">By engagement</h3>'
                   '<p class="v2-subline">Reactions on the vendor\'s own posts in the period.</p>'
                   '<div class="v2-bars">')
        for r in by_reactions:
            n = int(r["reactions"])
            out.append('<div class="v2-bar">'
                       f'<div class="v2-bar-name">{_mark(logos, r["vendor"])}{esc(r["vendor"])}</div>'
                       f'<div class="v2-bar-track"><div class="v2-bar-fill" style="width:{100 * n / top:.0f}%"></div></div>'
                       f'<div class="v2-bar-n">{n:,}</div>'
                       + (_delta(r["vendor"], "reactions", n) or
                          f'<span class="v2-move same">{int(r.get("measured") or r.get("own_posts") or 0)} posts</span>')
                       + '</div>')
        out.append("</div>")
    if by_earned:
        top = max(int(r["earned"]) for r in by_earned) or 1
        out.append('<h3 class="v2-sub">Most discussed</h3>'
                   '<p class="v2-subline">Articles and posts by others that name the vendor.</p>'
                   '<div class="v2-bars">')
        for r in by_earned:
            n = int(r["earned"])
            out.append('<div class="v2-bar">'
                       f'<div class="v2-bar-name">{_mark(logos, r["vendor"])}{esc(r["vendor"])}</div>'
                       f'<div class="v2-bar-track"><div class="v2-bar-fill" style="width:{100 * n / top:.0f}%"></div></div>'
                       f'<div class="v2-bar-n">{n}</div>'
                       + (_delta(r["vendor"], "earned", n) or "<span></span>")
                       + '</div>')
        out.append("</div>")
    return "".join(out)


def _recent_movers(devs: List[Dict[str, Any]], limit: int = 8) -> List[Dict[str, Any]]:
    """The newest dated developments worth a mover row, newest first.

    The card asks "who moved", which is a recency question. It used to show
    ``main_developments`` — the importance-ranked top slice — so on a 30-day
    window August's independently reported events permanently outranked the
    current week's vendor-sourced launches, and the operator read the card as
    stale (8 Sep 2026: every row was 17–31 Aug while launches from 3–7 Sep
    sat lower in the list). The cut is by kind, not importance: a
    vendor-sourced launch from this week is a mover even at low importance,
    while headcount and hiring-volume rows are chart material, not moves."""
    skip = {"headcount_change", "significant_hiring"}
    pool = [d for d in devs
            if d.get("date") and d.get("event_type") not in skip]
    return sorted(pool, key=lambda d: d.get("date") or "", reverse=True)[:limit]


def _v2_moved(devs: List[Dict[str, Any]], limit: int = 8,
              logos: Optional[Dict[str, str]] = None) -> str:
    """Who moved, as a sidebar list: the vendor, the kind and the date on
    the line; the headline, the summary and the sources open on click. The
    front page shows only the top of each section, so a jump link would
    often land nowhere; the entry carries its own detail instead."""
    if not devs:
        return '<p class="n-empty">No vendor had a development in the period.</p>'
    rows = []
    for d in devs[:limit]:
        vendors = ", ".join(v.get("vendor") or "" for v in d.get("vendors") or [])
        summary = _summary_unless_duplicate(d)
        top = next((e for e in (d.get("evidence") or []) if e.get("uri")), None)
        headline = (f'<a href="{esc(top["uri"])}">{esc(d.get("headline") or "")}</a>'
                    if top else esc(d.get("headline") or ""))
        rows.append('<details class="v2-mv"><summary>'
                    f'<div><strong>{_vendor_line(d, logos) if logos else esc(vendors)}</strong>'
                    f'<div class="n-row-label">{esc(_v2_tag(d))} · {esc(_dev_date(d))}</div></div>'
                    '</summary><div class="v2-mv-body">'
                    f'<p class="v2-mv-head">{headline}</p>'
                    + (f'<p class="n-story-sum">{esc(_clip(summary, 220))}</p>' if summary else "")
                    + _dev_evidence_links(d) + "</div></details>")
    return '<div class="v2-moved">' + "".join(rows) + "</div>"


def _v2_horizon(horizon: Dict[str, Any], full_href: str) -> str:
    """The arc for the sidebar: the top forty dots when the map is crowded
    (the same cut as the full map opens on), and the names of the largest and
    fastest few. Hovering any dot names its vendor; the full map with every
    name and the switch to all is one link away."""
    cfg = horizon.get("config") or {}
    rated = horizon.get("rated") or []
    counts = horizon.get("counts") or {}
    svg = _horizon_svg(rated, None, cfg.get("tiers") or {},
                       tiers=horizon.get("tiers") or {}, bands=horizon.get("bands") or {},
                       with_inputs=False, labels=_V2_HORIZON_NAMES, label_scale=2.0)
    crowd = len(rated) > _HORIZON_TOP
    return (f'<div class="mm-hz v2-hz{" mm-top" if crowd else ""}">' + svg + '<div class="mm-hz-tip" hidden></div></div>'
            f'<p class="n-note">{counts.get("rated", len(rated))} of '
            f'{counts.get("eligible", "")} vendors mapped by scale and momentum'
            + (f'; the {_HORIZON_TOP} largest and fastest shown here' if crowd else '') + '. '
            f'<a href="{full_href}">Full map with names</a>.</p>')


def _v2_logos(conn, market_id: int) -> Dict[str, str]:
    """Each vendor's mark by display name, for the vendors that have one
    (``bw_brands.logo_data``, a data URI written by
    ``scripts/fetch_vendor_logos.py``)."""
    from sqlalchemy import text as _sql

    rows = conn.execute(_sql("""
        SELECT b.display_name, b.logo_data
          FROM bw_market_brands mb JOIN bw_brands b ON b.id = mb.brand_id
         WHERE mb.market_id = :m AND b.logo_data IS NOT NULL
    """), {"m": market_id}).fetchall()
    return {r[0]: r[1] for r in rows if r[1] and str(r[1]).startswith("data:image/")}


def _mark(logos: Optional[Dict[str, str]], vendor: str, size: int = 18) -> str:
    """The vendor's mark as an inline image, or nothing. Looked up by the
    name the page is about to print, so a withheld vendor never gets one."""
    uri = (logos or {}).get(vendor or "")
    if not uri:
        return ""
    return (f'<img class="v2-mark" src="{uri}" alt="" width="{size}" height="{size}" '
            'loading="lazy">')


def _v2_images(conn, uris: List[str]) -> Dict[str, str]:
    """The image collected with each record, by uri: a LinkedIn post's
    picture (``image_url``, kept since 2026-08-29, 800 px or wider).
    The social collector's ``thumbnail`` is not used: a Reddit or Bluesky
    preview is 140 px wide and was reaching the lead slot stretched to
    320. Records without a picture are absent from the map."""
    from sqlalchemy import text as _sql

    uris = sorted({u for u in uris if u})
    if not uris:
        return {}
    rows = conn.execute(_sql("""
        SELECT uri, social_meta->>'image_url' AS img
          FROM articles
         WHERE uri = ANY(:uris) AND jsonb_typeof(social_meta) = 'object'
           AND social_meta->>'image_url' IS NOT NULL
    """), {"uris": uris}).fetchall()
    # A rendered PDF page (a carousel or a document post) is a wall of small
    # text, unreadable as a thumbnail; a company logo is not a picture of
    # the story. Photos, cards and link previews stay.
    skip = ("document-images", "company-logo")
    return {r[0]: r[1] for r in rows
            if str(r[1]).startswith("http") and not any(k in str(r[1]) for k in skip)}


def _shared_view_note(conn, market_id: int, allowed_brand_ids: List[int]) -> str:
    """What the shared view leaves out, in one sentence, with the trial link."""
    from sqlalchemy import text as _sql

    total = conn.execute(_sql("""
        SELECT COUNT(*) FROM bw_market_brands
         WHERE market_id = :m AND role <> 'excluded'
    """), {"m": market_id}).scalar() or 0
    return ('<p class="mm-src">This is a shared view. It covers the '
            f'{len(allowed_brand_ids)} most active of the {total} vendors we '
            'watch, and leaves the rest out. Figures that cover the whole '
            'market say so. <a href="#mm-trial">Request a trial</a> to see '
            'all of it.</p>')


def _safe_list(fn, *args, **kwargs) -> List[Dict[str, Any]]:
    try:
        return list(fn(*args, **kwargs) or [])
    except Exception as exc:                                      # noqa: BLE001
        logger.warning("front page input %s failed: %s", getattr(fn, "__name__", fn), exc)
        return []


def build_market_report_v2(conn, market: Dict[str, Any], *, days: int = 30,
                           section: Optional[str] = None,
                           piece: Optional[int] = None,
                           page: Optional[str] = None,
                           sort: Optional[str] = None,
                           topic: Optional[int] = None,
                           allowed_brand_ids: Optional[List[int]] = None,
                           link_params: Optional[Dict[str, Any]] = None
                           ) -> bytes:
    """The front page, or one of its sections as a page of its own.

    ``topic`` opens one subject from the stored "Being discussed" and
    "Emerging" run as a page of its articles; an id the newest run does
    not carry raises LookupError.

    Same access rules as the report: a restricted reader's developments are
    computed from the vendors it may see, everything with text is checked
    for withheld names, and the finished bytes are checked again before they
    leave. Nothing on the front page is blurred: the hiring top five and the
    market figures are readable in the shared view (user's decision,
    29 August 2026); a hiring section page blurs the entries past five.

    Our own pieces (``kind`` analysis or note, approved) are public in full,
    whoever opens the page — an editorial piece naming a vendor is our
    writing, not the roster (decision 29 August 2026). Like the Horizon they
    are rendered apart, into ``_PIECES_SLOT``, and put back after the
    withheld-names check. ``piece`` opens one of them as a page; an unknown
    or unapproved id raises LookupError.
    """
    from app.services import market_analysis as man
    from app.services import market_briefing as mbr
    from app.services import market_assessment as massess
    from app.services import market_corpus as mcorp
    from app.services import market_entitlements as ent

    if section is not None and section not in V2_SECTIONS:
        raise KeyError(f"unknown section {section!r}")
    if page is not None and page not in V2_PAGES:
        raise KeyError(f"unknown page {page!r}")
    pieces = _safe_list(mbr.approved_pieces, conn, market["id"])
    piece_row = None
    if piece is not None:
        piece_row = next((p for p in pieces if int(p["id"]) == int(piece)), None)
        if piece_row is None:
            raise LookupError(f"no approved piece {piece}")

    link_params = dict(link_params or {})
    teaser = allowed_brand_ids is not None
    withheld = ent.withheld_names(conn, market["id"], allowed_brand_ids)

    def _safe(fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:                                  # noqa: BLE001
            logger.warning("front page input %s failed: %s",
                           getattr(fn, "__name__", fn), exc)
            return None

    assessment = massess.assess(conn, market, days=days,
                                allowed_brand_ids=allowed_brand_ids)
    rows = mcorp.articles(conn, market["id"], limit=2000, days=days,
                          require_signal_for_social=False)
    highlights = _safe(man.social_highlights, conn, market["id"], days=days,
                       limit=_V2_HIGHLIGHTS * 2) or []
    hiring = _safe(man.hiring, conn, market["id"], days=days) or {}
    sov_rows = list(((_safe(man.share_of_voice, conn, market["id"], days=days)
                      if section is None else None) or {}).get("vendors") or [])
    # The same numbers for the window before this one, so the attention card
    # can mark movement — a 30-day rolling sum barely shifts day to day and
    # read as "not updating" without it (8 Sep 2026).
    sov_prev = list(((_safe(man.share_of_voice, conn, market["id"],
                            days=2 * days, until_days_ago=days)
                      if section is None else None) or {}).get("vendors") or [])
    # The newest stored subjects run: one indexed read, ranked ids inside.
    from app.services import market_topics as mt
    topics = (_safe(mt.latest, conn, market["id"])
              if (section is None or topic is not None) else None)
    if topic is not None and mt.topic_by_id(topics, topic) is None:
        raise LookupError(f"no topic {topic}")

    # Every account with a post in the period, not the 80 most reacted-to:
    # the card looks tracked people up in this list, and a followed analyst
    # whose one post drew no reactions fell off the end and read as "quiet".
    top_voices = (_safe(man.top_voices, conn, market["id"], days=days, limit=5000)
                  if section in (None, "social") else None)
    pc = _safe(man.period_comparison, conn, market["id"], days=days)
    period_txt = _fmt_range(*pc["current_range"]) if pc else f"last {days} days"

    if teaser:
        # Operator policy, 9 Sep 2026: a restricted reader sees the news,
        # posts and developments of EVERY vendor — the editorial surfaces
        # are open, because a movers card capped to the public tier sat on
        # 2 Sep while the market moved. What stays restricted to the
        # authorized set are KPIs and metrics: the attention bars, the
        # hiring figures, and the benchmark report (view=report keeps its
        # full masking). The maturity map names every rated vendor by the
        # 27 Aug decision; the earlier drop_text_mentioning calls on
        # developments, rows, highlights, topics and voices are gone on
        # purpose.
        # Masked, not filtered: the count of open roles is the market's.
        hiring = ent.mask_rows(hiring, allowed_brand_ids) or {}
        allowed_names = set(ent.vendor_names(conn, market["id"], allowed_brand_ids).values())
        sov_rows = ent.filter_rows(sov_rows, allowed_brand_ids, allowed_names)
        sov_prev = ent.filter_rows(sov_prev, allowed_brand_ids, allowed_names)


    developments = assessment["developments"]
    devs_by_id = {d["event_id"]: d for d in developments}

    # Each vendor's developments in the period before this one, for the
    # activity bars: one run over a window twice as long, split at the
    # current period's first day. None when the earlier window is one
    # nothing was watching, so the bars carry no arrows.
    previous_counts: Optional[Dict[str, int]] = None
    if section is None and pc and pc.get("comparable"):
        try:
            both = massess.material_developments(conn, market["id"], days * 2,
                                                 market=market)["developments"]
            first_day = pc["current_range"][0]
            previous_counts = {}
            for d in both:
                if (d.get("date") or "") < first_day:
                    for v in d.get("vendors") or []:
                        if v.get("vendor"):
                            previous_counts[v["vendor"]] = previous_counts.get(v["vendor"], 0) + 1
        except Exception as exc:                                  # noqa: BLE001
            logger.warning("front page previous-period counts failed: %s", exc)
            previous_counts = None
    lead_piece = pieces[0] if (pieces and section is None and piece_row is None
                               and _piece_is_fresh(pieces[0])) else None
    parts = _v2_sections(developments, rows, assessment.get("discussion") or [],
                         highlights, lead_from_developments=lead_piece is None)
    buckets = parts["buckets"]
    buckets["analysis"] = [p for p in pieces if lead_piece is None or p["id"] != lead_piece["id"]]
    # Latest research: reports vendors cite, then the analyst firms' own
    # posts. Both come out of the rows already fetched, which are the masked
    # set in the shared view, so a withheld vendor's citation is not here.
    from app.services import market_research as mres
    domain_names = _safe(_v2_vendor_domains, conn, market["id"]) or {}
    # A firm's own post ("Announcing The Forrester Wave…") is not a vendor
    # citing a report; it belongs under the firm's posts, not "Cited by".
    firm_hosts = tuple(mres.analyst_domains(market))
    def _own_post(r):
        h = (urlparse(r.get("uri") or "").netloc or "").lower().removeprefix("www.")
        return any(h == d or h.endswith("." + d) for d in firm_hosts)
    buckets["research"] = (mres.group_citations([r for r in rows if not _own_post(r)], domain_names)
                           + mres.analyst_posts(rows, market))
    pieces_html: List[str] = []   # rendered apart; put back after the check

    def piece_slot(html_fragment: str) -> str:
        pieces_html.append(html_fragment)
        return _PIECES_SLOT
    try:
        images = _v2_images(conn, [e.get("uri") for d in developments
                                   for e in (d.get("evidence") or [])])
    except Exception as exc:                                      # noqa: BLE001
        logger.warning("front page images failed: %s", exc)
        images = {}
    logos = _safe(_v2_logos, conn, market["id"]) or {}
    registry_total = int(((assessment.get("inputs") or {}).get("registry_total")) or 0)
    generated = datetime.now(timezone.utc)

    def section_href(key: str) -> str:
        return "?" + _relink(link_params, days=days, view="v2", section=key)

    def section_inner(key: str, items: List[Dict[str, Any]],
                      total: Optional[int] = None) -> str:
        if key == "analysis":
            return (piece_slot("".join(_v2_piece_card(p, link_params) for p in items))
                    if items else "")
        if key == "hiring":
            return _v2_hiring(items, hiring, total=total, logos=logos) if items else ""
        if key == "research":
            return _v2_research(items, logos) if items else ""
        if key == "voices":
            return _v2_voices(items, []) if items else ""
        if key == "social":
            return _v2_voices(items, parts["highlights"]) if (items or parts["highlights"]) else ""
        return _v2_stories(items, images, logos)

    # ---- chrome shared by the front page and a section page
    jump = "".join(
        f'<a href="{section_href(k)}"'
        + (' aria-current="page"' if k == section else "")
        + f'>{esc(v["heading"])}</a>' for k, v in V2_SECTIONS.items())
    if market.get("is_public"):
        # The two standing reports sit at the end of the section row, after
        # Latest research, outlined so they read as pages rather than sections.
        jump += "".join(
            f'<a class="n-jump-page" href="?{_relink(link_params, days=days, view="v2", page=k)}">{label}</a>'
            for k, label in (("consensus", "Consensus"), ("horizons", "Three horizons")))
    rss = (f'<a class="n-rss" href="feed.xml?days={days}" title="Subscribe in a feed reader">RSS</a>'
           + _AI_FEED_LINK.format(days=days) if market.get("is_public") else "")
    pages = ((f'<a href="?{_relink(link_params, days=days, view="v2")}">Front page</a>'
              if section else "")
             + f'<a href="?{_relink(link_params, days=days, view="report")}">Analyst View</a>'
             f'<a href="?{_relink(link_params, days=days, view="news")}">News river</a>'
             + rss + '<a class="n-tip" href="#mm-tip">Submit news</a>' + _book_link(market))
    periods = "".join(
        f'<a href="?{_relink(link_params, days=d, view="v2", section=section)}"'
        + (' aria-current="page"' if d == days else "")
        + f'>{d} days</a>' for d in (7, 30, 90))
    body: List[str] = [f"{_FONT_LINK_V2}<style>{EXTRA_CSS}{NEWS_CSS}{DARK_CSS}{V2_CSS}</style>",
                       '<div class="mm-news mm-v2">',
                       '<div class="n-top">' + _brand_line()
                       + f'<nav class="n-jump" aria-label="Sections">{jump}</nav>'
                       f'<nav class="n-pages" aria-label="Pages">{pages}{_theme_toggle()}</nav>'
                       f'<span class="n-market">{esc(market["name"])}</span></div>']
    horizon_html = ""

    if page == "about":
        body.append('<main class="v2-grid"><div class="v2-main v2-one">'
                    + _v2_about_page(market, link_params, days) + "</div></main>")
    elif piece_row is not None:
        others = [p for p in pieces if p["id"] != piece_row["id"]][:6]
        body.append('<main class="v2-grid"><div class="v2-main v2-one">'
                    + piece_slot(_v2_piece_page(piece_row, others, link_params))
                    + "</div></main>")
    elif topic is not None:
        cluster = mt.topic_by_id(topics, topic) or {}
        member_uris = cluster.get("uris") or []
        trows = mcorp.articles(conn, market["id"], limit=max(len(member_uris), 1),
                               uris=member_uris, require_signal_for_social=False)
        kind = ("Emerging" if topic in (topics.get("emerging") or [])
                else "Being discussed")
        n_recent, n_total = int(cluster.get("n_recent") or 0), int(cluster.get("n_total") or 0)
        # The count the reader can check against the list below.
        shown_txt = (f'{len(trows)} shown of {n_total}'
                     f'. {n_recent} of the {n_total} are from the last 7 days.')
        body.append('<header class="v2-mast"><div>'
                    f'<div class="n-kicker">{esc(market["name"])} · {esc(kind)}</div>'
                    f'<h1>{esc(cluster.get("name") or "")}</h1>'
                    f'<p class="n-sub">{esc(cluster.get("summary") or "")} '
                    f'{esc(shown_txt)} Grouped over the last '
                    f'{int(topics.get("window_days") or 30)} days.</p></div>'
                    f'<div><nav class="n-periods" aria-label="Reporting period">{periods}</nav>'
                    f'<div class="n-period">Generated {generated.strftime("%d %B %Y, %H:%M UTC")}'
                    '</div></div></header>')
        body.append('<main class="v2-grid"><div class="v2-main v2-one">'
                    + (render_news_river(trows) if trows
                       else '<p class="v2-subline">Nothing in this subject is readable in this view.</p>')
                    + "</div></main>")
    elif section:
        sec = V2_SECTIONS[section]
        items = buckets[section]
        # A section page lists newest first by default (user, 2 Sep 2026);
        # ``?sort=rank`` keeps the front page's order — importance bands for
        # the development sections, biggest recruiters for hiring. The sort
        # is stable, so equal dates keep their rank order.
        if sort != "rank":
            def _item_day(it: Any) -> str:
                if section == "research":
                    payload = it[1] if isinstance(it, tuple) else {}
                    return str(payload.get("latest") or payload.get("published") or "")
                if section == "analysis":
                    stamp = it.get("published_at") or it.get("updated_at")
                    return (stamp.isoformat() if hasattr(stamp, "isoformat")
                            else str(stamp or ""))
                if section in ("voices", "social"):
                    return str(it.get("published") or "")
                return str(it.get("date") or "")
            items = sorted(items, key=_item_day, reverse=True)
        count = len(items) + (len(parts["highlights"]) if section == "social" else 0)
        body.append('<header class="v2-mast"><div>'
                    f'<div class="n-kicker">{esc(market["name"])} · {esc(period_txt)}</div>'
                    f'<h1>{esc(sec["heading"])}</h1>'
                    f'<p class="n-sub">{esc(sec["subline"])} {count} in the period.</p></div>'
                    f'<div><nav class="n-periods" aria-label="Reporting period">{periods}</nav>'
                    '<nav class="n-periods" aria-label="Order">'
                    f'<a href="?{_relink(link_params, days=days, view="v2", section=section)}"'
                    + ("" if sort == "rank" else ' aria-current="page"') + '>Newest first</a>'
                    f'<a href="?{_relink(link_params, days=days, view="v2", section=section, sort="rank")}"'
                    + (' aria-current="page"' if sort == "rank" else "") + '>Ranked</a></nav>'
                    f'<div class="n-period">Generated {generated.strftime("%d %B %Y, %H:%M UTC")}'
                    '</div></div></header>')
        body.append('<main class="v2-grid"><div class="v2-main v2-one">')
        cap = _V2_CAPS.get(section)
        if section == "hiring" and teaser and cap and len(items) > cap:
            # The top five are readable; the rest of the list is the trial's.
            sig = [d for d in items if d.get("event_type") == "significant_hiring"]
            inner = (section_inner(section, items[:cap], total=len(sig))
                     + _teaser_open("The remaining hiring entries")
                     + _render_hiring_block([d for d in items[cap:]
                                             if d.get("event_type") == "significant_hiring"],
                                            logos=logos)
                     + _TEASER_END)
        else:
            inner = section_inner(section, items)
        body.append(_v2_section(section, inner, count=count, days=days, wide=True))
        body.append("</div></main>")
    else:
        body.append('<header class="v2-mast"><div>'
                    f'<div class="n-kicker">Cyberfuturists · {esc(period_txt)}</div>'
                    f'<h1>{esc(market["name"])}</h1>'
                    f'<p class="n-sub">Market News and Trends for {esc(market["name"])}</p></div>'
                    f'<div><nav class="n-periods" aria-label="Reporting period">{periods}</nav>'
                    f'<div class="n-period">Generated {generated.strftime("%d %B %Y, %H:%M UTC")}'
                    '</div></div></header>')
        body.append('<main class="v2-grid"><div class="v2-main">')
        # The lead, then the findings under it.
        body.append('<section class="v2-lead" id="v2-lead">')
        lead = parts["lead"]
        findings = assessment.get("findings") or []
        if lead_piece is not None:
            body.append(piece_slot(_v2_piece_card(lead_piece, link_params, lead=True)))
        elif lead is not None:
            body.append(_v2_lead(lead, images, logos))
        elif findings:
            body.append(_render_findings(findings[:1], devs_by_id))
            findings = findings[1:]
        else:
            body.append(f'<p class="n-empty">No development met the evidence bar '
                        f'in the last {days} days.</p>')
        body.append(_v2_highlights(findings, devs_by_id))
        body.append("</section>")
        for key in V2_SECTIONS:
            items = buckets[key]
            if key == "analysis" and not items:
                continue   # nothing of ours to show: no empty section (user, 29 Aug)
            shown = items[:_V2_CAPS[key]] if key in _V2_CAPS else items
            count = len(items) + (len(parts["highlights"]) if key == "social" else 0)
            inner = section_inner(key, shown, total=sum(
                1 for d in items if d.get("event_type") == "significant_hiring"))
            body.append(_v2_section(key, inner, count=count, days=days,
                                    more_href=section_href(key), wide=(key == "analysis")))
        body.append("</div>")
        # ---- the sidebar
        body.append('<aside class="v2-side">')
        from app.services import market_horizon as mh
        stored = _safe(mh.latest, conn, market["id"], n=2) or []
        if stored:
            horizon = mh.with_movement(stored[0], stored[1] if len(stored) > 1 else None)
            # Names every rated vendor, as the report does by decision; rendered
            # apart and put back after the withheld-names check.
            horizon_html = _v2_horizon(
                horizon, "?" + _relink(link_params, days=days, view="report") + "#mm-horizon")
            body.append('<div class="v2-card"><h2>Market Maturity Map</h2>'
                        + _HORIZON_SLOT + "</div>")
        topics_card = _v2_topics(topics, link_params, days)
        if topics_card:
            body.append('<div class="v2-card"><h2>What the market is talking about</h2>'
                        + topics_card + "</div>")
        body.append('<div class="v2-card"><h2>Who moved</h2>'
                    + _v2_moved(_recent_movers(assessment.get("developments") or []),
                                logos=logos) + "</div>")
        motion = _v2_motion(sov_rows, logos, prev=sov_prev)
        if motion:
            body.append('<div class="v2-card"><h2>Who got attention</h2>' + motion + "</div>")
        tracked = _safe_list(_v2_tracked_voices, conn)
        voices_card = _v2_voices_card(tracked, top_voices, teaser=teaser)
        if voices_card:
            body.append('<div class="v2-card"><h2>Influence and Influencers</h2>' + voices_card + "</div>")
        # withheld=[]: the briefing summary is editorial text, open under the
        # 9 Sep policy; ``restricted`` still gates the layout.
        body.append(_render_briefing_card(conn, market, withheld=[],
                                          restricted=teaser, link_params=link_params))
        # Last in the column (user, 29 Aug). The assessment already masks a
        # withheld vendor's name here, so the list stays readable in the
        # shared view.
        numbers = _v2_numbers(assessment, hiring, days)
        body.append('<div class="v2-card"><h2>By the numbers</h2>' + numbers
                    + _v2_top_vendors((assessment.get("distribution") or {}).get("by_vendor") or [],
                                      previous_counts, logos)
                    + "</div>")
        body.append("</aside></main>")

    about_href = "?" + _relink(link_params, days=days, view="v2", page="about")
    reports = "".join(
        f' · <a href="?{_relink(link_params, days=days, view="v2", page=k)}">{label}</a>'
        for k, label in (("consensus", "Consensus"), ("horizons", "Three horizons"))
    ) if market.get("is_public") else ""
    body.append('<div class="n-foot">' + _brand_line()
                + f'<span>{esc(market["name"])} · {esc(period_txt)} · '
                f'<a href="{about_href}">About</a> · <a href="{about_href}#privacy">Privacy</a>'
                f'{reports}</span></div>')
    if teaser:
        body.append(_shared_view_note(conn, market["id"], allowed_brand_ids))
    body.append(_contact_panel(market["id"], market["name"], trial=teaser))
    body.append("</div>")
    if horizon_html:
        body.append(f"<script>{_HORIZON_JS}</script>")

    title = (f'About — {market["name"]}' if page == "about"
             else f'{piece_row.get("title") or ""} — {market["name"]}' if piece_row is not None
             else f'{(mt.topic_by_id(topics, topic) or {}).get("name") or ""} — {market["name"]}' if topic is not None
             else f'{market["name"]} — {V2_SECTIONS[section]["heading"]}' if section
             else f'{market["name"]} front page')
    rendered = v2_document(title, "".join(body))
    if teaser:
        rendered = _apply_teasers(rendered)
    # The name tripwire is off for this page by the 9 Sep policy: editorial
    # text may name any vendor, and the metric surfaces are structurally
    # filtered above rather than scrubbed after the fact. view=report keeps
    # the full check.
    rendered = ent.enforce_no_withheld(rendered, [],
                                       context=f'market {market["id"]} front page')
    rendered = rendered.replace(_HORIZON_SLOT, horizon_html)
    for fragment in pieces_html:
        rendered = rendered.replace(_PIECES_SLOT, fragment, 1)
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
           f'<a href="?{_relink(link_params, days=days, view="v2")}">Front page</a>'
           f'<a href="?{_relink(link_params, days=days, view="report")}">Analyst View</a>'
           f'<a href="?{_relink(link_params, days=days, view="news")}">News river</a>'
           f'{_theme_toggle()}</nav>'
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
                + '<p class="n-distil"><a href="?' + _relink(link_params, days=days, view="report")
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
                '<section class="n-block v2-briefing">' + mbr.render_body(briefing) + more
                + "</section></main>")
    body = (f"{_FONT_LINK_V2}<style>{EXTRA_CSS}{NEWS_CSS}{DARK_CSS}{V2_CSS}</style>" '<div class="mm-news mm-v2">'
            + nav + main
            + '<div class="n-foot">' + _brand_line()
            + f'<span>{esc(market["name"])}</span></div></div>')
    rendered = v2_document(f'{market["name"]} — briefing', body)
    rendered = ent.enforce_no_withheld(rendered, withheld,
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
        # An account row's vendor identity lives in its tag ("Vendor (Torq)")
        # and its profile summary, not in an id or name key, so filter_rows
        # keeps it. The first repeatedly-posting account of a withheld vendor
        # (Torq, 4 Sep 2026) named it in the voices table and the fail-closed
        # check 500d the whole restricted report. Text scan, like the
        # articles; a quoted highlight can name one the same way.
        if voices:
            voices["consistent"] = ent.drop_text_mentioning(
                voices.get("consistent") or [], withheld)
        highlights = ent.drop_text_mentioning(highlights or [], withheld)
        dataset = ent.filter_rows(dataset, allowed_brand_ids, allowed_names)
        # The movers list was fetched above the gate and never filtered; the
        # first withheld vendor whose headcount moved (2 Sep 2026) put its
        # name in the Headcount table and the fail-closed check 500d the
        # whole restricted report. Rows carry brand_id, so filter_rows works.
        movers = ent.filter_rows(movers, allowed_brand_ids, allowed_names)
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
    body: List[str] = [f"{_FONT_LINK_V2}<style>{EXTRA_CSS}{NEWS_CSS}{DARK_CSS}{V2_CSS}</style>"]

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
    body.append('<div class="mm-news mm-v2">')
    body.append('<div class="n-top">'
                + _brand_line()
                + '<nav class="n-jump" aria-label="Jump to section">'
                '<a href="#mm-horizon">Maturity Map</a>'
                '<a href="#mm-assessment">Assessment</a>'
                '<a href="#mm-moved">Who moved</a>'
                '<a href="#mm-developments">Developments</a>'
                '<a href="#mm-analysis">Evidence</a>'
                '<a href="#mm-registry">Vendors</a>'
                '<a href="#mm-method">Method</a></nav>'
                '<nav class="n-pages" aria-label="Pages">'
                f'<a href="?{_relink(link_params, days=days, view="v2")}">Front page</a>'
                f'<a href="?{_relink(link_params, days=days, view="news")}">News river</a>'
                + (f'<a class="n-rss" href="feed.xml?days={days}" title="Subscribe in a feed reader">RSS</a>'
                   + _AI_FEED_LINK.format(days=days) if market.get("is_public") else "")
                + _book_link(market) + _theme_toggle() + '</nav>'
                f'<span class="n-market">{esc(market["name"])}</span></div>')

    body.append('<main class="n-main"><span id="mm-overview"></span>')
    periods = "".join(
        f'<a href="?{_relink(link_params, days=d, view="report")}"'
        + (' aria-current="page"' if d == days else "")
        + f'>{d} days</a>' for d in (7, 30, 90))
    question = (market.get("question") or "").strip()
    scope_text = (market.get("market_scope_description") or "").strip()
    body.append('<div class="n-head"><div>'
                # The publisher's line, then the period; the page is the
                # rating, and it carries the publisher's name the way a
                # named research product does.
                f'<div class="n-kicker">Cyberfuturists · {esc(period_txt)}</div>'
                f'<h1>{esc(market["name"])} Market Maturity Map</h1>'
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
            "Market Maturity Map",
            f"Where {horizon['counts']['rated']} of the market's "
            f"{horizon['counts']['eligible']} vendors are mapped today, based on "
            "how active they are, how they are growing and how fast they are moving.",
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

    # 2. Vendors with a development
    main_devs = assessment["main_developments"]
    other_devs = assessment["other_developments"]
    body.append('<section class="n-block" id="mm-moved">'
                '<div class="n-sec-head"><h2>Vendors with a development</h2>'
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
    body.append('<div class="n-sec-head"><h2>Developments</h2>'
                f'<div class="n-sec-actions">{rss}'
                f'<span class="n-updated">{esc(period_txt)}</span></div></div>')
    collected = int(assessment.get("collected_records") or 0)
    body.append(f'<p class="n-distil">{collected:,} records collected &rarr; '
                f'{len(developments)} development'
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
    # The panel stays open: the trial ask and the drawers below sit inside
    # it as content boxes, and the page closes it at the end.
    body.append(f"<script>{_NEWS_JS}</script>")
    if teaser:
        body.append(_trial_panel(market["id"]))

    # ================================================================
    # The evidence behind the conclusions, collapsed
    # ================================================================
    body.append(_drawer_open(
        "Evidence",
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
            body.append("<h4>Crunchbase score changes in the period</h4>")
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
                        + ('Changes appear once the scores have been collected for a '
                           'full period.' if not comparable else
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
                        f'open roles, with {esc(top[1]["vendor"])} '
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
                            f'headcount data so far: {esc(readings)} against where '
                            'these vendors started. A chart needs three.</p>')
            else:
                body.append('<p class="mm-src">Average change from each '
                            "vendor's first headcount count. Weeks covering fewer "
                            f'than half of the {hc_trend["watching"]} vendors '
                            'are less reliable.</p>')
                body.append(_line_chart(
                    hc_trend["points"], x_key="week",
                    series=[("avg_pct_vs_baseline", "#475569",
                             "Average change since first count")]))
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
        "Tracked vendors",
        f"{len(registry_rows)} companies we watch, with each one's "
        "collection state, country, founding year, staff, funding and open "
        "roles.",
        anchor="mm-registry"))
    body.append(section_open("Vendor registry"))
    body.append('<p><a class="mm-btn" href="#mm-missing">Is your company missing?</a></p>')
    body.append('<p class="mm-src">Sorted by collection state, then by the '
                "date of each vendor's latest development, then by name."
                + (f' {left_out} vendor{"" if left_out == 1 else "s"} on the '
                   'list are not shown, because collection is off for them or '
                   'we have never read anything about them.' if left_out else "")
                + '</p>')
    body.append('<table class="mm-table"><thead><tr>'
                "<th>Vendor</th><th>Status</th><th>Country</th>"
                "<th>Founded</th>"
                '<th class="mm-num">LinkedIn headcount</th>'
                '<th class="mm-num">Disclosed funding</th>'
                f'<th class="mm-num">Developments, {days}d</th>'
                '<th class="mm-num">Open roles</th>'
                "<th>Latest development</th></tr></thead><tbody>")
    short_state = {"material_change": "Changed",
                   "monitored_no_material_change": "No change",
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
    body.append(_contact_panel(market["id"], market["name"], trial=False))
    body.append(_drawer_open(
        "How this was measured",
        "Which sources we read, how much of the market each one reached, what "
        "every figure counts, and the records behind it.",
        anchor="mm-method"))
    body.append(section_open("What an event type can and cannot tell you"))
    body.append('<p>A product launch is a statement that something is available; it says '
                'nothing about adoption, which this report reads only from customer evidence. '
                'A funding round is capital raised, not revenue. A partnership is an agreement, '
                'not sales. An acquisition is a change of owner, not of product. The '
                '"why it matters" column therefore states only what the source itself says '
                'about the event — the product, the amount, the partner, the buyer — and is '
                'left empty when the source says nothing more than the headline.</p>')
    body.append("</section>")
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
        body.append(_pct_row("Have public job listings",
                             hc["measured"], hc["total"]))
    body.append("</tbody></table>")
    counts = observation.get("counts") or {}
    body.append(
        f'<p class="mm-src">Of the {registry_total} vendors, '
        f'{counts.get("material_change", 0)} had a development, '
        f'{counts.get("monitored_no_material_change", 0)} were watched and '
        f'had none, {counts.get("incomplete_coverage", 0)} '
        'were only partly collected'
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
        body.append(_shared_view_note(conn, market["id"], allowed_brand_ids))
    body.append("</div>")   # closes .mm-news.mm-v2

    rendered = v2_document(f'{market["name"]} Market Maturity Map',
                           "".join(body))
    if teaser:
        rendered = _apply_teasers(rendered)

    # Fail closed on the name, not on the page: a withheld name that reaches
    # the bytes is scrubbed to the withheld label and logged as a bug, so a
    # masking miss costs an ugly label instead of a 500 for every reader.
    rendered = ent.enforce_no_withheld(rendered, withheld,
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
