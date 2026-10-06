#!/usr/bin/env python3
"""One review page per site, from the per-brand samples brand_relevance_eval.py drew.

Rows are shuffled within each brand so their order says nothing about the
system's decision. Answers are kept in the browser as they are given and
saved as one file, <site>-reviews-<date>.json, keyed by article URL; the
score command reads it for every brand of the site:

    python3 scripts/brand_relevance_review_page.py eval/brand_relevance/reviews/sunstar-*-2026-10-06.json \\
        --out eval/brand_relevance/reviews/sunstar-review-2026-10-06.html
    .../brand_relevance_eval.py score eval/brand_relevance/reviews/sunstar-lion-corporation-2026-10-06.json \\
        --reviews eval/brand_relevance/reviews/sunstar-reviews-2026-10-06.json
"""
import argparse
import html
import json
import random

ANSWERS = [("coverage", "Coverage"), ("sector", "Sector"), ("owned", "Brand's own"),
           ("not_coverage", "Not coverage"), ("cannot_tell", "Cannot tell")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("samples", nargs="+")
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    metas = [json.load(open(p)) for p in sorted(a.samples)]
    site, drawn = metas[0]["site"], metas[0]["drawn"]
    save_name = f"{site}-reviews-{drawn}.json"
    rng = random.Random(a.seed)
    sections, total = [], 0
    for m in metas:
        rows = list(m["rows"])
        rng.shuffle(rows)
        items = []
        for r in rows:
            total += 1
            uid = html.escape(r["uri"])
            opts = "".join(f'<label><input type="radio" name="{uid}" value="{k}"> {v}</label>' for k, v in ANSWERS)
            en = (f'<div class="en">{html.escape(r["title_en"])}</div>'
                  if r.get("title_en") and r["title_en"] != r["title"] else "")
            items.append(
                f'<li data-uri="{uid}"><a href="{uid}" target="_blank" rel="noopener">{html.escape(r["title"] or r["uri"])}</a>'
                f'{en}<div class="src">{html.escape(r.get("source") or "")}</div>'
                f'<div class="sum">{html.escape(r.get("summary") or "")}</div><div class="opts">{opts}</div></li>')
        sections.append(
            f'<section><h2>{html.escape(m["brand"])} <span class="n">{len(rows)} articles</span></h2>'
            f'<p class="q">Does this article belong in independent coverage of <b>{html.escape(m["brand"])}</b>?</p>'
            f'<ol>{"".join(items)}</ol></section>')
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(site.capitalize())} brand review</title>
<style>
:root{{--bg:#fff;--fg:#1f2328;--muted:#656d76;--line:#d8dee4;--accent:#0969da;--done:#e6f4ea}}
@media (prefers-color-scheme:dark){{:root{{--bg:#0d1117;--fg:#e6edf3;--muted:#8d96a0;--line:#30363d;--accent:#4493f8;--done:#12261b}}}}
body{{background:var(--bg);color:var(--fg);font:15px/1.45 system-ui,sans-serif;max-width:920px;margin:0 auto;padding:16px}}
h1{{font-size:22px;margin:.2em 0}} h2{{font-size:18px;margin:1.6em 0 .2em;border-bottom:1px solid var(--line);padding-bottom:.2em}}
.n{{color:var(--muted);font-size:13px;font-weight:normal}} .q{{color:var(--muted);margin:.2em 0 .6em}}
li{{margin:.9em 0;padding:.5em .6em;border:1px solid var(--line);border-radius:6px}} li.done{{background:var(--done)}}
a{{color:var(--accent)}} .src,.en{{color:var(--muted);font-size:13px}} .sum{{font-size:13px;margin:.3em 0}}
.opts label{{display:inline-block;margin:.25em 1em .25em 0;white-space:nowrap}}
.bar{{position:sticky;top:0;background:var(--bg);padding:8px 0;border-bottom:1px solid var(--line);display:flex;gap:12px;align-items:center;flex-wrap:wrap}}
button{{font:inherit;padding:6px 14px;border-radius:6px;border:1px solid var(--line);background:var(--accent);color:#fff;cursor:pointer}}
</style></head><body>
<h1>{html.escape(site.capitalize())}: brand coverage review</h1>
<p>One question per article: <b>does it belong in independent coverage of the brand?</b><br>
<b>Coverage</b>: independent reporting where the brand is the subject or plays a real part (a quote, an action, a comparison).
<b>Sector</b>: about the brand's market, the brand not playing a part.
<b>Brand's own</b>: published by the brand itself.
<b>Not coverage</b>: anything else, including a different company with the same name, a deal listing or a passing mention.
<b>Cannot tell</b>: not enough to decide.</p>
<p>The order is random; the system's own decision is not shown. Answers are kept in this browser as you go.
When finished, press <b>Save answers</b> and send the file <code>{html.escape(save_name)}</code>.</p>
<div class="bar"><button onclick="save()">Save answers</button><span id="count"></span></div>
{''.join(sections)}
<div class="bar"><button onclick="save()">Save answers</button></div>
<script>
const KEY = {json.dumps('brand-review-' + site + '-' + drawn)}, TOTAL = {total};
let answers = {{}};
try {{ answers = JSON.parse(localStorage.getItem(KEY) || '{{}}'); }} catch (e) {{ answers = {{}}; }}
function paint() {{
  document.querySelectorAll('li[data-uri]').forEach(li => {{
    const v = answers[li.dataset.uri];
    li.classList.toggle('done', !!v);
    if (v) {{ const i = li.querySelector('input[value="' + v + '"]'); if (i) i.checked = true; }}
  }});
  document.getElementById('count').textContent = Object.keys(answers).length + ' of ' + TOTAL + ' answered';
}}
document.addEventListener('change', e => {{
  if (e.target.type !== 'radio') return;
  answers[e.target.name] = e.target.value;
  try {{ localStorage.setItem(KEY, JSON.stringify(answers)); }} catch (err) {{}}
  paint();
}});
function save() {{
  const blob = new Blob([JSON.stringify({{site: {json.dumps(site)}, drawn: {json.dumps(drawn)}, answers}}, null, 1)], {{type: 'application/json'}});
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = {json.dumps(save_name)}; a.click();
}}
paint();
</script></body></html>"""
    open(a.out, "w", encoding="utf-8").write(page)
    print(f"{a.out}: {len(metas)} brands, {total} articles; answers save as {save_name}")


if __name__ == "__main__":
    main()
