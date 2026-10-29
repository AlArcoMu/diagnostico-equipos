import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

from . import analysis, collector, report

__version__ = "1.0.0"


def default_folder():
    docs = Path.home() / "Documents"
    return (docs if docs.exists() else Path.home()) / "Diagnosticos"


def safe(text):
    return re.sub(r"[^\w.-]+", "-", text or "", flags=re.UNICODE).strip("-")[:40]


def run(days=7, ticket="", problem="", folder=None, demo=False, save_json=False, progress=lambda _m: None):
    data = collector.load_demo() if demo else collector.collect(days, progress)
    progress("Analizando los resultados…")
    now = analysis.parse_date(data.get("collectedAt")) if demo else None
    findings = analysis.analyse(data, now)
    folder = Path(folder or default_folder())
    folder.mkdir(parents=True, exist_ok=True)
    computer = (data.get("system") or {}).get("computer") or "equipo"
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    name = "_".join(filter(None, ["diagnostico", safe(computer), safe(ticket), stamp]))
    html = folder / f"{name}.html"
    html.write_text(report.render(data, findings, ticket, problem), encoding="utf-8")
    if save_json:
        (folder / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = analysis.summary_text(data, findings, ticket, problem)
    return html, findings, summary


def cli(argv=None):
    parser = argparse.ArgumentParser(prog="diagnostico", description="Genera un informe de diagnóstico del equipo para adjuntarlo a un ticket.")
    parser.add_argument("--cli", action="store_true", help="ejecutar sin ventana")
    parser.add_argument("--ticket", default="", help="número de ticket o incidencia")
    parser.add_argument("--problema", default="", help="problema que indica el usuario")
    parser.add_argument("--dias", type=int, default=7, help="días de eventos a revisar (por defecto 7)")
    parser.add_argument("--salida", default=None, help="carpeta donde guardar el informe")
    parser.add_argument("--json", action="store_true", help="guardar también los datos en bruto en JSON")
    parser.add_argument("--demo", action="store_true", help="usar datos de ejemplo")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser.parse_args(argv)


def main(argv=None):
    args = cli(argv)
    if not args.cli:
        from .gui import App
        App(demo=args.demo, days=args.dias, folder=args.salida).mainloop()
        return 0
    try:
        html, findings, summary = run(args.dias, args.ticket, args.problema, args.salida, args.demo, args.json,
                                      progress=lambda m: print(m, file=sys.stderr))
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(summary)
    print(f"\nInforme guardado en {html}")
    return 2 if analysis.overall(findings) == analysis.CRITICAL else 0
