"""Lesson 1 - open a SPHEREx file, RA/Dec <-> pixel."""
from astropy.io import fits
from astropy.wcs import WCS


def load_image(path):
    """SPHEREx MEF path -> (image array, celestial WCS, IMAGE header)."""
    with fits.open(path) as h:
        hdr = h["IMAGE"].header
        img = h["IMAGE"].data.astype(float)
    return img, WCS(hdr), hdr


def sky_to_pix(wcs, coord):
    """SkyCoord -> (x, y) pixel, 0-based, fractional. Index arrays as img[y, x]."""
    x, y = wcs.world_to_pixel(coord)
    return float(x), float(y)


def inside(shape, x, y):
    """True if pixel (x, y) is on an image of this numpy shape (ny, nx)."""
    ny, nx = shape
    return 0 <= x < nx and 0 <= y < ny
