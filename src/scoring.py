"""Opportunity score: demand x momentum / competition. Higher = better."""


def opportunity_score(avg_interest, momentum_pct, competition):
    demand = max(avg_interest or 0, 1)
    # Rising niches get boosted, falling ones penalized (floor at -50%)
    momentum_factor = 1 + max(momentum_pct or 0, -50) / 100
    # Unknown competition assumes a crowded 1000 listings (be pessimistic)
    comp = max(competition if competition else 1000, 1)
    return round(demand * momentum_factor * 1000 / comp, 2)
