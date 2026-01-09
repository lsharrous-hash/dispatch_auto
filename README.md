# 🚚 Dispatch Automatique - JNR Transport

Outil de découpage automatique des tournées basé sur des zones géographiques prédéfinies par chauffeur.

## 🎯 Fonctionnalités

### 1. Configuration des Zones (une seule fois)
- Ajouter les chauffeurs
- Dessiner les zones de livraison de chaque chauffeur sur la carte
- Les zones sont sauvegardées automatiquement dans `driver_patterns.json`

### 2. Dispatch Automatique (quotidien)
- Importer le fichier Cainiao (Excel/CSV)
- L'outil assigne automatiquement chaque colis au bon chauffeur selon sa position GPS
- Télécharger un ZIP avec tous les fichiers Excel par chauffeur

## 🚀 Installation

```bash
pip install -r requirements.txt
```

## ▶️ Lancement

```bash
streamlit run app_enhanced.py
```

## 📁 Structure des fichiers

```
dispatch-tool/
├── app_enhanced.py      # Application principale améliorée
├── data_processor.py    # Fonctions de traitement des données
├── requirements.txt     # Dépendances Python
├── driver_patterns.json # Configuration sauvegardée (auto-généré)
└── README.md
```

## 💾 Sauvegarde/Restauration

- **Exporter**: Bouton dans la sidebar pour télécharger `driver_patterns_backup.json`
- **Importer**: Uploader un fichier JSON pour restaurer une configuration

## 📋 Format du fichier Cainiao attendu

Colonnes requises:
- `Tracking No.` : Numéro de suivi
- `Sort Code` : Code postal
- `Receiver's City` : Ville
- `Receiver's Detail Address` : Adresse
- `Receiver to (Latitude,Longitude)` : Coordonnées GPS (format: "lat,lon")

## 🎨 Couleurs des chauffeurs

Chaque chauffeur se voit attribuer une couleur unique automatiquement pour faciliter la visualisation sur la carte.

---

Développé pour JNR Transport - Trizee
