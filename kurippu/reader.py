"""Read a WhatsApp order with a local open-weight model (Gemma 4 via Ollama).

The model only extracts what the customer asked for. It never sees prices and
never produces totals; matching and money are handled by plain code.
"""

import json
import os
import time
import urllib.error
import urllib.request

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
if not OLLAMA_HOST.startswith("http"):
    OLLAMA_HOST = "http://" + OLLAMA_HOST
MODEL = os.environ.get("KURIPPU_MODEL", "gemma4:e4b")
UNITS = ["kg", "g", "l", "ml", "pc", "pack", "dozen"]
MAX_ITEMS = 40

SCHEMA = {
    "type": "object",
    "properties": {
        "is_order": {"type": "boolean"},
        "items": {
            "type": "array",
            "maxItems": MAX_ITEMS,
            "items": {
                "type": "object",
                "properties": {
                    "raw": {"type": "string", "maxLength": 80},
                    "item": {"type": "string", "maxLength": 60},
                    "qty": {"type": ["number", "null"]},
                    "unit": {"type": ["string", "null"], "enum": UNITS + [None]},
                    "size": {"type": ["string", "null"], "enum": ["small", "big", None]},
                },
                "required": ["raw", "item", "qty", "unit", "size"],
            },
        },
    },
    "required": ["is_order", "items"],
}

SYSTEM = """You read grocery orders that customers send to a small Kerala grocery shop on WhatsApp.
Messages can be in Malayalam, Manglish (Malayalam written in Latin script), English or a mix, in Malayalam or Latin script.

Return JSON only. For every item the customer asks for, give:
- raw: the customer's own words for that item, copied exactly.
- item: a short lowercase English name for the product, keeping any brand (e.g. "milma butter", "matta rice", "eggs").
- qty: a number, or null if no quantity is given.
- unit: one of kg, g, l, ml, pc, pack, dozen, or null if none is said.
- size: "small" for cheriya/cheruthu/ചെറിയ/small, "big" for valiya/valuthu/വലിയ/large, otherwise null.

Number words: onnu/oru=1, randu=2, moonnu=3, naalu=4, anchu=5, aaru=6, pathu=10,
onnara=1.5, ara=0.5, kaal=0.25, mukkaal=0.75, randara=2.5, dozen=1 dozen.
"kaal" before a unit word means 0.25 (kaal kilo = 0.25 kg).
kilo/kg -> kg, gram/gm -> g, litre/ltr -> l, packet/pkt -> pack, piece/ennam -> pc.

Never invent items, never add prices. If the message is not an order (greeting, thanks, a question, payment
confirmation), return {"is_order": false, "items": []}."""

EXAMPLES = [
    ("chetta 2 kilo puttu podi, 1 Milma butter cheriya, 6 mutta ayakkane",
     {"is_order": True, "items": [
         {"raw": "2 kilo puttu podi", "item": "puttu podi", "qty": 2, "unit": "kg", "size": None},
         {"raw": "1 Milma butter cheriya", "item": "milma butter", "qty": 1, "unit": None, "size": "small"},
         {"raw": "6 mutta", "item": "eggs", "qty": 6, "unit": "pc", "size": None}]}),
    ("ചേച്ചി അര കിലോ പഞ്ചസാരയും ഒരു ലിറ്റർ പാലും വേണം",
     {"is_order": True, "items": [
         {"raw": "അര കിലോ പഞ്ചസാരയും", "item": "sugar", "qty": 0.5, "unit": "kg", "size": None},
         {"raw": "ഒരു ലിറ്റർ പാലും", "item": "milk", "qty": 1, "unit": "l", "size": None}]}),
    ("nanni chetta, paisa ayachu 🙏", {"is_order": False, "items": []}),
]


class ReaderError(RuntimeError):
    pass


def _messages(text):
    msgs = [{"role": "system", "content": SYSTEM}]
    for user, answer in EXAMPLES:
        msgs.append({"role": "user", "content": user})
        msgs.append({"role": "assistant", "content": json.dumps(answer, ensure_ascii=False)})
    msgs.append({"role": "user", "content": text})
    return msgs


def _post(path, payload, timeout=300):
    req = urllib.request.Request(
        OLLAMA_HOST + path, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:300]
        raise ReaderError(f"Ollama returned {e.code}: {body}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ReaderError(f"Cannot reach Ollama at {OLLAMA_HOST}. Is it running? ({e})") from None


def ollama_chat(text, model=MODEL):
    payload = {
        "model": model, "messages": _messages(text), "format": SCHEMA, "stream": False,
        "think": False, "keep_alive": "30m", "options": {"temperature": 0, "num_predict": 1500},
    }
    try:
        data = _post("/api/chat", payload)
    except ReaderError as e:
        if "think" not in str(e).lower():
            raise
        payload.pop("think")
        data = _post("/api/chat", payload)
    return data.get("message", {}).get("content", "")


def validate(content):
    """Turn model output into a clean dict. Raises ValueError if unusable."""
    data = json.loads(content)
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise ValueError("expected an object with an items list")
    items = []
    for it in data["items"][:MAX_ITEMS]:
        if not isinstance(it, dict):
            continue
        name = str(it.get("item") or "").strip()[:60]
        raw = str(it.get("raw") or name).strip()[:80]
        if not name and not raw:
            continue
        qty = it.get("qty")
        try:
            qty = float(qty) if qty is not None else None
        except (TypeError, ValueError):
            qty = None
        if qty is not None and not (0 < qty <= 1000):
            qty = None
        unit = it.get("unit")
        unit = unit if unit in UNITS else None
        size = it.get("size") if it.get("size") in ("small", "big") else None
        items.append({"raw": raw, "item": name.lower(), "qty": qty, "unit": unit, "size": size})
    is_order = bool(data.get("is_order", bool(items))) and bool(items)
    return {"is_order": is_order, "items": items if is_order else []}


def read_order(text, chat=ollama_chat):
    """Extract items from an order message. Retries once if the output is unusable."""
    text = (text or "").strip()
    if not text:
        return {"is_order": False, "items": [], "ms": 0}
    if len(text) > 4000:
        raise ReaderError("Message is too long (over 4000 characters). Paste one order at a time.")
    start = time.perf_counter()
    last_error = None
    for _ in range(2):
        content = chat(text)
        try:
            result = validate(content)
            result["ms"] = round((time.perf_counter() - start) * 1000)
            return result
        except (ValueError, json.JSONDecodeError) as e:
            last_error = e
    raise ReaderError(f"The model's answer could not be understood twice ({last_error}). Try again.")


def warmup(model=MODEL):
    """Load the model into memory so the shopkeeper's first order is fast."""
    try:
        _post("/api/generate", {"model": model, "prompt": "", "keep_alive": "30m"}, timeout=180)
        return True
    except ReaderError:
        return False


def health():
    try:
        req = urllib.request.Request(OLLAMA_HOST + "/api/tags")
        with urllib.request.urlopen(req, timeout=5) as resp:
            names = [m.get("name") for m in json.loads(resp.read()).get("models", [])]
        wanted = {MODEL, MODEL + ":latest"} if ":" not in MODEL else {MODEL}
        return {"ollama": True, "model": MODEL, "model_installed": bool(wanted & set(names))}
    except (urllib.error.URLError, OSError, ValueError):
        return {"ollama": False, "model": MODEL, "model_installed": False}
