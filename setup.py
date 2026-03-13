import sys
from setuptools import setup

if sys.version_info < (3, 10):
    raise RuntimeError(
        f"Python {sys.version_info} is unsupported. Requires 3.10+."
    )

setup()
