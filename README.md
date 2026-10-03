# SIH 2026 — PS 26166

**Multi-modal, Sun-angle and scale-invariant image correspondence using Chandrayaan-2 optical images (OHRC, TMC-2, IIRS)**

Registers Chandrayaan-2 optical imagery (source/moving) against Lunar Reconnaissance Orbiter imagery (reference/fixed) despite large differences in illumination (Sun azimuth/elevation), viewpoint (off-nadir views, jitter, terrain parallax) and scale (0.25 m OHRC to 100 m WAC, ratios up to ~400x).

How each of the three difficulties is handled, with measurements: [docs/architecture.md](docs/architecture.md), [docs/benchmark.md](docs/benchmark.md) (synthetic scenes with a known answer) and [docs/results.md](docs/results.md) (real projects).

## Layout

```
SIH26166/
├── algo/     # registration pipeline: preprocessing, matching, geometry, evaluation
│   └── src/algo/api/   # local FastAPI server wrapping algo.pipeline.run — used by desktop/
├── desktop/  # Flutter desktop app (Windows/Linux/macOS) — primary UI, see desktop/README.md
├── ui/       # future lightweight web demo, not started yet
├── data/     # local data cache — not committed, see data/README below
└── docs/     # architecture notes, write-ups
```

- Core CV/DL work happens in [algo/](algo/) — see [algo/README.md](algo/README.md) to get started.
- Desktop app lives in [desktop/](desktop/) — see [desktop/README.md](desktop/README.md) to run it. It talks to `algo.api.server` over localhost; nothing is bundled/compiled together.
- A future web demo will reuse the same `algo.api.server` backend from [ui/](ui/).
- Design rationale and the full pipeline write-up: [docs/architecture.md](docs/architecture.md).

## Data sources

- **Source (moving)**: Chandrayaan-2 OHRC / TMC-2 / IIRS — [ISSDC chmapbrowse](https://chmapbrowse.issdc.gov.in/MapBrowse/) and PRADAN (`pradan.issdc.gov.in`, login required; IIRS cubes are ~1-3 GB each)
- **Reference (fixed)**: LRO WAC/NAC mosaics, NAC DTMs — [LROC QuickMap](https://quickmap.lroc.im-ldi.com); NASA Moon Trek WMTS tiles (WAC 100 m global mosaic, LROC NAC south-pole mosaic, WAC polar) via `algo/scripts/fetch_wac_reference.py` / `fetch_trek_polar_nac.py`; Chang'e-2 7 m ortho mosaic (Moon Trek) is used only as a supplementary cross-check, not as an LRO reference
- **DEM** (optional; re-lit with the source's Sun for illumination-robust matching and used for parallax): LOLA polar DEMs ([PGDA](https://pgda.gsfc.nasa.gov/products/90), cloud-optimized GeoTIFF; `algo/scripts/fetch_lola_dem_window.py` reads only a window), SLDEM2015, or a TMC-2-derived DTM

Downloaded data is not committed — see `.gitignore`. Use `algo/scripts/` to fetch/organize it under `data/`.
