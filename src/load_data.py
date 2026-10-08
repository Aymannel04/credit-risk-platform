import io
import os

import pandas as pd
import requests


def load_german_credit_data():
    print("Téléchargement du dataset 'German Credit'...")
    
    # URL directe vers la version brute
    url = "https://archive.ics.uci.edu/ml/machine-learning-databases/statlog/german/german.data"
    
    # Les noms des colonnes (car le fichier brut n'en a pas)
    columns = [
        'checking_account_status', 'duration_months', 'credit_history', 'purpose',
        'credit_amount', 'savings_account', 'employment_length', 'installment_rate',
        'personal_status_sex', 'other_debtors', 'residence_since', 'property',
        'age', 'other_installment_plans', 'housing', 'existing_credits',
        'job', 'people_liable', 'telephone', 'foreign_worker', 'risk'
    ]
    
    try:
        # On télécharge le contenu
        response = requests.get(url)
        if response.status_code != 200:
            print("Erreur de téléchargement.")
            return

        # On le lit comme un fichier CSV (séparateur espace)
        df = pd.read_csv(io.StringIO(response.text), sep=' ', header=None, names=columns)
        
        # TRANSFORMATION CRUCIALE :
        # Dans ce dataset : 1 = Good (Bon), 2 = Bad (Mauvais)
        # En ML, on veut : 0 = Bon, 1 = Mauvais (Cible à détecter)
        df['target'] = df['risk'].map({1: 0, 2: 1})
        df = df.drop(columns=['risk'])
        
        print(f"Données récupérées : {df.shape[0]} clients.")
        
        # Vérification du déséquilibre
        count = df['target'].value_counts()
        print("\n--- Répartition des classes ---")
        print(f"Bons clients (0)    : {count[0]}")
        print(f"Mauvais clients (1) : {count[1]}")
        
        taux_defaut = (count[1] / len(df)) * 100
        print(f"Taux de défaut   : {taux_defaut:.2f}%")
        
        # Sauvegarde
        os.makedirs('data/raw', exist_ok=True)
        df.to_csv('data/raw/german_credit.csv', index=False)
        print("Sauvegardé dans data/raw/german_credit.csv")
        
    except Exception as e:
        print(f"Erreur : {e}")

if __name__ == "__main__":
    load_german_credit_data()