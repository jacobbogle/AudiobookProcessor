from setuptools import setup, find_packages

try:
    with open("README.md", "r", encoding="utf-8") as fh:
        long_description = fh.read()
except FileNotFoundError:
    long_description = "Audiobook processing utility"

setup(
    name="audiobook-p",
    version="1.0.0",
    author="bogle",
    description="Audiobook processing utility",
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=["audiobook_p"],
    package_dir={"audiobook_p": "."},
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.9",
    install_requires=[
        "mutagen",
        "ffmpeg-python",
    ],
    entry_points={
        "console_scripts": [
            "audiobook-p=audiobook_p.main:cli",
        ],
    },
)