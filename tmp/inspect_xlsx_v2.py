from pathlib import Path
import pandas as pd
import json

try:
    file_path = str(Path(__file__).resolve().parent.parent.parent.parent.joinpath('Bur2000_v2').joinpath('Gabriela').joinpath('v2').joinpath('propuesta_condiciones_dtos_enero_2026_rangos_limpia.xlsx'))
    df = pd.read_excel(file_path, header=None)
    print(df.head(20).to_json(orient='records'))
except Exception as e:
    print(f"Error: {e}")
