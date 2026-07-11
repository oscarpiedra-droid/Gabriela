---
name: bur2000-gabriela-tester
description: >
  Skill de QA para Gabriela (BUR2000 Comercial). Garantiza que cualquier
  cambio en el motor comercial (portes, descuentos, homologación) sea
  verificado con la suite de tests antes de darlo por válido.
  Protocolo: ROJO → VERDE → REFACTOR → CERTIFICAR.
---

# 🧪 BUR2000 Gabriela — Skill de Testing y QA

> **Regla de Oro:** Ningún cambio en el motor comercial se declara "funcionando"
> hasta que `pytest` confirme 0 fallos. Si hay fallos, ARREGLAR antes de responder.

---

## 📋 Suite de Tests Gabriela

Ubicación: `C:\Users\User\Desktop\Bur2000_v2\Gabriela\tests\`

| Test | Cubre | Estado |
|------|-------|--------|
| `test_g4_g5_fix.py` | Buckets G4 (C/D) y G5 (Baleares→B). Precios Portes Abril 2026 | ✅ 35 tests |
| `test_validate_range.py` | `DiscountProposalService.validate_range`: OK/AVISO/BLOQUEADO/UNCHECKED | ✅ 10 tests |
| `test_commercial_service.py` | `CommercialService`: fugas, filtrado clientes, sugerencias IA | ✅ 3 tests |
| `test_integrity_guards.py` | Guardas: hash Excel, cobertura mapa familias | ✅ variable |
| `test_multigama_bonus.py` | Bonus +2 GAMAS / +OTRA GAMA | ✅ variable |

**Comando maestro (ejecutar SIEMPRE antes de reportar éxito):**
```powershell
& "C:\Users\User\Desktop\Bur2000_v2\Gabriela\miniconda\python.exe" -m pytest `
  "C:\Users\User\Desktop\Bur2000_v2\Gabriela\tests\test_g4_g5_fix.py" `
  "C:\Users\User\Desktop\Bur2000_v2\Gabriela\tests\test_validate_range.py" `
  "C:\Users\User\Desktop\Bur2000_v2\Gabriela\tests\test_integrity_guards.py" `
  "C:\Users\User\Desktop\Bur2000_v2\Gabriela\tests\test_multigama_bonus.py" `
  "C:\Users\User\Desktop\Bur2000_v2\Gabriela\tests\test_commercial_service.py" `
  -v --tb=short 2>&1
```

---

## ⚠️ Errores Comunes (Lecciones Aprendidas)

### L1 — Tests con `print()/sys.exit()` causan INTERNALERROR en pytest
Los tests deben usar `def test_*()` con `assert`. Un archivo con código a nivel módulo
que llame a `sys.exit()` hace que pytest lance `INTERNALERROR` al coleccionar.

```python
# ❌ INCORRECTO — estilo script, no pytest
import sys
result = get_price("G4", "MADRID", 200)
if result != 110.0:
    FAIL += 1
sys.exit(0 if FAIL == 0 else 1)

# ✅ CORRECTO — estilo pytest
def test_g4_madrid_tramo1():
    assert get_price("G4_ANTIIMPACTO_NO_SOUND", "MADRID", 200) == pytest.approx(110.0, abs=0.01)
```

### L2 — FAKE_RULES deben usar las claves actuales del servicio
`DiscountProposalService` usa constantes como `COL_TRAMO`, `COL_DTO_TER`, `COL_DTO_BAL`.
Si el esquema del Excel cambia, los tests con FAKE_RULES deben actualizarse también.

```python
# ✅ Claves correctas (schema Excel 2026 — vigente desde 19/01/2026)
{
    "Segmento": "A",
    "Familia": "F1",
    "Tramo facturación": "< 1.000 €",   # COL_TRAMO
    "DTO Territorial (%)": 52,           # COL_DTO_TER
    "DTO Baleares (%)": 48,              # COL_DTO_BAL
    "Condición mínima (familias/referencias)": "",  # COL_CONDICION
}

# ❌ Claves obsoletas (schema anterior — no usar):
# "Base imponible desde (EUR)", "DTO máximo Península (%)", etc.
```

### L3 — Precios de test desactualizados tras actualización de tarifas
Al actualizar el JSON de reglas (p.ej. `patch_portes_abril2026.py`), los tests
que tienen precios hardcodeados DEBEN actualizarse o fallarán sistemáticamente.

**Proceso correcto para actualizar tarifas:**
1. Ejecutar el script de parche: `python tests/patch_portes_abril2026.py`
2. Verificar JSON: `python tests/verify_discounts_vs_excel.py`
3. **Actualizar los precios esperados en los tests afectados**
4. Ejecutar pytest → confirmar 0 fallos
5. Solo entonces reportar al usuario que funciona

### L4 — Bug zona de escalado: `next()` en lista ordenada DESC devuelve el mayor, no el adyacente
El algoritmo de "zona de escalado" en `validate_range` busca el tramo inmediatamente
superior. Si la lista está ordenada DESC y se usa `next()`, se obtiene el t_min más alto
(no el adyacente). Usar `min()` con filtro en su lugar.

```python
# ❌ BUG — next() en lista DESC devuelve el MAYOR t_min > current
next_rule = next(
    (r for r in rules if self._parse_tramo_minimo(r.get(COL_TRAMO)) > current_tmin),
    None,
)

# ✅ CORRECTO — min() sobre los candidatos da el ADYACENTE
candidatos = [r for r in rules if self._parse_tramo_minimo(r.get(COL_TRAMO)) > current_tmin]
next_rule = min(candidatos, key=lambda r: self._parse_tramo_minimo(r.get(COL_TRAMO)), default=None)
```

### L5 — `UNCHECKED` vs `OK` para segmentos sin regla
Desde la Guarda 3 (sesión 14 Abril 2026), `validate_range` devuelve `UNCHECKED`
(no `OK`) cuando no hay regla para el par segmento/familia. Los tests deben aceptar
AMBOS como no-bloqueantes.

```python
# ✅ Test robusto para comportamiento no-bloqueante
assert result["status"] in ("OK", "UNCHECKED")
assert result.get("valid", True) is True
```

---

## 🔄 Flujo de Trabajo (Protocol ROJO→VERDE→CERTIFICA)

```
1. ROJO    → Ejecutar pytest. Ver qué falla y por qué.
2. ANALIZAR → ¿Los tests están mal? ¿El código está mal?
              NO cambiar los tests para ocultar bugs del código.
3. VERDE   → Arreglar el código (o el test si el test era incorrecto).
             Ejecutar pytest → 0 fallos.
4. COMPRENDE → Añadir la lección al MEMORY.md y a esta skill.
5. CERTIFICA → Solo entonces reportar al usuario que "funciona".
```

**Regla crítica:** Si pytest falla, NUNCA reportar al usuario "debería funcionar"
o "prueba a ver". Resolver primero, reportar después.

---

## 📝 Cómo añadir un nuevo test

Cuando se implemente una nueva feature o fix en el motor comercial:

1. **Crear el test ANTES de la implementación** (TDD preferido) o como mínimo
   al mismo tiempo que el fix.

2. **Estructura estándar** para tests de portes:
```python
# tests/test_nueva_feature.py
import sys, os, pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))
import db.commercial_rules as rules

@pytest.fixture(autouse=True, scope="module")
def load_rules():
    rules.load_from_json()

class TestNuevaFeature:
    def test_caso_especifico(self):
        """Descripción clara de lo que verifica."""
        resultado = ...  # llamada al motor
        assert resultado == pytest.approx(VALOR_ESPERADO, abs=0.01), (
            f"REGRESIÓN: descripción del invariante"
        )
```

3. **Estructura estándar** para tests de descuentos (con FAKE_RULES):
```python
@pytest.fixture(autouse=True)
def inject_fake_data():
    from db.services.commercial_conditions_service import DiscountProposalService
    DiscountProposalService._cache_data = FAKE_RULES  # claves del schema 2026
    yield
    DiscountProposalService._cache_data = None
```

4. **Ejecutar la suite completa** → confirmar que los tests nuevos pasan y
   los existentes no se rompen.

---

## 🏷️ Convención de Nombres

| Tipo | Prefijo | Ejemplo |
|------|---------|---------|
| Tests de portes (grupos/buckets) | `test_g{N}_*.py` | `test_g4_g5_fix.py` |
| Tests de descuentos | `test_validate_*.py` | `test_validate_range.py` |
| Tests de integridad | `test_integrity_*.py` | `test_integrity_guards.py` |
| Tests de bonus | `test_*bonus*.py` | `test_multigama_bonus.py` |
| Tests de servicio completo | `test_{servicio}.py` | `test_commercial_service.py` |
