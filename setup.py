import setuptools

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setuptools.setup(
    name="ref-fetch",
    version="0.1.2",
    author="roobert",
    author_email="roobert@gmail.com",
    description="A tool to fetch, cache, and copy specific versions of libraries into repositories to provide code references and documentation to LLMs.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/roobert/ref-fetch",
    py_modules=["ref_fetch"],
    license="MIT",
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.6',
    install_requires=[
        "PyYAML",
        "requests",
        "ddgs",
        "tomli",
        "beautifulsoup4",
    ],
    entry_points={
        "console_scripts": [
            "ref-fetch=ref_fetch:main",
        ],
    },
)