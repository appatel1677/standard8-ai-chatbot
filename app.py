import streamlit as st
import streamlit.components.v1 as components
import json, os, io, re, math, urllib.request, urllib.parse
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
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-3-flash-preview",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
]

DEFAULT_IMAGE_MODELS = [
    "gemini-2.5-flash-image",
    "gemini-2.0-flash-exp-image-generation",
    "gemini-3-pro-image-preview",
]

@st.cache_resource
def get_cached_client(api_key):
    return genai.Client(api_key=api_key)

@st.cache_data(ttl=3600, show_spinner=False)
def get_available_models_cached(api_key, preferred_model):
    candidates = list(dict.fromkeys([preferred_model] + ACTIVE_MODELS))
    try:
        client = get_cached_client(api_key)
        for m in client.models.list():
            name = (getattr(m, "name", "") or "").replace("models/", "")
            if "gemini" in name.lower() and "flash" in name.lower() and not any(x in name.lower() for x in ("embedding", "imagen", "veo", "aqa", "tts", "audio", "robotics", "image")):
                if name not in candidates:
                    candidates.append(name)
    except Exception:
        pass
    return candidates[:5]

@st.cache_data(ttl=3600, show_spinner=False)
def get_available_image_models_cached(api_key):
    img_candidates = list(DEFAULT_IMAGE_MODELS)
    try:
        client = get_cached_client(api_key)
        for m in client.models.list():
            name = (getattr(m, "name", "") or "").replace("models/", "")
            if "image" in name.lower() and "imagen" not in name.lower() and name not in img_candidates:
                img_candidates.insert(0, name)
    except Exception:
        pass
    return img_candidates[:2]

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
        urllib.request.urlretrieve("https://github.com/google/fonts/raw/main/ofl/notosansgujarati/NotoSansGujarati%5Bwdth%2Cwght%5D.ttf", "NotoSansGujarati-Regular.ttf")
        return "NotoSansGujarati-Regular.ttf"
    except Exception:
        return None

def svg_to_png_bytes(svg_code):
    try:
        import fitz
        doc = fitz.open(stream=svg_code.encode("utf-8"), filetype="svg")
        pix = doc[0].get_pixmap(dpi=160, alpha=False)
        return pix.tobytes("png")
    except Exception:
        return None

def build_pdf_bytes(messages):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=14)
    pdf.set_text_shaping(True)
    font_path = get_pdf_font()
    base_font = "Gujarati" if font_path else "helvetica"
    if font_path:
        pdf.add_font("Gujarati", "", font_path)
        pdf.add_font("Gujarati", "B", font_path)
    pdf.add_page()
    pdf.set_font(base_font, "B", 15)
    pdf.set_text_color(30, 58, 138)
    pdf.cell(0, 10, "Standard 3 to 8 Smart AI Palaj Teacher - Classroom Notes", ln=True, align="C")
    pdf.set_draw_color(147, 197, 253)
    pdf.line(12, pdf.get_y(), 198, pdf.get_y())
    pdf.ln(4)

    for m in messages:
        is_user = m["role"] == "user"
        pdf.set_font(base_font, "B", 11)
        pdf.set_text_color(185, 28, 28) if is_user else pdf.set_text_color(15, 23, 42)
        pdf.cell(0, 7, ("વિદ્યાર્થી / શિક્ષક પ્રશ્ન:" if is_user else "સ્માર્ટ AI શિક્ષક જવાબ:"), ln=True)

        vis_bytes = m.get("map_bytes") or m.get("image_bytes")
        if not vis_bytes and m.get("math_svg"):
            vis_bytes = svg_to_png_bytes(m["math_svg"])
        if not vis_bytes and "<svg" in m.get("content", "").lower():
            svg_m = re.search(r"(<svg[\s\S]*?</svg>)", m["content"], flags=re.IGNORECASE)
            if svg_m:
                vis_bytes = svg_to_png_bytes(svg_m.group(1))

        if vis_bytes:
            try:
                pil_im = Image.open(io.BytesIO(vis_bytes)).convert("RGB")
                img_buf = io.BytesIO()
                pil_im.save(img_buf, format="JPEG", quality=88)
                img_buf.seek(0)
                aspect = pil_im.height / max(pil_im.width, 1)
                disp_w = 176
                disp_h = min(disp_w * aspect, 125)
                if pdf.get_y() + disp_h > 275:
                    pdf.add_page()
                pdf.image(img_buf, x=17, w=disp_w, h=disp_h)
                pdf.ln(3)
            except Exception:
                pass

        pdf.set_font(base_font, "", 10.5)
        pdf.set_text_color(30, 41, 59)
        clean_txt = re.sub(r"```(?:svg|xml|html)?\s*<svg[\s\S]*?</svg>\s*```", "", m["content"], flags=re.IGNORECASE)
        clean_txt = re.sub(r"<svg[\s\S]*?</svg>", "", clean_txt, flags=re.IGNORECASE)
        clean_txt = re.sub(r"```(?:map_json|village_map_json)[\s\S]*?```", "", clean_txt)
        clean_txt = re.sub(r"<[^>]+>", "", clean_txt)
        clean_txt = clean_txt.replace("**", "").replace("###", "").replace("##", "").strip()
        if clean_txt:
            pdf.multi_cell(0, 6.2, clean_txt)
        pdf.ln(3)
        pdf.set_draw_color(226, 232, 240)
        pdf.line(14, pdf.get_y(), 196, pdf.get_y())
        pdf.ln(3)

    return bytes(pdf.output(dest="S"))

def format_friendly_error(err_str):
    e = str(err_str)
    if "429" in e or "RESOURCE_EXHAUSTED" in e:
        return "API Key નો ફ્રી ક્વોટા પૂરો થઈ ગયો છે. થોડીવાર પછી પ્રયાસ કરો અથવા નવી Key ઉમેરો."
    if "400" in e and ("API_KEY_INVALID" in e or "API key not valid" in e):
        return "તમારી GEMINI_API_KEY ખોટી છે. Secrets માં તપાસો."
    return f"કનેક્શન સમસ્યા: {e[:150]}"

def transcribe_gujarati(audio_file, api_keys, preferred_model="gemini-2.5-flash"):
    if not HAS_GENAI or not api_keys or not audio_file:
        return "", "API Key અથવા ઓડિયો ઉપલબ્ધ નથી."
    audio_bytes = audio_file.getvalue()
    if len(audio_bytes) < 100:
        return "", "ઓડિયો રેકોર્ડ થયો નથી."
    detected_mime = getattr(audio_file, "type", None) or "audio/wav"
    prompt = "Transcribe ONLY the exact spoken words in Gujarati script (ગુજરાતી લિપિ). No extra text."
    last_err = ""
    for key in api_keys:
        client = get_cached_client(key)
        for mod in get_available_models_cached(key, preferred_model):
            try:
                resp = client.models.generate_content(model=mod, contents=[types.Part.from_bytes(data=audio_bytes, mime_type=detected_mime), prompt])
                if resp and resp.text and resp.text.strip():
                    return resp.text.strip(), ""
            except Exception as e:
                last_err = str(e)
    return "", format_friendly_error(last_err)

@st.cache_data
def load_syllabus():
    if os.path.exists("diksha_syllabus.json"):
        with open("diksha_syllabus.json", "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

# ==============================================================================
# REAL GIS MAP ENGINE: SUPPORTS FULL MAPS & "ONLY SELECTED" ZOOMED SUBSET MAPS
# ==============================================================================
DISTRICT_EN_TO_GUJ = {
    "kachchh": ("કચ્છ", "kutch"), "kutch": ("કચ્છ", "kutch"),
    "banaskantha": ("બનાસકાંઠા", "north"), "banas kantha": ("બનાસકાંઠા", "north"),
    "patan": ("પાટણ", "north"),
    "mahesana": ("મહેસાણા", "north"), "mehsana": ("મહેસાણા", "north"),
    "sabarkantha": ("સાબરકાંઠા", "north"), "sabar kantha": ("સાબરકાંઠા", "north"),
    "aravalli": ("અરવલ્લી", "north"), "arvalli": ("અરવલ્લી", "north"),
    "gandhinagar": ("ગાંધીનગર", "central"),
    "ahmadabad": ("અમદાવાદ", "central"), "ahmedabad": ("અમદાવાદ", "central"),
    "kheda": ("ખેડા", "central"),
    "mahisagar": ("મહીસાગર", "central"),
    "panchmahal": ("પંચમહાલ", "central"), "panch mahals": ("પંચમહાલ", "central"),
    "dohad": ("દાહોદ", "central"), "dahod": ("દાહોદ", "central"),
    "anand": ("આણંદ", "central"),
    "vadodara": ("વડોદરા", "central"),
    "chhotaudepur": ("છોટા ઉદેપુર", "central"), "chhota udaipur": ("છોટા ઉદેપુર", "central"),
    "bharuch": ("ભરૂચ", "south"),
    "narmada": ("નર્મદા", "south"),
    "surat": ("સુરત", "south"),
    "tapi": ("તાપી", "south"),
    "navsari": ("નવસારી", "south"),
    "the dangs": ("ડાંગ", "south"), "dang": ("ડાંગ", "south"), "dangs": ("ડાંગ", "south"),
    "valsad": ("વલસાડ", "south"),
    "surendranagar": ("સુરેન્દ્રનગર", "saurashtra"),
    "morbi": ("મોરબી", "saurashtra"),
    "jamnagar": ("જામનગર", "saurashtra"),
    "devbhumi dwarka": ("દેવભૂમિ દ્વારકા", "saurashtra"), "dwarka": ("દેવભૂમિ દ્વારકા", "saurashtra"),
    "porbandar": ("પોરબંદર", "saurashtra"),
    "rajkot": ("રાજકોટ", "saurashtra"),
    "botad": ("બોટાદ", "saurashtra"),
    "junagadh": ("જૂનાગઢ", "saurashtra"),
    "amreli": ("અમરેલી", "saurashtra"),
    "bhavnagar": ("ભાવનગર", "saurashtra"),
    "gir somnath": ("ગીર સોમનાથ", "saurashtra"),
}

STATE_EN_TO_GUJ = {
    "jammu & kashmir": ("જમ્મુ-કાશ્મીર", "north"), "jammu and kashmir": ("જમ્મુ-કાશ્મીર", "north"),
    "ladakh": ("લદ્દાખ", "north"), "himachal pradesh": ("હિમાચલ", "north"),
    "punjab": ("પંજાબ", "north"), "uttarakhand": ("ઉત્તરાખંડ", "north"),
    "haryana": ("હરિયાણા", "north"), "delhi": ("દિલ્હી", "north"), "nct of delhi": ("દિલ્હી", "north"),
    "rajasthan": ("રાજસ્થાન", "west"), "uttar pradesh": ("ઉત્તર પ્રદેશ", "north"),
    "bihar": ("બિહાર", "east"), "gujarat": ("ગુજરાત", "west"),
    "madhya pradesh": ("મધ્ય પ્રદેશ", "central"), "jharkhand": ("ઝારખંડ", "east"),
    "west bengal": ("પશ્ચિમ બંગાળ", "east"), "chhattisgarh": ("છત્તીસગઢ", "central"),
    "odisha": ("ઓડિશા", "east"), "orissa": ("ઓડિશા", "east"),
    "maharashtra": ("મહારાષ્ટ્ર", "west"), "telangana": ("તેલંગાણા", "south"),
    "karnataka": ("કર્ણાટક", "south"), "goa": ("ગોવા", "west"),
    "andhra pradesh": ("આંધ્ર પ્રદેશ", "south"), "kerala": ("કેરળ", "south"),
    "tamil nadu": ("તમિલનાડુ", "south"), "assam": ("આસામ", "east"),
    "arunachal pradesh": ("અરુણાચલ", "east"), "meghalaya": ("મેઘાલય", "east"),
    "manipur": ("મણિપુર", "east"), "mizoram": ("મિઝોરમ", "east"),
    "nagaland": ("નાગાલેન્ડ", "east"), "tripura": ("ત્રિપુરા", "east"), "sikkim": ("સિક્કિમ", "east"),
}

ZONE_COLORS = {
    "kutch": "#DCE775", "north": "#F8BBD0", "central": "#FFCC80",
    "saurashtra": "#CE93D8", "south": "#80DEEA", "west": "#DCE775", "east": "#80DEEA",
}
PASTEL_PALETTE = ["#FDE68A", "#BAE6FD", "#FBCFE8", "#BBF7D0", "#DDD6FE", "#FED7AA", "#99F6E4", "#FECACA", "#E9D5FF", "#BFDBFE"]

GUJARAT_RIVERS_GEO = [
    ("નર્મદા નદી", [(74.1, 21.85), (73.5, 21.88), (73.0, 21.72), (72.6, 21.68)]),
    ("તાપી નદી", [(74.2, 21.25), (73.5, 21.28), (72.8, 21.12), (72.65, 21.05)]),
    ("સાબરમતી નદી", [(72.9, 24.1), (72.65, 23.2), (72.55, 22.6), (72.35, 22.25)]),
    ("મહી નદી", [(73.8, 23.3), (73.3, 22.8), (72.95, 22.35), (72.7, 22.2)]),
    ("બનાસ નદી", [(72.6, 24.4), (72.0, 24.1), (71.5, 23.8)]),
]

INDIA_RIVERS_GEO = [
    ("ગંગા નદી", [(78.2, 30.1), (80.5, 26.5), (83.0, 25.3), (86.5, 25.2), (88.2, 23.0)]),
    ("યમુના નદી", [(77.2, 28.6), (78.0, 27.1), (81.8, 25.4)]),
    ("નર્મદા નદી", [(81.5, 22.7), (77.0, 22.1), (73.0, 21.7)]),
    ("ગોદાવરી નદી", [(73.8, 19.9), (78.0, 18.8), (82.1, 16.8)]),
    ("કૃષ્ણા નદી", [(74.0, 17.8), (77.5, 16.3), (80.9, 15.8)]),
]

@st.cache_data(show_spinner=False)
def fetch_osm_real_boundary(place_query):
    os.makedirs("geo_cache", exist_ok=True)
    safe_key = re.sub(r"[^a-zA-Z0-9_]", "_", place_query.lower())[:50]
    cache_file = f"geo_cache/osm_{safe_key}.json"
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    try:
        q_enc = urllib.parse.quote(place_query)
        url = f"https://nominatim.openstreetmap.org/search?q={q_enc}&format=geojson&polygon_geojson=1&limit=1"
        req = urllib.request.Request(url, headers={"User-Agent": "PalajSmartSchoolTeacherApp/2.5 (education)"})
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("features"):
                with open(cache_file, "w", encoding="utf-8") as f:
                    json.dump(data, f)
                return data
    except Exception:
        pass
    return None

@st.cache_data(show_spinner=False)
def fetch_osm_point(place_query):
    os.makedirs("geo_cache", exist_ok=True)
    safe_key = re.sub(r"[^a-zA-Z0-9_]", "_", place_query.lower())[:50]
    cache_file = f"geo_cache/pt_{safe_key}.json"
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    try:
        q_enc = urllib.parse.quote(place_query)
        url = f"https://nominatim.openstreetmap.org/search?q={q_enc}&format=json&limit=1"
        req = urllib.request.Request(url, headers={"User-Agent": "PalajSmartSchoolTeacherApp/2.5 (education)"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            arr = json.loads(resp.read().decode("utf-8"))
            if arr:
                pt = {"lon": float(arr[0]["lon"]), "lat": float(arr[0]["lat"])}
                with open(cache_file, "w", encoding="utf-8") as f:
                    json.dump(pt, f)
                return pt
    except Exception:
        pass
    return None

@st.cache_data(show_spinner=False)
def load_real_geojson(kind="gujarat"):
    os.makedirs("geo_cache", exist_ok=True)
    if kind == "gujarat":
        local_path = "geo_cache/gujarat_real_districts.geojson"
        urls = [
            "https://raw.githubusercontent.com/geohacker/india/master/district/india_district.geojson",
            "https://raw.githubusercontent.com/datameet/maps/master/Districts/Census_2011/2011_Dist.geojson",
        ]
    elif kind == "world":
        local_path = "geo_cache/world_countries.geojson"
        urls = ["https://raw.githubusercontent.com/johan/world.geo.json/master/countries.geo.json"]
    else:
        local_path = "geo_cache/india_real_states.geojson"
        urls = [
            "https://raw.githubusercontent.com/geohacker/india/master/state/india_state.geojson",
            "https://raw.githubusercontent.com/Subhash9325/GeoJson-Data-of-Indian-States/master/Indian_States",
        ]

    if os.path.exists(local_path):
        try:
            with open(local_path, "r", encoding="utf-8") as f:
                cached = json.load(f)
                if cached.get("features"):
                    return cached
        except Exception:
            pass

    for u in urls:
        try:
            req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
                if kind == "gujarat":
                    guj_feats = []
                    for feat in raw.get("features", []):
                        props = feat.get("properties") or {}
                        st_val = str(props.get("NAME_1") or props.get("ST_NM") or props.get("state") or "").lower()
                        if "gujarat" in st_val:
                            guj_feats.append(feat)
                    if len(guj_feats) >= 20:
                        data = {"type": "FeatureCollection", "features": guj_feats}
                        with open(local_path, "w", encoding="utf-8") as f:
                            json.dump(data, f)
                        return data
                else:
                    if raw.get("features"):
                        with open(local_path, "w", encoding="utf-8") as f:
                            json.dump(raw, f)
                        return raw
        except Exception:
            continue
    return None

def _extract_polygons_from_geom(geom):
    gtype = geom.get("type")
    coords = geom.get("coordinates", [])
    polys = []
    if gtype == "Polygon":
        if coords:
            polys.append(coords[0])
    elif gtype == "MultiPolygon":
        for poly in coords:
            if poly:
                polys.append(poly[0])
    return polys

def _polygon_centroid(pts):
    if not pts:
        return (0, 0)
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return (sum(xs) / len(xs), sum(ys) / len(ys))

def _query_asks_only_subset(raw_query):
    q = (raw_query or "").lower()
    return any(w in q for w in ("ફક્ત", "માત્ર", "fakt", "matra", "only", "જિલ્લાનો", "જિલ્લાઓનો", "રાજ્યોનો"))

def render_textbook_map_png(spec, raw_query=""):
    if not HAS_MPL:
        return None
    font_path = get_pdf_font()
    fp_title = font_manager.FontProperties(fname=font_path, size=14, weight="bold") if font_path else None
    fp_sub = font_manager.FontProperties(fname=font_path, size=10.5, weight="bold") if font_path else None
    fp_lbl = font_manager.FontProperties(fname=font_path, size=8.5, weight="bold") if font_path else None
    fp_leg = font_manager.FontProperties(fname=font_path, size=8.8) if font_path else None
    fp_small = font_manager.FontProperties(fname=font_path, size=7.8, weight="bold") if font_path else None

    fig = plt.figure(figsize=(13.0, 8.4), dpi=200)
    fig.patch.set_facecolor("#F5F5F4")

    bg_ax = fig.add_axes([0, 0, 1, 1])
    bg_ax.set_xlim(0, 100)
    bg_ax.set_ylim(0, 100)
    bg_ax.axis("off")
    bg_ax.add_patch(patches.FancyBboxPatch((1.5, 2), 97, 96, boxstyle="round,pad=0.4", facecolor="#FAF8F5", edgecolor="#78716C", linewidth=1.8))
    bg_ax.text(50, 94.8, spec.get("header_top", "સામાજિક વિજ્ઞાન - નકશા પૂર્તિ"), ha="center", va="center", color="#1E293B", fontproperties=fp_title)
    bg_ax.text(50, 91.2, spec.get("title", "ભૌગોલિક / રાજકીય નકશો"), ha="center", va="center", color="#B91C1C", fontproperties=fp_sub)

    map_ax = fig.add_axes([0.035, 0.055, 0.72, 0.82])
    map_ax.set_facecolor("#E0F2FE")
    for spine in map_ax.spines.values():
        spine.set_edgecolor("#475569")
        spine.set_linewidth(1.4)
    map_ax.set_xticks([])
    map_ax.set_yticks([])

    region = str(spec.get("region", "gujarat")).lower()
    highlights = spec.get("highlights", [])
    hl_map = {str(h.get("place", "")).strip(): h for h in highlights if h.get("place")}
    only_selected = bool(spec.get("only_selected", False)) or (_query_asks_only_subset(raw_query) and len(hl_map) >= 1)

    if region == "local":
        search_en = str(spec.get("osm_query_en") or "Mehsana, Gujarat, India").strip()
        osm_geo = fetch_osm_real_boundary(search_en)
        sub_places = spec.get("sub_places_en") or []
        all_x, all_y = [], []

        if osm_geo and osm_geo.get("features"):
            feat = osm_geo["features"][0]
            polys = _extract_polygons_from_geom(feat.get("geometry") or {})
            for poly in polys:
                map_ax.add_patch(patches.Polygon(poly, closed=True, facecolor="#FEF9C3", edgecolor="#B91C1C", linewidth=2.2, alpha=0.95, joinstyle="round"))
                for px, py in poly:
                    all_x.append(px)
                    all_y.append(py)

        for idx_s, sp in enumerate(sub_places[:10]):
            en_q = str(sp.get("en", "")).strip()
            guj_lbl = str(sp.get("guj", "")).strip()
            if not en_q or not guj_lbl:
                continue
            sub_geo = fetch_osm_real_boundary(en_q)
            sub_polys = _extract_polygons_from_geom((sub_geo["features"][0].get("geometry") or {})) if (sub_geo and sub_geo.get("features")) else []
            if sub_polys:
                fc = PASTEL_PALETTE[idx_s % len(PASTEL_PALETTE)]
                biggest = max(sub_polys, key=len)
                for spoly in sub_polys:
                    map_ax.add_patch(patches.Polygon(spoly, closed=True, facecolor=fc, edgecolor="#1E293B", linewidth=1.1, alpha=0.92, joinstyle="round"))
                    for px, py in spoly:
                        all_x.append(px)
                        all_y.append(py)
                cx, cy = _polygon_centroid(biggest)
                map_ax.text(cx, cy, guj_lbl, ha="center", va="center", color="#0F172A", fontproperties=fp_small)
            else:
                pt = fetch_osm_point(en_q)
                if pt:
                    map_ax.plot(pt["lon"], pt["lat"], marker="^", markersize=8.5, color="#DC2626", markeredgecolor="#FFFFFF", markeredgewidth=1.2, zorder=6)
                    map_ax.text(pt["lon"], pt["lat"] + 0.015, guj_lbl, ha="center", va="bottom", color="#0F172A", fontproperties=fp_small, bbox=dict(boxstyle="round,pad=0.15", facecolor="#FFFFFF", edgecolor="#94A3B8", alpha=0.9), zorder=7)
                    all_x.append(pt["lon"])
                    all_y.append(pt["lat"])

        if all_x and all_y:
            dx = max((max(all_x) - min(all_x)) * 0.14, 0.06)
            dy = max((max(all_y) - min(all_y)) * 0.14, 0.06)
            map_ax.set_xlim(min(all_x) - dx, max(all_x) + dx)
            map_ax.set_ylim(min(all_y) - dy, max(all_y) + dy)
            map_ax.set_aspect("equal", adjustable="datalim")
        else:
            region = "gujarat"

    if region == "world":
        geo = load_real_geojson("world")
        if geo and geo.get("features"):
            all_x, all_y = [], []
            for idx_w, feat in enumerate(geo["features"]):
                props = feat.get("properties") or {}
                raw_name = str(props.get("name") or "").strip()
                is_india = "india" in raw_name.lower()
                matched_hl = next((v for k, v in hl_map.items() if k.lower() in raw_name.lower()), None)
                if only_selected and not matched_hl:
                    continue
                fc = "#EF4444" if is_india else (matched_hl.get("color", "#FDE047") if matched_hl else PASTEL_PALETTE[idx_w % len(PASTEL_PALETTE)])
                polys = _extract_polygons_from_geom(feat.get("geometry") or {})
                for poly in polys:
                    map_ax.add_patch(patches.Polygon(poly, closed=True, facecolor=fc, edgecolor="#334155", linewidth=0.8, alpha=0.95))
                    for px, py in poly:
                        all_x.append(px)
                        all_y.append(py)
                if (is_india or matched_hl) and polys:
                    cx, cy = _polygon_centroid(max(polys, key=len))
                    lbl = matched_hl.get("label") if matched_hl else "ભારત"
                    map_ax.text(cx, cy, lbl, ha="center", va="center", color="#0F172A", fontproperties=fp_lbl)
            if all_x and all_y:
                if only_selected:
                    dx, dy = max((max(all_x)-min(all_x))*0.15, 2.0), max((max(all_y)-min(all_y))*0.15, 2.0)
                    map_ax.set_xlim(min(all_x) - dx, max(all_x) + dx)
                    map_ax.set_ylim(min(all_y) - dy, max(all_y) + dy)
                else:
                    map_ax.set_xlim(-175, 180)
                    map_ax.set_ylim(-58, 84)
                map_ax.set_aspect("equal", adjustable="datalim")

    elif region == "india":
        geo = load_real_geojson("india")
        if geo and geo.get("features"):
            all_x, all_y = [], []
            for idx_st, feat in enumerate(geo["features"]):
                props = feat.get("properties") or {}
                raw_name = str(props.get("NAME_1") or props.get("ST_NM") or props.get("state") or "").strip()
                guj_name, zone = STATE_EN_TO_GUJ.get(raw_name.lower(), (raw_name, "central"))
                matched_hl = next((v for k, v in hl_map.items() if k in guj_name or guj_name in k or k.lower() in raw_name.lower()), None)
                if only_selected and not matched_hl:
                    continue
                fc = matched_hl.get("color", PASTEL_PALETTE[idx_st % len(PASTEL_PALETTE)]) if matched_hl else ZONE_COLORS.get(zone, "#E2E8F0")
                ec = "#B91C1C" if matched_hl else "#1E293B"
                lw = 2.0 if matched_hl else 0.9

                polys = _extract_polygons_from_geom(feat.get("geometry") or {})
                biggest = max(polys, key=len) if polys else []
                for poly in polys:
                    map_ax.add_patch(patches.Polygon(poly, closed=True, facecolor=fc, edgecolor=ec, linewidth=lw, alpha=0.96, joinstyle="round"))
                    for px, py in poly:
                        all_x.append(px)
                        all_y.append(py)
                if biggest:
                    cx, cy = _polygon_centroid(biggest)
                    map_ax.text(cx, cy, guj_name, ha="center", va="center", color="#0F172A", fontproperties=fp_small)
                    if matched_hl and matched_hl.get("label") and matched_hl.get("label") != guj_name:
                        map_ax.text(cx, cy - 0.9, f"▲ {matched_hl.get('label')[:16]}", ha="center", va="center", color="#991B1B", fontproperties=fp_lbl)
            if spec.get("show_rivers", False) and not only_selected:
                for r_name, pts in INDIA_RIVERS_GEO:
                    xs, ys = zip(*pts)
                    map_ax.plot(xs, ys, color="#0284C7", linewidth=2.4)
                    map_ax.text(xs[1], ys[1] + 0.5, r_name, ha="center", va="center", color="#0369A1", fontproperties=fp_lbl)
            if all_x and all_y:
                dx = max((max(all_x) - min(all_x)) * 0.14, 1.0)
                dy = max((max(all_y) - min(all_y)) * 0.14, 1.0)
                map_ax.set_xlim(min(all_x) - dx, max(all_x) + dx)
                map_ax.set_ylim(min(all_y) - dy, max(all_y) + dy)
                map_ax.set_aspect("equal", adjustable="datalim")
                if not only_selected:
                    map_ax.text(min(all_x) + 3.5, min(all_y) + 6.0, "અરબ સાગર", ha="center", va="center", color="#0369A1", fontproperties=fp_lbl)
                    map_ax.text(max(all_x) - 8.5, min(all_y) + 6.0, "બંગાળની ખાડી", ha="center", va="center", color="#0369A1", fontproperties=fp_lbl)

    elif region == "gujarat":
        geo = load_real_geojson("gujarat")
        if geo and geo.get("features"):
            all_x, all_y = [], []
            for idx_d, feat in enumerate(geo["features"]):
                props = feat.get("properties") or {}
                raw_dist = str(props.get("NAME_2") or props.get("DISTRICT") or props.get("dtname") or props.get("district") or "").strip()
                guj_name, zone = DISTRICT_EN_TO_GUJ.get(raw_dist.lower(), (raw_dist, "central"))
                matched_hl = next((v for k, v in hl_map.items() if k in guj_name or guj_name in k or k.lower() in raw_dist.lower()), None)

                if only_selected and not matched_hl:
                    continue

                fc = matched_hl.get("color", PASTEL_PALETTE[idx_d % len(PASTEL_PALETTE)]) if matched_hl else ZONE_COLORS.get(zone, "#E2E8F0")
                ec = "#B91C1C" if matched_hl else "#1E293B"
                lw = 2.2 if matched_hl else 0.95

                polys = _extract_polygons_from_geom(feat.get("geometry") or {})
                biggest = max(polys, key=len) if polys else []
                for poly in polys:
                    map_ax.add_patch(patches.Polygon(poly, closed=True, facecolor=fc, edgecolor=ec, linewidth=lw, alpha=0.96, joinstyle="round"))
                    for px, py in poly:
                        all_x.append(px)
                        all_y.append(py)
                if biggest:
                    cx, cy = _polygon_centroid(biggest)
                    map_ax.text(cx, cy, guj_name, ha="center", va="center", color="#0F172A", fontproperties=fp_lbl if only_selected else fp_small)
                    if matched_hl and matched_hl.get("label") and matched_hl.get("label") != guj_name:
                        map_ax.text(cx, cy - 0.18, f"▲ {matched_hl.get('label')[:16]}", ha="center", va="center", color="#991B1B", fontproperties=fp_small)

            if spec.get("show_rivers", False):
                for r_name, pts in GUJARAT_RIVERS_GEO:
                    xs, ys = zip(*pts)
                    if only_selected and all_x and all_y:
                        if not any((min(all_x) <= x <= max(all_x) and min(all_y) <= y <= max(all_y)) for x, y in pts):
                            continue
                    map_ax.plot(xs, ys, color="#0284C7", linewidth=2.6)
                    map_ax.text(xs[1], ys[1] + 0.10, r_name, ha="center", va="center", color="#0369A1", fontproperties=fp_lbl)

            if all_x and all_y:
                dx = max((max(all_x) - min(all_x)) * 0.14, 0.25)
                dy = max((max(all_y) - min(all_y)) * 0.14, 0.25)
                map_ax.set_xlim(min(all_x) - dx, max(all_x) + dx)
                map_ax.set_ylim(min(all_y) - dy, max(all_y) + dy)
                map_ax.set_aspect("equal", adjustable="datalim")
                if not only_selected:
                    map_ax.text(69.5, 22.65, "કચ્છનો અખાત", ha="center", va="center", color="#0369A1", fontproperties=fp_small)
                    map_ax.text(72.35, 21.45, "ખંભાતનો અખાત", ha="center", va="center", color="#0369A1", fontproperties=fp_small)
                    map_ax.text(70.2, 20.45, "અરબ સાગર", ha="center", va="center", color="#0369A1", fontproperties=fp_lbl)

    map_ax.text(0.95, 0.94, "ઉત્તર", transform=map_ax.transAxes, ha="center", va="center", color="#0F172A", fontproperties=fp_lbl)
    map_ax.annotate("", xy=(0.95, 0.91), xytext=(0.95, 0.80), xycoords="axes fraction", textcoords="axes fraction", arrowprops=dict(arrowstyle="->", lw=2.2, color="#0F172A"))

    bg_ax.add_patch(patches.FancyBboxPatch((77.2, 5.5), 20.0, 82.0, boxstyle="round,pad=0.35", facecolor="#FFFFFF", edgecolor="#94A3B8", linewidth=1.3))
    bg_ax.text(87.2, 84.8, "📌 સંજ્ઞા સૂચિ", ha="center", va="center", color="#1E3A8A", fontproperties=fp_sub)
    bg_ax.plot([78.8, 95.6], [82.4, 82.4], color="#CBD5E1", linewidth=1)

    default_legends = {
        "gujarat": [{"color": "#DCE775", "label": "કચ્છ પ્રદેશ"}, {"color": "#F8BBD0", "label": "ઉત્તર ગુજરાત"}, {"color": "#FFCC80", "label": "મધ્ય ગુજરાત"}, {"color": "#CE93D8", "label": "સૌરાષ્ટ્ર"}, {"color": "#80DEEA", "label": "દક્ષિણ ગુજરાત"}],
        "india": [{"color": "#F8BBD0", "label": "ઉત્તર ભારત"}, {"color": "#FFCC80", "label": "મધ્ય ભારત"}, {"color": "#DCE775", "label": "પશ્ચિમ ભારત"}, {"color": "#80DEEA", "label": "પૂર્વ ભારત"}, {"color": "#CE93D8", "label": "દક્ષિણ ભારત"}],
        "world": [{"color": "#EF4444", "label": "ભારત દેશ"}, {"color": "#FDE68A", "label": "વિશ્વના દેશો"}],
        "local": [{"color": "#FEF9C3", "label": "વિસ્તારની સરહદ"}, {"color": "#BAE6FD", "label": "તાલુકા / ગામો"}, {"color": "#DC2626", "label": "કિલ્લા / સ્થળો"}],
    }
    legend_items = spec.get("legend") or default_legends.get(region, default_legends["gujarat"])
    for idx_l, li in enumerate(legend_items[:9]):
        ly = 78.0 - idx_l * 7.8
        bg_ax.add_patch(patches.Rectangle((78.8, ly - 1.6), 3.4, 3.2, facecolor=li.get("color", "#FDE047"), edgecolor="#334155", linewidth=1))
        bg_ax.text(83.3, ly, str(li.get("label", ""))[:16], ha="left", va="center", color="#0F172A", fontproperties=fp_leg)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=200)
    plt.close(fig)
    return buf.getvalue()

# --- NANO BANANA FOR DRAWINGS ONLY ---
def generate_clean_drawing(query_text, api_keys):
    if HAS_GENAI and api_keys:
        for key in api_keys:
            client = get_cached_client(key)
            for nb_model in get_available_image_models_cached(key):
                try:
                    res = client.models.generate_content(
                        model=nb_model,
                        contents=[f"Colorful, child-friendly Indian school textbook illustration of {query_text}, pure white background, clean outlines"],
                        config=types.GenerateContentConfig(response_modalities=["IMAGE"])
                    )
                    for cand in getattr(res, "candidates", []) or []:
                        for part in getattr(cand.content, "parts", []) or []:
                            if getattr(part, "inline_data", None) and getattr(part.inline_data, "data", None):
                                return part.inline_data.data
                except Exception:
                    pass
    return None

# --- MATH & GEOMETRY SVG BUILDER ---
def build_math_fraction_svg(query_text):
    q = (query_text or "").translate(str.maketrans("૦૧૨૩૪૫૬૭૮૯", "0123456789")).lower()
    if "ત્રિકોણ" in q or "triangle" in q or "trikon" in q:
        return '<svg width="100%" viewBox="0 0 520 290" xmlns="http://www.w3.org/2000/svg" style="max-height:290px; display:block; margin:auto;"><rect width="520" height="290" rx="12" fill="#FFFFFF"/><text x="260" y="28" text-anchor="middle" font-size="17" font-weight="bold" fill="#1E3A8A">📐 ત્રિકોણની આકૃતિ અને તેના અંગો</text><polygon points="260,60 130,235 390,235" fill="#DBEAFE" stroke="#1D4ED8" stroke-width="3"/><text x="260" y="48" text-anchor="middle" font-size="14" font-weight="bold" fill="#DC2626">શિરોબિંદુ A</text><text x="105" y="258" text-anchor="middle" font-size="14" font-weight="bold" fill="#DC2626">શિરોબિંદુ B</text><text x="415" y="258" text-anchor="middle" font-size="14" font-weight="bold" fill="#DC2626">શિરોબિંદુ C</text><text x="260" y="258" text-anchor="middle" font-size="13" font-weight="bold" fill="#0F172A">પાયો BC (૩ બાજુ, ૩ ખૂણા)</text></svg>'
    if "ચોરસ" in q or "લંબચોરસ" in q or "square" in q or "rectangle" in q or "choras" in q:
        is_rect = "લંબચોરસ" in q or "rectangle" in q
        w = 240 if is_rect else 160
        x0 = 260 - w // 2
        return f'<svg width="100%" viewBox="0 0 520 290" xmlns="http://www.w3.org/2000/svg" style="max-height:290px; display:block; margin:auto;"><rect width="520" height="290" rx="12" fill="#FFFFFF"/><text x="260" y="28" text-anchor="middle" font-size="17" font-weight="bold" fill="#1E3A8A">📐 {"લંબચોરસ" if is_rect else "ચોરસ"} ની આકૃતિ</text><rect x="{x0}" y="68" width="{w}" height="155" fill="#DCFCE7" stroke="#15803D" stroke-width="3"/><text x="260" y="255" text-anchor="middle" font-size="13" font-weight="bold" fill="#15803D">દરેક ખૂણો ૯૦° (કાટખૂણો)</text></svg>'

    word_to_num = {"બે": 2, "2": 2, "ત્રણ": 3, "3": 3, "ચાર": 4, "4": 4, "પાંચ": 5, "5": 5, "છ": 6, "6": 6, "સાત": 7, "7": 7, "આઠ": 8, "8": 8}
    total_parts = 3
    for w, n in word_to_num.items():
        if re.search(rf"{w}\s*(?:ભાગ|સમાન ભાગ|ટુકડા|parts|bhag)", q):
            total_parts = n
            break
    frac_match = re.search(r"(\d+)\s*/\s*(\d+)", q)
    num, den = (int(frac_match.group(1)), int(frac_match.group(2))) if frac_match else (1, total_parts)
    if den == 0:
        den = total_parts

    cx, cy, r = 160, 165, 105
    palette = ["#93C5FD", "#86EFAC", "#FDE047", "#FDBA74", "#F9A8D4", "#C4B5FD", "#5EEAD4", "#FCA5A5"]
    left_slices, right_slices = [], []
    for i in range(total_parts):
        a1, a2 = -90 + (360.0 / total_parts) * i, -90 + (360.0 / total_parts) * (i + 1)
        x1, y1, x2, y2 = cx + r * math.cos(math.radians(a1)), cy + r * math.sin(math.radians(a1)), cx + r * math.cos(math.radians(a2)), cy + r * math.sin(math.radians(a2))
        left_slices.append(f'<path d="M {cx},{cy} L {x1:.1f},{y1:.1f} A {r},{r} 0 {1 if (a2-a1)>180 else 0},1 {x2:.1f},{y2:.1f} Z" fill="{palette[i % len(palette)]}" stroke="#1E293B" stroke-width="2.2"/>')
        mid_a = math.radians((a1 + a2) / 2)
        left_slices.append(f'<text x="{cx + (r * 0.58) * math.cos(mid_a):.1f}" y="{cy + (r * 0.58) * math.sin(mid_a):.1f}" text-anchor="middle" dominant-baseline="middle" font-size="14" font-weight="bold" fill="#0F172A">ભાગ {i+1}</text>')

    cx2, cy2, disp_den, disp_num = 430, 165, max(den, 1), min(num, max(den, 1))
    for i in range(disp_den):
        a1, a2 = -90 + (360.0 / disp_den) * i, -90 + (360.0 / disp_den) * (i + 1)
        x1, y1, x2, y2 = cx2 + r * math.cos(math.radians(a1)), cy2 + r * math.sin(math.radians(a1)), cx2 + r * math.cos(math.radians(a2)), cy2 + r * math.sin(math.radians(a2))
        fill_c, txt_c = ("#2563EB", "#FFFFFF") if i < disp_num else ("#F1F5F9", "#334155")
        right_slices.append(f'<path d="M {cx2},{cy2} L {x1:.1f},{y1:.1f} A {r},{r} 0 {1 if (a2-a1)>180 else 0},1 {x2:.1f},{y2:.1f} Z" fill="{fill_c}" stroke="#1E293B" stroke-width="2.2"/>' if disp_den > 1 else f'<circle cx="{cx2}" cy="{cy2}" r="{r}" fill="{fill_c}" stroke="#1E293B" stroke-width="2.2"/>')
        mid_a = math.radians((a1 + a2) / 2)
        right_slices.append(f'<text x="{cx2 + (r * 0.55) * math.cos(mid_a):.1f}" y="{cy2 + (r * 0.55) * math.sin(mid_a):.1f}" text-anchor="middle" dominant-baseline="middle" font-size="14" font-weight="bold" fill="{txt_c}">1/{disp_den}</text>')

    return f'<svg width="100%" viewBox="0 0 600 330" xmlns="http://www.w3.org/2000/svg" style="max-height:330px; display:block; margin:auto;"><rect width="600" height="330" rx="12" fill="#FFFFFF"/><text x="300" y="28" text-anchor="middle" font-size="17" font-weight="bold" fill="#1E3A8A">📐 ગણિત આકૃતિ: વર્તુળના {total_parts} ભાગ અને {num}/{den} અપૂર્ણાંક</text>{"".join(left_slices)}<text x="{cx}" y="295" text-anchor="middle" font-size="14" font-weight="bold" fill="#0F172A">૧. વર્તુળના {total_parts} સમાન ભાગ</text>{"".join(right_slices)}<text x="{cx2}" y="295" text-anchor="middle" font-size="14" font-weight="bold" fill="#1D4ED8">૨. રંગીન ભાગ = {num}/{den}</text></svg>'

# --- DETECTION HELPERS ---
_GUJ_DIGIT_MAP = str.maketrans("૦૧૨૩૪૫૬૭૮૯", "0123456789")
_SUBJECT_LABELS = {"gujarati": "ગુજરાતી", "sanskrit": "સંસ્કૃત", "math": "ગણિત", "science": "વિજ્ઞાન", "social_science": "સામાજિક વિજ્ઞાન", "environment": "પર્યાવરણ", "english": "અંગ્રેજી", "hindi": "હિન્દી"}
_EXPLICIT_SUBJECTS = {
    "social_science": ["સામાજિક વિજ્ઞાન", "સામાજિક", "social", "ઇતિહાસ", "ભૂગોળ", "નકશો", "નક્શો", "નકશા", "નકશાપૂર્તિ", "naksho", "naksha", "જિલ્લા", "તાલુકા", "ગુજરાત", "મગધ", "કિલ્લો", "કિલ્લા", "પ્રદેશ", "ઉદ્યોગ", "ખેત ઉત્પાદન", "પાક"],
    "math": ["ગણિત", "math", "ભૂમિતિ", "અપૂર્ણાંક", "વર્તુળ", "ત્રિકોણ", "ચોરસ"],
    "science": ["વિજ્ઞાન", "science", "પ્રકાશસંશ્લેષણ", "કોષ", "વિદ્યુત", "ચુંબક"],
    "environment": ["પર્યાવરણ", "આસપાસ", "evs"],
    "gujarati": ["ગુજરાતી", "gujarati", "કલશોર", "કેકારવ", "કુહૂ", "પલાશ"],
    "sanskrit": ["સંસ્કૃત", "sanskrit"],
    "english": ["અંગ્રેજી", "english"],
    "hindi": ["હિન્દી", "hindi"],
}

def wants_map(text):
    t = (text or "").lower()
    return any(kw in t for kw in (
        "નકશો", "નક્શો", "નકશા", "નક્શા", "નકશાપૂર્તિ", "naksho", "naksha", "map",
        "સંજ્ઞા વડે", "નકશામાં દર્શાવો", "કિલ્લા", "મગધ", "પ્રદેશો",
        "રાજકીય", "ભૌગોલિક", "ગામનો", "gamno", "gamda", "ખેત ઉત્પાદન", "ઉદ્યોગો", "નદીઓ", "મતદાર", "વસ્તી ગણતરી", "blo"
    ))

def wants_math_geometry_visual(text):
    t = (text or "").lower()
    return any(k in t for k in ("વર્તુળ", "circle", "અપૂર્ણાંક", "ત્રિકોણ", "triangle", "ચોરસ", "લંબચોરસ", "square", "rectangle")) and any(w in t for w in ("ભાગ", "આકૃતિ", "દોરો", "બતાવો", "દર્શાવો", "1/", "2/", "3/", "ચિત્ર", "chitra", "chira", "akruti"))

def wants_any_drawing_or_diagram(text):
    t = (text or "").lower()
    return any(kw in t for kw in (
        "આકૃતિ", "akruti", "aakruti", "નામનિર્દેશ", "ચિત્ર", "chitra", "chira", "chitran",
        "દોરો", "દોરી", "doro", "dori", "બનાવો", "banavo", "banavi",
        "diagram", "draw", "drawing", "sketch", "image", "picture", "photo", "painting",
        "બાળક", "balak", "ગાય", "gay", "cow", "ફૂલ", "ful", "પ્રાણી", "પક્ષી", "કોષ", "પ્રકાશસંશ્લેષણ", "સફરજન", "કેળું", "દ્રાક્ષ"
    ))

def needs_textbook_vision(text):
    t = (text or "").lower()
    return any(k in t for k in ("પાઠ", "પ્રકરણ", "સ્વાધ્યાય", "સારાંશ", "કવિતા", "વાર્તા", "પુસ્તક", "chapter", "lesson", "exercise", "mcq"))

def extract_grade(text):
    t = (text or "").translate(_GUJ_DIGIT_MAP).lower()
    for p in [r"ધોરણ\s*[-:.]?\s*([3-8])", r"ધો\.?\s*[-:.]?\s*([3-8])", r"std\.?\s*[-:.]?\s*([3-8])", r"grade\s*[-:.]?\s*([3-8])"]:
        if m := re.search(p, t):
            return int(m.group(1))
    return None

def extract_subject(text):
    t = (text or "").lower()
    for code, keywords in _EXPLICIT_SUBJECTS.items():
        if any(kw.lower() in t for kw in keywords):
            return code
    return None

def resolve_grade_subject_and_pdfs(current_query, syllabus):
    grade, subject = extract_grade(current_query), extract_subject(current_query)
    if not grade or not subject:
        return grade, subject, []
    matched = []
    for _label, info in ((syllabus.get(f"ધોરણ {grade}") or {}).get("subjects", {})).items():
        if info.get("code") == subject:
            for p in info.get("local_pdfs") or []:
                path = p.replace("\\", "/")
                if os.path.exists(path) and path not in matched:
                    matched.append(path)
            break
    return grade, subject, matched[:1]

@st.cache_data(show_spinner=False)
def render_pdf_pages_as_jpeg_bytes(abspath, mtime, page_indices):
    images = []
    try:
        import fitz
        with fitz.open(abspath) as doc:
            for idx in page_indices:
                if 0 <= idx < len(doc):
                    images.append(doc[idx].get_pixmap(dpi=100, alpha=False).tobytes("jpeg", jpg_quality=70))
    except Exception:
        pass
    return images

def build_vision_pdf_parts(pdf_path):
    try:
        abspath = os.path.abspath(pdf_path)
        mtime = os.path.getmtime(abspath)
        import fitz
        with fitz.open(abspath) as doc:
            total = len(doc)
        return [types.Part.from_bytes(data=b, mime_type="image/jpeg") for b in render_pdf_pages_as_jpeg_bytes(abspath, mtime, tuple(range(min(6, total))))]
    except Exception:
        return []

def detect_default_map_spec(query_text):
    q = (query_text or "").lower()
    if any(w in q for w in ("વિશ્વ", "world", "દુનિયા", "ખંડો", "મહાસાગર")):
        return {"region": "world", "header_top": "સામાજિક વિજ્ઞાન - વિશ્વ નકશા પૂર્તિ", "title": "વિશ્વનો ભૌગોલિક અને રાજકીય નકશો"}
    if any(w in q for w in ("ભારત", "india", "મગધ", "દિલ્હી", "મહારાષ્ટ્ર", "રાજસ્થાન", "પંજાબ", "બિહાર", "ગંગા", "હિમાલય")):
        show_riv = any(w in q for w in ("નદી", "nadi", "river", "ગંગા", "યમુના", "ગોદાવરી"))
        return {"region": "india", "header_top": "સામાજિક વિજ્ઞાન - ભારત નકશા પૂર્તિ", "title": "ભારતનો રાજકીય અને ભૌગોલિક નકશો", "show_rivers": show_riv}
    show_riv = any(w in q for w in ("નદી", "nadi", "river", "નર્મદા", "તાપી", "સાબરમતી"))
    return {"region": "gujarat", "header_top": "સામાજિક વિજ્ઞાન - નકશા પૂર્તિ", "title": "ગુજરાતનો રાજકીય નકશો", "show_rivers": show_riv}

def extract_or_build_map_bytes(content, is_map_query=False, raw_query=""):
    map_img_bytes = None
    clean_text = content
    if "```map_json" in clean_text:
        m = re.search(r"```map_json\s*([\s\S]*?)```", clean_text)
        if m:
            try:
                spec = json.loads(m.group(1).strip())
                if spec.get("region") in ("village", "blo_village"):
                    spec["region"] = "local"
                map_img_bytes = render_textbook_map_png(spec, raw_query=raw_query)
            except Exception:
                map_img_bytes = render_textbook_map_png(detect_default_map_spec(raw_query), raw_query=raw_query)
        clean_text = re.sub(r"```map_json[\s\S]*?```", "", clean_text)
    if is_map_query and not map_img_bytes:
        map_img_bytes = render_textbook_map_png(detect_default_map_spec(raw_query), raw_query=raw_query)
    clean_text = re.sub(r"```(?!svg|xml|html)[a-zA-Z]*\n[\s\S]*?```", "", clean_text)
    return map_img_bytes, clean_text

def render_message_with_visuals(content, image_bytes=None, msg_idx=0, math_svg=None, is_map_query=False, raw_query="", cached_map_bytes=None):
    map_img_bytes = cached_map_bytes
    clean_text = content
    if map_img_bytes is None and ("```map_json" in content or is_map_query):
        map_img_bytes, clean_text = extract_or_build_map_bytes(content, is_map_query=is_map_query, raw_query=raw_query)
    else:
        clean_text = re.sub(r"```map_json[\s\S]*?```", "", clean_text)
        clean_text = re.sub(r"```(?!svg|xml|html)[a-zA-Z]*\n[\s\S]*?```", "", clean_text)

    final_img = map_img_bytes or (image_bytes if not is_map_query else None)
    if final_img:
        cap = "🗺️ પાઠ્યપુસ્તક શૈલીનો અસલી ભૌગોલિક સરહદો સાથેનો નકશો" if map_img_bytes else "🎨 AI દ્વારા તૈયાર કરેલ ચિત્ર / આકૃતિ"
        st.image(final_img, caption=cap, use_container_width=True)
        _ = st.download_button(
            "⬇️ નકશો / ચિત્ર ડાઉનલોડ કરો (PNG)",
            data=final_img,
            file_name=f"palaj_{'map' if map_img_bytes else 'art'}_{msg_idx}.png",
            mime="image/png",
            key=f"dl_img_{msg_idx}"
        )

    if math_svg and not final_img:
        components.html(f'<div style="background:#FFFFFF; border-radius:12px; padding:8px; text-align:center; border:2px solid #93C5FD;">{math_svg}</div>', height=330, scrolling=False)

    clean = re.sub(r"```(?:svg|xml|html)?\s*(<svg[\s\S]*?</svg>)\s*```", r"\1", clean_text, flags=re.IGNORECASE)
    if "<svg" in clean.lower() and "</svg>" in clean.lower():
        for part in re.split(r"(<svg[\s\S]*?</svg>)", clean, flags=re.IGNORECASE):
            if part.strip().lower().startswith("<svg"):
                if not final_img and not math_svg:
                    components.html(f'<div style="background:#FFFFFF; border-radius:12px; padding:8px; text-align:center; border:2px solid #93C5FD;">{part}</div>', height=350, scrolling=False)
            elif part.strip():
                st.markdown(part)
    else:
        st.markdown(clean)

syllabus_data = load_syllabus()

# --- ZERO-HORIZONTAL-SCROLL & SIDEBAR-AWARE CSS ---
st.markdown("""
<style>
html, body, [data-testid="stAppViewContainer"], .main {
    overflow-x: hidden !important;
    max-width: 100% !important;
}
.block-container {
    max-width: 820px !important;
    width: 100% !important;
    box-sizing: border-box !important;
    padding-top: 2.2rem !important;
    padding-bottom: 6.5rem !important;
    padding-left: 0.75rem !important;
    padding-right: 0.75rem !important;
}
.slim-header {
    background: linear-gradient(135deg, #1E3A8A 0%, #2563EB 55%, #0284C7 100%);
    color: #FFFFFF;
    padding: 12px 14px;
    border-radius: 14px;
    text-align: center;
    font-size: 1.05rem;
    font-weight: 700;
    box-shadow: 0 4px 12px rgba(37, 99, 235, 0.22);
    border: 1px solid rgba(255, 255, 255, 0.2);
    margin-top: 4px;
    margin-bottom: 14px;
    width: 100%;
    box-sizing: border-box;
}
.book-badge {
    display: inline-block;
    background: #DBEAFE;
    color: #1E3A8A;
    border: 1px solid #93C5FD;
    padding: 4px 12px;
    border-radius: 999px;
    font-size: 0.82rem;
    font-weight: 600;
    margin-bottom: 8px;
}

/* Bottom Bar: Respects Sidebar on Desktop & Fits 100% on Mobile */
[data-testid="stBottom"] > div {
    max-width: 820px !important;
    width: 100% !important;
    margin: 0 auto !important;
    padding: 6px 10px !important;
    box-sizing: border-box !important;
}
[data-testid="stBottom"] [data-testid="stHorizontalBlock"] {
    display: flex !important;
    flex-direction: row !important;
    flex-wrap: nowrap !important;
    align-items: flex-end !important;
    gap: 6px !important;
    width: 100% !important;
}
[data-testid="stBottom"] [data-testid="stHorizontalBlock"] > [data-testid="column"]:nth-child(1),
[data-testid="stBottom"] [data-testid="stHorizontalBlock"] > [data-testid="column"]:nth-child(3),
[data-testid="stBottom"] [data-testid="stHorizontalBlock"] > [data-testid="column"]:nth-child(4) {
    flex: 0 0 42px !important;
    width: 42px !important;
    min-width: 42px !important;
    max-width: 42px !important;
}
[data-testid="stBottom"] [data-testid="stHorizontalBlock"] > [data-testid="column"]:nth-child(2) {
    flex: 1 1 auto !important;
    min-width: 0 !important;
}
[data-testid="stBottom"] textarea {
    min-height: 44px !important;
    max-height: 140px !important;
    overflow-y: auto !important;
    font-size: 15px !important;
    line-height: 1.35 !important;
    border-radius: 12px !important;
    padding: 9px 10px !important;
    width: 100% !important;
    box-sizing: border-box !important;
}
[data-testid="stBottom"] button {
    width: 42px !important;
    min-width: 42px !important;
    max-width: 42px !important;
    height: 44px !important;
    min-height: 44px !important;
    padding: 0 !important;
    font-size: 16px !important;
    border-radius: 10px !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
}
[data-testid="stBottom"] [data-testid="stPopover"] > div > button svg {
    display: none !important;
}
@media (max-width: 640px) {
    .block-container {
        padding-top: 1.5rem !important;
        padding-left: 0.45rem !important;
        padding-right: 0.45rem !important;
    }
    .slim-header {
        font-size: 0.92rem !important;
        padding: 10px 8px !important;
    }
}
</style>
""", unsafe_allow_html=True)

defaults = {
    "messages": [],
    "chat_sessions": [],
    "active_session_idx": None,
    "mcq_questions": None,
    "mcq_user_answers": {},
    "mcq_checked": False,
    "draft_text": "",
    "mic_open": False,
    "audio_counter": 0,
    "input_version": 0,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

def sync_current_session():
    if not st.session_state.messages:
        return
    first_q = next((m["content"].strip() for m in st.session_state.messages if m["role"] == "user" and m["content"].strip()), "નવી ચર્ચા")
    title = (first_q[:38] + "...") if len(first_q) > 38 else first_q
    idx = st.session_state.active_session_idx
    if idx is not None and 0 <= idx < len(st.session_state.chat_sessions):
        st.session_state.chat_sessions[idx] = {"title": title, "messages": list(st.session_state.messages)}
    else:
        st.session_state.chat_sessions.insert(0, {"title": title, "messages": list(st.session_state.messages)})
        st.session_state.active_session_idx = 0

# --- SIDEBAR: CHAT HISTORY WITH REAL SENTENCE TITLES + PDF DOWNLOAD ---
with st.sidebar:
    st.markdown("### 🎓 સ્માર્ટ AI શિક્ષક")
    raw_keys = st.secrets.get("GEMINI_API_KEYS") or os.environ.get("GEMINI_API_KEYS") or st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY") or ""
    api_keys = [k.strip().strip("\"'") for k in str(raw_keys).split(",") if k.strip()]
    model_choice = st.selectbox("🤖 AI મોડેલ:", ACTIVE_MODELS)

    quick_action = None
    c1, c2 = st.columns(2)
    if c1.button("📖 સારાંશ", use_container_width=True): quick_action = "summary"
    if c1.button("📝 MCQ ટેસ્ટ", use_container_width=True): quick_action = "mcq"
    if c2.button("📝 સ્વાધ્યાય", use_container_width=True): quick_action = "exercise"
    if c2.button("💡 ઉદાહરણ", use_container_width=True): quick_action = "easy_example"

    st.divider()
    if st.button("➕ નવી ચેટ (New Chat)", use_container_width=True):
        sync_current_session()
        st.session_state.messages = []
        st.session_state.active_session_idx = None
        st.session_state.mcq_questions = None
        st.session_state.mcq_user_answers = {}
        st.session_state.mcq_checked = False
        st.session_state.draft_text = ""
        st.session_state.input_version += 1
        st.rerun()

    if st.session_state.chat_sessions:
        st.markdown("#### 📜 ચેટ ઇતિહાસ")
        for s_idx, sess in enumerate(st.session_state.chat_sessions[:12]):
            if st.button(f"💬 {sess['title']}", key=f"hist_sess_{s_idx}", use_container_width=True):
                sync_current_session()
                st.session_state.messages = list(sess["messages"])
                st.session_state.active_session_idx = s_idx
                st.session_state.mcq_questions = None
                st.session_state.mcq_checked = False
                st.rerun()

    if st.session_state.messages:
        st.divider()
        _ = st.download_button(
            "📄 PDF નોટ્સ (નકશા/ચાર્ટ સહિત)",
            data=build_pdf_bytes(st.session_state.messages),
            file_name="palaj_classroom_notes.pdf",
            mime="application/pdf",
            use_container_width=True
        )

st.markdown('<div class="slim-header">📚 Standard 3 to 8 Smart AI Palaj Teacher</div>', unsafe_allow_html=True)

# --- PERSISTENT BOTTOM INPUT BAR ---
attached_file = st.session_state.get("bottom_uploader") or st.session_state.get("bottom_camera")
with getattr(st, "bottom", st.container()):
    col_plus, col_in, col_mic, col_send = st.columns([1, 8, 1, 1], vertical_alignment="bottom")
    with col_plus:
        with st.popover("➕"):
            _ = st.file_uploader("📁 ગેલેરી / PDF પસંદ કરો", key="bottom_uploader")
            _ = st.camera_input("📸 કેમેરાથી ફોટો પાડો", key="bottom_camera")
    with col_in:
        user_text = st.text_area(
            "પ્રશ્ન...",
            value=st.session_state.draft_text,
            key=f"chat_box_{st.session_state.input_version}",
            height=46,
            placeholder="ASK PALAJ TEACHER",
            label_visibility="collapsed"
        )
        st.session_state.draft_text = user_text
    with col_mic:
        if st.button("🎤", key="real_mic_btn", help="બોલીને લખો"):
            st.session_state.mic_open = not st.session_state.mic_open
            st.rerun()
    with col_send:
        send_clicked = st.button("➤", type="primary", key="real_send_btn", help="મોકલો")

if send_clicked and (user_text.strip() or attached_file):
    st.session_state.messages.append({"role": "user", "content": user_text.strip() or "[કેમેરા / ફાઈલ સંલગ્ન છે]"})
    sync_current_session()
    st.session_state.draft_text = ""
    st.session_state.input_version += 1
    st.rerun()

if quick_action:
    prompts = {"summary": "છેલ્લી ચર્ચા મુજબના પાઠનો મુદ્દાસર સારાંશ આપો.", "exercise": "છેલ્લી ચર્ચા મુજબના પાઠના સ્વાધ્યાયના પ્રશ્નો અને જવાબો આપો.", "mcq": "છેલ્લી ચર્ચા મુજબ ૫ MCQ બનાવો. ફોર્મેટ:\nપ્રશ્ન 1: પ્રશ્ન?\nA. ...\nB. ...\nC. ...\nD. ...\nસાચો જવાબ: B\nસમજૂતી: ...", "easy_example": "છેલ્લી ચર્ચા મુજબના વિષયના સરળ ઉદાહરણો આપો."}
    if quick_action == "mcq":
        st.session_state.mcq_questions = None
        st.session_state.mcq_user_answers = {}
        st.session_state.mcq_checked = False
    st.session_state.messages.append({"role": "user", "content": prompts[quick_action]})
    sync_current_session()

for idx_m, m in enumerate(st.session_state.messages):
    with st.chat_message(m["role"]):
        render_message_with_visuals(
            m["content"],
            m.get("image_bytes"),
            msg_idx=idx_m,
            math_svg=m.get("math_svg"),
            is_map_query=m.get("is_map_query", False),
            raw_query=m.get("raw_query", ""),
            cached_map_bytes=m.get("map_bytes")
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
            spoken, _ = transcribe_gujarati(audio_val, api_keys, preferred_model=model_choice)
            st.session_state.audio_counter += 1
            st.session_state.mic_open = False
            if spoken:
                st.session_state.draft_text = f"{st.session_state.draft_text} {spoken}".strip()
                st.session_state.input_version += 1
            st.rerun()

if attached_file:
    with st.container(border=True):
        c_img, c_txt, c_rm = st.columns([1, 6, 1])
        try:
            c_img.image(Image.open(io.BytesIO(attached_file.getvalue())), width=45)
        except Exception:
            c_img.markdown("📎")
        c_txt.caption(f"📎 સંલગ્ન ફાઈલ / કેમેરા ફોટો: {getattr(attached_file, 'name', 'Camera Photo')}")
        if c_rm.button("❌", key="rm_att_btn"):
            if "bottom_uploader" in st.session_state:
                del st.session_state["bottom_uploader"]
            if "bottom_camera" in st.session_state:
                del st.session_state["bottom_camera"]
            st.rerun()

# --- GENERATE ASSISTANT RESPONSE ---
if st.session_state.messages and st.session_state.messages[-1]["role"] == "user":
    clean_q = st.session_state.messages[-1]["content"].strip()
    with st.chat_message("assistant"):
        if not HAS_GENAI or not api_keys:
            st.error("⚠️ Secrets માં GEMINI_API_KEY દાખલ કરો.")
        else:
            user_att_parts = []
            att = st.session_state.get("bottom_uploader") or st.session_state.get("bottom_camera")
            if att:
                fb = att.getvalue()
                if getattr(att, "type", "") == "application/pdf":
                    user_att_parts.append(types.Part.from_bytes(data=fb, mime_type="application/pdf"))
                else:
                    user_att_parts.append(Image.open(io.BytesIO(fb)))
            if "bottom_uploader" in st.session_state:
                del st.session_state["bottom_uploader"]
            if "bottom_camera" in st.session_state:
                del st.session_state["bottom_camera"]

            grade, subject, local_pdf_paths = resolve_grade_subject_and_pdfs(clean_q, syllabus_data)
            is_map_q = wants_map(clean_q)
            math_svg_code = build_math_fraction_svg(clean_q) if (wants_math_geometry_visual(clean_q) and not is_map_q) else None
            is_drawing_q = wants_any_drawing_or_diagram(clean_q) and not is_map_q and not math_svg_code

            if is_map_q:
                st.markdown('<div class="book-badge">🗺️ પાઠ્યપુસ્તક શૈલીનો અસલી ભૌગોલિક સરહદો સાથેનો નકશો</div>', unsafe_allow_html=True)
            elif grade and subject and local_pdf_paths:
                st.markdown(f'<div class="book-badge">📖 ધોરણ {grade} | {_SUBJECT_LABELS.get(subject, subject)}</div>', unsafe_allow_html=True)

            recent_hist = "\n".join(f"{'વિદ્યાર્થી' if m['role']=='user' else 'શિક્ષક'}: {m['content']}" for m in st.session_state.messages[:-1][-3:])
            book_page_parts = build_vision_pdf_parts(local_pdf_paths[0]) if (local_pdf_paths and needs_textbook_vision(clean_q)) else []

            generated_img_bytes = generate_clean_drawing(clean_q, api_keys) if is_drawing_q else None

            visual_instruction = ""
            if is_map_q:
                visual_instruction = (
                    "\n**મહત્વની સૂચના:** પ્રશ્ન મુજબ સાચો ```map_json બ્લોક ફરજિયાત આપો:\n"
                    "- જો વપરાશકર્તાએ **'ફક્ત / માત્ર / only' અમુક જિલ્લા કે રાજ્યો** (દા.ત. ફક્ત મહેસાણા, બનાસકાંઠા, પાટણ અને સુરેન્દ્રનગર) પૂછ્યા હોય, તો `\"only_selected\": true` રાખો અને `\"highlights\"` માં ફક્ત તે જ જિલ્લાઓ/રાજ્યોના ગુજરાતી નામ આપો — જેથી નકશો આખા ગુજરાતને બદલે ફક્ત તે પસંદ કરેલા જિલ્લાઓ પર જ ઝૂમ થઈને દોરાય!\n"
                    "- જો **સમગ્ર ગુજરાત** (૩૩ જિલ્લા, કિલ્લાઓ, નદીઓ, પાક) પૂછ્યું હોય તો `\"region\": \"gujarat\", \"only_selected\": false` રાખો.\n"
                    "- જો **ભારત** (રાજ્યો, નદીઓ, મગધ, પાક, કિલ્લાઓ) પૂછ્યું હોય તો `\"region\": \"india\"` રાખો.\n"
                    "- જો **વિશ્વ** (ખંડો, દેશો) પૂછ્યું હોય તો `\"region\": \"world\"` રાખો.\n"
                    "- જો **કોઈ એક જિલ્લો, તાલુકો કે ગામ** (જેમ કે જૂનાગઢ જિલ્લો, મહેસાણા તાલુકો, પાલજ) પૂછ્યું હોય તો `\"region\": \"local\"` રાખો, `\"osm_query_en\"` માં અંગ્રેજી નામ અને `\"sub_places_en\"` માં અંદરના ગામો/કિલ્લા/સ્થળો આપો.\n"
                    "```map_json\n"
                    '{"region": "gujarat", "only_selected": false, "header_top": "સામાજિક વિજ્ઞાન - નકશા પૂર્તિ", "title": "નકશાનું શીર્ષક", "show_rivers": false, "highlights": [{"place": "જૂનાગઢ", "label": "ઉપરકોટ કિલ્લો", "color": "#FDE047"}], "legend": [{"color": "#FDE047", "label": "ઉપરકોટ કિલ્લો"}]}\n'
                    "```\nઅને નીચે પ્રશ્નમાં પૂછેલા સ્થળો/કિલ્લાઓની મુદ્દાસર વિગતવાર સમજૂતી આપો."
                )
            elif is_drawing_q and generated_img_bytes:
                visual_instruction = (
                    "\n**મહત્વની સૂચના:** સિસ્ટમ દ્વારા ઉપર રંગીન ચિત્ર પહેલેથી જ દર્શાવવામાં આવ્યું છે! "
                    "સીધો જ આ ચિત્ર વિશે વિદ્યાર્થીઓને ગમે તેવો સરળ અને મુદ્દાસર પરિચય આપો."
                )
            elif is_drawing_q and not generated_img_bytes:
                visual_instruction = (
                    '\n**મહત્વની સૂચના:** તમારે જવાબમાં સૌથી પહેલા એકદમ સુંદર, રંગીન અને વિગતવાર `<svg width="520" height="350" viewBox="0 0 520 350" xmlns="[http://www.w3.org/2000/svg](http://www.w3.org/2000/svg)"><rect width="520" height="350" fill="#FFFFFF"/>...</svg>` ચિત્ર/આકૃતિ દોરવી જ પડશે. '
                    'ક્યારેય "હું ચિત્ર દોરી શકતો નથી" એવું ન લખો અને ASCII art ન બનાવો.'
                )

            sys_prompt = f"તમે ધોરણ 3 થી 8 ના વિદ્યાર્થીઓ અને શિક્ષકો માટેના ઝડપી અને નિષ્ણાત AI સહાયક છો. જવાબ શુદ્ધ ગુજરાતીમાં, ટૂંકમાં અને મુદ્દાસર આપો.{visual_instruction}"
            prompt_text = f"{sys_prompt}\n\n{recent_hist}\nપ્રશ્ન: {clean_q}"

            placeholder = st.empty()
            placeholder.markdown("⚡ *જવાબ તૈયાર થઈ રહ્યો છે...*")
            answer_text, success, last_err = "", False, None

            for key in api_keys:
                client = get_cached_client(key)
                for mod in get_available_models_cached(key, model_choice):
                    try:
                        temp = ""
                        for chunk in client.models.generate_content_stream(model=mod, contents=book_page_parts + user_att_parts + [prompt_text]):
                            if chunk.text:
                                temp += chunk.text
                                if "```map_json" not in temp and "<svg" not in temp.lower():
                                    placeholder.markdown(temp + "▌")
                        if temp.strip():
                            placeholder.empty()
                            computed_map_bytes, _ = extract_or_build_map_bytes(temp, is_map_query=is_map_q, raw_query=clean_q) if (is_map_q or "```map_json" in temp) else (None, temp)
                            render_message_with_visuals(
                                temp,
                                generated_img_bytes,
                                msg_idx=len(st.session_state.messages),
                                math_svg=math_svg_code,
                                is_map_query=is_map_q,
                                raw_query=clean_q,
                                cached_map_bytes=computed_map_bytes
                            )
                            answer_text, success = temp, True
                            break
                    except Exception as e:
                        last_err = e
                        if any(x in str(e) for x in ("429", "RESOURCE_EXHAUSTED", "API_KEY_INVALID")):
                            break
                if success:
                    break

            if success:
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": answer_text,
                    "map_bytes": computed_map_bytes,
                    "image_bytes": generated_img_bytes,
                    "math_svg": math_svg_code,
                    "is_map_query": is_map_q,
                    "raw_query": clean_q
                })
                sync_current_session()
                if quick_action == "mcq" and st.session_state.mcq_questions is None:
                    if parsed := parse_mcq(answer_text):
                        st.session_state.mcq_questions = parsed
                    st.rerun()
            else:
                placeholder.empty()
                st.error(f"❌ {format_friendly_error(last_err)}")