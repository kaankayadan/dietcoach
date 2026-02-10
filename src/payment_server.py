"""
Ödeme Web Sunucusu — Flask ile basit ödeme sayfası.
Kullanıcı Telegram'dan yönlendirilir, ödeme yapar, abonelik aktifleşir.
"""
import asyncio
import hashlib
import hmac
import json
import logging
import urllib.request
import urllib.parse
from datetime import date, timedelta
from flask import Flask, request, render_template_string, redirect, url_for
import asyncpg

from config.settings import Settings

logger = logging.getLogger(__name__)
settings = Settings()

app = Flask(__name__)

# ==========================================
# FIYATLAR
# ==========================================
PLANLAR = {
    "aylik": {"ad": "1 Aylık", "fiyat": 149.00, "gun": 30},
    "3aylik": {"ad": "3 Aylık", "fiyat": 349.00, "gun": 90},
    "yillik": {"ad": "Yıllık", "fiyat": 999.00, "gun": 365},
}

# ==========================================
# SAYFA ŞABLONLARI
# ==========================================
ODEME_SAYFASI = """
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Beslenme Koçu — Abonelik</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
               background: #f0f2f5; color: #1a1a2e; }
        .container { max-width: 600px; margin: 40px auto; padding: 20px; }
        h1 { text-align: center; margin-bottom: 10px; font-size: 28px; }
        .subtitle { text-align: center; color: #666; margin-bottom: 30px; }
        .plan { background: white; border-radius: 12px; padding: 24px; margin-bottom: 16px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.08); cursor: pointer; transition: all 0.2s;
                border: 2px solid transparent; }
        .plan:hover { border-color: #16a34a; transform: translateY(-2px); }
        .plan.populer { border-color: #16a34a; position: relative; }
        .plan.populer::before { content: "En Populer"; position: absolute; top: -12px; right: 16px;
                                 background: #16a34a; color: white; padding: 2px 12px;
                                 border-radius: 12px; font-size: 12px; }
        .plan-header { display: flex; justify-content: space-between; align-items: center; }
        .plan-name { font-size: 20px; font-weight: 600; }
        .plan-price { font-size: 24px; font-weight: 700; color: #16a34a; }
        .plan-detail { color: #666; margin-top: 4px; font-size: 14px; }
        .features { margin-top: 30px; background: white; border-radius: 12px; padding: 24px;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
        .features h3 { margin-bottom: 12px; }
        .features li { padding: 6px 0; list-style: none; }
        .features li::before { content: "✓ "; color: #16a34a; font-weight: bold; }
        .btn { display: block; width: 100%; padding: 16px; background: #16a34a; color: white;
               border: none; border-radius: 8px; font-size: 18px; font-weight: 600;
               cursor: pointer; margin-top: 20px; text-align: center; text-decoration: none; }
        .btn:hover { background: #15803d; }
        .success { background: white; border-radius: 12px; padding: 40px; text-align: center;
                   box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
        .success h2 { color: #16a34a; margin-bottom: 10px; }
    </style>
</head>
<body>
<div class="container">
    <h1>Beslenme Kocu</h1>
    <p class="subtitle">Kisisel AI beslenme kocunuz</p>

    {% for key, plan in planlar.items() %}
    <a href="/odeme/{{ telegram_id }}/{{ key }}" style="text-decoration:none; color:inherit;">
    <div class="plan {{ 'populer' if key == '3aylik' else '' }}">
        <div class="plan-header">
            <div>
                <div class="plan-name">{{ plan.ad }}</div>
                <div class="plan-detail">
                    {% if key == '3aylik' %}ayda 116 TL{% elif key == 'yillik' %}ayda 83 TL{% endif %}
                </div>
            </div>
            <div class="plan-price">{{ plan.fiyat|int }} TL</div>
        </div>
    </div>
    </a>
    {% endfor %}

    <div class="features">
        <h3>Abonelige Dahil</h3>
        <ul>
            <li>Kisisel AI beslenme kocu (7/24)</li>
            <li>Gunluk beslenme plani olusturma</li>
            <li>Ogun takibi ve kalori analizi</li>
            <li>Haftalik ilerleme raporu</li>
            <li>Su ve ogun hatirlatmalari</li>
            <li>Fotograf ile besin analizi</li>
        </ul>
    </div>
</div>
</body>
</html>
"""

ODEME_FORMU = """
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Odeme — {{ plan.ad }}</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
               background: #f0f2f5; color: #1a1a2e; }
        .container { max-width: 500px; margin: 40px auto; padding: 20px; }
        .card { background: white; border-radius: 12px; padding: 24px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
        h2 { margin-bottom: 20px; }
        .ozet { background: #f8f9fa; padding: 16px; border-radius: 8px; margin-bottom: 20px; }
        .ozet-row { display: flex; justify-content: space-between; padding: 4px 0; }
        .ozet-total { font-weight: 700; font-size: 18px; border-top: 1px solid #ddd; padding-top: 8px; margin-top: 8px; }
        label { display: block; font-weight: 500; margin-bottom: 4px; margin-top: 16px; }
        input { width: 100%; padding: 12px; border: 1px solid #ddd; border-radius: 8px; font-size: 16px; }
        input:focus { outline: none; border-color: #16a34a; }
        .row { display: flex; gap: 12px; }
        .row > div { flex: 1; }
        .btn { display: block; width: 100%; padding: 16px; background: #16a34a; color: white;
               border: none; border-radius: 8px; font-size: 18px; font-weight: 600;
               cursor: pointer; margin-top: 24px; }
        .btn:hover { background: #15803d; }
        .guvenli { text-align: center; color: #666; margin-top: 12px; font-size: 13px; }
    </style>
</head>
<body>
<div class="container">
    <div class="card">
        <h2>Odeme Bilgileri</h2>
        <div class="ozet">
            <div class="ozet-row"><span>Plan</span><span>{{ plan.ad }}</span></div>
            <div class="ozet-row"><span>Sure</span><span>{{ plan.gun }} gun</span></div>
            <div class="ozet-row ozet-total"><span>Toplam</span><span>{{ plan.fiyat|int }} TL</span></div>
        </div>

        <form method="POST" action="/odeme/{{ telegram_id }}/{{ plan_key }}/onayla">
            <label>Kart Uzerindeki Isim</label>
            <input type="text" name="kart_isim" required placeholder="Ad Soyad">

            <label>Kart Numarasi</label>
            <input type="text" name="kart_no" required placeholder="1234 5678 9012 3456"
                   maxlength="19" pattern="[0-9 ]{16,19}">

            <div class="row">
                <div>
                    <label>Son Kullanma</label>
                    <input type="text" name="son_kullanma" required placeholder="AA/YY" maxlength="5">
                </div>
                <div>
                    <label>CVV</label>
                    <input type="text" name="cvv" required placeholder="123" maxlength="4">
                </div>
            </div>

            <button type="submit" class="btn">{{ plan.fiyat|int }} TL Ode</button>
        </form>
        <p class="guvenli">Odemeniz guvenli baglanti ile iletilir.</p>
    </div>
</div>
</body>
</html>
"""

BASARI_SAYFASI = """
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Odeme Basarili</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
               background: #f0f2f5; }
        .container { max-width: 500px; margin: 80px auto; padding: 20px; }
        .success { background: white; border-radius: 12px; padding: 40px; text-align: center;
                   box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
        .check { font-size: 60px; margin-bottom: 16px; }
        h2 { color: #16a34a; margin-bottom: 10px; }
        p { color: #666; margin-bottom: 20px; }
        .btn { display: inline-block; padding: 12px 32px; background: #16a34a; color: white;
               border-radius: 8px; text-decoration: none; font-weight: 600; }
    </style>
</head>
<body>
<div class="container">
    <div class="success">
        <div class="check">&#10003;</div>
        <h2>Odeme Basarili!</h2>
        <p>Aboneliginiz {{ bitis_tarihi }} tarihine kadar aktif.<br>
           Telegram'a donup beslenme kocunuzla konusmaya baslayabilirsiniz.</p>
        <a href="https://t.me/{{ bot_username }}" class="btn">Telegram'a Don</a>
    </div>
</div>
</body>
</html>
"""


# ==========================================
# DB YARDIMCILARI (sync wrappers)
# ==========================================
def run_async(coro):
    """Sync Flask handler'dan async DB fonksiyonu çalıştır."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _activate_user(telegram_id: int, plan_key: str):
    """Kullanıcının aboneliğini aktifle."""
    pool = await asyncpg.create_pool(settings.database_url, min_size=1, max_size=2)
    try:
        plan = PLANLAR[plan_key]
        bugun = date.today()
        bitis = bugun + timedelta(days=plan["gun"])

        # Mevcut abonelik varsa üstüne ekle
        row = await pool.fetchrow(
            "SELECT abonelik_bitis FROM users WHERE telegram_id = $1", telegram_id
        )
        if row and row["abonelik_bitis"] and row["abonelik_bitis"] > bugun:
            bitis = row["abonelik_bitis"] + timedelta(days=plan["gun"])

        await pool.execute(
            """UPDATE users SET abonelik_durumu = 'aktif', abonelik_bitis = $2, updated_at = NOW()
               WHERE telegram_id = $1""",
            telegram_id, bitis,
        )

        # Ödeme kaydı
        user = await pool.fetchrow("SELECT id FROM users WHERE telegram_id = $1", telegram_id)
        if user:
            await pool.execute(
                """INSERT INTO odemeler (user_id, telegram_id, tutar, odeme_durumu, plan_tipi,
                       baslangic_tarihi, bitis_tarihi)
                   VALUES ($1, $2, $3, 'basarili', $4, $5, $6)""",
                user["id"], telegram_id, plan["fiyat"], plan_key, bugun, bitis,
            )

        return bitis
    finally:
        await pool.close()


async def _send_telegram_message(telegram_id: int, text: str):
    """Ödeme sonrası kullanıcıya Telegram mesajı gönder."""
    url = f"https://api.telegram.org/bot{settings.telegram_token}/sendMessage"
    data = json.dumps({"chat_id": telegram_id, "text": text}).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req)
    except Exception as e:
        logger.error(f"Telegram mesaj gönderilemedi: {e}")


# ==========================================
# ROUTE'LAR
# ==========================================
@app.route("/")
def anasayfa():
    return redirect("/odeme/0")


@app.route("/odeme/<int:telegram_id>")
def odeme_sayfasi(telegram_id):
    """Plan seçim sayfası."""
    return render_template_string(ODEME_SAYFASI, telegram_id=telegram_id, planlar=PLANLAR)


@app.route("/odeme/<int:telegram_id>/<plan_key>")
def odeme_formu(telegram_id, plan_key):
    """Kart bilgileri formu."""
    if plan_key not in PLANLAR:
        return "Geçersiz plan", 404
    return render_template_string(
        ODEME_FORMU, telegram_id=telegram_id, plan=PLANLAR[plan_key], plan_key=plan_key
    )


@app.route("/odeme/<int:telegram_id>/<plan_key>/onayla", methods=["POST"])
def odeme_onayla(telegram_id, plan_key):
    """
    Ödeme onayı — iyzico entegrasyonu burada yapılacak.
    Şimdilik: form verisini alır, aboneliği aktifler.

    TODO: iyzico API çağrısı eklenecek:
    1. request.form'dan kart bilgilerini al
    2. iyzico.Payment.create() ile ödeme başlat
    3. Başarılıysa aboneliği aktifle
    4. Başarısızsa hata sayfası göster
    """
    if plan_key not in PLANLAR:
        return "Geçersiz plan", 404

    # Aboneliği aktifle
    bitis = run_async(_activate_user(telegram_id, plan_key))

    # Kullanıcıya Telegram'dan bildirim gönder
    plan = PLANLAR[plan_key]
    run_async(_send_telegram_message(
        telegram_id,
        f"Ödemeniz alındı! {plan['ad']} aboneliğiniz {bitis} tarihine kadar aktif.\n\n"
        f"Artık beslenme koçunuzla konuşabilirsiniz!"
    ))

    # Bot username'i .env'den al veya varsayılan kullan
    bot_username = settings.telegram_token.split(":")[0] if settings.telegram_token else ""

    return render_template_string(
        BASARI_SAYFASI, bitis_tarihi=bitis, bot_username=bot_username
    )


# ==========================================
# WEBHOOK — İyzico callback (ileride)
# ==========================================
@app.route("/webhook/iyzico", methods=["POST"])
def iyzico_webhook():
    """İyzico ödeme callback'i — otomatik yenileme için."""
    # TODO: iyzico webhook doğrulama ve işleme
    return "OK", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
