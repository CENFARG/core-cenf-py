# M24 MaintenanceManager — Spec

## Requirements

### REQ-M24-01: Consent Management (GDPR)
**GIVEN** un usuario sin consentimiento previo  
**WHEN** el adapter intenta capturar un error  
**THEN** el adapter verifica `is_consent_granted()` → False → NO envía datos  

**GIVEN** un usuario otorga consentimiento explícito  
**WHEN** se llama `request_consent()`  
**THEN** retorna ConsentResult con status=GRANTED y timestamp  

### REQ-M24-02: Error Capture
**GIVEN** consentimiento otorgado  
**WHEN** ocurre una excepción en la app  
**THEN** `capture_error()` produce ErrorReport con stack trace, app_id, version, OS  
**AND** PII (emails, tokens, passwords) es enmascarado con ***  

### REQ-M24-03: Report Error to GitHub
**GIVEN** un ErrorReport válido  
**WHEN** se llama `report_error()` con GitHubIssueAdapter  
**THEN** crea un issue en el repo privado con labels [bug-automático]  

### REQ-M24-04: Report Error to Discord
**GIVEN** un ErrorReport válido  
**WHEN** se llama `report_error()` con DiscordAlertAdapter  
**THEN** envía webhook con embed (stack trace truncado a 2000 chars)  

### REQ-M24-05: Telemetry (OTLP)
**GIVEN** consentimiento otorgado  
**WHEN** se llama `send_telemetry()`  
**THEN** envía métricas vía OTLP: app_id, version, OS, uptime, error_count  
**AND** datos de usuario son anonimizados (UUID en vez de email)  

### REQ-M24-06: Tail-based Sampling
**GIVEN** 100 errores en 1 minuto  
**WHEN** el adapter aplica tail-based sampling  
**THEN** solo se reportan errores con severidad > WARNING  
**AND** el resto se descarta para no saturar  

### REQ-M24-07: Consent Revocation
**GIVEN** un usuario revoca consentimiento  
**WHEN** se llama `revoke_consent()`  
**THEN** todos los datos de telemetría del usuario se purgan (derecho al olvido)  

### REQ-M24-08: Adapter Fallback
**GIVEN** GitHub API no disponible  
**WHEN** `report_error()` falla con GitHubIssueAdapter  
**THEN** el adapter hace fallback a DiscordAlertAdapter  
**AND** no crashea la app principal  

### REQ-M24-09: PII Scrubbing
**GIVEN** un stack trace con `email=user@example.com`  
**WHEN** `capture_error()` procesa el error  
**THEN** el campo `email` es reemplazado por `***`  
**AND** JWT tokens son truncados a primeros 10 chars + `...`  

### REQ-M24-10: InMemory Adapter
**GIVEN** tests unitarios  
**WHEN** se usa InMemoryMaintenanceAdapter  
**THEN** todos los errores se almacenan en memoria  
**AND** son recuperables para assertions de test
