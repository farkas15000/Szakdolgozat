# UX Flows

## Fő flow: Új felhasználó – értékelés – ajánlás – frissítés

**Cél:** egy új felhasználó a regisztrációtól eljusson a számára releváns, folyamatosan frissülő ajánlásig.

**Előfeltétel:** a rendszer fut, a popularity/content/SVD modellek be vannak tanítva.

| # | Lépés                                          | Siker kritérium |
|---|------------------------------------------------|---|
| 1 | Regisztráció (e-mail + jelszó)                 | Fiók létrejön, a felhasználó bejelentkezett állapotba kerül |
| 2 | Film lista böngészése                          | Legalább 1 oldalnyi film látszik címmel, műfajjal |
| 3 | 7 film értékelése (1–5 skálán)                 | Minden értékelés elmentve, a film "értékelt" státuszú |
| 4 | Ajánlás lekérése                               | Mivel a user még nincs az SVD modellben (még ha van is 5 értékelése) → **content-based** ajánlás jön, rövid indoklással ("Hasonló a kedvelt filmjeidhez") |
| 5 | Egy korábbi értékelés módosítása (pl. 2★ → 5★) | Mentés sikeres |
| 6 | Ajánlás újra lekérése                          | A lista tükrözi az új értékelést (a frissen kedvelt film műfajához illő ajánlások jelennek meg) |
| 7 | Kijelentkezés, majd új bejelentkezés           | A visszaolvasott ajánláslista megegyezik a 6. lépésben kapottal (nem a 4. lépés elavult cache-e) |

### Siker kritérium (összegzés)
A 7. lépés után látott lista **nem** tartalmazza a már értékelt filmeket, és **nem** azonos a módosítás előtti (4. lépésbeli) listával, ha a módosítás műfajt/profilt érdemben befolyásolt.

---

## Flow: Ismert (régi) felhasználó – SVD aktiválódás

**Cél:** bemutatni, mikor kapcsol be ténylegesen az SVD/hybrid ajánló.

| # | Lépés                                                                                                       | Siker kritérium |
|---|-------------------------------------------------------------------------------------------------------------|---|
| 1 | Bejelentkezés egy olyan felhasználóval, aki szerepel a legutóbb tanított SVD modellben                      | – |
| 2 | Ajánlás lekérése                                                                                            | A válaszban az algoritmus mező `hybrid` vagy `svd`, és az indoklás ténylegesen SVD-pontozásra utal |
| 3 | (Kontroll) Bejelentkezés egy friss, a modellben nem szereplő felhasználóval, akinek van 7+ saját értékelése | Ajánlás `content-based` vagy `popularity`, **nem** `hybrid` – ez bizonyítja az SVD cold-start szabály helyes működését |

---

## Hibakezelés UX (minimum 3 eset)

| Helyzet | Amit a felhasználó lát | Amit NEM szabad látnia |
|---|---|---|
| Rossz jelszóval bejelentkezés | "Hibás e-mail vagy jelszó." | Stack trace, SQL hiba |
| Üres találati lista (pl. nincs elég adat) | "Egyelőre nincs elég adatunk – nézd meg a legnépszerűbb filmeket" + popularity lista | Üres fehér képernyő |
| TMDB API nem elérhető (poszter hiányzik) | Film cím/műfaj poszter nélkül jelenik meg | Törött kép ikon vagy az egész oldal hibája |

## Empty state

Ha a felhasználónak még nincs egyetlen értékelése sem: az ajánlások oldal popularity listát mutat, egy rövid magyarázó szöveggel ("Értékelj néhány filmet a személyre szabott ajánlásokért").

## Alap accessibility

- Szöveg/háttér kontraszt WCAG AA szerint.
- Értékelés UI billentyűzettel is elérhető (tab + enter/space).
- Hibaüzenetek szövegesen is megjelennek, nem csak színkóddal.
