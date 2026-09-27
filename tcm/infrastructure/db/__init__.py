"""The SQLite database: load snapshots and the test plan.

Every line of SQL in the app lives in this package. The engine is stdlib
`sqlite3` for now; the services reach it only through the ports in
`tcm.domain.ports`, so moving to SQLAlchemy or another database rewrites this
folder and `create_app`, and nothing else.
"""
