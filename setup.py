from setuptools import setup

setup()

# import os
# from setuptools import setup


# def package_files(base_dir, directory):
#     pwd = os.getcwd()
#     os.chdir(base_dir)
#     paths = []
#     for (path, directories, filenames) in os.walk(directory):
#         for filename in filenames:
#             paths.append(os.path.join(path, filename))
#     os.chdir(pwd)
#     return paths


# json_files = package_files("ebrains_validation_framework", "jsonTreeViewer")
# template_files = package_files("ebrains_validation_framework", "templates")

# setup(
#     name="ebrains_validation_framework",
#     version="0.9.0.dev",
#     packages=["ebrains_validation_framework"],
#     package_data={"": json_files + template_files},
#     url="https://github.com/HumanBrainProject/ebrains-validation-client",
#     license="BSD",
#     author="Andrew Davison and Shailesh Appukuttan",
#     author_email="andrew.davison@cnrs.fr, appukuttan.shailesh@gmail.com",
#     description="Python client for the EBRAINS Validation Framework web services",
#     install_requires=["requests", "nameparser", "ebrains_drive"],
#     extras_require={
#         "reports": ["Jinja2", "pyppdf", "beautifulsoup4", "hbp_archive"],
#         "utils": ["sciunit"],
#     },
# )
