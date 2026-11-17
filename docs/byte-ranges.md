# Reading only part of a SPHEREx file (HTTP byte ranges): what was tested

Checked on 17 Nov 2026 against IRSA, so that nobody has to repeat it blindly. Nothing here is
used by the code. Downloads still go through IRSA's cutout service (`spherex/download.py`).

## Why look at it at all

A cutout from IRSA's cutout service is **4.37 MB**, and we keep **0.41 MB** of it. The service
always includes the PSF cube (`EPSF`, ~4 MB), which is dropped after download (`DROP_LAYERS`).
The service takes only `center=` and `size=`, so it cannot leave the PSF out.
The full-frame files themselves are served directly, so the idea was to read only the
needed rows of each layer.

## What the archive supports

| Test | Result |
|---|---|
| `HEAD` on a full-frame file (`.../level2_..._spx_l2b-v27-....fits`) | 200, `Accept-Ranges: bytes`, 64.9-65.8 MB |
| `HEAD` on the cutout URL (`...fits?center=..&size=..`) | 405, only `GET` allowed |
| One range, `Range: bytes=0-2879` | 206 with exactly those bytes |
| Several ranges in one request | 206 `multipart/byteranges`, up to **100 ranges** |
| **101 or more ranges** | **200 with the whole file (65.8 MB)**: nginx ignores the Range header. A reader must never send more than 100 ranges, and must check for 206 before reading the body. |

## Layout of a full-frame file (DR1, pipeline v27)

| HDU | Kind | Size | Notes |
|---|---|---|---|
| PRIMARY | header only | | |
| IMAGE | float32 2040×2040, **uncompressed** | 16.65 MB | any rectangle can be read row by row |
| FLAGS | **tile-compressed**, one tile per image row | 11.82 MB | a cutout needs the whole compressed rows (~5.8 kB each) |
| VARIANCE | float32 2040×2040, uncompressed | 16.65 MB | |
| ZODI | float32 2040×2040, uncompressed | 16.65 MB | |
| EPSF | binary table | 3.95 MB | the PSF we drop |
| WCS-WAVE | small table | < 10 kB | |

Walking every header with ranged requests took 26 requests and 75 kB.

## The pixels: IRSA's cutout is a plain sub-array

The full file was read with `fits.open(url, use_fsspec=True)` and `.section[y0:y0+146, x0:x0+146]`
on IMAGE, VARIANCE, ZODI and FLAGS. All four are **byte-identical** to IRSA's 146×146 cutout of
the same frame and centre. IRSA's cutout is a sub-array, and its header shifts
`CRPIX1/2` (1020.5 → 731.5, 934.5, i.e. x0=289, y0=86) and the alternate WCSs
`CRPIX1A/2A`, `CRPIX1W/2W`.

## Speed: the fsspec route as such is a dead end

| Method, one 146×146 cutout | Time | Received |
|---|---|---|
| IRSA cutout service (what we use) | 0.9 s per image (6-11 at once, healthy archive); 3.4 s while it was busy | 4.37 MB |
| `fits.open(url, use_fsspec=True)` + `.section`, fsspec block size 5 MB | 32.9 s | ~22 MB |
| same, block size 64 kB | 28.3 s | ~5.3 MB |
| hand-made multi-range request, 16 IMAGE rows | 0.35 s | 11 kB |

Astropy reads a section one row at a time. Over HTTP that is hundreds of sequential small
requests, and with big blocks it fetches far more than needed. It is slower **and** larger
than the cutout service.

## What could work, and why it was not built

A custom reader could fetch the 146 rows of each uncompressed layer in two multi-range requests
(at most 100 ranges each). FLAGS would take its row-tile table plus two requests for the
compressed rows, and the headers a few more. That is about **12 requests and ~1.2 MB** (IMAGE,
VARIANCE and ZODI 85 kB each, FLAGS ~850 kB, headers ~75 kB). The cutout service needs 1 request
and 4.37 MB. Against that:

- FLAGS rows have to be decompressed by hand (tile-compressed binary table).
- The cutout header has to be rebuilt exactly as IRSA builds it (CRPIX and the A/W alternate
  WCSs). The pixel bounds must also be exactly IRSA's for a given centre and size. The sky
  level (median over the cutout) and the hole filling use the whole cutout, so different bounds
  would change the stacks, and new downloads would no longer match the files already in
  people's caches.
- Whether ~12 requests of 0.35-0.8 s each beat one 1-3 s request depends on IRSA's latency
  that day. It saves bandwidth (3.6× less) more surely than time.

Worth revisiting only if bandwidth becomes the limit (for example a metered server), or if
IRSA's cutout service gains an option to leave out the PSF. The 100-range cap and the
whole-file answer above it are the trap to remember.
