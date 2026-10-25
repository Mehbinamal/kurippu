# Kurippu (കുറിപ്പ്)

**WhatsApp orders → bills for nammude naadan grocery/bakery kadakal, on the shop's own laptop.**

A customer sends *"Chetta 2 kilo matta ari, 1 Milma butter cheriya, 6 mutta, oru packet banana chips"*. The shopkeeper pastes it into Kurippu and in about a second gets a checked order, a printable packing slip, a ready-to-send WhatsApp reply and a UPI QR for the exact amount. An open-weight model (**Gemma 4**, through Ollama) reads the Manglish, Malayalam, or English message. **Plain code** matches items to the shop's own price list and does all the money maths. The order-reading model runs locally; message content is not sent to an AI provider.

![New order: items checked against the price list, live bill, WhatsApp reply](docs/order.jpg)
![Orders dashboard: today's sales, still to collect, one-click status](docs/orders.jpg)

Built for the Hacktoberfest 2026 DEV "Side Hustle" challenge.

## Why it runs locally

- **Customer data kadayil thanne irikkum.** Orders carry names, phone numbers and what each household buys. The reader uses a local model rather than a hosted AI API.
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
| Confirm, then print / copy reply / show UPI QR | The shopkeeper |
| Corrections are remembered (*"kariveppila" → Curry Leaves*), and show up as customer words in the price list, where a wrong one can be deleted | Code (learned aliases) |

Also:
- **Searchable product picker**: type "mutta" or "Milma" to find Eggs or Milma Butter; suggestions first, keyboard friendly.
- **Live bill** that updates as you change products or quantities (the server still does the maths).
- **One-tap pack choices** when the customer asks for an amount that isn't whole packs (250 g of jeerakam sold in 100 g packs → "2 × 100 g" or "3 × 100 g").
- Items that aren't in the price list or are out of stock are **named in the reply** ("Kshamikkanam, ithu ippo stock illa: …").
- **WhatsApp "Export chat" .txt**: search it and click any message to bill it.
- **Live WhatsApp inbox** (optional): link the shop's WhatsApp account once, receive direct text orders in Kurippu, review the bill, and send the edited reply with one click. Group chats and media messages are skipped; Kurippu never auto-bills or auto-replies.
- **Orders dashboard**: orders and sales today, amount still to collect, filters, one-click New → Packed → Delivered → Paid, and "bill again".
- **Price list** with search, stock switches and an unsaved-changes bar; CSV import/export.
- Works on a **phone on the shop's Wi-Fi** (bottom navigation), **dark mode**, and no internet fonts or CDNs. The core billing workflow works offline; live WhatsApp needs an internet connection.
- The model is **warmed up when the page opens**, so the first order reads fast.

## Run it

One-time requirements: Python 3.10+, Node.js 18+, and [Ollama](https://ollama.com). Install Ollama and download the model once:

```sh
ollama pull gemma4:e4b
```

Download or copy this project folder onto the shop computer. Then start Kurippu:

- **Windows:** double-click `Start-Kurippu.bat`.
- **Linux:** double-click `start-kurippu.sh` (choose **Run** if asked), or run `./start-kurippu.sh`.
- **Mac / other:** run `python3 start.py` from this folder.

The first start installs the app and WhatsApp bridge automatically and creates a private local connection token. This can take a few minutes and needs internet. It opens Kurippu in your browser; keep the launcher window open while using the app, and press Ctrl+C in that window to stop it. Later starts reuse the installed files and WhatsApp login. In Kurippu, add your shop name and UPI ID in **Shop**, then edit the sample **Price list** (the sample prices are made up).

If you only want the manual-order app, run `kurippu` as described in the developer setup below without starting the WhatsApp bridge.

### Developer setup (optional)

To run just the Python app directly, install it with `pip install -e .` and start it using `kurippu`. To run the live WhatsApp bridge separately, follow the manual setup below.

Options: `KURIPPU_MODEL` (any Ollama model), `OLLAMA_HOST`, `KURIPPU_DB` (database path, default `data/kurippu.db`), `KURIPPU_HOST`, `KURIPPU_PORT`.

### Optional: live WhatsApp inbox

The bridge uses `whatsapp-web.js` and WhatsApp Web, not the official WhatsApp Business API. It is a community-maintained, unofficial integration: WhatsApp Web changes can break it, and WhatsApp may restrict accounts for automated use. Use only an account you control, keep message volume low, and prefer the official WhatsApp Business Platform for production or business-critical use.

Install the bridge dependencies once:

```sh
npm --prefix wa-bridge install
```

The launcher above creates and shares a private token automatically. For manual development only, choose a long random token and set the same value in **both** terminals. Do not commit or share it. Start Kurippu in the first terminal:

```sh
export KURIPPU_WA_TOKEN='paste-the-same-long-random-token-in-both-terminals'
kurippu
```

In another terminal, set that same token and start the bridge:

```sh
export KURIPPU_WA_TOKEN='paste-the-same-long-random-token-in-both-terminals'
npm --prefix wa-bridge start
```

Open **WhatsApp** in Kurippu and scan the pairing QR from WhatsApp on the keeper's phone (**Linked devices → Link a device**). The login session is saved in `wa-bridge/.wwebjs_auth/`, so it normally stays linked after restarting. Keep the QR and session folder private; do not commit or copy the session to another machine. Incoming messages are stored in the local Kurippu database; before sending, the bridge resolves newer WhatsApp LID-format chat IDs to their phone-number chat IDs. The bridge also applies a compatibility fix for a current `whatsapp-web.js` media-send bug when sending a UPI QR with the reply. Only direct text chats are currently accepted; the keeper must review each message, create the bill, and press **Send on WhatsApp**. A failed send can be ambiguous, so check the chat before retrying.

The bridge listens only on `127.0.0.1`. Kurippu itself has no user login; if you bind it to a network interface for phone access, use only a trusted shop network because the app exposes the shop's customer/order data to devices on that network.

On some Linux systems, AppArmor blocks Chromium's user-namespace sandbox and the bridge exits with `No usable sandbox`. First prefer fixing the host's Chromium/AppArmor sandbox configuration. As a less-safe workaround on a trusted, isolated computer only, start the launcher with `WA_CHROME_NO_SANDBOX=1 python3 start.py` (or the manual bridge with `WA_CHROME_NO_SANDBOX=1 npm --prefix wa-bridge start`); this disables Chromium's security sandbox. The setting is opt-in.

## How well it works (measured, with limits)

`python scripts/eval.py` runs 20 made-up orders (34 item lines) in Manglish, Malayalam, and English through the real model and the matcher. On an RTX 5060 laptop GPU with `gemma4:e4b`:

- **34 of 34 lines correct with no human help**: right product and right quantity, plus one "nandi/thank you" message correctly ignored.
- **Median read time 0.6 s** per order (the first order after start-up takes about 30 s while the model loads).
- One case is *meant* to need the shopkeeper: *"kaal kilo jeerakam"* (250 g) when jeerakam is sold in 100 g packs. Kurippu suggests 3 packs and marks it yellow instead of deciding.

Read this honestly: I wrote these 20 messages while building Kurippu, against a 26-item sample price list, so it is not a blind test. Real customers will write things it gets wrong. That is why every line is shown for review before billing, and why money is never left to the model.

## Known limits

- It makes an **order bill / estimate, not a GST tax invoice** (those need GSTIN and other mandatory fields).
- One message at a time; it does not merge several messages from the same customer.
- Live WhatsApp support is text-only and does not read group chats; it requires the bridge to remain running and is not an official WhatsApp API.
- Text only for now. Gemma 4 also accepts audio, so voice-note orders (which Malayalis love to send) are the next step.
- The database (`data/kurippu.db`) holds customer names and phone numbers. It is git-ignored; back it up, don't share it.

## Tests

```powershell
python -m pytest
```

44 tests cover the matcher (aliases, units, pack sizes and one-tap pack choices, sizes, unknown and out-of-stock items, learned corrections), the bill maths (prices only from the price list, rounding, bad quantities, NaN/infinite values), Indian rupee formatting, the UPI link and UPI ID check, WhatsApp export parsing (system and media lines skipped), price-list validation, model-output validation and retry, preview vs. saved bills, and end-to-end API runs with a fake model.

## Layout

```
kurippu/
  reader.py    Gemma 4 via Ollama: prompt, JSON schema, validation, one retry
  matcher.py   price-list matching, unit and pack maths, statuses
  billing.py   totals, WhatsApp reply, wa.me link, UPI QR
  whatsapp.py  "Export chat" .txt parser
  wa_live.py   WhatsApp inbox, pairing status and keeper-triggered replies
  store.py     SQLite: shop, price list, learned aliases, orders
  app.py       FastAPI app; static/index.html is the counter page
data/sample_pricelist.csv
wa-bridge/    Node.js whatsapp-web.js bridge
scripts/eval.py, scripts/try_samples.py
tests/
```

## License

MIT