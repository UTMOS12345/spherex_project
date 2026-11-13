# Demo results: what is ready, partial, possible, or not possible

Made by `make_gallery.py`. READY = made from every image; PARTIAL = made from the images in cache/ only; POSSIBLE = the images exist but are not downloaded; NOT POSSIBLE = cannot be measured (e.g. saturated). Open `index.html` to see them.

## Barnard's Star

| Product | Status | Notes |
|---|---|---|
| Video, D2 (`flipbook.gif`) | READY |  |
| Last minus first visit, D2 (`difference.png`) | READY |  |
| Gaia + WISE overlay (`overlay.png`) | READY |  |
| Light curve at 1.3 ± 0.02 µm (`lightcurve.png`) | NOT POSSIBLE | 'Barnard's Star' is saturated (too bright) in every SPHEREx image at 1.3 micron, so its brightness cannot be measured there. The pictures still show it. |
| Spectrum, latest visit (`spectrum.png`) | NOT POSSIBLE | No usable spectrum for 'Barnard's Star': it is saturated (too bright) in most images of that visit (1 of 102 channels usable). The pictures still show it. |
| Spectrum of every visit (`spectra_visits.png`) | NOT POSSIBLE | No usable spectrum for 'Barnard's Star': it is saturated (too bright) in most images of every visit. The pictures still show it. |
| All visits added, D2 (`deep.png`) | READY |  |
| Changes only: each visit minus the others, D2 (`minus_mean.gif`) | READY | The target is saturated: its core is filled in from the pixels around it, so its colour or brightness here is not a measurement. |
| Video, D5+D6 combined (3.8-5.0 µm) (`flipbook_D5+D6.gif`) | PARTIAL | Made from the 45 of 122 images in cache/; 77 more are at IRSA (python make_gallery.py --download). The target is saturated: its core is filled in from the pixels around it, so its colour or brightness here is not a measurement. |
| Video, all six detectors combined (`flipbook_all.gif`) | PARTIAL | Made from the 161 of 363 images in cache/; 202 more are at IRSA (python make_gallery.py --download). The target is saturated: its core is filled in from the pixels around it, so its colour or brightness here is not a measurement. |
| Colour difference: D6 minus scaled D2 (`band_difference.png`) | PARTIAL | Made from the 81 of 121 images in cache/; 40 more are at IRSA (python make_gallery.py --download). The target is saturated: its core is filled in from the pixels around it, so its colour or brightness here is not a measurement. |
| Colour picture: D6, D3, D1 as red, green, blue (`rgb.png`) | PARTIAL | Made from the 57 of 181 images in cache/; 124 more are at IRSA (python make_gallery.py --download). The target is saturated: its core is filled in from the pixels around it, so its colour or brightness here is not a measurement. |

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
| Light curve at 4.2 ± 0.02 µm (`lightcurve.png`) | READY |  |
| Spectrum, latest visit (`spectrum.png`) | READY |  |
| Spectrum of every visit (`spectra_visits.png`) | PARTIAL | Made from the 182 of 467 images in cache/; 285 more are at IRSA (python make_gallery.py --download). |
| All visits added, D5 (`deep.png`) | READY |  |
| Changes only: each visit minus the others, D5 (`minus_mean.gif`) | READY |  |
| Video, D5+D6 combined (3.8-5.0 µm) (`flipbook_D5+D6.gif`) | PARTIAL | Made from the 122 of 181 images in cache/; 59 more are at IRSA (python make_gallery.py --download). |
| Video, all six detectors combined (`flipbook_all.gif`) | PARTIAL | Made from the 182 of 467 images in cache/; 285 more are at IRSA (python make_gallery.py --download). |
| Colour difference: D6 minus scaled D2 (`band_difference.png`) | PARTIAL | Made from the 60 of 188 images in cache/; 128 more are at IRSA (python make_gallery.py --download). |
| Colour picture: D6, D3, D1 as red, green, blue (`rgb.png`) | POSSIBLE | 170 of 242 images it needs are at IRSA but not downloaded (about 26 min). Run: python make_gallery.py --download --only "Epsilon Indi B". Reason now: The D1 images of 'Epsilon Indi B' are not in the offline cache. Untick demo mode to download them (this takes minutes). |

## RW Aur

| Product | Status | Notes |
|---|---|---|
| Video, D1 (`flipbook.gif`) | READY |  |
| Last minus first visit, D1 (`difference.png`) | READY |  |
| Gaia + WISE overlay (`overlay.png`) | READY |  |
| Light curve at 0.9 ± 0.02 µm (`lightcurve.png`) | READY |  |
| Spectrum, latest visit (`spectrum.png`) | READY |  |
| Spectrum of every visit (`spectra_visits.png`) | PARTIAL | Made from the 148 of 336 images in cache/; 188 more are at IRSA (python make_gallery.py --download). |
| All visits added, D1 (`deep.png`) | READY |  |
| Changes only: each visit minus the others, D1 (`minus_mean.gif`) | READY |  |
| Video, D5+D6 combined (3.8-5.0 µm) (`flipbook_D5+D6.gif`) | PARTIAL | Made from the 37 of 112 images in cache/; 75 more are at IRSA (python make_gallery.py --download). |
| Video, all six detectors combined (`flipbook_all.gif`) | PARTIAL | Made from the 148 of 336 images in cache/; 188 more are at IRSA (python make_gallery.py --download). |
| Colour difference: D6 minus scaled D2 (`band_difference.png`) | PARTIAL | Made from the 37 of 112 images in cache/; 75 more are at IRSA (python make_gallery.py --download). |
| Colour picture: D6, D3, D1 as red, green, blue (`rgb.png`) | PARTIAL | Made from the 92 of 168 images in cache/; 76 more are at IRSA (python make_gallery.py --download). |

## R Draconis

| Product | Status | Notes |
|---|---|---|
| Video, D3 (`flipbook.gif`) | READY |  |
| Last minus first visit, D3 (`difference.png`) | READY |  |
| Gaia + WISE overlay (`overlay.png`) | READY |  |
| Light curve at 2.2 ± 0.02 µm (`lightcurve.png`) | NOT POSSIBLE | 'R Draconis' is saturated (too bright) in every SPHEREx image at 2.2 micron, so its brightness cannot be measured there. The pictures still show it. |
| Spectrum, latest visit (`spectrum.png`) | NOT POSSIBLE | No usable spectrum for 'R Draconis': it is saturated (too bright) in most images of that visit (0 of 102 channels usable). The pictures still show it. |
| Spectrum of every visit (`spectra_visits.png`) | NOT POSSIBLE | No usable spectrum for 'R Draconis' in any visit (saturated, or every measurement has flagged pixels). The pictures still show it. |
| All visits added, D3 (`deep.png`) | READY |  |
| Changes only: each visit minus the others, D3 (`minus_mean.gif`) | READY | The target is saturated: its core is filled in from the pixels around it, so its colour or brightness here is not a measurement. |
| Video, D5+D6 combined (3.8-5.0 µm) (`flipbook_D5+D6.gif`) | PARTIAL | Made from the 15 of 184 images in cache/; 169 more are at IRSA (python make_gallery.py --download). The target is saturated: its core is filled in from the pixels around it, so its colour or brightness here is not a measurement. |
| Video, all six detectors combined (`flipbook_all.gif`) | PARTIAL | Made from the 168 of 548 images in cache/; 380 more are at IRSA (python make_gallery.py --download). The target is saturated: its core is filled in from the pixels around it, so its colour or brightness here is not a measurement. |
| Colour difference: D6 minus scaled D2 (`band_difference.png`) | POSSIBLE | 168 of 183 images it needs are at IRSA but not downloaded (about 25 min). Run: python make_gallery.py --download --only "R Draconis". Reason now: The D6 images of 'R Draconis' are not in the offline cache. Untick demo mode to download them (this takes minutes). |
| Colour picture: D6, D3, D1 as red, green, blue (`rgb.png`) | POSSIBLE | 159 of 274 images it needs are at IRSA but not downloaded (about 24 min). Run: python make_gallery.py --download --only "R Draconis". Reason now: The D6 images of 'R Draconis' are not in the offline cache. Untick demo mode to download them (this takes minutes). |
