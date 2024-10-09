"""
Script to generate a codemeta.json file

This script requires a PyPI release of the desired version.
"""

import json
from dateutil import parser as date_parser
import requests


def generate_for_version(version):  # e.g. version="0.9.0"

    response = requests.get(f"https://pypi.org/pypi/ebrains-validation-framework/{version}/json")
    pypi_metadata = response.json()

    with open("./authors.json") as fp:
        authors = json.load(fp)

    if pypi_metadata["info"]["requires_python"]:
        requirements = [f"Python {pypi_metadata['info']['requires_python']}"] + pypi_metadata["info"][
            "requires_dist"
        ] or []
    else:
        requirements = None

    return {
        "@context": "https://doi.org/10.5063/schema/codemeta-2.0",
        "@type": "SoftwareSourceCode",
        "license": "https://spdx.org/licenses/BSD-3-Clause.html",
        "codeRepository": "https://github.com/HumanBrainProject/ebrains-validation-client",
        # "contIntegration": "https://gitlab.ebrains.eu/model-validation/todo",
        "dateModified": date_parser.parse(pypi_metadata["urls"][0]["upload_time"]).date().isoformat(),
        "downloadUrl": pypi_metadata["urls"][0]["url"],
        "issueTracker": "https://github.com/HumanBrainProject/ebrains-validation-client/issues",
        "name": "ebrains-validation-framework",
        "version": version,
        "identifier": f"https://pypi.org/project/ebrains-validation-framework/{version}/",
        "description": pypi_metadata["info"]["summary"],  # or use "description"?
        "applicationCategory": "neuroscience",
        # "releaseNotes": f"https://ebrains-validation-client.readthedocs.io/en/latest/releases/{version}.html",
        "funding": "https://cordis.europa.eu/project/id/945539",
        "developmentStatus": "active",
        "referencePublication": None,
        "funder": {"@type": "Organization", "name": "European Commission"},
        "programmingLanguage": ["Python"],
        "operatingSystem": ["Linux", "Windows", "macOS"],
        "softwareRequirements": requirements,
        "relatedLink": ["https://ebrains-validation-client.readthedocs.io"],
        "author": authors,
    }


if __name__ == "__main__":
    import sys
    import os

    version = sys.argv[1]
    code_metadata = generate_for_version(version)

    with open(os.path.join(os.path.dirname(__file__), "..", "codemeta.json"), "w") as fp:
        json.dump(code_metadata, fp, indent=2)
