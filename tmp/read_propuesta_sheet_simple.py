from pathlib import Path
import pandas as pd

try:
    file_path = str(Path(__file__).resolve().parent.parent.parent.parent.joinpath('Bur2000_v2').joinpath('Gabriela').joinpath('v2').joinpath('propuesta_condiciones_dtos_enero_2026_rangos_limpia.xlsx'))
    df = pd.read_excel(file_path, sheet_name='Propuesta_Rangos_2026')
    print("Columns:", df.columns.tolist())
    print("Head:\n", df.head(5).to_string())
except Exception as e:
    print(f"Error: {e}")
