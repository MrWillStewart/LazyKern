import streamlit as st
import io
import math
import time
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
    ignore = {'.notdef', 'space', 'null', 'CR', 'nonmarkingreturn'}
    profiles = {}
    for name in font.getGlyphOrder():
        if name in ignore: continue
        pen = ProfilePen(glyph_set)
        try: glyph_set[name].draw(pen)
        except: continue
        if not pen.points: continue
        
        # Stem detection logic
        points = pen.points
        xs = [p[0] for p in points]
        is_vertical = False
        if len(points) > 10:
            vertical_segments = sum(1 for i in range(len(points)-5) if abs(points[i][0] - points[i+5][0]) < 2)
            if vertical_segments > len(points) * 0.3: is_vertical = True

        profiles[name] = {
            "points": points, 
            "advance": glyph_set[name].width,
            "min_x": min(xs), "max_x": max(xs),
            "is_vertical": is_vertical
        }
    return profiles

def calculate_kerning(profiles, target_gap=60):
    glyph_list = list(profiles.keys())
    pairs_to_kern = [(a, b) for a in glyph_list for b in glyph_list]
    kern_pairs = {}
    progress_bar = st.progress(0)
    
    for i, (left, right) in enumerate(pairs_to_kern):
        if i % 100 == 0: progress_bar.progress(i / len(pairs_to_kern))
        
        # Jigsaw Logic: Determine base gap
        base_gap = target_gap
        if profiles[left]["is_vertical"] and profiles[right]["is_vertical"]:
            base_gap = target_gap - 25 # Tighter for stems
        elif not profiles[left]["is_vertical"] and not profiles[right]["is_vertical"]:
            base_gap = target_gap + 10 # Looser for curves
            
        # Collision scan
        needed_kern = base_gap - 100
        for lx, ly in profiles[left]["points"]:
            for rx, ry in profiles[right]["points"]:
                if abs(ly - ry) < 5:
                    dist = (rx + profiles[left]["advance"]) - lx
                    if dist < base_gap:
                        needed_kern = max(needed_kern, base_gap - dist)
        
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
    gap = st.slider("Target Gap (Base)", 10, 100, 60, 5)
    
    if st.button("Generate & Optimize"):
        with st.spinner("Analyzing stems and jigsaw-fitting..."):
            profiles = get_glyph_profiles(font)
            kern_pairs = calculate_kerning(profiles, target_gap=gap)
        
        if kern_pairs:
            fea = ["feature kern {"] + [f"    pos {l} {r} {v};" for (l, r), v in kern_pairs.items()] + ["} kern;"]
            addOpenTypeFeaturesFromString(font, "\n".join(fea))
        
        out = io.BytesIO()
        font.save(out)
        font_data = out.getvalue()
        
        unique_id = int(time.time())
        b64 = base64.b64encode(font_data).decode('utf-8')
        
        st.success(f"Generated {len(kern_pairs)} pairs with Stem Detection.")
        
        st.markdown(f"""
        <style>
        @font-face {{ font-family: 'LiveFont_{unique_id}'; src: url('data:font/ttf;charset=utf-8;base64,{b64}'); }}
        .tester {{ font-family: 'LiveFont_{unique_id}', sans-serif; font-size: 64px; width: 100%; border: 2px solid #ccc; padding: 20px; border-radius: 8px; }}
        </style>
        <textarea class="tester">HNHI OCO OHO</textarea>
        """, unsafe_allow_html=True)
        
        st.download_button("Download Kerned Font", font_data, f"kerned_{uploaded_file.name}")
