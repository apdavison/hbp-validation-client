"""
Provides a Mixin class for SciUnit model instances, which provides a version string
based on the Git repository where the model is tracked.

"""

import sys
import os.path
import git


class Versioned(object):
    """
    A Mixin class for SciUnit model instances, which provides a version string
    based on the Git repository where the model is tracked.
    """

    def get_version(self):
        module = sys.modules[self.__module__]
        path = os.path.realpath(module.__path__[0])
        repo = git.Repo(path, search_parent_directories=True)
        head = repo.head
        version = head.commit.hexsha
        if repo.is_dirty():
            version += "*"
        return version

    version = property(get_version)
