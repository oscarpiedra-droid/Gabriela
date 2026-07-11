import os
import contextlib
from loguru import logger

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False
    logger.warning("psycopg2 no está instalado. Instalalo usando 'pip install psycopg2-binary'")

def _create_raw_connection(autocommit: bool):
    if not HAS_PSYCOPG2:
        logger.error("Se requiere psycopg2 para conectarse a PostgreSQL. Simulando conexión por falla crítica.")
        # Raise here unless we want to fail gracefully in UI? 
        # The prompt architecture strictly requires PostgreSQL + psycopg2. We will raise.
        raise ImportError("psycopg2 no está instalado. (pip install psycopg2-binary)")

    host = os.environ.get("PG_HOST", "localhost")
    port = os.environ.get("PG_PORT", "5432")
    db   = os.environ.get("PG_DB",   "bur2000")
    user = os.environ.get("PG_USER", "postgres")
    pwd  = os.environ.get("PG_PASS", "")

    try:
        conn = psycopg2.connect(
            host=host, port=port, dbname=db, user=user, password=pwd,
            cursor_factory=RealDictCursor
        )
        conn.autocommit = autocommit
        return conn
    except Exception as e:
        logger.error(f"[DB] Error de conexión a PostgreSQL ({host}:{port}/{db}): {e}")
        raise

def get_conn(auto_return: bool = False):
    """
    Conexión principal usada por la UI (con autocommit o manejadas a mano).
    - Según `user_rules`: Las operaciones principales de UI usan get_conn(auto_return=False)
    """
    return _create_raw_connection(autocommit=auto_return)

@contextlib.contextmanager
def get_service_conn(auto_return: bool = True):
    """
    Context manager de conexión para workers de fondo y endpoints de API móvil.
    - Según `user_rules`: Los Workers utilizan get_service_conn(auto_return=True) 
      o manejan transactions dentro del with.
    """
    conn = _create_raw_connection(autocommit=auto_return)
    try:
        yield conn
        if not auto_return:
            conn.commit()
    except Exception:
        if not auto_return:
            conn.rollback()
        raise
    finally:
        conn.close()
