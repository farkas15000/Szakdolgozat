"""
E2E teszt: egy korábban kedvelt film értékelésének visszavonása (módosítás / törlés)
után az ajánlás a FRISS visszajelzésből számolódik, nem egy korábban eltárolt állapotból.

A vállalás (Vilmos, okt. 17.): "egy korábban kedvelt filmről megváltozhat a felhasználó
véleménye, és ezt a következő ajánlás figyelembe veszi".

Mit bizonyít a teszt (a webes véletlen változatosság, random.sample miatt NEM konkrét
filmlistákat hasonlít össze, hanem megfigyelhető, determinisztikus jeleket):
  1. a baseline ajánlás cache-be kerül (2. lekérés: source == "precomputed", azonos lista);
  2. PUT /ratings/{id} (kedvelés visszavonása) után a cache üres, az ajánlás újra
     számolódik (source == "realtime"), és nem tartalmaz értékelt filmet;
  3. ugyanazon filmek content-based pontszáma megváltozik (a profil tényleg más);
  4. új belépés után ugyanaz olvasható vissza, mint a friss számolás eredménye;
  5. DELETE /ratings/{id} után ugyanez igaz;
  6. ha már egyetlen film sem "kedvelt", érthető, nem üres tartalékajánlás jön.

Futtatás (a backend fut):
    BASE_URL=http://localhost:8000 API_PREFIX=/api pytest test_feedback_revoke.py -v
"""

from __future__ import annotations

import os
import uuid

import httpx
import pytest

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000")
API_PREFIX = os.environ.get("API_PREFIX", "/api/v1")

LIKED_RATING = 5.0
REVOKED_RATING = 1.0
# Eltérő jellegű műfajok → eltérő ízlésprofil-komponensek
GENRES = ["Action", "Drama", "Comedy", "Sci-Fi", "Animation"]


def _url(path: str) -> str:
    return f"{BASE_URL}{API_PREFIX}{path}"


@pytest.fixture(scope="module")
def client():
    with httpx.Client(timeout=60.0) as c:
        yield c


class _State:
    """Az egymásra épülő tesztek közös állapota (modulon belül)."""
    email: str = f"revoke_{uuid.uuid4().hex[:10]}@example.com"
    password: str = "Teszt1234!"
    liked: list[int] = []
    baseline_ids: list[int] = []
    baseline_scores: dict[int, float] = {}
    after_put_ids: list[int] = []


S = _State


def _login(client: httpx.Client) -> dict[str, str]:
    r = client.post(_url("/auth/login"), json={"email": S.email, "password": S.password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _recs(client: httpx.Client, headers: dict, top_n: int = 20) -> dict:
    r = client.get(_url("/recommendations"), params={"top_n": top_n}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def _rated_ids(client: httpx.Client, headers: dict) -> set[int]:
    ids: set[int] = set()
    page = 1
    while True:
        r = client.get(_url("/ratings"), params={"page": page, "page_size": 100}, headers=headers)
        assert r.status_code == 200, r.text
        body = r.json()
        ids |= {it["movie_id"] for it in body["items"]}
        if page >= body["pages"]:
            return ids
        page += 1


def _pick_one_movie_per_genre(client: httpx.Client) -> list[int]:
    """Műfajonként egy-egy (egymástól különböző) film – auth nélkül lekérhető."""
    picked: list[int] = []
    for genre in GENRES:
        r = client.get(_url("/movies"), params={"genre": genre, "page_size": 30})
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        # a lista közepéről választunk, hogy ne csak az ábécé eleje (ismeretlen filmek) legyen
        candidates = [m["movie_id"] for m in items[10:] if m["movie_id"] not in picked] or \
                     [m["movie_id"] for m in items if m["movie_id"] not in picked]
        assert candidates, f"Nincs film a(z) {genre} műfajban"
        picked.append(candidates[0])
    assert len(set(picked)) == len(GENRES)
    return picked


class TestRevokeLikedRating:
    def test_01_baseline_recommendation_is_cached(self, client):
        # regisztráció + belépés
        r = client.post(
            _url("/auth/register"),
            json={"email": S.email, "password": S.password, "display_name": "Revoke Teszt"},
        )
        assert r.status_code == 201, r.text
        headers = _login(client)

        # néhány eltérő jellegű kedvelt film
        S.liked = _pick_one_movie_per_genre(client)
        for mid in S.liked:
            r = client.post(_url("/ratings"), json={"movie_id": mid, "rating": LIKED_RATING}, headers=headers)
            assert r.status_code == 201, r.text

        first = _recs(client, headers)
        assert first["items"], "A baseline ajánlás nem lehet üres"
        S.baseline_ids = [it["movie_id"] for it in first["items"]]
        S.baseline_scores = {
            it["movie_id"]: it["score"] for it in first["items"] if it["algorithm"] == "content_based"
        }

        # a baseline ajánlás cache-be került: a második lekérés ugyanazt adja
        second = _recs(client, headers)
        assert second["source"] == "precomputed", (
            "A második lekérésnek cache-ből kell jönnie – különben a későbbi 'realtime' "
            "ellenőrzés nem bizonyítana semmit."
        )
        assert [it["movie_id"] for it in second["items"]] == S.baseline_ids

    def test_02_revoking_a_liked_rating_invalidates_cache_and_recomputes(self, client):
        headers = _login(client)
        revoked_movie = S.liked[0]

        r = client.put(
            _url(f"/ratings/{revoked_movie}"), json={"rating": REVOKED_RATING}, headers=headers
        )
        assert r.status_code == 200, r.text

        # az új értékelés visszaolvasható
        r = client.get(_url(f"/ratings/{revoked_movie}"), headers=headers)
        assert r.status_code == 200
        assert r.json()["rating"] == REVOKED_RATING

        # a cache üres → friss generálás
        after = _recs(client, headers)
        assert after["source"] == "realtime", (
            "A kedvelés visszavonása után a tárolt ajánlást el kell dobni, és újra kell számolni."
        )
        S.after_put_ids = [it["movie_id"] for it in after["items"]]
        assert S.after_put_ids, "Az új ajánlás nem lehet üres"
        assert len(S.after_put_ids) == len(set(S.after_put_ids)), "Nem lehet duplikátum"

        # értékelt film nem szerepelhet az ajánlásban
        assert not (set(S.after_put_ids) & _rated_ids(client, headers))

        # a profil tényleg megváltozott: ugyanazon filmek content-based pontszáma eltér
        after_scores = {
            it["movie_id"]: it["score"] for it in after["items"] if it["algorithm"] == "content_based"
        }
        common = set(S.baseline_scores) & set(after_scores)
        if common:
            assert any(abs(S.baseline_scores[m] - after_scores[m]) > 1e-9 for m in common), (
                "A közös filmek pontszáma azonos maradt – az ajánlás nem a friss "
                "ízlésprofilból számolódott."
            )

    def test_03_fresh_result_is_what_a_new_login_reads_back(self, client):
        headers = _login(client)  # új belépés
        again = _recs(client, headers)
        assert again["source"] == "precomputed"
        assert [it["movie_id"] for it in again["items"]] == S.after_put_ids

        r = client.get(_url(f"/ratings/{S.liked[0]}"), headers=headers)
        assert r.json()["rating"] == REVOKED_RATING

    def test_04_deleting_a_rating_also_recomputes(self, client):
        headers = _login(client)
        deleted_movie = S.liked[1]

        r = client.delete(_url(f"/ratings/{deleted_movie}"), headers=headers)
        assert r.status_code == 204, r.text
        assert client.get(_url(f"/ratings/{deleted_movie}"), headers=headers).status_code == 404

        after = _recs(client, headers)
        assert after["source"] == "realtime"
        ids = [it["movie_id"] for it in after["items"]]
        assert ids
        assert not (set(ids) & _rated_ids(client, headers))

    def test_05_no_liked_movies_left_still_gives_usable_fallback(self, client):
        headers = _login(client)
        for mid in S.liked[2:]:
            r = client.put(_url(f"/ratings/{mid}"), json={"rating": REVOKED_RATING}, headers=headers)
            assert r.status_code == 200, r.text

        after = _recs(client, headers)
        assert after["source"] == "realtime"
        assert after["items"], "Kedvelt film nélkül is érthető, nem üres tartalékajánlás kell"
        assert not ({it["movie_id"] for it in after["items"]} & _rated_ids(client, headers))
        assert all(it["algorithm"] for it in after["items"]), "Minden elemnek legyen algoritmusjelölése"
