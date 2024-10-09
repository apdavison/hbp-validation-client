from setuptools import setup

setup(
    name="hbp_validation_framework",
    version="0.9.0",
    packages=["hbp_validation_framework"],
    url="https://github.com/HumanBrainProject/hbp-validation-client",
    license="BSD",
    author="Andrew Davison and Shailesh Appukuttan",
    author_email="andrew.davison@cnrs.fr, appukuttan.shailesh@gmail.com",
    description="Python client for the EBRAINS Validation Framework web services",
    install_requires=["requests", "nameparser", "ebrains_drive", "ebrains_validation_framework"],
    extras_require={
        "reports": ["Jinja2", "pyppdf", "beautifulsoup4", "hbp_archive"],
        "utils": ["sciunit"],
    },
)
