"""Worker processes for the per-frame work: cleaning and reprojecting frames, drawing pictures.

SPHEREX_WORKERS (read at call time): how many processes; default min(os.cpu_count(), 8);
1 = everything in the calling process, as before. Results and their order do not depend on it.

The pool uses the "spawn" start method on every platform (the default on macOS and Windows):
each worker starts a fresh Python and imports spherex, so nothing depends on fork copying the
parent's memory, threads or locks (Streamlit runs scripts on threads). The pool is created on
first use, kept for further calls (starting workers costs ~1-2 s of imports), and shut down
after IDLE_S seconds without work, so an idle app does not hold the workers' memory (~130 MB
each). Starting the workers costs ~1.5 s, so a new pool is only started for MIN_TASKS_NEW_POOL
tasks or more; the app starts it in advance (prestart) when a target is shown.

Spawn normally re-runs the parent's main script in every worker (hence the
`if __name__ == "__main__":` rule). Our task functions live in spherex modules, never in
__main__, so this pool's workers are started without it: a script or notebook without that
guard works, and nothing of the caller (a Streamlit script, a notebook) runs again in a
worker. Only processes this module starts are affected.

Tasks carry file paths and plain parameters, never big arrays or WCS objects. If the pool
cannot start or breaks (a worker killed, a platform without process support), the work is
done in the calling process instead, and that is logged once per process.
"""
import atexit
import logging
import multiprocessing
import os
import threading
from concurrent.futures import ProcessPoolExecutor, as_completed

log = logging.getLogger("spherex.workers")

DEFAULT_MAX = 8
IDLE_S = 600            # shut the pool down after this long without work
MIN_TASKS = 4           # a running pool is used for this many tasks or more
MIN_TASKS_NEW_POOL = 32 # starting a pool costs ~1.5 s of imports (~50 frames of work in one
                        # process), so a pool is only started for this many tasks or more

_lock = threading.RLock()
_pool = None
_pool_n = 0
_timer = None
_active = 0             # run() calls using the pool right now (several app sessions may)
_failed = False         # the pool failed once in this process: stay serial, don't retry
_warned = False


def n_workers():
    """SPHEREX_WORKERS, default min(os.cpu_count(), 8), at least 1."""
    v = os.environ.get("SPHEREX_WORKERS")
    if v:
        try:
            return max(1, int(v))
        except ValueError:
            pass
    return max(1, min(os.cpu_count() or 1, DEFAULT_MAX))


_launch = threading.local()     # .ours = True while this module's pool starts processes


def _install_spawn_patch():
    """Leave the parent's __main__ out of the preparation data of the processes WE start (see
    the module docstring). multiprocessing starts spawn workers inside submit(), on the
    calling thread, so a thread-local flag around our submits marks exactly ours."""
    from multiprocessing import spawn
    if getattr(spawn.get_preparation_data, "_spherex", False):
        return
    original = spawn.get_preparation_data

    def get_preparation_data(name):
        d = original(name)
        if getattr(_launch, "ours", False):
            d.pop("init_main_from_name", None)
            d.pop("init_main_from_path", None)
        return d
    get_preparation_data._spherex = True
    spawn.get_preparation_data = get_preparation_data


class _ours:
    def __enter__(self):
        _install_spawn_patch()
        _launch.ours = True

    def __exit__(self, *exc):
        _launch.ours = False
        return False


def _init_worker():
    import matplotlib
    matplotlib.use("Agg")
    import spherex  # noqa: F401  (quiet astropy logging, as in the parent)


def _get_pool(n):
    global _pool, _pool_n
    with _lock:
        if _pool is not None and _pool_n != n and _active == 0:
            _shutdown()
        if _pool is None:
            ctx = multiprocessing.get_context("spawn")
            _pool = ProcessPoolExecutor(max_workers=n, mp_context=ctx, initializer=_init_worker)
            _pool_n = n
        _cancel_timer()
        return _pool


def _cancel_timer():
    global _timer
    if _timer is not None:
        _timer.cancel()
        _timer = None


def _arm_timer():
    global _timer
    with _lock:
        _cancel_timer()
        _timer = threading.Timer(IDLE_S, _idle_shutdown)
        _timer.daemon = True
        _timer.start()


def _idle_shutdown():
    with _lock:
        if _active == 0:
            _shutdown()


def _shutdown():
    global _pool, _pool_n
    with _lock:
        _cancel_timer()
        if _pool is not None:
            _pool.shutdown(wait=False, cancel_futures=True)
        _pool, _pool_n = None, 0


atexit.register(_shutdown)


def _note_failure(err):
    global _failed, _warned
    _failed = True
    _shutdown()
    if not _warned:
        _warned = True
        msg = f"spherex: worker processes unavailable ({type(err).__name__}: {err}); working in one process"
        log.warning(msg)
        print(msg, flush=True)


def running():
    """True when the worker processes are up (started by an earlier run or prestart)."""
    return _pool is not None and not _failed


def run(fn, tasks, on_done=None, workers=None, min_tasks=None, start=True):
    """[fn(*t) for t in tasks], in task order, using worker processes when worthwhile.
    fn must be a module-level function (spawn imports it by name); tasks are tuples of small
    picklable values. on_done(i) runs in the calling thread as task i finishes (progress).
    An exception raised by fn itself is raised here, as it would be serially.
    min_tasks: fewest tasks worth a running pool (default MIN_TASKS). start=False: use the
    pool only if it is already running, never start one for this call."""
    global _active
    tasks = list(tasks)
    n = n_workers() if workers is None else max(1, int(workers))
    out = [None] * len(tasks)
    done = [False] * len(tasks)
    least = MIN_TASKS if min_tasks is None else min_tasks
    if _pool is None:
        least = float("inf") if not start else max(least, MIN_TASKS_NEW_POOL)
    enough = len(tasks) >= least
    if n > 1 and enough and not _failed:
        with _lock:
            _active += 1
        try:
            pool = _get_pool(n)
            with _ours():                 # submit() starts the worker processes
                futures = {pool.submit(_call, fn, t): i for i, t in enumerate(tasks)}
            try:
                for fut in as_completed(futures):
                    i = futures[fut]
                    status, value = fut.result()
                    if status == "error":   # the task itself failed: the same error as serially
                        raise _TaskFailed() from value
                    out[i] = value
                    done[i] = True
                    if on_done is not None:
                        try:
                            on_done(i)
                        except Exception as cb:   # the caller's progress callback: not the pool
                            raise _TaskFailed() from cb
            finally:
                for fut in futures:
                    fut.cancel()
            return out
        except _TaskFailed as e:
            raise e.__cause__
        except Exception as e:            # the pool itself: cannot start, a worker died, ...
            _note_failure(e)
        finally:
            with _lock:
                _active -= 1
            if not _failed:
                _arm_timer()
    for i, t in enumerate(tasks):         # serial, or the rest after a pool failure
        if not done[i]:
            out[i] = fn(*t)
            if on_done is not None:
                on_done(i)
    return out


class _TaskFailed(Exception):
    """Carries an exception raised by a task out of run()'s pool handling."""


def _call(fn, args):
    """Runs in a worker: fn(*args) -> ("ok", result) or ("error", the exception), so an error
    of the task is told apart from a failure of the pool."""
    try:
        return "ok", fn(*args)
    except Exception as e:
        return "error", e


def prestart(workers=None):
    """Start the worker processes now (in the background), so the first cold build does not
    wait for their imports. Does nothing with SPHEREX_WORKERS=1."""
    n = n_workers() if workers is None else workers
    if n <= 1 or _failed:
        return
    try:
        pool = _get_pool(n)
        with _ours():
            for _ in range(n):
                pool.submit(_noop)
        _arm_timer()
    except Exception as e:
        _note_failure(e)


def _noop():
    return None
