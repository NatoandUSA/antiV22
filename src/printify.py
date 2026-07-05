"""Printify catalog helper: find products and their REAL US shipping costs.

Setup: in .env add   PRINTIFY_API_TOKEN=your_personal_access_token
(Printify -> My Profile -> Connections -> Generate token. Needs catalog.read.)

Commands:
  py main.py printify "pouch"        -> find matching products (blueprints)
  py main.py printify cost 1090      -> providers + US shipping for blueprint
"""
import os

import requests
from dotenv import load_dotenv

load_dotenv()

BASE = "https://api.printify.com/v1"
TOKEN = os.getenv("PRINTIFY_API_TOKEN")


def _get(path):
    if not TOKEN:
        raise SystemExit(
            "\nPRINTIFY_API_TOKEN missing from .env.\n"
            "Get one: printify.com -> My Profile -> Connections -> "
            "Generate token (catalog.read scope), then add to .env:\n"
            "  PRINTIFY_API_TOKEN=your_token\n"
        )
    resp = requests.get(
        f"{BASE}{path}",
        headers={"Authorization": f"Bearer {TOKEN}", "User-Agent": "etsy-agent"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def search_blueprints(query):
    q = query.lower()
    hits = [b for b in _get("/catalog/blueprints.json")
            if q in (b.get("title") or "").lower()]
    print(f"\n{len(hits)} Printify products match '{query}':\n")
    for b in hits[:25]:
        print(f"  id={b['id']:<6} {b['title']}  ({b.get('brand', '')})")
    if hits:
        print(f"\nNext: py main.py printify cost {hits[0]['id']}")
    else:
        print("Try a simpler word, e.g. 'bag', 'tote', 'pouch', 'tee'.")


def blueprint_costs(blueprint_id):
    bp = _get(f"/catalog/blueprints/{blueprint_id}.json")
    providers = _get(f"/catalog/blueprints/{blueprint_id}/print_providers.json")
    print(f"\n{bp['title']} ({bp.get('brand','')}) - print providers & US shipping:\n")
    print(f"{'provider':<28}{'US ship 1st':<13}{'US ship +1':<12}{'variants'}")
    for p in providers:
        try:
            ship = _get(f"/catalog/blueprints/{blueprint_id}"
                        f"/print_providers/{p['id']}/shipping.json")
            us = next((pr for pr in ship.get("profiles", [])
                       if "US" in pr.get("countries", [])), None)
            first = us["first_item"]["cost"] / 100 if us else None
            addl = us["additional_items"]["cost"] / 100 if us else None
            n_var = len(_get(f"/catalog/blueprints/{blueprint_id}"
                             f"/print_providers/{p['id']}/variants.json"
                             ).get("variants", []))
        except Exception as exc:
            print(f"{p['title'][:26]:<28}error: {exc}")
            continue
        f1 = f"${first:.2f}" if first is not None else "n/a"
        f2 = f"${addl:.2f}" if addl is not None else "n/a"
        print(f"{p['title'][:26]:<28}{f1:<13}{f2:<12}{n_var}")
    print("\nBase (blank product) cost: open this product in the Printify "
          "catalog UI,\nnote the cheapest suitable variant cost, and put "
          "base_cost + this shipping\ninto costs.csv. Then rerun: "
          "py main.py ideas")
