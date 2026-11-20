# Plan hackathonu: Flexible Alerting & Notification Service

Nov 20, 2026 · @Igor

## Cel i główna idea

Budujemy serwis alertów, w którym wszystko, co różni zespoły (źródła, schematy, reguły, kanały, runbooki), jest konfiguracją, a nie kodem. Rdzeń bierzemy z wcześniejszego pomysłu: log zdarzeń, deterministyczne reguły, widok na żywo, a LLM tylko pomaga. Z repozytorium Dynamic-Monitoring bierzemy prawdziwe źródło alertów (Prometheus + Alertmanager) i stack do mierzenia wydajności.

Trzy rzeczy, które mają nas wyróżnić u jury:

1. **Nowy schemat i nowy runbook od jury działają bez kodu.** Schemat opisuje profil w YAML (mapowanie może zaproponować LLM), a runbook w dowolnym formacie zamieniamy na kroki.
2. **Zmierzone p50/p99 i msg/s** na żywym dashboardzie Grafany oraz skalowanie workerów 1 → 4 pokazane na wideo.
3. **Podgląd reguły przed zapisem.** Edytor pokazuje, ile alertów i do kogo reguła wysłałaby z ostatniej godziny zdarzeń, zanim ktokolwiek dostanie SMS.

| Skąd | Element | Gdzie w zadaniu |
| --- | --- | --- |
| Pomysł z PDF | Append-only log zdarzeń z idempotencją | Ingest, brak zgubionych alertów, replay |
| Pomysł z PDF | Adaptery, walidacja, kolejka błędów | 2.1 Ingest |
| Pomysł z PDF | Akceptacja człowieka przed zmianą w systemach zewnętrznych | 2.6 Ryzykowne akcje |
| Pomysł z PDF | Profile osób w YAML | 2.3 Preferencje kanałów i on-call |
| Pomysł z PDF | Slack Bolt w Socket Mode, wątek na element | Kanał chat, zatwierdzanie odpowiedzią |
| Pomysł z PDF | SSE | 2.4 Live feed |
| Pomysł z PDF | Zwijanie z drill-downem | 2.5 Grupowanie i dedup w UI |
| Pomysł z PDF | Plan vs fakty | 2.6 Runbook vs wykonane kroki |
| Pomysł z PDF | Lokalny LLM (Ollama) | Prywatność, sekcja 4 zadania |
| Dynamic-Monitoring | `deploy/docker-compose.yml` (Prometheus + Grafana) | Źródło z Alertmanagera i metryki naszego serwisu |
| Dynamic-Monitoring | `FakeSource` w `app/exporter/fake.go` | Demo bez Slurma i GPU (trzeba dodać flagę w `main.go`) |
| Dynamic-Monitoring | `perf/` (flame graphy, stress testy) | Slajd o wydajności |

Odrzucamy: adaptery GitHub i Jira, sugestie przydziału, parser Mermaid i SQLite jako jedyny magazyn.

**Założenia do potwierdzenia:** zespół 2-osobowy, backend w Pythonie, godzina 0 to start hackathonu.

## Co jest innowacyjne

Pojedyncze funkcje nie są nowe: PagerDuty ma [AI-generated runbooks i Runbook Automation](https://www.helpnetsecurity.com/?p=274718), a Rootly [generuje postmortemy z sugestiami typu „zaktualizuj runbook”](https://rootly.com/sre/ai-generated-postmortems-outage-data-clear-insights). Wyróżniamy się połączeniem trzech rzeczy, których te narzędzia nie dają razem: bezpieczne zmiany reguł, onboarding bez kodu i wszystko lokalnie.

| Pomysł | Dlaczego się wyróżnia | Koszt przy 2 osobach | Decyzja |
| --- | --- | --- | --- |
| Podgląd i backtest reguły: przed zapisem edytor przepuszcza ostatnią godzinę zdarzeń z logu i pokazuje, ile alertów, do kogo i jakimi kanałami by poszło | Zapobiega zalewowi alertów, zanim ktoś dostanie SMS; zrozumiałe dla nie-inżyniera; korzysta z logu zdarzeń, który i tak mamy | Niski: `XRANGE` ze strumienia przez ten sam silnik reguł | Robimy |
| Onboarding nieznanego schematu: wklejasz JSON, LLM proponuje profil, test na żywych zdarzeniach, zapis | Jury przyniesie nowy schemat, więc pokazujemy to na żywo | Średni | Robimy |
| Wszystko lokalnie: LLM w Ollamie, dane alertów nie wychodzą z maszyny | Dla banku AI w SaaS to problem compliance; to też odpowiedź na pytanie o AI z sekcji 4 | Niski | Robimy |
| Runbook w dowolnym formacie zamieniony na wykonywalne kroki, zatwierdzanie odpowiedzią „APPROVE” na SMS | U dużych graczy istnieje, u nas z wolnego tekstu i bez chmury | Średni | Wersja podstawowa |
| Plan vs fakty: strukturalny diff runbooka z audytem i propozycja nowej wersji | Bliżej istniejących sugestii z postmortemów, więc mniejszy efekt „wow” | Średni | Tylko jeśli zostanie czas |

Na wideo innowację nazywamy jednym zdaniem: „zespoły zmieniają alerty bez strachu i bez kodu, a AI działa lokalnie”.

## Architektura

Zdarzenie przechodzi przez dwa strumienie Redis: `events` (do przetworzenia) i `deliveries` (do dostarczenia). Każdy etap między nimi to bezstanowe workery w consumer group, więc skalujemy je dokładając repliki.

&#91;embedded content: architektura · 4 źródła, 2 strumienie, 4 kanały\]

Główna ścieżka biegnie z góry na dół; konfiguracja, runbooki i LLM są z boku i nie spowalniają dostarczania. Przerywana linia na dole to pomiar opóźnienia end-to-end.

| Warstwa | Wybór |
| --- | --- |
| API i ingest | FastAPI, uvloop, orjson |
| Kolejki | Redis Streams z consumer groups; Kafka / Redpanda jako opcjonalny adapter |
| Magazyn | Postgres (reguły, alerty, outbox, audyt), Redis (okna dedup, pub/sub) |
| UI | React, SSE, edytor YAML z walidacją i formularz reguł |
| Kanały | MailHog, fałszywa bramka SMS i telefonu, generyczny kanał webhook |
| LLM | Ollama lokalnie |
| Metryki | Prometheus i Grafana z Dynamic-Monitoring, Alertmanager jako źródło |
| Uruchomienie | Docker Compose: jedno `docker compose up` |

## Model danych i konfiguracja

Cała konfiguracja to pliki YAML w katalogu `config/` oraz te same obiekty w Postgresie, edytowalne przez API i UI. Watcher plików i API zapisują do bazy, a workery przeładowują reguły po sygnale `config.changed` z Redis pub/sub, bez restartu. Dzięki temu zespół może trzymać reguły w gicie, a nie-inżynier klikać w UI.

**Profil schematu** mówi, jak rozpoznać zdarzenie i gdzie są jego pola. Reguły działają też na surowym JSON-ie, więc profil jest potrzebny tylko do pól wspólnych (severity, źródło, czas, fingerprint). Zdarzenie bez profilu trafia do profilu `generic` z heurystykami (`severity`, `level`, `labels.severity`) i do skrzynki „nieznane schematy” w UI.

```yaml
# config/schemas/trade-rejected.yaml
schema: trade.rejected
match: { glob: { meta.schema: "trade.rejected.*" } }
fields:
  type: meta.schema
  source: meta.producer
  severity: { const: ERROR }
  occurredAt: { path: meta.ts, format: epoch_ms }
  entity: payload.tradeId
fingerprint: [meta.schema, payload.desk, payload.reason]
```

**Reguła** to warunek (zagnieżdżone `all` / `any` / `not`), routing, prezentacja, dedup i opcjonalnie runbook. Operatory: `eq`, `ne`, `gt`, `gte`, `lt`, `lte`, `in`, `glob`, `regex`, `exists`. Pole to ścieżka w surowym zdarzeniu albo pole znormalizowane.

```yaml
# config/rules/rates-large-rejections.yaml
rule: rates-large-rejections
team: rates
when:
  all:
    - { field: type, op: glob, value: "trade.rejected.*" }
    - { field: payload.desk, op: eq, value: rates }
    - { field: payload.notional, op: gt, value: 10000000 }
route:
  channels: [email, ui]
present:
  title: "Rejected {{payload.currency}} {{payload.notional}} — {{payload.reason}}"
  fields: [payload.tradeId, payload.desk]
  color: orange
dedup: { window: 60s }
group: { by: [payload.desk], every: 5m }
runbook: trade-limit-breach
```

**Odbiorca** (osoba lub zespół) ma kontakty, preferencje kanałów zależne od severity i godzin oraz opcjonalny grafik on-call.

```yaml
# config/people/anna.yaml
person: anna
contacts: { email: anna@example.com, sms: "+48600000000" }
preferences:
  - when: { severity: critical, source: payments-api }
    channels: [sms]
    hours: "08:00-20:00"
    otherwise: [email]
```

**Runbook** przyjmujemy w trzech formatach: YAML z krokami, Markdown i wolny tekst. Wszystkie normalizujemy do listy kroków `{kind: text | check | action, action, params, approval}`. Markdown dzielimy na kroki parserem list, a wolny tekst przez LLM. Oryginał zawsze wyświetlamy obok. Parametry są szablonami (`{{workflowId}}`) wypełnianymi wartościami z alertu.

**Akcje** to wtyczki w rejestrze: `http_get`, `webhook`, `retry_workflow`, `restart_service`, `open_ticket`, `escalate`. Nową akcję typu webhook dodaje się samym YAML-em (URL, metoda, szablon body), a nową akcję z logiką jedną klasą z metodą `execute(params)`. Akcja z `approval: required` czeka na zatwierdzenie w UI albo odpowiedź na alert.

**Alert** (model wewnętrzny): `id`, `fingerprint`, `ruleId`, `team`, `severity`, `title`, `body`, `fields`, `count`, `firstSeen`, `lastSeen`, `status` (open, acked, resolved), `runbook`, `audit[]` (kto, co, kiedy, wynik).

## Mapowanie wymagań na rozwiązanie

Każdy punkt zadania ma konkretny element systemu i konkretny moment w demo.

| Wymaganie | Jak realizujemy | Pokazujemy w demo |
| --- | --- | --- |
| 2.1 Co najmniej dwa typy źródeł | Webhook HTTP (w tym Alertmanager) i tail pliku logu (pokrywa Team Pricing z Appendix A); zewnętrzny broker (Redpanda) opcjonalnie. Redis Streams to nasza wewnętrzna kolejka, więc nie liczymy go jako źródła | Trzy przykłady z Appendix A plus prawdziwy alert z Prometheusa |
| 2.1 Różne schematy, mało kodu | Profil schematu w YAML, reguły na surowym JSON-ie, skrzynka „nieznane schematy” z propozycją mapowania od LLM | Schemat od jury wklejony w UI, zapisany, działa |
| 2.2 Filtry na dowolnym polu, AND/OR | Zagnieżdżone `all` / `any` / `not`, operatory porównań, `in`, `glob`, `regex` | Reguła Team Rates z `notional > 10M` |
| 2.2 Routing i prezentacja per reguła | `route` i `present` w regule: szablony tytułu i body, lista pól, kolor | Tytuł „Rejected EUR 25000000 — LIMIT\_BREACH” |
| 2.2 Zmiany w locie | API, UI i watcher plików, przeładowanie przez pub/sub | Edycja reguły bez restartu |
| 2.3 Kanały Email, SMS, telefon, UI | Wtyczki kanałów za jednym interfejsem `send(alert, recipient)`. Email przez MailHog, SMS i telefon przez fałszywą bramkę z podglądem w UI oraz generyczny kanał webhook (URL + szablon body w YAML), który bez kodu obsłuży Slack Incoming Webhook, Teams czy PagerDuty | Telefon i SMS dla Team Settlements |
| 2.3 Preferencje, godziny, on-call | Profile osób i zespołów w YAML, okna godzinowe, rotacja on-call | Anna: SMS w dzień, email w nocy |
| 2.3 Odporność dostarczania | Outbox w Postgresie, retry z wykładniczym backoffem, `XAUTOCLAIM` po padłym workerze, DLQ, kanał zapasowy | Wyłączamy bramkę SMS, alerty przychodzą po jej powrocie |
| 2.4 UI | Live feed przez SSE, ack i resolve, edytor reguł (formularz + YAML), preferencje. Przy każdym alercie przycisk „Zaproponuj poprawkę” (próg, pola, okno dedup, krok runbooka), który trafia do właściciela reguły do akceptacji | Całe demo dzieje się w UI |
| 2.5 Deduplikacja | Fingerprint z profilu lub reguły, okno w Redisie z TTL, licznik | 500 błędów to jeden alert ×500 |
| 2.5 Throttling i grupowanie | `group.by` i `group.every` per reguła, limit na odbiorcę | Team Pricing: jeden alert na instrument co 5 minut |
| 2.6 Runbooki w wielu formatach | YAML, Markdown, wolny tekst normalizowane do kroków, szablony z wartościami alertu | Trzy runbooki z Appendix B plus runbook od jury |
| 2.6 Kroki per kanał | Pełne kroki w UI i emailu, krótki link w SMS | SMS z linkiem do alertu |
| 2.6 Akcje z zatwierdzaniem | Rejestr akcji, `approval: required`, zatwierdzenie w UI albo odpowiedzią „APPROVE” na SMS lub w wątku Slacka | Eskalacja po dwóch nieudanych retry |
| 2.6 Audyt i auto-zamykanie | `audit[]` przy alercie, zamknięcie po zdarzeniu „resolved” ze źródła lub po ciszy przez okno | Alertmanager wysyła `status: resolved` |
| 2.6 Opcjonalnie: auto-aktualizacja runbooków | Plan vs fakty: kroki pomijane i akcje spoza runbooka stają się propozycją nowej wersji do zatwierdzenia | Propozycja „dodaj krok: wyczyść cache” |

## Skalowalność i niezawodność

Każdy proces jest bezstanowy i skaluje się przez dodanie replik. Stan żyje w Redisie (strumienie i okna dedup) oraz w Postgresie (reguły, alerty, dostawy, audyt).

- **Ingest:** FastAPI w N replikach. Zapisuje surowe zdarzenie do strumienia `events` (`XADD`) i od razu zwraca 202. Identyfikator dostawy (z nagłówka albo hash treści) daje idempotencję.
- **Processor:** workery w consumer group czytają paczkami (`XREADGROUP COUNT 100`). Normalizacja, dopasowanie reguł z pamięci, dedup przez `SET fp NX EX window` i `INCR`. Pierwsze wystąpienie zapisuje alert i wpis do tabeli \`outbox\` w jednej transakcji Postgresa, kolejne tylko podbijają licznik. Zapisy idą paczkami przez asyncpg, nie pojedynczym INSERT-em na zdarzenie.
- **Delivery:** osobna consumer group na strumieniu `deliveries`. Retry z wykładniczym backoffem, circuit breaker na kanał, `XAUTOCLAIM` przejmuje wiadomości padniętego workera. Po N porażkach trafiają do DLQ i do kanału zapasowego (np. SMS nie działa, więc email + UI).
- **UI push:** serwer SSE subskrybuje `alerts.team.<id>` w Redis pub/sub, więc też działa w wielu replikach.
- **Reguły:** źródło prawdy w Postgresie, kopia w pamięci workera, unieważniana sygnałem `config.changed`.

**Outbox bez dual-write.** Processor nie robi `XADD` do `deliveries` sam. Osobny relay co 1–2 s bierze z tabeli `outbox` niewysłane wpisy (`FOR UPDATE SKIP LOCKED`), dodaje je do strumienia i oznacza jako wysłane. Gdy Redis padnie po commicie, wpis czeka w Postgresie, a ewentualny duplikat łapie idempotencja dostawy po ID wpisu.

**Grupowanie to inny mechanizm niż dedup.** Dedup łączy identyczne zdarzenia w jeden alert z licznikiem. Grupowanie (`group.by` + `group.every`) zbiera różne zdarzenia w buforze Redisa (klucz: reguła + grupa, np. instrument) i po upływie okna wysyła jeden zbiorczy alert. Na demo okno 10 s zamiast 5 minut.

**Load test bez sztucznego wąskiego gardła:** ingest w 2–4 workerach uvicorn, generator jako osobny proces, Redis pipeline przy zapisach. Inaczej wykres skalowania 1 → 4 workerów stanie w miejscu z powodu wejścia, a nie processora.

Uczciwie o słabych punktach (jury o to zapyta): Redis jest pojedynczym punktem awarii w wersji demo. Na produkcji: Redis Sentinel lub Cluster albo zamiana strumieni na Kafkę / Redpandę partycjonowaną po fingerprincie. Interfejs adaptera zostaje ten sam, a partycjonowanie po fingerprincie trzyma dedup jednego alertu na jednym workerze. Postgres na produkcji dostaje replikę.

W Pythonie wydajność trzymamy przez uvloop, orjson, paczki w strumieniach i brak wywołań LLM w głównej ścieżce. Jeśli load test pokaże, że processor jest wąskim gardłem, przepisanie go w Go jest odizolowaną zmianą (o ile ktoś w zespole zna Go).

## Warstwa LLM i prywatność

LLM nigdy nie decyduje o routingu, deduplikacji ani nie wykonuje akcji. Proponuje, a człowiek zatwierdza. Działa lokalnie przez Ollamę za jednym interfejsem, więc model można podmienić.

| Zastosowanie | Wejście → wyjście | Zabezpieczenie |
| --- | --- | --- |
| Runbook w wolnym tekście lub Markdown | Tekst → lista kroków (`text`, `check`, `action` + parametry) | Walidacja Pydantikiem, ponowienie przy błędzie, oryginał zawsze widoczny, kroki-akcje wymagają zatwierdzenia |
| Nieznany schemat | Przykładowy JSON → propozycja profilu (które pole to severity, źródło, czas, fingerprint) | Człowiek zatwierdza i zapisuje jako YAML |
| Reguła opisana słowami | „Team Rates: trade.rejected.\* gdzie notional > 10M → email” → YAML reguły | Podgląd i test na ostatnich zdarzeniach przed zapisem |
| Propozycje poprawek runbooka | Audyt rozwiązanych alertów → opis zmiany i nowa wersja | Diff wersji do zatwierdzenia |

Model nie pisze YAML-a bezpośrednio, bo małe modele psują wcięcia: zwraca JSON wymuszony schematem (structured output w Ollamie), walidowany Pydantikiem, a YAML serializujemy w Pythonie. Model sprawdzamy na naszym sprzęcie w 1. godzinie. Wyniki są w cache po hashu treści, a wywołania asynchroniczne, poza ścieżką ingest → delivery. Gdy LLM nie działa, system dalej działa: wolny tekst pokazujemy jako jeden krok tekstowy, a mapowanie schematu robi się ręcznie w formularzu.

Prywatność: żadne dane alertów nie opuszczają maszyny, a przed wysłaniem do modelu redagujemy wzorce sekretów (tokeny, hasła, numery kart). Model wybieramy pod sprzęt zespołu (mały model 7–8B przy kilku GB VRAM; ustalić przed startem).

Do zgłoszenia (sekcja 4 zadania): asystenci AI pomagali przy kodzie, testach i dokumentacji; do narzędzi chmurowych nie trafiały dane produkcyjne ani sekrety, a dane demo są syntetyczne. Kod od AI przechodzi review i testy jak każdy inny.

## Harmonogram 18 godzin

Po 7 godzinach musi działać pełna ścieżka od zdarzenia do powiadomienia, po 11 pierwszy pomiar, a po 14 zamrażamy funkcje. Dwie osoby pracują równolegle na wspólnym modelu `Alert` i kontraktach strumieni ustalonych w pierwszej godzinie.

&#91;embedded content: harmonogram 18 h · 4 role, 6 faz\]

Bramy na koniec każdej fazy (jeśli nie są spełnione, tniemy według kolejności z sekcji o ryzykach):

- [ ] 3 h: `docker compose up` stawia całość, generator wrzuca zdarzenia do strumienia, UI je widzi
- [ ] 7 h: trzy przykłady z Appendix A dają alerty w UI i emailu, retry działa
- [ ] 11 h: reguły zmieniane w locie, dedup, preferencje Anny, pierwszy pomiar p50/p99
- [ ] 14 h: runbook z zatwierdzaniem działa od alertu do audytu, wyniki load testu w Grafanie (feature freeze)
- [ ] 16 h: ścieżka „nowy schemat i runbook od jury” przetrenowana
- [ ] 18 h: wideo i link do repo w Lockboxie

**Praca z agentami AI w 2 osoby:** w 1. godzinie wspólny katalog `contracts/` (schematy zdarzeń, model `Alert`, API, eventy SSE), żeby backend i frontend się nie rozjechały. Do tego `smoke_test.py` (3 zdarzenia z Appendix A; sprawdza API, MailHog, dedup i runbook) odpalany po każdej zmianie. Zero auth: zespół wybiera się z listy w UI.

## Load test i pomiary

Jury chce liczb zmierzonych, więc pomiar wbudowujemy od pierwszej godziny, a nie na końcu. Każde zdarzenie z generatora niesie `sentAt`, a mock kanału zapisuje `deliveredAt`. Różnica trafia do histogramu Prometheusa `alert_e2e_latency_seconds`.

**Generator** (`loadtest/`, Python asyncio + httpx albo k6) wysyła mieszankę trzech schematów z Appendix A i jednego nieznanego, z regulowanym tempem i odsetkiem duplikatów. Ten sam skrypt służy do demo.

**Metryki w Grafanie** (stack z Dynamic-Monitoring): ingest msg/s, processed msg/s, lag strumieni, p50 / p95 / p99 end-to-end, liczba retry i wpisów w DLQ.

| Scenariusz | Co mierzymy | Co ma wyjść |
| --- | --- | --- |
| Stałe obciążenie | p50 i p99 przy stałym tempie | Stabilne opóźnienie, zerowy lag |
| Schodki do nasycenia, 1 / 2 / 4 workery | Maksymalne msg/s, przy którym lag nie rośnie | Przepustowość rośnie z liczbą workerów (skalowanie poziome) |
| Burza duplikatów | Liczba alertów vs liczba zdarzeń | Jeden alert z licznikiem |
| Kanał wyłączony na 60 s | Wysłane vs dostarczone po powrocie kanału | Zero strat |
| Zabity worker w trakcie | Wiadomości przejęte przez `XAUTOCLAIM` | Zero strat |

Wyniki trafiają do tabeli w README ze sprzętem, na którym mierzyliśmy, oraz na zrzut z Grafany do wideo. Docelowych liczb nie zakładamy z góry; pierwszy pomiar robimy około 11. godziny, żeby zdążyć poprawić wąskie gardło.

## Scenariusz demo i wideo 5 min

Wideo jest główną podstawą oceny, więc każde kryterium jury musi mieć w nim swoje kilkadziesiąt sekund. Nagrywamy fragmentami od 14. godziny, nie na samym końcu.

| Czas | Scena | Kryterium |
| --- | --- | --- |
| 0:00–0:30 | Problem i jedno zdanie o rozwiązaniu, diagram architektury | Prezentacja |
| 0:30–1:15 | `git clone` + `docker compose up`, UI się otwiera. Nowy zespół wkleja nieznany JSON, system proponuje mapowanie, zapis, pierwsze alerty | UX, elastyczność |
| 1:15–2:15 | Reguła Team Rates w edytorze z podglądem: ile alertów i do kogo poszłoby z ostatniej godziny, generator wysyła `trade.rejected`, alert w live feedzie i email w MailHogu. Anna: SMS w dzień, email w nocy | Elastyczność, UX |
| 2:15–3:15 | `WORKFLOW_FAILED`: telefon i SMS (mock), w UI runbook YAML z wypełnionym `workflowId`. Health check i retry automatycznie, eskalacja czeka na „APPROVE”. Runbook z wolnego tekstu zamieniony na kroki | Runbooki, innowacja |
| 3:15–3:45 | 500 błędów daje jeden alert ×500. Wyłączona bramka SMS, po powrocie nic nie zginęło | Niezawodność |
| 3:45–4:30 | Grafana: msg/s, p50/p99, skalowanie 1 → 4 workerów | Przepustowość, skalowalność |
| 4:30–5:00 | Prawdziwy alert z Prometheusa (Dynamic-Monitoring), LLM działa lokalnie, jak używaliśmy AI | Innowacja, sekcja 4 |

Na finał na żywo przygotowujemy ścieżkę „jury przynosi swój schemat i runbook”: wklejenie JSON-a, zatwierdzenie mapowania, reguła, wklejenie runbooka, wysłanie zdarzenia. Trenujemy ją na JSON-ie i runbooku przygotowanych przez osobę z zespołu, która nie pisała parsera.

Do Lockboxa: wideo, plik z linkiem do repo, README z liczbą komend do demo i listą tego, co zmockowane.

## Ryzyka, mocki i zakres

**Co mockujemy** (lista do README, wymagana przez jury):

- Email: MailHog, czyli prawdziwy protokół SMTP bez wysyłki na zewnątrz. Prawdziwy dostawca to zmiana konfiguracji.
- SMS i telefon: fałszywa bramka z zakładką „Telefon” w UI, która pokazuje dostawy i pozwala odpowiedzieć „APPROVE”. Prawdziwy dostawca (np. Twilio) to jedna klasa kanału.
- Akcje runbooków: `retry_workflow`, `restart_service` i `open_ticket` wołają mock serwisu, który loguje wywołania i potrafi „naprawić” problem, żeby pokazać auto-zamknięcie.
- Slack, Teams, PagerDuty: przez generyczny kanał webhook; na demo wysyła do lokalnego odbiornika, który loguje payload.
- Zdarzenia: generator syntetyczny plus prawdziwy Alertmanager z Dynamic-Monitoring (eksporter w trybie `FakeSource`).

| Ryzyko | Plan B |
| --- | --- |
| Brak GPU, lokalny LLM za wolny | Mały model, wyniki w cache i nagrane wcześniej; bez LLM wolny tekst jest jednym krokiem, a mapowanie robi się w formularzu |
| Edytor reguł zjada czas | Najpierw edytor YAML z walidacją i podglądem na ostatnich zdarzeniach, formularz tylko dla prostych warunków |
| Jury pyta o pojedynczy punkt awarii | Gotowa odpowiedź z sekcji o skalowalności (Sentinel lub Kafka partycjonowana po fingerprincie) |
| Demo na żywo się sypie | Wideo jest podstawą oceny, a na finał mamy nagrany fallback |
| Za mało czasu | Cięcia w kolejności poniżej |

**Przy 2 osobach od razu poza zakresem:** pełny Slack Bolt (zastępuje go kanał webhook), Kafka, grafiki on-call (zostają godziny pracy), reguła ze zdania. **Kolejność dalszych cięć**, jeśli nie zdążymy: 1) plan vs fakty, 2) onboarding schematu przez LLM (zostaje ręczny formularz mapowania), 3) LLM dla wolnego tekstu (zostaje jako jeden krok tekstowy), 4) formularz reguł (zostaje edytor YAML). Nie tniemy: dwóch typów źródeł, dedup, retry bez strat, runbooków z zatwierdzaniem, podglądu reguły, przycisku propozycji poprawek (wymaganie 2.4) i pomiaru p50/p99.

**Poza zakresem:** adaptery GitHub i Jira, sugestie przydziału osób, plan w Mermaid, uwierzytelnianie użytkowników (w UI wybór zespołu z listy).

**Do ustalenia od razu:** kto bierze tor A, a kto B; sprzęt pod LLM; czy ktoś zna Go.
