"""Preserve the distinction between an incorrect cascade and boundary failure."""

import pytest
from rewardkit import WorkerSetupError


WORKER_SETUP_FAILED = pytest.StashKey[bool]()


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_makereport(item, call):
    yield
    if call.excinfo is not None and call.excinfo.errisinstance(WorkerSetupError):
        item.session.stash[WORKER_SETUP_FAILED] = True


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session, exitstatus):
    if session.stash.get(WORKER_SETUP_FAILED, False):
        session.exitstatus = pytest.ExitCode.INTERNAL_ERROR
