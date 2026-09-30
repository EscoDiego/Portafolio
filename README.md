# TeamFlow — gestor de tareas para equipos

Aplicación full-stack para organizar proyectos, tareas y progreso colaborativo. El primer usuario registrado recibe el rol de **administrador**; los demás son miembros. Administradores y propietarios de proyecto pueden administrar proyectos y tareas.

## Inicio rápido

Necesitas Docker Desktop. Desde la raíz ejecuta:

```bash
docker compose up --build
```

Abre `http://localhost:5173`. Crea la primera cuenta y añade un proyecto y tareas. La documentación interactiva de la API queda disponible en `http://localhost:8000/docs`.

## Arquitectura

- `frontend/`: React + Vite, tablero Kanban responsive y filtros por estado.
- `backend/`: FastAPI, JWT, roles y CRUD de proyectos/tareas.
- `db`: PostgreSQL 16 persistido en un volumen Docker.

## API principal

| Área | Rutas |
| --- | --- |
| Autenticación | `POST /auth/register`, `POST /auth/login`, `GET /auth/me` |
| Proyectos | `GET/POST /projects`, `PUT/DELETE /projects/{id}` |
| Tareas | `GET/POST /projects/{id}/tasks`, `PUT/DELETE /tasks/{id}` |

Para producción, configura `SECRET_KEY`, credenciales de PostgreSQL y `CORS_ORIGINS` como secretos del proveedor. Puedes desplegar los tres servicios en Render, Railway, Fly.io o cualquier plataforma con Docker Compose/servicios de contenedor.

