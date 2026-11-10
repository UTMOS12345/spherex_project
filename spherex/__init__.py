"""
spherex - data side of the Planet X / SPHEREx tool.

Your teammate's Streamlit app only needs:

    from spherex import (parse_target, at_time, find_frames, get_cutout, clean_frame,
                         make_epochs, difference, gaia_overlay, light_curve, spectrum)

Lesson -> module:
    1  FITS + WCS              -> fitsio.py
    2  SkyCoord / names / Time -> targets.py
    3  IRSA frame search       -> frames.py
    4  cutouts + disk cache    -> download.py
    5  ZODI + FLAGS cleaning   -> clean.py
    6  epochs + stacking       -> epochs.py      (TODO)
    7  differences + GIF       -> diff.py        (TODO)
    8  Gaia overlay            -> gaia.py        (TODO)
    9  light curves            -> photometry.py  (TODO)
    10 spectra                 -> spectrum.py    (TODO)
"""
import warnings

from astropy.wcs import FITSFixedWarning
from erfa import ErfaWarning

warnings.simplefilter("ignore", FITSFixedWarning)   # harmless header-fix notices
warnings.simplefilter("ignore", ErfaWarning)        # "distance overridden" in apply_space_motion

from .net import with_retries                                     # noqa: E402
from .fitsio import load_image, sky_to_pix, inside                # noqa: E402
from .targets import parse_target, resolve_name, at_time, has_pm, years_since_j2000  # noqa: E402
from .frames import spherex_collections, find_frames, load_or_find_frames  # noqa: E402
from .download import get_cutout, prefetch, check_cache, CACHE_DIR  # noqa: E402
from .clean import clean_frame, flag_bits, decode_flags, BAD_FLAGS  # noqa: E402
from .epochs import make_epochs, stack_epoch                      # noqa: E402
from .diff import difference, make_gif                            # noqa: E402
from .gaia import gaia_overlay                                    # noqa: E402
from .photometry import light_curve                               # noqa: E402
from .spectrum import spectrum                                    # noqa: E402
