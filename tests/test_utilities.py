import os
import uuid
from time import sleep

import sciunit
from ebrains_validation_framework import sample, utils

import pytest


"""
1] Tests `view_json_tree`
"""


def test_view_json_tree(modelCatalog, myModelID):
    model_catalog = modelCatalog
    model_id = myModelID
    model = model_catalog.get_model(model_id=model_id)
    utils.view_json_tree(model)


"""
2] Tests `generate_report`
"""


def test_generate_HTML_report(modelCatalog, myResultID):
    model_catalog = modelCatalog
    result_id = myResultID
    sleep(20)
    report_path, valid_uuids = utils.generate_HTML_report(client_obj=model_catalog, result_list=[result_id])
    assert isinstance(valid_uuids, list)
    assert len(valid_uuids) == 1
    assert isinstance(uuid.UUID(valid_uuids[0], version=4), uuid.UUID)
    assert os.path.isfile(report_path)


"""
3] Tests `prepare_run_test_offline()`
"""


def test_prepare_run_test_offline(testLibrary, myTestID):
    test_library = testLibrary
    test_id = myTestID

    sleep(10)
    test = test_library.get_test_definition(test_id=test_id)
    test_config_file = utils.prepare_run_test_offline(
        test_id=test_id,
        test_version=test["instances"][0]["version"],
        client_obj=test_library,
    )
    assert os.path.isfile(test_config_file)


"""
4] Tests `run_test_offline()`
"""


def test_run_test_offline(modelCatalog, testLibrary, myModelID, myTestID):
    model_catalog = modelCatalog
    model_id = myModelID
    test_library = testLibrary
    test_id = myTestID

    sleep(10)
    test = test_library.get_test_definition(test_id=test_id)
    test_config_file = utils.prepare_run_test_offline(
        test_id=test_id,
        test_version=test["instances"][0]["version"],
        client_obj=test_library,
    )
    model = model_catalog.get_model(model_id=model_id)
    test_model = sample.SampleModel(model_instance_uuid=model["instances"][0]["id"])
    test_result_file = utils.run_test_offline(model=test_model, test_config_file=test_config_file)
    assert os.path.isfile(test_result_file)


"""
5] Tests `upload_test_result()`
"""


def test_upload_test_result(modelCatalog, testLibrary, myModelID, myTestID):
    model_catalog = modelCatalog
    model_id = myModelID
    test_library = testLibrary
    test_id = myTestID

    sleep(20)
    test = test_library.get_test_definition(test_id=test_id)
    test_config_file = utils.prepare_run_test_offline(
        test_id=test_id,
        test_version=test["instances"][0]["version"],
        client_obj=test_library,
    )
    model = model_catalog.get_model(model_id=model_id)
    test_model = sample.SampleModel(model_instance_uuid=model["instances"][0]["id"])
    test_result_file = utils.run_test_offline(model=test_model, test_config_file=test_config_file)
    result, score = utils.upload_test_result(test_result_file=test_result_file, client_obj=test_library)
    assert isinstance(uuid.UUID(result["id"], version=4), uuid.UUID)
    assert isinstance(score, float)


"""
6] Tests `run_test()`
"""


def test_run_test_combined(modelCatalog, testLibrary, myModelID, myTestID):
    model_catalog = modelCatalog
    model_id = myModelID
    test_library = testLibrary
    test_id = myTestID

    sleep(20)
    test = test_library.get_test_definition(test_id=test_id)
    model = model_catalog.get_model(model_id=model_id)
    test_model = sample.SampleModel(model_instance_uuid=model["instances"][0]["id"])

    result, score = utils.run_test(
        model=test_model,
        test_id=test_id,
        test_version=test["instances"][0]["version"],
        client_obj=test_library,
    )
    assert isinstance(uuid.UUID(result["id"], version=4), uuid.UUID)
    assert isinstance(score, float)
