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

**Érzékenységi vizsgálat (`--sweep`):** a fenti négy módszer mellett az SVD hiperparamétereit (`k`, `max_iter`), a hibrid α súlyát és a seedeket variálja, és seedek közötti átlag ± szórást ad – lásd az „Érzékenységi vizsgálat” részt.

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

### 3. módszer – érzékenységi vizsgálat (`--sweep`)

Az SVD-rács × hibrid α × seed vizsgálat. A `docker-compose.evaluate.yml` `command:` sorát a `run` után megadott argumentumok felülírják, ezért nem kell a fájlt módosítani. Az eredmény a host `out/` mappájába kerül (`-v "$PWD/out:/out"`).

```bash
docker compose -f docker-compose.yml -f docker-compose.evaluate.yml build evaluate

# A) időalapú felosztás (a fő táblával összevethető; a szórás csak az SVD inicializálásából jön)
docker compose -f docker-compose.yml -f docker-compose.evaluate.yml run --rm evaluate \
  --sweep --split-mode temporal --seeds 42,43,44 --k 10 \
  --ratings-csv ./dataset/ml-latest-small/ratings.csv \
  --movies-csv  ./dataset/ml-latest-small/movies.csv \
  --genome-csv  ./dataset/ml-latest-small/genome-scores.csv \
  --svd-k-list 100,50,32 --svd-iter-list 20,50,100 \
  --alphas 0.0,0.1,0.2,0.4,0.6,0.8,1.0 \
  --sweep-output-prefix /var/lib/recommender_model/data/sweep_temporal

# B) véletlen felosztás (a felosztás szórása is mérhető)
docker compose -f docker-compose.yml -f docker-compose.evaluate.yml run --rm evaluate \
  --sweep --split-mode random --seeds 42,43,44 --k 10 \
  --ratings-csv ./dataset/ml-latest-small/ratings.csv \
  --movies-csv  ./dataset/ml-latest-small/movies.csv \
  --genome-csv  ./dataset/ml-latest-small/genome-scores.csv \
  --svd-k-list 100,50,32 --svd-iter-list 20,50,100 \
  --alphas 0.0,0.1,0.2,0.4,0.6,0.8,1.0 \
  --sweep-output-prefix /var/lib/recommender_model/data/sweep_random
```

**Kimenet:** a konzolon az átlag ± szórás tábla és egy rövid összegzés; a `--sweep-output-prefix` megadásakor két CSV: `<prefix>_raw.csv` (seedenként, páros különbségekhez) és `<prefix>_summary.csv` (3 seed átlaga és szórása). A konfigurációk neve `k=<k>,iter=<max_iter>` (hibridnél `,alpha=<α>` is).

**Futásidő:** 9 SVD-konfiguráció × 3 seed × 2 felosztás tanítás. Gyorsításhoz szűkítheted a rácsot, pl. `--svd-k-list 100 --svd-iter-list 20,50`.

**Fontos:**
- Az α az **SVD-komponens súlya**: α = 0 a tiszta Content-based, α = 1 a tiszta SVD. Az α csökkentésével a hibrid a Content-based-hez közelít.
- A sweep minden SVD-konfigurációt a train halmazból tanít, a `svd.pkl`-t nem használja.
- A konfigurációk a **teszt halmazon** vannak összevetve. A legjobb sor értéke ezért optimista; érzékenységi vizsgálatként közöld, ne a teszten kiválasztott végleges modellként.
- Időalapú felosztáson a Popularity és a Content-based szórása 0 (determinisztikus felosztás); a véletlen felosztás szórása a felosztást is tartalmazza. 3 seednél a szórás durva becslés.
- A két felosztás abszolút értékei nem hasonlíthatók össze (a véletlen felosztás mindhárom módszernek könnyebb).

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
| `--sweep` | kikapcsolva | Érzékenységi vizsgálat mód (lásd fent). Bekapcsolva a fő tábla és a példák nem futnak le |
| `--seeds` | `42,43,44` | Sweep: vesszővel elválasztott seedek |
| `--split-mode` | `temporal` | Sweep: `temporal` (időrendben utolsó 20%, determinisztikus) vagy `random` (véletlen 20%, seedfüggő). **Csak `--sweep` mellett hat**, a normál mód mindig időalapú |
| `--svd-k-list` | `100,50,32` | Sweep: SVD látens dimenziók |
| `--svd-iter-list` | `20,50,100` | Sweep: SVD `max_iter` értékek |
| `--alphas` | `0.0,0.1,0.2,0.4,0.6,0.8,1.0` | Sweep: hibrid α értékek (az SVD súlya) |
| `--svd-lr` / `--svd-lambda` | `0.01` / `0.02` | Sweep: SVD tanulási ráta és regularizáció (rögzítettek, nem rács) |
| `--sweep-output-prefix` | – | Sweep: CSV előtag (`<prefix>_raw.csv`, `<prefix>_summary.csv`) |

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

Normál mód (`--k 10`, időalapú felosztás, `--seed 42`; a valós futás eredménye, lásd `docs/06_release/evaluation_results.md`):

```
===========================================================================
  Ajánlórendszer offline kiértékelés – top-10
===========================================================================
Modell            Precision@K   Recall@K     NDCG@K     RMSE      MAE    Users
---------------------------------------------------------------------------
Popularity             0.0220     0.0258     0.0262        –        –      591
Content-based          0.0462     0.0414     0.0587        –        –      591
SVD                    0.0134     0.0072     0.0130   0.8862   0.6851      591
Hybrid                 0.0294     0.0245     0.0364        –        –      591
===========================================================================
```

Sweep mód: egy sor konfigurációnként, átlag±szórás formában (a számok az időalapú futásból valók, `k=100,iter=50`):

```
Modell         Konfiguráció                       Precision@10        Recall@10          NDCG@10
Popularity     -                                 0.0220±0.0000    0.0258±0.0000    0.0262±0.0000
Content-based  -                                 0.0462±0.0000    0.0414±0.0000    0.0587±0.0000
SVD            k=100,iter=50                     0.0260±0.0006    0.0204±0.0010    0.0317±0.0020
Hybrid         k=100,iter=50,alpha=0.2           0.0457±0.0002    0.0401±0.0002    0.0603±0.0005
```

Az eddigi sweep-eredmények értelmezése: `docs/06_release/evaluation_results.md` 5. fejezete.

---

## Fontos megjegyzések

### Adatszivárgás elkerülése
A script a teszt értékeléseket **nem** adja hozzá a train halmazhoz, és a candidate pool is csak a train adatból épül fel – így a popularity modell sem „lát előre".

### Hibrid α iránya
A kódban az `alpha` az SVD súlya (`alpha * SVD + (1 - alpha) * Content`). A korábbi α = 0,6 beállítás mindkét felosztáson rontotta a Content-based eredményét; α ≈ 0,1–0,2 körül a hibrid a Content-based szintjén vagy kissé fölötte van.

### Saját alkalmazás felhasználói vs. MovieLens
A MovieLens offline eredmények a **modell képességét** mérik a MovieLens adatbázison. A saját alkalmazás új felhasználói cold start helyzetben indulnak – ezt a `hybrid.py` popularity és content-based fallbackjei kezelik.