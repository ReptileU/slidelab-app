"""FAQ из старого index.html — 8 вопросов на трёх языках."""

from typing import Any

FAQ: list[dict[str, Any]] = [
    {
        "ru": {
            "q": "Как быстро?",
            "a": "Срок обсуждаем в чате до начала работы и держим его — обычно в течение дня. Нужно очень быстро — «Срочно» (до 20 слайдов), +50%.",
        },
        "uz": {
            "q": "Qancha vaqtda?",
            "a": "Muddatni ish boshlanishidan oldin chatda kelishamiz va unga amal qilamiz — odatda bir kun ichida. Juda tez kerak bo‘lsa — «Shoshilinch» (20 slaydgacha), +50%.",
        },
        "en": {
            "q": "How fast?",
            "a": "We agree the deadline in the chat before starting and keep it — usually within a day. Need it very fast — «Urgent» (up to 20 slides), +50%.",
        },
    },
    {
        "ru": {
            "q": "Как оплатить?",
            "a": "Обложка — бесплатно. Понравилась — оплачиваете заказ картой Uzum Bank / Payme / Zoomrad (реквизиты пришлёт бот) или звёздами Telegram ⭐ в одно нажатие.",
        },
        "uz": {
            "q": "Qanday to‘lanadi?",
            "a": "Muqova — bepul. Yoqsa — buyurtmani Uzum Bank / Payme / Zoomrad kartasiga (rekvizitlarni bot yuboradi) yoki Telegram yulduzlari ⭐ bilan bir bosishda to‘laysiz.",
        },
        "en": {
            "q": "How to pay?",
            "a": "The cover is free. If you like it, you pay by Uzum Bank / Payme / Zoomrad card (the bot sends the details) or with Telegram Stars ⭐ in one tap.",
        },
    },
    {
        "ru": {
            "q": "А если не понравится?",
            "a": "Сначала делаем бесплатную обложку. Потом 2 правки бесплатно. Не подошло после правок — вернём предоплату.",
        },
        "uz": {
            "q": "Yoqmasa-chi?",
            "a": "Avval bepul muqova. Keyin 2 marta tuzatish bepul. Tuzatishdan keyin ham yoqmasa — oldindan to‘lovni qaytaramiz.",
        },
        "en": {
            "q": "What if I don't like it?",
            "a": "First we make a free cover. Then 2 rounds of edits are free. If it still doesn't fit after the edits, we refund the payment.",
        },
    },
    {
        "ru": {
            "q": "В каком формате?",
            "a": "PPTX (PowerPoint, Google Slides) и PDF. Каждый текст и график можно изменить.",
        },
        "uz": {
            "q": "Qaysi formatda?",
            "a": "PPTX (PowerPoint, Google Slides) va PDF. Har bir matn va grafikni o‘zgartirish mumkin.",
        },
        "en": {
            "q": "What format?",
            "a": "PPTX (PowerPoint, Google Slides) and PDF. Every text and chart can be edited.",
        },
    },
    {
        "ru": {
            "q": "Есть свой шаблон?",
            "a": "Пришлите — оформим в нём. Нет — придумаем дизайн под вашу тему.",
        },
        "uz": {
            "q": "O‘z shabloningiz bormi?",
            "a": "Yuboring — shunda bezaymiz. Yo‘q bo‘lsa — mavzuga mos dizayn o‘ylab topamiz.",
        },
        "en": {
            "q": "Have your own template?",
            "a": "Send it — we'll design in it. If not, we'll create a design for your topic.",
        },
    },
    {
        "ru": {"q": "Больше 30 слайдов?", "a": "Напишите нам — обсудим объём и срок индивидуально."},
        "uz": {"q": "30 slayddan ko‘p?", "a": "Bizga yozing — hajm va muddatni alohida kelishamiz."},
        "en": {
            "q": "More than 30 slides?",
            "a": "Write to us — we'll discuss the volume and deadline individually.",
        },
    },
    {
        "ru": {
            "q": "Как внести правки?",
            "a": "Когда файл готов, откройте «📦 Мои заказы» (на главной или в меню бота) и нажмите «✏️ Внести правки» — опишите, что поменять, и пришлите скриншоты в чат. 2 правки бесплатно.",
        },
        "uz": {
            "q": "Qanday tuzatish kiritaman?",
            "a": "Fayl tayyor bo‘lgach, «📦 Buyurtmalarim» (bosh sahifada yoki bot menyusida) → «✏️ Tuzatish kiritish» ni bosing — nimani o‘zgartirishni yozing va skrinshotlarni chatga yuboring. 2 marta tuzatish bepul.",
        },
        "en": {
            "q": "How to request edits?",
            "a": "When the file is ready, open «📦 My orders» (in your profile or the bot menu) and tap «✏️ Request edits» — describe what to change and send screenshots to the chat. 2 rounds of edits are free.",
        },
    },
    {
        "ru": {"q": "Мою работу покажут другим?", "a": "Нет, только с вашего разрешения."},
        "uz": {"q": "Ishimni boshqalarga ko‘rsatasizmi?", "a": "Yo‘q, faqat ruxsatingiz bilan."},
        "en": {"q": "Will my work be shown to others?", "a": "No, only with your permission."},
    },
]
