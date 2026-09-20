# TizenTube Custom

Bazuje na oficjalnym TizenTube (reisxd/TizenTube), wersja modulu 1.15.0.

Zmiany:
1. Po "Turn off screen" pierwszy dowolny przycisk TYLKO przywraca obraz.
   Zdarzenie jest konsumowane, wiec nie powinno otwierac "TizenTube Theme Configuration".
2. "Turn off screen" ma dodatkowa mala ikone EYE_OFF na pasku sterowania odtwarzacza.

Instalacja w TizenBrew:
- wrzuc zawartosc tego katalogu do PUBLICZNEGO repozytorium GitHub,
- w TizenBrew -> Module Manager usun npm/@foxreis/tizentube,
- wybierz Add GitHub Module,
- wpisz: TWOJ_LOGIN/NAZWA_REPO,
- wroc do Home TizenBrew i uruchom TizenTube Custom.

Uwaga:
GitHub/jsDelivr moze potrzebowac kilkudziesieciu sekund, zanim nowy plik bedzie widoczny w CDN.
