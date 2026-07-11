"""
Tests unitarios para DiscountProposalService.validate_range
=============================================================
Estos tests usan datos inyectados directamente en el caché de la clase
(sin necesitar el Excel real) para garantizar reproducibilidad en CI.

Escenarios cubiertos (Spec Técnica 2026):
  - DTO == tramo_max → OK (dentro del límite exacto)
  - DTO < tramo_max  → OK
  - DTO > tramo_max, DTO <= next_max → AVISO (zona de escalado)
  - DTO > tramo_max, DTO >  next_max → BLOQUEADO
  - DTO > tramo_max, sin siguiente tramo → BLOQUEADO
  - Tolerancia float: DTO = max + 0.005 → OK (dentro de FLOAT_TOL=0.01)
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

import pytest
from db.services.commercial_conditions_service import DiscountProposalService


# ---------------------------------------------------------------------------
# Dataset sintético de reglas — inyectado en el caché de clase
# ---------------------------------------------------------------------------
FAKE_RULES = [
    # Segmento A / Familia F1 — Tramo 1: 0–999 €  → dto max Territorial 52%, Baleares 48%
    # Claves según COL_DTO_TER y COL_DTO_BAL del servicio actual (schema Excel 2026)
    {
        "Segmento": "A",
        "Familia": "F1",
        "Tramo facturación": "< 1.000 €",   # tramo inferior → min=0, max=999.99
        "DTO Territorial (%)": 52,
        "DTO Baleares (%)": 48,
        "Condición mínima (familias/referencias)": "",
    },
    # Segmento A / Familia F1 — Tramo 2: 1000–4999 € → dto max Territorial 55%, Baleares 50%
    {
        "Segmento": "A",
        "Familia": "F1",
        "Tramo facturación": 1000,           # tramo numérico → min=1000, max=inf
        "DTO Territorial (%)": 55,
        "DTO Baleares (%)": 50,
        "Condición mínima (familias/referencias)": "",
    },
    # Segmento A / Familia F1 — Tramo 3: 5000+ €
    {
        "Segmento": "A",
        "Familia": "F1",
        "Tramo facturación": 5000,
        "DTO Territorial (%)": 60,
        "DTO Baleares (%)": 55,
        "Condición mínima (familias/referencias)": "",
    },
    # Segmento B / Familia FX — tramo único (sin siguiente)
    {
        "Segmento": "B",
        "Familia": "FX",
        "Tramo facturación": "< 1.000 €",   # único tramo
        "DTO Territorial (%)": 40,
        "DTO Baleares (%)": 38,
        "Condición mínima (familias/referencias)": "",
    },
]


@pytest.fixture(autouse=True)
def inject_fake_data():
    """Inyecta los datos sintéticos en el caché de clase antes de cada test y lo limpia después."""
    DiscountProposalService._cache_data = FAKE_RULES
    yield
    DiscountProposalService._cache_data = None


@pytest.fixture()
def svc():
    return DiscountProposalService(excel_path="/fake/path.xlsx")


# ---------------------------------------------------------------------------
# Casos OK
# ---------------------------------------------------------------------------

class TestDescuentoOK:
    def test_dto_exactamente_en_maximo(self, svc):
        """DTO == dto_max exacto → OK."""
        result = svc.validate_range("A", "F1", base_imponible=500, territorio="peninsula", dto_solicitado=52.0)
        assert result["status"] == "OK", f"Esperado OK, obtenido: {result}"

    def test_dto_por_debajo_del_maximo(self, svc):
        """DTO < dto_max → OK."""
        result = svc.validate_range("A", "F1", base_imponible=500, territorio="peninsula", dto_solicitado=45.0)
        assert result["status"] == "OK"

    def test_float_tolerancia_sin_falso_positivo(self, svc):
        """DTO = 52.005 % (dentro de FLOAT_TOL=0.01 sobre max=52%) → debe seguir siendo OK."""
        result = svc.validate_range("A", "F1", base_imponible=500, territorio="peninsula", dto_solicitado=52.005)
        assert result["status"] == "OK", (
            f"FLOAT_TOL no funciona: DTO 52.005 sobre max 52 debería ser OK pero fue {result['status']}"
        )


# ---------------------------------------------------------------------------
# Caso AVISO — zona de escalado
# ---------------------------------------------------------------------------

class TestZonaEscalado:
    def test_dto_excedido_dentro_del_siguiente_tramo(self, svc):
        """DTO=53% > max_tramo_1(52%) pero <= max_tramo_2(55%) → AVISO con next_max."""
        result = svc.validate_range("A", "F1", base_imponible=500, territorio="peninsula", dto_solicitado=53.0)
        assert result["status"] == "AVISO", f"Esperado AVISO, obtenido: {result}"
        assert result.get("rules", {}).get("next_max") == 55, "next_max debe ser 55"
        assert result.get("valid") is False

    def test_dto_justo_en_limite_del_siguiente_tramo(self, svc):
        """DTO=55% == max_tramo_2 → AVISO (está en la frontera exacta)."""
        result = svc.validate_range("A", "F1", base_imponible=500, territorio="peninsula", dto_solicitado=55.0)
        assert result["status"] == "AVISO", f"Esperado AVISO, obtenido: {result}"


# ---------------------------------------------------------------------------
# Caso BLOQUEADO
# ---------------------------------------------------------------------------

class TestDescuentoBloqueado:
    def test_dto_excedido_sin_siguiente_tramo(self, svc):
        """DTO=45% > max único de Seg B (40%) sin siguiente tramo → BLOQUEADO."""
        result = svc.validate_range("B", "FX", base_imponible=100, territorio="peninsula", dto_solicitado=45.0)
        assert result["status"] == "BLOQUEADO", f"Esperado BLOQUEADO, obtenido: {result}"

    def test_dto_excedido_por_encima_del_siguiente_tramo(self, svc):
        """DTO=56% > max_tramo_1(52%) Y > max_tramo_2(55%) → BLOQUEADO."""
        result = svc.validate_range("A", "F1", base_imponible=500, territorio="peninsula", dto_solicitado=56.0)
        assert result["status"] == "BLOQUEADO", f"Esperado BLOQUEADO, obtenido: {result}"


# ---------------------------------------------------------------------------
# Caso sin regla → OK por defecto
# ---------------------------------------------------------------------------

class TestSinRegla:
    def test_segmento_desconocido(self, svc):
        """Si no hay regla para el segmento, el sistema devuelve UNCHECKED (Guarda 3).
        No bloquea pero tampoco aprueba silenciosamente — la UI muestra ⚠️."""
        result = svc.validate_range("Z", "UNKNOWN", base_imponible=1000, territorio="peninsula", dto_solicitado=99.0)
        assert result["status"] in ("OK", "UNCHECKED"), (
            f"Segmento desconocido debe ser no-bloqueante (OK o UNCHECKED), obtenido: {result['status']}"
        )
        assert result.get("valid", True) is True, "No debe bloquear cuando no hay regla"



# ---------------------------------------------------------------------------
# Territorio Baleares
# ---------------------------------------------------------------------------

class TestBaleares:
    def test_dto_ok_baleares(self, svc):
        """DTO=48% == max_baleares_tramo_1 → OK."""
        result = svc.validate_range("A", "F1", base_imponible=500, territorio="baleares", dto_solicitado=48.0)
        assert result["status"] == "OK"

    def test_dto_excedido_baleares(self, svc):
        """DTO=52% > max_baleares_tramo_1(48%) pero <= max_baleares_tramo_2(50%) → AVISO."""
        result = svc.validate_range("A", "F1", base_imponible=500, territorio="baleares", dto_solicitado=49.0)
        assert result["status"] == "AVISO", f"Esperado AVISO Baleares, obtenido: {result}"
