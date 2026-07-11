# Changelog - Gabriela Rojas Pro

## [3.5] - 2026-04-12

### 🗂️ GAP 3 — Panel "Estado Catálogo Odoo" en Dashboard

#### `DashboardTab` (`ui/tabs/dashboard_tab.py`)
- **Nueva tarjeta "Estado Catálogo Odoo":** Añadida segunda tarjeta en el panel derecho
  del Dashboard con KPIs de calidad de datos del catálogo Odoo en tiempo real:
  - **Productos activos:** Total de referencias con SKU activo en Odoo
  - **Sin embalaje/UPP:** Productos sin `product.packaging` definido (crítico para logística)
  - **Sin peso definido:** Productos con `weight = 0`
  - **Sin volumen/dims:** Productos con `volume = 0`
- **Semáforo visual:** El KPI "Sin embalaje/UPP" cambia de color automáticamente:
  - 🟢 Verde: < 10% del catálogo sin UPP
  - 🟡 Ámbar: 10-30% sin UPP
  - 🔴 Rojo: > 30% sin UPP
- **`CatalogQualityWorker` (QThread):** Análisis asíncrono que no bloquea la UI.
  Utiliza el mismo patrón de `svc._lock` que los workers de la calculadora.
- **`set_odoo_service()`:** Nuevo método inyector para conectar el servicio Odoo al Dashboard.
- **Fix `StatsRefreshWorker`:** Renombrado `finished` → `done` para evitar colisión con
  `QThread.finished` nativo (lección del MEMORY.md BUR2000).
- **Botón ↻ Refresh:** Permite actualizar el diagnóstico manualmente en cualquier momento.

#### Infraestructura y Limpieza
- **BUR2000_app:** Eliminados **149 archivos** de diagnóstico/tmp/bak de la raíz
  (bulk_errors.txt 1.4MB, tmp_harmonize_log3.txt 206KB, etc.). Raíz reducida de ~198 a 49 archivos.
- **HORAS_TRABAJO.md:** Actualizado como fuente canónica única del banco de horas del Plan
  Transformación Digital (1.950h / 43.075€), cubriendo ambos repos BUR2000_app + Gabriela.
- **Skill `bur2000-registro-horas`:** Actualizado para apuntar a la fuente canónica correcta.
- **Workflow `registrar-horas`:** Actualizado — git log en ambos repos, fuente canónica correcta.

---

## [3.4] - 2026-04-12

### 🔐 Estabilización Completa del Motor Comercial 2026 — ENERO 2026 con Axarquía

#### Motor de Reglas (`commercial_conditions_service.py`)

- **Fix Crítico — `get_dto_for` devolvía `NaN`:**
  - El método `get_dto_for` retornaba `float('nan')` para segmentos como *Axarquía de Aislamientos* cuyos tramos no tienen `DTO Baleares (%)` en el Excel. El operador `or` de Python no activaba el fallback porque `NaN` es truthy.
  - **Corrección:** Reescrito con `_safe_dto()` + fallback explícito a Territorial, idéntico al patrón de `validate_range`. Ahora retorna siempre un valor en `[0, 100]` o `None`, **nunca NaN**.

- **Fix — `validate_range` zona-de-escalado con NaN:**
  - `next_dto_max = float(next_dto_raw or 0)` fallaba silenciosamente cuando `next_dto_raw` era `NaN` pandas (`float('nan')` no activa `or`). La condición `nan <= dto_solicitado` devolvía `False`, ignorando la zona de escalado.
  - **Corrección:** Sustituido por `_safe_dto(next_dto_raw)` con fallback a `0.0`.

- **Integración de `ENERO 2026 - Con Axarquia.xlsx`:**
  - Nuevo Excel maestro ubicado en `Nuevo/` con **142 reglas**, 6 segmentos, 11 familias y **8 tramos** para *Axarquía de Aislamientos (Distribución)*.
  - El motor carga automáticamente el fichero y cubre todas las combinaciones segmento/familia/territorio.

#### Simulador Comercial (`commercial_conditions_tab.py`)

- **Fix Crítico — `_calculate_conditions` usaba columnas obsoletas:**
  - El simulador referenciaba columnas del formato 2024 (`Importe_min`, `Descuento_max`, etc.) que **no existen** en el Excel 2026 (`Tramo facturación`, `DTO Territorial (%)`, `DTO Baleares (%)`).
  - **Corrección:** Reescritura completa del método usando las columnas reales del Excel 2026 y lógica de tramos correcta.

- **Fix — `AttributeError: btn_refresh` en callbacks de UI:**
  - Tres referencias a `self.btn_refresh.setEnabled()` en métodos del simulador que se ejecutan antes de que el widget esté construido.
  - **Corrección:** Protegidas con `hasattr(self, 'btn_refresh')`.

#### Nuevo Módulo — Calculadora de Producto (`product_calculator_dialog.py`)

- Diálogo independiente para calcular LDM, peso y métricas de paletización de productos individuales y líneas de pedido, con datos en tiempo real de Odoo y CSV maestro Imperbur.

#### Auditoría y QA

- **28.425 pruebas** ejecutadas en 5 rondas de stress testing (random, fuzzing, concurrencia, boundary exhaustivo, cross-validación `get_dto_for`):
  - Ronda 1 (3.000) — Cobertura Random: ✅ 3.000/3.000
  - Ronda 2 (15.284) — 4 tipos de stress: ✅ 15.284/15.284
  - Ronda 3 (9.991) — Semillas nuevas, mutation fuzzing, threading 50×100: ✅ 9.991/9.991
  - Auditoría exhaustiva determinista 13.005 checks × 12 casuísticas: ✅ 0 bugs reales
- **Casuísticas probadas:** dto=0 siempre OK · dto=max exacto · tolerancia FLOAT_TOL · zona escalado AVISO · tramo tope BLOQUEADO estricto · boundary ±0.01 · Axarquía Baleares fallback · segmentos inventados · DTOs negativos/NaN/inf · importes extremos (0€ a 999.999€) · idempotencia × 3 · `get_dto_for` coherente · error-freedom · UTF-8/mayúsculas/territorios edge-case.
- Resultado: **0 bugs en motor**, 0 crashes, 0 NaNs, 0 idempotencias rotas.

#### Scripts de Auditoría (`scripts/`)

- `audit_excel_comercial.py` — Auditoría continua del Excel contra el motor.
- `run_audit_loop.py` — Loop configurable para regresión automática ante cambios del Excel.

---



### Mejora UI/UX — Validador Comercial (`commercial_validator_tab.py`)

- **Visibilidad de Pedidos sin Clasificar:**
  - Corregida la lógica que filtraba y ocultaba los pedidos marcados con `ALERTA_TIPO_CLIENTE`. Ahora todos los pedidos aparecen en la tabla principal.
  - **Identificación Inmediata:** Los pedidos que requieren que el administrador asigne un "Tipo de Cliente" en Odoo ahora se resaltan visualmente con un fondo **púrpura (lavanda)** y el texto de estado **"⚠️ CLASIFICAR"**.
  - Actualizado el panel de detalles inferior para mostrar correctamente la advertencia cuando se seleccionan estos registros.

---

## [3.2] - 2026-03-24

### 🚀 Mejora Mayor — Pestaña "Consulta de Producto" › Dashboard Logístico Mega Pro

#### Panel izquierdo: 5 nuevas secciones operativas

- **📊 Stock en Tiempo Real (por Almacén)**
  - Tabla con columnas: Almacén, Disponible, Reservado, Total en Mano.
  - Fila de **TOTAL** acumulado con fondo oscuro para lectura rápida.
  - Código de color semafórico: 🟢 verde si `disponible > 0`, 🔴 rojo si sin stock.

- **🏢 Proveedores (todos)**
  - Muestra **todos** los `product.supplierinfo` del producto, no solo el principal.
  - Columnas: Nº, Proveedor, Ref. Proveedor, Precio de Compra, Lead Time (días), Cantidad mínima.
  - Ordenados por secuencia de Odoo (prioridad del proveedor).

- **🛒 Órdenes de Compra Pendientes**
  - Consulta directa a `purchase.order.line` para líneas en estado draft/sent/purchase con cantidad pendiente de recibir.
  - Columnas: OC, Proveedor, Pedido, Recibido, **Pendiente** (resaltado), Fecha Prevista, Precio Unitario.
  - Si no hay OC pendientes, muestra mensaje verde "✅ Sin órdenes de compra pendientes".

- **🔄 Reglas de Reaprovisionamiento**
  - Consulta `stock.warehouse.orderpoint` por almacén.
  - Columnas: Almacén, Stock Mínimo, Stock Máximo, Stock Actual, Estado.
  - Estado semafórico: 🔴 "Reponer YA" si `actual < mínimo`, 🟡 "Stock bajo" si `actual < mínimo × 1.25`, 🟢 "OK" en caso contrario.

- **🏷️ Trazabilidad**
  - Muestra el campo `tracking` del producto: Lote / Número de Serie / Sin seguimiento.

#### Tabla de Embalajes (panel derecho): ampliada a 9 columnas
- Añadidas: **Peso Unit. (kg)**, **Peso Palet (kg)**, **Peso Máx. (kg)**.
- Cálculo automático del peso del palet = `qty × peso_unitario`.
- Primera fila (embalaje de palet) resaltada en verde.

#### Panel CSV Maestro: enriquecido con secciones
- **Identificación**: SKU, Nombre, Familia, Sub-familia (CSV).
- **Unidad de Venta**: UM, Presentación, Factor de conversión, Espesor/Alto unitario (mm), Peso por unidad.
- **Paletización**: UPP, Peso palet completo, Tipo de palet, Alturas (capas), Ancho/Largo/Alto del palet.

---

## [3.1] - 2026-03-24

### Nueva Funcionalidad — Pestaña "Consulta de Producto" (`ui/tabs/product_query_tab.py`)

- **Nueva sub-pestaña dentro de "Stock y Artículos":**
  - Permite buscar cualquier producto por SKU (referencia interna) o nombre desde un campo de búsqueda unificado.
  - Recupera datos de forma asíncrona mediante `_ProductQueryWorker` (QThread) para no bloquear el hilo principal.

- **Consulta multi-fuente en paralelo:**
  - **Odoo (fuente primaria):** consulta `product.product` → `product.template` → `product.packaging` → `product.supplierinfo` usando `OdooServiceV2` con `odoorpc`.
  - **CSV maestro Imperbur (Google Sheets, fuente secundaria):** descarga y parsea el CSV de dimensiones/paletización sin dependencias externas (`urllib` + `csv`).
  - Los datos de Odoo tienen prioridad; el CSV enriquece los campos que Odoo no cubre.

- **Ficha técnica HTML detallada (panel izquierdo):**
  - Identificación: SKU, código de barras, UM, categoría.
  - Dimensiones y peso: largo, ancho, alto, peso unitario, volumen.
  - Datos de palet/UPP: UPP, tipo de palet, capas, peso palet completo, dimensiones de palet, remontable, despaletizable.
  - Precios y proveedor: precio de venta, coste estándar, proveedor principal, ref. proveedor, precio de compra, lead time.
  - Notas internas de Odoo (descripción, notas de picking).

- **Tabla de embalajes (panel derecho):**
  - Muestra todos los `product.packaging` del producto ordenados de mayor a menor cantidad.
  - Columnas: Nombre, Cantidad, Código Barras, L/An/Alt en metros (auto-conversión mm→m).

- **Panel de datos CSV Imperbur:**
  - Familia, sub-familia, UM de venta, presentación, UPP-CSV, peso unitario-CSV.

- **Acceso directo a Odoo:**
  - Botón "🌐 Abrir Ficha en Odoo" → abre el template del producto en el navegador.
  - Botón "🔗 Abrir Variante en Odoo" → abre la variante específica (form view).

- **Integración en `InventoryTab`:**
  - Registrada como tercera sub-pestaña ("🔍 Consulta Producto") junto a "Stock" y "Artículos".

### Fix Crítico — Worker Odoo en `product_query_tab.py`

- **Bug:** El método `_safe_exec` del `_ProductQueryWorker` llamaba a `svc.execute(model, method, ...)`, método que **no existe** en `OdooServiceV2`.
- **Síntoma:** `WARNING | 'OdooServiceV2' object has no attribute 'execute'` en cada búsqueda; resultado siempre vacío desde Odoo.
- **Causa raíz:** `OdooServiceV2` usa `odoorpc` directamente a través de `self.odoo.env[model]`, no tiene un método `execute` propio (ese patrón pertenece a `xmlrpc.client` / Odoo 14 RPC estándar).
- **Corrección:** `_safe_exec` ahora llama a `svc._ensure_connected()` y accede a `svc.odoo.env[model].<method>(...)`, idéntico al patrón de todos los demás métodos del servicio (`sync_pickings`, `get_stock_and_reservations`, etc.).

---

## [3.0] - 2026-03-24


### Fix Crítico — Reapertura Accidental de Tickets (`incidence_service.py`)

- **Bug corregido en `resolve_incidence`:**
  - El método carecía del bloqueo `with self.odoo._lock:` que protege el acceso concurrente a la sesión XML-RPC de Odoo.
  - Sin el lock, un hilo de background (p.ej. el refresh periódico del panel de incidencias) podía leer el estado del ticket entre el `_ensure_connected()` y el `write()`, y posteriormente sobreescribir el `stage_id` a un valor anterior, reabriendo el ticket.
  - El método ahora es consistente con el patrón de todos los demás métodos del servicio (`get_ticket_by_so`, `create_incidence`, `get_active_incidences`).
  - Se añade `logger.info` al cierre exitoso para trazabilidad.

### Mejora UI — Validador Comercial (`commercial_validator_tab.py`)

- **Panel de Criterios Detallado (Click en fila):**
  - Al hacer clic en cualquier fila de la tabla de pedidos, se actualiza un `QScrollArea` inferior con un panel HTML que muestra:
    - Desglose de descuentos por línea: % aplicado vs % máximo permitido, con alertas de escalado (⚠️) o bloqueo (🔴).
    - Estado de portes: discrepancia entre valor actual y esperado.
    - Errores de gestión comercial detectados.
  - Implementado mediante `_on_row_clicked` → `_build_detail_html`.

- **Corrección de Claves de Datos:**
  - `'discount'` → `'discounts'` en `_update_kpis` y `_render_table`.
  - `'commercial'` → `'management'` en `_render_table` y `_build_detail_html`.
  - Esto corregía el bug donde los KPIs de "fugas comerciales" siempre mostraban 0 y los tooltips aparecían vacíos.

- **Limpieza de Imports:**
  - Eliminadas importaciones no utilizadas `QGridLayout` y `QSizePolicy`.

---

## [2.9] - 2026-03-23

### Corrección — Creación de Incidencias sin Pedido de Venta vinculado

- **Fix en `logistics_tab.py` → `_manage_incidence`:**
  - Eliminada la llamada redundante a `self.odoo.get_so_name()` que bloqueaba el hilo principal y fallaba para albaranes de movimiento interno o sin SO vinculado directamente.
  - Nuevo flujo de resolución de referencia: (1) `sale_name` del dict de `picking` → (2) campo `origin` como fallback → (3) `QInputDialog` para que el usuario introduzca la referencia manualmente.
  - Si el usuario cancela el diálogo sin introducir referencia, la operación se aborta limpiamente (sin excepción).

- **Fix en `incidence_service.py` → `create_incidence`:**
  - `x_sale_order_id` pasa a ser **opcional**: si el nombre de pedido no se encuentra en `sale.order` de Odoo (p.ej. referencia de origen de movimiento interno), el ticket de Helpdesk se crea igualmente sin ese campo vinculado.
  - Se registra un `logger.warning` cuando el SO no se localiza, para trazabilidad.
  - Se evita pasar `x_sale_order_id: False` al `create` de Odoo; en su lugar, el campo simplemente se omite del dict de valores.

---

## [2.8] - 2026-03-20

### Mejoras — Validador Comercial (UX + Fiabilidad)

- **Confirmación previa a Auto-Fix de Portes (`commercial_validator_tab.py`):**
  - El botón "✨ Auto-Fix Portes" ahora abre un `QMessageBox` de confirmación mostrando los portes actuales y los correctos antes de enviar el cambio a Odoo.
  - Pulsando "No" el pedido no se modifica. Solo al confirmar con "Sí" se ejecuta `apply_portes_correction`.
  - Nuevo método `_confirm_autofix_portes(so_id, expected_portes, actual_portes)` encapsula el flujo.

- **Tooltip enriquecido con % del tramo (`_build_tooltip`):**
  - El tooltip de la columna **Estado** ahora incluye, para cada línea de descuento en zona de escalado (AVISO), la información: `Aplicado X% | Tramo máx Y% (sig. tramo: Z%)`.
  - Para líneas BLOQUEADAS muestra: `Aplicado X% | Máx permitido Y%`.
  - También incluye el resumen de portes si hay discrepancia (`Actual €  |  Correcto €`).

- **Tolerancia float en `validate_range` (`commercial_conditions_service.py`):**
  - Añadida `FLOAT_TOL = 0.01` para evitar falsos positivos por precisión de coma flotante (p.ej. `53.0001 > 53.0` ya no dispara AVISO innecesariamente).
  - Condición actualizada: `if dto_solicitado > dto_max + FLOAT_TOL`.

- **Nuevo test suite `tests/test_validate_range.py`:**
  - 9 escenarios cubriendo: OK exacto, OK inferior, tolerancia float, zona de escalado AVISO, AVISO en frontera exacta, BLOQUEADO sin siguiente tramo, BLOQUEADO por encima del siguiente tramo, sin regla (permisivo), y Baleares. Todos pasan (`EXIT:0`).

---

## [2.7] - 2026-03-19

### Corrección Crítica de Flujo y Estabilidad UI

- **Onboarding y Alta de Clientes (`customer_onboarding_tab.py`):**
  - **Corrección en Persistencia:** Solucionado el problema por el que las solicitudes procesadas con éxito ("alta") permanecían atascadas visualmente como "Pendientes".
  - **Sincronización de Web Leads:** Integrado el atado dinámico del identificador de registro (`uid`) a la interfaz (`self._current_lead_uid`), permitiendo a las funciones como `run_onboarding()` actualizar correctamente la caché del formulario y disparar auto-refrescos.
  - **Robustez de Caché:** Inyectada una política de retrocompatibilidad en `_load_leads_status()` para generar y asignar fechas (`last_update`) al vuelo en registros antiguos que no las poseían, previniendo cuelgues de UI y errores de parseo de fechas.
  - **Alta Directa:** El atajo rápido de alta desde tabla (`_lead_alta_directa`) ahora también incluye adecuadamente la estampa temporal (`last_update`) al guardar el estado, equiparando su comportamiento al del flujo estricto del formulario.

---

## [2.6] - 2026-03-18

*(Documentación retrospectiva de la versión 2.6)*
- Actualizaciones en la arquitectura de la ventana principal y optimización de inicialización del validador comercial.

---

## [2.5] - 2026-03-18

### Correcciones Críticas de Lógica Comercial

- **Fix 1 — Lookup de Cliente en `BUR_GROUP_CLIENTS` (Regla Especial):**
  - Corregida búsqueda de reglas especiales en `rules.BUR_GROUP_CLIENTS` en lugar del dict incorrecto `rules.DISCOUNT_RULES`.
  - Los clientes especiales como *Axarquía de Aislamientos* ahora se detectan correctamente en ambas rutas de validación (`validate_order` y `batch_validate_orders`).

- **Fix 2 — Override de Descuento para Clientes Especiales:**
  - Las reglas `dto_max_hasta_1500_pct` / `dto_max_mas_1500_pct` definidas en `BUR_GROUP_CLIENTS` ahora tienen **prioridad total** sobre la propuesta general del Excel 2026.
  - El flujo de decisión es: Regla Especial de Cliente → (fallback) Propuesta Excel 2026.
  - Implementado en ambos métodos (`validate_order` y `batch_validate_orders`) con label diferenciado en el reporte (`"Regla Especial Cliente"` vs `"Excel 2026"`).

- **Fix 3 — Regla de Gestión `BUR_GROUP_CLIENTS` (Soft Mode para supervisor nulo):**
  - El bloque `Comercial != Supervisor` ahora **no se activa** si el campo `supervisor_id` está vacío en Odoo.
  - Caso de uso cubierto: Directores Territoriales que gestionan clientes BUR directamente sin tener asignado supervisor en el sistema.
  - Condición anterior: `if comercial != supervisor` → **Condición corregida**: `if supervisor is not None and comercial != supervisor`.
  - Fix aplicado en las dos ubicaciones: `batch_validate_orders` (línea ~327) y `validate_order` (línea ~621).

- **Lógica de Portes Mejorada (Shipping Groups Máximo):**
  - El cálculo de `expected_portes` ahora agrega los costes por grupo de envío (`G1_GENERAL`, `G2_XPS`, etc.) en lugar de usar el tramo del grupo predominante en volumen.
  - Esto evita que un grupo de menor coste anule los portes de un grupo más restrictivo.

---

## [2.4] - 2026-03-18

### Añadido
- **Reglas Axarquía de Aislamientos (108 SKUs actualizados):**
  - Implementación completa del escalado de descuentos para el cliente `AXARQUIA_DE_AISLAMIENTOS_DISTRIBUCION` en las familias: `ACÚSTICA`, `ANTI IMPACTO (NO SOUND)`, `AIR-BUR TERMIC` (Excl. CM), `AIR-BUR TERMIC CM` e `IMPERMEABILIZANTES`.
  - El motor de descuentos ahora resuelve correctamente los 8 tramos (6.000€, 4.000€, 3.000€, 2.500€, 2.000€, 1.500€, 1.000€, < 1.000€) para este cliente especial de Andalucía.
  - Datos extraídos y validados contra el Excel oficial `ENERO 2026 - Con Axarquia.xlsx` y el PDF `Escalado descuentos Andalucía-Axarquía 2026.pdf`.
- **Nueva Pestaña 🚛 Políticas Transporte:**
  - Interfaz de consulta interactiva de las nuevas condiciones comerciales 2026 (`Propuesta_Rangos_2026`).
  - Buscador en tiempo real por Segmento, Familia o tramo de base imponible.
  - Estadísticas dinámicas: número de reglas, segmentos y familias cargadas.
  - Filtro por ComboBox de Segmento para acceso rápido.
- **Reorganización Pestaña Alta Clientes:**
  - Las sub-pestañas **Web** y **Solicitudes** ahora están integradas dentro de Alta Clientes.
  - Eliminada la pestaña independiente "Web Solicitudes Stats" del menú principal para evitar duplicidad.

### Mejoras / Correcciones v2.4
- **Fix: Detección de dirección de entrega alternativa (Solicitudes Web):**
  - Corregida la condición en `on_lead_selected` de `customer_onboarding_tab.py` que impedía mostrar los campos de entrega cuando el cliente indicaba una dirección distinta a la fiscal.
  - El CSV de Google Forms devuelve `'No'` (con N mayúscula), pero el código comparaba contra `"NO"/"DIFERENTE"/"OTRA"` sin normalizar. Ahora se aplica `.upper()` antes de la comparación: `if "NO" in sg(21).upper()` resuelve el problema con cualquier capitalización.
- **Credenciales Odoo actualizadas:** Migración a cuenta oficial `gabriela.rojas@bur2000.com` (configuación en `.env`). La app se autentica ahora en tiempo real con los permisos completos del perfil comercial.
- **Corrección NameError `List`:** Añadido `from typing import List, Dict` en `commercial_service.py` (Python 3.9 necesita tipado explícito en las anotaciones de métodos).
- **Import TransportPoliciesTab:** Corregida la ruta de importación en `main.py` para evitar `ModuleNotFoundError` al arrancar.
- **Tema UI (BUR Colors):** Eliminadas referencias a `BUR.text_secondary` (atributo inexistente). Sustituido por `BUR.accent` en `transport_policies_tab.py`.
- **Familia ALMACENES_E_INSTALADORES_GAMA_SOUND:** Validado que los SKUs de gama SOUND Parquet (21.xxx) reciben correctamente las condiciones de la tabla Parquetistas (3.000€/1.500€/<1.500€) con Baleares diferenciado.

### Mantenimiento y Limpieza v2.4 (2026-03-18)

- **Versión de ventana:** Actualizado título de `v2.3` a `v2.4` en `main.py`.
- **Tab huérfano eliminado:** `web_stats_tab.py` — estaba en disco pero ningún módulo lo importaba ni registraba en el menú principal. Su funcionalidad había sido absorbida por `customer_onboarding_tab.py`.
- **Import residual eliminado:** `from .web_stats_tab import WebStatsTab` en `customer_onboarding_tab.py` línea 16 — causaba `ModuleNotFoundError` al arrancar tras la eliminación del tab.
- **Scripts de debug eliminados:** `check_master_21.py` y `find_line.py` de la raíz del proyecto.
- **Exports de prueba eliminados:** 2 PDFs de albaranes antiguos de Marzo 2026 en `exports/`.
- **Archivos temporales eliminados:** `Cliente/docx_text.txt`, `Cliente/xlsx_contactos.txt`, `Cliente/xlsx_form.txt` (artefactos de extracción del análisis de documentos).
- **Carpeta `_archive/` eliminada:** Contenía backups obsoletos y el CHANGELOG antiguo.
- **Cache de tests eliminado:** `tests/__pycache__/`.
- **Verificación final:** 14/14 módulos de `ui.tabs` cargan sin errores.

---

## [2.3] - 2026-03-18

### Añadido
- **Módulo de Reglas Comerciales v2 (Específico SKU):**
  - Implementación de matriz granular por SKU con más de 2500 referencias mapeadas.
  - Diferenciación automática entre Tipos de Cliente (Especialistas PYL, Generalistas, Almacenes).
  - Nuevo motor de búsqueda de descuentos basado en familias y grupos de SKU (`commercial_rules_v2.json`).
- **Reportes de Auditoría de Sistemas:**
  - Generación automática de reportes PDF para pruebas de conexión e integridad de datos alojados en `/exports`.

### Mejoras / Correcciones v2.3
- **Actualización de Credenciales Odoo:** Migración segura a la cuenta oficial de **Gabriela Rojas** para sincronización en tiempo real.
- **Limpieza de Base de Datos:** Eliminación del esquema `commercial_rules.json` (V1) para evitar discrepancias y asegurar el uso de la V2.
- **Optimización de Servicios:** Refactorizado del `RulesService` y el motor de mapeo principal para mejorar el rendimiento del simulador.
- **Validación de Portes:** Ajuste en el cálculo de portes automáticos para pedidos Península/Baleares bajo el nuevo esquema.

---

## [2.2] - 2026-03-13

### Añadido

- **Módulo de Alta de Clientes (Onboarding):**
  - Interfaz unificada para la creación y actualización de clientes directamente desde la aplicación.
  - **Normalización Inteligente:** Aplicación automática de las "Reglas de Bur 2000" (Mayúsculas, eliminación de acentos, formato de dirección).
  - **Verificación de NIF:** Búsqueda en tiempo real en Odoo para detectar duplicados antes de procesar el alta.
  - **Autocompletado Geográfico:** Búsqueda automática de Ciudad y Provincia al introducir el Código Postal basada en el histórico de la base de datos.
  - **Gestión Documental:** Soporte para adjuntar archivos (NIF/VIES) que se suben automáticamente al Chatter de Odoo.
  - **Integración IBAN:** Validación de formato y creación automática de cuentas bancarias para formas de pago domiciliadas.
- **Módulo de Stock y Artículos (Avanzado):**
  - **Visibilidad Multi-Almacén:** Comparativa en tiempo real de disponibilidad entre Abrera, Silla y Pinto.
  - **Gestión de Reservas:** Desglose detallado de qué pedidos están reteniendo el stock (Move Lines).
  - **Maestro de Dimensiones:** Integración con base de datos externa para calcular pesos y volúmenes de carga automáticamente.
- **Módulo de Analíticas y Business Intelligence (Fase 2):**
  - Panel principal con gráficos de tendencia de ventas y KPIs locales.
  - **Predicciones con Machine Learning:** Implementación de un modelo Random Forest para predecir precios finales basados en el histórico.
  - **Generación de Datos Sintéticos:** Capacidad para generar pedidos realistas mediante `Faker` para entrenamiento de IA.

### Mejoras / Correcciones v2.2

- **Corrección de Temas UI:** Corregido un fallo de importación en el módulo de Onboarding que impedía el uso de la paleta de colores corporativa.
- **Migración a PySide6:** Homogeneización de librerías para asegurar compatibilidad total con el entorno de ejecución oficial.

## [2.1.1] - 2026-03-11

### Mejoras / Correcciones v2.1.1

- **Corrección de reglas en Simulador y Control Comercial:**
  - Añadidas las familias `SOUND` y `SUELOS` que no estaban presentes por defecto en los perfiles *Almacenes Especialistas (PYL)* y *Almacenes Generalistas*, lo cual provocaba que el pedido fuese bloqueado erróneamente al aplicarles 0% de descuento.
  - Asignado el `TERMICO_XPS` correctamente en el motor de mapeo principal, previamente asociado sólo a `TERMICO`, lo cual dejaba al XPS sin sus topes específicos del 55%.
  - Asignadas las familias especiales `PYL` y `CUBIERTAS` al motor de reglas para que los clientes de tipo *Empresas Instaladoras* disfrutasen de los correctos topes de volumen.
  - Implementación de un bloque de seguridad "default" en el JSON, garantizando que futuras gamas no tipificadas usen una tabla de contingencia y nunca se bloqueen al 0%.
  - **Independencia en Portes XPS:** Separación de la gama Térmico XPS de Térmico estándar. Se exige un mínimo de pedido de 3.000€ para portes pagados en XPS, conservando los 1.500€ para el resto del Térmico. Las tarifas para tramos inferiores se calculan con el escalado G1/G2 base estipulado.

[... resto del changelog abreviado ...]
