"""Витрина из старого index.html: 12 стилей и 5 работ, тексты на трёх языках."""

from typing import Any

STYLES: list[dict[str, Any]] = [
    {
        "key": "neon",
        "tags": ["study", "dark"],
        "is_real_work": True,
        "images": [
            "https://d2ol7oe51mr4n9.cloudfront.net/user_3Kg776n2YVTxhk4uIcG7vcKL8Pt/d797f293-74e4-4247-b132-38a2005c472b.png"
        ],
        "texts": {
            "ru": {"name": "Неон-журнал", "hint": "яркий, журнальный"},
            "uz": {"name": "Neon-jurnal", "hint": "yorqin, jurnal uslubi"},
            "en": {"name": "Neon magazine", "hint": "bright, editorial"},
        },
        "sort": 1,
    },
    {
        "key": "vintage",
        "tags": ["study", "light"],
        "is_real_work": True,
        "images": [
            "https://d2ol7oe51mr4n9.cloudfront.net/user_3Kg776n2YVTxhk4uIcG7vcKL8Pt/3c279dba-3468-4157-b550-8faccea7e58c.png"
        ],
        "texts": {
            "ru": {"name": "Винтажный скрапбук", "hint": "история, ретро"},
            "uz": {"name": "Vintaj skrapbuk", "hint": "tarix, retro"},
            "en": {"name": "Vintage scrapbook", "hint": "history, retro"},
        },
        "sort": 2,
    },
    {
        "key": "indust",
        "tags": ["business", "dark"],
        "is_real_work": True,
        "images": [
            "https://d2ol7oe51mr4n9.cloudfront.net/user_3Kg776n2YVTxhk4uIcG7vcKL8Pt/3ff9c549-44f5-4f93-ade8-bee16281befd.png"
        ],
        "texts": {
            "ru": {"name": "Индустриальный", "hint": "экономика, техника"},
            "uz": {"name": "Industrial", "hint": "iqtisod, texnika"},
            "en": {"name": "Industrial", "hint": "economy, tech"},
        },
        "sort": 3,
    },
    {
        "key": "artdeco",
        "tags": ["study", "dark"],
        "is_real_work": True,
        "images": [
            "https://d2ol7oe51mr4n9.cloudfront.net/user_3Kg776n2YVTxhk4uIcG7vcKL8Pt/9d75318d-71a4-4556-9b0b-7a9fe66e5663.png"
        ],
        "texts": {
            "ru": {"name": "Ар-деко 1920-х", "hint": "золото, история"},
            "uz": {"name": "Ar-deko 1920", "hint": "oltin, tarix"},
            "en": {"name": "Art Deco 1920s", "hint": "gold, history"},
        },
        "sort": 4,
    },
    {
        "key": "gazeta",
        "tags": ["study", "light"],
        "is_real_work": True,
        "images": [
            "https://d2ol7oe51mr4n9.cloudfront.net/user_3Kg776n2YVTxhk4uIcG7vcKL8Pt/eb96de66-11a9-4783-9406-2f42511d0b8e.png"
        ],
        "texts": {
            "ru": {"name": "Газета 1929", "hint": "газетный, история"},
            "uz": {"name": "1929 gazetasi", "hint": "gazeta uslubi, tarix"},
            "en": {"name": "1929 Newspaper", "hint": "newsprint, history"},
        },
        "sort": 5,
    },
    {
        "key": "minimal",
        "tags": ["business", "light"],
        "is_real_work": False,
        "images": [
            "https://d2ol7oe51mr4n9.cloudfront.net/user_3Kg776n2YVTxhk4uIcG7vcKL8Pt/cbc3dd2b-aee5-44f4-99fd-f49adb1c5bc8.png",
            "https://d2ol7oe51mr4n9.cloudfront.net/user_3Kg776n2YVTxhk4uIcG7vcKL8Pt/df5c6be7-3449-4f08-9b05-558b21237ae2.png",
            "https://d2ol7oe51mr4n9.cloudfront.net/user_3Kg776n2YVTxhk4uIcG7vcKL8Pt/d3aed93f-e151-4fc3-9464-311c5b95afc9.png",
            "https://d2ol7oe51mr4n9.cloudfront.net/user_3Kg776n2YVTxhk4uIcG7vcKL8Pt/dda05311-bfc9-4fe5-8ca8-5c2eff15809c.png",
            "https://d2ol7oe51mr4n9.cloudfront.net/user_3Kg776n2YVTxhk4uIcG7vcKL8Pt/e9d77e9e-0964-44b3-b832-ff30134da92a.png",
        ],
        "texts": {
            "ru": {"name": "Минимализм", "hint": "чисто и стильно"},
            "uz": {"name": "Minimalizm", "hint": "toza va zamonaviy"},
            "en": {"name": "Minimal", "hint": "clean and stylish"},
        },
        "sort": 6,
    },
    {
        "key": "corp",
        "tags": ["business", "dark"],
        "is_real_work": False,
        "images": [
            "https://d2ol7oe51mr4n9.cloudfront.net/user_3Kg776n2YVTxhk4uIcG7vcKL8Pt/1b4bad92-6a84-470a-8f36-6220ab60b612.png",
            "https://d2ol7oe51mr4n9.cloudfront.net/user_3Kg776n2YVTxhk4uIcG7vcKL8Pt/cc3ac479-8a11-4314-b2aa-c87a4591925d.png",
            "https://d2ol7oe51mr4n9.cloudfront.net/user_3Kg776n2YVTxhk4uIcG7vcKL8Pt/3c4b1f5f-4d16-409e-b1aa-62dc59691359.png",
            "https://d2ol7oe51mr4n9.cloudfront.net/user_3Kg776n2YVTxhk4uIcG7vcKL8Pt/e134f625-92ae-4bb4-a500-96eba2f6c812.png",
            "https://d2ol7oe51mr4n9.cloudfront.net/user_3Kg776n2YVTxhk4uIcG7vcKL8Pt/75732d0f-fd91-4455-8b5a-8263bde6013d.png",
        ],
        "texts": {
            "ru": {"name": "Корпоративный", "hint": "отчёт, бизнес-план"},
            "uz": {"name": "Korporativ", "hint": "hisobot, biznes-reja"},
            "en": {"name": "Corporate", "hint": "report, business plan"},
        },
        "sort": 7,
    },
    {
        "key": "samarkand",
        "tags": ["study", "dark"],
        "is_real_work": False,
        "images": [
            "https://d2ol7oe51mr4n9.cloudfront.net/user_3Kg776n2YVTxhk4uIcG7vcKL8Pt/6508f037-4f8c-49aa-a29c-bfd123551cfb.png",
            "https://d2ol7oe51mr4n9.cloudfront.net/user_3Kg776n2YVTxhk4uIcG7vcKL8Pt/66683a24-8136-46b9-8adc-984c71b4ca58.png",
            "https://d2ol7oe51mr4n9.cloudfront.net/user_3Kg776n2YVTxhk4uIcG7vcKL8Pt/272d6130-48ff-4f5d-8b38-01b09ac217e5.png",
            "https://d2ol7oe51mr4n9.cloudfront.net/user_3Kg776n2YVTxhk4uIcG7vcKL8Pt/fea2be4c-6bc4-49ee-9f25-22dd67b73915.png",
            "https://d2ol7oe51mr4n9.cloudfront.net/user_3Kg776n2YVTxhk4uIcG7vcKL8Pt/6c4aa712-158e-43ac-a544-381422cabbdb.png",
        ],
        "texts": {
            "ru": {"name": "Самарканд", "hint": "восточный узор"},
            "uz": {"name": "Samarqand", "hint": "sharqona naqsh"},
            "en": {"name": "Samarkand", "hint": "oriental pattern"},
        },
        "sort": 8,
    },
    {
        "key": "science",
        "tags": ["study", "light"],
        "is_real_work": False,
        "images": [
            "https://d2ol7oe51mr4n9.cloudfront.net/user_3Kg776n2YVTxhk4uIcG7vcKL8Pt/fffcfb28-f423-4889-82b9-9e884309ed4f.png",
            "https://d2ol7oe51mr4n9.cloudfront.net/user_3Kg776n2YVTxhk4uIcG7vcKL8Pt/ab120455-120f-4a4c-a49d-d89a35523ca5.png",
            "https://d2ol7oe51mr4n9.cloudfront.net/user_3Kg776n2YVTxhk4uIcG7vcKL8Pt/85d93bd1-8235-472a-b0cd-052b2788a233.png",
            "https://d2ol7oe51mr4n9.cloudfront.net/user_3Kg776n2YVTxhk4uIcG7vcKL8Pt/26331425-be63-4010-b259-789683ae1269.png",
            "https://d2ol7oe51mr4n9.cloudfront.net/user_3Kg776n2YVTxhk4uIcG7vcKL8Pt/8683947b-b551-4ce4-acb9-c8f877e0cf1f.png",
        ],
        "texts": {
            "ru": {"name": "Научный", "hint": "графики и схемы"},
            "uz": {"name": "Ilmiy", "hint": "grafik va sxemalar"},
            "en": {"name": "Science", "hint": "charts and diagrams"},
        },
        "sort": 9,
    },
    {
        "key": "premium",
        "tags": ["business", "dark"],
        "is_real_work": False,
        "images": [
            "https://d2ol7oe51mr4n9.cloudfront.net/user_3Kg776n2YVTxhk4uIcG7vcKL8Pt/abdf7ff5-06a5-4808-8d06-af6e8b640d87.png",
            "https://d2ol7oe51mr4n9.cloudfront.net/user_3Kg776n2YVTxhk4uIcG7vcKL8Pt/f6dbe652-3044-4fb7-94f0-223f0642c56b.png",
            "https://d2ol7oe51mr4n9.cloudfront.net/user_3Kg776n2YVTxhk4uIcG7vcKL8Pt/5321a667-feab-4dce-8e9d-4ee5aa5d6ce7.png",
            "https://d2ol7oe51mr4n9.cloudfront.net/user_3Kg776n2YVTxhk4uIcG7vcKL8Pt/ea8b77b4-75cf-4eb3-b532-8a248c5eb7b1.png",
            "https://d2ol7oe51mr4n9.cloudfront.net/user_3Kg776n2YVTxhk4uIcG7vcKL8Pt/cb6fccf6-7010-4ce1-813a-57ca22a84d06.png",
        ],
        "texts": {
            "ru": {"name": "Премиум", "hint": "чёрный с золотом"},
            "uz": {"name": "Premium", "hint": "qora va oltin"},
            "en": {"name": "Premium", "hint": "black and gold"},
        },
        "sort": 10,
    },
    {
        "key": "bright",
        "tags": ["study", "dark"],
        "is_real_work": False,
        "images": [
            "https://d2ol7oe51mr4n9.cloudfront.net/user_3Kg776n2YVTxhk4uIcG7vcKL8Pt/505a57af-3f66-4dd2-9ddc-7ed10283e9bd.png",
            "https://d2ol7oe51mr4n9.cloudfront.net/user_3Kg776n2YVTxhk4uIcG7vcKL8Pt/48b90b42-a3ec-41cf-a339-90348f4411fa.png",
            "https://d2ol7oe51mr4n9.cloudfront.net/user_3Kg776n2YVTxhk4uIcG7vcKL8Pt/1841cf42-364c-4569-a38b-abf4e91ef9b1.png",
            "https://d2ol7oe51mr4n9.cloudfront.net/user_3Kg776n2YVTxhk4uIcG7vcKL8Pt/528e911d-0806-4027-a1c8-1312c3af6976.png",
            "https://d2ol7oe51mr4n9.cloudfront.net/user_3Kg776n2YVTxhk4uIcG7vcKL8Pt/601c84ca-7af7-4fbb-b8f7-7993c2f8bc08.png",
        ],
        "texts": {
            "ru": {"name": "Яркий", "hint": "школа, творчество"},
            "uz": {"name": "Yorqin", "hint": "maktab, ijod"},
            "en": {"name": "Bright", "hint": "school, creative"},
        },
        "sort": 11,
    },
    {
        "key": "nature",
        "tags": ["study", "dark"],
        "is_real_work": False,
        "images": [
            "https://d2ol7oe51mr4n9.cloudfront.net/user_3Kg776n2YVTxhk4uIcG7vcKL8Pt/a75f019c-43ae-439e-831d-db6e4abbe002.png",
            "https://d2ol7oe51mr4n9.cloudfront.net/user_3Kg776n2YVTxhk4uIcG7vcKL8Pt/519e9954-5eee-481e-b19b-9b4f6cc5ebe0.png",
            "https://d2ol7oe51mr4n9.cloudfront.net/user_3Kg776n2YVTxhk4uIcG7vcKL8Pt/c0f8f77c-0087-429f-aa42-745cafa00307.png",
            "https://d2ol7oe51mr4n9.cloudfront.net/user_3Kg776n2YVTxhk4uIcG7vcKL8Pt/00e9369d-7e30-457b-bb13-cd9f36a6ff55.png",
            "https://d2ol7oe51mr4n9.cloudfront.net/user_3Kg776n2YVTxhk4uIcG7vcKL8Pt/d05a40e4-6561-45fc-bb67-27e1c012d174.png",
        ],
        "texts": {
            "ru": {"name": "Эко", "hint": "природа, биология"},
            "uz": {"name": "Eko", "hint": "tabiat, biologiya"},
            "en": {"name": "Eco", "hint": "nature, biology"},
        },
        "sort": 12,
    },
]

WORKS: list[dict[str, Any]] = [
    {
        "image": "https://d2ol7oe51mr4n9.cloudfront.net/user_3Kg776n2YVTxhk4uIcG7vcKL8Pt/d797f293-74e4-4247-b132-38a2005c472b.png",
        "sort": 1,
        "texts": {
            "ru": {"title": "Экономика Узбекистана 2026", "style": "Неон-журнал"},
            "uz": {"title": "O‘zbekiston iqtisodiyoti 2026", "style": "Neon-jurnal"},
            "en": {"title": "Economy of Uzbekistan 2026", "style": "Neon magazine"},
        },
    },
    {
        "image": "https://d2ol7oe51mr4n9.cloudfront.net/user_3Kg776n2YVTxhk4uIcG7vcKL8Pt/3c279dba-3468-4157-b550-8faccea7e58c.png",
        "sort": 2,
        "texts": {
            "ru": {"title": "История, 1929–1939", "style": "Винтажный скрапбук"},
            "uz": {"title": "Tarix, 1929–1939", "style": "Vintaj skrapbuk"},
            "en": {"title": "History, 1929–1939", "style": "Vintage scrapbook"},
        },
    },
    {
        "image": "https://d2ol7oe51mr4n9.cloudfront.net/user_3Kg776n2YVTxhk4uIcG7vcKL8Pt/3ff9c549-44f5-4f93-ade8-bee16281befd.png",
        "sort": 3,
        "texts": {
            "ru": {"title": "Экономика и милитаризация", "style": "Индустриальный"},
            "uz": {"title": "Iqtisodiyot va militarizatsiya", "style": "Industrial"},
            "en": {"title": "Economy and militarisation", "style": "Industrial"},
        },
    },
    {
        "image": "https://d2ol7oe51mr4n9.cloudfront.net/user_3Kg776n2YVTxhk4uIcG7vcKL8Pt/9d75318d-71a4-4556-9b0b-7a9fe66e5663.png",
        "sort": 4,
        "texts": {
            "ru": {"title": "Экономическое наследие Первой мировой", "style": "Ар-деко 1920-х"},
            "uz": {"title": "Birinchi jahon urushining iqtisodiy merosi", "style": "Ar-deko 1920-yillar"},
            "en": {"title": "Economic legacy of World War I", "style": "Art Deco 1920s"},
        },
    },
    {
        "image": "https://d2ol7oe51mr4n9.cloudfront.net/user_3Kg776n2YVTxhk4uIcG7vcKL8Pt/eb96de66-11a9-4783-9406-2f42511d0b8e.png",
        "sort": 5,
        "texts": {
            "ru": {"title": "Великая депрессия 1929–1930", "style": "Газета 1929 года"},
            "uz": {"title": "Buyuk depressiya 1929–1930", "style": "1929-yil gazetasi"},
            "en": {"title": "The Great Depression 1929–1930", "style": "1929 Newspaper"},
        },
    },
]
