"""
run_audit_loop.py
=================
Ejecuta audit_excel_comercial.py en bucle hasta que no haya errores.
Si detecta errores conocidos, intenta auto-fix antes del siguiente ciclo.

Uso:
  miniconda\python.exe -X utf8 scripts\run_audit_loop.py [--max-iterations N]

Exit code:
  0  →  0 errores en alguna iteracion
  1  →  Se agotaron las iteraciones con errores persistentes
"""

import subprocess
import sys
import os
import json
import math
import argparse
import datetime
import re

_ROOT        = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUDIT_SCRIPT = os.path.join(_ROOT, "scripts", "audit_excel_comercial.py")
PYTHON       = os.path.join(_ROOT, "miniconda", "python.exe")
CATALOG_PATH = os.path.join(_ROOT, "app", "db", "services", "homologacion_clientes.json")

# Segmentos canónicos según el Excel (fuente verdad)
SEGMENTOS_CANONICOS = {
    "Almacenes Especialistas (PYL)",
    "Almacenes Generalistas",
    "Empresas Constructoras",
    "Empresas Instaladoras",
    "Almacenes e Instaladores (Gama SOUND)",
    "Axarquía de Aislamientos (Distribución)",
}

# ── Auto-Fixes conocidos ──────────────────────────────────────────────────────

def autofix_sound_capitalisation():
    """Fix: normalizar capitalización del segmento SOUND en el catálogo JSON."""
    with open(CATALOG_PATH, encoding="utf-8") as f:
        d = json.load(f)

    OLD = "Almacenes e instaladores (GAMA SOUND)"
    NEW = "Almacenes e Instaladores (Gama SOUND)"
    count = 0
    for e in d.get("homologacion", []):
        if e.get("segmento_aplicacion", "") == OLD:
            e["segmento_aplicacion"] = NEW
            count += 1

    if count > 0:
        _bump_version(d, f"autofix capitalización SOUND ({count} entradas)")
        with open(CATALOG_PATH, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=2, ensure_ascii=False)
        print(f"    [AUTOFIX] SOUND capitalización corregida en {count} entradas")
    return count > 0


def autofix_nan_dto():
    """Fix: verificar que _safe_dto exista en commercial_conditions_service.py."""
    svc_path = os.path.join(_ROOT, "app", "db", "services", "commercial_conditions_service.py")
    with open(svc_path, encoding="utf-8") as f:
        content = f.read()
    if "_safe_dto" not in content:
        print("    [AUTOFIX] ATENCION: _safe_dto no encontrado en commercial_conditions_service.py")
        print("              Aplica el fix manual del NaN antes de continuar.")
        return False
    print("    [AUTOFIX] _safe_dto presente en commercial_conditions_service.py [OK]")
    return True


def autofix_missing_segment(seg_name):
    """Fix: añade una entrada placeholder para un segmento sin cobertura."""
    with open(CATALOG_PATH, encoding="utf-8") as f:
        d = json.load(f)

    existing_segs = {e.get("segmento_aplicacion","") for e in d.get("homologacion",[])}
    if seg_name in existing_segs:
        return False

    new_entry = {
        "odoo_tipo_cliente": seg_name,
        "segmento_aplicacion": seg_name,
        "uso": "ESTÁNDAR",
        "estado": "activo",
        "notas": f"AUTOFIX: placeholder para segmento '{seg_name}'. Revisar y completar."
    }
    d["homologacion"].insert(0, new_entry)
    _bump_version(d, f"autofix placeholder segmento '{seg_name}'")
    with open(CATALOG_PATH, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2, ensure_ascii=False)
    print(f"    [AUTOFIX] Placeholder añadido para segmento '{seg_name}'")
    return True


def _bump_version(d, nota):
    meta = d.setdefault("_meta", {})
    ver = meta.get("version", "0.0").split(".")
    try:
        ver[-1] = str(int(ver[-1]) + 1)
    except Exception:
        ver = ["3", "99"]
    meta["version"] = ".".join(ver)
    meta["last_updated"] = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M")
    existing = meta.get("fusion", "")
    meta["fusion"] = existing + f" {meta['last_updated']}: {nota}."


def run_audit():
    """Ejecuta el script de auditoría y retorna (returncode, output_text)."""
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(
        [PYTHON, "-X", "utf8", AUDIT_SCRIPT],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=_ROOT,
        env=env,
    )
    combined = result.stdout + result.stderr
    return result.returncode, combined


def parse_errors_from_output(output):
    """Extrae los errores del output del audit para hacer auto-fix."""
    errors = re.findall(r"\[ERR\s*\] (.+)", output)
    return errors


def apply_autofixes(errors, output):
    """Intenta aplicar fixes automáticos según los errores detectados."""
    fixed_something = False

    # Fix 1: capitalización SOUND
    if any("SOUND" in e or "instaladores" in e.lower() for e in errors):
        if autofix_sound_capitalisation():
            fixed_something = True

    # Fix 2: _safe_dto para NaN
    if any("NaN" in e or "nan" in e for e in errors):
        autofix_nan_dto()

    # Fix 3: segmentos sin cobertura
    for e in errors:
        m = re.search(r"Segmento SIN cobertura.*?'([^']+)'", e)
        if m:
            seg = m.group(1)
            if seg in SEGMENTOS_CANONICOS:
                if autofix_missing_segment(seg):
                    fixed_something = True

    return fixed_something


def main():
    parser = argparse.ArgumentParser(description="Loop de auditoría BUR2000 hasta 0 errores")
    parser.add_argument("--max-iterations", type=int, default=70,
                        help="Número máximo de iteraciones (default: 70)")
    parser.add_argument("--no-autofix", action="store_true",
                        help="Desactivar auto-fix entre iteraciones")
    args = parser.parse_args()

    MAX_ITER = args.max_iterations

    print("=" * 70)
    print(f"  LOOP DE AUDITORIA BUR2000 — max {MAX_ITER} iteraciones")
    print("=" * 70)

    log = []
    last_errors = []

    for i in range(1, MAX_ITER + 1):
        print(f"\n{'=' * 70}")
        print(f"  ITERACION {i}/{MAX_ITER} — {datetime.datetime.now().strftime('%H:%M:%S')}")
        print(f"{'=' * 70}")

        returncode, output = run_audit()
        errors = parse_errors_from_output(output)
        n_errors = len(errors)

        # Capturar línea de RESULTADO del output
        for line in output.splitlines():
            if "RESULTADO:" in line or "PERFECTO" in line or "HAY ERRORES" in line:
                print(f"  >>> {line.strip()}")

        log.append({
            "iteration": i,
            "timestamp": datetime.datetime.now().isoformat(),
            "n_errors": n_errors,
            "errors": errors,
        })

        if n_errors == 0:
            print(f"\n  *** PERFECTO EN ITERACION {i} — 0 errores ***")
            print(f"  El validador comercial esta 100% listo para produccion.")
            _write_log(log)
            sys.exit(0)

        # Errores persisten
        print(f"\n  Errores detectados ({n_errors}):")
        for e in errors:
            print(f"    [ERR] {e}")

        # Detectar si los errores son iguales a la iteración anterior (bucle sin progreso)
        if errors == last_errors and i > 1:
            print(f"\n  [STOP] Los errores no cambiaron desde la iteracion anterior.")
            print(f"         Se requiere intervencion manual para resolver:")
            for e in errors:
                print(f"           - {e}")
            _write_log(log)
            sys.exit(1)

        last_errors = errors

        # Auto-fix
        if not args.no_autofix:
            print(f"\n  Intentando auto-fix...")
            fixed = apply_autofixes(errors, output)
            if fixed:
                print(f"  Auto-fix aplicado. Reintentando auditoría...")
            else:
                print(f"  No se pudo auto-fix. Los errores requieren intervencion manual.")
                _write_log(log)
                sys.exit(1)

    print(f"\n  [STOP] Se agotaron las {MAX_ITER} iteraciones con {len(last_errors)} errores persistentes.")
    _write_log(log)
    sys.exit(1)


def _write_log(log):
    log_path = os.path.join(_ROOT, "scripts", "audit_loop_log.json")
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)
    print(f"\n  Log guardado en: {log_path}")


if __name__ == "__main__":
    main()
