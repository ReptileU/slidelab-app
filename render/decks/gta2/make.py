"""Слайды GTA 6 v2 — каждый со своей композицией. Сюжет: от пикселей 1997 года до $1,65 млрд в 2026-м."""
from pathlib import Path

OUT = Path(__file__).parent / "slides"
A = "../assets/"


def page(n: int, body: str, notes: str = "", bg: str = "") -> None:
    pg = f'<div class="a pg" data-t="meta">{n:02d}</div>' if n > 1 else ""
    (OUT / f"s{n:02d}.html").write_text(
        f'<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="base.css"></head>'
        f'<body data-notes="{notes}" style="{bg}">{body}{pg}</body></html>', encoding="utf-8")


# 1 — обложка: 1997 и 2026 в одном кадре, разрез по диагонали
page(1, f"""
<div class="a" style="inset:0;clip-path:polygon(0 0,58% 0,42% 100%,0 100%);background:#000">
  <img class="pix" src="{A}gta1.jpg" style="width:100%;height:100%;object-fit:cover;filter:saturate(1.2) brightness(.75)">
</div>
<div class="a" style="inset:0;clip-path:polygon(58% 0,100% 0,100% 100%,42% 100%)">
  <img src="{A}ads_toronto.jpg" style="width:100%;height:100%;object-fit:cover;object-position:30% 50%;filter:brightness(.7)">
</div>
<svg class="a" style="inset:0" width="1920" height="1080"><line x1="1113.6" y1="0" x2="806.4" y2="1080" stroke="#FF3EA5" stroke-width="8"/></svg>
<div class="a" style="inset:0;background:linear-gradient(0deg,rgba(13,9,19,.97) 0%,rgba(13,9,19,.85) 34%,rgba(13,9,19,0) 62%)"></div>
<div class="a px" data-t="label" style="left:64px;top:60px;font-size:40px;color:#FFE14D;text-shadow:4px 4px 0 #000">1997</div>
<div class="a num" data-t="label" style="right:64px;top:56px;font-size:56px;color:var(--cyan);text-shadow:0 4px 18px #000">2026</div>
<div class="a k" data-t="kicker" style="left:96px;top:640px">Игры · Бизнес · История</div>
<div class="a h" data-t="title" style="left:96px;top:688px;width:1500px;font-size:96px">От пикселей<br>до миллиардов</div>
<div class="a p" data-t="lead" style="left:100px;top:928px;width:1300px;color:#D9D0EA">История GTA — и почему GTA 6 стала крупнейшим запуском в истории развлечений</div>
<div class="a src" data-t="meta" style="right:64px;top:1010px;text-align:right;width:420px;font-size:15px">Слева — GTA 1997 (скриншот Rockstar, Wikipedia). Справа — реклама GTA 6 в метро Торонто, фото Dillan Payne, CC BY-SA 4.0</div>
""", "Начните с вопроса: кто играл в первую GTA? Слева — 1997 год, справа — 2026-й. Сегодня пройдём этот путь.")

# 2 — завязка: игра про полицейских
page(2, f"""
<div class="a crt" style="left:110px;top:170px;width:700px;height:700px"><div class="scr scan"><img class="pix" src="{A}racenchase.jpg"></div></div>
<div class="a src" data-t="meta" style="left:110px;top:900px;width:700px">Прототип «Race ’n’ Chase». Скриншот: DMA Design, через Wikipedia</div>
<div class="a k" data-t="kicker" style="left:930px;top:190px">С чего всё началось</div>
<div class="a h" data-t="title" style="left:930px;top:240px;width:880px;font-size:62px">Сначала это была игра про полицейских</div>
<div class="a p" data-t="body" style="left:930px;top:470px;width:860px">Шотландская студия DMA Design из города Данди делала гонку «Race ’n’ Chase»: полиция ловит преступников. Но тестерам было интереснее играть за преступников — и команда развернула игру.</div>
<div class="a" style="left:930px;top:800px;width:10px;height:120px;background:var(--pink)"></div>
<div class="a h" data-t="quote" style="left:972px;top:800px;width:820px;font-size:40px;color:var(--pink)">Так появилась Grand&nbsp;Theft&nbsp;Auto</div>
""", "Главная мысль: GTA родилась из случайного открытия на тестировании.")

# 3 — 1997: город сверху
page(3, f"""
<div class="a" style="left:0;top:0;width:1920px;height:90px;background:#000;border-bottom:4px solid #FFE14D"></div>
<div class="a px" data-t="label" style="left:64px;top:30px;font-size:26px;color:#FFE14D">GRAND THEFT AUTO · 1997</div>
<div class="a crt" style="left:90px;top:170px;width:1040px;height:800px"><div class="scr scan"><img class="pix" src="{A}gta1.jpg"></div></div>
<div class="a pin" style="left:520px;top:310px"></div><div class="a lead" style="left:542px;top:320px;width:300px;transform:rotate(-14deg)"></div>
<div class="a" data-t="label" style="left:780px;top:236px;width:300px;font-size:24px;font-weight:800;line-height:1.25;color:var(--cyan);background:rgba(0,0,0,.7);padding:6px 10px">машины — плоские картинки</div>
<div class="a pin" style="left:300px;top:700px"></div><div class="a lead" style="left:322px;top:710px;width:120px"></div>
<div class="a" data-t="label" style="left:450px;top:690px;width:360px;font-size:24px;font-weight:800;line-height:1.25;color:var(--cyan);background:rgba(0,0,0,.65);padding:6px 10px">камера смотрит сверху, как на карту</div>
<div class="a src" data-t="meta" style="left:90px;top:990px;width:1040px">Скриншот: Grand Theft Auto (1997), DMA Design / Rockstar, через Wikipedia</div>
<div class="a h" data-t="title" style="left:1220px;top:200px;width:620px;font-size:56px">Город, увиденный сверху</div>
<div class="a p" data-t="body" style="left:1220px;top:470px;width:620px">Игрок смотрел на город, как на карту. Можно было угнать любую машину и ехать куда угодно — эта свобода и стала главной идеей серии.</div>
<div class="a px" data-t="label" style="left:1220px;top:860px;width:640px;font-size:22px;color:#FFE14D;line-height:1.6">PC · вид сверху · 2D</div>
""", "Покажите на экран: так выглядела игра, с которой всё началось.")

# 4 — 2001: в 3D
page(4, f"""
<div class="a k" data-t="kicker" style="left:96px;top:70px">2001 · Grand Theft Auto III</div>
<div class="a h" data-t="title" style="left:96px;top:116px;width:1700px;font-size:58px">Город стал трёхмерным — и игра превратилась в мир</div>
<div class="a" style="left:96px;top:330px;width:560px;height:420px;border-radius:16px;overflow:hidden;filter:grayscale(.6) brightness(.8)"><img class="pix" src="{A}gta1.jpg" style="width:100%;height:100%;object-fit:cover"></div>
<div class="a px" data-t="label" style="left:96px;top:770px;font-size:22px;color:var(--mute)">1997 · вид сверху</div>
<svg class="a" style="left:690px;top:470px" width="150" height="120"><path d="M10 60 H120 M90 25 L130 60 L90 95" stroke="#FF3EA5" stroke-width="12" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>
<div class="a" style="left:870px;top:290px;width:960px;height:690px;border-radius:20px;overflow:hidden;box-shadow:0 0 0 4px var(--pink),0 0 90px rgba(255,62,165,.35)"><img src="{A}gta3walk.jpg" style="width:100%;height:100%;object-fit:cover"></div>
<div class="a" data-t="label" style="left:900px;top:910px;font-size:26px;font-weight:800;color:#fff;background:var(--pink);padding:8px 16px">2001 · камера за спиной героя</div>
<div class="a p" data-t="body" style="left:96px;top:830px;width:740px;font-size:26px">Прохожие, такси, ночь и день. GTA III на PlayStation 2 стала образцом для открытых миров в играх XXI века.</div>
<div class="a src" data-t="meta" style="left:96px;top:1010px;width:740px">Скриншоты: Rockstar Games, через Wikipedia · The National, 22.08.2026</div>
""", "Сравните два кадра: за 4 года игра из карты стала городом.")

# 5 — 2002: Вайс-Сити впервые
page(5, f"""
<div class="a" style="left:0;top:0;width:1920px;height:640px;overflow:hidden"><img src="{A}vc.jpg" style="width:100%;height:100%;object-fit:cover;object-position:50% 60%;filter:saturate(1.3)"></div>
<div class="a" style="left:0;top:0;width:1920px;height:640px;background:linear-gradient(0deg,#0D0913 0%,rgba(13,9,19,0) 45%)"></div>
<div class="a src" data-t="meta" style="right:64px;top:600px;width:700px;text-align:right">Скриншот: Grand Theft Auto: Vice City, Rockstar North, через Wikipedia</div>
<div class="a k" data-t="kicker" style="left:96px;top:690px">2002 · Vice City</div>
<div class="a h" data-t="title" style="left:96px;top:738px;width:1050px;font-size:54px">Впервые — Вайс-Сити: Майами 1980-х</div>
<div class="a p" data-t="body" style="left:96px;top:880px;width:1000px;font-size:28px">Неон, пальмы, 1986 год. Игру купили 17 млн раз — и запомнили этот город навсегда.</div>
<div class="a" style="left:1240px;top:700px;width:600px;height:300px;border:3px solid var(--cyan);border-radius:18px"></div>
<div class="a num" data-t="number" style="left:1280px;top:730px;font-size:84px;color:var(--cyan)">24 года</div>
<div class="a p" data-t="body" style="left:1280px;top:840px;width:540px;font-size:26px">спустя GTA 6 вернётся сюда же — в Вайс-Сити</div>
""", "Мостик к финалу: город, в который вернётся GTA 6.")

# 6 — 2013: $1 млрд за 3 дня
page(6, f"""
<div class="a" style="inset:0"><img src="{A}gta5.jpg" style="width:100%;height:100%;object-fit:cover;filter:blur(18px) brightness(.35)"></div>
<div class="a" style="left:96px;top:250px;width:1000px;height:562px;border-radius:18px;overflow:hidden;box-shadow:0 30px 90px rgba(0,0,0,.7)"><img src="{A}gta5.jpg" style="width:100%;height:100%;object-fit:cover"></div>
<div class="a src" data-t="meta" style="left:96px;top:830px;width:1000px">Скриншот: Grand Theft Auto V (2013), Rockstar, через Wikipedia</div>
<div class="a k" data-t="kicker" style="left:96px;top:90px;color:var(--cyan)">17 сентября 2013 · GTA V</div>
<div class="a h" data-t="title" style="left:96px;top:136px;width:1700px;font-size:54px">GTA V заработала больше, чем любой фильм</div>
<div class="a num" data-t="number" style="left:1180px;top:270px;font-size:96px;color:var(--pink)">$815,7&nbsp;млн</div>
<div class="a p" data-t="body" style="left:1180px;top:390px;width:660px;font-size:28px">за первые сутки</div>
<div class="a" style="left:1180px;top:470px;width:660px;height:3px;background:rgba(255,255,255,.25)"></div>
<div class="a num" data-t="number" style="left:1180px;top:510px;font-size:96px;color:var(--cyan)">3&nbsp;дня</div>
<div class="a p" data-t="body" style="left:1180px;top:630px;width:660px;font-size:28px">до $1 млрд — быстрее любого фильма, книги или игры. Рекорд Гиннесса.</div>
<div class="a src" data-t="meta" style="left:1180px;top:1000px;width:660px">Guinness World Records, 08.10.2013</div>
""", "Здесь игры впервые обогнали кино по скорости заработка.")

# 7 — 230 млн: сетка из 230 квадратов
cells = "".join(
    f'<div style="width:46px;height:46px;border-radius:6px;background:{"#FF3EA5" if i < 1 else "#29E3D6"};opacity:{1 if i < 1 else .85}"></div>'
    for i in range(230))
page(7, f"""
<div class="a k" data-t="kicker" style="left:96px;top:80px">2013 → 2026</div>
<div class="a h" data-t="title" style="left:96px;top:126px;width:1750px;font-size:54px">13 лет без новой части — а GTA V всё продавалась</div>
<div class="a" style="left:96px;top:300px;width:1180px;display:grid;grid-template-columns:repeat(23,46px);gap:6px">{cells}</div>
<div class="a" data-t="label" style="left:96px;top:880px;width:1180px;font-size:24px;font-weight:700;color:var(--mute)">Каждый квадрат — 1 млн проданных копий. Розовый — первый миллион.</div>
<div class="a num" data-t="number" style="left:1360px;top:300px;font-size:120px;color:var(--cyan)">230</div>
<div class="a p" data-t="body" style="left:1360px;top:440px;width:480px;font-size:30px;font-weight:700">млн копий к августу 2026</div>
<div class="a p" data-t="body" style="left:1360px;top:560px;width:480px;font-size:26px">Секрет — GTA Online: сетевой режим, который Rockstar обновляла больше 10 лет на трёх поколениях консолей.</div>
<div class="a src" data-t="meta" style="left:96px;top:1000px;width:1300px">Take-Two, отчёт за квартал до 30.06.2026 (Game Developer, 07.08.2026); The National, 22.08.2026</div>
""", "Каждый квадрат — миллион человек, которые купили игру.")

# 8 — трейлер: плееры размером по просмотрам
page(8, f"""
<img class="a" src="{A}logo_youtube.png" style="left:96px;top:84px;height:52px">
<div class="a k" data-t="kicker" style="left:360px;top:98px">Декабрь 2023</div>
<div class="a h" data-t="title" style="left:96px;top:170px;width:1750px;font-size:54px">Первый трейлер посмотрели 90 млн раз за сутки</div>
<div class="a" style="left:96px;top:360px;width:1000px;height:562px;border-radius:20px;background:linear-gradient(135deg,#3a1450,#0e2a3a);box-shadow:0 0 0 4px var(--pink)"></div>
<svg class="a" style="left:536px;top:571px" width="120" height="140"><path d="M0 0 L120 70 L0 140 Z" fill="#fff"/></svg>
<div class="a" style="left:96px;top:895px;width:1000px;height:10px;background:#FF0033;border-radius:5px"></div>
<div class="a num" data-t="number" style="left:130px;top:390px;font-size:64px;color:#fff">90&nbsp;421&nbsp;491</div>
<div class="a p" data-t="label" style="left:130px;top:470px;font-size:26px;font-weight:700;color:#fff">просмотров · трейлер GTA 6</div>
<div class="a" style="left:1200px;top:545px;width:657px;height:370px;border-radius:16px;background:#251a33"></div>
<svg class="a" style="left:1490px;top:690px" width="80" height="90"><path d="M0 0 L80 45 L0 90 Z" fill="#9C90B8"/></svg>
<div class="a num" data-t="number" style="left:1230px;top:570px;font-size:44px;color:#C9BFDD">59,4&nbsp;млн</div>
<div class="a p" data-t="label" style="left:1230px;top:630px;width:600px;font-size:22px;color:#C9BFDD">прежний рекорд — видео MrBeast</div>
<div class="a p" data-t="body" style="left:1200px;top:360px;width:657px;font-size:26px">Рекорд Гиннесса: самый просматриваемый показ игры на YouTube за сутки. Размер экранов — в масштабе просмотров.</div>
<div class="a src" data-t="meta" style="left:96px;top:1000px;width:1300px">Push Square, 06.12.2023; Guinness World Records</div>
""", "Люди ждали не игру, а событие.")

# 9 — переносы: календарь
def cal(x, top, date, sub, state):
    color = {"x": "#6E6385", "ok": "var(--cyan)"}[state]
    cross = ('<svg class="a" style="left:0;top:0" width="440" height="460"><path d="M40 70 L400 420 M400 70 L40 420" '
             'stroke="#FF3EA5" stroke-width="10" stroke-linecap="round" opacity=".55"/></svg>') if state == "x" else ""
    glow = "box-shadow:0 0 0 6px var(--cyan),0 0 90px rgba(41,227,214,.45);" if state == "ok" else ""
    return (f'<div class="a" style="left:{x}px;top:{top}px;width:440px;height:460px;border-radius:24px;background:#F4EEFF;{glow}overflow:hidden">'
            f'<div style="height:90px;background:{color}"></div>{cross}</div>'
            f'<div class="a h" data-t="label" style="left:{x}px;top:{top+150}px;width:440px;text-align:center;font-size:52px;color:#1A1026">{date}</div>'
            f'<div class="a p" data-t="label" style="left:{x}px;top:{top+330}px;width:440px;text-align:center;font-size:24px;font-weight:700;color:#5B5070">{sub}</div>')


page(9, f"""
<div class="a k" data-t="kicker" style="left:96px;top:80px">2025 — 2026</div>
<div class="a h" data-t="title" style="left:96px;top:126px;width:1750px;font-size:54px">Ожидание растянулось ещё на год</div>
{cal(96, 300, "осень<br>2025", "первое обещание", "x")}
{cal(740, 300, "26 мая<br>2026", "первый перенос", "x")}
{cal(1384, 300, "19 ноября<br>2026", "дата выхода", "ok")}
<div class="a p" data-t="body" style="left:96px;top:830px;width:1700px;font-size:28px">Rockstar: «Дополнительные месяцы нужны, чтобы довести игру до уровня качества, которого вы ждёте».</div>
<div class="a src" data-t="meta" style="left:96px;top:1000px;width:1300px">Video Games Chronicle, 06.11.2025</div>
""", "Каждый перенос только разогревал интерес.")

# 10 — кульминация: реальная реклама «I ♥ Vice City»
page(10, f"""
<div class="a" style="inset:0"><img src="{A}ads_toronto.jpg" style="width:100%;height:100%;object-fit:cover;object-position:50% 55%"></div>
<div class="a" style="inset:0;background:linear-gradient(90deg,rgba(13,9,19,.96) 0%,rgba(13,9,19,.9) 38%,rgba(13,9,19,.2) 70%,rgba(13,9,19,0) 100%)"></div>
<div class="a k" data-t="kicker" style="left:96px;top:110px">19 ноября 2026 · кульминация</div>
<div class="a h" data-t="title" style="left:96px;top:160px;width:820px;font-size:56px">Ещё до выхода игра стала событием</div>
<div class="a num" data-t="number" style="left:96px;top:450px;width:900px;font-size:120px;color:var(--pink)">$1,65&nbsp;млрд</div>
<div class="a p" data-t="body" style="left:96px;top:600px;width:760px;font-size:30px">предзаказов до выхода — больше, чем весь мировой прокат «Барби» (около $1,45 млрд).</div>
<div class="a p" data-t="body" style="left:96px;top:800px;width:760px;font-size:24px;color:#D0C6E2">На фото — реклама GTA 6 «I ♥ Vice City» в метро Торонто, за неделю до выхода.</div>
<div class="a src" data-t="meta" style="left:96px;top:990px;width:1500px">Оценка Sensor Tracker, LA Magazine, 18.11.2026 · Фото: Dillan Payne, CC BY-SA 4.0 / Wikimedia Commons</div>
""", "Кульминация: город в реальном мире живёт игрой.")

# 11 — финал: возвращаемся к пиксельной машинке
page(11, f"""
<div class="a" style="left:1180px;top:160px;width:620px;height:620px;overflow:hidden;border-radius:24px;box-shadow:0 0 0 4px #FFE14D">
  <img class="pix" src="{A}gta1.jpg" style="width:2480px;height:1860px;margin-left:-1360px;margin-top:-420px">
</div>
<div class="a px" data-t="label" style="left:1180px;top:820px;width:620px;font-size:22px;color:#FFE14D;text-align:center">1997 → 2026 · 29 лет</div>
<div class="a k" data-t="kicker" style="left:96px;top:170px">Главное</div>
<div class="a h" data-t="title" style="left:96px;top:220px;width:980px;font-size:66px">Игры стали больше кино — и по деньгам, и по вниманию</div>
<div class="a" style="left:96px;top:640px;width:10px;height:200px;background:var(--cyan)"></div>
<div class="a k" data-t="kicker" style="left:140px;top:640px;color:var(--cyan)">Вопрос для обсуждения</div>
<div class="a p" data-t="body" style="left:140px;top:690px;width:900px;font-size:34px">Почему миллионы людей платят заранее почти 1&nbsp;млн сумов за игру, которую ещё не видели?</div>
""", "Вернитесь к первой машинке 1997 года — путь длиной 29 лет.")

# 12 — источники
page(12, f"""
<div class="a h" data-t="title" style="left:96px;top:90px;font-size:48px">Источники</div>
<div class="a p" data-t="meta" style="left:96px;top:210px;width:860px;font-size:22px;line-height:1.55">LA Magazine, 18.11.2026 — GTA VI breaks records ahead of its Thursday release<br>Game Developer, 07.08.2026 — GTA V surpasses 230 million sales<br>The National, 22.08.2026 — From 1997’s Grand Theft Auto to GTA 6<br>Guinness World Records, 08.10.2013 — GTA V breaks six sales records<br>Push Square, 06.12.2023 — GTA 6 trailer pulls 90 million views<br>Video Games Chronicle, 06.11.2025 — GTA 6 delayed to 19.11.2026</div>
<div class="a p" data-t="meta" style="left:1010px;top:210px;width:820px;font-size:22px;line-height:1.55">Скриншоты GTA (1997), Race ’n’ Chase, GTA III, Vice City, GTA V — Rockstar Games / DMA Design, через Wikipedia, как иллюстрации<br>Реклама GTA 6 в Торонто — Dillan Payne, CC BY-SA 4.0<br>Логотип YouTube — Wikimedia Commons</div>
""")
print("ok")
