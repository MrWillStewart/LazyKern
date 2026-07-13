import streamlit as st
import io
import math
import base64
from fontTools.ttLib import TTFont
from fontTools.pens.basePen import BasePen
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString

# --- 1. CORE GEOMETRY ENGINE (High-Density) ---
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

def get_glyph_profiles(font, step_size=5):
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
            y_slice = int(round(y / step_size) * step_size)
            slices.setdefault(y_slice, []).append(x)
        profiles[name] = {
            "left": {y: min(x) for y, x in slices.items()},
            "right": {y: max(x) for y, x in slices.items()},
            "advance": glyph_set[name].width
        }
    return profiles

def get_optical_class(glyph_name):
    name = glyph_name.lower()
    if name in ['period', 'comma', 'colon', 'semicolon', 'hyphen', 'exclam', 'question', '.', ',']: return 'PUNCTUATION'
    if name in ['t', 'y', 'p', 'v', 'w', 'a', 'f', 'k', 'z']: return 'DIAGONAL_OPEN'
    if name in ['o', 'c', 'g', 'q', 'e', 's', 'd', 'b']: return 'ROUND'
    return 'STRAIGHT'

def calculate_kerning(profiles, target_gap=60):
    kern_pairs = {}
    ABS_SAFE_CLEARANCE = 35
    keys = list(profiles.keys())
    
    # 1. Pairwise Calculation
    for left in keys:
        for right in keys:
            prof_l = profiles[left]["right"]
            prof_r = profiles[right]["left"]
            common_ys = set(prof_l.keys()).intersection(set(prof_r.keys()))
            if not common_ys: continue
            
            # Optical Rules
            c_l, c_r = get_optical_class(left), get_optical_class(right)
            mod = 0
            if c_l == 'DIAGONAL_OPEN' and c_r == 'PUNCTUATION': mod = -35
            elif c_l == 'STRAIGHT' and c_r == 'STRAIGHT': mod = 10
            elif c_l == 'ROUND' and c_r == 'ROUND': mod = -10
            
            min_dist = min((profiles[right]["left"][y] + profiles[left]["advance"]) - profiles[left]["right"][y] for y in common_ys)
            kern_val = int((target_gap + mod) - min_dist)
            
            # Hardline Safety
            for y in common_ys:
                proj = (profiles[right]["left"][y] + profiles[left]["advance"] + kern_val) - profiles[left]["right"][y]
                if proj < ABS_SAFE_CLEARANCE:
                    kern_val += int(math.ceil(ABS_SAFE_CLEARANCE - proj))
            
            if abs(kern_val) > 2: kern_pairs[(left, right)] = int(round(kern_val / 5.0) * 5)
    return kern_pairs

# --- 2. UI ---
st.set_page_config(page_title="LazyKern Pro", layout="centered")
st.title("LazyKern Pro")
uploaded_file = st.file_uploader("Upload Font", type=["ttf", "otf"])

if uploaded_file:
    font_bytes = uploaded_file.read()
    font = TTFont(io.BytesIO(font_bytes))
    profiles = get_glyph_profiles(font)
    supported = set(chr(cp) for cp in font.getBestCmap().keys())
    
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
    st.markdown(f"""
        <style>
        @font-face {{ font-family: 'LiveFont'; src: url('data:font/ttf;base64,{b64}'); }}
        .tester {{ font-family: 'LiveFont', sans-serif !important; font-size: 50px; width: 100%; height: 200px; padding: 15px; border: 1px solid #ccc; }}
        </style>
    """, unsafe_allow_html=True)
    
    def sanitize(text): return "".join([c for c in text if c in supported or c in [" ", "\n", "."]])
    
    user_in = st.text_area("Test your kerning:", value="START.YOUR.ENGINES.", key="t")
    if user_in != sanitize(user_in):
        st.session_state.t = sanitize(user_in)
        st.rerun()
    
    st.markdown(f'<div class="tester">{user_in}</div>', unsafe_allow_html=True)
    st.download_button("Download Kerned Font", font_bytes, f"kerned_{uploaded_file.name}")
