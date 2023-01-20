"""
A Python package for working with the EBRAINS / Human Brain Project Model Validation Framework.

Andrew Davison and Shailesh Appukuttan, CNRS, 2017-2022

License: BSD 3-clause, see LICENSE.txt

"""

import os
import re
import getpass
import json

import platform
import socket
from importlib import import_module
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlparse, urlunparse, parse_qs, urljoin, urlencode, quote

import requests
from requests.auth import AuthBase
from .datastores import URI_SCHEME_MAP
from nameparser import HumanName


# check if running within Jupyter notebook inside Collab v2
try:
    from clb_nb_utils import oauth

    have_collab_token_handler = True
except ImportError:
    have_collab_token_handler = False


__version__ = "0.8.1"


TOKENFILE = os.path.expanduser("~/.hbptoken")


class ResponseError(Exception):
    pass


def handle_response_error(message, response):
    try:
        structured_error_message = response.json()
    except (json.JSONDecodeError, requests.JSONDecodeError):
        structured_error_message = None
    if structured_error_message:
        response_text = str(structured_error_message)  # temporary, to be improved
    else:
        response_text = response.text
    full_message = "{}. Response = {}".format(message, response_text)
    raise ResponseError(full_message)


def renameNestedJSONKey(iterable, old_key, new_key):
    if isinstance(iterable, list):
        return [renameNestedJSONKey(item, old_key, new_key) for item in iterable]
    if isinstance(iterable, dict):
        for key in list(iterable.keys()):
            if key == old_key:
                iterable[new_key] = iterable.pop(key)
    return iterable


class HBPAuth(AuthBase):
    """Attaches OIDC Bearer Authentication to the given Request object."""

    def __init__(self, token):
        # setup any auth-related data here
        self.token = token

    def __call__(self, r):
        # modify and return the request
        r.headers["Authorization"] = "Bearer " + self.token
        return r


class BaseClient(object):
    """
    Base class that handles EBRAINS authentication
    """

    # Note: Could possibly simplify the code later

    __test__ = False

    def __init__(
        self, username=None, password=None, environment="production", token=None
    ):
        self.username = username
        self.verify = True
        self.environment = environment
        self.token = token
        if environment == "production":
            self.url = "https://validation.brainsimulation.eu"
        elif environment == "staging":
            self.url = "https://validation-staging.brainsimulation.eu"
        elif environment == "dev":
            self.url = "http://localhost:8000"
        else:
            if os.path.isfile("config.json") and os.access("config.json", os.R_OK):
                with open("config.json") as config_file:
                    config = json.load(config_file)
                    if environment in config:
                        if "url" in config[environment]:
                            self.url = config[environment]["url"]
                            self.verify = config[environment].get("verify_ssl", True)
                        else:
                            raise KeyError(
                                "Cannot load environment info: config.json does not contain sufficient info for environment = {}".format(
                                    environment
                                )
                            )
                    else:
                        raise KeyError(
                            "Cannot load environment info: config.json does not contain environment = {}".format(
                                environment
                            )
                        )
            else:
                raise IOError(
                    "Cannot load environment info: config.json not found in the current directory."
                )
        if self.token:
            pass
        elif password is None:
            self.token = None
            if have_collab_token_handler:
                # if are we running in a Jupyter notebook within the Collaboratory
                # the token is already available
                self.token = oauth.get_token()
            elif os.path.exists(TOKENFILE):
                if username:
                    # check for a stored token
                    with open(TOKENFILE) as fp:
                        data = json.load(fp).get(username, None)
                        if data and "access_token" in data:
                            self.token = data["access_token"]
                            if not self._check_token_valid():
                                print(
                                    "EBRAINS authentication token is invalid or has expired. Will need to re-authenticate."
                                )
                                self.token = None
                        else:
                            print(
                                f"EBRAINS authentication token file not having required JSON data. data = {data}"
                            )
                else:
                    print("Authentication token file found, but you have not provided your username.")
            else:
                print("EBRAINS authentication token file not found locally.")

            if self.token is None:
                if not username:
                    print("\n==============================================")
                    print("Please enter your EBRAINS username.")
                    username = input("EBRAINS Username: ")

                password = os.environ.get("EBRAINS_PASS")
                if password is not None:
                    try:
                        self._hbp_auth(username, password)
                    except Exception:
                        print(
                            "Authentication Failure. Possibly incorrect EBRAINS password saved in environment variable 'EBRAINS_PASS'."
                        )
                if not hasattr(self, "config"):
                    try:
                        # prompt for password
                        print("Please enter your EBRAINS password: ")
                        password = getpass.getpass()
                        self._hbp_auth(username, password)
                    except Exception:
                        print(
                            "Authentication Failure! Password entered is possibly incorrect."
                        )
                        raise
                with open(TOKENFILE, "w") as fp:
                    json.dump({username: {"access_token": self.config["access_token"]}}, fp)
                os.chmod(TOKENFILE, 0o600)
        else:
            try:
                self._hbp_auth(username, password)
            except Exception:
                print("Authentication Failure! Password entered is possibly incorrect.")
                raise
            with open(TOKENFILE, "w") as fp:
                json.dump({username: {"access_token": self.config["access_token"]}}, fp)
            os.chmod(TOKENFILE, 0o600)
        self.auth = HBPAuth(self.token)

    def _check_token_valid(self):
        url = "https://iam.ebrains.eu/auth/realms/hbp/protocol/openid-connect/userinfo"
        data = requests.get(url, auth=HBPAuth(self.token), verify=self.verify)
        if data.status_code == 200:
            return True
        else:
            raise Exception()
            return False

    def _format_people_name(self, names):
        # converts a string of people names separated by semi-colons
        # into a list of dicts. Each list element will correspond to a
        # single person, and consist of keys `given_name` and `family_name`

        # list input - multiple persons
        if isinstance(names, list):
            if all("given_name" in entry.keys() for entry in names) and all(
                "family_name" in entry.keys() for entry in names
            ):
                return names
            else:
                raise ValueError(
                    "Name input as list but without required keys: given_name, family_name"
                )

        # dict input - single person
        if isinstance(names, dict):
            if "given_name" in names.keys() and "family_name" in names.keys():
                return [names]
            else:
                raise ValueError(
                    "Name input as dict but without required keys: given_name, family_name"
                )

        # string input - multiple persons
        output_names_list = []
        if names:
            input_names_list = names.split(";")
            for name in input_names_list:
                parsed_name = HumanName(name.strip())
                output_names_list.append(
                    {
                        "given_name": " ".join(
                            filter(None, [parsed_name.first, parsed_name.middle])
                        ),
                        "family_name": parsed_name.last,
                    }
                )
        else:
            output_names_list.append({"given_name": "", "family_name": ""})
        return output_names_list

    # def exists_in_collab_else_create(self, collab_id):
    #     #  TODO: needs to be updated for Collab v2
    #     """
    #     Checks with the hbp-collab-service if the Model Catalog / Validation Framework app
    #     exists inside the current collab (if run inside the Collaboratory), or Collab ID
    #     specified by the user (when run externally).
    #     """
    #     try:
    #         url = "https://services.humanbrainproject.eu/collab/v0/collab/"+str(collab_id)+"/nav/all/"
    #         response = requests.get(url, auth=HBPAuth(self.token), verify=self.verify)
    #     except ValueError:
    #         print("Error contacting hbp-collab-service for Collab info. Possibly invalid Collab ID: {}".format(collab_id))

    #     for app_item in response.json():
    #         if app_item["app_id"] == str(self.app_id):
    #             app_nav_id = app_item["id"]
    #             print ("Using existing {} app in this Collab. App nav ID: {}".format(self.app_name,app_nav_id))
    #             break
    #     else:
    #         url = "https://services.humanbrainproject.eu/collab/v0/collab/"+str(collab_id)+"/nav/root/"
    #         collab_root = requests.get(url, auth=HBPAuth(self.token), verify=self.verify).json()["id"]
    #         import uuid
    #         app_info = {"app_id": self.app_id,
    #                     "context": str(uuid.uuid4()),
    #                     "name": self.app_name,
    #                     "order_index": "-1",
    #                     "parent": collab_root,
    #                     "type": "IT"}
    #         url = "https://services.humanbrainproject.eu/collab/v0/collab/"+str(collab_id)+"/nav/"
    #         headers = {'Content-type': 'application/json'}
    #         response = requests.post(url, data=json.dumps(app_info),
    #                                  auth=HBPAuth(self.token), headers=headers,
    #                                  verify=self.verify)
    #         app_nav_id = response.json()["id"]
    #         print ("New {} app created in this Collab. App nav ID: {}".format(self.app_name,app_nav_id))
    #     return app_nav_id

    # def _configure_app_collab(self, config_data):
    #     #  TODO: needs to be updated for Collab v2
    #     """
    #     Used to configure the apps inside a Collab. Example `config_data`:
    #         {
    #            "config":{
    #               "app_id":68489,
    #               "app_type":"model_catalog",
    #               "brain_region":"",
    #               "cell_type":"",
    #               "collab_id":"model-validation",
    #               "recording_modality":"",
    #               "model_scope":"",
    #               "abstraction_level":"",
    #               "organization":"",
    #               "species":"",
    #               "test_type":""
    #            },
    #            "only_if_new":False,
    #            "url":"https://validation-v1.brainsimulation.eu/parametersconfiguration-model-catalog/parametersconfigurationrest/"
    #         }
    #     """
    #     if not config_data["config"]["collab_id"]:
    #         raise ValueError("`collab_id` cannot be empty!")
    #     if not config_data["config"]["app_id"]:
    #         raise ValueError("`app_id` cannot be empty!")
    #     # check if the app has previously been configured: decide POST or PUT
    #     response = requests.get(config_data["url"]+"?app_id="+str(config_data["config"]["app_id"]), auth=self.auth, verify=self.verify)
    #     headers = {'Content-type': 'application/json'}
    #     config_data["config"]["id"] = config_data["config"]["app_id"]
    #     app_id = config_data["config"].pop("app_id")
    #     if not response.json()["param"]:
    #         response = requests.post(config_data["url"], data=json.dumps(config_data["config"]),
    #                                  auth=self.auth, headers=headers,
    #                                  verify=self.verify)
    #         if response.status_code == 201:
    #             print("New app has beeen created and sucessfully configured!")
    #         else:
    #             print("Error! App could not be configured. Response = " + str(response.content))
    #     else:
    #         if not config_data["only_if_new"]:
    #             response = requests.put(config_data["url"], data=json.dumps(config_data["config"]),
    #                                     auth=self.auth, headers=headers,
    #                                     verify=self.verify)
    #             if response.status_code == 202:
    #                 print("Existing app has beeen sucessfully reconfigured!")
    #             else:
    #                 print("Error! App could not be reconfigured. Response = " + str(response.content))

    def _hbp_auth(self, username, password):
        """
        EBRAINS authentication
        """
        redirect_uri = self.url + "/auth"
        session = requests.Session()
        # log-in page of model validation service
        r_login = session.get(self.url + "/login", allow_redirects=False)
        if r_login.status_code != 302:
            raise Exception(
                "Something went wrong. Status code {} from login, expected 302".format(
                    r_login.status_code
                )
            )
        # redirects to EBRAINS IAM log-in page
        iam_auth_url = r_login.headers.get("location")
        r_iam1 = session.get(iam_auth_url, allow_redirects=False)
        if r_iam1.status_code != 200:
            raise Exception(
                "Something went wrong loading EBRAINS log-in page. Status code {}".format(
                    r_iam1.status_code
                )
            )
        # fill-in and submit form
        match = re.search(r"action=\"(?P<url>[^\"]+)\"", r_iam1.text)
        if not match:
            raise Exception("Received an unexpected page")
        iam_authenticate_url = match["url"].replace("&amp;", "&")
        r_iam2 = session.post(
            iam_authenticate_url,
            data={"username": username, "password": password},
            headers={
                "Referer": iam_auth_url,
                "Host": "iam.ebrains.eu",
                "Origin": "https://iam.ebrains.eu",
            },
            allow_redirects=False,
        )
        if r_iam2.status_code != 302:
            if r_iam2.status_code == 200 and "Invalid username or password" in r_iam2.text:
                raise Exception("Invalid username or password")

            raise Exception(
                "Something went wrong. Status code {} from authenticate, expected 302".format(
                    r_iam2.status_code
                )
            )
        # redirects either to "grant permissions" page or back to model validation service
        if r_iam2.headers["Location"].startswith("https://iam.ebrains.eu"):
            raise Exception(
                "Before you can use this Python client, you must grant it permission "
                "to access certain information from your EBRAINS account. "
                f"Please visit {self.url}/login in a web browser and click 'Yes' "
                "to grant the required privileges, then try again."
            )
        r_val = session.get(r_iam2.headers["Location"])
        if r_val.status_code != 200:
            raise Exception(
                "Something went wrong. Status code {} from final authentication step".format(
                    r_val.status_code
                )
            )
        config = r_val.json()
        self.token = config["access_token"]
        self.config = config

    @classmethod
    def from_existing(cls, client):
        """Used to easily create a TestLibrary if you already have a ModelCatalog, or vice versa"""
        obj = cls.__new__(cls)
        for attrname in ("username", "url", "token", "verify", "auth", "environment"):
            setattr(obj, attrname, getattr(client, attrname))
        obj._set_app_info()
        return obj

    def _get_attribute_options(self, param, valid_params):
        if param in ("", "all"):
            url = self.url + "/vocab/"
        elif param in valid_params:
            url = self.url + "/vocab/" + param.replace("_", "-") + "/"
        else:
            raise Exception(
                "Specified attribute '{}' is invalid. Valid attributes: {}".format(
                    param, valid_params
                )
            )
        return requests.get(url, auth=self.auth, verify=self.verify).json()

    def api_info(self):
        return requests.get(self.url).json()


class TestLibrary(BaseClient):
    """Client for the EBRAINS Validation Test library.

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
        Your EBRAINS Collaboratory username. Not needed in Jupyter notebooks within the EBRAINS Collaboratory.
    password : string, optional
        Your EBRAINS Collaboratory password; advisable to not enter as plaintext.
        If left empty, you would be prompted for password at run time (safer).
        Not needed in Jupyter notebooks within the EBRAINS Collaboratory.
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
                },
                "dev_test": {
                    "url": "https://localhost:8000",
                    "verify_ssl": false
                }
            }

    token : string, optional
        You may directly input a valid authenticated token from Collaboratory v1 or v2.
        Note: you should use the `access_token` and NOT `refresh_token`.

    Examples
    --------
    Instantiate an instance of the TestLibrary class

    >>> test_library = TestLibrary(username="<<hbp_username>>", password="<<hbp_password>>")
    >>> test_library = TestLibrary(token="<<token>>")
    """

    __test__ = False

    def __init__(
        self, username=None, password=None, environment="production", token=None
    ):
        super(TestLibrary, self).__init__(username, password, environment, token)
        self._set_app_info()

    def _set_app_info(self):
        if self.environment == "production":
            self.app_name = "Validation Framework"
        elif self.environment == "dev":
            self.app_name = "Validation Framework (dev)"
        elif self.environment == "staging":
            self.app_name = "Model Validation app (staging)"

    # def set_app_config(self, collab_id="", only_if_new=False, recording_modality="", test_type="", species="", brain_region="", cell_type="", model_scope="", abstraction_level="", organization=""):
    #     #  TODO: needs to be updated for Collab v2
    #     inputArgs = locals()
    #     params = {}
    #     params["url"] = self.url + "/parametersconfiguration-validation-app/parametersconfigurationrest/"
    #     params["only_if_new"] = only_if_new
    #     params["config"] = inputArgs
    #     params["config"].pop("self")
    #     params["config"].pop("only_if_new")
    #     params["config"]["app_type"] = "validation_app"
    #     self._configure_app_collab(params)

    def get_test_definition(self, test_path="", test_id="", alias=""):
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
            raise Exception(
                "test_path or test_id or alias needs to be provided for finding a test."
            )
        if test_path:
            if os.path.isfile(test_path):
                # test_path is a local path
                with open(test_path) as fp:
                    test_json = json.load(fp)
            else:
                raise Exception("Error in local file path specified by test_path.")
        else:
            if test_id:
                url = self.url + "/tests/" + test_id
            else:
                url = self.url + "/tests/" + quote(str(alias))
            test_json = requests.get(url, auth=self.auth, verify=self.verify)

        if test_json.status_code != 200:
            handle_response_error("Error in retrieving test", test_json)
        return test_json.json()

    def get_validation_test(
        self,
        test_path="",
        instance_path="",
        instance_id="",
        test_id="",
        alias="",
        version="",
        **params,
    ):
        """Retrieve a specific test instance as a Python class (sciunit.Test instance).

        A specific test definition can be specified
        in the following ways (in order of priority):

        1. load from a local JSON file specified via `test_path` and `instance_path`
        2. specify `instance_id` corresponding to test instance in test library
        3. specify `test_id` and `version`
        4. specify `alias` (of the test) and `version`

        Note: for (3) and (4) above, if `version` is not specified,
              then the latest test version is retrieved

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
            raise Exception(
                "One of the following needs to be provided for finding the required test:\n"
                "test_path, instance_id, test_id or alias"
            )
        else:
            if instance_id:
                # `instance_id` is sufficient for identifying both test and instance
                test_instance_json = self.get_test_instance(
                    instance_path=instance_path, instance_id=instance_id
                )  # instance_path added just to maintain order of priority
                test_id = test_instance_json["test_id"]
                test_json = self.get_test_definition(
                    test_path=test_path, test_id=test_id
                )  # test_path added just to maintain order of priority
            else:
                test_json = self.get_test_definition(
                    test_path=test_path, test_id=test_id, alias=alias
                )
                test_id = test_json[
                    "id"
                ]  # in case test_id was not input for specifying test
                test_instance_json = self.get_test_instance(
                    instance_path=instance_path,
                    instance_id=instance_id,
                    test_id=test_id,
                    version=version,
                )

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

        # Create the :class:`sciunit.Test` instance
        test_instance = test_cls(observation=observation_data, **params)
        test_instance.uuid = test_instance_json["id"]
        return test_instance

    def list_tests(self, size=1000000, from_index=0, **filters):
        """Retrieve a list of test definitions satisfying specified filters.

        The filters may specify one or more attributes that belong
        to a test definition. The following test attributes can be specified:

        * alias
        * name
        * implementation_status
        * brain_region
        * species
        * cell_type
        * data_type
        * recording_modality
        * test_type
        * score_type
        * author

        Parameters
        ----------
        size : positive integer
            Max number of tests to be returned; default is set to 1000000.
        from_index : positive integer
            Index of first test to be returned; default is set to 0.
        **filters : variable length keyword arguments
            To be used to filter test definitions from the test library.

        Returns
        -------
        list
            List of test descriptions satisfying specified filters.

        Examples
        --------
        >>> tests = test_library.list_tests()
        >>> tests = test_library.list_tests(test_type="single cell activity")
        >>> tests = test_library.list_tests(test_type="single cell activity", cell_type="Pyramidal Cell")
        """

        valid_filters = [
            "alias",
            "name",
            "implementation_status",
            "brain_region",
            "species",
            "cell_type",
            "data_type",
            "recording_modality",
            "test_type",
            "score_type",
            "author",
        ]
        params = locals()["filters"]
        for filter in params:
            if filter not in valid_filters:
                raise ValueError(
                    "The specified filter '{}' is an invalid filter!\nValid filters are: {}".format(
                        filter, valid_filters
                    )
                )

        url = self.url + "/tests/"
        url += (
            "?"
            + urlencode(params, doseq=True)
            + "&size="
            + str(size)
            + "&from_index="
            + str(from_index)
        )
        response = requests.get(url, auth=self.auth, verify=self.verify)
        if response.status_code != 200:
            handle_response_error("Error listing tests", response)
        tests = response.json()
        return tests

    def add_test(
        self,
        collab_id=None,
        name=None,
        alias=None,
        author=None,
        species=None,
        age=None,
        brain_region=None,
        cell_type=None,
        publication=None,
        description=None,
        recording_modality=None,
        test_type=None,
        score_type=None,
        data_location=None,
        data_type=None,
        implementation_status=None,
        instances=[],
    ):
        """Register a new test on the test library.

        This allows you to add a new test to the test library.

        Parameters
        ----------
        collab_id : string
            Identifier of the Collab that will be used for access control for this test
        name : string
            Name of the test definition to be created.
        alias : string, optional
            User-assigned unique identifier to be associated with test definition.
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
        recording_modality : string
            Specifies the type of observation used in the test.
        test_type : string
            Specifies the type of the test.
        score_type : string
            The type of score produced by the test.
        description : string
            Experimental protocol involved in obtaining reference data.
        data_location : string
            URL of file containing reference data (observation).
        data_type : string
            The type of reference data (observation).
        publication : string
            Publication or comment (e.g. "Unpublished") to be associated with observation.
        implementation_status : string
            Status of test: 'in development' / 'proposal' / 'published'
        instances : list, optional
            Specify a list of instances (versions) of the test.

        Returns
        -------
        dict
            data of test instance that has been created.

        Examples
        --------
        >>> test = test_library.add_test(name="Cell Density Test", alias="", version="1.0", author="Shailesh Appukuttan",
                                species="Mouse (Mus musculus)", age="TBD", brain_region="Hippocampus", cell_type="Other",
                                recording_modality="electron microscopy", test_type="network: microcircuit", score_type="mean squared error", description="Later",
                                data_location="https://object.cscs.ch/v1/AUTH_c0a333ecf7c045809321ce9d9ecdfdea/sp6_validation_data/hippounit/feat_CA1_pyr_cACpyr_more_features.json",
                                data_type="Mean, SD", publication="Halasy et al., 1996",
                                repository="https://github.com/appukuttan-shailesh/morphounit.git", path="morphounit.tests.CellDensityTest")
        """

        test_data = {}
        args = locals()
        # handle naming difference with API: collab_id <-> project_id
        args["project_id"] = args.pop("collab_id")

        for field in [
            "project_id",
            "name",
            "alias",
            "author",
            "species",
            "age",
            "brain_region",
            "cell_type",
            "publication",
            "description",
            "recording_modality",
            "test_type",
            "score_type",
            "data_location",
            "data_type",
            "implementation_status",
            "instances",
        ]:
            if args[field]:
                test_data[field] = args[field]

        values = self.get_attribute_options()
        for field in (
            "species",
            "brain_region",
            "cell_type",
            "recording_modality",
            "test_type",
            "score_type",
            "implementation_status",
        ):
            if field in test_data and test_data[field] not in values[field] + [None]:
                raise Exception(
                    "{} = '{}' is invalid.\nValue has to be one of these: {}".format(
                        field, test_data[field], values[field]
                    )
                )

        # format names of authors as required by API
        if "author" in test_data:
            test_data["author"] = self._format_people_name(test_data["author"])

        # 'data_location' is now a list of urls
        if not isinstance(test_data["data_location"], list):
            test_data["data_location"] = [test_data["data_location"]]

        url = self.url + "/tests/"
        headers = {"Content-type": "application/json"}
        response = requests.post(
            url,
            data=json.dumps(test_data),
            auth=self.auth,
            headers=headers,
            verify=self.verify,
        )
        if response.status_code == 201:
            return response.json()
        else:
            handle_response_error("Error in adding test", response)

    def edit_test(
        self,
        test_id=None,
        collab_id=None,
        name=None,
        alias=None,
        author=None,
        species=None,
        age=None,
        brain_region=None,
        cell_type=None,
        publication=None,
        description=None,
        recording_modality=None,
        test_type=None,
        score_type=None,
        data_location=None,
        data_type=None,
        implementation_status=None,
    ):
        """Edit an existing test in the test library.

        To update an existing test, the `test_id` must be provided. Any of the
        other parameters may be updated.
        Only the parameters being updated need to be specified.

        Parameters
        ----------
        name : string
            Name of the test definition.
        test_id : UUID
            System generated unique identifier associated with test definition.
        alias : string, optional
            User-assigned unique identifier to be associated with test definition.
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
        recording_modality : string
            Specifies the type of observation used in the test.
        test_type : string
            Specifies the type of the test.
        score_type : string
            The type of score produced by the test.
        description : string
            Experimental protocol involved in obtaining reference data.
        data_location : string
            URL of file containing reference data (observation).
        data_type : string
            The type of reference data (observation).
        publication : string
            Publication or comment (e.g. "Unpublished") to be associated with observation.
        implementation_status : string
            Status of test: 'in development' / 'proposal' / 'published'

        Note
        ----
        Test instances cannot be edited here.
        This has to be done using :meth:`edit_test_instance`

        Returns
        -------
        data
            data of test instance that has been edited.

        Examples
        --------
        test = test_library.edit_test(name="Cell Density Test", test_id="7b63f87b-d709-4194-bae1-15329daf3dec", alias="CDT-6", author="Shailesh Appukuttan", publication="Halasy et al., 1996",
                                      species="Mouse (Mus musculus)", brain_region="Hippocampus", cell_type="Other", age="TBD", recording_modality="electron microscopy",
                                      test_type="network: microcircuit", score_type="mean squared error", protocol="To be filled sometime later", data_location="https://object.cscs.ch/v1/AUTH_c0a333ecf7c045809321ce9d9ecdfdea/sp6_validation_data/hippounit/feat_CA1_pyr_cACpyr_more_features.json", data_type="Mean, SD")
        """

        if not test_id:
            raise Exception("Test ID needs to be provided for editing a test.")

        test_data = {}
        args = locals()
        # handle naming difference with API: collab_id <-> project_id
        args["project_id"] = args.pop("collab_id")

        for field in [
            "project_id",
            "name",
            "alias",
            "author",
            "species",
            "age",
            "brain_region",
            "cell_type",
            "publication",
            "description",
            "recording_modality",
            "test_type",
            "score_type",
            "data_location",
            "data_type",
            "implementation_status",
        ]:
            if args[field]:
                test_data[field] = args[field]

        values = self.get_attribute_options()
        for field in (
            "species",
            "brain_region",
            "cell_type",
            "recording_modality",
            "test_type",
            "score_type",
            "implementation_status",
        ):
            if field in test_data and test_data[field] not in values[field] + [None]:
                raise Exception(
                    "{} = '{}' is invalid.\nValue has to be one of these: {}".format(
                        field, test_data[field], values[field]
                    )
                )

        # format names of authors as required by API
        if "author" in test_data:
            test_data["author"] = self._format_people_name(test_data["author"])

        # 'data_location' is now a list of urls
        if "data_location" in test_data and not isinstance(
            test_data["data_location"], list
        ):
            test_data["data_location"] = [test_data["data_location"]]

        url = self.url + "/tests/" + test_id
        headers = {"Content-type": "application/json"}
        response = requests.put(
            url,
            data=json.dumps(test_data),
            auth=self.auth,
            headers=headers,
            verify=self.verify,
        )
        if response.status_code == 200:
            return response.json()
        else:
            handle_response_error("Error in editing test", response)

    def delete_test(self, test_id="", alias=""):
        """ONLY FOR SUPERUSERS: Delete a specific test definition by its test_id or alias.

        A specific test definition can be deleted from the test library, along with all
        associated test instances, in the following ways (in order of priority):

        1. specify the `test_id`
        2. specify the `alias` (of the test)

        Parameters
        ----------
        test_id : UUID
            System generated unique identifier associated with test definition.
        alias : string
            User-assigned unique identifier associated with test definition.

        Note
        ----
        * This feature is only for superusers!

        Examples
        --------
        >>> test_library.delete_test(test_id="8c7cb9f6-e380-452c-9e98-e77254b088c5")
        >>> test_library.delete_test(alias="B1")
        """

        if test_id == "" and alias == "":
            raise Exception(
                "test ID or alias needs to be provided for deleting a test."
            )
        elif test_id != "":
            url = self.url + "/tests/" + test_id
        else:
            url = self.url + "/tests/" + quote(str(alias))

        test_json = requests.delete(url, auth=self.auth, verify=self.verify)
        if test_json.status_code == 403:
            handle_response_error("Only SuperUser accounts can delete data", test_json)
        elif test_json.status_code != 200:
            handle_response_error("Error in deleting test", test_json)

    def get_test_instance(
        self, instance_path="", instance_id="", test_id="", alias="", version=""
    ):
        """Retrieve a specific test instance definition from the test library.

        A specific test instance can be retrieved
        in the following ways (in order of priority):

        1. load from a local JSON file specified via `instance_path`
        2. specify `instance_id` corresponding to test instance in test library
        3. specify `test_id` and `version`
        4. specify `alias` (of the test) and `version`

        Note: for (3) and (4) above, if `version` is not specified,
              then the latest test version is retrieved

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
        >>> test_instance = test_library.get_test_instance(test_id="7b63f87b-d709-4194-bae1-15329daf3dec")
        """

        if instance_path == "" and instance_id == "" and test_id == "" and alias == "":
            raise Exception(
                "instance_path or instance_id or test_id or alias needs to be provided for finding a test instance."
            )
        if instance_path:
            if os.path.isfile(instance_path):
                # instance_path is a local path
                with open(instance_path) as fp:
                    test_instance_json = json.load(fp)
            else:
                raise Exception("Error in local file path specified by instance_path.")
        else:
            test_identifier = test_id or alias
            if instance_id:
                url = self.url + "/tests/query/instances/" + instance_id
            elif test_id and version:
                url = self.url + "/tests/" + test_id + "/instances/?version=" + version
            elif alias and version:
                url = (
                    self.url
                    + "/tests/"
                    + quote(str(alias))
                    + "/instances/?version="
                    + version
                )
            elif test_id and not version:
                url = self.url + "/tests/" + test_id + "/instances/latest"
            else:
                url = self.url + "/tests/" + quote(str(alias)) + "/instances/latest"
            response = requests.get(url, auth=self.auth, verify=self.verify)

        if response.status_code != 200:
            handle_response_error("Error in retrieving test instance", response)
        test_instance_json = response.json()
        if isinstance(
            test_instance_json, list
        ):  # can have multiple instances with the same version but different parameters
            if len(test_instance_json) == 1:
                test_instance_json = test_instance_json[0]
            elif len(test_instance_json) > 1:
                return max(test_instance_json, key=lambda x: x["timestamp"])
        return test_instance_json

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
            raise Exception(
                "instance_path or test_id or alias needs to be provided for finding test instances."
            )
        if instance_path and os.path.isfile(instance_path):
            # instance_path is a local path
            with open(instance_path) as fp:
                test_instances_json = json.load(fp)
        else:
            if test_id:
                url = self.url + "/tests/" + test_id + "/instances/?size=100000"
            else:
                url = (
                    self.url + "/tests/" + quote(str(alias)) + "/instances/?size=100000"
                )
            response = requests.get(url, auth=self.auth, verify=self.verify)

        if response.status_code != 200:
            handle_response_error("Error in retrieving test instances", response)
        test_instances_json = response.json()
        return test_instances_json

    def add_test_instance(
        self,
        test_id="",
        alias="",
        repository="",
        path="",
        version="",
        description="",
        parameters="",
    ):
        """Register a new test instance.

        This allows to add a new instance to an existing test in the test library.
        The `test_id` or `alias` needs to be specified as input parameter.

        Parameters
        ----------
        test_id : UUID
            System generated unique identifier associated with test definition.
        alias : string
            User-assigned unique identifier associated with test definition.
        version : string
            User-assigned identifier (unique for each test) associated with test instance.
        repository : string
            URL of Python package repository (e.g. github).
        path : string
            Python path (not filesystem path) to test source code within Python package.
        description : string, optional
            Text describing this specific test instance.
        parameters : string, optional
            Any additional parameters to be submitted to test, or used by it, at runtime.

        Returns
        -------
        dict
            data of test instance that has been created.

        Examples
        --------
        >>> instance = test_library.add_test_instance(test_id="7b63f87b-d709-4194-bae1-15329daf3dec",
                                        repository="https://github.com/appukuttan-shailesh/morphounit.git",
                                        path="morphounit.tests.CellDensityTest",
                                        version="3.0")
        """

        instance_data = locals()
        instance_data.pop("self")

        for key, val in instance_data.items():
            if val == "":
                instance_data[key] = None

        test_id = test_id or alias
        if not test_id:
            raise Exception(
                "test_id or alias needs to be provided for finding the test."
            )
        else:
            url = self.url + "/tests/" + quote(str(test_id)) + "/instances/"

        headers = {"Content-type": "application/json"}
        response = requests.post(
            url,
            data=json.dumps(instance_data),
            auth=self.auth,
            headers=headers,
            verify=self.verify,
        )
        if response.status_code == 201:
            return response.json()
        else:
            handle_response_error("Error in adding test instance", response)

    def edit_test_instance(
        self,
        instance_id="",
        test_id="",
        alias="",
        repository=None,
        path=None,
        version=None,
        description=None,
        parameters=None,
    ):
        """Edit an existing test instance.

        This allows to edit an instance of an existing test in the test library.
        The test instance can be specified in the following ways (in order of priority):

        1. specify `instance_id` corresponding to test instance in test library
        2. specify `test_id` and `version`
        3. specify `alias` (of the test) and `version`

        Only the parameters being updated need to be specified. You cannot
        edit the test `version` in the latter two cases. To do so,
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
        description : string, optional
            Text describing this specific test instance.
        parameters : string, optional
            Any additional parameters to be submitted to test, or used by it, at runtime.

        Returns
        -------
        dict
            data of test instance that has was edited.

        Examples
        --------
        >>> instance = test_library.edit_test_instance(test_id="7b63f87b-d709-4194-bae1-15329daf3dec",
                                        repository="https://github.com/appukuttan-shailesh/morphounit.git",
                                        path="morphounit.tests.CellDensityTest",
                                        version="4.0")
        """

        test_identifier = test_id or alias
        if instance_id == "" and (test_identifier == "" or version is None):
            raise Exception(
                "instance_id or (test_id, version) or (alias, version) needs to be provided for finding a test instance."
            )

        instance_data = {}
        args = locals()
        for field in ("repository", "path", "version", "description", "parameters"):
            value = args[field]
            if value:
                instance_data[field] = value

        if instance_id:
            url = self.url + "/tests/query/instances/" + instance_id
        else:
            url = (
                self.url
                + "/tests/"
                + test_identifier
                + "/instances/?version="
                + version
            )
            response0 = requests.get(url, auth=self.auth, verify=self.verify)
            if response0.status_code != 200:
                raise Exception("Invalid test identifier and/or version")
            url = (
                self.url + "/tests/query/instances/" + response0.json()[0]["id"]
            )  # todo: handle more than 1 instance in response

        headers = {"Content-type": "application/json"}
        response = requests.put(
            url,
            data=json.dumps(instance_data),
            auth=self.auth,
            headers=headers,
            verify=self.verify,
        )
        if response.status_code == 200:
            return response.json()
        else:
            handle_response_error("Error in editing test instance", response)

    def delete_test_instance(self, instance_id="", test_id="", alias="", version=""):
        """ONLY FOR SUPERUSERS: Delete an existing test instance.

        This allows to delete an instance of an existing test in the test library.
        The test instance can be specified in the following ways (in order of priority):

        1. specify `instance_id` corresponding to test instance in test library
        2. specify `test_id` and `version`
        3. specify `alias` (of the test) and `version`

        Parameters
        ----------
        instance_id : UUID
            System generated unique identifier associated with test instance.
        test_id : UUID
            System generated unique identifier associated with test definition.
        alias : string
            User-assigned unique identifier associated with test definition.
        version : string
            User-assigned unique identifier associated with test instance.

        Note
        ----
        * This feature is only for superusers!

        Examples
        --------
        >>> test_library.delete_model_instance(test_id="8c7cb9f6-e380-452c-9e98-e77254b088c5")
        >>> test_library.delete_model_instance(alias="B1", version="1.0")
        """

        test_identifier = test_id or alias
        if instance_id == "" and (test_identifier == "" or version == ""):
            raise Exception(
                "instance_id or (test_id, version) or (alias, version) needs to be provided for finding a test instance."
            )

        if instance_id:
            url = self.url + "/tests/query/instances/" + instance_id
        else:
            url = self.url + "/tests/" + test_identifier + "/instances/" + version
            response0 = requests.get(url, auth=self.auth, verify=self.verify)
            if response0.status_code != 200:
                raise Exception("Invalid test identifier and/or version")
            url = self.url + "/tests/query/instances/" + response0.json()[0]["id"]
        response = requests.delete(url, auth=self.auth, verify=self.verify)
        if response.status_code == 403:
            handle_response_error("Only SuperUser accounts can delete data", response)
        elif response.status_code != 200:
            handle_response_error("Error in deleting test instance", response)

    def _load_reference_data(self, uri_list):
        # Load the reference data ("observations").
        observation_data = []
        return_single = False
        if not isinstance(uri_list, list):
            uri_list = [uri_list]
            return_single = True
        for uri in uri_list:
            parse_result = urlparse(uri)
            datastore = URI_SCHEME_MAP[parse_result.scheme](auth=self.auth)
            observation_data.append(datastore.load_data(uri))
        if return_single:
            return observation_data[0]
        else:
            return observation_data

    def get_attribute_options(self, param=""):
        """Retrieve valid values for test attributes.

        Will return the list of valid values (where applicable) for various test attributes.
        The following test attributes can be specified:

        * cell_type
        * test_type
        * score_type
        * brain_region
        * recording_modality
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
        >>> data = test_library.get_attribute_options("cell types")
        """
        valid_params = [
            "species",
            "brain_region",
            "cell_type",
            "test_type",
            "score_type",
            "recording_modality",
            "implementation_status",
        ]
        return self._get_attribute_options(param, valid_params)

    def get_result(self, result_id=""):
        """Retrieve a test result.

        This allows to retrieve the test result score and other related information.
        The `result_id` needs to be specified as input parameter.

        Parameters
        ----------
        result_id : UUID
            System generated unique identifier associated with result.

        Returns
        -------
        dict
            Information about the result retrieved.

        Examples
        --------
        >>> result = test_library.get_result(result_id="901ac0f3-2557-4ae3-bb2b-37617312da09")
        """

        if not result_id:
            raise Exception(
                "result_id needs to be provided for finding a specific result."
            )
        else:
            url = self.url + "/results/" + result_id
        response = requests.get(url, auth=self.auth, verify=self.verify)
        if response.status_code != 200:
            handle_response_error("Error in retrieving result", response)
        result_json = renameNestedJSONKey(response.json(), "project_id", "collab_id")
        return result_json

    def list_results(self, size=1000000, from_index=0, **filters):
        """Retrieve test results satisfying specified filters.

        This allows to retrieve a list of test results with their scores
        and other related information.

        Parameters
        ----------
        size : positive integer
            Max number of results to be returned; default is set to 1000000.
        from_index : positive integer
            Index of first result to be returned; default is set to 0.
        **filters : variable length keyword arguments
            To be used to filter the results metadata.

        Returns
        -------
        dict
            Information about the results retrieved.

        Examples
        --------
        >>> results = test_library.list_results()
        >>> results = test_library.list_results(test_id="7b63f87b-d709-4194-bae1-15329daf3dec")
        >>> results = test_library.list_results(id="901ac0f3-2557-4ae3-bb2b-37617312da09")
        >>> results = test_library.list_results(model_instance_id="f32776c7-658f-462f-a944-1daf8765ec97")
        """

        url = self.url + "/results/"
        url += (
            "?"
            + urlencode(filters, doseq=True)
            + "&size="
            + str(size)
            + "&from_index="
            + str(from_index)
        )
        response = requests.get(url, auth=self.auth, verify=self.verify)
        if response.status_code != 200:
            handle_response_error("Error in retrieving results", response)
        result_json = response.json()
        return renameNestedJSONKey(result_json, "project_id", "collab_id")

    def register_result(self, test_result, data_store=None, collab_id=None):
        """Register test result with HBP Validation Results Service.

        The score of a test, along with related output data such as figures,
        can be registered on the validation framework.

        Parameters
        ----------
        test_result : :class:`sciunit.Score`
            a :class:`sciunit.Score` instance returned by `test.judge(model)`
        data_store : :class:`DataStore`
            a :class:`DataStore` instance, for uploading related data generated by the test run, e.g. figures.
        collab_id : str
            String input specifying the Collab path, e.g. 'model-validation' to indicate Collab 'https://wiki.ebrains.eu/bin/view/Collabs/model-validation/'.
            This is used to indicate the Collab where results should be saved.

        Note
        ----
        Source code for this method still contains comments/suggestions from
        previous client. To be removed or implemented.

        Returns
        -------
        dict
            data of test result that has been created.

        Examples
        --------
        >>> score = test.judge(model)
        >>> response = test_library.register_result(test_result=score)
        """

        if collab_id is None:
            collab_id = test_result.related_data.get("collab_id", None)
        if collab_id is None:
            raise Exception(
                "Don't know where to register this result. Please specify `collab_id`!"
            )

        model_catalog = ModelCatalog.from_existing(self)
        model_instance_uuid = model_catalog.find_model_instance_else_add(
            test_result.model
        )["id"]

        results_storage = []
        if data_store:
            if not data_store.authorized:
                data_store.authorize(
                    self.auth
                )  # relies on data store using EBRAINS authorization
                # if this is not the case, need to authenticate/authorize
                # the data store before passing to `register()`
            if data_store.collab_id is None:
                data_store.collab_id = collab_id
            files_to_upload = []
            if "figures" in test_result.related_data:
                files_to_upload.extend(test_result.related_data["figures"])
            if files_to_upload:
                list_dict_files_to_upload = [
                    {"download_url": f["filepath"], "size": f["filesize"]}
                    for f in data_store.upload_data(files_to_upload)
                ]
                results_storage.extend(list_dict_files_to_upload)

        url = self.url + "/results/"
        result_json = {
            "model_instance_id": model_instance_uuid,
            "test_instance_id": test_result.test.uuid,
            "results_storage": results_storage,
            "score": int(test_result.score)
            if isinstance(test_result.score, bool)
            else test_result.score,
            "passed": None
            if "passed" not in test_result.related_data
            else test_result.related_data["passed"],
            # "platform": str(self._get_platform()), # not currently supported in v2
            "project_id": collab_id,
            "normalized_score": int(test_result.score)
            if isinstance(test_result.score, bool)
            else test_result.score,
        }

        headers = {"Content-type": "application/json"}
        response = requests.post(
            url,
            data=json.dumps(result_json),
            auth=self.auth,
            headers=headers,
            verify=self.verify,
        )
        if response.status_code == 201:
            print("Result registered successfully!")
            return renameNestedJSONKey(response.json(), "project_id", "collab_id")
        else:
            handle_response_error("Error registering result", response)

    def delete_result(self, result_id=""):
        """ONLY FOR SUPERUSERS: Delete a result on the validation framework.

        This allows to delete an existing result info on the validation framework.
        The `result_id` needs to be specified as input parameter.

        Parameters
        ----------
        result_id : UUID
            System generated unique identifier associated with result.

        Note
        ----
        * This feature is only for superusers!

        Examples
        --------
        >>> model_catalog.delete_result(result_id="2b45e7d4-a7a1-4a31-a287-aee7072e3e75")
        """

        if not result_id:
            raise Exception(
                "result_id needs to be provided for finding a specific result."
            )
        else:
            url = self.url + "/results/" + result_id
        model_image_json = requests.delete(url, auth=self.auth, verify=self.verify)
        if model_image_json.status_code == 403:
            handle_response_error(
                "Only SuperUser accounts can delete data", model_image_json
            )
        elif model_image_json.status_code != 200:
            handle_response_error("Error in deleting result", model_image_json)

    def _get_platform(self):
        """
        Return a dict containing information about the platform the test was run on.
        """
        # This needs to be extended to support remote execution, e.g. job queues on clusters.
        # Use Sumatra?
        network_name = platform.node()
        bits, linkage = platform.architecture()
        return dict(
            architecture_bits=bits,
            architecture_linkage=linkage,
            machine=platform.machine(),
            network_name=network_name,
            ip_addr=_get_ip_address(),
            processor=platform.processor(),
            release=platform.release(),
            system_name=platform.system(),
            version=platform.version(),
        )


class ModelCatalog(BaseClient):
    """Client for the EBRAINS Model Catalog.

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
    Download model instance                :meth:`download_model_instance`
    List model instances                   :meth:`list_model_instances`
    Add new model instance                 :meth:`add_model_instance`
    Find model instance; else add          :meth:`find_model_instance_else_add`
    Edit existing model instance           :meth:`edit_model_instance`
    ====================================   ====================================

    Parameters
    ----------
    username : string
        Your EBRAINS Collaboratory username. Not needed in Jupyter notebooks within the EBRAINS Collaboratory.
    password : string, optional
        Your EBRAINS Collaboratory password; advisable to not enter as plaintext.
        If left empty, you would be prompted for password at run time (safer).
        Not needed in Jupyter notebooks within the EBRAINS Collaboratory.
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
                },
                "dev_test": {
                    "url": "https://localhost:8000",
                    "verify_ssl": false
                }
            }

    token : string, optional
        You may directly input a valid authenticated token from Collaboratory v1 or v2.
        Note: you should use the `access_token` and NOT `refresh_token`.

    Examples
    --------
    Instantiate an instance of the ModelCatalog class

    >>> model_catalog = ModelCatalog(username="<<hbp_username>>", password="<<hbp_password>>")
    >>> model_catalog = ModelCatalog(token="<<token>>")
    """

    __test__ = False

    def __init__(
        self, username=None, password=None, environment="production", token=None
    ):
        super(ModelCatalog, self).__init__(username, password, environment, token)
        self._set_app_info()

    def _set_app_info(self):
        if self.environment == "production":
            self.app_name = "Model Catalog"
        elif self.environment == "dev":
            self.app_name = "Model Catalog (dev)"
        elif self.environment == "staging":
            self.app_name = "Model Catalog (staging)"

    # def set_app_config(self, collab_id="", only_if_new=False, species="", brain_region="", cell_type="", model_scope="", abstraction_level="", organization=""):
    #     #  TODO: needs to be updated for Collab v2
    #     inputArgs = locals()
    #     params = {}
    #     params["url"] = self.url + "/parametersconfiguration-model-catalog/parametersconfigurationrest/"
    #     params["only_if_new"] = only_if_new
    #     params["config"] = inputArgs
    #     params["config"].pop("self")
    #     params["config"].pop("only_if_new")
    #     params["config"]["app_type"] = "model_catalog"
    #     self._configure_app_collab(params)

    # def set_app_config_minimal(self, project_="", only_if_new=False):
    #     #  TODO: needs to be updated for Collab v2
    #     inputArgs = locals()
    #     species = []
    #     brain_region = []
    #     cell_type = []
    #     model_scope = []
    #     abstraction_level = []
    #     organization = []

    #     models = self.list_models(app_id=app_id)
    #     if len(models) == 0:
    #         print("There are currently no models associated with this Model Catalog app.\nConfiguring filters to show all accessible data.")

    #     for model in models:
    #         if model["species"] not in species:
    #             species.append(model["species"])
    #         if model["brain_region"] not in brain_region:
    #             brain_region.append(model["brain_region"])
    #         if model["cell_type"] not in cell_type:
    #             cell_type.append(model["cell_type"])
    #         if model["model_scope"] not in model_scope:
    #             model_scope.append(model["model_scope"])
    #         if model["abstraction_level"] not in abstraction_level:
    #             abstraction_level.append(model["abstraction_level"])
    #         if model["organization"] not in organization:
    #             organization.append(model["organization"])

    #     filters = {}
    #     for key in ["collab_id", "app_id", "species", "brain_region", "cell_type", "model_scope", "abstraction_level", "organization"]:
    #         if isinstance(locals()[key], list):
    #             filters[key] = ",".join(locals()[key])
    #         else:
    #             filters[key] = locals()[key]

    #     params = {}
    #     params["url"] = self.url + "/parametersconfiguration-model-catalog/parametersconfigurationrest/"
    #     params["only_if_new"] = only_if_new
    #     params["config"] = filters
    #     params["config"]["app_type"] = "model_catalog"
    #     self._configure_app_collab(params)

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
            raise Exception(
                "Model ID or alias needs to be provided for finding a model."
            )
        elif model_id != "":
            url = self.url + "/models/" + model_id
        else:
            url = self.url + "/models/" + quote(str(alias))

        model_json = requests.get(url, auth=self.auth, verify=self.verify)
        if model_json.status_code != 200:
            handle_response_error("Error in retrieving model", model_json)
        model_json = model_json.json()

        if instances is False:
            model_json.pop("instances")
        return renameNestedJSONKey(model_json, "project_id", "collab_id")

    def list_models(self, size=1000000, from_index=0, **filters):
        """Retrieve list of model descriptions satisfying specified filters.

        The filters may specify one or more attributes that belong
        to a model description. The following model attributes can be specified:

        * alias
        * name
        * brain_region
        * species
        * cell_type
        * model_scope
        * abstraction_level
        * author
        * owner
        * organization
        * collab_id
        * private

        Parameters
        ----------
        size : positive integer
            Max number of models to be returned; default is set to 1000000.
        from_index : positive integer
            Index of first model to be returned; default is set to 0.
        **filters : variable length keyword arguments
            To be used to filter model descriptions from the model catalog.

        Returns
        -------
        list
            List of model descriptions satisfying specified filters.

        Examples
        --------
        >>> models = model_catalog.list_models()
        >>> models = model_catalog.list_models(collab_id="model-validation")
        >>> models = model_catalog.list_models(cell_type="Pyramidal Cell", brain_region="Hippocampus")
        """

        valid_filters = [
            "name",
            "alias",
            "brain_region",
            "species",
            "cell_type",
            "model_scope",
            "abstraction_level",
            "author",
            "owner",
            "organization",
            "collab_id",
            "private",
        ]
        params = locals()["filters"]
        for filter in params:
            if filter not in valid_filters:
                raise ValueError(
                    "The specified filter '{}' is an invalid filter!\nValid filters are: {}".format(
                        filter, valid_filters
                    )
                )

        # handle naming difference with API: collab_id <-> project_id
        if "collab_id" in params:
            params["project_id"] = params.pop("collab_id")

        url = self.url + "/models/"
        url += (
            "?"
            + urlencode(params, doseq=True)
            + "&size="
            + str(size)
            + "&from_index="
            + str(from_index)
        )
        response = requests.get(url, auth=self.auth, verify=self.verify)
        if response.status_code == 200:
            try:
                models = response.json()
            except json.JSONDecodeError:
                handle_response_error("Error in list_models()", response)
            if isinstance(models, dict):
                models = [models]
            return renameNestedJSONKey(models, "project_id", "collab_id")
        else:
            error = response.json()
            raise Exception(f"{error['detail']} (status code {response.status_code})")

    def register_model(
        self,
        collab_id=None,
        name=None,
        alias=None,
        author=None,
        owner=None,
        organization=None,
        species=None,
        brain_region=None,
        cell_type=None,
        model_scope=None,
        abstraction_level=None,
        license=None,
        description=None,
        instances=[],
    ):
        """Register a new model in the model catalog.

        This allows you to add a new model to the model catalog. Model instances
        can optionally be specified at the time of model
        creation, or can be added later individually.

        Parameters
        ----------
        collab_id : string
            Specifies the ID of the host collab in the EBRAINS Collaboratory.
            (the model would belong to this collab)
        name : string
            Name of the model description to be created.
        alias : string, optional
            User-assigned unique identifier to be associated with model description.
        author : string
            Name of person creating the model description.
        organization : string, optional
            Option to tag model with organization info.
        species : string
            The species for which the model is developed.
        brain_region : string
            The brain region for which the model is developed.
        cell_type : string
            The type of cell for which the model is developed.
        model_scope : string
            Specifies the type of the model.
        abstraction_level : string
            Specifies the model abstraction level.
        owner : string
            Specifies the owner of the model. Need not necessarily be the same as the author.
        description : string
            Provides a description of the model.
        instances : list, optional
            Specify a list of instances (versions) of the model.

        Returns
        -------
        dict
            Model description that has been created.

        Examples
        --------
        (without instances)

        >>> model = model_catalog.register_model(collab_id="model-validation", name="Test Model - B2",
                        alias="Model vB2", author="Shailesh Appukuttan", organization="CNRS",
                        cell_type="Granule Cell", model_scope="Single cell model",
                        abstraction_level="Spiking neurons",
                        brain_region="Basal Ganglia", species="Mouse (Mus musculus)",
                        owner="Andrew Davison",
                        description="This is a test entry")

        (with instances)

        >>> model = model_catalog.register_model(collab_id="model-validation", name="Test Model - C2",
                        alias="Model vC2", author="Shailesh Appukuttan", organization="CNRS",
                        cell_type="Granule Cell", model_scope="Single cell model",
                        abstraction_level="Spiking neurons",
                        brain_region="Basal Ganglia", species="Mouse (Mus musculus)",
                        owner="Andrew Davison", license="BSD 3-Clause",
                        description="This is a test entry! Please ignore.",
                        instances=[{"source":"https://www.abcde.com", license="BSD 3-Clause",
                                    "version":"1.0", "parameters":""},
                                   {"source":"https://www.12345.com", license="BSD 3-Clause",
                                    "version":"2.0", "parameters":""}],
                        )
        """

        model_data = {}
        args = locals()

        # handle naming difference with API: collab_id <-> project_id
        args["project_id"] = args.pop("collab_id")

        for field in [
            "project_id",
            "name",
            "alias",
            "author",
            "organization",
            "cell_type",
            "model_scope",
            "abstraction_level",
            "brain_region",
            "species",
            "owner",
            "description",
            "instances",
        ]:
            if args[field]:
                model_data[field] = args[field]

        values = self.get_attribute_options()
        for field in [
            "species",
            "brain_region",
            "cell_type",
            "abstraction_level",
            "model_scope",
        ]:
            if field in model_data and model_data[field] not in values[field] + [None]:
                raise Exception(
                    "{} = '{}' is invalid.\nValue has to be one of these: {}".format(
                        field, model_data[field], values[field]
                    )
                )

        # format names of authors and owners as required by API
        for field in ("author", "owner"):
            if model_data[field]:
                model_data[field] = self._format_people_name(model_data[field])

        url = self.url + "/models/"
        headers = {"Content-type": "application/json"}
        response = requests.post(
            url,
            data=json.dumps(model_data),
            auth=self.auth,
            headers=headers,
            verify=self.verify,
        )
        if response.status_code == 201:
            return renameNestedJSONKey(response.json(), "project_id", "collab_id")
        else:
            handle_response_error("Error in adding model", response)

    def edit_model(
        self,
        model_id=None,
        collab_id=None,
        name=None,
        alias=None,
        author=None,
        owner=None,
        organization=None,
        species=None,
        brain_region=None,
        cell_type=None,
        model_scope=None,
        abstraction_level=None,
        project=None,
        license=None,
        description=None,
    ):
        """Edit an existing model on the model catalog.

        This allows you to edit a new model to the model catalog.
        The `model_id` must be provided. Any of the other parameters maybe updated.
        Only the parameters being updated need to be specified.

        Parameters
        ----------
        model_id : UUID
            System generated unique identifier associated with model description.
        collab_id : string
            Specifies the ID of the host collab in the EBRAINS Collaboratory.
            (the model would belong to this collab)
        name : string
            Name of the model description to be created.
        alias : string, optional
            User-assigned unique identifier to be associated with model description.
        author : string
            Name of person creating the model description.
        organization : string, optional
            Option to tag model with organization info.
        species : string
            The species for which the model is developed.
        brain_region : string
            The brain region for which the model is developed.
        cell_type : string
            The type of cell for which the model is developed.
        model_scope : string
            Specifies the type of the model.
        abstraction_level : string
            Specifies the model abstraction level.
        owner : string
            Specifies the owner of the model. Need not necessarily be the same as the author.
        project : string
            Can be used to indicate the project to which the model belongs.
        license : string
            Indicates the license applicable for this model.
        description : string
            Provides a description of the model.

        Note
        ----
        Model instances cannot be edited here.
        This has to be done using :meth:`edit_model_instance` and :meth:`edit_model_image`

        Returns
        -------
        dict
            Model description that has been edited.

        Examples
        --------
        >>> model = model_catalog.edit_model(collab_id="model-validation", name="Test Model - B2",
                        model_id="8c7cb9f6-e380-452c-9e98-e77254b088c5",
                        alias="Model-B2", author="Shailesh Appukuttan", organization="HBP-SP6",
                        cell_type="Granule Cell", model_scope="Single cell model",
                        abstraction_level="Spiking neurons",
                        brain_region="Basal Ganglia", species="Mouse (Mus musculus)",
                        owner="Andrew Davison", project="SP 6.4", license="BSD 3-Clause",
                        description="This is a test entry")
        """

        if not model_id:
            raise Exception("Model ID needs to be provided for editing a model.")

        model_data = {}
        args = locals()

        # handle naming difference with API: collab_id <-> project_id
        args["project_id"] = args.pop("collab_id")

        for field in [
            "project_id",
            "name",
            "alias",
            "author",
            "organization",
            "cell_type",
            "model_scope",
            "abstraction_level",
            "brain_region",
            "species",
            "owner",
            "project",
            "license",
            "description",
        ]:
            if args[field]:
                model_data[field] = args[field]

        values = self.get_attribute_options()
        for field in (
            "species",
            "brain_region",
            "cell_type",
            "abstraction_level",
            "model_scope",
        ):
            if field in model_data and model_data[field] not in values[field] + [None]:
                raise Exception(
                    "{} = '{}' is invalid.\nValue has to be one of these: {}".format(
                        field, model_data[field], values[field]
                    )
                )

        # format names of authors and owners as required by API
        for field in ("author", "owner"):
            if model_data.get(field):
                model_data[field] = self._format_people_name(model_data[field])

        if "alias" in model_data and model_data["alias"] == "":
            model_data["alias"] = None

        headers = {"Content-type": "application/json"}
        url = self.url + "/models/" + model_id
        response = requests.put(
            url,
            data=json.dumps(model_data),
            auth=self.auth,
            headers=headers,
            verify=self.verify,
        )
        if response.status_code == 200:
            return renameNestedJSONKey(response.json(), "project_id", "collab_id")
        else:
            handle_response_error("Error in updating model", response)

    def delete_model(self, model_id="", alias=""):
        """ONLY FOR SUPERUSERS: Delete a specific model description by its model_id or alias.

        A specific model description can be deleted from the model catalog, along with all
        associated model instances and results, in the following ways (in order of priority):

        1. specify the `model_id`
        2. specify the `alias` (of the model)

        Parameters
        ----------
        model_id : UUID
            System generated unique identifier associated with model description.
        alias : string
            User-assigned unique identifier associated with model description.

        Note
        ----
        * This feature is only for superusers!

        Examples
        --------
        >>> model_catalog.delete_model(model_id="8c7cb9f6-e380-452c-9e98-e77254b088c5")
        >>> model_catalog.delete_model(alias="B1")
        """

        if model_id == "" and alias == "":
            raise Exception(
                "Model ID or alias needs to be provided for deleting a model."
            )
        elif model_id != "":
            url = self.url + "/models/" + model_id
        else:
            url = self.url + "/models/" + quote(str(alias))

        model_json = requests.delete(url, auth=self.auth, verify=self.verify)
        if model_json.status_code == 403:
            handle_response_error("Only SuperUser accounts can delete data", model_json)
        elif model_json.status_code != 200:
            handle_response_error("Error in deleting model", model_json)

    def get_attribute_options(self, param=""):
        """Retrieve valid values for attributes.

        Will return the list of valid values (where applicable) for various attributes.
        The following model attributes can be specified:

        * cell_type
        * brain_region
        * model_scope
        * abstraction_level
        * species

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
        >>> data = model_catalog.get_attribute_options("cell types")
        """
        valid_params = [
            "species",
            "brain_region",
            "cell_type",
            "model_scope",
            "abstraction_level",
        ]
        return self._get_attribute_options(param, valid_params)

    def get_model_instance(
        self, instance_path="", instance_id="", model_id="", alias="", version=""
    ):
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
        >>> model_instance = model_catalog.get_model_instance(instance_id="a035f2b2-fe2e-42fd-82e2-4173a304263b")
        """

        if (
            instance_path == ""
            and instance_id == ""
            and (model_id == "" or version == "")
            and (alias == "" or version == "")
        ):
            raise Exception(
                "instance_path or instance_id or (model_id, version) or (alias, version) needs to be provided for finding a model instance."
            )
        if instance_path and os.path.isfile(instance_path):
            # instance_path is a local path
            with open(instance_path) as fp:
                model_instance_json = json.load(fp)
        else:
            if instance_id:
                url = self.url + "/models/query/instances/" + instance_id
            elif model_id and version:
                url = (
                    self.url + "/models/" + model_id + "/instances/?version=" + version
                )
            else:
                url = (
                    self.url
                    + "/models/"
                    + quote(str(alias))
                    + "/instances/?version="
                    + version
                )
            model_instance_json = requests.get(url, auth=self.auth, verify=self.verify)
        if model_instance_json.status_code != 200:
            handle_response_error(
                "Error in retrieving model instance", model_instance_json
            )
        model_instance_json = model_instance_json.json()
        # if specifying a version, this can return multiple instances, since instances
        # can have the same version but different parameters
        if len(model_instance_json) == 1:
            return model_instance_json[0]
        return model_instance_json

    def download_model_instance(
        self,
        instance_path="",
        instance_id="",
        model_id="",
        alias="",
        version="",
        local_directory=".",
        overwrite=False,
    ):
        """Download files/directory corresponding to an existing model instance.

        Files/directory corresponding to a model instance to be downloaded. The model
        instance can be specified in the following ways (in order of priority):

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
        local_directory : string
            Directory path (relative/absolute) where files should be downloaded and saved. Default is current location.
        overwrite: Boolean
            Indicates if any existing file at the target location should be overwritten; default is set to False

        Returns
        -------
        string
            Absolute path of the downloaded file/directory.

        Note
        ----
        Existing files, if any, at the target location will be overwritten!

        Examples
        --------
        >>> file_path = model_catalog.download_model_instance(instance_id="a035f2b2-fe2e-42fd-82e2-4173a304263b")
        """

        model_instance = self.get_model_instance(
            instance_path=instance_path,
            instance_id=instance_id,
            model_id=model_id,
            alias=alias,
            version=version,
        )
        model_source = model_instance["source"]
        if model_source[-1] == "/":
            model_source = model_source[:-1]  # remove trailing '/'
        Path(local_directory).mkdir(parents=True, exist_ok=True)
        fileList = []

        if "drive.ebrains.eu/lib/" in model_source:
            # ***** Handles Collab storage urls *****
            repo_id = model_source.split("drive.ebrains.eu/lib/")[1].split("/")[0]
            model_path = "/" + "/".join(
                model_source.split("drive.ebrains.eu/lib/")[1].split("/")[2:]
            )
            datastore = URI_SCHEME_MAP["collab_v2"](collab_id=repo_id, auth=self.auth)
            fileList = datastore.download_data(
                model_path, local_directory=local_directory, overwrite=overwrite
            )
        elif model_source.startswith("swift://cscs.ch/"):
            # ***** Handles CSCS private urls *****
            datastore = URI_SCHEME_MAP["swift"]()
            fileList = datastore.download_data(
                str(model_source), local_directory=local_directory, overwrite=overwrite
            )
        elif model_source.startswith("https://object.cscs.ch/"):
            # ***** Handles CSCS public urls (file or folder) *****
            if "?prefix" in model_source:
                url_parts = urlparse(model_source)
                query_params = parse_qs(url_parts.query)
                prefix = query_params["prefix"][0]
                resolved_parts = (url_parts.scheme, url_parts.netloc, url_parts.path + "/" + prefix, None, None, None)
                model_source = urlunparse(resolved_parts)
            else:
                model_source = urljoin(
                    model_source, urlparse(model_source).path
                )  # remove query params from URL, e.g. `?bluenaas=true`
            req = requests.head(model_source)
            if req.status_code == 200:
                if "directory" in req.headers["Content-Type"]:
                    base_source = "/".join(model_source.split("/")[:6])
                    model_rel_source = "/".join(model_source.split("/")[6:])
                    dir_name = model_source.split("/")[-1]
                    req = requests.get(base_source)
                    contents = req.text.split("\n")
                    files_match = [
                        os.path.join(base_source, x)
                        for x in contents
                        if x.startswith(model_rel_source) and "." in x
                    ]
                    local_directory = os.path.join(local_directory, dir_name)
                    Path(local_directory).mkdir(parents=True, exist_ok=True)
                else:
                    files_match = [model_source]
                datastore = URI_SCHEME_MAP["http"]()
                fileList = datastore.download_data(
                    files_match, local_directory=local_directory, overwrite=overwrite
                )
            else:
                raise FileNotFoundError(
                    "Requested file/folder not found: {}".format(model_source)
                )
        else:
            # ***** Handles ModelDB and external urls (only file; not folder) *****
            datastore = URI_SCHEME_MAP["http"]()
            fileList = datastore.download_data(
                str(model_source), local_directory=local_directory, overwrite=overwrite
            )

        if len(fileList) > 0:
            flag = True
            if len(fileList) == 1:
                outpath = fileList[0]
            else:
                outpath = os.path.dirname(os.path.commonprefix(fileList))
            return os.path.abspath(outpath.encode("ascii"))
        else:
            print("\nSource location: {}".format(model_source))
            print("Could not download the specified file(s)!")
            return None

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
        >>> model_instances = model_catalog.list_model_instances(alias="Model vB2")
        """

        if instance_path == "" and model_id == "" and alias == "":
            raise Exception(
                "instance_path or model_id or alias needs to be provided for finding model instances."
            )
        if instance_path and os.path.isfile(instance_path):
            # instance_path is a local path
            with open(instance_path) as fp:
                model_instances_json = json.load(fp)
        else:
            if model_id:
                url = self.url + "/models/" + model_id + "/instances/?size=100000"
            else:
                url = (
                    self.url
                    + "/models/"
                    + quote(str(alias))
                    + "/instances/?size=100000"
                )
            model_instances_json = requests.get(url, auth=self.auth, verify=self.verify)
        if model_instances_json.status_code != 200:
            handle_response_error(
                "Error in retrieving model instances", model_instances_json
            )
        model_instances_json = model_instances_json.json()
        return model_instances_json

    def add_model_instance(
        self,
        model_id="",
        alias="",
        source="",
        version="",
        description="",
        parameters=None,
        code_format="",
        hash="",
        morphology="",
        license="",
    ):
        """Register a new model instance.

        This allows to add a new instance of an existing model in the model catalog.
        The `model_id` or 'alias' needs to be specified as input parameter.

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
        description : string, optional
            Text describing this specific model instance.
        parameters : string, optional
            Any additional parameters to be submitted to model, or used by it, at runtime.
        code_format : string, optional
            Indicates the language/platform in which the model was developed.
        hash : string, optional
            Similar to a checksum; can be used to identify model instances from their implementation.
        morphology : string / list, optional
            URL(s) to the morphology file(s) employed in this model.
        license : string
            Indicates the license applicable for this model instance.

        Returns
        -------
        dict
            data of model instance that has been created.

        Examples
        --------
        >>> instance = model_catalog.add_model_instance(model_id="196b89a3-e672-4b96-8739-748ba3850254",
                                                  source="https://www.abcde.com",
                                                  version="1.0",
                                                  description="basic model variant",
                                                  parameters=None,
                                                  code_format="py",
                                                  hash="",
                                                  morphology="",
                                                  license="BSD 3-Clause")
        """

        instance_data = locals()
        instance_data.pop("self")

        for key, val in instance_data.items():
            if val == "":
                instance_data[key] = None

        model_id = model_id or alias
        if not model_id:
            raise Exception(
                "model_id or alias needs to be provided for finding the model."
            )
        else:
            url = self.url + "/models/" + quote(str(model_id)) + "/instances/"

        headers = {"Content-type": "application/json"}
        response = requests.post(
            url,
            data=json.dumps(instance_data),
            auth=self.auth,
            headers=headers,
            verify=self.verify,
        )
        if response.status_code == 201:
            return response.json()
        else:
            handle_response_error("Error in adding model instance", response)

    def find_model_instance_else_add(self, model_obj):
        """Find existing model instance; else create a new instance

        This checks if the input model object has an associated model instance.
        If not, a new model instance is created.

        Parameters
        ----------
        model_obj : object
            Python object representing a model.

        Returns
        -------
        dict
            data of existing or created model instance.

        Note
        ----
        * `model_obj` is expected to contain the attribute `model_instance_uuid`,
          or both the attributes `model_uuid`/`model_alias` and `model_version`.

        Examples
        --------
        >>> instance = model_catalog.find_model_instance_else_add(model)
        """

        if not getattr(model_obj, "model_instance_uuid", None):
            # check that the model is registered with the model registry.
            if not hasattr(model_obj, "model_uuid") and not hasattr(
                model_obj, "model_alias"
            ):
                raise AttributeError(
                    "Model object does not have a 'model_uuid'/'model_alias' attribute. "
                    "Please register it with the Validation Framework and add the 'model_uuid'/'model_alias' to the model object."
                )
            if not hasattr(model_obj, "model_version"):
                raise AttributeError(
                    "Model object does not have a 'model_version' attribute"
                )

            model_instance = self.get_model_instance(
                model_id=getattr(model_obj, "model_uuid", None),
                alias=getattr(model_obj, "model_alias", None),
                version=model_obj.model_version,
            )
            if not model_instance:  # check if instance doesn't exist
                # if yes, then create a new instance
                model_instance = self.add_model_instance(
                    model_id=getattr(model_obj, "model_uuid", None),
                    alias=getattr(model_obj, "model_alias", None),
                    source=getattr(model_obj, "remote_url", ""),
                    version=model_obj.model_version,
                    parameters=getattr(model_obj, "parameters", ""),
                )
        else:
            model_instance = self.get_model_instance(
                instance_id=model_obj.model_instance_uuid
            )
        return model_instance

    def edit_model_instance(
        self,
        instance_id="",
        model_id="",
        alias="",
        source=None,
        version=None,
        description=None,
        parameters=None,
        code_format=None,
        hash=None,
        morphology=None,
        license=None,
    ):
        """Edit an existing model instance.

        This allows to edit an instance of an existing model in the model catalog.
        The model instance can be specified in the following ways (in order of priority):

        1. specify `instance_id` corresponding to model instance in model catalog
        2. specify `model_id` and `version`
        3. specify `alias` (of the model) and `version`

        Only the parameters being updated need to be specified. You cannot
        edit the model `version` in the latter two cases. To do so,
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
        description : string, optional
            Text describing this specific model instance.
        parameters : string, optional
            Any additional parameters to be submitted to model, or used by it, at runtime.
        code_format : string, optional
            Indicates the language/platform in which the model was developed.
        hash : string, optional
            Similar to a checksum; can be used to identify model instances from their implementation.
        morphology : string / list, optional
            URL(s) to the morphology file(s) employed in this model.
        license : string
            Indicates the license applicable for this model instance.

        Returns
        -------
        dict
            data of model instance that has been edited.

        Examples
        --------
        >>> instance = model_catalog.edit_model_instance(instance_id="fd1ab546-80f7-4912-9434-3c62af87bc77",
                                                source="https://www.abcde.com",
                                                version="1.0",
                                                description="passive model variant",
                                                parameters=None,
                                                code_format="py",
                                                hash="",
                                                morphology="",
                                                license="BSD 3-Clause")
        """

        if (
            instance_id == ""
            and (model_id == "" or not version)
            and (alias == "" or not version)
        ):
            raise Exception(
                "instance_id or (model_id, version) or (alias, version) needs to be provided for finding a model instance."
            )

        instance_data = {
            key: value for key, value in locals().items() if value is not None
        }

        # assign existing values for parameters not specified
        if instance_id:
            url = self.url + "/models/query/instances/" + instance_id
        else:
            model_identifier = quote(str(model_id or alias))
            response0 = requests.get(
                self.url + f"/models/{model_identifier}/instances/?version={version}",
                auth=self.auth,
                verify=self.verify,
            )
            if response0.status_code != 200:
                raise Exception("Invalid model_id, alias and/or version")
            model_data = response0.json()[
                0
            ]  # to fix: in principle, can have multiple instances with same version but different parameters
            url = self.url + f"/models/{model_identifier}/instances/{model_data['id']}"

        for key in ["self", "instance_id", "alias", "model_id"]:
            instance_data.pop(key)

        headers = {"Content-type": "application/json"}
        response = requests.put(
            url,
            data=json.dumps(instance_data),
            auth=self.auth,
            headers=headers,
            verify=self.verify,
        )
        if response.status_code == 200:
            return response.json()
        else:
            handle_response_error(
                "Error in editing model instance at {}".format(url), response
            )

    def delete_model_instance(self, instance_id="", model_id="", alias="", version=""):
        """ONLY FOR SUPERUSERS: Delete an existing model instance.

        This allows to delete an instance of an existing model in the model catalog.
        The model instance can be specified in the following ways (in order of priority):

        1. specify `instance_id` corresponding to model instance in model catalog
        2. specify `model_id` and `version`
        3. specify `alias` (of the model) and `version`

        Parameters
        ----------
        instance_id : UUID
            System generated unique identifier associated with model instance.
        model_id : UUID
            System generated unique identifier associated with model description.
        alias : string
            User-assigned unique identifier associated with model description.
        version : string
            User-assigned unique identifier associated with model instance.

        Note
        ----
        * This feature is only for superusers!

        Examples
        --------
        >>> model_catalog.delete_model_instance(model_id="8c7cb9f6-e380-452c-9e98-e77254b088c5")
        >>> model_catalog.delete_model_instance(alias="B1", version="1.0")
        """

        if (
            instance_id == ""
            and (model_id == "" or not version)
            and (alias == "" or not version)
        ):
            raise Exception(
                "instance_id or (model_id, version) or (alias, version) needs to be provided for finding a model instance."
            )

        if instance_id:
            id = instance_id  # as needed by API
        if alias:
            model_alias = alias  # as needed by API

        if instance_id:
            if model_id:
                url = self.url + "/models/" + model_id + "/instances/" + instance_id
            else:
                url = self.url + "/models/query/instances/" + instance_id
        else:
            raise NotImplementedError("Need to retrieve instance to get id")
        model_instance_json = requests.delete(url, auth=self.auth, verify=self.verify)
        if model_instance_json.status_code == 403:
            handle_response_error(
                "Only SuperUser accounts can delete data", model_instance_json
            )
        elif model_instance_json.status_code != 200:
            handle_response_error(
                "Error in deleting model instance", model_instance_json
            )


def _get_ip_address():
    """
    Not foolproof, but allows checking for an external connection with a short
    timeout, before trying socket.gethostbyname(), which has a very long
    timeout.
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except (OSError, URLError, socket.timeout, socket.gaierror):
        return "127.0.0.1"
