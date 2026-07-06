"""Turn the ChatGPT image prompts into real PNGs via the OpenAI Images API.

Reads the JSON sidecar written by the daily run
(reports/<date>/design/chatgpt_prompts_<date>.json) and calls the OpenAI API
for each prompt. Needs OPENAI_API_KEY in .env and the openai package
(py -m pip install openai).

Usage:
  py main.py images                 -> list products + image counts (NO API calls)
  py main.py images --product 1     -> generate the 6 images for product #1
  py main.py images --all           -> generate every image (this costs money)
  py main.py images --product 1 --kind design   -> only the 5 design concepts
  py main.py images --product 1 --kind mockup    -> only the lifestyle mockup

Options:
  --date YYYY-MM-DD   which run to use (default: newest generated)
  --kind design|mockup|all           (default: all)
  --limit N           stop after N images (safety cap)
  --model gpt-image-1|dall-e-3       (default: gpt-image-1)
  --quality low|medium|high          (default: medium; mapped per model)
  --out DIR           output folder (default: <run>/design/images)
"""
import base64
import json
import os
from pathlib import Path

DEFAULT_MODEL = "gpt-image-1"
# gpt-image-1 supports these sizes directly; dall-e-3 uses 1024x1792 for tall.
DALLE_SIZE = {"1024x1024": "1024x1024", "1024x1536": "1024x1792",
              "1536x1024": "1792x1024"}


def _parse_args(args):
    opt = {"date": None, "product": None, "all": False, "kind": "all",
           "limit": None, "model": DEFAULT_MODEL, "quality": "medium",
           "out": None}
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--all":
            opt["all"] = True
        elif a in ("--product", "--date", "--kind", "--limit", "--model",
                   "--quality", "--out"):
            if i + 1 >= len(args):
                raise SystemExit(f"Missing value after {a}")
            val = args[i + 1]
            key = a[2:]
            opt[key] = int(val) if key in ("product", "limit") else val
            i += 1
        else:
            raise SystemExit(f"Unknown option: {a}\n\n{__doc__}")
        i += 1
    return opt


def _find_json(day=None):
    """Locate the prompt JSON. daily archives reports/<day> into the run
    folder and mirrors this file to reports/latest, so prefer that; fall back
    to the newest match anywhere (including run archives)."""
    root = Path("reports")

    def _newest(pattern):
        cands = [p for p in root.glob(pattern)
                 if not any("selftest" in part for part in p.parts)]
        return max(cands, key=lambda p: p.stat().st_mtime) if cands else None

    if day:
        return _newest(f"**/chatgpt_prompts_{day}.json")
    latest = sorted((root / "latest").glob("chatgpt_prompts_*.json"))
    if latest:
        return latest[-1]
    return _newest("**/chatgpt_prompts_*.json")


def _select(items, opt):
    sel = items
    if opt["product"] is not None:
        sel = [x for x in sel if x["product_index"] == opt["product"]]
    if opt["kind"] in ("design", "mockup"):
        sel = [x for x in sel if x["kind"] == opt["kind"]]
    if opt["limit"] is not None:
        sel = sel[:opt["limit"]]
    return sel


def _list_mode(items, json_path):
    print(f"Prompts from: {json_path}")
    by_product = {}
    for x in items:
        by_product.setdefault(x["product_index"], []).append(x)
    print(f"\n{len(items)} image prompts across {len(by_product)} products:\n")
    for idx in sorted(by_product):
        rows = by_product[idx]
        d = sum(1 for r in rows if r["kind"] == "design")
        m = sum(1 for r in rows if r["kind"] == "mockup")
        print(f"  #{idx}  {rows[0]['product']}  "
              f"({d} design + {m} mockup = {len(rows)} images)")
    print("\nNothing generated yet (list mode makes no API calls).")
    print("Generate with:")
    print("  py main.py images --product 1        # one product (6 images)")
    print("  py main.py images --product 1 --kind design   # 5 concepts only")
    print("  py main.py images --all              # every image (costs money)")


def _client(model):
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        print("OPENAI_API_KEY is not set.")
        print("Fix: add a line to your .env file:")
        print("  OPENAI_API_KEY=sk-...your key...")
        print("Get a key at https://platform.openai.com/api-keys")
        raise SystemExit(1)
    try:
        from openai import OpenAI
    except ImportError:
        print("The openai package is not installed.")
        print("Fix: py -m pip install openai")
        raise SystemExit(1)
    return OpenAI(api_key=key)


def _generate_one(client, item, model, quality):
    size = item["size"]
    kwargs = {"model": model, "prompt": item["prompt"], "n": 1}
    if model == "dall-e-3":
        kwargs["size"] = DALLE_SIZE.get(size, "1024x1024")
        kwargs["quality"] = "hd" if quality == "high" else "standard"
        kwargs["response_format"] = "b64_json"
    else:  # gpt-image-1
        kwargs["size"] = size
        kwargs["quality"] = quality  # low | medium | high | auto
    resp = client.images.generate(**kwargs)
    data = resp.data[0]
    b64 = getattr(data, "b64_json", None)
    if not b64:
        raise RuntimeError("API returned no image data (b64_json empty)")
    return base64.b64decode(b64)


def run_images(args):
    from dotenv import load_dotenv
    load_dotenv()
    opt = _parse_args(args)

    json_path = _find_json(opt["date"])
    if not json_path:
        where = f" for {opt['date']}" if opt["date"] else ""
        print(f"No ChatGPT prompt file found{where}.")
        print("Run `py main.py daily` first to generate the prompts.")
        raise SystemExit(1)
    data = json.loads(json_path.read_text(encoding="utf-8"))
    items = data.get("items", [])

    # Default (no --product and no --all) = safe list mode, no API calls.
    if opt["product"] is None and not opt["all"]:
        _list_mode(items, json_path)
        return

    sel = _select(items, opt)
    if not sel:
        print("No prompts match that selection. Try `py main.py images` "
              "(list mode) to see what's available.")
        raise SystemExit(1)

    out_dir = Path(opt["out"]) if opt["out"] else json_path.parent / "images"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Generating {len(sel)} image(s) with {opt['model']} "
          f"(quality={opt['quality']}) -> {out_dir}")
    print("Note: each image is a paid OpenAI API call.\n")
    client = _client(opt["model"])

    ok, failed = 0, 0
    manifest = []
    for j, item in enumerate(sel, 1):
        tag = f"#{item['product_index']} {item['label']}"
        try:
            png = _generate_one(client, item, opt["model"], opt["quality"])
            dest = out_dir / item["filename"]
            dest.write_bytes(png)
            ok += 1
            manifest.append(f"{item['filename']}\t{item['product']}\t{tag}")
            print(f"  [{j}/{len(sel)}] OK   {item['filename']}  ({tag})")
        except Exception as exc:
            failed += 1
            print(f"  [{j}/{len(sel)}] FAIL {tag}: {exc}")
    if manifest:
        (out_dir / "manifest.txt").write_text(
            "\n".join(manifest) + "\n", encoding="utf-8")
    print(f"\nDone: {ok} saved, {failed} failed. Folder: {out_dir}")
    if ok:
        print("These are concept images (not print-ready). Pick the winners, "
              "then rebuild the final 4500x5400 transparent PNG for the "
              "supplier.")
