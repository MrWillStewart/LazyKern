import streamlit as st
import io
import math
import base64
from fontTools.ttLib import TTFont
from fontTools.pens.basePen import BasePen
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString

# --- 1. CORE GEOMETRY ENGINE ---
# (Pen logic remains robust and consistent)
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

def get_glyph_profiles(font, step_size=5):
    glyph_set = font.getGlyphSet()
    profiles = {}
    for name in glyph_set.keys():
        pen = ProfilePen(glyph_set)
        try: glyph_set[name].draw(pen)
        except: continue
        if not pen.points: continue
        slices = {}
        for x, y in pen.points:
            y_slice = int(round(y / step_size) * step_size)
            slices.setdefault(y_slice, []).append(x)
        left_prof, right_prof = {}, {}
        for y, x_vals in slices.items():
            left_prof[y] = min(x_vals)
            right_prof[y] = max(x_vals)
        profiles[name] = {"left": left_prof, "right": right_prof, "advance": glyph_set[name].width}
    return profiles

def calculate_kerning(profiles, pairs_to_kern, target_gap=60):
    kern_pairs = {}
    
    # 1. PRIMARY PASS: Geometric Spacing
    for left, right in pairs_to_kern:
        if left not in profiles or right not in profiles: continue
        prof_l = profiles[left]["right"]
        prof_r = profiles[right]["left"]
        common_ys = set(prof_l.keys()).intersection(set(prof_r.keys()))
        if not common_ys: continue
        
        min_dist = min((prof_r[y] + profiles[left]["advance"]) - prof_l[y] for y in common_ys)
        kern_val = int(target_gap - min_dist)
        if abs(kern_val) > 2:
            kern_pairs[(left, right)] = int(round(kern_val / 5.0) * 5)
            
    # 2. SIMULATION PASS: Triplet Audit
    # We inspect the results for triplets (Left-Mid-Right) where 'Mid' is a narrow glyph
    # If the combined encroachment of Left and Right is too high, we force an adjustment.
    final_pairs = kern_pairs.copy()
    glyphs = list(profiles.keys())
    
    # Only run for triplets if punctuation/narrow chars exist
    narrow_chars = ['.', ',', ':', ';', '!', 'i', 'l'] 
    for left in glyphs:
        for mid in narrow_chars:
            if mid not in profiles: continue
            for right in glyphs:
                if (left, mid) in kern_pairs and (mid, right) in kern_pairs:
                    # Simulation: Check if 'left' and 'right' collide physically
                    # by ignoring the 'mid' character's width entirely
                    prof_l = profiles[left]["right"]
                    prof_r = profiles[right]["left"]
                    
                    # Logic: If Left and Right are closer than 10 units regardless of mid
                    collision_check = min((prof_r[y] + profiles[left]["advance"] + profiles[mid]["advance"]) - prof_l[y] for y in prof_l.keys() & prof_r.keys())
                    if collision_check < 20: 
                        final_pairs[(left, mid)] += 10
                        final_pairs[(mid, right)] += 10
                        
    return final_pairs

# --- 2. STREAMLIT RUNTIME ---
st.set_page_config(page_title="LazyKern Pro", layout="centered")

st.title("LazyKern Pro")
uploaded_file = st.file_uploader("Upload Font (TTF/OTF)", type=["ttf", "otf"])

if uploaded_file:
    font_bytes = uploaded_file.read()
    font = TTFont(io.BytesIO(font_bytes))
    
    with st.spinner("Running Geometric Simulation (Multi-Pass)..."):
        profiles = get_glyph_profiles(font)
        glyphs = [g for g in profiles.keys() if g not in [".notdef", "space"]]
        pairs = [(a, b) for a in glyphs for b in glyphs]
        gap = st.slider("Target Gap (Tightness)", 10, 100, 60, 5)
        
        kern_pairs = calculate_kerning(profiles, pairs, target_gap=gap)
        
        if kern_pairs:
            fea = ["feature kern {"] + [f"    pos {l} {r} {v};" for (l, r), v in kern_pairs.items()] + ["} kern;"]
            addOpenTypeFeaturesFromString(font, "\n".join(fea))
        
        out = io.BytesIO()
        font.save(out)
        active_bytes = out.getvalue()

    b64 = base64.b64encode(active_bytes).decode('utf-8')
    st.markdown(f"""<style>@font-face {{font-family: 'LiveFont'; src: url('data:font/ttf;charset=utf-8;base64,{b64}');}} .tester {{font-family: 'LiveFont'; font-size: 48px; width: 100%; border: 1px solid #ccc; padding: 10px;}}</style>""", unsafe_allow_html=True)
    st.markdown('<textarea class="tester">AVAW ST GR TEST.</textarea>', unsafe_allow_html=True)
    st.download_button("Download Kerned Font", active_bytes, f"kerned_{uploaded_file.name}")
