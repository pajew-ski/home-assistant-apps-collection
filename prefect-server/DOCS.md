# Prefect Server

[Prefect](https://www.prefect.io/) ist ein modernes Workflow-Orchestrierungs-Framework
fuer Python. Dieses Add-on betreibt den **Prefect Server v3** direkt in Home Assistant
und stellt das vollstaendige Dashboard ueber die Sidebar (Ingress) bereit.

## Web-Oberflaeche

Das Prefect-Dashboard ist nach der Installation direkt ueber die Home-Assistant-Sidebar
erreichbar (**Prefect**). Es ist keine Port-Freigabe noetig – der Zugriff laeuft
ueber den HA-Ingress und ist automatisch durch die HA-Authentifizierung geschuetzt.

Funktionen des Dashboards:
- Flow Runs ueberwachen und inspizieren
- Deployments verwalten und ausloesen
- Work Pools und Worker konfigurieren
- Automationen und Benachrichtigungen einrichten
- Logs und Artefakte einsehen

## Externer Zugriff (Worker, CI/CD, Remote-Clients)

Fuer die Verbindung von Prefect-Workern oder Remote-Clients zur API:

### Voraussetzungen

1. **auth_type** in den Add-on-Optionen auf `basic` oder `bearer` setzen
2. **network_access** aktivieren
3. Port **4200** in den Home-Assistant-Netzwerkeinstellungen freigeben

### Authentifizierungsoptionen

| Modus    | Konfiguration                    | Beschreibung                       |
|----------|----------------------------------|------------------------------------|
| `none`   | –                                | Kein Schutz (nicht empfohlen!)     |
| `basic`  | `username` + `password`          | HTTP Basic Authentication          |
| `bearer` | `bearer_token`                   | Bearer Token im Authorization-Header |

### Worker-Verbindung

Sobald der externe Zugriff aktiv ist, kann ein Worker so verbunden werden:

```bash
export PREFECT_API_URL="http://<ha-ip>:4200/api"
prefect worker start --pool 'my-pool'
```

Bei Bearer-Auth muss der Header manuell gesetzt werden oder ein Reverse-Proxy
die Authentifizierung uebernehmen.

## API-Endpunkte

| Pfad         | Beschreibung                        |
|--------------|-------------------------------------|
| `/api/`      | Prefect REST API                    |
| `/api/health`| Health-Check-Endpunkt               |
| `/`          | Prefect UI (Dashboard)              |

## Datenpersistenz

Alle Daten (SQLite-Datenbank, Logs, Konfiguration) werden unter `/data/prefect/`
gespeichert und ueberleben Neustarts und Updates des Add-ons.

## Sicherheitshinweis

Wenn `network_access` aktiviert und `auth_type` auf `none` gesetzt ist, ist die
Prefect-API **ohne jegliche Authentifizierung** ueber Port 4200 erreichbar.
Jeder im Netzwerk kann dann Flows erstellen, aendern und ausfuehren. Nutze
`basic` oder `bearer` um die API abzusichern.

## Ressourcenverbrauch

Prefect Server benoetigt ca. **300-500 MB RAM** im Leerlauf. Bei vielen
gleichzeitigen Flow Runs kann der Verbrauch steigen. Empfohlen wird ein System
mit mindestens 2 GB freiem Arbeitsspeicher.
