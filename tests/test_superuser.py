import os
import platform
from datetime import datetime
from time import sleep

from hbp_validation_framework import ModelCatalog, TestLibrary, sample

import pytest

HBP_USERNAME = os.environ.get('HBP_USER')
HBP_PASSWORD = os.environ.get('HBP_PASS')
TOKEN = os.environ.get("HBP_AUTH_TOKEN")
HBP_USERNAME_NORMAL_USER = os.environ.get('HBP_USER_NORMAL')
HBP_PASSWORD_NORMAL_USER = os.environ.get('HBP_PASS_NORMAL')
TOKEN_NORMAL_USER = os.environ.get("HBP_AUTH_TOKEN_NORMAL")


"""
1. Verify superuser delete privileges
"""

#1.1) Super user - Delete model, model_instance, model_image, test, test_instance and result
def test_delete_superUser(request):
    ENVIRONMENT = request.config.getoption("--environment")

    if HBP_USERNAME and HBP_PASSWORD:
        model_catalog = ModelCatalog(username=HBP_USERNAME, password=HBP_PASSWORD, environment=ENVIRONMENT)
    elif TOKEN:
        model_catalog = ModelCatalog(token=TOKEN, environment=ENVIRONMENT)
    else:
        raise Exception("Credentials not provided. Please define environment variables (HBP_AUTH_TOKEN or HBP_USER and HBP_PASS")

    model_name = "Model_{}_{}_py{}_superuser1".format(datetime.now().strftime("%Y-%m-%d_%H:%M:%S"), model_catalog.environment, platform.python_version())
    model = model_catalog.register_model(collab_id="model-validation", name="IGNORE - Test Model - " + model_name,
                   alias=model_name, author={"family_name": "Tester", "given_name": "Validation"}, organization="HBP-SP6",
                   private=False, cell_type="granule cell", model_scope="single cell",
                   abstraction_level="spiking neurons",
                   brain_region="basal ganglia", species="Mus musculus",
                   owner={"family_name": "Tester", "given_name": "Validation"}, license="BSD 3-Clause",
                   description="This is a test entry! Please ignore.",
                   instances=[{"source":"https://www.abcde.com",
                               "version":"1.0", "parameters":""}],
                   images=[{"url":"http://www.neuron.yale.edu/neuron/sites/default/themes/xchameleon/logo.png",
                            "caption":"NEURON Logo"}])

    model_instance_id = model["instances"][0]["id"]
    #model_image_id = model["images"][0]["id"]
    model_obj = sample.SampleModel(model_uuid=model["id"], model_version=model["instances"][0]["version"])

    test_library = TestLibrary.from_existing(model_catalog)
    test_name = "Test_{}_{}_py{}_superuser2".format(datetime.now().strftime("%Y-%m-%d_%H:%M:%S"), test_library.environment, platform.python_version())
    test = test_library.add_test(name="IGNORE - Test Test - " + test_name, alias=test_name, author={"family_name": "Tester", "given_name": "Validation"},
                    species="Mus musculus", age="", brain_region="basal ganglia", cell_type="granule cell",
                    recording_modality="electron microscopy", test_type="network structure", score_type="Other", description="Later",
                    data_location="https://object.cscs.ch/v1/AUTH_c0a333ecf7c045809321ce9d9ecdfdea/sp6_validation_data/test.txt",
                    data_type="Mean, SD", publication="Testing et al., 2019",
                    instances=[{"version":"1.0", "repository":"https://github.com/HumanBrainProject/hbp-validation-client.git", "path":"hbp_validation_framework.sample.SampleTest"}])

    test_instance_id = test["instances"][0]["id"]
    sleep(20)
    test_obj = test_library.get_validation_test(test_id=test["id"])

    score = test_obj.judge(model_obj)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    folder_name = "results_{}_{}_{}".format(model_obj.name, model_obj.model_uuid[:8], timestamp)
    result = test_library.register_result(score, collab_id = "model-validation") # Collab ID = model-validation

    test_library.delete_result(result_id=result["id"])
    sleep(20)
    with pytest.raises(Exception) as excinfo:
        result = test_library.get_result(result_id=result["id"])
    assert "not found" in str(excinfo.value)

    model_catalog.delete_model_instance(instance_id=model_instance_id)
    sleep(20)
    with pytest.raises(Exception) as excinfo:
        model_instance = model_catalog.get_model_instance(instance_id=model_instance_id)
    assert "Error in retrieving model instance." in str(excinfo.value)

    model_catalog.delete_model(model_id=model["id"])
    sleep(20)
    with pytest.raises(Exception) as excinfo:
        model = model_catalog.get_model(model_id=model["id"])
    assert "Error in retrieving model." in str(excinfo.value)

    test_library.delete_test_instance(instance_id=test_instance_id)
    sleep(20)
    with pytest.raises(Exception) as excinfo:
        test_instance = test_library.get_test_instance(instance_id=test_instance_id)
    assert "Error in retrieving test instance." in str(excinfo.value)

    test_library.delete_test(test_id=test["id"])
    sleep(20)
    with pytest.raises(Exception) as excinfo:
        test = test_library.get_test_definition(test_id=test["id"])
    assert "Error in retrieving test" in str(excinfo.value)


#1.2) Normal user - Delete model, model_instance, model_image, test, test_instance and result
# @pytest.mark.xfail(reason="delete for normal users not handled properly yet?!")
def test_delete_normalUser(request):
    ENVIRONMENT = request.config.getoption("--environment")
    if HBP_USERNAME_NORMAL_USER and HBP_PASSWORD_NORMAL_USER:
        model_catalog = ModelCatalog(username=HBP_USERNAME_NORMAL_USER,
                                     password=HBP_PASSWORD_NORMAL_USER, environment=ENVIRONMENT)
    elif TOKEN:
        model_catalog = ModelCatalog(token=TOKEN_NORMAL_USER, environment=ENVIRONMENT)
    else:
        raise Exception("Credentials not provided. Please define environment variables (HBP_AUTH_TOKEN or HBP_USER and HBP_PASS")
    model_name = "Model_{}_{}_py{}_normaluser1".format(datetime.now().strftime("%Y-%m-%d_%H:%M:%S"), model_catalog.environment, platform.python_version())
    model = model_catalog.register_model(collab_id="validation-tester", name="IGNORE - Test Model - " + model_name,
                   alias=model_name, author={"family_name": "Tester", "given_name": "Validation"}, organization="HBP-SP6",
                   private=False, cell_type="granule cell", model_scope="single cell",
                   abstraction_level="spiking neurons",
                   brain_region="basal ganglia", species="Mus musculus",
                   owner={"family_name": "Tester", "given_name": "Validation"}, license="BSD 3-Clause",
                   description="This is a test entry! Please ignore.",
                   instances=[{"source":"https://www.abcde.com",
                               "version":"1.0", "parameters":""}],
                   images=[{"url":"http://www.neuron.yale.edu/neuron/sites/default/themes/xchameleon/logo.png",
                            "caption":"NEURON Logo"}])

    model_instance_id = model["instances"][0]["id"]
    #model_image_id = model["images"][0]["id"]
    model_obj = sample.SampleModel(model_uuid=model["id"], model_version=model["instances"][0]["version"])

    test_library = TestLibrary.from_existing(model_catalog)
    test_name = "Test_{}_{}_py{}_normaluser2".format(datetime.now().strftime("%Y-%m-%d_%H:%M:%S"), test_library.environment, platform.python_version())
    test = test_library.add_test(name="IGNORE - Test Test - " + test_name, alias=test_name, author={"family_name": "Tester", "given_name": "Validation"},
                    species="Mus musculus", age="", brain_region="basal ganglia", cell_type="granule cell",
                    recording_modality="electron microscopy", test_type="network structure", score_type="Other", description="Later",
                    data_location="https://object.cscs.ch/v1/AUTH_c0a333ecf7c045809321ce9d9ecdfdea/sp6_validation_data/test.txt",
                    data_type="Mean, SD", publication="Testing et al., 2019",
                    instances=[{"version":"1.0", "repository":"https://github.com/HumanBrainProject/hbp-validation-client.git", "path":"hbp_validation_framework.sample.SampleTest"}])
    
    test_instance_id = test["instances"][0]["id"]
    sleep(20)
    test_obj = test_library.get_validation_test(test_id=test["id"])

    score = test_obj.judge(model_obj)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    folder_name = "results_{}_{}_{}".format(model_obj.name, model_obj.model_uuid[:8], timestamp)

    result = test_library.register_result(score, collab_id="validation-tester") # Collab ID = validation-tester

    # normal users cannot delete results
    with pytest.raises(Exception) as excinfo:
        test_library.delete_result(result_id=result["id"])
    assert "Only SuperUser accounts can delete data." in str(excinfo.value)

    # normal users can delete model instances that they have write access to
    model_catalog.delete_model_instance(instance_id=model_instance_id)

    # normal users can delete models that they have write access to
    model_catalog.delete_model(model_id=model["id"])

    # normal users cannot delete test instances
    with pytest.raises(Exception) as excinfo:
        test_library.delete_test_instance(instance_id=test_instance_id)
    assert "Only SuperUser accounts can delete data." in str(excinfo.value)

    # normal users cannot delete tests
    with pytest.raises(Exception) as excinfo:
        test_library.delete_test(test_id=test["id"])
    assert "Only SuperUser accounts can delete data." in str(excinfo.value)
