"""
control.py
==========
Panel de Control (Retroceso) — Sistema IoT Bucaramanga

Permite apagar, calibrar, ajustar frecuencia y reiniciar
cualquier dispositivo en tiempo real.

El collector.py lee control.json cada ciclo y aplica los comandos.

Uso interactivo:
    python control.py

Uso directo (sin menú):
    python control.py --device DT-BUC-GIR --cmd off
    python control.py --device DT-BUC-CAB --cmd calibrate --offset -1.5
    python control.py --device DT-BUC-MOV --cmd interval --value 30
    python control.py --device DT-BUC-ALT --cmd restart
    python control.py --device EST-BUC-API --cmd on
"""

import argparse
import json
import os

CONTROL_FILE = "control.json"

DEVICES = [
    ("EST-BUC-API", "Centro — API Real"),
    ("DT-BUC-CAB",  "Cabecera"),
    ("DT-BUC-LAG",  "Lagos del Cacique"),
    ("DT-BUC-FLO",  "Floridablanca"),
    ("DT-BUC-GIR",  "Girón"),
    ("DT-BUC-PIE",  "Piedecuesta"),
    ("DT-BUC-NOR",  "Norte (UIS)"),
    ("DT-BUC-ORI",  "Oriental"),
    ("DT-BUC-MOV",  "Estación Móvil"),
    ("DT-BUC-ALT",  "Alto de Mejoras"),
]

COMMANDS = {
    "1": "off",
    "2": "on",
    "3": "calibrate",
    "4": "interval",
    "5": "mute",
    "6": "unmute",
    "7": "restart",
}


def load_pending():
    if os.path.exists(CONTROL_FILE):
        with open(CONTROL_FILE, "r") as f:
            try:
                return json.load(f)
            except Exception:
                return []
    return []


def save_commands(cmds):
    pending = load_pending()
    pending.extend(cmds)
    with open(CONTROL_FILE, "w") as f:
        json.dump(pending, f, indent=2)
    print(f"\n✅ Comando(s) guardados en {CONTROL_FILE}")
    print("   El collector.py los aplicará en el próximo ciclo.\n")


def print_banner():
    print("=" * 55)
    print("  🌦️  CONTROL IoT — Estaciones Bucaramanga")
    print("=" * 55)


def select_device():
    print("\n📍 Dispositivos disponibles:\n")
    for i, (did, name) in enumerate(DEVICES, 1):
        print(f"  {i:2}. [{did}] {name}")
    print()
    while True:
        try:
            sel = int(input("  Selecciona dispositivo (número): "))
            if 1 <= sel <= len(DEVICES):
                return DEVICES[sel - 1][0]
        except ValueError:
            pass
        print("  ⚠️  Opción inválida.")


def select_all_or_one():
    print("\n  a. Un dispositivo específico")
    print("  b. TODOS los dispositivos")
    choice = input("\n  Opción: ").strip().lower()
    if choice == "b":
        return [d[0] for d in DEVICES]
    return [select_device()]


def select_command():
    print("\n⚙️  Comandos disponibles:\n")
    print("  1. Apagar dispositivo       (off)")
    print("  2. Encender dispositivo     (on)")
    print("  3. Calibrar temperatura     (calibrate)")
    print("  4. Ajustar intervalo        (interval)")
    print("  5. Silenciar alertas        (mute)")
    print("  6. Activar alertas          (unmute)")
    print("  7. Reiniciar dispositivo    (restart)")
    print()
    while True:
        sel = input("  Selecciona comando: ").strip()
        if sel in COMMANDS:
            return COMMANDS[sel]
        print("  ⚠️  Opción inválida.")


def build_commands(device_ids, cmd):
    cmds = []
    for did in device_ids:
        c = {"device": did, "cmd": cmd}

        if cmd == "calibrate":
            while True:
                try:
                    offset = float(input("\n  Offset de calibración (°C, ej: -1.5 / +2.0): "))
                    c["offset"] = offset
                    break
                except ValueError:
                    print("  ⚠️  Ingresa un número válido.")

        elif cmd == "interval":
            while True:
                try:
                    val = int(input("\n  Nuevo intervalo en segundos (ej: 30, 60, 120): "))
                    if val >= 5:
                        c["value"] = val
                        break
                    print("  ⚠️  Mínimo 5 segundos.")
                except ValueError:
                    print("  ⚠️  Ingresa un número entero.")

        cmds.append(c)
    return cmds


def interactive_mode():
    print_banner()
    while True:
        print("\n¿Qué deseas hacer?\n")
        print("  1. Enviar comando a dispositivo(s)")
        print("  2. Ver comandos pendientes")
        print("  3. Limpiar comandos pendientes")
        print("  0. Salir")
        print()
        opt = input("  Opción: ").strip()

        if opt == "0":
            print("\n  👋 Hasta luego.\n")
            break

        elif opt == "1":
            device_ids = select_all_or_one()
            cmd = select_command()
            cmds = build_commands(device_ids, cmd)
            save_commands(cmds)
            for c in cmds:
                print(f"  → {c}")

        elif opt == "2":
            pending = load_pending()
            if not pending:
                print("\n  (No hay comandos pendientes)")
            else:
                print(f"\n  Comandos pendientes ({len(pending)}):")
                for c in pending:
                    print(f"    {c}")

        elif opt == "3":
            with open(CONTROL_FILE, "w") as f:
                json.dump([], f)
            print("\n  🗑️  Comandos pendientes eliminados.")

        else:
            print("  ⚠️  Opción inválida.")


def cli_mode(args):
    """Modo no interactivo para scripting."""
    cmd_obj = {"device": args.device, "cmd": args.cmd}
    if args.cmd == "calibrate":
        if args.offset is None:
            print("Error: --offset requerido para calibrate")
            return
        cmd_obj["offset"] = args.offset
    elif args.cmd == "interval":
        if args.value is None:
            print("Error: --value requerido para interval")
            return
        cmd_obj["value"] = int(args.value)
    save_commands([cmd_obj])
    print(f"Comando enviado: {cmd_obj}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Control de dispositivos IoT Bucaramanga")
    parser.add_argument("--device", help="ID del dispositivo (ej: DT-BUC-GIR)")
    parser.add_argument("--cmd",    help="Comando: off, on, calibrate, interval, mute, unmute, restart")
    parser.add_argument("--offset", type=float, help="Offset para calibrate (°C)")
    parser.add_argument("--value",  type=float, help="Valor para interval (segundos)")
    args = parser.parse_args()

    if args.device and args.cmd:
        cli_mode(args)
    else:
        interactive_mode()
