# -*- coding: utf-8 -*-
from odoo import _, api, exceptions, fields, models


class GalgoShiftTemplate(models.Model):
    _name = "galgo.shift.template"
    _description = "Plantilla de Turno"
    _order = "name"

    name = fields.Char(
        string="Nombre",
        required=True,
    )
    code = fields.Char(
        string="Código",
        required=True,
        help="Código único de la plantilla (ej: manana, dia, noche, oficina).",
    )
    color = fields.Integer(
        string="Color",
    )
    area_ids = fields.Many2many(
        comodel_name="galgo.area",
        relation="galgo_shift_template_area_rel",
        column1="shift_template_id",
        column2="area_id",
        string="Áreas",
        help="Áreas que usan esta plantilla. Vacío = todas las áreas.",
    )
    interval_ids = fields.One2many(
        comodel_name="galgo.shift.interval",
        inverse_name="shift_id",
        string="Intervalos de Horario",
    )

    _sql_constraints = [
        (
            "code_uniq",
            "UNIQUE(code)",
            "El código de la plantilla de turno debe ser único.",
        ),
    ]

    @api.constrains("interval_ids")
    def _check_at_least_one_interval(self):
        for rec in self:
            if not rec.interval_ids:
                raise exceptions.ValidationError(
                    _("Debe definir al menos un intervalo de horario.")
                )


class GalgoShiftInterval(models.Model):
    _name = "galgo.shift.interval"
    _description = "Intervalo de Turno"
    _order = "hora_ini"

    shift_id = fields.Many2one(
        comodel_name="galgo.shift.template",
        string="Plantilla de Turno",
        ondelete="cascade",
        required=True,
    )
    hora_ini = fields.Char(
        string="Hora Inicio",
        required=True,
        help="Formato HH:MM",
    )
    hora_fin = fields.Char(
        string="Hora Fin",
        required=True,
        help="Formato HH:MM",
    )
