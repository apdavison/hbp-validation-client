"""
A Python package for working with the EBRAINS / Human Brain Project Model Validation Framework.

Andrew Davison and Shailesh Appukuttan, CNRS, 2017-2024

License: BSD 3-clause, see LICENSE.txt

"""

import warnings

from ebrains_validation_framework import TestLibrary, ModelCatalog, datastores, sample, utils, versioning

warnings.warn(
    "The hbp_validation_framework package is deprecated. "
    "Please use ebrains_validation_framework instead"
)
