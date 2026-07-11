---
name: bur2000-project-separation
description: >
  Skill de separación estricta entre proyectos BUR2000_app y Gabriela.
  Activa cuando hay riesgo de mezclar código, imports, rutas o convenciones
  de un proyecto en el otro. Los proyectos son PARALELOS e INDEPENDIENTES.
---

# 🚧 Separación Estricta: BUR2000_app vs Gabriela

> **Regla Absoluta:** Estos dos proyectos son INDEPENDIENTES.
> Nunca importar, copiar ni referenciar código entre ellos.
> Nunca asumir que una convención de uno aplica en el otro.

---

## 📁 Rutas de Proyecto — NO MEZCLAR

| Proyecto | Ruta raíz | Finalidad |
|----------|-----------|-----------|
| **BUR2000_app** | `C:\Users\User\Desktop\Bur2000_app\` | WMS + Logística + Dashboard ejecutivo |
| **Gabriela** | `C:\Users\User\Desktop\Bur2000_v2\Gabriela\` | CRM Comercial (motor descuentos, validador, calculadora) |

---

## ⚠️ Diferencias Críticas (NO asumir que son iguales)

| Aspecto | BUR2000_app | Gabriela |
|---------|-------------|----------|
| **BD** | PostgreSQL (Docker) | SQLite local (`app/db/clientes_local.db`) |
| **ORM** | `get_conn()` / `get_service_conn()` | `odoorpc` directo en servicios |
| **Odoo client** | `xmlrpc.client` + patrón propio | `odoorpc` con `svc.odoo.env[model]` |
| **UI base** | `BaseBurTab` + lazy loading | Sin clase base — tabs independientes |
| **`ui/components/`** | Widgets ricos y reutilizables | **VACÍO** (solo `__init__.py`) |
| **Arranque** | `Arrancar_Bur2000.bat` → `app.py` | `Gabriela.bat` → `app/main.py` |
| **Tests** | `Bur2000_app/tests/` | `Bur2000_v2/Gabriela/tests/` |
| **Python env** | `Bur2000_app/miniconda/` | `Bur2000_v2/Gabriela/miniconda/` |

---

## 🚫 Acciones Prohibidas

- ❌ Importar desde `Bur2000_app` dentro de código de Gabriela
- ❌ Copiar `get_conn()` / `get_service_conn()` de BUR2000_app a Gabriela (no existe PostgreSQL allí)
- ❌ Asumir que un fix en `commercial_service.py` de Gabriela afecta a BUR2000_app (son archivos distintos)
- ❌ Correr `pytest` de Gabriela con el miniconda de BUR2000_app o viceversa
- ❌ Referenciar rutas relativas `../../Bur2000_app/` desde Gabriela

---

## ✅ Cómo operar correctamente

**Antes de cada tarea, confirmar en qué proyecto estás:**

```python
# ¿Estoy en Gabriela?
# → El archivo está en: C:\Users\User\Desktop\Bur2000_v2\Gabriela\...
# → La BD es SQLite, odoorpc, miniconda propia

# ¿Estoy en BUR2000_app?
# → El archivo está en: C:\Users\User\Desktop\Bur2000_app\...
# → La BD es PostgreSQL, xmlrpc, miniconda propia
```

**Si el usuario pide algo en Gabriela:**  
→ Trabajar SÓLO en `Bur2000_v2\Gabriela\`  
→ Leer `_agents/MEMORY.md` de Gabriela (no el de BUR2000_app)  
→ Ejecutar tests de Gabriela con `Bur2000_v2\Gabriela\miniconda\python.exe`

**Si el usuario pide algo en BUR2000_app:**  
→ Trabajar SÓLO en `Bur2000_app\`  
→ Leer `.agent/MEMORY.md` de BUR2000_app  
→ Ejecutar tests de BUR2000_app con `Bur2000_app\miniconda\python.exe`

---

## 📝 Señales de Confusión (alerta roja)

Si detectas cualquiera de estos patrones, DETENERSE y confirmar con el usuario:

- Un import que cruza rutas de proyecto
- Un `sys.path.insert` que apunta a la raíz del otro proyecto
- Una referencia a `get_conn()` en código de Gabriela
- Una referencia a `odoorpc` en código de BUR2000_app (si no está en ese stack)
- Un `pytest` que colecta tests de ambos proyectos a la vez
