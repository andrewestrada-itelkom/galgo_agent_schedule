# -*- coding: utf-8 -*-
from odoo import fields, models


class GalgoNivelAtencion(models.Model):
    _name = "galgo.nivel.atencion"
    _description = "Nivel de Atención"
    _order = "secuencia, name"

    name = fields.Char(
        string="Nombre",
        required=True,
    )
    code = fields.Char(
        string="Código",
        required=True,
        help="Código único del nivel para integración con API REST.",
    )
    area_id = fields.Many2one(
        comodel_name="galgo.area",
        string="Área",
        help="Si no se selecciona área, aplica a todas las áreas.",
    )
    secuencia = fields.Integer(
        string="Secuencia",
        default=1,
        help="Orden de escalación (1=primero en atender).",
    )
    color = fields.Integer(
        string="Color",
    )