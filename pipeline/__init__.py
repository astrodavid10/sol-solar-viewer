"""Sol data pipeline.

Generates the static data products consumed by the Sol web app:
PFSS field-line frames (quantized binary), spacecraft ephemerides, active
region tables, a solar-activity digest, and the AIA 171 Carrington sphere
texture.

Everything here is deliberately dependency-light and offline-friendly:
stdlib HTTP, numpy/astropy/sunpy for the physics, no web framework.
"""

from .config import PIPELINE_VERSION

__all__ = ["PIPELINE_VERSION"]
