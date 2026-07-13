import streamlit as st
import io
import math
import base64
from fontTools.ttLib import TTFont
from fontTools.pens.basePen import BasePen
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString

# --- 1. CORE GEOMETRY ENGINE (High Density) ---
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
        pen = ProfilePen(glyph_set)
        try: glyph_set[name].draw(pen)
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
        profiles[name] = {"left": left_prof, "right": right_prof, "advance": glyph_set[name].width}
    return profiles

# --- 2. OPTICAL RULES ENGINE ---
def get_optical_category(name):
    n = name.lower()
    if n in ['a', 'v', 'w', 'y', 'k', 'x']: return 'DIAGONAL'
    if n in ['h', 'n', 'm', 'u', 'i', 'l', 't', 'f', 'b', 'd', 'p', 'r']: return 'STRAIGHT'
    if n in ['o', 'c', 'g', 'q', 'e', 's']: return 'ROUND'
    if n in ['.', ',', ':', ';', '-', '!', '?']: return 'PUNCTUATION'
    return 'DEFAULT'

def calculate_kerning(profiles, pairs_to_kern, target_gap=60):
    kern_pairs = {}
    
    for left, right in pairs_to_kern:
        if left not in profiles or right not in profiles: continue
        
        # Determine base optical offset based on your rules
        cat_l, cat_r = get_optical_category(left), get_optical_category(right)
        
        # RULES TABLE (The "Artistic" Logic)
        # Straight + Straight = More space (10)
        # Round + Round = Tighter (-15)
        # Diagonal + Straight = Tuck/Tighter (-20)
        offset = 0
        if cat_l == 'STRAIGHT' and cat_r == 'STRAIGHT': offset = 10
        elif cat_l == 'ROUND' and cat_r == 'ROUND': offset = -15
        elif cat_l == 'DIAGONAL' or cat_r == 'DIAGONAL': offset = -20
        elif cat_l == 'PUNCTUATION' or cat_r == 'PUNCTUATION': offset = -10
        
        # Geometry Collision (The "Safety" Logic)
        prof_l, prof_r = profiles[left]["right"], profiles[right]["left"]
        common_ys = set(prof_l.keys()).intersection(set(prof_r.keys()))
        if not common_ys: continue
        
        min_dist = min((prof_r[y] + profiles[left]["advance"]) - prof_l[y] for y in common_ys)
        
        # Final value = Target Gap + Optical Offset - Geometry
        # We want to force the gap, but obey optical rules
        kern_val = int((target_gap + offset) - min_dist)
        
        if abs(kern_val) > 2:
            kern_pairs[(left, right)] = int(round(kern_val / 5.0) * 5)
            
    return kern_pairs

# --- 3. UI ---
st.set_page_config(page_title="LazyKern Pro", layout="centered")
st.title("LazyKern Pro")
uploaded_file = st.file_uploader("Upload Font", type=["ttf", "otf"])

if uploaded_file:
    if "filename" not in st.session_state or st.session_state.filename != uploaded_file.name:
        with st.spinner("Analyzing geometry..."):
            font = TTFont(io.BytesIO(uploaded_file.read()))
            st.session_state.original_bytes = uploaded_file.getvalue()
            st.session_state.profiles = get_glyph_profiles(font)
            glyphs = [g for g in st.session_state.profiles.keys() if g not in [".notdef", "space"]]
            st.session_state.pairs = [(a, b) for a in glyphs for b in glyphs]
            st.session_state.filename = uploaded_file.name

    gap = st.slider("Target Gap (Pixels)", 10, 100, 60, 5)
    
    if st.button("Apply Typographic Rules"):
        with st.spinner("Calculating optical offsets..."):
            font = TTFont(io.BytesIO(st.session_state.original_bytes))
            kern_pairs = calculate_kerning(st.session_state.profiles, st.session_state.pairs, gap)
            
            if kern_pairs:
                fea = ["feature kern {"] + [f"    pos {l} {r} {v};" for (l, r), v in kern_pairs.items()] + ["} kern;"]
                addOpenTypeFeaturesFromString(font, "\n".join(fea))
            
            out = io.BytesIO()
            font.save(out)
            active_font = out.getvalue()
            
            # Preview (Cache Busting)
            b64 = base64.b64encode(active_font).decode('utf-8')
            st.markdown(f"""
                <style>
                @font-face {{ font-family: 'LiveFont'; src: url('data:font/ttf;base64,{b64}'); }}
                .tester {{ font-family: 'LiveFont'; font-size: 64px; border: 1px solid #ccc; padding: 20px; }}
                </style>
                <div class="tester" contenteditable="true">AVAW ST GR TEST</div>
            """, unsafe_allow_html=True)
            
            st.download_button("Download Font", active_font, f"kerned_{uploaded_file.name}")
