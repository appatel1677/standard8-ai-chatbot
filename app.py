import streamlit as st
import streamlit.components.v1 as components
import json, os, io, re, math
from PIL import Image
from fpdf import FPDF

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patches as patches
    from matplotlib import font_manager
    HAS_MPL = True
except ImportError:
    HAS_MPL = False

try:
    from google import genai
    from google.genai import types
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False

st.set_page_config(
    page_title="Standard 3 to 8 Smart AI Palaj Teacher",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="collapsed"
)

ACTIVE_MODELS = [
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-3-flash-preview",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
]

DEFAULT_IMAGE_MODELS = [
    "gemini-2.5-flash-image",
    "gemini-3-pro-image-preview",
    "gemini-2.0-flash-exp-image-generation",
]

def get_available_models_for_client(client, preferred_model):
    candidates = list(dict.fromkeys([preferred_model] + ACTIVE_MODELS))
    try:
        discovered = []
        for m in client.models.list():
            name = (getattr(m, "name", "") or "").replace("models/", "")
            methods = getattr(m, "supported_generation_methods", None) or getattr(m, "supported_actions", None) or []
            if "gemini" in name.lower() and not any(x in name.lower() for x in ("embedding", "imagen", "veo", "aqa", "tts", "audio", "robotics", "image")):
                if not methods or "generateContent" in methods:
                    discovered.append(name)
        flash_models = [n for n in discovered if "flash" in n.lower()]
        other_models = [n for n in discovered if "flash" not in n.lower()]
        for n in flash_models + other_models:
            if n not in candidates:
                candidates.append(n)
    except Exception:
        pass
    return candidates

def get_available_image_models(client):
    img_candidates = list(DEFAULT_IMAGE_MODELS)
    imagen_candidates = ["imagen-3.0-generate-002", "imagen-3.0-fast-generate-001"]
    try:
        for m in client.models.list():
            name = (getattr(m, "name", "") or "").replace("models/", "")
            low = name.lower()
            if "image" in low and "imagen" not in low and name not in img_candidates:
                img_candidates.insert(0, name)
            elif "imagen" in low and name not in imagen_candidates:
                imagen_candidates.insert(0, name)
    except Exception:
        pass
    return img_candidates, imagen_candidates

# --- PDF & MCQ HELPERS ---
def parse_mcq(text):
    questions = []
    for part in re.split(r'\n?પ્રશ્ન\s*\d+\s*[:.]', text)[1:]:
        lines = [l.strip() for l in part.strip().splitlines() if l.strip()]
        if not lines:
            continue
        q_text, options, answer, explanation = lines[0], {}, None, ""
        for l in lines[1:]:
            if m := re.match(r'([ABCD])[\).]\s*(.*)', l):
                options[m.group(1)] = m.group(2)
            elif re.search(r'સાચો જવાબ|જવાબ|Answer', l) and (ma := re.search(r'([ABCD])', l)):
                answer = ma.group(1)
            elif re.search(r'સમજૂતી|Explanation', l):
                explanation = re.sub(r'^(સમજૂતી|Explanation)[:.]?\s*', '', l)
        if q_text and options and answer:
            questions.append({"question": q_text, "options": options, "answer": answer, "explanation": explanation})
    return questions

@st.cache_resource
def get_pdf_font():
    for p in ["C:/Windows/Fonts/Nirmala.ttf", "C:/Windows/Fonts/Shruti.ttf", "NotoSansGujarati-Regular.ttf"]:
        if os.path.exists(p):
            return p
    try:
        import urllib.request
        urllib.request.urlretrieve(
            "https://github.com/google/fonts/raw/main/ofl/notosansgujarati/NotoSansGujarati%5Bwdth%2Cwght%5D.ttf",
            "NotoSansGujarati-Regular.ttf"
        )
        return "NotoSansGujarati-Regular.ttf"
    except Exception:
        return None

def build_pdf_bytes(messages):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_text_shaping(True)
    font_path = get_pdf_font()
    base_font = "Gujarati" if font_path else "helvetica"
    if font_path:
        pdf.add_font("Gujarati", "", font_path)
        pdf.add_font("Gujarati", "B", font_path)
    pdf.add_page()
    pdf.set_font(base_font, "B", 15)
    pdf.cell(0, 10, "Standard 3 to 8 Smart AI Palaj Teacher - Notes", ln=True, align="C")
    pdf.ln(4)
    for m in messages:
        pdf.set_font(base_font, "B", 11)
        pdf.cell(0, 7, ("વિદ્યાર્થી:" if m["role"] == "user" else "શિક્ષક:"), ln=True)
        pdf.set_font(base_font, "", 10)
        clean_txt = re.sub(r"<svg[\s\S]*?</svg>", "[આકૃતિ / નકશો સંલગ્ન છે]", m["content"])
        clean_txt = re.sub(r"```(?:map_json|village_map_json)[\s\S]*?```", "[નકશો સંલગ્ન છે]", clean_txt)
        clean_txt = re.sub(r"<[^>]+>", "", clean_txt)
        pdf.multi_cell(0, 6, clean_txt)
        pdf.ln(2)
    return bytes(pdf.output(dest="S"))

def format_friendly_error(err_str):
    e = str(err_str)
    if "429" in e or "RESOURCE_EXHAUSTED" in e:
        return "API Key નો આજનો ફ્રી ક્વોટા (Limit) પૂરો થઈ ગયો છે. નવી API Key ઉમેરો અથવા થોડીવાર પછી ફરી પ્રયાસ કરો."
    if "400" in e and ("API_KEY_INVALID" in e or "API key not valid" in e):
        return "તમારી GEMINI_API_KEY ખોટી છે. Secrets માં સાચી API Key તપાસો."
    if "403" in e:
        return "API Key પર પરમિશન નથી અથવા બ્લોક થઈ છે."
    return f"કનેક્શન સમસ્યા આવી છે: {e[:160]}"

def transcribe_gujarati(audio_file, api_keys, preferred_model="gemini-3.5-flash", lang_name="ગુજરાતી"):
    if not HAS_GENAI or not api_keys or not audio_file:
        return "", "API Key અથવા ઓડિયો ઉપલબ્ધ નથી."

    audio_bytes = audio_file.getvalue()
    if len(audio_bytes) < 100:
        return "", "ઓડિયો રેકોર્ડ થયો નથી, ફરીથી બોલો."

    detected_mime = getattr(audio_file, "type", None) or "audio/wav"
    mime_candidates = list(dict.fromkeys([detected_mime, "audio/wav", "audio/webm", "audio/mp4", "audio/ogg"]))

    script_hint = {
        "ગુજરાતી": "Gujarati script (ગુજરાતી લિપિ)",
        "English": "English text",
        "हिन्दी": "Hindi Devanagari script (हिन्दी लिपि)"
    }.get(lang_name, "Gujarati script (ગુજરાતી લિપિ)")

    prompt = (
        f"Listen to this audio carefully and transcribe ONLY the exact spoken words in {script_hint}. "
        "Do not add any explanation, translation, or extra text."
    )

    last_err = ""
    for key in api_keys:
        client = genai.Client(api_key=key)
        model_candidates = get_available_models_for_client(client, preferred_model)
        for mod in model_candidates:
            for mime in mime_candidates:
                try:
                    resp = client.models.generate_content(
                        model=mod,
                        contents=[types.Part.from_bytes(data=audio_bytes, mime_type=mime), prompt]
                    )
                    if resp and resp.text and resp.text.strip():
                        return resp.text.strip(), ""
                except Exception as e:
                    last_err = str(e)
                    if any(x in last_err for x in ("404", "429", "RESOURCE_EXHAUSTED", "API_KEY_INVALID")):
                        break
            if any(x in last_err for x in ("429", "RESOURCE_EXHAUSTED", "API_KEY_INVALID")):
                break

    return "", format_friendly_error(last_err)

@st.cache_data
def load_syllabus():
    if os.path.exists("diksha_syllabus.json"):
        with open("diksha_syllabus.json", "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

# --- MATPLOTLIB VILLAGE CENSUS / BLO / VOTER LIST MAP ENGINE ---
def render_village_census_map_matplotlib(spec):
    if not HAS_MPL:
        return None
    font_path = get_pdf_font()
    prop_title = font_manager.FontProperties(fname=font_path, size=14, weight="bold") if font_path else None
    prop_sub = font_manager.FontProperties(fname=font_path, size=10) if font_path else None
    prop_sec = font_manager.FontProperties(fname=font_path, size=10, weight="bold") if font_path else None
    prop_small = font_manager.FontProperties(fname=font_path, size=8.5) if font_path else None

    fig, ax = plt.subplots(figsize=(13.5, 8.5), dpi=200)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")
    fig.patch.set_facecolor("#F8FAFC")

    title = spec.get("title", "ગામનો મતદાર યાદી સુધારણા / વસ્તી ગણતરી નજરી નકશો (BLO Map)")
    subtitle = spec.get("subtitle", "મહોલ્લા, ઘર નંબર, બજાર, ધાર્મિક અને જાહેર સ્થળોની વિગત")
    ax.text(50, 96.5, title, ha="center", va="center", color="#1E3A8A", fontproperties=prop_title)
    ax.text(50, 93.2, subtitle, ha="center", va="center", color="#475569", fontproperties=prop_sub)

    # Outer Village Border & North Compass
    ax.add_patch(patches.FancyBboxPatch((2, 4), 69, 86, boxstyle="round,pad=0.6", facecolor="#FEFCE8", edgecolor="#854D0E", linewidth=2))
    ax.annotate("ઉત્તર\n↑", xy=(67, 88), xytext=(67, 81), ha="center", va="center",
                arrowprops=dict(arrowstyle="->", lw=2, color="#1E3A8A"), color="#1E3A8A", fontproperties=prop_sec)

    # River & Pond
    if spec.get("has_river", True):
        rx = [3, 18, 35, 52, 70]
        ry = [87, 85, 86, 84, 85]
        ax.plot(rx, ry, color="#0284C7", linewidth=9, alpha=0.45, solid_capstyle="round")
        ax.plot(rx, ry, color="#0369A1", linewidth=1.5, linestyle="--")
        ax.text(36, 86, f"〰️ {spec.get('river_name', 'ગામની નદી')} 〰️", ha="center", va="center", color="#0C4A6E", fontproperties=prop_small)

    if spec.get("has_pond", True):
        pond = patches.Ellipse((12, 14), 14, 9, facecolor="#BAE6FD", edgecolor="#0284C7", linewidth=1.8)
        ax.add_patch(pond)
        ax.text(12, 14, f"💧 {spec.get('pond_name', 'ગામ તળાવ')}", ha="center", va="center", color="#0369A1", fontproperties=prop_small)

    # Main Roads (Cross Roads)
    ax.add_patch(patches.Rectangle((3, 47), 67, 4.2, facecolor="#CBD5E1", edgecolor="#64748B", linewidth=1))
    ax.plot([3, 70], [49.1, 49.1], color="#FFFFFF", linewidth=1.2, linestyle="--")
    ax.text(36.5, 49.1, f"🛣️ {spec.get('main_road_name', 'મુખ્ય ગામ રસ્તો')}", ha="center", va="center", color="#0F172A", fontproperties=prop_small)

    ax.add_patch(patches.Rectangle((34.5, 6), 3.8, 76, facecolor="#CBD5E1", edgecolor="#64748B", linewidth=1))
    ax.plot([36.4, 36.4], [6, 82], color="#FFFFFF", linewidth=1.2, linestyle="--")

    # 4 Mohallas / Sectors with House Boxes
    mohallas = spec.get("mohallas") or [
        {"name": "વિભાગ-૧ (પટેલ વાસ)", "houses": ["ઘર-1", "ઘર-2", "ઘર-3", "ઘર-4", "ઘર-5", "ઘર-6"]},
        {"name": "વિભાગ-૨ (ઠાકોર વાસ)", "houses": ["ઘર-7", "ઘર-8", "ઘર-9", "ઘર-10", "ઘર-11", "ઘર-12"]},
        {"name": "વિભાગ-૩ (વણકર વાસ)", "houses": ["ઘર-13", "ઘર-14", "ઘર-15", "ઘર-16", "ઘર-17", "ઘર-18"]},
        {"name": "વિભાગ-૪ (નાનું બજાર અને દુકાનો)", "houses": ["કરિયાણા દુકાન", "દૂધ ડેરી", "મેડિકલ", "ઘર-19", "ઘર-20", "ઘર-21"]},
    ]
    zone_boxes = [
        (5, 55, 27, 23, "#DCFCE7", "#15803D"),   # Top-Left
        (40, 55, 28, 23, "#DBEAFE", "#1D4ED8"),  # Top-Right
        (5, 22, 27, 22, "#FCE7F3", "#BE185D"),   # Bottom-Left
        (40, 22, 28, 22, "#FEF3C7", "#B45309"),  # Bottom-Right
    ]

    for idx_z, moh in enumerate(mohallas[:4]):
        zx, zy, zw, zh, bg_col, bd_col = zone_boxes[idx_z]
        ax.add_patch(patches.FancyBboxPatch((zx, zy), zw, zh, boxstyle="round,pad=0.4", facecolor=bg_col, edgecolor=bd_col, linewidth=1.5, alpha=0.85))
        ax.text(zx + zw / 2, zy + zh - 2.3, f"🏘️ {moh.get('name', '')}", ha="center", va="center", color="#0F172A", fontproperties=prop_sec)
        houses = moh.get("houses", [])[:8]
        cols = 3
        for idx_h, h_lbl in enumerate(houses):
            r_i, c_i = divmod(idx_h, cols)
            hx = zx + 1.5 + c_i * ((zw - 2.5) / cols)
            hy = zy + zh - 7.5 - r_i * 5.2
            is_shop = any(w in str(h_lbl) for w in ("દુકાન", "બજાર", "ડેરી", "મેડિકલ", "shop"))
            h_fc = "#FDE047" if is_shop else "#FFFFFF"
            ax.add_patch(patches.Rectangle((hx, hy), (zw - 4.5) / cols, 3.8, facecolor=h_fc, edgecolor="#334155", linewidth=1))
            ax.text(hx + ((zw - 4.5) / cols) / 2, hy + 1.9, str(h_lbl)[:12], ha="center", va="center", color="#0F172A", fontproperties=prop_small)

    # Landmarks (Panchayat, School, Hospital, Bank, Post, Temple, Garden)
    landmarks = spec.get("landmarks") or [
        {"name": "ગ્રામ પંચાયત", "type": "govt"},
        {"name": "પ્રાથમિક શાળા", "type": "school"},
        {"name": "દવાખાનું / હોસ્પિટલ", "type": "hospital"},
        {"name": "બેંક / પોસ્ટ ઓફિસ", "type": "bank"},
        {"name": "મંદિર / ધાર્મિક સ્થળ", "type": "temple"},
        {"name": "બગીચો (Garden)", "type": "garden"},
    ]
    landmark_slots = [(22, 80.5), (48, 80.5), (15, 52.8), (56, 52.8), (27, 14), (54, 14), (15, 45.2), (56, 45.2)]
    type_styles = {
        "govt": ("#DBEAFE", "#1D4ED8", "🏛️"),
        "school": ("#FEF3C7", "#D97706", "🏫"),
        "hospital": ("#FEE2E2", "#DC2626", "🏥"),
        "bank": ("#E0E7FF", "#4338CA", "🏦"),
        "post": ("#FCE7F3", "#BE185D", "📮"),
        "temple": ("#FFEDD5", "#C2410C", "🛕"),
        "garden": ("#BBF7D0", "#166534", "🌳"),
    }
    for i, lm in enumerate(landmarks[:8]):
        lx, ly = landmark_slots[i]
        bg_c, bd_c, icon = type_styles.get(str(lm.get("type", "govt")).lower(), ("#F1F5F9", "#334155", "📍"))
        ax.add_patch(patches.FancyBboxPatch((lx - 6.2, ly - 1.9), 12.4, 3.8, boxstyle="round,pad=0.25", facecolor=bg_c, edgecolor=bd_c, linewidth=1.2))
        ax.text(lx, ly, f"{icon} {lm.get('name', '')[:16]}", ha="center", va="center", color="#0F172A", fontproperties=prop_small)

    # Right-Side Legend Box
    ax.add_patch(patches.FancyBboxPatch((73, 4), 25, 86, boxstyle="round,pad=0.6", facecolor="#FFFFFF", edgecolor="#CBD5E1", linewidth=1.5))
    ax.text(85.5, 87.5, "📌 સંજ્ઞા સૂચિ (Legend)", ha="center", va="center", color="#1E3A8A", fontproperties=prop_sec)
    ax.plot([74.5, 96.5], [85, 85], color="#CBD5E1", linewidth=1)

    legend_entries = [
        ("#FFFFFF", "#334155", "🏠 રહેણાંક ઘર (ઘર નંબર)"),
        ("#FDE047", "#B45309", "🏪 નાનું બજાર / દુકાનો"),
        ("#DBEAFE", "#1D4ED8", "🏛️ ગ્રામ પંચાયત ઓફિસ"),
        ("#FEF3C7", "#D97706", "🏫 પ્રાથમિક શાળા"),
        ("#FEE2E2", "#DC2626", "🏥 દવાખાનું / હોસ્પિટલ"),
        ("#E0E7FF", "#4338CA", "🏦 બેંક / પોસ્ટ ઓફિસ"),
        ("#FFEDD5", "#C2410C", "🛕 મંદિર / ધાર્મિક સ્થળ"),
        ("#BBF7D0", "#166534", "🌳 બગીચો (Garden)"),
        ("#BAE6FD", "#0284C7", "💧 તળાવ / નદી"),
        ("#CBD5E1", "#64748B", "🛣️ મુખ્ય રસ્તો / શેરી"),
    ]
    for idx_l, (fc, ec, ltxt) in enumerate(legend_entries):
        ly_pos = 80.5 - idx_l * 6.5
        ax.add_patch(patches.Rectangle((75, ly_pos - 1.3), 3.0, 2.6, facecolor=fc, edgecolor=ec, linewidth=1.1))
        ax.text(79.0, ly_pos, ltxt, ha="left", va="center", color="#0F172A", fontproperties=prop_small)

    total_note = str(spec.get("total_houses_note", "કુલ ઘર અને જાહેર સ્થળો દર્શાવેલ છે"))
    ax.add_patch(patches.FancyBboxPatch((74.5, 6), 22, 8.5, boxstyle="round,pad=0.35", facecolor="#EFF6FF", edgecolor="#93C5FD", linewidth=1))
    ax.text(85.5, 12.0, "📋 BLO / વસ્તી ગણતરી નોંધ:", ha="center", va="center", color="#1E3A8A", fontproperties=prop_small)
    ax.text(85.5, 8.5, total_note[:32], ha="center", va="center", color="#1E293B", fontproperties=prop_small)

    buf = io.BytesIO()
    plt.tight_layout(pad=0.3)
    fig.savefig(buf, format="png", dpi=200)
    plt.close(fig)
    return buf.getvalue()
# --- NANO BANANA (GEMINI IMAGE GEN) TEXTBOOK MAP & DIAGRAM GENERATOR ---
def generate_nano_banana_visual(query_text, api_keys, visual_type="map", reply_lang="ગુજરાતી"):
    if not HAS_GENAI or not api_keys:
        return None, "API Key ઉપલબ્ધ નથી."

    lang_script = {
        "ગુજરાતી": "Gujarati script (ગુજરાતી લિપિ)",
        "English": "English text",
        "हिन्दी": "Hindi Devanagari script (हिन्दी लिपि)"
    }.get(reply_lang, "Gujarati script (ગુજરાતી લિપિ)")

    if visual_type == "map":
        prompt = (
            f"Create an authentic, full-color GCERT school textbook printed map page illustration for: '{query_text}'. "
            f"Print all headings, labels, state/district/kingdom/fort names, compass North arrow ('ઉત્તર'), ocean names, and a bottom-right legend box ('સંજ્ઞા સૂચિ') clearly in {lang_script}. "
            "Style: Authentic Indian school textbook cartography with crisp black borders, distinct pastel colors, light blue ocean water, bold header title at top."
        )
    else:
        prompt = (
            f"Create an authentic, full-color GCERT school textbook labeled educational diagram/drawing for: '{query_text}'. "
            f"Print the top title and all part pointer labels clearly in {lang_script}. "
            "Style: Pure white background, crisp dark outlines, vibrant educational textbook colors, neat straight pointer lines to each part."
        )

    last_img_err = ""
    for key in api_keys:
        client = genai.Client(api_key=key)
        nb_models, imagen_models = get_available_image_models(client)
        for nb_model in nb_models:
            try:
                res = client.models.generate_content(
                    model=nb_model,
                    contents=[prompt],
                    config=types.GenerateContentConfig(response_modalities=["IMAGE"])
                )
                for cand in getattr(res, "candidates", []) or []:
                    for part in getattr(cand.content, "parts", []) or []:
                        if getattr(part, "inline_data", None) and getattr(part.inline_data, "data", None):
                            return part.inline_data.data, ""
            except Exception as e:
                last_img_err = str(e)
        for img_mod in imagen_models:
            try:
                res = client.models.generate_images(
                    model=img_mod,
                    prompt=prompt,
                    config=types.GenerateImagesConfig(number_of_images=1, output_mime_type="image/jpeg", aspect_ratio="4:3")
                )
                if res and getattr(res, "generated_images", None):
                    return res.generated_images[0].image.image_bytes, ""
            except Exception as e3:
                last_img_err = str(e3)

    return None, last_img_err

# --- SMART MATH & GEOMETRY SVG BUILDER ---
def build_math_fraction_svg(query_text):
    q = (query_text or "").translate(str.maketrans("૦૧૨૩૪૫૬૭૮૯", "0123456789")).lower()

    if "ત્રિકોણ" in q or "triangle" in q:
        return """
        <svg width="100%" viewBox="0 0 520 300" xmlns="http://www.w3.org/2000/svg" style="max-height:300px; display:block; margin:auto;">
          <rect width="520" height="300" rx="12" fill="#FFFFFF"/>
          <text x="260" y="28" text-anchor="middle" font-size="17" font-weight="bold" fill="#1E3A8A">📐 ત્રિકોણની આકૃતિ અને તેના અંગો</text>
          <polygon points="260,60 130,240 390,240" fill="#DBEAFE" stroke="#1D4ED8" stroke-width="3"/>
          <circle cx="260" cy="60" r="5" fill="#DC2626"/><text x="260" y="48" text-anchor="middle" font-size="14" font-weight="bold" fill="#DC2626">શિરોબિંદુ A</text>
          <circle cx="130" cy="240" r="5" fill="#DC2626"/><text x="105" y="262" text-anchor="middle" font-size="14" font-weight="bold" fill="#DC2626">શિરોબિંદુ B</text>
          <circle cx="390" cy="240" r="5" fill="#DC2626"/><text x="415" y="262" text-anchor="middle" font-size="14" font-weight="bold" fill="#DC2626">શિરોબિંદુ C</text>
          <text x="175" y="145" font-size="13" font-weight="bold" fill="#0F172A">બાજુ AB</text>
          <text x="345" y="145" font-size="13" font-weight="bold" fill="#0F172A">બાજુ AC</text>
          <text x="260" y="262" text-anchor="middle" font-size="13" font-weight="bold" fill="#0F172A">પાયો BC (૩ બાજુ, ૩ ખૂણા)</text>
        </svg>"""

    if "ચોરસ" in q or "લંબચોરસ" in q or "square" in q or "rectangle" in q:
        is_rect = "લંબચોરસ" in q or "rectangle" in q
        w = 240 if is_rect else 160
        x0 = 260 - w // 2
        title_t = "લંબચોરસ (સામસામેની બાજુ સરખી)" if is_rect else "ચોરસ (ચારેય બાજુ સરખી)"
        return f"""
        <svg width="100%" viewBox="0 0 520 300" xmlns="http://www.w3.org/2000/svg" style="max-height:300px; display:block; margin:auto;">
          <rect width="520" height="300" rx="12" fill="#FFFFFF"/>
          <text x="260" y="28" text-anchor="middle" font-size="17" font-weight="bold" fill="#1E3A8A">📐 {title_t}</text>
          <rect x="{x0}" y="70" width="{w}" height="160" fill="#DCFCE7" stroke="#15803D" stroke-width="3"/>
          <text x="260" y="60" text-anchor="middle" font-size="13" font-weight="bold" fill="#0F172A">લંબાઈ (Length)</text>
          <text x="{x0 + w + 42}" y="155" text-anchor="middle" font-size="13" font-weight="bold" fill="#0F172A">પહોળાઈ</text>
          <text x="260" y="260" text-anchor="middle" font-size="13" font-weight="bold" fill="#15803D">દરેક ખૂણો ૯૦° (કાટખૂણો)</text>
        </svg>"""

    word_to_num = {"બે": 2, "2": 2, "ત્રણ": 3, "3": 3, "ચાર": 4, "4": 4, "પાંચ": 5, "5": 5, "છ": 6, "6": 6, "સાત": 7, "7": 7, "આઠ": 8, "8": 8}
    total_parts = 3
    for w, n in word_to_num.items():
        if re.search(rf"{w}\s*(?:ભાગ|સમાન ભાગ|ટુકડા|parts)", q):
            total_parts = n
            break

    frac_match = re.search(r"(\d+)\s*/\s*(\d+)", q)
    num, den = (int(frac_match.group(1)), int(frac_match.group(2))) if frac_match else (1, total_parts)
    if den == 0:
        den = total_parts

    cx, cy, r = 160, 165, 105
    palette = ["#93C5FD", "#86EFAC", "#FDE047", "#FDBA74", "#F9A8D4", "#C4B5FD", "#5EEAD4", "#FCA5A5"]
    left_slices = []
    for i in range(total_parts):
        a1, a2 = -90 + (360.0 / total_parts) * i, -90 + (360.0 / total_parts) * (i + 1)
        x1, y1 = cx + r * math.cos(math.radians(a1)), cy + r * math.sin(math.radians(a1))
        x2, y2 = cx + r * math.cos(math.radians(a2)), cy + r * math.sin(math.radians(a2))
        large_arc = 1 if (a2 - a1) > 180 else 0
        left_slices.append(f'<path d="M {cx},{cy} L {x1:.1f},{y1:.1f} A {r},{r} 0 {large_arc},1 {x2:.1f},{y2:.1f} Z" fill="{palette[i % len(palette)]}" stroke="#1E293B" stroke-width="2.2"/>')
        mid_a = math.radians((a1 + a2) / 2)
        left_slices.append(f'<text x="{cx + (r * 0.58) * math.cos(mid_a):.1f}" y="{cy + (r * 0.58) * math.sin(mid_a):.1f}" text-anchor="middle" dominant-baseline="middle" font-size="14" font-weight="bold" fill="#0F172A">ભાગ {i+1}</text>')

    cx2, cy2 = 430, 165
    right_slices = []
    disp_den, disp_num = max(den, 1), min(num, max(den, 1))
    for i in range(disp_den):
        a1, a2 = -90 + (360.0 / disp_den) * i, -90 + (360.0 / disp_den) * (i + 1)
        x1, y1 = cx2 + r * math.cos(math.radians(a1)), cy2 + r * math.sin(math.radians(a1))
        x2, y2 = cx2 + r * math.cos(math.radians(a2)), cy2 + r * math.sin(math.radians(a2))
        large_arc = 1 if (a2 - a1) > 180 else 0
        fill_c, txt_c = ("#2563EB", "#FFFFFF") if i < disp_num else ("#F1F5F9", "#334155")
        if disp_den == 1:
            right_slices.append(f'<circle cx="{cx2}" cy="{cy2}" r="{r}" fill="{fill_c}" stroke="#1E293B" stroke-width="2.2"/>')
        else:
            right_slices.append(f'<path d="M {cx2},{cy2} L {x1:.1f},{y1:.1f} A {r},{r} 0 {large_arc},1 {x2:.1f},{y2:.1f} Z" fill="{fill_c}" stroke="#1E293B" stroke-width="2.2"/>')
        mid_a = math.radians((a1 + a2) / 2)
        right_slices.append(f'<text x="{cx2 + (r * 0.55) * math.cos(mid_a):.1f}" y="{cy2 + (r * 0.55) * math.sin(mid_a):.1f}" text-anchor="middle" dominant-baseline="middle" font-size="14" font-weight="bold" fill="{txt_c}">1/{disp_den}</text>')

    return f"""
    <svg width="100%" viewBox="0 0 600 330" xmlns="http://www.w3.org/2000/svg" style="max-height:330px; display:block; margin:auto;">
      <rect width="600" height="330" rx="12" fill="#FFFFFF"/>
      <text x="300" y="28" text-anchor="middle" font-size="17" font-weight="bold" fill="#1E3A8A">📐 ગણિત આકૃતિ: વર્તુળના {total_parts} ભાગ અને {num}/{den} અપૂર્ણાંક</text>
      {''.join(left_slices)}
      <text x="{cx}" y="295" text-anchor="middle" font-size="14" font-weight="bold" fill="#0F172A">૧. વર્તુળના {total_parts} સમાન ભાગ</text>
      {''.join(right_slices)}
      <text x="{cx2}" y="295" text-anchor="middle" font-size="14" font-weight="bold" fill="#1D4ED8">૨. રંગીન ભાગ = {num}/{den}</text>
    </svg>"""

# --- INDIA & GUJARAT MAP COORDINATES + AUTO-MAP BUILDER ---
_INDIA_STATE_COORDS = {
    "jammu": (165, 52, "જમ્મુ-કાશ્મીર"), "ladakh": (195, 42, "લદ્દાખ"),
    "himachal": (182, 85, "હિમાચલ પ્રદેશ"), "punjab": (152, 102, "પંજાબ"),
    "haryana": (162, 122, "હરિયાણા"), "uttarakhand": (205, 112, "ઉત્તરાખંડ"),
    "rajasthan": (122, 165, "રાજસ્થાન"), "uttar pradesh": (225, 162, "ઉત્તર પ્રદેશ"),
    "bihar": (292, 178, "બિહાર"), "gujarat": (88, 222, "ગુજરાત"),
    "madhya pradesh": (185, 218, "મધ્ય પ્રદેશ"), "chhattisgarh": (245, 238, "છત્તીસગઢ"),
    "jharkhand": (285, 208, "ઝારખંડ"), "west bengal": (322, 222, "પશ્ચિમ બંગાળ"),
    "odisha": (282, 265, "ઓડિશા"), "maharashtra": (148, 275, "મહારાષ્ટ્ર"),
    "telangana": (202, 298, "તેલંગાણા"), "andhra pradesh": (212, 342, "આંધ્ર પ્રદેશ"),
    "karnataka": (152, 348, "કર્ણાટક"), "goa": (125, 332, "ગોવા"),
    "kerala": (158, 412, "કેરળ"), "tamil nadu": (192, 405, "તમિલનાડુ"),
    "assam": (382, 168, "આસામ"), "magadha": (296, 184, "મગધ (પાટલિપુત્ર)"),
    "vaishali": (286, 168, "વૈશાલી"), "avanti": (168, 215, "અવંતિ (ઉજ્જૈન)"),
    "kashi": (254, 176, "કાશી (વારાણસી)"), "kosala": (235, 155, "કોસલ (અયોધ્યા)"),
    "kalinga": (284, 268, "કલિંગ"), "hastinapur": (182, 128, "દિલ્હી / હસ્તિનાપુર"),
    "lothal": (86, 228, "લોથલ"), "dholavira": (72, 206, "ધોળાવીરા"),
    "chittorgarh": (132, 192, "ચિત્તોડગઢ કિલ્લો"), "raigad": (132, 286, "રાયગઢ કિલ્લો"),
    "golconda": (202, 304, "ગોલકોંડા કિલ્લો"), "gwalior": (194, 185, "ગ્વાલિયર કિલ્લો"),
}

_STATE_ALIASES = {
    "પંજાબ": "punjab", "ઉત્તર પ્રદેશ": "uttar pradesh", "પશ્ચિમ બંગાળ": "west bengal", "રાજસ્થાન": "rajasthan",
    "ગુજરાત": "gujarat", "મહારાષ્ટ્ર": "maharashtra", "મધ્ય પ્રદેશ": "madhya pradesh", "બિહાર": "bihar",
    "ઓડિશા": "odisha", "કર્ણાટક": "karnataka", "તમિલનાડુ": "tamil nadu", "આંધ્ર પ્રદેશ": "andhra pradesh",
    "તેલંગાણા": "telangana", "કેરળ": "kerala", "આસામ": "assam", "ઝારખંડ": "jharkhand",
    "છત્તીસગઢ": "chhattisgarh", "હરિયાણા": "haryana", "હિમાચલ પ્રદેશ": "himachal",
    "ઉત્તરાખંડ": "uttarakhand", "જમ્મુ": "jammu", "ગોવા": "goa", "મગધ": "magadha",
    "પાટલિપુત્ર": "magadha", "વૈશાલી": "vaishali", "અવંતિ": "avanti", "કાશી": "kashi",
    "કોસલ": "kosala", "કલિંગ": "kalinga", "દિલ્હી": "hastinapur", "લાલ કિલ્લો": "hastinapur",
    "લોથલ": "lothal", "ધોળાવીરા": "dholavira", "ચિત્તોડગઢ": "chittorgarh", "રાયગઢ": "raigad",
    "ગોલકોંડા": "golconda", "ગ્વાલિયર": "gwalior",
}

_GUJARAT_DISTRICT_COORDS = {
    "kutch": (98, 138, "કચ્છ (ભુજ)"), "banaskantha": (232, 86, "બનાસકાંઠા"), "patan": (212, 118, "પાટણ"),
    "mehsana": (245, 128, "મહેસાણા"), "sabarkantha": (282, 102, "સાબરકાંઠા"), "aravalli": (305, 125, "અરવલ્લી"),
    "gandhinagar": (262, 148, "ગાંધીનગર"), "ahmedabad": (242, 172, "અમદાવાદ"), "surendranagar": (195, 182, "સુરેન્દ્રનગર"),
    "morbi": (155, 178, "મોરબી"), "jamnagar": (108, 208, "જામનગર"), "devbhumi dwarka": (74, 218, "દ્વારકા"),
    "porbandar": (92, 248, "પોરબંદર"), "rajkot": (152, 218, "રાજકોટ"), "botad": (198, 215, "બોટાદ"),
    "bhavnagar": (212, 248, "ભાવનગર"), "amreli": (172, 258, "અમરેલી"), "junagadh": (128, 265, "જૂનાગઢ"),
    "gir somnath": (142, 288, "ગીર સોમનાથ"), "kheda": (278, 175, "ખેડા"), "anand": (266, 198, "આણંદ"),
    "mahisagar": (318, 152, "મહીસાગર"), "panchmahal": (322, 178, "પંચમહાલ"), "dahod": (354, 178, "દાહોદ"),
    "vadodara": (302, 205, "વડોદરા"), "chhota udaipur": (342, 212, "છોટા ઉદેપુર"), "bharuch": (288, 238, "ભરૂચ"),
    "narmada": (324, 238, "નર્મદા"), "surat": (292, 268, "સુરત"), "tapi": (326, 268, "તાપી"),
    "navsari": (292, 295, "નવસારી"), "dang": (322, 298, "ડાંગ"), "valsad": (288, 324, "વલસાડ"),
    "north gujarat": (255, 112, "ઉત્તર ગુજરાત"), "central gujarat": (295, 182, "મધ્ય ગુજરાત"),
    "saurashtra": (155, 228, "સૌરાષ્ટ્ર"), "south gujarat": (298, 282, "દક્ષિણ ગુજરાત"),
    "girnar": (128, 265, "ગિરનાર / ઉપરકોટ"), "pavagadh": (322, 178, "પાવાગઢ / ચાંપાનેર"),
    "chotila": (175, 202, "ચોટીલા"), "shetrunjay": (205, 255, "શેત્રુંજય"), "arasur": (245, 82, "આરાસુર"),
    "kalo dungar": (95, 118, "કાળો ડુંગર"), "lakhpat": (62, 125, "લખપત કિલ્લો"), "dholavira": (125, 118, "ધોળાવીરા"),
    "lothal": (235, 192, "લોથલ"), "idargadh": (282, 98, "ઈડરિયો ગઢ"), "dabhoi": (312, 212, "ડભોઈ કિલ્લો"),
    "saputara": (322, 298, "સાપુતારા"), "narmada river": (295, 238, "નર્મદા નદી"), "tapi river": (298, 268, "તાપી નદી"),
    "sabarmati river": (252, 165, "સાબરમતી નદી"), "mahi river": (285, 195, "મહી નદી"),
    "banas river": (222, 95, "બનાસ નદી"), "bhadar river": (135, 245, "ભાદર નદી"),
}

_GUJARAT_ALIASES = {
    "કચ્છ": "kutch", "ભુજ": "kutch", "બનાસકાંઠા": "banaskantha", "પાટણ": "patan", "મહેસાણા": "mehsana",
    "સાબરકાંઠા": "sabarkantha", "અરવલ્લી": "aravalli", "ગાંધીનગર": "gandhinagar", "અમદાવાદ": "ahmedabad",
    "સુરેન્દ્રનગર": "surendranagar", "મોરબી": "morbi", "જામનગર": "jamnagar", "દ્વારકા": "devbhumi dwarka",
    "પોરબંદર": "porbandar", "રાજકોટ": "rajkot", "બોટાદ": "botad", "ભાવનગર": "bhavnagar",
    "અમરેલી": "amreli", "જૂનાગઢ": "junagadh", "ઉપરકોટ": "girnar", "ગીર સોમનાથ": "gir somnath",
    "ખેડા": "kheda", "આણંદ": "anand", "મહીસાગર": "mahisagar", "પંચમહાલ": "panchmahal", "દાહોદ": "dahod",
    "વડોદરા": "vadodara", "છોટા ઉદેપુર": "chhota udaipur", "ભરૂચ": "bharuch", "નર્મદા": "narmada river",
    "સુરત": "surat", "તાપી": "tapi river", "નવસારી": "navsari", "ડાંગ": "dang", "વલસાડ": "valsad",
    "ઉત્તર ગુજરાત": "north gujarat", "મધ્ય ગુજરાત": "central gujarat", "સૌરાષ્ટ્ર": "saurashtra",
    "દક્ષિણ ગુજરાત": "south gujarat", "ગિરનાર": "girnar", "પાવાગઢ": "pavagadh", "ચાંપાનેર": "pavagadh",
    "ચોટીલા": "chotila", "શેત્રુંજય": "shetrunjay", "આરાસુર": "arasur", "કાળો ડુંગર": "kalo dungar",
    "સાપુતારા": "saputara", "લખપત": "lakhpat", "ધોળાવીરા": "dholavira", "લોથલ": "lothal",
    "ઈડર": "idargadh", "ડભોઈ": "dabhoi", "સાબરમતી": "sabarmati river", "મહી": "mahi river",
    "બનાસ": "banas river", "ભાદર": "bhadar river",
}

def build_india_map_html(map_spec):
    title = map_spec.get("title", "ભારતનો નકશો - નકશા પૂર્તિ")
    items = map_spec.get("items", [])
    india_outline = (
        "M 162,25 L 185,22 L 210,36 L 222,55 L 205,72 L 198,92 L 222,108 L 245,132 "
        "L 285,148 L 325,152 L 334,138 L 342,152 L 365,152 L 395,132 L 422,142 L 414,168 "
        "L 404,195 L 392,226 L 378,224 L 372,202 L 352,196 L 342,216 L 332,242 L 308,262 "
        "L 282,292 L 245,326 L 218,365 L 204,405 L 182,438 L 166,435 L 152,398 L 134,355 "
        "L 118,308 L 112,262 L 82,252 L 58,236 L 74,218 L 62,204 L 88,196 L 102,182 "
        "L 92,155 L 122,126 L 142,96 L 152,68 L 146,44 Z"
    )
    state_offset_count, markers_svg, legend_svg = {}, [], []
    for idx, item in enumerate(items[:8]):
        label, symbol, color, states = str(item.get("label", "")), str(item.get("symbol", "●")), str(item.get("color", "#DC2626")), item.get("states", [])
        ly = 74 + idx * 40
        short_st = ", ".join(states[:2]) + ("..." if len(states) > 2 else "")
        legend_svg.append(
            f'<rect x="448" y="{ly-14}" width="22" height="22" rx="5" fill="{color}" fill-opacity="0.18" stroke="{color}" stroke-width="1.5"/>'
            f'<text x="459" y="{ly+2}" text-anchor="middle" font-size="14" font-weight="bold" fill="{color}">{symbol}</text>'
            f'<text x="478" y="{ly-2}" font-size="12.5" font-weight="bold" fill="#0F172A">{label}</text>'
            f'<text x="478" y="{ly+13}" font-size="10.5" fill="#334155">({short_st})</text>'
        )
        for st_name in states:
            clean_s = st_name.strip().lower()
            key = _STATE_ALIASES.get(clean_s) or _STATE_ALIASES.get(st_name.strip())
            if not key:
                for ak, av in _STATE_ALIASES.items():
                    if ak in clean_s:
                        key = av
                        break
            if not key or key not in _INDIA_STATE_COORDS:
                continue
            bx, by, guj_st = _INDIA_STATE_COORDS[key]
            cnt = state_offset_count.get(key, 0)
            state_offset_count[key] = cnt + 1
            px, py = bx + ((cnt % 2) * 20 - (10 if cnt > 0 else 0)), by + ((cnt // 2) * 18)
            markers_svg.append(f'<circle cx="{px}" cy="{py}" r="11" fill="#FFFFFF" stroke="{color}" stroke-width="2"/><text x="{px}" y="{py+4}" text-anchor="middle" font-size="13" font-weight="bold" fill="{color}">{symbol}</text>')
            if cnt == 0:
                markers_svg.append(f'<text x="{bx}" y="{by+22}" text-anchor="middle" font-size="10.5" font-weight="bold" fill="#1E293B">{guj_st}</text>')

    legend_height = max(160, 65 + len(items[:8]) * 40)
    return f'<div style="background:#FFFFFF; border:2px solid #93C5FD; border-radius:14px; padding:10px; font-family:\'Noto Sans Gujarati\', sans-serif;"><svg width="100%" viewBox="0 0 680 460" xmlns="http://www.w3.org/2000/svg" style="max-height:450px; display:block; margin:auto;"><rect x="0" y="0" width="680" height="460" rx="12" fill="#F8FAFC"/><text x="340" y="26" text-anchor="middle" font-size="17" font-weight="bold" fill="#1E3A8A">{title}</text><g transform="translate(55, 65)"><circle cx="0" cy="0" r="18" fill="#EFF6FF" stroke="#3B82F6" stroke-width="1.5"/><line x1="0" y1="-13" x2="0" y2="13" stroke="#1E3A8A" stroke-width="1.5"/><line x1="-13" y1="0" x2="13" y2="0" stroke="#1E3A8A" stroke-width="1.5"/><text x="0" y="-21" text-anchor="middle" font-size="10" font-weight="bold" fill="#1E3A8A">ઉત્તર</text></g><path d="{india_outline}" fill="#FEF9C3" stroke="#92400E" stroke-width="2.2" stroke-linejoin="round"/>{"".join(markers_svg)}<rect x="438" y="34" width="232" height="{legend_height}" rx="10" fill="#FFFFFF" stroke="#CBD5E1" stroke-width="1.5"/><text x="554" y="51" text-anchor="middle" font-size="13.5" font-weight="bold" fill="#1E3A8A">📌 સંજ્ઞા સૂચિ (Legend)</text><line x1="448" y1="57" x2="660" y2="57" stroke="#E2E8F0" stroke-width="1"/>{"".join(legend_svg)}</svg></div>'

def build_gujarat_map_html(map_spec):
    title = map_spec.get("title", "ગુજરાતનો રાજકીય નકશો (૩૩ જિલ્લા)")
    items = map_spec.get("items", [])
    gujarat_outline = (
        "M 42,132 L 92,108 L 146,114 L 166,144 L 136,168 L 168,172 L 204,132 "
        "L 214,88 L 254,74 L 296,86 L 318,122 L 324,152 L 366,164 L 368,196 "
        "L 348,224 L 336,256 L 332,298 L 296,338 L 278,334 L 280,272 L 272,232 "
        "L 250,208 L 234,234 L 214,274 L 162,296 L 114,274 L 72,234 L 86,202 "
        "L 142,188 L 122,172 L 68,168 Z"
    )
    offset_count, markers_svg, legend_svg = {}, [], []
    for idx, item in enumerate(items[:8]):
        label, symbol, color, places = str(item.get("label", "")), str(item.get("symbol", "●")), str(item.get("color", "#2563EB")), item.get("states", [])
        ly = 74 + idx * 42
        short_places = ", ".join(places[:2]) + ("..." if len(places) > 2 else "")
        legend_svg.append(
            f'<rect x="408" y="{ly-14}" width="22" height="22" rx="5" fill="{color}" fill-opacity="0.18" stroke="{color}" stroke-width="1.5"/>'
            f'<text x="419" y="{ly+2}" text-anchor="middle" font-size="14" font-weight="bold" fill="{color}">{symbol}</text>'
            f'<text x="438" y="{ly-2}" font-size="12.5" font-weight="bold" fill="#0F172A">{label}</text>'
            f'<text x="438" y="{ly+13}" font-size="10.5" fill="#334155">({short_places})</text>'
        )
        for p_name in places:
            clean_p = p_name.strip().lower()
            key = _GUJARAT_ALIASES.get(clean_p) or _GUJARAT_ALIASES.get(p_name.strip())
            if not key:
                for alias_k, alias_v in _GUJARAT_ALIASES.items():
                    if alias_k in clean_p:
                        key = alias_v
                        break
            if not key or key not in _GUJARAT_DISTRICT_COORDS:
                continue
            bx, by, guj_name = _GUJARAT_DISTRICT_COORDS[key]
            cnt = offset_count.get(key, 0)
            offset_count[key] = cnt + 1
            px, py = bx + ((cnt % 2) * 14 - (7 if cnt > 0 else 0)), by + ((cnt // 2) * 14)
            markers_svg.append(f'<circle cx="{px}" cy="{py}" r="9.5" fill="#FFFFFF" stroke="{color}" stroke-width="2"/><text x="{px}" y="{py+3.5}" text-anchor="middle" font-size="11.5" font-weight="bold" fill="{color}">{symbol}</text>')
            if cnt == 0:
                markers_svg.append(f'<text x="{bx}" y="{by+19}" text-anchor="middle" font-size="9.5" font-weight="bold" fill="#0F172A">{guj_name}</text>')

    legend_height = max(175, 65 + len(items[:8]) * 42)
    return f'<div style="background:#FFFFFF; border:2px solid #93C5FD; border-radius:14px; padding:10px; font-family:\'Noto Sans Gujarati\', sans-serif;"><svg width="100%" viewBox="0 0 670 395" xmlns="http://www.w3.org/2000/svg" style="max-height:410px; display:block; margin:auto;"><rect x="0" y="0" width="670" height="395" rx="12" fill="#F0F9FF"/><text x="335" y="25" text-anchor="middle" font-size="16.5" font-weight="bold" fill="#1E3A8A">{title}</text><g transform="translate(46, 56)"><circle cx="0" cy="0" r="15" fill="#EFF6FF" stroke="#3B82F6" stroke-width="1.5"/><line x1="0" y1="-10" x2="0" y2="10" stroke="#1E3A8A" stroke-width="1.5"/><line x1="-10" y1="0" x2="10" y2="0" stroke="#1E3A8A" stroke-width="1.5"/><text x="0" y="-18" text-anchor="middle" font-size="9.5" font-weight="bold" fill="#1E3A8A">ઉત્તર</text></g><path d="{gujarat_outline}" fill="#DCFCE7" stroke="#15803D" stroke-width="2.2" stroke-linejoin="round"/><text x="115" y="184" font-size="9.5" fill="#0369A1" font-style="italic">કચ્છનો અખાત</text><text x="236" y="264" font-size="9.5" fill="#0369A1" font-style="italic">ખંભાતનો અખાત</text>{"".join(markers_svg)}<rect x="398" y="36" width="260" height="{legend_height}" rx="10" fill="#FFFFFF" stroke="#CBD5E1" stroke-width="1.5"/><text x="528" y="53" text-anchor="middle" font-size="13" font-weight="bold" fill="#1E3A8A">📌 સંજ્ઞા સૂચિ (વિભાગ / જિલ્લા)</text><line x1="408" y1="59" x2="648" y2="59" stroke="#E2E8F0" stroke-width="1"/>{"".join(legend_svg)}</svg></div>'

# --- GUARANTEED FALLBACK AUTO-MAP BUILDER (IF AI SKIPS map_json) ---
def auto_build_map_from_query(query_text):
    q = (query_text or "").lower()
    is_guj = "ગુજરાત" in q or "gujarat" in q or any(k in q for k in _GUJARAT_ALIASES)
    if is_guj and "ભારત" not in q and "મગધ" not in q:
        matched = [k for k in _GUJARAT_ALIASES if k in q]
        if matched:
            items = [{"label": "દર્શાવેલ સ્થળો", "symbol": "★", "color": "#DC2626", "states": matched[:10]}]
        else:
            items = [
                {"label": "કચ્છ પ્રદેશ", "symbol": "▲", "color": "#D97706", "states": ["કચ્છ"]},
                {"label": "ઉત્તર ગુજરાત", "symbol": "■", "color": "#2563EB", "states": ["બનાસકાંઠા", "મહેસાણા", "સાબરકાંઠા"]},
                {"label": "મધ્ય ગુજરાત", "symbol": "●", "color": "#16A34A", "states": ["અમદાવાદ", "ખેડા", "વડોદરા", "પંચમહાલ"]},
                {"label": "સૌરાષ્ટ્ર પ્રદેશ", "symbol": "◆", "color": "#9333EA", "states": ["રાજકોટ", "જામનગર", "જૂનાગઢ", "ભાવનગર"]},
                {"label": "દક્ષિણ ગુજરાત", "symbol": "★", "color": "#DC2626", "states": ["સુરત", "નવસારી", "વલસાડ", "ડાંગ"]},
            ]
        return build_gujarat_map_html({"region": "gujarat", "title": "ગુજરાતનો નકશો - ભૌગોલિક અને રાજકીય વિભાગો", "items": items}), 420
    else:
        matched = [k for k in _STATE_ALIASES if k in q]
        if matched:
            items = [{"label": "દર્શાવેલ પ્રદેશ / રાજ્યો", "symbol": "★", "color": "#DC2626", "states": matched[:10]}]
        else:
            items = [
                {"label": "ઉત્તર ભારત", "symbol": "▲", "color": "#2563EB", "states": ["દિલ્હી", "પંજાબ", "ઉત્તર પ્રદેશ"]},
                {"label": "પશ્ચિમ ભારત", "symbol": "■", "color": "#16A34A", "states": ["ગુજરાત", "રાજસ્થાન", "મહારાષ્ટ્ર"]},
                {"label": "પૂર્વ ભારત", "symbol": "★", "color": "#DC2626", "states": ["બિહાર", "પશ્ચિમ બંગાળ", "ઓડિશા"]},
                {"label": "દક્ષિણ ભારત", "symbol": "●", "color": "#9333EA", "states": ["કર્ણાટક", "તમિલનાડુ", "કેરળ"]},
            ]
        return build_india_map_html({"region": "india", "title": "ભારતનો નકશો - મુખ્ય રાજ્યો અને પ્રદેશો", "items": items}), 475

# --- DETECTION HELPERS ---
_GUJ_DIGIT_MAP = str.maketrans("૦૧૨૩૪૫૬૭૮૯", "0123456789")
_SUBJECT_LABELS = {
    "gujarati": "ગુજરાતી", "sanskrit": "સંસ્કૃત", "math": "ગણિત", "science": "વિજ્ઞાન",
    "social_science": "સામાજિક વિજ્ઞાન", "environment": "પર્યાવરણ (આસપાસ)",
    "english": "અંગ્રેજી", "hindi": "હિન્દી", "vedic_math": "વૈદિક ગણિત", "allround": "સર્વાંગી શિક્ષણ",
}
_EXPLICIT_SUBJECTS = {
    "social_science": ["સામાજિક વિજ્ઞાન", "સામાજિક", "social science", "social", "ઇતિહાસ", "ભૂગોળ", "નાગરિક", "નકશો", "નક્શો", "નકશા", "નકશાપૂર્તિ", "જિલ્લા", "ગુજરાત", "મગધ", "કિલ્લો", "કિલ્લા", "પ્રદેશ", "લોથલ", "ધોળાવીરા"],
    "vedic_math": ["વૈદિક ગણિત", "vedic math"],
    "math": ["ગણિત", "math", "maths", "ભૂમિતિ", "અપૂર્ણાંક", "વર્તુળ", "ત્રિકોણ", "ચોરસ"],
    "science": ["વિજ્ઞાન", "science", "પ્રકાશસંશ્લેષણ", "કોષ", "વિદ્યુત", "ચુંબક", "મીણબત્તી"],
    "environment": ["પર્યાવરણ", "આસપાસ", "environment", "evs"],
    "gujarati": ["ગુજરાતી", "gujarati", "કલશોર", "કેકારવ", "કુહૂ", "પલાશ", "વ્યાકરણ"],
    "sanskrit": ["સંસ્કૃત", "sanskrit", "સુભાષિતાનિ"],
    "english": ["અંગ્રેજી", "english", "grammar"],
    "hindi": ["હિન્દી", "hindi", "તિતલી"],
}

def wants_village_census_map(text):
    t = (text or "").lower()
    return any(kw in t for kw in ("મતદાર", "વસ્તી ગણતરી", "વસ્તીગણતરી", "મહોલ્લા", "મહોલ્લો", "વાસ", "ફળિયું", "ઘર નંબર", "પંચાયત", "દવાખાનું", "હોસ્પિટલ", "પોસ્ટ ઓફિસ", "બગીચો", "બજાર", "દુકાનો", "ગામનો નકશો", "ગામ નો નકશો", "village map", "census", "blo", "નજરી નકશો"))

def wants_math_geometry_visual(text):
    t = (text or "").lower()
    return any(k in t for k in ("વર્તુળ", "circle", "અપૂર્ણાંક", "ત્રિકોણ", "triangle", "ચોરસ", "લંબચોરસ", "square", "rectangle")) and any(w in t for w in ("ભાગ", "આકૃતિ", "દોરો", "બતાવો", "દર્શાવો", "1/", "2/", "3/", "ચિત્ર"))

def wants_diagram(text):
    t = (text or "").lower()
    return any(kw in t for kw in ("આકૃતિ", "નામનિર્દેશ", "ચિત્ર", "દોરો", "દોરી", "diagram", "draw", "sketch", "કોષ", "પ્રકાશસંશ્લેષણ", "મીણબત્તી", "પરિપથ", "ચુંબક"))

def wants_map(text):
    t = (text or "").lower()
    return any(kw in t for kw in ("નકશો", "નક્શો", "નકશા", "નક્શા", "નકશાપૂર્તિ", "map", "સંજ્ઞા વડે", "નકશામાં દર્શાવો", "કિલ્લા", "મગધ", "પ્રદેશો"))

def extract_grade(text):
    t = (text or "").translate(_GUJ_DIGIT_MAP).lower()
    for p in [r"ધોરણ\s*[-:.]?\s*([3-8])", r"ધો\.?\s*[-:.]?\s*([3-8])", r"std\.?\s*[-:.]?\s*([3-8])", r"grade\s*[-:.]?\s*([3-8])"]:
        if m := re.search(p, t):
            return int(m.group(1))
    return None

def extract_subject(text):
    t = (text or "").lower()
    for code, keywords in _EXPLICIT_SUBJECTS.items():
        for kw in keywords:
            if kw.lower() in t:
                return code
    return None

def resolve_grade_subject_and_pdfs(current_query, past_user_queries, syllabus):
    if wants_village_census_map(current_query):
        return None, None, []
    grade, subject = extract_grade(current_query), extract_subject(current_query)
    if not grade or not subject:
        return grade, subject, []
    matched = []
    subjects_dict = (syllabus.get(f"ધોરણ {grade}") or {}).get("subjects", {})
    for _label, info in subjects_dict.items():
        if info.get("code") == subject:
            for p in info.get("local_pdfs") or []:
                path = p.replace("\\", "/")
                if os.path.exists(path) and path not in matched:
                    matched.append(path)
            break
    return grade, subject, matched[:2]

@st.cache_data(show_spinner=False)
def render_pdf_pages_as_jpeg_bytes(abspath, mtime, page_indices):
    images = []
    try:
        import fitz
        with fitz.open(abspath) as doc:
            for idx in page_indices:
                if 0 <= idx < len(doc):
                    images.append((idx + 1, doc[idx].get_pixmap(dpi=130, alpha=False).tobytes("jpeg", jpg_quality=82)))
    except Exception:
        pass
    return images

def build_vision_pdf_parts(pdf_path, query_text, history_text):
    try:
        abspath = os.path.abspath(pdf_path)
        mtime = os.path.getmtime(abspath)
        import fitz
        with fitz.open(abspath) as doc:
            total_pages = len(doc)
    except Exception:
        return []
    rendered = render_pdf_pages_as_jpeg_bytes(abspath, mtime, tuple(range(min(22, total_pages))))
    return [types.Part.from_bytes(data=jpg_bytes, mime_type="image/jpeg") for _pno, jpg_bytes in rendered]

def render_message_with_visuals(content, image_bytes=None, msg_idx=0, math_svg=None, fallback_map_html=None, fallback_map_h=450):
    village_img_bytes = None
    if "```village_map_json" in content:
        m_v = re.search(r"```village_map_json\s*([\s\S]*?)```", content)
        if m_v:
            try:
                village_img_bytes = render_village_census_map_matplotlib(json.loads(m_v.group(1).strip()))
            except Exception:
                village_img_bytes = render_village_census_map_matplotlib({})
        content = re.sub(r"```village_map_json[\s\S]*?```", "", content)

    content = re.sub(r"```(?!map_json)[a-zA-Z]*\n[\s\S]*?```", "", content)
    final_img = village_img_bytes or image_bytes
    if final_img:
        cap = "🏘️ Matplotlib BLO / વસ્તી ગણતરી ગ્રામ્ય નકશો" if village_img_bytes else "🗺️ Nano Banana AI પાઠ્યપુસ્તક નકશો / આકૃતિ"
        st.image(final_img, caption=cap, use_container_width=True)
        st.download_button("⬇️ નકશો / આકૃતિ ડાઉનલોડ કરો (PNG)", data=final_img, file_name=f"palaj_map_{msg_idx}.png", mime="image/png", key=f"dl_img_{msg_idx}")

    if math_svg and not final_img:
        components.html(f'<div style="background:#FFFFFF; border-radius:12px; padding:8px; text-align:center; border:2px solid #93C5FD;">{math_svg}</div>', height=345, scrolling=False)

    rendered_map = False
    if "```map_json" in content:
        for seg in re.split(r"(```map_json[\s\S]*?```)", content):
            if seg.startswith("```map_json"):
                if not final_img:
                    try:
                        spec = json.loads(re.sub(r"^```map_json\s*|\s*```$", "", seg).strip())
                        if str(spec.get("region", "")).lower() == "gujarat" or ("ગુજરાત" in str(spec.get("title", "")) and "ભારત" not in str(spec.get("title", ""))):
                            components.html(build_gujarat_map_html(spec), height=420, scrolling=False)
                        else:
                            components.html(build_india_map_html(spec), height=475, scrolling=False)
                        rendered_map = True
                    except Exception:
                        pass
            elif seg.strip():
                st.markdown(seg)
        if not rendered_map and not final_img and fallback_map_html:
            components.html(fallback_map_html, height=fallback_map_h, scrolling=False)
        return

    if not final_img and not rendered_map and fallback_map_html:
        components.html(fallback_map_html, height=fallback_map_h, scrolling=False)

    clean = re.sub(r"```(?:svg|xml|html)?\s*(<svg[\s\S]*?</svg>)\s*```", r"\1", content, flags=re.IGNORECASE)
    if "<svg" in clean.lower() and "</svg>" in clean.lower():
        for part in re.split(r"(<svg[\s\S]*?</svg>)", clean, flags=re.IGNORECASE):
            if part.strip().lower().startswith("<svg"):
                if not final_img and not math_svg:
                    components.html(f'<div style="background:#FFFFFF; border-radius:12px; padding:8px; text-align:center; border:2px solid #93C5FD;">{part}</div>', height=355, scrolling=False)
            elif part.strip():
                st.markdown(part)
    else:
        st.markdown(clean)

syllabus_data = load_syllabus()

st.markdown("""
<style>
.block-container { max-width: 820px !important; padding-top: 2rem !important; padding-bottom: 6rem !important; }
.slim-header { background: linear-gradient(90deg, #1E3A8A, #2563EB, #0284C7); color: #FFF; padding: 10px 18px; border-radius: 50px; text-align: center; font-weight: 700; margin-bottom: 12px; }
.book-badge { display: inline-block; background: #DBEAFE; color: #1E3A8A; border: 1px solid #93C5FD; padding: 4px 12px; border-radius: 999px; font-size: 0.85rem; font-weight: 600; margin-bottom: 8px; }
</style>
""", unsafe_allow_html=True)

defaults = {
    "messages": [], "mcq_questions": None, "mcq_user_answers": {}, "mcq_checked": False,
    "draft_text": "", "mic_open": False, "audio_counter": 0, "input_version": 0, "voice_error": "",
    "ui_lang": "ગુજરાતી", "visual_mode": "Smart Auto (Nano Banana + Matplotlib + Vector)"
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

with st.sidebar:
    st.markdown("### 🎓 સ્માર્ટ AI શિક્ષક")
    raw_keys = (st.secrets.get("GEMINI_API_KEYS") or os.environ.get("GEMINI_API_KEYS") or
                st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY") or "")
    api_keys = [k.strip().strip("\"'") for k in str(raw_keys).split(",") if k.strip()]
    model_choice = st.selectbox("🤖 AI મોડેલ:", ACTIVE_MODELS)
    st.session_state.visual_mode = st.selectbox("🗺️ નકશા / આકૃતિ મોડ:", ["Smart Auto (Nano Banana + Matplotlib + Vector)", "Only Interactive Vector / Matplotlib (Fastest)"])

    quick_action = None
    c1, c2 = st.columns(2)
    if c1.button("📖 સારાંશ"): quick_action = "summary"
    if c1.button("📝 MCQ ટેસ્ટ"): quick_action = "mcq"
    if c2.button("📝 સ્વાધ્યાય"): quick_action = "exercise"
    if c2.button("💡 ઉદાહરણ"): quick_action = "easy_example"

    st.divider()
    if st.button("🗑️ નવી ચેટ", use_container_width=True):
        st.session_state.update({"messages": [], "mcq_questions": None, "mcq_user_answers": {}, "mcq_checked": False, "draft_text": "", "voice_error": "", "input_version": st.session_state.input_version + 1})
        st.rerun()

    if st.session_state.messages:
        st.download_button("⬇️ PDF નોટ્સ ડાઉનલોડ", data=build_pdf_bytes(st.session_state.messages), file_name="notes.pdf", mime="application/pdf", use_container_width=True)

st.markdown('<div class="slim-header">📚 Standard 3 to 8 Smart AI Palaj Teacher</div>', unsafe_allow_html=True)

if quick_action:
    prompts = {
        "summary": "છેલ્લી ચર્ચા મુજબના પાઠનો સરળ ગુજરાતીમાં મુદ્દાસર સારાંશ આપો.",
        "exercise": "છેલ્લી ચર્ચા મુજબના પાઠના સ્વાધ્યાયના પ્રશ્નો અને જવાબો આપો.",
        "mcq": "છેલ્લી ચર્ચા મુજબના પાઠ આધારિત ૫ MCQ બનાવો. ફોર્મેટ:\nપ્રશ્ન 1: પ્રશ્ન?\nA. ...\nB. ...\nC. ...\nD. ...\nસાચો જવાબ: B\nસમજૂતી: ...",
        "easy_example": "છેલ્લી ચર્ચા મુજબના વિષયનું સરળ ઉદાહરણો દ્વારા સમજાવો."
    }
    if quick_action == "mcq":
        st.session_state.update({"mcq_questions": None, "mcq_user_answers": {}, "mcq_checked": False})
    st.session_state.messages.append({"role": "user", "content": prompts[quick_action]})

for idx_m, m in enumerate(st.session_state.messages):
    with st.chat_message(m["role"]):
        render_message_with_visuals(
            m["content"], m.get("image_bytes"), msg_idx=idx_m,
            math_svg=m.get("math_svg"), fallback_map_html=m.get("fallback_map_html"),
            fallback_map_h=m.get("fallback_map_h", 450)
        )

if st.session_state.mcq_questions:
    st.divider()
    st.markdown("### 📝 MCQ ટેસ્ટ - ૫ પ્રશ્નો")
    for i, q in enumerate(st.session_state.mcq_questions):
        st.markdown(f"**પ્રશ્ન {i+1}:** {q['question']}")
        keys = list(q["options"].keys())
        labels = [f"{k}. {q['options'][k]}" for k in keys]
        cur = st.session_state.mcq_user_answers.get(i)
        choice = st.radio("વિકલ્પ પસંદ કરો:", labels, index=(keys.index(cur) if cur in keys else None), key=f"mcq_{i}")
        st.session_state.mcq_user_answers[i] = choice[0] if choice else None
    if st.button("🏆 સ્કોર તપાસો"):
        st.session_state.mcq_checked = True
    if st.session_state.mcq_checked:
        score = sum(1 for i, q in enumerate(st.session_state.mcq_questions) if st.session_state.mcq_user_answers.get(i) == q["answer"])
        st.success(f"🎯 તમારો સ્કોર: **{score} / {len(st.session_state.mcq_questions)}**")

if st.session_state.mic_open:
    with st.container(border=True):
        audio_val = st.audio_input("રેકોર્ડ", key=f"mob_rec_{st.session_state.audio_counter}")
        if audio_val is not None:
            spoken, err = transcribe_gujarati(audio_val, api_keys, preferred_model=model_choice, lang_name=st.session_state.ui_lang)
            st.session_state.audio_counter += 1
            st.session_state.mic_open = False
            if spoken:
                st.session_state.draft_text = f"{st.session_state.draft_text} {spoken}".strip()
                st.session_state.input_version += 1
            st.rerun()

with getattr(st, "bottom", st.container()):
    col_plus, col_in, col_mic, col_send = st.columns([1, 10, 1, 1], vertical_alignment="center")
    with col_plus:
        with st.popover("➕"):
            st.session_state.ui_lang = st.radio("🌐 ભાષા:", ["ગુજરાતી", "English", "हिन्दी"], horizontal=True)
            st.file_uploader("📁 ફાઈલ / ફોટો", key="bottom_uploader")
    with col_in:
        user_text = st.text_input("પ્રશ્ન...", value=st.session_state.draft_text, key=f"chat_box_{st.session_state.input_version}", placeholder="પ્રશ્ન, આકૃતિ, નકશો કે BLO ગામ નકશો પૂછો...", label_visibility="collapsed")
        st.session_state.draft_text = user_text
    with col_mic:
        if st.button("🎤", key="real_mic_btn"):
            st.session_state.mic_open = not st.session_state.mic_open
            st.rerun()
    with col_send:
        send_clicked = st.button("➤", type="primary", key="real_send_btn")

if send_clicked and user_text.strip():
    st.session_state.messages.append({"role": "user", "content": user_text.strip()})
    st.session_state.draft_text = ""
    st.session_state.input_version += 1
    st.rerun()

if st.session_state.messages and st.session_state.messages[-1]["role"] == "user":
    clean_q = st.session_state.messages[-1]["content"].strip()
    reply_lang = st.session_state.ui_lang
    with st.chat_message("assistant"):
        if not HAS_GENAI or not api_keys:
            st.error("⚠️ Secrets માં GEMINI_API_KEY દાખલ કરો.")
        else:
            past_user_msgs = [m["content"] for m in st.session_state.messages[:-1] if m["role"] == "user"]
            grade, subject, local_pdf_paths = resolve_grade_subject_and_pdfs(clean_q, past_user_msgs, syllabus_data)
            is_village_q = wants_village_census_map(clean_q)
            sub_label = _SUBJECT_LABELS.get(subject, subject or "")

            if is_village_q:
                st.markdown('<div class="book-badge">🏘️ ગ્રામ્ય વસ્તી ગણતરી / મતદાર યાદી સુધારણા (BLO Map)</div>', unsafe_allow_html=True)
            elif grade and sub_label and local_pdf_paths:
                st.markdown(f'<div class="book-badge">📖 ધોરણ {grade} | {sub_label}</div>', unsafe_allow_html=True)

            recent_hist = "\n".join(f"{'વિદ્યાર્થી' if m['role']=='user' else 'શિક્ષક'}: {m['content']}" for m in st.session_state.messages[:-1][-4:])
            book_page_parts = []
            for pdf_path in local_pdf_paths:
                book_page_parts.extend(build_vision_pdf_parts(pdf_path, clean_q, recent_hist))

            generated_img_bytes = None
            math_svg_code = build_math_fraction_svg(clean_q) if wants_math_geometry_visual(clean_q) else None
            is_map_q = wants_map(clean_q) and not is_village_q
            is_diag_q = wants_diagram(clean_q) and not is_map_q and not is_village_q

            fb_map_html, fb_map_h = (auto_build_map_from_query(clean_q) if is_map_q else (None, 450))

            if (is_map_q or is_diag_q) and st.session_state.visual_mode != "Only Interactive Vector / Matplotlib (Fastest)":
                with st.spinner("🎨 Nano Banana AI દ્વારા પાઠ્યપુસ્તક નકશો / આકૃતિ તૈયાર થઈ રહી છે..."):
                    generated_img_bytes, _ = generate_nano_banana_visual(clean_q, api_keys, visual_type=("map" if is_map_q else "diagram"), reply_lang=reply_lang)

            visual_instruction = ""
            if is_village_q:
                visual_instruction = (
                    "\nતમારા જવાબમાં સૌથી પહેલા આ ```village_map_json બ્લોક ફરજિયાત આપો:\n"
                    "```village_map_json\n"
                    '{"title": "ગામનો મતદાર યાદી સુધારણા / વસ્તી ગણતરી નજરી નકશો", "subtitle": "મહોલ્લા, ઘર નંબર, બજાર અને જાહેર સ્થળો", "has_river": true, "river_name": "ગામની નદી", "has_pond": true, "pond_name": "ગામ તળાવ", "main_road_name": "મુખ્ય ગામ રસ્તો", "mohallas": [{"name": "પટેલ વાસ", "houses": ["ઘર-1", "ઘર-2", "ઘર-3", "ઘર-4", "ઘર-5", "ઘર-6"]}, {"name": "ઠાકોર વાસ", "houses": ["ઘર-7", "ઘર-8", "ઘર-9", "ઘર-10", "ઘર-11", "ઘર-12"]}, {"name": "વણકર વાસ", "houses": ["ઘર-13", "ઘર-14", "ઘર-15", "ઘર-16", "ઘર-17", "ઘર-18"]}, {"name": "નાનું બજાર અને દુકાનો", "houses": ["કરિયાણા દુકાન", "દૂધ ડેરી", "મેડિકલ", "ઘર-19", "ઘર-20"]}], "landmarks": [{"name": "ગ્રામ પંચાયત", "type": "govt"}, {"name": "પ્રાથમિક શાળા", "type": "school"}, {"name": "દવાખાનું / હોસ્પિટલ", "type": "hospital"}, {"name": "બેંક / પોસ્ટ ઓફિસ", "type": "bank"}, {"name": "મંદિર", "type": "temple"}, {"name": "બગીચો", "type": "garden"}], "total_houses_note": "કુલ ૪ વિભાગ અને ૨૦ ઘર"}\n'
                    "```\nપ્રશ્નમાં આપેલા ગામ, મહોલ્લા, ઘર અને સ્થળો મુજબ JSON અપડેટ કરી નીચે મુદ્દાસર સમજૂતી આપો."
                )
            elif is_map_q:
                visual_instruction = (
                    "\nતમારા જવાબમાં સૌથી પહેલા આ ```map_json બ્લોક ફરજિયાત આપો (ગુજરાત માટે region: gujarat, ભારત/મગધ/કિલ્લા માટે region: india):\n"
                    "```map_json\n"
                    '{"region": "gujarat", "title": "નકશા પૂર્તિ", "items": [{"label": "વિભાગ", "symbol": "★", "color": "#DC2626", "states": ["કચ્છ", "અમદાવાદ"]}]}\n'
                    "```\nઅને નીચે મુદ્દાસર સમજૂતી આપો."
                )
            elif is_diag_q and not math_svg_code:
                visual_instruction = (
                    '\nતમારા જવાબમાં સૌથી પહેલા એકદમ વિગતવાર, રંગીન અને સ્વચ્છ '
                    '`<svg width="520" height="350" viewBox="0 0 520 350" xmlns="[http://www.w3.org/2000/svg](http://www.w3.org/2000/svg)"><rect width="520" height="350" fill="#FFFFFF"/>...</svg>` '
                    'આકૃતિ ગુજરાતી નામનિર્દેશન અને તીર રેખાઓ સાથે ફરજિયાત મૂકો અને નીચે મુદ્દાસર સમજૂતી આપો.'
                )

            sys_prompt = f"તમે ધોરણ 3 થી 8 ના વિદ્યાર્થીઓ અને શિક્ષકો માટેના નિષ્ણાત AI સહાયક છો. જવાબ {reply_lang} ભાષામાં, શુદ્ધ જોડણીમાં અને પ્રેમાળ આવકાર સાથે આપો.{visual_instruction}"
            prompt_text = f"{sys_prompt}\n\n{recent_hist}\nપ્રશ્ન: {clean_q}"

            placeholder = st.empty()
            placeholder.markdown("⚡ *જવાબ તૈયાર થઈ રહ્યો છે...*")
            answer_text, success, last_err = "", False, None

            for key in api_keys:
                client = genai.Client(api_key=key)
                for mod in get_available_models_for_client(client, model_choice):
                    try:
                        resp = client.models.generate_content(model=mod, contents=book_page_parts + [prompt_text])
                        if resp and resp.text and resp.text.strip():
                            placeholder.empty()
                            render_message_with_visuals(
                                resp.text, generated_img_bytes, msg_idx=len(st.session_state.messages),
                                math_svg=math_svg_code, fallback_map_html=fb_map_html, fallback_map_h=fb_map_h
                            )
                            answer_text, success = resp.text, True
                            break
                    except Exception as e:
                        last_err = e
                        if any(x in str(e) for x in ("429", "RESOURCE_EXHAUSTED", "API_KEY_INVALID")):
                            break
                if success:
                    break

            if success:
                st.session_state.messages.append({
                    "role": "assistant", "content": answer_text,
                    "image_bytes": generated_img_bytes, "math_svg": math_svg_code,
                    "fallback_map_html": fb_map_html, "fallback_map_h": fb_map_h
                })
                if quick_action == "mcq" and st.session_state.mcq_questions is None:
                    if parsed := parse_mcq(answer_text):
                        st.session_state.mcq_questions = parsed
                    st.rerun()
            else:
                placeholder.empty()
                st.error(f"❌ {format_friendly_error(last_err)}")