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

## Legutolsó futás eredménye

- Dátum: 2026. 10. 16. 20:57
- Eredmény:  `6 passed in 3.16s`
- Részletek (teszt esetenként):

| Teszt | Eredmény | Megjegyzés |
|---|---|---|
| `test_01_register_and_login` | [PASSED] | |
| `test_02_rate_movies` | [PASSED] | |
| `test_03_recommendation_is_not_svd_for_unknown_user` | [PASSED] | |
| `test_04_modify_rating_changes_recommendation` | [PASSED] | |
| `test_05_recommendation_persists_after_relogin` | [PASSED] | |
| `test_svd_activates_for_known_user` | [PASSED] | |

- CI link:

## Ismert hiányosságok

- KITÖLTENDŐ

## Flaky / instabil tesztek
