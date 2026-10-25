"""Accuracy check: 20 made-up WhatsApp orders (Manglish, Malayalam, English) against the
sample price list. A line counts as correct only if Kurippu picks the right product AND quantity
with no human help ("ok" status). Run: python scripts/eval.py"""
import sys, time
from decimal import Decimal
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from kurippu import matcher, reader
from kurippu.store import Store

CASES = [
    ("chetta 2 kilo puttu podi, 6 mutta ayakkane", {"atta-loose": "2", "eggs": "6"}),
    ("1 Milma butter cheriya, 1 litre paal", {"butter-amul-100g": "1", "milk-amul-1l": "1"}),
    ("ചേച്ചി അര കിലോ പഞ്ചസാരയും ഒരു ലിറ്റർ പാലും വേണം", {"sugar": "0.5", "milk-amul-1l": "1"}),
    ("500 gm aval, 2 kg cheriya ulli", {"poha": "0.5", "onion": "2"}),
    ("1 dozen mutta please", {"eggs": "12"}),
    ("2 packet achappam and 1 Kannan Devan tea", {"parle-g-250g": "2", "tea-tata-250g": "1"}),
    ("onnara kilo urulakizhangu, ara kilo thakkali", {"potato": "1.5", "tomato": "0.5"}),
    ("1 kg cherupayar 2 kg matta ari", {"toor-dal": "1", "rice-kolam": "2"}),
    ("എനിക്ക് 2 കിലോ ഉരുളക്കിഴങ്ങും 1 കിലോ ചെറിയ ഉള്ളിയും വേണം", {"potato": "2", "onion": "1"}),
    ("1 kilo panchasara venam, 2 packet banana chips valiya venam", {"sugar": "1", "maggi-280g": "2"}),
    ("send 1 Kera coconut oil and 1 pack uppu", {"oil-sunflower-1l": "1", "salt-tata-1kg": "1"}),
    ("2 thayir, 1 bakery bread", {"dahi-400g": "2", "bread": "1"}),
    ("oru Milma butter valiya", {"butter-amul-500g": "1"}),
    ("3 banana chips cheriya", {"maggi-70g": "3"}),
    ("1 Eastern puttu podi packet", {"atta-aashirvaad-5kg": "1"}),
    ("kaal kilo jeerakam", {"jeera-100g": None}),      # 250 g asked, sold in 100 g packs -> should be flagged
    ("2 litre paal and 12 mutta", {"milk-amul-1l": "2", "eggs": "12"}),
    ("kariveppila 2 bunch, 1 kg thakkali", {"coriander": "2", "tomato": "1"}),
    ("1 palappam pack and 1 achappam pack", {"pav-6": "1", "parle-g-250g": "1"}),
    ("nanni chetta, payment cheythu", {}),
]

st = Store(":memory:")
right = total = flagged_ok = 0
times = []
for msg, want in CASES:
    t = time.perf_counter(); res = reader.read_order(msg); times.append(time.perf_counter() - t)
    lines = matcher.match_order(res["items"], st.skus(), {})
    got = {ln["sku"]: (ln["qty"], ln["status"]) for ln in lines if ln["sku"]}
    marks = []
    for sku, qty in want.items():
        total += 1
        g = got.get(sku)
        if qty is None:                       # we expect the shopkeeper to be asked
            ok = g is not None and g[1] == "check"
            flagged_ok += ok
        else:
            ok = g is not None and g[1] == "ok" and Decimal(g[0]) == Decimal(qty)
        right += ok
        marks.append(("✓" if ok else "✗") + f" {sku}")
    if not want:
        total += 1; ok = not res["is_order"]; right += ok; marks.append(("✓" if ok else "✗") + " not an order")
    print(f"{msg[:55]:55} | {', '.join(marks)}")
    for ln in lines:
        if ln["sku"] not in want or ln["status"] != "ok":
            print(f"{'':55} |   {ln['status']}: {ln['raw']} -> {ln['sku']} {ln['qty']} ({ln['note']})")
print(f"\nCorrect without help: {right}/{total} lines ({100*right/total:.0f}%). "
      f"Median read time {sorted(times)[len(times)//2]:.1f}s, model {reader.MODEL}.")
