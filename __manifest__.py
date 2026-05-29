# -*- coding: utf-8 -*-
{
    "name": "Galgo Agent Schedule",
    "version": "16.0.1.0.0",
    "category": "Galgo/HR",
    "summary": "Gestión visual de horarios rotativos para cualquier área",
    "description": """
        Módulo para la gestión visual de horarios rotativos por área o departamento.
        Soporta turnos rotativos (mañana, día, noche) por fecha con integración
        vía API REST para n8n u otros sistemas externos.
    """,
    "author": "Galgo",
    "website": "",
    "license": "LGPL-3",
    "depends": ["base", "web", "mail"],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "data/galgo_area_data.xml",
        "data/galgo_nivel_data.xml",
        "data/galgo_shift_template_data.xml",
        "data/galgo_dia_semana_data.xml",
        "views/galgo_area_views.xml",
        "views/galgo_nivel_atencion_views.xml",
        "views/galgo_agent_views.xml",
        "views/galgo_shift_template_views.xml",
        "views/galgo_agent_schedule_views.xml",
        "wizard/galgo_schedule_wizard_views.xml",
        "views/res_config_settings_views.xml",
        "views/menu.xml",
    ],
    "demo": [
        "demo/demo_agents.xml",
        "demo/demo_schedules.xml",
    ],
    "application": True,
    "installable": True,
    "auto_install": False,
}
