"""Word lists for execution_action.py's specificity check (Patch 4 Stage 2).

Pure data, no logic, so the vocabulary can be reviewed/tuned without touching
the decision code. Each set/dict below is either single words (matched as a
whole token) or phrases (matched as a contiguous token sequence) -- never a
raw substring, see execution_action._hit_category.

Tiering follows the owner-approved two-axis model: STRONG categories are
sufficient alone to call a keyword actionable; MEDIUM categories need a
second, distinct MEDIUM category before they count (see
execution_action.derive_execution_action). Product subtype and weak generic
modifiers never count toward market-angle strength on their own -- they are
informational only.
"""

# --- STRONG (any one hit alone -> STRONG_ANGLE) -----------------------------

STRONG_PROFESSION_ROLE = {
    "nurse", "teacher", "doctor", "vet", "veterinarian", "firefighter",
    "police", "officer", "engineer", "coach", "trucker", "farmer", "chef",
    "waitress", "mailman", "postal", "electrician", "plumber", "mechanic",
    "realtor", "lawyer", "accountant", "dentist", "therapist", "counselor",
    "pilot", "soldier", "veteran", "military", "cna", "rn",
    "bride", "groom", "bridesmaid", "groomsman", "maid of honor",
    "man of honor", "best man", "ring bearer", "flower girl",
}

OCCASION = {
    "christmas", "xmas", "halloween", "thanksgiving", "easter", "valentine",
    "valentines", "birthday", "wedding", "bridal", "bachelorette",
    "bachelor", "anniversary", "graduation", "retirement", "baby shower",
    "babyshower", "newborn", "engagement", "reunion", "housewarming",
    "mothers day", "fathers day", "new year", "newyear", "back to school",
    "memorial day", "veterans day", "fourth of july", "independence day",
    "st patricks", "hanukkah", "diwali",
}

USE_CASE = {
    "travel", "gym", "workout", "work", "school", "office", "outdoor",
    "camping", "hiking", "commute", "carry on", "carryon", "everyday",
    "daily", "beach", "vacation", "road trip", "roadtrip", "gaming",
    "kitchen", "bathroom", "bedroom", "desk", "wfh",
}

# --- MEDIUM (needs a second, distinct MEDIUM category to become STRONG) ----

GENERIC_AUDIENCE = {
    "mom", "mum", "dad", "mother", "father", "wife", "husband",
    "boyfriend", "girlfriend", "fiance", "fiancee", "grandma", "grandpa",
    "nana", "papa", "mimi", "gigi", "sister", "brother", "aunt", "uncle",
    "cousin", "coworker", "boss", "student", "graduate", "principal",
    "librarian", "babysitter", "nanny", "men", "women", "man", "woman",
    "kids", "kid", "child", "children", "toddler", "baby", "teen", "teens",
    "family", "couple", "couples",
}

PERSONALIZATION = {
    "personalized", "personalised", "custom", "customized", "monogram",
    "monogrammed", "name", "names", "initial", "initials", "engraved",
    "engrave",
}

MOTIF = {
    "dog", "cat", "horse", "fishing", "hunting", "golf", "football",
    "basketball", "baseball", "soccer", "hockey", "floral", "sunflower",
    "unicorn", "dinosaur", "coffee", "wine", "beer", "yoga", "running",
    "gardening", "reading", "music", "guitar", "piano", "gaming", "anime",
    "cars", "trucks", "motorcycle", "boat", "mountain", "butterfly",
    "mushroom", "skull", "western", "cowboy", "cowgirl", "farmhouse",
    "nautical", "tropical", "plaid", "leopard", "camo",
}

GENERIC_GIFT = {"gift", "gifts"}

# --- informational only, never counted toward angle strength ---------------

WEAK_GENERIC_MODIFIERS = {
    "funny", "cute", "trendy", "vintage", "retro", "cool", "best", "unique",
    "boho", "aesthetic", "cozy", "minimalist", "sassy", "groovy",
    "cottagecore", "popular", "new", "nice", "awesome", "great", "cheap",
    "affordable", "quality", "premium", "embroidered",
}

# subtype vocab: only the product families that actually show up in the
# data -- an unrecognized bare noun is left blank, not guessed.
SUBTYPE_BY_FAMILY = {
    "bag": {"duffel", "tote", "crossbody", "backpack", "weekender",
            "messenger", "fanny pack", "belt bag", "sling", "drawstring",
            "makeup bag", "diaper bag", "lunch bag", "gym bag"},
    "shirt": {"crewneck", "v-neck", "vneck", "raglan", "henley", "polo",
              "graphic tee", "long sleeve", "short sleeve", "tank top"},
    "mug": {"travel mug", "coffee mug", "camp mug", "enamel mug"},
    "tumbler": {"skinny tumbler", "stanley", "insulated tumbler"},
    "blanket": {"throw blanket", "weighted blanket", "sherpa", "fleece"},
    "ornament": {"acrylic ornament", "wood ornament", "flat ornament"},
}
