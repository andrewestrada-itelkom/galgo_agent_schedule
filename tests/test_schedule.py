# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from odoo.fields import Date

class TestGalgoAgentSchedule(TransactionCase):

    def setUp(self):
        super(TestGalgoAgentSchedule, self).setUp()
        
        # Crear Área
        self.area = self.env['galgo.area'].create({
            'name': 'Área de Prueba',
            'code': 'TEST',
        })
        
        # Crear Agente
        self.agent = self.env['galgo.agent'].create({
            'name': 'Agente de Prueba',
            'area_id': self.area.id,
        })
        
        # Crear Plantilla de Turno con Color e Intervalos
        self.shift_template = self.env['galgo.shift.template'].create({
            'name': 'Turno de Prueba',
            'code': 'TEST_SHIFT',
            'color': 5, # Un color cualquiera
            'interval_ids': [(0, 0, {
                'hora_ini': '08:00',
                'hora_fin': '12:00',
            }), (0, 0, {
                'hora_ini': '14:00',
                'hora_fin': '18:00',
            })]
        })

    def test_01_create_schedule_and_check_color_and_intervals(self):
        """Validar que al crear un schedule se herede el color y se generen intervalos."""
        schedule = self.env['galgo.agent.schedule'].create({
            'agent_id': self.agent.id,
            'shift_id': self.shift_template.id,
            'fecha': Date.today(),
        })
        
        # Verificar color heredado
        self.assertEqual(schedule.color, self.shift_template.color, "El color del schedule debe ser el mismo que el de la plantilla")
        
        # Verificar intervalos generados
        self.assertEqual(len(schedule.interval_ids), 2, "Se deben haber generado 2 intervalos")
        
        # Verificar datetimes de los intervalos
        for interval in schedule.interval_ids:
            self.assertTrue(interval.datetime_start, "El intervalo debe tener fecha de inicio")
            self.assertTrue(interval.datetime_end, "El intervalo debe tener fecha de fin")
            self.assertEqual(interval.color, self.shift_template.color, "El intervalo debe heredar el color")

    def test_02_create_interval_directly_creates_schedule(self):
        """Validar que crear un intervalo directamente en el calendario cree el schedule padre.

        Cuando se crea un intervalo directamente (sin schedule_id) pero con shift_id,
        el create() del intervalo crea el schedule padre (que a su vez genera intervalos
        desde la plantilla). El test verifica que schedule_id se setee correctamente.
        """
        # Simulamos la creación desde el calendario (sin schedule_id, solo shift_id)
        # El create() crea el schedule padre que genera intervalos desde la plantilla.
        # Para turnos partido, el schedule.interval_ids tendrá los intervalos de la plantilla.
        intervals = self.env['galgo.agent.schedule.interval'].create({
            'agent_id': self.agent.id,
            'shift_id': self.shift_template.id,
            'fecha': Date.today(),
            'hora_ini': '08:00',  # estos valores se ignoran porque el schedule los genera
            'hora_fin': '12:00',
        })

        # El schedule se creó con la plantilla (que tiene 2 intervalos en setUp)
        # El create() retorna schedule.interval_ids (los generados desde la plantilla)
        self.assertTrue(len(intervals) >= 1, "Se debería haber creado al menos un intervalo")
        first_interval = intervals[0]

        self.assertTrue(first_interval.schedule_id, "Se debería haber creado un schedule padre automáticamente")
        self.assertEqual(first_interval.schedule_id.shift_id, self.shift_template)
        # El schedule tiene los intervalos de la plantilla (2 para "Turno de Prueba")
        self.assertEqual(len(first_interval.schedule_id.interval_ids), 2,
                         "El schedule debería tener 2 intervalos (turno partido)")
        self.assertEqual(first_interval.color, self.shift_template.color, "El intervalo debe tener el color de la plantilla")
