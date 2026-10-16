"""
e2e teszt: új felhasználó teljes folyamata.

regisztráció -> filmek értékelése -> ajánlás (content-based/popularity,
mert az SVD modellben még nem szerepel) -> értékelés módosítása ->
friss ajánlás -> kijelentkezés/bejelentkezés után is a friss ajánlás
olvasható vissza.

A végpontok a ténylegesen feltöltött routerek (auth.py, movies.py,
ratings.py, recommendations.py) alapján vannak beállítva. Az egyetlen
bizonytalan pont az API_PREFIX ("/api"), mert a main.py (ami a
routereket prefix-eli) nem volt feltöltve – ha nálad nincs ilyen globális
prefix, állítsd API_PREFIX=-re üres stringet.

Futtatás:

    pip install pytest httpx
    BASE_URL=http://localhost:8000 API_PREFIX=/api pytest -v test_user_flow.py
"""

from __future__ import annotations

import os
import random
import string
from typing import Any, Generator

import httpx
import pytest
from httpx import Client

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000")
API_PREFIX = os.environ.get("API_PREFIX", "/api/v1")

ENDPOINT_REGISTER = f"{API_PREFIX}/auth/register"
ENDPOINT_LOGIN = f"{API_PREFIX}/auth/login"
ENDPOINT_MOVIES = f"{API_PREFIX}/movies"
ENDPOINT_RATINGS = f"{API_PREFIX}/ratings"
ENDPOINT_RECOMMENDATIONS = f"{API_PREFIX}/recommendations"

N_RATINGS = 10

def _random_email() -> str:
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    return f"e2e_{suffix}@example.com"


@pytest.fixture(scope="module")
def client() -> Generator[Client, Any, None]:
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as c:
        yield c


@pytest.fixture(scope="module")
def new_user(client: httpx.Client) -> dict:
    """Regisztrál egy új, egyedi felhasználót (RegisterRequest: email, password, display_name)."""
    email = _random_email()
    password = "TesztJelszo123!"

    resp = client.post(
        ENDPOINT_REGISTER,
        json={"email": email, "password": password, "display_name": "E2E Teszt User"},
    )
    assert resp.status_code == 201, f"Regisztráció sikertelen: {resp.status_code} {resp.text}"

    return {"email": email, "password": password}


def _login(client: httpx.Client, email: str, password: str) -> str:
    resp = client.post(ENDPOINT_LOGIN, json={"email": email, "password": password})
    assert resp.status_code == 200, f"Bejelentkezés sikertelen: {resp.status_code} {resp.text}"
    token = resp.json().get("access_token")
    assert token, "Nincs access_token a login válaszban"
    return token


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _get_candidate_movie_ids(client: httpx.Client, n: int) -> list[int]:
    """GET /movies nem igényel autentikációt (lásd movies.py)."""
    resp = client.get(ENDPOINT_MOVIES, params={"page": 1, "page_size": n})
    assert resp.status_code == 200, f"Filmlista lekérése sikertelen: {resp.status_code} {resp.text}"
    items = resp.json()["items"]
    ids = [m["movie_id"] for m in items][:n]
    assert len(ids) >= n, f"Nincs elég film a teszthez (kért: {n}, kapott: {len(ids)})"
    return ids


def _get_recommendations(client: httpx.Client, headers: dict, **params) -> dict:
    resp = client.get(ENDPOINT_RECOMMENDATIONS, headers=headers, params=params)
    assert resp.status_code == 200, f"Ajánlás lekérése sikertelen: {resp.status_code} {resp.text}"
    return resp.json()


class TestNewUserFlow:
    """1. story: regisztráció -> értékelés -> ajánlás -> módosítás -> friss ajánlás."""

    def test_01_register_and_login(self, client: httpx.Client, new_user: dict):
        token = _login(client, new_user["email"], new_user["password"])
        assert token

    def test_02_rate_movies(self, client: httpx.Client, new_user: dict):
        token = _login(client, new_user["email"], new_user["password"])
        headers = _auth_headers(token)

        movie_ids = _get_candidate_movie_ids(client, N_RATINGS)

        for movie_id in movie_ids:
            resp = client.post(
                ENDPOINT_RATINGS,
                json={"movie_id": movie_id, "rating": 5},
                headers=headers,
            )
            assert resp.status_code == 201, (
                f"Értékelés mentése sikertelen (movie_id={movie_id}): "
                f"{resp.status_code} {resp.text}"
            )

    def test_03_recommendation_is_not_svd_for_unknown_user(
        self, client: httpx.Client, new_user: dict
    ):
        """
        A user 10 saját értékeléssel rendelkezik, de nincs benne a legutóbb
        tanított SVD modellben -> egyetlen ajánlási tételnek sem szabad
        "svd"/"hybrid" algoritmus-címkét kapnia valódi SVD-pontozás nélkül
        (Vilmos 2. levél, 3. javítandó pont).
        """
        token = _login(client, new_user["email"], new_user["password"])
        headers = _auth_headers(token)

        data = _get_recommendations(client, headers, top_n=10)
        items = data["items"]
        assert items, "Üres ajánláslista egy 10 értékeléssel rendelkező usernél"

        algorithms = {item["algorithm"] for item in items}
        assert not algorithms & {"svd", "hybrid"}, (
            f"Ismeretlen (nem tanított) user 'svd'/'hybrid' címkét kapott: {algorithms}"
        )

    def test_04_modify_rating_changes_recommendation(
        self, client: httpx.Client, new_user: dict
    ):
        """
        FONTOS a recommendations.py tényleges logikája alapján: a cache
        csak akkor invalidálódik, ha egy MÁR AJÁNLOTT film kerül
        értékelésre (lásd `any(r.movie_id in rated_ids for r in cached)`
        a routerben). Ezért itt szándékosan a kapott ajánlások közül
        értékelünk egyet, nem egy tetszőleges film listából vett elemet –
        különben a teszt a router jelenlegi viselkedése mellett hamisan
        bukna (vagy hamisan menne át, anélkül hogy a valódi invalidációs
        utat lefedné).
        """
        token = _login(client, new_user["email"], new_user["password"])
        headers = _auth_headers(token)

        before = _get_recommendations(client, headers, top_n=10)
        before_items = before["items"]
        assert before_items, "Nincs ajánlás, amit értékelni lehetne"
        target_movie_id = before_items[0]["movie_id"]
        before_ids = {item["movie_id"] for item in before_items}

        resp = client.post(
            ENDPOINT_RATINGS,
            json={"movie_id": target_movie_id, "rating": 1},
            headers=headers,
        )
        assert resp.status_code == 201, f"Értékelés mentése sikertelen: {resp.text}"

        after = _get_recommendations(client, headers, top_n=10)
        after_items = after["items"]
        after_ids = {item["movie_id"] for item in after_items}

        assert target_movie_id not in after_ids, (
            "A frissen (akár alacsonyra) értékelt film nem tűnt el az ajánlásból – "
            "cache invalidáció vagy real-time kizárás hibája"
        )
        assert after["source"] in ("realtime", "precomputed"), f"Váratlan source: {after['source']}"
        assert before_ids != after_ids, (
            "Az ajánlás egyáltalán nem változott az értékelés módosítása után"
        )

    def test_05_recommendation_persists_after_relogin(
        self, client: httpx.Client, new_user: dict
    ):
        """
        A második lekérésnek cache-találatnak kell lennie (source=precomputed),
        mert az első hívás már elmentette az eredményt és nem rögzítettünk
        közben új, az ajánlásban szereplő film értékelést. Ha a második hívás
        is "realtime", az azt jelzi, hogy a cache nem él túl egy relogin-t –
        ez önmagában még nem feltétlenül hiba, de érdemes megjegyezni a
        test_report.md "Ismert hiányosságok" részében.
        """
        token1 = _login(client, new_user["email"], new_user["password"])
        headers1 = _auth_headers(token1)
        first = _get_recommendations(client, headers1, top_n=10)
        first_ids = [item["movie_id"] for item in first["items"]]

        token2 = _login(client, new_user["email"], new_user["password"])
        headers2 = _auth_headers(token2)
        second = _get_recommendations(client, headers2, top_n=10)
        second_ids = [item["movie_id"] for item in second["items"]]

        my_ratings = client.get(ENDPOINT_RATINGS, headers=headers2, params={"page_size": 100})
        assert my_ratings.status_code == 200
        rated_ids = {r["movie_id"] for r in my_ratings.json()["items"]}

        assert not (rated_ids & set(second_ids)), (
            "Egy már értékelt film visszaköszön az újra-bejelentkezés utáni ajánlásban "
            "(elavult/duplikált cache gyanúja)"
        )
        assert first_ids == second_ids, (
            f"Az ajánlás nem konzisztens két egymást követő bejelentkezés között "
            f"(first={first_ids}, second={second_ids}, second_source={second['source']})"
        )


class TestKnownUserSvdActivation:
    """
    2. flow: ha van olyan ismert (DB-ben régóta szereplő, a legutóbb tanított
    SVD modellbe bekerült) teszt felhasználó, azzal ellenőrizzük, hogy az
    SVD/hybrid ajánló ténylegesen aktiválódik.

        pytest -v --known-user-email=user@example.com --known-user-password=secret

    Ha nincs ismert teszt user megadva, a teszt kihagyva (skip).
    """

    @pytest.fixture(scope="session")
    @classmethod
    def known_user(cls, request):
        email = request.config.getoption("--known-user-email")
        password = request.config.getoption("--known-user-password")
        if not email or not password:
            pytest.skip("--known-user-email / --known-user-password nincs megadva")
        return {"email": email, "password": password}

    def test_svd_activates_for_known_user(
        self, client: httpx.Client, known_user: dict
    ):
        token = _login(client, known_user["email"], known_user["password"])
        headers = _auth_headers(token)

        data = _get_recommendations(client, headers, top_n=10, refresh=True)
        algorithms = {item["algorithm"].split(":")[0] for item in data["items"]}
        assert algorithms & {"svd", "hybrid"}, (
            f"Ismert, tanított user nem kapott SVD/hybrid ajánlást: {algorithms}"
        )
