# -*- coding: utf-8 -*-
import logging
import pytz
from datetime import datetime, timedelta

from odoo import _, api, exceptions, fields, models

_logger = logging.getLogger(__name__)


class GalgoAgentSchedule(models.Model):
    _name = "galgo.agent.schedule"
    _description = "Turno Asignado a Agente"
    _order = "fecha desc, hora_ini"
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
    # hora_ini/hora_fin se calculan desde los intervalos (para compatibilidad y búsqueda)
    hora_ini = fields.Char(
        string="Hora Inicio",
        compute="_compute_hora_ini_fin",
        store=True,
        help="Primera hora de los intervalos del turno.",
    )
    hora_fin = fields.Char(
        string="Hora Fin",
        compute="_compute_hora_ini_fin",
        store=True,
        help="Última hora de los intervalos del turno.",
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
    es_nocturno = fields.Boolean(
        string="Turno Nocturno",
        compute="_compute_es_nocturno",
        store=True,
    )
    duracion_horas = fields.Float(
        string="Duración (horas)",
        compute="_compute_duracion_horas",
        store=True,
    )
    fecha_fin = fields.Date(
        string="Fecha Fin",
        compute="_compute_fecha_fin",
        store=True,
    )
    datetime_start = fields.Datetime(
        string="Inicio Datetime",
        compute="_compute_datetimes",
        store=True,
    )
    datetime_end = fields.Datetime(
        string="Fin Datetime",
        compute="_compute_datetimes",
        store=True,
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
                    # Crear un intervalo por cada línea de la plantilla
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
        """Extrae la fecha de default_datetime_start del calendario (tratándolo como hora de Bogotá).

        Odoo calendar pasa default_datetime_start en UTC, pero lo computing desde la fecha visible
        del calendario, no desde datetime_start almacenado. Esto puede causar desfases de fecha
        cuando se clickea en un día diferente al mes visible.

        Para evitar esto, intentamos usar default_date (fecha exacta clickeada) si está disponible,
        o extraemos la fecha del datetime tratando de inferir si hay un problema de zona horaria.
        """
        # Primero intentamos con default_date (más confiable para la fecha clickeada)
        default_date = self.env.context.get('default_date')
        if default_date:
            _logger.info("[GALGO-DEBUG] _get_default_fecha | default_date=%s", default_date)
            if isinstance(default_date, str):
                return fields.Date.from_string(default_date)
            return default_date

        dt_start = self.env.context.get('default_datetime_start')
        _logger.info(
            "[GALGO-DEBUG] _get_default_fecha | default_datetime_start=%r type=%s",
            dt_start, type(dt_start).__name__,
        )
        if dt_start:
            try:
                if isinstance(dt_start, str):
                    dt_start = fields.Datetime.from_string(dt_start)
                fecha = dt_start.date()
                # Verificar si la fecha del datetime es muy distinta a la actual mes/vista del calendario.
                # Si dt_start mes != mes actual, probablemente hay un bug del calendario -> fallback a hoy.
                hoy = fields.Date.today()
                if fecha.year != hoy.year or fecha.month != hoy.month:
                    _logger.warning(
                        "[GALGO-DEBUG] _get_default_fecha | dt_start=%s no corresponde al mes visible (%s), usando hoy",
                        fecha, hoy,
                    )
                    # Intentar con default_fecha si existe
                    default_fecha = self.env.context.get('default_fecha')
                    if default_fecha:
                        if isinstance(default_fecha, str):
                            return fields.Date.from_string(default_fecha)
                        return default_fecha
                    return hoy
                _logger.info(
                    "[GALGO-DEBUG] _get_default_fecha | dt_start=%s -> fecha=%s",
                    dt_start, fecha,
                )
                return fecha
            except Exception:
                _logger.info("[GALGO-DEBUG] _get_default_fecha | EXCEPTION, returning today")
                return fields.Date.today()
        # Fallback: buscar default_fecha en contexto (usado por el wizard)
        default_fecha = self.env.context.get('default_fecha')
        if default_fecha:
            _logger.info("[GALGO-DEBUG] _get_default_fecha | default_fecha=%s", default_fecha)
            if isinstance(default_fecha, str):
                return fields.Date.from_string(default_fecha)
            return default_fecha
        _logger.info("[GALGO-DEBUG] _get_default_fecha | NO default_datetime_start, returning today=%s", fields.Date.today())
        return fields.Date.today()

    @api.onchange("shift_id")
    def _onchange_shift_id_fill_intervals(self):
        """Al seleccionar un turno, llenar interval_ids desde la plantilla.

        Todos los turnos tienen intervalos (1 o más). Se generan desde
        shift_id.interval_ids. El campo fecha del intervalo se hereda del
        schedule vía _compute_from_schedule.
        """
        for rec in self:
            if rec.shift_id and rec.shift_id.interval_ids:
                rec.interval_ids = [(5, 0, 0)]  # Limpiar actuales
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

    @api.depends("shift_id", "shift_id.hora_ini", "shift_id.hora_fin", "shift_id.interval_ids")
    def _compute_hora_ini_fin(self):
        for rec in self:
            if rec.shift_id:
                h_ini = rec.shift_id.hora_ini
                h_fin = rec.shift_id.hora_fin

                if not h_ini and not h_fin and rec.shift_id.interval_ids:
                    sorted_intervals = sorted(rec.shift_id.interval_ids, key=lambda i: i.hora_ini)
                    h_ini = sorted_intervals[0].hora_ini
                    h_fin = sorted_intervals[-1].hora_fin

                rec.hora_ini = h_ini
                rec.hora_fin = h_fin
            else:
                rec.hora_ini = False
                rec.hora_fin = False

    @api.depends("hora_ini", "hora_fin")
    def _compute_es_nocturno(self):
        for rec in self:
            try:
                ini = rec._time_to_minutes(rec.hora_ini)
                fin = rec._time_to_minutes(rec.hora_fin)
                # Si fin <= ini, significa que termina el día siguiente
                rec.es_nocturno = fin <= ini
            except (ValueError, TypeError, AttributeError, IndexError):
                rec.es_nocturno = False

    @api.depends("hora_ini", "hora_fin", "es_nocturno", "interval_ids.hora_ini", "interval_ids.hora_fin")
    def _compute_duracion_horas(self):
        for rec in self:
            try:
                if rec.interval_ids:
                    # Sumar duración de todos los intervalos
                    total_min = 0
                    for line in rec.interval_ids:
                        ini_m = rec._time_to_minutes(line.hora_ini)
                        fin_m = rec._time_to_minutes(line.hora_fin)
                        if fin_m >= ini_m:
                            total_min += (fin_m - ini_m)
                        else:
                            total_min += ((1440 - ini_m) + fin_m)
                    rec.duracion_horas = total_min / 60.0
                else:
                    ini = rec._time_to_minutes(rec.hora_ini)
                    fin = rec._time_to_minutes(rec.hora_fin)
                    if not rec.es_nocturno:
                        rec.duracion_horas = (fin - ini) / 60.0
                    else:
                        # Cruza medianoche: (1440 - ini) + fin
                        rec.duracion_horas = ((1440 - ini) + fin) / 60.0
            except (ValueError, TypeError, AttributeError, IndexError):
                rec.duracion_horas = 0.0

    @api.depends("fecha", "es_nocturno")
    def _compute_fecha_fin(self):
        for rec in self:
            if rec.fecha and rec.es_nocturno:
                rec.fecha_fin = rec.fecha + timedelta(days=1)
            else:
                rec.fecha_fin = rec.fecha

    @api.depends("fecha", "hora_ini", "hora_fin", "es_nocturno")
    def _compute_datetimes(self):
        tz_name = self.env["ir.config_parameter"].sudo().get_param("galgo_agent_schedule.timezone", "America/Bogota")
        tz = pytz.timezone(tz_name)
        for rec in self:
            if not rec.fecha or not rec.hora_ini or not rec.hora_fin:
                rec.datetime_start = False
                rec.datetime_end = False
                continue
            try:
                ini_m = self._time_to_minutes(rec.hora_ini)
                fin_m = self._time_to_minutes(rec.hora_fin)
                
                # Crear datetimes ingenuos (naive)
                start_naive = datetime.combine(rec.fecha, datetime.min.time()) + timedelta(minutes=ini_m)
                if rec.es_nocturno:
                    end_naive = datetime.combine(rec.fecha + timedelta(days=1), datetime.min.time()) + timedelta(minutes=fin_m)
                else:
                    end_naive = datetime.combine(rec.fecha, datetime.min.time()) + timedelta(minutes=fin_m)
                
                # Localizar y convertir a UTC para almacenamiento en Odoo
                rec.datetime_start = tz.localize(start_naive).astimezone(pytz.UTC).replace(tzinfo=None)
                rec.datetime_end = tz.localize(end_naive).astimezone(pytz.UTC).replace(tzinfo=None)
                _logger.info(
                    "[GALGO-DEBUG] _compute_datetimes SCHEDULE | rec.id=%s fecha=%s hora_ini=%s -> datetime_start=%s",
                    rec.id, rec.fecha, rec.hora_ini, rec.datetime_start,
                )
            except (ValueError, TypeError, AttributeError):
                rec.datetime_start = False
                rec.datetime_end = False

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
            # Formato más limpio: Agente | Turno (Área)
            if area:
                rec.name = "%s | %s (%s)" % (agente, turno, area)
            else:
                rec.name = "%s | %s" % (agente, turno)

    @api.constrains("agent_id", "fecha", "hora_ini", "hora_fin")
    def _check_no_overlap(self):
        for rec in self:
            if not rec.hora_ini or not rec.hora_fin or not rec.fecha or not rec.agent_id:
                continue
            # Buscamos en el día anterior, actual y siguiente para cubrir turnos nocturnos
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
                            date2=other.fecha_fin,
                            turno=other.shift_id.name,
                        )
                    )

    def _overlaps_with(self, other):
        """Verifica si dos turnos se solapan en horario, considerando todos sus intervalos."""

        def get_intervals(rec):
            res = []
            try:
                # Si tiene líneas de intervalo, usarlas
                if rec.interval_ids:
                    for line in rec.interval_ids:
                        ini_m = self._time_to_minutes(line.hora_ini)
                        fin_m = self._time_to_minutes(line.hora_fin)
                        start = datetime.combine(rec.fecha, datetime.min.time()) + timedelta(minutes=ini_m)
                        if fin_m <= ini_m:
                            end = datetime.combine(rec.fecha + timedelta(days=1), datetime.min.time()) + timedelta(minutes=fin_m)
                        else:
                            end = datetime.combine(rec.fecha, datetime.min.time()) + timedelta(minutes=fin_m)
                        res.append((start, end))
                else:
                    # Si no, usar el horario principal
                    ini_m = self._time_to_minutes(rec.hora_ini)
                    fin_m = self._time_to_minutes(rec.hora_fin)
                    start = datetime.combine(rec.fecha, datetime.min.time()) + timedelta(minutes=ini_m)
                    if fin_m <= ini_m:
                        end = datetime.combine(rec.fecha + timedelta(days=1), datetime.min.time()) + timedelta(minutes=fin_m)
                    else:
                        end = datetime.combine(rec.fecha, datetime.min.time()) + timedelta(minutes=fin_m)
                    res.append((start, end))
            except (ValueError, TypeError, AttributeError):
                pass
            return res

        intervals1 = get_intervals(self)
        intervals2 = get_intervals(other)

        for s1, e1 in intervals1:
            for s2, e2 in intervals2:
                if s1 < e2 and s2 < e1:
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
    # Campos replicados para la vista de calendario y creación
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
        # No default — el intervalo hereda fecha del schedule vía _compute_from_schedule.
        # Poner default causaría que se use default_date del calendario incorrectamente.
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

    @api.onchange("shift_id")
    def _onchange_shift_id(self):
        """Al seleccionar un turno, llenar hora_ini y hora_fin desde la plantilla."""
        for rec in self:
            if rec.shift_id:
                # Si el turno tiene intervalos, usar el primero y el último
                if rec.shift_id.interval_ids:
                    sorted_intervals = sorted(rec.shift_id.interval_ids, key=lambda i: i.hora_ini)
                    rec.hora_ini = sorted_intervals[0].hora_ini
                    rec.hora_fin = sorted_intervals[-1].hora_fin
                else:
                    rec.hora_ini = rec.shift_id.hora_ini
                    rec.hora_fin = rec.shift_id.hora_fin
            else:
                rec.hora_ini = False
                rec.hora_fin = False

    @api.depends("schedule_id")
    def _compute_from_schedule(self):
        for rec in self:
            _logger.info("[GALGO-DEBUG] _compute_from_schedule | rec.id=%s schedule_id=%s", rec.id, rec.schedule_id.id if rec.schedule_id else None)
            if rec.schedule_id:
                _logger.info("[GALGO-DEBUG] _compute_from_schedule | schedule.fecha=%s", rec.schedule_id.fecha)
                rec.agent_id = rec.schedule_id.agent_id
                rec.fecha = rec.schedule_id.fecha
            else:
                # No sobrescribir si ya tiene valor (útil en creación)
                _logger.info("[GALGO-DEBUG] _compute_from_schedule | NO schedule_id, agent_id=%s fecha=%s", rec.agent_id.id if rec.agent_id else None, rec.fecha)
                rec.agent_id = rec.agent_id or False
                rec.fecha = rec.fecha or False

    def _inverse_agent_id(self):
        for rec in self:
            if rec.schedule_id:
                rec.schedule_id.agent_id = rec.agent_id

    def _inverse_fecha(self):
        for rec in self:
            if rec.schedule_id:
                # Don't sync fecha back to schedule during creation.
                # Schedule's fecha is the source of truth; interval.fecha is derived.
                # The inverse is only for manual edits in existing intervals.
                pass

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
    # Campos para creación desde calendario
    shift_id = fields.Many2one(
        comodel_name="galgo.shift.template",
        string="Turno",
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
        # Para evitar problemas con el required=True de Odoo en la UI,
        # si viene un shift_id pero no schedule_id, creamos el padre primero.
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
                # El schedule ya creó sus propios intervalos automáticamente.
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

    def action_save_and_open_schedule(self):
        """Guarda el intervalo (creando schedule padre si no existe) y abre el schedule."""
        self.ensure_one()
        if not self.schedule_id:
            # Los valores ya están en el registro, el create() del ORM ya fue llamado.
            # schedule_id se habrá creado en el create() del modelo si shift_id estaba presente.
            # Re-buscar por si el schedule no se creó por algún motivo.
            if self.shift_id and self.agent_id and self.fecha:
                schedule = self.env["galgo.agent.schedule"].create(
                    {
                        "agent_id": self.agent_id.id,
                        "fecha": self.fecha,
                        "shift_id": self.shift_id.id,
                        "state": "draft",
                    }
                )
                # Recargar el registro para obtener el schedule creado
                self = self.browse(self.id)
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
            # El nombre del intervalo ahora será el nombre del turno + las horas del intervalo
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
                # Usamos la clase para el método estático
                ini_m = GalgoAgentSchedule._time_to_minutes(rec.hora_ini)
                fin_m = GalgoAgentSchedule._time_to_minutes(rec.hora_fin)
                
                # Crear datetimes ingenuos (naive)
                start_naive = datetime.combine(rec.fecha, datetime.min.time()) + timedelta(minutes=ini_m)
                # Si fin <= ini, es nocturno
                if fin_m <= ini_m:
                    end_naive = datetime.combine(rec.fecha + timedelta(days=1), datetime.min.time()) + timedelta(minutes=fin_m)
                else:
                    end_naive = datetime.combine(rec.fecha, datetime.min.time()) + timedelta(minutes=fin_m)
                
                # Localizar y convertir a UTC para almacenamiento en Odoo
                rec.datetime_start = tz.localize(start_naive).astimezone(pytz.UTC).replace(tzinfo=None)
                rec.datetime_end = tz.localize(end_naive).astimezone(pytz.UTC).replace(tzinfo=None)
            except (ValueError, TypeError, AttributeError, IndexError):
                rec.datetime_start = False
                rec.datetime_end = False
