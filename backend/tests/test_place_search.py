import json
import urllib.error

import pytest
from fastapi.testclient import TestClient

from app import config
from app.data import osm_loader
from app.data.place_search import (
    PhotonPlaceSearch,
    PlaceSearchUnavailable,
    get_place_search,
    local_matches,
    parse_photon,
    suggest,
)
from app.data.synthetic_graph_generator import generate_synthetic_graph, georeference
from app.main import app
from app.services.graph_store import get_store


def feature(name, lon, lat, **props):
    return {"geometry": {"type": "Point", "coordinates": [lon, lat]}, "properties": {"name": name, **props}}


PHOTON = {
    "features": [
        feature("Koramangala", 77.6241, 12.9357, type="locality", osm_key="place", osm_value="suburb",
                county="Bangalore South", state="Karnataka", country="India"),
        feature("Koramangala 210MLD Pumping Station", 77.6237, 12.9469, type="locality", osm_key="landuse",
                osm_value="industrial", state="Karnataka", country="India"),  # not a place to deliver around
        feature("42", 77.62, 12.93, type="house", osm_key="place", osm_value="house", state="Karnataka"),
        feature("Koramangala", 77.6242, 12.9358, type="locality", osm_key="place", osm_value="suburb",
                county="Bangalore South", state="Karnataka", country="India"),  # same label again
        {"geometry": {"type": "Point", "coordinates": []}, "properties": {"name": "No coordinates"}},
        feature("MG Road", 88.34, 22.66, type="street", osm_key="highway", osm_value="residential",
                city="Titagarh", state="West Bengal", country="India"),
        feature("Bengaluru", 77.59, 12.97, type="city", osm_key="place", osm_value="city",
                county="Bangalore North", state="Karnataka", country="India"),
    ]
}


class FakeResponse:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def make_search(payload=PHOTON, **kwargs):
    calls = []

    def fake_urlopen(request, timeout=None):
        calls.append(request)
        if isinstance(payload, Exception):
            raise payload
        return FakeResponse(payload)

    return PhotonPlaceSearch("https://photon.example/api/", urlopen=fake_urlopen, **kwargs), calls


# ---- reading Photon's answer ---------------------------------------------------------


def test_photon_results_become_labelled_suggestions_without_noise_or_repeats():
    found = parse_photon(PHOTON, limit=10)

    assert [s.label for s in found] == [
        "Koramangala, Bangalore South, Karnataka, India",
        "MG Road, Titagarh, West Bengal, India",
        "Bengaluru, Bangalore North, Karnataka, India",
    ]
    first, road, city = found
    assert (first.lat, first.lon) == (12.9357, 77.6241)  # Photon sends [lon, lat]
    assert (first.title, first.detail, first.kind, first.source) == ("Koramangala", "Bangalore South, Karnataka, India", "suburb", "online")
    assert road.kind == "road" and city.kind == "city"
    assert [s.title for s in parse_photon(PHOTON, limit=2)] == ["Koramangala", "MG Road"]


def test_a_title_is_not_repeated_in_its_own_region_line():
    payload = {"features": [feature("Karnataka", 76.0, 14.0, osm_key="place", osm_value="state", state="Karnataka", country="India")]}
    (only,) = parse_photon(payload, limit=5)
    assert only.label == "Karnataka, India"


# ---- the online searcher ---------------------------------------------------------------


def test_the_request_names_the_query_and_the_app_and_repeats_come_from_the_cache():
    search, calls = make_search()

    first = search.search("Koramang", limit=3)
    again = search.search("  koramang ", limit=3)  # same query typed differently

    assert first == again and len(calls) == 1
    request = calls[0]
    assert request.full_url.startswith("https://photon.example/api/?") and "q=Koramang" in request.full_url
    assert "limit=7" in request.full_url  # a few extra, since non-places are filtered out
    assert "SIH26137" in request.get_header("User-agent")


def test_a_nearby_point_is_sent_as_a_bias_and_keeps_answers_for_different_places_apart():
    search, calls = make_search()

    search.search("indiranagr")
    search.search("indiranagr", near=(12.9758, 77.6068))
    search.search("indiranagr", near=(12.9801, 77.6103))  # same neighbourhood: same cached answer
    search.search("indiranagr", near=(28.6315, 77.2167))  # Delhi: its own answer

    assert len(calls) == 3
    assert "lat=" not in calls[0].full_url
    assert "lat=12.9758" in calls[1].full_url and "lon=77.6068" in calls[1].full_url
    assert "lat=28.6315" in calls[2].full_url


def test_cached_answers_expire_and_the_cache_is_bounded():
    now = [0.0]
    search, calls = make_search(clock=lambda: now[0], cache_ttl_sec=60, cache_size=2)

    search.search("aaa")
    now[0] = 30
    search.search("aaa")
    assert len(calls) == 1
    now[0] = 120  # older than the ttl: asked again
    search.search("aaa")
    assert len(calls) == 2

    search.search("bbb")
    search.search("ccc")  # evicts the oldest entry
    search.search("aaa")
    assert len(calls) == 5


@pytest.mark.parametrize("problem", [urllib.error.URLError("no route to host"), TimeoutError("slow"), ConnectionResetError("reset")])
def test_a_network_problem_is_reported_as_unavailable_and_never_cached(problem):
    search, calls = make_search(payload=problem)
    with pytest.raises(PlaceSearchUnavailable):
        search.search("Koramang")
    with pytest.raises(PlaceSearchUnavailable):
        search.search("Koramang")
    assert len(calls) == 2


def test_an_unexpected_answer_is_unavailable_not_a_crash():
    search, _ = make_search(payload=["not", "geojson"])
    with pytest.raises(PlaceSearchUnavailable):
        search.search("Koramang")


# ---- places we already know ------------------------------------------------------------------


def test_presets_and_remembered_places_match_on_every_word_and_offline():
    osm_loader.remember_place("Koramangala, Bangalore South, Karnataka, India", 12.9357, 77.6241)

    assert [s.label for s in local_matches("mg")] == ["MG Road, Bengaluru"]
    assert local_matches("mg")[0].source == "preset"
    (recent,) = local_matches("koram")
    assert (recent.source, recent.title, recent.detail) == ("recent", "Koramangala", "Bangalore South, Karnataka, India")
    assert [s.label for s in local_matches("road beng")] == ["MG Road, Bengaluru"]  # words in any order
    assert local_matches("zzz") == [] and local_matches("   ") == []


def test_remembered_names_are_capitalised_by_word_without_breaking_ordinals():
    osm_loader.remember_place("koramangala 6th block, bangalore south, karnataka, india", 12.939, 77.6238)
    (recent,) = local_matches("6th")
    assert recent.label == "Koramangala 6th Block, Bangalore South, Karnataka, India"  # not "6Th"


def test_a_remembered_copy_of_a_preset_is_not_listed_twice():
    osm_loader.remember_place("mg road, bengaluru", 12.9758, 77.6068)
    assert len(local_matches("mg road")) == 1


# ---- merging ------------------------------------------------------------------------------------


def test_short_queries_stay_local_and_never_hit_the_network():
    search, calls = make_search()
    found, note = suggest("mg", search)
    assert [s.source for s in found] == ["preset"] and note is None and calls == []


def test_known_places_come_first_and_an_online_copy_of_one_is_dropped():
    search, _ = make_search({"features": [
        feature("MG Road", 77.6069, 12.9759, type="street", osm_key="highway", osm_value="primary",
                city="Bengaluru", state="Karnataka", country="India"),  # ~15 m from the preset
        feature("MG Road", 88.34, 22.66, type="street", osm_key="highway", osm_value="residential",
                city="Titagarh", state="West Bengal", country="India"),
    ]})

    found, note = suggest("MG Road", search)

    assert [(s.source, s.label) for s in found] == [("preset", "MG Road, Bengaluru"), ("online", "MG Road, Titagarh, West Bengal, India")]
    assert note is None


def test_when_online_suggestions_fail_the_saved_places_still_work_and_the_user_is_told():
    search, _ = make_search(payload=urllib.error.URLError("offline"))
    found, note = suggest("MG Road", search)
    assert [s.label for s in found] == ["MG Road, Bengaluru"]
    assert "unavailable" in note and "Enter" in note
    assert "offline" not in note  # the technical reason is logged, not shown


def test_with_online_suggestions_switched_off_there_is_no_warning():
    found, note = suggest("MG Road", None)
    assert [s.label for s in found] == ["MG Road, Bengaluru"] and note is None


def test_the_setting_that_switches_online_suggestions_off(monkeypatch):
    monkeypatch.delenv("PLACE_SEARCH_URL", raising=False)
    monkeypatch.setattr(config, "ENV_FILE", config.ENV_FILE.parent / "does-not-exist.env")
    assert config.place_search_url() == "https://photon.komoot.io/api/"
    monkeypatch.setenv("PLACE_SEARCH_URL", "off")
    assert config.place_search_url() is None and get_place_search() is None
    monkeypatch.setenv("PLACE_SEARCH_URL", "http://localhost:2322/api/")
    assert config.place_search_url() == "http://localhost:2322/api/"
    assert get_place_search() is get_place_search()  # one searcher, so one cache


# ---- the endpoint ----------------------------------------------------------------------------------

client = TestClient(app)


@pytest.fixture
def fake_online():
    search, calls = make_search()
    app.dependency_overrides[get_place_search] = lambda: search
    yield calls
    app.dependency_overrides.pop(get_place_search, None)


def test_the_endpoint_returns_typed_suggestions(fake_online):
    response = client.get("/api/graph/places", params={"q": "Koramang"})

    assert response.status_code == 200
    body = response.json()
    assert body["note"] is None
    assert body["suggestions"][0] == {
        "title": "Koramangala", "detail": "Bangalore South, Karnataka, India",
        "label": "Koramangala, Bangalore South, Karnataka, India", "kind": "suburb",
        "lat": 12.9357, "lon": 77.6241, "source": "online",
    }


def test_the_endpoint_passes_the_map_location_on_as_a_bias(fake_online):
    client.get("/api/graph/places", params={"q": "indiranagr", "lat": 12.9758, "lon": 77.6068})
    client.get("/api/graph/places", params={"q": "indiranagr2", "lat": 12.9758})  # half a point: ignored

    assert "lat=12.9758" in fake_online[0].full_url and "lon=77.6068" in fake_online[0].full_url
    assert "lat=" not in fake_online[1].full_url
    assert client.get("/api/graph/places", params={"q": "abc", "lat": 91, "lon": 0}).status_code == 422


def test_the_endpoint_copes_with_an_empty_or_oversized_query(fake_online):
    assert client.get("/api/graph/places").json() == {"suggestions": [], "note": None}
    assert client.get("/api/graph/places", params={"q": "x" * 101}).status_code == 422
    assert fake_online == []  # neither reached the network


def test_the_places_route_is_not_mistaken_for_a_graph_id(fake_online):
    assert client.get("/api/graph/places", params={"q": "mg"}).status_code == 200


# ---- picking a suggestion ---------------------------------------------------------------------------


@pytest.fixture
def city_loader(monkeypatch):
    get_store().clear()

    def loader(lat, lon, radius_m=1500, network_type="drive", refresh=False):
        graph = generate_synthetic_graph(n_nodes=30, area_size_km=2, seed=5)
        georeference(graph, lat, lon)
        return graph

    monkeypatch.setattr("app.api.graph.load_city_graph", loader)
    monkeypatch.setattr("app.api.graph.geocode", lambda place: pytest.fail("a picked suggestion carries its coordinates"))
    yield
    get_store().clear()


def test_a_picked_suggestion_loads_by_coordinates_and_is_remembered(city_loader):
    label = "Koramangala, Bangalore South, Karnataka, India"
    response = client.post("/api/graph/city", json={"place": label, "lat": 12.9357, "lon": 77.6241, "radius_m": 800})

    assert response.status_code == 200
    assert response.json()["summary"]["label"] == f"{label}, 800 m radius"
    assert osm_loader.remembered_places()[label.lower()] == (12.9357, 77.6241)
    assert [s.source for s in local_matches("koramangala")] == ["recent"]  # suggested offline from now on


def test_loading_a_preset_does_not_add_a_duplicate_to_the_remembered_places(city_loader):
    client.post("/api/graph/city", json={"place": "MG Road, Bengaluru", "lat": 12.9758, "lon": 77.6068})
    assert osm_loader.remembered_places() == {}
