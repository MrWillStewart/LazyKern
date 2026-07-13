import streamlit as st
import io
import math
from fontTools.ttLib import TTFont
from fontTools.pens.basePen import BasePen
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString

# --- 1. CORE GEOMETRY ENGINE ---
class ProfilePen(BasePen):
    def __init__(self, glyph_set):
        super().__init__(glyph_set)
        self.points = []

    def _moveTo(self, p): 
        self.points.append(p)

    def _lineTo(self, p): 
        self.points.append(p)

    def _curveToOne(self, p1, p2, p3):
        p0 = self._getCurrentPoint()
        approx_len = math.dist(p0, p1) + math.dist(p1, p2) + math.dist(p2, p3)
        steps = max(8, min(30, int(approx_len / 20)))
        
        for i in range(steps + 1):
            t = i / float(steps)
            x = (1-t)**3 * p0[0] + 3*(1-t)**2 * t * p1[0] + 3*(1-t) * t**2 * p2[0] + t**3 * p3[0]
            y = (1-t)**3 * p0[1] + 3*(1-t)**2 * t * p1[1] + 3*(1-t) * t**2 * p2[1] + t**3 * p3[1]
            self.points.append((x, y))

    def _qCurveToOne(self, p1, p2):
        p0 = self._getCurrentPoint()
        approx_len = math.dist(p0, p1) + math.dist(p1, p2)
        steps = max(6, min(20, int(approx_len / 20)))
        
        for i in range(steps + 1):
            t = i / float(steps)
            x = (1-t)**2 * p0[0] + 2*(1-t)*t * p1[0] + t**2 * p2[0]
            y = (1-t)**2 * p0[1] + 2*(1-t)*t * p1[1] + t**2 * p2[1]
            self.points.append((x, y))

def get_glyph_profiles(font, step_size=10):
    glyph_set = font.getGlyphSet()
    profiles = {}
    
    for glyph_name in glyph_set.keys():
        pen = ProfilePen(glyph_set)
        glyph = glyph_set[glyph_name]
        
        try:
            glyph.draw(pen)
        except Exception:
            continue
            
        if not pen.points: 
            continue
            
        slices = {}
        for x, y in pen.points:
            y_slice = int(round(y / step_size) * step_size)
            slices.setdefault(y_slice, []).append(x)
            
        left_profile, right_profile = {}, {}
        for y_slice, x_vals in slices.items():
            left_profile[y_slice] = min(x_vals)
            right_profile[y_slice] = max(x_vals)
            
        profiles[glyph_name] = {
            "left": left_profile, 
            "right": right_profile, 
            "advance": glyph.width,
            "nodes_count": len(pen.points)
        }
    return profiles

def analyze_character_set(font):
    cmap = font.getBestCmap()
    stats = {"type": "Standard Latin", "caps": 0, "lower": 0, "digits": 0, "punct": 0, "total": 0}
    if not cmap: 
        stats["type"] = "Unknown (No Cmap Table)"
        return stats
        
    for char_code in cmap.keys():
        try:
            char = chr(char_code)
            stats["total"] += 1
            if char.isupper(): stats["caps"] += 1
            elif char.islower(): stats["lower"] += 1
            elif char.isdigit(): stats["digits"] += 1
            elif char.isascii() and not char.isalnum() and not char.isspace(): stats["punct"] += 1
        except Exception:
            continue
            
    if stats["caps"] > 0 and stats["lower"] == 0:
        stats["type"] = "All Caps / Display"
    elif stats["total"] > 500:
        stats["type"] = "Extended / Multilingual"
        
    return stats

def calculate_kerning(profiles, pairs_to_kern, target_gap=40):
    kern_pairs = {}
    for left, right in pairs_to_kern:
        if left in profiles and right in profiles:
            prof_l = profiles[left]["right"]
            prof_r = profiles[right]["left"]
            common_ys = set(prof_l.keys()).intersection(set(prof_r.keys()))
            if not common_ys: 
                continue
            min_dist = min((prof_r[y] + profiles[left]["advance"]) - prof_l[y] for y in common_ys)
            kern_val = int(target_gap - min_dist)
            if abs(kern_val) > 2:
                kern_pairs[(left, right)] = int(round(kern_val / 5.0) * 5)
    return kern_pairs

# --- 2. BACKEND PROCESS PROCESSING LAYOUT ---
st.set_page_config(page_title="LazyKern", layout="centered")

st.title("LazyKern ✒️")
uploaded_file = st.file_uploader("Upload Font (TTF/OTF)", type=["ttf", "otf"])

if uploaded_file:
    gap = st.slider("Target Gap Distance", min_value=10, max_value=100, value=40, step=5)
    
    if st.button("Analyze & Process Font"):
        with st.spinner("Executing geometric matrix scan..."):
            font = TTFont(io.BytesIO(uploaded_file.read()))
            stats = analyze_character_set(font)
            profiles = get_glyph_profiles(font)
            
            glyphs = [g for g in profiles.keys() if g not in [".notdef", "space"]]
            pairs_to_kern = [(a, b) for a in glyphs for b in glyphs]
            kern_pairs = calculate_kerning(profiles, pairs_to_kern, target_gap=gap)
            
            fea_lines = ["feature kern {"] + [f"    pos {l} {r} {v};" for (l, r), v in kern_pairs.items()] + ["} kern;"]
            addOpenTypeFeaturesFromString(font, "\n".join(fea_lines))
            
            out = io.BytesIO()
            font.save(out)
            
            st.success("Analysis Complete!")
            st.download_button(
                label="📥 Download Kerned Font File", 
                data=out.getvalue(), 
                file_name=f"kerned_{uploaded_file.name}"
            )

# --- 3. FRONTEND PREVIEW COMPONENT ---
st.write("---")
st.subheader("Live Interactive Type Tester")

# Insert your full code design string right here
design_html = """
<style>
  /* Base Container - Defined as a style container context */
  .type-tester-container {
    --tester-font: sans-serif;
    background-color: #ffffff;
    border: 1px solid #dae1e8;
    border-radius: 10px;
    margin: 0;
    width: 100%;
    min-width: 0; 
    display: flex;
    flex-direction: column;
    overflow: hidden;
    font-family: 'Departuremono', monospace !important;
    -webkit-tap-highlight-color: transparent;
    container-type: inline-size;
  }

  .tester-header {
    display: flex;
    flex-direction: row;
    align-items: stretch;
    flex-wrap: nowrap;
    border-bottom: 1px solid #dae1e8;
    width: 100%;
    height: 60px;
    position: relative;
  }
  
  .slider-wrapper {
    flex-grow: 1;
    max-width: 400px;
    display: flex;
    align-items: center;
    padding: 0;
    gap: 0px;
    height: 100%;
  }

  .adjust-btn {
    width: 60px;
    height: 60px;
    background: none;
    border: none;
    cursor: pointer;
    font-size: 16px;
    color: #4c5b6b;
    display: flex;
    align-items: center;
    justify-content: center;
    outline: none;
    flex-shrink: 0;
    transition: background-color 0.15s ease, color 0.15s ease;
  }
  
  @media (hover: hover) {
    .adjust-btn:hover { background-color: #fcfcfc; color: #000000; }
  }
  .adjust-btn:active { background-color: #f0f0f0; }

  .divider {
    width: 1px !important;
    background-color: #dae1e8;
    align-self: stretch;
    flex-shrink: 0;
  }

  .size-readout {
    font-family: 'Departuremono', monospace !important;
    font-size: 13px !important;
    line-height: 20px !important;
    display: flex;
    align-items: center;
    justify-content: center;
    border-left: 1px solid #dae1e8;
    width: 75px; 
    flex-shrink: 0;
    color: #4c5b6b;
    white-space: nowrap;
    -webkit-user-select: none;
    user-select: none;
  }

  .style-switcher {
    display: flex;
    margin-left: auto;
    align-self: stretch;
    border-left: 1px solid #dae1e8;
    position: relative;
  }

  .style-btn {
    font-family: 'Departuremono', monospace !important;
    font-size: 13px !important;
    line-height: 20px !important;
    background: #ffffff;
    border: none;
    padding: 11px 30px;
    color: #4c5b6b;
    cursor: pointer;
    transition: background-color 0.2s ease;
    white-space: nowrap;
    display: flex;
    align-items: center;
    text-decoration: none;
    height: 100%;
    outline: none;
  }

  .style-btn:hover { background-color: #fafafb; }
  .style-btn.active { text-decoration: underline; text-underline-offset: 6px; }

  .sizeSlider {
    -webkit-appearance: none;
    appearance: none;
    width: 100%;
    height: 60px; 
    background: transparent;
    margin: 0;
    padding: 0 20px;
    cursor: pointer;
  }
  
  .sizeSlider::-webkit-slider-runnable-track { width: 100%; height: 1px; background-color: #dae1e8; }
  .sizeSlider::-webkit-slider-thumb {
    -webkit-appearance: none;
    appearance: none;
    height: 60px; 
    width: 40px;  
    background-color: transparent !important;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='20'%3E%3Crect width='10' height='20' rx='2' fill='%23000000'/%3E%3C/svg%3E");
    background-position: center;
    background-repeat: no-repeat;
    margin-top: -29.5px; 
  }

  .tester-body { padding: 20px 0; width: 100%; box-sizing: border-box; }
  .live-type-editor {
    font-family: var(--tester-font) !important;
    line-height: 1.2;        
    color: #000000;
    outline: none;
    border: none;
    padding: 0 30px;
    width: 100%;
    white-space: nowrap;
    overflow-x: auto;
  }
</style>

<div class="type-tester-container" 
     style="--tester-font: sans-serif" 
     data-glyphs="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.,:;!?#/-' $€£%" 
     data-start-size="60" data-min-size="20" data-max-size="150" data-start-text="Type Test Space">
     
  <div class="tester-header">
    <div class="slider-wrapper">
      <button class="adjust-btn prev">←</button>
      <div class="divider"></div>
      <input type="range" class="sizeSlider" step="1" />
      <div class="divider"></div>
      <button class="adjust-btn next">→</button>
    </div>
    <div class="size-readout"><span class="sizeValue">60pt</span></div>
  </div>

  <div class="tester-body">
    <div contenteditable="true" spellcheck="false" class="liveEditor live-type-editor">Type Test Space</div>
  </div>
</div>

<script>
  (function () {
    const box = document.querySelector('.type-tester-container');
    const slider = box.querySelector('.sizeSlider');
    const readout = box.querySelector('.sizeValue');
    const editor = box.querySelector('.liveEditor');
    const btnPrev = box.querySelector('.prev');
    const btnNext = box.querySelector('.next');

    function updateDisplay() {
        const size = slider.value + 'pt';
        editor.style.fontSize = size;
        if (readout) readout.textContent = size;
    }

    slider.min = box.getAttribute('data-min-size');
    slider.max = box.getAttribute('data-max-size');
    slider.value = box.getAttribute('data-start-size');
    updateDisplay();

    slider.addEventListener('input', updateDisplay);
    btnPrev.addEventListener('click', () => { slider.value = Math.max(20, parseInt(slider.value)-5); updateDisplay(); });
    btnNext.addEventListener('click', () => { slider.value = Math.min(150, parseInt(slider.value)+5); updateDisplay(); });
  })();
</script>
"""

import streamlit.components.v1 as components
components.html(design_html, height=300)
