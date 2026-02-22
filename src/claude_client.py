"""
Claude API Client — Her çağrıda kullanıcının güncel profilini context olarak gönderir.
Bu dosya tüm sistemin beyni: kullanıcıyı "tanıyan" AI burada oluşur.
"""
import logging
import anthropic
from pathlib import Path
from datetime import date, timedelta
from src.meal_validator import (
    extract_mealplan_json,
    fallback_extract_plan_from_text,
    response_has_meal_structure,
    validate_plan,
    build_correction_summary,
    patch_response_totals,
    patch_ingredient_grams,
)

logger = logging.getLogger(__name__)


class ClaudeClient:
    def __init__(self, api_key: str, system_prompt_path: str):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.system_prompt = Path(system_prompt_path).read_text(encoding="utf-8")
        # Modüler prompt parçaları — duruma göre eklenir
        modules_dir = Path(system_prompt_path).parent / "modules"
        self._modules = {}
        for mod_file in modules_dir.glob("*.md"):
            content = mod_file.read_text(encoding="utf-8")
            self._modules[mod_file.stem] = content
            logger.info(f"Prompt modülü yüklendi: {mod_file.stem} ({len(content.split())} kelime)")
        # Basit sorgular için ucuz model, plan oluşturma için güçlü model
        self.model_light = "claude-haiku-4-5-20251001"    # Besin sorgusu, kısa yanıt
        self.model_heavy = "claude-sonnet-4-5-20250929"   # Plan oluşturma, onboarding
    
    def _build_user_context(self, user: dict, recent_meals: list,
                            daily_summary: dict, weekly_summary: dict,
                            todays_plan: dict, weekly_meals: list = None,
                            weekly_water: list = None,
                            todays_water: dict = None) -> str:
        """
        Kullanıcının güncel verilerini Claude'a gönderilecek context string'ine dönüştürür.
        Bu fonksiyon her mesajda çağrılır — Claude bu sayede kullanıcıyı 'tanır'.
        """
        if not user:
            return "Kullanıcı henüz kayıtlı değil."
        
        ctx_parts = []
        
        # -- Profil --
        ctx_parts.append(f"""## Kullanıcı Profili
İsim: {user.get('isim', 'Bilinmiyor')}
Yaş: {user.get('yas')} | Cinsiyet: {user.get('cinsiyet')}
Boy: {user.get('boy_cm')} cm | Kilo: {user.get('kilo_kg')} kg
Vücut Yağ Oranı: %{user.get('vucut_yag_orani')} | Yağsız Kütle: {user.get('yagsiz_kutle_kg')} kg
Aktivite: {user.get('aktivite_seviyesi')}
Hedef: {user.get('hedef_tip')} | Hedef Kilo: {user.get('hedef_kilo', 'Belirtilmedi')} kg
Mutfak Stili: {user.get('mutfak_stili')} | Öğün Düzeni: {user.get('ogun_duzeni')}
Sevilen: {', '.join(user.get('sevilen_yiyecekler', []) or [])}
Sevilmeyen: {', '.join(user.get('sevilmeyen_yiyecekler', []) or [])}""")
        
        # -- Sağlık --
        hastaliklar = user.get('kronik_hastaliklar') or []
        sindirim = user.get('sindirim_sorunlari') or []
        alerjiler = user.get('alerjiler') or []
        ilaclar = user.get('ilaclar') or []
        if hastaliklar or sindirim or alerjiler or ilaclar:
            ctx_parts.append(f"""## Sağlık Durumu
Kronik: {', '.join(hastaliklar) if hastaliklar else 'Yok'}
Sindirim: {', '.join(sindirim) if sindirim else 'Yok'}
Alerjiler: {', '.join(alerjiler) if alerjiler else 'Yok'}
İlaçlar: {ilaclar if ilaclar else 'Yok'}""")
        
        # -- Metabolik Değerler --
        if user.get('bmr'):
            ctx_parts.append(f"""## Metabolik Değerler
BMR: {user['bmr']} kcal | TDEE: {user['tdee']} kcal
Hedef Kalori: {user['hedef_kalori']} kcal
Protein: {user['protein_g']}g | Karb: {user['karbonhidrat_g']}g | Yağ: {user['yag_g']}g | Lif: {user['lif_g']}g""")
        
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
        
        # -- Bugünkü Su Durumu --
        if todays_water:
            su_hedef = user.get('su_hedefi_litre', 2.5)
            toplam_litre = (todays_water.get('toplam_ml', 0) or 0) / 1000
            ctx_parts.append(f"""## Bugünkü Su Tüketimi
İçilen: {todays_water.get('bardak', 0)} bardak ({toplam_litre:.1f} litre)
Hedef: {su_hedef} litre
Kalan: {max(0, float(su_hedef or 2.5) - toplam_litre):.1f} litre""")

        # -- Haftalık Yemek Hafızası (son 7 gün) --
        if weekly_meals:
            days = {}
            for m in weekly_meals:
                tarih_str = str(m['tarih'])
                if tarih_str not in days:
                    days[tarih_str] = []
                days[tarih_str].append(m)

            meal_lines = []
            for tarih_str, meals in sorted(days.items()):
                gun_toplam_kcal = sum(float(m.get('kalori') or 0) for m in meals)
                gun_meals = ", ".join(
                    f"{m['ogun_tipi']}: {m['aciklama']} ({m.get('kalori', '?')} kcal)"
                    for m in meals
                )
                meal_lines.append(f"**{tarih_str}** ({gun_toplam_kcal:.0f} kcal): {gun_meals}")

            ctx_parts.append(f"""## Haftalık Yemek Geçmişi (Son 7 Gün)
{chr(10).join(meal_lines)}""")

        # -- Haftalık Su Geçmişi (son 7 gün) --
        if weekly_water:
            water_lines = []
            for w in weekly_water:
                litre = (w.get('toplam_ml', 0) or 0) / 1000
                water_lines.append(f"- {w['tarih']}: {w['bardak']} bardak ({litre:.1f} L)")
            ctx_parts.append(f"""## Haftalık Su Geçmişi (Son 7 Gün)
{chr(10).join(water_lines)}""")

        # -- Onboarding durumu --
        step = user.get('onboarding_step', 0)
        if step > 0 and step < 99:
            ctx_parts.append(f"""## Onboarding Durumu
Mevcut adım: {step}/15
Toplanan veriler: {user.get('onboarding_data', {})}""")

        # -- Bugünün tarihi --
        ctx_parts.append(f"\n## Tarih: {date.today().isoformat()} ({self._gun_adi()})")
        
        return "\n\n".join(ctx_parts)
    
    def _gun_adi(self) -> str:
        gunler = ['Pazartesi', 'Salı', 'Çarşamba', 'Perşembe', 'Cuma', 'Cumartesi', 'Pazar']
        return gunler[date.today().weekday()]

    def _compose_system_prompt(self, user: dict, is_plan: bool, is_onboarding: bool) -> str:
        """
        Duruma göre modüler system prompt oluştur.
        Core prompt her zaman gönderilir, modüller koşullu eklenir.
        """
        parts = [self.system_prompt]

        # Plan isteğinde: porsiyon kuralları, yağ dengeleme, örnek format
        if is_plan and "plan_reference" in self._modules:
            parts.append(self._modules["plan_reference"])

        # Onboarding sürecinde: adımlar, metadata formatı, hesaplama kuralları
        if is_onboarding and "onboarding" in self._modules:
            parts.append(self._modules["onboarding"])

        # Sağlık koşulları varsa: diyet kısıtlamaları, ilaç etkileşimleri
        has_health = bool(
            user.get("kronik_hastaliklar")
            or user.get("sindirim_sorunlari")
            or user.get("ilaclar")
        )
        if has_health and "health_rules" in self._modules:
            parts.append(self._modules["health_rules"])

        return "\n\n---\n\n".join(parts)
    
    # Plan oluşturma tetikleyicileri
    PLAN_TRIGGERS = [
        '/plan', '/haftalik', 'plan oluştur', 'plan yap', 'plan hazırla',
        'yeni plan', 'haftalık plan', 'diyet listesi', 'diyet planı',
        '/alternatif', 'alternatif öner',
        'planımı', 'planimi', 'plan ver', 'plan iste',
        'yarınki plan', 'yarinki plan', 'yarın plan', 'yarin plan',
        'bugünkü plan', 'bugunku plan', 'günlük plan', 'gunluk plan',
        'plan öner', 'plan oner',
        'ne yesem', 'ne yemeliyim', 'öğün öner', 'ogun oner',
        'yemek öner', 'yemek oner', 'liste yap', 'liste ver',
    ]

    def _is_plan_request(self, message: str) -> bool:
        """Mesaj plan oluşturma isteği mi?"""
        msg_lower = message.lower()
        return any(trigger in msg_lower for trigger in self.PLAN_TRIGGERS)

    def _select_model(self, message: str, is_onboarding: bool) -> str:
        """Mesaj karmaşıklığına göre model seç — maliyet optimizasyonu."""
        if is_onboarding:
            logger.info(f"Model seçimi: {self.model_heavy} (onboarding)")
            return self.model_heavy
        if self._is_plan_request(message):
            logger.info(f"Model seçimi: {self.model_heavy} (plan isteği)")
            return self.model_heavy
        logger.info(f"Model seçimi: {self.model_light} (genel sorgu)")
        return self.model_light
    
    def _validate_and_patch_plan(
        self, response_text: str, is_plan: bool, user: dict
    ) -> tuple:
        """
        Plan yanıtını doğrula ve düzelt.

        Returns: (patched_text, result_dict) — result_dict None olabilir.
        """
        # Plan yanıtlarını doğrula
        try:
            plan_json = extract_mealplan_json(response_text)
        except Exception as e:
            logger.warning(f"MEALPLAN_JSON parse hatası: {e}")
            plan_json = None

        # JSON yoksa → fallback text parser
        # Hem açık plan isteğinde hem de yanıt plan yapısı içeriyorsa dene
        # (Claude JSON bloğu üretmemiş olabilir veya kullanıcı mesajı
        #  plan trigger'larına uymamış olabilir)
        if not plan_json:
            looks_like_plan = response_has_meal_structure(response_text)
            if is_plan or looks_like_plan:
                if not is_plan and looks_like_plan:
                    logger.info(
                        "Plan isteği algılanmamıştı ama yanıt plan yapısı içeriyor "
                        "— fallback parser devreye giriyor"
                    )
                else:
                    logger.warning(
                        "MEALPLAN_JSON bulunamadı — fallback text parser devreye giriyor"
                    )
                try:
                    plan_json = fallback_extract_plan_from_text(response_text)
                    if plan_json:
                        logger.info(
                            f"Fallback parser başarılı: "
                            f"{len(plan_json.get('ogunler', []))} öğün çıkarıldı"
                        )
                    else:
                        logger.warning("Fallback parser da plan çıkaramadı")
                except Exception as e:
                    logger.error(f"Fallback parser hatası: {e}")
                    plan_json = None

        if not plan_json:
            return response_text, None

        try:
            result = validate_plan(plan_json, user or {})
        except Exception as e:
            logger.error(f"Plan doğrulama hatası: {e}")
            return response_text, None

        # food_database düzeltmeleri
        if result.get("db_corrections"):
            logger.info(
                f"food_database düzeltme: {len(result['db_corrections'])} besin düzeltildi"
            )
            for c in result["db_corrections"]:
                logger.info(f"  - {c}")

        if result["errors"]:
            logger.info(
                f"Plan doğrulama: {len(result['errors'])} hata — "
                f"Python tarafında düzeltiliyor (2. API çağrısı yok)"
            )
            for err in result["errors"]:
                logger.debug(f"  - {err}")

        # Her durumda düzeltilmiş toplamları uygula
        if result.get("corrected_plan"):
            # Önce gramaj değişikliklerini uygula (ör: 180g→120g)
            response_text = patch_ingredient_grams(
                response_text, plan_json, result["corrected_plan"]
            )
            # Sonra makro toplamlarını düzelt
            response_text = patch_response_totals(
                response_text, result["corrected_plan"]
            )

        if result["warnings"]:
            logger.info(
                f"Plan uyarıları: {len(result['warnings'])} uyarı"
            )
            for w in result["warnings"]:
                logger.debug(f"  - {w}")

        return response_text, result

    async def chat(
        self,
        user_message: str,
        user: dict,
        recent_meals: list = None,
        daily_summary: dict = None,
        weekly_summary: dict = None,
        todays_plan: dict = None,
        conversation_history: list = None,
        weekly_meals: list = None,
        weekly_water: list = None,
        todays_water: dict = None,
    ) -> str:
        """
        Ana chat fonksiyonu. Her kullanıcı mesajında çağrılır.
        
        1. Kullanıcı context'ini oluşturur (profil, öğünler, plan, haftalık durum)
        2. Konuşma geçmişini ekler
        3. Claude'a gönderir
        4. Yanıtı döner
        """
        # Context oluştur
        user_context = self._build_user_context(
            user=user,
            recent_meals=recent_meals or [],
            daily_summary=daily_summary or {},
            weekly_summary=weekly_summary or {},
            todays_plan=todays_plan or {},
            weekly_meals=weekly_meals or [],
            weekly_water=weekly_water or [],
            todays_water=todays_water or {},
        )

        # Model ve durumu belirle
        is_onboarding = user.get('onboarding_step', 0) > 0 and user.get('onboarding_step', 0) < 99
        model = self._select_model(user_message, is_onboarding)
        is_plan = self._is_plan_request(user_message)

        # Modüler system prompt + context
        system_prompt = self._compose_system_prompt(user or {}, is_plan, is_onboarding)
        full_system = f"{system_prompt}\n\n---\n\n{user_context}"

        # Konuşma geçmişi (son 15 mesaj)
        messages = []
        if conversation_history:
            for msg in conversation_history[-15:]:
                messages.append({
                    "role": msg["rol"],
                    "content": msg["mesaj"],
                })

        # Mevcut mesajı ekle
        messages.append({"role": "user", "content": user_message})

        # Plan isteklerinde daha yüksek max_tokens (JSON truncation önleme)
        max_tokens = 12000 if is_plan else 4000

        # Plan isteğinde hedefleri kullanıcı mesajına ekle (Claude daha iyi dikkat eder)
        if is_plan and user.get("hedef_kalori"):
            hedef_prefix = (
                f"[HEDEFLER: {user.get('hedef_kalori')} kcal | "
                f"P: {user.get('protein_g', '?')}g | "
                f"Y: {user.get('yag_g', '?')}g | "
                f"K: {user.get('karbonhidrat_g', '?')}g | "
                f"L: {user.get('lif_g', '?')}g]\n\n"
            )
            messages[-1]["content"] = hedef_prefix + messages[-1]["content"]

        # Claude API çağrısı
        response = self.client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=full_system,
            messages=messages,
        )

        response_text = response.content[0].text

        # ── Haiku plan ürettiyse → Sonnet'e yükselt ──────────────────
        # Kullanıcı mesajı plan trigger'larına uymamış ama Haiku plan
        # yapısı üretmiş olabilir. Bu durumda Sonnet ile yeniden üret.
        if model == self.model_light and response_has_meal_structure(response_text):
            logger.warning(
                "Haiku plan yapısı üretti ama plan isteği algılanmamıştı — "
                "Sonnet ile yeniden üretiliyor"
            )
            model = self.model_heavy
            is_plan = True
            max_tokens = 12000
            # System prompt'u plan modülleri ile yeniden oluştur
            system_prompt = self._compose_system_prompt(user or {}, True, is_onboarding)
            full_system = f"{system_prompt}\n\n---\n\n{user_context}"
            # Hedef bilgisini ekle
            if user.get("hedef_kalori") and not any(
                "[HEDEFLER:" in m.get("content", "") for m in messages
            ):
                hedef_prefix = (
                    f"[HEDEFLER: {user.get('hedef_kalori')} kcal | "
                    f"P: {user.get('protein_g', '?')}g | "
                    f"Y: {user.get('yag_g', '?')}g | "
                    f"K: {user.get('karbonhidrat_g', '?')}g | "
                    f"L: {user.get('lif_g', '?')}g]\n\n"
                )
                messages[-1]["content"] = hedef_prefix + messages[-1]["content"]

            response = self.client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=full_system,
                messages=messages,
            )
            response_text = response.content[0].text
            logger.info(f"Sonnet ile yeniden üretim tamamlandı")

        # Truncation kontrolü — max_tokens'a ulaşıldıysa JSON eksik olabilir
        if response.stop_reason == "max_tokens":
            logger.warning(
                f"Yanıt max_tokens ({max_tokens}) nedeniyle kesildi! "
                f"Model: {model}, Plan isteği: {is_plan}"
            )
            # Plan isteklerinde truncation olduysa daha yüksek token ile tekrar dene
            if is_plan and max_tokens < 16000:
                logger.info("Truncation nedeniyle plan isteği 16000 token ile yeniden deneniyor...")
                retry_response = self.client.messages.create(
                    model=model,
                    max_tokens=16000,
                    system=full_system,
                    messages=messages,
                )
                if retry_response.stop_reason != "max_tokens":
                    response_text = retry_response.content[0].text
                    logger.info("Retry başarılı — tam yanıt alındı")
                else:
                    logger.error("Retry'da da truncation oldu — orijinal yanıt kullanılacak")

        # Plan yanıtını doğrula, düzelt ve gerekirse kalori retry uygula
        response_text, result = self._validate_and_patch_plan(
            response_text, is_plan, user
        )

        # ── Kalori kontrolü + otomatik retry ──────────────────────
        # Düzeltilmiş plan hedeften >%15 düşükse, Claude'a tekrar sor
        # is_plan veya result varsa (fallback ile plan tespit edilmişse) retry yap
        if (
            result
            and result.get("corrected_totals")
            and user.get("hedef_kalori")
        ):
            hedef_kcal = float(user["hedef_kalori"])
            actual_kcal = float(result["corrected_totals"]["kcal"])
            sapma_pct = (hedef_kcal - actual_kcal) / hedef_kcal if hedef_kcal > 0 else 0

            # Kalori düşükse VEYA yüksekse retry tetikle
            if sapma_pct > 0.10 or sapma_pct < -0.15:
                yuksek_mi = sapma_pct < 0
                yon = "yüksek" if yuksek_mi else "düşük"
                logger.warning(
                    f"Kalori hedeften çok {yon}: {actual_kcal:.0f} vs {hedef_kcal:.0f} kcal "
                    f"({sapma_pct*100:+.0f}%) — retry tetikleniyor"
                )

                # Retry mesajı: Claude'a açık talimat ver
                actual_p = result["corrected_totals"]["p"]
                actual_y = result["corrected_totals"]["y"]
                actual_k = result["corrected_totals"]["k"]

                if yuksek_mi:
                    retry_msg = (
                        f"Oluşturduğun plan: {actual_kcal:.0f} kcal "
                        f"(P:{actual_p:.0f}g Y:{actual_y:.0f}g K:{actual_k:.0f}g). "
                        f"Hedefler: {hedef_kcal:.0f} kcal "
                        f"(P:{user.get('protein_g', '?')}g "
                        f"Y:{user.get('yag_g', '?')}g "
                        f"K:{user.get('karbonhidrat_g', '?')}g). "
                        f"Plan hedeflerin ÇOK üstünde ({actual_kcal - hedef_kcal:.0f} kcal fazla). "
                        f"Lütfen aynı formatta yeni bir plan oluştur: "
                        f"porsiyonları küçült (et/balık 80-120g, baklagil 80-120g), "
                        f"zeytinyağı miktarını azalt (günde toplam 2 yemek kaşığı maks), "
                        f"protein bütçesine dikkat et (günlük TEK ana et porsiyonu), "
                        f"günlük toplamı {hedef_kcal:.0f} kcal ±%5 hedefine yaklaştır."
                    )
                else:
                    retry_msg = (
                        f"Oluşturduğun plan: {actual_kcal:.0f} kcal "
                        f"(P:{actual_p:.0f}g Y:{actual_y:.0f}g K:{actual_k:.0f}g). "
                        f"Hedefler: {hedef_kcal:.0f} kcal "
                        f"(P:{user.get('protein_g', '?')}g "
                        f"Y:{user.get('yag_g', '?')}g "
                        f"K:{user.get('karbonhidrat_g', '?')}g). "
                        f"Plan hedeflere çok uzak. "
                        f"Lütfen aynı formatta yeni bir plan oluştur: "
                        f"karbonhidrat kaynaklarının porsiyonlarını büyüt "
                        f"(bulgur 200g, baklagil 200g gibi), "
                        f"protein bütçesine dikkat et (günlük TEK ana et porsiyonu), "
                        f"günlük toplamı {hedef_kcal:.0f} kcal ±%5 hedefine yaklaştır."
                    )

                # Mevcut konuşmaya asistan yanıtı ve retry mesajını ekle
                retry_messages = list(messages)
                retry_messages.append({"role": "assistant", "content": response_text})
                retry_messages.append({"role": "user", "content": retry_msg})

                try:
                    retry_response = self.client.messages.create(
                        model=model,
                        max_tokens=max_tokens,
                        system=full_system,
                        messages=retry_messages,
                    )
                    retry_text = retry_response.content[0].text

                    # Retry yanıtını da doğrula
                    retry_text, retry_result = self._validate_and_patch_plan(
                        retry_text, True, user
                    )

                    # Retry daha iyi mi kontrol et
                    if retry_result and retry_result.get("corrected_totals"):
                        retry_kcal = float(retry_result["corrected_totals"]["kcal"])
                        retry_sapma = abs(hedef_kcal - retry_kcal) / hedef_kcal if hedef_kcal > 0 else 1
                        orig_sapma = abs(hedef_kcal - actual_kcal) / hedef_kcal if hedef_kcal > 0 else 1

                        if retry_sapma < orig_sapma:
                            logger.info(
                                f"Retry başarılı: {retry_kcal:.0f} kcal "
                                f"(sapma %{retry_sapma*100:.0f} vs önceki %{orig_sapma*100:.0f})"
                            )
                            response_text = retry_text
                        else:
                            logger.warning(
                                f"Retry iyileştirme sağlamadı: {retry_kcal:.0f} kcal "
                                f"(sapma %{retry_sapma*100:.0f}) — orijinal plan korunuyor"
                            )
                    else:
                        logger.warning("Retry yanıtı doğrulanamadı — orijinal plan korunuyor")

                except Exception as e:
                    logger.error(f"Kalori retry hatası: {e} — orijinal plan korunuyor")

        return response_text
