"""
Orquestra a coleta de dados e geração do dashboard.
"""
import logging
from app.database import init_db
from app.macro import collect_all as collect_macro
from app.market import collect_all as collect_market
from app.cot import collect_cot, collect_cot_tff
from app.generator import generate

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def run_pipeline():
    log.info("=== Pipeline iniciado ===")
    init_db()
    collect_macro()
    collect_market()
    collect_cot()
    collect_cot_tff()
    generate()
    log.info("=== Pipeline concluido ===")
