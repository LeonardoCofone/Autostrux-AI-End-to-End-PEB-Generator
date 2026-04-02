import streamlit as st
import pandas as pd
import json
import os
import plotly.graph_objects as go

from staad_generator_pro import extract_process_json, get_field, parse_num, run_pipeline, generate_complex_geometry, resolve_dim, resolve_eave, resolve_slope, resolve_bays, resolve_accessories

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Autostrux AI | PEB Generator", 
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded"
)

def create_3d_preview(gm):
    """Genera un grafico 3D interattivo della struttura usando i nodi e i membri del GeometryManager."""
    fig = go.Figure()

    for mid, (n1, n2, mtype) in gm.members.items():
        p1 = gm.nodes[n1]
        p2 = gm.nodes[n2]
        
        # Colori e spessori per tipo di membro
        color = "#1f77b4" # default blue
        width = 2
        if "COLUMN" in mtype: color = "#d62728"; width = 5
        elif "RAFTER" in mtype: color = "#ff7f0e"; width = 5
        elif "PURLIN" in mtype or "GIRT" in mtype: color = "#7f7f7f"; width = 1
        elif "BRACING" in mtype: color = "#2ca02c"; width = 2
        elif "MEZZ" in mtype: color = "#9467bd"; width = 3
        
        fig.add_trace(go.Scatter3d(
            x=[p1[0], p2[0]],
            y=[p1[1], p2[1]],
            z=[p1[2], p2[2]],
            mode='lines',
            line=dict(color=color, width=width),
            name=mtype,
            hoverinfo='name',
            showlegend=False
        ))

    fig.update_layout(
        scene=dict(
            xaxis_title='Width (X)',
            yaxis_title='Length (Y)',
            zaxis_title='Height (Z)',
            aspectmode='data',
            camera=dict(eye=dict(x=1.5, y=1.5, z=1.2))
        ),
        margin=dict(l=0, r=0, b=0, t=0),
        height=650,
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)'
    )
    return fig

# --- SIDEBAR ---
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/c/c3/Python-logo-notext.svg/1200px-Python-logo-notext.svg.png", width=50)
    st.title("Autostrux AI")
    st.markdown("### Submission Features")
    st.markdown("""
    - 🧠 **Heuristic UR Optimization**
    - 📐 **Tapered Sections Generation**
    - ✅ **L/250 & H/150 Serviceability**
    - 🏗️ **Full 3D Geometry & Accessories**
    - 📦 **Automated BOQ & Costing**
    """)
    st.divider()
    st.info("Developed for the Kaggle AI-Powered STAAD.Pro Hackathon.")

# --- MAIN CONTENT ---
st.title("🏗️ Autostrux AI: End-to-End PEB Generator")
st.markdown("Automated 3D steel structure generator with analytical tapered section optimization.")

os.makedirs("output", exist_ok=True)
st.divider()

# File Uploader
uploaded_file = st.file_uploader("📂 Upload Quote Request Form (JSON)", type="json")

if uploaded_file is not None:
    data = json.load(uploaded_file)
    pj, status = extract_process_json(data)
    
    if pj:
        sections_data = pj.get("sections", {})
        
        # Pre-processing per la visualizzazione
        W = resolve_dim(get_field(sections_data, "Building Parameters", sl_no=2)) or 20.0
        L = resolve_dim(get_field(sections_data, "Building Parameters", sl_no=3)) or 60.0
        eave = resolve_eave(get_field(sections_data, "Building Parameters", sl_no=4))
        slope = resolve_slope(get_field(sections_data, "Building Parameters", sl_no=6))
        bays = resolve_bays(get_field(sections_data, "Building Parameters", sl_no=7), L=L)
        acc = resolve_accessories(sections_data)
        
        st.success("✅ File parsed successfully! Extracting geometry and load parameters...")
        st.markdown("<br>", unsafe_allow_html=True)

        # SPLIT LAYOUT: 3D Preview (Left) | Controls & Results (Right)
        col_left, col_right = st.columns([1.3, 1], gap="large")

        with col_left:
            st.subheader("🧊 Interactive 3D Geometry")
            with st.container(border=True):
                gm_preview, _, _ = generate_complex_geometry(W, L, eave, slope, bays, acc)
                fig_3d = create_3d_preview(gm_preview)
                st.plotly_chart(fig_3d, use_container_width=True)

        with col_right:
            st.subheader("⚙️ Analysis & Optimization")
            st.info("Start the Heuristic Engine to calculate Tapered sections, verify deflections, and generate the BOQ.")
            
            # IL PULSANTE IN ALTO
            run_btn = st.button("🚀 ESEGUI OTTIMIZZAZIONE E GENERA .STD", type="primary", use_container_width=True)
            
            if run_btn:
                with st.spinner("Calculating Stiffness Matrices and Tapered profiles..."):
                    out_name = uploaded_file.name.replace(".json", ".std")
                    out_path = os.path.join("output", out_name)
                    
                    qrf = {
                        "width_raw": W, "length_raw": L, "eave_height_raw": eave,
                        "roof_slope_raw": slope, "bay_spacing_raw": bays,
                        "live_load_roof": parse_num(get_field(sections_data, "Design Loads", sl_no=2)) or 0.57,
                        "dead_load": parse_num(get_field(sections_data, "Design Loads", sl_no=4)) or 0.15,
                        "wind_speed": parse_num(get_field(sections_data, "Design Loads", sl_no=5)) or 47.0,
                    }
                    
                    # RUN CORE ENGINE
                    nodes_c, members_c, t_ton, u_max, serv = run_pipeline(qrf, out_path, sections_data)
                    
                    st.divider()
                    st.subheader("📊 Structural Results")
                    
                    # Metriche strutturate
                    m1, m2 = st.columns(2)
                    m1.metric("Total Nodes", f"{nodes_c:,}")
                    m2.metric("3D Members", f"{members_c:,}")
                    
                    m3, m4 = st.columns(2)
                    m3.metric("Total Tonnage", f"{t_ton:.2f} t")
                    
                    ur_delta = "Optimized (Pass)" if u_max <= 1.0 else "Critical (Fail)"
                    ur_color = "normal" if u_max <= 1.0 else "inverse"
                    m4.metric("Max Utilization Ratio", f"{u_max:.3f}", delta=ur_delta, delta_color=ur_color)
                    
                    # Verifiche Frecce (Serviceability)
                    st.markdown("#### ✅ Serviceability Checks (IS 800:2007)")
                    if serv['pass_v']:
                        st.success(f"**Vertical Deflection:** PASSED (Limit: L/250)")
                    else:
                        st.error(f"**Vertical Deflection:** FAILED")
                        
                    if serv['pass_h']:
                        st.success(f"**Lateral Sway:** PASSED (Limit: H/150)")
                    else:
                        st.error(f"**Lateral Sway:** FAILED")
                        
                    # Effetto WOW
                    if u_max <= 1.0 and serv['pass_v'] and serv['pass_h']:
                        st.balloons()

                    # Pulsanti Download
                    st.markdown("#### 📥 Export Files")
                    d1, d2 = st.columns(2)
                    with d1:
                        with open(out_path, "r") as f:
                            st.download_button("🏗️ Download .STD", f, out_name, use_container_width=True)
                    with d2:
                        if os.path.exists("output/BOQ_Final.csv"):
                            with open("output/BOQ_Final.csv", "r") as f:
                                st.download_button("📦 Download BOQ", f, "BOQ_Final.csv", mime="text/csv", use_container_width=True)

        # TABELLA IN BASSO A TUTTO SCHERMO
        if run_btn and os.path.exists("output/BOQ_Final.csv"):
            st.divider()
            st.subheader("📋 Bill of Quantities (Takeoff Preview)")
            df_boq = pd.read_csv("output/BOQ_Final.csv")
            st.dataframe(df_boq, use_container_width=True, height=300)

    else:
        st.error("Invalid JSON format. Please upload a valid QRF extract.")