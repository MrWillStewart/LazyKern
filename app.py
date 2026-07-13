import streamlit as st
import io
import math
import base64
from fontTools.ttLib import TTFont
from fontTools.pens.basePen import BasePen
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString

# --- 0. UI SETUP ---
def inject_pro_cleaner():
    st.markdown("""
    <style>
    [data-testid="stAppFooter"], footer, #MainMenu, [data-testid="stHeader"], div[data-testid="stBottom"] { display: none !important; }
    button[title="View fullscreen"] { display: none !important; }
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
            steps = max(1, int(dist / 10.0)) # Reduced density for speed
            for i in range(steps + 1):
                t = i / float(steps)
                self.points.append((p0[0] + (p[0] - p0[0]) * t, p0[1] + (p[1] - p0[1]) * t))
        else: self.points.append(p)
    def _curveToOne(self, p1, p2, p3):
        p0 = self._getCurrentPoint()
        if not p0: return
        steps = 5 # Reduced density for speed
        for i in range(steps + 1):
            t = i / float(steps)
            x = (1-t)**3 * p0[0] + 3*(1-t)**2 * t * p1[0] + 3*(1-t) * t**2 * p2[0] + t**3 * p3[0]
            y = (1-t)**3 * p0[1] + 3*(1-t)**2 * t * p1[1] + 3*(1-t) * t**2 * p2[1] + t**3 * p3[1]
            self.points.append((x, y))
    def _qCurveToOne(self, p1, p2):
        p0 = self._getCurrentPoint()
        if not p0: return
        steps = 5 # Reduced density for speed
        for i in range(steps + 1):
            t = i / float(steps)
            x = (1-t)**2 * p0[0] + 2*(1-t)*t * p1[0] + t**2 * p2[0]
            y = (1-t)**2 * p0[1] + 2*(1-t)*t * p1[1] + t**2 * p2[1]
            self.points.append((x, y))

def get_glyph_profiles(font):
    glyph_set = font.getGlyphSet()
    profiles = {}
    for name in glyph_set.keys():
        pen = ProfilePen(glyph_set)
        try: glyph_set[name].draw(pen)
        except: continue
        if not pen.points: continue
        
        # Calculate bounding box for fast culling
        xs = [p[0] for p in pen.points]
        profiles[name] = {
            "points": pen.points, 
            "advance": glyph_set[name].width,
            "min_x": min(xs), "max_x": max(xs)
        }
    return profiles

def calculate_kerning(profiles, pairs_to_kern, target_gap=60):
    kern_pairs = {}
    progress_bar = st.progress(0)
    total_pairs = len(pairs_to_kern)
    
    for i, (left, right) in enumerate(pairs_to_kern):
        if i % 100 == 0: progress_bar.progress(i / total_pairs)
        
        if left not in profiles or right not in profiles: continue
        
        # --- CULLING: Only process if bounding boxes imply potential overlap ---
        # If right glyph's min_x is already far from left glyph's max_x, skip calculation.
        if (profiles[right]["min_x"] + profiles[left]["advance"]) > (profiles[left]["max_x"] + target_gap):
            continue
            
        # Collision calculation (Simplified slicing)
        points_l = profiles[left]["points"]
        advance_l = profiles[left]["advance"]
        points_r = profiles[right]["points"]
        
        # Check collision at y-levels
        collision_detected = False
        needed_kern = target_gap - 100 
        
        # Only check Y-slices that overlap
        for lx, ly in points_l:
            for rx, ry in points_r:
                if abs(ly - ry) < 5:
                    dist = (rx + advance_l) - lx
                    if dist < target_gap:
                        needed_kern = max(needed_kern, target_gap - dist)
        
        if needed_kern > 0:
            kern_pairs[(left, right)] = int(round(needed_kern / 5.0) * 5)
            
    progress_bar.empty()
    return kern_pairs

# --- 2. STREAMLIT RUNTIME ---
st.set_page_config(page_title="LazyKern Pro", layout="centered")
inject_pro_cleaner()
st.title("LazyKern Pro")
uploaded_file = st.file_uploader("Upload Font (TTF/OTF)", type=["ttf", "otf"])

if uploaded_file is not None:
    font_bytes = uploaded_file.read()
    font = TTFont(io.BytesIO(font_bytes))
    
    # Process
    profiles = get_glyph_profiles(font)
    glyphs = [g for g in profiles.keys() if g not in [".notdef", "space"]]
    pairs = [(a, b) for a in glyphs for b in glyphs]
    
    gap = st.slider("Target Gap", 10, 100, 60, 5)
    
    if st.button("Generate Kern"):
        kern_pairs = calculate_kerning(profiles, pairs, target_gap=gap)
        
        if kern_pairs:
            fea = ["feature kern {"] + [f"    pos {l} {r} {v};" for (l, r), v in kern_pairs.items()] + ["} kern;"]
            addOpenTypeFeaturesFromString(font, "\n".join(fea))
        
        out = io.BytesIO()
        font.save(out)
        active_bytes = out.getvalue()
        
        st.success("Kerning complete!")
        st.download_button("Download Kerned Font", active_bytes, f"kerned_{uploaded_file.name}")
else:
    st.info("Upload a font to begin.")
