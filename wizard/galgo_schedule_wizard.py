# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import _, exceptions, fields, models


class GalgoScheduleWizard(models.TransientModel):
    _name = "galgo.schedule.wizard"
    _description = "Generar Turnos en Lote"

    fecha_inicio = fields.Date(
        string="Fecha Inicio",
        required=True,
        default=fields.Date.context_today,
    )
    fecha_fin = fields.Date(
        string="Fecha Fin",
        required=True,
        default=fields.Date.context_today,
    )
    area_id = fields.Many2one(
        comodel_name="galgo.area",
        string="Área",
        required=True,
    )
    lineas_ids = fields.One2many(
        comodel_name="galgo.schedule.wizard.line",
        inverse_name="wizard_id",
        string="Líneas de Configuración",
    )

    def action_generate(self):
        self.ensure_one()
        if self.fecha_fin < self.fecha_inicio:
            raise exceptions.ValidationError(
                _("La fecha fin no puede ser anterior a la fecha inicio.")
            )
        if not self.lineas_ids:
            raise exceptions.ValidationError(
                _("Debe agregar al menos una línea de configuración.")
            )

        Schedule = self.env["galgo.agent.schedule"]
        created = 0
        skipped = 0

        current = self.fecha_inicio
        while current <= self.fecha_fin:
            day_week = str(current.weekday())  # 0=Lunes, 6=Domingo
            for line in self.lineas_ids:
                if day_week not in line.dias_semana.mapped("code"):
                    continue

                # Verificar si ya existe
                existing = Schedule.search(
                    [
                        ("agent_id", "=", line.agent_id.id),
                        ("fecha", "=", current),
                        ("shift_id", "=", line.shift_id.id),
                    ],
                    limit=1,
                )
                if existing:
                    skipped += 1
                    continue

                Schedule.create(
                    {
                        "fecha": current,
                        "agent_id": line.agent_id.id,
                        "shift_id": line.shift_id.id,
                        "state": "draft",
                    }
                )
                created += 1

            current += timedelta(days=1)

        return {
            "type": "ir.actions.act_window",
            "name": "Turnos Generados",
            "res_model": "galgo.agent.schedule",
            "view_mode": "tree,form",
            "domain": [
                ("fecha", ">=", self.fecha_inicio),
                ("fecha", "<=", self.fecha_fin),
                ("area_id", "=", self.area_id.id),
            ],
            "target": "current",
        }


class GalgoScheduleWizardLine(models.TransientModel):
    _name = "galgo.schedule.wizard.line"
    _description = "Línea de Configuración de Turnos"

    wizard_id = fields.Many2one(
        comodel_name="galgo.schedule.wizard",
        string="Wizard",
        required=True,
        ondelete="cascade",
    )
    agent_id = fields.Many2one(
        comodel_name="galgo.agent",
        string="Agente",
        required=True,
    )
    shift_id = fields.Many2one(
        comodel_name="galgo.shift.template",
        string="Turno",
        required=True,
    )
    dias_semana = fields.Many2many(
        comodel_name="galgo.dia.semana",
        relation="galgo_schedule_wizard_line_dia_rel",
        column1="line_id",
        column2="dia_id",
        string="Días de la Semana",
        required=True,
    )


class GalgoDiaSemana(models.Model):
    _name = "galgo.dia.semana"
    _description = "Día de la Semana"
    _order = "secuencia"

    name = fields.Char(
        string="Nombre",
        required=True,
    )
    code = fields.Char(
        string="Código",
        required=True,
    )
    secuencia = fields.Integer(
        string="Secuencia",
        default=1,
    )
