# SPHEREx Planet X tool: data side

Run everything from THIS folder (so `import spherex` and `cache/` work).

```
spherex_project/
├── spherex/              <- the library (your teammate imports from here)
│   ├── __init__.py       <- lists the public functions
│   ├── net.py            with_retries
│   ├── fitsio.py         L1  load_image, sky_to_pix, inside
│   ├── targets.py        L2  parse_target, resolve_name, at_time, years_since_j2000
│   ├── frames.py         L3  find_frames, load_or_find_frames
│   ├── download.py       L4  get_cutout, prefetch, check_cache (TODO: exercise)
│   ├── clean.py          L5  clean_frame, flag_bits, decode_flags
│   ├── epochs.py         L6  make_epochs, stack_epoch      (TODO)
│   ├── diff.py           L7  difference, make_gif          (TODO)
│   ├── gaia.py           L8  gaia_overlay                  (TODO)
│   ├── photometry.py     L9  light_curve                   (TODO)
│   └── spectrum.py       L10 spectrum                      (TODO)
├── show_target.py        L1-4 demo: PNGs of a target
├── lesson4_cache.py      L4 script + exercise
├── lesson5_clean.py      L5 script + exercise
├── requirements.txt
└── cache/                created automatically
    ├── frames/           saved search tables (.ecsv)
    └── cutouts/          downloaded FITS cutouts
```

Rules:
* Reusable functions go in `spherex/`. Lesson scripts only import and call them.
* New lesson N: write the TODO functions in `spherex/<module>.py`, add a `lessonN_*.py` script to test them.
* Teammate (Streamlit): `from spherex import parse_target, find_frames, get_cutout, clean_frame, ...`
  and ship the `cache/` folder for an offline demo.
