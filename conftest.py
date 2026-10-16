import pytest

def pytest_addoption(parser):
    parser.addoption(
        "--known-user-email",
        action="store",
        default=None,
        help="Email address",
    )
    parser.addoption(
        "--known-user-password",
        action="store",
        default=None,
        help="Password",
    )
