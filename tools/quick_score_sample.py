"""Muestra un sample de scores post-normalizacion para validar visualmente."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.connection import get_connection
from app.db.repositories import AgentRepo, ArchetypeRepo, DiscSetRepo, InventoryDiscRepo
from app.core.score_normalizer import ScoringContext
from app.core.recommender import recomendar
from collections import Counter

con = get_connection()
agent_repo = AgentRepo(con)
arch_repo  = ArchetypeRepo(con)
set_repo   = DiscSetRepo(con)
disc_repo  = InventoryDiscRepo(con)
ctx = ScoringContext()

discs = disc_repo.get_all_active()
print(f"Evaluando {len(discs)} discos...")

recs = Counter()
top10 = []

for d in discs:
    rec = recomendar(d, agent_repo, arch_repo, set_repo, ctx)
    recs[rec.tipo] += 1
    if rec.tipo in ("equipar", "mejorar") and rec.score_norm > 0.5:
        top10.append((rec.score_norm, d.id, d.slot, d.main_stat, rec.agente_nombre, rec.tipo))

print("\nDistribucion de recomendaciones:")
for tipo in ("equipar", "mejorar", "reserva", "descartar"):
    print(f"  {tipo:10s}: {recs[tipo]}")

top10.sort(reverse=True)
print("\nTop 10 discos por score:")
print(f"  {'score':>6}  {'id':>4}  {'slot'}  {'main':25s}  {'agente':20s}  tipo")
for score, did, slot, main, agente, tipo in top10[:10]:
    main_s = (main or "?")[:25]
    agente_s = (agente or "?")[:20]
    print(f"  {score:.3f}   {did:>4}    {slot}   {main_s:25s}  {agente_s:20s}  {tipo}")

con.close()
