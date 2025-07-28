import setuptools

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setuptools.setup(
    name="ref-fetch",
    version="0.1.3",
    author="roobert",
    author_email="roobert@gmail.com",
    description="Automates fetching and caching of documentation and source code for specified versions of core standard libraries and third-party packages. It intelligently locates repositories, resolves dependencies, and provides a local, version-controlled reference of your project's entire dependency tree for LLM-assisted development.",
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