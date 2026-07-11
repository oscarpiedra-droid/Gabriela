"""
commercial_conditions_service.py
Servicio que lee la tabla maestra de condiciones comerciales desde el Excel
oficial de Imperbur (ENERO 2026 - Con Axarquia.xlsx).

Schema del Excel:
  - Hoja principal: "Condiciones de dtos Enero 2026"
  - Cabeceras en fila 17 (índice 16), columnas D–I:
      D: Segmento
      E: Familia
      F: Tramo facturación   (int o str como "< 1.500 €")
      G: DTO Territorial (%)
      H: DTO Baleares (%)
      I: Condición mínima
  - Datos desde fila 18 en adelante.

Hoja de portes: "Portes Abril 2026"
  - Cabeceras en fila 10:
      B: Gama
      C: Portes Gratis Desde
      D: Portes por Comunidad Autónoma
"""

from __future__ import annotations

import math
import os
import json
import re
import hashlib
from typing import Any

import pandas as pd
from loguru import logger

# ─────────────────────────────────────────────────────────────────────────────
# Ruta por defecto al Excel maestro
# ─────────────────────────────────────────────────────────────────────────────
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)
))))
DEFAULT_EXCEL_PATH = os.path.join(_BASE_DIR, "Nuevo", "ENERO 2026 - Con Axarquia.xlsx")

# Nombre exacto de las hojas
SHEET_CONDICIONES = "Condiciones de dtos Enero 2026"
SHEET_PORTES      = "Portes Abril 2026"

# Índice de la fila de cabeceras (0-based → fila 17 = índice 16)
HEADER_ROW_IDX = 16
# Columnas a leer (D=3, E=4, F=5, G=6, H=7, I=8 → usecols 3..8)
DATA_USECOLS = "D:I"

# Mapeo de columnas internas → nombres friendly
COL_SEGMENTO  = "Segmento"
COL_FAMILIA   = "Familia"
COL_TRAMO     = "Tramo facturación"
COL_DTO_TER   = "DTO Territorial (%)"
COL_DTO_BAL   = "DTO Baleares (%)"
COL_CONDICION = "Condición mínima (familias/referencias)"

# Colores por segmento para la UI (igual visual que el Excel)
# IMPORTANTE: Los nombres deben coincidir EXACTAMENTE con el valor del campo "Segmento"
# en la hoja "Condiciones de dtos Enero 2026" del Excel maestro.
SEGMENT_COLORS: Dict[str, str] = {
    "Almacenes Especialistas (PYL)":                "#E3F2FD",   # azul claro
    "Almacenes Generalistas":                        "#E8F5E9",   # verde claro
    "Empresas Constructoras":                        "#FFF3E0",   # naranja claro
    "Empresas Instaladoras":                         "#F3E5F5",   # púrpura claro
    "Almacenes e Instaladores (Gama SOUND)":         "#FCE4EC",   # rosa claro (fix capitalización v3.2)
    "Axarquía de Aislamientos (Distribución)":       "#FFFDE7",   # amarillo claro
}

DEFAULT_SEGMENT_COLOR = "#F5F5F5"

# ─────────────────────────────────────────────────────────────────────────────
# Mapeo código interno (family_logic_base en SKU_MASTER) → nombre exacto Excel
# ─────────────────────────────────────────────────────────────────────────────
# Nombres base: aplican para la mayoría de segmentos estándar.
FAMILY_LOGIC_MAP: Dict[str, str] = {
    "CM_XPS_SYC":                  "AIR BUR TERMIC (CM XPS / S-YC)",
    "REFLECTIVOS_EXCL_CM_XPS_SYC": "AIR-BUR TERMIC / TERMOREFLEX (EXCL. CM XPS / S-YC)",
    "ACUSTICA":                    "AC\u00daSTICA",
    "ANTI_IMPACTO_NO_SOUND":       "ANTI IMPACTO (NO SOUND)",
    "IMPERMEABILIZANTES":          "IMPERMEABILIZANTES",
    "PARQUET":                     "PARQUET",
    "XPS_ESPECIAL":                "AIR BUR TERMIC (CM XPS / S-YC)",  # variantes especiales → misma tabla
    "REVIEW_REQUIRED":             None,   # excluir de validaci\u00f3n autom\u00e1tica
}

# Overrides por segmento: Axarqu\u00eda y Constructoras usan alias distintos en Excel
FAMILY_LOGIC_MAP_OVERRIDES: Dict[str, Dict[str, Optional[str]]] = {
    "Axarqu\u00eda de Aislamientos (Distribuci\u00f3n)": {
        "CM_XPS_SYC":                  "AIR BUR TERMIC (CM )",
        "REFLECTIVOS_EXCL_CM_XPS_SYC": "AIR-BUR TERMIC / (EXCL. CM )",
    },
    "Empresas Constructoras": {
        "REFLECTIVOS_EXCL_CM_XPS_SYC": "AIR-BUR TERMIC (EXCL. CM XPS / S-YC)",
    },
}

# Familias internas con bonus multi-gama (seg\u00fan Excel 2026)
_FAM_CM_XPS  = "CM_XPS_SYC"   # bonus: +2 GAMAS si se compra con \u22652 otras familias
_FAM_PARQUET = "PARQUET"       # bonus: +OTRA GAMA si se compra con \u22651 otra familia
_AXARQUIA_SEGMENT = "Axarqu\u00eda de Aislamientos (Distribuci\u00f3n)"   # sin bonus en esta hoja


class DiscountProposalService:
    """
    Lee y valida la tabla maestra de condiciones comerciales desde el Excel
    oficial (ENERO 2026 - Con Axarquia.xlsx).
    """

    _cache_data: Optional[List[Dict[str, Any]]] = None
    _cache_portes: Optional[List[Dict[str, Any]]] = None

    def __init__(self, excel_path: Optional[str] = None):
        self.excel_path = excel_path or DEFAULT_EXCEL_PATH

    # ── Lectura del Excel ───────────────────────────────────────────────────

    def _read_excel_condiciones(self) -> List[Dict[str, Any]]:
        """Lee la hoja de condiciones de descuento del Excel maestro."""
        try:
            df = pd.read_excel(
                self.excel_path,
                sheet_name=SHEET_CONDICIONES,
                header=HEADER_ROW_IDX,
                usecols=DATA_USECOLS,
                engine="openpyxl",
            )
            # Renombrar si las columnas no coinciden exactamente (trim)
            df.columns = [str(c).strip() for c in df.columns]

            # Eliminar filas completamente vacías
            df = df.dropna(how="all")

            # Filtrar filas donde Segmento o Familia son NaN
            df = df[df[COL_SEGMENTO].notna() & df[COL_FAMILIA].notna()]

            # DTO Baleares puede ser NaN para Axarquía → dejar como None
            df[COL_DTO_BAL] = df[COL_DTO_BAL].where(df[COL_DTO_BAL].notna(), None)
            df[COL_CONDICION] = df[COL_CONDICION].where(df[COL_CONDICION].notna(), "")

            records = df.to_dict(orient="records")
            logger.info(
                f"DiscountProposalService: {len(records)} reglas cargadas desde Excel."
            )
            return records
        except Exception as e:
            logger.error(f"DiscountProposalService: Error leyendo Excel: {e}")
            return []

    def _read_excel_portes(self) -> List[Dict[str, Any]]:
        """Lee la hoja de portes del Excel maestro."""
        try:
            df = pd.read_excel(
                self.excel_path,
                sheet_name=SHEET_PORTES,
                header=9,          # fila 10, índice 9
                usecols="B:D",
                engine="openpyxl",
            )
            df.columns = [str(c).strip() for c in df.columns]
            df = df.dropna(how="all").dropna(subset=[df.columns[0]])
            return df.to_dict(orient="records")
        except Exception as e:
            logger.error(f"DiscountProposalService: Error leyendo hoja portes: {e}")
            return []

    # ── API pública ─────────────────────────────────────────────────────────

    def get_proposal_data(self) -> List[Dict[str, Any]]:
        """Retorna todas las reglas de descuento. Usa caché en memoria."""
        if DiscountProposalService._cache_data is not None:
            return DiscountProposalService._cache_data

        if not os.path.exists(self.excel_path):
            logger.error(f"Excel not found at {self.excel_path}")
            # Intentar fallback JSON (compatibilidad con formato antiguo)
            json_path = self.excel_path.replace(".xlsx", ".json")
            if os.path.exists(json_path):
                try:
                    with open(json_path, "r", encoding="utf-8") as f:
                        records = json.load(f)
                    DiscountProposalService._cache_data = records
                    return records
                except Exception as e:
                    logger.error(f"JSON fallback also failed: {e}")
            return []

        records = self._read_excel_condiciones()
        DiscountProposalService._cache_data = records
        return records

    def get_portes_data(self) -> List[Dict[str, Any]]:
        """Retorna la tabla de portes vigente (Portes Abril 2026)."""
        if DiscountProposalService._cache_portes is not None:
            return DiscountProposalService._cache_portes

        if not os.path.exists(self.excel_path):
            return []

        records = self._read_excel_portes()
        DiscountProposalService._cache_portes = records
        return records

    # ── Guardas de integridad ────────────────────────────────────────────────

    def check_excel_integrity(self, json_rules_path: Optional[str] = None) -> Dict[str, Any]:
        """
        GUARDA 1 — Compara el SHA256 del Excel actual contra el hash guardado en
        commercial_rules_v2.json (_meta.excel_hash_sha256).

        Devuelve dict:
          { 'ok': bool, 'current_hash': str, 'expected_hash': str, 'msg': str }

        Si 'ok' es False, el Excel ha cambiado desde la última sincronización y
        hay que ejecutar el script de parche antes de continuar.
        """
        result: Dict[str, Any] = {
            'ok': False,
            'current_hash': '',
            'expected_hash': '',
            'msg': '',
        }

        # Calcular hash actual del Excel
        if not os.path.exists(self.excel_path):
            result['msg'] = f"Excel no encontrado: {self.excel_path}"
            logger.error(f"[IntegrityGuard] {result['msg']}")
            return result

        with open(self.excel_path, 'rb') as f:
            result['current_hash'] = hashlib.sha256(f.read()).hexdigest()

        # Leer hash esperado del JSON de reglas
        if json_rules_path is None:
            _svc_dir = os.path.dirname(os.path.abspath(__file__))
            json_rules_path = os.path.join(_svc_dir, '..', 'commercial_rules_v2.json')

        try:
            with open(json_rules_path, encoding='utf-8') as f:
                meta = json.loads(re.sub(r'\bNaN\b', 'null', f.read())).get('_meta', {})
            result['expected_hash'] = meta.get('excel_hash_sha256', '')
        except Exception as e:
            result['msg'] = f"No se pudo leer el hash esperado del JSON: {e}"
            logger.warning(f"[IntegrityGuard] {result['msg']}")
            return result

        if not result['expected_hash']:
            result['msg'] = "No hay hash registrado en _meta. Ejecuta el script de parche para registrarlo."
            logger.warning(f"[IntegrityGuard] {result['msg']}")
            return result

        if result['current_hash'] == result['expected_hash']:
            result['ok'] = True
            result['msg'] = "Excel coincide con el JSON de reglas. Motor comercial sincronizado."
            logger.debug(f"[IntegrityGuard] OK — hash coincide: {result['current_hash'][:12]}...")
        else:
            result['msg'] = (
                f"ALERTA: El Excel ha cambiado desde la última sincronización. "
                f"Ejecuta patch_all_from_excel.py antes de validar pedidos. "
                f"Hash actual: {result['current_hash'][:16]}... "
                f"Hash esperado: {result['expected_hash'][:16]}..."
            )
            logger.warning(f"[IntegrityGuard] {result['msg']}")

        return result

    def check_family_map_coverage(self) -> Dict[str, Any]:
        """
        GUARDA 2 — Comprueba cobertura bidireccional del mapa de familias:
          - Excel → interno: cada familia del Excel tiene código interno en FAMILY_LOGIC_MAP
          - Interno → Excel: cada código de FAMILY_LOGIC_MAP aparece en el Excel

        Devuelve dict:
          { 'ok': bool, 'missing_in_map': list, 'missing_in_excel': list, 'msg': str }
        """
        records = self.get_proposal_data()

        # Familias únicas en el Excel (excluir variantes bonus — son derivadas)
        # Nota: el Excel usa '+2 GAMAS' y 'OTRA GAMA' (con espacio) en los nombres bonus.
        excel_families = {
            str(r.get(COL_FAMILIA, '')).strip()
            for r in records
            if r.get(COL_FAMILIA)
            and '+2 GAMAS' not in str(r.get(COL_FAMILIA, ''))
            and 'OTRA GAMA'  not in str(r.get(COL_FAMILIA, ''))  # cubre "+ OTRA GAMA" y "+OTRA GAMA"
        }

        # Construir mapa inverso: nombre_excel → clave_interna
        excel_to_internal: Dict[str, str] = {}
        for internal_key, excel_name in FAMILY_LOGIC_MAP.items():
            if excel_name:  # puede ser None (REVIEW_REQUIRED)
                excel_to_internal[excel_name] = internal_key
        # Añadir overrides
        for seg_overrides in FAMILY_LOGIC_MAP_OVERRIDES.values():
            for internal_key, excel_name in seg_overrides.items():
                if excel_name:
                    excel_to_internal[excel_name] = internal_key

        missing_in_map   = sorted(excel_families - set(excel_to_internal.keys()))
        mapped_excel_names = {v for v in FAMILY_LOGIC_MAP.values() if v}
        for seg_ov in FAMILY_LOGIC_MAP_OVERRIDES.values():
            mapped_excel_names.update(v for v in seg_ov.values() if v)
        missing_in_excel = sorted(mapped_excel_names - excel_families)

        ok = not missing_in_map and not missing_in_excel
        msg_parts = []
        if missing_in_map:
            msg_parts.append(
                f"Familias del Excel SIN código interno: {missing_in_map}. "
                "Añadirlas a FAMILY_LOGIC_MAP."
            )
        if missing_in_excel:
            msg_parts.append(
                f"Códigos internos SIN familia en Excel: {missing_in_excel}. "
                "Puede ser normal si el segmento usa alias (Axarquía / Constructoras)."
            )

        if ok:
            msg = f"Cobertura completa: {len(excel_families)} familias Excel ↔ mapa interno OK."
            logger.debug(f"[FamilyMapGuard] {msg}")
        else:
            msg = ' | '.join(msg_parts)
            logger.warning(f"[FamilyMapGuard] {msg}")

        return {
            'ok': ok,
            'missing_in_map': missing_in_map,
            'missing_in_excel': missing_in_excel,
            'excel_families': sorted(excel_families),
            'msg': msg,
        }

    def run_integrity_checks(self, json_rules_path: Optional[str] = None) -> bool:
        """
        Ejecuta TODAS las guardas de integridad en un solo comando.
        Retorna True si todo está OK, False si hay algún problema.
        Ideal para llamar al arrancar la app.
        """
        r1 = self.check_excel_integrity(json_rules_path)
        r2 = self.check_family_map_coverage()
        all_ok = r1['ok'] and r2['ok']
        if all_ok:
            logger.info("[IntegrityChecks] Todas las guardas OK. Motor comercial en buen estado.")
        else:
            logger.warning(
                f"[IntegrityChecks] ATENCIÓN: "
                f"hash={'OK' if r1['ok'] else 'FAIL'} | "
                f"familias={'OK' if r2['ok'] else 'FAIL'}"
            )
        return all_ok

    def save_proposal_data(self, new_records: List[Dict[str, Any]]) -> bool:
        """
        Guarda modificaciones en JSON (el Excel original no se modifica).
        Uso interno cuando se edita la Matriz Base desde la UI.
        """
        json_path = os.path.join(
            os.path.dirname(self.excel_path), "condiciones_override.json"
        )
        try:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(new_records, f, indent=4, ensure_ascii=False)
            DiscountProposalService._cache_data = new_records
            logger.info(f"Matriz guardada en {json_path}")
            return True
        except Exception as e:
            logger.error(f"Error guardando matriz: {e}")
            return False

    # ── Validación ──────────────────────────────────────────────────────────

    def _parse_tramo_minimo(self, tramo_val) -> float:
        """
        Convierte un valor de tramo a su límite inferior numérico.
        Ejemplos:
          6000        → 6000.0
          "< 1.500 €" → 0.0     (tramo abierto por abajo)
          "< 3.000 €" → 0.0
          "< 1.000 €" → 0.0
        """
        if tramo_val is None:
            return 0.0
        try:
            return float(tramo_val)
        except (ValueError, TypeError):
            # Es un string como "< 1.500 €" → tramo mínimo = 0
            return 0.0

    def _parse_tramo_maximo(self, tramo_val) -> float:
        """
        Convierte un valor de tramo a su límite superior numérico.
        Ejemplos:
          6000        → inf   (tramo top)
          "< 1.500 €" → 1499.99
          "< 3.000 €" → 2999.99
        """
        if tramo_val is None:
            return float("inf")
        try:
            # Número puro → es el mínimo del tramo, sin máximo definido explícitamente
            float(tramo_val)
            return float("inf")
        except (ValueError, TypeError):
            s = str(tramo_val)
            # Extraer número del string "< 1.500 €"
            nums = re.findall(r"[\d.,]+", s)
            if nums:
                cleaned = nums[0].replace(".", "").replace(",", ".")
                try:
                    return float(cleaned) - 0.01
                except ValueError:
                    return float("inf")
            return float("inf")

    def _get_tramo_rules(self, segmento: str, familia: str) -> List[Dict]:
        """Retorna todas las reglas para un segmento+familia, ordenadas por tramo desc.
        Acepta tanto el nombre exacto del Excel como el c\u00f3digo interno (se resuelve internamente).
        """
        records = self.get_proposal_data()
        seg_upper = segmento.strip().upper()
        fam_upper = familia.strip().upper()

        rules = [
            r for r in records
            if str(r.get(COL_SEGMENTO, "")).strip().upper() == seg_upper
            and str(r.get(COL_FAMILIA, "")).strip().upper() == fam_upper
        ]

        # Ordenar por tramo m\u00ednimo descendente (reglas m\u00e1s altas primero)
        rules.sort(key=lambda r: self._parse_tramo_minimo(r.get(COL_TRAMO)), reverse=True)
        return rules

    def resolve_familia_excel(
        self,
        familia_interna: str,
        segmento: str,
        familias_en_pedido: Optional[set] = None,
    ) -> Optional[str]:
        """
        Convierte el c\u00f3digo interno family_logic_base al nombre exacto de la hoja Excel
        aplicando los alias por segmento (Axarqu\u00eda, Constructoras) y el bonus +2 GAMAS.

        Devuelve:
          - str con el nombre Excel a buscar en la tabla (puede ser la variante bonus)
          - None  si la familia debe excluirse de validaci\u00f3n autom\u00e1tica
        """
        seg = segmento.strip()

        # 1. Nombre base (aplicar override de segmento si existe)
        seg_overrides = FAMILY_LOGIC_MAP_OVERRIDES.get(seg, {})
        if familia_interna in seg_overrides:
            name: Optional[str] = seg_overrides[familia_interna]
        else:
            name = FAMILY_LOGIC_MAP.get(familia_interna, familia_interna)

        if name is None:
            return None  # familia excluida de validaci\u00f3n

        # 2. Bonus multi-gama (solo en segmentos que tienen filas bonus en Excel)
        if familias_en_pedido and seg != _AXARQUIA_SEGMENT and len(familias_en_pedido) > 1:
            otras = {
                f for f in familias_en_pedido
                if f not in (familia_interna, "XPS_ESPECIAL", "REVIEW_REQUIRED", "")
            }

            if familia_interna == _FAM_CM_XPS and len(otras) >= 2:
                bonus_name = name + " +2 GAMAS"
                if self._get_tramo_rules(seg, bonus_name):
                    logger.debug(
                        f"[MultiGama] +2 GAMAS activado: {seg} / {familia_interna} "
                        f"(otras familias: {otras})"
                    )
                    return bonus_name

            elif familia_interna == _FAM_PARQUET and len(otras) >= 1:
                bonus_name = "PARQUET + OTRA GAMA"
                if self._get_tramo_rules(seg, bonus_name):
                    logger.debug(
                        f"[MultiGama] +OTRA GAMA activado: {seg} / PARQUET "
                        f"(otras familias: {otras})"
                    )
                    return bonus_name

        return name

    def validate_range(
        self,
        segmento: str,
        familia: str,
        base_imponible: float,
        territorio: str,
        dto_solicitado: float,
        familias_en_pedido: Optional[set] = None,
    ) -> Dict[str, Any]:
        """
        Valida un descuento solicitado contra la tabla 2026.
        Acepta c\u00f3digos internos (family_logic_base) o nombres exactos del Excel.
        Si familias_en_pedido se provee, activa el bonus +2 GAMAS / +OTRA GAMA.
        Lógica:
          1. Buscar reglas para (segmento, familia).
          2. Encontrar la regla cuyo tramo aplica para base_imponible.
          3. Comparar dto_solicitado con DTO Territorial o Baleares.
          4. Si excede, comprobar "zona de escalado" (siguiente tramo superior).
        """
        # Resolver nombre Excel (con bonus multi-gama si aplica)
        familia_excel = self.resolve_familia_excel(familia, segmento, familias_en_pedido)
        if familia_excel is None:
            return {
                "valid": True,
                "msg": f"Familia '{familia}' excluida de validaci\u00f3n autom\u00e1tica",
                "status": "OK",
            }

        rules = self._get_tramo_rules(segmento, familia_excel)

        if not rules:
            # GUARDA 3: status UNCHECKED (antes era OK silencioso) — permite a la
            # UI mostrar ⚠️ en lugar de ✅ cuando no hay regla para esta combinación.
            logger.debug(
                f"[validate_range] Sin regla 2026 para {segmento}/{familia_excel} "
                f"→ UNCHECKED (no se puede validar, no se bloquea)"
            )
            return {
                "valid": True,
                "msg": f"Sin regla 2026 para {segmento}/{familia_excel}",
                "status": "UNCHECKED",
            }

        # Encontrar regla aplicable: buscar donde tramo_min <= base_imponible < tramo_max
        # Para el tramo "< X €", tramo_min=0 y tramo_max=X-0.01
        # Para tramos numéricos, tramo_min=valor y tramo_max=inf
        # Usamos el tramo más alto donde tramo_min <= base_imponible
        rule = None
        for r in rules:  # ya ordenado desc por tramo_min
            t_min = self._parse_tramo_minimo(r.get(COL_TRAMO))
            if base_imponible >= t_min:
                rule = r
                break

        if rule is None:
            return {
                "valid": True,
                "msg": f"Sin tramo aplicable para {base_imponible:.2f}€",
                "status": "OK",
            }

        # Obtener DTO permitido ────────────────────────────────────────────────
        # _safe_dto: convierte el valor raw del Excel a float, manejando TODOS los
        # valores nulos de pandas (None, float('nan'), pd.NA, NaN) de forma uniforme.
        def _safe_dto(val: Any) -> float | None:
            """Convierte un valor raw de Excel a float. Retorna None si es nulo."""
            if val is None:
                return None
            try:
                f = float(val)
                return None if math.isnan(f) else f
            except (ValueError, TypeError):
                return None

        es_baleares = "baleares" in territorio.lower()
        if es_baleares:
            dto_max = _safe_dto(rule.get(COL_DTO_BAL))
            if dto_max is None:
                # Axarquía y similares sin DTO Baleares definido → usar territorial
                dto_max = _safe_dto(rule.get(COL_DTO_TER))
                if dto_max is not None:
                    logger.debug(
                        f"[DTO] Baleares-fallback a Territorial ({dto_max}%) "
                        f"para {segmento}/{familia}"
                    )
        else:
            dto_max = _safe_dto(rule.get(COL_DTO_TER))

        if dto_max is None:
            logger.warning(
                f"[DTO] No se encontró DTO Territorial ni Baleares para "
                f"{segmento}/{familia}/tramo={rule.get(COL_TRAMO)}. "
                f"La regla existe pero el DTO es nulo — pedido no bloqueado."
            )
            return {
                "valid": True,
                "msg": f"DTO nulo en tabla 2026 para tramo {rule.get(COL_TRAMO)} — no evaluado",
                "status": "OK",
                "rules": {"max": None},
            }

        FLOAT_TOL = 0.01
        if dto_solicitado <= dto_max + FLOAT_TOL:
            return {
                "valid": True,
                "msg": "DTO Validado (2026)",
                "status": "OK",
                "rules": {"max": dto_max},
            }

        # Excedido → comprobar zona de escalado (tramo inmediatamente superior al actual).
        # IMPORTANTE: `rules` está ordenado DESC por tramo_min. Con `next()` iterando en ese
        # orden, el primer elemento con t_min > current_tmin sería el MÁS ALTO (error).
        # Se necesita el tramo INMEDIATAMENTE superior = el de menor t_min entre los candidatos.
        current_tmin = self._parse_tramo_minimo(rule.get(COL_TRAMO))
        candidatos = [
            r for r in rules
            if self._parse_tramo_minimo(r.get(COL_TRAMO)) > current_tmin
        ]
        # Tomar el de menor t_min (el adyacente al tramo actual)
        next_rule = min(
            candidatos,
            key=lambda r: self._parse_tramo_minimo(r.get(COL_TRAMO)),
            default=None,
        )

        if next_rule:
            next_dto_raw = (
                next_rule.get(COL_DTO_BAL)
                if es_baleares and next_rule.get(COL_DTO_BAL) is not None
                else next_rule.get(COL_DTO_TER)
            )
            next_dto_max = _safe_dto(next_dto_raw)
            if next_dto_max is None:
                next_dto_max = 0.0

            if dto_solicitado <= next_dto_max:
                return {
                    "valid": False,
                    "msg": (
                        f"DTO Excedido: {dto_solicitado}% > Máx {dto_max}% "
                        f"(Tramo actual). En zona de escalado "
                        f"(Máx siguiente tramo {next_dto_max}%)"
                    ),
                    "status": "AVISO",
                    "rules": {"max": dto_max, "next_max": next_dto_max},
                }


        return {
            "valid": False,
            "msg": f"DTO Excedido: {dto_solicitado}% > Máx {dto_max}% (Tramo {base_imponible:.2f}€)",
            "status": "BLOQUEADO",
            "rules": {"max": dto_max},
        }

    def get_dto_for(
        self,
        segmento: str,
        familia: str,
        base_imponible: float,
        territorio: str,
        familias_en_pedido: Optional[set] = None,
    ) -> Optional[float]:
        """Helper: retorna el DTO m\u00e1ximo permitido para una combinaci\u00f3n dada, o None.
        Usa la misma l\u00f3gica de NaN/fallback que validate_range:
          - Baleares \u2192 DTO Baleares; si NaN \u2192 fallback a Territorial (Axarqu\u00eda)
          - Nunca retorna float('nan')
        Acepta c\u00f3digos internos: traduce v\u00eda resolve_familia_excel.
        """
        def _safe(v: Any) -> float | None:
            if v is None:
                return None
            try:
                f = float(v)
                return None if math.isnan(f) else f
            except (ValueError, TypeError):
                return None

        es_baleares = "baleares" in territorio.lower()
        familia_excel = self.resolve_familia_excel(familia, segmento, familias_en_pedido)
        if familia_excel is None:
            return None
        rules = self._get_tramo_rules(segmento, familia_excel)
        for r in rules:
            t_min = self._parse_tramo_minimo(r.get(COL_TRAMO))
            if base_imponible >= t_min:
                if es_baleares:
                    val = _safe(r.get(COL_DTO_BAL))
                    # Fallback a Territorial si Baleares es NaN (Axarquía)
                    if val is None:
                        val = _safe(r.get(COL_DTO_TER))
                else:
                    val = _safe(r.get(COL_DTO_TER))
                return val  # puede ser None si no hay DTO en la tabla
        return None

    def get_summary_stats(self) -> str:
        records = self.get_proposal_data()
        if not records:
            return "No hay datos disponibles"
        segments = {r.get(COL_SEGMENTO) for r in records if r.get(COL_SEGMENTO)}
        families = {r.get(COL_FAMILIA) for r in records if r.get(COL_FAMILIA)}
        return f"{len(records)} reglas · {len(segments)} segmentos · {len(families)} familias"


# Alias para compatibilidad hacia atrás
CommercialConditionsService = DiscountProposalService
