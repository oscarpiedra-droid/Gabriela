import openpyxl, warnings
warnings.filterwarnings('ignore')
wb = openpyxl.load_workbook('Nuevo/ENERO 2026 - Con Axarquia.xlsx', data_only=True)
ws = wb['Condiciones de dtos Enero 2026']

rows = list(ws.iter_rows(values_only=True))

# Find header row
header_row = None
for i, row in enumerate(rows):
    if row and any('segmento' in str(c).lower() or 'tramo' in str(c).lower() for c in row if c):
        header_row = i
        print(f"CABECERA en fila {i+1}:", row)
        break

if header_row is not None:
    # Print all rows where Empresas Constructoras appears
    print("\n--- FILAS CON 'Empresas Constructoras' ---")
    for i, row in enumerate(rows[header_row:], header_row+1):
        row_str = ' | '.join(str(c) for c in row if c is not None)
        if 'constructora' in row_str.lower() or ('empresas' in row_str.lower()):
            print(f"Fila {i}: {row}")
