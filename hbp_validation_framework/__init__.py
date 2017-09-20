"""
A Python package for working with the Human Brain Project Model Validation Framework.

Andrew Davison and Shailesh Appukuttan, CNRS, February 2016

Licence: BSD 3-clause, see LICENSE.txt

"""

import os
from importlib import import_module
import platform
try:  # Python 3
    from urllib.request import urlopen
    from urllib.parse import urlparse, urlencode
    from urllib.error import URLError
except ImportError:  # Python 2
    from urllib2 import urlopen, URLError
    from urlparse import urlparse
    from urllib import urlencode
import socket
import json
import ast
import getpass
import quantities
import requests
from requests.auth import AuthBase
from .datastores import URI_SCHEME_MAP


VALIDATION_FRAMEWORK_URL = "https://validation-dev.brainsimulation.eu"
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
            #password = os.environ.get('HBP_PASS')
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
                # OLD ID = 8a6b7458-1044-4ebd-9b7e-f8fd3469069c
                url = "https://services.humanbrainproject.eu/oidc/authorize?state={}&redirect_uri={}/complete/hbp/&response_type=code&client_id=90c719e0-29ce-43a2-9c53-15cb314c2d0b".format(state, self.url)
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

    def get_validation_test_definition(self, test_uri):
        """
        Download a test definition from the given URL, or load from a local JSON file.

        Returns a dict containing information about the test.

        Also see: `get_validation_test()`.
        """
        if os.path.isfile(test_uri):
            # test_uri is a local path
            with open(test_uri) as fp:
                config = json.load(fp)
        else:
            config = requests.get(test_uri, auth=self.auth).json()
        return config

    def get_validation_test(self, test_uri, **params):
        """
        Download a test definition from the given URL, or load from a local JSON file.

        `params` are additional keyword arguments to be passed to the :class:`Test` constructor.

        Returns a :class:`sciunit.Test` instance.
        """
        config = self.get_validation_test_definition(test_uri)

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
            if not data_store.authorized:
                data_store.authorize(self.auth)  # relies on data store using HBP authorization
                                                 # if this is not the case, need to authenticate/authorize
                                                 # the data store before passing to `register()`
            if data_store.collab_id is None:
                data_store.collab_id = project
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

    def list_validation_tests(self, **filters):
        """
        docstring needed
        """
        url = self.url + "/search?{}".format(urlencode(filters))
        print(url)
        response = requests.get(url)
        return response.json()

    #def list_validation_results(self, **filters):
    #


class ModelRepository(BaseClient):
    """
    Client for the HBP Model Repository. Can do the following:
    > Retrieve a specific model description from the repository
    > Retrieve a list of model descriptions from the repository
    > Return list of valid values (where applicable) for model catalog fields
    > Add a new model description to the repository
    > Add a new model instance for an existing model in the repository
    > Add a new image for an existing model in the repository

    Usage
    -----
    model_library = ModelRepository()
    """

    def get_model(self, model_id="", alias="", instances=False, images=False):
        """
        Retrieve a model description by its model_id or alias.
        Either model_id or alias needs to be provided, with model_id taking precedence over alias.

        (Optional) Set 'instances' to False if you wish to omit the details of the model instances.
        (Optional) Set 'images' to False if you wish to omit the details of the model images.

        Example usage:
        model = model_library.get_model(model_id="8c7cb9f6-e380-452c-9e98-e77254b088c5")
        or
        model = model_library.get_model(alias="B1")
        """
        if model_id == "" and alias == "":
            raise Exception("Model ID or alias needs to be provided for finding a model.")
        elif model_id != "":
            model_uri = self.url + "/scientificmodel/?id=" + model_id + "&format=json"
        else:
            model_uri = self.url + "/scientificmodel/?alias=" + alias + "&format=json"
        model = requests.get(model_uri, auth=self.auth).json()

        if instances == False:
            model["models"][0].pop("instances")
        if images == False:
            model["models"][0].pop("images")
        return model["models"][0]

    def list_models(self, **filters):
        """
        List models satisfying all specified filters

        Example usage:
        models = model_library.list_models()
        models = model_library.list_models(app_id="39968")
        models = model_library.list_models(cell_type="Pyramidal Cell",
                                           brain_region="Hippocampus")
        """
        params = locals()["filters"]
        model_list_uri = self.url + "/scientificmodel/?"+urlencode(params)+"&format=json"
        models = requests.get(model_list_uri, auth=self.auth).json()
        return models["models"]

    def get_options(self, param=""):
        """
        Will return the list of valid values (where applicable) for model catalog fields.
        If a parameter is specified then, only values that correspond to it will be returned,
        else values for all fields are returned.
        Note: When specified, only the first parameter is considered; the rest are ignored.
              So the function either returns for all parameters or a single parameter.

        Example Usage:
        data = model_library.get_options()
        or
        data = model_library.get_options("cell_type")
        """
        if param == "":
            param = "all"

        if param in ["cell_type", "test_type", "score_type", "brain_region", "model_type", "data_modalities", "species", "all"]:
            url = self.url + "/authorizedcollabparameterrest/?python_client=true&parameters="+param+"&format=json"
        else:
            raise Exception("Parameter, if specified, has to be one from: cell_type, test_type, score_type, brain_region, model_type, data_modalities, species, all]")
        data = requests.get(url, auth=self.auth).json()
        return ast.literal_eval(json.dumps(data))

    def register_model(self, app_id="", name="", alias=None, author="", private="False",
                       cell_type="", model_type="", brain_region="", species="", description="",
                       instances=[], images=[]):
        """
        To register a new model on the model catalog

        Example usage:
        (without specification of instances and images)
        model = model_library.register_model(app_id="39968", name="Test Model - B2",
                        alias="Model-B2", author="Shailesh Appukuttan",
                        private="False", cell_type="Granule Cell", model_type="Single Cell",
                        brain_region="Basal Ganglia", species="Mouse (Mus musculus)",
                        description="This is a test entry")
        or
        (with specification of instances and images)
        model = model_library.register_model(app_id="39968", name="Client Test - C2",
                        alias="C2", author="Shailesh Appukuttan",
                        private="False", cell_type="Granule Cell", model_type="Single Cell",
                        brain_region="Basal Ganglia", species="Mouse (Mus musculus)",
                        description="This is a test entry! Please ignore.",
                        instances=[{"source":"https://www.abcde.com",
                                    "version":"1.0", "parameters":""},
                                   {"source":"https://www.12345.com",
                                    "version":"2.0", "parameters":""}],
                        images=[{"url":"http://www.neuron.yale.edu/neuron/sites/default/themes/xchameleon/logo.png",
                                 "caption":"NEURON Logo"},
                                {"url":"https://collab.humanbrainproject.eu/assets/hbp_diamond_120.png",
                                 "caption":"HBP Logo"}])
        """
        values = self.get_options()

        if cell_type not in values["cell_type"]:
            raise Exception("cell_type = '" +cell_type+"' is invalid.\nValue has to be one of these: " + str(values["cell_type"]))
        if model_type not in values["model_type"]:
            raise Exception("model_type = '" +model_type+"' is invalid.\nValue has to be one of these: " + str(values["model_type"]))
        if brain_region not in values["brain_region"]:
            raise Exception("brain_region = '" +brain_region+"' is invalid.\nValue has to be one of these: " + str(values["brain_region"]))
        if species not in values["species"]:
            raise Exception("species = '" +species+"' is invalid.\nValue has to be one of these: " + str(values["species"]))

        if private not in ["True", "False"]:
            raise Exception("Model's 'private' attribute should be specified as True / False. Default value is False.")
        if alias == "":
            alias = None

        model_data = locals()
        model_data.pop("self")
        model_data.pop("app_id")
        model_data.pop("instances")
        model_data.pop("images")

        model_list_uri = self.url + "/scientificmodel/?app_id="+app_id+"&format=json"
        model_json = {
                        "model": model_data,
                        "model_instance":instances,
                        "model_image":images
                     }
        headers = {'Content-type': 'application/json'}
        response = requests.post(model_list_uri, data=json.dumps(model_json),
                                 auth=self.auth, headers=headers)
        return response

    def add_model_instance(self, model_id="", alias="", source="", version="", parameters=""):
        """
        To add a single new instance of an existing model in the model catalog.
        'model_id' needs to be specified as input parameter.
        Returns True if instance is successfully added to the model catalog, else False.
        The second return parameter provides the original server response.

        Example usage:
        status = model_library.add_model_instance(model_id="196b89a3-e672-4b96-8739-748ba3850254",
                                                  source="https://www.abcde.com",
                                                  version="1.0",
                                                  parameters="")

        Note: 'alias' is not currently implemented in the API, and the same is kept for future use here.
        TO DO: Either model_id or alias needs to be provided, with uri taking precedence over alias.
        """
        instance_data = locals()
        instance_data.pop("self")

        if model_id == "" and alias == "":
            raise Exception("Model ID needs to be provided for finding the model.")
            #raise Exception("Model ID or alias needs to be provided for finding the model.")
        elif model_id != "":
            url = self.url + "/scientificmodelinstance/?format=json"
        else:
            raise Exception("alias is not currently implemented for this feature.")
            #url = self.url + "/scientificmodelinstance/?alias=" + alias + "&format=json"
        headers = {'Content-type': 'application/json'}
        response = requests.post(url, data=json.dumps([instance_data]),
                                 auth=self.auth, headers=headers)
        if str(response) == "<Response [201]>":
            return True, response
        else:
            return False, response

    def add_model_image(self, model_id="", alias="", url="", caption=""):
        """
        To add a new image to an existing model in the model catalog.
        'model_id' needs to be specified as input parameter.
        Returns True if instance is successfully added to the model catalog, else False.
        The second return parameter provides the original server response.

        Example usage:
        status = model_library.add_model_image(model_id="196b89a3-e672-4b96-8739-748ba3850254",
                                               url="http://www.neuron.yale.edu/neuron/sites/default/themes/xchameleon/logo.png",
                                               caption="NEURON Logo")

        Note: 'alias' is not currently implemented in the API, and the same is kept for future use here.
        TO DO: Either model_id or alias needs to be provided, with uri taking precedence over alias.
        """
        image_data = locals()
        image_data.pop("self")
        image_data.pop("alias")

        if model_id == "" and alias == "":
            raise Exception("Model ID needs to be provided for finding the model.")
            #raise Exception("Model ID or alias needs to be provided for finding the model.")
        elif model_id != "":
            url = self.url + "/scientificmodelimage/?format=json"
        else:
            raise Exception("alias is not currently implemented for this feature.")
            #url = self.url + "/scientificmodelimage/?alias=" + alias + "&format=json"
        headers = {'Content-type': 'application/json'}
        print "url = ", url
        print "[image_data] = ", [image_data]
        response = requests.post(url, data=json.dumps([image_data]),
                                 auth=self.auth, headers=headers)
        if str(response) == "<Response [201]>":
            return True, response
        else:
            return False, response


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
