# Wikipedia Pulse

Counts the public edit stream of every Wikimedia wiki
([EventStreams](https://wikitech.wikimedia.org/wiki/Event_Platform/EventStreams_HTTP_Service),
`mediawiki.recentchange`) in one long-lived connection and serves the result as
JSON. Nothing to configure; no account or key.

## What it serves

`GET http://037accb4-wikipedia-pulse:8104/` from Home Assistant (the add-on's
host name on the internal network; there is no port on the host):

| Field | Meaning |
|---|---|
| `per_minute` | Edits per minute over the last five minutes: `all`, `humans`, `bots`, `new` (page creations), and `dewiki`, `enwiki`, `wikidatawiki`, `commonswiki` |
| `hot.dewiki`, `hot.enwiki` | Up to ten articles with the most distinct human editors in the last hour (at least two), with `edits` and `editors` |
| `connected`, `last_event`, `reconnects` | State of the stream connection |
| `warm` | `false` during the first five minutes after a start, while the rate window fills |

Many people editing one article at the same time is how breaking news shows
up in Wikipedia, often before the page views move.

## Example sensor

```yaml
rest:
  - resource: http://037accb4-wikipedia-pulse:8104/
    scan_interval: 60
    sensor:
      - name: Wikipedia edits per minute
        unique_id: wikipedia_pulse_all
        value_template: "{{ value_json.per_minute.all }}"
        availability: "{{ value_json.connected }}"
        unit_of_measurement: edits/min
        state_class: measurement
```

## Deutsch

Zählt den öffentlichen Bearbeitungsstrom aller Wikimedia-Wikis und gibt ihn als
JSON aus: Bearbeitungen je Minute (alle, Menschen, Bots, neue Seiten, große
Wikis) und je für de und en die Artikel mit den meisten verschiedenen
menschlichen Bearbeitern der letzten Stunde. Abgefragt wird er von Home
Assistant mit einem `rest`-Sensor unter `http://037accb4-wikipedia-pulse:8104/`.
