# -*- coding: utf-8 -*-
"""
DTC Knowledge Graph - On-Device Standalone Engine & Database Generator
Builds mobile/static/dtc_ondevice_engine.js for 100% offline standalone operation.
"""
import json
from collections import defaultdict
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
GRAPH_PATH = ROOT_DIR / "dtc_knowledge_graph.json"
LATENT_PATH = ROOT_DIR / "rgat_latent_2d.json"
OUT_JS_PATH = ROOT_DIR / "mobile" / "static" / "dtc_ondevice_engine.js"

def build():
    with open(GRAPH_PATH, "r", encoding="utf-8") as f:
        g = json.load(f)

    with open(LATENT_PATH, "r", encoding="utf-8") as f:
        latent_points = json.load(f)

    nodes = g["nodes"]
    edges = g["edges"]

    node_by_id = {n["id"]: n for n in nodes}
    dtc_to_ecus = defaultdict(set)
    dtc_to_conns = defaultdict(set)
    ecu_to_conns = defaultdict(set)
    conn_to_ecus = defaultdict(set)
    code_to_nids = defaultdict(list)

    for e in edges:
        rel = e.get("rel", "")
        src = e.get("source", "")
        dst = e.get("target", "")
        if rel in ("SW_IN", "SW_LOGIC"):
            dtc_to_ecus[src].add(dst)
        elif rel == "HW_MAP":
            dtc_to_conns[src].add(dst)
        elif rel == "HW_WIRE":
            ecu_to_conns[src].add(dst)
            src_n = node_by_id.get(src, {})
            if src_n.get("node_type") == "ECU":
                conn_to_ecus[dst].add(src_n.get("name", "?"))

    for n in nodes:
        if n.get("node_type") == "DTC":
            code = n.get("code", "").upper().strip()
            if code:
                code_to_nids[code].append(n["id"])

    conns = [n for n in nodes if n.get("node_type") == "Connector"]

    dtc_db = {}
    for code, nids in code_to_nids.items():
        fn = node_by_id[nids[0]]
        reached_ecus = set()
        reached_conns = set()
        verified_conns = set()
        for nid in nids:
            for eid in dtc_to_ecus.get(nid, ()):
                reached_ecus.add(node_by_id[eid].get("name", eid))
                for cid in ecu_to_conns.get(eid, ()):
                    reached_conns.add(cid)
            for cid in dtc_to_conns.get(nid, ()):
                reached_conns.add(cid)
                verified_conns.add(cid)

        dtc_db[code] = {
            "desc": (fn.get("description", "") or "")[:70],
            "cat": fn.get("fault_category", ""),
            "sys_code": fn.get("system_code", ""),
            "sys_name": fn.get("system_name", ""),
            "mfr": fn.get("mfr_specific", ""),
            "st_code": fn.get("subtype_code", ""),
            "st_name": fn.get("subtype_name", ""),
            "pos": fn.get("position", ""),
            "ecus": sorted(reached_ecus),
            "conns": sorted(reached_conns),
            "v_conns": sorted(verified_conns)
        }

    conn_db = {}
    for n in conns:
        cid = n["id"]
        conn_db[cid] = {
            "name": n.get("name", cid),
            "loc": n.get("location", ""),
            "ecus": sorted(conn_to_ecus.get(cid, set()))
        }

    # Precomputed hybrid scores for reachable connectors
    ecu_wires = []
    for src_id, dst_set in ecu_to_conns.items():
        src_name = node_by_id[src_id].get("name", src_id)
        for dst_id in dst_set:
            ecu_wires.append({"ecu": src_name, "conn": dst_id})

    js_content = f"""/**
 * DTC Knowledge Graph - 100% Offline On-Device Diagnostic Engine
 * Bundles full graph topology, master mappings, and client-side scoring.
 * Enables 0-latency standalone diagnostic inference on smartphones without PC or Wi-Fi.
 */
(function() {{
  'use strict';

  const DTC_DB = {json.dumps(dtc_db, ensure_ascii=False)};
  const CONN_DB = {json.dumps(conn_db, ensure_ascii=False)};
  const ECU_WIRES = {json.dumps(ecu_wires, ensure_ascii=False)};
  const LATENT_POINTS = {json.dumps(latent_points, ensure_ascii=False)};

  const DTCLocalEngine = {{
    isAvailable: true,

    search(query, limit = 20) {{
      const q = (query || '').toUpperCase().trim();
      if (!q) return [];
      const results = [];
      for (const [code, info] of Object.entries(DTC_DB)) {{
        if (code.includes(q)) {{
          results.push({{
            code: code,
            ecu: info.ecus.length ? info.ecus.slice(0, 2).join(', ') : '기타',
            desc: info.desc || '설명 없음',
            cat: info.cat || '기타'
          }});
          if (results.length >= limit) break;
        }}
      }}
      return results;
    }},

    getLatentPoints() {{
      return LATENT_POINTS;
    }},

    analyze(inputCodes, topK = 5) {{
      const codes = Array.isArray(inputCodes) ? inputCodes : [];
      const dtc_info = [];
      const unknown = [];

      codes.forEach(rawCode => {{
        const code = (rawCode || '').toUpperCase().trim();
        if (!code) return;
        const entry = DTC_DB[code];
        if (entry) {{
          dtc_info.push({{
            code: code,
            ecu_names: entry.ecus,
            struct_conns: entry.conns,
            has_struct: entry.conns.length > 0,
            desc: entry.desc,
            cat: entry.cat,
            system_code: entry.sys_code,
            system_name: entry.sys_name,
            mfr_specific: entry.mfr,
            subtype_code: entry.st_code,
            subtype_name: entry.st_name,
            position: entry.pos
          }});
        }} else {{
          unknown.push(code);
        }}
      }});

      if (dtc_info.length === 0) {{
        return {{
          error: '유효한 DTC 코드가 없습니다.',
          unknown: unknown,
          dtc_info: [],
          results: [],
          vis_nodes: [],
          vis_edges: [],
          is_offline: true
        }};
      }}

      const n_valid = dtc_info.length;

      // 1. Master Verified Mapping
      const verifiedHits = {{}};
      dtc_info.forEach(d => {{
        const entry = DTC_DB[d.code];
        if (entry && entry.v_conns) {{
          entry.v_conns.forEach(cid => {{
            if (!verifiedHits[cid]) verifiedHits[cid] = new Set();
            verifiedHits[cid].add(d.code);
          }});
        }}
      }});

      // 2. Structural Reachability Hit Count
      const structHits = {{}};
      dtc_info.forEach(d => {{
        d.struct_conns.forEach(cid => {{
          if (!structHits[cid]) structHits[cid] = new Set();
          structHits[cid].add(d.code);
        }});
      }});

      const results = [];
      const addedConns = new Set();

      // Top verified connectors first
      const sortedVerified = Object.keys(verifiedHits).sort((a, b) => verifiedHits[b].size - verifiedHits[a].size);
      for (const cid of sortedVerified) {{
        if (results.length >= topK) break;
        const cMeta = CONN_DB[cid] || {{ name: cid, loc: '', ecus: [] }};
        const hitCodes = Array.from(verifiedHits[cid]).sort();
        results.push({{
          rank: results.length + 1,
          conn_id: cid,
          name: cMeta.name || cid,
          location: cMeta.loc || '',
          final_score: 2.0,
          struct_score: 2.0,
          n_hit: hitCodes.length,
          n_valid: n_valid,
          hit_codes: hitCodes,
          conn_ecus: cMeta.ecus,
          verified: true,
          is_reachable: true
        }});
        addedConns.add(cid);
      }}

      // Reachable connectors sorted by hit ratio
      const sortedReachable = Object.keys(structHits)
        .filter(cid => !addedConns.has(cid))
        .sort((a, b) => structHits[b].size - structHits[a].size);

      for (const cid of sortedReachable) {{
        if (results.length >= topK) break;
        const cMeta = CONN_DB[cid] || {{ name: cid, loc: '', ecus: [] }};
        const hitCodes = Array.from(structHits[cid]).sort();
        const score = hitCodes.length / n_valid;
        results.push({{
          rank: results.length + 1,
          conn_id: cid,
          name: cMeta.name || cid,
          location: cMeta.loc || '',
          final_score: parseFloat(score.toFixed(4)),
          struct_score: parseFloat(score.toFixed(4)),
          n_hit: hitCodes.length,
          n_valid: n_valid,
          hit_codes: hitCodes,
          conn_ecus: cMeta.ecus,
          verified: false,
          is_reachable: true
        }});
        addedConns.add(cid);
      }}

      // 3. Build Vis Nodes & Edges
      const vis_nodes = [];
      const vis_edges = [];
      const addedNodeIds = new Set();

      // (1) DTC nodes
      dtc_info.forEach(d => {{
        vis_nodes.push({{
          id: d.code,
          label: d.code,
          title: `[DTC] ${{d.code}}\\n${{d.desc}}\\n제어기: ${{d.ecu_names.join(', ')}}`,
          level: 1,
          group: 'dtc_input'
        }});
        addedNodeIds.add(d.code);
      }});

      // (2) ECU nodes
      const allEcus = new Set();
      dtc_info.forEach(d => d.ecu_names.forEach(e => allEcus.add(e)));
      allEcus.forEach(ecuName => {{
        vis_nodes.push({{
          id: ecuName,
          label: ecuName,
          title: `[ECU] ${{ecuName}}`,
          level: 2,
          group: 'ecu'
        }});
        addedNodeIds.add(ecuName);
      }});

      // (3) Connector nodes
      results.forEach((r, idx) => {{
        const isTop1 = (idx === 0);
        vis_nodes.push({{
          id: r.conn_id,
          label: (r.name || r.conn_id).split(' / ')[0],
          title: `[커넥터] #${{r.rank}} ${{r.name}}\\n${{r.verified ? '마스터 검증' : '점수 ' + r.final_score}}\\n연결 ECU: ${{r.conn_ecus.join(', ')}}`,
          level: 3,
          group: isTop1 ? 'conn_top1' : (idx < 3 ? 'conn_top' : 'conn')
        }});
        addedNodeIds.add(r.conn_id);
      }});

      // (4) Edges
      // SW_LOGIC: DTC -> ECU
      dtc_info.forEach(d => {{
        d.ecu_names.forEach(ecuName => {{
          vis_edges.push({{
            from: d.code,
            to: ecuName,
            title: `SW_LOGIC (DTC ${{d.code}} -> ECU ${{ecuName}})`,
            dashes: false
          }});
        }});
      }});

      // HW_MAP: Top-1 Conn -> DTC
      if (results.length > 0) {{
        const top1 = results[0];
        top1.hit_codes.forEach(code => {{
          vis_edges.push({{
            from: top1.conn_id,
            to: code,
            title: `HW_MAP (검증매핑: ${{top1.name}} -> ${{code}})`,
            dashes: false
          }});
        }});
      }}

      // HW_WIRE: ECU -> Top Connectors
      const topConnIds = new Set(results.map(r => r.conn_id));
      const connectedEcuConn = new Set();

      ECU_WIRES.forEach(w => {{
        if (allEcus.has(w.ecu) && topConnIds.has(w.conn)) {{
          vis_edges.push({{
            from: w.ecu,
            to: w.conn,
            title: `HW_WIRE (물리배선: ${{w.ecu}} <-> ${{CONN_DB[w.conn] ? CONN_DB[w.conn].name : w.conn}})`,
            dashes: false
          }});
          connectedEcuConn.add(`${{w.ecu}}->${{w.conn}}`);
        }}
      }});

      // AI_HW_WIRE for unlinked ECUs
      if (results.length > 0) {{
        const top1Id = results[0].conn_id;
        allEcus.forEach(ecuName => {{
          if (!connectedEcuConn.has(`${{ecuName}}->${{top1Id}}`)) {{
            vis_edges.push({{
              from: ecuName,
              to: top1Id,
              title: `AI_HW_WIRE (추론배선: ${{ecuName}} -> ${{results[0].name}})`,
              dashes: true
            }});
          }}
        }});
      }}

      return {{
        results: results,
        dtc_info: dtc_info,
        vis_nodes: vis_nodes,
        vis_edges: vis_edges,
        unknown: unknown,
        is_offline: true
      }};
    }}
  }};

  window.DTCLocalEngine = DTCLocalEngine;
  console.log('[On-Device DTC Engine] Loaded successfully. Offline standalone ready.');
}})();
"""

    with open(OUT_JS_PATH, "w", encoding="utf-8") as f:
        f.write(js_content)

    print(f"Generated On-Device Engine JS: {OUT_JS_PATH} ({len(js_content)} bytes)")

if __name__ == "__main__":
    build()
