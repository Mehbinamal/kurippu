import json
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from kurippu import billing, matcher, reader, whatsapp
from kurippu.app import create_app
from kurippu.store import Store, parse_pricelist_csv


@pytest.fixture
def store():
    return Store(":memory:")


def item(raw, name, qty=None, unit=None, size=None):
    return {"raw": raw, "item": name, "qty": qty, "unit": unit, "size": size}


def match(store, it, learned=None):
    return matcher.match_line(it, store.skus(), learned or {})


# --- matcher -------------------------------------------------------------

def test_alias_match_and_kg(store):
    ln = match(store, item("2 kilo puttu podi", "puttu podi", 2, "kg"))
    assert (ln["status"], ln["sku"], ln["qty"]) == ("ok", "atta-loose", "2")


def test_sample_price_list_uses_kerala_products_and_customer_words(store):
    skus = store.skus()
    names = {sku.name for sku in skus}
    aliases = {alias for sku in skus for alias in sku.aliases}
    assert {"Puttu Podi (loose)", "Kerala Matta Rice", "Cherupayar Parippu",
            "Nendran Banana Chips 100 g", "Curry Leaves (bunch)"} <= names
    assert {"puttupodi", "matta ari", "kariveppila"} <= aliases
    assert any("\u0d00" <= char <= "\u0d7f" for alias in aliases for char in alias)


def test_phrase_key_removes_manglish_quantity_and_size_words():
    assert matcher.phrase_key({"raw": "chetta oru kaal kilo jeerakam cheriya"}) == "jeerakam"


def test_grams_convert_to_kg(store):
    ln = match(store, item("500 gm aval", "aval", 500, "g"))
    assert (ln["sku"], ln["qty"], ln["status"]) == ("poha", "0.5", "ok")


def test_dozen_eggs(store):
    assert match(store, item("1 dozen mutta", "eggs", 1, "dozen"))["qty"] == "12"


def test_size_word_picks_pack(store):
    ln = match(store, item("1 Milma butter cheriya", "milma butter", 1, None, "small"))
    assert (ln["sku"], ln["status"]) == ("butter-amul-100g", "ok")


def test_volume_picks_pack(store):
    ln = match(store, item("ഒരു ലിറ്റർ പാൽ", "milk", 1, "l"))
    assert (ln["sku"], ln["qty"], ln["status"]) == ("milk-amul-1l", "1", "ok")


def test_two_litres_is_two_one_litre_packs(store):
    ln = match(store, item("2 litre paal", "milk", 2, "l"))
    assert (ln["sku"], ln["qty"]) == ("milk-amul-1l", "2")


def test_several_sizes_needs_check(store):
    ln = match(store, item("oru banana chips", "banana chips", 1, "pack"))
    assert ln["status"] == "check" and {o["sku"] for o in ln["options"]} >= {"maggi-70g", "maggi-280g"}


def test_unknown_item(store):
    ln = match(store, item("pazham pori", "pazham pori"))
    assert ln["status"] == "unknown" and ln["sku"] is None


def test_out_of_stock(store):
    assert match(store, item("paneer", "paneer"))["status"] == "out"


def test_missing_qty_is_flagged(store):
    ln = match(store, item("thayir", "curd"))
    assert ln["status"] == "check" and "assumed 1" in ln["note"]


def test_learned_alias_wins(store):
    it = item("2 packet achappam", "achappam", 2, "pack")
    learned = {matcher.phrase_key(it): "parle-g-250g"}
    ln = match(store, it, learned)
    assert (ln["sku"], ln["status"], ln["qty"]) == ("parle-g-250g", "ok", "2")


# --- billing -------------------------------------------------------------

def test_bill_uses_price_list_not_request(store):
    bill = billing.build_bill([{"sku": "eggs", "qty": "6", "price": "1"}], store.sku_map())
    assert bill["rows"][0]["total"] == "42.00" and bill["total"] == "42"


def test_bill_rounds_to_rupee_and_skips_out_of_stock(store):
    bill = billing.build_bill([{"sku": "sugar", "qty": "0.25"}, {"sku": "paneer-200g", "qty": "1"}],
                              store.sku_map(), delivery="10")
    assert bill["subtotal"] == "11.25" and bill["total"] == "21" and bill["round_off"] == "-0.25"
    assert bill["skipped"] == ["Paneer 200 g"]


@pytest.mark.parametrize("qty", ["0", "-1", "abc", "5000"])
def test_bad_quantity_rejected(store, qty):
    with pytest.raises(billing.BillError):
        billing.build_bill([{"sku": "eggs", "qty": qty}], store.sku_map())


def test_upi_uri_is_encoded():
    uri = billing.upi_uri("shop@okaxis", "Kochi Naadan Stores", "224", "Kurippu order 7")
    assert uri.startswith("upi://pay?pa=shop%40okaxis&pn=Kochi%20Naadan%20Stores&am=224.00&cu=INR")
    assert billing.qr_svg(uri).lstrip().startswith("<?xml") or "<svg" in billing.qr_svg(uri)


def test_wa_link_adds_india_code():
    assert billing.wa_link("98765 43210", "hi").startswith("https://wa.me/919876543210?text=hi")


# --- reader --------------------------------------------------------------

def test_reader_validates_and_clamps():
    out = json.dumps({"is_order": True, "items": [
        {"raw": "2 kilo puttu podi", "item": "Puttu Podi", "qty": 2, "unit": "kg", "size": None},
        {"raw": "x", "item": "rice", "qty": -3, "unit": "tonne", "size": "huge"}]})
    res = reader.read_order("2 kilo puttu podi", chat=lambda t: out)
    assert res["items"][0]["item"] == "puttu podi"
    assert res["items"][1] == {"raw": "x", "item": "rice", "qty": None, "unit": None, "size": None}


def test_reader_retries_once_then_fails():
    calls = []
    def bad(t):
        calls.append(t)
        return "not json"
    with pytest.raises(reader.ReaderError):
        reader.read_order("2 kilo puttu podi", chat=bad)
    assert len(calls) == 2


def test_reader_not_an_order():
    res = reader.read_order("thank you", chat=lambda t: '{"is_order": false, "items": []}')
    assert res["is_order"] is False and res["items"] == []


def test_reader_prompt_targets_malayalam_and_manglish():
    assert "Malayalam" in reader.SYSTEM and "Manglish" in reader.SYSTEM
    assert "Hindi" not in reader.SYSTEM and "Marathi" not in reader.SYSTEM
    assert any(any("\u0d00" <= char <= "\u0d7f" for char in message)
               for message, _ in reader.EXAMPLES)


# --- whatsapp export -------------------------------------------------------

def test_parse_android_and_iphone_exports():
    text = ("15/10/26, 9:41 am - Anjali: 2 kilo puttu podi\nand 6 mutta\n"
            "15/10/26, 9:42 am - Anjali: <Media omitted>\n"
            "[15/10/26, 10:02:11 AM] Anoop: 1 litre paal")
    msgs = whatsapp.parse_chat(text)
    assert [(m["sender"], m["text"]) for m in msgs] == [("Anjali", "2 kilo puttu podi\nand 6 mutta"), ("Anoop", "1 litre paal")]


# --- price list ------------------------------------------------------------

def test_pricelist_rejects_bad_unit():
    with pytest.raises(ValueError, match="sold by"):
        parse_pricelist_csv("sku,name,unit,price\na,Puttu Podi,bag,40\n")


# --- API end to end (fake model) -------------------------------------------

def test_api_read_and_bill(store):
    fake = json.dumps({"is_order": True, "items": [
        {"raw": "6 mutta", "item": "eggs", "qty": 6, "unit": "pc", "size": None},
        {"raw": "<script>alert(1)</script> 1 achappam", "item": "achappam", "qty": 1, "unit": "pack", "size": None}]})
    app = create_app(store=store, read=lambda t: reader.read_order(t, chat=lambda _: fake))
    c = TestClient(app)
    c.post("/api/shop", json={"name": "Kochi Naadan Stores", "upi_id": "kochi@okaxis"})
    lines = c.post("/api/read", json={"text": "6 mutta, 1 achappam"}).json()["lines"]
    assert lines[0]["status"] == "ok"
    bill = c.post("/api/bill", json={"customer": "Anjali", "lines": [
        {"sku": "eggs", "qty": "6", "raw": "6 mutta"},
        {"sku": "parle-g-250g", "qty": "1", "raw": lines[1]["raw"], "phrase": lines[1]["phrase"], "learn": True}]}).json()
    assert bill["total"] == "67" and "Total: ₹67" in bill["reply"] and "am=67.00" in bill["upi_uri"]
    assert store.learned()[lines[1]["phrase"]] == "parle-g-250g"
    assert c.get("/api/orders").json()[0]["total"] == "67"
    assert c.post(f"/api/orders/{bill['order_id']}/status", json={"status": "paid"}).json() == {"ok": True}
    assert c.post("/api/bill", json={"lines": [{"sku": "nope", "qty": "1"}]}).status_code == 400


def test_partial_pack_rounds_up_and_asks(store):
    ln = match(store, item("kaal kilo jeerakam", "jeerakam", 0.25, "kg"))
    assert (ln["sku"], ln["qty"], ln["status"]) == ("jeera-100g", "3", "check")
    assert [c["qty"] for c in ln["choices"]] == ["2", "3"]
    assert ln["choices"][0]["label"] == "2 × 100 g = 200 g"


# --- regressions found in review -------------------------------------------

@pytest.mark.parametrize("price", ["nan", "inf", "-5", "abc", ""])
def test_pricelist_rejects_bad_prices(price):
    with pytest.raises(ValueError, match="price"):
        parse_pricelist_csv(f"sku,name,unit,price\na,Puttu Podi,kg,{price}\n")


def test_pricelist_error_names_the_product():
    with pytest.raises(ValueError, match="Cherupayar Parippu"):
        parse_pricelist_csv("sku,name,unit,price\ndal,Cherupayar Parippu,kg,lots\n")


def test_money_uses_indian_grouping():
    assert billing.money(Decimal("123456")) == "₹1,23,456"
    assert billing.money(Decimal("1234567.5")) == "₹12,34,567.50"
    assert billing.money(Decimal("999")) == "₹999"
    assert billing.money(Decimal("-0.25")) == "−₹0.25"


def test_wa_link_handles_leading_zero():
    assert billing.wa_link("09876543210", "x").startswith("https://wa.me/919876543210?")


def test_chat_export_skips_system_and_media_lines():
    text = ("15/10/26, 9:40 am - Messages and calls are end-to-end encrypted. No one outside of this chat can read them.\n"
            "15/10/26, 9:41 am - Anjali: 2 kilo puttu podi\n"
            "15/10/26, 9:42 am - Anjali changed their phone number\n"
            "15/10/26, 9:43 am - Anjali: image omitted\n"
            "15/10/26, 9:44 am - Anoop: 1 litre paal")
    msgs = whatsapp.parse_chat(text)
    assert [(m["sender"], m["text"]) for m in msgs] == [("Anjali", "2 kilo puttu podi"), ("Anoop", "1 litre paal")]


def test_learning_shows_up_as_customer_word_and_can_be_removed(store):
    store.learn("achappam", "parle-g-250g")
    achappam = store.sku_map()["parle-g-250g"]
    assert "achappam" in achappam.aliases and store.learned()["achappam"] == "parle-g-250g"
    achappam.aliases.remove("achappam")
    store.replace_skus([achappam if s.sku == achappam.sku else s for s in store.skus()])
    store.forget_missing_aliases()
    assert "achappam" not in store.learned()


def test_api_rejects_bad_upi_and_does_not_learn_from_failed_bill(store):
    c = TestClient(create_app(store=store, read=lambda t: {"is_order": False, "items": []}))
    assert c.post("/api/shop", json={"upi_id": "not a upi"}).status_code == 400
    assert c.post("/api/shop", json={"upi_id": "kochi.naadan@okaxis"}).status_code == 200
    bad = c.post("/api/bill", json={"lines": [{"sku": "eggs", "qty": "abc", "phrase": "mutta", "learn": True}]})
    assert bad.status_code == 400 and "mutta" not in store.learned()


def test_quote_mode_saves_nothing(store):
    c = TestClient(create_app(store=store, read=lambda t: {"is_order": False, "items": []}))
    q = c.post("/api/bill", json={"save": False, "lines": [{"ref": "l1", "sku": "eggs", "qty": "6", "phrase": "mutta", "learn": True}]}).json()
    assert q["total"] == "42" and q["rows"][0]["ref"] == "l1"
    assert store.orders() == [] and "mutta" not in store.learned()


def test_index_is_not_cached(store):
    c = TestClient(create_app(store=store))
    assert c.get("/").headers["cache-control"] == "no-store"


def test_learning_keeps_customer_words_too(store):
    c = TestClient(create_app(store=store, read=lambda t: {"is_order": False, "items": []}))
    r = c.post("/api/bill", json={"lines": [{"sku": "coriander", "qty": "2", "raw": "2 kariveppila", "phrase": "curry leaves", "learn": True}]})
    assert r.status_code == 200
    assert {"curry leaves", "kariveppila"} <= set(store.sku_map()["coriander"].aliases)
    ln = matcher.match_line(item("4 kariveppila", "curry leaves", 4, None), store.skus(), store.learned())
    assert ln["sku"] == "coriander"


def test_reply_shows_round_off(store):
    bill = billing.build_bill([{"sku": "sugar", "qty": "0.5"}], store.sku_map())
    text = billing.reply_text({"name": "Shop"}, "", bill, 1, [])
    assert "Round off – ₹0.50" in text and "*Total: ₹23*" in text
