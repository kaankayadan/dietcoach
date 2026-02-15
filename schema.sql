-- Türk Beslenme Koçu — Veritabanı Şeması
-- Her tablo kullanıcıya bağlı, her API çağrısında ilgili veriler çekilip Claude'a context olarak verilir.

-- =============================================
-- 1. KULLANICI PROFİLİ
-- Onboarding'de toplanan tüm bilgiler + hesaplamalar
-- =============================================
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT UNIQUE NOT NULL,
    
    -- Kişisel bilgiler
    isim VARCHAR(100),
    yas INT,
    cinsiyet VARCHAR(10), -- 'erkek' veya 'kadin'
    boy_cm DECIMAL(5,1),
    kilo_kg DECIMAL(5,1),
    vucut_yag_orani DECIMAL(4,1),
    yagsiz_kutle_kg DECIMAL(5,1),
    bel_cevresi_cm DECIMAL(5,1),
    vyo_yontemi VARCHAR(20), -- 'direkt', 'navy', 'bmi_tahmini'
    
    -- Günlük aktivite seviyesi
    aktivite_seviyesi VARCHAR(20), -- 'masa_basi', 'hafif_aktif', 'aktif', 'cok_aktif'
    
    -- Sağlık
    kronik_hastaliklar TEXT[], -- örn: {'tiroid', 'diyabet'}
    sindirim_sorunlari TEXT[],
    alerjiler TEXT[],
    ilaclar JSONB, -- [{"ilac": "levotiroksin", "etki": "tiroid"}]
    
    -- Hedef
    hedef_tip VARCHAR(20), -- 'kayip', 'koruma', 'kazanim'
    hedef_kilo DECIMAL(5,1),
    agresiflik VARCHAR(20), -- 'yavas', 'dengeli', 'agresif'
    
    -- Tercihler
    mutfak_stili VARCHAR(20), -- 'geleneksel', 'modern', 'karma'
    sevilen_yiyecekler TEXT[],
    sevilmeyen_yiyecekler TEXT[],
    ogun_duzeni VARCHAR(30), -- '3_ana_2_ara', '3_ana_1_ara', '4_ogun', 'if'
    if_penceresi VARCHAR(20),
    
    -- Hesaplanan değerler
    bmr DECIMAL(6,1),
    neat DECIMAL(6,1),
    tef DECIMAL(6,1),
    eat_gunluk DECIMAL(6,1),
    tdee DECIMAL(6,1),
    hedef_kalori DECIMAL(6,1),
    
    -- Makro hedefleri
    protein_g DECIMAL(5,1),
    karbonhidrat_g DECIMAL(5,1),
    yag_g DECIMAL(5,1),
    lif_g DECIMAL(5,1),
    
    -- Su hedefi
    su_hedefi_litre DECIMAL(3,1),
    
    -- Durum
    onboarding_step INT DEFAULT 0, -- 0=başlamadı, 1-15=süreçte, 99=tamamlandı
    onboarding_data JSONB DEFAULT '{}', -- tamamlanmamış onboarding verisi
    
    -- Abonelik
    abonelik_durumu VARCHAR(20) DEFAULT 'trial', -- 'trial', 'aktif', 'pasif'
    abonelik_bitis DATE,
    
    -- Zaman damgaları
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    son_tartim_tarihi DATE,
    plan_revizyonu_tarihi DATE
);

-- =============================================
-- 2. AKTİVİTE BİLGİLERİ
-- Kullanıcının egzersiz programı
-- =============================================
CREATE TABLE IF NOT EXISTS aktiviteler (
    id SERIAL PRIMARY KEY,
    user_id INT REFERENCES users(id) ON DELETE CASCADE,
    aktivite_tipi VARCHAR(50), -- 'agirlik', 'kosu', 'yuzme', vb.
    haftalik_siklik INT,
    gunler TEXT[], -- {'pazartesi', 'carsamba', 'cuma'}
    saat VARCHAR(10), -- '07:00'
    sure_dk INT,
    met_degeri DECIMAL(3,1),
    created_at TIMESTAMP DEFAULT NOW()
);

-- =============================================
-- 3. KİLO GEÇMİŞİ
-- Haftalık tartım kayıtları
-- =============================================
CREATE TABLE IF NOT EXISTS kilo_gecmisi (
    id SERIAL PRIMARY KEY,
    user_id INT REFERENCES users(id) ON DELETE CASCADE,
    tarih DATE NOT NULL,
    kilo_kg DECIMAL(5,1) NOT NULL,
    notlar TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- =============================================
-- 4. GÜNLÜK BESLENME PLANI
-- AI tarafından oluşturulan plan
-- =============================================
CREATE TABLE IF NOT EXISTS gunluk_plan (
    id SERIAL PRIMARY KEY,
    user_id INT REFERENCES users(id) ON DELETE CASCADE,
    tarih DATE NOT NULL,
    plan_detay JSONB NOT NULL,
    -- plan_detay yapısı:
    -- {
    --   "ogunler": [
    --     {
    --       "ogun": "kahvalti",
    --       "saat": "08:00",
    --       "yemekler": "2 yumurta, 30g peynir, ...",
    --       "kalori": 350,
    --       "protein": 25,
    --       "karbonhidrat": 30,
    --       "yag": 15,
    --       "lif": 4
    --     }
    --   ],
    --   "toplam_kalori": 1800,
    --   "toplam_protein": 133,
    --   "toplam_karbonhidrat": 200,
    --   "toplam_yag": 60,
    --   "toplam_lif": 30
    -- }
    toplam_kalori DECIMAL(6,1),
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, tarih)
);

-- =============================================
-- 5. ÖĞÜN KAYITLARI
-- Kullanıcının gerçekte yedikleri
-- =============================================
CREATE TABLE IF NOT EXISTS ogun_kayitlari (
    id SERIAL PRIMARY KEY,
    user_id INT REFERENCES users(id) ON DELETE CASCADE,
    tarih DATE NOT NULL DEFAULT CURRENT_DATE,
    ogun_tipi VARCHAR(30), -- 'kahvalti', 'ogle', 'aksam', 'ara_ogun_1', 'ara_ogun_2'
    aciklama TEXT NOT NULL, -- kullanıcının yazdığı: "2 dilim pizza + ayran"
    plan_uyumu VARCHAR(10), -- 'tam', 'kismi', 'farkli'
    
    -- Hesaplanan değerler
    kalori DECIMAL(6,1),
    protein DECIMAL(5,1),
    karbonhidrat DECIMAL(5,1),
    yag DECIMAL(5,1),
    lif DECIMAL(4,1),
    
    created_at TIMESTAMP DEFAULT NOW()
);

-- =============================================
-- 6. GÜNLÜK ÖZET
-- Gün sonu sapma analizi
-- =============================================
CREATE TABLE IF NOT EXISTS gunluk_ozet (
    id SERIAL PRIMARY KEY,
    user_id INT REFERENCES users(id) ON DELETE CASCADE,
    tarih DATE NOT NULL,
    
    planlanan_kalori DECIMAL(6,1),
    tuketilen_kalori DECIMAL(6,1),
    sapma_kalori DECIMAL(6,1),
    
    planlanan_protein DECIMAL(5,1),
    tuketilen_protein DECIMAL(5,1),
    planlanan_karbonhidrat DECIMAL(5,1),
    tuketilen_karbonhidrat DECIMAL(5,1),
    planlanan_yag DECIMAL(5,1),
    tuketilen_yag DECIMAL(5,1),
    
    su_litre DECIMAL(3,1) DEFAULT 0,
    uyum_puani INT, -- 0-100
    notlar TEXT,
    
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, tarih)
);

-- =============================================
-- 7. HAFTALIK ÖZET
-- Telafi hesabı için haftalık toplam
-- =============================================
CREATE TABLE IF NOT EXISTS haftalik_ozet (
    id SERIAL PRIMARY KEY,
    user_id INT REFERENCES users(id) ON DELETE CASCADE,
    hafta_baslangic DATE NOT NULL,
    hafta_bitis DATE NOT NULL,
    
    ortalama_kalori DECIMAL(6,1),
    toplam_sapma DECIMAL(7,1),
    uyum_orani DECIMAL(4,1), -- 0-100
    kilo_degisimi DECIMAL(4,1),
    
    telafi_uygulanacak BOOLEAN DEFAULT FALSE,
    telafi_miktari_gunluk DECIMAL(5,1) DEFAULT 0,
    
    notlar TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, hafta_baslangic)
);

-- =============================================
-- 8. KONUŞMA GEÇMİŞİ
-- Son N mesaj Claude'a context olarak gönderilir
-- =============================================
CREATE TABLE IF NOT EXISTS konusma_gecmisi (
    id SERIAL PRIMARY KEY,
    user_id INT REFERENCES users(id) ON DELETE CASCADE,
    rol VARCHAR(10) NOT NULL, -- 'user' veya 'assistant'
    mesaj TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- =============================================
-- 9. SU TAKİBİ
-- Günlük su tüketim kayıtları (bardak bazında)
-- =============================================
CREATE TABLE IF NOT EXISTS su_takibi (
    id SERIAL PRIMARY KEY,
    user_id INT REFERENCES users(id) ON DELETE CASCADE,
    tarih DATE NOT NULL DEFAULT CURRENT_DATE,
    miktar_ml INT NOT NULL DEFAULT 200, -- 1 bardak = 200ml
    created_at TIMESTAMP DEFAULT NOW()
);

-- =============================================
-- INDEXLER
-- =============================================
CREATE INDEX idx_users_telegram ON users(telegram_id);
CREATE INDEX idx_ogun_user_tarih ON ogun_kayitlari(user_id, tarih);
CREATE INDEX idx_plan_user_tarih ON gunluk_plan(user_id, tarih);
CREATE INDEX idx_ozet_user_tarih ON gunluk_ozet(user_id, tarih);
CREATE INDEX idx_kilo_user_tarih ON kilo_gecmisi(user_id, tarih);
CREATE INDEX idx_konusma_user ON konusma_gecmisi(user_id, created_at DESC);
CREATE INDEX idx_haftalik_user ON haftalik_ozet(user_id, hafta_baslangic);
CREATE INDEX idx_su_user_tarih ON su_takibi(user_id, tarih);
