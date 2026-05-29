# -*- coding: utf-8 -*-
from odoo import api, fields, models


class GalgoAgent(models.Model):
    _name = "galgo.agent"
    _description = "Agente de Atención"
    _order = "name"

    name = fields.Char(
        string="Nombre",
        required=True,
    )
    chatwoot_agent_id = fields.Integer(
        string="ID Agente Chatwoot",
        help="ID del agente en Chatwoot para integración con WhatsApp.",
    )
    area_id = fields.Many2one(
        comodel_name="galgo.area",
        string="Área",
        required=True,
    )
    nivel_id = fields.Many2one(
        comodel_name="galgo.nivel.atencion",
        string="Nivel de Atención",
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        string="Usuario Odoo",
        help="Usuario de Odoo vinculado al agente (opcional).",
    )
    telefono = fields.Char(
        string="Teléfono",
    )
    email = fields.Char(
        string="Email",
    )
    active = fields.Boolean(
        string="Activo",
        default=True,
    )
    notas = fields.Text(
        string="Notas",
    )
    schedule_ids = fields.One2many(
        comodel_name="galgo.agent.schedule",
        inverse_name="agent_id",
        string="Turnos",
    )
    schedule_count = fields.Integer(
        string="Cantidad de turnos",
        compute="_compute_schedule_count",
    )

    @api.onchange("user_id")
    def _onchange_user_id(self):
        for rec in self:
            if not rec.user_id:
                continue
            rec.name = rec.user_id.name or rec.name
            rec.telefono = rec.user_id.phone or rec.telefono
            rec.email = rec.user_id.email or rec.email

    def _compute_schedule_count(self):
        Schedule = self.env["galgo.agent.schedule"]
        for rec in self:
            rec.schedule_count = Schedule.search_count(
                [("agent_id", "=", rec.id)]
            )

    def action_view_schedules(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Historial de Turnos",
            "res_model": "galgo.agent.schedule",
            "view_mode": "tree,form",
            "domain": [("agent_id", "=", self.id)],
        }
