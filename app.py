from flask import Flask, request, jsonify
import requests
import re
import os
import hashlib
import json

app = Flask(__name__)

TELEGRAM_TOKEN = "8414450173:AAGpMe7TBP4xQiL_YjfB2_WboKnkFN4t3AI"
TELEGRAM_CHAT_ID = "-4949276017"
ADMIN_ID = 7627804591

mod = {"aktif": "oto"}
sira = {"num": 1}
islemler = {}
islem_sayac = {"num": 1}
duplicate_set = set()

def parse_bildirim(metin):
    isim_match = re.search(r'([A-ZÇĞİÖŞÜ][A-ZÇĞİÖŞÜa-züşğıöç\s]{2,}?)\s+tarafından', metin)
    tutar_match = re.search(r'([\d.,]+)\s*TL', metin)
    gonderenisim = isim_match.group(1).strip() if isim_match else "Bilinmiyor"
    tutar_str = tutar_match.group(1).strip() if tutar_match else "0"
    tutar_float = float(tutar_str.replace('.', '').replace(',', '.'))
    return gonderenisim, tutar_str, tutar_float

def hash_uret(metin):
    return hashlib.md5(metin.strip().encode()).hexdigest()

def telegram_gonder(chat_id, mesaj, butonlar=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": chat_id, "text": mesaj, "parse_mode": "HTML"}
    if butonlar:
        data["reply_markup"] = json.dumps({"inline_keyboard": butonlar})
    try:
        requests.post(url, data=data, timeout=5)
    except Exception as e:
        print(f"Telegram hata: {e}")

def gruba_gonder(s, gonderenisim, tutar_str):
    mesaj = f"{s}. {gonderenisim} {tutar_str}"
    telegram_gonder(TELEGRAM_CHAT_ID, mesaj)

def onay_sor(islem_id, gonderenisim, tutar_str):
    mesaj = f"⚠️ <b>Onay Bekliyor</b>\n\n👤 {gonderenisim}\n💰 {tutar_str} TL\n\nOnaylıyor musun?"
    butonlar = [[
        {"text": "✅ Onayla", "callback_data": f"onayla_{islem_id}"},
        {"text": "❌ Reddet", "callback_data": f"reddet_{islem_id}"}
    ]]
    telegram_gonder(ADMIN_ID, mesaj, butonlar)

@app.route('/bildirim', methods=['POST', 'GET'])
def bildirim():
    if request.method == 'POST':
        metin = request.json.get('metin', '') if request.is_json else request.form.get('metin', '')
    else:
        metin = request.args.get('metin', '')

    if not metin:
        return jsonify({"hata": "Metin bos"}), 400

    h = hash_uret(metin)
    if h in duplicate_set:
        return jsonify({"durum": "duplicate"}), 200
    duplicate_set.add(h)

    gonderenisim, tutar_str, tutar_float = parse_bildirim(metin)
    aktif_mod = mod["aktif"]

    if aktif_mod == 'manuel':
        islem_id = islem_sayac["num"]
        islem_sayac["num"] += 1
        islemler[islem_id] = {"gonderenisim": gonderenisim, "tutar_str": tutar_str}
        onay_sor(islem_id, gonderenisim, tutar_str)
        return jsonify({"durum": "onay_bekleniyor"})

    elif aktif_mod == 'oto':
        if tutar_float <= 100:
            islem_id = islem_sayac["num"]
            islem_sayac["num"] += 1
            islemler[islem_id] = {"gonderenisim": gonderenisim, "tutar_str": tutar_str}
            onay_sor(islem_id, gonderenisim, tutar_str)
            return jsonify({"durum": "onay_bekleniyor"})
        else:
            s = sira["num"]
            sira["num"] += 1
            gruba_gonder(s, gonderenisim, tutar_str)
            return jsonify({"durum": "ok"})

    return jsonify({"durum": "ok"})

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.json
        if not data:
            return "ok"

        if 'message' in data:
            msg = data['message']
            if msg['chat']['type'] != 'private':
                return "ok"
            from_id = msg['from']['id']
            if from_id != ADMIN_ID:
                return "ok"
            text = msg.get('text', '')
            chat_id = msg['chat']['id']

            if text == '/oto':
                mod["aktif"] = "oto"
                telegram_gonder(chat_id, "✅ <b>OTO mod aktif</b>\n100 TL üzeri direkt gider\n100 TL ve altı onay bekler.")
            elif text == '/manuel':
                mod["aktif"] = "manuel"
                telegram_gonder(chat_id, "✅ <b>MANUEL mod aktif</b>\nHer yatırım onayını bekler.")
            elif text == '/mod':
                telegram_gonder(chat_id, f"Aktif mod: <b>{mod['aktif'].upper()}</b>")

        if 'callback_query' in data:
            cb = data['callback_query']
            from_id = cb['from']['id']
            cb_data = cb['data']
            cb_id = cb['id']

            try:
                requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/answerCallbackQuery",
                              data={"callback_query_id": cb_id}, timeout=5)
            except:
                pass

            if from_id != ADMIN_ID:
                return "ok"

            if cb_data.startswith("onayla_"):
                islem_id = int(cb_data.split("_")[1])
                if islem_id in islemler:
                    islem = islemler[islem_id]
                    s = sira["num"]
                    sira["num"] += 1
                    gruba_gonder(s, islem["gonderenisim"], islem["tutar_str"])
                    del islemler[islem_id]
                    telegram_gonder(ADMIN_ID, "✅ Onaylandı ve gruba gönderildi.")
                else:
                    telegram_gonder(ADMIN_ID, "⚠️ Bu işlem bulunamadı.")

            elif cb_data.startswith("reddet_"):
                islem_id = int(cb_data.split("_")[1])
                if islem_id in islemler:
                    del islemler[islem_id]
                telegram_gonder(ADMIN_ID, "❌ Reddedildi.")

    except Exception as e:
        print(f"Webhook hata: {e}")

    return "ok"
    
elif text == '/id':
    telegram_gonder(chat_id, f"Chat ID: <b>{chat_id}</b>")

@app.route('/')
def index():
    return "Ziraat Bot calisiyor"

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
