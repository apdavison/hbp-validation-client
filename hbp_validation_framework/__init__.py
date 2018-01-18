"""
A Python package for working with the Human Brain Project Model Validation Framework.

Andrew Davison and Shailesh Appukuttan, CNRS, 2017

License: BSD 3-clause, see LICENSE.txt

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

TOKENFILE = os.path.expanduser("~/.hbptoken")

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
    Base class that handles HBP authentication
    """
    # Note: Could possibly simplify the code later

    def __init__(self, username,
                 password=None,
                 environment="production"):

        if environment == "production":
            self.url = "https://validation-v1.brainsimulation.eu"
            self.client_id = "3ae21f28-0302-4d28-8581-15853ad6107d" # Prod ID
        elif environment == "dev":
            self.url = "https://validation-dev.brainsimulation.eu"
            self.client_id = "90c719e0-29ce-43a2-9c53-15cb314c2d0b" # Dev ID
        else:
            if os.path.isfile('config.json') and os.access('config.json', os.R_OK):
                with open('config.json') as config_file:
                    config = json.load(config_file)
                    if environment in config:
                        if "url" in config[environment] and "client_id" in config[environment]:
                            self.url = config[environment]["url"]
                            self.client_id = config[environment]["client_id"]
                        else:
                            raise KeyError("Cannot load environment info: config.json does not contain sufficient info for environment = {}".format(environment))
                    else:
                        raise KeyError("Cannot load environment info: config.json does not contain environment = {}".format(environment))
            else:
                raise IOError("Cannot load environment info: config.json not found in the current directory.")

        self.username = username
        self.verify = True
        if password is None:
            # check for a stored token
            self.token = None
            if os.path.exists(TOKENFILE):
                with open(TOKENFILE) as fp:
                    # self.token = json.load(fp).get(username, None)["access_token"]
                    data = json.load(fp).get(username, None)
                    if data and "access_token" in data:
                        self.token = data["access_token"]
                        if not self._check_token_valid():
                            print("HBP authentication token is invalid or has expired. Will need to re-authenticate.")
                            self.token = None
                    else:
                        print("HBP authentication token file not having required JSON data.")
            else:
                print("HBP authentication token file not found locally.")

            if self.token is None:
                password = os.environ.get('HBP_PASS')
                if password is not None:
                    try:
                        self._hbp_auth(username, password)
                    except Exception:
                        print("Authentication Failure. Possibly incorrect HBP password saved in environment variable 'HBP_PASS'.")
                if not hasattr(self, 'config'):
                    try:
                        # prompt for password
                        print("Please enter your HBP password: ")
                        password = getpass.getpass()
                        self._hbp_auth(username, password)
                    except Exception:
                        print("Authentication Failure! Password entered is possibly incorrect.")
                        raise
                with open(TOKENFILE, "w") as fp:
                    json.dump({username: self.config["auth"]["token"]}, fp)
                os.chmod(TOKENFILE, 0o600)
        else:
            try:
                self._hbp_auth(username, password)
            except Exception:
                print("Authentication Failure! Password entered is possibly incorrect.")
                raise
            with open(TOKENFILE, "w") as fp:
                json.dump({username: self.config["auth"]["token"]}, fp)
            os.chmod(TOKENFILE, 0o600)
        self.auth = HBPAuth(self.token)

    def _check_token_valid(self):
        """
        Checks with the hbp-collab-service if the locally saved HBP token is valid.
        See if this can be tweaked to improve performance.
        """
        url = "https://services.humanbrainproject.eu/collab/v0/collab/"
        data = requests.get(url, auth=HBPAuth(self.token))
        if data.status_code == 200:
            return True
        else:
            return False

    def _hbp_auth(self, username, password):
        """
        HBP authentication
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
                if not isinstance(res, str):
                    res = res.decode("ascii")
                state = res[res.find("state")+6:res.find("&redirect_uri")]
                url = "https://services.humanbrainproject.eu/oidc/authorize?state={}&redirect_uri={}/complete/hbp/&response_type=code&client_id={}".format(state, self.url, self.client_id)
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
                    #print "rNMPI2.status_code = ", rNMPI2.status_code
                    #print "content = ", rNMPI2.content
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

    def _translate_URL_to_UUID(self, path):
        """
        Can take a path such as `collab:///5165/hippoCircuit_20171027-142713`
        with 5165 being the collab ID and the latter part being the target folder
        name, and translate this to the UUID on the HBP Collaboratory storage.
        The target can be a file or folder.
        """
        base_url = "https://services.humanbrainproject.eu/storage/v1/api/entity/"
        if path.startswith("collab://"):
            path = path[len("collab://"):]
        url = base_url + "?path=" + path
        data = requests.get(url, auth=self.auth)
        if data.status_code == 200:
            return data.json()["uuid"]
        else:
            raise Exception("Error: " + data.content)

    def _download_resource(self, uuid):
        """
        Downloads the resource specified by the UUID on the HBP Collaboratory.
        Target can be a file or a folder. Returns a list containing absolute
        filepaths of all downloaded files.
        """
        files_downloaded = []

        base_url = "https://services.humanbrainproject.eu/storage/v1/api/entity/"
        url = base_url + "?uuid=" + uuid
        data = requests.get(url, auth=self.auth)
        if data.status_code != 200:
            raise Exception("The provided 'uuid' is invalid!")
        else:
            data = data.json()
            if data["entity_type"] == "folder":
                if not os.path.exists(data["name"]):
                    os.makedirs(data["name"])
                os.chdir(data["name"])
                base_url = "https://services.humanbrainproject.eu/storage/v1/api/folder/"
                url = base_url + uuid + "/children/"
                folder_data = requests.get(url, auth=self.auth)
                folder_sublist = folder_data.json()["results"]
                for entity in folder_sublist:
                    files_downloaded.extend(self._download_resource(entity["uuid"]))
                os.chdir('..')
            elif data["entity_type"] == "file":
                base_url = "https://services.humanbrainproject.eu/storage/v1/api/file/"
                url = base_url + uuid + "/content/"
                file_data = requests.get(url, auth=self.auth)
                with open(data["name"], "w") as filename:
                    filename.write("%s" % file_data.content)
                    files_downloaded.append(os.path.realpath(filename.name))
            else:
                raise Exception("Downloading of resources currently supported only for files and folders!")
        return files_downloaded

    @classmethod
    def from_existing(cls, client):
        """Used to easily create a TestLibrary if you already have a ModelCatalog, or vice versa"""
        obj = cls.__new__(cls)
        for attrname in ("username", "url", "client_id", "token", "verify", "auth"):
            setattr(obj, attrname, getattr(client, attrname))
        return obj


class TestLibrary(BaseClient):
    """Client for the HBP Validation Test library.

    The TestLibrary client manages all actions pertaining to tests and results.
    The following actions can be performed:

    ====================================   ====================================
    Action                                 Method
    ====================================   ====================================
    Get test definition                    :meth:`get_test_definition`
    Get test as Python (sciunit) class     :meth:`get_validation_test`
    List test definitions                  :meth:`list_tests`
    Add new test definition                :meth:`add_test`
    Edit test definition                   :meth:`edit_test`
    Get test instances                     :meth:`get_test_instance`
    List test instances                    :meth:`list_test_instances`
    Add new test instance                  :meth:`add_test_instance`
    Edit test instance                     :meth:`edit_test_instance`
    Get valid attribute values             :meth:`get_attribute_options`
    Get test result                        :meth:`get_result`
    List test results                      :meth:`list_results`
    Register test result                   :meth:`register_result`
    ====================================   ====================================

    Parameters
    ----------
    username : string
        Your HBP Collaboratory username.
    password : string, optional
        Your HBP Collaboratory password; advisable to not enter as plaintext.
        If left empty, you would be prompted for password at run time (safer).
    environment : string, optional
        Used to indicate whether being used for development/testing purposes.
        Set as `production` as default for using the production system,
        which is appropriate for most users. When set to `dev`, it uses the
        `development` system. Other environments, if required, should be defined
        inside a json file named `config.json` in the working directory. Example:

        .. code-block:: JSON

            {
                "prod": {
                    "url": "https://validation-v1.brainsimulation.eu",
                    "client_id": "3ae21f28-0302-4d28-8581-15853ad6107d"
                },
                "dev_test": {
                    "url": "https://validation-dev.brainsimulation.eu",
                    "client_id": "90c719e0-29ce-43a2-9c53-15cb314c2d0b"
                }
            }

    Examples
    --------
    Instantiate an instance of the TestLibrary class

    >>> test_library = TestLibrary(hbp_username)
    """

    def get_test_definition(self, test_path="", test_id = "", alias=""):
        """Retrieve a specific test definition.

        A specific test definition can be retrieved from the test library
        in the following ways (in order of priority):

        1. load from a local JSON file specified via `test_path`
        2. specify the `test_id`
        3. specify the `alias` (of the test)

        Parameters
        ----------
        test_path : string
            Location of local JSON file with test definition.
        test_id : UUID
            System generated unique identifier associated with test definition.
        alias : string
            User-assigned unique identifier associated with test definition.

        Note
        ----
        Also see: :meth:`get_validation_test`

        Returns
        -------
        dict
            Information about the test.

        Examples
        --------
        >>> test = test_library.get_test_definition("/home/shailesh/Work/dummy_test.json")
        >>> test = test_library.get_test_definition(test_id="7b63f87b-d709-4194-bae1-15329daf3dec")
        >>> test = test_library.get_test_definition(alias="CDT-6")
        """

        if test_path == "" and test_id == "" and alias == "":
            raise Exception("test_path or test_id or alias needs to be provided for finding a test.")
        if test_path:
            if os.path.isfile(test_path):
                # test_path is a local path
                with open(test_path) as fp:
                    test_json = json.load(fp)
            else:
                raise Exception("Error in local file path specified by test_path.")
        else:
            if test_id:
                url = self.url + "/tests/?id=" + test_id + "&format=json"
            else:
                url = self.url + "/tests/?alias=" + alias + "&format=json"
            test_json = requests.get(url, auth=self.auth)

        if test_json.status_code != 200:
            raise Exception("Error in retrieving test. Response = " + str(test_json.content))
        test_json = test_json.json()
        if len(test_json["tests"]) == 1:
            return test_json["tests"][0]
        else:
            raise Exception("Error in retrieving test definition. Possibly invalid input data.")

    def get_validation_test(self, test_path="", instance_path="", instance_id ="", test_id = "", alias="", version="", **params):
        """Retrieve a specific test instance as a Python class (sciunit.Test instance).

        A specific test definition can be specified
        in the following ways (in order of priority):

        1. load from a local JSON file specified via `test_path` and `instance_path`
        2. specify `instance_id` corresponding to test instance in test library
        3. specify `test_id` and `version`
        4. specify `alias` (of the test) and `version`

        Parameters
        ----------
        test_path : string
            Location of local JSON file with test definition.
        instance_path : string
            Location of local JSON file with test instance metadata.
        instance_id : UUID
            System generated unique identifier associated with test instance.
        test_id : UUID
            System generated unique identifier associated with test definition.
        alias : string
            User-assigned unique identifier associated with test definition.
        version : string
            User-assigned identifier (unique for each test) associated with test instance.
        **params :
            Additional keyword arguments to be passed to the Test constructor.

        Note
        ----
        To confirm the priority of parameters for specifying tests and instances,
        see :meth:`get_test_definition` and :meth:`get_test_instance`

        Returns
        -------
        sciunit.Test
            Returns a :class:`sciunit.Test` instance.

        Examples
        --------
        >>> test = test_library.get_validation_test(alias="CDT-6", instance_id="36a1960e-3e1f-4c3c-a3b6-d94e6754da1b")
        """

        if test_path == "" and instance_id == "" and test_id == "" and alias == "":
            raise Exception("One of the following needs to be provided for finding the required test:\n"
                            "test_path, instance_id, test_id or alias")
        elif instance_path == "" and instance_id == "" and  version == "":
            raise Exception("One of the following needs to be provided for finding the required test instance:\n"
                            "instance_path, instance_id or version")
        else:
            if instance_id:
                # `instance_id` is sufficient for identifying both test and instance
                test_instance_json = self.get_test_instance(instance_path=instance_path, instance_id=instance_id) # instance_path added just to maintain order of priority
                test_id = test_instance_json["test_definition_id"]
                test_json = self.get_test_definition(test_path=test_path, test_id=test_id) # test_path added just to maintain order of priority
            else:
                test_json = self.get_test_definition(test_path=test_path, test_id=test_id, alias=alias)
                test_id = test_json["id"] # in case test_id was not input for specifying test
                test_instance_json = self.get_test_instance(instance_path=instance_path, instance_id=instance_id, test_id=test_id, version=version)

        # Import the Test class specified in the definition.
        # This assumes that the module containing the class is installed.
        # In future we could add the ability to (optionally) install
        # Python packages automatically.
        path_parts = test_instance_json["path"].split(".")
        cls_name = path_parts[-1]
        module_name = ".".join(path_parts[:-1])
        test_module = import_module(module_name)
        test_cls = getattr(test_module, cls_name)

        # Load the reference data ("observations")
        observation_data = self._load_reference_data(test_json["data_location"])

        # Transform string representations of quantities, e.g. "-65 mV",
        # into :class:`quantities.Quantity` objects.

        # note: we shouldn't really do this here; this should be done in the test classes
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
                        try:
                            number = float(quantity_parts[0])
                        except ValueError:
                            observations[key] = val
                        else:
                            units = " ".join(quantity_parts[1:])
                            observations[key] = quantities.Quantity(number, units)

        # Create the :class:`sciunit.Test` instance
        test_instance = test_cls(observation=observations, **params)
        test_instance.id = test_instance_json["id"]  # this is just the path part. Should be a full url
        return test_instance

    def list_tests(self, **filters):
        """Retrieve a list of test definitions satisfying specified filters.

        The filters may specify one or more attributes that belong
        to a test definition. The following test attributes can be specified:

        * name
        * alias
        * version
        * author
        * species
        * age
        * brain_region
        * cell_type
        * data_modality
        * test_type
        * score_type
        * model_type
        * data_type
        * publication

        Parameters
        ----------
        **filters : variable length keyword arguments
            To be used to filter test definitions from the test library.

        Returns
        -------
        list
            List of model descriptions satisfying specified filters.

        Examples
        --------
        >>> tests = test_library.list_tests()
        >>> tests = test_library.list_tests(test_type="single cell activity")
        >>> tests = test_library.list_tests(test_type="single cell activity", cell_type="Pyramidal Cell")
        """

        params = locals()["filters"]
        url = self.url + "/tests/?"+urlencode(params)+"&format=json"
        tests = requests.get(url, auth=self.auth).json()
        return tests["tests"]

    def add_test(self, name="", alias=None, version="", author="", species="",
                      age="", brain_region="", cell_type="", data_modality="",
                      test_type="", score_type="", protocol="", data_location="",
                      data_type="", publication="", repository="", path=""):
        """Register a new test on the test library.

        This allows you to add a new test to the test library. A test instance
        (version) needs to be specified when registering a new test.

        Parameters
        ----------
        name : string
            Name of the test definition to be created.
        alias : string, optional
            User-assigned unique identifier to be associated with test definition.
        version : string
            User-assigned identifier (unique for each test) associated with test instance.
        author : string
            Name of person creating the test.
        species : string
            The species from which the data was collected.
        age : string
            The age of the specimen.
        brain_region : string
            The brain region being targeted in the test.
        cell_type : string
            The type of cell being examined.
        data_modality : string
            Specifies the type of observation used in the test.
        test_type : string
            Specifies the type of the test.
        score_type : string
            The type of score produced by the test.
        protocol : string
            Experimental protocol involved in obtaining reference data.
        data_location : string
            URL of file containing reference data (observation).
        data_type : string
            The type of reference data (observation).
        publication : string
            Publication or comment (e.g. "Unpublished") to be associated with observation.
        repository : string
            URL of Python package repository (e.g. GitHub).
        path : string
            Python path (not filesystem path) to test source code within Python package.

        Returns
        -------
        UUID
            (Verify!) UUID of the test instance that has been created.

        Examples
        --------
        >>> test = test_library.add_test(name="Cell Density Test", alias="", version="1.0", author="Shailesh Appukuttan",
                                species="Mouse (Mus musculus)", age="TBD", brain_region="Hippocampus", cell_type="Other",
                                data_modality="electron microscopy", test_type="network structure", score_type="Other", protocol="Later",
                                data_location="collab://Validation Framework/observations/test_data/cell_density_Halasy_1996.json",
                                data_type="Mean, SD", publication="Halasy et al., 1996",
                                repository="https://github.com/appukuttan-shailesh/morphounit.git", path="morphounit.tests.CellDensityTest")
        """

        values = self.get_attribute_options()

        if species not in values["species"]:
            raise Exception("species = '" +species+"' is invalid.\nValue has to be one of these: " + str(values["species"]))
        if brain_region not in values["brain_region"]:
            raise Exception("brain_region = '" +brain_region+"' is invalid.\nValue has to be one of these: " + str(values["brain_region"]))
        if cell_type not in values["cell_type"]:
            raise Exception("cell_type = '" +cell_type+"' is invalid.\nValue has to be one of these: " + str(values["cell_type"]))
        if data_modality not in values["data_modalities"]:
            raise Exception("data_modality = '" +data_modality+"' is invalid.\nValue has to be one of these: " + str(values["data_modality"]))
        if test_type not in values["test_type"]:
            raise Exception("test_type = '" +test_type+"' is invalid.\nValue has to be one of these: " + str(values["test_type"]))
        if score_type not in values["score_type"]:
            raise Exception("score_type = '" +score_type+"' is invalid.\nValue has to be one of these: " + str(values["score_type"]))

        if alias == "":
            alias = None

        test_data = locals()
        test_data.pop("self")
        code_data = {}
        for key in ["version", "repository", "path"]:
            code_data[key] = test_data.pop(key)

        url = self.url + "/tests/?format=json"
        test_json = {
                        "test_data": test_data,
                        "code_data": code_data
                    }

        headers = {'Content-type': 'application/json'}
        response = requests.post(url, data=json.dumps(test_json),
                                 auth=self.auth, headers=headers)
        if response.status_code == 201:
            return response.json()
        else:
            raise Exception("Error in adding test. Response = " + str(response.json()))

    def edit_test(self, name="", test_id="", alias=None, version="", author="",
                  species="", age="", brain_region="", cell_type="", data_modality="",
                  test_type="", score_type="", protocol="", data_location="",
                  data_type="", publication="", repository="", path=""):
        """Edit an existing test in the test library.

        To update an existing test, the `test_id` must be provided. Any of the
        other parameters may be updated.

        Parameters
        ----------
        name : string
            Name of the test definition.
        test_id : UUID
            System generated unique identifier associated with test definition.
        alias : string, optional
            User-assigned unique identifier to be associated with test definition.
        version : string
            User-assigned identifier (unique for each test) associated with test instance.
        author : string
            Name of person who created the test.
        species : string
            The species from which the data was collected.
        age : string
            The age of the specimen.
        brain_region : string
            The brain region being targeted in the test.
        cell_type : string
            The type of cell being examined.
        data_modality : string
            Specifies the type of observation used in the test.
        test_type : string
            Specifies the type of the test.
        score_type : string
            The type of score produced by the test.
        protocol : string
            Experimental protocol involved in obtaining reference data.
        data_location : string
            URL of file containing reference data (observation).
        data_type : string
            The type of reference data (observation).
        publication : string
            Publication or comment (e.g. "Unpublished") to be associated with observation.
        repository : string
            URL of Python package repository (e.g. github).
        path : string
            Python path (not filesystem path) to test source code within Python package.

        Note
        ----
        Test instances cannot be edited here.
        This has to be done using :meth:`edit_test_instance`

        Returns
        -------
        UUID
            (Verify!) UUID of the test instance that has been edited.

        Examples
        --------
        test = test_library.edit_test(name="Cell Density Test", test_id="7b63f87b-d709-4194-bae1-15329daf3dec", alias="CDT-6", author="Shailesh Appukuttan", publication="Halasy et al., 1996",
                                      species="Mouse (Mus musculus)", brain_region="Hippocampus", cell_type="Other", age="TBD", data_modality="electron microscopy",
                                      test_type="network structure", score_type="Other", protocol="To be filled sometime later", data_location="collab://Validation Framework/observations/test_data/cell_density_Halasy_1996.json", data_type="Mean, SD")
        """

        values = self.get_attribute_options()

        if species not in values["species"]:
            raise Exception("species = '" +species+"' is invalid.\nValue has to be one of these: " + str(values["species"]))
        if brain_region not in values["brain_region"]:
            raise Exception("brain_region = '" +brain_region+"' is invalid.\nValue has to be one of these: " + str(values["brain_region"]))
        if cell_type not in values["cell_type"]:
            raise Exception("cell_type = '" +cell_type+"' is invalid.\nValue has to be one of these: " + str(values["cell_type"]))
        if data_modality not in values["data_modalities"]:
            raise Exception("data_modality = '" +data_modality+"' is invalid.\nValue has to be one of these: " + str(values["data_modality"]))
        if test_type not in values["test_type"]:
            raise Exception("test_type = '" +test_type+"' is invalid.\nValue has to be one of these: " + str(values["test_type"]))
        if score_type not in values["score_type"]:
            raise Exception("score_type = '" +score_type+"' is invalid.\nValue has to be one of these: " + str(values["score_type"]))

        if alias == "":
            alias = None

        id = test_id   # as needed by API
        test_data = locals()
        for key in ["self", "test_id"]:
            test_data.pop(key)

        url = self.url + "/tests/?format=json"
        test_json = test_data   # retaining similar structure as other methods

        headers = {'Content-type': 'application/json'}
        response = requests.put(url, data=json.dumps(test_json),
                                auth=self.auth, headers=headers)
        if response.status_code == 202:
            return response.json()
        else:
            raise Exception("Error in editing test. Response = " + str(response.json()))

    def get_test_instance(self, instance_path="", instance_id="", test_id="", alias="", version=""):
        """Retrieve a specific test instance definition from the test library.

        A specific test instance can be retrieved
        in the following ways (in order of priority):

        1. load from a local JSON file specified via `instance_path`
        2. specify `instance_id` corresponding to test instance in test library
        3. specify `test_id` and `version`
        4. specify `alias` (of the test) and `version`

        Parameters
        ----------
        instance_path : string
            Location of local JSON file with test instance metadata.
        instance_id : UUID
            System generated unique identifier associated with test instance.
        test_id : UUID
            System generated unique identifier associated with test definition.
        alias : string
            User-assigned unique identifier associated with test definition.
        version : string
            User-assigned identifier (unique for each test) associated with test instance.

        Returns
        -------
        dict
            Information about the test instance.

        Examples
        --------
        >>> test_instance = test_library.get_test_instance(test_id="7b63f87b-d709-4194-bae1-15329daf3dec", version="1.0")
        """

        if instance_path == "" and instance_id == "" and (test_id == "" or version == "") and (alias == "" or version == ""):
            raise Exception("instance_path or instance_id or (test_id, version) or (alias, version) needs to be provided for finding a test instance.")
        if instance_path:
            if os.path.isfile(instance_path):
                # instance_path is a local path
                with open(instance_path) as fp:
                    test_instance_json = json.load(fp)
            else:
                raise Exception("Error in local file path specified by instance_path.")
        else:
            if instance_id:
                url = self.url + "/test-instances/?id=" + instance_id + "&format=json"
            elif test_id and version:
                url = self.url + "/test-instances/?test_definition_id=" + test_id + "&version=" + version + "&format=json"
            else:
                url = self.url + "/test-instances/?test_alias=" + alias + "&version=" + version + "&format=json"
            test_instance_json = requests.get(url, auth=self.auth)

        if test_instance_json.status_code != 200:
            raise Exception("Error in retrieving test instance. Response = " + str(test_instance_json.content))
        test_instance_json = test_instance_json.json()
        if len(test_instance_json["test_codes"]) == 1:
            return test_instance_json["test_codes"][0]
        else:
            raise Exception("Error in retrieving test instance. Possibly invalid input data.")

    def list_test_instances(self, instance_path="", test_id="", alias=""):
        """Retrieve list of test instances belonging to a specified test.

        This can be retrieved in the following ways (in order of priority):

        1. load from a local JSON file specified via `instance_path`
        2. specify `test_id`
        3. specify `alias` (of the test)

        Parameters
        ----------
        instance_path : string
            Location of local JSON file with test instance metadata.
        test_id : UUID
            System generated unique identifier associated with test definition.
        alias : string
            User-assigned unique identifier associated with test definition.

        Returns
        -------
        dict[]
            Information about the test instances.

        Examples
        --------
        >>> test_instances = test_library.list_test_instances(test_id="8b63f87b-d709-4194-bae1-15329daf3dec")
        """

        if instance_path == "" and test_id == "" and alias == "":
            raise Exception("instance_path or test_id or alias needs to be provided for finding test instances.")
        if instance_path and os.path.isfile(instance_path):
            # instance_path is a local path
            with open(instance_path) as fp:
                test_instances_json = json.load(fp)
        else:
            if test_id:
                url = self.url + "/test-instances/?test_definition_id=" + test_id + "&format=json"
            else:
                url = self.url + "/test-instances/?test_alias=" + alias + "&format=json"
            test_instances_json = requests.get(url, auth=self.auth)

        if test_instances_json.status_code != 200:
            raise Exception("Error in retrieving test instances. Response = " + str(test_instances_json))
        test_instances_json = test_instances_json.json()
        return test_instances_json["test_codes"]

    def add_test_instance(self, test_id="", alias="", repository="", path="", version=""):
        """Register a new test instance.

        This allows to add a new instance to an existing test in the test library.
        The `test_id` needs to be specified as input parameter.

        Parameters
        ----------
        test_id : UUID
            System generated unique identifier associated with test definition.
        alias : string
            User-assigned unique identifier associated with test definition.
        repository : string
            URL of Python package repository (e.g. github).
        path : string
            Python path (not filesystem path) to test source code within Python package.
        version : string
            User-assigned identifier (unique for each test) associated with test instance.

        Returns
        -------
        UUID
            UUID of the test instance that has been created.

        Note
        ----
        * `alias` is not currently implemented in the API; kept for future use.
        * TODO: Either test_id or alias needs to be provided, with test_id taking precedence over alias.

        Examples
        --------
        >>> response = test_library.add_test_instance(test_id="7b63f87b-d709-4194-bae1-15329daf3dec",
                                        repository="https://github.com/appukuttan-shailesh/morphounit.git",
                                        path="morphounit.tests.CellDensityTest",
                                        version="3.0")
        """

        if test_id:
            test_definition_id = test_id    # as needed by API
        instance_data = locals()
        for key in ["self", "test_id"]:
            instance_data.pop(key)

        if test_definition_id == "" and alias == "":
            raise Exception("test_id needs to be provided for finding the model.")
            #raise Exception("test_id or alias needs to be provided for finding the model.")
        elif test_definition_id != "":
            url = self.url + "/test-instances/?format=json"
        else:
            raise Exception("alias is not currently implemented for this feature.")
            #url = self.url + "/test-instances/?alias=" + alias + "&format=json"
        headers = {'Content-type': 'application/json'}
        response = requests.post(url, data=json.dumps([instance_data]),
                                 auth=self.auth, headers=headers)
        if response.status_code == 201:
            return response.content
        else:
            raise Exception("Error in adding test instance. Response = " + str(response))

    def edit_test_instance(self, instance_id="", test_id="", alias="", repository="", path="", version=""):
        """Edit an existing test instance.

        This allows to edit an instance of an existing test in the test library.
        The test instance can be specified in the following ways (in order of priority):

        1. specify `instance_id` corresponding to test instance in test library
        2. specify `test_id` and `version`
        3. specify `alias` (of the test) and `version`

        You cannot edit the test `version` in the latter two cases. To do so,
        you must employ the first option above. You can retrieve the `instance_id`
        via :meth:`get_test_instance`

        Parameters
        ----------
        instance_id : UUID
            System generated unique identifier associated with test instance.
        test_id : UUID
            System generated unique identifier associated with test definition.
        alias : string
            User-assigned unique identifier associated with test definition.
        repository : string
            URL of Python package repository (e.g. github).
        path : string
            Python path (not filesystem path) to test source code within Python package.
        version : string
            User-assigned identifier (unique for each test) associated with test instance.

        Returns
        -------
        UUID
            UUID of the test instance that has was edited.

        Examples
        --------
        >>> response = test_library.edit_test_instance(test_id="7b63f87b-d709-4194-bae1-15329daf3dec",
                                        repository="https://github.com/appukuttan-shailesh/morphounit.git",
                                        path="morphounit.tests.CellDensityTest",
                                        version="4.0")
        """
        if instance_id:
            id = instance_id    # as needed by API
        if test_id:
            test_definition_id = test_id    # as needed by API
        if alias:
            test_alias = alias  # as needed by API
        instance_data = locals()
        for key in ["self", "test_id", "alias"]:
            instance_data.pop(key)

        if instance_id == "" and (test_id == "" or version == "") and (alias == "" or version == ""):
            raise Exception("instance_id or (test_id, version) or (alias, version) needs to be provided for finding a test instance.")
        else:
            url = self.url + "/test-instances/?format=json"

        headers = {'Content-type': 'application/json'}
        response = requests.put(url, data=json.dumps([instance_data]), auth=self.auth, headers=headers)
        if response.status_code == 202:
            return response.content
        else:
            raise Exception("Error in editing test instance. Response = " + str(response.content))

    def _load_reference_data(self, uri):
        # Load the reference data ("observations"). For now this is assumed
        # to be in JSON format, but we should support other data formats.
        parse_result = urlparse(uri)
        datastore = URI_SCHEME_MAP[parse_result.scheme](auth=self.auth)
        observation_data = datastore.load_data(uri)
        return observation_data

    def get_attribute_options(self, param=""):
        """Retrieve valid values for test attributes.

        Will return the list of valid values (where applicable) for various test attributes.
	The following test attributes can be specified:

	* cell_type
	* test_type
	* score_type
	* brain_region
	* data_modalities
	* species

        If an attribute is specified, then only values that correspond to it will be returned,
        else values for all attributes are returned.

        Parameters
        ----------
        param : string, optional
            Attribute of interest

        Returns
        -------
        dict
            Dictionary with key(s) as attribute(s), and value(s) as list of valid options.

        Examples
        --------
        >>> data = test_library.get_attribute_options()
        >>> data = test_library.get_attribute_options("cell_type")
        """

        if param == "":
            param = "all"

        if param in ["cell_type", "test_type", "score_type", "brain_region", "model_type", "data_modalities", "species", "organization", "all"]:
            url = self.url + "/authorizedcollabparameterrest/?python_client=true&parameters="+param+"&format=json"
        else:
            raise Exception("Attribute, if specified, has to be one from: cell_type, test_type, score_type, brain_region, model_type, data_modalities, species, all]")
        data = requests.get(url, auth=self.auth).json()
        return ast.literal_eval(json.dumps(data))

    def get_result(self, result_id="", order=""):
        """Retrieve a test result.

        This allows to retrieve the test result score and other related information.
        The `result_id` needs to be specified as input parameter.

        Parameters
        ----------
        result_id : UUID
            System generated unique identifier associated with result.
        order : string, optional
            Determines how the result should be structured. Valid values are
            "test", "model" or "". Default is "" and provides concise  result summary.

        Returns
        -------
        dict
            Information about the result retrieved.

        Examples
        --------
        >>> result = test_library.get_result(result_id="901ac0f3-2557-4ae3-bb2b-37617312da09")
        >>> result = test_library.get_result(result_id="901ac0f3-2557-4ae3-bb2b-37617312da09", order="test")
        """

        if not result_id:
            raise Exception("result_id needs to be provided for finding a specific result.")
        elif order not in ["test", "model", ""]:
            raise Exception("order needs to be specified as 'test', 'model' or ''.")
        else:
            url = self.url + "/results/?id=" + result_id + "&order=" + order + "&format=json"
        result_json = requests.get(url, auth=self.auth)
        if result_json.status_code != 200:
            raise Exception("Error in retrieving result. Response = " + str(result_json) + ".\nContent = " + result_json.content)
        result_json = result_json.json()
        # Unlike other "get_" methods, we do not return "[key][0]" as the key can vary
        # based on the parameter "order". Retaining this key is potentially useful.
        return result_json

    def list_results(self, order="", **filters):
        """Retrieve test results satisfying specified filters.

        This allows to retrieve a list of test results with their scores
        and other related information.

        Parameters
        ----------
        order : string, optional
            Determines how the result should be structured. Valid values are
            "test", "model" or "". Default is "" and provides concise  result summary.
        **filters : variable length keyword arguments
            To be used to filter the results metadata.

        Returns
        -------
        dict
            Information about the results retrieved.

        Examples
        --------
        >>> results = test_library.list_results()
        >>> results = test_library.list_results(order="test", test_id="7b63f87b-d709-4194-bae1-15329daf3dec")
        >>> results = test_library.list_results(id="901ac0f3-2557-4ae3-bb2b-37617312da09")
        >>> results = test_library.list_results(model_version_id="f32776c7-658f-462f-a944-1daf8765ec97", order="test")
        """

        if order not in ["test", "model", ""]:
            raise Exception("order needs to be specified as 'test', 'model' or ''.")
        else:
            params = locals()["filters"]
            url = self.url + "/results/?" + "order=" + order + "&" + urlencode(params) + "&format=json"
        result_json = requests.get(url, auth=self.auth)
        if result_json.status_code != 200:
            raise Exception("Error in retrieving results. Response = " + str(result_json) + ".\nContent = " + result_json.content)
        result_json = result_json.json()
        return result_json

    def register_result(self, test_result="", data_store=None):
        """Register test result with HBP Validation Results Service.

        The score of a test, along with related output data such as figures,
        can be registered on the validation framework.

        Parameters
        ----------
        test_result : :class:`sciunit.Score`
            a :class:`sciunit.Score` instance returned by `test.judge(model)`
        data_store : :class:`DataStore`
            a :class:`DataStore` instance, for uploading related data generated by the test run, e.g. figures.

        Note
        ----
        Source code for this method still contains comments/suggestions from
        previous client. To be removed or implemented.

        Returns
        -------
        UUID
            UUID of the test result that has been created.

        Examples
        --------
        >>> score = test.judge(model)
        >>> response = test_library.register_result(test_result=score)
        """

        # print("TEST RESULT: {}".format(test_result))
        # print(test_result.model)
        # print(test_result.prediction)
        # print(test_result.observation)
        # print(test_result.score)
        # for file_path in test_result.related_data:
        #     print(file_path)
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
        url = self.url + "/results/?format=json"
        result_json = {
                        "model_version_id": test_result.model.instance_id,
                        "test_code_id": test_result.test.id,
                        "results_storage": results_storage,
                        "score": test_result.score,
                        "passed": None if "passed" not in test_result.related_data else test_result.related_data["passed"],
                        "platform": str(self._get_platform()), # database accepts a string
                        "project": test_result.related_data["project"],
                        "normalized_score": test_result.score
                      }

        # print(result_json)
        headers = {'Content-type': 'application/json'}
        response = requests.post(url, data=json.dumps([result_json]),
                                 auth=self.auth, headers=headers)
        print("Result registered successfully!")
        return response.json()["uuid"][0]

    def _get_platform(self):
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


class ModelCatalog(BaseClient):
    """Client for the HBP Model Catalog.

    The ModelCatalog client manages all actions pertaining to models.
    The following actions can be performed:

    ====================================   ====================================
    Action                                 Method
    ====================================   ====================================
    Get model description                  :meth:`get_model`
    List model descriptions                :meth:`list_models`
    Register new model description         :meth:`register_model`
    Edit model description                 :meth:`edit_model`
    Get valid attribute values             :meth:`get_attribute_options`
    Get model instance                     :meth:`get_model_instance`
    List model instances                   :meth:`list_model_instances`
    Add new model instance                 :meth:`add_model_instance`
    Edit existing model instance           :meth:`edit_model_instance`
    Get figure from model description      :meth:`get_model_image`
    List figures from model description    :meth:`list_model_images`
    Add figure to model description        :meth:`add_model_image`
    Edit existing figure metadata          :meth:`edit_model_image`
    ====================================   ====================================

    Parameters
    ----------
    username : string
        Your HBP Collaboratory username.
    password : string, optional
        Your HBP Collaboratory password; advisable to not enter as plaintext.
        If left empty, you would be prompted for password at run time (safer).
    environment : string, optional
        Used to indicate whether being used for development/testing purposes.
        Set as `production` as default for using the production system,
        which is appropriate for most users. When set to `dev`, it uses the
        `development` system. Other environments, if required, should be defined
        inside a json file named `config.json` in the working directory. Example:

        .. code-block:: JSON

            {
                "prod": {
                    "url": "https://validation-v1.brainsimulation.eu",
                    "client_id": "3ae21f28-0302-4d28-8581-15853ad6107d"
                },
                "dev_test": {
                    "url": "https://validation-dev.brainsimulation.eu",
                    "client_id": "90c719e0-29ce-43a2-9c53-15cb314c2d0b"
                }
            }

    Examples
    --------
    Instantiate an instance of the ModelCatalog class

    >>> model_catalog = ModelCatalog(hbp_username)
    """

    def get_model(self, model_id="", alias="", instances=True, images=True):
        """Retrieve a specific model description by its model_id or alias.

        A specific model description can be retrieved from the model catalog
        in the following ways (in order of priority):

        1. specify the `model_id`
        2. specify the `alias` (of the model)

        Parameters
        ----------
        model_id : UUID
            System generated unique identifier associated with model description.
        alias : string
            User-assigned unique identifier associated with model description.
        instances : boolean, optional
            Set to False if you wish to omit the details of the model instances; default True.
        images : boolean, optional
            Set to False if you wish to omit the details of the model images (figures); default True.

        Returns
        -------
        dict
            Entire model description as a JSON object.

        Examples
        --------
        >>> model = model_catalog.get_model(model_id="8c7cb9f6-e380-452c-9e98-e77254b088c5")
        >>> model = model_catalog.get_model(alias="B1")
        """

        if model_id == "" and alias == "":
            raise Exception("Model ID or alias needs to be provided for finding a model.")
        elif model_id != "":
            url = self.url + "/models/?id=" + model_id + "&format=json"
        else:
            url = self.url + "/models/?alias=" + alias + "&format=json"

        model_json = requests.get(url, auth=self.auth)
        if model_json.status_code != 200:
            raise Exception("Error in retrieving model. Response = " + str(model_json))
        model_json = model_json.json()

        if len(model_json["models"]) == 1:
            if instances == False:
                model_json["models"][0].pop("instances")
            if images == False:
                model_json["models"][0].pop("images")
            return model_json["models"][0]
        else:
            raise Exception("Error in retrieving model description. Possibly invalid input data.")

    def list_models(self, **filters):
        """Retrieve list of model descriptions satisfying specified filters.

        The filters may specify one or more attributes that belong
        to a model description. The following model attributes can be specified:

        * app_id
        * name
        * alias
        * author
        * organization
        * species
        * brain_region
        * cell_type
        * model_type

        Parameters
        ----------
        **filters : variable length keyword arguments
            To be used to filter model descriptions from the model catalog.

        Returns
        -------
        list
            List of model descriptions satisfying specified filters.

        Examples
        --------
        >>> models = model_catalog.list_models()
        >>> models = model_catalog.list_models(app_id="39968")
        >>> models = model_catalog.list_models(cell_type="Pyramidal Cell", brain_region="Hippocampus")
        """

        params = locals()["filters"]
        url = self.url + "/models/?"+urlencode(params)+"&format=json"
        models = requests.get(url, auth=self.auth).json()
        return models["models"]

    def register_model(self, app_id="", name="", alias=None, author="", organization="", private=False,
                       species="", brain_region="", cell_type="", model_type="", description="",
                       instances=[], images=[]):
        """Register a new model in the model catalog.

        This allows you to add a new model to the model catalog. Model instances
        and/or images (figures) can optionally be specified at the time of model
        creation, or can be added later individually.

        Parameters
        ----------
        app_id : string
            Specifies the ID of the host model catalog app on the HBP Collaboratory.
            (the model would belong to this app)
        name : string
            Name of the model description to be created.
        alias : string, optional
            User-assigned unique identifier to be associated with model description.
        author : string
            Name of person creating the model description.
        organization : string, optional
            Option to tag model with organization info.
        private : boolean
            Set visibility of model description. If True, model would only be seen in host app (where created). Default False.
        species : string
            The species for which the model is developed.
        brain_region : string
            The brain region for which the model is developed.
        cell_type : string
            The type of cell for which the model is developed.
        model_type : string
            Specifies the type of the model.
        description : string
            Provides a description of the model.
        instances : list, optional
            Specify a list of instances (versions) of the model.
        images : list, optional
            Specify a list of images (figures) to be linked to the model.

        Returns
        -------
        UUID
            (Verify!) UUID of the model description that has been created.

        Examples
        --------
        (without instances and images)

        >>> model = model_catalog.register_model(app_id="39968", name="Test Model - B2",
                        alias="Model-B2", author="Shailesh Appukuttan", organization="HBP-SP6",
                        private="False", cell_type="Granule Cell", model_type="Single Cell",
                        brain_region="Basal Ganglia", species="Mouse (Mus musculus)",
                        description="This is a test entry")

        (with instances and images)

        >>> model = model_catalog.register_model(app_id="39968", name="Client Test - C2",
                        alias="C2", author="Shailesh Appukuttan", organization="HBP-SP6",
                        private=False, cell_type="Granule Cell", model_type="Single Cell",
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

        values = self.get_attribute_options()

        if cell_type not in values["cell_type"]:
            raise Exception("cell_type = '" +cell_type+"' is invalid.\nValue has to be one of these: " + str(values["cell_type"]))
        if model_type not in values["model_type"]:
            raise Exception("model_type = '" +model_type+"' is invalid.\nValue has to be one of these: " + str(values["model_type"]))
        if brain_region not in values["brain_region"]:
            raise Exception("brain_region = '" +brain_region+"' is invalid.\nValue has to be one of these: " + str(values["brain_region"]))
        if species not in values["species"]:
            raise Exception("species = '" +species+"' is invalid.\nValue has to be one of these: " + str(values["species"]))
        if organization not in values["organization"]:
            raise Exception("organization = '" +organization+"' is invalid.\nValue has to be one of these: " + str(values["organization"]+[""]))

        if private not in [True, False]:
            raise Exception("Model's 'private' attribute should be specified as True / False. Default value is False.")
        else:
            private = str(private)

        model_data = locals()
        for key in ["self", "app_id", "instances", "images"]:
            model_data.pop(key)

        url = self.url + "/models/?app_id="+app_id+"&format=json"
        model_json = {
                        "model": model_data,
                        "model_instance":instances,
                        "model_image":images
                     }
        headers = {'Content-type': 'application/json'}
        response = requests.post(url, data=json.dumps(model_json),
                                 auth=self.auth, headers=headers)
        if response.status_code == 201:
            return response.json()
        else:
            raise Exception("Error in adding model. Response = " + str(response.json()))

    def edit_model(self, model_id="", app_id="", name="", alias=None, author="", organization="", private="False",
                   cell_type="", model_type="", brain_region="", species="", description=""):
        """Edit an existing model on the model catalog.

        This allows you to edit an new model to the model catalog.
        The `model_id` must be provided. Any of the other parameters maybe updated.

        Parameters
        ----------
        model_id : UUID
            System generated unique identifier associated with model description.
        app_id : string
            Specifies the ID of the host model catalog app on the HBP Collaboratory.
            (the model would belong to this app)
        name : string
            Name of the model description to be created.
        alias : string, optional
            User-assigned unique identifier to be associated with model description.
        author : string
            Name of person creating the model description.
        organization : string, optional
            Option to tag model with organization info.
        private : boolean
            Set visibility of model description. If True, model would only be seen in host app (where created). Default False.
        species : string
            The species for which the model is developed.
        brain_region : string
            The brain region for which the model is developed.
        cell_type : string
            The type of cell for which the model is developed.
        model_type : string
            Specifies the type of the model.
        description : string
            Provides a description of the model.
        instances : list, optional
            Specify a list of instances (versions) of the model.
        images : list, optional
            Specify a list of images (figures) to be linked to the model.

        Note
        ----
        Does not allow editing details of model instances and images (figures).
        Will be implemented later, if required.

        Returns
        -------
        UUID
            (Verify!) UUID of the model description that has been edited.

        Examples
        --------
        >>> model = model_catalog.edit_model(app_id="39968", name="Test Model - B2",
                        model_id="8c7cb9f6-e380-452c-9e98-e77254b088c5",
                        alias="Model-B2", author="Shailesh Appukuttan", organization="HBP-SP6",
                        private=False, cell_type="Granule Cell", model_type="Single Cell",
                        brain_region="Basal Ganglia", species="Mouse (Mus musculus)",
                        description="This is a test entry")
        """

        values = self.get_attribute_options()

        if cell_type not in values["cell_type"]:
            raise Exception("cell_type = '" +cell_type+"' is invalid.\nValue has to be one of these: " + str(values["cell_type"]))
        if model_type not in values["model_type"]:
            raise Exception("model_type = '" +model_type+"' is invalid.\nValue has to be one of these: " + str(values["model_type"]))
        if brain_region not in values["brain_region"]:
            raise Exception("brain_region = '" +brain_region+"' is invalid.\nValue has to be one of these: " + str(values["brain_region"]))
        if species not in values["species"]:
            raise Exception("species = '" +species+"' is invalid.\nValue has to be one of these: " + str(values["species"]))
        if organization not in values["organization"]:
            raise Exception("organization = '" +organization+"' is invalid.\nValue has to be one of these: " + str(values["organization"]))

        if private not in [True, False]:
            raise Exception("Model's 'private' attribute should be specified as True / False. Default value is False.")
        else:
            private = str(private)

        id = model_id   # as needed by API
        model_data = locals()
        for key in ["self", "app_id", "model_id"]:
            model_data.pop(key)

        url = self.url + "/models/?app_id="+app_id+"&format=json"
        model_json = {
                        "models": [model_data]
                     }
        headers = {'Content-type': 'application/json'}
        response = requests.put(url, data=json.dumps(model_json),
                                 auth=self.auth, headers=headers)
        if response.status_code == 202:
            return response.json()
        else:
            raise Exception("Error in updating model. Response = " + str(response.json()))

    def get_attribute_options(self, param=""):
        """Retrieve valid values for attributes.

        Will return the list of valid values (where applicable) for various attributes.
    	The following model attributes can be specified:

    	* cell_type
    	* brain_region
    	* model_type
    	* species
    	* organization

        If an attribute is specified then, only values that correspond to it will be returned,
        else values for all attributes are returned.

        Parameters
        ----------
        param : string, optional
            Attribute of interest

        Returns
        -------
        dict
            Dictionary with key(s) as attribute(s), and value(s) as list of valid options.

        Examples
        --------
        >>> data = model_catalog.get_attribute_options()
        >>> data = model_catalog.get_attribute_options("cell_type")
        """

        if param == "":
            param = "all"

        if param in ["cell_type", "test_type", "score_type", "brain_region", "model_type", "data_modalities", "species", "organization", "all"]:
            url = self.url + "/authorizedcollabparameterrest/?python_client=true&parameters="+param+"&format=json"
        else:
            raise Exception("Attribute, if specified, has to be one from: cell_type, test_type, score_type, brain_region, model_type, data_modalities, species, all]")
        data = requests.get(url, auth=self.auth).json()
        return ast.literal_eval(json.dumps(data))

    def get_model_instance(self, instance_path="", instance_id="", model_id="", alias="", version=""):
        """Retrieve an existing model instance.

        A specific model instance can be retrieved
        in the following ways (in order of priority):

        1. load from a local JSON file specified via `instance_path`
        2. specify `instance_id` corresponding to model instance in model catalog
        3. specify `model_id` and `version`
        4. specify `alias` (of the model) and `version`

        Parameters
        ----------
        instance_path : string
            Location of local JSON file with model instance metadata.
        instance_id : UUID
            System generated unique identifier associated with model instance.
        model_id : UUID
            System generated unique identifier associated with model description.
        alias : string
            User-assigned unique identifier associated with model description.
        version : string
            User-assigned identifier (unique for each model) associated with model instance.

        Returns
        -------
        dict
            Information about the model instance.

        Examples
        --------
        >>> model_instance = model_catalog.get_model_instance(model_id="a035f2b2-fe2e-42fd-82e2-4173a304263b")
        """

        if instance_path == "" and instance_id == "" and (model_id == "" or version == "") and (alias == "" or version == ""):
            raise Exception("instance_path or instance_id or (model_id, version) or (alias, version) needs to be provided for finding a model instance.")
        if instance_path and os.path.isfile(instance_path):
            # instance_path is a local path
            with open(instance_path) as fp:
                model_instance_json = json.load(fp)
        else:
            if instance_id:
                url = self.url + "/model-instances/?id=" + instance_id + "&format=json"
            elif model_id and version:
                url = self.url + "/model-instances/?model_id=" + model_id + "&version=" + version + "&format=json"
            else:
                url = self.url + "/model-instances/?model_alias=" + alias + "&version=" + version + "&format=json"
            model_instance_json = requests.get(url, auth=self.auth)
        if model_instance_json.status_code != 200:
            raise Exception("Error in retrieving model instance. Response = " + str(model_instance_json))
        model_instance_json = model_instance_json.json()
        if len(model_instance_json["instances"]) == 1:
            return model_instance_json["instances"][0]
        else:
            raise Exception("Error in retrieving model instance. Possibly invalid input data.")

    def list_model_instances(self, instance_path="", model_id="", alias=""):
        """Retrieve list of model instances belonging to a specified model.

        This can be retrieved in the following ways (in order of priority):

        1. load from a local JSON file specified via `instance_path`
        2. specify `model_id`
        3. specify `alias` (of the model)

        Parameters
        ----------
        instance_path : string
            Location of local JSON file with model instance metadata.
        model_id : UUID
            System generated unique identifier associated with model description.
        alias : string
            User-assigned unique identifier associated with model description.

        Returns
        -------
        list
            List of dicts containing information about the model instances.

        Examples
        --------
        >>> model_instances = model_catalog.list_model_instances(alias="alias2")
        """

        if instance_path == "" and model_id == "" and alias == "":
            raise Exception("instance_path or model_id or alias needs to be provided for finding model instances.")
        if instance_path and os.path.isfile(instance_path):
            # instance_path is a local path
            with open(instance_path) as fp:
                model_instances_json = json.load(fp)
        else:
            if model_id:
                url = self.url + "/model-instances/?model_id=" + model_id + "&format=json"
            else:
                url = self.url + "/model-instances/?model_alias=" + alias + "&format=json"
            model_instances_json = requests.get(url, auth=self.auth)
        if model_instances_json.status_code != 200:
            raise Exception("Error in retrieving model instances. Response = " + str(model_instances_json))
        model_instances_json = model_instances_json.json()
        return model_instances_json["instances"]

    def add_model_instance(self, model_id="", alias="", source="", version="", parameters=""):
        """Register a new model instance.

        This allows to add a new instance of an existing model in the model catalog.
        The `model_id` needs to be specified as input parameter.

        Parameters
        ----------
        model_id : UUID
            System generated unique identifier associated with model description.
        alias : string
            User-assigned unique identifier associated with model description.
        source : string
            Path to model source code repository (e.g. github).
        version : string
            User-assigned identifier (unique for each model) associated with model instance.
        parameters : string
            Any additional parameters to be submitted to model at runtime.

        Returns
        -------
        UUID
            UUID of the model instance that has been created.

        Note
        ----
        * `alias` is not currently implemented in the API; kept for future use.
        * TODO: Either model_id or alias needs to be provided, with model_id taking precedence over alias.

        Examples
        --------
        >>> instance_id = model_catalog.add_model_instance(model_id="196b89a3-e672-4b96-8739-748ba3850254",
                                                  source="https://www.abcde.com",
                                                  version="1.0",
                                                  parameters="")
        """

        instance_data = locals()
        instance_data.pop("self")

        if model_id == "" and alias == "":
            raise Exception("Model ID needs to be provided for finding the model.")
            #raise Exception("Model ID or alias needs to be provided for finding the model.")
        elif model_id != "":
            url = self.url + "/model-instances/?format=json"
        else:
            raise Exception("alias is not currently implemented for this feature.")
            #url = self.url + "/model-instances/?alias=" + alias + "&format=json"
        headers = {'Content-type': 'application/json'}
        response = requests.post(url, data=json.dumps([instance_data]),
                                 auth=self.auth, headers=headers)
        if response.status_code == 201:
            return response.json()
        else:
            raise Exception("Error in adding model instance. Response = " + str(response.json()))

    def edit_model_instance(self, instance_id="", model_id="", alias="", source="", version="", parameters=""):
        """Edit an existing model instance.

        This allows to edit an instance of an existing model in the model catalog.
        The model instance can be specified in the following ways (in order of priority):

        1. specify `instance_id` corresponding to model instance in model catalog
        2. specify `model_id` and `version`
        3. specify `alias` (of the model) and `version`

        You cannot edit the model `version` in the latter two cases. To do so,
        you must employ the first option above. You can retrieve the `instance_id`
        via :meth:`get_model_instance`

        Parameters
        ----------
        instance_id : UUID
            System generated unique identifier associated with model instance.
        model_id : UUID
            System generated unique identifier associated with model description.
        alias : string
            User-assigned unique identifier associated with model description.
        source : string
            Path to model source code repository (e.g. github).
        version : string
            User-assigned identifier (unique for each model) associated with model instance.
        parameters : string
            Any additional parameters to be submitted to model at runtime.

        Returns
        -------
        UUID
            UUID of the model instance that has been created.

        Examples
        --------
        >>> instance_id = model_catalog.edit_model_instance(instance_id="fd1ab546-80f7-4912-9434-3c62af87bc77",
                                                model_id="196b89a3-e672-4b96-8739-748ba3850254",
                                                source="https://www.abcde.com",
                                                version="10.0",
                                                parameters="")
        """

        if instance_id:
            id = instance_id    # as needed by API
        if alias:
            model_alias = alias # as needed by API
        instance_data = locals()
        for key in ["self", "instance_id", "alias"]:
            instance_data.pop(key)

        if instance_id == "" and (model_id == "" or version == "") and (alias == "" or version == ""):
            raise Exception("instance_id or (model_id, version) or (alias, version) needs to be provided for finding a model instance.")
        else:
            url = self.url + "/model-instances/?format=json"

        headers = {'Content-type': 'application/json'}
        response = requests.put(url, data=json.dumps([instance_data]), auth=self.auth, headers=headers)
        if response.status_code == 202:
            return response.json()
        else:
            raise Exception("Error in editing model instance. Response = " + str(response.json()))

    def get_model_image(self, image_id=""):
        """Retrieve image info from a model description.

        This allows to retrieve image (figure) info from the model catalog.
        The `image_id` needs to be specified as input parameter.

        Parameters
        ----------
        image_id : UUID
            System generated unique identifier associated with image (figure).

        Returns
        -------
        dict
            Information about the image (figure) retrieved.

        Examples
        --------
        >>> model_image = model_catalog.get_model_image(image_id="2b45e7d4-a7a1-4a31-a287-aee7072e3e75")
        """

        if not image_id:
            raise Exception("image_id needs to be provided for finding a specific model image (figure).")
        else:
            url = self.url + "/images/?id=" + image_id + "&format=json"
        model_image_json = requests.get(url, auth=self.auth)
        if model_image_json.status_code != 200:
            raise Exception("Error in retrieving model images (figures). Response = " + str(model_image_json))
        model_image_json = model_image_json.json()
        if len(model_image_json["images"]) == 1:
            return model_image_json["images"][0]
        else:
            raise Exception("Error in retrieving model image. Possibly invalid input data.")
        return model_image_json["images"][0]

    def list_model_images(self, model_id="", alias=""):
        """Retrieve all images (figures) associated with a model.

        This can be retrieved in the following ways (in order of priority):
        1. specify `model_id`
        2. specify `alias` (of the model)

        Parameters
        ----------
        model_id : UUID
            System generated unique identifier associated with model description.
        alias : string
            User-assigned unique identifier associated with model description.

        Returns
        -------
        list
            List of dicts containing information about the model images (figures).

        Examples
        --------
        >>> model_images = model_catalog.list_model_images(model_id="196b89a3-e672-4b96-8739-748ba3850254")
        """

        if model_id == "" and alias == "":
            raise Exception("model_id or alias needs to be provided for finding model images.")
        elif model_id:
            url = self.url + "/images/?model_id=" + model_id + "&format=json"
        else:
            url = self.url + "/images/?model_alias=" + alias + "&format=json"
        model_images_json = requests.get(url, auth=self.auth)
        if model_images_json.status_code != 200:
            raise Exception("Error in retrieving model images (figures). Response = " + str(model_images_json.content))
        model_images_json = model_images_json.json()
        return model_images_json["images"]

    def add_model_image(self, model_id="", alias="", url="", caption=""):
        """Add a new image (figure) to a model description.

        This allows to add a new image (figure) to an existing model in the model catalog.
        The `model_id` needs to be specified as input parameter.

        Parameters
        ----------
        model_id : UUID
            System generated unique identifier associated with model description.
        alias : string
            User-assigned unique identifier associated with model description.
        url : string
            Url of image (figure) to be added.
        caption : string
            Caption to be associated with the image (figure).

        Returns
        -------
        UUID
            UUID of the image (figure) that was added.

        Note
        ----
        * `alias` is not currently implemented in the API; kept for future use.
        * TODO: Either model_id or alias needs to be provided, with model_id taking precedence over alias.
        * TODO: Allow image (figure) to be located locally

        Examples
        --------
        >>> image_id = model_catalog.add_model_image(model_id="196b89a3-e672-4b96-8739-748ba3850254",
                                               url="http://www.neuron.yale.edu/neuron/sites/default/themes/xchameleon/logo.png",
                                               caption="NEURON Logo")
        """

        image_data = locals()
        image_data.pop("self")
        image_data.pop("alias")

        if model_id == "" and alias == "":
            raise Exception("Model ID needs to be provided for finding the model.")
            #raise Exception("Model ID or alias needs to be provided for finding the model.")
        elif model_id != "":
            url = self.url + "/images/?format=json"
        else:
            raise Exception("alias is not currently implemented for this feature.")
            #url = self.url + "/images/?alias=" + alias + "&format=json"
        headers = {'Content-type': 'application/json'}
        response = requests.post(url, data=json.dumps([image_data]),
                                 auth=self.auth, headers=headers)
        if response.status_code == 201:
            return response.json()
        else:
            raise Exception("Error in adding image (figure). Response = " + str(response.json()))

    def edit_model_image(self, image_id="", url="", caption=""):
        """Edit an existing image (figure) metadata.

        This allows to edit the metadata of an image (figure) in the model catalog.
        The `image_id` needs to be specified as input parameter.

        Parameters
        ----------
        image_id : UUID
            System generated unique identifier associated with image (figure).

        Returns
        -------
        UUID
            UUID of the image (figure) that was edited.

        Examples
        --------
        >>> image_id = model_catalog.edit_model_image(image_id="2b45e7d4-a7a1-4a31-a287-aee7072e3e75", caption = "Some Logo", url="http://www.somesite.com/logo.png")
        """

        id = image_id
        image_data = locals()
        for key in ["self", "image_id"]:
            image_data.pop(key)

        if image_id == "":
            raise Exception("Image ID needs to be provided for finding the image (figure).")
        else:
            url = self.url + "/images/?id=" + image_id + "&format=json"
        headers = {'Content-type': 'application/json'}
        response = requests.put(url, data=json.dumps([image_data]), auth=self.auth, headers=headers)
        if response.status_code == 202:
            return response.json()
        else:
            raise Exception("Error in adding image (figure). Response = " + str(response.json()))


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
