import streamlit as st
import io
import math
import base64
from fontTools.ttLib import TTFont
from fontTools.pens.basePen import BasePen
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString

# --- 0. BRANDING STRIPPER & TYPOGRAPHY ENFORCER ---
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

# --- 1. CORE GEOMETRY ENGINE ---
class ProfilePen(BasePen):
    def __init__(self, glyph_set):
        super().__init__(glyph_set)
        self.points = []

    def _moveTo(self, p): 
        self.points.append(p)

    def _lineTo(self, p):
        p0 = self._getCurrentPoint()
        if p0:
            dist = math.dist(p0, p)
            steps = max(1, int(dist / 5.0))
            for i in range(steps + 1):
                t = i / float(steps)
                x = p0[0] + (p[0] - p0[0]) * t
                y = p0[1] + (p[1] - p0[1]) * t
                self.points.append((x, y))
        else:
            self.points.append(p)

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
        glyph = glyph_set[name]
        try: glyph.draw(pen)
        except Exception: continue
        if not pen.points: continue
        
        slices = {}
        for x, y in pen.points:
            y_slice = int(round(y / step_size) * step_size)
            slices.setdefault(y_slice, []).append(x)
            
        left_prof, right_prof = {}, {}
        for y_slice, x_vals in slices.items():
            left_prof[y_slice] = min(x_vals)
            right_prof[y_slice] = max(x_vals)
            
        profiles[name] = {"left": left_prof, "right": right_prof, "advance": glyph.width}
    return profiles

def get_optical_class(glyph_name):
    name = glyph_name.lower().strip('_')
    if name in ['period', 'comma', 'colon', 'semicolon', 'hyphen', 'exclam', 'question', 'dot', 'underscore']:
        return 'PUNCTUATION'
    if name in ['t', 'v', 'w', 'y', 'a', 'x', 'f', 'k', 'l']:
        return 'DIAGONAL_OPEN'
    if name in ['o', 'c', 'q', 'g', 'e', 'd', 'p', 'b', 's']:
        return 'ROUND'
    if name in ['h', 'i', 'm', 'n', 'u', 'j', 'r']:
        return 'STRAIGHT'
    return 'DEFAULT'

def calculate_kerning(profiles, pairs_to_kern, target_gap=60):
    kern_pairs = {}
    ABS_SAFE_CLEARANCE = 25 
    for left, right in pairs_to_kern:
        if left in profiles and right in profiles:
            prof_l = profiles[left]["right"]
            prof_r = profiles[right]["left"]
            common_ys = set(prof_l.keys()).intersection(set(prof_r.keys()))
            if not common_ys: continue
            class_l, class_r = get_optical_class(left), get_optical_class(right)
            optical_modifier = 0
            if class_l == 'STRAIGHT' and class_r == 'STRAIGHT': optical_modifier += 15
            elif class_l == 'ROUND' and class_r == 'ROUND': optical_modifier -= 10
            elif (class_l == 'DIAGONAL_OPEN' and class_r == 'PUNCTUATION') or (class_l == 'PUNCTUATION' and class_r == 'DIAGONAL_OPEN'): optical_modifier -= 15
            adjusted_target = target_gap + optical_modifier
            min_dist = min((prof_r[y] + profiles[left]["advance"]) - prof_l[y] for y in common_ys)
            kern_val = int(adjusted_target - min_dist)
            max_adjacent_compensation = 0
            for y in common_ys:
                projected_space = (prof_r[y] + profiles[left]["advance"] + kern_val) - prof_l[y]
                if projected_space < ABS_SAFE_CLEARANCE:
                    compensation = ABS_SAFE_CLEARANCE - projected_space
                    if compensation > max_adjacent_compensation: max_adjacent_compensation = compensation
            if max_adjacent_compensation > 0: kern_val += int(math.ceil(max_adjacent_compensation))
            if abs(kern_val) > 2: kern_pairs[(left, right)] = int(round(kern_val / 5.0) * 5)
    return kern_pairs

# --- 2. STREAMLIT RUNTIME ---
st.set_page_config(page_title="LazyKern", layout="centered")
inject_pro_cleaner()
st.title("LazyKern")
uploaded_file = st.file_uploader("Upload Font (TTF/OTF)", type=["ttf", "otf"])

if uploaded_file:
    if "filename" not in st.session_state or st.session_state.filename != uploaded_file.name:
        with st.spinner("Analyzing geometry..."):
            font_bytes = uploaded_file.read()
            st.session_state.original_bytes = font_bytes
            st.session_state.filename = uploaded_file.name
            font = TTFont(io.BytesIO(font_bytes))
            st.session_state.profiles = get_glyph_profiles(font)
            st.session_state.supported_chars = set(chr(cp) for cp in font.getBestCmap().keys())
            glyphs = [g for g in st.session_state.profiles.keys() if g not in [".notdef", "space"]]
            st.session_state.pairs = [(a, b) for a in glyphs for b in glyphs]

    gap = st.slider("Target Gap (Tightness)", 10, 100, 60, 5)
    use_kerning = st.toggle("Apply Auto-Kerning", value=True)
    
    if use_kerning:
        font = TTFont(io.BytesIO(st.session_state.original_bytes))
        kern_pairs = calculate_kerning(st.session_state.profiles, st.session_state.pairs, target_gap=gap)
        if kern_pairs:
            fea_lines = ["feature kern {"] + [f"    pos {l} {r} {v};" for (l, r), v in kern_pairs.items()] + ["} kern;"]
            addOpenTypeFeaturesFromString(font, "\n".join(fea_lines))
        out = io.BytesIO()
        font.save(out)
        active_font_bytes = out.getvalue()
    else:
        active_font_bytes = st.session_state.original_bytes

    b64_font = base64.b64encode(active_font_bytes).decode('utf-8')
    st.markdown(f"""
        <style>
            @font-face {{ font-family: 'LiveFont'; src: url('data:font/ttf;base64,{b64_font}'); }}
            div[data-baseweb="textarea"] textarea {{
                font-family: 'LiveFont' !important;
                font-size: 48px !important;
            }}
        </style>
    """, unsafe_allow_html=True)

    user_text = st.text_area("Live Preview:", value="START.YOUR.ENGINES.", key="tester")
    sanitized = "".join([c for c in user_text if c in st.session_state.supported_chars or c in [" ", "\n"]])
    
    st.text_area("Sanitized Preview (Rendered):", value=sanitized, disabled=True)

    st.download_button("📥 Download Kerned Font", active_font_bytes, f"kerned_{uploaded_file.name}")
