#!/usr/bin/env python
# coding: utf-8

# In[ ]:


from flask import Flask, request, jsonify, render_template_string, send_file, abort
import sqlite3
import os
from io import BytesIO
from gtts import gTTS

app = Flask(__name__)

# ======================
#  1. VERİTABANI OKUMA
# ======================
def load_from_db(db_path="ceviri.db"):
    if not os.path.exists(db_path):
        print(f"⚠️ {db_path} bulunamadı. Uygulama yine açılacak ama kelime listesi boş olabilir.")

    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    try:
        c.execute("SELECT english, turkish FROM ceviri2 ORDER BY rowid")
        rows = c.fetchall()
    except Exception as e:
        print("⚠️ ceviri2 tablosundan veri çekilemedi:", e)
        rows = []
    conn.close()

    words_dict = {}
    words_list = []
    for eng, tr in rows:
        if eng:
            eng_key = eng.strip().lower()
            tr_val = (tr or "").strip()
            words_dict[eng_key] = tr_val
            words_list.append((eng_key, tr_val))
    print(f"✅ {len(words_list)} kelime yüklendi (sıralı).")
    return words_dict, words_list

# ======================
#  2. KELİMELERİ YÜKLE
# ======================
WORDS, WORDS_LIST = load_from_db("ceviri.db")
CURRENT_INDEX = 0

# ======================
#  3. HTML ARAYÜZ
# ======================
INDEX_HTML = """
<!doctype html>
<html lang='tr'>
<head>
<meta charset='utf-8'>
<title>İngilizce - Türkçe Test</title>
<style>
  body { font-family: Arial; background:#0f172a; color:#fff; text-align:center; padding-top:80px; }
  .card { background:#1e293b; display:inline-block; padding:30px; border-radius:16px; }
  input { padding:10px; border-radius:8px; border:0; width:260px; }
  button { padding:10px 16px; border:0; border-radius:8px; background:#16a34a; color:white; cursor:pointer; margin:4px; }
  .result { margin-top:16px; font-size:18px; min-height: 24px; }
</style>
</head>
<body>
  <div class='card'>
    <h2>İngilizce - Türkçe Test</h2>
    <p id='word'>...</p>
    <input id='answer' placeholder='Türkçesini yaz'>
    <br>
    <button onclick='startSpeaking()'>▶️ Başla</button>
    <button onclick='checkAnswer()'>Kontrol Et</button>
    <button onclick='speakCurrent()'>🔊 Dinle</button>
    <div class='result' id='result'></div>
  </div>

<script>
let currentWord = null;
// "Başla" basıldı mı? Basıldıysa yeni kelime yüklendiğinde otomatik seslendireceğiz.
let autoSpeak = false;

async function loadWord(){
  const res = await fetch('/api/word');
  const data = await res.json();
  currentWord = data.word;
  document.getElementById('word').textContent = 'Kelime: ' + currentWord;
  document.getElementById('answer').value = '';
  document.getElementById('result').textContent = '';
  document.getElementById('answer').focus();

  // Eğer Başla aktifse, yeni kelimeyi otomatik seslendir
  if (autoSpeak && currentWord) {
    // çok küçük bir gecikme, DOM güncellensin
    setTimeout(() => speakCurrent(), 120);
  }
}

function speakText(text, lang='en'){
  const audio = new Audio('/api/tts?text=' + encodeURIComponent(text) + '&lang=' + encodeURIComponent(lang));
  audio.play();
}

function speakCurrent(){
  if(!currentWord) return;
  speakText(currentWord, 'en'); // İngilizce kelimeyi oku
}

// "Başla": sadece mevcut kelimeyi seslendirir ve autoSpeak'i açar.
// Kendiliğinden yeni kelimeye geçmez!
function startSpeaking(){
  autoSpeak = true;
  speakCurrent();
}

async function checkAnswer(){
  const answer = document.getElementById('answer').value.trim();
  if(!answer) return;

  const res = await fetch('/api/check', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({word: currentWord, answer: answer})
  });
  const data = await res.json();

  const resultEl = document.getElementById('result');
  resultEl.textContent = data.result;

  if(data.correct){
    resultEl.style.color = '#22c55e';
    // Doğruysa server indexi artırır; yeni kelimeyi yükle
    await loadWord();   // autoSpeak true ise burada yeni kelime otomatik seslendirilir
  } else {
    resultEl.style.color = '#ef4444';
    // Yanlışsa mevcut kelime kalır; istersen uyarıyı seslendirebilirsin
    speakText('Tekrar dene', 'tr');
  }
}

// Enter ile kontrol et
document.addEventListener('DOMContentLoaded', () => {
  const input = document.getElementById('answer');
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      checkAnswer();
    }
  });
});

window.onload = loadWord;
</script>
</body>
</html>
"""

# ======================
#  4. FLASK ROTALARI
# ======================
@app.get('/')
def index():
    return render_template_string(INDEX_HTML)

@app.get('/api/word')
def get_word():
    global CURRENT_INDEX
    if not WORDS_LIST:
        return jsonify({'word': '--- (kelime yok) ---'})
    if CURRENT_INDEX >= len(WORDS_LIST):
        CURRENT_INDEX = 0  # sona gelince başa dön
    eng, _ = WORDS_LIST[CURRENT_INDEX]
    return jsonify({'word': eng})

@app.post('/api/check')
def check_word():
    data = request.get_json()
    word = (data.get('word') or '').strip().lower()
    answer = (data.get('answer') or '').strip().lower()

    correct = False
    result = ''

    if word in WORDS:
        tr_meanings = [x.strip().lower() for x in WORDS[word].split(',') if x.strip()]
        if any(t in answer for t in tr_meanings):
            correct = True
            result = '✅ Doğru!'
            global CURRENT_INDEX
            CURRENT_INDEX += 1
        else:
            result = '❌ Yanlış! Tekrar dene.'
    else:
        result = 'Kelime bulunamadı.'

    return jsonify({'correct': correct, 'result': result})

# --- TTS: dil parametreli ---
@app.get('/api/tts')
def tts():
    text = (request.args.get('text') or '').strip()
    lang = (request.args.get('lang') or 'en').strip().lower()
    if not text:
        abort(400, 'text parametresi gerekli')

    if lang not in ('en', 'tr'):
        lang = 'en'

    mp3 = BytesIO()
    tts_obj = gTTS(text, lang=lang)
    tts_obj.write_to_fp(mp3)
    mp3.seek(0)
    return send_file(mp3, mimetype='audio/mpeg', as_attachment=False)

# ======================
#  5. ÇALIŞTIR
# ======================
if __name__ == "__main__":
    app.run(debug=True, use_reloader=False, host="127.0.0.1", port=5000)

