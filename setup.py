from setuptools import setup, find_packages
from codecs import open
from os import path


here = path.abspath(path.dirname(__file__))

with open(path.join(here, 'requirements.txt'), encoding='utf-8') as f:
    all_reqs = f.read().split('\n')

install_requires = [x.strip() for x in all_reqs if 'git+' not in x]
dependency_links = [x.strip().replace('git+', '') for x in all_reqs if x.startswith('git+')]

setup(
    name="symmetrize",
    version="0.1.0",
    url="https://github.com/RealPolitiX/symmetrize",

    author="R. Patrick Xian",
    author_email="xrpatrick@gmail.com",

    description="Symmetrization and centering of 2D pattern using nonrigid point set registration",
    setup_requires=['setuptools-markdown'],
    long_description_markdown_filename='README.md',

    packages=find_packages(exclude=['docs', 'tests*']),
    install_requires=install_requires,
    dependency_links=dependency_links,

    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
    ],
)
