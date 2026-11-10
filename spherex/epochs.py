"""Lesson 6 - group frames into survey visits (epochs) and stack each onto one grid.  TODO"""


def make_epochs(frames, gap_days=30):
    """Frames table -> list of epochs, one per survey visit, split per detector.
    A new epoch starts when the time gap between frames exceeds gap_days."""
    raise NotImplementedError("Lesson 6")


def stack_epoch(paths, target_wcs, shape):
    """Several cleaned frames of one epoch -> one image on a common grid (reproject + nanmean)."""
    raise NotImplementedError("Lesson 6")
