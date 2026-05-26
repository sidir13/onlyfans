#!/usr/bin/env python
"""Script d ecoute des flux MQTT publies par le simulateur Jumeaux Chauds.

Souscrit aux topics du cluster et affiche les messages en temps reel.
Utile pour deboguer, monitorer ou developper un consumer custom.

Usage:
    python scripts/mqtt_listener.py [OPTIONS]

Options:
    --broker   Adresse du broker MQTT         [default: localhost]
    --port     Port du broker                  [default: 1883]
    --topic    Topic(s) a ecouter (wildcard)   [default: dt/#]
    --cluster  Filtrer sur un cluster          [default: tous]
    --format   Format d affichage (pretty|json|csv) [default: pretty]
    --output   Fichier de sortie (optionnel)

Exemples:
    python scripts/mqtt_listener.py
    python scripts/mqtt_listener.py --cluster cluster_alpha
    python scripts/mqtt_listener.py --topic "dt/cluster_alpha/+/telemetry" --format json
    python scripts/mqtt_listener.py --output logs/mqtt_capture.jsonl
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import aiomqtt
except ImportError:
    print("[ERREUR] aiomqtt non installe. Lancer: pip install aiomqtt")
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("jumeaux-chauds.listener")

# Compteurs globaux
_msg_count = 0
_start_time = datetime.now()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ecoute des flux MQTT - Jumeaux Chauds",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--broker",
        default=os.getenv("MQTT_BROKER_HOST", "localhost"),
        help="Adresse du broker MQTT [default: localhost]",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("MQTT_BROKER_PORT", "1883")),
        help="Port du broker MQTT [default: 1883]",
    )
    parser.add_argument(
        "--topic",
        default=os.getenv("MQTT_TOPIC", "dt/#"),
        help="Topic MQTT a ecouter (wildcards # et + supportes) [default: dt/#]",
    )
    parser.add_argument(
        "--cluster",
        default=os.getenv("CLUSTER_ID", ""),
        help="Filtrer sur un cluster specifique (ex: cluster_alpha)",
    )
    parser.add_argument(
        "--format",
        choices=["pretty", "json", "csv"],
        default=os.getenv("OUTPUT_FORMAT", "pretty"),
        help="Format d affichage des messages [default: pretty]",
    )
    parser.add_argument(
        "--output",
        default=os.getenv("OUTPUT_FILE", ""),
        help="Fichier de sortie .jsonl (optionnel, append mode)",
    )
    parser.add_argument(
        "--log-level",
        default=os.getenv("LOG_LEVEL", "WARNING"),
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Niveau de log [default: WARNING]",
    )
    return parser.parse_args()


def format_pretty(topic: str, payload: dict) -> str:
    """Affichage lisible colore pour le terminal."""
    ts = payload.get("ts", datetime.now().isoformat())
    machine_id = payload.get("machine_id", topic.split("/")[-2] if "/" in topic else "?")
    status = payload.get("status", "?")
    temp = payload.get("temperature_c", payload.get("value", "?"))

    # Indicateurs visuels selon statut
    status_icon = {"on": "[ON ]", "off": "[OFF]", "degraded": "[DEG]"}.get(status, "[?  ]")

    lines = [f"  {status_icon} {machine_id:<20} topic={topic}"]
    if isinstance(temp, float):
        lines.append(f"         temp={temp:.1f}C")
    if "fans" in payload:
        fan_info = " | ".join(
            f"fan{i}={f.get('rpm_pct', 0):.0f}%" for i, f in enumerate(payload["fans"])
        )
        lines.append(f"         fans: {fan_info}")
    if "power_w" in payload:
        lines.append(f"         power={payload['power_w']:.1f}W")
    return "\n".join(lines)


def format_csv_line(topic: str, payload: dict) -> str:
    """Ligne CSV: ts,topic,machine_id,status,temperature_c,power_w"""
    ts = payload.get("ts", datetime.now().isoformat())
    machine_id = payload.get("machine_id", "")
    status = payload.get("status", "")
    temp = payload.get("temperature_c", "")
    power = payload.get("power_w", "")
    return f"{ts},{topic},{machine_id},{status},{temp},{power}"


async def listen(
    broker: str,
    port: int,
    topic: str,
    cluster_filter: str,
    fmt: str,
    output_file: str,
) -> None:
    global _msg_count

    out_fp = None
    if output_file:
        Path(output_file).parent.mkdir(parents=True, exist_ok=True)
        out_fp = open(output_file, "a", encoding="utf-8")  # noqa: WPS515
        logger.info("Sortie vers fichier: %s", output_file)

    # Afficher l en-tete CSV
    if fmt == "csv":
        header = "ts,topic,machine_id,status,temperature_c,power_w"
        print(header)
        if out_fp:
            out_fp.write(header + "\n")

    print(f"Connexion au broker MQTT {broker}:{port} | topic={topic}")
    if cluster_filter:
        print(f"Filtre cluster: {cluster_filter}")
    print("En attente de messages... (Ctrl+C pour arreter)\n")

    try:
        async with aiomqtt.Client(hostname=broker, port=port) as client:
            await client.subscribe(topic)
            async for message in client.messages:
                msg_topic = str(message.topic)

                # Filtrer par cluster si specifie
                if cluster_filter and cluster_filter not in msg_topic:
                    continue

                # Decoder le payload JSON
                try:
                    payload = json.loads(message.payload.decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    payload = {"raw": message.payload.decode("utf-8", errors="replace")}

                _msg_count += 1

                # Afficher selon le format
                if fmt == "pretty":
                    line = format_pretty(msg_topic, payload)
                elif fmt == "csv":
                    line = format_csv_line(msg_topic, payload)
                else:  # json
                    line = json.dumps({"topic": msg_topic, "payload": payload}, ensure_ascii=False)

                print(line)

                # Ecrire dans le fichier si specifie
                if out_fp:
                    raw_line = json.dumps(
                        {"topic": msg_topic, "payload": payload}, ensure_ascii=False
                    )
                    out_fp.write(raw_line + "\n")
                    out_fp.flush()

    except aiomqtt.MqttError as e:
        logger.error("Erreur MQTT: %s", e)
        logger.error("Verifier que le broker est lance: docker compose up broker")
    finally:
        if out_fp:
            out_fp.close()
        elapsed = (datetime.now() - _start_time).total_seconds()
        print(f"\n{_msg_count} messages recus en {elapsed:.1f}s ({_msg_count/max(elapsed,1):.1f} msg/s)")


async def main() -> None:
    args = parse_args()
    logging.getLogger().setLevel(getattr(logging, args.log_level))

    # Si cluster specifie et topic par defaut, affiner le topic
    topic = args.topic
    if args.cluster and topic == "dt/#":
        topic = f"dt/{args.cluster}/#"

    try:
        await listen(
            broker=args.broker,
            port=args.port,
            topic=topic,
            cluster_filter=args.cluster,
            fmt=args.format,
            output_file=args.output,
        )
    except KeyboardInterrupt:
        print("\nArret demande par l utilisateur.")


if __name__ == "__main__":
    asyncio.run(main())
