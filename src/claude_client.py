"""
Claude API Client — Her çağrıda kullanıcının güncel profilini context olarak gönderir.
Bu dosya tüm sistemin beyni: kullanıcıyı "tanıyan" AI burada oluşur.
"""
import anthropic
import logging
from pathlib import Path
from datetime import date, timedelta
from typing import Optional

from src.meal_validator import (
    parse_plan_json, remove_plan_json, validate_plan, format_validation_feedback
)
from src.food_database import BESIN_DB

logger = logging.getLogger(__name__)

# Plan isteklerini tetikleyen anahtar kelimeler
PLAN_TRIGGERS = [
    '/plan', '/haftalik', 'plan oluştur', 'plan yap', 'haftalık plan',
    'diyet listesi', '/alternatif', 'alternatif öner',
]

MAX_VALIDATION_RETRIES = 2


class ClaudeClient:
    def __init__(self, api_key: str, system_prompt_path: str):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.system_prompt = Path(system_prompt_path).read_text(encoding="utf-8")
        # Tüm sorgular için Sonnet 4.5 — tutarlı kalite ve doğruluk
        self.model_light = "claude-sonnet-4-5-20250929"
        self.model_heavy = "claude-sonnet-4-5-20250929"

    def _build_user_context(self, user: dict, recent_meals: list,
                            daily_summary: dict, weekly_summary: dict,
                            todays_plan: dict) -> str:
        """
        Kullanıcının güncel verilerini Claude'a gönderilecek context string'ine dönüştürür.
        Bu fonksiyon her mesajda çağrılır — Claude bu sayede kullanıcıyı 'tanır'.
        """
        if not user:
            return "Kullanıcı henüz kayıtlı değil."

        ctx_parts = []

        # onboarding_data'dan fallback değerleri oku (profil sütunları NULL olabilir)
        ob = user.get('onboarding_data') or {}
        if isinstance(ob, str):
            import json as _json
            try:
                ob = _json.loads(ob)
            except Exception:
                ob = {}

        def _g(field, default=None):
            """Profil sütunundan oku, NULL ise onboarding_data'dan fallback."""
            val = user.get(field)
            if val is not None:
                return val
            return ob.get(field, default)

        # -- Profil --
        sevilen = _g('sevilen_yiyecekler', []) or []
        sevilmeyen = _g('sevilmeyen_yiyecekler', []) or []
        if isinstance(sevilen, str):
            sevilen = [sevilen]
        if isinstance(sevilmeyen, str):
            sevilmeyen = [sevilmeyen]

        ctx_parts.append(f"""## Kullanıcı Profili
İsim: {_g('isim', 'Bilinmiyor')}
Yaş: {_g('yas', 'Belirtilmedi')} | Cinsiyet: {_g('cinsiyet', 'Belirtilmedi')}
Boy: {_g('boy_cm', 'Belirtilmedi')} cm | Kilo: {_g('kilo_kg', 'Belirtilmedi')} kg
Vücut Yağ Oranı: %{_g('vucut_yag_orani', 'Belirtilmedi')} | Yağsız Kütle: {_g('yagsiz_kutle_kg', 'Belirtilmedi')} kg
Aktivite: {_g('aktivite_seviyesi', 'Belirtilmedi')}
Hedef: {_g('hedef_tip', 'Belirtilmedi')} | Hedef Kilo: {_g('hedef_kilo', 'Belirtilmedi')} kg
Mutfak Stili: {_g('mutfak_stili', 'Belirtilmedi')} | Öğün Düzeni: {_g('ogun_duzeni', 'Belirtilmedi')}
Sevilen: {', '.join(sevilen) if sevilen else 'Belirtilmedi'}
Sevilmeyen: {', '.join(sevilmeyen) if sevilmeyen else 'Belirtilmedi'}""")

        # -- Sağlık --
        hastaliklar = _g('kronik_hastaliklar', []) or []
        sindirim = _g('sindirim_sorunlari', []) or []
        alerjiler = _g('alerjiler', []) or []
        ilaclar = _g('ilaclar', []) or []
        if hastaliklar or sindirim or alerjiler or ilaclar:
            ctx_parts.append(f"""## Sağlık Durumu
Kronik: {', '.join(hastaliklar) if hastaliklar else 'Yok'}
Sindirim: {', '.join(sindirim) if sindirim else 'Yok'}
Alerjiler: {', '.join(alerjiler) if alerjiler else 'Yok'}
İlaçlar: {ilaclar if ilaclar else 'Yok'}""")

        # -- Metabolik Değerler --
        bmr = _g('bmr')
        if bmr:
            ctx_parts.append(f"""## Metabolik Değerler
BMR: {bmr} kcal | TDEE: {_g('tdee')} kcal
Hedef Kalori: {_g('hedef_kalori')} kcal
Protein: {_g('protein_g')}g | Karb: {_g('karbonhidrat_g')}g | Yağ: {_g('yag_g')}g | Lif: {_g('lif_g')}g""")

        # -- Bugünkü Plan --
        if todays_plan:
            ctx_parts.append(f"""## Bugünkü Plan
{todays_plan.get('plan_detay', 'Plan henüz oluşturulmadı')}""")

        # -- Son Öğün Kayıtları (bugün) --
        if recent_meals:
            meal_lines = []
            for m in recent_meals:
                meal_lines.append(
                    f"- {m['ogun_tipi']}: {m['aciklama']} "
                    f"({m['kalori']} kcal, P:{m['protein']}g K:{m['karbonhidrat']}g Y:{m['yag']}g)"
                )
            ctx_parts.append(f"""## Bugün Yenilenler
{chr(10).join(meal_lines)}""")

        # -- Günlük Özet --
        if daily_summary:
            ctx_parts.append(f"""## Günlük Durum
Planlanan: {daily_summary.get('planlanan_kalori')} kcal
Tüketilen: {daily_summary.get('tuketilen_kalori')} kcal
Sapma: {daily_summary.get('sapma_kalori')} kcal
Su: {daily_summary.get('su_litre', 0)} litre""")

        # -- Haftalık Özet --
        if weekly_summary:
            ctx_parts.append(f"""## Bu Hafta Özet
Uyum Oranı: %{weekly_summary.get('uyum_orani')}
Toplam Sapma: {weekly_summary.get('toplam_sapma')} kcal
Kilo Değişimi: {weekly_summary.get('kilo_degisimi', 'Tartılmadı')} kg
Telafi: {'Evet, günlük ' + str(weekly_summary.get('telafi_miktari_gunluk')) + ' kcal' if weekly_summary.get('telafi_uygulanacak') else 'Gerek yok'}""")

        # -- Onboarding durumu --
        step = user.get('onboarding_step', 0)
        if step > 0 and step < 99:
            onboarding_data = user.get('onboarding_data') or {}
            if isinstance(onboarding_data, str):
                import json as _json
                try:
                    onboarding_data = _json.loads(onboarding_data)
                except Exception:
                    onboarding_data = {}

            field_labels = {
                'isim': 'İsim', 'yas': 'Yaş', 'cinsiyet': 'Cinsiyet',
                'boy_cm': 'Boy (cm)', 'kilo_kg': 'Kilo (kg)',
                'vucut_yag_orani': 'Vücut Yağ Oranı (%)', 'bel_cevresi_cm': 'Bel Çevresi (cm)',
                'aktivite_detay': 'Aktivite Detayları', 'aktivite_seviyesi': 'Günlük Aktivite Seviyesi',
                'kronik_hastaliklar': 'Kronik Hastalıklar', 'sindirim_sorunlari': 'Sindirim Sorunları',
                'alerjiler': 'Alerjiler', 'ilaclar': 'İlaçlar',
                'hedef_tip': 'Hedef', 'hedef_kilo': 'Hedef Kilo',
                'mutfak_stili': 'Mutfak Tercihi',
                'sevilen_yiyecekler': 'Sevilen Yiyecekler', 'sevilmeyen_yiyecekler': 'Sevilmeyen Yiyecekler',
                'ogun_duzeni': 'Öğün Düzeni',
            }

            collected_lines = []
            for key, value in onboarding_data.items():
                label = field_labels.get(key, key)
                collected_lines.append(f"  ✓ {label}: {value}")

            collected_str = "\n".join(collected_lines) if collected_lines else "  (henüz veri yok)"

            ctx_parts.append(f"""## Onboarding Durumu
Mevcut adım: {step}/14
Toplanan veriler:
{collected_str}

ÖNEMLİ: Yukarıda listelenen verileri TEKRAR SORMA. Sadece henüz toplanmamış bilgileri sor.""")

        # -- Bugünün tarihi --
        ctx_parts.append(f"\n## Tarih: {date.today().isoformat()} ({self._gun_adi()})")

        return "\n\n".join(ctx_parts)

    def _build_food_reference_table(self) -> str:
        """
        BESIN_DB'den dinamik besin referans tablosu oluştur.
        Claude plan üretirken bu tabloyu kullanarak doğru değerler verir.
        """
        lines = [
            "## BESİN DEĞER TABLOSU (100g pişmiş/hazır — programatik referans)",
            "Aşağıdaki değerler BAĞLAYICI referanstır. Plan oluştururken BU değerleri kullan.",
            "Gramaj değişince orantılı hesapla (ör: 150g tavuk göğsü = 31×1.5 = 46.5g protein).",
            "Bu tabloda OLMAYAN bir besin kullanma. Sadece bu listedeki besinlerden plan oluştur.",
            ""
        ]
        # Kategorilere göre grupla
        kategoriler = {}
        for ad, v in BESIN_DB.items():
            kat = v.get("kategori", "diger")
            kategoriler.setdefault(kat, []).append((ad, v))

        kat_labels = {
            "protein": "Protein Kaynakları",
            "sut_urunu": "Süt Ürünleri",
            "karbonhidrat": "Karbonhidrat",
            "baklagil": "Baklagiller",
            "sebze": "Sebzeler",
            "meyve": "Meyveler",
            "kuru_meyve": "Kuru Meyveler",
            "kuruyemis": "Kuruyemişler",
            "yag": "Yağlar",
            "tatlandirici": "Tatlandırıcılar",
            "supplement": "Takviyeler",
            "diger": "Diğer",
        }

        for kat, items in kategoriler.items():
            label = kat_labels.get(kat, kat.title())
            lines.append(f"**{label}:**")
            for ad, v in sorted(items, key=lambda x: x[0]):
                porsiyon = ""
                if "porsiyon_g" in v:
                    porsiyon = f" (1 porsiyon={v['porsiyon_g']}g)"
                lines.append(
                    f"- {ad}{porsiyon}: {v['kalori']} kcal, "
                    f"P:{v['protein']}g, Y:{v['yag']}g, K:{v['karb']}g, L:{v['lif']}g"
                )
            lines.append("")

        return "\n".join(lines)

    def _gun_adi(self) -> str:
        gunler = ['Pazartesi', 'Salı', 'Çarşamba', 'Perşembe', 'Cuma', 'Cumartesi', 'Pazar']
        return gunler[date.today().weekday()]

    def _is_plan_request(self, message: str) -> bool:
        """Mesajın plan isteği olup olmadığını kontrol et."""
        msg_lower = message.lower()
        return any(trigger in msg_lower for trigger in PLAN_TRIGGERS)

    def _select_model(self, message: str, is_onboarding: bool) -> str:
        """Mesaj karmaşıklığına göre model seç — maliyet optimizasyonu."""
        if is_onboarding:
            return self.model_heavy
        if self._is_plan_request(message):
            return self.model_heavy
        return self.model_light

    async def _call_claude(self, system: str, messages: list, model: str, max_tokens: int = 4000) -> str:
        """Claude API'ye tek bir çağrı yap."""
        response = self.client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
        )
        return response.content[0].text

    async def chat(
        self,
        user_message: str,
        user: dict,
        recent_meals: list = None,
        daily_summary: dict = None,
        weekly_summary: dict = None,
        todays_plan: dict = None,
        conversation_history: list = None,
        previous_plan_json: dict = None,
    ) -> str:
        """
        Ana chat fonksiyonu. Her kullanıcı mesajında çağrılır.

        1. Kullanıcı context'ini oluşturur (profil, öğünler, plan, haftalık durum)
        2. Konuşma geçmişini ekler
        3. Claude'a gönderir
        4. Plan isteğiyse validasyon döngüsü çalıştırır
        5. Yanıtı döner
        """
        # Context oluştur
        user_context = self._build_user_context(
            user=user,
            recent_meals=recent_meals or [],
            daily_summary=daily_summary or {},
            weekly_summary=weekly_summary or {},
            todays_plan=todays_plan or {},
        )

        # System prompt + context + besin tablosu
        food_table = self._build_food_reference_table()
        full_system = f"{self.system_prompt}\n\n---\n\n{food_table}\n\n---\n\n{user_context}"

        # Konuşma geçmişi
        messages = []
        if conversation_history:
            for msg in conversation_history:
                messages.append({
                    "role": msg["rol"],
                    "content": msg["mesaj"],
                })

        # Mevcut mesajı ekle
        messages.append({"role": "user", "content": user_message})

        # Model seç
        is_onboarding = user.get('onboarding_step', 0) > 0 and user.get('onboarding_step', 0) < 99
        model = self._select_model(user_message, is_onboarding)

        # Plan isteği mi?
        if self._is_plan_request(user_message) and not is_onboarding:
            return await self._generate_validated_plan(
                full_system=full_system,
                messages=messages,
                model=model,
                user=user,
                previous_plan_json=previous_plan_json,
            )

        # Normal chat
        return await self._call_claude(full_system, messages, model)

    async def _generate_validated_plan(
        self,
        full_system: str,
        messages: list,
        model: str,
        user: dict,
        previous_plan_json: Optional[dict] = None,
    ) -> str:
        """
        Plan üret → doğrula → hata varsa düzelt döngüsü.

        Max MAX_VALIDATION_RETRIES deneme yapar.
        Her denemede Claude'a önceki hataları gönderir.
        """
        current_messages = list(messages)  # Kopyala
        best_response = None
        best_errors_count = float('inf')

        for attempt in range(1 + MAX_VALIDATION_RETRIES):
            # Claude'dan yanıt al
            response = await self._call_claude(
                full_system, current_messages, model, max_tokens=4000
            )

            # JSON metadata'sını parse et
            plan_json = parse_plan_json(response)

            if not plan_json:
                # JSON yoksa — ilk denemede model formatı takip etmedi
                if attempt == 0:
                    logger.warning("Plan yanıtında PLAN_JSON bulunamadı, validasyon atlanıyor")
                return response

            # Validate
            result = validate_plan(plan_json, user, previous_plan_json)

            logger.info(
                f"Plan validasyonu (deneme {attempt+1}): "
                f"{'BAŞARILI' if result['valid'] else 'HATALI'} — "
                f"{len(result['errors'])} hata, {len(result['warnings'])} uyarı"
            )

            # En iyi sonucu takip et
            if len(result['errors']) < best_errors_count:
                best_errors_count = len(result['errors'])
                best_response = response

            if result['valid']:
                # Plan geçerli — JSON'ı temizleyip döndür
                clean_response = remove_plan_json(response)
                # Doğrulanmış toplamları yanıta ekle
                corrected = result['corrected_totals']
                if corrected:
                    clean_response += (
                        f"\n\n_Doğrulanmış toplamlar: "
                        f"{corrected['kalori']} kcal | "
                        f"P: {corrected['protein']}g | "
                        f"Y: {corrected['yag']}g | "
                        f"K: {corrected['karb']}g | "
                        f"Lif: {corrected['lif']}g_"
                    )
                return clean_response

            # Geçersiz — son deneme değilse feedback gönder
            if attempt < MAX_VALIDATION_RETRIES:
                feedback = format_validation_feedback(result)
                # Claude'a asistan yanıtı + kullanıcı feedback'i ekle
                current_messages.append({"role": "assistant", "content": response})
                current_messages.append({"role": "user", "content": feedback})
                logger.info(f"Plan düzeltme isteği gönderiliyor (deneme {attempt+2})")

        # Tüm denemeler bitti — en iyi sonucu dön
        logger.warning(f"Plan {MAX_VALIDATION_RETRIES+1} denemede de tam doğrulanamadı, en iyi sonuç döndürülüyor")

        clean_response = remove_plan_json(best_response)

        # Son doğrulama sonuçlarını uyarı olarak ekle
        if result and result.get('corrected_totals'):
            corrected = result['corrected_totals']
            clean_response += (
                f"\n\n_Sistem notu: Programatik hesaplanan toplamlar: "
                f"{corrected['kalori']} kcal | "
                f"P: {corrected['protein']}g | "
                f"Y: {corrected['yag']}g | "
                f"K: {corrected['karb']}g | "
                f"Lif: {corrected['lif']}g_"
            )

        return clean_response
