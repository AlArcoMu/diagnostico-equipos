import json
from html import escape

from .analysis import (CRITICAL, HEALTH, OK, WARNING, PRINTER_ERRORS, antivirus_state, event_groups, gb, overall,
                       parse_date, pct, plural, relevant_services, summary_text, uptime_days)

MEDIA = {"3": "HDD", "HDD": "HDD", "4": "SSD", "SSD": "SSD", "5": "SCM", "0": "", "Unspecified": ""}
SERVICE_STATE = {"Stopped": "Detenido", "Start Pending": "Iniciándose", "Stop Pending": "Deteniéndose",
                 "Paused": "En pausa", "Unknown": "Desconocido"}
LEVEL_LABEL = {CRITICAL: "Crítico", WARNING: "Aviso", OK: "Correcto"}
STATUS_TEXT = {CRITICAL: "Hay problemas que requieren atención", WARNING: "Hay puntos a revisar", OK: "Todo correcto"}


def e(value):
    return escape("" if value is None else str(value))


def fmt_date(value, with_time=True):
    d = parse_date(value)
    if not d:
        return "—"
    return d.strftime("%d/%m/%Y %H:%M" if with_time else "%d/%m/%Y")


def bar(percent, warn=80, crit=90):
    cls = "crit" if percent >= crit else "warn" if percent >= warn else ""
    return f'<span class="bar {cls}"><span style="width:{min(percent, 100)}%"></span></span><span class="num">{percent} %</span>'


def check(result, label_ok="Correcto", label_ko="Sin respuesta"):
    if not result:
        return '<span class="pill">No comprobado</span>'
    ms = f" · {result['ms']:.0f} ms" if result.get("ms") is not None else ""
    return f'<span class="pill ok">{label_ok}{ms}</span>' if result.get("ok") else f'<span class="pill crit">{label_ko}</span>'


def rows(pairs):
    return "".join(f"<tr><th>{e(k)}</th><td>{v}</td></tr>" for k, v in pairs if v not in (None, "", "—"))


def table(head, body, empty):
    if not body:
        return f'<p class="empty">{e(empty)}</p>'
    return f'<table class="grid"><thead><tr>{"".join(f"<th>{e(h)}</th>" for h in head)}</tr></thead><tbody>{"".join(body)}</tbody></table>'


PILL_OK = '<span class="pill ok">{}</span>'
PILL_WARN = '<span class="pill warn">{}</span>'
PILL_CRIT = '<span class="pill crit">{}</span>'


def alert_item(f):
    detail = f"<p>{e(f['detail'])}</p>" if f["detail"] else ""
    return (f'<li class="{f["level"]}"><span class="tag">{LEVEL_LABEL[f["level"]]}</span>'
            f'<div><strong>{e(f["title"])}</strong>{detail}</div><span class="area">{e(f["area"])}</span></li>')


def printer_row(p):
    default = ' <span class="pill">Predeterminada</span>' if p.get("default") else ""
    status = PILL_WARN.format("Sin conexión") if p.get("offline") else e(PRINTER_ERRORS.get(p.get("error"), "Lista"))
    return (f"<tr><td><strong>{e(p.get('name'))}</strong>{default}<span class='sub'>{e(p.get('driver'))}</span></td>"
            f"<td>{e(p.get('port'))}</td><td>{status}</td><td>{p.get('jobs') or 0}</td></tr>")


def event_row(g):
    level = PILL_CRIT.format("Crítico") if g["level"] == 1 else PILL_WARN.format("Error")
    return (f"<tr><td>{level}</td><td><strong>{e(g['source'])}</strong><span class='sub'>Id {e(g['id'])} · {e(g['log'])}</span></td>"
            f"<td class='msg'>{e(g['message'])}</td><td>{g['count']}</td><td>{fmt_date(g['last'])}</td></tr>")


def antivirus_cell(a):
    st = antivirus_state(a.get("state"))
    enabled = PILL_OK.format("Activado") if st["enabled"] else PILL_CRIT.format("Desactivado")
    updated = "" if st["updated"] else " " + PILL_WARN.format("Sin actualizar")
    return f"{e(a.get('name'))} · {enabled}{updated}"


def render(data, findings, ticket="", problem=""):
    s = data.get("system") or {}
    net = data.get("connectivity") or {}
    state = overall(findings)
    summary_json = json.dumps(summary_text(data, findings, ticket, problem)).replace("</", "<\\/")
    days = uptime_days(s, parse_date(data.get("collectedAt")))

    alerts = "".join(alert_item(f) for f in findings) or (
        '<li class="ok"><span class="tag">Correcto</span><div><strong>No se han encontrado problemas</strong></div></li>')

    ram_total = (s.get("ramTotalKB") or 0) / 1024 ** 2
    ram_used = 100 - pct(s.get("ramFreeKB") or 0, s.get("ramTotalKB") or 0) if s.get("ramTotalKB") else None

    equipo = rows([
        ("Nombre", e(s.get("computer"))),
        ("Usuario", e(s.get("user"))),
        ("Dominio", e(s.get("domain")) + ("" if s.get("partOfDomain") else " (grupo de trabajo)") if s.get("domain") else None),
        ("Fabricante y modelo", e(f"{s.get('manufacturer', '')} {s.get('model', '')}".strip())),
        ("Número de serie", e(s.get("serial"))),
        ("Sistema operativo", e(f"{s.get('os', '')} {s.get('arch', '')}".strip())),
        ("Versión", e(f"{s.get('osVersion', '')} (compilación {s.get('osBuild')})") if s.get("osVersion") else None),
        ("Último arranque", f"{fmt_date(s.get('lastBoot'))} · hace {plural(int(days), 'día', 'días')}" if days is not None else None),
        ("Instalado el", fmt_date(s.get("installDate"), False) if s.get("installDate") else None),
    ])

    rendimiento = rows([
        ("Procesador", e(f"{s.get('cpu', '')} · {s.get('cores', '?')} núcleos / {s.get('threads', '?')} hilos") if s.get("cpu") else None),
        ("Carga del procesador", bar(s["cpuLoad"]) if s.get("cpuLoad") is not None else None),
        ("Memoria RAM", f"{bar(ram_used)}<span class='sub'>{ram_total:.1f} GB en total</span>" if ram_used is not None else None),
        ("Batería", f"{(data.get('battery') or {}).get('charge')} %" if (data.get("battery") or {}).get("charge") is not None else None),
    ])

    discos = [
        f"<tr><td><strong>{e(d.get('drive'))}</strong> {e(d.get('label'))}</td><td>{e(d.get('fs'))}</td>"
        f"<td>{gb(d.get('size')):.0f} GB</td><td>{gb(d.get('free')):.1f} GB</td>"
        f"<td class='w'>{bar(100 - pct(d.get('free', 0), d.get('size', 0)), 80, 90)}</td></tr>"
        for d in data.get("disks") or []]
    fisicos = [
        f"<tr><td>{e(d.get('name'))}</td><td>{e(MEDIA.get(str(d.get('media')), d.get('media')))}</td><td>{gb(d.get('size')):.0f} GB</td>"
        f"<td>{e(HEALTH.get(str(d.get('health')), d.get('health')))}</td></tr>"
        for d in data.get("physicalDisks") or []]

    adaptadores = [
        f"<tr><td><strong>{e(n.get('name') or '—')}</strong><span class='sub'>{e(n.get('description'))}</span></td>"
        f"<td>{e(', '.join(n.get('ipv4', [])))}<span class='sub'>{'DHCP' if n.get('dhcp') else 'IP fija'}</span></td>"
        f"<td>{e(', '.join(n.get('gateway', [])) or '—')}</td><td>{e(', '.join(n.get('dns', [])) or '—')}</td>"
        f"<td>{e(n.get('mac'))}<span class='sub'>{(n.get('speed') or 0) / 1e6:.0f} Mbps</span></td></tr>"
        for n in data.get("network") or []]
    wf = net.get("wifi") or {}
    conexion = rows([
        ("Puerta de enlace", f"{check(net.get('gateway'))} <span class='sub'>{e((net.get('gateway') or {}).get('host'))}</span>"),
        ("Internet (1.1.1.1)", check(net.get("internet"))),
        ("Resolución DNS", f"{check(net.get('dns'), 'Correcto', 'Fallo')} <span class='sub'>{e((net.get('dns') or {}).get('host'))}</span>"),
        ("Acceso web", check(net.get("http"), "Correcto", "Sin acceso")),
        ("Wi-Fi", f"{e(wf.get('ssid'))} · señal {wf.get('signal')} %" if wf else None),
    ])

    impresoras = [printer_row(p) for p in data.get("printers") or []]

    servicios = [
        f"<tr><td>{e(sv.get('display'))}<span class='sub'>{e(sv.get('name'))}</span></td><td>{e(SERVICE_STATE.get(sv.get('state'), sv.get('state')))}</td></tr>"
        for sv in relevant_services(data.get("services"))]

    eventos = [event_row(g) for g in event_groups(data.get("events"))[:25]]

    upd = data.get("lastUpdate") or {}
    seguridad = rows([
        *[("Antivirus", antivirus_cell(a)) for a in data.get("antivirus") or []],
        ("Última actualización", f"{e(upd.get('id'))} · {fmt_date(upd.get('date'), False)}" if upd else None),
        ("Reinicio pendiente", '<span class="pill warn">Sí</span>' if data.get("pendingReboot") else "No"),
    ])

    head = f"""<header class="top {state}">
  <div><p class="eyebrow">Informe de diagnóstico</p><h1>{e(s.get('computer'))}</h1>
  <p class="meta">{fmt_date(data.get('collectedAt'))}{f' · Ticket {e(ticket)}' if ticket else ''} · {e(s.get('user'))}</p></div>
  <div class="state"><span class="dot"></span>{STATUS_TEXT[state]}</div>
</header>"""

    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Diagnóstico {e(s.get('computer'))}{f' · {e(ticket)}' if ticket else ''}</title>
<style>{CSS}</style>
</head>
<body>
<main>
{head}
<div class="actions"><button id="copy" type="button">Copiar resumen para el ticket</button><button id="print" type="button" class="ghost">Guardar como PDF</button><span id="copied" role="status"></span></div>
{f'<section class="card problem"><h2>Problema indicado</h2><p>{e(problem)}</p></section>' if problem else ''}
<section class="card"><h2>Resumen</h2><ul class="alerts">{alerts}</ul></section>
<div class="cols">
<section class="card"><h2>Equipo</h2><table class="kv">{equipo}</table></section>
<section class="card"><h2>Rendimiento</h2><table class="kv">{rendimiento}</table></section>
</div>
<section class="card"><h2>Discos</h2>{table(["Unidad", "Sistema", "Tamaño", "Libre", "Uso"], discos, "No se han encontrado unidades.")}
{table(["Disco físico", "Tipo", "Tamaño", "Estado"], fisicos, "") if fisicos else ""}</section>
<section class="card"><h2>Red</h2><table class="kv">{conexion}</table>
{table(["Adaptador", "IPv4", "Puerta de enlace", "DNS", "MAC"], adaptadores, "No hay adaptadores con IP.")}</section>
<section class="card"><h2>Impresoras</h2>{table(["Impresora", "Puerto", "Estado", "En cola"], impresoras, "No hay impresoras instaladas.")}</section>
<div class="cols">
<section class="card"><h2>Seguridad</h2><table class="kv">{seguridad}</table></section>
<section class="card"><h2>Servicios automáticos detenidos</h2>{table(["Servicio", "Estado"], servicios, "Todos los servicios automáticos están en marcha.")}</section>
</div>
<section class="card"><h2>Visor de eventos · últimos {data.get('eventDays', 7)} días</h2>{table(["Nivel", "Origen", "Mensaje", "Veces", "Última vez"], eventos, "Sin errores ni eventos críticos.")}</section>
<footer>Generado con Diagnóstico de equipos · {fmt_date(data.get('collectedAt'))}</footer>
</main>
<script id="summary" type="application/json">{summary_json}</script>
<script>{JS}</script>
</body>
</html>
"""


CSS = """
:root{--ink:#13253a;--text:#1d2733;--muted:#5c6b7a;--line:#e1e6ec;--bg:#eef1f5;--ok:#1f8a4c;--warn:#c47a00;--crit:#d23b1c;--accent:#e2541c}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:14px/1.5 "Segoe UI",system-ui,-apple-system,Roboto,sans-serif}
main{max-width:1060px;margin:0 auto;padding:28px 20px 40px;display:grid;gap:16px}
h1,h2,p{margin:0}
.top{display:flex;justify-content:space-between;align-items:flex-end;gap:16px;flex-wrap:wrap;background:var(--ink);color:#fff;padding:24px 28px;border-radius:12px;border-left:8px solid var(--ok)}
.top.aviso{border-left-color:var(--warn)}.top.critico{border-left-color:var(--crit)}
.eyebrow{font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:#a9b6c4}
h1{font-size:30px;line-height:1.1;margin:4px 0 6px}
.meta{color:#c9d2dc}
.state{display:flex;align-items:center;gap:10px;font-weight:600;font-size:15px}
.state .dot{width:12px;height:12px;border-radius:50%;background:var(--ok)}
.aviso .state .dot{background:var(--warn)}.critico .state .dot{background:var(--crit)}
.actions{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
button{font:inherit;font-weight:600;border:0;border-radius:8px;padding:10px 16px;background:var(--accent);color:#fff;cursor:pointer}
button.ghost{background:#fff;color:var(--ink);border:1px solid #c9d2dc}
button:focus-visible{outline:3px solid var(--ink);outline-offset:2px}
#copied{color:var(--ok);font-weight:600}
.card{background:#fff;border:1px solid var(--line);border-radius:12px;padding:18px 20px;display:grid;gap:12px;align-content:start}
h2{font-size:15px;color:var(--ink)}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.problem p{white-space:pre-wrap}
.alerts{list-style:none;margin:0;padding:0;display:grid;gap:8px}
.alerts li{display:grid;grid-template-columns:auto 1fr auto;gap:12px;align-items:start;padding:10px 12px;border-radius:8px;background:#f6f8fa;border-left:4px solid var(--ok)}
.alerts li.aviso{border-left-color:var(--warn);background:#fff8ec}.alerts li.critico{border-left-color:var(--crit);background:#fdf1ee}
.alerts p{color:var(--muted)}
.tag{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;padding:3px 8px;border-radius:4px;background:var(--ok);color:#fff}
.aviso .tag{background:var(--warn)}.critico .tag{background:var(--crit)}
.area{font-size:12px;color:var(--muted)}
table{width:100%;border-collapse:collapse}
.kv th{text-align:left;font-weight:500;color:var(--muted);padding:6px 12px 6px 0;width:38%;vertical-align:top}
.kv td{padding:6px 0;vertical-align:top}
.grid th{text-align:left;font-size:12px;font-weight:600;color:#fff;background:var(--ink);padding:7px 10px}
.grid td{padding:7px 10px;border-bottom:1px solid var(--line);vertical-align:top}
.grid tr:nth-child(even) td{background:#f6f8fa}
.grid td.w{width:30%}.grid td.msg{color:var(--muted);max-width:420px}
.sub{display:block;font-size:12px;color:var(--muted)}
.kv .sub{display:inline;margin-left:6px}
.bar{display:inline-block;vertical-align:middle;width:140px;height:8px;border-radius:4px;background:var(--line);overflow:hidden;margin-right:8px}
.bar span{display:block;height:100%;background:var(--ok)}
.bar.warn span{background:var(--warn)}.bar.crit span{background:var(--crit)}
.num{font-variant-numeric:tabular-nums}
.pill{display:inline-block;font-size:12px;font-weight:600;padding:2px 8px;border-radius:999px;background:var(--line);color:var(--ink)}
.pill.ok{background:#e3f4ea;color:var(--ok)}.pill.warn{background:#fdf0d9;color:#8a5600}.pill.crit{background:#fbe2dc;color:var(--crit)}
.empty{color:var(--muted)}
footer{text-align:center;color:var(--muted);font-size:12px}
@media (max-width:760px){.cols{grid-template-columns:1fr}.grid{display:block;overflow-x:auto}}
@media print{body{background:#fff}main{padding:0}.actions{display:none}.card,.top{break-inside:avoid}.top{-webkit-print-color-adjust:exact;print-color-adjust:exact}
.grid th,.tag,.bar span,.pill,.alerts li{-webkit-print-color-adjust:exact;print-color-adjust:exact}}
"""

JS = """
(function(){
  var text = JSON.parse(document.getElementById('summary').textContent);
  var out = document.getElementById('copied');
  function done(){ out.textContent = 'Resumen copiado'; setTimeout(function(){ out.textContent = ''; }, 2500); }
  document.getElementById('copy').addEventListener('click', function(){
    if (navigator.clipboard && window.isSecureContext) { navigator.clipboard.writeText(text).then(done, fallback); } else { fallback(); }
    function fallback(){ var t = document.createElement('textarea'); t.value = text; document.body.appendChild(t); t.select(); document.execCommand('copy'); t.remove(); done(); }
  });
  document.getElementById('print').addEventListener('click', function(){ window.print(); });
})();
"""
