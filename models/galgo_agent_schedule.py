# -*- coding: utf-8 -*-
import logging
import pytz
from datetime import datetime, timedelta

from odoo import _, api, exceptions, fields, models

_logger = logging.getLogger(__name__)


class GalgoAgentSchedule(models.Model):
    _name = "galgo.agent.schedule"
    _description = "Turno Asignado a Agente"
    _order = "fecha desc"
    _rec_name = "name"

    name = fields.Char(
        string="Descripción",
        compute="_compute_name",
        store=True,
    )

    fecha = fields.Date(
        string="Fecha",
        required=True,
        default=lambda self: self._get_default_fecha(),
        help="Fecha del turno. Se establece automáticamente desde el calendario.",
    )
    agent_id = fields.Many2one(
        comodel_name="galgo.agent",
        string="Agente",
        required=True,
    )
    area_id = fields.Many2one(
        comodel_name="galgo.area",
        string="Área",
        related="agent_id.area_id",
        store=True,
    )
    nivel_id = fields.Many2one(
        comodel_name="galgo.nivel.atencion",
        string="Nivel",
        related="agent_id.nivel_id",
        store=True,
    )
    shift_id = fields.Many2one(
        comodel_name="galgo.shift.template",
        string="Turno",
        required=True,
    )
    chatwoot_agent_id = fields.Integer(
        string="ID Chatwoot",
        related="agent_id.chatwoot_agent_id",
        store=True,
    )
    notas = fields.Text(
        string="Notas",
    )
    interval_ids = fields.One2many(
        comodel_name="galgo.agent.schedule.interval",
        inverse_name="schedule_id",
        string="Intervalos de Horario",
        copy=True,
    )
    color = fields.Integer(
        string="Color",
        related="shift_id.color",
        store=True,
    )
    state = fields.Selection(
        selection=[
            ("draft", "Borrador"),
            ("confirmado", "Confirmado"),
        ],
        string="Estado",
        default="draft",
    )

    _sql_constraints = [
        (
            "unique_agent_fecha_shift",
            "UNIQUE(agent_id, fecha, shift_id)",
            "Un agente no puede tener el mismo turno duplicado en la misma fecha.",
        ),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        """Override create to generate interval_ids from shift template.

        Todos los turnos tienen intervalos (1 o más). Se leen desde
        shift_id.interval_ids y se crean como interval_ids del schedule.
        """
        for vals in vals_list:
            shift_id = vals.get("shift_id")
            if shift_id and not vals.get("interval_ids"):
                shift = self.env["galgo.shift.template"].browse(shift_id)
                agent_id = vals.get("agent_id")
                if shift.interval_ids:
                    interval_vals = [
                        (0, 0, {
                            "hora_ini": line.hora_ini,
                            "hora_fin": line.hora_fin,
                            "shift_id": shift_id,
                            "agent_id": agent_id,
                        })
                        for line in shift.interval_ids
                    ]
                    vals["interval_ids"] = interval_vals
        records = super().create(vals_list)
        for rec in records.filtered("interval_ids"):
            rec.interval_ids.recompute()
        return records

    @api.model
    def _get_default_fecha(self):
        """Extrae la fecha del contexto (default_date o default_datetime_start)."""
        default_date = self.env.context.get('default_date')
        if default_date:
            if isinstance(default_date, str):
                return fields.Date.from_string(default_date)
            return default_date
        dt_start = self.env.context.get('default_datetime_start')
        if dt_start:
            try:
                if isinstance(dt_start, str):
                    dt_start = fields.Datetime.from_string(dt_start)
                return dt_start.date()
            except Exception:
                return fields.Date.today()
        default_fecha = self.env.context.get('default_fecha')
        if default_fecha:
            if isinstance(default_fecha, str):
                return fields.Date.from_string(default_fecha)
            return default_fecha
        return fields.Date.today()

    @api.onchange("shift_id")
    def _onchange_shift_id_fill_intervals(self):
        """Al seleccionar un turno, llenar interval_ids desde la plantilla."""
        for rec in self:
            if rec.shift_id and rec.shift_id.interval_ids:
                rec.interval_ids = [(5, 0, 0)]
                interval_vals = []
                for line in rec.shift_id.interval_ids:
                    interval_vals.append((0, 0, {
                        "hora_ini": line.hora_ini,
                        "hora_fin": line.hora_fin,
                    }))
                rec.interval_ids = interval_vals
            else:
                rec.interval_ids = [(5, 0, 0)]

    @api.onchange("agent_id", "shift_id", "fecha")
    def _onchange_check_duplicate(self):
        """Advierte si ya existe un schedule para el mismo agente, fecha y turno."""
        for rec in self:
            if rec.agent_id and rec.shift_id and rec.fecha:
                domain = [
                    ("agent_id", "=", rec.agent_id.id),
                    ("shift_id", "=", rec.shift_id.id),
                    ("fecha", "=", rec.fecha),
                ]
                if rec.id:
                    domain.append(("id", "!=", rec.id))
                existing = self.search(domain, limit=1)
                if existing:
                    return {
                        "warning": {
                            "title": _("Turno duplicado"),
                            "message": _(
                                "Ya existe un turno '%(shift)s' para %(agent)s el %(date)s.",
                                shift=rec.shift_id.name,
                                agent=rec.agent_id.name,
                                date=rec.fecha,
                            ),
                        }
                    }

    def action_open_schedule(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Turno Completo",
            "res_model": "galgo.agent.schedule",
            "res_id": self.id,
            "view_mode": "form",
            "target": "current",
        }

    @api.depends("shift_id.name", "agent_id.name", "area_id.name")
    def _compute_name(self):
        for rec in self:
            turno = rec.shift_id.name or ""
            agente = rec.agent_id.name or ""
            area = rec.area_id.name or ""
            if area:
                rec.name = "%s | %s (%s)" % (agente, turno, area)
            else:
                rec.name = "%s | %s" % (agente, turno)

    def _get_hora_ini_fin(self):
        """Retorna hora_ini y hora_fin desde el primer y último intervalo."""
        if not self.interval_ids:
            return None, None
        sorted_int = sorted(self.interval_ids, key=lambda i: i.hora_ini)
        return sorted_int[0].hora_ini, sorted_int[-1].hora_fin

    def _is_nocturnal(self):
        """Determina si el schedule tiene algún intervalo nocturno (cruza medianoche)."""
        if not self.interval_ids:
            return False
        for line in self.interval_ids:
            try:
                ini = self._time_to_minutes(line.hora_ini)
                fin = self._time_to_minutes(line.hora_fin)
                if fin <= ini:
                    return True
            except (ValueError, AttributeError, IndexError):
                continue
        return False

    def _get_fecha_fin(self):
        """Retorna la fecha fin (un día después si hay intervalo nocturno)."""
        if self._is_nocturnal():
            return self.fecha + timedelta(days=1)
        return self.fecha

    def _get_duracion_horas(self):
        """Calcula la duración total en horas desde los intervalos."""
        if not self.interval_ids:
            return 0.0
        total_min = 0
        for line in self.interval_ids:
            try:
                ini_m = self._time_to_minutes(line.hora_ini)
                fin_m = self._time_to_minutes(line.hora_fin)
                if fin_m >= ini_m:
                    total_min += (fin_m - ini_m)
                else:
                    total_min += ((1440 - ini_m) + fin_m)
            except (ValueError, AttributeError, IndexError):
                continue
        return total_min / 60.0

    @api.constrains("agent_id", "fecha")
    def _check_no_overlap(self):
        """Verifica que no haya turnos solapados para el mismo agente."""
        for rec in self:
            if not rec.fecha or not rec.agent_id or not rec.interval_ids:
                continue
            fecha_ant = rec.fecha - timedelta(days=1)
            fecha_sig = rec.fecha + timedelta(days=1)
            domain = [
                ("agent_id", "=", rec.agent_id.id),
                ("fecha", "in", [fecha_ant, rec.fecha, fecha_sig]),
                ("id", "!=", rec.id),
            ]
            overlapping = self.search(domain)
            for other in overlapping:
                if rec._overlaps_with(other):
                    raise exceptions.ValidationError(
                        _(
                            "El agente '%(agent)s' ya tiene un turno solapado "
                            "entre el %(date1)s y %(date2)s (Turno: %(turno)s).",
                            agent=rec.agent_id.name,
                            date1=other.fecha,
                            date2=other._get_fecha_fin(),
                            turno=other.shift_id.name,
                        )
                    )

    def _overlaps_with(self, other):
        """Verifica si dos turnos se solapan, considerando todos sus intervalos."""
        if not self.interval_ids or not other.interval_ids:
            return False
        for line in self.interval_ids:
            for other_line in other.interval_ids:
                ini_m = self._time_to_minutes(line.hora_ini)
                fin_m = self._time_to_minutes(line.hora_fin)
                o_ini_m = self._time_to_minutes(other_line.hora_ini)
                o_fin_m = self._time_to_minutes(other_line.hora_fin)

                start = datetime.combine(self.fecha, datetime.min.time()) + timedelta(minutes=ini_m)
                if fin_m <= ini_m:
                    end = datetime.combine(self.fecha + timedelta(days=1), datetime.min.time()) + timedelta(minutes=fin_m)
                else:
                    end = datetime.combine(self.fecha, datetime.min.time()) + timedelta(minutes=fin_m)

                o_start = datetime.combine(other.fecha, datetime.min.time()) + timedelta(minutes=o_ini_m)
                if o_fin_m <= o_ini_m:
                    o_end = datetime.combine(other.fecha + timedelta(days=1), datetime.min.time()) + timedelta(minutes=o_fin_m)
                else:
                    o_end = datetime.combine(other.fecha, datetime.min.time()) + timedelta(minutes=o_fin_m)

                if start < o_end and o_start < end:
                    return True
        return False

    @staticmethod
    def _time_to_minutes(time_str):
        """Convierte 'HH:MM' a minutos desde medianoche."""
        parts = time_str.split(":")
        return int(parts[0]) * 60 + int(parts[1])

    def action_confirm(self):
        for rec in self:
            rec.state = "confirmado"

    def action_draft(self):
        for rec in self:
            rec.state = "draft"

    def action_confirm_selected(self):
        """Confirmar los registros seleccionados."""
        self.action_confirm()


class GalgoAgentScheduleInterval(models.Model):
    _name = "galgo.agent.schedule.interval"
    _description = "Intervalo de Turno Agente"
    _order = "datetime_start"

    schedule_id = fields.Many2one(
        comodel_name="galgo.agent.schedule",
        string="Turno",
        ondelete="cascade",
        required=False,
    )
    agent_id = fields.Many2one(
        comodel_name="galgo.agent",
        string="Agente",
        compute="_compute_from_schedule",
        inverse="_inverse_agent_id",
        store=True,
        readonly=False,
    )
    fecha = fields.Date(
        string="Fecha",
        compute="_compute_from_schedule",
        inverse="_inverse_fecha",
        store=True,
        readonly=False,
    )

    @api.model
    def _get_default_fecha(self):
        """Extrae la fecha del contexto (default_date o default_datetime_start)."""
        default_date = self.env.context.get('default_date')
        if default_date:
            if isinstance(default_date, str):
                return fields.Date.from_string(default_date)
            return default_date
        dt_start = self.env.context.get('default_datetime_start')
        if dt_start:
            try:
                if isinstance(dt_start, str):
                    dt_start = fields.Datetime.from_string(dt_start)
                return dt_start.date()
            except Exception:
                return fields.Date.today()
        default_fecha = self.env.context.get('default_fecha')
        if default_fecha:
            if isinstance(default_fecha, str):
                return fields.Date.from_string(default_fecha)
            return default_fecha
        return fields.Date.today()

    @api.depends("schedule_id")
    def _compute_from_schedule(self):
        for rec in self:
            if rec.schedule_id:
                rec.agent_id = rec.schedule_id.agent_id
                rec.fecha = rec.schedule_id.fecha
            else:
                rec.agent_id = rec.agent_id or False
                rec.fecha = rec.fecha or False

    def _inverse_agent_id(self):
        for rec in self:
            if rec.schedule_id:
                rec.schedule_id.agent_id = rec.agent_id

    def _inverse_fecha(self):
        pass  # No sync — schedule.fecha is source of truth

    area_id = fields.Many2one(
        comodel_name="galgo.area",
        string="Área",
        related="schedule_id.area_id",
        store=True,
    )
    nivel_id = fields.Many2one(
        comodel_name="galgo.nivel.atencion",
        string="Nivel",
        related="schedule_id.nivel_id",
        store=True,
    )
    color = fields.Integer(
        string="Color",
        related="schedule_id.shift_id.color",
        store=True,
    )
    state = fields.Selection(
        string="Estado",
        related="schedule_id.state",
        store=True,
    )
    name = fields.Char(
        string="Nombre",
        compute="_compute_interval_name",
        store=True,
    )
    shift_id = fields.Many2one(
        comodel_name="galgo.shift.template",
        string="Turno",
    )

    hora_ini = fields.Char(
        string="Hora Inicio",
        required=True,
    )
    hora_fin = fields.Char(
        string="Hora Fin",
        required=True,
    )

    datetime_start = fields.Datetime(
        string="Inicio",
        compute="_compute_datetimes",
        store=True,
    )
    datetime_end = fields.Datetime(
        string="Fin",
        compute="_compute_datetimes",
        store=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        intervals = self.env['galgo.agent.schedule.interval']
        for vals in vals_list:
            if not vals.get('schedule_id') and vals.get('shift_id'):
                fecha = vals.get('fecha')
                if not fecha and vals.get('datetime_start'):
                    dt = fields.Datetime.from_string(vals.get('datetime_start'))
                    tz_name = self.env["ir.config_parameter"].sudo().get_param("galgo_agent_schedule.timezone", "America/Bogota")
                    tz = pytz.timezone(tz_name)
                    fecha = pytz.utc.localize(dt).astimezone(tz).date()

                schedule = self.env['galgo.agent.schedule'].create({
                    'agent_id': vals.get('agent_id'),
                    'fecha': fecha or fields.Date.today(),
                    'shift_id': vals.get('shift_id'),
                })
                if schedule.interval_ids:
                    intervals |= schedule.interval_ids
            else:
                intervals |= super(GalgoAgentScheduleInterval, self).create([vals])
        return intervals

    def action_open_schedule(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Turno Completo",
            "res_model": "galgo.agent.schedule",
            "res_id": self.schedule_id.id,
            "view_mode": "form",
            "target": "current",
        }

    @api.depends("schedule_id.name", "hora_ini", "hora_fin")
    def _compute_interval_name(self):
        for rec in self:
            parent_name = rec.schedule_id.name or ""
            horas = "(%s - %s)" % (rec.hora_ini, rec.hora_fin)
            rec.name = "%s %s" % (parent_name, horas)

    @api.depends("fecha", "hora_ini", "hora_fin")
    def _compute_datetimes(self):
        tz_name = self.env["ir.config_parameter"].sudo().get_param("galgo_agent_schedule.timezone", "America/Bogota")
        tz = pytz.timezone(tz_name)
        for rec in self:
            if not rec.fecha or not rec.hora_ini or not rec.hora_fin:
                rec.datetime_start = False
                rec.datetime_end = False
                continue
            try:
                ini_m = GalgoAgentSchedule._time_to_minutes(rec.hora_ini)
                fin_m = GalgoAgentSchedule._time_to_minutes(rec.hora_fin)

                start_naive = datetime.combine(rec.fecha, datetime.min.time()) + timedelta(minutes=ini_m)
                if fin_m <= ini_m:
                    end_naive = datetime.combine(rec.fecha + timedelta(days=1), datetime.min.time()) + timedelta(minutes=fin_m)
                else:
                    end_naive = datetime.combine(rec.fecha, datetime.min.time()) + timedelta(minutes=fin_m)

                rec.datetime_start = tz.localize(start_naive).astimezone(pytz.UTC).replace(tzinfo=None)
                rec.datetime_end = tz.localize(end_naive).astimezone(pytz.UTC).replace(tzinfo=None)
            except (ValueError, TypeError, AttributeError):
                rec.datetime_start = False
                rec.datetime_end = False