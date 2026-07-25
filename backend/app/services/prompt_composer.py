"""Compose personalized prompts from structured user profile fields.

The templates below are the DEFAULT prompts with personal sections
replaced by {placeholders}. When profile is None or a field is None,
the corresponding default value is used — producing output functionally
equivalent to the original hardcoded DEFAULT_*_PROMPT.
"""

from __future__ import annotations

from app.schemas.profile import UserProfile


# ---------------------------------------------------------------------------
# Tone presets
# ---------------------------------------------------------------------------
TONE_PRESETS: dict[str, str] = {
    "conversational": (
        "lively, conversational, first person. As if sitting on camera telling "
        "a friend through personal experience. No corporate speak, no pomposity. "
        "Words people understand. Don't compress excessively — the text must "
        "sound natural when read from a teleprompter."
    ),
    "expert": (
        "confident, expert-level. Speaking as a practitioner who knows their "
        "craft. Not overly casual, but not academic either. Facts, numbers, specifics. "
        "The text should sound authoritative yet accessible when spoken aloud."
    ),
    "energetic": (
        "energetic, dynamic, with a touch of humor. Short phrases, rhythmic "
        "delivery, vivid comparisons. Drive without hype. As if telling a story "
        "at a party, energizing the audience."
    ),
    "calm": (
        "calm, thoughtful. No rush, with pauses. As if explaining "
        "over a cup of coffee. Depth matters more than speed. The text must sound "
        "natural and measured when read aloud."
    ),
}

# ---------------------------------------------------------------------------
# Language-specific AI marker words to ban
# ---------------------------------------------------------------------------
AI_MARKER_WORDS: dict[str, str] = {
    "ru": (
        "важно отметить, следует подчеркнуть, данный, является, обеспечивает, "
        "в рамках, на сегодняшний день, в современном мире, в контексте, "
        "это позволяет, это даёт возможность, комплексный подход, "
        "инновационный, ключевой аспект, уникальный, "
        "осуществление, использование (как существительное), обеспечение, "
        "более того, кроме того, помимо этого, таким образом, "
        "необходимо учитывать, в заключение хотелось бы, "
        "стоит отметить, нельзя не упомянуть"
    ),
    "en": (
        "delve, tapestry, realm, landscape, beacon, cacophony, symphony, "
        "harness, leverage, navigate, unlock, unleash, embark, "
        "meticulous, seamless, robust, holistic, pivotal, vibrant, "
        "foster, underscore, showcase, bolster, garner, "
        "moreover, furthermore, additionally, it's important to note, "
        "in today's world, in an era of, let's dive in, "
        "testament, commendable, unparalleled, transformative, pioneering, "
        "not just X but also Y, whether you're X or Y"
    ),
    "es": (
        "es importante destacar, cabe señalar, en el mundo actual, "
        "además, por otro lado, asimismo, en este sentido, "
        "permite, posibilita, facilita, garantiza, "
        "innovador, excepcional, notable, incomparable, "
        "sin lugar a dudas, en conclusión, por consiguiente"
    ),
    "fr": (
        "il est important de noter, il convient de souligner, "
        "dans le monde actuel, en effet, par ailleurs, "
        "permet de, offre la possibilité, met en lumière, "
        "incontournable, novateur, remarquable, exceptionnel"
    ),
    "pt": (
        "é importante destacar, vale ressaltar, no mundo atual, "
        "além disso, dessa forma, proporciona, viabiliza, "
        "inovador, excepcional, notável, incomparável"
    ),
    "de": (
        "es ist wichtig zu beachten, hervorzuheben ist, "
        "in der heutigen Welt, darüber hinaus, des Weiteren, "
        "ermöglicht, gewährleistet, innovativ, einzigartig, bemerkenswert"
    ),
}

# ---------------------------------------------------------------------------
# Language-specific speech markers (colloquialisms for natural scripts)
# ---------------------------------------------------------------------------
SPEECH_MARKERS: dict[str, str] = {
    "ru": (
        "Разговорные вставки естественны и НУЖНЫ: «вот смотрите», «короче», "
        "«и тут самое интересное», «знаете что», «ну вот». Без них текст звучит как зачитка.\n"
        "- Допустимы фрагменты предложений: «Не идеально. Но работает.» — это нормально для устной речи.\n"
        "- Допустимы самокоррекции: «Их там три... нет, скорее четыре момента.» — маркер живого рассказа.\n"
        "- Начинать предложения с «И», «А», «Но», «Ну» — нормально. Это устная речь."
    ),
    "en": (
        "Colloquial inserts are natural and NEEDED: 'look', 'here's the thing', "
        "'honestly', 'basically', 'right?', 'I mean'. Without them the script sounds like a press release.\n"
        "- Sentence fragments are fine: 'Not perfect. But it works.' — that's how people talk.\n"
        "- Self-corrections are fine: 'There are three... no, actually four things.' — marker of real speech.\n"
        "- Starting with 'And', 'But', 'So', 'Now' is normal. Always use contractions: don't, it's, we're, that's."
    ),
    "es": (
        "Inserciones coloquiales son naturales y NECESARIAS: 'mira', 'o sea', "
        "'la verdad es que', 'bueno', 'a ver'. Sin ellas el texto suena a lectura.\n"
        "- Fragmentos de oraciones están bien: 'No es perfecto. Pero funciona.'\n"
        "- Autocorrecciones están bien: 'Son tres... no, en realidad cuatro cosas.'\n"
        "- Empezar con 'Y', 'Pero', 'Bueno', 'Pues' es normal. Es habla oral."
    ),
    "fr": (
        "Les insertions familières sont naturelles et NÉCESSAIRES : 'écoutez', 'en fait', "
        "'du coup', 'bon', 'vous voyez'. Sans elles le texte sonne comme un communiqué de presse.\n"
        "- Les fragments de phrases sont OK : 'Pas parfait. Mais ça marche.'\n"
        "- Les autocorrections sont OK : 'Y'en a trois... non, en fait quatre.'\n"
        "- Commencer par 'Et', 'Mais', 'Bon', 'Du coup' est normal. C'est de l'oral."
    ),
    "pt": (
        "Inserções coloquiais são naturais e NECESSÁRIAS: 'olha', 'tipo', "
        "'na real', 'bom', 'sabe'. Sem elas o texto soa como um comunicado.\n"
        "- Fragmentos de frase são OK: 'Não é perfeito. Mas funciona.'\n"
        "- Autocorreções são OK: 'São três... não, na verdade quatro coisas.'\n"
        "- Começar com 'E', 'Mas', 'Então', 'Bom' é normal. É fala oral."
    ),
    "de": (
        "Umgangssprachliche Einschübe sind natürlich und NÖTIG: 'schaut mal', 'also', "
        "'ehrlich gesagt', 'na ja', 'wisst ihr was'. Ohne sie klingt der Text wie vorgelesen.\n"
        "- Satzfragmente sind OK: 'Nicht perfekt. Aber es funktioniert.'\n"
        "- Selbstkorrekturen sind OK: 'Es sind drei... nein, eigentlich vier Sachen.'\n"
        "- Mit 'Und', 'Aber', 'Also', 'Na' anfangen ist normal. Das ist gesprochene Sprache."
    ),
}

# ---------------------------------------------------------------------------
# Language-specific few-shot script examples
# ---------------------------------------------------------------------------
FEWSHOT_SCRIPTS: dict[str, str] = {
    "ru": """**Пример полного сценария (ориентир стиля, НЕ копировать):**

Оригинал (~35 сек, EN): «I replaced my $4,000/month developer with a $20 tool called Cursor. It writes code, fixes bugs, and ships features faster than any junior dev I've hired. Here's how I set it up in 10 minutes.»

Адаптированный сценарий:
«Разработчик обходился мне в 4000 долларов в месяц. Я нашёл замену за двадцатку. Cursor. Это ИИ-редактор кода — ну, по сути, ты ему говоришь что сделать, а он пишет.

Вот смотрите. Я открываю проект, описываю задачу обычным текстом. Не код — просто «добавь форму регистрации с валидацией почты». И он делает. Целиком. С обработкой ошибок.

Баги? Кидаешь ему лог ошибки — он сам находит проблему и фиксит. Я за вечер закрыл задачи, на которые раньше уходила неделя.

Подпишись, чтобы не пропустить.

~33 секунды»

Обрати внимание на стиль: короткие панчи чередуются с длинными предложениями. «Ну, по сути» — разговорная вставка. «Вот смотрите» — прямое обращение. Фрагмент «Баги?» — одно слово как абзац.""",

    "en": """**Full script example (style reference, do NOT copy):**

Original (~35 sec, EN): «I replaced my $4,000/month developer with a $20 tool called Cursor. It writes code, fixes bugs, and ships features faster than any junior dev I've hired. Here's how I set it up in 10 minutes.»

Adapted script:
«Four thousand dollars a month. That's what my developer cost me. I replaced him with a twenty dollar tool. It's called Cursor — basically, you tell it what to build and it writes the code.

Here's the thing. I open my project, describe what I need in plain English. Not code — just 'add a signup form with email validation.' And it does it. The whole thing. Error handling included.

Bugs? You paste the error log — it finds the problem and fixes it. I shipped a week's worth of work in one evening.

Subscribe so you don't miss the next one.

~33 seconds»

Notice the style: short punches alternate with longer sentences. 'Here's the thing' — colloquial insert. 'Bugs?' — one word as a paragraph. Contractions everywhere: 'That's', 'it's', 'don't'.""",

    "es": """**Ejemplo de guion completo (referencia de estilo, NO copiar):**

Original (~35 seg, EN): «I replaced my $4,000/month developer with a $20 tool called Cursor.»

Guion adaptado:
«Cuatro mil dólares al mes. Eso me costaba mi programador. Lo reemplacé con una herramienta de veinte dólares. Se llama Cursor — o sea, le dices qué hacer y escribe el código.

Mira. Abro mi proyecto, describo lo que necesito en texto normal. No código — solo 'agrega un formulario de registro con validación de email.' Y lo hace. Completo. Con manejo de errores.

¿Bugs? Le pegas el log del error — encuentra el problema y lo arregla solo. En una tarde cerré tareas que antes me llevaban una semana.

Suscríbete para no perderte el siguiente.

~33 segundos»

Observa el estilo: frases cortas se alternan con largas. 'O sea' — inserción coloquial. '¿Bugs?' — una palabra como párrafo.""",
}

_DEFAULT_FEWSHOT = FEWSHOT_SCRIPTS["ru"]

# Labels for the frontend preset selector
TONE_LABELS: dict[str, dict[str, str]] = {
    "conversational": {
        "ru": "Разговорный",
        "en": "Conversational",
        "fr": "Conversationnel",
        "pt": "Conversacional",
        "de": "Umgangssprachlich",
    },
    "expert": {
        "ru": "Экспертный",
        "en": "Expert",
        "fr": "Expert",
        "pt": "Especialista",
        "de": "Experte",
    },
    "energetic": {
        "ru": "Энергичный",
        "en": "Energetic",
        "fr": "Énergique",
        "pt": "Energético",
        "de": "Energisch",
    },
    "calm": {
        "ru": "Спокойный",
        "en": "Calm",
        "fr": "Calme",
        "pt": "Calmo",
        "de": "Ruhig",
    },
}

# ---------------------------------------------------------------------------
# Video format presets
# ---------------------------------------------------------------------------
VIDEO_FORMAT_PRESETS: dict[str, str] = {
    "head_plus_visual": "top 30% of the screen is talking head, bottom 70% is visuals",
    "talking_head_only": "talking head full screen with text callouts overlaid on video",
    "screencast_voiceover": "full-screen screencast with voiceover, no talking head",
}

VIDEO_FORMAT_LABELS: dict[str, dict[str, str]] = {
    "head_plus_visual": {
        "ru": "Голова + визуал",
        "en": "Head + visual",
        "fr": "Tête + visuel",
        "pt": "Cabeça + visual",
        "de": "Kopf + visuell",
    },
    "talking_head_only": {
        "ru": "Только голова",
        "en": "Talking head",
        "fr": "Tête parlante",
        "pt": "Cabeça falante",
        "de": "Sprechender Kopf",
    },
    "screencast_voiceover": {
        "ru": "Скринкаст",
        "en": "Screencast",
        "fr": "Screencast",
        "pt": "Screencast",
        "de": "Screencast",
    },
}

# ---------------------------------------------------------------------------
# Default values (match the original hardcoded DEFAULT_CONTENT_PROMPT)
# ---------------------------------------------------------------------------
DEFAULT_ABOUT_ME = (
    "The author adapts viral reels for their own audience. "
    "Identify the niche and target audience from the original reel's content. "
    "Adapt the content to resonate maximally with that audience: "
    "use relevant examples, accessible terminology, and current "
    "pain points of the niche."
)

DEFAULT_TONE_KEY = "conversational"

DEFAULT_SCRIPT_CTA = "Subscribe so you don't miss the next one."

DEFAULT_DESCRIPTION_CTA = (
    "\"Save and send to someone who needs this\" → "
    "\"Subscribe so you don't miss the next one.\""
)

DEFAULT_FORBIDDEN_WORDS = (
    "уничтожил, убийца, революция, это меняет всё, "
    "безумный, невероятный, шокирующий, взорвал, потрясающий, "
    "буквально перевернул, навсегда изменит, вы не поверите, "
    "секретный способ, волшебный"
)

DEFAULT_VIDEO_FORMAT_KEY = "head_plus_visual"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _resolve_tone(value: str | None) -> str:
    """Expand a preset key into full text, or return custom text as-is."""
    if value is None:
        return TONE_PRESETS[DEFAULT_TONE_KEY]
    return TONE_PRESETS.get(value, value)


def _resolve_video_format(value: str | None) -> str:
    if value is None:
        return VIDEO_FORMAT_PRESETS[DEFAULT_VIDEO_FORMAT_KEY]
    return VIDEO_FORMAT_PRESETS.get(value, value)


def _format_forbidden_words(words_csv: str) -> str:
    """Convert comma-separated words into a bullet-point line for the prompt."""
    words = [w.strip() for w in words_csv.split(",") if w.strip()]
    if not words:
        return ""
    return "- «" + "», «".join(words) + "»"


def _wrap_field(tag_name: str, value: str, is_user_provided: bool) -> str:
    """Wrap a value in XML tags if it was user-provided (not a default/preset).

    Default values are trusted system content and don't need wrapping.
    User-provided values get wrapped to help the LLM distinguish data from instructions.
    """
    if not is_user_provided:
        return value
    return f"<user_{tag_name}>{value}</user_{tag_name}>"


# ---------------------------------------------------------------------------
# Content prompt template
# ---------------------------------------------------------------------------
CONTENT_PROMPT_TEMPLATE = """\
You are an expert in reel adaptation.

## Who the author is and their audience

{about_me}

## Input you receive

1. Reel transcript with timecodes
2. Frame-by-frame breakdown: what is visually happening on screen at each moment
3. Video metadata (duration, platform, author)
4. Original post description (text below the reel) — hooks, CTAs, author's hashtags
5. Top comments (sorted by likes) — what hooked the audience

## How to use the input data

Silently analyze the source material:
- What is the core message, why did it work, what value is embedded.
- Extract specific hook artifacts: names, numbers, contrasts, actions.
- Identify the key value for the author's audience. Use the author's description, their niches and interests — examples, terminology and pain points should resonate with THEIR audience, not the original's audience.
- Estimate the original's timing (~2.5 words per second in Russian).
- Consider the original post description — it may contain hooks and CTAs absent from the speech.
- Consider the comments — if people are massively asking the same thing, it means this wasn't covered in the original. Address it in the script.
- If comments are not available — skip comment analysis, don't fabricate.
- If the original post description is empty — rely only on transcript and visuals.
- If the transcript is short or incomplete — compensate with the visual breakdown.

## What you must output

Exactly three blocks. No introductions, no analysis recap. Only the blocks.

### Block 1 — script (Teleprompter script)

Clean text split into paragraphs by semantic blocks. No labels like [HOOK], [BRIDGE], no formatting, no internal headings. Just text you read on camera. At the very end — on a separate line: ~XX seconds.

**Script structure:**
1. **Hook (first 2-3 seconds).** Give the viewer a reason not to scroll past.
2. **Topic development (main body).** Specifics on the reel's subject. For a review — what tool/method, how to launch it. For a story — what happened, where's the twist. For a transformation — the process and result. Simple and clear, no jargon where possible. This is the only part that can be cut if time is tight.
3. **Value bridge (mandatory block).** Explain the concrete benefit for the author's audience in plain terms. With numbers, if available. Examples must be relevant to the author's niche.
4. **Ending.** Always: "{script_cta}"

**Hook formula:**
- Value and specifics first, then the name. The product name comes AFTER the viewer understands why they need it.
- All specific artifacts from the original (names, numbers, contrasts) must be carried over. Cannot be replaced with abstractions.
- No abstract promises: "does something others can't," "and it has this one trick" — FORBIDDEN.
- No hype: "destroyed," "killer," "revolution," "this changes everything" — FORBIDDEN.

**Examples of correct hooks:**

Original: "I replaced my $4,000/month developer with a $20 tool called Cursor."
Hook: "I replaced a $4,000/month developer with a $20 tool. It's called Cursor."

Original: "OpenClaw just launched and it builds full CRMs from a single prompt."
Hook: "OpenClaw just dropped — write one prompt and get a full CRM."

Original: "I lost 12kg in 90 days without cutting carbs. Here's the exact protocol."
Hook: "I lost 12 kg in three months without cutting carbs. Here's the protocol."

Original: "This $8 serum outperformed my $120 La Mer in a blind test."
Hook: "An $8 serum beat La Mer at $120 in a blind test."

Original: "My small business hit $50K/month after one change to the funnel."
Hook: "My business hit $50K/month after one change to the funnel."

{fewshot_script}

**Timing:** the script should be approximately the same length as the original (~2.5 words/sec in Russian, ±5 seconds). If you need to shorten — cut part 2, NOT part 1 (hook) and NOT part 3 (value).

**Tone:** {tone}

**KEY RULE: write for the ear, not the eye.**
This text will be read aloud from a teleprompter. It's spoken language, not an essay. Every sentence must be easily spoken in one breath.

**Rhythm and burstiness (variation):**
- Vary length AGGRESSIVELY: short (3-5 words) → medium (8-12 words) → long (15-20 words) → punch (2-4 words). Monotonous rhythm = AI-text marker.
- Paragraphs also vary in length: one paragraph — one sentence, the next — three or four.
- If the script contains a list (tool rankings, list of AI tools, bullet points, etc.) — each item on a new line. Never merge lists into a single dense paragraph, otherwise the text is impossible to read from a teleprompter.

**Live speech markers:**
- {speech_markers}
- Avoid symmetrical lists where every item has the same length and structure.

**AI-text antipatterns (FORBIDDEN):**
{ai_markers}
- Nominalizations instead of verbs (not "implementation of the process" but "when you do it")
- Every paragraph following a "thesis → argument → conclusion" template — people don't talk like that
- Symmetrical constructions "Not only X, but also Y," "Both X and Y"
- Predictable transitions between blocks

**Self-check before output:**
1. Hook: will the viewer understand in 2 seconds why they should keep watching?
2. Artifacts: are all names, numbers, contrasts from the original in place?
3. Timing: does it fit the original's duration (±5 sec)?
4. Burstiness: do the shortest and longest sentences differ by at least 3x?
5. Read-aloud: can every sentence be spoken in one breath without stumbling?
6. AI markers: are there any words from the forbidden AI pattern list above?
7. Empty promises: any "and it has this one trick," "and it really works"?
8. Gaps from comments: are questions that were massively asked addressed?
9. "Friend over coffee" test: would you really say it like this to a friend? If not — rewrite.

### Block 2 — description (Reel description)

Ready-to-use text for the reel description. The description is text read with the eyes. It should look like it was written by a real person, not generated by AI.

**First line — always value.** Patterns by content type:
  - Review/tutorial: "How to launch...," "Step-by-step guide...," "Full walkthrough..."
  - Story/case study: hook-question or personal fact ("I spent 2 years and found...")
  - Transformation: "Before → after" ("From 0 to 50K subscribers in 3 months")
  - Compilation: "[Number] [things] for [result]" ("5 services for automation")
  - Audience pain: a question they recognize ("Tired of spending 3 hours on editing?")
- NEVER start with salary figures, pain points, or intros like "this is a tool from company X."
- Format: value-headline → step-by-step breakdown → what you can do → link (if available) → {description_cta}
- Consider CTAs from the original description — adapt the best ideas, don't copy verbatim.
- Additional content: if the reel has useful information that doesn't fit in the video (tool lists, repositories) — add it to the description. Such reels are more valuable and get saved more often.
- Maximum 8-10 lines. With emojis where appropriate.

**Description style — lively, not templated:**
- Vary line lengths: one line — 3-5 words, the next — 10-15. Uniform lines of equal length = AI marker.
- Incomplete sentences, exclamations, questions are fine. This is social media, not an article.
- Emojis — when appropriate, not every other word. 2-4 for the entire description.
- Do NOT start every line with an emoji — that's a template everyone has seen.
- Lists are fine, but don't turn the entire description into a bulleted list from start to finish. Alternate: text paragraph → bullet points → text.

**AI description antipatterns (FORBIDDEN):**
- Every line starts with an emoji (fire headline rocket point 1 bulb point 2) — this screams "AI"
- Symmetrical constructions: every item the same length and structure
- "In this video you'll learn," "In this reel I talked about" — direct AI indicators
- "Don't miss this opportunity," "This will change your approach" — empty promises
- ALL CAPS headings every other line
- "Problem → solution → CTA" format without variation — people don't write like that

**Description self-check:**
1. Does the first line hook and deliver value?
2. Does it look like an "emoji + bullet" template from start to finish?
3. AI markers: any forbidden AI phrases?
4. Do line lengths vary? Any monotony?
5. Test: if you saw this description in your feed — would you believe a human wrote it?

### Block 3 — editor_instructions (Instructions for the editor)

A text document for sending to the video editor via messenger. No tables. Compact, easy to read on a phone.

Frame format — {video_format}.

Structure:

FORMAT: {video_format}
DURATION: ~XX sec

— 0:00–0:03
Visual: what to show
Text: short phrase on screen
Transition: cut / zoom / swipe

— 0:03–0:08
Visual: screencast — opening the project
Text: short phrase
Transition: cut

...and so on for the entire reel.

Principles:
- Do NOT write speech text (it's in the script) — only visuals, on-screen text, and transitions
- Visuals amplify the words, not duplicate them
- The reel must be understandable without sound — from the picture and on-screen text alone
- On-screen text — 3-5 words maximum, not sentences
- Specify transition type between frames (cut, zoom in, swipe, fade)
- For screencasts — specify exactly what to show on screen

## Important rules

FORBIDDEN in the script:
{forbidden_words}
- Phrases that people never say in real life

FORBIDDEN in the hook:
- Starting with a product name that means nothing to the viewer
- Replacing specific artifacts from the original with abstractions
- Empty promises

FORBIDDEN in the description:
- Starting with pain points or salary figures
- Company introductions"""


# ---------------------------------------------------------------------------
# Strategy prompt template
# ---------------------------------------------------------------------------
STRATEGY_PROMPT_TEMPLATE = """\
You are a viral content strategist. Your task is to break down why a reel went viral and provide a concrete promotion strategy for the adapted version.

## Author context

{about_me}
**Tone:** {tone_short}

## Input you receive

1. Video metadata (views, likes, author, platform)
2. Transcript
3. Original post description
4. Top comments, sorted by likes
5. List of frames with descriptions (for cover recommendation)

## What you must output

### Block 1 — virality_breakdown (Why it went viral)

Compact analysis, 5-8 sentences:
- Hook type (contrast / shock / curiosity / specific number / pain point)
- How it retains after the hook (escalating value / series of mini-revelations / storytelling / step-by-step process)
- Engagement rate (likes/views, 3-5% is normal, higher = viral)
- Main emotional trigger — what exactly made people like/comment/save
- What in the comments confirms the hypothesis

No fluff, no "overall the reel is good." Only specifics and mechanics.

### Block 2 — hook_variants (Alternative hooks)

The primary hook already exists in the script (faithful adaptation of the original). You generate 4 ALTERNATIVES — each using a DIFFERENT technique so the author can choose the best approach.

Each variant is an object with three fields:
- "text" — hook text (1-2 sentences to say on camera)
- "score" — effectiveness score 0-100
- "why" — 2-3 sentences: (1) name the technique, (2) explain the psychological mechanism — why it stops the scroller, (3) a short example or analogy from real practice

Variants:
1. Amplified for the author's audience — more specifics, stronger numbers/contrasts
2. Provocative or contrasting — hook the scroller with an unexpected angle
3. Question / curiosity gap — intrigue that compels watching to the end
4. Bold claim / transformation — result upfront (before/after, outcome first)

Score criteria:
- Attention capture (will it stop the scroll?) — 40%
- Relevance to the author's audience — 30%
- Emotional trigger strength — 30%

Also rate the PRIMARY hook (the one in the script — faithful adaptation of the original):
- "primary_hook_score" — its score 0-100
- "primary_hook_why" — 2-3 sentences: (1) name the technique, (2) explain the psychological mechanism, (3) why it worked for this specific audience

Rules:
- Value first, then tool name
- No hype: "killer," "revolution" — FORBIDDEN
- No abstractions: "and it has this one trick" — FORBIDDEN
- Specific artifacts from the original (numbers, names, contrasts) are mandatory

### Block 3 — hashtags (Hashtags)

**primary** — 5-7 main hashtags. Mix:
- 2-3 broad high-reach ones (relevant to the author's niche)
- 2-3 niche-specific ones (specific to the author's topic area)
- 1 trending, if relevant

**secondary** — 3-5 additional narrow hashtags for the algorithm

All hashtags should be in the target audience's language, except product names.

### Block 4 — cover (Cover recommendation)

**recommended_frame_index** — index of the frame best suited for a cover. Choose a frame where:
- It's maximally clear what the video is about (screencast with result, interface, finished product)
- NOT a blank screen, NOT a close-up face without context

**cover_text** — text to overlay on the cover. 3-5 words maximum.

**why** — 1 sentence explaining why this frame and this text.

### Block 5 — classification (Library classification)

**language** — two-letter ISO code of the original language (en, es, ru...)
**content_format** — one of: tutorial, review, comparison, story, behind_the_scenes, news, motivation, entertainment, demo, explainer, other
**topics** — 3-6 topic slugs in English (ai-tools, vibe-coding, no-code, saas, automation, cursor, productivity)
**keywords** — 5-10 specific keywords/names from the original in the original language
**niche** — one niche slug: ai, vibe-coding, software-dev, saas, no-code, cybersecurity, business, startups, ecommerce, finance, investing, crypto, real-estate, marketing, personal-brand, copywriting, seo, design, photography, video-production, music, art, education, career, coaching, health, fitness, mental-health, lifestyle, travel, food, fashion, parenting, entertainment, gaming, sports, other. "vibe-coding" — building apps with AI (Cursor, Replit, v0). "ai" — reviewing/teaching AI tools. "software-dev" — programming without AI focus. "ecommerce" — dropshipping/marketplaces. "personal-brand" — content creation/audience growth

## Important rules

- Adapt hashtags for the author's audience market
- Don't fabricate metrics — use actual views/likes for engagement rate calculation"""


# ---------------------------------------------------------------------------
# Compose functions
# ---------------------------------------------------------------------------
def _format_ai_markers(lang: str) -> str:
    """Build AI marker ban-list for the target language (no fallback to unrelated language)."""
    markers = AI_MARKER_WORDS.get(lang, "")
    if not markers:
        return "- Avoid generic filler phrases and overly formal language typical of AI-generated text"
    words = [w.strip() for w in markers.split(",") if w.strip()]
    return "- AI marker words and phrases: \"" + "\", \"".join(words) + "\""


def _resolve_speech_markers(lang: str) -> str:
    """Get language-specific speech markers, falling back to Russian."""
    return SPEECH_MARKERS.get(lang, SPEECH_MARKERS["ru"])


def _resolve_fewshot(lang: str) -> str:
    """Get language-specific few-shot script example."""
    return FEWSHOT_SCRIPTS.get(lang, _DEFAULT_FEWSHOT)


def compose_content_prompt(
    profile: UserProfile | None,
    target_language: str = "ru",
) -> str:
    """Build the full content system prompt from profile fields."""
    p = profile or UserProfile()

    about_me = p.about_me or DEFAULT_ABOUT_ME
    # Enrich about_me with niches and interests from profile
    if p.niches:
        about_me += f"\n\nAuthor's niches: {', '.join(p.niches)}"
    if p.interests:
        about_me += f"\nTopics and interests: {', '.join(p.interests)}"

    tone = _resolve_tone(p.tone)
    script_cta = p.script_cta or DEFAULT_SCRIPT_CTA
    description_cta = p.description_cta or DEFAULT_DESCRIPTION_CTA
    forbidden = p.forbidden_words or DEFAULT_FORBIDDEN_WORDS
    video_format = _resolve_video_format(p.video_format)
    forbidden_words = _format_forbidden_words(forbidden)
    ai_markers = _format_ai_markers(target_language)
    speech_markers = _resolve_speech_markers(target_language)
    fewshot_script = _resolve_fewshot(target_language)

    # Wrap user-provided values in XML tags for prompt isolation
    about_me = _wrap_field("about_me", about_me, p.about_me is not None)
    tone = _wrap_field("tone", tone, p.tone is not None and p.tone not in TONE_PRESETS)
    script_cta = _wrap_field("script_cta", script_cta, p.script_cta is not None)
    description_cta = _wrap_field("description_cta", description_cta, p.description_cta is not None)
    forbidden_words = _wrap_field("forbidden_words", forbidden_words, p.forbidden_words is not None)
    video_format = _wrap_field(
        "video_format", video_format,
        p.video_format is not None and p.video_format not in VIDEO_FORMAT_PRESETS,
    )

    result = CONTENT_PROMPT_TEMPLATE.format(
        about_me=about_me,
        tone=tone,
        script_cta=script_cta,
        description_cta=description_cta,
        forbidden_words=forbidden_words,
        video_format=video_format,
        ai_markers=ai_markers,
        speech_markers=speech_markers,
        fewshot_script=fewshot_script,
    )

    if p.content_prompt_additions:
        additions = _wrap_field("content_prompt_additions", p.content_prompt_additions, True)
        result += f"\n\n## Additional author style instructions\n{additions}"

    return result


def compose_strategy_prompt(profile: UserProfile | None) -> str:
    """Build the full strategy system prompt from profile fields."""
    p = profile or UserProfile()

    about_me = p.about_me or DEFAULT_ABOUT_ME
    tone = _resolve_tone(p.tone)
    # Use a short version of tone for the strategy rules section
    tone_short = tone.split(".")[0] if "." in tone else tone

    # Wrap user-provided values in XML tags for prompt isolation
    about_me = _wrap_field("about_me", about_me, p.about_me is not None)
    tone_short = _wrap_field("tone", tone_short, p.tone is not None and p.tone not in TONE_PRESETS)

    return STRATEGY_PROMPT_TEMPLATE.format(
        about_me=about_me,
        tone_short=tone_short,
    )
