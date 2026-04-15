"""RDF triple generation for Oxigraph from parsed notes."""

from __future__ import annotations

from datetime import datetime
from urllib.parse import quote

from exocortex.core.markdown_parser import ParsedNote

# Namespace prefixes
EX = "http://exocortex.local/ontology#"
EXN = "http://exocortex.local/note/"
SCHEMA = "http://schema.org/"
RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
RDFS = "http://www.w3.org/2000/01/rdf-schema#"
XSD = "http://www.w3.org/2001/XMLSchema#"
DCTERMS = "http://purl.org/dc/terms/"
SKOS = "http://www.w3.org/2004/02/skos/core#"

ONTOLOGY_TURTLE = """\
@prefix ex:     <http://exocortex.local/ontology#> .
@prefix exn:    <http://exocortex.local/note/> .
@prefix schema: <http://schema.org/> .
@prefix rdf:    <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs:   <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd:    <http://www.w3.org/2001/XMLSchema#> .
@prefix dcterms: <http://purl.org/dc/terms/> .
@prefix skos:   <http://www.w3.org/2004/02/skos/core#> .

ex:Note a rdfs:Class ;
    rdfs:subClassOf schema:CreativeWork ;
    rdfs:label "Knowledge Note" .

ex:Tag a rdfs:Class ;
    rdfs:subClassOf skos:Concept ;
    rdfs:label "Tag" .

ex:Folder a rdfs:Class ;
    rdfs:subClassOf schema:Collection ;
    rdfs:label "Folder" .

ex:linksTo a rdf:Property ;
    rdfs:domain ex:Note ;
    rdfs:range ex:Note ;
    rdfs:label "Wikilink" .

ex:hasTag a rdf:Property ;
    rdfs:domain ex:Note ;
    rdfs:range ex:Tag .

ex:inFolder a rdf:Property ;
    rdfs:domain ex:Note ;
    rdfs:range ex:Folder .

ex:confidence a rdf:Property ;
    rdfs:domain ex:Note ;
    rdfs:range xsd:integer ;
    rdfs:label "Confidence Level (1-5)" .

ex:hasLocation a rdf:Property ;
    rdfs:domain ex:Note ;
    rdfs:range schema:GeoCoordinates .

ex:agentAnnotation a rdf:Property ;
    rdfs:domain ex:Note ;
    rdfs:range xsd:string ;
    rdfs:label "AI Agent Annotation" .

ex:HAEntity a rdfs:Class ;
    rdfs:label "Home Assistant Entity" .

ex:AgentDecision a rdfs:Class ;
    rdfs:label "Agent Decision Record" .

ex:lastState a rdf:Property ;
    rdfs:domain ex:HAEntity ;
    rdfs:range xsd:string .

ex:lastChanged a rdf:Property ;
    rdfs:domain ex:HAEntity ;
    rdfs:range xsd:dateTime .

ex:agent a rdf:Property ;
    rdfs:domain ex:AgentDecision ;
    rdfs:range xsd:string .

ex:triggeredBy a rdf:Property ;
    rdfs:domain ex:AgentDecision ;
    rdfs:range ex:HAEntity .

ex:decidedAction a rdf:Property ;
    rdfs:domain ex:AgentDecision ;
    rdfs:range xsd:string .

ex:decisionReasoning a rdf:Property ;
    rdfs:domain ex:AgentDecision ;
    rdfs:range xsd:string .
"""


def _escape_turtle_string(s: str) -> str:
    """Escape a string for use in Turtle format."""
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r")


def _note_uri(path: str) -> str:
    """Generate URI for a note."""
    return f"<{EXN}{quote(path, safe='/')}>"


def _tag_uri(tag: str) -> str:
    """Generate URI for a tag."""
    return f"<http://exocortex.local/tag/{quote(tag)}>"


def _folder_uri(folder: str) -> str:
    """Generate URI for a folder."""
    return f"<http://exocortex.local/folder/{quote(folder)}>"


def note_to_triples(path: str, note: ParsedNote) -> str:
    """Generate Turtle triples for a single note."""
    uri = _note_uri(path)
    lines: list[str] = []

    lines.append(f"{uri} a <{EX}Note> .")
    lines.append(f'{uri} <{SCHEMA}name> "{_escape_turtle_string(note.title)}" .')

    if note.modified:
        lines.append(f'{uri} <{DCTERMS}modified> "{note.modified}"^^<{XSD}dateTime> .')
    if note.created:
        lines.append(f'{uri} <{DCTERMS}created> "{note.created}"^^<{XSD}dateTime> .')

    if note.confidence:
        lines.append(f'{uri} <{EX}confidence> "{note.confidence}"^^<{XSD}integer> .')

    # Folder
    folder = str(path).rsplit("/", 1)[0] if "/" in str(path) else ""
    if folder:
        lines.append(f"{uri} <{EX}inFolder> {_folder_uri(folder)} .")

    # Tags
    for tag in note.tags:
        lines.append(f"{uri} <{EX}hasTag> {_tag_uri(tag)} .")
        lines.append(f'{_tag_uri(tag)} a <{EX}Tag> ; <{SCHEMA}name> "{_escape_turtle_string(tag)}" .')

    # Aliases
    for alias in note.aliases:
        lines.append(f'{uri} <{SKOS}altLabel> "{_escape_turtle_string(alias)}" .')

    # Wikilinks
    for link in note.wikilinks:
        # Resolve wikilink to path (simple: assume .md extension)
        link_path = link if link.endswith(".md") else f"{link}.md"
        lines.append(f"{uri} <{EX}linksTo> {_note_uri(link_path)} .")

    # Geo location
    if note.location:
        lat, lon = note.location
        bnode = f"_:geo_{hash(path) & 0xFFFFFFFF}"
        lines.append(f"{uri} <{EX}hasLocation> {bnode} .")
        lines.append(f"{bnode} a <{SCHEMA}GeoCoordinates> .")
        lines.append(f'{bnode} <{SCHEMA}latitude> "{lat}"^^<{XSD}decimal> .')
        lines.append(f'{bnode} <{SCHEMA}longitude> "{lon}"^^<{XSD}decimal> .')

    # Status
    if note.status:
        lines.append(f'{uri} <{EX}status> "{_escape_turtle_string(note.status)}" .')

    return "\n".join(lines)


def build_sparql_delete(path: str) -> str:
    """Generate SPARQL UPDATE to delete all triples for a note."""
    uri = _note_uri(path)
    return f"DELETE WHERE {{ {uri} ?p ?o . }}"


def build_sparql_insert(path: str, note: ParsedNote) -> str:
    """Generate SPARQL UPDATE to insert triples for a note."""
    triples = note_to_triples(path, note)
    # Convert Turtle to SPARQL INSERT DATA
    return f"INSERT DATA {{\n{triples}\n}}"


def build_sparql_upsert(path: str, note: ParsedNote) -> str:
    """Generate SPARQL UPDATE to replace all triples for a note (delete + insert)."""
    delete = build_sparql_delete(path)
    insert = build_sparql_insert(path, note)
    return f"{delete};\n{insert}"
