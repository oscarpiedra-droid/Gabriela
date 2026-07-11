import pandas as pd

try:
    file_path = r'c:\Users\User\Desktop\Bur2000_v2\Gabriela\v2\propuesta_condiciones_dtos_enero_2026_rangos_limpia.xlsx'
    df = pd.read_excel(file_path, sheet_name='Propuesta_Rangos_2026')
    print("Columns:", df.columns.tolist())
    print("Head:\n", df.head(5).to_string())
except Exception as e:
    print(f"Error: {e}")
