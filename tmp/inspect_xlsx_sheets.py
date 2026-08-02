from pathlib import Path
import pandas as pd

try:
    file_path = str(Path(__file__).resolve().parent.parent.parent.parent.joinpath('Bur2000_v2').joinpath('Gabriela').joinpath('v2').joinpath('propuesta_condiciones_dtos_enero_2026_rangos_limpia.xlsx'))
    xl = pd.ExcelFile(file_path)
    print(xl.sheet_names)
except Exception as e:
    print(f"Error: {e}")
