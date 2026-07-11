import pandas as pd
import json

try:
    file_path = r'c:\Users\User\Desktop\Bur2000_v2\Gabriela\v2\propuesta_condiciones_dtos_enero_2026_rangos_limpia.xlsx'
    df = pd.read_excel(file_path)
    print(df.head(10).to_json(orient='records'))
    print("\nColumns:", df.columns.tolist())
except Exception as e:
    print(f"Error: {e}")
