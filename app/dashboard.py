import joblib
import matplotlib.pyplot as plt
import pandas as pd
import shap
import streamlit as st

# 1. Configuration
st.set_page_config(page_title="Credit Scoring AI", page_icon="🏦", layout="wide")

# 2. Chargement des outils (Cerveau + Traducteurs)
@st.cache_resource
def load_assets():
    model = joblib.load('models/credit_xgb_model.pkl')
    scaler = joblib.load('models/scaler.pkl')
    encoders = joblib.load('models/encoders.pkl')
    return model, scaler, encoders

try:
    model, scaler, encoders = load_assets()
except FileNotFoundError:
    st.error("Fichiers manquants. As-tu bien lancé src/process.py et src/model.py ?")
    st.stop()

# 3. Interface Latérale (Saisie Banquier)
st.sidebar.header("Profil du Client")
st.sidebar.markdown("Entrez les infos du demandeur de crédit.")

def user_input_features():
    # On recrée les champs les plus importants (basé sur le dataset German Credit)
    # Note : Pour faire simple, on simule certaines valeurs secondaires par la moyenne
    
    # Variables Numériques
    age = st.sidebar.slider("Age", 18, 90, 30)
    credit_amount = st.sidebar.number_input("Montant du Crédit (DM)", 500, 20000, 5000)
    duration = st.sidebar.slider("Durée (Mois)", 6, 72, 24)
    
    # Variables Catégorielles (Listes déroulantes)
    # On reprend les codes du dataset (A11 = < 0 DM, A12 = < 200 DM, etc.)
    checking_status = st.sidebar.selectbox("Compte Courant", ["A11 (< 0 DM)", "A12 (0-200 DM)", "A13 (> 200 DM)", "A14 (Pas de compte)"])
    history = st.sidebar.selectbox("Historique Crédit", ["A30 (Nul)", "A31 (Tout payé)", "A32 (En cours sans retard)", "A33 (Retard passé)", "A34 (Compte critique)"])
    purpose = st.sidebar.selectbox("Motif", ["A40 (Voiture Neuve)", "A41 (Voiture Occasion)", "A42 (Meubles)", "A43 (Radio/TV)", "A46 (Education)"])
    
    # On stocke ça dans un Dictionnaire
    data = {
        'age': age,
        'credit_amount': credit_amount,
        'duration_months': duration,
        # On doit mapper les choix texte vers les codes Axx originaux pour que l'encodeur comprenne
        'checking_account_status': checking_status.split(' ')[0],
        'credit_history': history.split(' ')[0],
        'purpose': purpose.split(' ')[0],
        
        # Pour les autres colonnes moins importantes, on met des valeurs par défaut (mode/moyenne)
        # pour éviter de faire un formulaire de 20 questions
        'savings_account': 'A61', 
        'employment_length': 'A73',
        'installment_rate': 3,
        'personal_status_sex': 'A93',
        'other_debtors': 'A101',
        'residence_since': 3,
        'property': 'A121',
        'other_installment_plans': 'A143',
        'housing': 'A152',
        'existing_credits': 1,
        'job': 'A173',
        'people_liable': 1,
        'telephone': 'A191',
        'foreign_worker': 'A201'
    }
    return pd.DataFrame([data])

input_df = user_input_features()

# 4. Prétraitement (Même cuisine que dans process.py)
# A. Encodage (Texte -> Chiffres)
for col, encoder in encoders.items():
    if col in input_df.columns:
        # On gère le cas où l'utilisateur entre une valeur inconnue (sécurité)
        try:
            input_df[col] = encoder.transform(input_df[col])
        except:
            input_df[col] = 0 # Valeur par défaut

# B. Scaling (Mise à l'échelle)
# Attention : il faut que les colonnes soient dans le bon ordre
# On recharge les colonnes d'entraînement pour aligner
expected_cols = scaler.feature_names_in_ if hasattr(scaler, 'feature_names_in_') else input_df.columns
input_df = input_df[expected_cols] 
input_scaled = scaler.transform(input_df)

# 5. Prédiction & SHAP
st.title("Analyse de Risque Crédit")

col1, col2 = st.columns(2)

# --- Prédiction ---
prediction = model.predict(input_scaled)[0]
prob = model.predict_proba(input_scaled)[0][1] # Probabilité d'être "Mauvais" (Classe 1)

with col1:
    st.subheader("Verdict de l'IA")
    if prediction == 0:
        st.success("CRÉDIT ACCORDÉ")
        st.metric("Score de Confiance", f"{(1-prob)*100:.1f}% Sûr")
    else:
        st.error("CRÉDIT REFUSÉ")
        st.metric("Probabilité de Défaut", f"{prob*100:.1f}% Risqué")

# --- Explication (SHAP) ---
with col2:
    st.subheader("Pourquoi cette décision ?")
    st.markdown("L'IA explique quels facteurs ont pesé dans la balance.")
    
    # Calcul des valeurs SHAP
    explainer = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(input_scaled)
    
    # Graphique Waterfall (Le plus clair pour un individu)
    fig, ax = plt.subplots()
    # On prend seulement les données du client actuel [0]
    shap.plots.waterfall(shap.Explanation(values=shap_values[0], 
                                         base_values=explainer.expected_value, 
                                         data=input_df.iloc[0], 
                                         feature_names=input_df.columns),
                        show=False)
    st.pyplot(fig, bbox_inches='tight')

# --- Données Brutes ---
st.markdown("---")
st.subheader("Données du Client (Traitées)")
st.dataframe(input_df)