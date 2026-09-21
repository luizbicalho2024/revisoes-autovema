from pymongo.errors import AutoReconnect, NotPrimaryError, OperationFailure

from src.db import is_transient_mongo_error


def test_not_primary_is_transient():
    assert is_transient_mongo_error(NotPrimaryError("not primary")) is True


def test_auto_reconnect_is_transient():
    assert is_transient_mongo_error(AutoReconnect("connection changed")) is True


def test_not_writable_primary_code_is_transient():
    exc = OperationFailure(
        "not primary",
        code=10107,
        details={"code": 10107, "codeName": "NotWritablePrimary"},
    )
    assert is_transient_mongo_error(exc) is True


def test_generic_operation_failure_is_not_transient():
    exc = OperationFailure(
        "authentication failed",
        code=18,
        details={"code": 18},
    )
    assert is_transient_mongo_error(exc) is False
