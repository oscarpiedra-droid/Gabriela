"""
Servicio de Homologación de Clientes BUR2000 (v3.5).

ARQUITECTURA:
─────────────────────────────────────────────────────────────────
Fuente de verdad: campo Many2one oficial de Odoo
    • sale.order   → partner_type
    • res.partner  → customer_type

El catálogo homologacion_clientes.json es una capa de RE-MAPEO opcional,
NO una whitelist de validación.

Lógica de resolución:
    1. Campo vacío/nulo       → SIN_HOMOLOGACION (bloquear)
    2. Nombre en catálogo     → usar segmento del catálogo (re-mapeo)
    3. Nombre NO en catálogo  → usar el nombre directamente (pass-through OK)
    4. Segmento especial      → FUERA_TABLA / POR_DEFINIR

El catálogo solo es necesario cuando el nombre en Odoo difiere del segmento
de la tabla de descuentos (ej: "Constructora" → "Especialistas").
Para tipos nuevos en Odoo, funciona automáticamente sin tocar el catálogo.
─────────────────────────────────────────────────────────────────
"""

import json
import os
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from loguru import logger

# ── Ruta al catálogo maestro ────────────────────────────────────────────────
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_CATALOG_PATH = os.path.join(_BASE_DIR, "homologacion_clientes.json")


# ── Tipos de resultado ───────────────────────────────────────────────────────

class HomologacionStatus(str, Enum):
    """Estado devuelto por el motor de homologación."""
    OK               = "OK"              # Segmento tarifable (catálogo o pass-through)
    FUERA_TABLA      = "FUERA_DE_TABLA"  # 'Condiciones fuera de la tabla'
    POR_DEFINIR      = "POR_DEFINIR"     # 'Tipo de Empresa por Definir'
    SIN_HOMOLOGACION = "SIN_HOMOLOGACION"  # Campo vacío en Odoo


@dataclass
class HomologacionResult:
    """Resultado completo de la homologación de un cliente."""
    odoo_tipo_cliente:   str
    segmento_aplicacion: str
    uso:                 str  # ESTÁNDAR | SOUND | ESPECIAL | REVISIÓN
    status:              HomologacionStatus
    mensaje_funcional:   str
    winning_rule_id:     str
    notas:               str = ""

    @property
    def es_tarifable(self) -> bool:
        """True si se puede aplicar tabla estándar de descuentos."""
        return self.status == HomologacionStatus.OK


# ── Servicio principal ───────────────────────────────────────────────────────

class HomologacionService:
    """
    Servicio singleton que resuelve el segmento comercial de un cliente.

    El catálogo actúa como capa de re-mapeo opcional: solo es necesario
    cuando el nombre del tipo en Odoo difiere del nombre de segmento en la
    tabla de descuentos. Para cualquier tipo no registrado, se usa el propio
    nombre del tipo directamente como segmento (pass-through). Solo se bloquea
    cuando el campo en Odoo está vacío/nulo.

    Uso:
        svc = HomologacionService()
        result = svc.homologar("Distribuidor Oficial. Independiente")
        if result.es_tarifable:
            segmento = result.segmento_aplicacion  # → "Almacenes Generalistas"
    """
    _catalog: dict[str, dict] = {}
    _loaded:  bool = False

    def __init__(self, catalog_path: Optional[str] = None):
        self._path = catalog_path or _CATALOG_PATH
        if not HomologacionService._loaded:
            self._load_catalog()

    # ── Carga del catálogo ───────────────────────────────────────────────────

    def _load_catalog(self) -> None:
        """Carga homologacion_clientes.json en un dict de búsqueda rápida O(1)."""
        if not os.path.exists(self._path):
            logger.error(f"[Homologación] Catálogo no encontrado: {self._path}")
            HomologacionService._catalog = {}
            HomologacionService._loaded = True
            return

        try:
            with open(self._path, "r", encoding="utf-8") as f:
                raw = json.load(f)

            catalog: dict[str, dict] = {}
            for entry in raw.get("homologacion", []):
                key = entry.get("odoo_tipo_cliente", "").strip()
                if key and entry.get("estado", "activo") == "activo":
                    catalog[key] = entry

            HomologacionService._catalog = catalog
            HomologacionService._loaded = True
            logger.info(
                f"[Homologación] Catálogo de re-mapeo cargado: {len(catalog)} entradas "
                f"(v{raw.get('_meta', {}).get('version', '?')})"
            )
        except Exception as exc:
            logger.error(f"[Homologación] Error cargando catálogo: {exc}")
            HomologacionService._catalog = {}
            HomologacionService._loaded = True

    def reload(self) -> None:
        """Fuerza la recarga del catálogo desde disco."""
        HomologacionService._loaded = False
        self._load_catalog()

    # ── Resolución de homologación ───────────────────────────────────────────

    def homologar(self, odoo_tipo_cliente: str) -> HomologacionResult:
        """
        Resuelve el segmento comercial a partir del tipo de cliente de Odoo.

        El catálogo es una capa de RE-MAPEO opcional (no whitelist):
        - Vacío          → SIN_HOMOLOGACION (bloquear — no hay tipo asignado en Odoo)
        - En catálogo    → usar segmento del catálogo
        - No en catálogo → usar el valor directamente como segmento (pass-through OK)
        """
        valor = (odoo_tipo_cliente or "").strip()

        # 1. Campo vacío → cliente sin tipo asignado en Odoo
        if not valor:
            return HomologacionResult(
                odoo_tipo_cliente   = "",
                segmento_aplicacion = "",
                uso                 = "DESCONOCIDO",
                status              = HomologacionStatus.SIN_HOMOLOGACION,
                mensaje_funcional   = (
                    "Sin segmento: el campo 'Tipo de cliente' está vacío en Odoo. "
                    "Asignar el tipo de cliente al cliente en Odoo y reintentar."
                ),
                winning_rule_id     = "SIN_CAMPO_ODOO",
            )

        # 2. Re-mapeo desde catálogo (coincidencia exacta case-sensitive)
        entry = HomologacionService._catalog.get(valor)

        if entry is not None:
            segmento = entry.get("segmento_aplicacion", valor)
            uso      = entry.get("uso", "ESTÁNDAR")
            notas    = entry.get("notas", "")

            if segmento == "Condiciones fuera de la tabla":
                return HomologacionResult(
                    odoo_tipo_cliente   = valor,
                    segmento_aplicacion = segmento,
                    uso                 = uso,
                    status              = HomologacionStatus.FUERA_TABLA,
                    mensaje_funcional   = (
                        f"ALERTA — '{valor}' → condiciones fuera de tabla estándar. "
                        "Requiere regla comercial dedicada."
                    ),
                    winning_rule_id     = "FUERA_DE_TABLA",
                    notas               = notas,
                )

            if segmento == "Tipo de Empresa por Definir":
                return HomologacionResult(
                    odoo_tipo_cliente   = valor,
                    segmento_aplicacion = segmento,
                    uso                 = uso,
                    status              = HomologacionStatus.POR_DEFINIR,
                    mensaje_funcional   = (
                        f"'{valor}' pendiente de clasificación. "
                        "Actualizar el tipo de cliente en Odoo."
                    ),
                    winning_rule_id     = "POR_DEFINIR",
                    notas               = notas,
                )

            logger.debug(f"[Homologación] Re-mapeo catálogo: '{valor}' → '{segmento}'")
            return HomologacionResult(
                odoo_tipo_cliente   = valor,
                segmento_aplicacion = segmento,
                uso                 = uso,
                status              = HomologacionStatus.OK,
                mensaje_funcional   = f"OK — '{valor}' → '{segmento}' (catálogo).",
                winning_rule_id     = f"OK_CATALOGO_{uso}",
                notas               = notas,
            )

        # 3. No en catálogo: pass-through — el nombre es el segmento directamente
        logger.info(
            f"[Homologación] Pass-through: '{valor}' "
            "(campo oficial Odoo, sin re-mapeo en catálogo)"
        )
        return HomologacionResult(
            odoo_tipo_cliente   = valor,
            segmento_aplicacion = valor,
            uso                 = "ESTÁNDAR",
            status              = HomologacionStatus.OK,
            mensaje_funcional   = (
                f"OK — '{valor}' aceptado directamente como segmento (pass-through)."
            ),
            winning_rule_id     = "OK_PASS_THROUGH",
        )

    # ── Utilities ────────────────────────────────────────────────────────────

    def listar_entradas(self) -> list[dict]:
        """Devuelve todas las entradas activas del catálogo (para auditoría/UI)."""
        return list(HomologacionService._catalog.values())

    def get_catalog_size(self) -> int:
        """Número de entradas activas en el catálogo."""
        return len(HomologacionService._catalog)


# ── Instancia singleton de módulo ────────────────────────────────────────────
homologacion = HomologacionService()
