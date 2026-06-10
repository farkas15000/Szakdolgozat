# Személyre szabott film ajánlórendszer

> Webalkalmazás, amely valós idejű, személyre szabott tartalomajánlásokat nyújt felhasználóknak az érdeklődési körük és korábbi interakcióik alapján – hogy ne vesszetek el a tartalmak tengerében.

## Fő képességek

- **Felhasználói regisztráció és bejelentkezés** – profil létrehozása, kezelése, biztonságos autentikáció
- **Preferenciák rögzítése** – tartalmak értékelése és kedvencként jelölése
- **Személyre szabott ajánlások** – az ajánlóalgoritmus a korábbi interakciók alapján generál javaslatokat
- **Interaktív webes felület** – az ajánlások áttekinthető, kattintható listában jelennek meg (Vue.js)
- **REST API** – FastAPI-alapú backend, amely kiszolgálja az ajánlásokat és rögzíti az interakciókat

---

## Tech stack

| Réteg     | Technológia          |
|-----------|----------------------|
| Frontend  | Vue.js 3             |
| Backend   | Python 3.11, FastAPI |
| Adatbázis | PostgreSQL 15        |
| Infra     | Docker, Docker Compose |

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


## Konfiguráció

Másold a `.env.example` fájlt `.env` névvel, és töltsd ki az értékeket:

```bash
cp .env.example .env
```

### Kötelező környezeti változók

| Változó                  | Leírás                                              | Példa                                                            |
|--------------------------|-----------------------------------------------------|------------------------------------------------------------------|
| `DATABASE_URL`           | PostgreSQL kapcsolati string                        | `postgresql+psycopg2://username:password@db:5432/recommender_db` |
| `POSTGRES_USER`           | PostgreSQL felhasználó string                       | `username`                                                       |
| `POSTGRES_PASSWORD`           | PostgreSQL jelszó string                            | `password`                                                       |
| `SECRET_KEY`             | JWT aláíráshoz használt titkos kulcs (min. 32 kar.) | `random_string_legalabb_32_karakter`                             |
| `ALGORITHM`              | JWT algoritmus                                      | `HS256`                                                          |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Token lejárati idő percben                          | `30`                                                             |
| `TMDB_API_KEY` | The Movie Database API kulcs                        | `a_te_api_kulcsod`                                                             |

## Demo / Kipróbálás

| Szolgáltatás        | URL                          |
|---------------------|------------------------------|
| Webalkalmazás       | http://localhost:8000        |
| API (Swagger UI)    | http://localhost:8000/docs   |
| API (ReDoc)         | http://localhost:8000/redoc  |
| Health endpoint     | http://localhost:8000/health |

Készítette: Füleki Balázs
Konzulens: Bilicki Vilmos
