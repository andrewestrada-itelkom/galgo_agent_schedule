# Galgo Agent Schedule

Módulo Odoo 16 para gestión visual de horarios rotativos por área con integración API REST.

## Funcionalidades

- **Calendario visual** de turnos por agente y área
- **Turnos partidos** (turnos divididos en intervalos, ej: 08:00-12:00 y 14:00-18:00)
- **Turnos nocturnos** con detección automática de cruce de medianoche
- **Wizard batch** para generar turnos en lote por rango de fechas y días de la semana
- **API REST** para integración con n8n y sistemas externos
- **Control de acceso** por roles (Viewer, User, Manager, Admin)
- **Zonas horarias** configurables via `ir.config_parameter`

## Instalación

```bash
# Instalar módulo
docker exec odoo odoo -c /etc/odoo/odoo.conf -i galgo_agent_schedule --stop-after-init

# Actualizar módulo
docker restart odoo && docker exec -u 0 odoo odoo -c /etc/odoo/odoo.conf -d galgo -i galgo_agent_schedule --test-enable --stop-after-init
```

## Modelo de datos

```
galgo.area ───1:M──► galgo.agent ───1:M──► galgo.agent.schedule
                                                      └── galgo.agent.schedule.interval
galgo.shift.template ───1:M──► galgo.shift.interval
galgo.nivel.atencion ──M2O──► galgo.area (opcional)
galgo.dia.semana ──M2M──► galgo.schedule.wizard.line
```

### Relación entre intervalos

`galgo.shift.interval` y `galgo.agent.schedule.interval` **NO tienen relación directa**. Ambos modelos están relacionados con `galgo.shift.template` pero de formas diferentes:

```
galgo.shift.template ──1:N──► galgo.shift.interval (plantilla de intervalos)
        │
        └──1:N──► galgo.agent.schedule ──1:N──► galgo.agent.schedule.interval (copia real)
```

| Modelo | Propósito | Ejemplo |
|--------|-----------|---------|
| `galgo.shift.interval` | Plantilla de horarios | "Oficina tiene 2 bloques: 08-12 y 14-18" |
| `galgo.agent.schedule.interval` | Copia real para un agente | "Juan trabaja 08-12 y 14-18 el 30/05" |

**Flujo de creación:**
1. Se define la plantilla `galgo.shift.template` con sus `galgo.shift.interval`
2. Se crea un `galgo.agent.schedule` seleccionando la plantilla
3. El `create()` lee los `galgo.shift.interval` y crea copias en `galgo.agent.schedule.interval`

## API REST

| Endpoint | Método | Auth | Descripción |
|----------|--------|------|-------------|
| `/galgo/schedule/on_duty` | GET | API Key | Agentes disponibles |
| `/galgo/schedule/areas` | GET | No | Lista de áreas y niveles |

### Parámetros `/on_duty`

| Parámetro | Tipo | Default | Descripción |
|-----------|------|---------|-------------|
| `fecha` | string | Hoy | Formato YYYY-MM-DD |
| `hora` | string | Ahora | Formato HH:MM |
| `area_code` | string | Todas | Código de área |
| `nivel_code` | string | Todos | Código de nivel |
| `solo_confirmados` | string | true | Solo agentes confirmados |

### Ejemplo

```bash
curl -H "X-API-Key: YOUR_KEY" "http://localhost:8069/galgo/schedule/on_duty?fecha=2026-05-30&hora=10:00&area_code=noc"
```

## Configuración

| Parámetro | Descripción |
|-----------|-------------|
| `galgo_agent_schedule.api_key` | API key para endpoints externos |
| `galgo_agent_schedule.timezone` | Zona horaria (default: America/Bogota) |

## Estructura del módulo

```
galgo_agent_schedule/
├── models/              # Lógica de negocio
├── wizard/              # Wizard de generación batch
├── controllers/         # API REST (schedule_api.py)
├── views/               # Vistas XML y menús
├── data/                # Datos estáticos (áreas, turnos, días)
├── security/            # Control de acceso (CSV + XML rules)
├── tests/               # Tests TransactionCase
├── AGENTS.md            # Documentación para AI agents
└── README.md            # Este archivo
```

## Roles de acceso

| Rol | Permisos |
|-----|----------|
| **Viewer** | Solo lectura de turnos |
| **User** | Crear/editar turnos propios |
| **Manager** | CRUD completo + wizard + config |
| **Admin** | Igual que Manager + gestión de áreas/niveles |

## Datos demo

### Turnos predefinidos

| Código | Nombre | Horario |
|--------|--------|---------|
| `manana` | Mañana | 06:00 - 14:00 |
| `dia` | Día | 08:00 - 18:00 |
| `noche` | Noche | 18:00 - 06:00 (cruza medianoche) |
| `oficina` | Oficina | 08:00 - 17:00 |
| `medio_tiempo` | Medio tiempo | 08:00 - 13:00 |

### Áreas

- **NOC** - Network Operations Center
- **Ventas** - Equipo de Ventas

### Niveles

- **Nivel 1** - Primer nivel de atención
- **Nivel 2** - Segundo nivel de atención

## Notas técnicas

- Timezone: `pytz` con configurable via `ir.config_parameter`
- Turnos nocturnos: lógica `fin <= ini` = cruza medianoche
- Turnos partidos: múltiples `interval_ids` por shift
- Wizard batch: crea schedules por rango de fechas filtrando por `dias_semana.code`

## License

LGPL-3
