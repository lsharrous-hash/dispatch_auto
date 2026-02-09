import pandas as pd
import io
import datetime
from shapely.geometry import shape, Point

def load_data(uploaded_file):
    """Charge le fichier avec une détection robuste (CSV/Excel)."""
    file_name = uploaded_file.name
    raw_content = uploaded_file.getvalue()
    try:
        if file_name.lower().endswith('.xlsx'):
            df = pd.read_excel(uploaded_file, dtype=str)
        else:
            text = raw_content.decode('utf-8', errors='ignore')
            df = pd.read_csv(io.StringIO(text), sep=None, engine='python', dtype=str)
    except Exception as e:
        return None, f"Erreur de lecture : {e}"

    def split_gps(val):
        try:
            if pd.isna(val) or ',' not in str(val): return None, None
            lat, lon = str(val).replace('"', '').split(',')
            return float(lat), float(lon)
        except: return None, None

    # Support pour différents formats de colonnes GPS
    gps_columns = [
        "Receiver to (Latitude,Longitude)",
        "GPS",
        "Coordinates",
        "LatLng"
    ]
    
    for col in gps_columns:
        if col in df.columns:
            df[['lat', 'lon']] = df[col].apply(lambda x: pd.Series(split_gps(x)))
            break
    
    # Convertir lat/lon en float si présents
    if 'lat' in df.columns:
        df['lat'] = pd.to_numeric(df['lat'], errors='coerce')
    if 'lon' in df.columns:
        df['lon'] = pd.to_numeric(df['lon'], errors='coerce')
    
    return df, None

def filtrer_colis_par_zone(df, last_draw):
    """Vérifie quels points GPS sont dans la zone dessinée."""
    if not last_draw or 'geometry' not in last_draw:
        return pd.DataFrame()
    
    polygon = shape(last_draw['geometry'])
    
    def est_dedans(row):
        if pd.isna(row['lat']) or pd.isna(row['lon']): return False
        point = Point(row['lon'], row['lat']) # Longitude, Latitude
        return polygon.contains(point)
    
    mask = df.apply(est_dedans, axis=1)
    return df[mask]

def preparer_telechargement_excel(df_selection):
    """Génère un fichier Excel en mémoire pour le téléchargement Web."""
    output = io.BytesIO()
    df_export = df_selection.copy()
    
    # Renommer lat/lon en Latitude/Longitude pour plus de clarté
    if 'lat' in df_export.columns:
        df_export = df_export.rename(columns={'lat': 'Latitude'})
    if 'lon' in df_export.columns:
        df_export = df_export.rename(columns={'lon': 'Longitude'})
    
    # Ajouter/renommer la colonne Ville si elle n'existe pas
    if 'Ville' not in df_export.columns:
        # Chercher dans les colonnes possibles
        city_cols = ["Receiver's City", "Receivers City", "Receiver's Region/Province"]
        for col in city_cols:
            if col in df_export.columns:
                df_export['Ville'] = df_export[col]
                break
    
    # Réorganiser les colonnes pour mettre les plus importantes en premier
    priority_cols = ['Tracking No.', 'Sort Code', 'Ville', "Receiver's Detail Address", 'Latitude', 'Longitude']
    existing_priority = [c for c in priority_cols if c in df_export.columns]
    other_cols = [c for c in df_export.columns if c not in existing_priority]
    df_export = df_export[existing_priority + other_cols]
    
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_export.to_excel(writer, index=False)
    return output.getvalue()
