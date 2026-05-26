import requests
import time
import numpy as np
from collections import deque
import joblib

print("🛡️ Initialisation du Watchdog IA...")

# 1. Chargement du cerveau (le modèle sérialisé)
try:
    model = joblib.load('modele_thermique_rf.pkl')
    print("✅ Modèle Random Forest chargé avec succès.")
except FileNotFoundError:
    print("❌ Erreur : Le fichier 'modele_thermique_rf.pkl' est introuvable. Exécute d'abord l'export depuis le Notebook.")
    exit(1)

history = deque(maxlen=20)
print("⏳ Attente de 20 secondes pour le calibrage de la variance thermique...")

try:
    while True:
        res = requests.get("http://localhost:8000/cluster/status")
        if res.status_code != 200:
            time.sleep(1)
            continue
            
        data = res.json()
        master_info = data.get('machines', {}).get('srv-master-01')
        
        if not master_info or master_info['status'] == 'off':
            time.sleep(1)
            continue
            
        current_temp = master_info['temperature_c']
        fans = master_info.get('fans', [])
        avg_rpm = sum(f.get('rpm', 0) for f in fans) / len(fans) if fans else 0
        
        history.append(current_temp)
        
        if len(history) >= 2:
            # Calcul dynamique des features
            temp_diff = history[-1] - history[-2]
            temp_std_20s = np.std(history) if len(history) == 20 else 0.0
            
            X_live = np.array([[temp_diff, temp_std_20s, avg_rpm]])
            
            # Inférence
            prediction = model.predict(X_live)[0]
            
            print(f"🌡️ T: {current_temp:.1f}°C | Δ: {temp_diff:+.2f} | σ: {temp_std_20s:.2f} | RPM: {avg_rpm:.0f} -> IA: {'🚨 DANGER' if prediction == 1 else '✅ OK'}")
            
            if prediction == 1:
                print("\n⚡ [INTERVENTION IA] Emballement détecté ! Rallumage d'urgence des ventilateurs...")
                
                for idx in [0, 1]:
                    requests.put(
                        "http://localhost:8000/machines/srv-master-01/fan_mode", 
                        json={"fan_idx": idx, "mode": "auto"}
                    )
                
                print("✅ Sauvetage effectué. Purge de la mémoire à court terme...\n")
                history.clear()
                time.sleep(10)
                
        time.sleep(1)
        
except KeyboardInterrupt:
    print("\n🛑 Watchdog arrêté proprement par l'utilisateur.")