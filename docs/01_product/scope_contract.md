# Scope Contract

## MVP user story-k és elfogadási kritériumok

### 1. Regisztráció és bejelentkezés
Felhasználóként fiókot akarok létrehozni és bejelentkezni, hogy a saját, perzisztens profilom legyen.

**Elfogadási kritériumok**
- Ha egy új e-mail címmel, érvényes jelszóval regisztrálok, akkor a fiók létrejön, és utána be tudok jelentkezni vele.
- Ha helytelen jelszóval próbálok bejelentkezni, akkor érthető hibaüzenetet kapok, technikai részlet nélkül.
- Ha már foglalt e-mail címmel próbálok regisztrálni, akkor a rendszer elutasítja a kérést, érthető üzenettel.

### 2. Filmek böngészése és értékelése
Felhasználóként filmeket akarok böngészni és értékelni, hogy a rendszer megismerje az ízlésemet.

**Elfogadási kritériumok**
- Ha bejelentkezett felhasználóként megnyitom a filmlistát, akkor látom a címet, a műfajt, és - ha elérhető - a posztert.
- Ha egy filmre 1-5 közötti értékelést adok, akkor az értékelés elmentődik, és a film értékelt státuszban jelenik meg.
- Ha egy már korábban értékelt filmet újraértékelek, akkor a korábbi érték felülíródik, nem duplázódik.

### 3. Személyre szabott ajánlás
Felhasználóként ajánlást akarok kapni a korábbi értékeléseim alapján, hogy könnyebben találjak új, tetsző filmet.

**Elfogadási kritériumok**
- Ha még egyetlen értékelésem sincs, akkor népszerűségi (popularity) alapú ajánlást kapok.
- Ha van 1-6 kedvelt (≥4-es) értékelésem, akkor tartalomalapú (content-based) ajánlást kapok.
- Ha a felhasználó szerepel a legutóbb tanított SVD modellben, akkor az ajánlás SVD/hibrid alapon aktiválódik.
- Ha a felhasználó NEM szerepel a tanított SVD modellben - akkor sem, ha már van 7 vagy több saját értékelése -, akkor a rendszer tartalomalapú vagy népszerűségi tartalékmegoldásra vált, és az eredményt NEM címkézi "hibrid"-nek valódi SVD-pontozás nélkül.
- Minden ajánláshoz rövid indoklás jár (pl. "Hasonló a kedvelt filmjeidhez"), amely a ténylegesen használt módszerből következik.

### 4. Értékelés módosítása és friss ajánlás
Felhasználóként meg akarom tudni változtatni egy korábbi értékelésemet, és ezt a következő ajánlásnak tükröznie kell.

**Elfogadási kritériumok**
- Ha módosítok egy korábban adott értékelést, akkor a következő ajánlás-lekérdezés figyelembe veszi az új értéket.
- Ha a módosítás után kijelentkezem, majd újra bejelentkezem, akkor a friss ajánlás olvasható vissza, nem a régi, gyorsítótárazott lista.
- Ha a gyorsítótárazott ajánlás olyan filmet tartalmaz, amelyet időközben értékeltem, akkor a rendszer automatikusan frissíti a listát, és az értékelt film többé nem jelenik meg benne.

### 5. Ajánlások megjelenítése webes felületen
Felhasználóként interaktív felületen akarom látni az ajánlott filmeket.

**Elfogadási kritériumok**
- Ha érvényesen be vagyok jelentkezve és az ajánlások oldalra navigálok, akkor listát látok, amely tartalmazza a filmek címét, posztereit (ha van) és az ajánlás rövid indoklását.
- Ha nincs elég adat személyre szabott ajánláshoz, akkor az oldal nem üres vagy hibás képernyőt mutat, hanem népszerűségi alapú listát.

### 6. Ajánlórendszer API
Fejlesztőként/kiértékelőként API-n keresztül akarom lekérdezni az ajánlásokat és rögzíteni a felhasználói interakciókat.

**Elfogadási kritériumok**
- A `GET /api/.../recommendations` végpont érvényes JWT-vel személyre szabott listát ad vissza.
- A `POST /api/.../ratings` végpont elmenti az értékelést, és validációs hiba esetén konzisztens hibamodellt ad vissza.
- Az OpenAPI dokumentáció (`/docs`) a ténylegesen elérhető végpontokat tükrözi.

## Non-goals (nem része a projektnek)

- Social funkciók (követés, kommentek, mások értékeléseinek megtekintése)
- Felhasználói aktivitási feed
- Többféle szerepkör (admin, moderátor)
- OAuth / külső bejelentkezés (Google stb.)
- Komplex indexelési stratégiák nagy adatmennyiséghez
- Ajánlásgenerálás valós idejű teljesítmény-optimalizálása (a batch előgenerálás elfogadott)

## Korlátok

- Adat: MovieLens `ml-latest-small` (610 user, ~9700 film, ~100k értékelés) - saját alkalmazásbeli új felhasználók erre a betanított modellre épülnek rá.
- Idő: szakdolgozati keretidő, heti ~15 óra a jelenlegi fázisban (2026.10.10-i vállalás szerint).
- Platform: csak webes kliens (Vue.js), natív mobil nincs.
- Külső API: TMDB (poszterek) - ha nem elérhető, a lista posztert nélkül is működjön (graceful degradation).

## Kész definíciója (Definition of Done) erre a körre (okt. 16-i cél)

- A fenti 1-5. user story mindegyike végigpróbálható egy tiszta telepítésen.
- A 4. story automata e2e teszttel védett (lásd `docs/04_quality/test_strategy.md`).
- A SVD cold-start szabály (3. story) explicit tesztelve: ismeretlen user nem kap hamis "hybrid" címkét.
- README + ez a dokumentum tükrözi a valós viselkedést.
