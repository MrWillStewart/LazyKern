import streamlit as st
import io
import math
import base64
from fontTools.ttLib import TTFont
from fontTools.pens.basePen import BasePen
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString

# --- 0. BRANDING STRIPPER ---
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
            # High-density sampling to prevent collisions on narrow/slanted lines
            steps = max(2, int(dist / 2.0)) 
            for i in range(steps + 1):
                t = i / float(steps)
                self.points.append((p0[0] + (p[0] - p0[0]) * t, p0[1] + (p[1] - p0[1]) * t))
        else: self.points.append(p)

    def _curveToOne(self, p1, p2, p3):
        p0 = self._getCurrentPoint()
        if not p0: return
        steps = 20 # Increased resolution
        for i in range(steps + 1):
            t = i / float(steps)
            x = (1-t)**3 * p0[0] + 3*(1-t)**2 * t * p1[0] + 3*(1-t) * t**2 * p2[0] + t**3 * p3[0]
            y = (1-t)**3 * p0[1] + 3*(1-t)**2 * t * p1[1] + 3*(1-t) * t**2 * p2[1] + t**3 * p3[1]
            self.points.append((x, y))

    def _qCurveToOne(self, p1, p2):
        p0 = self._getCurrentPoint()
        if not p0: return
        steps = 20
        for i in range(steps + 1):
            t = i / float(steps)
            x = (1-t)**2 * p0[0] + 2*(1-t)*t * p1[0] + t**2 * p2[0]
            y = (1-t)**2 * p0[1] + 2*(1-t)*t * p1[1] + t**2 * p2[1]
            self.points.append((x, y))

def get_glyph_profiles(font, step_size=2): # High-res profiling
    glyph_set = font.getGlyphSet()
    profiles = {}
    for name in glyph_set.keys():
        pen = ProfilePen(glyph_set)
        try: glyph_set[name].draw(pen)
        except: continue
        if not pen.points: continue
        
        # We store every point to allow for perfect overlap detection
        # No more rounding/slicing which causes jagged collision gaps
        profiles[name] = {"points": pen.points, "advance": glyph_set[name].width}
    return profiles

def calculate_kerning(profiles, pairs_to_kern, target_gap=60):
    kern_pairs = {}
    
    for left, right in pairs_to_kern:
        if left not in profiles or right not in profiles: continue
        
        # Collision simulation: brute force check of all point interactions
        points_l = profiles[left]["points"]
        advance_l = profiles[left]["advance"]
        points_r = profiles[right]["points"]
        
        # We shift right glyph by 'kern' until no points overlap
        # Check every point of R against every point of L
        # This is expensive but ensures 0% overlap
        current_kern = target_gap - 100 # Start very tight
        
        while True:
            collision = False
            for lx, ly in points_l:
                # Shift R points by the current advance + kern
                for rx, ry in points_r:
                    # If Y coordinates are close, check X distance
                    if abs(ly - ry) < 5: 
                        if (rx + advance_l + current_kern) - lx < 10:
                            collision = True
                            break
                if collision: break
            
            if not collision:
                break
            else:
                current_kern += 5 # Push apart until clear
        
        if abs(current_kern) > 2:
            kern_pairs[(left, right)] = int(round(current_kern / 5.0) * 5)
            
    return kern_pairs

# --- 2. STREAMLIT RUNTIME ---
st.set_page_config(page_title="LazyKern Pro", layout="centered")
inject_pro_cleaner()

st.title("LazyKern Pro")
uploaded_file = st.file_uploader("Upload Font (TTF/OTF)", type=["ttf", "otf"])

if uploaded_file:
    font_bytes = uploaded_file.read()
    font = TTFont(io.BytesIO(font_bytes))
    
    with st.spinner("Running deep-geometry collision simulation..."):
        profiles = get_glyph_profiles(font)
        glyphs = [g for g in profiles.keys() if g not in [".notdef", "space"]]
        pairs = [(a, b) for a in glyphs for b in glyphs]
        
        # Simplified slider: The logic now handles collisions automatically
        kern_pairs = calculate_kerning(profiles, pairs, target_gap=60)
        
        if kern_pairs:
            fea = ["feature kern {"] + [f"    pos {l} {r} {v};" for (l, r), v in kern_pairs.items()] + ["} kern;"]
            addOpenTypeFeaturesFromString(font, "\n".join(fea))
        
        out = io.BytesIO()
        font.save(out)
        active_bytes = out.getvalue()

    st.success("Simulation Complete. Font kerning enforced.")
    st.download_button("Download Kerned Font", active_bytes, f"kerned_{uploaded_file.name}")
