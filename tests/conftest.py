import os
import platform
from datetime import datetime
from time import sleep

from hbp_validation_framework import ModelCatalog, TestLibrary, sample

import pytest

HBP_USERNAME = os.environ.get('HBP_USER')
HBP_PASSWORD = os.environ.get('HBP_PASS')
TOKEN = os.environ.get("HBP_AUTH_TOKEN")  ###


def pytest_addoption(parser):
    parser.addoption(
        "--environment", action="store", default="production", help="options: production or dev"
    )


@pytest.fixture(scope="session")
def modelCatalog(request):
   ENVIRONMENT = request.config.getoption("--environment")
   if HBP_USERNAME and HBP_PASSWORD:
      model_catalog = ModelCatalog(username=HBP_USERNAME, password=HBP_PASSWORD, environment=ENVIRONMENT)
   elif TOKEN:
      model_catalog = ModelCatalog(token=TOKEN, environment=ENVIRONMENT)
   else:
      raise Exception("Credentials not provided. Please define environment variables (HBP_AUTH_TOKEN or HBP_USER and HBP_PASS")
   return model_catalog


@pytest.fixture(scope="session")
def testLibrary(request):
   ENVIRONMENT = request.config.getoption("--environment")
   if HBP_USERNAME and HBP_PASSWORD:
      test_library = TestLibrary(username=HBP_USERNAME, password=HBP_PASSWORD, environment=ENVIRONMENT)
   elif TOKEN:
      test_library = TestLibrary(token=TOKEN, environment=ENVIRONMENT)
   else:
      raise Exception("Credentials not provided. Please define environment variables (HBP_AUTH_TOKEN or HBP_USER and HBP_PASS")
   return test_library


@pytest.fixture(scope="session")
def myModelID(modelCatalog):
   model_catalog = modelCatalog
   model_name = "Model_{}_{}_py{}".format(datetime.now().strftime("%Y-%m-%d_%H:%M:%S"), model_catalog.environment, platform.python_version())
   # todo: need to test with both "single cell" and "network" as model_scope, since these have different KG representations
   model = model_catalog.register_model(collab_id="model-validation", name="IGNORE - Test Model - " + model_name,
                   alias=model_name, author={"family_name": "Tester", "given_name": "Validation"}, organization="HBP-SP6",
                   private=False, cell_type="granule cell", model_scope="single cell",
                   abstraction_level="spiking neurons",
                   brain_region="basal ganglia", species="Mus musculus",
                   owner={"family_name": "Tester", "given_name": "Validation"}, license="BSD 3-Clause",
                   description="This is a test entry! Please ignore.",
                   instances=[{"source":"https://www.abcde.com",
                               "version":"1.0", "parameters":"", "morphology": "http://example.com/mycell.asc"},
                              {"source":"https://www.abcde.com",
                               "version":"1.0a", "parameters":""},
                              {"source":"https://object.cscs.ch/v1/AUTH_c0a333ecf7c045809321ce9d9ecdfdea/sp6_validation_data/test.txt",
                               "version":"2.0a", "parameters":""},
                              {"source":"https://drive.ebrains.eu/lib/0fee1620-062d-4643-865b-951de1eee355/file/CA1_pyr_cACpyr_mpg141017_a1-2_idC_20190328143405.zip",
                               "version":"2.0b", "parameters":""}],
                   images=[{"url":"http://www.neuron.yale.edu/neuron/sites/default/themes/xchameleon/logo.png",
                            "caption":"NEURON Logo"},
                           {"url":"https://raw.githubusercontent.com/HumanBrainProject/hbp-validation-client/master/eu_logo.jpg",
                            "caption":"HBP Logo"}])
   return model["id"]

@pytest.fixture(scope="session")
def myTestID(testLibrary):
   test_library = testLibrary
   test_name = "Test_{}_{}_py{}".format(datetime.now().strftime("%Y-%m-%d_%H:%M:%S"), test_library.environment, platform.python_version())
   test = test_library.add_test(name="IGNORE - Test Test - " + test_name, alias=test_name, author={"family_name": "Tester", "given_name": "Validation"},
                        species="Mus musculus", age="", brain_region="basal ganglia", cell_type="granule cell",
                        recording_modality="electron microscopy", test_type="network structure", score_type="Other", description="Later",
                        data_location="https://object.cscs.ch/v1/AUTH_c0a333ecf7c045809321ce9d9ecdfdea/sp6_validation_data/test.txt",
                        data_type="Mean, SD", publication="Testing et al., 2019",
                        instances=[{"version":"1.0", "repository":"https://github.com/HumanBrainProject/hbp-validation-client.git", "path":"hbp_validation_framework.sample.SampleTest"}])
   isinstance_id = testLibrary.add_test_instance(test_id=test["id"], version="2.0", repository="http://www.12345.com", path="hbp_validation_framework.sample.SampleTest", parameters="", description="")
   return test["id"]


@pytest.fixture(scope="session")
def myResultID(modelCatalog, testLibrary, myModelID, myTestID):
   model_catalog = modelCatalog
   model_id = myModelID
   test_library = testLibrary
   test_id = myTestID
   sleep(20)
   model = model_catalog.get_model(model_id=model_id)
   model = sample.SampleModel(model_uuid=model_id, model_version=model["instances"][0]["version"])

   test_name = "Test_{}_{}_py{}_getValTest_1".format(datetime.now().strftime("%Y-%m-%d_%H:%M:%S"), test_library.environment, platform.python_version())
   test = test_library.add_test(name="IGNORE - Test Test - " + test_name, alias=test_name, author={"family_name": "Tester", "given_name": "Validation"},
              species="Mus musculus", age="", brain_region="basal ganglia", cell_type="granule cell",
              recording_modality="electron microscopy", test_type="network structure", score_type="Other", description="Later",
              data_location="https://object.cscs.ch/v1/AUTH_c0a333ecf7c045809321ce9d9ecdfdea/sp6_validation_data/test.txt",
              data_type="Mean, SD", publication="Testing et al., 2019",
              instances=[{"version":"1.0", "repository":"https://github.com/HumanBrainProject/hbp-validation-client.git", "path":"hbp_validation_framework.sample.SampleTest"}])
   sleep(20)
   test = test_library.get_validation_test(test_id=test["id"])

   score = test.judge(model)
   timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
   folder_name = "results_{}_{}_{}".format(model.name, model.model_uuid[:8], timestamp)
   result = test_library.register_result(score, collab_id="model-validation") # Collab ID for testing
   return result["id"]


def pytest_sessionfinish(session, exitstatus):
   ENVIRONMENT = session.config.getoption("--environment")
   model_catalog = ModelCatalog(username=HBP_USERNAME, password=HBP_PASSWORD, environment=ENVIRONMENT)
   # model_catalog = ModelCatalog(token=TOKEN, environment=ENVIRONMENT)
   models = model_catalog.list_models(collab_id="model-validation", author={"family_name": "Tester", "given_name": "Validation"})
   for model in models:
      if "IGNORE - Test Model - " in model["name"]:
         model_catalog.delete_model(model["id"])
   test_library = TestLibrary.from_existing(model_catalog)
   tests = test_library.list_tests(author={"family_name": "Tester", "given_name": "Validation"})
   for test in tests:
      if "IGNORE - Test Test - " in test["name"]:
         test_library.delete_test(test["id"])
