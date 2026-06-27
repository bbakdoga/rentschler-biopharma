#!/usr/bin/env python3
"""
BPR Validation Tool — entry point.
Run:  python main.py
      python main.py path/to/batch.pdf          # headless processing
      python main.py --revalidate <batch_id>     # re-run rules only
"""
import sys
from pathlib import Path

# Ensure the project root is on the path regardless of working directory
sys.path.insert(0, str(Path(__file__).parent))

from db.session import init_db


def _headless(pdf_path: str):
    from processor import BPRProcessor

    def progress(cur, tot, msg=''):
        bar = '█' * int(cur / tot * 30)
        print(f"\r[{bar:<30}] {cur}/{tot}  {msg}", end='', flush=True)

    proc = BPRProcessor()
    bid  = proc.process(pdf_path, progress)
    print(f"\n\nDone — batch_id={bid}")

    from db.session import get_session
    from db.models import ValidationResult
    session = get_session()
    try:
        results = (session.query(ValidationResult)
                   .filter(ValidationResult.batch_id == bid)
                   .order_by(ValidationResult.severity).all())
        errors   = [r for r in results if r.severity == 'error']
        warnings = [r for r in results if r.severity == 'warning']
        print(f"\nValidation summary: {len(errors)} error(s), "
              f"{len(warnings)} warning(s), "
              f"{len(results) - len(errors) - len(warnings)} info")
        for r in results:
            icon = {'error': '✗', 'warning': '⚠', 'info': 'ℹ'}.get(r.severity, '·')
            print(f"  {icon} [{r.rule_id}] §{r.section or '?'} p.{r.page_num or '?'}: {r.message}")
    finally:
        session.close()


def _revalidate(batch_id: int):
    from db.session import get_session
    from db.models import Batch, ValidationResult
    from validate.engine import ValidationEngine

    session = get_session()
    try:
        batch = session.get(Batch, batch_id)
        if not batch:
            print(f"Batch {batch_id} not found.")
            return
        # Clear old results
        session.query(ValidationResult).filter(
            ValidationResult.batch_id == batch_id
        ).delete()
        session.commit()

        eng     = ValidationEngine()
        results = eng.run(batch, session)
        errors  = sum(1 for r in results if r.severity == 'error')
        print(f"Re-validation done: {errors} error(s), "
              f"{len(results) - errors} other finding(s).")
    finally:
        session.close()


def main():
    init_db()

    args = sys.argv[1:]

    if not args:
        from ui.app import BPRApp
        BPRApp().run()
        return

    if args[0] == '--revalidate' and len(args) == 2:
        _revalidate(int(args[1]))
        return

    pdf = args[0]
    if not Path(pdf).exists():
        print(f"File not found: {pdf}")
        sys.exit(1)
    _headless(pdf)


if __name__ == "__main__":
    main()
