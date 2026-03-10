# Metabase Analytics

Business-Intelligence und Datenanalyse direkt in Home Assistant.
[Metabase](https://www.metabase.com/) ist ein Open-Source-BI-Tool, das
SQL-Datenbanken visuell aufbereitet – Diagramme, Dashboards, Abfragen.

## Erste Schritte

1. Add-on installieren und starten.
2. Metabase oeffnet sich automatisch ueber die **HA-Seitenleiste** (Ingress).
3. Du bist bereits eingeloggt – kein separates Metabase-Passwort noetig.

## Datenbank verbinden

### PostgreSQL / MySQL (empfohlen)

Wenn dein HA Recorder eine externe Datenbank nutzt, wird sie automatisch
verbunden. Stelle sicher, dass `recorder_db_url` in den Add-on-Optionen
gesetzt ist, z. B.:

```
postgresql://user:password@localhost:5432/homeassistant
```

Das Add-on erkennt auch automatisch die `db_url` aus deiner
`configuration.yaml`, falls sie dort konfiguriert ist.

### SQLite (Standard)

Die Standard-SQLite-Datenbank von HA kann nicht automatisch verbunden
werden (Dateisystem-Einschraenkungen). Fuer Analysen mit Metabase wird
empfohlen, auf PostgreSQL oder MySQL umzusteigen.

Du kannst die Datenbank aber manuell in der Metabase-Oberflaeche
hinzufuegen, wenn du weisst was du tust.

## Optionen

| Option | Standard | Beschreibung |
|--------|----------|--------------|
| `recorder_db_url` | *(leer)* | Recorder-DB-URL (auto-detect aus configuration.yaml wenn leer) |
| `java_memory` | `1g` | Maximaler Java-Heap fuer Metabase (z. B. `512m`, `2g`) |
| `theme_sync` | `true` | HA-Farbschema auf Metabase anwenden |

## Speicher

- Metabase-Konfiguration wird in `/data/metabase.db` gespeichert
  und ueberlebt Neustarts und Updates.
- Mindestens **1 GB RAM** empfohlen (2 GB fuer groessere Datenbanken).

## Dashboards in Lovelace einbetten

Metabase kann Dashboards als oeffentliche Links teilen:

1. Oeffne ein Dashboard in Metabase.
2. Klicke auf **Teilen** → **Oeffentlicher Link**.
3. Kopiere die URL.
4. Fuege eine **Webpage Card** in Lovelace hinzu mit der URL.

## Sicherheit

- Metabase ist **nur ueber HA Ingress** erreichbar (kein offener Port).
- Der Admin-Account wird automatisch erstellt und verwaltet.
- Die Zugangsdaten liegen in `/data/admin.json` (nur root-lesbar).
- Alle API-Zugriffe laufen ueber den HA Supervisor Proxy.

## Fehlerbehebung

### Metabase startet nicht

Pruefe das Add-on-Log. Haeufige Ursachen:
- Zu wenig RAM: Erhoehe `java_memory` auf `2g`.
- Port-Konflikt: Stelle sicher, dass kein anderes Add-on Port 8099 nutzt.

### Datenbank wird nicht verbunden

- Pruefe, ob die `recorder_db_url` korrekt ist.
- PostgreSQL/MySQL muessen vom Add-on-Container aus erreichbar sein.
- Netzwerk-Addons (z. B. MariaDB Add-on) nutzen den Hostnamen
  `core-mariadb` im HA-Netzwerk.

### Session abgelaufen

Das Add-on erneuert die Session automatisch alle 6 Stunden. Falls du
trotzdem einen Login-Screen siehst, starte das Add-on neu.
