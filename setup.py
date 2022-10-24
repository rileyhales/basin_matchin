from setuptools import setup

with open("README.md", "r") as readme:
    long_description = readme.read()

AUTHOR = 'Riley C. Hales'
DESCRIPTION = 'The SABER tool for bias correcting large hydrologic models'

VERSION = '0.7.0'

PYTHON_REQUIRES = '>=3.10'
INSTALL_REQUIRES = [
    'contextily',
    'fastparquet',
    'geopandas',
    'hydrostats',
    'joblib',
    'kneed',
    'matplotlib',
    'natsort',
    'numba',
    'numpy',
    'pandas',
    'pyarrow',
    'requests',
    'scikit-learn',
    'scipy',
    'seaborn',
    'xarray',
    'zarr'
]

TROVE_CLASSIFIERS = [
    'Development Status :: 4 - Beta',
    'Programming Language :: Python :: 3',
    'Topic :: Scientific/Engineering',
    'Topic :: Scientific/Engineering :: Hydrology',
    'Topic :: Scientific/Engineering :: Visualization',
    'Topic :: Scientific/Engineering :: GIS',
    'Intended Audience :: Science/Research',
    'License :: OSI Approved :: BSD License',
    'Natural Language :: English',
]

setup(
    name='saber-hbc',
    packages=['saber', ],
    version=VERSION,
    description=DESCRIPTION,
    long_description=long_description,
    long_description_content_type="text/markdown",
    author=AUTHOR,
    license='BSD 3-Clause',
    classifiers=TROVE_CLASSIFIERS,
    python_requires=PYTHON_REQUIRES,
    install_requires=INSTALL_REQUIRES
)
