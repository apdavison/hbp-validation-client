import platform
import uuid
from datetime import datetime
from time import sleep

import sciunit

import pytest
from .conftest import TESTING_COLLAB


"""
1] Retrieve a test definition by its test_id or alias.
"""

# 1.1) Without test_id or alias
def test_getTest_none(testLibrary):
    test_library = testLibrary
    with pytest.raises(Exception) as excinfo:
        test = test_library.get_test_definition()
    assert (
        str(excinfo.value)
        == "test_path or test_id or alias needs to be provided for finding a test."
    )


# 1.2) Using test_id
def test_getTest_id(testLibrary, myTestID):
    test_library = testLibrary
    test_id = myTestID
    test = test_library.get_test_definition(test_id=test_id)
    assert test["id"] == test_id


# 1.3) Using alias
def test_getTest_alias(testLibrary, myTestID):
    test_library = testLibrary
    test_id = myTestID
    sleep(20)
    test = test_library.get_test_definition(test_id=test_id)
    test = test_library.get_test_definition(alias=test["alias"])
    assert test["id"] == test_id


# 1.4) Using test_id and alias
def test_getTest_both(testLibrary, myTestID):
    test_library = testLibrary
    test_id = myTestID
    test = test_library.get_test_definition(test_id=test_id)
    test = test_library.get_test_definition(test_id=test_id, alias=test["alias"])
    assert test["id"] == test_id


# 1.5) Using invalid test_id format
def test_getTest_invalid_id_format(testLibrary):
    test_library = testLibrary
    with pytest.raises(Exception) as excinfo:
        test = test_library.get_test_definition(test_id="abcde")
    assert "Error in retrieving test." in str(excinfo.value)


# 1.6) Using invalid test_id value
def test_getTest_invalid_id_value(testLibrary):
    test_library = testLibrary
    with pytest.raises(Exception) as excinfo:
        test = test_library.get_test_definition(test_id=str(uuid.uuid4()))
    assert "Error in retrieving test" in str(excinfo.value)


# 1.7) Using invalid alias
def test_getTest_invalid_alias(testLibrary):
    test_library = testLibrary
    with pytest.raises(Exception) as excinfo:
        test = test_library.get_test_definition(alias="<>(@#%^)")
    assert "Error in retrieving test" in str(excinfo.value)


# 1.8) Using empty test_id
def test_getTest_empty_id(testLibrary):
    test_library = testLibrary
    with pytest.raises(Exception) as excinfo:
        test = test_library.get_test_definition(test_id="")
    assert (
        str(excinfo.value)
        == "test_path or test_id or alias needs to be provided for finding a test."
    )


# 1.9) Using empty alias
def test_getTest_empty_alias(testLibrary):
    test_library = testLibrary
    with pytest.raises(Exception) as excinfo:
        test = test_library.get_test_definition(alias="")
    assert (
        str(excinfo.value)
        == "test_path or test_id or alias needs to be provided for finding a test."
    )


"""
2] List tests satisfying all specified filters
"""

# 2.1) No filters
# because it takes too long to get all tests, fetch first 10 and test 'size' parameter
def test_getList_no_filter(testLibrary):
    test_library = testLibrary
    tests = test_library.list_tests(size=10)
    assert isinstance(tests, list)
    assert len(tests) == 10


# 2.2) Single filter
def test_getList_one_filter(testLibrary, myTestID):
    test_library = testLibrary
    tests = test_library.list_tests(cell_type="hippocampus CA1 pyramidal neuron")
    assert isinstance(tests, list)
    assert len(tests) > 0


# 2.3) Multiple filters
def test_getList_many_filters(testLibrary, myTestID):
    test_library = testLibrary
    tests = test_library.list_tests(
        cell_type="hippocampus CA1 pyramidal neuron",
        brain_region="CA1 field of hippocampus",
        species="Mus musculus",
    )
    assert isinstance(tests, list)
    assert len(tests) > 0


# 2.4) Invalid filter
def test_getList_invalid_filter(testLibrary):
    test_library = testLibrary
    with pytest.raises(Exception) as excinfo:
        tests = test_library.list_tests(abcde="12345")
    assert "The specified filter 'abcde' is an invalid filter!" in str(excinfo.value)


# 2.5) Filter with no matches
def test_getList_nomatch(testLibrary):
    test_library = testLibrary
    tests = test_library.list_tests(data_type="ABCDE")
    assert isinstance(tests, list)
    assert len(tests) == 0


# 2.6) Check if 'from_index' parameter works as expected
def test_getList_no_filter_check_index(testLibrary):
    test_library = testLibrary
    tests1 = test_library.list_tests(size=5, from_index=0)
    tests2 = test_library.list_tests(size=5, from_index=4)
    assert isinstance(tests1, list)
    assert len(tests1) == 5
    assert isinstance(tests2, list)
    assert len(tests2) == 5
    assert tests1[-1]["id"] == tests2[0]["id"]


"""
3] Display list of valid values for fields
"""

# 3.1) No parameters (all)
def test_getTestValid_none(testLibrary):
    test_library = testLibrary
    data = test_library.get_attribute_options()
    assert isinstance(data, dict)
    assert len(data.keys()) > 0


# 3.2) One parameter
def test_getTestValid_one(testLibrary):
    test_library = testLibrary
    data = test_library.get_attribute_options("cell_type")
    assert isinstance(data, list)
    assert len(data) > 0


# 3.3) Multiple parameters
def test_getTestValid_many(testLibrary):
    test_library = testLibrary
    with pytest.raises(TypeError) as excinfo:
        data = test_library.get_attribute_options("cell_type", "brain_region")
    assert "takes at most 2 arguments" in str(
        excinfo.value
    ) or "takes from 1 to 2 positional arguments" in str(excinfo.value)


# 3.4) Invalid parameter
def test_getTestValid_invalid(testLibrary):
    test_library = testLibrary
    with pytest.raises(Exception) as excinfo:
        data = test_library.get_attribute_options("abcde")
    assert "Specified attribute 'abcde' is invalid." in str(excinfo.value)


"""
4] Register a new test on the test catalog
"""

# 4.1) No parameters
def test_addtest_none(testLibrary):
    test_library = testLibrary
    with pytest.raises(Exception) as excinfo:
        test = test_library.add_test()


# 4.2) Missing mandatory parameter (author)
def test_addtest_missingParam(testLibrary):
    test_library = testLibrary
    with pytest.raises(Exception) as excinfo:
        test_name = "Test_{}_{}_py{}_add2".format(
            datetime.now().strftime("%Y%m%d-%H%M%S"),
            test_library.environment,
            platform.python_version(),
        )
        test = test_library.add_test(
            collab_id=TESTING_COLLAB,
            name="IGNORE - Test Test - " + test_name,
            alias=test_name,
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
    assert "field required" in str(excinfo.value)


# 4.3) Invalid value for parameter (brain_region)
def test_addtest_invalidParam(testLibrary):
    test_library = testLibrary
    with pytest.raises(Exception) as excinfo:
        test_name = "Test_{}_{}_py{}_add3".format(
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
            brain_region="ABCDE",
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
    assert "brain_region = 'ABCDE' is invalid." in str(excinfo.value)


# 4.4) Valid test without alias
def test_addtest_valid_noalias_nodetails(testLibrary):
    test_library = testLibrary
    test_name = "Test_{}_{}_py{}_add4".format(
        datetime.now().strftime("%Y%m%d-%H%M%S"),
        test_library.environment,
        platform.python_version(),
    )
    test = test_library.add_test(
        collab_id=TESTING_COLLAB,
        name="IGNORE - Test Test - " + test_name,
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


# 4.5) Valid test with alias
def test_addtest_valid_withalias_nodetails(testLibrary):
    test_library = testLibrary
    test_name = "Test_{}_{}_py{}_add5".format(
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
    assert isinstance(uuid.UUID(test["id"], version=4), uuid.UUID)


# 4.6) Invalid test with repeated alias; without instances
def test_addtest_repeat_alias_nodetails(testLibrary):
    test_library = testLibrary
    test_name = "Test_{}_{}_py{}_add6".format(
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
    with pytest.raises(Exception) as excinfo:
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
    assert "already exists" in str(excinfo.value)


# #4.7) Invalid test with no instances
# def test_addtest_valid_withalias_withdetails(testLibrary):
#     test_library = testLibrary
#     test_name = "Test_{}_{}_py{}_add7".format(datetime.now().strftime("%Y%m%d-%H%M%S"), test_library.environment, platform.python_version())
#     with pytest.raises(Exception) as excinfo:
#         test = test_library.add_test(name="IGNORE - Test Test - " + test_name, alias=test_name, author={"family_name": "Tester", "given_name": "Validation"},
#                         species="Mus musculus", age="", brain_region="collection of basal ganglia", cell_type="granule cell",
#                         recording_modality="electron microscopy", test_type="network: microcircuit", score_type="mean squared error", description="Later",
#                         data_location="https://object.cscs.ch/v1/AUTH_c0a333ecf7c045809321ce9d9ecdfdea/sp6_validation_data/test.txt",
#                         data_type="Mean, SD", publication="Testing et al., 2019")
#     assert "Error in adding test." in str(excinfo.value)


"""
5] Edit an existing test on the test catalog
"""

# 5.1) Invalid change - no test_id
def test_editTest_invalid_noID(testLibrary):
    test_library = testLibrary
    test_name = "Test_{}_{}_py{}_edit1".format(
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
    with pytest.raises(Exception) as excinfo:
        test = test_library.edit_test(
            name="IGNORE - Test Test - " + test_name,
            alias=test["alias"] + "_changed",
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
        )
    assert str(excinfo.value) == "Test ID needs to be provided for editing a test."


# 5.2) Valid change - test_id
def test_editTest_valid(testLibrary):
    test_library = testLibrary
    test_name = "Test_{}_{}_py{}_edit2".format(
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
    test = test_library.edit_test(
        test_id=test["id"],
        name="IGNORE - Test Test - " + test_name,
        alias=test["alias"] + "_changed",
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
    )
    assert isinstance(uuid.UUID(test["id"], version=4), uuid.UUID)


# 5.3) Invalid change - duplicate alias
def test_editTest_invalid_duplicate_alias(testLibrary):
    test_library = testLibrary
    test_name1 = "Test_{}_{}_py{}_edit3.1".format(
        datetime.now().strftime("%Y%m%d-%H%M%S"),
        test_library.environment,
        platform.python_version(),
    )
    test = test_library.add_test(
        collab_id=TESTING_COLLAB,
        name="IGNORE - Test Test - " + test_name1,
        alias=test_name1,
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
    test_name2 = "Test_{}_{}_py{}_edit3.2".format(
        datetime.now().strftime("%Y%m%d-%H%M%S"),
        test_library.environment,
        platform.python_version(),
    )
    test = test_library.add_test(
        collab_id=TESTING_COLLAB,
        name="IGNORE - Test Test - " + test_name2,
        alias=test_name2,
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
    test = test_library.get_test_definition(test_id=test["id"])
    with pytest.raises(Exception) as excinfo:
        test = test_library.edit_test(
            test_id=test["id"],
            name=test["name"] + "_changed",
            alias=test_name1,
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
        )
    assert "already exists" in str(excinfo.value)


# 5.4) Invalid change - version info
def test_editTest_invalid_version_info(testLibrary):
    test_library = testLibrary
    test_name = "Test_{}_{}_py{}_edit4".format(
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
    test = test_library.get_test_definition(test_id=test["id"])
    with pytest.raises(Exception) as excinfo:
        test["id"] = test_library.edit_test(
            test_id=test["id"],
            name="IGNORE - Test Test - " + test_name,
            alias=test["alias"] + "_changed",
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
    assert "got an unexpected keyword argument" in str(excinfo.value)


"""
6. Get 'sciunit' validation test instance
"""

# 6.1) With valid details - test_id
def test_getValidationTest_testID(testLibrary):
    test_library = testLibrary
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
    sleep(30)
    test = test_library.get_validation_test(test_id=test["id"])
    assert isinstance(test, sciunit.Test)
    assert "test.txt" in test.observation
