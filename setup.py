from setuptools import setup

with open("README.md", "r") as ifd:
    long_description = ifd.read()

setup(
    name="radiacode-tools",
    version="0.1.1",
    description="radiacode interface to the larger gamma spectrometry ecosystem",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Chris Kuethe",
    author_email="chris.kuethe@gmail.com",
    url="https://github.com/ckuethe/radiacode-tools",
    py_modules=["radqr", "n42convert"],
    # extras_require={ "dev": [ "pytest>=3.7", "twine", ] },
    install_requires=[
        "radiacode>=0.3.2",
        "flask",
        "numpy>=1.22.2",
        "tqdm",
        "qrcode",
        "requests",
        "xmlschema",
        "xmltodict",
        "defusedxml",
        "dateutils",
    ],
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "License :: OSI Approved :: MIT License",
        "Operating System :: POSIX",
        "Development Status :: 4 - Beta",
        "Topic :: Scientific/Engineering :: Physics",
        "Topic :: Utilities",
    ],
    package_dir={"": "src"},
)
