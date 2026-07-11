import openpyxl, warnings
warnings.filterwarnings('ignore')
wb = openpyxl.load_workbook('Nuevo/ENERO 2026 - Con Axarquia.xlsx', data_only=True)

def dump_sheet(name):
    ws = wb[name]
    print(f"\n{'='*90}")
    print(f"HOJA: {name!r}")
    print('='*90)
    for row in ws.iter_rows(values_only=True):
        if any(c is not None for c in row):
            print(row)

dump_sheet('Condiciones de dtos Enero 2026')
dump_sheet('Portes Abril 2026')
dump_sheet('Portes ')
dump_sheet('XPS ')
dump_sheet('README')
