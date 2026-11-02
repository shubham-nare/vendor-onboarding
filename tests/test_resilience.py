"""A dropped database connection shouldn't turn a page view into an error (pages only read)."""


def test_dropped_connection_is_recognised_through_wrapping():
    from onboarding.main import is_dropped_connection

    try:
        try:
            raise ConnectionAbortedError("aborted by the local system")
        except OSError as inner:
            raise RuntimeError("driver error") from inner
    except RuntimeError as e:
        assert is_dropped_connection(e)
    assert not is_dropped_connection(ValueError("an actual bug"))


def test_page_is_retried_once_but_a_form_is_not():
    from fastapi.testclient import TestClient

    from onboarding.main import app

    calls = []

    @app.get("/_test_flaky_page")
    async def flaky_page():
        calls.append("get")
        if calls.count("get") == 1:
            raise ConnectionResetError("wifi blip")
        return {"ok": True}

    @app.post("/_test_flaky_form")
    async def flaky_form():
        calls.append("post")
        raise ConnectionResetError("wifi blip")

    c = TestClient(app, raise_server_exceptions=False)  # no lifespan: no database needed
    r = c.get("/_test_flaky_page")
    assert r.status_code == 200 and r.json() == {"ok": True} and calls.count("get") == 2
    assert c.post("/_test_flaky_form").status_code == 500 and calls.count("post") == 1
