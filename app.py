import streamlit as st
import io
import math
import base64
from fontTools.ttLib import TTFont
from fontTools.pens.basePen import BasePen
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString

def inject_pro_cleaner():
    st.markdown("""
    <style>
    [data-testid="stHeader"] { display: none !important; }
    footer { visibility: hidden !important; }
    #MainMenu { visibility: hidden !important; }
    .header-anchor { display: none !important; }
    h1 a, h2 a, h3 a, h4 a { display: none !important; }
    h1, h2, h3, h4, label, .stMarkdown p {
        font-family: 'Departure Mono', monospace !important;
    }
    </style>
    """, unsafe_allow_html=True)

class ProfilePen(BasePen):
    def __init__(self, glyph_set):
        super().__init__(glyph_set)
        self.points = []
    def _moveTo(self, p): self.points.append(p)
    def _lineTo(self, p):
        p0 = self._getCurrentPoint()
        if p0:
            dist = math.dist(p0, p)
            steps = max(1, int(dist / 5.0))
            for i in range(steps + 1):
                t = i / float(steps)
                self.points.append((p0[0] + (p[0] - p0[0]) * t, p0[1] + (p[1] - p0[1]) * t))
        else: self.points.append(p)
    def _curveToOne(self, p1, p2, p3):
        p0 = self._getCurrentPoint()
        if not p0: return
        approx_len = math.dist(p0, p1) + math.dist(p1, p2) + math.dist(p2, p3)
        steps = max(8, min(40, int(approx_len / 5.0)))
        for i in range(steps + 1):
            t = i / float(steps)
            x = (1-t)**3 * p0[0] + 3*(1-t)**2 * t * p1[0] + 3*(1-t) * t**2 * p2[0] + t**3 * p3[0]
            y = (1-t)**3 * p0[1] + 3*(1-t)**2 * t * p1[1] + 3*(1-t) * t**2 * p2[1] + t**3 * p3[1]
            self.points.append((x, y))
    def _qCurveToOne(self, p1, p2):
        p0 = self._getCurrentPoint()
        if not p0: return
        approx_len = math.dist(p0, p1) + math.dist(p1, p2)
        steps = max(6, min(30, int(approx_len / 5.0)))
        for i in range(steps + 1):
            t = i / float(steps)
            x = (1-t)**2 * p0[0] + 2*(1-t)*t * p1[0] + t**2 * p2[0]
            y = (1-t)**2 * p0[1] + 2*(1-t)*t * p1[1] + t**2 * p2[1]
            self.points.append((x, y))

def get_glyph_profiles(font, step_size=5):
    glyph_set = font.getGlyphSet()
    profiles = {}
    for name in glyph_set.keys():
        pen = ProfilePen(glyph_set)
        try: glyph_set[name].draw(pen)
        except Exception: continue
        if not pen.points: continue
        slices = {}
        for x, y in pen.points:
            y_slice = int(round(y / step_size) * step_size)
            slices.setdefault(y_slice, []).append(x)
        profiles[name] = {"left": {y: min(x) for y, x in slices.items()}, "right": {y: max(x) for y, x in slices.items()}, "advance": glyph_set[name].width}
    return profiles

def get_optical_class(name):
    n = name.lower().strip('_')
    if n in ['period', 'comma', 'colon', 'semicolon', 'hyphen', 'exclam', 'question', 'dot', 'underscore']: return 'PUNCTUATION'
    if n in ['t', 'v', 'w', 'y', 'a', 'x', 'f', 'k', 'l']: return 'DIAGONAL_OPEN'
    if n in ['o', 'c', 'q', 'g', 'e', 'd', 'p', 'b', 's']: return 'ROUND'
    if n in ['h', 'i', 'm', 'n', 'u', 'j', 'r']: return 'STRAIGHT'
    return 'DEFAULT'

def calculate_kerning(profiles, pairs_to_kern, target_gap=60):
    kern_pairs = {}
    ABS_SAFE_CLEARANCE = 25
    for left, right in pairs_to_kern:
        if left not in profiles or right not in profiles: continue
        prof_l, prof_r = profiles[left]["right"], profiles[right]["left"]
        common_ys = set(prof_l.keys()).intersection(set(prof_r.keys()))
        if not common_ys: continue
        mod = 0
        cl, cr = get_optical_class(left), get_optical_class(right)
        if cl == 'STRAIGHT' and cr == 'STRAIGHT': mod = 15
        elif cl == 'ROUND' and cr == 'ROUND': mod = -10
        elif (cl == 'DIAGONAL_OPEN' and cr == 'PUNCTUATION') or (cl == 'PUNCTUATION' and cr == 'DIAGONAL_OPEN'): mod = -15
        min_dist = min((prof_r[y] + profiles[left]["advance"]) - prof_l[y] for y in common_ys)
        kern_val = int((target_gap + mod) - min_dist)
        max_comp = 0
        for y in common_ys:
            proj = (prof_r[y] + profiles[left]["advance"] + kern_val) - prof_l[y]
            if proj < ABS_SAFE_CLEARANCE: max_comp = max(max_comp, ABS_SAFE_CLEARANCE - proj)
        if max_comp > 0: kern_val += int(math.ceil(max_comp))
        if abs(kern_val) > 2: kern_pairs[(left, right)] = int(round(kern_val / 5.0) * 5)
    return kern_pairs

st.set_page_config(page_title="LazyKern", layout="centered")
inject_pro_cleaner()
st.title("LazyKern")
uploaded_file = st.file_uploader("Upload Font (TTF/OTF)", type=["ttf", "otf"])

if uploaded_file:
    if "filename" not in st.session_state or st.session_state.filename != uploaded_file.name:
        font_bytes = uploaded_file.read()
        font = TTFont(io.BytesIO(font_bytes))
        st.session_state.original_bytes = font_bytes
        st.session_state.filename = uploaded_file.name
        st.session_state.profiles = get_glyph_profiles(font)
        st.session_state.supported = {chr(cp) for cp in font.getBestCmap().keys()}
        st.session_state.pairs = [(a, b) for a in st.session_state.profiles for b in st.session_state.profiles]

    gap = st.slider("Target Gap", 10, 100, 60, 5)
    use_kerning = st.toggle("Apply Auto-Kerning", True)
    
    bytes_data = st.session_state.original_bytes
    if use_kerning:
        font = TTFont(io.BytesIO(bytes_data))
        k = calculate_kerning(st.session_state.profiles, st.session_state.pairs, gap)
        fea = ["feature kern {"] + [f"    pos {l} {r} {v};" for (l, r), v in k.items()] + ["} kern;"]
        addOpenTypeFeaturesFromString(font, "\n".join(fea))
        out = io.BytesIO()
        font.save(out)
        bytes_data = out.getvalue()

    b64 = base64.b64encode(bytes_data).decode()
    fmt = "opentype" if uploaded_file.name.lower().endswith('.otf') else "truetype"
    st.markdown(f"""<style>@font-face {{font-family:'LiveFont'; src:url('data:font/{fmt};base64,{b64}');}} 
    .tbox {{font-family:'LiveFont'; font-size:48px; width:100%; height:140px; padding:15px; border:1px solid #ccc; border-radius:10px;}}</style>""", unsafe_allow_html=True)

    # Sanitize input: Replace the static HTML with this logic
    user_input = st.text_area("Live Preview", value="START.YOUR.ENGINES.", key="user_text")
    clean = "".join([c for c in user_input if c in st.session_state.supported or c in [" ", "\n", "."]])
    if user_input != clean:
        st.session_state.user_text = clean
        st.rerun()

    st.markdown(f'<div class="tbox">{clean}</div>', unsafe_allow_html=True)
    st.download_button("📥 Download", bytes_data, f"kerned_{uploaded_file.name}")
