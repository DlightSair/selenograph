# SIH 2026 — PS 26166

**Multi-modal, Sun-angle and scale-invariant image correspondence using Chandrayaan-2 optical images (OHRC, TMC-2, IIRS)**

Registers Chandrayaan-2 optical imagery (source/moving) against Lunar Reconnaissance Orbiter imagery (reference/fixed, via LROC QuickMap) despite large differences in illumination (sun azimuth/elevation), viewpoint, and scale (up to ~150-300x GSD ratio).

## Layout

```
SIH26166/
├── algo/     # registration pipeline: preprocessing, matching, geometry, evaluation
├── ui/       # frontend/demo app (AOI selection, upload, results viewer)
├── data/     # local data cache — not committed, see data/README below
└── docs/     # architecture notes, write-ups
```

- Core CV/DL work happens in [algo/](algo/) — see [algo/README.md](algo/README.md) to get started.
- UI/demo app lives in [ui/](ui/), independent of the algo package; it calls into `algo` as a library or over a small API.
- Design rationale and the full pipeline write-up: [docs/architecture.md](docs/architecture.md).

## Data sources

- **Source (moving)**: Chandrayaan-2 OHRC / TMC-2 / IIRS — [ISSDC chmapbrowse](https://chmapbrowse.issdc.gov.in/MapBrowse/)
- **Reference (fixed)**: LRO WAC/NAC mosaics, NAC DTMs — [LROC QuickMap](https://quickmap.lroc.im-ldi.com)
- **DEM** (optional, for illumination normalization): SLDEM2015 / LOLA gridded data, or a TMC-2-derived DTM

Downloaded data is not committed — see `.gitignore`. Use `algo/scripts/` to fetch/organize it under `data/`.
