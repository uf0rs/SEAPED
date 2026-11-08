"""Manual content chapters (rendered as Markdown inside the MANUAL section)."""

from __future__ import annotations

from typing import Dict, List, Tuple

CHAPTERS_EN: List[Tuple[str, str, str]] = [
    (
        "about",
        "1 · About SEAPED",
        """
# About SEAPED

**SEAPED** is a professional suite for load testing websites and checking the
resilience of server infrastructure. It runs in your terminal as a full-screen
application with complete mouse and keyboard control.

## What it does

* generates controlled HTTP/HTTPS traffic (virtual users) against a target you choose,
* measures latency, throughput, errors and availability in real time,
* visualises the load curve while the test is running,
* saves every run as a report you can export to JSON / CSV / HTML,
* optionally distributes the load across extra computers that **you own**,
* manages your own proxy list and network profiles.

## Who it is for

Site owners, QA and DevOps engineers who need to answer questions like:

* how many users can my service handle?
* where does latency start to grow?
* does the auto-scaling react to a traffic spike?
* does the service survive a long soak test?

## Rules of use (important)

SEAPED is a **measurement tool**. Run it only against systems that you own or
for which you have explicit written permission. Before every test you must
confirm the ownership checkbox in the *Configure* section — the application
refuses to start otherwise.

Do not point SEAPED at third-party services, APIs of other companies or any
infrastructure you are not allowed to stress.

## Technology

Python 3.10 · Textual TUI (mouse + keyboard) · asyncio/aiohttp engine ·
AES-256-GCM encrypted control channel for distributed agents · PyInstaller build.
""",
    ),
    (
        "interface",
        "2 · Interface overview",
        """
# Interface overview

The window is split into three areas:

| Area | Purpose |
|------|---------|
| **Left sidebar** | navigation between sections; shows the current scenario and proxy profile |
| **Main area** | the active section |
| **Bottom status bar** | live state of the test: state, target, elapsed, users, RPS, p95, errors, agents |

## Sections

* **Dashboard** — live KPI tiles, realtime charts, event log, Start/Stop controls.
* **Configure** — every test parameter: target, request profile, scenario,
  safety limits, proxy profile, authorization and presets.
* **Results** — history of runs, detailed summary, error breakdown and exports.
* **Proxies** — add/import/check your own proxies, group them into profiles.
* **Agents** — distributed testing: coordinator, connected devices, fleet control.
* **MANUAL** — this documentation.
* **About** — version and developer information.

## Mouse

All buttons, table rows, switches, dropdowns and scroll areas respond to the
mouse. Tables use a row cursor: click a row to select it, then press the
action buttons. Charts and logs scroll with the wheel.

## Keyboard

| Key | Action |
|-----|--------|
| `F1` | open MANUAL |
| `F5` | start the configured test |
| `F6` | stop the running test |
| `Esc` | back to Dashboard |
| `Tab` / `Shift+Tab` | move between controls |
| `Enter` | activate the focused button |
| arrows | navigate lists, tables and dropdowns |

Keys are ignored while you are typing inside a text field.
""",
    ),
    (
        "basics",
        "3 · Load testing basics",
        """
# Load testing basics

## Key metrics

| Metric | Meaning |
|--------|---------|
| **Virtual users (VU)** | simulated concurrent clients, each sending requests in a loop |
| **RPS** | requests per second — the throughput of the test |
| **Latency** | time from sending a request to receiving the response, in milliseconds |
| **p50 / p90 / p95 / p99** | the value below which that percentage of responses falls; p95 is the usual "slow but acceptable" boundary |
| **Availability** | share of successful responses out of all attempts |
| **Error rate** | share of failed requests (timeouts, 5xx, connection errors) |

Example: *p95 = 450 ms* means that 95 % of all responses were faster than
450 ms — only the slowest 5 % took longer.

## Scenarios

| Scenario | Load shape | Use it to |
|----------|-----------|-----------|
| **Smoke Test** | 1–5 users, ~30 s | verify the URL, method and settings |
| **Constant Load** | fixed number of users | baseline behaviour at a known load |
| **Ramp-Up** | linear growth | find the point where latency starts to rise |
| **Step Load** | four plateaus | compare metrics between discrete load levels |
| **Spike** | sudden burst, hold, drop | check autoscaling and recovery |
| **Stress Test** | aggressive growth until a limit | find the breaking point |
| **Endurance** | long moderate load | leaks, pool exhaustion, slow degradation |

## How a test runs

1. SEAPED validates the configuration and the authorization flag.
2. The scheduler spawns virtual users according to the chosen scenario.
3. Every virtual user sends requests with an optional think time between them.
4. Each response is measured and recorded (latency, status, bytes).
5. Once per second a sample is written to the live charts.
6. Safety limits are checked continuously; if one is reached the test stops
   on its own and the reason is stored in the report.
7. When the duration ends, remaining users are released and the report is saved.
""",
    ),
    (
        "configure",
        "4 · Configuring a test",
        """
# Configuring a test

All parameters live in **Configure**, split into three simple tabs. Changes are
applied with *Apply & open Dashboard*; *Start test now* applies and launches.
The bottom bar always shows the presets, the ownership confirmation and the
action buttons.

## Tab “Target”

| Field | Meaning |
|-------|---------|
| **Test name** | appears in the history and in reports |
| **Target URL** | base address, `http://` or `https://` (auto-added if missing) |
| **Method** | GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS |
| **Path** | path/query appended to the target, e.g. `/api/search?q=test` |
| **Expected status** | status code counted as success; `0` = any 2xx/3xx |
| **follow redirects** | let the client follow 3xx responses |
| **verify TLS** | validate the server certificate (disable only for self-signed test hosts) |

## Tab “Load”

| Field | Meaning |
|-------|---------|
| **Scenario** | the load shape (see section 3) |
| **Start users** | users active at the beginning of the ramp |
| **Max users** | upper bound of concurrent users |
| **Duration (s)** | total length of the test |
| **Ramp-up (s)** | time used to grow from start to max users |

The chart on the right previews the exact user count over time.

## Tab “Advanced”

**Request:** custom headers (one `Name: value` per line, `#` starts a comment),
request body for POST/PUT/PATCH, per-request timeout, think time (pause between
requests of one user).

**Safety limits (auto-stop):**

| Field | Meaning |
|-------|---------|
| **Max users** | hard ceiling, the engine never spawns more |
| **Max duration (s)** | hard duration ceiling |
| **Max req/s** | client-side throttle implemented with a token bucket |
| **Stop at errors (%)** | stop when the error rate exceeds this value (0 = off) |
| **Stop at p95 (ms)** | stop when p95 latency exceeds this value (0 = off) |
| **Stop after N failures** | stop after this many consecutive failures |
| **Warm-up (s)** | grace period before error/latency rules are applied |

0 disables a rule; the test stops automatically when a limit is reached.

**Network:** proxy profile (section 6) or a direct connection.

## Authorization and presets

The checkbox *I own this target or have written permission to test it* is
mandatory. The flag is intentionally **never saved** to disk — you confirm it
for every session.

Presets (bottom bar) save the current configuration under a name, reload it
later, or delete it. Presets are stored as JSON in the `presets/` folder.
""",
    ),
    (
        "results",
        "5 · Charts and results",
        """
# Charts and results

## Reading the live charts

**Throughput chart**

* teal line — requests per second currently achieved;
* red line — failed requests per second;
* if the teal line flattens while users keep growing, the server has reached
  its capacity;
* if the red line rises, something starts to fail — check the event log.

**Latency chart**

* blue — p50 (typical response time);
* amber — p95 (the slowest 5 %);
* red — p99 (worst 1 %);
* a sharp jump of all three lines means saturation: queues, CPU or database
  limits;
* p95 growing while p50 stays flat means a minority of requests is stalling —
  usually a lock, a cache miss or a cold worker.

## Interpreting a finished run

The **Results** section shows, for every run:

* requests, successes, failures and availability;
* throughput average and peak;
* latency avg / p50 / p90 / p95 / p99 / max;
* error breakdown by kind (`timeout`, `http_500`, `conn_refused`, `dns_error`,
  `tls_cert`, `proxy_error`, …);
* HTTP status class distribution;
* the reason the test ended (duration, user limit, error rate, latency, manual stop).

## Exports

* **Export CSV** — one row per second, ready for spreadsheets;
* **Export HTML** — self-contained report with an embedded chart, suitable for
  sharing with a team;
* **📁 Folder** — open the `results/` folder containing JSON, CSV and HTML files.

Reports are created automatically after every completed test.
""",
    ),
    (
        "proxies",
        "6 · Proxies and network profiles",
        """
# Proxies and network profiles

The **Proxies** section manages servers that *you* provide.

## Adding a proxy

Fill in scheme, host, port and — if required — username/password, give it a
label and a profile name, then press **＋ Add**.

Supported schemes: `http`, `https`, `socks5`, `socks4`
(SOCKS requires the optional `aiohttp-socks` package).

## Importing a list

Enter the path to a text file and press **⤓ Import file**. Accepted formats,
one entry per line:

```
10.0.0.1:8080
socks5://user:pass@10.0.0.2:1080
# comments and empty lines are skipped
```

## Checking proxies

**✔ Check all** sends a real request through every enabled proxy and records:

* whether it works at all,
* connection latency,
* the exit IP address,
* region/ISP (only if online lookup is available),
* the time of the last check.

Only proxies marked **online** are used in tests.

## Network profiles

A *profile* is just a name you attach to proxies (for example `europe`,
`backup`, `lab`). In **Configure → Network** you pick the profile that the test
should use. If none is selected the test goes through a direct connection.

## Policy

SEAPED never downloads public proxy lists and never uses unknown proxies
automatically. Everything in this section is added, verified and selected by
you.
""",
    ),
    (
        "distributed",
        "7 · Distributed testing",
        """
# Distributed testing

Distributed testing lets several computers that **you own** take part in one
test session. It is optional — everything works without it.

## Roles

* **Coordinator** — runs inside SEAPED, listens on a TCP port, keeps the list
  of devices and merges their metrics.
* **Agent** — a separate process started on a worker machine; it connects
  *outbound* to the coordinator (no port opening on the worker is needed).

## Starting a session

1. Open **Agents**, press **Generate** to create a session token.
2. Press **▶ Start coordinator** — the status line turns green.
3. Copy the displayed command line and run it on each device you own:

```
python -m seaped.agent --host <coordinator-ip> --port 8765 \
    --token <token> --consent --max-vus 100 --max-duration 600 --max-rps 2000
```

4. Devices appear in the table with their state, caps and current test.
5. Press **▶ Start test on fleet** to dispatch the configured test to every
   connected device (tick *include this machine* to also load the local box).

## Owner controls

| Control | Effect |
|---------|--------|
| `--consent` | without it the device is an observer and refuses tests |
| `--max-vus` | owner's ceiling for virtual users — the coordinator can only lower it |
| `--max-duration` | owner's ceiling for test length |
| `--max-rps` | owner's ceiling for request rate |
| **Disconnect selected** | kicks the device and blocks it for 5 minutes |
| **Ping all** | checks the liveness of every device |
| **Save merged report** | writes one combined report for the whole fleet |

## Security

* authentication uses an HMAC proof derived from the shared token — the token
  itself never travels over the network;
* every session negotiates a fresh key with HKDF; all further messages are
  encrypted and authenticated with **AES-256-GCM**;
* message counters are strictly monotonic, which prevents replay attacks;
* a device executes a test only if its owner started it with `--consent` **and**
  the specification carries the operator's authorization flag.

## Scaling

The coordinator handles several dozen devices comfortably. Metrics are merged
per second, so the dashboard charts show the combined fleet load.
""",
    ),
    (
        "safety",
        "8 · Safe usage examples",
        """
# Safe usage examples

## Example 1 — smoke check before a real run

```
Scenario      : Smoke Test
Target        : https://staging.example.com
max VUs       : 5
Duration      : 30 s
Error stop    : 10 %
```

Purpose: confirm that the URL, method, headers and proxy profile are correct.

## Example 2 — find the capacity of a service

```
Scenario      : Ramp-Up
start / max   : 10 → 400 users
Duration      : 10 min
p95 stop      : 3000 ms
Error stop    : 5 %
Warm-up       : 15 s
```

Watch where the p95 line bends — that is your practical capacity.

## Example 3 — burst recovery (production, off-peak)

```
Scenario      : Spike
max VUs       : 200
Duration      : 3 min
Error stop    : 10 %
```

Observe how fast latency returns to normal after the burst.

## Example 4 — long soak (staging)

```
Scenario      : Endurance
max VUs       : 80
Duration      : 2 h
p95 stop      : 5000 ms
```

Compare the first and the last half-hour of the run: growing latency with a
constant load usually means a leak.

## Checklist before pressing Start

1. You own the target or have written permission.
2. The target is a staging/pre-production host whenever possible.
3. Safety limits are set (users, duration, error rate, latency).
4. The warm-up window covers the first seconds of ramp-up.
5. You told your team that a test is running.
6. In production, run at off-peak hours and keep the stop rules armed.

## What not to do

* do not test systems you do not own;
* do not disable the safety limits "just to see what happens";
* do not run production tests without a rollback plan;
* do not share your session token publicly.
""",
    ),
    (
        "troubleshooting",
        "9 · Errors and troubleshooting",
        """
# Errors and troubleshooting

## Error kinds shown in reports

| Kind | Meaning | What to check |
|------|---------|---------------|
| `timeout` | no response within the timeout | server load, timeout value, network |
| `conn_refused` | the host actively refused the connection | service is running, correct port |
| `dns_error` | the hostname could not be resolved | URL spelling, DNS settings |
| `tls_cert` / `tls_error` | certificate or handshake problem | certificate validity, `verify TLS` switch |
| `conn_error` | other connection-level failure | firewall, proxy, VPN |
| `proxy_error` | the selected proxy is unusable | run *Check all* in Proxies |
| `http_4xx` / `http_5xx` | server answered with an error status | application logs, expected status field |
| `too_many_redirects` | redirect loop | disable *follow redirects* |
| `client_error` | other client-side problem | event log for details |

## Common situations

**"Target URL is required"** — fill in the target field in Configure.

**"Test not authorized"** — tick the ownership confirmation checkbox.

**"Proxy profile has no working proxies"** — run *Check all* and add the
missing servers, or switch to a direct connection.

**The test stops immediately with "Error rate limit reached"** — the target is
failing; look at the event log, or raise the warm-up window.

**Charts stay empty** — the test has not produced a full second yet; wait a
moment or check the event log for errors.

**Coordinator will not start** — the port is already in use; choose another
port or stop the previous coordinator.

**A device does not appear** — verify host/port/token, check that the agent
process is running and that a firewall allows outbound TCP to the coordinator.
""",
    ),
    (
        "developer",
        "10 · Developer",
        """
# Developer

**Project:** SEAPED — Professional Load Testing Suite

**Developer:** @uf0rs

**Telegram channel:** @HSIIHprime

**Version:** 2.0.0

## Project layout

```
SEAPED/
├── seaped/              application package
│   ├── core/            load engine, metrics, scenarios, limits, reports
│   ├── net/             proxy management and network profiles
│   ├── dist/            coordinator, agent, encrypted protocol
│   └── ui/              Textual interface: sections, widgets, theme
├── tests/               unit and integration tests
├── presets/             saved test configurations
├── results/             reports (JSON / CSV / HTML)
└── seaped.exe           built application (after `build_exe.py`)
```

## Building the executable

```
python build_exe.py
```

PyInstaller produces `dist\\SEAPED\\SEAPED.exe` — a standalone build that does
not require Python to be installed on the target machine.

## Extending SEAPED

* new scenario → add a scheduler function and a `Scenario` entry in
  `seaped/core/scenarios.py`;
* new metric → extend `MetricsCollector` and the dashboard tiles;
* new section → create a class inheriting `Section`, register it in
  `seaped/ui/screens/__init__.py` and in the sidebar of `seaped/ui/app.py`.
""",
    ),
]


CHAPTERS_RU: List[Tuple[str, str, str]] = [
    (
        "about",
        "1 · О SEAPED",
        """
# О SEAPED

**SEAPED** — профессиональный набор для нагрузочного тестирования сайтов и
проверки устойчивости серверной инфраструктуры. Работает в терминале как
полноэкранное приложение с поддержкой мыши и клавиатуры.

## Что умеет

* генерирует управляемый HTTP/HTTPS-трафик (виртуальные пользователи);
* измеряет задержку, пропускную способность, ошибки и доступность в реальном времени;
* показывает график нагрузки во время теста;
* сохраняет каждый запуск как отчёт (JSON / CSV / HTML);
* при желании распределяет нагрузку по дополнительным компьютерам, **которыми
  владеете вы**;
* управляет вашим списком прокси и сетевыми профилями.

## Для кого

Для владельцев сайтов, QA- и DevOps-инженеров, которым нужно ответить на вопросы:

* сколько пользователей выдержит сервис?
* где начинает расти задержка?
* сработает ли автоскейлинг при всплеске трафика?
* переживёт ли сервис длительный тест на выносливость?

## Правила использования

SEAPED — **инструмент измерений**. Запускайте его только на системах, которыми
владеете, или на тестирование которых у вас есть письменное разрешение. Перед
каждым тестом нужно подтвердить чекбокс прав на цель в разделе *Настройка* —
без этого приложение не стартует.

Не направляйте SEAPED на сторонние сервисы, чужие API или инфраструктуру,
тестировать которую вам не разрешено.

## Технологии

Python 3.10 · Textual TUI (мышь + клавиатура) · движок asyncio/aiohttp ·
зашифрованный канал AES-256-GCM для распределённых агентов · сборка PyInstaller.
""",
    ),
    (
        "interface",
        "2 · Интерфейс",
        """
# Интерфейс

Окно состоит из трёх частей:

| Область | Назначение |
|---------|-----------|
| **Слева — панель разделов** | переходы между разделами; показывает сценарий и профиль прокси |
| **Центр — активный раздел** | содержимое раздела |
| **Внизу — статус-бар** | живое состояние теста: состояние, цель, время, VU, RPS, p95, ошибки |

## Разделы

* **Главная** — плитки состояния, графики в реальном времени, журнал событий,
  кнопки запуска и остановки.
* **Настройка** — все параметры теста: цель, запрос, сценарий, лимиты
  безопасности, профиль прокси, подтверждение прав и пресеты.
* **Отчёты** — история запусков, подробная сводка, разбор ошибок, экспорт.
* **Прокси** — добавление/импорт/проверка ваших прокси, группировка в профили.
* **Устройства** — распределённое тестирование: координатор, подключённые
  компьютеры, управление флотом.
* **РУКОВОДСТВО** — эта документация.
* **О программе** — версия, данные разработчика, смена языка.

## Мышь

Все кнопки, строки таблиц, переключатели, списки и области прокрутки работают
мышью. В таблицах есть курсор строки: щёлкните строку, затем нажмите кнопку
действия. Графики и журнал прокручиваются колесом.

## Клавиатура

| Клавиша | Действие |
|---------|----------|
| `F1` | открыть РУКОВОДСТВО |
| `F5` | запустить настроенный тест |
| `F6` | остановить тест |
| `Esc` | вернуться на Главную |
| `Tab` / `Shift+Tab` | переход между полями |
| `Enter` | нажать выбранную кнопку |
| стрелки | навигация по спискам и таблицам |

Клавиши не срабатывают, пока вы печатаете в поле ввода.
""",
    ),
    (
        "basics",
        "3 · Основы нагрузочного тестирования",
        """
# Основы нагрузочного тестирования

## Ключевые метрики

| Метрика | Значение |
|---------|----------|
| **Виртуальные пользователи (VU)** | моделируемые клиенты, поочерёдно отправляющие запросы |
| **RPS** | запросов в секунду — пропускная способность теста |
| **Задержка** | время от отправки запроса до получения ответа, в миллисекундах |
| **p50 / p90 / p95 / p99** | значение, ниже которого находится соответствующий процент ответов; p95 — обычный порог «медленно, но приемлемо» |
| **Доступность** | доля успешных ответов от всех попыток |
| **Доля ошибок** | доля неудачных запросов (таймауты, 5xx, ошибки соединения) |

Пример: *p95 = 450 мс* означает, что 95 % ответов пришли быстрее 450 мс —
только самые медленные 5 % дольше.

## Сценарии

| Сценарий | Форма нагрузки | Для чего |
|----------|---------------|----------|
| **Smoke Test** | 1–5 пользователей, ~30 с | проверить URL, метод и настройки |
| **Constant Load** | постоянное число пользователей | базовое поведение при известной нагрузке |
| **Ramp-Up** | линейный рост | найти точку, где начинает расти задержка |
| **Step Load** | четыре ступени | сравнить метрики между уровнями нагрузки |
| **Spike** | резкий всплеск, удержание, спад | проверить автоскейлинг и восстановление |
| **Stress Test** | агрессивный рост до лимита | найти точку отказа |
| **Endurance** | долгая умеренная нагрузка | утечки, исчерпание пулов, медленная деградация |

## Как проходит тест

1. SEAPED проверяет конфигурацию и флаг авторизации.
2. Планировщик запускает виртуальных пользователей по выбранному сценарию.
3. Каждый пользователь отправляет запросы с определённой паузой между ними.
4. Каждый ответ замеряется и записывается (задержка, статус, байты).
5. Раз в секунду пишется образец для графиков в реальном времени.
6. Непрерывно проверяются лимиты безопасности; при срабатывании любого тест
   останавливается автоматически, причина сохраняется в отчёте.
7. По окончании длительности пользователи завершаются, отчёт сохраняется.
""",
    ),
    (
        "configure",
        "4 · Настройка теста",
        """
# Настройка теста

Все параметры находятся в разделе **Настройка**, разделённом на три вкладки.

## Вкладка «Цель»

| Поле | Назначение |
|------|-----------|
| **Название теста** | отображается в истории и отчётах |
| **Адрес цели (URL)** | базовый адрес, `http://` или `https://` (добавляется автоматически) |
| **Метод** | GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS |
| **Путь** | путь/параметры к URL, например `/api/search?q=test` |
| **Ожидаемый статус** | код, считающийся успехом; `0` — любой 2xx/3xx |
| **следовать редиректам** | разрешить переход по 3xx |
| **проверять TLS** | валидация сертификата (выключайте только для тестовых хостов) |

## Вкладка «Нагрузка»

| Поле | Назначение |
|------|-----------|
| **Сценарий** | форма нагрузки (см. раздел 3) |
| **Стартовых** | пользователи в начале разгона |
| **Максимум** | верхняя граница одновременных пользователей |
| **Длительность (с)** | общая продолжительность теста |
| **Разгон (с)** | время роста от стартового до максимального числа |

Справа — график **расписания пользователей**: как именно будет меняться
нагрузка во времени.

## Вкладка «Дополнительно»

**Запрос:** заголовки (по одному «Имя: значение» на строку, строки с `#` —
комментарии), тело запроса для POST/PUT/PATCH, таймаут, пауза между запросами.

**Лимиты безопасности (автостоп):**

| Поле | Назначение |
|------|-----------|
| **Макс. пользователей** | жёсткий потолок, движок никогда не превысит |
| **Макс. длительность (с)** | потолок по времени |
| **Макс. зн/с** | ограничение скорости на стороне клиента |
| **Стоп при ошибках (%)** | остановка при превышении доли ошибок (0 — выкл.) |
| **Стоп при p95 (мс)** | остановка по задержке (0 — выкл.) |
| **Стоп после N неудач** | остановка после серии неудач подряд |
| **Прогрев (с)** | пауза, после которой начинают действовать правила ошибок/задержки |

**Сеть:** выбор профиля прокси (раздел 6) или прямого подключения.

## Подтверждение прав и действия

Нижняя панель раздела всегда содержит:

1. чекбокс **«Я владею этой целью или получил разрешение на тестирование»** —
   обязателен, не сохраняется на диск;
2. кнопки **Проверить** (валидация), **Применить и открыть Главную**,
   **Запустить тест**.

## Пресеты

Во вкладке «Дополнительно» сохраните текущую конфигурацию под именем,
загрузите её позже или удалите. Пресеты хранятся в папке `presets/`.
""",
    ),
    (
        "results",
        "5 · Графики и результаты",
        """
# Графики и результаты

## Как читать живые графики

**График пропускной способности**

* бирюзовая линия — фактические запросы в секунду;
* красная линия — неудачные запросы в секунду;
* если бирюзовая линия выходит на плато, а число пользователей растёт —
  сервер достиг предела;
* если красная линия идёт вверх — что-то начинает ломаться, смотрите журнал.

**График задержки**

* синяя — p50 (типичное время ответа);
* янтарная — p95 (самые медленные 5 %);
* красная — p99 (худшие 1 %);
* резкий подъём всех трёх линий означает насыщение: очереди, CPU или база;
* p95 растёт, а p50 плоский — часть запросов застревает (блокировки, кэш,
  холодные воркеры).

## Как разбирать завершённый тест

Раздел **Отчёты** показывает для каждого запуска:

* запросы, успехи, ошибки и доступность;
* среднюю и пиковую пропускную способность;
* задержки avg / p50 / p90 / p95 / p99 / max;
* разбор ошибок по типам (`timeout`, `http_500`, `conn_refused`, `dns_error`,
  `tls_cert`, `proxy_error`, …);
* распределение по классам HTTP-статусов;
* причину остановки (длительность, лимит пользователей, ошибки, задержка,
  ручная остановка).

## Экспорт

* **Экспорт CSV** — по строке на секунду, удобно для таблиц;
* **Экспорт HTML** — самодостаточный отчёт со встроенным графиком, можно
  отправить коллеге;
* **📁 Папка** — открыть папку `results/` со всеми отчётами.

Отчёты создаются автоматически после каждого завершённого теста.
""",
    ),
    (
        "proxies",
        "6 · Прокси и сетевые профили",
        """
# Прокси и сетевые профили

Раздел **Прокси** управляет серверами, которые добавили *вы*.

## Добавление

Укажите схему, хост, порт и — при необходимости — логин/пароль, дайте метку и
имя профиля, нажмите **＋ Добавить**.

Поддерживаемые схемы: `http`, `https`, `socks5`, `socks4`
(для SOCKS нужен пакет `aiohttp-socks`).

## Импорт списка

Введите путь к файлу и нажмите **⤓ Импорт файла**. Формат — одна запись на
строку:

```
10.0.0.1:8080
socks5://user:pass@10.0.0.2:1080
# комментарии и пустые строки пропускаются
```

## Проверка

**✔ Проверить все** отправляет реальный запрос через каждый включённый прокси и
записывает:

* работает ли он вообще;
* задержку подключения;
* выходной IP-адрес;
* регион/провайдер (если доступен онлайн-lookup);
* время последней проверки.

В тестах используются только прокси в статусе **online**.

## Сетевые профили

*Профиль* — просто имя, которое вы присваиваете прокси (например `europe`,
`backup`, `lab`). В **Настройка → Сеть** выбирается профиль, который должен
использоваться тестом. Если профиль не выбран — подключение прямое.

## Политика

SEAPED не скачивает публичные списки прокси и автоматически не использует
неизвестные серверы. Всё в этом разделе добавлено, проверено и выбрано вами.
""",
    ),
    (
        "distributed",
        "7 · Распределённое тестирование",
        """
# Распределённое тестирование

Позволяет нескольким компьютерам, **которыми владеете вы**, участвовать в одной
тестовой сессии. Раздел необязателен — всё работает и без него.

## Роли

* **Координатор** — работает внутри SEAPED, слушает TCP-порт, ведёт список
  устройств и объединяет их метрики.
* **Агент** — отдельный процесс на рабочей машине; он подключается *наружу* к
  координатору (на рабочей машине не нужно открывать порты).

## Запуск сессии

1. Откройте **Устройства**, нажмите **Создать** — появится токен сессии.
2. Нажмите **▶ Запустить координатор** — статус станет зелёным.
3. Скопируйте отображённую команду и выполните её на каждом своём устройстве:

```
python -m seaped.dist.agent --host <IP-координатора> --port 8765 \
    --token <токен> --consent --max-vus 100 --max-duration 600 --max-rps 2000
```

4. Устройства появятся в таблице с состоянием, лимитами и текущим тестом.
5. Нажмите **▶ Тест на весь флот**, чтобы отправить настроенный тест всем
  подключённым устройствам (флажок *включить этот компьютер* добавит и локальную
  машину).

## Контроль владельцем

| Средство | Эффект |
|----------|--------|
| `--consent` | без него устройство — наблюдатель и отказывается от тестов |
| `--max-vus` | потолок владельца по пользователям — координатор может только уменьшить его |
| `--max-duration` | потолок по длительности |
| `--max-rps` | потолок по скорости запросов |
| **Отключить выбранное** | отключает устройство и блокирует его на 5 минут |
| **Ping всем** | проверка живости всех устройств |
| **Сохранить сводный отчёт** | один общий отчёт на весь флот |

## Безопасность

* аутентификация — HMAC-доказательство по общему токену: сам токен по сети не передаётся;
* каждая сессия договаривается о новом ключе через HKDF, дальше всё
  шифруется и аутентифицируется **AES-256-GCM**;
* счётчики сообщений строго монотонны — защита от повторов;
* устройство выполняет тест только если владелец запустило с `--consent`
  **и** в задании стоит флаг авторизации оператора.

## Масштаб

Координатор комфортно обслуживает несколько десятков устройств. Метрики
агрегируются по секундам, поэтому графики показывают суммарную нагрузку флота.
""",
    ),
    (
        "safety",
        "8 · Безопасное использование",
        """
# Безопасное использование

## Пример 1 — быстрая проверка перед настоящим тестом

```
Сценарий     : Smoke Test
Цель         : https://staging.example.com
Макс. VU     : 5
Длительность : 30 с
Стоп по ошиб.: 10 %
```

Задача: убедиться, что URL, метод, заголовки и профиль прокси корректны.

## Пример 2 — поиск ёмкости сервиса

```
Сценарий     : Ramp-Up
Старт / макс : 10 → 400 пользователей
Длительность : 10 мин
Стоп по p95  : 3000 мс
Стоп по ошиб.: 5 %
Прогрев      : 15 с
```

Смотрите, где ломается линия p95 — это ваша практическая ёмкость.

## Пример 3 — всплеск трафика (прод, в низкое окно)

```
Сценарий     : Spike
Макс. VU     : 200
Длительность : 3 мин
Стоп по ошиб.: 10 %
```

Наблюдайте, за сколько секунд задержка возвращается к норме.

## Пример 4 — длительный тест на выносливость (стейджинг)

```
Сценарий     : Endurance
Макс. VU     : 80
Длительность : 2 ч
Стоп по p95  : 5000 мс
```

Сравните первую и вторую половины запуска: растущая задержка при одной и той же
нагрузке обычно означает утечку.

## Чек-лист перед нажатием «Запустить»

1. Вы владеете целью или имеете письменное разрешение.
2. По возможности тест идёт на staging/предпрод.
3. Заданы лимиты безопасности (пользователи, время, ошибки, задержка).
4. Прогрев покрывает первые секунды разгона.
5. Команда знает, что идёт тест.
6. На проде — в низкое окно нагрузки и с готовым планом отката.

## Чего делать не нужно

* не тестируйте чужие системы;
* не выключайте лимиты безопасности «просто посмотреть»;
* не запускайте тесты на проде без плана отката;
* не публикуйте токен сессии.
""",
    ),
    (
        "troubleshooting",
        "9 · Ошибки и решения",
        """
# Ошибки и решения

## Типы ошибок в отчётах

| Тип | Значение | Что проверить |
|-----|---------|---------------|
| `timeout` | нет ответа за таймаут | нагрузка на сервер, значение таймаута, сеть |
| `conn_refused` | хост отклонил соединение | запущена ли служба, верный порт |
| `dns_error` | не разрешилось имя хоста | адрес, DNS-настройки |
| `tls_cert` / `tls_error` | проблема серфиката/рукопожатия | срок действия сертификата, переключатель «проверять TLS» |
| `conn_error` | другая ошибка соединения | фаервол, прокси, VPN |
| `proxy_error` | выбранный прокси нерабочий | запустите «Проверить все» в разделе Прокси |
| `http_4xx` / `http_5xx` | сервер ответил ошибкой | логи приложения, поле ожидаемого статуса |
| `too_many_redirects` | петля редиректов | выключите «следовать редиректам» |
| `client_error` | другая ошибка клиента | журнал событий |

## Частые ситуации

**«Укажите адрес цели»** — заполните поле цели в Настройке.

**«Тест не авторизован»** — отметьте чекбокс подтверждения прав.

**«В профиле нет работающих прокси»** — запустите «Проверить все», добавьте
недостающие серверы или выберите прямое подключение.

**Тест останавливается сразу с «Достигнут лимит ошибок»** — цель не отвечает;
посмотрите журнал событий или увеличьте прогрев.

**Графики пустые** — тест ещё не проработал секунду; подождите или проверьте
журнал на ошибки.

**Координатор не стартует** — порт занят; выберите другой порт или остановите
предыдущий координатор.

**Устройство не появляется** — проверьте хост/порт/токен, запущен ли процесс
агента и разрешён ли исходящий TCP на координатор.
""",
    ),
    (
        "developer",
        "10 · Разработчик",
        """
# Разработчик

**Проект:** SEAPED — Professional Load Testing Suite

**Разработчик:** @uf0rs

**Telegram-канал:** @HSIIHprime

**Версия:** 2.0.0

## Структура проекта

```
SEAPED/
├── seaped/              пакет приложения
│   ├── core/            движок, метрики, сценарии, лимиты, отчёты
│   ├── net/             прокси и сетевые профили
│   ├── dist/            координатор, агент, шифропротокол
│   └── ui/              интерфейс: разделы, виджеты, тема, локализация
├── tests/               unit- и integration-тесты
├── presets/             сохранённые конфигурации
├── results/             отчёты (JSON / CSV / HTML)
└── seaped.exe           собранное приложение (после build_exe.py)
```

## Сборка исполняемого файла

```
python build_exe.py
```

PyInstaller создаёт `dist\\SEAPED.exe` — автономную сборку, для которой не
нужно устанавливать Python.

## Расширение SEAPED

* новый сценарий → функция планировщика и запись `Scenario` в
  `seaped/core/scenarios.py`;
* новый показатель → `MetricsCollector` и плитки на Главной;
* новый раздел → класс `Section` в `seaped/ui/screens/`, регистрация в
  `seaped/ui/screens/__init__.py` и в боковой панели `seaped/ui/app.py`;
* новый язык → таблица в `seaped/i18n.py` и главы в
  `seaped/ui/manual_content.py`.
""",
    ),
]


def chapters(lang: str | None = None) -> List[Tuple[str, str, str]]:
    """Manual chapters for the given (or current) language."""
    from ..i18n import get_language

    language = lang or get_language()
    return CHAPTERS_RU if language == "ru" else CHAPTERS_EN


def chapter_map(lang: str | None = None) -> Dict[str, Tuple[str, str]]:
    return {cid: (title, body) for cid, title, body in chapters(lang)}
