import random
import os
from datetime import datetime
from loguru import logger
import requests

class TechnicalService:
    def __init__(self, odoo_service):
        self.odoo = odoo_service
        self.provider = os.getenv("AI_PROVIDER", "Mock (Simulado)")
        self.api_key = os.getenv("AI_API_KEY", "")
        self.history = [
            {
                "time": "10:30",
                "client": "Construcciones S.A.",
                "subject": "Duda sobre secado de S-YC",
                "action": "🟢 Automático",
                "summary": "Respondido con FAQ #4"
            }
        ]

    def get_recent_activity(self):
        return self.history

    def get_bot_stats(self):
        return {
            "processed": 12,
            "automated": 9,
            "consultations": 2,
            "escalated": 1,
            "status": "Dormido" if datetime.now().hour < 8 or datetime.now().hour > 20 else "Activo"
        }

    def get_ai_insights(self, stats_dict: dict):
        """Perform a data-driven analysis using AI."""
        if self.provider == "Mock (Simulado)":
            return "Análisis Simulado: Se observa una concentración del 40% de incidencias en el almacén de Pinto. Se recomienda revisar los procesos de carga matutinos."
        
        prompt = f"""
        Analiza estos datos de incidencias de Bur 2000:
        - Total Activas: {stats_dict.get('total', 0)}
        - Por Almacén: {stats_dict.get('by_warehouse', {})}
        - Por Etapa: {stats_dict.get('by_stage', {})}
        
        Pregunta: ¿Cuál es la situación actual y qué recomendación técnica darías para reducir incidencias?
        Se breve y profesional.
        """
        
        return self.refine_draft(prompt, system_role="Eres un Analista de Operaciones experto para Bur 2000.")


    def refine_draft(self, raw_input, system_role="Eres un Asistente Técnico Senior de Bur 2000. Redacta profesionalmente."):

        if not raw_input: return ""
        
        if self.provider == "Mock (Simulado)":
            return self._mock_generation(raw_input)
            
        try:
            if self.provider == "OpenAI":
                return self._call_openai(raw_input, system_role)
            elif "Anthropic" in self.provider:
                return self._call_anthropic(raw_input, system_role) # Anthropic method needs update too
            elif "Google" in self.provider:
                return self._call_gemini(raw_input, system_role)
            elif "Groq" in self.provider:
                return self._call_groq(raw_input, system_role)
            elif "Ollama" in self.provider:
                return self._call_ollama(raw_input, system_role)

        except ImportError as ie:
            return f"⚠️ No se han instalado las librerías de {self.provider}.\nPor favor, ejecuta 'Gabriela.bat'.\n\n(Fallback):\n{self._mock_generation(raw_input)}"
        except Exception as e:
            logger.error(f"AI Provider Error ({self.provider}): {e}")
            return f"Error de IA: {e}\n\n(Fallback):\n{self._mock_generation(raw_input)}"

        return self._mock_generation(raw_input)

    def _call_openai(self, text, role):
        import openai
        client = openai.OpenAI(api_key=self.api_key)
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": role},
                {"role": "user", "content": text}
            ]
        )
        return response.choices[0].message.content


    def _call_anthropic(self, text, role):
        import anthropic
        client = anthropic.Anthropic(api_key=self.api_key)
        message = client.messages.create(
            model="claude-3-5-sonnet-20240620",
            max_tokens=1024,
            system=role,
            messages=[{"role": "user", "content": text}]
        )
        return message.content[0].text

    def _call_gemini(self, text, role):
        import google.generativeai as genai
        genai.configure(api_key=self.api_key)
        model = genai.GenerativeModel('gemini-1.5-pro', system_instruction=role)
        response = model.generate_content(text)
        return response.text

    def _call_groq(self, text, role):
        from groq import Groq
        client = Groq(api_key=self.api_key)
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": role},
                {"role": "user", "content": text}
            ],
            temperature=0.7,
            max_tokens=1024,
        )
        return completion.choices[0].message.content

    def _call_ollama(self, text, role):
        url = "http://localhost:11434/api/generate"
        payload = {
            "model": "llama3",
            "system": role,
            "prompt": text,
            "stream": False
        }
        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status()
        return response.json().get('response', '')


    def _mock_generation(self, raw_input):
        return f"Estimado cliente,\n\nGracias por contactar con Bur 2000 sobre: {raw_input}.\n\n(Respuesta Simulada / Fallback)\n\nAtentamente."

    def send_via_bot(self, recipient, subject, body, ticket_id=None, ticket_name="General"):
        # Actual Odoo integration via tracking chatter / mail API
        if ticket_id and self.odoo:
            # We don't have direct CC here, assume generic reply or rely on message_post parsing
            # However, since it is a ticket, message_post directly onto 'helpdesk.ticket' is the most native UX in Odoo
            try:
                success, error_msg = self.odoo.send_email_with_odoo(
                    res_model='helpdesk.ticket',
                    res_id=ticket_id,
                    to_email=recipient,
                    cc_emails="",
                    subject=subject,
                    body=body
                )
                if not success:
                    raise Exception(f"send_email_with_odoo falló: {error_msg}")
            except Exception as e:
                logger.error(f"Error posting bot reply to ticket {ticket_id}: {e}")
                return False

        self.history.insert(0, {
            "time": datetime.now().strftime("%H:%M"),
            "client": ticket_name,
            "subject": subject,
            "action": "🟢 Mail Enviado",
            "summary": "Redactado y enviado vía IA"
        })
        return True
