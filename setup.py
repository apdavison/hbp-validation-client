import os
from distutils.core import setup

def package_files(directory):
    paths = []
    for (path, directories, filenames) in os.walk(directory):
        for filename in filenames:
            paths.append(os.path.join(path, filename))
    return paths

json_files = package_files('hbp_validation_framework/jsonTreeViewer')

setup(
    name='hbp_validation_framework',
    version='0.3.0',
    packages=['hbp_validation_framework'],
    package_data={'hbp_validation_framework': json_files},
    url='https://github.com/HumanBrainProject/hbp-validation-client',
    license='BSD',
    author='Andrew Davison and Shailesh Appukuttan',
    author_email='andrew.davison@unic.cnrs-gif.fr, shailesh.appukuttan@unic.cnrs-gif.fr',
    description='Python client for the HBP Validation Framework web services'
)
