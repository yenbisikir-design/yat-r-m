from flask import Flask, request, jsonify
import requests
import re
import os
import sqlite3
import hashlib
import json

app = Flask(__name__)

TELEGRAM_TOKEN = "8414450173:AAGpMe7TBP4xQiL_YjfB2_WboKnkFN4t3AI"
TELEGRAM_CHAT_ID = "-4949276017"
ADMIN_ID = 7627804591

DB = "ziraat.db"

# --- Veritabanı ---
def db_init():
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS islemler (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        gonderenisim TEXT,
        tutar REAL,
        ham_metin TEXT,
        hash TEXT UNIQUE,
        durum TEXT DEFAULT 'beklemede',
        tarih DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    cur.execute('''CREATE TABLE IF NOT EXISTS ayarlar (
        anahtar TEXT PRIMARY KEY,
        deger TEXT
    )''')
    # Varsayılan mod: oto
    cur.execute("INSERT OR IGNORE INTO ayarlar VALUES ('mod', 'oto')")
    # Sıra numarası
    cur.execute("INSERT OR IGNORE INTO ayarlar VALUES ('sira', '1')")
    con.commit()
    con.close()

def ayar_oku(anahtar):
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute("SELECT deger FROM ayarlar WHERE anahtar=?", (anahtar,))
    row = cur.fetchone()
    con.close()
    return row[0] if row else None

def ayar_yaz(anahtar, deger):
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute("INSERT OR REPLACE INTO ayarlar VALUES (?,?)", (anahtar, str(deger)))
    con.commit()
    con.close()

def sira_al():
    sira = int(ayar_oku('sira'))
    ayar_yaz('sira', sira + 1)
    return sira

def hash_uret(metin):
    return hashlib.md5(metin.strip().encode()).hexdigest()

def duplicate_mi(hash):
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute("SELECT id FROM islemler WHERE hash=?", (hash,))
    row = cur.fetchone()
    con.close()
    return row is not None

def islem_kaydet(gonderenisim, tutar, ham_metin, hash, durum='beklemede'):
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute("INSERT INTO islemler (gonderenisim, tutar, ham_metin, hash, durum) VALUES (?,?,?,?,?)",
                (gonderenisim, tutar, ham_metin, hash, durum))
    islem_id = cur.lastrowid
    con.commit()
    con.close()
    return islem_id

def islem_guncelle(islem_id, durum):
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute("UPDATE islemler SET durum=? WHERE id=?", (durum, islem_id))
    con.commit()
    con.close()

# --- Parse ---
def parse_bildirim(metin):
    isim_match = re.search(r'([A-ZÇĞİÖŞÜ][A-ZÇĞİÖŞÜa-züşğıöç\s]{2,}?)\s+tarafından', metin)
    tutar_match = re.search(r'([\d.,]+)\s*TL', metin)
    gonderenisim = isim_match.group(1).strip() if isim_match else "Bilinmiyor"
    tutar_str = tutar_match.group(1).strip() if tutar_match else "0"
    tutar_float = float(tutar_str.replace('.', '').replace(',', '.'))
    return gonderenisim, tutar_str, tutar_float

# --- Telegram ---
def telegram_gonder(chat_id, mesaj, butonlar=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": chat_id, "text": mesaj}
    if butonlar:
        data["reply_markup"] = json.dumps({"inline_keyboard": butonlar})
    requests.post(url, data=data)

def gruba_gonder(sira, gonderenisim, tutar_str):
    mesaj = f"{sira}. {gonderenisim} {tutar_str}"
    telegram_gonder(TELEGRAM_CHAT_ID, mesaj)

def onay_sor(islem_id, gonderenisim, tutar_str):
    mesaj = f"⚠️ Onay Bekliyor\n\n👤 {gonderenisim}\n💰 {tutar_str} TL\n\nOnaylıyor musun?"
    butonlar = [[
        {"text": "✅ Onayla", "callback_data": f"onayla_{islem_id}"},
        {"text": "❌ Reddet", "callback_data": f"reddet_{islem_id}"}
    ]]
    telegram_gonder(ADMIN_ID, mesaj, butonlar)

# --- Ana endpoint ---
@app.route('/bildirim', methods=['POST', 'GET'])
def bildirim():
    if request.method == 'POST':
        metin = request.json.get('metin', '') if request.is_json else request.form.get('metin', '')
    else:
        metin = request.args.get('metin', '')

    if not metin:
        return jsonify({"hata": "Metin bos"}), 400

    # Duplicate kontrol
    h = hash_uret(metin)
    if duplicate_mi(h):
        return jsonify({"durum": "duplicate", "mesaj": "Bu bildirim zaten islendi"}), 200

    gonderenisim, tutar_str, tutar_float = parse_bildirim(metin)
    mod = ayar_oku('mod')

    if mod == 'manuel':
        # Her yatırım onay bekler
        islem_id = islem_kaydet(gonderenisim, tutar_float, metin, h, 'beklemede')
        onay_sor(islem_id, gonderenisim, tutar_str)
        return jsonify({"durum": "onay_bekleniyor"})

    elif mod == 'oto':
        if tutar_float <= 100:
            # 100 TL ve altı onay bekler
            islem_id = islem_kaydet(gonderenisim, tutar_float, metin, h, 'beklemede')
            onay_sor(islem_id, gonderenisim, tutar_str)
            return jsonify({"durum": "onay_bekleniyor"})
        else:
            # 100 TL üzeri direkt gider
            sira = sira_al()
            islem_kaydet(gonderenisim, tutar_float, metin, h, 'onaylandi')
            gruba_gonder(sira, gonderenisim, tutar_str)
            return jsonify({"durum": "ok", "mesaj": f"{sira}. {gonderenisim} {tutar_str}"})

# --- Callback (Onayla/Reddet butonları) ---
if 'message' in data:
    msg = data['message']
    # Sadece özel mesajları dinle
    if msg['chat']['type'] != 'private':
        return "ok"
@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    if not data:
        return "ok"

    # Komut kontrolü
    if 'message' in data:
        msg = data['message']
        chat_id = msg['chat']['id']
        from_id = msg['from']['id']
        text = msg.get('text', '')

        if from_id != ADMIN_ID:
            return "ok"

        if text == '/oto':
            ayar_yaz('mod', 'oto')
            telegram_gonder(chat_id, "✅ Mod: OTO\n100 TL üzeri direkt gider, 100 TL ve altı onay bekler.")
        elif text == '/manuel':
            ayar_yaz('mod', 'manuel')
            telegram_gonder(chat_id, "✅ Mod: MANUEL\nHer yatırım onayını bekler.")
        elif text == '/mod':
            mod = ayar_oku('mod')
            telegram_gonder(chat_id, f"Aktif mod: {mod.upper()}")

    # Buton callback
    if 'callback_query' in data:
        cb = data['callback_query']
        from_id = cb['from']['id']
        cb_data = cb['data']
        cb_id = cb['id']

        if from_id != ADMIN_ID:
            return "ok"

        # Callback yanıtla (butonu kapat)
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/answerCallbackQuery",
                      data={"callback_query_id": cb_id})

        if cb_data.startswith("onayla_"):
            islem_id = int(cb_data.split("_")[1])
            con = sqlite3.connect(DB)
            cur = con.cursor()
            cur.execute("SELECT gonderenisim, tutar FROM islemler WHERE id=?", (islem_id,))
            row = cur.fetchone()
            con.close()

            if row:
                gonderenisim, tutar_float = row
                tutar_str = f"{tutar_float:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
                sira = sira_al()
                islem_guncelle(islem_id, 'onaylandi')
                gruba_gonder(sira, gonderenisim, tutar_str)
                telegram_gonder(ADMIN_ID, f"✅ Onaylandı ve gruba gönderildi.")

        elif cb_data.startswith("reddet_"):
            islem_id = int(cb_data.split("_")[1])
            islem_guncelle(islem_id, 'reddedildi')
            telegram_gonder(ADMIN_ID, "❌ Reddedildi.")

    return "ok"

@app.route('/')
def index():
    return "Ziraat Bot calisiyor ✅"

db_init()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
