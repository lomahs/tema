"""One blueprint per resource.

A blueprint reads the request, calls a service and jsonifies the answer. It
holds no state: the services live on the app, which is what lets one be built
differently for a test without reaching into a module.
"""
from flask import current_app


def workspace():
    """The Workspace this app was built with."""
    return current_app.extensions["workspace"]


def identity():
    """The IdentityService this app was built with."""
    return current_app.extensions["identity"]


def planning():
    """The PlanningService this app was built with."""
    return current_app.extensions["planning"]
