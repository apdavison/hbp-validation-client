import platform
import uuid
from datetime import datetime
from time import sleep

from hbp_validation_framework import sample

import pytest
from .conftest import TESTING_COLLAB


"""
1. Register a test result
"""

# 1.1) With valid details
def test_register_result_valid(modelCatalog, testLibrary, myModelID, myTestID):
    model_catalog = modelCatalog
    model_id = myModelID
    test_library = testLibrary
    test_id = myTestID
    sleep(20)
    model = model_catalog.get_model(model_id=model_id)
    model = sample.SampleModel(
        model_uuid=model_id, model_version=model["instances"][0]["version"]
    )

    test_name = "Test_{}_{}_py{}_getValTest_1".format(
        datetime.now().strftime("%Y%m%d-%H%M%S"),
        test_library.environment,
        platform.python_version(),
    )
    test = test_library.add_test(
        collab_id=TESTING_COLLAB,
        name="IGNORE - Test Test - " + test_name,
        alias=test_name,
        author={"family_name": "Tester", "given_name": "Validation"},
        species="Mus musculus",
        age="",
        brain_region="collection of basal ganglia",
        cell_type="granule cell",
        recording_modality="electron microscopy",
        test_type="network: microcircuit",
        score_type="mean squared error",
        description="Later",
        data_location="https://object.cscs.ch/v1/AUTH_c0a333ecf7c045809321ce9d9ecdfdea/sp6_validation_data/test.txt",
        data_type="Mean, SD",
        publication="Testing et al., 2019",
        instances=[
            {
                "version": "1.0",
                "repository": "https://github.com/HumanBrainProject/hbp-validation-client.git",
                "path": "hbp_validation_framework.sample.SampleTest",
            }
        ],
    )
    sleep(20)
    test = test_library.get_validation_test(test_id=test["id"])

    score = test.judge(model)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    folder_name = "results_{}_{}_{}".format(model.name, model.model_uuid[:8], timestamp)

    result = test_library.register_result(score, collab_id=TESTING_COLLAB)
    assert isinstance(uuid.UUID(result["id"], version=4), uuid.UUID)


"""
2. Get a test result
"""

# 2.1) With valid details
def test_get_result_valid_order_default(testLibrary, myResultID):
    test_library = testLibrary
    result_id = myResultID
    sleep(30)
    result = test_library.get_result(result_id=result_id)
    assert isinstance(result, dict)
    assert result["id"] == result_id


"""
3. List results satisfying specified filters
"""

# 3.1) With valid details - default order = results
def test_list_results_valid(testLibrary, myTestID, myResultID):
    test_library = testLibrary
    test_id = myTestID
    sleep(20)
    result = test_library.list_results(test_id=test_id)
    assert isinstance(result, list)


# 3.2) No filters
# because it takes too long to get all results, fetch first 10 and test 'size' parameter
def test_list_results_no_filter(testLibrary):
    test_library = testLibrary
    results = test_library.list_results(size=10)
    assert isinstance(results, list)
    assert len(results) == 10


# 3.3) Check if 'from_index' parameter works as expected
def test_list_results_no_filter_check_index(testLibrary):
    test_library = testLibrary
    results1 = test_library.list_results(size=5, from_index=0)
    results2 = test_library.list_results(size=5, from_index=4)
    assert isinstance(results1, list)
    assert len(results1) == 5
    assert isinstance(results2, list)
    assert len(results2) == 5
    assert results1[-1]["id"] == results2[0]["id"]
