"""probe_excel.py — inspecciona el Excel 2026 para un segmento y familia dados."""
import sys, os, json
import pandas as pd

EXCEL = r"C:\Users\User\Desktop\Bur2000_v2\Gabriela\v2\propuesta_condiciones_dtos_enero_2026_rangos_limpia.xlsx"
df = pd.read_excel(EXCEL, sheet_name="Propuesta_Rangos_2026", engine="openpyxl")
df = df.fillna("")

# Mostrar todos los segmentos únicos
segs = sorted(set(str(v).strip() for v in df["Segmento"] if str(v).strip()))
print("=== SEGMENTOS EN EXCEL ===")
for s in segs:
    print(f"  '{s}'")

# Mostrar familias únicas
fams = sorted(set(str(v).strip() for v in df["Familia"] if str(v).strip()))
print("\n=== FAMILIAS EN EXCEL ===")
for f in fams:
    print(f"  '{f}'")

# Filtrar por segmento + familia del caso
SEGMENTO_HOMO = "Almacenes e instaladores (GAMA SOUND)"
# Buscar filas que coincidan con UPPER
TARGET_SEG_UP = SEGMENTO_HOMO.strip().upper()
FAMILIA_CAND  = sys.argv[1] if len(sys.argv) > 1 else ""

print(f"\n=== FILAS con SEGMENTO '{TARGET_SEG_UP}' ===")
matched = df[df["Segmento"].apply(lambda x: str(x).strip().upper()) == TARGET_SEG_UP]
print(f"Total filas: {len(matched)}")
if not matched.empty:
    cols = ["Segmento","Familia","Base imponible desde (EUR)","Base imponible hasta (EUR)",
            "DTO mínimo Península (%)","DTO máximo Península (%)"]
    avail = [c for c in cols if c in matched.columns]
    print(matched[avail].to_string(index=False))

# Buscar cuál sería el segmento "más parecido"
print(f"\n=== BÚSQUEDA DIFUSA para '{SEGMENTO_HOMO}' ===")
search_upper = SEGMENTO_HOMO.upper()
partial = {str(s): 0 for s in segs}
for s in segs:
    words = s.upper().split()
    score = sum(1 for w in words if w in search_upper or w in ["GAMA","SOUND","ALMAC"])
    partial[s] = score
top = sorted(partial.items(), key=lambda x: -x[1])[:5]
for name, score in top:
    print(f"  score={score}: '{name}'")
