from pathlib import Path
import pandas as pd
excel_path = str(Path(__file__).resolve().parent.parent.parent.joinpath('Bur2000_v2').joinpath('Gabriela').joinpath('v2').joinpath('propuesta_condiciones_dtos_enero_2026_rangos_limpia.xlsx'))
df = pd.read_excel(excel_path, sheet_name='Propuesta_Rangos_2026', engine='openpyxl')
print(df['Segmento'].unique())
