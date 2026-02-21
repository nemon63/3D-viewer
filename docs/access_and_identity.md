# Access and Identity Strategy

Last update: 2026-02-21

## EN

### 1. Authentication model
1. Preferred enterprise path: AD/LDAP/SSO integration.
2. MVP fallback: local users with secure password hash (argon2/bcrypt).
3. No self-registration in production mode; admin-provisioned accounts.

### 2. Roles
1. Reader: browse and inspect.
2. Analyst: shortlist and export request operations.
3. Animator/Modeler: update asset/animation production states.
4. Lead/Reviewer: approve/reject and validation governance.
5. Admin: user/role/system administration.

### 3. Permission matrix (minimum)
1. `can_open_asset`
2. `can_edit_overrides`
3. `can_create_request`
4. `can_review_animation`
5. `can_export_package`
6. `can_manage_users`

### 4. Session model
1. Session starts at login and ends at logout/timeout.
2. Session stores:
`user_id`, `host`, `app_version`, `started_at`, `ended_at`.
3. Every auditable action references session id.

### 5. Operational policy
1. First login requires password reset (if local auth).
2. Password complexity and rotation policy is documented.
3. Inactive users are disabled, not deleted.

---

## RU

### 1. Модель аутентификации
1. Предпочтительный enterprise-путь: AD/LDAP/SSO.
2. MVP fallback: локальные пользователи с безопасным hash пароля (argon2/bcrypt).
3. Саморегистрация в production не используется; аккаунты выдает админ.

### 2. Роли
1. Reader: просмотр.
2. Analyst: отбор и операции подготовки выдачи.
3. Animator/Modeler: обновление статусов ассетов/анимаций.
4. Lead/Reviewer: утверждение/отклонение и контроль валидации.
5. Admin: управление пользователями/ролями/системой.

### 3. Минимальная матрица прав
1. `can_open_asset`
2. `can_edit_overrides`
3. `can_create_request`
4. `can_review_animation`
5. `can_export_package`
6. `can_manage_users`

### 4. Модель сессии
1. Сессия начинается при логине и заканчивается при logout/timeout.
2. В сессии хранить:
`user_id`, `host`, `app_version`, `started_at`, `ended_at`.
3. Каждое аудит-событие ссылается на id сессии.

### 5. Операционная политика
1. На первом входе обязательная смена пароля (для локальной auth).
2. Политика сложности и ротации паролей документирована.
3. Неактивные пользователи отключаются, а не удаляются.
