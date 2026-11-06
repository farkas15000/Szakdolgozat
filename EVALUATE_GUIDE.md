# Offline kiértékelési útmutató

## Mit csinál ez a script?

Az `evaluate.py` összehasonlítja a négy ajánlómodellt **ugyanazon rögzített train/test felosztáson**, így az eredmények reprodukálhatók és egymással közvetlenül összehasonlíthatók.

| Modell | Leírás |
|---|---|
| Popularity | A train halmazban legtöbbet értékelt filmeket ajánlja |
| Content-based | Műfaj + genome tag cosine similarity a kedvelt filmekhez |
| SVD | Cornac SVD kollaboratív szűrés |
| Hybrid | SVD + Content lineáris kombinációja (alpha=0.6) |

**Metrikák:**
- **Precision@K** – a top-K ajánlás hány %-a releváns (≥4.0 teszt-értékelésű film)
- **Recall@K** – a releváns (≥4.0) teszt filmek hány %-a kerül be a top-K ajánlásba
- **NDCG@K** – rangsor minőség (korábbi találat = nagyobb súly)
- **RMSE / MAE** – csak SVD-nél: becsült vs. tényleges értékelés különbsége

**Konkrét felhasználói példák:** az aggregált táblázat mellett a script egy–egy kiválasztott felhasználóra (userId) kilistázza a kedvelt filmjeit és a négy módszer ajánlását egymás mellett – lásd a „Konkrét felhasználói példák” részt.

---

## Fájlstruktúra a konténerben

A Docker image az összes szükséges fájlt tartalmazza:

```
/app/
├── src/backend/app/recommender/
│   └── evaluate.py              ← a script
├── dataset/ml-latest-small/
│   ├── ratings.csv
│   ├── movies.csv
│   └── genome-scores.csv
└── models/
    ├── svd.pkl                  ← docker-entrypoint.sh által generált
    └── content.pkl              ← docker-entrypoint.sh által generált
```

> A modellek az `app` service indulásakor automatikusan generálódnak (`train.py` fut az entrypointban).
> Ha az `app` service még nem futott le egyszer sem, előbb indítsd el: `docker compose up app`.

---

## Futtatás

### 1. módszer – `docker compose exec` (legegyszerűbb)

Ha az `app` service már fut:

```bash
docker compose exec app python -m src.backend.app.recommender.evaluate \
  --ratings-csv ./dataset/ml-latest-small/ratings.csv \
  --movies-csv  ./dataset/ml-latest-small/movies.csv \
  --genome-csv  ./dataset/ml-latest-small/genome-scores.csv \
  --k 10
```

Eredmény fájlba mentve:

```bash
docker compose exec app python -m src.backend.app.recommender.evaluate \
  --ratings-csv ./dataset/ml-latest-small/ratings.csv \
  --movies-csv  ./dataset/ml-latest-small/movies.csv \
  --genome-csv  ./dataset/ml-latest-small/genome-scores.csv \
  --k 10 \
  --output /var/lib/recommender_model/data/eval_results.csv
```

A kimenet másolása a host gépre:

```bash
docker compose cp app:/var/lib/recommender_model/data/eval_results.csv ./eval_results.csv
```

---

### 2. módszer – `docker-compose.evaluate.yml` (önálló futtatás)

Ezzel a megközelítéssel az `app` service futása **nem szükséges** – az `evaluate` service saját konténerként indul, de ugyanazt az image-et és modell-köteteket használja.

**Előfeltétel:** az `app` service legalább egyszer lefutott, hogy a modellek (`svd.pkl`, `content.pkl`) és a `recommender_model` kötet létezzenek.

```bash
# Modell generálás (ha még nem történt meg):
docker compose up app --no-start
docker compose run --rm app

# Kiértékelés futtatása:
docker compose -f docker-compose.yml -f docker-compose.evaluate.yml build --no-cache
docker compose -f docker-compose.yml -f docker-compose.evaluate.yml run --rm evaluate
```

Az `evaluate` service a `docker-compose.evaluate.yml`-ben rögzített paraméterekkel fut (lásd `command:`); az eredmény a `recommender_model` köteten keresztül a hoszton is elérhető, vagy:

```bash
docker compose -f docker-compose.yml -f docker-compose.evaluate.yml cp \
  evaluate:/var/lib/recommender_model/data/eval_results.csv ./eval_results.csv
```

---

## Paraméterek

```bash
python -m src.backend.app.recommender.evaluate \
  --ratings-csv ./dataset/ml-latest-small/ratings.csv \
  --movies-csv  ./dataset/ml-latest-small/movies.csv \
  --genome-csv  ./dataset/ml-latest-small/genome-scores.csv \
  --k 10 \
  --test-ratio 0.2 \
  --candidate-pool-size 500 \
  --min-ratings 5 \
  --seed 42 \
  --output /var/lib/recommender_model/data/eval_results.csv
```

| Paraméter | Alapértelmezett | Leírás |
|---|---|---|
| `--ratings-csv` | `data/ml-latest-small/ratings.csv` | Értékelések CSV (konténerben: `./dataset/ml-latest-small/ratings.csv`) |
| `--movies-csv` | `data/ml-latest-small/movies.csv` | Filmcímek és műfajok |
| `--genome-csv` | *(opcionális)* | Genome tag score-ok (content modellhez) |
| `--k` | 10 | Top-K ajánlás (Precision@K, Recall@K, NDCG@K) |
| `--test-ratio` | 0.2 | Minden user értékeléseinek hány %-a kerüljön tesztbe |
| `--candidate-pool-size` | 500 | Hány filmből választhat az ajánló |
| `--min-ratings` | 5 | Min. értékelésszám a kiértékelt usereknek |
| `--seed` | 42 | Véletlenszám seed (reprodukálhatóság) |
| `--output` | – | Ha megadod, CSV-be is menti az eredményt (csak az aggregált táblát, a példákat nem) |
| `--example-user-ids` | – | Vesszővel elválasztott userId lista a konkrét példákhoz, pl. `116,26,91` |
| `--example-users-count` | 0 | Ennyi felhasználót választ véletlenszerűen (a `--seed` miatt reprodukálhatóan) példának, ha `--example-user-ids` nincs megadva |

> **Fontos:** a `--ratings-csv` alapértelmezett értéke (`data/...`) a helyi fejlesztésre vonatkozik.
> Docker konténerben mindig add meg explicit módon: `--ratings-csv ./dataset/ml-latest-small/ratings.csv`

---

## Konkrét felhasználói példák

Az aggregált átlag nem mutatja meg, *kinek* és *miért* segít (vagy nem) a személyre szabás. Erre való a példa mód: megadott felhasználóra ugyanazt a jelölthalmazt és ugyanazokat a `recommend(...)` hívásokat használja, mint a fő kiértékelés, így a példák konzisztensek az eredménytáblával.

```bash
# Konkrét userId-k megadásával:
docker compose exec app python -m src.backend.app.recommender.evaluate \
  --ratings-csv ./dataset/ml-latest-small/ratings.csv \
  --movies-csv  ./dataset/ml-latest-small/movies.csv \
  --genome-csv  ./dataset/ml-latest-small/genome-scores.csv \
  --k 10 \
  --example-user-ids 116,26,91

# Vagy véletlenszerűen (reprodukálható) kiválasztott 3 felhasználóval:
docker compose exec app python -m src.backend.app.recommender.evaluate \
  --ratings-csv ./dataset/ml-latest-small/ratings.csv \
  --movies-csv  ./dataset/ml-latest-small/movies.csv \
  --genome-csv  ./dataset/ml-latest-small/genome-scores.csv \
  --k 10 \
  --example-users-count 3 --seed 42
```

A példák az aggregált tábla **után** íródnak ki. Mentéshez irányítsd át a kimenetet: `... | tee konkret_peldak.txt`.

**Mit ír ki felhasználónként?**
- a train halmazbeli értékelései és kedvelt (≥4.0) filmjei száma, a kedvelt filmek első 5 címe
- a releváns (≥4.0) teszt filmek száma
- a négy módszer top-K ajánlása címekkel; a **★** jelzi, ha az ajánlott film a felhasználó teszt halmazában ténylegesen releváns volt (valódi találat)
- találatok száma módszerenként (pl. `Popularity=3, Content-based=1, SVD=0, Hybrid=1`)

**Szabályok:**
- Csak olyan felhasználó szerepelhet példaként, akinek van legalább egy releváns teszt filmje; ha ilyen userId-t adsz meg, figyelmeztetést kapsz, és kimarad.
- `--example-users-count` csak legalább 7 train értékeléssel rendelkező felhasználók közül választ, hogy ne csak cold-start esetek kerüljenek be. Cold-start viselkedést explicit `--example-user-ids`-szel (kevés értékelésű userrel) tudsz bemutatni.
- A `--k` a példákra is érvényes (a fenti futtatásban `--k 10`; a dolgozatban szereplő példák top-20-szal készültek, ezt jelezd, ha összehasonlítod őket a top-10 táblával).
- Az adatszivárgás-tilalom itt is érvényes: a kedvelt filmek profilja kizárólag a train halmazból épül, a teszt filmek csak a ★ jelöléshez kellenek.

**Hogyan válassz példát?** Egy eredménytáblához érdemes 3–4 eltérő jellegű felhasználó:
- sok értékeléssel rendelkező (ahol az SVD/Hybrid is működhet),
- kevés értékeléssel rendelkező (ahol a Popularity is versenyképes lehet),
- olyan, ahol a Content-based nyer,
- olyan, ahol egyik személyre szabott módszer sem talál semmit.

Az eddigi futás tanulságai (dolgozat: *Eredmények → Konkrét felhasználói példák*): aktív usernél (#91) minden módszer talált, kevés értékelésű usereknél (#26, #235) a Popularity versenyképes vagy jobb volt, #116-nál a Content-based és Hybrid talált, a Popularity és az SVD nem.

---

## Várható kimenet

```
===========================================================================
  Ajánlórendszer offline kiértékelés – top-10
===========================================================================
Modell            Precision@K   Recall@K     NDCG@K     RMSE      MAE    Users
---------------------------------------------------------------------------
Popularity             0.0410     0.0258     0.0262        –        –      591
Content-based           0.0520     0.0414     0.0587        –        –      591
SVD                    0.0098     0.0072     0.0130   0.8862   0.6851      591
Hybrid                  0.0355     0.0245     0.0364        –        –      591
===========================================================================
```

(A fenti számok illusztrációk; a tényleges futtatás a lenti "Eredmények értelmezése" alapján rögzítendők.)

---

## Fontos megjegyzések

### Adatszivárgás elkerülése
A script a teszt értékeléseket **nem** adja hozzá a train halmazhoz, és a candidate pool is csak a train adatból épül fel – így a popularity modell sem „lát előre".

### Saját alkalmazás felhasználói vs. MovieLens
A MovieLens offline eredmények a **modell képességét** mérik a MovieLens adatbázison. A saját alkalmazás új felhasználói cold start helyzetben indulnak – ezt a `hybrid.py` popularity és content-based fallbackjei kezelik.

### Eredmények értelmezése (kötelező a november 6-i leadáshoz)
Az eredménytábla önmagában nem elég – Vilmos kifejezetten kéri, hogy néhány jellemző példán mutasd be, hol segített és hol nem segített a személyre szabás, és mi lehet ennek az oka (pl. candidate pool mérete, SVD alulillesztettsége kevés iterációnál, adatritkaság). Nem elvárás, hogy a hibrid mindenhol nyerjen; a megalapozott következtetés a fontos.

Ehhez használd a fenti **konkrét felhasználói példákat** (`--example-user-ids` / `--example-users-count`): a kimenetet mentsd el, a kiválasztott példákat és magyarázatukat pedig rögzítsd a `docs/04_quality/test_report.md` vagy egy külön `docs/06_release/evaluation_results.md` fájlban, a CSV-re és a példa-kimenetre hivatkozva mint evidence.
