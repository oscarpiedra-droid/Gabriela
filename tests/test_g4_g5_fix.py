# -*- coding: utf-8 -*-
"""
test_g4_g5_fix.py — Portes Abril 2026
======================================
Verifica que el motor de portes aplica los buckets C/D para G4 y el
bucket B correcto para BALEARES en G5, usando los precios vigentes
desde el 01/04/2026 (Portes Abril 2026).

Precios vigentes Abril 2026:
  G4 Bucket C  (<500€)   = 110€   (anterior: 90€)
  G4 Bucket C  (500-3K€) = 140€   (anterior: 120€)
  G4 Bucket D  (<500€)   = 180€   (anterior: 150€)
  G4 Bucket D  (500-3K€) = 200€   (anterior: 180€)
  G5 Bucket A  (<1500€)  =  60€   (anterior: 50€)
  G5 Bucket B  (<1500€)  = 110€   (anterior: 90€)
  G1 Bucket A  (<500€)   =  60€   (anterior: 50€)
  G1 Bucket A  (500-1.5K€) = 110€ (anterior: 90€)
  G2 Bucket A  (<3K€)    = 110€   (anterior: 90€)
"""
import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

import db.commercial_rules as rules


@pytest.fixture(autouse=True, scope="module")
def load_rules():
    """Carga el JSON de reglas una vez para todos los tests del módulo."""
    rules.load_from_json()


def get_price(group: str, region: str, amount: float) -> float | None:
    """Simula el motor Paso 7 con get_region_bucket_for_group."""
    bucket = rules.get_region_bucket_for_group(region, group)
    for r in rules.SHIPPING_GROUPS.get(group, []):
        if r['region_bucket_key'] == bucket and r['min_order_eur'] <= amount <= r['max_order_eur']:
            return float(r['price_eur'])
    return None


# ────────────────────────────────────────────────────────────────────────────
# G4_ANTIIMPACTO_NO_SOUND — Bucket C (Cataluña, Levante, Madrid)
# ────────────────────────────────────────────────────────────────────────────

class TestG4BucketC:
    """G4: solo Cataluña, Levante y Madrid van a bucket C."""

    def test_barcelona_tramo1(self):
        """G4 Barcelona — <500€ → Bucket C → 110€ (Abril 2026)."""
        assert get_price("G4_ANTIIMPACTO_NO_SOUND", "CATALUÑA", 200) == pytest.approx(110.0, abs=0.01)

    def test_alicante_tramo1(self):
        """G4 Alicante — <500€ → Bucket C → 110€ (Abril 2026)."""
        assert get_price("G4_ANTIIMPACTO_NO_SOUND", "LEVANTE", 200) == pytest.approx(110.0, abs=0.01)

    def test_madrid_tramo1(self):
        """G4 Madrid — <500€ → Bucket C → 110€ (Abril 2026)."""
        assert get_price("G4_ANTIIMPACTO_NO_SOUND", "MADRID", 200) == pytest.approx(110.0, abs=0.01)

    def test_barcelona_tramo2(self):
        """G4 Barcelona — 500-3000€ → Bucket C → 140€ (Abril 2026)."""
        assert get_price("G4_ANTIIMPACTO_NO_SOUND", "CATALUÑA", 1000) == pytest.approx(140.0, abs=0.01)

    def test_madrid_tramo2(self):
        """G4 Madrid — 500-3000€ → Bucket C → 140€ (Abril 2026)."""
        assert get_price("G4_ANTIIMPACTO_NO_SOUND", "MADRID", 1000) == pytest.approx(140.0, abs=0.01)

    def test_madrid_franco(self):
        """G4 Madrid — ≥3000€ → Franco (0€)."""
        assert get_price("G4_ANTIIMPACTO_NO_SOUND", "MADRID", 3000) == pytest.approx(0.0, abs=0.01)


# ────────────────────────────────────────────────────────────────────────────
# G4_ANTIIMPACTO_NO_SOUND — Bucket D (Resto: Aragón, Baleares, PV/Nav/Can, etc.)
# ────────────────────────────────────────────────────────────────────────────

class TestG4BucketD:
    """G4: Aragón, Baleares, PV-Nav-Can, CLM, And.Este, Asturias, CyL, Ext., And.Oeste → Bucket D."""

    def test_aragon_tramo1(self):
        assert get_price("G4_ANTIIMPACTO_NO_SOUND", "ARAGON-RIOJA", 200) == pytest.approx(180.0, abs=0.01)

    def test_baleares_tramo1(self):
        """Baleares va obligatoriamente a Bucket D en G4 (no a A)."""
        assert get_price("G4_ANTIIMPACTO_NO_SOUND", "BALEARES", 200) == pytest.approx(180.0, abs=0.01)

    def test_norte_tramo1(self):
        assert get_price("G4_ANTIIMPACTO_NO_SOUND", "NORTE (PV-NAV-CAN)", 200) == pytest.approx(180.0, abs=0.01)

    def test_clm_tramo1(self):
        assert get_price("G4_ANTIIMPACTO_NO_SOUND", "CASTILLA LA MANCHA", 200) == pytest.approx(180.0, abs=0.01)

    def test_andalucia_este_tramo1(self):
        assert get_price("G4_ANTIIMPACTO_NO_SOUND", "ANDALUCIA ESTE", 200) == pytest.approx(180.0, abs=0.01)

    def test_asturias_tramo1(self):
        assert get_price("G4_ANTIIMPACTO_NO_SOUND", "ASTURIAS-GALICIA", 200) == pytest.approx(180.0, abs=0.01)

    def test_cyl_tramo1(self):
        assert get_price("G4_ANTIIMPACTO_NO_SOUND", "CASTILLA Y LEON", 200) == pytest.approx(180.0, abs=0.01)

    def test_extremadura_tramo1(self):
        assert get_price("G4_ANTIIMPACTO_NO_SOUND", "EXTREMADURA", 200) == pytest.approx(180.0, abs=0.01)

    def test_andalucia_oeste_tramo1(self):
        assert get_price("G4_ANTIIMPACTO_NO_SOUND", "ANDALUCIA OESTE", 200) == pytest.approx(180.0, abs=0.01)

    def test_aragon_tramo2(self):
        assert get_price("G4_ANTIIMPACTO_NO_SOUND", "ARAGON-RIOJA", 1000) == pytest.approx(200.0, abs=0.01)

    def test_baleares_tramo2(self):
        assert get_price("G4_ANTIIMPACTO_NO_SOUND", "BALEARES", 1000) == pytest.approx(200.0, abs=0.01)

    def test_baleares_franco(self):
        """G4 Baleares — ≥3000€ → Franco (0€)."""
        assert get_price("G4_ANTIIMPACTO_NO_SOUND", "BALEARES", 3000) == pytest.approx(0.0, abs=0.01)


# ────────────────────────────────────────────────────────────────────────────
# G5_SOUND — Baleares va a Bucket B (no A)
# ────────────────────────────────────────────────────────────────────────────

class TestG5Sound:
    """G5: Baleares debe ir a Bucket B (110€), no al A (60€)."""

    def test_barcelona_bucket_a(self):
        assert get_price("G5_SOUND", "CATALUÑA", 500) == pytest.approx(60.0, abs=0.01)

    def test_aragon_bucket_a(self):
        assert get_price("G5_SOUND", "ARAGON-RIOJA", 500) == pytest.approx(60.0, abs=0.01)

    def test_levante_bucket_a(self):
        assert get_price("G5_SOUND", "LEVANTE", 500) == pytest.approx(60.0, abs=0.01)

    def test_norte_bucket_a(self):
        assert get_price("G5_SOUND", "NORTE (PV-NAV-CAN)", 500) == pytest.approx(60.0, abs=0.01)

    def test_madrid_bucket_a(self):
        assert get_price("G5_SOUND", "MADRID", 500) == pytest.approx(60.0, abs=0.01)

    def test_clm_bucket_a(self):
        assert get_price("G5_SOUND", "CASTILLA LA MANCHA", 500) == pytest.approx(60.0, abs=0.01)

    def test_andalucia_este_bucket_a(self):
        assert get_price("G5_SOUND", "ANDALUCIA ESTE", 500) == pytest.approx(60.0, abs=0.01)

    def test_baleares_bucket_b_no_a(self):
        """Baleares en G5 debe pagar 110€ (Bucket B), NO 60€ (Bucket A)."""
        price = get_price("G5_SOUND", "BALEARES", 500)
        assert price == pytest.approx(110.0, abs=0.01), (
            f"REGRESIÓN: Baleares en G5 debe ser BUCKET B (110€), obtenido {price}€"
        )

    def test_asturias_bucket_b(self):
        assert get_price("G5_SOUND", "ASTURIAS-GALICIA", 500) == pytest.approx(110.0, abs=0.01)

    def test_cyl_bucket_b(self):
        assert get_price("G5_SOUND", "CASTILLA Y LEON", 500) == pytest.approx(110.0, abs=0.01)

    def test_extremadura_bucket_b(self):
        assert get_price("G5_SOUND", "EXTREMADURA", 500) == pytest.approx(110.0, abs=0.01)

    def test_andalucia_oeste_bucket_b(self):
        assert get_price("G5_SOUND", "ANDALUCIA OESTE", 500) == pytest.approx(110.0, abs=0.01)

    def test_baleares_franco(self):
        """G5 Baleares — ≥1500€ → Franco (0€)."""
        assert get_price("G5_SOUND", "BALEARES", 1500) == pytest.approx(0.0, abs=0.01)


# ────────────────────────────────────────────────────────────────────────────
# G1/G2/G3 — Baleares en Bucket A (sin cambio de asignación, pero precio nuevo)
# ────────────────────────────────────────────────────────────────────────────

class TestG1G2G3Baleares:
    """G1/G2/G3: Baleares sigue en Bucket A; precios actualizados Abril 2026."""

    def test_g1_baleares_tramo1(self):
        """G1 Baleares — <500€ → Bucket A → 60€ (Abril 2026)."""
        assert get_price("G1_GENERAL", "BALEARES", 200) == pytest.approx(60.0, abs=0.01)

    def test_g1_baleares_tramo2(self):
        """G1 Baleares — 500-1500€ → Bucket A → 110€ (Abril 2026)."""
        assert get_price("G1_GENERAL", "BALEARES", 800) == pytest.approx(110.0, abs=0.01)

    def test_g2_baleares_tramo2(self):
        """G2 Baleares — 500-3000€ → Bucket A → 110€ (Abril 2026)."""
        assert get_price("G2_CM_XPS", "BALEARES", 1500) == pytest.approx(110.0, abs=0.01)

    def test_g3_baleares_tramo2(self):
        """G3 Baleares — 500-3000€ → Bucket A → 90€ (G3 sin cambio en Abril 2026)."""
        assert get_price("G3_ACUSTICA_AGLO", "BALEARES", 1500) == pytest.approx(90.0, abs=0.01)
