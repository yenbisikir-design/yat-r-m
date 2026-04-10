from flask import Flask, request, jsonify
import requests
import re

app = Flask(__name__)

# Ayarlar
TELEGRAM_TOKEN = "8414450173:AAGpMe7TBP4xQiL_YjfB2_WboKnkFN4t3AI"
TELEGRAM_CHAT_ID = "-4949276017"

# Sıra numarası (sunucu yeniden başlayınca sıfırlanır, ileride DB eklenebilir)
sira = {"num": 1}

def parse_bildirim(metin):
    """Ziraat bildirim metninden gönderen ve tutarı çeker"""
    
    # Gönderen ismi: "... ECE TEKİN tarafından ..."
    isim_match = re.search(r'(\w[\w\s]+?)\s+tarafından', metin)
    
    # Tutar: "... 100,00 TL ..."
    tutar_match = re.search(r'([\d.,]+)\s*TL', metin)
    
    gonderenisim = isim_match.group(1).strip() if isim_match else "Bilinmiyor"
    tutar = tutar_match.group(1).strip() if tutar_match else "?"
    
    return gonderenisim, tutar

def telegram_gonder(mesaj):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": mesaj
    }
    requests.post(url, data=data)

@app.route('/bildirim', methods=['POST', 'GET'])
def bildirim():
    # Hem POST hem GET destekle (MacroDroid için)
    if request.method == 'POST':
        metin = request.json.get('metin', '') if request.is_json else request.form.get('metin', '')
    else:
        metin = request.args.get('metin', '')

    if not metin:
        return jsonify({"hata": "Metin boş"}), 400

    gonderenisim, tutar = parse_bildirim(metin)

    mesaj = f"{sira['num']}. {gonderenisim} — {tutar} TL"
    sira['num'] += 1

    telegram_gonder(mesaj)

    return jsonify({"durum": "ok", "mesaj": mesaj})

@app.route('/')
def index():
    return "Ziraat Bot çalışıyor ✅"
if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
