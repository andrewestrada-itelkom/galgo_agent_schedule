# PRD — Galgo Agent Schedule

## 1. Concept & Vision

**Galgo Agent Schedule** es un módulo Odoo 16 para gestión visual de horarios rotativos de agentes por área, diseñado para teams de soporte/NOC que necesitan turnos partidos (con breaks), turnos nocturnos, y visualización clara en calendario.

El módulo prioriza la **experiencia de调度 visual** — crear turnos haciendo click en el calendario es más rápido que usar un wizard. La integración API permite que sistemas externos (n8n, chatbots) consulten quién está disponible en tiempo real.

**Usuario típico**: supervisor de NOC que programa turnos semanalmente y necesita la API para routing de chats.

---

## 2. Product Overview

### 2.1 Core Problem
- Agentes de soporte necesitan turnos rotativos con múltiples bloques de horario (turnos partidos: mañana + tarde con break al mediodía)
- Turnos nocturnos que cruzan medianoche
- Visualización en calendario para identificar gaps de coverage
- Sistemas externos (Chatwoot, n8n) necesitan saber quién está disponible en tiempo real

### 2.2 Solution
- Calendario visual de turnos por agente y área
- Turnos partidos con múltiples intervalos por schedule
- Wizard batch para generación semanal/mensual
- API REST `/on_duty` con auth por API key
- API REST `/areas` pública (sin auth)

### 2.3 Target Users
| Rol | Uso |
|-----|-----|
| Supervisor NOC | Crear/editar turnos, usar wizard batch |
| Agente | Ver sus propios turnos (solo lectura) |
| Sistema externo (n8n) | Consultar `/on_duty` para routing |

---

## 3. Data Model

```
galgo.area ───1:M──► galgo.agent ───1:M──► galgo.agent.schedule
                                                      └── galgo.agent.schedule.interval
galgo.shift.template ───1:M──► galgo.shift.interval
galgo.nivel.atencion ──M2O──► galgo.area (opcional)
galgo.dia.semana ──M2M──► galgo.schedule.wizard.line
```

### Interval relationship (critical)

`galgo.shift.interval` (plantilla) **NO FK** a `galgo.agent.schedule.interval` (copia real). La relación es conceptual, no referencial:

```
galgo.shift.template ──1:N──► galgo.shift.interval (plantilla)
        │
        └──1:N──► galgo.agent.schedule ──1:N──► galgo.agent.schedule.interval (copia)
```

**Flow**: `create()` en `galgo.agent.schedule` lee `galgo.shift.interval` y genera copias en `galgo.agent.schedule.interval`.

---

## 4. Functional Specification

### 4.1 Schedule Creation (Calendar Click)

**Actor**: Supervisor
**Trigger**: Click en día del calendario, selecciona agente + turno
**Behavior**:
1. Click en fecha → se abre form con `fecha` pre-poblada desde `default_date` (no `default_datetime_start`)
2. Seleccionar agente → `area_id` y `nivel_id` se auto-rellenan (stored related)
3. Seleccionar turno →
   - Si turno tiene `interval_ids`: se generan intervalos en `interval_ids` del schedule vía `_onchange_shift_id_fill_intervals`
   - Si turno simple (`hora_ini`/`hora_fin`): se crea un solo intervalo
4. `_onchange_check_duplicate` advierte si ya existe schedule igual
5. Guardar → `create()` genera los intervalos definitivos en BD

**Edge cases**:
- Turno partido (ej: "Oficina" 08-12 y 14-18): genera 2 intervalos
- Turno nocturno (`hora_fin <= hora_ini`): `es_nocturno=True`, `fecha_fin = fecha + 1`
- Click en día diferente al mes visible: `default_date` evita desfase de fecha

### 4.2 Schedule Creation (Direct Interval Click)

**Actor**: Supervisor
**Trigger**: Click directo en calendario de intervalos
**Behavior**:
1. Click en fecha/hora del calendario de intervalos
2. Formulario pre-poblado con `agent_id`, `shift_id`, `fecha`, `hora_ini`, `hora_fin`
3. Si `schedule_id` vacío y tiene `shift_id`: `create()` del intervalo crea el schedule padre automáticamente
4. Schedule padre recibe los intervalos del turno (no los ingresados en el form)

### 4.3 Batch Generation (Wizard)

**Actor**: Supervisor
**Trigger**: Menú → "Generar Turnos en Lote"
**Behavior**:
1. Seleccionar rango de fechas, área
2. Agregar líneas: agente + turno + días de semana (checkboxes Lunes-Domingo)
3. `action_generate()` itera cada día del rango:
   - Filtra por `day_week` (weekday 0-6)
   - Busca schedules existentes para skip duplicates
   - Crea schedules con `state='draft'`
4. Al finalizar, abre tree con los schedules creados

### 4.4 API: On Duty

**Actor**: Sistema externo (n8n)
**Endpoint**: `GET /galgo/schedule/on_duty`
**Auth**: Header `X-API-Key`

**Parameters**:
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `fecha` | string | hoy | YYYY-MM-DD |
| `hora` | string | ahora | HH:MM |
| `area_code` | string | todas | Filter by area |
| `nivel_code` | string | todos | Filter by nivel |
| `solo_confirmados` | string | true | Filter by state=confirmado |

**Logic**:
1. Busca schedules del día + día anterior (para nocturnos)
2. Si schedule.fecha == ayer y es nocturno: solo incluir si `hora` < `hora_fin`
3. Para cada schedule: verifica si `hora` está dentro de algún intervalo (`_is_on_shift`)
4. Retorna array de agentes disponibles con metadata

### 4.5 API: Areas

**Actor**: Sistema externo
**Endpoint**: `GET /galgo/schedule/areas`
**Auth**: Ninguna

**Response**: Lista de áreas con sus niveles (id, code, name, secuencia).

---

## 5. User Interface

### 5.1 Calendar View (Primary)

```
┌─────────────────────────────────────────────────────────────┐
│ Calendario de Turnos                          [+ New] [≡]   │
├─────────────────────────────────────────────────────────────┤
│<   Mayo 2026   >                                             │
├─────────────────────────────────────────────────────────────┤
│ Lu  Ma  Mi  Ju  Vi  Sa  Do                                   │
│                                     1                        │
│  4   5   6   7   8   9  10                                   │
│ 11  12  13  14 [15] 16  17  ← usuario clickeó 15              │
│ 18  19  20  21  22  23  24                                  │
│ 25  26  27  28  29  30  31                                  │
└─────────────────────────────────────────────────────────────┘
```

- Click en día → abre form con fecha = día clickeado
- Eventos mostrados con color del turno
- Modo month por defecto

### 5.2 Form View (Schedule)

```
┌─────────────────────────────────────────────────────────────┐
│ Turno Asignado                                    [Confirmar]│
├─────────────────────────────────────────────────────────────┤
│ ┌─────────────┐  ┌─────────────┐                             │
│ │ Agente      │  │ Hora Inicio │                             │
│ │ Juan Pérez  │  │ 08:00       │                             │
│ ├─────────────┤  ├─────────────┤                             │
│ │ Fecha       │  │ Hora Fin    │                             │
│ │ 2026-05-15  │  │ 18:00       │                             │
│ ├─────────────┤  ├─────────────┤                             │
│ │ Turno       │  │ Duración    │                             │
│ │ Oficina  ●  │  │ 08:00       │                             │
│ └─────────────┘  └─────────────┘                             │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ Intervalos de Horario                           [Edit]  │ │
│ ├─────────────────────────────────────────────────────────┤ │
│ │  hora_ini   │   hora_fin  │                              │ │
│ │  08:00      │   12:00     │  ━━━━ bloque mañana          │ │
│ │  14:00      │   18:00     │  ━━━━ bloque tarde          │ │
│ └─────────────────────────────────────────────────────────┘ │
│ Notas:                                                        │
│ ____________________________________________________________ │
│                                           [Guardar] [Cancel] │
└─────────────────────────────────────────────────────────────┘
```

### 5.3 Interval Calendar (Split Shifts)

Calendario separado que muestra cada intervalo como evento individual, permitiendo ver los bloques de turnos partidos como eventos separados.

### 5.4 Batch Wizard

```
┌─────────────────────────────────────────────────────────────┐
│ Generar Turnos en Lote                                       │
├─────────────────────────────────────────────────────────────┤
│ Fecha Inicio: [15/05/2026]  Fecha Fin: [31/05/2026]         │
│ Área: [NOC ▼]                                               │
├─────────────────────────────────────────────────────────────┤
│ Líneas de Configuración                                     │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ Agente      │ Turno      │ Días                         │ │
│ │ Juan Pérez  │ Oficina ▼  │ ☐Lu ☐Ma ☑Mi ☐Ju ☐Vi ☐Sa ☐Do│ │
│ │ María García│ Mañana ▼  │ ☐Lu ☑Ma ☑Mi ☑Ju ☑Vi ☐Sa ☐Do│ │
│ └─────────────────────────────────────────────────────────┘ │
│ [+ Agregar Línea]                                           │
│                                              [Generar]       │
└─────────────────────────────────────────────────────────────┘
```

---

## 6. API Reference

### 6.1 GET /galgo/schedule/on_duty

**Request**:
```bash
curl -H "X-API-Key: YOUR_KEY" \
  "http://localhost:8069/galgo/schedule/on_duty?fecha=2026-05-30&hora=10:00&area_code=noc"
```

**Response** (200 OK):
```json
{
  "status": "ok",
  "fecha": "2026-05-30",
  "hora": "10:00",
  "area": "noc",
  "agentes_disponibles": [
    {
      "nombre": "Juan Pérez",
      "chatwoot_agent_id": 42,
      "area": "noc",
      "area_nombre": "Network Operations Center",
      "nivel_code": "n1",
      "nivel_nombre": "Nivel 1",
      "turno": "Oficina",
      "hora_ini": "08:00",
      "hora_fin": "18:00"
    }
  ],
  "total": 1,
  "hay_disponibles": true
}
```

**Error (401)**:
```json
{"status": "error", "message": "API Key inválida"}
```

### 6.2 GET /galgo/schedule/areas

**Request**:
```bash
curl "http://localhost:8069/galgo/schedule/areas"
```

**Response** (200 OK):
```json
{
  "status": "ok",
  "areas": [
    {
      "id": 1,
      "code": "noc",
      "name": "Network Operations Center",
      "niveles": [
        {"id": 1, "code": "n1", "name": "Nivel 1", "secuencia": 1},
        {"id": 2, "code": "n2", "name": "Nivel 2", "secuencia": 2}
      ]
    },
    {
      "id": 2,
      "code": "ventas",
      "name": "Ventas",
      "niveles": []
    }
  ],
  "total": 2
}
```

---

## 7. Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `galgo_agent_schedule.api_key` | (empty) | API key for `/on_duty`. Empty = allow all |
| `galgo_agent_schedule.timezone` | America/Bogota | Timezone for datetime calculations |

Configurable via: Settings → Technical → System Parameters

---

## 8. Security / Access Control

### Groups

| Group | Schedule CRUD | Wizard | Interval View | Area/Nivel CRUD |
|-------|--------------|-------|---------------|-----------------|
| Viewer | Read only | No | Yes | No |
| User | Create own | No | Yes | No |
| Manager | Full | Yes | Yes | No |
| Admin | Full | Yes | Yes | Yes |

### Access Records (ir.model.access.csv)

- Viewer: `perm_read=1` only
- User: `perm_read=1, perm_write=1, perm_create=1`
- Manager: `perm_read=1, perm_write=1, perm_create=1, perm_unlink=1`
- Admin: same as Manager + access to area/nivel models

---

## 9. Known Issues / Gotchas

1. **`schedule_id` doesn't exist on `galgo.agent.schedule`**
   - `action_open_schedule` must use `self.id`, not `self.schedule_id.id`
   - `schedule_id` belongs to `galgo.agent.schedule.interval`

2. **`default_datetime_start` is unreliable in month view**
   - When clicking a day cell in month view, Odoo passes the datetime of the *visible month start*, not the clicked day
   - **Fix**: Use `default_date` context instead

3. **`area_id`, `nivel_id` empty on historical records**
   - These are stored related fields that weren't populated during initial creation
   - **Fix**: Run SQL UPDATE or recreate records via wizard

4. **Demo data for `galgo.dia.semana` lives in `data/galgo_dia_semana_data.xml`**
   - NOT in wizard views XML

5. **Two fields with label "Turno" on `galgo.agent.schedule.interval`**
   - `schedule_id` and `shift_id` both have `string="Turno"` → warning in logs
   - Currently not fixed (cosmetic only)

---

## 10. Testing Checklist

### Functional Tests

- [ ] **TC-1**: Create schedule by clicking calendar day → fecha correcta
- [ ] **TC-2**: Create schedule with split-shift template (2+ intervals) → intervals generated correctly
- [ ] **TC-3**: Create schedule with night shift (18:00-06:00) → `es_nocturno=True`, `fecha_fin = fecha + 1`
- [ ] **TC-4**: Duplicate schedule warning appears when creating duplicate
- [ ] **TC-5**: Batch wizard generates schedules for correct days of week
- [ ] **TC-6**: Batch wizard skips existing schedules (no duplicates)
- [ ] **TC-7**: `/on_duty` returns correct agents for given fecha/hora
- [ ] **TC-8**: `/on_duty` filters by area_code and nivel_code
- [ ] **TC-9**: `/on_duty` handles night shifts spanning midnight
- [ ] **TC-10**: `/on_duty` requires valid API key (or returns 401)
- [ ] **TC-11**: `/areas` returns all active areas with niveles
- [ ] **TC-12**: View schedule interval from interval calendar → opens parent schedule form

### Non-Functional Tests

- [ ] **NFT-1**: Module updates without errors (`docker exec ... -i galgo_agent_schedule`)
- [ ] **NFT-2**: All tests pass (`--test-tags=galgo_agent_schedule`)
- [ ] **NFT-3**: Access control enforced (viewer can't create, etc.)

---

## 11. File Structure

```
galgo_agent_schedule/
├── __init__.py
├── __manifest__.py
├── models/
│   ├── __init__.py
│   ├── galgo_area.py              # galgo.area model
│   ├── galgo_nivel_atencion.py    # galgo.nivel.atencion model
│   ├── galgo_agent.py             # galgo.agent model
│   ├── galgo_shift_template.py    # galgo.shift.template + galgo.shift.interval
│   ├── galgo_agent_schedule.py    # galgo.agent.schedule + galgo.agent.schedule.interval
│   └── res_config_settings.py     # Settings form
├── wizard/
│   ├── __init__.py
│   └── galgo_schedule_wizard.py   # Batch generation wizard
├── controllers/
│   ├── __init__.py
│   └── schedule_api.py            # REST API
├── views/
│   ├── galgo_area_views.xml
│   ├── galgo_nivel_atencion_views.xml
│   ├── galgo_agent_views.xml
│   ├── galgo_shift_template_views.xml
│   ├── galgo_agent_schedule_views.xml
│   ├── res_config_settings_views.xml
│   └── menu.xml
├── data/
│   ├── galgo_area_data.xml
│   ├── galgo_nivel_data.xml
│   ├── galgo_shift_template_data.xml
│   └── galgo_dia_semana_data.xml
├── security/
│   ├── ir.model.access.csv
│   └── ir.access_groups_xml.yaml
├── tests/
│   ├── __init__.py
│   └── test_schedule.py
├── AGENTS.md                      # AI agent instructions
└── README.md
```

---

## 12. Out of Scope / Future

- Reporting/analytics (coverage maps, horas por agente)
- Integration with Chatwoot API para verificar agente online
- Asignación automática de turnos (algoritmo de rotación)
- Notificaciones a agentes cuando se les asigna turno
- Turnos recurrentes (RRULE-like)
- Multi-company support

---

## 12. Goals

- [x] **G-1**: Unificar vista calendario para turnos sencillos y partidos — dejar SOLO `galgo_agent_schedule_view_calendar` (usando `interval_ids` para mostrar bloques en calendario de intervalos). Eliminar `galgo_agent_schedule_interval_view_calendar` y el menú separado "Ver Intervalos (Turnos Partidos)". ✓ (May 2026)

---

## Appendix A: SQL Fix for Historical Records

If `area_id`, `nivel_id`, `chatwoot_agent_id` are empty on historical `galgo.agent.schedule` records:

```sql
UPDATE galgo_agent_schedule SET
  area_id = (SELECT area_id FROM galgo_agent WHERE id = galgo_agent_schedule.agent_id),
  nivel_id = (SELECT nivel_id FROM galgo_agent WHERE id = galgo_agent_schedule.agent_id),
  chatwoot_agent_id = (SELECT chatwoot_agent_id FROM galgo_agent WHERE id = galgo_agent_schedule.agent_id)
WHERE area_id IS NULL OR area_id = 0;
```

---

## Appendix B: Quick Reference Commands

```bash
# Update module
docker restart odoo && docker exec -u 0 odoo odoo -c /etc/odoo/odoo.conf -d galgo -i galgo_agent_schedule --test-enable --stop-after-init

# Run tests
docker exec odoo odoo -c /etc/odoo/odoo.conf --test-tags=galgo_agent_schedule --stop-after-init

# API test (on_duty)
curl -H "X-API-Key: YOUR_KEY" "http://localhost:8069/galgo/schedule/on_duty?fecha=2026-05-30&hora=10:00"

# API test (areas)
curl "http://localhost:8069/galgo/schedule/areas"
```

---

*Document version: 1.0 — Mayo 2026*
*Last updated: 2026-05-29 after fixing default_date context bug*