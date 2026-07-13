import streamlit as st
import io
import math
from fontTools.ttLib import TTFont
from fontTools.pens.basePen import BasePen
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString

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
        # DYNAMIC PRECISION: Scale sampling density based on curve length
        approx_len = math.dist(p0, p1) + math.dist(p1, p2) + math.dist(p2, p3)
        steps = max(8, min(30, int(approx_len / 20))) # Dynamic, smooth sampling
        
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
        
        # FIX 1: Safety wrapper preventing crashes on missing outline data
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
            
    # Intelligently tag the font style
    if stats["caps"] > 0 and stats["lower"] == 0:
        stats["type"] = "All Caps / Display"
    elif stats["total"] > 500:
        stats["type"] = "Extended / Multilingual"
        
    return stats
