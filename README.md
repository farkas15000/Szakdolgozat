# Személyre szabott film ajánlórendszer

> Webalkalmazás, amely valós idejű, személyre szabott tartalomajánlásokat nyújt felhasználóknak az érdeklődési körük és korábbi interakcióik alapján – hogy ne vesszetek el a tartalmak tengerében.

## Fő képességek

- **Felhasználói regisztráció és bejelentkezés** – profil létrehozása, kezelése, biztonságos autentikáció
- **Preferenciák rögzítése** – tartalmak értékelése és kedvencként jelölése
- **Személyre szabott ajánlások** – az ajánlóalgoritmus a korábbi interakciók alapján generál javaslatokat (popularity → content-based → SVD/hybrid, a rendelkezésre álló adat mennyiségétől függően)
- **Interaktív webes felület** – az ajánlások áttekinthető, kattintható listában jelennek meg (Vue.js)
- **REST API** – FastAPI-alapú backend, amely kiszolgálja az ajánlásokat és rögzíti az interakciókat
- **Offline modell-kiértékelés** – a négy ajánlómodell (popularity, content-based, SVD, hybrid) MovieLens-alapú, reprodukálható összehasonlítása ([EVALUATE_GUIDE.md](./EVALUATE_GUIDE.md))

---

## Tech stack

| Réteg     | Technológia          |
|-----------|----------------------|
| Frontend  | Vue.js 3             |
| Backend   | Python 3.11, FastAPI |
| Adatbázis | PostgreSQL 15        |
| Infra     | Docker, Docker Compose |

---

## Dokumentáció

A teljes termékdokumentáció a [`docs/`](./docs) mappában található ([index](./docs/00_index.md)):

| Terület | Link |
|---|---|
| Termék scope, MVP, elfogadási kritériumok | [docs/01_product/scope_contract.md](./docs/01_product/scope_contract.md) |
| Fő felhasználói folyamat (UX flow) | [docs/03_design/ux_flows.md](./docs/03_design/ux_flows.md) |
| Teszt stratégia | [docs/04_quality/test_strategy.md](./docs/04_quality/test_strategy.md) |
| Teszt riport (legutolsó futás) | [docs/04_quality/test_report.md](./docs/04_quality/test_report.md) |
| Offline modell-kiértékelés útmutató | [EVALUATE_GUIDE.md](./EVALUATE_GUIDE.md) |

---

## Quickstart (lokál, ~10 perc)

### Előfeltételek

- Docker Desktop (vagy Docker Engine + Compose plugin) telepítve
- Git

### 1. Konfiguráció

```bash
cp .env.example .env
# Szükség szerint szerkeszd a .env fájlt (lásd Konfiguráció szekció)
```

### 2. Indítás

```bash
docker compose up --build
```

Az induláskor automatikusan lefut: adatbázis-migráció → MovieLens adat betöltése → popularity/content/SVD modellek tanítása → ajánlások előgenerálása → az API szerver elindul.

**Várt kimenet az indulás végén:**

```
db-1   | database system is ready to accept connections
app-1  | INFO:    Uvicorn running on http://0.0.0.0:8000
```

### 3. Ellenőrzés

Nyisd meg a böngészőt: **http://localhost:8000**

A health endpoint ellenőrzése:

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

### 4. Tesztek futtatása

```bash
docker compose exec app pytest -v
```

A teszt stratégiáról és a tesztszuitokról lásd: [docs/04_quality/test_strategy.md](./docs/04_quality/test_strategy.md).

---

## Konfiguráció

Másold a `.env.example` fájlt `.env` névvel, és töltsd ki az értékeket:

```bash
cp .env.example .env
```

### Környezeti változók

| Változó                       | Leírás                                              | Példa                                                                  |
|--------------------------------|-----------------------------------------------------|------------------------------------------------------------------------|
| `DATABASE_URL`                 | PostgreSQL kapcsolati string                        | `postgresql+psycopg2://username:password@db:5432/recommender_db`       |
| `POSTGRES_USER`                | PostgreSQL felhasználó                              | `username`                                                             |
| `POSTGRES_PASSWORD`            | PostgreSQL jelszó                                   | `change_me`                                                            |
| `SECRET_KEY`                   | JWT aláíráshoz használt titkos kulcs (min. 32 kar.) | `python -c "import secrets; print(secrets.token_hex(32))"`             |
| `JWT_ALGORITHM`                | JWT algoritmus                                      | `HS256`                                                                |
| `ACCESS_TOKEN_EXPIRE_MINUTES`  | Access token lejárati idő percben                   | `30`                                                                   |
| `REFRESH_TOKEN_EXPIRE_DAYS`    | Refresh token lejárati idő napban                   | `7`                                                                    |
| `SVD_MODEL_PATH`               | SVD modell fájl helye (kötetben perzisztál)         | `/var/lib/recommender_model/data/svd.pkl`                              |
| `CONTENT_MODEL_PATH`           | Content-based modell fájl helye                     | `/var/lib/recommender_model/data/content.pkl`                          |
| `HYBRID_SVD_WEIGHT`            | Hybrid ajánló SVD-súlya (alpha)                     | `0.6`                                                                  |
| `MIN_RATINGS_FOR_SVD`          | Min. saját értékelésszám, hogy SVD-t próbáljunk      | `7`                                                                    |
| `RECOMMENDATION_TOP_N`         | Előgenerált ajánlások száma felhasználónként          | `20`                                                                   |
| `RECOMMENDATION_EXPIRES_HOURS` | Gyorsítótárazott ajánlás érvényessége órában         | `24`                                                                   |
| `TMDB_API_KEY`                 | The Movie Database API kulcs (poszterekhez)         | [themoviedb.org/settings/api](https://www.themoviedb.org/settings/api) |
| `TMDB_POSTER_SIZE`             | TMDB poszterméret                                   | `w342`                                                                 |

> **Megjegyzés:** az `7` saját értékelés (`MIN_RATINGS_FOR_SVD`) önmagában **nem** teszi a felhasználót az SVD modell számára ismertté – az SVD csak azokat a felhasználókat tudja pontozni, akik a modell legutóbbi tanításában szerepeltek. Új felhasználónál eddig a pontig content-based/popularity ajánlás aktív. Lásd: [docs/03_design/ux_flows.md](./docs/03_design/ux_flows.md).

---

## Hibakeresés (gyakori hibák)

| Hiba | Ok | Megoldás                                                                                                                                       |
|---|---|------------------------------------------------------------------------------------------------------------------------------------------------|
| Regisztrációkor `bcrypt` import hiba | `bcrypt>=5.0` nem kompatibilis a `passlib`-bal | `requirements.txt`-ben `bcrypt==4.0.0` rögzítve, `passlib` elhagyva.                                                                           |
| Üres vagy duplikált ajánláslista frissítés után | Elavult cache | A cache automatikusan frissül, ha már értékelt film van benne; lásd `recommendations_router.py`                                                |
| `SVD modell nem található` log | `svd.pkl` még nincs legenerálva | Várd meg az első `docker compose up` teljes lefutását, vagy `docker compose exec app python -m src.backend.app.recommender.train --model both` |

---

## Demo / Kipróbálás

| Szolgáltatás        | URL                          |
|---------------------|------------------------------|
| Webalkalmazás       | http://localhost:8000        |
| API (Swagger UI)    | http://localhost:8000/docs   |
| API (ReDoc)         | http://localhost:8000/redoc  |
| Health endpoint     | http://localhost:8000/health |

Készítette: Füleki Balázs
Konzulens: Bilicki Vilmos
