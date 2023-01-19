"""
Defines classes for interacting with remote data stores.

Currently supported:
    - EBRAINS Collaboratory v2 seafile storage
    - Swift CSCS storage
    - ModelDB

Other possibilities:
    - Fenix storage
    - Zenodo
    - Open Science Framework
    - Figshare
    - Dropbox
    - OwnCloud
    - ...
"""

import os
import json
import mimetypes
from warnings import warn
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlretrieve

import requests

import ebrains_drive

mimetypes.init()


class FileSystemDataStore(object):
    """
    A class for interacting with the local file system
    """

    def __init__(self, **kwargs):
        pass

    def load_data(self, local_path):
        with open(local_path) as fp:
            observation_data = json.load(fp)


class _CollabDataStore(object):
    """Base class for data stores that are part of the EBRAINS Collaboratory"""

    def __init__(self, collab_id=None, base_folder="/", auth=None, **kwargs):
        self.collab_id = collab_id
        self.base_folder = base_folder.strip("/")
        self._auth = auth  # we defer authorization until needed
        self._authorized = False

    @property
    def authorized(self):
        return self._authorized

    def _get_relative_paths(self, file_paths):
        if isinstance(file_paths, str):
            file_paths = [file_paths]
        if len(file_paths) > 1:
            common_base_dir = os.path.dirname(os.path.commonprefix(file_paths))
        else:
            common_base_dir = os.path.dirname(file_paths[0])
        return [os.path.relpath(p, common_base_dir) for p in file_paths]


class CollabDriveDataStore(_CollabDataStore):
    """
    A class for uploading and downloading data from EBRAINS Collaboratory Drive storage.
    """

    def authorize(self, auth=None):
        if auth is None:
            auth = self._auth
        self.client = ebrains_drive.DriveApiClient(token=auth.token)
        self._authorized = True
        self.repo = self.client.repos.get_repo_by_url(self.collab_id)

    def upload_data(self, file_paths, overwrite=False):
        if not self.authorized:
            self.authorize(self._auth)

        # make specified base directory
        seafdir_base = self._make_folders(self.base_folder, parent="/")
        relative_paths = self._get_relative_paths(file_paths)
        uploaded_file_paths = []
        upload_path_prefix = "https://drive.ebrains.eu/lib/" + self.repo.id + "/file"
        for local_path, relative_path in zip(file_paths, relative_paths):
            if os.path.dirname(relative_path):
                seafdir_parent = self._make_folders(
                    os.path.dirname(relative_path),
                    parent=os.path.join("/", self.base_folder),
                )
                parent = os.path.join(
                    "/", self.base_folder, os.path.dirname(relative_path)
                )
            else:
                parent = os.path.join("/", self.base_folder)

            filename = os.path.basename(relative_path)
            seafdir = self.repo.get_dir(parent)
            file_entity = seafdir.upload_local_file(local_path, overwrite=overwrite)
            uploaded_file_paths.append(
                {
                    "filepath": upload_path_prefix + file_entity.path,
                    "filesize": file_entity.size,
                }
            )
            # uploaded_file_paths.append(file_entity._get_download_link()) # this does not work as the link changes with token
        return uploaded_file_paths

    def _make_folders(self, folder_path, parent):
        for i, folder_name in enumerate(folder_path.split(os.path.sep)):
            if folder_name:
                seafdir = self.repo.get_dir(parent)
                if not seafdir.check_exists(folder_name):
                    child = seafdir.mkdir(folder_name)
            parent = os.path.join(parent, folder_name)
        return self.repo.get_dir(parent)

    def _download_data_content(self, remote_path):
        if not self.authorized:
            self.authorize(self._auth)
        file_obj = self.repo.get_file(remote_path)
        content = file_obj.get_content()
        return content

    def download_data(self, remote_paths, local_directory=".", overwrite=False):
        """
        Note: This can download one or more files (not directories)
        Example inputs:
        (e.g. part following 'https://drive.ebrains.eu/lib/0fee1620-062d-4643-865b-951de1eee355/file')
        1) /sample-latest.csv
        2) /Dir1/data.json
        """
        if isinstance(remote_paths, str):
            remote_paths = [remote_paths]
        local_paths = []

        if not overwrite:
            # confirm that each target filepath doesn't already exist
            for remote_path in remote_paths:
                local_path = os.path.join(
                    local_directory, os.path.basename(remote_path)
                )
                if os.path.exists(local_path):
                    raise FileExistsError(
                        "Target file path `{}` already exists!\nSet `overwrite=True` if you wish overwrite existing files!".format(
                            local_path
                        )
                    )

        for remote_path in remote_paths:
            local_path = os.path.join(local_directory, os.path.basename(remote_path))
            Path(os.path.dirname(local_path)).mkdir(parents=True, exist_ok=True)
            with open(local_path, "wb") as fp:
                fp.write(self._download_data_content(remote_path))
            local_paths.append(local_path)
        return local_paths

    def load_data(self, remote_path):
        content = self._download_data_content(remote_path)
        content_type = mimetypes.guess_type(remote_path)[0]
        if content_type == "application/json":
            return json.loads(content)
        elif content_type == "text/plain":
            return content.decode("utf-8")
        else:
            return content


class CollabBucketDataStore(_CollabDataStore):
    """
    A class for uploading and downloading data from EBRAINS Collaboratory Bucket (aka DataProxy) storage.
    """

    def authorize(self, auth=None):
        if auth is None:
            auth = self._auth
        self.client = ebrains_drive.BucketApiClient(token=auth.token)
        self._authorized = True
        self.bucket = self.client.buckets.get_bucket(self.collab_id)


    def upload_data(self, file_paths, overwrite=False):
        if not self.authorized:
            self.authorize(self._auth)

        if not overwrite:
            existing_files = self.bucket.ls()

        relative_paths = self._get_relative_paths(file_paths)
        uploaded_file_paths = []
        for local_path, relative_path in zip(file_paths, relative_paths):
            remote_path = os.path.join(self.base_folder, relative_path)
            if not overwrite:
                if remote_path in existing_files:
                    warn(f"File {remote_path} already exists and you have set overwrite=False")

            self.bucket.upload(local_path, remote_path)
            uploaded_file_paths.append(
                {
                    "filepath": f"https://data-proxy.ebrains.eu/api/v1/buckets/{self.collab_id}/{self.base_folder}/{remote_path}",
                    "filesize": os.stat(local_path).st_size,
                }
            )
        return uploaded_file_paths


class HTTPDataStore(object):
    """
    A class for downloading data from the web.
    """

    def __init__(self, **kwargs):
        pass

    def upload_data(self, file_paths):
        raise NotImplementedError("The HTTPDataStore does not support uploading data.")

    def download_data(self, remote_paths, local_directory=".", overwrite=False):
        if isinstance(remote_paths, str):
            remote_paths = [remote_paths]
        local_paths = []

        if not overwrite:
            # confirm that each target filepath doesn't already exist
            for url in remote_paths:
                req = requests.head(url)
                if req.status_code == 200:
                    if url.startswith(
                        "https://senselab.med.yale.edu/modeldb/"
                    ) and url.endswith("&mime=application/zip"):
                        filename = req.headers["Content-Disposition"].split(
                            "filename="
                        )[1]
                    else:
                        filename = url.split("/")[-1]
                local_path = os.path.join(local_directory, filename)
                # local_path = os.path.join(local_directory, os.path.basename(urlparse(url).path))
                if os.path.exists(local_path):
                    raise FileExistsError(
                        "Target file path `{}` already exists!\nSet `overwrite=True` if you wish overwrite existing files!".format(
                            local_path
                        )
                    )

        for url in remote_paths:
            req = requests.head(url)
            if req.status_code == 200:
                if url.startswith(
                    "https://senselab.med.yale.edu/modeldb/"
                ) and url.endswith("&mime=application/zip"):
                    filename = req.headers["Content-Disposition"].split("filename=")[1]
                else:
                    filename = url.split("/")[-1]
            local_path = os.path.join(local_directory, filename)
            # local_path = os.path.join(local_directory, os.path.basename(urlparse(url).path))
            Path(os.path.dirname(local_path)).mkdir(parents=True, exist_ok=True)
            filename, headers = urlretrieve(url, local_path)
            local_paths.append(filename)
        return local_paths

    def load_data(self, remote_path):
        content_type, encoding = mimetypes.guess_type(remote_path)
        if content_type == "application/json":
            return requests.get(remote_path).json()
        else:
            local_paths = self.download_data([remote_path], overwrite=True)
            return local_paths[0]


class SwiftDataStore(object):
    """
    A class for uploading and downloading data from CSCS Swift storage.
    Note: data from public containers can also be downloaded via `HTTPDataStore`
    """

    def __init__(self, **kwargs):
        pass

    def upload_data(
        self,
        file_paths,
        username="",
        container="",
        project=None,
        remote_directory="",
        overwrite=False,
    ):
        try:
            from hbp_archive import Container
        except ImportError:
            print("Please install the following package: hbp_archive")
            return

        print("----------------------------------------------------")
        print("NOTE: The target location is inside a CSCS container")
        print("----------------------------------------------------")
        if not username:
            username = input("Please enter your CSCS username: ")
        if not container:
            container = input("Please enter target container name: ")
        if isinstance(file_paths, str):
            file_paths = [file_paths]
        container_obj = Container(container, username, project=project)
        url_prefix = ""
        if container_obj.public_url:
            url_prefix = container_obj.public_url + "/"
        remote_paths = container_obj.upload(
            file_paths, remote_directory=remote_directory, overwrite=overwrite
        )
        uploaded_file_paths = []
        for ind, f in enumerate(file_paths):
            uploaded_file_paths.append(
                {
                    "filepath": url_prefix + remote_paths[ind],
                    "filesize": os.path.getsize(f),
                }
            )
        return uploaded_file_paths

    def get_container(self, remote_path, username=""):
        try:
            from hbp_archive import Container
        except ImportError:
            print("Please install the following package: hbp_archive")
            return

        name_parts = remote_path.split("swift://cscs.ch/")[1].split("/")
        if name_parts[0].startswith(
            "bp00sp"
        ):  # presuming all project names start like this
            prj_name = name_parts[0]
            ind = 1
        else:
            prj_name = None
            ind = 0
        cont_name = name_parts[ind]
        entity_path = "/".join(name_parts[ind + 1 :])
        pre_path = None
        if not "." in name_parts[-1]:
            dirname = name_parts[-1]
            pre_path = entity_path.replace(dirname, "", 1)

        print("----------------------------------------------------")
        print("NOTE: The target location is inside a CSCS container")
        print("----------------------------------------------------")
        if not username:
            username = input("Please enter your CSCS username: ")
        container = Container(cont_name, username, project=prj_name)
        if prj_name:
            container.project._get_container_info()
        return container, entity_path, pre_path

    def download_data(
        self, remote_paths, local_directory=".", username="", overwrite=False
    ):
        if isinstance(remote_paths, str):
            remote_paths = [remote_paths]
        local_paths = []

        if not overwrite:
            # confirm that each target filepath doesn't already exist
            for remote_path in remote_paths:
                local_path = os.path.join(
                    local_directory, os.path.basename(remote_path)
                )
                if os.path.exists(local_path):
                    raise FileExistsError(
                        "Target file path `{}` already exists!\nSet `overwrite=True` if you wish overwrite existing files!".format(
                            local_path
                        )
                    )

        for remote_path in remote_paths:
            container, entity_path, pre_path = self.get_container(
                remote_path, username=username
            )
            contents = container.list()
            contents_match = [x for x in contents if x.name.startswith(entity_path)]
            for item in contents_match:
                if pre_path:
                    localdir = os.path.join(
                        local_directory, entity_path.replace(pre_path, "", 1)
                    )
                else:
                    localdir = local_directory
                if not "directory" in item.content_type:  # download files
                    outpath = container.download(
                        item.name,
                        local_directory=localdir,
                        with_tree=False,
                        overwrite=False,
                    )
                    if outpath:
                        local_paths.append(outpath)
        return local_paths

    def load_data(self, remote_path, username=""):
        container, entity_path, pre_path = self.get_container(
            remote_path, username=username
        )
        content = container.read(entity_path)
        content_type = mimetypes.guess_type(remote_path)[0]
        if content_type == "application/json":
            return json.loads(content)
        else:
            return content


URI_SCHEME_MAP = {
    "collabv2": CollabDriveDataStore,
    "http": HTTPDataStore,
    "https": HTTPDataStore,
    "swift": SwiftDataStore,
}
