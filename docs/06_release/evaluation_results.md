# Offline összehasonlítás – eredmények és értelmezés

> Helye a repóban: `docs/06_release/evaluation_results.md`
> Evidence: `eval_results.csv` (aggregált tábla), `konkret_peldak.txt` (konkrét felhasználói példák kimenete)
> Futtatás és paraméterek: `EVALUATE_GUIDE.md`

## 1. Mérési felállás

| Elem | Érték |
|---|---|
| Adathalmaz | MovieLens ml-latest-small |
| Felosztás | felhasználónként az időrendben legkésőbbi 20% a teszt halmaz (`--test-ratio 0.2`), minimum 5 értékelés (`--min-ratings 5`) |
| Méret | 80 896 train és 19 940 teszt értékelés; 610 teszt felhasználó, ebből 591-nél van legalább egy releváns teszt film |
| Jelölthalmaz | a train halmazban legtöbbet értékelt 500 film (`--candidate-pool-size 500`), a felhasználó már értékelt filmjei nélkül; mind a négy módszerre azonos |
| Releváns elem | a teszt halmazban ≥4,0 értékelést kapott film |
| Metrikák | Precision@10, Recall@10, NDCG@10; csak az SVD-re RMSE és MAE |
| Reprodukálhatóság | `--seed 42`, determinisztikus felosztás; a webes felület `random.sample` változatossága az offline mérésben nem szerepel |

**Adatszivárgás elleni szabály.** A teszt értékelések nem kerülnek vissza a modell tanításába, a népszerűségi számlálásba, a jelölthalmaz építésébe és a felhasználó kedvelt filmjeinek összeállításába. A teszt filmek csak a találatok kiértékeléséhez kellenek.

**SVD-modell.** A `svd.pkl` userId-i nem egyeztek a MovieLens userId-kkal, ezért a script a train halmazból újratanította a modellt (610 user, 7 457 item; `k=100`, `max_iter=20`, `lr=0.01`, `λ=0.02`).

## 2. Összehasonlító tábla (top-10, 591 felhasználó)

| Modell | Precision@10 | Recall@10 | NDCG@10 | RMSE | MAE |
|---|---:|---:|---:|---:|---:|
| Popularity | 0,0220 | 0,0258 | 0,0262 | – | – |
| **Content-based** | **0,0462** | **0,0414** | **0,0587** | – | – |
| SVD | 0,0134 | 0,0072 | 0,0130 | 0,8862 | 0,6851 |
| Hybrid (α = 0,6) | 0,0294 | 0,0245 | 0,0364 | – | – |

Az RMSE/MAE csak az SVD-nél értelmezhető, mert csak ez ad értékelés-előrejelzést.

## 3. Értelmezés

1. **A tartalomalapú módszer nyer.** A Content-based a népszerűségi alapvonalhoz képest nagyjából kétszeres Precision@10-et és NDCG@10-et ér el (0,0462 és 0,0220, illetve 0,0587 és 0,0262), a Recall@10 pedig 0,0414 a 0,0258-cal szemben. Ez az egyszerű népszerűségi listához képest mérhető többletet jelent a személyre szabásra.
2. **Az SVD a legrosszabb rangsoroló, miközben az előrejelzése elfogadható.** RMSE = 0,8862 és MAE = 0,6851 mellett a top-10 rangsorolása a Popularity alatt van. Ez a jelenség a szakirodalomban ismert: az előrejelzési hibára optimalizált modell nem feltétlenül jó top-N feladatban (Cremonesi, Koren és Turrin, 2010).
3. **A Hybrid a Popularity-nél jobb, de a Content-based-nél gyengébb.** Az SVD-komponens (α = 0,6) ezen az adaton rontja a tiszta tartalomalapú eredményt, nem kiegészíti. Vilmos szerint sem elvárás, hogy a hibrid mindenhol nyerjen.

### Lehetséges okok az SVD gyengeségére

- **Alulillesztettség.** A modell 20 iterációval, kis és ritka adathalmazon tanult. Ez az elsődleges magyarázat.
- **Jelölthalmaz népszerűségi torzítása.** Az 500 leggyakrabban értékelt filmből álló jelölthalmaz a népszerűségi szignálnak kedvez, az SVD erőssége viszont a kevésbé nyilvánvaló találatokban lenne. A jelölthalmaz méretének hatását ellenőriztük: 500-ról 9 999-re növelve az SVD mutatói nem javultak, tovább romlottak (a Content-based kicsit javult). A jelölthalmaz mérete tehát nem a fő ok.
- **Ritka adat.** A felhasználók többségének kevés értékelése van, ez a kollaboratív szűrés ismert gyenge pontja.

## 4. Konkrét felhasználói példák (top-20)

A példák a `--example-user-ids 116,26,235,91,176,100` futásból származnak, top-20 ajánlással (nem a top-10 táblával azonos K). A ★ jelöli, ha az ajánlott film a felhasználó teszt halmazában releváns (≥4,0) volt.

| userId | Train értékelés (kedvelt) | Releváns teszt film | Popularity | Content-based | SVD | Hybrid |
|---:|---:|---:|---:|---:|---:|---:|
| 116 | 70 (32) | 7 | 0 | 2 | 0 | 2 |
| 26 | 17 (3) | 4 | 2 | 1 | 0 | 1 |
| 235 | 52 (29) | 9 | 3 | 0 | 0 | 0 |
| 91 | 460 (182) | 56 | 9 | 3 | 5 | 6 |
| 176 | 29 (21) | 5 | 3 | 1 | 0 | 0 |
| 100 | 119 (85) | 22 | 0 | 2 | 1 | 1 |

A cellák a top-20-on belüli találatok számát mutatják.

### Hol segített a személyre szabás

- **#116 (Content-based és Hybrid 2–2 találat, Popularity és SVD 0).** A felhasználó kedvelt filmjei (pl. Congo, Crimson Tide, The Client, Forrest Gump) akció- és thriller-ízlésre utalnak. A Content-based és a Hybrid ezzel összhangban a Gladiator és a Pirates of the Caribbean filmeket találta el. A Popularity általános slágerlistát adott, az SVD pedig régebbi klasszikusokat (Lawrence of Arabia, North by Northwest), amelyek közül egy sem volt releváns.
- **#100 (Content-based 2, SVD és Hybrid 1, Popularity 0).** A kedvelt filmek (Sense and Sensibility, Persuasion, Mr. Holland's Opus) drámai, romantikus ízlést mutatnak. A Content-based a Bridget Jones's Diary és a Catch Me If You Can filmeket találta el, a Popularity egyet sem.
- **#91 (minden módszer talált).** Ez az aktív, adatgazdag felhasználó (460 értékelés). Az SVD (5) és a Hybrid (6) is érdemben teljesít, és részben más filmeket talált el (Spirited Away, Shaun of the Dead), mint a Popularity. Itt a Popularity vitt 9 találattal, mert a felhasználó ízlése a népszerű filmeket is lefedi.

### Hol nem segített

- **#235 és #176 (Popularity 3–3 találat, a személyre szabott módszerek 0 vagy 1).** A kedvelt filmek (pl. The American President, Get Shorty, Babe) és a releváns teszt filmek (Silence of the Lambs, Terminator 2, Independence Day) között nincs olyan műfaji vagy tartalmi kapcsolat, amit a profil megragadna. Itt a népszerű filmek közül jött a találat.
- **#26 (kevés adat: 17 train értékelés, csak 3 kedvelt film).** A három kedvelt film szűk profilt ad. A Popularity 2, a Content-based és a Hybrid 1 találatot ért el, az SVD nullát. Kevés adattal a személyre szabás nem tud érdemben előnyt szerezni.
- **SVD több felhasználónál.** Az SVD ajánlásai mindegyik példában ugyanazt a szűk klasszikus-halmazt ismétlik (Lawrence of Arabia, Rear Window, Great Escape, Life Is Beautiful, Boondock Saints). Ez az alulillesztett, kevés iterációval tanult modellre jellemző viselkedés: a felhasználótól függetlenül csaknem azonos lista jön, ezért gyakran 0 találat.

## 5. Következtetések

- Ezen az adathalmazon és beállítás mellett a tartalomalapú személyre szabás mérhetően jobb rangsort ad, mint az egyszerű népszerűségi lista.
- Nem minden személyre szabott módszer múlja felül az alapvonalat: az SVD és az SVD-t is használó hibrid ezen a konfiguráción gyengébb a Content-based-nél.
- A személyre szabás haszna nem egyenletes: a felhasználó értékeléseinek számától és ízlésének jellegétől függ. Kevés adatnál vagy a mainstreamtől eltérő ízlésnél a Popularity versenyképes lehet.

## 6. Korlátok

- Egyetlen adathalmaz és egyetlen felosztás (`--seed 42`); a felosztás szórása nem lett mérve.
- Csak 500 elemű, népszerűségi alapú jelölthalmaz; a korábbi jelölthalmaz-kísérletek alapján nem ez a fő ok, de a long-tail teljesítményt ez a beállítás nem méri jól.
- A Precision/Recall értékei abszolút értelemben alacsonyak (a ritka adat és a kicsi, 10 elemű lista miatt); az összehasonlítás a módszerek egymáshoz viszonyított sorrendjére alkalmas.
- Az SVD hiperparaméterei (iterációszám, látens dimenzió) és a hibrid α súlya nem lettek hangolva.
- A példák 6 felhasználóra vonatkoznak, szemléltetésre valók, nem általánosításra.
- Az offline mérés a modellek képességét vizsgálja; a webes alkalmazás használhatóságát a felhasználói kipróbálás vizsgálja.

## 7. Továbbfejlesztési irányok

- SVD hiperparaméter-hangolás (iterációszám, `k`, tanulási ráta) és az α súly csökkentése a hibridben.
- Több felosztás/seed és átlagolás, szórás megadása.
- Nagyobb vagy nem népszerűségi alapú jelölthalmaz vizsgálata.

## Hivatkozás

Cremonesi, P., Koren, Y., & Turrin, R. (2010). Performance of Recommender Algorithms on Top-N Recommendation Tasks. *Proceedings of the 4th ACM Conference on Recommender Systems (RecSys '10)*, 39–46.
