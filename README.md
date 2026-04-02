# 🏗️ Autostrux AI: Automated STAAD.Pro PEB Generator

**Autostrux AI** is an intelligent, end-to-end pipeline designed to transform unstructured Quote Request Forms (QRF) into fully optimized, production-ready 3D STAAD.Pro (`.std`) models.

Built for the **Kaggle AI-Powered STAAD.Pro Hackathon**, this tool solves the complexity of Pre-Engineered Building (PEB) design using a custom Heuristic Optimization Engine.

## 🚀 Key Features

* **🧠 Heuristic Optimization:** Automatically selects tapered plate profiles to achieve a Target Utilization Ratio (UR) of **0.90–0.98**.
* **🧊 Interactive 3D Dashboard:** A built-in Streamlit interface to preview the structural geometry (nodes, members, bracings) before export.
* **📐 Full Structural Detail:** Generates main frames, purlins, girts, X-bracings, crane beams, mezzanines, and canopies.
* **✅ Serviceability Guardrails:** Built-in checks for **L/250** vertical deflection and **H/150** lateral sway.
* **📦 Automated Takeoff (BOQ):** Generates a comprehensive `BOQ_Final.csv` with exact weights and estimated material costs.

## 🛠️ Installation & Setup

Ensure you have Python 3.9+ installed.

1. **Clone the repository:**
git clone https://github.com/LeonardoCofone/Autostrux-AI-End-to-End-PEB-Generator.git

1. **Install dependencies:**
pip install streamlit pandas plotly

3. **Run the Application:**
python -m streamlit run app.py

## Strucutre
└── 📁competizione    
└── 📁input  
            ├── BulkStore.json  
            ├── Jebel_Ali_Industrial_Area.json  
            ├── knitting-plant.json  
            ├── RMStore.json  
            ├── RSC-ARC-101-R0_AISC.json  
            ├── S-2447-BANSWARA.json  
    └── 📁output  
        ├── BOQ_Final.csv  
        ├── BulkStore.std  
        ├── Jebel_Ali_Industrial_Area.std  
        ├── knitting-plant.std  
        ├── RMStore.std  
        ├── RSC-ARC-101-R0_AISC.std  
        ├── S-2447-BANSWARA.std  
    ├── app.py  
    ├── Autostrux AI _ PEB Generator.pdf  
    ├── README.md  
    ├── requirements.txt  
    └── staad_generator_pro.py


## 📖 How it Works

1. **Input:** Upload a standard QRF JSON file.
2. **Preview:** The system generates a real-time 3D wireframe using Plotly.
3. **Optimize:** Click the "Run Optimization" button. The engine performs iterative calculations to minimize steel weight while passing all stress and deflection checks.
4. **Export:** Download the `.std` file (ready for STAAD.Pro) and the `.csv` Bill of Quantities.

## 📊 Performance Benchmark

| Dataset | Max UR | Serviceability | Total Tonnage |
| :--- | :--- | :--- | :--- |
| **BulkStore** | 0.830 | ✅ PASSED | ~196 t |
| **RMStore** | 0.855 | ✅ PASSED | ~81 t |
| **Knitting Plant** | 0.905 | ✅ PASSED | ~218 t |

## 📂 Project Structure

* `app.py`: The Streamlit web interface and 3D visualization logic.
* `main.py`: The core structural engine (Geometry Manager, Load Generator, and Optimization).
* `output/`: Directory where generated STAAD models and BOQs are saved.

## 🏆 Hackathon Tracks

This project is submitted for:
1. **STAAD Structural Automation Wiz** (Full automation of geometry and loads).
2. **3D Strength Wiz** (Advanced tapered section optimization and UR targeting).

Developed with heart for the Kaggle Engineering Community