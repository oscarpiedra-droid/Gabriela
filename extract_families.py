import pandas as pd
excel_path = r'c:\Users\User\Desktop\Bur2000_v2\Gabriela\v2\propuesta_condiciones_dtos_enero_2026_rangos_limpia.xlsx'
xl = pd.ExcelFile(excel_path)
print(xl.sheet_names)
