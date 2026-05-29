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
    # Los turnos se definen SOLO por intervalos. hora_ini/hora_fin son un atajo
    # para turnos de un solo bloque — se calculan desde los intervalos.
    hora_ini = fields.Char(
        string="Hora Inicio",
        compute="_compute_hora_ini_fin",
        store=False,
        help="Calculado desde el primer intervalo.",
    )
    hora_fin = fields.Char(
        string="Hora Fin",
        compute="_compute_hora_ini_fin",
        store=False,
        help="Calculado desde el último intervalo.",
    )
    cruza_medianoche = fields.Boolean(
        string="Cruza Medianoche",
        compute="_compute_cruza_medianoche",
        store=True,
    )
    duracion_horas = fields.Float(
        string="Duración (horas)",
        compute="_compute_duracion_horas",
        store=True,
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

    @api.depends("interval_ids")
    def _compute_hora_ini_fin(self):
        for rec in self:
            if rec.interval_ids:
                sorted_int = sorted(rec.interval_ids, key=lambda i: i.hora_ini)
                rec.hora_ini = sorted_int[0].hora_ini
                rec.hora_fin = sorted_int[-1].hora_fin
            else:
                rec.hora_ini = False
                rec.hora_fin = False

    @api.onchange("interval_ids")
    def _onchange_interval_ids(self):
        """Sincronizar hora_ini/hora_fin para compatibilidad (aunque ya no se usan directamente)."""
        if self.interval_ids:
            sorted_int = sorted(self.interval_ids, key=lambda i: i.hora_ini)
            self.hora_ini = sorted_int[0].hora_ini
            self.hora_fin = sorted_int[-1].hora_fin

    @staticmethod
    def _time_to_minutes(time_str):
        parts = time_str.split(":")
        return int(parts[0]) * 60 + int(parts[1])

    @api.depends("interval_ids.hora_ini", "interval_ids.hora_fin")
    def _compute_cruza_medianoche(self):
        for rec in self:
            if not rec.interval_ids:
                rec.cruza_medianoche = False
                continue
            # Un turno cruza medianoche si ALGÚN intervalo cruza medianoche
            for line in rec.interval_ids:
                try:
                    ini = rec._time_to_minutes(line.hora_ini)
                    fin = rec._time_to_minutes(line.hora_fin)
                    if fin <= ini:
                        rec.cruza_medianoche = True
                        break
                except (ValueError, AttributeError, IndexError):
                    continue
            else:
                rec.cruza_medianoche = False

    @api.depends("interval_ids.hora_ini", "interval_ids.hora_fin")
    def _compute_duracion_horas(self):
        for rec in self:
            try:
                if not rec.interval_ids:
                    rec.duracion_horas = 0.0
                    return
                total_min = 0
                for line in rec.interval_ids:
                    ini = rec._time_to_minutes(line.hora_ini)
                    fin = rec._time_to_minutes(line.hora_fin)
                    if fin >= ini:
                        total_min += (fin - ini)
                    else:
                        # Cruza medianoche: (1440 - ini) + fin
                        total_min += ((1440 - ini) + fin)
                rec.duracion_horas = total_min / 60.0
            except (ValueError, AttributeError, IndexError):
                rec.duracion_horas = 0.0


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
