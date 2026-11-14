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


3. OPEN ITEMS FROM THE FIRST REVIEW: STATUS AFTER THE SECOND ROUND

Second round: commits 273e7b9..e294981, one per item; demo/ rebuilt in 33ab3c2. Details in section 4.

HIGH
- FIXED. Few-frame stacking (epochs.py, CLIP_MIN_FRAMES). Pixels covered by 2-3 frames now use the
  median; one frame is used as it is. Pictures resting on fewer than 4 frames say
  "few frames: unreliable".
  WISE 0855 first visit (3 frames): the deepest pixel went from -31 sigma to -4 sigma, and the
  red "new object" is gone from demo/WISE_0855/difference.png [ran, saw].
  Limit that remains: with exactly 2 frames the median is the mean of the two, so a bad value still
  shows (now documented, and those pictures carry the note).
- FIXED. Wavelength spread in light curves. Each point is labelled with its wavelength; a warning
  and a figure note appear when usable points differ by more than 0.01 µm (Epsilon Indi B 0.018,
  RW Aur 0.013, WISE 0855 0.033). The README now attributes Epsilon Indi B's step to wavelength
  (4.195 against 4.211 and 4.213 µm), not calibration.
  Not done (longer): interpolating each visit to the exact wavelength.

MEDIUM
- FIXED, documented. Clipping suppresses short events. clip=False (the plain average; Epsilon Indi B
  stacks bit-identical to the pre-clipping code, blobs included) is available in flipbook,
  player_html, picture and visits. Each visit has clipped_fraction. README and API.md state the limit
  (a 1 px-per-frame mover keeps about 1/3 of its light, a flare in 6 of 21 frames about 3/4).
  The filled saturated cores are still trimmed at single pixels (pictures only).
- FIXED. Neighbour warning text. A neighbour within 8″ is named, with its separation and G
  magnitude, as the main light source where the target is faint. Only WISE 0855 triggers it.
- FIXED. Masked circles labelled "saturated". Lower limits now exist only for saturated
  measurements; mostly-masked circles are "masked: not measured" (open squares). The WISE 0855 point
  at 2.427 µm (DICHROIC, not saturated) no longer shows a lower limit. Saturated targets keep theirs:
  Barnard 114 of 119, R Draconis 76 of 76, RW Aur 50.
- FIXED. Per-visit spectra and releases. A release column was added to spectrum tables; the
  every-visit spectrum gets the mixed-release note and warning (Barnard, Epsilon Indi B, RW Aur,
  R Draconis; not WISE 0855, all DR1).

LOW
- OPEN. RELEASE_MARKERS has 6 entries; a 7th distinct release raises KeyError (plots.py). Not in this
  round's list.
- FIXED. Light-curve grouping uses the frames' visit (new "visit" column). Epsilon Indi B at tol 0.1
  now shows one point per visit (4) instead of splitting visit 0 into 56.7 and 37.5 mJy.
- OPEN. parse_target rewrites unusual input ("RA 1,5 Dec 2" reaches SIMBAD as "1 5 2"; Dec-first
  input fails). Not in this round's list.
- PARTLY FIXED. Empty-cache error in demo mode. API.md now states that OSError can come in demo mode
  too. SPHEREX_CACHE is still not expanded ("~") or made absolute, and api._load still lets the raw
  OSError through.
- FIXED. Documentation mismatches (REVIEW 2e). resolve() now returns known=True for a test target's
  coordinates (code fix); the OSError wording and the RA= example (now "RA=133.795129 Dec=-7.245147",
  which resolves to WISE 0855) are corrected; the _fmt and stack_epoch docstrings are updated.
- FIXED. Difference labels. Panels read "earlier: <date>", "later: <date>", "later minus earlier"
  with "red = brighter later, blue = brighter earlier" in prepare_demo.py, lesson7_diff.py,
  explore.py and api.picture "pair". The pair is now always later minus earlier, whichever order a
  and b are given in (same image either way; the same visit twice is a ValueError). Band differences
  say "red = brighter in D6, blue = brighter in scaled D2".

STILL OPEN (data side)

MEDIUM
- epochs.py stack_epoch clipping.
  What is wrong: in crowded fields the clipping rejects more than defects. clipped_fraction is 9.1%
  for RW Aur D1 visit 0 (3-5% elsewhere, 1% for WISE 0855), probably star edges that differ between
  frames.
  Evidence so far: the target sums moved by under 0.4% for RW Aur in the first review. Not looked
  at further.
  Fix: compare sigma 4 with sigma 5 on RW Aur's field stars, and raise it if the fraction drops
  without bringing the blobs back.
- WISE 0855 light curve.
  What is wrong: the 0.33 -> 0.63 mJy "doubling" is still drawn as a line between two visit
  averages, and the 0.33 comes from one usable frame. It now carries three caveats (wavelengths
  4.486-4.519 µm, the dominant 6″ neighbour, upper limits), but the line itself still invites a
  reading as variability.
  Fix: mark single-frame visit averages (open symbol) or draw no line when a visit has one point.
- prepare_demo.py save_flipbook_and_diff.
  What is wrong: the backup difference.png has no "few frames: unreliable" note; only the API titles
  do. WISE 0855's earlier panel is a 3-frame median and looks noisier than the later one.
  Fix: put api._few() into that figure's panel title (2 lines).

LOW
- plots.py plot_light_curve_simple.
  What is wrong: at wide tolerances (5-6 points per visit) the wavelength labels overlap and become
  unreadable (Epsilon Indi B at tol 0.1). This view always carries the wide-tolerance warning.
  Fix: label only the visit averages with their wavelength range when a visit has more than 3 points.
- visits(detector=...).
  What is wrong: visits with no image from that detector get n_min 0 and clipped_fraction NaN
  (R Draconis D3 in visits 1, 2, 5). This is correct, but not documented as "no picture".
  Fix: one line in API.md.
- The item list named "api.frames", which does not exist in the API. clip was passed through
  flipbook, player_html, picture and visits instead.
- From the first review, still open: RELEASE_MARKERS (6 releases at most), parse_target rewriting
  unusual input, and SPHEREX_CACHE expansion (see above).

Not checked: the Streamlit app (not installed, out of scope); downloads and refresh=True (need the
network); asteroid overlay content.


4. SECOND ROUND: CHECKS AND READINESS

Every item was followed by an offline smoke test of every view on Barnard's Star and Epsilon Indi B,
plus a check on the target the item concerned. All smoke tests passed [ran].

Item checks [ran]:
- Few-frame stacking. WISE 0855 visit 0: -31 sigma hole -> -4 sigma.
  The target's peak moved 0.0944 -> 0.1106, which is 0.5 sigma of the stack noise; the 2.5 px sum
  moved 1.03 -> 1.15, which is 0.9 sigma. With 3 frames reading 0.072, 0.159 and 0.161, the median
  simply picks a different value than the mean. Pictures only; photometry is measured separately.
  Barnard and Epsilon Indi B peaks unchanged; n_min 18-30 there, 3 for WISE 0855 visit 0.
- clip. clip=False is bit-identical to the 6c8b275 stacks for all 4 Epsilon Indi B visits
  (max difference 0), blobs -129/-165/-171 sigma included; clip=True gives 0/-1/-1 sigma.
  clipped_fraction: Epsilon Indi B 2.3-4.3%, WISE 0855 0.9-1.1%.
- Remaining items: as described in section 3.

After all items [ran]:
a. demo/ rebuilt offline: prepare_demo.py --skip-explore 30 of 30 steps OK; make_gallery.py 45 of 45
   products, none failed. cache/ unchanged: 1758 files, none newer than the start of the branch.
   Committed as 33ab3c2.
b. Every api view for all five targets: all OK except the asteroid overlay, which fails offline as
   expected.
   Measurements equal to REVIEW 2b:
   - light-curve visit means: Epsilon Indi B 40.55 / 39.79 / 44.69; RW Aur 153.86 / 156.92 / 231.81;
     WISE 0855 0.33 / 0.63;
   - spectrum channels: 62 / 53 / 79; R Draconis 76 lower limits;
   - flags rows 9-11; visits 3 / 4 / 3 / 3 / 6.
   New outputs only: the visit and release columns, the warnings, and n_min / clipped_fraction.
   First video, timed one target at a time (REVIEW 2b in brackets): Barnard 6.3 s (5.7),
   Epsilon Indi B 4.6 (4.4), WISE 0855 2.4 (2.4), RW Aur 2.7 (2.8), R Draconis 4.2 (4.2).
   Nothing is slower by more than 12%.
c. demo/WISE_0855/difference.png [saw]: the black hole at about 8h55m00s -7°14.2′ in the earlier
   panel is gone, and so is the red spot it made. The one strong red spot left is WISE 0855 itself,
   at the centre of the field. The panels read "earlier: 2025-05-05", "later: 2026-04-27",
   "later minus earlier (red = brighter later, blue = brighter earlier)".

Readiness (data side):
- Data pipeline: 90% (was 85%). Stacking is now robust to single-frame defects at every frame count
  from 3 up, with a raw-average option and per-visit statistics; downloads are still one at a time,
  and the network path was not tested.
- Science correctness: 85% (was 65%). The three misleading cases from REPORT.md are fixed or
  carry specific caveats on the figure and in the warnings. What is left: WISE 0855's
  one-frame "doubling" line, and the clipping's 9% rejection in a crowded field, not yet understood.
- Documentation: 85% (was 45%). README and API.md match the code (all 12 signatures checked),
  including stacking and its limits; missing are presentation material and anything about the
  app's own behaviour, which was not run.
