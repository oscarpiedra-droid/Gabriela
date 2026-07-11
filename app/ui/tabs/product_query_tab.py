# ui/tabs/product_query_tab.py
# ──────────────────────────────────────────────────────────────────────────────
# Pestaña: Consulta de Producto
# Permite buscar cualquier producto por SKU o nombre y visualizar toda su
# información logística: peso, dimensiones, UPP, embalajes, precios y
# datos del template en Odoo. También accede directamente a la ficha del
# producto en Odoo vía navegador. Enriquece los datos con el CSV maestro
# de Imperbur (Google Sheets) cuando están disponibles.
# ──────────────────────────────────────────────────────────────────────────────
from __future__ import annotations

import io
import csv
import re
import unicodedata
import urllib.request
import webbrowser
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from loguru import logger


# ──────────────────────────────────────────────────────────────────────────────
# CSV Maestro de Imperbur – URL pública de Google Sheets
# ──────────────────────────────────────────────────────────────────────────────
_CSV_URL = (
    "https://docs.google.com/spreadsheets/d/e/"
    "2PACX-1vTnOqJY2bxOMvHV9Zs0u1q6fX2I3jybjP2pleeEQozKddAHi43BrVx4"
    "H_PqZO7tB4KTbTJVjr5i6K48/pub?gid=487943712&single=true&output=csv"
)

# Índices de columna en el CSV maestro (fila cabecera en índice 2; datos desde índice 3)
_CSV_COL = {
    "sku":          0,
    "name":         1,
    "family":       2,
    "sub_family":   3,
    "unit":        15,
    "presentation":16,
    "factor":      17,
    "width_m":     19,
    "length_m":    20,
    "espesor_mm":  21,
    "pallet_type": 25,
    "upp":         28,
    "depal":       29,
    "peso_palet":  30,
    "pal_ancho":   31,
    "pal_largo":   32,
    "pal_alto":    33,
    "remontable":  34,
    "num_alturas": 35,
}

_PALLET_TYPE_MAP = {
    "pallet 2x1":       "EUROPA",
    "pallet americano": "AMERICANO",
    "gabia":            "OTRO",
    "granel":           "OTRO",
    "media europa":     "MEDIA EUROPA",
}


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────
def _normalize(s: str) -> str:
    s = s.lower().strip()
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return " ".join(s.split())


def _safe_float(val: str) -> float:
    if not val:
        return 0.0
    val = val.strip().replace("\xa0", "").replace("%", "")
    if "," in val and "." not in val:
        val = val.replace(",", ".")
    val = val.replace('"', "").strip()
    try:
        return float(val)
    except ValueError:
        return 0.0


def _parse_pallet_type(raw: str) -> str:
    raw_low = _normalize(raw)
    for key, val in _PALLET_TYPE_MAP.items():
        if key in raw_low:
            return val
    return "OTRO"


def _html_to_text(raw: Any) -> str:
    if not raw or raw is False:
        return ""
    s = re.sub(r"<[^>]+>", " ", str(raw))
    return re.sub(r"\s+", " ", s).strip()[:500]


# ──────────────────────────────────────────────────────────────────────────────
# Worker – Búsqueda multi-fuente (Odoo + CSV)
# ──────────────────────────────────────────────────────────────────────────────
class _ProductQueryWorker(QThread):
    """
    Consulta en paralelo:
      1. Odoo (product.product → template → packaging → suppliers)
      2. CSV maestro de Imperbur (Google Sheets)
    Emite result(dict) con toda la información fusionada, o error(str).
    """

    result = Signal(dict)
    error  = Signal(str)

    def __init__(self, odoo_service, query: str, parent=None):
        super().__init__(parent)
        self.odoo_service = odoo_service
        self.query        = query.strip()

    # ── CSV ───────────────────────────────────────────────────────────────────
    def _fetch_csv_data(self, sku: str, name: str) -> Optional[Dict[str, Any]]:
        try:
            with urllib.request.urlopen(_CSV_URL, timeout=15) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
            reader = csv.reader(io.StringIO(raw))
            rows   = list(reader)

            lookup_sku:  Dict[str, Dict] = {}
            lookup_name: Dict[str, Dict] = {}

            for row in rows[3:]:
                if len(row) <= _CSV_COL["length_m"]:
                    continue
                raw_sku  = row[_CSV_COL["sku"]].strip()
                raw_name = row[_CSV_COL["name"]].strip()
                if not raw_sku and not raw_name:
                    continue

                peso_palet = _safe_float(row[_CSV_COL["peso_palet"]] if len(row) > _CSV_COL["peso_palet"] else "")
                upp_raw    = _safe_float(row[_CSV_COL["upp"]]        if len(row) > _CSV_COL["upp"]        else "")
                peso_unit  = (peso_palet / upp_raw) if (peso_palet > 0 and upp_raw > 0) else 0.0
                espesor_mm = _safe_float(row[_CSV_COL["espesor_mm"]] if len(row) > _CSV_COL["espesor_mm"] else "")
                factor_raw = _safe_float(row[_CSV_COL["factor"]]     if len(row) > _CSV_COL["factor"]     else "")

                parsed: Dict[str, Any] = {
                    "csv_sku":          raw_sku,
                    "csv_name":         raw_name,
                    "family":           row[_CSV_COL["family"]].strip()        if len(row) > _CSV_COL["family"]       else "",
                    "sub_family":       row[_CSV_COL["sub_family"]].strip()    if len(row) > _CSV_COL["sub_family"]   else "",
                    "unit":             row[_CSV_COL["unit"]].strip()          if len(row) > _CSV_COL["unit"]         else "",
                    "presentation":     row[_CSV_COL["presentation"]].strip()  if len(row) > _CSV_COL["presentation"] else "",
                    "factor":           factor_raw,
                    "width_m":          _safe_float(row[_CSV_COL["width_m"]]  if len(row) > _CSV_COL["width_m"]  else ""),
                    "length_m":         _safe_float(row[_CSV_COL["length_m"]] if len(row) > _CSV_COL["length_m"] else ""),
                    "espesor_mm":       espesor_mm,
                    "height_m":         round(espesor_mm / 1000.0, 4) if espesor_mm > 0 else 0.0,
                    "weight_kg":        round(peso_unit, 4),
                    "units_per_pallet": upp_raw,
                    "pallet_type":      _parse_pallet_type(row[_CSV_COL["pallet_type"]] if len(row) > _CSV_COL["pallet_type"] else ""),
                    "is_despaletizable":1 if (row[_CSV_COL["depal"]].strip().lower() == "si" if len(row) > _CSV_COL["depal"] else False) else 0,
                    "is_stackable":     1 if (row[_CSV_COL["remontable"]].strip().lower() == "si" if len(row) > _CSV_COL["remontable"] else False) else 0,
                    "layers_per_pallet":int(_safe_float(row[_CSV_COL["num_alturas"]] if len(row) > _CSV_COL["num_alturas"] else "")),
                    "pallet_width_m":   _safe_float(row[_CSV_COL["pal_ancho"]] if len(row) > _CSV_COL["pal_ancho"] else ""),
                    "pallet_length_m":  _safe_float(row[_CSV_COL["pal_largo"]] if len(row) > _CSV_COL["pal_largo"] else ""),
                    "pallet_height_m":  _safe_float(row[_CSV_COL["pal_alto"]]  if len(row) > _CSV_COL["pal_alto"]  else ""),
                    "peso_palet_total": peso_palet,
                }
                if raw_sku:
                    lookup_sku[_normalize(raw_sku)]   = parsed
                if raw_name:
                    lookup_name[_normalize(raw_name)] = parsed

            q = _normalize(self.query)
            return lookup_sku.get(q) or lookup_name.get(q)

        except Exception as exc:
            logger.warning(f"[ProductQueryTab] CSV fetch error: {exc}")
            return None

    # ── Odoo ──────────────────────────────────────────────────────────────────
    def _fetch_odoo_data(self) -> Optional[Dict[str, Any]]:
        svc = self.odoo_service
        if not svc:
            return None

        PP_FIELDS = [
            "id", "default_code", "name", "barcode",
            "weight", "volume",
            "packaging_ids", "product_tmpl_id", "uom_id",
            "list_price", "standard_price",
            "description", "description_picking",
            "description_pickingin", "description_pickingout",
            "categ_id", "active",
        ]
        PKG_FIELDS  = ["name", "qty", "barcode", "package_type_id"]
        PT_FIELDS   = ["name", "default_code", "weight", "volume", "packaging_ids",
                       "seller_ids", "description", "description_sale", "description_purchase",
                       "categ_id", "image_1920", "tracking"]
        SELLER_FIELDS = ["partner_id", "product_code", "product_name", "price", "min_qty", "delay", "currency_id", "sequence"]

        def _safe_exec(model, method, *args, **kwargs):
            """Ejecuta una llamada Odoo usando odoorpc directamente (sin svc.execute)."""
            try:
                with svc._lock:
                    svc._ensure_connected()
                    env_model = svc.odoo.env[model]
                    fn = getattr(env_model, method)
                    return fn(*args, **kwargs)
            except Exception as exc:
                logger.warning(f"[ProductQueryTab] Odoo {model}.{method} error: {exc}")
                return [] if method in ("search", "search_read") else None

        q = self.query
        # Buscar por SKU exacto primero, luego ilike, luego por nombre
        pp_ids = _safe_exec("product.product", "search", [["default_code", "=", q]], limit=5)
        if not pp_ids:
            pp_ids = _safe_exec("product.product", "search", [["default_code", "ilike", q]], limit=5)
        if not pp_ids:
            pp_ids = _safe_exec("product.product", "search", [["name", "ilike", q]], limit=5)
        if not pp_ids:
            return None

        pp_rows = _safe_exec("product.product", "read", list(pp_ids), PP_FIELDS)
        if not pp_rows:
            return None

        odoo_pp = pp_rows[0]  # tomar la primera coincidencia
        product_id = odoo_pp.get("id")

        weight      = float(odoo_pp.get("weight") or 0.0)
        volume      = float(odoo_pp.get("volume") or 0.0)
        list_price  = float(odoo_pp.get("list_price") or 0.0)
        std_price   = float(odoo_pp.get("standard_price") or 0.0)
        barcode_raw = odoo_pp.get("barcode")
        barcode     = "" if not barcode_raw or barcode_raw is False else str(barcode_raw)

        desc_parts: List[str] = []
        for k in ("description", "description_picking", "description_pickingin", "description_pickingout"):
            txt = _html_to_text(odoo_pp.get(k))
            if txt:
                desc_parts.append(txt)
        notes = " | ".join(dict.fromkeys(desc_parts))

        # Embalajes
        pkg_ids = [int(x) for x in (odoo_pp.get("packaging_ids") or []) if x]
        pkg_rows = _safe_exec("product.packaging", "read", pkg_ids, PKG_FIELDS) if pkg_ids else []
        if not isinstance(pkg_rows, list):
            pkg_rows = []

        def _enrich_pkg_dims(rows: List[Dict]) -> List[Dict]:
            """Rellena dimensiones desde stock.package.type (length, width, height, max_weight)."""
            if not rows:
                return rows
            type_ids = list({int(r["package_type_id"][0]) for r in rows
                             if r.get("package_type_id") and r["package_type_id"]})
            if not type_ids:
                return rows
            PT_DIM_FIELDS = ["id", "name", "packaging_length", "width", "height", "max_weight"]
            type_rows = _safe_exec("stock.package.type", "read", type_ids, PT_DIM_FIELDS)
            type_map: Dict[int, Dict] = {}
            if isinstance(type_rows, list):
                for t in type_rows:
                    type_map[t["id"]] = t
            for r in rows:
                pt_ref = r.get("package_type_id")
                if pt_ref:
                    tid = int(pt_ref[0])
                    td  = type_map.get(tid, {})
                    r["dim_l"]     = float(td.get("packaging_length") or 0.0)
                    r["dim_w"]     = float(td.get("width")            or 0.0)
                    r["dim_h"]     = float(td.get("height")           or 0.0)
                    r["max_weight"]= float(td.get("max_weight")       or 0.0)
                else:
                    r["dim_l"] = r["dim_w"] = r["dim_h"] = r["max_weight"] = 0.0
            return rows

        pkg_rows = _enrich_pkg_dims(pkg_rows)

        # Template
        tmpl_ref = odoo_pp.get("product_tmpl_id")
        tmpl_id  = int(tmpl_ref[0]) if isinstance(tmpl_ref, (list, tuple)) else (int(tmpl_ref) if tmpl_ref else None)
        seller_info:      Dict[str, Any] = {}
        tmpl_data:        Dict[str, Any] = {}
        all_sellers_data: List[Dict]     = []
        stock_by_loc:     List[Dict]     = []
        reorder_rules:    List[Dict]     = []
        pending_po:       List[Dict]     = []
        tracking_label:   str            = "⭕ Sin seguimiento"

        if tmpl_id:
            tmpl_rows = _safe_exec("product.template", "read", [tmpl_id], PT_FIELDS)
            if tmpl_rows and isinstance(tmpl_rows, list):
                tmpl_data = tmpl_rows[0]
                if not pkg_rows:
                    tmpl_pkg_ids = [int(x) for x in (tmpl_data.get("packaging_ids") or []) if x]
                    pkg_rows     = _safe_exec("product.packaging", "read", tmpl_pkg_ids, PKG_FIELDS) if tmpl_pkg_ids else []
                    if not isinstance(pkg_rows, list):
                        pkg_rows = []
                    pkg_rows = _enrich_pkg_dims(pkg_rows)
                if weight == 0:
                    weight = float(tmpl_data.get("weight") or 0.0)
                if volume == 0:
                    volume = float(tmpl_data.get("volume") or 0.0)
                for k in ("description", "description_sale", "description_purchase"):
                    txt = _html_to_text(tmpl_data.get(k))
                    if txt and txt not in notes:
                        notes = f"{notes} | {txt}".strip(" |")

                seller_ids_raw = [int(x) for x in (tmpl_data.get("seller_ids") or []) if x]
                if seller_ids_raw:
                    s_rows = _safe_exec("product.supplierinfo", "read", seller_ids_raw[:8], SELLER_FIELDS)
                    if s_rows and isinstance(s_rows, list):
                        s_rows_sorted = sorted(s_rows, key=lambda x: int(x.get("sequence") or 0))
                        seller_info = s_rows_sorted[0]
                        for s in s_rows_sorted:
                            p_r = s.get("partner_id")
                            c_r = s.get("currency_id")
                            all_sellers_data.append({
                                "name":    p_r[1] if isinstance(p_r, (list, tuple)) and len(p_r) > 1 else str(p_r or ""),
                                "code":    str(s.get("product_code") or ""),
                                "price":   float(s.get("price") or 0.0),
                                "min_qty": float(s.get("min_qty") or 0.0),
                                "delay":   int(s.get("delay") or 0),
                                "currency":c_r[1] if isinstance(c_r, (list, tuple)) and len(c_r) > 1 else "EUR",
                            })
                # Tipo de seguimiento
                t_raw = str(tmpl_data.get("tracking") or "none")
                tracking_label = {"serial": "🔢 Por Nº Serie", "lot": "📦 Por Lote", "none": "⭕ Sin seguimiento"}.get(t_raw, "⭕ Sin seguimiento")

        # ── Stock en tiempo real ─────────────────────────────────────────────────────
        q_rows = _safe_exec(
            "stock.quant", "search_read",
            [["product_id", "=", product_id], ["location_id.usage", "=", "internal"]],
            fields=["location_id", "quantity", "reserved_quantity"], limit=30,
        )
        if isinstance(q_rows, list):
            for q in q_rows:
                loc_r    = q.get("location_id")
                loc_name = loc_r[1] if isinstance(loc_r, (list, tuple)) and len(loc_r) > 1 else str(loc_r or "")
                on_hand  = float(q.get("quantity") or 0.0)
                reserved = float(q.get("reserved_quantity") or 0.0)
                if on_hand != 0.0 or reserved != 0.0:
                    stock_by_loc.append({"location": loc_name, "on_hand": on_hand,
                                         "reserved": reserved, "available": on_hand - reserved})

        # ── Reglas de reaprovisionamiento ───────────────────────────────────────
        op_rows = _safe_exec(
            "stock.warehouse.orderpoint", "search_read",
            [["product_id", "=", product_id]],
            fields=["product_min_qty", "product_max_qty", "qty_on_hand", "warehouse_id"], limit=5,
        )
        if isinstance(op_rows, list):
            for op in op_rows:
                wh_r = op.get("warehouse_id")
                reorder_rules.append({
                    "warehouse": wh_r[1] if isinstance(wh_r, (list, tuple)) and len(wh_r) > 1 else str(wh_r or ""),
                    "min_qty":   float(op.get("product_min_qty") or 0.0),
                    "max_qty":   float(op.get("product_max_qty") or 0.0),
                    "qty_on_hand":float(op.get("qty_on_hand") or 0.0),
                })

        # ── Órdenes de compra pendientes ────────────────────────────────────────────
        pl_rows = _safe_exec(
            "purchase.order.line", "search_read",
            [["product_id", "=", product_id], ["state", "in", ["purchase", "sent"]]],
            fields=["product_qty", "qty_received", "date_planned", "order_id", "partner_id", "price_unit"],
            limit=10, order="date_planned asc",
        )
        if isinstance(pl_rows, list):
            for pl in pl_rows:
                qty_ord = float(pl.get("product_qty") or 0.0)
                qty_rec = float(pl.get("qty_received") or 0.0)
                qty_pen = round(qty_ord - qty_rec, 4)
                if qty_pen <= 0:
                    continue
                o_r = pl.get("order_id")
                p_r = pl.get("partner_id")
                pending_po.append({
                    "order":    o_r[1] if isinstance(o_r, (list, tuple)) and len(o_r) > 1 else str(o_r or ""),
                    "partner":  p_r[1] if isinstance(p_r, (list, tuple)) and len(p_r) > 1 else str(p_r or ""),
                    "qty_pen":  qty_pen,
                    "qty_rec":  qty_rec,
                    "date":     str(pl.get("date_planned") or "")[:10],
                    "price":    float(pl.get("price_unit") or 0.0),
                })

        # Analizar embalajes
        upp = bundle_qty = bundle_name = 0.0
        pkg_barcode = pkg_dim_l = pkg_dim_w = pkg_dim_h = pkg_max_kg = 0.0
        pkg_details: List[Dict] = []
        if pkg_rows:
            pkg_sorted = sorted(pkg_rows, key=lambda r: float(r.get("qty") or 0), reverse=True)
            biggest       = pkg_sorted[0]
            upp           = float(biggest.get("qty") or 0.0)
            bc_raw        = biggest.get("barcode")
            pkg_barcode   = "" if not bc_raw or bc_raw is False else str(bc_raw)
            pkg_dim_l     = float(biggest.get("dim_l") or 0.0)
            pkg_dim_w     = float(biggest.get("dim_w") or 0.0)
            pkg_dim_h     = float(biggest.get("dim_h") or 0.0)
            pkg_max_kg    = float(biggest.get("max_weight") or 0.0)
            if len(pkg_sorted) > 1:
                second      = pkg_sorted[1]
                bundle_qty  = float(second.get("qty") or 0.0)
                bundle_name = str(second.get("name") or "Caja")
            for p in pkg_sorted:
                pkg_details.append({
                    "name": str(p.get("name") or ""),
                    "qty":  float(p.get("qty") or 0.0),
                    "barcode": "" if not p.get("barcode") or p.get("barcode") is False else str(p.get("barcode")),
                    "h": float(p.get("dim_h") or 0.0),
                    "l": float(p.get("dim_l") or 0.0),
                    "w": float(p.get("dim_w") or 0.0),
                    "max_kg": float(p.get("max_weight") or 0.0),
                })

        # Dimensiones del embalaje (convertir de mm a m si > 10)
        factor = 0.001 if pkg_dim_l > 10 else 1.0
        dim_l = round(pkg_dim_l * factor, 4) if pkg_dim_l > 0 else 0.0
        dim_w = round(pkg_dim_w * factor, 4) if pkg_dim_w > 0 else 0.0
        dim_h = round(pkg_dim_h * factor, 4) if pkg_dim_h > 0 else 0.0

        # URL de la ficha en Odoo
        base_url = (svc.url or "").rstrip("/")
        odoo_url_tmpl    = f"{base_url}/odoo/inventory/products/{tmpl_id}"    if tmpl_id else ""
        odoo_url_variant = f"{base_url}/web#id={product_id}&model=product.product&view_type=form" if product_id else ""

        uom_raw  = odoo_pp.get("uom_id")
        uom_name = uom_raw[1] if isinstance(uom_raw, (list, tuple)) and len(uom_raw) > 1 else str(uom_raw or "")

        categ_raw  = odoo_pp.get("categ_id")
        categ_name = categ_raw[1] if isinstance(categ_raw, (list, tuple)) and len(categ_raw) > 1 else str(categ_raw or "")

        seller_name  = ""
        seller_code  = ""
        seller_price = 0.0
        seller_delay = 0
        if seller_info:
            partner = seller_info.get("partner_id")
            seller_name  = partner[1] if isinstance(partner, (list, tuple)) and len(partner) > 1 else str(partner or "")
            seller_code  = str(seller_info.get("product_code") or "")
            seller_price = float(seller_info.get("price") or 0.0)
            seller_delay = int(seller_info.get("delay") or 0)

        return {
            "product_id":    product_id,
            "tmpl_id":       tmpl_id,
            "sku":           str(odoo_pp.get("default_code") or ""),
            "name":          str(odoo_pp.get("name") or ""),
            "barcode":       barcode,
            "pkg_barcode":   pkg_barcode,
            "uom":           uom_name,
            "categ":         categ_name,
            "weight_kg":     weight,
            "volume_m3":     volume,
            "list_price":    list_price,
            "std_price":     std_price,
            "notes":         notes,
            "upp":           upp,
            "bundle_qty":    bundle_qty,
            "bundle_name":   bundle_name,
            "pkg_dim_l":     dim_l,
            "pkg_dim_w":     dim_w,
            "pkg_dim_h":     dim_h,
            "pkg_max_kg":    pkg_max_kg,
            "pkg_details":   pkg_details,
            "seller_name":   seller_name,
            "seller_code":   seller_code,
            "seller_price":  seller_price,
            "seller_delay":  seller_delay,
            "odoo_url_tmpl":    odoo_url_tmpl,
            "odoo_url_variant": odoo_url_variant,
            "tracking_label":   tracking_label,
            "all_sellers":      all_sellers_data,
            "stock_by_loc":     stock_by_loc,
            "reorder_rules":    reorder_rules,
            "pending_po":       pending_po,
        }

    # ── run ───────────────────────────────────────────────────────────────────
    def run(self):
        try:
            logger.info(f"[ProductQueryTab] Buscando: '{self.query}'")
            odoo_data = self._fetch_odoo_data()
            csv_data  = self._fetch_csv_data(
                sku  = odoo_data.get("sku", self.query) if odoo_data else self.query,
                name = odoo_data.get("name", "")        if odoo_data else "",
            )

            # Fusionar: Odoo es fuente primaria; CSV complementa
            merged: Dict[str, Any] = {}
            merged["odoo"]    = odoo_data or {}
            merged["csv"]     = csv_data  or {}
            merged["found"]   = bool(odoo_data or csv_data)
            merged["query"]   = self.query
            self.result.emit(merged)
        except Exception as exc:
            logger.error(f"[ProductQueryTab] Worker error: {exc}")
            self.error.emit(str(exc))


# ──────────────────────────────────────────────────────────────────────────────
# Pestaña principal
# ──────────────────────────────────────────────────────────────────────────────
class ProductQueryTab(QWidget):
    """
    Pestaña 'Consulta de Producto' dentro del módulo Stock y Artículos.
    Busca por SKU o nombre y muestra información logística completa desde
    Odoo y el CSV maestro de Imperbur.
    """

    def __init__(self, odoo_service, parent=None):
        super().__init__(parent)
        self.odoo_service = odoo_service
        self._worker: Optional[_ProductQueryWorker] = None
        self._last_odoo_url_tmpl    = ""
        self._last_odoo_url_variant = ""
        self._build_ui()

    # ── UI ────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        # ── Cabecera ──────────────────────────────────────────────────────────
        title = QLabel("🔍 Consulta de Producto")
        font  = QFont()
        font.setPointSize(15)
        font.setBold(True)
        title.setFont(font)

        sub = QLabel("Busca cualquier producto por SKU o nombre. Los datos se obtienen de Odoo y del CSV maestro de Imperbur.")
        sub.setStyleSheet("color: #6c757d; font-size: 11px;")
        sub.setWordWrap(True)

        # ── Barra de búsqueda ─────────────────────────────────────────────────
        search_row = QHBoxLayout()
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("SKU, referencia interna o nombre del producto…")
        self._search_input.setMinimumHeight(34)
        self._search_input.returnPressed.connect(self._do_search)

        self._btn_search = QPushButton("🔍 Buscar")
        self._btn_search.setMinimumHeight(34)
        self._btn_search.setMinimumWidth(110)
        self._btn_search.clicked.connect(self._do_search)
        self._btn_search.setStyleSheet("QPushButton { background-color: #0d6efd; color: white; border-radius:6px; font-weight: bold; }"
                                       "QPushButton:hover { background-color: #0b5ed7; }"
                                       "QPushButton:disabled { background-color: #adb5bd; }")

        search_row.addWidget(self._search_input)
        search_row.addWidget(self._btn_search)

        # ── Acciones Odoo ─────────────────────────────────────────────────────
        action_row = QHBoxLayout()
        self._btn_open_odoo = QPushButton("🌐 Abrir Ficha en Odoo")
        self._btn_open_odoo.setEnabled(False)
        self._btn_open_odoo.setMinimumHeight(30)
        self._btn_open_odoo.clicked.connect(self._open_odoo_url)
        self._btn_open_odoo.setStyleSheet("QPushButton { background-color: #198754; color: white; border-radius:5px; }"
                                          "QPushButton:hover { background-color: #157347; }"
                                          "QPushButton:disabled { background-color: #adb5bd; color: #fff; }")

        self._btn_open_variant = QPushButton("🔗 Abrir Variante en Odoo")
        self._btn_open_variant.setEnabled(False)
        self._btn_open_variant.setMinimumHeight(30)
        self._btn_open_variant.clicked.connect(lambda: webbrowser.open(self._last_odoo_url_variant))
        self._btn_open_variant.setStyleSheet("QPushButton { background-color: #6f42c1; color: white; border-radius:5px; }"
                                             "QPushButton:hover { background-color: #59359a; }"
                                             "QPushButton:disabled { background-color: #adb5bd; }")

        self._status_lbl = QLabel("Ingrese un SKU o nombre y pulse Buscar.")
        self._status_lbl.setStyleSheet("color: #6c757d; font-style: italic;")

        action_row.addWidget(self._btn_open_odoo)
        action_row.addWidget(self._btn_open_variant)
        action_row.addStretch()
        action_row.addWidget(self._status_lbl)

        # ── Separador ─────────────────────────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #dee2e6;")

        # ── Panel de resultados (Splitter) ────────────────────────────────────
        splitter = QSplitter(Qt.Horizontal)

        # Panel izquierdo: Ficha logística
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setMinimumWidth(400)
        self._detail_widget = QLabel("Sin datos. Realice una búsqueda.")
        self._detail_widget.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self._detail_widget.setWordWrap(True)
        self._detail_widget.setContentsMargins(10, 10, 10, 10)
        self._detail_widget.setTextFormat(Qt.RichText)
        self._detail_widget.setOpenExternalLinks(True)
        left_scroll.setWidget(self._detail_widget)

        # Panel derecho: Embalajes / tabla
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        pkg_label = QLabel("📦 Embalajes del Producto")
        pkg_label.setStyleSheet("font-weight: bold; font-size: 12px; color: #495057;")

        self._pkg_table = QTableWidget(0, 9)
        self._pkg_table.setHorizontalHeaderLabels([
            "Nombre", "Cantidad", "Código Barras",
            "L (m)", "An (m)", "Alt (m)",
            "Peso Unit. (kg)", "Peso Palet (kg)", "Peso Máx. (kg)",
        ])
        self._pkg_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self._pkg_table.horizontalHeader().setStretchLastSection(True)
        self._pkg_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._pkg_table.setAlternatingRowColors(True)
        self._pkg_table.setMaximumHeight(220)

        csv_label = QLabel("📋 Datos del CSV Maestro Imperbur")
        csv_label.setStyleSheet("font-weight: bold; font-size: 12px; color: #495057; margin-top: 8px;")

        csv_sep = QFrame()
        csv_sep.setFrameShape(QFrame.HLine)
        csv_sep.setStyleSheet("color: #dee2e6;")

        self._csv_detail = QLabel("Datos CSV no disponibles.")
        self._csv_detail.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self._csv_detail.setWordWrap(True)
        self._csv_detail.setTextFormat(Qt.RichText)
        self._csv_detail.setContentsMargins(6, 6, 6, 6)
        self._csv_detail.setStyleSheet("background-color: #f8f9fa; border: 1px solid #dee2e6; border-radius:4px;")

        right_layout.addWidget(pkg_label)
        right_layout.addWidget(self._pkg_table)
        right_layout.addWidget(csv_label)
        right_layout.addWidget(csv_sep)
        right_layout.addWidget(self._csv_detail)
        right_layout.addStretch()

        splitter.addWidget(left_scroll)
        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        # ── Montaje ───────────────────────────────────────────────────────────
        root.addWidget(title)
        root.addWidget(sub)
        root.addLayout(search_row)
        root.addLayout(action_row)
        root.addWidget(sep)
        root.addWidget(splitter, 1)

    # ── Lógica de búsqueda ────────────────────────────────────────────────────
    def _do_search(self):
        query = self._search_input.text().strip()
        if not query:
            QMessageBox.information(self, "Búsqueda vacía", "Introduzca un SKU o nombre de producto.")
            return

        self._btn_search.setEnabled(False)
        self._btn_open_odoo.setEnabled(False)
        self._btn_open_variant.setEnabled(False)
        self._status_lbl.setText(f"🔄 Buscando «{query}»…")
        self._status_lbl.setStyleSheet("color: #fd7e14; font-style: italic;")
        self._detail_widget.setText("<i>Consultando Odoo y CSV maestro…</i>")
        self._csv_detail.setText("<i>Consultando CSV maestro de Imperbur…</i>")
        self._pkg_table.setRowCount(0)
        QApplication.processEvents()

        self._worker = _ProductQueryWorker(self.odoo_service, query)
        self._worker.result.connect(self._on_result)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_result(self, data: Dict[str, Any]):
        self._btn_search.setEnabled(True)

        if not data.get("found"):
            self._status_lbl.setText(f"⚠️ No se encontró «{data.get('query')}» en Odoo ni en el CSV.")
            self._status_lbl.setStyleSheet("color: #dc3545; font-style: italic;")
            self._detail_widget.setText(
                f"<b>Sin resultados</b><br>"
                f"No se encontró ningún producto para <i>{data.get('query')}</i>.<br><br>"
                f"Verifique el SKU o nombre e intente de nuevo."
            )
            return

        odoo = data.get("odoo", {})
        csv  = data.get("csv",  {})

        # URLs de Odoo
        self._last_odoo_url_tmpl    = odoo.get("odoo_url_tmpl", "")
        self._last_odoo_url_variant = odoo.get("odoo_url_variant", "")
        if self._last_odoo_url_tmpl:
            self._btn_open_odoo.setEnabled(True)
        if self._last_odoo_url_variant:
            self._btn_open_variant.setEnabled(True)

        # Obtener valores clave (Odoo primario, CSV como fallback)
        sku    = odoo.get("sku") or csv.get("csv_sku", "—")
        name   = odoo.get("name") or csv.get("csv_name", "—")
        weight = odoo.get("weight_kg") or csv.get("weight_kg", 0.0)
        upp    = odoo.get("upp") or csv.get("units_per_pallet", 0.0)
        dim_l  = odoo.get("pkg_dim_l")  or csv.get("length_m", 0.0)
        dim_w  = odoo.get("pkg_dim_w")  or csv.get("width_m", 0.0)
        dim_h  = odoo.get("pkg_dim_h")  or csv.get("height_m", 0.0)
        is_stk = "✅ Sí" if csv.get("is_stackable") else ("—" if not csv else "❌ No")
        is_dep = "✅ Sí" if csv.get("is_despaletizable") else ("—" if not csv else "❌ No")

        def _fmt_m(v) -> str:
            f = float(v or 0)
            return f"{f:.4f} m ({f*100:.1f} cm)" if f > 0 else "—"

        def _fmt_kg(v) -> str:
            f = float(v or 0)
            return f"{f:.3f} kg" if f > 0 else "—"

        def _fmt_qty(v) -> str:
            f = float(v or 0)
            return f"{f:g}" if f > 0 else "—"

        source_tag = "🟢 Odoo + CSV" if (odoo and csv) else ("🔵 Odoo" if odoo else "🟡 CSV Imperbur")

        # Construir HTML de ficha logística
        html = f"""
        <style>
            table {{ border-collapse: collapse; width: 100%; font-size: 12px; }}
            th {{ background: #343a40; color: white; padding: 6px 10px; text-align: left; }}
            td {{ padding: 5px 10px; border-bottom: 1px solid #dee2e6; }}
            tr:nth-child(even) {{ background: #f8f9fa; }}
            .section {{ font-size: 11px; font-weight: bold; color: #6c757d;
                        text-transform: uppercase; letter-spacing: 0.5px;
                        margin-top: 14px; margin-bottom: 4px; }}
            .value-hi {{ color: #0d6efd; font-weight: bold; }}
            .badge {{ display: inline-block; padding: 2px 8px; border-radius: 10px;
                      font-size: 10px; font-weight: bold; }}
            .badge-ok {{ background:#d1e7dd; color:#0f5132; }}
            .badge-warn {{ background:#fff3cd; color:#664d03; }}
        </style>

        <div style="margin-bottom:8px;">
            <span style="font-size:15px; font-weight:bold;">{name}</span>
            <span class="badge badge-ok" style="margin-left:8px;">{source_tag}</span>
        </div>
        <div style="color:#6c757d; font-size:11px; margin-bottom:10px;">
            SKU: <b>{sku}</b> &nbsp;|&nbsp;
            Cód. Barras: <b>{odoo.get('barcode') or '—'}</b> &nbsp;|&nbsp;
            UM: <b>{odoo.get('uom') or '—'}</b> &nbsp;|&nbsp;
            Categoría: <b>{odoo.get('categ') or csv.get('family') or '—'}</b>
        </div>

        <div class="section">📐 Dimensiones y Peso</div>
        <table>
            <tr><th>Campo</th><th>Valor</th><th>Fuente</th></tr>
            <tr><td>Peso unitario</td>
                <td class="value-hi">{_fmt_kg(weight)}</td>
                <td>{'Odoo' if odoo.get('weight_kg') else 'CSV'}</td></tr>
            <tr><td>Volumen</td>
                <td>{f"{float(odoo.get('volume_m3') or 0):.6f} m³" if odoo.get('volume_m3') else '—'}</td>
                <td>Odoo</td></tr>
            <tr><td>Largo</td>
                <td class="value-hi">{_fmt_m(dim_l)}</td>
                <td>{'Odoo' if odoo.get('pkg_dim_l') else 'CSV'}</td></tr>
            <tr><td>Ancho</td>
                <td class="value-hi">{_fmt_m(dim_w)}</td>
                <td>{'Odoo' if odoo.get('pkg_dim_w') else 'CSV'}</td></tr>
            <tr><td>Alto</td>
                <td class="value-hi">{_fmt_m(dim_h)}</td>
                <td>{'Odoo' if odoo.get('pkg_dim_h') else 'CSV'}</td></tr>
        </table>

        <div class="section">📦 Datos de Palet / UPP</div>
        <table>
            <tr><th>Campo</th><th>Valor</th></tr>
            <tr><td>Unidades por Palet (UPP)</td>
                <td class="value-hi">{_fmt_qty(upp)}</td></tr>
            <tr><td>Tipo de Palet</td>
                <td>{csv.get('pallet_type') or '—'}</td></tr>
            <tr><td>Alturas por Palet (capas)</td>
                <td>{csv.get('layers_per_pallet') or '—'}</td></tr>
            <tr><td>Peso Palet Completo</td>
                <td>{_fmt_kg(csv.get('peso_palet_total', 0))}</td></tr>
            <tr><td>Ancho Palet</td><td>{_fmt_m(csv.get('pallet_width_m', 0))}</td></tr>
            <tr><td>Largo Palet</td><td>{_fmt_m(csv.get('pallet_length_m', 0))}</td></tr>
            <tr><td>Alto Palet</td><td>{_fmt_m(csv.get('pallet_height_m', 0))}</td></tr>
            <tr><td>Remontable (apilable)</td><td>{is_stk}</td></tr>
            <tr><td>Despaletizable</td><td>{is_dep}</td></tr>
        </table>

        <div class="section">💰 Precios y Proveedor</div>
        <table>
            <tr><th>Campo</th><th>Valor</th></tr>
            <tr><td>Precio de Venta</td>
                <td class="value-hi">{f"{float(odoo.get('list_price') or 0):,.2f} €" if odoo.get('list_price') else '—'}</td></tr>
            <tr><td>Coste Estándar</td>
                <td>{f"{float(odoo.get('std_price') or 0):,.2f} €" if odoo.get('std_price') else '—'}</td></tr>
            <tr><td>Proveedor Principal</td>
                <td>{odoo.get('seller_name') or '—'}</td></tr>
            <tr><td>Ref. Proveedor</td>
                <td>{odoo.get('seller_code') or '—'}</td></tr>
            <tr><td>Precio Compra</td>
                <td>{f"{float(odoo.get('seller_price') or 0):,.2f} €" if odoo.get('seller_price') else '—'}</td></tr>
            <tr><td>Lead Time (días)</td>
                <td>{odoo.get('seller_delay') or '—'}</td></tr>
        </table>

        <div class="section">📦 Bundle / Caja intermedia (Odoo)</div>
        <table>
            <tr><td>Cantidad por Bulto</td>
                <td>{_fmt_qty(odoo.get('bundle_qty', 0))}</td></tr>
            <tr><td>Nombre Bulto</td>
                <td>{odoo.get('bundle_name') or '—'}</td></tr>
        </table>

        <div class="section">🏷️ Trazabilidad</div>
        <table>
            <tr><td>Seguimiento</td>
                <td><b>{odoo.get('tracking_label') or '—'}</b></td></tr>
        </table>
        """

        # ── Stock en tiempo real ───────────────────────────────────────────────
        stock_by_loc: List[Dict[str, Any]] = odoo.get("stock_by_loc", [])
        if stock_by_loc:
            html += "<div class=\"section\">📊 Stock en Tiempo Real (por Almacén)</div>"
            html += ("<table><tr>"
                     "<th>Almacén</th><th>Disponible</th><th>Reservado</th><th>Total Mano</th>"
                     "</tr>")
            total_avail = 0.0
            total_oh    = 0.0
            for loc in stock_by_loc:
                avail  = float(loc.get("available", 0) or 0)
                reserv = float(loc.get("reserved",  0) or 0)
                oh     = float(loc.get("on_hand",   0) or 0)
                total_avail += avail
                total_oh    += oh
                bg = "#d1e7dd" if avail > 0 else "#f8d7da"
                html += (
                    f"<tr style='background:{bg};'>"
                    f"<td><b>{loc.get('warehouse', '?')}</b></td>"
                    f"<td class='value-hi'>{avail:g}</td>"
                    f"<td style='color:#dc3545;'>{reserv:g}</td>"
                    f"<td>{oh:g}</td></tr>"
                )
            html += (
                f"<tr style='background:#343a40; color:white; font-weight:bold;'>"
                f"<td>TOTAL</td>"
                f"<td>{total_avail:g}</td>"
                f"<td></td>"
                f"<td>{total_oh:g}</td></tr>"
                f"</table>"
            )
        else:
            html += ("<div class=\"section\">📊 Stock</div>"
                     "<div style='color:#6c757d;font-size:11px; padding:4px;'>"
                     "Sin datos de stock disponibles.</div>")

        # ── Todos los proveedores ──────────────────────────────────────────────
        all_sellers: List[Dict[str, Any]] = odoo.get("all_sellers", [])
        if all_sellers:
            html += "<div class=\"section\">🏢 Proveedores (todos)</div>"
            html += ("<table><tr>"
                     "<th>#</th><th>Proveedor</th><th>Ref. Proveedor</th>"
                     "<th>Precio</th><th>Lead (d)</th><th>Q. mín.</th>"
                     "</tr>")
            for idx, seller in enumerate(all_sellers, 1):
                s_name  = seller.get("name", "—")
                s_code  = seller.get("code") or "—"
                s_price = float(seller.get("price") or 0)
                s_delay = seller.get("delay", 0) or 0
                s_minq  = float(seller.get("min_qty") or 0)
                bg = "#f8f9fa" if idx % 2 == 0 else "white"
                html += (
                    f"<tr style='background:{bg};'>"
                    f"<td style='text-align:center;'>{idx}</td>"
                    f"<td><b>{s_name}</b></td>"
                    f"<td>{s_code}</td>"
                    f"<td>{f'{s_price:,.2f} €' if s_price else '—'}</td>"
                    f"<td style='text-align:center;'>{s_delay}</td>"
                    f"<td style='text-align:right;'>{f'{s_minq:g}' if s_minq else '—'}</td>"
                    f"</tr>"
                )
            html += "</table>"

        # ── OC Pendientes ──────────────────────────────────────────────────────
        pending_po: List[Dict[str, Any]] = odoo.get("pending_po", [])
        if pending_po:
            html += "<div class=\"section\">🛒 Órdenes de Compra Pendientes</div>"
            html += ("<table><tr>"
                     "<th>OC</th><th>Proveedor</th><th>Pedido</th>"
                     "<th>Recibido</th><th>Pendiente</th><th>F. Prevista</th><th>P. Unit.</th>"
                     "</tr>")
            for po in pending_po:
                qty_ord  = float(po.get("qty_ordered",  0) or 0)
                qty_rcv  = float(po.get("qty_received", 0) or 0)
                qty_pend = float(po.get("qty_pending",  0) or 0)
                date_pl  = str(po.get("date_planned", "") or "")[:10] or "—"
                price_u  = float(po.get("price_unit", 0) or 0)
                html += (
                    f"<tr>"
                    f"<td><b>{po.get('po_name', '?')}</b></td>"
                    f"<td>{po.get('supplier', '—')}</td>"
                    f"<td style='text-align:right;'>{qty_ord:g}</td>"
                    f"<td style='text-align:right;'>{qty_rcv:g}</td>"
                    f"<td class='value-hi' style='text-align:right;'><b>{qty_pend:g}</b></td>"
                    f"<td>{date_pl}</td>"
                    f"<td style='text-align:right;'>{f'{price_u:,.2f} €' if price_u else '—'}</td>"
                    f"</tr>"
                )
            html += "</table>"
        else:
            html += ("<div class=\"section\">🛒 OC Pendientes</div>"
                     "<div style='color:#198754; font-size:11px; padding:4px;'>"
                     "✅ Sin órdenes de compra pendientes de recibir.</div>")

        # ── Reglas de Reaprovisionamiento ──────────────────────────────────────
        reorder_rules: List[Dict[str, Any]] = odoo.get("reorder_rules", [])
        if reorder_rules:
            html += "<div class=\"section\">🔄 Reglas de Reaprovisionamiento</div>"
            html += ("<table><tr>"
                     "<th>Almacén</th><th>Stock Mín.</th><th>Stock Máx.</th><th>Stock Actual</th><th>Estado</th>"
                     "</tr>")
            for rr in reorder_rules:
                q_min = float(rr.get("product_min_qty", 0) or 0)
                q_max = float(rr.get("product_max_qty", 0) or 0)
                q_oh  = float(rr.get("qty_on_hand",    0) or 0)
                if q_oh < q_min:
                    bg, estado = "#f8d7da", "🔴 Reponer YA"
                elif q_oh < q_min * 1.25:
                    bg, estado = "#fff3cd", "🟡 Stock bajo"
                else:
                    bg, estado = "#d1e7dd", "🟢 OK"
                html += (
                    f"<tr style='background:{bg};'>"
                    f"<td><b>{rr.get('warehouse', '?')}</b></td>"
                    f"<td style='text-align:right;'>{q_min:g}</td>"
                    f"<td style='text-align:right;'>{q_max:g}</td>"
                    f"<td style='text-align:right;'><b>{q_oh:g}</b></td>"
                    f"<td style='text-align:center;'>{estado}</td>"
                    f"</tr>"
                )
            html += "</table>"
        else:
            html += ("<div class=\"section\">🔄 Reaprovisionamiento</div>"
                     "<div style='color:#6c757d; font-size:11px; padding:4px;'>"
                     "Sin reglas de reaprovisionamiento configuradas.</div>")

        # ── Notas internas ─────────────────────────────────────────────────────
        if odoo.get("notes"):
            html += (
                "<div class=\"section\">📝 Notas internas (Odoo)</div>"
                "<div style='background:#fff8e1; border:1px solid #ffe082; "
                "border-radius:4px; padding:8px; font-size:11px; color:#555;'>"
                f"{odoo.get('notes')}</div>"
            )

        self._detail_widget.setText(html)

        # ── Tabla de embalajes ─────────────────────────────────────────────────
        pkg_details  = odoo.get("pkg_details", [])
        # Peso unitario: Odoo es primario, CSV como fallback
        weight_unit  = float(odoo.get("weight_kg") or csv.get("weight_kg") or 0.0)

        self._pkg_table.setRowCount(len(pkg_details))
        for row_i, p in enumerate(pkg_details):
            qty_pkg = float(p.get("qty") or 0.0)
            peso_unit_pkg  = weight_unit                     # kg por unidad/bobina
            peso_palet_pkg = qty_pkg * weight_unit           # kg estimado del palet (sin palet vacío)
            max_kg_pkg     = float(p.get("max_kg") or 0.0)  # kg máximo del tipo de embalaje

            factor_p = 0.001 if (p.get("l") or 0) > 10 else 1.0

            self._pkg_table.setItem(row_i, 0, QTableWidgetItem(p.get("name", "")))
            self._pkg_table.setItem(row_i, 1, QTableWidgetItem(f"{qty_pkg:g}"))
            self._pkg_table.setItem(row_i, 2, QTableWidgetItem(p.get("barcode", "") or "—"))
            self._pkg_table.setItem(row_i, 3, QTableWidgetItem(f"{(p.get('l') or 0) * factor_p:.4f}"))
            self._pkg_table.setItem(row_i, 4, QTableWidgetItem(f"{(p.get('w') or 0) * factor_p:.4f}"))
            self._pkg_table.setItem(row_i, 5, QTableWidgetItem(f"{(p.get('h') or 0) * factor_p:.4f}"))
            self._pkg_table.setItem(row_i, 6, QTableWidgetItem(f"{peso_unit_pkg:.3f}" if peso_unit_pkg > 0 else "—"))
            self._pkg_table.setItem(row_i, 7, QTableWidgetItem(f"{peso_palet_pkg:.2f}" if peso_palet_pkg > 0 else "—"))
            self._pkg_table.setItem(row_i, 8, QTableWidgetItem(f"{max_kg_pkg:.1f}" if max_kg_pkg > 0 else "—"))

            for col_i in range(9):
                item = self._pkg_table.item(row_i, col_i)
                if item:
                    item.setTextAlignment(Qt.AlignVCenter | (Qt.AlignRight if col_i > 0 else Qt.AlignLeft))
            if row_i == 0:
                for col_i in range(9):
                    item = self._pkg_table.item(row_i, col_i)
                    if item:
                        item.setBackground(QColor("#d1e7dd"))

        # ── CSV extra ─────────────────────────────────────────────────────────
        if csv:
            espesor_mm = float(csv.get('espesor_mm') or 0.0)
            factor_val = float(csv.get('factor') or 0.0)
            _espesor_str  = f"{espesor_mm:.1f} mm" if espesor_mm > 0 else "—"
            _factor_str   = f"{factor_val:g}" if factor_val > 0 else "—"
            _upp_str      = _fmt_qty(csv.get('units_per_pallet', 0))
            _peso_u_str   = _fmt_kg(csv.get('weight_kg', 0))
            _peso_p_str   = _fmt_kg(csv.get('peso_palet_total', 0))
            _cap_str      = str(csv.get('layers_per_pallet') or '—')
            _pal_t_str    = csv.get('pallet_type') or '—'
            _pal_w_str    = _fmt_m(csv.get('pallet_width_m', 0))
            _pal_l_str    = _fmt_m(csv.get('pallet_length_m', 0))
            _pal_h_str    = _fmt_m(csv.get('pallet_height_m', 0))
            csv_html = f"""
            <table style="font-size:11px; border-collapse:collapse; width:100%;">
                <tr style="background:#e9ecef;"><td colspan="2" style="padding:4px 8px; font-weight:bold;">🏷️ Identificación</td></tr>
                <tr><td style="padding:3px 8px;"><b>SKU (CSV)</b></td><td style="padding:3px 8px;">{csv.get('csv_sku') or '—'}</td></tr>
                <tr><td style="padding:3px 8px;"><b>Nombre (CSV)</b></td><td style="padding:3px 8px;">{csv.get('csv_name') or '—'}</td></tr>
                <tr><td style="padding:3px 8px;"><b>Familia</b></td><td style="padding:3px 8px;">{csv.get('family') or '—'}</td></tr>
                <tr><td style="padding:3px 8px;"><b>Sub-familia</b></td><td style="padding:3px 8px;">{csv.get('sub_family') or '—'}</td></tr>
                <tr style="background:#e9ecef;"><td colspan="2" style="padding:4px 8px; font-weight:bold;">📐 Unidad de Venta</td></tr>
                <tr><td style="padding:3px 8px;"><b>UM Venta</b></td><td style="padding:3px 8px;">{csv.get('unit') or '—'}</td></tr>
                <tr><td style="padding:3px 8px;"><b>Presentación</b></td><td style="padding:3px 8px;">{csv.get('presentation') or '—'}</td></tr>
                <tr><td style="padding:3px 8px;"><b>Factor conversión</b></td><td style="padding:3px 8px;">{_factor_str}</td></tr>
                <tr><td style="padding:3px 8px;"><b>Espesor / Alto unit.</b></td><td style="padding:3px 8px;">{_espesor_str}</td></tr>
                <tr><td style="padding:3px 8px;"><b>Peso por unidad</b></td><td style="padding:3px 8px;"><b>{_peso_u_str}</b></td></tr>
                <tr style="background:#e9ecef;"><td colspan="2" style="padding:4px 8px; font-weight:bold;">📦 Paletización</td></tr>
                <tr><td style="padding:3px 8px;"><b>UPP (ud/palet)</b></td><td style="padding:3px 8px;"><b>{_upp_str}</b></td></tr>
                <tr><td style="padding:3px 8px;"><b>Peso palet completo</b></td><td style="padding:3px 8px;"><b>{_peso_p_str}</b></td></tr>
                <tr><td style="padding:3px 8px;"><b>Tipo de palet</b></td><td style="padding:3px 8px;">{_pal_t_str}</td></tr>
                <tr><td style="padding:3px 8px;"><b>Alturas (capas)</b></td><td style="padding:3px 8px;">{_cap_str}</td></tr>
                <tr><td style="padding:3px 8px;"><b>Ancho palet</b></td><td style="padding:3px 8px;">{_pal_w_str}</td></tr>
                <tr><td style="padding:3px 8px;"><b>Largo palet</b></td><td style="padding:3px 8px;">{_pal_l_str}</td></tr>
                <tr><td style="padding:3px 8px;"><b>Alto palet</b></td><td style="padding:3px 8px;">{_pal_h_str}</td></tr>
            </table>
            """
            self._csv_detail.setText(csv_html)
        else:
            self._csv_detail.setText("<i style='color:#6c757d;'>Producto no encontrado en el CSV maestro de Imperbur.</i>")

        # Status
        n_results = 1  # siempre es un producto principal
        self._status_lbl.setText(f"✅ Producto encontrado ({source_tag}).")
        self._status_lbl.setStyleSheet("color: #198754; font-style: normal;")

    def _on_error(self, msg: str):
        self._btn_search.setEnabled(True)
        self._status_lbl.setText(f"❌ Error: {msg}")
        self._status_lbl.setStyleSheet("color: #dc3545; font-style: italic;")
        QMessageBox.critical(self, "Error de Consulta", f"No se pudo completar la búsqueda:\n{msg}")
        logger.error(f"[ProductQueryTab] {msg}")

    def _open_odoo_url(self):
        url = self._last_odoo_url_tmpl
        if url:
            webbrowser.open(url)
        else:
            QMessageBox.information(self, "Sin URL", "No hay URL de Odoo disponible para este producto.")
