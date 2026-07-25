"""Central niche definitions registry — single source of truth for the entire app."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class NicheDefinition:
    slug: str
    display_name: str
    description: str
    keywords: list[str] = field(default_factory=list)


# ── Niche definitions ─────────────────────────────────────────────────────

NICHE_DEFINITIONS: dict[str, NicheDefinition] = {
    # ── Tech & AI ────────────────────────────────────────────────────────
    "ai": NicheDefinition(
        slug="ai",
        display_name="AI & Machine Learning",
        description="AI tools, prompts, agents, AI-generated content, LLM wrappers",
        keywords=["chatgpt", "claude", "midjourney", "dall-e", "ai-agents", "prompt-engineering", "llm"],
    ),
    "vibe-coding": NicheDefinition(
        slug="vibe-coding",
        display_name="Vibe Coding",
        description="Building apps/products with AI coding assistants, no-code AI dev",
        keywords=["cursor", "replit", "v0", "bolt", "lovable", "windsurf", "ai-coding"],
    ),
    "software-dev": NicheDefinition(
        slug="software-dev",
        display_name="Software Development",
        description="Programming, code tutorials, dev tools (not AI-focused)",
        keywords=["javascript", "python", "react", "api", "github", "backend", "frontend"],
    ),
    "saas": NicheDefinition(
        slug="saas",
        display_name="SaaS",
        description="SaaS products, micro-SaaS, indie hacking, MRR growth",
        keywords=["mrr", "churn", "saas", "subscription", "indie-hacker", "micro-saas"],
    ),
    "no-code": NicheDefinition(
        slug="no-code",
        display_name="No-Code / Low-Code",
        description="No-code/low-code platforms and automation (not AI-specific)",
        keywords=["zapier", "bubble", "make", "airtable", "notion", "glide"],
    ),
    "cybersecurity": NicheDefinition(
        slug="cybersecurity",
        display_name="Cybersecurity",
        description="InfoSec, hacking, privacy, data protection",
        keywords=["hacking", "pentest", "vpn", "encryption", "osint", "privacy"],
    ),
    "tech": NicheDefinition(
        slug="tech",
        display_name="Tech & Gadgets",
        description="General technology, gadgets, hardware, apps (not AI or coding specific)",
        keywords=["gadgets", "hardware", "apps", "smartphone", "tech-review", "apple", "android"],
    ),
    "science": NicheDefinition(
        slug="science",
        display_name="Science & Space",
        description="Popular science, physics, chemistry, biology, space exploration, experiments",
        keywords=["science", "space", "nasa", "physics", "biology", "chemistry", "experiment"],
    ),
    "data-science": NicheDefinition(
        slug="data-science",
        display_name="Data Science & Analytics",
        description="Data analysis, machine learning pipelines, visualization, SQL, BI tools",
        keywords=["pandas", "sql", "tableau", "power-bi", "data-visualization", "statistics"],
    ),

    # ── Business & Money ─────────────────────────────────────────────────
    "business": NicheDefinition(
        slug="business",
        display_name="Business",
        description="Business management, scaling, operations, established companies",
        keywords=["founder", "ceo", "revenue", "scaling", "management", "operations"],
    ),
    "startups": NicheDefinition(
        slug="startups",
        display_name="Startups",
        description="Early-stage startups, fundraising, MVPs, accelerators",
        keywords=["seed", "vc", "pitch-deck", "accelerator", "mvp", "fundraising"],
    ),
    "ecommerce": NicheDefinition(
        slug="ecommerce",
        display_name="E-commerce",
        description="Dropshipping, marketplaces, Shopify, Amazon FBA, online stores",
        keywords=["shopify", "amazon", "dropshipping", "wildberries", "ozon", "fba"],
    ),
    "finance": NicheDefinition(
        slug="finance",
        display_name="Personal Finance",
        description="Personal finance, budgeting, taxes, banking, saving money",
        keywords=["budget", "taxes", "savings", "credit", "banking", "money"],
    ),
    "investing": NicheDefinition(
        slug="investing",
        display_name="Investing",
        description="Stock market, ETFs, portfolio management, dividends",
        keywords=["stocks", "etf", "portfolio", "dividends", "sp500", "trading"],
    ),
    "crypto": NicheDefinition(
        slug="crypto",
        display_name="Crypto & Web3",
        description="Cryptocurrency, blockchain, DeFi, Web3, NFTs",
        keywords=["bitcoin", "ethereum", "defi", "nft", "web3", "token"],
    ),
    "real-estate": NicheDefinition(
        slug="real-estate",
        display_name="Real Estate",
        description="Property investing, flipping, rental income, mortgages",
        keywords=["property", "rental", "mortgage", "flipping", "reit"],
    ),
    "freelance": NicheDefinition(
        slug="freelance",
        display_name="Freelance & Remote Work",
        description="Freelancing, remote work, gig economy, client management",
        keywords=["freelance", "upwork", "fiverr", "remote", "digital-nomad", "gig"],
    ),
    "legal": NicheDefinition(
        slug="legal",
        display_name="Legal & Law",
        description="Legal advice, law explained, rights, contracts, legal tips for business",
        keywords=["lawyer", "contract", "rights", "court", "legal-advice", "law"],
    ),

    # ── Marketing & Growth ───────────────────────────────────────────────
    "marketing": NicheDefinition(
        slug="marketing",
        display_name="Marketing",
        description="Digital marketing, ads, funnels, growth hacking, analytics",
        keywords=["facebook-ads", "google-ads", "funnel", "cpm", "roas", "analytics"],
    ),
    "personal-brand": NicheDefinition(
        slug="personal-brand",
        display_name="Personal Brand",
        description="Content creation tips, social media growth, audience building",
        keywords=["instagram-growth", "tiktok", "youtube", "followers", "creator"],
    ),
    "copywriting": NicheDefinition(
        slug="copywriting",
        display_name="Copywriting",
        description="Persuasive writing, sales copy, email marketing, hooks",
        keywords=["headline", "hook", "email-sequence", "cta", "conversion", "copy"],
    ),
    "seo": NicheDefinition(
        slug="seo",
        display_name="SEO",
        description="Search engine optimization, organic traffic, keyword research",
        keywords=["backlinks", "serp", "keyword-research", "google", "organic"],
    ),
    "smm": NicheDefinition(
        slug="smm",
        display_name="SMM & Social Media",
        description="Social media management, community building, platform strategies",
        keywords=["smm", "instagram", "tiktok", "reels", "engagement", "community"],
    ),

    # ── Creative ─────────────────────────────────────────────────────────
    "design": NicheDefinition(
        slug="design",
        display_name="Design",
        description="UI/UX, graphic design, branding, visual identity",
        keywords=["figma", "canva", "typography", "ui", "ux", "logo", "branding"],
    ),
    "photography": NicheDefinition(
        slug="photography",
        display_name="Photography",
        description="Photography techniques, editing, gear reviews",
        keywords=["lightroom", "photoshop", "portrait", "landscape", "camera"],
    ),
    "video-production": NicheDefinition(
        slug="video-production",
        display_name="Video Production",
        description="Video editing, cinematography, filmmaking, production tips",
        keywords=["premiere", "davinci", "transitions", "b-roll", "cinematography", "film"],
    ),
    "music": NicheDefinition(
        slug="music",
        display_name="Music",
        description="Music production, beats, instruments, releases, covers",
        keywords=["ableton", "fl-studio", "beats", "mixing", "mastering", "guitar", "piano"],
    ),
    "art": NicheDefinition(
        slug="art",
        display_name="Art & Illustration",
        description="Illustration, digital art, 3D, animation, traditional art",
        keywords=["procreate", "blender", "3d", "illustration", "animation", "drawing"],
    ),
    "writing": NicheDefinition(
        slug="writing",
        display_name="Writing & Literature",
        description="Creative writing, poetry, storytelling, book authoring",
        keywords=["writing", "novel", "poetry", "storytelling", "author", "nanowrimo"],
    ),
    "dance": NicheDefinition(
        slug="dance",
        display_name="Dance & Choreography",
        description="Dance tutorials, choreography, dance challenges, performances",
        keywords=["dance", "choreography", "ballet", "hip-hop", "contemporary", "twerk"],
    ),
    "crafts": NicheDefinition(
        slug="crafts",
        display_name="DIY & Crafts",
        description="Handmade, DIY projects, crafting, woodworking, knitting, sewing",
        keywords=["diy", "handmade", "craft", "knitting", "sewing", "woodworking", "epoxy"],
    ),

    # ── Education & Career ───────────────────────────────────────────────
    "education": NicheDefinition(
        slug="education",
        display_name="Education",
        description="Teaching, courses, e-learning, study techniques, academic content",
        keywords=["course", "tutorial", "learning", "study", "online-school", "university"],
    ),
    "career": NicheDefinition(
        slug="career",
        display_name="Career & Jobs",
        description="Job search, resume, interviews, professional growth",
        keywords=["resume", "linkedin", "interview", "salary", "promotion", "hr"],
    ),
    "coaching": NicheDefinition(
        slug="coaching",
        display_name="Coaching & Mentoring",
        description="Life/business coaching, mentorship, consulting",
        keywords=["mentor", "coaching", "mindset", "accountability", "consulting"],
    ),
    "languages": NicheDefinition(
        slug="languages",
        display_name="Language Learning",
        description="Foreign language learning, polyglot tips, language apps",
        keywords=["english", "spanish", "duolingo", "polyglot", "vocabulary", "grammar"],
    ),
    "self-development": NicheDefinition(
        slug="self-development",
        display_name="Self-Development",
        description="Personal growth, habits, goal setting, motivation, discipline",
        keywords=["growth", "habits", "goals", "motivation", "discipline", "self-improvement"],
    ),
    "philosophy": NicheDefinition(
        slug="philosophy",
        display_name="Philosophy",
        description="Philosophy, stoicism, existentialism, meaning of life, ethics, critical thinking",
        keywords=["stoicism", "philosophy", "existentialism", "ethics", "meaning", "socrates", "nietzsche"],
    ),

    # ── Health & Wellness ────────────────────────────────────────────────
    "health": NicheDefinition(
        slug="health",
        display_name="Health & Wellness",
        description="General health, wellness, biohacking, longevity",
        keywords=["wellness", "supplements", "biohacking", "sleep", "longevity"],
    ),
    "fitness": NicheDefinition(
        slug="fitness",
        display_name="Fitness & Gym",
        description="Exercise, gym, training programs, sports performance",
        keywords=["workout", "gym", "crossfit", "running", "training", "bodybuilding"],
    ),
    "mental-health": NicheDefinition(
        slug="mental-health",
        display_name="Mental Health",
        description="Clinical mental health: anxiety, depression, therapy, PTSD, burnout, recovery",
        keywords=["anxiety", "depression", "therapy", "burnout", "ptsd", "recovery", "psychiatry"],
    ),
    "psychology": NicheDefinition(
        slug="psychology",
        display_name="Psychology",
        description="Popular psychology: narcissism, attachment styles, emotional intelligence, manipulation, body language, cognitive biases",
        keywords=["narcissism", "attachment", "emotional-intelligence", "manipulation", "body-language", "cognitive-bias", "psychology"],
    ),
    "sexology": NicheDefinition(
        slug="sexology",
        display_name="Sexology & Intimacy",
        description="Sex education, intimacy, sexual health, libido, consent, pleasure",
        keywords=["sexology", "intimacy", "libido", "consent", "sex-education", "sexual-health"],
    ),
    "nutrition": NicheDefinition(
        slug="nutrition",
        display_name="Nutrition & Diets",
        description="Nutrition science, diets, meal planning, supplements, weight management",
        keywords=["diet", "calories", "protein", "keto", "fasting", "supplements", "macros"],
    ),
    "yoga": NicheDefinition(
        slug="yoga",
        display_name="Yoga & Meditation",
        description="Yoga practice, meditation, breathing exercises, flexibility",
        keywords=["yoga", "meditation", "pranayama", "flexibility", "chakra", "zen"],
    ),
    "medicine": NicheDefinition(
        slug="medicine",
        display_name="Medicine & Pharma",
        description="Medical education, doctor content, pharma, clinical topics",
        keywords=["doctor", "medicine", "diagnosis", "pharma", "surgery", "hospital"],
    ),
    "biohacking": NicheDefinition(
        slug="biohacking",
        display_name="Biohacking",
        description="Biohacking, nootropics, performance optimization, quantified self",
        keywords=["nootropics", "biohacking", "cold-plunge", "sauna", "wearables", "optimization"],
    ),

    # ── Beauty & Fashion ─────────────────────────────────────────────────
    "beauty": NicheDefinition(
        slug="beauty",
        display_name="Beauty & Makeup",
        description="Makeup tutorials, beauty routines, cosmetics reviews, skincare",
        keywords=["makeup", "skincare", "cosmetics", "beauty-routine", "foundation", "lipstick"],
    ),
    "fashion": NicheDefinition(
        slug="fashion",
        display_name="Fashion & Style",
        description="Style, outfits, clothing brands, fashion trends, streetwear",
        keywords=["outfit", "streetwear", "luxury", "thrift", "style", "ootd"],
    ),
    "hair": NicheDefinition(
        slug="hair",
        display_name="Hair & Hairstyling",
        description="Hairstyling, haircare, hair color, barber content",
        keywords=["hairstyle", "haircare", "color", "barber", "curls", "braids"],
    ),
    "nails": NicheDefinition(
        slug="nails",
        display_name="Nails & Nail Art",
        description="Manicure, nail art, nail design, nail care",
        keywords=["manicure", "nail-art", "gel", "pedicure", "nail-design"],
    ),

    # ── Lifestyle ────────────────────────────────────────────────────────
    "lifestyle": NicheDefinition(
        slug="lifestyle",
        display_name="Lifestyle",
        description="Daily routines, productivity, minimalism, vlogs",
        keywords=["morning-routine", "vlog", "minimalism", "habits", "aesthetic"],
    ),
    "travel": NicheDefinition(
        slug="travel",
        display_name="Travel",
        description="Travel content, destinations, tips, digital nomad, backpacking",
        keywords=["flight", "hotel", "backpacking", "digital-nomad", "destination"],
    ),
    "food": NicheDefinition(
        slug="food",
        display_name="Food & Cooking",
        description="Recipes, restaurants, cooking tutorials, food reviews",
        keywords=["recipe", "cooking", "restaurant", "meal-prep", "foodie", "baking"],
    ),
    "home-decor": NicheDefinition(
        slug="home-decor",
        display_name="Home & Interior",
        description="Interior design, home decor, renovation, organization",
        keywords=["interior", "decor", "renovation", "ikea", "organization", "home-tour"],
    ),
    "sustainability": NicheDefinition(
        slug="sustainability",
        display_name="Sustainability & Eco",
        description="Eco lifestyle, zero waste, sustainability, climate, environment",
        keywords=["eco", "zero-waste", "sustainability", "recycle", "climate", "green"],
    ),
    "gardening": NicheDefinition(
        slug="gardening",
        display_name="Gardening",
        description="Gardening, plants, urban farming, houseplants, landscaping",
        keywords=["garden", "plants", "houseplants", "farming", "landscape", "grow"],
    ),
    "productivity": NicheDefinition(
        slug="productivity",
        display_name="Productivity & Habits",
        description="Productivity systems, time management, habits, tools, planning",
        keywords=["productivity", "notion", "planning", "time-management", "habits", "gtd"],
    ),
    "automotive": NicheDefinition(
        slug="automotive",
        display_name="Automotive & Cars",
        description="Cars, car reviews, motorsport, auto repair, car culture",
        keywords=["cars", "automotive", "tesla", "bmw", "tuning", "car-review", "drift"],
    ),
    "outdoor": NicheDefinition(
        slug="outdoor",
        display_name="Outdoor & Adventure",
        description="Hiking, camping, outdoor sports, survival, nature exploration",
        keywords=["hiking", "camping", "outdoor", "survival", "mountains", "trail"],
    ),
    "immigration": NicheDefinition(
        slug="immigration",
        display_name="Immigration & Relocation",
        description="Emigration, relocation, life abroad, visas, adaptation, expat life",
        keywords=["relocation", "emigration", "visa", "expat", "abroad", "immigration", "adaptation"],
    ),
    "fishing": NicheDefinition(
        slug="fishing",
        display_name="Fishing & Hunting",
        description="Fishing, hunting, tackle reviews, fishing spots, catches, hunting gear",
        keywords=["fishing", "hunting", "tackle", "catch", "bass", "carp", "rifle", "hunt"],
    ),

    # ── Family & Relationships ───────────────────────────────────────────
    "parenting": NicheDefinition(
        slug="parenting",
        display_name="Parenting & Motherhood",
        description="Parenthood, child development, motherhood, fatherhood, baby care",
        keywords=["kids", "baby", "motherhood", "family", "parenting", "toddler"],
    ),
    "relationships": NicheDefinition(
        slug="relationships",
        display_name="Relationships & Dating",
        description="Dating, love, couples, relationship advice, breakups",
        keywords=["dating", "love", "couples", "relationship", "breakup", "marriage"],
    ),
    "family": NicheDefinition(
        slug="family",
        display_name="Family Life",
        description="Family life, home, household, family traditions, multi-generational",
        keywords=["family", "home", "household", "siblings", "grandparents", "traditions"],
    ),
    "pregnancy": NicheDefinition(
        slug="pregnancy",
        display_name="Pregnancy & Birth",
        description="Pregnancy journey, birth preparation, postnatal care, fertility",
        keywords=["pregnancy", "birth", "prenatal", "postnatal", "fertility", "baby-bump"],
    ),
    "wedding": NicheDefinition(
        slug="wedding",
        display_name="Wedding",
        description="Wedding planning, bridal content, wedding inspiration",
        keywords=["wedding", "bride", "groom", "wedding-planning", "engagement"],
    ),

    # ── Spirituality & Esoteric ──────────────────────────────────────────
    "astrology": NicheDefinition(
        slug="astrology",
        display_name="Astrology & Horoscopes",
        description="Astrology, zodiac signs, horoscopes, natal charts, planetary transits",
        keywords=["zodiac", "horoscope", "natal-chart", "mercury-retrograde", "aries", "scorpio"],
    ),
    "tarot": NicheDefinition(
        slug="tarot",
        display_name="Tarot & Divination",
        description="Tarot readings, oracle cards, divination, fortune telling",
        keywords=["tarot", "oracle", "divination", "cards", "reading", "fortune"],
    ),
    "numerology": NicheDefinition(
        slug="numerology",
        display_name="Numerology",
        description="Numerology, angel numbers, life path numbers, number meanings",
        keywords=["numerology", "angel-numbers", "life-path", "111", "222", "333"],
    ),
    "energy-practices": NicheDefinition(
        slug="energy-practices",
        display_name="Energy Practices",
        description="Reiki, energy healing, chakras, aura, crystal healing, sound baths",
        keywords=["reiki", "chakra", "energy", "crystal", "healing", "aura", "sound-bath"],
    ),
    "human-design": NicheDefinition(
        slug="human-design",
        display_name="Human Design",
        description="Human Design system, types, profiles, gates, channels, strategy & authority",
        keywords=["human-design", "generator", "manifestor", "projector", "reflector", "bodygraph"],
    ),
    "religion": NicheDefinition(
        slug="religion",
        display_name="Religion & Faith",
        description="Religious content, faith, prayer, church, mosque, temple, scripture",
        keywords=["religion", "faith", "prayer", "bible", "quran", "church", "god"],
    ),
    "spirituality": NicheDefinition(
        slug="spirituality",
        display_name="Spirituality & Mindfulness",
        description="Spiritual growth, consciousness, awakening, non-religious spirituality",
        keywords=["spirituality", "consciousness", "awakening", "manifestation", "universe"],
    ),

    # ── Entertainment & Humor ────────────────────────────────────────────
    "entertainment": NicheDefinition(
        slug="entertainment",
        display_name="Entertainment",
        description="General entertainment, reactions, challenges, pop culture",
        keywords=["challenge", "reaction", "viral", "pop-culture", "celebrity"],
    ),
    "comedy": NicheDefinition(
        slug="comedy",
        display_name="Comedy & Humor",
        description="Comedy sketches, stand-up, humor, funny videos, satire",
        keywords=["comedy", "funny", "standup", "sketch", "humor", "satire", "joke"],
    ),
    "memes": NicheDefinition(
        slug="memes",
        display_name="Memes",
        description="Meme culture, internet humor, viral memes, meme edits",
        keywords=["meme", "shitpost", "viral", "dank", "edit"],
    ),
    "gaming": NicheDefinition(
        slug="gaming",
        display_name="Gaming",
        description="Video games, streaming, game reviews, walkthroughs",
        keywords=["twitch", "steam", "game-review", "playstation", "xbox", "nintendo"],
    ),
    "anime": NicheDefinition(
        slug="anime",
        display_name="Anime & Manga",
        description="Anime reviews, manga, cosplay, Japanese pop culture",
        keywords=["anime", "manga", "cosplay", "otaku", "one-piece", "naruto"],
    ),
    "true-crime": NicheDefinition(
        slug="true-crime",
        display_name="True Crime",
        description="True crime stories, investigations, cold cases, criminal psychology",
        keywords=["true-crime", "murder", "investigation", "cold-case", "serial-killer"],
    ),
    "asmr": NicheDefinition(
        slug="asmr",
        display_name="ASMR",
        description="ASMR content, relaxation sounds, triggers, whispering",
        keywords=["asmr", "triggers", "relaxation", "whispering", "tapping", "tingles"],
    ),
    "books": NicheDefinition(
        slug="books",
        display_name="Books & BookTok",
        description="Book reviews, reading recommendations, BookTok, literature discussions",
        keywords=["booktok", "reading", "book-review", "bookstagram", "tbr", "fiction"],
    ),
    "cinema": NicheDefinition(
        slug="cinema",
        display_name="Cinema & TV",
        description="Movie reviews, TV series, film analysis, watch lists, Oscar predictions",
        keywords=["movie", "film-review", "series", "netflix", "oscar", "cinema", "tv-show"],
    ),

    # ── Sports ───────────────────────────────────────────────────────────
    "sports": NicheDefinition(
        slug="sports",
        display_name="Sports",
        description="Sports commentary, analysis, athlete content, general sports",
        keywords=["football", "basketball", "soccer", "nfl", "nba", "championship"],
    ),
    "martial-arts": NicheDefinition(
        slug="martial-arts",
        display_name="Martial Arts & MMA",
        description="MMA, boxing, BJJ, karate, self-defense, fight commentary",
        keywords=["mma", "ufc", "boxing", "bjj", "karate", "self-defense"],
    ),
    "extreme-sports": NicheDefinition(
        slug="extreme-sports",
        display_name="Extreme Sports",
        description="Skateboarding, surfing, snowboarding, parkour, BMX",
        keywords=["skateboard", "surf", "snowboard", "parkour", "bmx", "adrenaline"],
    ),
    "esports": NicheDefinition(
        slug="esports",
        display_name="Esports",
        description="Competitive gaming, esports tournaments, pro players, team content",
        keywords=["esports", "tournament", "league", "valorant", "cs2", "dota"],
    ),

    # ── Pets & Animals ───────────────────────────────────────────────────
    "pets": NicheDefinition(
        slug="pets",
        display_name="Pets",
        description="Pet care, pet lifestyle, general pet content",
        keywords=["pet", "puppy", "kitten", "pet-care", "vet", "adoption"],
    ),
    "dogs": NicheDefinition(
        slug="dogs",
        display_name="Dogs",
        description="Dog content, training, breeds, dog lifestyle",
        keywords=["dog", "puppy", "golden-retriever", "dog-training", "doggo"],
    ),
    "cats": NicheDefinition(
        slug="cats",
        display_name="Cats",
        description="Cat content, cat behavior, breeds, funny cats",
        keywords=["cat", "kitten", "catto", "cat-behavior", "meow"],
    ),
    "wildlife": NicheDefinition(
        slug="wildlife",
        display_name="Wildlife & Nature",
        description="Wild animals, nature documentaries, conservation, marine life",
        keywords=["wildlife", "nature", "animals", "conservation", "marine", "safari"],
    ),

    # ── News & Society ───────────────────────────────────────────────────
    "news": NicheDefinition(
        slug="news",
        display_name="News & Current Events",
        description="Breaking news, current events, journalism, news commentary",
        keywords=["news", "breaking", "journalism", "current-events", "headlines"],
    ),
    "politics": NicheDefinition(
        slug="politics",
        display_name="Politics",
        description="Political commentary, elections, policy, geopolitics",
        keywords=["politics", "election", "policy", "government", "geopolitics"],
    ),
    "economics": NicheDefinition(
        slug="economics",
        display_name="Economics",
        description="Macroeconomics, economic analysis, global markets, inflation",
        keywords=["economics", "inflation", "gdp", "recession", "fed", "markets"],
    ),
    "history": NicheDefinition(
        slug="history",
        display_name="History",
        description="Historical content, history education, historical events, documentaries",
        keywords=["history", "ww2", "ancient", "medieval", "historical", "documentary"],
    ),
    "military": NicheDefinition(
        slug="military",
        display_name="Military & Defense",
        description="Military content, defense technology, veterans, military history",
        keywords=["military", "army", "navy", "defense", "veteran", "weapons"],
    ),

    # ── Fallback ─────────────────────────────────────────────────────────
    "other": NicheDefinition(
        slug="other",
        display_name="Other",
        description="Does not clearly fit any category above",
        keywords=[],
    ),
}


# ── Derived constants ─────────────────────────────────────────────────────

VALID_NICHES: set[str] = set(NICHE_DEFINITIONS.keys())

# Logical groups for frontend UI
NICHE_GROUPS: dict[str, list[str]] = {
    "tech_ai": ["ai", "vibe-coding", "software-dev", "tech", "saas", "no-code", "cybersecurity", "science", "data-science"],
    "business_money": ["business", "startups", "ecommerce", "finance", "investing", "crypto", "real-estate", "freelance", "legal"],
    "marketing_growth": ["marketing", "personal-brand", "copywriting", "seo", "smm"],
    "creative": ["design", "photography", "video-production", "music", "art", "writing", "dance", "crafts"],
    "education_career": ["education", "career", "coaching", "languages", "self-development", "philosophy"],
    "health_wellness": ["health", "fitness", "mental-health", "psychology", "sexology", "nutrition", "yoga", "medicine", "biohacking"],
    "beauty_fashion": ["beauty", "fashion", "hair", "nails"],
    "lifestyle": ["lifestyle", "travel", "food", "home-decor", "sustainability", "gardening", "productivity", "automotive", "outdoor", "immigration", "fishing"],
    "family_relationships": ["parenting", "relationships", "family", "pregnancy", "wedding"],
    "spirituality_esoteric": ["astrology", "tarot", "numerology", "energy-practices", "human-design", "religion", "spirituality"],
    "entertainment": ["entertainment", "comedy", "memes", "gaming", "anime", "true-crime", "asmr", "books", "cinema"],
    "sports": ["sports", "martial-arts", "extreme-sports", "esports"],
    "pets_animals": ["pets", "dogs", "cats", "wildlife"],
    "news_society": ["news", "politics", "economics", "history", "military"],
    "other": ["other"],
}


# ── Disambiguation rules for LLM prompts ─────────────────────────────────

DISAMBIGUATION_RULES = """\
RULES:
- "vibe-coding" = building apps/products WITH AI tools (Cursor, Replit, v0, Bolt, Lovable). \
NOT "ai" (which is about AI tools themselves) and NOT "software-dev" (which is traditional coding)
- "ai" = reviewing/teaching/discussing AI tools and models. NOT building with them
- "software-dev" = traditional programming WITHOUT AI focus
- "data-science" = data analysis, BI, SQL, pandas, visualization. NOT "ai" (which is LLMs/generative AI)
- "saas" = building/growing SaaS products. NOT "business" (which is broader)
- "startups" = early-stage, fundraising, MVPs. NOT "business" (which is established companies)
- "investing" = stocks/ETFs/portfolio. NOT "crypto" (blockchain-specific) and NOT "finance" (personal money)
- "economics" = macroeconomics/global markets. NOT "finance" (which is personal money)
- "freelance" = freelancing/remote work. NOT "career" (which is corporate jobs)
- "copywriting" = writing/copy. NOT "marketing" (which is strategy/ads)
- "smm" = social media management/strategy. NOT "personal-brand" (which is building YOUR audience)
- "fitness" = exercise/gym/training. NOT "health" (which is general wellness)
- "nutrition" = diets/meal planning/macros. NOT "food" (which is recipes/restaurants/cooking)
- "yoga" = yoga/meditation practice. NOT "fitness" (which is gym/exercise) and NOT "spirituality" (which is beliefs)
- "medicine" = clinical/doctor/pharma content. NOT "health" (which is wellness/lifestyle)
- "biohacking" = nootropics/wearables/optimization. NOT "health" (which is general wellness)
- "mental-health" = clinical mental health: anxiety/depression/therapy/PTSD. NOT "psychology" (which is pop-psychology) \
and NOT "self-development" (which is growth/motivation)
- "psychology" = popular psychology: narcissism/attachment/EQ/manipulation/body language. \
NOT "mental-health" (which is clinical) and NOT "coaching" (which is professional service) \
and NOT "self-development" (which is habits/motivation)
- "sexology" = sex education/intimacy/sexual health. NOT "relationships" (which is dating/love) \
and NOT "psychology" (which is broader behavioral psychology)
- "self-development" = personal growth/habits/motivation. NOT "coaching" (which is professional service) \
and NOT "psychology" (which is understanding behavior) and NOT "mental-health" (which is clinical)
- "beauty" = makeup/cosmetics/skincare routines. NOT "fashion" (which is clothing/style)
- "hair" = hairstyling/haircare. NOT "beauty" (which is makeup/skincare)
- "nails" = nail art/manicure. NOT "beauty" (which is makeup/skincare)
- "fashion" = clothing/outfits/style. NOT "beauty" (which is makeup)
- "relationships" = dating/love/couples advice. NOT "family" (which is family life/household)
- "family" = family life/home/traditions. NOT "parenting" (which is child-rearing focused)
- "pregnancy" = pregnancy/birth/fertility. NOT "parenting" (which is after child is born)
- "astrology" = zodiac/horoscopes/natal charts. NOT "spirituality" (which is broader non-religious spirituality)
- "tarot" = card readings/divination. NOT "astrology" (which is zodiac-based)
- "numerology" = number meanings/angel numbers. NOT "astrology" and NOT "tarot"
- "energy-practices" = reiki/crystal healing/energy work. NOT "yoga" (which is physical practice)
- "human-design" = Human Design system/bodygraph/types. NOT "astrology" (which is zodiac) \
and NOT "energy-practices" (which is healing)
- "religion" = organized religion/faith/scripture. NOT "spirituality" (which is non-religious)
- "comedy" = comedy sketches/stand-up/humor. NOT "entertainment" (which is broader)
- "memes" = meme culture/internet humor. NOT "comedy" (which is performed humor)
- "anime" = anime/manga/cosplay. NOT "entertainment" (which is broader)
- "esports" = competitive gaming/tournaments. NOT "gaming" (which is casual/reviews)
- "martial-arts" = MMA/boxing/BJJ. NOT "sports" (which is mainstream sports) and NOT "fitness"
- "extreme-sports" = skateboard/surf/parkour. NOT "sports" (which is mainstream) and NOT "outdoor"
- "outdoor" = hiking/camping/nature. NOT "travel" (which is destinations/tourism)
- "automotive" = cars/car culture. NOT "tech" (which is gadgets/electronics)
- "science" = popular science/space/experiments. NOT "education" (which is teaching/courses)
- "crafts" = DIY/handmade/woodworking. NOT "art" (which is illustration/digital art)
- "writing" = creative writing/books authored. NOT "books" (which is reading/reviews)
- "books" = reading/book reviews/BookTok. NOT "writing" (which is authoring content)
- "wildlife" = wild animals/nature docs. NOT "pets" (which is domesticated animals)
- "philosophy" = philosophical content/stoicism/existentialism. NOT "self-development" (which is practical growth) \
and NOT "spirituality" (which is spiritual beliefs) and NOT "education" (which is teaching/courses)
- "immigration" = emigration/relocation/expat life. NOT "travel" (which is tourism/destinations)
- "fishing" = fishing/hunting content. NOT "outdoor" (which is hiking/camping)
- "cinema" = movie/TV reviews and analysis. NOT "entertainment" (which is broader) \
and NOT "video-production" (which is creating video) and NOT "books" (which is reading)
- If content spans multiple niches, choose the PRIMARY focus of this specific reel"""


# ── Prompt helpers (use DB cache when available, fallback to constants) ───

def niche_prompt_compact() -> str:
    """For Haiku / lightweight classification: 'slug: description' per line."""
    from app.core.niche_cache import niche_cache
    if niche_cache.is_loaded:
        return niche_cache.prompt_compact()
    return "\n".join(
        f"- {n.slug}: {n.description}"
        for n in NICHE_DEFINITIONS.values()
    )


def niche_prompt_detailed() -> str:
    """For GPT-4o / full classification: includes signal keywords."""
    from app.core.niche_cache import niche_cache
    if niche_cache.is_loaded:
        return niche_cache.prompt_detailed()
    lines = []
    for n in NICHE_DEFINITIONS.values():
        if n.keywords:
            lines.append(f"- {n.slug}: {n.description} (signals: {', '.join(n.keywords[:5])})")
        else:
            lines.append(f"- {n.slug}: {n.description}")
    return "\n".join(lines)


def niche_slugs_csv() -> str:
    """Comma-separated list of all niche slugs for inline use in prompts."""
    from app.core.niche_cache import niche_cache
    if niche_cache.is_loaded:
        return niche_cache.slugs_csv()
    return ", ".join(NICHE_DEFINITIONS.keys())
