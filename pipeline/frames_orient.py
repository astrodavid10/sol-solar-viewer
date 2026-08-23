"""Per-frame solar orientation: L0/B0/P, Carrington rotation, basis matrices.

The field-line vertices are stored in the ROTATING Carrington frame, so
consecutive frames differ only by real magnetic evolution (that is what makes a
GPU lerp physical).  The ~2.36 deg of Carrington rotation between frames --
plus the Sun's axial tilt -- therefore has to be carried by a per-frame
orientation, which is what this module computes.

Convention (verified empirically, see ``_assert_conventions``):
    matrices are ROW-MAJOR and right-multiply COLUMN vectors:
        v_ecliptic_J2000 = M . v_carrington
Flattened row-major for JSON.  ``THREE.Matrix3.fromArray`` is column-major, so
the app must either transpose or use ``quat_carr_to_ecl`` (which is
orientation-only and unambiguous) -- the quaternion is the recommended path.

Every run re-derives the matrices from sunpy by transforming the identity basis
AND asserts them against the closed form ``M_hci . Rz(angle)``.  That
agreement (measured at 3e-16) is a free regression test: if a future sunpy
changes a frame definition, the run fails loudly instead of shipping a
subtly-rotated corona.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Dict, Optional

import numpy as np

from .config import SOLAR_AXIS_NODE_DEG, SOLAR_AXIS_TILT_DEG

_HEAVY = False
_u = None
_Time = None
_SkyCoord = None
_CartesianRepresentation = None
_HeliocentricMeanEcliptic = None
_HGC = None
_HGS = None
_HCI = None
_get_earth = None
_sun = None
_Rotation = None

_CACHE: Dict[str, dict] = {}
ASSERT_TOL = 1e-9


def _ensure_imports() -> None:
    global _HEAVY, _u, _Time, _SkyCoord, _CartesianRepresentation
    global _HeliocentricMeanEcliptic, _HGC, _HGS, _HCI, _get_earth, _sun
    global _Rotation
    if _HEAVY:
        return
    import astropy.units as u_
    from astropy.time import Time as Time_
    from astropy.coordinates import (SkyCoord as SkyCoord_,
                                     CartesianRepresentation as CR_,
                                     HeliocentricMeanEcliptic as HME_)
    import sunpy.coordinates                            # noqa: F401
    from sunpy.coordinates import (HeliographicCarrington as HGC_,
                                  HeliographicStonyhurst as HGS_,
                                  HeliocentricInertial as HCI_,
                                  get_earth as get_earth_, sun as sun_)
    from scipy.spatial.transform import Rotation as Rotation_
    _u, _Time, _SkyCoord, _CartesianRepresentation = u_, Time_, SkyCoord_, CR_
    _HeliocentricMeanEcliptic = HME_
    _HGC, _HGS, _HCI = HGC_, HGS_, HCI_
    _get_earth, _sun = get_earth_, sun_
    _Rotation = Rotation_
    _HEAVY = True


def rz(deg: float) -> np.ndarray:
    """Right-handed rotation about +Z, for column vectors."""
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


def _basis_matrix(frame, t) -> np.ndarray:
    """Matrix taking ``frame`` cartesian vectors to ecliptic J2000 cartesian.

    Built by transforming the three unit basis vectors and stacking their
    images as COLUMNS -- which is exactly the matrix M with v_ecl = M . v_frame.
    Derived rather than hand-written so it inherits sunpy's full frame
    definition (obliquity, node, light-travel Carrington correction).
    """
    eye = np.eye(3)
    c = _SkyCoord(_CartesianRepresentation(eye * _u.R_sun), frame=frame)
    out = c.transform_to(_HeliocentricMeanEcliptic(obstime=t, equinox="J2000"))
    return np.asarray(out.cartesian.xyz.to_value(_u.R_sun), dtype=float)


def _assert_conventions(mat_carr: np.ndarray, mat_heeq: np.ndarray,
                        mat_hci: np.ndarray, l0_deg: float,
                        hci_rot_deg: float, t) -> None:
    """Closed-form + column-vector-convention checks (both must hold)."""
    e_carr = float(np.abs(mat_carr - mat_hci @ rz(hci_rot_deg)).max())
    e_heeq = float(np.abs(mat_heeq - mat_hci @ rz(l0_deg + hci_rot_deg)).max())
    if e_carr > ASSERT_TOL or e_heeq > ASSERT_TOL:
        raise AssertionError(
            "frame closed-form check failed (carr {0:.3e}, heeq {1:.3e} > "
            "{2:.0e}); sunpy frame definitions may have changed"
            .format(e_carr, e_heeq, ASSERT_TOL))
    for m, name in ((mat_carr, "carr"), (mat_heeq, "heeq"), (mat_hci, "hci")):
        if abs(float(np.linalg.det(m)) - 1.0) > ASSERT_TOL:
            raise AssertionError("{0} matrix is not a proper rotation "
                                 "(det={1})".format(name, np.linalg.det(m)))
        if float(np.abs(m @ m.T - np.eye(3)).max()) > ASSERT_TOL:
            raise AssertionError("{0} matrix is not orthonormal".format(name))
    # Empirical column-vector check: one real point through both paths.
    tp = _SkyCoord(30.0 * _u.deg, 20.0 * _u.deg, 1.5 * _u.R_sun,
                   frame=_HGC(obstime=t, observer="earth"))
    v_carr = np.asarray(tp.cartesian.xyz.to_value(_u.R_sun), dtype=float)
    v_ecl = np.asarray(
        tp.transform_to(_HeliocentricMeanEcliptic(obstime=t, equinox="J2000")
                        ).cartesian.xyz.to_value(_u.R_sun), dtype=float)
    err = float(np.abs(mat_carr @ v_carr - v_ecl).max())
    if err > 1e-9:
        raise AssertionError(
            "column-vector convention check failed ({0:.3e} R_sun); the "
            "matrix is not v_ecl = M . v_carr".format(err))


def orient_for(mag_time: datetime) -> dict:
    """Orientation block for one magnetogram time.

    ``mag_time`` must be timezone-aware UTC.  Results are cached per second-
    resolution ISO string: consecutive slots often share a magnetogram, and each
    call costs a handful of sunpy transforms.
    """
    _ensure_imports()
    if mag_time.tzinfo is None:
        mag_time = mag_time.replace(tzinfo=timezone.utc)
    iso = mag_time.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if iso in _CACHE:
        return _CACHE[iso]

    t = _Time(iso.replace("Z", ""), scale="utc")
    l0_deg = float(_sun.L0(t).to_value(_u.deg))
    b0_deg = float(_sun.B0(t).to_value(_u.deg))
    p_deg = float(_sun.P(t).to_value(_u.deg))
    carrington_rotation = float(_sun.carrington_rotation_number(t))

    # HCI longitude of Earth minus Carrington L0 == the accumulated Carrington
    # rotation angle relative to the (inertial) HCI zero meridian.
    earth_hci = _get_earth(t).transform_to(_HCI(obstime=t))
    hci_rot_deg = float((earth_hci.lon.to_value(_u.deg) - l0_deg) % 360.0)

    # GONG is ground-based, so 'earth' is the right Carrington observer; the
    # difference from the map's exact observer is the Sun-observer light-travel
    # correction of two points 1 AU out, i.e. < 1e-5 deg.
    mat_carr = _basis_matrix(_HGC(obstime=t, observer="earth"), t)
    mat_heeq = _basis_matrix(_HGS(obstime=t), t)
    mat_hci = _basis_matrix(_HCI(obstime=t), t)
    _assert_conventions(mat_carr, mat_heeq, mat_hci, l0_deg, hci_rot_deg, t)

    quat = _Rotation.from_matrix(mat_carr).as_quat()      # (x, y, z, w)

    out = {
        "iso": iso,
        "unix": int(mag_time.astimezone(timezone.utc).timestamp()),
        "l0_deg": l0_deg,
        "b0_deg": b0_deg,
        "p_deg": p_deg,
        "carrington_rotation": carrington_rotation,
        "hci_rot_deg": hci_rot_deg,
        "quat_carr_to_ecl": [float(v) for v in quat],
        "mat3_carr_to_ecliptic_j2000": [float(v) for v in mat_carr.ravel()],
        "mat3_heeq_to_ecliptic_j2000": [float(v) for v in mat_heeq.ravel()],
        "mat3_hci_to_ecliptic_j2000": [float(v) for v in mat_hci.ravel()],
    }
    _CACHE[iso] = out
    return out


def constants_block(reference: Optional[dict] = None) -> dict:
    """The manifest's ``constants`` block.

    ``mat3_hci_to_ecliptic_j2000`` is constant to ~6e-8 over a year (HCI is
    inertial; the residual is the ecliptic-of-date vs J2000 difference in
    sunpy's definition), so one sample stands for the window.
    """
    ref = reference or orient_for(datetime.now(timezone.utc))
    return {
        "solar_axis_tilt_deg": SOLAR_AXIS_TILT_DEG,
        "solar_axis_node_deg": SOLAR_AXIS_NODE_DEG,
        "mat3_hci_to_ecliptic_j2000": ref["mat3_hci_to_ecliptic_j2000"],
        "note": ("All mat3 values are ROW-MAJOR and right-multiply COLUMN "
                 "vectors: v_ecliptic_j2000 = M . v_frame. THREE.Matrix3."
                 "fromArray() expects column-major, so transpose or (better) "
                 "use quat_carr_to_ecl, which is convention-free."),
    }
