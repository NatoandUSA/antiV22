"""Heuristic trademark risk flagging. NOT legal advice.

HIGH    = contains a known brand/franchise term. Do not use.
CAUTION = slogan-like phrase; apparel slogans are frequently trademarked.
          Verify manually before designing: https://tmsearch.uspto.gov
OK      = no known flag found. Descriptive product keywords (e.g.
          "embroidered sweatshirt") are generally safe to use as keywords,
          but always keep the DESIGN itself original.
"""

KNOWN_BRANDS = {
    # media / characters
    "disney", "mickey", "minnie", "marvel", "avengers", "spiderman",
    "spider man", "batman", "superman", "dc comics", "star wars", "yoda",
    "baby yoda", "grogu", "mandalorian", "harry potter", "hogwarts",
    "pokemon", "pikachu", "hello kitty", "sanrio", "barbie", "bluey",
    "paw patrol", "peppa", "minions", "grinch", "dr seuss", "sesame",
    "elmo", "mario", "nintendo", "zelda", "minecraft", "roblox",
    "fortnite", "stitch", "lilo", "frozen", "elsa", "moana", "encanto",
    "toy story", "cars movie", "lightning mcqueen", "winnie the pooh",
    "snoopy", "peanuts", "garfield", "simpsons", "rick and morty",
    "friends tv", "the office", "stranger things", "squid game",
    "one piece", "naruto", "dragon ball", "ghibli", "totoro", "sailor moon",
    # brands / retail
    "nike", "adidas", "jordan", "gucci", "louis vuitton", "chanel",
    "starbucks", "coca cola", "pepsi", "mcdonalds", "jeep", "ford",
    "chevy", "harley", "john deere", "carhartt", "stanley cup tumbler",
    "yeti", "lego", "crocs", "vans", "converse", "tiffany",
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


def check(tag):
    """Return (risk, reason). risk in {'HIGH', 'CAUTION', 'OK'}."""
    t = " " + tag.strip().lower() + " "
    for brand in KNOWN_BRANDS:
        if f" {brand} " in t or t.strip() == brand or brand in t.replace(" ", "") and len(brand) > 7:
            return "HIGH", f"known brand/franchise: '{brand}'"

    words = tag.lower().replace("'", "'").split()
    non_product = [w for w in words if w not in PRODUCT_WORDS]
    if any(w in SLOGAN_PRONOUNS for w in words):
        return "CAUTION", "slogan-like phrase - verify at tmsearch.uspto.gov"
    if len(non_product) >= 3 and len(words) >= 4:
        return "CAUTION", "phrase could be a registered slogan - verify manually"
    return "OK", ""
