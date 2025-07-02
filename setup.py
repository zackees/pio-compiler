"""
Setup file.
"""

import os
import re

from setuptools import setup

URL = "https://github.com/zackees/pio-compiler"
KEYWORDS = "platformio poi compile arduino esp32"
HERE = os.path.dirname(os.path.abspath(__file__))



if __name__ == "__main__":
    setup(
        maintainer="Zachary Vorhies",
        keywords=KEYWORDS,
        url=URL,
        package_data={"": ["assets/example.txt"]},
        include_package_data=True)

