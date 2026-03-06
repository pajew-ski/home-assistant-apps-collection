# Oxigraph

SPARQL 1.1 triple store und RDF-Graphdatenbank mit eingebautem
[YASGUI](https://yasgui.triply.cc/)-Query-Interface.

## Web-Oberfläche

Die YASGUI-Oberfläche ist immer über die **Home-Assistant-Seitenleiste**
erreichbar (Ingress). Es sind keine zusätzlichen Port-Freigaben nötig.

## Externer Zugriff (SPARQL-Clients, APIs)

Standardmäßig ist Oxigraph nur innerhalb von Home Assistant erreichbar.
Um es auch aus dem Netzwerk (z. B. für SPARQL-Clients) zugänglich zu machen:

1. **`auth_type`** auf `basic` oder `bearer` setzen und Zugangsdaten eintragen
   (bei `none` erscheint eine Warnung – Oxigraph hat keinen eigenen Passwortschutz).
2. **`network_access`** auf `true` setzen.
3. In den Add-on-Einstellungen unter **Netzwerk** den Host-Port für
   `7878/tcp` eintragen (z. B. `7878`).

### Auth-Optionen

| `auth_type` | Zugangsdaten | Beschreibung |
|-------------|--------------|--------------|
| `none`      | –            | Kein Schutz. Nur für lokale Tests geeignet. |
| `basic`     | `username` + `password` | HTTP Basic Auth (Browser-Dialog). |
| `bearer`    | `bearer_token` | `Authorization: Bearer <token>` Header. Ideal für SPARQL-Clients. |

### SPARQL-Endpunkte (wenn externer Zugriff aktiv)

| Endpunkt | Methode | Zweck |
|----------|---------|-------|
| `http://<ha-ip>:7878/query` | GET / POST | SPARQL SELECT / ASK / CONSTRUCT |
| `http://<ha-ip>:7878/update` | POST | SPARQL UPDATE |
| `http://<ha-ip>:7878/store` | GET / POST / PUT | Graph Store Protocol |
| `http://<ha-ip>:7878/` | GET | YASGUI Web-UI |

## Datenpersistenz

Alle RDF-Daten werden in `/data/storage` gespeichert und bleiben bei
Updates und Neustarts erhalten.

## Sicherheitshinweis

Oxigraph selbst hat **keine eingebaute Authentifizierung**. Wer Port 7878
ohne Auth-Schutz freigibt, gibt vollen Lese- und Schreibzugriff auf den
Triple Store frei. Aktiviere immer `auth_type=basic` oder `auth_type=bearer`
bevor du `network_access=true` setzt.
