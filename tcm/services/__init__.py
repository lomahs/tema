"""Orchestration over domain objects.

Plain functions and small objects: no Flask, no HTTP, no request context. The
routes are jsonify wrappers around what lives here, and the report publisher
calls the same functions the screen does -- which is what stops the numbers on
screen and the numbers in the report drifting apart.
"""
