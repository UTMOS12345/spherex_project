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
    6  epochs + stacking       -> epochs.py
    7  differences + GIF       -> diff.py
    8  Gaia overlay            -> gaia.py
    9  light curves            -> photometry.py
    10 spectra                 -> spectrum.py
"""
import warnings

from astropy.wcs import FITSFixedWarning
from erfa import ErfaWarning

warnings.simplefilter("ignore", FITSFixedWarning)   # harmless header-fix notices
warnings.simplefilter("ignore", ErfaWarning)        # "distance overridden" in apply_space_motion

from astropy import log as _astropy_log                           # noqa: E402
_astropy_log.setLevel("WARNING")    # hide the harmless "Inconsistent SIP" INFO printed per frame

from .net import with_retries                                     # noqa: E402
from .fitsio import load_image, sky_to_pix, inside                # noqa: E402
from .targets import parse_target, resolve_name, at_time, has_pm, years_since_j2000  # noqa: E402
from .frames import spherex_collections, find_frames, load_or_find_frames  # noqa: E402
from .download import get_cutout, prefetch, check_cache, CACHE_DIR  # noqa: E402
from .clean import clean_frame, flag_bits, decode_flags, saturated_mask, BAD_FLAGS, SATURATION_FLAGS, DEFAULT_BITS  # noqa: E402
from .epochs import assign_epochs, make_grid, stack_epoch, make_epochs, parse_detectors   # noqa: E402
from .diff import difference, make_gif, shared_norm                            # noqa: E402
from .gaia import gaia_stars, gaia_overlay, draw_gaia
from .wise import wise_stars, wise_overlay                                    # noqa: E402
from .photometry import light_curve, measure_frame, wavelength_at                               # noqa: E402
from .plots import plot_light_curve, plot_light_curve_simple, plot_spectrum, plot_spectra_visits, set_style                               # noqa: E402
from .combine import deep_image, minus_mean, difference_series, band_difference, rgb_image  # noqa: E402
from .asteroids import known_asteroids, draw_asteroids                                   # noqa: E402
from .spectrum import spectrum, bin_to_channels, epoch_frames, channel_edges                                    # noqa: E402
from . import api                                                  # noqa: E402
from .api import molecule_bands                                    # noqa: E402
