"""Heuristic trademark risk flagging. NOT legal advice.

HIGH    = contains a known brand/franchise term, OR an ambiguous brand word
          together with a co-signal that shows the brand is meant. Do not use.
CAUTION = slogan-like phrase, OR an ambiguous brand word with no co-signal
          (e.g. "frozen hot chocolate"). Apparel slogans are frequently
          trademarked - verify manually before designing:
          https://tmsearch.uspto.gov
OK      = no known flag found. Descriptive product keywords (e.g.
          "embroidered sweatshirt", "cross stitch monogram") are generally
          safe to use as keywords, but always keep the DESIGN itself original.

V35.5 L0 gate fixes (classification only - no ranking-math change):
  - BUG-2: bare "stitch" (an embroidery technique) is no longer a brand. Only
    Lilo & Stitch CONTEXT triggers HIGH, so cross/satin/chain stitch, stitch
    count, etc. are usable again.
  - BUG-3: everyday words that collide with brands (frozen, converse, cars,
    jordan, mario, chevy, ford, stitch, lilo, elsa) are context-required: HIGH
    only with a brand co-signal, otherwise a soft CAUTION/OK - never a hard
    block on the plain-English use.
  - BUG-4: concatenated multi-word brands (superbowl, starwars, babyyoda) are
    caught by normalising BOTH the brand and the text (spaces stripped) before
    comparing - previously only the text was normalised, so the space in the
    brand made the check always miss.
Real brand protection (disney, bluey, pokemon, nike, taylor swift, ...) is
unchanged.
"""

# Unambiguous brands / franchises -> always HIGH.
ALWAYS_HIGH = {
    # media / characters
    "disney", "mickey", "minnie", "marvel", "avengers", "spiderman",
    "spider man", "batman", "superman", "dc comics", "star wars", "yoda",
    "baby yoda", "grogu", "mandalorian", "harry potter", "hogwarts",
    "pokemon", "pikachu", "hello kitty", "sanrio", "barbie", "bluey",
    "paw patrol", "peppa", "minions", "grinch", "dr seuss", "sesame",
    "elmo", "nintendo", "zelda", "minecraft", "roblox",
    "fortnite", "moana", "encanto",
    "toy story", "lightning mcqueen", "winnie the pooh",
    "snoopy", "peanuts", "garfield", "simpsons", "rick and morty",
    "friends tv", "the office", "stranger things", "squid game",
    "one piece", "naruto", "dragon ball", "ghibli", "totoro", "sailor moon",
    # brands / retail
    "nike", "adidas", "gucci", "louis vuitton", "chanel",
    "starbucks", "coca cola", "pepsi", "mcdonalds", "jeep",
    "harley", "john deere", "carhartt", "stanley cup tumbler",
    "yeti", "lego", "crocs", "vans", "tiffany",
    # music / celebrities
    "taylor swift", "swiftie", "eras tour", "beyonce", "drake",
    "bad bunny", "travis kelce", "messi", "ronaldo", "lebron",
    # sports leagues / teams
    "nfl", "nba", "mlb", "nhl", "fifa", "olympics", "super bowl",
    "world cup", "cowboys", "yankees", "lakers", "packers", "chiefs",
    "red sox", "dodgers", "49ers", "eagles nfl",
    # institutions
    "fbi", "nasa", "fda",
}

# Ambiguous everyday words that are ALSO brands/characters. Flag HIGH only when a
# co-signal (the tuple) shows the brand is meant; otherwise fall back to `soft`
# (CAUTION = "verify", OK = treat as the ordinary word). This is what stops the
# engine hard-blocking core embroidery vocab ("cross stitch") and normal phrases
# ("frozen hot chocolate", "converse with god shirt").
#   word: (co_signals, soft_when_no_signal)
CONTEXT_REQUIRED = {
    "stitch":   (("lilo", "disney", "ohana", "experiment 626", "626"), "OK"),
    "lilo":     (("stitch", "disney", "ohana"), "OK"),
    "frozen":   (("elsa", "anna", "olaf", "arendelle", "disney", "movie"), "CAUTION"),
    "elsa":     (("frozen", "anna", "olaf", "arendelle", "disney"), "CAUTION"),
    "cars":     (("lightning", "mcqueen", "pixar", "disney", "movie",
                  "radiator springs"), "CAUTION"),
    "converse": (("shoes", "sneakers", "all star", "chuck taylor", "chucks"),
                 "CAUTION"),
    "jordan":   (("air jordan", "jumpman", "nike", "retro", "23"), "CAUTION"),
    "mario":    (("nintendo", "luigi", "bowser", "bros", "kart", "odyssey",
                  "super mario"), "CAUTION"),
    "chevy":    (("chevrolet", "silverado", "camaro", "corvette"), "CAUTION"),
    "ford":     (("mustang", "f150", "f 150", "raptor", "bronco", "f250"),
                 "CAUTION"),
}

# Back-compat alias: anything that referenced KNOWN_BRANDS still sees the full
# set of flagged terms (always-high + the ambiguous ones).
KNOWN_BRANDS = ALWAYS_HIGH | set(CONTEXT_REQUIRED)

SLOGAN_PRONOUNS = {
    "you", "your", "yours", "me", "my", "mine", "them", "they", "their",
    "we", "us", "our", "i", "im", "i'm", "aint", "ain't", "dont", "don't",
}

PRODUCT_WORDS = {
    "shirt", "tee", "tshirt", "t-shirt", "hoodie", "sweatshirt", "crewneck",
    "mug", "bag", "tote", "pouch", "necklace", "bracelet", "ring", "earring",
    "pendant", "ornament", "sticker", "print", "poster", "hat", "cap",
    "embroidered", "embroidery", "gift", "gifts", "custom", "personalized",
    "svg", "png", "digital", "womens", "mens", "kids", "baby", "vintage",
}


def _has_signal(signal, spaced_text, text_nospace):
    """A co-signal hits if it appears as a spaced phrase, or (for signals long
    enough to be collision-safe) as a space-stripped substring."""
    if f" {signal} " in spaced_text:
        return True
    sig_nospace = signal.replace(" ", "")
    return len(sig_nospace) > 4 and sig_nospace in text_nospace


def check(tag):
    """Return (risk, reason). risk in {'HIGH', 'CAUTION', 'OK'}."""
    raw = tag.strip().lower()
    t = " " + raw + " "
    t_nospace = raw.replace(" ", "")
    words = raw.replace("’", "'").split()
    wordset = set(words)

    # 1. Always-HIGH brands. Whole-word match, exact match, OR concatenated match
    #    for multi-word brands written without spaces (BUG-4: normalise BOTH the
    #    brand and the text, so "star wars" catches "starwars").
    for brand in ALWAYS_HIGH:
        brand_nospace = brand.replace(" ", "")
        if (f" {brand} " in t or raw == brand
                or (len(brand_nospace) > 7 and brand_nospace in t_nospace)):
            return "HIGH", f"known brand/franchise: '{brand}'"

    # 2. Context-required ambiguous words (BUG-2 + BUG-3). HIGH only with a brand
    #    co-signal; otherwise remember the soft fallback and keep scanning (a
    #    later word might still be a hard hit).
    soft = None
    for word, (signals, soft_default) in CONTEXT_REQUIRED.items():
        if word not in wordset:
            continue
        if any(_has_signal(s, t, t_nospace) for s in signals):
            return "HIGH", f"brand term '{word}' with brand context - do not use"
        if soft_default == "CAUTION":
            soft = "CAUTION"
    if soft == "CAUTION":
        return "CAUTION", ("word can collide with a brand - verify at "
                           "tmsearch.uspto.gov")

    # 3. Slogan pronoun / long non-descriptive phrase (unchanged behaviour).
    non_product = [w for w in words if w not in PRODUCT_WORDS]
    if any(w in SLOGAN_PRONOUNS for w in words):
        return "CAUTION", "slogan-like phrase - verify at tmsearch.uspto.gov"
    # Long, non-descriptive phrases can be registered slogans. Descriptive Etsy
    # long-tails (e.g. "gift for dog mom", "personalized dog name shirt") are 4
    # words but clearly product-descriptive, so require 5+ words / 4+ non-product
    # words here to avoid flagging every normal long-tail tag.
    if len(non_product) >= 4 and len(words) >= 5:
        return "CAUTION", "long phrase could be a registered slogan - verify manually"
    return "OK", ""
