"""The page and its assets, which no /api test covers.

Every other test in this suite asks for JSON. If `template_folder` or
`static_folder` were wrong, all of them would still pass and the app would
serve nothing a browser could use -- so this is the only thing standing
between a factory refactor and a blank page.
"""
from tcm.web.app import create_app


def client():
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def test_the_index_page_renders_the_shell():
    response = client().get("/")
    assert response.status_code == 200
    # A view section from templates/index.html: proves the template was found
    # and rendered, not merely that a route answered.
    assert b"summaryView" in response.data


def test_the_static_assets_are_served():
    c = client()
    for path in ("/static/js/main.js", "/static/css/app.css",
                 "/static/css/tokens.css"):
        assert c.get(path).status_code == 200, path
