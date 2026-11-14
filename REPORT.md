# SPHEREx Flipbook: project assessment, 14 Nov 2026

Tags used throughout: [ran] = I executed it on the real cached data, offline, with the network blocked and writes into the project blocked. [saw] = I opened the file or image. [read] = inferred from reading code only. Git status is unchanged; nothing in the project was written.

## SUMMARY

The data library is in good shape. Every view (video, difference modes, pictures, overlays, light curve, spectrum, flags) ran offline for all five test targets, in 0.1 to 23 seconds per view.

The weak link is the app. The new version of `app_example.py` is uncommitted and has never run on this machine: Streamlit and pandas are not installed anywhere here. It also dropped the demo-mode switch, so a judge clicking colour pictures, "every visit" spectra or combined detectors will start minutes of downloads, or a near-hang on bad wifi.

Three results could mislead a careful judge:
- **Fake spots:** a single bad frame plants fake "new object" spots in difference videos (verified on Epsilon Indi B).
- **WISE 0855:** its light curve "doubles" and its short-wavelength spectrum is really a G=16.3 neighbour star.
- **Epsilon Indi B:** its +10% brightening lands exactly on the DR1→QR3 release change, and a field star jumps by the same amount.

Of yesterday's ten findings, seven are fixed and verified, two are partly fixed, and one (long download timeouts) is effectively back, because the app no longer turns demo mode on.

Most valuable use of the next ~2 hours: commit, install Streamlit and click through everything, restore demo mode, make stacking robust to outliers, and put the warnings back on the page. Only then add new features, with Aladin first.

## 1. CAPABILITY INVENTORY

Format: feature: status (evidence). Where it lives. Notes.

- **Target lookup by name:** works on real data [ran]. targets.py parse_target/resolve_name. All five names and their aliases resolve offline. SIMBAD/Sesame lookup of other names not tested (needs network).
- **Degrees and sexagesimal input:** works on real data [ran]. targets.py:161. These all work: `08h55m10.831s -7d14m42.53s`, `08:55:10.831 -07:14:42.53`, space-separated, and decimal degrees. These fail with "could not find": the brief's own form `RA 08h55m10.831s, Dec -7d14m42.53s`, and sexagesimal with a comma.
- **Proper motion and epochs:** works on real data [ran][saw]. targets.KNOWN, at_time. Coordinates typed within 10″ of a known target pick up its motion. The circle tracks the target in every picture. WISE 0855 uses its 2010.4 epoch.
- **Frame search and release handling:** works on real data [ran]. frames.py. DR1 and QR3 are merged and duplicate exposures removed. Future qrN/drN releases are picked up automatically [read]. The refresh path is unverified today.
- **Cutout download and cache:** works on real data via the cache [ran]. download.py. Integrity check plus PSF stripping. The download path itself was not run (read-only).
- **Cleaning and flags (QR2/QR3/DR1):** works on real data, with a hole [ran]. clean.py. Both header formats (MP_ and MSKN) plus fallback defaults. Some strongly negative single-frame pixels are not caught by any flag (see bug H1).
- **Per-visit stacking:** works, with a hole [ran]. epochs.py make_epochs/stack_epoch. A plain nanmean, so one bad frame survives the stack.
- **Combined detectors (D5+D6, all):** works on real data [ran]. Partial offline for 4 targets (frames missing from the cache).
- **Wavelength-range images (e.g. 4.4–4.7 µm):** works on real data [ran], all five targets.
- **Video as GIF:** works on real data [ran]. api.flipbook. 0.15–0.19 MB.
- **Interactive player:** works in code but unverified in a browser [ran: HTML generated, 0.06–0.65 MB]. api.player_html, new and uncommitted.
- **Difference and minus-mean videos:** work on real data [ran][saw]. Artefact spots from H1.
- **Deep image (all visits added):** works on real data [ran].
- **Band difference:** works on real data [ran]. Partial offline for 4 targets.
- **RGB:** works on real data [ran]. Partial offline for 4 targets.
- **Gaia DR3 overlay:** works on real data [ran][saw]. Disk cache hits for all five targets.
- **WISE (CatWISE) overlay:** works on real data [ran][saw]. Arrows only for motions measured at ≥5σ; halo filtering.
- **Asteroid overlay:** partly verified. out/WISE_0855/asteroids.png exists from an earlier run (not opened). Offline it fails cleanly as "not available".
- **Light curve:** partly works [ran][saw]. Correct handling of saturation and neighbours, but only 1–5 points per target, release boundaries are not marked, and value labels round to whole mJy.
- **Spectrum:** works on real data [ran][saw]. 53–79 of 102 channels. Saturated stars give lower limits.
- **Per-visit spectra:** works [ran]. Partial offline for Epsilon Indi B, RW Aur and R Draconis.
- **Flags view:** works on real data [ran]. 9–11 flag rows per target.
- **Visits / metadata table:** works on real data [ran], including the release of each visit.
- **URL parameters:** works in code but unverified [read]. target, detector, fov, wl, view, mode.
- **Streamlit app:** unverified and at risk [read]. A 273-line uncommitted rewrite; Streamlit not installed; demo-mode switch removed. Weekly pictures, speed control and choosing which visits to subtract exist in the API but are not shown in the app.
- **Offline / demo operation:** library works offline [ran]. The app is broken in practice: it only gets demo mode if launched with `SPHEREX_DEMO=1`, which nothing documents.
- **Backup gallery (demo/index.html, STATUS.md):** works [saw]. Every product for every target, with READY / PARTIAL / LOWER LIMITS labels.

## 2. STATE OF EACH TEST TARGET

All [ran] offline unless noted. "Visit" is a block of observations a few weeks long.

**Barnard's Star**
- **In the cache:** 363 frames (239 DR1, 124 QR3), 3 visits (Aug 2025, Mar–May 2026, Aug–Sep 2026). 360 of 363 frames cached, covering every detector and visit. Gaia and CatWISE catalogues cached.
- **demo/:** everything. Light curve and spectra are labelled LOWER LIMITS; combined-detector and colour products are PARTIAL.
- **Works offline:** every view.
- **What a judge sees:** a saturated star with a filled core. The circle moves about 11″ over the year. Difference mode shows a clean red/blue pair, which makes the motion obvious: this is the best "moving object" demo. The light curve is 5 grey triangles labelled "at least…". The overlay shows the proper-motion arrow.

**Epsilon Indi B**
- **In the cache:** 467 frames (347 DR1, 120 QR3), 4 visits. D5 is cached for all visits (31/24/7/24 frames). The last visit has D2, D3, D5 and D6 complete. The first visit has only 4 frames each of D1, D3 and D6. Catalogues cached.
- **demo/:** everything; per-visit spectra and multi-detector products PARTIAL.
- **Works offline:** D5 video in all modes, deep, pair, overlay, light curve at 4.2 µm (3 points), latest spectrum (62 channels), flags. RGB and band difference work, but from the first visit only, with 4 frames per detector.
- **What a judge sees:** a faint source with a motion pair at the target. The difference video also shows three red spots that are artefacts (H1). Light curve reads 41 → 40 → 45 mJy; the last jump is probably calibration (H3).

**WISE 0855**
- **In the cache:** 258 frames, all DR1, all cached. 3 visits: May 2025 (only 3–8 frames per detector), Oct–Dec 2025, Apr–May 2026. No QR3 visit in the frame list. Whether one now exists is unknown: the list was last searched 13 Nov.
- **demo/:** everything READY.
- **Works offline:** everything except asteroids.
- **What a judge sees:** a faint smudge in the circle at D6. The first visit is very noisy. The overlay shows long CatWISE arrows at the target, which looks good. The light curve shows 0.33 → 0.63 mJy, labelled "0" and "1". The spectrum shows about 1 mJy at 0.75–2.5 µm; that light is the neighbour star, not WISE 0855 (H2).

**RW Aur**
- **In the cache:** 336 frames (226 DR1, 110 QR3), 3 visits. D1 is cached for all visits. The last visit has every detector; the first two have only D1.
- **demo/:** everything; multi-detector products PARTIAL.
- **Works offline:** D1 video in all modes, overlay, light curve at 0.9 µm, latest spectrum (53 channels plus 50 lower limits), flags.
- **What a judge sees:** a crowded field. Difference mode shows RW Aur clearly brightening: 154 → 157 → 230 mJy. I checked this is real: field stars in the same frames stay within 1–3% [ran]. This is the strongest variability story.

**R Draconis**
- **In the cache:** 548 frames, 6 visits. D3 is cached for visits 0, 3 and 4; D3 has no frames at all in visits 1, 2 and 5. The last visit has D1, D2, D4 and D5 complete.
- **demo/:** everything; light curve and spectra are lower limits.
- **Works offline:** D3 video (3 pictures), modes, overlay, light curve, latest spectrum (76 lower limits), flags.
- **What a judge sees:** a huge saturated blob. Difference mode shows ring-shaped changes in the star's wings, so the variability is visible only qualitatively. The light curve is a single triangle on an axis running 2023 to 2027. This is the weakest target.

## 3. BUGS AND WEAK POINTS

### Critical

**C1. The app no longer turns demo mode on**
- **Where:** app_example.py. The committed version had a checkbox, on by default, at old lines 41–44. Nothing now calls `set_demo_mode`, and no document mentions `SPHEREX_DEMO`.
- **What happens:** any click that needs frames not in the cache downloads them.
  - RGB on Epsilon Indi B: about 150 frames.
  - "Every visit" spectrum: 190–350 frames.
  - D5+D6, "all", a wavelength range, or a different light-curve wavelength.
  - Each frame can take up to 6 tries, with waits of 5–60 s and a 120 s timeout (download.py:48, :79). On bad wifi that is effectively a hang behind a spinner.
- **Evidence:** [read] the code; [ran] the offline run printed how many frames each view would otherwise fetch.
- **Fix:** call `api.set_demo_mode(True)` at the top of the app unless the URL has `?live=1`, and launch with `SPHEREX_DEMO=1`.

**C2. The app has never run here, and the rewrite is uncommitted**
- **Where:** streamlit and pandas are missing from .venv and from requirements.txt; the venv is Python 3.14. app_example.py and api.py are modified but not committed.
- **What happens:** any Streamlit API mismatch shows up for the first time during demo prep. An accidental checkout loses the player.
- **Evidence:** [ran].
- **Fix:** commit on a branch, `pip install streamlit`, add it to requirements.txt, then click through 5 targets × 6 views.

### High

**H1. One bad frame plants fake sources in the stacks**
- **Where:** epochs.py:79 (`nanmean`).
- **What happens:** Epsilon Indi B D5, first visit, has three blobs at −130 to −170σ. Each comes from a single frame with values around −50 to −64, against a typical 0.001. In difference mode they become red spots in every frame, which look like new objects. WISE 0855 D6 visit 2 has another; it shows as a black hole in the overlay picture.
- **Evidence:** [ran] per-frame values at each blob; [saw] in the contact sheet and the WISE 0855 overlay.
- **Fix:** take a sigma-clipped mean along the frame axis (astropy.stats.sigma_clip on the cube), then rebuild the demo/ backups.

**H2. WISE 0855 is blended with a neighbour star**
- **What happens:** a G=16.3 star sits 4.4–7.5″ away, inside the 12″ measuring circle. It supplies essentially all of the 0.75–2.5 µm "spectrum" and probably drives the 0.33 → 0.63 mJy "doubling" as the target moves past it.
- **Where the warning went:** the warning exists, but the new app shows it only as 7-point text at the bottom of the figure. The old `st.warning` calls are gone (app_example.py:138–154).
- **Evidence:** [ran][saw].
- **Fix:** restore `st.warning(table.meta["warning"])`. For the presentation, say plainly that WISE 0855 below 3 µm is the neighbour.

**H3. Light curves mix data releases without saying so**
- **Where:** photometry.light_curve; the table has no release column.
- **What happens:** Epsilon Indi B rises 10–12% exactly at the DR1→QR3 boundary, and the one usable field star rises 14% in the same frames. That points to calibration, not the brown dwarf (one star, so suggestive only).
- **Evidence:** [ran]. RW Aur's change at the same boundary is real (see section 2).
- **Fix:** add a release column, use a different marker per release, and add a note when a light curve crosses releases.

**H4. Not a public web tool**
- **What happens:** the brief says "public-facing", but there is no hosting setup. The cache is 3.1 GB and the FITS files are gitignored.
- **Evidence:** [read].
- **Fix:** either present it locally and say so, or host on a VM with a trimmed cache (see section 4).

### Medium

**M1. The brief's coordinates fail when pasted as written**
- **Where:** targets.py:161–173.
- **What happens:** `RA …, Dec …` or a comma between the two parts gives "Could not find". [ran]
- **Fix:** strip the "RA" and "Dec" labels and commas before parsing.

**M2. The empty light-curve message gives bad advice**
- **Where:** api.py:482 says "Try a wider tolerance". The app's tolerance box allows up to 0.5 µm (app_example.py:137) with no caution.
- **Why it matters:** widening the tolerance is exactly how wavelengths get mixed. [read]
- **Fix:** reword the message and cap the tolerance at about 0.05 µm, or warn above it.

**M3. Light-curve labels round to whole mJy**
- **Where:** plots.py:140 uses `f"{m:,.0f}"`.
- **What happens:** WISE 0855's points are labelled "0" and "1" mJy. [saw]
- **Fix:** use 3 significant figures.

**M4. Light curves are very sparse**
- **What happens:** 1–5 points per target. R Draconis has one point, on an axis running 2023 to 2027. [saw]
- **Fix:** set the x-axis to the mission span. For saturated stars, use a wider window for the lower limits only.

**M5. Cache paths are relative**
- **Where:** frames.py:15, download.py:14, gaia.py:12, wise.py:27.
- **What happens:** started from any other folder, the app sees an empty cache. [read]
- **Fix:** build the paths from `Path(__file__)`.

**M6. Typed coordinates must be within 10″ to pick up proper motion**
- **Where:** targets.py:35.
- **What happens:** Barnard's Star's Gaia 2016 position is about 110″ from both its J2000 and today positions. Typed in, it becomes a static field with its own cache entry and new downloads. The untracked cache/frames/17h57m49_5s_04d41m36_2s.ecsv shows this already happened once, from a 1-second typo in RA. [ran][read]
- **Fix:** also match against the 2016 position, or widen the radius to about 3′.

### Low

- Spectrum legends sit on top of the data at 0.75–2.4 µm (plots.py:241, :297). [saw]
- The app keeps its own copy of the per-target defaults instead of calling `api.defaults()`. Today they match; an alias typed by hand gets the generic 1.6 µm. [read]
- The player iframe height (800 px) and the wrapping of the five example buttons are unverified. [read]

### Status of yesterday's findings

- **Gaia/WISE disk cache never hits:** fixed [ran]. Every overlay and neighbour check worked with the network blocked.
- **App and prepare_demo name frame tables differently:** fixed [ran]. There is now one naming rule (frames.table_path); aliases and coordinates all land on the same file.
- **App defaults not cached:** fixed for the five targets [ran]. Small leftover: the duplicated defaults table.
- **Only ValueError caught in the app:** fixed [read]. Any exception now becomes a short message.
- **Very long download timeouts:** still open, and effectively regressed (C1). The timeouts are unchanged and the app no longer turns demo mode on.
- **Light curves mixing wavelengths:** partly fixed. The ±0.02 µm default works [ran], but see M2, and release mixing (H3) is new.
- **No check for neighbours in the aperture:** fixed in the API [ran]. The app's page display regressed (H2). Only Gaia, i.e. optical, neighbours are checked.
- **Overclaiming "verdict":** fixed [ran]. It now reads "Catalogue check … This is not a detection".
- **Noisy CatWISE proper motions drawn as arrows:** fixed [read][saw]. ≥5σ cut, artefact flags and halo filtering.
- **Saturated targets returning zeros:** fixed [ran]. They now give NaN plus lower limits plus a message.

## 4. PERFORMANCE

Measured [ran], cached data, demo mode:

- **Server start:** importing the library takes about 3 s, once.
- **First video, cached target:** 3.8–7.1 s (WISE 0855 3.8, RW Aur 4.6, Barnard 5.3, Epsilon Indi B 7.0, R Draconis 7.1). Inferred: the time goes into cleaning and reprojecting 20–45 frames per visit.
- **Other modes of the same video:** 0.2–0.3 s.
- **GIF:** 0.7–1.1 s.
- **Deep or pair picture:** 0.1 s.
- **Band difference:** 2–4 s. **RGB:** 1–6 s.
- **Overlay:** 0.2–0.3 s.
- **Light curve:** 3–5.5 s.
- **Latest spectrum:** 5–8 s. **Every-visit spectrum:** 9–23 s.
- **Flags:** 0.1 s.
- **10′ field of view:** 3–7 s. **D5+D6:** 2–6.5 s. **Wavelength range:** 2.5–9 s.
- **Memory:** 220–240 MB peak per process after every view of one target. No problem.

New target, estimated (not run, because it would download):
- **First video: about 3–8 minutes.** That covers 2–4 archive searches plus about 50–70 cutout downloads, one after another. Each download is about 4.8 MB, including a PSF layer that is thrown away afterwards.
- **Latest spectrum:** about 100+ more downloads.
- **Every-visit spectrum:** 300–500 downloads, i.e. tens of minutes.
- I am not sure whether IRSA's cutout service can leave the PSF out of the download.

Disk: the cache is 3.1 GB, and 2.8 GB of that is 579 older 0.1° cutouts that still hold the PSF (4.8 MB each, against 0.41 MB for the newer files). This matters only if you ship or host the cache.

Changes that would help most:
1. **Demo mode on by default:** 5 min, low risk. Removes the worst case entirely.
2. **Warm the memory cache at startup** for the five default views: 10 min, low risk. The first click drops from 4–7 s to 0.3 s.
3. **Parallel downloads** (6 threads) in make_epochs, light_curve and spectrum: about 45 min, medium risk. A new target gets about 4–6× faster.
4. **Strip the PSF from the old cutouts:** 15 min, low risk if done on a copy. Only worth it for hosting.

## 5. FIT TO THE CHALLENGE

Each row: rating, then evidence, then what would raise it one level.

- **Core objective (RA/Dec → little video):** adequate. Fast and correct for the five targets; any other coordinates take minutes and the tool is local only. Raise: hosting, demo-mode safety, parallel downloads.
- **Barnard's Star:** strong. A clear motion pair; saturation is handled honestly. Raise: a caption explaining the circle's motion.
- **Epsilon Indi B:** adequate. Motion is visible, but there are fake spots (H1) and a release-boundary jump (H3). Raise: fix H1 and mark releases.
- **WISE 0855:** adequate. Faint but present; good CatWISE arrows; but the blended light curve and spectrum (H2). Raise: a prominent warning and a robust stack.
- **RW Aur:** strong. Real brightening, checked against field stars. Raise: say "verified against field stars" in the demo.
- **R Draconis:** weak. A saturated blob and one lower limit. Raise: narrate the ring changes in the difference video; download D1 for more visits.
- **1. Easy to update with new releases:** adequate–strong. Releases are found automatically, the best copy of each exposure wins, and there is a refresh button. Raise: show the release and "data as of" date on the video.
- **2. Bands, combined detectors, on-the-fly spectra:** strong. Detector sums, wavelength ranges, RGB, band difference, 102-channel spectra per visit. Raise: click a pixel to get its spectrum.
- **3. Add or subtract images over time:** strong in the API (deep, pair, difference series, minus-mean). The app only offers latest minus first. Raise: let the user pick the two visits.
- **4. User-chosen field of view:** adequate, 2–10′. Raise: not worth it now.
- **5. Overlays from Gaia DR3 / WISE:** strong. Moved to each visit's date, motion arrows with a significance cut, plus asteroids. Raise: Aladin, or hover labels.
- **6. Coordinates in the URL:** adequate, coded but unverified. Raise: test it and document an embed link.
- **7. Metadata such as contamination flags:** adequate–strong. Flags view, flags per measurement, visits table with releases. Raise: show a flag summary per video frame.
- **8. Astropy and Aladin:** Astropy strong, Aladin missing. Raise: an Aladin Lite panel.

Compared with WiseView, as far as I know it (not checked today):
- **WiseView has:** instant results for any position (precomputed tiles), about 10 years of epochs, interactive contrast and zoom, and well-known URL parameters.
- **We have:** spectra, light curves, a flags view, catalogue overlays with motion, RGB and band difference, minus-mean, a circle that follows the target's motion, and honest handling of saturation and neighbour stars.
- **We lack:** speed on new targets, a long baseline (3–6 visits over about 1.5 years), contrast controls, and public hosting.

NASA resources judges might notice are unused:
- **Aladin:** named explicitly in consideration 8 and absent from the code. Most noticeable gap.
- **CSA resources (NEOSSat, CADC):** unused. Probably few teams use them.
- **IRSA archive and Gaia DR3:** both used well.

## 6. READINESS

- **Data pipeline: 85%.** Every stage verified on real data for all five targets; stacking needs outlier rejection, and downloads run one at a time.
- **Science correctness: 65%.** Saturation and neighbour handling is honest, but fake spots from single frames, the WISE 0855 blend and the unmarked release jump can all be read as discoveries.
- **Web app: 50%.** Feature-complete in code, but uncommitted, never run here, missing a dependency, without demo protection, and not hosted.
- **Demo reliability: 55%.** About 85% once launched with `SPHEREX_DEMO=1` and clicked through once; the demo/ gallery is a solid fallback.
- **Documentation and presentation: 45%.** API.md, STATUS.md and index.html are good. README.md is stale (lesson TODOs, no run instructions, no demo mode), and I found no pitch material.

Three biggest risks to the demo:
1. **A click that starts downloads** (C1): RGB, every-visit spectrum or combined detectors on venue wifi.
2. **The untested app failing in front of judges** (C2).
3. **A judge reading an artefact as a result:** the red spots in Epsilon Indi B's difference video, WISE 0855's "doubling", or Epsilon Indi B's +10%.

## 7. PLAN

Demo-protecting fixes first, then new features:

1. **Commit the working tree on a branch:** 2 min, fix. Protects the player and app rewrite from being lost.
2. **Restore demo mode by default** (`?live=1` to allow downloads) and write down the launch command: 10 min, fix. Protects against C1.
3. **Install Streamlit, add it to requirements, click through 5 targets × 6 views** with demo mode on: 30 min, fix. Protects against C2; also checks URL parameters and the player.
4. **Sigma-clipped stacking** in stack_epoch, then re-check Epsilon Indi B and WISE 0855 and rebuild the demo/ backups: 30 min, fix. Removes the fake spots (H1).
5. **Warnings back on the page,** label format, tolerance message and cap: 10 min, fix. Covers H2, M2, M3.
6. **Release column and markers in light curves,** plus a note when releases are mixed: 20 min, fix. Covers H3.
7. **Accept "RA …, Dec …" and commas;** absolute cache paths: 15 min, fix. Covers M1, M5.
8. **Fix the light-curve x-axis to the mission span** and move spectrum legends off the data: 10 min, fix. Covers M4 and the legend overlap.
9. **README run instructions and a 3-minute demo script:** 20 min, presentation.
   - Script order: Barnard difference → RW Aur brightening → WISE 0855 overlay → spectrum.
   - Fall back to demo/index.html if anything misbehaves.
10. **Aladin Lite panel** (a new "sky" view with Gaia DR3 and WISE layers): 35 min, new feature. Ticks consideration 8. It needs the network, so hide it cleanly when offline.

If time remains after that: parallel downloads (45 min, medium risk), then hosting (60–120 min, high risk).

Leave alone:
- Don't run `prepare_demo --refresh` or `--all-frames` close to the demo.
- No new targets, and no field of view beyond 10′.
- Don't change the photometry method itself (aperture size, PSF fitting).
- Don't rewrite the cache in place (PSF stripping), refactor api.py or plots.py, or touch the lesson scripts.
- Skip CADC/NEOSSat.
- Leave the untracked Barnard coordinate table where it is; it's harmless.

I'm stopping here as asked. The helper scripts, logs and the contact sheet I made are in `/tmp/claude-1000/-home-utmost-Lab-PARAMOST-SPHEREX-spherex-project/51592b64-3e6a-4aa2-bf30-e30734026c32/scratchpad/`.
