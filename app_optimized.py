import streamlit as st
import pandas as pd
import folium
from folium.plugins import Draw, FastMarkerCluster
from streamlit_folium import st_folium
import json
import os
from datetime import datetime
from data_processor import load_data, preparer_telechargement_excel
from shapely.geometry import shape, Point
import zipfile
import io

# Configuration
st.set_page_config(layout="wide", page_title="Dispatch Auto - JNR Transport")

PATTERNS_FILE = "driver_patterns.json"

# === CACHE ET OPTIMISATIONS ===

@st.cache_data
def load_and_process_file(file_content, file_name):
    """Cache le chargement des fichiers."""
    import io as io_module
    if file_name.lower().endswith('.xlsx') or file_name.lower().endswith('.xls'):
        df = pd.read_excel(io_module.BytesIO(file_content), dtype=str)
    else:
        text = file_content.decode('utf-8', errors='ignore')
        df = pd.read_csv(io_module.StringIO(text), sep=None, engine='python', dtype=str)
    
    # Parser GPS
    def split_gps(val):
        try:
            if pd.isna(val) or ',' not in str(val): return None, None
            lat, lon = str(val).replace('"', '').split(',')
            return float(lat), float(lon)
        except: return None, None
    
    gps_columns = ["Receiver to (Latitude,Longitude)", "GPS", "Coordinates", "LatLng"]
    for col in gps_columns:
        if col in df.columns:
            df[['lat', 'lon']] = df[col].apply(lambda x: pd.Series(split_gps(x)))
            break
    
    if 'lat' in df.columns:
        df['lat'] = pd.to_numeric(df['lat'], errors='coerce')
    if 'lon' in df.columns:
        df['lon'] = pd.to_numeric(df['lon'], errors='coerce')
    
    return df

# === FONCTIONS UTILITAIRES ===

def load_patterns():
    """Charge les patterns sauvegardés depuis le fichier JSON."""
    if os.path.exists(PATTERNS_FILE):
        with open(PATTERNS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"drivers": {}, "updated_at": None}

def save_patterns(patterns):
    """Sauvegarde les patterns dans le fichier JSON."""
    patterns["updated_at"] = datetime.now().isoformat()
    with open(PATTERNS_FILE, 'w', encoding='utf-8') as f:
        json.dump(patterns, f, ensure_ascii=False, indent=2)

def get_driver_color(index):
    """Retourne une couleur unique pour chaque chauffeur."""
    colors = [
        "#e74c3c", "#3498db", "#2ecc71", "#f39c12", "#9b59b6",
        "#1abc9c", "#e67e22", "#34495e", "#16a085", "#c0392b",
        "#2980b9", "#27ae60", "#d35400", "#8e44ad", "#17a2b8"
    ]
    return colors[index % len(colors)]

def point_in_zones(lat, lon, zones):
    """Vérifie si un point est dans une des zones."""
    point = Point(lon, lat)
    for zone in zones:
        polygon = shape(zone)
        if polygon.contains(point):
            return True
    return False

def filter_by_driver_zones(df, zones):
    """Filtre les colis qui sont dans les zones d'un chauffeur."""
    if not zones:
        return pd.DataFrame()
    
    def is_in_zones(row):
        if pd.isna(row['lat']) or pd.isna(row['lon']):
            return False
        return point_in_zones(row['lat'], row['lon'], zones)
    
    mask = df.apply(is_in_zones, axis=1)
    return df[mask]

def auto_dispatch(df, patterns):
    """Dispatch automatique basé sur les patterns sauvegardés."""
    results = {}
    assigned_indices = set()
    
    for driver_name, driver_data in patterns.get("drivers", {}).items():
        zones = driver_data.get("zones", [])
        if not zones:
            continue
        
        driver_df = filter_by_driver_zones(df, zones)
        driver_df = driver_df[~driver_df.index.isin(assigned_indices)]
        
        if not driver_df.empty:
            results[driver_name] = driver_df
            assigned_indices.update(driver_df.index.tolist())
    
    unassigned = df[~df.index.isin(assigned_indices)]
    if not unassigned.empty:
        results["_NON_ASSIGNES"] = unassigned
    
    return results

def create_zip_with_excels(dispatch_results):
    """Crée un ZIP contenant tous les fichiers Excel."""
    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for driver_name, driver_df in dispatch_results.items():
            if driver_df.empty:
                continue
            excel_data = preparer_telechargement_excel(driver_df)
            safe_name = driver_name.replace(" ", "_").replace("/", "-")
            filename = f"{safe_name}.xlsx"
            zip_file.writestr(filename, excel_data)
    
    zip_buffer.seek(0)
    return zip_buffer.getvalue()

# === INTERFACE ===

st.title("🚚 Dispatch Automatique - JNR Transport")

patterns = load_patterns()

tab1, tab2 = st.tabs(["📍 Configuration des Zones", "⚡ Dispatch Automatique"])

# === TAB 1: CONFIGURATION DES ZONES ===
with tab1:
    st.markdown("### Définir les zones de livraison par chauffeur")
    
    # Options d'affichage
    col_options = st.columns([2, 1, 1])
    with col_options[0]:
        uploaded_ref = st.file_uploader(
            "Charger un fichier de référence", 
            type=['csv', 'xlsx', 'xls'],
            key="ref_file"
        )
    with col_options[1]:
        sample_rate = st.selectbox(
            "Afficher 1 point sur",
            options=[1, 5, 10, 20],
            index=1,
            help="Réduire pour plus de fluidité"
        )
    with col_options[2]:
        show_points = st.checkbox("Afficher les points", value=True)
    
    col_left, col_right = st.columns([3, 1])
    
    with col_right:
        st.markdown("#### 👥 Chauffeurs")
        
        new_driver = st.text_input("Nom du chauffeur", placeholder="Ex: Mohamed")
        if st.button("➕ Ajouter", use_container_width=True):
            if new_driver and new_driver.strip():
                driver_name = new_driver.strip()
                if driver_name not in patterns.get("drivers", {}):
                    if "drivers" not in patterns:
                        patterns["drivers"] = {}
                    patterns["drivers"][driver_name] = {"zones": [], "color": get_driver_color(len(patterns["drivers"]))}
                    save_patterns(patterns)
                    st.success(f"✅ {driver_name} ajouté!")
                    st.rerun()
                else:
                    st.warning("Ce chauffeur existe déjà")
        
        st.markdown("---")
        
        selected_driver = st.selectbox(
            "Sélectionner un chauffeur pour dessiner ses zones:",
            options=list(patterns.get("drivers", {}).keys()) or ["Aucun chauffeur"],
            key="driver_select"
        )
        
        st.markdown("#### 📊 Zones définies")
        for driver, data in patterns.get("drivers", {}).items():
            zone_count = len(data.get("zones", []))
            color = data.get("color", "#666")
            st.markdown(f"""
                <div style="display:flex; align-items:center; gap:8px; margin:4px 0; padding:8px; background:#f0f0f0; border-radius:4px; border-left:4px solid {color};">
                    <span style="font-weight:bold;">{driver}</span>
                    <span style="color:#666;">({zone_count} zone{'s' if zone_count > 1 else ''})</span>
                </div>
            """, unsafe_allow_html=True)
        
        st.markdown("---")
        
        if selected_driver and selected_driver != "Aucun chauffeur":
            st.markdown(f"**Actions pour {selected_driver}:**")
            
            if st.button("🗑️ Supprimer ses zones", use_container_width=True):
                patterns["drivers"][selected_driver]["zones"] = []
                save_patterns(patterns)
                st.success("Zones supprimées!")
                st.rerun()
            
            if st.button("❌ Supprimer le chauffeur", use_container_width=True):
                del patterns["drivers"][selected_driver]
                save_patterns(patterns)
                st.success("Chauffeur supprimé!")
                st.rerun()
    
    with col_left:
        center_lat, center_lon = 49.25, 4.03
        
        df_map = pd.DataFrame()
        if uploaded_ref:
            file_content = uploaded_ref.getvalue()
            df_ref = load_and_process_file(file_content, uploaded_ref.name)
            df_map = df_ref.dropna(subset=['lat', 'lon']).copy()
            if not df_map.empty:
                center_lat = df_map['lat'].mean()
                center_lon = df_map['lon'].mean()
        
        m = folium.Map(location=[center_lat, center_lon], zoom_start=10, prefer_canvas=True)
        
        Draw(
            export=False,
            draw_options={
                'polyline': False, 
                'circle': False, 
                'marker': False, 
                'circlemarker': False, 
                'polygon': True, 
                'rectangle': True
            }
        ).add_to(m)
        
        # Afficher les zones existantes
        for driver, data in patterns.get("drivers", {}).items():
            color = data.get("color", "#666")
            for zone in data.get("zones", []):
                folium.GeoJson(
                    zone,
                    style_function=lambda x, c=color: {
                        'fillColor': c,
                        'color': c,
                        'weight': 2,
                        'fillOpacity': 0.3
                    },
                    tooltip=driver
                ).add_to(m)
        
        # Afficher les points (échantillonnés) avec FastMarkerCluster
        if show_points and not df_map.empty:
            df_sampled = df_map.iloc[::sample_rate]
            
            # Utiliser FastMarkerCluster pour de meilleures performances
            callback = """
            function (row) {
                var marker = L.circleMarker(new L.LatLng(row[0], row[1]), {
                    radius: 4,
                    color: '#333',
                    fillColor: '#333',
                    fillOpacity: 0.6
                });
                return marker;
            }
            """
            
            points_data = df_sampled[['lat', 'lon']].values.tolist()
            FastMarkerCluster(data=points_data, callback=callback).add_to(m)
            
            st.caption(f"📍 {len(df_sampled)}/{len(df_map)} points affichés (1 sur {sample_rate})")
        
        output = st_folium(m, width="100%", height=500, key="config_map", returned_objects=["all_drawings"])
        
        # Capturer les nouvelles zones
        if output and output.get('all_drawings'):
            last_draw = output['all_drawings'][-1]
            if last_draw and 'geometry' in last_draw:
                st.info(f"🎯 Zone détectée! Cliquez pour l'assigner à **{selected_driver}**")
                
                if st.button(f"✅ Assigner cette zone à {selected_driver}", type="primary"):
                    if selected_driver and selected_driver != "Aucun chauffeur":
                        geometry = last_draw['geometry']
                        patterns["drivers"][selected_driver]["zones"].append(geometry)
                        save_patterns(patterns)
                        st.success(f"Zone ajoutée pour {selected_driver}!")
                        st.rerun()

# === TAB 2: DISPATCH AUTOMATIQUE ===
with tab2:
    st.markdown("### Importer et dispatcher automatiquement")
    
    total_zones = sum(len(d.get("zones", [])) for d in patterns.get("drivers", {}).values())
    
    if total_zones == 0:
        st.warning("⚠️ Aucune zone n'est configurée. Allez dans l'onglet 'Configuration des Zones' pour définir les zones de chaque chauffeur.")
    else:
        st.success(f"✅ {len(patterns.get('drivers', {}))} chauffeur(s) configuré(s) avec {total_zones} zone(s) au total")
        
        with st.expander("📋 Voir les chauffeurs configurés"):
            for driver, data in patterns.get("drivers", {}).items():
                zones = data.get("zones", [])
                st.write(f"**{driver}**: {len(zones)} zone(s)")
    
    st.markdown("---")
    
    uploaded_dispatch = st.file_uploader(
        "📁 Charger le fichier Cainiao à dispatcher",
        type=['csv', 'xlsx', 'xls'],
        key="dispatch_file"
    )
    
    if uploaded_dispatch and total_zones > 0:
        file_content = uploaded_dispatch.getvalue()
        df_dispatch = load_and_process_file(file_content, uploaded_dispatch.name)
        
        df_with_coords = df_dispatch.dropna(subset=['lat', 'lon']).copy()
        
        st.info(f"📦 **{len(df_dispatch)}** colis chargés ({len(df_with_coords)} avec coordonnées GPS)")
        
        if st.button("🚀 Lancer le dispatch automatique", type="primary", use_container_width=True):
            with st.spinner("Dispatch en cours..."):
                results = auto_dispatch(df_with_coords, patterns)
            
            st.markdown("### 📊 Résultats du dispatch")
            
            cols = st.columns(3)
            col_idx = 0
            
            total_assigned = 0
            for driver_name, driver_df in results.items():
                if driver_name == "_NON_ASSIGNES":
                    continue
                
                with cols[col_idx % 3]:
                    color = patterns["drivers"].get(driver_name, {}).get("color", "#666")
                    st.markdown(f"""
                        <div style="padding:15px; background:white; border-radius:8px; border-left:5px solid {color}; margin-bottom:10px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                            <h4 style="margin:0; color:{color};">{driver_name}</h4>
                            <p style="font-size:24px; font-weight:bold; margin:5px 0;">{len(driver_df)} colis</p>
                        </div>
                    """, unsafe_allow_html=True)
                    total_assigned += len(driver_df)
                col_idx += 1
            
            if "_NON_ASSIGNES" in results:
                unassigned = results["_NON_ASSIGNES"]
                st.warning(f"⚠️ **{len(unassigned)}** colis non assignés (hors zones définies)")
                
                with st.expander("Voir les colis non assignés"):
                    display_cols = [c for c in ["Tracking No.", "Sort Code", "Receiver's City"] if c in unassigned.columns]
                    st.dataframe(unassigned[display_cols].head(50))
            
            st.markdown("---")
            st.markdown("### 📥 Télécharger les fichiers")
            
            zip_data = create_zip_with_excels(results)
            st.download_button(
                label="📦 Télécharger TOUS les fichiers (ZIP)",
                data=zip_data,
                file_name=f"Dispatch_{datetime.now().strftime('%Y%m%d_%H%M')}.zip",
                mime="application/zip",
                use_container_width=True
            )
            
            st.markdown("---")
            st.markdown("**Ou télécharger individuellement:**")
            for driver_name, driver_df in results.items():
                if driver_df.empty:
                    continue
                
                display_name = "Non assignés" if driver_name == "_NON_ASSIGNES" else driver_name
                excel_data = preparer_telechargement_excel(driver_df)
                
                st.download_button(
                    label=f"📄 {display_name} ({len(driver_df)} colis)",
                    data=excel_data,
                    file_name=f"{driver_name.replace(' ', '_')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key=f"dl_{driver_name}"
                )

# === SIDEBAR ===
with st.sidebar:
    st.markdown("## ⚙️ Gestion")
    
    if patterns.get("drivers"):
        st.download_button(
            label="💾 Exporter la config",
            data=json.dumps(patterns, ensure_ascii=False, indent=2),
            file_name="driver_patterns_backup.json",
            mime="application/json",
            use_container_width=True
        )
    
    st.markdown("---")
    uploaded_patterns = st.file_uploader("📂 Importer une config", type=['json'], key="import_patterns")
    if uploaded_patterns:
        try:
            imported = json.load(uploaded_patterns)
            if st.button("✅ Appliquer cette configuration"):
                save_patterns(imported)
                st.success("Configuration importée!")
                st.rerun()
        except:
            st.error("Fichier JSON invalide")
    
    st.markdown("---")
    st.markdown("### 📖 Guide rapide")
    st.markdown("""
    1. **Ajouter chauffeurs** et dessiner leurs zones
    2. **Réduire les points** (1 sur 10) pour plus de fluidité
    3. **Dispatcher** dans l'onglet 2
    """)
    
    if patterns.get("updated_at"):
        st.caption(f"Mis à jour: {patterns['updated_at'][:16]}")
