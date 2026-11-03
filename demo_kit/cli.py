import argparse
import json
import logging
import sys

from bson import ObjectId

from demo_kit import config, pipeline, safety

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)


class _JsonEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, ObjectId):
            return str(o)
        try:
            return o.isoformat()
        except AttributeError:
            return str(o)


def _venues(arg):
    return [v.strip() for v in arg.split(",") if v.strip()] or None


def main(argv=None):
    parser = argparse.ArgumentParser(prog="demo_kit")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("refresh", help="prod ops → playda_demo (masked)")
    p.add_argument("--venues", help="comma-separated venue ids; omit for full copy")
    p.add_argument("--lookback-days", type=int, default=None)
    p.add_argument("--pair-crm", action="store_true",
                   help="also refresh playda_crm_demo for the same venues")

    p = sub.add_parser("refresh-crm", help="prod CRM → playda_crm_demo (masked)")
    p.add_argument("--venues", help="comma-separated venue ids; omit for full copy")

    sub.add_parser("status", help="show demo db meta + collection counts")

    args = parser.parse_args(argv)
    try:
        if args.command == "refresh":
            report = pipeline.refresh_ops(
                venue_ids=_venues(args.venues) if args.venues else None,
                lookback_days=args.lookback_days,
                pair_crm=args.pair_crm,
            )
        elif args.command == "refresh-crm":
            report = pipeline.refresh_crm(
                venue_ids=_venues(args.venues) if args.venues else None
            )
        else:
            report = pipeline.status()
    except safety.SafetyError as exc:
        print(f"SAFETY ABORT: {exc}", file=sys.stderr)
        sys.exit(2)
    print(json.dumps(report, indent=2, cls=_JsonEncoder))


if __name__ == "__main__":
    main()
