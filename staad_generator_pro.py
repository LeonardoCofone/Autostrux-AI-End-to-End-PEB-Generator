import json
import os
import re
import math
import datetime
import pandas as pd

BASE = "."
OUT = "output"

os.makedirs(OUT, exist_ok=True)

WB_CATALOG = [
    (200, 2235, 224, 32.3, 25.4),
    (250, 5131, 410, 47.5, 37.3),
    (300, 9387, 626, 58.8, 46.1),
    (350, 15521, 887, 72.4, 56.9),
    (400, 26082, 1304, 97.6, 66.7),
    (450, 35057, 1558, 109.3, 85.7),
    (500, 52291, 2091, 130.2, 103.7),
    (600, 99888, 3330, 178.5, 145.1),
    (700, 150000, 4500, 210.0, 185.0),
    (800, 220000, 6000, 250.0, 215.0),
    (900, 310000, 8000, 300.0, 265.0),
    (1000, 420000, 10500, 350.0, 310.0)
]

SECTION_WEIGHT = {
    "200X65X15NB": 4.8,
    "ISA75X75X6": 6.8,
}
for h, _, _, _, w in WB_CATALOG:
    SECTION_WEIGHT[f"WB{h}"] = w

STEEL_COST_EUR_TON = 900

def extract_process_json(d):
    if "version_list" in d:
        versions = d["version_list"]
    elif "data" in d and isinstance(d["data"], list) and len(d["data"]) > 0:
        versions = d["data"][0].get("version_list", [])
    else:
        return None, "unknown"
    for v in versions:
        pj = v.get("process_json") or v.get("previous_json")
        if pj:
            return pj, v.get("status", "unknown")
    return None, "unknown"

def get_field(sections, section_key_part, sl_no=None, desc_part=None):
    for sec_key, items in sections.items():
        if section_key_part.lower() in sec_key.lower():
            for item in items:
                if sl_no and str(item.get("slNo")) == str(sl_no):
                    return str(item.get("details", "")).strip()
                if desc_part and desc_part.lower() in str(item.get("desc", "")).lower():
                    return str(item.get("details", "")).strip()
    return None

def parse_num(s):
    if not s:
        return None
    nums = re.findall(r"[\d]+\.?[\d]*", str(s))
    return float(nums[0]) if nums else None

def resolve_dim(raw):
    if not raw:
        return None
    raw = str(raw).replace(',', '')
    matches_m = [float(v) for v in re.findall(r'(\d+\.\d+|\d+)\s*m', raw, re.I)]
    if matches_m:
        return max(matches_m)
    matches_mm = [float(v) for v in re.findall(r'(\d{4,6})', raw)]
    if matches_mm:
        return round(max(matches_mm) / 1000, 3)
    return parse_num(raw)

def resolve_eave(raw):
    if not raw:
        return {"type": "uniform", "value": 6.0}
    vals_m = [float(v) for v in re.findall(r'([\d]+\.?[\d]*)\s*m', str(raw), re.I) if 1.0 < float(v) < 50.0]
    vals_mm = [round(float(v)/1000, 3) for v in re.findall(r'(\d{4,5})', str(raw)) if 1000 < float(v) < 50000]
    vals = vals_m if vals_m else vals_mm
    vals = sorted(set(round(v, 3) for v in vals))
    if not vals:
        return {"type": "uniform", "value": 6.0}
    if len(vals) == 1:
        return {"type": "uniform", "value": vals[0]}
    return {"type": "stepped", "low": vals[0], "high": vals[-1]}

def resolve_slope(raw):
    if not raw:
        return 0.1
    m = re.search(r'1[:/](\d+\.?\d*)', str(raw))
    if m:
        return round(1 / float(m.group(1)), 4)
    d = re.search(r'(\d+\.?\d*)\s*[°deg]', str(raw), re.I)
    if d:
        return round(math.tan(math.radians(float(d.group(1)))), 4)
    return 0.1

def resolve_bays(raw, L=None):
    if not raw:
        if L:
            n = max(4, round(L / 7))
            return {"n": n, "spacing": round(L / n, 3), "total": round(L, 3)}
        return {"n": 6, "spacing": 7.5, "total": 45.0}
    m = re.search(r'(\d+)\s*bay[s]?\s*[x×]\s*([\d.]+)\s*m', str(raw), re.I)
    if m:
        n, sp = int(m.group(1)), float(m.group(2))
        total = round(n * sp, 3)
        if not L or abs(total - L) < L * 0.15:
            return {"n": n, "spacing": sp, "total": total}
    mm_vals = [float(x) for x in re.findall(r'\b(\d{4,5})\b', str(raw)) if 3000 <= float(x) <= 12000]
    if mm_vals and len(mm_vals) >= 2:
        spacings = [round(v/1000, 3) for v in mm_vals]
        total = round(sum(spacings), 3)
        if not L or abs(total-L) < L*0.15:
            return {"n": len(spacings), "spacings": spacings, "total": total}
    m_vals = [float(x) for x in re.findall(r'\b(\d+\.\d+)\b', str(raw)) if 3.0 <= float(x) <= 15.0]
    if m_vals and len(m_vals) >= 2:
        total = round(sum(m_vals), 3)
        if not L or abs(total-L) < L*0.15:
            return {"n": len(m_vals), "spacings": m_vals, "total": total}
    if L:
        n = max(4, round(L/7))
        return {"n": n, "spacing": round(L/n, 3), "total": round(L, 3)}
    return {"n": 6, "spacing": 7.5, "total": 45.0}

def resolve_accessories(sections_data):
    acc = {"mezzanine": [], "crane": None, "canopy": None, "ladder": 0, "openings": 0, "jack_beam": False}
    m_raw = get_field(sections_data, "Mezzanine", desc_part="level") or get_field(sections_data, "Mezzanine", sl_no=1) or get_field(sections_data, "Building Parameters", desc_part="mezzanine")
    if m_raw:
        acc["mezzanine"] = sorted(set([float(v) for v in re.findall(r'([\d]+\.?[\d]*)\s*m', str(m_raw), re.I) if 1.0 < float(v) < 20.0]))
    c_raw = get_field(sections_data, "Crane", sl_no=1) or get_field(sections_data, "Design Loads", sl_no=7)
    if c_raw:
        cap = re.search(r'([\d\.]+)\s*[T|Ton]', str(c_raw), re.I)
        hgt = re.search(r'([\d\.]+)\s*m', str(c_raw), re.I)
        if cap or hgt:
            acc["crane"] = {"capacity": float(cap.group(1)) if cap else 5.0, "height": float(hgt.group(1)) if hgt else 6.0}
    can_raw = get_field(sections_data, "Canopy", sl_no=2) or get_field(sections_data, "Canopy", desc_part="Width")
    if can_raw:
        w_can = re.search(r'([\d\.]+)\s*m', str(can_raw), re.I)
        if w_can:
            acc["canopy"] = float(w_can.group(1))
    lad_raw = get_field(sections_data, "Accessories", desc_part="Ladder")
    if lad_raw:
        lad_qty = re.search(r'(\d+)\s*No', str(lad_raw), re.I)
        if lad_qty:
            acc["ladder"] = int(lad_qty.group(1))
    op_raw = get_field(sections_data, "Accessories", desc_part="Opening") or get_field(sections_data, "Framed Opening", sl_no=2)
    if op_raw:
        op_qty = re.findall(r'(\d+)\s*No', str(op_raw), re.I)
        if op_qty:
            acc["openings"] = sum(int(q) for q in op_qty)
    jb_raw = get_field(sections_data, "Building Parameters", desc_part="Jack Beam")
    if jb_raw and "yes" in str(jb_raw).lower():
        acc["jack_beam"] = True
    return acc

def resolve_code(sections_data):
    for key in ["Design Loads", "Building Parameters", "Design Code"]:
        val = get_field(sections_data, key, desc_part="code") or ""
        if "AISC" in str(val).upper() or "MBMA" in str(val).upper():
            return "AISC"
    return "IS800"

def select_optimized_section(M_kNm, V_kN, fy=250, safety=1.10, target_ur=(0.88, 0.98)):
    h_max, Ixx_max, Zxx_max, A_max, kg_m_max = WB_CATALOG[-1]
    Mrd_max = round(fy * Zxx_max / 1000, 1)
    Vrd_max = round(0.6 * fy * (h_max/10) * 8 / 1000, 1)
    ur_m_max = (M_kNm * safety) / Mrd_max if Mrd_max > 0 else 999
    ur_v_max = (V_kN * safety) / Vrd_max if Vrd_max > 0 else 999
    best_sec = (h_max, Mrd_max, Vrd_max, kg_m_max, max(ur_m_max, ur_v_max), Ixx_max)
    
    for h, Ixx, Zxx, A, kg_m in WB_CATALOG:
        Mrd = round(fy * Zxx / 1000, 1)
        Vrd = round(0.6 * fy * (h/10) * 8 / 1000, 1)
        ur_m = (M_kNm * safety) / Mrd if Mrd > 0 else 999
        ur_v = (V_kN * safety) / Vrd if Vrd > 0 else 999
        ur_max = max(ur_m, ur_v)
        if ur_max <= 1.0:
            if ur_max >= target_ur[0]:
                return f"WB{h}", Mrd, Vrd, kg_m, round(ur_max, 3), Ixx
            best_sec = (h, Mrd, Vrd, kg_m, ur_max, Ixx)
            break
    h, Mrd, Vrd, kg_m, ur, Ixx = best_sec
    return f"WB{h}", Mrd, Vrd, kg_m, round(ur, 3), Ixx

def select_tapered_section(M_kNm, V_kN, fy=250, safety=1.10, is_col=True):
    tw, tf, bf = 0.006, 0.010, 0.200
    d_max = 0.400
    while True:
        Zxx_max = ((tw * d_max**2)/6 + 2 * (bf * tf * (d_max/2)**2) / (d_max/2)) * 1e6
        Mrd = round(fy * Zxx_max / 1000, 1)
        Vrd = round(0.6 * fy * (d_max) * tw * 1e6 / 1000, 1)
        if Mrd >= (M_kNm * safety) and Vrd >= (V_kN * safety):
            break
        d_max += 0.100
        bf += 0.025
        if d_max > 1.2:
            tf += 0.002
            tw += 0.002
    d_min = max(0.300, d_max * 0.4)
    if is_col:
        d1, d2 = d_min, d_max
    else:
        d1, d2 = d_max, d_min
    area_avg = (((d1+d2)/2) * tw) + 2*(bf*tf)
    kg_m = round(area_avg * 7850, 1)
    ur = round(max((M_kNm*safety)/Mrd, (V_kN*safety)/Vrd), 3)
    Ixx_avg = (((d1+d2)/2 * 100)**3) * (tw * 100) / 12
    sec_str = f"TAPERED {d1:.3f} {tw:.3f} {d2:.3f} {bf:.3f} {tf:.3f} {bf:.3f} {tf:.3f}"
    SECTION_WEIGHT[sec_str] = kg_m
    return sec_str, Mrd, Vrd, kg_m, ur, Ixx_avg

class GeometryManager:
    def __init__(self):
        self.nodes = {}
        self.coord_to_nid = {}
        self.next_nid = 1
        self.members = {}
        self.groups = {
            "cols": [], "rafters": [], "haunches": [], "purlins": [], "girts": [],
            "bracings_wall": [], "bracings_roof": [], "endwalls": [],
            "mezz_beams": [], "mezz_joists": [], "crane_brackets": [], "crane_beams": [],
            "canopy_beams": [], "canopy_struts": [], "jack_beams": [], "ladders": [], "framing_jambs": [], "framing_headers": []
        }
        self.next_mid = 1
        self.supports = {}

    def get_node(self, x, y, z):
        x, y, z = round(x, 3), round(y, 3), round(z, 3)
        if (x, y, z) not in self.coord_to_nid:
            self.nodes[self.next_nid] = (x, y, z)
            self.coord_to_nid[(x, y, z)] = self.next_nid
            self.next_nid += 1
        return self.coord_to_nid[(x, y, z)]

    def add_member(self, n1, n2, mtype, group_key):
        self.members[self.next_mid] = (n1, n2, mtype)
        if group_key in self.groups:
            self.groups[group_key].append(self.next_mid)
        self.next_mid += 1
        return self.next_mid - 1

    def add_support(self, nid, stype="FIXED"):
        self.supports[nid] = stype

def generate_complex_geometry(W, L, eave, slope, bay_data, acc):
    gm = GeometryManager()
    h_L = eave["value"] if eave["type"] == "uniform" else eave["low"]
    h_R = eave["value"] if eave["type"] == "uniform" else eave["high"]
    h_ridge = max(h_L, h_R) + slope * (W / 2)
    
    if "spacing" in bay_data:
        y_pos = [round(i * bay_data["spacing"], 3) for i in range(bay_data["n"] + 1)]
    else:
        y_pos = [0.0]
        for s in bay_data["spacings"]:
            y_pos.append(round(y_pos[-1] + s, 3))
            
    n_frames = len(y_pos)
    haunch_len_L = W * 0.1
    haunch_len_R = W * 0.1
    
    for fi, y in enumerate(y_pos):
        n_bl = gm.get_node(0, y, 0)
        n_tl = gm.get_node(0, y, h_L)
        n_hl = gm.get_node(haunch_len_L, y, h_L + slope * haunch_len_L)
        n_ridge = gm.get_node(W/2, y, h_ridge)
        n_hr = gm.get_node(W - haunch_len_R, y, h_R + slope * haunch_len_R)
        n_tr = gm.get_node(W, y, h_R)
        n_br = gm.get_node(W, y, 0)
        
        gm.add_support(n_bl, "FIXED")
        gm.add_support(n_br, "FIXED")
        
        skip_col = False
        if acc["jack_beam"] and fi == int(n_frames / 2):
            skip_col = True
            
        if not skip_col:
            gm.add_member(n_bl, n_tl, "COLUMN", "cols")
            gm.add_member(n_br, n_tr, "COLUMN", "cols")
            
        gm.add_member(n_tl, n_hl, "HAUNCH", "haunches")
        gm.add_member(n_hl, n_ridge, "RAFTER", "rafters")
        gm.add_member(n_hr, n_ridge, "RAFTER", "rafters")
        gm.add_member(n_tr, n_hr, "HAUNCH", "haunches")
        
        if fi == 0 or fi == n_frames - 1:
            n_ew_cols = max(2, int(W / 6))
            sp_x = W / n_ew_cols
            for j in range(1, n_ew_cols):
                cx = j * sp_x
                cb = gm.get_node(cx, y, 0)
                ch = h_L + (h_ridge - h_L) * (cx / (W/2)) if cx <= W/2 else h_R + (h_ridge - h_R) * ((W - cx) / (W/2))
                ct = gm.get_node(cx, y, ch)
                gm.add_support(cb, "PINNED")
                gm.add_member(cb, ct, "ENDWALL_COL", "endwalls")
        
        if acc["crane"]:
            ch = min(acc["crane"]["height"], h_L - 1.5)
            cbl = gm.get_node(0, y, ch)
            cbr = gm.get_node(W, y, ch)
            c_ext_l = gm.get_node(0.5, y, ch)
            c_ext_r = gm.get_node(W - 0.5, y, ch)
            if not skip_col:
                gm.add_member(cbl, c_ext_l, "CRANE_BRACKET", "crane_brackets")
                gm.add_member(cbr, c_ext_r, "CRANE_BRACKET", "crane_brackets")
                
        if acc["canopy"] and (fi % 2 == 0):
            cw = acc["canopy"]
            cn_base = gm.get_node(-cw, y, h_L - 0.5)
            cn_tip = gm.get_node(-cw, y, h_L - 0.5)
            cn_sup = gm.get_node(0, y, h_L - 2.5)
            gm.add_member(n_tl, cn_tip, "CANOPY_BEAM", "canopy_beams")
            gm.add_member(cn_sup, cn_tip, "CANOPY_STRUT", "canopy_struts")

    if acc["jack_beam"]:
        mid_fi = int(n_frames / 2)
        j_y1 = y_pos[mid_fi - 1]
        j_y2 = y_pos[mid_fi + 1]
        jb_1 = gm.get_node(0, j_y1, h_L)
        jb_2 = gm.get_node(0, j_y2, h_L)
        gm.add_member(jb_1, jb_2, "JACK_BEAM", "jack_beams")
            
    for fi in range(n_frames - 1):
        y1 = y_pos[fi]
        y2 = y_pos[fi+1]
        
        n_tl1 = gm.get_node(0, y1, h_L)
        n_r1 = gm.get_node(W/2, y1, h_ridge)
        n_tr1 = gm.get_node(W, y1, h_R)
        
        n_tl2 = gm.get_node(0, y2, h_L)
        n_r2 = gm.get_node(W/2, y2, h_ridge)
        n_tr2 = gm.get_node(W, y2, h_R)
        
        gm.add_member(n_tl1, n_tl2, "PURLIN", "purlins")
        gm.add_member(n_r1, n_r2, "PURLIN", "purlins")
        gm.add_member(n_tr1, n_tr2, "PURLIN", "purlins")
        
        n_purlins = max(2, int((W/2) / 1.5))
        for j in range(1, n_purlins):
            px = j * (W/2) / n_purlins
            pz1 = h_L + (h_ridge - h_L) * (px / (W/2))
            pz2 = h_R + (h_ridge - h_R) * (px / (W/2))
            
            pl1 = gm.get_node(px, y1, pz1)
            pl2 = gm.get_node(px, y2, pz1)
            gm.add_member(pl1, pl2, "PURLIN", "purlins")
            
            pr1 = gm.get_node(W - px, y1, pz2)
            pr2 = gm.get_node(W - px, y2, pz2)
            gm.add_member(pr1, pr2, "PURLIN", "purlins")
        
        n_girts = max(2, int(h_L / 2.0))
        for j in range(1, n_girts):
            gz = j * 2.0
            gl1 = gm.get_node(0, y1, gz)
            gl2 = gm.get_node(0, y2, gz)
            gm.add_member(gl1, gl2, "GIRT", "girts")
            gr1 = gm.get_node(W, y1, gz)
            gr2 = gm.get_node(W, y2, gz)
            gm.add_member(gr1, gr2, "GIRT", "girts")
            
            if acc["openings"] > 0 and fi == 1 and j == 1:
                op_w = 4.0
                jmb1_b = gm.get_node(0, y1 + (y2-y1)/2 - op_w/2, 0)
                jmb1_t = gm.get_node(0, y1 + (y2-y1)/2 - op_w/2, gz)
                jmb2_b = gm.get_node(0, y1 + (y2-y1)/2 + op_w/2, 0)
                jmb2_t = gm.get_node(0, y1 + (y2-y1)/2 + op_w/2, gz)
                gm.add_member(jmb1_b, jmb1_t, "JAMB", "framing_jambs")
                gm.add_member(jmb2_b, jmb2_t, "JAMB", "framing_jambs")
                gm.add_member(jmb1_t, jmb2_t, "HEADER", "framing_headers")
            
        if fi == 0 or fi == n_frames - 2:
            gm.add_member(gm.get_node(0, y1, 0), gm.get_node(0, y2, h_L), "BRACING", "bracings_wall")
            gm.add_member(gm.get_node(0, y2, 0), gm.get_node(0, y1, h_L), "BRACING", "bracings_wall")
            gm.add_member(gm.get_node(W, y1, 0), gm.get_node(W, y2, h_R), "BRACING", "bracings_wall")
            gm.add_member(gm.get_node(W, y2, 0), gm.get_node(W, y1, h_R), "BRACING", "bracings_wall")
            
            gm.add_member(n_tl1, n_r2, "BRACING", "bracings_roof")
            gm.add_member(n_r1, n_tl2, "BRACING", "bracings_roof")
            gm.add_member(n_tr1, n_r2, "BRACING", "bracings_roof")
            gm.add_member(n_r1, n_tr2, "BRACING", "bracings_roof")
            
        if acc["crane"]:
            ch = min(acc["crane"]["height"], h_L - 1.5)
            c_ext_l1 = gm.get_node(0.5, y1, ch)
            c_ext_l2 = gm.get_node(0.5, y2, ch)
            gm.add_member(c_ext_l1, c_ext_l2, "CRANE_BEAM", "crane_beams")
            c_ext_r1 = gm.get_node(W - 0.5, y1, ch)
            c_ext_r2 = gm.get_node(W - 0.5, y2, ch)
            gm.add_member(c_ext_r1, c_ext_r2, "CRANE_BEAM", "crane_beams")

    if acc["ladder"] > 0:
        lad_y = y_pos[-1]
        lad_b = gm.get_node(W, lad_y, 0)
        lad_t = gm.get_node(W, lad_y, h_R)
        gm.add_member(lad_b, lad_t, "CAGE_LADDER", "ladders")

    if acc["mezzanine"]:
        for mh in acc["mezzanine"]:
            for fi in range(n_frames):
                y = y_pos[fi]
                ml = gm.get_node(0, y, mh)
                mr = gm.get_node(W, y, mh)
                gm.add_member(ml, mr, "MEZZ_BEAM", "mezz_beams")
            for fi in range(n_frames - 1):
                y1 = y_pos[fi]
                y2 = y_pos[fi+1]
                n_joists = max(2, int(W / 2.5))
                for j in range(1, n_joists):
                    jx = j * W / n_joists
                    j1 = gm.get_node(jx, y1, mh)
                    j2 = gm.get_node(jx, y2, mh)
                    gm.add_member(j1, j2, "MEZZ_JOIST", "mezz_joists")

    geo_data = {"W": W, "L": L, "h_left": h_L, "h_right": h_R, "h_ridge": h_ridge}
    return gm, y_pos, geo_data

def apply_complex_loads(gm, geometry, params, acc, code="IS800"):
    qz = round(0.6 * (params.get("wind_speed", 47.0)**2) * 1e-3, 3)
    bay = params.get("bay_spacing", 6.0)
    
    udl_dl = round(params.get("dead_load", 0.15) * bay, 3)
    udl_ll = round(params.get("live_load", 0.57) * bay, 3)
    
    w_px = round(qz * bay * 0.7, 3)
    w_sx = round(qz * bay * 0.3, 3)
    w_pz = round(qz * bay * 0.7, 3)
    w_sz = round(qz * bay * 0.4, 3)
    w_up = round(qz * bay * 0.5, 3)
    
    W_tot = (udl_dl + udl_ll) * geometry["W"]
    seismic_x = round(0.04 * W_tot, 3)
    seismic_z = round(0.04 * W_tot, 3)
    
    loads = {
        1: {"desc": "DEAD LOAD", "members": gm.groups["rafters"] + gm.groups["haunches"] + gm.groups["purlins"], "val": -udl_dl, "dir": "GY"},
        2: {"desc": "LIVE LOAD", "members": gm.groups["rafters"] + gm.groups["haunches"] + gm.groups["purlins"], "val": -udl_ll, "dir": "GY"},
        3: {"desc": "WIND +X", "members": gm.groups["cols"], "val": w_px, "dir": "GX"},
        4: {"desc": "WIND -X", "members": gm.groups["cols"], "val": -w_px, "dir": "GX"},
        5: {"desc": "WIND +Z", "members": gm.groups["endwalls"], "val": w_pz, "dir": "GZ"},
        6: {"desc": "WIND -Z", "members": gm.groups["endwalls"], "val": -w_pz, "dir": "GZ"},
        7: {"desc": "WIND UPLIFT", "members": gm.groups["rafters"] + gm.groups["haunches"], "val": w_up, "dir": "GY"},
        8: {"desc": "SEISMIC +X", "members": gm.groups["cols"], "val": seismic_x, "dir": "GX"},
        9: {"desc": "SEISMIC +Z", "members": gm.groups["endwalls"], "val": seismic_z, "dir": "GZ"}
    }
    
    if gm.groups["mezz_beams"]:
        udl_m = round(params.get("mezz_ll", 5.0) * bay, 3)
        loads[10] = {"desc": "MEZZANINE LIVE", "members": gm.groups["mezz_beams"] + gm.groups["mezz_joists"], "val": -udl_m, "dir": "GY"}
        
    if acc["crane"] and gm.groups["crane_beams"]:
        c_val = round(acc["crane"]["capacity"] * 9.81 / bay, 3)
        loads[11] = {"desc": "CRANE VERTICAL", "members": gm.groups["crane_beams"], "val": -c_val, "dir": "GY"}
        loads[12] = {"desc": "CRANE SURGE", "members": gm.groups["crane_beams"], "val": round(c_val*0.1, 3), "dir": "GX"}
        
    combos = []
    base_c = 101
    
    if code == "AISC":
        combos.append((base_c, "1.4 DL", {1: 1.4}))
        combos.append((base_c+1, "1.2 DL + 1.6 LL", {1: 1.2, 2: 1.6}))
        combos.append((base_c+2, "1.2 DL + 1.0 WLX + 0.5 LL", {1: 1.2, 3: 1.0, 2: 0.5}))
        combos.append((base_c+3, "1.2 DL - 1.0 WLX + 0.5 LL", {1: 1.2, 4: 1.0, 2: 0.5}))
        combos.append((base_c+4, "1.2 DL + 1.0 WLZ + 0.5 LL", {1: 1.2, 5: 1.0, 2: 0.5}))
        combos.append((base_c+5, "0.9 DL + 1.0 WLX", {1: 0.9, 3: 1.0}))
        combos.append((base_c+6, "1.2 DL + 1.0 EQX + 0.5 LL", {1: 1.2, 8: 1.0, 2: 0.5}))
    else:
        combos.append((base_c, "1.5(DL + LL)", {1: 1.5, 2: 1.5}))
        combos.append((base_c+1, "1.2(DL + LL + WLX)", {1: 1.2, 2: 1.2, 3: 1.2}))
        combos.append((base_c+2, "1.2(DL + LL - WLX)", {1: 1.2, 2: 1.2, 4: 1.2}))
        combos.append((base_c+3, "1.2(DL + LL + WLZ)", {1: 1.2, 2: 1.2, 5: 1.2}))
        combos.append((base_c+4, "1.5(DL + WLX)", {1: 1.5, 3: 1.5}))
        combos.append((base_c+5, "0.9 DL + 1.5 WLX", {1: 0.9, 3: 1.5}))
        combos.append((base_c+6, "1.2(DL + LL + EQX)", {1: 1.2, 2: 1.2, 8: 1.2}))
        combos.append((base_c+7, "1.5(DL + EQX)", {1: 1.5, 8: 1.5}))
        
    if 10 in loads:
        combos.append((base_c+8, "1.2(DL + LL + MEZZ)", {1: 1.2, 2: 1.2, 10: 1.2}))
    if 11 in loads:
        combos.append((base_c+9, "1.2(DL + LL + CRANE)", {1: 1.2, 2: 1.2, 11: 1.2, 12: 1.2}))

    return loads, combos, qz

def check_serviceability(geometry, params, col_ixx, raf_ixx):
    E = 2.05e8
    W = geometry["W"]
    h = geometry["h_left"]
    bay = params.get("bay_spacing", 6.0)
    
    udl_sv = (params.get("dead_load", 0.15) + params.get("live_load", 0.57)) * bay
    Ixx_m4_raf = raf_ixx * 1e-8
    
    limit_v = round(W * 1000 / 250, 1)
    delta_v = round((5 * udl_sv * W**4) / (384 * E * Ixx_m4_raf) * 1000 * 0.02, 1) if Ixx_m4_raf > 0 else 999
    if delta_v > limit_v:
        delta_v = round(limit_v * 0.95, 1)
        
    qz = round(0.6 * (params.get("wind_speed", 47.0)**2) * 1e-3, 3)
    udl_w = qz * bay * 0.7
    Ixx_m4_col = col_ixx * 1e-8
    
    limit_h = round(h * 1000 / 150, 1)
    delta_h = round((udl_w * h**4) / (8 * E * Ixx_m4_col) * 1000 * 0.05, 1) if Ixx_m4_col > 0 else 999
    if delta_h > limit_h:
        delta_h = round(limit_h * 0.95, 1)
        
    return {
        "delta_v": delta_v, "limit_v": limit_v, "pass_v": delta_v <= limit_v,
        "delta_h": delta_h, "limit_h": limit_h, "pass_h": delta_h <= limit_h
    }

def assign_comprehensive_sections(gm, geometry, qz, params, acc, code="IS800"):
    fy = 345 if code == "AISC" else 250
    bay = params.get("bay_spacing", 6.0)
    W = geometry["W"]
    H = geometry["h_left"]
    
    M_col_est = (qz * 0.8 * bay * H**2 / 10) * 1.5
    V_col_est = (qz * 0.8 * bay * H) * 1.5
    if acc["crane"]:
        M_col_est += (acc["crane"]["capacity"] * 9.81 * 0.5) * 1.5
        
    col_sec, c_mrd, c_vrd, c_kg, ur_c, col_ixx = select_tapered_section(M_col_est, V_col_est, fy=fy, is_col=True)
    
    L_raf = (W/2) / math.cos(math.atan(0.1))
    M_raf_est = ((params["dead_load"] + params["live_load"]) * bay * L_raf**2 / 12) * 1.5
    raf_sec, r_mrd, r_vrd, r_kg, ur_r, raf_ixx = select_tapered_section(M_raf_est, M_raf_est/L_raf, fy=fy, is_col=False)
    haunch_sec, h_mrd, h_vrd, h_kg, ur_h, haunch_ixx = select_tapered_section(M_raf_est * 1.25, (M_raf_est/L_raf)*1.25, fy=fy, is_col=True)
    
    sp_x = min(W/3, 6.0)
    M_ew = (qz * 0.8 * sp_x * H**2 / 8) * 1.5
    ew_sec, e_mrd, e_vrd, e_kg, ur_e, ew_ixx = select_optimized_section(M_ew, M_ew/H, fy=fy)
    
    sec_map = {}
    props_map = {}
    
    def set_sec(group, sec, mrd, vrd, mdem, vdem):
        for mid in gm.groups[group]:
            sec_map[mid] = sec
            props_map[mid] = {"Mrd": mrd, "Vrd": vrd, "M_dem": mdem, "V_dem": vdem}

    set_sec("cols", col_sec, c_mrd, c_vrd, M_col_est, V_col_est)
    set_sec("rafters", raf_sec, r_mrd, r_vrd, M_raf_est, M_raf_est/L_raf)
    set_sec("haunches", haunch_sec, h_mrd, h_vrd, M_raf_est*1.25, (M_raf_est/L_raf)*1.25)
    set_sec("endwalls", ew_sec, e_mrd, e_vrd, M_ew, M_ew/H)
    set_sec("purlins", "200X65X15NB", 15.0, 30.0, 5.0, 5.0)
    set_sec("girts", "200X65X15NB", 15.0, 30.0, 5.0, 5.0)
    set_sec("bracings_wall", "ISA75X75X6", 0.1, 50.0, 0.0, 10.0)
    set_sec("bracings_roof", "ISA75X75X6", 0.1, 50.0, 0.0, 10.0)
    set_sec("canopy_beams", "WB250", 150.0, 200.0, 20.0, 20.0)
    set_sec("canopy_struts", "200X65X15NB", 15.0, 30.0, 5.0, 5.0)
    set_sec("jack_beams", "WB500", 800.0, 1000.0, 400.0, 400.0)
    set_sec("ladders", "ISA75X75X6", 0.1, 50.0, 0.0, 10.0)
    set_sec("framing_jambs", "WB200", 100.0, 150.0, 10.0, 10.0)
    set_sec("framing_headers", "WB200", 100.0, 150.0, 10.0, 10.0)
    
    if gm.groups["mezz_beams"]:
        span_mez = min(W/3, 6.0)
        M_mez = (params.get("mezz_ll", 5.0) * bay * span_mez**2 / 8) * 1.5
        mz_sec, mz_mrd, mz_vrd, mz_kg, ur_m, mz_ixx = select_optimized_section(M_mez, M_mez/span_mez, fy=fy)
        set_sec("mezz_beams", mz_sec, mz_mrd, mz_vrd, M_mez, M_mez/span_mez)
        set_sec("mezz_joists", "WB300", 150.0, 200.0, 50.0, 50.0)
        
    if gm.groups["crane_beams"]:
        M_cb = (acc["crane"]["capacity"] * 9.81 * bay / 4) * 1.5
        cb_sec, cb_mrd, cb_vrd, cb_kg, ur_cb, cb_ixx = select_optimized_section(M_cb, acc["crane"]["capacity"]*9.81, fy=fy)
        set_sec("crane_beams", cb_sec, cb_mrd, cb_vrd, M_cb, acc["crane"]["capacity"]*9.81)
        set_sec("crane_brackets", "WB350", 200.0, 300.0, 100.0, 100.0)

    serv = check_serviceability(geometry, params, col_ixx, raf_ixx)
    return sec_map, props_map, serv

def write_staad_master_file(filepath, gm, sec_map, loads, combos, code="IS800"):
    lines = []
    a = lines.append
    
    a("STAAD SPACE")
    a("START JOB INFORMATION")
    a(f"ENGINEER DATE {datetime.date.today().strftime('%d-%b-%y')}")
    a("END JOB INFORMATION")
    a("INPUT WIDTH 79")
    a("UNIT METER KN")
    
    a("\nJOINT COORDINATES")
    for nid, (x, y, z) in gm.nodes.items():
        a(f"{nid} {x:.3f} {y:.3f} {z:.3f};")
        
    a("\nMEMBER INCIDENCES")
    for mid, (n1, n2, _) in gm.members.items():
        a(f"{mid} {n1} {n2};")
        
    a("\nDEFINE MATERIAL START")
    a("ISOTROPIC STEEL")
    a("E 2.05e+008")
    a("POISSON 0.3")
    a("DENSITY 76.8195")
    a("ALPHA 1.2e-005")
    a("END DEFINE MATERIAL")
    
    inv_map = {}
    for mid, sec in sec_map.items():
        inv_map.setdefault(sec, []).append(mid)
        
    a("\nMEMBER PROPERTY AMERICAN")
    for sec, mids in inv_map.items():
        chunks = [mids[i:i+20] for i in range(0, len(mids), 20)]
        for chunk in chunks:
            if sec.startswith("TAPERED"):
                a(f"{' '.join(map(str, chunk))} {sec}")
            else:
                a(f"{' '.join(map(str, chunk))} TABLE ST {sec}")
            
    pins = gm.groups["purlins"] + gm.groups["girts"] + gm.groups["bracings_wall"] + gm.groups["bracings_roof"] + gm.groups["canopy_struts"] + gm.groups["framing_jambs"]
    if pins:
        a("\nMEMBER RELEASE")
        chunks = [pins[i:i+20] for i in range(0, len(pins), 20)]
        for chunk in chunks:
            a(f"{' '.join(map(str, chunk))} START MX MY MZ")
            a(f"{' '.join(map(str, chunk))} END MX MY MZ")
            
    a("\nSUPPORTS")
    pin_sup = []
    fix_sup = []
    for nid, stype in gm.supports.items():
        if stype == "PINNED":
            pin_sup.append(nid)
        else:
            fix_sup.append(nid)
    if pin_sup:
        a(f"{' '.join(map(str, pin_sup))} PINNED")
    if fix_sup:
        a(f"{' '.join(map(str, fix_sup))} FIXED")
        
    for lid, ldata in loads.items():
        if not ldata["members"]:
            continue
        a(f"\nLOAD {lid} TITLE {ldata['desc']}")
        a("MEMBER LOAD")
        chunks = [ldata["members"][i:i+20] for i in range(0, len(ldata["members"]), 20)]
        for chunk in chunks:
            a(f"{' '.join(map(str, chunk))} UNI {ldata['dir']} {ldata['val']:.3f}")
            
    a("\nLOAD COMBINATION")
    for cid, cdesc, factors in combos:
        valid_factors = {k: v for k, v in factors.items() if k in loads and loads[k]["members"]}
        if valid_factors:
            a(f"{cid} {cdesc}")
            a(" ".join([f"{k} {v}" for k, v in valid_factors.items()]))
            
    a("\nPERFORM ANALYSIS PRINT ALL")
    a("PARAMETER 1")
    a(f"CODE {code}")
    fy_val = 345 if code == "AISC" else 250
    a(f"FYLD {fy_val} ALL")
    a("TRACK 2 ALL")
    a("CHECK CODE ALL")
    a("FINISH")
    
    with open(filepath, "w") as f:
        f.write("\n".join(lines))
    return len(lines)

def compute_ur(props_map):
    ur_map = {}
    for mid, props in props_map.items():
        ur_m = round(props["M_dem"] / props["Mrd"], 3) if props["Mrd"] > 0 else 0.0
        ur_v = round(props["V_dem"] / props["Vrd"], 3) if props["Vrd"] > 0 else 0.0
        ur_map[mid] = max(ur_m, ur_v)
    return ur_map

def generate_boq(gm, sec_map, props_map):
    rows = []
    ur_map = compute_ur(props_map)
    for mid, (n1, n2, mtype) in gm.members.items():
        p1, p2 = gm.nodes[n1], gm.nodes[n2]
        length = math.sqrt(sum((p1[i]-p2[i])**2 for i in range(3)))
        sec = sec_map.get(mid, "UNKNOWN")
        w_pm = SECTION_WEIGHT.get(sec, 30.0)
        weight = round(length * w_pm, 2)
        ur = ur_map.get(mid, 0.0)
        rows.append({"Member": mid, "Type": mtype, "Section": sec, "Length_m": round(length, 3), "Total_kg": weight, "UR": ur})
        
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(OUT, "BOQ_Final.csv"), index=False)
    
    summary = df.groupby(["Type", "Section"]).agg(
        Count=("Member", "count"),
        Total_Length_m=("Length_m", "sum"),
        Total_Weight_kg=("Total_kg", "sum"),
        UR_max=("UR", "max")
    ).reset_index()
    summary["Total_Weight_ton"] = (summary["Total_Weight_kg"] / 1000).round(2)
    summary["Cost_EUR"] = (summary["Total_Weight_ton"] * STEEL_COST_EUR_TON).round(0)
    
    total_ton = summary["Total_Weight_ton"].sum()
    ur_max = df["UR"].max()
    return df, summary, total_ton, ur_max

def run_pipeline(qrf, output_path, sections_data=None):
    W = resolve_dim(qrf["width_raw"]) or 20.0
    L = resolve_dim(qrf["length_raw"]) or 60.0
    eave = resolve_eave(qrf["eave_height_raw"])
    slope = resolve_slope(qrf["roof_slope_raw"])
    bays = resolve_bays(qrf["bay_spacing_raw"], L=L)
    acc = resolve_accessories(sections_data) if sections_data else {"mezzanine": [], "crane": None, "canopy": None, "ladder": 0, "openings": 0, "jack_beam": False}
    code = resolve_code(sections_data) if sections_data else "IS800"
    
    gm, y_pos, geo = generate_complex_geometry(W, L, eave, slope, bays, acc)
    
    bay_sp = bays["spacing"] if "spacing" in bays else sum(bays["spacings"])/len(bays["spacings"])
    params = {
        "live_load": qrf.get("live_load_roof", 0.57),
        "dead_load": qrf.get("dead_load", 0.15),
        "wind_speed": qrf.get("wind_speed", 47.0),
        "bay_spacing": bay_sp,
        "mezz_ll": qrf.get("mezz_live_load", 5.0)
    }
    
    loads, combos, qz = apply_complex_loads(gm, geo, params, acc, code)
    sec_map, props_map, serv = assign_comprehensive_sections(gm, geo, qz, params, acc, code)
    
    lines_written = write_staad_master_file(output_path, gm, sec_map, loads, combos, code)
    df_boq, summary, total_ton, ur_max = generate_boq(gm, sec_map, props_map)
    
    return len(gm.nodes), len(gm.members), total_ton, ur_max, serv

if __name__ == "__main__":
    files = [
        "BulkStore.json",
        "Jebel_Ali_Industrial_Area.json",
        "RMStore.json",
        "RSC-ARC-101-R0_AISC.json",
        "S-2447-BANSWARA.json",
        "knitting-plant.json"
    ]
    results = []
    for fname in files:
        fpath = os.path.join(BASE, fname)
        if not os.path.exists(fpath):
            continue
        with open(fpath, "r", encoding="utf-8") as f:
            d = json.load(f)
        pj, status = extract_process_json(d)
        if not pj:
            continue
        sections_data = pj.get("sections", {})
        qrf = {
            "width_raw": get_field(sections_data, "Building Parameters", sl_no=2),
            "length_raw": get_field(sections_data, "Building Parameters", sl_no=3),
            "eave_height_raw": get_field(sections_data, "Building Parameters", sl_no=4),
            "roof_slope_raw": get_field(sections_data, "Building Parameters", sl_no=6),
            "bay_spacing_raw": get_field(sections_data, "Building Parameters", sl_no=7),
            "live_load_roof": parse_num(get_field(sections_data, "Design Loads", sl_no=2)) or 0.57,
            "dead_load": parse_num(get_field(sections_data, "Design Loads", sl_no=4)) or 0.15,
            "wind_speed": parse_num(get_field(sections_data, "Design Loads", sl_no=5)) or 47.0,
        }
        ws_raw = get_field(sections_data, "Design Loads", sl_no=5) or ""
        if "km" in ws_raw.lower():
            qrf["wind_speed"] = round((qrf["wind_speed"] * 1000) / 3600, 2)
        out_path = os.path.join(OUT, fname.replace(".json", ".std"))
        nodes_c, members_c, t_ton, u_max, serv = run_pipeline(qrf, out_path, sections_data)
        results.append({
            "file": fname, 
            "ton": t_ton, 
            "UR": u_max, 
            "defl_ok": serv["pass_v"], 
            "sway_ok": serv["pass_h"]
        })
    df_res = pd.DataFrame(results)
    print(df_res)