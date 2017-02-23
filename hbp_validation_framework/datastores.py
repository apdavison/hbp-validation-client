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

import os.path
import mimetypes
from bbp_client.oidc.client import BBPOIDCClient
from bbp_client.document_service.client import Client as DocClient
import bbp_services.client as bsc



class CollabDataStore(object):
    """
    A class for uploading data to HBP Collaboratory storage.
    """

    def __init__(self, username, collab_id, base_folder=None):
        self.collab_id = collab_id
        self.base_folder = base_folder

        services = bsc.get_services()

        oidc_client = BBPOIDCClient.implicit_auth(username)
        self.doc_client = DocClient(services['document_service']['prod']['url'], oidc_client)

        project = self.doc_client.get_project_by_collab_id(collab_id)
        self.root = self.doc_client.get_path_by_id(project["_uuid"])

    def upload_data(self, file_paths):
        collab_folder = self.root + "/" + self.base_folder
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
