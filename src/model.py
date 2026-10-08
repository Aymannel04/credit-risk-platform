import os

import joblib
import pandas as pd
import xgboost as xgb
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix


def train_model():
    print("Entraînement du modèle de Risque Crédit (XGBoost)...")

    # 1. Chargement des données préparées
    try:
        X_train = pd.read_csv('data/processed/X_train.csv')
        y_train = pd.read_csv('data/processed/y_train.csv').values.ravel() # .ravel() pour aplatir en 1D
        X_test = pd.read_csv('data/processed/X_test.csv')
        y_test = pd.read_csv('data/processed/y_test.csv').values.ravel()
    except FileNotFoundError:
        print("Erreur : Données introuvables. Lance src/process.py d'abord.")
        return

    # 2. Création du modèle XGBoost
    # Note : pas de 'scale_pos_weight' ici ; le déséquilibre est traité par SMOTE (process.py)
    model = xgb.XGBClassifier(
        objective='binary:logistic',
        n_estimators=100,
        learning_rate=0.1,
        max_depth=5,
        eval_metric='logloss',
        random_state=42
    )

    # 3. Entraînement
    model.fit(X_train, y_train)

    # 4. Évaluation (Le moment de vérité)
    predictions = model.predict(X_test)
    
    print("\n--- RAPPORT DE PERFORMANCE ---")
    acc = accuracy_score(y_test, predictions)
    print(f"Précision Globale (Accuracy) : {acc*100:.2f}%")
    
    print("\nDétails par classe :")
    print(classification_report(y_test, predictions, target_names=['Bon Client', 'Mauvais Client']))

    from sklearn.metrics import roc_auc_score
    y_pred_proba = model.predict_proba(X_test)[:, 1]
    auc = roc_auc_score(y_test, y_pred_proba)
    print(f"AUC-ROC : {auc:.4f}")
    
    # 5. La Matrice de Confusion (Cruciale pour la banque)
    cm = confusion_matrix(y_test, predictions)
    
    # On affiche les chiffres bruts
    tn, fp, fn, tp = cm.ravel()
    print("\n ANALYSE DES RISQUES (Sur les données de test) :")
    print(f"Vrais Bons (Crédits accordés à raison) : {tn}")
    print(f"Faux Mauvais (Clients refusés à tort - Manque à gagner) : {fp}")
    print(f"Vrais Mauvais (Défauts évités - Argent sauvé !) : {tp}")
    print(f"Faux Bons (Crédits accordés à tort - PERTE SÈCHE) : {fn}")

    # 6. Sauvegarde
    os.makedirs('models', exist_ok=True)
    joblib.dump(model, 'models/credit_xgb_model.pkl')
    print("\n Modèle sauvegardé : models/credit_xgb_model.pkl")

if __name__ == "__main__":
    train_model()