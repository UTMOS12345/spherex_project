# Demo results: what is ready, partial, possible, or not possible

Made by `make_gallery.py`. READY = made from every image; PARTIAL = made from the images in cache/ only (`--download` completes it); LOWER LIMITS = the star is saturated, so the brightnesses shown are lower limits. Open `index.html` to see them.

## Barnard's Star

| Product | Status | Notes |
|---|---|---|
| Video, D2 (`flipbook.gif`) | READY |  |
| Last minus first visit, D2 (`difference.png`) | READY |  |
| Gaia + WISE overlay (`overlay.png`) | READY |  |
| Light curve at 1.3 ± 0.02 µm (`lightcurve.png`) | LOWER LIMITS | The target is saturated (too bright for SPHEREx) here: triangles are lower limits from the unsaturated wings of the star; its true brightness is higher. These measurements come from different data releases (DR1, QR3). Their calibration can differ by several percent, so a step between releases is not necessarily a real change. |
| Spectrum, latest visit (`spectrum.png`) | LOWER LIMITS | The target is saturated (too bright for SPHEREx) here: triangles are lower limits from the unsaturated wings of the star; its true brightness is higher. |
| Spectrum of every visit (`spectra_visits.png`) | LOWER LIMITS | The target is saturated (too bright for SPHEREx) here: triangles are lower limits from the unsaturated wings of the star; its true brightness is higher. |
| All visits added, D2 (`deep.png`) | READY |  |
| Changes only: each visit minus the others, D2 (`minus_mean.gif`) | READY | The target is saturated: its core is filled in from the pixels around it, so its colour or brightness here is not a measurement. |
| Video, D5+D6 combined (3.8-5.0 µm) (`flipbook_D5+D6.gif`) | READY | The target is saturated: its core is filled in from the pixels around it, so its colour or brightness here is not a measurement. |
| Video, all six detectors combined (`flipbook_all.gif`) | PARTIAL | Made from the 360 of 363 images in cache/; the other 3 are at IRSA (python make_gallery.py --download --only "Barnard's Star").  The target is saturated: its core is filled in from the pixels around it, so its colour or brightness here is not a measurement. |
| Colour difference: D6 minus scaled D2 (`band_difference.png`) | READY | The target is saturated: its core is filled in from the pixels around it, so its colour or brightness here is not a measurement. |
| Colour picture: D6, D3, D1 as red, green, blue (`rgb.png`) | PARTIAL | Made from the 180 of 181 images in cache/; the other 1 are at IRSA (python make_gallery.py --download --only "Barnard's Star").  The target is saturated: its core is filled in from the pixels around it, so its colour or brightness here is not a measurement. |

## WISE 0855

| Product | Status | Notes |
|---|---|---|
| Video, D6 (`flipbook.gif`) | READY |  |
| Last minus first visit, D6 (`difference.png`) | READY |  |
| Gaia + WISE overlay (`overlay.png`) | READY |  |
| Light curve at 4.5 ± 0.02 µm (`lightcurve.png`) | READY | 1 Gaia star(s) inside the 12″ measuring circle (G=16.3 at 6.0″): part of the light measured comes from them, mostly at short wavelengths. Treat these brightnesses as upper limits. |
| Spectrum, latest visit (`spectrum.png`) | READY | 1 Gaia star(s) inside the 12″ measuring circle (G=16.3 at 4.4″): part of the light measured comes from them, mostly at short wavelengths. Treat these brightnesses as upper limits. |
| Spectrum of every visit (`spectra_visits.png`) | READY | 1 Gaia star(s) inside the 12″ measuring circle (G=16.3 at 7.5″): part of the light measured comes from them, mostly at short wavelengths. Treat these brightnesses as upper limits. |
| All visits added, D6 (`deep.png`) | READY |  |
| Changes only: each visit minus the others, D6 (`minus_mean.gif`) | READY |  |
| Video, D5+D6 combined (3.8-5.0 µm) (`flipbook_D5+D6.gif`) | READY |  |
| Video, all six detectors combined (`flipbook_all.gif`) | READY |  |
| Colour difference: D6 minus scaled D2 (`band_difference.png`) | READY |  |
| Colour picture: D6, D3, D1 as red, green, blue (`rgb.png`) | READY |  |

## Epsilon Indi B

| Product | Status | Notes |
|---|---|---|
| Video, D5 (`flipbook.gif`) | READY |  |
| Last minus first visit, D5 (`difference.png`) | READY |  |
| Gaia + WISE overlay (`overlay.png`) | READY |  |
| Light curve at 4.2 ± 0.02 µm (`lightcurve.png`) | READY | These measurements come from different data releases (DR1, QR3). Their calibration can differ by several percent, so a step between releases is not necessarily a real change. |
| Spectrum, latest visit (`spectrum.png`) | READY |  |
| Spectrum of every visit (`spectra_visits.png`) | PARTIAL | Made from the 194 of 467 images in cache/; the other 273 are at IRSA (python make_gallery.py --download --only "Epsilon Indi B"). |
| All visits added, D5 (`deep.png`) | READY |  |
| Changes only: each visit minus the others, D5 (`minus_mean.gif`) | READY |  |
| Video, D5+D6 combined (3.8-5.0 µm) (`flipbook_D5+D6.gif`) | PARTIAL | Made from the 126 of 181 images in cache/; the other 55 are at IRSA (python make_gallery.py --download --only "Epsilon Indi B"). |
| Video, all six detectors combined (`flipbook_all.gif`) | PARTIAL | Made from the 194 of 467 images in cache/; the other 273 are at IRSA (python make_gallery.py --download --only "Epsilon Indi B"). |
| Colour difference: D6 minus scaled D2 (`band_difference.png`) | PARTIAL | Made from the 64 of 188 images in cache/; the other 124 are at IRSA (python make_gallery.py --download --only "Epsilon Indi B"). |
| Colour picture: D6, D3, D1 as red, green, blue (`rgb.png`) | PARTIAL | Made from the 84 of 242 images in cache/; the other 158 are at IRSA (python make_gallery.py --download --only "Epsilon Indi B"). |

## RW Aur

| Product | Status | Notes |
|---|---|---|
| Video, D1 (`flipbook.gif`) | READY |  |
| Last minus first visit, D1 (`difference.png`) | READY |  |
| Gaia + WISE overlay (`overlay.png`) | READY |  |
| Light curve at 0.9 ± 0.02 µm (`lightcurve.png`) | READY | These measurements come from different data releases (DR1, QR3). Their calibration can differ by several percent, so a step between releases is not necessarily a real change. |
| Spectrum, latest visit (`spectrum.png`) | READY |  |
| Spectrum of every visit (`spectra_visits.png`) | PARTIAL | Made from the 148 of 336 images in cache/; the other 188 are at IRSA (python make_gallery.py --download --only "RW Aur"). |
| All visits added, D1 (`deep.png`) | READY |  |
| Changes only: each visit minus the others, D1 (`minus_mean.gif`) | READY |  |
| Video, D5+D6 combined (3.8-5.0 µm) (`flipbook_D5+D6.gif`) | PARTIAL | Made from the 37 of 112 images in cache/; the other 75 are at IRSA (python make_gallery.py --download --only "RW Aur"). |
| Video, all six detectors combined (`flipbook_all.gif`) | PARTIAL | Made from the 148 of 336 images in cache/; the other 188 are at IRSA (python make_gallery.py --download --only "RW Aur"). |
| Colour difference: D6 minus scaled D2 (`band_difference.png`) | PARTIAL | Made from the 37 of 112 images in cache/; the other 75 are at IRSA (python make_gallery.py --download --only "RW Aur"). |
| Colour picture: D6, D3, D1 as red, green, blue (`rgb.png`) | PARTIAL | Made from the 92 of 168 images in cache/; the other 76 are at IRSA (python make_gallery.py --download --only "RW Aur"). |

## R Draconis

| Product | Status | Notes |
|---|---|---|
| Video, D3 (`flipbook.gif`) | READY |  |
| Last minus first visit, D3 (`difference.png`) | READY |  |
| Gaia + WISE overlay (`overlay.png`) | READY |  |
| Light curve at 2.2 ± 0.02 µm (`lightcurve.png`) | LOWER LIMITS | The target is saturated (too bright for SPHEREx) here: triangles are lower limits from the unsaturated wings of the star; its true brightness is higher. |
| Spectrum, latest visit (`spectrum.png`) | LOWER LIMITS | The target is saturated (too bright for SPHEREx) here: triangles are lower limits from the unsaturated wings of the star; its true brightness is higher. |
| Spectrum of every visit (`spectra_visits.png`) | LOWER LIMITS | The target is saturated (too bright for SPHEREx) here: triangles are lower limits from the unsaturated wings of the star; its true brightness is higher. |
| All visits added, D3 (`deep.png`) | READY |  |
| Changes only: each visit minus the others, D3 (`minus_mean.gif`) | READY | The target is saturated: its core is filled in from the pixels around it, so its colour or brightness here is not a measurement. |
| Video, D5+D6 combined (3.8-5.0 µm) (`flipbook_D5+D6.gif`) | PARTIAL | Made from the 31 of 184 images in cache/; the other 153 are at IRSA (python make_gallery.py --download --only "R Draconis").  The target is saturated: its core is filled in from the pixels around it, so its colour or brightness here is not a measurement. |
| Video, all six detectors combined (`flipbook_all.gif`) | PARTIAL | Made from the 196 of 548 images in cache/; the other 352 are at IRSA (python make_gallery.py --download --only "R Draconis").  The target is saturated: its core is filled in from the pixels around it, so its colour or brightness here is not a measurement. |
| Colour difference: D6 minus scaled D2 (`band_difference.png`) | PARTIAL | Made from the 35 of 183 images in cache/; the other 148 are at IRSA (python make_gallery.py --download --only "R Draconis").  The target is saturated: its core is filled in from the pixels around it, so its colour or brightness here is not a measurement. |
| Colour picture: D6, D3, D1 as red, green, blue (`rgb.png`) | PARTIAL | Made from the 139 of 274 images in cache/; the other 135 are at IRSA (python make_gallery.py --download --only "R Draconis").  The target is saturated: its core is filled in from the pixels around it, so its colour or brightness here is not a measurement. |
