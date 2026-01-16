#!/usr/bin/env python

from setuptools import find_packages, setup

import os
import subprocess
import time

version_file = 'basicsr/version.py'

def readme():
    with open('README.md', encoding='utf-8') as f:
        content = f.read()
    return content

def get_requirements(filename='requirements.txt'):
    here = os.path.dirname(os.path.realpath(__file__))
    with open(os.path.join(here, filename), 'r') as f:
        requires = [line.replace('\n', '') for line in f.readlines()]
    return requires

if __name__ == '__main__':
    # Force disable CUDA extensions for now to ensure successful install on Python 3.14
    # The user can re-enable later if they have the environment set up
    ext_modules = []
    setup_kwargs = dict()

    # Hardcoded version to bypass the broken dynamic version generation
    # which causes KeyError: '__version__' in newer tools
    VERSION = '1.4.2'

    # Manually write the version file so the package works after install
    with open(version_file, 'w') as f:
        f.write(f"__version__ = '{VERSION}'\n")
        f.write(f"__gitsha__ = 'unknown'\n")
        f.write(f"version_info = (1, 4, 2)\n")

    setup(
        name='basicsr',
        version=VERSION,
        description='Open Source Image and Video Super-Resolution Toolbox',
        long_description=readme(),
        long_description_content_type='text/markdown',
        author='Xintao Wang',
        author_email='xintao.wang@outlook.com',
        keywords='computer vision, restoration, super resolution',
        url='https://github.com/xinntao/BasicSR',
        include_package_data=True,
        packages=find_packages(exclude=('options', 'datasets', 'experiments', 'results', 'tb_logger', 'wandb')),
        classifiers=[
            'Development Status :: 4 - Beta',
            'License :: OSI Approved :: Apache Software License',
            'Operating System :: OS Independent',
            'Programming Language :: Python :: 3',
        ],
        license='Apache License 2.0',
        setup_requires=['cython', 'numpy'],
        install_requires=get_requirements(),
        ext_modules=ext_modules,
        zip_safe=False,
        **setup_kwargs)
