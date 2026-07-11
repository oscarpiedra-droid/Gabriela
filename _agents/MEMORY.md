# 🧠 MEMORY.md — Gabriela Rojas Pro (BUR2000 Comercial)
> **Lectura OBLIGATORIA al inicio de cada sesión.**
> Contiene lecciones aprendidas que evitan repetir errores costosos.
> Actualizado: 13 Abril 2026 · Versión Gabriela v3.5

---

## 📌 Regla de Oro para el Agente

**ANTES de escribir código, leer este archivo y verificar:**
1. ¿Ya existe el módulo que quiero crear? **Gabriela tiene 1700+ líneas solo en `product_calculator_dialog.py`**
2. ¿La llamada a Odoo está dentro de `with svc._lock`?
3. ¿La operación pesada va en un QThread?

---

## 🏗️ Arquitectura Gabriela vs BUR2000_app

> **¡CRÍTICO!** Gabriela NO es un clon de BUR2000_app. Tienen diferencias fundamentales.

| Aspecto | BUR2000_app (WMS) | Gabriela (CRM Comercial) |
|---------|-------------------|--------------------------|
| Base de datos | PostgreSQL (Docker) | **SQLite local** (`app/db/clientes_local.db`) + Odoo XML-RPC |
| ORM | `get_conn()` / `get_service_conn()` | `odoorpc` directo en servicios |
| Entorno Python | Miniconda local | Miniconda local (`miniconda/`) |
| UI base | `BaseBurTab` + `lazy loading` | **Sin clase base** — cada tab independiente |
| `ui/components/` | Rico, con widgets reutilizables | **VACÍO** — solo `__init__.py` |
| Skills locales | 27 skills en `.agent/skills/` | Sin skills propias (usar las de BUR2000_app) |
| API móvil | FastAPI (`mobile_server.py`) | No tiene |
| Arranque | `Arrancar_Bur2000.bat` | `Gabriela.bat` o `miniconda\python.exe app/main.py` |

---

## 🔑 Archivos Críticos de Gabriela

| Archivo | Rol | Tamaño |
|---------|-----|--------|
| `app/main.py` | Punto de entrada, orquestador de tabs | 12.6 KB |
| `app/bur2000_theme.py` | Tokens de color/tema — usar siempre | 3 KB |
| `app/db/connection.py` | `get_conn()` y `get_service_conn()` — PostgreSQL | 2.2 KB |
| `app/db/services/odoo_service_v2.py` | ⭐ API Odoo central (41 KB) | 41 KB |
| `app/db/services/commercial_service.py` | ⭐ Motor comercial completo | 54 KB |
| `app/db/services/commercial_conditions_service.py` | Validador 2026, tramos, NaN fix | 18 KB |
| `app/ui/dialogs/product_calculator_dialog.py` | ⭐ Calculadora logística completa | 90 KB |
| `app/ui/tabs/commercial_validator_tab.py` | Validador comercial UI | 54 KB |
| `app/ui/tabs/customer_onboarding_tab.py` | Alta de clientes | 71 KB |
| `app/ui/tabs/product_query_tab.py` | Consulta de producto | 57 KB |
| `app/ui/tabs/logistics_tab.py` | Logística y albaranes | 27 KB |
| `app/db/commercial_rules_v2.json` | Reglas descuentos (600 KB) — NO tocar directamente. Usar scripts `tests/patch_*.py` | 600 KB |
| `Nuevo/ENERO 2026 - Con Axarquia.xlsx` | ⭐ **ÚNICA FUENTE DE VERDAD** (descuentos + portes). Hoja `Portes Abril 2026` vigente desde 01/04/2026. Hoja `Condiciones de dtos` vigente desde 19/01/2026. Usar `tests/verify_discounts_vs_excel.py` para auditar. | — |

---

## ⚠️ LECCIÓN 1 — Llamadas a Odoo: patrón correcto

**El patrón correcto en `odoo_service_v2.py` usa `odoorpc`, NO `xmlrpc.client`.**

```python
# ✅ CORRECTO en Gabriela (odoorpc)
def _ex(model, method, *args, **kw):
    try:
        with svc._lock:
            svc._ensure_connected()
            return getattr(svc.odoo.env[model], method)(*args, **kw)
    except Exception as e:
        logger.warning(f"[Worker] {model}.{method}: {e}")
        return [] if method in ("search", "search_read") else None

# ❌ INCORRECTO — método que NO existe en OdooServiceV2
svc.execute(model, method, ...)  # AttributeError!
```

**Lección:** `OdooServiceV2` NO tiene método `.execute()`. Eso es del cliente xmlrpc estándar.

---

## ⚠️ LECCIÓN 2 — Motor Comercial 2026: NaN es truthy en Python

**el operador `or` NO detecta `float('nan')` como falso.**

```python
# ❌ BUGGY — NaN pasa el 'or' sin activar el fallback
dto = float(row.get("DTO Baleares (%)") or 0)  # NaN es truthy → devuelve NaN

# ✅ CORRECTO — usar _safe_dto() que convierte NaN → None/0
def _safe_dto(v) -> float | None:
    if v is None: return None
    f = float(v)
    return None if math.isnan(f) else f

dto = _safe_dto(row.get("DTO Baleares (%)")) or _safe_dto(row.get("DTO Territorial (%)")) or 0.0
```

**Columnas del Excel 2026 (NO usar nombres de 2024):**
- ✅ `"Tramo facturación"`, `"DTO Territorial (%)"`, `"DTO Baleares (%)"`
- ❌ ~~`"Importe_min"`, `"Descuento_max"`~~ (formato 2024, ya NO existe)

---

## ⚠️ LECCIÓN 3 — Calculadora Logística: NO recrear desde cero

**`app/ui/dialogs/product_calculator_dialog.py` ya existe con 1700+ líneas.**
Tiene Tab 1 (Por SKU) y Tab 2 (Por Pedido SO), 3 QThreads, diagnóstico de calidad de datos.

### UoM m² — Bug crítico corregido (2026-04-12)

Para productos en m² (aislantes, membranas), Odoo devuelve `packaging.qty` en la UoM del producto:
- `pkg_sorted[0].qty = 800` → m²/palet **(NO 800 bobinas/palet)**
- `pkg_sorted[1].qty = 25` → m²/bobina

```python
# Detección de UoM de superficie
_UOM_MEASURE_KW = ("m²", "m2", "superficie", "surface", "area")
uom_is_measure = any(kw in uom.lower() for kw in _UOM_MEASURE_KW)

# Corrección UPP y peso unitario
if uom_is_measure and unit_pkg_qty > 1.001 and palet_qty_odoo > 0:
    upp    = round(palet_qty_odoo / unit_pkg_qty, 4)  # bobinas/palet
    weight = round(weight * unit_pkg_qty, 4)           # kg/m² → kg/bobina
```

### _OrderWorker — Leer dimensiones del palé (GAP 4, 2026-04-12)

El `_OrderWorker` de Tab 2 ahora lee `stock.package.type` para LDM exacto:

```python
# Leer dimensiones del tipo de palé
t_rows = _ex("stock.package.type", "read", type_ids,
             ["id", "name", "packaging_length", "width", "height", "max_weight"])

# Usar _calc_ldm() en vez de _ldm_std()
ldm_line = _calc_ldm(pals_frac, line_dim_l, line_dim_w, pallet_type, is_stackable)
```

Indicador en tabla: `"0.400 ◉"` (verde, dims reales) vs `"~0.400"` (estimado estándar).

---

## ⚠️ LECCIÓN 4 — Incidencias: siempre usar `with svc.odoo._lock`

**Bug real ocurrido en `resolve_incidence`:** Un hilo de fondo puede sobreescribir el `stage_id`
si `resolve_incidence` no tiene el lock.

```python
# ✅ CORRECTO — siempre proteger escrituras a Odoo con _lock
def resolve_incidence(self, ticket_id: int) -> bool:
    with self.odoo._lock:
        self._ensure_connected()
        self.odoo.env["helpdesk.ticket"].write([ticket_id], {"stage_id": ...})
```

---

## ⚠️ LECCIÓN 5 — Alta de clientes: normalización de campos CSV

El CSV de Google Forms puede devolver `'No'` (N mayúscula). Siempre normalizar:

```python
# ✅ Correcto
if "NO" in campo.upper():
    ...

# ❌ Incorrecto — falla con 'No', 'no', 'NO', etc.
if campo in ["NO", "DIFERENTE"]:
    ...
```

---

## ⚠️ LECCIÓN 6 — `btn_refresh` y atributos no inicializados

En PySide6, los callbacks de señales pueden ejecutarse antes de que el widget esté construido.

```python
# ✅ Siempre guardar con hasattr antes de acceder a widgets
if hasattr(self, 'btn_refresh'):
    self.btn_refresh.setEnabled(True)
```

---

## 🗺️ Jerarquía de fuentes de datos (calculadora)

```
1. Odoo XML-RPC (real time, máxima precisión)
   └─ product.packaging + stock.package.type
2. BD local inventory_item (armonizado) ← pendiente implementar en Gabriela
3. CSV Maestro Google Sheets (~20s timeout, fallback)
4. Defaults: EUROPA, no apilable, 0.40 LDM/palé
```

---

## 🧹 Archivos temporales a limpiar (raíz Gabriela)

> Ejecutar `/clean-debug` cuando se acumulen:

```
debug_*.py, debug_*.txt
diagnose_*.py
explore_*.py
probe_*.py, probe_*.txt, probe_*.json
tmp_*.py, tmp_*.txt, tmp_*.json
scan_*.py, scan_*.txt
diff.txt (2.8 MB), patch*.diff (3 MB)
status.txt (si existe)
```

---

## 📊 Estado módulos Gabriela (Abril 2026)

| Módulo | Estado | Horas |
|--------|--------|-------|
| Motor Comercial 2026 + Validador | ✅ Certificado | ~28h |
| Calculadora Logística (GAP 2+4) | ✅ Fix UoM m² | esta sesión |
| Onboarding Clientes | ✅ Entregado | ~14h |
| WMS Logística / Albaranes | ✅ Entregado | ~35h |
| Helpdesk Incidencias | ✅ Entregado | ~18h |
| Dashboard BI | 🔄 Parcial | ~10h |
| Consulta Producto | 🔄 Parcial | ~12h |
| Control Horario QR | 🔄 En curso | ~6h |

---

## 📝 Automantenimiento del Agente

Si en **esta sesión** solucionas un bug o defines una arquitectura nueva para Gabriela,
es **TU RESPONSABILIDAD** añadir la lección aquí antes de terminar la sesión.

---

## ⚠️ LECCIÓN 7 — Motor de Portes: G4 usa buckets C/D, G5 pone Baleares en B

**Bugs encontrados en auditoría exhaustiva (13 Abril 2026) al comparar Excel vs JSON:**

El bucket global `A/B` no es válido para todos los grupos de envío. El Excel oficial
`Descuentos/Nueva Política de Portes 2026.xlsx` (vigente desde 19/01/2026) define:

| Grupo | Zona baja | Zona alta |
|-------|-----------|-----------|
| **G1/G2/G3** | A: Cataluña+Aragón+Levante+**Baleares**+PV-Nav-Can+Madrid+CLM+And.Este → 50/90/90€ | B: Asturias-Galicia+CyL+Extremadura+And.Oeste → 90/120/120€ |
| **G4_ANTIIMPACTO_NO_SOUND** | C (solo): Cataluña+Levante+Madrid → 90/120€ | D (RESTO incl. **Baleares**, Aragón, PV-Nav-Can, CLM, And.Este, Asturias, CyL, Ext., And.Oeste) → **150/180€** |
| **G5_SOUND** | A: Cataluña+Aragón+Levante+PV-Nav-Can+Madrid+CLM+And.Este → 50€ | B: **BALEARES**+Asturias-Galicia+CyL+Extremadura+And.Oeste → **90€** |

**Bajo-cobros que existían antes del fix:**
- G4 Baleares/Aragón/PV/CLM/And.Este: cobraban 90€ en vez de 150€ (-60€ por envío)
- G5 Baleares: cobraba 50€ en vez de 90€ (-40€ por envío)

**Archivos modificados:**
- `app/db/commercial_rules.py`: nueva función `get_region_bucket_for_group(region, group)`
- `app/db/commercial_rules_v2.json`: G4 tiene ahora buckets `C` y `D` (no A/B)
- `app/db/services/commercial_service.py` (Paso 7, ambos paths): usa `get_region_bucket_for_group(region, sg)` en el bucle de grupos

```python
# ✅ CORRECTO — bucket específico por grupo de envío
sg_bucket = rules.get_region_bucket_for_group(region, sg)
for r in sg_rules:
    if r['region_bucket_key'] == sg_bucket and \
       r['min_order_eur'] <= total_products_base <= r['max_order_eur']:
        group_cost = float(r['price_eur'])
        break

# ❌ INCORRECTO (bug previo) — bucket global ignora excepciones G4 y G5
for r in sg_rules:
    if r['region_bucket_key'] == region_bucket and ...
```

**Tests de regresión:** `tests/test_g4_g5_fix.py` — 35 casos, 12 regiones × G4/G5. ✅ 0 fallos.

---

## 🔑 LECCIÓN 8 — Alineación Portes Abril 2026 + Descuentos Excel completo

**Fecha:** 13 Abril 2026 | **Archivos cambiados:** `commercial_rules_v2.json` (SHIPPING_GROUPS + SKU_DISCOUNTS)

### 8.1 Tarifas Portes Abril 2026 — Subidas aplicadas

| Grupo | Bucket | Cambio |
|-------|--------|--------|
| G1 General | A Grado1 | 50→**60€** |
| G1 General | A Grado2 | 90→**110€** |
| G1 General | B Grado1 | 90→**110€** |
| G1 General | B Grado2 | 120→**140€** |
| G2 CM XPS | A | 90→**110€** |
| G2 CM XPS | B | 120→**140€** |
| G3 Acústica AGLO | A/B | **sin cambio** (90/120€) |
| G4 NO SOUND | C \<500€ | 90→**110€** |
| G4 NO SOUND | C 500-3000€ | 120→**140€** |
| G4 NO SOUND | D \<500€ | 150→**180€** |
| G4 NO SOUND | D 500-3000€ | 180→**200€** |
| G5 SOUND | A | 50→**60€** |
| G5 SOUND | B | 90→**110€** |

### 8.2 Bugs de descuento corregidos

- Valores cruzados Especialistas ↔ Generalistas en CM XPS (el JSON tenía los de +2 GAMAS como base)
- Empresas Instaladoras Anti Impacto y Impermeabilizantes (tenían valores de otro segmento)
- Axarquía tramos granulares Anti Impacto e Impermeabilizantes (2500 y 1000 distintos al estándar)
- PARQUET SKUs (21.xxx) sin segmento `ALMACENES_INSTALADORES_SOUND` → añadido

**Resultado:** 118 combinaciones verificadas → **0 ERR** | `tests/verify_discounts_vs_excel.py`

### 8.3 Feature Pendiente — Bonus +2 GAMAS

Cuando CM XPS se compra con ≥2 familias adicionales o PARQUET con otra gama, el Excel define un bonus de **+2% de descuento territorial**. **NO implementado** en `commercial_conditions_service.py`. Hay 16 filas `[PEND]` en el audit. Cuando se implemente, añadir clave `_2GAMAS` en el JSON.

### 8.4 Excel obsoletos eliminados

Solo queda `Nuevo/ENERO 2026 - Con Axarquia.xlsx`. Eliminados: `Descuentos/Nueva Política de Portes 2026.xlsx`, `Descuentos/Nueva tabla de descuentos ENERO 2026.xlsx`, `Descuentos/Axarquia/ENERO 2026 - Con Axarquia.xlsx`, `v2/propuesta_condiciones_dtos_enero_2026_rangos_limpia.xlsx`.

---

## ⚠️ LECCIÓN 9 — Tipo de cliente Odoo: campo correcto y arquitectura del homologador

**Fecha:** 14 Abril 2026 | **Archivos:** `homologacion_service.py`, `commercial_service.py`

### 9.1 El campo correcto en Odoo

El tipo de cliente en Imperbur **NO** está en `category_id` (etiquetas). Siempre ha estado en:

| Modelo | Campo | Tipo | Usa como |
|--------|-------|------|----------|
| `sale.order` | `partner_type` | Many2one | ⭐ Fuente primaria — ya viene en el fetch del pedido, sin coste extra |
| `res.partner` | `customer_type` | Many2one | Fuente secundaria — si el pedido no trae `partner_type` |
| `res.partner` | `category_id` | Many2many | **SIEMPRE VACÍO en este Odoo.** No usar nunca. ❌ |

```python
# ✅ CORRECTO — Many2one devuelve [id, nombre]; usar [1]
_pt = order.get('partner_type')
customer_type_raw = _pt[1] if (_pt and isinstance(_pt, (list, tuple)) and len(_pt) > 1) else ""

# ❌ INCORRECTO — category_id está vacío para todos los clientes
cat_ids = partner.get('category_id', [])  # → [] siempre
```

### 9.2 Fetch correcto en Odoo

```python
# sale.order — añadir partner_type al search_read del pedido
orders_data = SO.search_read([('id', 'in', so_ids)], [
    'name', 'partner_id', 'amount_untaxed', ...,
    'partner_type'  # ← OBLIGATORIO, no olvidar
])

# res.partner — solo zip + customer_type. Sin category_id.
partners = svc.odoo.env['res.partner'].search_read(
    [('id', 'in', ids)], ['zip', 'customer_type']
)
```

### 9.3 Arquitectura definitiva del HomologacionService (v3.5)

**El catálogo `homologacion_clientes.json` es RE-MAPEO opcional, NO whitelist.**

```
Valor nombreOdoo (Many2one[1])
    │
    ├─ ""  (vacío)     → SIN_HOMOLOGACION ❌  cliente sin tipo asignado en Odoo
    ├─ En catálogo     → segmento del catálogo (renombrado)
    │                    Solo necesario si nombreOdoo ≠ nombre segmento en tarifa
    │                    Ej: "Constructora" → "Especialistas"
    └─ No en catálogo  → PASS-THROUGH ✅  nombre usado directamente como segmento
                         Tipos nuevos en Odoo funcionan solos, sin tocar el catálogo
```

### 9.4 Patrón canónico en commercial_service.py

```python
# Fuente 1: partner_type del pedido (gratis, ya en memoria)
_pt = order.get('partner_type')
if _pt and isinstance(_pt, (list, tuple)) and len(_pt) > 1:
    customer_type_raw = _pt[1]
else:
    # Fuente 2: customer_type del partner
    _ct = (partner_map.get(p_id) or {}).get('customer_type')
    customer_type_raw = _ct[1] if (_ct and isinstance(_ct, (list, tuple)) and len(_ct) > 1) else ""

homo_result = _homologacion_svc.homologar(customer_type_raw)
# homologar() hace pass-through internamente → nunca bloquea por tipo "nuevo"
```

**Nunca** añadir una tercera fuente `category_id`. **Nunca** pasar flags de contexto al llamador (`desde_campo_oficial`, etc.). La lógica de tolerancia vive **dentro** del servicio `homologar()`.

---

## 🚨 LECCIÓN 10 — Regla E1 de Portes y Audit Excel Abril 2026

**Sesión:** 14 Abril 2026 · BUG resuelto en `commercial_service.py`

### El Bug: E1 sobreescribía el msg_prefix aunque el pedido ya era franco por importe

**Antes (MAL):**
```python
elif has_valid_lines and all_lines_high_discount:
    expected_portes = 0.0
    msg_prefix = f"Dto. Lineal >= {min_dto_for_free_portes}%"
```
Si el pedido tenía ≥ 1.500€ (G1 franco → `expected_portes = 0`), E1 se evaluaba igualmente
y mostraba "Dto. Lineal ≥ 30%" en la UI cuando el motivo real era el franco de importe.

**Después (CORRECTO):**
```python
elif has_valid_lines and all_lines_high_discount and expected_portes > 0:
    # E1: solo cuando aún no era franco por importe
    expected_portes = 0.0
    msg_prefix = f"Dto. Lineal >= {min_dto_for_free_portes}% (Portes Gratis)"
```

### Umbrales de franquicia oficiales (Portes Abril 2026 — vigente 01/04/2026)

| Grupo | `shipping_group_key` | Franco desde |
|-------|---------------------|-------------|
| Air-Bur / Termoreflex / Acústicos / Impermeabilizantes | `G1_GENERAL` | **1.500 €** |
| Air-Bur Termic (CM XPS) | `G2_CM_XPS` | **3.000 €** |
| Acústica AGLO | `G3_ACUSTICA_AGLO` | **3.000 €** |
| Anti Impacto NO SOUND | `G4_ANTIIMPACTO_NO_SOUND` | **3.000 €** |
| Anti Impacto SOUND | `G5_SOUND` | **1.500 €** |

Tarifa Bucket A (Península A): G1 — 60€ (<500€) / 110€ (500→1500€)
Tarifa Bucket B (Península B): G1 — 110€ (<500€) / 140€ (500→1500€)

### Audit Excel → Motor: qué está correcto

- ✅ **Empresas Constructoras** y todos sus segmentos leen del Excel directamente (`DiscountProposalService` usa `pandas.read_excel`, no JSON)
- ✅ **6 segmentos** activos en Excel: cubiertos por `commercial_conditions_service.py`
- ✅ **Tarifas G1 JSON** alineadas con Portes Abril 2026 (60/110/0€ y 110/140/0€)
- ✅ **Regla E1** ahora solo se activa si `expected_portes > 0` (el pedido no llega al umbral)
- ✅ **FAMILY_LOGIC_MAP_OVERRIDES** cubre los alias propios de Constructoras y Axarquía

### Mapeo de familias por segmento

`FAMILY_LOGIC_MAP_OVERRIDES` en `commercial_conditions_service.py`:
- `Axarquía de Aislamientos (Distribución)` → alias `CM_XPS_SYC` = `"AIR BUR TERMIC (CM )"` y `REFLECTIVOS_...` = `"AIR-BUR TERMIC / (EXCL. CM )"`
- `Empresas Constructoras` → alias `REFLECTIVOS_EXCL_CM_XPS_SYC` = `"AIR-BUR TERMIC (EXCL. CM XPS / S-YC)"`

**Si aparece nuevo segmento en el Excel**: el motor lo leerá automáticamente via pandas. Solo necesita que el `homologacion_service.py` lo acepte como pass-through (ya implementado en v3.5).

---

## ⚠️ LECCIÓN 11 — Tests con `sys.exit()` causan INTERNALERROR en pytest

**Sesión:** 14 Abril 2026

`test_g4_g5_fix.py` usaba `print()` + `sys.exit()` a nivel módulo → cuando pytest
intentaba coleccionarlo lanzaba `INTERNALERROR`. La solución es usar siempre `def test_*()`
con `assert` y `pytest.approx`.

```python
# ❌ INCORRECTO — no es un test pytest válido
OK = 0; FAIL = 0
check("G4 Barcelona 200EUR", get_price(...), 90.0)  # sys.exit(1) si falla
sys.exit(0 if FAIL == 0 else 1)

# ✅ CORRECTO — pytest nativo
class TestG4BucketC:
    def test_barcelona_tramo1(self):
        assert get_price("G4_ANTIIMPACTO_NO_SOUND", "CATALUÑA", 200) == pytest.approx(110.0, abs=0.01)
```

**Causa raíz paralela:** los precios esperados estaban desactualizados (tarifa enero 2026
en vez de Portes Abril 2026). Al actualizar la tarifa en el JSON, hay que actualizar los
tests en el mismo commit.

---

## ⚠️ LECCIÓN 12 — Bug zona escalado: `next()` en lista DESC devuelve el mayor, no el adyacente

**Sesión:** 14 Abril 2026 · **Archivo:** `commercial_conditions_service.py` L597

`_get_tramo_rules()` devuelve reglas ordenadas DESC por tramo_min. Al buscar el
"siguiente tramo" con `next()`, se devuelve el PRIMERO con `t_min > current` → el MÁS ALTO.
Pero se necesita el ADYACENTE (el menor entre los candidatos).

```python
# ❌ BUG — next() en lista DESC retorna el mayor t_min > current_tmin
next_rule = next(
    (r for r in rules if self._parse_tramo_minimo(r.get(COL_TRAMO)) > current_tmin),
    None,
)

# ✅ CORRECTO — min() sobre los candidatos = el tramo inmediatamente superior
candidatos = [r for r in rules if self._parse_tramo_minimo(r.get(COL_TRAMO)) > current_tmin]
next_rule = min(candidatos, key=lambda r: self._parse_tramo_minimo(r.get(COL_TRAMO)), default=None)
```

**Efecto del bug:** `AVISO` mostraba el DTO del tramo 3 (el más alto) en vez del tramo 2
(el adyacente), y pedidos que debían ser `BLOQUEADO` quedaban en `AVISO`.

---

## 🧪 Protocolo de Test Obligatorio (Gabriela v3.5+)

**Antes de reportar cualquier fix como "funciona":**

```powershell
& "C:\Users\User\Desktop\Bur2000_v2\Gabriela\miniconda\python.exe" -m pytest `
  "C:\Users\User\Desktop\Bur2000_v2\Gabriela\tests\test_g4_g5_fix.py" `
  "C:\Users\User\Desktop\Bur2000_v2\Gabriela\tests\test_validate_range.py" `
  "C:\Users\User\Desktop\Bur2000_v2\Gabriela\tests\test_integrity_guards.py" `
  "C:\Users\User\Desktop\Bur2000_v2\Gabriela\tests\test_multigama_bonus.py" `
  "C:\Users\User\Desktop\Bur2000_v2\Gabriela\tests\test_commercial_service.py" `
  -v --tb=short 2>&1
```

**Resultado esperado:** `XX passed, 0 failed`. Si hay fallos, resolverlos ANTES de responder.

