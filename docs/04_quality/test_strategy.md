# Teszt stratégia

## Teszt piramis

| Szint | Mit fed le | Eszköz |
|---|---|---|
| Unit | Ajánló logika (popularity ranking, content cosine similarity, SVD score lekérdezés, hybrid alpha-kombináció, cold-start fallback döntés) | `pytest` |
| Integráció | API + DB együtt (regisztráció, értékelés mentése, cache-olvasás/-írás) | `pytest` + teszt DB (konténerben futó Postgres) |
| E2E | Teljes user flow: regisztráció → értékelés → ajánlás → módosítás → friss ajánlás; kedvelés visszavonása | `pytest` + `httpx` a futó `app` service ellen ([tests/e2e/test_user_flow.py](../../tests/e2e/test_user_flow.py), [tests/e2e/test_feedback_revoke.py](../../tests/e2e/test_feedback_revoke.py)) |

## Mit unit-, mit integrációs szinten tesztelünk

- **Unit**: tiszta logika, DB nélkül – pl. `recall_at_k`, `ndcg_at_k`, a hybrid `use_svd` döntési ág, az SVD cold-start ellenőrzés (`str(user_id) not in uid_map`).
- **Integráció**: minden, ami DB-t vagy a cache táblát érinti – pl. a cache lekérdezés nem duplikál, a már értékelt film kiesik a candidate poolból.

## Legkritikusabb user flow-k, amiket e2e teszt véd

1. Új felhasználó: regisztráció → 7 értékelés → ajánlás (content-based, nem hybrid) → értékelés módosítása → friss, konzisztens ajánlás újra-bejelentkezés után is (`TestNewUserFlow`).
2. Ismert, a legutóbb tanított SVD modellben szereplő felhasználó ténylegesen SVD/hybrid ajánlást kap (`TestKnownUserSvdActivation`).
3. Kedvelés visszavonása (`TestRevokeLikedRating`): a felhasználó egy korábban kedvelt film értékelését módosítja (PUT) vagy törli (DELETE), és a következő ajánlás a friss visszajelzésből számolódik. Lépések:
   - 5 kedvelt film eltérő műfajokból, az ajánlás cache-be kerül (2. lekérés `precomputed`);
   - az egyik kedvelés visszavonása után a cache üres, az ajánlás `realtime`, nem tartalmaz értékelt filmet, és a közös content-based filmek pontszáma megváltozik;
   - új belépés után ugyanaz a lista olvasható vissza;
   - törlés után ugyanez igaz;
   - ha egyetlen kedvelt film sem marad, nem üres tartalékajánlás jön.

   Backend-szabály, amit a teszt véd: a `PUT /ratings/{movie_id}` és a `DELETE /ratings/{movie_id}` a saját tranzakciójában törli a felhasználó tárolt ajánlásait, így üres cache esetén a `GET /recommendations` friss generálást ad.

## Mock/stub stratégia

- A TMDB API hívás (poszter lekérés) mockolva van a unit/integrációs tesztekben, hogy a tesztek ne függjenek külső szolgáltatástól.
- Az e2e teszt a valós, futó stacket használja (DB, backend) – ez szándékosan nem mockolt, mert pont az integrált viselkedést ellenőrzi.

## Quality gate-ek

- A teszteknek a `main`/`develop` branch-en zöldnek kell lenniük, mielőtt merge történik.
- Lint/format ellenőrzés (ha be van állítva CI-ban) a teszt lépés előtt fut.

## Futtatás

```bash
# Unit + integrációs tesztek a futó konténerben
docker compose exec app pytest -v --ignore=tests/e2e

# E2E teszt a futó app ellen
docker compose exec app pytest -v --known-user-email=user@example.com --known-user-password=secret

# Kedvelés visszavonása (feedback revoke) e2e teszt
BASE_URL=http://localhost:8000 pytest -v tests/e2e/test_feedback_revoke.py
```

## Megjegyzés a véletlen változatosságról

A webes ajánlás real-time ága `random.sample`-t használ, ezért két egymást követő friss generálás eltérő listát adhat. Az e2e tesztek ezért nem konkrét filmlistákat hasonlítanak össze, hanem determinisztikus jeleket: `source` (`precomputed`/`realtime`), az értékelt filmek hiánya a listában, azonos lista cache-ből újraolvasva, és (ha van közös elem) a content-based pontszámok változása. Az offline mérés (`evaluate.py`) determinisztikus, a véletlen mintavételtől független.

## Ismert hiányosságok

- A jelenlegi kódbázisban nincs elkülönített `tests/` mappa unit/integrációs tesztekkel – ez a következő kör feladata (lásd `test_report.md` "Ismert hiányosságok").
