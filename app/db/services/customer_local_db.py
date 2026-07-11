"""
customer_local_db.py
--------------------
Base de datos SQLite local para clientes dados de alta vía el formulario de onboarding.
Complementa a Odoo: guarda un registro local de cada alta/actualización.

Ubicación: app/db/clientes_local.db  (se crea automáticamente)
"""

import sqlite3
import os
from datetime import datetime
from typing import List, Dict, Any, Optional
from loguru import logger

# Ruta al fichero SQLite (junto al resto de datos de la app)
_DB_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # → app/db/
_DB_PATH = os.path.join(_DB_DIR, "clientes_local.db")


class CustomerLocalDB:
    """Gestión de la base de datos SQLite local de clientes."""

    # ------------------------------------------------------------------ #
    #  DDL – esquema de la tabla                                          #
    # ------------------------------------------------------------------ #
    _CREATE_TABLE = """
    CREATE TABLE IF NOT EXISTS clientes (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        nif             TEXT NOT NULL,
        nombre          TEXT NOT NULL,
        tipo_cliente    TEXT,
        tipo_entidad    TEXT,          -- 'empresa' / 'persona'
        comercial       TEXT,
        comercial_email TEXT,
        comercial_cod   TEXT,
        telefono        TEXT,
        movil           TEXT,
        email           TEXT,
        calle           TEXT,
        cp              TEXT,
        ciudad          TEXT,
        provincia       TEXT,
        iban            TEXT,
        modo_pago       TEXT,
        plazo_pago      TEXT,
        odoo_partner_id INTEGER,
        accion          TEXT,          -- 'alta' / 'actualizacion'
        fecha_alta      TEXT NOT NULL,
        fecha_mod       TEXT,
        notas           TEXT
    );
    """

    _CREATE_IDX_NIF = "CREATE INDEX IF NOT EXISTS idx_clientes_nif ON clientes(nif);"
    _CREATE_IDX_NOMBRE = "CREATE INDEX IF NOT EXISTS idx_clientes_nombre ON clientes(nombre);"

    # ------------------------------------------------------------------ #
    #  Conexión                                                           #
    # ------------------------------------------------------------------ #
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(_DB_PATH)
        conn.row_factory = sqlite3.Row          # acceso por nombre de columna
        conn.execute("PRAGMA journal_mode=WAL;")  # mejor rendimiento concurrente
        return conn

    def _ensure_schema(self):
        """Crea las tablas si no existen."""
        with self._connect() as conn:
            conn.execute(self._CREATE_TABLE)
            conn.execute(self._CREATE_IDX_NIF)
            conn.execute(self._CREATE_IDX_NOMBRE)

    # ------------------------------------------------------------------ #
    #  Operaciones principales                                            #
    # ------------------------------------------------------------------ #
    def upsert(self, data: Dict[str, Any], odoo_partner_id: int, accion: str) -> int:
        """
        Inserta o actualiza un cliente en la BD local.

        Si ya existe un registro con el mismo NIF lo actualiza (modo 'actualizacion').
        En cualquier caso devuelve el id local del registro.

        Parámetros
        ----------
        data              : el mismo dict que se pasa a create_or_update_customer
        odoo_partner_id   : el id devuelto por Odoo tras el alta
        accion            : 'alta' | 'actualizacion'
        """
        self._ensure_schema()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        nif = (data.get("nif") or "").strip().upper()

        row = {
            "nif":             nif,
            "nombre":          (data.get("name") or "").upper().strip(),
            "tipo_cliente":    data.get("customer_type", ""),
            "tipo_entidad":    "empresa" if data.get("is_company") else "persona",
            "comercial":       data.get("commercial_agent", ""),
            "comercial_email": data.get("commercial_agent_email", ""),
            "comercial_cod":   data.get("commercial_agent_code", ""),
            "telefono":        data.get("phone", ""),
            "movil":           data.get("mobile", ""),
            "email":           data.get("email_facturacion") or data.get("email_principal", ""),
            "calle":           data.get("street", ""),
            "cp":              data.get("zip", ""),
            "ciudad":          data.get("city", ""),
            "provincia":       data.get("province_name", ""),
            "iban":            data.get("iban", ""),
            "modo_pago":       data.get("payment_mode", ""),
            "plazo_pago":      data.get("payment_terms", ""),
            "odoo_partner_id": odoo_partner_id,
            "accion":          accion,
            "notas":           data.get("notes", ""),
        }

        with self._connect() as conn:
            existing = conn.execute(
                "SELECT id FROM clientes WHERE nif = ?", (nif,)
            ).fetchone()

            if existing:
                # UPDATE — actualizar registro existente
                row["fecha_mod"] = now
                set_clause = ", ".join(
                    f"{k} = :{k}" for k in row if k not in ("nif",)
                )
                conn.execute(
                    f"UPDATE clientes SET {set_clause} WHERE nif = :nif",
                    row
                )
                local_id = existing["id"]
                logger.info(f"[LocalDB] Cliente actualizado → NIF={nif} id_local={local_id}")
            else:
                # INSERT
                row["fecha_alta"] = now
                row["fecha_mod"]  = now
                cols = ", ".join(row.keys())
                vals = ", ".join(f":{k}" for k in row.keys())
                cur = conn.execute(f"INSERT INTO clientes ({cols}) VALUES ({vals})", row)
                local_id = cur.lastrowid
                logger.info(f"[LocalDB] Cliente nuevo → NIF={nif} id_local={local_id}")

            conn.commit()

        return local_id

    # ------------------------------------------------------------------ #
    #  Consultas                                                          #
    # ------------------------------------------------------------------ #
    def search_by_nif(self, nif: str) -> Optional[Dict[str, Any]]:
        self._ensure_schema()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM clientes WHERE nif = ?",
                (nif.strip().upper(),)
            ).fetchone()
        return dict(row) if row else None

    def search_by_name(self, name: str) -> List[Dict[str, Any]]:
        self._ensure_schema()
        pattern = f"%{name.upper()}%"
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM clientes WHERE nombre LIKE ?",
                (pattern,)
            ).fetchall()
        return [dict(r) for r in rows]

    def get_all(self, limit: int = 500, offset: int = 0) -> List[Dict[str, Any]]:
        """Devuelve todos los registros (para el panel de consulta)."""
        self._ensure_schema()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM clientes ORDER BY fecha_mod DESC LIMIT ? OFFSET ?",
                (limit, offset)
            ).fetchall()
        return [dict(r) for r in rows]

    def get_recent(self, days: int = 30) -> List[Dict[str, Any]]:
        """Clientes dados de alta en los últimos N días."""
        self._ensure_schema()
        since = datetime.now().strftime(f"%Y-%m-%d")
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM clientes WHERE fecha_alta >= ? ORDER BY fecha_alta DESC",
                (since,)
            ).fetchall()
        return [dict(r) for r in rows]

    def count(self) -> int:
        self._ensure_schema()
        with self._connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM clientes").fetchone()[0]

    # ------------------------------------------------------------------ #
    #  Utilidades                                                         #
    # ------------------------------------------------------------------ #
    @property
    def db_path(self) -> str:
        return _DB_PATH
