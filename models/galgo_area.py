# -*- coding: utf-8 -*-
from odoo import fields, models


class GalgoArea(models.Model):
    _name = "galgo.area"
    _description = "Área o Departamento"
    _order = "name"

    name = fields.Char(
        string="Nombre",
        required=True,
    )
    code = fields.Char(
        string="Código",
        required=True,
        help="Código único del área para integración con API REST.",
    )
    color = fields.Integer(
        string="Color",
    )
    descripcion = fields.Text(
        string="Descripción",
    )
    active = fields.Boolean(
        string="Activo",
        default=True,
    )
    responsable_id = fields.Many2one(
        comodel_name="res.users",
        string="Responsable",
    )

    _sql_constraints = [
        (
            "code_uniq",
            "UNIQUE(code)",
            "El código del área debe ser único.",
        ),
    ]