# Contributing

Thanks for helping! Bug reports, ideas and pull requests are welcome. See
[ROADMAP.md](ROADMAP.md) for planned work.

## Setup

```
git clone https://github.com/UTMOS12345/spherex_project.git
cd spherex_project
python -m venv .venv
.venv/bin/pip install -e ".[test]"     # or: pip install -r requirements-dev.txt (exact versions)
.venv/bin/python -m paramost           # the app, with cache/ in the checkout
```

Python 3.10 or newer.

## Tests

```
pytest -q tests
```

The tests need no network and work in temporary folders, not in your cache. CI runs them on Python 3.11 and 3.12 for
every push and pull request (`.github/workflows/tests.yml`). If you change how an image,
table or figure is computed, show in the pull request that the outputs for a cached target
are unchanged, or explain why they change. If a change alters saved results, raise
`RESULTS_VERSION` in `spherex/results.py`.

## Layout rules

- **`spherex/` never imports from `paramost/` or `tools/`.** The library has to work on its
  own; the app and the scripts build on it, never the other way round.
- The app talks to the library only through `spherex/api.py`, documented in
  [docs/API.md](docs/API.md). New behaviour goes in as optional arguments, so existing calls
  give the same results.
- Don't commit downloaded data. `cache/` is ignored except the frame lists and catalogue cones
  of the five challenge targets.

## Pull requests

- One topic per pull request, with a short description of what changed and how you checked it.
- Keep the caveats honest: when a measurement can be misleading (saturation, neighbours, mixed
  releases), say so on the figure and in `table.meta["warning"]`.
