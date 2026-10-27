TEXTS: dict[str, str] = {
    # --- language and welcome ---
    "lang_pick": "Выберите язык · Tilni tanlang · Choose language",
    "lang_name": "English",
    "welcome": (
        "<b>SlideLab</b>\n"
        "Presentations designed for your topic.\n\n"
        "First — a free cover. Pay only if you like it.\n\n"
        "Forward a lecture or assignment here — I'll set up the order in two taps."
    ),
    "welcome_back": "<b>SlideLab</b>\nHow can I help?",
    "error": "Something went wrong. Try again — or message @{admin}.",
    "use_buttons": "Please choose an option with the buttons above.",
    "send_text": "Please type it as text.",
    "cancelled": "Cancelled. You're back in the main menu.",
    # --- menu ---
    "btn_new": "New presentation",
    "btn_app": "Order in the app",
    "btn_orders": "My orders",
    "btn_prices": "Prices",
    "btn_examples": "Examples",
    "btn_help": "Questions",
    "btn_open_app": "Open SlideLab",
    # --- prices and packs ---
    "prices": (
        "<b>Prices</b>\n\n"
        "Up to 10 slides — {s10} UZS\n"
        "11–20 slides — {s20} UZS\n"
        "21–30 slides — {s30} UZS\n\n"
        "First order up to 10 slides — <b>{first} UZS</b>\n\n"
        "Urgent — +{urgent}% (up to 20 slides)\n"
        "Full text written for you — +{text}\n"
        "Speaker notes — +{notes}\n\n"
        "<i>Included: design for your topic, photos and charts, PPTX and PDF, two rounds of edits.</i>"
    ),
    "btn_packages": "Packs — cheaper",
    "packages": "<b>Packs</b>\nEach presentation is cheaper. The balance doesn't expire — it carries over to a new pack.",
    "package_line": "<b>{name}</b> — {price} UZS · {per} each · {days} days",
    "plan_week": "2 presentations",
    "plan_month": "4 presentations",
    "plan_vip": "VIP · 10 presentations",
    "packages_note": "<i>21–30 slides use two presentations. Urgency and full text are paid separately.</i>",
    "my_package": "\n\n<b>Your pack</b>: {left} of {total} left, until {date}.",
    "btn_buy": "{plan} — {price} UZS",
    "gift_promo": "\n\n🎁 Until {date} — a Telegram gift with any pack.",
    "pkg_requested": "Pack «{plan}». Payment details below — I'll turn it on as soon as it's paid.",
    "pkg_on": "<b>Pack «{plan}» is on</b>\nAvailable: {left} · until {date}.\nOrder as usual — it's deducted from the pack.",
    "gift_text": "Thank you for choosing SlideLab! May your presentations get top marks.",
    "gift_sent": "🎁 Your pack gift is already in your Telegram profile.",
    # --- examples and questions ---
    "examples": "<b>Our work</b>\nEach presentation has its own style for the topic.",
    "examples_channel": "All work and styles — in the channel {channel}",
    "examples_soon": "Examples are coming soon. Meanwhile, order — the cover in your topic's style is free.",
    "help": "<b>Questions</b>",
    "btn_ask": "Ask the manager",
    "btn_language": "Language",
    "ask_prompt": "Write your question in one message — I'll pass it to the manager. The answer will come here.",
    "question_sent": "Sent. We'll reply right here in the chat.",
    "menu_updated": "The menu has been updated — buttons are below.",
    "stale_button": "This button is from the previous version of the bot. Open the order in “My orders” for the current buttons.",
    "manager_reply": "<b>SlideLab reply</b>",
    "paysupport": "About payments and refunds — write here or to @{admin}. If an order is cancelled before work starts, we refund the Stars.",
    # --- order form ---
    "step": "<i>Step {n} of {total}</i>",
    "ask_topic": "<b>Presentation topic</b>\nE.g.: <i>Japan's economy after 1990</i>",
    "topic_short": "The topic is too short — at least 3 characters.",
    "topic_long": "The topic is longer than 300 characters — please shorten it.",
    "ask_slides": "<b>How many slides?</b>",
    "slides_s10": "Up to 10",
    "slides_s20": "11–20",
    "slides_s30": "21–30",
    "ask_deadline": "<b>Deadline</b>",
    "dl_urgent": "Urgent · +50%",
    "dl_normal": "Regular — we'll agree in the chat",
    "dl_relaxed": "No rush",
    "ask_plang": "<b>Presentation language</b>",
    "plang_ru": "Русский",
    "plang_uz": "O‘zbek",
    "plang_en": "English",
    "ask_design": "<b>Design</b>\nDo you have a template or example — or should we design for the topic?",
    "ds_ours": "Design it for my topic",
    "ds_own": "I have a template",
    "ask_template": (
        "<b>Template</b>\nSend a link (Canva, Google Slides, Figma, Drive) with «Anyone with the link» access "
        "— or the file itself."
    ),
    "btn_template_later": "I'll send it later",
    "ask_extras": "<b>Extras</b>\nTick what you need and tap «Next».",
    "x_text": "Full text · +5 000",
    "x_notes": "Speaker notes · +5 000",
    "x_humor": "With humor · free",
    "btn_next": "Next",
    "ask_files": "<b>Materials</b>\nLecture, handout, teacher's requirements — send files or text. Several are fine.",
    "files_got": "Received: {n}. More — or «Done».",
    "btn_done": "Done",
    "btn_skip": "No materials",
    "ask_contact": "<b>How can we reach you?</b>\nTap the button to share your number. Or type a username.",
    "btn_phone": "Share my number",
    "summary": (
        "<b>Check your request</b>\n\n"
        "{topic}\n"
        "{slides} slides · {deadline}\n"
        "{plang} · {design}{extras}{files}\n\n"
        "{price}"
    ),
    "summary_files": "\nMaterials: {n}",
    "price_cash": "<b>{price} UZS</b>\n<i>No payment now — we'll send a free cover first.</i>",
    "price_first": " · first order discount",
    "price_package": "<b>From your pack</b>: {cost}, {left} left",
    "price_package_extra": "<b>From your pack</b>: {cost}, {left} left\nExtra — {price} UZS",
    "btn_send": "Send request",
    "btn_restart": "Start over",
    "btn_cancel": "Cancel",
    "humor_label": "with humor",
    "text_label": "full text",
    "notes_label": "speaker notes",
    # --- request received ---
    "order_created": ("<b>Order #{id} received</b>\nWe're making a free cover — I'll send it here.{package}"),
    "order_created_files": "\n\nHave materials? Forward them here from any chat — no need to save them to your phone.",
    "order_created_tpl": "\n\nSend your template: a file or a link with open access.",
    "package_used": "\n\n{cost} deducted from your pack, {left} left.",
    "package_extra": " Extra — {price} UZS.",
    "package_empty": "\n\nYour pack is used up — this order is at the regular price.",
    "files_attached": "Added to order #{id}.",
    # --- quick order from a file ---
    "quick_ask": "<b>Let's make a presentation from this file</b>\nHow many slides?",
    "quick_deadline": "<b>Deadline</b>",
    "quick_more": "File added — {n} in total. Choose an option with the buttons above.",
    "quick_topic": "From file: {name}",
    # --- cover ---
    "cover_ready": "<b>Cover for order #{id}</b>\nIt's free. Do you like it?",
    "btn_cover_ok": "I like it",
    "btn_cover_change": "Change it",
    "cover_change_prompt": "What should we change in the cover — colour, style, photo, text? A screenshot of an example helps.",
    "cover_change_sent": "Passed to the designer — I'll send a new version.",
    "cover_go": "<b>Great!</b>\nStarting the full presentation — I'll send it when it's ready.",
    "cover_pay": "<b>Great!</b>\nOnly payment is left — then we start right away.",
    # --- payment ---
    "pay_order": "<b>Payment for order #{id}</b>\n{price} UZS",
    "pay_package": "<b>Pack «{plan}»</b>\n{price} UZS",
    "pay_credit": "\n<i>Order #{id} counted: −{amount} UZS.</i>",
    "pay_early": "\n\n<i>The cover is free. You can pay now or after you see it.</i>",
    "pay_cards": "\n\nTransfer to a card — tap the number to copy it:\n{cards}{name}\n\nThen tap «I've paid» and send the receipt.",
    "pay_name": "\nRecipient: {name}",
    "pay_stars_only": "\n\nPay with Telegram Stars — one button, confirmed instantly.",
    "pay_stars_too": "\n\nOr with Telegram Stars — confirmed instantly.",
    "pay_manual": "\n\nThe manager will tell you how to pay.",
    "btn_pay_stars": "⭐ With Stars · {stars}",
    "btn_paid": "I've paid by card",
    "receipt_ask": "Send a screenshot or photo of the receipt. Text is fine too: amount, time, which card.",
    "receipt_sent": "Thank you! I'll check the payment and confirm — usually within an hour.",
    "invoice_order": "SlideLab · order #{id}",
    "invoice_order_desc": "«{topic}» · {slides} slides. The full presentation, the cover is free.",
    "invoice_package": "SlideLab · {plan}",
    "invoice_package_desc": "{count} presentations for {days} days. The balance doesn't expire.",
    "already_paid": "Already paid.",
    "paid_go": "<b>Payment received</b>\nStarting the full presentation for order #{id}.",
    "paid_early": "<b>Payment received</b>\nFirst I'll send the cover — after your «I like it» we make the full presentation.",
    "payment_not_found": "I couldn't find the payment for {what}. If you've already paid, write here and we'll sort it out.",
    "what_order": "order #{id}",
    "what_package": "the «{plan}» pack",
    # --- done ---
    "formats_ask": "<b>Presentation #{id} is ready</b>\nWhich format would you like?",
    "fmt_pptx": "PowerPoint",
    "fmt_pdf": "PDF",
    "fmt_png": "Images",
    "fmt_gslides": "Google Slides",
    "fmt_canva": "Canva",
    "fmt_all": "All formats",
    "fmt_sending": "Sending…",
    "fmt_none": "That format isn't available — write to us and we'll send it.",
    "deck_ready": "<b>Presentation #{id} is ready</b>",
    "link_gslides": "<b>Google Slides</b> — your own copy:\n{url}\n\nTap «Make a copy» — it will appear in your Google Drive.",
    "link_canva": "<b>Canva</b> — your own copy:\n{url}\n\nTap «Use template» — a copy will appear in your Canva account.",
    "how_gslides": (
        "<b>How to open in Google Slides</b>\n"
        "1. Save the PPTX above\n2. drive.google.com → «New» → «File upload»\n"
        "3. Open the file → «Open with Google Slides»"
    ),
    "how_canva": (
        "<b>How to open in Canva</b>\n"
        "1. Save the PPTX above\n2. In Canva: «Create a design» → «Import file»\n3. Pick the PPTX — everything is editable"
    ),
    "after_delivery": "Need changes? Two rounds of edits are free.\n<i>Another format — use the buttons in the message above.</i>",
    "btn_revise": "Request edits",
    "btn_all_good": "All good",
    "revise_prompt": (
        "<b>Edits for order #{id}</b>\n"
        "Write what to change — e.g. «slide 3: another chart». Screenshots and files are welcome. "
        "When you're done, tap «Send»."
    ),
    "btn_send_revision": "Send edits",
    "revise_empty": "Describe what to change.",
    "revise_sent": "Edits sent — I'll send the corrected version.",
    "revise_paid": "\n<i>Free edits are used up — the manager will tell you the price.</i>",
    "revise_not_allowed": "You can request edits once the order is ready.",
    "rate_ask": "Rate our work:",
    "rate_thanks": "Thanks for the rating!",
    # --- credit towards a pack ---
    "credit_offer": (
        "<b>Liked it? Let's make it cheaper</b>\n"
        "Get a pack before {date} — this order ({amount} UZS) counts towards it. Pay only the difference:\n\n{lines}"
    ),
    "credit_line": "{plan}: <s>{full}</s> → <b>{pay} UZS</b> · {more} more",
    "btn_credit": "{plan} — {pay} UZS",
    "credit_expired": "The offer has expired — the pack is available at the regular price.",
    # --- my orders ---
    "orders_title": "<b>My orders</b>",
    "orders_empty": "No orders yet. Tap «New presentation» — it takes a couple of minutes.",
    "order_row": "#{id} · {status} · {topic}",
    "order_card": "<b>Order #{id}</b> · {status}\n{topic}\n{slides} slides · {price}",
    "price_from_package": "from your pack",
    "btn_pay": "Pay",
    "btn_get_files": "Get the files",
    "btn_hide": "Remove from list",
    "hidden": "Removed #{id} from the list. The files in the chat are still here.",
    "st_new": "Received",
    "st_cover": "Cover ready",
    "st_awaiting_payment": "Awaiting payment",
    "st_work": "In progress",
    "st_done": "Done",
    "st_revision": "Making edits",
    "st_cancelled": "Cancelled",
    "status_changed": "<b>Order #{id}</b> · {status}\n{topic}",
    "order_cancelled": "<b>Order #{id} cancelled</b>",
    "stars_refunded": "Refunded {amount} ⭐ for order #{id}.",
}
