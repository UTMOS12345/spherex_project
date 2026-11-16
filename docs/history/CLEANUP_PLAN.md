# Cleanup plan: production, 16 Nov 2026

Safety tag `before-cleanup-1116` = `cec8634` (production HEAD), pushed to origin.
Work happens in the worktree `spherex_project-grammar`, which already has `production` checked out
(git won't let the main worktree switch to it while that worktree holds it).

## 1. Branches

Every branch is already fully contained in production: `git log production..origin/<b>` is empty
for all of them, so there is nothing to merge and no merge test to run.

| branch | last commit (remote) | last author | ahead of production | group |
|---|---|---|---|---|
| main | 2026-11-15 11:22 | me | 0 (same commit as production) | keep (GitHub default branch) |
| production | 2026-11-15 11:22 | me | n/a | keep |
| molecule-bands-api | 2026-11-15 10:24 | me | 0 | a) merged, delete |
| fix-wavelength-reset | 2026-11-15 10:58 | me | 0 | a) merged, delete |
| grammar-sweep | 2026-11-15 10:23 | me | 0 | a) merged, delete |
| fix-asteroids | 2026-11-15 09:33 | me | 0 | a) merged, delete |
| progress | 2026-11-15 08:37 | me | 0 | a) merged, delete |
| hackathon | 2026-11-14 15:44 | me | 0 | a) merged, delete |
| demo-fixes | 2026-11-13 14:30 | me | 0 | a) merged, delete |
| frontend | 2026-11-15 10:57 | **teammate's** | 0 | **teammate's: keep, don't delete** (local copy is 5 commits behind origin; harmless) |

- b) unmerged useful work: **none**. Of the branches you named, `aladin`, `request-ack`,
  `crowd-ready`, `portfolio` and `local-app` don't exist locally or on origin. The Aladin work is
  already in production (`cec8634`).
- c) stale/experimental: none.
- Deleting `molecule-bands-api` locally means switching the main worktree off it first. I'll
  switch it to `main`.

## 2. Files on production

| category | files | action |
|---|---|---|
| core library | `spherex/` (19 modules) | unchanged |
| app | `app.py`, `.streamlit/config.toml` | stay at root |
| API docs | `API.md` | → `docs/API.md` |
| helper scripts | `prepare_demo.py`, `explore.py`, `make_gallery.py` | → `tools/` |
| warmup/precompute scripts | none exist (`prepare_demo.py` does that job) | n/a |
| lesson/test leftovers, temp files | **none on production** (`lesson*.py` only exist in old history) | n/a |
| review/report notes | `REPORT.md`, `REVIEW.md` (14 Nov assessments) | → `docs/history/` |
| server/deploy | `deploy/` (README, bootstrap.sh, deploy.sh, nginx-spherex.conf, spherex.env.example, spherex.service) | already in place, only fix paths |
| tests | `tests/test_cache_limit.py`, `tests/test_progress.py` (14 pass) | keep |
| dev config | `requirements-dev.txt` (adds pytest), `pyrightconfig.json` | keep at root |
| secrets | **none found** in tracked files or in history (scanned for passwords, keys, tokens, `.env`, `.pem`). Only `127.0.0.1` loopback addresses; `deploy/spherex.env.example` holds paths and limits, no credentials. | nothing to rotate |
| large files (> 5 MB) | **none**. Biggest tracked file is 748 KB. | n/a |
| tracked cache | `cache/frames/` (6 frame lists, 0.7 MB), `cache/gaia/` (11 cones, 1.1 MB), `cache/wise/` (6 cones, 2.4 MB). Committed on purpose in `82349b7`. `cache/cutouts/` (FITS) is already ignored. `demo/` and `out/` are not tracked. | **decision needed: see 4** |

Who imports what: `prepare_demo.py` does `import explore` (and fakes `sys.argv = ["explore.py", ...]`).
Nothing imports `make_gallery.py`. `spherex/api.py` mentions `prepare_demo.py` only in a comment.
All three scripts find `spherex` only because they sit next to it, so moving them needs a fix
(see 3).

## 3. Layout and moves (one commit)

```
spherex/            core library (unchanged)
app.py              Streamlit app (root; systemd unit runs `streamlit run app.py`)
.streamlit/         theme
tools/              prepare_demo.py, explore.py, make_gallery.py
deploy/             unchanged location
docs/API.md
docs/history/       REPORT.md, REVIEW.md, CLEANUP_PLAN.md (this file)
tests/              unchanged
README.md, requirements.txt, requirements-dev.txt, pyrightconfig.json, .gitignore
```

- No `examples/`: there are no lesson scripts worth keeping. No LICENSE in the repo (worth adding
  in the portfolio step).
- `git mv` the files. At the top of each tool, add a 2-line `sys.path` insert of the repo root so
  `python tools/prepare_demo.py` keeps working from the repo root. `import explore` keeps working
  because both files sit in `tools/`.
- Output folders stay `demo/` and `out/`, relative to the current folder. Commands are still run
  from the repo root, so nothing moves.
- Fix path references in: `README.md` (lines 12, 68-73, 95-101, 213-218), `API.md:404`,
  `deploy/README.md:42`, `deploy/bootstrap.sh:71`, `deploy/spherex.env.example:13`, the
  usage docstrings in the three tools, the `sys.argv[0]` string, and the comment at
  `spherex/api.py:53-54` (comment only, no code change).

## 4. .gitignore (one commit)

Add `.env`, `*.env` (keeping `!deploy/spherex.env.example`), `*.fits`, `*.fits.gz`,
`.streamlit/secrets.toml`, `venv/`, `env/`, `.DS_Store`, and ignore all of `cache/` except the
three small catalog folders.

**Decision for you:** `cache/frames|gaia|wise` (4.2 MB of ECSV). Two options:
- **Keep them tracked (my recommendation).** A fresh clone and the server get the IRSA frame lists
  and the Gaia/CatWISE cones, so demo mode can show the five targets' overlays without network.
  Also, `deploy.sh` runs `git reset --hard`, so untracking them would **delete them from the
  server's `/srv/spherex/cache` on the next deploy**. The server uses `SPHEREX_CACHE=/srv/spherex-cache`,
  so it's probably unaffected, but a fresh local or desktop-app install would lose them.
- Untrack them (`git rm --cached`, local copies stay). Then they'd have to ship with the cutouts
  bundle.

## 5. Requirements (one commit)

`requirements.txt` has every package except two that the code imports directly but only gets
through other packages: `scipy` (`spherex/clean.py`) and `pyerfa` (`spherex/__init__.py`).
Add `scipy==1.18.1` and `pyerfa==2.0.1.5`, which are the versions in the working venv. All other
pins already match the venv. Keep `requirements-dev.txt` (pytest) as the one extra file.

## 6. README (one commit)

Update paths and commands for `tools/` and `docs/` only.

## 7. Deletions

Nothing to `git rm` besides the moves above. There are no leftovers on production.

## Checks after Phase 2

- Fresh venv in the scratchpad: `pip install -r requirements.txt`, then `import spherex`.
  `tools/prepare_demo.py --help`, `tools/explore.py --help`, `tools/make_gallery.py --help`.
- AppTest in demo mode for the five targets. Today: all 5 pass, 0 exceptions, 0 errors.
- `pytest` (14 pass today).
- api.py outputs for WISE 0855 (`visits`, `light_curve`, `spectrum`, `molecule_bands`, `epochs`)
  compared, table by table, against a worktree at `before-cleanup-1116`.
- `git status` clean, no tracked file > 5 MB, secrets scan clean.

## Afterwards

- `git push origin production`. The server's 5-minute cron deploys it. The systemd unit and nginx
  are untouched.
- Delete local and remote: molecule-bands-api, fix-wavelength-reset, grammar-sweep,
  fix-asteroids, progress, hackathon, demo-fixes.
- Keep `main`. It's the GitHub default branch and is the same commit as production; I can
  fast-forward it to the new production if you want.
- Keep `frontend` (teammate's) and every tag.
- Tell the teammate: scripts moved to `tools/`, `API.md` moved to `docs/`.
