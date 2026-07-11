import openpyxl, warnings
warnings.filterwarnings('ignore')
wb = openpyxl.load_workbook('Nuevo/ENERO 2026 - Con Axarquia.xlsx', data_only=True)

def read_sheet(name):
    ws = wb[name]
    rows = []
    for row in ws.iter_rows(values_only=True):
        if any(c is not None for c in row):
            rows.append(row)
    return rows

# ── PORTES ABRIL 2026 ────────────────────────────────────────────────────
print("=" * 80)
print("HOJA: Portes Abril 2026")
print("=" * 80)
rows = read_sheet('Portes Abril 2026')
for r in rows[:60]:
    print(r)

# ── PORTES ────────────────────────────────────────────────────────────────
print("\n" + "=" * 80)
print("HOJA: Portes ")
print("=" * 80)
rows2 = read_sheet('Portes ')
for r in rows2[:60]:
    print(r)

# ── XPS ──────────────────────────────────────────────────────────────────
print("\n" + "=" * 80)
print("HOJA: XPS ")
print("=" * 80)
rows3 = read_sheet('XPS ')
for r in rows3[:60]:
    print(r)
