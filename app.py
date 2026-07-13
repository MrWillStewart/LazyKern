import streamlit as st
import io
import math
import base64
from fontTools.ttLib import TTFont
from fontTools.pens.basePen import BasePen
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString

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
            steps = max(1, int(dist / 5.0))
            for i in range(steps + 1):
                t = i / float(steps)
                self.points.append((p0[0] + (p[0] - p0[0]) * t, p0[1] + (p[1] - p0[1]) * t))
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

def get_optical_category(name):
    n = name.lower()
    if n in ['t', 'y', 'p', 'v', 'w', 'a', 'f', 'k', 'z']: return 'DIAGONAL_OVERHANG'
    if n in ['h', 'n', 'm', 'u', 'i', 'l', 'd', 'b']: return 'STRAIGHT'
    if n in ['o', 'c', 'g', 'q', 'e', 's']: return 'ROUND'
    if n in ['.', ',', ':', ';', '-', '!', '?', 'period', 'comma']: return 'PUNCTUATION'
    return 'DEFAULT'

def get_glyph_profiles(font):
    glyph_set = font.getGlyphSet()
    profiles = {}
    for name in glyph_set.keys():
        if name in {'.notdef', 'space', 'null', 'CR'}: continue
        pen = ProfilePen(glyph_set)
        try: glyph_set[name].draw(pen)
        except Exception: continue
        if not pen.points: continue
        
        slices = {}
        for x, y in pen.points:
            y_slice = int(round(y / 5.0) * 5)
            slices.setdefault(y_slice, []).append(x)
        
        left_prof = {y: min(x) for y, x in slices.items()}
        right_prof = {y: max(x) for y, x in slices.items()}
        profiles[name] = {"left": left_prof, "right": right_prof, "advance": glyph_set[name].width}
    return profiles

def get_supported_chars(font):
    # Returns a set of characters that actually have glyphs in the font
    cmap = font.getBestCmap()
    return set(chr(cp) for cp in cmap.keys())

def calculate_kerning(profiles, target_gap):
    kern_pairs = {}
    ABS_SAFE_CLEARANCE = 35 
    keys = list(profiles.keys())
    
    for left in keys:
        for right in keys:
            prof_l = profiles[left]["right"]
            prof_r = profiles[right]["left"]
            common_ys = set(prof_l.keys()).intersection(set(prof_r.keys()))
            if not common_ys: continue
            
            cat_l, cat_r = get_optical_category(left), get_optical_category(right)
            
            offset = 0
            if cat_l == 'DIAGONAL_OVERHANG' and cat_r == 'PUNCTUATION': offset = -35 
            elif cat_l == 'PUNCTUATION' and cat_r == 'DIAGONAL_OVERHANG': offset = -10
            elif cat_l == 'STRAIGHT' and cat_r == 'STRAIGHT': offset = 10
            elif cat_l == 'ROUND' and cat_r == 'ROUND': offset = -10
            
            min_dist = min((prof_r[y] + profiles[left]["advance"]) - prof_l[y] for y in common_ys)
            kern_val = int((target_gap + offset) - min_dist)
            
            for y in common_ys:
                projected_space = (prof_r[y] + profiles[left]["advance"] + kern_val) - prof_l[y]
                if projected_space < ABS_SAFE_CLEARANCE:
                    compensation = ABS_SAFE_CLEARANCE - projected_space
                    kern_val += int(math.ceil(compensation))
            
            if abs(kern_val) > 2:
                kern_pairs[(left, right)] = int(round(kern_val / 5.0) * 5)
    return kern_pairs

# --- 2. UI ---
st.set_page_config(page_title="LazyKern Live", layout="centered")
st.title("LazyKern Live")
uploaded_file = st.file_uploader("Upload Font", type=["ttf", "otf"])

if uploaded_file:
    font_data_raw = uploaded_file.read()
    font = TTFont(io.BytesIO(font_data_raw))
    profiles = get_glyph_profiles(font)
    supported_chars = get_supported_chars(font)
    
    use_kern = st.toggle("Apply Auto-Kerning", value=True)
    gap = st.slider("Target Gap", 10, 100, 60, 5)
    
    if use_kern:
        kern_pairs = calculate_kerning(profiles, gap)
        fea = ["feature kern {"] + [f"    pos {l} {r} {v};" for (l, r), v in kern_pairs.items()] + ["} kern;"]
        addOpenTypeFeaturesFromString(font, "\n".join(fea))
    
    out = io.BytesIO()
    font.save(out)
    font_bytes = out.getvalue()
    b64 = base64.b64encode(font_bytes).decode('utf-8')
    
    # Filter function: Only allow characters present in supported_chars
    def sanitize_input(text):
        return "".join([c for c in text if c in supported_chars or c in [" ", "\n"]])

    st.markdown(f"""
        <style>
        @font-face {{ font-family: 'LiveFont'; src: url('data:font/ttf;base64,{b64}'); }}
        .stTextArea textarea {{
            font-family: 'LiveFont', sans-serif !important;
            font-size: 48px !important;
            line-height: 1.2 !important;
            height: 200px !important;
        }}
        </style>
    """, unsafe_allow_html=True)
    
    # Text area with automatic input cleaning
    user_input = st.text_area("Test your kerning here:", value="START.YOUR.ENGINES.", key="tester")
    
    # If the user typed something invalid, we sanitize it immediately
    if user_input != sanitize_input(user_input):
        st.warning("Some characters were stripped because they are not supported by the font.")
        st.session_state.tester = sanitize_input(user_input)
        st.rerun()

    st.download_button("Download Kerned Font", font_bytes, f"kerned_{uploaded_file.name}")
