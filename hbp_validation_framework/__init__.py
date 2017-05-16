"""
A Python package for working with the Human Brain Project Model Validation Framework.

Andrew Davison, CNRS, February 2016

Licence: BSD 3-clause, see LICENSE.txt

"""

import os
from importlib import import_module
import platform
try:  # Python 3
    from urllib.request import urlopen
    from urllib.parse import urlparse
    from urllib.error import URLError
except ImportError:  # Python 2
    from urllib2 import urlopen, URLError
    from urlparse import urlparse
import socket
import json
import getpass
import quantities
import requests
from requests.auth import AuthBase
from .datastores import URI_SCHEME_MAP


VALIDATION_FRAMEWORK_URL = "https://validation.brainsimulation.eu"
#VALIDATION_FRAMEWORK_URL = "http://127.0.0.1:8001"


class HBPAuth(AuthBase):
    """Attaches OIDC Bearer Authentication to the given Request object."""

    def __init__(self, token):
        # setup any auth-related data here
        self.token = token

    def __call__(self, r):
        # modify and return the request
        r.headers['Authorization'] = 'Bearer ' + self.token
        return r



class BaseClient(object):
    """
    
    """

    def __init__(self, username,
                 password=None,
                 url=VALIDATION_FRAMEWORK_URL):
        self.username = username
        self.url = url
        self.verify = True
        if password is None:
            # prompt for password
            password = getpass.getpass()
        self._hbp_auth(username, password)
        self.auth = HBPAuth(self.token)

    def _hbp_auth(self, username, password):
        """
        """
        redirect_uri = self.url + '/complete/hbp/'

        self.session = requests.Session()
        # 1. login button on NMPI
        rNMPI1 = self.session.get(self.url + "/login/hbp/?next=/config.json",
                                  allow_redirects=False, verify=self.verify)
        # 2. receives a redirect or some Javascript for doing an XMLHttpRequest
        if rNMPI1.status_code in (302, 200):
            # Get its new destination (location)
            if rNMPI1.status_code == 302:
                url = rNMPI1.headers.get('location')
            else:
                res = rNMPI1.content
                state = res[res.find("state")+6:res.find("&redirect_uri")]
                url = "https://services.humanbrainproject.eu/oidc/authorize?state={}&redirect_uri={}/complete/hbp/&response_type=code&client_id=8a6b7458-1044-4ebd-9b7e-f8fd3469069c".format(state, self.url)
            # get the exchange cookie
            cookie = rNMPI1.headers.get('set-cookie').split(";")[0]
            self.session.headers.update({'cookie': cookie})
            # 3. request to the provided url at HBP
            rHBP1 = self.session.get(url, allow_redirects=False, verify=self.verify)
            # 4. receives a redirect to HBP login page
            if rHBP1.status_code == 302:
                # Get its new destination (location)
                url = rHBP1.headers.get('location')
                cookie = rHBP1.headers.get('set-cookie').split(";")[0]
                self.session.headers.update({'cookie': cookie})
                # 5. request to the provided url at HBP
                rHBP2 = self.session.get(url, allow_redirects=False, verify=self.verify)
                # 6. HBP responds with the auth form
                if rHBP2.text:
                    # 7. Request to the auth service url
                    formdata = {
                        'j_username': username,
                        'j_password': password,
                        'submit': 'Login',
                        'redirect_uri': redirect_uri + '&response_type=code&client_id=nmpi'
                    }
                    headers = {'accept': 'application/json'}
                    rNMPI2 = self.session.post("https://services.humanbrainproject.eu/oidc/j_spring_security_check",
                                               data=formdata,
                                               allow_redirects=True,
                                               verify=self.verify,
                                               headers=headers)
                    # check good communication
                    if rNMPI2.status_code == requests.codes.ok:
                        #import pdb; pdb.set_trace()
                        # check success address
                        if rNMPI2.url == self.url + '/config.json':
                            # print rNMPI2.text
                            res = rNMPI2.json()
                            self.token = res['auth']['token']['access_token']
                            self.config = res
                        # unauthorized
                        else:
                            if 'error' in rNMPI2.url:
                                raise Exception("Authentication Failure: No token retrieved." + rNMPI2.url)
                            else:
                                raise Exception("Unhandled error in Authentication." + rNMPI2.url)
                    else:
                        raise Exception("Communication error")
                else:
                    raise Exception("Something went wrong. No text.")
            else:
                raise Exception("Something went wrong. Status code {} from HBP, expected 302".format(rHBP1.status_code))
        else:
            raise Exception("Something went wrong. Status code {} from NMPI, expected 302".format(rNMPI1.status_code))


class ValidationTestLibrary(BaseClient):
    """
    Client for the HBP Validation Test library.

    Usage
    -----

    test_library = ValidationTestLibrary()

    # List test definitions
    tests = test_library.list_validation_tests(brain_region="hippocampus",
                                               cell_type="pyramidal cell")

    # Download the test definition
    test = test_library.get_validation_test(test_uri)

    # Run the test
    score = test.judge(model)  # tests use the SciUnit framework

    # Register the result
    test_library.register(score)
    """

    def get_validation_test(self, test_uri, **params):
        """
        Download a test definition from the given URL, or load from a local JSON file.

        `params` are additional keyword arguments to be passed to the :class:`Test` constructor.

        Returns a :class:`sciunit.Test` instance.
        """
        if os.path.isfile(test_uri):
            # test_uri is a local path
            with open(test_uri) as fp:
                config = json.load(fp)
        else:
            config = requests.get(test_uri, auth=self.auth).json()

        # Import the Test class specified in the definition.
        # This assumes that the module containing the class is installed.
        # In future we could add the ability to (optionally) install
        # Python packages automatically.

        path_parts = config["code"]["path"].split(".")
        cls_name = path_parts[-1]
        module_name = ".".join(path_parts[:-1])
        test_module = import_module(module_name)
        test_cls = getattr(test_module, cls_name)

        # Load the reference data ("observations")
        observation_data = self._load_reference_data(config["data_location"])

        # Transform string representations of quantities, e.g. "-65 mV",
        # into :class:`quantities.Quantity` objects.
        observations = {}
        if type(observation_data.values()[0]) is dict:
            observations = observation_data
        else:
            for key, val in observation_data.items():
                try:
                    observations[key] = int(val)
                except ValueError:
                    try:
                        observations[key] = float(val)
                    except ValueError:
                        quantity_parts = val.split(" ")
                        number = float(quantity_parts[0])
                        units = " ".join(quantity_parts[1:])
                        observations[key] = quantities.Quantity(number, units)

        # Create the :class:`sciunit.Test` instance
        test_instance = test_cls(observations, **params)
        test_instance.id = config["resource_uri"]  # this is just the path part. Should be a full url
        return test_instance

    def _load_reference_data(self, uri):
        # Load the reference data ("observations")
        # For now this is assumed to be in JSON format, but we
        # should support other data formats.
        # For now, data is assumed to be on the local disk, but we
        # need to add support for remote downloads.
        parse_result = urlparse(uri)
        datastore = URI_SCHEME_MAP[parse_result.scheme](auth=self.auth)
        observation_data = datastore.load_data(uri)
        return observation_data

    def register(self, test_result, project=None, data_store=None):
        """
        Register the test result with the HBP Validation Results Service.

        Arguments:
            test_result - a :class:`sciunit.Score` instance returned by `test.judge(model)`
            project - the Collab ID
            data_store - a :class:`DataStore` instance, for uploading related data
                         generated by the test run, e.g. figures.
        """
        print("TEST RESULT: {}".format(test_result))
        print(test_result.model)
        print(test_result.prediction)
        print(test_result.observation)
        print(test_result.score)
        for file_path in test_result.related_data:
            print(file_path)
        # depending on value of data_store,
        # upload data file to Collab storage,
        # or just store path if it is on HPAC machine
        if data_store:
            results_storage = data_store.upload_data(test_result.related_data["figures"])
        else:
            results_storage = ""

        # check that the model is registered with the model registry.
        # If not, offer to register it?

        data = {
            "model_instance": {
                "model_id": test_result.model.id,  # uri? overload 'model.name' attribute?
                "version": test_result.model.version,
                "parameters": test_result.model.params
            },
            "test_definition": test_result.test.id,  # this should be the test URI provided to get_validation_test()?
            "results_storage": results_storage,
            "result": test_result.score,
            "passed": None,
            "platform": self.get_platform(),
        }
        if project:
            data["project"] = project
        print(data)
        response = requests.post(self.url + "/results/", data=json.dumps(data),
                                 auth=self.auth)
        print(response)

    def get_platform(self):
        """
        Return a dict containing information about the platform the test was run on.
        """
        # This needs to be extended to support remote execution, e.g. job queues on clusters.
        # Use Sumatra?
        network_name = platform.node()
        bits, linkage = platform.architecture()
        if _have_internet_connection():
            try:
                ip_addr = socket.gethostbyname(network_name)
            except socket.gaierror:
                ip_addr = "127.0.0.1"
        else:
            ip_addr = "127.0.0.1"
        return dict(architecture_bits=bits,
                    architecture_linkage=linkage,
                    machine=platform.machine(),
                    network_name=network_name,
                    ip_addr=ip_addr,
                    processor=platform.processor(),
                    release=platform.release(),
                    system_name=platform.system(),
                    version=platform.version())

    #def list_validation_tests(self, **filters):
    #
    #def list_validation_results(self, **filters):
    #


class ModelRepository(BaseClient):
    """
    Client for the HBP Model Repository.

    Usage
    -----

    model_library = ModelRepository()

    # List models
    models = model_library.list_models(brain_region="hippocampus")

    # Download a model description
    model_description = model_library.get_model(model_uri)

    """

    def list_models(self, **filters):
        model_list_uri = self.url + "/models/"  # todo: support filters
        models = requests.get(model_list_uri, auth=self.auth).json()
        return models

    def register(self, name, description="",  species="", brain_region="",
                 cell_type="", author="", source=""):
        data = locals()
        data.pop("self")
        model_list_uri = self.url + "/models/"
        response = requests.post(model_list_uri, data=json.dumps(data),
                                 auth=self.auth)
        return response.json()


def _have_internet_connection():
    """
    Not foolproof, but allows checking for an external connection with a short
    timeout, before trying socket.gethostbyname(), which has a very long
    timeout.
    """
    test_address = 'http://74.125.113.99'  # google.com
    try:
        urlopen(test_address, timeout=1)
        return True
    except (URLError, socket.timeout):
        pass
    return False
