from setuptools import setup, Extension
import numpy

module = Extension(
    'app.analysis.maudlinlib',
    sources=['app/analysis/clustering_c.c'],
    include_dirs=[numpy.get_include()]
)

setup(
    name='maudlinlib',
    version='0.1',
    description='Maudlin C library',
    ext_modules=[module],
    packages=['app'],
    install_requires=[
        'numpy',  # Specify any dependencies here
    ],
    test_suite='tests',
    classifiers=[
        'Programming Language :: Python :: 3',
        'Programming Language :: C',
        'License :: OSI Approved :: MIT License',
    ],
)
