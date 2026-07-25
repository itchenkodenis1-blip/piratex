# Piratex.ai — Playbook масштабирования

## Текущая конфигурация (22 марта 2026)

| Компонент | Значение |
|-----------|----------|
| web | 1 реплика, 4 uvicorn workers, 32 GB RAM |
| worker | 3 реплики, 8 jobs каждая = 24 параллельных анализа |
| scheduler | 1 реплика |
| PostgreSQL max_connections | 600 |
| DB pool (web) | pool=10, overflow=20 |
| DB pool (worker) | pool=8, overflow=15 |
| DB pool (scheduler) | pool=5, overflow=8 |

---

## Уровень 1: до 500 пользователей (ТЕКУЩИЙ)

Всё уже настроено. Ничего делать не нужно.

---

## Уровень 2: 500–1000 пользователей

### Сигналы что пора:
- Telegram алерт "Queue overloaded" (очередь > 50 джобов)
- Пользователи ждут анализ дольше 5-7 минут
- В логах ошибки "connection pool exhausted"

### Что делать:
Открыть Claude Code и написать:
```
масштабируй воркеры до 6 реплик
```

Или вручную в терминале:
```bash
railway scale -s worker 6
```

Время: 2 минуты. Стоимость: +3 контейнера на Railway.

---

## Уровень 3: 1000–3000 пользователей

### Сигналы что пора:
- Алерты продолжаются даже с 6 воркерами
- Сайт медленно отвечает (API > 2 секунды)
- Railway Dashboard показывает высокую CPU на web

### Что делать:

**Шаг 1 — больше воркеров:**
```bash
railway scale -s worker 10
```

**Шаг 2 — добавить реплики web:**
```bash
railway scale -s web 3
```

**Шаг 3 — увеличить DB pool на web:**
```bash
railway variable set DB_POOL_SIZE=15 DB_MAX_OVERFLOW=30 -s web
railway redeploy -s web --yes
```

Время: 5 минут.

---

## Уровень 4: 3000–5000 пользователей

### Сигналы что пора:
- PostgreSQL CPU > 80%
- Ошибки "too many connections" в логах
- Воркеры перезапускаются (OOM)

### Что делать:

**Шаг 1 — PostgreSQL max_connections:**
Railway Dashboard → PostgreSQL → Settings → Deploy → Custom Start Command:
```
docker-entrypoint.sh postgres -c max_connections=1000
```
Нажать Deploy.

**Шаг 2 — воркеры и web:**
```bash
railway scale -s worker 15
railway scale -s web 4
```

**Шаг 3 — рассмотреть PgBouncer:**
На этом уровне лучше добавить PgBouncer (connection pooler) как отдельный сервис в Railway, чтобы мультиплексировать коннекты. Попросить Claude Code настроить.

---

## Уровень 5: 5000+ пользователей

### Что делать:
- Включить Railway Autoscaling (Dashboard → Service → Settings → Scaling)
- Добавить PgBouncer (обязательно)
- Рассмотреть Read Replica для PostgreSQL (разделить чтение/запись)
- Рассмотреть CDN для статики

На этом уровне написать в Claude Code: "нужно масштабировать на 5000+ пользователей" — и получить детальный план.

---

## Быстрая справка: команды

```bash
# Посмотреть текущее состояние
railway service status -s web
railway service status -s worker

# Масштабировать воркеры (N = нужное количество реплик)
railway scale -s worker N

# Масштабировать web
railway scale -s web N

# Изменить переменные (каждый set триггерит редеплой)
railway variable set KEY=VALUE -s SERVICE_NAME

# Редеплой
railway redeploy -s SERVICE_NAME --yes
```

## Важно помнить
- Единственное что стоит денег — это реплики (контейнеры 24/7)
- max_connections, pool size, переменные — бесплатно
- После масштабирования можно уменьшить обратно когда нагрузка спадёт
- Scheduler ВСЕГДА 1 реплика — не масштабировать!
