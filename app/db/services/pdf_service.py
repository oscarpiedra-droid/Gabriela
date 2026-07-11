import os
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from loguru import logger

class PDFService:
    def __init__(self):
        # We find the app directory to locate exports correctly
        self.app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.exports_dir = os.path.join(self.app_dir, "..", "exports")
        if not os.path.exists(self.exports_dir):
            os.makedirs(self.exports_dir)

    def generate_policy_pdf(self, current_data: dict) -> str:
        """
        Generates a professional PDF document with the 2026 Commercial Policy (v2 structure).
        Returns the absolute path to the generated file.
        """
        filename = f"Politica_Comercial_2026_v2_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        filepath = os.path.join(self.exports_dir, filename)
        
        doc = SimpleDocTemplate(filepath, pagesize=A4)
        elements = []
        styles = getSampleStyleSheet()
        
        # Corporate Styles
        title_style = ParagraphStyle(
            'CorporateTitle',
            parent=styles['Heading1'],
            fontSize=22,
            textColor=colors.HexColor("#714B67"), # Odoo/Bur Primary
            alignment=1,
            spaceAfter=30
        )
        
        section_style = ParagraphStyle(
            'SectionHeader',
            parent=styles['Heading2'],
            fontSize=16,
            textColor=colors.HexColor("#00A09D"), # Odoo/Bur Secondary
            spaceBefore=20,
            spaceAfter=15
        )

        # 1. Header
        elements.append(Paragraph("BUR 2000 - POLÍTICA COMERCIAL 2026 (ACTUALIZADA V2)", title_style))
        elements.append(Paragraph(f"Fecha de actualización: {datetime.now().strftime('%d/%m/%Y %H:%M')}", styles['Normal']))
        elements.append(Spacer(1, 20))

        # 2. Shipping Costs Table (Using v2 SHIPPING_GROUPS)
        elements.append(Paragraph("📦 TARIFAS DE PORTES (LOGÍSTICA - G1 GENERAL)", section_style))
        
        shipping_groups = current_data.get("SHIPPING_GROUPS", {})
        g1_rules = shipping_groups.get("G1_GENERAL", [])
        
        if g1_rules:
            table_data = [["Min Order (€)", "Max Order (€)", "Región Bkt", "Precio (€)"]]
            for rule in g1_rules:
                table_data.append([
                    f"{rule.get('min_order_eur', 0)} €",
                    f"{rule.get('max_order_eur', 0)} €",
                    rule.get('region_bucket_key', ''),
                    f"{rule.get('price_eur', 0)} €"
                ])
                
            t = Table(table_data, colWidths=[100, 100, 100, 100])
            t.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#714B67")),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.grey),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
            ]))
            elements.append(t)
        else:
            elements.append(Paragraph("No se encontraron reglas de portes en formato v2.", styles['Normal']))
            
        elements.append(Spacer(1, 30))

        # 3. Policy Summary
        elements.append(Paragraph("💰 RESUMEN DE POLÍTICA DE DESCUENTOS", section_style))
        sku_count = len(current_data.get('SKU_MASTER', {}))
        disc_count = len(current_data.get('SKU_DISCOUNTS', {}))
        
        summary_text = (
            f"La política comercial actual contempla un maestro de <b>{sku_count} SKUs</b> "
            f"con una matriz de descuentos detallada para <b>{disc_count} productos</b>. "
            "Los descuentos se aplican de forma granular según la región y tipo de cliente (Constructoras, Instaladoras, Parquetistas, etc.)."
        )
        elements.append(Paragraph(summary_text, styles['Normal']))

        # 4. Footer info
        elements.append(Spacer(1, 40))
        footer_text = "<i>Este documento es de uso interno exclusivo para la red comercial de BUR 2000. Los datos se actualizan automáticamente desde el sistema centralizado de Gabriela Rojas (v2).</i>"
        elements.append(Paragraph(footer_text, styles['Italic']))

        # Build PDF
        try:
            doc.build(elements)
            logger.info(f"PDF generated successfully at: {filepath}")
            return filepath
        except Exception as e:
            logger.error(f"Failed to build PDF: {e}")
            raise
