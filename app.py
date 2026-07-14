import streamlit as st
import io
import math
import base64
from fontTools.ttLib import TTFont
from fontTools.pens.basePen import BasePen
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString

# --- 0. BRANDING & PREVIEW ENGINE ---
def inject_pro_cleaner():
    st.markdown("""
    <style>
    [data-testid="stHeader"] { display: none !important; }
    footer { visibility: hidden !important; }
    #MainMenu { visibility: hidden !important; }
    .stTextArea textarea {
        font-family: 'LiveFont', sans-serif !important;
        font-size: 48px !important;
        min-height: 140px !important;
        border: 1px solid #DAE1E8 !important;
        border-radius: 10px !important;
        color: #000000 !important;
        line-height: 1.2 !important;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 1. CORE GEOMETRY ENGINE ---
class ProfilePen(BasePen):
    def __init__(self, glyph_set):
        super().__init__(glyph_set)
        self.points = []
    def _moveTo(self, p): self.points.append(p)
    def _lineTo(self, p):
        p0 = self._getCurrentPoint()
        if p0:
            dist = math.dist(p0, p)
            steps = max(1, int(dist / 3.0))
            for i in range(steps + 1):
                t = i / float(steps)
                self.points.append((p0[0] + (p[0] - p0[0]) * t, p0[1] + (p[1] - p0[1]) * t))
        else: self.points.append(p)
    def _curveToOne(self, p1, p2, p3):
        p0 = self._getCurrentPoint()
        if not p0: return
        steps = 15
        for i in range(steps + 1):
            t = i / float(steps)
            x = (1-t)**3 * p0[0] + 3*(1-t)**2 * t * p1[0] + 3*(1-t) * t**2 * p2[0] + t**3 * p3[0]
            y = (1-t)**3 * p0[1] + 3*(1-t)**2 * t * p1[1] + 3*(1-t) * t**2 * p2[1] + t**3 * p3[1]
            self.points.append((x, y))
    def _qCurveToOne(self, p1, p2):
        p0 = self._getCurrentPoint()
        if not p0: return
        steps = 15
        for i in range(steps + 1):
            t = i / float(steps)
            x = (1-t)**2 * p0[0] + 2*(1-t)*t * p1[0] + t**2 * p2[0]
            y = (1-t)**2 * p0[1] + 2*(1-t)*t * p1[1] + t**2 * p2[1]
            self.points.append((x, y))

@st.cache_data(show_spinner=False)
def get_glyph_profiles(_font_bytes):
    font = TTFont(io.BytesIO(_font_bytes))
    head = font['head']
    h_min, h_max = head.yMin, head.yMax
    
    glyph_set = font.getGlyphSet()
    profiles = {}
    
    for name in glyph_set.keys():
        pen = ProfilePen(glyph_set)
        try: glyph_set[name].draw(pen)
        except: continue
        if not pen.points: continue
        
        zones = {"top": {}, "mid": {}, "bot": {}}
        for x, y in pen.points:
            norm_y = (y - h_min) / (h_max - h_min) if h_max > h_min else 0
            zone = "bot" if norm_y < 0.33 else "mid" if norm_y < 0.66 else "top"
            if x not in zones[zone] or x > zones[zone].get(x, -9999): zones[zone][y] = x
        
        xs = [p[0] for p in pen.points]
        profiles[name] = {
            "adv": glyph_set[name].width,
            "zones": {
                "top": max(zones["top"].values()) if zones["top"] else None,
                "mid": max(zones["mid"].values()) if zones["mid"] else None,
                "bot": max(zones["bot"].values()) if zones["bot"] else None,
            }
        }
    return profiles

def calculate_kerning(profiles, pairs, target_gap):
    kern_pairs = {}
    for l, r in pairs:
        if l not in profiles or r not in profiles: continue
        max_overlap = 0
        p_l, p_r = profiles[l], profiles[r]
        for zone in ["top", "mid", "bot"]:
            l_val = p_l["zones"][zone]
            r_val = p_r["zones"][zone]
            if l_val is not None and r_val is not None:
                dist = r_val + p_l["adv"] - l_val
                max_overlap = max(max_overlap, dist)
        kern_val = int(target_gap - max_overlap)
        if abs(kern_val) > 2: kern_pairs[(l, r)] = kern_val
    return kern_pairs

# --- 2. RUNTIME ---
st.set_page_config(page_title="LazyKern Pro", layout="centered")
inject_pro_cleaner()
st.title("LazyKern Pro")

uploaded_file = st.file_uploader("Upload Font", type=["ttf", "otf"])

if uploaded_file:
    file_bytes = uploaded_file.getvalue()
    profiles = get_glyph_profiles(file_bytes)
    
    target_gap = st.slider("Target Gap", 0, 150, 60, 5)
    
    # Process
    glyphs = list(profiles.keys())
    pairs = [(a, b) for a in glyphs for b in glyphs]
    k = calculate_kerning(profiles, pairs, target_gap)
    
    # Generate Modified Font
    font = TTFont(io.BytesIO(file_bytes))
    fea = ["feature kern {"] + [f"    pos {l} {r} {v};" for (l, r), v in k.items()] + ["} kern;"]
    
    try:
        addOpenTypeFeaturesFromString(font, "\n".join(fea))
        out = io.BytesIO()
        font.save(out)
        bytes_data = out.getvalue()
        st.download_button("Download Kerned Font", bytes_data, f"Kerned_{uploaded_file.name}")
    except:
        bytes_data = file_bytes
        st.error("Kerning generation failed.")

    # RE-ENABLE PREVIEW
    b64 = base64.b64encode(bytes_data).decode('utf-8')
    fmt = "opentype" if uploaded_file.name.lower().endswith('.otf') else "truetype"
    st.markdown(f"""<style>@font-face {{font-family:'LiveFont'; src:url('data:font/{fmt};charset=utf-8;base64,{b64}');}}</style>""", unsafe_allow_html=True)
    
    user_text = st.text_area("Test your typography:", "HOHO TO AV")
