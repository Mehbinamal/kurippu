# Kurippu (കുറിപ്പ്)

**WhatsApp orders → bills for nammude naadan kirana/bakery stores, on the shop's own laptop.**

A customer sends *"Chetta 2 kilo ari, 1 amul butter cheriya, 6 mutta, oru maggi"*. The shopkeeper pastes it into Kurippu and in about a second gets a checked order, a printable packing slip, a ready-to-send WhatsApp reply and a UPI QR for the exact amount. An open-weight model (**Gemma 4**, through Ollama) reads the Manglish, Malayalam, or English message. **Plain code** matches items to the shop's own price list and does all the money maths. Nothing leaves the computer.

![New order: items checked against the price list, live bill, WhatsApp reply](docs/order.jpg)
![Orders dashboard: today's sales, still to collect, one-click status](docs/orders.jpg)

Built for the Hacktoberfest 2026 DEV "Side Hustle" challenge.

## Why it runs locally

- **Customer data kadayil thanne irikkum.** Orders carry names, phone numbers and what each household buys. A hosted AI API would see all of it.
- **No per-order cost.** Oru cheriya kadayil rosam kure small orders varum. With the model on the laptop, reading an order costs nothing, so a ₹199/month tool can actually make money.
- **Works on patchy internet.** After the one-time model download, Kurippu needs no connection. Net poyalum bill adikkam.
- **Swappable.** Any Ollama model works: `KURIPPU_MODEL=qwen2.5vl:7b kurippu`.

## How it works

| Step | Who does it |
|---|---|
| Read the message: items, quantities, units, size words (*cheruthu/valuthu*), number words (*onnu, randu, ara, kaal, dozen*) | Gemma 4, constrained to a JSON schema, never shown prices |
| Match to the price list (aliases like *mutta → Eggs*, *ulli → Onion*), convert units (500 gm → 0.5 kg, 1 dozen → 12, 2 L → two 1 L packs) | Code (`rapidfuzz` + rules) |
| Prices, totals, rounding | Code (`Decimal`), from the price list only |
| Anything unsure (several sizes, no quantity, partial packs) is yellow; unknown items are red; out-of-stock items are left out and named in the reply | Code |
| Confirm, then print / copy reply / show UPI QR | The shopkeeper. Kurippu never sends a message by itself |
| Corrections are remembered (*"naranga" → Lemon*), and show up as customer words in the price list, where a wrong one can be deleted | Code (learned aliases) |

Also:
- **Searchable product picker**: type "mutta" or "but" to find Eggs or Amul Butter; suggestions first, keyboard friendly.
- **Live bill** that updates as you change products or quantities (the server still does the maths).
- **One-tap pack choices** when the customer asks for an amount that isn't whole packs (250 g of jeerakam sold in 100 g packs → "2 × 100 g" or "3 × 100 g").
- Items that aren't in the price list or are out of stock are **named in the reply** ("Kshamikkanam, ithu ippo stock illa: …").
- **WhatsApp "Export chat" .txt**: search it and click any message to bill it.
- **Orders dashboard**: orders and sales today, amount still to collect, filters, one-click New → Packed → Delivered → Paid, and "bill again".
- **Price list** with search, stock switches and an unsaved-changes bar; CSV import/export.
- Works on a **phone on the shop's Wi-Fi** (bottom navigation), **dark mode**, and no internet fonts or CDNs, so it stays fully offline.
- The model is **warmed up when the page opens**, so the first order reads fast.

## Run it

Requirements: Python 3.10+, [Ollama](https://ollama.com), about 7 GB of disk for the model. A GPU helps; CPU works, slower.

```powershell
ollama pull gemma4:e4b
git clone https://github.com/YourUsername/kurippu.git ; cd kurippu
python -m venv .venv ; .\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
kurippu
```

Open http://127.0.0.1:8765, add your shop name and UPI ID in **Shop**, edit the **Price list** (a sample kirana list is preloaded; its prices are made up), and paste an order. Click **Try a sample** for test messages.

Options: `KURIPPU_MODEL` (any Ollama model), `OLLAMA_HOST`, `KURIPPU_DB` (database path, default `data/kurippu.db`), `KURIPPU_HOST`, `KURIPPU_PORT`.

## How well it works (measured, with limits)

`python scripts/eval.py` runs 20 made-up orders (34 item lines) in Manglish, Malayalam, and English through the real model and the matcher. On an RTX 5060 laptop GPU with `gemma4:e4b`:

- **34 of 34 lines correct with no human help**: right product and right quantity, plus one "nandi/thank you" message correctly ignored.
- **Median read time 0.6 s** per order (the first order after start-up takes about 30 s while the model loads).
- One case is *meant* to need the shopkeeper: *"kaal kilo jeerakam"* (250 g) when jeerakam is sold in 100 g packs. Kurippu suggests 3 packs and marks it yellow instead of deciding.

Read this honestly: I wrote these 20 messages while building Kurippu, against a 26-item sample price list, so it is not a blind test. Real customers will write things it gets wrong. That is why every line is shown for review before billing, and why money is never left to the model.

## Known limits

- It makes an **order bill / estimate, not a GST tax invoice** (those need GSTIN and other mandatory fields).
- One message at a time; it does not merge several messages from the same customer.
- Text only for now. Gemma 4 also accepts audio, so voice-note orders (which Malayalis love to send) are the next step.
- The database (`data/kurippu.db`) holds customer names and phone numbers. It is git-ignored; back it up, don't share it.

## Tests

```powershell
python -m pytest
```

41 tests cover the matcher (aliases, units, pack sizes and one-tap pack choices, sizes, unknown and out-of-stock items, learned corrections), the bill maths (prices only from the price list, rounding, bad quantities, NaN/infinite values), Indian rupee formatting, the UPI link and UPI ID check, WhatsApp export parsing (system and media lines skipped), price-list validation, model-output validation and retry, preview vs. saved bills, and end-to-end API runs with a fake model.

## Layout

```
kurippu/
  reader.py    Gemma 4 via Ollama: prompt, JSON schema, validation, one retry
  matcher.py   price-list matching, unit and pack maths, statuses
  billing.py   totals, WhatsApp reply, wa.me link, UPI QR
  whatsapp.py  "Export chat" .txt parser
  store.py     SQLite: shop, price list, learned aliases, orders
  app.py       FastAPI app; static/index.html is the counter page
data/sample_pricelist.csv
scripts/eval.py, scripts/try_samples.py
tests/
```

## License

MIT