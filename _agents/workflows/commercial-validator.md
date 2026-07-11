---
description: Workflow para validar, depurar o extender el motor de validación comercial de pedidos BUR2000 (descuentos, portes, grupos especiales).
---

# Workflow: Validación Comercial BUR2000

> Activa el skill `bur2000-commercial-validator` antes de ejecutar este workflow.

## Paso 1 — Identificar la tarea concreta

Determina cuál de estos casos aplica:

- **A)** Validar un pedido concreto (SO) → ir al Paso 2
- **B)** Regenerar `commercial_rules_v2.json` desde el Excel → ir al Paso 5
- **C)** Añadir o modificar una regla comercial → ir al Paso 6
- **D)** Depurar un resultado incorrecto → ir al Paso 7

---

## Paso 2 — Cargar contexto del cliente y pedido

```python
# Verificar que las reglas están cargadas correctamente
from app.db import commercial_rules as rules
print("SKU_MASTER count:", len(rules.SKU_MASTER))
print("BUR group size:", len(rules.BUR_GROUP_CLIENTS))
print("SPECIAL_CUSTOMERS:", list(rules.SPECIAL_CUSTOMERS.keys())[:5])
```

Confirmar:
- `SKU_MASTER` tiene ≥ 142 entradas
- `BUR_GROUP_CLIENTS` es un **set** (no dict)
- `SPECIAL_CUSTOMERS` contiene las excepciones si las hay

---

## Paso 3 — Ejecutar la validación

### Reporte masivo (Leak Report)
```python
from app.db.services.commercial_service import CommercialService
svc = CommercialService(odoo_service)
report = svc.get_leak_report(month=3, year=2026)
```

### Validación de pedido único
```python
result = svc.validate_single_order(order_id="S00123")
```

---

## Paso 4 — Interpretar el resultado

Usar el esquema de salida estándar:

| Campo | Qué verificar |
|-------|---------------|
| `status` | `APTO` / `NO APTO` / `APTO CON EXCEPCION` |
| `winning_rule_id` | ¿Qué regla ganó? ¿Es la esperada? |
| `rules_evaluated` | ¿Se evaluaron todas las reglas pertinentes? |
| `current_discount` vs `expected_discount` | ¿Hay fuga comercial? |
| `current_shipping` vs `expected_shipping` | ¿El porte es correcto? |
| `exception_reason` | Obligatorio si `exception_kept = True` |

Si `status = NO APTO` y el resultado parece incorrecto → ir al Paso 7.

---

## Paso 5 — Regenerar `commercial_rules_v2.json`

// turbo
```bash
cd c:\Users\User\Desktop\Bur2000_v2\Gabriela\scripts
python extract_commercial_matrix.py
```

Verificar tras la ejecución:
- `commercial_rules_v2.json` actualizado con fecha del día
- `SKU_MASTER` ≥ 142 SKUs
- `BUR_GROUP_CLIENTS` como lista JSON (el módulo lo convierte a `set` al cargar)
- `SHIPPING_GROUPS` contiene las claves `peninsula` y `baleares`

---

## Paso 6 — Añadir o modificar una regla comercial

1. **Asignar semáforo** 🟢🟠🔴 (ver §1 del skill)
2. **Si 🔴** → añadir `# TODO: DATO PENDIENTE` y no implementar lógica real
3. **Si 🟢/🟠** → editar `commercial_rules_v2.json` con el dato fuente
4. Regenerar con el Paso 5
5. Crear test unitario con un pedido real que ejercite la nueva regla
6. Verificar que `winning_rule_id` refleja el nuevo ID de regla

---

## Paso 7 — Depurar una validación incorrecta

1. **Verificar segmento**:
   ```python
   # ¿El customer_key es correcto?
   from app.db.services.commercial_service import _normalize_customer_key
   print(_normalize_customer_key("Almacenes Generalistas"))
   ```

2. **Verificar SKU**:
   ```python
   sku_info = rules.SKU_MASTER.get("98.020", {})
   print(sku_info)  # ¿Tiene family_logic_base y pallet_size_m2?
   ```

3. **Verificar zona geográfica**:
   ```python
   from app.db import commercial_rules as rules
   region = rules.get_region_by_cp("08001")
   print(region, rules.get_region_bucket(region))
   ```

4. **Comprobar pertenencia BUR**:
   ```python
   p_name = "PANEL-PLAC DISTRIBUIDORA, S.L."
   print(p_name in rules.BUR_GROUP_CLIENTS)  # debe ser True
   ```

5. Si todo lo anterior es correcto y el resultado sigue siendo incorrecto →
   revisar `discount_proposal.validate_range()` con los parámetros exactos del pedido.

---

## Checklist final antes de cerrar

- [ ] `status` correcto para todos los pedidos de prueba
- [ ] `winning_rule_id` trazable a un archivo fuente
- [ ] `commercial_rules_v2.json` versionado en git
- [ ] CHANGELOG.md actualizado con `fix:` o `feat:`
- [ ] Sin `# TODO: DATO PENDIENTE` en producción (solo aceptado en 🟠)
