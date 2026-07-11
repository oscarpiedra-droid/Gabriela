import pandas as pd
excel_path = r'c:\Users\User\Desktop\Bur2000_v2\Gabriela\v2\propuesta_condiciones_dtos_enero_2026_rangos_limpia.xlsx'
df = pd.read_excel(excel_path, sheet_name='Propuesta_Rangos_2026', engine='openpyxl')
res = df[(df['Segmento'].str.strip().str.upper() == 'PYL') & (df['Familia'].str.strip().str.upper() == 'PARQUET')]
print(res[['Segmento', 'Familia', 'Base imponible desde (EUR)', 'DTO máximo Península (%)']])
