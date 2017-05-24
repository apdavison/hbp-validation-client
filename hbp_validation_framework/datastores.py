"""
Defines classes for interacting with remote data stores.

Currently supported:
    - HBP Collaboratory storage

Other possibilities:
    - Fenix storage
    - Zenodo
    - Open Science Framework
    - Dropbox
    - OwnCloud
    - ...
"""

import os
import mimetypes
import json
try:
    input = raw_input  # Py2
    from urllib import urlretrieve
    from urlparse import urlparse
except (NameError, ImportError):
    from urllib.request import urlretrieve  # Py3
    from urllib.parse import urlparse
import mimetypes
import requests
from bbp_client.oidc.client import BBPOIDCClient
from bbp_client.document_service.client import Client as DocClient
import bbp_services.client as bsc

# todo: replace bbp_client and bbp_services with hbp_service_client


class FileSystemDataStore(object):
    """
    A class for interacting with the local file system
    """

    def __init__(self):
        pass

    def load_data(self, local_path):
        with open(local_path) as fp:
            observation_data = json.load(fp)


class CollabDataStore(object):
    """
    A class for uploading data to HBP Collaboratory storage.
    """

    def __init__(self, username=None, collab_id=None, base_folder=None, auth=None):
        self.collab_id = collab_id
        self.base_folder = base_folder
        self.username = username
        self._auth = auth  # we defer authorization until needed
        self._authorized = False

    @property
    def authorized(self):
        return self._authorized

    def authorize(self, auth=None):
        services = bsc.get_services()
        if auth is None:
            if self.username is None:
                self.username = os.environ.get('HBP_USERNAME', None)
                if self.username is None:
                    self.username = input("Please enter your HBP username: ")
            oidc_client = BBPOIDCClient.implicit_auth(self.username)
        else:
            oidc_client = BBPOIDCClient.bearer_auth(services['oidc_service']['prod']['url'], auth.token)
        self.doc_client = DocClient(services['document_service']['prod']['url'], oidc_client)
        # 'https://services.humanbrainproject.eu/document/v0/api'
        self._authorized = True

    def upload_data(self, file_paths):
        if not self.authorized:
            self.authorize(self._auth)
        project = self.doc_client.get_project_by_collab_id(self.collab_id)
        root = self.doc_client.get_path_by_id(project["_uuid"])
        collab_folder = root + "/" + self.base_folder
        self.doc_client.mkdir(collab_folder)

        if len(file_paths) > 1:
            common_prefix = os.path.commonprefix(file_paths)
            assert common_prefix[-1] == "/"
        else:
            common_prefix = os.path.dirname(file_paths[0])
        relative_paths = [os.path.relpath(p, common_prefix) for p in file_paths]

        collab_paths = []
        for local_path, relative_path in zip(file_paths, relative_paths):
            collab_path = os.path.join(collab_folder, relative_path)
            if os.path.dirname(relative_path):  # if there are subdirectories...
                self.doc_client.makedirs(os.path.dirname(collab_path))
            id = self.doc_client.upload_file(local_path, collab_path)
            collab_paths.append(collab_path)
            content_type = mimetypes.guess_type(local_path)[0]
            if content_type:
                self.doc_client.set_standard_attr(collab_path, {'_contentType': content_type})  # this doesn't seem to be working
        return "collab://{}".format(collab_folder)

    def download_data(self, remote_paths, local_directory="."):
        if not self.authorized:
            self.authorize(self._auth)
        if isinstance(remote_paths, str):
            remote_paths = [remote_paths]
        local_paths = []
        for remote_path in remote_paths:
            local_path = os.path.join(local_directory, os.path.basename(remote_path))
            self.doc_client.download_file(remote_path, local_path)
            local_paths.append(local_path)
        return local_paths

    def load_data(self, remote_path):
        if not self.authorized:
            self.authorize(self._auth)
        # need to support other formats besides JSON
        if remote_path.startswith("collab:/"):
            remote_path = remote_path[len("collab:/"):]
        return json.loads(self.doc_client.download_file(remote_path))


class HTTPDataStore(object):
    """
    A class for downloading data from the web.
    """

    def upload_data(self, file_paths):
        raise NotImplementedError("The HTTPDataStore does not support uploading data.")

    def download_data(self, remote_paths, local_directory="."):
        local_paths = []
        for url in remote_paths:
            local_path = os.path.join(local_directory, os.path.basename(urlparse(url).path))
            filename, headers = urlretrieve(url, local_path)
            local_paths.append(filename)
        return local_paths

    def load_data(self, remote_path):
        content_type, encoding = mimetypes.guess_type(remote_path)
        if content_type == "application/json":
            return requests.get(remote_path).json()
        else:
            local_paths = self.download_data([remote_path])
            return local_paths[0]


URI_SCHEME_MAP = {
    "collab": CollabDataStore,
    "http": HTTPDataStore,
    "https": HTTPDataStore
}
