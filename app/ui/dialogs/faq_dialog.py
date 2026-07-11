from PySide6.QtWidgets import QDialog, QVBoxLayout, QTextBrowser, QPushButton, QHBoxLayout, QLabel, QFrame
from PySide6.QtCore import Qt
import bur2000_theme

class FAQDialog(QDialog):
    def __init__(self, parent=None, mode="faq"):
        super().__init__(parent)
        self.mode = mode
        if mode == "faq":
            self.setWindowTitle("Guía de Ayuda Completa - Gabriela Rojas Pro")
        else:
            self.setWindowTitle("Historial de Versiones - Gabriela Rojas Pro")
        self.resize(850, 700)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Header (Branded)
        header = QFrame()
        header.setFixedHeight(70)
        header.setStyleSheet(f"background-color: {bur2000_theme.BUR.primary};")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(25, 0, 25, 0)
        
        if self.mode == "faq":
            title = QLabel("❓ Centro de Ayuda Bur 2000")
        else:
            title = QLabel("📜 Historial de Versiones")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: white;")
        h_layout.addWidget(title)
        h_layout.addStretch()
        
        v_label = QLabel("v3.4 Enterprise")
        v_label.setStyleSheet("color: rgba(255,255,255,0.7); font-weight: bold;")
        h_layout.addWidget(v_label)
        
        layout.addWidget(header)
        
        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        if self.mode == "faq":
            self.browser.setHtml(self._get_help_content())
        else:
            self.browser.setHtml(self._get_changelog_content())
        self.browser.setStyleSheet("""
            QTextBrowser {
                background-color: white;
                border: none;
                padding: 30px;
                font-family: 'Segoe UI', sans-serif;
            }
        """)
        layout.addWidget(self.browser)
        
        # Bottom Bar
        bottom = QFrame()
        bottom.setFixedHeight(60)
        bottom.setStyleSheet(f"background-color: {bur2000_theme.BUR.background}; border-top: 1px solid {bur2000_theme.BUR.border};")
        b_layout = QHBoxLayout(bottom)
        b_layout.setContentsMargins(25, 0, 25, 0)
        
        attr = QLabel("Desarrollado por Oscar Piedra Osuna")
        attr.setStyleSheet(f"color: {bur2000_theme.BUR.muted}; font-size: 11px; font-style: italic;")
        b_layout.addWidget(attr)
        
        b_layout.addStretch()
        
        btn_close = QPushButton("Cerrar Guía")
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.setMinimumWidth(120)
        btn_close.setStyleSheet(f"""
            QPushButton {{
                background-color: white;
                border: 1px solid {bur2000_theme.BUR.primary};
                color: {bur2000_theme.BUR.primary};
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {bur2000_theme.BUR.background};
            }}
        """)
        btn_close.clicked.connect(self.close)
        b_layout.addWidget(btn_close)
        
        layout.addWidget(bottom)
 
    def _get_help_content(self):
        primary = bur2000_theme.BUR.primary
        teal = bur2000_theme.BUR.secondary
        
        return f"""
        <style>
            h2 {{ color: {primary}; border-bottom: 2px solid {primary}; padding-bottom: 5px; margin-top: 25px; }}
            h3 {{ color: {teal}; margin-top: 20px; }}
            b {{ color: {primary}; }}
            .tip {{ background-color: #f0fdfa; border-left: 4px solid {teal}; padding: 15px; margin: 15px 0; }}
            .warn {{ background-color: #fffbeb; border-left: 4px solid #f59e0b; padding: 15px; margin: 15px 0; }}
            ul {{ line-height: 1.6; }}
            li {{ margin-bottom: 8px; }}
        </style>
 
        <h1>📘 Manual de Operaciones - Gabriela Rojas Pro</h1>
        <p>Bienvenido al asistente inteligente de Bur 2000. Esta herramienta centraliza la logística, el control comercial y la gestión de expedientes.</p>
 
        <h2>🚛 Módulo de Logística (Carga y Envío)</h2>
        <p>Gestión avanzada de albaranes y entregas en tiempo real.</p>
        <ul>
            <li><b>Visibilidad Exclusiva:</b> El filtro de almacenes muestra únicamente los centros operativos (Abrera, Pinto, Valencia).</li>
            <li><b>Visibilidad Pinto (MAD3)</b>: Se incluyen albaranes de salida (OUT), traspasos internos (INT) y estados en borrador (DRAFT).</li>
            <li><b>Tablas Ordenables</b>: Pulsa en las cabeceras de columnas como <i>Estado</i>, <i>Origen</i>, o <i>Almacén</i> para ordenar automáticamente alfabéticamente la tabla entera.</li>
            <li><b>Filtros Avanzados</b>: Selecciona un estado específico o entradas/salidas para centrarte sólo en lo urgente desde la barra de arriba.</li>
            <li><b>Emailing Inteligente</b>: El botón de enviar correo detecta si el pedido es de Pinto y te permite elegir entre <i>"Envío Logística"</i> o <i>"Recoge Cliente"</i> actualizando el texto automáticamente.</li>
        </ul>
 
        <h2>🎫 Módulo de Incidencias (Helpdesk)</h2>
        <ul>
            <li><b>Filtros Avanzados</b>: Ahora puedes filtrar por 📍 Almacén, 📅 Rango de Fechas y 👤 Responsable Asignado.</li>
            <li><b>Asignación Live</b>: Cambia el responsable del ticket directamente desde la tabla (Administración, Logística Interna BUR, Logística Transporte Externo, Calidad); se guardará en Odoo al instante y coinciden con sus equipos respectivos.</li>
            <li><b>Trazabilidad Rápida</b>: El botón de Chat/Historial presenta ahora en su cabecera un resumen destacado mostrando el motivo original de la incidencia.</li>
            <li><b>Control de Adjuntos</b>: Para evitar errores del servidor, el tamaño total de las fotos está limitado a <b>5MB</b>. Gabriela te avisará si lo superas.</li>
        </ul>
 
        <h2>🖱️ Optimización de Sistema y Personalización</h2>
        <p>Ajustes profundos del sistema operativo directamente desde Gabriela.</p>
        <ul>
            <li><b>Limpieza Profunda (Temp & Bin):</b> Borra archivos temporales de Windows y vacía la papelera de reciclaje de forma segura y silenciosa (sin ventanas de error).</li>
            <li><b>Gestor de Cursores (Bibata):</b> Instala y aplica automáticamente el cursor premium 'Bibata Modern Classic' en Windows a nivel de registro del sistema.</li>
            <li><b>Wallpapers IA (Nivel Dios):</b> Generación y aplicación automática de fondos de escritorio ultra-realistas y cyberpunk sin necesidad de salir de la aplicación.</li>
        </ul>

        <h2>📈 Control Comercial</h2>
        <ul>
            <li><b>Estado Emitido:</b> Este panel ahora se centra exclusivamente en pedidos ya "Emitidos" (Sent) al cliente para validar sus condiciones finales.</li>
            <li><b>Validación Activa Instantánea:</b> El sistema evalúa portes y descuentos extraídos de la central en menos de un segundo por todos los clientes en bloque.</li>
            <li><b>Tarifas y Reglas Propias:</b> Configura márgenes, condiciones especiales y reglas G1/G2 cómodamente desde las opciones superiores sin depender de Excel.</li>
            <li><b>Distribuidores VIP y Group:</b> Lógica especializada de descuentos (55%/60%) y validación de Supervisor.</li>
            <li><b>Control XPS:</b> Bloqueo estricto por paletización incompleta, techo de descuento del 55% y cálculo indepediente de portes (3.000€ mínimo).</li>
            <li><b>Simulador Económico:</b> Herramienta para probar y calcular la factura antes de aplicarla a presupuestos vivos en la cuenta del cliente.</li>
            <li><b>Clientes Satélite (150*):</b> Validador nativo inteligente. Las delegaciones con prefijo 150 absorben y evalúan automáticamente los descuentos contra sus matrices.</li>
        </ul>

        <h2>🔐 Motor Comercial ENERO 2026</h2>
        <p>Motor de reglas de descuento completamente refactorizado y certificado mediante auditoría de <b>28.425 pruebas</b>.</p>
        <ul>
            <li><b>Excel Maestro 2026:</b> Las condiciones se leen directamente del fichero <i>ENERO 2026 - Con Axarquia.xlsx</i> (142 reglas, 6 segmentos, 11 familias). No requiere sincronización manual.</li>
            <li><b>Tramos y Escalado:</b> El motor aplica automáticamente la lógica de tramos por importe (ej. &lt;1.500€ → 47%, 1.500€ → 50%, 3.000€ → 52%, 6.000€ → 55%). Si el descuento solicitado supera el tramo actual pero cabe en el siguiente, se devuelve <b>AVISO</b> en lugar de bloqueo directo.</li>
            <li><b>Axarquía de Aislamientos:</b> Segmento con <b>8 tramos</b> específicos. En territorios Baleares, el motor hace <i>fallback automático</i> al DTO Territorial (no hay DTO Baleares en el Excel para este segmento).</li>
            <li><b>Tolerancia flotante (FLOAT_TOL=0,01%):</b> Un descuento de 50,009% con máximo 50% se acepta como OK. Esto evita falsos bloqueos por errores de precisión de coma flotante.</li>
            <li><b>Simulador de Condiciones:</b> Pestaña «🔐 Condiciones Comerciales» para probar combinaciones de segmento/familia/territorio/importe/descuento antes de cerrar un pedido.</li>
            <li><b>Scripts de Regresión:</b> <code>scripts/audit_excel_comercial.py</code> y <code>scripts/run_audit_loop.py</code> disponibles para verificar el motor si el Excel maestro se actualiza.</li>
        </ul>
        <div class='tip'>
            <b>💡 ¿Cuándo aparece AVISO vs BLOQUEADO?</b><br/>
            <b>AVISO</b>: el descuento supera el máximo del tramo actual pero entraría en el tramo inmediatamente superior (zona de escalado). El pedido puede continuar con aprobación.<br/>
            <b>BLOQUEADO</b>: el descuento supera incluso el máximo del tramo más alto disponible para ese segmento/familia. Requiere intervención del supervisor.
        </div>

        <h2>🤝 Alta y Onboarding de Clientes</h2>
        <ul>
            <li><b>Normalización Automática:</b> El sistema convierte nombres y direcciones a mayúsculas sin acentos (Estándar Odoo Bur 2000) para evitar duplicados y errores manuales.</li>
            <li><b>Búsqueda por NIF/CIF:</b> Detecta instantáneamente si un cliente ya existe antes de crearlo, permitiendo elegir entre "Alta" o "Actualización".</li>
            <li><b>Inteligencia Geo-Postal:</b> Al introducir el Código Postal, Gabriela autocompleta la Ciudad y la Provincia basándose en el histórico de la base de datos.</li>
            <li><b>Gestión de Documentación:</b> Adjunta directamente el PDF del NIF o certificado VIES; el sistema lo subirá automáticamente como adjunto al registro del cliente en Odoo.</li>
            <li><b>Direcciones de Entrega:</b> Soporte para obras con campos específicos de logística (Acceso tráiler, medios de descarga) que se guardan como notas internas para transportistas.</li>
        </ul>

        <h2>Inventario y Stock</h2>
        <p>Consulta en tiempo real la disponibilidad de productos en todos los almacenes operativos.</p>
        <ul>
            <li><b>Stock Reservado:</b> Identifica por qué un producto no está disponible viendo los pedidos asignados que lo están reteniendo.</li>
            <li><b>Pesos Totales:</b> Gabriela calcula automáticamente el peso en KG por ubicación para facilitar la planificación de cargas.</li>
            <li><b>Búsqueda por SKU:</b> Localiza rápidamente referencias específicas para checking de picking.</li>
        </ul>

        <h2>🔍 Consulta de Producto</h2>
        <p>Busca la ficha técnica completa de cualquier artículo directamente desde la pestaña <b>Stock y Artículos → Consulta Producto</b>.</p>
        <ul>
            <li><b>Búsqueda flexible:</b> Introduce el SKU (referencia interna) o cualquier parte del nombre del producto y pulsa <i>Buscar</i> o la tecla Enter.</li>
            <li><b>Ficha técnica:</b> Verás de un vistazo el código de barras, UM, categoría, dimensiones (L/An/Alt), peso unitario, volumen y datos completos de paletización (UPP, tipo de palet, capas, remontable, peso palet lleno).</li>
            <li><b>Precio y proveedor:</b> La ficha incluye el precio de venta, el coste estándar y los datos del proveedor principal (nombre, referencia, precio de compra y lead time).</li>
            <li><b>Embalajes:</b> En el panel derecho aparece la tabla de todos los formatos de embalaje (<i>product.packaging</i>) del producto, con sus dimensiones reales.</li>
            <li><b>Datos CSV Imperbur:</b> Si el producto está en el maestro de Imperbur (Google Sheets), se muestra también la familia, sub-familia y la paletización del CSV como referencia cruzada.</li>
            <li><b>Abrir en Odoo:</b> Usa los botones <i>"🌐 Abrir Ficha en Odoo"</i> o <i>"🔗 Abrir Variante en Odoo"</i> para ir directamente al registro en el navegador.</li>
        </ul>
        <div class='tip'>
            <b>💡 TIP:</b> Si buscas por SKU exacto (ej: <i>16.001</i>) el resultado es inmediato. Para búsquedas por nombre parcial (ej: <i>reticulado</i>) Gabriela mostrará la primera coincidencia encontrada en Odoo.
        </div>

        <h2>📦 Pedidos y Artículos</h2>
        <p>Vista especializada que desglosa cada pedido pendiente en sus componentes individuales.</p>
        <ul>
            <li><b>Comparativa de Almacenes:</b> Consulta en una sola línea el stock disponible en Abrera, Silla y Pinto para cada artículo del pedido.</li>
            <li><b>Manual de Dimensiones:</b> El sistema cruza datos de Odoo con el maestro de dimensiones (Ancho, Largo, Espesor) para cubicar expediciones rápidamente.</li>
            <li><b>Paletización:</b> Visualiza cuántas unidades se incluyen por palet directamente en la tabla.</li>
        </ul>

        <div class='tip'>
            <b>💡 TIP de Productividad:</b> Pulsa el botón superior "📋 Ver Logs" si necesitas registrar errores ocultos de cara a servicio técnico.
        </div>
 
        <h2>📊 Analíticas y Machine Learning</h2>
        <p>Toma de decisiones impulsada por inteligencia artificial y visualización de datos.</p>
        <ul>
            <li><b>Gráficos Interactivos:</b> Visualiza las tendencias de ventas, portes, márgenes y categorías de productos mes a mes.</li>
            <li><b>Predicciones Inteligentes:</b> Un modelo de Machine Learning (Random Forest) analiza el histórico para predecir precios y volúmenes de demanda para futuros pedídos con alta precisión.</li>
            <li><b>Generador de Datos Sintéticos:</b> Permite poblar la base de datos local con cientos de pedidos ficticios basados en el comportamiento real, ideal para entrenar a la IA o hacer pruebas sin afectar a Odoo.</li>
        </ul>

        <h2>🤖 Motores de Inteligencia</h2>
        <p>Gabriela integra múltiples opciones según la necesidad:</p>
        <ul>
            <li><b>Groq</b>: Velocidad extrema (Llama 3). Ideal para uso diario.</li>
            <li><b>Ollama</b>: Privacidad total (Local). Funciona sin internet.</li>
            <li><b>OpenAI/Gemini</b>: Potencia máxima para análisis complejos.</li>
        </ul>


        <h2>📋 Editor de Políticas</h2>
        <p>Administra las reglas del negocio sin tocar código.</p>
        <ul>
            <li><b>Editar Precios</b>: Cambia los costes G1 y G2 por región. Se aplican al instante tras pulsar Guardar.</li>
            <li><b>PDF Corporativo</b>: Genera un documento PDF profesional con el diseño de Bur 2000 para compartir las nuevas tarifas con la red comercial.</li>
        </ul>

        <h2>⚙️ Ajustes y Configuración</h2>
        <p>Asegúrate de que todo esté en verde.</p>
        <ul>
            <li><b>Conexión Odoo</b>: Verifica URL, Base de Datos y Credenciales. Pulsa "Probar Conexión" para validar.</li>
            <li><b>API Keys</b>: Introduce tus claves de Groq u otros proveedores aquí.</li>
        </ul>

        <div class='warn'>
            <b>⚠️ Solución de Problemas:</b>
            <br/>- Si la app no arranca tras una actualización, ejecuta <b>Gabriela.bat</b> para instalar nuevas librerías.
            <br/>- Si ves "Login required" persistente, revisa tu contraseña en Ajustes.
            <br/>- Si los PDFs no se abren, verifica que tienes instalado un lector de PDF.
            <br/>- Si el cursor Bibata no se aplica a la primera, usa el script de reinstalación `reinstall_cursor_fix.py`.
        </div>

        <p style='text-align: center; margin-top: 40px; border-top: 1px solid #eee; padding-top: 20px;'>
            <b>Software desarrollado para Bur 2000 por Oscar Piedra Osuna</b>
        </p>
        """

    def _get_changelog_content(self):
        primary = bur2000_theme.BUR.primary
        teal = bur2000_theme.BUR.secondary
        
        return f"""
        <style>
            h2 {{ color: {primary}; border-bottom: 2px solid {primary}; padding-bottom: 5px; margin-top: 25px; }}
            h3 {{ color: {teal}; margin-top: 20px; }}
            .ver {{ font-weight: bold; background: {primary}; color: white; padding: 2px 8px; border-radius: 4px; }}
            ul {{ line-height: 1.6; margin-bottom: 20px; }}
            li {{ margin-bottom: 5px; }}
        </style>

        <h1>📜 Historial de Versiones - Gabriela Rojas Pro</h1>
        
        <h2><span class='ver'>v3.4</span> - 🔐 Estabilización Motor Comercial 2026 + Auditoría 28k</h2>
        <p><b>Fecha:</b> 12 de Abril, 2026</p>
        <ul>
            <li><b>Fix crítico get_dto_for:</b> El método retornaba NaN silencioso para segmentos sin DTO Baleares (Axarquía). Corregido con _safe_dto() y fallback explícito a Territorial.</li>
            <li><b>Fix validate_range zona-escalado:</b> next_dto_max con valor NaN de pandas no activaba el bloqueo correcto. Sustituido por _safe_dto() con fallback a 0.0.</li>
            <li><b>Fix simulador _calculate_conditions:</b> Reescritura completa usando columnas del Excel 2026 reales (<i>Tramo facturación</i>, <i>DTO Territorial (%)</i>, <i>DTO Baleares (%)</i>).</li>
            <li><b>Fix AttributeError btn_refresh:</b> Callbacks del simulador protegidos con hasattr() para evitar crash en inicialización.</li>
            <li><b>Integración ENERO 2026 con Axarquía:</b> 142 reglas, 6 segmentos, 11 familias, 8 tramos para Axarquía de Aislamientos.</li>
            <li><b>Nueva Calculadora de Producto:</b> Diálogo <i>product_calculator_dialog.py</i> para calcular LDM, peso y paletización por SKU y pedido con datos de Odoo en tiempo real.</li>
            <li><b>Scripts de auditoría:</b> audit_excel_comercial.py + run_audit_loop.py para regresión automática.</li>
            <li><b>Resultado QA:</b> 28.425 pruebas — 0 bugs reales — 0 crashes — 0 NaNs.</li>
        </ul>

        <h2><span class='ver'>v3.3</span> - Mejora UI/UX — Validador Comercial</h2>
        <p><b>Fecha:</b> 26 de Marzo, 2026</p>
        <ul>
            <li><b>Visibilidad de Pedidos sin Clasificar:</b> Corregida la lógica que filtraba y ocultaba los pedidos marcados con <code>ALERTA_TIPO_CLIENTE</code>. Ahora todos los pedidos aparecen en la tabla principal.</li>
            <li><b>Identificación Inmediata:</b> Los pedidos que requieren clasificación manual se resaltan con un fondo <b>púrpura (lavanda)</b> y el estado <b>"⚠️ CLASIFICAR"</b>.</li>
            <li><b>Detalles Inferiores:</b> El panel de detalles ahora muestra correctamente la advertencia para registros no clasificados.</li>
        </ul>

        <h2><span class='ver'>v3.2</span> - Dashboard Logístico Mega Pro — Consulta de Producto</h2>
        <p><b>Fecha:</b> 24 de Marzo, 2026</p>
        <ul>
            <li><b>Stock en Tiempo Real:</b> Desglose detallado por Almacén (Disponible/Reservado/Total) con semáforo inteligente y fila de totales sumada automáticamente.</li>
            <li><b>Gestión de Proveedores:</b> Acceso a la matriz completa de proveedores (<i>product.supplierinfo</i>) con referencias, precios de compra y lead times.</li>
            <li><b>Órdenes de Compra:</b> Visibilidad directa de pedidos pendientes de recibir desde Odoo, resaltando las cantidades pendientes.</li>
            <li><b>Reaprovisionamiento:</b> Integración de reglas de stock mínimo/máximo con estados de alerta: 🔴 "Reponer YA", 🟡 "Stock bajo", 🟢 "OK".</li>
            <li><b>Cálculo de Cargas:</b> Pesos unitarios y de palet calculados al vuelo en la tabla de embalajes para facilitar la logística.</li>
            <li><b>Trazabilidad:</b> Consulta instantánea del tipo de seguimiento (Lote/Serie) del producto.</li>
        </ul>

        <h2><span class='ver'>v3.1</span> - Consulta de Producto y Correcciones Odoo</h2>
        <p><b>Fecha:</b> 24 de Marzo, 2026</p>
        <ul>
            <li><b>Nueva pestaña "🔍 Consulta Producto":</b> Integrada en el módulo Stock y Artículos. Permite buscar cualquier producto por SKU o nombre y obtener su ficha técnica completa: dimensiones, peso, UPP, embalajes, precios, proveedor y notas internas.</li>
            <li><b>Consulta multi-fuente:</b> Los datos se obtienen simultáneamente de Odoo (fuente primaria) y del CSV maestro de Imperbur en Google Sheets (fuente complementaria). Odoo siempre tiene prioridad.</li>
            <li><b>Ficha técnica detallada:</b> Muestra SKU, código de barras, UM, categoría, largo/ancho/alto, peso, volumen, datos de palet (UPP, tipo, capas, remontable), precio de venta, coste estándar, proveedor principal y notas de picking.</li>
            <li><b>Tabla de embalajes:</b> Todos los <i>product.packaging</i> del producto con nombre, cantidad, código de barras y dimensiones (leídas desde <i>stock.package.type</i>).</li>
            <li><b>Acceso directo:</b> Botones para abrir la ficha del producto en Odoo (template y variante) directamente desde el navegador.</li>
            <li><b>Fix crítico - dimensiones de embalajes:</b> Corregido el error <i>"Invalid field 'height' on model 'product.packaging'"</i>. Las dimensiones (largo, ancho, alto, peso máximo) se leen correctamente desde <i>stock.package.type</i>.</li>
            <li><b>Fix crítico - worker Odoo:</b> Resuelto <i>'OdooServiceV2' object has no attribute 'execute'</i>; ahora usa <code>svc.odoo.env[model]</code> siguiendo el patrón nativo de odoorpc.</li>
        </ul>

        <h2><span class='ver'>v2.7</span> - Gestión Integral y Clientes Satélite</h2>
        <p><b>Fecha:</b> 19 de Marzo, 2026</p>
        <ul>
            <li><b>Persistencia de Onboarding:</b> Resolución técnica del refresco automático de solicitudes de Alta Web/Mail tras ser validadas en CRM y pasadas a "Aprobado".</li>
            <li><b>Homologación 150:</b> Implementado el motor de validación de clientes satélite/sucursal. Gabriela identificará nativamente códigos 150 deduciendo qué entidad madre asume la regla comercial.</li>
            <li><b>Motor Comercial Extendido:</b> Ahora con cruces asíncronos rápidos JSON.</li>
        </ul>

        <h2><span class='ver'>v2.5</span> - Fiabilidad y Reparaciones en el Motor</h2>
        <p><b>Fecha:</b> 18 de Marzo, 2026</p>
        <ul>
            <li><b>Cruces Odoo Precisos:</b> Solventado fallo de evaluación y lectura recursiva con NIFs/CIFs. Reglas estrictas aplicadas al validador en bloque.</li>
            <li><b>VIP Overrides:</b> Los clientes especiales ahora pasan correctamente el filtro Bur Group sobreescribiendo familias que puedan fallar en bases Odoo por descuentos manuales.</li>
        </ul>

        <h2><span class='ver'>v2.3</span> - Entorno y Optimización de PC</h2>
        <p><b>Fecha:</b> 14 de Marzo, 2026</p>
        <ul>
            <li><b>Gestor de Cursores:</b> Integración del script de modificación del registro (Regedit) para instalar e inyectar en caliente el cursor 'Bibata Modern Classic' interactuando directamente con la API Win32 de Windows.</li>
            <li><b>Optimizador Silencioso:</b> El panel de limpieza profunda ahora ignora de forma inteligente los archivos bloqueados (WinError 32) por el SO sin saturar la consola de errores.</li>
            <li><b>Decorador de Entorno:</b> Funcionalidad para la creación procedimental mediante IA y aplicación automatizada de fondos de pantalla inmersivos tipo "Megaprochulo Nivel Dios" en el escritorio de Windows.</li>
            <li><b>Documentación:</b> Actualización del Centro de Ayuda incluyendo la nueva sección de "Optimización de Sistema y Personalización".</li>
        </ul>
        
        <h2><span class='ver'>v2.2</span> - Onboarding, Stock y Machine Learning</h2>
        <p><b>Fecha:</b> 13 de Marzo, 2026</p>
        <ul>
            <li><b>Módulo de Stock 2.0:</b> Nueva pestaña de Inventario con desglose de Reservas (Move Lines) y cálculo automático de Pesos por ubicación para optimización de logística.</li>
            <li><b>Control de Artículos:</b> Vista detallada por pedido que cruza el stock disponible en Abrera, Silla y Pinto con las dimensiones maestras (CSV Externo).</li>
            <li><b>Alta de Clientes (Onboarding):</b> Nuevo módulo unificado para la creación y actualización de clientes en Odoo. Incluye normalización de NIF, gestión de IBAN, adjuntos de documentos y autocompletado por Código Postal.</li>
            <li><b>Módulo Analíticas:</b> Nuevo panel principal dedicado al Business Intelligence con gráficos interactivos y KPIs nativos basados en la facturación local.</li>
            <li><b>Predicciones IA:</b> Entrenamiento en vivo de un modelo Random Forest Regressor capaz de analizar el histórico reciente para predecir el Precio Total esperado.</li>
            <li><b>Generador de Contextos:</b> Herramienta `Faker` integrada para volcar pedidos sintéticos estadísticamente precisos en la base de datos de pruebas.</li>
        </ul>

        <h2><span class='ver'>v2.1.1</span> - Correcciones de Reglas y Portes XPS</h2>
        <p><b>Fecha:</b> 11 de Marzo, 2026</p>
        <ul>
            <li><b>Corrección de Gamas en Reglas:</b> Solucionado el bloqueo erróneo al cargar familias SOUND, SUELOS, PYL y CUBIERTAS para distintos perfiles de cliente (Especialistas e Instaladores).</li>
            <li><b>Topes XPS Asegurados:</b> Corrección en el asignador del JSON para que la familia TERMICO_XPS herede los topes del 55% en lugar de los globales de TERMICO estándar.</li>
            <li><b>Seguridad en Familias Futuras:</b> Implementada tabla "default" de topes para acoger gamas no tipificadas sin bloquear el flujo por 0%.</li>
            <li><b>Nuevos Portes XPS:</b> Exigencia incrementada exclusivamente para el poliestireno extruido (XPS), demandando 3.000€ para portes pagados respecto a los 1.500€ del resto de Lanas Térmicas.</li>
        </ul>

        <h2><span class='ver'>v2.1</span> - Clientes Estratégicos y Protección XPS</h2>
        <p><b>Fecha:</b> 10 de Marzo, 2026</p>
        <ul>
            <li><b>Distribuidores Bur Group:</b> Nueva política para grandes cuentas con escalado por importe y validación de jerarquía Comercial vs Supervisor.</li>
            <li><b>Regla de Oro XPS:</b> Las referencias de poliestireno extruido ahora tienen un techo de descuento del 55% y validan obligatoriamente el palet completo.</li>
            <li><b>Portes Fase 2:</b> Implementación de portes pagados automáticos por "Recoge Cliente" o por alcanzar descuento lineal mínimo (30%/25%).</li>
            <li><b>Reporte Chatter VIP:</b> Los bloqueos de Bur Group detallan ahora en Odoo si el error es de gestión o de condiciones comerciales.</li>
        </ul>

        <h2><span class='ver'>v2.0</span> - Velocidad, Batch y Analítica Cero Fuga</h2>
        <p><b>Fecha:</b> 10 de Marzo, 2026</p>
        <ul>
            <li><b>Simulador de Beneficios:</b> Sistema interactivo para probar descuentos al vuelo.</li>
            <li><b>Tarificador en Vivo:</b> Panel MasterRules nativo, adiós a los libros Excel.</li>
            <li><b>Reglas de Cliente:</b> Añade descuentos perpetuos directamente desde la UI de la tabla por IDs de cliente Odoo.</li>
            <li><b>Velocidad x100 (API Batching):</b> Cálculo de KPIs masivo reescrito de un logaritmo N+1 Odoo RPC a empaquetado de red reduciendo las validaciones al 2% de cuellos de red. Cargas inmediatas.</li>
            <li><b>Defensa de Conexión:</b> Manejo robusto de picos Odoo ("Risk Amount") en validaciones sin derrumbar el resto del programa o hilos visuales. </li>
        </ul>

        <h2><span class='ver'>v1.9</span> - Nomenclaturas y Simplificación</h2>
        <p><b>Fecha:</b> 08 de Marzo, 2026</p>
        <ul>
            <li><b>Logística Operativa:</b> Rediseño del selector de almacenes para mostrar exclusivamente aquellos en producción (Abrera, Pinto, Valencia), evitando saturación visual con locales sin actividad.</li>
            <li><b>Roles unificados en Incidencias:</b> Reestructuración del combo de 'Asignado' para calcar la denominación oficial del Helpdesk de Odoo ("Administración", "Logística Interna BUR", "Logística Transporte Externo").</li>
            <li><b>Resumen Inmediato en Chatter:</b> El diálogo de historial ahora incorpora un bloque destacado en la zona superior mostrando la descripción original introducida al crear el ticket.</li>
        </ul>

        <h2><span class='ver'>v1.8</span> - Experiencia y Filtros</h2>
        <p><b>Fecha:</b> 06 de Marzo, 2026</p>
        <ul>
            <li><b>Ordenación Nativa:</b> Tablas en logística ordenables al hacer click en los headers, sin crashear frente a botones (items simulados).</li>
            <li><b>Filtros Dinámicos:</b> Mejor selector de vista por Origen (Entrada/Salida) y Estado de la operación.</li>
            <li><b>Asistente Técnico Integrado:</b> El Asistente IA ahora puede despachar directamente sus redacciones generadas hacia Odoo, como respuestas oficiales XML-RPC en el *Chatter* de un ticket mediante hilos en segundo plano no bloqueantes. El modelo local LLaMA ha sido migrado a su iteración rápida de última generación (3.3).</li>
            <li><b>Control Comercial 2.0:</b> Exclusión garantizada de ofertas; ahora solo analiza <i>Pedidos Emitidos</i> absolutos de forma estricta.</li>
            <li><b>Tablero de Mejoras:</b> Restaurada la pestaña local para el envío de peticiones de sistema.</li>
            <li><b>Layout Adaptativo:</b> Rejilla principal corregida para expandirse dinámicamente si maximizas o reduces tu pantalla sin solapar componentes.</li>
        </ul>
        
        <h2><span class='ver'>v1.7</span> - Gestión Silenciosa y Almacenes</h2>
        <p><b>Fecha:</b> 04 de Marzo, 2026</p>
        <ul>
            <li><b>Detección de Almacenes:</b> Motor mejorado que identifica automáticamente Abrera, Valencia, Silla, etc., desde el pedido y la referencia.</li>
            <li><b>Modo Solo Registro:</b> Las incidencias creadas o cerradas desde la app ya no disparan correos automáticos de Odoo (Notificaciones suprimidas).</li>
            <li><b>Resiliencia UI:</b> Ajuste dinámico de tablas para evitar solapamientos al maximizar la ventana.</li>
        </ul>

        <h2><span class='ver'>v1.6</span> - Mejoras de Filtrado y Estabilidad</h2>
        <p><b>Fecha:</b> 03 de Marzo, 2026</p>
        <ul>
            <li><b>Helpdesk Pro:</b> Añadido filtro por Almacén, Rango de Fecha y Responsable.</li>
            <li><b>Asignación Live:</b> Reasignación de tickets directamente desde la tabla sincronizada con Odoo.</li>
            <li><b>Logística Pinto:</b> Integración total de MAD3 con estados Draft, Internal y Outbound.</li>
            <li><b>Control de Tamaño:</b> Validación de 5MB en adjuntos para evitar errores 413.</li>
            <li><b>Encuesta:</b> Sistema de valoración de 5 estrellas integrado.</li>
        </ul>

        <h2><span class='ver'>v1.5</span> - Control Comercial 2026</h2>
        <ul>
            <li><b>Motor de Portes:</b> Cálculo automático según regiones de la península y Baleares.</li>
            <li><b>Reglas de Descuento:</b> Bloqueo inteligente por familia de producto y tipo de cliente.</li>
            <li><b>Editor de Políticas:</b> Interfaz para cambiar tarifas sin tocar código.</li>
        </ul>

        <h2><span class='ver'>v1.0</span> - Lanzamiento Base</h2>
        <ul>
            <li>Visibilidad de Logística y sincronización Odoo-Gabriela.</li>
            <li>Gestión básica de incidencias con subida de fotos.</li>
            <li>Asistente IA para redacción técnica.</li>
        </ul>

        <p style='text-align: center; margin-top: 40px; border-top: 1px solid #eee; padding-top: 20px;'>
            <b>Gabriela Rojas Pro - Bur 2000 Ecosystem</b>
        </p>
        """

