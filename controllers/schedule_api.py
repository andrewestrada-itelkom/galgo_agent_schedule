# -*- coding: utf-8 -*-
import json
import logging
from datetime import datetime, timedelta

import pytz

from odoo import http
from odoo.http import Response, request

_logger = logging.getLogger(__name__)


class ScheduleApiController(http.Controller):
    """API REST para integración con n8n y sistemas externos."""

    def _get_timezone(self):
        """Obtiene la zona horaria configurada."""
        tz_name = (
            request.env["ir.config_parameter"]
            .sudo()
            .get_param("galgo_agent_schedule.timezone", "America/Bogota")
        )
        return pytz.timezone(tz_name)

    def _get_api_key(self):
        """Obtiene la API key configurada."""
        return (
            request.env["ir.config_parameter"]
            .sudo()
            .get_param("galgo_agent_schedule.api_key", "")
        )

    def _authenticate(self, headers):
        """Valida la API key del header X-API-Key."""
        api_key = self._get_api_key()
        if not api_key:
            # Si no hay API key configurada, permitir acceso
            return True
        provided_key = headers.get("X-Api-Key") or headers.get("x-api-key", "")
        return provided_key == api_key

    def _now_local(self):
        """Retorna la fecha y hora actual en la zona horaria configurada."""
        tz = self._get_timezone()
        utc_now = datetime.utcnow().replace(tzinfo=pytz.UTC)
        local_now = utc_now.astimezone(tz)
        return local_now

    @staticmethod
    def _time_to_minutes(time_str):
        """Convierte 'HH:MM' a minutos desde medianoche."""
        parts = time_str.split(":")
        return int(parts[0]) * 60 + int(parts[1])

    def _is_on_shift(self, schedule, current_minutes):
        """Determina si un agente está en turno en el minuto actual, considerando todos sus intervalos."""
        if not schedule.interval_ids:
            return False
        for line in schedule.interval_ids:
            ini = self._time_to_minutes(line.hora_ini)
            fin = self._time_to_minutes(line.hora_fin)
            # Caso normal
            if fin > ini:
                if ini <= current_minutes < fin:
                    return True
            # Caso nocturno (cruza medianoche)
            else:
                if current_minutes >= ini or current_minutes < fin:
                    return True
        return False

    def _get_shift_horas(self, schedule):
        """Obtiene hora_ini y hora_fin del schedule desde sus intervalos."""
        if not schedule.interval_ids:
            return None, None
        sorted_int = sorted(schedule.interval_ids, key=lambda i: i.hora_ini)
        return sorted_int[0].hora_ini, sorted_int[-1].hora_fin

    def _is_shift_nocturnal(self, schedule):
        """Determina si el schedule tiene algún intervalo nocturno (cruza medianoche)."""
        if not schedule.interval_ids:
            return False
        for line in schedule.interval_ids:
            ini = self._time_to_minutes(line.hora_ini)
            fin = self._time_to_minutes(line.hora_fin)
            if fin <= ini:
                return True
        return False

    def _json_response(self, data, status=200):
        """Retorna una respuesta JSON."""
        return Response(
            json.dumps(data, ensure_ascii=False),
            content_type="application/json",
            status=status,
        )

    @http.route("/galgo/schedule/on_duty", type="http", auth="public", methods=["GET"], csrf=False)
    def on_duty(self, **kwargs):
        """
        GET /galgo/schedule/on_duty

        Retorna los agentes disponibles en el momento de la consulta.

        Parámetros query:
            fecha (opcional, default: hoy, formato YYYY-MM-DD)
            hora (opcional, default: hora actual Colombia, formato HH:MM)
            area_code (opcional) — filtra por galgo.area.code
            nivel_code (opcional) — filtra por galgo.nivel.atencion.code
            solo_confirmados (opcional, default: true)
        """
        # Autenticación
        if not self._authenticate(request.httprequest.headers):
            return self._json_response(
                {"status": "error", "message": "API Key inválida"}, status=401
            )

        try:
            params = request.httprequest.args.to_dict()

            solo_confirmados = params.get("solo_confirmados", "true").lower() != "false"
            area_code = params.get("area_code", "")
            nivel_code = params.get("nivel_code", "")

            # Determinar fecha y hora
            now_local = self._now_local()
            fecha_str = params.get("fecha", now_local.strftime("%Y-%m-%d"))
            hora_str = params.get("hora", now_local.strftime("%H:%M"))

            fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date()
            current_minutes = self._time_to_minutes(hora_str)

            # Buscar schedules del día
            Schedule = request.env["galgo.agent.schedule"].sudo()
            domain = [("fecha", "=", fecha)]

            if solo_confirmados:
                domain.append(("state", "=", "confirmado"))

            # Filtro de área
            if area_code:
                Area = request.env["galgo.area"].sudo()
                area = Area.search([("code", "=", area_code)], limit=1)
                if not area:
                    return self._json_response(
                        {
                            "status": "ok",
                            "fecha": fecha_str,
                            "hora": hora_str,
                            "area": area_code,
                            "agentes_disponibles": [],
                            "total": 0,
                            "hay_disponibles": False,
                        }
                    )
                domain.append(("area_id", "=", area.id))

            # Filtro de nivel
            if nivel_code:
                Nivel = request.env["galgo.nivel.atencion"].sudo()
                nivel = Nivel.search([("code", "=", nivel_code)], limit=1)
                if not nivel:
                    return self._json_response(
                        {
                            "status": "ok",
                            "fecha": fecha_str,
                            "hora": hora_str,
                            "area": area_code or "todas",
                            "agentes_disponibles": [],
                            "total": 0,
                            "hay_disponibles": False,
                        }
                    )
                domain.append(("nivel_id", "=", nivel.id))

            schedules = Schedule.search(domain)

            # Para turnos nocturnos: si hora < hora_fin, buscar en fecha-1 también
            fecha_anterior = fecha - timedelta(days=1)
            domain_prev = list(domain)
            domain_prev[0] = ("fecha", "=", fecha_anterior)

            schedules_prev = Schedule.search(domain_prev)
            all_schedules = schedules | schedules_prev

            # Filtrar por horario activo
            agentes_disponibles = []
            seen_agents = set()

            for sched in all_schedules:
                # Para schedules de fecha anterior, solo incluir nocturnos
                if sched.fecha == fecha_anterior:
                    if not self._is_shift_nocturnal(sched):
                        continue
                    # Para nocturnos del día anterior, solo si la hora actual
                    # está en la parte nocturna (antes de hora_fin)
                    _, fin = self._get_shift_horas(sched)
                    if fin:
                        fin_min = self._time_to_minutes(fin)
                        if current_minutes >= fin_min:
                            continue

                # Para schedules del día actual
                if sched.fecha == fecha:
                    if not self._is_on_shift(sched, current_minutes):
                        continue

                # Evitar duplicados del mismo agente
                if sched.agent_id.id in seen_agents:
                    continue
                seen_agents.add(sched.agent_id.id)

                hora_ini, hora_fin = self._get_shift_horas(sched)
                agente_data = {
                    "nombre": sched.agent_id.name,
                    "chatwoot_agent_id": sched.chatwoot_agent_id or 0,
                    "area": sched.area_id.code or "",
                    "area_nombre": sched.area_id.name or "",
                    "nivel_code": sched.nivel_id.code or "",
                    "nivel_nombre": sched.nivel_id.name or "",
                    "turno": sched.shift_id.name,
                    "hora_ini": hora_ini or "",
                    "hora_fin": hora_fin or "",
                }
                agentes_disponibles.append(agente_data)

            result = {
                "status": "ok",
                "fecha": fecha_str,
                "hora": hora_str,
                "area": area_code or "todas",
                "agentes_disponibles": agentes_disponibles,
                "total": len(agentes_disponibles),
                "hay_disponibles": len(agentes_disponibles) > 0,
            }

            return self._json_response(result)

        except Exception as e:
            _logger.exception("Error en /galgo/schedule/on_duty: %s", e)
            return self._json_response(
                {"status": "error", "message": str(e)}, status=500
            )

    @http.route("/galgo/schedule/areas", type="http", auth="public", methods=["GET"], csrf=False)
    def areas(self, **kwargs):
        """
        GET /galgo/schedule/areas

        Retorna la lista de áreas activas con sus niveles.
        Sin autenticación requerida.
        """
        try:
            areas = request.env["galgo.area"].sudo().search([("active", "=", True)])
            result_list = []
            for area in areas:
                niveles = request.env["galgo.nivel.atencion"].sudo().search(
                    [
                        "|",
                        ("area_id", "=", area.id),
                        ("area_id", "=", False),
                    ]
                )
                result_list.append(
                    {
                        "id": area.id,
                        "code": area.code,
                        "name": area.name,
                        "niveles": [
                            {
                                "id": n.id,
                                "code": n.code,
                                "name": n.name,
                                "secuencia": n.secuencia,
                            }
                            for n in niveles
                        ],
                    }
                )

            return self._json_response(
                {
                    "status": "ok",
                    "areas": result_list,
                    "total": len(result_list),
                }
            )

        except Exception as e:
            _logger.exception("Error en /galgo/schedule/areas: %s", e)
            return self._json_response(
                {"status": "error", "message": str(e)}, status=500
            )
