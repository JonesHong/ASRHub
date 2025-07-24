"""ASR Hub - A unified speech recognition middleware system."""

from setuptools import setup, find_packages
import os

# Read README for long description
with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

# Read requirements
with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = [line.strip() for line in fh if line.strip() and not line.startswith("#")]

setup(
    name="asr-hub",
    version="0.1.0",
    author="ASR Hub Team",
    author_email="team@asrhub.io",
    description="A unified speech recognition middleware system integrating multiple ASR providers",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/asrhub/asr-hub",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Multimedia :: Sound/Audio :: Speech",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.8",
    install_requires=requirements,
    extras_require={
        "dev": [
            "pytest>=7.4.0",
            "pytest-cov>=4.1.0",
            "pytest-asyncio>=0.21.0",
            "black>=23.7.0",
            "flake8>=6.1.0",
            "mypy>=1.5.0",
            "pre-commit>=3.3.3",
        ],
        "whisper": [
            "openai-whisper>=20230314",
            "faster-whisper>=0.10.0",
        ],
        "vosk": [
            "vosk>=0.3.45",
        ],
        "google": [
            "google-cloud-speech>=2.20.0",
        ],
        "docs": [
            "mkdocs>=1.5.0",
            "mkdocs-material>=9.2.0",
            "mkdocstrings[python]>=0.23.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "asr-hub=src.core.asr_hub:main",
        ],
    },
    include_package_data=True,
    package_data={
        "": ["*.yaml", "*.yml", "*.json"],
    },
)