# SlideLab render — движок презентаций без Canva (прототип)

deck.json (тема + слайды по макетам) → редактируемый PPTX + PDF + отчёт проверки.

    ./render.sh decks/aral      # собрать, отрендерить PDF/PNG и лист со всеми слайдами (decks/aral/r/all.png)

- Правила содержания и дизайна: «Книга правил SlideLab» (Claude Docs).
- Макеты: cover, hook, bignum, chart, flow, story, three, timeline, split, end, sources (engine.py → LAYOUTS).
- Картинки: decks/<тема>/assets/<file> + поле image.file в слайде; без файла ставится заглушка с описанием.
- Шрифты (OFL): Montserrat, Unbounded, PT Serif — в fonts/. Для LibreOffice: скопировать в ~/.fonts.

Следующие шаги: фото (Unsplash/Wikimedia/Higgsfield), слайды «картинка + данные» (подписи по предметам фото),
встраивание шрифтов в PPTX, подключение к боту вместо Canva.
