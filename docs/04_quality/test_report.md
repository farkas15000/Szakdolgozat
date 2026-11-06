# Test Report

> Ezt a dokumentumot a tényleges futtatás után töltsd ki (a `[ KITÖLTENDŐ ]` jelölt helyeken). Ne hagyd üresen a leadásban.

## Környezet

- OS: Windows 11
- Runtime/SDK: Python 3.11 (Docker image szerint)
- DB: PostgreSQL 16 (docker-compose `db` service)
- Teszt adat: MovieLens `ml-latest-small` + e2e teszt során generált egyedi (`e2e_*@example.com`) felhasználók

## Teszt suite-ek és futtatás

- Unit + integráció: `docker compose exec app pytest -v --ignore=tests/e2e`
- E2E (új felhasználó flow): `BASE_URL=http://localhost:8000 pytest -v tests/e2e/test_user_flow.py`
- E2E (ismert user SVD-aktiválódás): `pytest -v -k KnownUser tests/e2e/test_user_flow.py --known-user-email=user@example.com --known-user-password=secret`
- E2E (kedvelés visszavonása / feedback revoke): `BASE_URL=http://localhost:8000 pytest -v tests/e2e/test_feedback_revoke.py`

## Legutolsó futás eredménye

- Dátum: 2026. 10. 16. 20:57
- Eredmény:  `6 passed`
- Részletek (teszt esetenként):

| Teszt | Eredmény | Megjegyzés |
|---|---|---|
| `test_01_register_and_login` | [PASSED] | |
| `test_02_rate_movies` | [PASSED] | |
| `test_03_recommendation_is_not_svd_for_unknown_user` | [PASSED] | |
| `test_03b_detector_actually_fails_on_forbidden_label` | [PASSED] | |
| `test_04_modify_rating_changes_recommendation` | [PASSED] | |
| `test_05_recommendation_persists_after_relogin` | [PASSED] | |
| `test_rated_but_none_liked_gets_usable_fallback` | [PASSED] | |
| `test_requesting_more_than_available_does_not_error` | [PASSED] | |
| `test_svd_activates_for_known_user` | [PASSED] | |

- CI link:

### Feedback revoke teszt (`tests/e2e/test_feedback_revoke.py`)

- Dátum: 2026. 11. 04.
- Eredmény: `5 passed`
- Előfeltétel: a `ratings.py` módosítás/törlés (PUT/DELETE) kiüríti a felhasználó tárolt ajánlásait (`_invalidate_recommendation_cache`).
- Cél: egy korábban kedvelt film értékelésének visszavonása után az ajánlás a friss visszajelzésből számolódik, és ez új belépéskor is visszaolvasható.

| Teszt | Eredmény | Megjegyzés |
|---|---|---|
| `test_01_baseline_recommendation_is_cached` | [PASSED] | 5 kedvelt film 5 műfajból; a 2. lekérés `precomputed`, azonos lista |
| `test_02_revoking_a_liked_rating_invalidates_cache_and_recomputes` | [PASSED] | PUT után `realtime`, nincs értékelt film a listában, a közös content-based pontszámok változnak |
| `test_03_fresh_result_is_what_a_new_login_reads_back` | [PASSED] | új belépés után ugyanaz a lista (`precomputed`), a visszavont értékelés látszik |
| `test_04_deleting_a_rating_also_recomputes` | [PASSED] | DELETE után 404 az értékelésre, az ajánlás `realtime` |
| `test_05_no_liked_movies_left_still_gives_usable_fallback` | [PASSED] | kedvelt film nélkül is nem üres, algoritmusjelölt tartalékajánlás |

## Ismert hiányosságok

- Nincs elkülönített unit/integrációs `tests/` mappa; jelenleg az e2e tesztek védik a fő folyamatokat.
- A webes ajánlás `random.sample`-t használ, ezért az e2e tesztek nem konkrét filmlistákat hasonlítanak össze, hanem megfigyelhető jeleket (`source`, nincs értékelt film a listában, azonos lista újra-olvasáskor).
- A feedback revoke teszt pontszám-összehasonlítása csak akkor fut, ha a két ajánlás között van közös, `content_based` jelölésű elem.
- A böngészős fő folyamat kézi végigjárása és a célcsoportbeli felhasználói kipróbálás még nem történt meg.

## Flaky / instabil tesztek

- Eddig nem tapasztalt. Figyelendő: a feedback revoke teszt pontszám-ellenőrzése a véletlen mintavétel miatt elvileg érzékeny lehet, ha nincs elég közös elem (ilyenkor kimarad).
