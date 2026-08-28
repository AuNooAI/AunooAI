# The Market Horizon now reads as a life cycle
_2026-08-28 · Market Monitor: the Market Horizon tab in the app and the map on the shared market report_

## What shipped
- The map's left-to-right sweep is now the vendor's stage: Emerging, Building, Scaling,
  Executing, by size. A vendor moves right as it grows.
- The distance from the base is now momentum. The inner band is holding, the middle band
  growing, the outer band accelerating. A vendor moves outward as it speeds up.
- "Establishing" is gone. The four stages are words people use about companies.
- Every vendor label has a clear spot. Crowded parts of the map use short leader lines
  instead of stacking names on dots or on each other.

## Why it matters
Before, the four regions were quarters of a grid: big-and-fast, fast, big, neither. Two of
them sat on opposite sides of the map, so there was no path a vendor could take through them
and nothing to read off a vendor's position except "which quarter". An analyst could not
answer "where is this vendor on its journey" from the picture.

Now the picture is the journey. A new vendor appears small at the left. If it is hiring,
shipping and being talked about, it pushes outward into the accelerating band. As headcount,
funding and customer evidence build, it sweeps right through Building and Scaling. At the
right end, the large vendors sit at the height their momentum earns them: a large vendor that
has stopped moving sits near the base, which is exactly what it is. The trail we already draw
for a big move since the previous map now shows a step along that path.

The analyst reading the app and the outsider reading the shared report both get this without
a key. The stage names run along the rim, the band names sit on the arcs, and the two axis
captions say what left-right and near-far mean.

## Release notes (copy-ready)
- Market Horizon: the map now reads left to right as the vendor's stage (Emerging, Building,
  Scaling, Executing) and outward as momentum (holding, growing, accelerating).
- Every vendor is labelled, with a leader line where the map is crowded.
- Hover a dot to see its stage, band, scores and markers.

## Demo / walkthrough
App: Explore → Market Monitor → Market Horizon. Hover a dot for the stage, band and scores.
The stage lists below the map are by stage; the Method section at the bottom states the cuts.

Shared report: https://aisoc.aunoo.ai/ → the map under the heading. Hover or tap a dot.

## Positioning notes
This is the difference between a scatter plot and a market map. The Gartner-style quadrant
tells a buyer which box a vendor is in today. This map tells the buyer which way the vendor is
moving and how fast, from readings we collect every week rather than from an analyst's
opinion, and it shows the whole rated market on one picture.

## Limits and what's next
- The stage is size, not maturity. A vendor with a large disclosed funding total and a large
  headcount is Executing even if its product is young. The innovating marker is the only
  product signal on the map.
- The cuts (25/50/75 for stage, 33/67 for band) are defaults in the config, not calibrated to
  any market. On AI in the SOC the growing band holds 26 of 40 vendors.
- Momentum needs two profile readings inside the 90-day window. Markets whose profile
  collection is younger than that place vendors nearer the base than they belong.
- A crowded centre still needs a few long leader lines. Numbering the densest cluster with a
  key beside the map is the next step if that gets worse.
