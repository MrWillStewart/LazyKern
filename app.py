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
            steps = max(1, int(dist / 10.0))
            for i in range(steps + 1):
                t = i / float(steps)
                self.points.append((p0[0] + (p[0] - p0[0]) * t, p0[1] + (p[1] - p0[1]) * t))
    def _curveToOne(self, p1, p2, p3):
        p0 = self._getCurrentPoint()
        if not p0: return
        steps = 5
        for i in range(steps + 1):
            t = i / float(steps)
            x = (1-t)**3 * p0[0] + 3*(1-t)**2 * t * p1[0] + 3*(1-t) * t**2 * p2[0] + t**3 * p3[0]
            y = (1-t)**3 * p0[1] + 3*(1-t)**2 * t * p1[1] + 3*(1-t) * t**2 * p2[1] + t**3 * p3[1]
            self.points.append((x, y))
    def _qCurveToOne(self, p1, p2):
        p0 = self._getCurrentPoint()
        if not p0: return
        steps = 5
        for i in range(steps + 1):
            t = i / float(steps)
            x = (1-t)**2 * p0[0] + 2*(1-t)*t * p1[0] + t**2 * p2[0]
            y = (1-t)**2 * p0[1] + 2*(1-t)*t * p1[1] + t**2 * p2[1]
            self.points.append((x, y))

def get_glyph_profiles(font):
    glyph_set = font.getGlyphSet()
    # List of glyphs to ignore (structural/invisible)
    ignore = {'.notdef', 'space', 'null', 'CR', 'nonmarkingreturn'}
    
    profiles = {}
    for name in font.getGlyphOrder():
        if name in ignore: continue
        
        pen = ProfilePen(glyph_set)
        try: glyph_set[name].draw(pen)
        except: continue
        if not pen.points: continue
        
        xs = [p[0] for p in pen.points]
        profiles[name] = {
            "points": pen.points, 
            "advance": glyph_set[name].width,
            "min_x": min(xs), "max_x": max(xs)
        }
    return profiles

def calculate_kerning(profiles, target_gap=60):
    # Dynamically build pairs from the detected profiles
    glyph_list = list(profiles.keys())
    pairs_to_kern = [(a, b) for a in glyph_list for b in glyph_list]
    
    kern_pairs = {}
    total_pairs = len(pairs_to_kern)
    progress_bar = st.progress(0)
    
    for i, (left, right) in enumerate(pairs_to_kern):
        if i % 100 == 0: progress_bar.progress(i / total_pairs)
        
        # Culling
        if (profiles[right]["min_x"] + profiles[left]["advance"]) > (profiles[left]["max_x"] + target_gap + 40):
            continue
            
        needed_kern = target_gap - 100
        for lx, ly in profiles[left]["points"]:
            for rx, ry in profiles[right]["points"]:
                if abs(ly - ry) < 5:
                    dist = (rx + profiles[left]["advance"]) - lx
                    if dist < target_gap:
                        needed_kern = max(needed_kern, target_gap - dist)
        
        if needed_kern > 5:
            kern_pairs[(left, right)] = int(round(needed_kern / 5.0) * 5)
            
    progress_bar.empty()
    return kern_pairs

# --- 2. STREAMLIT UI ---
st.set_page_config(page_title="LazyKern Pro", layout="wide")
st.title("LazyKern Pro")
uploaded_file = st.file_uploader("Upload Font", type=["ttf", "otf"])

if uploaded_file:
    font = TTFont(io.BytesIO(uploaded_file.read()))
    gap = st.slider("Target Gap", 10, 100, 60, 5)
    
    if st.button("Generate & Optimize"):
        with st.spinner("Analyzing your font glyphs..."):
            profiles = get_glyph_profiles(font)
            st.write(f"Detected {len(profiles)} printable glyphs.")
            kern_pairs = calculate_kerning(profiles, target_gap=gap)
        
        if kern_pairs:
            fea = ["feature kern {"] + [f"    pos {l} {r} {v};" for (l, r), v in kern_pairs.items()] + ["} kern;"]
            addOpenTypeFeaturesFromString(font, "\n".join(fea))
        
        out = io.BytesIO()
        font.save(out)
        st.success("Kerning Applied to detected glyphs!")
        st.download_button("Download", out.getvalue(), f"kerned_{uploaded_file.name}")
