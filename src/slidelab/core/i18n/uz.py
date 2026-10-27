TEXTS: dict[str, str] = {
    # --- til va salomlashish ---
    "lang_pick": "Выберите язык · Tilni tanlang · Choose language",
    "lang_name": "O‘zbekcha",
    "welcome": (
        "<b>SlideLab</b>\n"
        "Mavzuingizga mos dizayndagi taqdimotlar.\n\n"
        "Avval — bepul muqova. Yoqsagina to‘laysiz.\n\n"
        "Ma’ruza yoki topshiriqni shu yerga forward qiling — ikki bosishda buyurtma qilaman."
    ),
    "welcome_back": "<b>SlideLab</b>\nNima yordam kerak?",
    "error": "Nimadir xato ketdi. Qaytadan urinib ko‘ring — yoki @{admin} ga yozing.",
    "use_buttons": "Yuqoridagi tugmalardan birini tanlang.",
    "send_text": "Iltimos, matn bilan yozing.",
    "cancelled": "Bekor qildim. Bosh menyudasiz.",
    # --- menyu ---
    "btn_new": "Yangi taqdimot",
    "btn_app": "Ilovada buyurtma",
    "btn_orders": "Buyurtmalarim",
    "btn_prices": "Narxlar",
    "btn_examples": "Namunalar",
    "btn_help": "Savollar",
    "btn_open_app": "SlideLab’ni ochish",
    # --- narxlar va paketlar ---
    "prices": (
        "<b>Narxlar</b>\n\n"
        "10 slaydgacha — {s10} so‘m\n"
        "11–20 slayd — {s20} so‘m\n"
        "21–30 slayd — {s30} so‘m\n\n"
        "10 slaydgacha birinchi buyurtma — <b>{first} so‘m</b>\n\n"
        "Shoshilinch — +{urgent}% (20 slaydgacha)\n"
        "Matnni yozib berish — +{text}\n"
        "Chiqish uchun konspekt — +{notes}\n\n"
        "<i>Narxga kiradi: mavzuga mos dizayn, rasm va grafiklar, PPTX va PDF, ikki tuzatish.</i>"
    ),
    "btn_packages": "Paketlar — arzonroq",
    "packages": "<b>Paketlar</b>\nHar bir taqdimot arzonroq. Qoldiq yonmaydi — yangi paketga o‘tadi.",
    "package_line": "<b>{name}</b> — {price} so‘m · donasi {per} · {days} kun",
    "plan_week": "2 ta taqdimot",
    "plan_month": "4 ta taqdimot",
    "plan_vip": "VIP · 10 ta taqdimot",
    "packages_note": "<i>21–30 slayd paketdan 2 ta yechadi. Shoshilinch va matn alohida to‘lanadi.</i>",
    "my_package": "\n\n<b>Paketingiz</b>: {total} tadan {left} ta qoldi, {date} gacha.",
    "btn_buy": "{plan} — {price} so‘m",
    "gift_promo": "\n\n🎁 {date} gacha — har qanday paketga Telegramda sovg‘a.",
    "pkg_requested": "«{plan}» paketi. Rekvizitlar quyida — to‘lovdan so‘ng o‘zim yoqaman.",
    "pkg_on": "<b>«{plan}» paketi yoqildi</b>\nMavjud: {left} · {date} gacha.\nOdatdagidek buyurtma bering — paketdan yechiladi.",
    "gift_text": "SlideLab’ni tanlaganingiz uchun rahmat! Taqdimotlaringiz a’lo bo‘lsin.",
    "gift_sent": "🎁 Paket uchun sovg‘a — allaqachon Telegram profilingizda.",
    # --- namunalar va savollar ---
    "examples": "<b>Ishlar namunasi</b>\nHar bir taqdimot — mavzuga mos o‘z uslubida.",
    "examples_channel": "Barcha ishlar va uslublar — {channel} kanalida",
    "examples_soon": "Namunalar tez orada. Hozircha buyurtma bering — mavzuingiz uslubidagi muqova bepul.",
    "help": "<b>Savollar</b>",
    "btn_ask": "Menejerdan so‘rash",
    "btn_language": "Til",
    "ask_prompt": "Savolingizni bitta xabarda yozing — menejerga yetkazaman. Javob shu yerga keladi.",
    "question_sent": "Yubordim. Shu yerda, chatda javob beramiz.",
    "menu_updated": "Menyu yangilandi — tugmalar pastda.",
    "stale_button": "Bu tugma botning eski versiyasidan. Buyurtmani «Buyurtmalarim»da oching — u yerda yangi tugmalar bor.",
    "manager_reply": "<b>SlideLab javobi</b>",
    "paysupport": "To‘lov va qaytarish bo‘yicha — shu yerga yoki @{admin} ga yozing. Ish boshlanishidan oldin bekor qilinsa, yulduzlarni qaytaramiz.",
    # --- anketa ---
    "step": "<i>{total} qadamdan {n}-qadam</i>",
    "ask_topic": "<b>Taqdimot mavzusi</b>\nMasalan: <i>1990-yildan keyingi Yaponiya iqtisodiyoti</i>",
    "topic_short": "Mavzu juda qisqa — kamida 3 ta belgi.",
    "topic_long": "Mavzu 300 belgidan uzun — qisqartiring, iltimos.",
    "ask_slides": "<b>Nechta slayd?</b>",
    "slides_s10": "10 gacha",
    "slides_s20": "11–20",
    "slides_s30": "21–30",
    "ask_deadline": "<b>Muddat</b>",
    "dl_urgent": "Shoshilinch · +50%",
    "dl_normal": "Odatiy — chatda kelishamiz",
    "dl_relaxed": "Shoshilmayman",
    "ask_plang": "<b>Taqdimot tili</b>",
    "plang_ru": "Русский",
    "plang_uz": "O‘zbek",
    "plang_en": "English",
    "ask_design": "<b>Dizayn</b>\nO‘z shabloningiz yoki namunangiz bormi — yoki mavzuga moslab o‘ylab topaylikmi?",
    "ds_ours": "Mavzuga moslab qiling",
    "ds_own": "Shablonim bor",
    "ask_template": (
        "<b>Shablon</b>\nHavolani yuboring (Canva, Google Slides, Figma, Disk), «Havolaga ega barcha» ruxsati bilan "
        "— yoki faylning o‘zini."
    ),
    "btn_template_later": "Keyinroq yuboraman",
    "ask_extras": "<b>Qo‘shimcha</b>\nKeraklisini belgilang va «Keyingi»ni bosing.",
    "x_text": "Matnni yozib berish · +5 000",
    "x_notes": "Chiqish uchun konspekt · +5 000",
    "x_humor": "Hazil bilan · bepul",
    "btn_next": "Keyingi",
    "ask_files": "<b>Materiallar</b>\nMa’ruza, qo‘llanma, o‘qituvchi talablari — fayl yoki matn yuboring. Bir nechtasi ham bo‘ladi.",
    "files_got": "Qabul qilindi: {n}. Yana — yoki «Tayyor».",
    "btn_done": "Tayyor",
    "btn_skip": "Material yo‘q",
    "ask_contact": "<b>Siz bilan qanday bog‘lanamiz?</b>\nTugmani bosing — raqamingizni yuboraman. Yoki nikni yozing.",
    "btn_phone": "Raqamni yuborish",
    "summary": (
        "<b>Arizani tekshiring</b>\n\n"
        "{topic}\n"
        "{slides} slayd · {deadline}\n"
        "{plang} · {design}{extras}{files}\n\n"
        "{price}"
    ),
    "summary_files": "\nMateriallar: {n}",
    "price_cash": "<b>{price} so‘m</b>\n<i>Hozir to‘lash shart emas — avval bepul muqova yuboramiz.</i>",
    "price_first": " · birinchi buyurtmaga chegirma",
    "price_package": "<b>Paketdan</b>: {cost}, {left} ta qoladi",
    "price_package_extra": "<b>Paketdan</b>: {cost}, {left} ta qoladi\nQo‘shimcha — {price} so‘m",
    "btn_send": "Arizani yuborish",
    "btn_restart": "Qaytadan to‘ldirish",
    "btn_cancel": "Bekor qilish",
    "humor_label": "hazil bilan",
    "text_label": "matn yozib berish",
    "notes_label": "konspekt",
    # --- ariza qabul qilindi ---
    "order_created": (
        "<b>#{id} buyurtma qabul qilindi</b>\nBepul muqova tayyorlayapmiz — shu yerga yuboraman.{package}"
    ),
    "order_created_files": "\n\nMateriallar bormi? Istalgan chatdan shu yerga forward qiling — telefonga saqlash shart emas.",
    "order_created_tpl": "\n\nShabloningizni yuboring: fayl yoki ochiq havola.",
    "package_used": "\n\nPaketdan {cost} ta yechildi, {left} ta qoldi.",
    "package_extra": " Qo‘shimcha — {price} so‘m.",
    "package_empty": "\n\nPaketdagi taqdimotlar tugadi — bu buyurtma odatiy narxda.",
    "files_attached": "#{id} buyurtmaga qo‘shdim.",
    # --- fayl bo‘yicha tezkor buyurtma ---
    "quick_ask": "<b>Shu fayl bo‘yicha taqdimot qilamiz</b>\nNechta slayd?",
    "quick_deadline": "<b>Muddat</b>",
    "quick_more": "Fayl qo‘shildi — jami {n}. Yuqoridagi tugma bilan tanlang.",
    "quick_topic": "Fayl bo‘yicha: {name}",
    # --- muqova ---
    "cover_ready": "<b>#{id} buyurtma muqovasi</b>\nBu bepul. Yoqdimi?",
    "btn_cover_ok": "Yoqdi",
    "btn_cover_change": "O‘zgartirish",
    "cover_change_prompt": "Muqovada nimani o‘zgartirish kerak — rang, uslub, rasm, matn? Namuna skrinshoti bilan ham bo‘ladi.",
    "cover_change_sent": "Dizaynerga yetkazdim — yangi variant yuboraman.",
    "cover_go": "<b>Ajoyib!</b>\nButun taqdimotni boshlaymiz — tayyor bo‘lgach yuboraman.",
    "cover_pay": "<b>Ajoyib!</b>\nTo‘lov qoldi — va darhol boshlaymiz.",
    # --- to‘lov ---
    "pay_order": "<b>#{id} buyurtma to‘lovi</b>\n{price} so‘m",
    "pay_package": "<b>«{plan}» paketi</b>\n{price} so‘m",
    "pay_credit": "\n<i>#{id} buyurtma hisobga olindi: −{amount} so‘m.</i>",
    "pay_early": "\n\n<i>Muqova bepul. Hozir yoki muqovani ko‘rgach to‘lashingiz mumkin.</i>",
    "pay_cards": "\n\nKartaga o‘tkazing — raqamni bosing, nusxa olinadi:\n{cards}{name}\n\nSo‘ng «To‘ladim» ni bosing va chek yuboring.",
    "pay_name": "\nQabul qiluvchi: {name}",
    "pay_stars_only": "\n\nTelegram yulduzlari bilan to‘lov — bitta tugma, darhol tasdiqlanadi.",
    "pay_stars_too": "\n\nYoki Telegram yulduzlari bilan — darhol tasdiqlanadi.",
    "pay_manual": "\n\nMenejer qanday to‘lashni yozadi.",
    "btn_pay_stars": "⭐ Yulduzlar · {stars}",
    "btn_paid": "Karta bilan to‘ladim",
    "receipt_ask": "Chek skrinshoti yoki rasmini yuboring. Matn ham bo‘ladi: summa, vaqt, qaysi kartadan.",
    "receipt_sent": "Rahmat! To‘lovni tekshirib tasdiqlayman — odatda bir soat ichida.",
    "invoice_order": "SlideLab · #{id} buyurtma",
    "invoice_order_desc": "«{topic}» · {slides} slayd. Butun taqdimot, muqova — bepul.",
    "invoice_package": "SlideLab · {plan}",
    "invoice_package_desc": "{days} kunga {count} ta taqdimot. Qoldiq yonmaydi.",
    "already_paid": "Allaqachon to‘langan.",
    "paid_go": "<b>To‘lov qabul qilindi</b>\n#{id} buyurtma bo‘yicha butun taqdimotni boshlaymiz.",
    "paid_early": "<b>To‘lov qabul qilindi</b>\nAvval muqovani yuboraman — «Yoqdi» dan keyin darhol butun taqdimotni qilamiz.",
    "payment_not_found": "{what} uchun to‘lov topilmadi. Agar o‘tkazgan bo‘lsangiz — shu yerga yozing, hal qilamiz.",
    "what_order": "#{id} buyurtma",
    "what_package": "«{plan}» paketi",
    # --- tayyor ---
    "formats_ask": "<b>#{id} taqdimot tayyor</b>\nQaysi formatda yuboray?",
    "fmt_pptx": "PowerPoint",
    "fmt_pdf": "PDF",
    "fmt_png": "Rasmlar",
    "fmt_gslides": "Google Slides",
    "fmt_canva": "Canva",
    "fmt_all": "Barcha formatlar",
    "fmt_sending": "Yuboryapman…",
    "fmt_none": "Bunday format yo‘q — yozing, yuboramiz.",
    "deck_ready": "<b>#{id} taqdimot tayyor</b>",
    "link_gslides": "<b>Google Slides</b> — shaxsiy nusxangiz:\n{url}\n\n«Nusxa yaratish» ni bosing — Google Diskingizda paydo bo‘ladi.",
    "link_canva": "<b>Canva</b> — shaxsiy nusxangiz:\n{url}\n\n«Shablondan foydalanish» ni bosing — Canva akkauntingizda paydo bo‘ladi.",
    "how_gslides": (
        "<b>Google Slides’da qanday ochish</b>\n"
        "1. Yuqoridagi PPTX’ni saqlang\n2. drive.google.com → «Yaratish» → «Fayl yuklash»\n"
        "3. Faylni oching → «Google Presentations’da ochish»"
    ),
    "how_canva": (
        "<b>Canva’da qanday ochish</b>\n"
        "1. Yuqoridagi PPTX’ni saqlang\n2. Canva’da: «Dizayn yaratish» → «Faylni import qilish»\n3. PPTX’ni tanlang — hammasi tahrirlanadi"
    ),
    "after_delivery": "Nimanidir tuzatish kerakmi? Ikki tuzatish — bepul.\n<i>Boshqa format — yuqoridagi xabardagi tugma bilan.</i>",
    "btn_revise": "Tuzatish kiritish",
    "btn_all_good": "Hammasi zo‘r",
    "revise_prompt": (
        "<b>#{id} buyurtmaga tuzatishlar</b>\n"
        "Nimani o‘zgartirishni yozing — masalan, «3-slayd: boshqa grafik». Skrinshot va fayllar ham bo‘ladi. "
        "Tugatgach — «Yuborish» ni bosing."
    ),
    "btn_send_revision": "Tuzatishlarni yuborish",
    "revise_empty": "Nimani o‘zgartirishni yozing.",
    "revise_sent": "Tuzatishlarni yetkazdim — tuzatilgan variantni yuboraman.",
    "revise_paid": "\n<i>Bepul tuzatishlar tugadi — menejer narxini aytadi.</i>",
    "revise_not_allowed": "Tuzatishni buyurtma tayyor bo‘lgach yuborish mumkin.",
    "rate_ask": "Ishimizni baholang:",
    "rate_thanks": "Baho uchun rahmat!",
    # --- paketga hisoblash ---
    "credit_offer": (
        "<b>Yoqdimi? Arzonroq qilamiz</b>\n"
        "{date} gacha paket oling — bu buyurtma ({amount} so‘m) hisobga olinadi. Faqat farqini to‘laysiz:\n\n{lines}"
    ),
    "credit_line": "{plan}: <s>{full}</s> → <b>{pay} so‘m</b> · yana {more} ta",
    "btn_credit": "{plan} — {pay} so‘m",
    "credit_expired": "Hisoblash muddati o‘tdi — paketni odatiy narxda olish mumkin.",
    # --- buyurtmalarim ---
    "orders_title": "<b>Buyurtmalarim</b>",
    "orders_empty": "Hali buyurtma yo‘q. «Yangi taqdimot» ni bosing — bir-ikki daqiqa.",
    "order_row": "#{id} · {status} · {topic}",
    "order_card": "<b>#{id} buyurtma</b> · {status}\n{topic}\n{slides} slayd · {price}",
    "price_from_package": "paketdan",
    "btn_pay": "To‘lash",
    "btn_get_files": "Fayllarni olish",
    "btn_hide": "Ro‘yxatdan olib tashlash",
    "hidden": "#{id} ro‘yxatdan olib tashlandi. Chatdagi fayllar qoldi.",
    "st_new": "Qabul qilindi",
    "st_cover": "Muqova tayyor",
    "st_awaiting_payment": "To‘lov kutilmoqda",
    "st_work": "Ishlanmoqda",
    "st_done": "Tayyor",
    "st_revision": "Tuzatilmoqda",
    "st_cancelled": "Bekor qilindi",
    "status_changed": "<b>#{id} buyurtma</b> · {status}\n{topic}",
    "order_cancelled": "<b>#{id} buyurtma bekor qilindi</b>",
    "stars_refunded": "#{id} buyurtma uchun {amount} ⭐ qaytarildi.",
}
