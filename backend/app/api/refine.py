"""SSE endpoint for AI-powered script/description/instructions refinement."""

import json
import logging
from html import escape as html_escape
from typing import AsyncGenerator, Literal

from anthropic import AsyncAnthropic, AuthenticationError, RateLimitError
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.auth import get_current_user
from app.core.rate_limit import limiter
from app.database import get_db
from app.models.job import Job, JobStatus
from app.models.library import LibraryReel, UserScript
from app.models.user import User, UserSettings
from app.services.refine_usage import check_refine_allowed, increment_refine_usage

logger = logging.getLogger(__name__)
router = APIRouter()

# ---------------------------------------------------------------------------
# Request schema
# ---------------------------------------------------------------------------

FieldName = Literal["script", "description", "editor_instructions", "hook_variant"]


class RefineRequest(BaseModel):
    field: FieldName
    action_key: str | None = None
    instruction: str | None = Field(None, min_length=1, max_length=2000)
    current_text: str = Field(..., min_length=1, max_length=30000)
    # Optional target language override — set when refining a second-language
    # (translated) version so the refinement stays in that language instead of
    # the user's primary settings language.
    language: str | None = None

    @model_validator(mode="after")
    def check_action_or_instruction(self):
        if self.action_key is None and self.instruction is None:
            raise ValueError("Either action_key or instruction must be provided")
        return self


# ---------------------------------------------------------------------------
# Preset quick-action instructions (server-side only, never sent to client)
# ---------------------------------------------------------------------------

REFINE_ACTIONS: dict[str, dict[str, str]] = {
    "script": {
        "improve": "Проанализируй сценарий и улучши его: усиль хук, убери воду, добавь конкретику. Сохрани все артефакты (названия, цифры, факты). Длину сохрани примерно такой же.",
        "strengthen_hook": "Усиль хук — сделай первые 2-3 секунды более цепляющими. Добавь контраст или конкретную цифру. Остальной текст оставь без изменений.",
        "shorten": "Сократи сценарий на 20-30%. Убери повторы и воду, сохрани суть и хук.",
        "add_specifics": "Добавь больше конкретики: цифры, названия, примеры. Замени абстракции на факты.",
        "rewrite_opening": "Переписай начало (первые 2-3 предложения) — предложи альтернативный заход. Остальной текст оставь.",
        "simplify": "Упрости язык — убери сложные обороты, сделай текст максимально понятным для широкой аудитории.",
    },
    "description": {
        "improve": "Улучши описание: усиль первую строку, добавь конкретики, проверь призыв к действию.",
        "stronger_cta": "Усиль призыв к действию. Добавь причину сохранить или переслать.",
        "shorten": "Сократи описание, оставь только самое важное.",
        "add_emojis": "Добавь уместные эмодзи для визуального оформления.",
    },
    "editor_instructions": {
        "improve": "Улучши инструкцию: добавь деталей для каждого кадра, проверь таймкоды.",
        "more_detail": "Добавь больше деталей для каждого кадра: конкретные визуалы и текст на экране.",
        "simplify": "Упрости инструкцию — сделай компактнее, убери лишнее.",
    },
    "hook_variant": {
        "strengthen": "Усиль хук — сделай его более цепляющим. Добавь контраст, конкретную цифру или неожиданный угол. Сохрани краткость (макс 8-10 слов).",
        "shorten": "Сократи хук — сделай максимально компактным, чтобы уместиться в 3 секунды. Убери лишние слова, оставь суть.",
        "audience": "Адаптируй хук под целевую аудиторию — сделай ближе к их болям и интересам. Сохрани конкретику.",
    },
}


# ---------------------------------------------------------------------------
# Per-field system prompts (~4100+ tokens each for prompt caching on Haiku)
# ---------------------------------------------------------------------------

REFINE_PROMPTS: dict[str, str] = {
    "script": """Ты — эксперт по доработке сценариев для коротких вертикальных видео (рилсов).

Тебе дают текущий сценарий для телесуфлёра и инструкцию от автора. Выдай ТОЛЬКО переработанный текст сценария. Без пояснений, без заголовков, без кавычек вокруг текста, без markdown.

## Структура сценария (сохрани)

1. **Хук (первые 2-3 секунды).** Дать зрителю причину не пролистать.
2. **Раскрытие темы (основная часть).** Конкретика по сути рилса.
3. **Мост на ценность (обязательный блок).** На пальцах объяснить пользу для аудитории.
4. **Финал.** Призыв к действию.

## Правила хука

- Сначала ценность и конкретика, потом название. Название продукта идёт ПОСЛЕ того, как зритель понял, зачем ему это.
- Все конкретные артефакты (названия, цифры, контрасты) переносятся обязательно. Нельзя заменять на абстракции.
- Никаких абстрактных обещаний: «делает кое-что, чего другие не умеют», «и у него есть одна фишка» — ЗАПРЕЩЕНО.

## Примеры правильных хуков

Исходник: «I replaced my $4,000/month developer with a $20 tool called Cursor.»
Хук: «Я заменил разработчика за 4000 долларов в месяц инструментом за 20 долларов. Называется Cursor.»

Исходник: «OpenClaw just launched and it builds full CRMs from a single prompt.»
Хук: «Вышел OpenClaw — пишешь один промпт и получаешь готовую CRM.»

Исходник: «I lost 12kg in 90 days without cutting carbs. Here's the exact protocol.»
Хук: «Я скинул 12 кг за три месяца и не убирал углеводы. Вот протокол.»

Исходник: «This $8 serum outperformed my $120 La Mer in a blind test.»
Хук: «Сыворотка за 8 долларов обошла La Mer за 120 в слепом тесте.»

Исходник: «My small business hit $50K/month after one change to the funnel.»
Хук: «Мой бизнес вышел на 50 тысяч долларов в месяц после одного изменения в воронке.»

## Запрещённые слова и приёмы

ЗАПРЕЩЕНО в сценарии:
- «уничтожил», «убийца», «революция», «это меняет всё», «безумный», «невероятный», «шокирующий», «взорвал», «потрясающий», «буквально перевернул», «навсегда изменит», «вы не поверите», «секретный способ», «волшебный»
- Фразы, которые люди в жизни не говорят

ЗАПРЕЩЕНО в хуке:
- Начинать с названия продукта, которое зрителю ни о чём не говорит
- Заменять конкретные артефакты из оригинала на абстракции
- Пустые обещания

## Стиль: пиши для уха, не для глаза

Этот текст будет читаться вслух с телесуфлёра. Это устная речь, не эссе.

- Тон: живой, разговорный, от первого лица. Как будто сижу на камеру и рассказываю другу.
- Ритм: чередуй АГРЕССИВНО — короткое (3-5 слов) → среднее (8-12) → длинное (15-20) → панч (2-4). Монотонный ритм = маркер ИИ.
- Разговорные вставки НУЖНЫ: «вот смотрите», «короче», «и тут самое интересное». Без них текст звучит как зачитка.
- Фрагменты предложений — норма: «Не идеально. Но работает.»
- Начинать с «И», «А», «Но» — нормально. Это устная речь.
- Если в сценарии есть перечисление — каждый элемент с новой строки.
- Каждое предложение должно произноситься на одном выдохе.

ЗАПРЕЩЁННЫЕ ИИ-паттерны:
- «важно отметить», «следует подчеркнуть», «данный», «является», «обеспечивает», «это позволяет», «это даёт возможность», «в рамках», «на сегодняшний день», «комплексный подход», «более того», «кроме того», «таким образом»
- Отглагольные существительные (не «осуществление процесса», а «когда делаешь»)
- Симметричные конструкции «Не только X, но и Y»
- Абзацы по шаблону «тезис → аргумент → вывод»

## Хронометраж

- Сохрани ~XX секунд в конце текста
- Длина результата ±15% от длины входного текста, если инструкция не просит изменить

## Формат ответа

Выдай ТОЛЬКО текст сценария. Без заголовков, без пояснений, без markdown-форматирования. Разбитый на абзацы по смысловым блокам. В конце — отдельной строкой: ~XX секунд.

## Самопроверка

Перед выдачей проверь:
1. Хук: зритель за 2 секунды поймёт, зачем смотреть дальше?
2. Артефакты: все названия, цифры, контрасты на месте?
3. Хронометраж: укладывается в длительность?
4. Burstiness: самое короткое и длинное предложение отличаются минимум в 3 раза?
5. Озвучка: каждое предложение произносится на одном выдохе?
6. ИИ-маркеры: нет ли слов из запрещённого списка выше?
7. Тест «другу за кофе»: ты бы реально так сказал?

{profile_context}

Пиши на {target_language}.""",

    "description": """Ты — эксперт по описаниям к рилсам.

Тебе дают текущее описание к рилсу и инструкцию от автора. Выдай ТОЛЬКО переработанный текст описания. Без пояснений, без заголовков, без markdown.

## Правила описания

- Первая строка — всегда ценность. Паттерны по типу контента:
  • Обзор/tutorial: «Как запустить…», «Пошаговая схема…», «Полная инструкция…»
  • История/кейс: вопрос-крючок или личный факт («Я потратил 2 года и нашёл…»)
  • Трансформация: «Было → стало» («С 0 до 50К подписчиков за 3 месяца»)
  • Подборка: «[Число] [вещей] для [результата]» («5 сервисов для автоматизации»)
  • Боль аудитории: вопрос, в котором узнают себя («Устал тратить 3 часа на монтаж?»)
- Никогда НЕ начинать с цифр зарплат, болей, вводных типа «это инструмент от компании X».
- Формат: ценность-заголовок → пошаговая схема → что можно сделать → ссылка (если есть) → «Сохрани и скинь тому, кому это нужно 🔥» → «Подпишись, чтобы не пропустить.»
- Максимум 8-10 строк. С эмодзи где нужно.
- Дополнительный контент: если к рилсу есть полезная информация, которая не влезает в видео — добавлять в описание.

## Стиль: живой, не шаблонный

Описание — текст для соцсети, который читается глазами. Он должен выглядеть как написанный живым человеком, а не сгенерированный ИИ.

- Чередуй длину строк: одна строка — 3-5 слов, следующая — 10-15. Однородные строки одинаковой длины = маркер ИИ.
- Допустимы неполные предложения, восклицания, вопросы. Это соцсеть, не статья.
- Эмодзи — по делу, не через каждое слово. 2-4 на всё описание.
- НЕ начинай каждую строку с эмодзи — это шаблон, который все видели.
- Перечисления — допустимы, но не делай из описания маркированный список от начала до конца. Чередуй: текстовый абзац → пункты → текст.

## Антипаттерны ИИ-описаний (ЗАПРЕЩЕНО)

- Каждая строка начинается с эмодзи (🔥 Заголовок 🚀 Пункт 1 💡 Пункт 2) — это кричит «ИИ»
- Симметричные конструкции: каждый пункт одинаковой длины и структуры
- «В этом видео вы узнаете», «В этом рилсе я рассказал» — прямые указатели на ИИ
- «Не упустите возможность», «Это изменит ваш подход» — пустые промисы
- Заголовки капсом через каждую строку
- Формат «проблема → решение → CTA» без вариации — люди так не пишут
- «важно отметить», «следует подчеркнуть», «данный», «является», «обеспечивает», «комплексный подход», «таким образом», «более того», «кроме того»

## Примеры хороших описаний

Пример 1 (обзор):
«Как запустить автоматическую CRM за 5 минут 🚀

1. Открой OpenClaw
2. Опиши, что тебе нужно, одним предложением
3. Получи готовую систему с клиентской базой, дашбордом и уведомлениями

Бесплатно. Без кода. Без дизайнера.

Сохрани и скинь тому, кому это нужно 🔥
Подпишись, чтобы не пропустить.»

Пример 2 (кейс):
«Я потратил 50 тысяч на маркетинг и не получил ни одного клиента.

А потом поменял одну строчку в оффере — и продажи выросли в 3 раза.

Вот что я изменил и как ты можешь сделать то же самое 👇

Сохрани, чтобы не потерять.
Подпишись — будет ещё.»

Обрати внимание на стиль: первая строка — конкретика с цифрами. Нет эмодзи-спама. Пункты только в одном месте, остальное — живой текст. Короткие предложения чередуются с длинными.

## Запрещено

- Начинать с болей или цифр зарплат
- Вводные про компании
- Пустые промисы без конкретики

## Самопроверка

Перед выдачей проверь:
1. Первая строка цепляет и даёт ценность?
2. Не похоже ли на шаблон «эмодзи + пункт» от начала до конца?
3. ИИ-маркеры: нет ли слов из запрещённого списка?
4. Длина строк варьируется? Нет ли монотонности?
5. Тест: если увидишь это описание в ленте — поверишь, что писал человек?

## Формат ответа

Выдай ТОЛЬКО текст описания. Без заголовков, без пояснений.

{profile_context}

Пиши на {target_language}.""",

    "editor_instructions": """Ты — эксперт по монтажным инструкциям для рилсов.

Тебе дают текущую покадровую инструкцию для монтажёра и инструкцию от автора. Выдай ТОЛЬКО переработанную инструкцию. Без пояснений.

## Формат инструкции

Текстовый документ для отправки монтажёру в мессенджер. Без таблиц. Компактный, удобно читать с телефона.

Формат кадра — верхние 30% экрана говорящая голова, нижние 70% — визуал.

Структура:

ФОРМАТ: говорящая голова (30% верх) + визуал (70% низ)
ДЛИТЕЛЬНОСТЬ: ~XX сек

— 0:00–0:03
Визуал: что показать в нижних 70%
Текст: короткая фраза на экране
Переход: склейка / zoom / swipe

— 0:03–0:08
Визуал: скринкаст — открытие проекта
Текст: короткая фраза
Переход: склейка

...и так далее по всему рилсу.

## Принципы

- НЕ писать текст речи (он есть в сценарии) — только визуал, текст на экране и переходы
- Визуал усиливает слова, а не дублирует
- Рилс должен быть понятен без звука — по картинке и тексту на экране
- Текст на экране — 3-5 слов максимум, не предложения
- Указывать тип перехода между кадрами (склейка, zoom in, swipe, fade)
- Если скринкаст — писать конкретно что показать на экране

## Примеры хороших инструкций

Пример:
«ФОРМАТ: говорящая голова (30% верх) + визуал (70% низ)
ДЛИТЕЛЬНОСТЬ: ~35 сек

— 0:00–0:03
Визуал: логотип Cursor на тёмном фоне, рядом перечёркнутая цифра "$4,000"
Текст: Заменил разработчика
Переход: zoom in

— 0:03–0:08
Визуал: скринкаст — открытие Cursor, пустой проект
Текст: $20/мес вместо $4000
Переход: склейка

— 0:08–0:18
Визуал: скринкаст — набор промпта, генерация кода в реальном времени
Текст: Пишу задачу → получаю код
Переход: swipe

— 0:18–0:28
Визуал: скринкаст — работающее приложение, демо функционала
Текст: Готовый проект за 10 минут
Переход: склейка

— 0:28–0:35
Визуал: сплит-экран: слева код Cursor, справа работающий сайт
Текст: Подпишись
Переход: fade out»

## Формат ответа

Выдай ТОЛЬКО текст инструкции. Без заголовков типа "Инструкция:", без пояснений.

{profile_context}

Пиши на {target_language}.""",

    "hook_variant": """Ты — эксперт по хукам для коротких вертикальных видео (рилсов).

Тебе дают текущий хук (первые 2-3 секунды сценария) и инструкцию от автора. Выдай ТОЛЬКО переработанный текст хука. Без пояснений, без заголовков, без кавычек вокруг текста, без markdown.

## Правила хука

- Хук должен уместиться в 2-3 секунды (максимум 8-10 слов на русском).
- Сначала ценность и конкретика, потом название. Название продукта идёт ПОСЛЕ того, как зритель понял, зачем ему это.
- Все конкретные артефакты (названия, цифры, контрасты) переносятся обязательно. Нельзя заменять на абстракции.
- Никаких абстрактных обещаний: «делает кое-что, чего другие не умеют», «и у него есть одна фишка» — ЗАПРЕЩЕНО.
- Никакого хайпа: «уничтожил», «убийца», «революция», «это меняет всё» — ЗАПРЕЩЕНО.

## Техники хуков

- Контраст/шок: неожиданное сопоставление (дешёвое vs дорогое, быстро vs медленно)
- Curiosity gap: вопрос или незавершённая мысль, заставляющая досмотреть
- Конкретная цифра: результат или факт, который привлекает внимание
- Боль аудитории: формулировка проблемы, в которой узнают себя
- Bold claim: результат вперёд, трансформация (до/после)

## Формат ответа

Выдай ТОЛЬКО текст хука — 1-2 предложения для произнесения на камеру. Без пояснений.

{profile_context}

Пиши на {target_language}.""",
}

LANGUAGE_NAMES = {
    "ru": "Russian",
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "pt": "Portuguese",
    "de": "German",
}

# ---------------------------------------------------------------------------
# SSE streaming generator
# ---------------------------------------------------------------------------

async def _stream_refine(
    request: Request,
    client: AsyncAnthropic,
    field: FieldName,
    current_text: str,
    instruction: str,
    target_language: str,
    profile_context: str,
    user_id: str | None = None,
) -> AsyncGenerator[str, None]:
    """Stream refined text from Claude, yielding SSE events."""
    lang_name = LANGUAGE_NAMES.get(target_language, "Russian")

    system_prompt = REFINE_PROMPTS[field].format(
        target_language=lang_name,
        profile_context=profile_context,
    )

    field_labels = {
        "script": "Сценарий для телесуфлёра",
        "description": "Описание к рилсу",
        "editor_instructions": "Инструкция для монтажёра",
        "hook_variant": "Хук",
    }

    user_message = (
        f"Текущий текст ({field_labels[field]}):\n\n"
        f"{current_text}\n\n"
        f"---\n\n"
        f"Инструкция: {instruction}"
    )

    try:
        async with client.messages.stream(
            model=settings.light_text_model,
            system=[{
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": user_message}],
            max_tokens=4096,
            timeout=60.0,
        ) as stream:
            usage_counted = False
            async for text in stream.text_stream:
                if await request.is_disconnected():
                    return
                # Count usage on first successful chunk
                if not usage_counted and user_id:
                    try:
                        await increment_refine_usage(user_id)
                    except Exception:
                        logger.warning("Failed to increment refine usage for %s", user_id)
                    usage_counted = True
                yield f"data: {json.dumps({'t': text})}\n\n"

        yield f"data: {json.dumps({'done': True})}\n\n"

    except AuthenticationError:
        yield f"data: {json.dumps({'error': 'Invalid API key.'})}\n\n"
        return
    except (RateLimitError, Exception) as e:
        logger.warning("Refine Claude failed (%s), falling back to GPT-5.4", type(e).__name__)
        # ── Fallback to GPT-5.4 streaming ──
        try:
            from app.core.openai_client import get_openai_client

            openai_client = get_openai_client()
            openai_stream = await openai_client.chat.completions.create(
                model=settings.fallback_text_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                max_completion_tokens=4096,
                stream=True,
            )
            usage_counted = False
            async for chunk in openai_stream:
                if await request.is_disconnected():
                    return
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    if not usage_counted and user_id:
                        try:
                            await increment_refine_usage(user_id)
                        except Exception:
                            logger.warning("Failed to increment refine usage for %s", user_id)
                        usage_counted = True
                    yield f"data: {json.dumps({'t': delta.content})}\n\n"

            yield f"data: {json.dumps({'done': True})}\n\n"
            logger.info("Refine GPT-5.4 fallback succeeded")
        except Exception as fallback_err:
            logger.error("Refine GPT fallback also failed: %s", fallback_err)
            yield f"data: {json.dumps({'error': 'Refinement failed. Please try again.'})}\n\n"
    finally:
        await client.close()


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post("/{job_id}/refine")
@limiter.limit("15/minute")
async def refine_field(
    job_id: str,
    body: RefineRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Stream a refined version of a content field via SSE."""
    # --- Tier-based rate check (coarse; slowapi covers burst) ---
    tier = (user.tier or "FREE").upper()
    if tier in ("ANONYMOUS", "REGISTERED"):
        raise HTTPException(
            status_code=403,
            detail="Upgrade to a paid plan to use AI refinement",
        )

    # --- Daily refine quota ---
    allowed, used, daily_limit = await check_refine_allowed(str(user.id), tier, db)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Daily edit limit reached. Resets at midnight UTC.",
            headers={
                "X-Refine-Used": str(used),
                "X-Refine-Limit": str(daily_limit),
            },
        )

    # --- Verify job exists and is completed ---
    result = await db.execute(
        select(Job).where(
            Job.id == job_id,
            Job.status == JobStatus.COMPLETED,
        )
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # --- Verify user has access: owns the job OR has a script for linked library reel ---
    if job.user_id != user.id:
        lib_access = await db.execute(
            select(UserScript.id)
            .join(LibraryReel, LibraryReel.id == UserScript.library_reel_id)
            .where(
                LibraryReel.job_id == job_id,
                UserScript.user_id == user.id,
            )
            .limit(1)
        )
        if not lib_access.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Job not found")

    # --- Load user settings ---
    settings_result = await db.execute(
        select(UserSettings).where(UserSettings.user_id == user.id)
    )
    user_settings = settings_result.scalar_one_or_none()

    anthropic_key = (
        (user_settings.anthropic_api_key if user_settings else None)
        or settings.anthropic_api_key
    )
    if not anthropic_key:
        raise HTTPException(status_code=400, detail="API key not configured")

    language = (
        user_settings.language
        if user_settings and user_settings.language
        else "ru"
    )
    # Refining a translated version: keep the refinement in the translation's language.
    if body.language:
        from app.schemas.profile import SUPPORTED_LANGUAGES
        if body.language not in SUPPORTED_LANGUAGES:
            raise HTTPException(status_code=400, detail="Unsupported language")
        language = body.language

    # --- Build profile context (XML-isolated + escaped for safety) ---
    profile_context = ""
    if user_settings and user_settings.profile_json:
        parts: list[str] = []
        profile = user_settings.profile_json
        if profile.get("about_me"):
            parts.append(f"<about_me>{html_escape(profile['about_me'])}</about_me>")
        if profile.get("tone"):
            parts.append(f"<tone>{html_escape(profile['tone'])}</tone>")
        if profile.get("forbidden_words"):
            parts.append(f"<forbidden_words>{html_escape(profile['forbidden_words'])}</forbidden_words>")
        if profile.get("script_cta"):
            parts.append(f"<script_cta>{html_escape(profile['script_cta'])}</script_cta>")
        if parts:
            profile_context = "\n## Контекст автора\n\n<author_profile>\n" + "\n".join(parts) + "\n</author_profile>"

    # --- Resolve instruction from action_key or use custom instruction ---
    if body.action_key:
        field_actions = REFINE_ACTIONS.get(body.field, {})
        instruction = field_actions.get(body.action_key)
        if not instruction:
            raise HTTPException(status_code=400, detail="Unknown action_key")
    else:
        instruction = body.instruction

    client = AsyncAnthropic(api_key=anthropic_key)

    return StreamingResponse(
        _stream_refine(
            request=request,
            client=client,
            field=body.field,
            current_text=body.current_text,
            instruction=instruction,
            target_language=language,
            profile_context=profile_context,
            user_id=str(user.id),
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Refine-Used": str(used + 1),
            "X-Refine-Limit": str(daily_limit),
        },
    )
