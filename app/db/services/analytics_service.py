import json
import os
import random
import pandas as pd
try:
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.preprocessing import LabelEncoder
except ImportError:
    RandomForestRegressor = None
    LabelEncoder = None
import numpy as np


class AnalyticsService:
    def __init__(self):
        self.df = None
        self.model = None
        self.label_encoders = {}
        self.is_trained = False
        
        self.load_synthetic_data()
        
    def load_synthetic_data(self):
        # Load the v2 json to extract existing families
        # __file__ = app/db/services/analytics_service.py
        # one dirname up  -> app/db/   (where commercial_rules_v2.json lives)
        base_dir = os.path.dirname(os.path.abspath(__file__))
        json_path = os.path.join(base_dir, "..", "commercial_rules_v2.json")
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                rules = json.load(f)
        except Exception as e:
            # Fallback mock data if json doesn't exist yet
            rules = {"SKU_MASTER": {"TEST1": {"family_logic_base": "CM_XPS"}}}
            
        # Generate synthetic orders
        sku_master = rules.get("SKU_MASTER", [])
        if isinstance(sku_master, dict):
            families = list(set([v.get("family_logic_base", "default") for k, v in sku_master.items()]))
        else:
            families = list(set([item.get("family_logic_base", "default") for item in sku_master if isinstance(item, dict)]))
        if not families:
            families = ["Aislamiento", "Impermeabilizacion", "Accesorios"]
            
        zones = ["PENINSULA", "BALEARES", "CANARIAS", "INTERNACIONAL"]
        
        data = []
        for _ in range(1500): # 1500 synthetic historic orders
            family = random.choice(families)
            zone = random.choice(zones)
            weight = random.uniform(50, 5000) # 50kg to 5000kg
            
            # Simple synthetic logic for shipping cost to make plots interesting
            base_cost = weight * 0.15
            if zone == "BALEARES": base_cost *= 1.5
            elif zone == "CANARIAS": base_cost *= 2.5
            elif zone == "INTERNACIONAL": base_cost *= 3.0
            
            if "XPS" in family: base_cost += 50
            if "TELA" in family: base_cost += 20
            
            # Add some algorithmic noise to mimic real-world unpredictability
            cost = base_cost + random.uniform(-20, 50)
            cost = max(0, cost)
            
            data.append({
                "ZONA": zone,
                "FAMILIA": family,
                "PESO_KG": weight,
                "COSTE_ENVIO_EUR": cost
            })
            
        self.df = pd.DataFrame(data)
        
    def train_model(self):
        if self.df is None or len(self.df) == 0:
            return False
            
        X = self.df.copy()
        y = X.pop("COSTE_ENVIO_EUR")
        
        # Encode categorical variables
        for col in ["ZONA", "FAMILIA"]:
            le = LabelEncoder()
            X[col] = le.fit_transform(X[col])
            self.label_encoders[col] = le
            
        # Use a lightweight Random Forest
        self.model = RandomForestRegressor(n_estimators=50, random_state=42)
        self.model.fit(X, y)
        self.is_trained = True
        return True
        
    def predict_shipping(self, zone: str, family: str, weight: float) -> str:
        if not self.is_trained:
            return "Modelo no entrenado"
            
        try:
            # Safely transform inputs
            z_encoded = self.label_encoders["ZONA"].transform([zone])[0] if zone in self.label_encoders["ZONA"].classes_ else 0
            f_encoded = self.label_encoders["FAMILIA"].transform([family])[0] if family in self.label_encoders["FAMILIA"].classes_ else 0
            
            # Inference Warning handler missing feature names because training was via DataFrame and predicting with array
            pred = self.model.predict([[z_encoded, f_encoded, weight]])
            return f"{pred[0]:.2f} €"
        except Exception as e:
            return f"Error: {str(e)}"
            
    def get_summary_stats(self):
        if self.df is None: return {}
        return {
            "Total_Orders": len(self.df),
            "Avg_Shipping": self.df["COSTE_ENVIO_EUR"].mean(),
            "Max_Shipping": self.df["COSTE_ENVIO_EUR"].max(),
            "Families": self.df["FAMILIA"].nunique(),
        }
