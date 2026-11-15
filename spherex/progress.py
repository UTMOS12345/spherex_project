"""Progress reporting for the slow api functions.

A progress callback is any callable progress(stage, done, total):
    stage  short plain text, one of STAGES ("downloading images", ...)
    done   items finished so far in this stage (0 when the stage starts)
    total  items in this stage
It is called at the start of each stage (done=0) and after each item. It is only ever called
from the thread doing the work, and an exception raised inside it is ignored: progress
reporting can never change or break a result.
"""

SEARCHING = "searching the archive"
DOWNLOADING = "downloading images"
CLEANING = "cleaning and aligning"
STACKING = "stacking visits"
MEASURING = "measuring"
DRAWING = "drawing"
STAGES = (SEARCHING, DOWNLOADING, CLEANING, STACKING, MEASURING, DRAWING)


def report(progress, stage, done, total):
    """Call progress(stage, done, total) if a callback was given; ignore anything it raises."""
    if progress is None:
        return
    try:
        progress(stage, int(done), int(total))
    except Exception:
        pass


def shifted(progress, stage, offset, grand_total):
    """A callback that forwards only `stage`, counted from `offset` out of `grand_total`.
    Lets a loop over parts (the visits of spectrum_figure(all_visits=True)) report one running
    count instead of restarting at 0 for every part; other stages are dropped."""
    if progress is None:
        return None

    def forward(s, done, total):
        if s == stage and done > 0:
            report(progress, stage, offset + done, grand_total)
    return forward
