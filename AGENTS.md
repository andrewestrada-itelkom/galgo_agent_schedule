# Galgo Agent Schedule

Odoo 16 module for visual rotational shift scheduling by area.

## Environment

- Odoo 16.0 running in Docker (`odoo:16`), port 8069
- Database: `galgo` on `odoodb:5432` (postgres:15)
- Config: `/etc/odoo/odoo.conf` (inside container)

## Setup

```bash
# Update module (recommended)
docker restart odoo && docker exec -u 0 odoo odoo -c /etc/odoo/odoo.conf -d galgo -i galgo_agent_schedule --test-enable --stop-after-init

# Install module
docker exec odoo odoo -c /etc/odoo/odoo.conf -i galgo_agent_schedule --stop-after-init
```

## Testing

```bash
# Run module tests
docker exec odoo odoo -c /etc/odoo/odoo.conf --test-tags=galgo_agent_schedule --stop-after-init
```

## Project structure

```
models/          # Core business logic
wizard/          # Batch generation wizard
controllers/     # REST API (schedule_api.py)
views/           # XML views and menus
data/            # Static data (areas, shifts, days)
security/        # Access control (CSV + XML rules)
tests/           # pytest-style TransactionCase tests
```

## Data model

```
galgo.area ───1:M──► galgo.agent ───1:M──► galgo.agent.schedule
                                                      └── galgo.agent.schedule.interval
galgo.shift.template ───1:M──► galgo.shift.interval
galgo.nivel.atencion ──M2O──► galgo.area (optional)
galgo.dia.semana ──M2M──► galgo.schedule.wizard.line
```

### Relationship between intervals

`galgo.shift.interval` and `galgo.agent.schedule.interval` have **NO direct relationship**. Both models relate to `galgo.shift.template` but in different ways:

```
galgo.shift.template ──1:N──► galgo.shift.interval (template intervals)
        │
        └──1:N──► galgo.agent.schedule ──1:N──► galgo.agent.schedule.interval (actual copies)
```

- `galgo.shift.interval` = template (e.g., "Office has 2 blocks: 08-12 and 14-18")
- `galgo.agent.schedule.interval` = actual copy for an agent on a specific date

When a schedule is created, the `create()` method reads `galgo.shift.interval` from the template and creates copies in `galgo.agent.schedule.interval`.

## REST API

- `GET /galgo/schedule/on_duty` — agents on duty (auth: `X-API-Key` header)
- `GET /galgo/schedule/areas` — list areas and levels (no auth)

## Key patterns

- Timezone handling via `pytz` + `ir.config_parameter` (`galgo_agent_schedule.timezone`)
- Night shifts: `hora_fin <= hora_ini` implies overnight
- Split shifts: multiple `interval_ids` per shift template
- Wizard batch: filters by `dias_semana.code` (string weekday 0-6)

## Gotchas

- `galgo.agent.schedule` does NOT have `schedule_id` — that field belongs to `galgo.agent.schedule.interval`
- `action_open_schedule` on schedule must use `self.id`, not `self.schedule_id.id`
- Demo data for days of week lives in `data/galgo_dia_semana_data.xml`, not in wizard views
- `area_id`, `nivel_id`, `chatwoot_agent_id` on `galgo.agent.schedule` are stored related fields. If historical records show empty area/nivel in API responses, run:
  ```sql
  UPDATE galgo_agent_schedule SET area_id = (
      SELECT area_id FROM galgo_agent WHERE id = galgo_agent_schedule.agent_id
  ), nivel_id = (
      SELECT nivel_id FROM galgo_agent WHERE id = galgo_agent_schedule.agent_id
  ), chatwoot_agent_id = (
      SELECT chatwoot_agent_id FROM galgo_agent WHERE id = galgo_agent_schedule.agent_id
  )
  WHERE area_id IS NULL OR area_id = 0;
  ```
