"""
ui/dialogs/product_calculator_dialog.py
────────────────────────────────────────────────────────────────────────────────
Calculadora Logística de Productos para Gabriela Rojas v4.0

Fuente primaria: Odoo (búsqueda exhaustiva igual que ProductQueryTab)
  · product.product → weight, volume, barcode, uom, precios
  · product.packaging + stock.package.type → UPP, dimensiones, pesos máx
  · product.template → sellers, tracking
  · product.supplierinfo → proveedor principal, lead time, precio compra
  · stock.quant → stock real por ubicación
  · stock.warehouse.orderpoint → reglas reaprovisionamiento
  · purchase.order.line → OCs pendientes

Fuente secundaria: CSV Maestro Imperbur (pallet_type, remontable, paso_palet)

Dos pestañas:
  · TAB 1 – POR SKU / MANUAL  : búsqueda, ficha completa, inputs bidireccionales
  · TAB 2 – POR PEDIDO (SO)   : carga líneas Odoo, calcula LDM por línea y total
────────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import csv
import io
import math
import re
import unicodedata
import urllib.request
import webbrowser
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QDoubleValidator, QFont
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

import bur2000_theme as t
from loguru import logger

# ── CSV Maestro (solo para enriquecer pallet_type/remontable/peso_palet) ─────
_CSV_URL = (
    "https://docs.google.com/spreadsheets/d/e/"
    "2PACX-1vTnOqJY2bxOMvHV9Zs0u1q6fX2I3jybjP2pleeEQozKddAHi43BrVx4"
    "H_PqZO7tB4KTbTJVjr5i6K48/pub?gid=487943712&single=true&output=csv"
)
_CSV_COL = {
    # Identificación
    "sku":           0,   # Referencia interna
    "name":          1,   # Nombre
    "familia":       2,   # Familia / Segmentación
    "subfamilia":    3,   # Sub Familia
    "tipologia":     4,   # Tipología (COMPRADO/FABRICADO)
    # Documentación
    "doc_ft":        7,   # Ficha Técnica
    "doc_ce":        10,  # Marcado CE
    # Comercial / Embalaje
    "unit":          15,  # Unidad de Medida de Venta
    "presentation":  16,  # Presentación (Bobina, Plancha...)
    "factor":        17,  # Factor (m²/bob, m²/plancha...)
    # Dimensiones físicas del producto
    "prod_ancho_m":  19,  # Ancho (m)
    "prod_largo_m":  20,  # Largo (m)
    "prod_espesor_mm": 21,# Espesor (mm)
    "masa_m2":       22,  # Masa por unidad de área (kg/m²)
    "densidad":      23,  # Densidad (kg/m³)
    # Logística del palé
    "pallet_type":   25,  # Tipo (Pallet Americano, Europa...)
    "ud_fisicas":    27,  # Unidades físicas incluidas por palé
    "upp":           28,  # Unidades de Venta incluidas (UPP en UM venta)
    "depal":         29,  # Despaletizable
    "peso_palet":    30,  # Peso palé (kg)
    "pal_ancho_m":   31,  # Ancho Tipo palé (m)
    "pal_largo_m":   32,  # Largo Tipo palé (m)
    "pal_alto_m":    33,  # Altura Tipo palé (m)
    "remontable":    34,  # Remontable / Apilable
    "n_alturas":     35,  # Número de alturas posibles
    "ruta":          36,  # Ruta Preferente
}

_PALLET_LDM   = {"EUROPA": 0.40, "AMERICANO": 0.50, "MEDIA EUROPA": 0.20, "OTRO": 0.40}
_TRUCK_WIDTH  = 2.40   # metros, ancho útil camión

# ── Helpers globales ──────────────────────────────────────────────────────────
def _normalize(s: str) -> str:
    s = s.lower().strip()
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return " ".join(s.split())

def _safe_float(v: Any) -> float:
    if not v and v != 0:
        return 0.0
    s = str(v).strip().replace("\xa0", "").replace('"', "").replace("%", "")
    if "," in s and "." not in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0

def _html_to_text(raw: Any) -> str:
    if not raw or raw is False:
        return ""
    s = re.sub(r"<[^>]+>", " ", str(raw))
    return re.sub(r"\s+", " ", s).strip()[:400]

def _parse_pallet_type(raw: str) -> str:
    raw_l = _normalize(raw)
    if "american" in raw_l:              return "AMERICANO"
    if "media" in raw_l and "euro" in raw_l: return "MEDIA EUROPA"
    if "euro" in raw_l or "2x1" in raw_l:   return "EUROPA"
    if raw_l:                            return "OTRO"
    return "EUROPA"

def _dim_to_m(v: float) -> float:
    """Convierte mm → m si v > 10 (Odoo guarda a veces en mm)."""
    if v <= 0:
        return 0.0
    return round(v * 0.001, 4) if v > 10 else round(v, 4)

def _ldm_from_dims(pals: float, dim_l: float, dim_w: float, stackable: bool) -> float:
    """LDM exacto si tenemos dimensiones del palé."""
    if dim_l > 0 and dim_w > 0 and _TRUCK_WIDTH > 0:
        cols = max(1, math.floor(_TRUCK_WIDTH / dim_w))
        ldm_per = dim_l / cols
        if stackable:
            ldm_per /= 2.0
        return round(pals * ldm_per, 3)
    return 0.0

def _ldm_std(pals: float, pallet_type: str, stackable: bool) -> float:
    """LDM estándar cuando no hay dimensiones exactas."""
    ldm_p = _PALLET_LDM.get(pallet_type, 0.40)
    if stackable:
        ldm_p /= 2.0
    return round(pals * ldm_p, 3)

def _calc_ldm(pals: float, dim_l: float, dim_w: float,
              pallet_type: str, stackable: bool) -> float:
    exact = _ldm_from_dims(pals, dim_l, dim_w, stackable)
    if exact > 0:
        return exact
    return _ldm_std(pals, pallet_type, stackable)


def _build_breakdown(total_qty: float, pkg_levels: List[Dict]) -> str:
    """
    Dado el total de unidades y la lista de niveles de embalaje ordenados
    de mayor a menor (palé → caja → ud), calcula el desglose exacto:
      «2 Palé + 1 Caja + 15 m²»
    Si no hay niveles definidos, devuelve la cantidad bruta.
    """
    if not pkg_levels or total_qty <= 0:
        return f"{total_qty:g}"

    parts: List[str] = []
    remaining = total_qty
    for level in pkg_levels:
        qty_per = float(level.get("qty") or 0)
        name_   = level.get("name") or "ud"
        if qty_per <= 0:
            continue
        n_full = math.floor(remaining / qty_per)
        if n_full > 0:
            parts.append(f"{n_full:g} {name_}")
        remaining = round(remaining - n_full * qty_per, 6)

    if remaining > 0.001:
        parts.append(f"{remaining:g} ud")

    return " + ".join(parts) if parts else f"{total_qty:g}"


# ══════════════════════════════════════════════════════════════════════════════
# Worker: carga CSV (secundario, para pallet_type/remontable)
# ══════════════════════════════════════════════════════════════════════════════
class _CsvWorker(QThread):
    loaded = Signal(dict)
    def run(self):
        try:
            with urllib.request.urlopen(_CSV_URL, timeout=20) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
            reader = csv.reader(io.StringIO(raw))
            rows   = list(reader)
            out    = {}
            for row in rows[3:]:
                while len(row) <= max(_CSV_COL.values()):
                    row.append("")
                sku  = row[_CSV_COL["sku"]].strip()
                name = row[_CSV_COL["name"]].strip()
                if not sku and not name:
                    continue

                def _g(col_key: str) -> str:
                    """Extrae celda de forma segura por clave de _CSV_COL."""
                    idx = _CSV_COL.get(col_key, -1)
                    return row[idx].strip() if 0 <= idx < len(row) else ""

                rec = {
                    "sku":              sku,
                    "name":             name,
                    # Segmentación
                    "familia":          _g("familia"),
                    "subfamilia":       _g("subfamilia"),
                    "tipologia":        _g("tipologia"),
                    # Documentación
                    "doc_ft":           _g("doc_ft"),
                    "doc_ce":           _g("doc_ce"),
                    # Comercial
                    "unit":             _g("unit"),
                    "presentation":     _g("presentation"),
                    "factor":           _safe_float(_g("factor")),
                    # Dimensiones físicas del producto
                    "prod_ancho_m":     _safe_float(_g("prod_ancho_m")),
                    "prod_largo_m":     _safe_float(_g("prod_largo_m")),
                    "prod_espesor_mm":  _safe_float(_g("prod_espesor_mm")),
                    "masa_m2":          _safe_float(_g("masa_m2")),
                    "densidad":         _safe_float(_g("densidad")),
                    # Logística palé
                    "pallet_type":      _parse_pallet_type(_g("pallet_type")),
                    "pallet_type_raw":  _g("pallet_type"),
                    "ud_fisicas":       _safe_float(_g("ud_fisicas")),
                    "units_per_pallet": _safe_float(_g("upp")),
                    "depalletizable":   _g("depal").strip().lower() in ("si", "sí", "yes", "1"),
                    "peso_palet":       _safe_float(_g("peso_palet")),
                    # Dimensiones del palé tipo
                    "pal_ancho_m":      _safe_float(_g("pal_ancho_m")),
                    "pal_largo_m":      _safe_float(_g("pal_largo_m")),
                    "pal_alto_m":       _safe_float(_g("pal_alto_m")),
                    # Apilado
                    "is_stackable":     _g("remontable").strip().lower() in ("si", "sí", "yes", "1"),
                    "n_alturas":        _safe_float(_g("n_alturas")),
                    "ruta_preferente":  _g("ruta"),
                }
                if sku:
                    out[_normalize(sku)]  = rec
                if name and _normalize(name) not in out:
                    out[_normalize(name)] = rec
            logger.info(f"[Calc] CSV: {len(out)//2} productos cargados")
            self.loaded.emit(out)
        except Exception as e:
            logger.warning(f"[Calc] CSV error: {e}")
            self.loaded.emit({})


# ══════════════════════════════════════════════════════════════════════════════
# Worker: búsqueda exhaustiva en Odoo (producto + embalajes + stock + OCs)
# ══════════════════════════════════════════════════════════════════════════════
class _OdooProductWorker(QThread):
    result = Signal(dict)
    error  = Signal(str)

    def __init__(self, svc, query: str, csv_catalog: dict, parent=None):
        super().__init__(parent)
        self.svc     = svc
        self.query   = query.strip()
        self.catalog = csv_catalog

    def run(self):
        svc = self.svc
        if not svc:
            self.error.emit("Sin conexión a Odoo.")
            return
        try:
            def _ex(model, method, *args, **kw):
                """Ejecuta llamada Odoo. Intenta adquirir lock con timeout=10s."""
                try:
                    acquired = svc._lock.acquire(timeout=10)
                    if not acquired:
                        logger.warning(f"[Calc] Lock ocupado, reintentando sin lock: {model}.{method}")
                        # Intento sin lock como fallback (Odoo XML-RPC es stateless)
                        try:
                            svc._ensure_connected()
                            fn = getattr(svc.odoo.env[model], method)
                            return fn(*args, **kw)
                        except Exception as e2:
                            logger.warning(f"[Calc] Fallback Odoo {model}.{method}: {e2}")
                            return [] if method in ("search", "search_read") else None
                    try:
                        svc._ensure_connected()
                        fn = getattr(svc.odoo.env[model], method)
                        return fn(*args, **kw)
                    finally:
                        svc._lock.release()
                except Exception as e:
                    logger.warning(f"[Calc] Odoo {model}.{method}: {e}")
                    return [] if method in ("search", "search_read") else None

            q = self.query
            # 1. Búsqueda — también elimina espacios extras que puedan romper la query
            q_clean = q.strip()
            PP_FIELDS = [
                "id", "default_code", "name", "barcode",
                "weight", "volume", "packaging_ids", "product_tmpl_id",
                "uom_id", "list_price", "standard_price",
                "description", "description_picking",
                "description_pickingin", "description_pickingout",
                "categ_id", "active",
            ]
            # Búsqueda exacta por SKU
            pp_ids = _ex("product.product", "search", [["default_code", "=", q_clean],
                                                        ["active", "in", [True, False]]], limit=5)
            # Búsqueda parcial por SKU
            if not pp_ids:
                pp_ids = _ex("product.product", "search", [["default_code", "ilike", q_clean],
                                                            ["active", "in", [True, False]]], limit=10)
            # Búsqueda por nombre
            if not pp_ids:
                pp_ids = _ex("product.product", "search", [["name", "ilike", q_clean],
                                                            ["active", "in", [True, False]]], limit=10)
            if not pp_ids:
                self.error.emit(f"'{q_clean}' no encontrado en Odoo.")
                return


            pp_rows = _ex("product.product", "read", list(pp_ids), PP_FIELDS)
            if not pp_rows:
                self.error.emit("Error leyendo producto de Odoo.")
                return

            pp        = pp_rows[0]
            prod_id   = pp["id"]
            weight    = float(pp.get("weight") or 0)
            volume    = float(pp.get("volume") or 0)
            barcode   = str(pp["barcode"] or "") if pp.get("barcode") else ""

            uom_raw   = pp.get("uom_id")
            uom       = uom_raw[1] if isinstance(uom_raw, (list, tuple)) else str(uom_raw or "ud")
            # Detectar UoM de superficie (m²) — crítico para UPP real
            _UOM_MEASURE_KW = ("m\u00b2", "m2", "superficie", "surface", "area")
            uom_is_measure  = any(kw in uom.lower() for kw in _UOM_MEASURE_KW)
            categ_raw = pp.get("categ_id")
            categ     = categ_raw[1] if isinstance(categ_raw, (list, tuple)) else ""
            sku       = str(pp.get("default_code") or "")
            name      = str(pp.get("name") or "")

            # Notas
            notes_parts = []
            for k in ("description", "description_picking", "description_pickingin", "description_pickingout"):
                t_ = _html_to_text(pp.get(k))
                if t_:
                    notes_parts.append(t_)
            notes = " | ".join(dict.fromkeys(notes_parts))

            # 2. Embalajes (product.packaging → stock.package.type)
            pkg_ids = [int(x) for x in (pp.get("packaging_ids") or []) if x]
            pkg_rows = _ex("product.packaging", "read", pkg_ids,
                           ["name", "qty", "barcode", "package_type_id"]) if pkg_ids else []
            if not isinstance(pkg_rows, list):
                pkg_rows = []

            def _enrich_dims(rows):
                if not rows:
                    return rows
                type_ids = list({int(r["package_type_id"][0]) for r in rows
                                 if r.get("package_type_id")})
                if not type_ids:
                    return rows
                t_rows = _ex("stock.package.type", "read", type_ids,
                             ["id", "name", "packaging_length", "width", "height", "max_weight"])
                tmap = {t_["id"]: t_ for t_ in (t_rows or [])}
                for r in rows:
                    pt = r.get("package_type_id")
                    if pt:
                        td = tmap.get(int(pt[0]), {})
                        r["dim_l"]      = float(td.get("packaging_length") or 0)
                        r["dim_w"]      = float(td.get("width")            or 0)
                        r["dim_h"]      = float(td.get("height")           or 0)
                        r["max_weight"] = float(td.get("max_weight")       or 0)
                        r["pkg_type_name"] = str(td.get("name") or "")
                    else:
                        r["dim_l"] = r["dim_w"] = r["dim_h"] = r["max_weight"] = 0.0
                        r["pkg_type_name"] = ""
                return rows

            pkg_rows = _enrich_dims(pkg_rows)

            # 3. Template (sellers, tracking, packaging fallback)
            tmpl_ref = pp.get("product_tmpl_id")
            tmpl_id  = int(tmpl_ref[0]) if isinstance(tmpl_ref, (list, tuple)) else None
            sellers: List[Dict] = []
            tracking_label = "⭕ Sin seguimiento"
            tmpl_data: Dict = {}

            if tmpl_id:
                t_rows = _ex("product.template", "read", [tmpl_id],
                              ["name", "weight", "volume", "packaging_ids",
                               "seller_ids", "tracking",
                               "description", "description_sale", "description_purchase"])
                if t_rows:
                    tmpl_data = t_rows[0]
                    if not pkg_rows:
                        t_pkg_ids = [int(x) for x in (tmpl_data.get("packaging_ids") or []) if x]
                        tp = _ex("product.packaging", "read", t_pkg_ids,
                                 ["name", "qty", "barcode", "package_type_id"]) if t_pkg_ids else []
                        pkg_rows = _enrich_dims(tp if isinstance(tp, list) else [])
                    if weight == 0:
                        weight = float(tmpl_data.get("weight") or 0)
                    if volume == 0:
                        volume = float(tmpl_data.get("volume") or 0)
                    for k in ("description", "description_sale", "description_purchase"):
                        tx = _html_to_text(tmpl_data.get(k))
                        if tx and tx not in notes:
                            notes = (notes + " | " + tx).strip(" |")

                    # Sellers
                    s_ids = [int(x) for x in (tmpl_data.get("seller_ids") or []) if x]
                    if s_ids:
                        s_rows = _ex("product.supplierinfo", "read", s_ids[:8],
                                      ["partner_id", "product_code", "product_name",
                                       "price", "min_qty", "delay", "currency_id", "sequence"])
                        if s_rows:
                            for s in sorted(s_rows, key=lambda x: int(x.get("sequence") or 0)):
                                p_r = s.get("partner_id")
                                c_r = s.get("currency_id")
                                sellers.append({
                                    "name":     p_r[1] if isinstance(p_r, (list, tuple)) else str(p_r or ""),
                                    "code":     str(s.get("product_code") or ""),
                                    "price":    float(s.get("price") or 0),
                                    "min_qty":  float(s.get("min_qty") or 0),
                                    "delay":    int(s.get("delay") or 0),
                                    "currency": c_r[1] if isinstance(c_r, (list, tuple)) else "EUR",
                                })
                    t_raw = str(tmpl_data.get("tracking") or "none")
                    tracking_label = {"serial": "🔢 Por Nº Serie", "lot": "📦 Por Lote",
                                      "none": "⭕ Sin seguimiento"}.get(t_raw, "⭕ Sin seguimiento")

            # 4. Stock real por ubicación
            stock_by_loc: List[Dict] = []
            q_rows = _ex("stock.quant", "search_read",
                          [["product_id", "=", prod_id],
                           ["location_id.usage", "=", "internal"]],
                          fields=["location_id", "quantity", "reserved_quantity"], limit=30)
            if isinstance(q_rows, list):
                for qr in q_rows:
                    loc_r  = qr.get("location_id")
                    loc    = loc_r[1] if isinstance(loc_r, (list, tuple)) else str(loc_r or "")
                    oh     = float(qr.get("quantity") or 0)
                    res    = float(qr.get("reserved_quantity") or 0)
                    if oh or res:
                        stock_by_loc.append({"location": loc, "on_hand": oh,
                                             "reserved": res, "available": oh - res})

            # 5. Reglas de reaprovisionamiento
            reorder_rules: List[Dict] = []
            op_rows = _ex("stock.warehouse.orderpoint", "search_read",
                           [["product_id", "=", prod_id]],
                           fields=["product_min_qty", "product_max_qty", "qty_on_hand", "warehouse_id"],
                           limit=5)
            if isinstance(op_rows, list):
                for op in op_rows:
                    wh = op.get("warehouse_id")
                    reorder_rules.append({
                        "warehouse": wh[1] if isinstance(wh, (list, tuple)) else str(wh or ""),
                        "min_qty":   float(op.get("product_min_qty") or 0),
                        "max_qty":   float(op.get("product_max_qty") or 0),
                        "on_hand":   float(op.get("qty_on_hand") or 0),
                    })

            # 6. OCs pendientes
            pending_po: List[Dict] = []
            pl_rows = _ex("purchase.order.line", "search_read",
                           [["product_id", "=", prod_id],
                            ["state", "in", ["purchase", "sent"]]],
                           fields=["product_qty", "qty_received", "date_planned",
                                   "order_id", "partner_id", "price_unit"],
                           limit=10, order="date_planned asc")
            if isinstance(pl_rows, list):
                for pl in pl_rows:
                    qty_pen = float(pl.get("product_qty") or 0) - float(pl.get("qty_received") or 0)
                    if qty_pen <= 0:
                        continue
                    o_r = pl.get("order_id"); p_r = pl.get("partner_id")
                    pending_po.append({
                        "order":   o_r[1] if isinstance(o_r, (list, tuple)) else str(o_r or ""),
                        "partner": p_r[1] if isinstance(p_r, (list, tuple)) else str(p_r or ""),
                        "qty_pen": qty_pen,
                        "date":    str(pl.get("date_planned") or "")[:10],
                        "price":   float(pl.get("price_unit") or 0),
                    })

            # 7. Analizar embalajes
            pkg_details: List[Dict] = []
            upp = 0.0; bundle_qty = 0.0; bundle_name = ""; pkg_barcode = ""
            raw_dim_l = raw_dim_w = raw_dim_h = 0.0; pkg_max_kg = 0.0; pkg_type_name = ""
            # Para productos de superficie: m²/unidad vs m²/palet
            unit_pkg_qty = 0.0   # m² (o unidades) por embalaje unitario (bobina/plancha/rollo)

            if pkg_rows:
                pkg_sorted = sorted(pkg_rows, key=lambda r: float(r.get("qty") or 0), reverse=True)
                big = pkg_sorted[0]
                raw_dim_l   = float(big.get("dim_l") or 0)
                raw_dim_w   = float(big.get("dim_w") or 0)
                raw_dim_h   = float(big.get("dim_h") or 0)
                pkg_max_kg  = float(big.get("max_weight") or 0)
                pkg_type_name = big.get("pkg_type_name", "")
                bc_raw      = big.get("barcode")
                pkg_barcode = str(bc_raw) if bc_raw and bc_raw is not False else ""

                palet_qty_odoo = float(big.get("qty") or 0)  # qty del nivel más alto

                if len(pkg_sorted) > 1:
                    sec        = pkg_sorted[1]
                    unit_pkg_qty = float(sec.get("qty") or 0)   # m²/bobina (nivel unitario)
                    bundle_name  = str(sec.get("name") or "Caja")

                # ── Corrección UoM m² (MEMORY §8-9-10) ───────────────────────
                # Para m²: Odoo almacena qty en la UoM del producto.
                #   pkg_sorted[0].qty = m²/palet (ej: 800)
                #   pkg_sorted[1].qty = m²/bobina (ej: 25)
                # UPP real = bobinas/palet = 800 / 25 = 32
                # weight real = kg/m² × m²/bobina (Odoo weight = kg/m²)
                if uom_is_measure and unit_pkg_qty > 1.001 and palet_qty_odoo > 0:
                    upp        = round(palet_qty_odoo / unit_pkg_qty, 4)  # bobinas/palet
                    bundle_qty = upp                                        # compat. desglose
                    # Ajustar peso: weight es kg/m² → kg/bobina = kg/m² × m²/bobina
                    if weight > 0:
                        weight = round(weight * unit_pkg_qty, 4)  # kg/bobina
                    logger.debug(
                        f"[Calc] UoM m² detectada ({uom}): "
                        f"palet={palet_qty_odoo} m², bobina={unit_pkg_qty} m², "
                        f"UPP corregido={upp} bob/pal, peso bob={weight:.3f} kg"
                    )
                else:
                    # Producto regular (unidades, ml, kg): UPP = qty más alto directo
                    upp        = palet_qty_odoo
                    bundle_qty = float(pkg_sorted[1].get("qty") or 0) if len(pkg_sorted) > 1 else 0.0

                for p_ in pkg_sorted:
                    bc = p_.get("barcode")
                    pkg_details.append({
                        "name":    str(p_.get("name") or ""),
                        "qty":     float(p_.get("qty") or 0),
                        "barcode": str(bc) if bc and bc is not False else "",
                        "l_m":     _dim_to_m(float(p_.get("dim_l") or 0)),
                        "w_m":     _dim_to_m(float(p_.get("dim_w") or 0)),
                        "h_m":     _dim_to_m(float(p_.get("dim_h") or 0)),
                        "max_kg":  float(p_.get("max_weight") or 0),
                        "type":    p_.get("pkg_type_name", ""),
                    })

            # Convertir dimensiones principales mm→m
            dim_l = _dim_to_m(raw_dim_l)
            dim_w = _dim_to_m(raw_dim_w)
            dim_h = _dim_to_m(raw_dim_h)

            # 8. Enriquecer con CSV (pallet_type, apilable, peso_palet)
            csv_rec = self.catalog.get(_normalize(sku)) or self.catalog.get(_normalize(name)) or {}
            pallet_type = csv_rec.get("pallet_type", "")
            if not pallet_type and pkg_type_name:
                pallet_type = _parse_pallet_type(pkg_type_name)
            if not pallet_type:
                pallet_type = "EUROPA"
            is_stackable   = csv_rec.get("is_stackable", False)
            peso_palet_csv = float(csv_rec.get("peso_palet") or 0)
            # Calcular peso del palé:
            #   - Prioridad 1: CSV Maestro (dato verificado)
            #   - Prioridad 2: weight (ya corregido a kg/bobina) × UPP (bobinas/palet)
            #   - Prioridad 3: pkg_max_kg de Odoo
            peso_palet = peso_palet_csv
            if peso_palet == 0 and weight > 0 and upp > 0:
                peso_palet = weight * upp  # weight ya está en kg/bobina tras corrección UoM
            if pkg_max_kg > 0 and peso_palet == 0:
                peso_palet = pkg_max_kg

            # Presentación (bultos)
            pres_name   = csv_rec.get("presentation", "")
            pres_factor = float(csv_rec.get("factor") or 0)
            unit_csv    = csv_rec.get("unit", "") or uom

            # URLs Odoo
            base_url = (svc.url or "").rstrip("/")
            odoo_url_tmpl = f"{base_url}/odoo/inventory/products/{tmpl_id}" if tmpl_id else ""

            seller_main = sellers[0] if sellers else {}

            self.result.emit({
                # Identidad
                "product_id":   prod_id,
                "tmpl_id":      tmpl_id,
                "sku":          sku,
                "name":         name,
                "barcode":      barcode,
                "pkg_barcode":  pkg_barcode,
                "uom":          uom,
                "unit_csv":     unit_csv,
                "categ":        categ,
                "tracking":     tracking_label,
                "notes":        notes,
                # Peso / volumen
                "weight_unit_kg": weight,          # kg/unidad Odoo
                "volume_m3":      volume,
                "peso_palet":     peso_palet,       # kg bruto palé
                # Embalajes
                "upp":           upp,            # bobinas/palet (corregido para m²)
                "unit_pkg_qty":  unit_pkg_qty,   # m²/bobina (0 para productos regulares)
                "uom_is_measure":uom_is_measure,  # True si la UoM es superficie
                "bundle_qty":    bundle_qty,
                "bundle_name":   bundle_name,
                "pres_name":     pres_name,
                "pres_factor":   pres_factor,
                # Dimensiones palé principal (m)
                "dim_l":        dim_l,
                "dim_w":        dim_w,
                "dim_h":        dim_h,
                "pkg_max_kg":   pkg_max_kg,
                "pkg_type_name":pkg_type_name,
                "pkg_details":  pkg_details,
                # Logística / LDM
                "pallet_type":  pallet_type,
                "is_stackable": is_stackable,
                # Precios
                "list_price":   float(pp.get("list_price") or 0),
                "std_price":    float(pp.get("standard_price") or 0),
                # Proveedor
                "seller_name":  seller_main.get("name", ""),
                "seller_code":  seller_main.get("code", ""),
                "seller_price": seller_main.get("price", 0.0),
                "seller_delay": seller_main.get("delay", 0),
                "all_sellers":  sellers,
                # Stock
                "stock_by_loc": stock_by_loc,
                "reorder_rules":reorder_rules,
                "pending_po":   pending_po,
                # URL
                "odoo_url":     odoo_url_tmpl,
                # CSV maestro crudo (para diagnóstico de campos faltantes)
                "csv_rec":      csv_rec,
            })

        except Exception as exc:
            logger.error(f"[Calc] Worker error: {exc}")
            import traceback
            logger.debug(traceback.format_exc())
            self.error.emit(f"Error al buscar: {str(exc)[:120]}")


# ══════════════════════════════════════════════════════════════════════════════
# Worker: pedido SO
# ══════════════════════════════════════════════════════════════════════════════
class _OrderWorker(QThread):
    result = Signal(dict)
    error  = Signal(str)

    def __init__(self, svc, so_name: str, csv_catalog: dict, parent=None):
        super().__init__(parent)
        self.svc     = svc
        self.so_name = so_name.strip()
        self.catalog = csv_catalog

    def run(self):
        svc = self.svc
        if not svc:
            self.error.emit("Sin conexión a Odoo.")
            return
        try:
            def _ex(model, method, *args, **kw):
                try:
                    with svc._lock:
                        svc._ensure_connected()
                        return getattr(svc.odoo.env[model], method)(*args, **kw)
                except Exception as e:
                    logger.warning(f"[Order] {model}.{method}: {e}")
                    return [] if method in ("search", "search_read") else None

            orders = _ex("sale.order", "search_read",
                          [["name", "=", self.so_name]],
                          fields=["id", "name", "order_line", "partner_id",
                                  "amount_total", "date_order"])
            if not orders:
                self.error.emit(f"Pedido '{self.so_name}' no encontrado.")
                return
            order = orders[0]
            line_ids = order.get("order_line", [])
            if not line_ids:
                self.error.emit("El pedido no tiene líneas.")
                return

            lines = _ex("sale.order.line", "read", list(line_ids),
                         ["product_id", "product_uom_qty", "product_uom",
                          "price_unit", "price_subtotal", "discount"])
            if not lines:
                self.error.emit("No se pudieron leer las líneas.")
                return

            enriched = []
            for line in lines:
                if not line.get("product_id"):
                    continue
                prod_id   = line["product_id"][0]
                prod_name = line["product_id"][1]
                qty       = float(line.get("product_uom_qty") or 0)

                # SKU
                pp = _ex("product.product", "read", [prod_id], ["default_code", "weight"])
                sku    = str(pp[0].get("default_code") or "") if pp else ""
                w_unit = float(pp[0].get("weight") or 0)     if pp else 0.0

                # ── Embalajes: TODOS los niveles (palé, caja, ud) + dimensiones exactas
                pp_pkg = _ex("product.product", "read", [prod_id],
                             ["packaging_ids", "uom_id"])
                pkg_ids = [int(x) for x in (pp_pkg[0].get("packaging_ids") or [])] if pp_pkg else []

                # UoM del producto — necesario para detectar si es m²
                uom_raw_line = (pp_pkg[0].get("uom_id") if pp_pkg else None)
                uom_line = uom_raw_line[1] if isinstance(uom_raw_line, (list, tuple)) else str(uom_raw_line or "ud")
                _UOM_MEASURE_KW = ("m\u00b2", "m2", "superficie", "surface", "area")
                uom_is_measure_line = any(kw in uom_line.lower() for kw in _UOM_MEASURE_KW)

                pkg_data = _ex("product.packaging", "read", pkg_ids,
                               ["name", "qty", "barcode", "package_type_id"]) if pkg_ids else []

                # Enriquecer con dimensiones del tipo de palé (GAP 4)
                if isinstance(pkg_data, list) and pkg_data:
                    type_ids_line = list({
                        int(r["package_type_id"][0])
                        for r in pkg_data if r.get("package_type_id")
                    })
                    if type_ids_line:
                        t_rows_line = _ex(
                            "stock.package.type", "read", type_ids_line,
                            ["id", "name", "packaging_length", "width", "height", "max_weight"]
                        ) or []
                        tmap_line = {t_["id"]: t_ for t_ in t_rows_line}
                        for r in pkg_data:
                            pt = r.get("package_type_id")
                            if pt:
                                td = tmap_line.get(int(pt[0]), {})
                                r["dim_l"]  = float(td.get("packaging_length") or 0)
                                r["dim_w"]  = float(td.get("width")            or 0)
                                r["dim_h"]  = float(td.get("height")           or 0)
                            else:
                                r["dim_l"] = r["dim_w"] = r["dim_h"] = 0.0

                pkg_levels: List[Dict] = []
                upp = 0.0
                pkg_type_name_line = ""
                line_dim_l = line_dim_w = 0.0   # dimensiones del nivel más alto
                unit_pkg_qty_line  = 0.0         # m²/bobina (para UoM m²)

                if isinstance(pkg_data, list) and pkg_data:
                    pkg_sorted_line = sorted(pkg_data,
                                            key=lambda r: float(r.get("qty") or 0),
                                            reverse=True)
                    for pk in pkg_sorted_line:
                        pt_ref = pk.get("package_type_id")
                        pt_name = pt_ref[1] if isinstance(pt_ref, (list, tuple)) else ""
                        bc_raw = pk.get("barcode")
                        pkg_levels.append({
                            "name":    str(pk.get("name") or ""),
                            "qty":     float(pk.get("qty") or 0),
                            "barcode": str(bc_raw) if bc_raw and bc_raw is not False else "",
                            "type":    pt_name,
                        })

                    biggest = pkg_sorted_line[0]
                    palet_qty_odoo_line = float(biggest.get("qty") or 0)
                    pt_big  = biggest.get("package_type_id")
                    if pt_big:
                        pkg_type_name_line = pt_big[1] if isinstance(pt_big, (list, tuple)) else ""

                    # Dimensiones exactas del nivel más alto (mm → m)
                    line_dim_l = _dim_to_m(float(biggest.get("dim_l") or 0))
                    line_dim_w = _dim_to_m(float(biggest.get("dim_w") or 0))

                    # UoM m²: nivel unitario para el ratio bobinas/palet
                    if len(pkg_sorted_line) > 1:
                        unit_pkg_qty_line = float(pkg_sorted_line[1].get("qty") or 0)

                    # ─ Corrección UoM m² (igual que en _OdooProductWorker) ─
                    if uom_is_measure_line and unit_pkg_qty_line > 1.001 and palet_qty_odoo_line > 0:
                        upp = round(palet_qty_odoo_line / unit_pkg_qty_line, 4)  # bobinas/palet
                        # Ajustar w_unit: kg/m² → kg/bobina
                        if w_unit > 0:
                            w_unit = round(w_unit * unit_pkg_qty_line, 4)
                    else:
                        upp = palet_qty_odoo_line

                # CSV enriquecimiento (pallet_type, apilable, peso_palet)
                key  = _normalize(sku) if sku else _normalize(prod_name)
                csv_ = self.catalog.get(key) or {}
                if not csv_ and sku:
                    for k, v in self.catalog.items():
                        if _normalize(sku) in k or k in _normalize(sku):
                            csv_ = v; break

                pallet_type  = csv_.get("pallet_type", _parse_pallet_type(pkg_type_name_line) or "EUROPA")
                is_stackable = csv_.get("is_stackable", False)
                peso_palet   = float(csv_.get("peso_palet") or 0)
                csv_upp      = float(csv_.get("units_per_pallet") or 0)
                final_upp    = upp or csv_upp  # Odoo primero, CSV como fallback

                # Peso línea
                if final_upp > 0 and peso_palet > 0:
                    line_weight = (qty / final_upp) * peso_palet
                elif w_unit > 0:
                    line_weight = qty * w_unit
                else:
                    line_weight = 0.0

                pals_frac = (qty / final_upp) if final_upp > 0 else 0.0

                # ─ LDM exacto si hay dimensiones, estándar si no (GAP 4) ─
                ldm_line = _calc_ldm(pals_frac, line_dim_l, line_dim_w,
                                     pallet_type, is_stackable)

                # ── Desglose visual: N pal + M caj + X ud
                breakdown = _build_breakdown(qty, pkg_levels)

                uom_raw = line.get("product_uom")
                uom     = uom_raw[1] if isinstance(uom_raw, (list, tuple)) else str(uom_raw or "ud")

                enriched.append({
                    "sku":         sku or "—",
                    "name":        prod_name,
                    "qty":         qty,
                    "uom":         uom,
                    "upp":         final_upp,
                    "pallet_type": pallet_type,
                    "stackable":   is_stackable,
                    "pals":        pals_frac,
                    "weight":      line_weight,
                    "ldm":         ldm_line,
                    "ldm_exact":   line_dim_l > 0 and line_dim_w > 0,  # True = dimensiones reales
                    "price":       float(line.get("price_subtotal") or 0),
                    "has_logistic":final_upp > 0,
                    "pkg_levels":  pkg_levels,
                    "breakdown":   breakdown,
                })

            p_r     = order.get("partner_id")
            partner = p_r[1] if isinstance(p_r, (list, tuple)) else ""

            self.result.emit({
                "so_name": order.get("name", self.so_name),
                "partner": partner,
                "amount":  float(order.get("amount_total") or 0),
                "lines":   enriched,
            })
        except Exception as exc:
            logger.error(f"[Order] error: {exc}")
            self.error.emit(str(exc))


# ══════════════════════════════════════════════════════════════════════════════
# Diálogo principal
# ══════════════════════════════════════════════════════════════════════════════
class ProductCalculatorDialog(QDialog):
    def __init__(self, odoo_service=None, parent: QWidget | None = None):
        super().__init__(parent)
        self.odoo_service  = odoo_service
        self._csv_catalog: Dict[str, Any] = {}
        self._product: Optional[Dict[str, Any]] = None
        self._is_updating  = False
        self._csv_ready    = False

        self.setWindowTitle("🧮 Calculadora Logística · Gabriela")
        self.resize(820, 960)
        self.setMinimumSize(680, 820)
        self._build_ui()
        self._load_csv()

    # ─────────────────────────────────────────────────────────────────────────
    # UI BUILD
    # ─────────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        hdr = QFrame(); hdr.setFixedHeight(66)
        hdr.setStyleSheet(f"background:{t.BUR.primary};")
        hl  = QHBoxLayout(hdr); hl.setContentsMargins(20, 0, 20, 0)
        ico = QLabel("🧮"); ico.setFont(QFont("Segoe UI Emoji", 20))
        ico.setStyleSheet("color:white; background:transparent;")
        tv  = QVBoxLayout()
        lt  = QLabel("CALCULADORA LOGÍSTICA")
        lt.setStyleSheet("color:white; font-size:16px; font-weight:800; background:transparent; letter-spacing:1px;")
        ls  = QLabel("Odoo · CSV Imperbur · Pallets · LDM · Stock · OCs")
        ls.setStyleSheet(f"color:{t.BUR.secondary}; font-size:10px; background:transparent; font-weight:600;")
        tv.addWidget(lt); tv.addWidget(ls)
        hl.addWidget(ico); hl.addSpacing(10); hl.addLayout(tv); hl.addStretch()
        root.addWidget(hdr)

        # Top progress
        self.prg = QProgressBar(); self.prg.setRange(0, 0); self.prg.setFixedHeight(3)
        self.prg.setStyleSheet(
            f"QProgressBar {{ border:none; background:{t.BUR.border}; }}"
            f"QProgressBar::chunk {{ background:{t.BUR.secondary}; }}"
        )
        root.addWidget(self.prg)

        # Tabs
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(f"""
            QTabWidget::pane {{ border:none; background:{t.BUR.background}; top:-1px; }}
            QTabBar::tab {{ background:{t.BUR.lvl2}; padding:11px 22px; font-weight:700;
                color:{t.BUR.accent}; border-top-left-radius:6px; border-top-right-radius:6px;
                font-size:12px; margin-right:2px; }}
            QTabBar::tab:selected {{ background:{t.BUR.background}; color:{t.BUR.primary};
                border-top:3px solid {t.BUR.secondary}; font-weight:800; }}
        """)
        self.tabs.addTab(self._tab_sku(),   "📦 POR SKU / MANUAL")
        self.tabs.addTab(self._tab_order(), "🗒️ POR PEDIDO (SO)")
        root.addWidget(self.tabs, 1)

        # Footer
        ftr = QFrame(); ftr.setStyleSheet(f"background:white; border-top:1px solid {t.BUR.border};")
        fl  = QHBoxLayout(ftr); fl.setContentsMargins(16, 8, 16, 8)
        self.lbl_foot = QLabel("⏳ Enlazando con CSV maestro…")
        self.lbl_foot.setStyleSheet(f"color:{t.BUR.accent}; font-size:10px;")
        fl.addWidget(self.lbl_foot); fl.addStretch()
        bc = self._btn("Limpiar", outline=True);  bc.clicked.connect(self._clear_all)
        bx = self._btn("Cerrar", primary=True);  bx.clicked.connect(self.accept)
        fl.addWidget(bc); fl.addWidget(bx)
        root.addWidget(ftr)
        QTimer.singleShot(200, self.ed_search.setFocus)

    # ── Tab 1: Por SKU ────────────────────────────────────────────────────────
    def _tab_sku(self) -> QWidget:
        page = QWidget(); page.setStyleSheet(f"background:{t.BUR.background};")
        lay  = QVBoxLayout(page); lay.setContentsMargins(20, 16, 20, 16); lay.setSpacing(12)

        # Búsqueda
        sc  = self._card(); sl = QVBoxLayout(sc); sl.setContentsMargins(16,14,16,14); sl.setSpacing(8)
        lh  = QLabel("BUSCAR PRODUCTO EN ODOO (SKU O NOMBRE)")
        lh.setStyleSheet(f"color:{t.BUR.primary}; font-weight:800; font-size:10px; letter-spacing:1px;")
        sl.addWidget(lh)
        row = QHBoxLayout()
        self.ed_search = QLineEdit(); self.ed_search.setPlaceholderText("SKU, referencia o nombre del producto…")
        self.ed_search.setMinimumHeight(36); self.ed_search.setStyleSheet(self._css_input())
        self.ed_search.returnPressed.connect(self._search_odoo)
        self.btn_search = self._btn("Buscar", primary=True); self.btn_search.setMinimumHeight(36)
        self.btn_search.setMinimumWidth(90); self.btn_search.clicked.connect(self._search_odoo)
        row.addWidget(self.ed_search); row.addWidget(self.btn_search); sl.addLayout(row)
        self.lbl_search_status = QLabel("Introduce un SKU o nombre y pulsa Buscar.")
        self.lbl_search_status.setStyleSheet(f"color:{t.BUR.accent}; font-size:11px; font-style:italic;")
        sl.addWidget(self.lbl_search_status)
        lay.addWidget(sc)

        # Ficha del producto (scrollable)
        self.prod_scroll = QScrollArea(); self.prod_scroll.setWidgetResizable(True)
        self.prod_scroll.setStyleSheet("QScrollArea { border:none; background:transparent; }")
        self.prod_scroll.setVisible(False)
        self.prod_inner = QWidget(); self.prod_inner.setStyleSheet(f"background:{t.BUR.background};")
        pil = QVBoxLayout(self.prod_inner); pil.setContentsMargins(0,0,0,0); pil.setSpacing(10)
        self.lbl_prod_block = QLabel()
        self.lbl_prod_block.setWordWrap(True); self.lbl_prod_block.setTextFormat(Qt.RichText)
        self.lbl_prod_block.setOpenExternalLinks(True)
        self.lbl_prod_block.setStyleSheet(f"background:white; border-radius:10px; border:1px solid {t.BUR.border}; padding:14px; font-size:12px; color:{t.BUR.text};")
        pil.addWidget(self.lbl_prod_block)
        self.prod_scroll.setWidget(self.prod_inner)
        self.prod_scroll.setFixedHeight(220)   # ficha producto fija, inputs siempre visibles
        lay.addWidget(self.prod_scroll)

        # Card inputs
        ic  = self._card(); gl = QGridLayout(ic)
        gl.setContentsMargins(16,16,16,16); gl.setSpacing(12)
        self.lbl_pal_sub  = QLabel(""); self.lbl_pal_sub.setStyleSheet(f"color:{t.BUR.accent}; font-size:9px;")
        self.lbl_pres_hdr = QLabel("BULTOS / PRESENT. (L2)")
        self.lbl_pres_hdr.setStyleSheet(f"color:{t.BUR.accent}; font-weight:800; font-size:10px;")
        self.lbl_pres_sub = QLabel(""); self.lbl_pres_sub.setStyleSheet(f"color:{t.BUR.accent}; font-size:9px;")
        self.lbl_base_hdr = QLabel("UNIDADES BASE (L1)")
        self.lbl_base_hdr.setStyleSheet(f"color:{t.BUR.accent}; font-weight:800; font-size:10px;")

        pv = QVBoxLayout(); ph = QLabel("PALLETS (L3)")
        ph.setStyleSheet(f"color:{t.BUR.primary}; font-weight:800; font-size:10px; letter-spacing:1px;")
        pv.addWidget(ph); pv.addWidget(self.lbl_pal_sub)
        prev = QVBoxLayout(); prev.addWidget(self.lbl_pres_hdr); prev.addWidget(self.lbl_pres_sub)
        bv   = QVBoxLayout(); bv.addWidget(self.lbl_base_hdr)

        self.ed_pals = self._big_ed("#1D365C", "Ej: 2")
        self.ed_pres = self._big_ed("#4F5D72", "Ej: 5")
        self.ed_base = self._big_ed("#2BB673", "Ej: 50")
        for e in (self.ed_pals, self.ed_pres, self.ed_base):
            e.textChanged.connect(self._recalc)
        gl.addLayout(pv,  0, 0); gl.addWidget(self.ed_pals, 1, 0)
        gl.addLayout(prev,0, 1); gl.addWidget(self.ed_pres, 1, 1)
        gl.addLayout(bv,  0, 2); gl.addWidget(self.ed_base, 1, 2)
        lay.addWidget(ic)

        # Resultado LDM
        lay.addWidget(self._result_card_sku())
        return page

    def _result_card_sku(self) -> QFrame:
        rc = QFrame(); rc.setObjectName("RC1")
        rc.setStyleSheet(f"QFrame#RC1 {{ background:qlineargradient(x1:0,y1:0,x2:1,y2:1,"
                         f"stop:0 {t.BUR.primary},stop:1 #0a2540); border-radius:12px; }}")
        rl = QVBoxLayout(rc); rl.setContentsMargins(22,16,22,16); rl.setSpacing(4)
        lh = QLabel("LDM ESTIMADOS")
        lh.setStyleSheet("color:rgba(255,255,255,0.55); font-size:10px; font-weight:800; letter-spacing:2px; background:transparent;")
        rl.addWidget(lh)
        self.lbl_ldm = QLabel("—")
        self.lbl_ldm.setStyleSheet(f"color:{t.BUR.secondary}; font-size:46px; font-weight:900; background:transparent;")
        rl.addWidget(self.lbl_ldm)
        dr = QHBoxLayout()
        for attr, hdr_ in [("lbl_qty","UNIDADES"), ("lbl_weight","PESO EST."), ("lbl_pals_out","PALLETS")]:
            vv = QVBoxLayout(); hh = QLabel(hdr_)
            hh.setStyleSheet("color:rgba(255,255,255,0.5); font-size:9px; font-weight:700; background:transparent;")
            lv = QLabel("—"); lv.setStyleSheet("color:rgba(255,255,255,0.92); font-size:15px; font-weight:800; background:transparent;")
            setattr(self, attr, lv); vv.addWidget(hh); vv.addWidget(lv)
            dr.addLayout(vv)
            if attr != "lbl_pals_out": dr.addStretch()
        rl.addLayout(dr)
        self.lbl_sum = QLabel("")
        self.lbl_sum.setWordWrap(True)
        self.lbl_sum.setStyleSheet("color:rgba(255,255,255,0.5); font-size:10px; font-style:italic; background:transparent; margin-top:4px;")
        rl.addWidget(self.lbl_sum)
        return rc

    # ── Tab 2: Por Pedido SO ──────────────────────────────────────────────────
    def _tab_order(self) -> QWidget:
        page = QWidget(); page.setStyleSheet(f"background:{t.BUR.background};")
        lay  = QVBoxLayout(page); lay.setContentsMargins(20,16,20,16); lay.setSpacing(12)

        sc  = self._card(); sl = QVBoxLayout(sc); sl.setContentsMargins(16,14,16,14); sl.setSpacing(8)
        lh2 = QLabel("BUSCAR POR NÚMERO DE PEDIDO ODOO")
        lh2.setStyleSheet(f"color:{t.BUR.primary}; font-weight:800; font-size:10px; letter-spacing:1px;")
        sl.addWidget(lh2)
        row2 = QHBoxLayout()
        self.ed_so = QLineEdit(); self.ed_so.setPlaceholderText("SO49770, SO50001…")
        self.ed_so.setMinimumHeight(36); self.ed_so.setStyleSheet(self._css_input())
        self.ed_so.returnPressed.connect(self._fetch_order)
        self.btn_so = self._btn("Cargar", primary=True)
        self.btn_so.setMinimumHeight(36); self.btn_so.setMinimumWidth(90)
        self.btn_so.clicked.connect(self._fetch_order)
        row2.addWidget(self.ed_so); row2.addWidget(self.btn_so); sl.addLayout(row2)
        self.lbl_so_status = QLabel("Introduce un número de pedido y pulsa Cargar.")
        self.lbl_so_status.setStyleSheet(f"color:{t.BUR.accent}; font-size:11px; font-style:italic;")
        sl.addWidget(self.lbl_so_status)
        lay.addWidget(sc)

        # Tabla
        self.tbl = QTableWidget(0, 8)
        self.tbl.setHorizontalHeaderLabels(
            ["SKU", "Producto", "Cantidad", "Desglose Embalaje", "Pallets", "LDM", "Peso", "Importe"]
        )
        h_ = self.tbl.horizontalHeader()
        h_.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        h_.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)  # Desglose también se estira
        for c in (0, 2, 4, 5, 6, 7):
            h_.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        self.tbl.setAlternatingRowColors(True)
        self.tbl.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tbl.setStyleSheet(f"""
            QTableWidget {{ background:white; border:1px solid {t.BUR.border};
                border-radius:8px; font-size:12px; color:{t.BUR.text}; }}
            QHeaderView::section {{ background:{t.BUR.lvl2}; color:{t.BUR.primary};
                font-weight:800; font-size:10px; border:none; padding:6px; }}
            QTableWidget::item:alternate {{ background:{t.BUR.lvl1}; }}
        """)
        lay.addWidget(self.tbl, 1)
        lay.addWidget(self._result_card_order())
        return page

    def _result_card_order(self) -> QFrame:
        rc = QFrame(); rc.setObjectName("RC2")
        rc.setStyleSheet(f"QFrame#RC2 {{ background:qlineargradient(x1:0,y1:0,x2:1,y2:1,"
                         f"stop:0 {t.BUR.primary},stop:1 #0a2540); border-radius:12px; }}")
        rl = QVBoxLayout(rc); rl.setContentsMargins(22,16,22,16); rl.setSpacing(4)
        self.lbl_so_hdr = QLabel("TOTAL PEDIDO")
        self.lbl_so_hdr.setStyleSheet("color:rgba(255,255,255,0.55); font-size:10px; font-weight:800; letter-spacing:2px; background:transparent;")
        rl.addWidget(self.lbl_so_hdr)
        self.lbl_so_ldm = QLabel("—")
        self.lbl_so_ldm.setStyleSheet(f"color:{t.BUR.secondary}; font-size:46px; font-weight:900; background:transparent;")
        rl.addWidget(self.lbl_so_ldm)
        dr2 = QHBoxLayout()
        for attr, hdr_ in [("lbl_so_weight","PESO EST."), ("lbl_so_pals","PALLETS"), ("lbl_so_lines","LÍNEAS"), ("lbl_so_amount","IMPORTE")]:
            vv = QVBoxLayout(); hh = QLabel(hdr_)
            hh.setStyleSheet("color:rgba(255,255,255,0.5); font-size:9px; font-weight:700; background:transparent;")
            lv = QLabel("—"); lv.setStyleSheet("color:rgba(255,255,255,0.92); font-size:15px; font-weight:800; background:transparent;")
            setattr(self, attr, lv); vv.addWidget(hh); vv.addWidget(lv); dr2.addLayout(vv)
            if attr != "lbl_so_amount": dr2.addStretch()
        rl.addLayout(dr2)
        self.lbl_so_note = QLabel("")
        self.lbl_so_note.setWordWrap(True)
        self.lbl_so_note.setStyleSheet(f"color:{t.BUR.secondary}; font-size:10px; background:transparent; margin-top:4px;")
        rl.addWidget(self.lbl_so_note)
        return rc

    # ─────────────────────────────────────────────────────────────────────────
    # Helpers UI
    # ─────────────────────────────────────────────────────────────────────────
    def _card(self) -> QFrame:
        f = QFrame()
        f.setStyleSheet(f"QFrame {{ background:white; border-radius:10px; border:1px solid {t.BUR.border}; }}")
        f.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        return f

    def _btn(self, text: str, primary=False, outline=False) -> QPushButton:
        b = QPushButton(text); b.setFixedHeight(33); b.setMinimumWidth(80)
        if primary:
            b.setStyleSheet(f"QPushButton {{ background:{t.BUR.primary}; color:white; border-radius:6px; font-weight:800; font-size:12px; border:none; }} QPushButton:hover {{ background:#0d2240; }} QPushButton:disabled {{ background:{t.BUR.border}; color:white; }}")
        elif outline:
            b.setStyleSheet(f"QPushButton {{ border:1px solid {t.BUR.border}; border-radius:6px; background:white; color:{t.BUR.text}; font-weight:600; font-size:11px; }} QPushButton:hover {{ background:{t.BUR.lvl2}; }}")
        return b

    def _css_input(self) -> str:
        return (f"QLineEdit {{ padding:6px 12px; border:2px solid {t.BUR.border}; border-radius:6px;"
                f" font-size:14px; background:white; color:{t.BUR.text}; }}"
                f"QLineEdit:focus {{ border-color:{t.BUR.primary}; }}")

    def _big_ed(self, color: str, placeholder: str = "") -> QLineEdit:
        ed = QLineEdit()
        ed.setPlaceholderText(placeholder or "0")
        v  = QDoubleValidator(0.0, 9_999_999.0, 4)
        v.setNotation(QDoubleValidator.Notation.StandardNotation)
        ed.setValidator(v)
        ed.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ed.setToolTip("Introduce un valor para calcular LDM y pallets")
        ed.setStyleSheet(f"QLineEdit {{ font-size:28px; font-weight:900; padding:10px; color:{color};"
                         f" border:2px solid {t.BUR.border}; border-radius:8px; background:white; }}"
                         f"QLineEdit:focus {{ border-color:{color}; background:#f0f9f4; }}"
                         f"QLineEdit:hover {{ border-color:{color}; }}")
        return ed

    # ─────────────────────────────────────────────────────────────────────────
    # CSV (secundario)
    # ─────────────────────────────────────────────────────────────────────────
    def _load_csv(self):
        self._csv_w = _CsvWorker(self)
        self._csv_w.loaded.connect(self._on_csv)
        self._csv_w.start()

    def _on_csv(self, cat: dict):
        self._csv_catalog = cat
        self._csv_ready   = True
        n = len({v["sku"] for v in cat.values() if v.get("sku")})
        self.lbl_foot.setText(f"📋 CSV Imperbur: {n} productos (enriquecimiento logístico)")
        self.prg.setVisible(False)

    # ─────────────────────────────────────────────────────────────────────────
    # Tab 1: Búsqueda Odoo
    # ─────────────────────────────────────────────────────────────────────────
    def _search_odoo(self):
        q = self.ed_search.text().strip()
        if not q:
            return
        if not self.odoo_service:
            self.lbl_search_status.setText("⚠️ No hay conexión a Odoo configurada.")
            return
        self.btn_search.setEnabled(False)
        self.lbl_search_status.setText(f"🔄 Buscando «{q}» en Odoo…")
        self.lbl_search_status.setStyleSheet(f"color:{t.BUR.STATUS_WAITING}; font-size:11px;")
        self.prod_scroll.setVisible(False)
        self._prod_w = _OdooProductWorker(self.odoo_service, q, self._csv_catalog, self)
        self._prod_w.result.connect(self._on_product)
        self._prod_w.error.connect(self._on_prod_error)
        self._prod_w.finished.connect(lambda: self.btn_search.setEnabled(True))
        self._prod_w.start()

    def _on_product(self, data: dict):
        self._product = data
        self._build_product_block(data)
        self.prod_scroll.setVisible(True)

        sku = data.get("sku", "—")
        self.lbl_search_status.setText(f"✅ {sku} · {data.get('name','')[:40]}")
        self.lbl_search_status.setStyleSheet(f"color:{t.BUR.STATUS_READY}; font-size:11px;")

        # Actualizar labels inputs
        upp    = float(data.get("upp") or 0)
        unit   = data.get("unit_csv") or data.get("uom", "ud")
        pres   = data.get("pres_name", "")
        factor = float(data.get("pres_factor") or 0)
        p_type = data.get("pallet_type", "EUROPA")
        stk    = bool(data.get("is_stackable"))
        ldm_p  = _PALLET_LDM.get(p_type, 0.40)
        if stk: ldm_p /= 2.0
        self.lbl_pal_sub.setText(f"{p_type} · {ldm_p:.2f} LDM/palé")
        if pres and factor > 0:
            self.lbl_pres_hdr.setText(f"{pres.upper()} (L2)")
            self.lbl_pres_sub.setText(f"1 {pres} = {factor:g} {unit}")
        else:
            bundle_qty  = float(data.get("bundle_qty") or 0)
            bundle_name = data.get("bundle_name", "")
            if bundle_qty > 0 and bundle_name:
                self.lbl_pres_hdr.setText(f"{bundle_name.upper()} (L2)")
                self.lbl_pres_sub.setText(f"1 {bundle_name} = {bundle_qty:g} {unit}")
            else:
                self.lbl_pres_hdr.setText("BULTOS / PRESENT. (L2)")
                self.lbl_pres_sub.setText("datos no disponibles")
        self.lbl_base_hdr.setText(f"{unit.upper()} BASE (L1)")
        self._recalc()

    def _on_prod_error(self, msg: str):
        self.lbl_search_status.setText(f"❌ {msg}")
        self.lbl_search_status.setStyleSheet(f"color:{t.BUR.STATUS_ERROR}; font-size:11px;")
        self._product = None
        self.prod_scroll.setVisible(False)

    def _build_product_block(self, d: dict):
        """Construye HTML con toda la ficha del producto."""
        sku        = d.get("sku", "—")
        name       = d.get("name", "—")
        barcode    = d.get("barcode", "")
        pkg_bc     = d.get("pkg_barcode", "")
        uom        = d.get("uom", "")
        categ      = d.get("categ", "")
        tracking   = d.get("tracking", "")
        w_unit     = float(d.get("weight_unit_kg") or 0)
        vol        = float(d.get("volume_m3") or 0)
        peso_pal   = float(d.get("peso_palet") or 0)
        upp        = float(d.get("upp") or 0)
        bundle_qty = float(d.get("bundle_qty") or 0)
        bname      = d.get("bundle_name", "")
        dim_l      = float(d.get("dim_l") or 0)
        dim_w      = float(d.get("dim_w") or 0)
        dim_h      = float(d.get("dim_h") or 0)
        pkg_max_kg = float(d.get("pkg_max_kg") or 0)
        pkg_type_n = d.get("pkg_type_name", "")
        p_type     = d.get("pallet_type", "EUROPA")
        stk        = bool(d.get("is_stackable"))
        list_price = float(d.get("list_price") or 0)
        std_price  = float(d.get("std_price") or 0)
        seller     = d.get("seller_name", ""); seller_price = float(d.get("seller_price") or 0)
        seller_code= d.get("seller_code",""); seller_delay = int(d.get("seller_delay") or 0)
        all_sellers= d.get("all_sellers", [])
        notes      = d.get("notes", "")
        odoo_url   = d.get("odoo_url","")
        pkg_details= d.get("pkg_details", [])
        stock_locs = d.get("stock_by_loc", [])
        reorders   = d.get("reorder_rules", [])
        pending    = d.get("pending_po", [])

        def _m(v): return f"{v:.4f} m ({v*100:.1f} cm)" if v > 0 else "—"
        def _kg(v): return f"{v:,.3f} kg" if v > 0 else "—"
        def _e(v):  return f"{v:,.2f} €" if v > 0 else "—"

        ldm_per = _PALLET_LDM.get(p_type, 0.40)
        if stk: ldm_per /= 2.0
        ldm_exact = _ldm_from_dims(1, dim_l, dim_w, stk)
        ldm_ref   = f"{ldm_exact:.3f} m (exacto dims)" if ldm_exact > 0 else f"{ldm_per:.3f} m (estándar {p_type})"

        # ── Stock HTML
        stock_html = ""
        if stock_locs:
            rows_s = "".join(f"<tr><td>{s['location']}</td><td align='center'>{s['on_hand']:g}</td>"
                             f"<td align='center'>{s['reserved']:g}</td>"
                             f"<td align='center' style='color:#2BB673;font-weight:bold;'>{s['available']:g}</td></tr>"
                             for s in stock_locs)
            stock_html = (f"<div class='sec'>📦 Stock por Ubicación</div>"
                          f"<table><tr><th>Ubicación</th><th>Existencia</th><th>Reservado</th><th>Disponible</th></tr>"
                          f"{rows_s}</table>")
        else:
            stock_html = f"<div class='sec'>📦 Stock</div><p style='color:{t.BUR.accent};'>Sin stock registrado en ubicaciones internas.</p>"

        # ── Reorder
        reorder_html = ""
        if reorders:
            rows_r = "".join(f"<tr><td>{r['warehouse']}</td><td align='center'>{r['min_qty']:g}</td>"
                             f"<td align='center'>{r['max_qty']:g}</td>"
                             f"<td align='center'>{r['on_hand']:g}</td></tr>"
                             for r in reorders)
            reorder_html = (f"<div class='sec'>🔄 Reglas de Reaprovisionamiento</div>"
                            f"<table><tr><th>Almacén</th><th>Mín.</th><th>Máx.</th><th>En Mano</th></tr>"
                            f"{rows_r}</table>")

        # ── Pending POs
        po_html = ""
        if pending:
            rows_p = "".join(f"<tr><td>{p['order']}</td><td>{p['partner']}</td>"
                             f"<td align='center'>{p['qty_pen']:g}</td>"
                             f"<td align='center'>{p['date']}</td>"
                             f"<td align='right'>{_e(p['price'])}</td></tr>"
                             for p in pending)
            po_html = (f"<div class='sec'>🛒 Órdenes de Compra Pendientes</div>"
                       f"<table><tr><th>OC</th><th>Proveedor</th><th>Pendiente</th><th>Fecha Plan.</th><th>Precio Unit.</th></tr>"
                       f"{rows_p}</table>")

        # ── Embalajes
        pkg_html = ""
        if pkg_details:
            rows_k = "".join(
                f"<tr><td><b>{p_['name']}</b></td><td align='center'>{p_['qty']:g}</td>"
                f"<td align='center'>{_m(p_['l_m'])}</td><td align='center'>{_m(p_['w_m'])}</td>"
                f"<td align='center'>{_m(p_['h_m'])}</td>"
                f"<td align='center'>{p_['max_kg']:g} kg</td>"
                f"<td align='center'>{p_['barcode'] or '—'}</td>"
                f"<td>{p_['type']}</td></tr>"
                for p_ in pkg_details
            )
            pkg_html = (f"<div class='sec'>📐 Embalajes (product.packaging)</div>"
                        f"<table><tr><th>Nombre</th><th>Cant.</th><th>Largo</th><th>Ancho</th>"
                        f"<th>Alto</th><th>Peso Máx.</th><th>Cód. Barras</th><th>Tipo</th></tr>"
                        f"{rows_k}</table>")

        # ── Sellers
        sellers_html = ""
        if all_sellers:
            rows_sl = "".join(f"<tr><td>{s['name']}</td><td>{s['code']}</td>"
                              f"<td align='right'>{_e(s['price'])}</td>"
                              f"<td align='center'>{s['min_qty']:g}</td>"
                              f"<td align='center'>{s['delay']} días</td>"
                              f"<td>{s['currency']}</td></tr>"
                              for s in all_sellers)
            sellers_html = (f"<div class='sec'>🏭 Proveedores</div>"
                            f"<table><tr><th>Proveedor</th><th>Ref.</th><th>Precio</th>"
                            f"<th>Cant. Mín.</th><th>Lead Time</th><th>Divisa</th></tr>"
                            f"{rows_sl}</table>")

        open_btn = f"<a href='{odoo_url}' style='color:{t.BUR.primary}; font-weight:700;'>🌐 Abrir en Odoo</a>" if odoo_url else ""

        # ── Diagnóstico automático de campos vacíos + cruce CSV ──────────────
        _odoo_prod_url = odoo_url or ""
        csv_rec = d.get("csv_rec", {})  # CSV maestro crudo para sugerencias

        # Helper: busca valor en CSV y devuelve badge verde o cadena vacía
        def _csv_hint(valor, etiqueta="") -> str:
            if valor:
                tag = etiqueta or str(valor)
                return (f"<span style='background:#e8f5e9;color:#2e7d32;font-weight:bold;"
                        f"padding:1px 5px;border-radius:4px;font-size:10px;'>💾 CSV: {tag}</span>")
            return "<span style='color:#aaa;font-size:10px;'>No en CSV</span>"

        gaps: list = []  # (campo, impacto, donde_en_odoo, csv_badge_html)

        if upp == 0:
            csv_upp = float(csv_rec.get("units_per_pallet") or 0)
            gaps.append(("UPP (Unidades por Palé)",
                         "Sin UPP el cálculo de pallets y LDM es imposible",
                         "Inventario → Inventario → Embalajes",
                         _csv_hint(csv_upp, f"{csv_upp:g} ud/palé" if csv_upp else "")))

        pkg_missing_dims = [p_ for p_ in pkg_details if p_["l_m"] == 0 or p_["w_m"] == 0]
        if pkg_missing_dims:
            names_ = ", ".join(p_["name"] for p_ in pkg_missing_dims)
            csv_pl = float(csv_rec.get("pal_largo_m") or 0)
            csv_pa = float(csv_rec.get("pal_ancho_m") or 0)
            csv_ph = float(csv_rec.get("pal_alto_m") or 0)
            if csv_pl > 0 and csv_pa > 0:
                dim_hint = f"{csv_pl}m × {csv_pa}m × {csv_ph}m (L×A×H palé)"
            else:
                dim_hint = ""
            gaps.append((f"Dimensiones L×W×H: {names_}",
                         "LDM se calcula con valor estándar (menos preciso)",
                         "Inventario → Configuración → Tipos de Paquete",
                         _csv_hint(dim_hint, dim_hint)))


        pkg_missing_kg = [p_ for p_ in pkg_details if p_["max_kg"] == 0]
        if pkg_missing_kg:
            names_ = ", ".join(p_["name"] for p_ in pkg_missing_kg)
            csv_pp = float(csv_rec.get("peso_palet") or 0)
            gaps.append((f"Peso máximo: {names_}",
                         "Necesario para control de sobrepeso en picking",
                         "Inventario → Configuración → Tipos de Paquete",
                         _csv_hint(csv_pp, f"{csv_pp:g} kg (peso palé CSV)" if csv_pp else "")))

        pkg_missing_bc = [p_ for p_ in pkg_details if not p_["barcode"]]
        if pkg_missing_bc:
            names_ = ", ".join(p_["name"] for p_ in pkg_missing_bc)
            gaps.append((f"Cód. barras de embalaje: {names_}",
                         "Necesario para recepción y expedición por escáner",
                         "Producto → Inventario → Embalajes → columna EAN",
                         _csv_hint(False)))  # CSV no tiene EAN de embalaje

        if w_unit == 0:
            gaps.append(("Peso unitario del producto",
                         "Sin peso no se calcula el peso total del envío",
                         "Producto → pestaña Inventario → campo Peso",
                         _csv_hint(False)))

        if std_price == 0:
            gaps.append(("Coste estándar (Standard Price)",
                         "Necesario para valoración de inventario y margen",
                         "Producto → Info General → Precio de Coste",
                         _csv_hint(False)))

        if not all_sellers:
            gaps.append(("Proveedor / Precio de compra",
                         "Sin proveedor no hay lead time ni precio de reposición",
                         "Producto → pestaña Compra → Proveedores",
                         _csv_hint(False)))

        pkg_missing_type = [p_ for p_ in pkg_details if not p_["type"]]
        if pkg_missing_type:
            names_ = ", ".join(p_["name"] for p_ in pkg_missing_type)
            csv_pt = csv_rec.get("pallet_type", "")
            gaps.append((f"Tipo de paquete: {names_}",
                         "El tipo define las dimensiones del contenedor",
                         "Inventario → Configuración → Tipos de Paquete",
                         _csv_hint(csv_pt, f"{csv_pt}" if csv_pt else "")))

        # ── ¿Tiene el CSV datos que Odoo no tiene? (informe adicional) ────────
        csv_extras: list[str] = []
        csv_pt_val  = csv_rec.get("pallet_type", "")
        csv_stk_val = csv_rec.get("is_stackable")
        csv_pp_val  = float(csv_rec.get("peso_palet") or 0)
        csv_pres    = csv_rec.get("presentation", "")
        csv_factor  = float(csv_rec.get("factor") or 0)
        csv_unit    = csv_rec.get("unit", "")
        csv_upp_val = float(csv_rec.get("units_per_pallet") or 0)

        if csv_pt_val:
            csv_extras.append(f"Tipo palé: <b>{csv_pt_val}</b>")
        if csv_stk_val is not None:
            csv_extras.append(f"Apilable: <b>{'Sí' if csv_stk_val else 'No'}</b>")
        if csv_pp_val > 0:
            csv_extras.append(f"Peso palé: <b>{csv_pp_val:g} kg</b>")
        if csv_upp_val > 0 and upp == 0:
            csv_extras.append(f"UPP: <b>{csv_upp_val:g} ud/palé</b>")
        if csv_pres and csv_factor > 0:
            unit_lbl = csv_unit or uom
            csv_extras.append(f"Presentación: <b>1 {csv_pres} = {csv_factor:g} {unit_lbl}</b>")

        csv_banner = ""
        if csv_extras:
            csv_banner = (
                f"<div style='background:#e8f5e9;border:1px solid #2BB673;border-radius:6px;"
                f"padding:6px 12px;margin-bottom:8px;font-size:11px;'>"
                f"<b style='color:#2e7d32;'>💾 Datos disponibles en CSV Maestro</b> "
                f"<span style='color:#555;'>(ya aplicados como fallback)</span><br/>"
                + "  ·  ".join(csv_extras)
                + "</div>"
            )

        if gaps:
            rows_gap = "".join(
                f"<tr>"
                f"<td style='color:#c0392b;font-weight:bold;padding:3px 4px;'>❌ {g[0]}</td>"
                f"<td style='color:#555;font-size:10px;padding:3px 4px;'>{g[1]}</td>"
                f"<td style='color:#777;font-size:10px;padding:3px 4px;font-style:italic;'>📍 {g[2]}</td>"
                f"<td style='padding:3px 4px;'>{g[3]}</td>"
                f"</tr>"
                for g in gaps
            )
            diag_html = (
                f"{csv_banner}"
                f"<div style='background:#fff3f3;border:1px solid #e74c3c;border-radius:6px;"
                f"padding:8px 12px;margin-bottom:8px;'>"
                f"<b style='color:#c0392b;font-size:12px;'>⚠️ {len(gaps)} campo(s) sin completar en Odoo</b>"
                f"<table style='margin-top:5px;border-collapse:collapse;width:100%;'>"
                f"<tr style='background:#fce4e4;'>"
                f"<th style='text-align:left;padding:3px 4px;font-size:10px;'>Campo faltante</th>"
                f"<th style='text-align:left;padding:3px 4px;font-size:10px;'>Impacto</th>"
                f"<th style='text-align:left;padding:3px 4px;font-size:10px;'>Dónde en Odoo</th>"
                f"<th style='text-align:left;padding:3px 4px;font-size:10px;'>¿Está en CSV?</th>"
                f"</tr>"
                f"{rows_gap}"
                f"</table>"
                f"</div>"
            )
        else:
            diag_html = (
                f"{csv_banner}"
                f"<div style='background:#f0fff4;border:1px solid #2BB673;border-radius:6px;"
                f"padding:5px 12px;margin-bottom:8px;'>"
                f"<b style='color:#2BB673;'>✅ Todos los campos logísticos de Odoo están completos</b>"
                f"</div>"
            )


        html = f"""
<style>
  table {{ border-collapse:collapse; width:100%; font-size:11px; }}
  th {{ background:{t.BUR.primary}; color:white; padding:5px 8px; text-align:left; }}
  td {{ padding:4px 8px; border-bottom:1px solid {t.BUR.border}; }}
  tr:nth-child(even) {{ background:{t.BUR.lvl1}; }}
  .sec {{ font-size:10px; font-weight:800; color:{t.BUR.accent}; text-transform:uppercase;
          letter-spacing:0.5px; margin-top:12px; margin-bottom:3px; border-left:3px solid {t.BUR.secondary}; padding-left:6px; }}
  .badge {{ display:inline-block; padding:2px 7px; border-radius:8px; font-size:10px; font-weight:bold; }}
  .ok {{ background:#d4edda; color:#155724; }}
  .warn {{ background:#fff3cd; color:#856404; }}
</style>

<div style="margin-bottom:6px;">
  <span style="font-size:15px;font-weight:800;color:#1D365C;">{name}</span>
  <span class="badge ok" style="margin-left:8px;">Odoo</span>
  {"<span class='badge warn' style='margin-left:4px;'>⚠️ Sin apilable CSV</span>" if not stk else ""}
  &nbsp;&nbsp;{open_btn}
</div>
<div style="color:#4F5D72;font-size:11px;margin-bottom:10px;">
  SKU: <b>{sku}</b> &nbsp;|&nbsp;
  Barcode: <b>{barcode or '—'}</b> &nbsp;|&nbsp;
  UM: <b>{uom}</b> &nbsp;|&nbsp;
  Categoría: <b>{categ or '—'}</b> &nbsp;|&nbsp;
  Trazab.: <b>{tracking}</b>
</div>

{diag_html}

<div class="sec">⚖️ Peso y Dimensiones</div>
<table>
  <tr><th>Campo</th><th>Valor</th></tr>
  <tr><td>Peso unitario (Odoo)</td><td><b>{_kg(w_unit)}</b></td></tr>
  <tr><td>Volumen unitario</td><td>{f"{vol:.6f} m³" if vol > 0 else "—"}</td></tr>
  <tr><td>Peso palé bruto (estimado)</td><td><b>{_kg(peso_pal)}</b></td></tr>
</table>

<div class="sec">📦 Logística de Palé</div>
<table>
  <tr><th>Campo</th><th>Valor</th></tr>
  <tr><td>UPP (unidades/palé)</td><td><b style="color:{t.BUR.primary};font-size:14px;">{f"{upp:g}" if upp > 0 else "—"}</b></td></tr>
  <tr><td>Tipo de palé (CSV)</td><td><b>{p_type}</b></td></tr>
  <tr><td>Apilable (CSV)</td><td>{"✅ Sí" if stk else "❌ No"}</td></tr>
  <tr><td>LDM por palé ({pkg_type_n or "—"})</td><td><b style="color:#2BB673;">{ldm_ref}</b></td></tr>
  <tr><td>Dim. palé principal (L×W×H)</td><td>{_m(dim_l)} × {_m(dim_w)} × {_m(dim_h)}</td></tr>
  <tr><td>Peso máx. embalaje</td><td>{_kg(pkg_max_kg)}</td></tr>
  <tr><td>Bultos/caja (2º embalaje)</td><td>{f"{bundle_qty:g} ud → {bname}" if bundle_qty > 0 else "—"}</td></tr>
  <tr><td>Cód. barras palé</td><td>{pkg_bc or "—"}</td></tr>
</table>

{pkg_html}

<div class="sec">💰 Precios</div>
<table>
  <tr><th>Campo</th><th>Valor</th></tr>
  <tr><td>PVP (Odoo)</td><td><b>{_e(list_price)}</b></td></tr>
  <tr><td>Coste estándar</td><td>{_e(std_price)}</td></tr>
  {"<tr><td>Precio compra</td><td>" + _e(seller_price) + " (" + seller_code + " · " + str(seller_delay) + " días)</td></tr>" if seller else ""}
</table>

{sellers_html}
{stock_html}
{reorder_html}
{po_html}

{"<div class='sec'>📝 Notas</div><div style='color:#4F5D72;font-size:11px;padding:4px 0;'>" + notes + "</div>" if notes else ""}
"""
        self.lbl_prod_block.setText(html)

    # ─────────────────────────────────────────────────────────────────────────
    # Cálculo Tab 1
    # ─────────────────────────────────────────────────────────────────────────
    def _recalc(self):
        if not self._product or self._is_updating:
            return
        try:
            pals  = _safe_float(self.ed_pals.text().replace(",", "."))
            pres_ = _safe_float(self.ed_pres.text().replace(",", "."))
            base  = _safe_float(self.ed_base.text().replace(",", "."))

            d      = self._product
            upp    = float(d.get("upp") or 0)
            # Intentar factor CSV, luego bundle_qty como fallback
            factor = float(d.get("pres_factor") or d.get("bundle_qty") or 0)
            peso_p = float(d.get("peso_palet") or 0)
            w_unit = float(d.get("weight_unit_kg") or 0)
            uom    = d.get("unit_csv") or d.get("uom", "ud")
            p_type = d.get("pallet_type", "EUROPA")
            stk    = bool(d.get("is_stackable"))
            dim_l  = float(d.get("dim_l") or 0)
            dim_w  = float(d.get("dim_w") or 0)

            total  = (pals * upp) + (pres_ * factor) + base
            pf     = (total / upp) if upp > 0 else 0.0
            pc     = math.floor(pf); frac = pf - pc

            if upp > 0 and peso_p > 0:
                tw = pf * peso_p
            else:
                tw = total * w_unit

            ldm = _calc_ldm(pf, dim_l, dim_w, p_type, stk)

            self.lbl_ldm.setText(f"{ldm:,.3f} LDM")
            self.lbl_qty.setText(f"{total:g} {uom.upper()}")
            self.lbl_weight.setText(f"{tw:,.1f} KG")
            self.lbl_pals_out.setText(f"{pc}+{frac:.0%}" if frac > 0.01 else str(pc))

            info = []
            if upp > 0: info.append(f"1 palé = {upp:g} {uom}")
            if factor > 0:
                pn = d.get("pres_name") or d.get("bundle_name") or "bulto"
                info.append(f"1 {pn} = {factor:g} {uom}")
            ldm_p = _PALLET_LDM.get(p_type, 0.40)
            if stk: ldm_p /= 2.0
            exact = _ldm_from_dims(1, dim_l, dim_w, stk)
            method = f"(exacto dims {dim_l:.2f}×{dim_w:.2f} m)" if exact > 0 else f"(estándar {p_type})"
            info.append(f"{ldm_p:.3f} LDM/palé {method}")
            self.lbl_sum.setText("  ·  ".join(info))
        except Exception as e:
            logger.warning(f"[Calc] recalc error: {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # Tab 2: Pedido SO
    # ─────────────────────────────────────────────────────────────────────────
    def _fetch_order(self):
        so = self.ed_so.text().strip()
        if not so: return
        if not self.odoo_service:
            self.lbl_so_status.setText("⚠️ Sin conexión a Odoo.")
            return
        self.btn_so.setEnabled(False)
        self.lbl_so_status.setText(f"🔄 Cargando {so} desde Odoo…")
        self.lbl_so_status.setStyleSheet(f"color:{t.BUR.STATUS_WAITING}; font-size:11px;")
        self.tbl.setRowCount(0)
        self.lbl_so_ldm.setText("…")
        self._ord_w = _OrderWorker(self.odoo_service, so, self._csv_catalog, self)
        self._ord_w.result.connect(self._on_order)
        self._ord_w.error.connect(self._on_order_error)
        self._ord_w.finished.connect(lambda: self.btn_so.setEnabled(True))
        self._ord_w.start()

    def _on_order(self, data: dict):
        lines = data.get("lines", [])
        total_ldm = total_w = total_pals = 0.0
        no_log = []

        self.tbl.setRowCount(0)
        for line in lines:
            qty    = line["qty"]; pals   = line["pals"]
            ldm    = line["ldm"]; weight = line["weight"]
            total_ldm += ldm; total_w += weight; total_pals += pals

            if not line["has_logistic"]:
                no_log.append(line["sku"])

            row = self.tbl.rowCount(); self.tbl.insertRow(row)

            # Columna палlets formateada
            pc_   = math.floor(pals); frac_ = pals - pc_
            pals_txt = f"{pc_}+{frac_:.0%}" if frac_ > 0.01 else (str(pc_) if pals > 0 else "—")
            pals_txt = pals_txt.replace("+0%", "")

            # Desglose de embalaje jerárquico
            breakdown = line.get("breakdown", f"{qty:g} {line['uom']}")
            if not line["has_logistic"]:
                breakdown = f"{qty:g} {line['uom']} ⚠️"

            items = [
                QTableWidgetItem(line["sku"]),                          # 0
                QTableWidgetItem(line["name"]),                         # 1
                QTableWidgetItem(f"{qty:g} {line['uom']}"),             # 2
                QTableWidgetItem(breakdown),                            # 3
                QTableWidgetItem(pals_txt),                             # 4
            ]
            # Col 5: LDM — marcar si es exacto (dims reales) o estimado (estándar)
            ldm_exact_line = line.get("ldm_exact", False)
            ldm_txt = f"{ldm:.3f} ◉" if ldm_exact_line else f"~{ldm:.3f}"
            it_ldm = QTableWidgetItem(ldm_txt)
            it_ldm.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if ldm_exact_line:
                it_ldm.setForeground(QColor("#1a7a3c"))  # verde oscuro = calculado con dims

            items += [
                it_ldm,                                                 # 5 LDM
                QTableWidgetItem(f"{weight:,.0f} kg"),                  # 6
                QTableWidgetItem(f"{line['price']:,.2f} €"),            # 7
            ]
            for c, it in enumerate(items):
                left_cols = {1, 3}  # Producto y Desglose alineados a la izquierda
                if c != 5:  # La celda LDM ya tiene alineación propia
                    it.setTextAlignment(
                        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                        if c in left_cols else Qt.AlignmentFlag.AlignCenter
                    )
                if not line["has_logistic"]:
                    it.setBackground(QColor("#fff8e6"))
                self.tbl.setItem(row, c, it)

        pc = math.floor(total_pals); frac = total_pals - pc
        so_ = data.get("so_name", "")
        self.lbl_so_hdr.setText(f"PEDIDO {so_}  ·  {data.get('partner','')}")
        self.lbl_so_ldm.setText(f"{total_ldm:,.3f} LDM")
        self.lbl_so_weight.setText(f"{total_w:,.0f} KG")
        self.lbl_so_pals.setText(f"{pc}+{frac:.0%}" if frac > 0.01 else str(pc))
        self.lbl_so_lines.setText(str(len(lines)))
        self.lbl_so_amount.setText(f"{data.get('amount',0):,.2f} €")
        if no_log:
            self.lbl_so_note.setText(
                f"⚠️ {len(no_log)} línea(s) sin datos logísticos (amarillo): "
                + ", ".join(no_log[:5]) + ("…" if len(no_log) > 5 else "")
            )
        else:
            self.lbl_so_note.setText("")
        self.lbl_so_status.setText(f"✅ {so_} · {len(lines)} líneas · LDM total: {total_ldm:.3f}")
        self.lbl_so_status.setStyleSheet(f"color:{t.BUR.STATUS_READY}; font-size:11px;")

    def _on_order_error(self, msg: str):
        self.lbl_so_status.setText(f"❌ {msg}")
        self.lbl_so_status.setStyleSheet(f"color:{t.BUR.STATUS_ERROR}; font-size:11px;")
        self.lbl_so_ldm.setText("ERROR")

    # ─────────────────────────────────────────────────────────────────────────
    # Limpiar
    # ─────────────────────────────────────────────────────────────────────────
    def _clear_all(self):
        if self.tabs.currentIndex() == 0:
            self._is_updating = True
            self.ed_pals.setText("0"); self.ed_pres.setText("0"); self.ed_base.setText("0")
            self._is_updating = False
            self._recalc()
            self.ed_search.clear()
            self.prod_scroll.setVisible(False)
            self._product = None
            self.lbl_search_status.setText("Introduce un SKU o nombre y pulsa Buscar.")
            self.lbl_search_status.setStyleSheet(f"color:{t.BUR.accent}; font-size:11px; font-style:italic;")
            self.lbl_ldm.setText("—"); self.lbl_qty.setText("—")
            self.lbl_weight.setText("—"); self.lbl_pals_out.setText("—")
            self.ed_search.setFocus()
        else:
            self.ed_so.clear(); self.tbl.setRowCount(0)
            self.lbl_so_ldm.setText("—"); self.lbl_so_weight.setText("—")
            self.lbl_so_pals.setText("—"); self.lbl_so_lines.setText("—")
            self.lbl_so_amount.setText("—"); self.lbl_so_note.setText("")
            self.lbl_so_hdr.setText("TOTAL PEDIDO")
            self.lbl_so_status.setText("Introduce un número de pedido y pulsa Cargar.")
            self.lbl_so_status.setStyleSheet(f"color:{t.BUR.accent}; font-size:11px; font-style:italic;")
            self.ed_so.setFocus()
