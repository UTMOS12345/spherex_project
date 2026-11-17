# Standing rules for this repo

These apply to every session. Don't wait to be told them again.

## Git
- Work on a branch off `main`, never on `main` directly.
- One commit per item of the task. Run the checks after each one.
- Never force-push. Never delete a branch you didn't create.
- Report before merging into `main`, unless the task explicitly says to merge.

## Layout
- `spherex/` is the library. It must never import from `paramost/`, `tools/` or `deploy/`.
- `paramost/` is the app (Streamlit). It talks to the library through `spherex/api.py`
  (documented in `docs/API.md`).
- `tools/` holds helper scripts. `deploy/` holds server setup.

## Correctness
- Scientific outputs (stacks, tables, photometry, spectra) must stay byte-identical unless the
  change is explicitly about changing them.
- For images, compare the pixel array before encoding, not the PNG or video bytes.
- If saved results change on purpose, raise `RESULTS_VERSION` in `spherex/results.py`.

## Checks that matter
- **pytest:** `.venv/bin/python -m pytest -q tests`. This needs the editable install
  (`uv pip install --python .venv/bin/python -e ".[test]"`); without it, imports fail.
- **The app in offline mode:** `SPHEREX_DEMO=1 .venv/bin/python -m paramost --port 8502 --no-browser`
  should serve HTTP 200. Use Streamlit's AppTest with `SPHEREX_DEMO=1` to drive the page.
- **Outputs against the pre-change tag:** compare with the `before-*` tag from before the change
  (`git tag`), using a cached target.

## Cache
- `cache/` is downloaded and regenerable. It is untracked and ignored.
- Never commit it, and never read, search or scan it (`.claude/settings.json` denies Read
  there, and that also covers Grep and Glob; with Bash, stay out of it yourself).
- Never download data just to make a check pass. Say the check was skipped and why.

## Honesty
- Don't claim a check passed unless you ran it and saw it pass. Report failures with their output.
- Don't cite a source, URL, ID or API you haven't verified.
