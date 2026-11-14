REVIEW: hackathon branch, data side, 14 Nov 2026

Branch "hackathon". Starting commit 6c8b275 (the working tree as it was, committed unchanged).
All checks ran offline on the real cached data: demo mode on, network calls blocked in code, and
writes into the project blocked except where a fix needed them (demo/ in fix 7). Nothing was
downloaded. The cache is unchanged: 1758 files, none newer than the starting commit.
app_example.py was not touched.

Part 2 was done by a separate reviewer agent. It saw only the branch diff, REPORT.md and the review
instructions, and changed nothing. Before writing this I checked its most important new finding
myself (section 2d).

Tags: [ran] = executed, [read] = from the code, [saw] = opened the image.


1. WHAT WAS DONE

Fix 1, outlier-robust stacking. Commits af3a5a7, plus 4eecaa9 (a follow-up that silences a log
notice).
  Change: epochs.stack_epoch now uses a per-pixel sigma-clipped mean along the frame axis (sigma 4,
  median centre, MAD spread, up to 3 iterations). Pixels covered by fewer than 4 frames keep the
  plain nanmean.
  Check [ran]:
  - Epsilon Indi B D5 visit 0 blobs: -129, -165, -171 sigma before; 0, -1, -1 after.
  - WISE 0855 D6 visit 2 blob: -20 sigma before; -1 after.
  - Target peaks per visit, unchanged to 4 digits: Barnard 747.2 / 906.6 / 917.8; RW Aur
    52.41 / 78.17 / 101.4; WISE 0855 0.0944 / 0.146 / 0.219; Epsilon Indi B 15.0 / 17.4 / 16.7 / 16.2.
  - Exception: R Draconis' filled saturated core, 1210 / 1500 / 1076 before, 1187 / 1355 / 1076
    after (-2%, -10%, 0%).
  - Stacking time unchanged (3-8 s per target).
  - Follow-up commit: sigma_clip logged an "invalid values" notice on every stack. It is now silenced.

Fix 2, releases in light curves. Commit f019cc2.
  Change:
  - photometry.light_curve adds a "release" column ("DR1", "QR3").
  - plot_light_curve_simple draws one marker per release (circle, square, ...) with a legend entry.
  - When releases are mixed, a corner note appears on the figure and api.light_curve_figure adds a
    sentence to table.meta["warning"].
  Check [ran, saw]:
  - Releases per point: Barnard DR1 x3, QR3 x2; Epsilon Indi B DR1, DR1, QR3; RW Aur DR1, DR1, QR3, QR3.
    The warning appears for these three.
  - WISE 0855 (all DR1) and R Draconis (one point) get no release warning.
  - Figures inspected.

Fix 3, coordinate input. Commit fc0aa9d.
  Change: parse_target strips "RA ... Dec ..." labels (also "RA=", "RA:") and accepts one comma
  between the two parts.
  Check [ran]: 12 input forms of the WISE 0855 and Barnard positions resolve to the right target
  with proper motion. These include the brief's exact text "RA 08h55m10.831s, Dec -7d14m42.53s",
  "RA=...", "ra: ... dec: ...", and comma forms in sexagesimal, colon and decimal notation. Names
  starting with "Ra" ("Rasalhague", "RAVE J1234") still go to the name resolver.

Fix 4, cache location. Commit 92b90a1.
  Change: net.CACHE_ROOT = $SPHEREX_CACHE, otherwise <package parent>/cache. frames.py,
  download.py, gaia.py and wise.py build their paths from it.
  Check [ran]:
  - Started from the scratchpad folder: the project cache is found, and visits, video and overlay
    all work for Barnard and Epsilon Indi B.
  - With SPHEREX_CACHE pointing to an empty folder, the library looks for the network instead, so
    the override is used.

Fix 5, Gaia-epoch matching. Commit 46076bd.
  Change: known_near also compares typed coordinates with each moving target's position at 2016.0
  (and, as before, today and its catalogue position), within 10″.
  Check [ran]:
  - The real Gaia DR3 entries from the cached cones now pick up proper motion and the right cache
    name: Barnard's Star "269.448503 +4.739420" (before the fix: no motion, its own new cache entry)
    and Epsilon Indi B.
  - A position 30″ away does not match.
  - Side result: the KNOWN position of Epsilon Indi B, marked "not checked", agrees with Gaia DR3
    to 1.0″.

Fix 6, presentation. Commit 4ffa4a8.
  Change:
  - Light-curve value labels have 3 significant figures (0.329, 0.630, 45.0, 2,349).
  - The no-data message suggests another wavelength, and says demo mode uses only cached images.
  - A meta warning when tol > 0.05 µm (api.MAX_SAFE_TOL).
  - The light-curve time axis spans all visits of the target.
  - Spectrum legends are drawn outside the axes; the long saturation label is wrapped.
  Check [ran, saw]:
  - WISE 0855 labels now read 0.329 / 0.630 instead of "0" / "1".
  - The R Draconis axis runs 2025-05 to 2026-07 instead of 2023 to 2027.
  - Epsilon Indi B at tol 0.1 gets the warning; at 0.05 it does not.
  - The RW Aur and Barnard spectra have their legends clear of the data.
  - Smoke test on Barnard and Epsilon Indi B passed.

Fix 7, demo/ rebuilt offline. Commit 1dfdd60.
  Change: prepare_demo.py --skip-explore, then make_gallery.py, run with the network blocked and
  writes allowed only in demo/.
  Check [ran]:
  - All steps OK for all five targets (SUMMARY.txt). Cache unchanged (1758 files, none newer).
  - Visible changes:
    - Epsilon Indi B deep, video, difference and all-detector video: the three fake red spots and a
      white blob are gone, and the stretch is better. 30-60% of pixels changed.
    - WISE 0855 overlay: the black rectangle is gone (57%).
    - RW Aur D5+D6 video (34%) and RGB (20%).
  - Barnard's and R Draconis' D5+D6 videos gained frames (2 -> 3, 1 -> 3), and STATUS.md now says
    READY for some products that said PARTIAL. Both are because the old gallery predated part of the
    current cache; nothing was downloaded.
  - Two note files are new: Epsilon Indi B and RW Aur light curves now carry the mixed-release
    warning.

Fix 8, documentation. Commit a1a4c34.
  Change: README.md rewritten:
  - what the tool does, and how it meets each challenge point (Aladin stated as not used);
  - install and run commands, with SPHEREX_DEMO=1 and SPHEREX_CACHE;
  - a feature list limited to what was run, with a separate "in the code, not verified here" list;
  - the five targets, known limits and data credits.
  API.md matched to the code: all 12 functions with exact signatures, settings (set_demo_mode,
  demo_mode, defaults, constants), output columns, note keys, meta warnings, errors, measured speeds,
  and a "For the app" section (demo mode on at start, show table.meta warnings, use api.defaults()).
  Check [ran, by the reviewer]: signatures, columns, keys and warnings compared with the code. See 2e.

Nothing was skipped or reverted.
The only deviation from "one fix per commit" is fix 1, which took two commits.


2. REVIEW FINDINGS

a. Scope [read, reviewer; high certainty]
  Each commit touches only what its fix needs. No change outside scope was found. Photometry method,
  aperture and sky ring are unchanged, and app_example.py is untouched.
  Small leftover: the stack_epoch docstring (epochs.py:55-56) still says "averaged with nanmean".

b. Regressions [ran, reviewer; high certainty]
  Every view (all three video modes as player and GIF, visit, deep, pair, band difference, RGB,
  overlay, light curve, latest and every-visit spectrum, flags, visits) ran for all five targets.
  The only failure is the expected one: the asteroid overlay offline.
  Nothing got slower by more than half. First video: Barnard 5.7 s (REPORT 5.3), Epsilon Indi B 4.4
  (7.0), WISE 0855 2.4 (3.8), RW Aur 2.8 (4.6), R Draconis 4.2 (7.1). Other views are within
  REPORT's ranges.
  One exception is explained by more data, not a regression: Barnard D5+D6 takes 10.2 s (REPORT 2-6.5)
  because it now stacks all 122 cached frames instead of 45.
  Measured results are unchanged:
  - Light curves: Epsilon Indi B 40.55 / 39.79 / 44.69 mJy; RW Aur 153.9 / 156.9 / 231.8;
    WISE 0855 0.33 / 0.63.
  - Spectrum channels: 62 / 53 / 79, and 76 lower limits for R Draconis.

c. Sigma-clipped stacking [ran, reviewer; high certainty for the numbers, medium for the general claim]
  - It works as intended against single-frame defects. Negative holes and positive one-frame spikes
    (hot pixels or cosmic rays, e.g. 8.0 against about 0.02) are removed.
  - Target fluxes within 2.5 px change by 0 to 4%: Barnard -4.3 / -1.7 / 0%, others under 1.4%.
  - Saturated, filled cores are not clipped at the target pixel. Some pixels beside the core are:
    Barnard 719 -> 430, R Draconis 458 -> 104. Sums near R Draconis' core drop up to 15-19%. This
    is not visible in the minus-mean videos. These cores are not measurements anyway; pictures only.
  - Real sources can be clipped if they appear in only a minority of a visit's frames. Tested by
    injecting sources into the real 21-frame WISE 0855 cube:
    - constant source, or brightness varying 5x across frames: kept in full;
    - bright in 10 of 21 frames: kept;
    - bright in 6 of 21: 76% kept;
    - mover at 1 px (3″) per frame: 34% kept;
    - mover at 0.3 px per frame: 94% kept.
    The test targets themselves are unaffected (none moves that fast within a visit). But fast
    movers and short transients fade in per-visit stacks, which matters if the tool is pitched for
    asteroids or flares.
  - Gap: where fewer than 4 frames cover a pixel there is no protection. WISE 0855's first visit has
    only 3 frames, and one frame plants a -31 sigma hole there. 4 of 7 weekly WISE pictures are
    also unprotected.

d. Science honesty, the three REPORT cases [ran and saw]
  1. Fake spots.
     - Epsilon Indi B: fixed. Only the motion pair remains in difference and minus-mean [saw].
     - WISE 0855: NOT fixed. The 3-frame first visit still has a black hole at about
       8h55m00s -7°14.2′. In demo/WISE_0855/difference.png (A-B) it is a red "brighter now" spot as
       strong as the target, and it is red in 2 of 3 minus-mean frames. I opened the image and
       confirmed it. Nothing on these products says so; STATUS.md lists them as READY.
  2. WISE 0855 blend. A warning is in the metadata, in the demo note files and as 7-pt text under
     the figures. But it says "part of the light ... mostly at short wavelengths", which understates
     that 0.75-2.5 µm is essentially all the G=16.3 neighbour. The 0.329 -> 0.630 "doubling" is
     still drawn, and the 0.329 comes from a single usable frame. The app does not show meta
     warnings (out of scope; API.md now asks it to).
  3. Epsilon Indi B jump. Now visibly marked as a release change (square marker, legend, note,
     meta warning). But the reviewer's new evidence points to wavelength, not calibration:
     - the QR3 point is at 4.195 µm, the DR1 points at 4.211 and 4.213 µm, all inside the
       ±0.02 µm window;
     - on a slope of about -3 mJy per 0.01 µm, DR1 interpolated to 4.195 µm gives 43.9 and
       45.4 mJy, against QR3's 44.7;
     - at four other matched wavelengths DR1 and QR3 agree within about 2% (one is -6%).
     My single-field-star test in REPORT.md (+14%) was weaker evidence. So the README's "probably
     calibration" is likely wrong, and the mixed-release note, while true, suggests the wrong cause.
     The wavelength values in demo/Epsilon_Indi_B/lightcurve.csv (4.211, 4.213, 4.195) confirm the
     offset; the cause is medium-high certainty.
  Also seen (older than this branch): the WISE 0855 spectrum shows a triangle labelled "saturated:
  lower limit" at 2.43 µm. It is a DICHROIC-masked point, not a saturated one.

e. Documentation against the code [ran, reviewer; high certainty]
  These all match the code:
  - signatures and defaults of the 12 API functions and set_style;
  - constants, table columns, note keys and all four meta warnings;
  - input formats, the SPHEREX_CACHE override, and the script flags.
  Small mismatches:
  - resolve() returns known=False for coordinates of a test target, while defaults() recognises them.
  - API.md says OSError happens only outside demo mode, but an empty cache in demo mode also raises
    a raw OSError.
  - API.md's example "RA=133.79 Dec=-7.24" parses but is 36″ from WISE 0855, so it does not resolve
    to that target.
  - The _fmt docstring example says "2,350" where the code prints "2,349".
  - The README's Epsilon Indi B sentence (see d3).

f. Repository state [ran; high certainty]
  - git status is clean on "hackathon" (REVIEW.md is committed with this report). No stray files.
  - The files changed are exactly those in the diff.
  - cache/ has 1758 files, none newer than the starting commit, and is unchanged after all review
    runs.
  - The untracked Barnard coordinate frame table, .streamlit/ and REPORT.md were committed in the
    starting snapshot 6c8b275, as the "commit the current working tree" rule asked.


3. STILL OPEN (data side)

HIGH
- epochs.py:94 (CLIP_MIN_FRAMES = 4; constant at epochs.py:18).
  Visits or pixels with 1-3 frames are not protected.
  How a user notices: WISE 0855 first visit has a fake red "new object" in difference.png,
  minus_mean.gif and the live difference video. Weekly pictures are also exposed.
  Fix: with 2-3 frames use the per-pixel median (or drop a value far from the others relative to
  the frame noise), and label 1-frame pictures as unreliable. About 15 min, then rebuild demo/.
- api.py light_curve_figure and photometry.py light_curve (the ±tol window).
  Points inside the window differ in wavelength by up to 0.04 µm. On steep spectra that alone makes
  about 10% steps, which the release note may then be blamed for.
  How a user notices: Epsilon Indi B 40.5 -> 39.8 -> 44.7.
  Fix: put each point's wavelength in the figure (it is already in the table), add a note when the
  spread is large, and correct the README sentence now. About 15 min. Interpolating each visit to the
  exact band from neighbouring channels would be the proper fix (longer).

MEDIUM
- epochs.py:86-94.
  Clipping suppresses sources present in only a minority of a visit's frames (34% kept for a
  1 px-per-frame mover, 76% for a source bright in 6 of 21 frames). It also cuts filled saturated
  cores at individual pixels.
  How a user notices: fast asteroids and short flares fade from per-visit pictures.
  Fix: document it in README and API.md, or offer an unclipped stack option.
- api.py:456 (neighbour warning text), plus the app.
  The wording understates a dominant neighbour, and the warning is small.
  How a user notices: the WISE 0855 spectrum and "doubling" read as its own.
  Fix: when a neighbour is within about 8″, say "below about 3 µm the light is mostly the
  neighbour"; the app should st.warning(table.meta["warning"]).
- photometry.py:73-76 with plots.py (spectrum legend label).
  A mostly-masked (not saturated) circle gets a lower limit labelled "saturated".
  How a user notices: the WISE 0855 spectrum shows a "saturated" triangle at 2.43 µm.
  Fix: compute flux_min_mjy only when saturated is True, or label it "masked".
- Per-visit spectra (api.spectrum_figure with all_visits=True) mix DR1 and QR3 without the release
  note that light curves now carry.
  Fix: reuse _mixed_releases_note on the measurement table.

LOW
- plots.py RELEASE_MARKERS has 6 entries; a 7th distinct release raises KeyError. Fix: cycle them.
- plots.py plot_light_curve_simple groups points by a 30-day gap, not by the frames' visit, so a
  wide tolerance can split one visit into two plotted points (Epsilon Indi B at tol 0.1: 56.7 and
  37.5 mJy in May and June 2025). Fix: group by the epoch column.
- targets.py parse_target rewrites unusual input before lookup: "RA 1,5 Dec 2" reaches SIMBAD as
  "1 5 2"; Dec-first input fails. Fix: rewrite only when both parts parse as coordinates.
- net.py CACHE_ROOT does not expand "~" and is not made absolute. An empty cache in demo mode gives
  a raw OSError, not a user message. Fix: Path(...).expanduser().resolve(); convert the error to
  ValueError in api._load.
- API.md: resolve()'s "known" flag, the OSError wording and the "RA=133.79" example (see 2e). The
  _fmt and stack_epoch docstrings are out of date.

Not checked: the Streamlit app (not installed, out of scope); downloads and refresh=True (need the
network); asteroid overlay content; whether every hole in the WISE 0855 first visit comes from the
same frame (only the deepest was traced).
