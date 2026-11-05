"""The reliability score: capped per source, advisory, and honest about sources that aren't connected."""

import asyncio

import httpx

from onboarding import reliability as RL


def sig(source, weight):
    return dict(source=source, weight=weight, title="t", detail="", link="")


def test_each_source_is_capped_and_the_total_is_out_of_100():
    assert RL.score([sig("news", 25), sig("news", 25)]) == 25                   # news alone can't make a vendor high risk
    assert RL.score([sig("history", 40), sig("history", 40), sig("sanctions", 70)]) == 100
    assert RL.level_of(59) == "medium" and RL.level_of(60) == "high" and RL.level_of(10) == "low"


def test_news_searches_the_name_without_the_company_suffix():
    assert RL.search_name("NILGIRI PACKAGING PRIVATE LIMITED") == "NILGIRI PACKAGING"
    assert RL.search_name("Kesari Facility Services Pvt. Ltd.") == "Kesari Facility Services"


def test_keyed_sources_say_not_connected_without_a_key(monkeypatch):
    monkeypatch.setattr(RL, "get_settings", lambda: type("S", (), {"opensanctions_api_key": "", "google_maps_api_key": ""})())
    assert asyncio.run(RL.sanctions("Nilgiri Packaging Private Limited")) == ("not connected", [])
    assert asyncio.run(RL.reviews("Nilgiri Packaging Private Limited", "Bengaluru")) == ("not connected", [])


class FakeClient:
    """Stands in for httpx.AsyncClient: answers every request with one canned response."""
    reply: httpx.Response

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, **k):
        return FakeClient.reply

    async def post(self, url, **k):
        return FakeClient.reply


def _reply(status, payload):
    return httpx.Response(status, json=payload, request=httpx.Request("GET", "https://example.test"))


def test_a_watch_list_hit_on_the_same_name_counts(monkeypatch):
    monkeypatch.setattr(RL, "get_settings", lambda: type("S", (), {"opensanctions_api_key": "k", "google_maps_api_key": ""})())
    monkeypatch.setattr(RL.httpx, "AsyncClient", FakeClient)
    FakeClient.reply = _reply(200, {"results": [{"id": "x1", "caption": "Deccan Office Supplies Pvt Ltd", "properties": {"topics": ["debarment"]}}]})
    st, sigs = asyncio.run(RL.sanctions("DECCAN OFFICE SUPPLIES PRIVATE LIMITED"))
    assert st == "checked" and sigs[0]["weight"] == 70 and "debarment" in sigs[0]["detail"]
    st, sigs = asyncio.run(RL.sanctions("Nilgiri Packaging Private Limited"))      # a different business: no hit
    assert st == "checked" and sigs == []


def test_a_poor_google_rating_counts_a_little_and_a_good_one_not_at_all(monkeypatch):
    monkeypatch.setattr(RL, "get_settings", lambda: type("S", (), {"opensanctions_api_key": "", "google_maps_api_key": "k"})())
    monkeypatch.setattr(RL.httpx, "AsyncClient", FakeClient)
    place = {"displayName": {"text": "Nilgiri Packaging"}, "rating": 2.1, "userRatingCount": 40, "googleMapsUri": "https://maps.example/x"}
    FakeClient.reply = _reply(200, {"places": [place]})
    assert asyncio.run(RL.reviews("NILGIRI PACKAGING PRIVATE LIMITED", "Bengaluru"))[1][0]["weight"] == 20
    FakeClient.reply = _reply(200, {"places": [place | {"rating": 4.5}]})
    assert asyncio.run(RL.reviews("NILGIRI PACKAGING PRIVATE LIMITED", "Bengaluru"))[1][0]["weight"] == 0


def test_news_hits_are_for_a_person_to_check(monkeypatch):
    monkeypatch.setattr(RL.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(RL, "NEWS_GAP", 0)
    arts = [{"title": f"Raid at Kesari Facility Services {i}", "url": f"https://news.example/{i}"} for i in range(4)]
    FakeClient.reply = _reply(200, {"articles": arts})
    st, sigs = asyncio.run(RL.news("Kesari Facility Services Private Limited"))
    assert st == "checked" and sigs[0]["weight"] == 25 and "For a person to check" in sigs[0]["detail"]
    FakeClient.reply = httpx.Response(429, text="Please limit requests", request=httpx.Request("GET", "https://example.test"))
    assert asyncio.run(RL.news("Kesari Facility Services Private Limited")) == ("unavailable", [])   # never a mark against the vendor
