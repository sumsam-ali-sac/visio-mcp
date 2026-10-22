"""Generic (provider-neutral) kinds: flow, architecture, data, network, org and ERD shapes."""

from __future__ import annotations

from visio_mcp.catalog.model import Kind, Shape
from visio_mcp.catalog.stencils import (
    AZ_ENT,
    AZ_GEN,
    BASFLO,
    BASIC,
    CAN,
    CIRCLE,
    COMPS,
    DB,
    DIAMOND,
    ELL,
    HEX,
    NETSYM,
    ORGCH,
    PARA,
    PEOPLE,
    RECT,
    RR,
    SERVER,
)


def _g(name: str, description: str, category: str, geometry: str, glyph: str, *shapes: tuple[str, str]) -> Kind:
    """A generic kind."""
    return Kind(name, description, tuple(Shape(s, m) for s, m in shapes), category, geometry,
                None, None, glyph)


GENERIC_KINDS: tuple[Kind, ...] = (
    # --- flowchart / terminals ---
    _g("start", "Entry point of a flow (rounded terminator).", "terminal", "terminator", "", (BASFLO, "Start/End")),
    _g("end", "Exit point of a flow (rounded terminator).", "terminal", "terminator", "", (BASFLO, "Start/End")),
    _g("initial", "State machine initial pseudo state (filled dot).", "terminal", "circle", "", CIRCLE, ELL),
    _g("final", "State machine final pseudo state.", "terminal", "circle", "", CIRCLE, ELL),
    _g("process", "A step or action in a flow.", "flow", "rect", "", (BASFLO, "Process"), RECT),
    _g("subprocess", "A predefined process that is detailed elsewhere.", "flow", "subprocess", "", (BASFLO, "Subprocess"), RECT),
    _g("data", "Input or output data (parallelogram).", "flow", "parallelogram", "", (BASFLO, "Data"), PARA),
    _g("document", "A document or report.", "flow", "document", "", (BASFLO, "Document")),
    _g("manual", "A manual step done by a person.", "flow", "trapezoid", "", (BASIC, "Trapezoid")),
    _g("state", "A state in a state machine (rounded).", "flow", "rounded", "", RR),
    _g("decision", "A yes/no or branching question.", "decision", "decision", "", (BASFLO, "Decision"), DIAMOND),
    # --- software architecture (C4 style) ---
    _g("service", "A backend service or application component.", "compute", "rounded", "", RR),
    _g("microservice", "A small independently deployable service.", "compute", "rounded", "", RR),
    _g("component", "A component inside a container or application (C4 component).", "compute", "rounded", "", RR),
    _g("container", "A deployable app or data container (C4 container, e.g. SPA, API, DB).", "compute", "rounded", "", RR),
    _g("system", "A software system (C4 software system).", "compute", "rounded", "", RR),
    _g("worker", "A background worker or job processor.", "compute", "rounded", "", RR),
    _g("function", "A serverless function.", "compute", "rounded", "λ", RR),
    _g("cron", "A scheduled job or scheduler (cron, timer).", "compute", "rounded", "", RR),
    _g("cluster", "A container orchestration cluster such as Kubernetes.", "compute", "hexagon", "K8s", HEX),
    _g("ml-model", "A machine-learning model or inference endpoint.", "compute", "hexagon", "ML", HEX),
    _g("llm", "A large language model or AI assistant.", "compute", "hexagon", "AI", HEX),
    _g("api", "An API or web service endpoint.", "integration", "hexagon", "", HEX),
    _g("gateway", "An API gateway or protocol gateway.", "integration", "hexagon", "", HEX),
    _g("queue", "A message queue or broker.", "integration", "queue", "", PARA),
    _g("topic", "A pub/sub topic or event stream (Kafka, Event Hubs, Kinesis).", "integration", "queue", "", PARA),
    _g("etl", "An ETL / data integration job or pipeline.", "integration", "hexagon", "ETL", HEX),
    _g("email", "An email service (SMTP, transactional mail).", "integration", "rounded", "@", RR),
    _g("notification", "A notification or push service (SMS, push, chat alerts).", "integration", "rounded", "", RR),
    # --- data ---
    _g("database", "A database or data store (cylinder).", "data", "cylinder", "", DB, (NETSYM, "Relational database"), CAN),
    _g("cache", "An in-memory cache such as Redis or Memcached.", "data", "cylinder", "", CAN),
    _g("storage", "Object, blob or file storage.", "data", "cylinder", "", CAN),
    _g("data-warehouse", "An analytical data warehouse.", "data", "cylinder", "DW", CAN),
    _g("data-lake", "A data lake for raw and curated data.", "data", "cylinder", "", CAN),
    _g("search", "A search index or engine (Elasticsearch, OpenSearch).", "data", "cylinder", "", CAN),
    _g("vector-db", "A vector database for embeddings.", "data", "cylinder", "", CAN),
    _g("repo", "A source code (git) repository.", "data", "rounded", "", RR),
    _g("registry", "A container or package registry.", "data", "rounded", "", RR),
    _g("artifact", "A build artifact or package.", "data", "rounded", "", RR),
    # --- CI/CD ---
    _g("pipeline", "A CI/CD or data pipeline.", "flow", "rounded", "", RR),
    _g("build", "A build step.", "flow", "rounded", "", RR),
    _g("test", "A test or verification step.", "flow", "rounded", "", RR),
    _g("deploy", "A deployment or release step.", "flow", "rounded", "", RR),
    # --- clients / people / external ---
    _g("webapp", "A web app, website or frontend page.", "client", "rounded", "", RR),
    _g("client", "A client application or browser.", "client", "icon", "", (AZ_GEN, "Browser"), (COMPS, "PC"), RR),
    _g("mobile", "A mobile device or app.", "client", "icon", "", (AZ_GEN, "Mobile"), (AZ_ENT, "Phone"), (COMPS, "PDA")),
    _g("pc", "A desktop or laptop computer.", "client", "icon", "", (COMPS, "PC"), (COMPS, "Laptop computer")),
    _g("user", "A person or actor using the system.", "person", "person", "", (PEOPLE, "User"), ("AZUREGENERALSYMBOLS_U.VSSX", "User")),
    _g("person", "A person (C4 person).", "person", "person", "", (PEOPLE, "User"), ("AZUREGENERALSYMBOLS_U.VSSX", "User")),
    _g("actor", "An actor interacting with the system (UML actor).", "person", "person", "", (PEOPLE, "User"), ("AZUREGENERALSYMBOLS_U.VSSX", "User")),
    _g("external", "An external system or third-party service outside your control.", "external", "rect", "", RECT),
    _g("external-system", "An external software system (C4 external system).", "external", "rect", "", RECT),
    _g("payment", "A payment provider or gateway (Stripe, PayPal).", "external", "rounded", "$", RR),
    # --- network / infrastructure / security ---
    _g("server", "A generic server.", "network", "icon", "", (SERVER, "Server"), RR),
    _g("router", "A network router.", "network", "icon", "", (NETSYM, "Router"), HEX),
    _g("switch", "A network switch.", "network", "icon", "", (NETSYM, "Workgroup switch"), HEX),
    _g("loadbalancer", "A load balancer spreading traffic across instances.", "network", "hexagon", "LB", HEX),
    _g("cdn", "A content delivery network.", "network", "hexagon", "CDN", HEX),
    _g("dns", "A DNS service or zone.", "network", "hexagon", "DNS", HEX),
    _g("cloud", "A cloud or WAN network region.", "network", "cloud", "", ("NETLOC_U.VSSX", "Cloud"), (AZ_ENT, "Cloud")),
    _g("internet", "The public internet.", "network", "cloud", "", (AZ_ENT, "Internet"), ("AWSGEN_U.VSSX", "Internet alt1"), ("NETLOC_U.VSSX", "Cloud")),
    _g("firewall", "A firewall.", "security", "icon", "", (AZ_ENT, "Firewall"), ("AWSGEN_U.VSSX", "Generic Firewall"), (BASIC, "Pentagon")),
    _g("waf", "A web application firewall.", "security", "hexagon", "WAF", HEX),
    _g("vpn", "A VPN gateway or tunnel.", "security", "hexagon", "VPN", HEX),
    _g("identity", "An identity provider (IdP, SSO, directory).", "security", "rounded", "ID", RR),
    _g("secrets", "A secrets manager or key vault.", "security", "rounded", "", RR),
    # --- observability ---
    _g("monitoring", "Monitoring, metrics and alerting.", "generic", "rounded", "", RR),
    _g("logging", "Log collection and analysis.", "generic", "rounded", "", RR),
    # --- org chart ---
    _g("executive", "A top executive in an org chart.", "org", "rect", "", (ORGCH, "Executive"), RECT),
    _g("manager", "A manager in an org chart.", "org", "rect", "", (ORGCH, "Manager"), RECT),
    _g("position", "An employee or position in an org chart.", "org", "rect", "", (ORGCH, "Position"), RECT),
    # --- ERD ---
    # Chen entity is one shape; the Crow's Foot entity spawns attribute-row shapes that layout scatters.
    _g("entity", "A database entity (table) in an ER diagram.", "entity", "entity", "", ("DBCHEN_U.VSSX", "Entity"), RECT),
    # --- generic ---
    _g("box", "A plain rectangle.", "generic", "rect", "", RECT),
    _g("ellipse", "A plain ellipse.", "generic", "ellipse", "", ELL),
    _g("mindmap-root", "The central topic of a mind map.", "generic", "ellipse", "", ELL),
    _g("note", "A sticky note or free text annotation.", "note", "note", "", (BASIC, "Single Snip Corner Rectangle"), ("ANNOT_U.VSSX", "Note symbol")),
)
