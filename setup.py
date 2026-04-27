from setuptools import setup, find_packages

setup(
    name="video-analyzer-cli",
    version="0.6.0",
    description="CLI for video-analyzer-web",
    packages=find_packages(),
    python_requires=">=3.11",
    install_requires=[
        "click>=8.0",
        "rich>=10.0",
        "requests>=2.28",
        "python-socketio>=5.0",
    ],
    entry_points={
        "console_scripts": [
            "va=src.cli.main:cli",
        ],
    },
)
