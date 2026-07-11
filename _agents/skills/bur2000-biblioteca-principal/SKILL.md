---
name: bur2000-biblioteca-principal
description: >
  Skill para indicar a los agentes que existe una biblioteca externa con +1000 herramientas,
  prompts y conocimientos en C:\Users\User\Desktop\BIBLIOTECA-Principal. Usar cuando se requiera
  un skill avanzado o de referencia que no esté en el repositorio actual.
---

# 📚 Biblioteca Principal de Skills

> **Ubicación Física:** `C:\Users\User\Desktop\BIBLIOTECA-Principal`

Tanto el proyecto WMS (BUR2000) como Gabriela cuentan con una biblioteca centralizada de recursos para agentes de IA, que vive en un repositorio estrictamente separado. Contiene más de 1000 skills organizados por temática, herramientas avanzadas y material de referencia (docs, APIs, prompts).

## 🎯 ¿Cuándo usarla?

Si te piden una tarea compleja y notas que falta contexto, librerías, o herramientas que no están en tu carpeta local de `_agents/skills/` (o `.agent/skills/`), **antes de improvisar**, debes consultar esta biblioteca.

- Si te falta experiencia en una tecnología (ej: automatización, IA, web scraping).
- Si necesitas plantillas o prompts del sistema base.

## 🔍 ¿Cómo buscar en la Biblioteca?

1. **Catálogo de Skills:** Lee el archivo `C:\Users\User\Desktop\BIBLIOTECA-Principal\skills\CATALOG.md` o el JSON `skills_index.json` para ver el índice.
2. **Exploración de Carpetas:** Explora `C:\Users\User\Desktop\BIBLIOTECA-Principal\skills\skills\` (está dividido por categorías).
3. **Estructuras y Prompts:** Revisa `C:\Users\User\Desktop\BIBLIOTECA-Principal\estructuras-de-prompts\` para ver plantillas de agentes.

## ⚠️ Reglas de Uso

1. **NO COPIAR FÍSICAMENTE:** Lee el archivo del skill directamente desde el Escritorio usando tus herramientas (como `view_file` o `grep`) y aplica las instrucciones en el código. No copies el archivo `.md` a tu repositorio activo, así evitamos duplicidades.
2. **SOLO LECTURA:** Trabajas como consumidor de la biblioteca. No modifiques los skills de la biblioteca a menos que el usuario explícitamente pida "actualiza este skill en la biblioteca".
