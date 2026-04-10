from flask import Flask, request, jsonify
import requests
import re
import os
import hashlib
import json
import time
from threading import Timer
from datetime import datetime, timedelta

app = Flask(__name__)

TELEGRAM_TOKEN = "8414450173:AAGpMe7TBP4xQiL_YjfB2_WboKnkFN4t3AI"
ADMIN_ID = 7627804591
GUVENLIK_ANAHTARI = "redkit2026"

BANKA_GRUPLARI = {
    "enpara": "-4949276017",
    "ziraat": "-4949276017",
}
VARSAYILAN_GRUP = "-4949276017"

adminler = {ADMIN_ID: "bas admin"}
mod = {"aktif": "oto"}
sira = {"num": 1}
islemler = {}
islem_sayac = {"num": 1}
duplicate_set = set()
son_odeme = {}
gunluk = {}
LIMIT_SURE = 600

BANKA_KELIMELERI = {
    "enpara": ["enpara", "qnb"],
    "ziraat": ["ziraat", "havale aktarilmistir", "havale aktarılmıştır"],
    "garanti": ["garanti", "bbva"],
    "vakif": ["vakifbank", "vakif", "vakıfbank"],
    "yapi_kredi": ["yapi kredi", "yapı kredi"],
    "akbank": ["akbank"],
    "isbankasi": ["is bankasi", "iş bankası", "isbank"],
}

def banka_tespit(metin):
    metin_lower = metin.lower()
    for banka, kelimeler in BANKA_KELIMELERI.items():
        for k in kelimeler:
            if k in metin_lower:
                return banka
    return "diger"

def parse_bildirim(metin):
    isim_match = re.search(r'([A-ZÇĞİÖŞÜ][A-ZÇĞİÖŞÜa-züşğıöç\s]{2,}?)\s+tarafından', metin)
    tutar_match = re.search(r'([\d.,]+)\s*TL', metin)
    gonderenisim = isim_match.group(1).strip() if isim_match else None
    tutar_str = tutar_match.group(1).strip() if tutar_match else None
    if not gonderenisim or not tutar_str:
        return None, None, None
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

def gruba_gonder(s, gonderenisim, tutar_str, grup_id):
    mesaj = f"{s}. {gonderenisim} {tutar_str}"
    telegram_gonder(grup_id, mesaj)
    if grup_id not in gunluk:
        gunluk[grup_id] = []
    try:
        tutar_float = float(tutar_str.replace('.', '').replace(',', '.'))
    except:
        tutar_float = 0
    gunluk[grup_id].append({"isim": gonderenisim, "tutar": tutar_float})

def onay_sor(islem_id, gonderenisim, tutar_str, banka, zorunlu_manuel=False):
    etiket = "🔄" if zorunlu_manuel else "⚠️"
    ekstra = "\n<i>Aynı kişiden tekrar ödeme - manuel onay zorunlu</i>" if zorunlu_manuel else ""
    mesaj = f"{etiket} <b>Onay Bekliyor</b>{ekstra}\n\n🏦 {banka.upper()}\n👤 {gonderenisim}\n💰 {tutar_str} TL\n\nOnaylıyor musun?"
    butonlar = [[
        {"text": "✅ Onayla", "callback_data": f"onayla_{islem_id}"},
        {"text": "❌ Reddet", "callback_data": f"reddet_{islem_id}"}
    ]]
    for admin_id in adminler:
        telegram_gonder(admin_id, mesaj, butonlar)

def gunluk_ozet_gonder():
    if gunluk:
        for grup_id, liste in gunluk.items():
            if not liste:
                continue
            toplam = sum(i["tutar"] for i in liste)
            sayi = len(liste)
            mesaj = f"📊 <b>Günlük Özet</b>\n\nToplam işlem: {sayi}\nToplam tutar: {toplam:,.2f} TL"
            telegram_gonder(ADMIN_ID, mesaj)
        gunluk.clear()
    zamanla_gunluk_ozet()

def zamanla_gunluk_ozet():
    now = datetime.now()
    yarin_gece = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    kalan = (yarin_gece - now).total_seconds()
    t = Timer(kalan, gunluk_ozet_gonder)
    t.daemon = True
    t.start()

@app.route('/bildirim', methods=['POST', 'GET'])
def bildirim():
    # Güvenlik anahtarı kontrolü
    anahtar = request.args.get('key', '')
    if anahtar != GUVENLIK_ANAHTARI:
        return jsonify({"hata": "Yetkisiz"}), 403

    if request.method == 'POST':
        metin = request.json.get('metin', '') if request.is_json else request.form.get('metin', '')
    else:
        metin = request.args.get('metin', '')

    if not metin or len(metin.strip()) < 10:
        return jsonify({"hata": "Gecersiz metin"}), 400

    h = hash_uret(metin)
    if h in duplicate_set:
        return jsonify({"durum": "duplicate"}), 200
    duplicate_set.add(h)

    gonderenisim, tutar_str, tutar_float = parse_bildirim(metin)

    # Parse başarısız olduysa işleme
    if not gonderenisim or not tutar_str:
        return jsonify({"hata": "Bildirim parse edilemedi"}), 400

    banka = banka_tespit(metin)
    grup_id = BANKA_GRUPLARI.get(banka, VARSAYILAN_GRUP)
    aktif_mod = mod["aktif"]

    simdi = time.time()
    zorunlu_manuel = False
    if gonderenisim in son_odeme:
        if simdi - son_odeme[gonderenisim] < LIMIT_SURE:
            zorunlu_manuel = True
    son_odeme[gonderenisim] = simdi

    if zorunlu_manuel or aktif_mod == 'manuel':
        islem_id = islem_sayac["num"]
        islem_sayac["num"] += 1
        islemler[islem_id] = {"gonderenisim": gonderenisim, "tutar_str": tutar_str, "grup_id": grup_id}
        onay_sor(islem_id, gonderenisim, tutar_str, banka, zorunlu_manuel)
        return jsonify({"durum": "onay_bekleniyor"})

    elif aktif_mod == 'oto':
        if tutar_float <= 100:
            islem_id = islem_sayac["num"]
            islem_sayac["num"] += 1
            islemler[islem_id] = {"gonderenisim": gonderenisim, "tutar_str": tutar_str, "grup_id": grup_id}
            onay_sor(islem_id, gonderenisim, tutar_str, banka)
            return jsonify({"durum": "onay_bekleniyor"})
        else:
            s = sira["num"]
            sira["num"] += 1
            gruba_gonder(s, gonderenisim, tutar_str, grup_id)
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
            from_id = msg['from']['id']
            chat_id = msg['chat']['id']
            text = msg.get('text', '')
            chat_type = msg['chat']['type']

            if text == '/id':
                telegram_gonder(chat_id, f"Chat ID: <b>{chat_id}</b>")
                return "ok"

            if chat_type != 'private':
                return "ok"

            if from_id not in adminler:
                telegram_gonder(chat_id, "⛔ Bu bota erişim izniniz yok.")
                return "ok"

            if text == '/oto':
                mod["aktif"] = "oto"
                telegram_gonder(chat_id, "✅ <b>OTO mod aktif</b>\n100 TL üzeri direkt gider\n100 TL ve altı onay bekler.")
            elif text == '/manuel':
                mod["aktif"] = "manuel"
                telegram_gonder(chat_id, "✅ <b>MANUEL mod aktif</b>\nHer yatırım onayını bekler.")
            elif text == '/mod':
                telegram_gonder(chat_id, f"Aktif mod: <b>{mod['aktif'].upper()}</b>")
            elif text == '/toplam':
                if not gunluk:
                    telegram_gonder(chat_id, "Bugün henüz işlem yok.")
                else:
                    yanit = "<b>Bugünkü Özetler:</b>\n"
                    for gid, liste in gunluk.items():
                        toplam = sum(i["tutar"] for i in liste)
                        yanit += f"\nGrup {gid}:\n{len(liste)} işlem — {toplam:,.2f} TL"
                    telegram_gonder(chat_id, yanit)
            elif text == '/adminler':
                if from_id != ADMIN_ID:
                    return "ok"
                liste = "\n".join([f"• {v} ({k})" for k, v in adminler.items()])
                telegram_gonder(chat_id, f"<b>Admin Listesi:</b>\n{liste}")
            elif text.startswith('/ytekle'):
                if from_id != ADMIN_ID:
                    telegram_gonder(chat_id, "⛔ Sadece baş admin yönetici ekleyebilir.")
                    return "ok"
                parca = text.split()
                if len(parca) < 2:
                    telegram_gonder(chat_id, "Kullanım: /ytekle 123456789")
                    return "ok"
                try:
                    hedef_id = int(parca[1])
                    adminler[hedef_id] = str(hedef_id)
                    telegram_gonder(chat_id, f"✅ <b>{hedef_id}</b> admin olarak eklendi.")
                    telegram_gonder(hedef_id, "✅ Artık bu bota admin olarak erişebilirsiniz.")
                except:
                    telegram_gonder(chat_id, "⚠️ Geçersiz ID.")
            elif text.startswith('/ysil'):
                if from_id != ADMIN_ID:
                    telegram_gonder(chat_id, "⛔ Sadece baş admin yönetici silebilir.")
                    return "ok"
                parca = text.split()
                if len(parca) < 2:
                    telegram_gonder(chat_id, "Kullanım: /ysil 123456789")
                    return "ok"
                try:
                    hedef_id = int(parca[1])
                    if hedef_id == ADMIN_ID:
                        telegram_gonder(chat_id, "⛔ Baş admin silinemez.")
                        return "ok"
                    if hedef_id in adminler:
                        del adminler[hedef_id]
                        telegram_gonder(chat_id, "✅ Admin silindi.")
                    else:
                        telegram_gonder(chat_id, "⚠️ Bu ID adminler arasında yok.")
                except:
                    telegram_gonder(chat_id, "⚠️ Geçersiz ID.")

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

            if from_id not in adminler:
                return "ok"

            if cb_data.startswith("onayla_"):
                islem_id = int(cb_data.split("_")[1])
                if islem_id in islemler:
                    islem = islemler[islem_id]
                    s = sira["num"]
                    sira["num"] += 1
                    gruba_gonder(s, islem["gonderenisim"], islem["tutar_str"], islem["grup_id"])
                    del islemler[islem_id]
                    telegram_gonder(from_id, "✅ Onaylandı ve gruba gönderildi.")
                    for admin_id in adminler:
                        if admin_id != from_id:
                            telegram_gonder(admin_id, f"✅ İşlem onaylandı: {islem['gonderenisim']} {islem['tutar_str']}")
                else:
                    telegram_gonder(from_id, "⚠️ Bu işlem zaten işlendi.")

            elif cb_data.startswith("reddet_"):
                islem_id = int(cb_data.split("_")[1])
                if islem_id in islemler:
                    islem = islemler[islem_id]
                    del islemler[islem_id]
                    telegram_gonder(from_id, "❌ Reddedildi.")
                    for admin_id in adminler:
                        if admin_id != from_id:
                            telegram_gonder(admin_id, f"❌ İşlem reddedildi: {islem['gonderenisim']} {islem['tutar_str']}")
                else:
                    telegram_gonder(from_id, "⚠️ Bu işlem zaten işlendi.")

    except Exception as e:
        print(f"Webhook hata: {e}")

    return "ok"

@app.route('/')
def index():
    return "Ziraat Bot calisiyor"

zamanla_gunluk_ozet()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
