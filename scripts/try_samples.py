"""Quick manual check: run a few sample orders through the real model and the matcher."""
import sys, time
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))
from kurippu import reader, matcher
from kurippu.store import Store

st = Store(":memory:")
for msg in ["chetta 2 kilo puttu podi, 1 Milma butter cheriya, 6 mutta, oru packet banana chips",
            "ചേച്ചി അര കിലോ പഞ്ചസാരയും ഒരു ലിറ്റർ പാലും വേണം",
            "Hi, please send 500 gm aval, 2 kg cheriya ulli, 1 dozen mutta and Kannan Devan tea",
            "1 packet achappam, thayir, paneer and kurachu kariveppila",
            "nanni chetta 🙏"]:
    t = time.time(); r = reader.read_order(msg)
    print(f"--- {msg}  ({time.time()-t:.1f}s) is_order={r['is_order']}")
    for ln in matcher.match_order(r["items"], st.skus(), {}):
        print("  ", ln["status"], "|", ln["raw"], "->", ln["sku"], ln["qty"], "|", ln["note"])
