# -*- coding: utf-8 -*-
import secrets

from odoo import _, api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    galgo_schedule_api_key = fields.Char(
        string="API Key Turnos",
        config_parameter="galgo_agent_schedule.api_key",
        help="Clave API para autenticación de endpoints externos (n8n).",
    )
    galgo_schedule_timezone = fields.Char(
        string="Zona Horaria",
        config_parameter="galgo_agent_schedule.timezone",
        default="America/Bogota",
        help="Zona horaria por defecto para cálculos de turno.",
    )
    galgo_schedule_mensaje_fuera_horario = fields.Text(
        string="Mensaje Fuera de Horario",
        help="Mensaje a enviar por WhatsApp cuando no hay agentes disponibles.",
    )

    def action_generate_galgo_schedule_api_key(self):
        """Genera (o regenera) una API key segura para el módulo de turnos.

        Usa secrets.token_urlsafe para garantizar entropía criptográfica.
        Persiste directamente en ir.config_parameter y actualiza el campo
        en el formulario para que sea visible de inmediato.
        """
        new_key = secrets.token_urlsafe(32)

        # Persistir la key sin esperar al save del TransientModel
        self.env["ir.config_parameter"].sudo().set_param(
            "galgo_agent_schedule.api_key", new_key
        )

        # Reflejar el valor en el registro transiente (UI)
        self.write({"galgo_schedule_api_key": new_key})

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("API Key Generada"),
                "message": _(
                    "La nueva API Key ha sido generada y guardada. "
                    "Copiela antes de cerrar esta ventana si la necesita."
                ),
                "type": "success",
                "sticky": False,
            },
        }

    @api.model
    def get_values(self):
        res = super().get_values()
        params = self.env["ir.config_parameter"].sudo()
        res.update(
            galgo_schedule_mensaje_fuera_horario=params.get_param(
                "galgo_agent_schedule.mensaje_fuera_horario", default=""
            )
        )
        return res

    def set_values(self):
        super().set_values()
        params = self.env["ir.config_parameter"].sudo()
        params.set_param(
            "galgo_agent_schedule.mensaje_fuera_horario",
            self.galgo_schedule_mensaje_fuera_horario or "",
        )
