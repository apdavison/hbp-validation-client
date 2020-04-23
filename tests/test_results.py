import pytest
import platform
import uuid
from time import sleep
from hbp_validation_framework import sample
from hbp_validation_framework.datastores import CollabDataStore
from datetime import datetime


"""
1. Register a test result
"""

#1.1) With valid details
def test_register_result_valid(modelCatalog, testLibrary, myModelID, myTestID):
    model_catalog = modelCatalog
    model_id = myModelID
    test_library = testLibrary
    test_id = myTestID
    sleep(20)
    model = model_catalog.get_model(model_id=model_id)
    model = sample.SampleModel(model_uuid=model_id, model_version=model["instances"][0]["version"])

    test_name = "Test_{}_{}_py{}_getValTest_1".format(datetime.now().strftime("%Y-%m-%d_%H:%M:%S"), test_library.environment, platform.python_version())
    test_id = test_library.add_test(name="IGNORE - Test Test - " + test_name, alias=test_name, author={"family_name": "Tester", "given_name": "Validation"},
                    species="Mus musculus", age="", brain_region="basal ganglia", cell_type="granule cell",
                    data_modality="electron microscopy", test_type="network structure", score_type="Other", protocol="Later",
                    data_location="https://object.cscs.ch/v1/AUTH_c0a333ecf7c045809321ce9d9ecdfdea/sp6_validation_data/test.txt",
                    data_type="Mean, SD", publication="Testing et al., 2019",
                    version="1.0", repository="https://github.com/HumanBrainProject/hbp-validation-client.git", path="hbp_validation_framework.sample.SampleTest")
    sleep(20)
    test = test_library.get_validation_test(test_id=test_id)

    score = test.judge(model)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    folder_name = "results_{}_{}_{}".format(model.name, model.model_uuid[:8], timestamp)

    result_id = test_library.register_result(score, project="model-validation")
    assert isinstance(uuid.UUID(result_id, version=4), uuid.UUID)


"""
2. Get a test result
"""

#2.1) With valid details
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

#3.1) With valid details - default order = results
def test_list_results_valid(testLibrary, myTestID, myResultID):
    test_library = testLibrary
    test_id = myTestID
    sleep(20)
    result = test_library.list_results(test_id=test_id)
    assert isinstance(result, list)
