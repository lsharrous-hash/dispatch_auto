import streamlit as st
import pandas as pd
import folium
from folium.plugins import Draw
from streamlit_folium import st_folium
import json
import os
from datetime import datetime
from data_processor import load_data, preparer_telechargement_excel
from shapely.geometry import shape, Point, mapping
from shapely.ops import unary_union
import zipfile
import io

# Configuration
st.set_page_config(layout="wide", page_title="Dispatch Auto - JNR Transport")

PATTERNS_FILE = "driver_patterns.json"

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
        # Exclure les colis déjà assignés
        driver_df = driver_df[~driver_df.index.isin(assigned_indices)]
        
        if not driver_df.empty:
            results[driver_name] = driver_df
            assigned_indices.update(driver_df.index.tolist())
    
    # Colis non assignés
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
            
            # Préparer l'Excel
            excel_data = preparer_telechargement_excel(driver_df)
            
            # Nom du fichier
            safe_name = driver_name.replace(" ", "_").replace("/", "-")
            filename = f"Tournee_{safe_name}.xlsx"
            
            zip_file.writestr(filename, excel_data)
    
    zip_buffer.seek(0)
    return zip_buffer.getvalue()

# === INTERFACE ===

st.title("🚚 Dispatch Automatique - JNR Transport")

# Charger les patterns existants
patterns = load_patterns()

# Tabs pour les différents modes
tab1, tab2 = st.tabs(["📍 Configuration des Zones", "⚡ Dispatch Automatique"])

# === TAB 1: CONFIGURATION DES ZONES ===
with tab1:
    st.markdown("### Définir les zones de livraison par chauffeur")
    
    # Fichier de référence pour visualiser les points
    uploaded_ref = st.file_uploader(
        "Charger un fichier de référence (pour visualiser les points)", 
        type=['csv', 'xlsx'],
        key="ref_file"
    )
    
    col_left, col_right = st.columns([3, 1])
    
    with col_right:
        st.markdown("#### 👥 Chauffeurs")
        
        # Ajouter un chauffeur
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
        
        # Liste des chauffeurs
        selected_driver = st.selectbox(
            "Sélectionner un chauffeur pour dessiner ses zones:",
            options=list(patterns.get("drivers", {}).keys()) or ["Aucun chauffeur"],
            key="driver_select"
        )
        
        # Afficher les chauffeurs et leurs stats
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
        
        # Actions sur le chauffeur sélectionné
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
        # Carte avec les zones existantes et les points
        center_lat, center_lon = 49.25, 4.03  # Centre approximatif (Reims)
        
        df_map = pd.DataFrame()
        if uploaded_ref:
            df_ref, error = load_data(uploaded_ref)
            if not error:
                df_map = df_ref.dropna(subset=['lat', 'lon']).copy()
                center_lat = df_map['lat'].mean()
                center_lon = df_map['lon'].mean()
        
        m = folium.Map(location=[center_lat, center_lon], zoom_start=10)
        
        # Ajouter l'outil de dessin
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
        
        # Afficher les zones existantes de tous les chauffeurs
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
        
        # Afficher les points du fichier de référence
        if not df_map.empty:
            for _, row in df_map.iterrows():
                cp = str(row.get('Sort Code', ''))
                folium.CircleMarker(
                    location=[row['lat'], row['lon']],
                    radius=3,
                    color="#333",
                    fill=True,
                    fillOpacity=0.6,
                    popup=f"{row.get('Receiver City', row.get('Receivers City', 'N/A'))} - {cp}"
                ).add_to(m)
        
        output = st_folium(m, width="100%", height=550, key="config_map")
        
        # Capturer les nouvelles zones dessinées
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
    
    # Vérifier qu'il y a des patterns configurés
    total_zones = sum(len(d.get("zones", [])) for d in patterns.get("drivers", {}).values())
    
    if total_zones == 0:
        st.warning("⚠️ Aucune zone n'est configurée. Allez dans l'onglet 'Configuration des Zones' pour définir les zones de chaque chauffeur.")
    else:
        st.success(f"✅ {len(patterns.get('drivers', {}))} chauffeur(s) configuré(s) avec {total_zones} zone(s) au total")
        
        # Afficher un résumé
        with st.expander("📋 Voir les chauffeurs configurés"):
            for driver, data in patterns.get("drivers", {}).items():
                zones = data.get("zones", [])
                st.write(f"**{driver}**: {len(zones)} zone(s)")
    
    st.markdown("---")
    
    # Upload du fichier à dispatcher
    uploaded_dispatch = st.file_uploader(
        "📁 Charger le fichier Cainiao à dispatcher",
        type=['csv', 'xlsx'],
        key="dispatch_file"
    )
    
    if uploaded_dispatch and total_zones > 0:
        df_dispatch, error = load_data(uploaded_dispatch)
        
        if error:
            st.error(error)
        else:
            df_with_coords = df_dispatch.dropna(subset=['lat', 'lon']).copy()
            
            st.info(f"📦 **{len(df_dispatch)}** colis chargés ({len(df_with_coords)} avec coordonnées GPS)")
            
            if st.button("🚀 Lancer le dispatch automatique", type="primary", use_container_width=True):
                with st.spinner("Dispatch en cours..."):
                    results = auto_dispatch(df_with_coords, patterns)
                
                st.markdown("### 📊 Résultats du dispatch")
                
                # Afficher les résultats
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
                
                # Colis non assignés
                if "_NON_ASSIGNES" in results:
                    unassigned = results["_NON_ASSIGNES"]
                    st.warning(f"⚠️ **{len(unassigned)}** colis non assignés (hors zones définies)")
                    
                    with st.expander("Voir les colis non assignés"):
                        st.dataframe(unassigned[["Tracking No.", "Sort Code", "Receiver's City"]].head(50))
                
                st.markdown("---")
                
                # Téléchargement
                st.markdown("### 📥 Télécharger les fichiers")
                
                # Option 1: ZIP avec tous les fichiers
                zip_data = create_zip_with_excels(results)
                st.download_button(
                    label="📦 Télécharger TOUS les fichiers (ZIP)",
                    data=zip_data,
                    file_name=f"Dispatch_{datetime.now().strftime('%Y%m%d_%H%M')}.zip",
                    mime="application/zip",
                    use_container_width=True
                )
                
                st.markdown("---")
                
                # Option 2: Fichiers individuels
                st.markdown("**Ou télécharger individuellement:**")
                for driver_name, driver_df in results.items():
                    if driver_df.empty:
                        continue
                    
                    display_name = "Non assignés" if driver_name == "_NON_ASSIGNES" else driver_name
                    excel_data = preparer_telechargement_excel(driver_df)
                    
                    st.download_button(
                        label=f"📄 {display_name} ({len(driver_df)} colis)",
                        data=excel_data,
                        file_name=f"Tournee_{driver_name.replace(' ', '_')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key=f"dl_{driver_name}"
                    )

# === SIDEBAR: GESTION DES PATTERNS ===
with st.sidebar:
    st.markdown("## ⚙️ Gestion")
    
    # Export des patterns
    if patterns.get("drivers"):
        st.download_button(
            label="💾 Exporter la config",
            data=json.dumps(patterns, ensure_ascii=False, indent=2),
            file_name="driver_patterns_backup.json",
            mime="application/json",
            use_container_width=True
        )
    
    # Import des patterns
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
    
    # Infos
    st.markdown("---")
    st.markdown("### 📖 Guide")
    st.markdown("""
    1. **Configurer les zones**: Ajoutez vos chauffeurs et dessinez leurs zones sur la carte
    2. **Sauvegarder**: Les zones sont auto-sauvegardées
    3. **Dispatcher**: Importez votre fichier Cainiao et téléchargez les tournées
    """)
    
    if patterns.get("updated_at"):
        st.caption(f"Dernière mise à jour: {patterns['updated_at'][:16]}")