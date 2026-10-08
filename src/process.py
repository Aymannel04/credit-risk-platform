import os

import joblib
import pandas as pd
from imblearn.over_sampling import SMOTE
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder, StandardScaler


def process_data():
    print(" Démarrage du prétraitement...")
    
    # 1. Chargement
    try:
        df = pd.read_csv('data/raw/german_credit.csv')
    except FileNotFoundError:
        print("Erreur : Fichier data/raw/german_credit.csv introuvable.")
        return

    # 2. Séparation Target / Features
    X = df.drop('target', axis=1)
    y = df['target']

    # 3. Encodage des variables texte (ex: "A34" -> 0, 1, 2...)
    # On repère les colonnes qui contiennent du texte (object)
    cat_columns = X.select_dtypes(include=['object', 'str']).columns
    
    # On sauvegarde les encodeurs pour pouvoir les réutiliser dans l'App plus tard
    encoders = {}
    for col in cat_columns:
        le = LabelEncoder()
        X[col] = le.fit_transform(X[col])
        encoders[col] = le
    
    # On sauvegarde ce dictionnaire d'encodeurs
    os.makedirs('models', exist_ok=True)
    joblib.dump(encoders, 'models/encoders.pkl')

    # 4. Split Train / Test (Avant le SMOTE ! Très important)
    # On garde 20% pour le test final
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

    print(f"Avant SMOTE : {sum(y_train==1)} mauvais payeurs dans le train set.")

    # 5. Application du SMOTE (Seulement sur le Train !)
    smote = SMOTE(random_state=42)
    X_train_resampled, y_train_resampled = smote.fit_resample(X_train, y_train)

    print(f"Après SMOTE : {sum(y_train_resampled==1)} mauvais payeurs (Équilibrage 50/50 réussi).")

    # 6. Scaling (Mise à l'échelle)
    # Pour que "Age=30" et "Crédit=5000" aient le même poids mathématique
    scaler = StandardScaler()
    X_train_final = scaler.fit_transform(X_train_resampled)
    X_test_final = scaler.transform(X_test) # On utilise le même scaler
    
    # Sauvegarde du scaler
    joblib.dump(scaler, 'models/scaler.pkl')

    # 7. Sauvegarde des données prêtes pour le ML
    os.makedirs('data/processed', exist_ok=True)
    
    # On remet en DataFrame pour la lisibilité (optionnel mais propre)
    pd.DataFrame(X_train_final, columns=X.columns).to_csv('data/processed/X_train.csv', index=False)
    pd.DataFrame(y_train_resampled).to_csv('data/processed/y_train.csv', index=False)
    pd.DataFrame(X_test_final, columns=X.columns).to_csv('data/processed/X_test.csv', index=False)
    pd.DataFrame(y_test).to_csv('data/processed/y_test.csv', index=False)

    print("Données traitées et sauvegardées dans data/processed/")

if __name__ == "__main__":
    process_data()