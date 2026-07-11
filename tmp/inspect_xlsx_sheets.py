import pandas as pd

try:
    file_path = r'c:\Users\User\Desktop\Bur2000_v2\Gabriela\v2\propuesta_condiciones_dtos_enero_2026_rangos_limpia.xlsx'
    xl = pd.ExcelFile(file_path)
    print(xl.sheet_names)
except Exception as e:
    print(f"Error: {e}")
