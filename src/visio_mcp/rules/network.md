# Network

**Use when:** you need the physical or virtual network: sites, segments, subnets, routing, firewalls and the devices on them.

## Purpose
A network topology for network engineers, security reviewers and operations. It
answers "how does traffic get from A to B, and what filters it on the way?" Use
Cisco-style device symbols (router, switch, firewall) and show segments as groups.

## Spec settings
- `"type": "network"`, `"layout": "flowchart-tb"`: internet/WAN on top, core in the
  middle, access layer and endpoints at the bottom (core-distribution-access).
- Theme `professional` or `blueprint`.

## Node kinds
| Kind | Use for |
|---|---|
| `internet`, `cloud` | Internet, WAN, MPLS, a provider cloud as a black box. |
| `router` | Edge and core routers, VPN gateways. |
| `firewall` | Firewalls, WAFs, security appliances. |
| `switch` | Core/distribution/access switches. |
| `loadbalancer` | Load balancers. |
| `server`, `pc`, `mobile` | Endpoints and hosts. |

Label devices by role + name (`Core Switch 1`, `Edge Router`); put model and IP
addressing in `technology` (`Cisco 9300`) or `description` (`10.0.1.1/24`).

## Groups
- `network` for sites, VLANs or VNets/VPCs; `subnet` for subnets/VLAN segments with
  the CIDR in the label or description (`Servers 10.0.20.0/24`).
- `boundary` for security zones (DMZ, PCI, OT). `zone` only for cloud availability
  zones.
- Order: site/network > subnet > devices.

## Edges
- Links are physical or logical connections; label with what matters: link type and
  speed (`10 GbE`, `IPsec VPN`, `trunk`), or VLAN ids.
- Use `arrow: "none"` for physical links (no direction); arrows only for traffic
  flows. `dashed` for VPN/tunnels and backup links.
- Two-way arrows are a smell here too: an undirected link uses `arrow: "none"`.

## Checklist
- [ ] Hierarchy top to bottom: WAN/Internet > edge > core > access > endpoints
- [ ] Every segment has its CIDR or VLAN
- [ ] Firewalls between every zone boundary are visible
- [ ] Links labeled with type/speed where relevant; undirected links have no arrows
- [ ] Endpoints summarized (`Workstations x40`) rather than drawn one by one

## Common mistakes
- Drawing every PC; use one node with a count.
- Mixing logical application flows into the topology; draw a separate flow diagram.
- Missing addressing on segments.
- Arrows on physical cables.

## Example
```json
{
  "title": "Head Office Network",
  "subtitle": "Physical topology - rev C, Oct 2026",
  "type": "network",
  "layout": "flowchart-tb",
  "groups": [
    {"id": "site", "label": "Head Office", "kind": "network"},
    {"id": "dmz", "label": "DMZ 10.0.10.0/24", "kind": "subnet", "parent": "site"},
    {"id": "lan", "label": "Staff LAN 10.0.20.0/24", "kind": "subnet", "parent": "site"}
  ],
  "nodes": [
    {"id": "internet", "label": "Internet", "kind": "internet"},
    {"id": "edge", "label": "Edge Router", "kind": "router", "group": "site"},
    {"id": "fw", "label": "Perimeter Firewall", "kind": "firewall", "group": "site"},
    {"id": "web", "label": "Web Server", "kind": "server", "group": "dmz"},
    {"id": "core", "label": "Core Switch", "kind": "switch", "group": "lan"},
    {"id": "pcs", "label": "Workstations x40", "kind": "pc", "group": "lan"}
  ],
  "edges": [
    {"source": "internet", "target": "edge", "label": "fibre uplink", "arrow": "none"},
    {"source": "edge", "target": "fw", "label": "1 GbE", "arrow": "none"},
    {"source": "fw", "target": "web", "label": "DMZ VLAN 10", "arrow": "none"},
    {"source": "fw", "target": "core", "label": "trunk", "arrow": "none"},
    {"source": "core", "target": "pcs", "label": "VLAN 20", "arrow": "none"}
  ]
}
```
