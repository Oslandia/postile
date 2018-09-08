import os
import re
import io
from setuptools import setup, find_packages

here = os.path.abspath(os.path.dirname(__file__))

requirements = (
    'cython',
    'mercantile',
    'sanic==0.8.1',
    'sanic-cors==0.9.5',
    'pyyaml',
    'asyncpg>=0.15.0',
)


def find_version(*file_paths):
    """
    see https://github.com/pypa/sampleproject/blob/master/setup.py
    """
    with io.open(os.path.join(here, *file_paths), 'r') as f:
        version_file = f.read()

    # The version line must have the form
    # __version__ = 'ver'
    version_match = re.search(r"^__version__ = ['\"]([^'\"]*)['\"]",
                              version_file, re.M)
    if version_match:
        return version_match.group(1)
    raise RuntimeError("Unable to find version string. "
                       "Should be at the first line of __init__.py.")


setup(
    name='Postile',
    version=find_version('postile', '__init__.py'),
    description="Fast Vector Tile Server",
    url='https://github.com/ldgeo/postile',
    author='ldgeo',
    author_email='contact@oslandia.com',
    license='BSD-3',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Programming Language :: Python :: 3.6',
    ],
    packages=find_packages(),
    install_requires=requirements,
    include_package_data=True,
    entry_points={
        'console_scripts': [
            'postile=postile.postile:main',
        ],
    },
)
