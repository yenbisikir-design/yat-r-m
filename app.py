from flask import Flask, request, jsonify
import requests
import re
import os

app = Flask(__name__)

TELEGRAM_TOKEN = "8414450173:AAGpMe7TBP4xQiL_YjfB2_WboKnkFN4t3AI"
TELEGRAM_CHAT_ID = "-4949276017"

sira = {"num": 1}

def parse_bildirim(metin):
    isim_match = re.search(r'([A-ZÇĞİÖŞÜ][A-ZÇĞİÖŞÜa-züşğıöç\s]{2,}?)\s+tarafından', metin)
    tutar_match = re.search(r'([\d.,]+)\s*TL', metin)
    gonderenisim = isim_match.group(1).strip() if isim_match else "Bilinmiyor"
    tutar = tutar_match.group(1).strip() if tutar_match else "?"
    return gonderenisim, tutar

def telegram_gonder(mesaj):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": mesaj}
    requests.post(url, data=data)

@app.route('/bildirim', methods=['POST', 'GET'])
def bildirim():
    if request.method == 'POST':
        metin = request.json.get('metin', '') if request.is_json else request.form.get('metin', '')
    else:
        metin = request.args.get('metin', '')

    if not metin:
        return jsonify({"hata": "Metin bos"}), 400

    gonderenisim, tutar = parse_bildirim(metin)
    mesaj = f"{sira['num']}. {gonderenisim} {tutar}"
    sira['num'] += 1
    telegram_gonder(mesaj)
    return jsonify({"durum": "ok", "mesaj": mesaj})

@app.route('/')
def index():
    return "Ziraat Bot calisiyor"

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
