from collections import Counter
from datetime import datetime

CRITICAL, WARNING, OK = "critico", "aviso", "ok"
ORDER = {CRITICAL: 0, WARNING: 1, OK: 2}

IGNORED_SERVICES = {
    "gupdate", "edgeupdate", "MapsBroker", "sppsvc", "RemoteRegistry", "TrustedInstaller",
    "wuauserv", "BITS", "CDPSvc", "tiledatamodelsvc", "WbioSrvc", "GoogleUpdaterService",
    "GoogleUpdaterInternalService", "MicrosoftEdgeElevationService", "dbupdate", "WMPNetworkSvc",
    "clr_optimization_v4.0.30319_32", "clr_optimization_v4.0.30319_64", "UsoSvc", "ShellHWDetection",
}

PRINTER_ERRORS = {
    2: "error desconocido", 3: "poco papel", 4: "sin papel", 5: "poco tóner", 6: "sin tóner",
    7: "puerta abierta", 8: "atasco de papel", 9: "sin conexión", 10: "requiere intervención",
    11: "bandeja de salida llena",
}


HEALTH = {"0": "Correcto", "Healthy": "Correcto", "1": "Advertencia", "Warning": "Advertencia",
          "2": "Dañado", "Unhealthy": "Dañado", "5": "Desconocido", "Unknown": "Desconocido"}


def plural(count, one, many):
    return f"{count} {one if count == 1 else many}"


def parse_date(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)[:19])
    except ValueError:
        return None


def gb(value):
    return (value or 0) / 1024 ** 3


def pct(part, total):
    return round(part / total * 100) if total else 0


def uptime_days(system, now=None):
    boot = parse_date((system or {}).get("lastBoot"))
    if not boot:
        return None
    return ((now or datetime.now()) - boot).total_seconds() / 86400


def antivirus_state(state):
    code = f"{int(state or 0):06x}"
    return {"enabled": code[2:4] in ("10", "11"), "updated": code[4:6] == "00"}


def relevant_services(services):
    return [s for s in services or [] if s.get("name") not in IGNORED_SERVICES]


def event_groups(events):
    groups = {}
    for e in events or []:
        key = (e.get("source"), e.get("id"))
        g = groups.setdefault(key, {"source": e.get("source"), "id": e.get("id"), "log": e.get("log"),
                                    "level": e.get("level"), "count": 0, "last": None, "message": e.get("message")})
        g["count"] += 1
        g["level"] = min(g["level"] or 9, e.get("level") or 9)
        if not g["last"] or (e.get("time") or "") > g["last"]:
            g["last"] = e.get("time")
            g["message"] = e.get("message") or g["message"]
    return sorted(groups.values(), key=lambda g: (g["level"], -g["count"]))


def analyse(data, now=None):
    now = now or datetime.now()
    found = []

    def add(level, area, title, detail=""):
        found.append({"level": level, "area": area, "title": title, "detail": detail})

    system = data.get("system") or {}
    for d in data.get("disks") or []:
        free = pct(d.get("free", 0), d.get("size", 0))
        if d.get("size") and free < 10:
            add(CRITICAL, "Disco", f"La unidad {d['drive']} está casi llena", f"Quedan {gb(d['free']):.1f} GB libres ({free} %).")
        elif d.get("size") and free < 20:
            add(WARNING, "Disco", f"Poco espacio libre en la unidad {d['drive']}", f"Quedan {gb(d['free']):.1f} GB libres ({free} %).")

    for d in data.get("physicalDisks") or []:
        health = str(d.get("health") or "")
        if health and health not in ("Healthy", "0"):
            add(CRITICAL, "Disco", f"El disco {d.get('name')} no está en buen estado",
                f"Estado: {HEALTH.get(health, health).lower()}. Haz una copia de seguridad cuanto antes.")

    total, free_kb = system.get("ramTotalKB"), system.get("ramFreeKB")
    if total:
        used = 100 - pct(free_kb or 0, total)
        if used >= 90:
            add(WARNING, "Memoria", "Memoria RAM casi agotada", f"En uso: {used} % de {total / 1024 ** 2:.1f} GB.")
    if (system.get("cpuLoad") or 0) >= 90:
        add(WARNING, "Procesador", "Procesador al límite", f"Carga del {system['cpuLoad']} % al hacer el diagnóstico.")

    days = uptime_days(system, now)
    if days is not None and days >= 7:
        add(WARNING, "Sistema", "El equipo lleva tiempo sin reiniciarse", f"Encendido desde hace {int(days)} días. Un reinicio suele resolver problemas de rendimiento.")
    if data.get("pendingReboot"):
        add(WARNING, "Sistema", "Reinicio pendiente", "Hay actualizaciones esperando a que se reinicie el equipo.")

    last = parse_date((data.get("lastUpdate") or {}).get("date"))
    if last and (now - last).days > 45:
        add(WARNING, "Seguridad", "Actualizaciones atrasadas", f"La última actualización instalada es del {last:%d/%m/%Y}.")

    av = data.get("antivirus") or []
    if not av and data.get("system") and data["system"].get("os") and "Server" not in data["system"]["os"]:
        add(CRITICAL, "Seguridad", "No se detecta antivirus")
    for a in av:
        st = antivirus_state(a.get("state"))
        if not st["enabled"]:
            add(CRITICAL, "Seguridad", f"{a.get('name')} está desactivado")
        elif not st["updated"]:
            add(WARNING, "Seguridad", f"{a.get('name')} no está actualizado")

    net = data.get("connectivity") or {}
    adapters = data.get("network") or []
    gateway, internet, dns, http = (net.get(k) for k in ("gateway", "internet", "dns", "http"))
    if not adapters:
        add(CRITICAL, "Red", "Sin adaptador de red con IP", "El equipo no tiene ninguna conexión de red activa.")
    elif any(ip.startswith("169.254.") for n in adapters for ip in n.get("ipv4", [])):
        add(CRITICAL, "Red", "IP automática (169.254.x.x)", "El equipo no recibe IP del servidor DHCP. Revisa el cable, la Wi-Fi o el DHCP.")
    elif gateway is None:
        add(CRITICAL, "Red", "Sin puerta de enlace", "Ningún adaptador tiene puerta de enlace configurada.")
    elif not gateway.get("ok"):
        add(CRITICAL, "Red", "No responde la puerta de enlace", f"Sin respuesta de {gateway['host']}. El fallo está en la red local.")
    if adapters and gateway and gateway.get("ok"):
        if internet and not internet.get("ok") and http and not http.get("ok"):
            add(CRITICAL, "Red", "Sin salida a internet", "La red local funciona, pero no hay salida al exterior.")
        elif dns and not dns.get("ok"):
            add(CRITICAL, "Red", "Fallo de DNS", "Hay conexión, pero no se resuelven nombres. Revisa los servidores DNS.")
    wf = net.get("wifi") or {}
    if wf.get("signal") is not None and wf["signal"] < 50:
        add(WARNING, "Red", "Señal Wi-Fi débil", f"{wf['signal']} % en la red {wf.get('ssid')}.")

    for p in data.get("printers") or []:
        if p.get("offline"):
            add(WARNING, "Impresoras", f"{p['name']} está sin conexión")
        elif p.get("error") in PRINTER_ERRORS:
            add(WARNING, "Impresoras", f"{p['name']}: {PRINTER_ERRORS[p['error']]}")
        if (p.get("jobs") or 0) > 0:
            add(WARNING, "Impresoras", f"{p['name']} tiene {plural(p['jobs'], 'trabajo', 'trabajos')} en cola",
                "Si no imprime, puede haber un trabajo atascado.")

    stopped = relevant_services(data.get("services"))
    if stopped:
        names = ", ".join(s.get("display") or s.get("name") for s in stopped[:5])
        more = f" y {len(stopped) - 5} más" if len(stopped) > 5 else ""
        title = "Hay un servicio automático detenido" if len(stopped) == 1 else f"Hay {len(stopped)} servicios automáticos detenidos"
        add(WARNING, "Servicios", title, names + more + ".")

    events = data.get("events") or []
    critical = [e for e in events if e.get("level") == 1]
    if critical:
        sources = Counter(f"{e.get('source')} (Id {e.get('id')})" for e in critical).most_common()
        detail = f"Origen: {sources[0][0]}." if len(sources) == 1 else f"El más repetido: {sources[0][0]}."
        add(WARNING, "Eventos", f"{plural(len(critical), 'evento crítico', 'eventos críticos')} en los últimos {data.get('eventDays', 7)} días", detail)
    errors = [e for e in events if e.get("level") == 2]
    if len(errors) >= 50:
        add(WARNING, "Eventos", f"{len(errors)} errores en el visor de eventos", "Revisa el desglose para ver qué se repite.")

    bat = data.get("battery") or {}
    if bat.get("charge") is not None and bat["charge"] < 20 and bat.get("status") != 2:
        add(WARNING, "Batería", "Batería baja", f"Carga al {bat['charge']} % y sin cargador.")

    found.sort(key=lambda f: ORDER[f["level"]])
    return found


def overall(findings):
    if any(f["level"] == CRITICAL for f in findings):
        return CRITICAL
    if findings:
        return WARNING
    return OK


def summary_text(data, findings, ticket="", problem=""):
    s = data.get("system") or {}
    net = data.get("connectivity") or {}
    when = parse_date(data.get("collectedAt"))
    lines = [f"DIAGNÓSTICO {s.get('computer', '')} · {when:%d/%m/%Y %H:%M}" if when else f"DIAGNÓSTICO {s.get('computer', '')}"]
    if ticket:
        lines.append(f"Ticket: {ticket}")
    if problem:
        lines.append(f"Problema indicado: {problem}")
    hw = " ".join(filter(None, [s.get("manufacturer"), s.get("model")]))
    if hw or s.get("serial"):
        lines.append("Equipo: " + " · ".join(filter(None, [hw, f"S/N {s['serial']}" if s.get("serial") else ""])))
    if s.get("os") or s.get("user"):
        os_name = f"{s['os']} ({s['osBuild']})" if s.get("os") and s.get("osBuild") else s.get("os")
        lines.append(" · ".join(filter(None, [f"Sistema: {os_name}" if os_name else "", f"Usuario: {s['user']}" if s.get("user") else ""])))
    ips = [ip for n in data.get("network") or [] for ip in n.get("ipv4", [])]
    lines.append(f"IP: {', '.join(ips) or 'sin IP'} · Puerta de enlace: {'OK' if (net.get('gateway') or {}).get('ok') else 'sin respuesta'}"
                 f" · Internet: {'OK' if (net.get('http') or {}).get('ok') or (net.get('internet') or {}).get('ok') else 'sin salida'}"
                 f" · DNS: {'OK' if (net.get('dns') or {}).get('ok') else 'fallo'}")
    lines.append("")
    if findings:
        lines.append("Avisos:")
        lines += [f"- [{'CRÍTICO' if f['level'] == CRITICAL else 'AVISO'}] {f['title']}" + (f": {f['detail']}" if f["detail"] else "") for f in findings]
    else:
        lines.append("Sin avisos: no se han encontrado problemas.")
    return "\n".join(lines)
