import streamlit as st
import streamlit.components.v1 as components
import json, os, io, re, math
from PIL import Image
from fpdf import FPDF

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
        clean_txt = re.sub(r"```map_json[\s\S]*?```", "[નકશો સંલગ્ન છે]", clean_txt)
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

# --- NANO BANANA (GEMINI IMAGE GEN) TEXTBOOK MAP & DIAGRAM GENERATOR ---
def generate_nano_banana_visual(query_text, api_keys, visual_type="map", reply_lang="ગુજરાતી"):
    """Generates GCERT textbook-style full-color maps, historical forts/kingdoms, science & math diagrams."""
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
            "Style: Authentic Indian school textbook cartography with crisp black borders, distinct pastel colors (yellow, light green, pink, purple, orange, light blue) for different regions/districts/historical empires, light blue ocean water, white margin frame, bold header title at top. "
            "High resolution, accurate geography, zero garbled or overlapping text."
        )
    elif visual_type == "math":
        prompt = (
            f"Create a clean, colorful GCERT school textbook math geometry/fraction diagram illustration for: '{query_text}'. "
            f"Print all fraction numbers, division lines, shaded sectors, and labels clearly in {lang_script}. "
            "Style: Pure white background, crisp black geometric outlines, bright distinct pastel colors for shaded parts, clear labels and arrows, school textbook quality."
        )
    else:
        prompt = (
            f"Create an authentic, full-color GCERT school textbook labeled scientific/educational diagram for: '{query_text}'. "
            f"Print the top title and all part pointer labels clearly in {lang_script}. "
            "Style: Pure white background, crisp dark outlines, vibrant educational textbook colors, neat straight pointer lines to each part, uncluttered layout, zero overlapping text."
        )

    last_img_err = ""
    for key in api_keys:
        client = genai.Client(api_key=key)
        nb_models, imagen_models = get_available_image_models(client)

        # 1. Try Nano Banana native image models
        for nb_model in nb_models:
            try:
                res = client.models.generate_content(
                    model=nb_model,
                    contents=[prompt],
                    config=types.GenerateContentConfig(response_modalities=["IMAGE"])
                )
                for cand in getattr(res, "candidates", []) or []:
                    for part in getattr(cand.content, "parts", []) or []:
                        if getattr(part, "inline_data", None) and getattr(part, "inline_data", None).data:
                            return part.inline_data.data, ""
            except Exception as e:
                last_img_err = str(e)
                try:
                    res = client.models.generate_content(model=nb_model, contents=[prompt])
                    for cand in getattr(res, "candidates", []) or []:
                        for part in getattr(cand.content, "parts", []) or []:
                            if getattr(part, "inline_data", None) and getattr(part, "inline_data", None).data:
                                return part.inline_data.data, ""
                except Exception as e2:
                    last_img_err = str(e2)

        # 2. Fallback to Imagen models
        for img_mod in imagen_models:
            try:
                res = client.models.generate_images(
                    model=img_mod,
                    prompt=prompt,
                    config=types.GenerateImagesConfig(
                        number_of_images=1,
                        output_mime_type="image/jpeg",
                        aspect_ratio="4:3"
                    )
                )
                if res and getattr(res, "generated_images", None):
                    return res.generated_images[0].image.image_bytes, ""
            except Exception as e3:
                last_img_err = str(e3)

    return None, last_img_err

# --- SMART MATH FRACTION / CIRCLE DIAGRAM BUILDER ---
def build_math_fraction_svg(query_text):
    """Generates an exact geometric SVG when student asks to divide a circle into parts and highlight a fraction."""
    q = (query_text or "").translate(str.maketrans("૦૧૨૩૪૫૬૭૮૯", "0123456789")).lower()
    word_to_num = {
        "બે": 2, "2": 2, "two": 2,
        "ત્રણ": 3, "3": 3, "three": 3,
        "ચાર": 4, "4": 4, "four": 4,
        "પાંચ": 5, "5": 5, "five": 5,
        "છ": 6, "6": 6, "six": 6,
        "સાત": 7, "7": 7, "seven": 7,
        "આઠ": 8, "8": 8, "eight": 8,
    }
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

    # Draw left circle: Divided into `total_parts` equal parts
    left_slices = []
    for i in range(total_parts):
        a1 = -90 + (360.0 / total_parts) * i
        a2 = -90 + (360.0 / total_parts) * (i + 1)
        x1 = cx + r * math.cos(math.radians(a1))
        y1 = cy + r * math.sin(math.radians(a1))
        x2 = cx + r * math.cos(math.radians(a2))
        y2 = cy + r * math.sin(math.radians(a2))
        large_arc = 1 if (a2 - a1) > 180 else 0
        fill_c = palette[i % len(palette)]
        left_slices.append(
            f'<path d="M {cx},{cy} L {x1:.1f},{y1:.1f} A {r},{r} 0 {large_arc},1 {x2:.1f},{y2:.1f} Z" '
            f'fill="{fill_c}" stroke="#1E293B" stroke-width="2.2"/>'
        )
        mid_a = math.radians((a1 + a2) / 2)
        lx = cx + (r * 0.58) * math.cos(mid_a)
        ly = cy + (r * 0.58) * math.sin(mid_a)
        left_slices.append(
            f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="middle" dominant-baseline="middle" '
            f'font-size="14" font-weight="bold" fill="#0F172A">ભાગ {i+1}</text>'
        )

    # Draw right circle: Highlighting `num/den` fraction
    cx2, cy2 = 430, 165
    right_slices = []
    disp_den = max(den, 1)
    disp_num = min(num, disp_den)
    for i in range(disp_den):
        a1 = -90 + (360.0 / disp_den) * i
        a2 = -90 + (360.0 / disp_den) * (i + 1)
        x1 = cx2 + r * math.cos(math.radians(a1))
        y1 = cy2 + r * math.sin(math.radians(a1))
        x2 = cx2 + r * math.cos(math.radians(a2))
        y2 = cy2 + r * math.sin(math.radians(a2))
        large_arc = 1 if (a2 - a1) > 180 else 0
        fill_c = "#2563EB" if i < disp_num else "#F1F5F9"
        txt_c = "#FFFFFF" if i < disp_num else "#334155"
        if disp_den == 1:
            right_slices.append(f'<circle cx="{cx2}" cy="{cy2}" r="{r}" fill="{fill_c}" stroke="#1E293B" stroke-width="2.2"/>')
        else:
            right_slices.append(
                f'<path d="M {cx2},{cy2} L {x1:.1f},{y1:.1f} A {r},{r} 0 {large_arc},1 {x2:.1f},{y2:.1f} Z" '
                f'fill="{fill_c}" stroke="#1E293B" stroke-width="2.2"/>'
            )
        mid_a = math.radians((a1 + a2) / 2)
        lx = cx2 + (r * 0.55) * math.cos(mid_a)
        ly = cy2 + (r * 0.55) * math.sin(mid_a)
        right_slices.append(
            f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="middle" dominant-baseline="middle" '
            f'font-size="14" font-weight="bold" fill="{txt_c}">1/{disp_den}</text>'
        )

    return f"""
    <svg width="100%" viewBox="0 0 600 330" xmlns="http://www.w3.org/2000/svg" style="max-height:330px; display:block; margin:auto;">
      <rect width="600" height="330" rx="12" fill="#FFFFFF"/>
      <text x="300" y="28" text-anchor="middle" font-size="17" font-weight="bold" fill="#1E3A8A">📐 ગણિત આકૃતિ: વર્તુળના {total_parts} ભાગ અને {num}/{den} અપૂર્ણાંક</text>
      {''.join(left_slices)}
      <text x="{cx}" y="295" text-anchor="middle" font-size="14" font-weight="bold" fill="#0F172A">૧. વર્તુળના {total_parts} સમાન ભાગ</text>
      {''.join(right_slices)}
      <text x="{cx2}" y="295" text-anchor="middle" font-size="14" font-weight="bold" fill="#1D4ED8">૨. રંગીન ભાગ = {num}/{den} (અડધો/અપૂર્ણાંક)</text>
    </svg>
    """

# --- ACCURATE INDIA MAP COORDINATES (STATES + HISTORICAL KINGDOMS & FORTS) ---
_INDIA_STATE_COORDS = {
    "jammu": (165, 52, "જમ્મુ-કાશ્મીર"),
    "ladakh": (195, 42, "લદ્દાખ"),
    "himachal": (182, 85, "હિમાચલ પ્રદેશ"),
    "punjab": (152, 102, "પંજાબ"),
    "haryana": (162, 122, "હરિયાણા"),
    "uttarakhand": (205, 112, "ઉત્તરાખંડ"),
    "rajasthan": (122, 165, "રાજસ્થાન"),
    "uttar pradesh": (225, 162, "ઉત્તર પ્રદેશ"),
    "bihar": (292, 178, "બિહાર"),
    "gujarat": (88, 222, "ગુજરાત"),
    "madhya pradesh": (185, 218, "મધ્ય પ્રદેશ"),
    "chhattisgarh": (245, 238, "છત્તીસગઢ"),
    "jharkhand": (285, 208, "ઝારખંડ"),
    "west bengal": (322, 222, "પશ્ચિમ બંગાળ"),
    "odisha": (282, 265, "ઓડિશા"),
    "maharashtra": (148, 275, "મહારાષ્ટ્ર"),
    "telangana": (202, 298, "તેલંગાણા"),
    "andhra pradesh": (212, 342, "આંધ્ર પ્રદેશ"),
    "karnataka": (152, 348, "કર્ણાટક"),
    "goa": (125, 332, "ગોવા"),
    "kerala": (158, 412, "કેરળ"),
    "tamil nadu": (192, 405, "તમિલનાડુ"),
    "assam": (382, 168, "આસામ"),
    "arunachal": (405, 142, "અરુણાચલ પ્રદેશ"),
    "meghalaya": (368, 185, "મેઘાલય"),
    "tripura": (375, 212, "ત્રિપુરા"),
    "mizoram": (388, 215, "મિઝોરમ"),
    "manipur": (398, 195, "મણિપુર"),
    "nagaland": (405, 175, "નાગાલેન્ડ"),
    "sikkim": (332, 152, "સિક્કિમ"),
    # Historical Kingdoms, Ancient Capitals & Forts
    "magadha": (296, 184, "મગધ (પાટલિપુત્ર)"),
    "vaishali": (286, 168, "વૈશાલી"),
    "avanti": (168, 215, "અવંતિ (ઉજ્જૈન)"),
    "kashi": (254, 176, "કાશી (વારાણસી)"),
    "kosala": (235, 155, "કોસલ (અયોધ્યા)"),
    "kalinga": (284, 268, "કલિંગ"),
    "hastinapur": (182, 128, "હસ્તિનાપુર / દિલ્હી"),
    "lothal": (86, 228, "લોથલ"),
    "dholavira": (72, 206, "ધોળાવીરા"),
    "chittorgarh": (132, 192, "ચિત્તોડગઢ કિલ્લો"),
    "raigad": (132, 286, "રાયગઢ કિલ્લો"),
    "golconda": (202, 304, "ગોલકોંડા કિલ્લો"),
    "gwalior": (194, 185, "ગ્વાલિયર કિલ્લો"),
}

_STATE_ALIASES = {
    "પંજાબ": "punjab", "punjab": "punjab",
    "ઉત્તર પ્રદેશ": "uttar pradesh", "uttar pradesh": "uttar pradesh", "up": "uttar pradesh",
    "પશ્ચિમ બંગાળ": "west bengal", "west bengal": "west bengal", "બંગાળ": "west bengal",
    "રાજસ્થાન": "rajasthan", "rajasthan": "rajasthan",
    "ગુજરાત": "gujarat", "gujarat": "gujarat",
    "મહારાષ્ટ્ર": "maharashtra", "maharashtra": "maharashtra",
    "મધ્ય પ્રદેશ": "madhya pradesh", "madhya pradesh": "madhya pradesh", "mp": "madhya pradesh",
    "બિહાર": "bihar", "bihar": "bihar",
    "ઓડિશા": "odisha", "odisha": "odisha", "orissa": "odisha",
    "કર્ણાટક": "karnataka", "karnataka": "karnataka",
    "તમિલનાડુ": "tamil nadu", "tamil nadu": "tamil nadu",
    "આંધ્ર પ્રદેશ": "andhra pradesh", "andhra pradesh": "andhra pradesh",
    "તેલંગાણા": "telangana", "telangana": "telangana",
    "કેરળ": "kerala", "kerala": "kerala",
    "આસામ": "assam", "assam": "assam",
    "ઝારખંડ": "jharkhand", "jharkhand": "jharkhand",
    "છત્તીસગઢ": "chhattisgarh", "chhattisgarh": "chhattisgarh",
    "હરિયાણા": "haryana", "haryana": "haryana",
    "હિમાચલ પ્રદેશ": "himachal", "himachal": "himachal",
    "ઉત્તરાખંડ": "uttarakhand", "uttarakhand": "uttarakhand",
    "જમ્મુ": "jammu", "jammu": "jammu", "kashmir": "jammu",
    "ગોવા": "goa", "goa": "goa",
    "સિક્કિમ": "sikkim", "sikkim": "sikkim",
    # Historical aliases
    "મગધ": "magadha", "મગધ દેશ": "magadha", "પાટલિપુત્ર": "magadha", "રાજગૃહ": "magadha", "magadha": "magadha",
    "વૈશાલી": "vaishali", "vaishali": "vaishali",
    "અવંતિ": "avanti", "ઉજ્જૈન": "avanti", "avanti": "avanti",
    "કાશી": "kashi", "વારાણસી": "kashi", "kashi": "kashi",
    "કોસલ": "kosala", "અયોધ્યા": "kosala", "kosala": "kosala",
    "કલિંગ": "kalinga", "kalinga": "kalinga",
    "હસ્તિનાપુર": "hastinapur", "દિલ્હી": "hastinapur", "લાલ કિલ્લો": "hastinapur", "ઇન્દ્રપ્રસ્થ": "hastinapur",
    "લોથલ": "lothal", "lothal": "lothal",
    "ધોળાવીરા": "dholavira", "dholavira": "dholavira",
    "ચિત્તોડગઢ": "chittorgarh", "કુંભલગઢ": "chittorgarh", "મેવાડ": "chittorgarh",
    "રાયગઢ": "raigad", "શિવાજી": "raigad", "પ્રતાપગઢ": "raigad",
    "ગોલકોંડા": "golconda", "ગ્વાલિયર": "gwalior",
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

    state_offset_count = {}
    markers_svg = []
    legend_svg = []

    for idx, item in enumerate(items[:8]):
        label = str(item.get("label", ""))
        symbol = str(item.get("symbol", "●"))
        color = str(item.get("color", "#DC2626"))
        states = item.get("states", [])

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

            dx = (cnt % 2) * 20 - (10 if cnt > 0 else 0)
            dy = (cnt // 2) * 18
            px, py = bx + dx, by + dy

            markers_svg.append(
                f'<circle cx="{px}" cy="{py}" r="11" fill="#FFFFFF" stroke="{color}" stroke-width="2"/>'
                f'<text x="{px}" y="{py+4}" text-anchor="middle" font-size="13" font-weight="bold" fill="{color}">{symbol}</text>'
            )
            if cnt == 0:
                markers_svg.append(
                    f'<text x="{bx}" y="{by+22}" text-anchor="middle" font-size="10.5" font-weight="bold" fill="#1E293B">{guj_st}</text>'
                )

    legend_height = max(160, 65 + len(items[:8]) * 40)
    return f"""
    <div style="background:#FFFFFF; border:2px solid #93C5FD; border-radius:14px; padding:10px; font-family:'Noto Sans Gujarati', sans-serif;">
      <svg width="100%" viewBox="0 0 680 460" xmlns="http://www.w3.org/2000/svg" style="max-height:450px; display:block; margin:auto;">
        <rect x="0" y="0" width="680" height="460" rx="12" fill="#F8FAFC"/>
        <text x="340" y="26" text-anchor="middle" font-size="17" font-weight="bold" fill="#1E3A8A">{title}</text>
        <g transform="translate(55, 65)">
          <circle cx="0" cy="0" r="18" fill="#EFF6FF" stroke="#3B82F6" stroke-width="1.5"/>
          <line x1="0" y1="-13" x2="0" y2="13" stroke="#1E3A8A" stroke-width="1.5"/>
          <line x1="-13" y1="0" x2="13" y2="0" stroke="#1E3A8A" stroke-width="1.5"/>
          <text x="0" y="-21" text-anchor="middle" font-size="10" font-weight="bold" fill="#1E3A8A">ઉત્તર</text>
        </g>
        <path d="{india_outline}" fill="#FEF9C3" stroke="#92400E" stroke-width="2.2" stroke-linejoin="round"/>
        {''.join(markers_svg)}
        <rect x="438" y="34" width="232" height="{legend_height}" rx="10" fill="#FFFFFF" stroke="#CBD5E1" stroke-width="1.5"/>
        <text x="554" y="51" text-anchor="middle" font-size="13.5" font-weight="bold" fill="#1E3A8A">📌 સંજ્ઞા સૂચિ (Legend)</text>
        <line x1="448" y1="57" x2="660" y2="57" stroke="#E2E8F0" stroke-width="1"/>
        {''.join(legend_svg)}
      </svg>
    </div>
    """

# --- ACCURATE GUJARAT MAP COORDINATES (33 DISTRICTS, ZONES, RIVERS, MOUNTAINS & FORTS) ---
_GUJARAT_DISTRICT_COORDS = {
    "kutch": (98, 138, "કચ્છ (ભુજ)"),
    "banaskantha": (232, 86, "બનાસકાંઠા"),
    "patan": (212, 118, "પાટણ"),
    "mehsana": (245, 128, "મહેસાણા"),
    "sabarkantha": (282, 102, "સાબરકાંઠા"),
    "aravalli": (305, 125, "અરવલ્લી"),
    "gandhinagar": (262, 148, "ગાંધીનગર"),
    "ahmedabad": (242, 172, "અમદાવાદ"),
    "surendranagar": (195, 182, "સુરેન્દ્રનગર"),
    "morbi": (155, 178, "મોરબી"),
    "jamnagar": (108, 208, "જામનગર"),
    "devbhumi dwarka": (74, 218, "દ્વારકા"),
    "porbandar": (92, 248, "પોરબંદર"),
    "rajkot": (152, 218, "રાજકોટ"),
    "botad": (198, 215, "બોટાદ"),
    "bhavnagar": (212, 248, "ભાવનગર"),
    "amreli": (172, 258, "અમરેલી"),
    "junagadh": (128, 265, "જૂનાગઢ"),
    "gir somnath": (142, 288, "ગીર સોમનાથ"),
    "kheda": (278, 175, "ખેડા"),
    "anand": (266, 198, "આણંદ"),
    "mahisagar": (318, 152, "મહીસાગર"),
    "panchmahal": (322, 178, "પંચમહાલ"),
    "dahod": (354, 178, "દાહોદ"),
    "vadodara": (302, 205, "વડોદરા"),
    "chhota udaipur": (342, 212, "છોટા ઉદેપુર"),
    "bharuch": (288, 238, "ભરૂચ"),
    "narmada": (324, 238, "નર્મદા"),
    "surat": (292, 268, "સુરત"),
    "tapi": (326, 268, "તાપી"),
    "navsari": (292, 295, "નવસારી"),
    "dang": (322, 298, "ડાંગ"),
    "valsad": (288, 324, "વલસાડ"),
    "north gujarat": (255, 112, "ઉત્તર ગુજરાત"),
    "central gujarat": (295, 182, "મધ્ય ગુજરાત"),
    "saurashtra": (155, 228, "સૌરાષ્ટ્ર"),
    "south gujarat": (298, 282, "દક્ષિણ ગુજરાત"),
    # Rivers, Mountains & Historical Forts
    "girnar": (128, 265, "ગિરનાર / ઉપરકોટ કિલ્લો"),
    "pavagadh": (322, 178, "પાવાગઢ / ચાંપાનેર"),
    "chotila": (175, 202, "ચોટીલા"),
    "shetrunjay": (205, 255, "શેત્રુંજય"),
    "arasur": (245, 82, "આરાસુર / ગબ્બર"),
    "kalo dungar": (95, 118, "કાળો ડુંગર"),
    "lakhpat": (62, 125, "લખપત કિલ્લો"),
    "dholavira": (125, 118, "ધોળાવીરા"),
    "lothal": (235, 192, "લોથલ"),
    "idargadh": (282, 98, "ઈડરિયો ગઢ"),
    "dabhoi": (312, 212, "ડભોઈ કિલ્લો"),
    "saputara": (322, 298, "સાપુતારા"),
    "narmada river": (295, 238, "નર્મદા નદી"),
    "tapi river": (298, 268, "તાપી નદી"),
    "sabarmati river": (252, 165, "સાબરમતી નદી"),
    "mahi river": (285, 195, "મહી નદી"),
    "banas river": (222, 95, "બનાસ નદી"),
    "bhadar river": (135, 245, "ભાદર નદી"),
}

_GUJARAT_ALIASES = {
    "કચ્છ": "kutch", "ભુજ": "kutch", "kutch": "kutch", "kachchh": "kutch",
    "બનાસકાંઠા": "banaskantha", "પાલનપુર": "banaskantha", "banaskantha": "banaskantha",
    "પાટણ": "patan", "રાણીની વાવ": "patan", "patan": "patan",
    "મહેસાણા": "mehsana", "mehsana": "mehsana", "mahesana": "mehsana",
    "સાબરકાંઠા": "sabarkantha", "હિંમતનગર": "sabarkantha", "sabarkantha": "sabarkantha",
    "અરવલ્લી": "aravalli", "મોડાસા": "aravalli", "aravalli": "aravalli",
    "ગાંધીનગર": "gandhinagar", "અડાલજ": "gandhinagar", "gandhinagar": "gandhinagar",
    "અમદાવાદ": "ahmedabad", "ભદ્રનો કિલ્લો": "ahmedabad", "ahmedabad": "ahmedabad",
    "સુરેન્દ્રનગર": "surendranagar", "surendranagar": "surendranagar",
    "મોરબી": "morbi", "morbi": "morbi",
    "જામનગર": "jamnagar", "jamnagar": "jamnagar",
    "દ્વારકા": "devbhumi dwarka", "દેવભૂમિ દ્વારકા": "devbhumi dwarka", "dwarka": "devbhumi dwarka",
    "પોરબંદર": "porbandar", "porbandar": "porbandar",
    "રાજકોટ": "rajkot", "rajkot": "rajkot",
    "બોટાદ": "botad", "botad": "botad",
    "ભાવનગર": "bhavnagar", "bhavnagar": "bhavnagar",
    "અમરેલી": "amreli", "amreli": "amreli",
    "જૂનાગઢ": "junagadh", "ઉપરકોટ": "girnar", "junagadh": "junagadh",
    "ગીર સોમનાથ": "gir somnath", "સોમનાથ": "gir somnath", "gir somnath": "gir somnath",
    "ખેડા": "kheda", "નડિયાદ": "kheda", "kheda": "kheda",
    "આણંદ": "anand", "anand": "anand",
    "મહીસાગર": "mahisagar", "લુણાવાડા": "mahisagar", "mahisagar": "mahisagar",
    "પંચમહાલ": "panchmahal", "ગોધરા": "panchmahal", "panchmahal": "panchmahal",
    "દાહોદ": "dahod", "dahod": "dahod",
    "વડોદરા": "vadodara", "vadodara": "vadodara", "baroda": "vadodara",
    "છોટા ઉદેપુર": "chhota udaipur", "chhota udaipur": "chhota udaipur",
    "ભરૂચ": "bharuch", "bharuch": "bharuch",
    "નર્મદા": "narmada river", "રાજપીપળા": "narmada", "narmada": "narmada",
    "સુરત": "surat", "સુરતનો કિલ્લો": "surat", "surat": "surat",
    "તાપી": "tapi river", "વ્યારા": "tapi", "tapi": "tapi",
    "નવસારી": "navsari", "navsari": "navsari",
    "ડાંગ": "dang", "આહવા": "dang", "dang": "dang",
    "વલસાડ": "valsad", "valsad": "valsad",
    "ઉત્તર ગુજરાત": "north gujarat", "north gujarat": "north gujarat",
    "મધ્ય ગુજરાત": "central gujarat", "central gujarat": "central gujarat",
    "સૌરાષ્ટ્ર": "saurashtra", "saurashtra": "saurashtra",
    "દક્ષિણ ગુજરાત": "south gujarat", "south gujarat": "south gujarat",
    "ગિરનાર": "girnar", "પાવાગઢ": "pavagadh", "ચાંપાનેર": "pavagadh", "ચોટીલા": "chotila",
    "શેત્રુંજય": "shetrunjay", "આરાસુર": "arasur", "ગબ્બર": "arasur",
    "કાળો ડુંગર": "kalo dungar", "સાપુતારા": "saputara",
    "લખપત": "lakhpat", "ધોળાવીરા": "dholavira", "લોથલ": "lothal",
    "ઈડર": "idargadh", "ઈડરિયો ગઢ": "idargadh", "ડભોઈ": "dabhoi",
    "સાબરમતી": "sabarmati river", "મહી": "mahi river",
    "બનાસ": "banas river", "સરસ્વતી": "banas river",
    "રૂપેણ": "mehsana", "ભાદર": "bhadar river", "લૂણી": "kutch",
}

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

    offset_count = {}
    markers_svg = []
    legend_svg = []

    for idx, item in enumerate(items[:8]):
        label = str(item.get("label", ""))
        symbol = str(item.get("symbol", "●"))
        color = str(item.get("color", "#2563EB"))
        places = item.get("states", [])

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
            px = bx + ((cnt % 2) * 14 - (7 if cnt > 0 else 0))
            py = by + ((cnt // 2) * 14)

            markers_svg.append(
                f'<circle cx="{px}" cy="{py}" r="9.5" fill="#FFFFFF" stroke="{color}" stroke-width="2"/>'
                f'<text x="{px}" y="{py+3.5}" text-anchor="middle" font-size="11.5" font-weight="bold" fill="{color}">{symbol}</text>'
            )
            if cnt == 0:
                markers_svg.append(
                    f'<text x="{bx}" y="{by+19}" text-anchor="middle" font-size="9.5" font-weight="bold" fill="#0F172A">{guj_name}</text>'
                )

    legend_height = max(175, 65 + len(items[:8]) * 42)
    return f"""
    <div style="background:#FFFFFF; border:2px solid #93C5FD; border-radius:14px; padding:10px; font-family:'Noto Sans Gujarati', sans-serif;">
      <svg width="100%" viewBox="0 0 670 395" xmlns="http://www.w3.org/2000/svg" style="max-height:410px; display:block; margin:auto;">
        <rect x="0" y="0" width="670" height="395" rx="12" fill="#F0F9FF"/>
        <text x="335" y="25" text-anchor="middle" font-size="16.5" font-weight="bold" fill="#1E3A8A">{title}</text>
        <g transform="translate(46, 56)">
          <circle cx="0" cy="0" r="15" fill="#EFF6FF" stroke="#3B82F6" stroke-width="1.5"/>
          <line x1="0" y1="-10" x2="0" y2="10" stroke="#1E3A8A" stroke-width="1.5"/>
          <line x1="-10" y1="0" x2="10" y2="0" stroke="#1E3A8A" stroke-width="1.5"/>
          <text x="0" y="-18" text-anchor="middle" font-size="9.5" font-weight="bold" fill="#1E3A8A">ઉત્તર</text>
        </g>
        <path d="{gujarat_outline}" fill="#DCFCE7" stroke="#15803D" stroke-width="2.2" stroke-linejoin="round"/>
        <text x="115" y="184" font-size="9.5" fill="#0369A1" font-style="italic">કચ્છનો અખાત</text>
        <text x="236" y="264" font-size="9.5" fill="#0369A1" font-style="italic">ખંભાતનો અખાત</text>
        {''.join(markers_svg)}
        <rect x="398" y="36" width="260" height="{legend_height}" rx="10" fill="#FFFFFF" stroke="#CBD5E1" stroke-width="1.5"/>
        <text x="528" y="53" text-anchor="middle" font-size="13" font-weight="bold" fill="#1E3A8A">📌 સંજ્ઞા સૂચિ (વિભાગ / જિલ્લા)</text>
        <line x1="408" y1="59" x2="648" y2="59" stroke="#E2E8F0" stroke-width="1"/>
        {''.join(legend_svg)}
      </svg>
    </div>
    """

# --- SMART GRADE, SUBJECT, DIAGRAM, MATH, MAP & GK DETECTION ---
_GUJ_DIGIT_MAP = str.maketrans("૦૧૨૩૪૫૬૭૮૯", "0123456789")

_SUBJECT_LABELS = {
    "gujarati": "ગુજરાતી",
    "sanskrit": "સંસ્કૃત",
    "math": "ગણિત",
    "science": "વિજ્ઞાન",
    "social_science": "સામાજિક વિજ્ઞાન",
    "environment": "પર્યાવરણ (આસપાસ)",
    "english": "અંગ્રેજી",
    "hindi": "હિન્દી",
    "vedic_math": "વૈદિક ગણિત",
    "allround": "સર્વાંગી શિક્ષણ",
}

_EXPLICIT_SUBJECTS = {
    "social_science": [
        "સામાજિક વિજ્ઞાન", "સામાજિક", "સમાજિક", "social science", "social", "samajik", "samaj",
        "ઇતિહાસ", "ભૂગોળ", "નાગરિક", "ઉદ્યોગ", "ટિસ્કો", "tisco", "જમશેદપુર", "બંધારણ", "સંસદ",
        "નકશો", "નક્શો", "નકશા", "નક્શા", "નકશાપૂર્તિ", "પાક ઉત્પાદન", "જિલ્લા", "ગુજરાત",
        "મગધ", "મૌર્ય", "કિલ્લો", "કિલ્લા", "ગઢ", "પ્રદેશ", "લોથલ", "ધોળાવીરા", "પાટલિપુત્ર"
    ],
    "vedic_math": ["વૈદિક ગણિત", "vedic math", "vedic"],
    "math": ["ગણિત", "ગણીત", "math", "maths", "ganit", "ગણિત ગમ્મત", "ગણિત મેળો", "ભૂમિતિ", "બીજગણિત", "સમીકરણ", "અપૂર્ણાંક", "વર્તુળ", "ત્રિકોણ", "ચોરસ"],
    "science": ["વિજ્ઞાન", "science", "vigyan", "vignan", "પ્રકાશસંશ્લેષણ", "કોષ", "વિદ્યુત", "ચુંબક", "બળ", "દબાણ", "અણુ", "પરમાણુ", "મીણબત્તી", "જ્યોત"],
    "environment": ["પર્યાવરણ", "આસપાસ", "environment", "paryavaran", "aaspas", "aaspaas", "evs"],
    "gujarati": ["ગુજરાતી", "gujarati", "કલશોર", "kalshor", "કેકારવ", "kekarav", "કુહૂ", "કહુ", "kuhu", "પલાશ", "પળાશ", "palash", "કાવ્ય", "વ્યાકરણ", "સમાસ", "અલંકાર", "રૂઢિપ્રયોગ"],
    "sanskrit": ["સંસ્કૃત", "sanskrit", "sanskrut", "સુભાષિતાનિ", "શ્લોક"],
    "english": ["અંગ્રેજી", "english", "grammar", "tense"],
    "hindi": ["હિન્દી", "hindi", "हिन्दी", "તિતલી", "titali"],
    "allround": ["સર્વાંગી", "sarvangi", "ગીતા", "gita"],
}

_GK_OR_CA_KEYWORDS = [
    "current affair", "current affairs", "કરંટ અફેર્સ", "કરંટ", "વર્તમાન પ્રવાહ", "વર્તમાન પ્રવાહો",
    "તાજેતરના", "તાજેતરમાં", "આજના સમાચાર", "general knowledge", "સામાન્ય જ્ઞાન", "gk", "જી.કે", "જીકે",
    "વડાપ્રધાન", "રાષ્ટ્રપતિ", "મુખ્યમંત્રી", "રાજધાની", "ઓલિમ્પિક", "વર્લ્ડ કપ", "ઈસરો", "isro", "ચંદ્રયાન"
]

_DIAGRAM_KEYWORDS = [
    "આકૃતિ", "નામનિર્દેશ", "નામ નિર્દેશ", "ચિત્ર દોરી", "આકૃતિ દોરી", "આકૃતિ દોરો",
    "diagram", "labeled diagram", "draw", "sketch", "કોષ", "વર્તુળ", "ભાગ પાડી", "અપૂર્ણાંક"
]

_MAP_KEYWORDS = [
    "નકશો", "નક્શો", "નકશા", "નક્શા", "નકશાપૂર્તિ", "નક્શાપૂર્તિ", "map", "સંજ્ઞા વડે", "સંગ્ના વદે",
    "નકશામાં દર્શાવો", "વિભાગો બતાવો", "જિલ્લા દર્શાવો", "કિલ્લા", "મગધ", "પ્રદેશો"
]

def wants_math_fraction_visual(text):
    t = (text or "").lower()
    return ("વર્તુળ" in t or "circle" in t or "અપૂર્ણાંક" in t) and any(k in t for k in ("ભાગ", "1/", "2/", "3/", "part", "બતાવો", "દર્શાવો"))

def wants_diagram(text):
    t = (text or "").lower()
    return any(kw in t for kw in _DIAGRAM_KEYWORDS)

def wants_map(text):
    t = (text or "").lower()
    return any(kw in t for kw in _MAP_KEYWORDS)

def is_gk_or_current_affairs(text):
    t = (text or "").lower()
    return any(kw in t for kw in _GK_OR_CA_KEYWORDS)

def extract_grade(text):
    t = (text or "").translate(_GUJ_DIGIT_MAP).lower()
    patterns = [
        r"ધોરણ\s*[-:.]?\s*([3-8])",
        r"ધો\.?\s*[-:.]?\s*([3-8])",
        r"std\.?\s*[-:.]?\s*([3-8])",
        r"dhoran\s*[-:.]?\s*([3-8])",
        r"grade\s*[-:.]?\s*([3-8])",
        r"class\s*[-:.]?\s*([3-8])",
        r"\b([3-8])\s*મુ\b",
        r"\b([3-8])\s*માં\b",
    ]
    for p in patterns:
        if m := re.search(p, t):
            return int(m.group(1))
    return None

def extract_subject(text):
    t = (text or "").lower()
    for code, keywords in _EXPLICIT_SUBJECTS.items():
        for kw in keywords:
            if re.search(rf"(?<![a-zA-Z]){re.escape(kw.lower())}(?![a-zA-Z])", t):
                return code
    return None

def resolve_grade_subject_and_pdfs(current_query, past_user_queries, syllabus):
    explicit_grade = extract_grade(current_query)
    explicit_subject = extract_subject(current_query)

    if explicit_grade is None and is_gk_or_current_affairs(current_query):
        return None, None, []

    grade = explicit_grade
    subject = explicit_subject

    if grade is None or subject is None:
        is_followup = any(w in current_query.lower() for w in ("આ પાઠ", "આ પ્રકરણ", "આનો", "તેનો", "સારાંશ", "સ્વાધ્યાય", "mcq", "ઉદાહરણ", "વધુ સમજાવો"))
        if is_followup:
            for prev_q in reversed(past_user_queries[-3:]):
                if grade is None:
                    grade = extract_grade(prev_q)
                if subject is None:
                    subject = extract_subject(prev_q)
                if grade is not None and subject is not None:
                    break

    if not grade or not subject:
        return grade, subject, []

    matched = []
    grade_key = f"ધોરણ {grade}"
    subjects_dict = (syllabus.get(grade_key) or {}).get("subjects", {})
    for _label, info in subjects_dict.items():
        if info.get("code") == subject:
            for p in info.get("local_pdfs") or []:
                path = p.replace("\\", "/")
                if os.path.exists(path) and path not in matched:
                    matched.append(path)
            break

    if not matched:
        folder = f"textbook/std{grade}"
        if os.path.isdir(folder):
            for fname in sorted(os.listdir(folder)):
                if not fname.lower().endswith(".pdf"):
                    continue
                low = fname.lower()
                if subject == "gujarati" and any(k in low for k in ("gujarati", "kalshor", "kekarav", "kuhu", "palash")) and not any(x in low for x in ("sanskrit", "sanskrut", "gita", "ગીતા")):
                    matched.append(f"{folder}/{fname}")
                elif subject == "sanskrit" and any(k in low for k in ("sanskrit", "sanskrut", "સંસ્કૃત")):
                    matched.append(f"{folder}/{fname}")
                elif subject == "math" and any(k in low for k in ("math", "ganit", "ગણિત")) and "vedic" not in low and "વૈદિક" not in low:
                    matched.append(f"{folder}/{fname}")
                elif subject == "science" and any(k in low for k in ("science", "vigyan", "વિજ્ઞાન")):
                    matched.append(f"{folder}/{fname}")
                elif subject == "social_science" and any(k in low for k in ("social", "samajik", "સામાજિક")):
                    matched.append(f"{folder}/{fname}")
                elif subject == "environment" and any(k in low for k in ("environment", "evs", "paryavaran", "પર્યાવરણ")):
                    matched.append(f"{folder}/{fname}")
                elif subject == "english" and "english" in low:
                    matched.append(f"{folder}/{fname}")
                elif subject == "hindi" and any(k in low for k in ("hindi", "titali")):
                    matched.append(f"{folder}/{fname}")

    return grade, subject, matched[:2]

# --- VISION PAGE RENDERER ---
def _pick_target_page_indices(total_pages, query_text, full_query_context):
    selected = set(range(min(22, total_pages)))

    q_norm = f"{query_text} {full_query_context}".translate(_GUJ_DIGIT_MAP).lower()
    chap_nums = [int(n) for n in re.findall(r"(?:પાઠ|પ્રકરણ|કવિતા|એકમ|chapter|unit|lesson)\s*[-:.]?\s*(\d{1,2})", q_norm)]
    if not chap_nums:
        cleaned = re.sub(r"(?:ધોરણ|ધો\.?|std\.?|dhoran|grade|class)\s*[-:.]?\s*[3-8]", " ", q_norm)
        chap_nums = [int(n) for n in re.findall(r"\b(\d{1,2})\b", cleaned) if 1 <= int(n) <= 25]

    for ch in chap_nums[:2]:
        est_start = max(16, 14 + (ch - 1) * 8)
        for p in range(est_start - 2, min(total_pages, est_start + 10)):
            selected.add(p)

    for p_str in re.findall(r"(?:પાના|પાનું|પેજ|page)\s*(?:નંબર|નં\.?|no\.?)?\s*[-:.]?\s*(\d{1,3})", q_norm):
        p_idx = int(p_str) - 1
        for neighbor in range(max(0, p_idx - 1), min(total_pages, p_idx + 3)):
            selected.add(neighbor)

    return sorted(selected)[:28]

@st.cache_data(show_spinner=False)
def render_pdf_pages_as_jpeg_bytes(abspath, mtime, page_indices):
    images = []
    try:
        import fitz
        with fitz.open(abspath) as doc:
            for idx in page_indices:
                if 0 <= idx < len(doc):
                    pix = doc[idx].get_pixmap(dpi=130, alpha=False)
                    images.append((idx + 1, pix.tobytes("jpeg", jpg_quality=82)))
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

    target_indices = _pick_target_page_indices(total_pages, query_text, history_text)
    rendered = render_pdf_pages_as_jpeg_bytes(abspath, mtime, tuple(target_indices))
    parts = []
    for _pno, jpg_bytes in rendered:
        parts.append(types.Part.from_bytes(data=jpg_bytes, mime_type="image/jpeg"))
    return parts

def render_message_with_visuals(content, image_bytes=None, msg_idx=0, math_svg=None):
    # Strip any accidental ASCII art code blocks
    content = re.sub(r"```(?!map_json)[a-zA-Z]*\n[\s\S]*?```", "", content)

    if image_bytes:
        st.image(image_bytes, caption="🗺️ Nano Banana AI દ્વારા તૈયાર કરેલ પાઠ્યપુસ્તક નકશો / આકૃતિ", use_container_width=True)
        st.download_button(
            "⬇️ નકશો / આકૃતિ ડાઉનલોડ કરો",
            data=image_bytes,
            file_name=f"palaj_ai_visual_{msg_idx}.png",
            mime="image/png",
            key=f"dl_img_{msg_idx}"
        )

    if math_svg and not image_bytes:
        html_math = (
            '<div style="background:#FFFFFF; border-radius:12px; padding:8px; '
            'text-align:center; border:2px solid #93C5FD; font-family:\'Noto Sans Gujarati\', sans-serif;">'
            f'{math_svg}</div>'
        )
        components.html(html_math, height=345, scrolling=False)

    if "```map_json" in content:
        segments = re.split(r"(```map_json[\s\S]*?```)", content)
        for seg in segments:
            if seg.startswith("```map_json"):
                if not image_bytes:
                    raw_json = re.sub(r"^```map_json\s*|\s*```$", "", seg).strip()
                    try:
                        spec = json.loads(raw_json)
                        region = str(spec.get("region", "")).lower()
                        title_low = str(spec.get("title", "")).lower()
                        if region == "gujarat" or ("ગુજરાત" in title_low and "ભારત" not in title_low and "મગધ" not in title_low):
                            components.html(build_gujarat_map_html(spec), height=420, scrolling=False)
                        else:
                            components.html(build_india_map_html(spec), height=475, scrolling=False)
                    except Exception:
                        pass
            elif seg.strip():
                st.markdown(seg)
        return

    clean = re.sub(r"```(?:svg|xml|html)?\s*(<svg[\s\S]*?</svg>)\s*```", r"\1", content, flags=re.IGNORECASE)
    if "<svg" in clean.lower() and "</svg>" in clean.lower():
        parts = re.split(r"(<svg[\s\S]*?</svg>)", clean, flags=re.IGNORECASE)
        for part in parts:
            if part.strip().lower().startswith("<svg"):
                if not image_bytes and not math_svg:
                    html_box = (
                        '<div style="background:#FFFFFF; border-radius:12px; padding:8px; '
                        'text-align:center; border:2px solid #93C5FD; font-family:\'Noto Sans Gujarati\', sans-serif;">'
                        f'{part}</div>'
                    )
                    components.html(html_box, height=355, scrolling=False)
            elif part.strip():
                st.markdown(part)
    else:
        st.markdown(clean)

syllabus_data = load_syllabus()

# --- PREMIUM GEMINI / CHATGPT STYLE UI ---
st.markdown("""
<style>
:root {
    --app-bg: #F4F7FB;
    --app-text: #0F172A;
    --surface: #FFFFFF;
    --surface-border: #CBD5E1;
    --sidebar-bg: #FFFFFF;
    --sidebar-text: #0F172A;
    --bubble-user: #1E3A8A;
    --bubble-assistant: #111827;
    --bubble-text: #FFFFFF;
}

html, body, [data-testid="stAppViewContainer"], .stApp, .main {
    max-width: 100vw !important;
    overflow-x: hidden !important;
    font-family: system-ui, -apple-system, 'Noto Sans Gujarati', 'Shruti', sans-serif !important;
    background-color: var(--app-bg) !important;
    color: var(--app-text) !important;
}

[data-testid="stHeader"] { background: transparent !important; }

.block-container {
    padding-top: 2.5rem !important;
    padding-bottom: 6.2rem !important;
    padding-left: 0.75rem !important;
    padding-right: 0.75rem !important;
    max-width: 820px !important;
    margin: 0 auto !important;
}

.slim-header {
    background: linear-gradient(90deg, #1E3A8A 0%, #2563EB 50%, #0284C7 100%);
    color: #FFFFFF !important;
    -webkit-text-fill-color: #FFFFFF !important;
    padding: 10px 18px;
    border-radius: 50px;
    text-align: center;
    font-size: 1.05rem;
    font-weight: 700;
    box-shadow: 0 4px 14px rgba(37, 99, 235, 0.22);
    margin-bottom: 12px;
}

.book-badge {
    display: inline-block;
    background: #DBEAFE;
    color: #1E3A8A !important;
    -webkit-text-fill-color: #1E3A8A !important;
    border: 1px solid #93C5FD;
    padding: 4px 12px;
    border-radius: 999px;
    font-size: 0.85rem;
    font-weight: 600;
    margin-bottom: 8px;
}

section[data-testid="stSidebar"], [data-testid="stSidebar"] > div {
    background-color: var(--sidebar-bg) !important;
    color: var(--sidebar-text) !important;
    border-right: 1px solid var(--surface-border) !important;
}
section[data-testid="stSidebar"] p, section[data-testid="stSidebar"] span, section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] h1, section[data-testid="stSidebar"] h2, section[data-testid="stSidebar"] h3 {
    color: var(--sidebar-text) !important;
    -webkit-text-fill-color: var(--sidebar-text) !important;
}

.stButton > button, [data-testid="stDownloadButton"] > button {
    background-color: var(--surface) !important;
    color: var(--app-text) !important;
    -webkit-text-fill-color: var(--app-text) !important;
    border: 1px solid var(--surface-border) !important;
    border-radius: 10px !important;
    font-weight: 600 !important;
}

[data-testid="stChatMessage"] {
    border-radius: 16px !important;
    padding: 0.75rem 0.95rem !important;
    margin-bottom: 0.65rem !important;
    box-shadow: 0 2px 10px rgba(15, 23, 42, 0.12) !important;
    background-color: var(--bubble-assistant) !important;
    border-left: 4px solid #3B82F6 !important;
}
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]),
[data-testid="stChatMessage"][aria-label*="user" i] {
    background-color: var(--bubble-user) !important;
    border-left: 4px solid #93C5FD !important;
}
[data-testid="stChatMessage"] p, [data-testid="stChatMessage"] li, [data-testid="stChatMessage"] span,
[data-testid="stChatMessage"] strong, [data-testid="stChatMessage"] em {
    color: var(--bubble-text) !important;
    -webkit-text-fill-color: var(--bubble-text) !important;
}
[data-testid="stChatMessage"] p, [data-testid="stChatMessage"] li { font-size: 16px !important; line-height: 1.6 !important; }
[data-testid="stChatMessage"] .book-badge {
    background: #DBEAFE !important;
    color: #1E3A8A !important;
    -webkit-text-fill-color: #1E3A8A !important;
}
[data-testid="stChatMessage"] [data-testid="stDownloadButton"] > button {
    background-color: #FFFFFF !important;
    color: #0F172A !important;
    -webkit-text-fill-color: #0F172A !important;
}

[data-testid="stBottom"],
[data-testid="stBottom"] > div,
[data-testid="stBottom"] [data-testid="stVerticalBlock"],
[data-testid="stBottom"] [data-testid="stElementContainer"] {
    background: transparent !important;
    background-color: transparent !important;
    box-shadow: none !important;
    border: none !important;
}

[data-testid="stBottom"] {
    padding: 0.5rem 0.75rem 0.75rem 0.75rem !important;
    z-index: 99999 !important;
}

[data-testid="stBottom"] > div {
    max-width: 780px !important;
    margin: 0 auto !important;
    padding: 0 !important;
}

[data-testid="stBottom"] [data-testid="stHorizontalBlock"] {
    display: grid !important;
    grid-template-columns: 38px minmax(0, 1fr) 38px 38px !important;
    align-items: center !important;
    gap: 8px !important;
    background: linear-gradient(135deg, #1E293B 0%, #0F172A 100%) !important;
    border: 1px solid #334155 !important;
    border-radius: 999px !important;
    padding: 6px 10px !important;
    box-shadow: 0 10px 28px rgba(15, 23, 42, 0.25) !important;
    width: 100% !important;
    box-sizing: border-box !important;
}

[data-testid="stBottom"] [data-testid="stColumn"] {
    width: 100% !important;
    min-width: 0 !important;
    max-width: 100% !important;
    padding: 0 !important;
    margin: 0 !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
}

[data-testid="stBottom"] [data-testid="stTextInput"] { width: 100% !important; }
[data-testid="stBottom"] div[data-baseweb="input"],
[data-testid="stBottom"] div[data-baseweb="base-input"] {
    background-color: transparent !important;
    border: none !important;
    box-shadow: none !important;
    min-height: 38px !important;
    width: 100% !important;
}
[data-testid="stBottom"] input,
[data-testid="stBottom"] input[type="text"] {
    background-color: transparent !important;
    color: #F8FAFC !important;
    -webkit-text-fill-color: #F8FAFC !important;
    caret-color: #60A5FA !important;
    border: none !important;
    box-shadow: none !important;
    padding: 6px 6px !important;
    font-size: 15.5px !important;
    height: 38px !important;
    width: 100% !important;
}
[data-testid="stBottom"] input::placeholder {
    color: #94A3B8 !important;
    -webkit-text-fill-color: #94A3B8 !important;
    opacity: 1 !important;
}
[data-testid="stBottom"] [data-testid="InputInstructions"] { display: none !important; }

[data-testid="stBottom"] button {
    border-radius: 50% !important;
    width: 38px !important;
    height: 38px !important;
    min-height: 38px !important;
    min-width: 38px !important;
    padding: 0 !important;
    border: none !important;
    color: #FFFFFF !important;
    -webkit-text-fill-color: #FFFFFF !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    box-shadow: none !important;
    transition: transform 0.15s ease, background-color 0.2s ease !important;
}
[data-testid="stBottom"] button:hover { transform: scale(1.06); }

[data-testid="stBottom"] [data-testid="stPopover"] > button {
    background-color: #334155 !important;
    border: 1px solid #475569 !important;
    font-size: 17px !important;
}
[data-testid="stBottom"] [data-testid="stPopover"] > button svg { display: none !important; }

[data-testid="stBottom"] button[kind="secondary"] {
    background-color: #334155 !important;
    border: 1px solid #475569 !important;
    font-size: 16px !important;
}
[data-testid="stBottom"] button[kind="secondary"]:hover {
    background-color: #475569 !important;
}

[data-testid="stBottom"] button[kind="primary"] {
    background: linear-gradient(135deg, #3B82F6 0%, #1D4ED8 100%) !important;
    font-size: 15px !important;
}

@media (max-width: 600px) {
    .slim-header { font-size: 0.92rem; padding: 8px 12px; }
    [data-testid="stBottom"] { padding: 0.35rem 0.45rem 0.5rem 0.45rem !important; }
    [data-testid="stBottom"] [data-testid="stHorizontalBlock"] {
        grid-template-columns: 34px minmax(0, 1fr) 34px 34px !important;
        gap: 6px !important;
        padding: 4px 8px !important;
    }
    [data-testid="stBottom"] button {
        width: 34px !important;
        height: 34px !important;
        min-height: 34px !important;
        min-width: 34px !important;
    }
    [data-testid="stBottom"] input,
    [data-testid="stBottom"] input[type="text"] {
        font-size: 14.5px !important;
        height: 34px !important;
    }
}
</style>
""", unsafe_allow_html=True)

# --- SESSION STATE ---
defaults = {
    "messages": [], "mcq_questions": None, "mcq_user_answers": {}, "mcq_checked": False,
    "draft_text": "", "mic_open": False, "audio_counter": 0, "input_version": 0, "voice_error": "",
    "ui_lang": "ગુજરાતી", "visual_mode": "Nano Banana Full Textbook Image (Auto Backup)"
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# --- SIDEBAR ---
with st.sidebar:
    st.markdown("### 🎓 સ્માર્ટ AI શિક્ષક")
    raw_keys = (st.secrets.get("GEMINI_API_KEYS") or os.environ.get("GEMINI_API_KEYS") or
                st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY") or "")
    api_keys = [k.strip().strip("\"'") for k in str(raw_keys).split(",") if k.strip()]

    model_choice = st.selectbox("🤖 AI મોડેલ:", ACTIVE_MODELS)
    st.session_state.visual_mode = st.selectbox(
        "🗺️ નકશા / આકૃતિ મોડ:",
        [
            "Nano Banana Full Textbook Image (Auto Backup)",
            "Only Interactive Vector Map/SVG (Fastest)",
        ]
    )

    st.markdown("### 🛠️ ક્વિક ટૂલ્સ")
    quick_action = None
    c1, c2 = st.columns(2)
    if c1.button("📖 સારાંશ"): quick_action = "summary"
    if c1.button("📝 MCQ ટેસ્ટ"): quick_action = "mcq"
    if c2.button("📝 સ્વાધ્યાય"): quick_action = "exercise"
    if c2.button("💡 ઉદાહરણ"): quick_action = "easy_example"

    st.divider()
    if st.button("🗑️ નવી ચેટ", use_container_width=True):
        st.session_state.update({
            "messages": [], "mcq_questions": None, "mcq_user_answers": {},
            "mcq_checked": False, "draft_text": "", "voice_error": "",
            "input_version": st.session_state.input_version + 1
        })
        st.rerun()

    u1, u2 = st.columns([1, 2])
    dl_fmt = u1.selectbox("ફોર્મેટ", [".pdf", ".txt", ".md"], label_visibility="collapsed")
    if u2.button("📥 નોટ્સ", use_container_width=True) and st.session_state.messages:
        if dl_fmt == ".pdf":
            data, mime = build_pdf_bytes(st.session_state.messages), "application/pdf"
        else:
            data = "\n\n".join(f"{'વિદ્યાર્થી' if m['role']=='user' else 'શિક્ષક'}: {m['content']}" for m in st.session_state.messages)
            mime = "text/plain"
        st.download_button("⬇️ ડાઉનલોડ", data=data, file_name=f"notes{dl_fmt}", mime=mime, use_container_width=True)

# --- HEADER ---
st.markdown('<div class="slim-header">📚 Standard 3 to 8 Smart AI Palaj Teacher</div>', unsafe_allow_html=True)

if quick_action:
    prompts = {
        "summary": "છેલ્લી ચર્ચા મુજબના પાઠનો સરળ ગુજરાતીમાં મુદ્દાસર સારાંશ આપો.",
        "exercise": "છેલ્લી ચર્ચા મુજબના પાઠના સ્વાધ્યાયના પ્રશ્નો અને જવાબો સમજૂતી સાથે આપો.",
        "mcq": "છેલ્લી ચર્ચા મુજબના પાઠ આધારિત ૫ MCQ બનાવો. ફોર્મેટ:\nપ્રશ્ન 1: પ્રશ્ન?\nA. ...\nB. ...\nC. ...\nD. ...\nસાચો જવાબ: B\nસમજૂતી: ...",
        "easy_example": "છેલ્લી ચર્ચા મુજબના વિષયનું વાસ્તવિક જીવનના સરળ ઉદાહરણો દ્વારા સમજાવો."
    }
    if quick_action == "mcq":
        st.session_state.update({"mcq_questions": None, "mcq_user_answers": {}, "mcq_checked": False})
    st.session_state.messages.append({"role": "user", "content": prompts[quick_action]})

# --- CHAT HISTORY ---
for idx_m, m in enumerate(st.session_state.messages):
    with st.chat_message(m["role"]):
        render_message_with_visuals(
            m["content"],
            m.get("image_bytes"),
            msg_idx=idx_m,
            math_svg=m.get("math_svg")
        )

# --- INTERACTIVE MCQ ---
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

    c1, c2 = st.columns(2)
    if c1.button("🏆 સ્કોર તપાસો"):
        st.session_state.mcq_checked = True
    if c2.button("🔄 નવો ટેસ્ટ"):
        st.session_state.update({"mcq_questions": None, "mcq_user_answers": {}, "mcq_checked": False})
        st.rerun()

    if st.session_state.mcq_checked:
        score = sum(1 for i, q in enumerate(st.session_state.mcq_questions) if st.session_state.mcq_user_answers.get(i) == q["answer"])
        st.success(f"🎯 તમારો સ્કોર: **{score} / {len(st.session_state.mcq_questions)}**")
        for i, q in enumerate(st.session_state.mcq_questions):
            ua, ca = st.session_state.mcq_user_answers.get(i), q["answer"]
            correct_opt = q["options"].get(ca, "")
            with st.container(border=True):
                status_text = "✅ સાચો!" if ua == ca else f"❌ ખોટો! સાચો જવાબ: **{ca}. {correct_opt}**"
                st.markdown(f"**પ્રશ્ન {i+1}:** {status_text}")
                if q.get("explanation"):
                    st.caption(f"💡 સમજૂતી: {q['explanation']}")

if st.session_state.voice_error:
    e1, e2 = st.columns([8, 1])
    e1.warning(f"⚠️ {st.session_state.voice_error}")
    if e2.button("✖", key="dismiss_err"):
        st.session_state.voice_error = ""
        st.rerun()

# --- VOICE INPUT ---
if st.session_state.mic_open:
    with st.container(border=True):
        st.markdown(f"🎙️ **માઈક પર દબાવી {st.session_state.ui_lang} માં બોલો, પૂરું થાય એટલે ⏹ દબાવો:**")
        audio_val = st.audio_input("રેકોર્ડ", key=f"mob_rec_{st.session_state.audio_counter}", label_visibility="collapsed")
        if st.button("❌ બંધ કરો", key="close_rec_btn"):
            st.session_state.mic_open = False
            st.rerun()
        if audio_val is not None:
            with st.spinner("🎧 લખાઈ રહ્યું છે..."):
                spoken, err = transcribe_gujarati(audio_val, api_keys, preferred_model=model_choice, lang_name=st.session_state.ui_lang)
            st.session_state.audio_counter += 1
            st.session_state.mic_open = False
            if spoken:
                st.session_state.voice_error = ""
                existing = st.session_state.draft_text.strip()
                st.session_state.draft_text = f"{existing} {spoken}".strip() if existing else spoken
                st.session_state.input_version += 1
            else:
                st.session_state.voice_error = err or "અવાજ સ્પષ્ટ સંભળાયો નથી, ફરીથી બોલો."
            st.rerun()

# --- ATTACHMENT PREVIEW ---
attached = st.session_state.get("bottom_uploader") or st.session_state.get("bottom_camera")
if attached:
    with st.container(border=True):
        t1, t2, t3 = st.columns([1, 6, 1])
        try:
            t1.image(Image.open(io.BytesIO(attached.getvalue())), width=45)
        except Exception:
            t1.markdown("📎")
        t2.caption(f"📎 જોડાયેલ: {getattr(attached, 'name', 'ફોટો')}")
        if t3.button("❌", key="rm_att"):
            st.session_state.pop("bottom_uploader", None)
            st.session_state.pop("bottom_camera", None)
            st.rerun()

# --- SLEEK GEMINI / CHATGPT STYLE FLOATING INPUT BAR ---
with getattr(st, "bottom", st.container()):
    col_plus, col_in, col_mic, col_send = st.columns([1, 10, 1, 1], vertical_alignment="center")
    with col_plus:
        with st.popover("➕"):
            selected_lang = st.radio(
                "🌐 જવાબની ભાષા પસંદ કરો:",
                ["ગુજરાતી", "English", "हिन्दी"],
                index=["ગુજરાતી", "English", "हिन्दी"].index(st.session_state.ui_lang),
                horizontal=True,
                key="popover_lang_select"
            )
            st.session_state.ui_lang = selected_lang
            st.divider()
            st.file_uploader("📁 ગેલેરી / PDF પસંદ કરો", key="bottom_uploader")
            st.camera_input("📸 કેમેરાથી ફોટો પાડો", key="bottom_camera")
    with col_in:
        placeholders = {
            "ગુજરાતી": f"પ્રશ્ન, આકૃતિ, નકશો કે GK પૂછો ({st.session_state.ui_lang})...",
            "English": "Ask any question, diagram, map or GK (English)...",
            "हिन्दी": "प्रश्न, चित्र, मानचित्र या GK पूछें (हिन्दी)..."
        }
        user_text = st.text_input(
            "પ્રશ્ન...",
            value=st.session_state.draft_text,
            key=f"chat_box_{st.session_state.input_version}",
            placeholder=placeholders.get(st.session_state.ui_lang, placeholders["ગુજરાતી"]),
            label_visibility="collapsed"
        )
        st.session_state.draft_text = user_text
    with col_mic:
        if st.button("🎤", key="real_mic_btn", help="બોલીને લખો"):
            st.session_state.voice_error = ""
            st.session_state.mic_open = not st.session_state.mic_open
            st.rerun()
    with col_send:
        send_clicked = st.button("➤", type="primary", key="real_send_btn", help="મોકલો")

if send_clicked and (user_text.strip() or attached):
    st.session_state.messages.append({"role": "user", "content": user_text.strip() or "[ફાઈલ સંલગ્ન છે]"})
    st.session_state.draft_text = ""
    st.session_state.voice_error = ""
    st.session_state.input_version += 1
    st.session_state.mic_open = False
    st.rerun()

# --- AI RESPONSE ---
if st.session_state.messages and st.session_state.messages[-1]["role"] == "user":
    clean_q = st.session_state.messages[-1]["content"].strip()
    reply_lang = st.session_state.ui_lang
    with st.chat_message("assistant"):
        if not HAS_GENAI or not api_keys:
            st.error("⚠️ Secrets માં GEMINI_API_KEY દાખલ કરો.")
        else:
            past_user_msgs = [m["content"] for m in st.session_state.messages[:-1] if m["role"] == "user"]
            grade, subject, local_pdf_paths = resolve_grade_subject_and_pdfs(clean_q, past_user_msgs, syllabus_data)

            user_att_parts = []
            att = st.session_state.get("bottom_uploader") or st.session_state.get("bottom_camera")
            if att:
                fb = att.getvalue()
                if getattr(att, "type", "") == "application/pdf":
                    user_att_parts.append(types.Part.from_bytes(data=fb, mime_type="application/pdf"))
                else:
                    user_att_parts.append(Image.open(io.BytesIO(fb)))
            st.session_state.pop("bottom_uploader", None)
            st.session_state.pop("bottom_camera", None)

            sub_label = _SUBJECT_LABELS.get(subject, subject or "")
            if grade and sub_label and local_pdf_paths:
                pdf_names = ", ".join(os.path.basename(p) for p in local_pdf_paths)
                st.markdown(f'<div class="book-badge">📖 ધોરણ {grade} | {sub_label} — {pdf_names}</div>', unsafe_allow_html=True)
            elif is_gk_or_current_affairs(clean_q):
                st.markdown('<div class="book-badge">🌍 સામાન્ય જ્ઞાન (GK) & વર્તમાન પ્રવાહો (Current Affairs)</div>', unsafe_allow_html=True)

            recent_hist = "\n".join(
                f"{'વિદ્યાર્થી' if m['role']=='user' else 'શિક્ષક'}: {m['content']}"
                for m in st.session_state.messages[:-1][-4:]
            )

            book_page_parts = []
            for pdf_path in local_pdf_paths:
                book_page_parts.extend(build_vision_pdf_parts(pdf_path, clean_q, recent_hist))

            # --- VISUAL ENGINE: NANO BANANA IMAGE + MATH FRACTION + BACKUP VECTOR ---
            generated_img_bytes = None
            math_svg_code = None
            is_map_q = wants_map(clean_q)
            is_math_frac_q = wants_math_fraction_visual(clean_q)
            is_diag_q = wants_diagram(clean_q)
            v_mode = st.session_state.visual_mode

            if is_math_frac_q:
                math_svg_code = build_math_fraction_svg(clean_q)

            if (is_map_q or is_diag_q) and v_mode != "Only Interactive Vector Map/SVG (Fastest)":
                v_type = "map" if is_map_q else ("math" if is_math_frac_q else "diagram")
                with st.spinner("🎨 Nano Banana AI દ્વારા પાઠ્યપુસ્તક નકશો / આકૃતિ તૈયાર થઈ રહી છે..."):
                    generated_img_bytes, img_err = generate_nano_banana_visual(
                        clean_q,
                        api_keys,
                        visual_type=v_type,
                        reply_lang=reply_lang
                    )
                if not generated_img_bytes and img_err:
                    st.caption(f"ℹ️ ઈમેજ મોડેલ નોંધ: ફ્રી API પર ઈમેજ ક્વોટા મર્યાદિત હોવાથી સ્માર્ટ વેક્ટર નકશો/આકૃતિ બતાવેલ છે.")

            visual_instruction = ""
            if is_map_q:
                visual_instruction = (
                    "\n6. **નકશા પૂર્તિ (ASCII Art સખત પ્રતિબંધિત છે):** "
                    "ક્યારેય ટેક્સ્ટ બોક્સ, `~~~`, `|`, `-`, `•` કે ASCII art વડે નકશો ન દોરો! "
                    "તમારા જવાબમાં સૌથી પહેલા નીચે મુજબનો એક ચોક્કસ ```map_json બ્લોક આપો:\n"
                    "```map_json\n"
                    "{\n"
                    "  \"region\": \"india\",\n"
                    "  \"title\": \"નકશા પૂર્તિ - પ્રદેશો / કિલ્લા / રાજ્યો\",\n"
                    "  \"items\": [\n"
                    "    {\"label\": \"મગધ દેશ\", \"symbol\": \"★\", \"color\": \"#DC2626\", \"states\": [\"મગધ\", \"વૈશાલી\"]},\n"
                    "    {\"label\": \"જૂના કિલ્લા\", \"symbol\": \"▲\", \"color\": \"#16A34A\", \"states\": [\"ચિત્તોડગઢ\", \"ગ્વાલિયર\"]}\n"
                    "  ]\n"
                    "}\n"
                    "```\n"
                    "   - જો નકશો ફક્ત **ગુજરાત** (જિલ્લા, નદીઓ, ગુજરાતના કિલ્લા) નો હોય તો `\"region\": \"gujarat\"` રાખો.\n"
                    "   - જો નકશો **ભારત, મગધ દેશ, પ્રાચીન પ્રદેશો કે ભારતના કિલ્લા** નો હોય તો `\"region\": \"india\"` રાખો.\n"
                    "   - `map_json` બ્લોકની નીચે દરેક સ્થળની મુદ્દાસર સ્પષ્ટ સમજૂતી આપો."
                )
            elif is_diag_q and not is_math_frac_q:
                visual_instruction = (
                    "\n6. **નામનિર્દેશવાળી આકૃતિ (ફરજિયાત `<svg>` કોડ મૂકો):** "
                    "તમારા જવાબમાં સૌથી પહેલા એકદમ સ્પષ્ટ, રંગીન અને સ્વચ્છ "
                    "**`<svg width=\"460\" height=\"340\" viewBox=\"0 0 460 340\" xmlns=\"[http://www.w3.org/2000/svg](http://www.w3.org/2000/svg)\">...</svg>`** કોડ ફરજિયાત લખો! "
                    "તેમાં સફેદ બેકગ્રાઉન્ડ (`<rect width=\"460\" height=\"340\" fill=\"#FFFFFF\"/>`), મુખ્ય આકૃતિ (દા.ત. વનસ્પતિ કોષની કોષદીવાલ, હરિતકણ, કોષકેન્દ્ર, રસધાની), તીર રેખાઓ (`<line>`) અને ગુજરાતીમાં નામનિર્દેશન (`<text>`) મૂકો, અને તેની નીચે મુદ્દાસર સમજૂતી આપો."
                )

            book_context_instruction = (
                f"સંદર્ભ પાઠ્યપુસ્તક: GCERT ધોરણ {grade} - {sub_label} (ગુજરાતી માધ્યમ). "
                "જો પ્રશ્ન પાઠ્યપુસ્તકના પાઠ કે અનુક્રમણિકાનો હોય, તો સંલગ્ન પાનાઓની ઈમેજ પરથી ૧૦૦% શુદ્ધ જોડણીમાં જવાબ આપો. "
                "જો વિદ્યાર્થીએ કોઈ બીજા વિષય કે સામાન્ય જ્ઞાનનો પ્રશ્ન પૂછ્યો હોય, તો પણ કોઈ ઠપકો આપ્યા વગર સીધો અને સચોટ જવાબ આપો."
                if local_pdf_paths else
                "વિદ્યાર્થીએ ધોરણ 3 થી 8 અભ્યાસક્રમ, General Knowledge (સામાન્ય જ્ઞાન), અથવા Current Affairs (વર્તમાન પ્રવાહો) નો પ્રશ્ન પૂછ્યો છે. ત્વરિત અને સચોટ જવાબ આપો."
            )

            sys_prompt = (
                "તમે ધોરણ 3 થી 8 ના વિદ્યાર્થીઓ માટેના અત્યંત પ્રેમાળ, ઉત્સાહી અને નિષ્ણાત AI શિક્ષક છો.\n"
                "મહત્વના નિયમો (કડકાઈથી પાલન કરો):\n"
                f"1. **જવાબની ભાષા:** વિદ્યાર્થીએ પસંદ કરેલી ભાષા **{reply_lang}** છે — આખો જવાબ, આકૃતિ અને નકશાના નામનિર્દેશન **{reply_lang}** ભાષામાં જ આપો (જ્યાં સુધી પ્રશ્નમાં અન્ય ભાષા ન માંગી હોય).\n"
                "2. **ઉષ્માભર્યો આવકાર:** દરેક જવાબની શરૂઆત ટૂંકા, પ્રેમાળ આવકારથી કરો (દા.ત., 'નમસ્તે વિદ્યાર્થી મિત્ર! 🙏' અથવા 'ખૂબ સરસ પ્રશ્ન છે! 🌟').\n"
                "3. **ક્યારેય વિષય બાબતે ઠપકો ન આપો:** ક્યારેય એવું ન લખો કે 'તમે આ વિષયનો જ પ્રશ્ન પૂછો' — વિદ્યાર્થી જે ધોરણ, જે વિષય, General Knowledge કે Current Affairs પૂછે તેનો તરત જ સીધો જવાબ આપો.\n"
                "4. **વિદ્યાર્થીની માંગ મુજબ શૈલી:** ટૂંકમાં માંગે તો ટૂંકમાં, વિગતવાર માંગે તો મુદ્દાસર વિગતથી, અને ઉદાહરણ માંગે તો સરળ ઉદાહરણો સાથે જવાબ આપો.\n"
                "5. **શુદ્ધ જોડણી:** ૧૦૦% શુદ્ધ લિપિ વાપરો અને ગણિત/વિજ્ઞાનના સૂત્રો $...$ માં લખો."
                f"{visual_instruction}\n\n"
                f"{book_context_instruction}"
            )
            prompt_text = f"{sys_prompt}\n\n{recent_hist}\nવિદ્યાર્થીનો પ્રશ્ન: {clean_q}"

            placeholder = st.empty()
            placeholder.markdown("⚡ *તમારા પ્રશ્નનો જવાબ તૈયાર થઈ રહ્યો છે...*")
            answer_text, success, last_err = "", False, None

            for key in api_keys:
                client = genai.Client(api_key=key)
                models = get_available_models_for_client(client, model_choice)
                contents = []
                contents.extend(book_page_parts)
                contents.extend(user_att_parts)
                contents.append(prompt_text)

                for mod in models:
                    try:
                        temp = ""
                        for chunk in client.models.generate_content_stream(model=mod, contents=contents):
                            if chunk.text:
                                temp += chunk.text
                                if "<svg" not in temp.lower() and "```map_json" not in temp:
                                    placeholder.markdown(temp + "▌")
                                else:
                                    placeholder.markdown("🗺️ *નકશો / આકૃતિ તૈયાર થઈ રહી છે...* ▌")
                        if temp.strip():
                            placeholder.empty()
                            render_message_with_visuals(
                                temp,
                                generated_img_bytes,
                                msg_idx=len(st.session_state.messages),
                                math_svg=math_svg_code
                            )
                            answer_text, success = temp, True
                            break
                    except Exception as e:
                        last_err = e
                        if not any(x in str(e) for x in ("404", "429", "RESOURCE_EXHAUSTED", "API_KEY_INVALID")):
                            try:
                                resp = client.models.generate_content(model=mod, contents=contents)
                                if resp and resp.text and resp.text.strip():
                                    placeholder.empty()
                                    render_message_with_visuals(
                                        resp.text,
                                        generated_img_bytes,
                                        msg_idx=len(st.session_state.messages),
                                        math_svg=math_svg_code
                                    )
                                    answer_text, success = resp.text, True
                                    break
                            except Exception as e2:
                                last_err = e2
                        if any(x in str(last_err) for x in ("429", "RESOURCE_EXHAUSTED", "API_KEY_INVALID")):
                            break
                if success:
                    break

            if success:
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": answer_text,
                    "image_bytes": generated_img_bytes,
                    "math_svg": math_svg_code
                })
                if quick_action == "mcq" and st.session_state.mcq_questions is None:
                    if parsed := parse_mcq(answer_text):
                        st.session_state.mcq_questions = parsed
                    st.rerun()
            else:
                placeholder.empty()
                friendly = format_friendly_error(last_err)
                err_msg = f"❌ {friendly}"
                st.error(err_msg)
                st.session_state.messages.append({"role": "assistant", "content": err_msg})